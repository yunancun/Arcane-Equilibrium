//! MODULE_NOTE
//! 模塊用途：IBKR **W5-S3 open orders / executions / commissions 消化層**（IBKR_TODO §5-W5;
//!   沿 W5-S2 `ibkr_tws_account_data` 全部慣例）。把 `reqExecutions`/`reqOpenOrders`/
//!   `reqAllOpenOrders` 的單次快照 + 其後恆在推送收斂為 typed、fail-closed 的消化狀態機：
//!   出站 builder（IB 現勘 pinned 欄位序）→ 入站 decode → W5-S1 row 契約
//!   （`IbkrExecutionsRowV1`/`IbkrCommissionsRowV1`,「先契約後消化,禁裸 map」）+
//!   orderStatus/openOrder 最小 typed 快照 → exec↔commission either-order join → typed
//!   staleness（沿 `SnapshotStaleness` 六態）。
//! 主要區段：
//!   - (a) OUT 常數 + 出站 builder 三個（IB 現勘 2026-07-17 pinned,官方 ibapi 9.81.1.post1
//!     sdist:OUT 空間 reqOpenOrders=5 / reqExecutions=7 / reqAllOpenOrders=16;IN 空間
//!     OPEN_ORDER=5 與 OUT 5 撞值——IN 常數居 `ibkr_tws_wire`,`IN_`/`OUT_` 方向命名防混用,
//!     沿 W5-S2 G4 慣例。`reqAutoOpenOrders`(OUT 15) **不做**:僅 client 0 專屬 auto-bind
//!     語義,本 lane 不用,builder 面留空並在此註明）。
//!   - (b) config：`OrderExecDataConfig`（DIVERGENT-1 floor/ceiling serverVersion 兩界 /
//!     exec_time grammar 白名單 / join 孤兒 TTL / staleness 窗;參數禁假功能,每項真生效）。
//!   - (c) typed 裁決：`OrderExecDataReject`（wire 損壞 / 契約 blocker / 佈局窗 / grammar /
//!     表外 status——全 typed,不 panic、不捏值、不默認）。
//!   - (d) `OrderExecDataDigest`：executions/open-orders 雙槽狀態機（End 界定快照;之後推送
//!     恆在=Live 相位續收）+ exec↔commission either-order join + audit 計數器 + 斷線失效。
//! 依賴：`ibkr_tws_wire`（codec/IN 常數）、`ibkr_tws_account_data`（`SnapshotStaleness`
//!   六態共用）、`openclaw_types`（W5-S1 executions/commissions row 契約 + secType/symbol
//!   紀律）、`std::collections::BTreeMap`。
//! 硬邊界：
//!   - **無 socket / 無 I/O / 無 async**：純同步狀態機,注入時鐘（now_ms）。出站 frame 由
//!     本檔 build,**送出必經 pacing 單一出口**（driver 以 `OutboundClass::AccountData` 主桶
//!     取 `OutboundGrant` 後 `send_framed`;IB 現勘:此三 outbound 不受 historical 四規則
//!     約束,走主桶）。
//!   - **唯讀對賬面**：本模塊只 build 唯讀對賬請求（reqExecutions/reqOpenOrders/
//!     reqAllOpenOrders）——**絕不新增下單/改單/撤單 builder**（IBKR_TODO §2 permanent
//!     denied 面;W7 order lifecycle 另案且仍 fail-closed gated）。
//!   - **DIVERGENT-1（PM 裁 (a),floor/ceiling 佈局窗）**：官方位元組只 pin 到 serverVersion
//!     157;引擎協商上限 176。①floor：協商 sv<145 → 整面拒開消化（一次覆蓋 136/131/145 三
//!     門檻,消除雙佈局分支）;②ceiling：sv>157 按 157 佈局 decode——EXECUTION_DATA/
//!     COMMISSION_REPORT/ORDER_STATUS 為定長平面尾,尾端未讀欄 → 該 frame 拒收+audit
//!     （禁猜讀）;OPEN_ORDER 本就 head-prefix+tail-discard 天然容忍。兩界 config 化;
//!     10.x band（158..=176）佈局官方位元組 **UNVERIFIED**,補證歸 operator follow-up。
//!   - **realizedPNL 哨兵→None（移交 blocking #1,雙判別 fail-closed）**：空欄→None;解析後
//!     |v|≥1.0e308 或精確字串 `1.7976931348623157E308`（E 大小寫不敏感）→ None+audit 記
//!     原始字串;其餘→Some（簽名定點字串,`0`=合法損益恆 `Some("0")`,**禁折 0**）。
//!   - **exec_time grammar（移交 blocking #2）**：官方不 pin 格式 → grammar 白名單 config
//!     fail-closed:首選 UTC 形 `^\d{8}-\d{2}:\d{2}:\d{2}$`;白名單外（帶 TZ 後綴/雙空格
//!     傳統形）→ row 級拒收+audit（契約承原字串,拒收可重放）。**EA 活化前置**:operator 須
//!     設 TWS API 時間=UTC 模式 + 首批樣本 grammar attestation。
//!   - **unsolicited 通道**：reqExecutions=單次快照（execDetailsEnd 收批),之後成交自動推
//!     execDetails+commissionReport;推送 reqId 慣稱 -1 但無官方位元組證 → 未知/負 reqId 走
//!     unsolicited 通道承接+計數,**禁按 pending 匹配失敗丟棄**。commissionReport 與
//!     execDetails **無到達順序保證** → execId 鍵 either-order join,孤兒側 TTL 計量。
//!   - **零 production caller（W3-W7 B′ 姿態）**：本模塊經 driver 測試域消費;default build
//!     隨 TWS 連接器面 DCE,g4/driver-absence audit 保綠。Bybit crypto_perp 不變;無 DB
//!     migration。

// intentional-DCE 姿態繼承 wire/session/pacing/driver/account_data（見各檔 MODULE_NOTE）:
// 本模塊在 default build 零 production caller（真消費者=driver 測試域;W6+ 接 IPC 投影面）。
#![allow(dead_code)]

use std::collections::BTreeMap;
use std::time::Duration;

use openclaw_types::{
    is_normalized_symbol, is_positive_decimal_string, is_signed_decimal_string,
    IbkrCommissionsRowBlocker, IbkrCommissionsRowV1, IbkrExecutionSideV1, IbkrExecutionsRowBlocker,
    IbkrExecutionsRowV1, IbkrSecTypeV1, StockEtfCurrency, IBKR_COMMISSIONS_ROW_CONTRACT_ID,
    IBKR_EXECUTIONS_ROW_CONTRACT_ID,
};

use crate::ibkr_tws_account_data::SnapshotStaleness;
use crate::ibkr_tws_wire::{
    decode_fields, encode_fields, encode_frame, CodecError, IN_COMMISSION_REPORT_MSG_ID,
    IN_EXECUTION_DATA_END_MSG_ID, IN_EXECUTION_DATA_MSG_ID, IN_OPEN_ORDER_END_MSG_ID,
    IN_OPEN_ORDER_MSG_ID, IN_ORDER_STATUS_MSG_ID,
};

// ===========================================================================
// (a) OUT 常數 + 出站 builder（IB 現勘 2026-07-17 pinned;官方 ibapi 9.81.1.post1 sdist）
// 注:OUT 與 IN 是兩個獨立編號空間,5 撞值（OUT reqOpenOrders=5 vs IN OPEN_ORDER=5）——IN
// 空間常數居 `ibkr_tws_wire`（`IN_*`）,此處為 OUT 空間（`OUT_*`）,命名帶方向防混用。
// ===========================================================================

