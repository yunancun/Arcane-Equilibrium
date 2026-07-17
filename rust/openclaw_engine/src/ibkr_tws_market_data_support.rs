//! MODULE_NOTE
//! 模塊用途：`ibkr_tws_market_data` 的 **support 子模塊**（800 行帽拆檔;非獨立面）——
//!   承載 W6-S3 market data lane 的純 codec/門控常數/entitlement 錯誤碼分類/tick 值紀律/
//!   provenance 雜湊面:OUT reqMktData v11 / cancelMktData / reqMarketDataType builder（IB
//!   現勘 pinned;**regulatorySnapshot 資金效果封死**;STK-only;snapshot⊥genericTickList）+
//!   per-reqId entitlement 錯誤碼 FSM 分類（354/10167/10186/10190/10197/10090）+ tick 值
//!   保真/no-data 抑制 + provenance_hash 鑄造。
//! 依賴：父模塊型別（`MarketDataReject`）、`ibkr_tws_wire` codec、`openclaw_types` 契約、
//!   `sha2`/`hex`。
//! 硬邊界：與父模塊同一 typed fail-closed 紀律（不 panic、不捏值、不默認）;無 socket、
//!   無 I/O、無狀態——本檔只有純函數/純資料,狀態機恆在父模塊。

use std::collections::BTreeMap;

use sha2::{Digest, Sha256};

use openclaw_types::{
    is_nonnegative_decimal_string, is_positive_decimal_string, IbkrMarketDataEntitlementStateV1,
    IbkrMarketDataProvenanceV1, IbkrQuoteFieldV1, IbkrQuoteRowV1, IbkrTickValueKind,
};

use crate::ibkr_tws_wire::{encode_fields, encode_fields_checked, encode_frame, CodecError};

use super::MarketDataReject;

// ===========================================================================
// (a) OUT 常數 + 全限定行情請求 + v11 builder（IB 現勘 2026-07-17 pinned;官方 ibapi
// 9.81.1.post1 sdist）
// 注:OUT 與 IN 是兩個獨立編號空間——OUT REQ_MKT_DATA=1 / CANCEL_MKT_DATA=2 與 IN
// TICK_PRICE=1 / TICK_SIZE=2 撞值;IN 空間常數居 `ibkr_tws_wire`（`IN_*`）,此處為 OUT 空間
// （`OUT_*`）,命名帶方向防混用（沿 W5-S2/S3/W6-S1 慣例）。
// ===========================================================================

/// OUT 1:reqMktData（唯讀 L1 tick 訂閱）。
pub(crate) const OUT_REQ_MKT_DATA_MSG_ID: &str = "1";
/// reqMktData 的 wire VERSION 欄（IB 現勘:v11）。
const REQ_MKT_DATA_VERSION: &str = "11";
/// OUT 2:cancelMktData。
pub(crate) const OUT_CANCEL_MKT_DATA_MSG_ID: &str = "2";
/// cancelMktData 的 wire VERSION 欄（IB 現勘:v2）。
const CANCEL_MKT_DATA_VERSION: &str = "2";
/// OUT 59:reqMarketDataType（entitlement 降級 opt-in）。
pub(crate) const OUT_REQ_MARKET_DATA_TYPE_MSG_ID: &str = "59";
/// reqMarketDataType 的 wire VERSION 欄（IB 現勘:v1）。
const REQ_MARKET_DATA_TYPE_VERSION: &str = "1";

/// **regulatorySnapshot 資金效果封死常量（本 lane 硬紅線）**。恆 `"0"`（false）——**非 caller
/// 可控**,不作 `MarketDataRequest` 欄。為什麼:IB 現勘 headline,regulatorySnapshot 每次
/// 計費 0.01 USD 且 **paper 亦計費**;翻真=直接資金效果,違 root principle 5 與 §4「零資金
/// 效果面」。機器守衛測試 pin:任何 `MarketDataRequest` 輸入下 wire regulatorySnapshot 欄
/// 恆 `"0"`（結構上無翻真路徑）。
pub(crate) const REGULATORY_SNAPSHOT_WIRE: &str = "0";

