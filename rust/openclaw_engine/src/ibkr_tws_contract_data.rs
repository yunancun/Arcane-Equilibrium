//! MODULE_NOTE
//! 模塊用途：IBKR **W6-S1 contract details 消化層**（IBKR_TODO §5-W6 範圍 in 1;沿 W5-S2
//!   `ibkr_tws_account_data` / W5-S3 `ibkr_tws_order_exec_data` 全部慣例）。把
//!   `reqContractDetails` 的單次快照生命週期收斂為 typed、fail-closed 的消化狀態機:
//!   出站 v8 builder（全限定 STK 查詢）→ IN 10 decode（message-version 硬 pin ==8 +
//!   per-field sv 門控表 + secIdList bounded skip + longName unicode-escape）→ W6-S1
//!   instrument identity row 契約（`IbkrInstrumentIdentityRowV1`,「先契約後消化,禁裸
//!   map」;identity_hash 於此鑄造）→ IN 52 End 界定快照 → typed staleness（沿
//!   `SnapshotStaleness` 六態）。
//! 主要區段：
//!   - (a) OUT 常數 + `ContractDetailsQuery` + v8 builder（IB 現勘 2026-07-17 pinned,官方
//!     ibapi 9.81.1.post1 sdist:OUT REQ_CONTRACT_DATA=9 與 IN NEXT_VALID_ID=9 撞值——IN
//!     常數居 `ibkr_tws_wire`,`IN_`/`OUT_` 方向命名防混用,沿 W5-S2/S3 慣例）。
//!   - (b) config：`ContractDataConfig`（floor/ceiling serverVersion 兩界 / 請求 timeout /
//!     staleness 窗 / 快照 cap / secIdList count cap;參數禁假功能,每項真生效）。
//!   - (c) typed 裁決：`ContractDataReject`（wire 損壞 / message-version 撕 pin / 契約
//!     blocker / secIdList 荒謬 count / 佈局窗——全 typed,不 panic、不捏值、不默認）+
//!     `ContractDataAudit`（沿 `*_last_*` 樣本欄慣例）。
//!   - (d) `ContractDataDigest`：單槽快照狀態機（begin → IN 10 行 → IN 52 End → Live;
//!     **請求 timeout typed 化**=`expire_overdue` 注入時鐘裁決,非懸掛）+ IN 18
//!     bondContractData **typed-ignore**（記帳丟棄,不消化不 unknown-fail）+ Invalidated
//!     世代內終態、唯 `on_new_connection_generation` 重評 + `(staleness, rows)` 綁定視圖
//!     + cap 超界毒化非驅逐（全部沿 R17 W6-S0 新慣例）。
//! 依賴：`ibkr_tws_wire`（codec/IN 常數）、`ibkr_tws_account_data`（`SnapshotStaleness`
//!   六態共用）、`openclaw_types`（W6-S1 identity row 契約 + secType/symbol 紀律）、
//!   support 子模塊 `ibkr_tws_contract_data_support.rs`（800 行帽拆檔:OUT builder/全限定
//!   查詢/per-field sv 門控表/identity_hash 鑄造/unicode-escape/純 helper）、
//!   `std::collections::BTreeMap`。
//! 硬邊界：
//!   - **無 socket / 無 I/O / 無 async**：純同步狀態機,注入時鐘（now_ms）。出站 frame 由
//!     本檔 build,**送出必經 pacing 單一出口**（driver 以 `OutboundClass::AccountData` 主桶
//!     取 `OutboundGrant` 後 `send_framed`;contract details 非 historical 面,走主桶——IB
//!     現勘 pinned）。
//!   - **全限定查詢義務**：伺服端對**模糊** contractDetails 查詢有遞增 hold（官方:相似後續
//!     請求 hold 一分鐘,DIVERGENT 細節）——builder 只接受全限定 STK 查詢（conId 或
//!     symbol+STK+exchange+USD;`QueryNotFullyQualified` typed 拒),請求 timeout 正規化
//!     兜底（逾時=typed 釋放槽+audit,絕不懸掛）。
//!   - **message-version 硬 pin ==8**：IN 10 自帶 message-version 欄（sv≥163 世代無此欄,
//!     與 sv≤157 ceiling 互為表裡）——≠8 = 佈局權威失效,typed fail-closed（毒化非猜讀）。
//!   - **本切片零行情面**：不做 reqMktData/reqMarketDataType/**regulatorySnapshot**（後者
//!     paper 也計費,源碼封死歸 W6-S3 紅線）;identity 是 S2 日曆/S3 行情的前置契約。
//!   - **唯讀識別面**：只 build 唯讀 contract details 請求——**絕不新增下單/改單/撤單
//!     builder**（IBKR_TODO §2 permanent denied 面）。
//!   - **零 production caller（W3-W7 B′ 姿態）**：本模塊經 driver 測試域消費;default build
//!     隨 TWS 連接器面 DCE,g4/driver-absence audit 保綠。Bybit crypto_perp 不變;無 DB
//!     migration。

