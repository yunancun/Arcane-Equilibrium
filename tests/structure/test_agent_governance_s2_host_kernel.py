"""S2 trusted-host kernel structural proof.
The suite enforces one exec point, kernel-side argv re-assertion, capability
separation, and a derived owner allowlist. It also proves target class is
host-derived and process hardening is enforced.
"""
from __future__ import annotations
import ast
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
import agent_governance_alr_quiesce_inventory as qi  # noqa: E402
import agent_governance_s2_host_kernel as kernel  # noqa: E402
KERNEL_PATH = HELPERS / "agent_governance_s2_host_kernel.py"
RUNNER_FAMILY_GLOBS = ("agent_governance_s2_*host_*.py", "aiml_s2_*host_run*.py")
# Explicit exclusions still pass every raw-command rule and the import denylist.
NON_RUNNER_HOST_LEAVES = {
    "agent_governance_s2_4_host_identity.py": (
        "S2.4 HOST_IDENTITY_INSTALL row 的 typed driver Protocol 與純導出葉;它不驅動任何 lane、"
        "不持有主機能力,匯入面屬 s2_4_install_adapter_v1 的 component_paths 治理範圍"
    ),
}


def _discover_runner_family(helpers_dir: Path) -> list[Path]:
    """由磁碟導出受信 host runner family；只有具理由的 protocol 葉可除名。"""

    return sorted({
        path
        for glob in RUNNER_FAMILY_GLOBS
        for path in helpers_dir.glob(glob)
        if path.name not in NON_RUNNER_HOST_LEAVES
    })
RUNNER_FAMILY = tuple(_discover_runner_family(HELPERS))
# 四個 S2 effect adapter 的 apply 進入點 + 其驅動葉:observer/kernel 的 import closure 不得含它們。
APPLIER_MODULES = frozenset({
    "agent_governance_pg_observer_bootstrap",
    "agent_governance_alr_quiesce_fence",
    "agent_governance_s2_4_apply",
    "agent_governance_s2_4_install",
    "agent_governance_s2_4_install_driver",
    "agent_governance_s2_4_prepare",
    "agent_governance_s2_4_probe",
    "agent_governance_s2_5_lifecycle",
    "agent_governance_s2_5_driver",
})
# Positive imports are capability declarations; unlisted imports fail closed.
ALLOWED_STDLIB_IMPORTS = frozenset({
    "__future__", "argparse", "base64", "datetime", "errno", "fcntl", "hashlib", "json",
    "os", "pathlib", "re", "socket", "stat", "sys", "typing",
})
STDLIB_IMPORTS_BY_FILE = {"agent_governance_s2_5_recovery_lock.py": frozenset({"functools"})}
ALLOWED_THIRD_PARTY_IMPORTS = frozenset({"psycopg2"})
# Governance imports are per-file rather than family-wide.
GOVERNANCE_IMPORTS_BY_FILE: dict[str, frozenset[str]] = {
    "agent_governance_s2_5_recovery_lock.py": frozenset({"agent_governance_s2_5_disposable_profile", "agent_governance_schema", "aiml_gate_receipt_validator"}),
    "agent_governance_s2_5_recovery_anchor.py": frozenset({"agent_governance_s2_5_disposable_profile", "agent_governance_s2_5_recovery_store", "agent_governance_schema", "aiml_gate_receipt_validator"}),
    "agent_governance_s2_host_kernel.py": frozenset({
        "agent_governance_alr_quiesce_inventory",
    }),
    "agent_governance_s2_host_observer.py": frozenset({
        "agent_governance_alr_quiesce_inventory",
        "agent_governance_s2_host_kernel",
    }),
    "agent_governance_s2_0_host_runner.py": frozenset({
        "agent_governance_pg_observer_bootstrap",
        "agent_governance_s2_effect_binding",
        "agent_governance_s2_host_kernel",
    }),
    "agent_governance_s2_1_host_runner.py": frozenset({
        "agent_governance_alr_quiesce_fence",
        "agent_governance_alr_quiesce_inventory",
        "agent_governance_s2_effect_binding",
        "agent_governance_s2_host_kernel",
    }),
    "agent_governance_s2_4_host_storage.py": frozenset({
        "agent_governance_s2_4_journal",
        "agent_governance_s2_4_lock",
    }),
    "agent_governance_s2_4_host_recovery.py": frozenset({
        "agent_governance_s2_4_component",
        "agent_governance_s2_4_install_driver",
        "agent_governance_s2_4_install_evidence",
        "agent_governance_s2_4_journal",
        "agent_governance_s2_4_lock",
        "agent_governance_s2_4_reconcile",
        "aiml_gate_receipt_validator",
    }),
    "aiml_s2_effect_host_run.py": frozenset({
        "agent_governance_alr_quiesce_fence",
        "agent_governance_pg_observer_bootstrap",
        "agent_governance_s2_0_host_runner",
        "agent_governance_s2_1_host_runner",
        "agent_governance_s2_4_host_recovery",
        "agent_governance_s2_host_kernel",
        "agent_governance_s2_host_observer",
    }),
}
# Kernel-only modules expose process/FFI capability.
KERNEL_ONLY_IMPORTS = frozenset({
    "subprocess", "ctypes", "agent_governance_command_capture_v2",
})
# Exempt leaves retain an explicit exec-capable import denylist.
EXEC_CAPABLE_IMPORT_DENYLIST = frozenset({
    "pty", "importlib", "commands", "asyncio", "multiprocessing", "runpy", "imp",
    "code", "pdb", "timeit", "concurrent",
})
FORBIDDEN_RAW_COMMAND_NAMES = frozenset({
    "system", "popen", "startfile", "fork", "forkpty",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
    "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
    "posix_spawn", "posix_spawnp",
})
FORBIDDEN_BUILTINS = frozenset({
    "eval", "exec", "compile", "__import__", "globals", "locals", "vars",
})
DYNAMIC_ATTRIBUTE_BUILTINS = frozenset({
    "getattr", "setattr", "delattr", "__getattribute__",
})
OBFUSCATION_SENSITIVE_LITERALS = (
    FORBIDDEN_RAW_COMMAND_NAMES | FORBIDDEN_BUILTINS
    | {"subprocess", "importlib", "pty", "commands", "ctypes"}
)
FORBIDDEN_EXEC_CAPABILITY_NAMES = (
    FORBIDDEN_RAW_COMMAND_NAMES
    | FORBIDDEN_BUILTINS
    | {
        "run_module", "run_path", "import_module", "reload", "interact", "runcall",
        "runctx", "timeit", "repeat", "ProcessPoolExecutor", "create_subprocess_exec",
        "create_subprocess_shell", "capture_command",
    }
)
SUBPROCESS_EXEC_CAPABILITY_NAMES = frozenset({
    "run", "Popen", "call", "check_call", "check_output", "getoutput",
    "getstatusoutput",
})
def _present_family() -> list[Path]:
    return _discover_runner_family(HELPERS)

