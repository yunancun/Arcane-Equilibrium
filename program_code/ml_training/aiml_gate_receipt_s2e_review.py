"""Code-owned Git-blob review profiles and typed disposable test evidence."""

from __future__ import annotations

import ast
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePath
from typing import Any

from agent_governance_pytest_provider import (
    GOVERNED_PYTEST_BOOTSTRAP,
    GOVERNED_PYTEST_REQUIRED_ARGS,
)
from agent_governance_schema import schema_subset_errors
from aiml_gate_receipt_schema_core import (
    _load_schema,
    canonical_digest,
)


GENESIS_WAVE = "W0-GENESIS"
LAUNCH_WAVES = ("S2E-LW1", "S2E-LW2", "S2E-LW3", "S2E-LW4", "S2E-LW5")
S2E_RECEIPT_SIGNER_IDENTITY = "aiml-s2e-receipt-signer-v1"
S2E_RECEIPT_SIGNATURE_NAMESPACE = "arcane-equilibrium-aiml-s2e-receipts"

_S2E_REVIEW_COMMON_PREDICATES = (
    "CANDIDATE_SCHEMA_VALID",
    "EXACT_SOURCE_HEAD_TREE_VALID",
    "DURABILITY_ANCHOR_IMMUTABLE_READBACK_VALID",
    "INDEPENDENT_GOVERNED_REVIEW_VALID",
    "INDEPENDENT_SSHSIG_VALID",
)
_S2E_LW1_REVIEW_PREDICATES = (
    "OWNED_GIT_BLOB_REPLAY_VALID",
    "LW1_PRIVATE_PENETRATION_GUARD_VALID",
    "LW1_RECOVERY_CONTRACT_FAMILY_VALID",
    "LW1_TRUSTED_ANCHOR_ROLLBACK_PROTECTION_VALID",
    "LW1_DUAL_LOCK_DURABLE_STORE_VALID",
    "LW1_DERIVED_IDENTITY_EXACT_COMPLETION_VALID",
    "LW1_DISPOSABLE_EFFECT_CHAIN_VALID",
    "LW1_VALIDATOR_LINE_POLICY_VALID",
    "LW1_EXIT_BOUNDARY_VALID",
)

