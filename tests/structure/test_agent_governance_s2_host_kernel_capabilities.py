"""Split capability-boundary tests for the S2 trusted-host scanner."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
STRUCTURE = ROOT / "tests" / "structure"
if str(STRUCTURE) not in sys.path:
    sys.path.insert(0, str(STRUCTURE))

import test_agent_governance_s2_host_kernel as scanner  # noqa: E402


EXPECTED_RECOVERY_LEAVES = frozenset({
    "agent_governance_s2_5_recovery.py",
    "agent_governance_s2_5_recovery_anchor.py",
    "agent_governance_s2_5_recovery_anchor_v2.py",
    "agent_governance_s2_5_recovery_controller.py",
    "agent_governance_s2_5_recovery_lock.py",
    "agent_governance_s2_5_recovery_readback.py",
    "agent_governance_s2_5_recovery_state.py",
    "agent_governance_s2_5_recovery_store.py",
    "agent_governance_s2_5_recovery_store_v2.py",
})


def test_every_recovery_leaf_has_exact_import_and_callable_policy():
    assert scanner.RECOVERY_GOVERNED_FILES == EXPECTED_RECOVERY_LEAVES
    assert set(scanner.EXACT_STDLIB_IMPORTS_BY_FILE) >= EXPECTED_RECOVERY_LEAVES
    assert set(scanner.GOVERNANCE_IMPORTS_BY_FILE) >= EXPECTED_RECOVERY_LEAVES
    assert set(scanner.RECOVERY_SENSITIVE_CALLS_BY_FILE) == EXPECTED_RECOVERY_LEAVES


@pytest.mark.parametrize("name", sorted(EXPECTED_RECOVERY_LEAVES))
def test_every_recovery_leaf_rejects_an_undeclared_os_unlink_call(
    tmp_path,
    name,
):
    original = scanner.HELPERS / name
    mutated = tmp_path / name
    mutated.write_text(
        original.read_text(encoding="utf-8")
        + "\n\nimport os\nos.unlink('/tmp/s2e-scanner-mutation')\n",
        encoding="utf-8",
    )
    findings = scanner._raw_command_findings(mutated)
    assert any(
        "sensitive callable outside the per-file allowlist: os.unlink" in item
        for item in findings
    ), findings


@pytest.mark.parametrize("name", sorted(EXPECTED_RECOVERY_LEAVES))
def test_every_recovery_leaf_rejects_an_aliased_socket_callable(
    tmp_path,
    name,
):
    original = scanner.HELPERS / name
    mutated = tmp_path / name
    mutated.write_text(
        original.read_text(encoding="utf-8")
        + "\n\nimport socket as network\n"
        + "connect = network.create_connection\n"
        + "aliased_connect = connect\n"
        + "aliased_connect(('127.0.0.1', 9))\n",
        encoding="utf-8",
    )
    findings = scanner._raw_command_findings(mutated)
    assert any(
        "sensitive callable outside the per-file allowlist: "
        "socket.create_connection" in item
        for item in findings
    ), findings


@pytest.mark.parametrize("name", sorted(EXPECTED_RECOVERY_LEAVES))
@pytest.mark.parametrize(
    ("source", "expected"),
    (
        (
            "import socket\nsocket.create_connection(('127.0.0.1', 9))\n",
            "socket.create_connection",
        ),
        (
            "import os as filesystem\n"
            "filesystem.unlink('/tmp/s2e-scanner-mutation')\n",
            "os.unlink",
        ),
        (
            "from os import unlink as erase\n"
            "erase('/tmp/s2e-scanner-mutation')\n",
            "os.unlink",
        ),
    ),
)
def test_recovery_sensitive_call_policy_covers_import_forms(
    tmp_path,
    name,
    source,
    expected,
):
    original = scanner.HELPERS / name
    mutated = tmp_path / name
    mutated.write_text(
        original.read_text(encoding="utf-8") + "\n\n" + source,
        encoding="utf-8",
    )
    findings = scanner._raw_command_findings(mutated)
    assert any(
        "sensitive callable outside the per-file allowlist: "
        + expected in item
        for item in findings
    ), findings


def test_recovery_store_effect_and_pure_builder_are_scanned_per_file():
    present = {path.name for path in scanner._present_family()}
    assert {
        "agent_governance_s2_5_recovery_anchor_v2.py",
        "agent_governance_s2_5_recovery_store.py",
        "agent_governance_s2_5_recovery_store_v2.py",
    } <= present


def test_controller_anchor_effect_adapter_has_a_positive_import_allowlist(
    tmp_path,
):
    name = "agent_governance_s2_5_recovery_anchor_v2.py"
    assert name in scanner.GOVERNANCE_IMPORTS_BY_FILE
    path = scanner.HELPERS / name
    assert scanner._raw_command_findings(path, exec_family=True) == []
    mutated = tmp_path / name
    mutated.write_text(
        path.read_text(encoding="utf-8") + "\nimport runpy\n",
        encoding="utf-8",
    )
    assert scanner._raw_command_findings(mutated, exec_family=True)


@pytest.mark.parametrize(
    "source",
    (
        "import os\n",
        "from fcntl import flock\n",
        "import socket as network\n",
        "from os import *\n",
        "import importlib\nimportlib.import_module('os')\n",
    ),
)
def test_pure_recovery_store_builder_denies_every_effect_import_form(
    tmp_path,
    source,
):
    path = tmp_path / "agent_governance_s2_5_recovery_store_v2.py"
    path.write_text(source, encoding="utf-8")
    assert scanner._raw_command_findings(path)


def test_a_declared_non_runner_leaf_is_still_denied_every_exec_path():
    for name, reason in scanner.NON_RUNNER_HOST_LEAVES.items():
        path = scanner.HELPERS / name
        assert path.is_file(), name
        assert reason.strip(), name
        assert scanner._raw_command_findings(
            path, exec_family=False
        ) == [], name
        assert "subprocess" not in path.read_text(encoding="utf-8"), name


def test_the_exec_family_exemption_never_admits_a_kernel_only_module(tmp_path):
    for module in sorted(scanner.KERNEL_ONLY_IMPORTS):
        path = tmp_path / f"exempt_{module}.py"
        path.write_text(f"import {module}\n", encoding="utf-8")
        findings = scanner._raw_command_findings(path, exec_family=False)
        assert any(
            "kernel-only module outside the kernel" in item
            for item in findings
        ), module


EXEMPT_LEAF_EXEC_COUNTEREXAMPLES = {
    "E2_pty_spawn_on_an_exempt_leaf": (
        "import pty\n\n\ndef f(argv):\n    return pty.spawn(argv)\n"
    ),
    "E2_importlib_dynamic_name_on_an_exempt_leaf": (
        "import importlib\n\n\ndef f(name):\n"
        "    return importlib.import_module(name)\n"
    ),
    "asyncio_create_subprocess": (
        "import asyncio\n\n\nasync def f(argv):\n"
        "    return await asyncio.create_subprocess_exec(*argv)\n"
    ),
    "multiprocessing_spawn": (
        "import multiprocessing\n\n\ndef f(fn):\n"
        "    return multiprocessing.Process(target=fn)\n"
    ),
    "commands_legacy": (
        "import commands\n\n\ndef f(cmd):\n    return commands.getoutput(cmd)\n"
    ),
}


@pytest.mark.parametrize("mutation", sorted(EXEMPT_LEAF_EXEC_COUNTEREXAMPLES))
def test_the_exec_family_exemption_never_admits_an_exec_capable_module(
    tmp_path,
    mutation,
):
    path = tmp_path / f"{mutation}.py"
    path.write_text(
        EXEMPT_LEAF_EXEC_COUNTEREXAMPLES[mutation], encoding="utf-8"
    )
    findings = scanner._raw_command_findings(path, exec_family=False)
    assert any(
        "exec-capable module on a non-runner leaf" in item
        for item in findings
    ), findings
    assert scanner._raw_command_findings(path, exec_family=True)


@pytest.mark.parametrize("module", sorted(scanner.EXEC_CAPABLE_IMPORT_DENYLIST))
@pytest.mark.parametrize(
    "form",
    ["import {m}", "import {m}.sub", "from {m} import x"],
)
def test_every_exec_capable_denylist_entry_is_caught_in_every_import_form(
    tmp_path,
    module,
    form,
):
    path = tmp_path / f"denied_{module}_{abs(hash(form))}.py"
    path.write_text(form.format(m=module) + "\n", encoding="utf-8")
    assert any(
        "exec-capable module on a non-runner leaf" in item
        for item in scanner._raw_command_findings(path, exec_family=False)
    ), (module, form)


def test_the_two_import_denylists_never_overlap_the_positive_allowlist():
    allowed = (
        scanner.ALLOWED_STDLIB_IMPORTS
        | scanner.ALLOWED_THIRD_PARTY_IMPORTS
    )
    for modules in scanner.GOVERNANCE_IMPORTS_BY_FILE.values():
        allowed |= modules
    assert not (scanner.EXEC_CAPABLE_IMPORT_DENYLIST & allowed)
    assert not (
        scanner.EXEC_CAPABLE_IMPORT_DENYLIST & scanner.KERNEL_ONLY_IMPORTS
    )


def test_the_family_derivation_is_red_when_a_new_runner_is_left_out(tmp_path):
    names = {
        "agent_governance_s2_9_host_runner.py",
        "aiml_s2_other_host_run.py",
    }
    for name in names:
        (tmp_path / name).write_text("x = 1\n", encoding="utf-8")
    assert scanner._unscanned_runner_candidates(tmp_path, set()) == sorted(names)
    assert scanner._unscanned_runner_candidates(tmp_path, names) == []


def test_the_runner_family_is_auto_discovered_not_copied_into_a_tuple(tmp_path):
    expected = []
    for name in (
        "agent_governance_s2_9_host_runner.py",
        "aiml_s2_other_host_run.py",
    ):
        path = tmp_path / name
        path.write_text("x = 1\n", encoding="utf-8")
        expected.append(path)
    (tmp_path / "agent_governance_s2_4_host_identity.py").write_text(
        "x = 1\n", encoding="utf-8"
    )
    assert scanner._discover_runner_family(tmp_path) == sorted(expected)


def test_the_governance_import_allowlist_is_per_file_not_family_wide(tmp_path):
    applier = sorted(
        scanner.APPLIER_MODULES
        & scanner.GOVERNANCE_IMPORTS_BY_FILE[
            "agent_governance_s2_4_host_recovery.py"
        ]
    )
    assert applier
    source = "".join(f"import {module}\n" for module in applier)
    admitted = tmp_path / "agent_governance_s2_4_host_recovery.py"
    admitted.write_text(source, encoding="utf-8")
    assert scanner._raw_command_findings(admitted) == []
    for name in (
        "agent_governance_s2_host_observer.py",
        "agent_governance_s2_host_kernel.py",
        "agent_governance_s2_0_host_runner.py",
    ):
        elsewhere = tmp_path / name
        elsewhere.write_text(source, encoding="utf-8")
        assert scanner._raw_command_findings(elsewhere), name


def test_every_governance_allowlist_entry_belongs_to_a_family_member():
    family_names = {
        path.name for path in scanner.RUNNER_FAMILY
    } | scanner.RECOVERY_GOVERNED_FILES
    assert set(scanner.GOVERNANCE_IMPORTS_BY_FILE) <= family_names
    for name, modules in scanner.GOVERNANCE_IMPORTS_BY_FILE.items():
        assert not (modules & scanner.KERNEL_ONLY_IMPORTS), name
