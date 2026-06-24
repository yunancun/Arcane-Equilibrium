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


def _source_status(head: str = TARGET_HEAD, *, ready: bool = True) -> dict:
    return {
        "git_head": head,
        "git_head_short": head[:8],
        "expected_head_status": "MATCH" if head == TARGET_HEAD else "MISMATCH",
        "source_activation_status": "SYNCED_CLEAN" if ready else "DIRTY",
        "source_activation_ready": ready,
    }


def _artifact_status(*, mm_missing_fields: list[str] | None = None, friction_present: bool = True) -> dict:
    return {
        "artifacts": [
            {
                "name": "mm_current_fee_confirmation_latest",
                "present": True,
                "schema_version": "mm_current_fee_confirmation_packet_v1",
                "status": "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_REPEAT_WINDOW",
                "missing_required_fields": mm_missing_fields or [],
            },
            {
                "name": "false_negative_candidate_friction_scorecard_latest",
                "present": friction_present,
                "schema_version": "false_negative_candidate_friction_scorecard_v1",
                "status": (
                    "FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY"
                    if friction_present
                    else None
                ),
                "answers": {
                    "global_cost_gate_lowering_recommended": False,
                    "probe_authority_granted": False,
                    "order_authority_granted": False,
                    "promotion_evidence": False,
                },
            },
        ]
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
    assert packet["source_checkout"]["status"] == "SOURCE_CHECKOUT_NOT_SUPPLIED"
    assert packet["artifact_compatibility"]["status"] == (
        "ARTIFACT_COMPATIBILITY_NOT_SUPPLIED"
    )
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


def test_runtime_health_hygiene_detects_source_head_mismatch() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status=_source_status(OLD_HEAD),
        artifact_status=_artifact_status(),
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "RUNTIME_SOURCE_HEAD_MISMATCH"
    assert packet["answers"]["runtime_source_drift_present"] is True
    assert packet["source_checkout"]["runtime_source_head"] == OLD_HEAD
    assert packet["next_actions"] == [
        "operator_review_runtime_source_sync_to_target_head"
    ]
    assert packet["answers"]["order_authority_granted"] is False


def test_runtime_health_hygiene_source_status_unavailable_is_incomplete() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status=None,
        source_status_error="missing",
        artifact_status=_artifact_status(),
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "RUNTIME_HEALTH_HYGIENE_EVIDENCE_INCOMPLETE"
    assert packet["source_checkout"]["status"] == (
        "SOURCE_CHECKOUT_SNAPSHOT_UNAVAILABLE"
    )
    assert packet["answers"]["operator_action_required"] is True
    assert packet["next_actions"] == [
        "capture_read_only_runtime_source_checkout_snapshot"
    ]


def test_runtime_health_hygiene_rejects_empty_supplied_source_status() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status={},
        artifact_status=_artifact_status(),
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "RUNTIME_HEALTH_HYGIENE_EVIDENCE_INCOMPLETE"
    assert packet["source_checkout"]["status"] == "SOURCE_CHECKOUT_EVIDENCE_MISSING"
    assert packet["answers"]["runtime_source_drift_present"] is False
    assert packet["next_actions"] == [
        "capture_read_only_runtime_source_checkout_snapshot",
    ]


def test_runtime_health_hygiene_detects_mm_v466_artifact_field_drift() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status=_source_status(),
        artifact_status=_artifact_status(
            mm_missing_fields=[
                "summary.candidate_observed_independent_windows",
                "summary.repeat_window_design_status",
                "repeat_window_design.max_safe_next_action",
            ]
        ),
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "CANONICAL_ARTIFACT_COMPATIBILITY_DRIFT"
    assert packet["answers"]["artifact_compatibility_drift_present"] is True
    assert packet["artifact_compatibility"]["issues"][0]["artifact"] == (
        "mm_current_fee_confirmation_latest"
    )
    assert "refresh_or_quarantine_stale_canonical_profit_learning_artifacts" in (
        packet["next_actions"]
    )


def test_runtime_health_hygiene_detects_missing_friction_scorecard() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status=_source_status(),
        artifact_status=_artifact_status(friction_present=False),
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "CANONICAL_ARTIFACT_COMPATIBILITY_DRIFT"
    assert packet["artifact_compatibility"]["issues"] == [
        {
            "artifact": "false_negative_candidate_friction_scorecard_latest",
            "issue": "missing",
        }
    ]


def test_runtime_health_hygiene_rejects_incomplete_artifact_snapshot() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status=_source_status(),
        artifact_status={
            "artifacts": [{
                "name": "bounded_probe_operator_authorization_latest",
                "present": True,
                "schema_version": "bounded_demo_probe_operator_authorization_packet_v1",
                "status": "READY_FOR_OPERATOR_AUTHORIZATION_REVIEW",
            }]
        },
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "CANONICAL_ARTIFACT_COMPATIBILITY_DRIFT"
    assert packet["artifact_compatibility"]["issues"] == [
        {
            "artifact": "mm_current_fee_confirmation_latest",
            "issue": "check_not_supplied",
        },
        {
            "artifact": "false_negative_candidate_friction_scorecard_latest",
            "issue": "check_not_supplied",
        },
    ]


def test_runtime_health_hygiene_rejects_empty_supplied_artifact_status() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status=_source_status(),
        artifact_status={},
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "CANONICAL_ARTIFACT_COMPATIBILITY_DRIFT"
    assert packet["artifact_compatibility"]["issues"] == [
        {
            "artifact": "mm_current_fee_confirmation_latest",
            "issue": "check_not_supplied",
        },
        {
            "artifact": "false_negative_candidate_friction_scorecard_latest",
            "issue": "check_not_supplied",
        },
    ]


def test_runtime_health_hygiene_current_status_beats_stale_friction_latest() -> None:
    artifact_status = _artifact_status(friction_present=True)
    artifact_status["friction_scorecard_current_status"] = {
        "enabled": False,
        "status": "DISABLED",
        "rc": 0,
    }
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status=_source_status(),
        artifact_status=artifact_status,
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "CANONICAL_ARTIFACT_COMPATIBILITY_DRIFT"
    assert packet["artifact_compatibility"]["issues"] == [
        {
            "artifact": "false_negative_candidate_friction_scorecard_latest",
            "issue": "current_status_not_clean",
            "current_status": {
                "status": "DISABLED",
                "rc": 0,
                "enabled": False,
                "reason": None,
            },
        }
    ]


def test_runtime_health_hygiene_rejects_supplied_authority_signal() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status=_source_status(),
        artifact_status={
            "main_cost_gate_adjustment": "LOWER",
            **_artifact_status(),
        },
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "RUNTIME_HEALTH_HYGIENE_BOUNDARY_VIOLATION"
    assert "main_cost_gate_adjustment" in packet["reason"]
    assert packet["answers"]["authority_boundary_violation_present"] is True
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert packet["answers"]["probe_authority_granted"] is False


def test_runtime_health_hygiene_rejects_truthy_supplied_authority_signal() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status={
            **_source_status(),
            "order_authority_granted": "true",
        },
        artifact_status={
            **_artifact_status(),
            "promotion_proof": 1,
        },
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "RUNTIME_HEALTH_HYGIENE_BOUNDARY_VIOLATION"
    assert "order_authority_granted" in packet["reason"]
    assert packet["answers"]["authority_boundary_violation_present"] is True
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False


def test_runtime_health_hygiene_rejects_live_authority_signal_names() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status={
            **_api_status(service_active=True),
            "live_authority": "GRANTED",
        },
        source_status={
            **_source_status(),
            "active_runtime_authority": True,
        },
        artifact_status={
            **_artifact_status(),
            "live_authority_granted": True,
        },
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "RUNTIME_HEALTH_HYGIENE_BOUNDARY_VIOLATION"
    assert "live_authority" in packet["reason"]
    assert packet["answers"]["authority_boundary_violation_present"] is True
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["probe_authority_granted"] is False


def test_runtime_health_hygiene_rejects_bounded_authorization_object_signal_names() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status=_source_status(),
        artifact_status={
            **_artifact_status(),
            "bounded_demo_probe_authorized": True,
            "operator_authorization_object_emitted": True,
            "probe_authority_granted_in_authorization_object": True,
            "order_authority_granted_in_authorization_object": True,
            "writer_enabled": True,
        },
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "RUNTIME_HEALTH_HYGIENE_BOUNDARY_VIOLATION"
    assert "bounded_demo_probe_authorized" in packet["reason"]
    assert packet["answers"]["authority_boundary_violation_present"] is True
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["probe_authority_granted"] is False


def test_runtime_health_hygiene_rejects_flattened_authority_status_signal_names() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status=_source_status(),
        artifact_status={
            **_artifact_status(),
            "bounded_probe_operator_authorization_object_emitted": True,
            "bounded_probe_operator_authorization_bounded_demo_probe_authorized": True,
            "bounded_probe_operator_authorization_writer_enabled": True,
            "runtime_writer_enabled": True,
        },
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "RUNTIME_HEALTH_HYGIENE_BOUNDARY_VIOLATION"
    assert "bounded_probe_operator_authorization_object_emitted" in packet["reason"]
    assert packet["answers"]["authority_boundary_violation_present"] is True
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["probe_authority_granted"] is False


def test_runtime_health_hygiene_rejects_prefixed_authority_suffixes() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status=_source_status(),
        artifact_status={
            **_artifact_status(),
            "bounded_probe_operator_authorization_active_runtime_order_authority": True,
            "bounded_probe_operator_authorization_active_runtime_probe_authority": True,
            "false_negative_candidate_friction_scorecard_probe_authority_granted": True,
            "false_negative_candidate_friction_scorecard_order_authority_granted": True,
            "probe_authority_granted_in_object": True,
            "order_authority_granted_in_object": True,
            "runtime_runner_probe_authority_granted_in_object": True,
            "runtime_runner_order_authority_granted_in_object": True,
            "false_negative_candidate_friction_scorecard_promotion_evidence": True,
            "false_negative_candidate_friction_scorecard_main_cost_gate_adjustment": "LOWER",
        },
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "RUNTIME_HEALTH_HYGIENE_BOUNDARY_VIOLATION"
    assert "active_runtime_order_authority" in packet["reason"]
    assert packet["answers"]["authority_boundary_violation_present"] is True
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["probe_authority_granted"] is False


def test_runtime_health_hygiene_combines_source_and_artifact_drift() -> None:
    packet = build_runtime_health_hygiene_packet(
        crontab_text=_crontab(OLD_HEAD),
        target_source_head=TARGET_HEAD,
        api_service_status=_api_status(service_active=True),
        source_status=_source_status(OLD_HEAD),
        artifact_status=_artifact_status(friction_present=False),
        now_utc=dt.datetime(2026, 6, 24, 6, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "RUNTIME_HEALTH_HYGIENE_DRIFT"
    assert packet["reason"] == "multiple_runtime_health_hygiene_drifts_present"
    assert packet["next_actions"] == [
        "operator_reinstall_or_update_demo_learning_cron_expected_head_pins",
        "operator_review_runtime_source_sync_to_target_head",
        "refresh_or_quarantine_stale_canonical_profit_learning_artifacts",
    ]
