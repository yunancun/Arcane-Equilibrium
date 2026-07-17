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
    // W7-S1:send_order_framed 回 sealed WireBytes（NOTE-1 (a) 型別屏障;非裸 Vec<u8>）→ test 域 view。
    let wire = send_order_framed(grant, permit, frame);
    assert_eq!(wire.view(), &[0x01, 0x02, 0x03]);
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
    // 唯一取出路徑:mint permit + grant + send_order_framed → sealed WireBytes。
    let wire = send_order_framed(mint_test_grant(), OrderEffectPermit::mint(), frame);
    assert_eq!(wire.view(), &[0xAA]);
}

// ── (e) place/cancel encoder + §1.5 encode ceiling guard ─────────────────────

/// 骨架 placeOrder 請求 fixture（sv∈[145,157] band;whatIf=false 常態）。
fn sample_place_request() -> PlaceOrderWireRequest {
    PlaceOrderWireRequest {
        order_id: 42,
        symbol: "AAPL".to_string(),
        sec_type: "STK".to_string(),
        exchange: "SMART".to_string(),
        currency: "USD".to_string(),
        action: "BUY".to_string(),
        total_quantity_decimal: "10".to_string(),
        order_type: "LMT".to_string(),
        lmt_price_decimal: "150.25".to_string(),
        aux_price_decimal: String::new(),
        time_in_force: "DAY".to_string(),
        account: "DU111111".to_string(),
        transmit: true,
        outside_rth: false,
        cash_qty_decimal: String::new(),
        what_if: false,
    }
}

/// decode framed bytes → 欄位字串序（測試斷言用;4-byte 長度前綴後為 payload,沿 wire codec 慣例）。
fn decode_frame_fields(framed: &[u8]) -> Vec<String> {
    use crate::ibkr_tws_wire::decode_fields;
    decode_fields(&framed[4..]).expect("decode fields")
}

/// 斷言 encoder 回特定 typed reject（OrderFrame 刻意 sealed 非 Debug/PartialEq → 不比較 Ok 臂）。
fn assert_encode_reject(res: Result<OrderFrame, OrderEncodeReject>, expected: OrderEncodeReject) {
    match res {
        Ok(_) => panic!("expected encode reject, got Ok(OrderFrame)"),
        Err(e) => assert_eq!(e, expected),
    }
}

#[test]
fn place_order_encoder_skeleton_bytes() {
    let frame = encode_place_order(&sample_place_request(), 157).expect("encode place");
    // OrderFrame bytes 唯經 send_order_framed 出線 → 以 mint 取出後 decode 斷言骨架欄。
    let wire = send_order_framed(mint_test_grant(), OrderEffectPermit::mint(), frame);
    let fields = decode_frame_fields(wire.view());
    assert_eq!(fields[0], "3", "msg id = PLACE_ORDER");
    assert_eq!(fields[1], "42", "order id");
    assert_eq!(fields[2], "AAPL");
    assert_eq!(fields[6], "BUY", "action 承載欄");
    assert_eq!(fields[7], "10", "totalQuantity 承載欄");
    assert_eq!(fields[8], "LMT", "orderType 承載欄");
    assert_eq!(fields[9], "150.25", "lmtPrice");
    assert_eq!(*fields.last().unwrap(), "", "末欄 usePriceMgmtAlgo unset");
}

#[test]
fn place_order_encoder_carries_whatif_flag() {
    let mut req = sample_place_request();
    req.what_if = true;
    let frame = encode_place_order(&req, 150).expect("encode whatif");
    let wire = send_order_framed(mint_test_grant(), OrderEffectPermit::mint(), frame);
    let fields = decode_frame_fields(wire.view());
    // whatIf flag 承載於骨架末段（usePriceMgmtAlgo 之前一欄）。
    assert_eq!(fields[fields.len() - 2], "1", "whatIf flag=1");
}

#[test]
fn cancel_order_encoder_skeleton_bytes() {
    let frame = encode_cancel_order(42, 157).expect("encode cancel");
    let wire = send_order_framed(mint_test_grant(), OrderEffectPermit::mint(), frame);
    let fields = decode_frame_fields(wire.view());
    // ≤157 band = [4, VERSION=1, orderId]，無 manualOrderCancelTime。
    assert_eq!(
        fields,
        vec!["4".to_string(), "1".to_string(), "42".to_string()]
    );
}

#[test]
fn encode_ceiling_guard_refuses_above_157() {
    // §1.5 INV-ORDER-ENCODE:sv>157 一律拒產出（禁佈局猜送）。
    assert_encode_reject(
        encode_place_order(&sample_place_request(), 158),
        OrderEncodeReject::ServerVersionAboveCeiling {
            server_version: 158,
            ceiling: 157,
        },
    );
    assert_encode_reject(
        encode_cancel_order(42, 176),
        OrderEncodeReject::ServerVersionAboveCeiling {
            server_version: 176,
            ceiling: 157,
        },
    );
}

#[test]
fn encode_floor_guard_refuses_below_145() {
    assert_encode_reject(
        encode_place_order(&sample_place_request(), 144),
        OrderEncodeReject::ServerVersionBelowFloor {
            server_version: 144,
            floor: 145,
        },
    );
}

#[test]
fn encode_boundary_145_and_157_ok() {
    assert!(encode_place_order(&sample_place_request(), 145).is_ok());
    assert!(encode_place_order(&sample_place_request(), 157).is_ok());
    assert!(encode_cancel_order(1, 145).is_ok());
}

#[test]
fn place_order_encoder_rejects_malformed_fields() {
    let mut req = sample_place_request();
    req.total_quantity_decimal = "0".to_string(); // 非正 → 拒（is_positive_decimal_string）。
    assert_encode_reject(
        encode_place_order(&req, 150),
        OrderEncodeReject::FieldInvalid {
            field: "total_quantity",
        },
    );
    let mut req2 = sample_place_request();
    req2.account = "  ".to_string();
    assert_encode_reject(
        encode_place_order(&req2, 150),
        OrderEncodeReject::FieldInvalid { field: "account" },
    );
    let mut req3 = sample_place_request();
    req3.lmt_price_decimal = "abc".to_string();
    assert_encode_reject(
        encode_place_order(&req3, 150),
        OrderEncodeReject::FieldInvalid { field: "lmt_price" },
    );
}