S2E_REVIEW_BASE_PATHS = (
    ".codex/agent_registry_v1.json",
    ".codex/providers/governed_pytest_v1/lock.json",
    (
        ".codex/providers/governed_pytest_v1/wheels/"
        "exceptiongroup-1.3.1-py3-none-any.whl"
    ),
    (
        ".codex/providers/governed_pytest_v1/wheels/"
        "iniconfig-2.3.0-py3-none-any.whl"
    ),
    (
        ".codex/providers/governed_pytest_v1/wheels/"
        "packaging-26.1-py3-none-any.whl"
    ),
    (
        ".codex/providers/governed_pytest_v1/wheels/"
        "pluggy-1.6.0-py3-none-any.whl"
    ),
    (
        ".codex/providers/governed_pytest_v1/wheels/"
        "pygments-2.20.0-py3-none-any.whl"
    ),
    (
        ".codex/providers/governed_pytest_v1/wheels/"
        "pytest-9.0.3-py3-none-any.whl"
    ),
    (
        ".codex/providers/governed_pytest_v1/wheels/"
        "tomli-2.4.1-py3-none-any.whl"
    ),
    (
        ".codex/providers/governed_pytest_v1/wheels/"
        "typing_extensions-4.15.0-py3-none-any.whl"
    ),
    ".codex/schemas/closure_packet_v1.schema.json",
    "helper_scripts/maintenance_scripts/agent_governance_capture.py",
    "helper_scripts/maintenance_scripts/agent_governance_command_capture_v2.py",
    "helper_scripts/maintenance_scripts/agent_governance_command_replay.py",
    (
        "helper_scripts/maintenance_scripts/"
        "agent_governance_context_validation.py"
    ),
    (
        "helper_scripts/maintenance_scripts/"
        "agent_governance_generation_summary.py"
    ),
    "helper_scripts/maintenance_scripts/agent_governance_permissions.py",
    "helper_scripts/maintenance_scripts/agent_governance_pytest_provider.py",
    "helper_scripts/maintenance_scripts/agent_governance_registry.py",
    "helper_scripts/maintenance_scripts/agent_governance_routing.py",
    "helper_scripts/maintenance_scripts/agent_governance_schema.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2e_launch_receipts.py",
    (
        "helper_scripts/maintenance_scripts/"
        "agent_governance_workflow_receipts.py"
    ),
    # committed floor 與其讀取模組:reviewer 簽名的 source_blob_manifest 逐位元組
    # 釘住 floor,關掉「review 與 transition 之間 floor 被換掉」這條縫。
    (
        "docs/execution_plan/ai_ml_landing/receipts/S2E-LW1-LW5/"
        "durability-anchor-floor-v1.json"
    ),
    "program_code/ml_training/application_bundle_runtime_closure_v1.json",
    "program_code/ml_training/aiml_gate_receipt_s2e_anchor_floor.py",
    "program_code/ml_training/aiml_gate_receipt_s2e_consumption.py",
    "program_code/ml_training/aiml_gate_receipt_s2e_dispatch.py",
    "program_code/ml_training/aiml_gate_receipt_s2e_external_evidence.py",
    "program_code/ml_training/aiml_gate_receipt_s2e_launch.py",
    "program_code/ml_training/aiml_gate_receipt_s2e_review.py",
    "program_code/ml_training/aiml_gate_receipt_schema_core.py",
    "program_code/ml_training/aiml_gate_receipt_validator.py",
    (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "receipt_carrier_attestation_v1.schema.json"
    ),
    (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2e_disposable_test_effect_chain_v1.schema.json"
    ),
    (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2e_durability_anchor_attestation_v1.schema.json"
    ),
    (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2e_durability_anchor_floor_v1.schema.json"
    ),
    (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2e_launch_consumption_bootstrap_authority_v1.schema.json"
    ),
    (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2e_launch_predecessor_consumption_ledger_v1.schema.json"
    ),
    (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2e_launch_acceptance_review_bundle_v1.schema.json"
    ),
    (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2e_launch_genesis_receipt_v1.schema.json"
    ),
    (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2e_launch_wave_receipt_v1.schema.json"
    ),
    (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "s2e_predecessor_registry_attestation_v1.schema.json"
    ),
    "program_code/ml_training/tests/test_aiml_gate_receipt_validator_s2_4.py",
    "tests/structure/test_agent_governance_s2_2b.py",
    "tests/structure/test_agent_governance_command_capture_v2.py",
    "tests/structure/test_agent_governance_node_permissions.py",
    "tests/structure/test_agent_governance_s2e_launch_chain.py",
    "tests/structure/test_agent_governance_s2e_launch_hardening.py",
    "tests/structure/test_agent_governance_s2e_launch_receipts.py",
    "tests/structure/test_agent_governance_s2e_external_evidence.py",
)
S2E_LW1_REVIEW_PREFIXES = (
    ".codex/schemas/s2_5_recovery_",
    "helper_scripts/maintenance_scripts/agent_governance_s2_5_recovery",
    "program_code/ml_training/schemas/aiml_gate_receipts/s2_5_recovery_",
    "tests/structure/s2_5_recovery_",
    "tests/structure/test_agent_governance_s2_5_recovery",
)
S2E_LW1_REVIEW_PATHS = (
    "CLAUDE.md",
    "TODO.md",
    "docs/references/2000_line_exception_registry.md",
    "helper_scripts/maintenance_scripts/agent_governance_s2_0_host_runner.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_1_host_runner.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_host_recovery.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_host_storage.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_5.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_5_disposable_profile.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_5_lifecycle.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_host_kernel.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_host_observer.py",
    "helper_scripts/maintenance_scripts/aiml_s2_effect_host_run.py",
    "program_code/ml_training/aiml_gate_receipt_s2_5.py",
    "program_code/ml_training/aiml_gate_receipt_s2_5_host_capture.py",
    "program_code/ml_training/aiml_gate_receipt_schema_core.py",
    "program_code/ml_training/aiml_gate_receipt_source_compatibility.py",
    "program_code/ml_training/aiml_gate_receipt_validator.py",
    "program_code/ml_training/tests/test_aiml_gate_receipt_validator_s2_4.py",
    "tests/structure/s2_5_testkit.py",
    "tests/structure/test_agent_governance_s2_2b.py",
    "tests/structure/test_agent_governance_s2_4_install_application_bundle.py",
    "tests/structure/test_agent_governance_s2_5_disposable_profile.py",
    "tests/structure/test_agent_governance_s2_5_durability_s2e3.py",
    "tests/structure/test_agent_governance_s2_5_hardening.py",
    "tests/structure/test_agent_governance_s2_5_host_capture.py",
    "tests/structure/test_agent_governance_s2_5_lifecycle.py",
    "tests/structure/test_agent_governance_s2_5_lifecycle_fixtures.py",
    "tests/structure/test_agent_governance_s2_host_kernel.py",
    "tests/structure/test_agent_governance_s2_host_kernel_alias_flow.py",
    "tests/structure/test_agent_governance_s2_host_kernel_capabilities.py",
    "tests/structure/test_file_line_policy_static.py",
)

_LW1_PREDICATE_PATH_TOKENS = {
    "LW1_PRIVATE_PENETRATION_GUARD_VALID": (
        "s2_host_kernel",
        "private_guard",
        "socket_scan",
    ),
    "LW1_RECOVERY_CONTRACT_FAMILY_VALID": (
        "s2_5_recovery",
        "aiml_gate_receipt_s2_5",
    ),
    "LW1_TRUSTED_ANCHOR_ROLLBACK_PROTECTION_VALID": (
        "recovery_anchor",
        "recovery_readback",
    ),
    "LW1_DUAL_LOCK_DURABLE_STORE_VALID": (
        "recovery_lock",
        "recovery_store",
    ),
    "LW1_DERIVED_IDENTITY_EXACT_COMPLETION_VALID": (
        "host_capture",
        "recovery_controller",
        "s2_5_lifecycle",
        "s2_2b",
    ),
}


def _git(
    repo_root: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        capture_output=True,
        text=True,
    )


