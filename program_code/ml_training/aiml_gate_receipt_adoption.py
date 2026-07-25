"""S0.3 program-adoption 受理路徑下層(facade 2000 行治理拆分;WP4 S2.4)。

這是 ``aiml_gate_receipt_validator``(facade)的**下層**:terminal sink 契約宣告、GitHub
repository-policy attestation 身分/語意驗、S0 predecessor lineage 檢查,與唯一能簽發
``PROGRAM_ADOPTED`` 的 ``validate_program_adoption_receipt``。全部為逐位元組等值搬移;
消費者「只」匯入 facade。

**循環相依處理與 monkeypatch 縫。** 本模組 top-level 只匯入 sibling 下層,絕不匯入 facade;
``validate_program_adoption_receipt`` 需要中央 dispatcher ``validate_aiml_artifact``(留在
facade),故於函式內**延遲匯入** facade 呼叫——經 facade 模組物件呼叫保持測試對 facade 屬性
monkeypatch 的縫逐字有效,並避免 import 期循環。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aiml_gate_receipt_schema_core import (
    ExternalAttestationVerifier,
    PROGRAM_DOCUMENT_PATHS,
    PROGRAM_GOVERNANCE_PATHS,
    PROGRAM_REVIEW_NODES,
    PROGRAM_SCHEMA_PATHS,
    S0_DEPENDENCY_DIGESTS,
    S0_PREDECESSOR_CONTRACTS,
    SourceManifestVerifier,
    _contains_github_secret_like_content,
    _parse_timestamp,
    artifact_self_digest,
    canonical_digest,
    resolve_facade,
)
from aiml_gate_receipt_classifiers import AIML_EFFECT_CLASSIFIER_RULES


def _terminal_receipt_sink_body() -> dict[str, Any]:
    return {
        "schema_version": "terminal_receipt_sink_v1",
        "sink_id": "terminal_receipt_sink_v1",
        "status": "CONTRACT_ONLY",
        "authority": "terminal_candidate_validators_only",
        "destination_class": "EXTERNAL_IMMUTABLE_WORM",
        "allowed_terminal_receipt_types": [
            "aiml_module_landed_for_trading_receipt_v1",
            "aiml_platform_no_candidate_receipt_v1",
        ],
        "append_intent_schema_version": "terminal_receipt_append_intent_v1",
        "append_result_schema_version": "terminal_receipt_append_result_v1",
        "readback_ack_schema_version": "terminal_receipt_readback_ack_v1",
        "actor_contract": {
            "append_actor_class": "DEDICATED_APPEND_ACTOR",
            "readback_verifier_class": "INDEPENDENT_READBACK_VERIFIER",
            "same_actor_allowed": False,
        },
        "idempotency_key_fields": [
            "landing_scope_id",
            "terminal_state",
            "terminal_payload_digest",
        ],
        "payload_binding_fields": [
            "final_source_head",
            "landing_scope_id",
            "learning_runtime_digest",
            "terminal_payload_digest",
            "terminal_state",
        ],
        "implementation_owner_session": "S1.2",
        "implementation_paths": [],
    }


def terminal_receipt_sink_contract() -> dict[str, Any]:
    """Return S0.3's non-executable sink contract; S1.2 owns implementation."""

    contract = _terminal_receipt_sink_body()
    contract["self_digest"] = artifact_self_digest(contract)
    return contract


def github_policy_attestation_identity_digest(attestation: dict[str, Any]) -> str:
    """Bind repository, exact heads, observed policy, provenance and validity window."""

    return canonical_digest({
        key: value
        for key, value in attestation.items()
        if key not in {"attestation_id", "self_digest"}
    })


