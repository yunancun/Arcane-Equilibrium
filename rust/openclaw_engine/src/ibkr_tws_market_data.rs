//! MODULE_NOTE
//! 模塊用途：IBKR **W6-S3 market data lane 消化層**（IBKR_TODO §5-W6 範圍 in 2/3;沿 W6-S1
//!   `ibkr_tws_contract_data` / W5-S2/S3 全部慣例）。把 `reqMktData` 的 L1 tick 訂閱生命週期
//!   收斂為 typed、fail-closed 的消化狀態機:出站 reqMktData/cancelMktData/reqMarketDataType
//!   builder（STK-only;**regulatorySnapshot 資金效果封死**;snapshot⊥genericTickList,居
//!   `_support`）→ IN tick 家族 decode（TICK_PRICE 合成 tickSize 去重/TICK_SIZE 嚴格 5 欄/
//!   per-reqId entitlement FSM 三態+錯誤碼映射/TICK_REQ_PARAMS 無 version/generic·string
//!   typed-ignore）→ W6-S3 quote row + provenance 契約填值（delayed 值必標 entitlement=Delayed,
//!   契約 validate 兜底;provenance_hash 消化層鑄）→ snapshot 11s 終態 timeout。
//! 主要區段（本檔=狀態機;builder/門控常數/entitlement 錯誤碼分類/tick 值紀律/hash 居
//!   `ibkr_tws_market_data_support.rs`,tests 居 `_tests`）：
//!   - config：`MarketDataConfig`（floor / lines 上限 semaphore / snapshot 終態窗 / quote
//!     新鮮窗;參數禁假功能,每項真生效）。
//!   - typed 裁決：`MarketDataReject`（builder 拒 + wire 損壞 + lines 耗盡 + 契約 blocker +
//!     未訂而收）+ `MarketDataAudit`（沿 `*_last_*` 樣本欄慣例）。
//!   - `MarketDataDigest`：per-reqId 訂閱表狀態機（begin → IN tick → SNAPSHOT_END/timeout;
//!     lines count quota / cancel-before-resubscribe 紀律 / per-reqId entitlement FSM /
//!     `(staleness, rows)` 綁定視圖 / 世代重評 / 斷線重訂）。
//! 依賴：`ibkr_tws_wire`（codec/IN 常數）、`ibkr_tws_account_data`（`SnapshotStaleness` 六態
//!   共用）、`openclaw_types`（W6-S3 quote/provenance 契約）、support 子模塊、`BTreeMap`。
//! 硬邊界：
//!   - **regulatorySnapshot 封死**（見 support;每次 0.01 USD 且 paper 亦計費=資金效果,
//!     結構上不可由任何路徑翻真）。
//!   - **STK-only** / **snapshot ⊥ genericTickList**（builder 定界;見 support）。
//!   - **無 socket / 無 I/O / 無 async**:純同步注入時鐘,出站 frame 由本檔 build,**送出必經
//!     pacing 單一出口**（driver 以 `OutboundClass::MarketData` 或主桶取 grant 後 `send_framed`;
//!     lines semaphore=訂閱數配額,與 W3 50msg/s rate bucket 分軸——IB 現勘 pinned）。
//!   - **唯讀行情面**:只 build 唯讀 market data 請求——**絕不新增下單/改單/撤單 builder**。
//!   - **零 production caller（W3-W7 B′ 姿態）**:本模塊經 driver 測試域消費;default build 隨
//!     TWS 連接器面 DCE,g4/driver-absence audit 保綠。Bybit crypto_perp 不變;無 DB migration。

// intentional-DCE 姿態繼承 wire/session/pacing/driver/account_data/order_exec/contract_data
// （見各檔 MODULE_NOTE）:本模塊在 default build 零 production caller（真消費者=driver
// 測試域;W6+ 接 IPC 投影面）。
#![allow(dead_code)]

use std::collections::BTreeMap;
use std::time::Duration;

use openclaw_types::{
    IbkrMarketDataProvenanceV1, IbkrPriceAdjustmentV1, IbkrQuoteRowV1, IbkrTickEntitlementV1,
    IbkrTickTypeV1, IbkrTickValueKind, IBKR_CALENDAR_HASH_UNBOUND_SENTINEL,
    IBKR_MARKET_DATA_PROVENANCE_CONTRACT_ID, IBKR_QUOTE_ROW_CONTRACT_ID,
};

use crate::ibkr_tws_account_data::SnapshotStaleness;
use crate::ibkr_tws_wire::{
    decode_fields, CodecError, IN_MARKET_DATA_TYPE_MSG_ID, IN_TICK_GENERIC_MSG_ID,
    IN_TICK_PRICE_MSG_ID, IN_TICK_REQ_PARAMS_MSG_ID, IN_TICK_SIZE_MSG_ID,
    IN_TICK_SNAPSHOT_END_MSG_ID, IN_TICK_STRING_MSG_ID,
};

#[path = "ibkr_tws_market_data_support.rs"]
mod support;
use support::{
    classify_entitlement_error, compute_provenance_hash, expect_msg_id, field_key, parse_i64,
    sanitize_tick_value, EntitlementErrorOutcome, MarketDataAudit, ReqEntitlement,
    SnapshotTerminal, SubPhase, Subscription, MKT_DATA_SERVER_VERSION_FLOOR,
};
pub(crate) use support::{
    encode_cancel_mkt_data, encode_req_market_data_type, encode_req_mkt_data, MarketDataRequest,
};
// 資金紅線常量僅 builder 機器守衛測試消費（非 test build 無 caller）→ 測試域專屬 re-export。
#[cfg(test)]
pub(crate) use support::REGULATORY_SNAPSHOT_WIRE;