/// OUT 5:reqOpenOrders（綁本 clientId 的 open orders 快照,唯讀）。
pub(crate) const OUT_REQ_OPEN_ORDERS_MSG_ID: &str = "5";
/// OUT 7:reqExecutions（executions 快照,唯讀;之後推送恆在）。
pub(crate) const OUT_REQ_EXECUTIONS_MSG_ID: &str = "7";
/// OUT 16:reqAllOpenOrders(全 client 全量單次,無 client 關聯;唯讀)。
/// 注:OUT 15 reqAutoOpenOrders **不做**——僅 client 0 專屬 auto-bind 語義,本 lane 不用。
pub(crate) const OUT_REQ_ALL_OPEN_ORDERS_MSG_ID: &str = "16";

/// reqOpenOrders / reqAllOpenOrders 的 wire VERSION 欄（IB 現勘:皆為 1）。
const OPEN_ORDERS_OUT_VERSION: &str = "1";
/// reqExecutions 的 wire VERSION 欄（IB 現勘:3）。
const REQ_EXECUTIONS_OUT_VERSION: &str = "3";
/// reqExecutions filter.clientId 欄:官方默認送 `"0"`（其餘 filter 欄恆空,見 builder）。
const EXECUTIONS_FILTER_CLIENT_ID: &str = "0";

/// encode reqExecutions：framed `[7, 3, reqId, filter.clientId, filter.acctCode, filter.time,
/// filter.symbol, filter.secType, filter.exchange, filter.side]`（IB 現勘欄位序）。
/// **恆送空 filter 全量**（clientId 按官方默認送 "0",其餘空字串;time 格式官方自我分歧,
/// 恆空繞開）——以 execId 去重,不以 filter 篩選。
pub(crate) fn encode_req_executions(req_id: i64) -> Vec<u8> {
    let rid = req_id.to_string();
    encode_frame(&encode_fields(&[
        OUT_REQ_EXECUTIONS_MSG_ID,
        REQ_EXECUTIONS_OUT_VERSION,
        &rid,
        EXECUTIONS_FILTER_CLIENT_ID,
        "", // filter.acctCode
        "", // filter.time（官方格式自我分歧 → 恆空繞開）
        "", // filter.symbol
        "", // filter.secType
        "", // filter.exchange
        "", // filter.side
    ]))
}

/// encode reqOpenOrders：framed `[5, 1]`（綁本 clientId;IB 現勘欄位序）。
pub(crate) fn encode_req_open_orders() -> Vec<u8> {
    encode_frame(&encode_fields(&[
        OUT_REQ_OPEN_ORDERS_MSG_ID,
        OPEN_ORDERS_OUT_VERSION,
    ]))
}

/// encode reqAllOpenOrders：framed `[16, 1]`（全量單次,無 client 關聯;IB 現勘欄位序）。
pub(crate) fn encode_req_all_open_orders() -> Vec<u8> {
    encode_frame(&encode_fields(&[
        OUT_REQ_ALL_OPEN_ORDERS_MSG_ID,
        OPEN_ORDERS_OUT_VERSION,
    ]))
}

// ===========================================================================
// (b) config（全 config 化;參數禁假功能——每項必真實被讀取、生效、可觀測）
// ===========================================================================

/// order/exec 消化配置。default = IB 現勘常數（2026-07-17）+ PM DIVERGENT-1 裁決 (a)。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct OrderExecDataConfig {
    /// **floor guard**:協商 sv < 此值 → 整面拒開消化（默認 145 = OPEN_ORDER 無前導 version
    /// 欄門檻;一次覆蓋 136(EXECUTION_DATA)/131(ORDER_STATUS)/145 三門檻,消除雙佈局分支）。
    pub min_server_version_floor: i32,
    /// **ceiling guard**:官方位元組 pin 上界（默認 157）。sv > 此值按 157 佈局 decode,
    /// 定長平面訊息尾端有未讀欄 → 該 frame 拒收+audit（禁猜讀;10.x band 佈局 UNVERIFIED,
    /// 補證歸 operator follow-up）。
    pub max_pinned_server_version: i32,
    /// **exec_time grammar 白名單**:接受 UTC 形 `^\d{8}-\d{2}:\d{2}:\d{2}$`（唯一現行白名單
    /// 項;false → 全 grammar 拒收——config 真功能,測試驗證）。帶 TZ 後綴/雙空格傳統形恆
    /// 拒收（row 級+audit）;EA 活化將要求 operator 設 TWS API 時間=UTC 模式+首批樣本
    /// grammar attestation。
    pub accept_utc_compact_dash_hms: bool,
    /// exec↔commission join 孤兒 TTL:單側先到逾此窗仍未成對 → 計入孤兒計量（觀測用,
    /// 不丟棄——commissionReport 與 execDetails 無到達順序保證,丟棄=記帳謊言）。
    pub join_orphan_ttl: Duration,
    /// executions 新鮮窗:推送事件驅動**無節拍保證** → client 時鐘保守標記,逾窗無事件 →
    /// `Stale`（保守標記非斷言;連線 liveness 由 session 心跳把關;對齊 W5-S2 positions 窗）。
    pub executions_stale_after: Duration,
    /// open orders 新鮮窗（同上事件驅動,無節拍保證）。
    pub open_orders_stale_after: Duration,
}

impl Default for OrderExecDataConfig {
    fn default() -> Self {
        Self {
            min_server_version_floor: 145,
            max_pinned_server_version: 157,
            accept_utc_compact_dash_hms: true,
            join_orphan_ttl: Duration::from_secs(60),
            executions_stale_after: Duration::from_secs(390),
            open_orders_stale_after: Duration::from_secs(390),
        }
    }
}

// ===========================================================================
// (c) typed 裁決（全 typed;禁 panic / 捏值 / 默認值 / silent drop）
// ===========================================================================

