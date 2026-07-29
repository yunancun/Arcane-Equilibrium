#!/usr/bin/env python3
"""Generate or validate S2E launch payloads without repository/runtime effects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPO_ROOT / "program_code" / "ml_training"
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from aiml_gate_receipt_s2e_launch import (  # noqa: E402,F401
    build_genesis_candidate,
    build_wave_candidate,
    issue_s2e_launch_receipt,
    validate_receipt_carrier_attestation,
    validate_s2e_launch_genesis_receipt,
    validate_s2e_launch_transition,
    validate_s2e_launch_wave_receipt,
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
    wave.add_argument("--launch-contract-digest", required=True)
    wave.add_argument("--generation-task-contract-digest", required=True)
    wave.add_argument(
        "--side-effect-class",
        choices=("SOURCE_ONLY", "DISPOSABLE_TEST"),
        default="SOURCE_ONLY",
    )
    validate = subparsers.add_parser("validate")
    validate.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    validate.add_argument("--receipt", type=Path, required=True)
    validate.add_argument("--predecessor-receipt", type=Path)
    validate.add_argument("--payload-receipt", type=Path)
    validate.add_argument("--now")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
            launch_contract_digest=args.launch_contract_digest,
            generation_task_contract_digest=args.generation_task_contract_digest,
            side_effect_class=args.side_effect_class,
        )
        print(json.dumps(artifact, ensure_ascii=False, sort_keys=True))
        return 0
    artifact = _read(args.receipt)
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
                now=args.now,
            )
    elif args.predecessor_receipt is None:
        errors = validate_s2e_launch_wave_receipt(artifact, repo_root=args.repo_root)
    else:
        errors = validate_s2e_launch_transition(
            artifact,
            predecessor_receipt=_read(args.predecessor_receipt),
            repo_root=args.repo_root,
        )
    print(json.dumps({"status": "PASS" if not errors else "FAIL", "errors": errors}))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
