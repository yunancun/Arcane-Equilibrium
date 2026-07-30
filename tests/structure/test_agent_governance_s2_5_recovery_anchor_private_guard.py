"""Positive import/capability guard for the non-runner recovery-anchor leaf。"""

from __future__ import annotations

import sys
from pathlib import Path


TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

import test_agent_governance_s2_host_kernel as guard  # noqa: E402


PRIVATE_CAPABILITY_LEAF = "agent_governance_s2_5_recovery_anchor.py"


def test_private_capability_leaf_is_positive_scanned_not_exempted():
    assert PRIVATE_CAPABILITY_LEAF not in guard.NON_RUNNER_HOST_LEAVES
    assert PRIVATE_CAPABILITY_LEAF in guard.GOVERNANCE_IMPORTS_BY_FILE
    path = guard.HELPERS / PRIVATE_CAPABILITY_LEAF
    assert path.is_file()
    assert guard._raw_command_findings(path, exec_family=True) == []


def test_private_capability_leaf_positive_allowlist_catches_exec_import(tmp_path):
    source = (
        guard.HELPERS / PRIVATE_CAPABILITY_LEAF
    ).read_text(encoding="utf-8")
    mutated = tmp_path / PRIVATE_CAPABILITY_LEAF
    mutated.write_text(source + "\nimport runpy\n", encoding="utf-8")
    findings = guard._raw_command_findings(mutated, exec_family=True)
    assert any(
        "import outside the declared allowlist" in item
        or "exec-capable module" in item
        for item in findings
    ), findings
