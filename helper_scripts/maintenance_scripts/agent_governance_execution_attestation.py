"""Out-of-band execution-authenticity seam for governance closure.

Canonical/self digests prove integrity only.  A closure validator therefore
accepts runtime, business-outcome, deploy, and controller-call execution as
authentic only when its trusted host supplies a verifier capability that is not
serialized in the caller-controlled closure packet.

同一條理由適用於**獨立 ops_postcheck artifact**(Codex-2/E2-RES-3):它自報 ``PASS`` 且
self_digest 由 caller 自己重算,因此其確切 bytes 一樣是本模組的候選,必須被 host verifier
認證,否則 closure 不得 PASS。
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


def _independent_postcheck_candidate(
    artifact: dict[str, Any],
) -> tuple[str, str, dict[str, Any], tuple[str, ...]]:
    """把一份獨立 ops_postcheck artifact 正規化成 (kind, digest, artifact, dedup identity)。

    Codex-2 / E2-RES-3:closure 對這類 artifact 原本只有「caller 可控的 canonical self-digest
    重算 + 自報 PASS」,而 OPS fragment 只綁它的 evidence ID —— 拿到真 effect receipt 後,封包
    產生者可以用同一個 evidence ID 換上一份新鮮自封的 PASS postcheck,宣稱獨立運維驗證跑過
    (含 W6B 安裝與 PG migration 之後)。故其**確切 bytes** 必須與 effect receipt 一樣通過
    out-of-band host verifier。

    ``kind`` 取 artifact 自己的 ``schema_version``(不借用 effect receipt 的通用
    ``effect_adapter_result_v1``:它不是一份 adapter result,借用會讓兩類 artifact 在
    verifier 的 (kind, digest) 命名空間互相冒充)。dedup identity 另含 effect_step 與
    verifier_node,讓缺 ``self_digest`` 的兩份不同 postcheck 不會塌成同一身分。
    """

    kind = str(artifact.get("schema_version") or "")
    digest = str(artifact.get("self_digest") or "")
    step = str(artifact.get("effect_step") or "")
    verifier_node = str(artifact.get("verifier_node") or "")
    return kind, digest, artifact, (kind, digest, step, verifier_node)


def validate_execution_attestations(
    *,
    gate_verdict: str,
    captures: dict[str, Any],
    observation_artifacts: dict[str, dict[str, Any]],
    effect_receipts: dict[str, dict[str, Any]],
    independent_postcheck_artifacts: dict[str, dict[str, Any]],
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
    # 獨立 ops_postcheck 的 identity 另含 effect_step/verifier_node(且 kind 是它自己的
    # schema_version,絕不與 effect receipt 的通用 kind 塌成同一身分),見兩個 _candidate。
    candidates: list[tuple[str, str, dict[str, Any], tuple[str, ...]]] = []
    for wave in captures.get("waves", {}).values():
        if isinstance(wave, dict):
            kind, digest = "workflow_wave_record_v1", str(wave.get("record_digest", ""))
            candidates.append((kind, digest, wave, (kind, digest)))
    for receipt in effect_receipts.values():
        candidates.append(_effect_receipt_candidate(receipt))
    for artifact in independent_postcheck_artifacts.values():
        candidates.append(_independent_postcheck_candidate(artifact))
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