// ===========================================================================
// config（全 config 化;參數禁假功能——每項必真實生效）
// ===========================================================================

/// market data 消化配置。default = IB 現勘常數（2026-07-17）+ W6-S1 floor 慣例。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct MarketDataConfig {
    /// **floor guard**:協商 sv < 此值 → 拒開訂閱（默認 145,對齊 W5-S3/W6-S1——reqMktData
    /// v11 body 無條件 emit conId/tradingClass 僅 sv≥145 安全,見 support IB-NOTE-2）。
    pub min_server_version_floor: i32,
    /// **lines 上限（count semaphore;IB 默認 100=同時活躍訂閱數）**:config 保守 <100
    /// （默認 90 留裕度）。超界=`LinesExhausted` typed 拒（backpressure,**禁靜默驅逐**既有
    /// 訂閱——cancel-before-resubscribe 紀律歸 pump）。與 W3 50msg/s rate bucket 分軸。
    pub max_lines: usize,
    /// **snapshot 終態窗**（IB 現勘:snapshot=true 於 11s 後 server 送 TICK_SNAPSHOT_END 並
    /// 自動取消;此為 END 缺席的兜底,11s+裕度=13s → typed 終態釋放 line+audit,絕不懸掛）。
    pub snapshot_terminal_after: Duration,
    /// quote 新鮮窗（streaming/snapshot-complete 逾此窗無 tick → `Stale` 保守標記;L1 tick
    /// 高頻,逾窗即應降信心)。
    pub quote_stale_after: Duration,
}

impl Default for MarketDataConfig {
    fn default() -> Self {
        Self {
            min_server_version_floor: MKT_DATA_SERVER_VERSION_FLOOR,
            max_lines: 90,
            snapshot_terminal_after: Duration::from_secs(13),
            quote_stale_after: Duration::from_secs(5),
        }
    }
}

// ===========================================================================
// typed 裁決:reject + audit（全 typed;禁 panic / 捏值 / 默認值 / silent drop）
// ===========================================================================

/// 消化層 typed 拒絕。呼叫端（driver）分流:`WireMalformed` = wire 損壞 → fail-closed 斷線;
/// 其餘 = 資料層 fail-closed（毒化/backpressure/typed 計數,session 續 serve,不 panic）。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub(crate) enum MarketDataReject {
    /// **snapshot ⊥ genericTickList**（builder 級;IB 現勘:snapshot 一次性,tick 列表無意義且
    /// server 拒;不送）。
    #[error("snapshot market data request must not carry a generic tick list")]
    SnapshotWithGenericTicks,
    /// **floor**:協商 sv 低於 config 下界 → 拒開訂閱（不實作舊佈局分支）。
    #[error("server version {server_version} below market data floor {floor}")]
    ServerVersionBelowFloor { server_version: i32, floor: i32 },
    /// **lines 上限（count semaphore）**:活躍訂閱數已達 config 上界 → 拒新訂（backpressure;
    /// cancel-before-resubscribe 紀律歸 pump,**禁驅逐既有訂閱**）。
    #[error("market data lines exhausted ({active}/{max}; cancel before resubscribe)")]
    LinesExhausted { active: usize, max: usize },
    /// reqId 已有活躍訂閱（單一 reqId 結構性自限;重訂須先 cancel/終態/斷線後 re-begin）。
    #[error("market data subscription already active for req id {req_id}")]
    SubscriptionAlreadyActive { req_id: i64 },
    /// reqId 已 entitlement halt（354/10197/未知 code → 世代內終態;不重訂,新世代重評）。
    #[error("market data subscription req id {req_id} entitlement-halted (no resubscribe)")]
    EntitlementHalted { req_id: i64 },
    /// 未訂而收:入站 tick 的 reqId 無活躍訂閱 → fail-closed 拒併入（audit 計數丟棄可觀測)。
    #[error("market data tick for req id {req_id} without active subscription")]
    NoActiveSubscription { req_id: i64 },
    /// quote row 契約 blocker（值/entitlement/時戳…）——資料層 fail-closed:抑制不併入
    /// （不 panic、不斷線、不捏值;通常已由 `sanitize_tick_value` 前置抑制,此為契約兜底）。
    #[error("quote row blocked by contract")]
    QuoteRowBlocked,
    /// wire 形狀損壞（欄位缺/非數字/非 ASCII/錯 msgId）——呼叫端按既有紀律 fail-closed 斷線。
    #[error("wire malformed: {0}")]
    WireMalformed(CodecError),
}

// ===========================================================================
// MarketDataDigest — per-reqId 訂閱表狀態機 + tick 消化 + entitlement FSM + audit
// ===========================================================================

