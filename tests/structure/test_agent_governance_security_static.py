from __future__ import annotations

import ast
import importlib.util
import re
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    ROOT / "helper_scripts" / "maintenance_scripts" / "agent_governance.py"
)
WRITER_LEASE_PATH = (
    ROOT
    / "helper_scripts"
    / "maintenance_scripts"
    / "agent_governance_writer_lease.py"
)
CAPTURE_PATH = (
    ROOT / "helper_scripts" / "maintenance_scripts" / "agent_governance_capture.py"
)
GUARD_PATH = (
    ROOT / "helper_scripts" / "maintenance_scripts" / "git_loop_guard.py"
)


def _load_governance():
    spec = importlib.util.spec_from_file_location("agent_governance", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lw2_publication_status_static_surface_is_read_only() -> None:
    tree = ast.parse(WRITER_LEASE_PATH.read_text(encoding="utf-8"))
    publication = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_lw2_publication_status"
    )
    forbidden_git_mutations = {
        "add", "branch", "checkout", "clean", "commit", "fetch", "merge",
        "pull", "push", "rebase", "reset", "restore", "switch", "tag",
        "update-ref", "worktree",
    }
    git_commands: set[str] = set()
    for node in ast.walk(publication):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"_git_bytes", "_git_text"}
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            git_commands.add(node.args[1].value)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and node.args
            and isinstance(node.args[0], ast.List)
        ):
            git_commands.update(
                element.value
                for element in node.args[0].elts
                if isinstance(element, ast.Constant)
                and isinstance(element.value, str)
            )
    assert git_commands.isdisjoint(forbidden_git_mutations)
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr
        in {"transact", "update", "write", "write_bytes", "write_text"}
        for node in ast.walk(publication)
    )
    for node in ast.walk(publication):
        targets: list[ast.expr] = []
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            raw_targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            targets.extend(raw_targets)
        assert not any(
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id in {"record", "lease", "accepted", "task_contract"}
            for target in targets
        )


def test_lw2_publication_status_uses_only_native_git_graph_reads() -> None:
    source = WRITER_LEASE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    git_bytes_source = ast.get_source_segment(source, functions["_git_bytes"])
    native_env_source = ast.get_source_segment(
        source, functions["_native_git_environment"]
    )
    publication_source = ast.get_source_segment(
        source, functions["_lw2_publication_status"]
    )
    action_source = ast.get_source_segment(
        source, functions["filesystem_writer_lease_action"]
    )
    assert git_bytes_source is not None
    assert "_native_git_command(repo, *args)" in git_bytes_source
    assert "env=_native_git_environment()" in git_bytes_source
    assert native_env_source is not None
    assert "native_git_environment" in native_env_source
    assert publication_source is not None
    assert '"merge-base"' not in publication_source
    assert '"rev-list"' not in publication_source
    assert '"cat-file"' in source
    assert "native_graph=True" in publication_source
    assert action_source is not None
    assert 'native_graph=action == "publication-status"' in action_source

    capture_source = CAPTURE_PATH.read_text(encoding="utf-8")
    assert 'TRUSTED_GIT_EXECUTABLE = "/usr/bin/git"' in capture_source
    assert "TRUSTED_GIT_EXECUTABLE," in capture_source
    assert '"--no-replace-objects"' in capture_source
    assert '"core.fsmonitor=false"' in capture_source
    assert '"core.hooksPath=/dev/null"' in capture_source
    for required in (
        "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_ATTR_NOSYSTEM",
        "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", "GIT_REPLACE_REF_BASE",
        "GIT_OPTIONAL_LOCKS", "GIT_TERMINAL_PROMPT", "LC_ALL",
    ):
        assert required in capture_source


