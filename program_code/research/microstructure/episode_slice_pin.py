#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""episode_slice_pin — bb_reversion R1 重放的 L1/trades 切片釘存器（FIX-4 / GO 條件 C2）。

MODULE_NOTE
模塊用途：
  move2 決策 dossier（docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-10--move2_decision_dossier.md）
  §③④ FIX-4 的死線工具。market.l1_events 有 21 天滾動保留 → 2026-06-28→07-02 episode 的
  full-L1 BBO 事件流會在 ~2026-07-19 起蒸發。本 script 在左緣前，把 bb_reversion entry 信號
  episode（gap-dedup 30min）∪ 已成交 fill anchor（Buy 開倉腿 + Sell 平倉腿，保 post-fill markout
  L1）的 per-symbol 合併窗口原始 row 釘進一個 write-once 的 immutable artifact（sha256），使凍結
  斷言錨可遷入 artifact store、R1 三週後仍可離線複核。G8（grid close_maker 校準）的 L1 context
  已滑出 21d 保留窗（探針 2026-07-11：last attempt 2026-06-19、l1 min 2026-06-20 → 0 存活 L1），
  故 manifest 以 g8_status=unpinnable_l1_aged_out 誠實標註，不靜默輸出空段。

  窗口定義（dossier §④B）：每個 anchor t_place → [t_place − 60s, t_place + τ + 300s]，τ=60s，
  即 [t−60s, t+360s]。四張表（market.l1_events / trading.fills / trading.orders /
  trading.signals）在該 symbol × 窗口內的原始 row 全量匯出（SELECT *，不投影，保 raw）。

  ⚠️ $0 read-only：只 SELECT，0 寫 PG、0 order path、0 auth/lease/risk。唯一寫入 = 本地
     artifact 目錄（write-once）。連線走 sibling data_loader.connect() 的既有 read-only 慣例
     （OPENCLAW_DATABASE_URL 或 libpq PG* env；--dsn 覆蓋）+ set_session(readonly=True)。

主要函數（純函數可離線測）：
  - compute_window：anchor ts → (lo_dt, hi_dt, lo_ms, hi_ms)。窗口數學單一真源。
  - dedup_episodes：per-symbol gap-dedup（預設 1800s=30min）。
  - build_manifest / write_artifact：manifest.json + per-window parquet(或 csv.gz) + sha256sums。

CLI：
  - 預設 --dry-run：不連 PG。印出解析計畫（凍結 SQL、窗口公式、planned artifact path）；
    若給 --anchors-fixture <json> 則從 fixture 解析窗口並印出（供離線驗證/self-test）。
  - --apply：真跑（連 PG、解析 episodes/attempts、匯出 artifact）。
  - --dsn / OPENCLAW_DATABASE_URL、--out <dir>。

硬邊界：
  - 只 SELECT market.l1_events / trading.fills / trading.orders / trading.signals。
  - artifact write-once：目標目錄存在且非空 → fail-loud，不覆蓋。
  - 跨平台：無硬編 /Users/ncyu 或 /home/ncyu；--out 預設 repo-relative 或 $OPENCLAW_ARTIFACT_ROOT。
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

# ── 窗口 / dedup 常數（dossier §④B / N7；凍結，勿因結果調整） ──
PRE_S = 60          # t_place 前置 60s
TAU_S = 60          # τ=60s（信號壽命上界）
POST_S = 300        # t_place + τ 後再 +300s
DEDUP_GAP_S = 1800  # per-symbol gap-dedup 30min → ~25 episodes（N7）
L1_RETENTION_DAYS = 21   # market.l1_events 滾動保留（N6；trades 45d / signals 90d）
DEFAULT_LOOKBACK_DAYS = 21  # 預設 signal 查詢回看 = L1 保留窗（只釘存仍有 L1 覆蓋的 episode）

# 策略名 literal（rust/openclaw_engine/src/strategies/registry.rs module 名 = strategy_name 欄值）
BB_STRATEGY = "bb_reversion"
GRID_STRATEGY = "grid_trading"
# bb_reversion entry 信號類型：trading.signals.signal_type literal = 'OpenLong' / 'OpenShort'
# （非 'LONG'/'SHORT'；read-only PG 探針 2026-07-11 確認）。排除 CLOSE/HOLD；OpenShort 僅
# 2026-07-06 後才出現，下游單列標註，此處只錨 entry 側。
BB_ENTRY_SIGNAL_TYPES = ("OpenLong", "OpenShort")
# bb_reversion 成交 anchor 兩側：Buy=開倉腿、Sell=平倉腿（不 dedup，每筆為真事件）。
BB_FILL_SIDES = ("Buy", "Sell")

