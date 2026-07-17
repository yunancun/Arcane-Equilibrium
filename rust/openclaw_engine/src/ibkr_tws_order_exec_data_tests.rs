//! W5-S3 open orders/executions/commissions 消化層測試（拆檔;主體
//! `ibkr_tws_order_exec_data.rs`,同 account_data/session/pacing/driver 範式）。純同步、
//! 注入時鐘（任意相對 ms,fixture 禁硬編日期）、零 socket、零 IO——inbound payload 以
//! wire `encode_fields` 合成。

use super::*;

use openclaw_types::IbkrCommissionsRowBlocker;

/// 測試用注入時鐘基準（任意相對值,非牆鐘）。
const T0: u64 = 20_000;
const REQ_ID: i64 = 9002;
/// pinned 上界內的 serverVersion（157 佈局精確欄長紀律域）。
const SV_PINNED: i32 = 157;
/// pinned 上界外的 serverVersion（ceiling 佈局窗域;引擎協商上限）。
const SV_CEILING: i32 = 176;

fn digest() -> OrderExecDataDigest {
    OrderExecDataDigest::new(OrderExecDataConfig::default())
}

/// 合法 grammar 的 exec_time fixture（相對樣式,非牆鐘依賴——grammar 只驗形不驗值）。
const EXEC_TIME_OK: &str = "20200102-13:30:05";

/// 合成 IN 11 execDetails payload（31 定長平面欄;`contract_exchange` 與 `exec_exchange`
/// 刻意可異值,驗 row 綁 Execution.exchange）。
#[allow(clippy::too_many_arguments)]
fn execution_payload(
    req_id: i64,
    order_id: i64,
    exec_id: &str,
    exec_time: &str,
    contract_exchange: &str,
    exec_exchange: &str,
    side: &str,
    shares: &str,
    price: &str,
) -> Vec<u8> {
    let rid = req_id.to_string();
    let oid = order_id.to_string();
    encode_fields(&[
        "11",
        &rid,
        &oid, // msgId, reqId, orderId
        // Contract: conId, symbol, secType, lastTradeDateOrContractMonth, strike, right,
        // multiplier, exchange, currency, localSymbol, tradingClass
        "756733",
        "SPY",
        "STK",
        "",
        "0",
        "",
        "",
        contract_exchange,
        "USD",
        "SPY",
        "SPY",
        // Execution: execId, time, acctNumber, exchange, side, shares, price, permId,
        // clientId, liquidation, cumQty, avgPrice, orderRef, evRule, evMultiplier,
        // modelCode, lastLiquidity
        exec_id,
        exec_time,
        "DU1234567",
        exec_exchange,
        side,
        shares,
        price,
        "1000001",
        "0",
        "0",
        shares,
        price,
        "",
        "",
        "",
        "",
        "1",
    ])
}

/// 合成 IN 55 execDetailsEnd payload。
fn execution_end_payload(req_id: i64) -> Vec<u8> {
    let rid = req_id.to_string();
    encode_fields(&["55", "1", &rid])
}

/// 合成 IN 59 commissionReport payload（8 定長平面欄）。
fn commission_payload(exec_id: &str, commission: &str, currency: &str, pnl: &str) -> Vec<u8> {
    encode_fields(&["59", "1", exec_id, commission, currency, pnl, "", ""])
}

/// 合成 IN 3 orderStatus payload（12 定長平面欄）。
fn order_status_payload(order_id: i64, status: &str, filled: &str, remaining: &str) -> Vec<u8> {
    let oid = order_id.to_string();
    encode_fields(&[
        "3", &oid, status, filled, remaining, "412.35", "1000001", "0", "412.35", "0", "", "412.35",
    ])
}

/// 合成 IN 5 openOrder payload（26 head 欄 + 可注入 tail;tail=ceiling/全欄尾模擬）。
fn open_order_payload(order_id: i64, action: &str, lmt: &str, tail: &[&str]) -> Vec<u8> {
    let oid = order_id.to_string();
    let mut fields: Vec<&str> = vec![
        "5",
        &oid, // msgId, orderId
        // Contract: conId, symbol, secType, lastTradeDateOrContractMonth, strike, right,
        // multiplier, exchange, currency, localSymbol, tradingClass
        "756733",
        "SPY",
        "STK",
        "",
        "0",
        "",
        "",
        "ARCA",
        "USD",
        "SPY",
        "SPY",
        // action, totalQuantity, orderType, lmtPrice, auxPrice, tif, ocaGroup, account,
        // openClose, origin, orderRef, clientId, permId
        action,
        "100",
        "LMT",
        lmt,
        "",
        "DAY",
        "",
        "DU1234567",
        "O",
        "0",
        "",
        "0",
        "1000001",
    ];
    fields.extend_from_slice(tail);
    encode_fields(&fields)
}

/// 已到 Live 的 executions 快照（begin → 一行 → End）。
fn live_executions(d: &mut OrderExecDataDigest, sv: i32) {
    d.begin_executions(sv, REQ_ID).unwrap();
    d.on_execution_frame(
        &execution_payload(
            REQ_ID,
            7,
            "0000e0d5.0001.01",
            EXEC_TIME_OK,
            "SMART",
            "ARCA",
            "BOT",
            "100",
            "412.35",
        ),
        T0,
    )
    .unwrap();
    d.on_execution_end_frame(&execution_end_payload(REQ_ID), T0 + 10)
        .unwrap();
}

// ===========================================================================
// (a) 出站 builder:IB pinned 欄位序（唯讀對賬請求;零下單/改單/撤單 builder）
// ===========================================================================

#[test]
fn outbound_builders_match_pinned_field_order() {
    // reqExecutions = [7, 3, reqId, clientId="0", 空 filter ×6]（恆空 filter 全量）。
    let fields = decode_fields(&encode_req_executions(9002)[4..]).unwrap();
    assert_eq!(
        fields,
        vec!["7", "3", "9002", "0", "", "", "", "", "", ""],
        "空 filter 全量(clientId 官方默認 0,time 恆空繞開格式分歧)"
    );
    // reqOpenOrders = [5, 1]。
    assert_eq!(
        decode_fields(&encode_req_open_orders()[4..]).unwrap(),
        vec!["5", "1"]
    );
    // reqAllOpenOrders = [16, 1]。
    assert_eq!(
        decode_fields(&encode_req_all_open_orders()[4..]).unwrap(),
        vec!["16", "1"]
    );
}

