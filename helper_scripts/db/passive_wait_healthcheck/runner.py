"""Cron / CLI runner — orchestrates all checks and formats the output.
Cron / CLI runner — 編排所有 check 並格式化輸出。

MODULE_NOTE (EN): Extracted from the original ``passive_wait_healthcheck.py``
``main()`` (lines 2127-2294 in the pre-split file). Preserves the exact
invocation order, cursor lifecycle (DB checks inside the cursor block,
filesystem-only checks after ``conn.close()``), and exit-code contract:
  * 0 = all checks PASS or only WARN
  * 1 = ≥1 check FAIL
  * 2 = DB connection error

Output format also preserved byte-identical:
  - "Passive-wait healthcheck @ <ts> UTC" header
  - "=" * 70 separator
  - "{status:4s} {name:<36s} {msg}" per row
  - SUMMARY line at end

The ``--quiet`` flag skips PASS rows (operator quick-glance mode).

MODULE_NOTE (中): 從原 main() 抽出，invocation order / cursor 生命週期 /
exit code 全部 byte-identical。0 = 全 PASS/WARN、1 = ≥1 FAIL、2 = DB 連線
失敗。輸出格式與拆分前一致；--quiet 只印非 PASS 列供 operator 快速一瞥。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from .db import _get_conn
from .checks_engine import (
    check_close_fills_24h,
    check_label_backfill_ratio,
    check_exit_features_writer,
)
from .checks_ipc_edge import (
    check_phys_lock_runtime,
    check_micro_profit_fire,
    check_trailing_stop_fire,
    check_edge_estimates_freshness,
    check_shadow_exit_ratio,
    check_model_registry_freshness,
)
from .checks_strategy import (
    check_intents_writer_ratio,
    check_counterfactual_clean_window_growth,
    check_bb_breakout_post_deadlock_fix,
    check_edge_estimator_scheduler_fresh,
    check_exit_features_accumulation_rate,
    check_shadow_exit_agreement_phase2,
    check_strategist_cycle_fresh,
)
from .checks_derived import (
    check_leader_election_health,
    check_pipeline_triangulation,
    check_disabled_strategy_inventory,
)


# Module docstring used by argparse to show the original passive-wait
# healthcheck description (kept identical to the pre-split file's __doc__).
# argparse 用本字串顯示 description（與拆分前 __doc__ 一致）。
_RUNNER_DESCRIPTION = """Passive-wait pipeline healthcheck.
被動等待管線健康檢查。

Single-command check that 17+ key runtime data pipelines are actually
producing data, versus silently failing under fail-open error handling.
單命令檢查 17+ 個關鍵 runtime 資料管線實際有資料流入，
識破 fail-open 下的 silent failure。

Exit codes:
  0 = all checks PASS / only WARN
  1 = ≥1 check FAIL (pipeline silent-dead or anomalous)
  2 = DB connection error