def _fold_string(node: ast.AST) -> str | None:
    """把純字面的 ``"a" + "b"`` 折成 ``"ab"``(其他形一律回 None)。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _fold_string(node.left)
        right = _fold_string(node.right)
        if left is not None and right is not None:
            return left + right
    return None

def _raw_command_findings(path: Path, *, exec_family: bool = True) -> list[str]:
    """Fail closed over imports, raw/dynamic callees, obfuscation and shell use.

    ``exec_family=False`` disables only the positive import list and shell-shape rule."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    is_kernel = path.name == KERNEL_PATH.name
    allowed_modules: frozenset[str] | None = None
    if exec_family:
        allowed_modules = (
            ALLOWED_STDLIB_IMPORTS
            | STDLIB_IMPORTS_BY_FILE.get(path.name, frozenset())
            | ALLOWED_THIRD_PARTY_IMPORTS
            | GOVERNANCE_IMPORTS_BY_FILE.get(path.name, frozenset())
        )
        if is_kernel:
            allowed_modules = allowed_modules | KERNEL_ONLY_IMPORTS
    findings: list[str] = []
    dynamic_callable_aliases: set[str] = set()
    dynamic_return_functions: set[str] = set()
    ctypes_handles: set[str] = set()
    builtins_aliases: set[str] = {"__builtins__", "builtins"}
    attribute_getter_aliases: set[str] = {"getattr"}
    module_registry_aliases: set[str] = set()
    module_registry_accessor_aliases: set[str] = set()
    module_lookup_aliases: set[str] = set()
    os_aliases: set[str] = {"os"}
    subprocess_aliases: set[str] = {"subprocess"}
    container_aliases: dict[str, object] = {}
    wildcard_key = ("dynamic",)
    sequence_wildcard_key = ("constant", ("sequence", "*"))
    sequence_uncertain_key = ("sequence_uncertain",)
    family_aliases = {
        "attribute_getter": attribute_getter_aliases,
        "builtins": builtins_aliases, "ctypes": ctypes_handles,
        "module_lookup": module_lookup_aliases,
        "module_registry_accessor": module_registry_accessor_aliases,
        "module_registry": module_registry_aliases, "os": os_aliases,
        "subprocess": subprocess_aliases,
    }
    for imported in (item for item in ast.walk(tree) if isinstance(item, ast.Import)):
        for alias in imported.names:
            if alias.name.split(".")[0] == "os":
                os_aliases.add(alias.asname or alias.name.split(".")[0])
    containing_function: dict[int, str] = {}
    for function in (
        item for item in ast.walk(tree)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        for child in ast.walk(function):
            containing_function[id(child)] = function.name
    def _check_module(lineno: int, module: str, rendered: str) -> None:
        top = (module or "").split(".")[0]
        if allowed_modules is None:
            if top in KERNEL_ONLY_IMPORTS:
                findings.append(
                    f"line {lineno}: kernel-only module outside the kernel: {rendered}"
                )
            elif top in EXEC_CAPABLE_IMPORT_DENYLIST:
                findings.append(
                    f"line {lineno}: exec-capable module on a non-runner leaf: {rendered}"
                )
            return
        if top in allowed_modules:
            return
        findings.append(f"line {lineno}: import outside the declared allowlist: {rendered}")
    def _flatten_provenance(provenance: object) -> set[str]:
        if isinstance(provenance, set):
            return set(provenance)
        families: set[str] = set()
        for member in provenance.values() if isinstance(provenance, dict) else ():
            families.update(_flatten_provenance(member))
        return families
    def _merge_provenance(left: object, right: object) -> object:
        if isinstance(left, dict) and isinstance(right, dict):
            merged = deepcopy(left)
            for key, member in right.items():
                merged[key] = _merge_provenance(merged[key], member) if key in merged else deepcopy(member)
            return merged
        return _flatten_provenance(left) | _flatten_provenance(right)
    def _key_token(node: ast.AST) -> object:
        return ("constant", node.value) if isinstance(node, ast.Constant) else ("expression", ast.dump(node, annotate_fields=False))
    def _target_path(node: ast.AST) -> tuple[str, list[ast.AST]] | None:
        slices: list[ast.AST] = []
        while isinstance(node, ast.Subscript):
            slices.append(node.slice)
            node = node.value
        return (node.id, list(reversed(slices))) if isinstance(node, ast.Name) else None
    def _write_provenance(current: object, slices: list[ast.AST], value: object) -> object:
        if not slices:
            return _merge_provenance(current, value)
        mapping = dict(current) if isinstance(current, dict) else {}
        token = _key_token(slices[0])
        child = _write_provenance(mapping.get(token, {}), slices[1:], value)
        mapping[token] = child
        if not isinstance(slices[0], ast.Constant):
            mapping[wildcard_key] = _merge_provenance(mapping.get(wildcard_key, set()), child)
        return mapping
    def _value_provenance(node: ast.AST | None) -> object:
        if isinstance(node, ast.Name):
            if node.id in container_aliases:
                return container_aliases[node.id]
            families = {family for family, aliases in family_aliases.items() if node.id in aliases}
            return families | ({"ctypes"} if node.id == "ctypes" else set())
        if isinstance(node, (ast.List, ast.Tuple)):
            members = {index: _value_provenance(item) for index, item in enumerate(node.elts)}
            members[("sequence_length", len(node.elts))] = set()
            return members
        if isinstance(node, ast.Dict):
            members: dict[object, object] = {}
            for key, item in zip(node.keys, node.values):
                if key is None:
                    expanded = _value_provenance(item)
                    members = _merge_provenance(members, expanded if isinstance(expanded, dict) else {wildcard_key: expanded})
                    continue
                provenance = _value_provenance(item)
                token = _key_token(key)
                members[token] = _merge_provenance(members[token], provenance) if token in members else provenance
                if not isinstance(key, ast.Constant):
                    members[wildcard_key] = _merge_provenance(members.get(wildcard_key, set()), provenance)
            return members
        if isinstance(node, ast.Attribute):
            if node.attr == "modules" and isinstance(node.value, ast.Name) and node.value.id == "sys":
                return {"module_registry"}
            return {"subprocess"} if node.attr == "subprocess" else set()
        if isinstance(node, ast.Call):
            called = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else None
            )
            if called == "__getattribute__" or called in attribute_getter_aliases:
                direct = isinstance(node.func, ast.Name)
                receiver = node.args[0] if direct and node.args else (
                    node.func.value if isinstance(node.func, ast.Attribute) else None
                )
                offset = 1 if direct else 0
                name_arg = node.args[offset] if len(node.args) > offset else None
                folded = _fold_string(name_arg) if name_arg is not None else None
                families = _flatten_provenance(_value_provenance(receiver))
                if (
                    folded == "modules" and isinstance(receiver, ast.Name)
                    and receiver.id == "sys"
                ):
                    return {"module_registry"}
                if folded in {"get", "__getitem__"} and "module_registry" in families:
                    return {"module_registry_accessor"}
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and (
                node.func.value.id == "ctypes" and node.func.attr == "CDLL"
            ):
                return {"ctypes"}
            if "module_registry_accessor" in _flatten_provenance(_value_provenance(node.func)):
                return {"module_lookup"}
            if (
                isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and "module_registry" in _flatten_provenance(_value_provenance(node.func.value))
            ):
                return {"module_lookup"}
            return set()
        if isinstance(node, ast.Subscript):
            provenance = _value_provenance(node.value)
            if isinstance(provenance, dict):
                if isinstance(node.slice, ast.Constant):
                    mapping = provenance
                    raw, keyed = mapping.get(node.slice.value), mapping.get(_key_token(node.slice))
                    exact = keyed if raw is None else raw if keyed is None else _merge_provenance(raw, keyed)
                    general = mapping.get(wildcard_key, set())
                    provenance = (
                        _merge_provenance(exact, general) if general else exact
                    ) if exact is not None else _merge_provenance(
                        mapping.get(sequence_wildcard_key, set()), general
                    )
                else:
                    provenance = _flatten_provenance(provenance)
            families = _flatten_provenance(provenance)
            if isinstance(provenance, set) and "module_registry" in families:
                return (families - {"module_registry"}) | {"module_lookup"}
            return provenance
        return set()
    def _value_families(node: ast.AST | None) -> set[str]:
        return _flatten_provenance(_value_provenance(node))
    def _module_registry(receiver: ast.AST | None) -> bool:
        return "module_registry" in _value_families(receiver)
    def _module_lookup(receiver: ast.AST | None) -> bool:
        return "module_lookup" in _value_families(receiver)
    def _builtins_source(node: ast.AST | None) -> bool:
        return "builtins" in _value_families(node)
    def _callee_capability(node: ast.AST) -> str | None:
        """Resolve only execution-capable callees; unknown data stays fail-closed."""
        def _sensitive_receiver(receiver: ast.AST | None) -> bool:
            return (
                bool(_value_families(receiver) & {
                    "builtins", "ctypes", "module_lookup", "module_registry",
                    "os", "subprocess",
                })
                or isinstance(receiver, ast.Attribute)
                and (
                    _sensitive_receiver(receiver.value)
                )
            )
        if isinstance(node, ast.Name):
            if node.id in FORBIDDEN_EXEC_CAPABILITY_NAMES:
                return node.id
            if node.id in dynamic_callable_aliases:
                return "dynamic callable alias"
            return None
        if isinstance(node, ast.Attribute):
            if (
                node.attr in SUBPROCESS_EXEC_CAPABILITY_NAMES
                and "module_lookup" in _value_families(node.value)
            ):
                return "dynamic module execution"
            if (
                node.attr in SUBPROCESS_EXEC_CAPABILITY_NAMES
                and "subprocess" in _value_families(node.value)
            ):
                return "raw subprocess execution"
            return node.attr if node.attr in FORBIDDEN_EXEC_CAPABILITY_NAMES else None
        if isinstance(node, ast.Subscript):
            key = _fold_string(node.slice)
            if key in FORBIDDEN_EXEC_CAPABILITY_NAMES:
                return "dynamic execution subscript"
            if (
                _builtins_source(node.value)
                or isinstance(node.value, ast.Name)
                and node.value.id in dynamic_callable_aliases
            ):
                return "dynamic execution subscript"
            if (
                _module_registry(node.value)
            ):
                return "dynamic module execution"
            if (
                isinstance(node.value, ast.Attribute)
                and node.value.attr == "__dict__"
                and _module_lookup(node.value.value)
            ):
                return "dynamic module execution"
            return None
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and _builtins_source(node.func.value)
            ):
                return "dynamic execution subscript"
            called = (
                node.func.id if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute) else None
            )
            if called in {"getattr", "__getattribute__"}:
                name_arg = (
                    node.args[1] if called == "getattr" and len(node.args) >= 2
                    else node.args[-1] if len(node.args) >= 2 else None
                )
                folded = _fold_string(name_arg) if name_arg is not None else None
                if folded in FORBIDDEN_EXEC_CAPABILITY_NAMES:
                    return folded
                receiver = (
                    node.args[0] if called == "getattr" and node.args
                    else node.func.value if isinstance(node.func, ast.Attribute) else None
                )
                if folded is None and _sensitive_receiver(receiver):
                    return "dynamic callable attribute"
            if isinstance(node.func, ast.Name) and node.func.id in dynamic_return_functions:
                return "dynamic callable return"
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            if any(_callee_capability(item) is not None for item in node.elts):
                return "dynamic callable container"
        if isinstance(node, ast.Dict):
            if any(
                item is not None and _callee_capability(item) is not None
                for item in node.values
            ):
                return "dynamic callable container"
        return None
    for function in (
        item for item in ast.walk(tree)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        if any(
            _callee_capability(item.value) is not None
            for item in ast.walk(function)
            if isinstance(item, ast.Return) and item.value is not None
        ):
            dynamic_return_functions.add(function.name)
    def _assignment_bindings(
        target: ast.AST, value: ast.AST | None, provenance: object | None = None
    ) -> list[tuple[ast.AST, ast.AST | None, object]]:
        provenance = _value_provenance(value) if provenance is None else provenance
        indexes = (
            sorted(key for key in provenance if isinstance(key, int))
            if isinstance(provenance, dict) else []
        )
        if isinstance(target, (ast.List, ast.Tuple)) and indexes == list(range(len(indexes))):
            targets = list(target.elts)
            values = list(value.elts) if isinstance(value, (ast.List, ast.Tuple)) else [None] * len(indexes)
            provenances = [provenance[index] for index in indexes]
            stars = [index for index, item in enumerate(targets) if isinstance(item, ast.Starred)]
            if len(stars) == 1:
                index = stars[0]
                suffix = len(targets) - index - 1
                if len(indexes) < index + suffix:
                    return [(target, value, provenance)]
                stop = len(indexes) - suffix
                pairs = list(zip(targets[:index], values[:index], provenances[:index]))
                pairs.append((targets[index].value, None, {
                    offset: item for offset, item in enumerate(provenances[index:stop])
                }))
                pairs.extend(zip(targets[index + 1:], values[stop:], provenances[stop:]))
            elif not stars and len(targets) == len(values):
                pairs = list(zip(targets, values, provenances))
            else:
                return [(target, value, provenance)]
            return [
                binding
                for item_target, item_value, item_provenance in pairs
                for binding in _assignment_bindings(item_target, item_value, item_provenance)
            ]
        return [(target, value, provenance)]
    def _sequence_length(provenance: object) -> int | None:
        if not isinstance(provenance, dict) or sequence_uncertain_key in provenance:
            return None
        return max((key[1] for key in provenance if isinstance(key, tuple) and len(key) == 2 and key[0] == "sequence_length" and isinstance(key[1], int)), default=None)
    def _merge_target(target: ast.AST, provenance: object) -> None:
        target_path = _target_path(target)
        if target_path is not None and not isinstance(target, ast.Name):
            root, slices = target_path
            container_aliases[root] = _write_provenance(
                container_aliases.get(root, {}), slices, provenance
            )
            return
        if isinstance(target, ast.Name):
            for family in _flatten_provenance(provenance):
                family_aliases[family].add(target.id)
            if isinstance(provenance, dict):
                container_aliases[target.id] = _merge_provenance(
                    container_aliases.get(target.id, {}), provenance
                )

    sequence_positions: dict[int, int] = {}
    alias_edges: dict[tuple[int, int], tuple[ast.AST, ast.AST]] = {}
    uncertain_flow = (
        ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.Try,
        ast.Match, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.BoolOp,
    ) + ((ast.TryStar,) if hasattr(ast, "TryStar") else ())
    def _structured_nodes(
        node: ast.AST, uncertain: bool = False
    ) -> object:
        current = uncertain or isinstance(node, uncertain_flow)
        yield node, current
        for child in ast.iter_child_nodes(node):
            yield from _structured_nodes(child, current)
    flow_nodes = tuple(_structured_nodes(tree))

    changed = True
    while changed:
        before = (
            repr(container_aliases),
            tuple((family, tuple(sorted(aliases))) for family, aliases in family_aliases.items()),
            tuple(sorted(dynamic_callable_aliases)),
            tuple(sorted(sequence_positions.items())),
        )
        for node, flow_uncertain in flow_nodes:
            value: ast.AST | None = None
            targets: list[ast.AST] = []
            sequence_receiver = None
            sequence_end = None
            sequence_is_uncertain = False
            if isinstance(node, ast.Assign):
                value, targets = node.value, list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                value, targets = node.value, [node.target]
            elif isinstance(node, ast.NamedExpr) or isinstance(node, ast.AugAssign) and isinstance(node.op, ast.BitOr):
                value, targets = node.value, [node.target]
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update" and (node.args or node.keywords):
                value = ast.Dict(
                    keys=([None] if node.args else []) + [
                        ast.Constant(keyword.arg) if keyword.arg is not None else None
                        for keyword in node.keywords
                    ],
                    values=([node.args[0]] if node.args else []) + [
                        keyword.value for keyword in node.keywords
                    ],
                )
                targets = [node.func.value]
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "setdefault" and len(node.args) > 1:
                value, targets = node.args[1], [ast.Subscript(value=node.func.value, slice=node.args[0], ctx=ast.Store())]
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"append", "extend"} and node.args:
                sequence_receiver = node.func.value
                receiver_provenance = _value_provenance(sequence_receiver)
                sequence_is_uncertain = flow_uncertain or (
                    isinstance(receiver_provenance, dict)
                    and sequence_uncertain_key in receiver_provenance
                )
                start = None if sequence_is_uncertain else sequence_positions.get(id(node))
                if start is None and not sequence_is_uncertain:
                    start = _sequence_length(receiver_provenance)
                    if start is not None:
                        sequence_positions[id(node)] = start
                count = 1 if node.func.attr == "append" else _sequence_length(
                    _value_provenance(node.args[0])
                )
                if start is not None and count is not None:
                    values = [node.args[0]] if node.func.attr == "append" else [
                        ast.Subscript(value=node.args[0], slice=ast.Constant(index), ctx=ast.Load())
                        for index in range(count)
                    ]
                    value = ast.Tuple(elts=values, ctx=ast.Load())
                    targets = [ast.Tuple(elts=[
                        ast.Subscript(value=sequence_receiver, slice=ast.Constant(start + index), ctx=ast.Store())
                        for index in range(count)
                    ], ctx=ast.Store())]
                    sequence_end = start + count
                else:
                    sequence_is_uncertain = True
                    value, targets = node.args[0], [ast.Subscript(
                        value=sequence_receiver, slice=ast.Constant(("sequence", "*")), ctx=ast.Store()
                    )]
            bindings = [
                binding
                for target in targets
                for binding in _assignment_bindings(target, value)
            ]
            if sequence_end is not None:
                bindings.append((sequence_receiver, None, {("sequence_length", sequence_end): set()}))
            if sequence_is_uncertain:
                bindings.append((sequence_receiver, None, {sequence_uncertain_key: set()}))
            for target, bound_value, provenance in bindings:
                is_alias = (
                    isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
                    and isinstance(target, (ast.Name, ast.Subscript))
                    and isinstance(bound_value, (ast.Name, ast.Subscript))
                )
                if is_alias:
                    alias_edges[(id(target), id(bound_value))] = (target, bound_value)
                _merge_target(target, provenance)
                if is_alias and flow_uncertain and (
                    isinstance(_value_provenance(target), dict)
                    or isinstance(_value_provenance(bound_value), dict)
                ):
                    marker = {sequence_uncertain_key: set()}
                    _merge_target(target, marker)
                    _merge_target(bound_value, marker)
            for target, bound_value, _ in bindings:
                if bound_value is None or _callee_capability(bound_value) is None:
                    continue
                names = [
                    item.id for item in ast.walk(target)
                    if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)
                ]
                for name in names:
                    if name not in dynamic_callable_aliases:
                        dynamic_callable_aliases.add(name)
        for left, right in alias_edges.values():
            _merge_target(left, _value_provenance(right))
            _merge_target(right, _value_provenance(left))
        changed = before != (
            repr(container_aliases),
            tuple((family, tuple(sorted(aliases))) for family, aliases in family_aliases.items()),
            tuple(sorted(dynamic_callable_aliases)),
            tuple(sorted(sequence_positions.items())),
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(node.lineno, alias.name, f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                findings.append(
                    f"line {node.lineno}: relative import is outside the declared allowlist"
                )
            _check_module(node.lineno, module, f"from {module} import ...")
            for alias in node.names:
                if alias.name == "*":
                    findings.append(
                        f"line {node.lineno}: star import is outside the declared capability allowlist"
                    )
                if alias.name in FORBIDDEN_RAW_COMMAND_NAMES or alias.name in FORBIDDEN_BUILTINS:
                    findings.append(
                        f"line {node.lineno}: from {module} import {alias.name}"
                    )
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_RAW_COMMAND_NAMES:
                findings.append(f"line {node.lineno}: attribute .{node.attr}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_BUILTINS and isinstance(node.ctx, ast.Load):
                findings.append(f"line {node.lineno}: builtin {node.id}")
        elif isinstance(node, ast.BinOp):
            folded = _fold_string(node)
            if folded in OBFUSCATION_SENSITIVE_LITERALS:
                findings.append(
                    f"line {node.lineno}: obfuscated identifier literal {folded!r}"
                )
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if exec_family and keyword.arg == "shell" and not (
                    isinstance(keyword.value, ast.Constant) and keyword.value.value is False
                ):
                    findings.append(f"line {node.lineno}: shell= is not the constant False")
            func = node.func
            called = (
                func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute) else None
            )
            if called in DYNAMIC_ATTRIBUTE_BUILTINS:
                name_arg = (
                    node.args[1] if called == "getattr" and len(node.args) >= 2
                    else node.args[-1] if len(node.args) >= 2 else None
                )
                if isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str):
                    if name_arg.value in OBFUSCATION_SENSITIVE_LITERALS:
                        findings.append(
                            f"line {node.lineno}: {called}(…, {name_arg.value!r})"
                        )
                elif not isinstance(name_arg, ast.Name):
                    findings.append(
                        f"line {node.lineno}: {called}() with a computed attribute name"
                    )
            capability = _callee_capability(func)
            if capability == "dynamic callable attribute":
                findings.append(f"line {node.lineno}: dynamic callable attribute")
            elif capability == "dynamic execution subscript":
                findings.append(f"line {node.lineno}: dynamic execution subscript")
            elif capability == "dynamic callable alias":
                findings.append(f"line {node.lineno}: dynamic callable alias")
            elif capability == "dynamic callable return":
                findings.append(f"line {node.lineno}: dynamic callable return")
            elif capability == "dynamic module execution":
                findings.append(f"line {node.lineno}: dynamic module execution")
            elif capability == "raw subprocess execution":
                exact_kernel_run = (
                    is_kernel
                    and containing_function.get(id(node)) == "_execute"
                    and isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "subprocess"
                    and func.attr == "run"
                    and len(node.args) == 1
                    and isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Name)
                    and node.args[0].func.id == "list"
                    and {
                        keyword.arg for keyword in node.keywords
                    } == {
                        "shell", "stdin", "stdout", "stderr", "env", "timeout", "check",
                    }
                    and all(
                        not (
                            keyword.arg in {"shell", "check"}
                            and not (
                                isinstance(keyword.value, ast.Constant)
                                and keyword.value.value is False
                            )
                        )
                        for keyword in node.keywords
                    )
                )
                if not exact_kernel_run:
                    findings.append(f"line {node.lineno}: raw subprocess execution")
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "ctypes"
                and func.attr in {"CDLL", "get_errno"}
            ):
                exact_cdll = (
                    is_kernel
                    and containing_function.get(id(node)) == "enforce_process_hardening"
                    and (
                        func.attr == "get_errno"
                        and not node.args
                        and not node.keywords
                        or func.attr == "CDLL"
                        and len(node.args) == 1
                        and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value is None
                        and len(node.keywords) == 1
                        and node.keywords[0].arg == "use_errno"
                        and isinstance(node.keywords[0].value, ast.Constant)
                        and node.keywords[0].value.value is True
                    )
                )
                if not exact_cdll:
                    findings.append(
                        f"line {node.lineno}: ctypes call outside the hardening allowlist"
                    )
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id in ctypes_handles
            ):
                exact_prctl = (
                    is_kernel
                    and containing_function.get(id(node)) == "enforce_process_hardening"
                    and func.attr == "prctl"
                    and len(node.args) == 5
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id in {"_PR_SET_DUMPABLE", "_PR_GET_DUMPABLE"}
                    and all(
                        isinstance(item, ast.Constant) and item.value == 0
                        for item in node.args[1:]
                    )
                    and not node.keywords
                )
                if not exact_prctl:
                    findings.append(
                        f"line {node.lineno}: ctypes call outside the hardening allowlist"
                    )
    return findings