def _git_bytes(repo_root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
    ).stdout


def _tree(repo_root: Path, head: str) -> str:
    return _git(
        repo_root, "rev-parse", "--verify", f"{head}^{{tree}}"
    ).stdout.strip()


def _raw_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _time(value: str | datetime) -> datetime:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _schema_errors(value: Any, schema_version: str) -> list[str]:
    if not isinstance(value, dict):
        return ["S2E review artifact must be an object"]
    schema = _load_schema(schema_version)
    return schema_subset_errors(value, schema, schema)


def _without_digest(value: dict[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}


def _reviewed_head_tree(candidate: dict[str, Any]) -> tuple[str, str]:
    if candidate.get("schema_version") == "s2e_launch_genesis_receipt_v1":
        return (
            str(candidate.get("schema_carrier_head", "")),
            str(candidate.get("schema_carrier_tree", "")),
        )
    if candidate.get("schema_version") == "s2e_launch_wave_receipt_v1":
        return (
            str(candidate.get("source_head", "")),
            str(candidate.get("source_tree", "")),
        )
    raise ValueError("unsupported S2E launch candidate schema")


def _python_module_names(path: str) -> set[str]:
    relative = path.removesuffix(".py")
    parts = relative.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    dotted = ".".join(parts)
    names = {dotted}
    if parts:
        names.add(parts[-1])
    for prefix in (
        ("helper_scripts", "maintenance_scripts"),
        ("program_code", "ml_training"),
        ("tests", "structure"),
        ("program_code", "ml_training", "tests"),
    ):
        if tuple(parts[: len(prefix)]) == prefix and len(parts) > len(prefix):
            names.add(".".join(parts[len(prefix):]))
    return {name for name in names if name}


def _repo_python_import_closure(
    selected: set[str],
    *,
    tracked: list[str],
    reviewed_head: str,
    repo_root: Path,
) -> set[str]:
    """Expand every repo-local import from exact candidate Git blobs."""

    python_paths = {
        path
        for path in tracked
        if path.endswith(".py")
        and path.startswith(
            (
                "helper_scripts/maintenance_scripts/",
                "program_code/ml_training/",
                "tests/structure/",
            )
        )
    }
    module_index: dict[str, set[str]] = {}
    for path in python_paths:
        for name in _python_module_names(path):
            module_index.setdefault(name, set()).add(path)

    queue: list[str] = []
    queued: set[str] = set()
    parsed: set[str] = set()

    def enqueue_with_package_initializers(path: str) -> None:
        if path not in python_paths:
            return
        dependencies = {path}
        parent = PurePath(path).parent
        while parent.parts:
            initializer = (parent / "__init__.py").as_posix()
            if initializer in python_paths:
                dependencies.add(initializer)
            parent = parent.parent
        for dependency in sorted(dependencies):
            selected.add(dependency)
            if dependency not in queued:
                queued.add(dependency)
                queue.append(dependency)

    for path in sorted(selected):
        enqueue_with_package_initializers(path)
    while queue:
        path = queue.pop(0)
        if path in parsed:
            continue
        parsed.add(path)
        try:
            tree = ast.parse(
                _git_bytes(repo_root, "show", f"{reviewed_head}:{path}"),
                filename=path,
            )
        except (SyntaxError, UnicodeDecodeError) as error:
            raise ValueError(
                f"S2E review dependency blob is not parseable Python: {path}: {error}"
            ) from error
        imported_names: set[str] = set()
        relative_paths: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parent = PurePath(path).parent
                    for _ in range(max(node.level - 1, 0)):
                        parent = parent.parent
                    if node.module:
                        relative_paths.add(
                            (parent / f"{node.module.replace('.', '/')}.py")
                            .as_posix()
                        )
                    for alias in node.names:
                        module = (
                            f"{node.module}.{alias.name}"
                            if node.module
                            else alias.name
                        )
                        relative_paths.add(
                            (parent / f"{module.replace('.', '/')}.py")
                            .as_posix()
                        )
                elif node.module:
                    imported_names.add(node.module)
                    imported_names.update(
                        f"{node.module}.{alias.name}"
                        for alias in node.names
                    )
            elif (
                isinstance(node, ast.Call)
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and (
                    (
                        isinstance(node.func, ast.Name)
                        and node.func.id == "__import__"
                    )
                    or (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == "import_module"
                    )
                )
            ):
                imported_names.add(node.args[0].value)
        discovered = set(relative_paths) & python_paths
        for name in imported_names:
            candidates = module_index.get(name, set())
            if not candidates and "." in name:
                candidates = module_index.get(name.rsplit(".", 1)[-1], set())
            discovered.update(candidates)
        for dependency in sorted(discovered):
            enqueue_with_package_initializers(dependency)
    return selected


def _s2e_review_source_paths(
    candidate: dict[str, Any], *, repo_root: Path
) -> list[str]:
    wave = str(candidate.get("wave", ""))
    reviewed_head, _ = _reviewed_head_tree(candidate)
    tracked = _git(
        repo_root, "ls-tree", "-r", "--name-only", reviewed_head
    ).stdout.splitlines()
    if wave == GENESIS_WAVE:
        selected = set(S2E_REVIEW_BASE_PATHS)
    elif wave == "S2E-LW1":
        selected = set(S2E_REVIEW_BASE_PATHS)
        selected.update(S2E_LW1_REVIEW_PATHS)
        selected.update(
            path
            for path in tracked
            if any(path.startswith(prefix) for prefix in S2E_LW1_REVIEW_PREFIXES)
        )
    else:
        raise ValueError(f"{wave} acceptance review profile is not implemented")
    return sorted(_repo_python_import_closure(
        selected,
        tracked=tracked,
        reviewed_head=reviewed_head,
        repo_root=repo_root,
    ))


def s2e_review_source_blob_manifest(
    candidate: dict[str, Any], *, repo_root: Path
) -> list[dict[str, str]]:
    """Re-read every governed source/test byte from the candidate's Git tree."""

    reviewed_head, reviewed_tree = _reviewed_head_tree(candidate)
    if _tree(repo_root, reviewed_head) != reviewed_tree:
        raise ValueError("reviewed source tree differs from candidate")
    manifest: list[dict[str, str]] = []
    for path in _s2e_review_source_paths(candidate, repo_root=repo_root):
        listing = _git(
            repo_root, "ls-tree", reviewed_head, "--", path
        ).stdout.rstrip("\n")
        if not listing:
            raise ValueError(f"required S2E review Git blob is missing: {path}")
        metadata, listed_path = listing.split("\t", 1)
        mode, object_type, blob = metadata.split()
        if listed_path != path or object_type != "blob" or mode not in {
            "100644",
            "100755",
        }:
            raise ValueError(f"S2E review path is not one regular Git blob: {path}")
        raw = _git_bytes(repo_root, "show", f"{reviewed_head}:{path}")
        manifest.append({
            "path": path,
            "mode": mode,
            "git_blob": blob,
            "sha256": _raw_digest(raw),
        })
    return manifest


def s2e_review_test_argv(
    candidate: dict[str, Any], *, repo_root: Path
) -> list[str]:
    """Return the one exact, shell-free pytest argv accepted for a wave."""

    wave = str(candidate.get("wave", ""))
    if wave == GENESIS_WAVE:
        tests = [
            "program_code/ml_training/tests/"
            "test_aiml_gate_receipt_validator_s2_4.py",
            "tests/structure/test_agent_governance_s2_2b.py",
            "tests/structure/test_agent_governance_command_capture_v2.py",
            "tests/structure/test_agent_governance_node_permissions.py",
            "tests/structure/test_agent_governance_s2e_external_evidence.py",
            "tests/structure/test_agent_governance_s2e_launch_chain.py",
            "tests/structure/test_agent_governance_s2e_launch_hardening.py",
            "tests/structure/test_agent_governance_s2e_launch_receipts.py",
        ]
    elif wave == "S2E-LW1":
        reviewed_head, _ = _reviewed_head_tree(candidate)
        tracked = _git(
            repo_root, "ls-tree", "-r", "--name-only", reviewed_head
        ).stdout.splitlines()
        owned_paths = set(S2E_REVIEW_BASE_PATHS)
        owned_paths.update(S2E_LW1_REVIEW_PATHS)
        owned_paths.update(
            path
            for path in tracked
            if any(
                path.startswith(prefix)
                for prefix in S2E_LW1_REVIEW_PREFIXES
            )
        )
        tests = sorted(
            path
            for path in owned_paths
            if (
                path.startswith("tests/")
                or path.startswith("program_code/ml_training/tests/")
            )
            and Path(path).name.startswith("test_")
            and path.endswith(".py")
        )
    else:
        raise ValueError(f"{wave} acceptance test profile is not implemented")
    return [
        "python3",
        "-S",
        "-c",
        GOVERNED_PYTEST_BOOTSTRAP,
        *GOVERNED_PYTEST_REQUIRED_ARGS,
        "-q",
        *tests,
    ]


def _manifest_evidence_digest(
    manifest: list[dict[str, str]], *, predicate_id: str
) -> str:
    if predicate_id == "OWNED_GIT_BLOB_REPLAY_VALID":
        selected = manifest
    else:
        tokens = _LW1_PREDICATE_PATH_TOKENS[predicate_id]
        selected = [
            entry
            for entry in manifest
            if any(token in entry["path"] for token in tokens)
        ]
    if not selected:
        raise ValueError(f"{predicate_id} has no code-owned Git blob evidence")
    return canonical_digest({
        "schema_version": "s2e_review_git_blob_evidence_v1",
        "predicate_id": predicate_id,
        "entries": selected,
    })


def _line_policy_evidence(
    candidate: dict[str, Any],
    manifest: list[dict[str, str]],
    *,
    repo_root: Path,
) -> str:
    reviewed_head, _ = _reviewed_head_tree(candidate)
    path = "program_code/ml_training/aiml_gate_receipt_validator.py"
    entry = next((item for item in manifest if item["path"] == path), None)
    if entry is None:
        raise ValueError("LW1 line-policy validator blob is absent")
    raw = _git_bytes(repo_root, "show", f"{reviewed_head}:{path}")
    line_count = raw.count(b"\n") + int(bool(raw) and not raw.endswith(b"\n"))
    policy_branch = "ACTUAL_SPLIT_AT_OR_BELOW_2000"
    if line_count > 2000:
        registry = _git_bytes(
            repo_root,
            "show",
            (
                f"{reviewed_head}:"
                "docs/references/2000_line_exception_registry.md"
            ),
        ).decode("utf-8")
        required_markers = (
            f"`{path}`",
            "owner",
            "reason",
            "trigger",
            "review",
        )
        if not all(marker.lower() in registry.lower() for marker in required_markers):
            raise ValueError(
                "LW1 validator exceeds 2000 lines without a closed exception entry"
            )
        policy_branch = "DOCUMENTED_PRE_EXISTING_EXCEPTION"
    return canonical_digest({
        "schema_version": "s2e_review_line_policy_evidence_v1",
        "path": path,
        "git_blob": entry["git_blob"],
        "line_count": line_count,
        "threshold": 2000,
        "policy_branch": policy_branch,
    })


def _exit_boundary_evidence(
    candidate: dict[str, Any],
    manifest: list[dict[str, str]],
    *,
    repo_root: Path,
) -> str:
    reviewed_head, _ = _reviewed_head_tree(candidate)
    entry = next((item for item in manifest if item["path"] == "TODO.md"), None)
    if entry is None:
        raise ValueError("LW1 exit-boundary TODO blob is absent")
    text = _git_bytes(
        repo_root, "show", f"{reviewed_head}:TODO.md"
    ).decode("utf-8")
    rows = [
        line
        for line in text.splitlines()
        if line.lstrip().startswith("| `S2E.2b-2` |")
    ]
    if len(rows) != 1:
        raise ValueError("LW1 exit boundary cannot identify one S2E.2b-2 row")
    cells = [cell.strip() for cell in rows[0].split("|")[1:-1]]
    if len(cells) < 2:
        raise ValueError("LW1 exit boundary row has no package-state cell")
    status_cell = cells[1]
    if not status_cell.startswith("**") or not status_cell.endswith("**"):
        raise ValueError("LW1 exit boundary package-state cell is not canonical")
    observed_state = status_cell[2:-2].split("/", 1)[0].strip()
    if observed_state != "ACTIVE":
        raise ValueError("LW1 illegally flips S2E.2b-2 package state")
    return canonical_digest({
        "schema_version": "s2e_review_exit_boundary_evidence_v1",
        "path": "TODO.md",
        "git_blob": entry["git_blob"],
        "package_id": "S2E.2b-2",
        "observed_state": observed_state,
        "wave_exit_id": candidate.get("wave_exit_id"),
    })


def _capture_evidence(
    candidate: dict[str, Any],
    capture: Any,
    *,
    repo_root: Path,
) -> str:
    if not isinstance(capture, dict):
        raise ValueError("S2E review requires one governed capture")
    expected_argv = s2e_review_test_argv(candidate, repo_root=repo_root)
    reviewed_head, _ = _reviewed_head_tree(candidate)
    before = capture.get("whole_repository_before", {})
    after = capture.get("whole_repository_after", {})
    if (
        capture.get("argv") != expected_argv
        or capture.get("result") != "PASS"
        or capture.get("exit_code") != 0
        or capture.get("task_contract_digest")
        != candidate.get("generation_task_contract_digest")
        or before.get("source_head") != reviewed_head
        or after.get("source_head") != reviewed_head
        or before.get("generation_digest") != after.get("generation_digest")
    ):
        raise ValueError(
            "governed capture is not an exact same-generation S2E pytest PASS"
        )
    digest = capture.get("record_digest")
    if not isinstance(digest, str):
        raise ValueError("governed S2E capture digest is absent")
    return digest


def s2e_review_predicate_results(
    candidate: dict[str, Any],
    *,
    source_blob_manifest: Any,
    governed_capture_record: Any,
    disposable_test_effect_chains: Any,
    predecessor_chain: Any,
    repo_root: Path,
) -> list[dict[str, Any]]:
    """Recompute code-owned predicate evidence; callers cannot submit PASS labels."""

    wave = str(candidate.get("wave", ""))
    expected_manifest = s2e_review_source_blob_manifest(
        candidate, repo_root=repo_root
    )
    if source_blob_manifest != expected_manifest:
        raise ValueError("predicate oracle source manifest differs from Git")
    capture_digest = _capture_evidence(
        candidate, governed_capture_record, repo_root=repo_root
    )
    if not isinstance(disposable_test_effect_chains, list):
        raise ValueError("predicate oracle disposable chains must be a list")
    if not disposable_test_effect_chains:
        raise ValueError("predicate oracle requires typed disposable test evidence")
    chain_digests: list[str] = []
    for chain in disposable_test_effect_chains:
        errors = validate_s2e_disposable_test_effect_chain(
            chain,
            candidate=candidate,
            governed_capture_record=governed_capture_record,
            repo_root=repo_root,
        )
        if errors:
            raise ValueError("; ".join(errors))
        chain_digests.append(str(chain["chain_digest"]))
    if not isinstance(predecessor_chain, list):
        raise ValueError("predicate oracle predecessor chain must be a list")
    if wave == GENESIS_WAVE:
        predicate_ids = _S2E_REVIEW_COMMON_PREDICATES
        if predecessor_chain:
            raise ValueError("genesis predicate oracle cannot consume a predecessor")
    elif wave == "S2E-LW1":
        predicate_ids = (
            _S2E_REVIEW_COMMON_PREDICATES
            + ("PREDECESSOR_CHAIN_VALID",)
            + _S2E_LW1_REVIEW_PREDICATES
        )
        if (
            not predecessor_chain
            or not isinstance(predecessor_chain[-1], dict)
            or predecessor_chain[-1].get("payload_digest")
            != candidate.get("predecessor")
            or predecessor_chain[-1].get("checkpoint_status")
            != "W0_GENESIS_READY"
        ):
            raise ValueError("LW1 predicate oracle predecessor is not exact READY W0")
    else:
        raise ValueError(f"{wave} predicate oracle is not implemented")
    reviewed_head, reviewed_tree = _reviewed_head_tree(candidate)
    manifest_digest = canonical_digest({
        "schema_version": "s2e_review_source_blob_manifest_v1",
        "entries": expected_manifest,
    })
    evidence: dict[str, list[str]] = {
        "CANDIDATE_SCHEMA_VALID": [
            canonical_digest({
                "schema_version": "s2e_review_candidate_schema_evidence_v1",
                "candidate_schema_version": candidate.get("schema_version"),
                "candidate_payload_digest": candidate.get("payload_digest"),
            })
        ],
        "EXACT_SOURCE_HEAD_TREE_VALID": [
            canonical_digest({
                "schema_version": "s2e_review_source_identity_evidence_v1",
                "reviewed_source_head": reviewed_head,
                "reviewed_source_tree": reviewed_tree,
                "manifest_digest": manifest_digest,
            })
        ],
        "DURABILITY_ANCHOR_IMMUTABLE_READBACK_VALID": [
            canonical_digest({
                "schema_version": "s2e_review_durability_anchor_requirement_v1",
                "candidate_payload_digest": candidate.get("payload_digest"),
                "required_adapter": "TRUSTED_HOST_SSHSIG_APPEND_ONLY_V1",
                "immutable_readback_required": True,
            })
        ],
        "INDEPENDENT_GOVERNED_REVIEW_VALID": [capture_digest],
        "INDEPENDENT_SSHSIG_VALID": [
            canonical_digest({
                "schema_version": "s2e_review_sshsig_requirement_v1",
                "candidate_payload_digest": candidate.get("payload_digest"),
                "identity": S2E_RECEIPT_SIGNER_IDENTITY,
                "namespace": S2E_RECEIPT_SIGNATURE_NAMESPACE,
                "independent_reviewer_required": True,
            })
        ],
    }
    if wave == "S2E-LW1":
        evidence["PREDECESSOR_CHAIN_VALID"] = [
            canonical_digest({
                "schema_version": "s2e_review_predecessor_chain_evidence_v1",
                "payload_digests": [
                    item.get("payload_digest") for item in predecessor_chain
                ],
            })
        ]
        evidence["OWNED_GIT_BLOB_REPLAY_VALID"] = [
            _manifest_evidence_digest(
                expected_manifest,
                predicate_id="OWNED_GIT_BLOB_REPLAY_VALID",
            )
        ]
        for predicate_id in _LW1_PREDICATE_PATH_TOKENS:
            evidence[predicate_id] = [
                capture_digest,
                _manifest_evidence_digest(
                    expected_manifest, predicate_id=predicate_id
                ),
            ]
        evidence["LW1_DISPOSABLE_EFFECT_CHAIN_VALID"] = sorted(chain_digests)
        evidence["LW1_VALIDATOR_LINE_POLICY_VALID"] = [
            _line_policy_evidence(
                candidate, expected_manifest, repo_root=repo_root
            )
        ]
        evidence["LW1_EXIT_BOUNDARY_VALID"] = [
            _exit_boundary_evidence(
                candidate, expected_manifest, repo_root=repo_root
            )
        ]
    return [
        {
            "predicate_id": predicate_id,
            "result": "PASS",
            "evidence_digests": sorted(set(evidence[predicate_id])),
        }
        for predicate_id in predicate_ids
    ]


def build_s2e_disposable_test_effect_chain(
    capture: dict[str, Any],
    *,
    candidate: dict[str, Any],
    repo_root: Path,
    observed_at: str | datetime,
) -> dict[str, Any]:
    """Derive a typed test-effect chain from one exact governed pytest capture."""

    reviewed_head, reviewed_tree = _reviewed_head_tree(candidate)
    expected_argv = s2e_review_test_argv(candidate, repo_root=repo_root)
    if capture.get("argv") != expected_argv:
        raise ValueError("governed capture argv is not the code-owned S2E test profile")
    if capture.get("task_contract_digest") != candidate.get(
        "generation_task_contract_digest"
    ):
        raise ValueError("governed capture task generation differs from candidate")
    if capture.get("result") != "PASS" or capture.get("exit_code") != 0:
        raise ValueError("governed S2E acceptance tests did not PASS")
    before = capture.get("whole_repository_before", {})
    after = capture.get("whole_repository_after", {})
    if (
        before.get("source_head") != reviewed_head
        or after.get("source_head") != reviewed_head
        or before.get("generation_digest") != after.get("generation_digest")
    ):
        raise ValueError("governed S2E tests are not bound to one clean source generation")
    effect_id = canonical_digest({
        "schema_version": "s2e_disposable_test_effect_identity_v1",
        "wave": candidate.get("wave"),
        "source_head": reviewed_head,
        "capture_record_digest": capture.get("record_digest"),
    })
    intent = {
        "schema_version": "s2e_disposable_test_intent_v1",
        "effect_id": effect_id,
        "wave": candidate.get("wave"),
        "wave_exit_id": candidate.get("wave_exit_id"),
        "source_head": reviewed_head,
        "source_tree": reviewed_tree,
        "target_profile_id": "governed_command_repository_policy_only_v1",
        "argv": expected_argv,
        "side_effect_class": "DISPOSABLE_TEST",
        "production_effect": False,
        "production_authority": False,
        "issued_at": capture.get("started_at"),
    }
    intent["intent_digest"] = canonical_digest(intent)
    result = {
        "schema_version": "s2e_disposable_test_result_v1",
        "effect_id": effect_id,
        "intent_digest": intent["intent_digest"],
        "governed_capture_record_digest": capture.get("record_digest"),
        "status": "PASS",
        "exit_code": capture.get("exit_code"),
        "stdout_digest": capture.get("stdout", {}).get("digest"),
        "stderr_digest": capture.get("stderr", {}).get("digest"),
        "started_at": capture.get("started_at"),
        "completed_at": capture.get("completed_at"),
        "production_effect": False,
    }
    result["result_digest"] = canonical_digest(result)
    postcheck = {
        "schema_version": "s2e_disposable_test_postcheck_v1",
        "effect_id": effect_id,
        "result_digest": result["result_digest"],
        "source_head": reviewed_head,
        "repository_generation_before": before.get("generation_digest"),
        "repository_generation_after": after.get("generation_digest"),
        "repository_unchanged": True,
        "isolated_temp_root_cleanup": "TEMPORARY_DIRECTORY_CONTEXT_EXITED",
        "repository_residue_count": 0,
        "production_target_observed": False,
        "production_target_observation_scope": (
            "COMMAND_CAPTURE_REPOSITORY_POLICY_ONLY"
        ),
        "effect_enforcement": capture.get("effect_enforcement"),
        "host_sandbox_attestation_ref": capture.get(
            "host_sandbox_attestation_ref"
        ),
        "status": "PASS",
        "observed_at": _time(observed_at).isoformat(),
    }
    postcheck["postcheck_digest"] = canonical_digest(postcheck)
    rollback = {
        "schema_version": "s2e_disposable_test_rollback_v1",
        "effect_id": effect_id,
        "result_digest": result["result_digest"],
        "postcheck_digest": postcheck["postcheck_digest"],
        "status": "NOT_REQUIRED_CLEAN_POSTCHECK",
        "rollback_performed": False,
        "residue_count": 0,
        "production_effect": False,
    }
    rollback["rollback_digest"] = canonical_digest(rollback)
    chain = {
        "schema_version": "s2e_disposable_test_effect_chain_v1",
        "effect_id": effect_id,
        "wave": candidate.get("wave"),
        "wave_exit_id": candidate.get("wave_exit_id"),
        "source_head": reviewed_head,
        "source_tree": reviewed_tree,
        "side_effect_class": "DISPOSABLE_TEST",
        "production_effect_count": 0,
        "intent": intent,
        "result": result,
        "postcheck": postcheck,
        "rollback": rollback,
    }
    chain["chain_digest"] = canonical_digest(chain)
    errors = validate_s2e_disposable_test_effect_chain(
        chain,
        candidate=candidate,
        governed_capture_record=capture,
        repo_root=repo_root,
    )
    if errors:
        raise ValueError("; ".join(errors))
    return chain


def validate_s2e_disposable_test_effect_chain(
    chain: Any,
    *,
    candidate: dict[str, Any],
    governed_capture_record: Any,
    repo_root: Path,
) -> list[str]:
    errors = _schema_errors(chain, "s2e_disposable_test_effect_chain_v1")
    if errors or not isinstance(chain, dict):
        return errors
    capture = (
        governed_capture_record
        if isinstance(governed_capture_record, dict)
        else {}
    )
    reviewed_head, reviewed_tree = _reviewed_head_tree(candidate)
    expected_effect_id = canonical_digest({
        "schema_version": "s2e_disposable_test_effect_identity_v1",
        "wave": candidate.get("wave"),
        "source_head": reviewed_head,
        "capture_record_digest": capture.get("record_digest"),
    })
    for field, expected in (
        ("effect_id", expected_effect_id),
        ("wave", candidate.get("wave")),
        ("wave_exit_id", candidate.get("wave_exit_id")),
        ("source_head", reviewed_head),
        ("source_tree", reviewed_tree),
        ("side_effect_class", "DISPOSABLE_TEST"),
        ("production_effect_count", 0),
    ):
        if chain.get(field) != expected:
            errors.append(f"disposable test chain {field} binding differs")
    if chain.get("chain_digest") != canonical_digest(
        _without_digest(chain, "chain_digest")
    ):
        errors.append("disposable test chain digest is invalid")
    intent = chain.get("intent", {})
    result = chain.get("result", {})
    postcheck = chain.get("postcheck", {})
    rollback = chain.get("rollback", {})
    for item, digest_field, label in (
        (intent, "intent_digest", "intent"),
        (result, "result_digest", "result"),
        (postcheck, "postcheck_digest", "postcheck"),
        (rollback, "rollback_digest", "rollback"),
    ):
        if not isinstance(item, dict) or item.get(digest_field) != canonical_digest(
            _without_digest(item, digest_field)
        ):
            errors.append(f"disposable test {label} digest is invalid")
    for label, item in (
        ("intent", intent),
        ("result", result),
        ("postcheck", postcheck),
        ("rollback", rollback),
    ):
        if item.get("effect_id") != expected_effect_id:
            errors.append(f"disposable test {label} effect_id binding differs")
    for field, expected in (
        ("wave", candidate.get("wave")),
        ("wave_exit_id", candidate.get("wave_exit_id")),
        ("source_head", reviewed_head),
        ("source_tree", reviewed_tree),
        ("target_profile_id", "governed_command_repository_policy_only_v1"),
        ("issued_at", capture.get("started_at")),
    ):
        if intent.get(field) != expected:
            errors.append(f"disposable test intent {field} binding differs")
    if result.get("intent_digest") != intent.get("intent_digest"):
        errors.append("disposable test result does not bind exact intent")
    if postcheck.get("result_digest") != result.get("result_digest"):
        errors.append("disposable test postcheck does not bind exact result")
    if (
        rollback.get("result_digest") != result.get("result_digest")
        or rollback.get("postcheck_digest") != postcheck.get(
            "postcheck_digest"
        )
    ):
        errors.append("disposable test rollback does not bind result and postcheck")
    expected_argv = s2e_review_test_argv(candidate, repo_root=repo_root)
    if intent.get("argv") != expected_argv or capture.get("argv") != expected_argv:
        errors.append("disposable test argv is not the exact code-owned profile")
    if result.get("governed_capture_record_digest") != capture.get("record_digest"):
        errors.append("disposable test result does not bind governed capture")
    for field, expected in (
        ("exit_code", capture.get("exit_code")),
        ("stdout_digest", capture.get("stdout", {}).get("digest")),
        ("stderr_digest", capture.get("stderr", {}).get("digest")),
    ):
        if result.get(field) != expected:
            errors.append(f"disposable test result {field} differs from capture")
    if capture.get("result") != "PASS" or result.get("status") != "PASS":
        errors.append("disposable test capture did not PASS")
    before = capture.get("whole_repository_before", {})
    after = capture.get("whole_repository_after", {})
    if (
        before.get("source_head") != reviewed_head
        or after.get("source_head") != reviewed_head
        or before.get("generation_digest") != after.get("generation_digest")
        or postcheck.get("source_head") != reviewed_head
        or postcheck.get("repository_generation_before")
        != before.get("generation_digest")
        or postcheck.get("repository_generation_after")
        != after.get("generation_digest")
        or postcheck.get("repository_unchanged") is not True
        or postcheck.get("repository_residue_count") != 0
        or postcheck.get("production_target_observed") is not False
    ):
        errors.append("disposable test postcheck did not prove zero repository residue")
    if (
        postcheck.get("production_target_observation_scope")
        != "COMMAND_CAPTURE_REPOSITORY_POLICY_ONLY"
        or postcheck.get("effect_enforcement")
        != capture.get("effect_enforcement")
        or postcheck.get("host_sandbox_attestation_ref")
        != capture.get("host_sandbox_attestation_ref")
        or capture.get("effect_enforcement") != "repository_policy_only"
        or capture.get("host_sandbox_attestation_ref") is not None
    ):
        errors.append(
            "disposable test postcheck overstates its command-level evidence scope"
        )
    for field in ("started_at", "completed_at"):
        if result.get(field) != capture.get(field):
            errors.append(f"disposable test result {field} differs from capture")
    try:
        if _time(result.get("started_at")) > _time(result.get("completed_at")):
            errors.append("disposable test result timestamps are reversed")
        if _time(postcheck.get("observed_at")) < _time(
            result.get("completed_at")
        ):
            errors.append("disposable test postcheck predates command completion")
    except (TypeError, ValueError) as error:
        errors.append(f"disposable test timestamps are invalid: {error}")
    if (
        rollback.get("status") != "NOT_REQUIRED_CLEAN_POSTCHECK"
        or rollback.get("rollback_performed") is not False
        or rollback.get("residue_count") != 0
    ):
        errors.append("disposable test rollback is not the clean no-residue terminal")
    if any(
        item.get(field) is not False
        for item, field in (
            (intent, "production_effect"),
            (intent, "production_authority"),
            (result, "production_effect"),
            (rollback, "production_effect"),
        )
    ):
        errors.append("disposable test chain admits production authority or effect")
    return sorted(set(errors))
