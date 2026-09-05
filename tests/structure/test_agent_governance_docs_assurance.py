"""Assurance routing for narrowly classified editorial documentation."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_routing import (  # noqa: E402
    route_task,
    task_contract_projection,
)
from agent_governance_workflow_codegen import (  # noqa: E402
    render_context_admission_block,
)


EDITORIAL_PATH = "docs/guides/release-notes.md"
R4_SKIP = {
    "role": "R4",
    "reason": (
        "explicit low-risk editorial docs classification does not require the "
        "documentation integrity reviewer"
    ),
    "residual_risk": (
        "typed facts cannot prove prose semantics under innocuous filenames; "
        "reopen on scope, classification, or surface drift"
    ),
    "owner": "PM",
}


def _facts() -> dict[str, object]:
    return {
        "task_shape": "docs",
        "surfaces": ["comments", "docs"],
        "risk": "low",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "docs_write",
        "continuation_mode": "finite",
        "objective": "Clarify one editorial guide paragraph.",
        "scope": [EDITORIAL_PATH],
        "dirty_scope": [EDITORIAL_PATH],
        "acceptance_criteria": ["The paragraph is unambiguous."],
        "hard_stops": ["Do not change policy or source."],
        "baseline": {},
        "direct_interfaces": [],
        "claim_inputs": {},
        "task_prompt": "Clarify one editorial guide paragraph.",
    }


def _public_nodes(route: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            key: node[key]
            for key in ("id", "role", "kind", "requires", "mandatory")
        }
        for node in route["nodes"]
    ]


def test_explicit_single_file_editorial_docs_route_skips_r4() -> None:
    route = route_task(_facts())

    assert _public_nodes(route) == [
        {
            "id": "pm_triage",
            "role": "PM",
            "kind": "role",
            "requires": [],
            "mandatory": True,
        },
        {
            "id": "docs_update",
            "role": "TW",
            "kind": "role",
            "requires": ["pm_triage"],
            "mandatory": True,
        },
        {
            "id": "pm_closure",
            "role": "PM",
            "kind": "role",
            "requires": ["docs_update"],
            "mandatory": True,
        },
    ]
    assert route["required_role_nodes"] == [
        {
            "node_id": "docs_update",
            "role": "TW",
            "native_agent": "TW",
            "node_class": "work",
            "permission": "docs_writer",
            "requires": [],
            "path_scope": [EDITORIAL_PATH],
        }
    ]
    assert R4_SKIP in route["skipped"]


def test_editorial_docs_shortcut_fails_closed_for_adversarial_facts() -> None:
    cases: list[tuple[str, dict[str, object]]] = []

    def add(name: str, **updates: object) -> None:
        facts = deepcopy(_facts())
        facts.update(updates)
        cases.append((name, facts))

    add("ordinary docs surface", surfaces=["docs"])
    add("extra surface", surfaces=["comments", "docs", "governance"])
    add("wrong shape", task_shape="feature", side_effect_class="repo_write")
    add("medium risk", risk="medium")
    add("unknown uncertainty", uncertainty="unknown")
    add(
        "operator loop",
        continuation_mode="operator_loop",
        task_prompt="/loop\nClarify one editorial guide paragraph.",
    )
    add("runtime claim", runtime_claim=True)
    add("end-to-end claim", end_to_end_claim=True)
    add("multiple scope paths", scope=[EDITORIAL_PATH, "docs/guides/typos.md"])
    add("scope drift", scope=["docs/guides/typos.md"])
    add("uppercase", scope=["docs/guides/Notes.md"], dirty_scope=["docs/guides/Notes.md"])
    add("non-ascii", scope=["docs/guides/說明.md"], dirty_scope=["docs/guides/說明.md"])
    add("documentation alias", scope=["doc/guides/notes.md"], dirty_scope=["doc/guides/notes.md"])
    for token in (
        "governance", "agent", "agents", "adr", "adrs", "decision",
        "decisions", "security", "currentstate", "index", "readme", "claude",
        "architecture", "runbook", "runbooks", "reference", "references",
        "registry", "routing", "policy", "policies", "schema", "schemas",
        "contract", "contracts", "api", "spec", "protocol", "todo",
    ):
        path = f"docs/guides/{token}-notes.md"
        add(f"protected token {token}", scope=[path], dirty_scope=[path])
    for path in (
        "docs/guides/current-state-notes.md",
        "docs/current/guides/state-notes.md",
        "docs/guides/current-notes-for-state.md",
    ):
        add("protected current and state tokens", scope=[path], dirty_scope=[path])

    for name, facts in cases:
        r4_nodes = [
            node for node in route_task(facts)["required_role_nodes"]
            if node["role"] == "R4"
        ]
        assert len(r4_nodes) == 1, name
        assert r4_nodes[0]["native_agent"] == "R4", name
        assert r4_nodes[0]["node_class"] == "verification", name
        assert r4_nodes[0]["permission"] == "read_only", name

    traversal = deepcopy(_facts())
    traversal.update({
        "scope": ["docs/guides/../notes.md"],
        "dirty_scope": ["docs/guides/../notes.md"],
    })
    with pytest.raises(ValueError, match="safe repo-relative paths"):
        route_task(traversal)


def test_generated_saved_admission_matches_editorial_route() -> None:
    route = route_task(_facts())
    contract = task_contract_projection(route["task_facts"])
    script = "\n".join((
        "const canonicalJson = value => JSON.stringify(value);",
        render_context_admission_block(),
        f"const contract = {json.dumps(contract, ensure_ascii=False)};",
        "console.log(JSON.stringify(canonicalRouteCallNodesV1(null, contract)));",
    ))
    completed = subprocess.run(
        ["node", "-e", script], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == [
        {
            "node_id": "docs_update",
            "role": "TW",
            "native_agent": "TW",
            "requires": [],
            "node_class": "work",
            "permission": "docs_writer",
        }
    ]


def test_mixed_source_and_docs_retains_e2_e4_tw_and_r4_edges() -> None:
    facts = deepcopy(_facts())
    facts.update({
        "task_shape": "feature",
        "surfaces": ["comments", "docs", "python"],
        "side_effect_class": "repo_write",
        "objective": "Change source and its guide.",
        "scope": ["src/widget.py", "docs/guides/widget.md"],
        "dirty_scope": ["src/widget.py", "docs/guides/widget.md"],
        "task_prompt": "Change source and its guide.",
    })

    assert route_task(facts)["required_role_nodes"] == [
        {
            "node_id": "implementation", "role": "E1", "native_agent": "E1",
            "node_class": "work", "permission": "source_writer", "requires": [],
            "path_scope": ["src/widget.py"],
        },
        {
            "node_id": "independent_review", "role": "E2", "native_agent": "E2",
            "node_class": "verification", "permission": "read_only",
            "requires": ["implementation"], "path_scope": [],
        },
        {
            "node_id": "regression", "role": "E4", "native_agent": "E4-verifier",
            "node_class": "verification", "permission": "read_only",
            "requires": ["independent_review"], "path_scope": [],
        },
        {
            "node_id": "docs_projection", "role": "TW", "native_agent": "TW",
            "node_class": "work", "permission": "docs_writer",
            "requires": ["regression"], "path_scope": ["docs/guides/widget.md"],
        },
        {
            "node_id": "docs_integrity_review", "role": "R4", "native_agent": "R4",
            "node_class": "verification", "permission": "read_only",
            "requires": ["docs_projection"], "path_scope": [],
        },
    ]
