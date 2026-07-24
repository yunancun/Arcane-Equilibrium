"""Semantic validation for operator-authenticated target-host command captures."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any

import agent_governance_command_capture_v2 as command_capture
import agent_governance_target_host_operator_authorization as operator_auth


OBSERVATION_SCRIPT = (
    "helper_scripts/maintenance_scripts/"
    "agent_governance_target_host_observation.py"
)
OBSERVATION_SCHEMA_VERSION = "target_host_governed_observation_v1"
UNIT_RE = re.compile(r"^aiml-probeB-(?:absent|final)-[0-9]+\.scope$")


def _decode_json(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    try:
        decoded = base64.b64decode(value, validate=True)
        artifact = json.loads(decoded.decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    return artifact if isinstance(artifact, dict) else None


def _decode_signature(value: Any) -> bytes:
    if not isinstance(value, str):
        return b""
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        return b""


def _argv_inputs(
    argv: Any,
    *,
    expected_mode: str,
) -> tuple[list[str], dict[str, Any] | None, dict[str, Any] | None, bytes, str | None, str | None]:
    if not isinstance(argv, list) or any(
        not isinstance(item, str) for item in argv
    ):
        return [], None, None, b"", None, None
    if (
        len(argv) not in {10, 14}
        or argv[0] not in {"python", "python3"}
        or argv[1] != OBSERVATION_SCRIPT
        or argv[2:4] != ["--mode", expected_mode]
        or argv[4] != "--intent-base64"
        or argv[6] != "--permit-base64"
        or argv[8] != "--signature-base64"
    ):
        return argv, None, None, b"", None, None
    intent = _decode_json(argv[5])
    permit = _decode_json(argv[7])
    signature = _decode_signature(argv[9])
    unit: str | None = None
    teardown_root: str | None = None
    if expected_mode == "preflight":
        if len(argv) != 10:
            return argv, None, None, b"", None, None
    elif expected_mode == "postcheck":
        if (
            len(argv) != 14
            or argv[10] != "--unit"
            or UNIT_RE.fullmatch(argv[11]) is None
            or argv[12] != "--teardown-root"
        ):
            return argv, None, None, b"", None, None
        unit, teardown_root = argv[11], argv[13]
    else:
        return argv, None, None, b"", None, None
    return argv, intent, permit, signature, unit, teardown_root


def validate_target_host_observation_capture(
    capture: Any,
    *,
    expected_mode: str,
    expected_source_head: str,
    expected_intent_digest: str,
    expected_node_id: str,
    expected_residue_observation: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, Any] | None]:
    """Validate command, signed intent, output bytes, and observation semantics."""

    errors = command_capture.validate_governed_command_capture(
        capture,
        expected_source_head=expected_source_head,
    )
    if not isinstance(capture, dict):
        return errors, None
    if capture.get("node_id") != expected_node_id:
        errors.append(
            "target-host observation capture node differs from the declared OPS node"
        )
    (
        argv,
        intent,
        permit,
        signature,
        unit,
        teardown_root,
    ) = _argv_inputs(capture.get("argv"), expected_mode=expected_mode)
    if not argv or intent is None or permit is None or not signature:
        errors.append(
            "target-host observation capture argv is not the exact "
            "operator-authenticated observer invocation"
        )
        return errors, None
    if intent.get("self_digest") != expected_intent_digest:
        errors.append(
            "target-host observation capture intent differs from the effect intent"
        )
    if expected_mode == "postcheck" and teardown_root != intent.get(
        "throwaway_root"
    ):
        errors.append(
            "target-host postcheck teardown_root differs from its signed intent"
        )
    auth_errors = operator_auth.validate_operator_authorization(
        permit,
        signature,
        intent=intent,
        source_head=expected_source_head,
        now=str(capture.get("completed_at", "")),
        actual_host=str(intent.get("expected_host", "")),
    )
    errors.extend(
        "target-host observation operator authorization: " + error
        for error in auth_errors
    )
    stdout = capture.get("stdout")
    preview = stdout.get("preview_text") if isinstance(stdout, dict) else None
    if not isinstance(preview, str):
        errors.append("target-host observation stdout is not complete UTF-8")
        return errors, None
    raw = preview.encode("utf-8")
    if (
        capture.get("result") != "PASS"
        or capture.get("exit_code") != 0
        or stdout.get("encoding") != "utf-8"
        or stdout.get("truncated") is not False
        or stdout.get("bytes") != len(raw)
        or stdout.get("digest")
        != "sha256:" + hashlib.sha256(raw).hexdigest()
    ):
        errors.append("target-host observation stdout is incomplete or invalid")
        return errors, None
    try:
        artifact = json.loads(preview)
    except ValueError:
        errors.append("target-host observation stdout is not JSON")
        return errors, None
    expected_fields = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "mode": expected_mode,
        "source_head": expected_source_head,
        "intent_digest": expected_intent_digest,
        "operator_authorization_digest": permit.get(
            "authorization_digest"
        ),
    }
    if not isinstance(artifact, dict) or set(artifact) != {
        *expected_fields,
        "observation",
    }:
        errors.append("target-host observation artifact fields are invalid")
        return errors, None
    for field, expected in expected_fields.items():
        if artifact.get(field) != expected:
            errors.append(
                f"target-host observation {field} is not capture-bound"
            )
    observation = artifact.get("observation")
    if not isinstance(observation, dict):
        errors.append("target-host observation payload is missing")
        return errors, None
    if expected_mode == "preflight":
        if (
            observation.get("expected_host") != intent.get("expected_host")
            or observation.get("observed_host") != intent.get("expected_host")
            or observation.get("non_root_uid") is not True
            or observation.get("sudo_noprompt_present") is not False
            or observation.get("throwaway_root_under_runtime_dir") is not True
        ):
            errors.append(
                "target-host preflight observation lacks the exact safe host facts"
            )
    else:
        expected_postcheck = {
            "unit_absent": True,
            "cgroup_gone": True,
            "temp_gone": True,
            "no_residue": True,
        }
        if observation != expected_postcheck:
            errors.append(
                "target-host postcheck observation is not an exact zero-residue sweep"
            )
        if expected_residue_observation is not None:
            projected = {
                "units_gone": observation.get("unit_absent"),
                "cgroup_gone": observation.get("cgroup_gone"),
                "netns_gone": True,
                "temp_gone": observation.get("temp_gone"),
            }
            if projected != expected_residue_observation:
                errors.append(
                    "target-host postcheck capture differs from the attached residue observation"
                )
    return errors, observation if not errors else None
