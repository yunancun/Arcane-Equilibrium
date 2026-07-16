//! W5-S1 executions row 契約 acceptance 測試（source-only）。
//!
//! 只驗型別/校驗/serde 形態:不接觸 IBKR、不開 socket、不讀 secret、不做 IO、無牆鐘依賴
//! （`exec_time` fixture 為占位字串,本契約不斷言其格式）。

use openclaw_types::{
    AssetLane, Broker, IbkrExecutionSideV1, IbkrExecutionsRowBlocker, IbkrExecutionsRowV1,
    IbkrSecTypeV1, StockEtfCurrency, IBKR_EXECUTIONS_ROW_CONTRACT_ID,
};

#[test]
fn default_row_is_fail_closed() {
    use IbkrExecutionsRowBlocker as B;

    let verdict = IbkrExecutionsRowV1::default().validate();
    assert!(!verdict.accepted, "default 必須 fail-closed 拒");
    for expected in [
        B::ContractIdMismatch,
        B::SourceVersionMismatch,
        B::WrongAssetLane,
        B::WrongBroker,
        B::AccountIdMissing,
        B::ExecIdMissing,
        B::ConIdInvalid,
        B::SymbolInvalid,
        B::SecTypeUnknownDenied,
        B::CurrencyDenied,
        B::ExecTimeMissing,
        B::SideUnknownDenied,
        B::SharesDecimalInvalid,
        B::PriceDecimalInvalid,
        B::ExchangeMissing,
    ] {
        assert!(
            verdict.blockers.contains(&expected),
            "缺 blocker {expected:?}"
        );
    }
}

#[test]
fn accepted_fixture_validates() {
    let row = IbkrExecutionsRowV1::accepted_fixture();
    let verdict = row.validate();
    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(row.contract_id, IBKR_EXECUTIONS_ROW_CONTRACT_ID);
    assert_eq!(row.source_version, 1);
    assert_eq!(row.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(row.broker, Broker::Ibkr);
    assert_eq!(row.side, IbkrExecutionSideV1::Bought);
    // instrument identity 束(F2):同 positions-row 白名單姿態。
    assert!(row.con_id > 0);
    assert_eq!(row.sec_type, IbkrSecTypeV1::Stk);
    assert_eq!(row.currency, StockEtfCurrency::Usd);
    assert!(!row.order_routed);
    assert!(!row.secret_content_serialized);
}

#[test]
fn instrument_identity_bundle_is_fail_closed() {
    use IbkrExecutionsRowBlocker as B;

    // 表外 secType(margin/options/cfd 家族的型別層投影)→ 拒。
    let unknown_sec = IbkrExecutionsRowV1 {
        sec_type: IbkrSecTypeV1::classify_wire_sec_type("OPT"),
        ..IbkrExecutionsRowV1::accepted_fixture()
    };
    let verdict = unknown_sec.validate();
    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![B::SecTypeUnknownDenied]);

    // con_id/symbol/currency 逐欄拒。
    let broken = IbkrExecutionsRowV1 {
        con_id: 0,
        symbol: "spy lower".to_string(),
        currency: StockEtfCurrency::UnknownDenied,
        ..IbkrExecutionsRowV1::accepted_fixture()
    };
    let verdict = broken.validate();
    assert!(!verdict.accepted);
    for expected in [B::ConIdInvalid, B::SymbolInvalid, B::CurrencyDenied] {
        assert!(verdict.blockers.contains(&expected), "缺 {expected:?}");
    }

    // 白名單 secType round-trip:wire "STK" → Stk → wire "STK"(F4 反向)。
    let stk = IbkrSecTypeV1::classify_wire_sec_type("STK");
    assert_eq!(stk, IbkrSecTypeV1::Stk);
    assert_eq!(
        IbkrSecTypeV1::classify_wire_sec_type(stk.as_wire_sec_type().unwrap()),
        stk
    );
}

#[test]
fn wire_side_whitelist_round_trips_and_unknown_is_denied() {
    // 白名單:BOT/SLD(IBKR 官方 Execution.side 慣例)。
    assert_eq!(
        IbkrExecutionSideV1::classify_wire_side("BOT"),
        IbkrExecutionSideV1::Bought
    );
    assert_eq!(
        IbkrExecutionSideV1::classify_wire_side("SLD"),
        IbkrExecutionSideV1::Sold
    );
    assert_eq!(IbkrExecutionSideV1::Bought.as_wire_side(), Some("BOT"));
    assert_eq!(IbkrExecutionSideV1::Sold.as_wire_side(), Some("SLD"));
    // 表外/大小寫變體/裸語義詞 → 一律 UnknownDenied(fail-closed)。
    for bad in ["BUY", "SELL", "bot", "sld", "B", "S", "", "BOT "] {
        assert_eq!(
            IbkrExecutionSideV1::classify_wire_side(bad),
            IbkrExecutionSideV1::UnknownDenied,
            "side {bad:?} 必須 UnknownDenied"
        );
    }
    assert_eq!(IbkrExecutionSideV1::UnknownDenied.as_wire_side(), None);
    assert_eq!(
        IbkrExecutionSideV1::default(),
        IbkrExecutionSideV1::UnknownDenied
    );
    // F4 反向斷言:每個非 UnknownDenied 變體 classify(as_wire) 恆等回自身。
    for side in [IbkrExecutionSideV1::Bought, IbkrExecutionSideV1::Sold] {
        let wire = side.as_wire_side().expect("非 Unknown 變體必有 wire 對應");
        assert_eq!(IbkrExecutionSideV1::classify_wire_side(wire), side);
    }
}

