from __future__ import annotations

import importlib.util
import re
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    ROOT / "helper_scripts" / "maintenance_scripts" / "agent_governance.py"
)


def _load_governance():
    spec = importlib.util.spec_from_file_location("agent_governance", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    marker = "\n  development-agent-governance:\n"
    assert marker in source
    job = source.split(marker, 1)[1]
    next_job = re.search(r"\n  [a-z0-9][a-z0-9-]*:\n", job)
    if next_job:
        job = job[: next_job.start()]

    for required in (
        "runs-on: ubuntu-latest",
        "timeout-minutes: 20",
        "python3 helper_scripts/maintenance_scripts/agent_governance.py validate",
        "python3 helper_scripts/maintenance_scripts/agent_governance.py render --check",
        "tests/structure/test_development_agent_governance.py",
        "tests/structure/test_agent_governance_*.py",
    ):
        assert required in job
