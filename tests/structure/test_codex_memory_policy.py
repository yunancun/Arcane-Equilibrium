"""Project memory-generation policy and host-capability probe tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from codex_memory_policy_probe import probe_codex_memory_policy  # noqa: E402


def test_project_memory_policy_excludes_external_context_and_uses_luna() -> None:
    config = tomllib.loads(
        (ROOT / ".codex/config.toml").read_text(encoding="utf-8")
    )
    assert config["features"]["memories"] is True
    assert config["memories"] == {
        "generate_memories": True,
        "use_memories": True,
        "disable_on_external_context": True,
        "extract_model": "gpt-5.6-luna",
        "consolidation_model": "gpt-5.6-luna",
    }


def _completed(
    args: list[str], *, returncode: int = 0, stdout: str = "", stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def _supported_runner(args, **_kwargs):
    argv = list(args)
    if argv[-1] == "--version":
        return _completed(argv, stdout="codex-cli 0.146.0-alpha.3.1\n")
    if argv[1:4] == ["debug", "models", "--bundled"]:
        return _completed(
            argv,
            stdout=json.dumps({"models": [{"slug": "gpt-5.6-luna"}]}),
        )
    if any("__governance_unknown_probe" in value for value in argv):
        return _completed(
            argv,
            returncode=1,
            stderr="unknown configuration field `memories.__governance_unknown_probe`",
        )
    return _completed(
        argv,
        returncode=1,
        stderr="failed to initialize sqlite state runtime",
    )


def test_memory_policy_probe_reports_supported_keys_and_model() -> None:
    result = probe_codex_memory_policy("/opt/codex", runner=_supported_runner)
    assert result == {
        "schema_version": "codex_memory_policy_capability_v1",
        "status": "SUPPORTED",
        "codex_version": "0.146.0-alpha.3.1",
        "supported_keys": [
            "features.memories",
            "memories.consolidation_model",
            "memories.disable_on_external_context",
            "memories.extract_model",
            "memories.generate_memories",
            "memories.use_memories",
        ],
        "selected_models_available": ["gpt-5.6-luna"],
        "reasons": [],
    }


def test_memory_policy_probe_binds_project_root_and_feature_gate() -> None:
    invocations: list[tuple[list[str], object]] = []

    def recording_runner(args, **kwargs):
        invocations.append((list(args), kwargs.get("cwd")))
        return _supported_runner(args, **kwargs)

    result = probe_codex_memory_policy(
        "/opt/codex",
        runner=recording_runner,
    )

    assert result["status"] == "SUPPORTED"
    assert invocations
    assert all(cwd == ROOT for _, cwd in invocations)
    strict_config_call = next(
        argv for argv, _ in invocations if "--strict-config" in argv
    )
    assert "features.memories=true" in strict_config_call


def test_missing_or_older_host_returns_explicit_external_limit() -> None:
    def missing(_args, **_kwargs):
        raise FileNotFoundError

    missing_result = probe_codex_memory_policy("/missing/codex", runner=missing)
    assert missing_result["status"] == "EXTERNAL_LIMIT"
    assert "CODEX_BINARY_UNAVAILABLE" in missing_result["reasons"]

    def old_runner(args, **_kwargs):
        argv = list(args)
        if argv[-1] == "--version":
            return _completed(argv, stdout="codex-cli 0.120.0\n")
        return _completed(
            argv,
            returncode=2,
            stderr="unexpected argument '--strict-config'",
        )

    old_result = probe_codex_memory_policy("/opt/old-codex", runner=old_runner)
    assert old_result["status"] == "EXTERNAL_LIMIT"
    assert "STRICT_CONFIG_VALIDATION_UNAVAILABLE" in old_result["reasons"]


def test_unknown_memory_config_key_is_not_silently_accepted() -> None:
    def permissive_runner(args, **kwargs):
        argv = list(args)
        if any("__governance_unknown_probe" in value for value in argv):
            return _completed(argv, returncode=0)
        return _supported_runner(args, **kwargs)

    result = probe_codex_memory_policy("/opt/codex", runner=permissive_runner)
    assert result["status"] == "EXTERNAL_LIMIT"
    assert "STRICT_CONFIG_UNKNOWN_KEY_NOT_REJECTED" in result["reasons"]