// intentional-DCE 姿態繼承 wire/session/pacing/driver/account_data/order_exec（見各檔
// MODULE_NOTE）:本模塊在 default build 零 production caller（真消費者=driver 測試域;
// W6+ 接 IPC 投影面）。
#![allow(dead_code)]

use std::collections::BTreeMap;
use std::time::Duration;

use openclaw_types::{
    IbkrInstrumentIdentityRowBlocker, IbkrInstrumentIdentityRowV1, IbkrSecTypeV1, IbkrStockTypeV1,
    IBKR_INSTRUMENT_IDENTITY_ROW_CONTRACT_ID,
};

use crate::ibkr_tws_account_data::SnapshotStaleness;
use crate::ibkr_tws_wire::{
    decode_fields, CodecError, IN_BOND_CONTRACT_DATA_MSG_ID, IN_CONTRACT_DATA_END_MSG_ID,
    IN_CONTRACT_DATA_MSG_ID,
};

// support 子模塊（800 行帽拆檔;沿 `_tests` 的 `#[path]` 檔名慣例）:純 codec/查詢/門控表/
// 雜湊 helper 居彼,狀態機恆在本檔。
#[path = "ibkr_tws_contract_data_support.rs"]
mod support;
use support::{
    classify_wire_currency, decode_unicode_escape_minimal, expect_msg_id, parse_i64, staleness_of,
    sv_gate, FieldCursor, SV_GATE_AGG_GROUP, SV_GATE_LONG_NAME_UNICODE_ESCAPE,
    SV_GATE_MARKET_RULE_IDS, SV_GATE_MD_SIZE_MULTIPLIER, SV_GATE_REAL_EXPIRATION_DATE,
    SV_GATE_STOCK_TYPE, SV_GATE_UNDER_SYMBOL_SECTYPE,
};
pub(crate) use support::{
    compute_identity_hash, encode_req_contract_details, ContractDetailsQuery,
};

// ===========================================================================
// (b) config（全 config 化;參數禁假功能——每項必真實生效。per-field sv 門控表居 support）
// ===========================================================================

/// contract details 消化配置。default = IB 現勘常數（2026-07-17）+ W5-S3 DIVERGENT-1 兩界
/// 慣例。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct ContractDataConfig {
    /// **floor guard**:協商 sv < 此值 → 整面拒開消化（默認 145,對齊 W5-S3 order/exec 面
    /// ——一次覆蓋舊佈局門檻,不實作雙分支;IN 10 的 per-field 表只需服務 [floor,ceiling]
    /// band）。
    pub min_server_version_floor: i32,
    /// **ceiling guard**:官方位元組 pin 上界（默認 157;與 message-version==8 pin 互為
    /// 表裡——sv≥163 世代無 version 欄）。sv > 此值按 pinned 佈局 decode,尾端有未讀欄 →
    /// 該 frame 拒收+audit（禁猜讀;10.x band 佈局 UNVERIFIED,補證歸 operator follow-up）。
    pub max_pinned_server_version: i32,
    /// 請求 timeout（typed 正規化:在途請求逾此窗無 End → `expire_overdue` 釋放槽+audit,
    /// 絕不懸掛——伺服端模糊查詢 hold 的兜底;全限定查詢影響低仍必設）。
    pub request_timeout: Duration,
    /// identity 快照新鮮窗（End 後逾窗 → `Stale` 保守標記;identity 是 PIT 事實,逐日
    /// 刷新紀律=24h——tradingHours 逐日變,隔日快照即應降信心重取）。
    pub identity_stale_after: Duration,
    /// **快照 map 行數上界（W6-S0 cap 慣例,E3 LOW-02 家族）**:identity 快照 map 的
    /// config 化 cap。依據:單 entry 由單 frame 產生（1 frame ≤ 64KB）,driver 單 serve
    /// 迴圈 frame 預算 100_000 → 無 cap = 無界注入面;真實 lane 量級=數百 instrument,
    /// 4096 為 10×+ 裕度。**超界=該面 `Invalidated` 毒化+audit 計數**（fail-closed;
    /// 禁靜默驅逐——驅逐=對消費端的記帳謊言）。
    pub max_identity_rows: usize,
    /// **secIdList bounded-count guard**:count 欄超此上界=荒謬值拒（真實 STK secIdList
    /// 量級=個位數 ISIN/CUSIP tag;64 為 10×+ 裕度。count 用於確定性 skip,不設界=按
    /// untrusted 長度盲走游標）。
    pub max_sec_id_list_entries: i64,
}

impl Default for ContractDataConfig {
    fn default() -> Self {
        Self {
            min_server_version_floor: 145,
            max_pinned_server_version: 157,
            request_timeout: Duration::from_secs(30),
            identity_stale_after: Duration::from_secs(86_400),
            max_identity_rows: 4096,
            max_sec_id_list_entries: 64,
        }
    }
}

