from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from helper_scripts.db.audit import demo_data_flow_monitor as monitor
from helper_scripts.db.audit.demo_data_flow_monitor import (
    WindowFetchObservation,
    build_monitor_payload,
    build_timeout_monitor_payload,
    fetch_window_payloads,
    parse_windows,
    render_markdown,
    summarize_windows,
)


def _window(
    hours: int,
    *,
    status: str = "NO_RECENT_PIPELINE_DATA",
    data_status: str = "NOT_ACCUMULATING_RECENT_DATA",
    decisions: int = 0,
    risk: int = 0,
    rejected_risk: int = 0,
    intents: int = 0,
    orders: int = 0,
    fills: int = 0,
    cost_gate_rejects: int = 0,
    stale: bool = False,
) -> dict:
    risk_rows = []
    if cost_gate_rejects:
        risk_rows.append(
            {
                "reason": "cost_gate(JS-demo): estimated=-6.01bps < 0",
                "n": cost_gate_rejects,
                "rejected_n": cost_gate_rejects,
                "approved_n": 0,
            }
        )
    return {
        "lookback_hours": hours,
        "classification": {
            "status": status,
            "data_accumulation_status": data_status,
            "primary_blocker_stage": "risk_to_intents",
            "dominant_risk_category": {
                "category": "cost_gate" if cost_gate_rejects else None,
                "pct": 99.0 if cost_gate_rejects else None,
            },
            "data_flow_freshness": {
                "status": (
                    "LEARNING_DATA_FLOW_STALE"
                    if stale
                    else "LEARNING_DATA_FLOW_FRESH"
                ),
                "latest_learning_stage": "risk_verdicts" if risk else None,
                "latest_learning_ts_utc": "2026-06-22T00:00:00+00:00"
                if risk
                else None,
                "latest_learning_age_seconds": 7200 if stale else 30,
            },
            "answers": {"learning_data_flow_stale": stale},
        },
        "counts": {
            "decision_context_snapshots": 0,
            "candidate_evaluations": 0,
            "decision_features": decisions,
            "rejected_decision_features": decisions,
            "risk_verdicts": risk,
            "approved_risk_verdicts": 0,
            "rejected_risk_verdicts": rejected_risk,
            "intents": intents,
            "orders": orders,
            "fills": fills,
        },
        "risk_reason_top": risk_rows,
    }


def test_recent_empty_window_with_prior_orders_no_fills_is_explicit() -> None:
    summary = summarize_windows(
        [
            _window(1),
            _window(
                4,
                status="ORDER_TO_FILL_GAP",
                data_status="REJECT_OR_CANDIDATE_DATA_ACCUMULATING",
                decisions=2699,
                risk=2699,
                rejected_risk=2696,
                intents=3,
                orders=3,
                cost_gate_rejects=2696,
            ),
        ]
    )

    assert summary["status"] == "RECENT_WINDOW_EMPTY_PRIOR_ORDER_FLOW_NO_FILLS"
    assert summary["answers"]["short_window_empty"] is True
    assert summary["answers"]["cost_gate_rejects_recorded"] is True
    assert summary["answers"]["orders_present"] is True
    assert summary["answers"]["fills_present"] is False
    assert summary["answers"]["global_cost_gate_lowering_recommended"] is False
    assert summary["key_counts"]["broad_orders"] == 3
    assert summary["key_counts"]["broad_cost_gate_rejects"] == 2696


def test_recent_empty_window_with_cost_gate_reject_wall_no_orders() -> None:
    summary = summarize_windows(
        [
            _window(1),
            _window(
                24,
                status="COST_GATE_REJECTING_ALL_RECENT_ATTEMPTS",
                data_status="REJECT_OR_CANDIDATE_DATA_ACCUMULATING",
                decisions=10_000,
                risk=10_000,
                rejected_risk=10_000,
                cost_gate_rejects=10_000,
            ),
        ]
    )

    assert summary["status"] == "RECENT_WINDOW_EMPTY_COST_GATE_REJECT_WALL"
    assert summary["next_action"] == (
        "restore_fresh_demo_flow_then_continue_cost_gate_learning_lane"
    )


