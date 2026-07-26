"""S2.4 §2.1/§10.5 #23(W2a)engine-scanner privilege-split 靜態執法測試。

覆蓋:
* 真 repo 樹上 derive_engine_scanner_privilege_split 導出 PASS(retention 面 import
  不可達、SQL inventory 零 DELETE/零 retention mutation、與 pg_acl_manifest_v1.json
  雙向 exact-match);
* 合成違規樹(consumer 重新匯入 retention / 消費面夾帶 DELETE)→ typed
  ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED;
* manifest 竄改(over-grant / unlisted / self-digest 偽造)→ typed refusal;
* inventory deterministic(同一樹重建 → canonical digest 相等);
* generate_engine_scanner_grant_sql 的封閉性(無 GRANT OPTION / ALL / CREATE /
  membership;語句嚴格由 manifest 導出)。

真 PG 佐證(丟棄式 cluster、42501 denial)屬 sibling
``test_agent_governance_s2_4_install_engine_scanner_disposable.py``。
"""

from __future__ import annotations

import copy
import json
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_install as install  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

MANIFEST_PATH = ROOT / "program_code/ml_training/pg_acl_manifest_v1.json"


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _write_synthetic_tree(root: Path, *, consumer_source: str, extra: dict[str, str] | None = None) -> Path:
    package = root / "program_code/ml_training"
    package.mkdir(parents=True)
    (package / "alr_event_consumer.py").write_text(
        textwrap.dedent(consumer_source), encoding="utf-8"
    )
    for name, source in (extra or {}).items():
        (package / name).write_text(textwrap.dedent(source), encoding="utf-8")
    return root


