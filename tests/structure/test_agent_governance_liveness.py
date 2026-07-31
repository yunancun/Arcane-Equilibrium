from __future__ import annotations

import inspect
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
SCHEMA = ROOT / ".codex/schemas/agent_liveness_adjudication_v1.schema.json"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_liveness as liveness  # noqa: E402
from agent_governance_liveness import adjudicate_agent_liveness  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


def test_stale_running_activity_fails_closed_to_unknown(monkeypatch) -> None:
    monkeypatch.setattr(
        liveness,
        "_trusted_utc_now",
        lambda: datetime(
            2026, 7, 30, 10, 1, 0, 1, tzinfo=timezone.utc
        ),
        raising=False,
    )

    result = adjudicate_agent_liveness(
        supported_activity={
            "schema_version": "supported_agent_activity_v1",
            "interface": "collaboration",
            "state": "RUNNING",
            "observed_at": "2026-07-30T10:00:00Z",
        },
        transcript_diagnostic={
            "schema_version": "private_jsonl_liveness_diagnostic_v1",
            "exists": False,
            "size_bytes": None,
            "mtime_ms": None,
        },
    )

    assert result["liveness_state"] == "UNKNOWN"
    assert result["activity_freshness"] == "STALE"
    assert result["activity_observed_at"] == "2026-07-30T10:00:00Z"
    assert result["adjudicated_at"] == "2026-07-30T10:01:00.000001Z"


@pytest.mark.parametrize("state", ["RUNNING", "WAITING"])
def test_future_active_activity_fails_closed_to_unknown(
    monkeypatch,
    state: str,
) -> None:
    monkeypatch.setattr(
        liveness,
        "_trusted_utc_now",
        lambda: datetime(2026, 7, 30, 9, 59, 59, 999999, tzinfo=timezone.utc),
    )

    result = adjudicate_agent_liveness(
        supported_activity={
            "schema_version": "supported_agent_activity_v1",
            "interface": "thread",
            "state": state,
            "observed_at": "2026-07-30T10:00:00Z",
        },
        transcript_diagnostic={
            "schema_version": "private_jsonl_liveness_diagnostic_v1",
            "exists": True,
            "size_bytes": 1,
            "mtime_ms": 1,
        },
    )

    assert result["liveness_state"] == "UNKNOWN"
    assert result["activity_freshness"] == "FUTURE"


def test_offset_activity_observed_at_is_canonicalized_to_utc_z(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        liveness,
        "_trusted_utc_now",
        lambda: datetime(2026, 7, 30, 10, 0, 30, tzinfo=timezone.utc),
    )

    result = adjudicate_agent_liveness(
        supported_activity={
            "schema_version": "supported_agent_activity_v1",
            "interface": "collaboration",
            "state": "RUNNING",
            "observed_at": "2026-07-30T12:00:00+02:00",
        },
        transcript_diagnostic={
            "schema_version": "private_jsonl_liveness_diagnostic_v1",
            "exists": False,
            "size_bytes": None,
            "mtime_ms": None,
        },
    )

    assert result["activity_observed_at"] == "2026-07-30T10:00:00Z"
    assert result["activity_freshness"] == "FRESH"
    assert result["liveness_state"] == "UNKNOWN"


@pytest.mark.parametrize(
    "clock",
    [
        lambda: datetime(2026, 7, 30, 10, 0, 30),
        lambda: "2026-07-30T10:00:30Z",
        lambda: (_ for _ in ()).throw(RuntimeError("clock unavailable")),
    ],
)
def test_unverifiable_trusted_clock_fails_closed_to_unknown(
    monkeypatch,
    clock,
) -> None:
    monkeypatch.setattr(liveness, "_trusted_utc_now", clock)

    result = adjudicate_agent_liveness(
        supported_activity={
            "schema_version": "supported_agent_activity_v1",
            "interface": "collaboration",
            "state": "RUNNING",
            "observed_at": "2026-07-30T10:00:00Z",
        },
        transcript_diagnostic={
            "schema_version": "private_jsonl_liveness_diagnostic_v1",
            "exists": False,
            "size_bytes": None,
            "mtime_ms": None,
        },
    )

    assert result["liveness_state"] == "UNKNOWN"
    assert result["activity_freshness"] == "UNVERIFIABLE"
    assert result["adjudicated_at"] is None


def test_exact_maximum_age_is_fresh_but_not_authenticated(monkeypatch) -> None:
    monkeypatch.setattr(
        liveness,
        "_trusted_utc_now",
        lambda: datetime(2026, 7, 30, 10, 1, tzinfo=timezone.utc),
    )

    result = adjudicate_agent_liveness(
        supported_activity={
            "schema_version": "supported_agent_activity_v1",
            "interface": "collaboration",
            "state": "WAITING",
            "observed_at": "2026-07-30T10:00:00Z",
        },
        transcript_diagnostic={
            "schema_version": "private_jsonl_liveness_diagnostic_v1",
            "exists": False,
            "size_bytes": None,
            "mtime_ms": None,
        },
    )

    assert result["liveness_state"] == "UNKNOWN"
    assert result["activity_freshness"] == "FRESH"
    assert result["activity_verification_status"] == "EXTERNAL_LIMIT"