def test_no_data_any_window_and_fill_present_branches() -> None:
    empty = summarize_windows([_window(1), _window(4)])
    assert empty["status"] == "NO_DEMO_DATA_ANY_WINDOW"

    filled = summarize_windows(
        [
            _window(
                1,
                status="RECENT_FILL_FLOW_PRESENT",
                orders=2,
                fills=1,
            ),
            _window(
                24,
                status="RECENT_FILL_FLOW_PRESENT",
                orders=10,
                fills=4,
            ),
        ]
    )
    assert filled["status"] == "DEMO_FILL_FLOW_PRESENT"
    assert filled["answers"]["fills_present"] is True


def test_build_payload_and_markdown_surface_compact_windows() -> None:
    payload = build_monitor_payload(
        engine_modes=("demo", "live_demo"),
        windows=[
            _window(1),
            _window(
                4,
                status="ORDER_TO_FILL_GAP",
                data_status="REJECT_OR_CANDIDATE_DATA_ACCUMULATING",
                decisions=2699,
                risk=2699,
                rejected_risk=2696,
                intents=3,
                orders=3,
                cost_gate_rejects=2696,
            ),
        ],
        generated="2026-06-22T01:00:00+00:00",
    )
    markdown = render_markdown(payload)

    assert payload["schema_version"] == "demo_data_flow_monitor_v1"
    assert payload["summary"]["status"] == (
        "RECENT_WINDOW_EMPTY_PRIOR_ORDER_FLOW_NO_FILLS"
    )
    assert payload["windows"][1]["counts"]["risk_verdicts"] == 2699
    assert "Demo Data Flow Monitor" in markdown
    assert "RECENT_WINDOW_EMPTY_PRIOR_ORDER_FLOW_NO_FILLS" in markdown
    assert "cost_gate(JS-demo)" in markdown


def test_parse_windows_dedupes_and_validates_bounds() -> None:
    assert parse_windows([24, 1, 4, 4]) == [1, 4, 24]

    with pytest.raises(ValueError):
        parse_windows([])
    with pytest.raises(ValueError):
        parse_windows([0])
    with pytest.raises(ValueError):
        parse_windows([721])


def test_statement_timeout_first_window_returns_partial_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StatementTimeout(RuntimeError):
        pgcode = "57014"
        diag = SimpleNamespace(
            message_primary="canceling statement due to statement timeout"
        )

    def raise_timeout(*_args: object, **_kwargs: object) -> None:
        raise StatementTimeout("must not be copied into the observation")

    monkeypatch.setattr(
        "helper_scripts.db.audit.demo_data_flow_monitor.order_stall.fetch_audit",
        raise_timeout,
    )

    observation = fetch_window_payloads(
        object(),
        engine_modes=("demo", "live_demo"),
        windows=[1, 4, 24],
        top_limit=10,
        generated="2026-07-17T03:00:00+00:00",
    )

    assert observation.query_complete is False
    assert observation.requested_windows == (1, 4, 24)
    assert observation.completed_payloads == ()
    assert observation.failed_windows == (1,)


def test_timeout_payload_is_explicitly_partial_without_fabricated_window() -> None:
    payload = build_timeout_monitor_payload(
        engine_modes=("demo", "live_demo"),
        observation=WindowFetchObservation(
            requested_windows=(1, 4, 24),
            completed_payloads=(),
            failed_windows=(1,),
        ),
        generated="2026-07-17T03:00:00+00:00",
    )

    assert payload["schema_version"] == "demo_data_flow_monitor_v1"
    assert payload["summary"]["status"] == "READONLY_QUERY_TIMEOUT"
    assert payload["observation"] == {
        "status": "PARTIAL_QUERY_INCOMPLETE",
        "query_complete": False,
        "requested_windows": [1, 4, 24],
        "completed_windows": [],
        "failed_windows": [1],
        "not_attempted_windows": [4, 24],
        "stale_snapshot_reused": False,
    }
    assert payload["windows"] == []
    answers = payload["summary"]["answers"]
    assert answers["global_cost_gate_lowering_recommended"] is False
    assert answers["stale_snapshot_reused"] is False
    assert answers["query_complete"] is False
    assert all(
        answers[key] is False
        for key in (
            "candidate_selection_authority_granted",
            "cost_gate_change_authority_granted",
            "risk_change_authority_granted",
            "order_authority_granted",
            "proof_authority_granted",
            "serving_authority_granted",
            "promotion_authority_granted",
            "latest_authority_granted",
        )
    )


