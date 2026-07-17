//! MODULE_NOTE
//! 模塊用途：IBKR **W5-S2 account/positions 消化層**（IBKR_TODO §5-W5;騎 W3 session manager
//!   請求路由）。把 `reqAccountSummary`/`reqPositions` 的訂閱生命週期 + 入站行消化收斂為
//!   typed、fail-closed 的快照狀態機:出站 builder（IB pinned 欄位序）→ 入站 decode →
//!   W5-S1 row 契約（`IbkrAccountSummaryRowV1`/`IbkrPositionsRowV1`,「先契約後消化,禁裸
//!   map」）→ typed staleness 標記（非 bool）。
//! 主要區段：
//!   - (a) OUT 常數 + 出站 builder 四個（IB 現勘 2026-07-17 pinned,官方 ibapi 9.81.1.post1:
//!     OUT 空間 reqPositions=61 / reqAccountSummary=62 / cancelAccountSummary=63 /
//!     cancelPositions=64;IN 空間 61-64 撞號居 `ibkr_tws_wire`,命名帶方向防混用）。
//!   - (b) config：`AccountDataConfig`（G1 serverVersion 下界 / summary 3 分鐘節拍 /
//!     positions client 時鐘窗 / G2 哨兵位數守衛;參數禁假功能,每項真讀取生效）。
//!   - (c) typed 裁決：`AccountDataReject`（wire 損壞 / 契約 blocker / G1 / G2 / G3 /
//!     reqId 錯配——全 typed,不 panic、不捏值、不默認）+ `SnapshotStaleness`。
//!   - (d) `AccountDataDigest`：summary/positions 雙訂閱狀態機（G3 單訂閱不變量）+ 行存放
//!     （client 側 `captured_at_ms`/`snapshot_seq` 注入）+ 斷線失效。
//!   - (e) **W6-S0 硬化**：`AccountDataAudit`（typed reject 身分觀測面,沿 OrderExecAudit
//!     慣例）;Invalidated 恢復政策=世代內終態、唯 `on_new_connection_generation` 重評;
//!     快照 map config 化 cap（超界=毒化非驅逐）;行視圖改 staleness 綁定形
//!     `(SnapshotStaleness, rows)`。
//! 依賴：`ibkr_tws_wire`（codec/常數）、`openclaw_types`（W5-S1 row 契約 + tag/secType
//!   白名單）、`std::collections::BTreeMap`。
//! 硬邊界：
//!   - **無 socket / 無 I/O / 無 async**：純同步狀態機,注入時鐘（now_ms）。出站 frame 由
//!     本檔 build,**送出必經 pacing 單一出口**（driver 以 `OutboundClass::AccountData` 取
//!     `OutboundGrant` 後 `send_framed`;無 grant 無法送,編譯期強制）。
//!   - **G1（fail-closed 版本門控）**：position 訊息 version<3 → typed reject（禁 ibapi 式
//!     默認 avgCost=0 捏值）;serverVersion < config 下界（默認 101=
//!     MIN_SERVER_VER_FRACTIONAL_POSITIONS）→ 訂閱前 session 級 blocker,不實作 <101 舊解析
//!     分支。
//!   - **G2（哨兵守衛）**：10.x `UNSET_DECIMAL` 精確哨兵位元組 UNVERIFIABLE → 不寫死哨兵
//!     常數,以 config 化整數位數守衛拒斥（EA 跑道實測校準）。
//!   - **G3（單訂閱不變量）**：官方硬限同時最多 2 份 summary 訂閱 → engine 自限 1 份,
//!     **結構性**強制（digest 只有一個 summary 槽 + 活躍時 begin 即拒）,不依賴 server 報錯。
//!     positions 同為全域單訂閱（cancelPositions 無 reqId=全域取消,IB 現勘）。
//!   - **訂閱語義（IB 現勘 pinned）**：summary=訂閱型,首回全量→End→之後每 3 分鐘僅推變動
//!     tag 直到 cancel;positions=訂閱型,首回全量→positionEnd→之後事件驅動增量（**無節拍
//!     保證**）→ staleness 以 client 時鐘+心跳為準,不可假設週期推送。
//!   - **零 production caller（W3-W7 B′ 姿態）**：本模塊經 driver 測試域消費;default build
//!     隨 TWS 連接器面 DCE,g4 零符號 audit 保綠。Bybit crypto_perp 不變;無 DB migration。

// intentional-DCE 姿態繼承 wire/session/pacing/driver（見各檔 MODULE_NOTE）:本模塊在
// default build 零 production caller（真消費者=driver 測試域;W6+ 接真 IPC 投影面）。
#![allow(dead_code)]

use std::collections::BTreeMap;
use std::time::Duration;

use openclaw_types::{
    IbkrAccountSummaryRowBlocker, IbkrAccountSummaryRowV1, IbkrAccountSummaryTagV1,
    IbkrPositionsRowBlocker, IbkrPositionsRowV1, IbkrSecTypeV1, StockEtfCurrency,
    IBKR_ACCOUNT_SUMMARY_ROW_CONTRACT_ID, IBKR_ACCOUNT_SUMMARY_WIRE_TAG_WHITELIST,
    IBKR_POSITIONS_ROW_CONTRACT_ID,
};

use crate::ibkr_tws_wire::{
    decode_fields, encode_fields, encode_frame, CodecError, IN_ACCOUNT_SUMMARY_END_MSG_ID,
    IN_ACCOUNT_SUMMARY_MSG_ID, IN_POSITION_DATA_MSG_ID, IN_POSITION_END_MSG_ID,
};

// ===========================================================================
// (a) OUT 常數 + 出站 builder（IB 現勘 2026-07-17 pinned;官方 ibapi 9.81.1.post1 sdist）
// 注:OUT 與 IN 是兩個獨立編號空間,61-64 撞號——IN 空間常數居 `ibkr_tws_wire`（`IN_*`）,
// 此處為 OUT 空間（`OUT_*`）,命名顯式帶方向防混用。
// ===========================================================================