def program_adoption_identity_digest(receipt: dict[str, Any]) -> str:
    """Return the pre-graph adoption identity used as the dependency-graph root.

    The graph digest is intentionally excluded: the graph binds this adoption
    identity as its root, while the completed receipt binds the graph digest.
    This gives both directions without a self-digest cycle.
    """

    return canonical_digest({
        key: value
        for key, value in receipt.items()
        if key not in {
            "adoption_id", "receipt_dependency_graph_digest", "self_digest"
        }
    })


def _github_policy_attestation_errors(
    attestation: dict[str, Any], *, now: str | datetime | None
) -> list[str]:
    errors: list[str] = []
    if _contains_github_secret_like_content(attestation):
        errors.append(
            "GitHub repository-policy attestation contains secret-like content"
        )
    try:
        if isinstance(now, str):
            evaluated_at = _parse_timestamp(now)
        elif isinstance(now, datetime):
            if now.tzinfo is None:
                raise ValueError("now must be timezone-aware")
            evaluated_at = now
        else:
            evaluated_at = datetime.now(timezone.utc)
        observed_at = _parse_timestamp(attestation["observed_at"])
        expires_at = _parse_timestamp(attestation["expires_at"])
        valid_from = _parse_timestamp(attestation["valid_from"])
        effect_at = _parse_timestamp(attestation["effect_at"])
        if observed_at > evaluated_at:
            errors.append("GitHub repository-policy attestation is future-dated")
        if not observed_at <= valid_from <= effect_at < expires_at:
            errors.append(
                "GitHub repository-policy effect time is outside its authority window"
            )
        if any(
            _parse_timestamp(capture["captured_at"]) > observed_at
            for capture in attestation["evidence_captures"]
        ):
            errors.append("GitHub evidence capture postdates the attested observation")
    except (TypeError, ValueError) as error:
        errors.append(f"GitHub repository-policy timestamp is invalid: {error}")
    if attestation["observer_node_id"] == attestation["validator_node_id"]:
        errors.append("GitHub policy observer and adoption validator must be independent")
    ruleset = attestation["ruleset"]
    expected_checks = sorted(
        ruleset["required_checks"],
        key=lambda check: (check["context"], check["integration_id"] or -1),
    )
    if ruleset["required_checks"] != expected_checks:
        errors.append("GitHub required checks must be in canonical sorted order")
    if ruleset["ref_includes"] != sorted(ruleset["ref_includes"]) or ruleset[
        "ref_excludes"
    ] != sorted(ruleset["ref_excludes"]):
        errors.append("GitHub ruleset ref conditions must be sorted")
    if "~DEFAULT_BRANCH" in ruleset["ref_excludes"]:
        errors.append("GitHub ruleset excludes the default branch")
    if attestation["attestation_id"] != github_policy_attestation_identity_digest(
        attestation
    ):
        errors.append("GitHub repository-policy attestation_id is invalid")
    if attestation["self_digest"] != artifact_self_digest(attestation):
        errors.append("GitHub repository-policy attestation self_digest is invalid")
    return errors


