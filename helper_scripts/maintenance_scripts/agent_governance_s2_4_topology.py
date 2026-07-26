#!/usr/bin/env python3
"""S2.4(WP4·W3a)PG topology 唯讀觀測葉(§8.2 / §10.5 #25)。

由 install 模組 2000 行帽拆出的 W3a 第二面;install 上層逐名 re-export。本葉做三件事:

1. :func:`observe_pg_topology` —— 從**注入的**唯讀觀測(或丟棄式叢集的觀測)產出
   ``pg_topology_attestation_v1``。它只帶證據:``topology_status`` 是觀測類別、
   ``derived_verdict`` 恆 ``null``——「是否 PROVEN」永遠由獨立驗證者再導出,絕不自證。
2. :func:`derive_pg_topology_status` —— 獨立驗證者的再導出。listener 漂移、proxy-config
   漂移、cluster 不符、落在**簽章 HBA 投影之外**的條目、未經 attest 的 admin endpoint、
   或非 §8.2 封閉 DSN 的 runtime endpoint,一律 typed ``PG_TOPOLOGY_UNPROVEN``。
3. :func:`build_pg_topology_runtime_guard` —— 由已證的 topology 與 admin-owned 身分列
   渲染 root-owned ``pg_topology_runtime_guard_v1``。其
   ``cluster_identity_row_digest`` 由 **consumer 側同一個** 封閉欄位契約
   (``ml_training.alr_consumer_resilience.CLUSTER_IDENTITY_COLUMNS``)折出,故 guard 與
   §8.3 重連身分閘必然對齊——欄位序/名稱漂移在 W3 wave-exit 就會炸。

硬邊界:**零 socket、零 psql、零 production 連線**。source lane 只吃注入觀測或丟棄式叢集;
九 authority / production_apply_performed / running_attested 恆 false。
"""
from __future__ import annotations

import sys
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402

canonical_digest = central_validator.canonical_digest
artifact_self_digest = central_validator.artifact_self_digest

# ── §8.2 封閉 runtime transport(worker 不得選 transport)───────────────────────
RUNTIME_ENDPOINT = {"host": "127.0.0.1", "port": 5432, "dbname": "trading_ai"}
RUNTIME_ENDPOINT_TEXT = "127.0.0.1:5432"
RUNTIME_ROLE = "aiml_engine_scanner"
RUNTIME_AUTH_METHOD = "scram-sha-256"
RUNTIME_HBA_SOURCE = "127.0.0.1/32"
# §8.2:administration channel 可以是被 attest 的本機 socket 或 5433,**永不**是 runtime 5432。
ADMIN_ENDPOINT_CLASSES = ("attested_local_socket", "port_5433")
TOPOLOGY_STATUS_UNPROVEN = "PG_TOPOLOGY_UNPROVEN"
TOPOLOGY_STATUS_EVIDENCE_CAPTURED = "PG_TOPOLOGY_EVIDENCE_CAPTURED"
TOPOLOGY_STATUS_PROVEN = "PG_TOPOLOGY_PROVEN"
TOPOLOGY_EVIDENCE_TTL_SECONDS = 900
# §8.2:root-owned guard 檔的固定位置(mode 0440;渲染由 ENGINE_SCANNER host actor 做)。
TOPOLOGY_GUARD_PATH = "/etc/arcane-equilibrium/aiml/engine-scanner/topology-runtime-guard.json"

_OBSERVATION_SECTIONS = (
    "runtime_listener",
    "proxy_hops",
    "admin_endpoint",
    "cluster_identity",
    "file_identities",
    "effective_hba_rule",
    "end_to_end_reaches_cluster",
)