/// 消化層 typed 拒絕。呼叫端（driver）分流:`WireMalformed` = wire 損壞 → fail-closed
/// 斷線;其餘 = 資料層 fail-closed（毒化/row 級拒收/typed 計數,session 續 serve,不 panic）。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub(crate) enum OrderExecDataReject {
    /// executions 快照已在途/已成（單槽結構性自限;重取須先斷線或毒化後 re-begin）。
    #[error("executions snapshot already active (engine self-limit = 1 slot)")]
    ExecutionsAlreadyActive,
    /// open orders 快照已在途/已成（同上單槽自限）。
    #[error("open orders snapshot already active (engine self-limit = 1 slot)")]
    OpenOrdersAlreadyActive,
    /// **DIVERGENT-1 floor**:協商 sv 低於 config 下界 → 整面拒開消化（不實作舊佈局分支）。
    #[error("server version {server_version} below order/exec floor {floor}")]
    ServerVersionBelowFloor { server_version: i32, floor: i32 },
    /// 未 begin 任何請求（無 serverVersion context / 槽非活躍）卻收到資料/End——未訂而收=
    /// 協議意外,fail-closed 拒併入（沿 W5-S2 `NoActiveSubscription` 語義）。
    #[error("order/exec frame without active digest context")]
    NoActiveContext,
    /// End 的 reqId 與活躍 executions 快照不符（串流錯配,fail-closed 不轉相位）。
    #[error("unexpected req id {got} for active executions snapshot")]
    UnexpectedReqId { got: i64 },
    /// **DIVERGENT-1 ceiling**:sv>157 且定長平面訊息尾端有未讀欄 → 該 frame 拒收+audit
    /// （10.x band 佈局 UNVERIFIED,禁猜讀;非斷線——佈局成長是 band 內已知可能性）。
    #[error("frame exceeds pinned (sv<=157) layout for msg {msg_id} (refuse to guess-read)")]
    PinnedLayoutOverflow { msg_id: i64 },
    /// exec_time grammar 白名單外 → **row 級拒收**+audit（原字串記 audit 可重放;不毒化——
    /// PM 移交 blocking #2 裁決:拒收粒度=row,快照信心由 audit 計數觀測面承載）。
    #[error("exec_time outside grammar whitelist (row rejected, raw kept in audit)")]
    ExecTimeGrammarRejected,
    /// executions row 契約 blocker（表外 side/secType/幣別/符號紀律…）——資料層 fail-closed:
    /// executions 面毒化 `Invalidated`,不 panic、不斷線、不默默跳行。
    #[error("executions row blocked by contract")]
    ExecutionRowBlocked(Vec<IbkrExecutionsRowBlocker>),
    /// commissions row 契約 blocker（幣別/decimal 紀律…）——同上 executions 面毒化。
    #[error("commissions row blocked by contract")]
    CommissionRowBlocked(Vec<IbkrCommissionsRowBlocker>),
    /// orderStatus 表外 status（含 `ApiPending`）→ `UnknownDenied`:audit 計數 + open-orders
    /// 面毒化（不 crash;無法建模的狀態=該面視圖不可信,fail-closed 側不升格）。
    #[error("order status outside whitelist (UnknownDenied)")]
    OrderStatusUnknownDenied,
    /// orderStatus 欄位值違反本地 typed 紀律（decimal 形狀等）→ open-orders 面毒化。
    #[error("order status field invalid: {field}")]
    OrderStatusFieldInvalid { field: &'static str },
    /// openOrder head 欄位違反白名單/紀律（action/secType/幣別/數量…）→ open-orders 面毒化。
    #[error("open order head denied: {field}")]
    OpenOrderHeadDenied { field: &'static str },
    /// wire 形狀損壞（欄位缺/非數字/非 ASCII/錯 msgId）——呼叫端按既有紀律 fail-closed 斷線。
    #[error("wire malformed: {0}")]
    WireMalformed(CodecError),
}

/// 成交方向/開單 action 白名單（wire `"BUY"`/`"SELL"`;表外 fail-closed 拒）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum IbkrOrderActionV1 {
    Buy,
    Sell,
    /// 白名單外 action 的 fail-closed 分類（消化端必拒）。
    UnknownDenied,
}

impl IbkrOrderActionV1 {
    /// wire action 字串 → 白名單枚舉（大小寫敏感精確匹配;表外一律 `UnknownDenied`）。
    fn classify_wire_action(raw: &str) -> Self {
        match raw {
            "BUY" => Self::Buy,
            "SELL" => Self::Sell,
            _ => Self::UnknownDenied,
        }
    }
}

/// orderStatus status 白名單（IB 現勘 pinned 8 值;表外含 `ApiPending` → `UnknownDenied`,
/// audit 不 crash）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum IbkrOrderStatusV1 {
    PendingSubmit,
    PendingCancel,
    PreSubmitted,
    Submitted,
    ApiCancelled,
    Cancelled,
    Filled,
    Inactive,
    /// 表外 status 的 fail-closed 分類（audit 計數,消化端拒併入）。
    UnknownDenied,
}

impl IbkrOrderStatusV1 {
    /// wire status 字串 → 白名單枚舉（大小寫敏感精確匹配;表外一律 `UnknownDenied`）。
    fn classify_wire_status(raw: &str) -> Self {
        match raw {
            "PendingSubmit" => Self::PendingSubmit,
            "PendingCancel" => Self::PendingCancel,
            "PreSubmitted" => Self::PreSubmitted,
            "Submitted" => Self::Submitted,
            "ApiCancelled" => Self::ApiCancelled,
            "Cancelled" => Self::Cancelled,
            "Filled" => Self::Filled,
            "Inactive" => Self::Inactive,
            _ => Self::UnknownDenied,
        }
    }
}

/// orderStatus 最小 typed 快照行（本地 typed;無 types 契約——orderStatus 非 W5-S1 row 面,
/// 本地白名單+decimal 紀律把守）。官方明言 orderStatus 常有重複 → 冪等去重見
/// `same_wire_facts`。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct IbkrOrderStatusSnapshotV1 {
    pub order_id: i64,
    pub status: IbkrOrderStatusV1,
    pub filled_decimal: String,
    pub remaining_decimal: String,
    pub avg_fill_price_decimal: String,
    pub perm_id: i64,
    pub parent_id: i64,
    pub last_fill_price_decimal: String,
    pub client_id: i64,
    /// whyHeld 原字串保真（可空;IB 慣例如 "locate"）。
    pub why_held: String,
    pub mkt_cap_price_decimal: String,
    /// client 側捕捉時鐘（注入;不參與去重比較）。
    pub captured_at_ms: u64,
}

impl IbkrOrderStatusSnapshotV1 {
    /// 冪等去重判據:wire 事實欄全等（**排除** `captured_at_ms`——重複推送的到達時刻不同
    /// 不代表新事實;官方明言 orderStatus 常有重複）。
    fn same_wire_facts(&self, other: &Self) -> bool {
        self.order_id == other.order_id
            && self.status == other.status
            && self.filled_decimal == other.filled_decimal
            && self.remaining_decimal == other.remaining_decimal
            && self.avg_fill_price_decimal == other.avg_fill_price_decimal
            && self.perm_id == other.perm_id
            && self.parent_id == other.parent_id
            && self.last_fill_price_decimal == other.last_fill_price_decimal
            && self.client_id == other.client_id
            && self.why_held == other.why_held
            && self.mkt_cap_price_decimal == other.mkt_cap_price_decimal
    }
}

/// openOrder **head-prefix 最小 typed 行**（PM descope 裁決:head 前綴平面欄讀到 permId 止,
/// frame 剩餘位元組整體丟棄+audit 計數;66 步/變長塊全欄 decode 明確 defer——TWS 訊框帶
/// 長度前綴,tail-discard 確定性安全）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct IbkrOpenOrderHeadV1 {
    pub order_id: i64,
    pub con_id: i64,
    pub symbol: String,
    pub sec_type: IbkrSecTypeV1,
    /// Contract.exchange 原字串保真（head 內唯一 exchange 欄;成交所語義歸 executions row）。
    pub exchange: String,
    pub currency: StockEtfCurrency,
    pub action: IbkrOrderActionV1,
    pub total_quantity_decimal: String,
    /// orderType 原字串保真（LMT/MKT…;白名單歸 W7 order lifecycle,本面唯讀承載）。
    pub order_type: String,
    /// lmtPrice:wire 空欄=unset → `None`（禁折 0——0 是合法價格,語義不可混用）。
    pub lmt_price_decimal: Option<String>,
    /// auxPrice:同上空欄=unset → `None`。
    pub aux_price_decimal: Option<String>,
    pub tif: String,
    pub oca_group: String,
    pub account_id: String,
    pub open_close: String,
    pub origin: String,
    pub order_ref: String,
    pub client_id: i64,
    pub perm_id: i64,
    /// client 側捕捉時鐘（注入）。
    pub captured_at_ms: u64,
}

/// exec↔commission either-order join 槽（execId 鍵;兩側先到皆緩存,join 完整對=typed
/// 完整成交紀錄）。
#[derive(Debug, Clone)]
pub(crate) struct ExecJoinSlot {
    pub execution: Option<IbkrExecutionsRowV1>,
    pub commission: Option<IbkrCommissionsRowV1>,
    /// 首側到達時刻（孤兒 TTL 計量基準）。
    pub first_seen_ms: u64,
}

