//! `ibkr_tws_market_data` 測試（synthetic;無 gateway、無 socket）。
//! 本 commit 覆蓋兩紅線 builder 安全:regulatorySnapshot 封死（機器守衛）+ E2-F1 出站注入
//! 拒 + STK-only + snapshot⊥genericTickList。decode/entitlement FSM 測試歸後續 commit。

use super::*;
use crate::ibkr_tws_wire::decode_fields;

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
    // frame = 4-byte BE length + payload;payload 為 null-terminated 欄。
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
    assert_eq!(fields[12], "USD"); // currency（lane 白名單）
    assert_eq!(fields[17], "0"); // snapshot=false
}

/// **紅線 2 機器守衛**:regulatorySnapshot 恆 "0"——任何 `MarketDataRequest` 輸入下 wire
/// regulatorySnapshot 欄不可翻真（結構上非 caller 可控;翻真=每次 0.01 USD 資金效果,paper
/// 亦計費）。matrix 覆蓋 snapshot true/false + 有無 tickList + 各 sv band。
#[test]
fn regulatory_snapshot_field_is_structurally_false_under_all_inputs() {
    // sv≥114 下 regulatorySnapshot 欄位置=index 18（deltaNeutral..snapshot 後）。
    let cases = [
        (spy_request(), 176),
        (spy_request(), 114), // 門檻邊界
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
        assert_eq!(
            fields[18], "0",
            "regulatorySnapshot 必恆 false(=\"0\";資金紅線),req={req:?} sv={sv}"
        );
    }
    // 常量本身 pin（源碼級不變量）。
    assert_eq!(REGULATORY_SNAPSHOT_WIRE, "0");
}

/// sv<114 時 regulatorySnapshot 欄結構性缺席（不誤生欄;佈局隨 sv 門控）。
#[test]
fn regulatory_snapshot_field_absent_below_gate() {
    // 造一個 sv=113 的請求（< SV_GATE_REGULATORY_SNAPSHOT=114）:reg 欄不出現,但 mktDataOptions
    //（sv≥70）仍在 → 欄數少一。與 sv=176 對比。
    let full = decode_req_mkt_data(&encode_req_mkt_data(9, &spy_request(), 176).unwrap());
    let below = decode_req_mkt_data(&encode_req_mkt_data(9, &spy_request(), 113).unwrap());
    assert_eq!(
        below.len(),
        full.len() - 1,
        "sv<114 少 regulatorySnapshot 欄"
    );
    // sv=113 下末欄=mktDataOptions（"")而非 regulatorySnapshot。
    assert_eq!(below[17], "0"); // snapshot 仍在 index 17
    assert_eq!(below[18], ""); // 直接 mktDataOptions(空),無 regulatorySnapshot
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