class PgTopologyContractError(ValueError):
    """topology 契約層硬錯誤(帶 typed ``code``)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def cluster_identity_columns() -> tuple[str, ...]:
    """consumer 側封閉欄位契約(SSOT = ml_training.alr_consumer_resilience)。"""

    from ml_training import alr_consumer_resilience as _resilience

    return tuple(_resilience.CLUSTER_IDENTITY_COLUMNS)


def cluster_identity_relation() -> str:
    from ml_training import alr_consumer_resilience as _resilience

    return str(_resilience.CLUSTER_IDENTITY_RELATION)


def _cluster_identity_row_digest(projection: dict[str, Any]) -> str:
    from ml_training import alr_consumer_resilience as _resilience

    return _resilience.cluster_identity_row_digest(projection)


def server_major_version(server_version: Any) -> int:
    """``"16.3"`` / ``"16"`` / ``"16.3 (Debian ...)"`` → 16;無法解析即 typed 失敗。"""

    text = str(server_version or "").strip()
    head = text.split()[0] if text else ""
    major = head.split(".", 1)[0]
    if not major.isdigit():
        raise PgTopologyContractError("pg_server_version_unparsable")
    return int(major)


def listener_config_digest(runtime_listener: dict[str, Any]) -> str:
    """listener 身分投影 digest(socket inode/PID/UID/executable/cgroup/endpoint)。"""

    return canonical_digest({
        key: runtime_listener.get(key)
        for key in ("socket_inode", "owning_pid", "owning_uid", "executable_digest", "cgroup", "endpoint")
    })


def proxy_config_digest(proxy_hops: Any) -> str:
    """每一 proxy/pooler/forwarder hop 的不可變組態 digest + upstream endpoint 折出的鏈身分。"""

    hops = list(proxy_hops or [])
    return canonical_digest([
        {"config_digest": hop.get("config_digest"), "upstream_endpoint": hop.get("upstream_endpoint")}
        for hop in hops
    ])


def cluster_identity_digest(cluster_identity: dict[str, Any]) -> str:
    """system_identifier / server_version / database OID / postmaster / reload id 的叢集身分。"""

    return canonical_digest({
        key: cluster_identity.get(key)
        for key in (
            "system_identifier",
            "server_version",
            "database_oid",
            "postmaster_identity",
            "reload_operation_id",
        )
    })


def _observation_shape_reasons(observation: Any) -> list[str]:
    if not isinstance(observation, dict):
        return ["pg topology observation must be an object"]
    reasons = [
        f"pg topology observation is missing {section}"
        for section in _OBSERVATION_SECTIONS
        if section not in observation
    ]
    listener = observation.get("runtime_listener")
    if isinstance(listener, dict) and listener.get("endpoint") != RUNTIME_ENDPOINT_TEXT:
        reasons.append(
            "runtime listener endpoint is not the §8.2 closed runtime endpoint "
            f"{RUNTIME_ENDPOINT_TEXT}"
        )
    admin = observation.get("admin_endpoint")
    if isinstance(admin, dict):
        if admin.get("endpoint_class") not in ADMIN_ENDPOINT_CLASSES:
            reasons.append("administration endpoint_class is not an attested §8.2 class")
        if not str(admin.get("handle_class") or "").strip():
            reasons.append("administration handle_class is empty (unattested admin endpoint)")
    rule = observation.get("effective_hba_rule")
    if isinstance(rule, dict):
        if rule.get("source") != RUNTIME_HBA_SOURCE:
            reasons.append(f"effective HBA rule source is not {RUNTIME_HBA_SOURCE}")
        if rule.get("database") != RUNTIME_ENDPOINT["dbname"]:
            reasons.append("effective HBA rule database is not the closed runtime database")
        if rule.get("user") != RUNTIME_ROLE:
            reasons.append("effective HBA rule user is not the engine-scanner role")
        if rule.get("method") != RUNTIME_AUTH_METHOD:
            reasons.append("effective HBA rule method is not SCRAM")
    if observation.get("end_to_end_reaches_cluster") is not True:
        reasons.append(
            "the observation does not assert that runtime endpoint 5432 reaches that exact cluster"
        )
    return reasons


def observe_pg_topology(
    observation: Any,
    *,
    source_head: str,
    target_host: str,
    observed_at: str,
    ttl_seconds: int = TOPOLOGY_EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """由注入的唯讀觀測產出 ``pg_topology_attestation_v1``(evidence-only,絕不自證判定)。

    觀測不完整/不符 §8.2 封閉面時,``topology_status`` 記為 ``PG_TOPOLOGY_UNPROVEN``——它是
    觀測類別而非判定;真正的 PROVEN/UNPROVEN 由 :func:`derive_pg_topology_status` 再導出。
    """

    reasons = _observation_shape_reasons(observation)
    if not isinstance(observation, dict):
        raise PgTopologyContractError("pg_topology_observation_not_object")
    at = central_validator._parse_timestamp(observed_at)
    listener = dict(observation.get("runtime_listener") or {})
    hops = [dict(hop) for hop in (observation.get("proxy_hops") or [])]
    cluster = dict(observation.get("cluster_identity") or {})
    attestation = {
        "schema_version": "pg_topology_attestation_v1",
        "target_host": target_host,
        "source_head": source_head,
        "topology_status": (
            TOPOLOGY_STATUS_EVIDENCE_CAPTURED if not reasons else TOPOLOGY_STATUS_UNPROVEN
        ),
        # §8.2/§10.5 #20:判定永遠由獨立驗證者導出,attestation 不得攜帶判定。
        "derived_verdict": None,
        "runtime_listener": listener,
        "proxy_hops": hops,
        "admin_endpoint": dict(observation.get("admin_endpoint") or {}),
        "cluster_identity": cluster,
        "file_identities": dict(observation.get("file_identities") or {}),
        "effective_hba_rule": dict(observation.get("effective_hba_rule") or {}),
        "end_to_end_reaches_cluster": bool(observation.get("end_to_end_reaches_cluster")),
        "listener_config_digest": listener_config_digest(listener),
        "proxy_config_digest": proxy_config_digest(hops),
        "cluster_identity_digest": cluster_identity_digest(cluster),
        "observed_at": central_validator._parse_timestamp(observed_at).astimezone(
            timezone.utc
        ).isoformat(),
        "expires_at": (at + timedelta(seconds=int(ttl_seconds))).astimezone(
            timezone.utc
        ).isoformat(),
    }
    attestation["self_digest"] = artifact_self_digest(attestation)
    return attestation


def _hba_projection_reasons(attestation: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """簽章 HBA 投影比對:effective rule 必須逐欄落在投影之內(投影外條目即 UNPROVEN)。"""

    projection = expected.get("hba_projection")
    if not isinstance(projection, dict):
        return ["expected signed HBA projection is missing"]
    entries = projection.get("entries")
    if not isinstance(entries, list) or not entries:
        return ["signed HBA projection has no entries"]
    if projection.get("projection_digest") != canonical_digest(entries):
        return ["signed HBA projection digest does not re-derive its entries"]
    rule = attestation.get("effective_hba_rule")
    if not isinstance(rule, dict):
        return ["attested effective HBA rule is missing"]
    normalized = {key: rule.get(key) for key in ("source", "database", "user", "method")}
    if normalized not in [
        {key: entry.get(key) for key in ("source", "database", "user", "method")}
        for entry in entries
        if isinstance(entry, dict)
    ]:
        return [
            "the effective HBA rule is outside the signed HBA projection "
            "(out-of-projection HBA entry)"
        ]
    return []


def derive_pg_topology_status(
    attestation: Any,
    *,
    expected: Any,
    now: str | None = None,
) -> dict[str, Any]:
    """獨立驗證者再導出 §8.2 topology 判定(caller 不可自證;任何漂移即 UNPROVEN)。

    ``expected`` 綁定基線:``listener_config_digest`` / ``proxy_config_digest`` /
    ``cluster_identity_digest`` / ``hba_projection`` / ``source_head`` / ``target_host``。
    """

    reasons: list[str] = []
    if not isinstance(attestation, dict):
        return {"status": TOPOLOGY_STATUS_UNPROVEN, "reasons": ["pg topology attestation must be an object"]}
    if not isinstance(expected, dict):
        return {"status": TOPOLOGY_STATUS_UNPROVEN, "reasons": ["expected topology baseline must be an object"]}
    schema_errors = central_validator.validate_aiml_artifact(attestation)
    if schema_errors:
        return {"status": TOPOLOGY_STATUS_UNPROVEN, "reasons": schema_errors}
    if attestation.get("self_digest") != artifact_self_digest(attestation):
        reasons.append("pg topology attestation self_digest is invalid")
    if attestation.get("derived_verdict") is not None:
        reasons.append("pg topology attestation must not carry a self-declared verdict")
    if attestation.get("topology_status") != TOPOLOGY_STATUS_EVIDENCE_CAPTURED:
        reasons.append("pg topology observation did not capture a complete §8.2 evidence set")
    reasons.extend(_observation_shape_reasons(attestation))
    # 內容 digest 必須由 attestation 自身的欄位重新導出(避免「digest 對、內容被換」)。
    if attestation.get("listener_config_digest") != listener_config_digest(
        attestation.get("runtime_listener") or {}
    ):
        reasons.append("listener_config_digest does not re-derive the attested listener fields")
    if attestation.get("proxy_config_digest") != proxy_config_digest(attestation.get("proxy_hops")):
        reasons.append("proxy_config_digest does not re-derive the attested proxy hops")
    if attestation.get("cluster_identity_digest") != cluster_identity_digest(
        attestation.get("cluster_identity") or {}
    ):
        reasons.append("cluster_identity_digest does not re-derive the attested cluster identity")
    # 基線比對:listener / proxy / cluster 任一漂移即 UNPROVEN(§10.5 #25)。
    for field, label in (
        ("listener_config_digest", "runtime listener drifted from the attested baseline"),
        ("proxy_config_digest", "proxy configuration drifted from the attested baseline"),
        ("cluster_identity_digest", "PostgreSQL cluster identity does not match the baseline"),
    ):
        if expected.get(field) is not None and attestation.get(field) != expected.get(field):
            reasons.append(label)
    for hop in attestation.get("proxy_hops") or []:
        if not isinstance(hop, dict) or not hop.get("config_digest") or not hop.get("upstream_endpoint"):
            reasons.append("an unproved proxy/pooler hop is in front of 5432")
            break
    admin = attestation.get("admin_endpoint") or {}
    if admin.get("handle_class") == RUNTIME_ENDPOINT_TEXT or admin.get("endpoint_class") not in (
        ADMIN_ENDPOINT_CLASSES
    ):
        reasons.append(
            "the administration endpoint is unattested or collapses onto the runtime 5432 listener"
        )
    reasons.extend(_hba_projection_reasons(attestation, expected))
    for field in ("source_head", "target_host"):
        if expected.get(field) is not None and attestation.get(field) != expected.get(field):
            reasons.append(f"pg topology attestation {field} does not match the expected binding")
    now_text = central_validator._now_text(now)
    if now_text is not None:
        try:
            current = central_validator._parse_timestamp(now_text)
            observed = central_validator._parse_timestamp(attestation["observed_at"])
            expires = central_validator._parse_timestamp(attestation["expires_at"])
            if not observed <= current < expires:
                reasons.append(
                    "pg topology evidence is outside its short expiry window "
                    "(expired runtime/topology evidence cannot be refreshed by reference)"
                )
        except (KeyError, TypeError, ValueError):
            reasons.append("pg topology attestation timestamps are invalid")
    return {
        "status": TOPOLOGY_STATUS_PROVEN if not reasons else TOPOLOGY_STATUS_UNPROVEN,
        "reasons": sorted(set(reasons)),
    }


def pg_topology_guard_field_contract() -> dict[str, Any]:
    """guard 的封閉欄位契約 + consumer 側身分列欄位序(W3 ABI 折入面)。"""

    return {
        "guard_path": TOPOLOGY_GUARD_PATH,
        "guard_fields": [
            "schema_version",
            "guard_path",
            "cluster_identity_row_digest",
            "plan_topology_digest",
            "runtime_endpoint",
            "system_identifier",
            "database_oid",
            "server_major_version",
            "binding_nonce",
            "expected_topology_values_digest",
            "self_digest",
        ],
        "runtime_endpoint": dict(RUNTIME_ENDPOINT),
        "runtime_role": RUNTIME_ROLE,
        "auth_method": RUNTIME_AUTH_METHOD,
        "hba_source": RUNTIME_HBA_SOURCE,
        "cluster_identity_relation": cluster_identity_relation(),
        "cluster_identity_columns": list(cluster_identity_columns()),
    }


def build_pg_topology_runtime_guard(
    attestation: dict[str, Any],
    *,
    cluster_identity_row: dict[str, Any],
    plan_topology_digest: str,
    binding_nonce: str,
    guard_path: str = TOPOLOGY_GUARD_PATH,
) -> dict[str, Any]:
    """由已證 topology 與 admin-owned 身分列渲染 ``pg_topology_runtime_guard_v1``。

    身分列必須逐欄等於 consumer 側封閉欄位契約,且其 system_identifier / database OID /
    major version / endpoint 必須與 attestation 一致——否則 typed 失敗(絕不渲染出一份
    「永遠對不上」的 guard,那會讓每次重連 exit 78)。
    """

    columns = cluster_identity_columns()
    if not isinstance(cluster_identity_row, dict) or sorted(cluster_identity_row) != sorted(columns):
        raise PgTopologyContractError("cluster_identity_row_columns_mismatch")
    cluster = attestation.get("cluster_identity") or {}
    major = server_major_version(cluster.get("server_version"))
    projection = {
        "system_identifier": str(cluster_identity_row["system_identifier"]),
        "database_oid": int(cluster_identity_row["database_oid"]),
        "server_major_version": int(cluster_identity_row["server_major_version"]),
        "runtime_host": str(cluster_identity_row["runtime_host"]),
        "runtime_port": int(cluster_identity_row["runtime_port"]),
        "runtime_dbname": str(cluster_identity_row["runtime_dbname"]),
        "binding_nonce": str(cluster_identity_row["binding_nonce"]),
    }
    if projection["system_identifier"] != str(cluster.get("system_identifier")):
        raise PgTopologyContractError("cluster_identity_row_system_identifier_mismatch")
    if projection["database_oid"] != int(cluster.get("database_oid")):
        raise PgTopologyContractError("cluster_identity_row_database_oid_mismatch")
    if projection["server_major_version"] != major:
        raise PgTopologyContractError("cluster_identity_row_server_version_mismatch")
    if (
        projection["runtime_host"] != RUNTIME_ENDPOINT["host"]
        or projection["runtime_port"] != RUNTIME_ENDPOINT["port"]
        or projection["runtime_dbname"] != RUNTIME_ENDPOINT["dbname"]
    ):
        raise PgTopologyContractError("cluster_identity_row_endpoint_mismatch")
    if projection["binding_nonce"] != str(binding_nonce):
        raise PgTopologyContractError("cluster_identity_row_binding_nonce_mismatch")
    guard = {
        "schema_version": "pg_topology_runtime_guard_v1",
        "guard_path": guard_path,
        "cluster_identity_row_digest": _cluster_identity_row_digest(projection),
        "plan_topology_digest": plan_topology_digest,
        "runtime_endpoint": dict(RUNTIME_ENDPOINT),
        "system_identifier": projection["system_identifier"],
        "database_oid": projection["database_oid"],
        "server_major_version": projection["server_major_version"],
        "binding_nonce": str(binding_nonce),
        "expected_topology_values_digest": canonical_digest({
            "cluster_identity_digest": attestation.get("cluster_identity_digest"),
            "listener_config_digest": attestation.get("listener_config_digest"),
            "proxy_config_digest": attestation.get("proxy_config_digest"),
            "runtime_endpoint": dict(RUNTIME_ENDPOINT),
        }),
    }
    guard["self_digest"] = artifact_self_digest(guard)
    return guard


def topology_abi_projection() -> dict[str, Any]:
    """W3 exported-ABI 的 topology 面(骨架 + guard/身分列契約的活再導出)。"""

    try:
        guard_contract_digest = canonical_digest(pg_topology_guard_field_contract())
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        guard_contract_digest = None
    try:
        identity_columns = list(cluster_identity_columns())
        identity_relation = cluster_identity_relation()
    except Exception:  # noqa: BLE001
        identity_columns, identity_relation = None, None
    return {
        "topology_observer": "agent_governance_s2_4_topology.observe_pg_topology",
        "topology_verdict_predicate": "agent_governance_s2_4_topology.derive_pg_topology_status",
        "topology_guard_builder": "agent_governance_s2_4_topology.build_pg_topology_runtime_guard",
        "runtime_endpoint": dict(RUNTIME_ENDPOINT),
        "runtime_role": RUNTIME_ROLE,
        "auth_method": RUNTIME_AUTH_METHOD,
        "hba_source": RUNTIME_HBA_SOURCE,
        "admin_endpoint_classes": list(ADMIN_ENDPOINT_CLASSES),
        "topology_guard_path": TOPOLOGY_GUARD_PATH,
        "topology_guard_field_contract_digest": guard_contract_digest,
        "cluster_identity_relation_name": identity_relation,
        "cluster_identity_columns": identity_columns,
        "typed_failure": TOPOLOGY_STATUS_UNPROVEN,
        "schema_ids": ["pg_topology_attestation_v1", "pg_topology_runtime_guard_v1"],
    }
