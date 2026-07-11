"""Content-addressed Context compiler primitives for Development-Agent governance."""

from __future__ import annotations

import base64
import json
import re
import subprocess
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_governance_external_evidence import (
    ExternalEvidenceVerifier,
    validate_external_evidence_capture,
)

from agent_governance_registry import REPO_ROOT
from agent_governance_context_specs import source_name
from agent_governance_routing import TASK_CONTRACT_FIELDS, _sha256_bytes
from agent_governance_schema import schema_subset_errors


CONTEXT_EVIDENCE_SCHEMA_PATH = REPO_ROOT / ".codex/schemas/context_evidence_artifact_v1.schema.json"
TRUSTED_DERIVED_SOURCES = {
    "current diff": "diff_snapshot",
    "direct interfaces": "interface_inventory",
    "direct callers": "caller_inventory",
    "focused acceptance tests": "test_inventory",
}
MAX_INLINE_MATCHES = 64
MAX_INLINE_DIFF_BYTES = 64 * 1024


@lru_cache(maxsize=1)
def _context_evidence_schema() -> dict[str, Any]:
    return json.loads(CONTEXT_EVIDENCE_SCHEMA_PATH.read_text(encoding="utf-8"))


def _estimate_tokens(value: Any) -> int:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return max(1, (len(encoded) + 3) // 4)


def _select_envelope(task_facts: dict[str, Any]) -> str:
    risk = str(task_facts.get("risk", "unknown")).lower()
    uncertainty = str(task_facts["uncertainty"]).lower()
    surfaces = {str(value).lower() for value in task_facts.get("surfaces", [])}
    if "profit_diagnosis" in surfaces:
        return "profit_diagnosis"
    if (
        risk not in {"low", "medium", "high", "critical"}
        or uncertainty == "unknown"
        or "full_audit" in surfaces
    ):
        return "full_audit"
    if risk in {"high", "critical"} or uncertainty == "high" or surfaces & {
        "authority", "live", "risk", "cross_interface"
    }:
        return "complex"
    return "narrow" if risk == "low" and uncertainty == "low" else "standard"


def _git_bytes(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True
    ).stdout


def _safe_artifact(path_value: Any, root: Path) -> tuple[Path | None, str | None]:
    if (
        not isinstance(path_value, str)
        or not path_value.strip()
        or path_value.startswith("~")
    ):
        return None, "artifact_path must be a non-empty repository-relative path"
    relative = Path(path_value)
    sensitive = {
        ".ssh", ".aws", ".gnupg", ".git", ".env", ".netrc", "credentials",
        "credentials.json", "id_rsa", "id_ed25519",
    }
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or sensitive.intersection(part.lower() for part in relative.parts)
    ):
        return None, "artifact_path escapes the repository or targets a sensitive directory"
    root_resolved, cursor = root.resolve(), root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return None, "artifact_path may not traverse a symlink"
    try:
        resolved = (root / relative).resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (FileNotFoundError, RuntimeError, ValueError):
        return None, "artifact_path is missing or outside the repository"
    if not resolved.is_file():
        return None, "artifact_path must resolve to a regular file"
    return resolved, None


def _untracked_manifest_bytes(root: Path) -> bytes:
    paths = [
        item.decode("utf-8", errors="surrogateescape")
        for item in _git_bytes(
            root, "ls-files", "--others", "--exclude-standard", "-z"
        ).split(b"\0")
        if item
    ]
    manifest: list[dict[str, Any]] = []
    for raw_path in sorted(paths):
        candidate, error = _safe_artifact(raw_path, root)
        if candidate is None:
            manifest.append({"path": raw_path, "status": "unsafe", "error": error})
        else:
            data = candidate.read_bytes()
            manifest.append(
                {"path": raw_path, "bytes": len(data), "digest": _sha256_bytes(data)}
            )
    return json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def capture_repository_baseline(root: Path = REPO_ROOT) -> dict[str, str]:
    """Capture the exact Git generation consumed by Context and Closure."""

    root = root.resolve()
    try:
        source_head = _git_bytes(root, "rev-parse", "HEAD").decode("ascii").strip().lower()
        dirty_diff = _git_bytes(root, "diff", "--no-ext-diff", "--binary", "HEAD", "--")
        untracked_manifest = _untracked_manifest_bytes(root)
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise ValueError(f"cannot capture repository baseline: {error}") from error
    if not re.fullmatch(r"[0-9a-f]{40}", source_head):
        raise ValueError("captured repository HEAD is not exact 40-hex")
    return {
        "source_head": source_head,
        "dirty_diff_hash": _sha256_bytes(dirty_diff),
        "untracked_relevant_hash": _sha256_bytes(untracked_manifest),
    }