/// market data 消化器。純同步、注入時鐘;quote 行以 W6-S3 契約承載（`validate(now_ms)` 過才
/// 併入）。出站 frame 由 `begin_subscription`/`cancel_subscription`/`request_delayed_mode`
/// 產出,**送出必經 pacing 單一出口**（呼叫端持 `OutboundGrant` 才可 `send_framed`）。
pub(crate) struct MarketDataDigest {
    config: MarketDataConfig,
    /// begin 時綁定的協商 serverVersion（`None`=尚未開任何訂閱）。
    server_version: Option<i32>,
    /// 訂閱表（鍵=reqId;含活躍 + 終態供觀測）。
    subs: BTreeMap<i64, Subscription>,
    /// **delayed-only opt-in flag**:本 session 是否已顯式送 reqMarketDataType(3|4)。10167
    /// 「displaying delayed」僅在此為真時是合法降級確認,否則=協議意外拒（見 support
    /// `classify_entitlement_error`）。
    delayed_opt_in: bool,
    /// 全域單調 tick 序列（每 materialize 遞增;契約 `seq` 非零源）。
    seq_counter: u64,
    audit: MarketDataAudit,
}

impl MarketDataDigest {
    pub(crate) fn new(config: MarketDataConfig) -> Self {
        Self {
            config,
            server_version: None,
            subs: BTreeMap::new(),
            delayed_opt_in: false,
            seq_counter: 0,
            audit: MarketDataAudit::default(),
        }
    }

    // ---- 出站意圖（送出經 pacing 單一出口,見模塊硬邊界）----

    /// **delayed-only v1 send-before-subscribe**:回待送 reqMarketDataType(3) frame 並記
    /// opt-in flag。為什麼先於訂閱:IB 現勘,降級是每 session 顯式 opt-in（送 type 3 後
    /// 訂閱才可能回 delayed tick / 10167 才是合法降級確認,非自動降級）。
    pub(crate) fn request_delayed_mode(&mut self) -> Vec<u8> {
        self.delayed_opt_in = true;
        encode_req_market_data_type(3)
    }

    /// 開始一個 L1 tick 訂閱:回待送 v11 reqMktData frame。floor guard → 單一 reqId 自限 →
    /// halt 記憶 → lines count quota → 綁定 sv/hash context。
    /// **W6-S4 溯源錨綁真值**:`instrument_identity_hash`（W6-S1）/`calendar_hash`（W6-S2 由
    /// driver 對該 conId 的 identity row 跑 `parse_trading_calendar`+`compute_calendar_hash`
    /// 產出真值）由 driver 供給。begin 當下該 conId 的 identity row 若尚未到達（contract details
    /// 與 market data 為獨立請求 lane,回報有先後）,driver 傳未綁哨兵/空——provenance mint 誠實
    /// 標未綁（fail-closed,絕不捏值）,待 row 到達由 `rebind_provenance_anchors_if_unbound` 補綁。
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn begin_subscription(
        &mut self,
        req: &MarketDataRequest,
        req_id: i64,
        server_version: i32,
        instrument_identity_hash: String,
        calendar_hash: String,
        now_ms: u64,
    ) -> Result<Vec<u8>, MarketDataReject> {
        // E2-N1 caller-contract:market-data 訂閱 reqId 恆正（enable_market_data 分配正 id）——
        // session-scope ERR_MSG 攜 reqId=-1,恆正令 -1 結構上不與任何訂閱撞（見 driver
        // entitlement 路由的 `rid > 0` 守衛）。違反=分配器 bug,debug 期即炸。
        debug_assert!(
            req_id > 0,
            "market data reqId must be positive (session-scope reqId=-1 must not collide)"
        );
        if server_version < self.config.min_server_version_floor {
            return Err(MarketDataReject::ServerVersionBelowFloor {
                server_version,
                floor: self.config.min_server_version_floor,
            });
        }
        // 既有訂閱檢查:活躍=自限拒;halt=世代內終態拒;其餘終態（Complete/Invalidated/
        // DisconnectedStale）可 re-begin（覆寫 slot,不新增 line）。
        let reusing_slot = match self.subs.get(&req_id) {
            Some(s) if s.phase.occupies_line() => {
                return Err(MarketDataReject::SubscriptionAlreadyActive { req_id })
            }
            Some(s) if s.phase == SubPhase::Halted => {
                return Err(MarketDataReject::EntitlementHalted { req_id })
            }
            Some(_) => true,
            None => false,
        };
        // lines count quota（**禁驅逐既有訂閱**;新 line 才計 cap,re-begin 既有 slot 不增）。
        if !reusing_slot {
            let active = self.lines_in_use();
            if active >= self.config.max_lines {
                self.audit.lines_exhausted_rejects += 1;
                return Err(MarketDataReject::LinesExhausted {
                    active,
                    max: self.config.max_lines,
                });
            }
        }
        // E2-F1 + IB-NOTE-2 floor assert 於 builder;被注入的 frame → typed WireMalformed,
        // 相位不動,絕不送出。
        let frame = encode_req_mkt_data(req_id, req, server_version)?;
        self.server_version = Some(server_version);
        self.subs.insert(
            req_id,
            Subscription {
                con_id: req.con_id,
                symbol: req.symbol.clone(),
                snapshot: req.snapshot,
                phase: if req.snapshot {
                    SubPhase::SnapshotPending
                } else {
                    SubPhase::Streaming
                },
                entitlement: ReqEntitlement::Pending,
                started_at_ms: now_ms,
                first_tick_at_ms: 0,
                last_tick_at_ms: 0,
                instrument_identity_hash,
                calendar_hash,
                quotes: BTreeMap::new(),
            },
        );
        Ok(frame)
    }