def test_public_liveness_interface_has_no_caller_now_override() -> None:
    assert set(inspect.signature(adjudicate_agent_liveness).parameters) == {
        "supported_activity",
        "transcript_diagnostic",
    }


@pytest.mark.parametrize(
    ("forged_field", "forged_value"),
    [
        ("activity_identity", "host-call-123"),
        ("activity_sequence", 42),
        ("activity_head", "sha256:" + "a" * 64),
    ],
)
def test_caller_identity_sequence_or_head_self_assertion_is_rejected(
    forged_field: str,
    forged_value: object,
) -> None:
    activity = {
        "schema_version": "supported_agent_activity_v1",
        "interface": "collaboration",
        "state": "RUNNING",
        "observed_at": "2026-07-30T10:00:00Z",
        forged_field: forged_value,
    }

    with pytest.raises(
        ValueError,
        match="supported_activity fields do not match canonical contract",
    ):
        adjudicate_agent_liveness(
            supported_activity=activity,
            transcript_diagnostic={
                "schema_version": "private_jsonl_liveness_diagnostic_v1",
                "exists": False,
                "size_bytes": None,
                "mtime_ms": None,
            },
        )


def test_stale_terminal_activity_also_fails_closed_to_unknown(monkeypatch) -> None:
    monkeypatch.setattr(
        liveness,
        "_trusted_utc_now",
        lambda: datetime(2026, 7, 30, 10, 1, 1, tzinfo=timezone.utc),
    )

    result = adjudicate_agent_liveness(
        supported_activity={
            "schema_version": "supported_agent_activity_v1",
            "interface": "thread",
            "state": "COMPLETED",
            "observed_at": "2026-07-30T10:00:00Z",
        },
        transcript_diagnostic={
            "schema_version": "private_jsonl_liveness_diagnostic_v1",
            "exists": False,
            "size_bytes": None,
            "mtime_ms": None,
        },
    )

    assert result["liveness_state"] == "UNKNOWN"
    assert result["activity_freshness"] == "STALE"


def test_fresh_terminal_caller_claim_remains_unknown(monkeypatch) -> None:
    monkeypatch.setattr(
        liveness,
        "_trusted_utc_now",
        lambda: datetime(2026, 7, 30, 10, 0, 30, tzinfo=timezone.utc),
    )

    result = adjudicate_agent_liveness(
        supported_activity={
            "schema_version": "supported_agent_activity_v1",
            "interface": "thread",
            "state": "COMPLETED",
            "observed_at": "2026-07-30T10:00:00Z",
        },
        transcript_diagnostic={
            "schema_version": "private_jsonl_liveness_diagnostic_v1",
            "exists": False,
            "size_bytes": None,
            "mtime_ms": None,
        },
    )

    assert result["liveness_state"] == "UNKNOWN"
    assert result["activity_freshness"] == "FRESH"
    assert result["activity_verification_status"] == "EXTERNAL_LIMIT"


def test_newer_terminal_then_older_fresh_running_replay_stays_unknown(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        liveness,
        "_trusted_utc_now",
        lambda: datetime(2026, 7, 30, 10, 1, tzinfo=timezone.utc),
    )
    transcript = {
        "schema_version": "private_jsonl_liveness_diagnostic_v1",
        "exists": False,
        "size_bytes": None,
        "mtime_ms": None,
    }

    terminal = adjudicate_agent_liveness(
        supported_activity={
            "schema_version": "supported_agent_activity_v1",
            "interface": "thread",
            "state": "COMPLETED",
            "observed_at": "2026-07-30T10:00:59Z",
        },
        transcript_diagnostic=transcript,
    )
    replayed_running = adjudicate_agent_liveness(
        supported_activity={
            "schema_version": "supported_agent_activity_v1",
            "interface": "thread",
            "state": "RUNNING",
            "observed_at": "2026-07-30T10:00:58Z",
        },
        transcript_diagnostic=transcript,
    )

    assert terminal["activity_freshness"] == "FRESH"
    assert replayed_running["activity_freshness"] == "FRESH"
    assert terminal["liveness_state"] == "UNKNOWN"
    assert replayed_running["liveness_state"] == "UNKNOWN"
    assert replayed_running["activity_verification_status"] == "EXTERNAL_LIMIT"


