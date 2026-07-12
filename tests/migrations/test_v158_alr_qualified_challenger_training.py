"""Static source contract for V158 qualified challenger training persistence.

The migration is intentionally source-only until a separate disposable-PG and
operator apply gate.  These tests reject authority widening, partial model
bundles, weak replay arbitration, and unsafe SECURITY DEFINER posture without
contacting PostgreSQL.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest


SRV_ROOT = Path(__file__).resolve().parents[2]
V158 = SRV_ROOT / "sql/migrations/V158__alr_qualified_challenger_training.sql"
SCHEMA_CONTRACT = SRV_ROOT / "rust/openclaw_engine/tests/schema_contract_test.rs"
FUNCTIONAL_PROBE = (
    SRV_ROOT
    / "program_code/ml_training/tests/integration/"
    "alr_challenger_training_isolated_pg.py"
)
CONCURRENCY_PROBE = (
    SRV_ROOT
    / "program_code/ml_training/tests/integration/"
    "alr_challenger_training_concurrency_isolated_pg.py"
)
CI_WORKFLOW = SRV_ROOT / ".github/workflows/ci.yml"
_CHECK_SOURCE_SHA256 = {
    "alr_qualified_receipts_hashes_check": "2207cdecf0a4b7e187ec8f523215f17bdfaa56e52ae920bf79569ae7ed31f4b4",
    "alr_qualified_receipts_status_check": "5be717b46cea1bd93c9549977feabf52f1e9117be5facbb3e964fd936e27683c",
    "alr_qualified_receipts_payload_check": "f37c055da9c4d38a0a55a353cb134653befe734afcb97ceae8ee2aa5b69c9ebe",
    "alr_qualified_receipts_no_authority_check": "9eedcea8a82b0860fc465defcd7d913f3c2008cfcea37b2fd2aab21c8e09c86d",
    "alr_qualified_receipts_counters_check": "dafb690e5e54fcc52d78d1c7128e636a09af1a25bdd1415de81f4fecf4334bf0",
    "alr_challenger_runs_hashes_check": "489c783a7062debfba76373ac5c9daa1e804510368354fb81d4905b67a2e0293",
    "alr_challenger_runs_model_schema_check": "744dd8f6d358e56e580593a6dbece9af8ac61c274d351da830f9aa67cf81428f",
    "alr_challenger_runs_state_check": "1506e6af360cf5ca2783cc97dc07255b05ed192090272312fa9d0e3ea51eef0b",
    "alr_challenger_runs_payload_check": "b5ca13dfea90fa182b68534516da69dda041533b89ad20ca90562db686bf7d0e",
    "alr_challenger_runs_no_authority_check": "e0a1ca76f133e0a2b4fc01ce3d5bcf7b5cb9dce835d6acaa7a7df991c4d1f25b",
    "alr_challenger_runs_counters_check": "83e4456e1b8483ac766017a203e3588f82a30b9a2b89ecc5f714c76ab7d190bd",
    "alr_challenger_artifacts_hashes_check": "173facbaa0390aea76becd71aab0cc1852fa6ff869e0fd6a7634bdfe84b39cf5",
    "alr_challenger_artifacts_shape_check": "e79ef56e2e91aa0e9ab39f98557b1295e0c786f75daf92bb026d04a01ffddaab",
    "alr_challenger_registry_hashes_check": "e97a154f9bea87eb5d844d85129433437e1053adffb93f728d68a20e747b2b72",
    "alr_challenger_registry_state_check": "63b5ee397a5c6d0ae5381f5424d1d90c97c5f725eb5b1e3bdd877f82be267dec",
    "alr_challenger_registry_payload_check": "b495518ca89cd6a38c99ddfdb5714c5f586c08947e88e2f9b2ac1786795784f8",
}


def _sql() -> str:
    assert V158.exists(), f"V158 migration is missing: {V158}"
    return V158.read_text(encoding="utf-8")


def _assert_top_level_case_guard_is_parenthesized(sql: str) -> None:
    safe = (
        "<> (CASE WHEN v_spec.caller_access THEN 1 ELSE 0 END) THEN"
    )
    assert safe in sql
    assert "<> CASE WHEN v_spec.caller_access THEN 1 ELSE 0 END THEN" not in sql


def test_v158_plpgsql_if_does_not_terminate_at_nested_case_then() -> None:
    _assert_top_level_case_guard_is_parenthesized(_sql())


def test_v158_unparenthesized_top_level_case_guard_mutation_is_rejected() -> None:
    sql = _sql()
    safe = "<> (CASE WHEN v_spec.caller_access THEN 1 ELSE 0 END) THEN"
    assert safe in sql
    with pytest.raises(AssertionError):
        _assert_top_level_case_guard_is_parenthesized(
            sql.replace(
                safe,
                "<> CASE WHEN v_spec.caller_access THEN 1 ELSE 0 END THEN",
                1,
            )
        )


def _code(sql: str | None = None) -> str:
    value = _sql() if sql is None else sql
    return "\n".join(re.sub(r"--.*$", "", line) for line in value.splitlines())


def _function_body(sql: str, name: str, next_marker: str) -> str:
    start = sql.index(f"CREATE OR REPLACE FUNCTION learning.{name}")
    end = sql.index(next_marker, start)
    return sql[start:end]


def _dollar_body(sql: str, tag: str) -> str:
    match = re.search(rf"AS \${tag}\$(.*?)\${tag}\$;", sql, re.DOTALL)
    assert match, tag
    return match.group(1)


def _rust_code(value: str) -> str:
    return "\n".join(re.sub(r"//.*$", "", line) for line in value.splitlines())


def _ci_code(value: str) -> str:
    return "\n".join(re.sub(r"#.*$", "", line) for line in value.splitlines())


def _python_function(value: str, name: str, next_name: str) -> str:
    start = value.index(f"def {name}(")
    end = value.index(f"def {next_name}(", start)
    return value[start:end]


def _python_guard(function: str, condition: str) -> ast.If:
    expected = ast.dump(ast.parse(condition, mode="eval").body)
    matches = [
        node
        for node in ast.walk(ast.parse(function))
        if isinstance(node, ast.If) and ast.dump(node.test) == expected
    ]
    assert len(matches) == 1
    return matches[0]


def _assert_guard_raises_probe_failure(function: str, condition: str) -> None:
    guard = _python_guard(function, condition)
    assert len(guard.body) == 1
    statement = guard.body[0]
    assert (
        isinstance(statement, ast.Raise)
        and isinstance(statement.exc, ast.Call)
        and isinstance(statement.exc.func, ast.Name)
        and statement.exc.func.id == "ProbeFailure"
    )
    for handler in (
        node for node in ast.walk(ast.parse(function)) if isinstance(node, ast.ExceptHandler)
    ):
        assert handler.type is not None
        caught = {
            node.id
            for node in ast.walk(handler.type)
            if isinstance(node, ast.Name)
        } | {
            node.attr
            for node in ast.walk(handler.type)
            if isinstance(node, ast.Attribute)
        }
        assert not caught.intersection({"ProbeFailure", "Exception", "BaseException"})


def _replace_guard_body_with_pass(
    source: str, function_name: str, next_name: str, condition: str
) -> str:
    function = _python_function(source, function_name, next_name)
    guard = _python_guard(function, condition)
    assert guard.body
    lines = function.splitlines(keepends=True)
    start = guard.body[0].lineno - 1
    end = guard.body[-1].end_lineno
    lines[start:end] = [f"{' ' * (guard.col_offset + 4)}pass\n"]
    weakened_function = "".join(lines)
    weakened = source.replace(function, weakened_function, 1)
    compile(weakened, "<mutated-probe>", "exec")
    return weakened


def _prepend_guard_statement(
    source: str,
    function_name: str,
    next_name: str,
    condition: str,
    statement: str,
) -> str:
    function = _python_function(source, function_name, next_name)
    guard = _python_guard(function, condition)
    assert guard.body
    lines = function.splitlines(keepends=True)
    start = guard.body[0].lineno - 1
    lines.insert(start, f"{' ' * (guard.col_offset + 4)}{statement}\n")
    weakened_function = "".join(lines)
    weakened = source.replace(function, weakened_function, 1)
    compile(weakened, "<mutated-probe>", "exec")
    return weakened


def _prepend_function_statement(
    source: str, function_name: str, next_name: str, statement: str
) -> str:
    function = _python_function(source, function_name, next_name)
    parsed = ast.parse(function)
    definition = parsed.body[0]
    assert isinstance(definition, ast.FunctionDef) and definition.body
    lines = function.splitlines(keepends=True)
    lines.insert(definition.body[0].lineno - 1, f"    {statement}\n")
    weakened_function = "".join(lines)
    weakened = source.replace(function, weakened_function, 1)
    compile(weakened, "<mutated-negative-probe>", "exec")
    return weakened


def _assert_probe_safety_contracts(source: str, apply_function: str) -> None:
    dsn_parser = _python_function(source, "_parse_complete_dsn", "_migration_bytes")
    credential_conditions = (
        "bool(password) == bool(passfile_value)",
        "not passfile.is_absolute()",
        "stat.S_ISLNK(passfile_metadata.st_mode)",
        "not stat.S_ISREG(passfile_metadata.st_mode)",
        "resolved_passfile == default_passfile",
        "passfile_metadata.st_uid != os.geteuid()",
        "stat.S_IMODE(passfile_metadata.st_mode) != 0o600",
    )
    assert 'default_passfile = (Path.home() / ".pgpass").resolve(strict=False)' in (
        dsn_parser
    )
    for condition in credential_conditions:
        guard = f"if {condition}:"
        assert guard in dsn_parser
        assert dsn_parser.index(guard) < dsn_parser.index("return parsed")
        _assert_guard_raises_probe_failure(dsn_parser, condition)

    apply = _python_function(source, apply_function, "_target_identity")
    target_condition = "_target_identity(connection) != dict(expected_target)"
    target_guard = f"if {target_condition}:"
    ddl_execute = 'cursor.execute(migration.decode("utf-8"))'
    assert apply.count(target_guard) == 1
    assert apply.count(ddl_execute) == 1
    assert apply.index(target_guard) < apply.index(ddl_execute)
    _assert_guard_raises_probe_failure(apply, target_condition)


def _assert_functional_negative_contract(source: str) -> None:
    generic = _python_function(
        source,
        "_assert_generic_function_execute_denied",
        "_assert_session_replication_role_denied",
    )
    assert "for role in _GENERIC_ROLES:" in generic
    assert "_connect_as_generic(admin_parameters, expected_target, role)" in generic
    assert '_call(connection, _FUNCTIONS["receipt"], receipt_arguments)' in generic
    assert 'exc.pgcode != "42501"' in generic
    assert "unexpectedly executed a V158 function" in generic
    generic_definition = ast.parse(generic).body[0]
    assert isinstance(generic_definition, ast.FunctionDef)
    assert not any(isinstance(node, ast.Return) for node in ast.walk(generic_definition))

    replication = _python_function(
        source,
        "_assert_session_replication_role_denied",
        "_seed_projection_artifact",
    )
    assert "connections = [caller]" in replication
    assert "for role in _GENERIC_ROLES:" in replication
    assert "_connect_as_generic(admin_parameters, expected_target, role)" in replication
    assert 'cursor.execute("SET LOCAL session_replication_role = \'replica\'")' in (
        replication
    )
    assert 'exc.pgcode != "42501"' in replication
    assert "non-privileged V158 identity set session_replication_role" in replication
    replication_definition = ast.parse(replication).body[0]
    assert isinstance(replication_definition, ast.FunctionDef)
    assert not any(
        isinstance(node, ast.Return) for node in ast.walk(replication_definition)
    )

    deferred = _python_function(
        source, "_assert_deferred_completeness_rejected", "_run_calls"
    )
    for token in (
        '("partial_trio", "SET_CONSTRAINTS")',
        '("schema_mismatch", "COMMIT")',
        "V158 complete result invariant: exact q10/q50/q90 bundle required",
        "DELETE FROM learning.alr_challenger_model_artifacts",
        "UPDATE learning.alr_challenger_model_artifacts",
        "SET feature_schema_hash = %s",
        "DELETE FROM learning.alr_challenger_registry",
        "GRANT INSERT ON TABLE learning.alr_challenger_registry",
        "SET SESSION AUTHORIZATION alr_challenger_trainer_caller",
        "INSERT INTO learning.alr_challenger_registry",
        'if actual_phase == "SET_CONSTRAINTS":',
        'elif actual_phase == "COMMIT":',
        "setup failed before {boundary}",
        "expected_boundaries = dict(cases)",
        "connection.commit()",
        "except psycopg2.Error as exc:",
        'exc.pgcode != "P0001"',
        "observed_boundaries[case] = actual_phase",
        "if observed_boundaries != expected_boundaries:",
        "deferred boundary coverage incomplete",
    ):
        assert token in deferred
    assert deferred.count("except psycopg2.Error as exc:") == 2
    deferred_definition = ast.parse(deferred).body[0]
    assert isinstance(deferred_definition, ast.FunctionDef)
    assert not any(
        isinstance(node, (ast.Break, ast.Continue))
        for node in ast.walk(deferred_definition)
    )
    deferred_returns = [
        node for node in ast.walk(deferred_definition) if isinstance(node, ast.Return)
    ]
    assert len(deferred_returns) == 1
    assert deferred_definition.body[-1] is deferred_returns[0]
    assert isinstance(deferred_returns[0].value, ast.Name)
    assert deferred_returns[0].value.id == "observed_boundaries"
    target_check = "_target_identity(connection) != dict(expected_target)"
    set_deferred = 'f"SET CONSTRAINTS {_NAMED_COMPLETENESS_CONSTRAINTS} DEFERRED"'
    replica = 'cursor.execute("SET LOCAL session_replication_role = \'replica\'")'
    origin = 'cursor.execute("SET LOCAL session_replication_role = \'origin\'")'
    grant = "GRANT INSERT ON TABLE learning.alr_challenger_registry"
    authorization = "SET SESSION AUTHORIZATION alr_challenger_trainer_caller"
    registry_insert = "INSERT INTO learning.alr_challenger_registry"
    immediate = 'f"SET CONSTRAINTS {_NAMED_COMPLETENESS_CONSTRAINTS} "'
    assert deferred.index(target_check) < deferred.index(set_deferred)
    assert deferred.index(set_deferred) < deferred.index(replica)
    assert deferred.index(replica) < deferred.index(origin)
    assert deferred.index(origin) < deferred.index(grant)
    assert deferred.index(grant) < deferred.index(authorization)
    assert deferred.index(authorization) < deferred.index(registry_insert)
    assert deferred.index(registry_insert) < deferred.index(immediate)

    main_start = source.index("def main(")
    main_end = source.index('if __name__ == "__main__":', main_start)
    main = source[main_start:main_end]
    assert main.count("_assert_generic_function_execute_denied(") == 1
    assert main.count("_assert_session_replication_role_denied(") == 1
    assert main.count("_assert_deferred_completeness_rejected(") == 1
    assert main.count("_assert_direct_table_access_denied(caller)") == 2
    assert main.index("_assert_generic_function_execute_denied(") < main.index(
        "_run_calls(caller, fixture)"
    )
    assert main.index("_run_calls(caller, fixture)") < main.index(
        "_assert_deferred_completeness_rejected("
    )
    assert main.index("_assert_deferred_completeness_rejected(") < main.index(
        "_apply_migration(admin_parameters, migration, expected_target, 2)"
    )
    restoration = (
        "if _read_calls(caller, fixture) != readback:\n"
        '            raise ProbeFailure("rollback-only negative checks changed '
        'persisted readback")'
    )
    assert restoration in main
    exact_boundary_result = (
        "if deferred_boundaries != {\n"
        '            "partial_trio": "SET_CONSTRAINTS",\n'
        '            "schema_mismatch": "COMMIT",\n'
        "        }:"
    )
    assert exact_boundary_result in main


def _assert_fail_closed_catalog_guards(sql: str) -> None:
    code = _code(sql)
    assert "pg_get_expr(a.conbin,a.conrelid,FALSE) AS actual_expr" in code
    assert "v_actual.actual_expr IS DISTINCT FROM v_actual.expected_expr" in code
    assert code.count("c.conrelid=v_spec.relation_name::regclass") >= 2
    assert code.count("t.tgrelid=v_spec.relation_name::regclass") == 2
    assert code.count("t.tgfoid=v_spec.function_name::regprocedure") == 2
    assert len(re.findall(r"md5\(p[.]prosrc\)\s*<>\s*v_spec[.]body_md5", code)) == 2
    assert "a.grantee NOT IN (v_schema_owner, v_writer_oid)" in code
    assert "a.grantee NOT IN (v_writer_oid,v_caller_oid)" in code
    assert "writer owns objects beyond six fixed functions" in code
    assert "pg_shdepend" in code and "deptype='o'" in code
    assert code.count("c.relpersistence='p'") == 3 and "relhasrules" in code
    assert "pg_policy" in code and "indisexclusion" in code
    assert code.count("t.tgattr::TEXT=''") == 2
    assert "session_user<>current_user" in code
    assert "a.is_grantable" in code and "a.grantor<>" in code
    assert "p_canonical_payload ?& ARRAY[" in code
    assert "p_canonical_payload - ARRAY[" in code
    assert "training_rows')::BIGINT > 2147483647" in code
    assert code.count("rolname IN ('trading_ai', 'alr_shadow')") == 3
    assert "pg_has_role(generic.oid, reachable.oid, 'SET')" in code
    assert (
        "V158 Guard C FAIL: generic role has session_replication_role SET authority"
        in code
    )
    for field, expected in (
        ("schema_version", "alr_qualified_training_receipt_v1"),
        ("projection_artifact_kind", "learning_target"),
        ("receipt_status", "QUALIFIED_INPUT_PERSISTED"),
    ):
        assert re.search(
            rf"p_canonical_payload->>'{field}'\s+IS DISTINCT FROM\s+"
            rf"'{expected}'",
            code,
        )
    _assert_check_source_and_catalog_twins(sql)
    _assert_function_body_contracts(sql)


def _assert_check_source_and_catalog_twins(sql: str) -> None:
    names = re.findall(r"CONSTRAINT\s+(alr_[a-z0-9_]+_check)\s+CHECK", sql)
    assert set(names) == set(_CHECK_SOURCE_SHA256)
    for name in names:
        start = sql.index(f"CONSTRAINT {name}")
        boundaries = [
            position
            for position in (
                sql.find("\n    CONSTRAINT ", start + 1),
                sql.find("\n);", start + 1),
            )
            if position >= 0
        ]
        assert boundaries
        block = sql[start : min(boundaries)]
        digest = hashlib.sha256(block.encode("utf-8")).hexdigest()
        assert digest == _CHECK_SOURCE_SHA256[name], name
    expected = set(re.findall(r"ADD CONSTRAINT\s+(expected_[a-z0-9_]+)\s+CHECK", sql))
    assert len(expected) == 16
    for name in expected:
        assert sql.count(name) == 2, name


def _assert_function_body_contracts(sql: str) -> None:
    tags = (
        "v158_receipt_writer",
        "v158_result_writer",
        "v158_receipt_reader",
        "v158_result_reader",
        "v158_complete_trigger",
        "v158_immutable_trigger",
    )
    for tag in tags:
        body = _dollar_body(sql, tag)
        digest = hashlib.md5(body.encode("utf-8")).hexdigest()  # noqa: S324
        assert sql.count(digest) == 2, tag
        assert "current_user <> 'alr_challenger_writer'" in body
        assert "current_setting('session_replication_role') <> 'origin'" in body
        assert "EXECUTE " not in body
    for tag in tags[:-1]:
        assert "session_user <> 'alr_challenger_trainer_caller'" in _dollar_body(
            sql, tag
        )


def test_v158_is_bounded_forward_only_and_guarded() -> None:
    sql = _sql()
    code = _code(sql)
    assert len(sql.splitlines()) < 2000
    assert code.lstrip().startswith("BEGIN;")
    assert "SET LOCAL search_path = pg_catalog, pg_temp" in code
    for guard in ("V158 Guard A", "V158 Guard B", "V158 Guard C"):
        assert guard in sql
        assert f"{guard} FAIL" in code
    assert code.rstrip().endswith("COMMIT;")

    forbidden = (
        r"\bCREATE\s+ROLE\b",
        r"\bALTER\s+ROLE\b",
        r"\bCREATE\s+USER\b",
        r"\bPASSWORD\b",
        r"\bEXECUTE\s+FORMAT\b",
        r"\bEXECUTE\s+[^;]*\|\|",
        r"learning[.]model_registry",
        r"trading[.]",
        r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b",
        r"\bCREATE\s+SEQUENCE\b",
    )
    for pattern in forbidden:
        assert re.search(pattern, code, re.IGNORECASE) is None, pattern
    for frozen in (
        "V152__",
        "V153__",
        "V157__",
        "run_training_pipeline",
        "transition_canary_status",
        "onnx_current",
    ):
        assert frozen not in code


def test_v158_declares_exact_four_append_only_tables_and_lineage() -> None:
    code = _code()
    tables = (
        "alr_qualified_training_receipts",
        "alr_challenger_training_runs",
        "alr_challenger_model_artifacts",
        "alr_challenger_registry",
    )
    assert code.count("CREATE TABLE IF NOT EXISTS learning.") == 4
    for table in tables:
        assert f"CREATE TABLE IF NOT EXISTS learning.{table}" in code

    for column in (
        "durable_receipt_hash TEXT NOT NULL",
        "training_key_hash TEXT NOT NULL",
        "training_run_hash TEXT NOT NULL",
        "model_artifact_set_hash TEXT NOT NULL",
        "actual_feature_schema_hash TEXT NOT NULL",
        "model_schema_version TEXT NOT NULL",
        "artifact_hash TEXT NOT NULL",
        "quantile TEXT NOT NULL",
        "registry_status TEXT NOT NULL",
    ):
        assert column in code

    required_constraints = (
        "alr_qualified_receipts_receipt_training_uniq",
        "alr_challenger_runs_receipt_training_fk",
        "alr_challenger_runs_result_lineage_uniq",
        "alr_challenger_runs_artifact_lineage_uniq",
        "alr_challenger_artifacts_run_lineage_fk",
        "alr_challenger_registry_run_lineage_fk",
        "alr_challenger_artifacts_run_quantile_uniq",
    )
    for name in required_constraints:
        assert f"CONSTRAINT {name}" in code
    assert code.count("NOT DEFERRABLE") >= len(required_constraints)
    assert "FOREIGN KEY (durable_receipt_hash, training_key_hash)" in code
    assert re.search(
        r"FOREIGN KEY\s*\(\s*training_run_hash,\s*training_key_hash,\s*"
        r"model_artifact_set_hash,\s*feature_schema_hash,\s*model_schema_version\s*\)",
        code,
    )


def test_v158_hash_status_and_authority_constants_are_database_owned() -> None:
    code = _code()
    for value in (
        "QUALIFIED_INPUT_PERSISTED",
        "TRAINING_PERFORMED",
        "NOT_SERVING",
        "q10",
        "q50",
        "q90",
        "onnx",
    ):
        assert value in code
    assert "model_training_performed BOOLEAN NOT NULL" in code
    assert "model_training_performed IS TRUE" in code
    for denied in (
        "serving_allowed IS FALSE",
        "promotion_allowed IS FALSE",
        "latest_pointer_allowed IS FALSE",
        "symlink_allowed IS FALSE",
        "symlink_created IS FALSE",
        "serving_visible IS FALSE",
    ):
        assert denied in code
    assert "model_fit_count" in code
    assert "order_or_probe_count" in code
    assert "exchange_contact_count" in code

    canonical = "q10=%s\\nq50=%s\\nq90=%s\\n"
    assert canonical in code
    assert "public.digest" in code
    assert "pg_catalog.convert_to" in code
    assert re.search(r"(?<!public[.])\bdigest[(]", code) is None


def test_v158_exposes_only_fixed_security_definer_functions() -> None:
    code = _code()
    public_functions = (
        "persist_alr_qualified_training_receipt_v1",
        "persist_alr_challenger_training_result_v1",
        "read_alr_qualified_training_receipt_v1",
        "read_alr_challenger_training_result_v1",
    )
    for name in public_functions:
        assert f"CREATE OR REPLACE FUNCTION learning.{name}" in code
        assert f"ALTER FUNCTION learning.{name}" in code
    assert code.count("SECURITY DEFINER") >= 6
    assert code.count("SET search_path = pg_catalog, pg_temp") >= 6
    assert "session_user <> 'alr_challenger_trainer_caller'" in code
    assert "current_user <> 'alr_challenger_writer'" in code
    assert "current_setting('session_replication_role') <> 'origin'" in code
    assert "to_regprocedure" in code
    assert "md5(p.prosrc)" in code
    assert "prorettype" in code
    assert "provariadic" in code
    assert "prosecdef" in code
    assert "proconfig" in code
    assert "proname" in code and "pronargs" in code


def test_v158_result_writer_is_atomic_exact_trio_and_conflict_closed() -> None:
    code = _code()
    body = _function_body(
        code,
        "persist_alr_challenger_training_result_v1",
        "CREATE OR REPLACE FUNCTION learning.read_alr_qualified_training_receipt_v1",
    )
    assert "SET CONSTRAINTS" in body
    assert "SET CONSTRAINTS ALL" not in body
    for trigger in (
        "learning.alr_challenger_run_complete_ct_v1",
        "learning.alr_challenger_artifact_complete_ct_v1",
        "learning.alr_challenger_registry_complete_ct_v1",
    ):
        assert trigger in body
    assert "DEFERRED" in body
    assert "IMMEDIATE" in body
    assert "ON CONFLICT DO NOTHING" in body
    assert "RETURNING" in body
    assert "IF NOT FOUND" in body or "IF v_inserted" in body
    assert "FOR UPDATE" not in body
    assert "FOR SHARE" not in body
    assert body.count("INSERT INTO learning.alr_challenger_model_artifacts") == 3
    assert body.count("INSERT INTO learning.alr_challenger_training_runs") == 1
    assert body.count("INSERT INTO learning.alr_challenger_registry") == 1
    assert "artifact hashes must be distinct" in body
    assert "artifact set hash mismatch" in body
    assert "replay conflict" in body


def test_v158_constraint_and_immutability_triggers_are_exact() -> None:
    code = _code()
    for name in (
        "alr_challenger_run_complete_ct_v1",
        "alr_challenger_artifact_complete_ct_v1",
        "alr_challenger_registry_complete_ct_v1",
    ):
        assert f"CREATE CONSTRAINT TRIGGER {name}" in code
    assert code.count("DEFERRABLE INITIALLY DEFERRED") == 3
    assert code.count("FOR EACH ROW") >= 7
    assert "v_artifact_count <> 3" in code
    assert "v_quantile_count <> 3" in code
    assert "v_registry_count <> 1" in code
    assert "q10=%s\\nq50=%s\\nq90=%s\\n" in code
    for table in (
        "alr_qualified_training_receipts",
        "alr_challenger_training_runs",
        "alr_challenger_model_artifacts",
        "alr_challenger_registry",
    ):
        assert f"alr_v158_immutable_{table}_trg" in code
    assert "TG_OP IN ('UPDATE', 'DELETE')" in code


def test_v158_acl_surface_is_writer_and_caller_only() -> None:
    code = _code()
    for role in ("PUBLIC", "trading_ai", "alr_shadow"):
        assert role in code
    assert "GRANT SELECT, INSERT ON TABLE" in code
    assert "TO alr_challenger_writer" in code
    assert "GRANT EXECUTE ON FUNCTION" in code
    assert "TO alr_challenger_trainer_caller" in code
    assert "GRANT USAGE ON SCHEMA learning TO alr_challenger_trainer_caller" in code
    assert "GRANT USAGE ON SCHEMA public TO alr_challenger_writer" in code
    assert "public.digest(bytea, text) TO alr_challenger_writer" in code
    assert "GRANT SELECT ON TABLE learning.alr_artifact_nodes" in code
    assert "artifact_kind = 'learning_target'" in code
    assert "GRANT UPDATE" not in code
    assert "GRANT DELETE" not in code
    assert "GRANT TRUNCATE" not in code
    assert "GRANT CREATE ON SCHEMA" not in code
    assert "pg_auth_members" in code
    assert "pg_parameter_acl" in code
    assert "rolconnlimit" in code
    assert "rolbypassrls" in code
    assert code.count(
        "REVOKE SET ON PARAMETER session_replication_role FROM trading_ai"
    ) == 1
    assert code.count(
        "REVOKE SET ON PARAMETER session_replication_role FROM alr_shadow"
    ) == 1
    assert "V158 Guard C FAIL: generic role has session_replication_role SET authority" in code


def test_v158_functional_probe_names_all_mandatory_negative_boundaries() -> None:
    source = FUNCTIONAL_PROBE.read_text(encoding="utf-8")
    for token in (
        "_assert_generic_function_execute_denied",
        "_assert_session_replication_role_denied",
        "_assert_deferred_completeness_rejected",
        "SET SESSION AUTHORIZATION trading_ai",
        "SET SESSION AUTHORIZATION alr_shadow",
        "SET LOCAL session_replication_role = 'replica'",
        "SET LOCAL session_replication_role = 'origin'",
        "V158 complete result invariant: exact q10/q50/q90 bundle required",
        "SET CONSTRAINTS",
        "IMMEDIATE",
        "connection.commit()",
        '"partial_trio_boundary": "SET_CONSTRAINTS"',
        '"schema_mismatch_boundary": "COMMIT"',
    ):
        assert token in source
    _assert_functional_negative_contract(source)


@pytest.mark.parametrize(
    "needle,replacement",
    (
        (
            '("partial_trio", "SET_CONSTRAINTS")',
            '("partial_trio", "COMMIT")',
        ),
        (
            "V158 complete result invariant: exact q10/q50/q90 bundle required",
            "weakened completeness message",
        ),
        (
            'if exc.pgcode != "P0001" or primary != expected_message:',
            "if False:",
        ),
        (
            "SET SESSION AUTHORIZATION alr_challenger_trainer_caller",
            "removed caller authorization",
        ),
        (
            "_assert_generic_function_execute_denied(\n"
            "            admin_parameters, expected_target, fixture[\"receipt\"]\n"
            "        )",
            "removed_generic_execute_negative = True",
        ),
        (
            "_assert_session_replication_role_denied(\n"
            "            caller, admin_parameters, expected_target\n"
            "        )",
            "removed_replication_negative = True",
        ),
        (
            "if _read_calls(caller, fixture) != readback:\n"
            "            raise ProbeFailure(\"rollback-only negative checks changed "
            "persisted readback\")",
            "removed_readback_restoration = True",
        ),
        (
            "                observed_boundaries[case] = actual_phase",
            "                observed_boundaries[case] = actual_phase\n"
            "                break",
        ),
    ),
)
def test_v158_mandatory_negative_contract_mutations_are_rejected(
    needle: str, replacement: str
) -> None:
    source = FUNCTIONAL_PROBE.read_text(encoding="utf-8")
    assert needle in source
    weakened = source.replace(needle, replacement, 1)
    with pytest.raises(AssertionError):
        _assert_functional_negative_contract(weakened)


@pytest.mark.parametrize(
    "function_name,next_name,statement",
    (
        (
            "_assert_generic_function_execute_denied",
            "_assert_session_replication_role_denied",
            "return None",
        ),
        (
            "_assert_session_replication_role_denied",
            "_seed_projection_artifact",
            "return None",
        ),
        (
            "_assert_deferred_completeness_rejected",
            "_run_calls",
            'return {"partial_trio": "SET_CONSTRAINTS", '
            '"schema_mismatch": "COMMIT"}',
        ),
    ),
)
def test_v158_mandatory_negative_early_returns_are_rejected(
    function_name: str, next_name: str, statement: str
) -> None:
    source = FUNCTIONAL_PROBE.read_text(encoding="utf-8")
    weakened = _prepend_function_statement(
        source, function_name, next_name, statement
    )
    with pytest.raises(AssertionError):
        _assert_functional_negative_contract(weakened)


def test_v158_replay_preserves_server_timestamps_and_reads_complete_state() -> None:
    code = _code()
    assert "created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP" in code
    assert "p_created_at" not in code
    assert "ORDER BY CASE quantile" in code
    assert "q10" in code and "q50" in code and "q90" in code
    assert "typed_not_found" in code.lower() or "NOT_FOUND" in code
    assert "partial or divergent" in code.lower() or "PARTIAL_OR_DIVERGENT" in code


def test_v158_static_source_names_disposable_pg_probes() -> None:
    migration_sha = hashlib.sha256(V158.read_bytes()).hexdigest()
    probes = (
        (FUNCTIONAL_PROBE, "_apply_migration"),
        (CONCURRENCY_PROBE, "_apply_migration_twice"),
    )
    for path, apply_function in probes:
        assert path.exists(), f"isolated PG probe missing: {path}"
        text = path.read_text(encoding="utf-8")
        assert "V158" in text
        assert "ON_ERROR_STOP" in text
        assert "alr_challenger_writer" in text
        assert "alr_challenger_trainer_caller" in text
        assert '"learning_target"' in text
        assert '"candidate_artifact"' not in text
        assert "production" not in text.lower()
        assert "exchange" not in text.lower()
        assert migration_sha in text
        assert "expected_target" in text
        assert "passfile" in text and "password" in text
        _assert_probe_safety_contracts(text, apply_function)


@pytest.mark.parametrize(
    "path,apply_function",
    (
        (FUNCTIONAL_PROBE, "_apply_migration"),
        (CONCURRENCY_PROBE, "_apply_migration_twice"),
    ),
)
def test_v158_probe_safety_mutations_are_rejected(
    path: Path, apply_function: str
) -> None:
    source = path.read_text(encoding="utf-8")
    mutations = (
        (
            "if _target_identity(connection) != dict(expected_target):",
            "if False:",
        ),
        ("if bool(password) == bool(passfile_value):", "if False:"),
        ("if resolved_passfile == default_passfile:", "if False:"),
        (
            "if passfile_metadata.st_uid != os.geteuid():",
            "if False:",
        ),
        (
            "if stat.S_IMODE(passfile_metadata.st_mode) != 0o600:",
            "if False:",
        ),
    )
    for needle, replacement in mutations:
        assert needle in source
        weakened = source.replace(needle, replacement, 1)
        with pytest.raises(AssertionError):
            _assert_probe_safety_contracts(weakened, apply_function)

    no_op_guards = (
        (
            apply_function,
            "_target_identity",
            "_target_identity(connection) != dict(expected_target)",
        ),
        (
            "_parse_complete_dsn",
            "_migration_bytes",
            "bool(password) == bool(passfile_value)",
        ),
        (
            "_parse_complete_dsn",
            "_migration_bytes",
            "stat.S_IMODE(passfile_metadata.st_mode) != 0o600",
        ),
    )
    for function_name, next_name, condition in no_op_guards:
        weakened = _replace_guard_body_with_pass(
            source, function_name, next_name, condition
        )
        with pytest.raises(AssertionError):
            _assert_probe_safety_contracts(weakened, apply_function)

    early_returns = (
        (
            apply_function,
            "_target_identity",
            "_target_identity(connection) != dict(expected_target)",
            "return None",
        ),
        (
            "_parse_complete_dsn",
            "_migration_bytes",
            "bool(password) == bool(passfile_value)",
            "return dict(parsed)",
        ),
    )
    for function_name, next_name, condition, statement in early_returns:
        weakened = _prepend_guard_statement(
            source, function_name, next_name, condition, statement
        )
        with pytest.raises(AssertionError):
            _assert_probe_safety_contracts(weakened, apply_function)

    broad_handlers = (
        source.replace(
            "except psycopg2.ProgrammingError as exc:",
            "except Exception as exc:",
            1,
        ),
        source.replace(
            "except psycopg2.Error as exc:",
            "except ProbeFailure as exc:",
            1,
        ),
    )
    for weakened in broad_handlers:
        assert weakened != source
        compile(weakened, "<mutated-probe>", "exec")
        with pytest.raises(AssertionError):
            _assert_probe_safety_contracts(weakened, apply_function)


def test_v158_guards_bind_exact_catalog_and_payload_properties() -> None:
    sql = _sql()
    _assert_fail_closed_catalog_guards(sql)
    assert sql.count("CREATE TEMP TABLE alr_v158_expected_") == 4
    assert "unexpected trigger set" in sql
    assert "exact column schema mismatch" in sql
    assert "unexpected table/column ACL" in sql


@pytest.mark.parametrize(
    "needle,replacement",
    (
        (
            "v_actual.actual_expr IS DISTINCT FROM v_actual.expected_expr",
            "TRUE",
        ),
        (
            "t.tgrelid=v_spec.relation_name::regclass",
            "TRUE",
        ),
        ("md5(p.prosrc)<>v_spec.body_md5", "TRUE"),
        (
            "a.grantee NOT IN (v_schema_owner, v_writer_oid)",
            "FALSE",
        ),
        ("t.tgattr::TEXT=''", "TRUE"),
        ("c.relpersistence='p'", "TRUE"),
        ("generic.rolname IN ('trading_ai', 'alr_shadow')", "FALSE"),
        (
            "p_canonical_payload->>'projection_artifact_kind' IS DISTINCT FROM",
            "p_canonical_payload->>'projection_artifact_kind' <>",
        ),
        (
            "receipt_status = 'QUALIFIED_INPUT_PERSISTED'",
            "receipt_status <> ''",
        ),
        ("training_rows')::BIGINT > 2147483647", "training_rows')::BIGINT > 9223372036854775807"),
    ),
)
def test_v158_adversarial_guard_mutations_are_rejected(
    needle: str, replacement: str
) -> None:
    sql = _sql()
    assert needle in sql
    weakened = sql.replace(needle, replacement, 1)
    with pytest.raises(AssertionError):
        _assert_fail_closed_catalog_guards(weakened)


def test_v158_self_consistent_weakened_function_hash_is_rejected() -> None:
    sql = _sql()
    body = _dollar_body(sql, "v158_receipt_writer")
    weakened_body = body.replace(
        "session_user <> 'alr_challenger_trainer_caller'",
        "session_user = 'alr_challenger_trainer_caller'",
        1,
    )
    assert weakened_body != body
    old_hash = hashlib.md5(body.encode("utf-8")).hexdigest()  # noqa: S324
    new_hash = hashlib.md5(weakened_body.encode("utf-8")).hexdigest()  # noqa: S324
    weakened = sql.replace(body, weakened_body, 1).replace(old_hash, new_hash)
    with pytest.raises(AssertionError):
        _assert_fail_closed_catalog_guards(weakened)


def _assert_harness_contracts(rust: str, ci: str) -> None:
    maybe_pool = _rust_code(
        rust[rust.index("async fn maybe_pool") : rust.index("async fn seed_legacy")]
    )
    assert "Err(std::env::VarError::NotPresent) => return None" in maybe_pool
    assert ".connect(&url)" in maybe_pool
    assert "OPENCLAW_TEST_PG set but connect failed" in maybe_pool
    assert ".ok()?" not in maybe_pool
    connect_failure = re.search(
        r"[.]connect\(&url\)\s*[.]await\s*[.]unwrap_or_else\(\|e\|\s*\{\s*"
        r'panic!\("\[schema_contract_test\] OPENCLAW_TEST_PG set but connect '
        r'failed: \{e\}"\)\s*\}\)',
        maybe_pool,
        re.DOTALL,
    )
    assert connect_failure is not None
    seed = _rust_code(
        rust[
            rust.index("async fn seed_v158_role_preconditions") : rust.index(
                "async fn migrated_pool"
            )
        ]
    )
    assert ".execute(&mut *tx)" in seed and ".execute(pool)" not in seed
    assert seed.count("has_parameter_privilege") == 4
    assert "pg_parameter_acl" in seed
    posture_assertion = re.search(
        r"assert!\(\s*posture_is_exact\s*,\s*"
        r'"V158 role fixture found attribute, membership, or parameter-privilege drift"'
        r"\s*\);",
        seed,
        re.DOTALL,
    )
    assert posture_assertion is not None
    assert seed.index("let posture_is_exact") < posture_assertion.start()
    assert posture_assertion.end() < seed.index("tx.commit()")
    migrated_pool = _rust_code(rust[rust.index("async fn migrated_pool") :])
    invocation = "seed_v158_role_preconditions(&pool).await;"
    assert invocation in migrated_pool
    assert migrated_pool.index(invocation) < migrated_pool.index(
        "MigrationRunner::run_if_enabled"
    )
    ci_code = _ci_code(ci)
    assert re.search(
        r'^\s*OPENCLAW_TEST_PG_DESTRUCTIVE:\s*["\']1["\']\s*$',
        ci_code,
        re.MULTILINE,
    )
    assert "tests/migrations/test_v158_alr_qualified_challenger_training.py" in ci_code


def test_full_tree_schema_contract_seeds_exact_v158_role_preconditions() -> None:
    rust = SCHEMA_CONTRACT.read_text(encoding="utf-8")
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    _assert_harness_contracts(rust, ci)
    assert "CREATE ROLE alr_challenger_writer NOLOGIN" in rust
    assert "CREATE ROLE alr_challenger_trainer_caller LOGIN" in rust
    assert "CREATE ROLE trading_ai NOLOGIN" in rust
    assert "CREATE ROLE alr_shadow NOLOGIN" in rust
    assert "CONNECTION LIMIT 1" in rust
    assert "PASSWORD" not in rust
    assert 'OPENCLAW_TEST_PG_DESTRUCTIVE' in rust
    assert "server_version_num" in rust
    assert "session_identity" in rust and "database_owner" in rust


def test_harness_adversarial_mutations_are_rejected() -> None:
    rust = SCHEMA_CONTRACT.read_text(encoding="utf-8")
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    hard_connect = '''    Some(
        sqlx::postgres::PgPoolOptions::new()
            .max_connections(2)
            .acquire_timeout(std::time::Duration::from_secs(5))
            .connect(&url)
            .await
            .unwrap_or_else(|e| {
                panic!("[schema_contract_test] OPENCLAW_TEST_PG set but connect failed: {e}")
            }),
    )'''
    soft_connect = '''    match sqlx::postgres::PgPoolOptions::new()
        .max_connections(2)
        .acquire_timeout(std::time::Duration::from_secs(5))
        .connect(&url)
        .await
    {
        Ok(pool) => Some(pool),
        Err(e) => {
            eprintln!("[schema_contract_test] OPENCLAW_TEST_PG set but connect failed: {e}");
            None
        }
    }'''
    posture_assertion = '''    assert!(
        posture_is_exact,
        "V158 role fixture found attribute, membership, or parameter-privilege drift"
    );
'''
    posture_commit = '''    tx.commit()
        .await
        .expect("commit exact V158 role prerequisites in disposable cluster");
'''
    assert hard_connect in rust
    assert posture_assertion + posture_commit in rust
    cases = (
        (rust.replace(".execute(&mut *tx)", ".execute(pool)", 1), ci),
        (
            rust.replace(
                "seed_v158_role_preconditions(&pool).await;",
                "// seed_v158_role_preconditions(&pool).await;",
                1,
            ),
            ci,
        ),
        (rust.replace("has_parameter_privilege", "removed_parameter_check", 1), ci),
        (rust.replace("OPENCLAW_TEST_PG set but connect failed", "connect ignored", 1), ci),
        (rust, ci.replace('OPENCLAW_TEST_PG_DESTRUCTIVE: "1"', '# removed ack', 1)),
        (
            rust,
            ci.replace(
                "tests/migrations/test_v158_alr_qualified_challenger_training.py",
                "# removed V158 static gate",
                1,
            ),
        ),
        (rust.replace(hard_connect, soft_connect, 1), ci),
        (
            rust.replace(
                posture_assertion + posture_commit,
                posture_commit + posture_assertion,
                1,
            ),
            ci,
        ),
    )
    for weakened_rust, weakened_ci in cases:
        with pytest.raises(AssertionError):
            _assert_harness_contracts(weakened_rust, weakened_ci)
