//! W5-S2 account/positions 消化層測試（拆檔;主體 `ibkr_tws_account_data.rs`,同
//! session/pacing/driver 範式）。純同步、注入時鐘（任意相對 ms,fixture 禁硬編日期）、
//! 零 socket、零 IO——inbound payload 以 wire `encode_fields` 合成。

use super::*;

use openclaw_types::IbkrAccountSummaryRowBlocker;

/// 測試用注入時鐘基準（任意相對值,非牆鐘）。
const T0: u64 = 10_000;
const REQ_ID: i64 = 9001;
const SERVER_V: i32 = 176;

fn digest() -> AccountDataDigest {
    AccountDataDigest::new(AccountDataConfig::default())
}

/// 合成 IN 63 accountSummary 行 payload（IB pinned 欄序）。
fn summary_payload(req_id: i64, account: &str, tag: &str, value: &str, currency: &str) -> Vec<u8> {
    let rid = req_id.to_string();
    encode_fields(&["63", "1", &rid, account, tag, value, currency])
}

/// 合成 IN 64 accountSummaryEnd payload。
fn summary_end_payload(req_id: i64) -> Vec<u8> {
    let rid = req_id.to_string();
    encode_fields(&["64", "1", &rid])
}

/// 合成 IN 61 position 行 payload（version 3,16 欄;STK 佔位欄空值/零值）。
fn position_payload(
    account: &str,
    con_id: i64,
    symbol: &str,
    sec_type: &str,
    exchange: &str,
    currency: &str,
    position: &str,
    avg_cost: &str,
) -> Vec<u8> {
    let cid = con_id.to_string();
    encode_fields(&[
        "61", "3", account, &cid, symbol, sec_type, "", "0", "", "", exchange, currency, symbol,
        symbol, position, avg_cost,
    ])
}

/// 合成 IN 62 positionEnd payload。
fn position_end_payload() -> Vec<u8> {
    encode_fields(&["62", "1"])
}

/// 已到 Live 的 summary 快照（訂閱 → 一行 NetLiquidation → End）。
fn live_summary(d: &mut AccountDataDigest) {
    d.begin_account_summary(REQ_ID).unwrap();
    d.on_account_summary_frame(
        &summary_payload(REQ_ID, "DU1234567", "NetLiquidation", "100000.25", "USD"),
        T0,
    )
    .unwrap();
    d.on_account_summary_end_frame(&summary_end_payload(REQ_ID), T0 + 10)
        .unwrap();
}

// ===========================================================================
// (a) 出站 builder:IB pinned 欄位序
// ===========================================================================

#[test]
fn outbound_builders_match_pinned_field_order() {
    // reqAccountSummary = [62, 1, reqId, "All", tags(9 值逗號)]。
    let frame = encode_req_account_summary(7);
    let payload = &frame[4..];
    let fields = decode_fields(payload).unwrap();
    assert_eq!(fields[0], "62");
    assert_eq!(fields[1], "1");
    assert_eq!(fields[2], "7");
    assert_eq!(fields[3], "All", "group 必為 All(不支援單帳號 group)");
    let tags: Vec<&str> = fields[4].split(',').collect();
    assert_eq!(tags.len(), 9, "tags = 契約白名單 9 值單欄逗號連接");
    assert_eq!(
        tags,
        IBKR_ACCOUNT_SUMMARY_WIRE_TAG_WHITELIST.to_vec(),
        "tags 序 = 契約 const 序"
    );
    // cancelAccountSummary = [63, 1, reqId]。
    let fields = decode_fields(&encode_cancel_account_summary(7)[4..]).unwrap();
    assert_eq!(fields, vec!["63", "1", "7"]);
    // reqPositions = [61, 1](無 reqId)。
    let fields = decode_fields(&encode_req_positions()[4..]).unwrap();
    assert_eq!(fields, vec!["61", "1"]);
    // cancelPositions = [64, 1](無 reqId,全域取消)。
    let fields = decode_fields(&encode_cancel_positions()[4..]).unwrap();
    assert_eq!(fields, vec!["64", "1"]);
}

