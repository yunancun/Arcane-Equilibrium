//! W7-S0 order transport-gating 骨架單元測試（恆拒地基）。
//!
//! 覆蓋:①`EffectEnvelopeRequiredStub` 恆拒（production 唯一 provider）;②test 域鑄 permit →
//! `send_order_framed` 取出 order bytes（唯一出站位點,型別上需 permit）;③capability gate
//! accept（accepted_fixture）;④capability gate deny（paper verb 破口 / denied verb 放行破口）。
//! **INV-ORDER**:`OrderEffectPermit::mint`（W7-S4a 起 `pub(crate)`）唯一 production 呼叫點 =
//! `check_effect_contact` `Ok` 臂,而該函數 S4a 零 production caller → mint 呼叫 DCE → production
//! 恆無 permit。本檔（test 域）另可鑄以驗 transport 骨架。源級守衛見結構測試。

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

// ── byte-golden round-trip（golden 由 pinned ibapi 9.81.1 `client.py placeOrder` 逐位捕捉;
//    canonical STK LMT DAY order,orderId=42/AAPL/SMART/USD/BUY/10/150.25/DU111111,
//    transmit=true/outsideRth=false/whatIf=false/cashQty unset。禁人審替代——golden 即官方 wire）──

/// sv=145 golden（108 欄;無 discretionaryUpToLimitPrice / usePriceMgmtAlgo）。
const GOLDEN_145: &[&str] = &[
    "3",
    "42",
    "0",
    "AAPL",
    "STK",
    "",
    "0.0",
    "",
    "",
    "SMART",
    "",
    "USD",
    "",
    "",
    "",
    "",
    "BUY",
    "10",
    "LMT",
    "150.25",
    "",
    "DAY",
    "",
    "DU111111",
    "",
    "0",
    "",
    "1",
    "0",
    "0",
    "0",
    "0",
    "0",
    "0",
    "0",
    "",
    "0",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "0",
    "",
    "-1",
    "0",
    "",
    "",
    "0",
    "",
    "",
    "1",
    "1",
    "",
    "0",
    "",
    "",
    "",
    "",
    "",
    "0",
    "",
    "",
    "",
    "",
    "0",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "0",
    "",
    "",
    "0",
    "0",
    "",
    "",
    "0",
    "",
    "0",
    "0",
    "0",
    "0",
    "",
    "1.7976931348623157e+308",
    "1.7976931348623157e+308",
    "1.7976931348623157e+308",
    "1.7976931348623157e+308",
    "1.7976931348623157e+308",
    "0",
    "",
    "",
    "",
    "1.7976931348623157e+308",
    "",
    "",
    "",
    "",
    "0",
    "0",
];
/// sv=151 golden（110 欄;+discretionaryUpToLimitPrice(148) +usePriceMgmtAlgo(151)）。
const GOLDEN_151: &[&str] = &[
    "3",
    "42",
    "0",
    "AAPL",
    "STK",
    "",
    "0.0",
    "",
    "",
    "SMART",
    "",
    "USD",
    "",
    "",
    "",
    "",
    "BUY",
    "10",
    "LMT",
    "150.25",
    "",
    "DAY",
    "",
    "DU111111",
    "",
    "0",
    "",
    "1",
    "0",
    "0",
    "0",
    "0",
    "0",
    "0",
    "0",
    "",
    "0",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "0",
    "",
    "-1",
    "0",
    "",
    "",
    "0",
    "",
    "",
    "1",
    "1",
    "",
    "0",
    "",
    "",
    "",
    "",
    "",
    "0",
    "",
    "",
    "",
    "",
    "0",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "0",
    "",
    "",
    "0",
    "0",
    "",
    "",
    "0",
    "",
    "0",
    "0",
    "0",
    "0",
    "",
    "1.7976931348623157e+308",
    "1.7976931348623157e+308",
    "1.7976931348623157e+308",
    "1.7976931348623157e+308",
    "1.7976931348623157e+308",
    "0",
    "",
    "",
    "",
    "1.7976931348623157e+308",
    "",
    "",
    "",
    "",
    "0",
    "0",
    "0",
    "",
];

