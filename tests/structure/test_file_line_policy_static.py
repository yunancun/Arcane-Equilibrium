import ast
from pathlib import Path

from tests.structure.file_line_policy import MAX_FILE_LINES


STRUCTURE_TESTS = Path(__file__).resolve().parent
LEGACY_FILE_LINE_LIMIT = 8 * 100


def test_canonical_file_line_policy_is_2000() -> None:
    assert MAX_FILE_LINES == 2_000


def test_structure_tests_do_not_reintroduce_legacy_line_limit_literal() -> None:
    violations: list[str] = []

    for path in sorted(STRUCTURE_TESTS.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, int)
                and not isinstance(node.value, bool)
                and node.value == LEGACY_FILE_LINE_LIMIT
            ):
                violations.append(f"{path.name}:{node.lineno}")

    assert not violations, (
        "active structure tests must import MAX_FILE_LINES instead of restoring "
        f"the legacy line-limit literal: {violations}"
    )
