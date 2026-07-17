//! `ibkr_tws_market_data` 測試（synthetic;無 gateway、無 socket）。
//! (a) builder 兩紅線（regulatorySnapshot 封死機器守衛 + E2-F1 出站注入拒 + STK-only +
//!     snapshot⊥genericTickList;IB-NOTE-1 strike="0.0" / IB-NOTE-2 sv-floor 不變量）。
//! (b) digest 狀態機:begin/lines semaphore/floor、TICK_PRICE 合成 tickSize 去重、TICK_SIZE
//!     嚴格 5 欄、per-reqId entitlement FSM（MARKET_DATA_TYPE + 錯誤碼 354/10167/10197/10090）、
//!     delayed provenance 標記、snapshot 11s 終態、no-data 抑制、typed-ignore、斷線/世代重評。

use super::*;
use crate::ibkr_tws_wire::encode_fields;
use openclaw_types::IbkrMarketDataEntitlementStateV1;

const NOW: u64 = 1_000_000_000;
/// 64 hex 占位 hash（S1/S2 供給;shape 驗）。
fn h(c: char) -> String {
    c.to_string().repeat(64)
}

// ---------------------------------------------------------------------------
// (a) builder 紅線
// ---------------------------------------------------------------------------

/// 測試 helper:全限定 SPY 行情請求（snapshot=false;streaming L1）。
fn spy_request() -> MarketDataRequest {
    MarketDataRequest {
        con_id: 756733,
        symbol: "SPY".to_string(),
        exchange: "SMART".to_string(),
        primary_exchange: "ARCA".to_string(),
        local_symbol: "SPY".to_string(),
        trading_class: "SPY".to_string(),
        generic_tick_list: String::new(),
        snapshot: false,
    }
}

/// 解出 reqMktData frame 的欄位序（去 4-byte length 前綴）。
fn decode_req_mkt_data(frame: &[u8]) -> Vec<String> {
    decode_fields(&frame[4..]).expect("reqMktData frame decodes")
}

#[test]
fn req_mkt_data_layout_stk_only_and_currency_usd() {
    let f = encode_req_mkt_data(101, &spy_request(), 176).unwrap();
    let fields = decode_req_mkt_data(&f);
    // [1, 11, reqId, conId, symbol, secType, lastTrade, strike, right, multiplier, exchange,
    //  primaryExchange, currency, localSymbol, tradingClass, deltaNeutral, genericTicks,
    //  snapshot, regulatorySnapshot, mktDataOptions]
    assert_eq!(fields[0], "1"); // OUT REQ_MKT_DATA
    assert_eq!(fields[1], "11"); // v11
    assert_eq!(fields[2], "101"); // reqId
    assert_eq!(fields[3], "756733"); // conId
    assert_eq!(fields[4], "SPY"); // symbol
    assert_eq!(fields[5], "STK"); // secType（STK-only）
    assert_eq!(fields[7], "0.0"); // strike（IB-NOTE-1:float 0.0,非整數 "0"）
    assert_eq!(fields[12], "USD"); // currency（lane 白名單）
    assert_eq!(fields[17], "0"); // snapshot=false
}

/// **紅線 2 機器守衛**:regulatorySnapshot 恆 "0"——任何 `MarketDataRequest` 輸入下 wire
/// regulatorySnapshot 欄不可翻真（結構上非 caller 可控;翻真=每次 0.01 USD 資金效果,paper
/// 亦計費）。matrix 覆蓋 snapshot true/false + 有無 tickList;sv 皆 ≥floor(145,IB-NOTE-2)。
#[test]
fn regulatory_snapshot_field_is_structurally_false_under_all_inputs() {
    let cases = [
        (spy_request(), 176),
        (spy_request(), 145), // floor 邊界（IB-NOTE-2:sv≥145 才安全 emit conId/tradingClass）
        (
            MarketDataRequest {
                generic_tick_list: "233,236".to_string(),
                ..spy_request()
            },
            176,
        ),
        (
            MarketDataRequest {
                snapshot: true,
                ..spy_request()
            },
            176,
        ),
    ];
    for (req, sv) in cases {
        let f = encode_req_mkt_data(9, &req, sv).unwrap();
        let fields = decode_req_mkt_data(&f);
        // sv≥114 下 regulatorySnapshot 欄位置=index 18（deltaNeutral..snapshot 後）。
        assert_eq!(
            fields[18], "0",
            "regulatorySnapshot 必恆 false(=\"0\";資金紅線),req={req:?} sv={sv}"
        );
    }
    // 常量本身 pin（源碼級不變量）。
    assert_eq!(REGULATORY_SNAPSHOT_WIRE, "0");
}