# --------------------------------------------------------------------------- #
# 真 repo 樹:PASS 與其證據面
# --------------------------------------------------------------------------- #
def test_real_tree_privilege_split_derives_pass() -> None:
    verdict = install.derive_engine_scanner_privilege_split()
    assert verdict["status"] == "PASS"
    assert verdict["reasons"] == []
    assert verdict["retention_forbidden_reachable"] == []
    assert verdict["manifest_digest"] == _load_manifest()["self_digest"]
    assert verdict["statement_count"] >= 50
    assert verdict["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }


def test_real_tree_inventory_has_no_delete_and_no_retention_mutation() -> None:
    inventory = install.build_engine_scanner_sql_inventory()
    assert inventory["violations"] == []
    assert inventory["unresolved"] == []
    assert all(
        record["statement_class"] != "delete" and not record["mutation"]
        for record in inventory["statements"]
    )
    # retention 表在 post-split 消費面只允許唯讀(health 計數)。
    for table in install._RETENTION_TABLES:
        assert inventory["required_privileges"]["tables"].get(table, []) in ([], ["SELECT"])
    # retention 模組完全不在 import 閉包(含 lazy/條件;閉包同時走 helper 域)。
    assert not set(install._RETENTION_FORBIDDEN_MODULES) & set(inventory["import_closure"])


def test_real_tree_inventory_is_deterministic() -> None:
    first = install.build_engine_scanner_sql_inventory()
    second = install.build_engine_scanner_sql_inventory()
    assert validator.canonical_digest(first) == validator.canonical_digest(second)


# --------------------------------------------------------------------------- #
# W2 P1-C/P2-F:掃描面零排除,且覆蓋 bundle 內的 helper 域模組
# --------------------------------------------------------------------------- #
def test_sql_scan_has_zero_named_exclusions_and_covers_every_closure_member() -> None:
    inventory = install.build_engine_scanner_sql_inventory()
    verdict = install.derive_engine_scanner_privilege_split()
    # 具名排除面(舊 sql_scan_excluded)必須「整個消失」——不得留任何殘存鍵。
    assert "sql_scan_excluded" not in inventory
    assert "sql_scan_excluded" not in verdict
    assert not hasattr(install, "_ENGINE_SCANNER_SQL_SCAN_EXCLUDED")
    scanned = set(inventory["sql_scanned_modules"])
    # bundle runtime closure 的每一個成員(含 helper 域)都必須在掃描面內。
    bundle = install.build_engine_scanner_runtime_import_closure(
        ROOT, lazy_helper_roots=install._declared_lazy_helper_roots(ROOT)
    )
    assert set(bundle) <= scanned, sorted(set(bundle) - scanned)
    assert {"agent_governance_schema", "agent_governance_sealed_build"} <= scanned
    # ml_training 域的每一個 import-closure 成員同樣在掃描面內。
    ml_dir = (ROOT / "program_code/ml_training").resolve()
    ml_members = {
        name
        for name in inventory["import_closure"]
        if (ml_dir / f"{name}.py").is_file()
    }
    assert ml_members <= scanned, sorted(ml_members - scanned)
    assert verdict["sql_scan_surface"] == (
        "ml_training_modules_union_application_runtime_closure"
    )


def test_ambient_dsn_parquet_etl_is_no_longer_import_reachable() -> None:
    """P1-C:parquet_etl(真連 PG 的 duckdb ETL 面)必須離開 import 閉包。"""
    inventory = install.build_engine_scanner_sql_inventory()
    assert "parquet_etl" not in inventory["import_closure"]
    assert "parquet_etl" not in inventory["sql_scanned_modules"]
    bundle = install.build_engine_scanner_runtime_import_closure(
        ROOT, lazy_helper_roots=install._declared_lazy_helper_roots(ROOT)
    )
    assert "parquet_etl" not in bundle


def test_reintroduced_parquet_etl_import_is_refused(tmp_path: Path) -> None:
    """回歸:任何人把 ambient-DSN 面 import 回 runtime 閉包即掃描面違規。"""
    root = _write_synthetic_tree(
        tmp_path,
        consumer_source="""
        _LOCAL_DSN_REQUIRED = {
            "host": "127.0.0.1",
            "port": "5432",
            "dbname": "trading_ai",
            "user": "aiml_engine_scanner",
        }
        from ml_training.parquet_etl import EDGE_P3_FEATURE_NAMES
        """,
        extra={
            "parquet_etl.py": """
            import os


            def extract(pg_url=None):
                db_url = pg_url or os.getenv("OPENCLAW_DATABASE_URL", "")
                conn = duckdb.connect()
                conn.execute(f"ATTACH '{db_url}' AS pg (TYPE postgres, READ_ONLY);")
            """,
        },
    )
    inventory = install.build_engine_scanner_sql_inventory(root)
    assert "parquet_etl" in inventory["sql_scanned_modules"]
    verdict = install.derive_engine_scanner_privilege_split(
        root, manifest_path=MANIFEST_PATH
    )
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"


# --------------------------------------------------------------------------- #
# W2 P1-B(E3 P1-1):data-modifying CTE 不得被首 token 分類放行
# --------------------------------------------------------------------------- #
# 審查報告給出的原始攻擊字串(head 是 WITH → 舊分類器判 read → 只導出 SELECT)。
_CTE_ATTACK_SQL = (
    "WITH purged AS ("
    "DELETE FROM learning.alr_derived_cache_entries WHERE cache_key = %s "
    "RETURNING cache_key"
    ") SELECT count(*) AS purged_count FROM purged"
)


def test_data_modifying_cte_is_classified_as_mutation_not_read() -> None:
    classified = install._classify_sql_statement(_CTE_ATTACK_SQL)
    assert classified["statement_class"] == "data_modifying_cte"
    assert classified["mutation"] is True
    # 真目標的真權限被導出(不是只有 SELECT)
    assert "DELETE" in classified["tables"]["learning.alr_derived_cache_entries"]
    assert any("data_modifying_cte:DELETE" in error for error in classified["errors"])
    # 對照:同一形狀的純讀 CTE 仍是 read 類(無誤報)
    benign = install._classify_sql_statement(
        "WITH recent AS (SELECT source_key FROM learning.alr_source_events) "
        "SELECT count(*) AS n FROM recent"
    )
    assert benign["statement_class"] == "read"
    assert benign["mutation"] is False
    assert benign["errors"] == []


def test_data_modifying_cte_fails_the_split_predicate(tmp_path: Path) -> None:
    root = _write_synthetic_tree(
        tmp_path,
        consumer_source=f'''
        _LOCAL_DSN_REQUIRED = {{
            "host": "127.0.0.1",
            "port": "5432",
            "dbname": "trading_ai",
            "user": "aiml_engine_scanner",
        }}
        _PURGE_SQL = (
            "{_CTE_ATTACK_SQL}"
        )


        def sweep(connection):
            with connection.cursor() as cursor:
                cursor.execute(_PURGE_SQL, ("k",))
        ''',
    )
    verdict = install.derive_engine_scanner_privilege_split(
        root, manifest_path=MANIFEST_PATH
    )
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    assert any("delete_statement_forbidden" in reason for reason in verdict["reasons"])
    assert any("retention_table_mutation" in reason for reason in verdict["reasons"])
    assert any(
        "data_modifying_cte_forbidden" in reason for reason in verdict["reasons"]
    )


@pytest.mark.parametrize(
    "sql,needle",
    [
        (
            "WITH bumped AS (UPDATE learning.alr_consumer_events SET error_code = NULL "
            "RETURNING session_id) SELECT count(*) AS n FROM bumped",
            "data_modifying_cte:UPDATE:learning.alr_consumer_events",
        ),
        (
            "WITH copied AS (INSERT INTO learning.alr_retention_events "
            "SELECT * FROM learning.alr_retention_events WHERE false RETURNING 1) "
            "SELECT count(*) AS n FROM copied",
            "data_modifying_cte:INSERT:learning.alr_retention_events",
        ),
        (
            "SELECT count(*) AS n FROM learning.alr_source_events; "
            "TRUNCATE TABLE learning.alr_source_events",
            "data_modifying_cte:TRUNCATE:learning.alr_source_events",
        ),
    ],
)
def test_every_embedded_data_modification_verb_is_derived(sql: str, needle: str) -> None:
    classified = install._classify_sql_statement(sql)
    assert classified["mutation"] is True
    assert needle in classified["errors"]


def test_insert_on_conflict_do_update_requires_update_privilege() -> None:
    classified = install._classify_sql_statement(
        "INSERT INTO learning.alr_source_events (source_key) VALUES (%s) "
        "ON CONFLICT (source_key) DO UPDATE SET source_key = EXCLUDED.source_key"
    )
    assert classified["mutation"] is True
    assert set(classified["tables"]["learning.alr_source_events"]) == {
        "INSERT",
        "SELECT",
        "UPDATE",
    }
    # E2 P2-F:修前 `DO UPDATE SET` 的 SET 被當成關聯名 → 恆有 unqualified_relation:SET
    # → 這條路徑「永遠不可能 PASS」,未來一條合法語句會被以誤導理由攔下。
    assert classified["errors"] == []
    assert classified["statement_class"] == "insert"


# --------------------------------------------------------------------------- #
# E2 P2-D(已證實的規避):verb 與 FROM 之間的註解不得繞過 CTE mutation 掃描
# --------------------------------------------------------------------------- #
# 審查報告給出的兩條原始 evasion 字串(PG 兩條都照收;舊掃描器 read + 零 error)。
_COMMENT_EVASION_BLOCK = (
    "WITH x AS (DELETE /*evade*/ FROM learning.alr_derived_cache_entries "
    "RETURNING entry_id) SELECT count(*) FROM x"
)
_COMMENT_EVASION_LINE = (
    "WITH x AS (DELETE --evade\n FROM learning.alr_derived_cache_entries "
    "RETURNING entry_id) SELECT count(*) FROM x"
)
# PG 的區塊註解可巢狀;單層剝除會在此處提前收尾,verb 與 FROM 又被拆開。
_COMMENT_EVASION_NESTED = (
    "WITH x AS (DELETE /* a /* b */ still-comment */ FROM "
    "learning.alr_derived_cache_entries RETURNING entry_id) SELECT count(*) FROM x"
)


@pytest.mark.parametrize(
    "sql",
    [_COMMENT_EVASION_BLOCK, _COMMENT_EVASION_LINE, _COMMENT_EVASION_NESTED],
    ids=["block_comment", "line_comment", "nested_block_comment"],
)
def test_comments_between_verb_and_from_do_not_bypass_the_mutation_scan(
    sql: str,
) -> None:
    classified = install._classify_sql_statement(sql)
    assert classified["statement_class"] == "data_modifying_cte"
    assert classified["mutation"] is True
    assert "DELETE" in classified["tables"]["learning.alr_derived_cache_entries"]
    assert any("data_modifying_cte:DELETE" in error for error in classified["errors"])
    assert ("DELETE", "learning.alr_derived_cache_entries") in (
        install._embedded_data_modifications(sql)
    )


@pytest.mark.parametrize(
    "sql",
    [_COMMENT_EVASION_BLOCK, _COMMENT_EVASION_LINE, _COMMENT_EVASION_NESTED],
    ids=["block_comment", "line_comment", "nested_block_comment"],
)
def test_comment_evasion_fails_the_split_predicate(tmp_path: Path, sql: str) -> None:
    root = _write_synthetic_tree(
        tmp_path,
        consumer_source='''
        _LOCAL_DSN_REQUIRED = {{
            "host": "127.0.0.1",
            "port": "5432",
            "dbname": "trading_ai",
            "user": "aiml_engine_scanner",
        }}
        _PURGE_SQL = {sql!r}


        def sweep(connection):
            with connection.cursor() as cursor:
                cursor.execute(_PURGE_SQL)
        '''.format(sql=sql),
    )
    verdict = install.derive_engine_scanner_privilege_split(
        root, manifest_path=MANIFEST_PATH
    )
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    assert any("delete_statement_forbidden" in reason for reason in verdict["reasons"])
    assert any("retention_table_mutation" in reason for reason in verdict["reasons"])
    assert any(
        "data_modifying_cte_forbidden" in reason for reason in verdict["reasons"]
    )


def test_comment_stripping_never_touches_string_or_dollar_quoted_literals() -> None:
    """反向防呆:剝註解不得動到字面量,否則會把資料當註解吃掉(製造假紅/假綠)。"""
    literal = (
        "SELECT source_key FROM learning.alr_source_events "
        "WHERE note = '-- not a comment' AND tag = '/* nor this */'"
    )
    classified = install._classify_sql_statement(literal)
    assert classified["statement_class"] == "read"
    assert classified["errors"] == []
    stripped = install._strip_sql_comments(literal)
    assert "-- not a comment" in stripped and "/* nor this */" in stripped
    dollar = (
        "SELECT source_key FROM learning.alr_source_events "
        "WHERE body = $tag$ -- keep /* keep */ $tag$"
    )
    assert "-- keep /* keep */" in install._strip_sql_comments(dollar)
    assert install._classify_sql_statement(dollar)["errors"] == []
    # 雙引號識別子內同理;且剝除是 idempotent(重複套用結果不變)。
    quoted = 'SELECT "we--ird" FROM learning.alr_source_events'
    assert install._strip_sql_comments(quoted) == quoted
    once = install._strip_sql_comments(_COMMENT_EVASION_BLOCK)
    assert install._strip_sql_comments(once) == once
    # 註解代換為空白而非刪除:相鄰 token 不得被黏成一個。
    assert "DELETE   FROM" in install._strip_sql_comments(
        "DELETE /*x*/ FROM learning.alr_source_events"
    )
    assert (
        install._strip_sql_comments("DELETE/*x*/FROM learning.alr_source_events")
        == "DELETE FROM learning.alr_source_events"
    )


# --------------------------------------------------------------------------- #
# E2 P2-E:MERGE(PG15+;PG17 起可入 CTE)必須在 data-modifying 動詞集內
# --------------------------------------------------------------------------- #
_MERGE_CTE_SQL = (
    "WITH m AS (MERGE INTO learning.alr_derived_cache_entries t "
    "USING learning.alr_source_events s ON t.cache_key = s.source_key "
    "WHEN MATCHED THEN DELETE RETURNING 1) SELECT count(*) FROM m"
)


def test_merge_inside_a_cte_is_a_data_modifying_verb() -> None:
    classified = install._classify_sql_statement(_MERGE_CTE_SQL)
    assert classified["statement_class"] == "data_modifying_cte"
    assert classified["mutation"] is True
    # MERGE 的 WHEN 分支可 INSERT/UPDATE/DELETE,靜態文字面無法排除 → fail-closed 導三者
    assert set(classified["tables"]["learning.alr_derived_cache_entries"]) >= {
        "DELETE",
        "INSERT",
        "UPDATE",
    }
    assert "data_modifying_cte:MERGE:learning.alr_derived_cache_entries" in (
        classified["errors"]
    )
    assert ("MERGE", "learning.alr_derived_cache_entries") in (
        install._embedded_data_modifications(_MERGE_CTE_SQL)
    )


def test_merge_in_a_cte_fails_the_split_predicate(tmp_path: Path) -> None:
    root = _write_synthetic_tree(
        tmp_path,
        consumer_source='''
        _LOCAL_DSN_REQUIRED = {{
            "host": "127.0.0.1",
            "port": "5432",
            "dbname": "trading_ai",
            "user": "aiml_engine_scanner",
        }}
        _MERGE_SQL = {sql!r}


        def sweep(connection):
            with connection.cursor() as cursor:
                cursor.execute(_MERGE_SQL)
        '''.format(sql=_MERGE_CTE_SQL),
    )
    verdict = install.derive_engine_scanner_privilege_split(
        root, manifest_path=MANIFEST_PATH
    )
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    assert any("data_modifying_cte:MERGE" in reason for reason in verdict["reasons"])
    assert any("retention_table_mutation" in reason for reason in verdict["reasons"])
    # MERGE 的 WHEN MATCHED 分支可刪列 → 與 head-DELETE 同等禁止。
    assert any("delete_statement_forbidden" in reason for reason in verdict["reasons"])


# --------------------------------------------------------------------------- #
# W2 P2-E:module 層級 / lambda 的 execute 不得靜默漏掃
# --------------------------------------------------------------------------- #
def test_module_level_and_lambda_execute_are_scanned(tmp_path: Path) -> None:
    root = _write_synthetic_tree(
        tmp_path,
        consumer_source="""
        _LOCAL_DSN_REQUIRED = {
            "host": "127.0.0.1",
            "port": "5432",
            "dbname": "trading_ai",
            "user": "aiml_engine_scanner",
        }
        _BOOTSTRAP = connection.cursor().execute(
            "DELETE FROM learning.alr_source_events"
        )
        _SWEEP = lambda cursor: cursor.execute(
            "DELETE FROM learning.alr_derived_cache_entries"
        )
        """,
    )
    inventory = install.build_engine_scanner_sql_inventory(root)
    module_level = [
        entry for entry in inventory["statements"] if entry["function"] == "<module>"
    ]
    assert len(module_level) == 2, inventory["statements"]
    verdict = install.derive_engine_scanner_privilege_split(
        root, manifest_path=MANIFEST_PATH
    )
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    assert sum("delete_statement_forbidden" in r for r in verdict["reasons"]) == 2


def test_module_level_unresolvable_execute_is_fail_closed(tmp_path: Path) -> None:
    root = _write_synthetic_tree(
        tmp_path,
        consumer_source="""
        import os

        _LOCAL_DSN_REQUIRED = {
            "host": "127.0.0.1",
            "port": "5432",
            "dbname": "trading_ai",
            "user": "aiml_engine_scanner",
        }
        _BOOTSTRAP = connection.cursor().execute(os.environ["SQL"])
        """,
    )
    inventory = install.build_engine_scanner_sql_inventory(root)
    assert [entry["function"] for entry in inventory["unresolved"]] == ["<module>"]
    verdict = install.derive_engine_scanner_privilege_split(
        root, manifest_path=MANIFEST_PATH
    )
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    assert any("not statically resolvable" in r for r in verdict["reasons"])


# --------------------------------------------------------------------------- #
# W2 P2-D:repo-local-looking 但解析不到的 import 必須 fail-closed
# --------------------------------------------------------------------------- #
def test_dotted_repo_local_import_that_does_not_resolve_is_refused(
    tmp_path: Path,
) -> None:
    root = _write_synthetic_tree(
        tmp_path,
        consumer_source="""
        _LOCAL_DSN_REQUIRED = {
            "host": "127.0.0.1",
            "port": "5432",
            "dbname": "trading_ai",
            "user": "aiml_engine_scanner",
        }
        from ml_training.hidden.retention_backdoor import purge
        """,
    )
    inventory = install.build_engine_scanner_sql_inventory(root)
    assert inventory["unresolved_imports"] == [
        "repo-local import does not resolve to a scanned module: "
        "ml_training.hidden.retention_backdoor"
    ]
    verdict = install.derive_engine_scanner_privilege_split(
        root, manifest_path=MANIFEST_PATH
    )
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    assert any(
        "import closure is not statically resolvable" in reason
        for reason in verdict["reasons"]
    )


def test_stdlib_and_package_root_imports_are_not_flagged(tmp_path: Path) -> None:
    """反向防呆:stdlib/第三方/純套件根名不得被誤判(否則真樹會假紅)。"""
    for name in ("os", "psycopg2.extras", "urllib.request", "ml_training", "program_code"):
        assert install._engine_scanner_unresolved_import_reason(ROOT, name) is None
    # repo 實體佈局的 program_code.ml_training.X 必須「真的解析到」同一個檔案
    resolved = install._engine_scanner_resolve_module(
        ROOT, "program_code.ml_training.alr_safe_file"
    )
    assert resolved is not None and resolved[0] == "alr_safe_file"


def test_real_manifest_passes_central_validator_and_forgery_is_rejected() -> None:
    manifest = _load_manifest()
    assert validator.validate_aiml_artifact(manifest) == []
    forged = copy.deepcopy(manifest)
    forged["tables"][0]["privileges"] = ["SELECT"]
    # 不重簽 self_digest → 中央閘拒。
    assert any(
        "self_digest" in error for error in validator.validate_aiml_artifact(forged)
    )


# --------------------------------------------------------------------------- #
# 合成違規樹:typed refusal
# --------------------------------------------------------------------------- #
def test_reintroduced_retention_import_is_refused(tmp_path: Path) -> None:
    root = _write_synthetic_tree(
        tmp_path,
        consumer_source="""
        _LOCAL_DSN_REQUIRED = {
            "host": "127.0.0.1",
            "port": "5432",
            "dbname": "trading_ai",
            "user": "aiml_engine_scanner",
        }
        from ml_training.alr_retention_repository import run_retention_pass


        def loop(connection):
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT source_ts FROM learning.alr_consumer_events WHERE lane = %s",
                    ("FRESH",),
                )
        """,
        extra={
            "alr_retention_repository.py": """
            def run_retention_pass(connection):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM learning.alr_derived_cache_entries WHERE cache_key = %s",
                        ("k",),
                    )
            """,
        },
    )
    verdict = install.derive_engine_scanner_privilege_split(
        root, manifest_path=MANIFEST_PATH
    )
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    assert any(
        "retention module is import-reachable" in reason for reason in verdict["reasons"]
    )
    assert any("delete_statement_forbidden" in reason for reason in verdict["reasons"])
    assert any("retention_table_mutation" in reason for reason in verdict["reasons"])


def test_consumer_delete_statement_is_refused_even_without_retention_import(
    tmp_path: Path,
) -> None:
    root = _write_synthetic_tree(
        tmp_path,
        consumer_source="""
        _LOCAL_DSN_REQUIRED = {
            "host": "127.0.0.1",
            "port": "5432",
            "dbname": "trading_ai",
            "user": "aiml_engine_scanner",
        }


        def purge(connection):
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM learning.alr_source_events WHERE source_key = %s",
                    ("k",),
                )
        """,
    )
    verdict = install.derive_engine_scanner_privilege_split(
        root, manifest_path=MANIFEST_PATH
    )
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    assert verdict["retention_forbidden_reachable"] == []
    assert any("delete_statement_forbidden" in reason for reason in verdict["reasons"])


def test_unresolvable_dynamic_sql_is_refused(tmp_path: Path) -> None:
    root = _write_synthetic_tree(
        tmp_path,
        consumer_source="""
        _LOCAL_DSN_REQUIRED = {
            "host": "127.0.0.1",
            "port": "5432",
            "dbname": "trading_ai",
            "user": "aiml_engine_scanner",
        }


        def sneaky(connection, table):
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM " + table)
        """,
    )
    verdict = install.derive_engine_scanner_privilege_split(
        root, manifest_path=MANIFEST_PATH
    )
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    assert any(
        "not statically resolvable" in reason for reason in verdict["reasons"]
    )


# --------------------------------------------------------------------------- #
# manifest 竄改:over-grant / unlisted / 讀取失敗
# --------------------------------------------------------------------------- #
def _rewrite_manifest(tmp_path: Path, mutate) -> Path:
    manifest = _load_manifest()
    mutate(manifest)
    manifest["self_digest"] = validator.artifact_self_digest(manifest)
    target = tmp_path / "pg_acl_manifest_v1.json"
    target.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def test_over_grant_in_manifest_is_refused(tmp_path: Path) -> None:
    def add_retention_insert(manifest: dict) -> None:
        for entry in manifest["tables"]:
            if entry["name"] == "learning.alr_retention_events":
                entry["privileges"] = ["INSERT", "SELECT"]

    target = _rewrite_manifest(tmp_path, add_retention_insert)
    verdict = install.derive_engine_scanner_privilege_split(manifest_path=target)
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    assert any(
        "never exercised: learning.alr_retention_events INSERT" in reason
        for reason in verdict["reasons"]
    )


def test_unlisted_statement_privilege_is_refused(tmp_path: Path) -> None:
    def drop_scanner_read(manifest: dict) -> None:
        manifest["tables"] = [
            entry
            for entry in manifest["tables"]
            if entry["name"] != "trading.scanner_snapshots"
        ]

    target = _rewrite_manifest(tmp_path, drop_scanner_read)
    verdict = install.derive_engine_scanner_privilege_split(manifest_path=target)
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    assert any(
        "unlisted: trading.scanner_snapshots" in reason for reason in verdict["reasons"]
    )


def test_missing_manifest_is_refused(tmp_path: Path) -> None:
    verdict = install.derive_engine_scanner_privilege_split(
        manifest_path=tmp_path / "absent.json"
    )
    assert verdict["status"] == "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED"
    assert any("unreadable" in reason for reason in verdict["reasons"])


# --------------------------------------------------------------------------- #
# grant SQL 生成器封閉性
# --------------------------------------------------------------------------- #
def test_grant_sql_is_closed_and_deterministic() -> None:
    manifest = _load_manifest()
    statements = install.generate_engine_scanner_grant_sql(manifest)
    assert statements == install.generate_engine_scanner_grant_sql(manifest)
    grants = [statement for statement in statements if statement.startswith("GRANT")]
    assert grants, "manifest must produce at least one grant"
    for statement in statements:
        assert "WITH GRANT OPTION" not in statement
        assert "OWNER" not in statement
    for statement in grants:
        assert (
            statement.startswith("GRANT CONNECT ON DATABASE")
            or statement.startswith("GRANT USAGE ON SCHEMA")
            or statement.startswith("GRANT INSERT, SELECT ON TABLE")
            or statement.startswith("GRANT SELECT ON TABLE")
            or statement.startswith("GRANT INSERT ON TABLE")
        ), statement
        # 無 wildcard、無 CREATE/TEMP、無 role membership(GRANT <role> TO ...)。
        assert " ALL " not in statement
        assert "CREATE" not in statement
        assert "TEMP" not in statement


def test_grant_sql_rejects_tampered_manifest() -> None:
    manifest = _load_manifest()
    manifest["role_name"] = "aiml_engine_scanner"
    manifest["tables"][0]["privileges"] = ["SELECT"]
    # 未重簽 → 生成器 fail-closed。
    try:
        install.generate_engine_scanner_grant_sql(manifest)
    except ValueError as error:
        assert "rejected" in str(error)
    else:  # pragma: no cover - 防呆
        raise AssertionError("tampered manifest must be rejected")