    /// cancel 一個訂閱:回待送 cancelMktData frame（若該 reqId 佔 line）並移除 slot（釋放
    /// line;cancel-before-resubscribe 紀律的 cancel 腿——lines 耗盡時 pump 據此先退訂）。
    /// reqId 不存在/已終態 → `None`（無 frame,冪等）。
    pub(crate) fn cancel_subscription(&mut self, req_id: i64) -> Option<Vec<u8>> {
        match self.subs.get(&req_id) {
            Some(s) if s.phase.occupies_line() => {
                self.subs.remove(&req_id);
                Some(encode_cancel_mkt_data(req_id))
            }
            _ => None,
        }
    }

    /// **W6-S4 provenance 錨補綁**:begin 訂閱時該 conId 的 W6-S1 identity row 可能尚未到達
    ///（contract details 與 market data 為獨立請求 lane,同 serve tick 併發送出,回報有先後）——
    /// 此時 provenance 溯源錨標未綁。driver 於 identity row 到達後以本方法補綁**尚未綁定**的
    /// 活躍訂閱。兩錨獨立補綁（row 在但日曆不可解時,identity_hash 可綁而 calendar 仍未綁）:
    /// - `instrument_identity_hash`:begin 時 row 未到=空;row 到達即補真值。
    /// - `calendar_hash`:begin 時=未綁哨兵;日曆解析成功即補真值,失敗仍留哨兵。
    /// 皆 bind-once（已綁定者不動,避免 PIT 溯源錨漂移;仍未綁則不動,絕不以未綁覆真值、不捏值）。
    pub(crate) fn rebind_provenance_anchors_if_unbound(
        &mut self,
        req_id: i64,
        instrument_identity_hash: String,
        calendar_hash: String,
    ) {
        if let Some(sub) = self.subs.get_mut(&req_id) {
            if !sub.phase.occupies_line() {
                return;
            }
            // identity_hash:空=未綁 → row 到達的真值補綁（已綁不動）。
            if sub.instrument_identity_hash.is_empty() && !instrument_identity_hash.is_empty() {
                sub.instrument_identity_hash = instrument_identity_hash;
            }
            // calendar_hash:哨兵=未綁 → 真值補綁（仍為哨兵則不動,不以未綁覆未綁）。
            if sub.calendar_hash == IBKR_CALENDAR_HASH_UNBOUND_SENTINEL
                && calendar_hash != IBKR_CALENDAR_HASH_UNBOUND_SENTINEL
            {
                sub.calendar_hash = calendar_hash;
            }
        }
    }

    /// **snapshot 終態 typed 化**（非懸掛）:snapshot 訂閱逾 config 終態窗無 TICK_SNAPSHOT_END
    /// → 標 `SnapshotComplete`（釋放 line）+ audit 落帳,回逾時清單。為什麼 Complete 而非
    /// 毒化:snapshot 11s 後 server 本就自動取消,END 缺席是時間性收尾非資料完整性失敗;值
    /// 保留供唯讀檢視。
    pub(crate) fn expire_overdue(&mut self, now_ms: u64) -> Vec<SnapshotTerminal> {
        let window_ms = self.config.snapshot_terminal_after.as_millis() as u64;
        let mut out = Vec::new();
        for (req_id, sub) in self.subs.iter_mut() {
            if sub.phase == SubPhase::SnapshotPending
                && now_ms.saturating_sub(sub.started_at_ms) > window_ms
            {
                sub.phase = SubPhase::SnapshotComplete;
                out.push(SnapshotTerminal {
                    req_id: *req_id,
                    started_at_ms: sub.started_at_ms,
                    terminated_at_ms: now_ms,
                });
            }
        }
        self.audit.snapshot_terminals += out.len() as u64;
        out
    }

    // ---- 入站消化（payload = 已 unframe 的欄位序,含 msgId 欄）----