/// deltaNeutral flag（STK 恆無 delta-neutral 合約 → 恆 `"0"`;IB reqMktData v11 欄）。
const DELTA_NEUTRAL_WIRE: &str = "0";

/// regulatorySnapshot 欄門檻（sv≥114;floor=145 下恆在,gate 仍按 IB 佈局防 band 錯位）。
pub(crate) const SV_GATE_REGULATORY_SNAPSHOT: i32 = 114;
/// mktDataOptions 欄門檻（sv≥70;linking 世代起 tagValue 尾欄,本 lane 恆空）。
pub(crate) const SV_GATE_MKT_DATA_OPTIONS: i32 = 70;

/// **market data floor guard**（IB-NOTE-2 R19）:reqMktData v11 body **無條件** emit conId 與
/// tradingClass 欄——此二欄僅 sv≥145 世代安全（早世代 reqMktData 佈局無 conId/tradingClass）。
/// 本 lane floor=145（對齊 W5-S3/W6-S1）→ builder 對 sv<145 加 debug_assert 防未來誤用,
/// begin 層另以 `ServerVersionBelowFloor` typed 拒（真 fail-closed,非僅 debug 斷言）。
pub(crate) const MKT_DATA_SERVER_VERSION_FLOOR: i32 = 145;

/// 全限定 STK 行情請求（reqMktData 的 typed 出站承載;secType 恆 STK、currency 恆 USD 由
/// builder 定界——lane 白名單於出站即成立,非僅入站拒）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct MarketDataRequest {
    /// IBKR contract id（主鍵;正整數;由 W6-S1 identity 快照解出）。
    pub con_id: i64,
    /// 標的代碼（wire 原字串;E2-F1 由 builder 校驗 NUL/非 ASCII）。
    pub symbol: String,
    /// 路由交易所（慣例 `SMART`）。
    pub exchange: String,
    /// 主上市交易所（消歧欄;可空）。
    pub primary_exchange: String,
    /// 本地代碼（可含空格如 `"BRK B"`;wire 原字串保真）。
    pub local_symbol: String,
    /// tradingClass（wire 原字串保真）。
    pub trading_class: String,
    /// generic tick 型別列表（csv;**snapshot=true 時必空**,見硬邊界）。
    pub generic_tick_list: String,
    /// snapshot 語義:true=回當前值一次後自動取消（11s 終態 timeout,digest 相位語義）。
    pub snapshot: bool,
}

