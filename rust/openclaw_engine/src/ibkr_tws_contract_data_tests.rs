//! W6-S1 contract details 消化層單元測試（拆檔;主體 + 測試分檔,同 account_data/order_exec
//! 範式）。synthetic payload、注入時鐘、零 socket、fixture 禁硬編當前日期。

use super::*;

use crate::ibkr_tws_wire::encode_fields;
use openclaw_types::is_sha256_hex;

/// 測試固定 reqId（與 driver `CONTRACT_DETAILS_REQ_ID` 同值域,本檔獨立常數不跨檔耦合）。
const REQ_ID: i64 = 9003;
/// 注入時鐘基準（相對時鐘,無牆鐘依賴）。
const NOW: u64 = 1_000;

fn spy_query() -> ContractDetailsQuery {
    ContractDetailsQuery {
        con_id: None,
        symbol: "SPY".to_string(),
        exchange: "SMART".to_string(),
        primary_exchange: "ARCA".to_string(),
    }
}

/// 按 per-field sv 表組一筆 happy SPY contractData 欄序（IB 現勘 2026-07-17 pinned;
/// version 欄恆 "8",門控尾段依 sv 出現/缺席——與消化端同表,fake-TWS 另備獨立編碼）。
fn spy_fields(sv: i32, req_id: i64) -> Vec<String> {
    let mut f: Vec<String> = vec![
        "10".into(),
        "8".into(),
        req_id.to_string(),
        // head 1-29
        "SPY".into(),    // 1 symbol
        "STK".into(),    // 2 secType
        "".into(),       // 3 lastTradeDateOrContractMonth
        "0".into(),      // 4 strike
        "".into(),       // 5 right
        "SMART".into(),  // 6 exchange
        "USD".into(),    // 7 currency
        "SPY".into(),    // 8 localSymbol
        "SPY".into(),    // 9 marketName
        "SPY".into(),    // 10 tradingClass
        "756733".into(), // 11 conId
        "0.01".into(),   // 12 minTick
    ];
    if sv >= 110 {
        f.push("100".into()); // 13 mdSizeMultiplier
    }
    f.extend([
        "".into(),                            // 14 multiplier
        "LMT,MKT".into(),                     // 15 orderTypes
        "SMART,ARCA".into(),                  // 16 validExchanges
        "1".into(),                           // 17 priceMagnifier
        "0".into(),                           // 18 underConId
        "SPDR S&P 500 ETF TRUST".into(),      // 19 longName
        "ARCA".into(),                        // 20 primaryExchange
        "".into(),                            // 21 contractMonth
        "Funds".into(),                       // 22 industry
        "".into(),                            // 23 category
        "".into(),                            // 24 subcategory
        "US/Eastern".into(),                  // 25 timeZoneId(legacy 名保真)
        "20260102:0400-20260102:2000".into(), // 26 tradingHours
        "20260102:0930-20260102:1600".into(), // 27 liquidHours
        "".into(),                            // 28 evRule
        "0".into(),                           // 29 evMultiplier
        // 30 secIdList:count=2 + 兩對 (tag,value)
        "2".into(),
        "ISIN".into(),
        "US78462F1030".into(),
        "CUSIP".into(),
        "78462F103".into(),
    ]);
    if sv >= 121 {
        f.push("1".into()); // 31 aggGroup
    }
    if sv >= 122 {
        f.push("".into()); // 32 underSymbol
        f.push("".into()); // 33 underSecType
    }
    if sv >= 126 {
        f.push("26,26".into()); // 34 marketRuleIds
    }
    if sv >= 134 {
        f.push("".into()); // 35 realExpirationDate
    }
    if sv >= 152 {
        f.push("ETF".into()); // 36 stockType
    }
    f
}

fn payload_of(fields: &[String]) -> Vec<u8> {
    let refs: Vec<&str> = fields.iter().map(String::as_str).collect();
    encode_fields(&refs)
}