impl ExecJoinSlot {
    /// join 完整對（typed 完整成交紀錄的判據）。
    pub(crate) fn is_complete(&self) -> bool {
        self.execution.is_some() && self.commission.is_some()
    }
}

/// 孤兒計量報告（觀測用;不丟棄任何一側——無到達順序保證下丟棄=記帳謊言）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub(crate) struct JoinOrphanReport {
    /// execution 先到、commission 未到的槽數。
    pub executions_awaiting_commission: usize,
    /// commission 先到、execution 未到的槽數。
    pub commissions_awaiting_execution: usize,
    /// 上兩類中逾 `join_orphan_ttl` 仍未成對者（degraded 信號）。
    pub over_ttl: usize,
}

/// audit 計數器（typed 觀測面;全部單調遞增,driver/W6 IPC 投影唯讀消費）。
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub(crate) struct OrderExecAudit {
    /// realizedPNL 哨兵→None 判別命中數（雙判別:精確字串 or |v|≥1.0e308）。
    pub realized_pnl_sentinel_hits: u64,
    /// 最後一次哨兵命中的原始字串（EA 校準/重放用;空欄→None 不計此處——空=誠實缺席）。
    pub realized_pnl_sentinel_last_raw: Option<String>,
    /// exec_time grammar 白名單外 row 級拒收數。
    pub exec_time_grammar_rejects: u64,
    /// 最後一次 grammar 拒收的原始 exec_time（可重放）。
    pub exec_time_grammar_last_raw: Option<String>,
    /// unsolicited 通道承接的 execution 行數（reqId 與活躍快照不符,慣稱 -1;禁丟棄）。
    pub unsolicited_execution_rows: u64,
    /// 同 execId 重複 execution 行數（快照/推送重疊;後到覆蓋）。
    pub duplicate_execution_rows: u64,
    /// 同 execId 重複 commission 行數（後到覆蓋）。
    pub duplicate_commission_rows: u64,
    /// orderStatus 冪等去重命中數（wire 事實全等的重複推送）。
    pub duplicate_order_status_rows: u64,
    /// orderStatus 表外 status（UnknownDenied,含 ApiPending）數。
    pub order_status_unknown_denied: u64,
    /// openOrder head 之後整體丟棄的 tail 欄位數（descope 觀測;66 步全欄 decode defer）。
    pub open_order_tail_fields_discarded: u64,
    /// ceiling 佈局窗拒收 frame 數（sv>157 尾端未讀欄;10.x band 補證信號）。
    pub pinned_layout_overflow_rejects: u64,
}

/// 單槽生命週期相位（同構 W5-S2 `SubPhase`——該型別為模塊私有,此處同名同義複刻,
/// 不越界改動 account_data）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SubPhase {
    Idle,
    /// 已發快照請求,End 前（首回全量進行中）。
    SnapshotIncomplete,
    /// End 已到:executions=推送恆在;open orders=事件驅動推送。
    Live,
    /// 契約 blocker / 表外分類毒化（fail-closed;唯 re-begin 離開）。
    Invalidated,
    /// 斷線失效（唯 re-begin 離開;快照不跨連線存活）。
    DisconnectedStale,
}

impl SubPhase {
    fn is_active(self) -> bool {
        matches!(self, SubPhase::SnapshotIncomplete | SubPhase::Live)
    }
}

// ===========================================================================
// (d) OrderExecDataDigest — 快照/推送狀態機 + join + audit
// ===========================================================================

/// IN 訊息定長平面欄數（IB 現勘 pinned,serverVersion≥136/131 無前導 version 欄）。
const EXECUTION_DATA_EXACT_FIELDS: usize = 31;
const COMMISSION_REPORT_EXACT_FIELDS: usize = 8;
const ORDER_STATUS_EXACT_FIELDS: usize = 12;
const EXECUTION_DATA_END_EXACT_FIELDS: usize = 3;
const OPEN_ORDER_END_EXACT_FIELDS: usize = 2;
/// OPEN_ORDER head 前綴欄數（msgId..permId;其後 tail 整體丟棄）。
const OPEN_ORDER_HEAD_MIN_FIELDS: usize = 26;

/// realizedPNL 精確哨兵字串（f64::MAX 的官方十進位形;比對大小寫不敏感於 `E`）。
const REALIZED_PNL_SENTINEL_EXACT: &str = "1.7976931348623157E308";
/// realizedPNL 量級哨兵下界（解析後 |v|≥此值即哨兵嫌疑;f64 僅作判別,契約承載仍定點字串）。
const REALIZED_PNL_SENTINEL_MAGNITUDE: f64 = 1.0e308;

/// open orders / executions 消化器。純同步、注入時鐘;executions/commissions 行以 W5-S1
/// 契約承載（`validate()` 過才併入），orderStatus/openOrder 以本地最小 typed 行承載。
/// 出站 frame 由 `begin_*` 產出,**送出必經 pacing 單一出口**（呼叫端持 `OutboundGrant`
/// 才可 `send_framed`）。
pub(crate) struct OrderExecDataDigest {
    config: OrderExecDataConfig,
    /// begin 時綁定的協商 serverVersion（=消化 context;`None`=整面未開,入站全拒。
    /// floor guard 於 begin 把關 → 綁定值恆 ≥ floor）。
    server_version: Option<i32>,
    /// 快照單調序列（每次 begin_* 遞增;telemetry 語義,沿 W5-S2）。
    snapshot_seq: u64,
    // ---- executions 槽（單槽結構性自限）----
    exec_phase: SubPhase,
    exec_req_id: Option<i64>,
    /// execId → join 槽（BTreeMap=確定序;execId 去重鍵）。
    exec_slots: BTreeMap<String, ExecJoinSlot>,
    exec_last_update_ms: u64,
    // ---- open orders 槽（單槽;openOrder head + orderStatus 同面）----
    orders_phase: SubPhase,
    open_orders: BTreeMap<i64, IbkrOpenOrderHeadV1>,
    order_statuses: BTreeMap<i64, IbkrOrderStatusSnapshotV1>,
    orders_last_update_ms: u64,
    audit: OrderExecAudit,
}

impl OrderExecDataDigest {
    pub(crate) fn new(config: OrderExecDataConfig) -> Self {
        Self {
            config,
            server_version: None,
            snapshot_seq: 0,
            exec_phase: SubPhase::Idle,
            exec_req_id: None,
            exec_slots: BTreeMap::new(),
            exec_last_update_ms: 0,
            orders_phase: SubPhase::Idle,
            open_orders: BTreeMap::new(),
            order_statuses: BTreeMap::new(),
            orders_last_update_ms: 0,
            audit: OrderExecAudit::default(),
        }
    }

    // ---- 出站意圖（快照生命週期;送出經 pacing 單一出口,見模塊硬邊界）----

    /// **DIVERGENT-1 floor**:協商 sv < config 下界 → 整面拒開（不實作 <145 舊佈局分支）。
    fn floor_guard(&self, server_version: i32) -> Result<(), OrderExecDataReject> {
        if server_version < self.config.min_server_version_floor {
            return Err(OrderExecDataReject::ServerVersionBelowFloor {
                server_version,
                floor: self.config.min_server_version_floor,
            });
        }
        Ok(())
    }