/// encode reqMktData：framed v11 body（IB 現勘欄序,2026-07-17 pinned）。
/// `[1, 11, reqId, conId, symbol, secType, lastTradeDateOrContractMonth, strike, right,
/// multiplier, exchange, primaryExchange, currency, localSymbol, tradingClass, (BAG combo
/// 塊僅 secType==BAG,STK 恆缺), deltaNeutral flag "0", genericTickList, snapshot,
/// regulatorySnapshot(sv≥114), mktDataOptions ""(sv≥70)]`。
///
/// STK-only（secType 恆 `"STK"`,BAG 塊結構性缺席）;currency 恆 `"USD"`;
/// **regulatorySnapshot 恆 `"0"`（資金紅線,非 caller 可控）**;snapshot=true 禁 genericTickList
/// （`SnapshotWithGenericTicks` 拒）;E2-F1:caller 供給欄經 `encode_fields_checked`。
///
/// **IB-NOTE-2（R19）**:conId/tradingClass 無條件 emit 僅 sv≥145 安全 → debug_assert floor。
pub(crate) fn encode_req_mkt_data(
    req_id: i64,
    req: &MarketDataRequest,
    server_version: i32,
) -> Result<Vec<u8>, MarketDataReject> {
    // IB-NOTE-2:conId/tradingClass 無條件 emit 的 sv-floor 不變量（begin 層另以 typed 拒把關;
    // 此斷言防未來繞過 begin 直呼 builder 於早世代誤用）。
    debug_assert!(
        server_version >= MKT_DATA_SERVER_VERSION_FLOOR,
        "reqMktData conId/tradingClass 無條件 emit 僅 sv>=145 安全(got {server_version})"
    );
    // snapshot ⊥ genericTickList（先於編碼裁決;結構性不送）。
    if req.snapshot && !req.generic_tick_list.trim().is_empty() {
        return Err(MarketDataReject::SnapshotWithGenericTicks);
    }
    let rid = req_id.to_string();
    let cid = req.con_id.to_string();
    let snapshot_wire = if req.snapshot { "1" } else { "0" };
    let mut fields: Vec<&str> = vec![
        OUT_REQ_MKT_DATA_MSG_ID,
        REQ_MKT_DATA_VERSION,
        &rid,
        &cid,
        &req.symbol,
        "STK", // secType（STK-only;BAG 塊因此結構性缺席）
        "",    // lastTradeDateOrContractMonth（STK 無到期）
        "0.0", // strike（IB-NOTE-1 R19:ibapi make_field(float 0.0)→"0.0",非整數 "0"）
        "",    // right
        "",    // multiplier
        &req.exchange,
        &req.primary_exchange,
        "USD", // currency（lane 白名單）
        &req.local_symbol,
        &req.trading_class,
        // BAG combo 塊:僅 secType==BAG 出現,STK 恆缺（結構性;不 push 任何 combo 欄）。
        DELTA_NEUTRAL_WIRE, // deltaNeutral flag（STK 恆 "0"）
        &req.generic_tick_list,
        snapshot_wire,
    ];
    // regulatorySnapshot（sv≥114;**builder 級常量 "0",資金紅線封死**）。
    if server_version >= SV_GATE_REGULATORY_SNAPSHOT {
        fields.push(REGULATORY_SNAPSHOT_WIRE);
    }
    // mktDataOptions（sv≥70;linking 世代 tagValue 尾欄,本 lane 恆空）。
    if server_version >= SV_GATE_MKT_DATA_OPTIONS {
        fields.push("");
    }
    Ok(encode_frame(
        &encode_fields_checked(&fields).map_err(MarketDataReject::WireMalformed)?,
    ))
}

/// encode cancelMktData：framed `[2, 2, reqId]`（IB 現勘 pinned;無 caller 自由欄,退訂紀律
/// 用——超 lines 上限先退訂再新訂）。
pub(crate) fn encode_cancel_mkt_data(req_id: i64) -> Vec<u8> {
    let rid = req_id.to_string();
    encode_frame(&encode_fields(&[
        OUT_CANCEL_MKT_DATA_MSG_ID,
        CANCEL_MKT_DATA_VERSION,
        &rid,
    ]))
}

/// encode reqMarketDataType：framed `[59, 1, marketDataType]`（IB 現勘 pinned）。
/// marketDataType:1=live/2=frozen/3=delayed/4=delayed-frozen——**v1 delayed-only 姿態**:降級
/// 是 opt-in（每 session 顯式先發 type 3 再訂閱,非自動)。marketDataType 為 i32 常數（enum
/// 語義歸 digest 層 entitlement FSM）。
pub(crate) fn encode_req_market_data_type(market_data_type: i32) -> Vec<u8> {
    let mdt = market_data_type.to_string();
    encode_frame(&encode_fields(&[
        OUT_REQ_MARKET_DATA_TYPE_MSG_ID,
        REQ_MARKET_DATA_TYPE_VERSION,
        &mdt,
    ]))
}

// ===========================================================================
// (b) MARKET_DATA_TYPE(58) 值映射 + per-reqId entitlement 錯誤碼 FSM 分類（IB pinned）
// ===========================================================================

