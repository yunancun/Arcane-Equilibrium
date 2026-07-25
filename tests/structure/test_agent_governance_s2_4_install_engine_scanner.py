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