def test_no_raw_command_outside_the_kernel():
    present = _present_family()
    assert KERNEL_PATH in present
    for path in present:
        findings = _raw_command_findings(path)
        assert findings == [], f"{path.name} carries a raw-command surface: {findings}"


def _unscanned_runner_candidates(helpers_dir: Path, family_names: set[str]) -> list[str]:
    """磁碟上「長得像 S2 受信主機 runner」但不在掃描家族、也未被顯式除名的檔案。"""

    discovered = {
        path.name for glob in RUNNER_FAMILY_GLOBS for path in helpers_dir.glob(glob)
    }
    return sorted(discovered - family_names - set(NON_RUNNER_HOST_LEAVES))


def test_every_file_that_looks_like_an_s2_host_runner_is_scanned():
    unscanned = _unscanned_runner_candidates(HELPERS, {path.name for path in RUNNER_FAMILY})
    assert unscanned == [], (
        f"{unscanned} match the S2 host-runner shape but are neither in RUNNER_FAMILY (so the "
        "AST no-raw-command scan never looks at them) nor declared in NON_RUNNER_HOST_LEAVES"
    )


def test_a_declared_non_runner_leaf_is_still_denied_every_exec_path():
    for name, reason in NON_RUNNER_HOST_LEAVES.items():
        path = HELPERS / name
        assert path.is_file(), name
        assert reason.strip(), name
        assert _raw_command_findings(path, exec_family=False) == [], name
        assert "subprocess" not in path.read_text(encoding="utf-8"), name