def _task_contract(normalized_facts: dict[str, Any]) -> dict[str, Any]:
    return {field: normalized_facts.get(field) for field in TASK_CONTRACT_FIELDS}


def _capture_times(capture_kind: str) -> tuple[str, str]:
    observed = datetime.now().astimezone()
    ttl = {
        "runtime_observation": timedelta(minutes=15),
        "diff_snapshot": timedelta(hours=1),
        "interface_inventory": timedelta(hours=1),
        "caller_inventory": timedelta(hours=1),
        "test_inventory": timedelta(hours=1),
        "repository_inventory": timedelta(hours=1),
        "external_policy_snapshot": timedelta(days=30),
    }.get(capture_kind, timedelta(hours=4))
    return observed.isoformat(), (observed + ttl).isoformat()


def _inline_content(data: bytes) -> tuple[str, str]:
    try:
        return "utf-8", data.decode("utf-8")
    except UnicodeDecodeError:
        return "base64", base64.b64encode(data).decode("ascii")


def _selected_markdown_bytes(data: bytes, selector: str) -> bytes | None:
    if not selector:
        return data
    try:
        lines = data.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None
    target, start, level = selector.strip().casefold(), None, 7
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match and target in match.group(2).casefold():
            start, level = index, len(match.group(1))
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = re.match(r"^(#{1,6})\s+", lines[index])
        if match and len(match.group(1)) <= level:
            end = index
            break
    return "".join(lines[start:end]).encode("utf-8")


def _baseline_errors(supplied: Any, actual: dict[str, str] | None) -> list[str]:
    required = {"source_head", "dirty_diff_hash", "untracked_relevant_hash"}
    if not isinstance(supplied, dict) or set(supplied) != required:
        return ["task baseline must contain exact source_head/dirty_diff_hash/untracked_relevant_hash"]
    if actual is None:
        return ["task baseline cannot be reconciled without a Git producer"]
    return [] if supplied == actual else ["task baseline does not match current repository generation"]


def _scan_interface_matches(root: Path, interfaces: list[str]) -> list[dict[str, Any]]:
    if not interfaces:
        return []
    # Let Git search its indexed + untracked, non-ignored source inventory in C.
    # This preserves the complete caller inventory while avoiding a Python
    # open/read/Unicode pass over every repository file on every Context compile.
    command = ["git", "grep", "--untracked", "-n", "-I", "-F"]
    for interface in interfaces:
        command.extend(("-e", interface))
    command.append("--")
    try:
        completed = subprocess.run(
            command, cwd=root, check=False, capture_output=True
        )
    except OSError:
        return []
    if completed.returncode not in {0, 1}:
        return []
    matches: list[dict[str, Any]] = []
    for raw_line in completed.stdout.splitlines():
        decoded = raw_line.decode("utf-8", errors="surrogateescape")
        parts = decoded.split(":", 2)
        if len(parts) != 3:
            continue
        path, raw_number, line = parts
        try:
            line_number = int(raw_number)
        except ValueError:
            continue
        matches.append({"path": path, "line": line_number, "text": line})
    return matches


