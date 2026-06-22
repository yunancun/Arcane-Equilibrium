from __future__ import annotations

from datetime import datetime, timezone

import pytest

from helper_scripts.db.audit.demo_order_stall_audit import (
    AuditConfig,
    build_context_payload_scope_sql,
    build_evaluation_outcome_sql,
    build_intent_order_lineage_sql,
    build_json_payload,
    build_pipeline_counts_sql,
    build_pre_gate_drilldown_sql,
    build_risk_reason_sql,
    classify_order_stall,
    render_markdown,
    reason_category,
    context_scope_is_observation_only,
    summarize_data_flow_freshness,
    summarize_pre_gate_drilldown,
    validate_config,
)


def _base_counts(**overrides: object) -> dict[str, object]:
    counts: dict[str, object] = {
        "decision_context_snapshots": 0,
        "candidate_evaluations": 0,
        "decision_features": 0,
        "rejected_decision_features": 0,
        "risk_verdicts": 0,
        "approved_risk_verdicts": 0,
        "rejected_risk_verdicts": 0,
        "intents": 0,
        "orders": 0,
        "post_only_orders": 0,
        "orders_with_fill_state": 0,
        "orders_with_rejected_state": 0,
        "orders_with_cancelled_state": 0,
        "post_only_cross_orders": 0,
        "fills": 0,
        "net_pnl_usdt": 0,
    }
    counts.update(overrides)
    return counts


def test_validate_config_bounds() -> None:
    validate_config(AuditConfig(engine_modes=("demo", "live_demo"), lookback_hours=24))

    with pytest.raises(ValueError):
        validate_config(AuditConfig(engine_modes=(), lookback_hours=24))
    with pytest.raises(ValueError):
        validate_config(AuditConfig(engine_modes=("unknown",), lookback_hours=24))
    with pytest.raises(ValueError):
        validate_config(AuditConfig(engine_modes=("demo",), lookback_hours=0))
    with pytest.raises(ValueError):
        validate_config(AuditConfig(engine_modes=("demo",), lookback_hours=24, top_limit=0))


def test_sql_contract_is_read_only_and_covers_pipeline_tables() -> None:
    sql = "\n".join(
        [
            build_pipeline_counts_sql(),
            build_risk_reason_sql(),
            build_evaluation_outcome_sql(),
            build_intent_order_lineage_sql(),
            build_context_payload_scope_sql(),
            build_pre_gate_drilldown_sql(),
        ]
    )
    for table in [
        "trading.decision_context_snapshots",
        "learning.decision_features_evaluations",
        "learning.decision_features",
        "trading.risk_verdicts",
        "trading.intents",
        "trading.orders",
        "trading.order_state_changes",
        "trading.fills",
    ]:
        assert table in sql
    assert "engine_mode = ANY" in sql
    assert "INSERT " not in sql.upper()
    assert "UPDATE " not in sql.upper()
    assert "DELETE " not in sql.upper()


def test_pipeline_counts_sql_escapes_literal_percent_for_psycopg() -> None:
    sql = build_pipeline_counts_sql()

    assert "ILIKE '%%post_only_cross%%'" in sql
    assert "ILIKE '%%postonlywilltakeliquidity%%'" in sql
    assert "ILIKE '%%post only will take liquidity%%'" in sql
    assert "ILIKE '%%ec_postonlywilltakeliquidity%%'" in sql


def test_pre_gate_drilldown_sql_joins_contexts_to_downstream_tables() -> None:
    sql = build_pre_gate_drilldown_sql()

    assert "FROM trading.decision_context_snapshots d" in sql
    assert "d.decision_payload->>'linucb_metadata_scope'" in sql
    assert "d.decision_payload->>'accepted_intent_bound'" in sql
    assert "jsonb_array_length" in sql
    assert "LEFT JOIN evals e" in sql
    assert "LEFT JOIN rv" in sql
    assert "LEFT JOIN intents i" in sql
    assert "LEFT JOIN orders o" in sql
    assert "LEFT JOIN fills f" in sql
    assert "d.context_id" in sql
    assert "coalesce(f.entry_context_id, f.context_id)" in sql
    assert "GROUP BY d.engine_mode, d.strategy_name, d.symbol, d.decision_type" in sql