// ===========================================================================
// (c) typed 裁決:reject + audit（全 typed;禁 panic / 捏值 / 默認值 / silent drop）
// ===========================================================================

/// 消化層 typed 拒絕。呼叫端（driver）分流:`WireMalformed` = wire 損壞 → fail-closed
/// 斷線;其餘 = 資料層 fail-closed（毒化/frame 級拒收/typed 計數,session 續 serve,不 panic）。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub(crate) enum ContractDataReject {
    /// 快照請求已在途/已成（單槽結構性自限;重取須先斷線/timeout/毒化世代重評後 re-begin）。
    #[error("contract details request already active (engine self-limit = 1 slot)")]
    RequestAlreadyActive,
    /// **floor**:協商 sv 低於 config 下界 → 整面拒開消化（不實作舊佈局分支）。
    #[error("server version {server_version} below contract data floor {floor}")]
    ServerVersionBelowFloor { server_version: i32, floor: i32 },
    /// 全限定義務:查詢缺 conId 且 symbol/exchange 不全 → 拒發（模糊查詢=伺服端遞增
    /// hold 面,結構性不送）。
    #[error("contract details query not fully qualified (conId or symbol+exchange required)")]
    QueryNotFullyQualified,
    /// 未 begin 任何請求卻收到資料/End——未請而收=協議意外,fail-closed 拒併入
    /// （沿 W5-S2 `NoActiveSubscription` 語義;audit 計數丟棄可觀測）。
    #[error("contract data frame without active request")]
    NoActiveRequest,
    /// 入站 reqId 與活躍請求不符（串流錯配,fail-closed 不併入/不轉相位）。
    #[error("unexpected req id {got} for active contract details request")]
    UnexpectedReqId { got: i64 },
    /// **message-version 撕 pin**:IN 10 自帶 version 欄 ≠8 → 佈局權威失效,毒化非猜讀
    /// （sv≥163 世代無此欄,與 ceiling 互為表裡——typed fail-closed,session 續 serve）。
    #[error("contract data message version {got} != pinned 8 (layout authority lost)")]
    MessageVersionUnpinned { got: i64 },
    /// **secIdList bounded-count guard**:count 超 config 上界=荒謬值 → 毒化+audit
    /// （untrusted 長度不作盲走游標依據;fail-closed）。
    #[error("sec id list count {got} exceeds bound (absurd; refuse to cursor-walk)")]
    SecIdListCountAbsurd { got: i64 },
    /// **ceiling 佈局窗**:sv>157 且全欄消費後尾端仍有未讀欄 → 該 frame 拒收+audit
    /// （10.x band 佈局 UNVERIFIED,禁猜讀;非斷線非毒化——band 內佈局成長是已知可能性）。
    #[error("frame exceeds pinned (sv<=157) layout for msg {msg_id} (refuse to guess-read)")]
    PinnedLayoutOverflow { msg_id: i64 },
    /// identity row 契約 blocker（表外 secType/stockType/venue/幣別/刻度…）——資料層
    /// fail-closed:快照毒化 `Invalidated`,不 panic、不斷線、不默默跳行。
    #[error("instrument identity row blocked by contract")]
    IdentityRowBlocked(Vec<IbkrInstrumentIdentityRowBlocker>),
    /// **恢復政策（W6-S0 慣例）**:毒化=同一 connect 世代內終態——世代內 re-begin 一律拒;
    /// 唯 driver 世代推進（新 handshake 成功,`on_new_connection_generation`）重評後可
    /// re-begin。
    #[error("contract data face invalidated; re-begin requires a new connection generation")]
    InvalidatedUntilNewGeneration,
    /// **cap 超界（W6-S0 慣例）**:快照 map 行數超 config 上界 → 該面毒化+audit 計數
    /// （fail-closed;禁靜默驅逐=不做記帳謊言）。
    #[error("identity snapshot row cap exceeded (face poisoned, no silent eviction)")]
    SnapshotRowCapExceeded,
    /// wire 形狀損壞（欄位缺/非數字/非 ASCII/錯 msgId）——呼叫端按既有紀律 fail-closed 斷線。
    #[error("wire malformed: {0}")]
    WireMalformed(CodecError),
}

/// 請求 timeout 的 typed 裁決產物（`expire_overdue` 回傳;非懸掛的證明面——driver pump
/// 據 staleness 重取,IPC 投影面據 audit 觀測）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct ContractDataRequestTimeout {
    /// 逾時請求的 reqId。
    pub req_id: i64,
    /// 請求發出的注入時刻。
    pub started_at_ms: u64,
    /// 裁決時刻。
    pub expired_at_ms: u64,
}