#[test]
fn unknown_side_row_is_rejected() {
    let row = IbkrExecutionsRowV1 {
        side: IbkrExecutionSideV1::UnknownDenied,
        ..IbkrExecutionsRowV1::accepted_fixture()
    };
    let verdict = row.validate();
    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![IbkrExecutionsRowBlocker::SideUnknownDenied]
    );
}

#[test]
fn shares_and_price_must_be_strictly_positive_fixed_point() {
    use IbkrExecutionsRowBlocker as B;

    // 零量/零價 → 拒(成交行不可能為零)。
    let zero = IbkrExecutionsRowV1 {
        shares_decimal: "0".to_string(),
        price_decimal: "0.00".to_string(),
        ..IbkrExecutionsRowV1::accepted_fixture()
    };
    let verdict = zero.validate();
    assert!(!verdict.accepted);
    for expected in [B::SharesDecimalInvalid, B::PriceDecimalInvalid] {
        assert!(verdict.blockers.contains(&expected), "缺 {expected:?}");
    }

    // 負值/浮點噪音 → 拒。
    let noise = IbkrExecutionsRowV1 {
        shares_decimal: "-100".to_string(),
        price_decimal: "4.1e2".to_string(),
        ..IbkrExecutionsRowV1::accepted_fixture()
    };
    let verdict = noise.validate();
    assert!(verdict.blockers.contains(&B::SharesDecimalInvalid));
    assert!(verdict.blockers.contains(&B::PriceDecimalInvalid));

    // 碎股成交合法。
    let fractional = IbkrExecutionsRowV1 {
        shares_decimal: "0.25".to_string(),
        ..IbkrExecutionsRowV1::accepted_fixture()
    };
    assert!(fractional.validate().accepted);
}

#[test]
fn missing_keys_and_time_are_rejected() {
    use IbkrExecutionsRowBlocker as B;

    let row = IbkrExecutionsRowV1 {
        exec_id: "  ".to_string(),
        exec_time: String::new(),
        exchange: String::new(),
        account_id: String::new(),
        ..IbkrExecutionsRowV1::accepted_fixture()
    };
    let verdict = row.validate();
    assert!(!verdict.accepted);
    for expected in [
        B::ExecIdMissing,
        B::ExecTimeMissing,
        B::ExchangeMissing,
        B::AccountIdMissing,
    ] {
        assert!(verdict.blockers.contains(&expected), "缺 {expected:?}");
    }
}

#[test]
fn order_and_perm_ids_carry_wire_values_without_unverified_invariants() {
    // order_id/perm_id 為 wire 原值承載:本契約不鑄 UNVERIFIED 取值域不變量
    // (語義由 W5-S3 消化現勘後 pin)——零值/大值皆不觸 blocker。
    let row = IbkrExecutionsRowV1 {
        order_id: 0,
        perm_id: 0,
        ..IbkrExecutionsRowV1::accepted_fixture()
    };
    assert!(row.validate().accepted);
    let big = IbkrExecutionsRowV1 {
        order_id: i64::MAX,
        perm_id: i64::MAX,
        ..IbkrExecutionsRowV1::accepted_fixture()
    };
    assert!(big.validate().accepted);
}

#[test]
fn boundary_flags_are_rejected() {
    use IbkrExecutionsRowBlocker as B;

    let row = IbkrExecutionsRowV1 {
        order_routed: true,
        secret_content_serialized: true,
        ..IbkrExecutionsRowV1::accepted_fixture()
    };
    let verdict = row.validate();
    assert!(!verdict.accepted);
    for expected in [B::OrderRouted, B::SecretContentSerialized] {
        assert!(verdict.blockers.contains(&expected), "缺 {expected:?}");
    }
}

#[test]
fn serde_roundtrip_snake_case_stable() {
    let row = IbkrExecutionsRowV1::accepted_fixture();
    let json = serde_json::to_value(&row).unwrap();
    assert_eq!(json["contract_id"], "ibkr_executions_row_v1");
    assert_eq!(json["side"], "bought");
    assert_eq!(json["sec_type"], "stk");
    assert_eq!(json["currency"], "usd");
    // 數量/價格為字串保真,非 JSON number。
    assert!(json["shares_decimal"].is_string());
    assert!(json["price_decimal"].is_string());
    let back: IbkrExecutionsRowV1 = serde_json::from_value(json).unwrap();
    assert_eq!(back, row);
}