/// IB 行情 entitlement 錯誤碼（現勘 2026-07-17 pinned;皆 ≥2100 → session 層 Info no-op,
/// **per-reqId 消費歸本 digest**——不進 session FSM,見 `IbkrTwsErrorClassV1::Entitlement`
/// 注釋）。354 例外為 <2100（Entitlement class,session 亦 no-op）。
pub(crate) const IB_ERR_MKT_DATA_NOT_SUBSCRIBED: i64 = 354;
/// 10167:displaying delayed market data（**僅當本 session 已顯式送 reqMarketDataType(3|4)**
/// 才是合法降級確認;否則=協議意外拒）。
pub(crate) const IB_ERR_DELAYED_MARKET_DATA: i64 = 10167;
/// 10186:requested market data is not subscribed（→ None halt）。
pub(crate) const IB_ERR_MKT_DATA_NOT_SUBSCRIBED_DISPLAY: i64 = 10186;
/// 10190:market data is not subscribed. Displaying delayed... 的 no-entitlement 變體（→ None）。
pub(crate) const IB_ERR_MKT_DATA_NOT_SUBSCRIBED_DELAYED_NA: i64 = 10190;
/// 10197:no market data during competing live session（**typed halt 禁重試**——另一 live
/// session 佔用 entitlement,重訂只會再撞）。
pub(crate) const IB_ERR_COMPETING_LIVE_SESSION: i64 = 10197;
/// 10090:part of requested market data is not subscribed（→ Partial;部分欄有值,窗不 halt）。
pub(crate) const IB_ERR_MKT_DATA_PART_NOT_SUBSCRIBED: i64 = 10090;

/// per-reqId entitlement 錯誤碼分類產物（IB pinned FSM）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum EntitlementErrorOutcome {
    /// 354/10186/10190 → NONE（halt;不重試）。
    None,
    /// 10167 且本 session 已 opt-in reqMarketDataType(3|4) → DELAYED 降級確認。
    Delayed,
    /// 10167 但本 session **未** opt-in → 協議意外（未請求降級卻收降級確認）→ fail-closed 退訂。
    DelayedWithoutOptIn,
    /// 10197 → COMPETING_SESSION（typed halt,禁重試）。
    CompetingSession,
    /// 10090 → PARTIAL（部分欄未訂;窗續存,不 halt）。
    Partial,
    /// 表外 code → fail-closed 退訂（未知 entitlement 語義不猜）。
    Unknown,
}

/// entitlement 錯誤碼 → FSM 裁決（IB pinned;10167 依 `delayed_opt_in` 分岔）。
pub(crate) fn classify_entitlement_error(
    code: i64,
    delayed_opt_in: bool,
) -> EntitlementErrorOutcome {
    match code {
        IB_ERR_MKT_DATA_NOT_SUBSCRIBED
        | IB_ERR_MKT_DATA_NOT_SUBSCRIBED_DISPLAY
        | IB_ERR_MKT_DATA_NOT_SUBSCRIBED_DELAYED_NA => EntitlementErrorOutcome::None,
        IB_ERR_DELAYED_MARKET_DATA => {
            if delayed_opt_in {
                EntitlementErrorOutcome::Delayed
            } else {
                EntitlementErrorOutcome::DelayedWithoutOptIn
            }
        }
        IB_ERR_COMPETING_LIVE_SESSION => EntitlementErrorOutcome::CompetingSession,
        IB_ERR_MKT_DATA_PART_NOT_SUBSCRIBED => EntitlementErrorOutcome::Partial,
        _ => EntitlementErrorOutcome::Unknown,
    }
}

// IB-B′（R20）收口:`is_market_data_entitlement_code` pre-filter 助手已移除。理由——把它接為
// pre-filter（僅已知 entitlement 碼進 FSM）會令表外 code 繞過 `on_entitlement_error` 的
// `Unknown → Halted` 臂,弱化 fail-closed（違反「unknown code→halt 保留」硬邊界);而 driver
// 對「reqId 對應活躍訂閱」的 ERR_MSG 一律入 FSM（表外 code→Unknown→Halt=保守 fail-closed)已是
// 更強姿態,故本助手接線後恆冗餘 → 移除。halt-on-unknown 由 driver e2e 回歸測試釘住。

