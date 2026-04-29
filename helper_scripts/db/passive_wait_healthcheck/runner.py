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
    check_paper_state_dust_inventory,
    # F7 (2026-04-26) MIT+E5 silent-regression sentinels
    check_trading_pipeline_silent_gap,
    check_orders_fills_consistency,
    check_dust_qty_distribution,
    check_intents_counter_freeze,
    check_phantom_fills_attribution,
    check_reconciler_paper_state_divergence,
)
from .checks_ipc_edge import (
    check_phys_lock_runtime,
    check_micro_profit_fire,
    check_trailing_stop_fire,
    check_edge_estimates_freshness,
    check_shadow_exit_ratio,
    check_model_registry_freshness,
    check_edge_diag_2_strategy_diversity,
)
from .checks_strategy import (
    check_intents_writer_ratio,
    check_counterfactual_clean_window_growth,
    check_bb_breakout_post_deadlock_fix,
    check_edge_estimator_scheduler_fresh,
    check_exit_features_accumulation_rate,
    check_shadow_exit_agreement_phase2,
    check_strategist_cycle_fresh,
    # F7 (2026-04-26) MIT silent-regression sentinel
    check_signals_writer_freshness,
)
from .checks_derived import (
    check_leader_election_health,
    check_pipeline_triangulation,
    check_disabled_strategy_inventory,
    check_observer_pipeline_alive,
    check_h_state_gateway_freshness,
    # F7 (2026-04-26) ML hygiene derived sentinel
    check_dust_spiral_noise_in_ef,
)
from .checks_cost_edge import (
    # G3-09 Phase A (2026-04-27) → Phase B (2026-04-28) cost_edge_advisor sentinel
    # — extracted into sibling by HIGH-1 fix (2026-04-28) so checks_derived.py
    # stays under CLAUDE.md §九 1200-line hard cap.
    # G3-09 Phase A → Phase B cost_edge_advisor 哨兵 — HIGH-1 fix 抽至 sibling，
    # 維持 checks_derived.py 1200 行硬上限。
    check_cost_edge_advisor_status,
)
from .checks_execution import (
    check_maker_entry_intent_drift,
)


# Module docstring used by argparse to show the passive-wait healthcheck
# description. The runner is the runtime source of truth, so keep the exact
# check IDs here instead of a fragile total count.
# argparse 用本字串顯示 description。runner 是 runtime source of truth，因此
# 這裡維護實際 check ID，不維護容易 drift 的總數。
_RUNNER_DESCRIPTION = """Passive-wait pipeline healthcheck.
被動等待管線健康檢查。

Single-command check that key runtime data pipelines are actually producing
data, versus silently failing under fail-open error handling.
單命令檢查關鍵 runtime 資料管線實際有資料流入，識破 fail-open 下的
silent failure。

The checks split between DB pipelines + filesystem/observability sentinels:
  Cursor block:
    [1][2][3][4][5][6][8][9][10][12][Xb][14][15][21]      14 baseline
    [22][23][24][25][26][27][28]                          7 F7 MIT+E5
    [30][31][32]                                          cost/execution sentinels
  Post-cursor (filesystem / pure-Python):
    [7][13][11][Xa][16][18][19][20]                       8 baseline
    [29]                                                  1 F7 (no-IPC stub)

F7 sentinels [22]-[29] added 2026-04-26 by MIT DB audit + E5 engine.log dive:
  [22] trading_pipeline_silent_gap    (DCS active but fills cliff)
  [23] orders_fills_consistency       (orders writer dropping rows)
  [24] signals_writer_freshness       (4/19-style trading.signals dead writer)
  [25] dust_qty_distribution          (sub-micro qty drift = dust spiral)
  [26] dust_spiral_noise_in_ef        (ML hygiene; B1 regression)
  [27] intents_counter_freeze         (intent counter wedge)
  [28] phantom_fills_attribution      (risk_close + qty<1e-3 mis-attribute)
  [29] reconciler_paper_state_divergence (deferred-no-ipc placeholder)

Execution / cost sentinels added after F7:
  [30] cost_edge_advisor_status
  [31] edge_diag_2_strategy_diversity
  [32] maker_entry_intent_drift

Exit codes:
  0 = all checks PASS / only WARN
  1 = ≥1 check FAIL (pipeline silent-dead or anomalous)
  2 = DB connection error
"""


