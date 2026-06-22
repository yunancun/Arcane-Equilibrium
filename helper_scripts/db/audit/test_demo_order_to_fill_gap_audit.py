from __future__ import annotations

import pytest

from helper_scripts.db.audit.demo_order_to_fill_gap_audit import (
    AuditConfig,
    build_order_touchability_sql,
    build_payload,
    classify_order,
    render_markdown,
    summarize_orders,
    validate_config,
)


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "engine_mode": "demo",
        "order_id": "oc_test",
        "intent_id": "intent-test",
        "context_id": "ctx-test",
        "order_ts": "2026-06-22T00:00:00+00:00",
        "symbol": "BNBUSDT",
        "side": "Buy",
        "strategy_name": "flash_dip_buy",
        "order_qty": 0.49,
        "order_price": None,
        "intent_price": 583.0,
        "intent_limit_price": 499.545,
        "maker_timeout_ms": 86400000,
        "effective_limit_price": 499.545,
        "effective_limit_price_source": "intents.details.limit_price",
        "order_type": "Limit",
        "time_in_force": "PostOnly",
        "order_status": "Working",
        "latest_to_status": "Working",
        "latest_reason": None,
        "any_fill_state": False,
        "any_cancelled_state": False,
        "any_rejected_state": False,
        "any_post_only_cross": False,
        "any_self_cancel": False,
        "fill_count": 0,
        "placement_best_bid": 583.5,
        "placement_best_ask": 583.7,
        "future_bbo_count": 600,
        "min_best_ask": 583.7,
        "max_best_bid": 584.7,
    }
    base.update(overrides)
    return base


def test_validate_config_bounds() -> None:
    validate_config(AuditConfig(engine_modes=("demo", "live_demo")))
    with pytest.raises(ValueError):
        validate_config(AuditConfig(engine_modes=()))
    with pytest.raises(ValueError):
        validate_config(AuditConfig(engine_modes=("unknown",)))
    with pytest.raises(ValueError):
        validate_config(AuditConfig(engine_modes=("demo",), lookback_hours=0))
    with pytest.raises(ValueError):
        validate_config(AuditConfig(engine_modes=("demo",), touch_window_minutes=0))
    with pytest.raises(ValueError):
        validate_config(AuditConfig(engine_modes=("demo",), placement_window_seconds=0))
    with pytest.raises(ValueError):
        validate_config(AuditConfig(engine_modes=("demo",), top_limit=0))
    with pytest.raises(ValueError):
        validate_config(AuditConfig(engine_modes=("demo",), deep_gap_bps=-1.0))


def test_sql_contract_is_read_only_and_covers_order_touchability_tables() -> None:
    sql = build_order_touchability_sql()

    for table in [
        "trading.orders",
        "trading.intents",
        "trading.order_state_changes",
        "trading.fills",
        "market.ob_top",
    ]:
        assert table in sql
    assert "engine_mode = ANY" in sql
    assert "effective_limit_price" in sql
    assert "^-?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)([eE][+-]?[0-9]+)?$" in sql
    assert "ILIKE '%%post_only_cross%%'" in sql
    assert "INSERT " not in sql.upper()
    assert "UPDATE " not in sql.upper()
    assert "DELETE " not in sql.upper()


def test_working_deep_passive_buy_limit_is_classified_no_touch() -> None:
    result = classify_order(_row(), deep_gap_bps=500.0)

    assert result["status"] == "WORKING_DEEP_PASSIVE_LIMIT_NO_TOUCH"
    assert result["bbo_touched_limit"] is False
    assert result["orders_price_missing"] is True
    assert result["effective_limit_price_inferred"] is True
    assert result["best_touch_gap_bps"] and result["best_touch_gap_bps"] > 1000.0


def test_self_cancelled_deep_limit_is_classified_as_timeout_no_touch() -> None:
    result = classify_order(
        _row(
            latest_to_status="Cancelled",
            latest_reason="exchange_status:Cancelled|reject=EC_PerCancelRequest|category=self_cancel",
            any_cancelled_state=True,
            any_self_cancel=True,
        ),
        deep_gap_bps=500.0,
    )

    assert result["status"] == "DAY_TIMEOUT_SELF_CANCEL_NO_TOUCH_DEEP_LIMIT"


def test_bbo_touched_without_fill_is_reconcile_required() -> None:
    result = classify_order(
        _row(effective_limit_price=584.0, min_best_ask=583.7),
        deep_gap_bps=500.0,
    )

    assert result["status"] == "BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED"
    assert result["bbo_touched_limit"] is True


def test_missing_effective_limit_price_is_explicit() -> None:
    result = classify_order(
        _row(
            order_price=None,
            intent_price=None,
            intent_limit_price=None,
            effective_limit_price=None,
            effective_limit_price_source=None,
        ),
        deep_gap_bps=500.0,
    )

    assert result["status"] == "MISSING_EFFECTIVE_LIMIT_PRICE"
    assert result["effective_limit_price_missing"] is True


def test_summary_routes_all_deep_no_touch_orders_to_touchability_gate() -> None:
    cfg = AuditConfig(engine_modes=("demo", "live_demo"))
    payload = build_payload(
        cfg=cfg,
        rows=[
            _row(order_id="oc_1"),
            _row(order_id="oc_2", symbol="XRPUSDT", effective_limit_price=0.9769, min_best_ask=1.1242),
        ],
        generated="2026-06-22T00:00:00+00:00",
    )
    markdown = render_markdown(payload)
    summary = payload["summary"]

    assert summary["status"] == "PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH"
    assert summary["counts"]["reviewed_orders"] == 2
    assert summary["counts"]["deep_passive_no_touch_orders"] == 2
    assert summary["answers"]["passive_limits_too_deep"] is True
    assert summary["answers"]["global_cost_gate_lowering_recommended"] is False
    assert summary["answers"]["order_authority_granted"] is False
    assert "Demo Order-To-Fill Gap Audit" in markdown
    assert "PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH" in markdown


def test_summary_prioritizes_touched_no_fill_over_deep_no_touch() -> None:
    orders = [
        {
            "classification": {"status": "WORKING_DEEP_PASSIVE_LIMIT_NO_TOUCH"},
            "fill_count": 0,
            "time_in_force": "PostOnly",
        },
        {
            "classification": {"status": "BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED"},
            "fill_count": 0,
            "time_in_force": "PostOnly",
        },
    ]

    summary = summarize_orders(orders)

    assert summary["status"] == "BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED"
    assert summary["counts"]["bbo_touched_no_fill_orders"] == 1