def test_authority_diff_argv_disables_ext_diff_and_textconv_everywhere() -> None:
    for path in (CAPTURE_PATH, WRITER_LEASE_PATH, GUARD_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        checked = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            literals = [
                argument.value
                for argument in node.args
                if isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
            ]
            if not ({"diff", "diff-tree"} & set(literals)):
                continue
            checked += 1
            assert "--no-ext-diff" in literals, (path, node.lineno, literals)
            assert "--no-textconv" in literals, (path, node.lineno, literals)
        assert checked, path


def test_read_only_command_preflight_rejects_every_ascii_control_character() -> None:
    governance = _load_governance()

    for codepoint in [*range(0x20), 0x7F]:
        control = chr(codepoint)
        local = governance.authorize_command("E2", f"git status{control}")
        remote = governance.authorize_command(
            "OPS",
            "ssh trade-core 'systemctl --user is-active "
            f"openclaw-trading-api.service{control}'",
        )
        assert local["allowed"] is False, (codepoint, local)
        assert remote["allowed"] is False, (codepoint, remote)
        assert "ASCII control" in local["reason"]
        assert "ASCII control" in remote["reason"]


def test_shell_encoded_control_sequences_cannot_bypass_preflight() -> None:
    governance = _load_governance()
    encoded_attempts = (
        r"git status$'\n'git add AGENTS.md",
        r"git status$'\r'git add AGENTS.md",
        r"git status$'\x0a'git add AGENTS.md",
        r"git status$'\012'git add AGENTS.md",
        r"git status$(printf '\n')git add AGENTS.md",
    )

    for command in encoded_attempts:
        decision = governance.authorize_command("E2", command)
        assert decision["allowed"] is False, (command, decision)


def test_registry_rejects_fictional_credentials_in_role_interfaces() -> None:
    governance = _load_governance()

    for fictional_text in (
        "Ph.D authority",
        "Professor of distributed systems",
        "20+ years of trading experience",
        "Resume of a famous engineer",
    ):
        registry = deepcopy(governance.load_registry())
        registry["roles"]["E2"]["lens"] = fictional_text
        errors = governance.validate_registry(registry, ROOT)
        assert "E2: fictional credential/persona text is forbidden" in errors


def test_psql_preflight_rejects_connection_output_and_script_flags() -> None:
    governance = _load_governance()
    attacks = (
        "psql --host=203.0.113.9 --output=/home/ncyu/BybitOpenClaw/srv/probe.out -c \"SELECT now()\"",
        "psql -f /home/ncyu/BybitOpenClaw/srv/migration.sql -c \"SELECT now()\"",
        "psql --username=postgres -c \"SELECT now()\"",
        "psql --command \"SELECT 1 \\\\gexec\"",
    )
    for inner in attacks:
        decision = governance.authorize_command("OPS", f"ssh trade-core '{inner}'")
        assert decision["allowed"] is False, (inner, decision)

    no_trusted_wrapper = governance.authorize_command(
        "OPS", "ssh trade-core 'psql -X -A -t -c \"SELECT now()\"'"
    )
    assert no_trusted_wrapper["allowed"] is False, no_trusted_wrapper


def test_pytest_preflight_rejects_persistent_output_plugins() -> None:
    governance = _load_governance()
    attacks = (
        "pytest tests/structure/test_x.py --junitxml=reviewer-owned.xml",
        "python3 -m pytest tests/structure/test_x.py --basetemp=.reviewer-owned",
        "pytest tests/structure/test_x.py --cov=. --cov-report=xml:coverage.xml",
        "pytest tests/structure/test_x.py --html=review.html",
    )
    for command in attacks:
        decision = governance.authorize_command("E2", command)
        assert decision["allowed"] is False, (command, decision)

    safe = governance.authorize_command(
        "E2", "python3 -m pytest tests/structure/test_x.py -q -k fail_closed"
    )
    assert safe["allowed"] is True, safe


def test_sed_execution_language_is_not_in_the_read_only_allowlist() -> None:
    governance = _load_governance()
    for command in (
        "sed -n '1,20p' AGENTS.md",
        "sed -n '1e echo forbidden' AGENTS.md",
        "sed --expression '1e echo forbidden' AGENTS.md",
    ):
        decision = governance.authorize_command("E2", command)
        assert decision["allowed"] is False, (command, decision)


def test_e4_has_a_local_test_only_adapter_path() -> None:
    governance = _load_governance()
    allowed = governance.authorize_command(
        "E4", "python3 -m pytest tests/structure/test_agent_governance_security_static.py -q",
        node_class="work", effective_permission="test_writer",
    )
    assert allowed == {
        "allowed": True,
        "policy_class": "local_test_adapter",
        "reason": "E4 local test Adapter command",
    }
    assert governance.authorize_command("E4", "git status")["allowed"] is False
    verification = governance.authorize_command(
        "E4", "git status", node_class="verification",
        effective_permission="read_only",
    )
    assert verification["allowed"] is True
    assert verification["policy_class"] == "node_scoped_read_only"
    assert governance.authorize_command(
        "PA", "git status", node_class="verification",
        effective_permission="design_writer",
    )["allowed"] is False
    assert governance.authorize_command(
        "E4", "ssh trade-core 'systemctl --user is-active openclaw-engine.service'"
    )["allowed"] is False


def test_remote_evidence_roots_reject_sibling_prefixes() -> None:
    governance = _load_governance()
    for path in (
        "/home/ncyu/BybitOpenClaw/srv_evil/data.txt",
        "/home/ncyu/BybitOpenClaw/var/openclaw_secrets/token.txt",
        "/tmp/openclaw-escape/result.txt",
    ):
        decision = governance.authorize_command(
            "OPS", f"ssh trade-core 'cat {path}'"
        )
        assert decision["allowed"] is False, (path, decision)


def test_ci_runs_the_cheap_development_agent_governance_gate() -> None:
    source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    def _job(name: str) -> str:
        match = re.search(rf"\n  {re.escape(name)}:\n(.*?)(?=\n  [a-z0-9][a-z0-9-]*:\n|\Z)", source, re.S)
        assert match is not None
        return match.group(1)
    worker, aggregate = (_job(name) for name in ("development-agent-governance-shard", "development-agent-governance"))
    worker_required = (
        "name: development-agent governance shard ${{ matrix.shard }} of 8", "runs-on: ubuntu-latest", "timeout-minutes: 45", "fail-fast: false", "shard: [0, 1, 2, 3, 4, 5, 6, 7]", "agent_governance.py validate", "agent_governance.py render --check", "-p helper_scripts.ci.select_pytest_shard", "--governance-shard-index ${{ matrix.shard }}", "--governance-shard-count 8", "--governance-shard-minimum 4548",
        "tests/structure/test_development_agent_governance.py", "tests/structure/test_agent_governance_*.py", "tests/structure/test_codex_memory_policy.py", "tests/structure/test_role_memory_compaction.py", "tests/structure/test_s2_4_w0_admission.py",
        "tests/structure/test_aiml_s1_closure_target_host_run.py", "tests/structure/test_target_host_effect_adapter.py", "tests/structure/test_target_host_apply_orchestrator.py", "tests/structure/test_terminal_receipt_external_sink.py", "if: matrix.shard == 0",
    )
    aggregate_required = (
        "name: development-agent governance (cheap static gate)", "needs: [changes, development-agent-governance-shard]", "if: always()", "timeout-minutes: 2", "GOVERNANCE_SELECTED: ${{ needs.changes.outputs.governance }}", "SHARD_RESULT: ${{ needs.development-agent-governance-shard.result }}", "set -euo pipefail", '"$GOVERNANCE_SELECTED" == "true" && "$SHARD_RESULT" == "success"', '"$GOVERNANCE_SELECTED" == "false" && "$SHARD_RESULT" == "skipped"',
    )
    for section, required in ((worker, worker_required), (aggregate, aggregate_required)):
        assert all(token in section for token in required)
    assert aggregate.count("exit 0") == 2 and aggregate.count("exit 1") == 1 and all(token not in worker + aggregate for token in ("continue-on-error", "|| true", " -k ", "--ignore", "--deselect", "--maxfail", " -x", "xdist"))