# PG statement_timeout 預設（ms）；--statement-timeout 可調（OPS preflight belt-and-suspenders）。
DEFAULT_STATEMENT_TIMEOUT_MS = 60000

# G8 grid close_maker 校準集 L1 已 aged-out（read-only PG 探針 2026-07-11 確認）：
#   grid_trading close_maker_attempt=TRUE 最後一筆 = 2026-06-19T18:48Z（本地 20:48，全時段 n=287），
#   而 market.l1_events 最早 ts = 2026-06-20 → 0 筆 close_maker attempt 有存活的 L1 context。
#   markout_bps 讀數本身仍存 trading.fills（365d 保留），僅 L1 上下文不可復原（先於本 pin 的既有損失）。
G8_LAST_CLOSE_MAKER_ATTEMPT_UTC = "2026-06-19T18:48:00Z"
G8_L1_EVENTS_MIN_UTC = "2026-06-20"
G8_STATUS_UNPINNABLE = "unpinnable_l1_aged_out"
G8_STATUS_PINNED = "pinned"

# 合併窗 provenance 固定排序（signal 在前、fill 在後；供 manifest 穩定輸出）。
_PROVENANCE_ORDER = ("bb_signal", "bb_fill")

RETENTION_NOTE = (
    "market.l1_events 有 21 天滾動保留（timescaledb drop_after='21 days'）；"
    "trading.fills=45d、trading.signals=90d。本 artifact 在左緣（~2026-07-19）前釘存 "
    "06-28→07-02 episode 的 full-L1 切片，使 R1 重放與凍結斷言錨三週後仍可離線複核。"
)


# ==========================================================
# 純函數：窗口數學 + episode dedup（0 DB，可離線測）
# ==========================================================
def _as_utc(ts: Any) -> datetime:
    """把 ts（datetime 或 ISO8601 字串）正規化成 tz-aware UTC datetime。"""
    if isinstance(ts, datetime):
        d = ts
    else:
        s = str(ts).strip()
        # 舊版 Python 的 fromisoformat 不吃 'Z' 尾綴 → 正規化成 +00:00
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def compute_window(anchor_ts: Any, pre_s: int = PRE_S, tau_s: int = TAU_S,
                   post_s: int = POST_S) -> dict[str, Any]:
    """anchor ts → 窗口邊界。窗口數學單一真源：[t−pre, t+τ+post]。

    回傳 dict：lo_dt / hi_dt（tz-aware UTC）、lo_ms / hi_ms（epoch 毫秒 int）、anchor_ms。
    預設 pre=60 / tau=60 / post=300 → [t−60s, t+360s]（dossier §④B）。
    """
    t = _as_utc(anchor_ts)
    lo = t - timedelta(seconds=pre_s)
    hi = t + timedelta(seconds=tau_s + post_s)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    to_ms = lambda x: int((x - epoch).total_seconds() * 1000)  # noqa: E731
    return {
        "lo_dt": lo,
        "hi_dt": hi,
        "lo_ms": to_ms(lo),
        "hi_ms": to_ms(hi),
        "anchor_ms": to_ms(t),
    }


def dedup_episodes(rows: list[dict[str, Any]], gap_s: int = DEDUP_GAP_S) -> list[dict[str, Any]]:
    """per-symbol gap-dedup：同 symbol 內，與上一個保留 anchor 間隔 ≤ gap_s 的信號折疊進同一 episode。

    rows：每筆需含 'ts'（datetime/ISO）與 'symbol'；其餘欄位（signal_id 等）保留於首筆代表。
    回傳保留的 episode 代表 row（每筆附 'anchor_ts' = 正規化 UTC datetime）並依 (symbol, ts) 排序。
    為什麼 per-symbol：不同 symbol 的信號在時間上重疊不代表同一 episode（N7 獨立時間簇 ≈14）。
    """
    norm = []
    for r in rows:
        rr = dict(r)
        rr["anchor_ts"] = _as_utc(r["ts"])
        norm.append(rr)
    norm.sort(key=lambda x: (str(x.get("symbol", "")), x["anchor_ts"]))

    kept: list[dict[str, Any]] = []
    last_by_symbol: dict[str, datetime] = {}
    for r in norm:
        sym = str(r.get("symbol", ""))
        prev = last_by_symbol.get(sym)
        if prev is None or (r["anchor_ts"] - prev).total_seconds() > gap_s:
            kept.append(r)
            last_by_symbol[sym] = r["anchor_ts"]
        # 否則折疊進上一 episode（丟棄，不新增 anchor）
    return kept