def main() -> int:
    """Entry point — runs all registered checks and prints a structured report.

    Order is significant — the cursor block runs DB-bound checks, then we
    close the connection before invoking filesystem-only checks. Every
    check returns ``(status, msg)`` (or ``(status, msg, extra)`` for [1]
    which yields the close_fills count used by [2]/[3]/[Xb]).

    Counted rows are documented by ID, not by fragile total:
      cursor: [1][2][3][4][5][6][8][9][10][12][Xb][14][15][21]
              [22][23][24][25][26][27][28] [30][31][32]
              (F7 [22]-[28] are MIT/E5; [30]-[32] are post-F7)
      post-cursor: [7][13][11][Xa][16][18][19][20]
                   [29]   (F7 [29] is deferred-no-ipc stub)

    入口 — 跑全部註冊 check 並印結構化報告。順序固定 — cursor 區塊跑
    DB 相關 check，conn.close() 之後再跑純檔案系統 check。每個 check 回
    ``(status, msg)``（[1] 額外回 close_fills，供 [2]/[3]/[Xb] 用）。
    清單依 ID 記錄，避免總數 drift：
      cursor: [1][2][3][4][5][6][8][9][10][12][Xb][14][15][21]
              [22][23][24][25][26][27][28] [30][31][32]
      post-cursor: [7][13][11][Xa][16][18][19][20] [29]
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
        # LOW-2 fix (2026-04-28, G3-09 Phase B Wave 1):
        # Phase A `[30]` was a filesystem-only sentinel that ran even when
        # DB connect failed. Phase B's in-cursor placement broke that —
        # DB unreachable would silently skip the env=1 invariant check.
        # Run the env-gate sentinel one more time with cur=None so the
        # OPENCLAW_COST_EDGE_ADVISOR=1 invariants (TOML + module files)
        # still fire even when DB is down. Pure filesystem path inside
        # check_cost_edge_advisor_status (Phase A code path); returns
        # PASS-skip when env != "1" so DB-down doesn't manufacture noise.
        # LOW-2 fix（2026-04-28，G3-09 Phase B Wave 1）：
        # Phase A [30] 為純檔案系統哨兵，DB connect 失敗時仍會跑。Phase B
        # 移入 cursor 區塊後，DB 不通就會靜默跳過 env=1 不變量驗證。
        # 此處以 cur=None 再呼叫 env-gate 哨兵，確保
        # OPENCLAW_COST_EDGE_ADVISOR=1 的 TOML + module 檔不變量在 DB 不通時
        # 仍生效。check_cost_edge_advisor_status Phase A 路徑為純檔案系統；
        # env != "1" 時回 PASS-skip，避免 DB-down 製造雜訊。
        print(f"[FATAL] DB connect failed: {e}")
        try:
            s, m = check_cost_edge_advisor_status(cur=None)
            print(f"{s:4s} [30] cost_edge_advisor_status (db-down fallback) {m}")
        except Exception as ce:  # noqa: BLE001 — keep DB-fail exit path robust
            print(f"WARN [30] cost_edge_advisor_status (db-down fallback) sentinel raised: {ce}")
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

            # [21] PAPER-STATE-DUST-INVENTORY-MONITOR (2026-04-26 Tier 7
            # Track 2): EXIT-FEATURES-WRITER-BUG-1-FIX (commits af48ee1 +
            # 83456e5) silent regression sentinel. Pure SELECT FROM
            # trading.fills counting last-1h `risk_close:fast_track%`
            # fills with `realized_pnl=0` + distinct-symbol fan-out;
            # three-state PASS/WARN/FAIL verdict per PA Track 3 §7.4
            # ready-to-deploy SQL (commit dd4d64a). Supersedes the
            # narrower MICRO-PROFIT-FIX-1-HEALTHCHECK backlog (MIT §6
            # follow-up #6, exact strategy_name + binary verdict).
            # Inside cursor block — pure SELECT, fail-soft on PG anomaly.
            # [21] PAPER-STATE-DUST-INVENTORY-MONITOR（2026-04-26 Tier 7
            # Track 2）：EXIT-FEATURES-WRITER-BUG-1-FIX（commits af48ee1 +
            # 83456e5）silent regression 哨兵。純 SELECT FROM trading.fills
            # 計算過去 1h `risk_close:fast_track%` 且 realized_pnl=0 的 fill
            # 計數 + distinct symbol 擴散度；三態 PASS/WARN/FAIL verdict
            # per PA Track 3 §7.4（commit dd4d64a）。Supersedes 較窄的
            # MICRO-PROFIT-FIX-1-HEALTHCHECK backlog（MIT §6 #6，
            # exact strategy_name + 二態）。在 cursor 區塊內跑 — 純 SELECT、
            # PG anomaly 時 fail-soft。
            s, m = check_paper_state_dust_inventory(cur)
            results.append(("[21] paper_state_dust_inventory", s, m))

            # ================================================================
            # F7 (2026-04-26): MIT DB audit + E5 engine.log dive — 8 new
            # silent-regression sentinels (check ids [22]-[29]). Each catches
            # a blind spot the prior 19 checks failed to alarm on. Pure SELECT
            # / pure-Python; cursor lifecycle preserved (DB checks here, then
            # filesystem checks after conn.close()). [29] is intentionally
            # filesystem-Python only (no IPC) per spec.
            # F7（2026-04-26）：MIT DB audit + E5 engine.log dive — 8 個
            # silent regression 哨兵 [22]-[29]，每個對應前 19 check 漏抓的
            # 盲點。純 SELECT / 純 Python，cursor 生命週期保持（DB 在 cursor
            # 區塊內、filesystem 在 conn.close() 後）。[29] per spec 為純
            # filesystem-Python（無 IPC）。
            # ================================================================

            # [22] trading_pipeline_silent_gap (MIT spec) — DCS active but
            # downstream fills cliff. 5-layer UNION ALL inside cursor block.
            # [22] DCS 活但下游 fill 死的 5 層 UNION ALL 對比，cursor 內。
            s, m = check_trading_pipeline_silent_gap(cur)
            results.append(("[22] trading_pipeline_silent_gap", s, m))

            # [23] orders_fills_consistency (MIT spec) — orders writer drop
            # detection (LEFT JOIN fills × orders 30min). Cursor only.
            # [23] orders writer 漏寫偵測（LEFT JOIN fills × orders 30min）。
            s, m = check_orders_fills_consistency(cur)
            results.append(("[23] orders_fills_consistency", s, m))

            # [24] signals_writer_freshness (MIT spec) — trading.signals dead
            # writer (4/19 silent outage fingerprint). Cursor only.
            # [24] trading.signals dead-writer (4/19 silent outage 指紋)。
            s, m = check_signals_writer_freshness(cur)
            results.append(("[24] signals_writer_freshness", s, m))

            # [25] dust_qty_distribution (MIT spec) — fills.qty log10-bucket
            # distribution drift toward sub-micro. Cursor only.
            # [25] fills.qty 對數桶分布往 sub-micro 漂移偵測。
            s, m = check_dust_qty_distribution(cur)
            results.append(("[25] dust_qty_distribution", s, m))

            # [26] dust_spiral_noise_in_ef (MIT spec / ML hygiene) — historical
            # noise rows + B1 regression sentinel. Cursor only.
            # [26] EF 中 dust spiral 雜訊（exit_trigger_rule + bps=-5.5 指紋）+
            # B1 regression 哨兵。
            s, m = check_dust_spiral_noise_in_ef(cur)
            results.append(("[26] dust_spiral_noise_in_ef", s, m))

            # [27] intents_counter_freeze (E5 spec) — intents counter not
            # incrementing 30+ min, per-engine_mode rollup. Cursor only.
            # [27] intents counter 30+ min 不前進，per-engine_mode 彙總。
            s, m = check_intents_counter_freeze(cur)
            results.append(("[27] intents_counter_freeze", s, m))

            # [28] phantom_fills_attribution (E5 spec) — risk_close fills
            # with sub-mililiter qty (mis-attribution fingerprint). Cursor only.
            # [28] risk_close 子-mililiter qty fill — mis-attribution 指紋。
            s, m = check_phantom_fills_attribution(cur)
            results.append(("[28] phantom_fills_attribution", s, m))

            # [30] G3-09 Phase B (2026-04-28): cost_edge_advisor env-gate +
            # RiskConfig flag + (env=1) DB freshness/trigger frequency sanity.
            # DEFAULT-OFF env=0 → PASS-skip; env=1 → verify [cost_edge] TOML
            # section + Rust module sibling files (Phase A invariants 1+2),
            # then Phase B Inv 3 (1h INSERT count) + Inv 4 (trigger frequency
            # bounds + dead-gate detection at 7d window). Moved INSIDE cursor
            # block by Phase B Wave 1 — Phase A version was filesystem-only
            # outside cursor; Phase B needs DB queries against
            # learning.cost_edge_advisor_log (V026 hypertable).
            # NOTE: PA RFC §6.2 originally proposed slot [22] (drafted before
            # F7); adjusted to [30] post-F7 landing. Slot remains [30].
            # [30] G3-09 Phase B（2026-04-28）：cost_edge_advisor env-gate +
            # RiskConfig flag + （env=1 時）DB 新鮮度 / Trigger 頻率合理性檢查。
            # env=0 → PASS-skip；env=1 → 驗 Phase A Inv 1+2（TOML + module 檔），
            # 再 Phase B Inv 3（1h INSERT 數）+ Inv 4（trigger 頻率邊界 + 7d 視窗
            # dead-gate 偵測）。Phase B Wave 1 將本 check 移至 cursor 區塊內 —
            # Phase A 版本在 cursor 外純 filesystem；Phase B 需查 V026 表。
            s, m = check_cost_edge_advisor_status(cur)
            results.append(("[30] cost_edge_advisor_status", s, m))

            # [31] EDGE-DIAG-2 (2026-04-28): demo cost_gate strategy diversity
            # sentinel. Verifies the low-sample exploration path is actually
            # unblocking non-grid strategies. Distinct strategy count in 6h
            # demo Approved verdicts: >=2 = PASS / 1 (grid-only) = WARN /
            # 0 = PASS (engine quiet). Engine-restart <30min grace period.
            # [31] EDGE-DIAG-2（2026-04-28）：demo cost_gate 策略多樣性哨兵 —
            # 驗證低樣本探索路徑確實放行非 grid 策略。6h demo Approved 中
            # distinct strategy 數：≥2 PASS / 1（grid-only）WARN / 0 PASS。
            s, m = check_edge_diag_2_strategy_diversity(cur)
            results.append(("[31] edge_diag_2_strategy_diversity", s, m))

            # [32] Runtime execution-shape drift: demo TOML maker-entry intent
            # must match recent entry intents. Uses trading.intents instead of
            # orders so intentional Market closes do not contaminate the check.
            # [32] 執行形態漂移：demo TOML maker-entry 設定須反映在近期入場
            # intents。使用 intents，避免 Market 平倉污染 orders 判讀。
            s, m = check_maker_entry_intent_drift(cur)
            results.append(("[32] maker_entry_intent_drift", s, m))
    finally:
        conn.close()

    # [29] reconciler_paper_state_divergence (E5 spec) — currently a
    # deferred-no-ipc PASS placeholder; runs AFTER conn.close() because
    # implementation is pure-Python (no DB cursor needed). Will become
    # IPC-driven once Rust handler `get_reconciler_status` is exposed.
    # [29] reconciler vs paper_state divergence — 當前為 deferred-no-ipc
    # PASS placeholder，conn.close() 後跑（純 Python，無需 cursor）。
    # Rust handler 加後升級為 IPC 驅動。
    s, m = check_reconciler_paper_state_divergence()
    results.append(("[29] reconciler_paper_state_divergence", s, m))

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

    # [19] OBSERVER-PIPELINE-POST-F42FACE-CLEANUP (2026-04-26): observer
    # cron freshness + ok ratio guard. Closes the silent-fail loophole
    # behind G9-04 (commit c7d7179) where a noise wrapper swallowed
    # 100% step failure for 3 days. Pure filesystem (mtime + JSON parse),
    # so kept outside the cursor block.
    # [19] OBSERVER-PIPELINE-POST-F42FACE-CLEANUP（2026-04-26）：observer
    # cron 新鮮度 + ok 比率守衛，閉合 G9-04 揭發的 silent-fail 漏洞
    # （noise wrapper 連續 3 天吞 100% step 失敗）。純檔案系統 check，
    # 不需 cursor。
    s, m = check_observer_pipeline_alive()
    results.append(("[19] observer_pipeline_alive", s, m))

    # [20] G3-08 Phase 1C (2026-04-26): H-state gateway env-gate + IPC route
    # + Phase 1 stub schema sentinel. DEFAULT-OFF env=0 → PASS-skip (Phase 1
    # dormant by design); env=1 → verify route registered + plumbing modules
    # importable + stub returns canonical empty shape. Pure-Python (grep
    # source + importlib), no live IPC roundtrip — keeps healthcheck
    # self-contained for cron / CI without HMAC secret coupling.
    # [20] G3-08 Phase 1C（2026-04-26）：H 狀態橋接器 env-gate + IPC route
    # + Phase 1 stub schema 哨兵。env=0 → PASS-skip（Phase 1 dormant by
    # design）；env=1 → 驗證 route 已註冊 + 線路模組可匯入 + stub 回標準
    # 空殼。純 Python（grep source + importlib），無 live IPC 來回，
    # 讓 healthcheck 自足，cron/CI 不需 HMAC secret 即可跑。
    s, m = check_h_state_gateway_freshness()
    results.append(("[20] h_state_gateway_freshness", s, m))

    # NOTE: [30] cost_edge_advisor_status moved INSIDE the cursor block by
    # G3-09 Phase B Wave 1 (2026-04-28). Phase A version was filesystem-only
    # and ran outside cursor; Phase B adds Inv 3 + Inv 4 which need DB
    # queries against learning.cost_edge_advisor_log. See cursor block above.
    # NOTE：[30] cost_edge_advisor_status 已由 G3-09 Phase B Wave 1（2026-04-28）
    # 移至 cursor 區塊內。Phase A 版本純 filesystem 在 cursor 外；Phase B
    # Inv 3+4 需查 learning.cost_edge_advisor_log，故移入。詳上方 cursor 區塊。

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
