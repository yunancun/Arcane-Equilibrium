#!/usr/bin/env python3
"""Retrieve one fixed-profile, capability-attested S2.5 host capture.

The unprivileged producer never authors source, host, process, clock, or identity
claims and never submits bytes for signing.  A separately provisioned root-owned
attestor derives the complete artifact from its immutable source view, signs it,
and returns bounded JSON.  This wrapper only parses and verifies that artifact.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import stat
import sys
from typing import Any

import agent_governance_s2_host_kernel as host_kernel
from aiml_gate_receipt_s2_5_host_capture import (
    HOST_CAPTURE_ATTESTOR_CAPABILITY_PATH,
    validate_s2_5_recovery_host_capture,
)


def _reject_nonfinite_json(token: str) -> None:
    raise ValueError(f"non-finite JSON token is forbidden: {token}")


def _closed_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _decode_attestor_artifact(payload: bytes) -> dict[str, Any]:
    try:
        decoded = payload.decode("utf-8")
        artifact = json.loads(
            decoded,
            object_pairs_hook=_closed_json_object,
            parse_constant=_reject_nonfinite_json,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("fixed host-capture attestor returned invalid JSON") from error
    if not isinstance(artifact, dict):
        raise ValueError("fixed host-capture attestor did not return one artifact")
    return artifact


def _invoke_fixed_attestor_capability() -> bytes:
    path = Path(HOST_CAPTURE_ATTESTOR_CAPABILITY_PATH)
    metadata = path.lstat()
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_nlink != 1
        or mode & 0o022
        or not mode & 0o111
    ):
        raise ValueError("fixed host-capture attestor capability is not trusted")
    try:
        return host_kernel.HostExecutionKernel(
            session=host_kernel.SESSION_S2_5_RECOVERY_HOST_CAPTURE
        ).capture_recovery_host()
    except host_kernel.S2HostKernelError as error:
        raise ValueError(
            "fixed host-capture attestor capability denied the request"
        ) from error


def _trusted_current_time() -> datetime:
    """Read the verifier-side host clock after the attestor returns."""

    return datetime.now(timezone.utc)


def capture_s2_5_recovery_host() -> dict[str, Any]:
    """Retrieve and validate the capability-authored disposable host capture."""

    artifact = _decode_attestor_artifact(_invoke_fixed_attestor_capability())
    errors = validate_s2_5_recovery_host_capture(
        artifact,
        now=_trusted_current_time(),
    )
    if errors:
        raise ValueError("attested host capture is invalid: " + "; ".join(errors))
    return artifact


def main(argv: list[str] | None = None) -> int:
    if list(sys.argv[1:] if argv is None else argv):
        raise SystemExit("host-capture producer accepts no arguments")
    artifact = capture_s2_5_recovery_host()
    print(json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