/// OUT 61:reqPositions（訂閱;無 reqId,全域）。
pub(crate) const OUT_REQ_POSITIONS_MSG_ID: &str = "61";
/// OUT 62:reqAccountSummary。
pub(crate) const OUT_REQ_ACCOUNT_SUMMARY_MSG_ID: &str = "62";
/// OUT 63:cancelAccountSummary。
pub(crate) const OUT_CANCEL_ACCOUNT_SUMMARY_MSG_ID: &str = "63";
/// OUT 64:cancelPositions（無 reqId,全域取消）。
pub(crate) const OUT_CANCEL_POSITIONS_MSG_ID: &str = "64";

/// 四個出站訊息的 wire VERSION 欄（IB 現勘:皆為 1）。
const ACCOUNT_DATA_OUT_VERSION: &str = "1";

/// reqAccountSummary 的 group 欄:用 `"All"`（IB 現勘:不支援單帳號 ID 作 group）。
const ACCOUNT_SUMMARY_GROUP_ALL: &str = "All";

/// encode reqAccountSummary：framed `[62, VERSION=1, reqId, group="All", tags]`——tags 為
/// **單欄逗號分隔**（IB 現勘欄位序）,取 types 契約 9 值白名單全集（消化端「認得才收」,
/// 表外回報 tag 走 UnknownDenied blocker 路徑）。
pub(crate) fn encode_req_account_summary(req_id: i64) -> Vec<u8> {
    let tags = IBKR_ACCOUNT_SUMMARY_WIRE_TAG_WHITELIST.join(",");
    let rid = req_id.to_string();
    encode_frame(&encode_fields(&[
        OUT_REQ_ACCOUNT_SUMMARY_MSG_ID,
        ACCOUNT_DATA_OUT_VERSION,
        &rid,
        ACCOUNT_SUMMARY_GROUP_ALL,
        &tags,
    ]))
}

/// encode cancelAccountSummary：framed `[63, 1, reqId]`。
pub(crate) fn encode_cancel_account_summary(req_id: i64) -> Vec<u8> {
    let rid = req_id.to_string();
    encode_frame(&encode_fields(&[
        OUT_CANCEL_ACCOUNT_SUMMARY_MSG_ID,
        ACCOUNT_DATA_OUT_VERSION,
        &rid,
    ]))
}

/// encode reqPositions：framed `[61, 1]`（無 reqId;IB 現勘欄位序）。
pub(crate) fn encode_req_positions() -> Vec<u8> {
    encode_frame(&encode_fields(&[
        OUT_REQ_POSITIONS_MSG_ID,
        ACCOUNT_DATA_OUT_VERSION,
    ]))
}

/// encode cancelPositions：framed `[64, 1]`（無 reqId,全域取消;IB 現勘欄位序）。
pub(crate) fn encode_cancel_positions() -> Vec<u8> {
    encode_frame(&encode_fields(&[
        OUT_CANCEL_POSITIONS_MSG_ID,
        ACCOUNT_DATA_OUT_VERSION,
    ]))
}

// ===========================================================================
// (b) config（全 config 化;參數禁假功能——每項必真實被讀取、生效、可觀測）
// ===========================================================================

/// account/positions 消化配置。default = IB 現勘常數（2026-07-17）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct AccountDataConfig {
    /// **G1**:positions 消化的 serverVersion 下界（默認 101 =
    /// MIN_SERVER_VER_FRACTIONAL_POSITIONS,官方 ibapi 常數）。低於此 → 訂閱前 session 級
    /// blocker（不實作 <101 舊解析分支,fail-closed）。config 化下界,非寫死。
    pub min_positions_server_version: i32,
    /// summary End 後的推送節拍（IB 現勘:每 3 分鐘僅推變動 tag）。
    pub summary_push_interval: Duration,
    /// summary 新鮮窗:End 後逾此窗無任何推送 → `Stale` 保守標記（值可能只是未變——IB 無
    /// 變動即無推送——消費端據此降信心,fail-closed 側不升格;默認 2×節拍+30s 容忍）。
    pub summary_stale_after: Duration,
    /// positions 新鮮窗:事件驅動**無節拍保證**（IB 現勘）→ 以 client 時鐘保守標記,逾窗
    /// 無事件 → `Stale`（同上為保守標記非斷言;連線 liveness 由 session 心跳把關）。
    pub positions_stale_after: Duration,
    /// **G2**:哨兵拒斥守衛——decimal 值整數位數 ≥ 此值即判哨兵嫌疑拒（10.x `UNSET_DECIMAL`
    /// 精確哨兵位元組 **UNVERIFIABLE** → 不寫死哨兵常數,EA 跑道實測校準此守衛;默認 21 位
    /// 遠超真實帳戶量級、遠低於 2^127-1≈39 位哨兵量級）。
    pub sentinel_integer_digits_guard: usize,
    /// **快照 map 行數上界（W6-S0,E3 LOW-02 家族）**:summary 快照 map 的 config 化 cap。
    /// 依據:單 entry 由單 frame 產生（1 frame ≤ `MAX_FRAME_LEN`=64KB）,driver 單 serve
    /// 迴圈 frame 預算 `SERVE_BUDGET`=100_000 → 無 cap 的理論注入面 ≈ 6.4GB/serve（無界);
    /// cap=4096 → 面駐留最壞 ≈ 256MB、實際 row 遠小,且真實 lane 量級（9-tag 白名單×帳戶
    /// 數）在數十內,4096 為 100×+ 裕度。**超界=該面 `Invalidated` 毒化+audit 計數**
    /// （fail-closed;禁靜默驅逐——驅逐=對消費端的記帳謊言）。
    pub max_summary_rows: usize,
    /// positions 快照 map 的 config 化 cap（同上依據;真實倉位量級=數百,4096 為 10×+ 裕度）。
    pub max_positions_rows: usize,
}

