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


def _effect_receipt_candidate(
    receipt: dict[str, Any],
) -> tuple[str, str, dict[str, Any], tuple[str, ...]]:
    """把一份 effect receipt 正規化成 (kind, digest, artifact, dedup identity)。

    E3-M-1:``receipt_digest`` 是通用 deploy 家族的權威摘要欄位,但九個 S2 receipt schema
    一律以 ``self_digest`` 為權威摘要且**沒有** ``receipt_digest`` 欄位 —— 舊碼因此把每份
    S2 收據都退化成 ``("effect_adapter_result_v1", "")``,再被 ``(kind, digest)`` 去重塌成
    同一身分:一份 S2 收據通過(或全部一起被跳過)就等於全部通過。此處先取
    ``receipt_digest`` 再退回 ``self_digest``,並把 adapter/schema/probe scope 併入 dedup
    identity,讓同摘要空字串的不同收據不再互相冒充。
    """

    digest = str(receipt.get("receipt_digest") or receipt.get("self_digest") or "")
    kind = "effect_adapter_result_v1"
    source = str(receipt.get("adapter_id") or receipt.get("schema_version") or "")
    scope = str(receipt.get("probe_scope") or "")
    return kind, digest, receipt, (kind, digest, source, scope)


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
    # 每個候選帶一個明確的 dedup identity;effect receipt 的 identity 另含 adapter/step,
    # 見 _effect_receipt_candidate。
    candidates: list[tuple[str, str, dict[str, Any], tuple[str, ...]]] = []
    for wave in captures.get("waves", {}).values():
        if isinstance(wave, dict):
            kind, digest = "workflow_wave_record_v1", str(wave.get("record_digest", ""))
            candidates.append((kind, digest, wave, (kind, digest)))
    for receipt in effect_receipts.values():
        candidates.append(_effect_receipt_candidate(receipt))
    for artifact in observation_artifacts.values():
        kind = str(artifact.get("schema_version", ""))
        if kind in ATTESTED_OBSERVATION_KINDS:
            digest = str(artifact.get("receipt_digest", ""))
            candidates.append((kind, digest, artifact, (kind, digest)))
    for artifact in captures.get("telemetry", {}).values():
        if isinstance(artifact, dict) and artifact.get("trust_tier") == (
            "PLATFORM_OR_EXTERNAL_ATTESTED"
        ):
            kind = "telemetry_record_v1"
            digest = str(artifact.get("record_digest", ""))
            candidates.append((kind, digest, artifact, (kind, digest)))

    errors: list[str] = []
    seen: set[tuple[str, ...]] = set()
    for kind, digest, artifact, identity in candidates:
        if identity in seen:
            continue
        seen.add(identity)
        if not _verified(verifier, kind, digest, artifact):
            errors.append(
                "closure PASS lacks out-of-band execution attestation for "
                f"{kind} {digest or '<missing>'}"
            )
    return errors
