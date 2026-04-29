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
]