// ===========================================================================
// (b) summary 生命週期:全量 → End → 增量;staleness typed
// ===========================================================================

#[test]
fn summary_full_snapshot_then_end_then_delta() {
    let mut d = digest();
    assert_eq!(d.summary_staleness(T0), SnapshotStaleness::NotSubscribed);
    d.begin_account_summary(REQ_ID).unwrap();
    // End 前=快照未完整。
    assert_eq!(
        d.summary_staleness(T0),
        SnapshotStaleness::SnapshotIncomplete
    );
    d.on_account_summary_frame(
        &summary_payload(REQ_ID, "DU1234567", "NetLiquidation", "100000.25", "USD"),
        T0,
    )
    .unwrap();
    d.on_account_summary_frame(
        &summary_payload(REQ_ID, "DU1234567", "BuyingPower", "50000", "USD"),
        T0 + 1,
    )
    .unwrap();
    assert_eq!(
        d.summary_staleness(T0 + 1),
        SnapshotStaleness::SnapshotIncomplete,
        "行到達但 End 未到 → 仍未完整"
    );
    d.on_account_summary_end_frame(&summary_end_payload(REQ_ID), T0 + 2)
        .unwrap();
    assert_eq!(
        d.summary_staleness(T0 + 3),
        SnapshotStaleness::Fresh { as_of_ms: T0 + 2 }
    );
    assert_eq!(d.summary_rows().count(), 2);
    // 節拍增量:同 tag 後到覆蓋(IB 每 3 分鐘僅推變動 tag)。
    d.on_account_summary_frame(
        &summary_payload(REQ_ID, "DU1234567", "BuyingPower", "48000", "USD"),
        T0 + 180_000,
    )
    .unwrap();
    assert_eq!(d.summary_rows().count(), 2, "同 tag 覆蓋非追加");
    let bp = d
        .summary_rows()
        .find(|r| r.tag == IbkrAccountSummaryTagV1::BuyingPower)
        .unwrap();
    assert_eq!(bp.value_decimal, "48000");
    assert_eq!(bp.captured_at_ms, T0 + 180_000, "client 側捕捉時鐘注入");
    assert!(bp.snapshot_seq > 0, "快照序非零(契約要求)");
}

#[test]
fn summary_staleness_goes_stale_after_window() {
    let mut d = digest();
    live_summary(&mut d);
    // 新鮮窗內 Fresh;逾 config 窗(390s)→ Stale 保守標記(值可能只是未變)。
    let last = T0 + 10;
    assert!(matches!(
        d.summary_staleness(last + 390_000),
        SnapshotStaleness::Fresh { .. }
    ));
    match d.summary_staleness(last + 390_001) {
        SnapshotStaleness::Stale { as_of_ms, age_ms } => {
            assert_eq!(as_of_ms, last);
            assert_eq!(age_ms, 390_001);
        }
        s => panic!("應為 Stale,得 {s:?}"),
    }
}

#[test]
fn summary_stale_window_is_config_driven() {
    // 參數禁假功能:改 summary_stale_after → 行為變化。
    let mut d = AccountDataDigest::new(AccountDataConfig {
        summary_stale_after: Duration::from_secs(1),
        ..AccountDataConfig::default()
    });
    live_summary(&mut d);
    assert!(matches!(
        d.summary_staleness(T0 + 10 + 1_001),
        SnapshotStaleness::Stale { .. }
    ));
}

// ===========================================================================
// (c) G3:單訂閱不變量;cancel;reqId 錯配;未訂而收
// ===========================================================================