def test_context_payload_scope_sql_surfaces_observation_payload_fields() -> None:
    sql = build_context_payload_scope_sql()

    assert "FROM trading.decision_context_snapshots d" in sql
    assert "d.decision_payload->>'linucb_metadata_scope'" in sql
    assert "d.decision_payload->>'accepted_intent_bound'" in sql
    assert "signal_observation_only_contexts" in sql
    assert "accepted_intent_bound_contexts" in sql
    assert "non_observation_scope_contexts" in sql


def test_reason_category_identifies_cost_gate_and_other_gate_types() -> None:
    assert reason_category("cost_gate(JS-demo): estimated=-3.5bps < 0") == "cost_gate"
    assert reason_category("predictor_fallback_fail_closed:predict_no_model") == "predictor_gate"
    assert (
        reason_category("BTCUSDT blocked by per_strategy.ma_crossover.blocked_symbols")
        == "strategy_blocklist"
    )
    assert reason_category("exposure cap exceeded") == "risk_envelope"
    assert reason_category("Decision Lease expired") == "governance_auth"
    assert reason_category("some other reject") == "other"


def test_classification_no_data_and_signal_only_paths() -> None:
    no_data = classify_order_stall(_base_counts(), [], {})
    assert no_data["status"] == "NO_RECENT_PIPELINE_DATA"
    assert no_data["data_accumulation_status"] == "NOT_ACCUMULATING_RECENT_DATA"

    signal_only = classify_order_stall(
        _base_counts(decision_context_snapshots=100),
        [],
        {},
    )
    assert signal_only["status"] == "SIGNAL_OBSERVATION_ONLY_PRE_GATE"
    assert signal_only["answers"]["silent_drop_risk"] is True

    observation_only_scope = {
        "context_rows": 100,
        "signal_observation_only_contexts": 100,
        "accepted_intent_bound_contexts": 0,
        "non_observation_scope_contexts": 0,
        "missing_scope_contexts": 0,
    }
    observation_only = classify_order_stall(
        _base_counts(decision_context_snapshots=100),
        [],
        {},
        observation_only_scope,
    )
    assert context_scope_is_observation_only(observation_only_scope) is True
    assert observation_only["status"] == "OBSERVATION_ONLY_CONTEXTS_ACTIVE"
    assert (
        observation_only["data_accumulation_status"]
        == "OBSERVATION_ONLY_CONTEXTS_ACCUMULATING"
    )
    assert observation_only["answers"]["context_payload_observation_only"] is True
    assert observation_only["answers"]["actionable_contexts_present"] is False
    assert observation_only["answers"]["silent_drop_risk"] is False

    candidates_only = classify_order_stall(
        _base_counts(decision_context_snapshots=100, candidate_evaluations=50),
        [],
        {},
    )
    assert candidates_only["status"] == "PREDICTOR_OR_STRATEGY_PRE_RISK_GATE"
    assert (
        candidates_only["data_accumulation_status"]
        == "REJECT_OR_CANDIDATE_DATA_ACCUMULATING"
    )


def test_classification_cost_gate_rejects_are_not_silent_drops() -> None:
    risk_reasons = [
        {
            "reason": "cost_gate(JS-demo): estimated=-3.5bps < 0",
            "n": 950,
            "approved_n": 0,
            "rejected_n": 950,
        },
        {"reason": "exposure cap exceeded", "n": 50, "approved_n": 0, "rejected_n": 50},
    ]
    result = classify_order_stall(
        _base_counts(
            decision_context_snapshots=1_000,
            candidate_evaluations=900,
            decision_features=800,
            rejected_decision_features=800,
            risk_verdicts=1_000,
            rejected_risk_verdicts=1_000,
        ),
        risk_reasons,
        {},
    )

    assert result["status"] == "COST_GATE_REJECTING_ALL_RECENT_ATTEMPTS"
    assert result["dominant_risk_category"]["category"] == "cost_gate"
    assert result["answers"]["rejected_signals_recorded"] is True
    assert result["answers"]["silent_drop_risk"] is False
    assert result["answers"]["global_cost_gate_lowering_recommended"] is False
    assert result["answers"]["bounded_demo_learning_lane_recommended"] is True


