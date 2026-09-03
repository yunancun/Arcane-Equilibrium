"""Deterministic, source-limited execution-surface truth reporting."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from agent_governance_schema import schema_subset_errors


_TYPED_CONFIG_KEYS = {
    "agents.enabled",
    "agents.max_concurrent_threads_per_session",
    "agents.default_subagent_model",
    "agents.default_subagent_reasoning_effort",
    "agents.interrupt_message",
}
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REPO_ROOT = Path(__file__).resolve().parents[2]
EXECUTION_SURFACE_PROBE_MAX_REQUEST_BYTES = 64 * 1024
ExecutionSurfaceHostVerifier = Callable[[str, str, dict[str, Any]], bool]


class ExecutionSurfaceProbeInputError(ValueError):
    """Typed, secret-safe rejection from the probe-specific request loader."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _probe_input_error(error_code: str, message: str) -> None:
    raise ExecutionSurfaceProbeInputError(error_code, message)


EXECUTION_SURFACE_PROBE_POLICY = {
    "schema_version": "execution_surface_probe_policy_v1",
    "report_schema_path": (
        ".codex/schemas/execution_surface_truth_probe_v1.schema.json"
    ),
    "declaration_source_precedence": {
        "global_config": 10,
        "repository_config": 20,
    },
    "host_observation_sources": {
        "host_config_read": "host_config_read_observation_v1",
        "prompt_input": "prompt_input_observation_v1",
    },
    "config_key_allowlist": [
        "agents.default_subagent_model",
        "agents.default_subagent_reasoning_effort",
        "agents.enabled",
        "agents.interrupt_message",
        "agents.max_concurrent_threads_per_session",
    ],
    "config_value_allowlists": {
        "agents.default_subagent_model": [
            "gpt-5.6-luna",
            "gpt-5.6-sol",
            "gpt-5.6-terra",
        ],
        "agents.default_subagent_reasoning_effort": [
            "high",
            "low",
            "max",
            "medium",
            "ultra",
            "xhigh",
        ],
    },
    "instruction_source_allowlist": [
        "canonical_repo_agents",
        "knowledgepilot_auto_rule",
        "workspace_entry_shim",
    ],
    "missing_selection_status": "UNVERIFIED",
    "causal_attribution": "NOT_INFERRED",
}


def execution_surface_probe_policy() -> dict[str, Any]:
    """Return the closed source/schema policy owned by this cohesive probe."""

    return deepcopy(EXECUTION_SURFACE_PROBE_POLICY)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _reject_duplicate_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _probe_input_error("PROBE_INPUT_JSON", "probe request JSON is invalid")
        value[key] = item
    return value


def _reject_nonfinite_json(_value: str) -> None:
    _probe_input_error("PROBE_INPUT_JSON", "probe request JSON is invalid")


