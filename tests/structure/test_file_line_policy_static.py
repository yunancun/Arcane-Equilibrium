import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIVE_TEST_ROOTS = (
    ROOT / "tests",
    ROOT
    / "program_code/exchange_connectors/bybit_connector/control_api_v1/tests",
)
ACTIVE_POLICY_TEXT_ROOTS = (
    ROOT / ".agents/skills",
    ROOT / ".claude/skills",
    ROOT / "tests",
    ROOT / "rust/openclaw_engine/src",
    ROOT / "rust/openclaw_engine/tests",
    ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app",
    ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/tests",
    ROOT / "program_code/learning_engine",
    ROOT / "helper_scripts/db/passive_wait_healthcheck",
)
ACTIVE_POLICY_TEXT_FILES = (
    ROOT / "CLAUDE.md",
    ROOT / "helper_scripts/db/passive_wait_healthcheck.py",
)
ACTIVE_POLICY_TEXT_SUFFIXES = {".css", ".html", ".js", ".md", ".py", ".rs"}
CURRENT_FILE_LINE_LIMIT = 2_000

_NUMBERED_FILE_LIMIT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        # A number attached directly to a file-line policy phrase.
        r"(?P<limit>(?<![\w.])\d[\d_,]*(?![\w.]))[ \t]*[- ]?[ \t]*(?:\blines?\b|\bloc\b|行)"
        r"[ \t]*(?:hard|soft|review/split|governance|治理|硬|軟)?[ \t]*"
        r"(?:cap|limit|threshold|warning|budget|上限|門檻|警告線|規則|約定)",
        # A file-line policy phrase followed directly by its number.
        r"(?:file[- ]?size|\blines?\b|\bloc\b|行數|文件大小)[ \t]*"
        r"(?:hard|soft|review/split|governance|治理|硬|軟)?[ \t]*"
        r"(?:cap|limit|threshold|warning|budget|上限|門檻|警告線|規則|約定)"
        r"[ \t]*(?:=|:|為|of)?[ \t]*(?P<limit>(?<![\w.])\d[\d_,]*(?![\w.]))",
        # LOC context with an explicit cap assignment later on the same line.
        r"(?:\bloc\b|行數|文件大小)[^;\n]{0,80}"
        r"(?:cap|limit|threshold|warning|budget|上限|門檻|警告線|規則|約定)"
        r"[ \t]*(?:=|:|為|of)?[ \t]*(?P<limit>(?<![\w.])\d[\d_,]*(?![\w.]))",
        # An explicit comparator immediately before a file-line count.
        r"(?:<=|<|≤)[ \t]*(?P<limit>(?<![\w.])\d[\d_,]*(?![\w.]))[ \t]*(?:\blines?\b|\bloc\b|行)",
        # Natural-language upper bounds immediately before a file-line count.
        r"(?:under|below|within|less[ \t]+than|低於|少於|不超過|上限為)[ \t]*"
        r"(?P<limit>(?<![\w.])\d[\d_,]*(?![\w.]))[ \t]*[- ]?[ \t]*(?:\blines?\b|\bloc\b|行)",
        # A wrapped policy where the numeric line phrase ends one comment line.
        r"(?P<limit>(?<![\w.])\d[\d_,]*(?![\w.]))[ \t]*-[ \t]*\bline\b[ \t]*\n[ \t]*"
        r"(?:[/#!*]+[ \t]*)?(?:hard|soft|review/split|governance)[ \t]*"
        r"(?:cap|limit|threshold|warning|budget)",
        # Section-scoped file policy, including compact "§九 N hard cap" prose.
        r"§[七九][^;\n]{0,40}?(?P<limit>(?<![\w.])\d[\d_,]*(?![\w.]))[ \t]*"
        r"(?:-?[ \t]*(?:\blines?\b|\bloc\b|行))?[ \t]*"
        r"(?:hard|soft|review/split|governance|治理|硬|軟)?[ \t]*"
        r"(?:cap|limit|threshold|warning|budget|上限|門檻|警告線|規則|約定)",
        # Section-scoped policy with the number after the policy token.
        r"§[七九][^;\n]{0,40}?"
        r"(?:cap|limit|threshold|warning|budget|上限|門檻|警告線|規則|約定)"
        r"[ \t]*(?:=|:|為|of)?[ \t]*"
        r"(?P<limit>(?<![\w.])\d[\d_,]*(?![\w.]))"
        r"(?:[ \t]*(?:\blines?\b|\bloc\b|行))?",
    )
)


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


