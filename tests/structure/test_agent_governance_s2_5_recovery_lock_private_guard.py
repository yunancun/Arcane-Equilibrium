"""Positive host-kernel scan for the private recovery dual-lock capability."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

import test_agent_governance_s2_host_kernel as guard  # noqa: E402


PRIVATE_CAPABILITY_LEAF = "agent_governance_s2_5_recovery_lock.py"


def test_private_lock_leaf_is_positive_per_file_scanned_without_global_widening():
    assert PRIVATE_CAPABILITY_LEAF not in guard.NON_RUNNER_HOST_LEAVES
    assert PRIVATE_CAPABILITY_LEAF in guard.GOVERNANCE_IMPORTS_BY_FILE
    assert PRIVATE_CAPABILITY_LEAF in guard.STDLIB_IMPORTS_BY_FILE
    assert {"functools"}.isdisjoint(guard.ALLOWED_STDLIB_IMPORTS)
    assert guard.STDLIB_IMPORTS_BY_FILE[PRIVATE_CAPABILITY_LEAF] == frozenset({
        "functools",
    })
    path = guard.HELPERS / PRIVATE_CAPABILITY_LEAF
    assert path.is_file()
    assert guard._raw_command_findings(path, exec_family=True) == []


@pytest.mark.parametrize(
    "payload",
    [
        "import runpy\n",
        "import imp as legacy_loader\n",
        "import code as harmless\n",
        "from pdb import run as inspect_only\n",
        "from timeit import *\n",
        "from concurrent.futures import ThreadPoolExecutor\n",
        "eval('1 + 1')\n",
    ],
)
def test_positive_scanner_rejects_import_alias_star_and_dynamic_exec_mutations(
    tmp_path,
    payload,
):
    source = (
        guard.HELPERS / PRIVATE_CAPABILITY_LEAF
    ).read_text(encoding="utf-8")
    mutated = tmp_path / PRIVATE_CAPABILITY_LEAF
    mutated.write_text(source + "\n" + payload, encoding="utf-8")
    findings = guard._raw_command_findings(mutated, exec_family=True)
    assert findings, payload


def test_positive_scanner_rejects_getattr_sys_modules_lookup_call(tmp_path):
    source = (
        guard.HELPERS / PRIVATE_CAPABILITY_LEAF
    ).read_text(encoding="utf-8")
    payload = """
registry_alias = getattr(sys, "modules")
subprocess_alias = registry_alias.get("subprocess")
subprocess_alias.run(["true"])
"""
    mutated = tmp_path / PRIVATE_CAPABILITY_LEAF
    mutated.write_text(source + payload, encoding="utf-8")

    findings = guard._raw_command_findings(mutated, exec_family=True)
    assert any("dynamic module execution" in item for item in findings), findings


@pytest.mark.parametrize(
    "payload",
    [
        """
registry_alias = sys.__getattribute__("mod" + "ules")
lookup_alias = registry_alias.__getattribute__("get")
subprocess_alias = lookup_alias("subprocess")
subprocess_alias.run(["true"])
""",
        """
attribute_reader = getattr
registry_alias = attribute_reader(sys, "mod" + "ules")
lookup_alias = attribute_reader(registry_alias, "__getitem__")
subprocess_alias = lookup_alias("subprocess")
subprocess_alias.run(["true"])
""",
    ],
)
def test_positive_scanner_rejects_computed_and_aliased_registry_lookup(
    tmp_path,
    payload,
):
    source = (
        guard.HELPERS / PRIVATE_CAPABILITY_LEAF
    ).read_text(encoding="utf-8")
    mutated = tmp_path / PRIVATE_CAPABILITY_LEAF
    mutated.write_text(source + payload, encoding="utf-8")

    findings = guard._raw_command_findings(mutated, exec_family=True)
    assert any("dynamic module execution" in item for item in findings), findings