def _program_adoption_receipt_errors(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if receipt["adoption_id"] != program_adoption_identity_digest(receipt):
        errors.append("program adoption_id is invalid")
    if receipt["self_digest"] != artifact_self_digest(receipt):
        errors.append("program adoption receipt self_digest is invalid")
    dependencies = {
        item["session_id"]: item["receipt_digest"]
        for item in receipt["dependency_receipts"]
    }
    if dependencies != S0_DEPENDENCY_DIGESTS:
        errors.append("program adoption dependencies are not the exact S0.1/S0.2 lineage")
    for field, expected_paths in (
        ("document_manifest", PROGRAM_DOCUMENT_PATHS),
        ("schema_manifest", PROGRAM_SCHEMA_PATHS),
        ("governance_manifest", PROGRAM_GOVERNANCE_PATHS),
    ):
        paths = [item["path"] for item in receipt[field]]
        if paths != list(expected_paths):
            errors.append(f"program adoption {field} paths differ from exact contract")
    review_nodes = {
        item["role"]: item["node_id"] for item in receipt["review_bindings"]
    }
    if (
        len(review_nodes) != len(receipt["review_bindings"])
        or review_nodes != PROGRAM_REVIEW_NODES
    ):
        errors.append("program adoption review bindings are incomplete or substituted")
    # 每個 reviewer 綁定一個唯一的 role_fragment id;採納收尾不得讓兩個 reviewer 共用
    # 同一 fragment 佯裝獨立審查。
    fragment_ids = [item["fragment_id"] for item in receipt["review_bindings"]]
    if len(set(fragment_ids)) != len(fragment_ids):
        errors.append("program adoption review binding fragment ids are not unique")
    # review_generation 綁定 merge_head 的完整 repo 位元代(source_head==merge_head),
    # 其 digest 為正規雜湊,採納 fragment 的 final_generation 必須逐一等於它。
    review_generation = receipt["review_generation"]
    if receipt["review_generation_digest"] != canonical_digest(review_generation):
        errors.append("program adoption review generation digest is invalid")
    if review_generation["source_head"] != receipt["merge_head"]:
        errors.append("program adoption review generation is not bound to merge_head")
    if receipt["terminal_sink_contract_digest"] != terminal_receipt_sink_contract()[
        "self_digest"
    ]:
        errors.append("program adoption terminal sink contract binding is invalid")
    governance_digests = {
        item["path"]: item["digest"] for item in receipt["governance_manifest"]
    }
    if receipt["validator_binding"]["implementation_digest"] != governance_digests.get(
        "program_code/ml_training/aiml_gate_receipt_validator.py"
    ):
        errors.append("program adoption non-call validator implementation binding is invalid")
    return errors


def _s0_predecessor_receipt_errors(
    artifact_name: str,
    receipt: Any,
) -> list[str]:
    expected = S0_PREDECESSOR_CONTRACTS[artifact_name]
    if not isinstance(receipt, dict):
        return [f"{artifact_name} must be a complete receipt object"]
    errors: list[str] = []
    for field in ("session_id", "receipt_type", "program_id"):
        if receipt.get(field) != expected[field]:
            errors.append(f"{artifact_name} {field} differs from exact S0 lineage")
    claimed_digest = receipt.get("self_digest")
    if claimed_digest != artifact_self_digest(receipt):
        errors.append(
            f"{artifact_name} self_digest does not bind the complete canonical receipt"
        )
    if claimed_digest != expected["self_digest"]:
        errors.append(f"{artifact_name} digest differs from hardcoded S0 lineage")
    return errors


def validate_program_adoption_receipt(
    receipt: Any,
    *,
    artifacts: dict[str, Any],
    now: str | datetime | None = None,
    external_verifier: ExternalAttestationVerifier | None = None,
    source_manifest_verifier: SourceManifestVerifier | None = None,
) -> list[str]:
    """Validate the only S0.3 path that can issue ``PROGRAM_ADOPTED``.

    This is the canonical cross-artifact semantic validator used by governance
    closure.  Registry, routing and closure may select/call it but must not
    duplicate these AIML adoption rules.

    ``source_manifest_verifier`` is mandatory and fail-closed: a missing verifier
    or any non-``True`` return (including a raised exception) rejects the
    receipt.  Returning ``True`` is a strengthened obligation — the host must have
    confirmed that ``reviewed_head`` and ``merge_head`` both exist, that
    ``git merge-base --is-ancestor reviewed_head merge_head`` holds (reflexive:
    ``reviewed_head == merge_head`` is accepted as a fast-forward), and that every
    manifest ``path`` resolves at ``merge_head`` to the exact declared blob
    ``sha256``.  The reviewed/merge cross-binds below feed the exact heads handed
    to that obligation; the offline CLI has no such host capability.
    """

    # 經 resolve_facade() 呼叫「既載入」的 facade dispatcher validate_aiml_artifact:
    # 保持測試 monkeypatch 縫(頂層/ package 兩種 import 形皆命中同一模組物件,E2 P1-1)
    # 並避免 import 期循環(2000 行治理拆分)。
    _central = resolve_facade()

    errors = [
        f"program adoption receipt invalid: {error}"
        for error in _central.validate_aiml_artifact(receipt, now=now)
    ]
    github_candidate = artifacts.get("github_attestation")
    if external_verifier is None:
        errors.append(
            "program adoption requires caller-supplied external GitHub verification"
        )
    elif not isinstance(github_candidate, dict):
        errors.append("program adoption external GitHub artifact is absent")
    else:
        try:
            externally_verified = external_verifier(github_candidate)
        except Exception:  # pragma: no cover - boundary failure is fail-closed
            externally_verified = False
        if externally_verified is not True:
            errors.append("program adoption external GitHub verification failed")
    if source_manifest_verifier is None:
        errors.append(
            "program adoption requires caller-supplied source manifest verification"
        )
    else:
        try:
            manifest_items = [
                item
                for field in (
                    "document_manifest",
                    "schema_manifest",
                    "governance_manifest",
                )
                for item in receipt[field]
            ]
            source_manifest = {
                item["path"]: item["digest"] for item in manifest_items
            }
            if len(source_manifest) != len(manifest_items):
                raise ValueError("source manifest paths are not unique")
            # reviewed_head/merge_head 是下方(reviewed_head==source-build
            # checkpoint、merge_head==finalization baseline)交叉綁定過的確切 head,
            # 於此餵給主機祖裔義務:主機須確認 merge_head 為 reviewed_head 的後代
            # (自反相等亦可),且各 path 於 merge_head 的 blob 與清單 digest 相符。
            source_verified = source_manifest_verifier(
                receipt["reviewed_head"],
                receipt["merge_head"],
                source_manifest,
            )
        except Exception:  # pragma: no cover - boundary failure is fail-closed
            source_verified = False
        if source_verified is not True:
            errors.append("program adoption source manifest verification failed")
    required_artifacts = {
        "s0_1_receipt",
        "s0_2_receipt",
        "source_attempt",
        "finalization_attempt",
        "effect_classification",
        "dependency_graph",
        "github_attestation",
        "terminal_sink_contract",
    }
    if set(artifacts) != required_artifacts:
        errors.append(
            "program adoption artifact inventory mismatch: "
            f"missing={sorted(required_artifacts - set(artifacts))} "
            f"extra={sorted(set(artifacts) - required_artifacts)}"
        )
        return errors
    for name, artifact in artifacts.items():
        if name in S0_PREDECESSOR_CONTRACTS:
            errors.extend(
                f"program adoption {error}"
                for error in _s0_predecessor_receipt_errors(name, artifact)
            )
            continue
        errors.extend(
            f"program adoption {name} invalid: {error}"
            for error in _central.validate_aiml_artifact(artifact, now=now)
        )
    if errors or not isinstance(receipt, dict):
        return errors

    source_attempt = artifacts["source_attempt"]
    final_attempt = artifacts["finalization_attempt"]
    classification = artifacts["effect_classification"]
    graph = artifacts["dependency_graph"]
    github = artifacts["github_attestation"]
    terminal_sink = artifacts["terminal_sink_contract"]

    program_scope_ref = {"kind": "PROGRAM", "landing_scope_id": None}
    if receipt["scope_ref"] != program_scope_ref or any(
        artifact["scope_ref"] != program_scope_ref
        for artifact in (source_attempt, final_attempt, graph)
    ):
        errors.append("program adoption requires the PROGRAM null scope_ref throughout")
    if not (
        source_attempt["session_id"] == "S0.3"
        and source_attempt["attempt"] == 1
        and source_attempt["attempt_phase"] == "SOURCE_BUILD"
        and source_attempt["status"] == "MERGED"
    ):
        errors.append("program adoption requires merged S0.3 source-build attempt 1")
    if not (
        final_attempt["session_id"] == "S0.3"
        and final_attempt["attempt"] >= 2
        and final_attempt["attempt_phase"] == "POST_MERGE_FINALIZATION"
        and final_attempt["status"] == "FINALIZED"
    ):
        errors.append("program adoption requires a finalized post-merge S0.3 attempt")
    if receipt["source_build_attempt_id"] != source_attempt["attempt_id"]:
        errors.append("program adoption source-build attempt binding is invalid")
    if receipt["finalization_attempt_id"] != final_attempt["attempt_id"]:
        errors.append("program adoption finalization attempt binding is invalid")
    if receipt["attempt"] != final_attempt["attempt"]:
        errors.append("program adoption finalization attempt number binding is invalid")
    # reviewed_head/merge_head 交叉綁定:分別必須等於 source-build checkpoint 與
    # finalization baseline。這兩個確切 head 是上方 source_manifest_verifier 祖裔
    # 義務(merge_head 為 reviewed_head 後代 + blob 相符)的輸入。
    if receipt["reviewed_head"] != source_attempt["source"]["checkpoint_head"]:
        errors.append("program adoption reviewed_head differs from source-build checkpoint")
    if receipt["merge_head"] != final_attempt["source"]["baseline_head"]:
        errors.append("program adoption merge_head differs from finalization baseline")
    if github["reviewed_head"] != receipt["reviewed_head"] or github[
        "merge_head"
    ] != receipt["merge_head"]:
        errors.append("GitHub policy attestation is not bound to reviewed/merge heads")
    if receipt["github_policy_attestation_digest"] != github["self_digest"]:
        errors.append("program adoption GitHub policy attestation binding is invalid")
    if receipt["required_effect_classification_digest"] != classification[
        "self_digest"
    ]:
        errors.append("program adoption required-effect classification binding is invalid")
    if final_attempt["effect_classification_digest"] != classification["self_digest"]:
        errors.append("finalization attempt does not bind required-effect classification")
    if classification["session_attempt_id"] != final_attempt["attempt_id"] or (
        classification["required_effects"] != [{
            **AIML_EFFECT_CLASSIFIER_RULES["S0.3"],
            "status": "REQUIRED_PENDING",
        }]
    ):
        errors.append("program adoption requires exact post-merge external attestation classification")
    if receipt["receipt_dependency_graph_digest"] != graph["self_digest"]:
        errors.append("program adoption dependency-graph binding is invalid")
    if receipt["terminal_sink_contract_digest"] != terminal_sink["self_digest"]:
        errors.append("program adoption terminal sink contract artifact binding is invalid")
    graph_receipts = {
        item["receipt_id"]: item["receipt_digest"]
        for item in graph["receipts"]
    }
    if graph["root_receipt_id"] != "S0.3" or graph_receipts.get("S0.3") != (
        receipt["adoption_id"]
    ):
        errors.append("program adoption dependency graph root is invalid")
    if {
        key: graph_receipts.get(key) for key in S0_DEPENDENCY_DIGESTS
    } != S0_DEPENDENCY_DIGESTS:
        errors.append("program adoption dependency graph lacks exact S0 lineage")
    if graph_receipts.get("github-policy") != github["self_digest"]:
        errors.append("program adoption dependency graph substitutes GitHub authority")
    try:
        issued_at = _parse_timestamp(receipt["issued_at"])
        if isinstance(now, str):
            evaluated_at = _parse_timestamp(now)
        elif isinstance(now, datetime):
            evaluated_at = now
        else:
            evaluated_at = datetime.now(timezone.utc)
        if issued_at > evaluated_at:
            errors.append("program adoption receipt is future-dated")
        if _parse_timestamp(github["effect_at"]) != issued_at:
            errors.append("program adoption issuance differs from GitHub authority effect time")
    except (TypeError, ValueError) as error:
        errors.append(f"program adoption timestamp is invalid: {error}")
    return errors