// ===========================================================================
// (c) tick 值紀律（保真 + no-data 抑制）+ provenance_hash 鑄造
// ===========================================================================

/// tick 值保真校驗:依 `kind` 走 price（定點嚴格正）或 size（非負整數）紀律。
/// **no-data 抑制**:IB 對無可用值送 price=-1 / 量級哨兵（`e` 記法）/空欄——皆非合法值 →
/// 回 `None`（消化端抑制,不materialize 一個被 blocker 拒的 row,亦不當真值記帳）。合法值
/// **原字串保真**回 `Some`（禁 f64 reparse——浮點在對齊/雜湊上非確定性;wire 已是定點字串）。
pub(crate) fn sanitize_tick_value(raw: &str, kind: IbkrTickValueKind) -> Option<String> {
    match kind {
        IbkrTickValueKind::Price => {
            // 嚴格正定點:排除 -1 no-data 哨兵、0、量級哨兵（含 e/E）、空欄。
            if is_positive_decimal_string(raw) {
                Some(raw.to_string())
            } else {
                None
            }
        }
        IbkrTickValueKind::Size => {
            // 非負整數:0=無掛單合法;-1 no-data / 小數 / 空欄 → 抑制。
            if is_nonnegative_decimal_string(raw) && !raw.contains('.') {
                Some(raw.to_string())
            } else {
                None
            }
        }
    }
}

/// provenance_hash 鑄造:sha256(preimage) → 64 lowercase hex。preimage 是契約純函數
/// （單一定義點,PIT 可重建——重放端以同 provenance 重建必得同 hash）;雜湊計算居 engine
/// （types crate 無雜湊依賴,契約只驗 shape `is_sha256_hex`）。沿 W6-S1 `compute_identity_hash`
/// 慣例。
pub(crate) fn compute_provenance_hash(prov: &IbkrMarketDataProvenanceV1) -> String {
    let mut hasher = Sha256::new();
    hasher.update(prov.provenance_hash_preimage().as_bytes());
    hex::encode(hasher.finalize())
}

/// 欄位 0 的 msgId 斷言（非數字/錯 id → `WireMalformed`,不猜、不容錯位;同構 W5-S2/S3/W6-S1）。
pub(crate) fn expect_msg_id(raw: &str, expected: i64) -> Result<(), MarketDataReject> {
    let got = parse_i64(raw, "msg_id")?;
    if got != expected {
        return Err(MarketDataReject::WireMalformed(
            CodecError::UnexpectedMsgId { got },
        ));
    }
    Ok(())
}

/// 數字欄 parse（非數字 → `WireMalformed(NonNumericField)`,禁 `unwrap_or(0)` 捏造;
/// 同構 W5-S2/S3/W6-S1）。
pub(crate) fn parse_i64(raw: &str, field: &'static str) -> Result<i64, MarketDataReject> {
    raw.parse::<i64>()
        .map_err(|_| MarketDataReject::WireMalformed(CodecError::NonNumericField(field)))
}

// ===========================================================================
// (d) 訂閱狀態純資料/枚舉 + staleness 投影（800 行帽:狀態機恆在父模塊,純資料/純函數居此）
// ===========================================================================

/// snapshot 終態 typed 裁決產物（`expire_overdue` 回傳;非懸掛的證明面）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct SnapshotTerminal {
    pub req_id: i64,
    pub started_at_ms: u64,
    pub terminated_at_ms: u64,
}