impl Default for AccountDataConfig {
    fn default() -> Self {
        Self {
            min_positions_server_version: 101,
            summary_push_interval: Duration::from_secs(180),
            summary_stale_after: Duration::from_secs(390),
            positions_stale_after: Duration::from_secs(390),
            sentinel_integer_digits_guard: 21,
            max_summary_rows: 4096,
            max_positions_rows: 4096,
        }
    }
}

// ===========================================================================
// (c) typed 裁決:reject + staleness（全 typed;禁 panic / 捏值 / 默認值 / silent drop）
// ===========================================================================

/// 消化層 typed 拒絕。呼叫端（driver）分流:`WireMalformed` = wire 損壞 → fail-closed
/// 斷線;其餘 = 資料層 fail-closed（快照標 `Invalidated`,session 續 serve,不 panic）。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub(crate) enum AccountDataReject {
    /// **G3**:summary 已有活躍訂閱（官方硬限同時 2 份 → engine 結構性自限 1 份,不依賴
    /// server 報錯）。
    #[error("account summary subscription already active (engine self-limit = 1)")]
    SummaryAlreadyActive,
    /// **G3**:positions 已有活躍訂閱（全域單訂閱;cancelPositions 為全域取消）。
    #[error("positions subscription already active (global single subscription)")]
    PositionsAlreadyActive,
    /// **G1**:serverVersion 低於 config 下界（默認 101=MIN_SERVER_VER_FRACTIONAL_POSITIONS）
    /// → session 級 blocker,不發 reqPositions、不實作舊解析分支。
    #[error("server version {server_version} below positions floor {floor}")]
    ServerVersionBelowPositionsFloor { server_version: i32, floor: i32 },
    /// **G1**:position 訊息 version<3 → 拒（禁 ibapi 式默認 avgCost=0 捏值）。
    #[error("position message version {version} < 3 (avgCost absent; refuse to fabricate)")]
    PositionVersionTooOld { version: i64 },
    /// **G2**:decimal 值整數位數超 config 守衛 → 哨兵嫌疑拒（UNSET_DECIMAL 不可證,守衛
    /// config 化,EA 校準）。
    #[error("decimal value flagged as sentinel-suspect (integer digits over guard)")]
    SentinelSuspectValue,
    /// 入站 reqId 與活躍 summary 訂閱不符（串流錯配,fail-closed 不併入快照）。
    #[error("unexpected req id {got} for active account summary subscription")]
    UnexpectedReqId { got: i64 },
    /// 無活躍訂閱卻收到資料/End（未訂而收=協議意外,fail-closed 拒併入）。
    #[error("account data frame without active subscription")]
    NoActiveSubscription,
    /// 訂閱槽內部不變量破裂（活躍卻無 reqId 等）——typed 拒,**不得**以默認值（reqId=0）
    /// 上 wire 掩蓋（F7,E2）。
    #[error("subscription slot invariant broken (state corrupted)")]
    SubscriptionStateCorrupted,
    /// **恢復政策（W6-S0,E2-R11-F3/E3 MED-01 家族）**:毒化=同一 connect 世代內終態——
    /// 世代內 re-begin 一律拒（毒化事實不得被同世代重訂沖淡）;唯 driver 世代推進
    /// （新 handshake 成功,`on_new_connection_generation`）重評後可 re-begin。
    #[error("snapshot invalidated; re-begin requires a new connection generation")]
    InvalidatedUntilNewGeneration,
    /// **cap 超界（W6-S0,E3 LOW-02 家族）**:快照 map 行數超 config 上界 → 該面毒化+audit
    /// 計數（fail-closed;禁靜默驅逐=不做記帳謊言）。
    #[error("snapshot row cap exceeded (face poisoned, no silent eviction)")]
    SnapshotRowCapExceeded,
    /// wire 形狀損壞（欄位缺/非數字/非 ASCII）——呼叫端按既有紀律 fail-closed 斷線。
    #[error("wire malformed: {0}")]
    WireMalformed(CodecError),
    /// summary row 契約 blocker（表外 tag `UnknownDenied`/幣別/符號紀律…）——資料層
    /// fail-closed:快照標 `Invalidated`,不 panic、不斷線、不默默跳行。
    #[error("account summary row blocked by contract")]
    SummaryRowBlocked(Vec<IbkrAccountSummaryRowBlocker>),
    /// positions row 契約 blocker（表外 secType/負倉 short/幣別…）——同上資料層 fail-closed。
    #[error("positions row blocked by contract")]
    PositionsRowBlocked(Vec<IbkrPositionsRowBlocker>),
}

/// typed staleness 標記（**非 bool**;快照消費端據此分級,fail-closed 側永不把弱態升格）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SnapshotStaleness {
    /// 未訂閱（或已 cancel）:無可信快照。
    NotSubscribed,
    /// 訂閱中、End 前:快照未完整（禁把部分快照當全量消費）。
    SnapshotIncomplete,
    /// End 後、新鮮窗內。
    Fresh { as_of_ms: u64 },
    /// 逾新鮮窗無推送的**保守標記**（summary:IB 無變動即無推送;positions:事件驅動無節拍
    /// 保證——值可能只是未變,消費端降信心）。
    Stale { as_of_ms: u64, age_ms: u64 },
    /// 契約 blocker 毒化:快照不可信（fail-closed;同 connect 世代內終態,唯新世代重評後
    /// 重訂閱可恢復——W6-S0 恢復政策）。
    Invalidated,
    /// 斷線失效:快照標 stale、**重連需重訂閱**（訂閱不跨連線存活,IB 現勘語義）。
    DisconnectedStale,
}