// ===========================================================================
// (b) floor/ceiling serverVersion guard（DIVERGENT-1,config 化）
// ===========================================================================

#[test]
fn floor_guard_blocks_whole_surface_below_145() {
    let mut d = digest();
    assert_eq!(
        d.begin_executions(144, REQ_ID).unwrap_err(),
        OrderExecDataReject::ServerVersionBelowFloor {
            server_version: 144,
            floor: 145
        }
    );
    assert_eq!(
        d.begin_open_orders(144).unwrap_err(),
        OrderExecDataReject::ServerVersionBelowFloor {
            server_version: 144,
            floor: 145
        }
    );
    // config 化下界:改 config → 行為變化（參數禁假功能）。
    let mut d = OrderExecDataDigest::new(OrderExecDataConfig {
        min_server_version_floor: 100,
        ..OrderExecDataConfig::default()
    });
    d.begin_executions(144, REQ_ID).unwrap();
}

#[test]
fn ceiling_extra_trailing_fields_rejected_with_audit_above_157() {
    // sv=176(>157):execution 32 欄(多 1)→ PinnedLayoutOverflow+audit,非斷線。
    let mut d = digest();
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    let mut payload = execution_payload(
        REQ_ID,
        7,
        "e1",
        EXEC_TIME_OK,
        "SMART",
        "ARCA",
        "BOT",
        "100",
        "412.35",
    );
    payload.extend_from_slice(b"surplus\0");
    assert_eq!(
        d.on_execution_frame(&payload, T0).unwrap_err(),
        OrderExecDataReject::PinnedLayoutOverflow { msg_id: 11 }
    );
    assert_eq!(d.audit().pinned_layout_overflow_rejects, 1);
    // 拒收該 frame 但不毒化(band 內佈局成長非資料謊言);槽仍可收合規 frame。
    assert_eq!(
        d.executions_staleness(T0),
        SnapshotStaleness::SnapshotIncomplete
    );
    // commission 9 欄(多 1)於 ceiling 域 → 同拒。
    let mut cpayload = commission_payload("e1", "1.25", "USD", "0");
    cpayload.extend_from_slice(b"surplus\0");
    assert_eq!(
        d.on_commission_frame(&cpayload, T0).unwrap_err(),
        OrderExecDataReject::PinnedLayoutOverflow { msg_id: 59 }
    );
    assert_eq!(d.audit().pinned_layout_overflow_rejects, 2);
    // **E2 F4**:overflow 拒收+audit 只在活躍窗口——斷線失效後同 frame → NoActiveContext
    //（計入 no_active_context_rejects),overflow 計數不動(未開消化窗口不做副作用)。
    d.on_disconnect();
    assert_eq!(
        d.on_execution_frame(&payload, T0).unwrap_err(),
        OrderExecDataReject::NoActiveContext
    );
    assert_eq!(
        d.audit().pinned_layout_overflow_rejects,
        2,
        "非活躍窗口不計 overflow"
    );
    assert_eq!(
        d.audit().no_active_context_rejects,
        1,
        "承接拒改計 no_active_context"
    );
}

#[test]
fn pinned_sv_extra_trailing_fields_are_wire_malformed() {
    // sv=157(pinned 內):多欄=wire 意外 → WireMalformed(沿 W5-S2 F2 精確欄長紀律)。
    let mut d = digest();
    d.begin_executions(SV_PINNED, REQ_ID).unwrap();
    let mut payload = execution_payload(
        REQ_ID,
        7,
        "e1",
        EXEC_TIME_OK,
        "SMART",
        "ARCA",
        "BOT",
        "100",
        "412.35",
    );
    payload.extend_from_slice(b"surplus\0");
    assert!(matches!(
        d.on_execution_frame(&payload, T0).unwrap_err(),
        OrderExecDataReject::WireMalformed(_)
    ));
    // orderStatus 13 欄(多 1)於 pinned 域 → 同紀律。
    let mut d2 = digest();
    d2.begin_open_orders(SV_PINNED).unwrap();
    let mut os = order_status_payload(7, "Submitted", "0", "100");
    os.extend_from_slice(b"surplus\0");
    assert!(matches!(
        d2.on_order_status_frame(&os, T0).unwrap_err(),
        OrderExecDataReject::WireMalformed(_)
    ));
    // 缺欄恆 WireMalformed(佈局只增不減;兩域一致)。
    let short = encode_fields(&["11", "9002", "7"]);
    assert!(matches!(
        d.on_execution_frame(&short, T0).unwrap_err(),
        OrderExecDataReject::WireMalformed(_)
    ));
}

// ===========================================================================
// (c) executions 快照 → End → unsolicited 推送;Execution.exchange 綁定
// ===========================================================================

#[test]
fn executions_snapshot_then_end_then_unsolicited_push() {
    let mut d = digest();
    assert_eq!(d.executions_staleness(T0), SnapshotStaleness::NotSubscribed);
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    assert_eq!(
        d.executions_staleness(T0),
        SnapshotStaleness::SnapshotIncomplete
    );
    // 兩個 exchange 欄異值:row 必綁 Execution.exchange(成交所)非 Contract.exchange。
    d.on_execution_frame(
        &execution_payload(
            REQ_ID,
            7,
            "e1",
            EXEC_TIME_OK,
            "SMART",
            "ARCA",
            "BOT",
            "100",
            "412.35",
        ),
        T0,
    )
    .unwrap();
    let (_, slot) = d.exec_slots(T0).1.next().unwrap();
    let row = slot.execution.as_ref().unwrap();
    assert_eq!(
        row.exchange, "ARCA",
        "exchange 必綁 Execution.exchange(idx 17),非 Contract.exchange(idx 10=SMART)"
    );
    assert_eq!(row.account_id, "DU1234567");
    assert_eq!(row.order_id, 7);
    assert_eq!(row.perm_id, 1_000_001);
    assert_eq!(row.exec_time, EXEC_TIME_OK);
    // End(reqId 對齊)→ Live。
    d.on_execution_end_frame(&execution_end_payload(REQ_ID), T0 + 10)
        .unwrap();
    assert_eq!(
        d.executions_staleness(T0 + 11),
        SnapshotStaleness::Fresh { as_of_ms: T0 + 10 }
    );
    // unsolicited 推送(reqId=-1 慣稱,無官方位元組證 → 承接+計數,禁丟棄)。
    d.on_execution_frame(
        &execution_payload(
            -1,
            8,
            "e2",
            EXEC_TIME_OK,
            "SMART",
            "NYSE",
            "SLD",
            "50",
            "413.00",
        ),
        T0 + 20,
    )
    .unwrap();
    assert_eq!(d.exec_slots(T0).1.count(), 2);
    assert_eq!(d.audit().unsolicited_execution_rows, 1);
    // 同 execId 重複行(快照/推送重疊):後到覆蓋+計數。
    d.on_execution_frame(
        &execution_payload(
            -1,
            8,
            "e2",
            EXEC_TIME_OK,
            "SMART",
            "NYSE",
            "SLD",
            "50",
            "413.00",
        ),
        T0 + 30,
    )
    .unwrap();
    assert_eq!(d.exec_slots(T0).1.count(), 2, "execId 去重:重複不增槽");
    assert_eq!(d.audit().duplicate_execution_rows, 1);
}