/// audit 計數器（W6-S0 慣例:全部單調遞增+`*_last_*` 樣本欄;driver/W6 IPC 投影唯讀消費）。
/// 為什麼需要:driver 對資料層 typed reject 走 `Err(_)=>{}` 分流續 serve——無 audit 則
/// blocker 身分零觀測。
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub(crate) struct MarketDataAudit {
    /// 已併入的 price/size tick 數。
    pub ticks_applied: u64,
    /// **TICK_PRICE 合成 tickSize 去重**:同一 TICK_PRICE 內嵌 size 抑制數（單源記帳=size
    /// 唯認 TICK_SIZE(2);禁雙記——S3a delayed-provenance 家族合成去重紅線）。
    pub synth_size_suppressed: u64,
    /// no-data 值抑制數（price=-1 / 量級哨兵 / 空欄 → 不 materialize、不當真值記帳）。
    pub no_data_suppressed: u64,
    /// TICK_GENERIC(45) typed-ignore 記帳數（L1 lane 不承 generic tick;記帳丟棄非 unknown-fail)。
    pub generic_tick_ignored: u64,
    /// TICK_STRING(46) typed-ignore 記帳數（同上）。
    pub string_tick_ignored: u64,
    /// TICK_REQ_PARAMS(81) typed-ignore 記帳數（minTick/bbo/snapshotPermissions;v1 不承）。
    pub tick_req_params_ignored: u64,
    /// 表外 tickType typed-ignore 數（非 BID/ASK/LAST 白名單的 tick;記帳丟棄）。
    pub unknown_tick_type_ignored: u64,
    /// entitlement 態↔tick provenance 衝突抑制數（state=Delayed 卻收 realtime tick 等;
    /// fail-closed 不 materialize,避免 entitlement 窗記帳謊言）。
    pub entitlement_tick_conflict: u64,
    /// halt 後仍收 tick 的抑制數（None/CompetingSession halt 後不應再有值）。
    pub tick_after_halt_suppressed: u64,
    /// MARKET_DATA_TYPE(58) 綁定數。
    pub market_data_type_bindings: u64,
    /// entitlement 錯誤碼裁決各態計數。
    pub entitlement_none_rejects: u64,
    pub entitlement_delayed_confirmed: u64,
    pub entitlement_delayed_without_optin: u64,
    pub entitlement_competing_session: u64,
    pub entitlement_partial: u64,
    pub entitlement_unknown_code_halts: u64,
    /// 最後一次 entitlement 錯誤碼（telemetry 樣本）。
    pub entitlement_last_code: Option<i64>,
    /// snapshot 終態 timeout 數（END 缺席兜底）。
    pub snapshot_terminals: u64,
    /// 未訂而收拒數。
    pub no_active_subscription_rejects: u64,
    /// lines 耗盡拒數（backpressure 可觀測）。
    pub lines_exhausted_rejects: u64,
    /// quote row 契約 blocker 拒數。
    pub quote_row_blocked_rejects: u64,
    /// wire 損壞拒數（呼叫端 fail-closed 斷線;此處留身分供斷線前因對賬）。
    pub wire_malformed_rejects: u64,
    /// 最後一次 wire 損壞的 typed 描述（不含 payload 原文）。
    pub wire_malformed_last_note: Option<String>,
}

/// per-reqId entitlement FSM 態（digest 內部;→ provenance `IbkrMarketDataEntitlementStateV1`
/// 於 `provenance_state()` 調和）。**IB-NOTE-3（R19）詞彙調和**:provenance 側說 `Entitled`
/// （溯源窗檔位）,tick 側說 `Realtime`（`IbkrTickEntitlementV1`）——二者指同一 realtime live
/// 檔位,只是溯源 vs 單 tick 的視角。本 FSM 以 provenance 視角命名。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ReqEntitlement {
    /// 尚未由 MARKET_DATA_TYPE(58) 或首 tick 判定（provenance=UnknownDenied,窗未成形）。
    Pending,
    /// realtime live 檔位（↔ tick 側 `Realtime`）。
    Entitled,
    /// delayed（15-20min）檔位（tick 側亦 `Delayed`）。
    Delayed,
    /// 354/10186/10190/未知 code → 無權限 halt。
    NoneHalt,
    /// 10197 competing live session → halt（禁重試）。
    CompetingHalt,
}

