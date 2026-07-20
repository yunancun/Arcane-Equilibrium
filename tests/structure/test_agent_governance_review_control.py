"""Executable scope and round controls for delegated review findings."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_review_control import (  # noqa: E402
    adjudicate_review_control,
    capture_review_generation,
    review_task_contract_digest,
    verification_fragment_truth_errors,
)


DIGEST = "sha256:" + "a" * 64
HEAD = "1" * 40
GENERATION = {
    "source_head": HEAD,
    "dirty_diff_hash": DIGEST,
    "untracked_relevant_hash": DIGEST,
}
CRITERION = "only task-scope regressions block completion"
TASK_FACTS = {
    "task_shape": "fix",
    "surfaces": ["agent_workflow", "governance", "python"],
    "risk": "medium",
    "uncertainty": "low",
    "side_effect_class": "repo_write",
    "objective": "bound delegated review without widening the task",
    "scope": ["review finding admission"],
    "acceptance_criteria": [CRITERION],
    "hard_stops": ["no scope expansion"],
    "baseline": {
        "source_head": "0" * 40,
        "dirty_diff_hash": DIGEST,
        "untracked_relevant_hash": DIGEST,
    },
    "dirty_scope": ["helper_scripts/maintenance_scripts/review.py"],
    "direct_interfaces": ["review_control_v1"],
    "previous_failure": "severity labels widened task scope",
    "task_prompt": "fix bounded review",
    "continuation_mode": "finite",
}


def _finding(
    finding_id: str,
    *,
    classification: str,
    severity: str = "P1",
    criterion: str | None = CRITERION,
    introduced: bool = False,
) -> dict:
    return {
        "id": finding_id,
        "classification": classification,
        "severity": severity,
        "summary": finding_id,
        "paths": ["helper_scripts/maintenance_scripts/review.py"],
        "evidence_refs": [f"evidence:{finding_id}"],
        "acceptance_criterion": criterion,
        "introduced_by_current_diff": introduced,
    }


def _round(number: int, generation: dict, findings: list[dict]) -> dict:
    return {
        "round": number,
        "kind": "initial" if number == 1 else "exact_recheck",
        "reviewed_generation": generation,
        "findings": findings,
    }


def _control(
    rounds: list[dict],
    *,
    final_generation: dict = GENERATION,
    non_goal: str = "open-ended redesign",
) -> dict:
    return {
        "schema_version": "review_control_v1",
        "task_contract_digest": review_task_contract_digest(TASK_FACTS),
        "non_goals": [non_goal],
        "final_generation": final_generation,
        "reviewers": [{"node_id": "independent_review", "rounds": rounds}],
    }


def _fragment(control: dict, concerns: list[str] | None = None) -> dict:
    return {
        "node_id": "independent_review",
        "classification": "FACT",
        "confidence": "high",
        "concerns": [] if concerns is None else concerns,
        "payload": {"review_control": control},
    }


def test_severity_never_promotes_an_out_of_scope_finding_to_blocker() -> None:
    control = _control([
        _round(1, GENERATION, [
            _finding(
                "p0-followup", classification="out_of_scope_followup",
                severity="P0", criterion=None,
            ),
            _finding("p3-blocker", classification="in_scope_blocker", severity="P3"),
        ])
    ])

    decision = adjudicate_review_control(TASK_FACTS, control)

    assert decision["blocking_finding_ids"] == ["p3-blocker"]
    assert decision["followup_finding_ids"] == ["p0-followup"]
    assert decision["action"] == "BATCH_REPAIR_THEN_EXACT_RECHECK"
    assert decision["recheck_allowed"] is True
    assert decision["scope_expansion_allowed"] is False


def test_exact_recheck_cannot_introduce_a_new_finding() -> None:
    initial = {**GENERATION, "source_head": "2" * 40}
    control = _control([
        _round(1, initial, [
            _finding("original-blocker", classification="in_scope_blocker")
        ]),
        _round(2, GENERATION, [
            _finding(
                "new-blocker", classification="regression_blocker", introduced=True
            )
        ]),
    ])

    with pytest.raises(ValueError, match="new finding"):
        adjudicate_review_control(TASK_FACTS, control)


def test_exact_recheck_cannot_hide_an_invalid_initial_blocker() -> None:
    initial = {**GENERATION, "source_head": "3" * 40}
    control = _control([
        _round(1, initial, [
            _finding("invalid-initial", classification="regression_blocker")
        ]),
        _round(2, GENERATION, []),
    ])

    with pytest.raises(ValueError, match="regression_blocker"):
        adjudicate_review_control(TASK_FACTS, control)


def test_review_decision_requires_the_clean_frozen_generation(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "review-control@example.invalid"],
        cwd=tmp_path, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Review Control Test"],
        cwd=tmp_path, check=True,
    )
    owned = tmp_path / "owned.py"
    owned.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "owned.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    generation = capture_review_generation(tmp_path)
    control = _control(
        [_round(1, generation, [])], final_generation=generation,
        non_goal="review moving source bytes",
    )

    assert adjudicate_review_control(TASK_FACTS, control, repo=tmp_path)[
        "action"
    ] == "CLOSE_REVIEW"
    cli = subprocess.run(
        [
            sys.executable, str(HELPERS / "agent_governance.py"),
            "review-control",
            json.dumps({"task_facts": TASK_FACTS, "review_control": control}),
            "--repo", str(tmp_path),
        ],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    assert cli.returncode == 0, cli.stderr or cli.stdout
    assert json.loads(cli.stdout)["action"] == "CLOSE_REVIEW"

    owned.write_text("value = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clean frozen head"):
        adjudicate_review_control(TASK_FACTS, control, repo=tmp_path)


def test_verification_fragment_cannot_hide_a_typed_blocker() -> None:
    control = _control([
        _round(1, GENERATION, [
            _finding("hidden-blocker", classification="in_scope_blocker", severity="P3")
        ])
    ], non_goal="hide review blockers")

    assert verification_fragment_truth_errors(
        _fragment(control), "independent review", TASK_FACTS
    ) == [
        "independent review typed blockers cannot support PASS: ['hidden-blocker']",
        "independent review concerns do not exactly project typed blocker IDs",
    ]


def test_nonblocking_p0_finding_remains_visible_without_blocking_pass() -> None:
    control = _control([
        _round(1, GENERATION, [
            _finding(
                "visible-followup", classification="out_of_scope_followup",
                severity="P0", criterion=None,
            )
        ])
    ], non_goal="promote severity into authority")

    assert verification_fragment_truth_errors(
        _fragment(control), "independent review", TASK_FACTS
    ) == []
    assert adjudicate_review_control(TASK_FACTS, control)[
        "followup_finding_ids"
    ] == ["visible-followup"]


def test_resolved_exact_recheck_closes_and_third_round_is_rejected() -> None:
    initial = {**GENERATION, "source_head": "4" * 40}
    control = _control([
        _round(1, initial, [
            _finding("resolved-blocker", classification="in_scope_blocker")
        ]),
        _round(2, GENERATION, []),
    ], non_goal="open a third review round")

    assert adjudicate_review_control(TASK_FACTS, control)["action"] == "CLOSE_REVIEW"
    control["reviewers"][0]["rounds"].append(_round(3, GENERATION, []))
    with pytest.raises(ValueError, match="at most one exact recheck"):
        adjudicate_review_control(TASK_FACTS, control)


def test_dispatch_rules_require_scope_classification_and_bounded_recheck() -> None:
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            ".codex/AGENT_DISPATCH_PROTOCOL.md",
            ".codex/SUBAGENT_EXECUTION_RULES.md",
        )
    )
    for required in (
        "review_control_v1", "in_scope_blocker", "regression_blocker",
        "out_of_scope_followup", "pre_existing", "one exact recheck",
        "frozen repository generation",
    ):
        assert required in sources