#[test]
fn execution_end_req_id_mismatch_rejected() {
    let mut d = digest();
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    assert_eq!(
        d.on_execution_end_frame(&execution_end_payload(REQ_ID + 5), T0)
            .unwrap_err(),
        OrderExecDataReject::UnexpectedReqId { got: REQ_ID + 5 }
    );
    assert_eq!(
        d.executions_staleness(T0),
        SnapshotStaleness::SnapshotIncomplete,
        "錯配 End 不得轉相位"
    );
}

#[test]
fn no_active_context_frames_rejected() {
    // 未 begin 任何請求:資料/End 全拒(未訂而收=協議意外;wire 形狀合法故非斷線)。
    let mut d = digest();
    assert_eq!(
        d.on_execution_frame(
            &execution_payload(
                REQ_ID,
                7,
                "e1",
                EXEC_TIME_OK,
                "SMART",
                "ARCA",
                "BOT",
                "100",
                "412.35"
            ),
            T0
        )
        .unwrap_err(),
        OrderExecDataReject::NoActiveContext
    );
    assert_eq!(
        d.on_commission_frame(&commission_payload("e1", "1.25", "USD", "0"), T0)
            .unwrap_err(),
        OrderExecDataReject::NoActiveContext
    );
    assert_eq!(
        d.on_order_status_frame(&order_status_payload(7, "Submitted", "0", "100"), T0)
            .unwrap_err(),
        OrderExecDataReject::NoActiveContext
    );
    assert_eq!(
        d.on_open_order_frame(&open_order_payload(7, "BUY", "412.00", &[]), T0)
            .unwrap_err(),
        OrderExecDataReject::NoActiveContext
    );
    assert_eq!(d.exec_slots(T0).1.count(), 0);
    assert_eq!(d.open_orders(T0).1.count(), 0);
    // **E2 F2**:承接拒逐 frame 計數(unsolicited 丟棄可觀測,非靜默)。
    assert_eq!(d.audit().no_active_context_rejects, 4);
}

#[test]
fn already_active_slots_are_structurally_limited() {
    let mut d = digest();
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    assert_eq!(
        d.begin_executions(SV_CEILING, REQ_ID + 1).unwrap_err(),
        OrderExecDataReject::ExecutionsAlreadyActive
    );
    d.begin_open_orders(SV_CEILING).unwrap();
    // reqOpenOrders 與 reqAllOpenOrders 共一槽:自限對兩形共同生效。
    assert_eq!(
        d.begin_all_open_orders(SV_CEILING).unwrap_err(),
        OrderExecDataReject::OpenOrdersAlreadyActive
    );
}

// ===========================================================================
// (d) exec_time grammar 白名單(row 級拒收+audit;config 真功能)
// ===========================================================================

#[test]
fn exec_time_grammar_whitelist_row_level_reject_with_audit() {
    let mut d = digest();
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    // 帶 TZ 後綴傳統形 → 白名單外,row 級拒收+audit 原字串(可重放),不毒化。
    let bad = "20200102-13:30:05 EST";
    assert_eq!(
        d.on_execution_frame(
            &execution_payload(REQ_ID, 7, "e1", bad, "SMART", "ARCA", "BOT", "100", "412.35"),
            T0
        )
        .unwrap_err(),
        OrderExecDataReject::ExecTimeGrammarRejected
    );
    assert_eq!(d.audit().exec_time_grammar_rejects, 1);
    assert_eq!(
        d.audit().exec_time_grammar_last_raw.as_deref(),
        Some(bad),
        "原字串記 audit 可重放"
    );
    assert_eq!(d.exec_slots(T0).1.count(), 0, "grammar 拒收行不併入");
    assert_eq!(
        d.executions_staleness(T0),
        SnapshotStaleness::SnapshotIncomplete,
        "row 級拒收不毒化(PM 裁決粒度=row)"
    );
    // 合法 UTC 形通過。
    d.on_execution_frame(
        &execution_payload(
            REQ_ID,
            7,
            "e1",
            EXEC_TIME_OK,
            "SMART",
            "ARCA",
            "BOT",
            "100",
            "412.35",
        ),
        T0,
    )
    .unwrap();
    // config 真功能:關掉白名單 → 合法形亦拒(fail-closed)。
    let mut d = OrderExecDataDigest::new(OrderExecDataConfig {
        accept_utc_compact_dash_hms: false,
        ..OrderExecDataConfig::default()
    });
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    assert_eq!(
        d.on_execution_frame(
            &execution_payload(
                REQ_ID,
                7,
                "e1",
                EXEC_TIME_OK,
                "SMART",
                "ARCA",
                "BOT",
                "100",
                "412.35"
            ),
            T0
        )
        .unwrap_err(),
        OrderExecDataReject::ExecTimeGrammarRejected
    );
}

// ===========================================================================
// (e) 契約 blocker=毒化(executions/commissions row validate())
// ===========================================================================

