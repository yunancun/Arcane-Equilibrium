//! W7-S0 order transport-gating 骨架單元測試（恆拒地基）。
//!
//! 覆蓋:①`EffectEnvelopeRequiredStub` 恆拒（production 唯一 provider）;②test 域鑄 permit →
//! `send_order_framed` 取出 order bytes（唯一出站位點,型別上需 permit）;③capability gate
//! accept（accepted_fixture）;④capability gate deny（paper verb 破口 / denied verb 放行破口）。
//! **INV-ORDER**:production 無 `OrderEffectPermit::mint`（本檔 cfg(test) 才可鑄）→ 恆無 permit。

use super::*;
use openclaw_types::StockEtfBrokerCapabilityEntryV1;

// ── (b) 恆拒 provider ────────────────────────────────────────────────────────

#[test]
fn effect_stub_denies_unconditionally() {
    // production 唯一 provider 恆 Err(EnvelopeRequired);無任何放行路徑（放行臂 S4）。
    let mut stub = EffectEnvelopeRequiredStub;
    // OrderEffectPermit 刻意非 Debug（sealed）→ 不 unwrap_err,以 matches! 斷言恆拒。
    assert!(matches!(stub.check(), Err(EffectDenied::EnvelopeRequired)));
    // 反覆呼叫仍恆拒（無狀態翻轉開關）。
    assert!(matches!(stub.check(), Err(EffectDenied::EnvelopeRequired)));
}

// ── (c) send_order_framed 是唯一 order 出站位點（型別上需 permit）─────────────

#[test]
fn send_order_framed_requires_permit_and_yields_order_bytes() {
    // test 域鑄 permit（S0 唯一鑄造點=cfg(test);production 無此符號）。
    let permit = OrderEffectPermit::mint();
    let frame = OrderFrame::from_order_bytes(vec![0x01, 0x02, 0x03]);
    // grant 唯 governor 放行時鑄——test 用 pacing governor 取一枚真 grant。
    let grant = mint_test_grant();
    let bytes = send_order_framed(grant, permit, frame);
    assert_eq!(bytes, vec![0x01, 0x02, 0x03]);
}

/// test 輔助:向真 pacing governor 取一枚 `OutboundGrant`（不偽造 grant 構造子）。
fn mint_test_grant() -> OutboundGrant {
    use crate::ibkr_tws_pacing::{OutboundClass, PacingConfig, PacingGovernor, SubmitOutcome};
    let mut gov = PacingGovernor::new(PacingConfig::default(), 0);
    // SubmitOutcome/OutboundGrant 皆非 Debug（結構性封裝）→ 不 format,只解構。
    if let SubmitOutcome::Admitted(grant) = gov.submit(OutboundClass::AccountData, 0) {
        grant
    } else {
        panic!("pacing governor did not admit initial AccountData submit");
    }
}

// ── (d) capability registry machine-check ────────────────────────────────────

#[test]
fn capability_gate_accepts_admitted_registry() {
    // accepted_fixture = paper verb PaperRehearsal+rust_owned、denied verb Denied → 閘放行。
    let registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    assert_eq!(order_effect_capability_gate(&registry), Ok(()));
}

#[test]
fn capability_gate_denies_when_registry_contract_invalid() {
    // 空 registry（validate 不 accepted）→ RegistryContractInvalid。
    let registry = StockEtfBrokerCapabilityRegistryV1::default();
    match order_effect_capability_gate(&registry) {
        Err(OrderEffectCapabilityDenial::RegistryContractInvalid(_)) => {}
        other => panic!("expected RegistryContractInvalid, got {other:?}"),
    }
}

#[test]
fn capability_gate_denies_when_paper_verb_scope_tampered() {
    // 把 PaperOrderSubmit 的 authority_scope 竄成 ReadOnly（effect 授權破口）→ validate 先攔
    // （scope mismatch），本閘回 RegistryContractInvalid（縱深:validate 是第一道）。
    let mut registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    for entry in registry.operations.iter_mut() {
        if entry.operation == BrokerOperation::PaperOrderSubmit {
            entry.authority_scope = AuthorityScope::ReadOnly;
        }
    }
    // pin 具體變體:scope mismatch 先被 types validate() 攔 → RegistryContractInvalid（第一道）。
    assert!(matches!(
        order_effect_capability_gate(&registry),
        Err(OrderEffectCapabilityDenial::RegistryContractInvalid(_))
    ));
}

#[test]
fn capability_gate_denies_when_denied_verb_opened() {
    // 移除 LiveOrderSubmit 的 typed_denial_reason 並改 scope=PaperRehearsal（放行破口）→ 拒。
    let mut registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    for entry in registry.operations.iter_mut() {
        if entry.operation == BrokerOperation::LiveOrderSubmit {
            entry.authority_scope = AuthorityScope::PaperRehearsal;
            entry.typed_denial_reason = None;
        }
    }
    assert!(order_effect_capability_gate(&registry).is_err());
}

#[test]
fn capability_gate_denies_when_paper_verb_missing() {
    // 直接丟掉 PaperOrderCancel entry（矩陣缺格）→ 拒（validate OperationMissing → 契約無效）。
    let mut registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    registry
        .operations
        .retain(|entry| entry.operation != BrokerOperation::PaperOrderCancel);
    assert!(order_effect_capability_gate(&registry).is_err());
}

// ── OrderFrame bytes 封裝（no pub accessor;唯 send_order_framed 取出）────────────

#[test]
fn order_frame_bytes_only_flow_through_send_order_framed() {
    // 建構 entry 借用以確認型別可見（結構性:OrderFrame 無 pub bytes accessor）。
    let _entry_type_check: Option<StockEtfBrokerCapabilityEntryV1> = None;
    let frame = OrderFrame::from_order_bytes(vec![0xAA]);
    // 唯一取出路徑:mint permit + grant + send_order_framed。
    let bytes = send_order_framed(mint_test_grant(), OrderEffectPermit::mint(), frame);
    assert_eq!(bytes, vec![0xAA]);
}
