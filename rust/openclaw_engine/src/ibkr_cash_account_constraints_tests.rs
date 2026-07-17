//! W7-S2 cash 約束引擎測試（每 gate 正/負;**注入時鐘 + 注入 config**,禁 wall-clock 日期腐化
//! time-bomb——所有時刻由固定日期字面量經 chrono-tz 建構,非 `now()`;規則值標 illustrative)。
//! Deletion test 精神:各 gate 的負向測試證明「引擎在位時主動拒違規」(GFV/no-short/over-buy/
//! settled-funds),即引擎刪除 → 違規放行的反證。

use std::collections::BTreeMap;

use chrono::TimeZone;
use chrono_tz::Tz;

use openclaw_types::{
    AssetLane, Broker, BrokerOperation, IbkrCalendarHoursKindV1, IbkrCalendarSessionKindV1,
    IbkrTradingCalendarSessionV1, IbkrTradingCalendarV1, StockEtfOrderSide, StockEtfPaperOrderType,
    StockEtfPaperTimeInForce, IBKR_TRADING_CALENDAR_CONTRACT_ID,
};

use crate::ibkr_tws_account_data::SnapshotStaleness;

use super::*;

// ---- 固定時鐘 / 日曆 fixture（全由日期字面量建構;非牆鐘)----

const TZ_NAME: &str = "America/New_York";

fn tz() -> Tz {
    TZ_NAME.parse().unwrap()
}

/// 固定注入「現在」:2026-03-10（週二,DST 已於 03-08 生效)10:30 ET,盤中。
fn now_rth() -> u64 {
    tz().with_ymd_and_hms(2026, 3, 10, 10, 30, 0)
        .unwrap()
        .timestamp_millis() as u64
}

/// 固定注入「現在」:2026-03-10 08:00 ET,盤前(RTH 外)。
fn now_premarket() -> u64 {
    tz().with_ymd_and_hms(2026, 3, 10, 8, 0, 0)
        .unwrap()
        .timestamp_millis() as u64
}

/// 建一個 09:30-16:00 ET 的 `Open` session。
fn open_session(y: i32, m: u32, d: u32, date_str: &str) -> IbkrTradingCalendarSessionV1 {
    let open = tz()
        .with_ymd_and_hms(y, m, d, 9, 30, 0)
        .unwrap()
        .timestamp_millis() as u64;
    let close = tz()
        .with_ymd_and_hms(y, m, d, 16, 0, 0)
        .unwrap()
        .timestamp_millis() as u64;
    IbkrTradingCalendarSessionV1 {
        date: date_str.to_string(),
        kind: IbkrCalendarSessionKindV1::Open,
        open_ms: open,
        close_ms: close,
    }
}

/// 日曆:03-10（今日)/ 03-11 / 03-12 三個交易日（T+1 結算 → 03-11)。
fn calendar_with(sessions: Vec<IbkrTradingCalendarSessionV1>) -> IbkrTradingCalendarV1 {
    IbkrTradingCalendarV1 {
        contract_id: IBKR_TRADING_CALENDAR_CONTRACT_ID.to_string(),
        source_version: 1,
        asset_lane: AssetLane::StockEtfCash,
        broker: Broker::Ibkr,
        con_id: 42,
        symbol: "AAPL".to_string(),
        hours_kind: IbkrCalendarHoursKindV1::Rth,
        time_zone_iana: TZ_NAME.to_string(),
        sessions,
        calendar_hash: String::new(),
        order_routed: false,
        secret_content_serialized: false,
    }
}

fn full_calendar() -> IbkrTradingCalendarV1 {
    calendar_with(vec![
        open_session(2026, 3, 10, "20260310"),
        open_session(2026, 3, 11, "20260311"),
        open_session(2026, 3, 12, "20260312"),
    ])
}

fn fresh_market(price: &str) -> MarketPreTradeState {
    MarketPreTradeState {
        halted: false,
        luld_limit_state: false,
        data_available: true,
        reference_price_decimal: price.to_string(),
    }
}

