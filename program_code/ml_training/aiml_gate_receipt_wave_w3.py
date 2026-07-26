"""S2.4(WP4·W3)wave-exit 綁定的 code-owned 投影葉模組(§10.3 W3 row)。

鏡 :mod:`aiml_gate_receipt_wave_w2`:facade 逐名 re-export,``derive_wave_exit_status``
的 W3 分支委派本葉。W3a 面(typed host capability probe + PG topology observer)於此折成
「活」再導出,任何 ABI/行為漂移都必然弄破 W3 wave-exit:

- ``_W3_OWNED_PATHS``:probe/topology 兩個 governed 葉、W3 發射葉、wave 投影葉、facade、
  consumer 側 guard 契約葉、七支 probe/topology/attestation schema 與三支 focused 測試;
- ``w3_exported_abi_projection``:§10.2/§10.3 W3 exit 的 exported-ABI 投影,折入六個活面——
  兩 scope 的 transient-unit property digest、route-surface 契約 digest、source-lane
  probe 行為(無 driver 必為 typed 非成功且零變更)、scope 替換必被拒、topology 的
  PROVEN/UNPROVEN 雙向再導出與 guard↔身分列欄位契約的 round-trip;
- W3 的 PASS 另需前導 W2 wave-exit「連同其 W1/W0/admission 鏈」一起再導出 PASS
  (predecessor 物件鏈驗在 facade 的 ``derive_wave_exit_status``)。

receipt 只帶 evidence,PASS 恆由中央 validator 導出;通過「不」認證任何 runtime——
九 authority / production_apply_performed / running_attested 恆 false。
facade 依 2000 行治理拆分規約「只」經 schema_core.resolve_facade() 取得;governed helper
模組(probe/topology/render)於函式內延遲匯入(保 monkeypatch 縫、避免 import 循環)。
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
_HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))
_PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
if str(_PROGRAM_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_PROGRAM_CODE_DIR))

from aiml_gate_receipt_schema_core import canonical_digest  # noqa: E402

_SCHEMA_DIR_REL = "program_code/ml_training/schemas/aiml_gate_receipts"
# §10.1 + §10.1.1(2026-07-26 PM path-scope amendment):W3a 的 owned-path 投影。
_W3_OWNED_PATHS = tuple(sorted((
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_install.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_probe.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_render.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_topology.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_w3_emit.py",
    "program_code/ml_training/aiml_gate_receipt_schema_core.py",
    "program_code/ml_training/aiml_gate_receipt_validator.py",
    "program_code/ml_training/aiml_gate_receipt_wave_w3.py",
    "program_code/ml_training/alr_consumer_resilience.py",
    # W3a 的兩個新 governed 葉進入 consumer runtime import 閉包的宣告面(§8.1 allowlist)。
    "program_code/ml_training/application_bundle_runtime_closure_v1.json",
    f"{_SCHEMA_DIR_REL}/network_sandbox_capability_attestation_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/pg_topology_attestation_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/pg_topology_runtime_guard_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_capability_probe_core_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_capability_probe_effect_receipt_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_capability_probe_intent_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_capability_probe_journal_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_capability_probe_postcheck_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_capability_probe_rollback_v1.schema.json",
    "tests/structure/test_agent_governance_s2_4_probe.py",
    "tests/structure/test_agent_governance_s2_4_topology.py",
    "tests/structure/test_agent_governance_s2_4_install_w3.py",
)))
# §10.2/§10.3 W3 exported-ABI 的 code-owned 骨架(live 部分見 w3_exported_abi_projection)。
_W3_EXPORTED_ABI = {
    "wave": "W3",
    "wave_scope": "typed host capability probe + PG topology observer (W3a)",
    "typed_failures": [
        "AUTHORIZATION_REJECTED",
        "EXTERNAL_VERIFICATION_PENDING",
        "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED",
        "PG_TOPOLOGY_UNPROVEN",
        "RECOVERY_REQUIRED",
    ],
    "driver_injection_contract": (
        "host actions only through the injected CapabilityProbeDriver; driver=None is a typed "
        "EXTERNAL_VERIFICATION_PENDING with zero mutation"
    ),
}
# code-owned 探針輸入(與真 repo/runtime 無關;只為把行為折成 deterministic 投影值)。
_W3_PROBE_MIRROR_ALLOWLIST = ("203.0.113.0/24",)
_W3_PROBE_HOST = "trade-core"
_W3_PROBE_CGROUP_ROOT = "/sys/fs/cgroup/system.slice"
_W3_PROBE_CREATED_AT = "2026-07-26T00:00:00+00:00"
_W3_PROBE_EXPIRES_AT = "2026-07-26T00:10:00+00:00"
_W3_PROBE_NOW = "2026-07-26T00:05:00+00:00"
_W3_TOPOLOGY_OBSERVED_AT = "2026-07-26T00:00:00+00:00"
_W3_TOPOLOGY_NOW = "2026-07-26T00:05:00+00:00"
_W3_TOPOLOGY_BINDING_NONCE = "w3-abi-projection-nonce"
_W3_FILE_IDENTITY = {
    "device": 66306,
    "inode": 4242,
    "path": "/var/lib/postgresql/16/main",
    "digest": "sha256:" + "c" * 64,
}


def _w3_topology_observation() -> dict[str, Any]:
    """W3 ABI 投影用的乾淨 §8.2 觀測(code-owned;非任何真主機的觀測)。"""

    return {
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
            "data_dir": dict(_W3_FILE_IDENTITY),
            "config_file": {**_W3_FILE_IDENTITY, "path": "/etc/postgresql/16/main/postgresql.conf"},
            "hba_file": {**_W3_FILE_IDENTITY, "path": "/etc/postgresql/16/main/pg_hba.conf"},
        },
        "effective_hba_rule": {
            "source": "127.0.0.1/32",
            "database": "trading_ai",
            "user": "aiml_engine_scanner",
            "method": "scram-sha-256",
        },
        "end_to_end_reaches_cluster": True,
    }


def _w3_topology_expected(attestation: dict[str, Any]) -> dict[str, Any]:
    entries = [dict(attestation["effective_hba_rule"])]
    return {
        "listener_config_digest": attestation["listener_config_digest"],
        "proxy_config_digest": attestation["proxy_config_digest"],
        "cluster_identity_digest": attestation["cluster_identity_digest"],
        "hba_projection": {"entries": entries, "projection_digest": canonical_digest(entries)},
        "source_head": attestation["source_head"],
        "target_host": attestation["target_host"],
    }


def _file_sha256(path: Path) -> str | None:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _probe_live_projection() -> dict[str, Any]:
    """probe 面的三個活再導出(source-lane 行為 / route-surface 拒絕 / scope 替換拒絕)。"""

    import agent_governance_s2_4_probe as _probe

    live: dict[str, Any] = {}
    try:
        core = _probe.build_capability_probe_core(
            scope="PREPARE_SANDBOX",
            host=_W3_PROBE_HOST,
            cgroup_manager_scope="system_manager",
            cgroup_root_pattern=_W3_PROBE_CGROUP_ROOT,
            source_head="0" * 40,
            target_host=_W3_PROBE_HOST,
            created_at=_W3_PROBE_CREATED_AT,
            max_cleanup_seconds=30,
            max_cgroup_drain_seconds=10,
            artifact_mirror_allowlist=list(_W3_PROBE_MIRROR_ALLOWLIST),
        )
        intent = _probe.build_capability_probe_intent(
            core, expires_at=_W3_PROBE_EXPIRES_AT, max_ttl_seconds=600
        )
        # source lane:intent/route-surface/scope 綁定全過,但沒有授權、也沒有 driver →
        # 必為 typed 非成功且零變更、零 driver 接觸(順序證明:授權閘在 driver 之前)。
        verdict = _probe.run_s2_4_capability_probe(
            intent,
            None,
            None,
            now=_W3_PROBE_NOW,
            artifact_mirror_allowlist=list(_W3_PROBE_MIRROR_ALLOWLIST),
        )
        live["source_lane_status"] = verdict["status"]
        live["source_lane_mutation_performed"] = verdict["mutation_performed"]
        live["source_lane_driver_engaged"] = verdict["driver_engaged"]
        live["source_lane_blocks_next_phase"] = verdict["blocks_next_phase"]
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        live["source_lane_status"] = None
        live["source_lane_mutation_performed"] = None
        live["source_lane_driver_engaged"] = None
        live["source_lane_blocks_next_phase"] = None
    try:
        forged = _probe.build_capability_probe_intent(
            _probe.build_capability_probe_core(
                scope="PREPARE_SANDBOX",
                host=_W3_PROBE_HOST,
                cgroup_manager_scope="system_manager",
                cgroup_root_pattern=_W3_PROBE_CGROUP_ROOT,
                source_head="0" * 40,
                target_host=_W3_PROBE_HOST,
                created_at=_W3_PROBE_CREATED_AT,
                max_cleanup_seconds=30,
                max_cgroup_drain_seconds=10,
                artifact_mirror_allowlist=list(_W3_PROBE_MIRROR_ALLOWLIST),
            ),
            expires_at=_W3_PROBE_EXPIRES_AT,
            max_ttl_seconds=600,
        )
        forged["forbidden_surfaces"]["pg"] = True
        forged["forbidden_surfaces"]["credential_install"] = True
        live["builder_authority_route_status"] = (
            _probe.derive_probe_route_surface_status(forged)["status"]
        )
    except Exception:  # noqa: BLE001
        live["builder_authority_route_status"] = None
    try:
        # scope 替換(core 導出層):兩 scope 的屬性 digest / probe_id 必不同,且跨 scope 輸入夾帶被拒。
        import agent_governance_s2_4_render as _render

        rendered = _render.render_engine_scanner_unit({
            "source_head": "0" * 40,
            "learning_runtime_digest": "sha256:" + "0" * 64,
            "learning_runtime_digest_v2": "sha256:" + "1" * 64,
            "application_bundle_digest": "sha256:" + "2" * 64,
            "launch_bundle_digest": "sha256:" + "3" * 64,
        })
        prepare_digest = _probe.capability_probe_property_digest(
            "PREPARE_SANDBOX", artifact_mirror_allowlist=list(_W3_PROBE_MIRROR_ALLOWLIST)
        )
        installed_digest = _probe.capability_probe_property_digest(
            "INSTALLED_UNIT", rendered_unit=rendered
        )
        cross_rejected = False
        try:
            _probe.capability_probe_property_digest("PREPARE_SANDBOX", rendered_unit=rendered)
        except _probe.ProbeContractError:
            cross_rejected = True
        live["scope_property_digests_differ"] = prepare_digest != installed_digest
        live["cross_scope_input_rejected"] = cross_rejected
    except Exception:  # noqa: BLE001
        live["scope_property_digests_differ"] = None
        live["cross_scope_input_rejected"] = None
    return live


def _topology_live_projection() -> dict[str, Any]:
    """topology 面的三個活再導出(PROVEN / drift→UNPROVEN / guard↔身分列 round-trip)。"""

    import agent_governance_s2_4_topology as _topology

    live: dict[str, Any] = {}
    try:
        attestation = _topology.observe_pg_topology(
            _w3_topology_observation(),
            source_head="0" * 40,
            target_host=_W3_PROBE_HOST,
            observed_at=_W3_TOPOLOGY_OBSERVED_AT,
        )
        expected = _w3_topology_expected(attestation)
        live["clean_status"] = _topology.derive_pg_topology_status(
            attestation, expected=expected, now=_W3_TOPOLOGY_NOW
        )["status"]
        drifted = _w3_topology_observation()
        drifted["runtime_listener"]["socket_inode"] = 9999
        drifted_attestation = _topology.observe_pg_topology(
            drifted,
            source_head="0" * 40,
            target_host=_W3_PROBE_HOST,
            observed_at=_W3_TOPOLOGY_OBSERVED_AT,
        )
        live["listener_drift_status"] = _topology.derive_pg_topology_status(
            drifted_attestation, expected=expected, now=_W3_TOPOLOGY_NOW
        )["status"]
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        live["clean_status"] = None
        live["listener_drift_status"] = None
        return live
    try:
        columns = _topology.cluster_identity_columns()
        row = {
            "system_identifier": "7000000000000000001",
            "database_oid": 16400,
            "server_major_version": 16,
            "runtime_host": "127.0.0.1",
            "runtime_port": 5432,
            "runtime_dbname": "trading_ai",
            "binding_nonce": _W3_TOPOLOGY_BINDING_NONCE,
        }
        guard = _topology.build_pg_topology_runtime_guard(
            attestation,
            cluster_identity_row={name: row[name] for name in columns},
            plan_topology_digest=attestation["self_digest"],
            binding_nonce=_W3_TOPOLOGY_BINDING_NONCE,
        )
        from ml_training import alr_consumer_resilience as _resilience

        live["guard_row_digest_matches_consumer_contract"] = (
            guard["cluster_identity_row_digest"]
            == _resilience.cluster_identity_row_digest(row)
        )
        live["guard_field_contract_digest"] = canonical_digest(
            _topology.pg_topology_guard_field_contract()
        )
    except Exception:  # noqa: BLE001
        live["guard_row_digest_matches_consumer_contract"] = None
        live["guard_field_contract_digest"] = None
    return live


def w3_exported_abi_projection(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """W3 exported-ABI 投影:code-owned 骨架 + probe/topology 兩葉的 ABI 與六個活再導出。"""

    import agent_governance_s2_4_probe as _probe
    import agent_governance_s2_4_topology as _topology

    try:
        probe_abi = _probe.probe_abi_projection()
    except Exception:  # noqa: BLE001
        probe_abi = None
    try:
        topology_abi = _topology.topology_abi_projection()
    except Exception:  # noqa: BLE001
        topology_abi = None
    return {
        **_W3_EXPORTED_ABI,
        "probe_abi": probe_abi,
        "topology_abi": topology_abi,
        "probe_live": _probe_live_projection(),
        "topology_live": _topology_live_projection(),
    }


def w3_owned_path_diff_digest(repo_root: Path = REPO_ROOT) -> str:
    """W3 owned-path 內容投影 digest(同 W0/W1/W2 機制,綁 W3 面;缺檔記 None)。"""

    projection: dict[str, str | None] = {}
    for rel in sorted(_W3_OWNED_PATHS):
        projection[rel] = _file_sha256(repo_root / rel)
    return canonical_digest(projection)


def w3_structural_errors(receipt: dict[str, Any], repo_root: Path = REPO_ROOT) -> list[str]:
    """wave=W3 的自足結構再導出(facade ``_wave_exit_structural_errors`` 委派)。

    除 digest 恆等外,把 W3 exit 的六個謂詞「顯式」折活:source-lane probe 必為零變更的
    typed 非成功、夾帶 builder/install 權限的 probe 請求必被 route-surface 拒、兩 scope 的
    property digest 必不同且跨 scope 輸入被拒、乾淨 topology 必再導出 PROVEN、listener 漂移
    必再導出 PG_TOPOLOGY_UNPROVEN、guard 的身分列 digest 必與 consumer 側封閉欄位契約一致。
    """

    reasons: list[str] = []
    if receipt.get("predecessor_wave_receipt_digest") is None:
        reasons.append(
            "W3 wave-exit requires a non-null predecessor_wave_receipt_digest "
            "(the W2 wave-exit self_digest)"
        )
    projection = w3_exported_abi_projection(repo_root)
    if receipt.get("exported_abi_digest") != canonical_digest(projection):
        reasons.append(
            "wave-exit exported_abi_digest does not re-derive the W3 exported-ABI projection"
        )
    if projection.get("probe_abi") is None:
        reasons.append("W3 capability-probe ABI projection cannot be re-derived")
    elif projection["probe_abi"].get("prepare_sandbox_property_digest") is None or (
        projection["probe_abi"].get("installed_unit_property_digest") is None
    ):
        reasons.append(
            "W3 scoped transient-unit property digests cannot be re-derived from the current checkout"
        )
    elif projection["probe_abi"].get("w6a_prerequisite_probe_scopes") != ["PREPARE_SANDBOX"]:
        reasons.append(
            "W3 W6A probe prerequisite must be PREPARE_SANDBOX only "
            "(a final-unit attestation is never a W6A prerequisite)"
        )
    if projection.get("topology_abi") is None:
        reasons.append("W3 PG-topology ABI projection cannot be re-derived")
    probe_live = projection["probe_live"]
    if probe_live.get("source_lane_mutation_performed") is not False or (
        probe_live.get("source_lane_driver_engaged") is not False
    ):
        reasons.append(
            "W3 source-lane capability probe must perform zero mutation and engage no driver"
        )
    if probe_live.get("source_lane_status") not in {
        "AUTHORIZATION_REJECTED",
        "EXTERNAL_VERIFICATION_PENDING",
        "PROBE_REQUEST_REJECTED",
    }:
        reasons.append("W3 source-lane capability probe does not re-derive a typed non-success")
    if probe_live.get("source_lane_blocks_next_phase") is not True:
        reasons.append("W3 source-lane capability probe must block the next phase")
    if probe_live.get("builder_authority_route_status") != "PROBE_ROUTE_SURFACE_REJECTED":
        reasons.append(
            "W3 probe route surface does not reject a request carrying builder/install authority"
        )
    if probe_live.get("scope_property_digests_differ") is not True or (
        probe_live.get("cross_scope_input_rejected") is not True
    ):
        reasons.append(
            "W3 probe scope substitution is not rejected at the core derivation layer"
        )
    topology_live = projection["topology_live"]
    if topology_live.get("clean_status") != "PG_TOPOLOGY_PROVEN":
        reasons.append("W3 PG-topology observer does not re-derive PROVEN on the clean fixture")
    if topology_live.get("listener_drift_status") != "PG_TOPOLOGY_UNPROVEN":
        reasons.append("W3 listener drift does not re-derive PG_TOPOLOGY_UNPROVEN")
    if topology_live.get("guard_row_digest_matches_consumer_contract") is not True:
        reasons.append(
            "W3 topology runtime guard row digest does not match the consumer-side "
            "CLUSTER_IDENTITY_COLUMNS contract"
        )
    if receipt.get("owned_path_manifest_digest") != canonical_digest(sorted(_W3_OWNED_PATHS)):
        reasons.append("wave-exit owned_path_manifest_digest is not the exact W3 owned-path set")
    if receipt.get("owned_path_diff_digest") != w3_owned_path_diff_digest(repo_root):
        reasons.append(
            "wave-exit owned_path_diff_digest does not re-derive the W3 owned-path content projection"
        )
    return reasons


def w3_chain_binding_errors(
    receipt: dict[str, Any],
    source_admission_receipt: dict[str, Any],
    predecessor_wave_receipt: dict[str, Any],
    head: str | None,
) -> list[str]:
    """W3 predecessor/admission/HEAD 綁定檢查(facade 於 W2 鏈已導 PASS 後呼叫)。"""

    reasons: list[str] = []
    if predecessor_wave_receipt.get("wave") != "W2":
        reasons.append("W3 wave-exit predecessor must be the W2 wave-exit receipt")
    if predecessor_wave_receipt.get("self_digest") != receipt.get(
        "predecessor_wave_receipt_digest"
    ):
        reasons.append(
            "W3 predecessor_wave_receipt_digest does not bind the derived W2 wave-exit receipt"
        )
    if source_admission_receipt.get("self_digest") != receipt.get(
        "source_admission_receipt_digest"
    ):
        reasons.append(
            "wave-exit source_admission_receipt_digest does not bind the derived admission receipt"
        )
    if head is None:
        reasons.append(
            "W3 wave-exit source_head cannot be bound: repo HEAD is unreadable (fail-closed)"
        )
    elif receipt.get("source_head") != head:
        reasons.append("W3 wave-exit source_head is not the current checkout HEAD")
    if receipt.get("source_head") != predecessor_wave_receipt.get("source_head"):
        reasons.append("W3 wave-exit source_head differs from the bound W2 wave-exit receipt")
    if receipt.get("source_head") != source_admission_receipt.get("source_head"):
        reasons.append("W3 wave-exit source_head differs from the bound admission receipt")
    return reasons
