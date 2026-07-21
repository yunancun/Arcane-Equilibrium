"""Deterministic scope admission and stop decisions for delegated reviews."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from agent_governance_context import capture_repository_baseline
from agent_governance_routing import _normalize_task_facts, task_contract_projection


BLOCKING_CLASSIFICATIONS = frozenset({"in_scope_blocker", "regression_blocker"})
FOLLOWUP_CLASSIFICATIONS = frozenset({"out_of_scope_followup", "pre_existing"})
FINDING_CLASSIFICATIONS = BLOCKING_CLASSIFICATIONS | FOLLOWUP_CLASSIFICATIONS
SEVERITIES = frozenset({"P0", "P1", "P2", "P3"})
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def review_task_contract_digest(task_facts: dict[str, Any]) -> str:
    """Bind review control to the same normalized task contract as Context."""

    return _canonical_digest(
        task_contract_projection(_normalize_task_facts(task_facts))
    )


def capture_review_generation(repo: Path) -> dict[str, str]:
    """Capture the complete repository-byte generation reviewed by a verifier."""

    return capture_repository_baseline(repo)


def _generation_errors(value: Any, label: str) -> list[str]:
    fields = {"source_head", "dirty_diff_hash", "untracked_relevant_hash"}
    if not isinstance(value, dict) or set(value) != fields:
        return [f"{label} fields are not exact"]
    errors: list[str] = []
    if not HEAD_RE.fullmatch(str(value["source_head"])):
        errors.append(f"{label} source_head must be exact 40-hex")
    for field in ("dirty_diff_hash", "untracked_relevant_hash"):
        if not DIGEST_RE.fullmatch(str(value[field])):
            errors.append(f"{label} {field} must be sha256")
    return errors


def _nonempty_strings(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _safe_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    path = PurePosixPath(value)
    if value.startswith(("/", "~")) or ".." in path.parts or "\\" in value:
        return None
    return path.as_posix()


def _within_scope(path: str, dirty_scope: list[str]) -> bool:
    return any(
        path == root or path.startswith(root.rstrip("/") + "/")
        for root in dirty_scope
    )


def _finding_errors(
    finding: Any,
    *,
    acceptance: set[str],
    dirty_scope: list[str],
    label: str,
) -> list[str]:
    errors: list[str] = []
    fields = {
        "id", "classification", "severity", "summary", "paths",
        "evidence_refs", "acceptance_criterion", "introduced_by_current_diff",
    }
    if not isinstance(finding, dict) or set(finding) != fields:
        return [f"{label} fields are not exact"]
    if not isinstance(finding["id"], str) or not finding["id"].strip():
        errors.append(f"{label} id is invalid")
    classification = finding["classification"]
    if classification not in FINDING_CLASSIFICATIONS:
        errors.append(f"{label} classification is invalid")
    if finding["severity"] not in SEVERITIES:
        errors.append(f"{label} severity is invalid")
    if not isinstance(finding["summary"], str) or not finding["summary"].strip():
        errors.append(f"{label} summary is invalid")
    if not _nonempty_strings(finding["paths"]):
        errors.append(f"{label} paths must be non-empty strings")
        paths: list[str] = []
    else:
        paths = [path for raw in finding["paths"] if (path := _safe_path(raw))]
        if len(paths) != len(finding["paths"]):
            errors.append(f"{label} contains an unsafe path")
    if not _nonempty_strings(finding["evidence_refs"]):
        errors.append(f"{label} evidence_refs must be non-empty strings")
    criterion = finding["acceptance_criterion"]
    introduced = finding["introduced_by_current_diff"]
    if not isinstance(introduced, bool):
        errors.append(f"{label} introduced_by_current_diff must be boolean")
    if classification == "in_scope_blocker":
        if criterion not in acceptance:
            errors.append(f"{label} in_scope_blocker lacks an admitted criterion")
        if any(not _within_scope(path, dirty_scope) for path in paths):
            errors.append(f"{label} in_scope_blocker path is outside dirty_scope")
    elif classification == "regression_blocker":
        if introduced is not True:
            errors.append(f"{label} regression_blocker must be introduced by current diff")
        if criterion is not None and criterion not in acceptance:
            errors.append(f"{label} regression_blocker criterion is not admitted")
        if any(not _within_scope(path, dirty_scope) for path in paths):
            errors.append(f"{label} regression_blocker path is outside dirty_scope")
    elif classification in FOLLOWUP_CLASSIFICATIONS:
        if criterion is not None:
            errors.append(f"{label} non-blocking finding cannot claim an acceptance criterion")
        if classification == "pre_existing" and introduced is not False:
            errors.append(f"{label} pre_existing finding cannot be current-diff introduced")
    return errors


def adjudicate_review_control(
    task_facts: dict[str, Any],
    control: dict[str, Any],
    *,
    repo: Path | None = None,
    expected_generation: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Validate one bounded review packet and return the only permitted action."""

    expected_fields = {
        "schema_version", "task_contract_digest", "non_goals", "final_generation",
        "reviewers",
    }
    if not isinstance(control, dict) or set(control) != expected_fields:
        raise ValueError("review_control_v1 fields are not exact")
    if control["schema_version"] != "review_control_v1":
        raise ValueError("review control schema_version is invalid")
    task_digest = review_task_contract_digest(task_facts)
    if control["task_contract_digest"] != task_digest:
        raise ValueError("review control task contract digest is not bound")
    if not _nonempty_strings(control["non_goals"]):
        raise ValueError("review control requires explicit non_goals")
    generation_errors = _generation_errors(
        control["final_generation"], "review control final_generation"
    )
    if generation_errors:
        raise ValueError("; ".join(generation_errors))
    if expected_generation is not None:
        trusted_errors = _generation_errors(
            expected_generation, "trusted repository generation"
        )
        if trusted_errors:
            raise ValueError("; ".join(trusted_errors))
        if control["final_generation"] != expected_generation:
            raise ValueError(
                "review control final_generation differs from trusted "
                "repository generation"
            )
    if repo is not None:
        try:
            generation = capture_review_generation(repo)
            status = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as error:
            raise ValueError(f"cannot verify clean frozen head: {error}") from error
        if generation != control["final_generation"] or status:
            raise ValueError("review control requires the clean frozen head")
    reviewers = control["reviewers"]
    if not isinstance(reviewers, list) or not reviewers:
        raise ValueError("review control reviewers must be a non-empty array")

    normalized = _normalize_task_facts(task_facts)
    acceptance = set(normalized.get("acceptance_criteria", []))
    dirty_scope = list(normalized.get("dirty_scope", []))
    errors: list[str] = []
    blocking: list[str] = []
    followups: list[str] = []
    seen_nodes: set[str] = set()
    blocker_recheck_exhausted = False
    for reviewer_index, reviewer in enumerate(reviewers):
        label = f"reviewers[{reviewer_index}]"
        if not isinstance(reviewer, dict) or set(reviewer) != {"node_id", "rounds"}:
            errors.append(f"{label} fields are not exact")
            continue
        node_id = reviewer["node_id"]
        if (
            not isinstance(node_id, str)
            or not node_id.strip()
            or node_id in seen_nodes
        ):
            errors.append(f"{label} node_id is invalid or duplicate")
            continue
        seen_nodes.add(node_id)
        rounds = reviewer["rounds"]
        if not isinstance(rounds, list) or not 1 <= len(rounds) <= 2:
            errors.append(f"{label} allows one initial round and at most one exact recheck")
            continue
        round_fields = {"round", "kind", "reviewed_generation", "findings"}
        for round_index, review_round in enumerate(rounds):
            expected_kind = "initial" if round_index == 0 else "exact_recheck"
            if not isinstance(review_round, dict) or set(review_round) != round_fields:
                errors.append(f"{label}.rounds[{round_index}] fields are not exact")
                continue
            if (
                review_round["round"] != round_index + 1
                or review_round["kind"] != expected_kind
            ):
                errors.append(f"{label}.rounds[{round_index}] has invalid round or kind")
            errors.extend(_generation_errors(
                review_round["reviewed_generation"],
                f"{label}.rounds[{round_index}].reviewed_generation",
            ))
            if not isinstance(review_round["findings"], list):
                errors.append(f"{label}.rounds[{round_index}] findings must be an array")
                continue
            round_ids: set[str] = set()
            for finding_index, finding in enumerate(review_round["findings"]):
                finding_label = (
                    f"{label}.rounds[{round_index}].findings[{finding_index}]"
                )
                errors.extend(_finding_errors(
                    finding,
                    acceptance=acceptance,
                    dirty_scope=dirty_scope,
                    label=finding_label,
                ))
                if not isinstance(finding, dict) or not isinstance(
                    finding.get("id"), str
                ):
                    continue
                if finding["id"] in round_ids:
                    errors.append(f"{finding_label} id is duplicate within reviewer")
                round_ids.add(finding["id"])
        if errors and any(error.startswith(f"{label}.rounds") for error in errors):
            continue
        if (
            len(rounds) == 2
            and rounds[0]["reviewed_generation"] == rounds[1]["reviewed_generation"]
        ):
            errors.append(f"{label} exact recheck requires a new frozen head")
        if len(rounds) == 2:
            initial_blockers = {
                finding["id"]: finding["classification"]
                for finding in rounds[0]["findings"]
                if isinstance(finding, dict)
                and finding.get("classification") in BLOCKING_CLASSIFICATIONS
                and isinstance(finding.get("id"), str)
            }
            initial_blocker_ids = set(initial_blockers)
            recheck_ids = {
                finding.get("id")
                for finding in rounds[1]["findings"]
                if isinstance(finding, dict) and isinstance(finding.get("id"), str)
            }
            new_ids = sorted(recheck_ids - initial_blocker_ids)
            if new_ids:
                errors.append(
                    f"{label} exact recheck introduced a new finding: {new_ids}"
                )
            reclassified = sorted(
                finding["id"] for finding in rounds[1]["findings"]
                if isinstance(finding, dict)
                and finding.get("id") in initial_blockers
                and finding.get("classification")
                != initial_blockers[finding["id"]]
            )
            if reclassified:
                errors.append(
                    f"{label} exact recheck changed blocker classification: "
                    f"{reclassified}"
                )
        current = rounds[-1]
        if not isinstance(current, dict) or not isinstance(current.get("findings"), list):
            errors.append(f"{label} current round is invalid")
            continue
        if current.get("reviewed_generation") != control["final_generation"]:
            errors.append(f"{label} latest review is stale against final_generation")
        current_blockers = False
        for finding in current["findings"]:
            if not isinstance(finding, dict):
                continue
            finding_id = finding.get("id")
            if finding.get("classification") in BLOCKING_CLASSIFICATIONS:
                current_blockers = True
                if isinstance(finding_id, str):
                    blocking.append(finding_id)
            elif finding.get("classification") in FOLLOWUP_CLASSIFICATIONS:
                if isinstance(finding_id, str):
                    followups.append(finding_id)
        if current_blockers and len(rounds) > 1:
            blocker_recheck_exhausted = True
    if errors:
        raise ValueError("; ".join(errors))

    blocking = sorted(blocking)
    followups = sorted(followups)
    if blocking and blocker_recheck_exhausted:
        action = "STOP_UNRESOLVED_BLOCKERS"
        recheck_allowed = False
    elif blocking:
        action = "BATCH_REPAIR_THEN_EXACT_RECHECK"
        recheck_allowed = True
    else:
        action = "CLOSE_REVIEW"
        recheck_allowed = False
    return {
        "schema_version": "review_control_decision_v1",
        "task_contract_digest": task_digest,
        "review_control_digest": _canonical_digest(control),
        "reviewed_generation": control["final_generation"],
        "blocking_finding_ids": blocking,
        "followup_finding_ids": followups,
        "action": action,
        "recheck_allowed": recheck_allowed,
        "scope_expansion_allowed": False,
    }


