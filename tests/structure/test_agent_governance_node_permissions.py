"""Node-scoped permission downgrade and E4 review-edge tests."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_execution_dag import topological_waves  # noqa: E402
from agent_governance_node_permissions import (  # noqa: E402
    validate_node_scoped_permissions,
)
from agent_governance_routing import route_task  # noqa: E402
from agent_governance_repository_changes import writer_scope_contracts  # noqa: E402


def _route(shape: str, risk: str = "low") -> dict:
    path = {
        "implementation": "src/feature.py",
        "test": "tests/test_feature.py",
    }.get(shape)
    return route_task({
        "task_shape": shape, "surfaces": ["python"], "risk": risk,
        "uncertainty": "low", "task_prompt": f"governed {shape}",
        **({"dirty_scope": [path]} if path else {}),
    })


def _requested(role: str, native_agent: str, node_class: str, permission: str) -> dict:
    return {
        "logical_role": role,
        "platform": "claude_saved_workflow",
        "platform_requested_agent": native_agent,
        "native_binding": {
            "logical_role": role, "native_agent": native_agent,
            "node_class": node_class, "permission": permission,
        },
        "model": None, "effort": None, "isolation": None,
        "node_class": node_class, "permission": permission,
    }


def test_route_prebinds_exact_native_identity_class_and_permission() -> None:
    analysis = _route("analysis", "high")
    pa = next(node for node in analysis["nodes"] if node.get("role") == "PA")
    assert {key: pa[key] for key in ("native_agent", "node_class", "permission")} == {
        "native_agent": "PA-investigator",
        "node_class": "verification",
        "permission": "read_only",
    }

    test_route = _route("test")
    e4 = next(node for node in test_route["nodes"] if node["id"] == "test_implementation")
    assert (e4["native_agent"], e4["node_class"], e4["permission"]) == (
        "E4-writer", "work", "test_writer",
    )
    implementation = _route("implementation")
    regression = next(node for node in implementation["nodes"] if node["id"] == "regression")
    assert (regression["native_agent"], regression["node_class"], regression["permission"]) == (
        "E4-verifier", "verification", "read_only",
    )
    assert all(
        set(requirement) == {
            "node_id", "role", "native_agent", "node_class", "permission",
            "requires", "path_scope",
        }
        for requirement in implementation["required_role_nodes"]
    )
    required = {
        item["node_id"]: item for item in implementation["required_role_nodes"]
    }
    assert required["implementation"]["requires"] == []
    assert required["independent_review"]["requires"] == ["implementation"]
    assert required["regression"]["requires"] == ["independent_review"]


def test_route_projects_mixed_writer_path_ownership_without_overlap() -> None:
    route = route_task({
        "task_shape": "implementation",
        "surfaces": ["python", "docs"],
        "risk": "low",
        "uncertainty": "low",
        "task_prompt": "change source and its documentation",
        "dirty_scope": [
            ".claude/workflows/agent-wave.js",
            ".codex/schemas/closure_packet_v1.schema.json",
            "src/feature.py",
            "docs/feature.md",
        ],
    })
    required = {
        item["node_id"]: item for item in route["required_role_nodes"]
    }
    assert required["implementation"]["path_scope"] == [
        ".claude/workflows/agent-wave.js",
        ".codex/schemas/closure_packet_v1.schema.json",
        "src/feature.py",
    ]
    assert required["docs_projection"]["path_scope"] == ["docs/feature.md"]
    assert required["docs_projection"]["requires"] == ["regression"]
    assert required["docs_integrity_review"]["requires"] == ["docs_projection"]
    writer_scopes, writer_errors = writer_scope_contracts(
        route["required_role_nodes"],
        expected_dirty_scope=route["task_facts"]["dirty_scope"],
    )
    assert writer_errors == []
    assert list(writer_scopes) == ["implementation", "docs_projection"]


@pytest.mark.parametrize(
    ("backend_surface", "backend_path"),
    [("python", "api/server.py"), ("rust", "rust/src/server.rs")],
)
def test_full_stack_route_keeps_frontend_and_backend_builders_disjoint(
    backend_surface: str, backend_path: str,
) -> None:
    route = route_task({
        "task_shape": "implementation",
        "surfaces": ["gui", backend_surface, "docs"],
        "risk": "low", "uncertainty": "low",
        "task_prompt": "change the Control Console end to end",
        "dirty_scope": ["gui/src/App.tsx", backend_path, "docs/console.md"],
    })
    required = {
        item["node_id"]: item for item in route["required_role_nodes"]
    }
    assert required["implementation_backend"]["role"] == "E1"
    assert required["implementation_backend"]["path_scope"] == [backend_path]
    assert required["implementation_frontend"]["role"] == "E1a"
    assert required["implementation_frontend"]["path_scope"] == ["gui/src/App.tsx"]
    assert required["implementation_frontend"]["requires"] == [
        "implementation_backend",
    ]
    assert backend_path not in required["implementation_frontend"]["path_scope"]
    assert required["independent_review"]["requires"] == [
        "implementation_backend", "implementation_frontend",
    ]
    assert required["regression"]["requires"] == ["independent_review"]
    assert required["docs_projection"]["path_scope"] == ["docs/console.md"]
    writer_scopes, errors = writer_scope_contracts(
        route["required_role_nodes"],
        expected_dirty_scope=route["task_facts"]["dirty_scope"],
    )
    assert errors == []
    assert list(writer_scopes) == [
        "implementation_backend", "implementation_frontend", "docs_projection",
    ]


def test_control_console_static_javascript_is_frontend_not_node_backend() -> None:
    backend = (
        "program_code/exchange_connectors/bybit_connector/control_api_v1/"
        "app/main.py"
    )
    frontend = (
        "program_code/exchange_connectors/bybit_connector/control_api_v1/"
        "app/static/control.js"
    )
    route = route_task({
        "task_shape": "implementation", "surfaces": ["gui", "python"],
        "risk": "low", "uncertainty": "low",
        "task_prompt": "change the real Control Console API and browser asset",
        "dirty_scope": [backend, frontend],
    })
    required = {
        node["node_id"]: node for node in route["required_role_nodes"]
    }
    assert required["implementation_backend"]["path_scope"] == [backend]
    assert required["implementation_frontend"]["path_scope"] == [frontend]


def test_pure_deploy_skips_source_builders_but_source_plus_deploy_keeps_them() -> None:
    pure = route_task({
        "task_shape": "deploy", "surfaces": ["deploy"],
        "risk": "high", "uncertainty": "low",
        "task_prompt": "deploy an already admitted immutable source generation",
    })
    pure_ids = {node["id"] for node in pure["nodes"]}
    assert not pure_ids.intersection({
        "implementation", "implementation_backend", "implementation_frontend",
        "independent_review", "regression",
    })
    assert {"ops_preflight", "deploy_adapter_v1"} <= pure_ids

    source = route_task({
        "task_shape": "implementation", "surfaces": ["python", "deploy"],
        "risk": "high", "uncertainty": "low",
        "task_prompt": "change source and then request a fail-closed deploy",
        "dirty_scope": ["api/server.py"],
    })
    source_ids = {node["id"] for node in source["nodes"]}
    assert {"implementation", "independent_review", "regression"} <= source_ids
    assert {"ops_preflight", "deploy_adapter_v1"} <= source_ids


def test_full_stack_route_rejects_unallocatable_frontend_or_backend_scope() -> None:
    with pytest.raises(ValueError, match="missing frontend paths"):
        route_task({
            "task_shape": "implementation", "surfaces": ["gui", "python"],
            "risk": "low", "uncertainty": "low",
            "task_prompt": "mixed task with no frontend ownership",
            "dirty_scope": ["api/server.py"],
        })
    with pytest.raises(ValueError, match="missing backend paths"):
        route_task({
            "task_shape": "implementation", "surfaces": ["gui", "rust"],
            "risk": "low", "uncertainty": "low",
            "task_prompt": "mixed task with no backend ownership",
            "dirty_scope": ["gui/src/App.tsx"],
        })


def test_pure_gui_and_backend_routes_keep_single_correct_builder() -> None:
    gui = route_task({
        "task_shape": "implementation", "surfaces": ["gui"],
        "risk": "low", "uncertainty": "low",
        "task_prompt": "change only the GUI", "dirty_scope": ["gui/App.tsx"],
    })
    backend = route_task({
        "task_shape": "implementation", "surfaces": ["python"],
        "risk": "low", "uncertainty": "low",
        "task_prompt": "change only the API", "dirty_scope": ["api/server.py"],
    })
    assert next(
        node for node in gui["required_role_nodes"]
        if node["node_id"] == "implementation"
    )["role"] == "E1a"
    assert next(
        node for node in backend["required_role_nodes"]
        if node["node_id"] == "implementation"
    )["role"] == "E1"


def test_write_route_rejects_empty_dirty_scope() -> None:
    with pytest.raises(ValueError, match="repo_write.*non-empty dirty_scope"):
        route_task({
            "task_shape": "implementation", "surfaces": ["python"],
            "risk": "low", "uncertainty": "low",
            "task_prompt": "undefined write ownership",
        })


def test_e4_work_requires_e2_review_and_writer_verification_is_read_only() -> None:
    e4_work = {
        "node_id": "test_implementation", "role": "E4", "requires": [],
        "native_agent": "E4-writer", "node_class": "work",
        "permission": "test_writer",
    }
    _, errors = topological_waves([e4_work])
    assert "E4 test work requires a following E2 verification node" in errors

    e2_review = {
        "node_id": "test_adversarial_review", "role": "E2",
        "requires": ["test_implementation"], "native_agent": "E2",
        "node_class": "verification",
        "permission": "read_only",
    }
    assert topological_waves([e4_work, e2_review]) == (
        [["test_implementation"], ["test_adversarial_review"]], []
    )

    regression = {
        "node_id": "regression", "role": "E4", "requires": [],
        "native_agent": "E4-verifier", "node_class": "verification",
        "permission": "read_only",
    }
    assert topological_waves([regression]) == ([["regression"]], [])
    regression["permission"] = "test_writer"
    assert any("must be read_only" in error for error in topological_waves([regression])[1])


def test_implementation_execution_dag_cannot_drop_builder_review_regression_edges() -> None:
    tasks = [
        {
            "node_id": "implementation", "role": "E1", "requires": [],
            "native_agent": "E1", "node_class": "work",
            "permission": "source_writer",
        },
        {
            "node_id": "independent_review", "role": "E2", "requires": [],
            "native_agent": "E2", "node_class": "verification",
            "permission": "read_only",
        },
        {
            "node_id": "regression", "role": "E4", "requires": [],
            "native_agent": "E4-verifier", "node_class": "verification",
            "permission": "read_only",
        },
    ]
    _, errors = topological_waves(tasks)
    assert "implementation requires a following E2 independent review node" in errors
    assert "implementation review requires a following E4 regression node" in errors


def test_full_stack_execution_review_must_wait_for_both_builders() -> None:
    tasks = [
        {
            "node_id": "implementation_backend", "role": "E1", "requires": [],
            "native_agent": "E1", "node_class": "work",
            "permission": "source_writer",
        },
        {
            "node_id": "implementation_frontend", "role": "E1a", "requires": [],
            "native_agent": "E1a", "node_class": "work",
            "permission": "source_writer",
        },
        {
            "node_id": "independent_review", "role": "E2",
            "requires": ["implementation_backend"], "native_agent": "E2",
            "node_class": "verification", "permission": "read_only",
        },
        {
            "node_id": "regression", "role": "E4",
            "requires": ["independent_review"], "native_agent": "E4-verifier",
            "node_class": "verification", "permission": "read_only",
        },
    ]
    assert any(
        "canonical backend-to-frontend serialization" in error
        for error in topological_waves(tasks)[1]
    )
    tasks[1]["requires"] = ["implementation_backend"]
    tasks[2]["requires"].append("implementation_frontend")
    assert topological_waves(tasks) == (
        [
            ["implementation_backend"], ["implementation_frontend"],
            ["independent_review"], ["regression"],
        ],
        [],
    )
    same_wave = deepcopy(tasks)
    same_wave[1]["requires"] = []
    scopes, scope_errors = writer_scope_contracts(
        [
            {**same_wave[0], "path_scope": ["api.py"]},
            {**same_wave[1], "path_scope": ["App.tsx"]},
            {**same_wave[2], "path_scope": []},
            {**same_wave[3], "path_scope": []},
        ],
        expected_dirty_scope=["api.py", "App.tsx"],
    )
    assert list(scopes) == ["implementation_backend", "implementation_frontend"]
    assert any("transitively serialized" in error for error in scope_errors)


def test_closure_projection_rejects_writer_permission_on_verification_call() -> None:
    route = {
        "nodes": [
            {
                "id": "regression", "kind": "role", "role": "E4",
                "requires": [], "native_agent": "E4-verifier",
                "node_class": "verification", "permission": "read_only",
            }
        ]
    }
    call = {
        "node_id": "regression",
        "requested": {
            "role": "E4", "native_agent": "E4-verifier",
            "node_class": "verification", "permission": "test_writer",
        },
    }
    command = {
        "node_id": "regression", "role_id": "E4", "node_class": "verification",
        "authorization": {"policy_class": "local_test_adapter"},
    }
    errors = validate_node_scoped_permissions(
        {"calls": {"call-regression": call}, "commands": {"ev-command": command}, "changes": {}},
        route,
        {},
    )
    assert any("requested permission differs" in error for error in errors)
    assert any("used writer permission for verification" in error for error in errors)


def test_routed_pa_analysis_uses_investigator_permission() -> None:
    route = {
        "task_facts": {"side_effect_class": "none"},
        "nodes": [
            {
                "id": "pa_design", "kind": "role", "role": "PA",
                "requires": [], "native_agent": "PA-investigator",
                "node_class": "verification", "permission": "read_only",
            }
        ],
    }
    call = {
        "node_id": "pa_design",
        "requested": _requested(
            "PA", "PA-investigator", "verification", "read_only",
        ),
    }
    assert validate_node_scoped_permissions(
        {"calls": {"call-pa": call}, "commands": {}, "changes": {}}, route, {},
    ) == []

    writer_call = deepcopy(call)
    writer_call["requested"] = _requested(
        "PA", "PA-design-writer", "work", "design_writer",
    )
    errors = validate_node_scoped_permissions(
        {"calls": {"call-pa": writer_call}, "commands": {}, "changes": {}}, route, {},
    )
    assert any("requested node_class differs" in error for error in errors)

    admitted_writer = {
        "pa_design_patch": {
            "role": "PA", "native_agent": "PA-design-writer",
            "node_class": "work", "permission": "design_writer",
        },
    }
    writer_call["node_id"] = "pa_design_patch"
    assert validate_node_scoped_permissions(
        {"calls": {"call-pa-write": writer_call}, "commands": {}, "changes": {}},
        {"nodes": []}, admitted_writer,
    ) == []