def test_the_exec_family_exemption_never_admits_a_kernel_only_module(tmp_path):
    for module in sorted(KERNEL_ONLY_IMPORTS):
        path = tmp_path / f"exempt_{module}.py"
        path.write_text(f"import {module}\n", encoding="utf-8")
        findings = _raw_command_findings(path, exec_family=False)
        assert any("kernel-only module outside the kernel" in item for item in findings), module


EXEMPT_LEAF_EXEC_COUNTEREXAMPLES = {
    "E2_pty_spawn_on_an_exempt_leaf": "import pty\n\n\ndef f(argv):\n    return pty.spawn(argv)\n",
    "E2_importlib_dynamic_name_on_an_exempt_leaf": (
        "import importlib\n\n\ndef f(name):\n    return importlib.import_module(name)\n"
    ),
    "asyncio_create_subprocess": (
        "import asyncio\n\n\nasync def f(argv):\n"
        "    return await asyncio.create_subprocess_exec(*argv)\n"
    ),
    "multiprocessing_spawn": (
        "import multiprocessing\n\n\ndef f(fn):\n    return multiprocessing.Process(target=fn)\n"
    ),
    "commands_legacy": ("import commands\n\n\ndef f(cmd):\n    return commands.getoutput(cmd)\n"),
}


@pytest.mark.parametrize("mutation", sorted(EXEMPT_LEAF_EXEC_COUNTEREXAMPLES))
def test_the_exec_family_exemption_never_admits_an_exec_capable_module(tmp_path, mutation):
    path = tmp_path / f"{mutation}.py"
    path.write_text(EXEMPT_LEAF_EXEC_COUNTEREXAMPLES[mutation], encoding="utf-8")
    findings = _raw_command_findings(path, exec_family=False)
    assert any("exec-capable module on a non-runner leaf" in item for item in findings), findings
    assert _raw_command_findings(path, exec_family=True)


@pytest.mark.parametrize("module", sorted(EXEC_CAPABLE_IMPORT_DENYLIST))
@pytest.mark.parametrize("form", ["import {m}", "import {m}.sub", "from {m} import x"])
def test_every_exec_capable_denylist_entry_is_caught_in_every_import_form(
    tmp_path, module, form
):
    path = tmp_path / f"denied_{module}_{abs(hash(form))}.py"
    path.write_text(form.format(m=module) + "\n", encoding="utf-8")
    assert any(
        "exec-capable module on a non-runner leaf" in item
        for item in _raw_command_findings(path, exec_family=False)
    ), (module, form)


def test_the_two_import_denylists_never_overlap_the_positive_allowlist():
    allowed = ALLOWED_STDLIB_IMPORTS | ALLOWED_THIRD_PARTY_IMPORTS
    for name, modules in GOVERNANCE_IMPORTS_BY_FILE.items():
        allowed = allowed | modules
    assert not (EXEC_CAPABLE_IMPORT_DENYLIST & allowed)
    assert not (EXEC_CAPABLE_IMPORT_DENYLIST & KERNEL_ONLY_IMPORTS)