@pytest.mark.parametrize(
    ("failed_window", "completed_windows"),
    ((4, [1]), (24, [1, 4])),
)
def test_statement_timeout_preserves_only_fully_completed_prior_windows(
    monkeypatch: pytest.MonkeyPatch,
    failed_window: int,
    completed_windows: list[int],
) -> None:
    class StatementTimeout(RuntimeError):
        pgcode = "57014"
        diag = SimpleNamespace(
            message_primary="  CANCELING statement due to statement   timeout  "
        )

    def fetch(_conn: object, cfg: object) -> tuple[object, ...]:
        if cfg.lookback_hours == failed_window:
            raise StatementTimeout("internal query detail must stay out of artifacts")
        return (object(), object(), object(), object(), object(), object())

    def build(cfg: object, *_args: object, **_kwargs: object) -> dict:
        return _window(cfg.lookback_hours, decisions=cfg.lookback_hours * 10)

    monkeypatch.setattr(
        "helper_scripts.db.audit.demo_data_flow_monitor.order_stall.fetch_audit",
        fetch,
    )
    monkeypatch.setattr(
        "helper_scripts.db.audit.demo_data_flow_monitor.order_stall.build_json_payload",
        build,
    )

    observation = fetch_window_payloads(
        object(),
        engine_modes=("demo", "live_demo"),
        windows=[1, 4, 24],
        top_limit=10,
        generated="2026-07-17T03:00:00+00:00",
    )
    payload = build_timeout_monitor_payload(
        engine_modes=("demo", "live_demo"),
        observation=observation,
        generated="2026-07-17T03:00:00+00:00",
    )

    assert [
        row["lookback_hours"] for row in observation.completed_payloads
    ] == completed_windows
    assert observation.failed_windows == (failed_window,)
    assert payload["observation"]["completed_windows"] == completed_windows
    assert [row["lookback_hours"] for row in payload["windows"]] == completed_windows
    assert [row["counts"]["decision_features"] for row in payload["windows"]] == [
        hours * 10 for hours in completed_windows
    ]
    assert failed_window not in {
        row["lookback_hours"] for row in payload["windows"]
    }
    assert "internal query detail" not in json.dumps(payload)


@pytest.mark.parametrize(
    ("pgcode", "message_primary"),
    (
        ("57014", "canceling statement due to user request"),
        ("57014", None),
        ("57014", "canceling statement due to conflict with recovery"),
        ("57014", "canceling statement due to statement timeout."),
        ("08006", "canceling statement due to statement timeout"),
    ),
)
def test_non_statement_timeout_errors_are_reraised_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    pgcode: str,
    message_primary: str | None,
) -> None:
    class AuditFailure(RuntimeError):
        pass

    failure = AuditFailure("opaque failure")
    failure.pgcode = pgcode
    if message_primary is not None:
        failure.diag = SimpleNamespace(message_primary=message_primary)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(
        "helper_scripts.db.audit.demo_data_flow_monitor.order_stall.fetch_audit",
        fail,
    )

    with pytest.raises(AuditFailure) as caught:
        fetch_window_payloads(
            object(),
            engine_modes=("demo", "live_demo"),
            windows=[1, 4, 24],
            top_limit=10,
            generated="2026-07-17T03:00:00+00:00",
        )

    assert caught.value is failure


def test_timeout_shaped_payload_build_error_is_not_converted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BuildFailure(RuntimeError):
        pgcode = "57014"
        diag = SimpleNamespace(
            message_primary="canceling statement due to statement timeout"
        )

    failure = BuildFailure("builder failure")
    monkeypatch.setattr(
        monitor.order_stall,
        "fetch_audit",
        lambda *_a, **_k: (object(), object(), object(), object(), object(), object()),
    )

    def fail_build(*_args: object, **_kwargs: object) -> dict:
        raise failure

    monkeypatch.setattr(monitor.order_stall, "build_json_payload", fail_build)

    with pytest.raises(BuildFailure) as caught:
        fetch_window_payloads(
            object(),
            engine_modes=("demo", "live_demo"),
            windows=[1],
            top_limit=10,
            generated="2026-07-17T03:00:00+00:00",
        )

    assert caught.value is failure


