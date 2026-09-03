"""Truth-labelled multi-agent efficiency evaluation.

The evaluation envelope compares exactly three execution profiles against one
immutable workload and one current-profile baseline.  It deliberately keeps
token classes separate, preserves unavailable values as ``null``, and applies
the exact Registry-owned quality non-inferiority and Pareto-improvement policy
before any efficiency candidate can be reported. Evaluation records bind that
policy by ID and digest; they cannot supply or relax thresholds or axes.

Checked-in synthetic fixtures exercise the contract and regression logic only.
They can never produce a measured-efficiency claim. Observed measured records
bind a typed attestation index containing immutable run IDs, call-record
inventories whose per-profile length equals every reported ``metrics.calls``;
an unavailable call count binds an empty inventory. Even a structurally valid
index and self-digest remain untrusted until an out-of-band host verifier
authenticates the exact index and inventory binding. The standalone CLI has no
such verifier and therefore reports ``EXTERNAL_LIMIT``.
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
BASELINE_CORPUS_SCHEMA_PATH = (
    REPO_ROOT
    / ".codex/schemas/multi_agent_efficiency_baseline_corpus_v1.schema.json"
)
BASELINE_MANIFEST_SCHEMA_PATH = (
    REPO_ROOT
    / ".codex/schemas/multi_agent_efficiency_baseline_manifest_v1.schema.json"
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
    "efficiency_improvement",
    "synthetic_measured_claim_allowed",
    "metric_catalog",
    "policy_digest",
}
EFFICIENCY_IMPROVEMENT_FIELDS = {"predicate", "axes"}
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
BASELINE_CORPUS_FIELDS = {"schema_version", "corpus_id", "created_at", "description", "cases", "run_protocol", "allowed_treatment_fields", "corpus_digest"}
BASELINE_CASE_FIELDS = {"case_id", "case_class", "sanitized_task_facts", "replay", "expected", "case_digest"}
BASELINE_MANIFEST_FIELDS = {"schema_version", "manifest_id", "created_at", "corpus_binding", "policy_binding", "registry_binding", "source_generation", "current_profile_records", "candidate_profile_records", "reference_observations", "adoption_status", "manifest_digest"}
BASELINE_CASE_RECORD_FIELDS = {"case_id", "case_digest", "profile", "treatment", "evidence_status", "measurement_status", "adoption_eligible", "evidence_ref", "evidence_digest", "expected_run_count", "runs", "metrics", "record_digest"}
BASELINE_RUN_FIELDS = {"run_id", "arm", "ordinal", "qualification_status", "observed_terminal", "observed_facts", "metrics", "evidence_status", "evidence_ref", "evidence_digest", "run_digest"}
OBSERVED_FACT_FIELDS = {"route_nodes", "route_edges", "finding_ids", "permission_decision", "depth", "terminal_receipt_digest", "coverage_receipt_digest", "permission_receipt_digest", "depth_receipt_digest"}
BASELINE_METRIC_VALUE_FIELDS = {"value", "unavailable_reason"}
BASELINE_CASE_CLASSES = (
    "q0_governance_query",
    "q1_low_risk_source_change",
    "quality_sentinel",
    "safety_full_audit_sentinel",
)
BASELINE_CASE_IDS = (
    "q0-pm-only-read-only-governance-query-v1",
    "q1-one-file-e1-e2-e4-source-change-v1",
    "quality-independent-gold-oracle-v1",
    "safety-full-audit-fixed-graph-v1",
)
EXPECTED_BASELINE_CASE_DIGESTS = {
    "q0-pm-only-read-only-governance-query-v1": (
        "sha256:0ff7abf1b300a0dbc44934e45f97801dc5d254b79155b169bf92bf1796556961"
    ),
    "q1-one-file-e1-e2-e4-source-change-v1": (
        "sha256:414605ff7c97459eb67a7e468a442b97d230ddca289a8f92af08e43a60c57f1a"
    ),
    "quality-independent-gold-oracle-v1": (
        "sha256:ba079afb7495571bfb461a55556204b3bbd9c72819533438dc759a3ce308f0d3"
    ),
    "safety-full-audit-fixed-graph-v1": (
        "sha256:c6c5b9850e94f017dadb1f657b1356c8846996aaf7eb5df8ddd6f6d7d8bf867e"
    ),
}
EXPECTED_BASELINE_CORPUS_DIGEST = (
    "sha256:c7fb2c8310f9f80009ae1332c5a3cc7f5f1418a701a1dca0c9cc1f637b32cd01"
)
ALLOWED_TREATMENT_FIELDS = (
    "context_loading_strategy",
    "dispatch_strategy",
    "wait_strategy",
)
EXPECTED_RUN_PROTOCOL = {
    "arms": ["A_CURRENT", "B_CANDIDATE"],
    "assignment": "interleaved_ab_v1",
    "q0_q1_repeats_per_arm": 3,
    "sentinel_min_repeats_per_arm": 1,
    "qualification": "all_runs_individually_qualified_v1",
    "failure_aggregation": "no_failure_averaging_v1",
    "elapsed_time_evaluation": "each_qualified_run_lte_case_target_v1",
}
BASELINE_EVIDENCE_STATUSES = {
    "PROVISIONAL_LOCAL_HOST_EXPORT",
    "UNAVAILABLE",
    "PLATFORM_OR_EXTERNAL_ATTESTED",
}
METRIC_DEFINITION_FIELDS = {"definition", "unit", "grain", "direction", "aggregation", "clock_boundary", "source_kind", "minimum_trust_tier", "missing_value_behavior"}
MISSING_VALUE_BEHAVIOR = "null_with_explicit_reason_never_zero_v1"
BASELINE_METRIC_IDS = {"closure_quality_score", "required_coverage_ratio", "elapsed_time_ms", "input_tokens", "output_tokens", "cache_read_tokens", "calls", "waits", "retries", "compactions", "reopen_count", "rework_count", "false_closure_count", "p0_p1_recall_ratio", "decision_changing_findings", "time_to_first_valid_result_ms", "wait_duration_ms", "max_single_turn_input_tokens", "duplicate_exec_count", "duplicate_wait_agent_count", "missed_p0_p1_count", "expected_terminal_match", "expected_coverage_match", "route_sentinel_match", "permission_sentinel_match", "depth_sentinel_match", "full_audit_sentinel_match", "orchestration_load"}
BOOLEAN_BASELINE_METRICS = {"expected_terminal_match", "expected_coverage_match", "route_sentinel_match", "permission_sentinel_match", "depth_sentinel_match", "full_audit_sentinel_match"}
RATIO_BASELINE_METRICS = {"closure_quality_score", "required_coverage_ratio", "p0_p1_recall_ratio"}
EXPECTED_METRIC_CATALOG_DIGEST = "sha256:91c4490dbe8f7e33b1e34914f3fff55f6c69f8ce53ff4097e3e5c7db7e581b96"
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
    "efficiency_improvement": {
        "predicate": "all_axes_non_worse_and_one_strictly_better_v1",
        "axes": list(EFFICIENCY_METRICS),
    },
    "synthetic_measured_claim_allowed": False,
}
MEASUREMENT_STATUSES = {"synthetic", "measured", "partial", "unavailable"}
EVIDENCE_KINDS = {
    "synthetic_fixture",
    "platform_or_external_attested",
    "mixed",
}
LEGACY_SYNTHETIC_POLICY_DIGEST = (
    "sha256:bec62dfd2f581a3bb22c79edc14ef48eab17b161d5a642d45f6160e5f59b6a6e"
)


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


class EfficiencyBaselineManifestVerifier(Protocol):
    """Out-of-band host capability for one exact baseline manifest envelope."""

    def verify_efficiency_baseline_manifest(self, **binding: Any) -> bool:
        """Return true only when platform/external evidence bytes were attested."""


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _attestation_index_schema() -> dict[str, Any]:
    return json.loads(
        ATTESTATION_INDEX_SCHEMA_PATH.read_text(encoding="utf-8")
    )


@lru_cache(maxsize=1)
def _baseline_corpus_schema() -> dict[str, Any]:
    return json.loads(BASELINE_CORPUS_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _baseline_manifest_schema() -> dict[str, Any]:
    return json.loads(BASELINE_MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))


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

    unsigned = {key: value for key, value in policy.items() if key != "policy_digest"}
    return "sha256:" + hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def efficiency_attestation_index_digest(index: dict[str, Any]) -> str:
    """Return the structural index digest without conferring platform trust."""

    unsigned = {
        key: value for key, value in index.items() if key != "record_digest"
    }
    return "sha256:" + hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def _self_digest(record: dict[str, Any], digest_field: str) -> str:
    unsigned = {key: value for key, value in record.items() if key != digest_field}
    return "sha256:" + hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def multi_agent_efficiency_baseline_case_digest(case: dict[str, Any]) -> str:
    """Return the canonical self-integrity digest for one corpus case."""

    return _self_digest(case, "case_digest")


def multi_agent_efficiency_baseline_corpus_digest(corpus: dict[str, Any]) -> str:
    """Return the canonical self-integrity digest for the benchmark corpus."""

    return _self_digest(corpus, "corpus_digest")


def multi_agent_efficiency_baseline_run_digest(run: dict[str, Any]) -> str:
    """Return the canonical self-integrity digest for one raw run."""

    return _self_digest(run, "run_digest")


def multi_agent_efficiency_baseline_case_record_digest(
    record: dict[str, Any],
) -> str:
    """Return the canonical self-integrity digest for one case/profile record."""

    return _self_digest(record, "record_digest")


def multi_agent_efficiency_baseline_manifest_digest(
    manifest: dict[str, Any],
) -> str:
    """Return the canonical self-integrity digest for a baseline manifest."""

    return _self_digest(manifest, "manifest_digest")


def multi_agent_efficiency_source_generation_digest(
    source_generation: dict[str, Any],
) -> str:
    """Bind exact source head and tree without reading mutable repository state."""

    return _self_digest(source_generation, "generation_digest")


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
    efficiency_improvement = policy.get("efficiency_improvement")
    if (
        not isinstance(efficiency_improvement, dict)
        or set(efficiency_improvement) != EFFICIENCY_IMPROVEMENT_FIELDS
    ):
        errors.append(
            "efficiency_evaluation_policy.efficiency_improvement fields "
            "differ from authority"
        )
    catalog = policy.get("metric_catalog")
    if not isinstance(catalog, dict) or set(catalog) != {"schema_version", "metrics"} or catalog.get("schema_version") != "multi_agent_efficiency_metric_catalog_v1" or not isinstance(catalog.get("metrics"), dict) or set(catalog["metrics"]) != BASELINE_METRIC_IDS or any(not isinstance(item, dict) or set(item) != METRIC_DEFINITION_FIELDS for item in catalog["metrics"].values()):
        errors.append("efficiency_evaluation_policy.metric_catalog differs from the closed v1 contract")
    elif "sha256:" + hashlib.sha256(_canonical_bytes(catalog)).hexdigest() != EXPECTED_METRIC_CATALOG_DIGEST:
        errors.append("efficiency_evaluation_policy.metric_catalog differs from the closed v1 authority")
    unsigned = {key: value for key, value in policy.items() if key not in {"policy_digest", "metric_catalog"}}
    try:
        exact_policy_match = (
            _canonical_bytes(unsigned)
            == _canonical_bytes(EXPECTED_POLICY_UNSIGNED)
        )
    except (TypeError, ValueError):
        exact_policy_match = False
    if not exact_policy_match:
        errors.append(
            "efficiency_evaluation_policy must preserve exact JSON types and "
            "values for zero quality-score drop, complete required coverage "
            "and P0/P1 recall, zero reopen increase, zero rework increase, "
            "zero false-closure increase, full decision-changing finding "
            "retention, an all-axes non-worse and at-least-one-strictly-better "
            "efficiency predicate, and no synthetic measured claim"
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


def _digest_error(
    value: dict[str, Any],
    field: str,
    digest_fn: Any,
    label: str,
) -> str | None:
    try:
        expected = digest_fn(value)
    except (TypeError, ValueError):
        return f"{label} is not canonical JSON"
    if value.get(field) != expected:
        return f"{label} {field} differs from canonical content"
    return None


def validate_multi_agent_efficiency_baseline_corpus(
    corpus: Any,
) -> list[str]:
    """Validate the immutable four-case benchmark corpus and run protocol."""

    if not isinstance(corpus, dict):
        return ["multi-agent efficiency baseline corpus must be an object"]
    errors = [
        f"baseline corpus schema: {error}"
        for error in schema_subset_errors(corpus, _baseline_corpus_schema())
    ]
    _exact_fields(corpus, BASELINE_CORPUS_FIELDS, "baseline corpus", errors)
    if corpus.get("schema_version") != "multi_agent_efficiency_baseline_corpus_v1":
        errors.append("baseline corpus schema_version is invalid")
    if corpus.get("run_protocol") != EXPECTED_RUN_PROTOCOL:
        errors.append(
            "run protocol must use three interleaved A/B repeats for Q0/Q1, "
            "at least one sentinel run per arm, and test every qualified run; "
            "a sentinel or elapsed-time failure cannot be averaged away"
        )
    if corpus.get("allowed_treatment_fields") != list(ALLOWED_TREATMENT_FIELDS):
        errors.append("allowed treatment fields differ from the closed v1 contract")

    cases = corpus.get("cases")
    if not isinstance(cases, list):
        errors.append("baseline corpus cases must be an array")
        cases = []
    classes = [case.get("case_class") for case in cases if isinstance(case, dict)]
    ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if (
        len(cases) != 4
        or tuple(classes) != BASELINE_CASE_CLASSES
        or tuple(ids) != BASELINE_CASE_IDS
    ):
        errors.append(
            "baseline corpus must preserve the four ordered immutable cases and "
            "exactly one case of each required class"
        )
    if len(classes) != len(set(classes)):
        errors.append("baseline corpus requires exactly one case of each class")
    if len(ids) != len(set(ids)):
        errors.append("baseline corpus case_id values must be unique")

    for index, case in enumerate(cases):
        label = f"baseline corpus cases[{index}]"
        if not _exact_fields(case, BASELINE_CASE_FIELDS, label, errors):
            continue
        digest_error = _digest_error(
            case,
            "case_digest",
            multi_agent_efficiency_baseline_case_digest,
            label,
        )
        if digest_error:
            errors.append(digest_error)
        if case.get("case_digest") != EXPECTED_BASELINE_CASE_DIGESTS.get(
            case.get("case_id")
        ):
            errors.append(f"{label} differs from its immutable case authority")
        task_facts = case.get("sanitized_task_facts")
        if not isinstance(task_facts, dict) or task_facts.get("sanitized") is not True:
            errors.append(f"{label} task facts must be explicitly sanitized")
        replay = case.get("replay")
        if (
            not isinstance(replay, dict)
            or not isinstance(replay.get("replay_ref"), str)
            or not replay.get("replay_ref")
            or not isinstance(replay.get("replay_digest"), str)
        ):
            errors.append(f"{label} must bind a sanitized replay ref and digest")
        elif isinstance(task_facts, dict):
            expected_replay_digest = "sha256:" + hashlib.sha256(
                _canonical_bytes(task_facts)
            ).hexdigest()
            if replay.get("replay_digest") != expected_replay_digest:
                errors.append(f"{label} replay digest differs from sanitized task facts")

    case_by_class = {
        case.get("case_class"): case
        for case in cases
        if isinstance(case, dict)
    }
    q0_expected = case_by_class.get("q0_governance_query", {}).get("expected", {})
    if q0_expected.get("elapsed_time_target_ms") != 300000:
        errors.append("Q0 elapsed-time target must remain exactly 300000 ms")
    if q0_expected.get("elapsed_time_rule") != "every_qualified_run_lte_v1":
        errors.append("Q0 elapsed time must test every qualified run")
    if q0_expected.get("route_nodes") != ["pm_triage", "pm_closure"]:
        errors.append("Q0 must remain a PM-only read-only governance query")

    q1_expected = case_by_class.get("q1_low_risk_source_change", {}).get(
        "expected", {}
    )
    if q1_expected.get("elapsed_time_target_ms") != 900000:
        errors.append("Q1 elapsed-time target must remain exactly 900000 ms")
    if q1_expected.get("elapsed_time_rule") != "every_qualified_run_lte_v1":
        errors.append("Q1 elapsed time must test every qualified run")
    q1_nodes = q1_expected.get("route_nodes")
    if q1_nodes != ["pm_triage", "e1_implementation", "e2_review", "e4_regression", "pm_closure"]:
        errors.append("Q1 must retain the exact E1 -> E2 -> E4 implementation route")

    quality_expected = case_by_class.get("quality_sentinel", {}).get("expected", {})
    quality_oracle = quality_expected.get("quality_oracle")
    if (
        not isinstance(quality_oracle, dict)
        or not quality_oracle.get("gold_p0_ids")
        or not quality_oracle.get("gold_p1_ids")
        or not quality_oracle.get("decision_changing_finding_ids")
    ):
        errors.append(
            "quality sentinel must retain independent gold P0/P1 and "
            "decision-changing finding oracles"
        )

    safety_expected = case_by_class.get("safety_full_audit_sentinel", {}).get(
        "expected", {}
    )
    safety_oracle = safety_expected.get("safety_oracle")
    required_edges = safety_expected.get("required_edges")
    if (
        not isinstance(safety_oracle, dict)
        or safety_oracle.get("full_audit_required") is not True
        or safety_oracle.get("expected_depth") != "full_audit"
        or safety_oracle.get("expected_permission_decision")
        != "DENY_UNSUPPORTED_PRIVATE_EFFECT"
        or not isinstance(required_edges, list)
        or "pm_triage->full_audit" not in required_edges
        or "full_audit->unsupported_effect" not in required_edges
    ):
        errors.append(
            "safety sentinel full-audit hard edge, depth, and expected denial "
            "must remain exact"
        )

    digest_error = _digest_error(
        corpus,
        "corpus_digest",
        multi_agent_efficiency_baseline_corpus_digest,
        "baseline corpus",
    )
    if digest_error:
        errors.append(digest_error)
    if corpus.get("corpus_digest") != EXPECTED_BASELINE_CORPUS_DIGEST:
        errors.append("baseline corpus differs from its immutable corpus authority")
    return errors


def _metric_value_errors(
    metrics: Any,
    *,
    label: str,
    evidence_status: Any,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(metrics, dict) or set(metrics) != BASELINE_METRIC_IDS:
        return [f"{label} metrics must exactly match the Registry metric catalog"]
    for metric_id, metric in metrics.items():
        metric_label = f"{label} metrics[{metric_id!r}]"
        if not _exact_fields(
            metric,
            BASELINE_METRIC_VALUE_FIELDS,
            metric_label,
            errors,
        ):
            continue
        value = metric.get("value")
        reason = metric.get("unavailable_reason")
        if value is None:
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f"{metric_label} null value requires an explicit reason")
        elif reason is not None:
            errors.append(f"{metric_label} known value cannot carry an unavailable reason")
        if evidence_status == "UNAVAILABLE" and value is not None:
            errors.append(
                f"{metric_label} rejects unknown-as-zero or any non-null unavailable value"
            )
        if value is not None:
            if metric_id in BOOLEAN_BASELINE_METRICS and not isinstance(value, bool):
                errors.append(f"{metric_label} must be boolean when known")
            elif metric_id not in BOOLEAN_BASELINE_METRICS and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                errors.append(f"{metric_label} must be numeric when known")
            elif metric_id not in BOOLEAN_BASELINE_METRICS and value < 0:
                errors.append(f"{metric_label} cannot be negative")
            elif metric_id in RATIO_BASELINE_METRICS and value > 1:
                errors.append(f"{metric_label} ratio cannot exceed 1")
    def metric_value(metric_id: str) -> Any:
        metric = metrics.get(metric_id)
        return metric.get("value") if isinstance(metric, dict) else None

    input_tokens = metric_value("input_tokens")
    cache_read_tokens = metric_value("cache_read_tokens")
    if (
        isinstance(input_tokens, (int, float))
        and not isinstance(input_tokens, bool)
        and isinstance(cache_read_tokens, (int, float))
        and not isinstance(cache_read_tokens, bool)
        and input_tokens < cache_read_tokens
    ):
        errors.append(f"{label} input_tokens must include cache_read_tokens")
    action_metric_ids = (
        "calls",
        "waits",
        "retries",
        "compactions",
        "duplicate_exec_count",
        "duplicate_wait_agent_count",
    )
    action_values = [metric_value(item) for item in action_metric_ids]
    orchestration_load = metric_value("orchestration_load")
    if all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in action_values
    ):
        if orchestration_load != sum(action_values):
            errors.append(
                f"{label} orchestration_load differs from its exact action-counter formula"
            )
    elif orchestration_load is not None:
        errors.append(
            f"{label} orchestration_load must be null when any exact action counter is missing"
        )
    return errors


def _derived_run_metrics(run: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    observed = run.get("observed_facts", {})
    expected = case.get("expected", {})
    nodes_match = observed.get("route_nodes") == expected.get("route_nodes")
    edges_match = observed.get("route_edges") == expected.get("required_edges")
    expected_route = set(expected.get("route_nodes", [])) | set(expected.get("required_edges", []))
    observed_route = set(observed.get("route_nodes", [])) | set(observed.get("route_edges", []))
    coverage = len(expected_route & observed_route) / len(expected_route) if expected_route else 1.0
    oracle = expected.get("quality_oracle") or {}
    gold = set(oracle.get("gold_p0_ids", [])) | set(oracle.get("gold_p1_ids", []))
    findings = set(observed.get("finding_ids", []))
    safety = expected.get("safety_oracle") or {}
    permission_match = observed.get("permission_decision") == safety.get("expected_permission_decision")
    depth_match = observed.get("depth") == safety.get("expected_depth")
    if safety:
        permission_match &= observed.get("permission_receipt_digest") is not None
        depth_match &= observed.get("depth_receipt_digest") is not None
    return {
        "required_coverage_ratio": coverage,
        "p0_p1_recall_ratio": len(gold & findings) / len(gold) if gold else 1.0,
        "decision_changing_findings": len(findings & set(oracle.get("decision_changing_finding_ids", []))),
        "missed_p0_p1_count": len(gold - findings),
        "expected_terminal_match": run.get("observed_terminal") == expected.get("terminal") and observed.get("terminal_receipt_digest") is not None,
        "expected_coverage_match": nodes_match and edges_match and observed.get("coverage_receipt_digest") is not None,
        "route_sentinel_match": nodes_match and edges_match,
        "permission_sentinel_match": bool(permission_match),
        "depth_sentinel_match": bool(depth_match),
        "full_audit_sentinel_match": nodes_match and edges_match and (not safety.get("full_audit_required") or permission_match and depth_match),
    }


def _run_adoption_qualifies(run: dict[str, Any], case: dict[str, Any]) -> bool:
    derived = _derived_run_metrics(run, case)
    metrics = run.get("metrics", {})
    values = {name: item.get("value") for name, item in metrics.items() if isinstance(item, dict)}
    target = case.get("expected", {}).get("elapsed_time_target_ms")
    return (
        run.get("qualification_status") == "qualified"
        and run.get("observed_terminal") == case.get("expected", {}).get("terminal")
        and all(derived[name] is True for name in BOOLEAN_BASELINE_METRICS)
        and (target is None or isinstance(values.get("elapsed_time_ms"), (int, float)) and not isinstance(values.get("elapsed_time_ms"), bool) and values["elapsed_time_ms"] <= target)
        and derived["missed_p0_p1_count"] == 0
        and derived["p0_p1_recall_ratio"] == 1
    )


def _baseline_case_record_errors(
    record: Any,
    *,
    label: str,
    expected_profile: str,
    cases_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if not _exact_fields(record, BASELINE_CASE_RECORD_FIELDS, label, errors):
        if not isinstance(record, dict):
            return errors
    case_id = record.get("case_id")
    case = cases_by_id.get(case_id)
    if case is None or record.get("case_digest") != case.get("case_digest"):
        errors.append(f"{label} case substitution or digest mismatch")
    if record.get("profile") != expected_profile:
        errors.append(f"{label} profile must be {expected_profile}")
    treatment = record.get("treatment")
    if not isinstance(treatment, dict) or set(treatment) != {"arm", "differences"}:
        errors.append(f"{label} treatment fields differ from the contract")
        treatment = {}
    differences = treatment.get("differences")
    if not isinstance(differences, dict):
        errors.append(f"{label} treatment differences must be an object")
        differences = {}
    unauthorized = sorted(set(differences) - set(ALLOWED_TREATMENT_FIELDS))
    if unauthorized:
        errors.append(
            f"{label} unauthorized treatment difference: {', '.join(unauthorized)}"
        )
    expected_arm = "A_CURRENT" if expected_profile == "current" else "B_CANDIDATE"
    if treatment.get("arm") != expected_arm:
        errors.append(f"{label} treatment arm must be {expected_arm}")
    if expected_profile == "current" and differences:
        errors.append(f"{label} current treatment differences must be empty")

    evidence_status = record.get("evidence_status")
    if evidence_status not in BASELINE_EVIDENCE_STATUSES:
        errors.append(f"{label} evidence_status is invalid")
    status = record.get("measurement_status")
    adoption_eligible = record.get("adoption_eligible")
    evidence_ref = record.get("evidence_ref")
    evidence_digest = record.get("evidence_digest")
    runs = record.get("runs")
    if not isinstance(runs, list):
        errors.append(f"{label} runs must be an array")
        runs = []
    if evidence_status == "UNAVAILABLE":
        if status != "unavailable":
            errors.append(f"{label} unavailable evidence must remain unavailable")
        if adoption_eligible is not False:
            errors.append(f"{label} unavailable evidence cannot support adoption")
        if evidence_ref is not None or evidence_digest is not None:
            errors.append(f"{label} unavailable evidence cannot claim a reference")
        if runs:
            errors.append(f"{label} unavailable evidence cannot invent raw runs")
    elif evidence_status == "PROVISIONAL_LOCAL_HOST_EXPORT":
        if status != "provisional":
            errors.append(f"{label} provisional evidence cannot be promoted to measured")
        if adoption_eligible is not False:
            errors.append(f"{label} provisional evidence cannot support adoption")
        if not evidence_ref or not evidence_digest:
            errors.append(f"{label} provisional evidence requires an exact reference")
    elif evidence_status == "PLATFORM_OR_EXTERNAL_ATTESTED":
        if status != "measured":
            errors.append(f"{label} platform/external evidence must be measured")
        if not evidence_ref or not evidence_digest:
            errors.append(f"{label} measured evidence requires an exact attestation")

    errors.extend(
        _metric_value_errors(
            record.get("metrics"),
            label=label,
            evidence_status=evidence_status,
        )
    )
    if evidence_status == "PLATFORM_OR_EXTERNAL_ATTESTED" and isinstance(record.get("metrics"), dict) and any(item.get("value") is None for item in record["metrics"].values() if isinstance(item, dict)):
        errors.append(f"{label} measured record requires every metric")
    case_class = case.get("case_class") if isinstance(case, dict) else None
    expected_run_count = 3 if case_class in {
        "q0_governance_query",
        "q1_low_risk_source_change",
    } else 1
    if record.get("expected_run_count") != expected_run_count:
        errors.append(f"{label} expected_run_count differs from the run protocol")
    if evidence_status != "UNAVAILABLE" and len(runs) != expected_run_count:
        errors.append(f"{label} must retain every raw per-run value")

    ordinals: list[Any] = []
    for index, run in enumerate(runs):
        run_label = f"{label} runs[{index}]"
        if not _exact_fields(run, BASELINE_RUN_FIELDS, run_label, errors):
            continue
        if run.get("arm") != expected_arm:
            errors.append(f"{run_label} arm differs from the profile")
        if run.get("evidence_status") != evidence_status:
            errors.append(f"{run_label} evidence_status differs from its record")
        errors.extend(
            _metric_value_errors(
                run.get("metrics"),
                label=run_label,
                evidence_status=evidence_status,
            )
        )
        observed = run.get("observed_facts")
        if not isinstance(observed, dict) or set(observed) != OBSERVED_FACT_FIELDS:
            errors.append(f"{run_label} observed facts differ from the typed evidence payload")
        elif isinstance(case, dict):
            derived = _derived_run_metrics(run, case)
            metrics = run.get("metrics", {})
            for metric_id, derived_value in derived.items():
                reported = metrics.get(metric_id, {}).get("value") if isinstance(metrics.get(metric_id), dict) else None
                if reported != derived_value:
                    errors.append(f"{run_label} {metric_id} differs from derived observed facts")
            expected_payload_digest = "sha256:" + hashlib.sha256(_canonical_bytes(observed)).hexdigest()
            if run.get("evidence_digest") != expected_payload_digest:
                errors.append(f"{run_label} evidence payload digest differs from observed facts")
        if evidence_status == "PLATFORM_OR_EXTERNAL_ATTESTED" and isinstance(run.get("metrics"), dict) and any(item.get("value") is None for item in run["metrics"].values() if isinstance(item, dict)):
            errors.append(f"{run_label} measured run requires every metric")
        ordinals.append(run.get("ordinal"))
        digest_error = _digest_error(
            run,
            "run_digest",
            multi_agent_efficiency_baseline_run_digest,
            run_label,
        )
        if digest_error:
            errors.append(digest_error)
    if runs and sorted(ordinals) != list(range(1, expected_run_count + 1)):
        errors.append(f"{label} run ordinals must exactly cover the repeat protocol")

    digest_error = _digest_error(
        record,
        "record_digest",
        multi_agent_efficiency_baseline_case_record_digest,
        label,
    )
    if digest_error:
        errors.append(digest_error)
    return errors


def validate_multi_agent_efficiency_baseline_manifest(
    manifest: Any,
    *,
    corpus: Any = None,
    registry: Any = None,
    manifest_verifier: EfficiencyBaselineManifestVerifier | None = None,
) -> list[str]:
    """Validate one corpus-, policy-, Registry-, and generation-bound baseline."""

    if not isinstance(manifest, dict):
        return ["multi-agent efficiency baseline manifest must be an object"]
    errors = [
        f"baseline manifest schema: {error}"
        for error in schema_subset_errors(manifest, _baseline_manifest_schema())
    ]
    _exact_fields(manifest, BASELINE_MANIFEST_FIELDS, "baseline manifest", errors)
    if manifest.get("schema_version") != "multi_agent_efficiency_baseline_manifest_v1":
        errors.append("baseline manifest schema_version is invalid")
    if corpus is None:
        try:
            corpus = json.loads(
                (REPO_ROOT / "tests/fixtures/agent_governance/multi_agent_efficiency_baseline_corpus_v1.json").read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, json.JSONDecodeError):
            corpus = None
    corpus_errors = validate_multi_agent_efficiency_baseline_corpus(corpus)
    errors.extend(f"bound corpus: {error}" for error in corpus_errors)
    if registry is None:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(registry, dict):
        errors.append("bound Registry must be an object")
        registry = {}

    corpus_binding = manifest.get("corpus_binding")
    if (
        not isinstance(corpus_binding, dict)
        or set(corpus_binding) != {"corpus_id", "corpus_digest"}
        or not isinstance(corpus, dict)
        or corpus_binding.get("corpus_id") != corpus.get("corpus_id")
        or corpus_binding.get("corpus_digest") != corpus.get("corpus_digest")
    ):
        errors.append("baseline manifest corpus binding differs from authority")
    policy = registry.get("efficiency_evaluation_policy", {})
    policy_binding = manifest.get("policy_binding")
    if (
        not isinstance(policy_binding, dict)
        or set(policy_binding) != {"policy_id", "policy_digest"}
        or policy_binding.get("policy_id") != policy.get("policy_id")
        or policy_binding.get("policy_digest") != policy.get("policy_digest")
    ):
        errors.append("baseline manifest policy binding differs from authority")
    registry_binding = manifest.get("registry_binding")
    try:
        expected_registry_digest = "sha256:" + hashlib.sha256(
            _canonical_bytes(registry)
        ).hexdigest()
    except (TypeError, ValueError):
        expected_registry_digest = None
    if (
        not isinstance(registry_binding, dict)
        or set(registry_binding) != {"schema_version", "registry_digest"}
        or registry_binding.get("schema_version") != "agent_registry_v1"
        or registry_binding.get("registry_digest") != expected_registry_digest
    ):
        errors.append("baseline manifest Registry binding differs from authority")

    source_generation = manifest.get("source_generation")
    if not isinstance(source_generation, dict) or set(source_generation) != {
        "head_sha",
        "tree_sha",
        "generation_digest",
    }:
        errors.append("baseline manifest source generation fields differ")
    else:
        digest_error = _digest_error(
            source_generation,
            "generation_digest",
            multi_agent_efficiency_source_generation_digest,
            "baseline manifest source generation",
        )
        if digest_error:
            errors.append(digest_error)

    cases = corpus.get("cases", []) if isinstance(corpus, dict) else []
    cases_by_id = {
        case.get("case_id"): case for case in cases if isinstance(case, dict)
    }
    current_records = manifest.get("current_profile_records")
    candidate_records = manifest.get("candidate_profile_records")
    if not isinstance(current_records, list):
        errors.append("current_profile_records must be an array")
        current_records = []
    if not isinstance(candidate_records, list):
        errors.append("candidate_profile_records must be an array")
        candidate_records = []
    current_ids = [
        record.get("case_id") for record in current_records if isinstance(record, dict)
    ]
    if len(current_records) != 4 or set(current_ids) != set(BASELINE_CASE_IDS):
        errors.append("current profile records must exactly cover all four corpus cases")
    candidate_ids = [
        record.get("case_id") for record in candidate_records if isinstance(record, dict)
    ]
    if len(candidate_ids) != len(set(candidate_ids)) or not set(candidate_ids).issubset(
        set(BASELINE_CASE_IDS)
    ):
        errors.append("candidate profile records contain duplicate or substituted cases")
    for index, record in enumerate(current_records):
        errors.extend(
            _baseline_case_record_errors(
                record,
                label=f"current_profile_records[{index}]",
                expected_profile="current",
                cases_by_id=cases_by_id,
            )
        )
    for index, record in enumerate(candidate_records):
        errors.extend(
            _baseline_case_record_errors(
                record,
                label=f"candidate_profile_records[{index}]",
                expected_profile="candidate",
                cases_by_id=cases_by_id,
            )
        )

    all_records = current_records + candidate_records
    platform_records = [record for record in all_records if isinstance(record, dict) and record.get("evidence_status") == "PLATFORM_OR_EXTERNAL_ATTESTED"]
    platform_verified = False
    if platform_records:
        binding = {
            "manifest_digest": manifest.get("manifest_digest"),
            "corpus_digest": corpus_binding.get("corpus_digest") if isinstance(corpus_binding, dict) else None,
            "policy_digest": policy_binding.get("policy_digest") if isinstance(policy_binding, dict) else None,
            "registry_digest": registry_binding.get("registry_digest") if isinstance(registry_binding, dict) else None,
            "source_generation_digest": source_generation.get("generation_digest") if isinstance(source_generation, dict) else None,
            "run_ids": tuple(sorted(run["run_id"] for record in platform_records for run in record.get("runs", []) if isinstance(run, dict) and isinstance(run.get("run_id"), str))),
            "evidence_payload_digests": tuple(sorted(run["evidence_digest"] for record in platform_records for run in record.get("runs", []) if isinstance(run, dict) and isinstance(run.get("evidence_digest"), str))),
            "record_digests": tuple(sorted(record["record_digest"] for record in platform_records if isinstance(record.get("record_digest"), str))),
        }
        if len(binding["run_ids"]) != len(set(binding["run_ids"])):
            errors.append("platform/external baseline run IDs must be globally unique")
        try:
            platform_verified = manifest_verifier is not None and manifest_verifier.verify_efficiency_baseline_manifest(**binding) is True
        except Exception:  # noqa: BLE001 - verifier failure is fail-closed
            platform_verified = False
        if not platform_verified:
            errors.append("platform/external baseline evidence requires exact out-of-band host verification")

    observations = manifest.get("reference_observations")
    if not isinstance(observations, list) or not observations:
        errors.append("reference observations must include an honest availability record")
    else:
        for index, observation in enumerate(observations):
            label = f"reference_observations[{index}]"
            if not isinstance(observation, dict) or set(observation) != {
                "status",
                "comparable",
                "observation",
                "provenance_ref",
                "provenance_digest",
                "unavailable_reason",
            }:
                errors.append(f"{label} fields differ from the contract")
                continue
            if observation.get("status") == "UNAVAILABLE":
                if (
                    observation.get("comparable") is not False
                    or observation.get("observation") is not None
                    or observation.get("provenance_ref") is not None
                    or observation.get("provenance_digest") is not None
                    or not observation.get("unavailable_reason")
                ):
                    errors.append(f"{label} unavailable reference must not invent provenance")
            elif observation.get("status") == "NON_COMPARABLE_REFERENCE":
                if (
                    observation.get("comparable") is not False
                    or not observation.get("observation")
                    or not observation.get("provenance_ref")
                    or not observation.get("provenance_digest")
                    or observation.get("unavailable_reason") is not None
                ):
                    errors.append(f"{label} non-comparable reference requires bound provenance")
            else:
                errors.append(f"{label} status is invalid")

    record_eligibility: list[bool] = []
    for record in all_records:
        case = cases_by_id.get(record.get("case_id"), {}) if isinstance(record, dict) else {}
        runs = record.get("runs", []) if isinstance(record, dict) else []
        eligible = platform_verified and record.get("evidence_status") == "PLATFORM_OR_EXTERNAL_ATTESTED" and len(runs) == record.get("expected_run_count") and all(_run_adoption_qualifies(run, case) for run in runs)
        record_eligibility.append(bool(eligible))
        if isinstance(record, dict) and record.get("adoption_eligible") is not bool(eligible):
            errors.append(f"{record.get('treatment', {}).get('arm')} {record.get('case_id')} adoption_eligible differs from derived qualification")
    current_by_case = {record.get("case_id"): record for record in current_records if isinstance(record, dict)}
    quality_ok = all(
        len(record.get("runs", [])) == len(current_by_case[record["case_id"]].get("runs", []))
        and all(_quality_noninferiority({name: item.get("value") for name, item in current_run["metrics"].items()}, {name: item.get("value") for name, item in candidate_run["metrics"].items()}, policy["thresholds"])["status"] == "PASS" for current_run, candidate_run in zip(current_by_case[record["case_id"]]["runs"], record["runs"]))
        for record in candidate_records if record.get("case_id") in current_by_case
    )
    adoption_ready = len(current_records) == len(candidate_records) == 4 and all(record_eligibility) and quality_ok
    derived_adoption_status = "PENDING_CANDIDATE_RUNS" if not candidate_records else "ADOPTION_EVIDENCE_AVAILABLE" if adoption_ready else "PROVISIONAL_DIAGNOSTICS_ONLY"
    if manifest.get("adoption_status") != derived_adoption_status:
        errors.append(f"adoption status differs from derived qualification: expected {derived_adoption_status}")

    digest_error = _digest_error(
        manifest,
        "manifest_digest",
        multi_agent_efficiency_baseline_manifest_digest,
        "baseline manifest",
    )
    if digest_error:
        errors.append(digest_error)
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
        else:
            metrics = profile.get("metrics")
            reported_calls = (
                metrics.get("calls") if isinstance(metrics, dict) else None
            )
            if reported_calls is None and call_digests:
                errors.append(
                    f"{label} unavailable metrics.calls requires an empty "
                    "call-record inventory"
                )
            elif (
                isinstance(reported_calls, int)
                and not isinstance(reported_calls, bool)
                and len(call_digests) != reported_calls
            ):
                errors.append(
                    f"{label} call_record_digests must exactly cover "
                    f"metrics.calls={reported_calls}; observed {len(call_digests)}"
                )
            if isinstance(run_id, str) and run_id:
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
    calls = metrics.get("calls")
    retries = metrics.get("retries")
    if (
        isinstance(calls, int)
        and not isinstance(calls, bool)
        and isinstance(retries, int)
        and not isinstance(retries, bool)
        and retries > calls
    ):
        errors.append(f"{label} retries cannot exceed calls")

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
    schema_record = dict(record)
    if isinstance(record.get("quality_noninferiority_policy"), dict):
        schema_record["quality_noninferiority_policy"] = dict(record["quality_noninferiority_policy"])
        schema_record["quality_noninferiority_policy"]["policy_digest"] = LEGACY_SYNTHETIC_POLICY_DIGEST
    errors = [
        f"evaluation schema: {error}"
        for error in schema_subset_errors(schema_record, _schema())
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
        binding_digest = policy_binding.get("policy_digest")
        legacy_synthetic_binding = (
            record.get("evidence_kind") == "synthetic_fixture"
            and isinstance(record.get("profiles"), list)
            and len(record["profiles"]) == 3
            and all(isinstance(profile, dict) and profile.get("measurement_status") == "synthetic" for profile in record["profiles"])
            and binding_digest == LEGACY_SYNTHETIC_POLICY_DIGEST
        )
        if binding_digest == LEGACY_SYNTHETIC_POLICY_DIGEST and not legacy_synthetic_binding:
            errors.append("legacy policy digest is restricted to all-synthetic fixture evidence")
        if (
            policy_binding.get("policy_id") != authority.get("policy_id")
            or (
                binding_digest != authority.get("policy_digest")
                and not legacy_synthetic_binding
            )
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


def _efficiency_improvement(
    baseline_metrics: dict[str, Any],
    candidate_metrics: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    axes = policy["axes"]
    checks = {
        axis: {
            "status": (
                "UNAVAILABLE"
                if baseline_metrics.get(axis) is None
                or candidate_metrics.get(axis) is None
                else (
                    "IMPROVED"
                    if candidate_metrics[axis] < baseline_metrics[axis]
                    else (
                        "WORSE"
                        if candidate_metrics[axis] > baseline_metrics[axis]
                        else "EQUAL"
                    )
                )
            ),
            "baseline": baseline_metrics.get(axis),
            "candidate": candidate_metrics.get(axis),
            "ratio": _ratio(
                candidate_metrics.get(axis),
                baseline_metrics.get(axis),
            ),
        }
        for axis in axes
    }
    strictly_improved_axes = sorted(
        axis for axis, check in checks.items() if check["status"] == "IMPROVED"
    )
    worse_axes = sorted(
        axis for axis, check in checks.items() if check["status"] == "WORSE"
    )
    unavailable_axes = sorted(
        axis for axis, check in checks.items() if check["status"] == "UNAVAILABLE"
    )
    return {
        "status": (
            "UNAVAILABLE"
            if unavailable_axes
            else (
                "PASS"
                if strictly_improved_axes and not worse_axes
                else "FAIL"
            )
        ),
        "predicate": policy["predicate"],
        "strictly_improved_axes": strictly_improved_axes,
        "worse_axes": worse_axes,
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
        improvement = _efficiency_improvement(
            baseline["metrics"],
            candidate["metrics"],
            quality_policy["efficiency_improvement"],
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
            "efficiency_improvement": improvement,
            "efficiency_ratios": ratios,
            "efficiency_claim_allowed": (
                all_measured
                and quality["status"] == "PASS"
                and improvement["status"] == "PASS"
            ),
        }

    benchmark_only = sorted(
        name
        for name, comparison in comparisons.items()
        if comparison["measurement_status"] == "synthetic"
        and comparison["quality_noninferiority"]["status"] == "PASS"
        and comparison["efficiency_improvement"]["status"] == "PASS"
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
        "quality_noninferiority_policy": {
            "policy_id": quality_policy["policy_id"],
            "policy_digest": quality_policy["policy_digest"],
        },
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