/// 單一訂閱槽的生命週期相位（G3:每資料面唯一一槽=結構性單訂閱）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SubPhase {
    /// 未訂閱 / 已 cancel。
    Idle,
    /// 已發訂閱,End 前（首回全量進行中）。
    SnapshotIncomplete,
    /// End 已到:summary=節拍推變動;positions=事件驅動增量。
    Live,
    /// 契約 blocker 毒化（fail-closed;同 connect 世代內終態,唯世代推進
    /// `on_new_connection_generation` 重評後離開——W6-S0 恢復政策）。
    Invalidated,
    /// 斷線失效（唯重訂閱離開）。
    DisconnectedStale,
}

impl SubPhase {
    /// 是否佔用訂閱槽（G3 begin 前置檢查:活躍中不得再訂）。
    fn is_active(self) -> bool {
        matches!(self, SubPhase::SnapshotIncomplete | SubPhase::Live)
    }
}

/// audit 計數器（W6-S0,對齊 W5-S3 `OrderExecAudit` 慣例:全部單調遞增+`*_last_*` 樣本欄;
/// driver/W6 IPC 投影唯讀消費）。為什麼需要:driver 對資料層 typed reject 走 `Err(_)=>{}`
/// 分流續 serve——無 audit 則 blocker 身分零觀測(CC lineage 斷點 1/E3 MED-01-S3 (a))。
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub(crate) struct AccountDataAudit {
    /// G2 哨兵嫌疑拒數。
    pub sentinel_suspect_rejects: u64,
    /// 最後一次哨兵嫌疑拒的原始值字串（EA 校準/重放用,沿 `*_last_raw` 慣例）。
    pub sentinel_last_raw: Option<String>,
    /// 未訂而收承接拒數（未訂/毒化/斷線失效窗口的入站丟棄可觀測）。
    pub no_active_subscription_rejects: u64,
    /// wire 損壞拒數（呼叫端 fail-closed 斷線;此處留身分供斷線前因對賬）。
    pub wire_malformed_rejects: u64,
    /// 最後一次 wire 損壞的 typed 描述（CodecError 顯示串,不含 payload 原文）。
    pub wire_malformed_last_note: Option<String>,
    /// 入站 reqId 錯配拒數。
    pub unexpected_req_id_rejects: u64,
    /// summary row 契約 blocker 拒數。
    pub summary_row_blocked_rejects: u64,
    /// 最後一筆 summary row blocker 列表（per-face 樣本欄）。
    pub summary_row_last_blockers: Vec<IbkrAccountSummaryRowBlocker>,
    /// positions row 契約 blocker 拒數。
    pub positions_row_blocked_rejects: u64,
    /// 最後一筆 positions row blocker 列表（per-face 樣本欄）。
    pub positions_row_last_blockers: Vec<IbkrPositionsRowBlocker>,
    /// G1 position version<3 拒數。
    pub position_version_too_old_rejects: u64,
    /// 訂閱槽不變量破裂（F7）拒數。
    pub subscription_state_corrupted_rejects: u64,
    /// 快照 map cap 超界毒化數（W6-S0 cap;禁靜默驅逐）。
    pub row_cap_exceeded_rejects: u64,
}

// ===========================================================================
// (d) AccountDataDigest — 訂閱生命週期狀態機 + 行消化
// ===========================================================================

/// account/positions 消化器。純同步、注入時鐘;快照行以 W5-S1 契約承載（`validate()` 過
/// 才併入）。出站 frame 由 `begin_*`/`cancel_*` 產出,**送出必經 pacing 單一出口**（呼叫端
/// 持 `OutboundGrant` 才可 `send_framed`）。
pub(crate) struct AccountDataDigest {
    config: AccountDataConfig,
    /// 快照單調序列（每次 begin_* 遞增;同快照世代的行共享 seq;契約要求非零）。
    snapshot_seq: u64,
    // ---- summary 訂閱槽（G3:唯一一槽）----
    summary_phase: SubPhase,
    summary_req_id: Option<i64>,
    /// 最新 summary 行,鍵=(account_id, wire tag)——同 tag 後到覆蓋（IB 節拍推變動 tag）。
    summary_rows: BTreeMap<(String, String), IbkrAccountSummaryRowV1>,
    /// 最後一次 summary 行/End 到達的注入 ms（staleness 基準）。
    summary_last_update_ms: u64,
    // ---- positions 訂閱槽（G3:唯一一槽）----
    positions_phase: SubPhase,
    /// 最新 position 行,鍵=(account_id, con_id)——同倉後到覆蓋（事件驅動增量）。
    positions_rows: BTreeMap<(String, i64), IbkrPositionsRowV1>,
    positions_last_update_ms: u64,
    /// W6-S0 audit 計數器（typed reject 身分觀測面;見 `AccountDataAudit`）。
    audit: AccountDataAudit,
}

impl AccountDataDigest {
    pub(crate) fn new(config: AccountDataConfig) -> Self {
        Self {
            config,
            snapshot_seq: 0,
            summary_phase: SubPhase::Idle,
            summary_req_id: None,
            summary_rows: BTreeMap::new(),
            summary_last_update_ms: 0,
            positions_phase: SubPhase::Idle,
            positions_rows: BTreeMap::new(),
            positions_last_update_ms: 0,
            audit: AccountDataAudit::default(),
        }
    }

    // ---- 出站意圖（訂閱生命週期;送出經 pacing 單一出口,見模塊硬邊界）----

