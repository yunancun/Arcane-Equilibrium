"""Reachability tests for typed conditional Context packs."""

from __future__ import annotations

import sys
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_execution import (  # noqa: E402
    capture_repository_baseline,
    compile_context,
    materialize_context_artifact,
    validate_context_artifact,
)
from agent_governance_execution import context_plan_digest  # noqa: E402
import agent_governance_context as context_producer  # noqa: E402
from agent_governance_context_refs import (  # noqa: E402
    EMPTY_DISPATCH_MARKER,
    project_todo_active_rows,
    project_todo_dispatch_projection,
)
from agent_governance_registry import load_registry, validate_registry  # noqa: E402


def _facts(**overrides):
    facts = {
        "task_shape": "review",
        "surfaces": ["comments"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "none",
        "objective": "review one stable source-only interface",
        "scope": ["AGENTS.md"],
        "dirty_scope": ["AGENTS.md"],
        "acceptance_criteria": ["the admitted role can start without fake evidence"],
        "hard_stops": ["no runtime or external effect"],
        "baseline": capture_repository_baseline(),
        "direct_interfaces": ["context_reachability_probe_v1"],
        "previous_failure": "descriptive virtual sources blocked every dispatch",
    }
    facts.update(overrides)
    return facts


def test_narrow_stable_pm_does_not_preload_active_state() -> None:
    plan = compile_context("PM", _facts())
    assert "TODO.md" not in [source["source"] for source in plan["sources"]]
    assert plan["unresolved_sources"] == []
    assert plan["budget"]["pass_allowed"] is True


@pytest.mark.parametrize(
    ("role", "surfaces", "expected_debt"),
    [
        ("PM", ["multi_agent"], set()), ("PA", ["architecture"], set()),
        ("FA", ["functional"], set()), ("CC", ["governance"], set()),
        ("E1", ["python"], set()), ("E1a", ["gui"], set()),
        ("E2", ["python"], set()), ("E3", ["security"], set()),
        ("E4", ["acceptance"], set()), ("E5", ["performance"], set()),
        ("QA", ["functional"], set()), ("QC", ["quant"], set()),
        ("MIT", ["ml"], set()), ("AI-E", ["consumption"], set()),
        ("BB", ["bybit"], {"official Bybit source when freshness matters"}),
        ("IB", ["ibkr"], {"official IBKR source when freshness matters"}),
        ("OPS", ["operations"], {"runtime observation"}),
        ("A3", ["visual"], {"viewport/accessibility evidence"}),
        ("R4", ["docs"], set()), ("TW", ["docs"], set()),
    ],
)
def test_every_registry_role_has_a_spawnable_representative_source_task(
    role: str, surfaces: list[str], expected_debt: set[str],
) -> None:
    plan = compile_context(
        role,
        _facts(
            surfaces=surfaces,
            risk="medium",
            uncertainty="medium",
            objective=f"run the representative source-only {role} review",
        ),
    )
    assert set(plan["evidence_debt"]) == expected_debt, (
        role, plan["evidence_debt"],
    )
    assert plan["budget"]["call_allowed"] is True, (
        role, plan["budget"],
    )
    assert plan["budget"]["claim_pass_eligible"] is (not expected_debt)


@pytest.mark.parametrize(
    ("role", "overrides", "required_sources"),
    [
        (
            "OPS",
            {"surfaces": ["runtime"], "runtime_claim": True},
            {"runtime observation"},
        ),
        (
            "QA",
            {"surfaces": ["runtime"], "end_to_end_claim": True},
            {"runtime observation", "business outcome observation"},
        ),
        (
            "BB",
            {"surfaces": ["bybit"]},
            {"official Bybit source when freshness matters"},
        ),
        (
            "IB",
            {"surfaces": ["ibkr"]},
            {"official IBKR source when freshness matters"},
        ),
        (
            "QC",
            {
                "surfaces": ["public_web_read"],
                "side_effect_class": "public_web_read",
            },
            {"external policy observation"},
        ),
    ],
)
def test_claim_required_runtime_external_and_broker_evidence_stays_fail_closed(
    role: str, overrides: dict, required_sources: set[str],
) -> None:
    plan = compile_context(role, _facts(risk="high", **overrides))
    assert required_sources <= set(plan["unresolved_sources"])
    assert required_sources <= set(plan["evidence_debt"])
    assert plan["budget"]["call_allowed"] is True
    assert plan["budget"]["claim_pass_eligible"] is False
    assert plan["budget"]["pass_allowed"] is True
    assert {item["source"] for item in plan["acquisition_plan"]} >= required_sources


def test_caller_producer_label_cannot_self_attest_required_runtime_evidence() -> None:
    plan = compile_context(
        "OPS",
        _facts(
            risk="high",
            surfaces=["runtime"],
            runtime_claim=True,
            evidence_state={
                "runtime observation": {
                    "producer": "caller_claimed_runtime_producer_v1",
                }
            },
        ),
    )
    runtime = next(
        source for source in plan["sources"]
        if source["source"] == "runtime observation"
    )
    assert runtime["status"] == "unbacked_evidence_state"
    assert "runtime observation" in plan["unresolved_sources"]


def test_local_inventory_context_is_admissible_through_public_artifact_validator() -> None:
    facts = _facts(
        risk="high", surfaces=["architecture"],
        objective="admit deterministic local architecture inventories",
    )
    artifact = materialize_context_artifact(compile_context("PA", facts))
    result = validate_context_artifact(artifact, expected_task_facts=facts)
    assert result["errors"] == []


def test_context_required_when_rejects_unknown_surface_typo() -> None:
    registry = deepcopy(load_registry())
    registry["context_packs"]["active_state"][0]["required_when"]["surfaces_any"].append(
        "runtiem"
    )
    assert any("unknown surface" in error for error in validate_registry(registry, ROOT))


def test_full_profit_and_incident_context_activate_bounded_current_todo() -> None:
    for surface in ("full_audit", "profit_diagnosis", "incident_rca"):
        plan = compile_context(
            "PM",
            _facts(
                surfaces=[surface],
                risk="medium" if surface != "full_audit" else "unknown",
                uncertainty="low",
            ),
        )
        todo = next(
            source for source in plan["sources"]
            if source["source"] == "TODO.md#S2E 當前派發投影"
        )
        assert todo["content"] == {
            "schema_version": "todo_dispatch_projection_v1",
            "projection_state": "EMPTY",
            "active_rows": [],
            "active_count": 0,
            "dispatchable": False,
            "next_action": None,
        }
        assert todo["planned_tokens"] < todo["full_file_token_estimate"]


def test_active_state_contains_the_exact_empty_dispatch_projection() -> None:
    plan = compile_context(
        "PM",
        _facts(
            surfaces=["runtime"],
            risk="high",
            objective="select the one current AI/ML work package",
        ),
    )
    todo = next(
        source for source in plan["sources"]
        if source["source"] == "TODO.md#S2E 當前派發投影"
    )
    content = todo["content"]
    assert content == {
        "schema_version": "todo_dispatch_projection_v1",
        "projection_state": "EMPTY",
        "active_rows": [],
        "active_count": 0,
        "dispatchable": False,
        "next_action": None,
    }
    assert todo["bytes"] < 8_192
    assert todo["planned_tokens"] < 2_048
    assert todo["digest"] == todo["content_digest"]


def test_active_state_projection_fails_closed_for_duplicate_active_or_missing_dependency() -> None:
    table = (
        "### S2E 當前 ACTIVE 派發\n\n"
        "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
        "|---|---|---|---|---|\n"
        "| `S2E.1` | SOURCE_LANDED | none | done | done |\n"
        "| `S2E.2` | ACTIVE | S2E.1 | work | pass |\n"
    ).encode()
    spec = {
        "source": "TODO.md#S2E 當前 ACTIVE 派發",
        "kind": "todo_active_rows",
        "heading": "S2E 當前 ACTIVE 派發",
        "id_column": "ID",
        "status_column": "Lane／狀態",
        "dependency_column": "依賴",
        "dependency_depth": 1,
        "required_when": {"surfaces_any": ["runtime"]},
    }
    assert b"`S2E.1`" in project_todo_active_rows(table, spec)

    duplicate = table + b"| `S2E.3` | ACTIVE | S2E.1 | work | pass |\n"
    with pytest.raises(ValueError, match="exactly one ACTIVE"):
        project_todo_active_rows(duplicate, spec)

    missing = table.replace(b"S2E.1 | work", b"S2E.9 | work")
    with pytest.raises(ValueError, match="missing dependency"):
        project_todo_active_rows(missing, spec)


def test_dispatch_projection_accepts_the_exact_empty_marker() -> None:
    document = (
        "# TODO\n\n"
        "### S2E 當前派發投影\n\n"
        "S2E-DISPATCH-PROJECTION:\n"
        "schema_version=todo_dispatch_projection_v1\n"
        "queue_state=NO_ACTIVE_UNIT\n"
        "active_unit_id=null\n"
        "active_count=0\n"
        "next_candidate=S2E-LW2\n"
        "next_candidate_state=WAITING_FRESH_ADMISSION\n"
        "dispatchable=false\n"
        "next_action=null\n\n"
        "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
        "|---|---|---|---|---|\n"
        "| `S2E.2b-2` | WAITING | S2E.2b-1 | future | later |\n"
    ).encode()
    spec = {
        "source": "TODO.md#S2E 當前派發投影",
        "kind": "todo_dispatch_projection",
        "heading": "S2E 當前派發投影",
        "id_column": "ID",
        "status_column": "Lane／狀態",
        "dependency_column": "依賴",
        "dependency_depth": 1,
        "required_when": {"surfaces_any": ["runtime"]},
    }

    assert project_todo_dispatch_projection(document, spec) == {
        "schema_version": "todo_dispatch_projection_v1",
        "projection_state": "EMPTY",
        "active_rows": [],
        "active_count": 0,
        "dispatchable": False,
        "next_action": None,
    }


def test_dispatch_projection_rejects_empty_marker_with_an_active_row() -> None:
    document = (
        "# TODO\n\n"
        "### S2E 當前派發投影\n\n"
        "S2E-DISPATCH-PROJECTION:\n"
        "schema_version=todo_dispatch_projection_v1\n"
        "queue_state=NO_ACTIVE_UNIT\n"
        "active_unit_id=null\n"
        "active_count=0\n"
        "next_candidate=S2E-LW2\n"
        "next_candidate_state=WAITING_FRESH_ADMISSION\n"
        "dispatchable=false\n"
        "next_action=null\n\n"
        "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
        "|---|---|---|---|---|\n"
        "| `S2E.2b-2` | ACTIVE | S2E.2b-1 | current | pass |\n"
    ).encode()
    spec = {
        "source": "TODO.md#S2E 當前派發投影",
        "kind": "todo_dispatch_projection",
        "heading": "S2E 當前派發投影",
        "id_column": "ID",
        "status_column": "Lane／狀態",
        "dependency_column": "依賴",
        "dependency_depth": 1,
        "required_when": {"surfaces_any": ["runtime"]},
    }

    with pytest.raises(ValueError, match="EMPTY marker cannot coexist with ACTIVE"):
        project_todo_dispatch_projection(document, spec)


def test_dispatch_projection_preserves_one_active_row_and_direct_dependencies() -> None:
    document = (
        "# TODO\n\n"
        "### S2E 當前派發投影\n\n"
        "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
        "|---|---|---|---|---|\n"
        "| `S2E.2b-1` | SOURCE_LANDED | none | dependency | done |\n"
        "| `S2E.2b-2` | ACTIVE | S2E.2b-1 | current | pass |\n"
        "| `S2E.2b-3` | WAITING | S2E.2b-2 | later | later |\n"
    ).encode()
    spec = {
        "source": "TODO.md#S2E 當前派發投影",
        "kind": "todo_dispatch_projection",
        "heading": "S2E 當前派發投影",
        "id_column": "ID",
        "status_column": "Lane／狀態",
        "dependency_column": "依賴",
        "dependency_depth": 1,
        "required_when": {"surfaces_any": ["runtime"]},
    }

    payload = project_todo_dispatch_projection(document, spec)

    assert payload["schema_version"] == "todo_dispatch_projection_v1"
    assert payload["projection_state"] == "ACTIVE"
    assert payload["active_count"] == 1
    assert payload["dispatchable"] is True
    assert payload["next_action"] == "S2E.2b-2"
    assert len(payload["active_rows"]) == 1
    projection = payload["active_rows"][0]["content"]
    assert "`S2E.2b-1`" in projection
    assert "`S2E.2b-2`" in projection
    assert "`S2E.2b-3`" not in projection


def test_empty_dispatch_context_capture_contains_payload_and_full_file_estimate(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    todo = repo / "TODO.md"
    todo.write_text(
        "# TODO\n\n"
        "unselected full-file bytes\n\n"
        "### S2E 當前派發投影\n\n"
        "S2E-DISPATCH-PROJECTION:\n"
        "schema_version=todo_dispatch_projection_v1\n"
        "queue_state=NO_ACTIVE_UNIT\n"
        "active_unit_id=null\n"
        "active_count=0\n"
        "next_candidate=S2E-LW2\n"
        "next_candidate_state=WAITING_FRESH_ADMISSION\n"
        "dispatchable=false\n"
        "next_action=null\n\n"
        "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
        "|---|---|---|---|---|\n"
        "| `S2E.2b-2` | WAITING | S2E.2b-1 | future | later |\n",
        encoding="utf-8",
    )
    for args in (
        ("init",),
        ("config", "user.email", "context-test@example.invalid"),
        ("config", "user.name", "Context Test"),
        ("add", "."),
        ("commit", "-m", "baseline"),
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    registry = deepcopy(load_registry())
    registry["roles"]["PM"]["context_packs"] = ["active_state"]
    registry["context_packs"]["active_state"] = [{
        "source": "TODO.md#S2E 當前派發投影",
        "kind": "todo_dispatch_projection",
        "heading": "S2E 當前派發投影",
        "id_column": "ID",
        "status_column": "Lane／狀態",
        "dependency_column": "依賴",
        "dependency_depth": 1,
        "required_when": {"surfaces_any": ["runtime"]},
    }]
    facts = _facts(
        surfaces=["runtime"],
        risk="high",
        uncertainty="high",
        baseline=capture_repository_baseline(repo),
        scope=["TODO.md"],
        dirty_scope=["TODO.md"],
    )

    plan = compile_context("PM", facts, registry, repo)
    source = plan["sources"][0]

    assert source["status"] == "pinned"
    assert source["content"] == {
        "schema_version": "todo_dispatch_projection_v1",
        "projection_state": "EMPTY",
        "active_rows": [],
        "active_count": 0,
        "dispatchable": False,
        "next_action": None,
    }
    full_bytes = todo.read_bytes()
    assert source["source_bytes"] == len(full_bytes)
    assert source["full_file_token_estimate"] == max(1, (len(full_bytes) + 3) // 4)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (
            "### S2E 當前派發投影\n\n"
            "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
            "|---|---|---|---|---|\n"
            "| `S2E.2b-2` | WAITING | S2E.2b-1 | future | later |\n",
            "EMPTY marker",
        ),
        (
            "### S2E 當前派發投影\n\n"
            "S2E-DISPATCH-PROJECTION:\n"
            "schema_version=todo_dispatch_projection_v1\n"
            "queue_state=NO_ACTIVE_UNIT\nactive_unit_id=null\nactive_count=0\n"
            "next_candidate=S2E-LW2\n"
            "next_candidate_state=WAITING_FRESH_ADMISSION\n"
            "dispatchable=true\nnext_action=null\n\n"
            "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
            "|---|---|---|---|---|\n"
            "| `S2E.2b-2` | WAITING | S2E.2b-1 | future | later |\n",
            "EMPTY marker",
        ),
        (
            "### S2E 當前派發投影\n\n"
            "S2E-DISPATCH-PROJECTION:\n"
            "schema_version=todo_dispatch_projection_v1\n"
            "queue_state=NO_ACTIVE_UNIT\nactive_unit_id=null\nactive_count=0\n"
            "next_candidate=S2E-LW2\n"
            "next_candidate_state=WAITING_FRESH_ADMISSION\n"
            "dispatchable=false\nnext_action=S2E-LW2\n\n"
            "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
            "|---|---|---|---|---|\n"
            "| `S2E.2b-2` | WAITING | S2E.2b-1 | future | later |\n",
            "EMPTY marker",
        ),
        (
            "### S2E 當前派發投影\n\n"
            "S2E-DISPATCH-PROJECTION:\n"
            "schema_version=todo_dispatch_projection_v1\n"
            "queue_state=ACTIVE_UNIT\nactive_unit_id=S2E.2b-2\nactive_count=1\n"
            "next_candidate=S2E-LW2\n"
            "next_candidate_state=WAITING_FRESH_ADMISSION\n"
            "dispatchable=true\nnext_action=S2E.2b-2\n\n"
            "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
            "|---|---|---|---|---|\n"
            "| `S2E.2b-1` | SOURCE_LANDED | none | dependency | done |\n"
            "| `S2E.2b-2` | ACTIVE | S2E.2b-1 | current | pass |\n",
            "EMPTY marker cannot coexist with ACTIVE",
        ),
        (
            "### S2E 當前派發投影\n\n"
            f"{EMPTY_DISPATCH_MARKER}\n{EMPTY_DISPATCH_MARKER}\n"
            "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
            "|---|---|---|---|---|\n"
            "| `S2E.2b-2` | WAITING | S2E.2b-1 | future | later |\n",
            "EMPTY marker",
        ),
        (
            "### S2E 當前派發投影\n\n"
            "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
            "|---|---|---|---|---|\n"
            "| `S2E.2b-1` | SOURCE_LANDED | none | dependency | done |\n"
            "| `S2E.2b-2` | ACTIVE | S2E.2b-1 | current | pass |\n"
            "| `S2E.2b-3` | ACTIVE | S2E.2b-1 | current | pass |\n",
            "at most one ACTIVE",
        ),
        (
            "### S2E 當前 ACTIVE 派發\n\n"
            "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
            "|---|---|---|---|---|\n"
            "| `S2E.2b-2` | ACTIVE | S2E.2b-1 | current | pass |\n",
            "heading",
        ),
    ],
)
def test_dispatch_projection_fails_closed_for_illegal_queue_states(
    document: str, message: str,
) -> None:
    spec = {
        "source": "TODO.md#S2E 當前派發投影",
        "kind": "todo_dispatch_projection",
        "heading": "S2E 當前派發投影",
        "id_column": "ID",
        "status_column": "Lane／狀態",
        "dependency_column": "依賴",
        "dependency_depth": 1,
        "required_when": {"surfaces_any": ["runtime"]},
    }
    with pytest.raises(ValueError, match=message):
        project_todo_dispatch_projection(document.encode(), spec)


def test_dispatch_projection_ignores_active_rows_outside_the_exact_section() -> None:
    marker = (
        "S2E-DISPATCH-PROJECTION:\n"
        "schema_version=todo_dispatch_projection_v1\n"
        "queue_state=NO_ACTIVE_UNIT\nactive_unit_id=null\nactive_count=0\n"
        "next_candidate=S2E-LW2\n"
        "next_candidate_state=WAITING_FRESH_ADMISSION\n"
        "dispatchable=false\nnext_action=null\n"
    )
    document = (
        "### Another lane\n\n"
        "| ID | Lane／狀態 | 依賴 |\n|---|---|---|\n"
        "| `OTHER` | ACTIVE | none |\n\n"
        "### S2E 當前派發投影\n\n"
        f"{marker}\n"
        "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
        "|---|---|---|---|---|\n"
        "| `S2E.2b-2` | WAITING | S2E.2b-1 | future | later |\n"
    ).encode()
    spec = {
        "source": "TODO.md#S2E 當前派發投影",
        "kind": "todo_dispatch_projection",
        "heading": "S2E 當前派發投影",
        "id_column": "ID",
        "status_column": "Lane／狀態",
        "dependency_column": "依賴",
        "dependency_depth": 1,
        "required_when": {"surfaces_any": ["runtime"]},
    }
    assert project_todo_dispatch_projection(document, spec)["projection_state"] == "EMPTY"


def test_unrelated_todo_row_does_not_change_model_visible_context(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    todo = repo / "TODO.md"
    prefix = (
        "# TODO\n\n### S2E 當前派發投影\n\n"
        "| ID | Lane／狀態 | 依賴 | 精確工作 | 驗收／下一步 |\n"
        "|---|---|---|---|---|\n"
        "| `S2E.1` | SOURCE_LANDED | none | dependency | done |\n"
        "| `S2E.2` | ACTIVE | S2E.1 | current work | pass |\n"
    )
    todo.write_text(
        prefix + "| `S2E.3` | WAITING | S2E.2 | unrelated v1 | later |\n",
        encoding="utf-8",
    )
    for args in (
        ("init",),
        ("config", "user.email", "context-test@example.invalid"),
        ("config", "user.name", "Context Test"),
        ("add", "."),
        ("commit", "-m", "baseline"),
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    registry = deepcopy(load_registry())
    registry["roles"]["PM"]["context_packs"] = ["active_state"]

    def facts() -> dict:
        return _facts(
            surfaces=["comments"],
            risk="medium",
            uncertainty="high",
            scope=["TODO.md"],
            dirty_scope=["TODO.md"],
            baseline=capture_repository_baseline(repo),
            objective="select the unique active work package",
        )

    first = compile_context("PM", facts(), registry, repo)
    first_artifact = materialize_context_artifact(first, registry)
    first_source = first["sources"][0]
    todo.write_text(
        prefix
        + "| `S2E.3` | WAITING | S2E.2 | unrelated v2 with more bytes | later |\n",
        encoding="utf-8",
    )
    second = compile_context("PM", facts(), registry, repo)
    second_artifact = materialize_context_artifact(second, registry)
    second_source = second["sources"][0]
    assert second_source["content_digest"] == first_source["content_digest"]
    assert second_source["planned_tokens"] == first_source["planned_tokens"]
    assert (
        second_artifact["shared_task_context_digest"]
        == first_artifact["shared_task_context_digest"]
    )
    assert second_artifact["semantic_input_tokens"] == first_artifact["semantic_input_tokens"]


def test_high_cardinality_interface_inventory_is_bounded_and_spawnable() -> None:
    plan = compile_context(
        "E5",
        _facts(
            surfaces=["performance"],
            risk="medium",
            uncertainty="medium",
            direct_interfaces=["test"],
            objective="profile the broad test interface without preloading its full grep corpus",
        ),
    )
    callers = next(source for source in plan["sources"] if source["source"] == "direct callers")
    tests = next(
        source for source in plan["sources"]
        if source["source"] == "focused acceptance tests"
    )
    assert callers["content"]["match_count"] > len(callers["content"]["matches"])
    assert tests["content"]["match_count"] > len(tests["content"]["matches"])
    assert len(callers["content"]["matches"]) <= 64
    assert len(tests["content"]["matches"]) <= 64
    assert plan["budget"]["compiler_estimated_input_tokens"] < 24_000
    assert plan["budget"]["call_allowed"] is True


def test_single_generated_receipt_line_cannot_exhaust_context_budget() -> None:
    prefix = "governed_interface="
    oversized = prefix + ("x" * 250_000)
    matches = [{"path": "receipts/generated.json", "line": 1, "text": oversized}]

    inventory = context_producer._bounded_match_inventory(matches)
    preview = inventory["matches"][0]

    assert len(preview["text"].encode("utf-8")) <= (
        context_producer.MAX_INLINE_MATCH_TEXT_BYTES
    )
    assert preview["text_truncated"] is True
    assert preview["text_bytes"] == len(oversized.encode("utf-8"))
    assert preview["text_digest"] == context_producer._sha256_bytes(
        oversized.encode("utf-8")
    )

    changed_tail = [{**matches[0], "text": oversized[:-1] + "y"}]
    changed_inventory = context_producer._bounded_match_inventory(changed_tail)
    assert changed_inventory["matches"][0]["text"] == preview["text"]
    assert changed_inventory["manifest_digest"] != inventory["manifest_digest"]
    assert changed_inventory["matches"][0]["text_digest"] != preview["text_digest"]


def test_standard_review_band_avoids_a_more_expensive_duplicate_context_split() -> None:
    facts = _facts(
        surfaces=["performance"], risk="medium", uncertainty="medium",
        direct_interfaces=["context"],
        objective="review the real Context interface without duplicating core and callers",
    )
    base_plan = compile_context("E5", facts)
    base_budget = base_plan["budget"]
    reserve_end = (
        base_budget["target_context_tokens"]
        + base_budget["quality_reserve_context_tokens"]
    )
    required_padding = max(
        0, 4 * (reserve_end + 1 - base_budget["estimated_tokens"]),
    )
    plan = None
    for extra_bytes in range(required_padding, required_padding + 8_193, 512):
        candidate = compile_context(
            "E5", {
                **facts,
                "task_prompt": "Review the bound Context interface. " + "x" * extra_bytes,
            },
        )
        candidate_budget = candidate["budget"]
        if (
            reserve_end < candidate_budget["estimated_tokens"]
            < candidate_budget["max_context_tokens_per_call"]
        ):
            plan = candidate
            break
    assert plan is not None, (
        "bounded deterministic padding could not reach the reviewed band",
        base_budget,
    )
    budget = plan["budget"]
    assert (
        budget["target_context_tokens"]
        + budget["quality_reserve_context_tokens"]
    ) == reserve_end
    assert reserve_end < budget["estimated_tokens"] < budget["max_context_tokens_per_call"]
    assert budget["action"] == "review_required"
    assert budget["review_required"] is True
    assert "avoids duplicate" in budget["review_rationale"]
    assert budget["call_allowed"] is True


def test_shared_task_prefix_is_identical_before_small_role_deltas() -> None:
    facts = _facts(
        task_shape="review", surfaces=["python"], risk="medium", uncertainty="medium",
        objective="independently inspect one admitted Python interface",
    )
    artifacts = {
        role: materialize_context_artifact(compile_context(role, facts))
        for role in ("E1", "E2", "E4")
    }
    assert len({item["shared_task_context_digest"] for item in artifacts.values()}) == 1
    assert len({item["shared_task_context_canonical"] for item in artifacts.values()}) == 1
    assert len({item["role_context_delta_digest"] for item in artifacts.values()}) == 3
    for role, artifact in artifacts.items():
        assert f'"logical_role":"{role}"' in artifact["role_context_delta_canonical"]
        assert artifact["semantic_input_tokens"] < artifact["canonical_plan"].__len__() // 4


def test_semantic_projection_tamper_is_rejected_before_call_admission() -> None:
    facts = _facts(surfaces=["python"], risk="medium", uncertainty="medium")
    artifact = materialize_context_artifact(compile_context("E2", facts))
    forged = deepcopy(artifact)
    forged["role_context_delta_canonical"] = forged["role_context_delta_canonical"].replace(
        '"logical_role":"E2"', '"logical_role":"E1"',
    )
    result = validate_context_artifact(forged, expected_task_facts=facts)
    assert any("role_context_delta_canonical" in error for error in result["errors"])


def test_unrelated_ambient_generation_changes_full_envelope_not_semantic_cache() -> None:
    facts = _facts(surfaces=["python"], risk="medium", uncertainty="medium")
    original = compile_context("E2", facts)
    changed = deepcopy(original)
    changed["task_contract"]["baseline"]["dirty_diff_hash"] = "sha256:" + "9" * 64
    changed["mandatory_content"]["baseline"] = changed["task_contract"]["baseline"]
    for source in changed["sources"]:
        source["baseline"] = changed["task_contract"]["baseline"]
    changed["context_digest"] = context_plan_digest(changed)
    original_artifact = materialize_context_artifact(original)
    changed_artifact = materialize_context_artifact(changed)
    assert original_artifact["artifact_digest"] != changed_artifact["artifact_digest"]
    assert original_artifact["shared_task_context_digest"] == changed_artifact["shared_task_context_digest"]
    assert "repository_bytes_v1" not in original_artifact["shared_task_context_canonical"]


def test_verdict_evidence_freshness_changes_semantic_cache_digest() -> None:
    facts = _facts(surfaces=["bybit"], risk="medium", uncertainty="medium")
    original = compile_context("BB", facts)
    changed = deepcopy(original)
    evidence = next(
        source for source in changed["sources"]
        if source["source"] == "official Bybit source when freshness matters"
    )
    evidence["observed_at"] = "2026-07-11T00:00:00+00:00"
    evidence["expires_at"] = "2026-07-12T00:00:00+00:00"
    evidence["producer"] = {"id": "external_policy_capture_adapter_v1", "input_digest": "sha256:" + "1" * 64}
    changed["context_digest"] = context_plan_digest(changed)
    assert (
        materialize_context_artifact(original)["shared_task_context_digest"]
        != materialize_context_artifact(changed)["shared_task_context_digest"]
    )