    /// 開始 executions 快照:回待送 reqExecutions frame（空 filter 全量）。floor guard →
    /// 單槽自限 → 清舊槽、遞增 seq、綁定 sv context。Idle/Invalidated/DisconnectedStale
    /// 可（重）取——**斷線 resync 語義**:重連後 re-begin 即全量重取,execId 去重吸收與
    /// 斷線前推送的重疊。
    pub(crate) fn begin_executions(
        &mut self,
        server_version: i32,
        req_id: i64,
    ) -> Result<Vec<u8>, OrderExecDataReject> {
        self.floor_guard(server_version)?;
        if self.exec_phase.is_active() {
            return Err(OrderExecDataReject::ExecutionsAlreadyActive);
        }
        self.server_version = Some(server_version);
        self.snapshot_seq += 1;
        self.exec_slots.clear();
        self.exec_phase = SubPhase::SnapshotIncomplete;
        self.exec_req_id = Some(req_id);
        Ok(encode_req_executions(req_id))
    }

    /// 開始 open orders 快照（本 clientId 綁定形）:回待送 reqOpenOrders frame。
    pub(crate) fn begin_open_orders(
        &mut self,
        server_version: i32,
    ) -> Result<Vec<u8>, OrderExecDataReject> {
        self.begin_open_orders_slot(server_version)?;
        Ok(encode_req_open_orders())
    }

    /// 開始 open orders 快照（全量形 reqAllOpenOrders;**同一槽**——單槽自限對兩形共同
    /// 生效,不並行雙快照）。
    pub(crate) fn begin_all_open_orders(
        &mut self,
        server_version: i32,
    ) -> Result<Vec<u8>, OrderExecDataReject> {
        self.begin_open_orders_slot(server_version)?;
        Ok(encode_req_all_open_orders())
    }

    fn begin_open_orders_slot(&mut self, server_version: i32) -> Result<(), OrderExecDataReject> {
        self.floor_guard(server_version)?;
        if self.orders_phase.is_active() {
            return Err(OrderExecDataReject::OpenOrdersAlreadyActive);
        }
        self.server_version = Some(server_version);
        self.snapshot_seq += 1;
        self.open_orders.clear();
        self.order_statuses.clear();
        self.orders_phase = SubPhase::SnapshotIncomplete;
        Ok(())
    }

    // ---- 入站消化（payload = 已 unframe 的欄位序,含 msgId 欄）----

    /// 定長平面訊息的欄數裁決（DIVERGENT-1 ceiling 語義集中點）:
    ///   - 欄數 < exact → `WireMalformed`（佈局只增不減,缺欄=損壞）;
    ///   - 欄數 > exact 且 sv>157 → `PinnedLayoutOverflow`+audit（band 內佈局成長,拒收該
    ///     frame 不斷線）;
    ///   - 欄數 > exact 且 sv≤157（或 context 未綁）→ `WireMalformed`（pinned 佈局下多欄=
    ///     wire 意外,沿 W5-S2 F2 精確欄長紀律;context 未綁時保守取斷線側）。
    fn exact_len_verdict(
        &mut self,
        msg_id: i64,
        got: usize,
        exact: usize,
        malformed_note: &'static str,
    ) -> Result<(), OrderExecDataReject> {
        if got < exact {
            return Err(OrderExecDataReject::WireMalformed(CodecError::Malformed(
                malformed_note,
            )));
        }
        if got > exact {
            match self.server_version {
                Some(sv) if sv > self.config.max_pinned_server_version => {
                    self.audit.pinned_layout_overflow_rejects += 1;
                    return Err(OrderExecDataReject::PinnedLayoutOverflow { msg_id });
                }
                _ => {
                    return Err(OrderExecDataReject::WireMalformed(CodecError::Malformed(
                        malformed_note,
                    )))
                }
            }
        }
        Ok(())
    }