/// **紅線 1 E2-F1**:caller 供給欄含 NUL → typed `WireMalformed(OutboundFieldInvalid)`,絕不
/// 送出被注入 frame。
#[test]
fn req_mkt_data_rejects_nul_injection_in_caller_field() {
    let req = MarketDataRequest {
        exchange: "SMART\0X".to_string(),
        ..spy_request()
    };
    let err = encode_req_mkt_data(1, &req, 176).unwrap_err();
    assert!(matches!(
        err,
        MarketDataReject::WireMalformed(CodecError::OutboundFieldInvalid("embedded NUL"))
    ));
}

/// E2-F1:非 ASCII caller 欄 → fail-closed。
#[test]
fn req_mkt_data_rejects_non_ascii_caller_field() {
    let req = MarketDataRequest {
        symbol: "SPÜ".to_string(),
        ..spy_request()
    };
    let err = encode_req_mkt_data(1, &req, 176).unwrap_err();
    assert!(matches!(
        err,
        MarketDataReject::WireMalformed(CodecError::OutboundFieldInvalid("non-ascii"))
    ));
}

/// snapshot=true 帶 genericTickList → 結構性拒（不送）。
#[test]
fn req_mkt_data_snapshot_forbids_generic_tick_list() {
    let req = MarketDataRequest {
        snapshot: true,
        generic_tick_list: "233".to_string(),
        ..spy_request()
    };
    let err = encode_req_mkt_data(1, &req, 176).unwrap_err();
    assert!(matches!(err, MarketDataReject::SnapshotWithGenericTicks));
}

/// snapshot=true 無 tickList → 放行,snapshot 欄="1"。
#[test]
fn req_mkt_data_snapshot_without_ticks_ok() {
    let req = MarketDataRequest {
        snapshot: true,
        ..spy_request()
    };
    let fields = decode_req_mkt_data(&encode_req_mkt_data(1, &req, 176).unwrap());
    assert_eq!(fields[17], "1");
}

/// cancelMktData 嚴格 3 欄 `[2, 2, reqId]`。
#[test]
fn cancel_mkt_data_layout() {
    let f = encode_cancel_mkt_data(101);
    let fields = decode_fields(&f[4..]).unwrap();
    assert_eq!(fields, vec!["2", "2", "101"]);
}

/// reqMarketDataType `[59, 1, marketDataType]`（delayed=3）。
#[test]
fn req_market_data_type_layout() {
    let f = encode_req_market_data_type(3);
    let fields = decode_fields(&f[4..]).unwrap();
    assert_eq!(fields, vec!["59", "1", "3"]);
}

// ---------------------------------------------------------------------------
// (b) digest 狀態機 — 訊息 builder helpers（payload=已 unframe 欄位序,含 msgId 欄）
// ---------------------------------------------------------------------------

fn tick_price(req_id: i64, tick_type: i64, price: &str, size: i64, attr: i64) -> Vec<u8> {
    encode_fields(&[
        "1",
        "6",
        &req_id.to_string(),
        &tick_type.to_string(),
        price,
        &size.to_string(),
        &attr.to_string(),
    ])
}

fn tick_size(req_id: i64, tick_type: i64, size: i64) -> Vec<u8> {
    encode_fields(&[
        "2",
        "6",
        &req_id.to_string(),
        &tick_type.to_string(),
        &size.to_string(),
    ])
}