def load_execution_surface_probe_request(
    reference: str,
    *,
    cwd: Path | None = None,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Load one bounded, repository-contained request without following symlinks."""

    if not isinstance(reference, str) or not reference.startswith("@"):
        _probe_input_error(
            "PROBE_PATH_REFERENCE",
            "probe request must use a repository-relative @path",
        )
    relative = Path(reference[1:])
    if relative.is_absolute():
        _probe_input_error(
            "PROBE_PATH_ABSOLUTE",
            "absolute probe request paths are not allowed",
        )
    if not relative.parts or any(part == ".." for part in relative.parts):
        _probe_input_error(
            "PROBE_PATH_TRAVERSAL",
            "probe request path traversal is not allowed",
        )

    repository_root = root.resolve(strict=True)
    working_directory = (Path.cwd() if cwd is None else cwd).resolve(strict=True)
    try:
        working_directory.relative_to(repository_root)
    except ValueError:
        _probe_input_error(
            "PROBE_PATH_OUTSIDE_REPOSITORY",
            "probe request working directory is outside the repository",
        )
    candidate = working_directory.joinpath(*relative.parts)
    current = working_directory
    target_stat: os.stat_result | None = None
    for part in relative.parts:
        current = current / part
        try:
            target_stat = os.lstat(current)
        except FileNotFoundError:
            _probe_input_error(
                "PROBE_PATH_MISSING",
                "probe request path does not exist",
            )
        except OSError:
            _probe_input_error(
                "PROBE_INPUT_IO",
                "probe request path cannot be inspected safely",
            )
        if stat.S_ISLNK(target_stat.st_mode):
            _probe_input_error(
                "PROBE_PATH_SYMLINK",
                "probe request path must not contain a symlink",
            )
    if target_stat is None or not stat.S_ISREG(target_stat.st_mode):
        _probe_input_error(
            "PROBE_PATH_NOT_REGULAR",
            "probe request path must be a regular file",
        )
    try:
        candidate.resolve(strict=True).relative_to(repository_root)
    except ValueError:
        _probe_input_error(
            "PROBE_PATH_OUTSIDE_REPOSITORY",
            "probe request path is outside the repository",
        )
    if target_stat.st_size > EXECUTION_SURFACE_PROBE_MAX_REQUEST_BYTES:
        _probe_input_error(
            "PROBE_INPUT_TOO_LARGE",
            "probe request exceeds the byte limit",
        )

    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(candidate, flags)
        opened_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or opened_stat.st_dev != target_stat.st_dev
            or opened_stat.st_ino != target_stat.st_ino
        ):
            _probe_input_error(
                "PROBE_INPUT_CHANGED",
                "probe request changed during bounded loading",
            )
        chunks: list[bytes] = []
        remaining = EXECUTION_SURFACE_PROBE_MAX_REQUEST_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
    except ExecutionSurfaceProbeInputError:
        raise
    except OSError:
        _probe_input_error(
            "PROBE_INPUT_IO",
            "probe request cannot be read safely",
        )
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(payload) > EXECUTION_SURFACE_PROBE_MAX_REQUEST_BYTES:
        _probe_input_error(
            "PROBE_INPUT_TOO_LARGE",
            "probe request exceeds the byte limit",
        )
    try:
        decoded = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _probe_input_error(
            "PROBE_INPUT_ENCODING",
            "probe request must use strict UTF-8 encoding",
        )
    try:
        parsed = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_json_object,
            parse_constant=_reject_nonfinite_json,
        )
    except ExecutionSurfaceProbeInputError:
        raise
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError):
        _probe_input_error("PROBE_INPUT_JSON", "probe request JSON is invalid")
    if not isinstance(parsed, dict):
        _probe_input_error("PROBE_INPUT_JSON", "probe request JSON is invalid")
    return parsed


def _host_source_authenticity(
    source: dict[str, Any],
    *,
    surface_profile_id: str,
    surface_profile_sha256: str,
    host_verifier: ExecutionSurfaceHostVerifier | None,
) -> str:
    if host_verifier is None:
        return "CALLER_CLAIMED"
    try:
        verified = host_verifier(
            surface_profile_id,
            surface_profile_sha256,
            deepcopy(source),
        )
    except Exception:
        verified = False
    return "HOST_VERIFIED" if verified is True else "CALLER_CLAIMED"


def _validated_source(source: Any, policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(source, dict) or set(source) != {
        "source_id",
        "source_kind",
        "payload",
        "payload_sha256",
        "source_sha256",
    }:
        raise ValueError("execution-surface source fields are not exact")
    source_without_digest = {
        key: value for key, value in source.items() if key != "source_sha256"
    }
    if source.get("payload_sha256") != _digest(source.get("payload")):
        raise ValueError("execution-surface source payload digest is invalid")
    if source.get("source_sha256") != _digest(source_without_digest):
        raise ValueError("execution-surface source digest is invalid")
    source_id = source.get("source_id")
    source_kind = source.get("source_kind")
    declaration_ranks = policy["declaration_source_precedence"]
    host_sources = policy["host_observation_sources"]
    if source_id in declaration_ranks and source_kind == "config_declaration_v1":
        _validate_config_values_payload(
            source.get("payload"), declaration=True, policy=policy
        )
    elif (
        source_id == "host_config_read"
        and source_kind == host_sources.get(source_id)
    ):
        _validate_host_config_read_payload(source.get("payload"), policy)
    elif (
        source_id == "prompt_input"
        and source_kind == host_sources.get(source_id)
    ):
        _validate_prompt_input_payload(source.get("payload"), policy)
    else:
        raise ValueError("execution-surface source is not allowlisted")
    return source


def _validate_safe_config_value(
    item: Any,
    *,
    origin_required: bool,
    policy: dict[str, Any],
) -> None:
    fields = {"key", "value", "origin_source_id"} if origin_required else {
        "key",
        "value",
    }
    if not isinstance(item, dict) or set(item) != fields:
        raise ValueError("config value fields are not exact")
    key = item.get("key")
    value = item.get("value")
    if key not in policy["config_key_allowlist"]:
        raise ValueError("config key is not allowlisted")
    if key not in _TYPED_CONFIG_KEYS:
        raise ValueError("config key lacks a closed type contract")
    if key in {"agents.enabled", "agents.interrupt_message"}:
        valid_value = type(value) is bool
    elif key == "agents.max_concurrent_threads_per_session":
        valid_value = type(value) is int and 1 <= value <= 16
    elif key == "agents.default_subagent_model":
        valid_value = value in policy["config_value_allowlists"][key]
    else:
        valid_value = value in policy["config_value_allowlists"][key]
    if not valid_value:
        raise ValueError("config value type is invalid")


def _validate_config_values_payload(
    payload: Any,
    *,
    declaration: bool,
    policy: dict[str, Any],
) -> None:
    if not isinstance(payload, dict) or set(payload) != {"values"}:
        raise ValueError("config declaration payload fields are not exact")
    values = payload.get("values")
    if not isinstance(values, list) or not values:
        raise ValueError("config declaration values must be a non-empty array")
    seen: set[str] = set()
    for item in values:
        _validate_safe_config_value(
            item,
            origin_required=not declaration,
            policy=policy,
        )
        key = item["key"]
        if key in seen:
            raise ValueError("config keys must be unique per source")
        seen.add(key)


def _validate_host_config_read_payload(
    payload: Any,
    policy: dict[str, Any],
) -> None:
    if not isinstance(payload, dict) or set(payload) != {
        "ordered_layer_source_ids",
        "selected_values",
    }:
        raise ValueError("host config-read payload fields are not exact")
    layers = payload.get("ordered_layer_source_ids")
    if (
        not isinstance(layers, list)
        or not layers
        or len(layers) != len(set(layers))
        or any(
            layer not in policy["declaration_source_precedence"] for layer in layers
        )
    ):
        raise ValueError("host config-read layers are invalid")
    declaration_ranks = policy["declaration_source_precedence"]
    if layers != sorted(layers, key=lambda item: declaration_ranks[item]):
        raise ValueError("host config-read layers are not in probe precedence order")
    values = payload.get("selected_values")
    if not isinstance(values, list) or not values:
        raise ValueError("host config-read selected values must be non-empty")
    seen: set[str] = set()
    for item in values:
        _validate_safe_config_value(item, origin_required=True, policy=policy)
        if item["origin_source_id"] not in layers:
            raise ValueError("host config-read origin is outside observed layers")
        if item["key"] in seen:
            raise ValueError("host config-read selected keys must be unique")
        seen.add(item["key"])


def _validate_prompt_input_payload(
    payload: Any,
    policy: dict[str, Any],
) -> None:
    if not isinstance(payload, dict) or set(payload) != {
        "cwd_class",
        "instruction_sources",
    }:
        raise ValueError("prompt-input payload fields are not exact")
    if payload.get("cwd_class") not in {
        "workspace_root",
        "canonical_repo",
        "linked_worktree",
    }:
        raise ValueError("prompt-input cwd class is invalid")
    instructions = payload.get("instruction_sources")
    instruction_ids = set(policy["instruction_source_allowlist"])
    if not isinstance(instructions, list) or len(instructions) != len(instruction_ids):
        raise ValueError("prompt-input instruction roster is invalid")
    seen: set[str] = set()
    for instruction in instructions:
        if not isinstance(instruction, dict) or set(instruction) != {
            "instruction_id",
            "selection",
            "content_sha256",
        }:
            raise ValueError("prompt-input instruction fields are not exact")
        instruction_id = instruction.get("instruction_id")
        selection = instruction.get("selection")
        content_digest = instruction.get("content_sha256")
        if instruction_id not in instruction_ids or instruction_id in seen:
            raise ValueError("prompt-input instruction id is invalid")
        if selection == "SELECTED":
            if not isinstance(content_digest, str) or not _DIGEST_RE.fullmatch(
                content_digest
            ):
                raise ValueError("selected prompt-input instruction lacks content digest")
        elif selection == "NOT_SELECTED":
            if content_digest is not None:
                raise ValueError("unselected prompt-input instruction has a content digest")
        else:
            raise ValueError("prompt-input instruction selection is invalid")
        seen.add(instruction_id)
    if seen != instruction_ids:
        raise ValueError("prompt-input instruction roster is invalid")


def build_execution_surface_truth_report(
    request: Any,
    registry: dict[str, Any],
    *,
    host_verifier: ExecutionSurfaceHostVerifier | None = None,
) -> dict[str, Any]:
    """Build one replayable report without treating declarations as selections."""

    if not isinstance(request, dict) or set(request) != {
        "schema_version",
        "surface_profile_id",
        "sources",
    }:
        raise ValueError("execution-surface probe request fields are not exact")
    if request.get("schema_version") != "execution_surface_probe_request_v1":
        raise ValueError("execution-surface probe request schema_version is invalid")
    surface_profile_id = request.get("surface_profile_id")
    profiles = registry.get("execution_policy", {}).get("surface_profiles", {})
    if surface_profile_id not in profiles:
        raise ValueError("execution-surface profile is not Registry declared")
    surface_profile_sha256 = _digest(profiles[surface_profile_id])
    policy = execution_surface_probe_policy()
    raw_sources = request.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("execution-surface probe sources must be non-empty")
    sources = [_validated_source(source, policy) for source in raw_sources]
    source_ids = [source["source_id"] for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("execution-surface source ids must be unique")

    declarations = [
        source
        for source in sources
        if source["source_kind"] == "config_declaration_v1"
    ]
    host_sources = [
        source
        for source in sources
        if source["source_kind"] == "host_config_read_observation_v1"
    ]
    if len(host_sources) > 1:
        raise ValueError("execution-surface probe accepts one host config-read source")
    prompt_sources = [
        source
        for source in sources
        if source["source_kind"] == "prompt_input_observation_v1"
    ]
    if len(prompt_sources) > 1:
        raise ValueError("execution-surface probe accepts one prompt-input source")
    if not declarations and not host_sources:
        raise ValueError("execution-surface probe requires allowlisted config evidence")
    source_authenticity = {
        source["source_id"]: (
            "DECLARATION_SNAPSHOT"
            if source["source_kind"] == "config_declaration_v1"
            else _host_source_authenticity(
                source,
                surface_profile_id=surface_profile_id,
                surface_profile_sha256=surface_profile_sha256,
                host_verifier=host_verifier,
            )
        )
        for source in sources
    }
    verified_host_sources = [
        source
        for source in host_sources
        if source_authenticity[source["source_id"]] == "HOST_VERIFIED"
    ]
    verified_prompt_sources = [
        source
        for source in prompt_sources
        if source_authenticity[source["source_id"]] == "HOST_VERIFIED"
    ]
    candidates: dict[str, list[dict[str, Any]]] = {}
    for source in declarations:
        for item in source["payload"]["values"]:
            candidates.setdefault(item["key"], []).append(
                {
                    "source_id": source["source_id"],
                    "precedence_rank": policy["declaration_source_precedence"][
                        source["source_id"]
                    ],
                    "value": item["value"],
                }
            )
    selected_values = {
        item["key"]: item
        for source in verified_host_sources
        for item in source["payload"]["selected_values"]
    }
    key_reports = []
    for key in sorted(set(candidates) | set(selected_values)):
        declared = sorted(
            candidates.get(key, []),
            key=lambda item: (item["precedence_rank"], item["source_id"]),
        )
        observed = selected_values.get(key)
        if observed is None:
            selected = {
                "status": policy["missing_selection_status"],
                "value": None,
                "origin_source_id": None,
                "evidence_source_id": None,
            }
            mismatch = "SELECTION_UNVERIFIED"
        else:
            selected = {
                "status": "HOST_OBSERVED",
                "value": observed["value"],
                "origin_source_id": observed["origin_source_id"],
                "evidence_source_id": "host_config_read",
            }
            if not declared:
                mismatch = "OBSERVED_VALUE_NOT_DECLARED"
            elif observed["value"] != declared[-1]["value"]:
                mismatch = "DIFFERS_FROM_HIGHEST_PRECEDENCE_DECLARATION"
            elif observed["origin_source_id"] != declared[-1]["source_id"]:
                mismatch = (
                    "ORIGIN_DIFFERS_FROM_HIGHEST_PRECEDENCE_DECLARATION"
                )
            else:
                mismatch = "MATCHES_HIGHEST_PRECEDENCE_DECLARATION"
        key_reports.append(
            {
                "key": key,
                "declared_candidates": declared,
                "selected": selected,
                "mismatch_classification": mismatch,
                "causal_attribution": policy["causal_attribution"],
            }
        )

    instruction_selection = (
        {
            "status": "HOST_OBSERVED",
            "cwd_class": verified_prompt_sources[0]["payload"]["cwd_class"],
            "sources": sorted(
                verified_prompt_sources[0]["payload"]["instruction_sources"],
                key=lambda item: item["instruction_id"],
            ),
            "evidence_source_id": "prompt_input",
            "causal_attribution": policy["causal_attribution"],
        }
        if verified_prompt_sources
        else {
            "status": policy["missing_selection_status"],
            "cwd_class": None,
            "sources": [],
            "evidence_source_id": None,
            "causal_attribution": policy["causal_attribution"],
        }
    )
    has_unverified = instruction_selection["status"] == policy[
        "missing_selection_status"
    ] or any(
        item["selected"]["status"] == policy["missing_selection_status"]
        for item in key_reports
    )
    report: dict[str, Any] = {
        "schema_version": "execution_surface_truth_probe_v1",
        "report_status": (
            "COMPLETE_WITH_UNVERIFIED" if has_unverified else "COMPLETE"
        ),
        "surface_profile_id": surface_profile_id,
        "surface_profile_sha256": surface_profile_sha256,
        "policy_sha256": _digest(policy),
        "authenticity": {
            "host_verifier": (
                "AVAILABLE" if host_verifier is not None else "UNAVAILABLE"
            ),
            "profile_selection": (
                "HOST_VERIFIED"
                if verified_host_sources or verified_prompt_sources
                else "CALLER_CLAIMED"
            ),
            "sha256_scope": "INTEGRITY_ONLY",
        },
        "source_manifest": [
            {
                "source_id": source["source_id"],
                "source_kind": source["source_kind"],
                "evidence_payload": source["payload"],
                "payload_sha256": source["payload_sha256"],
                "source_sha256": source["source_sha256"],
                "authenticity_status": source_authenticity[source["source_id"]],
            }
            for source in sorted(sources, key=lambda item: item["source_id"])
        ],
        "config_precedence": {
            "observed_layer_order": (
                verified_host_sources[0]["payload"]["ordered_layer_source_ids"]
                if verified_host_sources
                else []
            ),
            "keys": key_reports,
        },
        "instruction_selection": instruction_selection,
        "causal_limits": {
            "declaration_is_selection": False,
            "mismatch_establishes_causality": False,
            "missing_host_evidence_preserved_as_unverified": True,
            "sha256_establishes_authenticity": False,
        },
    }
    report["report_digest"] = _digest(report)
    return report


def execution_surface_truth_report_digest(report: dict[str, Any]) -> str:
    """Return the canonical digest of a report excluding its digest field."""

    return _digest({key: value for key, value in report.items() if key != "report_digest"})


def validate_execution_surface_truth_report(
    report: Any,
    registry: dict[str, Any],
    *,
    root: Path = REPO_ROOT,
    host_verifier: ExecutionSurfaceHostVerifier | None = None,
) -> list[str]:
    """Recheck schema plus every policy, payload, source, and report binding."""

    if not isinstance(report, dict):
        return ["execution-surface report must be an object"]
    policy = execution_surface_probe_policy()
    try:
        schema_path = Path(policy["report_schema_path"])
        if schema_path.is_absolute() or ".." in schema_path.parts:
            raise ValueError("unsafe report schema path")
        schema = json.loads((root / schema_path).read_text(encoding="utf-8"))
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        return [f"execution-surface report schema is unavailable: {error}"]
    errors = schema_subset_errors(report, schema, schema)
    authenticity = report.get("authenticity")
    if (
        isinstance(authenticity, dict)
        and authenticity.get("profile_selection") == "HOST_VERIFIED"
        and host_verifier is None
    ):
        errors.append(
            "host-verified execution-surface report requires an out-of-band verifier"
        )
    if report.get("policy_sha256") != _digest(policy):
        errors.append("execution-surface policy digest is invalid")
    profile_id = report.get("surface_profile_id")
    profiles = registry.get("execution_policy", {}).get("surface_profiles", {})
    if (
        profile_id not in profiles
        or report.get("surface_profile_sha256") != _digest(profiles[profile_id])
    ):
        errors.append("execution-surface profile digest is invalid")
    manifest = report.get("source_manifest")
    if isinstance(manifest, list):
        for binding in manifest:
            if not isinstance(binding, dict):
                continue
            source_id = binding.get("source_id")
            payload = binding.get("evidence_payload")
            if binding.get("payload_sha256") != _digest(payload):
                errors.append(f"{source_id}: evidence payload digest is invalid")
            source_without_digest = {
                "source_id": source_id,
                "source_kind": binding.get("source_kind"),
                "payload": payload,
                "payload_sha256": binding.get("payload_sha256"),
            }
            if binding.get("source_sha256") != _digest(source_without_digest):
                errors.append(f"{source_id}: source digest is invalid")
    if report.get("report_digest") != execution_surface_truth_report_digest(report):
        errors.append("execution-surface report digest is invalid")
    if isinstance(manifest, list):
        try:
            replay_sources = [
                {
                    "source_id": binding["source_id"],
                    "source_kind": binding["source_kind"],
                    "payload": binding["evidence_payload"],
                    "payload_sha256": binding["payload_sha256"],
                    "source_sha256": binding["source_sha256"],
                }
                for binding in manifest
            ]
            replayed = build_execution_surface_truth_report(
                {
                    "schema_version": "execution_surface_probe_request_v1",
                    "surface_profile_id": report.get("surface_profile_id"),
                    "sources": replay_sources,
                },
                registry,
                host_verifier=host_verifier,
            )
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"execution-surface source replay is invalid: {error}")
        else:
            if replayed != report:
                errors.append(
                    "execution-surface report differs from deterministic source replay"
                )
    return errors