    /// IN 11 execDetails 行（sv≥136 無前導 version 欄;IB 現勘欄位序,31 定長平面欄）:
    /// `[11, reqId, orderId, Contract(conId..tradingClass ×11), Execution(execId, time,
    /// acctNumber, exchange, side, shares, price, permId, clientId, liquidation, cumQty,
    /// avgPrice, orderRef, evRule, evMultiplier, modelCode, lastLiquidity)]`。
    /// **兩個 exchange 欄**:row 契約的 exchange 必綁 **Execution.exchange（idx 17,成交所）**
    /// 非 Contract.exchange（idx 10）——fixture 以兩欄不同值斷言取後者。中間欄全定長平面,
    /// 按位跳讀安全（liquidation/cumQty/avgPrice/orderRef/evRule/evMultiplier/modelCode/
    /// lastLiquidity 讀位即棄,不 bind 語義）。
    pub(crate) fn on_execution_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), OrderExecDataReject> {
        let fields = decode_fields(payload).map_err(OrderExecDataReject::WireMalformed)?;
        if fields.is_empty() {
            return Err(OrderExecDataReject::WireMalformed(CodecError::Malformed(
                "empty execution frame",
            )));
        }
        expect_msg_id(&fields[0], IN_EXECUTION_DATA_MSG_ID)?;
        self.exact_len_verdict(
            IN_EXECUTION_DATA_MSG_ID,
            fields.len(),
            EXECUTION_DATA_EXACT_FIELDS,
            "execution data needs exactly 31 fields (sv<=157 layout)",
        )?;
        // 數字欄 wire 形狀先裁（N1 紀律:wire 損壞裁決先於訂閱狀態,禁未訂窗口靜默吞損壞）。
        let req_id = parse_i64(&fields[1], "exec_req_id")?;
        let order_id = parse_i64(&fields[2], "exec_order_id")?;
        let con_id = parse_i64(&fields[3], "exec_con_id")?;
        let perm_id = parse_i64(&fields[21], "exec_perm_id")?;
        if !self.exec_phase.is_active() {
            return Err(OrderExecDataReject::NoActiveContext);
        }
        // exec_time grammar 白名單（移交 blocking #2）:白名單外 → row 級拒收+audit,原字串
        // 記 audit 可重放;不毒化（PM 裁決粒度=row,見 reject 型注釋）。
        let exec_time = &fields[15];
        if !self.exec_time_grammar_ok(exec_time) {
            self.audit.exec_time_grammar_rejects += 1;
            self.audit.exec_time_grammar_last_raw = Some(exec_time.clone());
            return Err(OrderExecDataReject::ExecTimeGrammarRejected);
        }
        let row = IbkrExecutionsRowV1 {
            contract_id: IBKR_EXECUTIONS_ROW_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: openclaw_types::AssetLane::StockEtfCash,
            broker: openclaw_types::Broker::Ibkr,
            account_id: fields[16].clone(),
            exec_id: fields[14].clone(),
            con_id,
            symbol: fields[4].clone(),
            sec_type: IbkrSecTypeV1::classify_wire_sec_type(&fields[5]),
            currency: classify_wire_currency(&fields[11]),
            order_id,
            perm_id,
            exec_time: exec_time.clone(),
            side: IbkrExecutionSideV1::classify_wire_side(&fields[18]),
            shares_decimal: fields[19].clone(),
            price_decimal: fields[20].clone(),
            // 兩 exchange 欄:必綁 Execution.exchange(idx 17,成交所),非 Contract.exchange(idx 10)。
            exchange: fields[17].clone(),
            order_routed: false,
            secret_content_serialized: false,
        };
        let verdict = row.validate();
        if !verdict.accepted {
            // 契約 blocker → executions 面毒化,fail-closed 不併入（沿 W5-S2 blocker=毒化）。
            self.exec_phase = SubPhase::Invalidated;
            return Err(OrderExecDataReject::ExecutionRowBlocked(verdict.blockers));
        }
        // unsolicited 通道:reqId 與活躍快照不符（推送慣稱 -1,無官方位元組證 → 未知/負值
        // 一體承接+計數,禁按 pending 匹配失敗丟棄）。
        if self.exec_req_id != Some(req_id) {
            self.audit.unsolicited_execution_rows += 1;
        }
        let exec_id = row.exec_id.clone();
        let slot = self.exec_slots.entry(exec_id).or_insert(ExecJoinSlot {
            execution: None,
            commission: None,
            first_seen_ms: now_ms,
        });
        if slot.execution.is_some() {
            // 快照/推送重疊的同 execId 重複行:後到覆蓋+計數（execId 去重紀律）。
            self.audit.duplicate_execution_rows += 1;
        }
        slot.execution = Some(row);
        self.exec_last_update_ms = now_ms;
        Ok(())
    }

    /// IN 55 execDetailsEnd（`[55, version, reqId]`;出典 官方 ibapi 9.81.1
    /// `processExecutionDataEndMsg`）:快照收批 → `Live`（**之後推送恆在**——成交自動推
    /// execDetails+commissionReport,unsolicited 通道續收）。
    pub(crate) fn on_execution_end_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), OrderExecDataReject> {
        let fields = decode_fields(payload).map_err(OrderExecDataReject::WireMalformed)?;
        if fields.is_empty() {
            return Err(OrderExecDataReject::WireMalformed(CodecError::Malformed(
                "empty execution end frame",
            )));
        }
        expect_msg_id(&fields[0], IN_EXECUTION_DATA_END_MSG_ID)?;
        self.exact_len_verdict(
            IN_EXECUTION_DATA_END_MSG_ID,
            fields.len(),
            EXECUTION_DATA_END_EXACT_FIELDS,
            "execution end needs exactly 3 fields",
        )?;
        let req_id = parse_i64(&fields[2], "exec_end_req_id")?;
        if !self.exec_phase.is_active() {
            return Err(OrderExecDataReject::NoActiveContext);
        }
        if self.exec_req_id != Some(req_id) {
            return Err(OrderExecDataReject::UnexpectedReqId { got: req_id });
        }
        self.exec_phase = SubPhase::Live;
        self.exec_last_update_ms = now_ms;
        Ok(())
    }

    /// IN 59 commissionReport（前導 version 恆在,無 sv 門控;IB 現勘欄位序 8 定長平面欄）:
    /// `[59, version, execId, commission, currency, realizedPNL, yield_, yieldRedemptionDate]`
    /// （yield_/yieldRedemptionDate 讀位即棄）。realizedPNL 走哨兵雙判別 → `None`（移交
    /// blocking #1）;execId 鍵 either-order join(commission 先到=孤兒緩存,禁丟棄)。
    pub(crate) fn on_commission_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), OrderExecDataReject> {
        let fields = decode_fields(payload).map_err(OrderExecDataReject::WireMalformed)?;
        if fields.is_empty() {
            return Err(OrderExecDataReject::WireMalformed(CodecError::Malformed(
                "empty commission frame",
            )));
        }
        expect_msg_id(&fields[0], IN_COMMISSION_REPORT_MSG_ID)?;
        self.exact_len_verdict(
            IN_COMMISSION_REPORT_MSG_ID,
            fields.len(),
            COMMISSION_REPORT_EXACT_FIELDS,
            "commission report needs exactly 8 fields",
        )?;
        // version 欄 wire 形狀先裁（恆在,非數字=損壞）。
        let _version = parse_i64(&fields[1], "commission_version")?;
        if !self.exec_phase.is_active() {
            return Err(OrderExecDataReject::NoActiveContext);
        }
        let realized_pnl_decimal = self.classify_realized_pnl(&fields[5]);
        let row = IbkrCommissionsRowV1 {
            contract_id: IBKR_COMMISSIONS_ROW_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: openclaw_types::AssetLane::StockEtfCash,
            broker: openclaw_types::Broker::Ibkr,
            exec_id: fields[2].clone(),
            commission_decimal: fields[3].clone(),
            currency: classify_wire_currency(&fields[4]),
            realized_pnl_decimal,
            order_routed: false,
            secret_content_serialized: false,
        };
        let verdict = row.validate();
        if !verdict.accepted {
            // 契約 blocker → executions 面毒化（commission 屬成交記帳同一面）。
            self.exec_phase = SubPhase::Invalidated;
            return Err(OrderExecDataReject::CommissionRowBlocked(verdict.blockers));
        }
        let exec_id = row.exec_id.clone();
        let slot = self.exec_slots.entry(exec_id).or_insert(ExecJoinSlot {
            execution: None,
            commission: None,
            first_seen_ms: now_ms,
        });
        if slot.commission.is_some() {
            self.audit.duplicate_commission_rows += 1;
        }
        slot.commission = Some(row);
        self.exec_last_update_ms = now_ms;
        Ok(())
    }

    /// IN 3 orderStatus（sv≥131 無前導 version 欄;IB 現勘欄位序 12 定長平面欄）:
    /// `[3, orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice,
    /// clientId, whyHeld, mktCapPrice]`。status 白名單 8 值;表外（含 `ApiPending`）→
    /// `UnknownDenied` audit+毒化不 crash。官方明言常有重複 → **冪等去重**（wire 事實全等
    /// → 計數後 no-op）。
    pub(crate) fn on_order_status_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), OrderExecDataReject> {
        let fields = decode_fields(payload).map_err(OrderExecDataReject::WireMalformed)?;
        if fields.is_empty() {
            return Err(OrderExecDataReject::WireMalformed(CodecError::Malformed(
                "empty order status frame",
            )));
        }
        expect_msg_id(&fields[0], IN_ORDER_STATUS_MSG_ID)?;
        self.exact_len_verdict(
            IN_ORDER_STATUS_MSG_ID,
            fields.len(),
            ORDER_STATUS_EXACT_FIELDS,
            "order status needs exactly 12 fields (sv<=157 layout)",
        )?;
        let order_id = parse_i64(&fields[1], "order_status_order_id")?;
        let perm_id = parse_i64(&fields[6], "order_status_perm_id")?;
        let parent_id = parse_i64(&fields[7], "order_status_parent_id")?;
        let client_id = parse_i64(&fields[9], "order_status_client_id")?;
        if !self.orders_phase.is_active() {
            return Err(OrderExecDataReject::NoActiveContext);
        }
        let status = IbkrOrderStatusV1::classify_wire_status(&fields[2]);
        if status == IbkrOrderStatusV1::UnknownDenied {
            // 表外 status（含 ApiPending）:audit 計數 + open-orders 面毒化——無法建模的狀態
            // = 該面視圖不可信（fail-closed 側不升格;不 crash,session 續 serve）。
            self.audit.order_status_unknown_denied += 1;
            self.orders_phase = SubPhase::Invalidated;
            return Err(OrderExecDataReject::OrderStatusUnknownDenied);
        }
        // 本地 decimal 紀律（orderStatus 無 types 契約,本地把守;`0` 合法——filled=0 常態）。
        for (idx, field) in [
            (3usize, "filled"),
            (4, "remaining"),
            (5, "avg_fill_price"),
            (8, "last_fill_price"),
            (11, "mkt_cap_price"),
        ] {
            if !is_signed_decimal_string(&fields[idx]) {
                self.orders_phase = SubPhase::Invalidated;
                return Err(OrderExecDataReject::OrderStatusFieldInvalid { field });
            }
        }
        let row = IbkrOrderStatusSnapshotV1 {
            order_id,
            status,
            filled_decimal: fields[3].clone(),
            remaining_decimal: fields[4].clone(),
            avg_fill_price_decimal: fields[5].clone(),
            perm_id,
            parent_id,
            last_fill_price_decimal: fields[8].clone(),
            client_id,
            why_held: fields[10].clone(),
            mkt_cap_price_decimal: fields[11].clone(),
            captured_at_ms: now_ms,
        };
        if let Some(existing) = self.order_statuses.get(&order_id) {
            if existing.same_wire_facts(&row) {
                // 冪等去重:重複推送計數後 no-op（不更新 captured_at——重複非新事實）。
                self.audit.duplicate_order_status_rows += 1;
                return Ok(());
            }
        }
        self.order_statuses.insert(order_id, row);
        self.orders_last_update_ms = now_ms;
        Ok(())
    }

    /// IN 5 openOrder（sv≥145 無前導 version 欄）= **head-prefix 最小消化**（PM descope
    /// 裁決）:head 平面欄 `[5, orderId, Contract(conId..tradingClass ×11), action,
    /// totalQuantity, orderType, lmtPrice(空欄=unset), auxPrice(空欄=unset), tif, ocaGroup,
    /// account, openClose, origin, orderRef, clientId, permId]` 讀到 permId（idx 25）止,
    /// **frame 剩餘欄位整體丟棄+audit 計數**（TWS 訊框帶長度前綴,tail-discard 確定性
    /// 安全);66 步/變長塊全欄 decode 明確 defer。
    pub(crate) fn on_open_order_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), OrderExecDataReject> {
        let fields = decode_fields(payload).map_err(OrderExecDataReject::WireMalformed)?;
        if fields.is_empty() {
            return Err(OrderExecDataReject::WireMalformed(CodecError::Malformed(
                "empty open order frame",
            )));
        }
        expect_msg_id(&fields[0], IN_OPEN_ORDER_MSG_ID)?;
        // head-prefix 消化:缺 head 欄=損壞;多欄=tail(丟棄+計數),**不**走 exact 紀律——
        // openOrder 對 ceiling 佈局成長天然容忍（見 MODULE_NOTE DIVERGENT-1）。
        if fields.len() < OPEN_ORDER_HEAD_MIN_FIELDS {
            return Err(OrderExecDataReject::WireMalformed(CodecError::Malformed(
                "open order needs >=26 head fields",
            )));
        }
        let order_id = parse_i64(&fields[1], "open_order_order_id")?;
        let con_id = parse_i64(&fields[2], "open_order_con_id")?;
        let client_id = parse_i64(&fields[24], "open_order_client_id")?;
        let perm_id = parse_i64(&fields[25], "open_order_perm_id")?;
        if !self.orders_phase.is_active() {
            return Err(OrderExecDataReject::NoActiveContext);
        }
        // Contract 佔位欄按位消費（idx 5=lastTradeDateOrContractMonth / 6=strike / 7=right /
        // 8=multiplier / 11=localSymbol / 12=tradingClass）:讀位即棄,不 bind 語義。
        let tail = (fields.len() - OPEN_ORDER_HEAD_MIN_FIELDS) as u64;
        // 本地白名單/紀律把守（openOrder 無 types 契約;denied → open-orders 面毒化）。
        let sec_type = IbkrSecTypeV1::classify_wire_sec_type(&fields[4]);
        let currency = classify_wire_currency(&fields[10]);
        let action = IbkrOrderActionV1::classify_wire_action(&fields[13]);
        let denied: Option<&'static str> = if con_id <= 0 {
            Some("con_id")
        } else if !is_normalized_symbol(&fields[3]) {
            Some("symbol")
        } else if sec_type == IbkrSecTypeV1::UnknownDenied {
            Some("sec_type")
        } else if currency != StockEtfCurrency::Usd {
            Some("currency")
        } else if action == IbkrOrderActionV1::UnknownDenied {
            Some("action")
        } else if !is_positive_decimal_string(&fields[14]) {
            Some("total_quantity")
        } else if fields[20].trim().is_empty() {
            Some("account")
        } else {
            None
        };
        if let Some(field) = denied {
            self.orders_phase = SubPhase::Invalidated;
            return Err(OrderExecDataReject::OpenOrderHeadDenied { field });
        }
        // 價格欄:空欄=unset → None（禁折 0）;非空必為簽名定點字串。
        let lmt_price_decimal = classify_optional_price(&fields[16], "lmt_price")
            .map_err(|field| self.deny_open_order(field))?;
        let aux_price_decimal = classify_optional_price(&fields[17], "aux_price")
            .map_err(|field| self.deny_open_order(field))?;
        let row = IbkrOpenOrderHeadV1 {
            order_id,
            con_id,
            symbol: fields[3].clone(),
            sec_type,
            exchange: fields[9].clone(),
            currency,
            action,
            total_quantity_decimal: fields[14].clone(),
            order_type: fields[15].clone(),
            lmt_price_decimal,
            aux_price_decimal,
            tif: fields[18].clone(),
            oca_group: fields[19].clone(),
            account_id: fields[20].clone(),
            open_close: fields[21].clone(),
            origin: fields[22].clone(),
            order_ref: fields[23].clone(),
            client_id,
            perm_id,
            captured_at_ms: now_ms,
        };
        self.audit.open_order_tail_fields_discarded += tail;
        self.open_orders.insert(order_id, row);
        self.orders_last_update_ms = now_ms;
        Ok(())
    }

    /// openOrder head denied 的毒化副作用收斂點（`map_err` 閉包內需 `&mut self`）。
    fn deny_open_order(&mut self, field: &'static str) -> OrderExecDataReject {
        self.orders_phase = SubPhase::Invalidated;
        OrderExecDataReject::OpenOrderHeadDenied { field }
    }

    /// IN 53 openOrderEnd（`[53, version]`;出典 官方 ibapi 9.81.1 `processOpenOrderEndMsg`）:
    /// 快照收批 → `Live`（其後本 client 綁定推送續收）。
    pub(crate) fn on_open_order_end_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), OrderExecDataReject> {
        let fields = decode_fields(payload).map_err(OrderExecDataReject::WireMalformed)?;
        if fields.is_empty() {
            return Err(OrderExecDataReject::WireMalformed(CodecError::Malformed(
                "empty open order end frame",
            )));
        }
        expect_msg_id(&fields[0], IN_OPEN_ORDER_END_MSG_ID)?;
        self.exact_len_verdict(
            IN_OPEN_ORDER_END_MSG_ID,
            fields.len(),
            OPEN_ORDER_END_EXACT_FIELDS,
            "open order end needs exactly 2 fields",
        )?;
        if !self.orders_phase.is_active() {
            return Err(OrderExecDataReject::NoActiveContext);
        }
        self.orders_phase = SubPhase::Live;
        self.orders_last_update_ms = now_ms;
        Ok(())
    }

    // ---- 生命週期:斷線 ----

    /// 斷線:活躍面一律標 `DisconnectedStale`（快照/推送不跨連線存活——**重連需 re-begin
    /// resync**,execId 去重吸收重疊;行保留供唯讀檢視,staleness 已明示不可信）。
    /// Idle/Invalidated 維持原相位（毒化事實不被斷線沖淡,沿 W5-S2）。
    pub(crate) fn on_disconnect(&mut self) {
        if self.exec_phase.is_active() {
            self.exec_phase = SubPhase::DisconnectedStale;
            self.exec_req_id = None;
        }
        if self.orders_phase.is_active() {
            self.orders_phase = SubPhase::DisconnectedStale;
        }
    }

    // ---- 觀測（typed staleness + 唯讀行檢視 + audit）----

    /// executions 面 staleness（typed 六態;推送事件驅動無節拍保證 → client 時鐘窗保守標記）。
    pub(crate) fn executions_staleness(&self, now_ms: u64) -> SnapshotStaleness {
        staleness_of(
            self.exec_phase,
            self.exec_last_update_ms,
            self.config.executions_stale_after,
            now_ms,
        )
    }

    /// open orders 面 staleness（typed 六態）。
    pub(crate) fn open_orders_staleness(&self, now_ms: u64) -> SnapshotStaleness {
        staleness_of(
            self.orders_phase,
            self.orders_last_update_ms,
            self.config.open_orders_stale_after,
            now_ms,
        )
    }

    /// 唯讀檢視:全部 join 槽（BTreeMap=確定序;含孤兒側）。
    pub(crate) fn exec_slots(&self) -> impl Iterator<Item = (&String, &ExecJoinSlot)> {
        self.exec_slots.iter()
    }

    /// 唯讀檢視:join 完整對（execution+commission 齊 = typed 完整成交紀錄）。
    pub(crate) fn completed_executions(
        &self,
    ) -> impl Iterator<Item = (&IbkrExecutionsRowV1, &IbkrCommissionsRowV1)> {
        self.exec_slots.values().filter_map(|s| {
            match (s.execution.as_ref(), s.commission.as_ref()) {
                (Some(e), Some(c)) => Some((e, c)),
                _ => None,
            }
        })
    }

    /// 孤兒計量（觀測;逾 `join_orphan_ttl` 未成對 → over_ttl,degraded 信號,不丟棄）。
    pub(crate) fn join_orphans(&self, now_ms: u64) -> JoinOrphanReport {
        let ttl_ms = self.config.join_orphan_ttl.as_millis() as u64;
        let mut report = JoinOrphanReport::default();
        for slot in self.exec_slots.values() {
            if slot.is_complete() {
                continue;
            }
            if slot.execution.is_some() {
                report.executions_awaiting_commission += 1;
            } else {
                report.commissions_awaiting_execution += 1;
            }
            if now_ms.saturating_sub(slot.first_seen_ms) > ttl_ms {
                report.over_ttl += 1;
            }
        }
        report
    }

    /// 唯讀檢視:openOrder head 行（BTreeMap=確定序）。
    pub(crate) fn open_orders(&self) -> impl Iterator<Item = &IbkrOpenOrderHeadV1> {
        self.open_orders.values()
    }

    /// 唯讀檢視:orderStatus 最新快照行。
    pub(crate) fn order_statuses(&self) -> impl Iterator<Item = &IbkrOrderStatusSnapshotV1> {
        self.order_statuses.values()
    }

    /// audit 計數器唯讀檢視。
    pub(crate) fn audit(&self) -> &OrderExecAudit {
        &self.audit
    }

    /// 當前快照世代序（telemetry）。
    pub(crate) fn snapshot_seq(&self) -> u64 {
        self.snapshot_seq
    }

    // ---- 內部 ----

    /// exec_time grammar 白名單:唯一現行白名單項=UTC 形 `^\d{8}-\d{2}:\d{2}:\d{2}$`
    /// （config 可關,關=全拒——fail-closed 真功能）。手寫定長比對,不引 regex 依賴。
    fn exec_time_grammar_ok(&self, raw: &str) -> bool {
        if !self.config.accept_utc_compact_dash_hms {
            return false;
        }
        let b = raw.as_bytes();
        b.len() == 17
            && b[..8].iter().all(u8::is_ascii_digit)
            && b[8] == b'-'
            && b[9].is_ascii_digit()
            && b[10].is_ascii_digit()
            && b[11] == b':'
            && b[12].is_ascii_digit()
            && b[13].is_ascii_digit()
            && b[14] == b':'
            && b[15].is_ascii_digit()
            && b[16].is_ascii_digit()
    }

    /// realizedPNL 哨兵雙判別 → `Option`（移交 blocking #1,fail-closed）:
    ///   ①空欄 → `None`（誠實缺席,不計 audit）;
    ///   ②精確字串 `1.7976931348623157E308`（E 大小寫不敏感）或解析後 |v|≥1.0e308 →
    ///     `None`+audit 計數記原始字串（f64 解析僅作哨兵判別,契約承載仍定點字串）;
    ///   ③其餘 → `Some(原字串)`——`0` 是合法實現損益,恆 `Some("0")`,**禁折 0**。
    fn classify_realized_pnl(&mut self, raw: &str) -> Option<String> {
        if raw.is_empty() {
            return None;
        }
        let exact_hit = raw.eq_ignore_ascii_case(REALIZED_PNL_SENTINEL_EXACT);
        let magnitude_hit = raw
            .parse::<f64>()
            .map(|v| v.abs() >= REALIZED_PNL_SENTINEL_MAGNITUDE)
            .unwrap_or(false);
        if exact_hit || magnitude_hit {
            self.audit.realized_pnl_sentinel_hits += 1;
            self.audit.realized_pnl_sentinel_last_raw = Some(raw.to_string());
            return None;
        }
        Some(raw.to_string())
    }
}