/// 基線 account:settled 100000,無 unsettled,long AAPL 100,Fresh。
fn base_account() -> CashAccountState {
    let mut long = BTreeMap::new();
    long.insert("AAPL".to_string(), "100".to_string());
    CashAccountState {
        account_id: "DU111".to_string(),
        settled_cash_decimal: "100000".to_string(),
        unsettled_tranches: Vec::new(),
        unsettled_funded_buys: BTreeMap::new(),
        long_positions: long,
        staleness: SnapshotStaleness::Fresh { as_of_ms: 1 },
    }
}

/// 基線 BUY intent:AAPL LMT DAY,qty 10 @ 150,盤中。
fn base_buy() -> CashOrderIntent {
    CashOrderIntent {
        account_id: "DU111".to_string(),
        symbol: "AAPL".to_string(),
        operation: BrokerOperation::PaperOrderSubmit,
        side: Some(StockEtfOrderSide::Buy),
        order_type: Some(StockEtfPaperOrderType::Limit),
        time_in_force: Some(StockEtfPaperTimeInForce::Day),
        quantity_decimal: "10".to_string(),
        limit_price_decimal: "150".to_string(),
        market: fresh_market("150"),
    }
}

fn base_sell() -> CashOrderIntent {
    CashOrderIntent {
        side: Some(StockEtfOrderSide::Sell),
        quantity_decimal: "50".to_string(),
        ..base_buy()
    }
}

fn rules() -> CashAccountRules {
    CashAccountRules::illustrative_v1()
}

// ===========================================================================
// gate #1 settled-funds 台帳（T+1)
// ===========================================================================