    /// 開始 summary 訂閱:回待送 frame。**G3**:活躍中再訂 → typed 拒（結構性單訂閱,不依賴
    /// server 報錯）。Idle/DisconnectedStale 可（重）訂:清舊快照、遞增 seq。
    /// **Invalidated=世代內終態**（W6-S0 恢復政策）:唯 `on_new_connection_generation` 重評
    /// 後可 re-begin——毒化事實不得被同世代重訂沖淡。
    pub(crate) fn begin_account_summary(
        &mut self,
        req_id: i64,
    ) -> Result<Vec<u8>, AccountDataReject> {
        if self.summary_phase == SubPhase::Invalidated {
            return Err(AccountDataReject::InvalidatedUntilNewGeneration);
        }
        if self.summary_phase.is_active() {
            return Err(AccountDataReject::SummaryAlreadyActive);
        }
        self.snapshot_seq += 1;
        self.summary_rows.clear();
        self.summary_phase = SubPhase::SnapshotIncomplete;
        self.summary_req_id = Some(req_id);
        Ok(encode_req_account_summary(req_id))
    }

    /// 取消 summary 訂閱:回待送 frame。非活躍 → typed 拒（無可取消之訂閱,不空發 cancel）。
    /// 取消後快照棄置（`NotSubscribed`——cancel 即宣告不再維護,不留半新鮮殘影）。
    pub(crate) fn cancel_account_summary(&mut self) -> Result<Vec<u8>, AccountDataReject> {
        if !self.summary_phase.is_active() {
            return Err(AccountDataReject::NoActiveSubscription);
        }
        // F7（E2）:活躍卻無 reqId = 不變量破裂——typed 拒 + 毒化,**不得**默認 reqId=0 上
        // wire（cancel 錯 id 是對 server 的語義謊言;新世代重評=唯一恢復）。
        let req_id = match self.summary_req_id.take() {
            Some(rid) => rid,
            None => {
                self.summary_phase = SubPhase::Invalidated;
                let e = AccountDataReject::SubscriptionStateCorrupted;
                self.audit_reject(&e);
                return Err(e);
            }
        };
        self.summary_phase = SubPhase::Idle;
        self.summary_rows.clear();
        Ok(encode_cancel_account_summary(req_id))
    }

    /// 開始 positions 訂閱:回待送 frame。**G1**:serverVersion < config 下界 → session 級
    /// blocker（不發、不實作舊解析分支）。**G3**:活躍中再訂 → typed 拒。
    /// **Invalidated=世代內終態**（W6-S0;同 `begin_account_summary`）。
    pub(crate) fn begin_positions(
        &mut self,
        server_version: i32,
    ) -> Result<Vec<u8>, AccountDataReject> {
        if server_version < self.config.min_positions_server_version {
            return Err(AccountDataReject::ServerVersionBelowPositionsFloor {
                server_version,
                floor: self.config.min_positions_server_version,
            });
        }
        if self.positions_phase == SubPhase::Invalidated {
            return Err(AccountDataReject::InvalidatedUntilNewGeneration);
        }
        if self.positions_phase.is_active() {
            return Err(AccountDataReject::PositionsAlreadyActive);
        }
        self.snapshot_seq += 1;
        self.positions_rows.clear();
        self.positions_phase = SubPhase::SnapshotIncomplete;
        Ok(encode_req_positions())
    }

    /// 取消 positions 訂閱（全域;無 reqId）。非活躍 → typed 拒。
    pub(crate) fn cancel_positions(&mut self) -> Result<Vec<u8>, AccountDataReject> {
        if !self.positions_phase.is_active() {
            return Err(AccountDataReject::NoActiveSubscription);
        }
        self.positions_phase = SubPhase::Idle;
        self.positions_rows.clear();
        Ok(encode_cancel_positions())
    }

    // ---- 入站消化（payload = 已 unframe 的欄位序,含 msgId 欄）----

