import ast
from pathlib import Path


STRUCTURE_TESTS = Path(__file__).resolve().parent
CURRENT_FILE_LINE_LIMIT = 2_000
LEGACY_GATE_VALUE = 8 * 100


def _target_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.List, ast.Tuple)):
        return {
            name
            for element in target.elts
            for name in _target_names(element)
        }
    return set()


def _static_int(node: ast.AST) -> int | None:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _static_int(node.operand)
        if operand is None:
            return None
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp):
        left = _static_int(node.left)
        right = _static_int(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.FloorDiv) and right != 0:
            return left // right
    return None


def _looks_like_line_limit_name(name: str) -> bool:
    normalized = name.casefold().strip("_")
    has_measure = "line" in normalized or "loc" in normalized
    has_limit = any(
        token in normalized
        for token in ("max", "limit", "cap", "threshold")
    )
    return has_measure and has_limit


def _looks_like_line_count_name(name: str) -> bool:
    normalized = name.casefold().strip("_")
    return (
        normalized in {"loc", "lines", "line_count"}
        or "line_count" in normalized
        or normalized.endswith("_loc")
        or normalized.startswith("loc_")
    )


def _call_name(function: ast.expr) -> str:
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return ""


def _is_line_count_expression(node: ast.AST, bound_names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in bound_names or _looks_like_line_count_name(node.id)
    if isinstance(node, ast.Call):
        function_name = _call_name(node.func).casefold().strip("_")
        if function_name == "splitlines" or _looks_like_line_count_name(function_name):
            return True
    return any(
        _is_line_count_expression(child, bound_names)
        for child in ast.iter_child_nodes(node)
    )


def _is_legacy_value(node: ast.AST, bound_names: set[str]) -> bool:
    if isinstance(node, ast.Name) and node.id in bound_names:
        return True
    return _static_int(node) == LEGACY_GATE_VALUE


def _assignment_parts(
    node: ast.AST,
) -> tuple[list[ast.expr], ast.expr] | None:
    if isinstance(node, ast.Assign):
        return node.targets, node.value
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return [node.target], node.value
    return None


def _legacy_line_gate_violations(source: str, path: Path) -> list[str]:
    tree = ast.parse(source, filename=str(path))
    assignments = [
        (node, parts)
        for node in ast.walk(tree)
        if (parts := _assignment_parts(node)) is not None
    ]
    legacy_value_names: set[str] = set()
    line_count_names: set[str] = set()

    for _, (targets, value) in assignments:
        names = {name for target in targets for name in _target_names(target)}
        if _static_int(value) == LEGACY_GATE_VALUE:
            legacy_value_names.update(names)

    changed = True
    while changed:
        changed = False
        for _, (targets, value) in assignments:
            names = {name for target in targets for name in _target_names(target)}
            if _is_line_count_expression(value, line_count_names):
                new_names = names - line_count_names
                if new_names:
                    line_count_names.update(new_names)
                    changed = True

    violations: list[str] = []
    for node, (targets, value) in assignments:
        names = {name for target in targets for name in _target_names(target)}
        if (
            any(_looks_like_line_limit_name(name) for name in names)
            and _is_legacy_value(value, legacy_value_names)
        ):
            violations.append(f"{path.name}:{node.lineno}:line-limit assignment")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        for left, right in zip(operands, operands[1:]):
            if (
                _is_legacy_value(left, legacy_value_names)
                and _is_line_count_expression(right, line_count_names)
            ) or (
                _is_line_count_expression(left, line_count_names)
                and _is_legacy_value(right, legacy_value_names)
            ):
                violations.append(f"{path.name}:{node.lineno}:line-count comparison")
                break

    return violations


def test_current_file_line_policy_is_exactly_2000() -> None:
    assert CURRENT_FILE_LINE_LIMIT == 2_000


def test_semantic_detector_rejects_only_legacy_file_line_gates() -> None:
    legacy = str(LEGACY_GATE_VALUE)
    source = "\n".join(
        (
            f"MAX_LINES = {legacy}",
            f"assert len(path.read_text().splitlines()) <= {legacy}",
            f"PORT = {legacy}",
            f"TIMEOUT_MS = {legacy}",
            f"assert latency_ms <= {legacy}",
            f"data = [{legacy}]",
        )
    )

    assert _legacy_line_gate_violations(source, Path("fixture.py")) == [
        "fixture.py:1:line-limit assignment",
        "fixture.py:2:line-count comparison",
    ]


def test_active_structure_tests_do_not_encode_legacy_file_line_gate() -> None:
    violations = [
        violation
        for path in sorted(STRUCTURE_TESTS.glob("test_*.py"))
        for violation in _legacy_line_gate_violations(
            path.read_text(encoding="utf-8"),
            path,
        )
    ]

    assert not violations, (
        "active structure tests must encode the current file-line policy, not "
        f"the legacy gate: {violations}"
    )
