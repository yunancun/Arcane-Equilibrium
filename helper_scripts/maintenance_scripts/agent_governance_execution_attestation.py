"""Out-of-band execution-authenticity seam for governance closure.

Canonical/self digests prove integrity only.  A closure validator therefore
accepts runtime, business-outcome, deploy, and controller-call execution as
authentic only when its trusted host supplies a verifier capability that is not
serialized in the caller-controlled closure packet.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


ExecutionAttestationVerifier = Callable[[str, str, dict[str, Any]], bool]
ATTESTED_OBSERVATION_KINDS = {
    "runtime_observation_receipt_v1",
    "business_outcome_receipt_v1",
}


def _verified(
    verifier: ExecutionAttestationVerifier | None,
    kind: str,
    digest: str,
    artifact: dict[str, Any],
) -> bool:
    if verifier is None:
        return False
    try:
        return verifier(kind, digest, artifact) is True
    except Exception:
        return False


def validate_execution_attestations(
    *,
    gate_verdict: str,
    captures: dict[str, Any],
    observation_artifacts: dict[str, dict[str, Any]],
    effect_receipts: dict[str, dict[str, Any]],
    verifier: ExecutionAttestationVerifier | None,
) -> list[str]:
    """Reject PASS when packet-local self-digests are the only execution proof.

    The verifier is a host capability, not data read from the packet.  Offline
    CLI validation deliberately has no such capability and therefore cannot
    authenticate delegated/runtime execution as PASS.
    """

    if gate_verdict != "PASS":
        return []
    candidates: list[tuple[str, str, dict[str, Any]]] = []
    for wave in captures.get("waves", {}).values():
        if isinstance(wave, dict):
            candidates.append(
                ("workflow_wave_record_v1", str(wave.get("record_digest", "")), wave)
            )
    for receipt in effect_receipts.values():
        candidates.append(
            ("effect_adapter_result_v1", str(receipt.get("receipt_digest", "")), receipt)
        )
    for artifact in observation_artifacts.values():
        kind = str(artifact.get("schema_version", ""))
        if kind in ATTESTED_OBSERVATION_KINDS:
            candidates.append((kind, str(artifact.get("receipt_digest", "")), artifact))
    for artifact in captures.get("telemetry", {}).values():
        if isinstance(artifact, dict) and artifact.get("trust_tier") == (
            "PLATFORM_OR_EXTERNAL_ATTESTED"
        ):
            candidates.append(
                ("telemetry_record_v1", str(artifact.get("record_digest", "")), artifact)
            )

    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for kind, digest, artifact in candidates:
        identity = (kind, digest)
        if identity in seen:
            continue
        seen.add(identity)
        if not _verified(verifier, kind, digest, artifact):
            errors.append(
                "closure PASS lacks out-of-band execution attestation for "
                f"{kind} {digest or '<missing>'}"
            )
    return errors