/// audit 計數器（W6-S0 慣例:全部單調遞增+`*_last_*` 樣本欄;driver/W6 IPC 投影唯讀
/// 消費）。為什麼需要:driver 對資料層 typed reject 走 `Err(_)=>{}` 分流續 serve——無
/// audit 則 blocker 身分零觀測。
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub(crate) struct ContractDataAudit {
    /// IN 18 bondContractData typed-ignore 記帳數（cash lane 丟棄可觀測,不消化不
    /// unknown-fail）。
    pub bond_contract_data_ignored: u64,
    /// message-version ≠8 撕 pin 拒數。
    pub message_version_unpinned_rejects: u64,
    /// 最後一次撕 pin 的 version 值。
    pub message_version_last_got: Option<i64>,
    /// identity row 契約 blocker 拒數。
    pub identity_row_blocked_rejects: u64,
    /// 最後一筆 identity row blocker 列表（per-face 樣本欄）。
    pub identity_row_last_blockers: Vec<IbkrInstrumentIdentityRowBlocker>,
    /// 未請而收承接拒數（未 begin/毒化/斷線失效窗口的入站丟棄可觀測）。
    pub no_active_request_rejects: u64,
    /// 入站 reqId 錯配拒數。
    pub unexpected_req_id_rejects: u64,
    /// wire 損壞拒數（呼叫端 fail-closed 斷線;此處留身分供斷線前因對賬）。
    pub wire_malformed_rejects: u64,
    /// 最後一次 wire 損壞的 typed 描述（CodecError 顯示串,不含 payload 原文）。
    pub wire_malformed_last_note: Option<String>,
    /// 快照 map cap 超界毒化數（禁靜默驅逐）。
    pub row_cap_exceeded_rejects: u64,
    /// secIdList 荒謬 count 拒數。
    pub sec_id_list_absurd_rejects: u64,
    /// 最後一次荒謬 count 值。
    pub sec_id_list_last_got: Option<i64>,
    /// ceiling 佈局窗拒收 frame 數（sv>157 尾端未讀欄;10.x band 補證信號）。
    pub pinned_layout_overflow_rejects: u64,
    /// 請求 timeout typed 裁決數（非懸掛證明面）。
    pub request_timeouts: u64,
    /// 最後一次 timeout 的 reqId。
    pub request_timeout_last_req_id: Option<i64>,
}

/// 單槽生命週期相位（同構 W5-S2/S3 `SubPhase`——該型別為模塊私有,此處同名同義複刻,
/// 不越界改動 sibling 檔）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SubPhase {
    Idle,
    /// 已發請求,End 前（回報進行中;請求 timeout 只在此相位計）。
    SnapshotIncomplete,
    /// End 已到:快照完整（identity=PIT 事實,staleness 轉新鮮窗語義）。
    Live,
    /// 契約 blocker / 撕 pin / 荒謬 count 毒化（fail-closed;同 connect 世代內終態,唯
    /// 世代推進 `on_new_connection_generation` 重評後 re-begin 離開——W6-S0 恢復政策）。
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
// (d) ContractDataDigest — 單槽快照狀態機 + 行消化 + audit
// ===========================================================================

/// contract details 消化器。純同步、注入時鐘;identity 行以 W6-S1 契約承載
/// （`validate(now_ms)` 過才併入;identity_hash 於本檔鑄造——preimage 單一定義點在契約）。
/// 出站 frame 由 `begin_contract_details` 產出,**送出必經 pacing 單一出口**（呼叫端持
/// `OutboundGrant` 才可 `send_framed`）。
pub(crate) struct ContractDataDigest {
    config: ContractDataConfig,
    /// begin 時綁定的協商 serverVersion（=per-field 門控 context;`None`=整面未開,
    /// 入站全拒。floor guard 於 begin 把關 → 綁定值恆 ≥ floor）。
    server_version: Option<i32>,
    /// 快照單調序列（每次 begin 遞增;契約要求非零,沿 W5-S2）。
    snapshot_seq: u64,
    phase: SubPhase,
    req_id: Option<i64>,
    /// 請求發出時刻（timeout 基準;僅 SnapshotIncomplete 相位有語義）。
    request_started_at_ms: u64,
    /// 最新 identity 行,鍵=con_id（主鍵;同 conId 後到覆蓋——單查詢可回多行,如模糊消歧,
    /// 全限定下慣為 1 行）。
    identity_rows: BTreeMap<i64, IbkrInstrumentIdentityRowV1>,
    last_update_ms: u64,
    audit: ContractDataAudit,
}

impl ContractDataDigest {
    pub(crate) fn new(config: ContractDataConfig) -> Self {
        Self {
            config,
            server_version: None,
            snapshot_seq: 0,
            phase: SubPhase::Idle,
            req_id: None,
            request_started_at_ms: 0,
            identity_rows: BTreeMap::new(),
            last_update_ms: 0,
            audit: ContractDataAudit::default(),
        }
    }

    // ---- 出站意圖（送出經 pacing 單一出口,見模塊硬邊界）----