def _bounded_match_inventory(
    matches: list[dict[str, Any]], *, limit: int = MAX_INLINE_MATCHES,
) -> dict[str, Any]:
    """Authenticate a complete match set while exposing only a bounded preview."""

    manifest_raw = json.dumps(
        matches, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {
        "match_count": len(matches),
        "manifest_digest": _sha256_bytes(manifest_raw),
        "manifest_bytes": len(manifest_raw),
        "matches": matches[:limit],
        "truncated": len(matches) > limit,
        "retrieval": "open task-relevant paths from the repository on demand",
    }


def _trusted_derived_record(
    source: str, *, root: Path, normalized_facts: dict[str, Any],
    actual_baseline: dict[str, str] | None,
) -> dict[str, Any]:
    capture_kind = TRUSTED_DERIVED_SOURCES[source]
    interfaces = [str(item) for item in normalized_facts.get("direct_interfaces", [])]
    if source == "current diff":
        if actual_baseline is None:
            return {"source": source, "status": "trusted_producer_unavailable", "digest": None, "planned_tokens": 32}
        raw_scope = normalized_facts.get("dirty_scope")
        scope_paths = []
        for value in raw_scope if isinstance(raw_scope, list) else []:
            if not isinstance(value, str) or not value.strip():
                continue
            relative = Path(value.strip())
            if relative.is_absolute() or ".." in relative.parts or value.startswith("~"):
                continue
            scope_paths.append(relative.as_posix())
        # The repository baseline already binds the complete dirty generation.
        # Role context must expose only the task-owned dirty scope; otherwise a
        # large unrelated worktree consumes the reviewer's quality reserve and
        # leaks ambient work into an otherwise exact dispatch.
        tracked_dirty = sorted(
            item.decode("utf-8", errors="surrogateescape")
            for item in _git_bytes(
                root, "diff", "--name-only", "-z", "HEAD", "--", *scope_paths
            ).split(b"\0")
            if item
        )
        scoped_untracked = sorted(
            item.decode("utf-8", errors="surrogateescape")
            for item in _git_bytes(
                root, "ls-files", "--others", "--exclude-standard", "-z",
                "--", *scope_paths,
            ).split(b"\0")
            if item
        )
        dirty_manifest = [
            *({"path": path, "status": "tracked"} for path in tracked_dirty),
            *({"path": path, "status": "untracked"} for path in scoped_untracked),
        ]
        diff_args = ["diff", "--no-ext-diff", "--binary", "HEAD", "--", *scope_paths]
        tracked = _git_bytes(root, *diff_args)
        untracked_args = [
            "ls-files", "--others", "--exclude-standard", "-z", "--", *scope_paths,
        ]
        untracked_paths = sorted(
            item.decode("utf-8", errors="strict")
            for item in _git_bytes(root, *untracked_args).split(b"\0")
            if item
        )
        untracked, withheld = [], []
        for relative_path in untracked_paths:
            path, path_error = _safe_artifact(relative_path, root)
            if path is None:
                withheld.append({"path": relative_path, "reason": path_error})
                continue
            data = path.read_bytes()
            if len(data) > 2_000_000:
                withheld.append(
                    {
                        "path": relative_path,
                        "reason": "untracked file exceeds inline Context size limit",
                        "bytes": len(data),
                        "content_digest": _sha256_bytes(data),
                    }
                )
                continue
            item_encoding, item_content = _inline_content(data)
            untracked.append(
                {
                    "path": relative_path,
                    "content_encoding": item_encoding,
                    "content": item_content,
                    "content_digest": _sha256_bytes(data),
                }
            )
        content = {
            "scope_paths": scope_paths,
            "dirty_manifest": dirty_manifest,
            "tracked_diff_encoding": (
                _inline_content(tracked)[0] if len(tracked) <= MAX_INLINE_DIFF_BYTES else None
            ),
            "tracked_diff": (
                _inline_content(tracked)[1] if len(tracked) <= MAX_INLINE_DIFF_BYTES else None
            ),
            "tracked_diff_digest": _sha256_bytes(tracked),
            "untracked": untracked,
            "withheld": withheld,
        }
        if len(tracked) > MAX_INLINE_DIFF_BYTES:
            withheld.append(
                {
                    "path": "<tracked scoped diff>",
                        "reason": "tracked diff exceeds bounded inline Context preview",
                    "bytes": len(tracked),
                    "content_digest": _sha256_bytes(tracked),
                }
            )
        encoding = "json"
        raw = json.dumps(
            content, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    elif source == "direct interfaces":
        content, encoding = {"interfaces": interfaces}, "json"
        raw = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    else:
        matches = _scan_interface_matches(root, interfaces)
        if source == "direct callers":
            content = {
                "interfaces": interfaces,
                **_bounded_match_inventory(matches),
            }
        else:
            test_matches = [
                item for item in matches
                if "test" in Path(item["path"]).name.lower()
                or "tests" in Path(item["path"]).parts
            ]
            content = {
                "acceptance_criteria": normalized_facts.get("acceptance_criteria", []),
                **_bounded_match_inventory(test_matches),
            }
        encoding = "json"
        raw = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    observed_at, expires_at = _capture_times(capture_kind)
    tokens = max(1, (len(raw) + 3) // 4)
    return {
        "source": source, "selector": None,
        "status": "trusted_producer",
        "capture_kind": capture_kind, "producer": "agent_governance_context_producer_v1",
        "baseline": actual_baseline, "observed_at": observed_at, "expires_at": expires_at,
        "content_encoding": encoding, "content": content, "digest": _sha256_bytes(raw),
        "content_digest": _sha256_bytes(raw), "bytes": len(raw),
        "full_file_token_estimate": tokens, "planned_tokens": tokens,
    }


def _repository_inventory_record(
    spec: dict[str, Any], *, root: Path,
    actual_baseline: dict[str, str] | None,
    normalized_facts: dict[str, Any],
) -> dict[str, Any]:
    """Capture an exact manifest digest plus a bounded task-scoped projection."""

    source = source_name(spec)
    try:
        raw_paths = _git_bytes(
            root, "ls-files", "--cached", "--others", "--exclude-standard",
            "-z", "--", *spec["paths"],
        ).split(b"\0")
    except (OSError, subprocess.CalledProcessError):
        raw_paths = []
    matches: list[dict[str, Any]] = []
    for raw_path in sorted({item for item in raw_paths if item}):
        relative = raw_path.decode("utf-8", errors="surrogateescape")
        path, error = _safe_artifact(relative, root)
        if path is None:
            continue
        data = path.read_bytes()
        matches.append(
            {"path": relative, "bytes": len(data), "digest": _sha256_bytes(data)}
        )
    manifest_raw = json.dumps(
        matches, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    raw_scope = normalized_facts.get("dirty_scope", [])
    scope = [
        str(value).strip().rstrip("/")
        for value in raw_scope if isinstance(value, str) and value.strip()
    ]
    relevant = [
        item for item in matches
        if any(
            item["path"] == prefix or item["path"].startswith(prefix + "/")
            for prefix in scope
        )
    ][:MAX_INLINE_MATCHES]
    content = {
        "patterns": spec["paths"],
        "match_count": len(matches),
        "total_bytes": sum(item["bytes"] for item in matches),
        "manifest_digest": _sha256_bytes(manifest_raw),
        "manifest_bytes": len(manifest_raw),
        "task_scope_matches": relevant,
        "task_scope_truncated": len(relevant) == MAX_INLINE_MATCHES,
        "retrieval": "open a manifest path from the repository on demand",
    }
    raw = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    observed_at, expires_at = _capture_times("repository_inventory")
    tokens = max(1, (len(raw) + 3) // 4)
    return {
        "source": source, "selector": None,
        "status": (
            "trusted_producer" if len(matches) >= spec["min_matches"]
            else "trusted_producer_unavailable"
        ),
        "capture_kind": "repository_inventory",
        "producer": "agent_governance_context_producer_v1",
        "baseline": actual_baseline,
        "observed_at": observed_at, "expires_at": expires_at,
        "content_encoding": "json", "content": content,
        "digest": _sha256_bytes(raw), "content_digest": _sha256_bytes(raw),
        "bytes": len(raw), "full_file_token_estimate": tokens,
        "inventory_manifest_token_estimate": max(1, (len(manifest_raw) + 3) // 4),
        "planned_tokens": tokens,
    }


def _valid_observed_at(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def _expected_capture_kind(source: str, declared: str | None = None) -> str:
    if declared is not None:
        return declared
    normalized = source.lower()
    if normalized == "current diff":
        return "diff_snapshot"
    if normalized == "direct interfaces":
        return "interface_inventory"
    if normalized == "direct callers":
        return "caller_inventory"
    if normalized == "focused acceptance tests":
        return "test_inventory"
    if "official " in normalized:
        return "external_policy_snapshot"
    if any(token in normalized for token in ("runtime", "service", "pg", "artifact")):
        return "runtime_observation"
    return "source_snapshot"


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _source_provenance_record(
    source_spec: str | dict[str, Any], root: Path, evidence_state: dict[str, Any],
    normalized_facts: dict[str, Any], actual_baseline: dict[str, str] | None,
    external_evidence_verifier: ExternalEvidenceVerifier | None = None,
) -> dict[str, Any]:
    source = source_name(source_spec)
    spec_kind = source_spec.get("kind") if isinstance(source_spec, dict) else None
    if spec_kind == "repository_inventory":
        if evidence_state.get(source) is not None:
            return {
                "source": source, "selector": None,
                "status": "trusted_producer_override_rejected", "digest": None,
                "planned_tokens": 32,
                "artifact_error": "repository inventory is locally produced and cannot be caller-supplied",
            }
        return _repository_inventory_record(
            source_spec, root=root, actual_baseline=actual_baseline,
            normalized_facts=normalized_facts,
        )
    raw_path, _, selector = source.partition("#")
    candidate = root / raw_path
    record: dict[str, Any] = {"source": source, "selector": selector or None}
    supplied = evidence_state.get(source)
    if source in TRUSTED_DERIVED_SOURCES:
        if supplied is not None:
            return {
                **record, "status": "trusted_producer_override_rejected", "digest": None,
                "planned_tokens": 32,
                "artifact_error": "derived context is produced in-process and cannot be replaced by caller evidence_state",
            }
        return _trusted_derived_record(
            source, root=root, normalized_facts=normalized_facts,
            actual_baseline=actual_baseline,
        )
    if spec_kind != "evidence_artifact" and candidate.is_file():
        local_file, local_error = _safe_artifact(raw_path, root)
        if local_file is None:
            return {
                **record, "status": "unsafe_local_source", "digest": None,
                "planned_tokens": 32, "artifact_error": local_error,
            }
        data = local_file.read_bytes()
        selected = _selected_markdown_bytes(data, selector)
        if selected is None:
            return {
                **record, "status": "selector_missing_or_non_text",
                "digest": _sha256_bytes(data), "planned_tokens": 32,
            }
        actual_digest, content_digest = _sha256_bytes(data), _sha256_bytes(selected)
        encoding, content = _inline_content(selected)
        full_estimate = max(1, (len(data) + 3) // 4)
        planned_tokens = max(1, (len(selected) + 3) // 4)
        observed_at, expires_at = _capture_times("source_snapshot")
        record.update(
            status="pinned", digest=actual_digest, content_digest=content_digest,
            content_encoding=encoding, content=content, capture_kind="source_snapshot",
            producer="repository_bytes_v1", baseline=actual_baseline,
            observed_at=observed_at, expires_at=expires_at, bytes=len(selected),
            source_bytes=len(data), full_file_token_estimate=full_estimate,
            planned_tokens=planned_tokens,
        )
        if supplied is None:
            return record
        if not isinstance(supplied, dict) or set(supplied) - {"digest", "observed_at", "planned_tokens"}:
            record.update(
                status="invalid_local_assertion",
                asserted_digest=supplied.get("digest") if isinstance(supplied, dict) else None,
            )
        else:
            record["asserted_digest"] = supplied.get("digest")
            record["asserted_observed_at"] = supplied.get("observed_at")
            if supplied.get("digest") != actual_digest:
                record["status"] = "local_digest_mismatch"
            elif supplied.get("observed_at") is not None and not _valid_observed_at(supplied["observed_at"]):
                record["status"] = "invalid_local_assertion"
            else:
                record["status"] = "pinned_verified"
        return record

    virtual = any(
        token in raw_path
        for token in ("*", "relevant ", "current ", "official ", "direct ", "focused ", "when available")
    ) or " " in raw_path
    if not virtual:
        return {**record, "status": "local_missing", "digest": None, "planned_tokens": 32}
    if supplied is None:
        return {**record, "status": "resolve_on_demand", "digest": None, "planned_tokens": 32}
    if not isinstance(supplied, dict) or set(supplied) - {"artifact_path", "digest"}:
        return {**record, "status": "unbacked_evidence_state", "digest": None, "planned_tokens": 32}
    artifact, path_error = _safe_artifact(supplied.get("artifact_path"), root)
    if artifact is None:
        return {
            **record, "status": "unbacked_evidence_state", "digest": None,
            "planned_tokens": 32, "artifact_error": path_error,
        }
    data, artifact_errors = artifact.read_bytes(), []
    actual_digest = _sha256_bytes(data)
    try:
        payload = json.loads(
            data, object_pairs_hook=_strict_json_object, parse_constant=_reject_json_constant
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        payload = None
    expected_kind = _expected_capture_kind(
        source,
        source_spec.get("capture_kind") if isinstance(source_spec, dict) else None,
    )
    if (
        expected_kind == "external_policy_snapshot"
        and isinstance(payload, dict)
        and payload.get("schema_version") == "external_evidence_capture_v1"
    ):
        capture_errors = validate_external_evidence_capture(
            payload, verifier=external_evidence_verifier,
            adjudicated_at=datetime.now().astimezone(),
        )
        unattested = (
            "external evidence capture lacks out-of-band host verification"
            in capture_errors
        )
        freshness_debt = "external evidence capture is stale at adjudication" in capture_errors
        structural_errors = [
            error for error in capture_errors
            if error not in {
                "external evidence capture lacks out-of-band host verification",
                "external evidence capture is stale at adjudication",
            }
        ]
        content_bytes = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        full_estimate = max(1, (len(content_bytes) + 3) // 4)
        record.update(
            selector=payload.get("selector"),
            status=(
                "invalid_context_artifact" if structural_errors
                else "stale_context_artifact" if freshness_debt
                else "available_unattested_evidence" if unattested
                else "resolved_artifact"
            ),
            artifact_path=str(artifact.relative_to(root.resolve())),
            digest=actual_digest,
            content_digest=_sha256_bytes(content_bytes),
            content_encoding="json", content=payload,
            capture_kind="external_policy_snapshot",
            producer={
                "id": "external_policy_capture_adapter_v1",
                "input_digest": payload.get("record_digest"),
            },
            baseline=actual_baseline, bytes=len(content_bytes), artifact_bytes=len(data),
            full_file_token_estimate=full_estimate, planned_tokens=full_estimate,
            observed_at=payload.get("observed_at"), expires_at=payload.get("expires_at"),
        )
        if structural_errors:
            record["artifact_errors"] = structural_errors
        if unattested:
            record["attestation_error"] = (
                "external capture integrity is present but host verification is unavailable"
            )
        if supplied.get("digest") is not None:
            record["asserted_digest"] = supplied["digest"]
            if supplied["digest"] != actual_digest:
                record["status"] = "artifact_digest_mismatch"
        return record
    artifact_schema = _context_evidence_schema()
    artifact_errors.extend(schema_subset_errors(payload, artifact_schema, artifact_schema))
    content_bytes, stale = b"", False
    if isinstance(payload, dict):
        if payload.get("logical_source") != source:
            artifact_errors.append("logical_source does not match requested context source")
        expected_kind = _expected_capture_kind(
            source,
            source_spec.get("capture_kind")
            if isinstance(source_spec, dict) else None,
        )
        if payload.get("capture_kind") != expected_kind:
            artifact_errors.append(f"capture_kind must be {expected_kind} for requested context source")
        content_bytes = json.dumps(
            payload.get("content"), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        if payload.get("content_digest") != _sha256_bytes(content_bytes):
            artifact_errors.append("content_digest does not match canonical content")
        if payload.get("baseline") != actual_baseline:
            artifact_errors.append("artifact baseline does not match current repository generation")
        producer_id = payload.get("producer", {}).get("id") if isinstance(payload.get("producer"), dict) else None
        required_producer = {
            "runtime_observation": "runtime_observation_adapter_v1",
            "external_policy_snapshot": "external_policy_capture_adapter_v1",
            "source_snapshot": "repository_snapshot_adapter_v1",
        }.get(expected_kind)
        if producer_id != required_producer:
            artifact_errors.append(f"capture_kind {expected_kind} requires producer {required_producer}")
        try:
            observed = datetime.fromisoformat(str(payload.get("observed_at", "")).replace("Z", "+00:00"))
            expiry = datetime.fromisoformat(str(payload.get("expires_at", "")).replace("Z", "+00:00"))
            now = datetime.now().astimezone()
            max_ttl = {
                "runtime_observation": timedelta(minutes=15),
                "external_policy_snapshot": timedelta(days=30),
                "source_snapshot": timedelta(hours=4),
            }.get(expected_kind, timedelta(hours=1))
            if observed.tzinfo is None or expiry.tzinfo is None or not observed < expiry:
                raise ValueError("invalid artifact time interval")
            if expiry - observed > max_ttl:
                artifact_errors.append(f"{expected_kind} artifact exceeds maximum freshness TTL")
            stale = not (observed <= now < expiry)
        except (TypeError, ValueError):
            artifact_errors.append("artifact observed_at/expires_at interval is invalid")
    full_estimate = max(1, (len(content_bytes) + 3) // 4)
    record.update(
        status=(
            "invalid_context_artifact" if artifact_errors
            else "stale_context_artifact" if stale
            else "available_unattested_evidence"
        ),
        artifact_path=str(artifact.relative_to(root.resolve())), digest=actual_digest,
        content_digest=payload.get("content_digest") if isinstance(payload, dict) else None,
        content_encoding="json", content=payload.get("content") if isinstance(payload, dict) else None,
        capture_kind=payload.get("capture_kind") if isinstance(payload, dict) else None,
        producer=payload.get("producer") if isinstance(payload, dict) else None,
        baseline=payload.get("baseline") if isinstance(payload, dict) else None,
        bytes=len(content_bytes), artifact_bytes=len(data),
        full_file_token_estimate=full_estimate, planned_tokens=full_estimate,
        observed_at=payload.get("observed_at") if isinstance(payload, dict) else None,
        expires_at=payload.get("expires_at") if isinstance(payload, dict) else None,
    )
    if not artifact_errors and not stale:
        record["attestation_error"] = (
            "repo-local producer metadata proves integrity only; an out-of-band host capability attestation is required for verdict evidence"
        )
    if artifact_errors:
        record["artifact_errors"] = artifact_errors
    if supplied.get("digest") is not None:
        record["asserted_digest"] = supplied["digest"]
        if supplied["digest"] != actual_digest:
            record["status"] = "artifact_digest_mismatch"
    return record


def _source_provenance(
    source_spec: str | dict[str, Any], root: Path, evidence_state: dict[str, Any],
    normalized_facts: dict[str, Any], actual_baseline: dict[str, str] | None,
    external_evidence_verifier: ExternalEvidenceVerifier | None = None,
) -> dict[str, Any]:
    """Attach the call-vs-verdict requirement class to every source record."""

    record = _source_provenance_record(
        source_spec, root, evidence_state, normalized_facts, actual_baseline,
        external_evidence_verifier,
    )
    verdict_evidence = (
        isinstance(source_spec, dict)
        and source_spec.get("kind") == "evidence_artifact"
    )
    record["requirement_class"] = (
        "verdict_evidence" if verdict_evidence else "call_context"
    )
    if verdict_evidence:
        record.setdefault("capture_kind", source_spec.get("capture_kind"))
        record.setdefault("baseline", actual_baseline)
    return record