#[test]
fn execution_row_contract_blockers_poison_surface() {
    // 表外 side("BUY" 非 wire side 慣例;白名單=BOT/SLD)→ blocker → 毒化。
    let mut d = digest();
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    assert!(matches!(
        d.on_execution_frame(
            &execution_payload(
                REQ_ID,
                7,
                "e1",
                EXEC_TIME_OK,
                "SMART",
                "ARCA",
                "BUY",
                "100",
                "412.35"
            ),
            T0
        )
        .unwrap_err(),
        OrderExecDataReject::ExecutionRowBlocked(_)
    ));
    assert_eq!(d.executions_staleness(T0), SnapshotStaleness::Invalidated);
    // 毒化後 End 不得復活(NoActiveContext)。
    assert_eq!(
        d.on_execution_end_frame(&execution_end_payload(REQ_ID), T0)
            .unwrap_err(),
        OrderExecDataReject::NoActiveContext
    );
    // W6-S0 audit:blocker 身分落帳(count+最後樣本)。
    assert_eq!(d.audit().execution_row_blocked_rejects, 1);
    assert!(!d.audit().execution_row_last_blockers.is_empty());
    // W6-S0 恢復政策:毒化=世代內終態——同世代 re-begin 一律拒。
    assert_eq!(
        d.begin_executions(SV_CEILING, REQ_ID + 1).unwrap_err(),
        OrderExecDataReject::InvalidatedUntilNewGeneration
    );
    // 世代推進(新 handshake 成功)重評 → re-begin 恢復(新快照世代,舊槽清空)。
    d.on_new_connection_generation();
    assert_eq!(
        d.executions_staleness(T0),
        SnapshotStaleness::DisconnectedStale
    );
    let seq = d.snapshot_seq();
    d.begin_executions(SV_CEILING, REQ_ID + 1).unwrap();
    assert_eq!(d.snapshot_seq(), seq + 1);
    assert_eq!(d.exec_slots(T0).1.count(), 0);
}

#[test]
fn commission_row_contract_blockers_poison_surface() {
    // 表外幣別 EUR → CurrencyDenied blocker → 毒化。
    let mut d = digest();
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    let err = d
        .on_commission_frame(&commission_payload("e1", "1.25", "EUR", "0"), T0)
        .unwrap_err();
    match err {
        OrderExecDataReject::CommissionRowBlocked(blockers) => {
            assert!(blockers.contains(&IbkrCommissionsRowBlocker::CurrencyDenied));
        }
        e => panic!("應為 CommissionRowBlocked,得 {e:?}"),
    }
    assert_eq!(d.executions_staleness(T0), SnapshotStaleness::Invalidated);
}

// ===========================================================================
// (f) realizedPNL 哨兵雙判別 → None(移交 blocking #1)
// ===========================================================================

#[test]
fn realized_pnl_sentinel_double_test_maps_to_none() {
    let mut d = digest();
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    // 形態①:空欄 → None(誠實缺席,不計哨兵 audit)。
    d.on_commission_frame(&commission_payload("e1", "1.25", "USD", ""), T0)
        .unwrap();
    // 形態②:精確哨兵字串(小寫 e 驗大小寫不敏感)→ None+audit 記原始字串。
    d.on_commission_frame(
        &commission_payload("e2", "1.25", "USD", "1.7976931348623157e308"),
        T0,
    )
    .unwrap();
    // 形態③:量級哨兵(|v|≥1.0e308,含負側)→ None+audit。
    d.on_commission_frame(
        &commission_payload("e3", "1.25", "USD", "-1.7976931348623157E308"),
        T0,
    )
    .unwrap();
    let pnl_of = |d: &OrderExecDataDigest, id: &str| {
        d.exec_slots(T0)
            .1
            .find(|(k, _)| k.as_str() == id)
            .unwrap()
            .1
            .commission
            .as_ref()
            .unwrap()
            .realized_pnl_decimal
            .clone()
    };
    assert_eq!(pnl_of(&d, "e1"), None);
    assert_eq!(pnl_of(&d, "e2"), None);
    assert_eq!(pnl_of(&d, "e3"), None);
    assert_eq!(d.audit().realized_pnl_sentinel_hits, 2, "空欄不計哨兵");
    assert_eq!(
        d.audit().realized_pnl_sentinel_last_raw.as_deref(),
        Some("-1.7976931348623157E308")
    );
    // `0` 是合法實現損益 → 恆 Some("0"),禁折 0。
    d.on_commission_frame(&commission_payload("e4", "1.25", "USD", "0"), T0)
        .unwrap();
    assert_eq!(pnl_of(&d, "e4"), Some("0".to_string()));
    // 一般簽名值 → Some 保真。
    d.on_commission_frame(&commission_payload("e5", "1.25", "USD", "-12.50"), T0)
        .unwrap();
    assert_eq!(pnl_of(&d, "e5"), Some("-12.50".to_string()));
}

// ===========================================================================
// (g) exec↔commission either-order join(execId 鍵;孤兒 TTL 計量)
// ===========================================================================

#[test]
fn either_order_join_and_orphan_ttl_metering() {
    let mut d = digest();
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    // 亂序:commission 先到 → 孤兒緩存(禁丟棄)。
    d.on_commission_frame(&commission_payload("e1", "1.25", "USD", "0"), T0)
        .unwrap();
    let report = d.join_orphans(T0);
    assert_eq!(report.commissions_awaiting_execution, 1);
    assert_eq!(report.executions_awaiting_commission, 0);
    assert_eq!(d.completed_executions(T0).1.count(), 0);
    // execution 後到 → join 完整對=typed 完整成交紀錄。
    d.on_execution_frame(
        &execution_payload(
            REQ_ID,
            7,
            "e1",
            EXEC_TIME_OK,
            "SMART",
            "ARCA",
            "BOT",
            "100",
            "412.35",
        ),
        T0 + 5,
    )
    .unwrap();
    assert_eq!(d.completed_executions(T0).1.count(), 1);
    let (exec, comm) = d.completed_executions(T0).1.next().unwrap();
    assert_eq!(exec.exec_id, comm.exec_id);
    assert_eq!(d.join_orphans(T0 + 5), JoinOrphanReport::default());
    // 正序:execution 先到、commission 逾 TTL 未到 → over_ttl 計量(degraded 信號)。
    d.on_execution_frame(
        &execution_payload(
            REQ_ID,
            8,
            "e2",
            EXEC_TIME_OK,
            "SMART",
            "ARCA",
            "BOT",
            "50",
            "413.00",
        ),
        T0 + 10,
    )
    .unwrap();
    let report = d.join_orphans(T0 + 10 + 60_001);
    assert_eq!(report.executions_awaiting_commission, 1);
    assert_eq!(report.over_ttl, 1);
    // TTL config 真功能:縮短 TTL → 更早計 over_ttl。
    let mut d = OrderExecDataDigest::new(OrderExecDataConfig {
        join_orphan_ttl: Duration::from_secs(1),
        ..OrderExecDataConfig::default()
    });
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    d.on_commission_frame(&commission_payload("e9", "1.25", "USD", "0"), T0)
        .unwrap();
    assert_eq!(d.join_orphans(T0 + 1_001).over_ttl, 1);
}