# ==========================================================
# 凍結 SQL（read-only；SELECT * 保 raw；ts 為所有表窗口欄）
# ==========================================================
# bb_reversion entry 信號解析（dedup 前母集）。ts 窗由 caller 傳（--since/--until 或 lookback）。
BB_EPISODE_SQL = (
    "SELECT ts, signal_id, symbol, strategy_name, signal_type, strength, context_id "
    "FROM trading.signals "
    "WHERE strategy_name = %(strategy)s "
    "AND signal_type = ANY(%(entry_types)s) "
    "AND ts >= %(since)s AND ts < %(until)s "
    "ORDER BY symbol, ts"
)

# bb_reversion 已成交 fill anchor（exit/close 腿健壯性）。持倉可長於 entry 信號窗，平倉腿的
# post-fill markout L1（60s/300s）須以真實 fill ts 為錨才能保存。Buy=開倉腿、Sell=平倉腿；不 dedup。
BB_FILL_SQL = (
    "SELECT ts, fill_id, order_id, symbol, strategy_name, side "
    "FROM trading.fills "
    "WHERE strategy_name = %(strategy)s "
    "AND side = ANY(%(sides)s) "
    "AND ts >= %(since)s AND ts < %(until)s "
    "ORDER BY symbol, ts"
)

# G8 校準 anchor：grid_trading close_maker 已成交 attempt（fills.close_maker_attempt=TRUE，V094）。
# 註：dossier N17「408 attempts / fill rate 34.8%」的完整 attempt 母集（含 no-fill fallback）之
# 精確 predicate 需 PG 驗證（見 blockers）；此處預設釘存已成交 attempt（markout n=96 讀數所在）。
G8_ATTEMPT_SQL = (
    "SELECT ts, fill_id, order_id, symbol, strategy_name, close_maker_attempt "
    "FROM trading.fills "
    "WHERE strategy_name = %(strategy)s "
    "AND close_maker_attempt = TRUE "
    "AND ts >= %(since)s AND ts < %(until)s "
    "ORDER BY symbol, ts"
)

# 每張表的窗口切片（SELECT * 保 raw；symbol × [lo,hi]）。%(sym)s / %(lo)s / %(hi)s 參數化。
SLICE_TABLES = ("market.l1_events", "trading.fills", "trading.orders", "trading.signals")


def _slice_sql(table: str) -> str:
    return (
        f"SELECT * FROM {table} "
        "WHERE symbol = %(sym)s AND ts >= %(lo)s AND ts < %(hi)s "
        "ORDER BY ts"
    )


# ==========================================================
# PG 連線（reuse sibling data_loader read-only 慣例）
# ==========================================================
def connect(dsn: Optional[str] = None, statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS):
    """read-only 連線 + 會話級唯讀/逾時護欄。沿用 sibling data_loader.connect() 慣例
    （psycopg2 + set_session(readonly=True)）。

    --dsn（或呼叫端傳 dsn）非空 → 覆寫 OPENCLAW_DATABASE_URL env 後再委派 data_loader.connect()，
    使 DSN 解析口徑與既有 microstructure loader 完全一致（不另發明新 DSN scheme）。

    OPS preflight 補償控制：exporter 可能以 superuser trading_admin 角色跑（現無專用唯讀 login role），
    故在 data_loader 的 set_session(readonly=True) 之上，再 SET default_transaction_read_only = on
    （會話級唯讀保證 = 補償控制）+ SET statement_timeout（預設 60000ms，--statement-timeout 可調），
    belt-and-suspenders 防任何寫入路徑與失控長查詢。
    """
    from . import data_loader  # 延遲匯入：保 import-time 零 DB 依賴

    if dsn:
        os.environ["OPENCLAW_DATABASE_URL"] = dsn
    conn = data_loader.connect()
    _apply_readonly_guards(conn, statement_timeout_ms)
    return conn


def _apply_readonly_guards(conn, statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS) -> None:
    """對已建立的連線施加會話級唯讀 + statement_timeout 護欄（belt-and-suspenders）。

    statement_timeout 為 argparse type=int 的受控整數，直接內插（非 bind-param）避開 SET utility
    對 extended-query bind 的相容性問題；default_transaction_read_only 為固定字面。read-only txn
    commit 使兩個 SET 在 session 層級持久生效（避免被後續事務邊界回退）。
    """
    cur = conn.cursor()
    cur.execute("SET statement_timeout = %d" % int(statement_timeout_ms))
    cur.execute("SET default_transaction_read_only = on")
    cur.close()
    conn.commit()