#[test]
fn g3_second_summary_subscription_rejected() {
    let mut d = digest();
    d.begin_account_summary(REQ_ID).unwrap();
    // 活躍中(End 前後皆然)再訂 → 結構性拒,不依賴 server 報錯。
    assert_eq!(
        d.begin_account_summary(REQ_ID + 1).unwrap_err(),
        AccountDataReject::SummaryAlreadyActive
    );
    d.on_account_summary_end_frame(&summary_end_payload(REQ_ID), T0)
        .unwrap();
    assert_eq!(
        d.begin_account_summary(REQ_ID + 1).unwrap_err(),
        AccountDataReject::SummaryAlreadyActive
    );
}

#[test]
fn g3_second_positions_subscription_rejected() {
    let mut d = digest();
    d.begin_positions(SERVER_V).unwrap();
    assert_eq!(
        d.begin_positions(SERVER_V).unwrap_err(),
        AccountDataReject::PositionsAlreadyActive
    );
}

#[test]
fn cancel_summary_clears_snapshot_and_requires_active() {
    let mut d = digest();
    // 未訂而 cancel → 拒(不空發 cancel)。
    assert_eq!(
        d.cancel_account_summary().unwrap_err(),
        AccountDataReject::NoActiveSubscription
    );
    live_summary(&mut d);
    let frame = d.cancel_account_summary().unwrap();
    let fields = decode_fields(&frame[4..]).unwrap();
    assert_eq!(fields, vec!["63", "1", &REQ_ID.to_string()]);
    assert_eq!(d.summary_staleness(T0), SnapshotStaleness::NotSubscribed);
    assert_eq!(d.summary_rows().count(), 0, "cancel 後不留半新鮮殘影");
    // cancel 後可重訂(新快照世代)。
    let seq_before = d.snapshot_seq();
    d.begin_account_summary(REQ_ID + 1).unwrap();
    assert_eq!(d.snapshot_seq(), seq_before + 1);
}

#[test]
fn cancel_positions_requires_active_and_is_global() {
    let mut d = digest();
    assert_eq!(
        d.cancel_positions().unwrap_err(),
        AccountDataReject::NoActiveSubscription
    );
    d.begin_positions(SERVER_V).unwrap();
    let frame = d.cancel_positions().unwrap();
    assert_eq!(decode_fields(&frame[4..]).unwrap(), vec!["64", "1"]);
    assert_eq!(d.positions_staleness(T0), SnapshotStaleness::NotSubscribed);
}

#[test]
fn summary_req_id_mismatch_and_unsubscribed_frames_rejected() {
    let mut d = digest();
    // 未訂而收 → NoActiveSubscription。
    assert_eq!(
        d.on_account_summary_frame(
            &summary_payload(REQ_ID, "DU1", "NetLiquidation", "1", "USD"),
            T0
        )
        .unwrap_err(),
        AccountDataReject::NoActiveSubscription
    );
    assert_eq!(
        d.on_position_end_frame(&position_end_payload(), T0)
            .unwrap_err(),
        AccountDataReject::NoActiveSubscription
    );
    // reqId 錯配 → UnexpectedReqId,不併入快照。
    d.begin_account_summary(REQ_ID).unwrap();
    assert_eq!(
        d.on_account_summary_frame(
            &summary_payload(REQ_ID + 5, "DU1", "NetLiquidation", "1", "USD"),
            T0
        )
        .unwrap_err(),
        AccountDataReject::UnexpectedReqId { got: REQ_ID + 5 }
    );
    assert_eq!(
        d.on_account_summary_end_frame(&summary_end_payload(REQ_ID + 5), T0)
            .unwrap_err(),
        AccountDataReject::UnexpectedReqId { got: REQ_ID + 5 }
    );
    assert_eq!(d.summary_rows().count(), 0);
}

// ===========================================================================
// (d) 契約 fail-closed:表外 tag / 幣別 / 壞 decimal → blocker 路徑,不 panic
// ===========================================================================

