#!/usr/bin/env python3
"""Generate/validate S2E launch payloads and atomically consume wave predecessors."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPO_ROOT / "program_code" / "ml_training"
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from aiml_gate_receipt_s2e_anchor_floor import (  # noqa: E402
    AnchorGateObservations,
)
from aiml_gate_receipt_s2e_launch import (  # noqa: E402,F401
    build_genesis_candidate,
    build_s2e_launch_predecessor_authority,
    build_wave_candidate,
    issue_s2e_launch_receipt,
    validate_receipt_carrier_attestation,
    validate_s2e_launch_genesis_receipt,
    validate_s2e_launch_transition,
    validate_s2e_launch_transition_payload,
    validate_s2e_launch_wave_receipt,
    verify_receipt_carrier_attestation,
)


_HOST_CLOCK_ACTIONS = frozenset({
    "generate-wave",
    "validate",
    "verify-carrier",
    "build-predecessor-authority",
    "transition-gate",
})


def _sample_utc_host_clock() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _add_durability_anchor(
    parser: argparse.ArgumentParser, *, prefix: str = ""
) -> None:
    option_prefix = f"{prefix}-" if prefix else ""
    destination_prefix = f"{prefix}_" if prefix else ""
    parser.add_argument(
        f"--{option_prefix}durability-anchor-attestation",
        dest=f"{destination_prefix}durability_anchor_attestation",
        type=Path,
        required=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    genesis = subparsers.add_parser("generate-genesis")
    genesis.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    genesis.add_argument("--baseline-head", required=True)
    genesis.add_argument("--schema-carrier-head", required=True)
    genesis.add_argument("--launch-contract-digest", required=True)
    genesis.add_argument("--generation-task-contract-digest", required=True)
    wave = subparsers.add_parser("generate-wave")
    wave.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    wave.add_argument("--wave", required=True)
    wave.add_argument("--source-head", required=True)
    wave.add_argument("--schema-carrier-head", required=True)
    wave.add_argument("--predecessor-receipt", type=Path, required=True)
    wave.add_argument("--predecessor-authority", type=Path, required=True)
    wave.add_argument("--launch-contract-digest", required=True)
    wave.add_argument("--generation-task-contract-digest", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    validate.add_argument("--receipt", type=Path, required=True)
    validate.add_argument("--predecessor-receipt", type=Path)
    validate.add_argument("--predecessor-authority", type=Path)
    validate.add_argument("--payload-receipt", type=Path)
    # optional:缺省時本分支只做 payload topology,維持現行
    # STRUCTURAL_PASS_NOT_ADVANCE 語義,不會靜默取得 Advance。
    validate.add_argument("--durability-anchor-attestation", type=Path)
    issue = subparsers.add_parser("issue")
    issue.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    issue.add_argument("--candidate", type=Path, required=True)
    issue.add_argument("--acceptance-review-bundle", type=Path, required=True)
    issue.add_argument("--governed-capture-record", type=Path, required=True)
    issue.add_argument(
        "--disposable-test-effect-chains", type=Path, required=True
    )
    issue.add_argument("--predecessor-receipt", type=Path)
    issue.add_argument("--predecessor-authority", type=Path)
    issue.add_argument(
        "--predecessor-consumption-bootstrap-authority", type=Path
    )
    _add_durability_anchor(issue)
    carrier = subparsers.add_parser("verify-carrier")
    carrier.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    carrier.add_argument("--attestation", type=Path, required=True)
    carrier.add_argument("--payload-receipt", type=Path, required=True)
    carrier.add_argument("--governed-capture-record", type=Path, required=True)
    _add_durability_anchor(carrier)
    authority = subparsers.add_parser("build-predecessor-authority")
    authority.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    authority.add_argument("--predecessor-receipt", type=Path, required=True)
    authority.add_argument(
        "--launch-chain-before-predecessor", type=Path, required=True
    )
    authority.add_argument(
        "--acceptance-review-bundle", type=Path, required=True
    )
    authority.add_argument(
        "--review-governed-capture-record", type=Path, required=True
    )
    authority.add_argument(
        "--review-disposable-test-effect-chains", type=Path, required=True
    )
    authority.add_argument("--carrier-attestation", type=Path, required=True)
    authority.add_argument(
        "--carrier-governed-capture-record", type=Path, required=True
    )
    _add_durability_anchor(authority, prefix="review")
    _add_durability_anchor(authority, prefix="carrier")
    transition = subparsers.add_parser("transition-gate")
    transition.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    transition.add_argument("--receipt", type=Path, required=True)
    transition.add_argument(
        "--predecessor-receipt", type=Path, required=True
    )
    transition.add_argument(
        "--predecessor-authority", type=Path, required=True
    )
    _add_durability_anchor(transition)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    authority_now = (
        _sample_utc_host_clock() if args.action in _HOST_CLOCK_ACTIONS else None
    )
    if args.action == "generate-genesis":
        artifact = build_genesis_candidate(
            repo_root=args.repo_root,
            baseline_head=args.baseline_head,
            schema_carrier_head=args.schema_carrier_head,
            launch_contract_digest=args.launch_contract_digest,
            generation_task_contract_digest=args.generation_task_contract_digest,
        )
        print(json.dumps(artifact, ensure_ascii=False, sort_keys=True))
        return 0
    if args.action == "generate-wave":
        artifact = build_wave_candidate(
            repo_root=args.repo_root,
            wave=args.wave,
            source_head=args.source_head,
            schema_carrier_head=args.schema_carrier_head,
            predecessor_receipt=_read(args.predecessor_receipt),
            predecessor_authority=_read(args.predecessor_authority),
            launch_contract_digest=args.launch_contract_digest,
            generation_task_contract_digest=args.generation_task_contract_digest,
            now=authority_now,
        )
        print(json.dumps(artifact, ensure_ascii=False, sort_keys=True))
        return 0
    if args.action == "issue":
        result = issue_s2e_launch_receipt(
            _read(args.candidate),
            acceptance_review_bundle=_read(args.acceptance_review_bundle),
            repo_root=args.repo_root,
            governed_capture_record=_read(args.governed_capture_record),
            disposable_test_effect_chains=_read(
                args.disposable_test_effect_chains
            ),
            durability_anchor_attestation=_read(
                args.durability_anchor_attestation
            ),
            predecessor_receipt=(
                _read(args.predecessor_receipt)
                if args.predecessor_receipt is not None
                else None
            ),
            predecessor_authority=(
                _read(args.predecessor_authority)
                if args.predecessor_authority is not None
                else None
            ),
            predecessor_consumption_bootstrap_authority=(
                _read(args.predecessor_consumption_bootstrap_authority)
                if args.predecessor_consumption_bootstrap_authority
                is not None
                else None
            ),
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("status") == "ISSUED" else 2
    if args.action == "verify-carrier":
        result = verify_receipt_carrier_attestation(
            _read(args.attestation),
            payload_receipt=_read(args.payload_receipt),
            repo_root=args.repo_root,
            now=authority_now,
            governed_capture_record=_read(args.governed_capture_record),
            durability_anchor_attestation=_read(
                args.durability_anchor_attestation
            ),
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("status") == "VERIFIED" else 2
    if args.action == "build-predecessor-authority":
        artifact = build_s2e_launch_predecessor_authority(
            predecessor_receipt=_read(args.predecessor_receipt),
            launch_chain_before_predecessor=_read(
                args.launch_chain_before_predecessor
            ),
            acceptance_review_bundle=_read(args.acceptance_review_bundle),
            review_governed_capture_record=_read(
                args.review_governed_capture_record
            ),
            review_disposable_test_effect_chains=_read(
                args.review_disposable_test_effect_chains
            ),
            review_durability_anchor_attestation=_read(
                args.review_durability_anchor_attestation
            ),
            carrier_attestation=_read(args.carrier_attestation),
            carrier_governed_capture_record=_read(
                args.carrier_governed_capture_record
            ),
            carrier_durability_anchor_attestation=_read(
                args.carrier_durability_anchor_attestation
            ),
            repo_root=args.repo_root,
            now=authority_now,
        )
        print(json.dumps(artifact, ensure_ascii=False, sort_keys=True))
        return 0
    if args.action == "transition-gate":
        artifact = _read(args.receipt)
        predecessor = _read(args.predecessor_receipt)
        authority = _read(args.predecessor_authority)
        chain = authority.get("launch_chain_before_predecessor", [])
        consumed = {
            str(item.get("payload_digest"))
            for item in chain
            if isinstance(item, dict)
        } if isinstance(chain, list) else set()
        # E3-B:`verdict` 出模組後曾被壓平成無型別 errors,下游只能靠
        # `"UNVERIFIED: "` 子字串去分辨「偽造的 floor 被拒」與「未 merge 因而誠實
        # 不可驗」。UNVERIFIED 仍然擋(status 照樣 FAIL),但 verdict 現在是 typed
        # 輸出的一格。同一個載體也帶出 host identity 觀察(E3-E 的另一半)。
        observations = AnchorGateObservations()
        errors = validate_s2e_launch_transition(
            artifact,
            predecessor_receipt=predecessor,
            predecessor_authority=authority,
            repo_root=args.repo_root,
            now=authority_now,
            consumed_predecessor_digests=frozenset(consumed),
            durability_anchor_attestation=_read(
                args.durability_anchor_attestation
            ),
            observations=observations,
        )
        status = "ADVANCE" if not errors else "FAIL"
        print(json.dumps({
            "status": status,
            "anchor_gate_observations": observations.as_records(),
            "errors": errors,
        }))
        return 0 if not errors else 2
    artifact = _read(args.receipt)
    status = "FAIL"
    observations = AnchorGateObservations()
    if artifact.get("schema_version") == "s2e_launch_genesis_receipt_v1":
        errors = validate_s2e_launch_genesis_receipt(
            artifact, repo_root=args.repo_root
        )
    elif artifact.get("schema_version") == "receipt_carrier_attestation_v1":
        if args.payload_receipt is None:
            errors = ["carrier attestation validation requires --payload-receipt"]
        else:
            errors = validate_receipt_carrier_attestation(
                artifact,
                payload_receipt=_read(args.payload_receipt),
                repo_root=args.repo_root,
                now=authority_now,
            )
    elif args.predecessor_receipt is None:
        errors = validate_s2e_launch_wave_receipt(artifact, repo_root=args.repo_root)
        status = "STRUCTURAL_PASS_NOT_ADVANCE" if not errors else "FAIL"
    else:
        predecessor = _read(args.predecessor_receipt)
        if args.predecessor_authority is None:
            errors = validate_s2e_launch_transition_payload(
                artifact,
                predecessor_receipt=predecessor,
                repo_root=args.repo_root,
                consumed_predecessor_digests=frozenset(),
            )
            status = "STRUCTURAL_PASS_NOT_ADVANCE" if not errors else "FAIL"
        elif args.durability_anchor_attestation is None:
            # authority 有、candidate anchor 沒有 ⇒ 不足以 Advance,只回 payload 語義。
            errors = validate_s2e_launch_transition_payload(
                artifact,
                predecessor_receipt=predecessor,
                repo_root=args.repo_root,
                consumed_predecessor_digests=frozenset(),
            )
            status = "STRUCTURAL_PASS_NOT_ADVANCE" if not errors else "FAIL"
        else:
            authority = _read(args.predecessor_authority)
            chain = authority.get("launch_chain_before_predecessor", [])
            consumed = {
                str(item.get("payload_digest"))
                for item in chain
                if isinstance(item, dict)
            } if isinstance(chain, list) else set()
            errors = validate_s2e_launch_transition(
                artifact,
                predecessor_receipt=predecessor,
                predecessor_authority=authority,
                repo_root=args.repo_root,
                now=authority_now,
                consumed_predecessor_digests=frozenset(consumed),
                durability_anchor_attestation=_read(
                    args.durability_anchor_attestation
                ),
                observations=observations,
            )
            status = "ADVANCE" if not errors else "FAIL"
    if artifact.get("schema_version") != "s2e_launch_wave_receipt_v1":
        status = "PASS" if not errors else "FAIL"
    print(json.dumps({
        "status": status,
        "anchor_gate_observations": observations.as_records(),
        "errors": errors,
    }))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