#[test]
fn buy_settled_ok() {
    let ok = evaluate(
        &base_buy(),
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap();
    assert_eq!(ok.side, StockEtfOrderSide::Buy);
    assert_eq!(ok.estimated_cost_decimal, "1500");
    assert_eq!(ok.settled_funds_remaining_decimal, "98500");
    // T+1 結算 → 今日(03-10)之後第 1 個交易日 = 03-11。
    assert_eq!(ok.projected_settlement_date, "20260311");
}

#[test]
fn buy_insufficient_settled() {
    let mut acct = base_account();
    acct.settled_cash_decimal = "1000".to_string(); // 成本 1500 > 1000
    let err = evaluate(&base_buy(), &acct, &rules(), &full_calendar(), now_rth()).unwrap_err();
    assert!(matches!(
        err,
        CashConstraintViolation::SettledFundsInsufficient { .. }
    ));
}

#[test]
fn buy_unsettled_tranche_not_counted() {
    let mut acct = base_account();
    acct.settled_cash_decimal = "1000".to_string();
    // 未成熟 tranche(結算 03-12 > 今日) → 不併入可用 → 仍不足。
    acct.unsettled_tranches = vec![CashTranche {
        amount_decimal: "5000".to_string(),
        settlement_date: "20260312".to_string(),
    }];
    let err = evaluate(&base_buy(), &acct, &rules(), &full_calendar(), now_rth()).unwrap_err();
    assert!(matches!(
        err,
        CashConstraintViolation::SettledFundsInsufficient { .. }
    ));
}

#[test]
fn buy_matured_tranche_counted() {
    let mut acct = base_account();
    acct.settled_cash_decimal = "1000".to_string();
    // 已成熟 tranche(結算 03-10 == 今日) → 併入可用(1000+5000=6000 ≥ 1500)。
    acct.unsettled_tranches = vec![CashTranche {
        amount_decimal: "5000".to_string(),
        settlement_date: "20260310".to_string(),
    }];
    let ok = evaluate(&base_buy(), &acct, &rules(), &full_calendar(), now_rth()).unwrap();
    assert_eq!(ok.settled_funds_remaining_decimal, "4500");
}

#[test]
fn buy_market_order_uses_buffered_reference_price() {
    // MKT 成本 = qty × ref × (1 + 100bps) = 10 × 150 × 1.01 = 1515（保守上浮,修 MED-1 fail-open)。
    let intent = CashOrderIntent {
        order_type: Some(StockEtfPaperOrderType::Market),
        limit_price_decimal: String::new(),
        market: fresh_market("150"),
        ..base_buy()
    };
    let ok = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap();
    assert_eq!(ok.estimated_cost_decimal, "1515");
    assert_eq!(ok.settled_funds_remaining_decimal, "98485");
}

#[test]
fn buy_market_buffer_causes_fail_closed_over_settled() {
    // settled=1500:無 buffer 剛好夠(10×150=1500),有 buffer(cost 1515)→ 保守拒(fail-closed)。
    let mut acct = base_account();
    acct.settled_cash_decimal = "1500".to_string();
    let intent = CashOrderIntent {
        order_type: Some(StockEtfPaperOrderType::Market),
        limit_price_decimal: String::new(),
        market: fresh_market("150"),
        ..base_buy()
    };
    let err = evaluate(&intent, &acct, &rules(), &full_calendar(), now_rth()).unwrap_err();
    assert!(matches!(
        err,
        CashConstraintViolation::SettledFundsInsufficient { .. }
    ));
    // 同單、buffer=0 → 無上浮(cost 1500 ≤ 1500)→ 放行(證 buffer 為 fail-closed 的 load-bearing 差異)。
    let mut r = rules();
    r.marketable_buffer_bps = 0;
    assert!(evaluate(&intent, &acct, &r, &full_calendar(), now_rth()).is_ok());
}

#[test]
fn buy_settlement_uncomputable_when_no_future_trading_day() {
    // 日曆只有今日 → 無 T+1 交易日 → BUY fail-closed。
    let cal = calendar_with(vec![open_session(2026, 3, 10, "20260310")]);
    let err = evaluate(&base_buy(), &base_account(), &rules(), &cal, now_rth()).unwrap_err();
    assert_eq!(err, CashConstraintViolation::SettlementDateUncomputable);
}

// ===========================================================================
// gate #2 GFV / free-riding
// ===========================================================================

#[test]
fn sell_unsettled_funded_before_funding_settles_denied() {
    let mut acct = base_account();
    // AAPL 有以未結算資金支付的買入(資金結算 03-12 > 今日) → 資金結算前賣出 = free-riding(真 GFV)。
    acct.unsettled_funded_buys.insert(
        "AAPL".to_string(),
        UnsettledFundedBuyLot {
            quantity_decimal: "50".to_string(),
            funding_settlement_date: "20260312".to_string(),
        },
    );
    let err = evaluate(&base_sell(), &acct, &rules(), &full_calendar(), now_rth()).unwrap_err();
    assert!(matches!(
        err,
        CashConstraintViolation::GfvFreeRidingViolation { .. }
    ));
}

#[test]
fn sell_ok_when_funding_already_settled() {
    let mut acct = base_account();
    // 支付資金已結算(結算 03-10 ≤ 今日) → 非 free-riding。
    acct.unsettled_funded_buys.insert(
        "AAPL".to_string(),
        UnsettledFundedBuyLot {
            quantity_decimal: "50".to_string(),
            funding_settlement_date: "20260310".to_string(),
        },
    );
    let ok = evaluate(&base_sell(), &acct, &rules(), &full_calendar(), now_rth()).unwrap();
    assert_eq!(ok.side, StockEtfOrderSide::Sell);
}

#[test]
fn sell_settled_funded_before_t1_not_misfired() {
    // E2 LOW-1 修:以 settled cash 全額買入的持倉(不入 unsettled_funded_buys),T+1 結算前的正當賣出
    // **不應被 GFV 誤殺**(官方明文不算 GFV)。unsettled_funded_buys 空 → 放行。
    let acct = base_account(); // unsettled_funded_buys 空
    let ok = evaluate(&base_sell(), &acct, &rules(), &full_calendar(), now_rth()).unwrap();
    assert_eq!(ok.side, StockEtfOrderSide::Sell);
}

// ===========================================================================
// gate #3 no-short（硬邊界)
// ===========================================================================

#[test]
fn sell_exceeding_long_denied() {
    let intent = CashOrderIntent {
        quantity_decimal: "200".to_string(), // > long 100
        ..base_sell()
    };
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert!(matches!(
        err,
        CashConstraintViolation::ShortSaleDenied { .. }
    ));
}

#[test]
fn sell_without_position_denied() {
    let mut acct = base_account();
    acct.long_positions.clear(); // 無 AAPL 倉位 → long=0
    let err = evaluate(&base_sell(), &acct, &rules(), &full_calendar(), now_rth()).unwrap_err();
    assert!(matches!(
        err,
        CashConstraintViolation::ShortSaleDenied { .. }
    ));
}

#[test]
fn sell_within_long_ok() {
    let ok = evaluate(
        &base_sell(),
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap();
    assert_eq!(ok.side, StockEtfOrderSide::Sell);
}

// ===========================================================================
// gate #4 RTH-only
// ===========================================================================

#[test]
fn order_inside_rth_ok() {
    // base_buy @ now_rth 已於 buy_settled_ok 證;此處顯式再證 RTH 命中不擋。
    assert!(evaluate(
        &base_buy(),
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth()
    )
    .is_ok());
}

#[test]
fn order_premarket_denied() {
    let err = evaluate(
        &base_buy(),
        &base_account(),
        &rules(),
        &full_calendar(),
        now_premarket(),
    )
    .unwrap_err();
    assert_eq!(err, CashConstraintViolation::OutsideRegularTradingHours);
}

#[test]
fn order_on_closed_day_denied() {
    // 週六 03-14,日曆無此開市日 → RTH 外。
    let now_sat = tz()
        .with_ymd_and_hms(2026, 3, 14, 12, 0, 0)
        .unwrap()
        .timestamp_millis() as u64;
    let err = evaluate(
        &base_buy(),
        &base_account(),
        &rules(),
        &full_calendar(),
        now_sat,
    )
    .unwrap_err();
    assert_eq!(err, CashConstraintViolation::OutsideRegularTradingHours);
}

// ===========================================================================
// gate #5 order-type / TIF 白名單
// ===========================================================================

#[test]
fn gtc_denied_by_default() {
    let intent = CashOrderIntent {
        time_in_force: Some(StockEtfPaperTimeInForce::Gtc),
        ..base_buy()
    };
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert!(matches!(
        err,
        CashConstraintViolation::TimeInForceNotWhitelisted { .. }
    ));
}

#[test]
fn gtc_allowed_when_opt_in() {
    let intent = CashOrderIntent {
        time_in_force: Some(StockEtfPaperTimeInForce::Gtc),
        ..base_buy()
    };
    let mut r = rules();
    r.allow_gtc = true;
    assert!(evaluate(&intent, &base_account(), &r, &full_calendar(), now_rth()).is_ok());
}

// ===========================================================================
// gate #6 fractional
// ===========================================================================

#[test]
fn fractional_quantity_denied() {
    let intent = CashOrderIntent {
        quantity_decimal: "10.5".to_string(),
        ..base_buy()
    };
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert_eq!(err, CashConstraintViolation::FractionalQuantityDenied);
}

#[test]
fn fractional_quantity_allowed_when_opt_in() {
    let intent = CashOrderIntent {
        quantity_decimal: "10.5".to_string(),
        ..base_buy()
    };
    let mut r = rules();
    r.allow_fractional = true;
    let ok = evaluate(&intent, &base_account(), &r, &full_calendar(), now_rth()).unwrap();
    // 成本 = 10.5 × 150 = 1575。
    assert_eq!(ok.estimated_cost_decimal, "1575");
}

#[test]
fn zero_quantity_denied() {
    let intent = CashOrderIntent {
        quantity_decimal: "0".to_string(),
        ..base_buy()
    };
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert_eq!(err, CashConstraintViolation::NonPositiveQuantity);
}

#[test]
fn negative_quantity_denied() {
    let intent = CashOrderIntent {
        quantity_decimal: "-5".to_string(),
        ..base_buy()
    };
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert_eq!(err, CashConstraintViolation::NonPositiveQuantity);
}

// ===========================================================================
// gate #7 LULD / halt
// ===========================================================================

#[test]
fn halt_denied() {
    let mut intent = base_buy();
    intent.market.halted = true;
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert_eq!(err, CashConstraintViolation::TradingHalted);
}

#[test]
fn luld_limit_state_denied() {
    let mut intent = base_buy();
    intent.market.luld_limit_state = true;
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert_eq!(err, CashConstraintViolation::LuldBandBreach);
}

#[test]
fn luld_band_breach_on_marketable_limit_deviation() {
    // marketable BUY LMT 200 ≥ 參考 150(會即時觸市),偏離 33% > 帶寬 5% → fat-finger sanity 拒。
    let mut intent = base_buy();
    intent.limit_price_decimal = "200".to_string();
    intent.market = fresh_market("150");
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert_eq!(err, CashConstraintViolation::LuldBandBreach);
}

#[test]
fn dip_buy_resting_limit_far_below_market_not_luld() {
    // E2 NOTE-1 修:遠低於現價的 dip-buy 限價單(BUY LMT 100 < ref 150,非 marketable)**非 LULD 事件**,
    // 本地 band **不得誤殺**。成本 10×100=1000 ≤ 100000 → 放行。
    let mut intent = base_buy();
    intent.limit_price_decimal = "100".to_string();
    intent.market = fresh_market("150");
    let ok = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap();
    assert_eq!(ok.estimated_cost_decimal, "1000");
}

#[test]
fn sell_resting_limit_far_above_market_not_luld() {
    // 賣出掛單遠高於現價(SELL LMT 300 > ref 150,非 marketable)非 LULD → 不誤殺;no-short 50≤100 → 放行。
    let mut intent = base_sell();
    intent.limit_price_decimal = "300".to_string();
    intent.market = fresh_market("150");
    let ok = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap();
    assert_eq!(ok.side, StockEtfOrderSide::Sell);
}

#[test]
fn luld_venue_limit_state_is_authoritative_even_for_resting_limit() {
    // venue flag 權威:即便 resting limit(100 < ref 150,本地 band 不套),場方 limit-state 仍恆拒。
    let mut intent = base_buy();
    intent.limit_price_decimal = "100".to_string();
    intent.market = fresh_market("150");
    intent.market.luld_limit_state = true;
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert_eq!(err, CashConstraintViolation::LuldBandBreach);
}

#[test]
fn luld_data_unavailable_fail_closed() {
    let mut intent = base_buy();
    intent.market.data_available = false; // filter 啟用但資料缺 → fail-closed
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert_eq!(err, CashConstraintViolation::LuldStateUnavailable);
}

#[test]
fn luld_filter_disabled_skips_band_check() {
    // filter 關 → 偏離 33% 亦不擋(其餘 gate 仍在;成本 10×200=2000 ≤ 100000)。
    let mut intent = base_buy();
    intent.limit_price_decimal = "200".to_string();
    intent.market = fresh_market("150");
    let mut r = rules();
    r.luld_filter_enabled = false;
    assert!(evaluate(&intent, &base_account(), &r, &full_calendar(), now_rth()).is_ok());
}

// ===========================================================================
// fail-closed 不確定族（快照 / 帳號 / operation / 必填欄 / decimal)
// ===========================================================================

#[test]
fn stale_snapshot_denied() {
    for staleness in [
        SnapshotStaleness::NotSubscribed,
        SnapshotStaleness::SnapshotIncomplete,
        SnapshotStaleness::Stale {
            as_of_ms: 1,
            age_ms: 999,
        },
        SnapshotStaleness::Invalidated,
        SnapshotStaleness::DisconnectedStale,
    ] {
        let mut acct = base_account();
        acct.staleness = staleness;
        let err = evaluate(&base_buy(), &acct, &rules(), &full_calendar(), now_rth()).unwrap_err();
        assert!(matches!(
            err,
            CashConstraintViolation::SnapshotNotFresh { .. }
        ));
    }
}

#[test]
fn account_mismatch_denied() {
    let intent = CashOrderIntent {
        account_id: "DU999".to_string(),
        ..base_buy()
    };
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert_eq!(err, CashConstraintViolation::AccountMismatch);
}

#[test]
fn non_submit_operation_denied() {
    let intent = CashOrderIntent {
        operation: BrokerOperation::PaperOrderCancel,
        ..base_buy()
    };
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert!(matches!(
        err,
        CashConstraintViolation::OperationNotSubmit { .. }
    ));
}

#[test]
fn missing_side_denied() {
    for side in [None, Some(StockEtfOrderSide::Unknown)] {
        let intent = CashOrderIntent { side, ..base_buy() };
        let err = evaluate(
            &intent,
            &base_account(),
            &rules(),
            &full_calendar(),
            now_rth(),
        )
        .unwrap_err();
        assert_eq!(
            err,
            CashConstraintViolation::IntentFieldMissing { field: "side" }
        );
    }
}

#[test]
fn missing_order_type_denied() {
    let intent = CashOrderIntent {
        order_type: None,
        ..base_buy()
    };
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert_eq!(
        err,
        CashConstraintViolation::IntentFieldMissing {
            field: "order_type"
        }
    );
}

#[test]
fn missing_tif_denied() {
    let intent = CashOrderIntent {
        time_in_force: None,
        ..base_buy()
    };
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert_eq!(
        err,
        CashConstraintViolation::IntentFieldMissing {
            field: "time_in_force"
        }
    );
}

#[test]
fn malformed_quantity_denied() {
    let intent = CashOrderIntent {
        quantity_decimal: "abc".to_string(),
        ..base_buy()
    };
    let err = evaluate(
        &intent,
        &base_account(),
        &rules(),
        &full_calendar(),
        now_rth(),
    )
    .unwrap_err();
    assert_eq!(
        err,
        CashConstraintViolation::MalformedDecimal { field: "quantity" }
    );
}

#[test]
fn over_precision_quantity_denied() {
    // 10 位小數 > 定點刻度 9 位 → fail-closed(不截斷)。
    let intent = CashOrderIntent {
        quantity_decimal: "10.0000000001".to_string(),
        ..base_buy()
    };
    let mut r = rules();
    r.allow_fractional = true; // 排除 fractional gate,單證過精度拒
    let err = evaluate(&intent, &base_account(), &r, &full_calendar(), now_rth()).unwrap_err();
    assert_eq!(
        err,
        CashConstraintViolation::MalformedDecimal { field: "quantity" }
    );
}

// ===========================================================================
// 定點 decimal helper 單元
// ===========================================================================

#[test]
fn parse_fixed_and_fmt_roundtrip() {
    assert_eq!(parse_fixed("0"), Some(0));
    assert_eq!(parse_fixed("150"), Some(150 * FIXED_SCALE));
    assert_eq!(parse_fixed("-0.5"), Some(-FIXED_SCALE / 2));
    assert_eq!(parse_fixed(""), None);
    assert_eq!(parse_fixed("1.2.3"), None);
    assert_eq!(parse_fixed("1.2345678901"), None); // >9 位
    assert_eq!(fmt_fixed(1500 * FIXED_SCALE), "1500");
    assert_eq!(fmt_fixed(FIXED_SCALE / 2), "0.5");
    assert_eq!(fmt_fixed(-3 * FIXED_SCALE / 2), "-1.5");
}