#[test]
fn off_whitelist_tag_takes_unknown_denied_blocker_path() {
    let mut d = digest();
    d.begin_account_summary(REQ_ID).unwrap();
    // 表外 tag "Cushion" → 契約 UnknownDenied blocker(不 panic,快照毒化)。
    let err = d
        .on_account_summary_frame(&summary_payload(REQ_ID, "DU1", "Cushion", "0.5", "USD"), T0)
        .unwrap_err();
    match err {
        AccountDataReject::SummaryRowBlocked(blockers) => {
            assert!(blockers.contains(&IbkrAccountSummaryRowBlocker::TagUnknownDenied));
        }
        e => panic!("應為 SummaryRowBlocked,得 {e:?}"),
    }
    assert_eq!(d.summary_staleness(T0), SnapshotStaleness::Invalidated);
    assert_eq!(d.summary_rows().count(), 0, "blocker 行不併入");
    // Invalidated 後可重訂恢復(新快照世代)。
    d.begin_account_summary(REQ_ID + 1).unwrap();
    assert_eq!(
        d.summary_staleness(T0),
        SnapshotStaleness::SnapshotIncomplete
    );
}

#[test]
fn bad_decimal_and_bad_currency_are_contract_blocked() {
    let mut d = digest();
    d.begin_account_summary(REQ_ID).unwrap();
    assert!(matches!(
        d.on_account_summary_frame(
            &summary_payload(REQ_ID, "DU1", "NetLiquidation", "1e5", "USD"),
            T0
        )
        .unwrap_err(),
        AccountDataReject::SummaryRowBlocked(_)
    ));
    let mut d = digest();
    d.begin_account_summary(REQ_ID).unwrap();
    assert!(matches!(
        d.on_account_summary_frame(
            &summary_payload(REQ_ID, "DU1", "NetLiquidation", "100", "EUR"),
            T0
        )
        .unwrap_err(),
        AccountDataReject::SummaryRowBlocked(_)
    ));
}

#[test]
fn negative_available_funds_is_accepted_after_divergent_5_fix() {
    // IB DIVERGENT #5 消化端證明:AvailableFunds 負值=合法簽名承載(契約修正後)。
    let mut d = digest();
    d.begin_account_summary(REQ_ID).unwrap();
    d.on_account_summary_frame(
        &summary_payload(REQ_ID, "DU1234567", "AvailableFunds", "-123.45", "USD"),
        T0,
    )
    .unwrap();
    assert_eq!(d.summary_rows().count(), 1);
}

#[test]
fn wire_malformed_summary_frames_are_typed() {
    let mut d = digest();
    d.begin_account_summary(REQ_ID).unwrap();
    // 欄數不足 → WireMalformed(呼叫端 fail-closed 斷線)。
    assert!(matches!(
        d.on_account_summary_frame(&encode_fields(&["63", "1", "9001"]), T0)
            .unwrap_err(),
        AccountDataReject::WireMalformed(_)
    ));
    // reqId 非數字 → WireMalformed(禁 unwrap_or(0) 捏造)。
    assert!(matches!(
        d.on_account_summary_frame(
            &encode_fields(&["63", "1", "abc", "DU1", "NetLiquidation", "1", "USD"]),
            T0
        )
        .unwrap_err(),
        AccountDataReject::WireMalformed(_)
    ));
    // 錯 msgId → WireMalformed(不容錯位)。
    assert!(matches!(
        d.on_account_summary_frame(
            &summary_end_payload(REQ_ID), // 64 的 payload 餵 63 入口
            T0
        )
        .unwrap_err(),
        AccountDataReject::WireMalformed(_)
    ));
}

// ===========================================================================
// (e) positions:G1 version 門控 + 佔位欄按位消費 + short 拒 + End
// ===========================================================================