fn encoded_fields(req: &PlaceOrderWireRequest, sv: i32) -> Vec<String> {
    let frame = encode_place_order(req, sv).expect("encode place");
    let wire = send_order_framed(mint_test_grant(), OrderEffectPermit::mint(), frame);
    decode_frame_fields(wire.view())
}

#[test]
fn place_order_byte_exact_vs_pinned_ibapi_145_151_157() {
    // sv=145：無兩 sv-gated 末欄。
    assert_eq!(encoded_fields(&sample_place_request(), 145), GOLDEN_145);
    // sv=151 與 sv=157：band 內佈局同（usePriceMgmtAlgo≥151;二者間無新增 placeOrder 欄）。
    assert_eq!(encoded_fields(&sample_place_request(), 151), GOLDEN_151);
    assert_eq!(encoded_fields(&sample_place_request(), 157), GOLDEN_151);
    // sv=148：僅 +discretionaryUpToLimitPrice（109 欄;無 usePriceMgmtAlgo）。
    let f148 = encoded_fields(&sample_place_request(), 148);
    assert_eq!(f148.len(), 109);
    assert_eq!(&f148[..108], GOLDEN_145);
    assert_eq!(f148[108], "0", "discretionaryUpToLimitPrice @148");
}

#[test]
fn place_order_caller_field_positions_and_whatif() {
    // whatIf flag 位於 pinned idx 85（cashQty 之前;非訊息末尾）。
    let mut req = sample_place_request();
    req.what_if = true;
    let f = encoded_fields(&req, 157);
    assert_eq!(f[85], "1", "whatIf @85");
    assert_eq!(
        f[101], "1.7976931348623157e+308",
        "cashQty unset 哨兵 @101 未受 whatIf 影響"
    );
    // transmit @27 / outsideRth @33。
    let mut req2 = sample_place_request();
    req2.transmit = false;
    req2.outside_rth = true;
    let f2 = encoded_fields(&req2, 157);
    assert_eq!(f2[27], "0", "transmit @27");
    assert_eq!(f2[33], "1", "outsideRth @33");
}

#[test]
fn place_order_mkt_empties_lmt_and_cashqty_uses_unset_sentinel() {
    // MKT 單:lmtPrice 空欄(handle_empty);cashQty 未設 → UNSET_DOUBLE 哨兵(plain make_field,非空欄)。
    let mut req = sample_place_request();
    req.order_type = "MKT".to_string();
    req.lmt_price_decimal = String::new();
    let f = encoded_fields(&req, 157);
    assert_eq!(f[18], "MKT", "orderType");
    assert_eq!(f[19], "", "MKT lmtPrice 空欄(handle_empty)");
    assert_eq!(
        f[101], "1.7976931348623157e+308",
        "cashQty 未設 → UNSET 哨兵(非空欄;DIVERGENT-1 修正:非 handle_empty)"
    );
    // caller 設 cashQty → 透傳 decimal。
    let mut req2 = sample_place_request();
    req2.cash_qty_decimal = "3.5".to_string();
    assert_eq!(encoded_fields(&req2, 157)[101], "3.5");
}

#[test]
fn place_order_rejects_embedded_nul_field() {
    // E3-N1/E2-F1:caller 字串內嵌 NUL → encode_fields_checked 拒(wire 注入防護)。
    let mut req = sample_place_request();
    req.symbol = "AA\0PL".to_string();
    assert_encode_reject(
        encode_place_order(&req, 157),
        OrderEncodeReject::WireFieldRejected("embedded NUL"),
    );
    let mut req2 = sample_place_request();
    req2.account = "DUéÉ".to_string(); // 非 ASCII
    assert_encode_reject(
        encode_place_order(&req2, 157),
        OrderEncodeReject::WireFieldRejected("non-ascii"),
    );
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
