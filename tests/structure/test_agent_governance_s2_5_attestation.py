"""S2.5(WP5)attestation 葉——SSHSIG 域分離 / payload 綁定 / dead-man / watchdog 導出(§8.2/§8.3)。

真 SSHSIG 驗簽(throwaway key;S2.0/S2.1/S2.4 同款):域分離不是文案——把 S2.4 install /
S2.1 quiesce / S2.0 observer namespace 的簽章重放為 S2.5 permit/attestor,`ssh-keygen -Y verify`
必須失敗。observer_gate 的 `stale` 與 watchdog_last 的 `unexplained_restart_detected` 是**導出**
值(caller 不可自證)。
"""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for _candidate in (HELPERS, ML_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_s2_5_attestation as attestation  # noqa: E402
import s2_5_testkit as kit  # noqa: E402

_FOREIGN_NAMESPACES = (
    "arcane-equilibrium-aiml-s2-install",           # S2.4 aggregate permit
    "arcane-equilibrium-aiml-s2-4-install-apply",   # S2.4 attestor
    "arcane-equilibrium-aiml-s2-quiesce-fence",     # S2.1
    "arcane-equilibrium-aiml-s2-observer-bootstrap",  # S2.0
)


def _setup(tmp_path, monkeypatch, phase="S2_5A_START"):
    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    intent = kit.start_intent(phase)
    return private_key, intent


def test_valid_permit_verifies_and_binds_the_exact_intent(tmp_path, monkeypatch):
    private_key, intent = _setup(tmp_path, monkeypatch)
    permit = kit.signed_permit(private_key, intent)
    assert attestation.verify_s2_5_operator_permit(permit, intent, now=kit.NOW) == []


@pytest.mark.parametrize("namespace", _FOREIGN_NAMESPACES)
def test_foreign_namespace_signatures_never_replay_as_an_s2_5_permit(
    tmp_path, monkeypatch, namespace
):
    private_key, intent = _setup(tmp_path, monkeypatch)
    permit = kit.signed_permit(private_key, intent, namespace=namespace)
    errors = attestation.verify_s2_5_operator_permit(permit, intent, now=kit.NOW)
    assert any("SSH signature is invalid" in error for error in errors)


def test_permit_payload_tamper_and_field_set_drift_are_rejected(tmp_path, monkeypatch):
    private_key, intent = _setup(tmp_path, monkeypatch)
    permit = kit.signed_permit(private_key, intent)
    # 逐欄竄改:任何 payload 欄位換值都必被抓(簽章 bytes 或 exact-intent 比對)。
    for field, value in (
        ("start_core_digest", "sha256:" + "9" * 64),
        ("target_host", "not-trade-core"),
        ("rollback_budget_seconds", 999),
        ("expires_at", (kit.ANCHOR + timedelta(days=9)).isoformat()),
    ):
        tampered = json.loads(json.dumps(permit))
        tampered["payload_binding"][field] = value
        assert attestation.verify_s2_5_operator_permit(tampered, intent, now=kit.NOW)
    # 少一欄 = 少簽一個綁定 ⇒ 拒。
    dropped = json.loads(json.dumps(permit))
    del dropped["payload_binding"]["rollback_budget_seconds"]
    errors = attestation.verify_s2_5_operator_permit(dropped, intent, now=kit.NOW)
    assert any("exact §5.6 field list" in error for error in errors)
    # profile 替換(S2.5B 的 identity 冒用在 A permit 上)⇒ 拒。
    swapped = json.loads(json.dumps(permit))
    swapped["profile_identity"] = attestation.S2_5B_FINAL_PERMIT_IDENTITY
    assert attestation.verify_s2_5_operator_permit(swapped, intent, now=kit.NOW)


def test_permit_expiry_skew_and_ttl_ceiling_fail_closed(tmp_path, monkeypatch):
    private_key, intent = _setup(tmp_path, monkeypatch)
    permit = kit.signed_permit(private_key, intent)
    # 過期。
    late = (kit.ANCHOR + timedelta(hours=2)).isoformat()
    assert any(
        "expired" in error
        for error in attestation.verify_s2_5_operator_permit(permit, intent, now=late)
    )
    # skew:now 遠早於 issued_at。
    early = (kit.ANCHOR - timedelta(minutes=30)).isoformat()
    assert any(
        "clock skew" in error
        for error in attestation.verify_s2_5_operator_permit(permit, intent, now=early)
    )
    # TTL 上限:>900s 的 permit 一律拒(§5.6)。
    long_core = kit.start_core(expires_at=(kit.ANCHOR + timedelta(hours=1)).isoformat())
    import agent_governance_s2_5_lifecycle as lifecycle
    long_intent = lifecycle.build_s2_5_start_intent(long_core, expires_at=kit.EXPIRES)
    long_permit = kit.signed_permit(private_key, long_intent)
    assert any(
        "TTL" in error
        for error in attestation.verify_s2_5_operator_permit(
            long_permit, long_intent, now=kit.NOW
        )
    )


def test_replay_ledger_is_consume_once_and_chain_tamper_fails(tmp_path, monkeypatch):
    private_key, intent = _setup(tmp_path, monkeypatch)
    permit = kit.signed_permit(private_key, intent)
    ledger = kit.empty_ledger()
    entry = attestation.consume_s2_5_authorization(
        ledger, permit, start_id=intent["start_id"], consumed_at=kit.NOW
    )
    assert ledger["entries"] == [entry]
    # 重複消費 ⇒ 拒。
    verdict = attestation.derive_s2_5_replay_binding(
        permit, ledger, start_id=intent["start_id"]
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    # hash chain 竄改 ⇒ 拒(斷鏈即斷)。
    ledger["entries"][0]["consumed_at"] = "2031-01-01T00:00:00+00:00"
    other_intent = kit.start_intent()
    other_permit = kit.signed_permit(private_key, other_intent)
    tampered = attestation.derive_s2_5_replay_binding(
        other_permit, ledger, start_id=other_intent["start_id"]
    )
    assert tampered["status"] == "AUTHORIZATION_REJECTED"
    assert any("hash chain" in reason for reason in tampered["reasons"])


def test_observer_gate_stale_is_derived_from_evidence_age():
    fresh = attestation.build_observer_gate(
        verifier_node_id="v", max_evidence_age_seconds=60,
        oldest_evidence_at=kit.ISSUED,
        evaluated_at=(kit.ANCHOR + timedelta(seconds=30)).isoformat(),
    )
    assert fresh["stale"] is False
    over_age = attestation.build_observer_gate(
        verifier_node_id="v", max_evidence_age_seconds=60,
        oldest_evidence_at=kit.ISSUED,
        evaluated_at=(kit.ANCHOR + timedelta(seconds=300)).isoformat(),
    )
    assert over_age["stale"] is True
    future_sample = attestation.build_observer_gate(
        verifier_node_id="v", max_evidence_age_seconds=60,
        oldest_evidence_at=(kit.ANCHOR + timedelta(seconds=30)).isoformat(),
        evaluated_at=kit.ISSUED,
    )
    assert future_sample["stale"] is True  # 證據時間倒流 = 不可信 = stale。


def test_watchdog_last_derivation_is_not_caller_declared():
    clean = attestation.build_watchdog_last(
        n_restarts_before=0, n_restarts_after=0,
        invocation_id_before="inv-1", invocation_id_after="inv-1",
        last_lifecycle_operation_kind="systemd_reset_failed",
        authorized_operation_kind="systemd_reset_failed",
    )
    assert clean["unexplained_restart_detected"] is False
    assert clean["watchdog_usec"] == "none"  # O-2:unit 無 WatchdogSec。
    supervening = attestation.build_watchdog_last(
        n_restarts_before=0, n_restarts_after=1,
        invocation_id_before="inv-1", invocation_id_after="inv-2",
        last_lifecycle_operation_kind="systemd_reset_failed",
        authorized_operation_kind="systemd_reset_failed",
    )
    assert supervening["unexplained_restart_detected"] is True
    unauthorized = attestation.build_watchdog_last(
        n_restarts_before=0, n_restarts_after=0,
        invocation_id_before="inv-1", invocation_id_after="inv-1",
        last_lifecycle_operation_kind="systemd_enable_now",
        authorized_operation_kind="systemd_reset_failed",
    )
    assert unauthorized["last_transition_matches_authorized_op"] is False
    assert unauthorized["unexplained_restart_detected"] is True


def test_attestor_verification_rejects_all_four_bad_paths(tmp_path, monkeypatch):
    private_key, intent = _setup(tmp_path, monkeypatch)
    dims = {"unit": {"active_state": "active"}}
    gate = {"verifier_node_id": "v", "stale": False}
    good = kit.signed_attestation(
        private_key, attestation_kind="A", intent=intent,
        running_dimensions=dims, observer_gate=gate,
    )
    assert attestation.verify_s2_5_trusted_host_attestation(
        good, intent_digest=intent["self_digest"], running_dimensions=dims,
        observer_gate=gate, now=kit.NOW,
    ) == []
    # 1. 無簽章(None artifact)。
    absent = attestation.verify_s2_5_trusted_host_attestation(
        None, intent_digest=intent["self_digest"], running_dimensions=dims,
        observer_gate=gate, now=kit.NOW,
    )
    assert any("permit alone never yields" in error for error in absent)
    # 2. 壞簽(payload 竄改後簽章不再覆蓋)。
    tampered = json.loads(json.dumps(good))
    tampered["running_dimensions_digest"] = "sha256:" + "9" * 64
    assert attestation.verify_s2_5_trusted_host_attestation(
        tampered, intent_digest=intent["self_digest"], running_dimensions=dims,
        observer_gate=gate, now=kit.NOW,
    )
    # 3. 錯 fingerprint(信任根不符)。
    _other_key, other_public, other_fingerprint = kit.mint_key(tmp_path, "s2-5-other")
    monkeypatch.setattr(attestation, "S2_5_TRUST_ROOT_FINGERPRINT", other_fingerprint)
    assert any(
        "fingerprint" in error
        for error in attestation.verify_s2_5_trusted_host_attestation(
            good, intent_digest=intent["self_digest"], running_dimensions=dims,
            observer_gate=gate, now=kit.NOW,
        )
    )
    monkeypatch.undo()
    # monkeypatch.undo 也還原了 pinned key;重釘後測第 4 路。
    _pk, public_key, fingerprint = kit.mint_key(tmp_path, "s2-5-repin")
    # 4. 錯 namespace(S2.4 attestor namespace 的簽章重放)。
    kit.install_pinned_key(
        monkeypatch,
        private_key.with_suffix(".pub").read_text(encoding="ascii").split()[0]
        + " "
        + private_key.with_suffix(".pub").read_text(encoding="ascii").split()[1],
        __import__("subprocess").run(
            ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
            check=True, capture_output=True, text=True,
        ).stdout.split()[1],
    )
    foreign = kit.signed_attestation(
        private_key, attestation_kind="A", intent=intent,
        running_dimensions=dims, observer_gate=gate,
        namespace="arcane-equilibrium-aiml-s2-4-install-apply",
    )
    assert any(
        "SSH signature is invalid" in error
        for error in attestation.verify_s2_5_trusted_host_attestation(
            foreign, intent_digest=intent["self_digest"], running_dimensions=dims,
            observer_gate=gate, now=kit.NOW,
        )
    )


def test_permit_signature_never_unlocks_an_attested_status(tmp_path, monkeypatch):
    """permit ≠ attestation:拿 permit namespace 簽出的「attestation」必驗簽失敗。"""

    private_key, intent = _setup(tmp_path, monkeypatch)
    dims = {"unit": {"active_state": "active"}}
    gate = {"verifier_node_id": "v", "stale": False}
    forged = kit.signed_attestation(
        private_key, attestation_kind="A", intent=intent,
        running_dimensions=dims, observer_gate=gate,
        namespace=attestation.S2_5A_START_PERMIT_NAMESPACE,
    )
    assert any(
        "SSH signature is invalid" in error
        for error in attestation.verify_s2_5_trusted_host_attestation(
            forged, intent_digest=intent["self_digest"], running_dimensions=dims,
            observer_gate=gate, now=kit.NOW,
        )
    )