def test_the_family_derivation_is_red_when_a_new_runner_is_left_out(tmp_path):
    (tmp_path / "agent_governance_s2_9_host_runner.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "aiml_s2_other_host_run.py").write_text("x = 1\n", encoding="utf-8")
    assert _unscanned_runner_candidates(tmp_path, set()) == [
        "agent_governance_s2_9_host_runner.py", "aiml_s2_other_host_run.py"
    ]
    assert _unscanned_runner_candidates(
        tmp_path,
        {"agent_governance_s2_9_host_runner.py", "aiml_s2_other_host_run.py"},
    ) == []


def test_the_runner_family_is_auto_discovered_not_copied_into_a_tuple(tmp_path):
    """新增 runner 不需第二次手改表；檔案一出現就立刻進 scanner 的輸入集合。"""

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
    assert _discover_runner_family(tmp_path) == sorted(expected)


def test_the_governance_import_allowlist_is_per_file_not_family_wide(tmp_path):
    """S2.4 補償 runner 需要的 applier 匯入面,絕不因此在 observer / kernel 上也成立。"""

    applier = sorted(APPLIER_MODULES & GOVERNANCE_IMPORTS_BY_FILE[
        "agent_governance_s2_4_host_recovery.py"
    ])
    assert applier, "the S2.4 recovery runner is expected to declare applier imports"
    source = "".join(f"import {module}\n" for module in applier)
    admitted = tmp_path / "agent_governance_s2_4_host_recovery.py"
    admitted.write_text(source, encoding="utf-8")
    assert _raw_command_findings(admitted) == []
    for name in ("agent_governance_s2_host_observer.py", "agent_governance_s2_host_kernel.py",
                 "agent_governance_s2_0_host_runner.py"):
        elsewhere = tmp_path / name
        elsewhere.write_text(source, encoding="utf-8")
        assert _raw_command_findings(elsewhere), name


def test_every_governance_allowlist_entry_belongs_to_a_family_member():
    family_names = {path.name for path in RUNNER_FAMILY} | {"agent_governance_s2_5_recovery_anchor.py", "agent_governance_s2_5_recovery_lock.py"}
    assert set(GOVERNANCE_IMPORTS_BY_FILE) <= family_names, sorted(
        set(GOVERNANCE_IMPORTS_BY_FILE) - family_names
    )
    for name, modules in GOVERNANCE_IMPORTS_BY_FILE.items():
        assert not (modules & KERNEL_ONLY_IMPORTS), name


AST_SCANNER_MUTATIONS = {
    "M2_from_os_import_system": (
        "from os import system as _s\n_s('id > /tmp/pwned')\n", "from os import system",
    ),
    "M2b_importlib_concat": (
        "import importlib\nimportlib.import_module('sub' + 'process').run(['id'])\n",
        "import outside the declared allowlist",
    ),
    "M2b_concat_literal_alone": (
        "def f(m):\n    return m('sub' + 'process')\n", "obfuscated identifier literal",
    ),
    "M2c_getattr_computed_name": (
        "import os\n_o = os\ngetattr(_o, 'sys' + 'tem')('id')\n",
        "getattr() with a computed attribute name",
    ),
    "M2c_getattr_constant_name": (
        "import os\ngetattr(os, 'system')('id')\n", "getattr(…, 'system')",
    ),
    "raw_import_subprocess": ("import subprocess\n", "import outside the declared allowlist"),
    "os_system_attribute": ("import os\nos.system('x')\n", "attribute .system"),
    "shell_true": (
        "import subprocess\nsubprocess.run(['x'], shell=True)\n", "shell= is not the constant False",
    ),
    "builtin_eval": ("eval('1')\n", "builtin eval"),
    "ctypes_libc_system": (
        "import ctypes\nctypes.CDLL(None).system(b'id')\n",
        "import outside the declared allowlist",
    ),
    "ctypes_attribute_even_if_imported_elsewhere": (
        "def f(libc):\n    libc.system(b'id')\n", "attribute .system",
    ),
    "pty_spawn": ("import pty\npty.spawn('/bin/sh')\n", "import outside the declared allowlist"),
    "dunder_import": ("__import__('subprocess')\n", "builtin __import__"),
    "dynamic_getattr_name_then_call": (
        "import os\n\ndef f(name, argv):\n    return getattr(os, name)(*argv)\n",
        "dynamic callable attribute",
    ),
    "builtins_string_index_then_call": (
        "def f(expr):\n    return __builtins__['e' + 'val'](expr)\n",
        "dynamic execution subscript",
    ),
    "compile_attribute_alias": (
        "def f(builtins_obj, source):\n"
        "    compiler = getattr(builtins_obj, 'compile')\n"
        "    return compiler(source, '<x>', 'exec')\n",
        "getattr(…, 'compile')",
    ),
    "dynamic_callable_alias_chain": (
        "import os\n\ndef f(name, argv):\n"
        "    first = getattr(os, name)\n    second = first\n    return second(*argv)\n",
        "dynamic callable alias",
    ),
    "dict_union_augassign": (
        "def f(key, expr):\n    outer = {}\n    outer |= {'cap': __builtins__}\n    return outer['cap'][key](expr)\n",
        "dynamic execution subscript",
    ),
    "builtins_alias_variable_subscript": (
        "def f(key, expr):\n"
        "    builtins_alias = __builtins__\n"
        "    return builtins_alias[key](expr)\n",
        "dynamic execution subscript",
    ),
    "variable_builtins_key_then_call": (
        "def f(key, expr):\n    return __builtins__[key](expr)\n", "dynamic execution subscript",
    ),
    "builtins_get_variable_key_then_call": (
        "def f(key, expr):\n    return __builtins__.get(key)(expr)\n", "dynamic execution subscript",
    ),
    "nested_starred_unpack_from_subscript": (
        "def f(key, expr):\n    source = (object(), (object(), __builtins__))\n"
        "    safe, *rest = source\n    safe2, *caps = rest[0]\n"
        "    return caps[0][key](expr)\n", "dynamic execution subscript",
    ),
    "dynamic_dict_key_nested_builtins_alias_variable_subscript": (
        "import sys\n\ndef f(slot, key, expr):\n"
        "    outer = {slot: [[__builtins__]], 'modules': [[sys.modules]]}\n"
        "    return outer[slot][0][0][key](expr)\n",
        "dynamic execution subscript",
    ),
    "dynamic_dict_key_alias_mismatch": (
        "def f(slot, other, key, expr):\n    outer = {slot: [[__builtins__]]}\n"
        "    return outer[other][0][0][key](expr)\n", "dynamic execution subscript",
    ),
    "starred_unpack_from_name": (
        "def f(key, expr):\n    source = (object(), __builtins__)\n"
        "    safe, *caps = source\n    return caps[0][key](expr)\n",
        "dynamic execution subscript",
    ),
    "starred_unpack_literal": (
        "def f(key, expr):\n    safe, *caps = (object(), __builtins__)\n"
        "    return caps[0][key](expr)\n", "dynamic execution subscript",
    ),
    "variable_sys_modules_key_then_run": (
        "import sys\n\ndef f(key, argv):\n    return sys.modules[key].run(argv)\n",
        "dynamic module execution",
    ),
    "sys_modules_alias_variable_subscript": (
        "import sys\n\ndef f(key, argv):\n"
        "    module_map = sys.modules\n"
        "    return module_map[key].run(argv)\n",
        "dynamic module execution",
    ),
    "sys_modules_get_variable_key_then_run": (
        "import sys\n\ndef f(key, argv):\n"
        "    return sys.modules.get(key).run(argv)\n",
        "dynamic module execution",
    ),
    "sys_modules_dunder_dict_variable_lookup": (
        "import sys\n\ndef f(module_key, name, argv):\n"
        "    return sys.modules[module_key].__dict__[name](argv)\n",
        "dynamic module execution",
    ),
    "assigned_sys_modules_lookup_alias_call": (
        "import sys\n\ndef f(module_key, argv):\n"
        "    sp = sys.modules[module_key]\n"
        "    return sp.call(argv)\n",
        "dynamic module execution",
    ),
    "recursive_mixed_container_sys_modules_alias_call": (
        "import sys\n\ndef f(module_key, argv):\n"
        "    outer = ({'level': [(sys.modules,)]},)\n"
        "    sp = outer[0]['level'][0][0][module_key]\n"
        "    return sp.call(argv)\n",
        "dynamic module execution",
    ),
    "dynamic_dict_sys_modules_sibling_alias_call": (
        "import sys\n\ndef f(slot, key, argv):\n"
        "    outer = {slot: [[__builtins__]], 'modules': [[sys.modules]]}\n"
        "    return outer['modules'][0][0][key].call(argv)\n", "dynamic module execution",
    ),
    "os_dunder_getattribute_then_call": (
        "import os\n\ndef f(name, argv):\n"
        "    return os.__getattribute__(os, name)(*argv)\n",
        "dynamic callable attribute",
    ),
    "imported_os_alias_variable_getattr": (
        "import os as operating_system\n\ndef f(name, argv):\n"
        "    return getattr(operating_system, name)(*argv)\n",
        "dynamic callable attribute",
    ),
    "assigned_os_alias_variable_getattr": (
        "import os\n\ndef f(name, argv):\n"
        "    other = os\n"
        "    return getattr(other, name)(*argv)\n",
        "dynamic callable attribute",
    ),
    "dict_expansion_from_name": (
        "def f(key, expr):\n    inner = {'cap': __builtins__}\n"
        "    outer = {**inner}\n    return outer['cap'][key](expr)\n",
        "dynamic execution subscript",
    ),
    "dict_update_mutation": (
        "def f(key, expr):\n    outer = {}\n    outer.update(cap=__builtins__)\n"
        "    return outer['cap'][key](expr)\n", "dynamic execution subscript",
    ),
    "dict_setdefault_mutation": (
        "def f(key, expr):\n    outer = {}\n    outer.setdefault('cap', __builtins__)\n"
        "    return outer['cap'][key](expr)\n", "dynamic execution subscript",
    ),
    "nested_dict_update_mutation": (
        "import os\n\ndef f(name, argv):\n    outer = {'nested': {}}\n"
        "    outer['nested'].update({'cap': os})\n"
        "    return getattr(outer['nested']['cap'], name)(*argv)\n",
        "dynamic callable attribute",
    ),
    "dict_held_os_alias": (
        "import os\n\ndef f(name, argv):\n    box = {'safe': object(), 'os': os}\n"
        "    return getattr(box['os'], name)(*argv)\n", "dynamic callable attribute",
    ),
    "subscript_target_builtins": (
        "def f(key, expr):\n    outer = {}\n    outer['cap'] = __builtins__\n"
        "    return outer['cap'][key](expr)\n", "dynamic execution subscript",
    ),
    "nested_subscript_target_os": (
        "import os\n\ndef f(name, argv):\n    outer = {'nested': {}}\n"
        "    outer['nested']['cap'] = os\n    return getattr(outer['nested']['cap'], name)(*argv)\n",
        "dynamic callable attribute",
    ),
    "nested_list_append_positions": (
        "def f(key, expr):\n    outer = {'nested': []}\n    outer['nested'].append({})\n"
        "    outer['nested'].append(__builtins__)\n    return outer['nested'][1][key](expr)\n",
        "dynamic execution subscript",
    ),
    "list_extend_name_positions": (
        "def f(key, expr):\n    source = [{}, __builtins__]\n    outer = []\n"
        "    outer.extend(source)\n    return outer[1][key](expr)\n", "dynamic execution subscript",
    ),
    "computed_getattr_stored_in_container": (
        "import os\n\ndef f(name, argv):\n"
        "    calls = [getattr(os, name)]\n    return calls[0](*argv)\n",
        "dynamic execution subscript",
    ),
    "computed_getattr_returned_then_called": (
        "import os\n\ndef pick(name):\n    return getattr(os, name)\n"
        "\ndef f(name, argv):\n    return pick(name)(*argv)\n",
        "dynamic callable return",
    ),
    "already_imported_kernel_subprocess_run": (
        "def f(kernel, argv):\n    return kernel.subprocess.run(argv)\n",
        "raw subprocess execution",
    ),
    "already_imported_kernel_subprocess_popen": (
        "def f(kernel, argv):\n    return kernel.subprocess.Popen(argv)\n",
        "raw subprocess execution",
    ),
    "already_imported_kernel_subprocess_call": (
        "def f(kernel, argv):\n    return kernel.subprocess.call(argv)\n",
        "raw subprocess execution",
    ),
    "already_imported_kernel_subprocess_check_call": (
        "def f(kernel, argv):\n    return kernel.subprocess.check_call(argv)\n",
        "raw subprocess execution",
    ),
    "already_imported_kernel_subprocess_check_output": (
        "def f(kernel, argv):\n    return kernel.subprocess.check_output(argv)\n",
        "raw subprocess execution",
    ),
    "already_imported_kernel_subprocess_getoutput": (
        "def f(kernel, command):\n    return kernel.subprocess.getoutput(command)\n",
        "raw subprocess execution",
    ),
    "already_imported_kernel_subprocess_getstatusoutput": (
        "def f(kernel, command):\n"
        "    return kernel.subprocess.getstatusoutput(command)\n",
        "raw subprocess execution",
    ),
    "assigned_kernel_subprocess_alias_call": (
        "def f(kernel, argv):\n"
        "    sp = kernel.subprocess\n"
        "    return sp.call(argv)\n",
        "raw subprocess execution",
    ),
    "assigned_kernel_subprocess_alias_check_output": (
        "def f(kernel, argv):\n"
        "    sp = kernel.subprocess\n"
        "    return sp.check_output(argv)\n",
        "raw subprocess execution",
    ),
    "runpy_import_alias": (
        "import runpy as runner\nrunner.run_path('payload.py')\n",
        "import outside the declared allowlist",
    ),
    "concurrent_futures_from_alias": (
        "from concurrent import futures as pool\npool.ProcessPoolExecutor()\n",
        "import outside the declared allowlist",
    ),
    "relative_import": (
        "from . import helper\n",
        "relative import is outside the declared allowlist",
    ),
    "star_import": (
        "from os import *\n",
        "star import is outside the declared capability allowlist",
    ),
    "string_import_builtin": (
        "def f(b):\n    return getattr(b, '__import__')('subprocess')\n",
        "getattr(…, '__import__')",
    ),
    "N16_governance_prefix_exec_module": (
        "import agent_governance_command_capture_v2 as cap\n"
        "cap.capture_command(['/bin/sh', '-c', 'id'])\n",
        "import outside the declared allowlist",
    ),
    "N16_governance_prefix_from_import": (
        "from agent_governance_command_capture_v2 import capture_command\n",
        "import outside the declared allowlist",
    ),
}


@pytest.mark.parametrize("mutation", sorted(AST_SCANNER_MUTATIONS))
def test_the_ast_scanner_actually_catches_a_violation(tmp_path, mutation):
    source, expected = AST_SCANNER_MUTATIONS[mutation]
    path = tmp_path / f"{mutation}.py"
    path.write_text(source, encoding="utf-8")
    findings = _raw_command_findings(path)
    assert any(expected in item for item in findings), (source, findings)


def test_kernel_ctypes_is_limited_to_the_exact_prctl_hardening_shapes(tmp_path):
    """Kernel-only import is not a blanket libc FFI capability."""

    path = tmp_path / KERNEL_PATH.name
    path.write_text(
        "import ctypes\n"
        "libc = ctypes.CDLL('/tmp/foreign.so', use_errno=True)\n"
        "libc.execve(b'/bin/id', (), ())\n",
        encoding="utf-8",
    )
    findings = _raw_command_findings(path)
    assert any("ctypes call outside the hardening allowlist" in item for item in findings)


def test_assigned_ctypes_handle_cannot_hide_dynamic_ffi_getattr(tmp_path):
    path = tmp_path / KERNEL_PATH.name
    path.write_text(
        "import ctypes\n"
        "def enforce_process_hardening(name, argv):\n"
        "    libc = ctypes.CDLL(None, use_errno=True)\n"
        "    other = libc\n"
        "    return getattr(other, name)(*argv)\n",
        encoding="utf-8",
    )
    findings = _raw_command_findings(path)
    assert any("dynamic callable attribute" in item for item in findings), findings


def test_nested_ctypes_handle_cannot_hide_dynamic_ffi_getattr(tmp_path):
    path = tmp_path / KERNEL_PATH.name
    source = (
        "import ctypes\n"
        "def enforce_process_hardening(name, argv):\n"
        "    libc = ctypes.CDLL(None, use_errno=True)\n"
        "    outer = [[libc, object()]]\n"
        "    return getattr(outer[0][0], name)(*argv)\n"
    )
    path.write_text(source, encoding="utf-8")
    findings = _raw_command_findings(path)
    assert any("dynamic callable attribute" in item for item in findings), findings
    path.write_text(source.replace("[0][0]", "[0][1]"), encoding="utf-8")
    assert _raw_command_findings(path) == []


def test_container_aliases_do_not_taint_a_benign_sibling(tmp_path):
    sources = (
        "outer = {'unsafe': [[__builtins__]], 'safe': [[{}]]}\nouter['safe'][0][0][key](expr)\n",
        "import sys\nouter = {'unsafe': [[sys.modules]], 'safe': [[{}]]}\nouter['safe'][0][0][key].call(argv)\n",
        "import os\nouter = {'unsafe': [[os]], 'safe': [[object()]]}\ngetattr(outer['safe'][0][0], name)\n",
        "safe, *caps = (object(), __builtins__)\ngetattr(safe, name)\n",
        "outer = {'nested': []}\nouter['nested'].append({})\nouter['nested'].append(__builtins__)\nouter['nested'][0][key](expr)\n",
        "source = [{}, __builtins__]\nouter = []\nouter.extend(source)\nouter[0][key](expr)\n",
    )
    for index, source in enumerate(sources):
        path = tmp_path / f"benign_container_sibling_{index}.py"
        path.write_text(source, encoding="utf-8")
        assert _raw_command_findings(path) == []


@pytest.mark.parametrize("mutation", sorted(AST_SCANNER_MUTATIONS))
def test_a_declared_non_runner_leaf_is_scanned_by_the_same_exec_rules(tmp_path, mutation):
    source, expected = AST_SCANNER_MUTATIONS[mutation]
    if expected in {"import outside the declared allowlist", "shell= is not the constant False"}:
        pytest.skip("this rule is deliberately exec-family-only; see _raw_command_findings")
    path = tmp_path / f"{mutation}.py"
    path.write_text(source, encoding="utf-8")
    assert any(expected in item for item in _raw_command_findings(path, exec_family=False))


def test_a_mutation_injected_into_a_real_family_file_is_caught(tmp_path):
    """把 M2 的突變真的注進一個**家族成員的副本**,證明掃描器對真檔也紅(不只對合成樣本)。"""

    for original in _present_family():
        mutated = tmp_path / original.name
        mutated.write_text(
            original.read_text(encoding="utf-8")
            + "\n\nfrom os import system as _s\n\n\ndef _pwn():\n    return _s('id')\n",
            encoding="utf-8",
        )
        findings = _raw_command_findings(mutated)
        assert any("from os import system" in item for item in findings), original.name


def test_the_import_allowlist_is_positive_and_kernel_only_imports_are_kernel_only(tmp_path):
    sample = tmp_path / "unknown_module.py"
    sample.write_text("import socketserver\n", encoding="utf-8")
    assert _raw_command_findings(sample)
    for module in sorted(KERNEL_ONLY_IMPORTS):
        elsewhere = tmp_path / f"not_the_kernel_{module}.py"
        elsewhere.write_text(f"import {module}\n", encoding="utf-8")
        assert _raw_command_findings(elsewhere), module


def test_kernel_is_the_only_family_member_importing_subprocess():
    for path in _present_family():
        source = path.read_text(encoding="utf-8")
        if path == KERNEL_PATH:
            assert "import subprocess" in source
        else:
            assert "subprocess" not in source, path.name


_FRAG = "/etc/systemd/system/arcane-equilibrium-aiml-engine-scanner.service"
_FLOCK = "/run/arcane-equilibrium/aiml-engine-scanner/consumer.lock"
_DSN = "/run/credentials/arcane-equilibrium-aiml-engine-scanner.service/pg-dsn"


class _RecordingProbe:
    """錄音式 host_probe:記下 owner 模組**實際**送出的每一條 argv。"""

    def __init__(self, proc_root: Path) -> None:
        self.proc_root = proc_root
        self.argv: list[tuple[str, ...]] = []

    def run(self, argv):
        self.argv.append(tuple(argv))
        if list(argv[:3]) == [qi.SYSTEMD, "show", qi.UNIT_NAME]:
            props = {
                "LoadState": "loaded", "ActiveState": "active", "SubState": "running",
                "MainPID": "0", "InvocationID": "inv", "NRestarts": "0", "ControlGroup": "",
                "FragmentPath": _FRAG, "DropInPaths": "", "NeedDaemonReload": "no",
                "Environment": "", "Restart": "on-failure", "RestartUSec": "5s",
                "TimeoutStopUSec": "30s", "WatchdogUSec": "0", "NoNewPrivileges": "yes",
                "ProtectSystem": "full", "PrivateTmp": "yes",
                "RestrictAddressFamilies": "AF_UNIX",
            }
            return "\n".join(f"{key}={props[key]}" for key in qi.QUIESCE_SHOW_PROPERTIES)
        if list(argv[:2]) == [qi.SYSTEMD, "list-units"]:
            return ""
        raise AssertionError(f"unexpected argv: {argv}")

    def dsn_stat(self):
        return {"dsn_file_path": _DSN, "dsn_mode": "0600", "dsn_owner_uid": 4001,
                "world_readable": False}

    def flock_held(self):
        return True


class _ScriptedCursor:
    """read_db_quiesce 的最小回應腳本(hashtext → holders → session*3 → queue usage)。"""

    def __init__(self) -> None:
        self._rows: list = []

    def execute(self, statement, parameters=None):
        text = " ".join(str(statement).split())
        if text.startswith("SELECT hashtext"):
            self._rows = [(1234,)]
        elif "pg_locks" in text:
            self._rows = []
        elif "pg_notification_queue_usage" in text:
            self._rows = [(0.0,)]
        else:
            self._rows = [(0,)]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def test_kernel_read_allowlist_equals_the_argv_the_owner_actually_issues(tmp_path):
    proc_root = tmp_path / "proc"
    (proc_root / "sys" / "kernel" / "random").mkdir(parents=True)
    (proc_root / "sys" / "kernel" / "random" / "boot_id").write_text("b\n", encoding="utf-8")
    probe = _RecordingProbe(proc_root)
    intent = {
        "flock_path": _FLOCK,
        "unit_fragment_path": _FRAG,
        "advisory_lock_name": qi.ADVISORY_LOCK_NAME,
        "consumer_session_relation": qi.DEFAULT_CONSUMER_SESSION_RELATION,
    }
    qi.build_owner_inventory(probe, _ScriptedCursor(), intent=intent)
    issued = set(probe.argv)
    assert issued, "the owner module issued no host command"
    assert issued == set(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])


