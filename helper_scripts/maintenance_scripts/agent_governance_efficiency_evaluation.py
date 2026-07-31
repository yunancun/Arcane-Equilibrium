"""Truth-labelled multi-agent efficiency evaluation.

The evaluation envelope compares exactly three execution profiles against one
immutable workload and one current-profile baseline.  It deliberately keeps
token classes separate, preserves unavailable values as ``null``, and applies
the exact Registry-owned quality non-inferiority policy before any efficiency
candidate can be reported. Evaluation records bind that policy by ID and digest;
they cannot supply or relax thresholds.

Checked-in synthetic fixtures exercise the contract and regression logic only.
They can never produce a measured-efficiency claim. Observed measured records
bind a typed attestation index containing immutable run IDs, exact call-record
inventories, and metrics payload digests. Even a structurally valid index and
self-digest remain untrusted until an out-of-band host verifier authenticates
the exact index and inventory binding. The standalone CLI has no such verifier
and therefore reports ``EXTERNAL_LIMIT``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Protocol


IMPLEMENTATION_DIR = Path(__file__).resolve().parent
if str(IMPLEMENTATION_DIR) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_DIR))

from agent_governance_schema import schema_subset_errors  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT
    / ".codex/schemas/multi_agent_efficiency_evaluation_v1.schema.json"
)
ATTESTATION_INDEX_SCHEMA_PATH = (
    REPO_ROOT
    / ".codex/schemas/multi_agent_efficiency_attestation_index_v1.schema.json"
)
REGISTRY_PATH = REPO_ROOT / ".codex/agent_registry_v1.json"

RECORD_FIELDS = {
    "schema_version",
    "evaluation_id",
    "created_at",
    "evidence_kind",
    "workload",
    "baseline",
    "profiles",
    "quality_noninferiority_policy",
    "limitations",
    "record_digest",
}
WORKLOAD_FIELDS = {"workload_id", "workload_digest", "description"}
BASELINE_FIELDS = {"baseline_id", "baseline_digest", "profile"}
PROFILE_FIELDS = {
    "profile",
    "workload_digest",
    "baseline_digest",
    "measurement_status",
    "evidence_ref",
    "evidence_digest",
    "unavailable_reason",
    "metrics",
}
PROFILE_NAMES = {"current", "single_agent", "bounded_role"}
METRIC_FIELDS = {
    "closure_quality_score",
    "required_coverage_ratio",
    "elapsed_time_ms",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "calls",
    "waits",
    "retries",
    "compactions",
    "reopen_count",
    "rework_count",
    "false_closure_count",
    "p0_p1_recall_ratio",
    "decision_changing_findings",
}
EFFICIENCY_METRICS = (
    "elapsed_time_ms",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "calls",
    "waits",
    "retries",
    "compactions",
)
QUALITY_METRICS = (
    "closure_quality_score",
    "required_coverage_ratio",
    "reopen_count",
    "rework_count",
    "false_closure_count",
    "p0_p1_recall_ratio",
    "decision_changing_findings",
)
SCORE_METRICS = {
    "closure_quality_score",
    "required_coverage_ratio",
    "p0_p1_recall_ratio",
}
POLICY_THRESHOLD_FIELDS = {
    "max_closure_quality_score_drop",
    "minimum_required_coverage_ratio",
    "max_reopen_count_increase",
    "max_rework_count_increase",
    "max_false_closure_count_increase",
    "minimum_p0_p1_recall_ratio",
    "minimum_decision_changing_findings_retention_ratio",
}
POLICY_FIELDS = {
    "schema_version",
    "policy_id",
    "thresholds",
    "synthetic_measured_claim_allowed",
    "policy_digest",
}
POLICY_BINDING_FIELDS = {"policy_id", "policy_digest"}
ATTESTATION_INDEX_FIELDS = {
    "schema_version",
    "trust_tier",
    "index_id",
    "evaluation_id",
    "producer",
    "records",
    "record_digest",
}
ATTESTATION_FIELDS = {
    "schema_version",
    "trust_tier",
    "attestation_id",
    "evaluation_id",
    "profile",
    "run_id",
    "workload_digest",
    "baseline_digest",
    "observed_at",
    "call_record_digests",
    "metrics_payload_digest",
    "producer",
    "record_digest",
}
PRODUCER_FIELDS = {"id", "kind"}
EXPECTED_POLICY_UNSIGNED = {
    "schema_version": "efficiency_evaluation_policy_v1",
    "policy_id": "gpt56_multi_agent_quality_noninferiority_v1",
    "thresholds": {
        "max_closure_quality_score_drop": 0.0,
        "minimum_required_coverage_ratio": 1.0,
        "max_reopen_count_increase": 0,
        "max_rework_count_increase": 0,
        "max_false_closure_count_increase": 0,
        "minimum_p0_p1_recall_ratio": 1.0,
        "minimum_decision_changing_findings_retention_ratio": 1.0,
    },
    "synthetic_measured_claim_allowed": False,
}
MEASUREMENT_STATUSES = {"synthetic", "measured", "partial", "unavailable"}
EVIDENCE_KINDS = {
    "synthetic_fixture",
    "platform_or_external_attested",
    "mixed",
}


class EfficiencyAttestationVerifier(Protocol):
    """Out-of-band host capability for one exact structural attestation index."""

    def verify_efficiency_attestation_index(
        self,
        *,
        index_digest: str,
        evaluation_id: str,
        run_ids: tuple[str, ...],
        call_record_digests: tuple[str, ...],
        metrics_payload_digests: tuple[str, ...],
        attestation_record_digests: tuple[str, ...],
    ) -> bool:
        """Return true only when the platform/external producer attested all bytes."""


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _attestation_index_schema() -> dict[str, Any]:
    return json.loads(
        ATTESTATION_INDEX_SCHEMA_PATH.read_text(encoding="utf-8")
    )


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def multi_agent_efficiency_evaluation_digest(record: dict[str, Any]) -> str:
    """Return the record's canonical self-integrity digest."""

    unsigned = {
        key: value for key, value in record.items() if key != "record_digest"
    }
    return "sha256:" + hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def efficiency_evaluation_policy_digest(policy: dict[str, Any]) -> str:
    """Return the canonical digest for one Registry quality policy."""

    unsigned = {
        key: value for key, value in policy.items() if key != "policy_digest"
    }
    return "sha256:" + hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def efficiency_attestation_index_digest(index: dict[str, Any]) -> str:
    """Return the structural index digest without conferring platform trust."""

    unsigned = {
        key: value for key, value in index.items() if key != "record_digest"
    }
    return "sha256:" + hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


