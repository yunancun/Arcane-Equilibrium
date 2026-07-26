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
# §10.1 + §10.1.1(2026-07-26 PM path-scope amendment):W3a+W3b 的 owned-path 投影。
_W3_OWNED_PATHS = tuple(sorted((
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_apply.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_component.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_credential.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_host_identity.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_install.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_prepare.py",
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
    # W3b:PREPARE 與五個 APPLY row 的 closed schema 面。
    f"{_SCHEMA_DIR_REL}/s2_4_component_effect_intent_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_component_effect_postcheck_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_component_effect_result_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_component_effect_rollback_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_prepare_core_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_prepare_effect_receipt_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_prepare_intent_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_prepare_journal_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_prepare_postcheck_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_prepare_rollback_v1.schema.json",
    f"{_SCHEMA_DIR_REL}/s2_4_prepared_install_bundle_v1.schema.json",
    "tests/structure/s2_4_w3b_testkit.py",
    "tests/structure/test_agent_governance_s2_4_apply.py",
    "tests/structure/test_agent_governance_s2_4_apply_pg_disposable.py",
    "tests/structure/test_agent_governance_s2_4_host_identity.py",
    "tests/structure/test_agent_governance_s2_4_prepare.py",
    "tests/structure/test_agent_governance_s2_4_probe.py",
    "tests/structure/test_agent_governance_s2_4_topology.py",
    "tests/structure/test_agent_governance_s2_4_install_w3.py",
)))
# §10.2/§10.3 W3 exported-ABI 的 code-owned 骨架(live 部分見 w3_exported_abi_projection)。
_W3_EXPORTED_ABI = {
    "wave": "W3",
    "wave_scope": (
        "typed host capability probe + PG topology observer (W3a) plus the typed PREPARE "
        "driver and the five APPLY component drivers (W3b)"
    ),
    "typed_failures": [
        "AUTHORIZATION_REJECTED",
        "CANDIDATE_POLICY_CONFIGURATION_REQUIRED",
        "EXTERNAL_VERIFICATION_PENDING",
        "HOST_CREDENTIAL_CAPABILITY_UNSATISFIED",
        "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED",
        "PG_TOPOLOGY_UNPROVEN",
        "POSTCHECK_FAILED_ROLLED_BACK",
        "PREEXISTING_UNOWNED_STATE",
        "PREPARED_BUNDLE_INVALID",
        "PRECHECK_FAILED",
        "PRESTATE_MISMATCH",
        "RAW_INGRESS_REJECTED",
        "RECOVERY_REQUIRED",
    ],
    "driver_injection_contract": (
        "host actions only through the injected CapabilityProbeDriver / PrepareDriver / five "
        "component driver protocols; driver=None is a typed EXTERNAL_VERIFICATION_PENDING with "
        "zero mutation"
    ),
    "raw_ingress_contract": (
        "no driver accepts caller-provided shell, SQL, unit text, secrets or arbitrary "
        "destination paths; every target path, grant statement and unit byte is derived from "
        "code-owned contracts and closed manifests"
    ),
    "evidence_class_contract": (
        "evidence_class is a self-declared attribute on the injected driver; nothing in-process "
        "can distinguish a fixture from a real host driver by that field. W3 therefore REFUSES "
        "to record a self-declared attested class and stamps STRUCTURAL_ONLY on every result, "
        "prepare receipt and probe attestation until a trusted-host platform-attestation "
        "verifier exists (see w4_owned_obligations)"
    ),
    "compensation_exactness_contract": (
        "s2_4_component_effect_rollback_v1.status==COMPENSATED_EXACT is emitted only when the "
        "INDEPENDENT postcheck verifier, re-run after compensation, reports the applied state "
        "absent and the pre-state lineage intact (W4a closed the "
        "INDEPENDENT_POST_COMPENSATION_POSTCHECK obligation); an applier-side self-report or an "
        "unobtainable independent re-observation yields COMPENSATED_NOT_REOBSERVED with "
        "exact_pre_state_restored=false"
    ),
    # §10.3:W3 **不**提供、且不得被當成已提供的義務——以 typed 狀態明載於 exported ABI
    # (W3 wave-exit receipt 以 exported_abi_digest 綁定本表)。
    #
    # W4a(2026-07-26)已交付並因此自本表移除三項:PERMIT_PLAN_BINDING(authorization_id 現由
    # profile 具名的 exact payload 導出,且每個消費閘再導出比對)、REPLAY_LEDGER_APPEND
    # (install lock 下的 atomic/hash-chained/fsynced/consume-once append 與 idempotent replay)、
    # INDEPENDENT_POST_COMPENSATION_POSTCHECK(補償後重跑獨立 verifier,exactness 只由它導出)。
    # 三者的當前契約見 aiml_gate_receipt_wave_w4._W4_EXPORTED_ABI;W4a 自身未交付的義務亦以
    # 同一誠實形狀記在該表的 remaining_owned_obligations。
    "w4_owned_obligations": [
        {
            "obligation_id": "ENCRYPTED_BLOB_DIGEST_ORDERING",
            "typed_status": "OPEN_DESIGN_QUESTION",
            "owner_wave": "W4/W6",
            "spec_refs": ["§5.1", "§7"],
            "statement": (
                "CREDENTIAL_INSTALL's signed intent must carry encrypted_blob_digest, but that "
                "digest is the hash of non-deterministic `systemd-creds encrypt` output. Either "
                "the intent cannot be signed before the encryption runs, or the plaintext handle "
                "must survive the signing window. W3 enforces the binding it was given "
                "(encrypt -> compare against the signed field) and does not resolve the ordering."
            ),
            "w3_provides": (
                "the fail-closed comparison only; the §5.1 ordering question is unresolved"
            ),
        },
    ],
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


# ── W3b(PREPARE + 五 APPLY row)的 code-owned 探針輸入 ─────────────────────────
_W3_PREPARE_DEVICE = 66306
_W3_PREPARE_INODE = 909_090
_W3_PLAN_DIGEST = "sha256:" + "1" * 64
_W3_PRE_STATE_DIGEST = "sha256:" + "2" * 64
# §9.1 PG-migration profile identity 的本地探針常量(避免對 validator 的 import 期依賴)。
PG_MIGRATION_PROFILE_PROBE = "aiml-s2-pg-migration-operator-v1"


def _prepare_live_projection() -> dict[str, Any]:
    """PREPARE 面的活再導出(source-lane 零變更 / APPLY 權限夾帶被拒 / staging 根不可自選)。"""

    import agent_governance_s2_4_prepare as _prepare

    live: dict[str, Any] = {}
    try:
        core = _prepare.build_prepare_core(
            staging_parent_device=_W3_PREPARE_DEVICE, staging_parent_inode=_W3_PREPARE_INODE,
            max_bytes=2_000_000_000, max_seconds=1800, max_fetch_bytes=800_000_000,
            max_fetch_seconds=600, max_artifacts=64, max_build_bytes=1_500_000_000,
            max_build_seconds=900, source_head="0" * 40, target_host=_W3_PROBE_HOST,
            created_at=_W3_PROBE_CREATED_AT,
        )
        intent = _prepare.build_prepare_intent(
            core,
            source_compatibility_receipt_digest="sha256:" + "1" * 64,
            sealed_build_receipt_digest="sha256:" + "2" * 64,
            identity_contract_digest="sha256:" + "3" * 64,
            application_manifest_digest="sha256:" + "4" * 64,
            prepare_sandbox_probe_receipt_digest="sha256:" + "5" * 64,
            expires_at=_W3_PROBE_EXPIRES_AT, max_ttl_seconds=600,
        )
        # source lane:無 probe 證據、無授權、無 driver → typed 非成功、零變更、零 driver 接觸。
        verdict = _prepare.prepare_s2_4_install_bundle(intent, None, None, now=_W3_PROBE_NOW)
        live["source_lane_status"] = verdict["status"]
        live["source_lane_mutation_performed"] = verdict["mutation_performed"]
        live["source_lane_driver_engaged"] = verdict["driver_engaged"]
        live["source_lane_blocks_apply"] = verdict["blocks_apply"]
        forged = _prepare.build_prepare_intent(
            core,
            source_compatibility_receipt_digest="sha256:" + "1" * 64,
            sealed_build_receipt_digest="sha256:" + "2" * 64,
            identity_contract_digest="sha256:" + "3" * 64,
            application_manifest_digest="sha256:" + "4" * 64,
            prepare_sandbox_probe_receipt_digest="sha256:" + "5" * 64,
            expires_at=_W3_PROBE_EXPIRES_AT, max_ttl_seconds=600,
        )
        forged["forbidden_surfaces"]["opt_publish"] = True
        forged["forbidden_surfaces"]["credential_install"] = True
        live["apply_authority_route_status"] = (
            _prepare.derive_prepare_route_surface_status(forged)["status"]
        )
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        live["source_lane_status"] = None
        live["source_lane_mutation_performed"] = None
        live["source_lane_driver_engaged"] = None
        live["source_lane_blocks_apply"] = None
        live["apply_authority_route_status"] = None
    try:
        rejected = False
        try:
            _prepare.build_prepare_core(
                staging_parent_path="/tmp/worker-chosen", staging_parent_device=1,
                staging_parent_inode=2, max_bytes=1, max_seconds=1, max_fetch_bytes=1,
                max_fetch_seconds=1, max_artifacts=1, max_build_bytes=1, max_build_seconds=1,
                source_head="0" * 40, target_host=_W3_PROBE_HOST, created_at=_W3_PROBE_CREATED_AT,
            )
        except _prepare.PrepareContractError:
            rejected = True
        live["worker_chosen_staging_root_rejected"] = rejected
        live["publication_deny_reason_count"] = len(
            _prepare.prepare_publication_boundary_reasons(
                ["/opt/arcane-equilibrium/aiml/runtimes/x",
                 "/etc/credstore.encrypted/aiml-engine-scanner-pg-dsn"]
            )
        )
    except Exception:  # noqa: BLE001
        live["worker_chosen_staging_root_rejected"] = None
        live["publication_deny_reason_count"] = None
    return live


def _apply_live_projection() -> dict[str, Any]:
    """五 APPLY row 的活再導出(source-lane 零變更 / #31 / 路徑導出 / 生命週期面拒絕)。"""

    import agent_governance_s2_4_apply as _apply
    import agent_governance_s2_4_credential as _credential

    live: dict[str, Any] = {}
    statuses: dict[str, Any] = {}
    mutations: dict[str, Any] = {}
    engagements: dict[str, Any] = {}
    try:
        manifest = _apply.build_uid_gid_directory_manifest(uid=947, gid=947)
        intents = {
            "HOST_IDENTITY_INSTALL": {
                "uid_gid_directory_manifest_digest": canonical_digest(manifest)
            },
            "PG_ROLE_ACL_MIGRATION": {
                "topology_attestation_digest": "sha256:" + "a" * 64,
                "acl_manifest_digest": "sha256:" + "b" * 64,
                "pg_migration_permit_digest": "sha256:" + "c" * 64,
                "admin_handle_descriptor_digest": "sha256:" + "d" * 64,
            },
            "CREDENTIAL_INSTALL": {
                "credential_name": _credential.CREDENTIAL_UNIT_NAME,
                "encrypted_blob_digest": "sha256:" + "e" * 64,
                "host_identity_digest": "sha256:" + "f" * 64,
            },
            "LEARNING_RUNTIME": {
                "prepare_effect_receipt_digest": "sha256:" + "0" * 64,
                "base_app_launch_target_manifest_digest": "sha256:" + "1" * 64,
            },
            "ENGINE_SCANNER": {
                "unit_policy_evidence_manifest_digest": "sha256:" + "2" * 64,
                "inactive_post_state_digest": canonical_digest(_apply.INACTIVE_UNIT_POSTSTATE),
            },
        }
        entrypoints = {
            "HOST_IDENTITY_INSTALL": _apply.apply_s2_4_host_identity,
            "PG_ROLE_ACL_MIGRATION": _apply.apply_s2_4_pg_role_acl,
            "CREDENTIAL_INSTALL": _apply.apply_s2_4_credential_install,
            "LEARNING_RUNTIME": _apply.apply_s2_4_learning_runtime,
            "ENGINE_SCANNER": _apply.apply_s2_4_engine_scanner_unit,
        }
        for name, fields in intents.items():
            intent = _apply.build_component_effect_intent(
                component_effect_class=name, install_plan_digest=_W3_PLAN_DIGEST,
                pre_state_digest=_W3_PRE_STATE_DIGEST, required_intent_fields=fields,
                expires_at=_W3_PROBE_EXPIRES_AT,
            )
            verdict = entrypoints[name](intent, None, None, now=_W3_PROBE_NOW)
            statuses[name] = verdict["status"]
            mutations[name] = verdict["mutation_performed"]
            engagements[name] = verdict["driver_engaged"]
        live["source_lane_statuses"] = statuses
        live["source_lane_mutations"] = mutations
        live["source_lane_driver_engagements"] = engagements
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        live["source_lane_statuses"] = None
        live["source_lane_mutations"] = None
        live["source_lane_driver_engagements"] = None
    try:
        # §10.5 #31:host/credential/runtime/unit row 只有 PG permit 時必被拒。
        rejections = {}
        for name in ("HOST_IDENTITY_INSTALL", "CREDENTIAL_INSTALL", "LEARNING_RUNTIME",
                     "ENGINE_SCANNER"):
            rejections[name] = bool(
                _apply._authorization_set_reasons(
                    {"pg_migration": {"profile_identity": PG_MIGRATION_PROFILE_PROBE}},
                    None, component_effect_class=name, now=_W3_PROBE_NOW,
                )
            )
        live["pg_permit_cannot_authorize_non_pg_rows"] = all(rejections.values())
        live["host_identity_classification_rejected"] = (
            _apply.derive_host_identity_effect_class_status(
                subject_kind="host_user", declared_class="PG_ROLE_ACL_MIGRATION"
            )["status"] == "HOST_IDENTITY_CLASSIFICATION_REJECTED"
        )
    except Exception:  # noqa: BLE001
        live["pg_permit_cannot_authorize_non_pg_rows"] = None
        live["host_identity_classification_rejected"] = None
    try:
        # §8.1:target 路徑由內容 digest 導出;非 digest 一律 typed 拒。
        derived = _apply.install_target_root(
            identity_field="launch_bundle_digest", digest="sha256:" + "3" * 64
        )
        arbitrary_rejected = False
        try:
            _apply.install_target_root(
                identity_field="launch_bundle_digest", digest="/srv/worker-chosen"
            )
        except _apply.ComponentContractError:
            arbitrary_rejected = True
        live["install_target_is_digest_derived"] = derived == (
            "/opt/arcane-equilibrium/aiml/launches/" + "3" * 64
        )
        live["arbitrary_install_path_rejected"] = arbitrary_rejected
        # §8.3:driver 上出現任何 enable/start/restart/signal 面即 typed 拒。
        stub = type("_LifecycleStub", (), {"start": lambda self: None})()
        live["lifecycle_surface_rejected"] = bool(
            _apply.assert_no_unit_lifecycle_surface(stub)
        )
        live["clean_driver_has_no_lifecycle_surface"] = (
            _apply.assert_no_unit_lifecycle_surface(object()) == []
        )
    except Exception:  # noqa: BLE001
        live["install_target_is_digest_derived"] = None
        live["arbitrary_install_path_rejected"] = None
        live["lifecycle_surface_rejected"] = None
        live["clean_driver_has_no_lifecycle_surface"] = None
    try:
        # §7:封閉 DSN 八鍵;任一禁鍵即拒。sealed handle 不可序列化。
        live["closed_dsn_exact_set_accepted"] = (
            _credential.derive_closed_dsn_key_status(
                list(_credential.CLOSED_DSN_KEYS)
            )["status"] == "CLOSED_DSN_ACCEPTED"
        )
        live["closed_dsn_passfile_rejected"] = (
            _credential.derive_closed_dsn_key_status(
                list(_credential.CLOSED_DSN_KEYS) + ["passfile"]
            )["status"] == "CLOSED_DSN_REJECTED"
        )
        handle = _credential.SealedSecretHandle(
            bytearray(b"probe"), operation_id="w3-abi", purpose="probe"
        )
        not_serializable = False
        try:
            handle.__reduce__()
        except _credential.CredentialContractError:
            not_serializable = True
        live["sealed_handle_not_serializable"] = not_serializable
        live["sealed_handle_repr_redacted"] = "probe" not in repr(handle) or "redacted" in repr(handle)
        handle.zeroize()
    except Exception:  # noqa: BLE001
        live["closed_dsn_exact_set_accepted"] = None
        live["closed_dsn_passfile_rejected"] = None
        live["sealed_handle_not_serializable"] = None
        live["sealed_handle_repr_redacted"] = None
    return live


def w3_exported_abi_projection(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """W3 exported-ABI 投影:code-owned 骨架 + 四葉 ABI 與其活再導出(W3a + W3b)。"""

    import agent_governance_s2_4_apply as _apply
    import agent_governance_s2_4_credential as _credential
    import agent_governance_s2_4_prepare as _prepare
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
    try:
        prepare_abi = _prepare.prepare_abi_projection()
    except Exception:  # noqa: BLE001
        prepare_abi = None
    try:
        apply_abi = _apply.apply_abi_projection()
    except Exception:  # noqa: BLE001
        apply_abi = None
    try:
        credential_abi = _credential.credential_abi_projection()
    except Exception:  # noqa: BLE001
        credential_abi = None
    return {
        **_W3_EXPORTED_ABI,
        "probe_abi": probe_abi,
        "topology_abi": topology_abi,
        "prepare_abi": prepare_abi,
        "apply_abi": apply_abi,
        "credential_abi": credential_abi,
        "probe_live": _probe_live_projection(),
        "topology_live": _topology_live_projection(),
        "prepare_live": _prepare_live_projection(),
        "apply_live": _apply_live_projection(),
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
    reasons.extend(_w3b_structural_reasons(projection))
    if receipt.get("owned_path_manifest_digest") != canonical_digest(sorted(_W3_OWNED_PATHS)):
        reasons.append("wave-exit owned_path_manifest_digest is not the exact W3 owned-path set")
    if receipt.get("owned_path_diff_digest") != w3_owned_path_diff_digest(repo_root):
        reasons.append(
            "wave-exit owned_path_diff_digest does not re-derive the W3 owned-path content projection"
        )
    return reasons


_W3B_APPLY_ROWS = (
    "HOST_IDENTITY_INSTALL",
    "PG_ROLE_ACL_MIGRATION",
    "CREDENTIAL_INSTALL",
    "LEARNING_RUNTIME",
    "ENGINE_SCANNER",
)
# source lane 允許的 typed 非成功集(全都在 driver 接觸之前;絕不含任何成功值)。
_W3B_SOURCE_LANE_TYPED_NON_SUCCESS = {
    "AUTHORIZATION_REJECTED",
    "COMPONENT_REQUEST_REJECTED",
    "EXTERNAL_VERIFICATION_PENDING",
    "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED",
    "PRECHECK_FAILED",
    "PREPARED_BUNDLE_INVALID",
    "PREPARE_REQUEST_REJECTED",
    "RAW_INGRESS_REJECTED",
}


def _w3b_structural_reasons(projection: dict[str, Any]) -> list[str]:
    """W3b(PREPARE + 五 APPLY row)的九個活裁決;任一漂移即弄破 W3 wave-exit。"""

    reasons: list[str] = []
    for name in ("prepare_abi", "apply_abi", "credential_abi"):
        if projection.get(name) is None:
            reasons.append(f"W3 {name} projection cannot be re-derived")
    apply_abi = projection.get("apply_abi") or {}
    if sorted(apply_abi.get("component_entrypoints") or {}) != sorted(_W3B_APPLY_ROWS):
        reasons.append(
            "W3 does not expose exactly the five APPLY component driver entrypoints"
        )
    if (apply_abi.get("component_row_abis") or None) is None:
        reasons.append("W3 five-row §4 ABI binding cannot be re-derived from the frozen v2 matrix")
    prepare_live = projection.get("prepare_live") or {}
    if prepare_live.get("source_lane_mutation_performed") is not False or (
        prepare_live.get("source_lane_driver_engaged") is not False
    ):
        reasons.append("W3 source-lane PREPARE must perform zero mutation and engage no driver")
    if prepare_live.get("source_lane_status") not in _W3B_SOURCE_LANE_TYPED_NON_SUCCESS:
        reasons.append("W3 source-lane PREPARE does not re-derive a typed non-success")
    if prepare_live.get("source_lane_blocks_apply") is not True:
        reasons.append("W3 source-lane PREPARE must block APPLY")
    if prepare_live.get("apply_authority_route_status") != "PREPARE_ROUTE_SURFACE_REJECTED":
        reasons.append(
            "W3 PREPARE route surface does not reject a request carrying APPLY authority"
        )
    if prepare_live.get("worker_chosen_staging_root_rejected") is not True:
        reasons.append("W3 PREPARE accepts a worker-chosen staging root")
    if prepare_live.get("publication_deny_reason_count") != 2:
        reasons.append(
            "W3 PREPARE does not fail closed on publication into /opt or the encrypted credstore"
        )
    apply_live = projection.get("apply_live") or {}
    statuses = apply_live.get("source_lane_statuses")
    mutations = apply_live.get("source_lane_mutations")
    engagements = apply_live.get("source_lane_driver_engagements")
    if not isinstance(statuses, dict) or sorted(statuses) != sorted(_W3B_APPLY_ROWS):
        reasons.append("W3 source-lane APPLY projection does not cover all five rows")
    elif any(value not in _W3B_SOURCE_LANE_TYPED_NON_SUCCESS for value in statuses.values()):
        reasons.append("W3 source-lane APPLY rows do not all re-derive a typed non-success")
    if not isinstance(mutations, dict) or any(value is not False for value in mutations.values()):
        reasons.append("W3 source-lane APPLY rows must perform zero mutation")
    if not isinstance(engagements, dict) or any(
        value is not False for value in engagements.values()
    ):
        reasons.append("W3 source-lane APPLY rows must engage no driver")
    if apply_live.get("pg_permit_cannot_authorize_non_pg_rows") is not True:
        reasons.append(
            "W3 does not reject a PG permit offered as authority for a host/credential/runtime/"
            "unit row (§10.5 #31)"
        )
    if apply_live.get("host_identity_classification_rejected") is not True:
        reasons.append(
            "W3 does not classify host identity effects exclusively as HOST_IDENTITY_INSTALL"
        )
    if apply_live.get("install_target_is_digest_derived") is not True or (
        apply_live.get("arbitrary_install_path_rejected") is not True
    ):
        reasons.append(
            "W3 install target paths are not derived from content identities, or an arbitrary "
            "caller path is not rejected"
        )
    if apply_live.get("lifecycle_surface_rejected") is not True or (
        apply_live.get("clean_driver_has_no_lifecycle_surface") is not True
    ):
        reasons.append(
            "W3 does not reject an engine-scanner driver exposing enable/start/restart/signal"
        )
    if apply_live.get("closed_dsn_exact_set_accepted") is not True or (
        apply_live.get("closed_dsn_passfile_rejected") is not True
    ):
        reasons.append("W3 closed DSN key set is not load-bearing")
    if apply_live.get("sealed_handle_not_serializable") is not True or (
        apply_live.get("sealed_handle_repr_redacted") is not True
    ):
        reasons.append("W3 sealed secret handle is serializable or leaks through its repr")
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