def test_kernel_read_allowlist_is_accepted_by_the_owner_assert():
    for argv in kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ]:
        qi._assert_allowlisted_systemctl(list(argv))


def test_fence_allowlist_is_exactly_the_units_own_stop_start():
    fence = kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_FENCE]
    assert fence == frozenset({
        (qi.SYSTEMD, "stop", qi.UNIT_NAME),
        (qi.SYSTEMD, "start", qi.UNIT_NAME),
    })
    for argv in fence:
        assert argv[0] == qi.SYSTEMD
        assert argv[2] == qi.UNIT_NAME
        assert "--user" not in argv


def test_s2_0_session_has_no_argv_surface_at_all():
    assert kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_0_OBSERVER_BOOTSTRAP] == frozenset()
    with pytest.raises(kernel.S2HostArgvNotAllowlisted):
        kernel.assert_session_argv(kernel.SESSION_S2_0_OBSERVER_BOOTSTRAP, ["/usr/bin/psql", "-c", "select 1"])


@pytest.mark.parametrize("argv", [
    [qi.SYSTEMD, "stop", qi.UNIT_NAME],                                   # 唯讀 session 不得 stop
    [qi.SYSTEMD, "show", qi.UNIT_NAME],                                   # 屬性集不完整
    [qi.SYSTEMD, "--user", "show", qi.UNIT_NAME],                         # --user 形
    ["systemctl", "list-units", "--type=scope", "--state=active",
     "--no-legend", "--no-pager"],                                        # 非絕對路徑
    [qi.SYSTEMD, "list-units", "--type=scope", "--state=active", "--no-legend"],
])
def test_non_allowlisted_argv_raises_and_never_executes(argv, monkeypatch):
    def _boom(*args, **kwargs):  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("subprocess.run must never be reached for a non-allowlisted argv")

    monkeypatch.setattr(subprocess, "run", _boom)
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    with pytest.raises(kernel.S2HostArgvNotAllowlisted):
        host.run(argv)
    assert host.calls == []


def test_shell_string_argv_is_refused(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not execute"))
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    with pytest.raises(kernel.S2HostArgvNotAllowlisted):
        host.run(f"{qi.SYSTEMD} show {qi.UNIT_NAME}")


def test_there_is_no_generic_session():
    with pytest.raises(kernel.S2HostSessionError):
        kernel.HostExecutionKernel(session="generic")
    with pytest.raises(kernel.S2HostSessionError):
        kernel.session_argv_allowlist("anything_else")


def test_mutating_session_requires_explicit_acknowledgement():
    with pytest.raises(kernel.S2HostSessionError):
        kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_FENCE)
    with pytest.raises(kernel.S2HostSessionError):
        kernel.HostExecutionKernel(
            session=kernel.SESSION_S2_1_QUIESCE_READ, allow_mutation=True
        )
    fence = kernel.HostExecutionKernel(
        session=kernel.SESSION_S2_1_QUIESCE_FENCE, allow_mutation=True
    )
    assert fence.allow_mutation is True


def test_kernel_execution_is_shell_false_absolute_and_sanitized(monkeypatch):
    captured: dict = {}

    class _Completed:
        returncode = 0
        stdout = b"LoadState=loaded\n"
        stderr = b""

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _Completed()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    output = host.run(list(allowed))
    assert output == "LoadState=loaded\n"
    assert captured["argv"] == list(allowed)
    assert captured["argv"][0].startswith("/")
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["timeout"] == kernel.SESSION_TIMEOUT_SECONDS[
        kernel.SESSION_S2_1_QUIESCE_READ
    ]
    environment = captured["kwargs"]["env"]
    assert environment["LC_ALL"] == "C"
    assert not {"HOME", "PGPASSWORD", "PYTHONPATH"} & set(environment)


def test_nonzero_exit_and_timeout_fail_closed(monkeypatch):
    class _Failed:
        returncode = 3
        stdout = b""
        stderr = b"boom"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Failed())
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    with pytest.raises(kernel.S2HostCommandFailed):
        host.run(list(allowed))

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(subprocess, "run", _timeout)
    with pytest.raises(kernel.S2HostCommandFailed):
        host.run(list(allowed))


def test_stdout_is_redacted_with_the_existing_capture_v2_patterns(monkeypatch):
    class _Completed:
        returncode = 0
        stdout = b"Environment=PGPASSWORD=hunter2\n"
        stderr = b""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Completed())
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    output = host.run(list(allowed))
    assert "hunter2" not in output
    assert "<redacted>" in output


class _WriterSurface:
    def stop(self):  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("assert_read_only_surface must refuse BEFORE calling anything")

    def read(self):
        return "ok"


class _ReaderSurface:
    def read(self):
        return "ok"


def test_assert_read_only_surface_refuses_before_calling_anything():
    errors = kernel.assert_read_only_surface(_WriterSurface())
    assert errors and "stop" in errors[0]
    assert kernel.assert_read_only_surface(_ReaderSurface()) == []


def test_forbidden_read_only_surface_covers_the_four_adapter_mutators():
    for name in ("stop", "start", "create_read_only_observer", "compensate",
                 "signed_apply_attestation", "enable_now"):
        assert name in kernel.FORBIDDEN_READ_ONLY_SURFACE


def _force_host(monkeypatch, *, platform, hostname, writable, roots):
    monkeypatch.setattr(kernel.sys, "platform", platform)
    monkeypatch.setattr(kernel, "_observed_nodename", lambda: hostname)
    monkeypatch.setattr(kernel.socket, "gethostname", lambda: hostname)
    monkeypatch.setattr(kernel, "_writable", lambda path: writable)
    monkeypatch.setattr(kernel, "_present", lambda path: roots)