def test_completed_observation_payloads_are_immutable_snapshots() -> None:
    source = _window(1, decisions=7)
    observation = WindowFetchObservation(
        requested_windows=(1, 4),
        completed_payloads=(source,),
        failed_windows=(4,),
    )
    source["counts"]["decision_features"] = 999

    assert observation.completed_payloads[0]["counts"]["decision_features"] == 7
    with pytest.raises(TypeError):
        observation.completed_payloads[0]["counts"]["decision_features"] = 8


def test_timeout_markdown_surfaces_partial_query_identity() -> None:
    payload = build_timeout_monitor_payload(
        engine_modes=("demo", "live_demo"),
        observation=WindowFetchObservation(
            requested_windows=(1, 4, 24),
            completed_payloads=(_window(1, decisions=7),),
            failed_windows=(4,),
        ),
        generated="2026-07-17T03:00:00+00:00",
    )

    markdown = render_markdown(payload)

    assert "READONLY_QUERY_TIMEOUT" in markdown
    assert "PARTIAL_QUERY_INCOMPLETE" in markdown
    assert "Query complete: `False`" in markdown
    assert "Requested windows: `1,4,24`" in markdown
    assert "Completed windows: `1`" in markdown
    assert "Failed windows: `4`" in markdown
    assert "Stale snapshot reused: `False`" in markdown


def test_main_closes_connection_before_building_and_writes_timeout_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []

    class Connection:
        def rollback(self) -> None:
            events.append("rollback")

        def set_session(self, **kwargs: object) -> None:
            assert kwargs == {"readonly": True, "autocommit": True}
            events.append("set_session")

        def close(self) -> None:
            events.append("close")

    output = tmp_path / "monitor.md"
    json_output = tmp_path / "monitor.json"
    args = SimpleNamespace(
        engine_modes=["demo", "live_demo"],
        windows=[1, 4, 24],
        top_limit=10,
        output=output,
        json_output=json_output,
    )
    observation = WindowFetchObservation(
        requested_windows=(1, 4, 24),
        completed_payloads=(_window(1, decisions=7),),
        failed_windows=(4,),
    )
    real_builder = monitor.build_timeout_monitor_payload

    def build_after_close(**kwargs: object) -> dict:
        assert events[-1] == "close"
        events.append("build")
        return real_builder(**kwargs)

    monkeypatch.setattr(monitor, "parse_args", lambda: args)
    monkeypatch.setattr(monitor, "connect_report_pg", lambda *_a, **_k: Connection())
    monkeypatch.setattr(monitor, "fetch_window_payloads", lambda *_a, **_k: observation)
    monkeypatch.setattr(monitor, "build_timeout_monitor_payload", build_after_close)

    assert monitor.main() == 0
    assert events == ["rollback", "set_session", "close", "build"]
    assert json.loads(json_output.read_text(encoding="utf-8"))["summary"][
        "status"
    ] == "READONLY_QUERY_TIMEOUT"
    assert "PARTIAL_QUERY_INCOMPLETE" in output.read_text(encoding="utf-8")


def test_main_success_outputs_remain_byte_equivalent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class Connection:
        def rollback(self) -> None:
            pass

        def set_session(self, **_kwargs: object) -> None:
            pass

        def close(self) -> None:
            pass

    output = tmp_path / "monitor.md"
    json_output = tmp_path / "monitor.json"
    args = SimpleNamespace(
        engine_modes=["demo", "live_demo"],
        windows=[1],
        top_limit=10,
        output=output,
        json_output=json_output,
    )
    source_window = _window(1, decisions=7, risk=7)
    observation = WindowFetchObservation(
        requested_windows=(1,),
        completed_payloads=(source_window,),
    )
    expected_payload = build_monitor_payload(
        engine_modes=("demo", "live_demo"),
        windows=[source_window],
        generated="2026-07-17T03:00:00+00:00",
    )
    expected_markdown = render_markdown(expected_payload)
    expected_json = (
        json.dumps(
            expected_payload,
            indent=2,
            sort_keys=True,
            default=monitor.order_stall._json_default,
        )
        + "\n"
    )

    monkeypatch.setattr(monitor, "parse_args", lambda: args)
    monkeypatch.setattr(monitor, "connect_report_pg", lambda *_a, **_k: Connection())
    monkeypatch.setattr(monitor, "fetch_window_payloads", lambda *_a, **_k: observation)
    monkeypatch.setattr(
        monitor,
        "build_monitor_payload",
        lambda **_kwargs: expected_payload,
    )

    assert monitor.main() == 0
    assert output.read_bytes() == expected_markdown.encode("utf-8")
    assert json_output.read_bytes() == expected_json.encode("utf-8")


