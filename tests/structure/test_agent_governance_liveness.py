from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
SCHEMA = ROOT / ".codex/schemas/agent_liveness_adjudication_v1.schema.json"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_liveness import adjudicate_agent_liveness  # noqa: E402


def test_supported_running_activity_survives_missing_private_transcript() -> None:
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

    assert result["liveness_state"] == "RUNNING"
    assert result["primary_evidence"] == "SUPPORTED_COLLABORATION_ACTIVITY"
    assert result["diagnostic_state"] == "UNAVAILABLE"
    assert result["automatic_stop"] is False


def test_oversized_transcript_is_only_a_runaway_diagnostic() -> None:
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

    assert result["liveness_state"] == "RUNNING"
    assert result["diagnostic_state"] == "RUNAWAY_SUSPECT"
    assert result["automatic_stop"] is False


def test_liveness_adjudication_has_an_exact_public_schema() -> None:
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
    assert set(result) == set(schema["required"])
    assert result["liveness_state"] == "UNKNOWN"
    assert result["diagnostic_state"] == "AVAILABLE"


def test_liveness_adjudication_is_exposed_through_the_public_facade() -> None:
    import agent_governance as governance

    assert "adjudicate_agent_liveness" in governance.__all__
    assert governance.adjudicate_agent_liveness is adjudicate_agent_liveness
