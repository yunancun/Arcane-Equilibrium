"""Typed cold-source resolution and immutable pre-capability terminal evidence.

This module proves only source availability.  It never creates candidate
evaluation, learning, hidden-OOS, proof, regime, portfolio, or resource
evidence, and it grants no training, serving, promotion, or order authority.
"""

from __future__ import annotations

import copy
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.candidate_evaluation_context import canonical_sha256


READY = "READY"
DEFER = "DEFER"
PERMANENTLY_UNAVAILABLE = "PERMANENTLY_UNAVAILABLE"
PRE_CAPABILITY_BUILD = "PRE_CAPABILITY_BUILD"

CANDIDATE_EVALUATION_SOURCE_CAPABILITY_GIT_SHA = (
    "c58b9904012418b0a50f2ed8ee3e917eccb7394e"
)
CANDIDATE_EVALUATION_SOURCE_CAPABILITY_SCHEMA_VERSION = (
    "candidate_evaluation_source_snapshot_v1"
)
CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_SCHEMA_VERSION = (
    "candidate_evaluation_source_unavailability_v1"
)
CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_BOUNDARY = (
    "source-availability terminal evidence only; no evaluation, learning, "
    "hidden-OOS, proof, regime, portfolio, resource, training, serving, "
    "promotion, order, lease, gate, config, broker, or runtime authority"
)
CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_HASH_FIELD = (
    "candidate_evaluation_source_unavailability_hash"
)

_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UNAVAILABILITY_FIELDS = {
    "schema_version",
    "status",
    "reason",
    "event_hash",
    "context_id",
    "build_git_sha",
    "capability_schema_version",
    "capability_introduced_at_git_sha",
    "ancestry_relation",
    "boundary",
    CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_HASH_FIELD,
}
_ROOT = Path(__file__).resolve().parents[3]


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
                and self.reason == PRE_CAPABILITY_BUILD
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
            reason=PRE_CAPABILITY_BUILD,
        )


GitRunner = Callable[..., Any]


@dataclass
class GitAncestryResolver:
    """Fail-closed strict-ancestor resolver cached by candidate build SHA."""

    repo_root: Path
    runner: GitRunner = subprocess.run
    timeout_seconds: float = 5.0
    _cache: dict[str, bool] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root).resolve()
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or self.timeout_seconds <= 0
        ):
            raise ValueError("GIT_ANCESTRY_TIMEOUT_INVALID")

    def is_strict_pre_capability(self, build_git_sha: Any) -> bool:
        if (
            not isinstance(build_git_sha, str)
            or _GIT_SHA.fullmatch(build_git_sha) is None
            or build_git_sha
            == CANDIDATE_EVALUATION_SOURCE_CAPABILITY_GIT_SHA
        ):
            return False
        if build_git_sha in self._cache:
            return self._cache[build_git_sha]

        env = os.environ.copy()
        env["GIT_NO_REPLACE_OBJECTS"] = "1"
        try:
            completed = self.runner(
                [
                    "git",
                    "--no-replace-objects",
                    "-C",
                    str(self.repo_root),
                    "merge-base",
                    "--is-ancestor",
                    build_git_sha,
                    CANDIDATE_EVALUATION_SOURCE_CAPABILITY_GIT_SHA,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=self.timeout_seconds,
                env=env,
            )
            result = (
                isinstance(getattr(completed, "returncode", None), int)
                and completed.returncode == 0
            )
        except (OSError, subprocess.SubprocessError):
            result = False
        self._cache[build_git_sha] = result
        return result


DEFAULT_GIT_ANCESTRY_RESOLVER = GitAncestryResolver(_ROOT)


def build_pre_capability_source_provider(
    resolver: GitAncestryResolver = DEFAULT_GIT_ANCESTRY_RESOLVER,
) -> Callable[[dict[str, Any], str], CandidateEvaluationSourceResolution]:
    """Return a partial provider that terminalizes only proven legacy builds."""

    def provider(
        candidate_event_context: dict[str, Any],
        _as_of_utc_date: str,
    ) -> CandidateEvaluationSourceResolution:
        try:
            build_git_sha = candidate_event_context.get("build_git_sha")
            if resolver.is_strict_pre_capability(build_git_sha):
                return CandidateEvaluationSourceResolution.permanently_unavailable()
        except Exception:
            pass
        return CandidateEvaluationSourceResolution.defer()

    return provider


def build_candidate_evaluation_source_unavailability(
    candidate_event_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Build deterministic event-bound metadata after ancestry was proven."""

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
        or _GIT_SHA.fullmatch(build_git_sha) is None
    ):
        raise ValueError("CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_EVENT_INVALID")
    body = {
        "schema_version": (
            CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_SCHEMA_VERSION
        ),
        "status": PERMANENTLY_UNAVAILABLE,
        "reason": PRE_CAPABILITY_BUILD,
        "event_hash": event_hash,
        "context_id": context_id,
        "build_git_sha": build_git_sha,
        "capability_schema_version": (
            CANDIDATE_EVALUATION_SOURCE_CAPABILITY_SCHEMA_VERSION
        ),
        "capability_introduced_at_git_sha": (
            CANDIDATE_EVALUATION_SOURCE_CAPABILITY_GIT_SHA
        ),
        "ancestry_relation": "STRICT_ANCESTOR_OF_CAPABILITY_INTRO",
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
) -> dict[str, Any]:
    """Validate canonical integrity and exact binding; ancestry is separate."""

    if not isinstance(value, Mapping):
        raise ValueError("CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_INVALID")
    try:
        source = copy.deepcopy({key: value[key] for key in value})
    except Exception as exc:
        raise ValueError(
            "CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_INVALID"
        ) from exc
    if set(source) != _UNAVAILABILITY_FIELDS:
        raise ValueError("CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_FIELDS_INVALID")
    expected = build_candidate_evaluation_source_unavailability(
        candidate_event_context
    )
    if source != expected:
        raise ValueError(
            "CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_NONCANONICAL"
        )
    return expected


__all__ = [
    "CANDIDATE_EVALUATION_SOURCE_CAPABILITY_GIT_SHA",
    "CANDIDATE_EVALUATION_SOURCE_CAPABILITY_SCHEMA_VERSION",
    "CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_HASH_FIELD",
    "CANDIDATE_EVALUATION_SOURCE_UNAVAILABILITY_SCHEMA_VERSION",
    "CandidateEvaluationSourceResolution",
    "DEFAULT_GIT_ANCESTRY_RESOLVER",
    "DEFER",
    "GitAncestryResolver",
    "PERMANENTLY_UNAVAILABLE",
    "PRE_CAPABILITY_BUILD",
    "READY",
    "build_candidate_evaluation_source_unavailability",
    "build_pre_capability_source_provider",
    "validate_candidate_evaluation_source_unavailability",
]