fn market_data_type(req_id: i64, mdt: i64) -> Vec<u8> {
    encode_fields(&["58", "1", &req_id.to_string(), &mdt.to_string()])
}

fn tick_snapshot_end(req_id: i64) -> Vec<u8> {
    encode_fields(&["57", "1", &req_id.to_string()])
}

/// 開一個 streaming SPY 訂閱的 digest（reqId 101,sv 176）。
fn streaming_digest() -> MarketDataDigest {
    let mut d = MarketDataDigest::new(MarketDataConfig::default());
    d.begin_subscription(&spy_request(), 101, 176, h('a'), h('b'), NOW)
        .expect("begin streaming");
    d
}

#[test]
fn begin_below_floor_is_fail_closed() {
    let mut d = MarketDataDigest::new(MarketDataConfig::default());
    let err = d
        .begin_subscription(&spy_request(), 101, 144, h('a'), h('b'), NOW)
        .unwrap_err();
    assert!(matches!(
        err,
        MarketDataReject::ServerVersionBelowFloor { floor: 145, .. }
    ));
}

#[test]
fn lines_semaphore_count_quota_fail_closed() {
    let cfg = MarketDataConfig {
        max_lines: 2,
        ..MarketDataConfig::default()
    };
    let mut d = MarketDataDigest::new(cfg);
    for rid in [101, 102] {
        d.begin_subscription(&spy_request(), rid, 176, h('a'), h('b'), NOW)
            .expect("within quota");
    }
    assert_eq!(d.lines_in_use(), 2);
    // 第 3 訂閱 → LinesExhausted（backpressure;禁驅逐既有）。
    let err = d
        .begin_subscription(&spy_request(), 103, 176, h('a'), h('b'), NOW)
        .unwrap_err();
    assert!(matches!(
        err,
        MarketDataReject::LinesExhausted { active: 2, max: 2 }
    ));
    // cancel 一個 → 釋放 line → 可再訂。
    assert!(d.cancel_subscription(101).is_some());
    assert_eq!(d.lines_in_use(), 1);
    d.begin_subscription(&spy_request(), 103, 176, h('a'), h('b'), NOW)
        .expect("resubscribe after cancel");
}

#[test]
fn duplicate_active_req_id_rejected() {
    let mut d = streaming_digest();
    let err = d
        .begin_subscription(&spy_request(), 101, 176, h('a'), h('b'), NOW)
        .unwrap_err();
    assert!(matches!(
        err,
        MarketDataReject::SubscriptionAlreadyActive { req_id: 101 }
    ));
}

/// TICK_PRICE 只 materialize price 邊;內嵌 size=合成 tickSize → 抑制（單源記帳去重紅線）。
/// 隨後 TICK_SIZE(2) 才是 size 唯一來源。
#[test]
fn tick_price_synthesizes_price_only_and_suppresses_embedded_size() {
    let mut d = streaming_digest();
    // BID price tick（tickType 1）帶內嵌 size 100。
    d.on_tick_price_frame(&tick_price(101, 1, "512.34", 100, 0), NOW)
        .unwrap();
    let (_st, rows) = d.quotes(101, NOW).unwrap();
    let rows: Vec<_> = rows.collect();
    // 只 1 row（BID price）;無 BID_SIZE row（內嵌 size 抑制）。
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].tick_type, IbkrTickTypeV1::Bid);
    assert_eq!(rows[0].value_decimal, "512.34");
    assert_eq!(rows[0].entitlement, IbkrTickEntitlementV1::Realtime);
    assert_eq!(d.audit().ticks_applied, 1);
    assert_eq!(d.audit().synth_size_suppressed, 1);
    // TICK_SIZE(2) BID_SIZE=0 → 唯一 size 來源。
    d.on_tick_size_frame(&tick_size(101, 0, 100), NOW).unwrap();
    let (_st, rows) = d.quotes(101, NOW).unwrap();
    assert_eq!(rows.count(), 2, "BID price + BID size 各一（size 未雙記）");
    assert_eq!(d.audit().ticks_applied, 2);
}