    /// 開始 contract details 快照:回待送 v8 frame。floor guard → 世代政策 → 單槽自限 →
    /// 全限定義務 → 清舊行、遞增 seq、綁定 sv context、記 timeout 基準。
    /// Idle/DisconnectedStale 可（重）取;**Invalidated=世代內終態**（W6-S0 恢復政策）。
    pub(crate) fn begin_contract_details(
        &mut self,
        server_version: i32,
        req_id: i64,
        query: &ContractDetailsQuery,
        now_ms: u64,
    ) -> Result<Vec<u8>, ContractDataReject> {
        if server_version < self.config.min_server_version_floor {
            return Err(ContractDataReject::ServerVersionBelowFloor {
                server_version,
                floor: self.config.min_server_version_floor,
            });
        }
        if self.phase == SubPhase::Invalidated {
            return Err(ContractDataReject::InvalidatedUntilNewGeneration);
        }
        if self.phase.is_active() {
            return Err(ContractDataReject::RequestAlreadyActive);
        }
        if !query.is_fully_qualified() {
            return Err(ContractDataReject::QueryNotFullyQualified);
        }
        self.server_version = Some(server_version);
        self.snapshot_seq += 1;
        self.identity_rows.clear();
        self.phase = SubPhase::SnapshotIncomplete;
        self.req_id = Some(req_id);
        self.request_started_at_ms = now_ms;
        Ok(encode_req_contract_details(req_id, query))
    }

    /// **請求 timeout typed 化**（非懸掛）:在途請求逾 config 窗無 End → 釋放槽回 Idle +
    /// audit 落帳,回 typed 裁決產物。為什麼回 Idle 而非毒化:timeout 是伺服端 hold/丟包
    /// 的時間性失敗,非資料完整性失敗——pump 據 staleness 經 governor 重取（重試節奏由
    /// pacing 單一出口約束,不會空轉灌流）;IPC 投影面由 audit `request_timeouts` 觀測。
    pub(crate) fn expire_overdue(&mut self, now_ms: u64) -> Option<ContractDataRequestTimeout> {
        if self.phase != SubPhase::SnapshotIncomplete {
            return None;
        }
        let timeout_ms = self.config.request_timeout.as_millis() as u64;
        if now_ms.saturating_sub(self.request_started_at_ms) <= timeout_ms {
            return None;
        }
        let req_id = self.req_id.take().unwrap_or(-1);
        self.phase = SubPhase::Idle;
        self.identity_rows.clear();
        self.audit.request_timeouts += 1;
        self.audit.request_timeout_last_req_id = Some(req_id);
        Some(ContractDataRequestTimeout {
            req_id,
            started_at_ms: self.request_started_at_ms,
            expired_at_ms: now_ms,
        })
    }

    // ---- 入站消化（payload = 已 unframe 的欄位序,含 msgId 欄）----