def _fetch_dicts(conn, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """參數化 SELECT → list[dict]（欄名取自 cursor.description）。read-only。"""
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def resolve_source_head(conn) -> dict[str, Any]:
    """來源 PG 的 now() + market.l1_events 覆蓋邊界（作 manifest 的 source head/now 錨）。"""
    cur = conn.cursor()
    cur.execute("SELECT now()")
    pg_now = cur.fetchone()[0]
    cur.execute("SELECT min(ts), max(ts), count(*) FROM market.l1_events")
    l1_min, l1_max, l1_n = cur.fetchone()
    cur.close()
    return {
        "pg_now_utc": _iso(pg_now),
        "l1_events_min_ts_utc": _iso(l1_min),
        "l1_events_max_ts_utc": _iso(l1_max),
        "l1_events_total_rows": int(l1_n) if l1_n is not None else None,
    }


# ==========================================================
# episode / attempt 解析
# ==========================================================
def resolve_episodes(conn, since: datetime, until: datetime, gap_s: int = DEDUP_GAP_S) -> list[dict[str, Any]]:
    """解析 bb_reversion entry episodes（gap-dedup 後）。"""
    raw = _fetch_dicts(conn, BB_EPISODE_SQL, {
        "strategy": BB_STRATEGY,
        "entry_types": list(BB_ENTRY_SIGNAL_TYPES),
        "since": since,
        "until": until,
    })
    return dedup_episodes(raw, gap_s=gap_s)


def resolve_bb_fill_anchors(conn, since: datetime, until: datetime) -> list[dict[str, Any]]:
    """解析 bb_reversion 已成交 fill anchors（Buy=開倉腿 / Sell=平倉腿；不 dedup，每筆真事件）。

    為何錨 fill 而非只錨 signal：持倉可長於 entry 信號窗，平倉腿的 post-fill markout L1（60s/300s）
    須以真實 fill ts 為錨才能保存（dossier 要 true post-fill markout）。每筆 fill 附 anchor_ts。
    """
    raw = _fetch_dicts(conn, BB_FILL_SQL, {
        "strategy": BB_STRATEGY,
        "sides": list(BB_FILL_SIDES),
        "since": since,
        "until": until,
    })
    for r in raw:
        r["anchor_ts"] = _as_utc(r["ts"])
    return raw


def resolve_g8_attempts(conn, since: datetime, until: datetime) -> list[dict[str, Any]]:
    """解析 grid_trading close_maker 校準 attempts（每筆 attempt 一個 anchor，不 dedup）。"""
    raw = _fetch_dicts(conn, G8_ATTEMPT_SQL, {
        "strategy": GRID_STRATEGY,
        "since": since,
        "until": until,
    })
    for r in raw:
        r["anchor_ts"] = _as_utc(r["ts"])
    return raw


def plan_windows(episodes: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    """把 anchor row 轉成窗口計畫項（kind='bb' | 'g8'）。"""
    out = []
    for i, ep in enumerate(episodes):
        win = compute_window(ep["anchor_ts"])
        out.append({
            "kind": kind,
            "idx": i,
            "symbol": str(ep.get("symbol", "")),
            "anchor_ts_utc": _iso(ep["anchor_ts"]),
            "anchor_id": str(ep.get("signal_id") or ep.get("fill_id") or ep.get("order_id") or ""),
            "lo_ts_utc": _iso(win["lo_dt"]),
            "hi_ts_utc": _iso(win["hi_dt"]),
            "lo_ms": win["lo_ms"],
            "hi_ms": win["hi_ms"],
        })
    return out


# ==========================================================
# anchor 窗口合併（signal ∪ fill，per-symbol 去重疊，避免同段 L1 重複釘存）
# ==========================================================
def _order_provenance(prov_set: set[str]) -> list[str]:
    """provenance 去重 + 固定排序（signal 前、fill 後）；未知標籤排在最後保穩定。"""
    order = {p: i for i, p in enumerate(_PROVENANCE_ORDER)}
    return sorted(prov_set, key=lambda p: order.get(p, len(_PROVENANCE_ORDER)))


def _anchor_windows(anchors: list[dict[str, Any]], provenance: str) -> list[dict[str, Any]]:
    """anchor rows → 原子窗口區間（帶 provenance；未合併）。每筆走 compute_window(anchor_ts)。"""
    out = []
    for a in anchors:
        win = compute_window(a["anchor_ts"])
        out.append({
            "symbol": str(a.get("symbol", "")),
            "provenance": provenance,
            "anchor_ts_utc": _iso(a["anchor_ts"]),
            "anchor_id": str(a.get("signal_id") or a.get("fill_id") or a.get("order_id") or ""),
            "lo_ms": win["lo_ms"],
            "hi_ms": win["hi_ms"],
            "lo_dt": win["lo_dt"],
            "hi_dt": win["hi_dt"],
        })
    return out


def merge_anchor_windows(atoms: list[dict[str, Any]], kind: str = "bb") -> list[dict[str, Any]]:
    """per-symbol 合併重疊 [lo,hi) 原子窗口，避免同段 L1 被多 anchor 重複釘存。

    半開區間 [lo,hi)：僅 it.lo_ms < cur.hi_ms 才視為重疊（相鄰觸碰 lo==hi 不共 row → 不併）。
    合併窗保留：union 覆蓋 [min lo, max hi]、provenance（去重、signal 前 fill 後）、組成 anchor 清單。
    idx 為跨 symbol 的全域序（保證檔名唯一）。
    """
    by_sym: dict[str, list[dict[str, Any]]] = {}
    for a in atoms:
        by_sym.setdefault(a["symbol"], []).append(a)

    merged: list[dict[str, Any]] = []
    for sym in sorted(by_sym):
        items = sorted(by_sym[sym], key=lambda x: (x["lo_ms"], x["hi_ms"]))
        cur: Optional[dict[str, Any]] = None
        for it in items:
            anchor_ref = {
                "provenance": it["provenance"],
                "anchor_ts_utc": it["anchor_ts_utc"],
                "anchor_id": it["anchor_id"],
            }
            if cur is None or it["lo_ms"] >= cur["_hi_ms"]:
                if cur is not None:
                    merged.append(cur)
                cur = {
                    "symbol": sym,
                    "_lo_ms": it["lo_ms"], "_hi_ms": it["hi_ms"],
                    "_lo_dt": it["lo_dt"], "_hi_dt": it["hi_dt"],
                    "_prov": {it["provenance"]},
                    "_anchors": [anchor_ref],
                }
            else:
                if it["hi_ms"] > cur["_hi_ms"]:
                    cur["_hi_ms"] = it["hi_ms"]
                    cur["_hi_dt"] = it["hi_dt"]
                cur["_prov"].add(it["provenance"])
                cur["_anchors"].append(anchor_ref)
        if cur is not None:
            merged.append(cur)

    out = []
    for i, w in enumerate(merged):
        anchors = w["_anchors"]
        out.append({
            "kind": kind,
            "idx": i,
            "symbol": w["symbol"],
            "provenance": _order_provenance(w["_prov"]),
            "n_anchors": len(anchors),
            "anchors": anchors,
            "anchor_ts_utc": anchors[0]["anchor_ts_utc"],  # 代表 anchor = 最早一筆
            "anchor_id": anchors[0]["anchor_id"],
            "lo_ts_utc": _iso(w["_lo_dt"]),
            "hi_ts_utc": _iso(w["_hi_dt"]),
            "lo_ms": w["_lo_ms"],
            "hi_ms": w["_hi_ms"],
        })
    return out


def build_bb_windows(signals: list[dict[str, Any]], fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """bb_reversion signal episodes ∪ realized fill anchors → per-symbol 合併後的匯出窗口清單。"""
    atoms = _anchor_windows(signals, "bb_signal") + _anchor_windows(fills, "bb_fill")
    return merge_anchor_windows(atoms, kind="bb")


def _g8_status(n_g8_windows: int) -> tuple[str, dict[str, Any]]:
    """回傳 (g8_status, g8_detail)。0 窗 → unpinnable_l1_aged_out + 探針事實；否則 pinned。

    誠實化：G8 grid close_maker 校準的 L1 context 已滑出 market.l1_events 21d 保留窗（探針事實），
    本 pin 無法釘存 G8；不靜默輸出空 g8 段而不解釋（見 module docstring / G8_* 常數）。
    """
    if n_g8_windows > 0:
        return G8_STATUS_PINNED, {"n_attempts": n_g8_windows}
    return G8_STATUS_UNPINNABLE, {
        "reason": (
            "grid_trading close_maker_attempt 的 L1 context 已滑出 market.l1_events 21d 保留窗；"
            "0 筆 attempt 有存活 L1。markout_bps 讀數本身仍存 trading.fills（365d），僅 L1 上下文不可復原。"
        ),
        "last_close_maker_attempt_utc": G8_LAST_CLOSE_MAKER_ATTEMPT_UTC,
        "l1_events_min_utc": G8_L1_EVENTS_MIN_UTC,
        "surviving_l1_attempts": 0,
    }


# ==========================================================
# artifact 寫出（write-once）+ manifest + sha256
# ==========================================================
def _iso(ts: Any) -> Optional[str]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return _as_utc(ts).isoformat()
    return str(ts)


def _pyarrow_available() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except Exception:
        return False


def _write_table_file(rows: list[dict[str, Any]], base: Path, use_parquet: bool) -> tuple[str, int]:
    """把一張表的窗口 row 寫成 parquet 或 csv.gz。回傳 (相對檔名, row 數)。

    無 pyarrow → csv.gz（對齊 data_loader/fill_sim 只依賴 pandas 的慣例）。空 row 仍寫空檔（0 row，
    保留窗口存在性證據 + 讓 sha256sums 覆蓋齊全）。
    """
    import pandas as pd

    df = pd.DataFrame(rows)
    if use_parquet:
        path = base.with_suffix(".parquet")
        df.to_parquet(path, index=False)
    else:
        path = base.with_suffix(".csv.gz")
        with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
            df.to_csv(f, index=False)
    return path.name, len(df)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head() -> Optional[str]:
    """repo source head（純檔案讀取，不 spawn git；跨平台安全）。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        gitdir = parent / ".git"
        if gitdir.is_dir():
            head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
            if head.startswith("ref:"):
                ref = head.split(" ", 1)[1].strip()
                ref_path = gitdir / ref
                if ref_path.is_file():
                    return ref_path.read_text(encoding="utf-8").strip()
                packed = gitdir / "packed-refs"
                if packed.is_file():
                    for line in packed.read_text(encoding="utf-8").splitlines():
                        if line.endswith(" " + ref) or line.endswith("\t" + ref):
                            return line.split()[0]
                return None
            return head
    return None


def write_artifact(conn, windows: list[dict[str, Any]], out_dir: Path, source_head: dict[str, Any],
                   fetch_slice: Optional[Callable] = None) -> dict[str, Any]:
    """把每個窗口的四表原始 row 匯出到 out_dir（write-once），並寫 manifest.json + sha256sums。

    fetch_slice(table, sym, lo_ms, hi_ms) -> list[dict]：可注入（測試用 mock）；預設走 PG。
    write-once：out_dir 存在且非空 → RuntimeError（不覆蓋既有 artifact）。
    """
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RuntimeError(f"artifact 目標非空，write-once 拒絕覆蓋：{out_dir}")
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    use_parquet = _pyarrow_available()
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def _default_fetch(table: str, sym: str, lo_ms: int, hi_ms: int) -> list[dict[str, Any]]:
        lo_dt = epoch + timedelta(milliseconds=lo_ms)
        hi_dt = epoch + timedelta(milliseconds=hi_ms)
        return _fetch_dicts(conn, _slice_sql(table), {"sym": sym, "lo": lo_dt, "hi": hi_dt})

    fetch = fetch_slice or _default_fetch

    manifest_windows = []
    data_files: list[str] = []
    for w in windows:
        table_counts = {}
        files_for_window = {}
        for table in SLICE_TABLES:
            rows = fetch(table, w["symbol"], w["lo_ms"], w["hi_ms"])
            short = table.replace(".", "_")
            base = data_dir / f"{short}__{w['kind']}{w['idx']:03d}_{w['symbol']}"
            fname, n = _write_table_file(rows, base, use_parquet)
            table_counts[table] = n
            files_for_window[table] = f"data/{fname}"
            data_files.append(f"data/{fname}")
        mw = dict(w)
        mw["row_counts"] = table_counts
        mw["files"] = files_for_window
        manifest_windows.append(mw)

    manifest = build_manifest(manifest_windows, source_head, use_parquet)
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # sha256sums 覆蓋 manifest + 每個 data file（write-once 完整性錨）
    sums_lines = []
    for rel in ["manifest.json"] + data_files:
        digest = _sha256_file(out_dir / rel)
        sums_lines.append(f"{digest}  {rel}")
    (out_dir / "sha256sums").write_text("\n".join(sums_lines) + "\n", encoding="utf-8")

    return manifest


def build_manifest(manifest_windows: list[dict[str, Any]], source_head: dict[str, Any],
                   use_parquet: bool) -> dict[str, Any]:
    """組裝 manifest.json（合併窗清單 + 窗口邊界 + per-table row 數 + provenance/G8 誠實標註 + 來源/保留/git 錨）。"""
    total_counts: dict[str, int] = {t: 0 for t in SLICE_TABLES}
    for w in manifest_windows:
        for t, n in w.get("row_counts", {}).items():
            total_counts[t] = total_counts.get(t, 0) + n

    bb_windows = [w for w in manifest_windows if w.get("kind") == "bb"]
    g8_windows = [w for w in manifest_windows if w.get("kind") == "g8"]
    # bb signal/fill anchor 數由合併窗的 anchors 清單推導（單一真源）。
    n_bb_signal = sum(1 for w in bb_windows for a in w.get("anchors", []) if a.get("provenance") == "bb_signal")
    n_bb_fill = sum(1 for w in bb_windows for a in w.get("anchors", []) if a.get("provenance") == "bb_fill")
    g8_status, g8_detail = _g8_status(len(g8_windows))
    return {
        "artifact_kind": "episode_slice_pin_v1",
        "purpose": "bb_reversion R1 replay L1/trades slice pin (dossier FIX-4 / C2)",
        "capture_ts_utc": datetime.now(timezone.utc).isoformat(),
        "git_source_head": _git_head(),
        "source_pg": source_head,
        "retention_note": RETENTION_NOTE,
        "window_def": {
            "formula": "[t_place - pre, t_place + tau + post]",
            "pre_s": PRE_S, "tau_s": TAU_S, "post_s": POST_S,
            "effective": f"[t-{PRE_S}s, t+{TAU_S + POST_S}s]",
            "dedup_gap_s": DEDUP_GAP_S,
        },
        "tables": list(SLICE_TABLES),
        "data_format": "parquet" if use_parquet else "csv.gz",
        "n_windows": len(manifest_windows),
        "n_bb_windows": len(bb_windows),
        "n_bb_signal_anchors": n_bb_signal,
        "n_bb_fill_anchors": n_bb_fill,
        "n_g8_attempts": len(g8_windows),
        "g8_status": g8_status,
        "g8_detail": g8_detail,
        "total_row_counts": total_counts,
        "windows": manifest_windows,
    }


# ==========================================================
# CLI
# ==========================================================
def _default_out() -> str:
    """跨平台預設 artifact 根：$OPENCLAW_ARTIFACT_ROOT 或 /tmp/openclaw（無硬編 home）。"""
    root = os.environ.get("OPENCLAW_ARTIFACT_ROOT", "/tmp/openclaw")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return str(Path(root) / "research" / "episode_slice_pin" / f"pin_{stamp}")


def _resolve_since_until(args) -> tuple[datetime, datetime]:
    """--since/--until（ISO）優先；否則 [now - lookback_days, now]（預設 21d = L1 保留窗）。"""
    now = datetime.now(timezone.utc)
    until = _as_utc(args.until) if args.until else now
    if args.since:
        since = _as_utc(args.since)
    else:
        since = until - timedelta(days=args.lookback_days)
    return since, until


def _print_plan(args, since: datetime, until: datetime, out_dir: Path) -> int:
    """--dry-run：不連 PG。印出解析計畫；若給 --anchors-fixture 則從 fixture 解析窗口並印出。"""
    print("=== episode_slice_pin DRY-RUN（未連 PG） ===")
    print(f"window formula     : [t-{PRE_S}s, t+{TAU_S + POST_S}s]（τ={TAU_S}s；dedup gap={DEDUP_GAP_S}s）")
    print(f"bb entry types     : {', '.join(BB_ENTRY_SIGNAL_TYPES)}（signals.signal_type literal；非 LONG/SHORT）")
    print(f"bb fill sides      : {', '.join(BB_FILL_SIDES)}（成交 anchor，不 dedup；Buy=開倉腿 Sell=平倉腿）")
    print(f"signal window      : {since.isoformat()} → {until.isoformat()}（lookback {args.lookback_days}d）")
    print(f"statement_timeout  : {args.statement_timeout}ms（+ SET default_transaction_read_only=on 會話護欄）")
    print(f"planned artifact   : {out_dir}")
    print(f"data format        : {'parquet' if _pyarrow_available() else 'csv.gz'}（pyarrow 不可用 → csv.gz）")
    print("bb episode SQL     :")
    print("  " + BB_EPISODE_SQL)
    print("bb fill SQL        :")
    print("  " + BB_FILL_SQL)
    print("g8 attempt SQL     :")
    print("  " + G8_ATTEMPT_SQL)
    print(f"g8 status          : {G8_STATUS_UNPINNABLE}（last close_maker_attempt {G8_LAST_CLOSE_MAKER_ATTEMPT_UTC}；"
          f"l1_events_min {G8_L1_EVENTS_MIN_UTC} → 0 存活 L1；見 manifest g8_detail）")
    print(f"slice tables       : {', '.join(SLICE_TABLES)}（per window: SELECT * WHERE symbol=%s AND ts∈[lo,hi]）")
    print(f"retention note     : {RETENTION_NOTE}")

    if args.anchors_fixture:
        fx = json.loads(Path(args.anchors_fixture).read_text(encoding="utf-8"))
        bb_signals = dedup_episodes(fx.get("bb_signals", []), gap_s=DEDUP_GAP_S)
        bb_fills = [{**r, "anchor_ts": _as_utc(r["ts"])} for r in fx.get("bb_fills", [])]
        g8 = [{**r, "anchor_ts": _as_utc(r["ts"])} for r in fx.get("g8_attempts", [])]
        bb_windows = build_bb_windows(bb_signals, bb_fills)
        windows = bb_windows + plan_windows(g8, "g8")
        print(f"\n=== fixture 解析：{len(bb_signals)} bb signals + {len(bb_fills)} bb fills "
              f"→ {len(bb_windows)} merged bb windows + {len(g8)} g8 attempts = {len(windows)} windows ===")
        for w in windows:
            prov = ",".join(w.get("provenance", [w["kind"]]))
            print(f"  [{w['kind']}{w['idx']:03d}] {w['symbol']:<12} prov={prov} "
                  f"anchor={w['anchor_ts_utc']} win=[{w['lo_ts_utc']}, {w['hi_ts_utc']}] "
                  f"ms=[{w['lo_ms']}, {w['hi_ms']}]")
    else:
        print("\n（未給 --anchors-fixture：真 episode 解析需 --apply 連 PG。此為計畫預覽。）")
    return 0


def _run_apply(args, since: datetime, until: datetime, out_dir: Path) -> int:
    """--apply：連 PG、解析、匯出 artifact。"""
    conn = connect(args.dsn, statement_timeout_ms=args.statement_timeout)
    try:
        source_head = resolve_source_head(conn)
        bb_signals = resolve_episodes(conn, since, until, gap_s=DEDUP_GAP_S)
        bb_fills = resolve_bb_fill_anchors(conn, since, until)
        g8 = resolve_g8_attempts(conn, since, until) if not args.no_g8 else []
        bb_windows = build_bb_windows(bb_signals, bb_fills)
        windows = bb_windows + plan_windows(g8, "g8")
        print(f"解析：{len(bb_signals)} bb signals + {len(bb_fills)} bb fills "
              f"→ {len(bb_windows)} merged bb windows + {len(g8)} g8 attempts = {len(windows)} windows → {out_dir}")
        manifest = write_artifact(conn, windows, out_dir, source_head)
    finally:
        conn.close()
    print(f"artifact 已釘存：{out_dir}")
    print(f"  n_windows={manifest['n_windows']} "
          f"bb_windows={manifest['n_bb_windows']}"
          f"(sig={manifest['n_bb_signal_anchors']}+fill={manifest['n_bb_fill_anchors']}) "
          f"g8={manifest['n_g8_attempts']}/{manifest['g8_status']} "
          f"total_rows={manifest['total_row_counts']}")
    print(f"  sha256sums: {out_dir / 'sha256sums'}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="bb_reversion R1 replay L1/trades slice-pin exporter（dossier FIX-4 / C2）。")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="（預設）不連 PG，印出解析計畫 / fixture 窗口。")
    mode.add_argument("--apply", action="store_true",
                      help="真跑：連 PG 解析並匯出 immutable artifact。")
    ap.add_argument("--dsn", default=None,
                    help="PG DSN（覆寫 OPENCLAW_DATABASE_URL；否則走 libpq PG* env）。")
    ap.add_argument("--out", default=None, help="artifact 目標目錄（預設 $OPENCLAW_ARTIFACT_ROOT 或 /tmp）。")
    ap.add_argument("--since", default=None, help="signal 查詢起（ISO8601 UTC）。")
    ap.add_argument("--until", default=None, help="signal 查詢迄（ISO8601 UTC）。")
    ap.add_argument("--lookback-days", type=float, default=DEFAULT_LOOKBACK_DAYS,
                    help=f"無 --since 時回看天數（預設 {DEFAULT_LOOKBACK_DAYS}=L1 保留窗）。")
    ap.add_argument("--anchors-fixture", default=None,
                    help="dry-run 用 fixture JSON（bb_signals/bb_fills/g8_attempts）解析窗口，離線驗證。")
    ap.add_argument("--no-g8", action="store_true", help="只釘存 bb episodes，跳過 G8 校準 attempts。")
    ap.add_argument("--statement-timeout", type=int, default=DEFAULT_STATEMENT_TIMEOUT_MS,
                    help=f"PG statement_timeout（ms，預設 {DEFAULT_STATEMENT_TIMEOUT_MS}；會話級唯讀護欄）。")
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    since, until = _resolve_since_until(args)
    out_dir = Path(args.out) if args.out else Path(_default_out())
    # --apply 顯式覆蓋預設 --dry-run（mutually exclusive group 中 --dry-run default=True）
    if args.apply:
        return _run_apply(args, since, until, out_dir)
    return _print_plan(args, since, until, out_dir)


if __name__ == "__main__":
    sys.exit(main())
