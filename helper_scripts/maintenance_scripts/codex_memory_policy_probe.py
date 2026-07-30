#!/usr/bin/env python3
"""Read-only capability probe for the project Codex memory policy."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from collections.abc import Callable
from typing import Any


SCHEMA_VERSION = "codex_memory_policy_capability_v1"
SELECTED_MODEL = "gpt-5.6-luna"
CONFIG_VALUES = {
    "memories.consolidation_model": f'"{SELECTED_MODEL}"',
    "memories.disable_on_external_context": "true",
    "memories.extract_model": f'"{SELECTED_MODEL}"',
    "memories.generate_memories": "true",
    "memories.use_memories": "true",
}
Runner = Callable[..., subprocess.CompletedProcess[str]]


def _result(
    *,
    status: str,
    codex_version: str | None,
    supported_keys: list[str],
    selected_models_available: list[str],
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "codex_version": codex_version,
        "supported_keys": supported_keys,
        "selected_models_available": selected_models_available,
        "reasons": reasons,
    }


def _invoke(
    runner: Runner, args: list[str],
) -> subprocess.CompletedProcess[str]:
    return runner(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )


def _catalog_slugs(payload: Any) -> set[str]:
    models = payload if isinstance(payload, list) else (
        payload.get("models", []) if isinstance(payload, dict) else []
    )
    result: set[str] = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        for field in ("slug", "id", "model"):
            value = item.get(field)
            if isinstance(value, str):
                result.add(value)
                break
    return result


def probe_codex_memory_policy(
    codex_path: str,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Confirm strict key parsing and bundled-model availability without a session."""

    reasons: list[str] = []
    version: str | None = None
    supported_keys: list[str] = []
    selected_models: list[str] = []
    try:
        version_run = _invoke(runner, [codex_path, "--version"])
    except (FileNotFoundError, OSError):
        return _result(
            status="EXTERNAL_LIMIT",
            codex_version=None,
            supported_keys=[],
            selected_models_available=[],
            reasons=["CODEX_BINARY_UNAVAILABLE"],
        )
    except subprocess.TimeoutExpired:
        return _result(
            status="EXTERNAL_LIMIT",
            codex_version=None,
            supported_keys=[],
            selected_models_available=[],
            reasons=["CODEX_VERSION_PROBE_TIMEOUT"],
        )
    match = re.search(r"\bcodex-cli\s+([^\s]+)", version_run.stdout)
    if match:
        version = match.group(1)
    else:
        reasons.append("CODEX_VERSION_UNPARSEABLE")

    known_args = [
        codex_path,
        "app-server",
        "--strict-config",
        "--listen",
        "off",
    ]
    for key in sorted(CONFIG_VALUES):
        known_args.extend(("-c", f"{key}={CONFIG_VALUES[key]}"))
    try:
        known = _invoke(runner, known_args)
        known_output = f"{known.stdout}\n{known.stderr}".lower()
        if (
            "unknown configuration field" in known_output
            or "strict-config` is not supported" in known_output
            or "unexpected argument '--strict-config'" in known_output
        ):
            reasons.append("STRICT_CONFIG_VALIDATION_UNAVAILABLE")
        else:
            supported_keys = sorted(CONFIG_VALUES)
    except (OSError, subprocess.TimeoutExpired):
        reasons.append("STRICT_CONFIG_VALIDATION_UNAVAILABLE")

    unknown_args = [
        codex_path,
        "app-server",
        "--strict-config",
        "--listen",
        "off",
        "-c",
        "memories.__governance_unknown_probe=true",
    ]
    try:
        unknown = _invoke(runner, unknown_args)
        unknown_output = f"{unknown.stdout}\n{unknown.stderr}"
        if (
            unknown.returncode == 0
            or "unknown configuration field "
            "`memories.__governance_unknown_probe`" not in unknown_output
        ):
            reasons.append("STRICT_CONFIG_UNKNOWN_KEY_NOT_REJECTED")
    except (OSError, subprocess.TimeoutExpired):
        if "STRICT_CONFIG_VALIDATION_UNAVAILABLE" not in reasons:
            reasons.append("STRICT_CONFIG_VALIDATION_UNAVAILABLE")

    try:
        catalog_run = _invoke(
            runner, [codex_path, "debug", "models", "--bundled"]
        )
        catalog = json.loads(catalog_run.stdout)
        if SELECTED_MODEL in _catalog_slugs(catalog):
            selected_models = [SELECTED_MODEL]
        else:
            reasons.append("SELECTED_MEMORY_MODEL_UNAVAILABLE")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        reasons.append("MODEL_CATALOG_UNAVAILABLE")

    reasons = list(dict.fromkeys(reasons))
    return _result(
        status="SUPPORTED" if not reasons else "EXTERNAL_LIMIT",
        codex_version=version,
        supported_keys=supported_keys,
        selected_models_available=selected_models,
        reasons=reasons,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", default=shutil.which("codex") or "codex")
    args = parser.parse_args()
    result = probe_codex_memory_policy(args.codex)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "SUPPORTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
