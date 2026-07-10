#!/usr/bin/env python3
"""WP-A.4 反事實重跑管線(one-shot research driver)。

MODULE_NOTE
模塊用途:按 QC 預註冊判準(docs/research/2026-07-10--counterfactual_rerun_
  preregistration.md,判準凍結、本檔不得偏離)對兩個母集重跑反事實統計並產出
  verdict artifact:
    母集 A = 71,207 筆「正 edge < threshold」拒單行(trading.risk_verdicts JOIN
      learning.decision_features;凍結 SQL WHERE 逐字 + 計數/join 守恆斷言,
      SELECT 投影改寫記 deviation_log);
    母集 B = 33 個 GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT cells(用凍結
      ledger 輸入 + v3 凍結分類器重新枚舉,枚舉數 ≠ 33 即停)。
  統計面(§2-§6):per-(side_cell, entry_minute, horizon) 去重(代表行 =
  attempt_id 字典序最小、不取平均)、greedy earliest-first 非重疊窗 n_eff、
  E1-E5 eligibility、CR1 cluster-SE by UTC day、BH-FDR(q=0.10,去重後 family)、
  成本雙軌(E[cost] 主判 + CVaR90 尾部並列 + conservative_v1 第三對照欄)、
  regime 標註(§7)、§8 判定式 + §8.4 gate 雙向計價。附 charter 指定的 NEAR
  候選(ma_crossover|NEARUSDT|Buy)按新統計重判(family 外,單列)。
主要函數:main(CLI)、run_rerun(編排)、load_frozen_ledger_rows(凍結 ledger
  視圖重建)、reproduce_population_b(v3 凍結分類器重放)、build_cell_horizon_stats
  (per-(cell,horizon) 統計)、judge_cell(§8.1)、global_verdict(§8.2)。
依賴:cost_gate_learning_lane.{evidence_stats,cost_model,outcome_review,contract}、
  helper_scripts.lib.pg_connect(read-only)、凍結 v3 outcome_review 檔(git
  8dfa1200a 提取,經 --frozen-outcome-review-py 傳入,importlib 載入)。
硬邊界:PG 全程 SELECT-only(set_session readonly);不寫 PG、不呼叫 Bybit、
  不送單、不動 runtime cost gate / 風控 / 授權;唯一寫入面 = 輸出 artifact JSON。
  order_authority=NOT_GRANTED、promotion_evidence=false;結論最大效力 =
  bounded probe 候選榜重排(預註冊 §9)。任何與預註冊不符的計算選擇必須記入
  deviation_log;影響判定式/門檻/family/成本公式的偏離 → 停(exit code 2)。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

RESEARCH_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
for _path in (str(RESEARCH_ROOT), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cost_gate_learning_lane.contract import BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE
from cost_gate_learning_lane.cost_model import (
    FEE_FLOOR_BPS,
    FEE_TAKER_BPS,
    MIN_SYMBOL_FILLS_FOR_QUANTILE,
    SlippageQuantileTable,
    conservative_cost_bps,
    funding_crossing_count,
    load_slippage_quantiles,
)
from cost_gate_learning_lane.evidence_stats import (
    cluster_one_sided_t_p_value,
    bh_fdr_pass,
    one_sided_t_p_value,
    sign_flip_selection_p_value,
)
from cost_gate_learning_lane.outcome_review import _load_expected_slippage

ARTIFACT_SCHEMA_VERSION = "counterfactual_rerun_prereg_v1"
PREREG_DOC_PATH = "docs/research/2026-07-10--counterfactual_rerun_preregistration.md"

# ---- 凍結錨(預註冊 §0.1;重跑第 0 步逐項驗證,偏差 → 停) ----
FROZEN_POPULATION_A_COUNT = 71_207
FROZEN_POPULATION_B_COUNT = 33
FROZEN_REVIEW_SHA256 = (
    "299751f291fdf6bc2f92ad6dc6bcdebe922bf4b382f4526b6a64349575e3249a"
)
FROZEN_REVIEW_GENERATED_AT = "2026-07-09T21:31:15.577558+00:00"
FROZEN_DIAGNOSIS_COUNTS = {
    "BLOCK_CONFIRMED_AFTER_COST": 28,
    "FALSE_NEGATIVE_CANDIDATE_AFTER_COST": 1,
    "GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT": 33,
    "POSITIVE_EDGE_UNSTABLE_AFTER_COST": 1,
    "SAMPLE_INSUFFICIENT": 13,
}
FROZEN_SIDE_CELL_COUNT = 76
FROZEN_BLOCKED_OUTCOME_COUNT = 951_456
LEDGER_RETENTION_DAYS = 14

# 母集 A 凍結 SQL(預註冊 §1.1)。WHERE 子句與預註冊逐字一致;SELECT 投影為
# 實作層改寫(r.ts → epoch-ms 的 ts_ms、省略 r.reason),非逐字 —— 屬 §10.1
# deviation,已記入 _base_deviation_log();母集身分由計數錨 + join 守恆斷言保證。
FROZEN_POPULATION_A_SQL = """
SELECT df.strategy_name, r.symbol, df.side, r.context_id,
       (EXTRACT(EPOCH FROM r.ts) * 1000)::bigint AS ts_ms
FROM trading.risk_verdicts r
JOIN learning.decision_features df ON df.context_id = r.context_id
WHERE r.ts >= '2026-06-15T00:00:00Z' AND r.ts < '2026-07-09T00:00:00Z'
  AND r.verdict = 'Rejected'
  AND r.reason ~ 'cost_gate\\(JS-demo\\): edge=[0-9.]+bps < threshold'
"""
FROZEN_POPULATION_A_COUNT_NO_JOIN_SQL = """
SELECT count(*)
FROM trading.risk_verdicts r
WHERE r.ts >= '2026-06-15T00:00:00Z' AND r.ts < '2026-07-09T00:00:00Z'
  AND r.verdict = 'Rejected'
  AND r.reason ~ 'cost_gate\\(JS-demo\\): edge=[0-9.]+bps < threshold'
