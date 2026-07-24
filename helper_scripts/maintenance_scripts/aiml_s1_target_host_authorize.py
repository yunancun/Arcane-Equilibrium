#!/usr/bin/env python3
"""Sign one exact S1 target-host typed intent through the loaded SSH agent."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ML_ROOT = HERE.parents[1] / "program_code/ml_training"
for candidate in (HERE, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_aiml_trusted_host as trusted
import agent_governance_target_host_apply as target_apply
import agent_governance_target_host_operator_authorization as operator_auth


def _sign_with_loaded_agent(authorization: dict) -> bytes:
    public_key = operator_auth.OPERATOR_PUBLIC_KEY
    listed = subprocess.run(
        ["/usr/bin/ssh-add", "-L"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
    )
    if listed.returncode != 0 or public_key.encode("ascii") not in listed.stdout:
        raise ValueError(
            "the authorized S1 operator key is not loaded in the current SSH agent"
        )
    with tempfile.TemporaryDirectory(prefix="aiml-s1-apply-sign-") as directory:
        root = Path(directory)
        public_path = root / "operator.pub"
        message_path = root / "operator-authorization.json"
        public_path.write_text(public_key + "\n", encoding="ascii")
        message_path.write_bytes(operator_auth.canonical_bytes(authorization))
        signed = subprocess.run(
            [
                trusted.SSH_KEYGEN_EXECUTABLE,
                "-Y",
                "sign",
                "-f",
                str(public_path),
                "-n",
                operator_auth.OPERATOR_SIGNATURE_NAMESPACE,
                str(message_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if signed.returncode != 0:
            raise ValueError(
                "SSH-agent target-host intent signing failed: "
                + signed.stderr.decode("utf-8", errors="replace")[:300]
            )
        return message_path.with_suffix(".json.sig").read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    intent = json.loads(args.intent.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).isoformat()
    intent_errors = target_apply.validate_probe_intent(intent, now=now)
    if intent_errors:
        raise SystemExit(
            "target-host intent is not currently admissible: "
            + "; ".join(intent_errors[:6])
        )
    authorization = operator_auth.build_operator_authorization(
        intent=intent,
        source_head=args.source_head,
    )
    signature = _sign_with_loaded_agent(authorization)
    verification_errors = operator_auth.validate_operator_authorization(
        authorization,
        signature,
        intent=intent,
        source_head=args.source_head,
        now=now,
        actual_host=str(intent["expected_host"]),
    )
    if verification_errors:
        raise SystemExit(
            "new operator authorization failed self-verification: "
            + "; ".join(verification_errors[:6])
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    permit_path = args.out_dir / "operator_authorization.json"
    signature_path = args.out_dir / "operator_authorization.json.sig"
    temporary = permit_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            authorization,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, permit_path)
    signature_path.write_bytes(signature)
    print(json.dumps({
        "status": "OPERATOR_AUTHORIZATION_SIGNED",
        "authorization_digest": authorization["authorization_digest"],
        "intent_digest": intent["self_digest"],
        "source_head": args.source_head,
        "signer_fingerprint": authorization["signer_fingerprint"],
        "permit_path": str(permit_path),
        "signature_path": str(signature_path),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