@pytest.mark.parametrize("platform,hostname,writable,roots,expected", [
    ("darwin", "trade-core", True, True, kernel.TARGET_CLASS_NON_TARGET),
    ("linux", "some-laptop", True, True, kernel.TARGET_CLASS_NON_TARGET),
    ("linux", "trade-core", False, False, kernel.TARGET_CLASS_UNKNOWN),
    ("linux", "trade-core", True, True, kernel.TARGET_CLASS_PRODUCTION),
    ("linux", "trade-core", None, True, kernel.TARGET_CLASS_UNKNOWN),
    ("linux", "trade-core", True, None, kernel.TARGET_CLASS_UNKNOWN),
    ("linux", "trade-core", True, False, kernel.TARGET_CLASS_UNKNOWN),
    ("linux", "trade-core", False, True, kernel.TARGET_CLASS_UNKNOWN),
])
def test_derive_host_target_class_matrix(monkeypatch, platform, hostname, writable, roots, expected):
    _force_host(monkeypatch, platform=platform, hostname=hostname, writable=writable, roots=roots)
    view = kernel.derive_host_target_class()
    assert view["target_class"] == expected
    assert view["facts"]["hostname"] == hostname


def test_derive_host_target_class_takes_no_caller_argument():
    import inspect

    assert list(inspect.signature(kernel.derive_host_target_class).parameters) == []


def test_this_development_machine_is_never_a_production_target():
    view = kernel.derive_host_target_class()
    if sys.platform != "linux":
        assert view["target_class"] == kernel.TARGET_CLASS_NON_TARGET


DIGEST = "sha256:" + "a" * 64


ADMITTED = {
    "allow_production": True, "production_confirm": DIGEST, "intent_digest": DIGEST,
    "operator_authorization_verified": True,
    "intent_target_class": kernel.INTENT_TARGET_CLASS_PRODUCTION,
}


@pytest.mark.parametrize("target_class", sorted(kernel.PRODUCTION_GRADE_TARGET_CLASSES))
def test_allow_production_alone_is_insufficient(target_class):
    view = {"target_class": target_class, "reason": "x", "facts": {}}
    errors = kernel.host_target_admission_errors(
        view, allow_production=True, production_confirm=None,
        intent_digest=DIGEST, operator_authorization_verified=False,
        intent_target_class=kernel.INTENT_TARGET_CLASS_PRODUCTION,
    )
    assert errors
    assert any("operator SSHSIG" in error for error in errors)
    assert any("--production-confirm" in error for error in errors)


@pytest.mark.parametrize("target_class", sorted(kernel.PRODUCTION_GRADE_TARGET_CLASSES))
def test_all_four_conditions_admit_and_any_missing_one_refuses(target_class):
    view = {"target_class": target_class, "reason": "x", "facts": {}}
    assert kernel.host_target_admission_errors(view, **ADMITTED) == []
    for override in (
        {"allow_production": False},
        {"operator_authorization_verified": False},
        {"production_confirm": "sha256:" + "b" * 64},
        {"production_confirm": None},
        {"intent_target_class": kernel.INTENT_TARGET_CLASS_DISPOSABLE_LOCAL},
        {"intent_target_class": None},
    ):
        assert kernel.host_target_admission_errors(view, **{**ADMITTED, **override})


def test_the_admission_predicate_cannot_silently_skip_the_intent_binding():
    """P1-B:``intent_target_class`` 是**必填** kwarg —— 忘了遞是 TypeError,不是靜默放行。"""

    import inspect

    parameter = inspect.signature(kernel.host_target_admission_errors).parameters[
        "intent_target_class"
    ]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


@pytest.mark.parametrize("target_class", sorted(kernel.PRODUCTION_GRADE_TARGET_CLASSES))
def test_a_disposable_local_intent_is_refused_on_a_production_grade_host(target_class):
    """P1-B:一份合法簽章的 ``disposable_local`` intent 絕不可在生產級主機上被承認。

    它若被承認,``apply_quiesce_fence`` 會走 disposable 分支,用**真的** kernel capability 發
    system-level ``stop``/``start``,再把那次真實 effect 標成 rehearsal 級的 local 證據。
    """

    view = {"target_class": target_class, "reason": "x", "facts": {}}
    errors = kernel.host_target_admission_errors(
        view, **{**ADMITTED, "intent_target_class": kernel.INTENT_TARGET_CLASS_DISPOSABLE_LOCAL}
    )
    assert len(errors) == 1
    assert kernel.INTENT_TARGET_CLASS_DISPOSABLE_LOCAL in errors[0]


