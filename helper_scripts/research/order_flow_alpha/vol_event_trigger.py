#!/usr/bin/env python3
"""order_flow_alpha.vol_event_trigger — vol-event 增量自動累積器（$0 唯讀，OFFLINE）。

MODULE_NOTE
模塊用途：
  把既有一次性的 regime-aware 決定性 fee-wall harness（analysis.py + regime.py，本 session
  所建）變成「增量自動累積器」。每次運行：掃 recorder-v2 tape（market.trades / ob_top）
  找出自上次以來「新」的 high-vol 事件窗，用 regime.py 的 leak-free PIT 偵測器標記，對每個
  新事件跑 regime-split fee-wall 分析（復用 analysis.run），把結果（per-axis gross bps、
  net-of-cost、survives_wall bool、direction tag、n_rows）append 進一個持久化 LEDGER（JSON）。
  累積到 ≥3 個獨立事件（含 ≥1 個 upside_squeeze）後，寫一份 robust-ruling summary markdown。

  「事件」定義（為什麼這樣切，避免假事件灌水）：
    一個 vol event = tape 可分析窗內、一串「連續的 high_vol 小時」（相鄰或 gap ≤ 1h 合併成
    一個 cluster）。把每個 cluster 視為「一個事件」，anchor = cluster 內 |hourly ret_bp| 最大
    的那一小時；direction = anchor 小時 ret 的符號（< 0 = downside / > 0 = upside_squeeze）。
    為什麼不是「每個 high_vol 小時 = 一個事件」：trailing RV 升高後常一連幾十小時都被標
    high_vol（RV 是 trailing 平均，滯後回落），逐小時記會造出幾十個高度重疊的假事件，破壞
    「≥3 個獨立事件」的統計獨立性。cluster 合併 → 每個獨立的波動行情 = 一個獨立事件。

  idempotent / 增量：ledger 以 anchor 小時 ISO 為 key，已分析過的事件絕不重跑。每次運行只
  處理「新」cluster，且按 anchor |ret_bp| 由大到小排序、最多取 --max-events 個（預設 2），
  確保每次運行 bounded + 快（最強的決定性事件優先入帳）。

  NOTIFICATION：偵測到既有的耐久告警 sink（helper_scripts/canary/alert_sink.py 的
  append_alert_sink，純本地 append JSONL、零外部發送、read-only-safe）→ 用它當主通道
  （channels_attempted=[] 故不嘗試任何外部發送）；同時恆寫一行到 self-contained run log
  + 在達成里程碑時寫 marker 檔（mandate 要求的 fallback 一併保留作審計線）。

依賴（READ-ONLY 復用 sibling 資料層 + 本目錄 harness，皆不改其檔）：
  - analysis.run / regime.classify_hours（本目錄 sibling）
  - program_code.research.microstructure.data_loader（read-only PG connect）
  - helper_scripts/canary/alert_sink.append_alert_sink（耐久告警 sink；read-only-safe）

硬邊界：
  - 純讀 PG（connect 已 set_session readonly=True）；0 寫 PG、0 order、0 auth/lease/risk、
    0 production engine/risk 改動。只寫 data-dir research artifact（ledger JSON / report md /
    log / marker），不把週期性 latest report 寫回 git source tree。
  - 不改 sibling microstructure 檔，不改 analysis.py / regime.py，只 import 復用。
  - leak-free 由 regime.py / analysis.py 保證（shift(1) PIT，無 current-bar）；本檔不新增任何
    統計，只編排 + 累積 + 通知。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

# --- 路徑：本檔在 helper_scripts/research/order_flow_alpha/ ---
_THIS = os.path.realpath(__file__)
_THIS_DIR = os.path.dirname(_THIS)
_SRV_ROOT = os.path.abspath(os.path.join(_THIS, "..", "..", "..", ".."))
if _SRV_ROOT not in sys.path:
    sys.path.insert(0, _SRV_ROOT)
# 同目錄 sibling（helper_scripts 非 package，加本檔目錄供 import）。
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
# 復用 canary 的耐久 sink（read-only-safe，純本地 append）。
_CANARY_DIR = os.path.abspath(os.path.join(_SRV_ROOT, "helper_scripts", "canary"))
if _CANARY_DIR not in sys.path:
    sys.path.insert(0, _CANARY_DIR)

import analysis as ofa_analysis  # noqa: E402
import regime as ofa_regime  # noqa: E402
from program_code.research.microstructure import data_loader as ms_loader  # noqa: E402

# 耐久 sink 為「可選的最佳通道」：缺席時不致命（fallback 到 log + marker）。
try:
    import alert_sink as _alert_sink  # noqa: E402

    _HAVE_SINK = hasattr(_alert_sink, "append_alert_sink")
except Exception:  # noqa: BLE001 - sink 缺席不得致命，僅退回 log fallback
    _alert_sink = None
    _HAVE_SINK = False


# --- 路徑常數（全走 env / $HOME，禁硬編 user path；跨平台） ---
def _data_dir() -> str:
    """OPENCLAW_DATA_DIR（cron wrapper export）否則預設 /tmp/openclaw。"""
    return os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")


def _ledger_path() -> str:
    return os.path.join(_data_dir(), "order_flow_alpha", "vol_event_ledger.json")


def _per_event_dir() -> str:
    return os.path.join(_data_dir(), "order_flow_alpha", "events")


def _log_path() -> str:
    return os.path.join(_data_dir(), "logs", "vol_event_trigger.log")


def _marker_path(tag: str) -> str:
    return os.path.join(_data_dir(), "order_flow_alpha", f"MARKER_{tag}.txt")


def _report_path() -> str:
    """robust-ruling latest md.

    The cron writes volatile latest evidence under OPENCLAW_DATA_DIR so routine
    runtime refreshes cannot dirty the source checkout. Set the explicit env var
    only for a one-off archival export that is meant to be reviewed/committed.
    """
    explicit = os.environ.get("OPENCLAW_VOL_EVENT_RULING_REPORT_PATH")
    if explicit:
        return explicit
    return os.path.join(_data_dir(), "order_flow_alpha", "vol-event-robust-ruling.md")


# 達成 robust ruling 的門檻（mandate 指定）。
MIN_EVENTS_FOR_RULING = 3
GAP_MERGE_HOURS = 1  # 相鄰 high_vol 小時 gap <= 1h 合併成一個事件 cluster
DEFAULT_MAX_EVENTS_PER_RUN = 2  # 每次運行最多分析 N 個新事件（bounded / 快）
DEFAULT_TOP_N = 12  # top 流動 symbol 數（含 BTCUSDT，per mandate）


# ============================================================================
# 結構化 logging（self-contained，每行帶 run timestamp）
# ============================================================================
def _log(msg: str) -> None:
    """append 一行帶 UTC timestamp 的 log（永不拋；log 是觀測面不得致命）。"""
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} [vol_event_trigger] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(_log_path()), exist_ok=True)
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001 - log 寫入失敗不得中斷主流程
        pass


# ============================================================================
# LEDGER I/O（idempotent 持久化）
# ============================================================================
def _load_ledger() -> dict:
    """讀 ledger JSON；不存在或損毀 → 回空 ledger（fail-soft 重建）。"""
    p = _ledger_path()
    if not os.path.exists(p):
        return {"version": 1, "events": {}, "milestones": {}}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("version", 1)
        data.setdefault("events", {})
        data.setdefault("milestones", {})
        return data
    except Exception as exc:  # noqa: BLE001 - 損毀 ledger 不得致命；記 log 後重建
        _log(f"WARN ledger 讀取失敗（將重建空 ledger）：{exc}")
        return {"version": 1, "events": {}, "milestones": {}}


def _save_ledger(ledger: dict) -> None:
    """原子寫 ledger（temp + os.replace，避免半截檔）。"""
    p = _ledger_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2, default=str)
    os.replace(tmp, p)


# ============================================================================
# 事件偵測：把 tape 可分析窗內的 high_vol 小時切成獨立事件 cluster
# ============================================================================
def _tape_window(conn) -> tuple[pd.Timestamp, pd.Timestamp]:
    """recorder-v2 tape 的 [min(ts), max(ts)]（UTC）。"""
    cur = conn.cursor()
    cur.execute("SELECT min(ts), max(ts) FROM market.trades")
    tmin, tmax = cur.fetchone()
    cur.close()
    if tmin is None or tmax is None:
        raise RuntimeError("market.trades 為空，無 tape 可分析")
    return pd.Timestamp(tmin).tz_convert("UTC"), pd.Timestamp(tmax).tz_convert("UTC")


def detect_events(conn) -> list[dict]:
    """偵測 tape 可分析窗內的所有 high_vol 事件 cluster（leak-free，PIT regime）。

    步驟：
      1. regime.classify_hours → 每小時 leak-free regime 標籤（PIT shift(1)）。
      2. 只留落在 tape [min,max) 窗內的 high_vol 小時（這些小時才有 trade/ob_top 微結構可分析）。
      3. 把連續（gap <= GAP_MERGE_HOURS）的 high_vol 小時合併成 cluster = 一個事件。
      4. 每個 cluster：anchor = |ret_bp| 最大的小時；direction = anchor ret 符號
         （< 0 = downside / > 0 = upside_squeeze / == 0 罕見 → flat 視為 downside 保守標）。

    回傳 list[event dict]，按 cluster 起始時間升序。每個 event 含：
      event_key（anchor 小時 ISO）、anchor_ts、direction、cluster_start/cluster_end（含端）、
      n_high_vol_hours、anchor_ret_bp、max_abs_ret_bp、hours（cluster 內各小時摘要）。
    """
    labelled, thr, _spk = ofa_regime.classify_hours(conn)
    tmin, tmax = _tape_window(conn)
    # tape 窗內的 high_vol 小時（floor 到 hour）。
    hv = labelled[
        (labelled["regime"] == "high_vol")
        & (labelled["ts"] >= tmin.floor("h"))
        & (labelled["ts"] < tmax)
    ].sort_values("ts").reset_index(drop=True)
    events: list[dict] = []
    if hv.empty:
        return events
    # cluster 合併：相鄰 high_vol 小時 gap <= GAP_MERGE_HOURS 視為同事件。
    cluster_rows: list[dict] = []
    prev_ts = None
    for _, row in hv.iterrows():
        ts = row["ts"]
        if prev_ts is not None and (ts - prev_ts) > timedelta(hours=GAP_MERGE_HOURS):
            events.append(_finalize_cluster(cluster_rows))
            cluster_rows = []
        cluster_rows.append(row.to_dict())
        prev_ts = ts
    if cluster_rows:
        events.append(_finalize_cluster(cluster_rows))
    return events


def _finalize_cluster(rows: list[dict]) -> dict:
    """把一串連續 high_vol 小時 row 收斂成一個事件 dict（決定 anchor + direction）。"""
    df = pd.DataFrame(rows)
    df["abs_ret"] = df["ret_bp"].abs()
    anchor = df.loc[df["abs_ret"].idxmax()]
    anchor_ts = pd.Timestamp(anchor["ts"])
    anchor_ret = float(anchor["ret_bp"]) if pd.notna(anchor["ret_bp"]) else 0.0
    # direction：anchor 小時 ret 符號。< 0 = 跌（downside）；> 0 = 漲（upside_squeeze）。
    # ret == 0（極罕見）保守標 downside（不誤宣稱 squeeze diversity）。
    direction = "upside_squeeze" if anchor_ret > 0 else "downside"
    return {
        "event_key": anchor_ts.isoformat(),
        "anchor_ts": anchor_ts.isoformat(),
        "direction": direction,
        "anchor_ret_bp": round(anchor_ret, 1),
        "max_abs_ret_bp": round(float(df["abs_ret"].max()), 1),
        "cluster_start": pd.Timestamp(df["ts"].min()).isoformat(),
        "cluster_end": pd.Timestamp(df["ts"].max()).isoformat(),
        "n_high_vol_hours": int(len(df)),
        "any_spike": bool(df["has_spike"].any()),
        "hours": [
            {"ts": pd.Timestamp(r["ts"]).isoformat(),
             "ret_bp": (round(float(r["ret_bp"]), 1) if pd.notna(r["ret_bp"]) else None),
             "rv_pctile": round(float(r["rv_pctile"]), 3),
             "has_spike": bool(r["has_spike"])}
            for r in rows
        ],
    }


# ============================================================================
# 對單一事件跑 regime-split fee-wall 分析（復用 analysis.run）
# ============================================================================
def analyze_event(event: dict, top_n: int) -> dict:
    """對一個事件 cluster 跑 regime-split harness，抽 high_vol block 的 fee-wall 結果。

    窗 = [cluster_start, cluster_end + 1h)（含 anchor 整段 + 收尾那一小時的完整資料）。
    復用 analysis.run（不改）：regime_split=True → report["regime_split_decisive"]["high_vol"]。
    把 per-axis gross bps / survives bool / net-of-cost / n_rows 收斂成 ledger record。
    """
    start = pd.Timestamp(event["cluster_start"])
    end = pd.Timestamp(event["cluster_end"]) + timedelta(hours=1)
    out_json = os.path.join(_per_event_dir(),
                            f"event_{pd.Timestamp(event['anchor_ts']).strftime('%Y%m%dT%H%M')}.json")
    os.makedirs(_per_event_dir(), exist_ok=True)
    rep = ofa_analysis.run(
        hours=None,
        since=start.isoformat(),
        until=end.isoformat(),
        top_n=top_n,
        out_path=out_json,
        regime_split=True,
    )
    rs = rep.get("regime_split_decisive", {})
    hv = rs.get("high_vol", {})
    fw = hv.get("fee_wall_test", {})
    per_signal = [
        {
            "signal": v.get("signal"),
            "gross_bps": v.get("gross_predicted_bps"),
            "gross_abs_bps": v.get("gross_abs_bps"),
            "net_vs_taker_bps": v.get("net_vs_taker_bps"),
            "net_minus_own_spread_bps": v.get("net_minus_own_spread_bps"),
            "survives_taker_wall": bool(v.get("survives_taker_wall")),
            "survives_maker_fee_wall": bool(v.get("survives_maker_fee_wall")),
            "verdict": v.get("verdict"),
        }
        for v in fw.get("per_signal", [])
    ]
    survives_wall = bool(fw.get("any_survives_taker") or fw.get("any_survives_maker_fee"))
    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "window": [start.isoformat(), end.isoformat()],
        "status": hv.get("status"),
        "n_high_vol_hours_labelled": hv.get("n_hours_labelled"),
        "n_trade_rows": hv.get("n_trade_rows"),
        "n_obtop_rows": hv.get("n_obtop_rows"),
        "symbols_with_valid_grid": hv.get("symbols_with_valid_grid"),
        "btc_present": hv.get("btc_present"),
        "per_signal": per_signal,
        "any_survives_taker": bool(fw.get("any_survives_taker")),
        "any_survives_maker_fee": bool(fw.get("any_survives_maker_fee")),
        "survives_wall": survives_wall,
        "decisive_verdict": rs.get("_decisive_summary", {}).get("verdict"),
        "per_event_report": out_json,
    }


# ============================================================================
# NOTIFICATION（耐久 sink 主 + log/marker fallback，全 read-only-safe）
# ============================================================================
def _notify(subject: str, body: str, severity: str, marker_tag: str | None = None) -> str:
    """發告警：優先用耐久 sink（純本地 append，無外部發送）+ 恆寫 log（+里程碑寫 marker）。

    為什麼也寫 log/marker（即使 sink 在）：mandate 要 self-contained run log + 里程碑 marker
    作審計線；sink 與 log 雙寫互為冗餘（sink 走 alerts.jsonl，log 走 vol_event_trigger.log）。
    回傳實際使用的通道字串（report 內據實揭露）。
    """
    used = []
    if _HAVE_SINK:
        try:
            # channels_attempted=[]：明確「不嘗試任何外部發送」，sink 只本地落盤（read-only-safe）。
            ok = _alert_sink.append_alert_sink(_data_dir(), subject, body, severity, [])
            used.append("durable_sink(alerts.jsonl)" + ("" if ok else "[write-failed]"))
        except Exception as exc:  # noqa: BLE001 - sink 故障不得中斷；退回 log fallback
            _log(f"WARN durable sink 失敗（退回 log fallback）：{exc}")
    # 恆寫 log。
    _log(f"ALERT[{severity}] {subject} :: {body}")
    used.append("run_log(vol_event_trigger.log)")
    if marker_tag:
        try:
            mp = _marker_path(marker_tag)
            os.makedirs(os.path.dirname(mp), exist_ok=True)
            with open(mp, "w", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat()}\n{subject}\n{body}\n")
            used.append(f"marker({os.path.basename(mp)})")
        except Exception as exc:  # noqa: BLE001 - marker 寫入失敗不得中斷
            _log(f"WARN marker 寫入失敗：{exc}")
    return " + ".join(used)


# ============================================================================
# robust-ruling summary markdown（≥3 事件 + ≥1 upside_squeeze 後產出）
# ============================================================================
def _write_robust_ruling(ledger: dict) -> str:
    """跨事件彙總：是否有任一軸在任一/多數 high_vol 事件過成本牆？寫 md。"""
    events = ledger["events"]
    rows = sorted(events.values(), key=lambda e: e.get("anchor_ts", ""))
    n = len(rows)
    directions = [e.get("direction") for e in rows]
    n_up = directions.count("upside_squeeze")
    n_down = directions.count("downside")
    n_survive = sum(1 for e in rows if e.get("analysis", {}).get("survives_wall"))
    # per-axis 跨事件存活計數。
    axis_survive: dict[str, int] = {}
    axis_total: dict[str, int] = {}
    for e in rows:
        for sig in e.get("analysis", {}).get("per_signal", []):
            name = sig.get("signal") or "unknown"
            axis_total[name] = axis_total.get(name, 0) + 1
            if sig.get("survives_taker_wall") or sig.get("survives_maker_fee_wall"):
                axis_survive[name] = axis_survive.get(name, 0) + 1

    any_axis_ever = any(axis_survive.get(k, 0) > 0 for k in axis_total)
    most = {k: v for k, v in axis_survive.items() if v > axis_total[k] / 2}
    if any_axis_ever and most:
        ruling = "ROBUST_EDGE: 某軸在多數 high_vol 事件過成本牆（需 QC 終裁）"
    elif any_axis_ever:
        ruling = "SPORADIC: 某軸僅在少數事件過牆（非穩健，可能 regime/雜訊；QC 終裁）"
    else:
        ruling = "NO_EDGE_SURVIVES: 跨所有 high_vol 事件，無任一軸過成本牆"

    lines = []
    lines.append("# Vol-Event Robust Ruling — order-flow edge × high-vol regime")
    lines.append("")
    lines.append(f"> 自動產出（vol_event_trigger.py）：{datetime.now(timezone.utc).isoformat()}")
    lines.append("> $0 唯讀 / OFFLINE / leak-free PIT。指標性彙總，**最終 verdict 屬 QC**。")
    lines.append("> 不下單、不碰 production engine/risk、不改 sibling 檔。")
    lines.append("")
    lines.append("## 彙總")
    lines.append("")
    lines.append(f"- 已分析獨立 high_vol 事件：**{n}**（downside={n_down} / upside_squeeze={n_up}）")
    lines.append(f"- regime diversity 達成（≥1 upside_squeeze）：**{n_up >= 1}**")
    lines.append(f"- 過成本牆的事件數：**{n_survive} / {n}**")
    lines.append(f"- **ROBUST RULING：{ruling}**")
    lines.append("")
    lines.append("## Per-axis 跨事件存活")
    lines.append("")
    lines.append("| 軸（signal） | 過牆事件數 / 總事件數 |")
    lines.append("|---|---|")
    for k in sorted(axis_total):
        lines.append(f"| {k} | {axis_survive.get(k, 0)} / {axis_total[k]} |")
    lines.append("")
    lines.append("## Per-event 明細")
    lines.append("")
    lines.append("| anchor(UTC) | direction | anchor_ret_bp | n_hours | n_trade_rows | status | survives_wall | verdict |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for e in rows:
        a = e.get("analysis", {})
        lines.append(
            f"| {e.get('anchor_ts')} | {e.get('direction')} | {e.get('anchor_ret_bp')} | "
            f"{a.get('n_high_vol_hours_labelled')} | {a.get('n_trade_rows')} | "
            f"{a.get('status')} | {a.get('survives_wall')} | {a.get('decisive_verdict')} |"
        )
    lines.append("")
    lines.append("## 方法與不變量")
    lines.append("")
    lines.append("- 事件=tape 可分析窗內連續 high_vol 小時 cluster（gap ≤ 1h 合併）；anchor=|ret| 最大時；")
    lines.append("  direction=anchor ret 符號。regime 標籤 leak-free PIT（regime.py，shift(1) RV）。")
    lines.append("- 每事件跑 analysis.run(regime_split=True)，取 high_vol block 的 fee-wall（taker 6bp /")
    lines.append("  maker 4bp / microprice 用 own-spread）。survives_wall=any axis 過牆。")
    lines.append("- low_power_preliminary（樣本薄）的事件 verdict 為指標性；穩健結論需多事件一致。")
    lines.append("")
    p = _report_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return p


# ============================================================================
# 主流程：掃新事件 → 分析 → 入帳 → 通知 → 達標寫 ruling
# ============================================================================
def run(top_n: int, max_events: int, dry_run: bool) -> dict:
    """一次 trigger 運行（idempotent / 增量 / bounded）。"""
    t0 = time.time()
    _log(f"RUN start (top_n={top_n}, max_events={max_events}, dry_run={dry_run})")
    ledger = _load_ledger()
    known = set(ledger["events"].keys())

    conn = ms_loader.connect()
    try:
        all_events = detect_events(conn)
    finally:
        conn.close()

    new_events = [e for e in all_events if e["event_key"] not in known]
    # 最強的決定性事件優先（anchor |ret_bp| 由大到小），bounded 取 max_events 個。
    new_events.sort(key=lambda e: -e["max_abs_ret_bp"])
    to_analyze = new_events[:max_events]
    _log(f"detected {len(all_events)} event clusters in tape; "
         f"{len(new_events)} new; analyzing {len(to_analyze)} this run")

    analyzed_keys = []
    for ev in to_analyze:
        _log(f"analyzing event anchor={ev['anchor_ts']} dir={ev['direction']} "
             f"anchor_ret_bp={ev['anchor_ret_bp']} hours={ev['n_high_vol_hours']}")
        analysis_res = analyze_event(ev, top_n)
        record = dict(ev)
        record["analysis"] = analysis_res
        record["event_index"] = len(ledger["events"]) + 1
        ledger["events"][ev["event_key"]] = record
        analyzed_keys.append(ev["event_key"])
        # (a) 新事件分析告警。
        chan = _notify(
            subject=f"[vol_event] NEW event #{record['event_index']} analyzed: "
                    f"{ev['direction']} anchor={ev['anchor_ts']} ({ev['anchor_ret_bp']}bp)",
            body=f"status={analysis_res.get('status')} "
                 f"n_trade_rows={analysis_res.get('n_trade_rows')} "
                 f"survives_wall={analysis_res.get('survives_wall')} "
                 f"verdict={analysis_res.get('decisive_verdict')}",
            severity="INFO",
        )
        _log(f"  -> recorded event #{record['event_index']}; notify via {chan}")

    if not dry_run or analyzed_keys:
        _save_ledger(ledger)

    # (b) ≥3 事件 + ≥1 upside_squeeze 里程碑。
    events = ledger["events"]
    n = len(events)
    n_up = sum(1 for e in events.values() if e.get("direction") == "upside_squeeze")
    ruling_path = None
    threshold_met = n >= MIN_EVENTS_FOR_RULING and n_up >= 1
    already_fired = ledger["milestones"].get("ruling_3plus_fired", False)
    if threshold_met:
        ruling_path = _write_robust_ruling(ledger)
        if not already_fired:
            chan = _notify(
                subject=f"[vol_event] THRESHOLD reached: {n} events incl {n_up} upside_squeeze "
                        f"-> robust ruling written",
                body=f"robust-ruling md: {ruling_path}",
                severity="WARNING",
                marker_tag="ROBUST_RULING_READY",
            )
            ledger["milestones"]["ruling_3plus_fired"] = True
            ledger["milestones"]["ruling_3plus_at"] = datetime.now(timezone.utc).isoformat()
            _save_ledger(ledger)
            _log(f"THRESHOLD milestone fired; notify via {chan}")
    else:
        _log(f"threshold not yet met: {n}/{MIN_EVENTS_FOR_RULING} events, "
             f"{n_up} upside_squeeze (need >=1)")

    dt = time.time() - t0
    _log(f"RUN done in {dt:.1f}s; ledger now holds {n} events "
         f"(downside={sum(1 for e in events.values() if e.get('direction')=='downside')}, "
         f"upside_squeeze={n_up}); ruling={'WRITTEN' if ruling_path else 'pending'}")
    return {
        "n_events_total": n,
        "n_upside_squeeze": n_up,
        "n_new_analyzed": len(analyzed_keys),
        "analyzed_keys": analyzed_keys,
        "threshold_met": threshold_met,
        "ruling_path": ruling_path,
        "elapsed_s": round(dt, 1),
        "ledger_path": _ledger_path(),
    }


def main():
    ap = argparse.ArgumentParser(
        description="vol-event 增量自動累積器（$0 唯讀；復用 order_flow_alpha harness）")
    ap.add_argument("--top-n", type=int, default=DEFAULT_TOP_N,
                    help=f"每事件取窗內最活躍前 N symbol（含 BTC；預設 {DEFAULT_TOP_N}）")
    ap.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS_PER_RUN,
                    help=f"每次運行最多分析的新事件數（bounded；預設 {DEFAULT_MAX_EVENTS_PER_RUN}）")
    ap.add_argument("--dry-run", action="store_true",
                    help="dry-run：仍寫 ledger（分析了新事件就落帳）但供首次驗證用")
    args = ap.parse_args()
    res = run(args.top_n, args.max_events, args.dry_run)
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