def test_atomic_output_failure_preserves_existing_target_and_cleans_stage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "monitor.json"
    target.write_text("previous-complete-artifact\n", encoding="utf-8")

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(monitor.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        monitor._write_text_atomic(target, "new-artifact\n")

    assert target.read_text(encoding="utf-8") == "previous-complete-artifact\n"
    assert list(tmp_path.iterdir()) == [target]


def test_main_write_failure_propagates_after_connection_close(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []

    class Connection:
        def rollback(self) -> None:
            pass

        def set_session(self, **_kwargs: object) -> None:
            pass

        def close(self) -> None:
            events.append("close")

    args = SimpleNamespace(
        engine_modes=["demo", "live_demo"],
        windows=[1],
        top_limit=10,
        output=tmp_path / "monitor.md",
        json_output=None,
    )
    observation = WindowFetchObservation(
        requested_windows=(1,),
        completed_payloads=(_window(1),),
    )

    def fail_write(_path: Path, _text: str) -> None:
        assert events == ["close"]
        raise OSError("write failed")

    monkeypatch.setattr(monitor, "parse_args", lambda: args)
    monkeypatch.setattr(monitor, "connect_report_pg", lambda *_a, **_k: Connection())
    monkeypatch.setattr(monitor, "fetch_window_payloads", lambda *_a, **_k: observation)
    monkeypatch.setattr(monitor, "_write_text_atomic", fail_write)

    with pytest.raises(OSError, match="write failed"):
        monitor.main()

    assert events == ["close"]


def test_main_close_failure_is_nonzero_and_prevents_artifact_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = False

    class Connection:
        def rollback(self) -> None:
            pass

        def set_session(self, **_kwargs: object) -> None:
            pass

        def close(self) -> None:
            raise OSError("close failed")

    args = SimpleNamespace(
        engine_modes=["demo", "live_demo"],
        windows=[1],
        top_limit=10,
        output=None,
        json_output=None,
    )
    observation = WindowFetchObservation(
        requested_windows=(1,),
        completed_payloads=(_window(1),),
    )

    def record_build(**_kwargs: object) -> dict:
        nonlocal built
        built = True
        return {}

    monkeypatch.setattr(monitor, "parse_args", lambda: args)
    monkeypatch.setattr(monitor, "connect_report_pg", lambda *_a, **_k: Connection())
    monkeypatch.setattr(monitor, "fetch_window_payloads", lambda *_a, **_k: observation)
    monkeypatch.setattr(monitor, "build_monitor_payload", record_build)

    with pytest.raises(OSError, match="close failed"):
        monitor.main()

    assert built is False


def test_main_build_failure_propagates_after_connection_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class Connection:
        def rollback(self) -> None:
            pass

        def set_session(self, **_kwargs: object) -> None:
            pass

        def close(self) -> None:
            events.append("close")

    args = SimpleNamespace(
        engine_modes=["demo", "live_demo"],
        windows=[1],
        top_limit=10,
        output=None,
        json_output=None,
    )
    observation = WindowFetchObservation(
        requested_windows=(1,),
        completed_payloads=(_window(1),),
    )

    def fail_build(**_kwargs: object) -> dict:
        assert events == ["close"]
        raise RuntimeError("build failed")

    monkeypatch.setattr(monitor, "parse_args", lambda: args)
    monkeypatch.setattr(monitor, "connect_report_pg", lambda *_a, **_k: Connection())
    monkeypatch.setattr(monitor, "fetch_window_payloads", lambda *_a, **_k: observation)
    monkeypatch.setattr(monitor, "build_monitor_payload", fail_build)

    with pytest.raises(RuntimeError, match="build failed"):
        monitor.main()

    assert events == ["close"]
