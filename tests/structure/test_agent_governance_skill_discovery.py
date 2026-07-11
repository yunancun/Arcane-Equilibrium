"""Codex discovery contract for the shared development-agent skill corpus."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 runner
    import tomli as tomllib  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[2]
CLAUDE_SKILLS = ROOT / ".claude" / "skills"
CODEX_SKILLS = ROOT / ".agents" / "skills"
REGISTRY = ROOT / ".codex" / "agent_registry_v1.json"


def _frontmatter(skill_file: Path) -> dict[str, str]:
    lines = skill_file.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---", f"{skill_file} has no YAML frontmatter"
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:  # pragma: no cover - assertion message is clearer
        raise AssertionError(f"{skill_file} has unclosed YAML frontmatter") from exc
    fields: dict[str, str] = {}
    for line in lines[1:closing]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def _canonical_skill_names() -> set[str]:
    return {
        path.parent.name
        for path in CLAUDE_SKILLS.glob("*/SKILL.md")
        if path.is_file()
    }


def test_shared_skills_are_real_repo_discoverable_codex_symlinks() -> None:
    """Codex officially scans .agents/skills and supports symlinked skill folders."""

    canonical_names = _canonical_skill_names()
    assert canonical_names
    for name in sorted(canonical_names):
        adapter = CODEX_SKILLS / name
        assert adapter.is_symlink(), f"{name} is not a zero-drift Codex skill adapter"
        assert os.readlink(adapter) == f"../../.claude/skills/{name}"
        assert adapter.resolve(strict=True) == (CLAUDE_SKILLS / name).resolve(strict=True)


def test_shared_skill_metadata_is_discoverable_and_name_stable() -> None:
    names_seen: set[str] = set()
    for name in sorted(_canonical_skill_names()):
        fields = _frontmatter(CODEX_SKILLS / name / "SKILL.md")
        assert fields.get("name") == name
        assert fields.get("description"), f"{name} has no trigger description"
        assert name not in names_seen
        names_seen.add(name)


def test_registry_skill_bindings_have_codex_discovery_targets() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    role_skills = {
        skill
        for role in registry["roles"].values()
        for skill in role.get("skills", [])
    }
    on_demand = set(registry["on_demand_skills"])
    for name in sorted(role_skills | on_demand):
        skill_file = CODEX_SKILLS / name / "SKILL.md"
        assert skill_file.is_file(), f"Registry skill {name} is not Codex-discoverable"
        assert _frontmatter(skill_file).get("name") == name


def test_native_agents_name_exact_discoverable_skill_paths() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    adapters = sorted((ROOT / ".codex" / "agents").glob("*.toml"))
    assert adapters
    for adapter in adapters:
        native = tomllib.loads(adapter.read_text(encoding="utf-8"))
        instructions = native["developer_instructions"]
        role_match = re.search(r"Registry role `([^`]+)`", instructions)
        assert role_match, f"{adapter.name} has no Registry role binding"
        role = role_match.group(1)
        owned_on_demand = {
            skill: binding["activation"]
            for skill, binding in registry["on_demand_skills"].items()
            if role in binding["owners"]
        }
        skills = set(registry["roles"][role].get("skills", [])) | set(owned_on_demand)
        for skill in skills:
            assert f"`${skill}`" in instructions
            assert f"`.agents/skills/{skill}/SKILL.md`" in instructions
            if skill in owned_on_demand:
                assert owned_on_demand[skill] in instructions
