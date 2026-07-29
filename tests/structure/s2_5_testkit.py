"""S2.5(WP5)focused 測試共用的丟棄式簽章/harness/授權工具(鏡 ``s2_4_w3b_testkit``)。

刻意**不是** ``conftest.py``:各測試檔顯式 import 這些純函式。所有時間錨定在凍結常量上
(無 wall clock,故無日期腐化;memory 的 fixture 時鐘鐵則)。

honesty:此處的一切鑰匙/授權/unit 狀態機都是**丟棄式/注入式**——真信任根私鑰不在 repo、
真實主機零接觸;harness 只證「狀態機與守衛邏輯在注入環境下正確」,絕不認證任何 runtime;
fixture 產物的 evidence_class 至多 ``LOCAL_REPRODUCIBLE``,永不假冒 platform-attested PASS。
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for _candidate in (HELPERS, ML_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_alr_quiesce_fence as quiesce  # noqa: E402
import agent_governance_alr_quiesce_inventory as inventory  # noqa: E402
from agent_governance_s2_4_install_evidence import (  # noqa: E402
    S2_4_APPLY_GATED_DEPENDENCY_CLASSES,
)
import agent_governance_s2_4_install_plan as s2_4_install_plan  # noqa: E402
import agent_governance_s2_5_attestation as attestation  # noqa: E402
import agent_governance_s2_5_lifecycle as lifecycle  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

ANCHOR = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
ISSUED = ANCHOR.isoformat()
NOW = (ANCHOR + timedelta(minutes=2)).isoformat()
EXPIRES = (ANCHOR + timedelta(minutes=10)).isoformat()
HOST = "trade-core"
SOURCE_HEAD = "0" * 40
FRAGMENT_DIGEST = "sha256:" + "a" * 64
LAUNCH_DIGEST = "sha256:" + "c" * 64
APPLICATION_DIGEST = "sha256:" + "d" * 64
BASE_TREE_DIGEST = "sha256:" + "e" * 64
LOADER_CLOSURE_DIGEST = "sha256:" + "f" * 64
CMDLINE_DIGEST = "sha256:" + "2" * 64
# owner 訊號(P2-k):OWNER_FINGERPRINT 不再是自由常量——由 WP3 compute_owner_fingerprint
# 對 harness 的標準訊號重算而得(SimulatedUnit 首次 enable 後恆為 pid 4001 / inv-1)。
OWNER_SIGNALS = {
    "main_pid": 4001,
    "process_start_ticks": "1234567",
    "boot_id": "boot-1",
    "control_group": f"/system.slice/{lifecycle.S2_5_UNIT_NAME}",
    "env_hash": "sha256:" + "5" * 64,
    "invocation_id": "inv-1",
    "cmdline_digest": CMDLINE_DIGEST,
    "runtime_digest": "sha256:" + "6" * 64,
    "flock_path": "/opt/aiml/run/engine_scanner/alr.lock",
}
OWNER_FINGERPRINT = inventory.compute_owner_fingerprint(**OWNER_SIGNALS)
_SIGN_SEQ = [0]
_STATE_SEQ = [0]


def frozen_clock(offset_minutes: float = 3.0):
    return lambda: ANCHOR + timedelta(minutes=offset_minutes)


# ── 丟棄式 SSHSIG 信任根(鏡 w3b_testkit.mint_key)────────────────────────────────
_KEY_SEQ = [0]


def mint_key(tmp_path: Path, name: str = "s2-5-operator"):
    _KEY_SEQ[0] += 1
    private_key = tmp_path / f"{name}-{_KEY_SEQ[0]}"
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
    monkeypatch.setattr(attestation, "S2_5_TRUST_ROOT_PUBLIC_KEY", public_key)
    monkeypatch.setattr(attestation, "S2_5_TRUST_ROOT_FINGERPRINT", fingerprint)


def _sign_bytes(private_key: Path, message_bytes: bytes, *, namespace: str) -> str:
    _SIGN_SEQ[0] += 1
    message = private_key.parent / f"s2-5-msg-{_SIGN_SEQ[0]}.bin"
    message.write_bytes(message_bytes)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n", namespace, str(message)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return message.with_name(message.name + ".sig").read_text(encoding="ascii")


def signed_permit(private_key: Path, intent: dict[str, Any], *, namespace: str | None = None) -> dict[str, Any]:
    """對 exact intent 簽出一張 permit(``namespace`` 可覆蓋以測域分離)。"""

    permit = attestation.build_s2_5_operator_permit(intent)
    permit["sshsig_armored"] = _sign_bytes(
        private_key,
        attestation.s2_5_permit_signed_bytes(permit),
        namespace=namespace or permit["signature_namespace"],
    )
    return permit


def signed_attestation(
    private_key: Path,
    *,
    attestation_kind: str,
    intent: dict[str, Any],
    running_dimensions: dict[str, Any],
    observer_gate: dict[str, Any],
    trusted_host_time: str = NOW,
    namespace: str | None = None,
) -> dict[str, Any]:
    artifact = attestation.build_s2_5_trusted_host_attestation(
        attestation_kind=attestation_kind,
        intent_digest=intent["self_digest"],
        running_dimensions=running_dimensions,
        observer_gate=observer_gate,
        trusted_host_time=trusted_host_time,
    )
    artifact["signature_armored"] = _sign_bytes(
        private_key,
        attestation.s2_5_attestation_signed_bytes(artifact),
        namespace=namespace or attestation.S2_5_ATTESTOR_NAMESPACE,
    )
    return artifact


# ── intent / evidence builders ───────────────────────────────────────────────
def start_core(phase: str = "S2_5A_START", **overrides: Any) -> dict[str, Any]:
    core = lifecycle.build_s2_5_start_core(
        phase=phase,
        target_host=HOST,
        expected_unit_fragment_digest=FRAGMENT_DIGEST,
        s2_4_install_effect_receipt_digest=S2_4_RECEIPT_DIGEST,
        expected_launch_bundle_digest=LAUNCH_DIGEST,
        expected_application_bundle_digest=APPLICATION_DIGEST,
        expected_base_runtime_tree_digest=BASE_TREE_DIGEST,
        native_loader_closure_digest=LOADER_CLOSURE_DIGEST,
        s2_1_drill_receipt_digest=DRILL_DIGEST if phase == "S2_5B_FINAL" else None,
        pre_drill_attestation_digest=(
            overrides.pop("pre_drill_attestation_digest", "sha256:" + "4" * 64)
            if phase == "S2_5B_FINAL"
            else None
        ),
        source_head=SOURCE_HEAD,
        issued_at=ISSUED,
        expires_at=EXPIRES,
    )
    core.update(overrides)
    return core


def start_intent(phase: str = "S2_5A_START", **core_overrides: Any) -> dict[str, Any]:
    return lifecycle.build_s2_5_start_intent(
        start_core(phase, **core_overrides), expires_at=EXPIRES
    )


def fixture_digest(label: str) -> str:
    """由導出的 ``canonical_digest`` 對標籤導出一個穩定 digest。

    lineage 細節一律**導出**而非寫死 hex 字面量(避免把上游契約凍進 S2.5 測試面)。
    """

    return validator.canonical_digest({"s2_5_testkit_fixture": label})


S2_4_PLAN_ID = "s2-4-" + fixture_digest("s2-4-install-plan").split(":", 1)[1]


def s2_4_receipt(*, expires_at: str = EXPIRES) -> dict[str, Any]:
    """P1-2:真 canonical 構造——self_digest 由 artifact_self_digest 重封(自報值不再可行)。

    PR#153 Codex-4:S2.5 precheck 已把這份 receipt 送進中央閘(closed schema CP2b +
    ``derive_install_lineage_status``)並另判新鮮度,故 fixture 必須是**全欄位**的真形狀:
    五 APPLY row 依 ``S2_4_APPLY_ROW_CLASS_ORDER`` exact 次序、兩 scoped probe digest 相異、
    逆向補償鏈 digest 由 ``aggregate_rollback_digest`` 導出、三族 dependency-refresh 鍵由
    ``S2_4_DEPENDENCY_REFRESH_CLASSES`` 導出。時間欄一律取凍結錨(禁 wall clock)。

    ⚠ honesty:這是丟棄式 fixture,``evidence_class`` 恆 ``STRUCTURAL_ONLY``——它證明的是
    「S2.5 的上游閘會對一份結構合格的 receipt 放行」,絕不假冒任何真發生過的安裝。
    """

    receipt = {
        "schema_version": "s2_4_install_effect_receipt_v1",
        "plan_id": S2_4_PLAN_ID,
        "plan_core_digest": fixture_digest("s2-4-plan-core"),
        "idempotency_key": S2_4_PLAN_ID,
        "status": "APPLIED_INACTIVE",
        "aggregate_authorization_id": fixture_digest("s2-4-aggregate-authorization-id"),
        "aggregate_authorization_digest": fixture_digest("s2-4-aggregate-authorization"),
        "pg_authorization_id": fixture_digest("s2-4-pg-authorization-id"),
        "pg_authorization_digest": fixture_digest("s2-4-pg-authorization"),
        # 兩 scoped probe receipt 必須相異(同一 digest = 一個 probe 充當兩 scope ⇒ lineage 拒)。
        "prepare_sandbox_probe_receipt_digest": fixture_digest("s2-4-prepare-sandbox-probe"),
        "installed_unit_probe_receipt_digest": fixture_digest("s2-4-installed-unit-probe"),
        "prepare_result_digest": fixture_digest("s2-4-prepare-result"),
        "prepare_postcheck_digest": fixture_digest("s2-4-prepare-postcheck"),
        # null = 該族在 admission 當下 SOURCE_DEPENDENCY_FRESH(S2.4-AMEND-1 §3/§9.2 三值窮盡);
        # 鍵集由 APPLY step(2b)真正被閘的三族導出(S1.3 不入閘,故不在 receipt 面上)。
        "dependency_refresh_digests": {
            name: None for name in S2_4_APPLY_GATED_DEPENDENCY_CLASSES
        },
        "apply_row_results": [
            {
                "component_effect_class": effect_class,
                "result_digest": fixture_digest(f"s2-4-apply-result-{effect_class}"),
                "postcheck_digest": fixture_digest(f"s2-4-apply-postcheck-{effect_class}"),
            }
            for effect_class in validator.S2_4_APPLY_ROW_CLASS_ORDER
        ],
        "reverse_compensation_chain_digest": s2_4_install_plan.aggregate_rollback_digest(
            plan_id=S2_4_PLAN_ID
        ),
        "journal_digest": fixture_digest("s2-4-terminal-journal"),
        "unit_state": {"loaded": True, "disabled": True, "inactive": True},
        "service_flags": {
            "service_enabled": False,
            "service_active": False,
            "service_started_by_s2_4": False,
        },
        "evidence_class": "STRUCTURAL_ONLY",
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        "source_head": SOURCE_HEAD,
        "target_host": HOST,
        "trusted_host_time": ISSUED,
        "observed_at": ISSUED,
        "expires_at": expires_at,
    }
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    return receipt


def legacy_s2_4_receipt_stub() -> dict[str, Any]:
    """Codex-4 修前唯一被接受的形狀:canonical 自洽、但**沒有** closed schema/lineage 的兩鍵 stub。

    digest 三值鏈仍成立(self_digest 真的重算),所以它專門用來證明「digest 綁定 ≠ 上游站得住」。
    """

    receipt = {
        "schema_version": "s2_4_install_effect_receipt_v1",
        "status": "APPLIED_INACTIVE",
    }
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    return receipt


# core 綁定常量由 canonical 構造導出(不再是自由 hex;上游替身在 precheck 就會被重算抓到)。
S2_4_RECEIPT_DIGEST = s2_4_receipt()["self_digest"]


def s2_4_prestate() -> dict[str, Any]:
    return {
        "active_state": "inactive",
        "unit_file_state": "disabled",
        "n_restarts": 0,
        "invocation_id": "none",
    }


# ── S2.1 drill receipt(同 Codex-4:S2.5B precheck 也把它送進中央閘的委派分支)────────
# 路徑/常量一律由 WP3 inventory 導出;fixture 的 owner/stable 指紋是丟棄式 digest(此處不
# 宣稱任何真主機觀測——真 fence 屬 S2.1 EFFECT session)。
_DRILL_FRAGMENT_PATH = "/etc/systemd/system/" + lifecycle.S2_5_UNIT_NAME
_DRILL_FLOCK_PATH = "/run/arcane-equilibrium/aiml-engine-scanner/consumer.lock"
_DRILL_DSN_PATH = "/run/credentials/" + lifecycle.S2_5_UNIT_NAME + "/pg-dsn"
_DRILL_CONTROL_GROUP = "/system.slice/" + lifecycle.S2_5_UNIT_NAME
_DRILL_SCANNER_UID = 4001
_DRILL_APPLIER_NODE = "s2-1-quiesce-applier"
_DRILL_VERIFIER_NODE = "s2-1-quiesce-verifier"
# 丟棄式 armor:body 是嚴格 base64(schema 的 SSHSIG armor pattern 與 strict-base64 護欄都要過);
# 它**不是**任何真簽章——中央閘對 quiesce result 的 operator 授權只做結構綁定驗(見該葉 docstring)。
_DRILL_SIGNATURE_ARMOR = (
    b"-----BEGIN SSH SIGNATURE-----\n"
    b"QVJDQU5FLUVRVUlMSUJSSVVNLVMyLTUtVEVTVEtJVC1GSVhUVVJFLVNJR05BVFVSRQ==\n"
    b"-----END SSH SIGNATURE-----\n"
)


def _drill_host_inventory(
    *,
    main_pid: int = 4242,
    start_ticks: str | None = "998877",
    invocation: str = "inv-1",
    active_state: str = "active",
    sub_state: str = "running",
) -> dict[str, Any]:
    return {
        "owner": {"uid": _DRILL_SCANNER_UID, "unit": lifecycle.S2_5_UNIT_NAME},
        "process": {
            "main_pid": main_pid,
            "process_start_ticks": start_ticks,
            "boot_id": "boot-1",
            "cmdline_digest": fixture_digest("s2-1-drill-cmdline"),
        },
        "unit": {
            "load_state": "loaded",
            "active_state": active_state,
            "sub_state": sub_state,
            "fragment_path": _DRILL_FRAGMENT_PATH,
            "drop_in_paths": "",
            "need_daemon_reload": "no",
        },
        "cgroup": {"control_group": _DRILL_CONTROL_GROUP},
        "env_hash": fixture_digest("s2-1-drill-env"),
        "runtime_digest": fixture_digest("s2-1-drill-runtime"),
        "restart_policy": {
            "restart": "on-failure", "restart_usec": "5s", "timeout_stop_usec": "30s",
        },
        "watchdog": {"watchdog_usec": "0", "n_restarts": 0, "invocation_id": invocation},
        "queue": {
            "listen_channel": inventory.LISTEN_CHANNEL,
            "advisory_lock_name": inventory.ADVISORY_LOCK_NAME,
            "flock_path": _DRILL_FLOCK_PATH,
            "flock_held": True,
        },
    }


def _drill_db(*, held: bool, count: int, backend: bool, status: str) -> dict[str, Any]:
    return {
        "advisory_lock_held": held,
        "advisory_lock_holder_count": count,
        "backend_present": backend,
        "consumer_session_status": status,
        "listen_backlog_drained": True,
    }


def _drill_credential_exposure() -> dict[str, Any]:
    return {
        "dsn_file_path": _DRILL_DSN_PATH,
        "dsn_mode": "0600",
        "dsn_owner_uid": _DRILL_SCANNER_UID,
        "world_readable": False,
        "plaintext_ingress": False,
        "unit_hardening": {
            "no_new_privileges": "yes",
            "protect_system": "full",
            "private_tmp": "yes",
            "restrict_address_families": "AF_UNIX AF_INET",
        },
    }


def _drill_observation(
    phase: str,
    verdict: str,
    *,
    candidate_count: int,
    host_inventory: dict[str, Any],
    db_quiesce: dict[str, Any],
    observed_at: str,
    owner_fingerprint: str,
) -> dict[str, Any]:
    return quiesce.build_quiesce_observation(
        phase=phase,
        verdict=verdict,
        candidate_count=candidate_count,
        owner_fingerprint=owner_fingerprint,
        host_inventory=host_inventory,
        db_quiesce=db_quiesce,
        credential_exposure=_drill_credential_exposure(),
        applier_node=_DRILL_APPLIER_NODE,
        verifier_node=_DRILL_VERIFIER_NODE,
        verifier_capture_digest=fixture_digest("s2-1-drill-verifier-capture"),
        observed_at=observed_at,
    )


def drill_receipt(*, completed_at: str = ISSUED) -> dict[str, Any]:
    """真 ``quiesce_result_v1``(QUIESCED_STATIC_GUARDS_HELD)——過中央閘的 S2.1 drill 錨。

    Codex-4:S2.5B precheck 不再只看 ``status.startswith("QUIESCED")`` + digest 三值鏈,
    而是把這份 receipt 丟進中央閘的 quiesce 委派分支(closed schema + 逐 observation 再驗 +
    window adequacy + 新鮮度),故 fixture 必須是完整的 confirm→fence→held-window→restore 形狀。
    時間錨全取凍結常量;窗跨度 5s(= duration_seconds)由兩個 in-window 樣本張開。
    """

    drill_intent = quiesce.build_quiesce_intent(
        target_class=quiesce.DISPOSABLE_TARGET_CLASS,
        target_host=HOST,
        unit_fragment_path=_DRILL_FRAGMENT_PATH,
        expected_owner_fingerprint=fixture_digest("s2-1-drill-owner"),
        flock_path=_DRILL_FLOCK_PATH,
        observed_relations=["learning.alr_consumer_events"],
        observation_window={
            "duration_seconds": 5, "min_samples": 2, "sample_interval_seconds": 5,
        },
        applier_node_id=_DRILL_APPLIER_NODE,
        postcheck_node_id=_DRILL_VERIFIER_NODE,
        created_at=ISSUED,
        ttl_seconds=900,
        source_head=SOURCE_HEAD,
    )
    owner = fixture_digest("s2-1-drill-owner")
    stable = fixture_digest("s2-1-drill-stable-identity")
    fenced_inventory = _drill_host_inventory(
        main_pid=0, start_ticks=None, invocation="",
        active_state="inactive", sub_state="dead",
    )
    return quiesce.build_quiesce_fence_result(
        intent=drill_intent,
        status="QUIESCED_STATIC_GUARDS_HELD",
        owner_fingerprint=owner,
        pre_fence_observation=_drill_observation(
            "PRE_FENCE_INVENTORY", "CONFIRMED_SINGLE_OWNER", candidate_count=1,
            host_inventory=_drill_host_inventory(),
            db_quiesce=_drill_db(held=True, count=1, backend=True, status="OPEN"),
            observed_at=ISSUED, owner_fingerprint=owner,
        ),
        window_samples=[
            _drill_observation(
                "IN_WINDOW_STATIC_GUARD", "STATIC_GUARDS_HELD", candidate_count=0,
                host_inventory=fenced_inventory,
                db_quiesce=_drill_db(held=False, count=0, backend=False, status="STOPPED"),
                observed_at=ISSUED, owner_fingerprint=owner,
            ),
            _drill_observation(
                "IN_WINDOW_STATIC_GUARD", "STATIC_GUARDS_HELD", candidate_count=0,
                host_inventory=fenced_inventory,
                db_quiesce=_drill_db(held=False, count=0, backend=False, status="STOPPED"),
                observed_at=(ANCHOR + timedelta(seconds=5)).isoformat(),
                owner_fingerprint=owner,
            ),
        ],
        post_unfence_observation=_drill_observation(
            "POST_UNFENCE_RESTORATION", "RESTORED_HEALTHY", candidate_count=1,
            host_inventory=_drill_host_inventory(main_pid=5555, start_ticks="1002003", invocation="inv-2"),
            db_quiesce=_drill_db(held=True, count=1, backend=True, status="OPEN"),
            observed_at=ISSUED,
            owner_fingerprint=fixture_digest("s2-1-drill-owner-after-restore"),
        ),
        rollback_record=quiesce.build_quiesce_rollback(
            intent=drill_intent,
            pre_fence_stable_fingerprint=stable,
            post_unfence_stable_fingerprint=stable,
            owner_healthy=True,
            observed_at=ISSUED,
        ),
        operator_authorization=quiesce.build_operator_authorization(
            intent=drill_intent, source_head=SOURCE_HEAD
        ),
        operator_signature=_DRILL_SIGNATURE_ARMOR,
        apply_actor_node=_DRILL_APPLIER_NODE,
        started_at=ISSUED,
        completed_at=completed_at,
        evidence_class="LOCAL_REPRODUCIBLE",
    )


def legacy_drill_receipt_stub() -> dict[str, Any]:
    """Codex-4 修前唯一被接受的形狀:``status.startswith("QUIESCED")`` + 自洽 self_digest 的兩鍵 stub。"""

    receipt = {
        "schema_version": "quiesce_result_v1",
        "status": "QUIESCED_STATIC_GUARDS_HELD",
    }
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    return receipt


DRILL_DIGEST = drill_receipt()["self_digest"]


def empty_ledger() -> dict[str, Any]:
    return {"entries": []}


SIMULATED_INSTALL_LOCK_PATH = "/tmp/s2-5-testkit/simulated-s2-4-install.lock"
SIMULATED_LIFECYCLE_LOCK_PATH = "/tmp/s2-5-testkit/simulated-s2-5-lifecycle.lock"


class SimulatedInstallLockProbe:
    """**S2.4 install 鎖**的 probe-only 注入模擬(F3:與 lifecycle hold 是兩個資源)。

    ``held`` 可注入;``probes`` 記次數以斷言「真的探測過,不是 caller 自報 boolean」。
    刻意沒有 acquire/release —— 有 hold 面的物件會被型別互斥守衛擋掉。
    """

    def __init__(
        self, *, held: bool = False, lock_path: str = SIMULATED_INSTALL_LOCK_PATH
    ) -> None:
        self.held = bool(held)
        self.lock_path = lock_path
        self.probes = 0

    def flock_probe(self) -> dict[str, Any]:
        self.probes += 1
        return {"held": self.held, "exists": True, "lock_path": self.lock_path}


class SimulatedLifecycleLock:
    """**S2.5 lifecycle 鎖**的 hold-style 注入模擬(P2-2):取鎖/釋放次數與持有態可斷言。

    ``fail_release`` 讓 release 逸出(F4 的 typed release 用):真實世界對應「flock UN /
    close 失敗」——fd 仍被持有,鎖窗未被證明關閉。
    """

    def __init__(
        self,
        *,
        held: bool = False,
        fail_release: bool = False,
        lock_path: str = SIMULATED_LIFECYCLE_LOCK_PATH,
    ) -> None:
        self.held = bool(held)
        self.fail_release = bool(fail_release)
        self.lock_path = lock_path
        self.acquires = 0
        self.releases = 0
        self.holding = False

    def acquire(self) -> dict[str, Any]:
        self.acquires += 1
        if self.held or self.holding:
            return {
                "status": lifecycle.S2_5_LOCK_HELD,
                "lock_path": self.lock_path,
                "reasons": ["simulated: the lifecycle lock is held by another applier"],
            }
        self.holding = True
        return {
            "status": lifecycle.S2_5_LOCK_ACQUIRED,
            "lock_path": self.lock_path,
            "reasons": [],
        }

    def release(self) -> dict[str, Any]:
        self.releases += 1
        if self.fail_release:
            raise RuntimeError("simulated: the lifecycle lock release failed")
        released, self.holding = self.holding, False
        return {
            "status": (
                lifecycle.S2_5_LOCK_RELEASED if released else lifecycle.S2_5_LOCK_NOT_HELD
            ),
            "lock_path": self.lock_path,
            "reasons": [],
        }


# ── §8.1 受控 unit 狀態機 harness(真實主機零接觸)─────────────────────────────────
class SimulatedUnit:
    """一個受控 systemd unit 狀態機:driver 五動詞把 property dict 翻面,零 subprocess。"""

    def __init__(self, *, fragment_digest: str = FRAGMENT_DIGEST) -> None:
        self.properties: dict[str, str] = {
            "ActiveState": "inactive",
            "SubState": "dead",
            "UnitFileState": "disabled",
            "MainPID": "0",
            "NRestarts": "0",
            "InvocationID": "none",
            "FragmentDigest": fragment_digest,
            "DropInPaths": "",
            "NeedDaemonReload": "no",
        }
        self.wanted_by_link = False
        self.last_operation = "none"
        self.calls: list[str] = []
        self._pid = 4000
        self._invocation = 0
        self.fail_enable = False
        self.fail_rollback = False

    # driver 面(五動詞;無任何 caller 參數)。
    def enable_now(self) -> None:
        self.calls.append("enable_now")
        self.last_operation = "systemd_enable_now"
        if self.fail_enable:
            raise RuntimeError("harness: enable --now failed")
        self._pid += 1
        self._invocation += 1
        self.properties.update({
            "ActiveState": "active",
            "SubState": "running",
            "UnitFileState": "enabled",
            "MainPID": str(self._pid),
            "InvocationID": f"inv-{self._invocation}",
        })
        self.wanted_by_link = True

    def stop(self) -> None:
        self.calls.append("stop")
        self.last_operation = "systemd_stop_disable"
        if self.fail_rollback:
            raise RuntimeError("harness: stop failed")
        self.properties.update({"ActiveState": "inactive", "SubState": "dead", "MainPID": "0"})

    def disable(self) -> None:
        self.calls.append("disable")
        self.last_operation = "systemd_stop_disable"
        if self.fail_rollback:
            raise RuntimeError("harness: disable failed")
        self.properties["UnitFileState"] = "disabled"
        self.wanted_by_link = False

    def reset_failed(self) -> None:
        self.calls.append("reset_failed")
        self.last_operation = "systemd_reset_failed"
        self.properties["NRestarts"] = "0"

    def show(self) -> dict[str, str]:
        self.calls.append("show")
        return dict(self.properties)

    # harness 專屬(非 driver 面):模擬 manager 重啟(persistence 的 source 可證半邊)
    # 與 supervening restart 注入。
    def manager_restart(self) -> None:
        self._invocation += 1
        self.properties["InvocationID"] = f"inv-{self._invocation}"

    def supervening_restart(self) -> None:
        self._pid += 1
        self._invocation += 1
        self.properties.update({
            "NRestarts": str(int(self.properties["NRestarts"]) + 1),
            "MainPID": str(self._pid),
            "InvocationID": f"inv-{self._invocation}",
        })
        self.last_operation = "systemd_enable_now"


def _set_dotted(target: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = target
    for key in parts[:-1]:
        node = node[key]
    node[parts[-1]] = value


class HarnessObserver:
    """獨立 verifier node 的觀測面(faults 以 dotted path 注入逐維失敗)。"""

    def __init__(
        self,
        unit: SimulatedUnit,
        *,
        clock,
        verifier_node_id: str = "s2-5-independent-verifier",
        faults: dict[str, Any] | None = None,
        post_reset_overrides: dict[str, Any] | None = None,
        owner_signal_overrides: dict[str, Any] | None = None,
        evidence_age_seconds: int = 5,
    ) -> None:
        self.unit = unit
        self.clock = clock
        self.verifier_node_id = verifier_node_id
        self.faults = dict(faults or {})
        self.post_reset_overrides = dict(post_reset_overrides or {})
        self.owner_signal_overrides = dict(owner_signal_overrides or {})
        self.evidence_age_seconds = int(evidence_age_seconds)

    def observe_running_dimensions(self) -> dict[str, Any]:
        properties = self.unit.show()
        dimensions: dict[str, Any] = {
            "unit": {
                "active_state": properties["ActiveState"],
                "sub_state": properties["SubState"],
                "unit_file_state": properties["UnitFileState"],
                "main_pid": int(properties["MainPID"]),
                "n_restarts_baseline": int(properties["NRestarts"]),
                "fragment_digest_match": properties["FragmentDigest"] == FRAGMENT_DIGEST,
            },
            "pid_cgroup": {
                "cmdline_digest": CMDLINE_DIGEST,
                "control_group_match": True,
                "boot_id": "boot-1",
                "process_start_ticks": "1234567",
                "invocation_id": properties["InvocationID"],
            },
            "mount": {
                "launch_root_match": True,
                "loader_closure_match": True,
                "executable_mappings_in_manifest": True,
            },
            "network": {
                "address_families_ok": True,
                "ip_allow_loopback_only": True,
                "listening_sockets_empty": True,
            },
            "pg_identity": {
                "advisory_lock_holder_count": 1,
                "backend_role": "aiml_engine_scanner",
                "backend_database": "trading_ai",
                "session_started_seen": True,
                "unclosed_session_absent": True,
                "topology_guard_match": True,
            },
        }
        for dotted, value in self.faults.items():
            _set_dotted(dimensions, dotted, value)
        return dimensions

    def observe_enabled_persistence(self) -> dict[str, Any]:
        properties = self.unit.show()
        return {
            "unit_file_state": properties["UnitFileState"],
            "wanted_by_link_present": self.unit.wanted_by_link,
            "reboot_survival_observed": None,
        }

    def observe_owner_signals(self) -> dict[str, Any]:
        properties = self.unit.show()
        signals = dict(OWNER_SIGNALS)
        signals["main_pid"] = int(properties["MainPID"])
        signals["invocation_id"] = properties["InvocationID"]
        signals.update(self.owner_signal_overrides)
        return signals

    def oldest_evidence_at(self) -> str:
        return (self.clock() - timedelta(seconds=self.evidence_age_seconds)).isoformat()

    def observe_post_reset(self) -> dict[str, Any]:
        properties = self.unit.show()
        observation = {
            "n_restarts": int(properties["NRestarts"]),
            "invocation_id": properties["InvocationID"],
            "last_lifecycle_operation_kind": self.unit.last_operation,
            "active_state": properties["ActiveState"],
            "unit_file_state": properties["UnitFileState"],
            "stable_identity_match": True,
        }
        observation.update(self.post_reset_overrides)
        return observation


def fresh_state_root(tmp_path: Path, label: str = "state") -> Path:
    """每呼叫一個新的 state_root(journal/ledger 的 durable 面按 apply 隔離)。"""

    _STATE_SEQ[0] += 1
    return tmp_path / f"{label}-{_STATE_SEQ[0]}"


def apply_kwargs(
    *,
    tmp_path: Path,
    unit: SimulatedUnit,
    observers: HarnessObserver | None = None,
    clock=None,
    **overrides: Any,
) -> dict[str, Any]:
    """``apply_s2_5_start``/``apply_s2_5_final`` 的 happy-path 共同參數面(可逐鍵覆蓋)。"""

    clock = clock or frozen_clock()
    kwargs: dict[str, Any] = {
        "now": NOW,
        "replay_ledger": empty_ledger(),
        "target_class": "simulated_harness",
        "s2_4_install_effect_receipt": s2_4_receipt(),
        "s2_4_inactive_prestate": s2_4_prestate(),
        "loader_closure_observation": {
            "native_loader_closure_digest": LOADER_CLOSURE_DIGEST
        },
        "s2_4_recovery_clear": True,
        # F3:兩個 lock 面是兩個資源(S2.4 install probe-only / S2.5 lifecycle hold)。
        "install_lock_probe": SimulatedInstallLockProbe(),
        "lifecycle_lock": SimulatedLifecycleLock(),
        "state_root": tmp_path / "state",
        "observers": observers or HarnessObserver(unit, clock=clock),
        "owner_fingerprint": OWNER_FINGERPRINT,
        "clock": clock,
    }
    kwargs.update(overrides)
    return kwargs


def final_apply_kwargs(**kwargs: Any) -> dict[str, Any]:
    """``apply_s2_5_final`` 的參數面(S2.5B 不消費 S2.4 inactive 前態)。"""

    final_kwargs = apply_kwargs(**kwargs)
    final_kwargs.pop("s2_4_inactive_prestate", None)
    return final_kwargs


def a_side_setup(tmp_path: Path, monkeypatch, **core_overrides: Any):
    """S2.5A happy-path 全套:pinned throwaway key + signed permit + harness。"""

    private_key, public_key, fingerprint = mint_key(tmp_path)
    install_pinned_key(monkeypatch, public_key, fingerprint)
    intent = start_intent("S2_5A_START", **core_overrides)
    permit = signed_permit(private_key, intent)
    unit = SimulatedUnit()
    return private_key, intent, permit, unit


def real_pre_drill_receipt(tmp_path: Path, private_key: Path) -> dict[str, Any]:
    """P1-2:pre-drill 錨是**真的** S2.5A SOURCE_SIMULATION_PASS receipt(過中央閘),
    不再是自報 digest 的三鍵 stub(pinned key 須已由 caller 安裝)。"""

    intent = start_intent("S2_5A_START")
    permit = signed_permit(private_key, intent)
    unit = SimulatedUnit()
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **apply_kwargs(
            tmp_path=tmp_path, unit=unit,
            state_root=fresh_state_root(tmp_path, "pre-drill-state"),
        ),
    )
    assert verdict["status"] == "SOURCE_SIMULATION_PASS", verdict["reasons"]
    return verdict["receipt"]


def b_side_setup(
    tmp_path: Path, monkeypatch, *, pre_drill_receipt: dict[str, Any] | None = None
):
    """S2.5B happy-path 全套(harness unit 先走完 A 側 enable;回傳含 pre-drill 錨)。"""

    private_key, public_key, fingerprint = mint_key(tmp_path)
    install_pinned_key(monkeypatch, public_key, fingerprint)
    pre_drill = (
        pre_drill_receipt
        if pre_drill_receipt is not None
        else real_pre_drill_receipt(tmp_path, private_key)
    )
    intent = start_intent(
        "S2_5B_FINAL",
        pre_drill_attestation_digest=pre_drill["self_digest"],
    )
    permit = signed_permit(private_key, intent)
    unit = SimulatedUnit()
    unit.enable_now()
    return private_key, intent, permit, unit, pre_drill