    /// IN 63 accountSummary 行:decode（IB pinned 欄序 `[63, version, reqId, account, tag,
    /// value, currency]`）→ G2 哨兵守衛 → W5-S1 row 契約 `validate()` → 併入快照。
    /// 表外 tag → 契約 `UnknownDenied` blocker 路徑（快照標 `Invalidated`,不 panic）。
    /// W6-S0:任何 typed reject 過 `audit_reject` 落帳身分（driver `Err(_)=>{}` 分流不再
    /// 零觀測）。
    pub(crate) fn on_account_summary_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), AccountDataReject> {
        let r = self.account_summary_frame_inner(payload, now_ms);
        if let Err(e) = &r {
            self.audit_reject(e);
        }
        r
    }

    fn account_summary_frame_inner(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), AccountDataReject> {
        let fields = decode_fields(payload).map_err(AccountDataReject::WireMalformed)?;
        // F2（E2）:精確 7 欄——按位消費不容錯位,多餘欄=wire 意外（與 position !=16 同紀律）。
        if fields.len() != 7 {
            return Err(AccountDataReject::WireMalformed(CodecError::Malformed(
                "account summary needs exactly 7 fields",
            )));
        }
        expect_msg_id(&fields[0], IN_ACCOUNT_SUMMARY_MSG_ID)?;
        let req_id = parse_i64(&fields[2], "req_id")?;
        if !self.summary_phase.is_active() {
            return Err(AccountDataReject::NoActiveSubscription);
        }
        if self.summary_req_id != Some(req_id) {
            return Err(AccountDataReject::UnexpectedReqId { got: req_id });
        }
        // G2:哨兵守衛先於契約校驗（哨兵是「值不可信」而非「格式非法」,獨立 typed 拒）。
        // 原始值就地記 audit（沿 `*_last_raw` 慣例;count 亦就地——audit_reject 不重複計）。
        if self.sentinel_suspect(&fields[5]) {
            self.audit.sentinel_suspect_rejects += 1;
            self.audit.sentinel_last_raw = Some(fields[5].clone());
            self.summary_phase = SubPhase::Invalidated;
            return Err(AccountDataReject::SentinelSuspectValue);
        }
        let row = IbkrAccountSummaryRowV1 {
            contract_id: IBKR_ACCOUNT_SUMMARY_ROW_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: openclaw_types::AssetLane::StockEtfCash,
            broker: openclaw_types::Broker::Ibkr,
            account_id: fields[3].clone(),
            tag: IbkrAccountSummaryTagV1::classify_wire_tag(&fields[4]),
            value_decimal: fields[5].clone(),
            currency: classify_wire_currency(&fields[6]),
            captured_at_ms: now_ms,
            snapshot_seq: self.snapshot_seq,
            order_routed: false,
            secret_content_serialized: false,
        };
        let verdict = row.validate();
        if !verdict.accepted {
            // 契約 blocker（含表外 tag UnknownDenied）→ 快照毒化,fail-closed 不併入。
            self.summary_phase = SubPhase::Invalidated;
            return Err(AccountDataReject::SummaryRowBlocked(verdict.blockers));
        }
        // W6-S0 cap:新鍵且已達上界 → 毒化+audit（fail-closed;禁靜默驅逐——驅逐哪一行都是
        // 對消費端的記帳謊言）。既有鍵覆蓋不受 cap 限（不增長）。
        let key = (row.account_id.clone(), fields[4].clone());
        if !self.summary_rows.contains_key(&key)
            && self.summary_rows.len() >= self.config.max_summary_rows
        {
            self.summary_phase = SubPhase::Invalidated;
            return Err(AccountDataReject::SnapshotRowCapExceeded);
        }
        self.summary_last_update_ms = now_ms;
        self.summary_rows.insert(key, row);
        Ok(())
    }

    /// IN 64 accountSummaryEnd（`[64, version, reqId]`）:首回全量完成 → `Live`（其後每 3
    /// 分鐘僅推變動 tag,staleness 轉節拍窗語義）。
    pub(crate) fn on_account_summary_end_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), AccountDataReject> {
        let r = self.account_summary_end_frame_inner(payload, now_ms);
        if let Err(e) = &r {
            self.audit_reject(e);
        }
        r
    }

    fn account_summary_end_frame_inner(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), AccountDataReject> {
        let fields = decode_fields(payload).map_err(AccountDataReject::WireMalformed)?;
        // F2（E2）:精確 3 欄（按位消費不容錯位,同 position !=16 紀律）。
        if fields.len() != 3 {
            return Err(AccountDataReject::WireMalformed(CodecError::Malformed(
                "account summary end needs exactly 3 fields",
            )));
        }
        expect_msg_id(&fields[0], IN_ACCOUNT_SUMMARY_END_MSG_ID)?;
        let req_id = parse_i64(&fields[2], "req_id")?;
        if !self.summary_phase.is_active() {
            return Err(AccountDataReject::NoActiveSubscription);
        }
        if self.summary_req_id != Some(req_id) {
            return Err(AccountDataReject::UnexpectedReqId { got: req_id });
        }
        self.summary_phase = SubPhase::Live;
        self.summary_last_update_ms = now_ms;
        Ok(())
    }

    /// IN 61 position 行:**G1 version 門控**（<3 → typed 拒,禁默認 avgCost=0 捏值）→
    /// 按位消費 IB pinned 16 欄（STK 行的 expiry/strike/right/multiplier/localSymbol/
    /// tradingClass 佔位欄仍在 wire,按位讀後棄——無 primaryExchange 欄）→ G2 哨兵守衛 →
    /// W5-S1 row 契約 → 併入快照。
    pub(crate) fn on_position_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), AccountDataReject> {
        let r = self.position_frame_inner(payload, now_ms);
        if let Err(e) = &r {
            self.audit_reject(e);
        }
        r
    }

    fn position_frame_inner(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), AccountDataReject> {
        let fields = decode_fields(payload).map_err(AccountDataReject::WireMalformed)?;
        if fields.len() < 2 {
            return Err(AccountDataReject::WireMalformed(CodecError::Malformed(
                "position needs >=2 fields",
            )));
        }
        expect_msg_id(&fields[0], IN_POSITION_DATA_MSG_ID)?;
        let version = parse_i64(&fields[1], "position_version")?;
        // **N1（W5-S3 E2 對齊）**:wire 形狀裁決先於訂閱狀態——v≥3 欄序固定 16 欄,多/少皆
        // wire 意外 → `WireMalformed`（按位消費不容錯位）。此裁決**不得**被未訂閱窗口的
        // `NoActiveSubscription` 遮蔽:version 欄非數字在未訂閱窗口已走 WireMalformed 斷線,
        // 欄數錯同屬 wire 損壞,靜默吞掉=同一損壞兩種裁決的不一致。v<3 的欄數形狀不 pin
        //（G1 於訂閱狀態裁決後拒收,見下）。
        if version >= 3 && fields.len() != 16 {
            return Err(AccountDataReject::WireMalformed(CodecError::Malformed(
                "position v3 needs exactly 16 fields",
            )));
        }
        // 未訂而收先裁（置於 version 門控前:不得對未訂閱的槽做毒化副作用）。
        if !self.positions_phase.is_active() {
            return Err(AccountDataReject::NoActiveSubscription);
        }
        // G1:version<3 無 avgCost 欄——拒收,不學 ibapi 默認 0 捏值（fail-closed）。
        // **F1（E2）**:G1 floor=101 下 server 聲明 v<3 = 協議異常——若僅拒行不毒化,
        // 其後 positionEnd 會把「缺行的不完整快照」推到 Live/Fresh,W5-S4 attestation/
        // 對賬將把它當真值。取「毒化 `Invalidated`」而非斷線:與契約 blocker 同為
        // **資料層** fail-closed（session 存活、快照不可用、重訂閱=唯一恢復）,不把
        // 資料層異常升格為 transport 事件,與 driver「WireMalformed 才斷線」分流一致。
        if version < 3 {
            self.positions_phase = SubPhase::Invalidated;
            return Err(AccountDataReject::PositionVersionTooOld { version });
        }
        // 佔位欄按位消費（idx 6=lastTradeDateOrContractMonth / 7=strike / 8=right /
        // 9=multiplier / 12=localSymbol / 13=tradingClass）:讀位即棄,不 bind 語義。
        let con_id = parse_i64(&fields[3], "con_id")?;
        // G2:position/avgCost 皆過哨兵守衛（10.x UNSET_DECIMAL 不可證 → config 守衛）。
        // 原始值就地記 audit（記命中側;兩側皆中取 position 側樣本即可）。
        if self.sentinel_suspect(&fields[14]) || self.sentinel_suspect(&fields[15]) {
            let raw = if self.sentinel_suspect(&fields[14]) {
                &fields[14]
            } else {
                &fields[15]
            };
            self.audit.sentinel_suspect_rejects += 1;
            self.audit.sentinel_last_raw = Some(raw.clone());
            self.positions_phase = SubPhase::Invalidated;
            return Err(AccountDataReject::SentinelSuspectValue);
        }
        let row = IbkrPositionsRowV1 {
            contract_id: IBKR_POSITIONS_ROW_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: openclaw_types::AssetLane::StockEtfCash,
            broker: openclaw_types::Broker::Ibkr,
            account_id: fields[2].clone(),
            con_id,
            symbol: fields[4].clone(),
            sec_type: IbkrSecTypeV1::classify_wire_sec_type(&fields[5]),
            currency: classify_wire_currency(&fields[11]),
            exchange: fields[10].clone(),
            position_decimal: fields[14].clone(),
            avg_cost_decimal: fields[15].clone(),
            order_routed: false,
            secret_content_serialized: false,
        };
        let verdict = row.validate();
        if !verdict.accepted {
            // 契約 blocker（表外 secType/short 負倉/幣別…）→ 快照毒化,fail-closed 不併入。
            self.positions_phase = SubPhase::Invalidated;
            return Err(AccountDataReject::PositionsRowBlocked(verdict.blockers));
        }
        // W6-S0 cap:同 summary 紀律（新鍵且達上界 → 毒化+audit,禁靜默驅逐）。
        let key = (row.account_id.clone(), con_id);
        if !self.positions_rows.contains_key(&key)
            && self.positions_rows.len() >= self.config.max_positions_rows
        {
            self.positions_phase = SubPhase::Invalidated;
            return Err(AccountDataReject::SnapshotRowCapExceeded);
        }
        self.positions_last_update_ms = now_ms;
        self.positions_rows.insert(key, row);
        Ok(())
    }

    /// IN 62 positionEnd（`[62, version]`）:首回全量完成 → `Live`（其後事件驅動增量,無節拍
    /// 保證——staleness 以 client 時鐘窗保守標記）。
    pub(crate) fn on_position_end_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), AccountDataReject> {
        let r = self.position_end_frame_inner(payload, now_ms);
        if let Err(e) = &r {
            self.audit_reject(e);
        }
        r
    }

    fn position_end_frame_inner(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), AccountDataReject> {
        let fields = decode_fields(payload).map_err(AccountDataReject::WireMalformed)?;
        // F2（E2）:精確 2 欄（按位消費不容錯位,同 position !=16 紀律）。
        if fields.len() != 2 {
            return Err(AccountDataReject::WireMalformed(CodecError::Malformed(
                "position end needs exactly 2 fields",
            )));
        }
        expect_msg_id(&fields[0], IN_POSITION_END_MSG_ID)?;
        if !self.positions_phase.is_active() {
            return Err(AccountDataReject::NoActiveSubscription);
        }
        self.positions_phase = SubPhase::Live;
        self.positions_last_update_ms = now_ms;
        Ok(())
    }

    // ---- 生命週期:斷線 / 世代推進 ----

    /// 斷線:活躍/已完成快照一律標 `DisconnectedStale`（訂閱不跨連線存活——**重連需重訂閱**,
    /// IB 現勘語義;行保留供唯讀檢視,staleness 已明示不可信）。Idle/Invalidated 維持原相位
    /// （毒化事實不被斷線沖淡;毒化面的重評歸 `on_new_connection_generation`）。
    pub(crate) fn on_disconnect(&mut self) {
        if self.summary_phase.is_active() {
            self.summary_phase = SubPhase::DisconnectedStale;
            self.summary_req_id = None;
        }
        if self.positions_phase.is_active() {
            self.positions_phase = SubPhase::DisconnectedStale;
        }
    }

    /// **W6-S0 恢復政策**（E2-R11-F3/E3 MED-01 家族）:driver 世代推進（新 handshake 成功）
    /// 時重評毒化面——`Invalidated` → `DisconnectedStale`,與既有「斷線→DisconnectedStale→
    /// 重訂閱」語義合流（pump 的 staleness 閘據此 re-begin）。為什麼不直接轉 `Idle`:毒化
    /// 世代的行保留供唯讀對賬（staleness 已明示不可信）,re-begin 時 `begin_*` 統一清行+
    /// 遞增快照世代。其餘相位不動（活躍面由 `on_disconnect` 收口;audit 計數跨世代累積=
    /// telemetry 語義,不清零）。
    pub(crate) fn on_new_connection_generation(&mut self) {
        if self.summary_phase == SubPhase::Invalidated {
            self.summary_phase = SubPhase::DisconnectedStale;
            self.summary_req_id = None;
        }
        if self.positions_phase == SubPhase::Invalidated {
            self.positions_phase = SubPhase::DisconnectedStale;
        }
    }

    // ---- 觀測（typed staleness + 唯讀行檢視）----

    /// summary 快照 staleness（typed;End 後按 3 分鐘節拍窗+client 時鐘保守標記）。
    pub(crate) fn summary_staleness(&self, now_ms: u64) -> SnapshotStaleness {
        staleness_of(
            self.summary_phase,
            self.summary_last_update_ms,
            self.config.summary_stale_after,
            now_ms,
        )
    }

    /// positions 快照 staleness（typed;事件驅動無節拍保證 → client 時鐘窗保守標記）。
    pub(crate) fn positions_staleness(&self, now_ms: u64) -> SnapshotStaleness {
        staleness_of(
            self.positions_phase,
            self.positions_last_update_ms,
            self.config.positions_stale_after,
            now_ms,
        )
    }

    /// 唯讀檢視:summary 面 **staleness 綁定視圖**（W6-S0,E2-R11-F4）——rows 只能與其
    /// staleness 一同取得,使「部分/毒化/斷線快照被當全量消費」**結構性不可能**（消費端
    /// 必先過 staleness 才拿得到行;BTreeMap=確定序）。
    pub(crate) fn summary_rows(
        &self,
        now_ms: u64,
    ) -> (
        SnapshotStaleness,
        impl Iterator<Item = &IbkrAccountSummaryRowV1>,
    ) {
        (self.summary_staleness(now_ms), self.summary_rows.values())
    }

    /// 唯讀檢視:positions 面 staleness 綁定視圖（同 `summary_rows` 紀律）。
    pub(crate) fn positions_rows(
        &self,
        now_ms: u64,
    ) -> (
        SnapshotStaleness,
        impl Iterator<Item = &IbkrPositionsRowV1>,
    ) {
        (self.positions_staleness(now_ms), self.positions_rows.values())
    }

    /// audit 計數器唯讀檢視（W6-S0;typed reject 身分觀測面）。
    pub(crate) fn audit(&self) -> &AccountDataAudit {
        &self.audit
    }

    /// 當前快照世代序（telemetry;契約 snapshot_seq 注入源）。
    pub(crate) fn snapshot_seq(&self) -> u64 {
        self.snapshot_seq
    }

    // ---- 內部 ----

    /// W6-S0:入站 typed reject → audit 身分落帳（單調計數+最後樣本;CC lineage 斷點 1 收口
    /// ——driver 對資料層 reject 走 `Err(_)=>{}` 續 serve,身分由此觀測面承載）。
    /// 哨兵拒的 count+raw 於拒點就地記錄（raw 不在 reject 變體內）,此處跳過防重複計數;
    /// begin 域拒（G1/G3/世代政策)由 pump 的 staleness/floor 閘先擋,不屬入站觀測面。
    fn audit_reject(&mut self, e: &AccountDataReject) {
        match e {
            AccountDataReject::SentinelSuspectValue => {}
            AccountDataReject::NoActiveSubscription => {
                self.audit.no_active_subscription_rejects += 1;
            }
            AccountDataReject::WireMalformed(c) => {
                self.audit.wire_malformed_rejects += 1;
                self.audit.wire_malformed_last_note = Some(c.to_string());
            }
            AccountDataReject::UnexpectedReqId { .. } => {
                self.audit.unexpected_req_id_rejects += 1;
            }
            AccountDataReject::SummaryRowBlocked(blockers) => {
                self.audit.summary_row_blocked_rejects += 1;
                self.audit.summary_row_last_blockers = blockers.clone();
            }
            AccountDataReject::PositionsRowBlocked(blockers) => {
                self.audit.positions_row_blocked_rejects += 1;
                self.audit.positions_row_last_blockers = blockers.clone();
            }
            AccountDataReject::PositionVersionTooOld { .. } => {
                self.audit.position_version_too_old_rejects += 1;
            }
            AccountDataReject::SubscriptionStateCorrupted => {
                self.audit.subscription_state_corrupted_rejects += 1;
            }
            AccountDataReject::SnapshotRowCapExceeded => {
                self.audit.row_cap_exceeded_rejects += 1;
            }
            AccountDataReject::SummaryAlreadyActive
            | AccountDataReject::PositionsAlreadyActive
            | AccountDataReject::ServerVersionBelowPositionsFloor { .. }
            | AccountDataReject::InvalidatedUntilNewGeneration => {}
        }
    }

    /// **G2** 哨兵守衛:整數位數（小數點前、忽略前導 `-`）≥ config 守衛值 → 哨兵嫌疑。
    /// 只判位數不判格式（格式非法交契約 `validate()` 專責,職責不重疊）。
    fn sentinel_suspect(&self, value: &str) -> bool {
        let digits = value.strip_prefix('-').unwrap_or(value);
        let int_part = digits.split('.').next().unwrap_or("");
        int_part.len() >= self.config.sentinel_integer_digits_guard
    }
}

