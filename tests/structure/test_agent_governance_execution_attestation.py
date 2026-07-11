"""Out-of-band execution authenticity cannot be replaced by self-digests."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_execution_attestation import (  # noqa: E402
    validate_execution_attestations,
)


def _inputs() -> tuple[dict, dict, dict]:
    wave = {"record_digest": "sha256:" + "1" * 64}
    runtime = {
        "schema_version": "runtime_observation_receipt_v1",
        "receipt_digest": "sha256:" + "2" * 64,
    }
    effect = {"receipt_digest": "sha256:" + "3" * 64}
    return (
        {"waves": {wave["record_digest"]: wave}, "telemetry": {}},
        {"runtime": runtime},
        {"effect": effect},
    )


def test_packet_local_execution_self_digests_cannot_support_pass() -> None:
    captures, observations, effects = _inputs()

    errors = validate_execution_attestations(
        gate_verdict="PASS",
        captures=captures,
        observation_artifacts=observations,
        effect_receipts=effects,
        verifier=None,
    )

    assert len(errors) == 3
    assert all("lacks out-of-band execution attestation" in error for error in errors)


def test_trusted_host_capability_is_exact_digest_bound_and_fail_closed() -> None:
    captures, observations, effects = _inputs()
    anchors = {
        ("workflow_wave_record_v1", "sha256:" + "1" * 64),
        ("runtime_observation_receipt_v1", "sha256:" + "2" * 64),
        ("effect_adapter_result_v1", "sha256:" + "3" * 64),
    }

    def verifier(kind: str, digest: str, _artifact: dict) -> bool:
        return (kind, digest) in anchors

    assert validate_execution_attestations(
        gate_verdict="PASS",
        captures=captures,
        observation_artifacts=observations,
        effect_receipts=effects,
        verifier=verifier,
    ) == []

    effects["effect"]["receipt_digest"] = "sha256:" + "4" * 64
    assert validate_execution_attestations(
        gate_verdict="PASS",
        captures=captures,
        observation_artifacts=observations,
        effect_receipts=effects,
        verifier=verifier,
    ) == [
        "closure PASS lacks out-of-band execution attestation for "
        f"effect_adapter_result_v1 {'sha256:' + '4' * 64}"
    ]


def test_non_pass_verdict_does_not_claim_execution_authenticity() -> None:
    captures, observations, effects = _inputs()
    assert validate_execution_attestations(
        gate_verdict="UNVERIFIED",
        captures=captures,
        observation_artifacts=observations,
        effect_receipts=effects,
        verifier=None,
    ) == []