// ===========================================================================
// (h) orderStatus:白名單/冪等去重/表外 UnknownDenied
// ===========================================================================

#[test]
fn order_status_whitelist_dedup_and_unknown_denied() {
    let mut d = digest();
    d.begin_open_orders(SV_CEILING).unwrap();
    d.on_order_status_frame(&order_status_payload(7, "Submitted", "0", "100"), T0)
        .unwrap();
    assert_eq!(d.order_statuses(T0).1.count(), 1);
    let row = d.order_statuses(T0).1.next().unwrap();
    assert_eq!(row.status, IbkrOrderStatusV1::Submitted);
    assert_eq!(row.filled_decimal, "0");
    // 官方明言常有重複 → 冪等去重(wire 事實全等:計數後 no-op,captured_at 不更新)。
    d.on_order_status_frame(&order_status_payload(7, "Submitted", "0", "100"), T0 + 5)
        .unwrap();
    assert_eq!(d.order_statuses(T0).1.count(), 1);
    assert_eq!(d.audit().duplicate_order_status_rows, 1);
    assert_eq!(d.order_statuses(T0).1.next().unwrap().captured_at_ms, T0);
    // 事實變化(Filled)→ 覆蓋非去重。
    d.on_order_status_frame(&order_status_payload(7, "Filled", "100", "0"), T0 + 9)
        .unwrap();
    assert_eq!(d.order_statuses(T0).1.count(), 1);
    assert_eq!(
        d.order_statuses(T0).1.next().unwrap().status,
        IbkrOrderStatusV1::Filled
    );
    // 表外 status(ApiPending 屬表外)→ UnknownDenied:audit 計數+毒化,不 crash。
    assert_eq!(
        d.on_order_status_frame(&order_status_payload(8, "ApiPending", "0", "100"), T0 + 10)
            .unwrap_err(),
        OrderExecDataReject::OrderStatusUnknownDenied
    );
    assert_eq!(d.audit().order_status_unknown_denied, 1);
    assert_eq!(d.open_orders_staleness(T0), SnapshotStaleness::Invalidated);
}

#[test]
fn order_status_bad_decimal_is_typed_denied() {
    let mut d = digest();
    d.begin_open_orders(SV_CEILING).unwrap();
    assert_eq!(
        d.on_order_status_frame(&order_status_payload(7, "Submitted", "1e5", "100"), T0)
            .unwrap_err(),
        OrderExecDataReject::OrderStatusFieldInvalid { field: "filled" }
    );
    assert_eq!(d.open_orders_staleness(T0), SnapshotStaleness::Invalidated);
}

// ===========================================================================
// (i) openOrder head-prefix 最小消化 + tail-discard + End 界定
// ===========================================================================

#[test]
fn open_order_head_prefix_digest_and_tail_discard() {
    let mut d = digest();
    d.begin_open_orders(SV_CEILING).unwrap();
    assert_eq!(
        d.open_orders_staleness(T0),
        SnapshotStaleness::SnapshotIncomplete
    );
    // head 26 欄+尾 3 欄(全欄 decode defer 域)→ head 消化,tail 整體丟棄+audit 計數。
    d.on_open_order_frame(
        &open_order_payload(7, "BUY", "412.00", &["tail_a", "tail_b", "tail_c"]),
        T0,
    )
    .unwrap();
    assert_eq!(d.audit().open_order_tail_fields_discarded, 3);
    let row = d.open_orders(T0).1.next().unwrap();
    assert_eq!(row.order_id, 7);
    assert_eq!(row.con_id, 756733);
    assert_eq!(row.action, IbkrOrderActionV1::Buy);
    assert_eq!(row.total_quantity_decimal, "100");
    assert_eq!(row.order_type, "LMT");
    assert_eq!(row.lmt_price_decimal, Some("412.00".to_string()));
    assert_eq!(row.aux_price_decimal, None, "空欄=unset → None(禁折 0)");
    assert_eq!(row.perm_id, 1_000_001);
    // End 界定 → Live。
    d.on_open_order_end_frame(&encode_fields(&["53", "1"]), T0 + 5)
        .unwrap();
    assert_eq!(
        d.open_orders_staleness(T0 + 6),
        SnapshotStaleness::Fresh { as_of_ms: T0 + 5 }
    );
    // head 欄不足 → WireMalformed(缺欄=損壞)。
    assert!(matches!(
        d.on_open_order_frame(&encode_fields(&["5", "7", "756733", "SPY"]), T0)
            .unwrap_err(),
        OrderExecDataReject::WireMalformed(_)
    ));
}

#[test]
fn open_order_head_denied_fields_poison_surface() {
    // 表外 action → 毒化。
    let mut d = digest();
    d.begin_open_orders(SV_CEILING).unwrap();
    assert_eq!(
        d.on_open_order_frame(&open_order_payload(7, "SSHORT", "412.00", &[]), T0)
            .unwrap_err(),
        OrderExecDataReject::OpenOrderHeadDenied { field: "action" }
    );
    assert_eq!(d.open_orders_staleness(T0), SnapshotStaleness::Invalidated);
    // 非法 lmtPrice 形狀 → 毒化(非空必為簽名定點字串)。
    let mut d = digest();
    d.begin_open_orders(SV_CEILING).unwrap();
    assert_eq!(
        d.on_open_order_frame(&open_order_payload(7, "BUY", "abc", &[]), T0)
            .unwrap_err(),
        OrderExecDataReject::OpenOrderHeadDenied { field: "lmt_price" }
    );
    assert_eq!(d.open_orders_staleness(T0), SnapshotStaleness::Invalidated);
}

// ===========================================================================
// (j) staleness 窗 + 斷線 resync
// ===========================================================================