    /// IN 10 contractData 行:message-version 硬 pin ==8 → per-field sv 表逐欄消費 →
    /// secIdList bounded skip → W6-S1 identity row 契約（identity_hash 於此鑄造）→
    /// 併入快照。任何 typed reject 過 `audit_reject` 落帳身分（driver `Err(_)=>{}` 分流
    /// 不零觀測,沿 W6-S0 慣例）。
    pub(crate) fn on_contract_data_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), ContractDataReject> {
        let r = self.contract_data_frame_inner(payload, now_ms);
        if let Err(e) = &r {
            self.audit_reject(e);
        }
        r
    }

    fn contract_data_frame_inner(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), ContractDataReject> {
        let fields = decode_fields(payload).map_err(ContractDataReject::WireMalformed)?;
        // wire 形狀先裁（N1 紀律):msgId/version/reqId 三前導欄至少要在。
        if fields.len() < 3 {
            return Err(ContractDataReject::WireMalformed(CodecError::Malformed(
                "contract data needs >=3 leading fields",
            )));
        }
        expect_msg_id(&fields[0], IN_CONTRACT_DATA_MSG_ID)?;
        let message_version = parse_i64(&fields[1], "contract_data_version")?;
        let req_id = parse_i64(&fields[2], "contract_data_req_id")?;
        // 未請而收先裁（不得對未開槽做毒化副作用,沿 W5-S2 position 慣例）。
        if !self.phase.is_active() {
            return Err(self.reject_no_active_request());
        }
        if self.req_id != Some(req_id) {
            return Err(ContractDataReject::UnexpectedReqId { got: req_id });
        }
        // message-version 硬 pin ==8:≠8=佈局權威失效 → 毒化非猜讀（與 sv≤157 ceiling
        // 互為表裡,見模塊硬邊界）。
        if message_version != 8 {
            self.audit.message_version_unpinned_rejects += 1;
            self.audit.message_version_last_got = Some(message_version);
            self.phase = SubPhase::Invalidated;
            return Err(ContractDataReject::MessageVersionUnpinned {
                got: message_version,
            });
        }
        // begin 把關後 server_version 恆 Some;缺=槽不變量破裂,按 wire 意外保守斷線側。
        let sv = match self.server_version {
            Some(v) => v,
            None => {
                return Err(ContractDataReject::WireMalformed(CodecError::Malformed(
                    "contract data slot without bound server version",
                )))
            }
        };
        // ---- per-field sv 表逐欄消費（head 1-29 → secIdList → 門控尾段）----
        let mut cur = FieldCursor::new(&fields, 3);
        let symbol = cur.take()?.to_string(); // 1 symbol
        let sec_type_raw = cur.take()?.to_string(); // 2 secType
        cur.take()?; // 3 lastTradeDateOrContractMonth（STK 慣空;空白分裂 lastTradeTime 語義不 bind,讀位即棄）
        cur.take()?; // 4 strike（讀位即棄）
        cur.take()?; // 5 right
        let exchange = cur.take()?.to_string(); // 6 exchange
        let currency_raw = cur.take()?.to_string(); // 7 currency
        let local_symbol = cur.take()?.to_string(); // 8 localSymbol
        let market_name = cur.take()?.to_string(); // 9 marketName
        let trading_class = cur.take()?.to_string(); // 10 tradingClass
        let con_id = parse_i64(cur.take()?, "contract_data_con_id")?; // 11 conId
        let min_tick = cur.take()?.to_string(); // 12 minTick
                                                // 13 mdSizeMultiplier（sv≥110;floor=145 下恆在,表仍按門檻消費防 band 錯位）。
        let md_size_multiplier = if sv_gate(sv, SV_GATE_MD_SIZE_MULTIPLIER) {
            cur.take()?.to_string()
        } else {
            String::new()
        };
        let multiplier = cur.take()?.to_string(); // 14 multiplier
        let order_types = cur.take()?.to_string(); // 15 orderTypes
        let valid_exchanges = cur.take()?.to_string(); // 16 validExchanges
        let price_magnifier = parse_i64(cur.take()?, "contract_data_price_magnifier")?; // 17
        cur.take()?; // 18 underConId（讀位即棄）
        let long_name_raw = cur.take()?.to_string(); // 19 longName
        let primary_exchange = cur.take()?.to_string(); // 20 primaryExchange
        cur.take()?; // 21 contractMonth
        cur.take()?; // 22 industry
        cur.take()?; // 23 category
        cur.take()?; // 24 subcategory
        let time_zone_id = cur.take()?.to_string(); // 25 timeZoneId（legacy 名,原字串保真）
        let trading_hours = cur.take()?.to_string(); // 26 tradingHours
        let liquid_hours = cur.take()?.to_string(); // 27 liquidHours
        cur.take()?; // 28 evRule
        cur.take()?; // 29 evMultiplier
                     // 30 secIdList:count + N×(tag,value) 變長塊——bounded-count guard 後確定性 skip。
        let sec_id_count = parse_i64(cur.take()?, "contract_data_sec_id_count")?;
        if sec_id_count < 0 || sec_id_count > self.config.max_sec_id_list_entries {
            self.audit.sec_id_list_absurd_rejects += 1;
            self.audit.sec_id_list_last_got = Some(sec_id_count);
            self.phase = SubPhase::Invalidated;
            return Err(ContractDataReject::SecIdListCountAbsurd { got: sec_id_count });
        }
        for _ in 0..sec_id_count {
            cur.take()?; // tag
            cur.take()?; // value
        }
        // 門控尾段（讀位即棄,identity 契約不承載;表按 IB 現勘門檻,band 內缺席=不消費）。
        if sv_gate(sv, SV_GATE_AGG_GROUP) {
            cur.take()?; // 31 aggGroup
        }
        if sv_gate(sv, SV_GATE_UNDER_SYMBOL_SECTYPE) {
            cur.take()?; // 32 underSymbol
            cur.take()?; // 33 underSecType
        }
        if sv_gate(sv, SV_GATE_MARKET_RULE_IDS) {
            cur.take()?; // 34 marketRuleIds
        }
        if sv_gate(sv, SV_GATE_REAL_EXPIRATION_DATE) {
            cur.take()?; // 35 realExpirationDate
        }
        // 36 stockType（sv≥152;缺席=UnknownDenied → 契約 blocker——lane 的 ETF|COMMON
        // 判別是承載義務,sv 不足不升格為「未知即過」）。
        let stock_type = if sv_gate(sv, SV_GATE_STOCK_TYPE) {
            IbkrStockTypeV1::classify_wire_stock_type(cur.take()?)
        } else {
            IbkrStockTypeV1::UnknownDenied
        };
        // 尾端未讀欄裁決:sv≤ceiling 下多欄=wire 意外（精確消費紀律）;sv>ceiling=band 內
        // 佈局成長 → 該 frame 拒收+audit（禁猜讀,非毒化非斷線——沿 W5-S3 ceiling 慣例）。
        if cur.remaining() > 0 {
            if sv > self.config.max_pinned_server_version {
                self.audit.pinned_layout_overflow_rejects += 1;
                return Err(ContractDataReject::PinnedLayoutOverflow {
                    msg_id: IN_CONTRACT_DATA_MSG_ID,
                });
            }
            return Err(ContractDataReject::WireMalformed(CodecError::Malformed(
                "contract data has unread trailing fields (sv<=157 layout)",
            )));
        }
        // longName unicode-escape（sv≥153;漏解=靜默 mojibake——最小實作見 fn 注釋）。
        let long_name = if sv_gate(sv, SV_GATE_LONG_NAME_UNICODE_ESCAPE) {
            decode_unicode_escape_minimal(&long_name_raw)
        } else {
            long_name_raw
        };
        // ---- 契約鑄行（先契約後消化;identity_hash 以 preimage 單一定義點鑄造）----
        let mut row = IbkrInstrumentIdentityRowV1 {
            contract_id: IBKR_INSTRUMENT_IDENTITY_ROW_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: openclaw_types::AssetLane::StockEtfCash,
            broker: openclaw_types::Broker::Ibkr,
            con_id,
            symbol,
            sec_type: IbkrSecTypeV1::classify_wire_sec_type(&sec_type_raw),
            exchange,
            primary_exchange,
            currency: classify_wire_currency(&currency_raw),
            local_symbol,
            trading_class,
            market_name,
            min_tick_decimal: min_tick,
            md_size_multiplier,
            multiplier,
            order_types,
            valid_exchanges,
            price_magnifier,
            long_name,
            time_zone_id,
            trading_hours,
            liquid_hours,
            stock_type,
            identity_hash: String::new(),
            captured_at_ms: now_ms,
            snapshot_seq: self.snapshot_seq,
            order_routed: false,
            secret_content_serialized: false,
        };
        row.identity_hash = compute_identity_hash(&row);
        let verdict = row.validate(now_ms);
        if !verdict.accepted {
            // 契約 blocker（表外 secType/stockType/venue/幣別/刻度…）→ 快照毒化,
            // fail-closed 不併入（沿 W5-S2 blocker=毒化慣例）。
            self.phase = SubPhase::Invalidated;
            return Err(ContractDataReject::IdentityRowBlocked(verdict.blockers));
        }
        // W6-S0 cap 慣例:新鍵且已達上界 → 毒化+audit（fail-closed;禁靜默驅逐）。既有鍵
        // 覆蓋不受 cap 限（不增長）。
        if !self.identity_rows.contains_key(&con_id)
            && self.identity_rows.len() >= self.config.max_identity_rows
        {
            self.phase = SubPhase::Invalidated;
            return Err(ContractDataReject::SnapshotRowCapExceeded);
        }
        self.last_update_ms = now_ms;
        self.identity_rows.insert(con_id, row);
        Ok(())
    }

    /// IN 52 contractDataEnd（**嚴格 3 欄** `[msgId, version, reqId]`,IB 現勘 pinned）:
    /// 快照收批 → `Live`（End 界定快照;identity=PIT 事實,staleness 轉新鮮窗語義）。
    pub(crate) fn on_contract_data_end_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), ContractDataReject> {
        let r = self.contract_data_end_frame_inner(payload, now_ms);
        if let Err(e) = &r {
            self.audit_reject(e);
        }
        r
    }

    fn contract_data_end_frame_inner(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), ContractDataReject> {
        let fields = decode_fields(payload).map_err(ContractDataReject::WireMalformed)?;
        // 嚴格 3 欄（按位消費不容錯位,沿 W5-S2 F2 精確欄長紀律）。
        if fields.len() != 3 {
            return Err(ContractDataReject::WireMalformed(CodecError::Malformed(
                "contract data end needs exactly 3 fields",
            )));
        }
        expect_msg_id(&fields[0], IN_CONTRACT_DATA_END_MSG_ID)?;
        let req_id = parse_i64(&fields[2], "contract_data_end_req_id")?;
        if !self.phase.is_active() {
            return Err(self.reject_no_active_request());
        }
        if self.req_id != Some(req_id) {
            return Err(ContractDataReject::UnexpectedReqId { got: req_id });
        }
        self.phase = SubPhase::Live;
        self.last_update_ms = now_ms;
        Ok(())
    }

    /// IN 18 bondContractData:**typed-ignore**（IB 現勘裁決:cash lane 收到=記帳丟棄,
    /// 不消化、不 unknown-fail——BOND 是白名單外資產但 msgId 已知,fail-closed 斷線反而
    /// 把良性雜訊升格為 transport 事件）。只驗 msgId 身分,不 bind 任何 bond 欄語義。
    pub(crate) fn on_bond_contract_data_frame(
        &mut self,
        payload: &[u8],
    ) -> Result<(), ContractDataReject> {
        let r = self.bond_contract_data_frame_inner(payload);
        if let Err(e) = &r {
            self.audit_reject(e);
        }
        r
    }

    fn bond_contract_data_frame_inner(&mut self, payload: &[u8]) -> Result<(), ContractDataReject> {
        let fields = decode_fields(payload).map_err(ContractDataReject::WireMalformed)?;
        if fields.is_empty() {
            return Err(ContractDataReject::WireMalformed(CodecError::Malformed(
                "empty bond contract data frame",
            )));
        }
        expect_msg_id(&fields[0], IN_BOND_CONTRACT_DATA_MSG_ID)?;
        self.audit.bond_contract_data_ignored += 1;
        Ok(())
    }

    // ---- 生命週期:斷線 / 世代推進（沿 W6-S0 慣例）----

    /// 斷線:活躍面標 `DisconnectedStale`（快照不跨連線存活——重連需 re-begin;行保留供
    /// 唯讀檢視,staleness 已明示不可信）。Idle/Invalidated 維持原相位（毒化事實不被斷線
    /// 沖淡;毒化面的重評歸 `on_new_connection_generation`）。
    pub(crate) fn on_disconnect(&mut self) {
        if self.phase.is_active() {
            self.phase = SubPhase::DisconnectedStale;
            self.req_id = None;
        }
    }

    /// **W6-S0 恢復政策**（同構 W5-S2/S3）:driver 世代推進（新 handshake 成功）時重評
    /// 毒化面——`Invalidated` → `DisconnectedStale`,與既有「斷線→DisconnectedStale→
    /// re-begin」語義合流。行保留供唯讀對賬;audit 計數跨世代累積（telemetry 語義,不清零）。
    pub(crate) fn on_new_connection_generation(&mut self) {
        if self.phase == SubPhase::Invalidated {
            self.phase = SubPhase::DisconnectedStale;
            self.req_id = None;
        }
    }

    // ---- 觀測（typed staleness 綁定視圖 + audit;沿 W6-S0 慣例）----

    /// identity 快照 staleness（typed 六態;End 後按 PIT 逐日刷新窗保守標記）。
    pub(crate) fn identity_staleness(&self, now_ms: u64) -> SnapshotStaleness {
        staleness_of(
            self.phase,
            self.last_update_ms,
            self.config.identity_stale_after,
            now_ms,
        )
    }

    /// 唯讀檢視:identity 面 **staleness 綁定視圖**（W6-S0 慣例）——rows 只能與其
    /// staleness 一同取得,使「部分/毒化/斷線快照被當全量消費」**結構性不可能**
    /// （BTreeMap=確定序,鍵=conId 主鍵）。
    pub(crate) fn identity_rows(
        &self,
        now_ms: u64,
    ) -> (
        SnapshotStaleness,
        impl Iterator<Item = &IbkrInstrumentIdentityRowV1>,
    ) {
        (self.identity_staleness(now_ms), self.identity_rows.values())
    }

    /// audit 計數器唯讀檢視。
    pub(crate) fn audit(&self) -> &ContractDataAudit {
        &self.audit
    }

    /// 當前快照世代序（telemetry;契約 snapshot_seq 注入源）。
    pub(crate) fn snapshot_seq(&self) -> u64 {
        self.snapshot_seq
    }

    // ---- 內部 ----

    /// 未請而收承接拒的收斂點:audit 計數（丟棄可觀測）後回 typed reject。
    fn reject_no_active_request(&mut self) -> ContractDataReject {
        self.audit.no_active_request_rejects += 1;
        ContractDataReject::NoActiveRequest
    }

    /// 入站 typed reject → audit 身分落帳（單調計數+最後樣本;沿 W6-S0 慣例——driver 對
    /// 資料層 reject 走 `Err(_)=>{}` 續 serve,身分由此觀測面承載）。已在拒點就地計數者
    /// （撕 pin/荒謬 count/overflow/未請而收）此處跳過防重複;begin 域拒（floor/單槽/
    /// 全限定/世代政策）由 pump 的閘先擋,不屬入站觀測面。
    fn audit_reject(&mut self, e: &ContractDataReject) {
        match e {
            ContractDataReject::WireMalformed(c) => {
                self.audit.wire_malformed_rejects += 1;
                self.audit.wire_malformed_last_note = Some(c.to_string());
            }
            ContractDataReject::IdentityRowBlocked(blockers) => {
                self.audit.identity_row_blocked_rejects += 1;
                self.audit.identity_row_last_blockers = blockers.clone();
            }
            ContractDataReject::UnexpectedReqId { .. } => {
                self.audit.unexpected_req_id_rejects += 1;
            }
            ContractDataReject::SnapshotRowCapExceeded => {
                self.audit.row_cap_exceeded_rejects += 1;
            }
            ContractDataReject::MessageVersionUnpinned { .. }
            | ContractDataReject::SecIdListCountAbsurd { .. }
            | ContractDataReject::PinnedLayoutOverflow { .. }
            | ContractDataReject::NoActiveRequest
            | ContractDataReject::RequestAlreadyActive
            | ContractDataReject::ServerVersionBelowFloor { .. }
            | ContractDataReject::QueryNotFullyQualified
            | ContractDataReject::InvalidatedUntilNewGeneration => {}
        }
    }
}

#[cfg(test)]
#[path = "ibkr_tws_contract_data_tests.rs"]
mod tests;