@lru_cache(maxsize=1)
def _registry_efficiency_evaluation_policy() -> dict[str, Any]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    policy = registry.get("efficiency_evaluation_policy")
    if not isinstance(policy, dict):
        raise ValueError(
            "Registry-owned quality non-inferiority policy is unavailable"
        )
    return policy


def registry_efficiency_evaluation_policy_errors(
    registry: dict[str, Any],
) -> list[str]:
    """Validate the exact fail-closed quality gate owned by the Registry."""

    policy = registry.get("efficiency_evaluation_policy")
    if not isinstance(policy, dict) or set(policy) != POLICY_FIELDS:
        return [
            "efficiency_evaluation_policy must contain the exact "
            "efficiency_evaluation_policy_v1 fields"
        ]
    errors: list[str] = []
    thresholds = policy.get("thresholds")
    if not isinstance(thresholds, dict) or set(thresholds) != POLICY_THRESHOLD_FIELDS:
        errors.append(
            "efficiency_evaluation_policy.thresholds fields differ from authority"
        )
    unsigned = {
        key: value for key, value in policy.items() if key != "policy_digest"
    }
    if unsigned != EXPECTED_POLICY_UNSIGNED:
        errors.append(
            "efficiency_evaluation_policy must preserve zero quality-score "
            "drop, complete required coverage and P0/P1 recall, zero reopen "
            "increase, zero rework increase, zero false-closure increase, "
            "full decision-changing finding retention, and no synthetic "
            "measured claim"
        )
    try:
        expected_digest = efficiency_evaluation_policy_digest(policy)
    except (TypeError, ValueError):
        errors.append("efficiency_evaluation_policy is not canonical JSON")
    else:
        if policy.get("policy_digest") != expected_digest:
            errors.append(
                "efficiency_evaluation_policy.policy_digest differs from authority"
            )
    return errors