def test_learning_data_flow_freshness_marks_stale_reject_rows() -> None:
    counts = _base_counts(
        decision_features=800,
        rejected_decision_features=800,
        risk_verdicts=1_000,
        rejected_risk_verdicts=1_000,
        latest_decision_feature_ts="2026-06-21T20:47:59+00:00",
        latest_risk_verdict_ts="2026-06-21T20:47:59+00:00",
    )
    now = datetime(2026, 6, 21, 23, 9, tzinfo=timezone.utc)

    freshness = summarize_data_flow_freshness(counts, now_utc=now)
    result = classify_order_stall(
        counts,
        [{"reason": "cost_gate(JS-demo): estimated=-3.5bps < 0", "n": 1_000}],
        {},
        now_utc=now,
    )

    assert freshness["status"] == "LEARNING_DATA_FLOW_STALE"
    assert freshness["latest_learning_stage"] == "decision_features"
    assert freshness["latest_learning_age_seconds"] == 8461
    assert result["data_accumulation_status"] == "LEARNING_DATA_FLOW_STALE"
    assert result["answers"]["learning_data_flow_stale"] is True
    assert "learning_data_flow_stale" in result["warnings"]


def test_classification_later_stage_gaps() -> None:
    approved_without_intent = classify_order_stall(
        _base_counts(risk_verdicts=10, approved_risk_verdicts=3),
        [{"reason": "approved", "n": 3}],
        {},
    )
    assert approved_without_intent["status"] == "APPROVED_VERDICT_INTENT_PERSISTENCE_GAP"

    no_orders = classify_order_stall(_base_counts(intents=7), [], {})
    assert no_orders["status"] == "INTENT_TO_ORDER_GAP"

    no_fills = classify_order_stall(_base_counts(intents=7, orders=7), [], {})
    assert no_fills["status"] == "ORDER_TO_FILL_GAP"

    post_only_gap = classify_order_stall(
        _base_counts(intents=7, orders=7, post_only_cross_orders=2),
        [],
        {},
    )
    assert post_only_gap["status"] == "ORDER_REJECT_OR_POST_ONLY_GAP"

    filled = classify_order_stall(_base_counts(intents=7, orders=7, fills=2), [], {})
    assert filled["status"] == "RECENT_FILL_FLOW_PRESENT"


def test_pre_gate_drilldown_summary_surfaces_unjoined_contexts() -> None:
    rows = [
        {
            "engine_mode": "demo",
            "strategy_name": "ma_crossover",
            "symbol": "REUSDT",
            "decision_type": "signal_generated",
            "context_rows": 549,
            "contexts_with_evaluation": 0,
            "contexts_with_risk": 0,
            "contexts_with_intent": 0,
            "contexts_with_order": 0,
            "contexts_with_fill": 0,
            "latest_context_ts": "2026-06-21T16:49:01+02:00",
        },
        {
            "engine_mode": "demo",
            "strategy_name": "flash_dip_buy",
            "symbol": "SUIUSDT",
            "decision_type": "signal_generated",
            "context_rows": 3,
            "contexts_with_evaluation": 3,
            "contexts_with_risk": 3,
            "contexts_with_intent": 1,
            "contexts_with_order": 1,
            "contexts_with_fill": 0,
            "latest_context_ts": "2026-06-21T02:00:00+02:00",
        },
    ]

    summary = summarize_pre_gate_drilldown(rows)

    assert summary["status"] == "TOP_CONTEXT_ROWS_HAVE_PARTIAL_DOWNSTREAM_JOIN"
    assert summary["scope"] == "top_limit_rows_only"
    assert summary["context_rows"] == 552
    assert summary["contexts_with_evaluation"] == 3
    assert summary["top_unjoined_context_rows"][0] == {
        "engine_mode": "demo",
        "strategy_name": "ma_crossover",
        "symbol": "REUSDT",
        "decision_type": "signal_generated",
        "unjoined_context_rows": 549,
        "latest_context_ts": "2026-06-21T16:49:01+02:00",
    }