"""


def main() -> int:
    """Entry point — runs all 19 checks and prints a structured report.

    Order is significant — the cursor block runs DB-bound checks, then we
    close the connection before invoking filesystem-only checks. Every
    check returns ``(status, msg)`` (or ``(status, msg, extra)`` for [1]
    which yields the close_fills count used by [2]/[3]/[Xb]).

    入口 — 跑全部 19 個 check 並印結構化報告。順序固定 — cursor 區塊跑
    DB 相關 check，conn.close() 之後再跑純檔案系統 check。每個 check 回
    ``(status, msg)``（[1] 額外回 close_fills，供 [2]/[3]/[Xb] 用）。
    """
    ap = argparse.ArgumentParser(description=_RUNNER_DESCRIPTION)
    ap.add_argument("--quiet", action="store_true", help="Only print non-PASS lines")
    args = ap.parse_args()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"Passive-wait healthcheck @ {now} UTC")
    print("=" * 70)

    try:
        conn = _get_conn()
    except Exception as e:
        print(f"[FATAL] DB connect failed: {e}")
        return 2

    results: list[tuple[str, str, str]] = []  # (check_name, status, msg)
    try:
        with conn.cursor() as cur:
            # [1] baseline
            s, m, close_fills = check_close_fills_24h(cur)
            results.append(("[1] close_fills_24h", s, m))

            # [2] labels
            s, m = check_label_backfill_ratio(cur, close_fills)
            results.append(("[2] label_backfill", s, m))

            # [3] exit_features writer
            s, m = check_exit_features_writer(cur, close_fills)
            results.append(("[3] exit_features_writer", s, m))

            # [4] phys_lock
            s, m = check_phys_lock_runtime(cur)
            results.append(("[4] phys_lock_runtime", s, m))

            # [5] micro_profit
            s, m = check_micro_profit_fire(cur)
            results.append(("[5] micro_profit_fire", s, m))

            # [6] trailing stop
            s, m = check_trailing_stop_fire(cur)
            results.append(("[6] trailing_stop_fire", s, m))

            # [8] shadow_exits — INFRA-PREBUILD-1 Part A
            # Runs before conn.close(); [7] (filesystem-only) runs after.
            # [8] shadow_exits — INFRA-PREBUILD-1 A 部；在 conn.close 前跑。
            s, m = check_shadow_exit_ratio(cur)
            results.append(("[8] shadow_exits_24h", s, m))

            # [9] model_registry — INFRA-PREBUILD-1 Part B
            # Phase 1a/2 expected empty; [9] turns signal once Phase 3+ lands.
            # [9] model_registry — INFRA-PREBUILD-1 B 部；Phase 1a/2 預期空。
            s, m = check_model_registry_freshness(cur)
            results.append(("[9] model_registry_freshness", s, m))

            # [10] intents_writer_ratio — P1-12 post-mortem guard
            # Catches 4/17-style whole-table intents-writer silent outage.
            # [10] intents writer 比率守衛 — P1-12 post-mortem，防 4/17 事件復發。
            s, m = check_intents_writer_ratio(cur)
            results.append(("[10] intents_writer_ratio", s, m))

            # [12] bb_breakout_post_deadlock_fix — P1-11 (1) FIX-26-DEADLOCK-1
            # Once Rust commit bcc5401 deploys via --rebuild, bb_breakout
            # should exit "permanent dormant" state. Track real fill count.
            # [12] FIX-26-DEADLOCK-1 部署後 bb_breakout 是否脫離 permanent-dormant。
            s, m = check_bb_breakout_post_deadlock_fix(cur)
            results.append(("[12] bb_breakout_post_deadlock_fix", s, m))

            # [Xb] G6-01 (2026-04-24): pipeline triangulation covers QA §2.2 #4
            # "12 檢查彼此獨立，無 fills/labels/intents 三角形驗證". Uses the
            # close_fills from [1] as baseline anchor; cross-validates against
            # labels (same filter as [2]) and intents (same filter as [10]).
            # Runs inside the cursor block because it issues DB queries.
            # [Xb] G6-01（2026-04-24）：fills/labels/intents 三角驗證，彌補 QA
            # §2.2 #4 盲點。必須在 cursor 區塊內跑（會發 SQL）。
            s, m = check_pipeline_triangulation(cur, close_fills)
            results.append(("[Xb] pipeline_triangulation", s, m))

            # [14] G6-02 (2026-04-24): exit_features weekly accumulation rate —
            # EDGE-P1b passive-wait sentinel for ML-training row growth.
            # [14] G6-02（2026-04-24）：exit_features 週環比累積速率
            # — EDGE-P1b 被動等待 ML 訓練樣本累積守衛。
            s, m = check_exit_features_accumulation_rate(cur)
            results.append(("[14] exit_features_accumulation_rate", s, m))

            # [15] G6-02 (2026-04-24): shadow exit Combine vs Physical
            # agreement — EDGE-P2 Phase 2 quality gate (≥95% strict).
            # Phase 1a dormant when shadow_enabled=false (table empty → PASS).
            # [15] G6-02（2026-04-24）：shadow exit Combine vs Physical 一致率
            # — EDGE-P2 Phase 2 品質閘（≥95% 嚴格）。Phase 1a 空表 PASS。
            s, m = check_shadow_exit_agreement_phase2(cur)
            results.append(("[15] shadow_exit_agreement_phase2", s, m))
    finally:
        conn.close()

    # [7] filesystem check
    s, m = check_edge_estimates_freshness()
    results.append(("[7] edge_estimates_freshness", s, m))

    # [13] G6-02 (2026-04-24): edge_estimator_scheduler freshness +
    # cell-count combined sentinel (G1-01 / G4-04 recovery monitoring).
    # Tighter than [7] (6h vs 90min) + (50 cells vs 10 cells); both run
    # because [7] catches steady-state hourly cadence + dormant prefix
    # breakdown, [13] catches G1-01-class scheduler outage + coverage target.
    # [13] G6-02（2026-04-24）：edge_estimator_scheduler 雙閾值哨兵
    # （G1-01 / G4-04 復原監控）。比 [7] 嚴：6h vs 90min + 50 cells vs 10。
    # 兩個並存 — [7] 抓穩態小時節奏 + dormant prefix；[13] 抓 G1-01 級停滯。
    s, m = check_edge_estimator_scheduler_fresh()
    results.append(("[13] edge_estimator_scheduler_fresh", s, m))

    # [11] EDGE-DIAG-1 Phase 3 gate (cron-driven, filesystem-only).
    # Also self-bootstraps daily snapshot history in audit/daily/.
    # [11] EDGE-DIAG-1 Phase 3 gate（cron 驅動，純檔案系統 check）。
    # 同時自 bootstrap audit/daily/ 每日快照歷史。
    s, m = check_counterfactual_clean_window_growth()
    results.append(("[11] counterfactual_clean_window_growth", s, m))

    # [Xa] G6-01 (2026-04-24): leader-lock health for edge_estimator_scheduler
    # — covers the QA-flagged blind spot where check [7] alone cannot
    # distinguish a stale-lock dead leader from a busy scheduler.
    # [Xa] G6-01（2026-04-24）：edge_estimator_scheduler leader-lock 健康 —
    # 覆蓋 QA 指出的盲點：[7] 單獨無法區分 stale-lock 死 leader vs busy scheduler。
    s, m = check_leader_election_health()
    results.append(("[Xa] leader_election_health", s, m))

    # [16] G3-11 (2026-04-25 MVP): StrategistScheduler last cycle freshness via
    # engine.log tail parse. Catches wedged scheduler invisible to "applied
    # params haven't moved" steady-state observation. Pure filesystem (no DB,
    # no IPC HMAC) so kept outside the cur block.
    # [16] G3-11（2026-04-25 MVP）：StrategistScheduler last cycle 新鮮度
    # （engine.log tail parse），抓 wedge 而 "params 沒動" 看不出來的盲點。
    s, m = check_strategist_cycle_fresh()
    results.append(("[16] strategist_cycle_fresh", s, m))

    # [18] G2-06 (2026-04-26): disabled-strategy inventory — CLAUDE.md §三
    # drift 防線 (G6-04). Pure observability, always PASS — lists strategies
    # with [<name>].active=false in strategy_params_demo.toml so future
    # audits can't forget about them.
    # [18] G2-06（2026-04-26）：disabled 策略 inventory — CLAUDE.md §三 drift
    # 防線（G6-04）。純記錄性，永遠 PASS — 列出 demo TOML 中 active=false
    # 的策略，確保未來 audit 不會「忘了還有這策略」。
    s, m = check_disabled_strategy_inventory()
    results.append(("[18] disabled_strategy_inventory", s, m))

    # output
    any_fail = False
    any_warn = False
    for name, status, msg in results:
        if args.quiet and status == "PASS":
            continue
        print(f"{status:4s} {name:<36s} {msg}")
        if status == "FAIL":
            any_fail = True
        elif status == "WARN":
            any_warn = True

    print("=" * 70)
    if any_fail:
        print("SUMMARY: FAIL — ≥1 pipeline silent-dead，查 docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md")
        return 1
    if any_warn:
        print("SUMMARY: WARN — 非致命但需關注")
        return 0
    print("SUMMARY: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