impl ReqEntitlement {
    /// → provenance 契約三態（Pending → UnknownDenied,窗未成形即 blocker——誠實不猜）。
    pub(crate) fn provenance_state(self) -> IbkrMarketDataEntitlementStateV1 {
        match self {
            ReqEntitlement::Entitled => IbkrMarketDataEntitlementStateV1::Entitled,
            ReqEntitlement::Delayed => IbkrMarketDataEntitlementStateV1::Delayed,
            ReqEntitlement::NoneHalt | ReqEntitlement::CompetingHalt => {
                IbkrMarketDataEntitlementStateV1::None
            }
            ReqEntitlement::Pending => IbkrMarketDataEntitlementStateV1::UnknownDenied,
        }
    }
}

/// 訂閱生命週期相位（per-reqId）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SubPhase {
    /// streaming 訂閱進行中（佔 line）。
    Streaming,
    /// snapshot 訂閱等 TICK_SNAPSHOT_END/timeout（佔 line）。
    SnapshotPending,
    /// snapshot 已終（END 到或 11s 終態 timeout;不佔 line,值供唯讀檢視）。
    SnapshotComplete,
    /// entitlement halt（None/CompetingSession/未知 code;世代內終態,不佔 line,唯世代重評
    /// 或斷線後 re-begin）。
    Halted,
    /// wire/契約毒化（fail-closed;世代內終態,不佔 line）。
    Invalidated,
    /// 斷線失效（唯 re-begin 離開;訂閱不跨連線存活）。
    DisconnectedStale,
}

impl SubPhase {
    /// 是否佔 line（count semaphore 計入面;僅活躍訂閱佔 line）。
    pub(crate) fn occupies_line(self) -> bool {
        matches!(self, SubPhase::Streaming | SubPhase::SnapshotPending)
    }
}

/// per-reqId 訂閱狀態（quotes 以 logical field 為鍵,結構性 ≤6 欄,無需 cap）。
#[derive(Debug, Clone)]
pub(crate) struct Subscription {
    pub con_id: i64,
    pub symbol: String,
    pub snapshot: bool,
    pub phase: SubPhase,
    pub entitlement: ReqEntitlement,
    /// begin 注入時刻（snapshot 終態 timeout 基準;僅 SnapshotPending 有語義）。
    pub started_at_ms: u64,
    /// 窗首/末 tick 捕捉時戳（provenance 窗;0=尚無 tick）。
    pub first_tick_at_ms: u64,
    pub last_tick_at_ms: u64,
    /// W6-S1 instrument identity hash（S1 供給;provenance 溯源錨）。
    pub instrument_identity_hash: String,
    /// W6-S2 calendar hash（S2 供給;provenance 溯源錨,本切片 shape 承載）。
    pub calendar_hash: String,
    /// 最新 quote row（鍵=logical field 的穩定序 index;後到覆蓋,latest-value 單源記帳。
    /// 用 u8 index 而非 `IbkrQuoteFieldV1` 為鍵:契約 field 未 impl `Ord`（BTreeMap 需之),
    /// 以本地 `field_key` 投影穩定序,不觸 types 契約——row 自帶 `tick_type` 供消費端還原欄）。
    pub quotes: BTreeMap<u8, IbkrQuoteRowV1>,
}

/// logical field → 穩定序 index（BTreeMap 鍵;確定序供綁定視圖）。
pub(crate) fn field_key(field: IbkrQuoteFieldV1) -> u8 {
    match field {
        IbkrQuoteFieldV1::Bid => 0,
        IbkrQuoteFieldV1::Ask => 1,
        IbkrQuoteFieldV1::Last => 2,
        IbkrQuoteFieldV1::BidSize => 3,
        IbkrQuoteFieldV1::AskSize => 4,
        IbkrQuoteFieldV1::LastSize => 5,
    }
}