    /// TICK_PRICE(1):`[1, version(棄), reqId, tickType, price, size, attrMask]`（嚴格 7 欄）。
    /// 只 materialize **price** 邊（BID/ASK/LAST）;內嵌 size = client 合成 tickSize → **抑制**
    /// （單源記帳:size 唯認 TICK_SIZE(2),禁雙記——S3a 合成去重紅線）。
    pub(crate) fn on_tick_price_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), MarketDataReject> {
        let r = self.tick_price_inner(payload, now_ms);
        if let Err(e) = &r {
            self.audit_reject(e);
        }
        r
    }

    fn tick_price_inner(&mut self, payload: &[u8], now_ms: u64) -> Result<(), MarketDataReject> {
        let fields = decode_fields(payload).map_err(MarketDataReject::WireMalformed)?;
        if fields.len() != 7 {
            return Err(MarketDataReject::WireMalformed(CodecError::Malformed(
                "tick price needs exactly 7 fields",
            )));
        }
        expect_msg_id(&fields[0], IN_TICK_PRICE_MSG_ID)?;
        let req_id = parse_i64(&fields[2], "tick_price_req_id")?;
        let tick_type_id = parse_i64(&fields[3], "tick_price_type")?;
        let price_wire = fields[4].clone();
        // size 欄嚴格驗形（合成 tickSize 來源;非數字=wire 損壞,不猜）——但**不 materialize**。
        let _synth_size = parse_i64(&fields[5], "tick_price_size")?;
        // attrMask 讀位即棄（canAutoExecute/pastLimit/preOpen bits;L1 quote 面不承）。
        let _attr = parse_i64(&fields[6], "tick_price_attr")?;
        self.audit.synth_size_suppressed += 1;
        self.apply_quote_tick(
            req_id,
            tick_type_id,
            IbkrTickValueKind::Price,
            &price_wire,
            now_ms,
        )
    }

    /// TICK_SIZE(2):**嚴格 5 欄** `[2, version, reqId, tickType, size]`（IB signature 訊息,
    /// 按位不容錯位）。materialize size 邊（BID_SIZE/ASK_SIZE/LAST_SIZE;0=無掛單合法）。
    pub(crate) fn on_tick_size_frame(
        &mut self,
        payload: &[u8],
        now_ms: u64,
    ) -> Result<(), MarketDataReject> {
        let r = self.tick_size_inner(payload, now_ms);
        if let Err(e) = &r {
            self.audit_reject(e);
        }
        r
    }

    fn tick_size_inner(&mut self, payload: &[u8], now_ms: u64) -> Result<(), MarketDataReject> {
        let fields = decode_fields(payload).map_err(MarketDataReject::WireMalformed)?;
        if fields.len() != 5 {
            return Err(MarketDataReject::WireMalformed(CodecError::Malformed(
                "tick size needs exactly 5 fields",
            )));
        }
        expect_msg_id(&fields[0], IN_TICK_SIZE_MSG_ID)?;
        let req_id = parse_i64(&fields[2], "tick_size_req_id")?;
        let tick_type_id = parse_i64(&fields[3], "tick_size_type")?;
        let size_wire = fields[4].clone();
        self.apply_quote_tick(
            req_id,
            tick_type_id,
            IbkrTickValueKind::Size,
            &size_wire,
            now_ms,
        )
    }

    /// TICK_GENERIC(45) / TICK_STRING(46):L1 lane 不承（halted/last-timestamp/option greeks
    /// 等）→ **typed-ignore**（驗 msgId+reqId 身分後記帳丟棄,不消化、不 unknown-fail——
    /// unknown-fail 會把良性 tick 升格為 transport 事件,同 W6-S1 bond typed-ignore 慣例）。
    pub(crate) fn on_tick_generic_frame(&mut self, payload: &[u8]) -> Result<(), MarketDataReject> {
        let r = self.tick_aux_inner(payload, IN_TICK_GENERIC_MSG_ID);
        match &r {
            Ok(()) => self.audit.generic_tick_ignored += 1,
            Err(e) => self.audit_reject(e),
        }
        r
    }

    pub(crate) fn on_tick_string_frame(&mut self, payload: &[u8]) -> Result<(), MarketDataReject> {
        let r = self.tick_aux_inner(payload, IN_TICK_STRING_MSG_ID);
        match &r {
            Ok(()) => self.audit.string_tick_ignored += 1,
            Err(e) => self.audit_reject(e),
        }
        r
    }

    /// generic/string 的共用驗形:`[msgId, version, reqId, tickType, value]`（≥5 欄;value
    /// 型別不 bind）。只驗身分,不 materialize。
    fn tick_aux_inner(&mut self, payload: &[u8], msg_id: i64) -> Result<(), MarketDataReject> {
        let fields = decode_fields(payload).map_err(MarketDataReject::WireMalformed)?;
        if fields.len() < 5 {
            return Err(MarketDataReject::WireMalformed(CodecError::Malformed(
                "aux tick needs >=5 fields",
            )));
        }
        expect_msg_id(&fields[0], msg_id)?;
        let _req_id = parse_i64(&fields[2], "aux_tick_req_id")?;
        Ok(())
    }

    /// TICK_REQ_PARAMS(81):**無 version 欄** `[81, tickerId, minTick, bboExchange,
    /// snapshotPermissions]`（IB 現勘 pinned）→ typed-ignore（v1 不承 minTick/bbo/permissions;
    /// 記帳丟棄）。驗 msgId + tickerId 身分即棄。
    pub(crate) fn on_tick_req_params_frame(
        &mut self,
        payload: &[u8],
    ) -> Result<(), MarketDataReject> {
        let r = self.tick_req_params_inner(payload);
        match &r {
            Ok(()) => self.audit.tick_req_params_ignored += 1,
            Err(e) => self.audit_reject(e),
        }
        r
    }

    fn tick_req_params_inner(&mut self, payload: &[u8]) -> Result<(), MarketDataReject> {
        let fields = decode_fields(payload).map_err(MarketDataReject::WireMalformed)?;
        // 無 version:5 欄 [msgId, tickerId, minTick, bboExchange, snapshotPermissions]。
        if fields.len() != 5 {
            return Err(MarketDataReject::WireMalformed(CodecError::Malformed(
                "tick req params needs exactly 5 fields (no version)",
            )));
        }
        expect_msg_id(&fields[0], IN_TICK_REQ_PARAMS_MSG_ID)?;
        let _ticker_id = parse_i64(&fields[1], "tick_req_params_ticker_id")?;
        Ok(())
    }

    /// TICK_SNAPSHOT_END(57):`[57, version, reqId]`（snapshot 收批;IB 於 11s 後送並自動取消
    /// 訂閱）→ 標 `SnapshotComplete`（釋放 line）。非 snapshot 訂閱收到=協議意外,typed-ignore
    /// 不轉相位（audit 未訂而收語義較重,此處寬容忽略——END 對 streaming 無害）。
    pub(crate) fn on_tick_snapshot_end_frame(
        &mut self,
        payload: &[u8],
    ) -> Result<(), MarketDataReject> {
        let r = self.tick_snapshot_end_inner(payload);
        if let Err(e) = &r {
            self.audit_reject(e);
        }
        r
    }

    fn tick_snapshot_end_inner(&mut self, payload: &[u8]) -> Result<(), MarketDataReject> {
        let fields = decode_fields(payload).map_err(MarketDataReject::WireMalformed)?;
        if fields.len() != 3 {
            return Err(MarketDataReject::WireMalformed(CodecError::Malformed(
                "tick snapshot end needs exactly 3 fields",
            )));
        }
        expect_msg_id(&fields[0], IN_TICK_SNAPSHOT_END_MSG_ID)?;
        let req_id = parse_i64(&fields[2], "tick_snapshot_end_req_id")?;
        match self.subs.get_mut(&req_id) {
            Some(s) if s.phase == SubPhase::SnapshotPending => {
                s.phase = SubPhase::SnapshotComplete;
                Ok(())
            }
            Some(_) => Ok(()), // streaming/終態:END 無害,忽略
            None => {
                self.audit.no_active_subscription_rejects += 1;
                Err(MarketDataReject::NoActiveSubscription { req_id })
            }
        }
    }

    /// MARKET_DATA_TYPE(58):`[58, version(棄), reqId, marketDataType]`——**per-reqId 綁定
    /// 非全局**（IB 現勘）。1|2=live/frozen → Entitled;3|4=delayed/delayed-frozen → Delayed;
    /// 其餘 → NoneHalt（fail-closed）。Pending→已判態;已 halt 則不覆寫（終態優先）。
    pub(crate) fn on_market_data_type_frame(
        &mut self,
        payload: &[u8],
    ) -> Result<(), MarketDataReject> {
        let r = self.market_data_type_inner(payload);
        if let Err(e) = &r {
            self.audit_reject(e);
        }
        r
    }

    fn market_data_type_inner(&mut self, payload: &[u8]) -> Result<(), MarketDataReject> {
        let fields = decode_fields(payload).map_err(MarketDataReject::WireMalformed)?;
        if fields.len() != 4 {
            return Err(MarketDataReject::WireMalformed(CodecError::Malformed(
                "market data type needs exactly 4 fields",
            )));
        }
        expect_msg_id(&fields[0], IN_MARKET_DATA_TYPE_MSG_ID)?;
        let req_id = parse_i64(&fields[2], "market_data_type_req_id")?;
        let mdt = parse_i64(&fields[3], "market_data_type_value")?;
        let sub = match self.subs.get_mut(&req_id) {
            Some(s) => s,
            None => {
                self.audit.no_active_subscription_rejects += 1;
                return Err(MarketDataReject::NoActiveSubscription { req_id });
            }
        };
        // halt 態=世代內終態,MARKET_DATA_TYPE 不復活。
        if matches!(sub.phase, SubPhase::Halted | SubPhase::Invalidated) {
            return Ok(());
        }
        sub.entitlement = match mdt {
            1 | 2 => ReqEntitlement::Entitled,
            3 | 4 => ReqEntitlement::Delayed,
            _ => ReqEntitlement::NoneHalt, // 未知檔位 → fail-closed
        };
        if sub.entitlement == ReqEntitlement::NoneHalt {
            sub.phase = SubPhase::Halted;
        }
        self.audit.market_data_type_bindings += 1;
        Ok(())
    }

    /// **per-reqId entitlement 錯誤碼 FSM**（driver 於 ERR_MSG(4) 依 reqId 路由至此;IB
    /// 現勘碼映射見 support）。354/10186/10190→None halt;10167→(opt-in?Delayed:退訂);
    /// 10197→CompetingSession halt;10090→Partial（窗續);未知→fail-closed 退訂。
    pub(crate) fn on_entitlement_error(&mut self, req_id: i64, code: i64) {
        self.audit.entitlement_last_code = Some(code);
        let outcome = classify_entitlement_error(code, self.delayed_opt_in);
        let sub = match self.subs.get_mut(&req_id) {
            Some(s) => s,
            None => {
                self.audit.no_active_subscription_rejects += 1;
                return;
            }
        };
        match outcome {
            EntitlementErrorOutcome::None => {
                sub.entitlement = ReqEntitlement::NoneHalt;
                sub.phase = SubPhase::Halted;
                self.audit.entitlement_none_rejects += 1;
            }
            EntitlementErrorOutcome::Delayed => {
                sub.entitlement = ReqEntitlement::Delayed;
                self.audit.entitlement_delayed_confirmed += 1;
            }
            EntitlementErrorOutcome::DelayedWithoutOptIn => {
                // 未 opt-in 卻收 delayed 確認=協議意外 → fail-closed 退訂（不 materialize delayed
                // 值於未請求降級的窗）。
                sub.entitlement = ReqEntitlement::NoneHalt;
                sub.phase = SubPhase::Halted;
                self.audit.entitlement_delayed_without_optin += 1;
            }
            EntitlementErrorOutcome::CompetingSession => {
                sub.entitlement = ReqEntitlement::CompetingHalt;
                sub.phase = SubPhase::Halted;
                self.audit.entitlement_competing_session += 1;
            }
            EntitlementErrorOutcome::Partial => {
                // 部分欄未訂;窗續存,entitlement 不變（已有值的欄仍 materialize）。
                self.audit.entitlement_partial += 1;
            }
            EntitlementErrorOutcome::Unknown => {
                sub.phase = SubPhase::Halted;
                self.audit.entitlement_unknown_code_halts += 1;
            }
        }
    }

    /// price/size tick 併入共用路徑:未訂而收拒 → tickType 白名單 → entitlement 態調和
    /// （Pending 升格 / halt 抑制 / 衝突抑制）→ no-data 抑制 → 契約 validate → 併入。
    fn apply_quote_tick(
        &mut self,
        req_id: i64,
        tick_type_id: i64,
        expected_kind: IbkrTickValueKind,
        value_wire: &str,
        now_ms: u64,
    ) -> Result<(), MarketDataReject> {
        let sub = match self.subs.get_mut(&req_id) {
            Some(s) => s,
            None => {
                self.audit.no_active_subscription_rejects += 1;
                return Err(MarketDataReject::NoActiveSubscription { req_id });
            }
        };
        let tick_type = IbkrTickTypeV1::classify_wire_tick_type(tick_type_id);
        // 表外 tickType（HIGH/VOLUME/greeks…）→ typed-ignore（L1 lane 不承）。
        let (Some(field), Some(tick_ent), Some(kind)) = (
            tick_type.logical_field(),
            tick_type.entitlement(),
            tick_type.value_kind(),
        ) else {
            self.audit.unknown_tick_type_ignored += 1;
            return Ok(());
        };
        // TICK_PRICE 只承 price 邊、TICK_SIZE 只承 size 邊——kind 錯配=協議意外,typed-ignore。
        if kind != expected_kind {
            self.audit.unknown_tick_type_ignored += 1;
            return Ok(());
        }
        // entitlement 態調和（IB-NOTE-3 詞彙:tick `Realtime` ↔ provenance `Entitled`）。
        let tick_state = match tick_ent {
            IbkrTickEntitlementV1::Realtime => ReqEntitlement::Entitled,
            IbkrTickEntitlementV1::Delayed => ReqEntitlement::Delayed,
        };
        match sub.entitlement {
            ReqEntitlement::Pending => sub.entitlement = tick_state, // 首 tick 判態
            ReqEntitlement::NoneHalt | ReqEntitlement::CompetingHalt => {
                self.audit.tick_after_halt_suppressed += 1;
                return Ok(());
            }
            existing if existing != tick_state => {
                // state=Delayed 卻收 realtime tick（或反）=entitlement 窗謊言風險 → 抑制。
                self.audit.entitlement_tick_conflict += 1;
                return Ok(());
            }
            _ => {}
        }
        // no-data 抑制（price=-1 / 量級哨兵 / 空欄;size=-1 → 不 materialize）。
        let value_decimal = match sanitize_tick_value(value_wire, kind) {
            Some(v) => v,
            None => {
                self.audit.no_data_suppressed += 1;
                return Ok(());
            }
        };
        self.seq_counter += 1;
        let row = IbkrQuoteRowV1 {
            contract_id: IBKR_QUOTE_ROW_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: openclaw_types::AssetLane::StockEtfCash,
            broker: openclaw_types::Broker::Ibkr,
            con_id: sub.con_id,
            symbol: sub.symbol.clone(),
            req_id,
            tick_type,
            value_decimal,
            // delayed tick 必攜 Delayed（契約 validate 兜底 EntitlementProvenanceMismatch）。
            entitlement: tick_ent,
            captured_at_ms: now_ms,
            seq: self.seq_counter,
            order_routed: false,
            secret_content_serialized: false,
        };
        if !row.validate(now_ms).accepted {
            // 契約兜底（sanitize 前置後理應不達;達=fail-closed 抑制+audit,不併入謊言值）。
            self.audit.quote_row_blocked_rejects += 1;
            return Err(MarketDataReject::QuoteRowBlocked);
        }
        if sub.first_tick_at_ms == 0 {
            sub.first_tick_at_ms = now_ms;
        }
        sub.last_tick_at_ms = now_ms;
        sub.quotes.insert(field_key(field), row);
        self.audit.ticks_applied += 1;
        Ok(())
    }

    // ---- 生命週期:斷線 / 世代推進（沿 W6-S0 慣例）----

    /// 斷線:活躍訂閱標 `DisconnectedStale`（訂閱不跨連線存活——重連需重訂閱;行保留供唯讀
    /// 檢視,staleness 已明示不可信）。終態（Halted/Invalidated/Complete）維持原相位。
    pub(crate) fn on_disconnect(&mut self) {
        for sub in self.subs.values_mut() {
            if sub.phase.occupies_line() {
                sub.phase = SubPhase::DisconnectedStale;
            }
        }
        // delayed opt-in 不跨連線存活（新 session 須重送 reqMarketDataType(3)）。
        self.delayed_opt_in = false;
    }

    /// **W6-S0 恢復政策**:driver 世代推進（新 handshake 成功）時重評終態面——Halted/
    /// Invalidated → DisconnectedStale,與「斷線→DisconnectedStale→re-begin」語義合流。
    /// 行保留供唯讀對賬;audit 計數跨世代累積（telemetry 語義,不清零）。
    pub(crate) fn on_new_connection_generation(&mut self) {
        for sub in self.subs.values_mut() {
            if matches!(sub.phase, SubPhase::Halted | SubPhase::Invalidated) {
                sub.phase = SubPhase::DisconnectedStale;
            }
        }
    }

    // ---- 觀測（typed staleness 綁定視圖 + provenance + audit;沿 W6-S0 慣例）----

    /// 是否有此 reqId 的訂閱（driver 路由 ERR_MSG entitlement 碼前的守衛:session 級
    /// ERR_MSG（reqId=-1）不路由至本面）。
    pub(crate) fn contains_subscription(&self, req_id: i64) -> bool {
        self.subs.contains_key(&req_id)
    }

    /// 當前佔 line 的活躍訂閱數（count semaphore 觀測面）。
    pub(crate) fn lines_in_use(&self) -> usize {
        self.subs
            .values()
            .filter(|s| s.phase.occupies_line())
            .count()
    }

    /// per-reqId quote staleness（typed 六態）。無此 reqId → `None`。
    pub(crate) fn quote_staleness(&self, req_id: i64, now_ms: u64) -> Option<SnapshotStaleness> {
        self.subs.get(&req_id).map(|s| self.staleness_of(s, now_ms))
    }

    fn staleness_of(&self, sub: &Subscription, now_ms: u64) -> SnapshotStaleness {
        match sub.phase {
            SubPhase::SnapshotPending => SnapshotStaleness::SnapshotIncomplete,
            SubPhase::Halted | SubPhase::Invalidated => SnapshotStaleness::Invalidated,
            SubPhase::DisconnectedStale => SnapshotStaleness::DisconnectedStale,
            SubPhase::Streaming | SubPhase::SnapshotComplete => {
                if sub.last_tick_at_ms == 0 {
                    // 訂閱中但尚無 tick=未完整（禁把空窗當新鮮消費）。
                    SnapshotStaleness::SnapshotIncomplete
                } else {
                    let age_ms = now_ms.saturating_sub(sub.last_tick_at_ms);
                    if age_ms > self.config.quote_stale_after.as_millis() as u64 {
                        SnapshotStaleness::Stale {
                            as_of_ms: sub.last_tick_at_ms,
                            age_ms,
                        }
                    } else {
                        SnapshotStaleness::Fresh {
                            as_of_ms: sub.last_tick_at_ms,
                        }
                    }
                }
            }
        }
    }

    /// 唯讀檢視:per-reqId quote 面 **staleness 綁定視圖**（W6-S0 慣例）——rows 只能與其
    /// staleness 一同取得,使「部分/毒化/斷線快照被當全量消費」**結構性不可能**（BTreeMap=
    /// 確定序,鍵=logical field）。無此 reqId → `None`。
    pub(crate) fn quotes(
        &self,
        req_id: i64,
        now_ms: u64,
    ) -> Option<(SnapshotStaleness, impl Iterator<Item = &IbkrQuoteRowV1>)> {
        self.subs
            .get(&req_id)
            .map(|s| (self.staleness_of(s, now_ms), s.quotes.values()))
    }

    /// per-reqId provenance 鑄造（消化層 sha256 over preimage;PIT 可重建）。entitlement 態
    /// 由 FSM 誠實投影（Pending→UnknownDenied,窗未成形即契約 blocker）;窗時戳由 tick 累積。
    /// 無此 reqId → `None`。呼叫端以 `validate(now_ms)` 兜底 shape。
    pub(crate) fn provenance(&self, req_id: i64) -> Option<IbkrMarketDataProvenanceV1> {
        let sub = self.subs.get(&req_id)?;
        let mut prov = IbkrMarketDataProvenanceV1 {
            contract_id: IBKR_MARKET_DATA_PROVENANCE_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: openclaw_types::AssetLane::StockEtfCash,
            broker: openclaw_types::Broker::Ibkr,
            con_id: sub.con_id,
            symbol: sub.symbol.clone(),
            req_id,
            entitlement_state: sub.entitlement.provenance_state(),
            // L1 realtime/delayed tick 恆未調整（split/div 調整歸歷史面,本 lane 不承）。
            adjustment: IbkrPriceAdjustmentV1::Raw,
            first_tick_at_ms: sub.first_tick_at_ms,
            last_tick_at_ms: sub.last_tick_at_ms,
            instrument_identity_hash: sub.instrument_identity_hash.clone(),
            calendar_hash: sub.calendar_hash.clone(),
            provenance_hash: String::new(),
            order_routed: false,
            secret_content_serialized: false,
        };
        prov.provenance_hash = compute_provenance_hash(&prov);
        Some(prov)
    }

    /// audit 計數器唯讀檢視。
    pub(crate) fn audit(&self) -> &MarketDataAudit {
        &self.audit
    }

    /// 當前 delayed opt-in flag（telemetry;driver pump 據此判是否已 send-before-subscribe）。
    pub(crate) fn delayed_opt_in(&self) -> bool {
        self.delayed_opt_in
    }

    // ---- 內部 ----

    /// 入站 typed reject → audit 身分落帳（單調計數+最後樣本;沿 W6-S0 慣例——driver 對資料層
    /// reject 走 `Err(_)=>{}` 續 serve,身分由此觀測面承載）。已在拒點就地計數者此處只補
    /// wire 損壞面（其餘已於拒點計數,防重複)。
    fn audit_reject(&mut self, e: &MarketDataReject) {
        if let MarketDataReject::WireMalformed(c) = e {
            self.audit.wire_malformed_rejects += 1;
            self.audit.wire_malformed_last_note = Some(c.to_string());
        }
    }
}

#[cfg(test)]
#[path = "ibkr_tws_market_data_tests.rs"]
mod tests;
