"""Static source contract for V159 durable challenger fit attestation.

V159 is source-only until a separately governed disposable-PostgreSQL/apply
gate.  This suite inspects repository bytes; it never connects to PostgreSQL,
runs a fit, or reads model artifacts.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import re
from collections.abc import Callable
from pathlib import Path

import pytest


SRV_ROOT = Path(__file__).resolve().parents[2]
V159 = SRV_ROOT / "sql/migrations/V159__alr_durable_fit_attestation.sql"
V158 = SRV_ROOT / "sql/migrations/V158__alr_qualified_challenger_training.sql"
FUNCTIONAL_PROBE = (
    SRV_ROOT
    / "program_code/ml_training/tests/integration/"
    "alr_durable_fit_attestation_isolated_pg.py"
)
CONCURRENCY_PROBE = (
    SRV_ROOT
    / "program_code/ml_training/tests/integration/"
    "alr_durable_fit_attestation_concurrency_isolated_pg.py"
)
SCHEMA_CONTRACT = SRV_ROOT / "rust/openclaw_engine/tests/schema_contract_test.rs"
CI_WORKFLOW = SRV_ROOT / ".github/workflows/ci.yml"

_TOP_LEVEL_CASE_GUARDS = (
    (
        "IF v_count<>(CASE WHEN p_mode='legacy' THEN 13 ELSE 28 END) THEN",
        "IF v_count<>CASE WHEN p_mode='legacy' THEN 13 ELSE 28 END THEN",
    ),
    (
        "IF v_count<>(CASE WHEN p_mode='legacy' THEN 7 ELSE 11 END) THEN",
        "IF v_count<>CASE WHEN p_mode='legacy' THEN 7 ELSE 11 END THEN",
    ),
    (
        "IF v_count<>(CASE WHEN p_mode='legacy' THEN 6 ELSE 11 END) THEN",
        "IF v_count<>CASE WHEN p_mode='legacy' THEN 6 ELSE 11 END THEN",
    ),
    (
        ")<>(CASE WHEN v_spec.caller_kind IN('trainer','attestor_caller') OR "
        "(v_spec.caller_kind='legacy_trainer' AND p_mode='legacy') THEN 2 ELSE 1 END) THEN",
        ")<>CASE WHEN v_spec.caller_kind IN('trainer','attestor_caller') OR "
        "(v_spec.caller_kind='legacy_trainer' AND p_mode='legacy') THEN 2 ELSE 1 END THEN",
    ),
    (
        "IF v_writer_owned<>(CASE p_mode WHEN 'legacy' THEN 6 ELSE 9 END) OR "
        "v_attestor_owned<>(CASE p_mode WHEN 'legacy' THEN 0 ELSE 2 END) OR",
        "IF v_writer_owned<>CASE p_mode WHEN 'legacy' THEN 6 ELSE 9 END OR "
        "v_attestor_owned<>CASE p_mode WHEN 'legacy' THEN 0 ELSE 2 END OR",
    ),
    (
        ")<>(CASE WHEN v_spec.writer_insert THEN 2 WHEN v_spec.writer_select THEN 1 ELSE 0 END) OR "
        "(SELECT count(*) FROM pg_class",
        ")<>CASE WHEN v_spec.writer_insert THEN 2 WHEN v_spec.writer_select THEN 1 ELSE 0 END OR "
        "(SELECT count(*) FROM pg_class",
    ),
    (
        ")<>(CASE WHEN v_spec.attestor_insert THEN 2 WHEN v_spec.attestor_select THEN 1 ELSE 0 END) THEN",
        ")<>CASE WHEN v_spec.attestor_insert THEN 2 WHEN v_spec.attestor_select THEN 1 ELSE 0 END THEN",
    ),
)


def _sql() -> str:
    assert V159.exists(), f"V159 migration is missing: {V159}"
    return V159.read_text(encoding="utf-8")


def _assert_attestation_column_aggregate_uses_implicit_single_group(
    sql: str,
) -> None:
    start = sql.index(
        "WITH expected(attnum, attname, data_type, not_null, has_default) AS ("
    )
    end = sql.index(") OR NOT EXISTS (", start)
    aggregate = sql[start:end]
    assert "GROUP BY TRUE" not in aggregate
    assert "GROUP BY FALSE" not in aggregate
    assert "GROUP BY" not in aggregate
    assert "FULL JOIN actual AS a USING (attnum)" in aggregate
    assert aggregate.count("HAVING count(*)=26") == 1
    for exactness in (
        "bool_and(e.attname IS NOT DISTINCT FROM a.attname)",
        "bool_and(e.data_type IS NOT DISTINCT FROM a.data_type)",
        "bool_and(e.not_null IS NOT DISTINCT FROM a.not_null)",
        "bool_and(e.has_default IS NOT DISTINCT FROM a.has_default)",
    ):
        assert aggregate.count(exactness) == 1


def test_v159_attestation_column_aggregate_has_no_constant_group_by() -> None:
    _assert_attestation_column_aggregate_uses_implicit_single_group(_sql())


@pytest.mark.parametrize("constant", ("TRUE", "FALSE"))
def test_v159_constant_group_by_mutations_are_rejected(constant: str) -> None:
    sql = _sql()
    assert sql.count("HAVING count(*)=26") == 1
    weakened = sql.replace(
        "HAVING count(*)=26",
        f"GROUP BY {constant}\n            HAVING count(*)=26",
        1,
    )
    with pytest.raises(AssertionError):
        _assert_attestation_column_aggregate_uses_implicit_single_group(
            weakened
        )


_LEGACY_RESULT_FUNCTIONS = (
    "persist_alr_challenger_training_result_v1",
    "read_alr_challenger_training_result_v1",
)
_LEGACY_QUOTED_IDENTIFIERS = frozenset(("learning", *_LEGACY_RESULT_FUNCTIONS))
_LEGACY_CLOSURE_START = (
    "-- All V158 result overloads were inventoried in Guard A.  Their first and\n"
    "-- only executable action is now an unconditional hard failure.\n"
)
_LEGACY_CLOSURE_END = (
    "\nALTER FUNCTION learning.persist_alr_challenger_fit_attestation_v1"
)


def _is_pg_identifier_start(char: str) -> bool:
    return (
        char == "_"
        or "A" <= char <= "Z"
        or "a" <= char <= "z"
        or not char.isascii()
    )


def _is_pg_identifier_continuation(char: str) -> bool:
    return (
        _is_pg_identifier_start(char)
        or "0" <= char <= "9"
        or char == "$"
    )


def _is_pg_dollar_quote_tag(tag: str) -> bool:
    return not tag or (
        _is_pg_identifier_start(tag[0])
        and all(
            _is_pg_identifier_continuation(char) and char != "$"
            for char in tag[1:]
        )
    )


def _pg_top_level_code(sql: str) -> str:
    """Mask quoted data/comments while preserving top-level code positions."""
    masked: list[str] = []
    cursor = 0
    previous_single_end: int | None = None
    previous_single_uses_backslash = False

    def mask(fragment: str) -> str:
        return "".join("\n" if char == "\n" else " " for char in fragment)

    while cursor < len(sql):
        start = cursor
        if sql.startswith("--", cursor):
            newline = sql.find("\n", cursor + 2)
            cursor = len(sql) if newline < 0 else newline
            masked.append(mask(sql[start:cursor]))
            continue
        if sql.startswith("/*", cursor):
            depth = 1
            cursor += 2
            while cursor < len(sql) and depth:
                if sql.startswith("/*", cursor):
                    depth += 1
                    cursor += 2
                elif sql.startswith("*/", cursor):
                    depth -= 1
                    cursor += 2
                else:
                    cursor += 1
            masked.append(mask(sql[start:cursor]))
            continue
        if sql[cursor] == "'":
            explicit_escape = (
                cursor > 0
                and sql[cursor - 1] in {"E", "e"}
                and (
                    cursor < 2
                    or not _is_pg_identifier_continuation(sql[cursor - 2])
                )
            )
            continuation_gap = (
                sql[previous_single_end:cursor]
                if previous_single_end is not None
                else ""
            )
            continued_escape = (
                previous_single_end is not None
                and "\n" in continuation_gap
                and continuation_gap.isspace()
                and previous_single_uses_backslash
            )
            uses_backslash = explicit_escape or continued_escape
            cursor += 1
            while cursor < len(sql):
                if uses_backslash and sql[cursor] == "\\":
                    cursor = min(len(sql), cursor + 2)
                    continue
                if sql[cursor] != "'":
                    cursor += 1
                    continue
                if cursor + 1 < len(sql) and sql[cursor + 1] == "'":
                    cursor += 2
                    continue
                cursor += 1
                break
            previous_single_end = cursor
            previous_single_uses_backslash = uses_backslash
            masked.append(mask(sql[start:cursor]))
            continue
        if sql[cursor] == '"':
            unicode_quoted = (
                cursor >= 2
                and sql[cursor - 2 : cursor].casefold() == "u&"
                and (
                    cursor < 3
                    or not _is_pg_identifier_continuation(sql[cursor - 3])
                )
            )
            cursor += 1
            while cursor < len(sql):
                if sql[cursor] != '"':
                    cursor += 1
                    continue
                if cursor + 1 < len(sql) and sql[cursor + 1] == '"':
                    cursor += 2
                    continue
                cursor += 1
                break
            fragment = sql[start:cursor]
            content = (
                fragment[1:-1].replace('""', '"')
                if fragment.endswith('"')
                else None
            )
            masked.append(
                fragment
                if unicode_quoted or content in _LEGACY_QUOTED_IDENTIFIERS
                else mask(fragment)
            )
            continue
        if sql[cursor] == "$":
            delimiter_end = sql.find("$", cursor + 1)
            tag = sql[cursor + 1 : delimiter_end] if delimiter_end >= 0 else None
            opening_boundary = (
                cursor == 0
                or not _is_pg_identifier_continuation(sql[cursor - 1])
            )
            if (
                opening_boundary
                and tag is not None
                and _is_pg_dollar_quote_tag(tag)
            ):
                marker = sql[cursor : delimiter_end + 1]
                cursor += len(marker)
                closing = sql.find(marker, cursor)
                cursor = len(sql) if closing < 0 else closing + len(marker)
                masked.append(mask(sql[start:cursor]))
                continue
        masked.append(sql[cursor])
        cursor += 1
    return "".join(masked)


def _legacy_function_target_pattern(function_name: str) -> re.Pattern[str]:
    schema = r'(?:"learning"|learning)'
    function = rf'(?:"{re.escape(function_name)}"|{re.escape(function_name)})'
    target = rf"(?:{schema}\s*[.]\s*)?{function}"
    return re.compile(rf"{target}\s*(?=[(])", re.IGNORECASE)


def _legacy_function_ddl_pattern(function_name: str) -> re.Pattern[str]:
    target = _legacy_function_target_pattern(function_name).pattern
    return re.compile(
        rf"\b(?P<verb>CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION|"
        rf"DROP\s+(?:FUNCTION|ROUTINE)(?:\s+IF\s+EXISTS)?|"
        rf"ALTER\s+(?:FUNCTION|ROUTINE))\s+{target}\s*(?=[(])",
        re.IGNORECASE,
    )


def _function_inputs_source(sql: str, function_name: str) -> str:
    prefix = f"CREATE OR REPLACE FUNCTION learning.{function_name}("
    assert sql.count(prefix) == 1, function_name
    start = sql.index(prefix) + len(prefix)
    end = sql.index(") RETURNS JSONB", start)
    return sql[start:end]


def _expected_legacy_closure_block(v158_sql: str) -> str:
    writer_inputs = _function_inputs_source(
        v158_sql, "persist_alr_challenger_training_result_v1"
    )
    reader_inputs = _function_inputs_source(
        v158_sql, "read_alr_challenger_training_result_v1"
    )
    return (
        _LEGACY_CLOSURE_START
        + "CREATE OR REPLACE FUNCTION "
        "learning.persist_alr_challenger_training_result_v1("
        + writer_inputs
        + ") RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER "
        "SET search_path=pg_catalog,pg_temp AS $v159_closed_writer$ "
        "BEGIN RAISE EXCEPTION 'V159 closed V158 result writer: "
        "durable fit attestation v2 required'; END $v159_closed_writer$;\n"
        "CREATE OR REPLACE FUNCTION "
        "learning.read_alr_challenger_training_result_v1("
        + reader_inputs
        + ") RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER "
        "SET search_path=pg_catalog,pg_temp AS $v159_closed_reader$ "
        "BEGIN RAISE EXCEPTION 'V159 closed V158 result reader: "
        "durable fit attestation v2 required'; END $v159_closed_reader$;\n"
    )


def _legacy_closure_block(sql: str) -> tuple[int, int, str]:
    assert sql.count(_LEGACY_CLOSURE_START) == 1
    assert sql.count(_LEGACY_CLOSURE_END) == 1
    start = sql.index(_LEGACY_CLOSURE_START)
    end = sql.index(_LEGACY_CLOSURE_END, start)
    return start, end, sql[start:end]


def _assert_legacy_v1_closures_preserve_catalog_inputs(
    v159_sql: str,
    v158_sql: str,
) -> None:
    executable_sql = _pg_top_level_code(v159_sql)
    block_start, block_end, actual = _legacy_closure_block(v159_sql)
    assert re.search(r"\bU&\"", executable_sql, re.IGNORECASE) is None
    drop_statements = tuple(
        re.finditer(
            r"\bDROP\s+(?:FUNCTION|ROUTINE)(?:\s+IF\s+EXISTS)?"
            r"(?P<targets>[^;]*);",
            executable_sql,
            re.IGNORECASE,
        )
    )
    for function_name in _LEGACY_RESULT_FUNCTIONS:
        declarations = tuple(
            _legacy_function_ddl_pattern(function_name).finditer(executable_sql)
        )
        assert len(declarations) == 1, function_name
        assert re.fullmatch(
            r"CREATE\s+OR\s+REPLACE\s+FUNCTION",
            declarations[0].group("verb"),
            re.IGNORECASE,
        )
        prefix = f"CREATE OR REPLACE FUNCTION learning.{function_name}("
        expected_start = v159_sql.index(prefix, block_start, block_end)
        expected_end = expected_start + len(prefix) - 1
        assert declarations[0].span() == (expected_start, expected_end)
        target = _legacy_function_target_pattern(function_name)
        assert not any(
            target.search(statement.group("targets"))
            for statement in drop_statements
        )
    assert actual == _expected_legacy_closure_block(v158_sql)


def test_v159_legacy_v1_closures_preserve_catalog_input_names() -> None:
    _assert_legacy_v1_closures_preserve_catalog_inputs(
        _sql(), V158.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    "function_name,parameter_name",
    (
        ("persist_alr_challenger_training_result_v1", "p_training_run_hash"),
        ("read_alr_challenger_training_result_v1", "p_training_key_hash"),
    ),
)
@pytest.mark.parametrize("mutation", ("rename", "omit"))
def test_v159_legacy_v1_closure_parameter_name_mutations_are_rejected(
    function_name: str,
    parameter_name: str,
    mutation: str,
) -> None:
    sql = _sql()
    start, end, block = _legacy_closure_block(sql)
    assert function_name in block and parameter_name in block
    replacement = f"{parameter_name}_drift" if mutation == "rename" else ""
    weakened = (
        sql[:start]
        + block.replace(parameter_name, replacement, 1)
        + sql[end:]
    )
    with pytest.raises(AssertionError):
        _assert_legacy_v1_closures_preserve_catalog_inputs(
            weakened, V158.read_text(encoding="utf-8")
        )


@pytest.mark.parametrize(
    "wrap",
    (
        lambda block: f"/* {block} */",
        lambda block: f"$é$ {block} $é$",
        lambda block: f"E'prefix\\' {block}'",
    ),
)
def test_v159_legacy_v1_closure_nonexecuting_decoys_are_rejected(
    wrap: Callable[[str], str],
) -> None:
    sql = _sql()
    start, end, block = _legacy_closure_block(sql)
    weakened = sql[:start] + wrap(block) + sql[end:]
    with pytest.raises(AssertionError):
        _assert_legacy_v1_closures_preserve_catalog_inputs(
            weakened, V158.read_text(encoding="utf-8")
        )


def test_v159_legacy_v1_closure_straddling_comment_is_rejected() -> None:
    sql = _sql()
    start, end, _block = _legacy_closure_block(sql)
    alter_end = sql.index(";", end) + 1
    weakened = (
        sql[:start]
        + "/*\n"
        + sql[start:alter_end]
        + "\n*/"
        + sql[alter_end:]
    )
    with pytest.raises(AssertionError):
        _assert_legacy_v1_closures_preserve_catalog_inputs(
            weakened, V158.read_text(encoding="utf-8")
        )


def test_v159_legacy_v1_closure_composed_mask_and_reopen_is_rejected() -> None:
    sql = _sql()
    start, end, _block = _legacy_closure_block(sql)
    alter_end = sql.index(";", end) + 1
    reopened = ""
    for function_name in _LEGACY_RESULT_FUNCTIONS:
        inputs = _function_inputs_source(
            V158.read_text(encoding="utf-8"), function_name
        )
        reopened += (
            f"\nCREATE OR REPLACE FUNCTION learning.{function_name}("
            + inputs
            + ") RETURNS JSONB LANGUAGE sql AS 'SELECT ''{}''::JSONB';\n"
        )
    commit = sql.rindex("\nCOMMIT;")
    weakened = (
        sql[:start]
        + "/*\n"
        + sql[start:alter_end]
        + "\n*/"
        + sql[alter_end:commit]
        + reopened
        + sql[commit:]
    )
    with pytest.raises(AssertionError):
        _assert_legacy_v1_closures_preserve_catalog_inputs(
            weakened, V158.read_text(encoding="utf-8")
        )


@pytest.mark.parametrize(
    "opening,closing",
    (
        ("SELECT $outer$\n", "\n$outer$;"),
        ('SELECT 1 AS "', '";'),
    ),
)
def test_v159_legacy_v1_closure_straddling_quote_is_rejected(
    opening: str,
    closing: str,
) -> None:
    sql = _sql()
    start, end, _block = _legacy_closure_block(sql)
    alter_end = sql.index(";", end) + 1
    weakened = (
        sql[:start]
        + opening
        + sql[start:alter_end]
        + closing
        + sql[alter_end:]
    )
    with pytest.raises(AssertionError):
        _assert_legacy_v1_closures_preserve_catalog_inputs(
            weakened, V158.read_text(encoding="utf-8")
        )


@pytest.mark.parametrize("function_name", _LEGACY_RESULT_FUNCTIONS)
@pytest.mark.parametrize(
    "target_format",
    (
        "learning.{function_name}",
        '"learning"."{function_name}"',
        'U&"learning".U&"{function_name}"',
        "unicode_escaped",
    ),
)
@pytest.mark.parametrize("leading", ("", "\nSELECT 'x\\';\n"))
def test_v159_legacy_v1_closure_later_reopen_is_rejected(
    function_name: str,
    target_format: str,
    leading: str,
) -> None:
    sql = _sql()
    inputs = _function_inputs_source(
        V158.read_text(encoding="utf-8"), function_name
    )
    if target_format == "unicode_escaped":
        first = f"{ord(function_name[0]):04X}"
        escaped_name = f"\\{first}{function_name[1:]}"
        target = f'U&"le\\0061rning".U&"{escaped_name}"'
    else:
        target = target_format.format(function_name=function_name)
    reopened = (
        f"\nCREATE\nOR REPLACE\nFUNCTION {target}("
        + inputs
        + ") RETURNS JSONB LANGUAGE sql AS 'SELECT ''{}''::JSONB';\n"
    )
    commit = sql.rindex("\nCOMMIT;")
    weakened = sql[:commit] + leading + reopened + sql[commit:]
    with pytest.raises(AssertionError):
        _assert_legacy_v1_closures_preserve_catalog_inputs(
            weakened, V158.read_text(encoding="utf-8")
        )


@pytest.mark.parametrize("function_name", _LEGACY_RESULT_FUNCTIONS)
@pytest.mark.parametrize(
    "override",
    (
        "DROP FUNCTION IF EXISTS learning.{function_name}({types});",
        "DROP FUNCTION IF EXISTS public.unrelated(), learning.{function_name}({types});",
        "DROP ROUTINE IF EXISTS learning.{function_name}({types});",
        "ALTER FUNCTION learning.{function_name}({types}) SECURITY INVOKER;",
        "ALTER ROUTINE learning.{function_name}({types}) SECURITY INVOKER;",
    ),
)
def test_v159_legacy_v1_closure_drop_or_alter_is_rejected(
    function_name: str,
    override: str,
) -> None:
    sql = _sql()
    inputs = _function_inputs_source(
        V158.read_text(encoding="utf-8"), function_name
    )
    types = ",".join(
        argument.strip().rsplit(" ", 1)[1]
        for argument in inputs.split(",")
    )
    statement = override.format(function_name=function_name, types=types)
    commit = sql.rindex("\nCOMMIT;")
    weakened = sql[:commit] + "\n" + statement + sql[commit:]
    with pytest.raises(AssertionError):
        _assert_legacy_v1_closures_preserve_catalog_inputs(
            weakened, V158.read_text(encoding="utf-8")
        )


def _assert_top_level_case_guards_are_parenthesized(sql: str) -> None:
    for safe, unsafe in _TOP_LEVEL_CASE_GUARDS:
        assert safe in sql
        assert unsafe not in sql


def test_v159_plpgsql_if_guards_do_not_terminate_at_nested_case_then() -> None:
    _assert_top_level_case_guards_are_parenthesized(_sql())


def _assert_json_type_predicates_are_parseable(sql: str) -> None:
    assert "IS DISTINCT FROM 'string' IS FALSE" not in sql
    assert "IS DISTINCT FROM 'number' IS FALSE" not in sql
    assert sql.count("IS NOT DISTINCT FROM 'string'") == 74
    assert sql.count("IS NOT DISTINCT FROM 'number'") == 8


def test_v159_json_type_predicates_do_not_chain_is_operators() -> None:
    _assert_json_type_predicates_are_parseable(_sql())


_JSONB_DELETE_SELECTOR_COUNTS = (
    ("receipt_projection->'subject'", 2),
    ("receipt_projection->'claims'", 2),
    ("receipt_projection->'result_observation'", 2),
    ("receipt_projection#>'{result_observation,actual_inputs}'", 2),
    ("receipt_projection#>'{result_observation,model}'", 2),
    ("receipt_projection#>'{result_observation,artifacts}'", 2),
    ("receipt_projection#>'{result_observation,artifacts,q10}'", 2),
    ("receipt_projection#>'{result_observation,artifacts,q50}'", 2),
    ("receipt_projection#>'{result_observation,artifacts,q90}'", 2),
    ("receipt_projection->'authentication'", 2),
    ("v_obs->'actual_inputs'", 1),
    ("v_obs->'model'", 1),
    ("v_obs->'artifacts'", 1),
)


def _assert_jsonb_delete_selectors_are_parenthesized(sql: str) -> None:
    for selector, expected_count in _JSONB_DELETE_SELECTOR_COUNTS:
        safe = re.compile(
            rf"\({re.escape(selector)}\)\s*-\s*ARRAY\["
        )
        unsafe = re.compile(
            rf"(?<!\(){re.escape(selector)}\s*-\s*ARRAY\["
        )
        assert len(safe.findall(sql)) == expected_count, selector
        assert unsafe.search(sql) is None, selector


def test_v159_jsonb_delete_selector_precedence_is_explicit() -> None:
    _assert_jsonb_delete_selectors_are_parenthesized(_sql())


@pytest.mark.parametrize("selector,_expected_count", _JSONB_DELETE_SELECTOR_COUNTS)
def test_v159_unparenthesized_jsonb_delete_selector_mutations_are_rejected(
    selector: str, _expected_count: int
) -> None:
    sql = _sql()
    safe = re.compile(
        rf"\({re.escape(selector)}\)(?P<suffix>\s*-\s*ARRAY\[)"
    )
    match = safe.search(sql)
    assert match is not None
    weakened = (
        sql[: match.start()]
        + selector
        + match.group("suffix")
        + sql[match.end() :]
    )
    with pytest.raises(AssertionError):
        _assert_jsonb_delete_selectors_are_parenthesized(weakened)


@pytest.mark.parametrize(
    "safe,unsafe",
    (
        (
            "IS NOT DISTINCT FROM 'string'",
            "IS DISTINCT FROM 'string' IS FALSE",
        ),
        (
            "IS NOT DISTINCT FROM 'number'",
            "IS DISTINCT FROM 'number' IS FALSE",
        ),
    ),
)
def test_v159_chained_json_type_predicate_mutations_are_rejected(
    safe: str, unsafe: str
) -> None:
    sql = _sql()
    assert safe in sql
    with pytest.raises(AssertionError):
        _assert_json_type_predicates_are_parseable(
            sql.replace(safe, unsafe, 1)
        )


@pytest.mark.parametrize("safe,unsafe", _TOP_LEVEL_CASE_GUARDS)
def test_v159_unparenthesized_top_level_case_guard_mutations_are_rejected(
    safe: str, unsafe: str
) -> None:
    sql = _sql()
    assert safe in sql
    with pytest.raises(AssertionError):
        _assert_top_level_case_guards_are_parenthesized(
            sql.replace(safe, unsafe, 1)
        )


def _function_body(sql: str, tag: str) -> str:
    match = re.search(rf"AS \${tag}\$(.*?)\${tag}\$;", sql, re.DOTALL)
    assert match, tag
    return match.group(1)


def _replace_function_body_and_refresh_md5(
    sql: str, tag: str, mutated_body: str
) -> str:
    original_body = _function_body(sql, tag)
    assert mutated_body != original_body
    original_digest = hashlib.md5(original_body.encode()).hexdigest()
    assert sql.count(f"'{original_digest}'") == 3
    weakened = sql.replace(original_body, mutated_body, 1)
    mutated_digest = hashlib.md5(mutated_body.encode()).hexdigest()
    weakened = weakened.replace(
        f"'{original_digest}'", f"'{mutated_digest}'"
    )
    assert weakened.count(f"'{mutated_digest}'") == 3
    return weakened


def _mutate_function_body_and_refresh_md5(
    sql: str, tag: str, needle: str, replacement: str
) -> str:
    body = _function_body(sql, tag)
    assert needle in body
    mutated_body = body.replace(needle, replacement, 1)
    return _replace_function_body_and_refresh_md5(sql, tag, mutated_body)


def _control_token_inventory(body: str) -> dict[str, int]:
    return {
        keyword: len(re.findall(rf"\b{keyword}\b", body, re.IGNORECASE))
        for keyword in (
            "IF", "ELSIF", "FOR", "LOOP", "WHILE", "FOREACH", "EXIT",
            "CONTINUE", "CASE", "WHEN", "BEGIN", "EXCEPTION"
        )
    }


def _into_statement_count(body: str, target: str) -> int:
    return len(
        re.findall(
            rf"(?<!INSERT )\bINTO\b[^;]*\b{re.escape(target)}\b",
            body,
            re.IGNORECASE,
        )
    )


def _assert_core_binding_contract(sql: str) -> None:
    code = "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())
    table_start = code.index(
        "CREATE TABLE IF NOT EXISTS learning.alr_challenger_fit_attestations"
    )
    table_end = code.index(");", table_start)
    attestation_table = code[table_start:table_end]
    assert "SELECT " not in attestation_table
    assert re.search(
        r"UNIQUE\s*\(\s*durable_receipt_hash\s*,\s*training_key_hash\s*\)",
        attestation_table,
    )
    assert "alr_fit_attestations_lineage_uniq" in attestation_table
    assert "durable_attestation_hash, durable_receipt_hash" in attestation_table
    assert (
        "receipt_projection#>>'{result_observation,artifacts,q90,artifact_hash}'\n"
        "        ),'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT)="
        "ordered_artifact_set_hash"
    ) in attestation_table

    assert "alr_challenger_runs_payload_check" in code
    assert "alr_challenger_registry_payload_check" in code
    assert "alr_challenger_training_result_v2" in code
    assert "alr_challenger_registry_entry_v2" in code
    assert "legacy payload expression drift" in code
    assert "v2 payload expression drift" in code

    writer = _function_body(sql, "v159_result_writer")
    assert "pg_advisory_xact_lock" in writer
    assert "FOR UPDATE" not in writer
    assert writer.index("FROM learning.alr_challenger_fit_attestations") < (
        writer.index("pg_advisory_xact_lock")
    )
    assert writer.index("pg_advisory_xact_lock") < writer.index(
        "V159 stored attestation integrity mismatch"
    )

    attestation_writer = _function_body(sql, "v159_attestation_writer")
    assert "result_observation" in attestation_table
    assert attestation_table.count(
        "'authentication_status','subject','claims','result_observation',"
    ) == 2
    for field in (
        "source_head",
        "actual_inputs",
        "dataset_hash",
        "row_ids_hash",
        "split_hash",
        "code_manifest_hash",
        "training_config_hash",
        "feature_schema_hash",
        "label_schema_hash",
        "training_rows",
        "model",
        "model_schema_version",
        "metrics_hash",
        "resource_usage_hash",
        "fit_started_at",
        "fit_completed_at",
        "artifacts",
        "q10",
        "q50",
        "q90",
        "artifact_hash",
        "artifact_size_bytes",
    ):
        assert field in attestation_table, field
    assert code.count("jsonb_typeof(") >= 30
    assert code.count("IS NOT DISTINCT FROM 'string'") >= 20
    assert (
        "jsonb_typeof(receipt_projection->'schema_version') "
        "IS NOT DISTINCT FROM 'string'"
    ) in attestation_table
    assert "IS NOT DISTINCT FROM 'number'" in code
    assert attestation_table.count("~'^[1-9][0-9]{0,18}$'") == 3
    assert attestation_table.count("::NUMERIC BETWEEN 1 AND 9223372036854775807") == 3
    assert attestation_table.count("artifact_hash}'<>") == 3
    assert "actual_input fields/type mismatch" in attestation_writer
    assert "model observation fields/type mismatch" in attestation_writer
    assert "artifact observation fields/type mismatch" in attestation_writer
    assert "fit observation ordering mismatch" in attestation_writer
    assert "signed observation differs from qualified receipt" in attestation_writer
    assert "signed observation artifact set mismatch" in attestation_writer
    assert "receipt_projection->>'verified_at'=to_char(verified_at" in code
    assert "receipt_projection->>'expires_at'=to_char(expires_at" in code
    assert "isfinite(verified_at) AND isfinite(expires_at)" in code
    assert code.count("fit_completed_at <= attestation_verified_at") == 1

    duplicate_lookup = attestation_writer.index(
        "FROM learning.alr_challenger_fit_attestations"
    )
    now_capture = attestation_writer.index("v_now:=clock_timestamp()")
    expiry_rejection = attestation_writer.index("future-dated or expired")
    assert duplicate_lookup < now_capture < expiry_rejection
    assert "alr_fit_attestations_receipt_training_uniq" in code
    assert "attestation replay conflict" in attestation_writer

    for argument, projection_path in (
        ("p_source_head", "source_head"),
        ("p_actual_dataset_hash", "dataset_hash"),
        ("p_actual_row_ids_hash", "row_ids_hash"),
        ("p_actual_split_hash", "split_hash"),
        ("p_actual_code_manifest_hash", "code_manifest_hash"),
        ("p_actual_training_config_hash", "training_config_hash"),
        ("p_actual_feature_schema_hash", "feature_schema_hash"),
        ("p_actual_label_schema_hash", "label_schema_hash"),
        ("p_model_schema_version", "model_schema_version"),
        ("p_metrics_hash", "metrics_hash"),
        ("p_resource_usage_hash", "resource_usage_hash"),
        ("p_q10_hash", "q10"),
        ("p_q50_hash", "q50"),
        ("p_q90_hash", "q90"),
    ):
        assert argument in writer and projection_path in writer
    assert writer.count("IS DISTINCT FROM p_") >= 20
    assert "p_fit_completed_at>a.verified_at" in writer
    assert "p_fit_completed_at>v_bound" in writer


def test_v159_core_binding_viability_contract() -> None:
    _assert_core_binding_contract(_sql())


@pytest.mark.parametrize(
    "needle,replacement",
    (
        (
            "UNIQUE (durable_receipt_hash, training_key_hash)",
            "UNIQUE (durable_attestation_hash, durable_receipt_hash, training_key_hash)",
        ),
        ("pg_advisory_xact_lock", "removed_advisory_lock"),
        (
            "'authentication_status','subject','claims','result_observation',",
            "'authentication_status','subject','claims','removed_result_observation',",
        ),
        (
            "jsonb_typeof(receipt_projection->'schema_version') IS NOT DISTINCT FROM 'string'",
            "jsonb_typeof(receipt_projection->'schema_version') IS NOT DISTINCT FROM 'number'",
        ),
        (
            "actual_input fields/type mismatch",
            "removed actual-input type guard",
        ),
        (
            "),'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT)=ordered_artifact_set_hash",
            "),'UTF8'::NAME),'sha256'::TEXT),'hex'::TEXT)<>ordered_artifact_set_hash",
        ),
        (
            "fit_completed_at <= attestation_verified_at",
            "fit_completed_at > attestation_verified_at",
        ),
        (
            "isfinite(verified_at) AND isfinite(expires_at)",
            "verified_at IS NOT NULL AND expires_at IS NOT NULL",
        ),
    ),
)
def test_v159_core_binding_mutations_are_rejected(
    needle: str, replacement: str
) -> None:
    sql = _sql()
    assert needle in sql
    weakened = sql.replace(needle, replacement)
    with pytest.raises(AssertionError):
        _assert_core_binding_contract(weakened)


_COLLISION_UNIQUES = (
    ("alr_fit_attestations_structural_result_uniq", "structural_result_hash"),
    ("alr_fit_attestations_structural_fit_capture_uniq", "structural_fit_capture_hash"),
    ("alr_fit_attestations_structural_candidate_uniq", "structural_candidate_hash"),
    ("alr_fit_attestations_structural_training_run_uniq", "structural_training_run_hash"),
    ("alr_fit_attestations_structural_challenger_uniq", "structural_challenger_hash"),
    ("alr_fit_attestations_ordered_artifact_set_uniq", "ordered_artifact_set_hash"),
)

_ATTESTOR_LOCK_SELECT = (
    "SELECT DISTINCT hashtextextended('v159:artifact:'||artifact_hash,0) AS lock_key "
    "FROM unnest(ARRAY[v_q10,v_q50,v_q90]) artifact_hash ORDER BY lock_key"
)
_ATTESTOR_LOCK_BLOCK = (
    f"    FOR v_lock_key IN {_ATTESTOR_LOCK_SELECT} LOOP\n"
    "        PERFORM pg_advisory_xact_lock(v_lock_key);\n"
    "    END LOOP;"
)
_ATTESTOR_Q_ASSIGNMENTS = (
    "v_q10:=v_obs#>>'{artifacts,q10,artifact_hash}'; "
    "v_q50:=v_obs#>>'{artifacts,q50,artifact_hash}'; "
    "v_q90:=v_obs#>>'{artifacts,q90,artifact_hash}';"
)
_ATTESTOR_OVERLAP_EXISTING_ARRAY = (
    "ARRAY[e.receipt_projection#>>'{result_observation,artifacts,q10,artifact_hash}',"
    "e.receipt_projection#>>'{result_observation,artifacts,q50,artifact_hash}',"
    "e.receipt_projection#>>'{result_observation,artifacts,q90,artifact_hash}']::TEXT[]"
)
_ATTESTOR_LOOKUP_PREDICATE = (
    "durable_attestation_hash=v_hash OR external_receipt_digest=v_digest OR "
    "(durable_receipt_hash=p_durable_receipt_hash AND "
    "training_key_hash=p_training_key_hash) OR "
    "structural_result_hash=p_structural_result_hash OR "
    "structural_fit_capture_hash=p_structural_fit_capture_hash OR "
    "structural_candidate_hash=p_structural_candidate_hash OR "
    "structural_training_run_hash=p_structural_training_run_hash OR "
    "structural_challenger_hash=p_structural_challenger_hash OR "
    "ordered_artifact_set_hash=p_ordered_artifact_set_hash"
)
_ATTESTOR_OVERLAP_PREDICATE = (
    "e.durable_attestation_hash<>v_hash AND "
    f"{_ATTESTOR_OVERLAP_EXISTING_ARRAY} && "
    "ARRAY[v_q10,v_q50,v_q90]::TEXT[]"
)
_ATTESTOR_OVERLAP_STATEMENT = (
    "IF EXISTS(SELECT 1 FROM learning.alr_challenger_fit_attestations e WHERE "
    f"{_ATTESTOR_OVERLAP_PREDICATE}) THEN RAISE EXCEPTION "
    "'V159 attestation replay conflict'; END IF;"
)
_ATTESTOR_POST_INSERT_GUARD = (
    "IF v_inserted IS NOT NULL AND clock_timestamp()>=p_expires_at THEN "
    "RAISE EXCEPTION 'V159 attestation future-dated or expired'; END IF;"
)
_WRITER_LOCK_SELECT = (
    "SELECT DISTINCT hashtextextended(lock_material,0) AS lock_key FROM unnest(ARRAY["
    "'v159:attestation:'||p_durable_attestation_hash,"
    "'v159:run:'||a.structural_training_run_hash,"
    "'v159:challenger:'||a.structural_challenger_hash,"
    "'v159:artifact:'||p_q10_hash,'v159:artifact:'||p_q50_hash,"
    "'v159:artifact:'||p_q90_hash]::TEXT[]) lock_material ORDER BY lock_key"
)
_WRITER_LOCK_BLOCK = (
    f"    FOR v_lock_key IN {_WRITER_LOCK_SELECT} LOOP\n"
    "        PERFORM pg_advisory_xact_lock(v_lock_key);\n"
    "    END LOOP;"
)
_WRITER_ARTIFACT_COUNT = (
    "SELECT count(*) INTO v_arts FROM learning.alr_challenger_model_artifacts "
    "WHERE durable_attestation_hash=a.durable_attestation_hash OR "
    "training_run_hash=a.structural_training_run_hash OR "
    "artifact_hash IN(p_q10_hash,p_q50_hash,p_q90_hash);"
)
_WRITER_RUN_COUNT = (
    "SELECT count(*) INTO v_runs FROM learning.alr_challenger_training_runs "
    "WHERE durable_attestation_hash=a.durable_attestation_hash OR "
    "training_run_hash=a.structural_training_run_hash;"
)
_WRITER_REGISTRY_COUNT = (
    "SELECT count(*) INTO v_regs FROM learning.alr_challenger_registry WHERE "
    "durable_attestation_hash=a.durable_attestation_hash OR "
    "training_run_hash=a.structural_training_run_hash OR "
    "challenger_hash=a.structural_challenger_hash;"
)
_WRITER_COUNT_BLOCK = (
    f"    {_WRITER_RUN_COUNT}\n"
    f"    {_WRITER_ARTIFACT_COUNT}\n"
    f"    {_WRITER_REGISTRY_COUNT}"
)


def _assert_collision_hardening_contract(sql: str) -> None:
    assert "/*" not in sql and "*/" not in sql
    code = "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())
    table_start = code.index(
        "CREATE TABLE IF NOT EXISTS learning.alr_challenger_fit_attestations"
    )
    table_end = code.index("CREATE OR REPLACE FUNCTION", table_start)
    table = code[table_start:table_end]
    for name, column in _COLLISION_UNIQUES:
        assert re.search(
            rf"CONSTRAINT\s+{name}\s+UNIQUE\s*\(\s*{column}\s*\)\s+NOT DEFERRABLE",
            table,
        ), name
        assert (
            f"('final','{name}','learning.alr_challenger_fit_attestations',"
            f"'u','{column}',NULL,NULL)"
        ) in sql
        assert sql.count(f"('{name}','learning.alr_challenger_fit_attestations','u')") == 1
        assert sql.count(name) == 5

    attestor = _function_body(sql, "v159_attestation_writer")
    assert "--" not in attestor
    assert not re.search(r"\bIF\s+FALSE\b", attestor, re.IGNORECASE)
    assert not re.search(r"\bv_inserted\s*:=", attestor)
    assert _control_token_inventory(attestor) == {
        "IF": 32,
        "ELSIF": 0,
        "FOR": 1,
        "LOOP": 2,
        "WHILE": 0,
        "FOREACH": 0,
        "EXIT": 0,
        "CONTINUE": 0,
        "CASE": 1,
        "WHEN": 1,
        "BEGIN": 1,
        "EXCEPTION": 15,
    }
    assert _into_statement_count(attestor, "v_inserted") == 1
    for target in ("v_q10", "v_q50", "v_q90"):
        assert _into_statement_count(attestor, target) == 0
    lookup_matches = list(re.finditer(
        r"SELECT \* INTO v_row FROM learning\.alr_challenger_fit_attestations "
        r"WHERE (.*?) ORDER BY \(durable_attestation_hash=v_hash\)",
        attestor,
        re.DOTALL,
    ))
    assert len(lookup_matches) == 2
    lookups = [match.group(1) for match in lookup_matches]
    assert attestor.count(
        "ORDER BY (durable_attestation_hash=v_hash) DESC LIMIT 1"
    ) == 2
    for predicate in lookups:
        assert predicate.strip() == _ATTESTOR_LOOKUP_PREDICATE
        assert predicate.count(" OR ") == 8
        for column, argument in (
            ("structural_result_hash", "p_structural_result_hash"),
            ("structural_fit_capture_hash", "p_structural_fit_capture_hash"),
            ("structural_candidate_hash", "p_structural_candidate_hash"),
            ("structural_training_run_hash", "p_structural_training_run_hash"),
            ("structural_challenger_hash", "p_structural_challenger_hash"),
            ("ordered_artifact_set_hash", "p_ordered_artifact_set_hash"),
        ):
            assert f"{column}={argument}" in predicate
    assert "v_q10 TEXT; v_q50 TEXT; v_q90 TEXT" in attestor
    assert attestor.count(_ATTESTOR_Q_ASSIGNMENTS) == 1
    assert attestor.count("v_q10:=") == 1
    assert attestor.count("v_q50:=") == 1
    assert attestor.count("v_q90:=") == 1
    attestor_lock = re.search(r"FOR v_lock_key IN (.*?) LOOP", attestor, re.DOTALL)
    assert attestor_lock
    assert attestor_lock.group(1).strip() == _ATTESTOR_LOCK_SELECT
    assert attestor.count(_ATTESTOR_LOCK_BLOCK) == 1
    assert attestor.count("PERFORM pg_advisory_xact_lock(v_lock_key)") == 1
    assert "statement_timestamp()" not in attestor
    assert attestor.count("clock_timestamp()") == 2
    assert attestor.count("v_now:=") == 1
    assert attestor.count(
        "v_now:=clock_timestamp();\n"
        "    IF p_verified_at>v_now OR v_now>=p_expires_at OR "
        "p_verified_at>=p_expires_at THEN RAISE EXCEPTION "
        "'V159 attestation future-dated or expired'; END IF;"
    ) == 1
    overlap = re.search(
        r"IF EXISTS\(SELECT 1 FROM learning\.alr_challenger_fit_attestations e "
        r"WHERE (.*?)\) THEN RAISE EXCEPTION 'V159 attestation replay conflict'",
        attestor,
        re.DOTALL,
    )
    assert overlap
    assert overlap.group(1).strip() == _ATTESTOR_OVERLAP_PREDICATE
    assert "e.durable_attestation_hash<>v_hash" in overlap.group(1)
    assert _ATTESTOR_OVERLAP_EXISTING_ARRAY in overlap.group(1)
    assert "&& ARRAY[v_q10,v_q50,v_q90]::TEXT[]" in overlap.group(1)
    overlap_position = overlap.start()
    insert_position = attestor.index(
        "INSERT INTO learning.alr_challenger_fit_attestations"
    )
    fresh_now_position = attestor.index("v_now:=clock_timestamp()")
    duplicate_return_position = attestor.index(
        "RETURN jsonb_build_object('status','DUPLICATE'"
    )
    post_insert_expiry_guard = (
        "IF v_inserted IS NOT NULL AND clock_timestamp()>=p_expires_at "
        "THEN RAISE EXCEPTION 'V159 attestation future-dated or expired'; END IF;"
    )
    assert post_insert_expiry_guard in attestor
    post_insert_expiry_position = attestor.index(post_insert_expiry_guard)
    insert_tail = (
        "ON CONFLICT DO NOTHING RETURNING durable_attestation_hash "
        "INTO v_inserted;"
    )
    assert attestor.count(insert_tail) == 1
    attestor_lock_end = attestor.index("END LOOP;", attestor_lock.start())
    post_compare_position = attestor.index(
        "IF NOT FOUND OR ROW(", lookup_matches[1].end()
    )
    final_return_position = attestor.rindex("RETURN jsonb_build_object(")
    assert len(re.findall(r"\bRETURN\b", attestor)) == 2
    assert (
        attestor_lock_end
        < lookup_matches[0].start()
        < duplicate_return_position
        < overlap_position
        < fresh_now_position
        < insert_position
        < post_insert_expiry_position
        < lookup_matches[1].start()
        < post_compare_position
        < final_return_position
    )

    writer = _function_body(sql, "v159_result_writer")
    assert "--" not in writer
    assert not re.search(r"\bIF\s+FALSE\b", writer, re.IGNORECASE)
    assert not re.search(r"\bv_(?:arts|regs)\s*:=", writer)
    assert writer.count("v_bound:=") == 2
    assert _control_token_inventory(writer) == {
        "IF": 24,
        "ELSIF": 1,
        "FOR": 1,
        "LOOP": 2,
        "WHILE": 0,
        "FOREACH": 0,
        "EXIT": 0,
        "CONTINUE": 0,
        "CASE": 2,
        "WHEN": 4,
        "BEGIN": 1,
        "EXCEPTION": 13,
    }
    assert _into_statement_count(writer, "v_bound") == 0
    for target in ("v_runs", "v_arts", "v_regs"):
        assert _into_statement_count(writer, target) == 1
    writer_lock = re.search(r"FOR v_lock_key IN (.*?) LOOP", writer, re.DOTALL)
    assert writer_lock
    assert writer_lock.group(1).strip() == _WRITER_LOCK_SELECT
    assert writer.count(_WRITER_LOCK_BLOCK) == 1
    assert writer.count("PERFORM pg_advisory_xact_lock(v_lock_key)") == 1
    assert "statement_timestamp()" not in writer
    assert writer.count("clock_timestamp()") == 1
    persisted_bound_position = writer.index("v_bound:=r.attestation_bound_at")
    fresh_bound_position = writer.index("v_bound:=clock_timestamp()")
    writer_lock_end = writer.index("END LOOP;", writer_lock.start())
    count_position = writer.index("SELECT count(*) INTO v_runs")
    assert (
        writer_lock_end
        < count_position
        < persisted_bound_position
        < fresh_bound_position
        < writer.index("expired or future attestation cannot bind")
    )
    assert re.search(
        r"IF v_runs=1 THEN .*? v_existing:=TRUE; "
        r"v_bound:=r\.attestation_bound_at;\s*"
        r"ELSIF v_runs=0 AND v_arts=0 AND v_regs=0 THEN "
        r"v_bound:=clock_timestamp\(\); IF a\.verified_at>v_bound "
        r"OR v_bound>=a\.expires_at",
        writer,
        re.DOTALL,
    )
    assert writer.count(_WRITER_ARTIFACT_COUNT) == 1
    assert writer.count(_WRITER_REGISTRY_COUNT) == 1
    write_position = writer.index(
        "INSERT INTO learning.alr_challenger_training_runs"
    )
    return_position = writer.index("RETURN jsonb_build_object(")
    exception_tail = "EXCEPTION WHEN unique_violation THEN"
    assert exception_tail in writer
    exception_tail_position = writer.index(exception_tail)
    assert len(re.findall(r"\bRETURN\b", writer)) == 1
    assert (
        writer_lock_end
        < count_position
        < write_position
        < return_position
        < exception_tail_position
    )
    assert writer.rstrip().endswith(
        "EXCEPTION WHEN unique_violation THEN\n"
        "    RAISE EXCEPTION 'V159 result v2 identity collision' "
        "USING ERRCODE='P0001';\n"
        "END"
    )

    assert "'pg_temp.alr_v159_expected_attestations',17,p_mode<>'legacy'" in sql
    assert "CASE WHEN p_mode='legacy' THEN 13 ELSE 28 END" in sql
    assert "v_attestation_relation AND v_lineage_columns = 11" in sql
    assert "v_v159_constraints = 29" in sql
    assert "IF v_count<>29 THEN" in sql
    assert "V159 constraints %/29" in sql
    for tag in ("v159_attestation_writer", "v159_result_writer"):
        digest = hashlib.md5(_function_body(sql, tag).encode()).hexdigest()
        assert sql.count(f"'{digest}'") == 3, (tag, digest)


def test_v159_collision_hardening_contract() -> None:
    _assert_collision_hardening_contract(_sql())


@pytest.mark.parametrize(
    "needle,replacement",
    tuple((name, f"removed_{name}") for name, _ in _COLLISION_UNIQUES)
    + (
        ("ELSE 28 END", "ELSE 22 END"),
        ("v_v159_constraints = 29", "v_v159_constraints = 23"),
        ("IF v_count<>29 THEN", "IF v_count<>23 THEN"),
        (
            "    CONSTRAINT alr_fit_attestations_structural_result_uniq\n"
            "        UNIQUE (structural_result_hash) NOT DEFERRABLE,",
            "    -- CONSTRAINT alr_fit_attestations_structural_result_uniq\n"
            "    --     UNIQUE (structural_result_hash) NOT DEFERRABLE,",
        ),
        (
            "    CONSTRAINT alr_fit_attestations_structural_result_uniq\n"
            "        UNIQUE (structural_result_hash) NOT DEFERRABLE,",
            "    /* CONSTRAINT alr_fit_attestations_structural_result_uniq\n"
            "        UNIQUE (structural_result_hash) NOT DEFERRABLE, */",
        ),
    ),
)
def test_v159_collision_catalog_mutations_are_rejected(
    needle: str, replacement: str
) -> None:
    sql = _sql()
    assert needle in sql
    weakened = sql.replace(needle, replacement, 1)
    with pytest.raises(AssertionError):
        _assert_collision_hardening_contract(weakened)


@pytest.mark.parametrize(
    "tag,needle,replacement",
    (
        (
            "v159_attestation_writer",
            "structural_result_hash=p_structural_result_hash",
            "FALSE",
        ),
        (
            "v159_attestation_writer",
            "ORDER BY (durable_attestation_hash=v_hash) DESC LIMIT 1",
            "ORDER BY (durable_attestation_hash=v_hash) ASC LIMIT 1",
        ),
        ("v159_attestation_writer", "e.durable_attestation_hash<>v_hash", "TRUE"),
        (
            "v159_attestation_writer",
            "e.durable_attestation_hash<>v_hash",
            "e.durable_attestation_hash=v_hash",
        ),
        (
            "v159_attestation_writer",
            "ARRAY[v_q10,v_q50,v_q90]",
            "ARRAY[v_q10,v_q10,v_q10]",
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_Q_ASSIGNMENTS,
            _ATTESTOR_Q_ASSIGNMENTS.replace(
                "{artifacts,q50,artifact_hash}", "{artifacts,q10,artifact_hash}"
            ).replace(
                "{artifacts,q90,artifact_hash}", "{artifacts,q10,artifact_hash}"
            ),
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_OVERLAP_EXISTING_ARRAY,
            _ATTESTOR_OVERLAP_EXISTING_ARRAY.replace("q50", "q10").replace(
                "q90", "q10"
            ),
        ),
        (
            "v159_attestation_writer",
            "hashtextextended('v159:artifact:'||artifact_hash,0)",
            "0::bigint",
        ),
        (
            "v159_attestation_writer",
            "pg_advisory_xact_lock(v_lock_key)",
            "pg_advisory_xact_lock(0)",
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_LOCK_BLOCK,
            _ATTESTOR_LOCK_BLOCK.replace(
                "        PERFORM pg_advisory_xact_lock(v_lock_key);\n",
                "        NULL;\n",
            )
            + "\n    PERFORM pg_advisory_xact_lock(v_lock_key);",
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_LOCK_BLOCK,
            f"/*{_ATTESTOR_LOCK_BLOCK}*/",
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_LOCK_BLOCK,
            f"    IF FALSE THEN\n{_ATTESTOR_LOCK_BLOCK}\n    END IF;",
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_LOCK_BLOCK,
            f"    IF NULL THEN\n{_ATTESTOR_LOCK_BLOCK}\n    END IF;",
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_LOCK_BLOCK,
            f"    CASE WHEN NULL THEN\n{_ATTESTOR_LOCK_BLOCK}\n    END CASE;",
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_LOCK_BLOCK,
            "    BEGIN\n        NULL;\n    EXCEPTION WHEN OTHERS THEN\n"
            f"{_ATTESTOR_LOCK_BLOCK}\n    END;",
        ),
        (
            "v159_attestation_writer",
            "ORDER BY lock_key LOOP",
            "ORDER BY lock_key DESC LOOP",
        ),
        (
            "v159_attestation_writer",
            "ORDER BY lock_key LOOP",
            "ORDER BY lock_key LIMIT 1 LOOP",
        ),
        (
            "v159_attestation_writer",
            "v_now:=clock_timestamp()",
            "v_now:=statement_timestamp()",
        ),
        (
            "v159_attestation_writer",
            "v_now:=clock_timestamp();",
            "v_now:=clock_timestamp(); v_now:=p_verified_at;",
        ),
        (
            "v159_attestation_writer",
            "v_inserted IS NOT NULL AND clock_timestamp()>=p_expires_at",
            "v_inserted IS NULL AND clock_timestamp()>=p_expires_at",
        ),
        (
            "v159_attestation_writer",
            "&& ARRAY[v_q10,v_q50,v_q90]::TEXT[]",
            "&& ARRAY[]::TEXT[]",
        ),
        (
            "v159_attestation_writer",
            "&& ARRAY[v_q10,v_q50,v_q90]::TEXT[]) THEN",
            "&& ARRAY[v_q10,v_q50,v_q90]::TEXT[] AND FALSE) THEN",
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_OVERLAP_STATEMENT,
            f"IF FALSE THEN {_ATTESTOR_OVERLAP_STATEMENT} END IF;",
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_OVERLAP_STATEMENT,
            f"IF NULL THEN {_ATTESTOR_OVERLAP_STATEMENT} END IF;",
        ),
        (
            "v159_attestation_writer",
            "ordered_artifact_set_hash=p_ordered_artifact_set_hash ORDER BY",
            "ordered_artifact_set_hash=p_ordered_artifact_set_hash AND FALSE ORDER BY",
        ),
        (
            "v159_attestation_writer",
            " ON CONFLICT DO NOTHING",
            "",
        ),
        (
            "v159_attestation_writer",
            "ON CONFLICT DO NOTHING RETURNING durable_attestation_hash INTO v_inserted",
            "ON CONFLICT (durable_attestation_hash) DO UPDATE SET "
            "external_receipt_digest=EXCLUDED.external_receipt_digest "
            "RETURNING durable_attestation_hash INTO v_inserted",
        ),
        (
            "v159_attestation_writer",
            "IF v_inserted IS NOT NULL AND clock_timestamp()>=p_expires_at "
            "THEN RAISE EXCEPTION 'V159 attestation future-dated or expired'; END IF;",
            "IF v_inserted IS NOT NULL AND clock_timestamp()>=p_expires_at "
            "THEN RAISE EXCEPTION 'V159 attestation future-dated or expired'; END IF; "
            "RETURN '{}'::JSONB;",
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_POST_INSERT_GUARD,
            f"IF FALSE THEN {_ATTESTOR_POST_INSERT_GUARD} END IF;",
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_POST_INSERT_GUARD,
            f"IF NULL THEN {_ATTESTOR_POST_INSERT_GUARD} END IF;",
        ),
        (
            "v159_attestation_writer",
            "INTO v_inserted;",
            "INTO v_inserted; v_inserted:=NULL;",
        ),
        (
            "v159_attestation_writer",
            "INTO v_inserted;",
            "INTO v_inserted; SELECT NULL INTO v_inserted;",
        ),
        (
            "v159_attestation_writer",
            _ATTESTOR_LOCK_BLOCK,
            f"{_ATTESTOR_LOCK_BLOCK}\n"
            "    SELECT v_q10,v_q10 INTO v_q50,v_q90;",
        ),
        (
            "v159_result_writer",
            "hashtextextended(lock_material,0)",
            "hashtextextended(lock_material,1)",
        ),
        (
            "v159_result_writer",
            "::TEXT[]) lock_material ORDER BY lock_key",
            "::TEXT[]) lock_material WHERE FALSE ORDER BY lock_key",
        ),
        (
            "v159_result_writer",
            "p_q10_hash,'v159:artifact:'||p_q50_hash,'v159:artifact:'||p_q90_hash",
            "p_q10_hash,'v159:artifact:'||p_q10_hash,'v159:artifact:'||p_q10_hash",
        ),
        (
            "v159_result_writer",
            "pg_advisory_xact_lock(v_lock_key)",
            "pg_advisory_xact_lock(0)",
        ),
        (
            "v159_result_writer",
            _WRITER_LOCK_BLOCK,
            _WRITER_LOCK_BLOCK.replace(
                "        PERFORM pg_advisory_xact_lock(v_lock_key);\n",
                "        NULL;\n",
            )
            + "\n    PERFORM pg_advisory_xact_lock(v_lock_key);",
        ),
        (
            "v159_result_writer",
            _WRITER_LOCK_BLOCK,
            f"/*{_WRITER_LOCK_BLOCK}*/",
        ),
        (
            "v159_result_writer",
            _WRITER_LOCK_BLOCK,
            f"    IF FALSE THEN\n{_WRITER_LOCK_BLOCK}\n    END IF;",
        ),
        (
            "v159_result_writer",
            _WRITER_LOCK_BLOCK,
            f"    IF NULL THEN\n{_WRITER_LOCK_BLOCK}\n    END IF;",
        ),
        (
            "v159_result_writer",
            _WRITER_LOCK_BLOCK,
            f"    CASE WHEN NULL THEN\n{_WRITER_LOCK_BLOCK}\n    END CASE;",
        ),
        (
            "v159_result_writer",
            _WRITER_LOCK_BLOCK,
            "    BEGIN\n        NULL;\n    EXCEPTION WHEN OTHERS THEN\n"
            f"{_WRITER_LOCK_BLOCK}\n    END;",
        ),
        (
            "v159_result_writer",
            _WRITER_LOCK_BLOCK,
            "    RETURN '{}'::JSONB;\n" + _WRITER_LOCK_BLOCK,
        ),
        (
            "v159_result_writer",
            "ORDER BY lock_key LOOP",
            "ORDER BY lock_key DESC LOOP",
        ),
        (
            "v159_result_writer",
            "ORDER BY lock_key LOOP",
            "ORDER BY lock_key LIMIT 1 LOOP",
        ),
        ("v159_result_writer", "'v159:attestation:'", "'weak:attestation:'"),
        (
            "v159_result_writer",
            "artifact_hash IN(p_q10_hash,p_q50_hash,p_q90_hash)",
            "FALSE",
        ),
        (
            "v159_result_writer",
            "artifact_hash IN(p_q10_hash,p_q50_hash,p_q90_hash)",
            "(artifact_hash IN(p_q10_hash,p_q50_hash,p_q90_hash) AND FALSE)",
        ),
        (
            "v159_result_writer",
            "challenger_hash=a.structural_challenger_hash",
            "FALSE",
        ),
        (
            "v159_result_writer",
            "challenger_hash=a.structural_challenger_hash",
            "(challenger_hash=a.structural_challenger_hash AND FALSE)",
        ),
        (
            "v159_result_writer",
            _WRITER_REGISTRY_COUNT,
            f"{_WRITER_REGISTRY_COUNT} v_arts:=0; v_regs:=0;",
        ),
        (
            "v159_result_writer",
            _WRITER_COUNT_BLOCK,
            f"    IF FALSE THEN\n{_WRITER_COUNT_BLOCK}\n    END IF;",
        ),
        (
            "v159_result_writer",
            _WRITER_COUNT_BLOCK,
            f"    IF NULL THEN\n{_WRITER_COUNT_BLOCK}\n    END IF;",
        ),
        (
            "v159_result_writer",
            _WRITER_COUNT_BLOCK,
            f"{_WRITER_COUNT_BLOCK}\n"
            "    SELECT 0,0,0 INTO v_runs,v_arts,v_regs;",
        ),
        (
            "v159_result_writer",
            "EXCEPTION WHEN unique_violation THEN",
            "EXCEPTION WHEN OTHERS THEN",
        ),
        (
            "v159_result_writer",
            "USING ERRCODE='P0001'",
            "USING ERRCODE='23505'",
        ),
        (
            "v159_result_writer",
            "RAISE EXCEPTION 'V159 result v2 identity collision' "
            "USING ERRCODE='P0001';",
            "IF FALSE THEN RAISE EXCEPTION 'V159 result v2 identity collision' "
            "USING ERRCODE='P0001'; END IF; RAISE;",
        ),
        (
            "v159_result_writer",
            "v_bound:=clock_timestamp()",
            "v_bound:=statement_timestamp()",
        ),
        (
            "v159_result_writer",
            "IF a.verified_at>v_bound OR v_bound>=a.expires_at THEN RAISE "
            "EXCEPTION 'V159 expired or future attestation cannot bind'; END IF;",
            "IF a.verified_at>v_bound OR v_bound>=a.expires_at THEN RAISE "
            "EXCEPTION 'V159 expired or future attestation cannot bind'; END IF; "
            "v_bound:=a.expires_at;",
        ),
        (
            "v159_result_writer",
            "IF a.verified_at>v_bound OR v_bound>=a.expires_at THEN RAISE "
            "EXCEPTION 'V159 expired or future attestation cannot bind'; END IF;",
            "IF a.verified_at>v_bound OR v_bound>=a.expires_at THEN RAISE "
            "EXCEPTION 'V159 expired or future attestation cannot bind'; END IF; "
            "SELECT a.expires_at - INTERVAL '1 microsecond' INTO v_bound;",
        ),
        (
            "v159_result_writer",
            "v_bound:=r.attestation_bound_at",
            "v_bound:=clock_timestamp()",
        ),
    ),
)
def test_v159_collision_function_semantic_mutations_are_rejected(
    tag: str, needle: str, replacement: str
) -> None:
    weakened = _mutate_function_body_and_refresh_md5(
        _sql(), tag, needle, replacement
    )
    with pytest.raises(AssertionError):
        _assert_collision_hardening_contract(weakened)


def test_v159_collision_both_lookup_false_mutation_is_rejected() -> None:
    sql = _sql()
    tag = "v159_attestation_writer"
    body = _function_body(sql, tag)
    assert body.count(_ATTESTOR_LOOKUP_PREDICATE) == 2
    mutated_body = body.replace(
        _ATTESTOR_LOOKUP_PREDICATE,
        f"({_ATTESTOR_LOOKUP_PREDICATE}) AND FALSE",
    )
    weakened = _replace_function_body_and_refresh_md5(sql, tag, mutated_body)
    with pytest.raises(AssertionError):
        _assert_collision_hardening_contract(weakened)


def test_v159_collision_attestor_lock_reordering_mutation_is_rejected() -> None:
    sql = _sql()
    tag = "v159_attestation_writer"
    body = _function_body(sql, tag)
    lock = re.search(
        r"    FOR v_lock_key IN .*?\n    END LOOP;\n", body, re.DOTALL
    )
    overlap = re.search(
        r"    IF EXISTS\(SELECT 1 FROM "
        r"learning\.alr_challenger_fit_attestations e WHERE .*?"
        r"&& ARRAY\[v_q10,v_q50,v_q90\]::TEXT\[\]\) THEN "
        r"RAISE EXCEPTION 'V159 attestation replay conflict'; END IF;\n",
        body,
        re.DOTALL,
    )
    assert lock and overlap and lock.end() < overlap.start()
    mutated_body = body[: lock.start()] + body[lock.end() :]
    overlap_end = overlap.end() - (lock.end() - lock.start())
    mutated_body = (
        mutated_body[:overlap_end] + lock.group(0) + mutated_body[overlap_end:]
    )
    weakened = _replace_function_body_and_refresh_md5(sql, tag, mutated_body)
    with pytest.raises(AssertionError):
        _assert_collision_hardening_contract(weakened)


def test_v159_collision_writer_lock_reordering_mutation_is_rejected() -> None:
    sql = _sql()
    tag = "v159_result_writer"
    body = _function_body(sql, tag)
    lock = re.search(
        r"    FOR v_lock_key IN .*?\n    END LOOP;\n", body, re.DOTALL
    )
    counts_end = re.search(
        r"    SELECT count\(\*\) INTO v_regs FROM .*?;\n", body
    )
    assert lock and counts_end and lock.end() < counts_end.start()
    mutated_body = body[: lock.start()] + body[lock.end() :]
    insertion = counts_end.end() - (lock.end() - lock.start())
    mutated_body = mutated_body[:insertion] + lock.group(0) + mutated_body[insertion:]
    weakened = _replace_function_body_and_refresh_md5(sql, tag, mutated_body)
    with pytest.raises(AssertionError):
        _assert_collision_hardening_contract(weakened)


def test_v159_collision_attestor_clock_reordering_mutation_is_rejected() -> None:
    sql = _sql()
    tag = "v159_attestation_writer"
    body = _function_body(sql, tag)
    clock_line = "    v_now:=clock_timestamp();\n"
    lock_start = body.index("    FOR v_lock_key IN ")
    assert body.index(clock_line) > lock_start
    mutated_body = body.replace(clock_line, "", 1)
    mutated_body = (
        mutated_body[:lock_start] + clock_line + mutated_body[lock_start:]
    )
    weakened = _replace_function_body_and_refresh_md5(sql, tag, mutated_body)
    with pytest.raises(AssertionError):
        _assert_collision_hardening_contract(weakened)


def test_v159_collision_writer_clock_reordering_mutation_is_rejected() -> None:
    sql = _sql()
    tag = "v159_result_writer"
    body = _function_body(sql, tag)
    lock_start = body.index("    FOR v_lock_key IN ")
    assert body.index("v_bound:=clock_timestamp()") > lock_start
    mutated_body = body.replace(
        "v_bound:=clock_timestamp()", "v_bound:=v_bound", 1
    )
    mutated_body = (
        mutated_body[:lock_start]
        + "    v_bound:=clock_timestamp();\n"
        + mutated_body[lock_start:]
    )
    weakened = _replace_function_body_and_refresh_md5(sql, tag, mutated_body)
    with pytest.raises(AssertionError):
        _assert_collision_hardening_contract(weakened)


def test_v159_collision_post_insert_expiry_reordering_mutation_is_rejected() -> None:
    sql = _sql()
    tag = "v159_attestation_writer"
    body = _function_body(sql, tag)
    guard_line = (
        "    IF v_inserted IS NOT NULL AND clock_timestamp()>=p_expires_at "
        "THEN RAISE EXCEPTION 'V159 attestation future-dated or expired'; END IF;\n"
    )
    insert_start = body.index(
        "    INSERT INTO learning.alr_challenger_fit_attestations"
    )
    assert body.index(guard_line) > insert_start
    mutated_body = body.replace(guard_line, "", 1)
    mutated_body = (
        mutated_body[:insert_start] + guard_line + mutated_body[insert_start:]
    )
    weakened = _replace_function_body_and_refresh_md5(sql, tag, mutated_body)
    with pytest.raises(AssertionError):
        _assert_collision_hardening_contract(weakened)


@pytest.mark.parametrize("tag", ("v159_attestation_writer", "v159_result_writer"))
def test_v159_collision_function_md5_mutation_is_rejected(tag: str) -> None:
    sql = _sql()
    digest = hashlib.md5(_function_body(sql, tag).encode()).hexdigest()
    assert sql.count(digest) == 3
    with pytest.raises(AssertionError):
        _assert_collision_hardening_contract(sql.replace(digest, "0" * 32, 1))


_FORWARD_V159_FUNCTION_IDENTITIES = (
    "learning.persist_alr_challenger_fit_attestation_v1("
    "bytea,jsonb,text,text,text,text,text,text,text,text,text,text,text,text,"
    "text,text,timestamp with time zone,timestamp with time zone)",
    "learning.persist_alr_challenger_training_result_v2("
    "text,text,text,text,text,text,text,text,text,text,integer,text,text,"
    "timestamp with time zone,timestamp with time zone,text,bigint,text,"
    "bigint,text,bigint)",
    "learning.read_alr_challenger_training_result_v2(text,text)",
)
_GENERIC_REACHABILITY_PROCEDURAL_GUARD = (
    "IF p_mode<>'legacy' THEN\n"
    "        IF EXISTS(SELECT 1 FROM pg_roles generic"
)
_GENERIC_REACHABILITY_BOOLEAN_GUARD = (
    "IF p_mode<>'legacy' AND EXISTS(SELECT 1 FROM pg_roles generic"
)


def _forward_function_privilege_call(identity: str, *, nullable: bool) -> str:
    resolver = (
        f"to_regprocedure('{identity}')"
        if nullable
        else f"'{identity}'::regprocedure"
    )
    return (
        "has_function_privilege(generic.rolname,"
        f"{resolver},'EXECUTE')"
    )


def _assert_catalog_hardening_contract(sql: str) -> None:
    code = "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())
    validator = _function_body(sql, "v159_catalog_validator")

    assert (
        "CREATE OR REPLACE FUNCTION pg_temp.alr_v159_assert_catalog(p_mode TEXT)"
        in code
    )
    assert "p_mode NOT IN ('legacy','replay','final')" in validator
    assert validator.count("alr_v159_assert_catalog") == 0
    assert (
        "pg_temp.alr_v159_assert_catalog(CASE WHEN v_exact_v159 "
        "THEN 'replay' ELSE 'legacy' END)"
    ) in code
    assert "pg_temp.alr_v159_assert_catalog('final')" in code
    assert "v_public_functions NOT IN (0,3)" not in code
    assert "v_public_functions<>3" in code

    for table in (
        "alr_qualified_training_receipts",
        "alr_challenger_training_runs",
        "alr_challenger_model_artifacts",
        "alr_challenger_registry",
        "alr_challenger_fit_attestations",
    ):
        assert table in validator
    for catalog_signal in (
        "format_type(a.atttypid,a.atttypmod)",
        "a.attnotnull",
        "a.atthasdef",
        "a.attgenerated",
        "a.attidentity",
        "a.attndims<>0",
        "a.attcollation",
        "c.relkind='r'",
        "c.relpersistence='p'",
        "c.relispartition IS FALSE",
        "c.relrowsecurity IS FALSE",
        "c.relforcerowsecurity IS FALSE",
        "c.relreplident='d'",
        "c.reloptions IS NULL",
    ):
        assert catalog_signal in validator
    for char_catalog_column in ("attgenerated", "attidentity"):
        assert (
            f"COALESCE(NULLIF(a.{char_catalog_column}::TEXT,''),'-')"
            in validator
        )
        assert f"COALESCE(NULLIF(a.{char_catalog_column},''),'-')" not in validator

    assert "CREATE TEMP TABLE alr_v159_expected_" in code
    assert "pg_get_expr(a.conbin,a.conrelid,FALSE)" in validator
    assert "pg_get_expr(e.conbin,e.conrelid,FALSE)" in validator
    assert "INTO v_expr" in validator
    assert " LIKE " not in validator
    for constraint_signal in (
        "c.contype",
        "c.conkey",
        "c.confkey",
        "c.confupdtype='a'",
        "c.confdeltype='a'",
        "c.confmatchtype='s'",
        "c.convalidated",
        "c.conislocal",
        "c.coninhcount=0",
        "c.conparentid=0",
        "NOT c.condeferrable",
        "NOT c.condeferred",
    ):
        assert constraint_signal in validator
    for index_signal in (
        "i.indnkeyatts=i.indnatts",
        "i.indexprs IS NULL",
        "i.indpred IS NULL",
        "i.indisvalid",
        "i.indisready",
        "i.indislive",
        "NOT i.indisexclusion",
        "NOT i.indnullsnotdistinct",
        "i.indkey",
        "i.indclass",
        "i.indcollation",
        "i.indoption",
    ):
        assert index_signal in validator
    for trigger_signal in (
        "t.tgtype",
        "t.tgenabled='O'",
        "t.tgnargs=0",
        "t.tgqual IS NULL",
        "t.tgattr::TEXT=''",
        "t.tgdeferrable",
        "t.tginitdeferred",
        "t.tgconstraint",
        "c.contype='t'",
    ):
        assert trigger_signal in validator
    assert "7 ELSE 11" in validator

    assert "aclexplode" in validator
    assert "privilege.grantor=v_schema_owner" in validator
    assert "privilege.is_grantable" in validator
    assert "'SELECT,INSERT'" not in validator
    assert "has_table_privilege" in validator
    assert "a.attacl IS NOT NULL" in validator
    assert "pg_shdepend" in validator
    assert "p.prorettype=CASE" in validator
    assert (
        "v_writer_owned<>(CASE p_mode WHEN 'legacy' THEN 6 ELSE 9 END)"
        in validator
    )
    assert (
        "v_attestor_owned<>(CASE p_mode WHEN 'legacy' THEN 0 ELSE 2 END)"
        in validator
    )

    for digest_signal in (
        "p.prosrc='pg_digest'",
        "p.probin='$libdir/pgcrypto'",
        "p.provolatile='i'",
        "p.proisstrict",
        "p.proparallel='s'",
        "NOT p.prosecdef",
        "p.prorettype='bytea'::regtype",
        "p.proargtypes='17 25'::oidvector",
        "p.proowner=e.extowner",
    ):
        assert digest_signal in validator
    assert "has_schema_privilege('alr_challenger_fit_attestor','public','USAGE')" in validator
    assert "privilege.grantor=n.nspowner" in validator
    assert "GRANT USAGE ON SCHEMA public TO alr_challenger_fit_attestor" in code
    assert "REVOKE EXECUTE ON FUNCTION public.digest" not in code

    assert "V159 catalog FAIL: generic role reachability" in validator
    assert "V159 catalog FAIL: generic learning CREATE reachability" in validator
    assert "V159 catalog FAIL: projection-read ACL/posture" in validator
    assert "privilege.grantor<>c.relowner" in validator
    assert "left(generic.rolname,3)<>'pg_'" in validator
    assert _GENERIC_REACHABILITY_PROCEDURAL_GUARD in validator
    assert _GENERIC_REACHABILITY_BOOLEAN_GUARD not in validator
    for identity in _FORWARD_V159_FUNCTION_IDENTITIES:
        safe = _forward_function_privilege_call(identity, nullable=True)
        unsafe = _forward_function_privilege_call(identity, nullable=False)
        assert validator.count(safe) == 1
        assert unsafe not in validator
    assert code.count("fit_completed_at <= attestation_verified_at") == 1
    assert "DROP CONSTRAINT alr_challenger_runs_v159_time_check" not in code


def test_v159_catalog_hardening_contract() -> None:
    _assert_catalog_hardening_contract(_sql())


@pytest.mark.parametrize(
    "needle,replacement",
    (
        (
            "p_mode NOT IN ('legacy','replay','final')",
            "p_mode NOT IN ('legacy','replay')",
        ),
        ("c.confupdtype='a'", "c.confupdtype='c'"),
        ("i.indnkeyatts=i.indnatts", "i.indnkeyatts<=i.indnatts"),
        ("privilege.grantor=v_schema_owner", "privilege.grantor<>v_schema_owner"),
        ("p.prosrc='pg_digest'", "p.prosrc='rogue_digest'"),
        ("p.prorettype=CASE", "p.prorettype<>CASE"),
        ("a.attndims<>0", "a.attndims<0"),
        (
            "COALESCE(NULLIF(a.attgenerated::TEXT,''),'-')",
            "COALESCE(NULLIF(a.attgenerated,''),'-')",
        ),
        (
            "COALESCE(NULLIF(a.attidentity::TEXT,''),'-')",
            "COALESCE(NULLIF(a.attidentity,''),'-')",
        ),
        ("NOT i.indnullsnotdistinct", "i.indnullsnotdistinct"),
        ("privilege.grantor<>c.relowner", "privilege.grantor=c.relowner"),
        (
            "v_writer_owned<>(CASE p_mode WHEN 'legacy' THEN 6 ELSE 9 END)",
            "v_writer_owned<0",
        ),
        (
            "fit_completed_at <= attestation_verified_at",
            "fit_completed_at > attestation_verified_at",
        ),
    ),
)
def test_v159_catalog_hardening_mutations_are_rejected(
    needle: str, replacement: str
) -> None:
    sql = _sql()
    assert needle in sql
    weakened = sql.replace(needle, replacement, 1)
    with pytest.raises(AssertionError):
        _assert_catalog_hardening_contract(weakened)


@pytest.mark.parametrize("identity", _FORWARD_V159_FUNCTION_IDENTITIES)
def test_v159_forward_function_eager_resolution_mutations_are_rejected(
    identity: str,
) -> None:
    sql = _sql()
    safe = _forward_function_privilege_call(identity, nullable=True)
    unsafe = _forward_function_privilege_call(identity, nullable=False)
    assert safe in sql
    with pytest.raises(AssertionError):
        _assert_catalog_hardening_contract(sql.replace(safe, unsafe, 1))


def test_v159_generic_reachability_boolean_guard_mutation_is_rejected() -> None:
    sql = _sql()
    assert _GENERIC_REACHABILITY_PROCEDURAL_GUARD in sql
    weakened = sql.replace(
        _GENERIC_REACHABILITY_PROCEDURAL_GUARD,
        _GENERIC_REACHABILITY_BOOLEAN_GUARD,
        1,
    )
    with pytest.raises(AssertionError):
        _assert_catalog_hardening_contract(weakened)


def _check_expressions(sql: str) -> dict[str, list[str]]:
    expressions: dict[str, list[str]] = {}
    pattern = re.compile(r"(?:ADD\s+)?CONSTRAINT\s+(\w+)\s+CHECK\s*\(", re.I)
    for match in pattern.finditer(sql):
        depth = 1
        cursor = match.end()
        quoted = False
        while cursor < len(sql) and depth:
            char = sql[cursor]
            if char == "'":
                if quoted and cursor + 1 < len(sql) and sql[cursor + 1] == "'":
                    cursor += 2
                    continue
                quoted = not quoted
            elif not quoted and char == "(":
                depth += 1
            elif not quoted and char == ")":
                depth -= 1
            cursor += 1
        assert depth == 0, match.group(1)
        expressions.setdefault(match.group(1), []).append(
            sql[match.end() : cursor - 1]
        )
    return expressions


def _compact_check(expression: str) -> str:
    return re.sub(r"\s+", "", expression).lower()


_POSTGRES_ARE_BOUND_LIMIT = 255
_POSTGRES_ARE_BOUND = re.compile(r"(?<!\\)\{(\d+)(?:,(\d*))?\}")
_ATTESTATION_SIGNATURE_PATTERN = (
    r"^[A-Za-z0-9_-]{43}[A-Za-z0-9_-]{0,255}"
    r"[A-Za-z0-9_-]{0,214}={0,2}$"
)
_ATTESTATION_EVIDENCE_CHECK_SHA256 = (
    "7e42b8382023589139a24a7b61050418d37a7338cfa444d10eb609c8be47dc82",
    "247c61dbb9b95b0af30423e11ffe04751b5ffc1a10b440ded046354fec126cc2",
)


def _assert_attestation_signature_are_bounds_supported(pattern: str) -> None:
    # This is intentionally scoped to the frozen signature alphabet below,
    # which contains no literal brace.  It is not a general SQL/ARE parser.
    bounds = list(_POSTGRES_ARE_BOUND.finditer(pattern))
    assert bounds
    for bound in bounds:
        lower = int(bound.group(1))
        upper_text = bound.group(2)
        assert lower <= _POSTGRES_ARE_BOUND_LIMIT, (
            pattern,
            bound.group(0),
        )
        if upper_text not in (None, ""):
            upper = int(upper_text)
            assert lower <= upper <= _POSTGRES_ARE_BOUND_LIMIT, (
                pattern,
                bound.group(0),
            )


def _executable_named_checks(sql: str, name: str) -> list[str]:
    code = _pg_top_level_code(sql)
    declaration = re.compile(
        rf"\bCONSTRAINT\s+{re.escape(name)}\s+CHECK\s*\(",
        re.IGNORECASE,
    )
    expressions: list[str] = []
    for match in declaration.finditer(code):
        depth = 1
        cursor = match.end()
        while cursor < len(code) and depth:
            if code[cursor] == "(":
                depth += 1
            elif code[cursor] == ")":
                depth -= 1
            cursor += 1
        assert depth == 0, name
        expressions.append(sql[match.end() : cursor - 1])
    return expressions


def _executed_dollar_ddl_bodies(function_body: str) -> list[str]:
    marker = "$ddl$"
    code = _pg_top_level_code(function_body)
    bodies: list[str] = []
    cursor = 0
    while True:
        opening = function_body.find(marker, cursor)
        if opening < 0:
            break
        sentinel = "Q" * len(marker)
        probe = (
            function_body[:opening]
            + sentinel
            + function_body[opening + len(marker) :]
        )
        marker_is_top_level = (
            _pg_top_level_code(probe)[opening : opening + len(marker)]
            == sentinel
        )
        if not marker_is_top_level:
            cursor = opening + len(marker)
            continue
        closing = function_body.find(marker, opening + len(marker))
        assert closing >= 0
        if re.search(r"\bEXECUTE\s*$", code[:opening], re.IGNORECASE):
            bodies.append(
                function_body[opening + len(marker) : closing]
            )
        cursor = closing + len(marker)
    return bodies


def _attestation_evidence_checks(sql: str) -> tuple[str, str]:
    name = "alr_fit_attestations_evidence_check"
    validator = _function_body(sql, "v159_catalog_validator")
    expected = [
        expression
        for body in _executed_dollar_ddl_bodies(validator)
        for expression in _executable_named_checks(body, name)
    ]
    authored = _executable_named_checks(
        sql.split("$v159_catalog_validator$;", 1)[1],
        name,
    )
    assert len(expected) == 1
    assert len(authored) == 1
    return expected[0], authored[0]


@pytest.mark.parametrize(
    "sql",
    (
        "EXECUTE /* $ddl$CHECK(TRUE)$ddl$ */ 'SELECT 1';",
        "EXECUTE '$ddl$CHECK(TRUE)$ddl$';",
        "EXECUTE -- $ddl$CHECK(TRUE)$ddl$\n'SELECT 1';",
    ),
)
def test_v159_non_executable_dollar_ddl_decoys_are_rejected(sql: str) -> None:
    assert _executed_dollar_ddl_bodies(sql) == []


def _assert_exact_attestation_signature_patterns(sql: str) -> None:
    checks = _attestation_evidence_checks(sql)
    for expression, expected_hash in zip(
        checks,
        _ATTESTATION_EVIDENCE_CHECK_SHA256,
        strict=True,
    ):
        assert hashlib.sha256(expression.encode("utf-8")).hexdigest() == (
            expected_hash
        )
        assert expression.count(_ATTESTATION_SIGNATURE_PATTERN) == 1


def test_v159_attestation_signature_pattern_is_exact_and_pg_compatible() -> None:
    sql = _sql()
    _assert_attestation_signature_are_bounds_supported(
        _ATTESTATION_SIGNATURE_PATTERN
    )
    _assert_exact_attestation_signature_patterns(sql)


@pytest.mark.parametrize(
    ("old", "new"),
    (
        ("{43}", "{42}"),
        ("{0,214}", "{0,215}"),
        ("={0,2}", "={0,3}"),
        ("A-Za-z0-9_-", "A-Za-z0-9_+/-"),
        ("$", ""),
    ),
)
def test_v159_attestation_signature_pattern_mutations_are_rejected(
    old: str,
    new: str,
) -> None:
    sql = _sql()
    assert sql.count(_ATTESTATION_SIGNATURE_PATTERN) == 2
    weakened_pattern = _ATTESTATION_SIGNATURE_PATTERN.replace(old, new, 1)
    assert weakened_pattern != _ATTESTATION_SIGNATURE_PATTERN
    weakened = sql.replace(
        _ATTESTATION_SIGNATURE_PATTERN,
        weakened_pattern,
        1,
    )
    with pytest.raises(AssertionError):
        _assert_exact_attestation_signature_patterns(weakened)


def test_v159_unsupported_postgres_are_bound_mutation_is_rejected() -> None:
    sql = _sql()
    assert sql.count(_ATTESTATION_SIGNATURE_PATTERN) == 2
    invalid_pattern = _ATTESTATION_SIGNATURE_PATTERN.replace(
        "{0,214}",
        "{0,256}",
        1,
    )
    with pytest.raises(AssertionError):
        _assert_attestation_signature_are_bounds_supported(invalid_pattern)
    invalid = sql.replace(
        _ATTESTATION_SIGNATURE_PATTERN,
        invalid_pattern,
        1,
    )
    with pytest.raises(AssertionError):
        _assert_exact_attestation_signature_patterns(invalid)


def test_v159_hosted_invalid_signature_pattern_mutation_is_rejected() -> None:
    sql = _sql()
    assert sql.count(_ATTESTATION_SIGNATURE_PATTERN) == 2
    invalid_pattern = r"^[A-Za-z0-9_-]{43,512}={0,2}$"
    invalid = sql.replace(
        _ATTESTATION_SIGNATURE_PATTERN,
        invalid_pattern,
        1,
    )
    with pytest.raises(AssertionError):
        _assert_attestation_signature_are_bounds_supported(invalid_pattern)
    with pytest.raises(AssertionError):
        _assert_exact_attestation_signature_patterns(invalid)


def test_v159_dual_mirror_signature_comment_spoof_is_rejected() -> None:
    sql = _sql().replace(_ATTESTATION_SIGNATURE_PATTERN, ".*")
    expected_operand = (
        "COALESCE(receipt_projection#>>'{authentication,signature}','')"
        "~'.*'"
    )
    authored_operand = (
        "COALESCE(receipt_projection#>>'{authentication,signature}', '')"
        "\n            ~ '.*'"
    )
    frozen_operand_comment = (
        "/*COALESCE(receipt_projection#>>'{authentication,signature}','')"
        f"~'{_ATTESTATION_SIGNATURE_PATTERN}'*/"
    )
    assert sql.count(expected_operand) == 1
    assert sql.count(authored_operand) == 1
    spoofed = sql.replace(
        expected_operand,
        frozen_operand_comment + expected_operand,
        1,
    ).replace(
        authored_operand,
        frozen_operand_comment + authored_operand,
        1,
    )
    assert spoofed.count(frozen_operand_comment) == 2
    _assert_expected_checks_track_authored_ddl(spoofed)
    with pytest.raises(AssertionError):
        _assert_exact_attestation_signature_patterns(spoofed)


def test_v159_dual_mirror_signature_dollar_spoof_is_rejected() -> None:
    sql = _sql().replace(_ATTESTATION_SIGNATURE_PATTERN, ".*")
    expected_operand = (
        "COALESCE(receipt_projection#>>'{authentication,signature}','')"
        "~'.*'"
    )
    authored_operand = (
        "COALESCE(receipt_projection#>>'{authentication,signature}', '')"
        "\n            ~ '.*'"
    )
    frozen_operand = (
        "COALESCE(receipt_projection#>>'{authentication,signature}','')"
        f"~'{_ATTESTATION_SIGNATURE_PATTERN}'"
    )
    spoof = f"($spoof${frozen_operand}$spoof$ IS NOT NULL) AND "
    assert sql.count(expected_operand) == 1
    assert sql.count(authored_operand) == 1
    spoofed = sql.replace(
        expected_operand,
        spoof + expected_operand,
        1,
    ).replace(
        authored_operand,
        spoof + authored_operand,
        1,
    )
    assert spoofed.count(spoof) == 2
    _assert_expected_checks_track_authored_ddl(spoofed)
    with pytest.raises(AssertionError):
        _assert_exact_attestation_signature_patterns(spoofed)


def test_v159_dual_mirror_full_check_comment_decoy_is_rejected() -> None:
    sql = _sql()
    expected_check, authored_check = _attestation_evidence_checks(sql)
    weakened = sql.replace(_ATTESTATION_SIGNATURE_PATTERN, ".*")
    expected_declaration = (
        "ADD CONSTRAINT alr_fit_attestations_evidence_check CHECK("
    )
    authored_declaration = (
        "    CONSTRAINT alr_fit_attestations_evidence_check CHECK ("
    )
    expected_decoy = (
        "/* CONSTRAINT alr_fit_attestations_evidence_check CHECK("
        f"{expected_check}) */ "
    )
    authored_decoy = (
        "/* CONSTRAINT alr_fit_attestations_evidence_check CHECK("
        f"{authored_check}) */\n"
    )
    assert weakened.count(expected_declaration) == 1
    assert weakened.count(authored_declaration) == 1
    spoofed = weakened.replace(
        expected_declaration,
        expected_decoy + expected_declaration,
        1,
    ).replace(
        authored_declaration,
        authored_decoy + authored_declaration,
        1,
    )
    assert spoofed.count("~'.*'") == 1
    assert spoofed.count("~ '.*'") == 1
    _assert_expected_checks_track_authored_ddl(spoofed)
    with pytest.raises(AssertionError):
        _assert_exact_attestation_signature_patterns(spoofed)


def test_v159_attestation_signature_pattern_preserves_frozen_boundaries() -> None:
    pattern = re.compile(_ATTESTATION_SIGNATURE_PATTERN)
    for core_length in (43, 44, 255, 256, 297, 298, 511, 512):
        core = "A" * core_length
        for padding in ("", "=", "=="):
            assert pattern.fullmatch(core + padding)
    for core_length in (0, 1, 42, 513, 514, 600):
        assert pattern.fullmatch("A" * core_length) is None
    for invalid in ("A" * 42 + "+", "A" * 43 + "===", "=" * 43):
        assert pattern.fullmatch(invalid) is None


def _assert_expected_checks_track_authored_ddl(sql: str) -> None:
    validator = _function_body(sql, "v159_catalog_validator")
    expected = _check_expressions(validator)
    v158_authored = _check_expressions(
        V158.read_text(encoding="utf-8").split(
            "-- Guard B compares each durable CHECK", 1
        )[0]
    )
    v159_authored = _check_expressions(
        sql.split("$v159_catalog_validator$;", 1)[1]
    )
    legacy = (
        "alr_qualified_receipts_hashes_check",
        "alr_qualified_receipts_status_check",
        "alr_qualified_receipts_payload_check",
        "alr_qualified_receipts_no_authority_check",
        "alr_qualified_receipts_counters_check",
        "alr_challenger_runs_hashes_check",
        "alr_challenger_runs_model_schema_check",
        "alr_challenger_runs_state_check",
        "alr_challenger_runs_payload_check",
        "alr_challenger_runs_no_authority_check",
        "alr_challenger_runs_counters_check",
        "alr_challenger_artifacts_hashes_check",
        "alr_challenger_artifacts_shape_check",
        "alr_challenger_registry_hashes_check",
        "alr_challenger_registry_state_check",
        "alr_challenger_registry_payload_check",
    )
    for name in legacy:
        assert _compact_check(expected[name][0]) == _compact_check(
            v158_authored[name][0]
        ), name
    upgraded_or_new = (
        "alr_challenger_runs_payload_check",
        "alr_challenger_runs_counters_check",
        "alr_challenger_artifacts_shape_check",
        "alr_challenger_registry_payload_check",
        "alr_challenger_runs_v159_hashes_check",
        "alr_challenger_runs_v159_time_check",
        "alr_challenger_artifacts_v159_hashes_check",
        "alr_challenger_registry_v159_hashes_check",
    )
    for name in upgraded_or_new:
        assert _compact_check(expected[name][-1]) == _compact_check(
            v159_authored[name][-1]
        ), name
    attestation = (
        "alr_fit_attestations_hashes_check",
        "alr_fit_attestations_signed_bytes_check",
        "alr_fit_attestations_evidence_check",
        "alr_fit_attestations_time_check",
        "alr_fit_attestations_no_authority_check",
        "alr_fit_attestations_counters_check",
    )
    for name in attestation:
        assert _compact_check(expected[name][0]) == _compact_check(
            v159_authored[name][0]
        ), name


def test_v159_expected_checks_track_authored_ddl() -> None:
    _assert_expected_checks_track_authored_ddl(_sql())


def test_v159_expected_check_mutation_is_rejected() -> None:
    sql = _sql()
    weakened = sql.replace(
        "'alr_challenger_training_result_v1'",
        "'alr_challenger_training_result_v0'",
        1,
    )
    with pytest.raises(AssertionError):
        _assert_expected_checks_track_authored_ddl(weakened)


def _functional_probe_source() -> str:
    assert FUNCTIONAL_PROBE.exists(), FUNCTIONAL_PROBE
    return FUNCTIONAL_PROBE.read_text(encoding="utf-8")


_AST_EXPECTED_FUNCTIONS = {
    "attest": "persist_alr_challenger_fit_attestation_v1",
    "bind": "persist_alr_challenger_training_result_v2",
    "read": "read_alr_challenger_training_result_v2",
    "closed_write": "persist_alr_challenger_training_result_v1",
    "closed_read": "read_alr_challenger_training_result_v1",
}
_AST_EXPECTED_ATTEST_ARGUMENTS = (
    ("p_signed_receipt_bytes", "bytea"),
    ("p_receipt_projection", "jsonb"),
    ("p_durable_receipt_hash", "text"),
    ("p_training_key_hash", "text"),
    ("p_structural_result_hash", "text"),
    ("p_structural_fit_capture_hash", "text"),
    ("p_structural_candidate_hash", "text"),
    ("p_structural_training_run_hash", "text"),
    ("p_structural_challenger_hash", "text"),
    ("p_runner_identity_hash", "text"),
    ("p_actual_input_material_set_hash", "text"),
    ("p_ordered_artifact_set_hash", "text"),
    ("p_issuer_id", "text"),
    ("p_trust_policy_id", "text"),
    ("p_signature_key_id", "text"),
    ("p_signature_algorithm", "text"),
    ("p_verified_at", "timestamptz"),
    ("p_expires_at", "timestamptz"),
)
_AST_EXPECTED_BIND_ARGUMENTS = (
    ("p_durable_attestation_hash", "text"),
    ("p_source_head", "text"),
    ("p_actual_dataset_hash", "text"),
    ("p_actual_row_ids_hash", "text"),
    ("p_actual_split_hash", "text"),
    ("p_actual_code_manifest_hash", "text"),
    ("p_actual_training_config_hash", "text"),
    ("p_actual_feature_schema_hash", "text"),
    ("p_actual_label_schema_hash", "text"),
    ("p_model_schema_version", "text"),
    ("p_actual_training_rows", "integer"),
    ("p_metrics_hash", "text"),
    ("p_resource_usage_hash", "text"),
    ("p_fit_started_at", "timestamptz"),
    ("p_fit_completed_at", "timestamptz"),
    ("p_q10_hash", "text"),
    ("p_q10_size", "bigint"),
    ("p_q50_hash", "text"),
    ("p_q50_size", "bigint"),
    ("p_q90_hash", "text"),
    ("p_q90_size", "bigint"),
)
_AST_EXPECTED_READ_ARGUMENTS = (
    ("p_durable_attestation_hash", "text"),
    ("p_structural_training_run_hash", "text"),
)
_AST_EXPECTED_MALFORMED_CASES = (
    "root_missing",
    "root_extra",
    "wrong_root_type",
    "subject_missing",
    "claims_false",
    "actual_inputs_extra",
    "model_scalar",
    "artifacts_missing",
    "bytes_mismatch",
    "signature_bad",
    "evidence_tier_bad",
    "claim_kind_bad",
    "authentication_status_bad",
    "issuer_id_bad",
    "policy_id_bad",
    "signature_key_id_bad",
    "algorithm_bad",
    "no_authority_true",
    "counter_nonzero",
    "hash_bad",
    "lineage_bad",
    "artifact_set_bad",
    "training_rows_string",
    "training_rows_zero",
    "training_rows_fraction",
    "training_rows_overflow",
    "artifact_size_zero",
    "artifact_size_string",
    "artifact_size_fraction",
    "artifact_size_overflow",
    "duplicate_q_hash",
    "q_object_extra",
    "q_object_scalar",
    "fit_completed_after_verified",
    "verified_not_before_expires",
    "time_reversed",
    "time_future",
    "time_expired",
    "time_nonfinite",
)
_AST_EXPECTED_SCENARIOS = (
    "_scenario_happy_path",
    "_scenario_signed_field_mutations",
    "_scenario_malformed_receipts",
    "_scenario_expiry_replay",
    "_scenario_rollback_invariants",
    "_scenario_acl_boundaries",
)
_AST_EXPECTED_REQUIRED_MARKERS = frozenset(
    {
        "BYTE_SHA256_DB_PYTHON_PARITY",
        "DURABLE_ATTESTATION_HASH_PARITY",
        "DURABLE_TRAINING_RUN_HASH_PARITY",
        "DURABLE_CHALLENGER_HASH_PARITY",
        "BYTE_EXACT_READBACK",
        "BUNDLE_1_3_1",
        "NO_AUTHORITY_FALSE_ZERO",
        "SIGNED_ALL_ARG_PARITY",
        "ATTESTATION_SIGNED_ARG_PARITY",
        "DIVERGENT_ATTESTATION_REPLAY_CONFLICT",
        "MALFORMED_VALID_ROLLBACK_NOT_FOUND",
        "MALFORMED_RECEIPTS_REJECTED",
        "EXPIRED_REPLAY_DUPLICATE",
        "BOUND_EXPIRED_RESULT_REPLAY_DUPLICATE",
        "BOUND_EXPIRED_SNAPSHOT_UNCHANGED",
        "EXPIRED_ORPHAN_BIND_DENIED",
        "V1_CALLER_DENIED",
        "V1_OWNER_HARDFAIL",
        "OWNER_V2_SESSION_IDENTITY_HARDFAIL",
        "CROSS_SEAM_DENIED",
        "DIRECT_DML_DENIED",
        "ATTESTATION_UPDATE_DENIED",
        "SESSION_REPLICATION_ROLE_DENIED",
        "ROLLBACK_CANONICAL_UNCHANGED",
        "ADVISORY_BIND_WITHOUT_UPDATE",
    }
)
_AST_ERROR_HELPERS = {
    "_expect_db_error": (
        "_call",
        frozenset({"sqlstate", "message"}),
        frozenset({"pgcode"}),
        "_scenario_signed_field_mutations",
    ),
    "_expect_db_sqlstate_only": (
        "_call",
        frozenset({"sqlstate"}),
        frozenset({"pgcode"}),
        "_scenario_malformed_receipts",
    ),
    "_expect_statement_error": (
        "cursor.execute",
        frozenset({"sqlstate", "message"}),
        frozenset({"pgcode"}),
        "_scenario_acl_boundaries",
    ),
    "_expect_function_sqlstate": (
        "_call",
        frozenset({"expected_sqlstate"}),
        frozenset({"pgcode"}),
        "_scenario_acl_boundaries",
    ),
}
_AST_EXPECTED_OUTPUT_EXPRESSIONS = {
    "schema_version": repr("alr_v159_disposable_pg_probe_v1"),
    "status": repr("PASS"),
    "database": "args.expected_database",
    "v158_sha256": "_EXPECTED_SHA256['V158']",
    "v159_sha256": "_EXPECTED_SHA256['V159']",
    "on_error_stop_equivalent": "_ON_ERROR_STOP_EQUIVALENT",
    "double_apply": "True",
    "schema_fingerprint": "fingerprint",
    "scenario_markers": "scenario_summary['markers']",
    "global_counts": "scenario_summary['global_counts']",
    "signature_fixture_only": "True",
    "external_authenticity_proven": "False",
    "model_fit_performed_by_probe": "False",
    "partial_deferred_bundle_injection_claimed": "False",
    "partial_deferred_bundle_injection_assigned_to": repr(
        "V159_CONCURRENCY_PROBE"
    ),
}


def _functional_probe_tree(source: str) -> ast.Module:
    try:
        compile(source, str(FUNCTIONAL_PROBE), "exec", dont_inherit=True)
        tree = compile(
            source,
            str(FUNCTIONAL_PROBE),
            "exec",
            flags=ast.PyCF_ONLY_AST,
            dont_inherit=True,
        )
    except SyntaxError as exc:
        raise AssertionError("V159 functional probe does not compile") from exc
    assert isinstance(tree, ast.Module)
    return tree


def _functional_assignment(tree: ast.Module, name: str) -> ast.expr:
    values: list[ast.expr] = []
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == name
                for target in statement.targets
            ):
                values.append(statement.value)
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == name
            and statement.value is not None
        ):
            values.append(statement.value)
    assert len(values) == 1, name
    return values[0]


def _functional_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        statement
        for statement in tree.body
        if isinstance(statement, ast.FunctionDef) and statement.name == name
    ]
    assert len(matches) == 1, name
    return matches[0]


def _functional_expression(source: str) -> ast.expr:
    return ast.parse(source, mode="eval").body


def _functional_ast_shape(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def _functional_dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _functional_dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _functional_calls(node: ast.AST, name: str) -> list[ast.Call]:
    return [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and _functional_dotted_name(child.func) == name
    ]


def _functional_argument_surfaces(
    tree: ast.Module,
) -> tuple[dict[str, str], dict[str, tuple[tuple[str, str], ...]]]:
    function_names = ast.literal_eval(
        _functional_assignment(tree, "_FUNCTIONS")
    )
    assert function_names == _AST_EXPECTED_FUNCTIONS
    mapping = _functional_assignment(tree, "_FUNCTION_ARGUMENTS")
    assert isinstance(mapping, ast.Dict)
    result: dict[str, tuple[tuple[str, str], ...]] = {}
    for key, value in zip(mapping.keys, mapping.values, strict=True):
        assert isinstance(key, ast.Subscript)
        assert isinstance(key.value, ast.Name) and key.value.id == "_FUNCTIONS"
        label = ast.literal_eval(key.slice)
        assert label in function_names
        function_name = function_names[label]
        assert function_name not in result
        arguments = ast.literal_eval(value)
        assert isinstance(arguments, tuple) and arguments
        assert all(
            isinstance(argument, tuple)
            and len(argument) == 2
            and all(isinstance(item, str) for item in argument)
            for argument in arguments
        )
        result[function_name] = arguments
    return function_names, result


def _functional_direct_call_name(statement: ast.stmt) -> str | None:
    value: ast.expr | None = None
    if isinstance(statement, ast.Expr):
        value = statement.value
    elif isinstance(statement, ast.Assign):
        value = statement.value
    elif isinstance(statement, ast.AnnAssign):
        value = statement.value
    if isinstance(value, ast.Call):
        return _functional_dotted_name(value.func)
    return None


def _functional_marker_additions(function: ast.FunctionDef) -> list[str]:
    markers: list[str] = []
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "markers"
            and node.func.attr == "add"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            markers.append(node.args[0].value)
    return markers


def _functional_raises_probe_failure(statements: list[ast.stmt]) -> bool:
    module = ast.Module(body=statements, type_ignores=[])
    return any(
        isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and _functional_dotted_name(node.exc.func) == "ProbeFailure"
        for node in ast.walk(module)
    )


def _functional_local_assignment(
    statements: list[ast.stmt], name: str
) -> ast.expr:
    values: list[ast.expr] = []
    for statement in statements:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        ):
            values.append(statement.value)
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == name
            and statement.value is not None
        ):
            values.append(statement.value)
    assert len(values) == 1, name
    return values[0]


def _functional_single_final_return(
    function: ast.FunctionDef, expression: str
) -> None:
    returns = [node for node in ast.walk(function) if isinstance(node, ast.Return)]
    assert len(returns) == 1, function.name
    assert function.body[-1] is returns[0], function.name
    assert returns[0].value is not None
    assert _functional_ast_shape(returns[0].value) == _functional_ast_shape(
        _functional_expression(expression)
    ), function.name


def _functional_string_constants(node: ast.AST) -> set[str]:
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


def _functional_subscript_keys(node: ast.AST) -> set[str]:
    return {
        child.slice.value
        for child in ast.walk(node)
        if isinstance(child, ast.Subscript)
        and isinstance(child.slice, ast.Constant)
        and isinstance(child.slice.value, str)
    }


def _assert_functional_hash_identity_helper(
    tree: ast.Module,
    function_name: str,
    domain: str,
    material_labels: frozenset[str],
    subscript_keys: frozenset[str],
    utc_calls: int,
) -> None:
    function = _functional_function(tree, function_name)
    material = _functional_local_assignment(function.body, "material")
    assert isinstance(material, ast.JoinedStr), function_name
    literal_material = "".join(
        part.value
        for part in material.values
        if isinstance(part, ast.Constant) and isinstance(part.value, str)
    )
    assert literal_material.startswith(f"{domain}\n"), function_name
    assert material_labels <= {
        line.split("=", 1)[0]
        for line in literal_material.splitlines()
        if "=" in line
    }, function_name
    assert subscript_keys <= _functional_subscript_keys(function), function_name
    assert len(_functional_calls(function, "_utc_six_digit_z")) == utc_calls
    _functional_single_final_return(
        function, "hashlib.sha256(material.encode('utf-8')).hexdigest()"
    )


def _assert_functional_positive_helper_contracts(tree: ast.Module) -> None:
    _assert_functional_hash_identity_helper(
        tree,
        "_expected_durable_attestation_hash",
        "alr_durable_fit_attestation_v1",
        frozenset(
            {
                "receipt",
                "durable_receipt",
                "training_key",
                "result",
                "fit_capture",
                "candidate",
                "run",
                "challenger",
                "runner",
                "materials",
                "artifacts",
                "issuer",
                "policy",
                "key",
                "verified",
                "expires",
            }
        ),
        frozenset(
            {
                "p_receipt_projection",
                "p_durable_receipt_hash",
                "p_training_key_hash",
                "p_structural_result_hash",
                "p_structural_fit_capture_hash",
                "p_structural_candidate_hash",
                "p_structural_training_run_hash",
                "p_structural_challenger_hash",
                "p_runner_identity_hash",
                "p_actual_input_material_set_hash",
                "p_ordered_artifact_set_hash",
                "p_issuer_id",
                "p_trust_policy_id",
                "p_signature_key_id",
                "verified_at",
                "expires_at",
            }
        ),
        0,
    )
    _assert_functional_hash_identity_helper(
        tree,
        "_expected_durable_training_run_hash",
        "alr_durable_training_run_v1",
        frozenset(
            {
                "attestation",
                "structural_run",
                "source",
                "dataset",
                "rows",
                "split",
                "code",
                "config",
                "feature",
                "label",
                "model",
                "training_rows",
                "artifacts",
                "metrics",
                "resources",
                "fit_start",
                "fit_end",
                "bound",
            }
        ),
        frozenset(
            {
                "bind",
                "durable_attestation_hash",
                "read",
                "p_structural_training_run_hash",
                "p_source_head",
                "p_actual_dataset_hash",
                "p_actual_row_ids_hash",
                "p_actual_split_hash",
                "p_actual_code_manifest_hash",
                "p_actual_training_config_hash",
                "p_actual_feature_schema_hash",
                "p_actual_label_schema_hash",
                "p_model_schema_version",
                "p_actual_training_rows",
                "attest",
                "p_ordered_artifact_set_hash",
                "p_metrics_hash",
                "p_resource_usage_hash",
                "p_fit_started_at",
                "p_fit_completed_at",
            }
        ),
        3,
    )
    _assert_functional_hash_identity_helper(
        tree,
        "_expected_durable_challenger_hash",
        "alr_durable_challenger_v1",
        frozenset(
            {"attestation", "durable_run", "structural_challenger", "artifacts"}
        ),
        frozenset(
            {
                "durable_attestation_hash",
                "attest",
                "p_structural_challenger_hash",
                "p_ordered_artifact_set_hash",
            }
        ),
        0,
    )

    utc = _functional_function(tree, "_utc_six_digit_z")
    _functional_single_final_return(
        utc,
        "parsed.astimezone(timezone.utc).strftime("
        "'%Y-%m-%dT%H:%M:%S.%fZ')",
    )
    assert len(_functional_calls(utc, "isinstance")) == 2
    for call_name in (
        "datetime.fromisoformat",
        "value.endswith",
        "parsed.astimezone",
        "strftime",
    ):
        assert _functional_calls(utc, call_name), call_name
    assert sum(
        1
        for node in ast.walk(utc)
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and _functional_dotted_name(node.exc.func) == "ProbeFailure"
    ) == 2

    canonical = _functional_function(tree, "_canonical_pg_jsonb_bytes")
    _functional_single_final_return(canonical, "(canonical, python_sha256)")
    for call_name in (
        "cursor.execute",
        "cursor.fetchone",
        "_pg_jsonb_ordered",
        "json.dumps",
        "hashlib.sha256",
        "hexdigest",
    ):
        assert _functional_calls(canonical, call_name), call_name
    canonical_text = " ".join(_functional_string_constants(canonical))
    for token in (
        "convert_to",
        "public.digest",
        "sha256",
        "canonical_bytes",
        "db_sha256",
        "BYTE_SHA256_DB_PYTHON_PARITY",
    ):
        assert token in canonical_text, token

    snapshot = _functional_function(tree, "_assert_bundle_snapshot")
    _functional_single_final_return(snapshot, "_normalized(row['snapshot'])")
    for call_name in ("cursor.execute", "cursor.fetchone", "_normalized"):
        assert _functional_calls(snapshot, call_name), call_name
    snapshot_text = " ".join(_functional_string_constants(snapshot))
    for token in (
        "jsonb_build_object",
        "alr_challenger_fit_attestations",
        "alr_challenger_training_runs",
        "alr_challenger_model_artifacts",
        "alr_challenger_registry",
        "signed_receipt_bytes",
        "receipt_projection",
    ):
        assert token in snapshot_text, token

    identity = _functional_function(tree, "_attestation_row_identity")
    _functional_single_final_return(identity, "_normalized(row)")
    for call_name in ("cursor.execute", "cursor.fetchone", "_normalized"):
        assert _functional_calls(identity, call_name), call_name
    identity_text = " ".join(_functional_string_constants(identity))
    for token in (
        "xmin::text",
        "ctid::text",
        "created_at",
        "alr_challenger_fit_attestations",
        "signed_receipt_bytes",
        "receipt_projection",
    ):
        assert token in identity_text, token

    exact_bundle = _functional_function(tree, "_assert_exact_bound_bundle")
    _functional_single_final_return(
        exact_bundle, "(durable_run, durable_challenger)"
    )
    required_exact_calls = {
        "_expected_durable_training_run_hash": 1,
        "_expected_durable_challenger_hash": 1,
        "cursor.execute": 1,
        "cursor.fetchone": 1,
        "_normalized": 1,
        "_require_fields": 3,
        "_utc_six_digit_z": 4,
    }
    for call_name, count in required_exact_calls.items():
        assert len(_functional_calls(exact_bundle, call_name)) == count, call_name
    exact_text = " ".join(_functional_string_constants(exact_bundle))
    for token in (
        "alr_challenger_training_runs",
        "alr_challenger_model_artifacts",
        "alr_challenger_registry",
        "alr_challenger_training_result_v2",
        "alr_challenger_registry_entry_v2",
        "TRAINING_PERFORMED",
        "NOT_SERVING",
        "q10",
        "q50",
        "q90",
        "onnx",
        "attestation_bound_at",
        "bind/read/persisted bundle projections differ",
    ):
        assert token in exact_text, token
    quantile_loops = [
        node
        for node in ast.walk(exact_bundle)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == "quantile"
    ]
    assert len(quantile_loops) == 1
    assert ast.literal_eval(quantile_loops[0].iter) == ("q10", "q50", "q90")

    happy_bundle = _functional_function(tree, "_assert_happy_bundle")
    assert not any(isinstance(node, ast.Return) for node in ast.walk(happy_bundle))
    assert len(_functional_calls(happy_bundle, "cursor.execute")) == 1
    assert len(_functional_calls(happy_bundle, "cursor.fetchone")) == 1
    count_checks = [
        node
        for node in happy_bundle.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "counts"
    ]
    assert len(count_checks) == 1
    assert ast.literal_eval(count_checks[0].test.comparators[0]) == {
        "attestations": 1,
        "runs": 1,
        "artifacts": 3,
        "registry": 1,
        "fixed_attestation": 1,
        "fixed_run": 1,
        "fixed_artifacts": 3,
        "fixed_registry": 1,
    }
    assert _functional_raises_probe_failure(count_checks[0].body)
    happy_text = " ".join(_functional_string_constants(happy_bundle))
    for token in (
        "alr_challenger_fit_attestations",
        "alr_challenger_training_runs",
        "alr_challenger_model_artifacts",
        "alr_challenger_registry",
        "model_fit_count",
        "model_training_performed",
        "NOT_SERVING",
        "serving_allowed",
        "promotion_allowed",
        "symlink_created",
        "serving_visible",
    ):
        assert token in happy_text, token


def _assert_functional_probe_contract(source: str) -> None:
    compile(source, str(FUNCTIONAL_PROBE), "exec")
    assert hashlib.sha256(V159.read_bytes()).hexdigest() == (
        "2e11d0ae0cbc2c1161a47d04bed4054c31b728e8cf945f931197f9b3455b7d74"
    )
    assert (
        '"V159": "2e11d0ae0cbc2c1161a47d04bed4054c31b728e8cf945f931197f9b3455b7d74"'
        in source
    )
    assert '_ACK_ENV = "ALR_V159_DISPOSABLE_ACK"' in source
    assert "_reject_ambient_libpq_routing()" in source
    assert "destructive_ack: bool" in source
    assert "role-session creation requires the explicit destructive ack" in source
    assert "SET SESSION AUTHORIZATION" in source
    assert "_parse_complete_dsn(" in source
    assert "class _SafeArgumentParser(argparse.ArgumentParser):" in source
    assert 'raise ProbeFailure("invalid V159 probe arguments")' in source
    assert "parser = _SafeArgumentParser(" in source
    assert "_connect as _v158_connect" in source
    assert "def _configure_v159_session(" in source
    assert source.count("_configure_v159_session(connection)") >= 2
    assert "SET SESSION TimeZone='UTC'" in source
    assert "SET SESSION default_transaction_isolation='read committed'" in source
    assert "current_setting('TimeZone')" in source
    assert "current_setting('default_transaction_isolation')" in source
    role_sessions = source[source.index("def _connect_as_role(") :]
    assert role_sessions.index("_configure_v159_session(connection)") > (
        role_sessions.index("SET SESSION AUTHORIZATION")
    )

    for helper in (
        "_canonical_pg_jsonb_bytes",
        "_expect_db_sqlstate_only",
        "_persist_qualified_receipt",
        "_expected_durable_attestation_hash",
        "_expected_durable_training_run_hash",
        "_expected_durable_challenger_hash",
        "_utc_six_digit_z",
        "_assert_exact_bound_bundle",
        "_assert_bundle_snapshot",
        "_scenario_happy_path",
        "_scenario_signed_field_mutations",
        "_scenario_malformed_receipts",
        "_scenario_expiry_replay",
        "_scenario_acl_boundaries",
        "_scenario_rollback_invariants",
        "_run_scenarios",
    ):
        assert f"def {helper}(" in source, helper

    for runtime_marker in (
        "BYTE_SHA256_DB_PYTHON_PARITY",
        "DURABLE_ATTESTATION_HASH_PARITY",
        "DURABLE_TRAINING_RUN_HASH_PARITY",
        "DURABLE_CHALLENGER_HASH_PARITY",
        "BYTE_EXACT_READBACK",
        "BUNDLE_1_3_1",
        "NO_AUTHORITY_FALSE_ZERO",
        "SIGNED_ALL_ARG_PARITY",
        "ATTESTATION_SIGNED_ARG_PARITY",
        "EXPIRED_REPLAY_DUPLICATE",
        "BOUND_EXPIRED_RESULT_REPLAY_DUPLICATE",
        "BOUND_EXPIRED_SNAPSHOT_UNCHANGED",
        "EXPIRED_ORPHAN_BIND_DENIED",
        "V1_CALLER_DENIED",
        "V1_OWNER_HARDFAIL",
        "CROSS_SEAM_DENIED",
        "DIRECT_DML_DENIED",
        "ATTESTATION_UPDATE_DENIED",
        "SESSION_REPLICATION_ROLE_DENIED",
        "ROLLBACK_CANONICAL_UNCHANGED",
        "ADVISORY_BIND_WITHOUT_UPDATE",
        "MALFORMED_RECEIPTS_REJECTED",
        "DIVERGENT_ATTESTATION_REPLAY_CONFLICT",
        "MALFORMED_VALID_ROLLBACK_NOT_FOUND",
        "OWNER_V2_SESSION_IDENTITY_HARDFAIL",
        "SCENARIO_SUITE_COMPLETE",
    ):
        assert runtime_marker in source, runtime_marker

    assert "for field_name in _SIGNED_AND_PERSISTED_FIELDS" in source
    assert "for field_name in _SIGNED_ATTESTATION_FIELDS" in source
    assert "for malformed_case in _MALFORMED_RECEIPT_CASES" in source
    assert source.count("AT TIME ZONE 'UTC'") >= 4
    assert "to_char(statement_timestamp()" not in source
    assert "pg_sleep" in source
    assert "GREATEST(" in source
    assert '"happy", expiry_seconds=12.0' in source
    assert '"expiry", expiry_seconds=6.0' in source
    assert "alr_durable_training_run_v1\\n" in source
    assert "alr_durable_challenger_v1\\n" in source
    assert "for quantile in (\"q10\", \"q50\", \"q90\")" in source
    assert "hashlib.sha512(" in source
    assert '"signature_fixture_only": True' in source
    assert '"external_authenticity_proven": False' in source
    assert '"model_fit_performed_by_probe": False' in source
    assert '"partial_deferred_bundle_injection_claimed": False' in source
    assert (
        '"partial_deferred_bundle_injection_assigned_to": '
        '"V159_CONCURRENCY_PROBE"' in source
    )
    for malformed_case in (
        "training_rows_string", "training_rows_zero", "training_rows_fraction",
        "training_rows_overflow", "artifact_size_zero", "artifact_size_string",
        "artifact_size_fraction", "artifact_size_overflow", "duplicate_q_hash",
        "q_object_extra", "q_object_scalar", "fit_completed_after_verified",
        "verified_not_before_expires",
    ):
        assert f'"{malformed_case}"' in source
    assert "executed_cases != set(_MALFORMED_RECEIPT_CASES)" in source
    assert '"alr_qualified_training_receipts"' in source
    assert '"qualified_receipt": receipt' in source
    assert 'fixture["qualified_receipt"]' in source
    assert "def _safe_entrypoint(" in source
    assert "except ProbeFailure:" in source and "except Exception:" in source
    assert 'sys.stderr.write(_SAFE_FAILURE_MESSAGE + "\\n")' in source
    assert "raise SystemExit(_safe_entrypoint())" in source
    assert "connection.rollback()" in source
    assert "base64" in source and "replace(" in source
    assert "model_fit_count" in source
    assert "serving_allowed" in source and "promotion_allowed" in source
    assert "symlink_created" in source and "serving_visible" in source
    assert "SCENARIOS_PENDING" not in source
    assert "return 2" not in source
    assert "NotImplemented" not in source and "TODO" not in source
    assert '"status": "PASS"' in source
    assert source.index("_run_scenarios(", source.index("def main(")) < source.index(
        '"status": "PASS"'
    )
    output = source[source.index("print(") :]
    for secret_name in (
        "admin_parameters",
        "signed_receipt_bytes",
        "receipt_projection",
        "dsn",
        "password",
    ):
        assert secret_name not in output


def _assert_functional_error_helper(
    tree: ast.Module,
    helper_name: str,
    action_name: str,
    required_names: frozenset[str],
    required_attributes: frozenset[str],
    caller_name: str,
) -> None:
    helper = _functional_function(tree, helper_name)
    assert not any(isinstance(node, ast.Return) for node in ast.walk(helper))
    tries = [statement for statement in helper.body if isinstance(statement, ast.Try)]
    assert len(tries) == 1, helper_name
    guarded = tries[0]
    assert _functional_calls(
        ast.Module(body=guarded.body, type_ignores=[]), action_name
    ), helper_name
    assert len(guarded.handlers) == 1, helper_name
    handler = guarded.handlers[0]
    assert handler.type is not None
    assert _functional_dotted_name(handler.type) == "psycopg2.Error"
    assert _functional_calls(handler, "connection.rollback")
    mismatch_checks = [
        statement for statement in handler.body if isinstance(statement, ast.If)
    ]
    assert len(mismatch_checks) == 1, helper_name
    mismatch = mismatch_checks[0]
    loaded_names = {
        node.id
        for node in ast.walk(mismatch.test)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    loaded_attributes = {
        node.attr for node in ast.walk(mismatch.test) if isinstance(node, ast.Attribute)
    }
    assert required_names <= loaded_names, helper_name
    assert required_attributes <= loaded_attributes, helper_name
    assert _functional_raises_probe_failure(mismatch.body), helper_name
    assert _functional_calls(
        ast.Module(body=guarded.orelse, type_ignores=[]),
        "connection.rollback",
    ), helper_name
    assert _functional_raises_probe_failure(guarded.orelse), helper_name
    assert not guarded.finalbody, helper_name
    caller = _functional_function(tree, caller_name)
    assert _functional_calls(caller, helper_name), helper_name


def _assert_functional_bind_time_oracle(tree: ast.Module) -> None:
    happy_scenario = _functional_function(tree, "_scenario_happy_path")
    bind_time_checks = [
        statement
        for statement in happy_scenario.body
        if isinstance(statement, ast.With)
    ]
    assert len(bind_time_checks) == 1
    expected = ast.parse(
        'with admin.cursor() as cursor:\n'
        '    cursor.execute(\n'
        '        "SELECT a.verified_at<=r.attestation_bound_at "\n'
        '        "AND r.attestation_bound_at<a.expires_at "\n'
        '        "AND r.attestation_verified_at=a.verified_at "\n'
        '        "AND r.attestation_expires_at=a.expires_at AS exact "\n'
        '        "FROM learning.alr_challenger_training_runs r "\n'
        '        "JOIN learning.alr_challenger_fit_attestations a "\n'
        '        "ON a.durable_attestation_hash=r.durable_attestation_hash "\n'
        '        "WHERE r.durable_attestation_hash=%s",\n'
        '        (fixture["durable_attestation_hash"],),\n'
        '    )\n'
        '    if cursor.fetchone() != {"exact": True}:\n'
        '        raise ProbeFailure("V159 database-owned bind time is invalid")\n'
    ).body[0]
    assert _functional_ast_shape(bind_time_checks[0]) == _functional_ast_shape(
        expected
    )


def _assert_functional_probe_ast_contract(source: str) -> None:
    tree = _functional_probe_tree(source)
    _assert_functional_bind_time_oracle(tree)

    pins = ast.literal_eval(_functional_assignment(tree, "_EXPECTED_SHA256"))
    assert pins == {
        "V158": hashlib.sha256(V158.read_bytes()).hexdigest(),
        "V159": hashlib.sha256(V159.read_bytes()).hexdigest(),
    }
    _assert_functional_positive_helper_contracts(tree)

    function_names, argument_surfaces = _functional_argument_surfaces(tree)
    assert argument_surfaces == {
        function_names["attest"]: _AST_EXPECTED_ATTEST_ARGUMENTS,
        function_names["bind"]: _AST_EXPECTED_BIND_ARGUMENTS,
        function_names["read"]: _AST_EXPECTED_READ_ARGUMENTS,
    }
    assert _functional_ast_shape(
        _functional_assignment(tree, "_SIGNED_AND_PERSISTED_FIELDS")
    ) == _functional_ast_shape(
        _functional_expression(
            "tuple(name for name, _ in "
            "_FUNCTION_ARGUMENTS[_FUNCTIONS['bind']] "
            "if name != 'p_durable_attestation_hash')"
        )
    )
    assert _functional_ast_shape(
        _functional_assignment(tree, "_SIGNED_ATTESTATION_FIELDS")
    ) == _functional_ast_shape(
        _functional_expression(
            "tuple(name for name, _ in "
            "_FUNCTION_ARGUMENTS[_FUNCTIONS['attest']] "
            "if name not in "
            "{'p_signed_receipt_bytes', 'p_receipt_projection'})"
        )
    )
    assert tuple(
        ast.literal_eval(_functional_assignment(tree, "_MALFORMED_RECEIPT_CASES"))
    ) == _AST_EXPECTED_MALFORMED_CASES
    signed_mutations = _functional_function(
        tree, "_scenario_signed_field_mutations"
    )
    signed_loop_inputs = [
        node.iter.id
        for node in ast.walk(signed_mutations)
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Name)
    ]
    assert signed_loop_inputs.count("_SIGNED_ATTESTATION_FIELDS") == 1
    assert signed_loop_inputs.count("_SIGNED_AND_PERSISTED_FIELDS") == 1

    malformed = _functional_function(tree, "_scenario_malformed_receipts")
    malformed_loops = [
        node
        for node in ast.walk(malformed)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Name)
        and node.iter.id == "_MALFORMED_RECEIPT_CASES"
    ]
    assert len(malformed_loops) == 1
    malformed_loop = malformed_loops[0]
    assert (
        isinstance(malformed_loop.target, ast.Name)
        and malformed_loop.target.id == "malformed_case"
    )
    assert len(_functional_calls(malformed_loop, "executed_cases.add")) == 1
    accounting_checks = [
        statement
        for statement in malformed.body
        if isinstance(statement, ast.If)
        and {
            node.id
            for node in ast.walk(statement.test)
            if isinstance(node, ast.Name)
        }
        >= {"executed_cases", "_MALFORMED_RECEIPT_CASES"}
    ]
    assert len(accounting_checks) == 1
    assert _functional_raises_probe_failure(accounting_checks[0].body)

    runner = _functional_function(tree, "_run_scenarios")
    marker_initializers = [
        statement
        for statement in runner.body
        if isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
        and statement.target.id == "markers"
    ]
    assert len(marker_initializers) == 1
    assert _functional_ast_shape(marker_initializers[0]) == _functional_ast_shape(
        ast.parse("markers: set[str] = set()").body[0]
    )
    runner_tries = [
        statement for statement in runner.body if isinstance(statement, ast.Try)
    ]
    assert len(runner_tries) == 1
    runner_body = runner_tries[0].body
    observed_scenarios = tuple(
        call_name
        for statement in runner_body
        if (call_name := _functional_direct_call_name(statement))
        in _AST_EXPECTED_SCENARIOS
    )
    assert observed_scenarios == _AST_EXPECTED_SCENARIOS
    for scenario_name in _AST_EXPECTED_SCENARIOS:
        assert len(_functional_calls(runner, scenario_name)) == 1, scenario_name

    happy_scenario = _functional_function(tree, "_scenario_happy_path")
    _functional_single_final_return(happy_scenario, "fixture")
    for scenario_name in _AST_EXPECTED_SCENARIOS[1:]:
        scenario = _functional_function(tree, scenario_name)
        assert not any(
            isinstance(node, ast.Return) for node in ast.walk(scenario)
        ), scenario_name

    runner_returns = [
        node for node in ast.walk(runner) if isinstance(node, ast.Return)
    ]
    assert len(runner_returns) == 1
    assert runner_body[-1] is runner_returns[0]
    assert _functional_ast_shape(runner_body[-2]) == _functional_ast_shape(
        ast.parse('markers.add("SCENARIO_SUITE_COMPLETE")').body[0]
    )
    required_assignments = [
        statement
        for statement in runner_body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "required"
            for target in statement.targets
        )
    ]
    assert len(required_assignments) == 1
    assert frozenset(ast.literal_eval(required_assignments[0].value)) == (
        _AST_EXPECTED_REQUIRED_MARKERS
    )
    assert _functional_marker_additions(runner) == ["SCENARIO_SUITE_COMPLETE"]

    global_count_queries = [
        statement
        for statement in runner_body
        if isinstance(statement, ast.With)
        and any(
            isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
            and "alr_qualified_training_receipts" in call.args[0].value
            for call in _functional_calls(statement, "cursor.execute")
            if call.args
        )
    ]
    assert len(global_count_queries) == 1
    global_count_query = global_count_queries[0]
    execute_calls = _functional_calls(global_count_query, "cursor.execute")
    assert len(execute_calls) == 1 and len(execute_calls[0].args) == 1
    assert ast.literal_eval(execute_calls[0].args[0]) == (
        "SELECT "
        "(SELECT count(*) FROM learning.alr_qualified_training_receipts) AS receipts,"
        "(SELECT count(*) FROM learning.alr_challenger_fit_attestations) AS attestations,"
        "(SELECT count(*) FROM learning.alr_challenger_training_runs) AS runs,"
        "(SELECT count(*) FROM learning.alr_challenger_model_artifacts) AS artifacts,"
        "(SELECT count(*) FROM learning.alr_challenger_registry) AS registry"
    )
    assert any(
        _functional_ast_shape(statement)
        == _functional_ast_shape(
            ast.parse("global_counts = cursor.fetchone()").body[0]
        )
        for statement in global_count_query.body
    )
    global_count_checks = [
        statement
        for statement in runner_body
        if isinstance(statement, ast.If)
        and isinstance(statement.test, ast.Compare)
        and isinstance(statement.test.left, ast.Name)
        and statement.test.left.id == "global_counts"
    ]
    assert len(global_count_checks) == 1
    global_count_check = global_count_checks[0]
    assert len(global_count_check.test.ops) == 1
    assert isinstance(global_count_check.test.ops[0], ast.NotEq)
    assert ast.literal_eval(global_count_check.test.comparators[0]) == {
        "receipts": 4,
        "attestations": 3,
        "runs": 1,
        "artifacts": 3,
        "registry": 1,
    }
    assert _functional_raises_probe_failure(global_count_check.body)
    assert "V159 scenario suite global counts differ" in (
        _functional_string_constants(global_count_check)
    )

    added_markers: list[str] = []
    for scenario_name in _AST_EXPECTED_SCENARIOS:
        added_markers.extend(
            _functional_marker_additions(
                _functional_function(tree, scenario_name)
            )
        )
    assert len(added_markers) == len(set(added_markers))
    assert frozenset(added_markers) == _AST_EXPECTED_REQUIRED_MARKERS

    for helper_name, contract in _AST_ERROR_HELPERS.items():
        _assert_functional_error_helper(tree, helper_name, *contract)

    main = _functional_function(tree, "main")
    main_returns = [node for node in ast.walk(main) if isinstance(node, ast.Return)]
    assert len(main_returns) == 1
    assert main.body[-1] is main_returns[0]
    assert isinstance(main_returns[0].value, ast.Constant)
    assert main_returns[0].value.value == 0
    scenario_assignments = [
        statement
        for statement in main.body
        if isinstance(statement, ast.Assign)
        and _functional_direct_call_name(statement) == "_run_scenarios"
    ]
    assert len(scenario_assignments) == 1
    assert len(_functional_calls(tree, "_run_scenarios")) == 1
    assert len(scenario_assignments[0].targets) == 1
    assert isinstance(scenario_assignments[0].targets[0], ast.Name)
    assert scenario_assignments[0].targets[0].id == "scenario_summary"

    output_assignments = [
        statement
        for statement in main.body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "output"
            for target in statement.targets
        )
    ]
    assert len(output_assignments) == 1
    output = output_assignments[0].value
    assert isinstance(output, ast.Dict)
    output_keys = [ast.literal_eval(key) for key in output.keys]
    assert output_keys == list(_AST_EXPECTED_OUTPUT_EXPRESSIONS)
    for key, value in zip(output_keys, output.values, strict=True):
        assert _functional_ast_shape(value) == _functional_ast_shape(
            _functional_expression(_AST_EXPECTED_OUTPUT_EXPRESSIONS[key])
        ), key

    main_prints = [
        statement
        for statement in main.body
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and _functional_dotted_name(statement.value.func) == "print"
    ]
    assert len(main_prints) == 1
    assert _functional_ast_shape(main_prints[0]) == _functional_ast_shape(
        ast.parse("print(json.dumps(output, sort_keys=True))").body[0]
    )
    assert len(_functional_calls(tree, "print")) == 1

    safe_entrypoint = _functional_function(tree, "_safe_entrypoint")
    assert len(safe_entrypoint.body) == 1
    assert isinstance(safe_entrypoint.body[0], ast.Try)
    safe_try = safe_entrypoint.body[0]
    assert len(safe_try.body) == 1 and isinstance(safe_try.body[0], ast.Return)
    assert _functional_ast_shape(safe_try.body[0].value) == _functional_ast_shape(
        _functional_expression("main(argv)")
    )
    assert not safe_try.orelse and not safe_try.finalbody
    assert len(safe_try.handlers) == 2
    assert [
        _functional_dotted_name(handler.type)
        for handler in safe_try.handlers
        if handler.type is not None
    ] == ["ProbeFailure", "Exception"]
    safe_write_shape = _functional_ast_shape(
        ast.parse('sys.stderr.write(_SAFE_FAILURE_MESSAGE + "\\n")').body[0]
    )
    safe_return_shape = _functional_ast_shape(ast.parse("return 1").body[0])
    for handler in safe_try.handlers:
        assert handler.name is None
        assert len(handler.body) == 2
        assert _functional_ast_shape(handler.body[0]) == safe_write_shape
        assert _functional_ast_shape(handler.body[1]) == safe_return_shape

    write_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (_functional_dotted_name(node.func) or "").endswith(".write")
    ]
    assert len(write_calls) == 2
    assert all(
        _functional_dotted_name(call.func) == "sys.stderr.write"
        for call in write_calls
    )
    forbidden_output_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            _functional_dotted_name(node.func) == "pprint"
            or (_functional_dotted_name(node.func) or "").startswith("logging.")
        )
    ]
    assert not forbidden_output_calls

    expected_guard = ast.parse(
        'if __name__ == "__main__":\n'
        "    raise SystemExit(_safe_entrypoint())\n"
    ).body[0]
    assert isinstance(expected_guard, ast.If)
    guards = [
        statement
        for statement in tree.body
        if isinstance(statement, ast.If)
        and _functional_ast_shape(statement.test)
        == _functional_ast_shape(expected_guard.test)
    ]
    assert len(guards) == 1
    assert _functional_ast_shape(guards[0]) == _functional_ast_shape(expected_guard)


def test_v159_functional_probe_source_contract() -> None:
    _assert_functional_probe_contract(_functional_probe_source())


def test_v159_functional_probe_ast_contract() -> None:
    _assert_functional_probe_ast_contract(_functional_probe_source())


def test_v159_functional_probe_checks_database_bind_time_against_attestation_row() -> None:
    _assert_functional_bind_time_oracle(
        _functional_probe_tree(_functional_probe_source())
    )


def test_v159_functional_probe_nonfinite_time_matches_writer_fail_closed_path() -> None:
    tree = _functional_probe_tree(_functional_probe_source())
    argument_builder = _functional_function(
        tree, "_malformed_attestation_arguments"
    )
    default_error = ast.parse(
        'sqlstate, message = "P0001", '
        '"V159 signed receipt bytes/projection/claim mismatch"'
    ).body[0]
    assert any(
        _functional_ast_shape(statement) == _functional_ast_shape(default_error)
        for statement in argument_builder.body
    )
    branch_test = ast.parse('malformed_case == "time_nonfinite"').body[0].value
    branches = [
        node
        for node in ast.walk(argument_builder)
        if isinstance(node, ast.If)
        and _functional_ast_shape(node.test) == _functional_ast_shape(branch_test)
    ]
    assert len(branches) == 1
    expected_body = ast.parse(
        'projection["expires_at"] = "infinity"\n'
        'arguments["p_expires_at"] = "infinity"\n'
    ).body
    assert [_functional_ast_shape(node) for node in branches[0].body] == [
        _functional_ast_shape(node) for node in expected_body
    ]

    malformed_scenario = _functional_function(
        tree, "_scenario_malformed_receipts"
    )
    assert not any(
        isinstance(node, ast.Constant) and node.value == "time_nonfinite"
        for node in ast.walk(malformed_scenario)
    )
    assert len(_functional_calls(malformed_scenario, "_expect_db_error")) == 1
    assert not _functional_calls(
        malformed_scenario, "_expect_nonfinite_constraint_error"
    )


@pytest.mark.parametrize(
    "needle,replacement",
    (
        (
            '"SELECT a.verified_at<=r.attestation_bound_at "',
            '"SELECT TRUE AS exact /* bind-time oracle bypassed */ "',
        ),
        (
            '"AND r.attestation_verified_at=a.verified_at "',
            '"AND TRUE "',
        ),
        (
            'if cursor.fetchone() != {"exact": True}:',
            "if False:",
        ),
    ),
)
def test_v159_functional_probe_bind_time_oracle_mutations_are_rejected(
    needle: str, replacement: str
) -> None:
    source = _functional_probe_source()
    assert source.count(needle) == 1
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(source.replace(needle, replacement))


@pytest.mark.parametrize(
    "needle,replacement",
    (
        (
            '_ACK_ENV = "ALR_V159_DISPOSABLE_ACK"',
            '_ACK_ENV = "ALR_V159_WEAK_ACK"',
        ),
        ("_reject_ambient_libpq_routing()", "ambient_routing_allowed()"),
        (
            "class _SafeArgumentParser(argparse.ArgumentParser):",
            "class _SafeArgumentParser(object):",
        ),
        ("_connect as _v158_connect", "_connect as _ambient_connect"),
        ("SET SESSION TimeZone='UTC'", "SET SESSION TimeZone='localtime'"),
        (
            "SET SESSION default_transaction_isolation='read committed'",
            "SET SESSION default_transaction_isolation='repeatable read'",
        ),
        (
            "_configure_v159_session(connection)",
            "allow_role_default_session(connection)",
        ),
        (
            '"V159": "2e11d0ae0cbc2c1161a47d04bed4054c31b728e8cf945f931197f9b3455b7d74"',
            '"V159": "' + "0" * 64 + '"',
        ),
        ("BYTE_EXACT_READBACK", "BYTE_READBACK_SKIPPED"),
        (
            "DURABLE_TRAINING_RUN_HASH_PARITY",
            "DURABLE_TRAINING_RUN_HASH_SKIPPED",
        ),
        (
            "DURABLE_CHALLENGER_HASH_PARITY",
            "DURABLE_CHALLENGER_HASH_SKIPPED",
        ),
        (
            "for field_name in _SIGNED_AND_PERSISTED_FIELDS",
            "for field_name in ()",
        ),
        (
            "for field_name in _SIGNED_ATTESTATION_FIELDS",
            "for field_name in ()",
        ),
        ("AT TIME ZONE 'UTC'", "AT TIME ZONE 'Europe/Madrid'"),
        ("EXPIRED_REPLAY_DUPLICATE", "EXPIRY_REPLAY_SKIPPED"),
        (
            "BOUND_EXPIRED_RESULT_REPLAY_DUPLICATE",
            "BOUND_EXPIRED_RESULT_REPLAY_SKIPPED",
        ),
        (
            "DIVERGENT_ATTESTATION_REPLAY_CONFLICT",
            "DIVERGENT_ATTESTATION_REPLAY_ALLOWED",
        ),
        (
            "MALFORMED_VALID_ROLLBACK_NOT_FOUND",
            "MALFORMED_VALID_ROLLBACK_SKIPPED",
        ),
        (
            "OWNER_V2_SESSION_IDENTITY_HARDFAIL",
            "OWNER_V2_SESSION_IDENTITY_ALLOWED",
        ),
        ("training_rows_overflow", "training_rows_overflow_skipped"),
        ('"qualified_receipt": receipt', '"qualified_receipt": None'),
        (
            'fixture["qualified_receipt"]',
            'fixture["receipt_not_returned"]',
        ),
        ("hashlib.sha512(", "hashlib.sha256("),
        (
            '"external_authenticity_proven": False',
            '"external_authenticity_proven": True',
        ),
        ("def _safe_entrypoint(", "def _unsafe_entrypoint("),
        ("V1_CALLER_DENIED", "V1_CALLER_ALLOWED"),
        ("DIRECT_DML_DENIED", "DIRECT_DML_ALLOWED"),
        ("NO_AUTHORITY_FALSE_ZERO", "AUTHORITY_UNCHECKED"),
        ("BUNDLE_1_3_1", "BUNDLE_COUNT_UNCHECKED"),
        ("SCENARIO_SUITE_COMPLETE", "SCENARIO_SUITE_PARTIAL"),
        (
            '"partial_deferred_bundle_injection_claimed": False',
            '"partial_deferred_bundle_injection_claimed": True',
        ),
    ),
)
def test_v159_functional_probe_mutations_are_rejected(
    needle: str, replacement: str
) -> None:
    source = _functional_probe_source()
    assert needle in source
    weakened = source.replace(needle, replacement)
    with pytest.raises(AssertionError):
        _assert_functional_probe_contract(weakened)


def _functional_insert_first_statement(
    source: str, function_name: str, statement: str
) -> str:
    tree = _functional_probe_tree(source)
    function = _functional_function(tree, function_name)
    lines = source.splitlines(keepends=True)
    first = function.body[0]
    lines.insert(
        first.lineno - 1,
        f"{' ' * first.col_offset}{statement}\n",
    )
    return "".join(lines)


def _functional_wrap_runner_scenario_dead(
    source: str, scenario_name: str
) -> str:
    tree = _functional_probe_tree(source)
    runner = _functional_function(tree, "_run_scenarios")
    guarded = next(
        statement for statement in runner.body if isinstance(statement, ast.Try)
    )
    scenario = next(
        statement
        for statement in guarded.body
        if _functional_direct_call_name(statement) == scenario_name
    )
    lines = source.splitlines(keepends=True)
    start = scenario.lineno - 1
    end = scenario.end_lineno
    indent = " " * scenario.col_offset
    lines[start:end] = [f"{indent}if False:\n"] + [
        f"    {line}" for line in lines[start:end]
    ]
    return "".join(lines)


def _functional_dead_main_runner(source: str) -> str:
    tree = _functional_probe_tree(source)
    main = _functional_function(tree, "main")
    scenario = next(
        statement
        for statement in main.body
        if isinstance(statement, ast.Assign)
        and _functional_direct_call_name(statement) == "_run_scenarios"
    )
    lines = source.splitlines(keepends=True)
    start = scenario.lineno - 1
    end = scenario.end_lineno
    indent = " " * scenario.col_offset
    lines[start:end] = [f"{indent}if False:\n"] + [
        f"    {line}" for line in lines[start:end]
    ] + [
        f"{indent}scenario_summary = "
        "{'markers': [], 'global_counts': {}}\n"
    ]
    return "".join(lines)


def _functional_inject_aliased_secret_print(source: str) -> str:
    tree = _functional_probe_tree(source)
    main = _functional_function(tree, "main")
    output = next(
        statement
        for statement in main.body
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and _functional_dotted_name(statement.value.func) == "print"
    )
    lines = source.splitlines(keepends=True)
    indent = " " * output.col_offset
    lines.insert(
        output.lineno - 1,
        f"{indent}leaked = admin_parameters\n{indent}print(leaked)\n",
    )
    return "".join(lines)


def test_v159_functional_probe_ast_rejects_syntax_error() -> None:
    source = _functional_probe_source()
    needle = "def _h(label: str) -> str:"
    assert needle in source
    weakened = source.replace(needle, "def _h(label: str -> str:", 1)
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


@pytest.mark.parametrize("version", ("V158", "V159"))
def test_v159_functional_probe_ast_rejects_stale_migration_pin(
    version: str,
) -> None:
    source = _functional_probe_source()
    migration = {"V158": V158, "V159": V159}[version]
    digest = hashlib.sha256(migration.read_bytes()).hexdigest()
    assert source.count(digest) == 1
    weakened = source.replace(digest, "0" * 64, 1)
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


@pytest.mark.parametrize(
    "constant_name,constructor",
    (
        ("_MALFORMED_RECEIPT_CASES", "("),
        ("_SIGNED_AND_PERSISTED_FIELDS", "tuple("),
        ("_SIGNED_ATTESTATION_FIELDS", "tuple("),
    ),
)
def test_v159_functional_probe_ast_rejects_empty_case_or_field_constants(
    constant_name: str, constructor: str
) -> None:
    source = _functional_probe_source()
    needle = f"{constant_name} = {constructor}"
    assert needle in source
    weakened = source.replace(
        needle,
        f"{constant_name} = ()\n_DEAD{constant_name} = {constructor}",
        1,
    )
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


def test_v159_functional_probe_ast_rejects_early_runner_return() -> None:
    weakened = _functional_insert_first_statement(
        _functional_probe_source(),
        "_run_scenarios",
        "return {'markers': [], 'global_counts': {}}",
    )
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


def test_v159_functional_probe_ast_rejects_dead_scenario() -> None:
    weakened = _functional_wrap_runner_scenario_dead(
        _functional_probe_source(), "_scenario_malformed_receipts"
    )
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


def test_v159_functional_probe_ast_rejects_dead_main_runner() -> None:
    weakened = _functional_dead_main_runner(_functional_probe_source())
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


@pytest.mark.parametrize("helper_name", tuple(_AST_ERROR_HELPERS))
def test_v159_functional_probe_ast_rejects_noop_error_helper(
    helper_name: str,
) -> None:
    weakened = _functional_insert_first_statement(
        _functional_probe_source(), helper_name, "return None"
    )
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


def test_v159_functional_probe_ast_rejects_aliased_secret_print() -> None:
    weakened = _functional_inject_aliased_secret_print(
        _functional_probe_source()
    )
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


@pytest.mark.parametrize(
    "helper_name,early_return",
    (
        (
            "_expected_durable_attestation_hash",
            "return '0' * 64",
        ),
        (
            "_expected_durable_training_run_hash",
            "return '0' * 64",
        ),
        (
            "_expected_durable_challenger_hash",
            "return '0' * 64",
        ),
        ("_utc_six_digit_z", "return str(value)"),
        ("_canonical_pg_jsonb_bytes", "return b'', '0' * 64"),
        ("_assert_bundle_snapshot", "return {}"),
        ("_attestation_row_identity", "return {}"),
        (
            "_assert_exact_bound_bundle",
            "return bind_result['durable_training_run_hash'], "
            "bind_result['durable_challenger_hash']",
        ),
        ("_assert_happy_bundle", "return None"),
    ),
)
def test_v159_functional_probe_ast_rejects_early_positive_helper_return(
    helper_name: str, early_return: str
) -> None:
    weakened = _functional_insert_first_statement(
        _functional_probe_source(), helper_name, early_return
    )
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


def test_v159_functional_probe_ast_rejects_early_malformed_return() -> None:
    weakened = _functional_insert_first_statement(
        _functional_probe_source(),
        "_scenario_malformed_receipts",
        "return None",
    )
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


def test_v159_functional_probe_ast_rejects_marker_preseed() -> None:
    source = _functional_probe_source()
    needle = "markers: set[str] = set()"
    assert source.count(needle) == 1
    weakened = source.replace(
        needle,
        'markers: set[str] = {"MALFORMED_VALID_ROLLBACK_NOT_FOUND", '
        '"MALFORMED_RECEIPTS_REJECTED"}',
        1,
    )
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


def test_v159_functional_probe_ast_rejects_global_receipt_count_drift() -> None:
    source = _functional_probe_source()
    needle = '"receipts": 4,'
    assert source.count(needle) == 1
    weakened = source.replace(needle, '"receipts": 3,', 1)
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


def test_v159_functional_probe_ast_rejects_composed_scenario_bypass() -> None:
    weakened = _functional_insert_first_statement(
        _functional_probe_source(),
        "_scenario_malformed_receipts",
        "return None",
    )
    weakened = weakened.replace(
        "markers: set[str] = set()",
        'markers: set[str] = {"MALFORMED_VALID_ROLLBACK_NOT_FOUND", '
        '"MALFORMED_RECEIPTS_REJECTED"}',
        1,
    )
    weakened = weakened.replace('"receipts": 4,', '"receipts": 3,', 1)
    with pytest.raises(AssertionError):
        _assert_functional_probe_ast_contract(weakened)


_CONCURRENCY_EXPECTED_SHA256 = {
    "V158": "7ed70599c6bd5f3cdb3376bc135a952d8c18f4ad62a62432c2bfdd8ee84e446b",
    "V159": "2e11d0ae0cbc2c1161a47d04bed4054c31b728e8cf945f931197f9b3455b7d74",
}
_CONCURRENCY_SCENARIO_ORDER = (
    "_scenario_identical_attestation",
    "_scenario_structural_identity_collisions",
    "_scenario_artifact_collisions",
    "_scenario_wait_past_expiry_attestor_lock",
    "_scenario_wait_past_expiry_unique_index",
    "_scenario_uncommitted_visibility",
    "_scenario_partial_bundle_injection",
    "_scenario_identical_bind",
    "_scenario_divergent_bind",
    "_scenario_bind_rollback",
    "_scenario_wait_past_expiry_bind",
)
_CONCURRENCY_SCENARIO_RETURNS = {
    "_scenario_identical_attestation": "fixture",
    "_scenario_structural_identity_collisions": "fixture",
    "_scenario_artifact_collisions": "None",
    "_scenario_wait_past_expiry_attestor_lock": "None",
    "_scenario_wait_past_expiry_unique_index": "None",
    "_scenario_uncommitted_visibility": "fixture",
    "_scenario_partial_bundle_injection": "None",
    "_scenario_identical_bind": "None",
    "_scenario_divergent_bind": "None",
    "_scenario_bind_rollback": "None",
    "_scenario_wait_past_expiry_bind": "None",
}
_CONCURRENCY_STRUCTURAL_FIELDS = (
    "p_structural_result_hash",
    "p_structural_fit_capture_hash",
    "p_structural_candidate_hash",
    "p_structural_training_run_hash",
    "p_structural_challenger_hash",
    "p_ordered_artifact_set_hash",
)
_CONCURRENCY_ARTIFACT_MODES = (
    "same_quantile",
    "cross_quantile",
    "exact_set",
)
_CONCURRENCY_REQUIRED_MARKERS = frozenset(
    {
        "IDENTICAL_ATTESTATION_PERSISTED_DUPLICATE",
        "IDENTICAL_ATTESTATION_IMMUTABLE",
        "UNCOMMITTED_STRUCTURAL_IDENTITY_P0001",
        "ALL_SIX_STRUCTURAL_IDENTITIES_P0001",
        "SAME_QUANTILE_ARTIFACT_P0001",
        "CROSS_QUANTILE_ARTIFACT_P0001",
        "EXACT_SET_ARTIFACT_P0001",
        "LOCK_BLOCKED_ARTIFACT_P0001",
        "WAIT_PAST_EXPIRY_ATTESTOR_LOCK_REJECTED",
        "WAIT_PAST_EXPIRY_UNIQUE_INDEX_REJECTED",
        "UNCOMMITTED_ATTESTATION_INVISIBLE",
        "ATTESTED_UNBOUND_AFTER_COMMIT",
        "PARTIAL_DEFERRED_BUNDLE_INJECTION_REJECTED",
        "PARTIAL_DEFERRED_BUNDLE_ROLLBACK_CLEAN",
        "IDENTICAL_BIND_PERSISTED_DUPLICATE",
        "BIND_ADVISORY_LOCKS_OBSERVED",
        "EXACT_BOUND_BUNDLE",
        "DIVERGENT_BIND_P0001_NO_PARTIAL",
        "BIND_ROLLBACK_ATTESTED_UNBOUND",
        "WAIT_PAST_EXPIRY_BIND_REJECTED",
        "WORKER_CONNECTION_OWNERSHIP_UNIQUE",
        "NO_AUTHORITY_FALSE_ZERO",
        "GLOBAL_ORACLE_3_3_2_6_2",
        "SCENARIO_SUITE_COMPLETE",
    }
)
_CONCURRENCY_WORKERS = frozenset(
    {
        "_attest_worker",
        "_bind_worker",
        "_lock_holder_worker",
        "_read_worker",
        "_partial_bundle_worker",
    }
)
_CONCURRENCY_GLOBAL_ORACLE = {
    "receipts": 3,
    "attestations": 3,
    "runs": 2,
    "artifacts": 6,
    "registry": 2,
}
_CONCURRENCY_OUTPUT_EXPRESSIONS = {
    "schema_version": repr("alr_v159_concurrency_disposable_pg_probe_v1"),
    "status": repr("PASS"),
    "database": "args.expected_database",
    "v158_sha256": "_EXPECTED_SHA256['V158']",
    "v159_sha256": "_EXPECTED_SHA256['V159']",
    "on_error_stop_equivalent": "_ON_ERROR_STOP_EQUIVALENT",
    "double_apply": "True",
    "scenario_markers": "summary['markers']",
    "global_counts": "summary['global_counts']",
    "signature_fixture_only": "True",
    "external_authenticity_proven": "False",
    "model_fit_performed_by_probe": "False",
    "partial_deferred_bundle_injection_exercised": "True",
    "partial_deferred_bundle_injection_claimed": "True",
    "postgresql_executed": "True",
    "session_authorization_test_only": "True",
    "connection_limit_preserved": "True",
    "admin_role_sessions_same_target": "True",
    "utc_read_committed_sessions": "True",
    "thread_local_connections": "True",
    "bounded_synchronization": "True",
    "advisory_lock_wait_observed": "True",
}


def _concurrency_probe_source() -> str:
    assert CONCURRENCY_PROBE.exists(), CONCURRENCY_PROBE
    source = CONCURRENCY_PROBE.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 2000
    return source


def _concurrency_probe_tree(source: str) -> ast.Module:
    try:
        compile(source, str(CONCURRENCY_PROBE), "exec", dont_inherit=True)
        tree = compile(
            source,
            str(CONCURRENCY_PROBE),
            "exec",
            flags=ast.PyCF_ONLY_AST,
            dont_inherit=True,
        )
    except SyntaxError as exc:
        raise AssertionError("V159 concurrency probe does not compile") from exc
    assert isinstance(tree, ast.Module)
    return tree


def _concurrency_scenario_calls(function: ast.FunctionDef) -> tuple[str, ...]:
    calls = sorted(
        (
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and _functional_dotted_name(node.func) in _CONCURRENCY_SCENARIO_ORDER
        ),
        key=lambda node: (node.lineno, node.col_offset),
    )
    return tuple(_functional_dotted_name(call.func) or "" for call in calls)


def _concurrency_call_has_timeout(call: ast.Call) -> bool:
    return any(keyword.arg == "timeout" for keyword in call.keywords)


def _concurrency_nested_assignment(
    function: ast.FunctionDef, name: str
) -> ast.expr:
    values: list[ast.expr] = []
    for statement in ast.walk(function):
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        ):
            values.append(statement.value)
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == name
            and statement.value is not None
        ):
            values.append(statement.value)
    assert len(values) == 1, name
    return values[0]


def _concurrency_assert_direct_if_predicate(
    function: ast.FunctionDef, expression: str
) -> None:
    expected = _functional_ast_shape(_functional_expression(expression))
    matches = [
        statement
        for statement in function.body
        if isinstance(statement, ast.If)
        and _functional_ast_shape(statement.test) == expected
    ]
    assert len(matches) == 1, (function.name, expression)


def _assert_concurrency_probe_contract(source: str) -> None:
    tree = _concurrency_probe_tree(source)
    assert len(source.splitlines()) < 2000
    assert "ThreadPoolExecutor" in source
    assert "Barrier" in source and "Event" in source and "Queue" in source
    assert "with ThreadPoolExecutor" not in source
    assert "time.sleep(" not in source and "pg_sleep" not in source
    assert "FROM pg_locks" in source and "FROM pg_stat_activity" in source
    for token in (
        "classid", "objid", "objsubid", "database", "pid", "granted",
        "hashtextextended", "wait_event_type", "transactionid",
        "AdvisoryLock", "clock_timestamp()", "SET CONSTRAINTS",
        "PARTIAL_OR_DIVERGENT", "P0001", "23505", "rolconnlimit",
    ):
        assert token in source, token
    for forbidden in (
        "traceback", "format_exc", "logging.", "repr(exc)", "str(exc)",
        "exc.args", "sys.stdout.write",
    ):
        assert forbidden not in source

    pins = ast.literal_eval(_functional_assignment(tree, "_EXPECTED_SHA256"))
    assert pins == _CONCURRENCY_EXPECTED_SHA256
    assert ast.literal_eval(
        _functional_assignment(tree, "_SCENARIO_ORDER")
    ) == _CONCURRENCY_SCENARIO_ORDER
    assert ast.literal_eval(
        _functional_assignment(tree, "_STRUCTURAL_IDENTITY_FIELDS")
    ) == _CONCURRENCY_STRUCTURAL_FIELDS
    assert ast.literal_eval(
        _functional_assignment(tree, "_ARTIFACT_COLLISION_MODES")
    ) == _CONCURRENCY_ARTIFACT_MODES
    assert frozenset(
        ast.literal_eval(_functional_assignment(tree, "_REQUIRED_MARKERS"))
    ) == _CONCURRENCY_REQUIRED_MARKERS
    deadline = ast.literal_eval(_functional_assignment(tree, "_DEADLINE_SECONDS"))
    assert isinstance(deadline, (int, float)) and 0 < deadline <= 30
    statement_timeout = ast.literal_eval(
        _functional_assignment(tree, "_STATEMENT_TIMEOUT_MS")
    )
    lock_timeout = ast.literal_eval(
        _functional_assignment(tree, "_LOCK_TIMEOUT_MS")
    )
    assert isinstance(statement_timeout, int)
    assert isinstance(lock_timeout, int)
    assert 0 < lock_timeout < statement_timeout <= deadline * 1000

    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    safe_parsers = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "_SafeArgumentParser"
    ]
    assert len(safe_parsers) == 1
    safe_parser = safe_parsers[0]
    assert any(_functional_dotted_name(base) == "argparse.ArgumentParser" for base in safe_parser.bases)
    error_methods = [
        node
        for node in safe_parser.body
        if isinstance(node, ast.FunctionDef) and node.name == "error"
    ]
    assert len(error_methods) == 1
    assert _functional_raises_probe_failure(error_methods[0].body)
    assert set(_CONCURRENCY_SCENARIO_ORDER).issubset(functions)
    assert _CONCURRENCY_WORKERS.issubset(functions)
    for required in (
        "_worker_session", "_admin_worker_session", "_run_concurrently",
        "_wait_for_blocked", "_observe_domain_locks", "_global_oracle",
        "_assert_pre_expiry", "_run_scenarios", "main", "_safe_entrypoint",
    ):
        assert required in functions

    worker_session = functions["_worker_session"]
    worker_source = ast.get_source_segment(source, worker_session) or ""
    assert "_connect_as_role" in worker_source
    assert "_ROLE_AUTHORIZATION[role]" in worker_source
    assert ast.literal_eval(
        _functional_assignment(tree, "_ROLE_AUTHORIZATION")
    ) == {
        "alr_challenger_fit_attestor_caller": (
            "SET SESSION AUTHORIZATION alr_challenger_fit_attestor_caller"
        ),
        "alr_challenger_trainer_caller": (
            "SET SESSION AUTHORIZATION alr_challenger_trainer_caller"
        ),
    }
    assert "SET SESSION TimeZone='UTC'" in worker_source
    assert "read committed" in worker_source
    assert "SET LOCAL statement_timeout" in worker_source
    assert "SET LOCAL lock_timeout" in worker_source
    assert "_worker_identity(connection, label, role)" in worker_source
    assert "_configure_v159_session" not in worker_source
    assert ".close()" in worker_source and "finally:" in worker_source
    admin_session_source = ast.get_source_segment(
        source, functions["_admin_worker_session"]
    ) or ""
    assert "_connect(" in admin_session_source
    assert "SET SESSION AUTHORIZATION" in admin_session_source
    assert (
        '_worker_identity(connection, label, admin_parameters["user"])'
        in admin_session_source
    )
    assert "_configure_v159_session" not in admin_session_source
    assert ".close()" in admin_session_source and "finally:" in admin_session_source

    identity_source = ast.get_source_segment(
        source, functions["_worker_identity"]
    ) or ""
    assert "pg_backend_pid" in identity_source
    assert "threading.get_ident" in identity_source
    assert '"session_user": expected_role' in identity_source
    assert '"current_user": expected_role' in identity_source
    assert "if not row:" in identity_source
    assert identity_source.index("if not row:") < identity_source.index(
        'row["backend_pid"]'
    )
    _functional_single_final_return(
        functions["_worker_identity"],
        "{'worker': label, 'backend_pid': int(row['backend_pid']), "
        "'thread_id': threading.get_ident()}",
    )

    for no_return_helper in (
        "_wait_event",
        "_observe_domain_locks",
        "_assert_p0001",
        "_assert_no_attestation",
        "_assert_pre_expiry",
        "_assert_connection_limits",
    ):
        assert not any(
            isinstance(node, ast.Return)
            for node in ast.walk(functions[no_return_helper])
        ), no_return_helper
    _functional_single_final_return(functions["_wait_for_blocked"], "observed")
    _functional_single_final_return(functions["_wait_past_expiry"], "None")

    blocked_source = ast.get_source_segment(
        source, functions["_wait_for_blocked"]
    ) or ""
    for token in (
        "FROM pg_stat_activity",
        'row["wait_event_type"] == "Lock"',
        'row["wait_event"] in set(expected_waits)',
        'row["state"] == "active"',
    ):
        assert token in blocked_source
    lock_source = ast.get_source_segment(
        source, functions["_observe_domain_locks"]
    ) or ""
    for token in (
        "FROM pg_locks holder",
        "JOIN pg_locks waiter",
        "holder.pid=%s",
        "waiter.pid=%s",
        "holder.granted IS TRUE",
        "waiter.granted IS FALSE",
        "waiter.database=holder.database",
        "waiter.classid=holder.classid",
        "waiter.objid=holder.objid",
        "waiter.objsubid=holder.objsubid",
    ):
        assert token in lock_source
    p0001_source = ast.get_source_segment(source, functions["_assert_p0001"]) or ""
    assert 'outcome.get("sqlstate") == "23505"' in p0001_source
    assert 'outcome.get("sqlstate") != "P0001"' in p0001_source
    assert 'outcome.get("message") != message' in p0001_source
    _concurrency_assert_direct_if_predicate(
        functions["_assert_pre_expiry"], 'row != {"pre_expiry": True}'
    )
    _concurrency_assert_direct_if_predicate(
        functions["_observe_domain_locks"],
        'not row or row["holder_labels"] != expected '
        'or not row["waiter_labels"] or len(row["waiter_labels"]) != 1 '
        'or row["waiter_labels"][0] not in expected',
    )
    _concurrency_assert_direct_if_predicate(
        functions["_assert_p0001"],
        'outcome.get("sqlstate") == "23505"',
    )
    _concurrency_assert_direct_if_predicate(
        functions["_assert_p0001"],
        'outcome.get("sqlstate") != "P0001" '
        'or outcome.get("message") != message',
    )
    _concurrency_assert_direct_if_predicate(
        functions["_assert_connection_limits"],
        'rows != ['
        '{"rolname": "alr_challenger_fit_attestor_caller", "rolconnlimit": 1},'
        '{"rolname": "alr_challenger_trainer_caller", "rolconnlimit": 1}]',
    )

    for worker_name in _CONCURRENCY_WORKERS:
        worker = functions[worker_name]
        body_source = ast.get_source_segment(source, worker) or ""
        assert "_worker_session" in body_source or "_admin_worker_session" in body_source
        assert ".close()" not in body_source
        assert not any(argument.arg == "connection" for argument in worker.args.args)
        assert any(isinstance(node, ast.Return) for node in ast.walk(worker))
    assert "_call(" in ast.get_source_segment(source, functions["_attest_worker"])
    assert "_call(" in ast.get_source_segment(source, functions["_bind_worker"])
    assert "_call(" in ast.get_source_segment(source, functions["_read_worker"])
    partial_worker_source = ast.get_source_segment(
        source, functions["_partial_bundle_worker"]
    ) or ""
    assert "_adapt(_normalized(run_row))" in partial_worker_source

    runner = functions["_run_scenarios"]
    assert _concurrency_scenario_calls(runner) == _CONCURRENCY_SCENARIO_ORDER
    marker_assignment = _functional_local_assignment(runner.body, "markers")
    assert isinstance(marker_assignment, ast.Call)
    assert _functional_dotted_name(marker_assignment.func) == "set"
    assert not marker_assignment.args and not marker_assignment.keywords
    fixture_assignment = _concurrency_nested_assignment(runner, "receipts")
    assert isinstance(fixture_assignment, ast.Dict)
    assert [ast.literal_eval(key) for key in fixture_assignment.keys] == ["a", "b", "c"]

    observed_markers: list[str] = []
    for scenario_name in _CONCURRENCY_SCENARIO_ORDER:
        scenario = functions[scenario_name]
        observed_markers.extend(_functional_marker_additions(scenario))
        _functional_single_final_return(
            scenario, _CONCURRENCY_SCENARIO_RETURNS[scenario_name]
        )
    observed_markers.extend(
        _functional_marker_additions(functions["_global_oracle"])
    )
    observed_markers.extend(
        _functional_marker_additions(functions["_run_scenarios"])
    )
    assert len(observed_markers) == len(set(observed_markers))
    assert frozenset(observed_markers) == _CONCURRENCY_REQUIRED_MARKERS

    identical_attestation_source = ast.get_source_segment(
        source, functions["_scenario_identical_attestation"]
    ) or ""
    for token in (
        'statuses != ["DUPLICATE", "PERSISTED"]',
        "persisted_payload != duplicate_payload",
        'fixture["durable_attestation_hash"]',
        'fixture["external_receipt_digest"]',
        "_utc_six_digit_z",
    ):
        assert token in identical_attestation_source
    _concurrency_assert_direct_if_predicate(
        functions["_scenario_identical_attestation"],
        'statuses != ["DUPLICATE", "PERSISTED"]',
    )
    _concurrency_assert_direct_if_predicate(
        functions["_scenario_identical_attestation"],
        "persisted_payload != duplicate_payload",
    )
    structural_source = ast.get_source_segment(
        source, functions["_scenario_structural_identity_collisions"]
    ) or ""
    assert "_STRUCTURAL_IDENTITY_FIELDS[1:]" in structural_source
    assert "enumerate(" in structural_source and "start=1" in structural_source

    identical_bind_source = ast.get_source_segment(
        source, functions["_scenario_identical_bind"]
    ) or ""
    assert "persisted_payload != duplicate_payload" in identical_bind_source
    assert "_assert_exact_bound_bundle(" in identical_bind_source
    _concurrency_assert_direct_if_predicate(
        functions["_scenario_identical_bind"],
        'statuses != ["DUPLICATE", "PERSISTED"]',
    )
    _concurrency_assert_direct_if_predicate(
        functions["_scenario_identical_bind"],
        "persisted_payload != duplicate_payload",
    )

    divergent = functions["_scenario_divergent_bind"]
    assert "fixture_b" in {argument.arg for argument in divergent.args.args}
    divergent_source = ast.get_source_segment(source, divergent) or ""
    for token in (
        "ready = Event()",
        "release = Event()",
        "_run_concurrently(",
        '"bind-b-exact-racer"',
        '"bind-b-divergent-racer"',
        'fixture_b["bind"], ownership, deadline, None, None, ready',
        "divergent, ownership, deadline, None, ready",
        "_wait_for_blocked(",
        "_observe_domain_locks(",
        'outcomes["bind-b-exact-racer"]["result"].get("status") != "DUPLICATE"',
        '_assert_p0001(\n        outcomes["bind-b-divergent-racer"]',
        "before != after",
    ):
        assert token in divergent_source
    _concurrency_assert_direct_if_predicate(
        divergent,
        'outcomes["bind-b-exact-racer"]["result"].get("status") '
        '!= "DUPLICATE"',
    )

    rollback_source = ast.get_source_segment(
        source, functions["_scenario_bind_rollback"]
    ) or ""
    for token in (
        "ready = Event()",
        "release = Event()",
        "_run_concurrently(",
        '"bind-a-rollback-reader"',
        'futures["bind-a-rollback-reader"].result(',
        'observed[0]["result"].get("state") != "ATTESTED_UNBOUND"',
        "during_snapshots[0] != before",
        "after != before",
    ):
        assert token in rollback_source
    _concurrency_assert_direct_if_predicate(
        functions["_scenario_bind_rollback"],
        'not observed or observed[0]["result"].get("state") '
        '!= "ATTESTED_UNBOUND" or not during_snapshots '
        'or during_snapshots[0] != before',
    )

    for scenario_name in (
        "_scenario_wait_past_expiry_attestor_lock",
        "_scenario_wait_past_expiry_unique_index",
        "_scenario_wait_past_expiry_bind",
    ):
        ttl_source = ast.get_source_segment(source, functions[scenario_name]) or ""
        assert ttl_source.count("_assert_pre_expiry(") == 1
        assert ttl_source.index("_assert_pre_expiry(") < ttl_source.index(
            "_wait_past_expiry("
        )

    oracle = functions["_global_oracle"]
    oracle_checks = [
        node
        for node in ast.walk(oracle)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "counts"
        and len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Dict)
    ]
    assert len(oracle_checks) == 1
    assert ast.literal_eval(oracle_checks[0].comparators[0]) == (
        _CONCURRENCY_GLOBAL_ORACLE
    )
    _concurrency_assert_direct_if_predicate(
        oracle,
        'counts != {"receipts": 3, "attestations": 3, "runs": 2, '
        '"artifacts": 6, "registry": 2}',
    )
    _concurrency_assert_direct_if_predicate(
        oracle,
        'any(int(row[key]) != 0 for key in '
        '("bad_attestation", "bad_run", "bad_artifact", "bad_registry"))',
    )
    oracle_source = ast.get_source_segment(source, oracle) or ""
    assert "no_authority" in oracle_source and "authority_counters" in oracle_source
    for token in (
        "serving_allowed", "promotion_allowed", "latest_pointer_allowed",
        "symlink_allowed", "serving_visible", "model_fit_count",
    ):
        assert token in oracle_source

    submissions = _functional_calls(functions["_run_concurrently"], "executor.submit")
    assert len(submissions) == 1
    assert _functional_dotted_name(submissions[0].args[0]) == "function"
    scenario_worker_references = {
        node.id
        for scenario_name in _CONCURRENCY_SCENARIO_ORDER
        for node in ast.walk(functions[scenario_name])
        if isinstance(node, ast.Name) and node.id in _CONCURRENCY_WORKERS
    }
    assert scenario_worker_references == _CONCURRENCY_WORKERS
    concurrent_source = ast.get_source_segment(
        source, functions["_run_concurrently"]
    ) or ""
    assert "shutdown(wait=False, cancel_futures=True)" in concurrent_source
    assert "release.set()" in concurrent_source
    assert "future.cancel()" in concurrent_source
    assert "barrier.abort()" in concurrent_source
    assert "finally:" in concurrent_source
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        dotted = _functional_dotted_name(call.func)
        leaf = dotted.rsplit(".", 1)[-1] if dotted else None
        receiver = (
            _functional_dotted_name(call.func.value)
            if isinstance(call.func, ast.Attribute)
            else None
        )
        is_synchronization_call = leaf in {"wait", "put", "result"} or (
            leaf == "get"
            and (not call.args or receiver in {"ownership", "completed"})
        )
        if is_synchronization_call:
            assert _concurrency_call_has_timeout(call), dotted
        if dotted and dotted.rsplit(".", 1)[-1] == "join":
            raise AssertionError("unbounded join is forbidden")

    main = functions["main"]
    main_source = ast.get_source_segment(source, main) or ""
    parser_source = ast.get_source_segment(source, functions["_parser"]) or ""
    assert (
        'parser.add_argument("--confirm-disposable-v159-concurrency", '
        'action="store_true")'
        in parser_source
    )
    assert "args.confirm_disposable_v159_concurrency" in main_source
    for token in (
        "_ACK_ENV", "_SENTINEL", "_DISPOSABLE_DATABASE",
        "_reject_ambient_libpq_routing",
        "_parse_complete_dsn", "_target_identity", "_assert_same_target",
        "_seed_v159_role_preconditions", "_orchestrate_migrations",
    ):
        assert token in main_source, token
    output = _functional_local_assignment(main.body, "output")
    assert isinstance(output, ast.Dict)
    assert [ast.literal_eval(key) for key in output.keys] == list(
        _CONCURRENCY_OUTPUT_EXPRESSIONS
    )
    for key, value in zip(output.keys, output.values, strict=True):
        label = ast.literal_eval(key)
        assert _functional_ast_shape(value) == _functional_ast_shape(
            _functional_expression(_CONCURRENCY_OUTPUT_EXPRESSIONS[label])
        )
    assert not {
        "backend_pid", "thread_id", "lock_key", "fixture", "receipt",
        "receipt_projection", "signed_receipt_bytes", "dsn", "exception",
    }.intersection(ast.literal_eval(key) for key in output.keys)

    _functional_single_final_return(
        runner,
        "{'markers': sorted(markers), 'global_counts': counts}",
    )

    safe = functions["_safe_entrypoint"]
    safe_source = ast.get_source_segment(source, safe) or ""
    assert "except ProbeFailure" in safe_source and "except Exception" in safe_source
    assert safe_source.count("_SAFE_FAILURE_MESSAGE") == 2
    print_calls = _functional_calls(tree, "print")
    assert len(print_calls) == 1
    assert _functional_dotted_name(print_calls[0].args[0].func) == "json.dumps"


def test_v159_concurrency_probe_static_ast_contract() -> None:
    _assert_concurrency_probe_contract(_concurrency_probe_source())


@pytest.mark.parametrize(
    "needle,replacement",
    (
        ('markers: set[str] = set()', 'markers: set[str] = set(_REQUIRED_MARKERS)'),
        ('"attestations": 3,', '"attestations": 2,'),
        ('"runs": 2,', '"runs": 1,'),
        ('"postgresql_executed": True', '"postgresql_executed": False'),
        (
            '"partial_deferred_bundle_injection_claimed": True',
            '"partial_deferred_bundle_injection_claimed": False',
        ),
        ('barrier.wait(timeout=_remaining(deadline))', 'barrier.wait()'),
        (
            'ownership.get(timeout=_remaining(deadline))',
            'ownership.get()',
        ),
        (
            'future.result(timeout=_remaining(deadline))',
            'future.result()',
        ),
        (
            'ownership.put(identity, timeout=_remaining(deadline))',
            'ownership.put(identity)',
        ),
        ('shutdown(wait=False, cancel_futures=True)', 'shutdown(wait=True)'),
        ('FROM pg_locks', 'FROM pg_stat_activity'),
        ('clock_timestamp()', 'statement_timestamp()'),
        ('"p_structural_result_hash",', '"removed_structural_result_hash",'),
        ('"same_quantile",', '"removed_same_quantile",'),
        ('_call(connection, _FUNCTIONS["attest"], arguments)', '{}'),
        ('_connect_as_role(', '_shared_connection('),
        ('_adapt(_normalized(run_row))', '_adapt(run_row)'),
        ('_STRUCTURAL_IDENTITY_FIELDS[1:]', '_STRUCTURAL_IDENTITY_FIELDS[1:2]'),
        (
            'statuses != ["DUPLICATE", "PERSISTED"]',
            'False',
        ),
        (
            '_assert_exact_bound_bundle(admin, fixture_b, persisted, readback["result"])',
            'deepcopy((admin, fixture_b, persisted, readback["result"]))',
        ),
        ('_assert_pre_expiry(', 'deepcopy('),
        (
            'divergent, ownership, deadline, None, ready',
            'divergent, ownership, deadline, None, None',
        ),
        ('row["wait_event_type"] == "Lock"', 'True'),
        ('row["state"] == "active"', 'True'),
        ('holder.granted IS TRUE', 'holder.granted IS NOT NULL'),
        ('waiter.granted IS FALSE', 'waiter.granted IS NOT NULL'),
        (
            '"session_user": expected_role,',
            '"session_user": row["session_user"],',
        ),
        (
            '"current_user": expected_role,',
            '"current_user": row["current_user"],',
        ),
        ('_LOCK_TIMEOUT_MS = 24000', '_LOCK_TIMEOUT_MS = 25000'),
        ('SET CONSTRAINTS', 'REMOVED CONSTRAINTS'),
        ('PARTIAL_OR_DIVERGENT', 'PARTIAL_ACCEPTED'),
    ),
)
def test_v159_concurrency_probe_mutations_are_rejected(
    needle: str, replacement: str
) -> None:
    source = _concurrency_probe_source()
    assert needle in source
    weakened = source.replace(needle, replacement)
    with pytest.raises(AssertionError):
        _assert_concurrency_probe_contract(weakened)


@pytest.mark.parametrize(
    "label,needle,replacement",
    (
        (
            "pre_expiry_noop",
            'if row != {"pre_expiry": True}:',
            'if False and row != {"pre_expiry": True}:',
        ),
        (
            "holder_labels_noop",
            'or row["holder_labels"] != expected',
            'or (False and row["holder_labels"] != expected)',
        ),
        (
            "waiter_cardinality_noop",
            'or len(row["waiter_labels"]) != 1',
            'or (False and len(row["waiter_labels"]) != 1)',
        ),
        (
            "duplicate_parity_noop",
            "if persisted_payload != duplicate_payload:",
            "if False and persisted_payload != duplicate_payload:",
        ),
        (
            "exact_p0001_noop",
            'if outcome.get("sqlstate") != "P0001" '
            'or outcome.get("message") != message:',
            'if False and (outcome.get("sqlstate") != "P0001" '
            'or outcome.get("message") != message):',
        ),
        (
            "connection_limits_noop",
            "if rows != [",
            "if False and rows != [",
        ),
        (
            "rollback_invisibility_noop",
            "if (\n        not observed\n",
            "if False and (\n        not observed\n",
        ),
        (
            "global_counts_noop",
            "if counts != {",
            "if False and counts != {",
        ),
        (
            "global_authority_noop",
            'if any(int(row[key]) != 0 for key in (\n'
            '        "bad_attestation", "bad_run", "bad_artifact", "bad_registry"',
            'if False and any(int(row[key]) != 0 for key in (\n'
            '        "bad_attestation", "bad_run", "bad_artifact", "bad_registry"',
        ),
    ),
)
def test_v159_concurrency_probe_composed_boolean_mutants_are_rejected(
    label: str, needle: str, replacement: str
) -> None:
    source = _concurrency_probe_source()
    assert needle in source, label
    weakened = source.replace(needle, replacement)
    with pytest.raises(AssertionError):
        _assert_concurrency_probe_contract(weakened)


@pytest.mark.parametrize(
    "function_name,early_return",
    (
        ("_assert_p0001", "return None"),
        ("_wait_for_blocked", "return {}"),
        ("_observe_domain_locks", "return None"),
        ("_assert_connection_limits", "return None"),
        (
            "_worker_identity",
            "return {'worker': label, 'backend_pid': 0, 'thread_id': 0}",
        ),
        ("_wait_past_expiry", "return None"),
        ("_assert_no_attestation", "return None"),
        ("_wait_event", "return None"),
        ("_assert_pre_expiry", "return None"),
    ),
)
def test_v159_concurrency_probe_helper_early_returns_are_rejected(
    function_name: str, early_return: str
) -> None:
    with pytest.raises(AssertionError):
        weakened = _functional_insert_first_statement(
            _concurrency_probe_source(), function_name, early_return
        )
        _assert_concurrency_probe_contract(weakened)


def test_v159_concurrency_probe_early_runner_return_is_rejected() -> None:
    weakened = _functional_insert_first_statement(
        _concurrency_probe_source(),
        "_run_scenarios",
        "return {'markers': sorted(_REQUIRED_MARKERS), 'global_counts': {}}",
    )
    with pytest.raises(AssertionError):
        _assert_concurrency_probe_contract(weakened)


def test_v159_concurrency_probe_scenario_reordering_is_rejected() -> None:
    source = _concurrency_probe_source()
    first, second = _CONCURRENCY_SCENARIO_ORDER[:2]
    runner_start = source.index("def _run_scenarios(")
    first_call = source.index(f"{first}(", runner_start)
    second_call = source.index(f"{second}(", runner_start)
    first_position = source.rfind("\n", 0, first_call) + 1
    second_position = source.rfind("\n", 0, second_call) + 1
    first_end = source.index("\n", first_call) + 1
    second_end = source.index("\n", second_call) + 1
    first_line = source[first_position:first_end]
    second_line = source[second_position:second_end]
    weakened = (
        source[:first_position]
        + second_line
        + source[first_end:second_position]
        + first_line
        + source[second_end:]
    )
    with pytest.raises(AssertionError):
        _assert_concurrency_probe_contract(weakened)


def _load_concurrency_probe_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "v159_concurrency_probe_under_test", CONCURRENCY_PROBE
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "error_kind,secret_message",
    (
        ("probe", "postgresql://admin:supersecret@db.example/test"),
        ("runtime", "password=hunter2 passfile=/tmp/private.pgpass"),
        ("value", "host=db user=admin sslkey=/tmp/client-secret.key"),
    ),
)
def test_v159_concurrency_probe_safe_entrypoint_redacts_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error_kind: str,
    secret_message: str,
) -> None:
    module = _load_concurrency_probe_module()
    if error_kind == "probe":
        error = module.ProbeFailure(secret_message)  # type: ignore[attr-defined]
    elif error_kind == "runtime":
        error = RuntimeError(secret_message)
    else:
        error = ValueError(secret_message)

    def fail_safely(_argv: object = None) -> int:
        raise error

    monkeypatch.setattr(module, "main", fail_safely)
    assert module._safe_entrypoint(()) == 1  # type: ignore[attr-defined]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "V159 concurrency disposable probe failed safely\n"
    assert secret_message not in captured.err
    for forbidden in (
        "postgresql://", "supersecret", "hunter2", "passfile", "sslkey",
        "Traceback", "RuntimeError", "ValueError",
    ):
        assert forbidden not in captured.err


def test_v159_concurrency_probe_parser_error_redacts_unknown_secret(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_concurrency_probe_module()
    secret = "postgresql://admin:parser-secret@db/private?password=hunter2"
    assert module._safe_entrypoint(("--unknown", secret)) == 1  # type: ignore[attr-defined]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "V159 concurrency disposable probe failed safely\n"
    assert secret not in captured.err
    assert "usage:" not in captured.err and "Traceback" not in captured.err


def _load_functional_probe_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "v159_functional_probe_under_test", FUNCTIONAL_PROBE
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "error_kind,secret_message",
    (
        ("probe", "postgresql://admin:supersecret@db.example/test"),
        ("runtime", "password=hunter2 passfile=/tmp/private.pgpass"),
        ("value", "host=db user=admin sslkey=/tmp/client-secret.key"),
    ),
)
def test_v159_functional_probe_safe_entrypoint_redacts_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error_kind: str,
    secret_message: str,
) -> None:
    module = _load_functional_probe_module()
    if error_kind == "probe":
        error = module.ProbeFailure(secret_message)  # type: ignore[attr-defined]
    elif error_kind == "runtime":
        error = RuntimeError(secret_message)
    else:
        error = ValueError(secret_message)

    def fail_safely(_argv: object = None) -> int:
        raise error

    monkeypatch.setattr(module, "main", fail_safely)
    assert module._safe_entrypoint(()) == 1  # type: ignore[attr-defined]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "V159 durable-fit disposable probe failed safely\n"
    assert secret_message not in captured.err
    for forbidden in (
        "postgresql://", "supersecret", "hunter2", "passfile", "sslkey",
        "Traceback", "RuntimeError", "ValueError",
    ):
        assert forbidden not in captured.err


def test_v159_functional_probe_parser_error_redacts_unknown_secret(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_functional_probe_module()
    secret = "postgresql://admin:parser-secret@db/private?password=hunter2"
    assert module._safe_entrypoint(("--unknown", secret)) == 1  # type: ignore[attr-defined]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "V159 durable-fit disposable probe failed safely\n"
    assert secret not in captured.err
    assert "usage:" not in captured.err and "Traceback" not in captured.err


def test_v159_declares_all_source_only_surfaces() -> None:
    assert V159.exists(), f"V159 migration is missing: {V159}"
    assert FUNCTIONAL_PROBE.exists(), f"functional probe is missing: {FUNCTIONAL_PROBE}"
    if not CONCURRENCY_PROBE.exists():
        functional = FUNCTIONAL_PROBE.read_text(encoding="utf-8")
        assert '"partial_deferred_bundle_injection_claimed": False' in functional
        assert '"V159_CONCURRENCY_PROBE"' in functional

    sql = V159.read_text(encoding="utf-8")
    executable_sql = re.sub(r"(?m)^\s*--[^\n]*(?:\n|$)", "", sql)
    assert executable_sql.lstrip().startswith("BEGIN;")
    assert executable_sql.rstrip().endswith("COMMIT;")
    assert "learning.alr_challenger_fit_attestations" in sql


def _assert_v159_ci_trading_ai_compatibility_database(ci: str) -> None:
    schema_start = ci.index("  schema-contract:")
    schema_end = ci.index("\n  # stock_etf", schema_start)
    schema_job = ci[schema_start:schema_end]
    setup_start = schema_job.index("- name: Create isolated V159 probe databases")
    first_baseline = schema_job.index(
        "- name: Prepare V157 baseline for V159 functional probe"
    )
    full_tree = schema_job.index("- name: Schema-consumer contract test (cargo)")
    setup = schema_job[setup_start:first_baseline]
    owner_check = (
        "pg_catalog.pg_get_userbyid(d.datdba) = 'contract_user'"
    )
    create = "createdb --host 127.0.0.1 --username contract_user " \
        "--owner contract_user trading_ai"
    assert "if ! PGPASSWORD=contract_pass psql" in setup
    assert "d.datname = 'trading_ai'" in setup
    assert owner_check in setup
    assert create in " ".join(setup.split())
    assert setup.index("d.datname = 'trading_ai'") < setup.index("createdb")
    assert setup.count("createdb") == 1
    assert setup_start < first_baseline < full_tree


def test_v159_ci_provisions_v006_trading_ai_compatibility_database() -> None:
    _assert_v159_ci_trading_ai_compatibility_database(
        CI_WORKFLOW.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    "needle,replacement",
    (
        ("d.datname = 'trading_ai'", "d.datname = 'wrong_db'"),
        (
            "pg_catalog.pg_get_userbyid(d.datdba) = 'contract_user'",
            "pg_catalog.pg_get_userbyid(d.datdba) = 'wrong_owner'",
        ),
        (
            "--owner contract_user trading_ai",
            "--owner wrong_owner trading_ai",
        ),
    ),
)
def test_v159_ci_trading_ai_compatibility_mutations_are_rejected(
    needle: str, replacement: str
) -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    _assert_v159_ci_trading_ai_compatibility_database(ci)
    assert needle in ci
    with pytest.raises(AssertionError):
        _assert_v159_ci_trading_ai_compatibility_database(
            ci.replace(needle, replacement, 1)
        )