/// size=0（無掛單）合法 materialize;TICK_SIZE 嚴格 5 欄。
#[test]
fn tick_size_zero_ok_and_strict_five_fields() {
    let mut d = streaming_digest();
    d.on_tick_size_frame(&tick_size(101, 0, 0), NOW).unwrap();
    let (_st, rows) = d.quotes(101, NOW).unwrap();
    let rows: Vec<_> = rows.collect();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].value_decimal, "0");
    // 6 欄（多一欄）→ WireMalformed（signature 訊息按位不容錯位）。
    let bad = encode_fields(&["2", "6", "101", "0", "100", "surplus"]);
    let err = d.on_tick_size_frame(&bad, NOW).unwrap_err();
    assert!(matches!(err, MarketDataReject::WireMalformed(_)));
    assert_eq!(d.audit().wire_malformed_rejects, 1);
}

/// MARKET_DATA_TYPE(58) per-reqId 綁定 entitlement 三態。
#[test]
fn market_data_type_binds_per_req_entitlement() {
    let mut d = streaming_digest();
    d.on_market_data_type_frame(&market_data_type(101, 3))
        .unwrap();
    assert_eq!(
        d.provenance(101).unwrap().entitlement_state,
        IbkrMarketDataEntitlementStateV1::Delayed
    );
    d.on_market_data_type_frame(&market_data_type(101, 1))
        .unwrap();
    assert_eq!(
        d.provenance(101).unwrap().entitlement_state,
        IbkrMarketDataEntitlementStateV1::Entitled
    );
    assert_eq!(d.audit().market_data_type_bindings, 2);
}

/// entitlement 錯誤碼 354 → NONE halt（釋放 line;provenance 態 None;quote staleness Invalidated）。
#[test]
fn entitlement_354_none_halt() {
    let mut d = streaming_digest();
    d.on_entitlement_error(101, 354);
    assert_eq!(
        d.provenance(101).unwrap().entitlement_state,
        IbkrMarketDataEntitlementStateV1::None
    );
    assert_eq!(
        d.quote_staleness(101, NOW),
        Some(SnapshotStaleness::Invalidated)
    );
    assert_eq!(d.lines_in_use(), 0, "halt 釋放 line");
    assert_eq!(d.audit().entitlement_none_rejects, 1);
    // halt=世代內終態:re-begin 拒。
    let err = d
        .begin_subscription(&spy_request(), 101, 176, h('a'), h('b'), NOW)
        .unwrap_err();
    assert!(matches!(
        err,
        MarketDataReject::EntitlementHalted { req_id: 101 }
    ));
}

/// 10197 competing live session → typed halt（禁重試）。
#[test]
fn entitlement_10197_competing_session_halt() {
    let mut d = streaming_digest();
    d.on_entitlement_error(101, 10197);
    assert_eq!(
        d.provenance(101).unwrap().entitlement_state,
        IbkrMarketDataEntitlementStateV1::None
    );
    assert_eq!(d.audit().entitlement_competing_session, 1);
    assert_eq!(d.lines_in_use(), 0);
}

/// 10167:未 opt-in → 協議意外退訂;已 opt-in（request_delayed_mode）→ Delayed 確認。
#[test]
fn entitlement_10167_gated_on_delayed_opt_in() {
    // 無 opt-in。
    let mut d = streaming_digest();
    d.on_entitlement_error(101, 10167);
    assert_eq!(d.audit().entitlement_delayed_without_optin, 1);
    assert_eq!(
        d.quote_staleness(101, NOW),
        Some(SnapshotStaleness::Invalidated),
        "未 opt-in 收 delayed 確認=退訂 halt"
    );
    // 有 opt-in。
    let mut d2 = MarketDataDigest::new(MarketDataConfig::default());
    let _ = d2.request_delayed_mode(); // 先送 reqMarketDataType(3)
    assert!(d2.delayed_opt_in());
    d2.begin_subscription(&spy_request(), 202, 176, h('a'), h('b'), NOW)
        .unwrap();
    d2.on_entitlement_error(202, 10167);
    assert_eq!(d2.audit().entitlement_delayed_confirmed, 1);
    assert_eq!(
        d2.provenance(202).unwrap().entitlement_state,
        IbkrMarketDataEntitlementStateV1::Delayed
    );
}

