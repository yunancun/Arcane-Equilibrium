"""Authenticated semantic projections for cacheable Development-Agent prompts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _semantic_source(source: dict[str, Any]) -> dict[str, Any]:
    """Exclude freshness/provenance receipts while retaining model-useful truth."""

    fields = (
        "source", "selector", "requirement_class", "status", "capture_kind",
        "content_encoding", "content", "content_digest",
    )
    projection = {field: source.get(field) for field in fields}
    if source.get("requirement_class") == "verdict_evidence":
        projection.update({
            field: source.get(field) for field in (
                "producer", "observed_at", "expires_at", "digest",
                "attestation_error",
            )
        })
    return projection


def _semantic_contract(contract: dict[str, Any]) -> dict[str, Any]:
    # Ambient dirty/untracked hashes remain in canonical_plan and Closure.  They
    # are intentionally absent from the cache key; scoped source projections
    # below carry the task's semantic generation instead.
    return {
        key: value for key, value in contract.items()
        if key != "baseline"
    }


def context_semantic_projections(
    plan: dict[str, Any], registry: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    shared_sources = [
        _semantic_source(source) for source in plan["sources"]
        if source.get("context_scope") == "shared"
    ]
    role_sources = [
        _semantic_source(source) for source in plan["sources"]
        if source.get("context_scope") == "role"
    ]
    source_head = plan["task_contract"]["baseline"]["source_head"]
    semantic_generation = digest_text(canonical_json([
        {
            "source": source["source"],
            "status": source["status"],
            "content_digest": source["content_digest"],
        }
        for source in shared_sources
    ]))
    shared = {
        "schema_version": "shared_task_context_v1",
        "registry_schema_version": plan["registry_schema_version"],
        "task_contract": _semantic_contract(plan["task_contract"]),
        "task_semantic_generation": {
            "source_head": source_head,
            "shared_sources_digest": semantic_generation,
        },
        "shared_packs": plan["shared_packs"],
        "sources": shared_sources,
        "evidence_debt": [
            name for name in plan["evidence_debt"]
            if any(source["source"] == name for source in shared_sources)
        ],
    }
    shared_canonical = canonical_json(shared)
    shared_digest = digest_text(shared_canonical)
    delta = {
        "schema_version": "role_context_delta_v1",
        "shared_task_context_digest": shared_digest,
        "logical_role": plan["role"],
        "permission": plan["role_permission"],
        "role_packs": plan["role_packs"],
        "sources": role_sources,
        "evidence_debt": [
            name for name in plan["evidence_debt"]
            if any(source["source"] == name for source in role_sources)
        ],
    }
    return shared, delta


def materialize_semantic_context(
    plan: dict[str, Any], registry: dict[str, Any],
) -> dict[str, str | int]:
    shared, delta = context_semantic_projections(plan, registry)
    shared_canonical = canonical_json(shared)
    delta_canonical = canonical_json(delta)
    prompt_bytes = (shared_canonical + "\n\n" + delta_canonical).encode("utf-8")
    return {
        "shared_task_context_canonical": shared_canonical,
        "shared_task_context_digest": digest_text(shared_canonical),
        "role_context_delta_canonical": delta_canonical,
        "role_context_delta_digest": digest_text(delta_canonical),
        "semantic_input_tokens": max(1, (len(prompt_bytes) + 3) // 4),
    }