/// 相位 + 最後更新時刻 → typed staleness（同構 W5-S2 `staleness_of`——該 fn 為模塊私有,
/// 此處同義複刻,不越界改動 account_data）。
fn staleness_of(
    phase: SubPhase,
    last_update_ms: u64,
    stale_after: Duration,
    now_ms: u64,
) -> SnapshotStaleness {
    match phase {
        SubPhase::Idle => SnapshotStaleness::NotSubscribed,
        SubPhase::SnapshotIncomplete => SnapshotStaleness::SnapshotIncomplete,
        SubPhase::Invalidated => SnapshotStaleness::Invalidated,
        SubPhase::DisconnectedStale => SnapshotStaleness::DisconnectedStale,
        SubPhase::Live => {
            let age_ms = now_ms.saturating_sub(last_update_ms);
            if age_ms > stale_after.as_millis() as u64 {
                SnapshotStaleness::Stale {
                    as_of_ms: last_update_ms,
                    age_ms,
                }
            } else {
                SnapshotStaleness::Fresh {
                    as_of_ms: last_update_ms,
                }
            }
        }
    }
}

/// 價格欄分類:空欄=unset → `None`;非空必為簽名定點字串,否則 denied（回欄名供 typed 拒）。
fn classify_optional_price(
    raw: &str,
    field: &'static str,
) -> Result<Option<String>, &'static str> {
    if raw.is_empty() {
        return Ok(None);
    }
    if !is_signed_decimal_string(raw) {
        return Err(field);
    }
    Ok(Some(raw.to_string()))
}

