//! W5-S1 account-summary row 契約 acceptance 測試（source-only）。
//!
//! 只驗型別/校驗/serde 形態:不接觸 IBKR、不開 socket、不讀 secret、不做 IO、
//! 無牆鐘依賴（時間戳 fixture 為任意非零占位,校驗只要求非零）。

use openclaw_types::{
    is_nonnegative_decimal_string, is_positive_decimal_string, is_signed_decimal_string, AssetLane,
    Broker, IbkrAccountSummaryRowBlocker, IbkrAccountSummaryRowV1, IbkrAccountSummaryTagV1,
    StockEtfCurrency, IBKR_ACCOUNT_SUMMARY_ROW_CONTRACT_ID,
    IBKR_ACCOUNT_SUMMARY_WIRE_TAG_WHITELIST,
};

#[test]
fn default_row_is_fail_closed() {
    use IbkrAccountSummaryRowBlocker as B;

    let verdict = IbkrAccountSummaryRowV1::default().validate();
    assert!(!verdict.accepted, "default 必須 fail-closed 拒");
    for expected in [
        B::ContractIdMismatch,
        B::SourceVersionMismatch,
        B::WrongAssetLane,
        B::WrongBroker,
        B::AccountIdMissing,
        B::TagUnknownDenied,
        B::ValueDecimalInvalid,
        B::CurrencyDenied,
        B::CapturedAtMissing,
        B::SnapshotSeqMissing,
    ] {
        assert!(
            verdict.blockers.contains(&expected),
            "缺 blocker {expected:?}"
        );
    }
}