/// 10090 partial → 窗續存（entitlement 不 halt;audit 記帳）。
#[test]
fn entitlement_10090_partial_keeps_window() {
    let mut d = streaming_digest();
    d.on_market_data_type_frame(&market_data_type(101, 1))
        .unwrap();
    d.on_entitlement_error(101, 10090);
    assert_eq!(d.audit().entitlement_partial, 1);
    // 仍 Entitled,line 未釋放。
    assert_eq!(
        d.provenance(101).unwrap().entitlement_state,
        IbkrMarketDataEntitlementStateV1::Entitled
    );
    assert_eq!(d.lines_in_use(), 1);
}

/// 未知 entitlement code（指向本訂閱 reqId）→ fail-closed 退訂 halt。
#[test]
fn entitlement_unknown_code_halts() {
    let mut d = streaming_digest();
    d.on_entitlement_error(101, 10168); // 表外
    assert_eq!(d.audit().entitlement_unknown_code_halts, 1);
    assert_eq!(
        d.quote_staleness(101, NOW),
        Some(SnapshotStaleness::Invalidated)
    );
}

/// delayed tick（66-71）→ quote row entitlement=Delayed（S3a 契約守）;首 tick 促 Pending→Delayed。
#[test]
fn delayed_tick_marks_delayed_entitlement_and_promotes_state() {
    let mut d = streaming_digest();
    // DelayedBid=66（price）。
    d.on_tick_price_frame(&tick_price(101, 66, "1.23", 5, 0), NOW)
        .unwrap();
    let (_st, rows) = d.quotes(101, NOW).unwrap();
    let rows: Vec<_> = rows.collect();
    assert_eq!(rows[0].tick_type, IbkrTickTypeV1::DelayedBid);
    assert_eq!(rows[0].entitlement, IbkrTickEntitlementV1::Delayed);
    // 契約 validate 過（delayed 值正確標 Delayed）。
    assert!(rows[0].validate(NOW).accepted);
    // 首 delayed tick 促 Pending→Delayed。
    assert_eq!(
        d.provenance(101).unwrap().entitlement_state,
        IbkrMarketDataEntitlementStateV1::Delayed
    );
}

/// entitlement 態衝突:state=Delayed 卻收 realtime tick → 抑制（不 materialize entitlement 謊言）。
#[test]
fn realtime_tick_under_delayed_state_is_suppressed() {
    let mut d = streaming_digest();
    d.on_market_data_type_frame(&market_data_type(101, 3))
        .unwrap(); // Delayed
                   // realtime BID（tickType 1）。
    d.on_tick_price_frame(&tick_price(101, 1, "512.34", 100, 0), NOW)
        .unwrap();
    assert_eq!(d.audit().entitlement_tick_conflict, 1);
    let (_st, rows) = d.quotes(101, NOW).unwrap();
    assert_eq!(rows.count(), 0, "衝突 tick 不併入");
}

/// halt 後仍收 tick → 抑制。
#[test]
fn tick_after_halt_suppressed() {
    let mut d = streaming_digest();
    d.on_entitlement_error(101, 354); // None halt
    d.on_tick_price_frame(&tick_price(101, 1, "512.34", 100, 0), NOW)
        .unwrap();
    assert_eq!(d.audit().tick_after_halt_suppressed, 1);
}

