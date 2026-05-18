"""Passive-wait pipeline healthcheck package.
被動等待管線健康檢查 package。

MODULE_NOTE (EN): Package split from the original 2294-line
``passive_wait_healthcheck.py`` per CLAUDE.md §九 1200-line hard cap
(G5-FUP-PASSIVE-HEALTH, 2026-04-26). The thin shim
``helper_scripts/db/passive_wait_healthcheck.py`` re-exports ``main``
from ``passive_wait_healthcheck.runner`` so the cron entry path stays
identical (``python3 helper_scripts/db/passive_wait_healthcheck.py``).

Public surface = ``main`` and the individual ``check_*`` functions.
SQL strings, exit-code semantics, output formatting are byte-identical
to the pre-split version — no behavior change.

MODULE_NOTE (中): 由原 2294 行 ``passive_wait_healthcheck.py`` 按
CLAUDE.md §九 1200 行硬上限拆分（G5-FUP-PASSIVE-HEALTH，2026-04-26）。
Thin shim ``passive_wait_healthcheck.py`` 從 ``runner`` 重新匯出 ``main``，
確保 cron 入口路徑不變。
公開介面 = ``main`` 與所有 ``check_*`` 函數；SQL / exit code / 輸出格式
與拆分前 byte-identical（無行為變更）。
"""

from __future__ import annotations

from .runner import main