def test_pre_gate_drilldown_summary_recognizes_observation_only_contexts() -> None:
    rows = [
        {
            "engine_mode": "demo",
            "strategy_name": "ma_crossover",
            "symbol": "REUSDT",
            "decision_type": "signal_generated",
            "context_rows": 549,
            "linucb_metadata_scopes": "signal_observation_only",
            "signal_observation_only_contexts": 549,
            "accepted_intent_bound_contexts": 0,
            "non_observation_scope_contexts": 0,
            "contexts_with_evaluation": 0,
            "contexts_with_risk": 0,
            "contexts_with_intent": 0,
            "contexts_with_order": 0,
            "contexts_with_fill": 0,
            "latest_context_ts": "2026-06-21T16:49:01+02:00",
        }
    ]

    summary = summarize_pre_gate_drilldown(rows)

    assert summary["status"] == "TOP_CONTEXT_ROWS_OBSERVATION_ONLY_NO_DOWNSTREAM_EXPECTED"
    assert summary["signal_observation_only_contexts"] == 549
    assert summary["accepted_intent_bound_contexts"] == 0
    assert summary["top_unjoined_context_rows"][0][
        "linucb_metadata_scopes"
    ] == "signal_observation_only"


def test_markdown_and_json_payload_surface_answers() -> None:
    cfg = AuditConfig(engine_modes=("demo", "live_demo"), lookback_hours=24)
    counts = _base_counts(
        decision_context_snapshots=100,
        candidate_evaluations=80,
        decision_features=70,
        rejected_decision_features=70,
        risk_verdicts=70,
        rejected_risk_verdicts=70,
    )
    risk_reasons = [
        {
            "reason": "cost_gate(JS-demo): estimated=-3.5bps < 0",
            "n": 70,
            "approved_n": 0,
            "rejected_n": 70,
            "latest_ts": "2026-06-21T00:00:00Z",
        }
    ]
    eval_outcomes = [
        {
            "evaluation_outcome": "reject",
            "evidence_source_tier": "evaluation_log",
            "n": 80,
            "symbols": 4,
            "latest_ts": "2026-06-21T00:00:00Z",
        }
    ]
    lineage = {"intents": 0, "intents_with_orders": 0, "intents_without_orders": 0}
    context_payload_scope = {
        "context_rows": 100,
        "signal_observation_only_contexts": 100,
        "accepted_intent_bound_contexts": 0,
        "non_observation_scope_contexts": 0,
        "missing_scope_contexts": 0,
        "distinct_scope_count": 1,
        "linucb_metadata_scopes": "signal_observation_only",
        "strategies": 1,
        "symbols": 1,
        "latest_context_ts": "2026-06-21T00:00:00Z",
        "avg_signal_count": 3.0,
    }
    pre_gate_drilldown = [
        {
            "engine_mode": "demo",
            "strategy_name": "ma_crossover",
            "symbol": "REUSDT",
            "decision_type": "signal_generated",
            "context_rows": 100,
            "contexts_with_evaluation": 0,
            "contexts_with_risk": 0,
            "contexts_with_intent": 0,
            "contexts_with_order": 0,
            "contexts_with_fill": 0,
            "latest_context_ts": "2026-06-21T00:00:00Z",
        }
    ]

    markdown = render_markdown(
        cfg,
        counts,
        risk_reasons,
        eval_outcomes,
        lineage,
        pre_gate_drilldown,
        context_payload_scope,
        generated="2026-06-21T00:00:00+00:00",
    )
    assert "COST_GATE_REJECTING_ALL_RECENT_ATTEMPTS" in markdown
    assert "Bounded demo-learning lane recommended: `True`" in markdown
    assert "candidate_evaluations" in markdown
    assert "## Context Payload Scope" in markdown
    assert "signal_observation_only" in markdown
    assert "## Pre-Gate Drilldown" in markdown
    assert "REUSDT" in markdown

    payload = build_json_payload(
        cfg,
        counts,
        risk_reasons,
        eval_outcomes,
        lineage,
        pre_gate_drilldown,
        context_payload_scope,
        generated="2026-06-21T00:00:00+00:00",
    )
    assert payload["schema_version"] == "demo_order_stall_audit_v1"
    assert payload["classification"]["answers"]["cost_gate_dominant"] is True
    assert payload["context_payload_scope"]["linucb_metadata_scopes"] == (
        "signal_observation_only"
    )
    assert (
        payload["pre_gate_drilldown_summary"]["status"]
        == "TOP_CONTEXT_ROWS_HAVE_NO_DOWNSTREAM_JOIN"
    )
