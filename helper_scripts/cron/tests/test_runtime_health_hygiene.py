from __future__ import annotations

import datetime as dt

from helper_scripts.cron.runtime_health_hygiene import (
    build_runtime_health_hygiene_packet,
    render_markdown,
)


TARGET_HEAD = "757dc2844ad03b47723472f88cd0407b34cf9a06"
OLD_HEAD = "c88deea7"


def _crontab(head: str = TARGET_HEAD) -> str:
    return "\n".join(
        [
            (
                "7,37 * * * * OPENCLAW_DEMO_LEARNING_EVIDENCE_EXPECTED_HEAD="
                f"{head} OPENCLAW_EXPECTED_SOURCE_HEAD={head} "
                "/srv/helper_scripts/cron/demo_learning_evidence_audit_cron.sh"
            ),
            (
                "22 * * * * OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD="
                f"{head} OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD={head} "
                "/srv/helper_scripts/cron/sealed_horizon_probe_preflight_cron.sh"
            ),
            (
                "27 * * * * OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD="
                f"{head} OPENCLAW_EXPECTED_SOURCE_HEAD={head} "
                "/srv/helper_scripts/cron/cost_gate_learning_lane_cron.sh"
            ),
            (
                "32 * * * * OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_EXPECTED_HEAD="
                f"{head} OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD={head} "
                "/srv/helper_scripts/cron/demo_learning_stack_healthcheck_cron.sh"
            ),
        ]
    )


def _api_status(*, service_active: bool = True) -> dict:
    return {
        "api_reachable": True,
        "uvicorn_process_present": True,
        "openclaw_trading_api_service_active": service_active,
        "openclaw_trading_api_service_status": (
            "active" if service_active else "inactive"
        ),
        "process_owner": "uvicorn",
    }


def test_runtime_health_hygiene_detects_cron_expected_head_drift() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(OLD_HEAD),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(),
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "CRON_EXPECTED_HEAD_DRIFT"
    assert packet["answers"]["cron_expected_head_drift_present"] is True
    assert packet["answers"]["api_service_ownership_drift_present"] is False
    assert packet["answers"]["crontab_mutation_performed"] is False
    assert packet["answers"]["service_restart_performed"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert len(packet["cron_expected_head"]["mismatched_entries"]) == 4
    assert packet["next_actions"] == [
        "operator_reinstall_or_update_demo_learning_cron_expected_head_pins"
    ]


def test_runtime_health_hygiene_detects_api_service_ownership_drift() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=False),
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "API_SERVICE_OWNERSHIP_DRIFT"
    assert packet["answers"]["cron_expected_head_drift_present"] is False
    assert packet["answers"]["api_service_ownership_drift_present"] is True
    assert packet["api_service_ownership"]["api_reachable"] is True
    assert packet["api_service_ownership"]["uvicorn_process_present"] is True
    assert packet["api_service_ownership"][
        "openclaw_trading_api_service_active"
    ] is False
    assert packet["next_actions"] == [
        "operator_choose_single_trading_api_service_owner_then_restart_under_that_owner"
    ]


def test_runtime_health_hygiene_combines_cron_and_api_drift() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(OLD_HEAD),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=False),
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "RUNTIME_HEALTH_HYGIENE_DRIFT"
    assert packet["answers"]["operator_action_required"] is True
    assert packet["next_actions"] == [
        "operator_reinstall_or_update_demo_learning_cron_expected_head_pins",
        "operator_choose_single_trading_api_service_owner_then_restart_under_that_owner",
    ]


def test_runtime_health_hygiene_clean_snapshot_is_source_only() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )
    markdown = render_markdown(packet)

    assert packet["status"] == "RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY"
    assert packet["answers"]["operator_action_required"] is False
    assert packet["answers"]["runtime_mutation_performed"] is False
    assert packet["answers"]["pg_query_performed"] is False
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert "no systemctl/ps/curl/PG/Bybit call" in markdown


def test_runtime_health_hygiene_requires_target_head() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=None,
        api_service_status=_api_status(service_active=True),
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "RUNTIME_HEALTH_HYGIENE_EVIDENCE_INCOMPLETE"
    assert packet["cron_expected_head"]["status"] == "TARGET_SOURCE_HEAD_MISSING"
    assert packet["answers"]["operator_action_required"] is True
    assert packet["next_actions"] == [
        "supply_target_source_head_before_hygiene_decision"
    ]


def test_runtime_health_hygiene_rejects_dangerously_short_expected_head() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab("7"),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "CRON_EXPECTED_HEAD_DRIFT"
    assert packet["answers"]["operator_action_required"] is True
    assert packet["cron_expected_head"]["invalid_expected_head_entries"] == [
        {
            "component": "demo_learning_evidence",
            "expected_head": "7",
            "validation_error": "invalid_length",
            "expected_head_var": "OPENCLAW_DEMO_LEARNING_EVIDENCE_EXPECTED_HEAD",
        },
        {
            "component": "sealed_horizon_probe_preflight",
            "expected_head": "7",
            "validation_error": "invalid_length",
            "expected_head_var": "OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD",
        },
        {
            "component": "cost_gate_learning_lane",
            "expected_head": "7",
            "validation_error": "invalid_length",
            "expected_head_var": "OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD",
        },
        {
            "component": "demo_learning_stack_healthcheck",
            "expected_head": "7",
            "validation_error": "invalid_length",
            "expected_head_var": (
                "OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_EXPECTED_HEAD"
            ),
        },
    ]
    assert packet["next_actions"] == [
        "operator_reinstall_or_update_demo_learning_cron_expected_head_pins"
    ]


def test_runtime_health_hygiene_does_not_clean_ambiguous_api_snapshot() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status={
            "api_reachable": False,
            "uvicorn_process_present": False,
            "openclaw_trading_api_service_active": True,
            "openclaw_trading_api_service_status": "active",
            "process_owner": "systemd",
        },
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["api_service_ownership"]["status"] == "API_SERVICE_REVIEW_REQUIRED"
    assert packet["status"] == "API_SERVICE_REVIEW_REQUIRED"
    assert packet["answers"]["operator_action_required"] is True
    assert packet["next_actions"] == [
        "operator_review_trading_api_service_ownership_snapshot"
    ]
