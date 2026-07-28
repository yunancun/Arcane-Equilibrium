"""S2.5(WP5)lifecycle 守衛面——fail-closed / precheck / journal / phase 綁定(design §8.2/§8.4)。

每一條守衛都有自己的紅測試:driver=None 零變更、production 無 attestor 永不 attested、
四項 precheck 逐一失敗即拒、journal 非終端殘留/corrupt 擋新 effect、phase 替換拒、
verifier==applier 拒、replay 重複消費拒。E4 mutation 面:§8.4 的每一刀(刪 S2.4-receipt
綁定/刪 loader-closure 重驗/刪 recovery 檢查/短路 supervening-restart)都會讓這裡至少
一支測試變紅——守衛不是命名出來的,是被這些注入逼出來的。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for _candidate in (HELPERS, ML_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_s2_5_attestation as attestation  # noqa: E402
import agent_governance_s2_5_driver as driver_leaf  # noqa: E402
import agent_governance_s2_5_lifecycle as lifecycle  # noqa: E402
import s2_5_testkit as kit  # noqa: E402


class UntouchableDriver:
    """任何方法被碰即炸——driver=None/前置拒絕路徑的零接觸斷言用。"""

    def __getattr__(self, name):  # noqa: D105
        raise AssertionError(f"driver surface {name!r} was touched before authorization")


# ── driver=None:reachable 但 authority-locked(零變更、零 driver 呼叫)────────────
def test_driver_none_returns_external_verification_pending_with_zero_mutation(
    tmp_path, monkeypatch
):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, None, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any("authority-locked" in reason for reason in verdict["reasons"])
    assert unit.calls == []  # mock driver 未被觸碰。
    assert not (tmp_path / "state").exists()  # 零 journal/ledger 寫入(state root 未被建立)。


def test_final_driver_none_returns_external_verification_pending(tmp_path, monkeypatch):
    _key, intent, permit, unit, pre_drill = kit.b_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_final(
        intent, permit, None,
        **kit.final_apply_kwargs(tmp_path=tmp_path, unit=unit),
        s2_1_drill_receipt=kit.drill_receipt(),
        pre_drill_attestation=pre_drill,
    )
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert unit.calls[:1] == ["enable_now"]  # 只有 harness 準備動作,applier 零接觸。


# ── §3.1 四項 precheck 逐一失敗即拒(§8.4:刪任一檢查即紅)────────────────────────
def test_missing_s2_4_receipt_binding_is_rejected_before_any_driver_touch(
    tmp_path, monkeypatch
):
    _key, intent, permit, _unit = kit.a_side_setup(tmp_path, monkeypatch)
    for broken in (
        None,
        {"schema_version": "s2_4_install_effect_receipt_v1", "status": "APPLIED_INACTIVE",
         "self_digest": "sha256:" + "9" * 64},  # digest 不符 = 名字相同的替身
        {"schema_version": "s2_4_install_effect_receipt_v1", "status": "RECOVERY_REQUIRED",
         "self_digest": kit.S2_4_RECEIPT_DIGEST},  # 非 APPLIED_INACTIVE
    ):
        verdict = lifecycle.apply_s2_5_start(
            intent, permit, UntouchableDriver(),
            **kit.apply_kwargs(
                tmp_path=tmp_path, unit=kit.SimulatedUnit(),
                s2_4_install_effect_receipt=broken,
            ),
        )
        assert verdict["status"] == "REQUEST_REJECTED"
        assert any("APPLIED_INACTIVE" in reason for reason in verdict["reasons"])


def test_loader_closure_drift_is_rejected(tmp_path, monkeypatch):
    _key, intent, permit, _unit = kit.a_side_setup(tmp_path, monkeypatch)
    for broken in (None, {"native_loader_closure_digest": "sha256:" + "9" * 64}):
        verdict = lifecycle.apply_s2_5_start(
            intent, permit, UntouchableDriver(),
            **kit.apply_kwargs(
                tmp_path=tmp_path, unit=kit.SimulatedUnit(),
                loader_closure_observation=broken,
            ),
        )
        assert verdict["status"] == "REQUEST_REJECTED"
        assert any("native-loader" in reason for reason in verdict["reasons"])


def test_unresolved_s2_4_recovery_blocks_the_start(tmp_path, monkeypatch):
    _key, intent, permit, _unit = kit.a_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, UntouchableDriver(),
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=kit.SimulatedUnit(), s2_4_recovery_clear=False,
        ),
    )
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert any("S2_4_RECOVERY_UNRESOLVED" in reason for reason in verdict["reasons"])


def test_held_install_lock_blocks_the_start(tmp_path, monkeypatch):
    # P1-5:install_lock_free 由注入 lock 介面的 flock 探測導出——持鎖 ⇒ typed 拒。
    _key, intent, permit, _unit = kit.a_side_setup(tmp_path, monkeypatch)
    probe = kit.SimulatedLockProbe(held=True)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, UntouchableDriver(),
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=kit.SimulatedUnit(), lock_probe=probe,
        ),
    )
    assert verdict["status"] == "REQUEST_REJECTED"
    assert any("install lock" in reason for reason in verdict["reasons"])
    assert probe.probes == 1  # 真的探測過,不是自報。
    # 無 lock 介面 = unproven-free ⇒ 同樣拒(caller 自報 boolean 不再是縫)。
    verdict2 = lifecycle.apply_s2_5_start(
        intent, permit, UntouchableDriver(),
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=kit.SimulatedUnit(), lock_probe=None,
        ),
    )
    assert verdict2["status"] == "REQUEST_REJECTED"
    assert any("install lock" in reason for reason in verdict2["reasons"])


def test_live_prestate_mismatch_refuses_a_lookalike_unit(tmp_path, monkeypatch):
    # 前態不是 S2.4 的 loaded/disabled/inactive(如已 active)⇒ 拒 start。
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    unit.enable_now()  # 先偷跑成 active——S2.5A 必須拒絕接手一個已活的替身
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert verdict["status"] == "REQUEST_REJECTED"
    assert any("pre-state" in reason for reason in verdict["reasons"])
    # fragment 替身同拒。
    _key2, intent2, permit2, _u = kit.a_side_setup(tmp_path, monkeypatch)
    fake_unit = kit.SimulatedUnit(fragment_digest="sha256:" + "9" * 64)
    verdict2 = lifecycle.apply_s2_5_start(
        intent2, permit2, fake_unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=fake_unit)
    )
    assert verdict2["status"] == "REQUEST_REJECTED"


# ── phase 綁定與 S2.5B 前置 ───────────────────────────────────────────────────
def test_phase_substitution_is_rejected_by_both_appliers(tmp_path, monkeypatch):
    _key, intent_b, permit_b, unit, pre_drill = kit.b_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_start(
        intent_b, permit_b, UntouchableDriver(),
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit),
    )
    assert verdict["status"] == "REQUEST_REJECTED"
    assert any("phase" in reason for reason in verdict["reasons"])
    _key2, intent_a, permit_a, unit2 = kit.a_side_setup(tmp_path, monkeypatch)
    verdict2 = lifecycle.apply_s2_5_final(
        intent_a, permit_a, UntouchableDriver(),
        **kit.final_apply_kwargs(tmp_path=tmp_path, unit=unit2),
        s2_1_drill_receipt=kit.drill_receipt(),
        pre_drill_attestation=pre_drill,
    )
    assert verdict2["status"] == "REQUEST_REJECTED"


def test_final_requires_the_exact_drill_and_pre_drill_bindings(tmp_path, monkeypatch):
    _key, intent, permit, unit, pre_drill = kit.b_side_setup(tmp_path, monkeypatch)
    # 缺 drill receipt / digest 不符 / 內容被竄改的 pre-drill(重算即斷)三路皆拒。
    for kwargs in (
        {"s2_1_drill_receipt": None, "pre_drill_attestation": pre_drill},
        {"s2_1_drill_receipt": dict(kit.drill_receipt(), self_digest="sha256:" + "9" * 64),
         "pre_drill_attestation": pre_drill},
        {"s2_1_drill_receipt": kit.drill_receipt(),
         "pre_drill_attestation": dict(pre_drill, status="ATTESTATION_FAILED")},
    ):
        verdict = lifecycle.apply_s2_5_final(
            intent, permit, UntouchableDriver(),
            **kit.final_apply_kwargs(tmp_path=tmp_path, unit=unit),
            **kwargs,
        )
        assert verdict["status"] == "REQUEST_REJECTED", verdict


# ── 授權面(§8.2)────────────────────────────────────────────────────────────
def test_missing_or_invalid_permit_is_rejected_before_the_driver(tmp_path, monkeypatch):
    _key, intent, permit, _unit = kit.a_side_setup(tmp_path, monkeypatch)
    # 無 permit。
    verdict = lifecycle.apply_s2_5_start(
        intent, None, UntouchableDriver(),
        **kit.apply_kwargs(tmp_path=tmp_path, unit=kit.SimulatedUnit()),
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    # payload 竄改(rollback budget 換值 ⇒ 簽章 bytes 變)。
    tampered = json.loads(json.dumps(permit))
    tampered["payload_binding"]["rollback_budget_seconds"] = 999
    verdict2 = lifecycle.apply_s2_5_start(
        intent, tampered, UntouchableDriver(),
        **kit.apply_kwargs(tmp_path=tmp_path, unit=kit.SimulatedUnit()),
    )
    assert verdict2["status"] == "AUTHORIZATION_REJECTED"


def test_replay_ledger_absent_or_consumed_authorization_is_rejected(tmp_path, monkeypatch):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    # 無 ledger ⇒ 消費不可證 ⇒ 拒。
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, UntouchableDriver(),
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, replay_ledger=None),
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    # 成功消費一次後,同一張 permit 重放 ⇒ AUTHORIZATION_REJECTED(rollback 不釋放)。
    ledger = kit.empty_ledger()
    first = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, replay_ledger=ledger),
    )
    assert first["status"] == "SOURCE_SIMULATION_PASS"
    unit2 = kit.SimulatedUnit()
    second = lifecycle.apply_s2_5_start(
        intent, permit, unit2,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit2, replay_ledger=ledger),
    )
    assert second["status"] == "AUTHORIZATION_REJECTED"
    assert any("already consumed" in reason for reason in second["reasons"])
    assert unit2.calls == []


# ── verifier 獨立性與 journal ─────────────────────────────────────────────────
def test_verifier_must_differ_from_applier(tmp_path, monkeypatch):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    observers = kit.HarnessObserver(
        unit, clock=kit.frozen_clock(), verifier_node_id="s2-5-start-applier"
    )
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, observers=observers),
    )
    assert verdict["status"] == "REQUEST_REJECTED"
    assert any("differ from the applier" in reason for reason in verdict["reasons"])


def test_non_terminal_or_corrupt_journal_blocks_a_new_effect(tmp_path, monkeypatch):
    _key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True)
    # 非終端殘留(**別的** start 留下的殘留同樣擋:reconcile 掃整個 state_root)。
    residue_path = state_root / f"s2-5-{'0' * 64}.journal.json"
    residue_path.write_text(json.dumps({
        "schema_version": "s2_5_start_journal_v1_informal",
        "start_id": "s2-5-" + "0" * 64, "state": "APPLYING",
        "updated_at": kit.NOW, "history": [],
    }), encoding="utf-8")
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert unit.calls == []
    # corrupt journal。
    residue_path.write_text("{not json", encoding="utf-8")
    verdict2 = lifecycle.apply_s2_5_start(
        intent, permit, unit, **kit.apply_kwargs(tmp_path=tmp_path, unit=unit)
    )
    assert verdict2["status"] == "RECOVERY_REQUIRED"
    assert any("JOURNAL_CORRUPT" in reason for reason in verdict2["reasons"])
    # journal 面缺席(driver 在場)一樣 fail-closed。
    verdict3 = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, state_root=None),
    )
    assert verdict3["status"] == "RECOVERY_REQUIRED"
    assert unit.calls == []


# ── production 面:permit 單獨在場永不 attested;attestor 才是唯一鑰匙 ────────────────
def test_production_with_valid_permit_but_no_attestor_never_yields_attested(
    tmp_path, monkeypatch
):
    private_key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(tmp_path=tmp_path, unit=unit, target_class="production"),
    )
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    receipt = verdict["receipt"]
    assert receipt["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert receipt["trusted_host_attestation"] is None
    assert receipt["evidence_class"] != "PLATFORM_OR_EXTERNAL_ATTESTED"


def test_production_with_verified_attestor_reaches_running_attested(tmp_path, monkeypatch):
    """key-custody 縫的存在證明:同一把(丟棄式)信任根簽出的 attestor 真的解鎖 attested。

    這裡的 throwaway key 就是「production 不可達的原因是 key custody 而非構造不可達」的
    對照組——真 §9.1 私鑰不在 Mac/trade-core,故 production lane 實際永遠停在 PENDING。
    """

    private_key, intent, permit, unit = kit.a_side_setup(tmp_path, monkeypatch)
    clock = kit.frozen_clock()
    observers = kit.HarnessObserver(unit, clock=clock)
    # 先走一遍拿到 exact 觀測(attestor 簽的是 exact dims/gate digest)。
    preview_unit = kit.SimulatedUnit()
    preview_observers = kit.HarnessObserver(preview_unit, clock=clock)
    preview = lifecycle.apply_s2_5_start(
        intent, kit.signed_permit(private_key, intent), preview_unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=preview_unit, observers=preview_observers,
            state_root=kit.fresh_state_root(tmp_path, "preview-state"),
        ),
    )
    assert preview["status"] == "SOURCE_SIMULATION_PASS"
    attested = kit.signed_attestation(
        private_key,
        attestation_kind="A",
        intent=intent,
        running_dimensions=preview["receipt"]["running_dimensions"],
        observer_gate=preview["receipt"]["observer_gate"],
    )
    verdict = lifecycle.apply_s2_5_start(
        intent, permit, unit,
        **kit.apply_kwargs(
            tmp_path=tmp_path, unit=unit, observers=observers,
            target_class="production", trusted_host_attestation=attested,
            state_root=kit.fresh_state_root(tmp_path, "prod-state"),
        ),
    )
    assert verdict["status"] == "RUNNING_ATTESTED", verdict["reasons"]
    assert verdict["receipt"]["evidence_class"] == "PLATFORM_OR_EXTERNAL_ATTESTED"


# ── driver 葉 allowlist(§7)─────────────────────────────────────────────────
def test_driver_argv_allowlist_is_closed_and_runnerless_by_default():
    projection = driver_leaf.s2_5_driver_abi_projection()
    assert projection["allowlisted_verbs"]["enable_now"] == [
        "/usr/bin/systemctl", "enable", "--now",
        "arcane-equilibrium-aiml-engine-scanner.service",
    ]
    for verb in ("daemon-reload", "kill", "restart", "start", "mask"):
        with pytest.raises(driver_leaf.S2_5DriverContractError):
            driver_leaf.allowlisted_systemctl_argv(verb)
    with pytest.raises(driver_leaf.S2_5DriverContractError):
        driver_leaf.allowlisted_systemctl_argv("show --user")
    # 無 runner 的 production driver 任何動詞都 typed 拒(不會靜默真執行)。
    bare = driver_leaf.TypedSystemdDriver()
    with pytest.raises(driver_leaf.S2_5DriverContractError):
        bare.show()


def test_attestation_window_budget_shapes_are_enforced_by_schema(tmp_path, monkeypatch):
    # min_samples=0 / interval=0 這類形狀由 closed schema 直接拒(中央閘)。
    _key, intent, permit, _unit = kit.a_side_setup(tmp_path, monkeypatch)
    broken = json.loads(json.dumps(intent))
    broken["core"]["attestation_window"]["min_samples"] = 0
    broken["core_digest"] = attestation.canonical_digest(broken["core"])
    broken["start_id"] = "s2-5-" + broken["core_digest"].split(":", 1)[1]
    import aiml_gate_receipt_validator as validator
    broken["self_digest"] = validator.artifact_self_digest(broken)
    errors = validator.validate_aiml_artifact(broken, now=kit.NOW)
    assert errors