#[test]
fn accepted_fixture_validates() {
    let row = IbkrAccountSummaryRowV1::accepted_fixture();
    let verdict = row.validate();
    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(row.contract_id, IBKR_ACCOUNT_SUMMARY_ROW_CONTRACT_ID);
    assert_eq!(row.source_version, 1);
    assert_eq!(row.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(row.broker, Broker::Ibkr);
    assert_eq!(row.currency, StockEtfCurrency::Usd);
    assert!(!row.order_routed);
    assert!(!row.secret_content_serialized);
}

#[test]
fn wire_tag_whitelist_round_trips_and_unknown_is_denied() {
    // 白名單全集:classify → 非 UnknownDenied,且 as_wire_tag 精確 round-trip。
    for wire in IBKR_ACCOUNT_SUMMARY_WIRE_TAG_WHITELIST {
        let tag = IbkrAccountSummaryTagV1::classify_wire_tag(wire);
        assert_ne!(
            tag,
            IbkrAccountSummaryTagV1::UnknownDenied,
            "白名單 tag {wire} 不得判 UnknownDenied"
        );
        assert_eq!(tag.as_wire_tag(), Some(wire), "round-trip 失敗: {wire}");
    }
    // 表外/大小寫變體/空字串 → 一律 UnknownDenied(fail-closed)。
    for bad in [
        "Cushion",
        "netliquidation",
        "NETLIQUIDATION",
        "NetLiquidation ",
        "",
        "TotalCash",
        "Leverage-S",
    ] {
        assert_eq!(
            IbkrAccountSummaryTagV1::classify_wire_tag(bad),
            IbkrAccountSummaryTagV1::UnknownDenied,
            "表外 tag {bad:?} 必須 UnknownDenied"
        );
    }
    // UnknownDenied 無 wire 對應。
    assert_eq!(IbkrAccountSummaryTagV1::UnknownDenied.as_wire_tag(), None);
    // 契約 default = fail-closed 未知拒。
    assert_eq!(
        IbkrAccountSummaryTagV1::default(),
        IbkrAccountSummaryTagV1::UnknownDenied
    );
}

#[test]
fn every_non_unknown_variant_wire_tag_is_in_whitelist_const() {
    use IbkrAccountSummaryTagV1 as Tag;

    // F4 反向斷言:每個非 UnknownDenied 枚舉變體的 wire tag ∈ WHITELIST const,
    // 且 classify(as_wire) 恆等回自身——枚舉與 const 表雙向鎖死,單側漂移即紅。
    let all_non_unknown = [
        Tag::NetLiquidation,
        Tag::TotalCashValue,
        Tag::SettledCash,
        Tag::BuyingPower,
        Tag::AvailableFunds,
        Tag::ExcessLiquidity,
        Tag::GrossPositionValue,
        Tag::AccruedCash,
        Tag::EquityWithLoanValue,
    ];
    for tag in all_non_unknown {
        let wire = tag.as_wire_tag().expect("非 Unknown 變體必有 wire 對應");
        assert!(
            IBKR_ACCOUNT_SUMMARY_WIRE_TAG_WHITELIST.contains(&wire),
            "變體 {tag:?} 的 wire tag {wire:?} 不在 WHITELIST const"
        );
        assert_eq!(IbkrAccountSummaryTagV1::classify_wire_tag(wire), tag);
    }
    // 基數鎖:const 表長度 = 非 Unknown 變體數(白名單無孤兒/無缺席)。
    assert_eq!(
        IBKR_ACCOUNT_SUMMARY_WIRE_TAG_WHITELIST.len(),
        all_non_unknown.len()
    );
}

#[test]
fn per_tag_sign_discipline_partitions_whitelist() {
    use IbkrAccountSummaryTagV1 as Tag;

    // F3 符號紀律表:結構性非負二 tag + fail-closed 的 UnknownDenied
    // （W5-S2 更正:AvailableFunds 移出非負列,IB DIVERGENT #5）。
    for tag in [
        Tag::GrossPositionValue,
        Tag::BuyingPower,
        Tag::UnknownDenied,
    ] {
        assert!(tag.is_structurally_non_negative(), "{tag:?} 應為結構性非負");
    }
    // 可負(簽名保真)七 tag:AvailableFunds=EWL−InitialMargin 恒 ≤ ExcessLiquidity,
    // 必先於它轉負（出典 ibkrguides available-for-trading）。
    for tag in [
        Tag::NetLiquidation,
        Tag::TotalCashValue,
        Tag::SettledCash,
        Tag::AccruedCash,
        Tag::ExcessLiquidity,
        Tag::EquityWithLoanValue,
        Tag::AvailableFunds,
    ] {
        assert!(!tag.is_structurally_non_negative(), "{tag:?} 應可負保真");
    }
}

#[test]
fn negative_value_on_structurally_non_negative_tag_is_rejected() {
    use IbkrAccountSummaryTagV1 as Tag;

    // 結構性非負 tag 帶負值 → 專屬 blocker(消化層錯誤,fail-closed)。
    // W5-S2 更正:AvailableFunds 不在此列(可負保真,見下方接納斷言)。
    for tag in [Tag::GrossPositionValue, Tag::BuyingPower] {
        let row = IbkrAccountSummaryRowV1 {
            tag,
            value_decimal: "-0.01".to_string(),
            ..IbkrAccountSummaryRowV1::accepted_fixture()
        };
        let verdict = row.validate();
        assert!(!verdict.accepted, "{tag:?} 負值應被拒");
        assert_eq!(
            verdict.blockers,
            vec![IbkrAccountSummaryRowBlocker::NegativeValueForNonNegativeTag]
        );
    }
    // 同 tag 零值/正值合法(邊界:紀律只拒負,不拒零)。
    for value in ["0", "12500.00"] {
        let row = IbkrAccountSummaryRowV1 {
            tag: Tag::BuyingPower,
            value_decimal: value.to_string(),
            ..IbkrAccountSummaryRowV1::accepted_fixture()
        };
        assert!(row.validate().accepted, "BuyingPower {value:?} 應合法");
    }
    // 非法 decimal 優先報 ValueDecimalInvalid,不重複報符號紀律 blocker。
    let malformed = IbkrAccountSummaryRowV1 {
        tag: Tag::BuyingPower,
        value_decimal: "-1e5".to_string(),
        ..IbkrAccountSummaryRowV1::accepted_fixture()
    };
    assert_eq!(
        malformed.validate().blockers,
        vec![IbkrAccountSummaryRowBlocker::ValueDecimalInvalid]
    );
}

#[test]
fn unknown_tag_row_is_rejected() {
    let row = IbkrAccountSummaryRowV1 {
        tag: IbkrAccountSummaryTagV1::UnknownDenied,
        ..IbkrAccountSummaryRowV1::accepted_fixture()
    };
    let verdict = row.validate();
    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![IbkrAccountSummaryRowBlocker::TagUnknownDenied]
    );
}