#[test]
fn executions_staleness_goes_stale_after_config_window() {
    let mut d = digest();
    live_executions(&mut d, SV_CEILING);
    let last = T0 + 10;
    assert!(matches!(
        d.executions_staleness(last + 390_000),
        SnapshotStaleness::Fresh { .. }
    ));
    match d.executions_staleness(last + 390_001) {
        SnapshotStaleness::Stale { as_of_ms, age_ms } => {
            assert_eq!(as_of_ms, last);
            assert_eq!(age_ms, 390_001);
        }
        s => panic!("應為 Stale,得 {s:?}"),
    }
    // config 真功能:縮窗 → 更早 Stale。
    let mut d = OrderExecDataDigest::new(OrderExecDataConfig {
        executions_stale_after: Duration::from_secs(1),
        ..OrderExecDataConfig::default()
    });
    live_executions(&mut d, SV_CEILING);
    assert!(matches!(
        d.executions_staleness(T0 + 10 + 1_001),
        SnapshotStaleness::Stale { .. }
    ));
}

#[test]
fn disconnect_marks_stale_and_rebegin_resyncs() {
    let mut d = digest();
    live_executions(&mut d, SV_CEILING);
    d.begin_open_orders(SV_CEILING).unwrap();
    d.on_open_order_frame(&open_order_payload(7, "BUY", "412.00", &[]), T0)
        .unwrap();
    d.on_open_order_end_frame(&encode_fields(&["53", "1"]), T0)
        .unwrap();

    d.on_disconnect();
    assert_eq!(
        d.executions_staleness(T0),
        SnapshotStaleness::DisconnectedStale
    );
    assert_eq!(
        d.open_orders_staleness(T0),
        SnapshotStaleness::DisconnectedStale
    );
    // 行保留供唯讀檢視(staleness 已明示不可信)。
    assert_eq!(d.exec_slots(T0).1.count(), 1);
    assert_eq!(d.open_orders(T0).1.count(), 1);
    // 斷線後入站 → NoActiveContext(快照/推送不跨連線存活)。
    assert_eq!(
        d.on_execution_frame(
            &execution_payload(
                -1,
                9,
                "e9",
                EXEC_TIME_OK,
                "SMART",
                "ARCA",
                "BOT",
                "10",
                "1.00"
            ),
            T0
        )
        .unwrap_err(),
        OrderExecDataReject::NoActiveContext
    );
    // 斷線 resync:re-begin → 新快照世代、舊槽清空、全量重取(execId 去重吸收重疊)。
    let seq = d.snapshot_seq();
    d.begin_executions(SV_CEILING, REQ_ID + 1).unwrap();
    assert_eq!(d.snapshot_seq(), seq + 1);
    assert_eq!(d.exec_slots(T0).1.count(), 0);
    assert_eq!(
        d.executions_staleness(T0),
        SnapshotStaleness::SnapshotIncomplete
    );
    let seq = d.snapshot_seq();
    d.begin_all_open_orders(SV_CEILING).unwrap();
    assert_eq!(d.snapshot_seq(), seq + 1);
    assert_eq!(d.open_orders(T0).1.count(), 0);
    assert_eq!(d.order_statuses(T0).1.count(), 0);
}

// ===========================================================================
// (k) wire 損壞 typed(欄缺/非數字/錯 msgId → WireMalformed,呼叫端斷線)
// ===========================================================================

#[test]
fn wire_malformed_frames_are_typed() {
    let mut d = digest();
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    // reqId 非數字 → WireMalformed(禁 unwrap_or(0) 捏造;N1 紀律:先於訂閱狀態裁決——
    // 未 begin 的 digest 同樣回 WireMalformed)。
    let mut bad = execution_payload(
        REQ_ID,
        7,
        "e1",
        EXEC_TIME_OK,
        "SMART",
        "ARCA",
        "BOT",
        "100",
        "412.35",
    );
    // 以 fields 重組替換 reqId 為非數字。
    bad = {
        let mut fields = decode_fields(&bad).unwrap();
        fields[1] = "abc".to_string();
        let refs: Vec<&str> = fields.iter().map(String::as_str).collect();
        encode_fields(&refs)
    };
    assert!(matches!(
        d.on_execution_frame(&bad, T0).unwrap_err(),
        OrderExecDataReject::WireMalformed(_)
    ));
    // 未 begin 的 digest:同 payload 仍 WireMalformed(wire 形狀先裁,非 NoActiveContext 靜默)。
    let mut idle = digest();
    assert!(matches!(
        idle.on_execution_frame(&bad, T0).unwrap_err(),
        OrderExecDataReject::WireMalformed(_)
    ));
    // 錯 msgId(64 的 payload 餵 55 入口)→ WireMalformed(不容錯位)。
    assert!(matches!(
        d.on_execution_end_frame(&encode_fields(&["64", "1", "9002"]), T0)
            .unwrap_err(),
        OrderExecDataReject::WireMalformed(_)
    ));
    // commission version 非數字 → WireMalformed。
    assert!(matches!(
        d.on_commission_frame(
            &encode_fields(&["59", "x", "e1", "1.25", "USD", "0", "", ""]),
            T0
        )
        .unwrap_err(),
        OrderExecDataReject::WireMalformed(_)
    ));
}

// ===========================================================================
// (l) W6-S0:恢復政策(世代內終態) / staleness 綁定視圖 / audit 樣本欄 / cap
// ===========================================================================

#[test]
fn w6s0_invalidated_open_orders_face_is_terminal_within_generation() {
    // open-orders 面毒化(表外 status)→ 同世代 re-begin 拒(兩形共同);斷線不沖淡;
    // 世代推進後恢復。
    let mut d = digest();
    d.begin_open_orders(SV_CEILING).unwrap();
    let _ = d.on_order_status_frame(&order_status_payload(7, "ApiPending", "0", "100"), T0);
    assert_eq!(d.open_orders_staleness(T0), SnapshotStaleness::Invalidated);
    assert_eq!(
        d.begin_open_orders(SV_CEILING).unwrap_err(),
        OrderExecDataReject::InvalidatedUntilNewGeneration
    );
    assert_eq!(
        d.begin_all_open_orders(SV_CEILING).unwrap_err(),
        OrderExecDataReject::InvalidatedUntilNewGeneration
    );
    d.on_disconnect();
    assert_eq!(d.open_orders_staleness(T0), SnapshotStaleness::Invalidated);
    assert_eq!(
        d.begin_open_orders(SV_CEILING).unwrap_err(),
        OrderExecDataReject::InvalidatedUntilNewGeneration
    );
    // 世代推進 → DisconnectedStale → re-begin 成功。
    d.on_new_connection_generation();
    assert_eq!(
        d.open_orders_staleness(T0),
        SnapshotStaleness::DisconnectedStale
    );
    d.begin_open_orders(SV_CEILING).unwrap();
    assert_eq!(
        d.open_orders_staleness(T0),
        SnapshotStaleness::SnapshotIncomplete
    );
}

