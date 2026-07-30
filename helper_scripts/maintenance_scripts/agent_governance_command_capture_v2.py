"""One-call, context-bound local command capture Adapter."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from agent_governance_capture import (
    LOCAL_REPRODUCIBLE,
    REPO_ROOT,
)
from agent_governance_command_replay import (
    CANONICAL_TEST_OUTPUT_V1,
    EXACT_OUTPUT,
    RESULT_ONLY,
    command_argv,
    replay_contract_for,
)
from agent_governance_context_validation import validate_context_artifact
from agent_governance_generation_summary import capture_generation_summary
from agent_governance_permissions import authorize_native_command
from agent_governance_pytest_provider import (
    GOVERNED_PYTEST_BOOTSTRAP,
    GOVERNED_PYTEST_PREFIX,
    GOVERNED_PYTEST_PROVIDER_LOCK_PATH,
    GOVERNED_PYTEST_PROVIDER_PROFILE_ID,
    GOVERNED_PYTEST_PROVIDER_WHEEL_PREFIX,
    GOVERNED_PYTEST_REQUIRED_ARGS,
)
from agent_governance_registry import native_agent_contract
from agent_governance_routing import route_task
from agent_governance_workflow_receipts import canonical_digest


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
DURATION_RE = re.compile(rb"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?(?:ms|s)(?![A-Za-z0-9_.])")
PREVIEW_LIMIT = 4096
LOCAL_POLICY_CLASSES = {
    "repo_or_local_test_read", "governance_readonly", "local_test_adapter",
    "node_scoped_read_only",
}
EXECUTION_TASK_FIELDS = {
    "node_id", "role", "native_agent", "node_class", "permission",
    "requires", "path_scope",
}
GENERATION_FIELDS = {
    "schema_version", "scope", "source_head", "generation_digest",
    "observed_at", "record_digest",
}
OUTPUT_FIELDS = {
    "encoding", "preview_text", "preview_base64", "preview_source_bytes",
    "bytes", "digest", "replay_digest", "truncated", "preview_redacted",
}
RECORD_FIELDS = {
    "schema_version", "trust_tier", "context_artifact_digest",
    "task_contract_digest", "execution_task", "execution_task_digest",
    "node_id", "role_id", "native_agent", "node_class", "permission",
    "path_scope", "argv", "command", "authorization", "replay_contract",
    "timeout_seconds", "started_at", "completed_at", "exit_code",
    "timed_out", "result", "stdout", "stderr", "repository_before",
    "repository_after", "whole_repository_before", "whole_repository_after",
    "pytest_provider", "effect_enforcement", "host_sandbox_attestation_ref",
    "record_digest",
}
LEGACY_RECORD_FIELDS = RECORD_FIELDS - {"pytest_provider"}
PYTEST_PROVIDER_FIELDS = {
    "schema_version", "profile_id", "bootstrap_digest", "interpreter_path",
    "interpreter_digest_before", "interpreter_digest_after",
    "source_kind", "source_head", "lock_path", "lock_blob", "lock_sha256",
    "distribution_manifest", "wheel_manifest", "file_manifest",
    "provider_digest_before", "provider_digest_after", "provider_stable",
    "site_import_disabled",
    "candidate_cwd_removed_by_bootstrap", "plugin_autoload_disabled",
    "conftest_loading_disabled", "project_config_loading_disabled",
    "test_import_path_appended", "repository_root_fixed",
}
PYTEST_PROVIDER_REQUIRED_DISTRIBUTIONS = (
    "iniconfig",
    "packaging",
    "pluggy",
    "Pygments",
    "pytest",
)
PYTEST_PROVIDER_OPTIONAL_DISTRIBUTIONS = (
    "exceptiongroup",
    "tomli",
    "typing_extensions",
)
PYTEST_PROVIDER_DISTRIBUTIONS = (
    *PYTEST_PROVIDER_REQUIRED_DISTRIBUTIONS,
    *PYTEST_PROVIDER_OPTIONAL_DISTRIBUTIONS,
)
PYTEST_PROVIDER_LOCK_FIELDS = {
    "schema_version", "profile_id", "required_distributions",
    "optional_distributions", "wheel_tag", "limits", "wheels",
}
PYTEST_PROVIDER_LIMIT_FIELDS = {
    "max_wheels", "max_members_per_wheel", "max_member_bytes",
    "max_total_uncompressed_bytes",
}
PYTEST_PROVIDER_WHEEL_FIELDS = {"name", "version", "path", "sha256"}
PYTEST_PROVIDER_WHEEL_IDENTITY_FIELDS = {
    "name", "version", "path", "git_blob", "bytes", "sha256",
}
PYTEST_PROVIDER_HARD_LIMITS = {
    "max_wheels": 8,
    "max_members_per_wheel": 2048,
    "max_member_bytes": 8 * 1024 * 1024,
    "max_total_uncompressed_bytes": 32 * 1024 * 1024,
}
SAFE_INHERITED_ENVIRONMENT = {
    "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "SYSTEMROOT",
}
SECRET_VALUE_PATTERNS = (
    re.compile(
        rb"(?i)([\"']?[A-Z0-9_.-]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIAL)[A-Z0-9_.-]*[\"']?\s*[:=]\s*[\"']?)([^\s,;}\"']+)"
    ),
    re.compile(rb"(?i)(authorization\s*:\s*bearer\s+)([A-Za-z0-9._~+/=-]+)"),
    re.compile(rb"(?i)(https?://)([^/\s:@]+):([^/@\s]+)@"),
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _self_digest(value: dict[str, Any]) -> str:
    return _digest_bytes(_canonical_bytes({
        key: item for key, item in value.items() if key != "record_digest"
    }))


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _generation_summary(scope: list[str], root: Path) -> dict[str, Any]:
    return capture_generation_summary(scope, root=root)


def _normalized_digest(handle: BinaryIO, replay_contract: str) -> str | None:
    if replay_contract == RESULT_ONLY:
        return None
    handle.seek(0)
    digest = hashlib.sha256()
    tail = b""
    while True:
        chunk = handle.read(64 * 1024)
        if not chunk:
            break
        data = tail + chunk
        if len(data) <= 256:
            tail = data
            continue
        body, tail = data[:-256], data[-256:]
        digest.update(
            DURATION_RE.sub(b"<duration>", body)
            if replay_contract == CANONICAL_TEST_OUTPUT_V1 else body
        )
    digest.update(
        DURATION_RE.sub(b"<duration>", tail)
        if replay_contract == CANONICAL_TEST_OUTPUT_V1 else tail
    )
    return "sha256:" + digest.hexdigest()


def _redact_preview(data: bytes) -> tuple[bytes, bool]:
    redacted = data
    for index, pattern in enumerate(SECRET_VALUE_PATTERNS):
        replacement = rb"\1<redacted>@" if index == 2 else rb"\1<redacted>"
        redacted = pattern.sub(replacement, redacted)
    return redacted, redacted != data


def _is_text(data: bytes) -> bool:
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False
    return not any(
        byte == 0 or (byte < 32 and byte not in b"\t\n\r") for byte in data
    )


def _bounded_text(data: bytes) -> str:
    candidate = data[:PREVIEW_LIMIT]
    while candidate:
        try:
            return candidate.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            if error.end != len(candidate):
                return candidate.decode("utf-8", errors="replace")
            candidate = candidate[:-1]
    return ""


def _output_summary(handle: BinaryIO, replay_contract: str) -> dict[str, Any]:
    handle.seek(0)
    raw_digest = hashlib.sha256()
    total = 0
    preview = bytearray()
    while True:
        chunk = handle.read(64 * 1024)
        if not chunk:
            break
        raw_digest.update(chunk)
        total += len(chunk)
        if len(preview) < PREVIEW_LIMIT:
            preview.extend(chunk[: PREVIEW_LIMIT - len(preview)])
    result_only = replay_contract == RESULT_ONLY
    source_preview = b"" if result_only else bytes(preview)
    shown, secret_redacted = _redact_preview(source_preview)
    shown = shown[:PREVIEW_LIMIT]
    textual = _is_text(shown)
    return {
        "encoding": "utf-8" if textual else "base64",
        "preview_text": _bounded_text(shown) if textual else None,
        "preview_base64": (
            None if textual else base64.b64encode(shown).decode("ascii")
        ),
        "preview_source_bytes": len(source_preview),
        "bytes": total,
        "digest": "sha256:" + raw_digest.hexdigest(),
        "replay_digest": _normalized_digest(handle, replay_contract),
        "truncated": total > len(source_preview),
        "preview_redacted": result_only or secret_redacted,
    }


def _is_pytest_argv(argv: list[str]) -> bool:
    return (
        tuple(argv[:4]) == GOVERNED_PYTEST_PREFIX
        or argv[:3] in (["python", "-m", "pytest"], ["python3", "-m", "pytest"])
        or (argv and argv[0].lower() == "pytest")
    )


def _is_governed_pytest_argv(argv: list[str]) -> bool:
    required_end = 4 + len(GOVERNED_PYTEST_REQUIRED_ARGS)
    return (
        tuple(argv[:4]) == GOVERNED_PYTEST_PREFIX
        and tuple(argv[4:required_end]) == GOVERNED_PYTEST_REQUIRED_ARGS
    )


def _raw_file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(64 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _capsule_file_manifest(capsule: Path) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for path in sorted(capsule.rglob("*")):
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("pytest provider capsule contains a non-regular file")
        manifest.append({
            "path": path.relative_to(capsule).as_posix(),
            "bytes": metadata.st_size,
            "sha256": _raw_file_digest(path),
        })
    return sorted(manifest, key=lambda item: item["path"])


def _pytest_provider_digest(
    distributions: list[dict[str, str]],
    wheels: list[dict[str, Any]],
    files: list[dict[str, Any]],
    *,
    source_head: str,
    lock_blob: str,
    lock_sha256: str,
) -> str:
    return canonical_digest({
        "schema_version": "governed_pytest_provider_payload_v1",
        "source_kind": "CODE_OWNED_GIT_BLOB",
        "source_head": source_head,
        "lock_path": GOVERNED_PYTEST_PROVIDER_LOCK_PATH,
        "lock_blob": lock_blob,
        "lock_sha256": lock_sha256,
        "distribution_manifest": distributions,
        "wheel_manifest": wheels,
        "file_manifest": files,
    })


def _strict_json_object(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)


def _git_blob_at_head(
    source_head: str, path: str,
) -> tuple[str, bytes]:
    if re.fullmatch(r"[0-9a-f]{40}", source_head) is None:
        raise ValueError("governed pytest provider source head is invalid")
    repository = Path(__file__).resolve().parents[2]
    listing = subprocess.run(
        ["git", "ls-tree", source_head, "--", path],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.rstrip("\n")
    if not listing:
        raise ValueError(
            f"governed pytest provider code-owned Git blob is missing: {path}"
        )
    metadata, listed_path = listing.split("\t", 1)
    mode, object_type, blob = metadata.split()
    if (
        listed_path != path
        or mode != "100644"
        or object_type != "blob"
        or re.fullmatch(r"[0-9a-f]{40}", blob) is None
    ):
        raise ValueError(
            f"governed pytest provider path is not one regular 100644 Git blob: {path}"
        )
    raw = subprocess.run(
        ["git", "show", f"{source_head}:{path}"],
        cwd=repository,
        check=True,
        capture_output=True,
    ).stdout
    return blob, raw


def _provider_tree_paths(source_head: str) -> list[str]:
    repository = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [
            "git", "ls-tree", "-r", "--name-only", source_head, "--",
            GOVERNED_PYTEST_PROVIDER_WHEEL_PREFIX,
        ],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()


def _load_pytest_provider_bundle(
    source_head: str,
) -> tuple[
    dict[str, Any],
    list[dict[str, str]],
    list[dict[str, Any]],
    list[tuple[dict[str, Any], bytes]],
]:
    lock_blob, lock_raw = _git_blob_at_head(
        source_head, GOVERNED_PYTEST_PROVIDER_LOCK_PATH
    )
    try:
        lock = _strict_json_object(lock_raw)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(
            f"governed pytest provider lock is invalid JSON: {error}"
        ) from error
    if not isinstance(lock, dict) or set(lock) != PYTEST_PROVIDER_LOCK_FIELDS:
        raise ValueError("governed pytest provider lock fields are invalid")
    expected_values = {
        "schema_version": "governed_pytest_provider_lock_v1",
        "profile_id": GOVERNED_PYTEST_PROVIDER_PROFILE_ID,
        "required_distributions": list(
            PYTEST_PROVIDER_REQUIRED_DISTRIBUTIONS
        ),
        "optional_distributions": list(
            PYTEST_PROVIDER_OPTIONAL_DISTRIBUTIONS
        ),
        "wheel_tag": "py3-none-any",
        "limits": PYTEST_PROVIDER_HARD_LIMITS,
    }
    for field, expected in expected_values.items():
        if lock.get(field) != expected:
            raise ValueError(
                f"governed pytest provider lock {field} is not code-owned"
            )
    wheels = lock.get("wheels")
    if (
        not isinstance(wheels, list)
        or len(wheels) != len(PYTEST_PROVIDER_DISTRIBUTIONS)
        or len(wheels) > PYTEST_PROVIDER_HARD_LIMITS["max_wheels"]
    ):
        raise ValueError("governed pytest provider wheel set is incomplete")
    expected_names = sorted(
        PYTEST_PROVIDER_DISTRIBUTIONS, key=str.lower
    )
    observed_names: list[str] = []
    observed_paths: list[str] = []
    distribution_manifest: list[dict[str, str]] = []
    wheel_manifest: list[dict[str, Any]] = []
    wheel_payloads: list[tuple[dict[str, Any], bytes]] = []
    for wheel in wheels:
        if (
            not isinstance(wheel, dict)
            or set(wheel) != PYTEST_PROVIDER_WHEEL_FIELDS
        ):
            raise ValueError("governed pytest provider wheel entry is invalid")
        name, version, path, expected_digest = (
            wheel.get("name"),
            wheel.get("version"),
            wheel.get("path"),
            wheel.get("sha256"),
        )
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(version, str)
            or not version
            or not isinstance(path, str)
            or not path.startswith(GOVERNED_PYTEST_PROVIDER_WHEEL_PREFIX)
            or "\\" in path
            or "\x00" in path
            or PurePosixPath(path).is_absolute()
            or ".." in PurePosixPath(path).parts
            or not path.endswith("-py3-none-any.whl")
            or not DIGEST_RE.fullmatch(str(expected_digest))
        ):
            raise ValueError(
                "governed pytest provider wheel binding is unsafe"
            )
        blob, raw = _git_blob_at_head(source_head, path)
        actual_digest = _digest_bytes(raw)
        if actual_digest != expected_digest:
            raise ValueError(
                f"governed pytest provider wheel hash differs: {path}"
            )
        observed_names.append(name)
        observed_paths.append(path)
        distribution_manifest.append({"name": name, "version": version})
        identity = {
            "name": name,
            "version": version,
            "path": path,
            "git_blob": blob,
            "bytes": len(raw),
            "sha256": actual_digest,
        }
        wheel_manifest.append(identity)
        wheel_payloads.append((identity, raw))
    if (
        observed_names != expected_names
        or observed_paths != sorted(set(observed_paths))
        or _provider_tree_paths(source_head) != observed_paths
    ):
        raise ValueError(
            "governed pytest provider wheel paths are missing, extra, or unsorted"
        )
    lock_identity = {
        "path": GOVERNED_PYTEST_PROVIDER_LOCK_PATH,
        "git_blob": lock_blob,
        "sha256": _digest_bytes(lock_raw),
    }
    return (
        lock_identity,
        distribution_manifest,
        wheel_manifest,
        wheel_payloads,
    )


def _extract_provider_wheels(
    capsule: Path,
    wheel_payloads: list[tuple[dict[str, Any], bytes]],
) -> None:
    observed_paths: set[str] = set()
    total_uncompressed = 0
    for identity, raw in wheel_payloads:
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except (OSError, zipfile.BadZipFile) as error:
            raise ValueError(
                f"governed pytest provider wheel is not a ZIP: {identity['path']}"
            ) from error
        with archive:
            members = archive.infolist()
            if len(members) > PYTEST_PROVIDER_HARD_LIMITS[
                "max_members_per_wheel"
            ]:
                raise ValueError(
                    "governed pytest provider wheel exceeds member limit"
                )
            for member in members:
                name = member.filename
                relative = PurePosixPath(name)
                mode = member.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if (
                    not name
                    or "\\" in name
                    or "\x00" in name
                    or relative.is_absolute()
                    or ".." in relative.parts
                    or name.lower().endswith(".pth")
                    or member.flag_bits & 0x1
                    or (
                        file_type
                        and file_type not in {stat.S_IFREG, stat.S_IFDIR}
                    )
                ):
                    raise ValueError(
                        f"governed pytest provider wheel member is unsafe: {name!r}"
                    )
                if member.is_dir():
                    continue
                if (
                    name in observed_paths
                    or member.file_size
                    > PYTEST_PROVIDER_HARD_LIMITS["max_member_bytes"]
                ):
                    raise ValueError(
                        "governed pytest provider wheel has duplicate or oversized member"
                    )
                total_uncompressed += member.file_size
                if total_uncompressed > PYTEST_PROVIDER_HARD_LIMITS[
                    "max_total_uncompressed_bytes"
                ]:
                    raise ValueError(
                        "governed pytest provider exceeds uncompressed byte limit"
                    )
                content = archive.read(member)
                if len(content) != member.file_size:
                    raise ValueError(
                        "governed pytest provider wheel member size differs"
                    )
                destination = capsule.joinpath(*relative.parts)
                destination.parent.mkdir(
                    parents=True, exist_ok=True, mode=0o700
                )
                try:
                    with destination.open("xb") as handle:
                        handle.write(content)
                        handle.flush()
                        os.fsync(handle.fileno())
                except FileExistsError as error:
                    raise ValueError(
                        "governed pytest provider wheel path overlaps"
                    ) from error
                destination.chmod(0o400)
                observed_paths.add(name)


def _prepare_pytest_provider(
    isolated_root: Path, *, argv: list[str], source_head: str
) -> tuple[Path | None, dict[str, Any] | None]:
    if not _is_pytest_argv(argv):
        return None, None
    if not _is_governed_pytest_argv(argv):
        raise ValueError(
            "pytest execution requires the complete governed isolation argv"
        )
    (
        lock_identity,
        distribution_manifest,
        wheel_manifest,
        wheel_payloads,
    ) = _load_pytest_provider_bundle(source_head)
    capsule = isolated_root / "pytest-provider"
    capsule.mkdir(mode=0o700)
    _extract_provider_wheels(capsule, wheel_payloads)
    file_manifest = _capsule_file_manifest(capsule)
    interpreter = Path(sys.executable).resolve(strict=True)
    interpreter_digest = _raw_file_digest(interpreter)
    for directory in sorted(
        (path for path in capsule.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o500)
    capsule.chmod(0o500)
    provider_digest = _pytest_provider_digest(
        distribution_manifest,
        wheel_manifest,
        file_manifest,
        source_head=source_head,
        lock_blob=lock_identity["git_blob"],
        lock_sha256=lock_identity["sha256"],
    )
    identity: dict[str, Any] = {
        "schema_version": "governed_pytest_provider_v1",
        "profile_id": GOVERNED_PYTEST_PROVIDER_PROFILE_ID,
        "bootstrap_digest": _digest_bytes(
            GOVERNED_PYTEST_BOOTSTRAP.encode("utf-8")
        ),
        "interpreter_path": str(interpreter),
        "interpreter_digest_before": interpreter_digest,
        "interpreter_digest_after": interpreter_digest,
        "source_kind": "CODE_OWNED_GIT_BLOB",
        "source_head": source_head,
        "lock_path": lock_identity["path"],
        "lock_blob": lock_identity["git_blob"],
        "lock_sha256": lock_identity["sha256"],
        "distribution_manifest": distribution_manifest,
        "wheel_manifest": wheel_manifest,
        "file_manifest": file_manifest,
        "provider_digest_before": provider_digest,
        "provider_digest_after": provider_digest,
        "provider_stable": True,
        "site_import_disabled": _is_governed_pytest_argv(argv),
        "candidate_cwd_removed_by_bootstrap": _is_governed_pytest_argv(argv),
        "plugin_autoload_disabled": True,
        "conftest_loading_disabled": (
            _is_governed_pytest_argv(argv)
        ),
        "project_config_loading_disabled": _is_governed_pytest_argv(argv),
        "test_import_path_appended": _is_governed_pytest_argv(argv),
        "repository_root_fixed": _is_governed_pytest_argv(argv),
    }
    return capsule, identity


def _finalize_pytest_provider(
    capsule: Path | None,
    identity: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if capsule is None or identity is None:
        return None
    after_manifest = _capsule_file_manifest(capsule)
    after_digest = _pytest_provider_digest(
        identity["distribution_manifest"],
        identity["wheel_manifest"],
        after_manifest,
        source_head=identity["source_head"],
        lock_blob=identity["lock_blob"],
        lock_sha256=identity["lock_sha256"],
    )
    interpreter_after = _raw_file_digest(
        Path(identity["interpreter_path"])
    )
    finalized = dict(identity)
    finalized["provider_digest_after"] = after_digest
    finalized["interpreter_digest_after"] = interpreter_after
    finalized["provider_stable"] = (
        after_manifest == identity["file_manifest"]
        and after_digest == identity["provider_digest_before"]
        and interpreter_after == identity["interpreter_digest_before"]
    )
    return finalized


def _make_capsule_removable(capsule: Path | None) -> None:
    if capsule is None:
        return
    for path in capsule.rglob("*"):
        try:
            path.chmod(0o700 if path.is_dir() else 0o600)
        except OSError:
            pass
    try:
        capsule.chmod(0o700)
    except OSError:
        pass


def _controlled_environment(
    isolated_root: Path,
    *,
    argv: list[str],
    pytest_provider: Path | None = None,
) -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items()
        if key in SAFE_INHERITED_ENVIRONMENT
    }
    environment.update({
        "HOME": str(isolated_root / "home"),
        "TMPDIR": str(isolated_root / "tmp"),
        "XDG_CONFIG_HOME": str(isolated_root / "config"),
        "XDG_CACHE_HOME": str(isolated_root / "cache"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
    })
    if _is_pytest_argv(argv):
        if pytest_provider is None:
            raise ValueError("governed pytest provider capsule is absent")
        environment["PYTHONPATH"] = str(pytest_provider)
    for directory in ("home", "tmp", "config", "cache"):
        (isolated_root / directory).mkdir(mode=0o700)
    return environment


def _execute(
    argv: list[str],
    *,
    root: Path,
    timeout_seconds: int,
    replay_contract: str,
    provider_source_head: str | None = None,
) -> dict[str, Any]:
    with (
        tempfile.TemporaryDirectory(prefix="governed-command-") as isolated,
        tempfile.TemporaryFile() as stdout_file,
        tempfile.TemporaryFile() as stderr_file,
    ):
        isolated_root = Path(isolated)
        started_at = _now()
        timed_out = False
        provider_capsule: Path | None = None
        pytest_provider: dict[str, Any] | None = None
        try:
            if _is_governed_pytest_argv(argv) and provider_source_head is None:
                provider_source_head = subprocess.run(
                    ["git", "rev-parse", "--verify", "HEAD^{commit}"],
                    cwd=Path(__file__).resolve().parents[2],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            provider_capsule, pytest_provider = _prepare_pytest_provider(
                isolated_root,
                argv=argv,
                source_head=str(provider_source_head or ""),
            )
            execution_argv = (
                [pytest_provider["interpreter_path"], *argv[1:]]
                if pytest_provider is not None
                else argv
            )
            completed = subprocess.run(
                execution_argv, cwd=root, shell=False, stdin=subprocess.DEVNULL,
                stdout=stdout_file, stderr=stderr_file, timeout=timeout_seconds,
                check=False,
                env=_controlled_environment(
                    isolated_root,
                    argv=argv,
                    pytest_provider=provider_capsule,
                ),
            )
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out, exit_code = True, -1
        except (OSError, ValueError) as error:
            exit_code = 127
            stderr_file.write(str(error).encode("utf-8", errors="replace"))
        finally:
            try:
                pytest_provider = _finalize_pytest_provider(
                    provider_capsule, pytest_provider
                )
            finally:
                _make_capsule_removable(provider_capsule)
        completed_at = _now()
        return {
            "started_at": started_at, "completed_at": completed_at,
            "exit_code": exit_code, "timed_out": timed_out,
            "result": "TIMED_OUT" if timed_out else "PASS" if exit_code == 0 else "FAIL",
            "stdout": _output_summary(stdout_file, replay_contract),
            "stderr": _output_summary(stderr_file, replay_contract),
            "pytest_provider": pytest_provider,
        }


def _bound_execution_task(
    context_artifact: dict[str, Any], native_agent: str, node_id: str, root: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    validated = validate_context_artifact(context_artifact, root=root)
    if validated["errors"]:
        raise ValueError("context artifact is invalid: " + "; ".join(validated["errors"]))
    plan = validated["plan"]
    task_contract = plan["task_contract"]
    route = route_task(task_contract)
    matches = [
        task for task in route["required_role_nodes"]
        if task.get("node_id") == node_id
    ]
    if len(matches) != 1:
        raise ValueError("node_id is not one canonical routed execution task")
    task = {field: matches[0].get(field) for field in EXECUTION_TASK_FIELDS}
    identity = native_agent_contract(native_agent)
    if (
        task["native_agent"] != native_agent
        or task["role"] != identity["role_id"]
        or task["node_class"] != identity["node_class"]
        or task["permission"] != identity["permission"]
    ):
        raise PermissionError("native agent does not own the routed execution task")
    if task["node_class"] != "verification" or task["permission"] != "read_only":
        raise PermissionError("capture-command is restricted to read-only verification tasks")
    path_scope = (
        task["path_scope"]
        or task_contract.get("verification_scope", [])
        or task_contract.get("dirty_scope", [])
    )
    if not isinstance(path_scope, list) or not path_scope:
        raise ValueError("routed command capture has no non-empty derived path_scope")
    return task, task_contract, sorted(path_scope)


def capture_governed_command(
    *,
    native_agent: str,
    node_id: str,
    context_artifact: dict[str, Any],
    argv: list[str] | tuple[str, ...],
    root: Path = REPO_ROOT,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Derive identity/scope from Context and execute exactly one local argv."""

    repository = Path(root).resolve(strict=True)
    if not 1 <= timeout_seconds <= 900:
        raise ValueError("timeout_seconds must be from 1 through 900")
    execution_task, task_contract, path_scope = _bound_execution_task(
        context_artifact, native_agent, node_id, repository,
    )
    command_argv_value, command = command_argv(argv)
    if _is_pytest_argv(command_argv_value) and not _is_governed_pytest_argv(
        command_argv_value
    ):
        raise PermissionError(
            "pytest capture requires the no-site governed bootstrap and "
            "--noconftest"
        )
    authorization = authorize_native_command(native_agent, command)
    if not authorization.get("allowed"):
        raise PermissionError(f"command is not authorized: {authorization.get('reason')}")
    if authorization.get("policy_class") not in LOCAL_POLICY_CLASSES:
        raise PermissionError(
            "capture-command policy rejects direct network/private/effect argv; "
            "repository policy is not OS effect isolation"
        )
    replay_contract = replay_contract_for(
        command_argv_value, authorization.get("policy_class")
    )
    whole_before = _generation_summary(["."], repository)
    repository_before = _generation_summary(path_scope, repository)
    provider_repository = Path(__file__).resolve().parents[2]
    provider_source_head = (
        whole_before["source_head"]
        if repository == provider_repository
        else subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=provider_repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    executed = _execute(
        command_argv_value, root=repository, timeout_seconds=timeout_seconds,
        replay_contract=replay_contract,
        provider_source_head=provider_source_head,
    )
    repository_after = _generation_summary(path_scope, repository)
    whole_after = _generation_summary(["."], repository)
    record: dict[str, Any] = {
        "schema_version": "command_capture_v2",
        "trust_tier": LOCAL_REPRODUCIBLE,
        "context_artifact_digest": context_artifact["artifact_digest"],
        "task_contract_digest": context_artifact["task_contract_digest"],
        "execution_task": execution_task,
        "execution_task_digest": canonical_digest(execution_task),
        "node_id": execution_task["node_id"], "role_id": execution_task["role"],
        "native_agent": native_agent, "node_class": execution_task["node_class"],
        "permission": execution_task["permission"], "path_scope": path_scope,
        "argv": command_argv_value, "command": command,
        "authorization": authorization, "replay_contract": replay_contract,
        "timeout_seconds": timeout_seconds, **executed,
        "repository_before": repository_before,
        "repository_after": repository_after,
        "whole_repository_before": whole_before,
        "whole_repository_after": whole_after,
        "pytest_provider": executed["pytest_provider"],
        "effect_enforcement": "repository_policy_only",
        "host_sandbox_attestation_ref": None,
    }
    record["record_digest"] = _self_digest(record)
    errors = validate_governed_command_capture(
        record, expected_context_artifact_digest=context_artifact["artifact_digest"],
        expected_task_contract_digest=context_artifact["task_contract_digest"],
        expected_execution_task=execution_task, expected_path_scope=path_scope,
        root=repository,
    )
    if errors:
        raise RuntimeError("governed command capture failed: " + "; ".join(errors))
    return record


def _generation_errors(
    summary: Any, *, expected_scope: list[str], label: str,
) -> list[str]:
    if not isinstance(summary, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    if set(summary) != GENERATION_FIELDS:
        errors.append(f"{label} fields are invalid")
    if summary.get("schema_version") != "repository_generation_summary_v1":
        errors.append(f"{label} schema_version is invalid")
    if summary.get("scope") != sorted(expected_scope):
        errors.append(f"{label} scope is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", str(summary.get("source_head", ""))):
        errors.append(f"{label} source_head is invalid")
    if not DIGEST_RE.fullmatch(str(summary.get("generation_digest", ""))):
        errors.append(f"{label} generation digest is invalid")
    if _time(summary.get("observed_at")) is None:
        errors.append(f"{label} observed_at is invalid")
    if summary.get("record_digest") != _self_digest(summary):
        errors.append(f"{label} self-digest is invalid")
    return errors


def _output_errors(output: Any, label: str) -> list[str]:
    if not isinstance(output, dict):
        return [f"{label} summary is missing"]
    errors: list[str] = []
    if set(output) != OUTPUT_FIELDS:
        errors.append(f"{label} summary fields are invalid")
        return errors
    encoding = output.get("encoding")
    preview_text = output.get("preview_text")
    preview_base64 = output.get("preview_base64")
    if encoding == "utf-8" and isinstance(preview_text, str) and preview_base64 is None:
        preview = preview_text.encode("utf-8")
    elif encoding == "base64" and preview_text is None and isinstance(preview_base64, str):
        try:
            preview = base64.b64decode(preview_base64, validate=True)
        except (TypeError, ValueError):
            preview = b""
            errors.append(f"{label} preview is invalid base64")
    else:
        preview = b""
        errors.append(f"{label} preview encoding/channel is invalid")
    source_bytes = output.get("preview_source_bytes")
    if (
        not isinstance(source_bytes, int) or isinstance(source_bytes, bool)
        or not 0 <= source_bytes <= PREVIEW_LIMIT
    ):
        errors.append(f"{label} preview source byte count is invalid")
    total = output.get("bytes")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        errors.append(f"{label} full byte count is invalid")
    if len(preview) > PREVIEW_LIMIT:
        errors.append(f"{label} preview exceeds bound")
    if _redact_preview(preview)[0] != preview:
        errors.append(f"{label} preview contains an unredacted secret")
    if not DIGEST_RE.fullmatch(str(output.get("digest", ""))):
        errors.append(f"{label} full digest is invalid")
    replay_digest = output.get("replay_digest")
    if replay_digest is not None and not DIGEST_RE.fullmatch(str(replay_digest)):
        errors.append(f"{label} replay digest is invalid")
    if output.get("truncated") is not (
        isinstance(total, int) and isinstance(source_bytes, int)
        and total > source_bytes
    ):
        errors.append(f"{label} truncation flag is invalid")
    if not isinstance(output.get("preview_redacted"), bool):
        errors.append(f"{label} preview_redacted is invalid")
    return errors


def _pytest_provider_errors(
    provider: Any,
    *,
    argv: list[str],
    expected_source_head: str | None = None,
) -> list[str]:
    if _is_pytest_argv(argv) and not _is_governed_pytest_argv(argv):
        return ["pytest argv does not use the governed provider isolation profile"]
    governed = _is_governed_pytest_argv(argv)
    if not governed:
        return (
            []
            if provider is None
            else ["non-pytest command cannot bind a pytest provider capsule"]
        )
    if not isinstance(provider, dict):
        return ["governed pytest provider capsule is absent"]
    errors: list[str] = []
    if set(provider) != PYTEST_PROVIDER_FIELDS:
        errors.append("governed pytest provider fields are invalid")
        return errors
    for field, expected in (
        ("schema_version", "governed_pytest_provider_v1"),
        ("profile_id", GOVERNED_PYTEST_PROVIDER_PROFILE_ID),
        (
            "bootstrap_digest",
            _digest_bytes(GOVERNED_PYTEST_BOOTSTRAP.encode("utf-8")),
        ),
        ("source_kind", "CODE_OWNED_GIT_BLOB"),
        ("lock_path", GOVERNED_PYTEST_PROVIDER_LOCK_PATH),
        ("site_import_disabled", True),
        ("candidate_cwd_removed_by_bootstrap", True),
        ("plugin_autoload_disabled", True),
        ("conftest_loading_disabled", True),
        ("project_config_loading_disabled", True),
        ("test_import_path_appended", True),
        ("repository_root_fixed", True),
        ("provider_stable", True),
    ):
        if provider.get(field) != expected:
            errors.append(f"governed pytest provider {field} is invalid")
    for field in ("source_head", "lock_blob"):
        if re.fullmatch(r"[0-9a-f]{40}", str(provider.get(field, ""))) is None:
            errors.append(f"governed pytest provider {field} is invalid")
    if (
        expected_source_head is not None
        and provider.get("source_head") != expected_source_head
    ):
        errors.append(
            "governed pytest provider source head differs from the exact "
            "reviewed repository head"
        )
    if not DIGEST_RE.fullmatch(str(provider.get("lock_sha256", ""))):
        errors.append("governed pytest provider lock_sha256 is invalid")
    try:
        (
            expected_lock,
            expected_distributions,
            expected_wheels,
            _,
        ) = _load_pytest_provider_bundle(str(provider.get("source_head", "")))
    except (
        OSError,
        TypeError,
        ValueError,
        subprocess.CalledProcessError,
    ) as error:
        expected_lock, expected_distributions, expected_wheels = {}, [], []
        errors.append(
            f"governed pytest provider code-owned Git source is invalid: {error}"
        )
    for field, expected in (
        ("lock_path", expected_lock.get("path")),
        ("lock_blob", expected_lock.get("git_blob")),
        ("lock_sha256", expected_lock.get("sha256")),
    ):
        if expected is not None and provider.get(field) != expected:
            errors.append(
                f"governed pytest provider {field} differs from code-owned Git"
            )
    interpreter_path = provider.get("interpreter_path")
    if (
        not isinstance(interpreter_path, str)
        or not Path(interpreter_path).is_absolute()
    ):
        errors.append("governed pytest interpreter path is invalid")
    for field in (
        "interpreter_digest_before",
        "interpreter_digest_after",
        "provider_digest_before",
        "provider_digest_after",
    ):
        if not DIGEST_RE.fullmatch(str(provider.get(field, ""))):
            errors.append(f"governed pytest provider {field} is invalid")
    if provider.get("interpreter_digest_before") != provider.get(
        "interpreter_digest_after"
    ):
        errors.append("governed pytest interpreter changed during execution")
    distributions = provider.get("distribution_manifest")
    required_names = set(PYTEST_PROVIDER_REQUIRED_DISTRIBUTIONS)
    allowed_names = set(PYTEST_PROVIDER_DISTRIBUTIONS)
    distribution_entries_valid = (
        isinstance(distributions, list)
        and all(
            isinstance(item, dict)
            and set(item) == {"name", "version"}
            and isinstance(item.get("name"), str)
            and bool(item["name"])
            and isinstance(item.get("version"), str)
            and bool(item["version"])
            for item in distributions
        )
    )
    observed_names = (
        [item["name"] for item in distributions]
        if distribution_entries_valid
        else []
    )
    if (
        not distribution_entries_valid
        or observed_names
        != sorted(observed_names, key=lambda name: name.lower())
        or not required_names <= set(observed_names) <= allowed_names
        or len(observed_names) != len(set(observed_names))
    ):
        errors.append(
            "governed pytest provider distribution manifest is invalid"
        )
        distributions = []
    elif distributions != expected_distributions:
        errors.append(
            "governed pytest provider distributions differ from code-owned lock"
        )
    wheels = provider.get("wheel_manifest")
    if (
        not isinstance(wheels, list)
        or any(
            not isinstance(item, dict)
            or set(item) != PYTEST_PROVIDER_WHEEL_IDENTITY_FIELDS
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("version"), str)
            or not isinstance(item.get("path"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", str(item.get("git_blob", "")))
            or not isinstance(item.get("bytes"), int)
            or isinstance(item.get("bytes"), bool)
            or item["bytes"] < 1
            or not DIGEST_RE.fullmatch(str(item.get("sha256", "")))
            for item in wheels
        )
    ):
        errors.append("governed pytest provider wheel manifest is invalid")
        wheels = []
    elif wheels != expected_wheels:
        errors.append(
            "governed pytest provider wheels differ from code-owned Git"
        )
    files = provider.get("file_manifest")
    if not isinstance(files, list) or not files:
        errors.append("governed pytest provider file manifest is empty")
        files = []
    else:
        observed_paths: list[str] = []
        for item in files:
            if (
                not isinstance(item, dict)
                or set(item) != {"path", "bytes", "sha256"}
                or not isinstance(item.get("path"), str)
                or not item["path"]
                or item["path"].startswith("/")
                or ".." in Path(item["path"]).parts
                or not isinstance(item.get("bytes"), int)
                or isinstance(item.get("bytes"), bool)
                or item["bytes"] < 0
                or not DIGEST_RE.fullmatch(str(item.get("sha256", "")))
            ):
                errors.append("governed pytest provider file entry is invalid")
                continue
            observed_paths.append(item["path"])
        if observed_paths != sorted(set(observed_paths)):
            errors.append(
                "governed pytest provider file manifest is not canonical"
            )
    expected_provider_digest = _pytest_provider_digest(
        distributions,
        wheels,
        files,
        source_head=str(provider.get("source_head", "")),
        lock_blob=str(provider.get("lock_blob", "")),
        lock_sha256=str(provider.get("lock_sha256", "")),
    )
    if provider.get("provider_digest_before") != expected_provider_digest:
        errors.append("governed pytest provider digest does not re-derive")
    if provider.get("provider_digest_after") != expected_provider_digest:
        errors.append("governed pytest provider changed during execution")
    return sorted(set(errors))


def validate_governed_command_capture(
    record: Any,
    *,
    expected_context_artifact_digest: str | None = None,
    expected_task_contract_digest: str | None = None,
    expected_execution_task: dict[str, Any] | None = None,
    expected_path_scope: list[str] | None = None,
    expected_source_head: str | None = None,
    root: Path = REPO_ROOT,
    reexecute: bool = False,
) -> list[str]:
    """Validate v2 binding, compact outputs, generations, and optional replay."""

    if not isinstance(record, dict):
        return ["governed command capture must be an object"]
    errors: list[str] = []
    if frozenset(record) not in {
        frozenset(RECORD_FIELDS),
        frozenset(LEGACY_RECORD_FIELDS),
    }:
        errors.append("governed command capture fields do not match contract")
    if record.get("schema_version") != "command_capture_v2":
        errors.append("governed command capture schema_version is invalid")
    if record.get("trust_tier") != LOCAL_REPRODUCIBLE:
        errors.append("governed command capture trust tier is invalid")
    if record.get("effect_enforcement") != "repository_policy_only":
        errors.append("governed command effect enforcement boundary is invalid")
    if record.get("host_sandbox_attestation_ref") is not None:
        errors.append("governed command cannot self-assert a host sandbox attestation")
    execution_task = record.get("execution_task")
    if not isinstance(execution_task, dict) or set(execution_task) != EXECUTION_TASK_FIELDS:
        errors.append("governed command execution task is invalid")
        execution_task = {}
    if record.get("execution_task_digest") != canonical_digest(execution_task):
        errors.append("governed command execution task digest is invalid")
    if expected_execution_task is not None and execution_task != expected_execution_task:
        errors.append("governed command execution task differs from dispatch")
    for record_field, task_field in (
        ("node_id", "node_id"), ("role_id", "role"),
        ("native_agent", "native_agent"), ("node_class", "node_class"),
        ("permission", "permission"),
    ):
        if record.get(record_field) != execution_task.get(task_field):
            errors.append(f"governed command {record_field} differs from execution task")
    path_scope = record.get("path_scope")
    if not isinstance(path_scope, list) or not path_scope or path_scope != sorted(set(path_scope)):
        errors.append("governed command path_scope is invalid")
        path_scope = []
    if expected_path_scope is not None and path_scope != sorted(expected_path_scope):
        errors.append("governed command path_scope differs from dispatch-derived scope")
    for field, expected in (
        ("context_artifact_digest", expected_context_artifact_digest),
        ("task_contract_digest", expected_task_contract_digest),
    ):
        if not DIGEST_RE.fullmatch(str(record.get(field, ""))):
            errors.append(f"governed command {field} is invalid")
        if expected is not None and record.get(field) != expected:
            errors.append(f"governed command {field} differs from expected Context")
    try:
        argv, command = command_argv(record.get("argv"))
        if record.get("command") != command:
            errors.append("governed command string differs from argv")
    except ValueError as error:
        argv, command = [], ""
        errors.append(f"governed command argv is invalid: {error}")
    provider_expected_source_head = None
    try:
        if Path(root).resolve() == Path(__file__).resolve().parents[2]:
            whole_before = record.get("whole_repository_before")
            if isinstance(whole_before, dict):
                provider_expected_source_head = whole_before.get(
                    "source_head"
                )
    except OSError:
        pass
    errors.extend(_pytest_provider_errors(
        record.get("pytest_provider"),
        argv=argv,
        expected_source_head=provider_expected_source_head,
    ))
    authorization = record.get("authorization")
    expected_authorization = authorize_native_command(str(record.get("native_agent", "")), command)
    if authorization != expected_authorization:
        errors.append("governed command authorization differs from exact native policy")
    if not isinstance(authorization, dict) or authorization.get("policy_class") not in LOCAL_POLICY_CLASSES:
        errors.append("governed command is not an authorized local read/test command")
    if record.get("replay_contract") != replay_contract_for(
        argv, authorization.get("policy_class") if isinstance(authorization, dict) else None
    ):
        errors.append("governed command replay contract is invalid")
    timeout = record.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 900:
        errors.append("governed command timeout is invalid")
    started, completed = _time(record.get("started_at")), _time(record.get("completed_at"))
    if started is None or completed is None or completed < started:
        errors.append("governed command interval is invalid")
    exit_code, timed_out = record.get("exit_code"), record.get("timed_out")
    expected_result = (
        "TIMED_OUT" if timed_out is True else "PASS" if exit_code == 0 else "FAIL"
    )
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        errors.append("governed command exit_code is invalid")
    if not isinstance(timed_out, bool) or record.get("result") != expected_result:
        errors.append("governed command result/timed_out is invalid")
    errors.extend(_output_errors(record.get("stdout"), "governed command stdout"))
    errors.extend(_output_errors(record.get("stderr"), "governed command stderr"))
    for field, scope in (
        ("repository_before", path_scope), ("repository_after", path_scope),
        ("whole_repository_before", ["."]), ("whole_repository_after", ["."]),
    ):
        errors.extend(_generation_errors(record.get(field), expected_scope=scope, label=field))
        summary = record.get(field)
        if (
            expected_source_head is not None and isinstance(summary, dict)
            and summary.get("source_head") != expected_source_head
        ):
            errors.append(f"{field} source_head differs from admitted baseline")
    if isinstance(record.get("repository_before"), dict) and isinstance(record.get("repository_after"), dict) and record["repository_before"].get("generation_digest") != record["repository_after"].get("generation_digest"):
        errors.append("governed command mutated task-scoped repository generation")
    if isinstance(record.get("whole_repository_before"), dict) and isinstance(record.get("whole_repository_after"), dict) and record["whole_repository_before"].get("generation_digest") != record["whole_repository_after"].get("generation_digest"):
        errors.append("governed command mutated whole-repository generation")
    if record.get("record_digest") != _self_digest(record):
        errors.append("governed command capture self-digest is invalid")
    if reexecute and not errors:
        errors.extend(_replay_errors(record, root=Path(root)))
    return errors


def _replay_errors(record: dict[str, Any], *, root: Path) -> list[str]:
    path_scope = record["path_scope"]
    current_task = _generation_summary(path_scope, root)
    current_whole = _generation_summary(["."], root)
    if current_task["generation_digest"] != record["repository_after"]["generation_digest"]:
        return ["governed command task generation is stale before replay"]
    if current_whole["generation_digest"] != record["whole_repository_after"]["generation_digest"]:
        return ["governed command whole-repository generation is stale before replay"]
    replay = _execute(
        record["argv"], root=root, timeout_seconds=record["timeout_seconds"],
        replay_contract=record["replay_contract"],
        provider_source_head=(
            record.get("pytest_provider", {}).get("source_head")
            if isinstance(record.get("pytest_provider"), dict)
            else None
        ),
    )
    errors: list[str] = []
    if replay["pytest_provider"] != record.get("pytest_provider"):
        errors.append("governed pytest provider does not reproduce")
    if any(replay[field] != record[field] for field in ("exit_code", "timed_out", "result")):
        errors.append("governed command result does not reproduce")
    for stream in ("stdout", "stderr"):
        expected, actual = record[stream], replay[stream]
        if record["replay_contract"] == EXACT_OUTPUT:
            if (actual["bytes"], actual["digest"]) != (expected["bytes"], expected["digest"]):
                errors.append(f"governed command {stream} exact output does not reproduce")
        elif record["replay_contract"] == CANONICAL_TEST_OUTPUT_V1 and actual["replay_digest"] != expected["replay_digest"]:
            errors.append(f"governed command {stream} canonical output does not reproduce")
    after_task = _generation_summary(path_scope, root)
    after_whole = _generation_summary(["."], root)
    if after_task["generation_digest"] != current_task["generation_digest"]:
        errors.append("governed command replay mutated task-scoped generation")
    if after_whole["generation_digest"] != current_whole["generation_digest"]:
        errors.append("governed command replay mutated whole-repository generation")
    return errors