"""

# ---- 凍結判準常數(預註冊 §3/§5/§6/§7;不得因結果調整) ----
HORIZON_UNIVERSE = (60, 240)
MIN_N_EFF = 30                     # §3 E1
MIN_DISTINCT_UTC_DAYS = 5          # §3 E2
MAX_TOP_DAY_SHARE_PCT = 50.0       # §3 E3
MAX_CENSORED_PCT = 30.0            # §3 E4(承 F7)
MIN_NET_POSITIVE_PCT = 60.0        # §8 P2(承現行 review 閾值)
FDR_Q = 0.10                       # §5
SIGN_FLIP_B = 1000                 # §5.6
SIGN_FLIP_SEED = 20260704          # §5.6
MAX_ENTRY_DELAY_MS = 5 * 60_000    # censored 語義承 lane 現行(outcome_writer)
REALIZED_CONTRADICTION_GAP_BPS = 50.0  # §6.3(F1 fix(c) 保留)
REALIZED_CONTRADICTION_MIN_N = 10
BULL_HEAVY_SHARE_PCT = 60.0        # §7 bull_heavy
BTC_RET_7D_BULL = 0.05             # §7 bucket 邊界
BTC_RET_7D_BEAR = -0.05
NEAR_CELL_KEY = "ma_crossover|NEARUSDT|Buy"

_SEGMENT_RE = re.compile(r"^probe_ledger\.(\d{8}T\d{6}Z)(?:_(\d+))?\.jsonl$")
_LEDGER_MAIN_NAME = "probe_ledger.jsonl"
# 去重複本一致性容差(§2.3)。
_REPLICA_TOL = 1e-9
# slim 投影欄位:v3 重放 + 本管線統計所需的全部 row 欄(其餘丟棄以控記憶體)。
_SLIM_FIELDS = (
    "record_type", "side_cell_key", "attempt_id", "strategy_name", "symbol",
    "side", "censored", "entry_ts_ms", "exit_ts_ms", "horizon_minutes",
    "gross_bps", "cost_bps", "realized_net_bps", "net_bps_optimistic",
    "cost_model_version", "funding_drag_bps", "generated_at_utc",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _parse_iso_utc(text: str) -> dt.datetime:
    value = text.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _minute_utc_day(entry_minute: int) -> str:
    return (
        dt.datetime.fromtimestamp(entry_minute * 60, tz=dt.timezone.utc)
        .date()
        .isoformat()
    )


class DeviationStop(RuntimeError):
    """影響判定式/母集凍結的偏離(預註冊 §10.2):停,回 PM。"""


# ---------------------------------------------------------------------------
# 凍結 ledger 視圖重建(§0.1/§1.2)
# ---------------------------------------------------------------------------

def load_frozen_ledger_rows(
    snapshot_dir: Path,
    *,
    frozen_generated_at: dt.datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """重建凍結 review 當時的 ledger 讀取視圖(blocked_signal_outcome 行)。

    為什麼不能直接全量讀:凍結 artifact 之後 cron 持續 append 主檔;凍結視圖 =
    「輪轉段檔(段 ts ∈ [frozen−14d, frozen])全量行」+「主檔/更晚段檔中
    generated_at_utc ≤ frozen 的行」。段檔 rename 不改行歸屬,故此重建對
    blocked_signal_outcome 行是精確的(outcome 行只由 cron review 前的 refresh
    階段寫入,凍結時刻與下一次 cron 之間無 outcome 寫入)。
    回傳 (manifest, slim_rows);manifest 含逐檔 sha256(§0.1 錨要求)。
    """
    cutoff = frozen_generated_at - dt.timedelta(days=LEDGER_RETENTION_DAYS)
    manifest: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    files = sorted(snapshot_dir.glob("probe_ledger*.jsonl"))
    if not files:
        raise DeviationStop(f"no probe_ledger files under {snapshot_dir}")
    for path in files:
        name = path.name
        matched = _SEGMENT_RE.match(name)
        if matched is not None:
            seg_ts = dt.datetime.strptime(matched.group(1), "%Y%m%dT%H%M%SZ").replace(
                tzinfo=dt.timezone.utc
            )
            if seg_ts < cutoff:
                membership = "excluded_before_retention_cutoff"
            elif seg_ts <= frozen_generated_at:
                membership = "full"
            else:
                membership = "generated_at_filtered"
        elif name == _LEDGER_MAIN_NAME:
            membership = "generated_at_filtered"
        else:
            membership = "excluded_unrecognized_name"
        manifest.append(
            {
                "name": name,
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
                "frozen_view_membership": membership,
            }
        )
        if membership not in ("full", "generated_at_filtered"):
            continue
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped or '"blocked_signal_outcome"' not in stripped:
                    # 快速預過濾:非 outcome 行不進 json.loads(記憶體/CPU 邊界)。
                    continue
                row = json.loads(stripped)
                if row.get("record_type") != BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE:
                    continue
                if membership == "generated_at_filtered":
                    gen = row.get("generated_at_utc")
                    if not gen or _parse_iso_utc(str(gen)) > frozen_generated_at:
                        continue
                rows.append({key: row.get(key) for key in _SLIM_FIELDS})
    return manifest, rows


# ---------------------------------------------------------------------------
# 母集 B 重枚舉(§1.2):v3 凍結分類器重放
# ---------------------------------------------------------------------------

def reproduce_population_b(
    frozen_module_path: Path,
    ledger_rows: list[dict[str, Any]],
    *,
    frozen_generated_at: dt.datetime,
) -> dict[str, Any]:
    """用 git 提取的 v3 outcome_review(產出凍結 artifact 的同一分類器)重放。

    為什麼重放而非解析凍結 JSON:凍結 artifact 只保留 top 16 cells,完整 33-cell
    清單必須用「同分類規則 + 同輸入」重新枚舉(§1.2);diagnosis_counts /
    side_cell_count / outcome_count 與凍結錨逐項比對 = 重建保真度的機械證明。
    sign_flip_b=1(非 1000):headline sign-flip 不參與 cell 分類,降 B 僅省時,
    不影響枚舉(記入 deviation_log 實作層項)。
    """
    spec = importlib.util.spec_from_file_location(
        "outcome_review_v3_frozen", frozen_module_path
    )
    if spec is None or spec.loader is None:
        raise DeviationStop(f"cannot load frozen v3 module at {frozen_module_path}")
    module = importlib.util.module_from_spec(spec)
    # dataclass 裝飾器解析欄位型別時查 sys.modules[cls.__module__];未註冊會
    # AttributeError,故 exec 前必須登記(標準 importlib 動態載入慣例)。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    cfg = module.BlockedOutcomeReviewConfig(
        min_outcomes_per_side_cell=3,
        min_avg_net_bps=0.0,
        min_net_positive_pct=60.0,
        fdr_q=0.10,
        sign_flip_b=1,
    )
    review = module.build_blocked_signal_outcome_review(
        ledger_rows, now_utc=frozen_generated_at, cfg=cfg
    )
    observed_counts = dict(review.get("diagnosis_counts") or {})
    observed_cells = int(review.get("side_cell_count") or 0)
    observed_outcomes = int(review.get("blocked_signal_outcome_count") or 0)
    anchor_match = (
        observed_counts == FROZEN_DIAGNOSIS_COUNTS
        and observed_cells == FROZEN_SIDE_CELL_COUNT
        and observed_outcomes == FROZEN_BLOCKED_OUTCOME_COUNT
    )
    gross_cells: list[str] = []
    near_diagnosis = None
    # v3 review 只在 top_side_cells 保留 16 行;完整逐 cell 診斷需按 v3 同語義
    # 重算 —— 直接調 v3 的 _review_side_cell_rows 全量取回(同模組同 cfg)。
    grouped: dict[str, list[dict[str, Any]]] = {}
    censored: dict[str, int] = {}
    for row in ledger_rows:
        key = str(row.get("side_cell_key") or "").strip()
        if not key:
            continue
        if row.get("censored") is True:
            censored[key] = censored.get(key, 0) + 1
            grouped.setdefault(key, [])
            continue
        if _float(row.get("realized_net_bps")) is None:
            continue
        grouped.setdefault(key, []).append(row)
    per_cell_diagnosis: dict[str, str] = {}
    for key, cell_rows in sorted(grouped.items()):
        cell = module._review_side_cell_rows(
            key, cell_rows, cfg=cfg, censored_count=censored.get(key, 0)
        )
        per_cell_diagnosis[key] = str(cell.get("learning_diagnosis") or "")
        if (
            per_cell_diagnosis[key]
            == "GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT"
        ):
            gross_cells.append(key)
    near_diagnosis = per_cell_diagnosis.get(NEAR_CELL_KEY)
    return {
        "anchor_match": anchor_match,
        "observed_side_cell_count": observed_cells,
        "observed_diagnosis_counts": observed_counts,
        "observed_blocked_outcome_count": observed_outcomes,
        "gross_edge_positive_cells": sorted(gross_cells),
        "near_cell_v3_diagnosis": near_diagnosis,
    }


# ---------------------------------------------------------------------------
# PG fetch(全程 SELECT-only)
# ---------------------------------------------------------------------------

def _connect_readonly_pg(*, statement_timeout_ms: int) -> Any:
    from helper_scripts.lib.pg_connect import connect_report_pg

    conn = connect_report_pg(
        "counterfactual_rerun_prereg_v1",
        statement_timeout_ms_default=statement_timeout_ms,
    )
    conn.rollback()
    # 為什麼 session readonly:預註冊 §9 邊界「PG read-only」的機械保證,
    # 任何誤寫在 session 層直接被 PG 拒絕。
    conn.set_session(readonly=True, autocommit=True)
    return conn


def fetch_population_a(conn: Any) -> list[dict[str, Any]]:
    """凍結 SQL(WHERE 逐字;SELECT 投影改寫已記 deviation_log)+ §1.1 計數/join
    守恆斷言(偏差 → 停)。"""
    cur = conn.cursor()
    try:
        cur.execute(FROZEN_POPULATION_A_COUNT_NO_JOIN_SQL)
        no_join = int(cur.fetchone()[0])
        cur.execute(FROZEN_POPULATION_A_SQL)
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, record)) for record in cur.fetchall()]
    finally:
        cur.close()
    if len(rows) != FROZEN_POPULATION_A_COUNT:
        raise DeviationStop(
            f"population A count {len(rows)} != frozen {FROZEN_POPULATION_A_COUNT}"
        )
    if no_join != len(rows):
        raise DeviationStop(
            f"join conservation broken: no-join {no_join} != joined {len(rows)}"
        )
    return rows


def fetch_minute_bars(
    conn: Any, symbols: list[str], *, start_ms: int, end_ms: int
) -> dict[str, dict[int, float]]:
    """1m klines open 價(bar 開盤時刻 → open;§2.1 kline_backfill 的價格源)。"""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT symbol, open_ts_ms, open::float8
            FROM market.klines
            WHERE timeframe = '1m' AND symbol = ANY(%(symbols)s)
              AND open_ts_ms >= %(start_ms)s AND open_ts_ms <= %(end_ms)s
            """,
            {"symbols": symbols, "start_ms": start_ms, "end_ms": end_ms},
        )
        out: dict[str, dict[int, float]] = {symbol: {} for symbol in symbols}
        for symbol, open_ts_ms, open_price in cur.fetchall():
            if open_price is not None and open_price > 0.0:
                out[str(symbol)][int(open_ts_ms) // 60_000] = float(open_price)
        return out
    finally:
        cur.close()


def fetch_daily_closes(conn: Any, symbols: list[str]) -> dict[str, dict[str, float]]:
    """1d klines close(UTC 日 → close;§7 regime 指標的唯一資料源,D−1 取值)。"""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT symbol, to_char(to_timestamp(open_ts_ms / 1000) AT TIME ZONE 'UTC',
                                   'YYYY-MM-DD') AS day, close::float8
            FROM market.klines
            WHERE timeframe = '1d' AND symbol = ANY(%(symbols)s)
            ORDER BY symbol, open_ts_ms
            """,
            {"symbols": symbols},
        )
        out: dict[str, dict[str, float]] = {}
        for symbol, day, close in cur.fetchall():
            if close is not None and close > 0.0:
                out.setdefault(str(symbol), {})[str(day)] = float(close)
        return out
    finally:
        cur.close()


def fetch_funding_intervals(conn: Any, symbols: list[str]) -> dict[str, float]:
    """per-symbol funding interval(小時),由 funding_ts 間距眾數導出(§6.1)。

    為什麼從歷史導出:research.alpha_funding_rates_history 的
    funding_interval_minutes 欄實測為 NULL,而結算間距本身就是 interval 的
    直接觀測。表中缺席的 symbol 由 caller 落 8h fallback 並記 deviation_log。
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            WITH d AS (
              SELECT symbol,
                     EXTRACT(EPOCH FROM funding_ts
                             - lag(funding_ts) OVER (PARTITION BY symbol
                                                     ORDER BY funding_ts)) AS gap_s
              FROM (SELECT DISTINCT symbol, funding_ts
                    FROM research.alpha_funding_rates_history
                    WHERE symbol = ANY(%(symbols)s)) t)
            SELECT symbol, mode() WITHIN GROUP (ORDER BY gap_s)
            FROM d WHERE gap_s IS NOT NULL AND gap_s > 0 GROUP BY symbol
            """,
            {"symbols": symbols},
        )
        return {
            str(symbol): float(gap_s) / 3600.0
            for symbol, gap_s in cur.fetchall()
            if gap_s
        }
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# 觀測構建(§2.1):ledger 優先 + kline 補算
# ---------------------------------------------------------------------------

def backfill_markout(
    bars: dict[int, float],
    *,
    ts_ms: int,
    horizon_minutes: int,
    side_sign: float,
) -> dict[str, Any]:
    """單筆拒單的 leak-free markout 補算(§2.1)。

    entry = 拒單 ts 後首根 1m bar open(嚴格 > ts;bar open 對齊分鐘邊界,故
    候選分鐘 = floor(ts/60_000)+1);exit = entry + horizon 後首根 bar open。
    觀測斷供沿 lane censored 語義:entry 延遲 > 5min 或 exit 延遲 >
    max(5min, min(25%×h, 30min)) → censored(計分母不入檢定)。
    """
    entry_candidate = ts_ms // 60_000 + 1
    max_entry_minutes = MAX_ENTRY_DELAY_MS // 60_000
    entry_minute = None
    for minute in range(entry_candidate, entry_candidate + max_entry_minutes + 1):
        if minute in bars:
            if minute * 60_000 - ts_ms > MAX_ENTRY_DELAY_MS:
                break
            entry_minute = minute
            break
    if entry_minute is None:
        return {"censored": True, "censor_reason": "entry_observation_gap"}
    horizon_ms = horizon_minutes * 60_000
    max_exit_delay_ms = int(max(5 * 60_000, min(0.25 * horizon_ms, 30 * 60_000)))
    exit_target = entry_minute + horizon_minutes
    exit_minute = None
    for minute in range(exit_target, exit_target + max_exit_delay_ms // 60_000 + 1):
        if minute in bars:
            exit_minute = minute
            break
    if exit_minute is None:
        return {"censored": True, "censor_reason": "exit_observation_gap"}
    entry_price = bars[entry_minute]
    exit_price = bars[exit_minute]
    gross_bps = side_sign * (exit_price - entry_price) / entry_price * 10_000.0
    return {
        "censored": False,
        "entry_minute": entry_minute,
        "gross_bps": gross_bps,
    }


def greedy_non_overlap(
    entries: list[dict[str, Any]], *, horizon_minutes: int
) -> tuple[list[dict[str, Any]], int]:
    """§2.6 非重疊窗子樣本:entry_minute 升序 greedy earliest-first(確定性)。"""
    selected: list[dict[str, Any]] = []
    blocked_until: int | None = None
    for entry in sorted(entries, key=lambda item: item["entry_minute"]):
        if blocked_until is not None and entry["entry_minute"] < blocked_until:
            continue
        selected.append(entry)
        blocked_until = entry["entry_minute"] + max(horizon_minutes, 1)
    return selected, len(entries) - len(selected)


def _expected_and_tail_cost(
    symbol: str,
    *,
    entry_ts_ms: int,
    horizon_minutes: int,
    expected_slippage: dict[str, Any],
    funding_interval_hours: float,
    funding_drag_override: float | None,
) -> tuple[float, float | None, str | None, float]:
    """§6.1/§6.2 成本雙軌(單觀測)。回傳 (cost_E, cost_tail, tail_metric, drag)。

    funding_drag_override:ledger 行沿用其記錄的 funding_drag_bps(承 v5 review
    語義);backfill 行以 per-symbol interval 現算 crossings × 1.0bps。
    """
    per_symbol = expected_slippage["per_symbol"].get(symbol.upper())
    if per_symbol is not None and per_symbol["n"] >= MIN_SYMBOL_FILLS_FOR_QUANTILE:
        slip = per_symbol["mean_abs"]
        tail_slip = per_symbol["tail_bps"]
        tail_metric = per_symbol["tail_metric"]
    else:
        slip = expected_slippage["global_mean_abs"]
        tail_slip = expected_slippage["global_tail_bps"]
        tail_metric = expected_slippage["global_tail_metric"]
    if tail_slip is None:
        tail_slip = expected_slippage["global_tail_bps"]
        tail_metric = expected_slippage["global_tail_metric"]
    if funding_drag_override is not None:
        drag = max(0.0, funding_drag_override)
    else:
        drag = float(
            funding_crossing_count(
                event_ts_ms=entry_ts_ms,
                horizon_minutes=horizon_minutes,
                funding_interval_hours=funding_interval_hours,
            )
        )
    cost_expected = max(2.0 * (FEE_TAKER_BPS + slip) + drag, FEE_FLOOR_BPS)
    cost_tail = (
        max(2.0 * (FEE_TAKER_BPS + tail_slip) + drag, FEE_FLOOR_BPS)
        if tail_slip is not None
        else None
    )
    return cost_expected, cost_tail, tail_metric, drag


def build_observations_for_cell(
    *,
    cell_key: str,
    horizon_minutes: int,
    ledger_rows: list[dict[str, Any]],
    pg_rejections: list[dict[str, Any]],
    bars: dict[int, float] | None,
) -> dict[str, Any]:
    """組裝單 (cell, horizon) 的觀測集(§2.1/§2.2/§2.3)。

    - ledger 行按 (entry_minute) 分組;代表行 = attempt_id 字典序最小,不取平均;
      複本 realized_net/gross 不一致(容差 1e-9)→ replica_inconsistent。
    - pg 拒單行:同鍵已有 ledger 觀測 → 取 ledger(§2.1「兩源同鍵取 ledger」);
      無覆蓋 → kline 補算(bars 缺失 → censored)。
    - E5 前置:gross_bps 缺失的 ledger 行無法按 §6 雙軌重算 → 剔除並計數。
    """
    groups: dict[int, list[dict[str, Any]]] = {}
    censored_row_count = 0
    dropped_not_recomputable = 0
    ledger_raw_count = 0
    for row in ledger_rows:
        if int(row.get("horizon_minutes") or 0) != horizon_minutes:
            continue
        if row.get("censored") is True:
            censored_row_count += 1
            continue
        ledger_raw_count += 1
        entry_ts = row.get("entry_ts_ms")
        try:
            entry_minute = int(entry_ts) // 60_000
        except (TypeError, ValueError):
            dropped_not_recomputable += 1
            continue
        groups.setdefault(entry_minute, []).append(row)

    observations: dict[int, dict[str, Any]] = {}
    replica_inconsistent = 0
    for entry_minute in sorted(groups):
        members = groups[entry_minute]
        representative = min(members, key=lambda row: str(row.get("attempt_id") or ""))
        for field in ("realized_net_bps", "gross_bps"):
            values = [_float(row.get(field)) for row in members]
            present = [v for v in values if v is not None]
            if present and (
                len(present) != len(values)
                or (max(present) - min(present)) > _REPLICA_TOL
            ):
                replica_inconsistent += 1
                break
        gross = _float(representative.get("gross_bps"))
        if gross is None:
            # E5:成本欄不可重算(無 gross)→ 剔除;剔除後仍需過 E1-E4。
            dropped_not_recomputable += len(members)
            continue
        observations[entry_minute] = {
            "entry_minute": entry_minute,
            "gross_bps": gross,
            "obs_source": "ledger",
            "funding_drag_bps": _float(representative.get("funding_drag_bps")),
            "net_conservative_recorded": _float(
                representative.get("realized_net_bps")
            ),
            "raw_member_count": len(members),
        }

    pg_raw_count = len(pg_rejections)
    ledger_keys = set(observations)
    backfill_censored: dict[int, str] = {}
    pg_rows_covered_by_ledger = 0
    pg_rows_duplicate_observation = 0
    pg_rows_backfilled = 0
    pg_rows_censored = 0
    for rejection in pg_rejections:
        ts_ms = int(rejection["ts_ms"])
        candidate_minute = ts_ms // 60_000 + 1
        if candidate_minute in observations:
            # 歸因拆分:同鍵已有觀測 —— 來自 ledger(§2.1 ledger 優先)或來自
            # 更早的同分鐘 pg 拒單(秒級重發的複本,dedup 正常收縮)。
            if candidate_minute in ledger_keys:
                pg_rows_covered_by_ledger += 1
            else:
                pg_rows_duplicate_observation += 1
            continue
        if candidate_minute in backfill_censored:
            pg_rows_censored += 1
            continue
        if bars is None:
            backfill_censored[candidate_minute] = "no_kline_source"
            pg_rows_censored += 1
            continue
        result = backfill_markout(
            bars,
            ts_ms=ts_ms,
            horizon_minutes=horizon_minutes,
            side_sign=-1.0 if cell_key.endswith("|Sell") else 1.0,
        )
        if result["censored"]:
            backfill_censored[candidate_minute] = result["censor_reason"]
            pg_rows_censored += 1
            continue
        entry_minute = result["entry_minute"]
        if entry_minute in observations:
            # bar 缺口使補算 entry 落到既有觀測分鐘 → 視為同觀測(dedup 收縮)。
            if entry_minute in ledger_keys:
                pg_rows_covered_by_ledger += 1
            else:
                pg_rows_duplicate_observation += 1
            continue
        observations[entry_minute] = {
            "entry_minute": entry_minute,
            "gross_bps": result["gross_bps"],
            "obs_source": "kline_backfill",
            "funding_drag_bps": None,
            "net_conservative_recorded": None,
            "raw_member_count": 1,
        }
        pg_rows_backfilled += 1

    return {
        "observations": list(observations.values()),
        "ledger_raw_row_count": ledger_raw_count,
        "ledger_censored_row_count": censored_row_count,
        "pg_rejection_row_count": pg_raw_count,
        "pg_rows_covered_by_ledger": pg_rows_covered_by_ledger,
        "pg_rows_duplicate_observation": pg_rows_duplicate_observation,
        "pg_rows_backfilled": pg_rows_backfilled,
        "pg_rows_censored": pg_rows_censored,
        "backfill_censored_key_count": len(backfill_censored),
        "replica_inconsistent_group_count": replica_inconsistent,
        "dropped_not_recomputable_row_count": dropped_not_recomputable,
    }


# ---------------------------------------------------------------------------
# Regime 標註(§7)
# ---------------------------------------------------------------------------

def build_regime_labels(
    selected_days: list[str],
    *,
    btc_closes: dict[str, float],
    symbol_closes: dict[str, float] | None,
) -> dict[str, Any]:
    """per-cell regime 標註(§7)。全指標用 entry 日 D 的 D−1 日終資料。

    黑名單模型(HMM/GARCH 等)禁用 —— 全部指標為可解釋的 SMA/報酬/實現波動
    分位(唯一正本 math-model-audit);資料缺失 → unknown bucket(不猜)。
    """
    btc_days = sorted(btc_closes)
    sym_days = sorted(symbol_closes) if symbol_closes else []

    def _closes_before(closes_days: list[str], day: str, count: int) -> list[str]:
        eligible = [d for d in closes_days if d < day]
        return eligible[-count:]

    trend_counts = {"up": 0, "down": 0, "unknown": 0}
    ret7_counts = {"bear": 0, "flat": 0, "bull": 0, "unknown": 0}
    vol_counts = {"low": 0, "mid": 0, "high": 0, "unknown": 0}
    for day in selected_days:
        window30 = _closes_before(btc_days, day, 30)
        if len(window30) >= 30:
            closes30 = [btc_closes[d] for d in window30]
            trend_counts["up" if closes30[-1] > _mean(closes30) else "down"] += 1
        else:
            trend_counts["unknown"] += 1
        window8 = _closes_before(btc_days, day, 8)
        if len(window8) >= 8:
            ret7 = btc_closes[window8[-1]] / btc_closes[window8[0]] - 1.0
            if ret7 >= BTC_RET_7D_BULL:
                ret7_counts["bull"] += 1
            elif ret7 <= BTC_RET_7D_BEAR:
                ret7_counts["bear"] += 1
            else:
                ret7_counts["flat"] += 1
        else:
            ret7_counts["unknown"] += 1
        vol_bucket = "unknown"
        if symbol_closes:
            history = _closes_before(sym_days, day, 800)
            if len(history) >= 90:
                log_returns = [
                    math.log(symbol_closes[history[i]] / symbol_closes[history[i - 1]])
                    for i in range(1, len(history))
                ]
                window_vols = []
                for end in range(30, len(log_returns) + 1):
                    window = log_returns[end - 30 : end]
                    mu = sum(window) / 30
                    window_vols.append(
                        math.sqrt(sum((r - mu) ** 2 for r in window) / 29)
                    )
                current = window_vols[-1]
                rank = sum(1 for v in window_vols if v <= current) / len(window_vols)
                vol_bucket = "low" if rank < 1 / 3 else ("high" if rank > 2 / 3 else "mid")
        vol_counts[vol_bucket] += 1

    n = len(selected_days) or 1
    distinct_days = len(set(selected_days))
    day_counts: dict[str, int] = {}
    for day in selected_days:
        day_counts[day] = day_counts.get(day, 0) + 1
    top_share = max(day_counts.values()) / n * 100.0 if day_counts else None
    known_trend = trend_counts["up"] + trend_counts["down"]
    single_direction_trend = known_trend > 0 and (
        trend_counts["up"] == known_trend or trend_counts["down"] == known_trend
    )
    single_regime_episode = bool(
        distinct_days < MIN_DISTINCT_UTC_DAYS
        or (top_share is not None and top_share > MAX_TOP_DAY_SHARE_PCT)
        or (single_direction_trend and distinct_days <= 2)
    )
    bull_heavy = bool(
        selected_days
        and ret7_counts["bull"] / n * 100.0 > BULL_HEAVY_SHARE_PCT
    )
    return {
        "btc_trend_30d_counts": trend_counts,
        "btc_ret_7d_counts": ret7_counts,
        "sym_vol_30d_counts": vol_counts,
        "single_regime_episode": single_regime_episode,
        "bull_heavy": bull_heavy,
        "indicator_note": (
            "全指標 D−1 日終(1d klines);btc_trend_30d=sign(close−SMA30);"
            "btc_ret_7d 7 日收盤報酬;sym_vol_30d=30d 實現波動在自身 2yr 滾動"
            "歷史的分位;缺資料 → unknown,不猜"
        ),
    }


# ---------------------------------------------------------------------------
# per-(cell,horizon) 統計 + §8 判定
# ---------------------------------------------------------------------------

def build_cell_horizon_stats(
    *,
    cell_key: str,
    horizon_minutes: int,
    membership: list[str],
    obs_bundle: dict[str, Any],
    expected_slippage: dict[str, Any],
    funding_interval_hours: float,
    conservative_table: SlippageQuantileTable | None,
    btc_closes: dict[str, float],
    symbol_closes: dict[str, float] | None,
    edge_estimate: dict[str, Any] | None,
    now_utc: dt.datetime,
) -> dict[str, Any]:
    """單 (cell, horizon) 的全欄統計(§2-§7;§8 判定欄由 family 步驟補齊)。"""
    symbol = cell_key.split("|")[1] if cell_key.count("|") >= 2 else ""
    dedup_entries = obs_bundle["observations"]
    for entry in dedup_entries:
        cost_e, cost_tail, tail_metric, drag = _expected_and_tail_cost(
            symbol,
            entry_ts_ms=entry["entry_minute"] * 60_000,
            horizon_minutes=horizon_minutes,
            expected_slippage=expected_slippage,
            funding_interval_hours=funding_interval_hours,
            funding_drag_override=entry["funding_drag_bps"],
        )
        entry["net_expected"] = entry["gross_bps"] - cost_e
        entry["expected_cost_bps"] = cost_e
        entry["net_tail"] = (
            entry["gross_bps"] - cost_tail if cost_tail is not None else None
        )
        entry["tail_cost_bps"] = cost_tail
        entry["tail_metric"] = tail_metric
        if entry["net_conservative_recorded"] is not None:
            entry["net_conservative"] = entry["net_conservative_recorded"]
        else:
            cons = conservative_cost_bps(
                symbol=symbol,
                horizon_minutes=horizon_minutes,
                table=conservative_table,
                now=now_utc,
                funding_crossings=funding_crossing_count(
                    event_ts_ms=entry["entry_minute"] * 60_000,
                    horizon_minutes=horizon_minutes,
                    funding_interval_hours=funding_interval_hours,
                ),
            )
            entry["net_conservative"] = entry["gross_bps"] - cons["cost_bps"]

    selected, overlap_excluded = greedy_non_overlap(
        dedup_entries, horizon_minutes=horizon_minutes
    )
    selected_days = [_minute_utc_day(entry["entry_minute"]) for entry in selected]
    day_counts: dict[str, int] = {}
    for day in selected_days:
        day_counts[day] = day_counts.get(day, 0) + 1
    n_eff = len(selected)
    distinct_days = len(day_counts)
    top_day = None
    top_day_share = None
    if day_counts:
        top_day, top_count = sorted(
            day_counts.items(), key=lambda item: (-item[1], item[0])
        )[0]
        top_day_share = top_count / n_eff * 100.0

    valid_row_count = (
        obs_bundle["ledger_raw_row_count"]
        - obs_bundle["dropped_not_recomputable_row_count"]
        + obs_bundle["pg_rows_backfilled"]
    )
    censored_count = (
        obs_bundle["ledger_censored_row_count"] + obs_bundle["pg_rows_censored"]
    )
    denominator = valid_row_count + censored_count
    censored_pct = censored_count / denominator * 100.0 if denominator else 0.0

    nets_main = [entry["net_expected"] for entry in selected]
    clusters = selected_days
    mean_net = _mean(nets_main)
    std_net = None
    if n_eff >= 2 and mean_net is not None:
        std_net = math.sqrt(
            sum((v - mean_net) ** 2 for v in nets_main) / (n_eff - 1)
        )
    zero_variance_suspect = bool(n_eff >= 2 and std_net is not None and std_net == 0.0)
    replica_suspect = obs_bundle["replica_inconsistent_group_count"] > 0
    cluster_result = (
        cluster_one_sided_t_p_value(nets_main, clusters)
        if n_eff >= 2 and not replica_suspect and not zero_variance_suspect
        else {"p": None, "t": None, "g": distinct_days, "n": n_eff, "df": None,
              "degenerate_reason": "not_computed"}
    )
    # 預註冊 §4 的 V=0 正本定義是 CR1 cluster 變異數:cluster sums 相消時
    # (如兩日各 {+1,−1})個體 std>0 而 V=0,std==0 只是其真子集。必須先算
    # cluster_result 再把 zero_cluster_variance 併入 data_integrity_suspect,
    # 否則此類 cell 以 eligible-with-p-None 進 judge → 排出 family 後被判
    # BLOCK_CONFIRMED(方向性統計結論),違 §4「V=0 不給 p、標 DATA_INTEGRITY」。
    cluster_zero_variance = bool(
        cluster_result.get("degenerate_reason") == "zero_cluster_variance"
    )
    data_integrity_suspect = bool(
        replica_suspect or zero_variance_suspect or cluster_zero_variance
    )

    # 敏感性欄(§2.7):全 n_dedup 樣本 + day-cluster,僅列報不判定。
    dedup_nets = [entry["net_expected"] for entry in dedup_entries]
    dedup_days = [_minute_utc_day(entry["entry_minute"]) for entry in dedup_entries]
    sensitivity_cluster = (
        cluster_one_sided_t_p_value(dedup_nets, dedup_days)
        if len(dedup_nets) >= 2
        else {"p": None, "t": None}
    )
    # 對照欄(§4):IID t(作廢,僅透明保留)。
    p_iid = (
        one_sided_t_p_value(mean_net or 0.0, std_net, n_eff)
        if std_net is not None
        else None
    )

    eligibility_failures: list[str] = []
    if n_eff < MIN_N_EFF:
        eligibility_failures.append("E1_n_eff_below_30")
    if distinct_days < MIN_DISTINCT_UTC_DAYS:
        eligibility_failures.append("E2_distinct_utc_days_below_5")
    if top_day_share is not None and top_day_share > MAX_TOP_DAY_SHARE_PCT:
        eligibility_failures.append("E3_top_day_share_above_50pct")
    if censored_pct > MAX_CENSORED_PCT:
        eligibility_failures.append("E4_censored_pct_above_30")
    if obs_bundle["dropped_not_recomputable_row_count"] > 0 and n_eff < MIN_N_EFF:
        # E5 條件式:剔除不可重算行後仍須過 E1-E4;E1-E4 已在剔除後樣本上計,
        # 此處僅為透明再標(不另立新門檻)。
        eligibility_failures.append("E5_after_drop_still_below_floor")
    eligible = not eligibility_failures and not data_integrity_suspect

    tail_nets = [entry["net_tail"] for entry in selected if entry["net_tail"] is not None]
    cons_nets = [
        entry["net_conservative"]
        for entry in selected
        if entry["net_conservative"] is not None
    ]
    net_positive_pct = (
        sum(1 for v in nets_main if v > 0.0) / n_eff * 100.0 if n_eff else None
    )
    cons_positive_pct = (
        sum(1 for v in cons_nets if v > 0.0) / len(cons_nets) * 100.0
        if cons_nets
        else None
    )
    mean_net_conservative = _mean(cons_nets)
    p1_main = bool(mean_net is not None and mean_net > 0.0)
    p2_main = bool(net_positive_pct is not None and net_positive_pct >= MIN_NET_POSITIVE_PCT)
    p1p2_conservative = bool(
        mean_net_conservative is not None
        and mean_net_conservative > 0.0
        and cons_positive_pct is not None
        and cons_positive_pct >= MIN_NET_POSITIVE_PCT
    )
    candidacy_flipped_by_cost_model = bool((p1_main and p2_main) != p1p2_conservative)

    realized_ev = None
    realized_n = 0
    if edge_estimate:
        realized_ev = _float(edge_estimate.get("raw_bps"))
        try:
            realized_n = int(edge_estimate.get("n") or 0)
        except (TypeError, ValueError):
            realized_n = 0
    gap = (
        mean_net - realized_ev
        if (mean_net is not None and realized_ev is not None)
        else None
    )
    execution_realism_suspect = bool(
        realized_n >= REALIZED_CONTRADICTION_MIN_N
        and realized_ev is not None
        and realized_ev < 0.0
        and gap is not None
        and gap > REALIZED_CONTRADICTION_GAP_BPS
    )

    regime = build_regime_labels(
        selected_days, btc_closes=btc_closes, symbol_closes=symbol_closes
    )

    obs_source_counts = {"ledger": 0, "kline_backfill": 0}
    for entry in selected:
        obs_source_counts[entry["obs_source"]] += 1

    return {
        "side_cell_key": cell_key,
        "horizon_minutes": horizon_minutes,
        "population_membership": membership,
        "symbol": symbol,
        "n_raw_ledger_rows": obs_bundle["ledger_raw_row_count"],
        "n_pg_rejection_rows": obs_bundle["pg_rejection_row_count"],
        "pg_rows_covered_by_ledger": obs_bundle["pg_rows_covered_by_ledger"],
        "pg_rows_duplicate_observation": obs_bundle["pg_rows_duplicate_observation"],
        "pg_rows_backfilled": obs_bundle["pg_rows_backfilled"],
        "n_dedup": len(dedup_entries),
        "n_eff": n_eff,
        "window_overlap_excluded_entry_count": overlap_excluded,
        "replica_inconsistent_group_count": (
            obs_bundle["replica_inconsistent_group_count"]
        ),
        "dropped_not_recomputable_row_count": (
            obs_bundle["dropped_not_recomputable_row_count"]
        ),
        "distinct_entry_utc_days": distinct_days,
        "entry_day_counts": {day: day_counts[day] for day in sorted(day_counts)},
        "top_entry_utc_day": top_day,
        "top_entry_day_share_pct": top_day_share,
        "censored_count": censored_count,
        "censored_pct": censored_pct,
        "obs_source_counts": obs_source_counts,
        "sample_eligibility_failures": eligibility_failures,
        "data_integrity_suspect": data_integrity_suspect,
        "zero_variance_suspect": zero_variance_suspect,
        "eligible": eligible,
        "mean_net_E": mean_net,
        "std_net_E": std_net,
        "net_E_positive_pct": net_positive_pct,
        "avg_expected_cost_bps": _mean(
            [entry["expected_cost_bps"] for entry in selected]
        ),
        "cluster_t": cluster_result.get("t"),
        "cluster_df": cluster_result.get("df"),
        "p_cluster_one_sided": cluster_result.get("p"),
        "cluster_degenerate_reason": cluster_result.get("degenerate_reason"),
        "p_iid_raw_deprecated": p_iid,
        "sensitivity_full_dedup": {
            "n_dedup": len(dedup_nets),
            "mean_net_E": _mean(dedup_nets),
            "p_cluster_one_sided": sensitivity_cluster.get("p"),
        },
        "mean_net_tail": _mean(tail_nets),
        "net_tail_positive_pct": (
            sum(1 for v in tail_nets if v > 0.0) / len(tail_nets) * 100.0
            if tail_nets
            else None
        ),
        "avg_tail_cost_bps": _mean(
            [e["tail_cost_bps"] for e in selected if e["tail_cost_bps"] is not None]
        ),
        "tail_metric": next(
            (entry["tail_metric"] for entry in selected if entry.get("tail_metric")),
            None,
        ),
        "mean_net_conservative_v1": mean_net_conservative,
        "net_conservative_positive_pct": cons_positive_pct,
        "candidacy_flipped_by_cost_model": candidacy_flipped_by_cost_model,
        "realized_cell_ev_bps": realized_ev,
        "realized_cell_n": realized_n,
        "counterfactual_vs_realized_gap_bps": gap,
        "execution_realism_suspect": execution_realism_suspect,
        "regime": regime,
        "p1_mean_net_E_positive": p1_main,
        "p2_net_E_positive_pct_ge_60": p2_main,
        # P3(BH)由 family 步驟寫回;P4/P5 此處即定。
        "p4_no_suspect": bool(not execution_realism_suspect and not data_integrity_suspect),
        "p5_not_single_regime_episode": not regime["single_regime_episode"],
        "bh_in_family": False,
        "bh_fdr_pass": None,
        "verdict": None,
        # headline sign-flip(§5.6)的樣本暫存(family 步驟取用後即從輸出移除)。
        "_selected_nets": list(nets_main),
        "flip_condition": (
            "新的去重樣本使 (n_eff, G, top-day) 重過 E1-E3 且 P1-P5 全過 → "
            "自動恢復候選資格(預註冊 §8.3)"
        ),
    }


def judge_cell(cell: dict[str, Any]) -> str:
    """§8.1 判定式(機械可裁,不得摻入敘事)。

    §2.3 前置:複本不一致 / V=0 的 cell 排除出檢定 family,統計結論(含
    BLOCK_CONFIRMED)一律不給 —— 與 v5 lane review 同語義,必須與「樣本不足」
    分開標示(這類 cell 可能 E1-E5 全過,混標會掩蓋資料完整性問題)。
    """
    if cell["data_integrity_suspect"]:
        return "DATA_INTEGRITY_SUSPECT_EXCLUDED"
    if not cell["eligible"]:
        return "SAMPLE_INSUFFICIENT_AFTER_DEDUP"
    p3 = bool(cell["bh_fdr_pass"])
    promote = (
        cell["p1_mean_net_E_positive"]
        and cell["p2_net_E_positive_pct_ge_60"]
        and p3
        and cell["p4_no_suspect"]
        and cell["p5_not_single_regime_episode"]
    )
    if promote:
        return "PROMOTE_BOUNDED_PROBE_CANDIDATE"
    if not cell["p1_mean_net_E_positive"] or not p3:
        return "BLOCK_CONFIRMED_UNDER_EXPECTED_COST"
    # E1-E5 過、P1∧P3 過但 P2/P4/P5 缺:非 PROMOTE 非 VETO,按 §8.1 字面
    # VETO 只由 ¬P1∨¬P3 觸發 → 此類 cell 記 NOT_PROMOTED_SECONDARY_CONDITION。
    return "NOT_PROMOTED_SECONDARY_CONDITION_FAILED"


def global_verdict(cells: list[dict[str, Any]]) -> dict[str, Any]:
    """§8.2 全域裁決語言(三態,擇一;樣本不足不得寫成落錘)。"""
    tested = [cell for cell in cells if cell["eligible"]]
    promote = [
        cell for cell in tested if cell["verdict"] == "PROMOTE_BOUNDED_PROBE_CANDIDATE"
    ]
    if promote:
        language = "翻正 cell 清單"
        state = "PROMOTE_CELLS_PRESENT"
    elif tested:
        language = (
            "誤殺假說在 E[cost] 主判下落錘;over-gate 淨貢獻按檢定 cells 收口"
        )
        state = "FALSE_KILL_HYPOTHESIS_HAMMERED"
    else:
        language = "母集去重後無可檢定 cell;誤殺問題維持 UNDECIDED"
        state = "UNDECIDED_ALL_SAMPLE_INSUFFICIENT"
    return {
        "state": state,
        "language": language,
        "tested_cell_count": len(tested),
        "promote_cells": [
            {
                "side_cell_key": cell["side_cell_key"],
                "horizon_minutes": cell["horizon_minutes"],
                "n_eff": cell["n_eff"],
                "g_days": cell["distinct_entry_utc_days"],
                "p_cluster": cell["p_cluster_one_sided"],
                "bh_fdr_pass": cell["bh_fdr_pass"],
                "mean_net_E": cell["mean_net_E"],
                "mean_net_tail": cell["mean_net_tail"],
                "bull_heavy": cell["regime"]["bull_heavy"],
            }
            for cell in promote
        ],
        "veto_cells": [
            {
                "side_cell_key": cell["side_cell_key"],
                "horizon_minutes": cell["horizon_minutes"],
                "n_eff": cell["n_eff"],
                "p_cluster": cell["p_cluster_one_sided"],
                "mean_net_E": cell["mean_net_E"],
            }
            for cell in tested
            if cell["verdict"] == "BLOCK_CONFIRMED_UNDER_EXPECTED_COST"
        ],
        # §2.3 排除明細:E1-E5 可能全過但複本不一致 / V=0 → 不進 family,
        # 無統計結論;artifact 必列(不得靜默消失在 sample-insufficient 裡)。
        "data_integrity_suspect_cells": [
            {
                "side_cell_key": cell["side_cell_key"],
                "horizon_minutes": cell["horizon_minutes"],
                "n_eff": cell["n_eff"],
                "replica_inconsistent_group_count": (
                    cell["replica_inconsistent_group_count"]
                ),
                "zero_variance_suspect": cell["zero_variance_suspect"],
                "mean_net_E_no_conclusion": cell["mean_net_E"],
            }
            for cell in cells
            if cell["verdict"] == "DATA_INTEGRITY_SUSPECT_EXCLUDED"
        ],
    }


# ---------------------------------------------------------------------------
# 編排
# ---------------------------------------------------------------------------

def _side_from_smallint(side: Any) -> str:
    return "Buy" if int(side) > 0 else "Sell"


def _base_deviation_log() -> list[dict[str, str]]:
    """§10.1 實作層 deviation 靜態清單(每次 run 起始寫入 artifact)。

    為什麼獨立成函數:預註冊 §10.1「任何與本檔不符的計算選擇 = deviation 必記」
    是管線自身的治理機制;清單抽出後可被單元測試鎖住,防止實作層偏離
    (如凍結 SQL 投影改寫)存在於代碼卻漏記 deviation_log 的不一致。
    """
    return [
        {
            "level": "implementation",
            "what": "population B 重放時 sign_flip_b=1(凍結 run 為 1000)",
            "why": "headline sign-flip 不參與 cell 分類,降 B 僅省時,枚舉不受影響",
        },
        {
            "level": "implementation",
            "what": "blocked_outcome_review_latest.json 已被後續 cron 覆蓋,"
                    "凍結輸入改用 stamped 檔 blocked_outcome_review_20260709T212701Z.json",
            "why": "該檔 sha256 與預註冊 §0.1 錨逐字節一致(299751f2…),凍結完整",
        },
        {
            "level": "implementation",
            "what": "edge_estimates 的 realized EV 取 raw_bps 欄(檔內無 "
                    "realized_ev_bps/ev_bps 鍵)",
            "why": "raw_bps = 未收縮的 realized fills 均值,語義即 §6.3 的 realized EV",
        },
        {
            "level": "implementation",
            "what": "ledger 觀測為 close 價 markout、kline_backfill 為 open 價"
                    "(§2.1 規格);兩源以 obs_source 欄申報,同鍵取 ledger",
            "why": "預註冊 §2.1 已預期雙源並要求記 obs_source 佔比",
        },
        {
            "level": "implementation",
            "what": "母集 A 凍結 SQL 非逐字執行:SELECT 投影改寫為 "
                    "(EXTRACT(EPOCH FROM r.ts)*1000)::bigint AS ts_ms 並省略 "
                    "r.ts/r.reason 原欄;WHERE 子句與預註冊 §1.1 逐字一致",
            "why": "投影只改欄位形態不改行集;母集身分由 71,207 計數錨 + no-join "
                   "守恆斷言機械保證,ts_ms 轉換等價於 Python 層 epoch-ms 轉換",
        },
    ]


def select_family(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """§5.1 family 選擇(純函數):eligible ∧ p 可用 ∧ 屬母集 A∪B。

    NEAR charter 單列 cell(population_membership=[NEAR_CHARTER_MANDATED])
    永不進 family:它在預註冊 family 之外,混入 BH step-up 會灌水 m(§5)。
    """
    return [
        cell
        for cell in cells
        if cell["eligible"]
        and cell["p_cluster_one_sided"] is not None
        and (
            "A" in cell["population_membership"]
            or "B" in cell["population_membership"]
        )
    ]


def run_rerun(args: argparse.Namespace) -> dict[str, Any]:
    now_utc = dt.datetime.now(dt.timezone.utc)
    frozen_generated_at = _parse_iso_utc(FROZEN_REVIEW_GENERATED_AT)
    deviation_log: list[dict[str, str]] = _base_deviation_log()

    # ---- 凍結錨驗證 ----
    frozen_review_path = Path(args.frozen_review_json)
    frozen_sha = _sha256_file(frozen_review_path)
    if frozen_sha != FROZEN_REVIEW_SHA256:
        raise DeviationStop(
            f"frozen review artifact sha256 {frozen_sha} != anchor {FROZEN_REVIEW_SHA256}"
        )
    manifest, ledger_rows = load_frozen_ledger_rows(
        Path(args.ledger_snapshot_dir), frozen_generated_at=frozen_generated_at
    )

    # ---- 母集 B 重枚舉 ----
    pop_b = reproduce_population_b(
        Path(args.frozen_outcome_review_py),
        ledger_rows,
        frozen_generated_at=frozen_generated_at,
    )
    if not pop_b["anchor_match"]:
        raise DeviationStop(
            "v3 reproduction does not match frozen anchors: "
            + json.dumps(
                {
                    "side_cell_count": pop_b["observed_side_cell_count"],
                    "diagnosis_counts": pop_b["observed_diagnosis_counts"],
                    "outcome_count": pop_b["observed_blocked_outcome_count"],
                },
                ensure_ascii=False,
            )
        )
    b_cells = pop_b["gross_edge_positive_cells"]
    if len(b_cells) != FROZEN_POPULATION_B_COUNT:
        raise DeviationStop(
            f"population B enumeration {len(b_cells)} != frozen {FROZEN_POPULATION_B_COUNT}"
        )

    # ---- PG:母集 A + 市場資料 ----
    conn = _connect_readonly_pg(statement_timeout_ms=args.pg_statement_timeout_ms)
    try:
        pop_a_rows = fetch_population_a(conn)
        a_cells: dict[str, list[dict[str, Any]]] = {}
        for row in pop_a_rows:
            key = "|".join(
                [
                    str(row["strategy_name"]).strip(),
                    str(row["symbol"]).strip().upper(),
                    _side_from_smallint(row["side"]),
                ]
            )
            a_cells.setdefault(key, []).append(row)

        scope_cells = sorted(set(a_cells) | set(b_cells) | {NEAR_CELL_KEY})
        scope_symbols = sorted(
            {key.split("|")[1] for key in scope_cells if key.count("|") >= 2}
        )
        a_symbols = sorted({key.split("|")[1] for key in a_cells})
        all_ts = [int(row["ts_ms"]) for row in pop_a_rows]
        bars_by_symbol = fetch_minute_bars(
            conn,
            a_symbols,
            start_ms=min(all_ts) - 60_000,
            end_ms=max(all_ts) + (max(HORIZON_UNIVERSE) + 60) * 60_000,
        )
        daily_closes = fetch_daily_closes(conn, sorted({"BTCUSDT", *scope_symbols}))
        funding_intervals = fetch_funding_intervals(conn, scope_symbols)
    finally:
        close = getattr(conn, "close", None)
        if callable(close):
            close()
    missing_funding = [s for s in scope_symbols if s not in funding_intervals]
    if missing_funding:
        deviation_log.append(
            {
                "level": "implementation",
                "what": (
                    "funding interval 缺歷史觀測 → 8h fallback: "
                    + ",".join(missing_funding)
                ),
                "why": "research.alpha_funding_rates_history 覆蓋 20 symbols 且止於 "
                       "2026-06-02;8h 為 Bybit 主流值,60/240m horizon 下影響 ≤1bps",
            }
        )
    missing_daily = [s for s in scope_symbols if s not in daily_closes]
    if missing_daily:
        deviation_log.append(
            {
                "level": "implementation",
                "what": "1d klines 缺 symbol → sym_vol_30d 記 unknown: "
                        + ",".join(missing_daily),
                "why": "§7 缺資料不猜;E1-E5 與 single_regime/bull_heavy 判定不受影響"
                       "(btc 指標與天數結構仍可計)",
            }
        )

    # ---- 成本雙軌輸入 ----
    slippage_payload = json.loads(
        Path(args.slippage_artifact).read_text(encoding="utf-8")
    )
    expected_slippage = _load_expected_slippage(slippage_payload, now=now_utc)
    if expected_slippage is None:
        raise DeviationStop(
            "slippage artifact unusable (missing/stale/no mean_abs); §6.1 主判軌"
            "不可用時不得以 conservative 頂替主判 —— 停"
        )
    conservative_table = load_slippage_quantiles(slippage_payload)
    edge_estimates: dict[str, Any] = {}
    if args.edge_estimates_json:
        edge_path = Path(args.edge_estimates_json)
        if edge_path.exists():
            edge_estimates = json.loads(edge_path.read_text(encoding="utf-8"))

    # ---- 觀測構建 + per-(cell,horizon) 統計 ----
    ledger_by_cell: dict[str, list[dict[str, Any]]] = {}
    for row in ledger_rows:
        key = str(row.get("side_cell_key") or "").strip()
        if key in scope_cells or key == NEAR_CELL_KEY:
            ledger_by_cell.setdefault(key, []).append(row)

    btc_closes = daily_closes.get("BTCUSDT", {})
    cells: list[dict[str, Any]] = []
    for cell_key in scope_cells:
        symbol = cell_key.split("|")[1]
        strategy = cell_key.split("|")[0]
        membership = []
        if cell_key in a_cells:
            membership.append("A")
        if cell_key in b_cells:
            membership.append("B")
        if cell_key == NEAR_CELL_KEY and not membership:
            membership.append("NEAR_CHARTER_MANDATED")
        edge_estimate = edge_estimates.get(f"{strategy}::{symbol}")
        for horizon in HORIZON_UNIVERSE:
            obs_bundle = build_observations_for_cell(
                cell_key=cell_key,
                horizon_minutes=horizon,
                ledger_rows=ledger_by_cell.get(cell_key, []),
                pg_rejections=a_cells.get(cell_key, []),
                bars=bars_by_symbol.get(symbol),
            )
            cells.append(
                build_cell_horizon_stats(
                    cell_key=cell_key,
                    horizon_minutes=horizon,
                    membership=membership,
                    obs_bundle=obs_bundle,
                    expected_slippage=expected_slippage,
                    funding_interval_hours=funding_intervals.get(symbol, 8.0),
                    conservative_table=conservative_table,
                    btc_closes=btc_closes,
                    symbol_closes=daily_closes.get(symbol),
                    edge_estimate=(
                        edge_estimate if isinstance(edge_estimate, dict) else None
                    ),
                    now_utc=now_utc,
                )
            )

    # ---- family 推斷(§5):BH 只對 A∪B eligibility 過的 cells;NEAR 家族外 ----
    family = select_family(cells)
    for cell in family:
        cell["bh_in_family"] = True
    if family:
        passed = bh_fdr_pass(
            [float(cell["p_cluster_one_sided"]) for cell in family], FDR_Q
        )
        for cell, ok in zip(family, passed):
            cell["bh_fdr_pass"] = bool(ok)
    for cell in cells:
        cell["verdict"] = judge_cell(cell)

    # headline sign-flip(§5.6):family cells 的去重後非重疊主判軌淨值
    # (build 階段以 _selected_nets 暫存,取用後全量移除,不落 artifact)。
    family_nets: list[list[float]] = []
    for cell in family:
        nets = cell.get("_selected_nets")
        if nets:
            family_nets.append(list(nets))
    headline = sign_flip_selection_p_value(
        family_nets, b=SIGN_FLIP_B, seed=SIGN_FLIP_SEED
    )
    for cell in cells:
        cell.pop("_selected_nets", None)

    # σ_dedup + power 表更新(§3.3;門檻不隨 σ 移動)。
    pooled = [v for nets in family_nets for v in nets]
    sigma_dedup = None
    if len(pooled) >= 2:
        pooled_mean = sum(pooled) / len(pooled)
        sigma_dedup = math.sqrt(
            sum((v - pooled_mean) ** 2 for v in pooled) / (len(pooled) - 1)
        )
    z_sum = 1.6448536269514722 + 0.8416212335729143  # z_0.95 + z_0.80
    power_table = None
    if sigma_dedup is not None and sigma_dedup > 0.0:
        power_table = {
            "sigma_dedup_bps": sigma_dedup,
            "detectable_effect_at_n30_bps": sigma_dedup * z_sum / math.sqrt(30),
            "n_for_50bps": (sigma_dedup * z_sum / 50.0) ** 2,
            "n_for_20bps": (sigma_dedup * z_sum / 20.0) ** 2,
            "note": "normal 近似(§3.3);E1-E5 門檻凍結,不因 σ_dedup 移動",
        }

    verdict = global_verdict(
        [cell for cell in cells if cell["population_membership"] != ["NEAR_CHARTER_MANDATED"]]
    )
    tested = [
        cell
        for cell in cells
        if cell["eligible"]
        and cell["population_membership"] != ["NEAR_CHARTER_MANDATED"]
    ]
    gate_pricing = {
        "wrongful_block_expected_loss_upper_bound_bps_x_n": sum(
            cell["n_eff"] * (cell["mean_net_E"] or 0.0) for cell in tested
        ),
        "caveat": (
            "fill-at-signal 反事實上界:真 fill 有滑點與 queue 損耗,只可作 "
            "upper bound 敘事(§8.4)"
        ),
        "veto_cells_avoided_loss_confirmation": [
            {
                "side_cell_key": cell["side_cell_key"],
                "horizon_minutes": cell["horizon_minutes"],
                "n_eff_x_mean_net_E": cell["n_eff"] * (cell["mean_net_E"] or 0.0),
            }
            for cell in tested
            if cell["verdict"] == "BLOCK_CONFIRMED_UNDER_EXPECTED_COST"
        ],
        "candidacy_flipped_by_cost_model_count": sum(
            1 for cell in cells if cell["candidacy_flipped_by_cost_model"]
        ),
    }

    near_cells = [cell for cell in cells if cell["side_cell_key"] == NEAR_CELL_KEY]
    near_section = {
        "side_cell_key": NEAR_CELL_KEY,
        "v3_frozen_diagnosis": pop_b["near_cell_v3_diagnosis"],
        "family_membership": "outside_prereg_family_charter_mandated_rejudgment",
        "per_horizon": [
            {
                "horizon_minutes": cell["horizon_minutes"],
                "n_raw_ledger_rows": cell["n_raw_ledger_rows"],
                "n_dedup": cell["n_dedup"],
                "n_eff": cell["n_eff"],
                "distinct_entry_utc_days": cell["distinct_entry_utc_days"],
                "sample_eligibility_failures": cell["sample_eligibility_failures"],
                "verdict": cell["verdict"],
                "mean_net_E": cell["mean_net_E"],
            }
            for cell in near_cells
        ],
    }

    k_registration = {
        "prereg_literal_cells": FROZEN_SIDE_CELL_COUNT + len(a_cells),
        "distinct_scanned_scope_cells": len(scope_cells),
        "horizon_universe": list(HORIZON_UNIVERSE),
        "k_effective_prereg_literal": (
            (FROZEN_SIDE_CELL_COUNT + len(a_cells)) * len(HORIZON_UNIVERSE)
        ),
        "note": (
            "§5.5 selection universe = 76 ledger cells + 母集 A 6 cells(重疊未去重"
            "即 82)× {60,240};並列申報 scope 去重計數供透明"
        ),
    }

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "record_type": "counterfactual_rerun_verdict",
        "generated_at_utc": now_utc.isoformat(),
        "preregistration": {
            "doc_path": PREREG_DOC_PATH,
            "doc_git_sha": args.prereg_doc_git_sha,
            "criteria_frozen": True,
        },
        "freeze_verification": {
            "population_a": {
                "expected": FROZEN_POPULATION_A_COUNT,
                "observed": len(pop_a_rows),
                "join_conserved": True,
                "cells": {key: len(rows) for key, rows in sorted(a_cells.items())},
            },
            "population_b": {
                "expected": FROZEN_POPULATION_B_COUNT,
                "observed": len(b_cells),
                "cells": b_cells,
                "v3_reproduction": {
                    "anchor_match": pop_b["anchor_match"],
                    "side_cell_count": pop_b["observed_side_cell_count"],
                    "diagnosis_counts": pop_b["observed_diagnosis_counts"],
                    "blocked_outcome_count": pop_b["observed_blocked_outcome_count"],
                },
            },
            "frozen_review_artifact": {
                "path": str(frozen_review_path),
                "sha256": frozen_sha,
                "anchor_sha256": FROZEN_REVIEW_SHA256,
                "match": True,
            },
            "ledger_files": manifest,
        },
        "inputs": {
            "slippage_artifact": {
                "path": str(args.slippage_artifact),
                "schema_version": slippage_payload.get("schema_version"),
                "asof": slippage_payload.get("asof"),
                "global_mean_abs": expected_slippage.get("global_mean_abs"),
                "global_tail_bps": expected_slippage.get("global_tail_bps"),
                "global_tail_metric": expected_slippage.get("global_tail_metric"),
            },
            "edge_estimates": {
                "path": args.edge_estimates_json,
                "loaded_cells": max(len(edge_estimates) - 1, 0),
                "realized_ev_field": "raw_bps",
            },
            "funding_intervals_hours": funding_intervals,
            "funding_interval_fallback_8h_symbols": missing_funding,
            "kline_1d_missing_symbols": missing_daily,
        },
        "thresholds": {
            "min_n_eff": MIN_N_EFF,
            "min_distinct_entry_utc_days": MIN_DISTINCT_UTC_DAYS,
            "max_top_entry_day_share_pct": MAX_TOP_DAY_SHARE_PCT,
            "max_censored_pct": MAX_CENSORED_PCT,
            "min_net_positive_pct": MIN_NET_POSITIVE_PCT,
            "fdr_q": FDR_Q,
            "horizon_universe": list(HORIZON_UNIVERSE),
        },
        "cells": cells,
        "family": {
            "m": len(family),
            "members": [
                {
                    "side_cell_key": cell["side_cell_key"],
                    "horizon_minutes": cell["horizon_minutes"],
                    "p_cluster": cell["p_cluster_one_sided"],
                    "bh_fdr_pass": cell["bh_fdr_pass"],
                }
                for cell in family
            ],
            "k_registration": k_registration,
            "headline_selection": {
                "method": "sign_flip",
                "b": SIGN_FLIP_B,
                "seed": SIGN_FLIP_SEED,
                **{k: v for k, v in headline.items() if k != "b"},
                "headline_edge_language_allowed": bool(
                    headline["p_selection"] < 0.05
                ),
            },
            "sigma_dedup_bps": sigma_dedup,
            "power_table": power_table,
        },
        "verdict": verdict,
        "gate_bidirectional_pricing": gate_pricing,
        "near_candidate_rejudgment": near_section,
        "deviation_log": deviation_log,
        "exploratory": False,
        "promotion_evidence": False,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "boundary": (
            "counterfactual rerun research artifact only; PG SELECT-only; no "
            "order, Bybit call, runtime config, risk, auth, or Cost Gate "
            "mutation; max effect = bounded probe candidate re-ranking"
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-snapshot-dir", type=Path, required=True)
    parser.add_argument("--frozen-review-json", type=Path, required=True)
    parser.add_argument("--frozen-outcome-review-py", type=Path, required=True)
    parser.add_argument("--slippage-artifact", type=Path, required=True)
    parser.add_argument("--edge-estimates-json", type=str, default=None)
    parser.add_argument("--prereg-doc-git-sha", type=str, required=True)
    parser.add_argument("--pg-statement-timeout-ms", type=int, default=300_000)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        artifact = run_rerun(args)
    except DeviationStop as exc:
        # 預註冊 §10.2:影響母集/判定式的偏離 → 停(不產 verdict,回 PM)。
        payload = {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "record_type": "counterfactual_rerun_deviation_stop",
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "deviation_stop": str(exc),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"DEVIATION_STOP: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    summary = {
        "verdict_state": artifact["verdict"]["state"],
        "tested_cells": artifact["verdict"]["tested_cell_count"],
        "promote_cells": len(artifact["verdict"]["promote_cells"]),
        "veto_cells": len(artifact["verdict"]["veto_cells"]),
        "family_m": artifact["family"]["m"],
        "output": str(args.output),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
