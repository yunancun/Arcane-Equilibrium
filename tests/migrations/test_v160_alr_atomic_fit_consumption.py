"""Static contract for V160 atomic challenger-fit consumption.

These checks inspect repository bytes only.  They never connect to PostgreSQL,
contact an issuer/runner, execute a fit, or create production model state.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest


SRV_ROOT = Path(__file__).resolve().parents[2]
V160 = SRV_ROOT / "sql/migrations/V160__alr_atomic_fit_consumption.sql"
FUNCTIONAL_PROBE = (
    SRV_ROOT
    / "program_code/ml_training/tests/integration/"
    "alr_atomic_fit_consumption_isolated_pg.py"
)
CONCURRENCY_PROBE = (
    SRV_ROOT
    / "program_code/ml_training/tests/integration/"
    "alr_atomic_fit_consumption_concurrency_isolated_pg.py"
)
SCHEMA_CONTRACT = SRV_ROOT / "rust/openclaw_engine/tests/schema_contract_test.rs"
CI_WORKFLOW = SRV_ROOT / ".github/workflows/ci.yml"

_ACTIONS = (
    "REGISTER_REQUEST",
    "CLAIM_REQUEST",
    "RECORD_STATUS",
    "CONSUME_TERMINAL",
    "EXPIRE_UNCLAIMED",
    "MARK_RECONCILE_REQUIRED",
)
_RELATIONS = (
    "alr_challenger_consumption_requests",
    "alr_challenger_consumption_claims",
    "alr_challenger_consumption_statuses",
    "alr_challenger_consumption_verifier_evidence",
    "alr_challenger_consumption_terminals",
    "alr_challenger_consumption_reconciliation_audit",
)
_PHASES = (
    "REQUEST_ONLY",
    "SIGNED_STATUS",
    "TERMINAL_SUCCESS",
    "TERMINAL_NO_INNER",
)
_PAYLOAD_KEYS = {
    "REGISTER_REQUEST": (
        "request_bytes_hex",
        "request_projection",
        "verification_receipt_bytes_hex",
        "verification_receipt",
    ),
    "CLAIM_REQUEST": (
        "request_hash",
        "claim_bytes_hex",
        "claim_projection",
        "verification_receipt_bytes_hex",
        "verification_receipt",
    ),
    "RECORD_STATUS": (
        "request_hash",
        "response_bytes_hex",
        "response_projection",
        "verification_receipt_bytes_hex",
        "verification_receipt",
    ),
    "CONSUME_TERMINAL": (
        "request_hash",
        "response_bytes_hex",
        "response_projection",
        "inner_receipt_bytes_hex",
        "verification_receipt_bytes_hex",
        "verification_receipt",
    ),
    "EXPIRE_UNCLAIMED": ("request_hash", "reason"),
    "MARK_RECONCILE_REQUIRED": (
        "request_hash",
        "event_bytes_hex",
        "event_projection",
        "verification_receipt_bytes_hex",
        "verification_receipt",
    ),
}
_VERIFIER_KEYS = (
    "schema_version",
    "evidence_tier",
    "declared_phase",
    "capability_authenticity",
    "coordinator_eligible",
    "semantic_phase_established",
    "canonical_input_bytes_established",
    "envelope_payload_binding_established",
    "policy_overlay_adjudication_established",
    "trusted_time_established",
    "signatures_valid",
    "request_envelope_sha256",
    "signed_status_envelope_sha256",
    "outer_terminal_envelope_sha256",
    "v159_inner_envelope_sha256",
    "provider_evidence_digest_sha256",
    "host_attestation_digest_sha256",
)
_NEGATIVE_MUTATIONS = ("missing", "extra", "wrong", "null", "foreign")
_CLOSED_V159_FUNCTIONS = (
    "persist_alr_challenger_fit_attestation_v1",
    "persist_alr_challenger_training_result_v2",
    "read_alr_challenger_training_result_v2",
)


def _sql() -> str:
    assert V160.is_file(), f"V160 migration is missing: {V160}"
    return V160.read_text(encoding="utf-8")


def _section(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


def _python(path: Path) -> str:
    assert path.is_file(), f"required V160 probe is missing: {path}"
    source = path.read_text(encoding="utf-8")
    ast.parse(source)
    return source


def _function(source: str, name: str) -> ast.FunctionDef:
    definitions = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(definitions) == 1, name
    return definitions[0]


def _assert_v160_repair_contract(sql: str, functional: str, rust: str) -> None:
    coordinator = _section(
        sql,
        "CREATE OR REPLACE FUNCTION learning.coordinate_alr_challenger_consumption_v1(",
        "$v160_coordinator$;",
    )
    assert "p_action NOT IN (" in coordinator
    for action in _ACTIONS:
        assert f"V160 {action} payload fields rejected" in coordinator
        for key in _PAYLOAD_KEYS[action]:
            assert f"'{key}'" in coordinator

    for function_name in (
        "_assert_v157_disposable_baseline",
        "_assert_closed_action_schemas",
        "_assert_v159_application_closure",
        "_assert_coordinator_execute_deletion",
        "_assert_verifier_fail_closed",
        "_assert_terminal_verifiers_fail_closed",
        "_assert_exact_success_readback",
        "_assert_exact_reconciliation_readback",
        "_assert_non_success_terminal_verifier",
        "_assert_failed_reconciliation_readback",
        "_assert_non_success_readback",
    ):
        assert functional.count(f"def {function_name}(") == 1
        assert functional.count(f"{function_name}(") >= 2
    for function_name in _CLOSED_V159_FUNCTIONS:
        assert f'"{function_name}"' in functional
    for mutation in _NEGATIVE_MUTATIONS:
        assert f'"{mutation}"' in functional
    for marker in (
        "DATABASE_RESIDENT_V157_SENTINEL",
        "CLOSED_ACTION_SCHEMA_MATRIX_6X5",
        "V159_WRAPPERS_ROLE_MATRIX_CLOSED",
        "COORDINATOR_EXECUTE_DELETION_FAIL_CLOSED",
        "INVALID_VERIFIER_FAIL_CLOSED",
        "FAILED_VERIFIER_FAIL_CLOSED",
        "TERMINAL_VERIFIER_PHASES_FAIL_CLOSED",
        "FIXED_READER_EXACT_LIFECYCLE_AND_V159",
        "NON_SUCCESS_TERMINAL_VERIFIER_EXACT",
        "FAILED_RECONCILIATION_EXACT",
        "NON_SUCCESS_FIXED_READER_NO_V159",
    ):
        assert marker in functional

    for token in (
        "CREATE TABLE public.alr_v160_disposable_probe_sentinel",
        "V160_V157_BASELINE_DISPOSABLE_CONFIRMED:",
        "migration_count",
        "post_v157_count",
        "baseline_session_user",
        "baseline_current_user",
        "V160 disposable baseline sentinel",
    ):
        assert token in rust


def test_v160_is_the_single_fresh_migration_reservation() -> None:
    migrations = list((SRV_ROOT / "sql/migrations").glob("V*.sql"))
    versions = [int(path.name[1:4]) for path in migrations]
    assert versions.count(160) == 1
    assert max(versions) == 160
    assert V160.name == "V160__alr_atomic_fit_consumption.sql"
    assert _sql().startswith("-- V160: atomic durable ALR fit consumption.\n")
    observed = hashlib.sha256(V160.read_bytes()).hexdigest()
    assert f'"V160": "{observed}"' in FUNCTIONAL_PROBE.read_text(encoding="utf-8")


def test_v160_installs_exact_six_relation_append_only_inventory() -> None:
    sql = _sql()
    for relation in _RELATIONS:
        assert sql.count(f"CREATE TABLE IF NOT EXISTS learning.{relation} (") == 1
        assert f"ALTER TABLE learning.{relation} OWNER TO alr_challenger_consumption_coordinator" not in sql
    trigger_block = _section(
        sql,
        "DO $v160_append_only_triggers$",
        "$v160_append_only_triggers$;",
    )
    assert trigger_block.count("FOR EACH ROW EXECUTE FUNCTION") == 1
    for suffix in (
        "requests",
        "claims",
        "statuses",
        "verifier_evidence",
        "terminals",
        "reconciliation",
    ):
        assert f"alr_v160_immutable_{suffix}_trg" in trigger_block
    assert "BEFORE UPDATE OR DELETE" in trigger_block
    assert "V160 append-only relation rejects %" in sql


def test_v160_coordinator_and_reader_are_the_only_new_application_interface() -> None:
    sql = _sql()
    assert sql.count(
        "CREATE OR REPLACE FUNCTION learning.coordinate_alr_challenger_consumption_v1("
    ) == 1
    assert sql.count(
        "CREATE OR REPLACE FUNCTION learning.read_alr_challenger_consumption_v1("
    ) == 1
    coordinator = _section(
        sql,
        "CREATE OR REPLACE FUNCTION learning.coordinate_alr_challenger_consumption_v1(",
        "$v160_coordinator$;",
    )
    reader = _section(
        sql,
        "CREATE OR REPLACE FUNCTION learning.read_alr_challenger_consumption_v1(",
        "$v160_reader$;",
    )
    assert "p_action TEXT,p_payload JSONB" in coordinator
    assert "p_request_hash TEXT" in reader
    assert "SECURITY DEFINER" in coordinator and "SECURITY DEFINER" in reader
    assert "SET search_path=pg_catalog,pg_temp" in coordinator
    assert "SET search_path=pg_catalog,pg_temp" in reader
    assert "session_user<>'alr_challenger_consumption_caller'" in coordinator
    assert "current_user<>'alr_challenger_consumption_coordinator'" in coordinator
    assert "session_user<>'alr_challenger_consumption_caller'" in reader


def test_v160_six_action_set_and_payload_schemas_are_closed() -> None:
    coordinator = _section(
        _sql(),
        "CREATE OR REPLACE FUNCTION learning.coordinate_alr_challenger_consumption_v1(",
        "$v160_coordinator$;",
    )
    for action in _ACTIONS:
        assert f"'{action}'" in coordinator
        assert f"p_action='{action}'" in coordinator or action in (
            "CLAIM_REQUEST",
            "CONSUME_TERMINAL",
            "MARK_RECONCILE_REQUIRED",
        )
        for key in _PAYLOAD_KEYS[action]:
            assert f"'{key}'" in coordinator
        assert f"V160 {action} payload fields rejected" in coordinator
    assert "p_action NOT IN (" in coordinator
    assert "p_payload-ARRAY[" in coordinator
    assert "V160 closed action or payload rejected" in coordinator


def test_v160_platform_attested_verifier_shape_and_phase_binding_are_closed() -> None:
    coordinator = _section(
        _sql(),
        "CREATE OR REPLACE FUNCTION learning.coordinate_alr_challenger_consumption_v1(",
        "$v160_coordinator$;",
    )
    for key in _VERIFIER_KEYS:
        assert coordinator.count(f"'{key}'") >= 2
    for phase in _PHASES:
        assert f"'{phase}'" in coordinator
    for token in (
        "alr_fit_verifier_host_attestation_v1",
        "PLATFORM_OR_EXTERNAL_ATTESTED",
        "v_verifier->'coordinator_eligible'<>'true'::JSONB",
        "v_verifier->'semantic_phase_established'<>'true'::JSONB",
        "v_verifier->'canonical_input_bytes_established'<>'true'::JSONB",
        "v_verifier->'envelope_payload_binding_established'<>'true'::JSONB",
        "v_verifier->'policy_overlay_adjudication_established'<>'true'::JSONB",
        "v_verifier->'trusted_time_established'<>'true'::JSONB",
        "v_verifier->'signatures_valid'<>'true'::JSONB",
        "V160 platform-attested verifier receipt rejected",
        "V160 signed-status verifier byte binding rejected",
        "V160 terminal verifier byte binding rejected",
    ):
        assert token in coordinator


def test_v160_replay_concurrency_and_generation_oracles_fail_closed() -> None:
    coordinator = _section(
        _sql(),
        "CREATE OR REPLACE FUNCTION learning.coordinate_alr_challenger_consumption_v1(",
        "$v160_coordinator$;",
    )
    for lock_domain in (
        "v160:admission:",
        "v160:generation:",
        "v160:issuer_nonce:",
        "v160:request:",
    ):
        assert lock_domain in coordinator
    assert "SELECT DISTINCT hashtextextended(lock_material,0) AS lock_key" in coordinator
    assert "ORDER BY lock_key" in coordinator
    assert "PERFORM pg_advisory_xact_lock(v_lock_key)" in coordinator
    assert coordinator.count("RAISE EXCEPTION 'DURABLE_CONSUMPTION_CONFLICT'") >= 8
    assert coordinator.count("'status','DUPLICATE'") >= 5
    assert "v_generation<=v_previous_generation" in coordinator
    assert "v_generation<=v_previous_status_generation" in coordinator


def test_v160_terminal_branches_preserve_success_only_v159_atomicity() -> None:
    coordinator = _section(
        _sql(),
        "CREATE OR REPLACE FUNCTION learning.coordinate_alr_challenger_consumption_v1(",
        "$v160_coordinator$;",
    )
    terminal = _section(
        coordinator,
        "-- The only remaining action is CONSUME_TERMINAL.",
        "EXCEPTION WHEN unique_violation THEN",
    )
    for outcome in (
        "SUCCEEDED",
        "REJECTED_PRE_FIT",
        "FAILED_AFTER_START",
        "EXPIRED_UNCLAIMED",
    ):
        assert f"'{outcome}'" in coordinator
    for relation in (
        "alr_challenger_fit_attestations",
        "alr_challenger_training_runs",
        "alr_challenger_model_artifacts",
        "alr_challenger_registry",
    ):
        assert terminal.count(f"INSERT INTO learning.{relation}") == 1
    assert terminal.index("IF v_outcome IN ('REJECTED_PRE_FIT','FAILED_AFTER_START') THEN") < terminal.index(
        "INSERT INTO learning.alr_challenger_fit_attestations"
    )
    assert "-- SUCCEEDED: decoded inner bytes" in terminal
    assert "v_outcome IN ('REJECTED_PRE_FIT','FAILED_AFTER_START')" in terminal
    assert "IF v_outcome='FAILED_AFTER_START' THEN" in terminal
    assert "FAILED_AFTER_START" in terminal and "reconciliation_audit" in terminal


def test_v160_hard_closes_v159_application_wrappers_but_not_v158_receipts() -> None:
    sql = _sql()
    for name, message in (
        (
            "persist_alr_challenger_fit_attestation_v1",
            "V160 closed V159 attestation wrapper: atomic coordinator required",
        ),
        (
            "persist_alr_challenger_training_result_v2",
            "V160 closed V159 result wrapper: atomic coordinator required",
        ),
        (
            "read_alr_challenger_training_result_v2",
            "V160 closed V159 result reader: fixed consumption read required",
        ),
    ):
        body = _section(sql, f"CREATE OR REPLACE FUNCTION learning.{name}(", ";\n\n")
        assert message in body
        assert "RAISE EXCEPTION" in body
    assert "CREATE OR REPLACE FUNCTION learning.persist_alr_qualified_training_receipt_v1" not in sql
    assert "CREATE OR REPLACE FUNCTION learning.read_alr_qualified_training_receipt_v1" not in sql


def test_v160_acl_is_membership_free_and_delete_safe() -> None:
    sql = _sql()
    for role in (
        "alr_challenger_consumption_coordinator",
        "alr_challenger_consumption_caller",
    ):
        assert role in sql
    assert "FROM PUBLIC,alr_challenger_consumption_caller" in sql
    assert "FOREACH v_role IN ARRAY ARRAY['trading_ai','alr_shadow']" in sql
    assert "FROM %I',v_role" in sql
    assert "learning.coordinate_alr_challenger_consumption_v1(TEXT,JSONB)" in sql
    assert "learning.read_alr_challenger_consumption_v1(TEXT)" in sql
    assert "TO alr_challenger_consumption_caller;" in sql
    assert "GRANT USAGE ON SCHEMA learning TO" in sql
    assert "GRANT CREATE ON SCHEMA learning TO alr_challenger_consumption_caller" not in sql
    assert "pg_auth_members" in sql
    assert "has_parameter_privilege" in sql


@pytest.mark.parametrize("probe", (FUNCTIONAL_PROBE, CONCURRENCY_PROBE))
def test_v160_disposable_probes_are_inert_and_explicitly_gated(probe: Path) -> None:
    source = _python(probe)
    main = _function(source, "main")
    assert source.count("if __name__ == \"__main__\":") == 1
    assert "_safe_entrypoint" in source
    assert not any(isinstance(node, ast.Call) for node in ast.parse(source).body)
    assert any(isinstance(node, ast.Return) for node in ast.walk(main))
    for token in (
        "ALR_V160_DISPOSABLE_ADMIN_DSN",
        "expected-database",
        "disposable-sentinel",
        "_parse_complete_dsn",
        "_reject_ambient_libpq_routing",
        "_target_identity",
        "V158",
        "V159",
        "V160",
    ):
        assert token in source


def test_v160_functional_probe_covers_fixed_interface_and_closed_boundaries() -> None:
    source = _python(FUNCTIONAL_PROBE)
    for action in _ACTIONS:
        assert action in source
    for marker in (
        "MIGRATION_REPLAY_STABLE",
        "REGISTER_EXACT_REPLAY",
        "CLAIM_BEFORE_FIT",
        "STATUS_MONOTONIC",
        "SUCCESS_BUNDLE_ATOMIC_1_1_3_1",
        "REJECTED_PRE_FIT_NO_V159",
        "FAILED_AFTER_START_RECONCILE_NO_V159",
        "EXPIRED_UNCLAIMED_NO_V159",
        "DIRECT_DML_AND_V159_WRAPPERS_CLOSED",
        "FIXED_READER_BYTE_READBACK",
        "NO_AUTHORITY_FALSE_ZERO",
        "DATABASE_RESIDENT_V157_SENTINEL",
        "CLOSED_ACTION_SCHEMA_MATRIX_6X5",
        "V159_WRAPPERS_ROLE_MATRIX_CLOSED",
        "COORDINATOR_EXECUTE_DELETION_FAIL_CLOSED",
        "INVALID_VERIFIER_FAIL_CLOSED",
        "FAILED_VERIFIER_FAIL_CLOSED",
        "FIXED_READER_EXACT_LIFECYCLE_AND_V159",
        "NON_SUCCESS_FIXED_READER_NO_V159",
        "SCENARIO_SUITE_COMPLETE",
    ):
        assert marker in source
    assert "model_training_performed=true" not in source.lower()


def test_v160_concurrency_probe_covers_conflict_and_rollback_oracles() -> None:
    source = _python(CONCURRENCY_PROBE)
    for token in (
        "ThreadPoolExecutor",
        "Barrier",
        "statement_timeout",
        "lock_timeout",
        "IDENTICAL_REGISTER_PERSISTED_DUPLICATE",
        "DIVERGENT_REGISTER_ONE_CONFLICT",
        "IDENTICAL_CLAIM_PERSISTED_DUPLICATE",
        "DIVERGENT_TERMINAL_ONE_CONFLICT",
        "CLAIM_VS_EXPIRE_RACE",
        "OUT_OF_ORDER_STATUS_SERIALIZED",
        "IDENTICAL_SUCCESS_TERMINAL_PERSISTED_DUPLICATE",
        "SUCCESS_VS_NONSUCCESS_ONE_CONFLICT",
        "DIVERGENT_ARTIFACT_ONE_CONFLICT",
        "EXACT_DOMAIN_LOCK_SET_OBSERVED",
        "ROLLBACK_NO_PARTIAL",
        "WORKER_CONNECTION_OWNERSHIP_UNIQUE",
        "GLOBAL_ORACLE",
        "SCENARIO_SUITE_COMPLETE",
    ):
        assert token in source


def test_v160_schema_fixture_and_hosted_ci_start_from_independent_v157_databases() -> None:
    rust = SCHEMA_CONTRACT.read_text(encoding="utf-8")
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    for token in (
        'const V160_BASELINE_ACK_ENV_VAR: &str = "OPENCLAW_V160_PROBE_BASELINE";',
        "async fn prepare_v160_probe_v157_baseline()",
        "migration.version == 158",
        "migration.version == 159",
        "migration.version == 160",
        "migration.version <= V160_BASELINE_VERSION",
        "alr_challenger_consumption_coordinator",
        "alr_challenger_consumption_caller",
        "V160 baseline is not empty of V158/V159/V160 durable relations",
        "public.alr_v160_disposable_probe_sentinel",
        "V160_V157_BASELINE_DISPOSABLE_CONFIRMED:",
        "migration_count",
        "post_v157_count",
    ):
        assert token in rust
    for token in (
        "alr_v160_functional_ci",
        "alr_v160_concurrency_ci",
        'OPENCLAW_V160_PROBE_BASELINE: "1"',
        "prepare_v160_probe_v157_baseline -- --exact --test-threads=1",
        "alr_atomic_fit_consumption_isolated_pg.py",
        "alr_atomic_fit_consumption_concurrency_isolated_pg.py",
        "dropdb --force --if-exists",
    ):
        assert token in workflow
    assert workflow.index("alr_v160_functional_ci") < workflow.index(
        "alr_atomic_fit_consumption_isolated_pg.py"
    )
    assert workflow.index("alr_v160_concurrency_ci") < workflow.index(
        "alr_atomic_fit_consumption_concurrency_isolated_pg.py"
    )


def test_v160_repair_contract_is_executable_and_complete() -> None:
    sql = _sql()
    functional = _python(FUNCTIONAL_PROBE)
    rust = SCHEMA_CONTRACT.read_text(encoding="utf-8")
    _assert_v160_repair_contract(sql, functional, rust)


def test_v160_repair_contract_mutations_are_rejected() -> None:
    sql = _sql()
    functional = _python(FUNCTIONAL_PROBE)
    rust = SCHEMA_CONTRACT.read_text(encoding="utf-8")
    mutations = (
        (
            sql.replace("p_action NOT IN (", "p_action IN (", 1),
            functional,
            rust,
        ),
        (
            sql,
            functional.replace(
                "def _assert_closed_action_schemas(",
                "def removed_closed_action_schemas(",
                1,
            ),
            rust,
        ),
        (
            sql,
            functional.replace(
                "def _assert_v159_application_closure(",
                "def removed_v159_application_closure(",
                1,
            ),
            rust,
        ),
        (
            sql,
            functional.replace(
                "def _assert_exact_success_readback(",
                "def removed_exact_success_readback(",
                1,
            ),
            rust,
        ),
        (
            sql,
            functional.replace(
                "def _assert_terminal_verifiers_fail_closed(",
                "def removed_terminal_verifiers_fail_closed(",
                1,
            ),
            rust,
        ),
        (
            sql,
            functional.replace(
                "def _assert_non_success_terminal_verifier(",
                "def removed_non_success_terminal_verifier(",
                1,
            ),
            rust,
        ),
        (
            sql,
            functional.replace(
                "def _assert_failed_reconciliation_readback(",
                "def removed_failed_reconciliation_readback(",
                1,
            ),
            rust,
        ),
        (
            sql,
            functional,
            rust.replace(
                "CREATE TABLE public.alr_v160_disposable_probe_sentinel",
                "CREATE TABLE public.removed_v160_disposable_probe_sentinel",
                1,
            ),
        ),
    )
    for weakened_sql, weakened_functional, weakened_rust in mutations:
        with pytest.raises(AssertionError):
            _assert_v160_repair_contract(
                weakened_sql, weakened_functional, weakened_rust
            )
