"""S2.4(WP4·W3a)PG topology 唯讀 observer 的 focused 測試(§8.2 / §10.5 #25)。

證明:
- 5432 direct 與 5432-behind-proxy 兩種 fixture 都能證出 cluster/HBA 身分,且 admin
  endpoint(attested local socket / 5433)與 runtime endpoint **分離**;
- listener 漂移、proxy-config 漂移、cluster 不符、落在簽章 HBA 投影之外的條目、未經
  attest 的 admin endpoint、非 §8.2 封閉 DSN 的 runtime endpoint、過期證據,一律 typed
  ``PG_TOPOLOGY_UNPROVEN``;
- attestation 恆為 evidence-only(``derived_verdict`` const null,不自證判定);
- ``pg_topology_runtime_guard_v1`` 的欄位與 ``CLUSTER_IDENTITY_COLUMNS`` 契約逐欄對齊——
  渲染出的 guard 檔可被 consumer 側 §8.3 重連身分閘(``verify_connected_cluster_identity``)
  直接吃下並回 MATCH,錯配的身分列則 typed 失敗;
- 全程零 socket、零 psql:所有觀測皆為注入物。
"""
from __future__ import annotations

import ast
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_topology as topology  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
from ml_training import alr_application_identity as app_identity  # noqa: E402
from ml_training import alr_consumer_resilience as resilience  # noqa: E402