def test_the_intent_binding_reason_never_echoes_the_caller_string():
    """理由字串會落進 artifact 與 stdout summary ⇒ 只准複述封閉枚舉,絕不回寫呼叫端遞來的位元組。"""

    view = {"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "x", "facts": {}}
    hostile = "PG" + "PASSWORD" + "=" + "s3cr3t-not-real"
    errors = kernel.host_target_admission_errors(
        view, **{**ADMITTED, "intent_target_class": hostile}
    )
    assert errors
    joined = " ".join(errors)
    assert hostile not in joined
    assert "unrecognized" in joined
    for unhashable in ([], {}, {"target_class": "production"}):
        assert kernel.host_target_admission_errors(
            view, **{**ADMITTED, "intent_target_class": unhashable}
        )


def test_non_target_and_the_rehearsal_only_class_are_both_refused():
    """P1-A:``disposable_candidate`` 是 rehearsal-only class ⇒ 生產進入點一律拒(曾經是放行)。"""

    assert kernel.host_target_admission_errors(
        {"target_class": kernel.TARGET_CLASS_NON_TARGET, "reason": "mac"}, **ADMITTED
    )
    errors = kernel.host_target_admission_errors(
        {"target_class": kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE, "reason": "throwaway"},
        **ADMITTED,
    )
    assert any("rehearsal-only" in error for error in errors)
    assert kernel.host_target_admission_errors(
        {"target_class": kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE, "reason": "throwaway"},
        allow_production=False, production_confirm=None, intent_digest=None,
        operator_authorization_verified=False, intent_target_class=None,
    )


def test_the_rehearsal_only_class_is_never_derivable_from_host_facts(monkeypatch):
    """P1-A 的核心:任何主機事實組合都導不出 ``disposable_candidate``。"""

    assert kernel.REHEARSAL_ONLY_TARGET_CLASSES == frozenset(
        {kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE}
    )
    assert not (kernel.DERIVABLE_TARGET_CLASSES & kernel.REHEARSAL_ONLY_TARGET_CLASSES)
    for platform in ("linux", "darwin"):
        for hostname in ("trade-core", "trade-core.internal", "some-laptop"):
            for writable in (True, False, None):
                for roots in (True, False, None):
                    _force_host(
                        monkeypatch, platform=platform, hostname=hostname,
                        writable=writable, roots=roots,
                    )
                    derived = kernel.derive_host_target_class()["target_class"]
                    assert derived in kernel.DERIVABLE_TARGET_CLASSES
                    assert derived not in kernel.REHEARSAL_ONLY_TARGET_CLASSES


@pytest.mark.parametrize("writable,roots", [(False, False), (False, True), (True, False)])
def test_an_unprovisioned_target_host_stays_inside_the_production_gate(monkeypatch, writable, roots):
    """P1-A 的實景:初始供裝 / 恢復期的真 trade-core(非 root、roots 未建)必須落 production 閘。"""

    _force_host(
        monkeypatch, platform="linux", hostname="trade-core", writable=writable, roots=roots
    )
    view = kernel.derive_host_target_class()
    assert view["target_class"] == kernel.TARGET_CLASS_UNKNOWN
    assert kernel.host_target_admission_errors(
        view, allow_production=False, production_confirm=None, intent_digest=None,
        operator_authorization_verified=False,
        intent_target_class=kernel.INTENT_TARGET_CLASS_PRODUCTION,
    )


def test_the_intent_target_classes_are_pinned_to_both_adapters():
    """kernel 不匯入 applier 模組,故 intent 側的字面量必須在測試裡對兩個 adapter 常量釘死。"""

    import agent_governance_alr_quiesce_fence as fence
    import agent_governance_pg_observer_bootstrap as bootstrap

    for adapter in (fence, bootstrap):
        assert kernel.INTENT_TARGET_CLASS_PRODUCTION == adapter.PRODUCTION_TARGET_CLASS
        assert kernel.INTENT_TARGET_CLASS_DISPOSABLE_LOCAL == adapter.DISPOSABLE_TARGET_CLASS
        assert kernel.INTENT_TARGET_CLASSES == adapter.TARGET_CLASSES


def test_unknown_is_treated_exactly_like_production():
    unknown = {"target_class": kernel.TARGET_CLASS_UNKNOWN, "reason": "x"}
    production = {"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "x"}
    for override in (
        {"allow_production": False},
        {"production_confirm": None},
        {"intent_target_class": kernel.INTENT_TARGET_CLASS_DISPOSABLE_LOCAL},
    ):
        kwargs = {**ADMITTED, **override}
        assert bool(kernel.host_target_admission_errors(unknown, **kwargs)) == bool(
            kernel.host_target_admission_errors(production, **kwargs)
        )


DISPOSABLE = {"target_class": kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE, "reason": "throwaway"}
NON_TARGET = {"target_class": kernel.TARGET_CLASS_NON_TARGET, "reason": "mac"}


@pytest.mark.parametrize("derived,injected,refused", [
    (DISPOSABLE, None, False),
    (NON_TARGET, None, False),
    ({"target_class": kernel.TARGET_CLASS_PRODUCTION}, None, True),
    ({"target_class": kernel.TARGET_CLASS_UNKNOWN}, None, True),
    ({"target_class": kernel.TARGET_CLASS_PRODUCTION}, DISPOSABLE, True),
    ({"target_class": kernel.TARGET_CLASS_UNKNOWN}, DISPOSABLE, True),
    (NON_TARGET, {"target_class": kernel.TARGET_CLASS_PRODUCTION}, True),
    (NON_TARGET, {"target_class": kernel.TARGET_CLASS_UNKNOWN}, True),
    (DISPOSABLE, {"target_class": kernel.TARGET_CLASS_PRODUCTION}, True),
])
def test_rehearsal_refusal_is_the_stricter_of_derived_and_injected(derived, injected, refused):
    assert bool(kernel.rehearsal_target_refusals(derived, injected)) is refused


def test_rehearsal_unknown_is_treated_exactly_like_production():
    assert kernel.REHEARSAL_REFUSED_TARGET_CLASSES == frozenset(
        {kernel.TARGET_CLASS_PRODUCTION, kernel.TARGET_CLASS_UNKNOWN}
    )


def test_the_recorded_target_class_is_always_the_derived_one():
    record = kernel.rehearsal_target_view_record(
        DISPOSABLE, {"target_class": kernel.TARGET_CLASS_NON_TARGET}
    )
    assert record["target_class"] == kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE
    assert record["derived"] is DISPOSABLE
    assert record["injected"] == {"target_class": kernel.TARGET_CLASS_NON_TARGET}
    assert record["injected_is_authoritative"] is False


def test_process_hardening_is_observed_and_load_bearing():
    observation = kernel.enforce_process_hardening(force=True)
    if sys.platform == "linux":
        assert observation == {"enforced": True, "observed_dumpable": 0, "reason": None}
    else:
        assert observation["enforced"] is False
        assert observation["observed_dumpable"] is None
        assert "executes no host command" not in observation["reason"]
        assert "cannot be observed on this platform" in observation["reason"]
        assert "may still execute here" in observation["reason"]


def test_process_hardening_is_re_observed_on_every_execution(monkeypatch):
    """P2 #10:快取會讓「執法」只發生一次;每次 exec 前都必須真的重新觀測。"""

    observations = {"count": 0}

    def _count(*, force: bool = False):
        observations["count"] += 1
        assert force is True, "run() must force a fresh observation, never reuse the cache"
        return {"enforced": True, "observed_dumpable": 0, "reason": None}

    class _Completed:
        returncode = 0
        stdout = b""
        stderr = b""

    monkeypatch.setattr(kernel, "enforce_process_hardening", _count)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Completed())
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    host.run(list(allowed))
    host.run(list(allowed))
    assert observations["count"] == 2


@pytest.mark.parametrize("target_class,allow,refused", [
    (kernel.TARGET_CLASS_NON_TARGET, False, False),
    (kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE, False, True),
    (kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE, True, True),
    (kernel.TARGET_CLASS_PRODUCTION, False, True),
    (kernel.TARGET_CLASS_UNKNOWN, False, True),      # unknown 同等對待
    (kernel.TARGET_CLASS_PRODUCTION, True, False),
    (kernel.TARGET_CLASS_UNKNOWN, True, False),
])
def test_read_only_observation_admission(target_class, allow, refused):
    errors = kernel.host_observation_admission_errors(
        {"target_class": target_class, "reason": "x"}, allow_production=allow
    )
    assert bool(errors) is refused


def test_the_observation_gate_is_deliberately_weaker_than_the_apply_gate():
    view = {"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "x"}
    assert kernel.host_observation_admission_errors(view, allow_production=True) == []
    assert kernel.host_target_admission_errors(
        view, allow_production=True, production_confirm=None, intent_digest=DIGEST,
        operator_authorization_verified=False,
        intent_target_class=kernel.INTENT_TARGET_CLASS_PRODUCTION,
    )


def test_hostname_comes_from_the_same_source_as_the_s1_6b_preflight():
    import agent_governance_target_host_probe as th
    import inspect

    assert "os.uname().nodename" in inspect.getsource(th.preflight_target_host)
    assert kernel._observed_nodename() == os.uname().nodename


@pytest.mark.parametrize("hostname,expected", [
    ("trade-core", kernel.TARGET_CLASS_PRODUCTION),
    ("trade-core.internal", kernel.TARGET_CLASS_PRODUCTION),   # FQDN nodename 仍是同一台
    ("trade-core-staging", kernel.TARGET_CLASS_NON_TARGET),    # 前綴相同但不是同一個 label
    ("some-laptop.trade-core", kernel.TARGET_CLASS_NON_TARGET),
])
def test_fqdn_nodename_still_resolves_to_the_pinned_target(monkeypatch, hostname, expected):
    monkeypatch.setattr(kernel.sys, "platform", "linux")
    monkeypatch.setattr(kernel, "_observed_nodename", lambda: hostname)
    monkeypatch.setattr(kernel, "_writable", lambda path: True)
    monkeypatch.setattr(kernel, "_present", lambda path: True)
    assert kernel.derive_host_target_class()["target_class"] == expected


def test_process_hardening_refusal_blocks_execution(monkeypatch):
    def _refuse(*args, **kwargs):
        raise kernel.S2HostKernelError("PR_GET_DUMPABLE observed 1")

    monkeypatch.setattr(kernel, "enforce_process_hardening", _refuse)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not execute"))
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    with pytest.raises(kernel.S2HostKernelError):
        host.run(list(allowed))


# derived constants are pinned against their owners (no re-invented host facts)
def test_target_hostnames_are_pinned_to_the_s1_target_host():
    import agent_governance_target_host_probe as th

    assert kernel.TARGET_HOSTNAMES == frozenset({th.EXPECTED_TARGET_HOST_DEFAULT})


def test_canonical_roots_and_unit_dir_match_the_s2_4_constants():
    import agent_governance_s2_4_apply as s2_4_apply

    assert set(kernel.CANONICAL_INSTALL_ROOTS) == set(s2_4_apply.INSTALL_ROOTS.values())
    assert kernel.SYSTEMD_SYSTEM_UNIT_DIR == str(
        Path(s2_4_apply.UNIT_FRAGMENT_PATH).parent
    )


def test_kernel_import_closure_excludes_every_applier_module():
    argv = [
        sys.executable, "-c",
        "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r); "
        "import agent_governance_s2_host_kernel; "
        "print('\\n'.join(sorted(sys.modules)))" % (str(ML_ROOT), str(HELPERS)),
    ]
    loaded = set(
        subprocess.run(argv, capture_output=True, text=True, check=True).stdout.split()
    )
    assert not (loaded & APPLIER_MODULES), sorted(loaded & APPLIER_MODULES)


def test_kernel_abi_projection_is_code_owned():
    projection = kernel.kernel_abi_projection()
    assert projection["sessions"] == sorted(kernel.SESSION_ARGV_ALLOWLISTS)
    assert projection["mutating_sessions"] == [kernel.SESSION_S2_1_QUIESCE_FENCE]
    assert projection["production_grade_target_classes"] == sorted(
        {kernel.TARGET_CLASS_PRODUCTION, kernel.TARGET_CLASS_UNKNOWN}
    )
    assert projection["rehearsal_only_target_classes"] == [
        kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE
    ]
    assert kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE not in projection[
        "derivable_target_classes"
    ]
    assert projection["production_entry_intent_target_class"] == (
        kernel.INTENT_TARGET_CLASS_PRODUCTION
    )
    assert projection["egress_secret_scanner"].endswith(
        "scan_serializable_surface_for_secrets"
    )
    assert projection["egress_secret_scanner_rules"].endswith("SECRET_VALUE_PATTERNS")


_SECRET_SHAPED_VALUES = (
    "PG" + "PASSWORD" + "=" + "s3cr3t-not-real",
    "Authorization: " + "Bearer " + "abcdef0123456789",
    "htt" + "ps://reader" + ":" + "s3cr3t-not-real" + "@trade-core/db",
)


def _clean_observation() -> dict:
    """一份形狀與真 observation 相同、但不含任何 secret 形的 payload。"""

    return {
        "schema_version": "s2_host_observation_v1",
        "observed_at": "2026-07-29T00:00:00Z",
        "target_class_view": kernel.derive_host_target_class(),
        "request_digest": "sha256:" + "0" * 64,
        "faces": {
            "unit_state": {
                "unit": "arcane-equilibrium-aiml-engine-scanner.service",
                "properties": {
                    "ActiveState": "active",
                    "Environment": "ALR_SOURCE_HEAD=" + "0" * 40,
                    "FragmentPath": "/etc/systemd/system/x.service",
                },
            },
            "file_identity": {"unit_fragment": {"present": False, "mode": "0644"}},
        },
        "self_digest": "sha256:" + "1" * 64,
    }


def test_a_clean_observation_shaped_payload_is_not_flagged():
    assert kernel.scan_serializable_surface_for_secrets(_clean_observation()) == []


@pytest.mark.parametrize("value", _SECRET_SHAPED_VALUES)
def test_every_central_secret_rule_blocks_an_observation(value):
    payload = _clean_observation()
    payload["faces"]["unit_state"]["properties"]["Environment"] = value
    reasons = kernel.scan_serializable_surface_for_secrets(payload)
    assert reasons, value
    assert "faces.unit_state.properties.Environment" in reasons[0]
    assert value not in reasons[0]


def test_the_key_value_adjacency_form_is_caught_too():
    """``{"password": "..."}`` 這種「鍵值相鄰」形只有掃 canonical JSON bytes 才看得見。"""

    payload = _clean_observation()
    payload["faces"]["pg_acl"] = {"pass" + "word": "s3cr3t-not-real"}
    reasons = kernel.scan_serializable_surface_for_secrets(payload)
    assert reasons and "faces.pg_acl" in reasons[0]


def test_the_scanner_delegates_to_the_capture_v2_rules_not_a_second_set():
    import inspect

    from agent_governance_command_capture_v2 import SECRET_VALUE_PATTERNS

    source = inspect.getsource(kernel._carries_secret_shaped_value)
    assert "from agent_governance_command_capture_v2 import _redact_preview" in source
    assert "re.compile" not in source
    assert len(SECRET_VALUE_PATTERNS) == len(_SECRET_SHAPED_VALUES)


def test_the_non_http_uri_dsn_gap_is_pinned_as_an_honest_boundary():
    """釘住殘餘缺口:中央規則的 URL 形只涵蓋 ``http(s)`` scheme,不涵蓋 DB-scheme 的 URI 形。

    這條缺口**不在**本波收口:正確的修法是把該形併進
    ``agent_governance_command_capture_v2.SECRET_VALUE_PATTERNS``(那樣全 repo 的 governed capture
    preview 一起受惠),而在 runner 家族自造第二套判準正是本波刻意拒絕的事。repo 內另有一支涵蓋
    該形的 ``public_repo_security_gate.EMBEDDED_CREDENTIAL_DSN``,但那個模組 ``import subprocess``
    ⇒ 匯入它等於給 runner 家族重開一條完整 exec 路徑(E2 RES-5 收掉的那條縫),故不採用。S2.4
    實際使用的封閉 DSN 是 libpq 鍵值形,那一形**有**被擋(下面第二個斷言)。未來一旦中央規則加寬,
    本測試變紅並被看見。
    """

    uri_form = "postgre" + "sql://reader" + ":" + "s3cr3t-not-real" + "@trade-core/db"
    assert kernel.scan_serializable_surface_for_secrets({"faces": uri_form}) == []
    libpq_form = "host=127.0.0.1 " + "pass" + "word=" + "s3cr3t-not-real" + " dbname=x"
    assert kernel.scan_serializable_surface_for_secrets({"faces": libpq_form})


def test_an_unserializable_payload_is_scanned_rather_than_waved_through():
    class _Opaque:
        def __repr__(self) -> str:
            return _SECRET_SHAPED_VALUES[0]

    assert kernel.scan_serializable_surface_for_secrets({"faces": _Opaque()})