fn end_payload(req_id: i64) -> Vec<u8> {
    encode_fields(&["52", "1", &req_id.to_string()])
}

/// begin 到在途的 digest（happy 前置）。
fn begun(sv: i32) -> ContractDataDigest {
    let mut d = ContractDataDigest::new(ContractDataConfig::default());
    d.begin_contract_details(sv, REQ_ID, &spy_query(), NOW)
        .expect("begin 應成功");
    d
}

// ===========================================================================
// (a) OUT v8 builder + 全限定義務
// ===========================================================================

#[test]
fn builder_produces_pinned_v8_field_order() {
    let frame = encode_req_contract_details(REQ_ID, &spy_query());
    // unframe(4-byte len prefix)後解欄。
    let fields = decode_fields(&frame[4..]).unwrap();
    assert_eq!(
        fields,
        vec![
            "9", "8", "9003", "0", "SPY", "STK", "", "0", "", "", "SMART", "ARCA", "USD", "", "",
            "0", "", ""
        ],
        "v8 欄序:msgId,version,reqId + 15 body(includeExpired 恆 0/secType 恆 STK/currency 恆 USD)"
    );
    // conId 直查形:conId 上 wire,symbol 可空。
    let q = ContractDetailsQuery {
        con_id: Some(756733),
        symbol: String::new(),
        exchange: String::new(),
        primary_exchange: String::new(),
    };
    let fields = decode_fields(&encode_req_contract_details(REQ_ID, &q)[4..]).unwrap();
    assert_eq!(fields[3], "756733");
}

#[test]
fn begin_guards_floor_slot_qualification_and_generation_policy() {
    let mut d = ContractDataDigest::new(ContractDataConfig::default());
    // floor:sv<145 → 整面拒開。
    assert_eq!(
        d.begin_contract_details(144, REQ_ID, &spy_query(), NOW),
        Err(ContractDataReject::ServerVersionBelowFloor {
            server_version: 144,
            floor: 145
        })
    );
    // 全限定義務:無 conId 且 symbol/exchange 不全 → 拒發（模糊查詢=伺服端 hold 面）。
    for bad in [
        ContractDetailsQuery {
            con_id: None,
            symbol: String::new(),
            exchange: "SMART".into(),
            primary_exchange: String::new(),
        },
        ContractDetailsQuery {
            con_id: None,
            symbol: "spy".into(), // 非規範化
            exchange: "SMART".into(),
            primary_exchange: String::new(),
        },
        ContractDetailsQuery {
            con_id: None,
            symbol: "SPY".into(),
            exchange: "  ".into(),
            primary_exchange: String::new(),
        },
        ContractDetailsQuery {
            con_id: Some(0), // 非正 conId 不算全限定
            symbol: String::new(),
            exchange: String::new(),
            primary_exchange: String::new(),
        },
    ] {
        assert_eq!(
            d.begin_contract_details(157, REQ_ID, &bad, NOW),
            Err(ContractDataReject::QueryNotFullyQualified),
            "query {bad:?} 應拒"
        );
    }
    // 單槽自限:在途再 begin → 拒。
    assert!(d
        .begin_contract_details(157, REQ_ID, &spy_query(), NOW)
        .is_ok());
    assert_eq!(
        d.begin_contract_details(157, REQ_ID + 1, &spy_query(), NOW),
        Err(ContractDataReject::RequestAlreadyActive)
    );
}

// ===========================================================================
// (d) IN 10 decode:happy / version pin / per-field sv 表 / secIdList / ceiling
// ===========================================================================