#[test]
fn w6s0_staleness_bound_views_expose_face_staleness() {
    // 綁定視圖:四個視圖各與其面 staleness 恆等(單一真源投影;部分快照必先見弱態)。
    let mut d = digest();
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    d.on_execution_frame(
        &execution_payload(
            REQ_ID,
            7,
            "e1",
            EXEC_TIME_OK,
            "SMART",
            "ARCA",
            "BOT",
            "100",
            "412.35",
        ),
        T0,
    )
    .unwrap();
    // End 前:槽已有行,視圖同步標 SnapshotIncomplete。
    let (staleness, slots) = d.exec_slots(T0);
    assert_eq!(staleness, SnapshotStaleness::SnapshotIncomplete);
    assert_eq!(slots.count(), 1);
    assert_eq!(d.completed_executions(T0).0, d.executions_staleness(T0));
    assert_eq!(d.open_orders(T0).0, d.open_orders_staleness(T0));
    assert_eq!(d.order_statuses(T0).0, d.open_orders_staleness(T0));
}

#[test]
fn w6s0_audit_records_per_face_blocker_samples() {
    // commissions 契約 blocker → per-face 樣本欄。
    let mut d = digest();
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    let _ = d.on_commission_frame(&commission_payload("e1", "1.25", "EUR", "0"), T0);
    assert_eq!(d.audit().commission_row_blocked_rejects, 1);
    assert!(d
        .audit()
        .commission_row_last_blockers
        .contains(&IbkrCommissionsRowBlocker::CurrencyDenied));
    // orderStatus decimal 紀律拒 → 欄名樣本。
    let mut d = digest();
    d.begin_open_orders(SV_CEILING).unwrap();
    let _ = d.on_order_status_frame(&order_status_payload(7, "Submitted", "1e5", "100"), T0);
    assert_eq!(d.audit().order_status_field_invalid_rejects, 1);
    assert_eq!(d.audit().order_status_field_last, Some("filled"));
    // openOrder head 拒 → 欄名樣本。
    let mut d = digest();
    d.begin_open_orders(SV_CEILING).unwrap();
    let _ = d.on_open_order_frame(&open_order_payload(7, "SSHORT", "412.00", &[]), T0);
    assert_eq!(d.audit().open_order_head_denied_rejects, 1);
    assert_eq!(d.audit().open_order_head_last_field, Some("action"));
    // End reqId 錯配 → unexpected_req_id_rejects;wire 損壞 → 計數+typed note。
    let mut d = digest();
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    let _ = d.on_execution_end_frame(&execution_end_payload(REQ_ID + 9), T0);
    assert_eq!(d.audit().unexpected_req_id_rejects, 1);
    let _ = d.on_execution_end_frame(&encode_fields(&["55", "1"]), T0);
    assert_eq!(d.audit().wire_malformed_rejects, 1);
    assert!(d.audit().wire_malformed_last_note.is_some());
}

#[test]
fn w6s0_exec_join_slot_cap_poisons_face_no_silent_eviction() {
    // cap=1:第二個新 execId(不論 execution/commission 側先到)→ CacheCapExceeded+毒化;
    // 既有鍵補側/覆蓋不受 cap 限(join 不增長)。
    let mut d = OrderExecDataDigest::new(OrderExecDataConfig {
        max_exec_join_slots: 1,
        ..OrderExecDataConfig::default()
    });
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    d.on_execution_frame(
        &execution_payload(
            REQ_ID,
            7,
            "e1",
            EXEC_TIME_OK,
            "SMART",
            "ARCA",
            "BOT",
            "100",
            "412.35",
        ),
        T0,
    )
    .unwrap();
    // 同 execId commission 補側:cap 邊界上仍允許(join 完整化非注入)。
    d.on_commission_frame(&commission_payload("e1", "1.25", "USD", "0"), T0 + 1)
        .unwrap();
    // 新 execId 超界(commission 孤兒側)→ 毒化非驅逐。
    assert_eq!(
        d.on_commission_frame(&commission_payload("e2", "1.25", "USD", "0"), T0 + 2)
            .unwrap_err(),
        OrderExecDataReject::CacheCapExceeded {
            cache: "exec_join_slots"
        }
    );
    assert_eq!(d.exec_slots(T0 + 2).0, SnapshotStaleness::Invalidated);
    assert_eq!(d.exec_slots(T0 + 2).1.count(), 1, "禁靜默驅逐:舊槽保留");
    assert_eq!(d.audit().cache_cap_exceeded_rejects, 1);
    // execution 側新 execId 超界同紀律。
    let mut d = OrderExecDataDigest::new(OrderExecDataConfig {
        max_exec_join_slots: 1,
        ..OrderExecDataConfig::default()
    });
    d.begin_executions(SV_CEILING, REQ_ID).unwrap();
    d.on_execution_frame(
        &execution_payload(
            REQ_ID,
            7,
            "e1",
            EXEC_TIME_OK,
            "SMART",
            "ARCA",
            "BOT",
            "100",
            "412.35",
        ),
        T0,
    )
    .unwrap();
    assert_eq!(
        d.on_execution_frame(
            &execution_payload(
                REQ_ID,
                8,
                "e2",
                EXEC_TIME_OK,
                "SMART",
                "NYSE",
                "BOT",
                "50",
                "411.00",
            ),
            T0 + 1,
        )
        .unwrap_err(),
        OrderExecDataReject::CacheCapExceeded {
            cache: "exec_join_slots"
        }
    );
    assert_eq!(d.audit().cache_cap_exceeded_rejects, 1);
}