def _static_int(node: ast.AST, bindings: dict[str, int] | None = None) -> int | None:
    if isinstance(node, ast.Name) and bindings is not None:
        return bindings.get(node.id)
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _static_int(node.operand, bindings)
        if operand is None:
            return None
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp):
        left = _static_int(node.left, bindings)
        right = _static_int(node.right, bindings)
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
    components = {component for component in normalized.split("_") if component}
    if components & {"byte", "bytes", "diff", "log", "logs"}:
        return False
    if normalized.endswith(("linebyte", "linebytes")):
        return False
    has_measure = "line" in normalized or "loc" in normalized
    has_limit = any(
        token in normalized
        for token in ("max", "limit", "cap", "threshold")
    )
    return has_measure and has_limit


def _looks_like_line_count_name(name: str) -> bool:
    normalized = name.casefold().strip("_")
    if _looks_like_line_limit_name(normalized):
        return False
    return (
        normalized in {"loc", "lines", "line_count"}
        or "line_count" in normalized
        or normalized.endswith(("_lines", "_loc"))
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
        if function_name in {"lines", "splitlines"}:
            return True
        if _looks_like_line_count_name(function_name):
            return True
    return any(
        _is_line_count_expression(child, bound_names)
        for child in ast.iter_child_nodes(node)
    )


def _assignment_parts(
    node: ast.AST,
) -> tuple[list[ast.expr], ast.expr] | None:
    if isinstance(node, ast.Assign):
        return node.targets, node.value
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return [node.target], node.value
    return None


def _numeric_bindings(
    assignments: list[tuple[ast.AST, tuple[list[ast.expr], ast.expr]]],
) -> dict[str, int]:
    bindings: dict[str, int] = {}
    changed = True
    while changed:
        changed = False
        for _, (targets, value) in assignments:
            static_value = _static_int(value, bindings)
            if static_value is None:
                continue
            for target in targets:
                for name in _target_names(target):
                    if name not in bindings:
                        bindings[name] = static_value
                        changed = True
    return bindings


def _line_count_bindings(
    assignments: list[tuple[ast.AST, tuple[list[ast.expr], ast.expr]]],
) -> set[str]:
    bindings: set[str] = set()
    changed = True
    while changed:
        changed = False
        for _, (targets, value) in assignments:
            if not _is_line_count_expression(value, bindings):
                continue
            names = {
                name
                for target in targets
                for name in _target_names(target)
            }
            new_names = names - bindings
            if new_names:
                bindings.update(new_names)
                changed = True
    return bindings


def _line_gate_violations(source: str, path: Path) -> list[str]:
    tree = ast.parse(source, filename=str(path))
    assignments = [
        (node, parts)
        for node in ast.walk(tree)
        if (parts := _assignment_parts(node)) is not None
    ]
    numeric_bindings = _numeric_bindings(assignments)
    line_count_bindings = _line_count_bindings(assignments)
    violations: list[str] = []

    for node, (targets, value) in assignments:
        names = {
            name
            for target in targets
            for name in _target_names(target)
        }
        static_value = _static_int(value, numeric_bindings)
        if (
            static_value is not None
            and any(_looks_like_line_limit_name(name) for name in names)
            and static_value != CURRENT_FILE_LINE_LIMIT
        ):
            violations.append(f"{path}:{node.lineno}:line-limit assignment")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        for left, operator, right in zip(operands, node.ops, operands[1:]):
            left_is_count = _is_line_count_expression(left, line_count_bindings)
            right_is_count = _is_line_count_expression(right, line_count_bindings)
            left_limit = _static_int(left, numeric_bindings)
            right_limit = _static_int(right, numeric_bindings)

            valid_inclusive_gate = (
                left_is_count
                and isinstance(operator, ast.LtE)
                and right_limit == CURRENT_FILE_LINE_LIMIT
            ) or (
                right_is_count
                and isinstance(operator, ast.GtE)
                and left_limit == CURRENT_FILE_LINE_LIMIT
            )
            is_upper_gate = (
                left_is_count
                and right_limit is not None
                and isinstance(operator, (ast.Lt, ast.LtE))
            ) or (
                right_is_count
                and left_limit is not None
                and isinstance(operator, (ast.Gt, ast.GtE))
            )
            if is_upper_gate and not valid_inclusive_gate:
                violations.append(f"{path}:{node.lineno}:line-count comparison")
                break

    return violations


def _active_test_paths() -> list[Path]:
    return sorted(
        {
            path
            for root in ACTIVE_TEST_ROOTS
            for path in root.rglob("*.py")
            if "__pycache__" not in path.parts
        }
    )


def _active_policy_text_paths() -> list[Path]:
    return sorted(
        {
            *ACTIVE_POLICY_TEXT_FILES,
            *(
                path
                for root in ACTIVE_POLICY_TEXT_ROOTS
                for path in root.rglob("*")
                if path.is_file()
                and path.suffix.casefold() in ACTIVE_POLICY_TEXT_SUFFIXES
                and "__pycache__" not in path.parts
            ),
        }
    )


def _numbered_file_policy_violations(source: str, path: Path) -> list[str]:
    violations: list[str] = []
    seen: set[tuple[int, int]] = set()
    for pattern_index, pattern in enumerate(_NUMBERED_FILE_LIMIT_PATTERNS):
        for match in pattern.finditer(source):
            line_start = source.rfind("\n", 0, match.start()) + 1
            line_end = source.find("\n", match.end())
            if line_end < 0:
                line_end = len(source)
            line_text = source[line_start:line_end]
            if pattern_index in {3, 4} and not re.search(
                r"cap|limit|threshold|warning|budget|上限|門檻|警告|規則|約定|"
                r"§[七九]|claude|file[- ]?size|行數",
                line_text,
                re.IGNORECASE,
            ):
                continue
            limit = int(match.group("limit").replace(",", "").replace("_", ""))
            if limit >= CURRENT_FILE_LINE_LIMIT:
                continue
            line = source.count("\n", 0, match.start()) + 1
            key = (line, limit)
            if key not in seen:
                seen.add(key)
                violations.append(f"{path}:{line}:numbered file limit {limit}")
    return violations


def test_current_file_line_policy_is_exactly_2000() -> None:
    assert CURRENT_FILE_LINE_LIMIT == 2_000


def test_semantic_detector_rejects_every_noncanonical_file_line_gate() -> None:
    lower_limit = CURRENT_FILE_LINE_LIMIT // 5
    timeout = CURRENT_FILE_LINE_LIMIT - 800
    source = "\n".join(
        (
            f"MAX_LINES = {lower_limit}",
            f"assert len(path.read_text().splitlines()) <= {lower_limit}",
            f"MAX_FILE_LINES = {CURRENT_FILE_LINE_LIMIT}",
            "assert loc(path) < MAX_FILE_LINES",
            f"PORT = {lower_limit}",
            f"TIMEOUT_MS = {timeout}",
            f"CATALOG_LINE_LIMIT = {lower_limit}",
            f"MAX_LINE_BYTES = {lower_limit}",
            f"assert latency_ms <= {lower_limit}",
            "assert line_count > 50",
        )
    )

    assert _line_gate_violations(source, Path("fixture.py")) == [
        "fixture.py:1:line-limit assignment",
        "fixture.py:7:line-limit assignment",
        "fixture.py:2:line-count comparison",
        "fixture.py:4:line-count comparison",
    ]


def test_text_detector_rejects_section_scoped_lower_file_limits_only() -> None:
    lower_limit = CURRENT_FILE_LINE_LIMIT - 500
    timeout_ms = CURRENT_FILE_LINE_LIMIT - 800
    source = "\n".join(
        (
            f"// §九 {lower_limit}-line hard cap",
            f"// §七 {lower_limit} 行硬上限",
            f"// keep file <= {lower_limit} lines under §九 policy",
            f"// §九 {lower_limit} hard cap",
            f"preview_text(limit={timeout_ms})",
            f"setTimeout(refresh, {timeout_ms})",
            f"MAX_LINE_BYTES = {lower_limit}",
            f"target implementation estimate: ~{lower_limit} LOC",
        )
    )

    assert _numbered_file_policy_violations(source, Path("fixture.rs")) == [
        f"fixture.rs:1:numbered file limit {lower_limit}",
        f"fixture.rs:2:numbered file limit {lower_limit}",
        f"fixture.rs:3:numbered file limit {lower_limit}",
        f"fixture.rs:4:numbered file limit {lower_limit}",
    ]


def test_all_active_python_tests_use_the_single_file_line_policy() -> None:
    violations = [
        violation
        for path in _active_test_paths()
        for violation in _line_gate_violations(
            path.read_text(encoding="utf-8"),
            path.relative_to(ROOT),
        )
    ]

    assert not violations, (
        "active tests must use one inclusive source-file line ceiling of "
        f"{CURRENT_FILE_LINE_LIMIT}: {violations}"
    )


def test_active_source_and_test_text_does_not_advertise_lower_file_limits() -> None:
    violations = [
        violation
        for path in _active_policy_text_paths()
        for violation in _numbered_file_policy_violations(
            path.read_text(encoding="utf-8"),
            path.relative_to(ROOT),
        )
    ]

    assert not violations, (
        "active source and test text must not advertise a numbered file-size "
        f"policy below {CURRENT_FILE_LINE_LIMIT}: {violations}"
    )
