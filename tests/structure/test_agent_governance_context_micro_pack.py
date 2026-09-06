"""
MODULE_NOTE
模塊用途：驗證 W3 Context micro-pack 的精確 Markdown 選段與 current-state 路由。
主要函數：透過 compile_context、materialize_context_artifact 與
validate_context_artifact 公開 seam 驗證 source 身分、內容與完整性。
依賴：真實臨時 Git fixture、Registry 正本與既有 Context compiler。
硬邊界：fixture filesystem 只模擬 repository 邊界，不 mock 選包或選段業務邏輯。
"""

from __future__ import annotations

import subprocess
import sys
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
from agent_governance_registry import load_registry  # noqa: E402


def _init_repo(root: Path, files: dict[str, bytes]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    for args in (
        ("init",),
        ("config", "user.email", "context-test@example.invalid"),
        ("config", "user.name", "Context Test"),
        ("add", "."),
        ("commit", "-m", "baseline"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _facts(root: Path, **overrides):
    facts = {
        "task_shape": "review",
        "surfaces": ["comments"],
        "risk": "low",
        "uncertainty": "low",
        "side_effect_class": "none",
        "objective": "read one exact bounded Context section",
        "scope": ["POLICY.md"],
        "dirty_scope": ["POLICY.md"],
        "acceptance_criteria": ["only the exact selected bytes are admitted"],
        "hard_stops": ["no runtime or external effect"],
        "baseline": capture_repository_baseline(root),
        "direct_interfaces": ["compile_context_v1"],
        "previous_failure": "substring selectors could select an impostor heading",
    }
    facts.update(overrides)
    return facts


def _section_registry(source: str, heading: str):
    registry = deepcopy(load_registry())
    registry["context_packs"]["core"] = [{
        "source": source,
        "kind": "markdown_section",
        "heading": heading,
    }]
    registry["roles"]["PM"]["context_packs"] = ["core"]
    return registry


def test_compile_materialize_validate_selects_one_exact_fence_aware_section(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    heading = "## 二、Root Principles"
    _init_repo(repo, {
        "POLICY.md": (
            "# Policy\n\n"
            "## Root Principles appendix\nwrong substring\n\n"
            "```markdown\n## 二、Root Principles\nfenced impostor\n```\n\n"
            f"{heading}\nrequired bytes\n### Detail\nkept detail\n\n"
            "## 三、Next\nunrelated bytes\n"
        ).encode("utf-8"),
    })
    facts = _facts(repo)
    registry = _section_registry("POLICY.md#二、Root Principles", heading)
    artifact = materialize_context_artifact(
        compile_context("PM", facts, registry, repo), registry,
    )

    result = validate_context_artifact(
        artifact,
        expected_task_facts=facts,
        registry=registry,
        root=repo,
    )
    assert result["errors"] == []
    selected = result["plan"]["sources"][0]
    assert selected["source_kind"] == "markdown_section"
    assert selected["selector"] == heading
    assert selected["content"] == (
        "## 二、Root Principles\nrequired bytes\n### Detail\nkept detail\n\n"
    )


@pytest.mark.parametrize(
    ("document", "error"),
    [
        ("# Policy\n\n## Exact extra\nwrong\n", "match exactly one"),
        ("# Policy\n\n## Exact\none\n\n## Exact\ntwo\n", "match exactly one"),
        ("# Policy\n\n```\n## Exact\n", "balanced"),
        ("# Policy\n\n## Exact\n" + "x" * 16_385, "16KiB"),
    ],
)
def test_markdown_section_rejects_missing_duplicate_unbalanced_and_oversize(
    tmp_path: Path, document: str, error: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, {"POLICY.md": document.encode("utf-8")})
    facts = _facts(repo)

    plan = compile_context(
        "PM", facts, _section_registry("POLICY.md#Exact", "## Exact"), repo,
    )

    source = plan["sources"][0]
    assert source["status"] == "markdown_section_invalid"
    assert error in source["artifact_error"]
    assert plan["budget"]["call_allowed"] is False


def test_markdown_section_rejects_invalid_utf8_and_unsafe_source(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo, {
        "POLICY.md": b"# Policy\n\n## Exact\n\xff\n",
        "placeholder.md": b"# placeholder\n",
    })
    facts = _facts(repo)
    invalid = compile_context(
        "PM", facts, _section_registry("POLICY.md#Exact", "## Exact"), repo,
    )["sources"][0]
    unsafe = compile_context(
        "PM", facts,
        _section_registry("../POLICY.md#Exact", "## Exact"), repo,
    )["sources"][0]

    assert invalid["status"] == "markdown_section_invalid"
    assert "UTF-8" in invalid["artifact_error"]
    assert unsafe["status"] == "markdown_section_invalid"
    assert "repository" in unsafe["artifact_error"]


@pytest.mark.parametrize(
    ("surface", "uncertainty", "expected_source"),
    [
        (
            "current_workflow_state",
            "low",
            "TODO.md#Workflow optimization physical queue（source-only）",
        ),
        ("current_s2e_state", "medium", "TODO.md#S2E 當前派發投影"),
    ],
)
def test_explicit_current_state_surface_selects_the_correct_source_for_every_role(
    surface: str, uncertainty: str, expected_source: str,
) -> None:
    registry = load_registry()
    facts = _facts(
        ROOT,
        surfaces=[surface],
        uncertainty=uncertainty,
        scope=["TODO.md"],
        dirty_scope=["TODO.md"],
    )
    for role in registry["roles"]:
        plan = compile_context(role, facts, registry, ROOT)
        source_names = [source["source"] for source in plan["sources"]]
        assert expected_source in source_names, (role, source_names)
        other = (
            "TODO.md#S2E 當前派發投影"
            if surface == "current_workflow_state"
            else "TODO.md#Workflow optimization physical queue（source-only）"
        )
        assert other not in source_names, (role, source_names)


def test_stable_query_omits_both_current_state_sources() -> None:
    plan = compile_context(
        "PM",
        _facts(ROOT, scope=["AGENTS.md"], dirty_scope=["AGENTS.md"]),
    )
    assert not any(
        source["source"].startswith("TODO.md#") for source in plan["sources"]
    )


@pytest.mark.parametrize("surface", ["current_workflow_state", "current_s2e_state"])
def test_current_state_surfaces_remain_low_risk_narrow_queries(surface: str) -> None:
    plan = compile_context(
        "PM",
        _facts(
            ROOT,
            task_shape="query",
            surfaces=[surface],
            direct_interfaces=[],
            scope=["TODO.md"],
            dirty_scope=["TODO.md"],
        ),
    )
    assert plan["execution_dag_binding"]["nodes"] == []
    assert plan["budget"]["call_allowed"] is True
    assert any(
        source["source"].startswith("TODO.md#") for source in plan["sources"]
    )


def test_core_and_docs_keep_exact_mandatory_rules_without_full_file_preload() -> None:
    core = compile_context(
        "PM",
        _facts(ROOT, scope=["AGENTS.md"], dirty_scope=["AGENTS.md"]),
    )
    core_by_name = {source["source"]: source for source in core["sources"]}
    assert "Single controlled write entry for orders/execution." in core_by_name[
        "CLAUDE.md#二、Root Principles"
    ]["content"]
    assert "Do not fake AI calls, trading activity, fills" in core_by_name[
        "CLAUDE.md#四、Hard Boundaries"
    ]["content"]
    assert all(
        source["source_kind"] == "markdown_section"
        for name, source in core_by_name.items()
        if name.startswith("CLAUDE.md#")
    )

    docs = compile_context(
        "R4",
        _facts(
            ROOT,
            surfaces=["docs"],
            risk="medium",
            uncertainty="medium",
            scope=["docs/README.md"],
            dirty_scope=["docs/README.md"],
        ),
    )
    docs_sections = [
        source for source in docs["sources"]
        if source["source"].startswith("docs/README.md#")
    ]
    assert {source["selector"] for source in docs_sections} == {
        "## 当前入口速查",
        "## Multi-Agent 接手路径",
        "## 强制规则 (Mandatory Rules)",
        "## 文件命名规范 (File Naming Convention)",
        "## 日志分类说明 (Log Categories)",
        "## 日志书写原则 (Writing Principles)",
        "## 文档索引 (Document Index)",
    }
    combined = "".join(source["content"] for source in docs_sections)
    assert "当前 active state 不进文档索引" in combined
    assert "文件必须放到对应分类目录" in combined
    assert "移动/重命名路径前先更新 `_indexes/path_redirects.md`" in combined
    assert sum(source["bytes"] for source in docs_sections) < len(
        (ROOT / "docs/README.md").read_bytes()
    ) // 2


def test_python_validation_rejects_resigned_omission_of_required_state_source() -> None:
    registry = load_registry()
    facts = _facts(
        ROOT,
        surfaces=["current_workflow_state"],
        scope=["TODO.md"],
        dirty_scope=["TODO.md"],
    )
    plan = compile_context("PM", facts, registry, ROOT)
    omitted = deepcopy(plan)
    omitted["sources"] = [
        source for source in omitted["sources"]
        if source["source"] != (
            "TODO.md#Workflow optimization physical queue（source-only）"
        )
    ]
    omitted["selected_packs"].remove("active_state")
    omitted["shared_packs"].remove("active_state")
    omitted["context_digest"] = context_plan_digest(omitted)
    resigned = materialize_context_artifact(omitted, registry)

    result = validate_context_artifact(
        resigned, expected_task_facts=facts, registry=registry, root=ROOT,
    )
    assert any(
        "Registry-selected Context packs differ" in error
        or "source inventory differs" in error
        for error in result["errors"]
    )

    wrong_kind = deepcopy(plan)
    state_source = next(
        source for source in wrong_kind["sources"]
        if source["source"] == (
            "TODO.md#Workflow optimization physical queue（source-only）"
        )
    )
    state_source["source_kind"] = "repository_source"
    wrong_kind["context_digest"] = context_plan_digest(wrong_kind)
    resigned_kind = materialize_context_artifact(wrong_kind, registry)
    kind_result = validate_context_artifact(
        resigned_kind, expected_task_facts=facts, registry=registry, root=ROOT,
    )
    assert any(
        "differs from recaptured repository bytes" in error
        for error in kind_result["errors"]
    )


def test_unrelated_todo_section_does_not_change_selected_semantic_context(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    heading = "## Workflow optimization physical queue（source-only）"
    _init_repo(repo, {
        "TODO.md": (
            "# TODO\n\n"
            f"{heading}\n\n### ACTIVE\nrequired physical row\n\n"
            "## Unrelated\nold ambient text\n"
        ).encode("utf-8"),
    })
    registry = deepcopy(load_registry())
    registry["roles"]["PM"]["context_packs"] = []
    registry["context_packs"]["active_state"] = [{
        "source": "TODO.md#Workflow optimization physical queue（source-only）",
        "kind": "markdown_section",
        "heading": heading,
        "required_when": {"surfaces_any": ["current_workflow_state"]},
    }]
    facts = _facts(
        repo,
        surfaces=["current_workflow_state"],
        scope=["TODO.md"],
        dirty_scope=["TODO.md"],
    )
    before = materialize_context_artifact(
        compile_context("PM", facts, registry, repo), registry,
    )
    (repo / "TODO.md").write_text(
        "# TODO\n\n"
        f"{heading}\n\n### ACTIVE\nrequired physical row\n\n"
        "## Unrelated\nchanged ambient text that must not enter Context\n",
        encoding="utf-8",
    )
    after_facts = {**facts, "baseline": capture_repository_baseline(repo)}
    after = materialize_context_artifact(
        compile_context("PM", after_facts, registry, repo), registry,
    )

    assert before["artifact_digest"] != after["artifact_digest"]
    assert before["shared_task_context_digest"] == after[
        "shared_task_context_digest"
    ]