#[test]
fn w6s0_open_orders_and_order_statuses_caps_poison_face() {
    // order_statuses cap=1:第二個新 orderId → 毒化;冪等去重/同鍵更新不受 cap 限。
    let mut d = OrderExecDataDigest::new(OrderExecDataConfig {
        max_order_statuses: 1,
        ..OrderExecDataConfig::default()
    });
    d.begin_open_orders(SV_CEILING).unwrap();
    d.on_order_status_frame(&order_status_payload(7, "Submitted", "0", "100"), T0)
        .unwrap();
    // 同鍵事實更新:允許(不增長)。
    d.on_order_status_frame(&order_status_payload(7, "Filled", "100", "0"), T0 + 1)
        .unwrap();
    assert_eq!(
        d.on_order_status_frame(&order_status_payload(8, "Submitted", "0", "100"), T0 + 2)
            .unwrap_err(),
        OrderExecDataReject::CacheCapExceeded {
            cache: "order_statuses"
        }
    );
    assert_eq!(d.order_statuses(T0 + 2).0, SnapshotStaleness::Invalidated);
    assert_eq!(d.order_statuses(T0 + 2).1.count(), 1, "禁靜默驅逐");
    assert_eq!(d.audit().cache_cap_exceeded_rejects, 1);
    // open_orders cap=1:第二個新 orderId → 毒化。
    let mut d = OrderExecDataDigest::new(OrderExecDataConfig {
        max_open_orders: 1,
        ..OrderExecDataConfig::default()
    });
    d.begin_open_orders(SV_CEILING).unwrap();
    d.on_open_order_frame(&open_order_payload(7, "BUY", "412.00", &[]), T0)
        .unwrap();
    assert_eq!(
        d.on_open_order_frame(&open_order_payload(8, "BUY", "411.00", &[]), T0 + 1)
            .unwrap_err(),
        OrderExecDataReject::CacheCapExceeded {
            cache: "open_orders"
        }
    );
    assert_eq!(d.open_orders(T0 + 1).0, SnapshotStaleness::Invalidated);
    assert_eq!(d.open_orders(T0 + 1).1.count(), 1, "禁靜默驅逐");
    assert_eq!(d.audit().cache_cap_exceeded_rejects, 1);
}

// ── W7-S1 openOrder whatIf OrderState tail decode（§2.2.2）────────────────────

/// whatIf OrderState 尾 fixture（15 欄:status/9 margin/3 commission/currency/warning）。
const WHATIF_TAIL: &[&str] = &[
    "PreSubmitted", // status
    "1000.00",      // initMarginBefore
    "900.00",       // maintMarginBefore
    "5000.00",      // equityWithLoanBefore
    "50.00",        // initMarginChange
    "40.00",        // maintMarginChange
    "0.00",         // equityWithLoanChange
    "1050.00",      // initMarginAfter
    "940.00",       // maintMarginAfter
    "5000.00",      // equityWithLoanAfter
    "1.00",         // commission
    "1.00",         // minCommission
    "1.00",         // maxCommission
    "USD",          // commissionCurrency
    "",             // warningText
];

#[test]
fn whatif_tail_decode_pinned_band_ok() {
    let payload = open_order_payload(7, "BUY", "412.00", WHATIF_TAIL);
    let cfg = OrderExecDataConfig::default();
    let preview = decode_open_order_whatif_tail(&payload, SV_PINNED, &cfg).expect("decode tail");
    assert_eq!(preview.status, IbkrOrderStatusV1::PreSubmitted);
    assert_eq!(
        preview.init_margin_after_decimal.as_deref(),
        Some("1050.00")
    );
    assert_eq!(preview.commission_decimal.as_deref(), Some("1.00"));
    assert_eq!(preview.commission_currency, "USD");
    assert_eq!(preview.warning_text, "");
}

#[test]
fn whatif_tail_margin_sentinel_maps_to_none() {
    // 空欄 + f64::MAX 哨兵 → None（unset;沿 realizedPNL 哨兵紀律）。
    let mut tail: Vec<&str> = WHATIF_TAIL.to_vec();
    tail[7] = ""; // initMarginAfter 空欄
    tail[10] = "1.7976931348623157E308"; // commission 哨兵
    let payload = open_order_payload(7, "BUY", "412.00", &tail);
    let cfg = OrderExecDataConfig::default();
    let preview = decode_open_order_whatif_tail(&payload, SV_PINNED, &cfg).unwrap();
    assert_eq!(preview.init_margin_after_decimal, None);
    assert_eq!(preview.commission_decimal, None);
}

#[test]
fn whatif_tail_refuses_above_ceiling() {
    // §11 BLOCK-ORDER-BAND-3:sv>157 whatIf 尾 UNVERIFIED → 拒解不猜。
    let payload = open_order_payload(7, "BUY", "412.00", WHATIF_TAIL);
    let cfg = OrderExecDataConfig::default();
    assert_eq!(
        decode_open_order_whatif_tail(&payload, SV_CEILING, &cfg).unwrap_err(),
        OrderExecDataReject::PinnedLayoutOverflow {
            msg_id: IN_OPEN_ORDER_MSG_ID
        }
    );
}

#[test]
fn whatif_tail_rejects_short_frame_and_bad_decimal_and_status() {
    let cfg = OrderExecDataConfig::default();
    // 缺 OrderState 尾（head-only）→ WireMalformed。
    let head_only = open_order_payload(7, "BUY", "412.00", &[]);
    assert!(matches!(
        decode_open_order_whatif_tail(&head_only, SV_PINNED, &cfg).unwrap_err(),
        OrderExecDataReject::WireMalformed(_)
    ));
    // 非法 margin decimal → WhatIfPreviewFieldInvalid。
    let mut bad = WHATIF_TAIL.to_vec();
    bad[1] = "not_a_number";
    let payload = open_order_payload(7, "BUY", "412.00", &bad);
    assert_eq!(
        decode_open_order_whatif_tail(&payload, SV_PINNED, &cfg).unwrap_err(),
        OrderExecDataReject::WhatIfPreviewFieldInvalid {
            field: "init_margin_before"
        }
    );
    // 表外 status → OrderStatusUnknownDenied（含 ApiPending 亦落此——orderStatus 面白名單;
    // 但 lifecycle 的 ApiPending 態分流在 lifecycle driver,見該模塊）。
    let mut unk = WHATIF_TAIL.to_vec();
    unk[0] = "ApiPending";
    let payload = open_order_payload(7, "BUY", "412.00", &unk);
    assert_eq!(
        decode_open_order_whatif_tail(&payload, SV_PINNED, &cfg).unwrap_err(),
        OrderExecDataReject::OrderStatusUnknownDenied
    );
}
