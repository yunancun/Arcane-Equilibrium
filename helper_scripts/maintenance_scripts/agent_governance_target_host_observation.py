#!/usr/bin/env python3
"""Read-only, operator-authorized target-host preflight/postcheck observation.

This is the only Python script admitted by the governed command-capture policy
for S1 target-host observations.  It validates the operator SSHSIG over the
exact typed intent and committed source head before opening the process-local
probe gate.  It performs no apply primitive.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import agent_governance_target_host_apply as target_apply
import agent_governance_target_host_operator_authorization as operator_auth
import agent_governance_target_host_probe as target_host


OBSERVATION_SCHEMA_VERSION = "target_host_governed_observation_v1"
UNIT_RE = re.compile(r"^aiml-probeB-(?:absent|final)-[0-9]+\.scope$")


def _decode_json(value: str, label: str) -> dict[str, Any]:
    try:
        decoded = base64.b64decode(value, validate=True)
        artifact = json.loads(decoded.decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError) as error:
        raise ValueError(f"{label} is not canonical base64 JSON") from error
    if not isinstance(artifact, dict):
        raise ValueError(f"{label} must decode to one JSON object")
    return artifact


def _decode_signature(value: str) -> bytes:
    try:
        signature = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("operator signature is not canonical base64") from error
    if not signature:
        raise ValueError("operator signature is empty")
    return signature


def _committed_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().lower()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(
            f"cannot bind target-host observation to Git HEAD: {error}"
        ) from error


def observe(
    *,
    mode: str,
    intent: dict[str, Any],
    authorization: dict[str, Any],
    signature: bytes,
    unit: str | None = None,
    teardown_root: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Return one canonical read-only observation after exact-intent auth."""

    current = now or datetime.now(timezone.utc).isoformat()
    source_head = _committed_head()
    intent_errors = target_apply.validate_probe_intent(intent, now=current)
    authorization_errors = operator_auth.validate_operator_authorization(
        authorization,
        signature,
        intent=intent,
        source_head=source_head,
        now=current,
        actual_host=socket.gethostname(),
    )
    errors = [*intent_errors, *authorization_errors]
    if errors:
        raise ValueError(
            "operator-authorized target-host observation rejected: "
            + "; ".join(errors[:5])
        )
    runtime_dir = f"/run/user/{os.getuid()}"
    os.environ["XDG_RUNTIME_DIR"] = runtime_dir
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime_dir}/bus"
    os.environ["AIML_TARGET_HOST_PROBE"] = "1"
    if mode == "preflight":
        if unit is not None or teardown_root is not None:
            raise ValueError("preflight observation accepts no residue arguments")
        raw_observation = target_host.preflight_target_host(
            throwaway_root=str(intent["throwaway_root"]),
            expected_host=str(intent["expected_host"]),
        )
        # command_capture_v2 deliberately redacts fields containing
        # PASSWORD/PASSWD.  Project the non-secret sudo fact under a neutral
        # wire name so the complete governed stdout remains machine-parseable;
        # the underlying host-identity contract keeps its original field.
        observation = {
            "expected_host": raw_observation["expected_host"],
            "observed_host": raw_observation["observed_host"],
            "non_root_uid": raw_observation["non_root_uid"],
            "sudo_noprompt_present": raw_observation[
                "passwordless_sudo_present"
            ],
            "delegated_controllers": raw_observation[
                "delegated_controllers"
            ],
            "deferred_root_only_controllers": raw_observation[
                "deferred_root_only_controllers"
            ],
            "throwaway_root_under_runtime_dir": raw_observation[
                "throwaway_root_under_runtime_dir"
            ],
        }
    elif mode == "postcheck":
        if not isinstance(unit, str) or UNIT_RE.fullmatch(unit) is None:
            raise ValueError("postcheck unit is outside the exact absent-unit contract")
        if teardown_root != intent.get("throwaway_root"):
            raise ValueError(
                "postcheck teardown_root differs from the operator-authorized intent"
            )
        observation = target_host.independent_postcheck_on_host(
            unit=unit,
            teardown_root=str(teardown_root),
        )
    else:
        raise ValueError("target-host observation mode is invalid")
    return {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "mode": mode,
        "source_head": source_head,
        "intent_digest": intent["self_digest"],
        "operator_authorization_digest": authorization[
            "authorization_digest"
        ],
        "observation": observation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "postcheck"), required=True)
    parser.add_argument("--intent-base64", required=True)
    parser.add_argument("--permit-base64", required=True)
    parser.add_argument("--signature-base64", required=True)
    parser.add_argument("--unit")
    parser.add_argument("--teardown-root")
    args = parser.parse_args()
    try:
        result = observe(
            mode=args.mode,
            intent=_decode_json(args.intent_base64, "intent"),
            authorization=_decode_json(args.permit_base64, "operator permit"),
            signature=_decode_signature(args.signature_base64),
            unit=args.unit,
            teardown_root=args.teardown_root,
        )
    except ValueError as error:
        sys.stderr.write(str(error) + "\n")
        return 3
    sys.stdout.write(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
