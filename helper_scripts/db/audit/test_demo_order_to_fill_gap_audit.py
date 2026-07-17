from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest

from helper_scripts.db.audit import demo_order_to_fill_gap_audit as audit
from helper_scripts.db.audit.demo_order_to_fill_gap_audit import (
    AuditConfig,
    build_order_touchability_sql,
    build_payload,
    build_timeout_audit_payload,
    classify_order,
    render_markdown,
    summarize_orders,
    validate_config,
)
from helper_scripts.research.cost_gate_learning_lane.bounded_probe_touchability_preflight import (
    build_bounded_demo_probe_touchability_preflight,
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


def test_main_statement_timeout_writes_non_authoritative_partial_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class StatementTimeout(RuntimeError):
        pgcode = "57014"
        diag = SimpleNamespace(
            message_primary="canceling statement due to statement timeout"
        )

    class Connection:
        closed = False

        def rollback(self) -> None:
            pass

        def set_session(self, **_kwargs: object) -> None:
            pass

        def close(self) -> None:
            self.closed = True

    connection = Connection()
    json_output = tmp_path / "order-gap.json"
    markdown_output = tmp_path / "order-gap.md"

    def raise_timeout(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        raise StatementTimeout("query text and connection details must not leak")

    monkeypatch.setattr(audit, "connect_report_pg", lambda *_args, **_kwargs: connection)
    monkeypatch.setattr(audit, "fetch_order_rows", raise_timeout)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "demo_order_to_fill_gap_audit.py",
            "--engine-mode",
            "demo",
            "--engine-mode",
            "live_demo",
            "--output",
            str(markdown_output),
            "--json-output",
            str(json_output),
        ],
    )

    assert audit.main() == 0
    assert connection.closed is True

    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "demo_order_to_fill_gap_audit_v1"
    assert payload["query_complete"] is False
    assert payload["stale_snapshot_reused"] is False
    assert payload["summary"]["status"] == "READONLY_QUERY_TIMEOUT"
    assert payload["summary"]["query_complete"] is False
    assert payload["summary"]["stale_snapshot_reused"] is False
    assert payload["observation"] == {
        "status": "PARTIAL_QUERY_INCOMPLETE",
        "query_complete": False,
        "requested_queries": ["order_touchability"],
        "completed_queries": [],
        "failed_queries": ["order_touchability"],
        "stale_snapshot_reused": False,
    }
    assert payload["orders"] == []
    answers = payload["summary"]["answers"]
    assert answers["partial_observation"] is True
    assert answers["query_complete"] is False
    assert answers["stale_snapshot_reused"] is False
    assert all(
        answers[key] is False
        for key in (
            "global_cost_gate_lowering_recommended",
            "candidate_selection_authority_granted",
            "cost_gate_change_authority_granted",
            "risk_change_authority_granted",
            "order_authority_granted",
            "probe_authority_granted",
            "proof_authority_granted",
            "serving_authority_granted",
            "promotion_authority_granted",
            "latest_authority_granted",
            "promotion_evidence",
        )
    )
    markdown = markdown_output.read_text(encoding="utf-8")
    assert "READONLY_QUERY_TIMEOUT" in markdown
    assert "Query complete: `False`" in markdown
    assert "Stale snapshot reused: `False`" in markdown
    assert "query text and connection details" not in json_output.read_text(
        encoding="utf-8"
    )
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_writer_fsyncs_file_and_parent_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    synced_kinds: list[str] = []
    real_fsync = audit.os.fsync

    def record_fsync(fd: int) -> None:
        mode = audit.os.fstat(fd).st_mode
        synced_kinds.append("directory" if stat.S_ISDIR(mode) else "file")
        real_fsync(fd)

    monkeypatch.setattr(audit.os, "fsync", record_fsync)

    target = tmp_path / "nested" / "artifact.json"
    audit._write_text_atomic(target, "{}\n")

    assert target.read_text(encoding="utf-8") == "{}\n"
    assert synced_kinds == ["file", "directory"]


def test_main_reraises_non_statement_timeout_without_publishing_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class NonTimeout(RuntimeError):
        pgcode = "40001"
        diag = SimpleNamespace(
            message_primary="canceling statement due to statement timeout"
        )

    class Connection:
        closed = False

        def rollback(self) -> None:
            pass

        def set_session(self, **_kwargs: object) -> None:
            pass

        def close(self) -> None:
            self.closed = True

    connection = Connection()
    json_output = tmp_path / "must-not-exist.json"
    markdown_output = tmp_path / "must-not-exist.md"
    error = NonTimeout("serialization failure")

    def raise_non_timeout(
        *_args: object, **_kwargs: object
    ) -> list[dict[str, object]]:
        raise error

    monkeypatch.setattr(audit, "connect_report_pg", lambda *_args, **_kwargs: connection)
    monkeypatch.setattr(audit, "fetch_order_rows", raise_non_timeout)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "demo_order_to_fill_gap_audit.py",
            "--output",
            str(markdown_output),
            "--json-output",
            str(json_output),
        ],
    )

    with pytest.raises(NonTimeout) as caught:
        audit.main()

    assert caught.value is error
    assert connection.closed is True
    assert json_output.exists() is False
    assert markdown_output.exists() is False


@pytest.mark.parametrize(
    ("pgcode", "message_primary", "expected"),
    (
        (
            "57014",
            "  CANCELING statement due to statement   timeout  ",
            True,
        ),
        ("57014", "canceling statement due to user request", False),
        ("08006", "canceling statement due to statement timeout", False),
        (None, "canceling statement due to statement timeout", False),
    ),
)
def test_statement_timeout_detection_requires_sqlstate_and_primary_message(
    pgcode: str | None,
    message_primary: str,
    expected: bool,
) -> None:
    class PgFailure(RuntimeError):
        pass

    failure = PgFailure("details are not classifier input")
    failure.pgcode = pgcode
    failure.diag = SimpleNamespace(message_primary=message_primary)

    assert audit._is_statement_timeout(failure) is expected


def test_timeout_artifact_keeps_touchability_consumer_fail_closed() -> None:
    generated = "2026-07-17T04:00:00+00:00"
    timeout_audit = build_timeout_audit_payload(
        cfg=AuditConfig(engine_modes=("demo", "live_demo")),
        generated=generated,
    )
    preflight = {
        "schema_version": "sealed_horizon_bounded_demo_probe_preflight_v1",
        "generated_at_utc": generated,
        "status": "READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION",
        "side_cell_key": "ma_crossover|BTCUSDT|Sell",
        "outcome_horizon_minutes": 240,
        "answers": {
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "bounded_demo_probe_design": {
            "schema_version": "bounded_demo_probe_design_v1",
            "status": "OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN",
            "candidate": {
                "side_cell_key": "ma_crossover|BTCUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "outcome_horizon_minutes": 240,
            },
            "suggested_initial_probe_limits": {
                "active": False,
                "requires_separate_operator_authorization": True,
            },
            "authority_boundary": {
                "global_cost_gate_lowering_recommended": False,
                "main_cost_gate_adjustment": "NONE",
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            },
        },
    }

    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=preflight,
        order_to_fill_gap_audit=timeout_audit,
        now_utc=dt.datetime(2026, 7, 17, 4, 1, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "TOUCHABILITY_REVIEW_REQUIRED"
    assert packet["order_touchability"]["status"] == "READONLY_QUERY_TIMEOUT"
    assert packet["answers"]["ready_for_operator_touchability_review"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False
    assert packet["placement_requirements"]["active"] is False
