//! W6-S1 instrument identity row 契約 acceptance 測試（source-only）。
//!
//! 只驗型別/校驗/serde/preimage 形態:不接觸 IBKR、不開 socket、不讀 secret、不做 IO、
//! 無牆鐘依賴（`validate(now_ms)` 全用相對注入時鐘,fixture 禁硬編當前日期）。

use openclaw_types::{
    is_whitelisted_instrument_exchange, is_whitelisted_primary_exchange, AssetLane, Broker,
    IbkrInstrumentIdentityRowBlocker, IbkrInstrumentIdentityRowV1, IbkrSecTypeV1, IbkrStockTypeV1,
    StockEtfCurrency, IBKR_INSTRUMENT_IDENTITY_ROW_CONTRACT_ID,
    IBKR_INSTRUMENT_PRIMARY_EXCHANGE_WHITELIST,
};

/// fixture captured_at 的注入校驗時鐘（≥ captured;相對時鐘,無牆鐘依賴）。
const NOW_MS: u64 = 123_456_789;

#[test]
fn default_row_is_fail_closed() {
    use IbkrInstrumentIdentityRowBlocker as B;

    let verdict = IbkrInstrumentIdentityRowV1::default().validate(NOW_MS);
    assert!(!verdict.accepted, "default 必須 fail-closed 拒");
    for expected in [
        B::ContractIdMismatch,
        B::SourceVersionMismatch,
        B::WrongAssetLane,
        B::WrongBroker,
        B::ConIdInvalid,
        B::SymbolInvalid,
        B::SecTypeUnknownDenied,
        B::ExchangeVenueDenied,
        B::PrimaryExchangeVenueDenied,
        B::CurrencyDenied,
        B::LocalSymbolMissing,
        B::TradingClassMissing,
        B::MarketNameMissing,
        B::MinTickInvalid,
        B::ValidExchangesMissing,
        B::PriceMagnifierInvalid,
        B::TimeZoneIdMissing,
        B::TradingHoursMissing,
        B::LiquidHoursMissing,
        B::StockTypeUnknownDenied,
        B::IdentityHashInvalid,
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
    let row = IbkrInstrumentIdentityRowV1::accepted_fixture();
    let verdict = row.validate(NOW_MS);
    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(row.contract_id, IBKR_INSTRUMENT_IDENTITY_ROW_CONTRACT_ID);
    assert_eq!(row.source_version, 1);
    assert_eq!(row.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(row.broker, Broker::Ibkr);
    assert_eq!(row.sec_type, IbkrSecTypeV1::Stk);
    assert_eq!(row.currency, StockEtfCurrency::Usd);
    assert_eq!(row.stock_type, IbkrStockTypeV1::Etf);
    assert!(!row.order_routed);
    assert!(!row.secret_content_serialized);
}

#[test]
fn stock_type_whitelist_is_closed_and_fail_closed() {
    // 白名單:ETF / COMMON 兩值精確匹配。
    assert_eq!(
        IbkrStockTypeV1::classify_wire_stock_type("ETF"),
        IbkrStockTypeV1::Etf
    );
    assert_eq!(
        IbkrStockTypeV1::classify_wire_stock_type("COMMON"),
        IbkrStockTypeV1::CommonStock
    );
    // 表外(PREFERRED/ADR/大小寫變體/空)一律 UnknownDenied。
    for bad in ["PREFERRED", "ADR", "etf", "Common", "STOCK", ""] {
        assert_eq!(
            IbkrStockTypeV1::classify_wire_stock_type(bad),
            IbkrStockTypeV1::UnknownDenied,
            "stockType {bad:?} 必須 UnknownDenied"
        );
    }
    assert_eq!(IbkrStockTypeV1::UnknownDenied.as_wire_stock_type(), None);
    assert_eq!(IbkrStockTypeV1::default(), IbkrStockTypeV1::UnknownDenied);
    // 反向窮舉斷言:每個非 UnknownDenied 變體 classify(as_wire) 恆等回自身。
    for st in [IbkrStockTypeV1::Etf, IbkrStockTypeV1::CommonStock] {
        let wire = st
            .as_wire_stock_type()
            .expect("非 Unknown 變體必有 wire 對應");
        assert_eq!(IbkrStockTypeV1::classify_wire_stock_type(wire), st);
    }
}

#[test]
fn venue_whitelist_is_closed_and_primary_excludes_smart() {
    // 反向窮舉:primaryExchange 白名單全集雙向成立（primary 亦是合法 exchange）。
    for venue in IBKR_INSTRUMENT_PRIMARY_EXCHANGE_WHITELIST {
        assert!(is_whitelisted_primary_exchange(venue), "缺白名單 {venue}");
        assert!(is_whitelisted_instrument_exchange(venue));
    }
    // SMART 僅屬 exchange 域（路由聚合層),不得作 primaryExchange。
    assert!(is_whitelisted_instrument_exchange("SMART"));
    assert!(!is_whitelisted_primary_exchange("SMART"));
    // 表外 venue(外盤/大小寫變體/空)雙域皆拒。
    for bad in ["LSE", "TSE", "smart", "nyse", "PINK", ""] {
        assert!(!is_whitelisted_instrument_exchange(bad), "{bad:?} 應拒");
        assert!(!is_whitelisted_primary_exchange(bad), "{bad:?} 應拒");
    }
}

#[test]
fn rejection_matrix_unknown_sec_type_venue_currency_stock_type() {
    use IbkrInstrumentIdentityRowBlocker as B;

    // 單欄劣化 → 恰好對應 blocker(拒絕矩陣逐欄面)。
    let cases: Vec<(IbkrInstrumentIdentityRowV1, B)> = vec![
        (
            IbkrInstrumentIdentityRowV1 {
                sec_type: IbkrSecTypeV1::UnknownDenied,
                ..IbkrInstrumentIdentityRowV1::accepted_fixture()
            },
            B::SecTypeUnknownDenied,
        ),
        (
            IbkrInstrumentIdentityRowV1 {
                exchange: "LSE".to_string(),
                ..IbkrInstrumentIdentityRowV1::accepted_fixture()
            },
            B::ExchangeVenueDenied,
        ),
        (
            IbkrInstrumentIdentityRowV1 {
                primary_exchange: "SMART".to_string(),
                ..IbkrInstrumentIdentityRowV1::accepted_fixture()
            },
            B::PrimaryExchangeVenueDenied,
        ),
        (
            IbkrInstrumentIdentityRowV1 {
                currency: StockEtfCurrency::UnknownDenied,
                ..IbkrInstrumentIdentityRowV1::accepted_fixture()
            },
            B::CurrencyDenied,
        ),
        (
            IbkrInstrumentIdentityRowV1 {
                stock_type: IbkrStockTypeV1::UnknownDenied,
                ..IbkrInstrumentIdentityRowV1::accepted_fixture()
            },
            B::StockTypeUnknownDenied,
        ),
        (
            IbkrInstrumentIdentityRowV1 {
                con_id: 0,
                ..IbkrInstrumentIdentityRowV1::accepted_fixture()
            },
            B::ConIdInvalid,
        ),
        (
            IbkrInstrumentIdentityRowV1 {
                symbol: "spy lower".to_string(),
                ..IbkrInstrumentIdentityRowV1::accepted_fixture()
            },
            B::SymbolInvalid,
        ),
        (
            IbkrInstrumentIdentityRowV1 {
                price_magnifier: 0,
                ..IbkrInstrumentIdentityRowV1::accepted_fixture()
            },
            B::PriceMagnifierInvalid,
        ),
        (
            IbkrInstrumentIdentityRowV1 {
                identity_hash: "not-a-hash".to_string(),
                ..IbkrInstrumentIdentityRowV1::accepted_fixture()
            },
            B::IdentityHashInvalid,
        ),
    ];
    for (row, expected) in cases {
        let verdict = row.validate(NOW_MS);
        assert!(!verdict.accepted);
        assert_eq!(
            verdict.blockers,
            vec![expected],
            "單欄劣化應恰觸 {expected:?}"
        );
    }
}

#[test]
fn min_tick_must_be_strictly_positive_decimal_string() {
    use IbkrInstrumentIdentityRowBlocker as B;

    // 合法嚴格正定點字串。
    for ok in ["0.01", "0.0001", "1", "12.5"] {
        let row = IbkrInstrumentIdentityRowV1 {
            min_tick_decimal: ok.to_string(),
            ..IbkrInstrumentIdentityRowV1::accepted_fixture()
        };
        assert!(row.validate(NOW_MS).accepted, "minTick {ok} 應合法");
    }
    // 零/負/空/指數記法/浮點噪音 → MinTickInvalid(0 刻度=下游價格對齊語義崩壞)。
    for bad in ["0", "0.0", "-0.01", "", "1e-2", "NaN"] {
        let row = IbkrInstrumentIdentityRowV1 {
            min_tick_decimal: bad.to_string(),
            ..IbkrInstrumentIdentityRowV1::accepted_fixture()
        };
        let verdict = row.validate(NOW_MS);
        assert!(!verdict.accepted, "minTick {bad:?} 應拒");
        assert_eq!(verdict.blockers, vec![B::MinTickInvalid]);
    }
}

#[test]
fn raw_preserve_fields_reject_empty_but_carry_verbatim() {
    use IbkrInstrumentIdentityRowBlocker as B;

    // 原字串保真欄:非空義務(識別載體不可缺),內容不賦語義——legacy 時區名/雙 grammar
    // hours 原樣通過(解析歸 W6-S2,禁默認 America/New_York)。
    let legacy = IbkrInstrumentIdentityRowV1 {
        time_zone_id: "EST5EDT".to_string(),
        trading_hours: "20260102:0400-20260102:2000;20260103:CLOSED".to_string(),
        ..IbkrInstrumentIdentityRowV1::accepted_fixture()
    };
    assert!(legacy.validate(NOW_MS).accepted, "legacy 時區名應保真通過");

    let row = IbkrInstrumentIdentityRowV1 {
        local_symbol: String::new(),
        trading_class: "  ".to_string(),
        market_name: String::new(),
        valid_exchanges: String::new(),
        time_zone_id: String::new(),
        trading_hours: String::new(),
        liquid_hours: String::new(),
        ..IbkrInstrumentIdentityRowV1::accepted_fixture()
    };
    let verdict = row.validate(NOW_MS);
    assert!(!verdict.accepted);
    for expected in [
        B::LocalSymbolMissing,
        B::TradingClassMissing,
        B::MarketNameMissing,
        B::ValidExchangesMissing,
        B::TimeZoneIdMissing,
        B::TradingHoursMissing,
        B::LiquidHoursMissing,
    ] {
        assert!(verdict.blockers.contains(&expected), "缺 {expected:?}");
    }
    // multiplier/mdSizeMultiplier/orderTypes/longName 為保真欄無非空義務(STK multiplier 慣例空)。
    let sparse = IbkrInstrumentIdentityRowV1 {
        multiplier: String::new(),
        md_size_multiplier: String::new(),
        order_types: String::new(),
        long_name: String::new(),
        ..IbkrInstrumentIdentityRowV1::accepted_fixture()
    };
    assert!(sparse.validate(NOW_MS).accepted);
}

#[test]
fn captured_at_injected_clock_discipline() {
    use IbkrInstrumentIdentityRowBlocker as B;

    // 零時間戳 → CapturedAtMissing。
    let zero = IbkrInstrumentIdentityRowV1 {
        captured_at_ms: 0,
        ..IbkrInstrumentIdentityRowV1::accepted_fixture()
    };
    assert!(zero
        .validate(NOW_MS)
        .blockers
        .contains(&B::CapturedAtMissing));
    // 未來時間戳(相對注入時鐘) → CapturedAtInFuture(PIT 紀律:身份快照不可來自未來)。
    let future = IbkrInstrumentIdentityRowV1 {
        captured_at_ms: NOW_MS + 1,
        ..IbkrInstrumentIdentityRowV1::accepted_fixture()
    };
    let verdict = future.validate(NOW_MS);
    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![B::CapturedAtInFuture]);
    // 恰等於注入時鐘 → 合法。
    let at_now = IbkrInstrumentIdentityRowV1 {
        captured_at_ms: NOW_MS,
        ..IbkrInstrumentIdentityRowV1::accepted_fixture()
    };
    assert!(at_now.validate(NOW_MS).accepted);
}

#[test]
fn boundary_flags_are_rejected() {
    use IbkrInstrumentIdentityRowBlocker as B;

    let row = IbkrInstrumentIdentityRowV1 {
        order_routed: true,
        secret_content_serialized: true,
        ..IbkrInstrumentIdentityRowV1::accepted_fixture()
    };
    let verdict = row.validate(NOW_MS);
    assert!(!verdict.accepted);
    for expected in [B::OrderRouted, B::SecretContentSerialized] {
        assert!(verdict.blockers.contains(&expected), "缺 {expected:?}");
    }
}

#[test]
fn identity_hash_preimage_is_deterministic_and_identity_scoped() {
    let row = IbkrInstrumentIdentityRowV1::accepted_fixture();
    let p1 = row.identity_hash_preimage();
    let p2 = row.identity_hash_preimage();
    // 同 row 同 preimage(PIT 可重建的契約錨;雜湊計算歸消化層)。
    assert_eq!(p1, p2);
    assert!(p1.starts_with(IBKR_INSTRUMENT_IDENTITY_ROW_CONTRACT_ID));
    assert!(p1.contains("756733"));
    assert!(p1.contains("SPY"));
    assert!(p1.contains("ETF"));

    // 身份欄變 → preimage 變。
    let other = IbkrInstrumentIdentityRowV1 {
        con_id: 8314,
        ..IbkrInstrumentIdentityRowV1::accepted_fixture()
    };
    assert_ne!(p1, other.identity_hash_preimage());

    // 會話性/展示/市場參數欄變 → preimage 不變(身份不因交易參數漂移)。
    let session_varied = IbkrInstrumentIdentityRowV1 {
        trading_hours: "20260105:0400-20260105:2000".to_string(),
        liquid_hours: "20260105:0930-20260105:1600".to_string(),
        long_name: "RENAMED FUND".to_string(),
        min_tick_decimal: "0.05".to_string(),
        captured_at_ms: NOW_MS,
        snapshot_seq: 42,
        ..IbkrInstrumentIdentityRowV1::accepted_fixture()
    };
    assert_eq!(p1, session_varied.identity_hash_preimage());
}

#[test]
fn serde_roundtrip_snake_case_stable() {
    let row = IbkrInstrumentIdentityRowV1::accepted_fixture();
    let json = serde_json::to_value(&row).unwrap();
    assert_eq!(json["contract_id"], "ibkr_instrument_identity_row_v1");
    assert_eq!(json["sec_type"], "stk");
    assert_eq!(json["currency"], "usd");
    assert_eq!(json["stock_type"], "etf");
    // 刻度為字串保真,非 JSON number。
    assert!(json["min_tick_decimal"].is_string());
    let back: IbkrInstrumentIdentityRowV1 = serde_json::from_value(json).unwrap();
    assert_eq!(back, row);
}