#[test]
fn happy_row_digests_with_minted_identity_hash_and_end_goes_live() {
    let mut d = begun(157);
    assert_eq!(
        d.identity_staleness(NOW),
        SnapshotStaleness::SnapshotIncomplete
    );
    d.on_contract_data_frame(&payload_of(&spy_fields(157, REQ_ID)), NOW)
        .expect("happy 行應消化");
    d.on_contract_data_end_frame(&end_payload(REQ_ID), NOW)
        .expect("End 應轉 Live");
    let (staleness, mut rows) = d.identity_rows(NOW);
    assert_eq!(staleness, SnapshotStaleness::Fresh { as_of_ms: NOW });
    let row = rows.next().expect("應有 1 行");
    assert_eq!(row.con_id, 756733);
    assert_eq!(row.symbol, "SPY");
    assert_eq!(row.sec_type, IbkrSecTypeV1::Stk);
    assert_eq!(row.stock_type, IbkrStockTypeV1::Etf);
    assert_eq!(row.primary_exchange, "ARCA");
    assert_eq!(row.min_tick_decimal, "0.01");
    assert_eq!(row.time_zone_id, "US/Eastern", "legacy 時區名原字串保真");
    assert_eq!(row.snapshot_seq, 1);
    // identity_hash:PIT 可重建——以同 row 的 preimage 重算必逐位一致。
    assert!(is_sha256_hex(&row.identity_hash));
    assert_eq!(row.identity_hash, compute_identity_hash(row));
    assert!(rows.next().is_none());
    // 契約 validate(now) 全綠(先契約後消化的閉環自證)。
    assert!(row.validate(NOW).accepted);
}

#[test]
fn message_version_pin_rejects_non_v8_and_poisons() {
    let mut d = begun(157);
    let mut f = spy_fields(157, REQ_ID);
    f[1] = "7".into();
    assert_eq!(
        d.on_contract_data_frame(&payload_of(&f), NOW),
        Err(ContractDataReject::MessageVersionUnpinned { got: 7 })
    );
    assert_eq!(d.identity_staleness(NOW), SnapshotStaleness::Invalidated);
    assert_eq!(d.audit().message_version_unpinned_rejects, 1);
    assert_eq!(d.audit().message_version_last_got, Some(7));
    // 毒化=世代內終態:同世代 re-begin 拒。
    assert_eq!(
        d.begin_contract_details(157, REQ_ID, &spy_query(), NOW),
        Err(ContractDataReject::InvalidatedUntilNewGeneration)
    );
}

#[test]
fn per_field_sv_table_gates_stock_type_at_152() {
    // sv=151:stockType 欄缺席——decode 形狀正確(不 WireMalformed),但 lane 的 ETF|COMMON
    // 判別義務不可未知即過 → 契約 StockTypeUnknownDenied blocker → 毒化。
    let mut d = begun(151);
    let err = d
        .on_contract_data_frame(&payload_of(&spy_fields(151, REQ_ID)), NOW)
        .unwrap_err();
    match err {
        ContractDataReject::IdentityRowBlocked(blockers) => {
            assert_eq!(
                blockers,
                vec![IbkrInstrumentIdentityRowBlocker::StockTypeUnknownDenied],
                "sv<152 缺席應恰觸 stockType blocker(其餘欄按 151 表對位消費)"
            );
        }
        other => panic!("應為 IdentityRowBlocked,得 {other:?}"),
    }
    assert_eq!(d.identity_staleness(NOW), SnapshotStaleness::Invalidated);
    assert_eq!(
        d.audit().identity_row_last_blockers,
        vec![IbkrInstrumentIdentityRowBlocker::StockTypeUnknownDenied]
    );
    // sv=152:同邏輯行帶 stockType → 接受(門控表兩側對照)。
    let mut d = begun(152);
    d.on_contract_data_frame(&payload_of(&spy_fields(152, REQ_ID)), NOW)
        .expect("sv=152 應消化");
    assert_eq!(d.identity_rows(NOW).1.count(), 1);
}