/// 相位 + 最後更新時刻 → typed staleness（summary/positions 共用投影）。
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

/// wire 幣別 → lane 白名單（USD 精確匹配;表外 → `UnknownDenied`,契約 `validate()` 拒）。
fn classify_wire_currency(raw: &str) -> StockEtfCurrency {
    match raw {
        "USD" => StockEtfCurrency::Usd,
        _ => StockEtfCurrency::UnknownDenied,
    }
}

/// 欄位 0 的 msgId 斷言（非數字/錯 id → `WireMalformed`,不猜、不容錯位）。
fn expect_msg_id(raw: &str, expected: i64) -> Result<(), AccountDataReject> {
    let got = parse_i64(raw, "msg_id")?;
    if got != expected {
        return Err(AccountDataReject::WireMalformed(
            CodecError::UnexpectedMsgId { got },
        ));
    }
    Ok(())
}

/// 數字欄 parse（非數字 → `WireMalformed(NonNumericField)`,禁 `unwrap_or(0)` 捏造）。
fn parse_i64(raw: &str, field: &'static str) -> Result<i64, AccountDataReject> {
    raw.parse::<i64>()
        .map_err(|_| AccountDataReject::WireMalformed(CodecError::NonNumericField(field)))
}

#[cfg(test)]
#[path = "ibkr_tws_account_data_tests.rs"]
mod tests;
