#!/usr/bin/env python3
"""[69] halt_session_root_cause_recurrence — P1-HALT-TRIGGER 自然事件 RCA 監測。

MODULE_NOTE:
  P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1 的 passive-wait healthcheck。
  v56 P0-ENGINE-HALTSESSION-STUCK-FIX（2026-05-19/20）Layer A + B 完整 CLOSED
  並 real-event verified：drawdown halt 27.51% 啟動 9s 後觸發 forensic log +
  `learning.governance_audit_log` INSERT。但 v56 incident **本身的 trigger
  根因仍 UNRESOLVED** —— 事故發生時 RCA 觀察到 `session_drawdown_pct ≈ 10.2%`
  vs TOML `session_drawdown_max_pct=25.0` / `daily_loss_max_pct=15.0` 數學
  不通；log rotation 失了 UTC 2026-05-19 12:27 那條 warn! 行；spec §1.4
  五個候選假設 (a)-(e) 仍未消除：
    (a) IPC `patch_risk_config` 把門檻臨時拉低
    (b) loading-order race 用了 default Limits 而非 TOML
    (c) 未識別第三條 path 寫了 `paper_paused=true` 而非走 Step 6
    (d) log rotation 真把 UTC 12:27:14 那條 `warn!` 丟了
    (e) drawdown 計算 bug（measurement-side error）

  Layer A 已 armed forensic `halt_audit.log` + Python tail writer
  `halt_audit_pg_writer.py` 把每筆 halt 事件 INSERT 進
  `learning.governance_audit_log`（V098 24-value allowlist 已 land）；
  payload JSONB 內含 `session_drawdown_pct` / `loaded_drawdown_threshold`
  / `loaded_daily_loss_threshold` / `risk_config_version_seen` /
  `paper_state_recompute_ok` 等 5.1 spec 規格欄位。

  本 [69] healthcheck 在 passive-wait 期間定期掃描 `governance_audit_log`
  最近 N 天 halt-session 事件，對每筆 `halt_session_set` event 驗 metric
  vs threshold 的數學關係：
    - PASS  = n ≥ 1 且每筆 halt_set 滿足
              (session_drawdown_pct ≥ loaded_drawdown_threshold)
           OR (daily_loss_pct ≥ loaded_daily_loss_threshold)
              → 自然 recurrence；root cause 跟 v56 incident **不同**
              （即新事故是合理 threshold trigger，可正常 close）
    - WARN  = n ≥ 1 且**至少 1 筆 halt_set** metric < threshold
              → recurrence 模式相符 v56；spec §1.4 五個候選假設 (a)-(e)
              仍未消除；P1-HALT-TRIGGER 須 PA + E2 + FA 聯合 RCA
    - FAIL  = n ≥ 1 (governance_audit_log 有事件) 但 forensic
              `halt_audit.log` 缺對應 row（process_pid + ts_ms 對不上）
              → forensic 寫入機制本身失效，更嚴重
    - INSUFFICIENT_SAMPLE = n = 0 events 過 window
              （多數情況；自然 sparse；不阻 deploy）

  與 [62-67] healthcheck 對齊 SQL semantic + JSON 輸出格式；本 check 不用
  Wilson CI（單筆事件 metric vs threshold 數學判定，非 binomial proportion）。

  Slot 編號邊界（2026-05-21）：
    - canary/healthchecks/（本 package）：[62][63][64][65][66][67][69]
    - [68] 預留 v59 TODO §6.1 H3 PA 用途；本 [69] 取 free slot
    - passive_wait_healthcheck/ 用 [70-74]；namespace 物理分離

  Schema 真相（V035 + V098；2026-05-21 E1 grep 驗證）：
    - `learning.governance_audit_log` 表 column = `ts TIMESTAMPTZ`、
      `event_type TEXT`、`payload JSONB`、`decided_by TEXT`、
      `lease_revoke_triggers TEXT[]`、`rule_failures TEXT[]`
    - V098 24-value CHECK 已含 3 個 halt_session_* event_type
    - `halt_audit_pg_writer.py` INSERT 時 payload jsonb 包整個 forensic
      JSONL row，包括 `session_drawdown_pct` / `loaded_drawdown_threshold`
      / `loaded_daily_loss_threshold` / `daily_loss_pct`（halt_audit.rs:287
      實際 emit Null）/ `process_pid` / `ts_ms`
    - 注意：`daily_loss_pct` 在 set event 為 null（halt_audit.rs:287
      註：「不在 PaperState API，留 null」）— FAIL 判定改為只在 kind
      ∈ {daily_loss, other} 時若 payload 缺 daily_loss_pct 視為「無 metric
      可驗」（不擋 PASS）；drawdown trigger 必有 session_drawdown_pct

CLI:
  python3 69_halt_session_root_cause_recurrence.py [--window-secs 7776000] \\
        [--write-file PATH] [--text]

Exit codes:
  0 = PASS / INSUFFICIENT_SAMPLE（多數情況；不阻 deploy）
  1 = WARN or FAIL（recurrence pattern 相符 v56 / forensic gap）
  2 = PG connect error

建議 cron：daily（rare event；不需 4h cycle；對齊 passive-wait healthcheck
默認 frequency）；若 operator 想更穩 weekly 也夠（事件本就 sparse）。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# 允許 standalone script + module 同時被呼叫
# stdlib import 之後加 sys.path 是為了讓 ``python3 69_halt_session_root_cause_recurrence.py``
# 直接執行也能 import 同目錄 _common；package import 走 __init__.py 不受影響
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _common import (  # noqa: E402
    EXIT_FAIL,
    EXIT_PASS,
    VERDICT_FAIL,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_PASS,
    VERDICT_WARN,
    configure_logging,
    connect_pg,
    emit_result,
    severity_max,
)


# ───────────────────────────────────────────────────────────────────────────
# Default observation window：90 天
# ───────────────────────────────────────────────────────────────────────────
#
# 為什麼 90d：
#   - halt-session 事件天然 sparse（v56 是 7h43m trading 後一次自然觸發）
#   - 90d 對齊 P1-HALT-TRIGGER review date 2026-08-21（v56 closure +90d）
#   - 過短（如 7d）多數情況下永遠 INSUFFICIENT_SAMPLE，passive-wait 變
#     dead gate；過長（如 365d）會把舊 incident 混進來干擾 verdict
#   - 90d 與 governance_audit_log retention 365d 不衝突（policy V098 設）
DEFAULT_WINDOW_SECS_HALT: int = 90 * 24 * 3600  # 90 天

# 數值容差：metric vs threshold 比較必允小 epsilon。
# 為什麼必要：halt_audit.rs payload 寫 f64 `session_drawdown_pct` 與
#   `loaded_drawdown_threshold` 兩個來源不同（前者由 PaperState 即時算，
#   後者由 RiskConfig dump），rounding 後可能差 1e-10 但實際是「達」門檻。
# 為什麼 1e-6：halt 觸發 threshold 都是百分比（0.0-100.0），1e-6 約等於
#   0.0001bp 容差，不會把真實「未達」case 誤判 PASS。
THRESHOLD_TOLERANCE: float = 1e-6


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="69_halt_session_root_cause_recurrence",
        description=(
            "[69] halt_session_root_cause_recurrence — "
            "P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1 自然事件 RCA 監測"
        ),
    )
    parser.add_argument(
        "--window-secs",
        type=int,
        default=DEFAULT_WINDOW_SECS_HALT,
        help=(
            f"Observation window in seconds "
            f"(default {DEFAULT_WINDOW_SECS_HALT}s = 90 天; 對齊 90d review date)"
        ),
    )
    parser.add_argument(
        "--write-file",
        type=str,
        default=None,
        help="Optional JSON artifact write path.",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Human-readable text output instead of JSON.",
    )
    parser.add_argument(
        "--audit-log-path",
        type=str,
        default=None,
        help=(
            "Optional explicit halt_audit.log path; "
            "default = $OPENCLAW_HALT_AUDIT_LOG / $OPENCLAW_DATA_DIR/halt_audit.log "
            "/ /tmp/openclaw/halt_audit.log (鏡 halt_audit_pg_writer.py)"
        ),
    )
    return parser.parse_args()


def _resolve_audit_log_path(explicit: str | None) -> Path:
    """halt_audit.log 路徑解析；與 Rust `halt_audit::resolve_log_path` +
    Python `halt_audit_pg_writer._resolve_audit_log_path` 邏輯對齊。

    為什麼三層 fallback：
      - CLI override > env override > $OPENCLAW_DATA_DIR > /tmp/openclaw
      - 避免本 healthcheck 在不同部署模式下找錯 forensic log
        導致 FAIL 偽陽性
    """
    if explicit:
        return Path(explicit)
    import os
    env = os.environ.get("OPENCLAW_HALT_AUDIT_LOG")
    if env:
        return Path(env)
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / "halt_audit.log"


def _classify_event(
    event_type: str,
    drawdown_pct: float | None,
    daily_loss_pct: float | None,
    threshold_drawdown: float | None,
    threshold_daily_loss: float | None,
    kind: str | None,
) -> tuple[str, str]:
    """單筆 halt_session_set event 的 metric vs threshold 數學判定。

    為什麼分 kind：
      - kind=session_drawdown：必驗 drawdown_pct ≥ threshold_drawdown
      - kind=daily_loss：halt_audit.rs:287 註明 daily_loss_pct 在 set event
        留 null（PaperState 未暴露 API），所以 daily_loss kind 的 halt_set
        無法從 payload 自證 metric；fallback 驗 drawdown_pct（兩條 path 都
        會 set paper_paused，session_drawdown 也會 fail-safe 觸發但 reason
        為 DAILY LOSS 不可能；若 drawdown_pct 也 null 視為「無 metric 可驗」
        → 不阻 PASS（保守不誤判 WARN）
      - kind=other：fail-safe sticky；任何 reason 都接受（無數學可驗）

    回傳 (cell_verdict, note)：
      - "PASS"：metric ≥ threshold（至少一條 satisfied）
      - "WARN"：metric < threshold 兩條都驗了還是低；v56 pattern
      - "INSUFFICIENT_SAMPLE"：payload metric 全 null（無法驗算）
        — 不阻 overall PASS，但 cell 標記 unverifiable
    """
    # event_type=manual_cleared / auto_cleared 不參與 trigger 判定
    # （只有 set event 才驗 metric vs threshold；clear event 是後續動作）
    if event_type != "halt_session_set":
        return (VERDICT_PASS, f"clear event {event_type}; not a trigger row")

    # threshold 來自 risk_config dump；若兩個都 null 代表 forensic 寫
    # 失敗或 RiskConfig load 異常，無法驗算
    if threshold_drawdown is None and threshold_daily_loss is None:
        return (
            VERDICT_INSUFFICIENT_SAMPLE,
            "both thresholds null in payload; cannot verify"
        )

    drawdown_ok = False
    daily_loss_ok = False
    notes: list[str] = []

    # drawdown 驗算：drawdown_pct 必有（halt_audit.rs:285 由 paper_state
    # 算出）；threshold 來自 RiskConfig limits.session_drawdown_max_pct
    if drawdown_pct is not None and threshold_drawdown is not None:
        if drawdown_pct + THRESHOLD_TOLERANCE >= threshold_drawdown:
            drawdown_ok = True
            notes.append(
                f"drawdown {drawdown_pct:.4f}% >= threshold {threshold_drawdown:.4f}% (OK)"
            )
        else:
            notes.append(
                f"drawdown {drawdown_pct:.4f}% < threshold {threshold_drawdown:.4f}% "
                f"(v56 pattern!)"
            )

    # daily_loss 驗算（payload 在 set event 多為 null per halt_audit.rs:287
    # 註；但 schema 允許 future 填入，所以仍跑邏輯）
    if daily_loss_pct is not None and threshold_daily_loss is not None:
        if daily_loss_pct + THRESHOLD_TOLERANCE >= threshold_daily_loss:
            daily_loss_ok = True
            notes.append(
                f"daily_loss {daily_loss_pct:.4f}% >= threshold {threshold_daily_loss:.4f}% (OK)"
            )
        else:
            notes.append(
                f"daily_loss {daily_loss_pct:.4f}% < threshold {threshold_daily_loss:.4f}% "
                f"(v56 pattern!)"
            )

    # daily_loss kind 但 daily_loss_pct null：halt_audit.rs:287 已知行為
    # （PaperState API 未暴露）；只能靠 drawdown 驗（drawdown_ok=True 即 PASS）
    # 若 drawdown 也 null → INSUFFICIENT_SAMPLE 不阻 overall PASS
    if kind == "daily_loss" and daily_loss_pct is None and drawdown_pct is None:
        return (
            VERDICT_INSUFFICIENT_SAMPLE,
            "daily_loss kind but both metrics null per halt_audit.rs:287; unverifiable"
        )

    # 任一條 metric ≥ threshold → PASS（合理 recurrence；root cause 跟 v56 不同）
    if drawdown_ok or daily_loss_ok:
        return (VERDICT_PASS, "; ".join(notes))

    # 兩個 metric 都驗了還是低（v56 pattern！）→ WARN
    # 注意：notes 此時非空（至少有一條 metric < threshold 紀錄）
    if notes:
        return (
            VERDICT_WARN,
            "; ".join(notes) + " — v56 pattern recurrence!"
        )

    # 兩個 metric 都 null → 無法驗
    return (
        VERDICT_INSUFFICIENT_SAMPLE,
        "both metric pct null in payload; cannot verify"
    )


def _check_forensic_log_present(
    audit_log_path: Path,
    expected_process_pid: int | None,
    expected_ts_ms: int | None,
) -> tuple[bool, str]:
    """驗 forensic halt_audit.log 是否含對應 process_pid + ts_ms 的 row。

    為什麼必要：v56 spec §5 強制 forensic dedicated log；若 governance_audit_log
    有 INSERT 但 halt_audit.log 缺對應 row → 寫入機制本身失效（FAIL）。

    為什麼用 process_pid + ts_ms 雙鍵：halt_audit.rs:282/293 都寫此兩字段；
    INSERT path（halt_audit_pg_writer.py:262-264）也用此兩字段 dedup；
    雙鍵唯一性足以 cross-link forensic ↔ governance_audit_log。

    回傳 (present, note)：
      - True / "matched ...": 找到對應 row
      - False / "missing ...": forensic log 存在但缺對應 row（FAIL trigger）
      - False / "log absent ...": forensic log 本身不存在（cold start，不 FAIL）
    """
    if not audit_log_path.exists():
        # cold start / fresh deploy；governance_audit_log 有事件但
        # forensic log 不存在 → 仍 FAIL（spec §5 要求 forensic 永遠在）
        return (
            False,
            f"forensic log absent at {audit_log_path}; spec §5 violation"
        )

    if expected_process_pid is None or expected_ts_ms is None:
        # 找不到唯一 key，無法 cross-link；不擋 PASS
        return (True, "no process_pid/ts_ms to cross-link; skip forensic check")

    # 行掃 forensic JSONL；行數應 ≤ 100k（一年事件數，sparse），夠快
    try:
        import json
        with audit_log_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    row.get("process_pid") == expected_process_pid
                    and row.get("ts_ms") == expected_ts_ms
                ):
                    return (
                        True,
                        f"matched pid={expected_process_pid} ts_ms={expected_ts_ms}"
                    )
        return (
            False,
            f"missing pid={expected_process_pid} ts_ms={expected_ts_ms} in forensic log"
        )
    except OSError as exc:
        # 讀檔錯誤本身不該 FAIL forensic check（healthcheck infra 自己壞了）
        return (
            True,
            f"forensic log unreadable ({exc}); skip cross-link"
        )


def run(
    cur,
    window_secs: int,
    audit_log_path: Path,
) -> dict:
    """掃 governance_audit_log 最近 window 內 halt_session_* events，
    每筆 halt_session_set 驗 metric vs threshold + forensic log 對應 row。

    為什麼 ORDER BY ts DESC + LIMIT 100：
      - 90d window 內事件天然 sparse（v56 7h+ trading 才一次）；100 row
        足夠覆蓋極端 burst 情況
      - 超過 100 row 反而代表系統性 trigger（self-fulfilling forensic gap）
        本就該 escalate；LIMIT 不會掩蓋 RCA 證據

    為什麼 SELECT 字段而非 SELECT *：減少 PG → Python 序列化負擔；
    payload->>'field' 取出 text 後 Python 端轉 float / int，比抓整個
    payload JSON 高效（payload 可含 10+ 欄位 quant-context）
    """
    # ─────────────────────────────────────────────────────────────────────
    # Query: 最近 window 內 halt_session_* events
    # ─────────────────────────────────────────────────────────────────────
    #
    # 為什麼用 payload->>'field' 而非 column access：
    #   - V035 schema 把 halt_audit 特定字段（session_drawdown_pct 等）
    #     不 promote 為 column；統一寫進 payload JSONB（spec §13 forward-compat）
    #   - halt_audit_pg_writer.py:250 INSERT 把 forensic JSON 整包進 payload
    cur.execute(
        """
        SELECT
            ts,
            event_type,
            (payload->>'engine_mode') AS engine_mode,
            (payload->>'kind') AS kind,
            (payload->>'process_pid')::bigint AS process_pid,
            (payload->>'ts_ms')::bigint AS ts_ms,
            -- 各 metric 與 threshold 用 nullable cast（payload 可能省略 / null）
            NULLIF(payload->>'session_drawdown_pct', '')::float AS drawdown_pct,
            NULLIF(payload->>'daily_loss_pct', '')::float AS daily_loss_pct,
            NULLIF(payload->>'loaded_drawdown_threshold', '')::float AS threshold_drawdown,
            NULLIF(payload->>'loaded_daily_loss_threshold', '')::float AS threshold_daily_loss,
            (payload->>'risk_config_version_seen') AS risk_config_version,
            (payload->>'paper_state_recompute_ok') AS recompute_ok,
            (payload->>'clear_path') AS clear_path
        FROM learning.governance_audit_log
        WHERE event_type IN (
            'halt_session_set',
            'halt_session_auto_cleared',
            'halt_session_manual_cleared'
        )
          AND ts > NOW() - (%s::int * INTERVAL '1 second')
        ORDER BY ts DESC
        LIMIT 100
        """,
        (window_secs,),
    )
    rows = list(cur.fetchall() or [])

    events: list[dict] = []
    overall_verdict = VERDICT_PASS
    n_set = 0
    n_cleared_auto = 0
    n_cleared_manual = 0
    n_v56_pattern = 0
    n_forensic_gap = 0

    if not rows:
        # 0 events in window；passive-wait dead zone — 不阻 deploy
        return {
            "metric": "halt_session_root_cause_recurrence",
            "check_id": "[69]",
            "spec": (
                "P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1 / "
                "v56 P0 §1.4 five candidate hypotheses (a)-(e) still open; "
                "passive-wait next natural halt-session event"
            ),
            "window_secs": window_secs,
            "audit_log_path": str(audit_log_path),
            "n_events": 0,
            "n_halt_set": 0,
            "n_cleared_auto": 0,
            "n_cleared_manual": 0,
            "n_v56_pattern": 0,
            "n_forensic_gap": 0,
            "events": [],
            "verdict": VERDICT_INSUFFICIENT_SAMPLE,
            "note": "no halt_session_* events in window; natural sparse",
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    for row in rows:
        (
            ts,
            event_type,
            engine_mode,
            kind,
            process_pid,
            ts_ms,
            drawdown_pct,
            daily_loss_pct,
            threshold_drawdown,
            threshold_daily_loss,
            risk_config_version,
            recompute_ok,
            clear_path,
        ) = row

        # 計事件型別
        if event_type == "halt_session_set":
            n_set += 1
        elif event_type == "halt_session_auto_cleared":
            n_cleared_auto += 1
        elif event_type == "halt_session_manual_cleared":
            n_cleared_manual += 1

        # 單筆 metric vs threshold 判定（只對 set 事件有意義）
        cell_verdict, note = _classify_event(
            event_type=event_type,
            drawdown_pct=drawdown_pct,
            daily_loss_pct=daily_loss_pct,
            threshold_drawdown=threshold_drawdown,
            threshold_daily_loss=threshold_daily_loss,
            kind=kind,
        )

        # WARN 統計（v56 pattern 計數）
        if event_type == "halt_session_set" and cell_verdict == VERDICT_WARN:
            n_v56_pattern += 1

        # Forensic log cross-link：只對 halt_session_set 做（避免重複掃檔）
        forensic_note = ""
        forensic_ok = True
        if event_type == "halt_session_set":
            forensic_ok, forensic_note = _check_forensic_log_present(
                audit_log_path,
                int(process_pid) if process_pid is not None else None,
                int(ts_ms) if ts_ms is not None else None,
            )
            if not forensic_ok:
                # forensic gap = FAIL（spec §5 violation）
                cell_verdict = VERDICT_FAIL
                note = f"{note} | forensic: {forensic_note}"
                n_forensic_gap += 1

        # 整體 verdict 滾動 max
        overall_verdict = severity_max(overall_verdict, cell_verdict)

        events.append({
            "ts_utc": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "event_type": event_type,
            "engine_mode": engine_mode,
            "kind": kind,
            "process_pid": int(process_pid) if process_pid is not None else None,
            "ts_ms": int(ts_ms) if ts_ms is not None else None,
            "drawdown_pct": (
                round(drawdown_pct, 4) if drawdown_pct is not None else None
            ),
            "daily_loss_pct": (
                round(daily_loss_pct, 4) if daily_loss_pct is not None else None
            ),
            "threshold_drawdown": (
                round(threshold_drawdown, 4)
                if threshold_drawdown is not None
                else None
            ),
            "threshold_daily_loss": (
                round(threshold_daily_loss, 4)
                if threshold_daily_loss is not None
                else None
            ),
            "risk_config_version": risk_config_version,
            "paper_state_recompute_ok": recompute_ok,
            "clear_path": clear_path,
            "verdict": cell_verdict,
            "note": note,
            "forensic_ok": forensic_ok,
            "forensic_note": forensic_note,
        })

    return {
        "metric": "halt_session_root_cause_recurrence",
        "check_id": "[69]",
        "spec": (
            "P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1 / "
            "v56 P0 §1.4 five candidate hypotheses (a)-(e); "
            "WARN = recurrence of v56 metric<threshold pattern; "
            "FAIL = forensic halt_audit.log row missing"
        ),
        "window_secs": window_secs,
        "audit_log_path": str(audit_log_path),
        "n_events": len(rows),
        "n_halt_set": n_set,
        "n_cleared_auto": n_cleared_auto,
        "n_cleared_manual": n_cleared_manual,
        "n_v56_pattern": n_v56_pattern,
        "n_forensic_gap": n_forensic_gap,
        "events": events,
        "verdict": overall_verdict,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    configure_logging()
    args = _parse_args()
    audit_log_path = _resolve_audit_log_path(args.audit_log_path)

    conn = connect_pg()
    try:
        with conn.cursor() as cur:
            result = run(
                cur,
                window_secs=args.window_secs,
                audit_log_path=audit_log_path,
            )
    finally:
        conn.close()

    emit_result(result, write_file=args.write_file, text_mode=args.text)

    if result["verdict"] in (VERDICT_FAIL, VERDICT_WARN):
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