#[test]
fn per_field_sv_table_gates_mid_band_tail_fields() {
    // sv=145(floor 恰好):121/122/126/134/152 門控欄全缺席——per-field 表必須按位少消費,
    // 否則錯位成 WireMalformed。行仍因 stockType 缺席走契約拒(非形狀拒=表正確的證明)。
    let mut d = begun(145);
    let err = d
        .on_contract_data_frame(&payload_of(&spy_fields(145, REQ_ID)), NOW)
        .unwrap_err();
    assert!(
        matches!(err, ContractDataReject::IdentityRowBlocked(_)),
        "145 佈局須按表對位消費(得 {err:?})"
    );
}

#[test]
fn sec_id_list_bounded_skip_and_absurd_count_rejected() {
    // count=0:合法(無 secId)。
    let mut d = begun(157);
    let mut f = spy_fields(157, REQ_ID);
    // count 欄位置=3 前導 + 29 head = index 32;移除其後兩對。
    f[32] = "0".into();
    f.drain(33..37);
    d.on_contract_data_frame(&payload_of(&f), NOW)
        .expect("count=0 應消化");
    assert_eq!(d.identity_rows(NOW).1.count(), 1);

    // 荒謬 count(超 config 上界)→ typed 拒+毒化+audit(untrusted 長度不作盲走游標依據)。
    let mut d = begun(157);
    let mut f = spy_fields(157, REQ_ID);
    f[32] = "9999".into();
    assert_eq!(
        d.on_contract_data_frame(&payload_of(&f), NOW),
        Err(ContractDataReject::SecIdListCountAbsurd { got: 9999 })
    );
    assert_eq!(d.identity_staleness(NOW), SnapshotStaleness::Invalidated);
    assert_eq!(d.audit().sec_id_list_absurd_rejects, 1);
    assert_eq!(d.audit().sec_id_list_last_got, Some(9999));

    // 負 count 同拒;非數字 count → WireMalformed(形狀損壞)。
    let mut d = begun(157);
    let mut f = spy_fields(157, REQ_ID);
    f[32] = "-1".into();
    assert_eq!(
        d.on_contract_data_frame(&payload_of(&f), NOW),
        Err(ContractDataReject::SecIdListCountAbsurd { got: -1 })
    );
    let mut d = begun(157);
    let mut f = spy_fields(157, REQ_ID);
    f[32] = "abc".into();
    assert!(matches!(
        d.on_contract_data_frame(&payload_of(&f), NOW),
        Err(ContractDataReject::WireMalformed(_))
    ));
    // count 宣稱 2 但欄不足 → WireMalformed(確定性 skip 不越界)。
    let mut d = begun(157);
    let mut f = spy_fields(157, REQ_ID);
    f.truncate(34); // count=2 之後只剩 1 欄
    assert!(matches!(
        d.on_contract_data_frame(&payload_of(&f), NOW),
        Err(ContractDataReject::WireMalformed(_))
    ));
}

#[test]
fn trailing_fields_split_by_ceiling_band() {
    // sv=157(pinned 域):尾端多欄=wire 意外 → WireMalformed(精確消費紀律)。
    let mut d = begun(157);
    let mut f = spy_fields(157, REQ_ID);
    f.push("surplus".into());
    assert!(matches!(
        d.on_contract_data_frame(&payload_of(&f), NOW),
        Err(ContractDataReject::WireMalformed(_))
    ));
    // sv=176(>ceiling band):尾端多欄=band 內佈局成長 → frame 拒收+audit,非毒化非斷線,
    // 其後同世代 good frame 仍可消化(沿 W5-S3 ceiling 慣例)。
    let mut d = begun(176);
    let mut f = spy_fields(176, REQ_ID);
    f.push("surplus".into());
    assert_eq!(
        d.on_contract_data_frame(&payload_of(&f), NOW),
        Err(ContractDataReject::PinnedLayoutOverflow { msg_id: 10 })
    );
    assert_eq!(d.audit().pinned_layout_overflow_rejects, 1);
    assert_eq!(
        d.identity_staleness(NOW),
        SnapshotStaleness::SnapshotIncomplete
    );
    d.on_contract_data_frame(&payload_of(&spy_fields(176, REQ_ID)), NOW)
        .expect("overflow 後 good frame 應可消化");
    assert_eq!(d.identity_rows(NOW).1.count(), 1);
}