#[test]
fn positions_full_snapshot_then_end() {
    let mut d = digest();
    d.begin_positions(SERVER_V).unwrap();
    assert_eq!(
        d.positions_staleness(T0),
        SnapshotStaleness::SnapshotIncomplete
    );
    d.on_position_frame(
        &position_payload(
            "DU1234567",
            756733,
            "SPY",
            "STK",
            "ARCA",
            "USD",
            "100",
            "412.35",
        ),
        T0,
    )
    .unwrap();
    d.on_position_end_frame(&position_end_payload(), T0 + 5)
        .unwrap();
    assert_eq!(
        d.positions_staleness(T0 + 6),
        SnapshotStaleness::Fresh { as_of_ms: T0 + 5 }
    );
    let row = d.positions_rows().next().unwrap();
    assert_eq!(row.con_id, 756733);
    assert_eq!(row.symbol, "SPY");
    assert_eq!(row.position_decimal, "100");
    assert_eq!(row.avg_cost_decimal, "412.35");
    // 事件驅動增量:同 (account, con_id) 覆蓋。
    d.on_position_frame(
        &position_payload(
            "DU1234567",
            756733,
            "SPY",
            "STK",
            "ARCA",
            "USD",
            "50",
            "410.00",
        ),
        T0 + 100,
    )
    .unwrap();
    assert_eq!(d.positions_rows().count(), 1);
    assert_eq!(d.positions_rows().next().unwrap().position_decimal, "50");
}

#[test]
fn g1_position_version_below_3_rejected_no_fabricated_avg_cost() {
    let mut d = digest();
    d.begin_positions(SERVER_V).unwrap();
    // version=2(無 avgCost 欄,15 欄)→ typed 拒,禁 ibapi 式默認 avgCost=0 捏值。
    let payload = encode_fields(&[
        "61", "2", "DU1", "756733", "SPY", "STK", "", "0", "", "", "ARCA", "USD", "SPY", "SPY",
        "100",
    ]);
    assert_eq!(
        d.on_position_frame(&payload, T0).unwrap_err(),
        AccountDataReject::PositionVersionTooOld { version: 2 }
    );
    assert_eq!(d.positions_rows().count(), 0);
}

#[test]
fn g1_server_version_below_floor_blocks_subscription() {
    let mut d = digest();
    // serverVersion 100 < 101(MIN_SERVER_VER_FRACTIONAL_POSITIONS)→ 訂閱前 blocker。
    assert_eq!(
        d.begin_positions(100).unwrap_err(),
        AccountDataReject::ServerVersionBelowPositionsFloor {
            server_version: 100,
            floor: 101
        }
    );
    // config 化下界:改 config → 行為變化(參數禁假功能)。
    let mut d = AccountDataDigest::new(AccountDataConfig {
        min_positions_server_version: 90,
        ..AccountDataConfig::default()
    });
    d.begin_positions(100).unwrap();
}

#[test]
fn position_v3_field_count_mismatch_is_wire_malformed() {
    let mut d = digest();
    d.begin_positions(SERVER_V).unwrap();
    // v3 宣稱但僅 15 欄(缺 avgCost)→ 按位消費不容錯位,WireMalformed。
    let payload = encode_fields(&[
        "61", "3", "DU1", "756733", "SPY", "STK", "", "0", "", "", "ARCA", "USD", "SPY", "SPY",
        "100",
    ]);
    assert!(matches!(
        d.on_position_frame(&payload, T0).unwrap_err(),
        AccountDataReject::WireMalformed(_)
    ));
}

#[test]
fn short_position_and_off_whitelist_sec_type_are_contract_blocked() {
    let mut d = digest();
    d.begin_positions(SERVER_V).unwrap();
    // 負倉(short 永久 denied)→ 契約 blocker 路徑。
    assert!(matches!(
        d.on_position_frame(
            &position_payload("DU1", 756733, "SPY", "STK", "ARCA", "USD", "-10", "412.35"),
            T0
        )
        .unwrap_err(),
        AccountDataReject::PositionsRowBlocked(_)
    ));
    assert_eq!(d.positions_staleness(T0), SnapshotStaleness::Invalidated);
    // 表外 secType(OPT=永久 denied 面投影)→ 契約 blocker。
    let mut d = digest();
    d.begin_positions(SERVER_V).unwrap();
    assert!(matches!(
        d.on_position_frame(
            &position_payload("DU1", 756733, "SPY", "OPT", "ARCA", "USD", "10", "412.35"),
            T0
        )
        .unwrap_err(),
        AccountDataReject::PositionsRowBlocked(_)
    ));
}