def verification_fragment_truth_errors(
    fragment: dict[str, Any], label: str, task_facts: dict[str, Any], *,
    expected_generation: dict[str, str],
) -> list[str]:
    """Project typed review findings into the closure PASS truth gate."""

    errors: list[str] = []
    if fragment.get("classification") != "FACT":
        errors.append(f"{label} PASS must be FACT, not assumption/inference")
    if fragment.get("confidence") == "low":
        errors.append(f"{label} low-confidence fragment cannot support PASS")
    concerns = fragment.get("concerns", [])
    payload = fragment.get("payload", {})
    control = payload.get("review_control") if isinstance(payload, dict) else None
    if control is None:
        if concerns:
            errors.append(f"{label} unresolved concerns cannot support PASS")
        return errors
    try:
        decision = adjudicate_review_control(
            task_facts, control, expected_generation=expected_generation
        )
    except (TypeError, ValueError) as error:
        errors.append(f"{label} review control is invalid: {error}")
        return errors
    matching = [
        reviewer for reviewer in control["reviewers"]
        if reviewer["node_id"] == fragment.get("node_id")
    ]
    if len(matching) != 1:
        errors.append(f"{label} review control does not bind the fragment node")
        return errors
    current_findings = matching[0]["rounds"][-1]["findings"]
    blocker_ids = sorted(
        finding["id"] for finding in current_findings
        if finding["classification"] in BLOCKING_CLASSIFICATIONS
    )
    if blocker_ids:
        errors.append(f"{label} typed blockers cannot support PASS: {blocker_ids}")
    elif concerns:
        errors.append(
            f"{label} concerns must be empty when typed blockers are resolved"
        )
    concern_ids = (
        sorted(concerns)
        if isinstance(concerns, list)
        and all(isinstance(concern, str) for concern in concerns)
        else None
    )
    if concern_ids != blocker_ids:
        errors.append(f"{label} concerns do not exactly project typed blocker IDs")
    if decision["blocking_finding_ids"] != blocker_ids:
        errors.append(f"{label} review decision contains blockers from another node")
    return errors


__all__ = [
    "adjudicate_review_control",
    "capture_review_generation",
    "review_task_contract_digest",
    "verification_fragment_truth_errors",
]