#[test]
fn signed_decimal_helper_accepts_fixed_point_and_rejects_float_noise() {
    // 合法:簽名定點(含負值/零/小數)。
    for ok in ["0", "1", "100000.25", "-3.5", "-0.01", "0.0", "42."] {
        assert!(is_signed_decimal_string(ok), "{ok:?} 應合法");
    }
    // 非法:空/正號/空白/指數/NaN/雙點/非數字。
    for bad in [
        "", "+5", " 5", "5 ", "1e5", "NaN", "inf", "1.2.3", "--1", "-", ".", "0x10", "1_000",
    ] {
        assert!(!is_signed_decimal_string(bad), "{bad:?} 應非法");
    }
    // 非負/嚴格正變體。
    assert!(is_nonnegative_decimal_string("0"));
    assert!(!is_nonnegative_decimal_string("-1"));
    assert!(is_positive_decimal_string("0.5"));
    assert!(!is_positive_decimal_string("0"));
    assert!(!is_positive_decimal_string("0.00"));
}

#[test]
fn negative_account_value_is_honest_and_accepted() {
    // AccruedCash / AvailableFunds 等帳戶值可為負——簽名保真,不拒。
    // AvailableFunds=EWL−InitialMargin 恒先於 ExcessLiquidity 轉負（W5-S2 更正,
    // IB DIVERGENT #5;出典 ibkrguides available-for-trading）——負值=合法承載。
    for tag in [
        IbkrAccountSummaryTagV1::AccruedCash,
        IbkrAccountSummaryTagV1::AvailableFunds,
    ] {
        let row = IbkrAccountSummaryRowV1 {
            tag,
            value_decimal: "-12.75".to_string(),
            ..IbkrAccountSummaryRowV1::accepted_fixture()
        };
        assert!(row.validate().accepted, "{tag:?} 負值應為合法簽名承載");
    }
}

#[test]
fn float_noise_value_and_zero_clock_are_rejected() {
    use IbkrAccountSummaryRowBlocker as B;

    let row = IbkrAccountSummaryRowV1 {
        value_decimal: "1e308".to_string(),
        captured_at_ms: 0,
        snapshot_seq: 0,
        ..IbkrAccountSummaryRowV1::accepted_fixture()
    };
    let verdict = row.validate();
    assert!(!verdict.accepted);
    for expected in [
        B::ValueDecimalInvalid,
        B::CapturedAtMissing,
        B::SnapshotSeqMissing,
    ] {
        assert!(verdict.blockers.contains(&expected), "缺 {expected:?}");
    }
}

#[test]
fn wrong_lane_currency_and_boundary_flags_are_rejected() {
    use IbkrAccountSummaryRowBlocker as B;

    let row = IbkrAccountSummaryRowV1 {
        asset_lane: AssetLane::CryptoPerp,
        broker: Broker::Bybit,
        currency: StockEtfCurrency::UnknownDenied,
        order_routed: true,
        secret_content_serialized: true,
        ..IbkrAccountSummaryRowV1::accepted_fixture()
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
fn serde_roundtrip_snake_case_stable() {
    let row = IbkrAccountSummaryRowV1::accepted_fixture();
    let json = serde_json::to_value(&row).unwrap();
    assert_eq!(json["contract_id"], "ibkr_account_summary_row_v1");
    assert_eq!(json["tag"], "net_liquidation");
    assert_eq!(json["currency"], "usd");
    // money 為字串保真,非 JSON number。
    assert!(json["value_decimal"].is_string());
    let back: IbkrAccountSummaryRowV1 = serde_json::from_value(json).unwrap();
    assert_eq!(back, row);
}