/// no-data 值抑制:price=-1 / 量級哨兵 / 空欄 → 不 materialize。
#[test]
fn no_data_values_suppressed() {
    let mut d = streaming_digest();
    d.on_tick_price_frame(&tick_price(101, 1, "-1", 0, 0), NOW)
        .unwrap();
    d.on_tick_price_frame(&tick_price(101, 4, "1.7976931348623157e308", 0, 0), NOW)
        .unwrap();
    let (_st, rows) = d.quotes(101, NOW).unwrap();
    assert_eq!(rows.count(), 0);
    assert_eq!(d.audit().no_data_suppressed, 2);
}

/// 未訂而收:unknown reqId 的 tick → NoActiveSubscription + audit（session 不斷）。
#[test]
fn tick_for_unknown_req_id_rejected() {
    let mut d = streaming_digest();
    let err = d
        .on_tick_price_frame(&tick_price(999, 1, "1.0", 0, 0), NOW)
        .unwrap_err();
    assert!(matches!(
        err,
        MarketDataReject::NoActiveSubscription { req_id: 999 }
    ));
    assert_eq!(d.audit().no_active_subscription_rejects, 1);
}

/// 壞欄位（非數字 reqId）→ WireMalformed。
#[test]
fn malformed_tick_field_fail_closed() {
    let mut d = streaming_digest();
    let bad = encode_fields(&["1", "6", "abc", "1", "1.0", "0", "0"]);
    let err = d.on_tick_price_frame(&bad, NOW).unwrap_err();
    assert!(matches!(err, MarketDataReject::WireMalformed(_)));
}

/// 表外 tickType（HIGH=6 等非 L1 白名單）→ typed-ignore。
#[test]
fn off_whitelist_tick_type_typed_ignore() {
    let mut d = streaming_digest();
    d.on_tick_price_frame(&tick_price(101, 6, "550.0", 0, 0), NOW)
        .unwrap();
    assert_eq!(d.audit().unknown_tick_type_ignored, 1);
    let (_st, rows) = d.quotes(101, NOW).unwrap();
    assert_eq!(rows.count(), 0);
}

/// TICK_GENERIC/STRING/REQ_PARAMS typed-ignore（記帳丟棄,session 不斷）。
#[test]
fn aux_ticks_typed_ignore() {
    let mut d = streaming_digest();
    d.on_tick_generic_frame(&encode_fields(&["45", "6", "101", "49", "0"]))
        .unwrap();
    d.on_tick_string_frame(&encode_fields(&["46", "6", "101", "45", "ts"]))
        .unwrap();
    // TICK_REQ_PARAMS 無 version:[81, tickerId, minTick, bboExchange, snapshotPermissions]。
    d.on_tick_req_params_frame(&encode_fields(&["81", "101", "0.01", "ARCA", "3"]))
        .unwrap();
    assert_eq!(d.audit().generic_tick_ignored, 1);
    assert_eq!(d.audit().string_tick_ignored, 1);
    assert_eq!(d.audit().tick_req_params_ignored, 1);
}

/// TICK_REQ_PARAMS 誤帶 version 欄（6 欄）→ WireMalformed（無 version 契約守）。
#[test]
fn tick_req_params_rejects_version_field() {
    let mut d = streaming_digest();
    let with_version = encode_fields(&["81", "1", "101", "0.01", "ARCA", "3"]);
    let err = d.on_tick_req_params_frame(&with_version).unwrap_err();
    assert!(matches!(err, MarketDataReject::WireMalformed(_)));
}

/// snapshot 11s 終態 timeout:逾窗無 TICK_SNAPSHOT_END → typed 終態釋放 line。
#[test]
fn snapshot_terminal_timeout() {
    let mut d = MarketDataDigest::new(MarketDataConfig::default());
    let snap = MarketDataRequest {
        snapshot: true,
        ..spy_request()
    };
    d.begin_subscription(&snap, 301, 176, h('a'), h('b'), NOW)
        .unwrap();
    assert_eq!(d.lines_in_use(), 1);
    assert_eq!(
        d.quote_staleness(301, NOW),
        Some(SnapshotStaleness::SnapshotIncomplete)
    );
    // 未逾窗（+5s < 13s）→ 無終態。
    assert!(d.expire_overdue(NOW + 5_000).is_empty());
    // 逾窗（+14s > 13s）→ 終態。
    let out = d.expire_overdue(NOW + 14_000);
    assert_eq!(out.len(), 1);
    assert_eq!(out[0].req_id, 301);
    assert_eq!(d.lines_in_use(), 0, "snapshot 終態釋放 line");
    assert_eq!(d.audit().snapshot_terminals, 1);
}

