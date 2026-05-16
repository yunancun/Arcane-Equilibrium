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
from .checks_derived_ml_hygiene import (
    # MIT W6-1 RFC SHOULD 7（2026-05-10）— `[65]` W-AUDIT-4b M3 producer
    # 接通後 chain integrity 哨兵；era filter `f.ts > '2026-05-09 09:22 UTC'`
    # 排除 pre-M3 historical artifact (3570 row orphan, 39%, producer 不存在不可修)。
    check_chain_integrity_post_audit_4b_m3,
    # W1 sub-task 3 (E1-γ, 2026-05-11) — `[66]` panel.* freshness sentinel
    # for W-AUDIT-8a Phase B Tier 2 panel collector (PanelAggregator + V085/V087)。
    # PASS_SKIP if V085/V087 not yet deployed (pre-deploy 不阻塞)。
    check_panel_freshness,
)
from .checks_feature_baseline import (
    # W-AUDIT-4b retained INSERT table readiness — `[67]` verifies
    # observability.feature_baselines active rows >0 and the 34-dim feature
    # vector contract before drift_events can mature through the burn-in gate.
    check_67_feature_baseline_readiness,
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
    check_maker_fill_rate,
    check_maker_entry_intent_drift,
    check_intent_signal_attribution,
    check_mlde_learning_data_contract,
    check_mlde_shadow_recommendations,
    check_mlde_demo_applier,
    # [38] (2026-04-29) MIT data-drift-detection: grid_trading single-position
    # lifecycle drift demo vs live_demo, passive 7d.
    # [38]（2026-04-29）MIT 資料漂移偵測：grid_trading 單倉 lifecycle 漂移
    # demo vs live_demo，被動 7d 觀察。
    check_grid_trading_lifecycle_drift,
    # [39] (2026-04-29) PA W1-T4 — cardinality regression detector for
    # trading.fills.strategy_name (post-W1-T2 normalization sentinel).
    # [39]（2026-04-29）PA W1-T4 — trading.fills.strategy_name cardinality
    # regression 偵測（W1-T2 規範化哨兵）。
    check_strategy_name_cardinality_drift,
    check_realized_edge_acceptance,
)
from .checks_scanner_market import (
    check_scanner_market_gate_confirmation,
    check_scanner_opportunity_shadow_acceptance,
)
from .checks_agent_events import (
    check_52_agent_event_store_rows,
)
from .checks_agent_spine import (
    check_55_agent_decision_spine_lineage,
)
from .checks_live_pipeline import (
    check_56_live_pipeline_active,
)
from .checks_btc_lead_lag import (
    # W2-IMPL-3 (2026-05-11) — `[57]` W2 A4-C BTC→Alt Lead-Lag panel 4 條件
    # 健康監測（PA dispatch plan §3.3：panel freshness + cohort coverage +
    # regime extreme ratio + book_imbalance 非 0 非 NULL）。Default-off
    # OPENCLAW_W2_HEALTHCHECK_ENABLED=1 opt-in；V088 未 deploy → PASS-skip。
    # OPENCLAW_W2_HEALTHCHECK_BOOK_REQUIRED=1 (W2-IMPL-1 orderbook 接線 land 後設)
    # 把 book_imb_avg=0/NULL 升 FAIL；W2-IMPL-1 land 前維持 WARN。
    check_57_btc_lead_lag_panel_health,
)
from .checks_openclaw_gateway import (
    check_54_openclaw_proposal_relay,
)
from .checks_governance import (
    # LG-5-IMPL-3 (2026-05-02) — RFC v2 §6 governance contract sentinels.
    # `[42]` review_live_candidate 1h SLA + audit row contract;
    # `[42b]` per-strategy 7d attribution_chain_ratio drift detector
    # (RFC §3 R-meta + §4 lease_revoke_trigger + MIT MF-M5).
    # LG-5-IMPL-3（2026-05-02）— RFC v2 §6 治理契約哨兵。
    # `[42]` review_live_candidate 1h SLA + audit row 契約；
    # `[42b]` per-strategy 7d attribution_chain_ratio 漂移偵測。
    check_42_live_candidate_eval_contract,
    check_42b_live_candidate_attribution_drift,
    # LG5-W3-FUP-2 Fix 2 (2026-05-02 RFC §5 Plan B) — `[42c]` 3d
    # gate-aligned mirror of `[42b]` (identical thresholds, 3d window).
    # Pairs with producer Fix 2 IMPL-1 (`_R_META_WINDOW_DAYS = 3` in
    # `mlde_demo_applier`); `[42b]` keeps 7d for long-window observability.
    # LG5-W3-FUP-2 Fix 2（2026-05-02 RFC §5 方案 B）— `[42c]` `[42b]` 的
    # R-meta gate 對齊 3d 鏡像（閾值一致、window 改 3d）。配對 producer
    # Fix 2 IMPL-1 (`_R_META_WINDOW_DAYS = 3`)；`[42b]` 保 7d 作 long-window。
    check_42c_live_candidate_attribution_drift_3d,
    # LG5-W3-FUP-2 Fix 1 (2026-05-02) — `[43]` label backfill cron liveness
    # sentinel (max(label_filled_at) freshness for demo+live_demo). Pairs
    # with helper_scripts/cron/edge_label_backfill_cron.sh per CLAUDE.md §七
    # 「被動等待 TODO 必附 healthcheck」requirement.
    # LG5-W3-FUP-2 Fix 1（2026-05-02）— `[43]` label backfill cron 活性哨兵
    # （demo+live_demo max(label_filled_at) 新鮮度）。與
    # helper_scripts/cron/edge_label_backfill_cron.sh 配對，符合 CLAUDE.md §七
    # 「被動等待 TODO 必附 healthcheck」要求。
    check_43_label_backfill_freshness,
    # REF-20 Sprint 1 Track B (2026-05-03) — `[44]` replay manifest sibling
    # key.hex presence sentinel. PA push back #3 — Track B closes E3-P0-1
    # fail-open by hard-erroring on key.hex absence at startup; this check
    # surfaces in-flight runs that may pre-date Track B deploy. WARN-only
    # transitional gate (V042 SQL-backed archive at Wave 6+ supersedes).
    # REF-20 Sprint 1 Track B（2026-05-03）— `[44]` replay manifest sibling
    # key.hex 存在性哨兵。PA push back #3 — Track B 把 key.hex 缺改 hard
    # error 封閉 E3-P0-1 fail-open；本 check surface 可能 pre-date Track B
    # 部署的 in-flight run。WARN-only 過渡 gate（V042 SQL-backed archive
    # 於 Wave 6+ land 後取代）。
    check_44_replay_manifest_key_presence,
    # W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1（2026-05-10 Sprint N+1）— `[64]`
    # unblock_candidates_drift sentinel。spec §6.2 4 sub-check：
    # (1) stale candidate >14d 無 sign-off → WARN
    # (2) yo-yo detection 30d 內 unfrozen+re_frozen 後新 candidate → FAIL
    # (3) sign-off completeness violation（V090 PG CHECK sentinel of
    #     sentinel）→ FAIL
    # (4) unfrozen rows count（freeze.json sync surrogate）。
    # 配對 writer: helper_scripts/db/audit/blocked_symbols_30d_unblock_check.py
    # 配對 V090: governance.unblock_candidates。
    check_64_unblock_candidates_drift,
)
from .checks_pricing_binding import (
    # REF-20 Sprint C R6-T7 (2026-05-05) — `[45]` LG-3 provider pricing
    # binding sentinel. Implements RFC §IMPL T2 healthcheck output
    # (`docs/CCAgentWorkSpace/PA/.../2026-05-01--lg3_provider_pricing_binding_rfc.md`).
    # PG-side proxy of Rust ``AccountManager`` runtime fee health via 24h
    # trading.fills.fee_rate distribution + last-ts staleness. Unblocks
    # LG-3 RFC closure 0% → 70% (T1 contract test deferred to Sprint D;
    # T3 startup assertion deferred to LG-4 IMPL pre-req).
    # REF-20 Sprint C R6-T7（2026-05-05）— `[45]` LG-3 提供者定價綁定哨兵
    # （RFC §IMPL T2）。PG 端 proxy 映射 Rust AccountManager 運行時 fee
    # 健康（24h trading.fills.fee_rate 分佈 + 末條 ts staleness）。
    # 解封 LG-3 RFC closure 0% → 70%（T1 contract test 留 Sprint D；
    # T3 startup assertion 留 LG-4 IMPL 前提）。
    check_45_pricing_binding,
)
from .checks_replay_maintenance import (
    # REF-20 Sprint D R8 (2026-05-05) — `[46]`-`[50]` maintenance / observation
    # sentinel suite per plan §6.R8 task 2, plus REF-21 `[53]` universe recorder.
    # [46] V056 retention cron 活性 + replay-derived candidate cap
    # [47] Linux replay_runner binary presence + executable bit
    # [48] replay.experiments row growth rate stall detection
    # [49] V046 replay.report_artifacts oldest age + storage cap dual check
    # [50] V045 replay.run_state failed rate + zombie 'running' detection
    # REF-20 Sprint D R8（2026-05-05）— `[46]`-`[50]` maintenance / observation
    # 哨兵套組（plan §6.R8 task 2），並追加 REF-21 `[53]` universe recorder。
    check_46_mlde_shadow_retention_status,
    check_47_replay_runner_binary,
    check_48_replay_manifest_registry_growth,
    check_49_replay_artifact_retention,
    check_50_replay_run_state_health,
    check_53_ref21_v058_symbol_universe_recorder,
)
from .checks_canary_stage_invariant import (
    # W-AUDIT-9 T4 (2026-05-09) — `[58]` graduated canary stage invariant
    # sentinel per AMD-2026-05-09-03 §4.1. Reads V080 governance.canary_stage_log
    # + governance.canary_stage_metric_registry, evaluates 5 invariants per
    # active cohort (metric registry presence x2, rollback trip detection,
    # observation period consistency, cohort scope rules), plus invariant 11
    # (manual_promote NOT NULL lease — V080 PG CHECK should block, observed
    # for partial-rollout drift) and invariant 12 (SM-04 >= L3 escalate must
    # auto-rollback all cohorts to Stage 0).
    # W-AUDIT-9 T4（2026-05-09）— `[58]` 漸進式 canary stage 不變式哨兵（AMD
    # §4.1）。讀 V080 兩表，對 active cohort 評估 5 不變式（metric registry
    # 存在 x2 / rollback trip / observation 期 / cohort 規範），加 invariant
    # 11（manual_promote NOT NULL lease，V080 PG CHECK 應擋，仍觀察 partial
    # rollout drift）與 invariant 12（SM-04 ≥ L3 escalate 必觸 stage 0
    # rollback）。
    check_58_graduated_canary_stage_invariant,
)
from .checks_canary_stage_criteria import (
    # W5-E1-A P1-CANARY-STAGE-CRITERIA-1 (2026-05-10) — `[58a]` enrich evidence
    # collection per spec §7.4. Reads V089 governance.canary_stage_metric_registry
    # seed and reports per-stage metric coverage + active cohort metric set
    # (promote / rollback row counts). Verdict-preserving: WARN on V089 seed
    # drift (per stage row count below EXPECTED), PASS on full seed. Evidence
    # only — actual cohort metric value computation deferred to W3 cohort SQL
    # pipeline land. Spec source:
    # docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md §7.4.
    # W5-E1-A（2026-05-10）— `[58a]` 補強證據收集（spec §7.4）。讀 V089 metric
    # registry seed 報告每 stage metric 覆蓋率 + active cohort 對應 metric set；
    # WARN-only verdict（不 hard FAIL,避免阻塞 silent-dead 偵測）。實際 cohort
    # metric 值計算等 W3 cohort SQL pipeline land 後 enrich。
    check_58a_stage_criteria_eval,
)
from .checks_h0_block_acceptance import (
    # LG1-T2 (2026-05-11) — `[59]` H0 hard-block production caller acceptance
    # sentinel per PA tech plan `2026-05-11--lg_2_3_4_design_plan.md` §1.4 T2.
    # 讀 ``pipeline_snapshot_{demo,live_demo}.json`` 的 `h0_gate_stats` 與
    # `risk_manager_config.runtime.h0_shadow_mode`,並跨檢 ``trading.fills``
    # 1h 入場 fill 計數,推斷 H0 hard-block 是否真實生效:
    #   PASS:  shadow=false + 充足樣本 + 無 block leakage
    #   WARN:  shadow_mode=true / 低樣本 / snapshot stale / pipeline quiet
    #   FAIL:  block dominant 但 entry fills > 0(block invariant 失效)
    # OPENCLAW_H0_BLOCK_HEALTH_REQUIRED=1 升 WARN → FAIL。
    # LG1-T2(2026-05-11)— `[59]` H0 hard-block 生產調用驗收哨兵
    # (PA tech plan §1.4 T2)。哨兵讀 snapshot.h0_gate_stats + h0_shadow_mode
    # 並跨檢 trading.fills 1h entry fills 推斷 hard-block 失效。
    check_59_h0_block_acceptance,
)
from .checks_portfolio_resting_exposure import (
    # P2-PORTFOLIO-RESTING-58-HEALTHCHECK（2026-05-16 P1-PORTFOLIO-RESTING-
    # EXPOSURE-1 commit `9980448a` follow-up; 升 P1 per FA verdict Stage 1
    # demo 啟前 mandatory）— resting maker exposure lineage 哨兵。配對 Rust
    # IMPL 把 ``resting_limit_orders`` 納入 ``compute_effective_long_short_notional``
    # SoT helper；本 check 監控 effective（filled+resting）vs filled-only
    # leverage chain semantic drift magnitude（A3 WARN-1 + E2 LOW-1 + PA
    # F-FA-2 §8）。
    # ID 註：PA spec / TODO row 標 ``[58]`` 但 ``[58]`` 已被 W-AUDIT-9 T4
    # ``graduated_canary_stage_invariant`` 占用，本 check 取下一自由 slot
    # ``[68]``；name ``portfolio_resting_exposure_lineage`` 保留。
    # Default-off escalation：OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED=1
    # 升 WARN → FAIL；OPENCLAW_PORTFOLIO_RESTING_LOOKBACK_HOURS=N 改視窗
    # （default 24h）。
    check_68_portfolio_resting_exposure,
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
    [30][31][32][33][34][35][36][37][38][39][40][41]      cost/execution/MLDE/lifecycle/cardinality/acceptance/scanner evidence
    [42][42b][42c][43][44][45]                             LG-5 governance contract + per-strategy attribution drift (7d + 3d gate-aligned) + label-backfill cron liveness + REF-20 replay manifest key.hex presence + LG-3 provider pricing binding
    [46][48][49][50][51][52][53][54][55][57][58][59][64][65][66][67][68]    REF-20 Sprint D R8 maintenance suite + scanner opportunity shadow acceptance + agent event-store row proof + REF-21 V058 universe recorder + OpenClaw proposal relay + Agent Decision Spine lineage + W2-IMPL-3 BTC→Alt Lead-Lag panel 4 conditions + W-AUDIT-9 T4 graduated canary stage invariant + LG1-T2 H0 block acceptance + W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1 unblock_candidates_drift + MIT W6-1 RFC SHOULD 7 W-AUDIT-4b M3 chain integrity + W1 panel freshness + W-AUDIT-4b feature baseline readiness + P2-PORTFOLIO-RESTING-58-HEALTHCHECK portfolio resting exposure lineage
  Post-cursor (filesystem / pure-Python):
    [7][13][11][Xa][16][18][19][20]                       8 baseline
    [29]                                                  1 F7 (no-IPC stub)
    [47]                                                  REF-20 Sprint D R8 — replay_runner binary presence (filesystem)
    [56]                                                  Live / LiveDemo pipeline active sentinel (filesystem)

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
  [33] maker_fill_rate                 (G2-01 PostOnly fee-drop monitor)
  [34] intent_signal_attribution       (strategy signal_id join chain)
  [35] mlde_learning_data_contract     (attributed post-fee training rows)
  [36] mlde_shadow_recommendations     (advisory/live lease boundary)
  [37] mlde_demo_applier               (demo autonomy audit + live lease boundary)
  [38] grid_trading_lifecycle_drift    (MIT 2026-04-29 demo vs live_demo passive 7d)
  [39] strategy_name_cardinality_drift (PA W1-T4 2026-04-29 post-normalization sentinel)
  [40] realized_edge_acceptance        (DB-truth post-fee profitability acceptance)
  [41] scanner_market_gate_confirmation (legacy scanner would-block evidence calibration; WARN-only after scanner authority retirement)
  [42] live_candidate_eval_contract    (LG-5-IMPL-3 2026-05-02 review_live_candidate 1h SLA + audit row)
  [42b] live_candidate_attribution_drift (LG-5-IMPL-3 2026-05-02 per-strategy 7d ratio drift)
  [42c] live_candidate_attribution_drift_3d (LG5-W3-FUP-2 Fix 2 2026-05-02 RFC §5 Plan B — gate-aligned 3d mirror of [42b])
  [43] label_backfill_freshness         (LG5-W3-FUP-2 Fix 1 2026-05-02 max(label_filled_at) age — cron liveness)
  [44] replay_manifest_key_presence     (REF-20 Sprint 1 Track B 2026-05-03 PA push back #3 — key.hex sibling presence; WARN-only until V042 Wave 6+)
  [45] pricing_binding                  (REF-20 Sprint C R6-T7 2026-05-05 — LG-3 RFC §IMPL T2 PG proxy of Rust AccountManager fee health; closes RFC 0%→70%, T1+T3 deferred Sprint D / LG-4)
  [46] mlde_shadow_retention_status     (REF-20 Sprint D R8 2026-05-05 — V056 retention cron 活性 + replay-derived candidate row cap dual probe)
  [47] replay_runner_binary             (REF-20 Sprint D R8 2026-05-05 — Linux replay_runner binary presence + executable bit; filesystem)
  [48] replay_manifest_registry_growth  (REF-20 Sprint D R8 2026-05-05 — replay.experiments row growth rate stall detection)
  [49] replay_artifact_retention        (REF-20 Sprint D R8 2026-05-05 — V046 oldest age + storage cap dual check vs replay_artifact_prune.py cron)
  [50] replay_run_state_health          (REF-20 Sprint D R8 2026-05-05 — V045 failed_rate 7d + zombie 'running' >1h detection)
  [51] scanner_opportunity_shadow_acceptance (2026-05-06 — snapshot/intent/MLDE row-proof coverage + opportunity_lcb_bps calibration, shadow-only)
  [52] agent_event_store_rows            (AgentTodo MAG-010..012 — agent.messages/state_changes/ai_invocations recent row proof)
  [54] openclaw_proposal_relay           (OC-GW-5/6/7 proposal/approval/channel ledger audit)
  [53] ref21_v058_symbol_universe_recorder (REF-21 — recurring V058 universe snapshot liveness)
  [55] agent_decision_spine_lineage       (P1-AGENT-OBS-1 — MAG-082 lineage readiness)
  [56] live_pipeline_active               (P0-NEW-ISSUE-1 — live slot configured but LiveDemo not spawned)
  [57] btc_lead_lag_panel_health          (W2-IMPL-3 — W2 A4-C BTC→Alt Lead-Lag panel 4 conditions: freshness < 120s + cohort=7 + regime extreme < 5% + book_imbalance non-zero/non-null; default-off OPENCLAW_W2_HEALTHCHECK_ENABLED=1 opt-in)
  [58] graduated_canary_stage_invariant   (W-AUDIT-9 T4 — AMD-2026-05-09-03 §4.1 5-stage state-machine invariant; SM-04 ≥ L3 escalate hard FAIL → triggers stage 0 rollback per invariant 12)
  [59] h0_block_acceptance                (LG1-T2 — PA tech plan §1.4 T2 H0 hard-block production caller acceptance; reads pipeline_snapshot_{demo,live_demo}.json h0_gate_stats + risk_manager_config.runtime.h0_shadow_mode, cross-joins trading.fills 1h entry fills; 4 sub-check: snapshot fresh / shadow_mode / sample size / block leakage; OPENCLAW_H0_BLOCK_HEALTH_REQUIRED=1 escalates WARN→FAIL)
  [64] unblock_candidates_drift           (W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1 2026-05-10 Sprint N+1 — spec §6.2 4 sub-check: stale candidate / yo-yo detection / sign-off completeness / unfrozen rows count; pairs with V090 governance.unblock_candidates + 30d cycle writer)
  [65] chain_integrity_post_audit_4b_m3   (MIT W6-1 RFC SHOULD 7 2026-05-10 — W-AUDIT-4b M3 producer post-deploy chain integrity sentinel; era filter `f.ts > '2026-05-09 09:22 UTC'` excludes pre-M3 historical orphan; PASS ≥ 95% / WARN 80-95% / FAIL < 80% / WARN_LOW_SAMPLE n<30; per-strategy drill-down annotation)
  [66] panel_freshness                     (W1 sub-task 3 — panel.funding_rates_panel + panel.oi_delta_panel freshness)
  [67] feature_baseline_readiness          (W-AUDIT-4b retained INSERT table readiness — active feature_baselines >0 + 34-dim vector contract; drift_events burn-in remains intact)
  [68] portfolio_resting_exposure_lineage  (P2-PORTFOLIO-RESTING-58-HEALTHCHECK 2026-05-16 P1-PORTFOLIO-RESTING-EXPOSURE-1 follow-up; 升 P1 per FA Stage 1 demo 啟前 mandatory; 監測 effective(filled+resting) vs filled-only leverage chain semantic drift; per engine 4 sub-check: long/short notional vs cap × {80%,100%} + divergence vs {50%,100%} + per-symbol resting/filled vs {80%,150%}; OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED=1 escalates WARN→FAIL; ID note: PA spec/TODO 標 [58] 但 [58]=W-AUDIT-9 T4 已占用，取 [68] free slot, name preserved)

Exit codes:
  0 = all checks PASS / only WARN
  1 = ≥1 check FAIL (silent-dead, drift, or anomalous)
  2 = DB connection error
"""


def _normalize_check_id(value: str) -> str:
    """Normalize CLI check selectors like '[4]', '4', '[Xb]', or 'xb'."""
    return value.strip().strip("[]").lower()


def _emit_results(results: list[tuple[str, str, str]], quiet: bool) -> int:
    """Print healthcheck rows and return the standard passive-check exit code."""
    any_fail = False
    any_warn = False
    for name, status, msg in results:
        if quiet and status == "PASS":
            continue
        print(f"{status:4s} {name:<36s} {msg}")
        if status == "FAIL":
            any_fail = True
        elif status == "WARN":
            any_warn = True

    print("=" * 70)
    if any_fail:
        print("SUMMARY: FAIL — ≥1 healthcheck failed（silent-dead / drift / regression）；先看上方 FAIL 行定位")
        return 1
    if any_warn:
        print("SUMMARY: WARN — 非致命但需關注")
        return 0
    print("SUMMARY: ALL PASS")
    return 0


def _run_selected_cursor_checks(
    cur,
    selected: set[str],
) -> list[tuple[str, str, str]]:
    """Run the narrow DB-bound subset requested by ``--check``.

    Dependencies may run silently. In particular, [Xb] needs [1]'s
    ``close_fills`` baseline even when [1] was not selected.
    """
    supported = {"1", "4", "xb"}
    unsupported = sorted(selected - supported)
    if unsupported:
        supported_display = ", ".join(f"[{x}]" if x != "xb" else "[Xb]" for x in sorted(supported))
        raise ValueError(
            "unsupported --check selector(s): "
            + ", ".join(unsupported)
            + f"; supported narrow selectors: {supported_display}"
        )

    results: list[tuple[str, str, str]] = []
    close_fills: int | None = None
    if "1" in selected or "xb" in selected:
        s, m, close_fills = check_close_fills_24h(cur)
        if "1" in selected:
            results.append(("[1] close_fills_24h", s, m))

    if "4" in selected:
        s, m = check_phys_lock_runtime(cur)
        results.append(("[4] phys_lock_runtime", s, m))

    if "xb" in selected:
        if close_fills is None:
            s, m, close_fills = check_close_fills_24h(cur)
        s, m = check_pipeline_triangulation(cur, close_fills)
        results.append(("[Xb] pipeline_triangulation", s, m))

    return results


def main() -> int:
    """Entry point — runs all registered checks and prints a structured report.

    Order is significant — the cursor block runs DB-bound checks, then we
    close the connection before invoking filesystem-only checks. Every
    check returns ``(status, msg)`` (or ``(status, msg, extra)`` for [1]
    which yields the close_fills count used by [2]/[3]/[Xb]).

    Counted rows are documented by ID, not by fragile total:
      cursor: [1][2][3][4][5][6][8][9][10][12][Xb][14][15][21]
              [22][23][24][25][26][27][28] [30][31][32][33][34][35][36][37][38][39][40][41]
              [42][42b][42c][43][44][45]
              [46][48][49][50][51][52][53][54][55][57][58][59][64][65][66][67][68]
              (F7 [22]-[28] are MIT/E5; [30]-[37] are post-F7/MLDE;
               [38] is MIT 2026-04-29 grid lifecycle drift;
               [39] is PA W1-T4 2026-04-29 strategy_name cardinality drift;
               [40] is DB-truth realized edge acceptance;
               [41] is scanner legacy would-block evidence calibration;
               [42]/[42b] are LG-5-IMPL-3 governance contract + attribution drift;
               [42c] is LG5-W3-FUP-2 Fix 2 RFC §5 Plan B — gate-aligned 3d mirror of [42b];
               [43] is LG5-W3-FUP-2 Fix 1 label-backfill cron liveness;
               [44] is REF-20 Sprint 1 Track B replay manifest key.hex presence;
               [45] is REF-20 Sprint C R6-T7 LG-3 provider pricing binding;
               [46]-[50] are REF-20 Sprint D R8 maintenance suite —
               [46] mlde_shadow retention cron + candidate cap;
               [47] post-cursor — replay_runner binary filesystem;
               [48] manifest registry growth stall;
               [49] V046 artifact retention dual-check;
               [50] V045 run_state health failed_rate + zombie;
               [51] scanner opportunity shadow acceptance;
               [52] agent event-store row proof;
               [53] REF-21 V058 universe recorder;
               [54] OpenClaw proposal relay;
               [55] Agent Decision Spine MAG-082 lineage readiness;
               [57] W2-IMPL-3 BTC→Alt Lead-Lag panel 4 conditions (freshness/cohort/regime/book_imb);
               [58] W-AUDIT-9 T4 graduated canary stage invariant — AMD-2026-05-09-03 §4.1;
               [59] LG1-T2 H0 hard-block production caller acceptance — PA tech plan §1.4 T2;
               [64] W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1 unblock_candidates_drift — spec §6.2 4 sub-check;
               [65] MIT W6-1 RFC SHOULD 7 W-AUDIT-4b M3 chain integrity — era filter post 2026-05-09 09:22 UTC;
               [66] W1 panel_freshness; [67] W-AUDIT-4b feature_baseline_readiness;
               [68] P2-PORTFOLIO-RESTING-58-HEALTHCHECK portfolio_resting_exposure_lineage —
                    P1-PORTFOLIO-RESTING-EXPOSURE-1 follow-up; 升 P1 Stage 1 demo 啟前 mandatory)
      post-cursor: [7][13][11][Xa][16][18][19][20]
                   [29]   (F7 [29] is deferred-no-ipc stub)
                   [47]   (REF-20 Sprint D R8 replay_runner binary filesystem)
                   [56]   (P0-NEW-ISSUE-1 live pipeline active filesystem)

    入口 — 跑全部註冊 check 並印結構化報告。順序固定 — cursor 區塊跑
    DB 相關 check，conn.close() 之後再跑純檔案系統 check。每個 check 回
    ``(status, msg)``（[1] 額外回 close_fills，供 [2]/[3]/[Xb] 用）。
    清單依 ID 記錄，避免總數 drift：
      cursor: [1][2][3][4][5][6][8][9][10][12][Xb][14][15][21]
              [22][23][24][25][26][27][28] [30][31][32][33][34][35][36][37][38][39][40][41]
              [42][42b][42c][43][44][45] [46][48][49][50][51][52][53][54][55][57][58][58a][59][64][65][66][67][68]
      post-cursor: [7][13][11][Xa][16][18][19][20] [29] [47] [56]
    """
    ap = argparse.ArgumentParser(description=_RUNNER_DESCRIPTION)
    ap.add_argument("--quiet", action="store_true", help="Only print non-PASS lines")
    ap.add_argument(
        "--check",
        action="append",
        default=[],
        metavar="ID",
        help=(
            "Run a narrow check subset by id, e.g. --check [4] --check [Xb]. "
            "Dependencies may run silently."
        ),
    )
    args = ap.parse_args()
    selected_checks = {_normalize_check_id(v) for v in args.check}

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

    if selected_checks:
        try:
            with conn.cursor() as cur:
                selected_results = _run_selected_cursor_checks(cur, selected_checks)
        except ValueError as e:
            conn.close()
            print(f"[FATAL] {e}")
            print("=" * 70)
            print("SUMMARY: FAIL — invalid --check selector")
            return 1
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return _emit_results(selected_results, args.quiet)

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

            # [33] G2-01 PostOnly settlement monitor: 7d demo/live_demo
            # entry fills should show fee-drop from taker 5.5bps toward
            # maker 2.0bps. Joins orders only for limit diagnostics because
            # the current Rust order writer does not persist time_in_force.
            # [33] G2-01 PostOnly 結算監控：7d demo/live_demo 入場 fills
            # 應呈現 5.5bps taker → 2.0bps maker 的有效降費。orders join
            # 僅作 Limit 診斷，因目前 Rust orders writer 未持久化 TIF。
            s, m = check_maker_fill_rate(cur)
            results.append(("[33] maker_fill_rate", s, m))

            # [34] Intent attribution chain: exchange intents must carry a
            # non-empty signal_id that joins to trading.signals on the same
            # context_id. Catches demo/live_demo signal_id regressions.
            # [34] Intent 歸因鏈：exchange intents 必須帶非空 signal_id 且能
            # join 到同 context_id 的 trading.signals。
            s, m = check_intent_signal_attribution(cur)
            results.append(("[34] intent_signal_attribution", s, m))

            # [35] MLDE learning data contract: training rows must carry the
            # repaired attribution chain plus post-fee reward and 8-dim LinUCB
            # context. Zero rows WARN during first deployment window.
            # [35] MLDE 訓練資料契約：需有修復後 attribution chain、扣費後
            # reward、8 維 LinUCB context。首次部署前期 0 row 只 WARN。
            s, m = check_mlde_learning_data_contract(cur)
            results.append(("[35] mlde_learning_data_contract", s, m))

            # [36] MLDE advisory/live boundary: shadow recommendations may be
            # logged, but live/live_demo applied rows must carry Decision Lease.
            # [36] MLDE advisory/live 邊界：可寫 shadow 建議，但 live/live_demo
            # applied row 必須有 Decision Lease。
            s, m = check_mlde_shadow_recommendations(cur)
            results.append(("[36] mlde_shadow_recommendations", s, m))

            # [37] MLDE demo autonomous applier: demo may apply bounded
            # strategy/risk changes, while live/live_demo remains lease-gated.
            # [37] MLDE demo 自主調參：demo 可 bounded apply，live/live_demo
            # 仍需 Decision Lease。
            s, m = check_mlde_demo_applier(cur)
            results.append(("[37] mlde_demo_applier", s, m))

            # [38] grid_trading lifecycle drift between demo / live_demo
            # (MIT 2026-04-29). Passive 7d observation per CLAUDE.md §七
            # requirement; PASS until clear evidence of grid out-of-control
            # behavior in live_demo. Three indicators tagged independently
            # (lifetime ratio / fee burn / re-entry rate); final verdict =
            # max severity. DB unreachable / 0 rows → WARN/PASS, never FAIL.
            # [38] grid_trading demo vs live_demo lifecycle 漂移；被動 7d
            # 觀察。三指標獨立標記（lifetime / fee burn / re-entry），最終
            # verdict 取最高嚴重度。低活動期 PASS-with-note 不假警報。
            s, m = check_grid_trading_lifecycle_drift(cur)
            results.append(("[38] grid_trading_lifecycle_drift", s, m))

            # [39] PA W1-T4 (2026-04-29) strategy_name cardinality regression.
            # Pre-W1-T2 close path emitted dynamic format!() into strategy_name
            # creating 25+ distinct values per 24h. Post-W1-T2 normalized to ≤7
            # enum-like values. FAIL when 24h distinct > 20 = emit point regressed
            # to dynamic strategy_name. cron 6h auto-catches before downstream ML
            # pipeline / agent-tracker / 7d edge effect endpoint get polluted.
            # First-run verdict (W1-T2 not yet deployed): FAIL — historical 24h
            # window still shows ~25 distinct dynamic format strings; expected to
            # drop to PASS within 24h after W1-T2 + restart_all --rebuild.
            # [39] PA W1-T4（2026-04-29）strategy_name cardinality regression
            # 偵測。修前 close path 寫 dynamic format 進 strategy_name 造成 24h
            # 25+ distinct；W1-T2 後規範化 ≤7 enum-like value。24h distinct >20
            # 即 FAIL（emit 點 regress）。cron 6h auto-catch 防 ML pipeline /
            # agent-tracker / 7d edge effect 端點污染。首跑 verdict（W1-T2 未
            # deploy）：FAIL — 歷史 24h window 仍含 25 個 dynamic format 字串；
            # W1-T2 + --rebuild 後 24h 內降回 PASS。
            s, m = check_strategy_name_cardinality_drift(cur)
            results.append(("[39] strategy_name_cardinality_drift", s, m))

            # [40] DB-truth profitability acceptance: post-fee MLDE avg edge,
            # negative active cells, and maker fee-drop targets.
            s, m = check_realized_edge_acceptance(cur)
            results.append(("[40] realized_edge_acceptance", s, m))

            # [41] Scanner market judgement confirmation: cells blocked by
            # market_gate / early negative-edge quarantine should later score
            # negative post-fee when labels are available.
            s, m = check_scanner_market_gate_confirmation(cur)
            results.append(("[41] scanner_market_gate_confirmation", s, m))

            # [42] LG-5-IMPL-3 (2026-05-02): live_candidate_eval_contract —
            # every >1h-old live candidate must have a `review_live_candidate`
            # audit row in `learning.governance_audit_log`. Catches
            # GovernanceHub silent failure where IMPL-1 inserts candidate rows
            # but IMPL-2 consumer never fires a verdict (RFC v2 §6 line 451-454,
            # §4 lease_revoke_trigger line 404). Pure SELECT inside cursor.
            # [42] LG-5-IMPL-3（2026-05-02）：live_candidate_eval_contract —
            # 每個 >1h 老的 live candidate 必須有 `review_live_candidate` audit
            # row。捕捉 IMPL-1 寫 candidate 但 IMPL-2 從未審查的 GovernanceHub
            # 靜默失敗（RFC v2 §6 line 451-454，§4 lease_revoke_trigger）。
            s, m = check_42_live_candidate_eval_contract(cur)
            results.append(("[42] live_candidate_eval_contract", s, m))

            # [42b] LG-5-IMPL-3 (2026-05-02): per-strategy 7d
            # attribution_chain_ok ratio drift for the 5 LG-5 strategies.
            # PASS ≥ 0.50 (RFC §3 R-meta floor) / WARN [0.10, 0.50) /
            # FAIL < 0.10 (pipeline-level alert + lease_revoke_trigger,
            # RFC §4 line 405 + MIT MF-M5 cross-ref). Pure SELECT.
            # [42b] LG-5-IMPL-3（2026-05-02）：5 個 LG-5 strategy 的 7d
            # attribution_chain_ok ratio 漂移偵測。PASS ≥ 0.50 / WARN
            # [0.10, 0.50) / FAIL < 0.10（pipeline-level alert +
            # lease_revoke_trigger）。純 SELECT。
            s, m = check_42b_live_candidate_attribution_drift(cur)
            results.append(("[42b] live_candidate_attribution_drift", s, m))

            # [42c] LG5-W3-FUP-2 Fix 2 (2026-05-02 RFC §5 Plan B):
            # gate-aligned 3d mirror of [42b]. Identical SQL shape /
            # engine_mode filter / threshold bands (0.50 / 0.30 / 0.10),
            # only window differs: 3d instead of 7d, aligning with producer
            # `mlde_demo_applier._R_META_WINDOW_DAYS = 3` shipped by Fix 2
            # IMPL-1. Operator interpretation matrix (per docstring):
            #   * [42b] PASS + [42c] PASS → R-meta healthy long+short
            #   * [42b] PASS + [42c] WARN → 4/24-28 bug residual fading;
            #     R-meta defer working as intended
            #   * [42b] FAIL + [42c] PASS → bug fixed, 7d will converge
            #   * [42b] FAIL + [42c] FAIL → real production drift
            # Pure SELECT inside cursor block.
            # [42c] LG5-W3-FUP-2 Fix 2（2026-05-02 RFC §5 方案 B）：
            # [42b] 的 R-meta gate 對齊 3d 鏡像。SQL 結構 / engine_mode
            # filter / 閾值（0.50 / 0.30 / 0.10）完全一致，window 改 3d，
            # 對齊 producer `_R_META_WINDOW_DAYS = 3`（Fix 2 IMPL-1）。
            # Operator 對照矩陣見 docstring：雙 PASS / 7d PASS+3d WARN
            # （bug 殘留淡出中）/ 7d FAIL+3d PASS（bug 已修等收斂）/
            # 雙 FAIL（真實 production drift）。純 SELECT。
            s, m = check_42c_live_candidate_attribution_drift_3d(cur)
            results.append(
                ("[42c] live_candidate_attribution_drift_3d", s, m)
            )

            # [43] LG5-W3-FUP-2 Fix 1 (2026-05-02): label backfill cron
            # liveness sentinel. Reads max(label_filled_at) for demo +
            # live_demo and verdicts on age (PASS <2h / WARN <6h /
            # FAIL >=6h or no rows). Catches silent death of the new
            # `helper_scripts/cron/edge_label_backfill_cron.sh` (every
            # 30 min). MIT FUP-2 diagnosis (2026-05-02) traced [42b]
            # FAIL → attribution_chain_ok=false 86%+ → label backfill
            # was on-demand only; this sentinel provides 30min-resolution
            # direct signal so cron stoppage cannot drag [42b] back below
            # R-meta floor invisibly.
            # [43] LG5-W3-FUP-2 Fix 1（2026-05-02）：label backfill cron
            # 活性哨兵。讀 demo + live_demo 的 max(label_filled_at) 並判
            # age（PASS <2h / WARN <6h / FAIL >=6h 或無 row）。捕捉新
            # `edge_label_backfill_cron.sh`（30min cron）的 silent death。
            # MIT FUP-2 diagnosis（2026-05-02）追蹤 [42b] FAIL ←
            # attribution_chain_ok=false 86%+ ← label backfill 純 on-demand；
            # 本哨兵提供 30min 解析度直接訊號，避 cron 停掉 24h 後才經 [42b]
            # 二階觀察到。純 SELECT。
            s, m = check_43_label_backfill_freshness(cur)
            results.append(("[43] label_backfill_freshness", s, m))

            # [44] REF-20 Sprint 1 Track B (2026-05-03) — replay manifest
            # sibling key.hex presence sentinel. PA push back #3.
            # Track B (Rust replay_runner verify path) is hard-error on
            # missing key.hex at startup; this check reads V045 running
            # rows + verifies sibling key.hex on disk. WARN-only transitional
            # gate — V042 SQL-backed key archive (Wave 6+) supersedes the
            # disk-fallback contract. Pure SELECT + filesystem stat; no
            # mutation. PASS-skip when V045 missing (avoids false FAIL on
            # rollout-order variance during Sprint 1).
            # [44] REF-20 Sprint 1 Track B（2026-05-03）— replay manifest
            # sibling key.hex 存在性哨兵。PA push back #3。Track B（Rust
            # replay_runner verify path）對 key.hex 缺改 hard error；本
            # check 讀 V045 running row 並驗 sibling key.hex 是否在磁碟。
            # WARN-only 過渡 gate — V042 SQL-backed key archive（Wave 6+）
            # 取代磁碟 fallback 契約。純 SELECT + filesystem stat。V045
            # 缺時 PASS-skip（避免 Sprint 1 rollout 順序差錯誤判 FAIL）。
            s, m = check_44_replay_manifest_key_presence(cur)
            results.append(("[44] replay_manifest_key_presence", s, m))

            # [45] REF-20 Sprint C R6-T7 (2026-05-05) — LG-3 provider pricing
            # binding sentinel. Implements RFC §IMPL T2 healthcheck output
            # per `docs/CCAgentWorkSpace/PA/.../2026-05-01--lg3_provider_pricing_binding_rfc.md`.
            # PG-side proxy of Rust ``AccountManager`` runtime fee health
            # via 24h trading.fills.fee_rate distribution + last-ts
            # staleness. Catches three failure modes:
            #   1. live mode + source=seed_default (RFC §2.3 mainnet
            #      fail-closed: never use defaults as availability workaround)
            #   2. last fill aged ≥24h regardless of mode
            #   3. quiet engine (0 fills) on warm engine (≥30min uptime)
            # Pure SELECT inside cursor; defensive rollback at top.
            # `[45]` LG-3 提供者定價綁定哨兵（RFC §IMPL T2）。PG 端 proxy
            # 映射 Rust AccountManager 運行時 fee 健康。捕捉 3 種失效：
            #   1. live + source=seed_default（RFC §2.3 mainnet fail-closed）
            #   2. 末條 fill aged ≥24h 不論 mode
            #   3. 熱機後（≥30min）仍 0 fills 靜默
            s, m = check_45_pricing_binding(cur)
            results.append(("[45] pricing_binding", s, m))

            # [46] REF-20 Sprint D R8 (2026-05-05) — V056 mlde_shadow
            # retention cron 活性 + replay-derived candidate row cap 雙軸驗證。
            # Sentinel 檔 mtime + V056 dry-run candidate count 雙軸 PASS/WARN/FAIL；
            # V056 缺即 graceful PASS-skip（pre-deploy 不阻塞）。
            # [46] V056 retention cron freshness + candidate row cap dual probe；
            # graceful PASS-skip when V056 absent。
            s, m = check_46_mlde_shadow_retention_status(cur)
            results.append(("[46] mlde_shadow_retention_status", s, m))

            # [48] REF-20 Sprint D R8 — replay.experiments row 增長率 stall
            # 偵測。Sprint A-C 後 runner 停滯 / E2E pipeline broken 即 7d 0
            # row 增長 → FAIL；24h 0 row → WARN（quiet day）；表缺即 PASS-skip。
            # [48] replay.experiments registry growth rate stall；7d 0 row +
            # total>=2 → FAIL（runner stalled）；24h 0 row → WARN（quiet）。
            s, m = check_48_replay_manifest_registry_growth(cur)
            results.append(("[48] replay_manifest_registry_growth", s, m))

            # [49] REF-20 Sprint D R8 — V046 replay.report_artifacts oldest
            # row age + storage cap 雙重驗證 cron `replay_artifact_prune.py`
            # 真有效跑。oldest >30d FAIL（TTL prune cron 死）；total >cap
            # FAIL（cap prune cron 死）；表缺即 PASS-skip。
            # [49] V046 oldest age + storage cap dual-check vs
            # replay_artifact_prune.py cron。
            s, m = check_49_replay_artifact_retention(cur)
            results.append(("[49] replay_artifact_retention", s, m))

            # [50] REF-20 Sprint D R8 — V045 replay.run_state 7d failed rate
            # + zombie 'running' >1h 偵測。failed_rate >20% → FAIL（系統性
            # 問題）；zombie >4h → FAIL（subprocess 死亡未收回）；表缺即
            # PASS-skip。
            # [50] V045 run_state failed rate (7d) + zombie 'running' age
            # >4h FAIL detection。
            s, m = check_50_replay_run_state_health(cur)
            results.append(("[50] replay_run_state_health", s, m))

            # [51] Scanner opportunity shadow acceptance: verify recent
            # scanner snapshots, scanner-origin intents, and MLDE row proof
            # all carry the neutral opportunity object; then compare
            # opportunity_lcb_bps with realized post-fee net bps once enough
            # labels exist. Shadow-only: no enforcement gate or trading
            # parameter mutation.
            # [51] scanner opportunity shadow 驗收：驗 snapshot / intent /
            # MLDE row proof 三段是否都帶 opportunity object，並在 label 足夠
            # 後比較 opportunity_lcb_bps 對 realized post-fee net bps 的關係。
            # 純 shadow，不接 enforcement gate，不改交易參數。
            s, m = check_scanner_opportunity_shadow_acceptance(cur)
            results.append(("[51] scanner_opportunity_shadow_acceptance", s, m))

            # [52] AgentTodo MAG-010..012 durable event-store row proof.
            # Feature-flagged default-off: env=0 PASS-skip; env=1 checks
            # recent rows in agent.messages / agent.state_changes /
            # agent.ai_invocations. REQUIRED env escalates WARN to FAIL.
            # [52] AgentTodo MAG-010..012 durable event-store row proof。
            # 預設關閉；啟用後檢查三張 agent.* 表近期是否都有 row。
            s, m = check_52_agent_event_store_rows(cur)
            results.append(("[52] agent_event_store_rows", s, m))

            # [53] REF-21 recurring V058 symbol-universe snapshot liveness.
            # Prevents survivorship-bias regression where full-chain replay
            # falls back to current survivors because universe snapshots stop.
            s, m = check_53_ref21_v058_symbol_universe_recorder(cur)
            results.append(("[53] ref21_v058_symbol_universe_recorder", s, m))

            # [54] OC-GW-5/6/7 proposal intake, approval relay, and channel
            # audit ledger sentinel. Missing tables WARN during migration
            # rollout; expired pending approvals or orphan decisions FAIL.
            s, m = check_54_openclaw_proposal_relay(cur)
            results.append(("[54] openclaw_proposal_relay", s, m))

            # [55] P1-AGENT-OBS-1 Agent Decision Spine lineage readiness.
            # Distinguishes writer disabled vs enabled-but-empty vs incomplete
            # MAG-082 runtime lineage. Read-only PG check; default WARN,
            # REQUIRED env escalates to FAIL.
            s, m = check_55_agent_decision_spine_lineage(cur)
            results.append(("[55] agent_decision_spine_lineage", s, m))

            # [57] W2-IMPL-3 (2026-05-11): W2 A4-C BTC→Alt Lead-Lag panel
            # 4 條件健康監測（PA dispatch plan §3.3）。Pure SELECT inside
            # cursor block；走 V088 hot-path index idx_btc_lead_lag_panel_ts_window。
            #   (1) panel freshness：max(snapshot_ts_ms) age < 120s PASS /
            #       120-300s WARN / ≥ 300s FAIL
            #   (2) cohort coverage：alt_symbols cohort_size = 7 PASS（spec §2.2
            #       7-sym ETHUSDT/SOLUSDT/XRPUSDT/DOGEUSDT/ADAUSDT/AVAXUSDT/DOTUSDT）
            #   (3) regime extreme ratio：extreme_n/total < 5% PASS /
            #       5-20% WARN / ≥ 20% FAIL（spec §9 condition #5
            #       |BTC 1h return| > 200 bps 標 extreme）
            #   (4) book_imbalance：W2-IMPL-1 orderbook 接線後 abs(avg) > 0
            #       PASS；W2-IMPL-1 land 前全 0 / 全 NULL WARN
            #       (OPENCLAW_W2_HEALTHCHECK_BOOK_REQUIRED=1 後升 FAIL)
            # Verdict matrix (PA §3.3)：PASS = 4 全綠 / WARN = 1-2 偏移 /
            # FAIL = age ≥ 300s OR cohort < 7 OR extreme ≥ 20% OR ≥3 條件破。
            # Default-off：OPENCLAW_W2_HEALTHCHECK_ENABLED=1 opt-in；
            # V088 panel.btc_lead_lag_panel 未 deploy → PASS-skip。
            # CLAUDE.md §七「被動等待 TODO 必附 healthcheck」強制配對 W2 paper
            # engine 7d evidence collection（D+5 deploy → D+12 paper edge report）。
            s, m = check_57_btc_lead_lag_panel_health(cur)
            results.append(("[57] btc_lead_lag_panel_health", s, m))

            # [58] W-AUDIT-9 T4 (2026-05-09): graduated canary stage invariant
            # sentinel. AMD-2026-05-09-03 §4.1 配套 — 對 active cohort 驗證
            # 5 invariants（metric registry / rollback trip / observation
            # period / cohort 規範）+ invariant 11（manual_promote NOT NULL
            # lease，V080 PG CHECK 應擋，partial-rollout drift 仍觀察）+
            # invariant 12（SM-04 ≥ L3 escalate 必觸 stage 0 rollback）。
            # SM-04 hard FAIL 由 transition_kind='incident_rollback' +
            # triggered_metric ILIKE '%sm04%' 偵測。
            # 純 SELECT inside cursor block; defensive rollback at top.
            # [58] W-AUDIT-9 T4（2026-05-09）— graduated canary stage 不變式
            # 哨兵（AMD-2026-05-09-03 §4.1）。對 active cohort 驗 5 不變式 +
            # invariant 11/12。SM-04 ≥ L3 escalate hard FAIL 由
            # transition_kind='incident_rollback' + triggered_metric ILIKE
            # '%sm04%' 偵測。純 SELECT，cursor 區塊內。
            s, m = check_58_graduated_canary_stage_invariant(cur)
            results.append(("[58] graduated_canary_stage_invariant", s, m))

            # [58a] W5-E1-A P1-CANARY-STAGE-CRITERIA-1 (2026-05-10 Sprint N+1):
            # spec §7.4 enrich evidence collection — per-stage metric registry
            # coverage + active cohort metric set summary. Verdict-preserving
            # WARN-on-V089-seed-drift / PASS-on-full-seed (does not hard FAIL,
            # avoiding silent-dead noise). Actual cohort metric value computation
            # deferred to W3 cohort SQL pipeline land. Pure SELECT inside cursor
            # block; defensive rollback at top.
            # [58a] W5-E1-A（2026-05-10）— spec §7.4 enrich 證據收集；報告 V089
            # metric registry 每 stage 覆蓋 + active cohort 對應 metric set。
            # WARN-on-drift / PASS-on-full-seed；實際 cohort metric 計算等 W3 land。
            s, m = check_58a_stage_criteria_eval(cur)
            results.append(("[58a] stage_criteria_eval", s, m))

            # [59] LG1-T2 (2026-05-11): H0 hard-block production caller
            # acceptance sentinel per PA tech plan `2026-05-11--lg_2_3_4_
            # design_plan.md` §1.4 T2. 讀 ``pipeline_snapshot_{demo,live_demo}.
            # json`` 的 `h0_gate_stats` + `risk_manager_config.runtime.
            # h0_shadow_mode`，並跨檢 ``trading.fills`` 1h 入場 fill 計數，
            # 推斷 H0 hard-block 是否真實生效。Per-engine 4 sub-check：
            #   A. snapshot fresh < 5min (否則 WARN_NO_SNAPSHOT skip engine)
            #   B. shadow_mode 旗標 (demo/live_demo 預設 false; true → WARN)
            #   C. stats sample (total_checks >= 100; 否則 WARN_LOW_SAMPLE)
            #   D. block leakage (blocked ratio > 0.5 + entry_fills > 0 →
            #      FAIL_BLOCK_LEAKAGE; invariant 失效)
            # OPENCLAW_H0_BLOCK_HEALTH_REQUIRED=1 升 WARN → FAIL。預設
            # WARN-only 避免 Mac dev / engine cold-start false-FAIL。
            # [59] LG1-T2（2026-05-11）H0 hard-block 生產調用驗收哨兵
            # （PA tech plan §1.4 T2）。讀 snapshot.h0_gate_stats +
            # h0_shadow_mode，跨檢 trading.fills 1h entry fills 推斷
            # hard-block 失效。OPENCLAW_H0_BLOCK_HEALTH_REQUIRED=1 升
            # WARN → FAIL。
            s, m = check_59_h0_block_acceptance(cur)
            results.append(("[59] h0_block_acceptance", s, m))

            # [64] W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1 (2026-05-10 Sprint N+1):
            # 動態解封 candidate 治理 4 項漂移哨兵（spec §6.2）。
            # (1) stale candidate >14d / (2) yo-yo / (3) sign-off completeness /
            # (4) unfrozen rows count（freeze.json 同步 surrogate）。
            # V090 缺即 PASS-skip（pre-deploy 不阻塞）。純 SELECT cursor 區塊內。
            # [64] W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1（2026-05-10 Sprint N+1）：
            # 動態解封候選漂移 4 哨兵。spec §6.2；V090 缺 PASS-skip。
            s, m = check_64_unblock_candidates_drift(cur)
            results.append(("[64] unblock_candidates_drift", s, m))

            # [65] MIT W6-1 RFC SHOULD 7 (2026-05-10): W-AUDIT-4b M3
            # producer post-deploy chain integrity sentinel. Era filter
            # `f.ts > '2026-05-09 09:22 UTC'` excludes pre-M3 historical
            # orphan (3570/5854 = 39%, producer didn't exist, unfixable).
            # PASS ≥ 95% / WARN 80-95% / FAIL < 80% / WARN_LOW_SAMPLE n<30.
            # Per-strategy drill-down annotation; verdict driven by global ratio.
            # Pure SELECT inside cursor block; defensive rollback at top.
            # [65] MIT W6-1 RFC SHOULD 7（2026-05-10）：W-AUDIT-4b M3
            # producer 接通後 chain integrity 哨兵；era filter 排除 pre-M3
            # 歷史 orphan。PASS ≥ 95% / WARN 80-95% / FAIL < 80%。
            s, m = check_chain_integrity_post_audit_4b_m3(cur)
            results.append(("[65] chain_integrity_post_audit_4b_m3", s, m))

            # [66] W1 sub-task 3 (E1-γ, 2026-05-11): panel.* freshness sentinel
            # 監控 PanelAggregator (W-AUDIT-8a Phase B Tier 2) 寫入 panel.funding_rates_panel
            # + panel.oi_delta_panel 的 snapshot 新鮮度。
            # PASS < 5min / WARN 5-15min / FAIL > 15min。V085/V087 未 deploy → PASS_SKIP。
            # 對應 cron: helper_scripts/cron/panel_aggregator_health_cron.sh（雙保險）
            s, m = check_panel_freshness(cur)
            results.append(("[66] panel_freshness", s, m))

            # [67] W-AUDIT-4b retained INSERT table readiness:
            # observability.feature_baselines must have active rows and preserve
            # the Rust 34-dim feature-vector contract. This check intentionally
            # does not bypass drift_detector ADWIN burn-in; it only proves the
            # baseline dependency is populated so drift_events can activate when
            # the configured burn-in matures.
            s, m = check_67_feature_baseline_readiness(cur)
            results.append(("[67] feature_baseline_readiness", s, m))

            # [68] P2-PORTFOLIO-RESTING-58-HEALTHCHECK (2026-05-16, P1
            # follow-up升級至 P1 per FA Stage 1 demo 啟前 mandatory): 配對
            # P1-PORTFOLIO-RESTING-EXPOSURE-1 Rust IMPL (commit `9980448a`)
            # 把 ``paper_state.resting_limit_orders`` 納入
            # ``compute_effective_long_short_notional`` SoT helper；本 check
            # 監測 effective (filled+resting) vs filled-only leverage chain
            # semantic drift magnitude (A3 WARN-1 + E2 LOW-1 + PA §8)。
            # 每 engine (paper/demo/live/live_demo) 各跑一次：
            #   1. 讀 pipeline_snapshot_{engine}.json 抽 filled notional + balance
            #   2. SQL ``trading.orders+order_state_changes`` 取 Working orders
            #      → per (symbol, side) resting notional
            #   3. 讀 risk_config_{engine}.toml correlated_exposure_max_pct
            #   4. Verdict: long/short 各別 < 80% cap PASS, ≥ 80% < 100% WARN,
            #      ≥ 100% FAIL；divergence < 50% PASS, ≥ 50% < 100% WARN,
            #      ≥ 100% FAIL；per-symbol resting/filled < 80% PASS,
            #      ≥ 80% WARN, > 150% FAIL
            # snapshot 缺 → 該 engine 跳過 (其他 engine 仍跑);
            # 表缺 → PASS_SKIP pre-deploy 不阻塞;
            # OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED=1 升 WARN → FAIL。
            # ID 註：PA spec / TODO 標 [58] 但 [58] = W-AUDIT-9 T4，取下一
            # 自由 slot [68]，name `portfolio_resting_exposure_lineage` 保留。
            s, m = check_68_portfolio_resting_exposure(cur)
            results.append(("[68] portfolio_resting_exposure_lineage", s, m))
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

    # [47] REF-20 Sprint D R8 (2026-05-05) — Linux replay_runner binary
    # presence + executable bit。Pure filesystem 檢查 (mirror
    # route_helpers.resolve_replay_runner_bin 5-path priority chain)：
    # workspace release → workspace debug → legacy nested release/debug；
    # release path 缺但 debug 在 → WARN（未 --rebuild）；4 path 全缺 → FAIL
    # （cargo --release 未跑）。Pure filesystem，post-conn.close()。
    # [47] Linux replay_runner binary 存在 + executable；filesystem only。
    s, m = check_47_replay_runner_binary()
    results.append(("[47] replay_runner_binary", s, m))

    # [56] P0-NEW-ISSUE-1 (2026-05-09): LiveDemo pipeline active sentinel.
    # If the live slot is configured, signed authorization must be present and
    # the Rust live snapshot must be fresh. Filesystem-only and read-only:
    # this never writes/renews authorization.json.
    # [56] LiveDemo 管線活性哨兵。live slot 已配置時，必須有簽名授權檔且
    # Rust live snapshot 新鮮。純 filesystem/read-only，不寫或續簽 auth。
    s, m = check_56_live_pipeline_active()
    results.append(("[56] live_pipeline_active", s, m))

    # NOTE: [30] cost_edge_advisor_status moved INSIDE the cursor block by
    # G3-09 Phase B Wave 1 (2026-04-28). Phase A version was filesystem-only
    # and ran outside cursor; Phase B adds Inv 3 + Inv 4 which need DB
    # queries against learning.cost_edge_advisor_log. See cursor block above.
    # NOTE：[30] cost_edge_advisor_status 已由 G3-09 Phase B Wave 1（2026-04-28）
    # 移至 cursor 區塊內。Phase A 版本純 filesystem 在 cursor 外；Phase B
    # Inv 3+4 需查 learning.cost_edge_advisor_log，故移入。詳上方 cursor 區塊。

    # output
    return _emit_results(results, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
