//! MODULE_NOTE
//! 模塊用途：IBKR **W6-S3 market data lane 消化層**（IBKR_TODO §5-W6 範圍 in 2/3;沿 W6-S1
//!   `ibkr_tws_contract_data` / W5-S2/S3 全部慣例）。把 `reqMktData` 的 L1 tick 訂閱生命週期
//!   收斂為 typed、fail-closed 的消化狀態機:出站 reqMktData/cancelMktData/reqMarketDataType
//!   builder（STK-only；**regulatorySnapshot 資金效果封死**；snapshot⊥genericTickList）→ IN
//!   tick 家族 decode（TICK_PRICE 合成去重/TICK_SIZE 嚴格 5 欄/per-reqId entitlement FSM/
//!   delayed provenance 標記）→ W6-S3 quote row 契約 → snapshot 11s 終態 timeout。
//! **本切片首 commit = 兩紅線（builder 級安全,先於 digest）**:
//!   - (紅線 1) E2-F1 出站 free-string 注入面:所有 caller 供給字串經 `encode_fields_checked`
//!     （NUL/非 ASCII → typed `CodecError::OutboundFieldInvalid`;涵蓋 reqMktData 全欄）。
//!   - (紅線 2) **regulatorySnapshot 資金效果封死**:regulatorySnapshot wire 欄=builder 級
//!     常量 `REGULATORY_SNAPSHOT_WIRE = "0"`（false）,**非 caller 可控**——IB headline 現勘:
//!     regulatorySnapshot 每次計費 0.01 USD 且 **paper 亦計費**（出典:官方 reqMktData 文檔,
//!     regulatorySnapshot 參數注記）。翻真=直接資金效果,違 root principle 5「survival>profit」
//!     與 §4 硬邊界「零下單/零資金效果面」→ 結構上不可由任何路徑翻真（機器守衛測試 pin）。
//! 主要區段（本 commit 僅 (a) 出站 builder;digest/decode/entitlement FSM 歸後續 commit）：
//!   - (a) OUT 常數 + `MarketDataRequest` + 三 builder（reqMktData v11 / cancelMktData /
//!     reqMarketDataType；IB 現勘 2026-07-17 pinned,官方 ibapi 9.81.1.post1 sdist）。
//! 依賴：`ibkr_tws_wire`（codec / `encode_fields_checked` E2-F1 校驗）、`thiserror`。
//! 硬邊界：
//!   - **regulatorySnapshot 封死**（見上;本切片硬紅線）。
//!   - **STK-only**:reqMktData 只承 STK 全限定合約——BAG combo 塊結構性缺席（secType 恆
//!     `"STK"`,非 caller 可控;combo/期權/期貨面永久 denied）。
//!   - **snapshot ⊥ genericTickList**:snapshot=true 回一次當前值即取消,genericTickList 對其
//!     無意義且 server 拒 → `SnapshotWithGenericTicks` typed 拒（結構性不送）。
//!   - **無 socket / 無 I/O / 無 async**:純同步,出站 frame 由本檔 build,**送出必經 pacing
//!     單一出口**（driver 以 `OutboundClass::MarketData` 取 grant 後 `send_framed`;lines
//!     semaphore 為訂閱數配額,與 W3 rate bucket 分軸——IB 現勘 pinned）。
//!   - **唯讀行情面**:只 build 唯讀 market data 請求——**絕不新增下單/改單/撤單 builder**。
//!   - **零 production caller（W3-W7 B′ 姿態）**:本模塊經 driver 測試域消費;default build 隨
//!     TWS 連接器面 DCE,g4/driver-absence audit 保綠。Bybit crypto_perp 不變;無 DB migration。

// intentional-DCE 姿態繼承 wire/session/pacing/driver/account_data/order_exec/contract_data
// （見各檔 MODULE_NOTE）:本模塊在 default build 零 production caller（真消費者=driver
// 測試域;W6+ 接 IPC 投影面）。
#![allow(dead_code)]

// `encode_fields`（raw 形）僅供內部常數欄（msgId/version）——無 caller 供給字串、無注入面;
// caller 供給字串一律走 `encode_fields_checked`（E2-F1）。
use crate::ibkr_tws_wire::{encode_fields, encode_fields_checked, encode_frame, CodecError};

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

/// **regulatorySnapshot 資金效果封死常量（本切片硬紅線）**。恆 `"0"`（false）——**非 caller
/// 可控**,不作 `MarketDataRequest` 欄。為什麼:IB 現勘 headline,regulatorySnapshot 每次
/// 計費 0.01 USD 且 **paper 亦計費**;翻真=直接資金效果,違 root principle 5 與 §4「零資金
/// 效果面」。機器守衛測試 pin:任何 `MarketDataRequest` 輸入下 wire regulatorySnapshot 欄
/// 恆 `"0"`（結構上無翻真路徑）。
const REGULATORY_SNAPSHOT_WIRE: &str = "0";

/// deltaNeutral flag（STK 恆無 delta-neutral 合約 → 恆 `"0"`;IB reqMktData v11 欄）。
const DELTA_NEUTRAL_WIRE: &str = "0";

/// regulatorySnapshot 欄門檻（sv≥114;floor=145 下恆在,gate 仍按 IB 佈局防 band 錯位）。
pub(crate) const SV_GATE_REGULATORY_SNAPSHOT: i32 = 114;
/// mktDataOptions 欄門檻（sv≥70;linking 世代起 tagValue 尾欄,本 lane 恆空）。
pub(crate) const SV_GATE_MKT_DATA_OPTIONS: i32 = 70;

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

/// market data builder / decode 層 typed 裁決（本 commit 僅 builder 用 (a) 兩變體;
/// digest/decode/entitlement 變體歸後續 commit 擴充）。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub(crate) enum MarketDataReject {
    /// **snapshot ⊥ genericTickList**:snapshot=true 帶 tick 列表 → 結構性拒（IB 現勘:snapshot
    /// 一次性,tick 型別列表無意義且 server 拒;不送）。
    #[error("snapshot market data request must not carry a generic tick list")]
    SnapshotWithGenericTicks,
    /// wire 形狀損壞 / **E2-F1 出站欄位注入**（NUL/非 ASCII）——builder 級 fail-closed,絕不
    /// 送出被注入的 frame（`CodecError::OutboundFieldInvalid`）。
    #[error("wire malformed: {0}")]
    WireMalformed(CodecError),
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
pub(crate) fn encode_req_mkt_data(
    req_id: i64,
    req: &MarketDataRequest,
    server_version: i32,
) -> Result<Vec<u8>, MarketDataReject> {
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
        "0",   // strike（ibapi 對 unset 送 0）
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
/// 語義歸 digest 層 entitlement FSM,後續 commit）。
pub(crate) fn encode_req_market_data_type(market_data_type: i32) -> Vec<u8> {
    let mdt = market_data_type.to_string();
    encode_frame(&encode_fields(&[
        OUT_REQ_MARKET_DATA_TYPE_MSG_ID,
        REQ_MARKET_DATA_TYPE_VERSION,
        &mdt,
    ]))
}

#[cfg(test)]
#[path = "ibkr_tws_market_data_tests.rs"]
mod tests;