def _install_guard_with_required_posture(guard: dict, guard_file: Path) -> None:
    """把渲染好的 guard 以契約要求的 host 姿態落檔(§8.3 / W2 P2-4)。

    W3 的 topology observer 產出 guard 內容,佈署姿態(root:aiml-engine-scanner、
    mode 恰 0440)則由 W2 的 `verify_topology_guard_host_posture` 在信任內容之前執法。
    測試在無 root 的 checkout 上只能真寫 mode;owner/group 由 `guard_host_identity`
    唯一縫模擬(判定邏輯不動,故不可能放行 group-writable 或非 root 所有的 guard)。
    """

    guard_file.write_text(
        json.dumps(guard, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    guard_file.chmod(app_identity.TOPOLOGY_GUARD_REQUIRED_MODE)


@pytest.fixture(autouse=True)
def _simulate_guard_host_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    """無 root checkout 上模擬 guard 的真實 host 佈署身分(唯一縫;mode 仍照真檔驗)。"""

    monkeypatch.setattr(
        app_identity,
        "guard_host_identity",
        lambda st: (
            app_identity.TOPOLOGY_GUARD_REQUIRED_OWNER_UID,
            app_identity.TOPOLOGY_GUARD_REQUIRED_GROUP,
        ),
    )

# 凍結時鐘錨點(每次呼叫都顯式傳 now;與 wall clock 無關)。
_ANCHOR = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_OBSERVED_AT = _ANCHOR.isoformat()
_NOW = (_ANCHOR + timedelta(minutes=5)).isoformat()
_STALE_NOW = (_ANCHOR + timedelta(minutes=30)).isoformat()
_HEAD = "0" * 40
_HOST = "trade-core"
_NONCE = "topology-binding-nonce-1"
_FILE = {
    "device": 66306,
    "inode": 4242,
    "path": "/var/lib/postgresql/16/main",
    "digest": "sha256:" + "c" * 64,
}


def _observation(**overrides):
    observation = {
        "runtime_listener": {
            "socket_inode": 4242,
            "owning_pid": 1234,
            "owning_uid": 26,
            "executable_digest": "sha256:" + "a" * 64,
            "cgroup": "/system.slice/postgresql.service",
            "endpoint": "127.0.0.1:5432",
        },
        "proxy_hops": [],
        "admin_endpoint": {
            "endpoint_class": "attested_local_socket",
            "handle_class": "peer-authenticated-unix-socket",
        },
        "cluster_identity": {
            "system_identifier": "7000000000000000001",
            "server_version": "16.3",
            "database_oid": 16400,
            "postmaster_identity": "postmaster:1234",
            "reload_operation_id": "reload-0001",
        },
        "file_identities": {
            "data_dir": dict(_FILE),
            "config_file": {**_FILE, "path": "/etc/postgresql/16/main/postgresql.conf"},
            "hba_file": {**_FILE, "path": "/etc/postgresql/16/main/pg_hba.conf"},
        },
        "effective_hba_rule": {
            "source": "127.0.0.1/32",
            "database": "trading_ai",
            "user": "aiml_engine_scanner",
            "method": "scram-sha-256",
        },
        "end_to_end_reaches_cluster": True,
    }
    observation.update(deepcopy(overrides))
    return observation


def _proxied_observation():
    """5432 前面有一個 pooler:hop 必須帶不可變組態 digest 與 upstream endpoint。"""
    return _observation(proxy_hops=[
        {"config_digest": "sha256:" + "b" * 64, "upstream_endpoint": "127.0.0.1:6432"}
    ])


def _attest(observation, *, observed_at=_OBSERVED_AT):
    return topology.observe_pg_topology(
        observation, source_head=_HEAD, target_host=_HOST, observed_at=observed_at
    )


def _expected(attestation, *, hba_entries=None):
    entries = hba_entries or [dict(attestation["effective_hba_rule"])]
    return {
        "listener_config_digest": attestation["listener_config_digest"],
        "proxy_config_digest": attestation["proxy_config_digest"],
        "cluster_identity_digest": attestation["cluster_identity_digest"],
        "hba_projection": {
            "entries": entries,
            "projection_digest": validator.canonical_digest(entries),
        },
        "source_head": _HEAD,
        "target_host": _HOST,
    }


def _row(**overrides):
    row = {
        "system_identifier": "7000000000000000001",
        "database_oid": 16400,
        "server_major_version": 16,
        "runtime_host": "127.0.0.1",
        "runtime_port": 5432,
        "runtime_dbname": "trading_ai",
        "binding_nonce": _NONCE,
    }
    row.update(overrides)
    return row


# ── 正例:direct 與 proxy 兩種 fixture ───────────────────────────────────────────
@pytest.mark.parametrize("observation_factory", [_observation, _proxied_observation])
def test_direct_and_proxied_5432_fixtures_prove_cluster_and_hba_identity(observation_factory) -> None:
    attestation = _attest(observation_factory())
    assert validator.validate_aiml_artifact(attestation) == []
    assert attestation["topology_status"] == "PG_TOPOLOGY_EVIDENCE_CAPTURED"
    # evidence-only:判定恆 null,絕不自證。
    assert attestation["derived_verdict"] is None
    verdict = topology.derive_pg_topology_status(
        attestation, expected=_expected(attestation), now=_NOW
    )
    assert verdict == {"status": "PG_TOPOLOGY_PROVEN", "reasons": []}
    # runtime endpoint 與 admin endpoint 明確分離。
    assert attestation["runtime_listener"]["endpoint"] == "127.0.0.1:5432"
    assert attestation["admin_endpoint"]["endpoint_class"] in topology.ADMIN_ENDPOINT_CLASSES
    assert attestation["admin_endpoint"]["handle_class"] != "127.0.0.1:5432"


def test_separate_admin_endpoint_on_5433_is_accepted() -> None:
    attestation = _attest(_observation(admin_endpoint={
        "endpoint_class": "port_5433", "handle_class": "127.0.0.1:5433"
    }))
    assert topology.derive_pg_topology_status(
        attestation, expected=_expected(attestation), now=_NOW
    )["status"] == "PG_TOPOLOGY_PROVEN"


# ── 負例:六類漂移一律 PG_TOPOLOGY_UNPROVEN ────────────────────────────────────
def test_listener_drift_is_unproven() -> None:
    baseline = _attest(_observation())
    drifted = _attest(_observation(runtime_listener={
        "socket_inode": 9999,
        "owning_pid": 1234,
        "owning_uid": 26,
        "executable_digest": "sha256:" + "a" * 64,
        "cgroup": "/system.slice/postgresql.service",
        "endpoint": "127.0.0.1:5432",
    }))
    verdict = topology.derive_pg_topology_status(
        drifted, expected=_expected(baseline), now=_NOW
    )
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN"
    assert any("runtime listener drifted" in reason for reason in verdict["reasons"])


def test_proxy_config_drift_is_unproven() -> None:
    baseline = _attest(_proxied_observation())
    drifted = _attest(_observation(proxy_hops=[
        {"config_digest": "sha256:" + "f" * 64, "upstream_endpoint": "127.0.0.1:6432"}
    ]))
    verdict = topology.derive_pg_topology_status(
        drifted, expected=_expected(baseline), now=_NOW
    )
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN"
    assert any("proxy configuration drifted" in reason for reason in verdict["reasons"])


def test_unproved_proxy_hop_is_unproven() -> None:
    attestation = _attest(_observation(proxy_hops=[{"upstream_endpoint": "127.0.0.1:6432"}]))
    verdict = topology.derive_pg_topology_status(
        attestation, expected=_expected(attestation), now=_NOW
    )
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN"
    # closed schema 先擋(hop 必帶 config_digest);兩道閘任一都不放行未證的 hop。
    assert any("config_digest" in reason or "unproved proxy" in reason
               for reason in verdict["reasons"])


def test_cluster_mismatch_is_unproven() -> None:
    baseline = _attest(_observation())
    other = _attest(_observation(cluster_identity={
        "system_identifier": "7000000000000000002",
        "server_version": "16.3",
        "database_oid": 16400,
        "postmaster_identity": "postmaster:1234",
        "reload_operation_id": "reload-0001",
    }))
    verdict = topology.derive_pg_topology_status(
        other, expected=_expected(baseline), now=_NOW
    )
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN"
    assert any("cluster identity does not match" in reason for reason in verdict["reasons"])


def test_out_of_projection_hba_entry_is_unproven() -> None:
    attestation = _attest(_observation())
    signed_only = [{
        "source": "127.0.0.1/32",
        "database": "trading_ai",
        "user": "aiml_engine_scanner",
        "method": "scram-sha-256",
    }]
    widened = _attest(_observation(effective_hba_rule={
        "source": "127.0.0.1/32",
        "database": "trading_ai",
        "user": "postgres",              # 投影之外的角色
        "method": "scram-sha-256",
    }))
    verdict = topology.derive_pg_topology_status(
        widened, expected=_expected(attestation, hba_entries=signed_only), now=_NOW
    )
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN"
    assert any("outside the signed HBA projection" in r for r in verdict["reasons"])


@pytest.mark.parametrize("admin_endpoint", [
    {"endpoint_class": "attested_local_socket", "handle_class": "127.0.0.1:5432"},
    {"endpoint_class": "attested_local_socket", "handle_class": "   "},
])
def test_unattested_or_collapsed_admin_endpoint_is_unproven(admin_endpoint) -> None:
    attestation = _attest(_observation(admin_endpoint=admin_endpoint))
    verdict = topology.derive_pg_topology_status(
        attestation, expected=_expected(attestation), now=_NOW
    )
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN"


def test_non_closed_runtime_endpoint_is_unproven() -> None:
    attestation = _attest(_observation(runtime_listener={
        "socket_inode": 4242,
        "owning_pid": 1234,
        "owning_uid": 26,
        "executable_digest": "sha256:" + "a" * 64,
        "cgroup": "/system.slice/postgresql.service",
        "endpoint": "127.0.0.1:5433",     # worker 不得改 transport
    }))
    assert attestation["topology_status"] == "PG_TOPOLOGY_UNPROVEN"
    verdict = topology.derive_pg_topology_status(
        attestation, expected=_expected(attestation), now=_NOW
    )
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN"
    assert any("closed runtime endpoint" in reason for reason in verdict["reasons"])


def test_missing_end_to_end_assertion_is_unproven() -> None:
    attestation = _attest(_observation(end_to_end_reaches_cluster=False))
    verdict = topology.derive_pg_topology_status(
        attestation, expected=_expected(attestation), now=_NOW
    )
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN"


def test_expired_topology_evidence_cannot_be_refreshed_by_reference() -> None:
    attestation = _attest(_observation())
    verdict = topology.derive_pg_topology_status(
        attestation, expected=_expected(attestation), now=_STALE_NOW
    )
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN"
    assert any("short expiry window" in reason for reason in verdict["reasons"])


def test_self_declared_verdict_or_tampered_digest_is_unproven() -> None:
    attestation = _attest(_observation())
    tampered = deepcopy(attestation)
    tampered["cluster_identity"]["database_oid"] = 99999
    tampered["self_digest"] = validator.artifact_self_digest(tampered)
    verdict = topology.derive_pg_topology_status(
        tampered, expected=_expected(attestation), now=_NOW
    )
    assert verdict["status"] == "PG_TOPOLOGY_UNPROVEN"
    assert any("cluster_identity_digest does not re-derive" in r for r in verdict["reasons"])


# ── guard ↔ consumer 側封閉欄位契約 ───────────────────────────────────────────
def test_guard_binds_the_exact_consumer_cluster_identity_column_contract() -> None:
    attestation = _attest(_observation())
    guard = topology.build_pg_topology_runtime_guard(
        attestation,
        cluster_identity_row=_row(),
        plan_topology_digest=attestation["self_digest"],
        binding_nonce=_NONCE,
    )
    assert validator.validate_aiml_artifact(guard) == []
    assert guard["guard_path"] == topology.TOPOLOGY_GUARD_PATH
    assert guard["runtime_endpoint"] == {"host": "127.0.0.1", "port": 5432, "dbname": "trading_ai"}
    assert guard["server_major_version"] == 16
    # guard 的身分列 digest 必須是 consumer 側同一個封閉欄位契約算出來的值。
    assert guard["cluster_identity_row_digest"] == resilience.cluster_identity_row_digest(_row())
    assert tuple(topology.cluster_identity_columns()) == resilience.CLUSTER_IDENTITY_COLUMNS
    assert topology.cluster_identity_relation() == resilience.CLUSTER_IDENTITY_RELATION


@pytest.mark.parametrize("bad_row", [
    _row(system_identifier="7000000000000000002"),
    _row(database_oid=99999),
    _row(server_major_version=15),
    _row(runtime_port=5433),
    _row(runtime_dbname="postgres"),
    _row(binding_nonce="other-nonce"),
])
def test_guard_refuses_a_row_that_would_never_match_at_runtime(bad_row) -> None:
    attestation = _attest(_observation())
    with pytest.raises(topology.PgTopologyContractError):
        topology.build_pg_topology_runtime_guard(
            attestation,
            cluster_identity_row=bad_row,
            plan_topology_digest=attestation["self_digest"],
            binding_nonce=_NONCE,
        )


def test_guard_rejects_a_row_with_the_wrong_column_set() -> None:
    attestation = _attest(_observation())
    row = _row()
    row.pop("binding_nonce")
    with pytest.raises(topology.PgTopologyContractError):
        topology.build_pg_topology_runtime_guard(
            attestation,
            cluster_identity_row=row,
            plan_topology_digest=attestation["self_digest"],
            binding_nonce=_NONCE,
        )


class _FakeCursor:
    """注入式游標(丟棄式;絕不連任何 socket)。"""

    def __init__(self, row, connected):
        self._row, self._connected = row, connected
        self._result = None

    def execute(self, sql, *args):
        self._result = self._connected if "current_user" in sql else self._row

    def fetchall(self):
        return [self._result]

    def fetchone(self):
        return self._result

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConnection:
    def __init__(self, row, connected):
        self._row, self._connected = row, connected
        self.rollbacks = 0

    def cursor(self, *args, **kwargs):
        return _FakeCursor(self._row, self._connected)

    def rollback(self):
        self.rollbacks += 1


def test_rendered_guard_file_is_accepted_by_the_consumer_reconnect_identity_gate(tmp_path) -> None:
    """§8.3 round-trip:W3 渲染的 guard 檔被 consumer 側重連身分閘直接吃下並回 MATCH。"""
    attestation = _attest(_observation())
    guard = topology.build_pg_topology_runtime_guard(
        attestation,
        cluster_identity_row=_row(),
        plan_topology_digest=attestation["self_digest"],
        binding_nonce=_NONCE,
    )
    guard_file = tmp_path / "topology-runtime-guard.json"
    _install_guard_with_required_posture(guard, guard_file)
    connection = _FakeConnection(
        row=dict(_row()),
        connected={
            "connected_user": "aiml_engine_scanner",
            "connected_database": "trading_ai",
            "server_version_num": "160003",
            # W2 P1-4:身分閘同時比對 lc_messages(非英文伺服器會讓連線期錯誤
            # 訊息指紋失效),故 fake connection 必須供出契約要求的值。
            "lc_messages": resilience.REQUIRED_LC_MESSAGES,
        },
    )
    result = resilience.verify_connected_cluster_identity(
        connection,
        topology_guard_file=guard_file,
        dsn_identity={
            "host": "127.0.0.1", "port": "5432", "dbname": "trading_ai",
            "user": "aiml_engine_scanner",
        },
    )
    assert result["status"] == "MATCH"
    assert result["topology_guard_digest"] == guard["self_digest"]
    assert result["cluster_identity_row_digest"] == guard["cluster_identity_row_digest"]
    # 一列被換掉的身分列 → typed permanent 失敗(production 為 exit 78)。
    drifted = _FakeConnection(
        row=_row(database_oid=99999),
        connected={
            "connected_user": "aiml_engine_scanner",
            "connected_database": "trading_ai",
            "server_version_num": "160003",
            # W2 P1-4:身分閘同時比對 lc_messages(非英文伺服器會讓連線期錯誤
            # 訊息指紋失效),故 fake connection 必須供出契約要求的值。
            "lc_messages": resilience.REQUIRED_LC_MESSAGES,
        },
    )
    with pytest.raises(resilience.AlrRuntimeIdentityError):
        resilience.verify_connected_cluster_identity(
            drifted, topology_guard_file=guard_file
        )


def test_observer_touches_no_socket_and_declares_no_production_authority() -> None:
    """本葉只吃注入觀測:import 面沒有任何 DB/網路/子行程入口(AST 靜態證明)。"""
    tree = ast.parse((HELPERS / "agent_governance_s2_4_topology.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {
        "psycopg2", "socket", "subprocess", "http", "urllib", "requests", "asyncio", "os"
    }, sorted(imported)
    # 也沒有任何 `*.connect(...)` 呼叫。
    assert not [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect"
    ]
    assert topology.RUNTIME_ENDPOINT == {"host": "127.0.0.1", "port": 5432, "dbname": "trading_ai"}
    assert topology.TOPOLOGY_STATUS_UNPROVEN == "PG_TOPOLOGY_UNPROVEN"
