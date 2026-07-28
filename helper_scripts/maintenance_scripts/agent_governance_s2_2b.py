#!/usr/bin/env python3
"""S2.2B(WP5 tranche 2)builder + 最小 CLI——LR1 ingestion-compatibility seam 的離線入口。

verbs(全部離線、零 runtime 接觸;S2.5 design §10 / PROGRESS S2.2B row):

* ``build``    —— 由三個輸入檔(S2.2A source receipt / s2_5_final_attestation /
  observation JSON)組出 closed ``ingestion_compatibility_receipt_v1`` 並列印:
  逐項 result 與 learning_runtime_digest_match 由觀測值**導出**(caller 不可自證
  MATCH),status 由 lane 導出(source lane 頂點=``SOURCE_REVALIDATION_PASS``,
  任一維失敗=``COMPATIBILITY_REJECTED``;production 無 runtime attestor=
  ``EXTERNAL_VERIFICATION_PENDING``);
* ``validate`` —— 把 receipt 檔丟中央閘(``--now`` 必帶;過期 fail-closed);
* ``apply``    —— **恆 typed ``EXTERNAL_VERIFICATION_PENDING``(exit 0)、零變更**:
  S2.2B 的 runtime-`DONE` 消費 ``S2.5B@EFFECT_DONE``,該 effect 尚不存在,CLI 也沒有
  任何 driver/attestor 注入縫;結構壞件先以 typed REJECTED 終止(exit 2)。

⚠ 誠實邊界:本 CLI 只做離線結構/整合檢查,不能認證任何 runtime PASS;乾淨輸出「不」
代表 manifest 真的在一個 running runtime 上被重驗。effect class 恆 ``REMOTE_READONLY``,
九項 authority 恆 false。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_s2_2b as s2_2b_leaf  # noqa: E402
import aiml_gate_receipt_validator as central_validator  # noqa: E402

# repo 內已 persisted 的真 S2.2A receipt(fixtures/operator 直接消費真檔)。
S2_2A_RECEIPT_V1_REL = (
    "docs/execution_plan/ai_ml_landing/receipts/S2.2A-source-compatibility-receipt-v1.json"
)


def build_ingestion_compatibility_receipt(
    *,
    source_compatibility_receipt: dict[str, Any],
    s2_5_final_attestation: dict[str, Any] | None,
    observed_fingerprints: dict[str, Any],
    application_root_learning_runtime_digest: str | None,
    verifier_node_id: str,
    observed_at: str,
    evidence_expires_at: str,
    source_head: str,
    target_class: str = "simulated_harness",
    runtime_attestor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """組出 closed receipt;result/match/status 全部由輸入**導出**(caller 不可自證)。

    上游綁定 fail-fast:S2.2A receipt 的 self_digest 就地重算不符即 raise(替身 stub
    不進 builder);final attestation 同。lane 導出:

    * 任一 V151-V160 revalidation 非 MATCH 或 learning_runtime_digest 不再導出
      ⇒ ``COMPATIBILITY_REJECTED``(誠實失敗紀錄);
    * production + 全 MATCH + production FINAL_ATTESTED 錨 + runtime_attestor 在手
      ⇒ ``RUNTIME_COMPATIBILITY_ATTESTED``(PLATFORM;真簽章驗證屬中央閘/EFFECT);
    * production + 全 MATCH 但無 attestor ⇒ ``EXTERNAL_VERIFICATION_PENDING``
      (STRUCTURAL_ONLY 的誠實終點);
    * 其餘(simulated/disposable 全 MATCH)⇒ ``SOURCE_REVALIDATION_PASS``
      (LOCAL_REPRODUCIBLE 頂點)。
    """

    if not isinstance(source_compatibility_receipt, dict) or (
        central_validator.artifact_self_digest(source_compatibility_receipt)
        != source_compatibility_receipt.get("self_digest")
    ):
        raise ValueError(
            "the S2.2A source_compatibility receipt self_digest does not re-derive; "
            "a self-reported stub never enters the builder"
        )
    if s2_5_final_attestation is not None and (
        not isinstance(s2_5_final_attestation, dict)
        or central_validator.artifact_self_digest(s2_5_final_attestation)
        != s2_5_final_attestation.get("self_digest")
    ):
        raise ValueError(
            "the s2_5_final_attestation self_digest does not re-derive; a self-"
            "reported stub never enters the builder"
        )
    expected = source_compatibility_receipt["migration_fingerprints"]
    items = []
    failing: list[str] = []
    for file_name in sorted(expected):
        observed = observed_fingerprints.get(file_name)
        result = s2_2b_leaf._derived_item_result(expected[file_name], observed)
        if result != "MATCH":
            failing.append(file_name)
        items.append({
            "file": file_name,
            "expected_fingerprint": expected[file_name],
            "observed_fingerprint": observed,
            "result": result,
        })
    digest_match = (
        application_root_learning_runtime_digest is not None
        and application_root_learning_runtime_digest
        == source_compatibility_receipt["learning_runtime_digest"]
    )
    revalidation = {
        "items": items,
        "application_root_learning_runtime_digest": (
            application_root_learning_runtime_digest
        ),
        "learning_runtime_digest_match": digest_match,
        "verifier_node_id": verifier_node_id,
        "observed_at": observed_at,
        "evidence_expires_at": evidence_expires_at,
    }
    all_match = not failing and digest_match
    final_is_production_attested = (
        isinstance(s2_5_final_attestation, dict)
        and s2_5_final_attestation.get("status") == "FINAL_ATTESTED"
        and s2_5_final_attestation.get("target_class") == "production"
    )
    failure_reason: str | None = None
    bound_attestor: dict[str, Any] | None = None
    if not all_match:
        status = s2_2b_leaf.S2_2B_STATUS_REJECTED
        evidence_class = "STRUCTURAL_ONLY"
        failure_reason = (
            "ingestion compatibility revalidation failed on: "
            + ", ".join(sorted(failing) or ["learning_runtime_digest"])
        )
    elif target_class == "production":
        if final_is_production_attested and isinstance(runtime_attestor, dict):
            status = s2_2b_leaf.S2_2B_STATUS_RUNTIME_ATTESTED
            evidence_class = "PLATFORM_OR_EXTERNAL_ATTESTED"
            bound_attestor = dict(runtime_attestor)
        else:
            status = s2_2b_leaf.S2_2B_STATUS_PENDING
            evidence_class = "STRUCTURAL_ONLY"
            failure_reason = (
                "production ingestion compatibility is pending the runtime attestor "
                "and a production FINAL_ATTESTED anchor (S2.5B@EFFECT_DONE does not "
                "exist yet)"
            )
    else:
        status = s2_2b_leaf.S2_2B_STATUS_SOURCE_PASS
        evidence_class = "LOCAL_REPRODUCIBLE"
    receipt: dict[str, Any] = {
        "schema_version": s2_2b_leaf.S2_2B_SCHEMA_VERSION,
        "session_id": "S2.2B",
        "effect_class": s2_2b_leaf.S2_2B_EFFECT_CLASS,
        "status": status,
        "target_class": target_class,
        "evidence_class": evidence_class,
        "source_compatibility_receipt": json.loads(
            json.dumps(source_compatibility_receipt)
        ),
        "source_compatibility_receipt_digest": source_compatibility_receipt[
            "self_digest"
        ],
        "s2_5_final_attestation": (
            json.loads(json.dumps(s2_5_final_attestation))
            if s2_5_final_attestation is not None
            else None
        ),
        "s2_5_final_attestation_digest": (
            s2_5_final_attestation["self_digest"]
            if s2_5_final_attestation is not None
            else None
        ),
        "manifest_revalidation": revalidation,
        "runtime_attestor": bound_attestor,
        "boundary": {
            "remote_readonly_only": True,
            "pg_write_surface_absent": True,
            "fixture_impersonates_platform_attested": False,
            "nine_authorities_false": True,
        },
        "failure_reason": failure_reason,
        "source_head": source_head,
    }
    receipt["self_digest"] = central_validator.artifact_self_digest(receipt)
    return receipt


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    build_parser = sub.add_parser(
        "build", help="由 S2.2A receipt + final attestation + observation 組出 receipt"
    )
    build_parser.add_argument(
        "--source-receipt", type=Path, default=REPO_ROOT / S2_2A_RECEIPT_V1_REL,
        help="S2.2A source_compatibility receipt(預設消費 repo 內 persisted 真檔)",
    )
    build_parser.add_argument("--final-attestation", required=True, type=Path)
    build_parser.add_argument(
        "--observation", required=True, type=Path,
        help="觀測 JSON:{observed_fingerprints, application_root_learning_runtime_"
        "digest, verifier_node_id, observed_at, evidence_expires_at, source_head, "
        "target_class?}",
    )

    validate_parser = sub.add_parser(
        "validate", help="中央閘驗一份 receipt(--now 必帶;過期 fail-closed)"
    )
    validate_parser.add_argument("--artifact", required=True, type=Path)
    validate_parser.add_argument("--now", required=True)

    apply_parser = sub.add_parser(
        "apply",
        help="typed EXTERNAL_VERIFICATION_PENDING(S2.5B@EFFECT_DONE 前不可達),零變更",
    )
    apply_parser.add_argument("--artifact", required=True, type=Path)
    apply_parser.add_argument("--now", required=True)

    args = parser.parse_args(argv)
    if args.action == "build":
        observation = _load_json(args.observation)
        _print(build_ingestion_compatibility_receipt(
            source_compatibility_receipt=_load_json(args.source_receipt),
            s2_5_final_attestation=_load_json(args.final_attestation),
            observed_fingerprints=observation["observed_fingerprints"],
            application_root_learning_runtime_digest=observation[
                "application_root_learning_runtime_digest"
            ],
            verifier_node_id=observation["verifier_node_id"],
            observed_at=observation["observed_at"],
            evidence_expires_at=observation["evidence_expires_at"],
            source_head=observation["source_head"],
            target_class=observation.get("target_class", "simulated_harness"),
        ))
        return 0
    if args.action == "validate":
        errors = central_validator.validate_aiml_artifact(
            _load_json(args.artifact), now=args.now
        )
        _print({"status": "PASS" if not errors else "REJECTED", "errors": errors})
        return 0 if not errors else 2
    if args.action == "apply":
        errors = central_validator.validate_aiml_artifact(
            _load_json(args.artifact), now=args.now
        )
        if errors:
            _print({"status": "REJECTED", "errors": errors})
            return 2
        # 誠實終點:LR1 runtime DONE 消費 S2.5B@EFFECT_DONE(尚不存在);CLI 沒有任何
        # driver/attestor 注入縫,apply 面永遠 typed PENDING、零變更。
        _print({
            "status": s2_2b_leaf.S2_2B_STATUS_PENDING,
            "reasons": [
                "S2.2B runtime-DONE consumes S2.5B@EFFECT_DONE which does not exist; "
                "the apply surface is reachable but authority-locked "
                "(EXTERNAL_VERIFICATION_PENDING with zero mutation)"
            ],
        })
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