#[test]
fn long_name_unicode_escape_gated_at_153() {
    // 純函數面:`\uXXXX`/`\\` 解碼,其餘保留(最小實作;非法 escape 原樣保真不 panic)。
    assert_eq!(
        decode_unicode_escape_minimal(r"SPDR \u0026 CO"),
        "SPDR & CO"
    );
    assert_eq!(decode_unicode_escape_minimal(r"caf\u00e9"), "café");
    assert_eq!(decode_unicode_escape_minimal(r"A\\B"), r"A\B");
    assert_eq!(decode_unicode_escape_minimal(r"plain"), "plain");
    assert_eq!(
        decode_unicode_escape_minimal(r"bad\uZZ99 tail"),
        r"bad\uZZ99 tail"
    );
    assert_eq!(decode_unicode_escape_minimal(r"lone\"), r"lone\");
    // decode 面:sv=157(≥153)→ longName 解碼;sv=151(<153)→ 原字串保真(以 audit 樣本外的
    // row 缺席對照——151 行被 stockType blocker 擋,故取 152 對照組驗「不解碼」不可行,
    // 152≥ gate 之下唯一 <153 可接受組不存在 → 以純函數測試補位,decode 面驗 ≥153 側)。
    let mut d = begun(157);
    let mut f = spy_fields(157, REQ_ID);
    f[21] = r"SPDR \u0026 CO".into(); // 19 longName = 3 前導 + 18 = index 21
    d.on_contract_data_frame(&payload_of(&f), NOW).unwrap();
    let (_, mut rows) = d.identity_rows(NOW);
    assert_eq!(rows.next().unwrap().long_name, "SPDR & CO");
}

#[test]
fn off_whitelist_sec_type_currency_and_venue_poison_with_exact_blockers() {
    use IbkrInstrumentIdentityRowBlocker as B;

    // (欄 index 相對 3 前導:secType=4, exchange=8, currency=9, primaryExchange=22)
    for (idx, val, expected) in [
        (4usize, "FUT", B::SecTypeUnknownDenied),
        (9, "EUR", B::CurrencyDenied),
        (22, "LSE", B::PrimaryExchangeVenueDenied),
        (8, "PINK", B::ExchangeVenueDenied),
    ] {
        let mut d = begun(157);
        let mut f = spy_fields(157, REQ_ID);
        f[idx] = val.into();
        let err = d.on_contract_data_frame(&payload_of(&f), NOW).unwrap_err();
        match err {
            ContractDataReject::IdentityRowBlocked(blockers) => {
                assert_eq!(
                    blockers,
                    vec![expected],
                    "欄 {idx}={val} 應恰觸 {expected:?}"
                );
            }
            other => panic!("應為 IdentityRowBlocked,得 {other:?}"),
        }
        assert_eq!(d.identity_staleness(NOW), SnapshotStaleness::Invalidated);
        assert_eq!(d.identity_rows(NOW).1.count(), 0, "blocker 行不得併入");
    }
}

// ===========================================================================
// End / bond typed-ignore / 未請而收 / reqId 錯配
// ===========================================================================

#[test]
fn end_frame_is_strict_three_fields_and_req_id_matched() {
    let mut d = begun(157);
    // 4 欄 End → WireMalformed(嚴格 3 欄,IB 現勘 pinned)。
    assert!(matches!(
        d.on_contract_data_end_frame(&encode_fields(&["52", "1", "9003", "x"]), NOW),
        Err(ContractDataReject::WireMalformed(_))
    ));
    // reqId 錯配 → typed 拒不轉相位。
    assert_eq!(
        d.on_contract_data_end_frame(&end_payload(REQ_ID + 1), NOW),
        Err(ContractDataReject::UnexpectedReqId { got: REQ_ID + 1 })
    );
    assert_eq!(d.audit().unexpected_req_id_rejects, 1);
    assert_eq!(
        d.identity_staleness(NOW),
        SnapshotStaleness::SnapshotIncomplete
    );
    // 行的 reqId 錯配同拒。
    assert_eq!(
        d.on_contract_data_frame(&payload_of(&spy_fields(157, REQ_ID + 1)), NOW),
        Err(ContractDataReject::UnexpectedReqId { got: REQ_ID + 1 })
    );
}

#[test]
fn frames_without_active_request_are_rejected_and_audited() {
    let mut d = ContractDataDigest::new(ContractDataConfig::default());
    assert_eq!(
        d.on_contract_data_frame(&payload_of(&spy_fields(157, REQ_ID)), NOW),
        Err(ContractDataReject::NoActiveRequest)
    );
    assert_eq!(
        d.on_contract_data_end_frame(&end_payload(REQ_ID), NOW),
        Err(ContractDataReject::NoActiveRequest)
    );
    assert_eq!(d.audit().no_active_request_rejects, 2);
}

#[test]
fn bond_contract_data_is_typed_ignored_with_accounting() {
    // typed-ignore:未請而收也記帳丟棄(cash lane 良性雜訊,不 unknown-fail 不消化)。
    let mut d = ContractDataDigest::new(ContractDataConfig::default());
    d.on_bond_contract_data_frame(&encode_fields(&["18", "6", "9003", "junk", "tail"]))
        .expect("bond 應 typed-ignore");
    assert_eq!(d.audit().bond_contract_data_ignored, 1);
    assert_eq!(d.identity_rows(NOW).1.count(), 0);
    // 錯 msgId → WireMalformed(身分斷言仍在)。
    assert!(matches!(
        d.on_bond_contract_data_frame(&encode_fields(&["10", "6", "9003"])),
        Err(ContractDataReject::WireMalformed(_))
    ));
}

// ===========================================================================
// timeout typed 化 / 斷線 / 世代重評 / cap
// ===========================================================================

#[test]
fn request_timeout_is_typed_not_hanging() {
    let mut d = begun(157); // begin at NOW,timeout 默認 30s
                            // 窗內:無裁決。
    assert_eq!(d.expire_overdue(NOW + 30_000), None);
    assert_eq!(
        d.identity_staleness(NOW),
        SnapshotStaleness::SnapshotIncomplete
    );
    // 逾窗:typed 裁決 → 槽釋放回 Idle(pump 據 staleness 重取)+audit 落帳。
    let t = d.expire_overdue(NOW + 30_001).expect("逾窗應裁決");
    assert_eq!(t.req_id, REQ_ID);
    assert_eq!(t.started_at_ms, NOW);
    assert_eq!(t.expired_at_ms, NOW + 30_001);
    assert_eq!(d.identity_staleness(NOW), SnapshotStaleness::NotSubscribed);
    assert_eq!(d.audit().request_timeouts, 1);
    assert_eq!(d.audit().request_timeout_last_req_id, Some(REQ_ID));
    // 釋放後可 re-begin(非懸掛的行為證明)。
    assert!(d
        .begin_contract_details(157, REQ_ID, &spy_query(), NOW + 31_000)
        .is_ok());
    // End 已到(Live)後不再計 timeout。
    d.on_contract_data_end_frame(&end_payload(REQ_ID), NOW + 31_000)
        .unwrap();
    assert_eq!(d.expire_overdue(NOW + 999_999), None);
}

#[test]
fn disconnect_marks_stale_and_generation_reevaluates_poison() {
    // 斷線:活躍面 → DisconnectedStale,行保留供唯讀檢視。
    let mut d = begun(157);
    d.on_contract_data_frame(&payload_of(&spy_fields(157, REQ_ID)), NOW)
        .unwrap();
    d.on_contract_data_end_frame(&end_payload(REQ_ID), NOW)
        .unwrap();
    d.on_disconnect();
    let (staleness, rows) = d.identity_rows(NOW);
    assert_eq!(staleness, SnapshotStaleness::DisconnectedStale);
    assert_eq!(rows.count(), 1, "斷線行保留(staleness 已明示不可信)");
    // 毒化面:斷線不沖淡;唯世代推進重評 → DisconnectedStale → re-begin 可。
    let mut d = begun(157);
    let mut f = spy_fields(157, REQ_ID);
    f[4] = "FUT".into();
    let _ = d.on_contract_data_frame(&payload_of(&f), NOW);
    d.on_disconnect();
    assert_eq!(d.identity_staleness(NOW), SnapshotStaleness::Invalidated);
    assert_eq!(
        d.begin_contract_details(157, REQ_ID, &spy_query(), NOW),
        Err(ContractDataReject::InvalidatedUntilNewGeneration)
    );
    d.on_new_connection_generation();
    assert_eq!(
        d.identity_staleness(NOW),
        SnapshotStaleness::DisconnectedStale
    );
    assert!(d
        .begin_contract_details(157, REQ_ID, &spy_query(), NOW)
        .is_ok());
    assert_eq!(d.snapshot_seq(), 2, "re-begin 遞增快照世代");
}

#[test]
fn row_cap_poisons_without_silent_eviction() {
    let mut d = ContractDataDigest::new(ContractDataConfig {
        max_identity_rows: 1,
        ..ContractDataConfig::default()
    });
    d.begin_contract_details(157, REQ_ID, &spy_query(), NOW)
        .unwrap();
    d.on_contract_data_frame(&payload_of(&spy_fields(157, REQ_ID)), NOW)
        .unwrap();
    // 同 conId 覆蓋不受 cap 限(不增長)。
    d.on_contract_data_frame(&payload_of(&spy_fields(157, REQ_ID)), NOW + 1)
        .expect("既有鍵覆蓋應可");
    // 新 conId 超界 → 毒化+audit(禁靜默驅逐)。
    let mut f = spy_fields(157, REQ_ID);
    f[13] = "8314".into(); // 11 conId = 3 前導 + 10 = index 13
    assert_eq!(
        d.on_contract_data_frame(&payload_of(&f), NOW + 2),
        Err(ContractDataReject::SnapshotRowCapExceeded)
    );
    assert_eq!(d.identity_staleness(NOW), SnapshotStaleness::Invalidated);
    assert_eq!(d.audit().row_cap_exceeded_rejects, 1);
}

#[test]
fn identity_hash_is_pit_rebuildable_across_captures() {
    // 同一 instrument 兩次捕捉(不同時刻/世代):identity_hash 逐位一致——PIT 身份不因
    // captured_at/snapshot_seq 漂移(preimage 排除會話性欄的行為證明)。
    let mut d1 = begun(157);
    d1.on_contract_data_frame(&payload_of(&spy_fields(157, REQ_ID)), NOW)
        .unwrap();
    let h1 = d1
        .identity_rows(NOW)
        .1
        .next()
        .unwrap()
        .identity_hash
        .clone();
    let mut d2 = ContractDataDigest::new(ContractDataConfig::default());
    d2.begin_contract_details(157, REQ_ID, &spy_query(), NOW + 500_000)
        .unwrap();
    d2.on_contract_data_frame(&payload_of(&spy_fields(157, REQ_ID)), NOW + 600_000)
        .unwrap();
    let h2 = d2
        .identity_rows(NOW)
        .1
        .next()
        .unwrap()
        .identity_hash
        .clone();
    assert_eq!(h1, h2, "同 instrument 跨捕捉 identity_hash 必須可重建一致");
    assert!(is_sha256_hex(&h1));
}
