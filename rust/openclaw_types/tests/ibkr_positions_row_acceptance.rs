//! W5-S1 positions row 契約 acceptance 測試（source-only）。
//!
//! 只驗型別/校驗/serde 形態:不接觸 IBKR、不開 socket、不讀 secret、不做 IO、無牆鐘依賴。

use openclaw_types::{
    AssetLane, Broker, IbkrPositionsRowBlocker, IbkrPositionsRowV1, IbkrSecTypeV1,
    StockEtfCurrency, IBKR_POSITIONS_ROW_CONTRACT_ID,
};

#[test]
fn default_row_is_fail_closed() {
    use IbkrPositionsRowBlocker as B;

    let verdict = IbkrPositionsRowV1::default().validate();
    assert!(!verdict.accepted, "default 必須 fail-closed 拒");
    for expected in [
        B::ContractIdMismatch,
        B::SourceVersionMismatch,
        B::WrongAssetLane,
        B::WrongBroker,
        B::AccountIdMissing,
        B::ConIdInvalid,
        B::SymbolInvalid,
        B::SecTypeUnknownDenied,
        B::CurrencyDenied,
        B::ExchangeMissing,
        B::PositionDecimalInvalid,
        B::AvgCostDecimalInvalid,
    ] {
        assert!(
            verdict.blockers.contains(&expected),
            "缺 blocker {expected:?}"
        );
    }
}

#[test]
fn accepted_fixture_validates() {
    let row = IbkrPositionsRowV1::accepted_fixture();
    let verdict = row.validate();
    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(row.contract_id, IBKR_POSITIONS_ROW_CONTRACT_ID);
    assert_eq!(row.source_version, 1);
    assert_eq!(row.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(row.broker, Broker::Ibkr);
    assert_eq!(row.sec_type, IbkrSecTypeV1::Stk);
    assert_eq!(row.currency, StockEtfCurrency::Usd);
    assert!(!row.order_routed);
    assert!(!row.secret_content_serialized);
}

#[test]
fn sec_type_whitelist_is_stk_only_and_fail_closed() {
    // 白名單:僅 "STK"(IBKR 慣例 ETF 亦為 STK wire 值)。
    assert_eq!(
        IbkrSecTypeV1::classify_wire_sec_type("STK"),
        IbkrSecTypeV1::Stk
    );
    assert_eq!(IbkrSecTypeV1::Stk.as_wire_sec_type(), Some("STK"));
    // 表外 secType(含 margin/short/options/cfd 家族與大小寫變體)一律 UnknownDenied。
    for bad in [
        "OPT", "FUT", "CASH", "CFD", "BOND", "WAR", "FOP", "stk", "Stk", "ETF", "",
    ] {
        assert_eq!(
            IbkrSecTypeV1::classify_wire_sec_type(bad),
            IbkrSecTypeV1::UnknownDenied,
            "secType {bad:?} 必須 UnknownDenied"
        );
    }
    assert_eq!(IbkrSecTypeV1::UnknownDenied.as_wire_sec_type(), None);
    assert_eq!(IbkrSecTypeV1::default(), IbkrSecTypeV1::UnknownDenied);
}

#[test]
fn unknown_sec_type_row_is_rejected() {
    let row = IbkrPositionsRowV1 {
        sec_type: IbkrSecTypeV1::UnknownDenied,
        ..IbkrPositionsRowV1::accepted_fixture()
    };
    let verdict = row.validate();
    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![IbkrPositionsRowBlocker::SecTypeUnknownDenied]
    );
}

#[test]
fn short_position_is_denied_and_zero_flat_is_honest() {
    // 負倉 → short 永久 denied 的專屬 blocker。
    let short = IbkrPositionsRowV1 {
        position_decimal: "-100".to_string(),
        ..IbkrPositionsRowV1::accepted_fixture()
    };
    let verdict = short.validate();
    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![IbkrPositionsRowBlocker::ShortPositionDenied]
    );

    // 零倉(平倉後 flat row)為誠實表示,允許。
    let flat = IbkrPositionsRowV1 {
        position_decimal: "0".to_string(),
        ..IbkrPositionsRowV1::accepted_fixture()
    };
    assert!(flat.validate().accepted);
}

#[test]
fn fractional_position_and_garbage_decimals_split_correctly() {
    // 碎股數量為合法定點字串。
    let fractional = IbkrPositionsRowV1 {
        position_decimal: "0.5".to_string(),
        ..IbkrPositionsRowV1::accepted_fixture()
    };
    assert!(fractional.validate().accepted);

    // 非法 decimal(浮點噪音)→ 各自 blocker。
    use IbkrPositionsRowBlocker as B;
    let garbage = IbkrPositionsRowV1 {
        position_decimal: "1e3".to_string(),
        avg_cost_decimal: "NaN".to_string(),
        ..IbkrPositionsRowV1::accepted_fixture()
    };
    let verdict = garbage.validate();
    assert!(!verdict.accepted);
    for expected in [B::PositionDecimalInvalid, B::AvgCostDecimalInvalid] {
        assert!(verdict.blockers.contains(&expected), "缺 {expected:?}");
    }
}

#[test]
fn symbol_and_identity_field_rejections() {
    use IbkrPositionsRowBlocker as B;

    let row = IbkrPositionsRowV1 {
        con_id: 0,
        symbol: "spy lower".to_string(),
        exchange: "  ".to_string(),
        account_id: String::new(),
        ..IbkrPositionsRowV1::accepted_fixture()
    };
    let verdict = row.validate();
    assert!(!verdict.accepted);
    for expected in [
        B::ConIdInvalid,
        B::SymbolInvalid,
        B::ExchangeMissing,
        B::AccountIdMissing,
    ] {
        assert!(verdict.blockers.contains(&expected), "缺 {expected:?}");
    }

    // 規範化 symbol 允許 BRK.B / QQQ-X 形態。
    for ok in ["BRK.B", "QQQ", "VOO-TEST"] {
        let row = IbkrPositionsRowV1 {
            symbol: ok.to_string(),
            ..IbkrPositionsRowV1::accepted_fixture()
        };
        assert!(row.validate().accepted, "symbol {ok} 應合法");
    }
}

#[test]
fn boundary_flags_are_rejected() {
    use IbkrPositionsRowBlocker as B;

    let row = IbkrPositionsRowV1 {
        order_routed: true,
        secret_content_serialized: true,
        ..IbkrPositionsRowV1::accepted_fixture()
    };
    let verdict = row.validate();
    assert!(!verdict.accepted);
    for expected in [B::OrderRouted, B::SecretContentSerialized] {
        assert!(verdict.blockers.contains(&expected), "缺 {expected:?}");
    }
}

#[test]
fn serde_roundtrip_snake_case_stable() {
    let row = IbkrPositionsRowV1::accepted_fixture();
    let json = serde_json::to_value(&row).unwrap();
    assert_eq!(json["contract_id"], "ibkr_positions_row_v1");
    assert_eq!(json["sec_type"], "stk");
    assert_eq!(json["currency"], "usd");
    // 數量/成本為字串保真,非 JSON number。
    assert!(json["position_decimal"].is_string());
    assert!(json["avg_cost_decimal"].is_string());
    let back: IbkrPositionsRowV1 = serde_json::from_value(json).unwrap();
    assert_eq!(back, row);
}