# Re-export individual check functions so external callers / tests can
# import them directly from the package root if they wish.
# 重新匯出個別 check 函數，方便外部呼叫者 / 測試直接從 package root import。
from .checks_engine import (  # noqa: F401
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
from .checks_ipc_edge import (  # noqa: F401
    check_phys_lock_runtime,
    check_micro_profit_fire,
    check_trailing_stop_fire,
    check_edge_estimates_freshness,
    check_shadow_exit_ratio,
    check_model_registry_freshness,
    # EDGE-DIAG-2 (2026-04-28) demo cost_gate strategy diversity sentinel
    # EDGE-DIAG-2（2026-04-28）demo cost_gate 策略多樣性哨兵
    check_edge_diag_2_strategy_diversity,
)
from .checks_strategy import (  # noqa: F401
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
from .checks_derived import (  # noqa: F401
    check_leader_election_health,
    check_pipeline_triangulation,
    check_disabled_strategy_inventory,
    check_observer_pipeline_alive,
    check_h_state_gateway_freshness,
    # F7 (2026-04-26) ML hygiene derived sentinel
    check_dust_spiral_noise_in_ef,
    # [65] MIT W6-1 RFC SHOULD 7 (2026-05-10) W-AUDIT-4b M3 producer
    # post-deploy chain integrity sentinel.
    # [65] MIT W6-1 RFC SHOULD 7（2026-05-10）W-AUDIT-4b M3 producer
    # 接通後 chain integrity 哨兵。
    check_chain_integrity_post_audit_4b_m3,
)
from .checks_cost_edge import (  # noqa: F401
    # G3-09 Phase A (2026-04-27) → Phase B (2026-04-28) cost_edge_advisor sentinel
    # extracted from checks_derived.py by HIGH-1 fix to keep checks_derived.py
    # under CLAUDE.md §九 1200-line hard cap.
    # G3-09 Phase A → Phase B cost_edge_advisor 哨兵；HIGH-1 fix 從 checks_derived
    # 抽出維持 1200 行硬上限。
    check_cost_edge_advisor_status,
)
from .checks_execution import (  # noqa: F401
    check_maker_fill_rate,
    check_maker_entry_intent_drift,
    check_intent_signal_attribution,
    check_mlde_learning_data_contract,
    check_mlde_shadow_recommendations,
    check_mlde_demo_applier,
    # [38] (2026-04-29) MIT data-drift-detection: grid_trading single-position
    # lifecycle drift demo vs live_demo (passive 7d observation per CLAUDE.md
    # §七 「被動等待 TODO 必附 healthcheck」).
    # [38]（2026-04-29）MIT 資料漂移偵測：grid_trading 單倉 lifecycle
    # demo vs live_demo 漂移哨兵（被動 7d，CLAUDE.md §七 規定）。
    check_grid_trading_lifecycle_drift,
    # [39] (2026-04-29) PA W1-T4 strategy_name attribution cleanup — cardinality
    # regression detector for trading.fills.strategy_name (post-W1-T2 expect ≤7
    # enum values; FAIL when dynamic format!() regression re-inflates cardinality).
    # [39]（2026-04-29）PA W1-T4 strategy_name attribution 清理 — cardinality
    # regression 偵測（W1-T2 後預期 ≤7 enum value；dynamic format regression
    # 復發即 FAIL）。
    check_strategy_name_cardinality_drift,
    # [40] DB-truth realized-edge acceptance monitor for profitability repair.
    check_realized_edge_acceptance,
)
from .checks_scanner_market import (  # noqa: F401
    # [41] scanner market-gate confirmation monitor.
    check_scanner_market_gate_confirmation,
    # [51] scanner opportunity shadow acceptance monitor.
    check_scanner_opportunity_shadow_acceptance,
)
from .checks_agent_events import (  # noqa: F401
    # [52] AgentTodo MAG-010..012 durable event-store row proof.
    check_52_agent_event_store_rows,
)
from .checks_governance import (  # noqa: F401
    # [42]/[42b] LG-5-IMPL-3 (2026-05-02) governance contract + attribution drift.
    # [42]/[42b] LG-5-IMPL-3（2026-05-02）治理契約 + 歸因漂移哨兵。
    check_42_live_candidate_eval_contract,
    check_42b_live_candidate_attribution_drift,
    # [42c] LG5-W3-FUP-2 Fix 2 (2026-05-02 RFC §5 Plan B) — gate-aligned
    # 3d mirror of [42b]; identical thresholds, 3d window matching producer
    # _R_META_WINDOW_DAYS so operator reads exactly what R-meta gate sees.
    # [42c] LG5-W3-FUP-2 Fix 2（2026-05-02 RFC §5 方案 B）— [42b] 的
    # R-meta gate 對齊 3d 鏡像；閾值一致，window 對齊 producer
    # _R_META_WINDOW_DAYS=3，operator 直接看 R-meta gate 吃到的 ratio。
    check_42c_live_candidate_attribution_drift_3d,
    # [43] LG5-W3-FUP-2 Fix 1 (2026-05-02) — label backfill cron liveness.
    # [43] LG5-W3-FUP-2 Fix 1（2026-05-02）— label backfill cron 活性哨兵。
    check_43_label_backfill_freshness,
    # [44] REF-20 Sprint 1 Track B (2026-05-03) — replay manifest sibling
    # key.hex presence (PA push back #3 — Track B fail-closed key.hex deploy
    # contract monitor; WARN-only until V042 SQL archive lands Wave 6+).
    # [44] REF-20 Sprint 1 Track B（2026-05-03）— replay manifest sibling
    # key.hex 存在性監測（PA push back #3 — Track B fail-closed key.hex 部署
    # 契約監測；V042 SQL archive 於 Wave 6+ land 前 WARN-only）。
    check_44_replay_manifest_key_presence,
)
from .checks_pricing_binding import (  # noqa: F401
    # [45] REF-20 Sprint C R6-T7 (2026-05-05) — LG-3 provider pricing
    # binding sentinel. Implements RFC §IMPL T2 healthcheck output
    # (`2026-05-01--lg3_provider_pricing_binding_rfc.md`); T1 contract
    # test deferred to Sprint D, T3 startup assertion deferred to LG-4
    # IMPL pre-req. PG-side proxy of Rust ``AccountManager`` runtime
    # fee health via 24h trading.fills.fee_rate distribution +
    # last-ts staleness.
    # [45] REF-20 Sprint C R6-T7（2026-05-05）— LG-3 提供者定價綁定哨兵
    # （RFC §IMPL T2）；T1 Sprint D / T3 LG-4 前提。PG 端 proxy（24h
    # trading.fills.fee_rate 分佈 + 末條 ts staleness）映射 Rust
    # AccountManager 運行時 fee 健康。
    check_45_pricing_binding,
)
from .checks_replay_maintenance import (  # noqa: F401
    # [46]-[50] REF-20 Sprint D R8 (2026-05-05) — maintenance / observation
    # sentinel suite。對應 Sprint D R8 plan §6.R8 task 2 五個哨兵：
    # mlde_shadow retention cron 活性 + replay_runner binary 存在 + manifest
    # registry 增長率 + V046 artifact retention + V045 run_state 健康。
    # [46]-[50] REF-20 Sprint D R8 (2026-05-05) — five sentinels covering
    # plan §6.R8 task 2: mlde_shadow retention cron freshness +
    # replay_runner binary presence + manifest registry growth + V046
    # artifact retention + V045 run_state health.
    check_46_mlde_shadow_retention_status,
    check_47_replay_runner_binary,
    check_48_replay_manifest_registry_growth,
    check_49_replay_artifact_retention,
    check_50_replay_run_state_health,
)
from .checks_live_pipeline import (  # noqa: F401
    # [56] P0-NEW-ISSUE-1 Live / LiveDemo pipeline active sentinel.
    check_56_live_pipeline_active,
)
from .checks_btc_lead_lag import (  # noqa: F401
    # [57] W2-IMPL-3 (2026-05-11) W2 A4-C BTC→Alt Lead-Lag panel 4 條件健康
    # 監測：panel freshness + cohort coverage + regime extreme ratio +
    # book_imbalance 非 0 / 非 NULL。default-off (OPENCLAW_W2_HEALTHCHECK_ENABLED=1
    # opt-in)；V088 未 deploy → PASS-skip pre-deploy 不阻塞。
    check_57_btc_lead_lag_panel_health,
)
from .checks_portfolio_resting_exposure import (  # noqa: F401
    # [68] P2-PORTFOLIO-RESTING-58-HEALTHCHECK (2026-05-16) — P1-PORTFOLIO-
    # RESTING-EXPOSURE-1 follow-up 升 P1 per FA Stage 1 demo 啟前 mandatory；
    # 監測 effective(filled+resting) vs filled-only leverage chain semantic
    # drift magnitude (A3 WARN-1 + E2 LOW-1 + PA §8)。
    # ID 註：PA spec / TODO 標 [58] 但 [58] 已被 W-AUDIT-9 T4 占用,取 [68]
    # 自由 slot；name `portfolio_resting_exposure_lineage` 保留。
    check_68_portfolio_resting_exposure,
)
from .checks_wp03_deploy_gate import (  # noqa: F401
    # [69] P1-WP03-DEPLOY-GATE-IMPL (2026-05-16) — WP-03 OU sigma residual
    # fix post-deploy 24h+ monitoring + revert flag。配對 PA spec
    # `docs/execution_plan/2026-05-16--wp03_ou_sigma_deploy_gate_spec.md`。
    # 監測 grid_trading 在 demo + live_demo 的 avg_net_bps 三窗 (12h/24h/7d)
    # trigger (T1=-10bps fast-fail / T2=-5bps primary / T3=baseline-3bps
    # cumulative / ZERO_FILLS)，任一觸發即寫 revert flag advisory（per
    # ADR-0020 manual-only，不 auto trigger revert action）。
    check_69_wp03_ou_sigma_deploy_gate,
)
from .checks_close_maker_audit import (  # noqa: F401
    # [70]-[74] Phase 1b close-maker V094 audit observability; literal
    # [62]-[65] from frozen V094 text are rebased because [64]/[65] are
    # already active in runner.py.
    # [70]-[74] Phase 1b close-maker V094 audit 哨兵；V094 凍結文本的
    # [62]-[65] 因 [64]/[65] 已占用，於 runner.py 內重排到自由 slot。
    check_close_maker_fill_rate,
    check_close_maker_zero_spine_lineage,
    check_close_maker_fallback_null_ladder,
    check_close_maker_rate_limit_backoff_coverage,
    check_close_maker_reject_samples,
)
from .checks_cron_heartbeat import (  # noqa: F401
    # [75]-[79] P1-CRON-INSTALL-WAVE-1（2026-05-18）— 5 個 cron wrapper
    # 已 source/test closed 但 crontab 尚未 install；每個 wrapper start-time
    # touch sentinel，本套哨兵以 sentinel mtime 推斷「cron 是否按時 fire」。
    # WARN-by-default（cron infra 不是 promotion-blocking）；
    # OPENCLAW_CRON_HEARTBEAT_REQUIRED=1 升 WARN → FAIL。
    check_75_panel_aggregator_health_cron_fires,
    check_76_wave9_replay_no_live_mutation_watch_cron_fires,
    check_77_replay_key_rotation_check_cron_fires,
    check_78_feature_baseline_writer_cron_fires,
    check_79_blocked_symbols_30d_unblock_check_cron_fires,
)

__all__ = [
    "main",
    # engine flow
    "check_close_fills_24h",
    "check_label_backfill_ratio",
    "check_exit_features_writer",
    "check_paper_state_dust_inventory",
    # F7 engine flow MIT+E5
    "check_trading_pipeline_silent_gap",
    "check_orders_fills_consistency",
    "check_dust_qty_distribution",
    "check_intents_counter_freeze",
    "check_phantom_fills_attribution",
    "check_reconciler_paper_state_divergence",
    # risk layer + shadow + freshness + registry
    "check_phys_lock_runtime",
    "check_micro_profit_fire",
    "check_trailing_stop_fire",
    "check_edge_estimates_freshness",
    "check_shadow_exit_ratio",
    "check_model_registry_freshness",
    "check_edge_diag_2_strategy_diversity",
    # strategy / scheduler
    "check_intents_writer_ratio",
    "check_counterfactual_clean_window_growth",
    "check_bb_breakout_post_deadlock_fix",
    "check_edge_estimator_scheduler_fresh",
    "check_exit_features_accumulation_rate",
    "check_shadow_exit_agreement_phase2",
    "check_strategist_cycle_fresh",
    # F7 strategy MIT
    "check_signals_writer_freshness",
    # derived / observability
    "check_leader_election_health",
    "check_pipeline_triangulation",
    "check_disabled_strategy_inventory",
    "check_observer_pipeline_alive",
    "check_h_state_gateway_freshness",
    # F7 derived ML hygiene
    "check_dust_spiral_noise_in_ef",
    # G3-09 Phase A cost_edge_advisor
    "check_cost_edge_advisor_status",
    # execution-shape / fee-drop drift
    "check_maker_entry_intent_drift",
    "check_maker_fill_rate",
    "check_intent_signal_attribution",
    "check_mlde_learning_data_contract",
    "check_mlde_shadow_recommendations",
    "check_mlde_demo_applier",
    # [38] grid_trading lifecycle drift (MIT 2026-04-29)
    "check_grid_trading_lifecycle_drift",
    # [39] strategy_name cardinality drift (PA W1-T4 2026-04-29)
    "check_strategy_name_cardinality_drift",
    # [40] realized edge acceptance
    "check_realized_edge_acceptance",
    # [41] scanner market-gate confirmation
    "check_scanner_market_gate_confirmation",
    # [51] scanner opportunity shadow acceptance
    "check_scanner_opportunity_shadow_acceptance",
    # [52] AgentTodo MAG-010..012 durable event-store row proof
    "check_52_agent_event_store_rows",
    # [42]/[42b] LG-5-IMPL-3 governance contract + attribution drift
    "check_42_live_candidate_eval_contract",
    "check_42b_live_candidate_attribution_drift",
    # [42c] LG5-W3-FUP-2 Fix 2 — 3d gate-aligned mirror of [42b]
    "check_42c_live_candidate_attribution_drift_3d",
    # [43] LG5-W3-FUP-2 Fix 1 label backfill cron liveness
    "check_43_label_backfill_freshness",
    # [44] REF-20 Sprint 1 Track B (2026-05-03) replay manifest key.hex presence
    "check_44_replay_manifest_key_presence",
    # [45] REF-20 Sprint C R6-T7 (2026-05-05) LG-3 pricing binding sentinel
    "check_45_pricing_binding",
    # [46]-[50] REF-20 Sprint D R8 (2026-05-05) maintenance sentinel suite
    "check_46_mlde_shadow_retention_status",
    "check_47_replay_runner_binary",
    "check_48_replay_manifest_registry_growth",
    "check_49_replay_artifact_retention",
    "check_50_replay_run_state_health",
    # [56] P0-NEW-ISSUE-1 live pipeline active sentinel
    "check_56_live_pipeline_active",
    # [57] W2-IMPL-3 (2026-05-11) W2 A4-C BTC→Alt Lead-Lag panel 4 條件健康監測
    "check_57_btc_lead_lag_panel_health",
    # [65] MIT W6-1 RFC SHOULD 7 (2026-05-10) W-AUDIT-4b M3 chain integrity
    "check_chain_integrity_post_audit_4b_m3",
    # [68] P2-PORTFOLIO-RESTING-58-HEALTHCHECK (2026-05-16) — P1-PORTFOLIO-
    # RESTING-EXPOSURE-1 follow-up; ID 註：原 PA spec/TODO 標 [58]，[58] 已被
    # W-AUDIT-9 T4 占用，取下一自由 [68] free slot；name preserved。
    "check_68_portfolio_resting_exposure",
    # [69] P1-WP03-DEPLOY-GATE-IMPL (2026-05-16) — WP-03 OU sigma residual
    # deploy gate；三窗 (12h/24h/7d) trigger + revert flag advisory (ADR-0020
    # manual-only)。
    "check_69_wp03_ou_sigma_deploy_gate",
    # [70]-[74] Phase 1b close-maker V094 audit observability.
    "check_close_maker_fill_rate",
    "check_close_maker_zero_spine_lineage",
    "check_close_maker_fallback_null_ladder",
    "check_close_maker_rate_limit_backoff_coverage",
    "check_close_maker_reject_samples",
    # [75]-[79] P1-CRON-INSTALL-WAVE-1（2026-05-18）cron heartbeat sentinels.
    "check_75_panel_aggregator_health_cron_fires",
    "check_76_wave9_replay_no_live_mutation_watch_cron_fires",
    "check_77_replay_key_rotation_check_cron_fires",
    "check_78_feature_baseline_writer_cron_fires",
    "check_79_blocked_symbols_30d_unblock_check_cron_fires",
]
