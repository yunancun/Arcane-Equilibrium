"""Typed cold-source resolution for one reviewed legacy build identity.

This module proves only that one exact, source-controlled legacy build lacks
the candidate-evaluation source snapshot.  It never creates evaluation,
learning, hidden-OOS, proof, regime, portfolio, or resource evidence, and it
grants no training, serving, promotion, order, or runtime authority.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from cost_gate_learning_lane.candidate_evaluation_context import canonical_sha256


READY = "READY"
DEFER = "DEFER"
PERMANENTLY_UNAVAILABLE = "PERMANENTLY_UNAVAILABLE"
REVIEWED_LEGACY_BUILD_SOURCE_UNAVAILABLE = (
    "REVIEWED_LEGACY_BUILD_SOURCE_UNAVAILABLE"
)
EXACT_BUILD_ATTESTATION = "EXACT_BUILD_ATTESTATION"

CANDIDATE_EVALUATION_SOURCE_SCHEMA_VERSION = (
    "candidate_evaluation_source_snapshot_v1"
)
REVIEWED_LEGACY_BUILD_ATTESTATION_SCHEMA_VERSION = (
    "reviewed_legacy_build_attestation_v1"
)
REVIEWED_LEGACY_BUILD_REGISTRY_SCHEMA_VERSION = (
    "reviewed_legacy_build_attestation_registry_v1"
)
CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_SCHEMA_VERSION = (
    "candidate_evaluation_source_unavailability_v2"
)
CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_BOUNDARY = (
    "source-availability terminal evidence only; exact reviewed build identity "
    "does not create evaluation, label, learning, hidden-OOS, proof, regime, "
    "portfolio, resource, training, serving, promotion, order, lease, gate, "
    "config, broker, risk, auth, profit, or runtime authority"
)
CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_HASH_FIELD = (
    "candidate_evaluation_source_unavailability_hash"
)
REVIEWED_LEGACY_BUILD_GIT_SHA = (
    "0a4d38ee08f93e9cb3a3bae7160f86fe1716297d"
)

_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ATTESTATION_FIELDS = {
    "schema_version",
    "status",
    "reason",
    "verification_method",
    "build_git_sha",
    "unavailable_source_schema_version",
    "boundary",
    "attestation_id",
}
_RESOLVED_ATTESTATION_FIELDS = _ATTESTATION_FIELDS | {
    "registry_schema_version",
    "registry_digest",
}
_UNAVAILABILITY_FIELDS = {
    "schema_version",
    "status",
    "reason",
    "verification_method",
    "event_hash",
    "context_id",
    "build_git_sha",
    "unavailable_source_schema_version",
    "attestation_schema_version",
    "attestation_id",
    "registry_schema_version",
    "registry_digest",
    "boundary",
    CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_HASH_FIELD,
}


def _reviewed_attestation_body() -> dict[str, Any]:
    return {
        "schema_version": REVIEWED_LEGACY_BUILD_ATTESTATION_SCHEMA_VERSION,
        "status": "ACTIVE",
        "reason": REVIEWED_LEGACY_BUILD_SOURCE_UNAVAILABLE,
        "verification_method": EXACT_BUILD_ATTESTATION,
        "build_git_sha": REVIEWED_LEGACY_BUILD_GIT_SHA,
        "unavailable_source_schema_version": (
            CANDIDATE_EVALUATION_SOURCE_SCHEMA_VERSION
        ),
        "boundary": CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_BOUNDARY,
    }


_REVIEWED_ATTESTATION_BODY = _reviewed_attestation_body()
REVIEWED_LEGACY_BUILD_ATTESTATION_ID = canonical_sha256(
    _REVIEWED_ATTESTATION_BODY
)
_REVIEWED_ATTESTATION = MappingProxyType(
    {
        **_REVIEWED_ATTESTATION_BODY,
        "attestation_id": REVIEWED_LEGACY_BUILD_ATTESTATION_ID,
    }
)
DEFAULT_REVIEWED_LEGACY_BUILD_REGISTRY = MappingProxyType(
    {
        REVIEWED_LEGACY_BUILD_GIT_SHA: _REVIEWED_ATTESTATION,
    }
)


def _copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy({key: value[key] for key in value})


def _validated_registry_projection(
    registry: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], str] | None:
    """Validate the closed singleton registry and return its canonical digest."""

    if (
        not isinstance(registry, Mapping)
        or set(registry) != {REVIEWED_LEGACY_BUILD_GIT_SHA}
    ):
        return None
    try:
        raw = registry[REVIEWED_LEGACY_BUILD_GIT_SHA]
        if not isinstance(raw, Mapping):
            return None
        attestation = _copy_mapping(raw)
    except Exception:
        return None
    if set(attestation) != _ATTESTATION_FIELDS:
        return None
    expected = {
        **_reviewed_attestation_body(),
        "attestation_id": REVIEWED_LEGACY_BUILD_ATTESTATION_ID,
    }
    if attestation != expected:
        return None
    registry_body = {
        "schema_version": REVIEWED_LEGACY_BUILD_REGISTRY_SCHEMA_VERSION,
        "entries": [attestation],
    }
    return attestation, canonical_sha256(registry_body)


_DEFAULT_REGISTRY_PROJECTION = _validated_registry_projection(
    DEFAULT_REVIEWED_LEGACY_BUILD_REGISTRY
)
if _DEFAULT_REGISTRY_PROJECTION is None:
    raise RuntimeError("REVIEWED_LEGACY_BUILD_REGISTRY_INVALID")
REVIEWED_LEGACY_BUILD_REGISTRY_DIGEST = _DEFAULT_REGISTRY_PROJECTION[1]


def resolve_reviewed_legacy_build(
    build_git_sha: Any,
    *,
    registry: Mapping[
        str,
        Mapping[str, Any],
    ] = DEFAULT_REVIEWED_LEGACY_BUILD_REGISTRY,
) -> dict[str, Any] | None:
    """Resolve one exact reviewed build without repository or command access."""

    if (
        not isinstance(build_git_sha, str)
        or _GIT_SHA.fullmatch(build_git_sha) is None
        or build_git_sha != REVIEWED_LEGACY_BUILD_GIT_SHA
    ):
        return None
    projection = _validated_registry_projection(registry)
    if projection is None:
        return None
    attestation, registry_digest = projection
    return {
        **attestation,
        "registry_schema_version": (
            REVIEWED_LEGACY_BUILD_REGISTRY_SCHEMA_VERSION
        ),
        "registry_digest": registry_digest,
    }


@dataclass(frozen=True)
class CandidateEvaluationSourceResolution:
    """Exact typed result returned by a candidate-evaluation source provider."""

    status: str
    bundle: Mapping[str, Any] | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        valid = bool(
            (
                self.status == READY
                and isinstance(self.bundle, Mapping)
                and self.reason is None
            )
            or (
                self.status == DEFER
                and self.bundle is None
                and self.reason is None
            )
            or (
                self.status == PERMANENTLY_UNAVAILABLE
                and self.bundle is None
                and self.reason
                == REVIEWED_LEGACY_BUILD_SOURCE_UNAVAILABLE
            )
        )
        if not valid:
            raise ValueError("CANDIDATE_EVALUATION_SOURCE_RESOLUTION_INVALID")

    @classmethod
    def ready(
        cls,
        bundle: Mapping[str, Any],
    ) -> "CandidateEvaluationSourceResolution":
        return cls(status=READY, bundle=bundle)

    @classmethod
    def defer(cls) -> "CandidateEvaluationSourceResolution":
        return cls(status=DEFER)

    @classmethod
    def permanently_unavailable(
        cls,
    ) -> "CandidateEvaluationSourceResolution":
        return cls(
            status=PERMANENTLY_UNAVAILABLE,
            reason=REVIEWED_LEGACY_BUILD_SOURCE_UNAVAILABLE,
        )


ReviewedLegacyBuildRegistry = Mapping[str, Mapping[str, Any]]


def build_reviewed_legacy_build_source_provider(
    registry: ReviewedLegacyBuildRegistry = (
        DEFAULT_REVIEWED_LEGACY_BUILD_REGISTRY
    ),
) -> Callable[[dict[str, Any], str], CandidateEvaluationSourceResolution]:
    """Return a provider that terminalizes only the exact reviewed build."""

    def provider(
        candidate_event_context: dict[str, Any],
        _as_of_utc_date: str,
    ) -> CandidateEvaluationSourceResolution:
        try:
            if resolve_reviewed_legacy_build(
                candidate_event_context.get("build_git_sha"),
                registry=registry,
            ) is not None:
                return CandidateEvaluationSourceResolution.permanently_unavailable()
        except Exception:
            pass
        return CandidateEvaluationSourceResolution.defer()

    return provider


def build_candidate_evaluation_source_unavailability(
    candidate_event_context: Mapping[str, Any],
    *,
    registry: ReviewedLegacyBuildRegistry = (
        DEFAULT_REVIEWED_LEGACY_BUILD_REGISTRY
    ),
) -> dict[str, Any]:
    """Build deterministic event-bound metadata after exact attestation lookup."""

    event_hash = candidate_event_context.get("event_hash")
    context_id = candidate_event_context.get("context_id")
    build_git_sha = candidate_event_context.get("build_git_sha")
    if (
        not isinstance(event_hash, str)
        or _SHA256.fullmatch(event_hash) is None
        or not isinstance(context_id, str)
        or not context_id
        or context_id != context_id.strip()
        or not isinstance(build_git_sha, str)
    ):
        raise ValueError("CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_EVENT_INVALID")
    attestation = resolve_reviewed_legacy_build(
        build_git_sha,
        registry=registry,
    )
    if (
        not isinstance(attestation, dict)
        or set(attestation) != _RESOLVED_ATTESTATION_FIELDS
    ):
        raise ValueError("CANDIDATE_EVALUATION_SOURCE_ATTESTATION_NOT_FOUND")
    body = {
        "schema_version": (
            CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_SCHEMA_VERSION
        ),
        "status": PERMANENTLY_UNAVAILABLE,
        "reason": REVIEWED_LEGACY_BUILD_SOURCE_UNAVAILABLE,
        "verification_method": EXACT_BUILD_ATTESTATION,
        "event_hash": event_hash,
        "context_id": context_id,
        "build_git_sha": build_git_sha,
        "unavailable_source_schema_version": (
            attestation["unavailable_source_schema_version"]
        ),
        "attestation_schema_version": attestation["schema_version"],
        "attestation_id": attestation["attestation_id"],
        "registry_schema_version": attestation["registry_schema_version"],
        "registry_digest": attestation["registry_digest"],
        "boundary": CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_BOUNDARY,
    }
    return {
        **body,
        CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_HASH_FIELD: (
            canonical_sha256(body)
        ),
    }


def validate_candidate_evaluation_source_unavailability(
    value: Any,
    *,
    candidate_event_context: Mapping[str, Any],
    registry: ReviewedLegacyBuildRegistry = (
        DEFAULT_REVIEWED_LEGACY_BUILD_REGISTRY
    ),
) -> dict[str, Any]:
    """Validate marker integrity, event binding, and the active exact registry."""

    if not isinstance(value, Mapping):
        raise ValueError("CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_INVALID")
    try:
        source = _copy_mapping(value)
    except Exception as exc:
        raise ValueError(
            "CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_INVALID"
        ) from exc
    if set(source) != _UNAVAILABILITY_FIELDS:
        raise ValueError("CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_FIELDS_INVALID")
    expected = build_candidate_evaluation_source_unavailability(
        candidate_event_context,
        registry=registry,
    )
    if source != expected:
        raise ValueError(
            "CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_NONCANONICAL"
        )
    return expected


__all__ = [
    "CANDIDATE_EVALUATION_SOURCE_SCHEMA_VERSION",
    "CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_HASH_FIELD",
    "CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_SCHEMA_VERSION",
    "CandidateEvaluationSourceResolution",
    "DEFAULT_REVIEWED_LEGACY_BUILD_REGISTRY",
    "DEFER",
    "EXACT_BUILD_ATTESTATION",
    "PERMANENTLY_UNAVAILABLE",
    "READY",
    "REVIEWED_LEGACY_BUILD_ATTESTATION_ID",
    "REVIEWED_LEGACY_BUILD_ATTESTATION_SCHEMA_VERSION",
    "REVIEWED_LEGACY_BUILD_GIT_SHA",
    "REVIEWED_LEGACY_BUILD_REGISTRY_DIGEST",
    "REVIEWED_LEGACY_BUILD_REGISTRY_SCHEMA_VERSION",
    "REVIEWED_LEGACY_BUILD_SOURCE_UNAVAILABLE",
    "ReviewedLegacyBuildRegistry",
    "build_candidate_evaluation_source_unavailability",
    "build_reviewed_legacy_build_source_provider",
    "resolve_reviewed_legacy_build",
    "validate_candidate_evaluation_source_unavailability",
]
