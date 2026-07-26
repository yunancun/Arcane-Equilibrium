"""S2.4(WP4·W3b)PG_ROLE_ACL_MIGRATION 的 disposable apply→postcheck→rollback 實證。

Gated on ``shutil.which("initdb")`` + ``psycopg2``(缺任一 → 整模組誠實 SKIP,絕不假 pass;
鏡 W2a 的 ``..._install_engine_scanner_disposable`` 慣例)。當 PG binaries 在場時,本檔用
**真** throwaway cluster 跑 :func:`agent_governance_s2_4_apply.apply_s2_4_pg_role_acl`,
driver 是本檔的真 psycopg2 實作(不是 fake):

1. ``initdb`` 建 socket-only / ``scram-sha-256`` 叢集,建庫 ``trading_ai``,套真 migrations;
2. 擷取**精確 catalog 前態**(pg_roles 屬性列 + datacl/nspacl/relacl 全文)並折成 digest;
3. 跑真 apply:角色由 broker 的 sealed handle 建立(密碼從不出現在任何字串/argv/日誌),
   grants 恰為封閉 manifest 生成序列;
4. 真證據:以該角色**真的** SCRAM 登入成功;manifest 上每一格 grant 都可用;
   over-grant(DELETE/UPDATE retention、TRUNCATE、CREATE TABLE/SCHEMA/TEMP)全數觀察到真
   ``42501``;
5. 讓獨立 postcheck 回 FAIL → 模組走 ownership-aware 逆向補償 → **catalog digest 逐位元組
   回到步驟 2 的前態**,且該角色再也無法登入。

誠實界線(本主機能證/不能證):

* 真:role/ACL 的 apply→postcheck→rollback 與 catalog 精確還原、真 42501、真 SCRAM 登入;
* **非**真:§8.2 的 ``127.0.0.1:5432`` runtime listener / HBA / proxy 拓撲——throwaway 叢集是
  socket-only,不會也不該去搶佔本機 5432。故 topology attestation 的 listener/HBA/admin 欄位
  是**契約 fixture**,而 ``system_identifier`` / database OID / server major version 是自本
  叢集**真實查詢**的觀測值。真拓撲 attestation 屬 W6B 的獨立 OPS producer。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE, ROOT / "tests/structure"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_apply as apply_mod  # noqa: E402
import agent_governance_s2_4_credential as credential  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")
psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 driver is required")

pytestmark = pytest.mark.skipif(
    not (INITDB and PG_CTL),
    reason="initdb/pg_ctl are absent; the disposable PG_ROLE_ACL_MIGRATION proof cannot run",
)

DB = "trading_ai"
ROLE = "aiml_engine_scanner"
MANIFEST = deepcopy(kit.PG_ACL_MANIFEST)
MIGRATIONS = (
    "sql/migrations/V030__scanner_snapshots.sql",
    "sql/migrations/V151__alr_persistence_foundation.sql",
    "sql/migrations/V152__alr_operational_artifacts.sql",
    "sql/migrations/V153__alr_outcome_feedback.sql",
    "sql/migrations/V154__alr_retention_guardian.sql",
    "sql/migrations/V155__alr_health_state.sql",
    "sql/migrations/V156__alr_consumer_freshness_state.sql",
)
CLEAN_SUBPROCESS_ENV = {"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C"}
_CLUSTER_IDENTITY_DDL = """
CREATE TABLE IF NOT EXISTS learning.alr_runtime_cluster_identity_v1 (
    system_identifier   text    NOT NULL,
    database_oid        integer NOT NULL,
    server_major_version integer NOT NULL,
    runtime_host        text    NOT NULL,
    runtime_port        integer NOT NULL,
    runtime_dbname      text    NOT NULL,
    binding_nonce       text    NOT NULL,
    singleton           boolean NOT NULL DEFAULT true UNIQUE CHECK (singleton)
)
"""
_PLAN_DIGEST = "sha256:" + "1" * 64
_PRE_STATE = "sha256:" + "2" * 64
_OVER_GRANT_PROBES = (
    ("retention_delete", "DELETE FROM learning.alr_derived_cache_entries"),
    ("retention_update", "UPDATE learning.alr_derived_cache_entries SET cache_state = 'ACTIVE'"),
    ("source_truncate", "TRUNCATE learning.alr_source_events"),
    ("schema_create_table", "CREATE TABLE learning.evil (id integer)"),
    ("database_create_schema", "CREATE SCHEMA evil_schema"),
    ("database_temp", "CREATE TEMP TABLE evil_tmp (id integer)"),
)


def _run(cmd, *, logfile, timeout):
    result = subprocess.run(
        cmd, env=CLEAN_SUBPROCESS_ENV, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=timeout,
    )
    if result.returncode != 0:
        detail = ""
        try:
            detail = Path(logfile).read_text(encoding="utf-8")[-800:]
        except OSError:
            pass
        raise RuntimeError(f"command failed rc={result.returncode}: {cmd[0]}\n{detail}")


@pytest.fixture(scope="module")
def cluster():
    tmp = tempfile.mkdtemp(prefix="aiml_s24_w3b_")
    data_dir = os.path.join(tmp, "data")
    sock_dir = os.path.join(tmp, "sock")
    logfile = os.path.join(tmp, "server.log")
    os.makedirs(sock_dir)
    started = False
    try:
        _run([INITDB, "-D", data_dir, "-U", "postgres", "--auth=trust", "-E", "UTF8", "-N"],
             logfile=logfile, timeout=90)
        with open(os.path.join(data_dir, "postgresql.auto.conf"), "a", encoding="utf-8") as handle:
            handle.write("\nlisten_addresses = ''\n")
            handle.write(f"unix_socket_directories = '{sock_dir}'\n")
            handle.write("fsync = off\n")
            handle.write("password_encryption = 'scram-sha-256'\n")
            handle.write("lc_messages = 'C'\n")
        with open(os.path.join(data_dir, "pg_hba.conf"), "w", encoding="utf-8") as handle:
            handle.write("local   all   postgres   trust\n")
            handle.write("local   all   all        scram-sha-256\n")
        _run([PG_CTL, "-D", data_dir, "-l", logfile, "-w", "-t", "40", "start"],
             logfile=logfile, timeout=60)
        started = True
        _bootstrap(sock_dir)
        yield {"socket_dir": sock_dir}
    finally:
        if started or os.path.exists(os.path.join(data_dir, "postmaster.pid")):
            try:
                subprocess.run([PG_CTL, "-D", data_dir, "-m", "immediate", "stop"],
                               env=CLEAN_SUBPROCESS_ENV, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def _bootstrap(sock_dir: str) -> None:
    """建庫 + 真 migrations + 叢集身分列。角色/ACL **刻意不建**——那是被測的 apply 路徑。"""

    bootstrap = psycopg2.connect(host=sock_dir, dbname="postgres", user="postgres", connect_timeout=10)
    bootstrap.autocommit = True
    try:
        bootstrap.cursor().execute(f"CREATE DATABASE {DB}")
    finally:
        bootstrap.close()
    admin = _admin(sock_dir)
    try:
        cur = admin.cursor()
        cur.execute("CREATE SCHEMA IF NOT EXISTS trading")
        for rel in MIGRATIONS:
            cur.execute((ROOT / rel).read_text(encoding="utf-8"))
        cur.execute(_CLUSTER_IDENTITY_DDL)
    finally:
        admin.close()


def _admin(sock_dir: str):
    connection = psycopg2.connect(host=sock_dir, dbname=DB, user="postgres", connect_timeout=10)
    connection.autocommit = True
    return connection


# ── 真 catalog 前/後態快照 ──────────────────────────────────────────────────────
#
# 「exact 還原」的判準是**有效權限**(每個 grantee × 每個 privilege),不是 acl 欄位的原始
# 文字。真跑實證的 PostgreSQL 事實:一個從未被授/收過權的物件其 ``datacl``/``nspacl``/
# ``relacl`` 是 ``NULL``(隱含預設);只要發生過任何 GRANT/REVOKE,catalog 就把它**物化**成
# 一個顯式陣列,即使語義完全等價也**永不回到 NULL**。故本檔:
#   * ``effective``(has_*_privilege 逐格)必須逐位元組相等 —— 這是 §5.4「exact 還原」的
#     load-bearing 性質;
#   * ``acl_text`` 只作資訊性記錄,並由 :func:`test_..._records_the_acl_materialisation` 明文
#     記下這個「NULL → 等價顯式陣列」的表示層變化,絕不假裝它沒發生。
_DATABASE_PRIVILEGES = ("CONNECT", "TEMPORARY", "CREATE")
_SCHEMA_PRIVILEGES = ("USAGE", "CREATE")
_TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


def _catalog_snapshot(sock_dir: str) -> dict:
    admin = _admin(sock_dir)
    try:
        cur = admin.cursor()
        cur.execute(
            "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolcanlogin, "
            "rolreplication, rolbypassrls, rolconnlimit FROM pg_roles WHERE rolname = %s",
            (ROLE,),
        )
        role_row = cur.fetchone()
        grantees = ["public"] + ([ROLE] if role_row else [])
        effective: dict[str, bool] = {}
        for grantee in grantees:
            for privilege in _DATABASE_PRIVILEGES:
                cur.execute("SELECT has_database_privilege(%s, %s, %s)", (grantee, DB, privilege))
                effective[f"{grantee}|database:{DB}|{privilege}"] = bool(cur.fetchone()[0])
            for entry in MANIFEST["schemas"]:
                for privilege in _SCHEMA_PRIVILEGES:
                    cur.execute(
                        "SELECT has_schema_privilege(%s, %s, %s)",
                        (grantee, entry["name"], privilege),
                    )
                    effective[f"{grantee}|schema:{entry['name']}|{privilege}"] = bool(
                        cur.fetchone()[0]
                    )
            for entry in MANIFEST["tables"]:
                for privilege in _TABLE_PRIVILEGES:
                    cur.execute(
                        "SELECT has_table_privilege(%s, %s, %s)",
                        (grantee, entry["name"], privilege),
                    )
                    effective[f"{grantee}|table:{entry['name']}|{privilege}"] = bool(
                        cur.fetchone()[0]
                    )
        cur.execute("SELECT datacl::text FROM pg_database WHERE datname = %s", (DB,))
        datacl = cur.fetchone()[0]
        cur.execute(
            "SELECT nspname, nspacl::text FROM pg_namespace WHERE nspname = ANY(%s) ORDER BY nspname",
            ([entry["name"] for entry in MANIFEST["schemas"]],),
        )
        schema_acls = [tuple(row) for row in cur.fetchall()]
        table_names = [entry["name"] for entry in MANIFEST["tables"]]
        cur.execute(
            "SELECT n.nspname || '.' || c.relname AS name, c.relacl::text FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname || '.' || c.relname = ANY(%s) ORDER BY 1",
            (table_names,),
        )
        table_acls = [tuple(row) for row in cur.fetchall()]
    finally:
        admin.close()
    return {
        "role": list(role_row) if role_row else None,
        "effective": effective,
        "acl_text": {
            "database_acl": datacl,
            "schema_acls": schema_acls,
            "table_acls": table_acls,
        },
    }


def _snapshot_digest(snapshot: dict) -> str:
    """exact-restoration digest:只折 role 屬性列 + 有效權限矩陣(見上方 ACL 物化說明)。"""

    return validator.canonical_digest(
        json.loads(json.dumps(
            {"role": snapshot["role"], "effective": snapshot["effective"]}, default=str
        ))
    )


# ── 真 driver(psycopg2;無任何 caller SQL 入口)──────────────────────────────────
class _DisposablePgDriver:
    """本檔的**真** PG driver:每個方法只執行本模組生成/參數化的固定操作。"""

    evidence_class = "STRUCTURAL_ONLY"  # 丟棄式叢集絕非 platform-attested runtime 證據

    def __init__(self, sock_dir: str, *, postcheck_ok: bool = True) -> None:
        self.sock_dir = sock_dir
        self.postcheck_ok = postcheck_ok
        self.calls: list[str] = []
        self.journal: list[dict] = []
        self.password: bytes | None = None
        # W4a:補償後的獨立 exact-還原判斷需要一個「動手之前」的真基線。
        self.baseline_digest = _snapshot_digest(_catalog_snapshot(sock_dir))

    def _cursor(self):
        return _admin(self.sock_dir)

    def journal_transition(self, *, entry):
        self.calls.append("journal:" + entry["state"])
        self.journal.append(dict(entry))

    def observe_role(self, *, role_name):
        self.calls.append("observe_role")
        admin = self._cursor()
        try:
            cur = admin.cursor()
            cur.execute("SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname = %s", (role_name,))
            row = cur.fetchone()
        finally:
            admin.close()
        return {"attributes": {"rolname": row[0], "rolcanlogin": row[1]}} if row else None

    def create_role_with_sealed_password(self, *, role_name, secret_handle, operation_id):
        self.calls.append("create_role_with_sealed_password")
        # 密碼只經 sealed handle → 立即用參數化語句消費;絕不進 argv/日誌/回傳值。
        password = secret_handle.consume(operation_id=operation_id)
        self.password = password
        admin = self._cursor()
        try:
            admin.cursor().execute(
                f'CREATE ROLE "{role_name}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %s',
                (password.decode("ascii"),),
            )
        finally:
            admin.close()

    def observe_public_defaults(self, *, database, schemas):
        self.calls.append("observe_public_defaults")
        admin = self._cursor()
        try:
            cur = admin.cursor()
            observed: dict[str, bool] = {}
            for privilege in ("TEMPORARY", "CREATE"):
                cur.execute(
                    "SELECT has_database_privilege('public', %s, %s)", (database, privilege)
                )
                observed[f"database:{database}:{privilege}"] = bool(cur.fetchone()[0])
            for schema in schemas:
                cur.execute("SELECT has_schema_privilege('public', %s, 'CREATE')", (schema,))
                observed[f"schema:{schema}:CREATE"] = bool(cur.fetchone()[0])
        finally:
            admin.close()
        return observed

    def apply_manifest_grants(self, *, generated_statements):
        self.calls.append("apply_manifest_grants")
        self._execute_all(generated_statements)

    def revoke_manifest_grants(self, *, generated_statements):
        self.calls.append("revoke_manifest_grants")
        self._execute_all(generated_statements)

    def restore_public_defaults(self, *, generated_statements):
        self.calls.append("restore_public_defaults")
        self._execute_all(generated_statements)

    def _execute_all(self, statements):
        admin = self._cursor()
        try:
            cur = admin.cursor()
            for statement in statements:
                cur.execute(statement)
        finally:
            admin.close()

    def observe_grants(self, *, role_name):
        self.calls.append("observe_grants")
        admin = self._cursor()
        try:
            cur = admin.cursor()
            observed = {}
            for entry in MANIFEST["tables"]:
                privileges = sorted(
                    privilege
                    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
                    if _has_table_privilege(cur, role_name, entry["name"], privilege)
                )
                observed[entry["name"]] = privileges
        finally:
            admin.close()
        return observed

    def drop_task_owned_role(self, *, role_name):
        self.calls.append("drop_task_owned_role")
        admin = self._cursor()
        try:
            admin.cursor().execute(f'DROP ROLE "{role_name}"')
        finally:
            admin.close()

    def independent_postcheck(self, *, component_effect_class, install_plan_digest, applier_node):
        """相異 verifier 節點的獨立觀測。

        W4a:同一個方法會在**補償之後**被重跑,故它必須回答「呼叫當下」的真叢集狀態——
        補償後 ``applied_state_verified`` 由「角色是否還在」實測,``pre_state_lineage_verified``
        由「當下快照是否等於本 driver 建構時擷取的基線」實測(這才是獨立的 exact 還原證據)。
        """

        self.calls.append("independent_postcheck")
        snapshot = _catalog_snapshot(self.sock_dir)
        digest = _snapshot_digest(snapshot)
        if any(
            call in {"drop_task_owned_role", "revoke_manifest_grants", "restore_public_defaults"}
            for call in self.calls
        ):
            return {
                "verifier_node": "s2-4-disposable-verifier",
                "observed_subject_digest": digest,
                "applied_state_verified": snapshot.get("role") is not None,
                "pre_state_lineage_verified": digest == self.baseline_digest,
                "verifier_capture_digest": kit.CAPTURE_DIGEST,
            }
        return {
            "verifier_node": "s2-4-disposable-verifier",
            "observed_subject_digest": digest,
            "applied_state_verified": self.postcheck_ok,
            "pre_state_lineage_verified": self.postcheck_ok,
            "verifier_capture_digest": kit.CAPTURE_DIGEST,
        }

    def trusted_host_time(self):
        return kit.NOW


def _has_table_privilege(cur, role: str, table: str, privilege: str) -> bool:
    cur.execute("SELECT has_table_privilege(%s, %s, %s)", (role, table, privilege))
    return bool(cur.fetchone()[0])


# ── 契約 fixture:topology attestation(叢集身分為真觀測、listener/HBA 為契約值)──
def _observed_topology(sock_dir: str) -> dict:
    admin = _admin(sock_dir)
    try:
        cur = admin.cursor()
        cur.execute(
            "SELECT (pg_control_system()).system_identifier::text, "
            "(SELECT oid FROM pg_database WHERE datname = current_database())::integer, "
            "current_setting('server_version')"
        )
        system_identifier, database_oid, server_version = cur.fetchone()
    finally:
        admin.close()
    observation = kit.topology_observation()
    observation["cluster_identity"]["system_identifier"] = str(system_identifier)
    observation["cluster_identity"]["database_oid"] = int(database_oid)
    observation["cluster_identity"]["server_version"] = str(server_version)
    return observation


def _pg_intent(attestation: dict) -> dict:
    return apply_mod.build_component_effect_intent(
        component_effect_class="PG_ROLE_ACL_MIGRATION",
        install_plan_digest=_PLAN_DIGEST, pre_state_digest=_PRE_STATE,
        required_intent_fields={
            "topology_attestation_digest": attestation["self_digest"],
            "acl_manifest_digest": MANIFEST["self_digest"],
            "pg_migration_permit_digest": "sha256:" + "6" * 64,
            "admin_handle_descriptor_digest": "sha256:" + "7" * 64,
        },
        expires_at=kit.EXPIRES,
    )


_KEY_SEQ = [0]


def _authorizations(tmp_path, monkeypatch):
    _KEY_SEQ[0] += 1
    private_key, public_key, fingerprint = kit.mint_key(
        tmp_path, name=f"w3b-pg-operator-{_KEY_SEQ[0]}"
    )
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    # W4a:兩張 permit 都綁同一份 plan(payload_binding → 導出 authorization_id)。
    return {
        "apply_aggregate": kit.authorization(
            private_key, profile_key="apply_aggregate",
            payload_binding=kit.apply_payload_binding("apply_aggregate"),
        ),
        "pg_migration": kit.authorization(
            private_key, profile_key="pg_migration",
            payload_binding=kit.apply_payload_binding("pg_migration"),
        ),
    }


def _apply(cluster, tmp_path, monkeypatch, *, postcheck_ok: bool):
    attestation = kit.topology_attestation(_observed_topology(cluster["socket_dir"]))
    handle = credential.SecretBroker(
        operation_id="disposable-pg-op"
    ).mint_first_provisioning_handles()[0]
    driver = _DisposablePgDriver(cluster["socket_dir"], postcheck_ok=postcheck_ok)
    verdict = apply_mod.apply_s2_4_pg_role_acl(
        _pg_intent(attestation), _authorizations(tmp_path, monkeypatch), driver,
        acl_manifest=deepcopy(MANIFEST), topology_attestation=attestation,
        expected_topology=kit.topology_expected(attestation), secret_handle=handle,
        operation_id="disposable-pg-op", replay_ledger=kit.replay_ledger(),
        now=kit.NOW, clock=kit.frozen_clock(),
    )
    return verdict, driver


def _compensate_manually(driver, public_pre_state: dict) -> None:
    """測試自身的收尾:走模組**自己**生成的 revoke / PUBLIC-restore / drop 序列。"""

    driver.revoke_manifest_grants(
        generated_statements=apply_mod.generate_manifest_revoke_statements(deepcopy(MANIFEST))
    )
    restore = apply_mod.generate_public_default_restore_statements(
        deepcopy(MANIFEST), public_pre_state
    )
    if restore:
        driver.restore_public_defaults(generated_statements=restore)
    driver.drop_task_owned_role(role_name=ROLE)


# ═══════════════════════ apply → postcheck → rollback 全循環 ═══════════════════
def test_disposable_apply_postcheck_rollback_restores_exact_catalog_state(
    cluster, tmp_path, monkeypatch
) -> None:
    """真 apply → 獨立 postcheck FAIL → ownership-aware 逆向補償 → catalog 逐位元組還原。"""

    sock = cluster["socket_dir"]
    before = _catalog_snapshot(sock)
    assert before["role"] is None, "the throwaway cluster must not pre-create the scanner role"
    before_digest = _snapshot_digest(before)

    rolled, driver = _apply(cluster, tmp_path, monkeypatch, postcheck_ok=False)

    assert rolled["status"] == "POSTCHECK_FAILED_ROLLED_BACK", rolled["reasons"]
    assert rolled["mutation_performed"] is True and rolled["driver_engaged"] is True
    assert rolled["postcheck"]["status"] == "FAIL"
    assert rolled["postcheck"]["verifier_node"] != rolled["postcheck"]["applier_node"]
    assert rolled["rollback"]["status"] == "COMPENSATED_EXACT"
    assert rolled["rollback"]["ownership_aware"] is True
    assert rolled["rollback"]["exact_pre_state_restored"] is True
    assert rolled["rollback"]["no_secret_reconstructed"] is True
    assert validator.validate_aiml_artifact(rolled["postcheck"]) == []
    assert validator.validate_aiml_artifact(rolled["rollback"]) == []
    # 真的建過角色與 grants(不是「什麼都沒做」的假成功)。
    assert "create_role_with_sealed_password" in driver.calls
    assert "apply_manifest_grants" in driver.calls
    assert "revoke_manifest_grants" in driver.calls
    assert "drop_task_owned_role" in driver.calls
    assert "restore_public_defaults" in driver.calls
    # catalog 逐位元組回到前態(pg_roles 屬性列 + datacl/nspacl/relacl 全文)。
    after = _catalog_snapshot(sock)
    assert after["role"] is None
    assert _snapshot_digest(after) == before_digest, {"before": before, "after": after}
    # 被 drop 的角色再也無法登入(真 authentication 失敗)。
    with pytest.raises(psycopg2.Error):
        psycopg2.connect(
            host=sock, dbname=DB, user=ROLE,
            password=driver.password.decode("ascii"), connect_timeout=5,
        )
    # production 旗標恆假:丟棄式叢集絕不是 runtime PASS。
    assert rolled["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }


def test_disposable_successful_apply_proves_real_login_and_real_42501(
    cluster, tmp_path, monkeypatch
) -> None:
    """真 apply(postcheck PASS):真 SCRAM 登入、manifest 每格 grant 可用、over-grant 真 42501。"""

    sock = cluster["socket_dir"]
    before = _catalog_snapshot(sock)
    assert before["role"] is None
    before_digest = _snapshot_digest(before)
    probe = _DisposablePgDriver(sock)
    public_pre_state = probe.observe_public_defaults(
        database=DB, schemas=[entry["name"] for entry in MANIFEST["schemas"]]
    )

    verdict, driver = _apply(cluster, tmp_path, monkeypatch, postcheck_ok=True)
    try:
        assert verdict["status"] == "SATISFIED", verdict["reasons"]
        assert verdict["result"]["status"] == "SATISFIED"
        assert validator.validate_aiml_artifact(verdict["result"]) == []
        assert validator.validate_aiml_artifact(verdict["postcheck"]) == []
        assert verdict["result"]["evidence_class"] == "STRUCTURAL_ONLY"
        applied = _catalog_snapshot(sock)
        assert applied["role"] is not None and applied["role"][5] is True  # rolcanlogin
        assert _snapshot_digest(applied) != before_digest

        # 真 SCRAM 登入:密碼只從 sealed handle 進過參數化 CREATE ROLE。
        password = driver.password.decode("ascii")
        connection = psycopg2.connect(
            host=sock, dbname=DB, user=ROLE, password=password, connect_timeout=10
        )
        connection.autocommit = True
        try:
            cur = connection.cursor()
            for entry in MANIFEST["tables"]:
                if "SELECT" in entry["privileges"]:
                    cur.execute(f'SELECT * FROM {entry["name"]} LIMIT 0')
            for name, statement in _OVER_GRANT_PROBES:
                with pytest.raises(psycopg2.Error) as denial:
                    cur.execute(statement)
                assert denial.value.pgcode == "42501", (name, denial.value.pgcode)
        finally:
            connection.close()
        # 任何序列化面都沒有密碼(或其常見編碼形)。
        for artifact in (verdict["result"], verdict["postcheck"], verdict["rollback"],
                         verdict["reasons"], verdict["journal_entries"],
                         verdict["observed_subjects"]):
            credential.assert_no_secret_material(artifact, [password])
    finally:
        _compensate_manually(driver, public_pre_state)
    # 收尾同樣走模組生成序列 → catalog 再次逐位元組回到前態。
    assert _snapshot_digest(_catalog_snapshot(sock)) == before_digest


def test_disposable_rollback_records_the_acl_materialisation_honestly(
    cluster, tmp_path, monkeypatch
) -> None:
    """明文記錄 PostgreSQL 的表示層事實:``NULL`` 預設 ACL 一旦被動過就永不回到 ``NULL``。

    有效權限矩陣完全還原(上一個測試已證);但 ``datacl``/``nspacl`` 從 ``NULL`` 被物化成
    語義等價的顯式陣列。本測試把該差異**顯式斷言出來**,而不是讓 digest 假裝它沒發生。
    """

    sock = cluster["socket_dir"]
    before = _catalog_snapshot(sock)
    rolled, _driver = _apply(cluster, tmp_path, monkeypatch, postcheck_ok=False)
    assert rolled["status"] == "POSTCHECK_FAILED_ROLLED_BACK", rolled["reasons"]
    after = _catalog_snapshot(sock)

    # load-bearing:有效權限逐格相等。
    assert after["effective"] == before["effective"]
    assert after["role"] is None and before["role"] is None
    # 表示層:datacl 至少在第一次 apply 之後已被物化(非 NULL),且此後保持顯式。
    assert after["acl_text"]["database_acl"] is not None
    # 物化後的 datacl 只含 postgres owner 與 PUBLIC 的等價預設,絕無殘留的 scanner 授權。
    assert ROLE not in (after["acl_text"]["database_acl"] or "")
    for _name, acl in after["acl_text"]["schema_acls"]:
        assert ROLE not in (acl or "")
    for _name, acl in after["acl_text"]["table_acls"]:
        assert ROLE not in (acl or "")


def test_disposable_pre_existing_unowned_role_is_never_touched(
    cluster, tmp_path, monkeypatch
) -> None:
    """真叢集上先有同名角色 → typed PREEXISTING_UNOWNED_STATE,且其屬性一位元組未動。"""

    sock = cluster["socket_dir"]
    admin = _admin(sock)
    try:
        admin.cursor().execute(
            f'CREATE ROLE "{ROLE}" LOGIN NOSUPERUSER PASSWORD %s', ("pre-existing-unowned",)
        )
    finally:
        admin.close()
    before = _snapshot_digest(_catalog_snapshot(sock))
    try:
        verdict, driver = _apply(cluster, tmp_path, monkeypatch, postcheck_ok=True)
        assert verdict["status"] == "PREEXISTING_UNOWNED_STATE", verdict["reasons"]
        assert "create_role_with_sealed_password" not in driver.calls
        assert "apply_manifest_grants" not in driver.calls
        assert _snapshot_digest(_catalog_snapshot(sock)) == before
        # 既有角色的密碼仍然有效(絕未被 re-password)。
        psycopg2.connect(
            host=sock, dbname=DB, user=ROLE, password="pre-existing-unowned", connect_timeout=10
        ).close()
    finally:
        admin = _admin(sock)
        try:
            admin.cursor().execute(f'DROP ROLE IF EXISTS "{ROLE}"')
        finally:
            admin.close()