def _exact_fields(
    value: Any,
    expected: set[str],
    label: str,
    errors: list[str],
) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return False
    if set(value) != expected:
        errors.append(f"{label} fields differ from the contract")
        return False
    return True


def _complete_metrics(metrics: Any) -> bool:
    if not isinstance(metrics, dict) or set(metrics) != METRIC_FIELDS:
        return False
    for field, value in metrics.items():
        if value is None or isinstance(value, bool):
            return False
        if field in SCORE_METRICS:
            if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                return False
        elif not isinstance(value, int) or value < 0:
            return False
    return True


def _timestamp_is_aware(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def validate_efficiency_attestation_index(
    evaluation: Any,
    attestation_index: Any,
) -> list[str]:
    """Validate exact structural bindings without upgrading their trust tier."""

    if not isinstance(attestation_index, dict):
        return ["efficiency attestation index must be an object"]
    errors = [
        f"efficiency attestation index schema: {error}"
        for error in schema_subset_errors(
            attestation_index,
            _attestation_index_schema(),
        )
    ]
    if set(attestation_index) != ATTESTATION_INDEX_FIELDS:
        errors.append(
            "efficiency attestation index fields differ from the v1 contract"
        )
    if (
        attestation_index.get("schema_version")
        != "multi_agent_efficiency_attestation_index_v1"
    ):
        errors.append("efficiency attestation index schema_version is invalid")
    if (
        attestation_index.get("trust_tier")
        != "PLATFORM_OR_EXTERNAL_ATTESTED"
    ):
        errors.append(
            "efficiency attestation index trust_tier is not platform/external"
        )
    expected_index_digest: str | None = None
    try:
        expected_index_digest = efficiency_attestation_index_digest(
            attestation_index
        )
    except (TypeError, ValueError):
        errors.append("efficiency attestation index is not canonical JSON")
    if attestation_index.get("record_digest") != expected_index_digest:
        errors.append(
            "efficiency attestation index record_digest differs from content"
        )

    if not isinstance(evaluation, dict):
        errors.append("efficiency evaluation must be an object")
        return errors
    if attestation_index.get("evaluation_id") != evaluation.get("evaluation_id"):
        errors.append("efficiency attestation index evaluation_id differs")
    producer = attestation_index.get("producer")
    if (
        not isinstance(producer, dict)
        or set(producer) != PRODUCER_FIELDS
        or not isinstance(producer.get("id"), str)
        or not producer.get("id")
        or producer.get("kind") not in {"platform", "external"}
    ):
        errors.append("efficiency attestation index producer is invalid")

    profiles = evaluation.get("profiles")
    profile_by_ref: dict[str, dict[str, Any]] = {}
    if isinstance(profiles, list):
        for profile in profiles:
            if (
                isinstance(profile, dict)
                and profile.get("measurement_status") in {"measured", "partial"}
                and isinstance(profile.get("evidence_ref"), str)
            ):
                profile_by_ref[profile["evidence_ref"]] = profile
    records = attestation_index.get("records")
    if not isinstance(records, dict) or set(records) != set(profile_by_ref):
        errors.append(
            "efficiency attestation records must exactly cover measured/partial "
            "profile references"
        )
        return errors

    run_ids: list[str] = []
    call_digest_run_ids: dict[str, set[str]] = {}
    if any(not isinstance(reference, str) for reference in records):
        errors.append("efficiency attestation record keys must be strings")
        return errors
    for reference in sorted(records):
        attestation = records[reference]
        label = f"efficiency attestation records[{reference!r}]"
        if not isinstance(attestation, dict):
            errors.append(f"{label} must be an object")
            continue
        if set(attestation) != ATTESTATION_FIELDS:
            errors.append(f"{label} fields differ from the v1 contract")
        if (
            attestation.get("schema_version")
            != "multi_agent_efficiency_attestation_v1"
        ):
            errors.append(f"{label} schema_version is invalid")
        if attestation.get("trust_tier") != "PLATFORM_OR_EXTERNAL_ATTESTED":
            errors.append(f"{label} trust_tier is not platform/external")
        if attestation.get("attestation_id") != reference:
            errors.append(f"{label} attestation_id differs from index key")
        if attestation.get("evaluation_id") != evaluation.get("evaluation_id"):
            errors.append(f"{label} evaluation_id differs")
        profile = profile_by_ref[reference]
        for field in ("profile", "workload_digest", "baseline_digest"):
            if attestation.get(field) != profile.get(field):
                errors.append(f"{label} {field} differs from evaluation profile")
        if attestation.get("producer") != producer:
            errors.append(f"{label} producer differs from index producer")
        if not _timestamp_is_aware(attestation.get("observed_at")):
            errors.append(f"{label} observed_at is invalid")
        run_id = attestation.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            errors.append(f"{label} run_id must be immutable and non-empty")
        else:
            run_ids.append(run_id)
        call_digests = attestation.get("call_record_digests")
        if (
            not isinstance(call_digests, list)
            or not call_digests
            or not all(
                isinstance(digest, str)
                and digest.startswith("sha256:")
                and len(digest) == 71
                and all(character in "0123456789abcdef" for character in digest[7:])
                for digest in call_digests
            )
            or call_digests != sorted(set(call_digests))
        ):
            errors.append(
                f"{label} call_record_digests must be a sorted unique inventory"
            )
        elif isinstance(run_id, str) and run_id:
            for digest in call_digests:
                call_digest_run_ids.setdefault(digest, set()).add(run_id)
        try:
            expected_metrics_digest = (
                "sha256:"
                + hashlib.sha256(
                    _canonical_bytes(profile.get("metrics"))
                ).hexdigest()
            )
        except (TypeError, ValueError):
            expected_metrics_digest = None
            errors.append(f"{label} profile metrics are not canonical JSON")
        if attestation.get("metrics_payload_digest") != expected_metrics_digest:
            errors.append(f"{label} metrics payload digest differs")
        try:
            expected_attestation_digest = "sha256:" + hashlib.sha256(
                _canonical_bytes(
                    {
                        key: value
                        for key, value in attestation.items()
                        if key != "record_digest"
                    }
                )
            ).hexdigest()
        except (TypeError, ValueError):
            expected_attestation_digest = None
            errors.append(f"{label} is not canonical JSON")
        if attestation.get("record_digest") != expected_attestation_digest:
            errors.append(f"{label} record_digest differs from content")
        if profile.get("evidence_digest") != attestation.get("record_digest"):
            errors.append(f"{label} digest differs from evaluation profile")
    if len(run_ids) != len(set(run_ids)):
        errors.append("efficiency attestation run_id values must be unique")
    if any(len(owners) > 1 for owners in call_digest_run_ids.values()):
        errors.append(
            "call_record_digest values cannot be reused across run_id values"
        )
    return errors


def _profile_errors(
    profile: Any,
    *,
    index: int,
    workload_digest: Any,
    baseline_digest: Any,
    evidence_kind: Any,
) -> list[str]:
    label = f"profiles[{index}]"
    errors: list[str] = []
    if not _exact_fields(profile, PROFILE_FIELDS, label, errors):
        if not isinstance(profile, dict):
            return errors

    if profile.get("workload_digest") != workload_digest:
        errors.append(f"{label} must bind the same workload")
    if profile.get("baseline_digest") != baseline_digest:
        errors.append(f"{label} must bind the same baseline")

    status = profile.get("measurement_status")
    if status not in MEASUREMENT_STATUSES:
        errors.append(f"{label} measurement_status is invalid")
        return errors

    metrics = profile.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != METRIC_FIELDS:
        errors.append(f"{label} metric fields differ from the contract")
        return errors

    evidence_ref = profile.get("evidence_ref")
    evidence_digest = profile.get("evidence_digest")
    unavailable_reason = profile.get("unavailable_reason")
    if status == "synthetic":
        if not _complete_metrics(metrics):
            errors.append(f"{label} synthetic profile requires every metric")
        if any(
            value is not None
            for value in (evidence_ref, evidence_digest, unavailable_reason)
        ):
            errors.append(
                f"{label} synthetic profile cannot claim evidence or unavailability"
            )
    elif status == "measured":
        if not _complete_metrics(metrics):
            errors.append(f"{label} measured profile requires every metric")
        if unavailable_reason is not None:
            errors.append(f"{label} measured profile cannot be unavailable")
        if (
            not isinstance(evidence_ref, str)
            or not evidence_ref
        ):
            errors.append(
                f"{label} measured profile requires a non-empty evidence ref"
            )
    elif status == "partial":
        values = list(metrics.values())
        if not any(value is None for value in values) or not any(
            value is not None for value in values
        ):
            errors.append(
                f"{label} partial profile requires both known and null metrics"
            )
        if not isinstance(unavailable_reason, str) or not unavailable_reason.strip():
            errors.append(f"{label} partial profile requires an unavailable reason")
        if (
            not isinstance(evidence_ref, str)
            or not evidence_ref
        ):
            errors.append(
                f"{label} partial profile requires a non-empty evidence ref"
            )
    else:
        if any(value is not None for value in metrics.values()):
            errors.append(f"{label} unavailable profile metrics must all be null")
        if evidence_ref is not None or evidence_digest is not None:
            errors.append(f"{label} unavailable profile cannot claim evidence")
        if not isinstance(unavailable_reason, str) or not unavailable_reason.strip():
            errors.append(
                f"{label} unavailable profile requires an unavailable reason"
            )

    if evidence_kind == "synthetic_fixture" and status != "synthetic":
        errors.append("synthetic fixture profiles must remain synthetic")
    if evidence_kind == "platform_or_external_attested" and status == "synthetic":
        errors.append(
            "platform/external-attested evaluation cannot contain synthetic profiles"
        )
    return errors


def validate_multi_agent_efficiency_evaluation(
    record: Any,
    *,
    attested_evidence_refs: Iterable[str] | None = None,
    attestation_index: Any = None,
) -> list[str]:
    """Validate structure without trusting evidence labels or free-form refs.

    ``attested_evidence_refs`` remains an ignored compatibility parameter; only
    a structurally bound ``attestation_index`` can become a verifier candidate.
    """

    if not isinstance(record, dict):
        return ["multi-agent efficiency evaluation must be an object"]
    errors = [
        f"evaluation schema: {error}"
        for error in schema_subset_errors(record, _schema())
    ]
    _exact_fields(record, RECORD_FIELDS, "evaluation", errors)
    if "quality_noninferiority_gate" in record:
        errors.append(
            "evaluation cannot carry free thresholds; it must reference the "
            "Registry-owned quality non-inferiority policy"
        )

    workload = record.get("workload")
    baseline = record.get("baseline")
    _exact_fields(workload, WORKLOAD_FIELDS, "workload", errors)
    _exact_fields(baseline, BASELINE_FIELDS, "baseline", errors)
    workload_digest = (
        workload.get("workload_digest") if isinstance(workload, dict) else None
    )
    baseline_digest = (
        baseline.get("baseline_digest") if isinstance(baseline, dict) else None
    )
    if isinstance(baseline, dict) and baseline.get("profile") != "current":
        errors.append("baseline profile must be current")

    policy_errors = registry_efficiency_evaluation_policy_errors(
        json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    )
    errors.extend(
        f"Registry-owned quality non-inferiority policy: {error}"
        for error in policy_errors
    )
    policy_binding = record.get("quality_noninferiority_policy")
    if _exact_fields(
        policy_binding,
        POLICY_BINDING_FIELDS,
        "quality_noninferiority_policy",
        errors,
    ):
        authority = _registry_efficiency_evaluation_policy()
        if (
            policy_binding.get("policy_id") != authority.get("policy_id")
            or policy_binding.get("policy_digest") != authority.get("policy_digest")
        ):
            errors.append(
                "quality_noninferiority_policy must bind the exact "
                "Registry-owned quality non-inferiority policy"
            )

    evidence_kind = record.get("evidence_kind")
    if evidence_kind not in EVIDENCE_KINDS:
        errors.append("evidence_kind is invalid")
    profiles = record.get("profiles")
    if not isinstance(profiles, list):
        errors.append("profiles must be an array")
        profiles = []
    names = [
        profile.get("profile")
        for profile in profiles
        if isinstance(profile, dict)
    ]
    if len(profiles) != 3 or set(names) != PROFILE_NAMES or len(names) != 3:
        errors.append(
            "profiles must contain exactly one current, single_agent, and bounded_role"
        )
    for index, profile in enumerate(profiles):
        errors.extend(
            _profile_errors(
                profile,
                index=index,
                workload_digest=workload_digest,
                baseline_digest=baseline_digest,
                evidence_kind=evidence_kind,
            )
        )

    evidence_refs = [
        profile.get("evidence_ref")
        for profile in profiles
        if isinstance(profile, dict)
        and isinstance(profile.get("evidence_ref"), str)
    ]
    if len(evidence_refs) != len(set(evidence_refs)):
        errors.append("profile evidence refs must be unique")

    limitations = record.get("limitations")
    if (
        evidence_kind == "synthetic_fixture"
        and isinstance(limitations, list)
        and not any(
            isinstance(item, str)
            and "synthetic" in item.lower()
            and "measured" in item.lower()
            for item in limitations
        )
    ):
        errors.append(
            "synthetic fixture must state that it is not measured evidence"
        )

    try:
        expected_digest = multi_agent_efficiency_evaluation_digest(record)
    except (TypeError, ValueError):
        errors.append("evaluation is not canonical JSON")
    else:
        if record.get("record_digest") != expected_digest:
            errors.append("record_digest differs from canonical evaluation content")
    if attestation_index is not None:
        errors.extend(
            validate_efficiency_attestation_index(record, attestation_index)
        )
    return errors


def _ratio(candidate: Any, baseline: Any) -> float | None:
    if (
        not isinstance(candidate, (int, float))
        or isinstance(candidate, bool)
        or not isinstance(baseline, (int, float))
        or isinstance(baseline, bool)
    ):
        return None
    if baseline == 0:
        return 1.0 if candidate == 0 else None
    return round(candidate / baseline, 6)


def _quality_noninferiority(
    baseline_metrics: dict[str, Any],
    candidate_metrics: dict[str, Any],
    gate: dict[str, Any],
) -> dict[str, Any]:
    if any(
        baseline_metrics.get(field) is None
        or candidate_metrics.get(field) is None
        for field in QUALITY_METRICS
    ):
        return {
            "status": "UNAVAILABLE",
            "checks": {
                field: {
                    "status": "UNAVAILABLE",
                    "baseline": baseline_metrics.get(field),
                    "candidate": candidate_metrics.get(field),
                    "threshold": None,
                }
                for field in QUALITY_METRICS
            },
        }

    minimum_quality = max(
        0.0,
        baseline_metrics["closure_quality_score"]
        - gate["max_closure_quality_score_drop"],
    )
    minimum_required_coverage = gate["minimum_required_coverage_ratio"]
    maximum_reopens = (
        baseline_metrics["reopen_count"] + gate["max_reopen_count_increase"]
    )
    maximum_rework = (
        baseline_metrics["rework_count"] + gate["max_rework_count_increase"]
    )
    maximum_false_closures = (
        baseline_metrics["false_closure_count"]
        + gate["max_false_closure_count_increase"]
    )
    minimum_p0_p1_recall = gate["minimum_p0_p1_recall_ratio"]
    minimum_findings = math.ceil(
        baseline_metrics["decision_changing_findings"]
        * gate["minimum_decision_changing_findings_retention_ratio"]
    )
    checks = {
        "closure_quality_score": {
            "status": (
                "PASS"
                if candidate_metrics["closure_quality_score"] >= minimum_quality
                else "FAIL"
            ),
            "baseline": baseline_metrics["closure_quality_score"],
            "candidate": candidate_metrics["closure_quality_score"],
            "threshold": round(minimum_quality, 6),
        },
        "required_coverage_ratio": {
            "status": (
                "PASS"
                if candidate_metrics["required_coverage_ratio"]
                >= minimum_required_coverage
                else "FAIL"
            ),
            "baseline": baseline_metrics["required_coverage_ratio"],
            "candidate": candidate_metrics["required_coverage_ratio"],
            "threshold": minimum_required_coverage,
        },
        "reopen_count": {
            "status": (
                "PASS"
                if candidate_metrics["reopen_count"] <= maximum_reopens
                else "FAIL"
            ),
            "baseline": baseline_metrics["reopen_count"],
            "candidate": candidate_metrics["reopen_count"],
            "threshold": maximum_reopens,
        },
        "rework_count": {
            "status": (
                "PASS"
                if candidate_metrics["rework_count"] <= maximum_rework
                else "FAIL"
            ),
            "baseline": baseline_metrics["rework_count"],
            "candidate": candidate_metrics["rework_count"],
            "threshold": maximum_rework,
        },
        "false_closure_count": {
            "status": (
                "PASS"
                if candidate_metrics["false_closure_count"]
                <= maximum_false_closures
                else "FAIL"
            ),
            "baseline": baseline_metrics["false_closure_count"],
            "candidate": candidate_metrics["false_closure_count"],
            "threshold": maximum_false_closures,
        },
        "p0_p1_recall_ratio": {
            "status": (
                "PASS"
                if candidate_metrics["p0_p1_recall_ratio"]
                >= minimum_p0_p1_recall
                else "FAIL"
            ),
            "baseline": baseline_metrics["p0_p1_recall_ratio"],
            "candidate": candidate_metrics["p0_p1_recall_ratio"],
            "threshold": minimum_p0_p1_recall,
        },
        "decision_changing_findings": {
            "status": (
                "PASS"
                if candidate_metrics["decision_changing_findings"]
                >= minimum_findings
                else "FAIL"
            ),
            "baseline": baseline_metrics["decision_changing_findings"],
            "candidate": candidate_metrics["decision_changing_findings"],
            "threshold": minimum_findings,
        },
    }
    return {
        "status": (
            "PASS"
            if all(check["status"] == "PASS" for check in checks.values())
            else "FAIL"
        ),
        "checks": checks,
    }


def evaluate_multi_agent_efficiency(
    record: dict[str, Any],
    *,
    attested_evidence_refs: Iterable[str] | None = None,
    attestation_index: Any = None,
    attestation_verifier: EfficiencyAttestationVerifier | None = None,
) -> dict[str, Any]:
    """Evaluate quality first, then require out-of-band attestation trust."""

    errors = validate_multi_agent_efficiency_evaluation(
        record,
        attested_evidence_refs=attested_evidence_refs,
        attestation_index=attestation_index,
    )
    if errors:
        raise ValueError("; ".join(errors))

    profiles = {item["profile"]: item for item in record["profiles"]}
    baseline = profiles["current"]
    quality_policy = _registry_efficiency_evaluation_policy()
    statuses = {profile["measurement_status"] for profile in profiles.values()}
    all_measured = False
    if (
        statuses == {"measured"}
        and record["evidence_kind"] == "platform_or_external_attested"
        and isinstance(attestation_index, dict)
        and attestation_verifier is not None
    ):
        attestations = attestation_index["records"].values()
        binding = {
            "index_digest": attestation_index["record_digest"],
            "evaluation_id": record["evaluation_id"],
            "run_ids": tuple(
                sorted(attestation["run_id"] for attestation in attestations)
            ),
            "call_record_digests": tuple(
                sorted(
                    {
                        digest
                        for attestation in attestations
                        for digest in attestation["call_record_digests"]
                    }
                )
            ),
            "metrics_payload_digests": tuple(
                sorted(
                    attestation["metrics_payload_digest"]
                    for attestation in attestations
                )
            ),
            "attestation_record_digests": tuple(
                sorted(
                    attestation["record_digest"]
                    for attestation in attestations
                )
            ),
        }
        try:
            all_measured = (
                attestation_verifier.verify_efficiency_attestation_index(
                    **binding
                )
                is True
            )
        except Exception:  # noqa: BLE001 - verifier failure is fail-closed
            all_measured = False
    if statuses == {"synthetic"}:
        measurement_status = "synthetic"
    elif statuses == {"measured"}:
        measurement_status = "measured" if all_measured else "external_limit"
    elif statuses == {"unavailable"}:
        measurement_status = "unavailable"
    else:
        measurement_status = "partial"

    comparisons: dict[str, Any] = {}
    for name in ("single_agent", "bounded_role"):
        candidate = profiles[name]
        quality = _quality_noninferiority(
            baseline["metrics"],
            candidate["metrics"],
            quality_policy["thresholds"],
        )
        ratios = {
            metric: _ratio(
                candidate["metrics"].get(metric),
                baseline["metrics"].get(metric),
            )
            for metric in EFFICIENCY_METRICS
        }
        comparisons[name] = {
            "measurement_status": candidate["measurement_status"],
            "quality_noninferiority": quality,
            "efficiency_ratios": ratios,
            "efficiency_claim_allowed": (
                all_measured and quality["status"] == "PASS"
            ),
        }

    benchmark_only = sorted(
        name
        for name, comparison in comparisons.items()
        if comparison["measurement_status"] == "synthetic"
        and comparison["quality_noninferiority"]["status"] == "PASS"
    )
    measured_candidates = sorted(
        name
        for name, comparison in comparisons.items()
        if comparison["efficiency_claim_allowed"]
    )
    if measurement_status == "synthetic":
        adoption_verdict = "SYNTHETIC_ONLY_NO_MEASURED_CLAIM"
    elif measurement_status == "measured":
        adoption_verdict = "MEASURED_COMPARISON_AVAILABLE"
    elif measurement_status == "external_limit":
        adoption_verdict = "EXTERNAL_LIMIT_PLATFORM_ATTESTATION_UNVERIFIED"
    else:
        adoption_verdict = "MEASUREMENT_INCOMPLETE"
    return {
        "schema_version": "multi_agent_efficiency_evaluation_result_v1",
        "evaluation_id": record["evaluation_id"],
        "workload_digest": record["workload"]["workload_digest"],
        "baseline_digest": record["baseline"]["baseline_digest"],
        "baseline_profile": "current",
        "baseline_metrics": baseline["metrics"],
        "attestation_index_digest": (
            attestation_index.get("record_digest")
            if isinstance(attestation_index, dict)
            else None
        ),
        "attestation_verification_status": (
            "verified"
            if all_measured
            else (
                "external_limit"
                if statuses == {"measured"}
                else "not_applicable"
            )
        ),
        "quality_noninferiority_policy": record[
            "quality_noninferiority_policy"
        ],
        "measurement_status": measurement_status,
        "measured_claim_allowed": all_measured,
        "adoption_verdict": adoption_verdict,
        "comparisons": comparisons,
        "benchmark_only_candidates": benchmark_only,
        "measured_efficiency_candidates": measured_candidates,
        "limitations": record["limitations"],
    }


def _load_json_arg(raw: str) -> Any:
    path = Path(raw[1:] if raw.startswith("@") else raw)
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate one multi_agent_efficiency_evaluation_v1 record"
    )
    parser.add_argument("evaluation", help="JSON path, optionally prefixed by @")
    parser.add_argument(
        "--attestation-index",
        help=(
            "typed attestation-index JSON path, optionally prefixed by @; "
            "standalone CLI has no trusted-host verifier and remains EXTERNAL_LIMIT"
        ),
    )
    args = parser.parse_args(argv)
    try:
        record = _load_json_arg(args.evaluation)
        result = evaluate_multi_agent_efficiency(
            record,
            attestation_index=(
                _load_json_arg(args.attestation_index)
                if args.attestation_index
                else None
            ),
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": (
                        "multi_agent_efficiency_evaluation_result_v1"
                    ),
                    "measurement_status": "invalid",
                    "errors": [str(exc)],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