def test_registry_owns_exact_liveness_freshness_policy() -> None:
    import agent_governance as governance

    registry = governance.load_registry()
    policy = registry["liveness_policy"]
    assert policy["max_observation_age_seconds"] == 60
    assert policy["max_future_skew_seconds"] == 0
    assert policy["clock_source"] == (
        "trusted_system_utc_no_caller_override_v1"
    )
    assert policy["policy_digest"] == governance.liveness_policy_digest(
        policy
    )

    drifted = deepcopy(registry)
    drifted_policy = drifted["liveness_policy"]
    drifted_policy["max_observation_age_seconds"] = 86_400
    drifted_policy["policy_digest"] = governance.liveness_policy_digest(
        drifted_policy
    )
    assert any(
        "exact 60-second maximum age" in error
        for error in governance.validate_registry(drifted, ROOT)
    )


def test_fabricated_fresh_timestamp_cannot_prove_host_activity(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        liveness,
        "_trusted_utc_now",
        lambda: datetime(2026, 7, 30, 10, 0, 30, tzinfo=timezone.utc),
    )
    result = adjudicate_agent_liveness(
        supported_activity={
            "schema_version": "supported_agent_activity_v1",
            "interface": "collaboration",
            "state": "RUNNING",
            "observed_at": "2026-07-30T10:00:00Z",
        },
        transcript_diagnostic={
            "schema_version": "private_jsonl_liveness_diagnostic_v1",
            "exists": False,
            "size_bytes": None,
            "mtime_ms": None,
        },
    )

    assert result["liveness_state"] == "UNKNOWN"
    assert result["activity_freshness"] == "FRESH"
    assert result["primary_evidence"] == "CALLER_ACTIVITY_UNVERIFIED"
    assert result["activity_verification_status"] == "EXTERNAL_LIMIT"
    assert result["activity_verification_reason"] == (
        "MANAGED_HOST_ACTIVITY_ADAPTER_UNAVAILABLE"
    )
    assert result["diagnostic_state"] == "UNAVAILABLE"
    assert result["automatic_stop"] is False


def test_oversized_transcript_is_only_a_runaway_diagnostic(monkeypatch) -> None:
    monkeypatch.setattr(
        liveness,
        "_trusted_utc_now",
        lambda: datetime(2026, 7, 30, 10, 0, 30, tzinfo=timezone.utc),
    )
    result = adjudicate_agent_liveness(
        supported_activity={
            "schema_version": "supported_agent_activity_v1",
            "interface": "thread",
            "state": "RUNNING",
            "observed_at": "2026-07-30T10:00:00Z",
        },
        transcript_diagnostic={
            "schema_version": "private_jsonl_liveness_diagnostic_v1",
            "exists": True,
            "size_bytes": 10 * 1024 * 1024 + 1,
            "mtime_ms": 1_775_037_600_000,
        },
    )

    assert result["liveness_state"] == "UNKNOWN"
    assert result["activity_verification_status"] == "EXTERNAL_LIMIT"
    assert result["diagnostic_state"] == "RUNAWAY_SUSPECT"
    assert result["automatic_stop"] is False


def test_liveness_adjudication_has_an_exact_public_schema(monkeypatch) -> None:
    monkeypatch.setattr(
        liveness,
        "_trusted_utc_now",
        lambda: datetime(2026, 7, 30, 10, 0, 30, tzinfo=timezone.utc),
    )
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    result = adjudicate_agent_liveness(
        supported_activity={
            "schema_version": "supported_agent_activity_v1",
            "interface": "collaboration",
            "state": "UNAVAILABLE",
            "observed_at": "2026-07-30T10:00:00Z",
        },
        transcript_diagnostic={
            "schema_version": "private_jsonl_liveness_diagnostic_v1",
            "exists": True,
            "size_bytes": 1024,
            "mtime_ms": 1_775_037_600_000,
        },
    )

    assert schema["$id"] == "agent_liveness_adjudication_v1.schema.json"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["liveness_state"] == {"const": "UNKNOWN"}
    assert schema["properties"]["activity_verification_status"] == {
        "const": "EXTERNAL_LIMIT"
    }
    assert schema["properties"]["activity_observed_at"]["pattern"] == "Z$"
    assert set(result) == set(schema["required"])
    assert schema_subset_errors(result, schema, schema) == []
    assert result["liveness_state"] == "UNKNOWN"
    assert result["diagnostic_state"] == "AVAILABLE"

    forged = dict(result)
    forged["liveness_state"] = "RUNNING"
    assert schema_subset_errors(forged, schema, schema)

    noncanonical = dict(result)
    noncanonical["activity_observed_at"] = "2026-07-30T12:00:00+02:00"
    assert schema_subset_errors(noncanonical, schema, schema)


def test_liveness_adjudication_is_exposed_through_the_public_facade() -> None:
    import agent_governance as governance

    assert "adjudicate_agent_liveness" in governance.__all__
    assert governance.adjudicate_agent_liveness is adjudicate_agent_liveness
    assert "liveness_policy_digest" in governance.__all__
    assert "registry_liveness_policy_errors" in governance.__all__