/// snapshot TICK_SNAPSHOT_END → SnapshotComplete（釋放 line）。
#[test]
fn snapshot_end_completes_and_frees_line() {
    let mut d = MarketDataDigest::new(MarketDataConfig::default());
    let snap = MarketDataRequest {
        snapshot: true,
        ..spy_request()
    };
    d.begin_subscription(&snap, 301, 176, h('a'), h('b'), NOW)
        .unwrap();
    d.on_tick_price_frame(&tick_price(301, 1, "512.34", 100, 0), NOW)
        .unwrap();
    d.on_tick_snapshot_end_frame(&tick_snapshot_end(301))
        .unwrap();
    assert_eq!(d.lines_in_use(), 0);
    // 值保留供唯讀（Fresh）。
    assert!(matches!(
        d.quote_staleness(301, NOW),
        Some(SnapshotStaleness::Fresh { .. })
    ));
}

/// provenance:realtime 窗有 tick 後 validate 過（entitlement Entitled + hash shape）。
#[test]
fn provenance_accepts_after_realtime_window() {
    let mut d = streaming_digest();
    d.on_market_data_type_frame(&market_data_type(101, 1))
        .unwrap();
    d.on_tick_price_frame(&tick_price(101, 1, "512.34", 100, 0), NOW)
        .unwrap();
    let prov = d.provenance(101).unwrap();
    assert!(prov.validate(NOW).accepted, "provenance 應過契約校驗");
    assert_eq!(
        prov.entitlement_state,
        IbkrMarketDataEntitlementStateV1::Entitled
    );
    // provenance_hash 綁 preimage（改 entitlement 態則 hash 變——溯源錨真綁）。
    assert_eq!(prov.provenance_hash.len(), 64);
}

/// quote staleness 綁定視圖:新鮮窗內 Fresh,逾窗 Stale。
#[test]
fn quote_bound_view_freshness() {
    let mut d = streaming_digest();
    // 尚無 tick → SnapshotIncomplete。
    assert_eq!(
        d.quote_staleness(101, NOW),
        Some(SnapshotStaleness::SnapshotIncomplete)
    );
    d.on_tick_price_frame(&tick_price(101, 1, "512.34", 100, 0), NOW)
        .unwrap();
    assert!(matches!(
        d.quote_staleness(101, NOW),
        Some(SnapshotStaleness::Fresh { .. })
    ));
    // 逾 quote_stale_after(5s)。
    assert!(matches!(
        d.quote_staleness(101, NOW + 6_000),
        Some(SnapshotStaleness::Stale { .. })
    ));
}

/// 斷線 → DisconnectedStale;世代推進 → halt 面重評為 DisconnectedStale（re-begin 可）。
#[test]
fn disconnect_and_generation_reeval() {
    let mut d = streaming_digest();
    d.on_disconnect();
    assert_eq!(
        d.quote_staleness(101, NOW),
        Some(SnapshotStaleness::DisconnectedStale)
    );
    assert!(!d.delayed_opt_in(), "delayed opt-in 不跨連線");
    // 斷線後可 re-begin（覆寫 slot,不新增 line）。
    d.begin_subscription(&spy_request(), 101, 176, h('a'), h('b'), NOW + 1)
        .expect("re-begin after disconnect");
    // halt 面世代重評。
    let mut d2 = streaming_digest();
    d2.on_entitlement_error(101, 354); // Halted
    d2.on_new_connection_generation();
    assert_eq!(
        d2.quote_staleness(101, NOW),
        Some(SnapshotStaleness::DisconnectedStale)
    );
}
