//! W5-S1 commissions row 契約 acceptance 測試（source-only）。
//!
//! 只驗型別/校驗/serde 形態:不接觸 IBKR、不開 socket、不讀 secret、不做 IO、無牆鐘依賴。
//! 重點覆蓋 realizedPnL 的缺席語義（`None`=誠實缺席;禁默認 0 假值）。

use openclaw_types::{
    AssetLane, Broker, IbkrCommissionsRowBlocker, IbkrCommissionsRowV1, IbkrExecutionsRowV1,
    StockEtfCurrency, IBKR_COMMISSIONS_ROW_CONTRACT_ID,
};

#[test]
fn default_row_is_fail_closed() {
    use IbkrCommissionsRowBlocker as B;

    let verdict = IbkrCommissionsRowV1::default().validate();
    assert!(!verdict.accepted, "default 必須 fail-closed 拒");
    for expected in [
        B::ContractIdMismatch,
        B::SourceVersionMismatch,
        B::WrongAssetLane,
        B::WrongBroker,
        B::ExecIdMissing,
        B::CommissionDecimalInvalid,
        B::CurrencyDenied,
    ] {
        assert!(
            verdict.blockers.contains(&expected),
            "缺 blocker {expected:?}"
        );
    }
}

#[test]
fn accepted_fixture_validates_with_absent_realized_pnl() {
    let row = IbkrCommissionsRowV1::accepted_fixture();
    let verdict = row.validate();
    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(row.contract_id, IBKR_COMMISSIONS_ROW_CONTRACT_ID);
    assert_eq!(row.source_version, 1);
    assert_eq!(row.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(row.broker, Broker::Ibkr);
    assert_eq!(row.currency, StockEtfCurrency::Usd);
    // 缺席語義:fixture 以 None 示範——缺席≠0,且缺席合法。
    assert_eq!(row.realized_pnl_decimal, None);
    assert!(!row.order_routed);
    assert!(!row.secret_content_serialized);
}

#[test]
fn present_realized_pnl_accepts_signed_values() {
    // 存在時:正/負/零皆為合法簽名定點字串。
    for pnl in ["12.50", "-3.75", "0"] {
        let row = IbkrCommissionsRowV1 {
            realized_pnl_decimal: Some(pnl.to_string()),
            ..IbkrCommissionsRowV1::accepted_fixture()
        };
        assert!(row.validate().accepted, "realizedPnL {pnl:?} 應合法");
    }
}

#[test]
fn present_but_invalid_realized_pnl_is_rejected() {
    // Some("")/浮點噪音/哨兵殘留形態 → 拒(缺席必須用 None 表達,不得用垃圾字串)。
    for bad in ["", " ", "1e308", "NaN", "1.7976931348623157E308", "--1"] {
        let row = IbkrCommissionsRowV1 {
            realized_pnl_decimal: Some(bad.to_string()),
            ..IbkrCommissionsRowV1::accepted_fixture()
        };
        let verdict = row.validate();
        assert!(!verdict.accepted, "Some({bad:?}) 應被拒");
        assert_eq!(
            verdict.blockers,
            vec![IbkrCommissionsRowBlocker::RealizedPnlDecimalInvalid]
        );
    }
}

#[test]
fn commission_is_signed_fixed_point_and_rejects_noise() {
    use IbkrCommissionsRowBlocker as B;

    // 負佣金(rebate 形態)簽名保真,不拒。
    let rebate = IbkrCommissionsRowV1 {
        commission_decimal: "-0.12".to_string(),
        ..IbkrCommissionsRowV1::accepted_fixture()
    };
    assert!(rebate.validate().accepted);

    // 浮點噪音/空字串 → 拒。
    for bad in ["", "1e-3", "NaN", "+1.25"] {
        let row = IbkrCommissionsRowV1 {
            commission_decimal: bad.to_string(),
            ..IbkrCommissionsRowV1::accepted_fixture()
        };
        let verdict = row.validate();
        assert!(!verdict.accepted, "commission {bad:?} 應被拒");
        assert!(verdict.blockers.contains(&B::CommissionDecimalInvalid));
    }
}

#[test]
fn exec_id_join_key_links_to_executions_row_fixture() {
    // 關聯鍵語義:commissions fixture 與 executions fixture 同 exec_id(消化層 join 面)。
    let commission = IbkrCommissionsRowV1::accepted_fixture();
    let execution = IbkrExecutionsRowV1::accepted_fixture();
    assert_eq!(commission.exec_id, execution.exec_id);

    // 空關聯鍵 → 拒。
    let orphan = IbkrCommissionsRowV1 {
        exec_id: "  ".to_string(),
        ..IbkrCommissionsRowV1::accepted_fixture()
    };
    let verdict = orphan.validate();
    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![IbkrCommissionsRowBlocker::ExecIdMissing]
    );
}

#[test]
fn wrong_lane_currency_and_boundary_flags_are_rejected() {
    use IbkrCommissionsRowBlocker as B;

    let row = IbkrCommissionsRowV1 {
        asset_lane: AssetLane::CryptoPerp,
        broker: Broker::Bybit,
        currency: StockEtfCurrency::UnknownDenied,
        order_routed: true,
        secret_content_serialized: true,
        ..IbkrCommissionsRowV1::accepted_fixture()
    };
    let verdict = row.validate();
    assert!(!verdict.accepted);
    for expected in [
        B::WrongAssetLane,
        B::WrongBroker,
        B::CurrencyDenied,
        B::OrderRouted,
        B::SecretContentSerialized,
    ] {
        assert!(verdict.blockers.contains(&expected), "缺 {expected:?}");
    }
}

#[test]
fn serde_roundtrip_preserves_absent_and_present_pnl() {
    // 缺席(None)round-trip:JSON null,不得變 0。
    let absent = IbkrCommissionsRowV1::accepted_fixture();
    let json = serde_json::to_value(&absent).unwrap();
    assert_eq!(json["contract_id"], "ibkr_commissions_row_v1");
    assert!(json["realized_pnl_decimal"].is_null());
    assert!(json["commission_decimal"].is_string());
    let back: IbkrCommissionsRowV1 = serde_json::from_value(json).unwrap();
    assert_eq!(back, absent);
    assert_eq!(back.realized_pnl_decimal, None);

    // 存在(Some)round-trip:字串保真。
    let present = IbkrCommissionsRowV1 {
        realized_pnl_decimal: Some("-3.75".to_string()),
        ..IbkrCommissionsRowV1::accepted_fixture()
    };
    let json = serde_json::to_value(&present).unwrap();
    assert_eq!(json["realized_pnl_decimal"], "-3.75");
    let back: IbkrCommissionsRowV1 = serde_json::from_value(json).unwrap();
    assert_eq!(back, present);
}