/// wire 幣別 → lane 白名單（USD 精確匹配;表外 → `UnknownDenied`,契約/本地紀律拒。
/// 同構 W5-S2 `classify_wire_currency`——該 fn 為模塊私有,此處同義複刻,不越界改動）。
fn classify_wire_currency(raw: &str) -> StockEtfCurrency {
    match raw {
        "USD" => StockEtfCurrency::Usd,
        _ => StockEtfCurrency::UnknownDenied,
    }
}

/// 欄位 0 的 msgId 斷言（非數字/錯 id → `WireMalformed`,不猜、不容錯位;同構 W5-S2）。
fn expect_msg_id(raw: &str, expected: i64) -> Result<(), OrderExecDataReject> {
    let got = parse_i64(raw, "msg_id")?;
    if got != expected {
        return Err(OrderExecDataReject::WireMalformed(
            CodecError::UnexpectedMsgId { got },
        ));
    }
    Ok(())
}

/// 數字欄 parse（非數字 → `WireMalformed(NonNumericField)`,禁 `unwrap_or(0)` 捏造;同構 W5-S2）。
fn parse_i64(raw: &str, field: &'static str) -> Result<i64, OrderExecDataReject> {
    raw.parse::<i64>()
        .map_err(|_| OrderExecDataReject::WireMalformed(CodecError::NonNumericField(field)))
}

#[cfg(test)]
#[path = "ibkr_tws_order_exec_data_tests.rs"]
mod tests;