// ===========================================================================
// (f) G2 哨兵守衛(config 化;UNSET_DECIMAL 不可證 → 位數守衛)
// ===========================================================================

#[test]
fn g2_sentinel_suspect_values_rejected_by_config_guard() {
    let mut d = digest();
    d.begin_account_summary(REQ_ID).unwrap();
    // 21 位整數(默認守衛)→ 哨兵嫌疑拒 + 快照毒化。
    let sentinel = "1".repeat(21);
    assert_eq!(
        d.on_account_summary_frame(
            &summary_payload(REQ_ID, "DU1", "NetLiquidation", &sentinel, "USD"),
            T0
        )
        .unwrap_err(),
        AccountDataReject::SentinelSuspectValue
    );
    assert_eq!(d.summary_staleness(T0), SnapshotStaleness::Invalidated);
    // 20 位(守衛下)→ 通過守衛(契約層再驗格式)。
    let mut d = digest();
    d.begin_account_summary(REQ_ID).unwrap();
    let big_but_ok = "9".repeat(20);
    d.on_account_summary_frame(
        &summary_payload(REQ_ID, "DU1", "NetLiquidation", &big_but_ok, "USD"),
        T0,
    )
    .unwrap();
    // config 化:守衛收緊到 5 位 → 6 位值即拒(參數禁假功能)。
    let mut d = AccountDataDigest::new(AccountDataConfig {
        sentinel_integer_digits_guard: 5,
        ..AccountDataConfig::default()
    });
    d.begin_positions(SERVER_V).unwrap();
    assert_eq!(
        d.on_position_frame(
            &position_payload("DU1", 756733, "SPY", "STK", "ARCA", "USD", "100", "123456.0"),
            T0
        )
        .unwrap_err(),
        AccountDataReject::SentinelSuspectValue
    );
}

// ===========================================================================
// (g) 斷線失效:全部快照標 DisconnectedStale,重連需重訂閱
// ===========================================================================

#[test]
fn disconnect_marks_snapshots_stale_and_requires_resubscribe() {
    let mut d = digest();
    live_summary(&mut d);
    d.begin_positions(SERVER_V).unwrap();
    d.on_position_frame(
        &position_payload(
            "DU1234567",
            756733,
            "SPY",
            "STK",
            "ARCA",
            "USD",
            "100",
            "412.35",
        ),
        T0,
    )
    .unwrap();
    d.on_position_end_frame(&position_end_payload(), T0)
        .unwrap();

    d.on_disconnect();
    assert_eq!(
        d.summary_staleness(T0),
        SnapshotStaleness::DisconnectedStale
    );
    assert_eq!(
        d.positions_staleness(T0),
        SnapshotStaleness::DisconnectedStale
    );
    // 行保留供唯讀檢視(staleness 已明示不可信)。
    assert!(d.summary_rows().count() > 0);
    // 斷線後入站行 → NoActiveSubscription(訂閱不跨連線存活)。
    assert_eq!(
        d.on_account_summary_frame(
            &summary_payload(REQ_ID, "DU1", "NetLiquidation", "1", "USD"),
            T0
        )
        .unwrap_err(),
        AccountDataReject::NoActiveSubscription
    );
    // 重連後重訂閱 → 新快照世代,舊行清空。
    let seq = d.snapshot_seq();
    d.begin_account_summary(REQ_ID + 1).unwrap();
    assert_eq!(d.snapshot_seq(), seq + 1);
    assert_eq!(d.summary_rows().count(), 0);
    assert_eq!(
        d.summary_staleness(T0),
        SnapshotStaleness::SnapshotIncomplete
    );
}
