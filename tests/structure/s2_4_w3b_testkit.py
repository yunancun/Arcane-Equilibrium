"""S2.4(WP4·W3b)focused 測試共用的丟棄式簽章/ledger/probe-證據工具。

刻意**不是** ``conftest.py``:三支 W3b 測試檔各自 import 這些純函式,呼叫點顯式可讀。
所有時間錨定在凍結常量上(無 wall clock,故無日期腐化;見 memory 的 fixture 時鐘鐵則)。

honesty:此處的一切鑰匙/授權/ledger/probe 證據都是**丟棄式**——真信任根私鑰不在 repo、
也不在任何主機上;這些 fixture 只證「契約層再導出行為」,絕不認證任何 runtime。
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for _candidate in (HELPERS, ML_ROOT, PROGRAM_CODE):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_schema_core as schema_core  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import agent_governance_s2_4_probe as probe  # noqa: E402
import agent_governance_s2_4_render as render  # noqa: E402
import agent_governance_s2_4_topology as topology  # noqa: E402

ANCHOR = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
ISSUED = ANCHOR.isoformat()
NOW = (ANCHOR + timedelta(minutes=2)).isoformat()
EXPIRES = (ANCHOR + timedelta(minutes=10)).isoformat()
HOST = "trade-core"
SOURCE_HEAD = "0" * 40
MIRROR = ["203.0.113.0/24"]
CGROUP_ROOT = "/sys/fs/cgroup/system.slice"
CAPTURE_DIGEST = "sha256:" + "7" * 64
UNIT_FIELDS = {
    "source_head": SOURCE_HEAD,
    "learning_runtime_digest": "sha256:" + "0" * 64,
    "learning_runtime_digest_v2": "sha256:" + "1" * 64,
    "application_bundle_digest": "sha256:" + "2" * 64,
    "launch_bundle_digest": "sha256:" + "3" * 64,
}
POLICY_BUDGETS = {
    "row_budget": 500,
    "byte_budget": 4_194_304,
    "collection_window_days": 7,
    "max_new_entries_per_window": 64,
}
_SIGN_SEQ = [0]


def frozen_clock(offset_minutes: float = 3.0):
    return lambda: ANCHOR + timedelta(minutes=offset_minutes)


def rendered_unit() -> str:
    return render.render_engine_scanner_unit(dict(UNIT_FIELDS))


# ── 丟棄式 SSHSIG 信任根 ─────────────────────────────────────────────────────────
def mint_key(tmp_path: Path, name: str = "w3b-operator"):
    private_key = tmp_path / name
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)], check=True
    )
    parts = private_key.with_suffix(".pub").read_text(encoding="ascii").split()
    public_key = " ".join(parts[:2])
    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
        check=True, capture_output=True, text=True,
    ).stdout.split()[1]
    return private_key, public_key, fingerprint


def install_pinned_key(monkeypatch, public_key: str, fingerprint: str) -> None:
    facade = schema_core.resolve_facade()
    monkeypatch.setattr(facade, "S2_4_OPERATOR_TRUST_ROOT_PUBLIC_KEY", public_key)
    monkeypatch.setattr(facade, "S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT", fingerprint)


def sign(private_key: Path, artifact: dict, *, namespace: str) -> dict:
    signed = validator._s2_4_operator_authorization_signed_bytes(artifact)
    _SIGN_SEQ[0] += 1
    message = private_key.parent / f"w3b-auth-{_SIGN_SEQ[0]}.bin"
    message.write_bytes(signed)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n", namespace, str(message)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    artifact["sshsig_armored"] = message.with_name(message.name + ".sig").read_text(encoding="ascii")
    artifact["self_digest"] = validator.artifact_self_digest(artifact)
    return artifact


def authorization(
    private_key: Path,
    *,
    profile_key: str,
    authorization_id: str,
    expires_at: str = EXPIRES,
) -> dict:
    profile = validator.S2_4_AUTHORIZATION_PROFILES[profile_key]
    artifact = {
        "schema_version": "s2_4_operator_authorization_v1",
        "profile_identity": profile["profile_identity"],
        "signature_namespace": profile["signature_namespace"],
        "authorization_id": authorization_id,
        "payload_fields": list(profile["payload_fields"]),
        "issued_at": ISSUED,
        "expires_at": expires_at,
        "sshsig_armored": "-----BEGIN SSH SIGNATURE-----\nAAAA\n-----END SSH SIGNATURE-----\n",
        "self_digest": "sha256:" + "0" * 64,
    }
    return sign(private_key, artifact, namespace=profile["signature_namespace"])


def replay_ledger(consumed=()) -> dict:
    entries = []
    previous = None
    seed = {
        "authorization_id": "sha256:" + "9" * 64,
        "authorization_digest": "sha256:" + "8" * 64,
        "profile_identity": "aiml-s2-capability-probe-operator-v1",
    }
    for index, item in enumerate([seed, *consumed]):
        entry = {
            "seq": index,
            "prev_entry_digest": previous,
            "authorization_id": item["authorization_id"],
            "authorization_digest": item["authorization_digest"],
            "profile_identity": item["profile_identity"],
            "consumed_at": ISSUED,
            "fsynced": True,
        }
        entry["entry_digest"] = validator.canonical_digest(entry)
        previous = entry["entry_digest"]
        entries.append(entry)
    ledger = {
        "schema_version": "s2_4_authorization_replay_ledger_v1",
        "ledger_path": "/var/lib/arcane-equilibrium/aiml/install/s2_4/replay-ledger.json",
        "entries": entries,
        "append_only": True,
    }
    ledger["self_digest"] = validator.artifact_self_digest(ledger)
    return ledger


# ── 終端 PREPARE_SANDBOX probe 證據(以 W3a 葉 + 注入 driver 真跑一次)──────────
class _ProbeDriver:
    # in-memory fixture 絕不冒充平台背書(W3 review E2 P1-1 / E3 P2-6)。
    evidence_class = "STRUCTURAL_ONLY"

    def __init__(self, property_digest: str) -> None:
        self.property_digest = property_digest
        self.invocation_id = "a" * 32

    def journal_transition(self, *, entry):
        return None

    def start_transient_unit(self, *, unit_name, scope, properties):
        self.unit_name = unit_name
        return self.invocation_id

    def read_unit_properties(self, *, unit_name):
        return {
            "invocation_id": self.invocation_id,
            "cgroup": f"{CGROUP_ROOT}/{unit_name}",
            "property_digest": self.property_digest,
        }

    def observe_egress(self, *, unit_name, scope):
        return {
            "host_systemd_cgroup_versions": {"kernel": "6.1.0", "systemd": "252", "cgroup": "v2"},
            "egress_observations": {"allow": "203.0.113.0/24", "deny": "any"},
            "network_isolation_verified": True,
        }

    def stop_transient_unit(self, *, unit_name, max_drain_seconds):
        return None

    def reset_failed(self, *, unit_name):
        return None

    def remove_transient_unit(self, *, unit_name):
        return None

    def sweep_residue(self, *, unit_name):
        return {
            "unit_absent": True, "cgroup_absent": True,
            "process_absent": True, "task_files_absent": True,
        }

    def independent_cleanup_postcheck(self, *, unit_name, probe_id, probe_core_digest):
        return {
            "verifier_node": "s2-4-probe-verifier",
            "verifier_capture_digest": CAPTURE_DIGEST,
            "stopped_confirmed": True, "reset_failed_confirmed": True,
            "removed_confirmed": True, "no_surviving_unit": True,
            "no_surviving_cgroup": True, "no_surviving_process": True,
        }

    def trusted_host_time(self):
        return NOW


# ── §8.2 topology 觀測 / attestation / guard(注入觀測,零 socket、零 psql)────────
_FILE_IDENTITY = {
    "device": 66306, "inode": 4242, "path": "/var/lib/postgresql/16/main",
    "digest": "sha256:" + "c" * 64,
}
BINDING_NONCE = "w3b-testkit-binding-nonce"
PG_ACL_MANIFEST = json.loads(
    (ROOT / "program_code/ml_training/pg_acl_manifest_v1.json").read_text(encoding="utf-8")
)


def topology_observation() -> dict:
    return {
        "runtime_listener": {
            "socket_inode": 4242, "owning_pid": 1234, "owning_uid": 26,
            "executable_digest": "sha256:" + "a" * 64,
            "cgroup": "/system.slice/postgresql.service", "endpoint": "127.0.0.1:5432",
        },
        "proxy_hops": [],
        "admin_endpoint": {
            "endpoint_class": "attested_local_socket",
            "handle_class": "peer-authenticated-unix-socket",
        },
        "cluster_identity": {
            "system_identifier": "7000000000000000001", "server_version": "16.3",
            "database_oid": 16400, "postmaster_identity": "postmaster:1234",
            "reload_operation_id": "reload-0001",
        },
        "file_identities": {
            "data_dir": dict(_FILE_IDENTITY),
            "config_file": {**_FILE_IDENTITY, "path": "/etc/postgresql/16/main/postgresql.conf"},
            "hba_file": {**_FILE_IDENTITY, "path": "/etc/postgresql/16/main/pg_hba.conf"},
        },
        "effective_hba_rule": {
            "source": "127.0.0.1/32", "database": "trading_ai",
            "user": "aiml_engine_scanner", "method": "scram-sha-256",
        },
        "end_to_end_reaches_cluster": True,
    }


def topology_attestation(observation: dict | None = None) -> dict:
    return topology.observe_pg_topology(
        observation if observation is not None else topology_observation(),
        source_head=SOURCE_HEAD, target_host=HOST, observed_at=ISSUED,
    )


def topology_expected(attestation: dict) -> dict:
    entries = [dict(attestation["effective_hba_rule"])]
    return {
        "listener_config_digest": attestation["listener_config_digest"],
        "proxy_config_digest": attestation["proxy_config_digest"],
        "cluster_identity_digest": attestation["cluster_identity_digest"],
        "hba_projection": {
            "entries": entries, "projection_digest": validator.canonical_digest(entries)
        },
        "source_head": attestation["source_head"],
        "target_host": attestation["target_host"],
    }


def topology_guard(attestation: dict) -> dict:
    row = {
        "system_identifier": "7000000000000000001", "database_oid": 16400,
        "server_major_version": 16, "runtime_host": "127.0.0.1", "runtime_port": 5432,
        "runtime_dbname": "trading_ai", "binding_nonce": BINDING_NONCE,
    }
    return topology.build_pg_topology_runtime_guard(
        attestation,
        cluster_identity_row={name: row[name] for name in topology.cluster_identity_columns()},
        plan_topology_digest=attestation["self_digest"], binding_nonce=BINDING_NONCE,
    )


def terminal_probe_evidence(private_key: Path, *, scope: str = "PREPARE_SANDBOX") -> dict:
    """真跑一次 W3a probe(注入 driver)以取得 scope 相符的 terminal receipt + attestation。"""

    scope_inputs = (
        {"artifact_mirror_allowlist": list(MIRROR)}
        if scope == "PREPARE_SANDBOX"
        else {"rendered_unit": rendered_unit()}
    )
    core = probe.build_capability_probe_core(
        scope=scope, host=HOST, cgroup_manager_scope="system_manager",
        cgroup_root_pattern=CGROUP_ROOT, source_head=SOURCE_HEAD, target_host=HOST,
        created_at=ISSUED, max_cleanup_seconds=30, max_cgroup_drain_seconds=10, **scope_inputs,
    )
    intent = probe.build_capability_probe_intent(core, expires_at=EXPIRES, max_ttl_seconds=600)
    auth = authorization(
        private_key, profile_key="capability_probe",
        authorization_id="sha256:" + ("1" if scope == "PREPARE_SANDBOX" else "2") * 64,
    )
    verdict = probe.run_s2_4_capability_probe(
        intent, auth, _ProbeDriver(core["transient_unit_property_digest"]),
        now=NOW, clock=frozen_clock(), replay_ledger=replay_ledger(), **scope_inputs,
    )
    assert verdict["status"] == "TERMINAL_CLEAN", verdict["reasons"]
    return {
        scope: {
            "attestation": verdict["attestation"],
            "effect_receipt": verdict["effect_receipt"],
        }
    }


# ── W3b APPLY row 的共用測試腳手架(依 §10.1.1 的 2000 行治理自 apply 測試檔下沉)──────
PLAN_DIGEST = "sha256:" + "1" * 64
PRE_STATE = "sha256:" + "2" * 64
AGGREGATE_AUTH_ID = "sha256:" + "4" * 64
PG_AUTH_ID = "sha256:" + "5" * 64
UID = 947
GID = 947


def signed_authorizations(tmp_path, monkeypatch) -> dict:
    """丟棄式 operator 信任根 + aggregate/pg-migration 兩張真簽章 permit。"""

    private_key, public_key, fingerprint = mint_key(tmp_path)
    install_pinned_key(monkeypatch, public_key, fingerprint)
    return {
        "private_key": private_key,
        "apply_aggregate": authorization(
            private_key, profile_key="apply_aggregate", authorization_id=AGGREGATE_AUTH_ID
        ),
        "pg_migration": authorization(
            private_key, profile_key="pg_migration", authorization_id=PG_AUTH_ID
        ),
    }


def component_intent(component_effect_class: str, required_intent_fields: dict) -> dict:
    import agent_governance_s2_4_apply as apply_mod

    return apply_mod.build_component_effect_intent(
        component_effect_class=component_effect_class,
        install_plan_digest=PLAN_DIGEST, pre_state_digest=PRE_STATE,
        required_intent_fields=required_intent_fields, expires_at=EXPIRES,
    )


def common_apply_kwargs(signed, *, pg: bool = False) -> dict:
    auth_set = {"apply_aggregate": signed["apply_aggregate"]}
    if pg:
        auth_set["pg_migration"] = signed["pg_migration"]
    return {
        "authorization_set": auth_set,
        "replay_ledger": replay_ledger(),
        "now": NOW,
        "clock": frozen_clock(),
    }


def owned_evidence(**extra) -> dict:
    """digest 形狀完整的 ownership 綁定(裸物件一律不成立)。"""

    return {
        "s2_4_receipt_digest": "sha256:" + "a" * 64,
        "journal_digest": "sha256:" + "b" * 64,
        **extra,
    }


class PostcheckMixin:
    """所有 fake driver 共用的相異 verifier postcheck(applier 不得自證)。"""

    postcheck_ok = True

    def independent_postcheck(self, *, component_effect_class, install_plan_digest, applier_node):
        self.calls.append("independent_postcheck")
        return {
            "verifier_node": "s2-4-independent-verifier",
            "observed_subject_digest": "sha256:" + "8" * 64,
            "applied_state_verified": self.postcheck_ok,
            "pre_state_lineage_verified": self.postcheck_ok,
            "verifier_capture_digest": CAPTURE_DIGEST,
        }

    def trusted_host_time(self):
        return NOW

    def journal_transition(self, *, entry):
        self.calls.append("journal:" + entry["state"])
