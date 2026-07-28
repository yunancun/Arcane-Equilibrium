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
S2_4_RECEIPT_DIGEST = "sha256:" + "b" * 64
LAUNCH_DIGEST = "sha256:" + "c" * 64
APPLICATION_DIGEST = "sha256:" + "d" * 64
BASE_TREE_DIGEST = "sha256:" + "e" * 64
LOADER_CLOSURE_DIGEST = "sha256:" + "f" * 64
DRILL_DIGEST = "sha256:" + "1" * 64
CMDLINE_DIGEST = "sha256:" + "2" * 64
OWNER_FINGERPRINT = "sha256:" + "3" * 64
_SIGN_SEQ = [0]


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


def s2_4_receipt() -> dict[str, Any]:
    return {
        "schema_version": "s2_4_install_effect_receipt_v1",
        "status": "APPLIED_INACTIVE",
        "self_digest": S2_4_RECEIPT_DIGEST,
    }


def s2_4_prestate() -> dict[str, Any]:
    return {
        "active_state": "inactive",
        "unit_file_state": "disabled",
        "n_restarts": 0,
        "invocation_id": "none",
    }


def drill_receipt() -> dict[str, Any]:
    return {
        "schema_version": "quiesce_result_v1",
        "status": "QUIESCED_STATIC_GUARDS_HELD_RESTORED",
        "self_digest": DRILL_DIGEST,
    }


def empty_ledger() -> dict[str, Any]:
    return {"entries": []}


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
        evidence_age_seconds: int = 5,
    ) -> None:
        self.unit = unit
        self.clock = clock
        self.verifier_node_id = verifier_node_id
        self.faults = dict(faults or {})
        self.post_reset_overrides = dict(post_reset_overrides or {})
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
        "install_lock_free": True,
        "journal_path": tmp_path / "journal" / "s2_5.journal.json",
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


def b_side_setup(tmp_path: Path, monkeypatch, *, pre_drill_receipt: dict[str, Any]):
    """S2.5B happy-path 全套(harness unit 先走完 A 側 enable)。"""

    private_key, public_key, fingerprint = mint_key(tmp_path)
    install_pinned_key(monkeypatch, public_key, fingerprint)
    intent = start_intent(
        "S2_5B_FINAL",
        pre_drill_attestation_digest=pre_drill_receipt["self_digest"],
    )
    permit = signed_permit(private_key, intent)
    unit = SimulatedUnit()
    unit.enable_now()
    return private_key, intent, permit, unit
