//! Intent Processor — H0 → Guardian → CostGate → Governance → OMS (R04-2).
//! 意圖處理器 — H0 → 守護者 → 成本門 → 治理 → OMS。
//!
//! MODULE_NOTE (EN): Processes trade intents through the governance pipeline:
//!   H0 gate → Guardian risk check → CostGate EV filter → Kelly sizing → OMS.
//!   Holds RiskConfig snapshot for per-tick limit enforcement.
//! MODULE_NOTE (中): 通過治理管線處理交易意圖：H0 門控 → Guardian 風控 →
//!   CostGate EV 過濾 → Kelly 倉位 → OMS。持有 RiskConfig 快照用於逐 tick 限制。

mod earn_router;
mod gates;
mod reject_reason_code;
mod rejection_coding;
mod router;
#[cfg(test)]
mod tests;

use reject_reason_code::map_reject_reason_to_code;
use rejection_coding::RejectionCode;

use crate::config::risk_config::EdgePredictorFallback;
use crate::config::RiskConfig;
use crate::edge_predictor::{
    features::FeatureVectorV1,
    gate::{
        edge_predictor_gate, FallbackReason, GateInputs, PredictorGateOutcome, ShadowFillPayload,
    },
    EdgePredictorStore,
};
use crate::risk_checks::check_order_allowed;
use crate::tick_pipeline::{PipelineCommand, PipelineKind};
use openclaw_core::{
    execution::{self, FillResult},
    // AMD-2026-05-02-01 Track E E-1: also re-export LeaseId / LeaseOutcome /
    // GovernanceError so router (E-2) and tests reach them via super::*.
    // AMD-2026-05-02-01 Track E E-1：同時 re-export LeaseId / LeaseOutcome /
    // GovernanceError，讓 router（E-2）與 tests 透過 super::* 取用。
    governance_core::{GovernanceCore, GovernanceError, GovernanceProfile, LeaseId, LeaseOutcome},
    guardian::{ExistingPosition, Guardian, PortfolioContext, TradeIntentCheck, Verdict},
};
use parking_lot::Mutex;
use rand::{rngs::SmallRng, SeedableRng};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::mpsc::UnboundedSender;

use crate::paper_state::PaperState;

/// Sprint 1B Earn first stake — IntentType 強型別 enum（7 variant）。
///
/// 設計依據:
///   - earn_governance_spec §3.1 + PA dispatch packet 2026-05-23 §2 設計;
///   - OP-4 path: CC 並行修 spec 加 PositionAdjust → 本 enum 同步含 7 variant;
///   - 既有 trading hot-path 透過 `is_long: bool` 隱性區分 long/short;新 enum
///     讓 IntentProcessor 入口可 dispatch trading vs Earn 分支(下游 Wave 接);
///   - serde rename_all = "snake_case" 對齊 IPC JSON 慣例; Default = OpenLong
///     保持既有 trading intent (4 策略 + IPC consumer) 反序列化路徑零行為差;
///   - `is_earn()` 給 IntentProcessor.process() 用以分支 (Earn 走 bybit_earn_client
///     + earn_movement_log writer; 非 Earn 走既有 trade path)。
///
/// E1b 接力說明(LeaseScope variant 擴展):
///   本 IMPL 暫不引入 `to_lease_scope()` returning enum; LeaseScope::EarnStake /
///   EarnRedeem 兩 variant 屬 E1b 工作(rust/openclaw_core/src/lease_scope.rs)。
///   E1b land 後 PR 應在此補:
///     pub fn to_lease_scope(self) -> openclaw_core::lease_scope::LeaseScope
///   並把 router.rs line 100 字面 "TRADE_ENTRY" 改為 enum-driven。
///   本 IMPL 提供 `to_lease_scope_audit_str()` 字串映射作為 forward-compatible 占位,
///   下游可先用字串比對直到 enum 就緒。
///
/// SAFETY 不變量:
///   - 新 variant 必須在 IntentType.to_lease_scope_audit_str() exhaustive match 同步補映射;
///   - serde rename_all 後字串格式為 "open_long" / "earn_stake" 等 (snake_case);
///   - Default = OpenLong: backward-compat IPC payload 不帶 intent_type 時自動回退。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IntentType {
    /// 真實開多 — Trading entry path(既有 is_long=true 路徑;serde default)。
    OpenLong,
    /// 真實開空 — Trading entry path(既有 is_long=false 路徑)。
    OpenShort,
    /// 真實平多 — Sprint 5+ position state machine 重構後啟用(預留)。
    CloseLong,
    /// 真實平空 — Sprint 5+ 預留。
    CloseShort,
    /// 倉位調整 — Strategist 重新 risk-scaled 動作(PA OP-4 path: CC 修 spec 加;
    /// LeaseScope::PositionAdjust 既存 variant 對齊)。
    PositionAdjust,
    /// Bybit Earn flexible/fixed stake 操作 — earn_governance §3.1 新增。
    /// amount + product_id + apr + tenor 等 Earn-specific field 走
    /// EarnIntentPayload (per OrderIntent.earn_payload field)。
    EarnStake,
    /// Bybit Earn flexible/fixed redeem 操作 — earn_governance §3.1 新增。
    /// 含提前贖回(fixed) + flexible 即時贖回兩種 sub-mode。
    EarnRedeem,
}

impl Default for IntentType {
    /// serde 反序列化 + 結構字面值 backward-compat 共用預設值。
    /// 既有 trading IPC payload 不含 intent_type 時自動視為 OpenLong;
    /// 非 OpenLong 場景(OpenShort/Earn) caller 必須顯式填。
    fn default() -> Self {
        Self::OpenLong
    }
}

impl IntentType {
    /// Sprint 1B Earn first stake — 是否為 Earn 路徑。
    /// 用於 IntentProcessor.process() 內部 dispatch:
    ///   true  → 走 bybit_earn_client + earn_movement_log writer(下游 Wave E1c/E1d);
    ///   false → 走既有 trade path(IntentProcessor.execute_trade + bybit_rest_client)。
    pub fn is_earn(self) -> bool {
        matches!(self, Self::EarnStake | Self::EarnRedeem)
    }

    /// 字串映射占位(forward-compat;E1b LeaseScope variant 落地後升級為 enum return)。
    ///
    /// 對齊 PA dispatch packet §3.2 line 320-330 LeaseScope::as_audit_str() 預期值:
    ///   OpenLong/OpenShort  → "TRADE_ENTRY"
    ///   CloseLong/CloseShort → "TRADE_EXIT"
    ///   PositionAdjust       → "POSITION_ADJUST"
    ///   EarnStake            → "EARN_STAKE"
    ///   EarnRedeem           → "EARN_REDEEM"
    ///
    /// 新 variant 必須在此 exhaustive match 同步補(編譯期強制)。
    pub fn to_lease_scope_audit_str(self) -> &'static str {
        match self {
            Self::OpenLong | Self::OpenShort => "TRADE_ENTRY",
            Self::CloseLong | Self::CloseShort => "TRADE_EXIT",
            Self::PositionAdjust => "POSITION_ADJUST",
            Self::EarnStake => "EARN_STAKE",
            Self::EarnRedeem => "EARN_REDEEM",
        }
    }
}

/// Sprint 1B Earn first stake — Earn-specific intent payload。
///
/// 設計依據:
///   - earn_governance §3.2 + V100 earn_movement_log schema 對映;
///   - amount_usdt 用 String 載荷(非 Decimal): Bybit V5 API 原生回字串;
///     避免引入 rust_decimal 新依賴(本 IMPL 範圍外); 下游 writer 可自行
///     `.parse::<f64>()` 或 `.parse::<Decimal>()` (見 PA dispatch §11 push back);
///   - product_id + tenor_days 對映 Bybit V5 Earn API param(flexible product_id /
///     fixed product_id + tenor_days);
///   - approval_id 對映 authorization.json UUID 字串
///     (CLAUDE.md §四 5-gate Gate b authz_id);
///   - actor_id: Operator role 字串(Gate a actor_id;
///     例如 "PrimaryOperator" / "BackupOperator");
///   - rationale: GUI 提交時的說明文字(audit forensic)。
///
/// SAFETY 不變量:
///   - 此 struct 僅在 OrderIntent.earn_payload = Some(...) 時被使用;
///   - serde default 路徑保留 IPC backward-compat (既有 trading payload 不含此 field);
///   - Bybit V5 Earn API 對 amount 字串期望小數點數字(例 "200.00000000"); 寫入端
///     必須先 sanitize / validate(下游 IMPL Wave E1c 職責);
///   - approval_id 與 governance_audit_log.id 是 soft ref(PA-DRIFT-6 lesson)。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EarnIntentPayload {
    /// stake / redeem 金額 USDT 字串(Bybit V5 API 原生格式;對映 V100
    /// earn_movement_log.amount_usdt NUMERIC(18,8))。
    pub amount_usdt: String,
    /// 預期 APR basis points(stake 必填;redeem 可填可不填)。
    /// 對映 V100 earn_movement_log.apr_at_time REAL(writer 將 bps → REAL 轉換)。
    pub expected_apr_bps: i32,
    /// Bybit product_id(flexible product_id 或 fixed product_id;
    /// 查 E-1 getFlexibleProductList / E-6 getFixedProductList 返回值)。
    pub product_id: String,
    /// fixed staking tenor 天數(90 / 180);flexible 對應值由 caller 約定。
    pub tenor_days: u32,
    /// authorization.json UUID 字串
    /// (Gate b cross-ref;對映 governance_audit_log.id soft ref)。
    pub approval_id: String,
    /// Operator role 字串(Gate a actor_id;
    /// 例 "PrimaryOperator" / "BackupOperator")。
    pub actor_id: String,
    /// GUI 提交時的說明文字
    /// (audit forensic;Sprint 1B Earn first stake operator 必填)。
    pub rationale: String,
}

/// A trade intent from a strategy.
/// 來自策略的交易意圖。
///
/// EDGE-P3-1 A6: `confluence_score` / `persistence_elapsed_ms` are plumbed from
/// strategies that compute them (MA/BBR/BBB) into `feature_builder::build_feature_vector`
/// for the predictor gate. `None` means the strategy does not compute that feature
/// (Grid, FundingArb) — builder fills with 0.0 and the zero-default stays benign
/// behind `use_edge_predictor=false`. `#[serde(default)]` keeps cross-version IPC
/// deserialization working if a producer omits these keys.
/// EDGE-P3-1 A6：`confluence_score` / `persistence_elapsed_ms` 由 MA/BBR/BBB 策略
/// 塞入，供 feature_builder 讀取；Grid/FundingArb 填 `None` 由 builder 補 0。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderIntent {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub confidence: f64,
    pub strategy: String,
    pub order_type: String, // "market" or "limit"
    pub limit_price: Option<f64>,
    /// Confluence score in [0, 65] at intent time; None when strategy has no
    /// confluence scoring (Grid / FundingArb). Fed to feature slot #9.
    #[serde(default)]
    pub confluence_score: Option<f32>,
    /// Milliseconds since signal onset (PersistenceTracker state), capped by
    /// caller to feature range [0, 3_600_000]; None when strategy has no
    /// persistence tracker. Fed to feature slot #10.
    #[serde(default)]
    pub persistence_elapsed_ms: Option<u64>,
    /// EDGE-P2-3 Phase 1a: optional TimeInForce for maker/limit orders.
    /// `None` means default (Market → no TIF; Limit → GTC at dispatch).
    /// Set to `Some(TimeInForce::PostOnly)` for maker-only entries.
    /// EDGE-P2-3 Phase 1a：maker/limit 可選 TIF。None 保留現行預設行為
    /// （Market 不帶 TIF；Limit 於派發層預設 GTC）。Maker-only 入場設 Some(PostOnly)。
    #[serde(default)]
    pub time_in_force: Option<crate::order_manager::TimeInForce>,
    /// EDGE-P2-3 Phase 1B-3.2: per-order maker-resting timeout (ms). Only
    /// populated when `time_in_force == Some(PostOnly)`. `None` means the
    /// event consumer falls back to its default (no special sweep). Caller
    /// MUST pass the strategy-configured value (already clamped by the
    /// factory to `[MAKER_LIMIT_TIMEOUT_MIN_MS, MAKER_LIMIT_TIMEOUT_MAX_MS]`).
    /// EDGE-P2-3 Phase 1B-3.2：每單 maker 掛單逾時（毫秒），僅在 PostOnly 時填。
    /// None → 消費端走預設行為（不特別 sweep）。呼叫方必須傳入策略配置值
    /// （已於工廠 clamp 到 [15s, 300s]）。
    #[serde(default)]
    pub maker_timeout_ms: Option<u64>,
    /// Sprint 1B Earn first stake — IntentType 強型別。
    ///
    /// 既有 trading intent ⇒ OpenLong (default;對齊既有 is_long=true 路徑) /
    /// OpenShort (caller 顯式填;對齊 is_long=false 路徑)
    /// Earn intent ⇒ EarnStake / EarnRedeem (走 bybit_earn_client + writer 下游 Wave)
    /// 倉位調整 ⇒ PositionAdjust (預留;LeaseScope::PositionAdjust 對齊)
    /// 平倉 ⇒ CloseLong / CloseShort (預留;Sprint 5+)
    ///
    /// serde default = OpenLong: 既有 IPC payload 不含此 field 時自動回退,
    /// 既有 32 個 OrderIntent struct literal callers 顯式填 OpenLong 對齊
    /// 既有行為(0 行為差;E2 review 重點 #2)。
    #[serde(default)]
    pub intent_type: IntentType,
    /// Sprint 1B Earn first stake — Earn-specific payload (per EarnIntentPayload schema)。
    ///
    /// trading intent ⇒ None (既有路徑;不變)
    /// Earn intent ⇒ Some(EarnIntentPayload {...}) (caller 必填 7 field)
    ///
    /// 不違反既有 trading hot-path: None 短路;下游 Earn writer Wave 才會讀。
    #[serde(default)]
    pub earn_payload: Option<EarnIntentPayload>,
}

impl OrderIntent {
    /// Sprint 1B audit Bug 2 fix（IntentType HYBRID-PLACEHOLDER-BUG）—— Constructor helper。
    ///
    /// 為什麼新增此 helper：32 既有 callsite 字面 `intent_type: IntentType::OpenLong`
    /// 是 backward-compat 占位；short-capable strategy（funding_arb / funding_harvest /
    /// bidirectional bb_breakout / bb_reversion / ma_crossover / grid_trading）出現
    /// `is_long=false / intent_type=OpenLong` 矛盾，造成 router.rs:100 寫死「TRADE_ENTRY」
    /// 與 LeaseScope 對映漂移風險。
    ///
    /// 本 helper 由 is_long 自動決定 intent_type，禁止 caller 再寫 literal；
    /// 8 個 strategy Open emit site 改走此 helper（per dispatch §Bug 2 Phase A）。
    /// 既有 Earn / CloseLong / PositionAdjust path 不走此 helper（caller 顯式填）。
    ///
    /// 不變量：本 helper 只負責 trade-entry intent（OpenLong / OpenShort 兩 variant）；
    /// 其他 intent_type 由 caller 直接 struct literal 或專屬 helper 構造。
    pub fn new_trade(
        symbol: String,
        is_long: bool,
        qty: f64,
        confidence: f64,
        strategy: String,
        order_type: String,
        limit_price: Option<f64>,
        confluence_score: Option<f32>,
        persistence_elapsed_ms: Option<u64>,
        time_in_force: Option<crate::order_manager::TimeInForce>,
        maker_timeout_ms: Option<u64>,
    ) -> Self {
        // 由 is_long 自動派生 intent_type，消除 is_long=false / OpenLong 矛盾。
        let intent_type = if is_long {
            IntentType::OpenLong
        } else {
            IntentType::OpenShort
        };
        let intent = Self {
            symbol,
            is_long,
            qty,
            confidence,
            strategy,
            order_type,
            limit_price,
            confluence_score,
            persistence_elapsed_ms,
            time_in_force,
            maker_timeout_ms,
            intent_type,
            earn_payload: None,
        };
        intent.validate();
        intent
    }

    /// Sprint 1B audit Bug 2 fix + Round 2 finding 6 —— dual-layer invariant check。
    ///
    /// 為什麼 dual-layer：
    /// 1. **Debug build**：debug_assert 直接 panic，CI / test / dev 自動暴露 mismatch；
    /// 2. **Release build**：tracing::warn! telemetry — trading hot path 不容許 panic
    ///    （Root Principle #5「survival above profit」），但 release CI 不能完全失明，
    ///    將來 caller 若用 inline struct literal 又呼 validate()，release 仍能由
    ///    log / metrics 監測到 mismatch。caller 必走 new_trade helper 才是設計契約；
    ///    本 layer 是 defence in depth，不是 fail-closed。
    ///
    /// Earn intent 跳過檢查（is_earn() 短路），因為 EarnStake / EarnRedeem 與
    /// is_long 不耦合（Earn flexible/fixed staking 與 long/short direction 無關）。
    pub fn validate(&self) {
        let aligned = self.intent_type.is_earn()
            || matches!(
                (self.is_long, &self.intent_type),
                (
                    true,
                    IntentType::OpenLong | IntentType::CloseLong | IntentType::PositionAdjust
                ) | (
                    false,
                    IntentType::OpenShort | IntentType::CloseShort | IntentType::PositionAdjust
                )
            );
        debug_assert!(
            aligned,
            "IntentType direction mismatch: is_long={} intent_type={:?} symbol={} strategy={}",
            self.is_long, self.intent_type, self.symbol, self.strategy
        );
        // Round 2 finding 6：release path 防線 —— warn telemetry 取代 silent passthrough。
        // 為什麼不 fail-closed reject：本 fn 簽名為 `(&self)` 無返回值，現有 caller
        // 路徑（OrderIntent::new_trade 構造 + IntentProcessor::process）已由 helper
        // 自動派生 intent_type，理論不會 mismatch。本 warn 是 future-proof defence。
        if !aligned {
            tracing::warn!(
                is_long = self.is_long,
                ?self.intent_type,
                symbol = %self.symbol,
                strategy = %self.strategy,
                "IntentType direction mismatch detected at validate() — caller bypassed new_trade helper / IntentType 方向不一致：caller 繞過 new_trade helper"
            );
        }
    }
}

/// Captured Guardian verdict for DB persistence (risk_verdicts table).
/// 捕獲的 Guardian 裁定，用於持久化到 risk_verdicts 表。
#[derive(Debug, Clone)]
pub struct VerdictInfo {
    /// "Approved", "Modified", or "Rejected" / 批准、修改或拒絕
    pub verdict: String,
    pub risk_score: f64,
    pub reasons: Vec<String>,
    pub modified_qty: Option<f64>,
}

impl VerdictInfo {
    /// P0-6 permanent fix: synthetic "Rejected" verdict for pre-Guardian gate
    /// rejections (cost_gate / qty_zero / risk_gate / duplicate_position / etc.).
    /// Callers lacking a real Guardian verdict use this so `persist_verdict`
    /// can still write the rejection reason into `trading.risk_verdicts`.
    /// P0-6 永久修復：前置 gate 拒絕時的 synthetic Rejected 裁定。
    pub(crate) fn rejected(reason: String) -> Self {
        Self {
            verdict: "Rejected".to_string(),
            risk_score: 0.0,
            reasons: vec![reason],
            modified_qty: None,
        }
    }
}

/// Result of intent processing.
/// 意圖處理結果。
#[derive(Debug, Clone)]
pub struct IntentResult {
    pub submitted: bool,
    pub rejected_reason: Option<String>,
    pub fill: Option<FillResult>,
    /// Guardian verdict for DB persistence; None if rejected before guardian check.
    /// Guardian 裁定供 DB 持久化；在 Guardian 前被拒時為 None。
    pub verdict_info: Option<VerdictInfo>,
    /// FUP-8 Phase 2: qty after Kelly+P1 sizing; 0.0 on rejection.
    /// Exposed so paper `persist_intent` can write the real sized qty into
    /// trading.intents.details (was 1e9 sentinel before Phase 2). Matches the
    /// pre-rounding `fill.fill_qty` on success.
    /// FUP-8 Phase 2：Kelly+P1 sizing 後的數量；拒絕路徑為 0.0。
    /// 暴露此欄位讓 paper `persist_intent` 寫入真實 sized qty（Phase 2 前為 1e9 sentinel）；
    /// 成功路徑下等同 `fill.fill_qty` 取整前。
    pub approved_qty: f64,
    /// EDGE-P2-3 Phase 1B-4.2: Paper-only handoff when router classifies a
    /// PostOnly limit intent as "accepted but waiting to fill". Router builds
    /// the draft using gate-approved qty + paper_state mid-price snapshot +
    /// caller-supplied context_id + now_ms; caller (`on_tick`) is responsible
    /// for `paper_state.enqueue_resting_limit_order(draft)` since router only
    /// holds `&PaperState` (immutable). `Some(_)` implies `submitted=true`
    /// and `fill=None` — the "accepted pending" shape. Market intents and
    /// all non-paper paths leave this `None`.
    /// EDGE-P2-3 Phase 1B-4.2：紙盤專用 PostOnly「已接受、等成交」交接。
    /// router 以 gate 通過的 qty、paper_state mid、caller context_id、now_ms
    /// 組成 draft；caller（on_tick）負責 enqueue（router 僅持唯讀借用）。
    /// `Some(_)` 蘊含 `submitted=true` 且 `fill=None`（「接受待成交」形狀）。
    /// 市價意圖與所有非紙盤路徑此欄位為 None。
    pub resting_order: Option<crate::paper_state::RestingLimitOrder>,
    /// EDGE-P2-3 Phase 1B-5: set by router when the MakerKpi gate downgraded
    /// a PostOnly intent to market execution because the symbol's fill rate
    /// / net-edge KPI is Degraded. Caller (`on_tick`) calls
    /// `paper_state.record_maker_degraded_fallback(symbol)` and logs — the
    /// market fill still happens on the normal path. `None` means "no gate
    /// action" (either market intent, Healthy/Cold gate, or exchange path).
    /// EDGE-P2-3 Phase 1B-5：router 因 MakerKpi gate 判定 Degraded 而將 PostOnly
    /// 降級為市價時填入 Some(symbol)。caller（on_tick）記 counter + warn，
    /// 市價成交仍走正常路徑。None = 無 gate 動作。
    pub maker_degraded_fallback: Option<String>,
    /// AMD-2026-05-02-01 Track E E-2: Decision Lease id acquired by Gate 1.4.
    /// `Some("lease:xxxx")` for Production profile when router-gate flag ON.
    /// `Some("bypass")` for Exploration / Validation profile (LeaseId::Bypass
    /// short-circuit). `None` means router-gate flag OFF (no acquire ever
    /// happened; default observable state during Sprint 3 灰度 Phase 5 OFF).
    /// E-3 IPC bridge / E-4 audit writer consume this for cross-row lineage.
    /// AMD-2026-05-02-01 Track E E-2：Gate 1.4 取得的 Decision Lease id。
    /// Production profile + flag ON → `Some("lease:xxxx")`；Exploration /
    /// Validation profile → `Some("bypass")`（LeaseId::Bypass 短路）；
    /// flag OFF（Sprint 3 灰度預設）→ `None`（從未 acquire）。
    /// E-3 IPC bridge 與 E-4 audit writer 取此欄位作 cross-row lineage 鍵。
    pub lease_id: Option<String>,
}

impl IntentResult {
    /// P0-6 permanent fix: build a rejected IntentResult with synthetic
    /// `verdict_info` so `persist_verdict` records the reason in DB.
    pub(crate) fn rejected(reason: String) -> Self {
        let vi = VerdictInfo::rejected(reason.clone());
        Self {
            submitted: false,
            rejected_reason: Some(reason),
            fill: None,
            verdict_info: Some(vi),
            approved_qty: 0.0,
            resting_order: None,
            maker_degraded_fallback: None,
            lease_id: None,
        }
    }
}

/// EXT-1: Result of gate-only processing for exchange mode.
/// EXT-1：交易所模式下僅門禁處理的結果。
#[derive(Debug, Clone)]
pub struct ExchangeGateResult {
    /// Whether the intent passed all gates / 意圖是否通過所有門禁
    pub approved: bool,
    /// Rejection reason if not approved / 未通過時的拒絕原因
    pub rejected_reason: Option<String>,
    /// Gate-approved quantity after Kelly sizing + P1 cap / 門禁批准的數量（Kelly + P1 上限後）
    pub approved_qty: f64,
    /// Guardian verdict for DB persistence; None if rejected before guardian check.
    /// Guardian 裁定供 DB 持久化；在 Guardian 前被拒時為 None。
    pub verdict_info: Option<VerdictInfo>,
    /// AMD-2026-05-02-01 Track E E-2: Decision Lease id acquired by Gate 1.4
    /// (mirror of IntentResult::lease_id; same semantics).
    /// AMD-2026-05-02-01 Track E E-2：Gate 1.4 取得的 Decision Lease id
    /// （與 IntentResult::lease_id 對齊，語意相同）。
    pub lease_id: Option<String>,
}

impl ExchangeGateResult {
    /// P0-6 permanent fix: see `IntentResult::rejected`.
    pub(crate) fn rejected(reason: String) -> Self {
        let vi = VerdictInfo::rejected(reason.clone());
        Self {
            approved: false,
            rejected_reason: Some(reason),
            approved_qty: 0.0,
            verdict_info: Some(vi),
            lease_id: None,
        }
    }
}

/// Intent processor with guardian checks.
/// 帶守護者檢查的意圖處理器。
/// Default P1 risk cap (3% of balance per trade).
/// 默認 P1 風險上限（每筆交易餘額的 3%）。
const DEFAULT_P1_RISK_PCT: f64 = 0.03;

/// Bybit USDT perp default taker fee (0.055%) — fallback when API rate not available.
/// Bybit USDT 永續合約默認 taker 費率，API 未提供時的回退值。
const DEFAULT_TAKER_FEE_RATE: f64 = 0.00055;

/// Bybit USDT perp default maker fee (0.02%) — fallback when API rate not available.
/// Matches `account_manager::DEFAULT_MAKER_FEE` so cold-boot cost estimates agree
/// with the AccountManager path once Bybit API rates arrive.
/// Bybit USDT 永續默認 maker 費率，API 未提供時的回退值；與 AccountManager 常量對齊。
const DEFAULT_MAKER_FEE_RATE: f64 = 0.0002;

/// G7-07: Default slippage rate fallback when volume data is unavailable, used
/// only by `lookup_slippage_default()` test helper / legacy callers that don't
/// have a `&RiskConfig` handy. Runtime slippage now flows through
/// `RiskConfig.slippage.lookup_rate(volume_24h)` so operators can hot-reload
/// the tier table from `risk_config*.toml`.
/// G7-07：默認滑點率回退；僅供 test helper / 無 RiskConfig 的舊 caller 使用。
/// 運行時滑點現由 `RiskConfig.slippage.lookup_rate(volume_24h)` 提供，可
/// 從 `risk_config*.toml` 熱重載 tier 表。
#[cfg(test)]
pub(crate) const DEFAULT_SLIPPAGE_RATE: f64 = 0.0005;

/// Maximum age for API-fetched fee rates before exchange cost gates fail closed.
/// API 費率最大可接受年齡；超過後 exchange 成本門 fail-closed。
pub(crate) const MAX_FEE_RATE_STALENESS_MS: u64 = 2 * 60 * 60 * 1000;

/// G7-07: Look up slippage using the live `SlippageConfig` (TOML-backed).
/// Pre-G7-07 callers used a free `lookup_slippage(volume_24h)` reading the
/// hardcoded `SLIPPAGE_TIERS`. Now the tier table lives in
/// `risk.slippage.tiers` and lookup goes through this thin wrapper to keep
/// call-site diff minimal while making the table runtime-tunable.
/// G7-07：經由 `SlippageConfig`（TOML 支援）查滑點。原 free fn 讀
/// hardcoded `SLIPPAGE_TIERS`；現 tier 表存於 `risk.slippage.tiers`，
/// 透過 thin wrapper 維持 call-site diff 最小。
fn lookup_slippage(config: &crate::config::SlippageConfig, volume_24h: f64) -> f64 {
    config.lookup_rate(volume_24h)
}

/// G7-07 test/helper: legacy free-function lookup using default tiers. Kept so
/// pre-G7-07 unit tests and any rare caller without a `RiskConfig` handle can
/// still resolve a tier rate without constructing a config snapshot.
/// G7-07 test/helper：用 default tiers 查滑點，供原始單測與少數無
/// RiskConfig handle 的 caller 使用，免於額外構造 config snapshot。
#[cfg(test)]
pub(crate) fn lookup_slippage_default(volume_24h: f64) -> f64 {
    crate::config::SlippageConfig::default().lookup_rate(volume_24h)
}

pub struct IntentProcessor {
    guardian: Guardian,
    /// Legacy single-rate fallback (None = use hardcoded default).
    /// Preferred path: read per-symbol from `account_manager` (live API source).
    /// 舊版單費率回退（None = 用常量）。優先路徑：從 account_manager 讀取 per-symbol 真實費率。
    taker_fee_rate: Option<f64>,
    /// Live per-symbol fee rates from Bybit `/v5/account/fee-rate`.
    /// Bybit API 動態 per-symbol 費率（每小時刷新）。
    account_manager: Option<std::sync::Arc<crate::account_manager::AccountManager>>,
    /// Phase 2b: Kelly sizing config (None = disabled, passthrough).
    /// Phase 2b：Kelly 倉位配置（None = 禁用，直通）。
    kelly_config: Option<crate::ml::kelly_sizer::KellyConfig>,
    /// Phase 2b: Per-symbol trade stats for Kelly calculation.
    /// Phase 2b：每交易對的交易統計，用於 Kelly 計算。
    trade_stats: std::collections::HashMap<String, crate::ml::kelly_sizer::TradeStats>,
    /// P1 risk cap percentage (configurable, default 3%).
    /// P1 風險上限百分比（可配置，默認 3%）。
    p1_risk_pct: f64,
    /// RRC-1-B4: Risk config for check_order_allowed Gate 0 (ARCH-RC1 unified).
    /// RRC-1-B4：風控配置，用於 Gate 0 訂單准入檢查。
    risk_config: RiskConfig,
    /// RRC-1-B2: Daily start balance for daily loss tracking (reset at UTC midnight).
    /// RRC-1-B2：每日起始餘額，用於日損追蹤（UTC 午夜重置）。
    daily_start_balance: f64,
    /// RRC-1-B2: UTC day number of last reset (days since epoch).
    /// RRC-1-B2：上次重置的 UTC 天數（自 epoch 起的天數）。
    daily_reset_day: u64,
    /// W-3: Optional LinUCB runtime — read-only, never affects gates / sizing /
    /// fills. Phase 5 will hook reward feedback through this same handle.
    /// W-3：可選的 LinUCB 運行時 — 唯讀，不影響任何 gate / sizing / fill。
    /// Phase 5 將通過此 handle 接 reward feedback。
    linucb: Option<std::sync::Arc<crate::linucb::LinUcbRuntime>>,
    /// W-3: Last LinUCB selection (set after gates pass; consumed by downstream
    /// DecisionContextMsg producer if it reads from intent_processor instead of
    /// computing inline).
    /// W-3：最近一次 LinUCB 選擇（gate 通過後設定；下游 DecisionContextMsg
    /// producer 若選擇從 intent_processor 讀則使用此欄位）。
    last_arm_selection: Option<crate::linucb::ArmSelection>,
    /// PH5-WIRE-1: Shrunk JS realized-edge estimates per (strategy, symbol).
    /// Loaded at startup from settings/edge_estimates.json; refreshed via set_edge_estimates().
    /// PH5-WIRE-1：每 (策略, 幣種) JS 收縮實現邊際估計。啟動時加載，可通過 set_edge_estimates() 刷新。
    edge_estimates: crate::edge_estimates::EdgeEstimates,
    /// BLOCKER-3 D15: Shared cross-engine global exposure (USDT × 100 for AtomicU64 precision).
    /// Updated by exchange pipelines (Demo/Live); Paper is excluded.
    /// BLOCKER-3 D15：跨引擎全局曝險（USDT × 100 存入 AtomicU64 以保留精度）。
    /// 由交易所管線（Demo/Live）更新；Paper 排除。
    global_exposure_usdt: Option<std::sync::Arc<std::sync::atomic::AtomicU64>>,
    /// FIX-28: Account leverage for risk checks. Paper=1.0, exchange=actual.
    /// FIX-28：帳戶槓桿用於風控檢查。Paper=1.0，交易所=實際值。
    account_leverage: f64,
    /// EDGE-P3-1 A4: Per-engine ML edge predictor store (None → gate skipped,
    /// falls through to legacy JS shrinkage gate). Wired by engine bootstrap
    /// via `set_edge_predictor_store`.
    /// EDGE-P3-1 A4：逐引擎 ML edge predictor store（None → 跳過 gate 回退 JS
    /// shrinkage）。由引擎啟動時經 `set_edge_predictor_store` 注入。
    edge_predictor_store: Option<Arc<EdgePredictorStore>>,
    /// EDGE-P3-1 A4: Pipeline kind — only Paper engine runs ε-greedy branch.
    /// EDGE-P3-1 A4：管線種類——僅 Paper 走 ε-greedy 分支。
    pipeline_kind: PipelineKind,
    /// Bybit endpoint this processor's pipeline is bound to. Used together with
    /// `pipeline_kind` to resolve the DB engine_mode tag via
    /// `mode_state::effective_engine_mode`. Set by
    /// `TickPipeline::set_endpoint_env` at bootstrap.
    /// Bybit 端點綁定，與 pipeline_kind 一併透過
    /// `mode_state::effective_engine_mode` 解析 DB engine_mode 標籤。
    endpoint_env: Option<crate::bybit_rest_client::BybitEnvironment>,
    /// EDGE-P3-1 A4: Deterministic SmallRng seeded per-engine (spec §7.3 F9).
    /// Interior mutability because gate evaluation happens via `&self`.
    /// EDGE-P3-1 A4：按引擎 seed 的 SmallRng（spec §7.3 F9）。
    /// interior mutability 以支援 `&self` 呼叫 gate。
    predictor_rng: Mutex<SmallRng>,
    /// EDGE-P3-1 A4: Pipeline command channel for `EmitShadowFill` dispatch.
    /// None → shadow fills dropped (fail-soft; predictor gate still runs).
    /// EDGE-P3-1 A4：PipelineCommand 發送通道用於 `EmitShadowFill`。None 時丟棄
    /// shadow fill（fail-soft；gate 仍運作）。
    shadow_fill_tx: Option<UnboundedSender<PipelineCommand>>,
    /// EDGE-P3-1 Step 7a: Direct DB channel for decision feature snapshots.
    /// Emitted at the top of `evaluate_predictor_gate` whenever a real
    /// `FeatureVectorV1` + non-empty `context_id` is available, regardless of
    /// whether the predictor is enabled — training data collection starts
    /// immediately in Stage 0 while the gate still short-circuits to the
    /// legacy shrinkage path.
    /// None → emission no-op (fail-soft; trading unaffected).
    /// EDGE-P3-1 Step 7a：決策特徵 DB 直寫通道。只要拿到真實 `FeatureVectorV1` +
    /// 非空 context_id，於 `evaluate_predictor_gate` 頂端即發射，無論 predictor
    /// 是否啟用 — Stage 0 即刻採集訓練資料；None 時發射為 no-op（fail-soft）。
    decision_feature_tx: Option<tokio::sync::mpsc::Sender<crate::database::DecisionFeatureMsg>>,
    /// W-AUDIT-4b-M1 split (V082)：candidate evaluation log channel。
    /// 對應每次 evaluate_predictor_gate 評估（無論 PredictorAction outcome），
    /// emit 到 learning.decision_features_evaluations（producer-debug / gate
    /// 行為觀測）。**不可作 ML training data**（pool 含 reject path 污染）。
    /// 與 decision_feature_tx 不同：後者改為 intent-only emit。
    /// None = 停用（fail-soft，不影響交易）。
    /// Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
    ///       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
    decision_feature_evaluation_tx:
        Option<tokio::sync::mpsc::Sender<crate::database::DecisionFeatureEvaluationMsg>>,
    /// EDGE-P2-3 Phase 1B-5: owned snapshot of `MakerKpiConfig` consulted by the
    /// router's PostOnly KPI gate (Degraded → silent market fallback). Mirrors
    /// the `risk_config` ownership pattern: TickPipeline pushes the latest
    /// `ConfigStore<MakerKpiConfig>` snapshot through `update_maker_kpi_config`
    /// whenever `sync_maker_kpi_config_if_changed` detects a version bump.
    /// Defaults to `MakerKpiConfig::default()` so tests and unwired bootstraps
    /// stay bit-identical to the pre-hot-reload commit.
    /// EDGE-P2-3 Phase 1B-5：router KPI gate 查詢用的 owned MakerKpiConfig 快照。
    /// 與 `risk_config` 同模式：TickPipeline 於偵測到版本升版時透過
    /// `update_maker_kpi_config` 推入最新快照；預設 `MakerKpiConfig::default()`
    /// 保持測試與未接線路徑的 bit-identical。
    maker_kpi_config: crate::paper_state::MakerKpiConfig,
    /// Sprint 1B Earn Wave C：Bybit Earn REST client（B3 wave land）。
    /// None = 引擎端 Earn capability OFF；process_earn_intent 路徑 fail-closed
    /// reject。Production caller 經 set_bybit_earn_client 注入；test 端不注入
    /// 即可驗 fail-closed 路徑。
    bybit_earn_client: Option<Arc<crate::bybit_earn_client::BybitEarnClient>>,
    /// Sprint 1B Earn Wave C：V100 earn_movement_log writer（B4 wave land）。
    /// None = Earn capability OFF；process_earn_intent 路徑 fail-closed reject。
    /// Production caller 經 set_earn_movement_writer 注入。
    earn_movement_writer: Option<Arc<crate::database::earn_movement_writer::EarnMovementWriter>>,
}

/// EDGE-P3-1 A4: Result of predictor-gate evaluation, translated to caller action.
/// EDGE-P3-1 A4：predictor gate 評估結果，已翻譯為 caller 動作。
#[derive(Debug, Clone)]
pub(super) enum PredictorAction {
    /// No-op — predictor disabled or no store; continue to legacy JS gate.
    /// 無動作 — predictor 禁用或無 store；繼續走 JS gate。
    UseLegacyGate,
    /// Predictor accepted (shadow_mode=false); skip legacy JS gate, continue pipeline.
    /// Predictor 接受（shadow_mode=false）；跳過 JS gate 繼續管線。
    SkipLegacyGate,
    /// Predictor rejected (hard reject OR ε-greedy fired OR fail-closed fallback).
    /// Predictor 拒絕（硬拒絕 / ε-greedy / fail-closed 回退）。
    Reject(String),
}

impl IntentProcessor {
    pub fn new() -> Self {
        Self {
            guardian: Guardian::default(),
            taker_fee_rate: None,
            account_manager: None,
            kelly_config: None,
            trade_stats: std::collections::HashMap::new(),
            p1_risk_pct: DEFAULT_P1_RISK_PCT,
            risk_config: RiskConfig::default(),
            daily_start_balance: 0.0,
            daily_reset_day: 0,
            linucb: None,
            last_arm_selection: None,
            edge_estimates: crate::edge_estimates::EdgeEstimates::empty(),
            global_exposure_usdt: None,
            account_leverage: 1.0,
            edge_predictor_store: None,
            pipeline_kind: PipelineKind::Paper,
            endpoint_env: None,
            // Tests get a fixed seed; production overrides via `set_predictor_rng_seed`.
            predictor_rng: Mutex::new(SmallRng::seed_from_u64(0)),
            shadow_fill_tx: None,
            decision_feature_tx: None,
            // W-AUDIT-4b-M1 split (V082)
            decision_feature_evaluation_tx: None,
            maker_kpi_config: crate::paper_state::MakerKpiConfig::default(),
            // Sprint 1B Earn Wave C：預設 None，capability OFF；
            // Production caller 經 set_bybit_earn_client / set_earn_movement_writer 注入。
            bybit_earn_client: None,
            earn_movement_writer: None,
        }
    }

    /// Create with an API-fetched taker fee rate.
    /// 使用 API 動態費率創建。
    pub fn with_fee_rate(rate: f64) -> Self {
        Self {
            guardian: Guardian::default(),
            taker_fee_rate: Some(rate),
            account_manager: None,
            kelly_config: None,
            trade_stats: std::collections::HashMap::new(),
            p1_risk_pct: DEFAULT_P1_RISK_PCT,
            risk_config: RiskConfig::default(),
            daily_start_balance: 0.0,
            daily_reset_day: 0,
            linucb: None,
            last_arm_selection: None,
            edge_estimates: crate::edge_estimates::EdgeEstimates::empty(),
            global_exposure_usdt: None,
            account_leverage: 1.0,
            edge_predictor_store: None,
            pipeline_kind: PipelineKind::Paper,
            endpoint_env: None,
            predictor_rng: Mutex::new(SmallRng::seed_from_u64(0)),
            shadow_fill_tx: None,
            decision_feature_tx: None,
            // W-AUDIT-4b-M1 split (V082)
            decision_feature_evaluation_tx: None,
            maker_kpi_config: crate::paper_state::MakerKpiConfig::default(),
            // Sprint 1B Earn Wave C：預設 None。
            bybit_earn_client: None,
            earn_movement_writer: None,
        }
    }

    /// FIX-28: Set account leverage for exchange pipelines (Demo/Live).
    /// FIX-28：為交易所管線設定帳戶槓桿。
    pub fn set_account_leverage(&mut self, leverage: f64) {
        self.account_leverage = leverage.max(1.0);
    }

    /// BLOCKER-3 D15: Wire shared global exposure atomic for cross-engine notional cap.
    /// BLOCKER-3 D15：接入跨引擎全局曝險原子量，用於全局名目上限檢查。
    pub fn set_global_exposure(&mut self, exposure: std::sync::Arc<std::sync::atomic::AtomicU64>) {
        self.global_exposure_usdt = Some(exposure);
    }

    /// BLOCKER-3 D15: Check if adding `order_notional_usdt` would breach the global cap.
    /// Returns None if no cap is configured or no shared atomic wired. Returns Some(reason) if blocked.
    /// BLOCKER-3 D15：檢查新增 order_notional_usdt 是否超出全局上限。
    /// 無上限或無共享原子量時返回 None。被阻擋時返回 Some(reason)。
    fn check_global_notional_cap(&self, order_notional_usdt: f64) -> Option<String> {
        let cap = self.risk_config.limits.global_notional_cap_usdt;
        if cap <= 0.0 {
            return None; // disabled
        }
        let exposure_arc = self.global_exposure_usdt.as_ref()?;
        let current_cents = exposure_arc.load(std::sync::atomic::Ordering::Relaxed);
        let current_usdt = current_cents as f64 / 100.0;
        let projected = current_usdt + order_notional_usdt;
        if projected > cap {
            Some(
                RejectionCode::GlobalNotionalCap {
                    projected,
                    cap,
                    current: current_usdt,
                }
                .format(),
            )
        } else {
            None
        }
    }

    /// FLASH-DIP-PILOT (2026-06-18): band-external hard cap (kill-switch 1).
    /// 對 `intent.strategy == "flash_dip_buy"` 的開倉做硬拒：若 effective notional
    /// (`final_qty * price`) > `balance * limits.flash_dip_buy_max_notional_pct_equity`
    /// 則回 Some(reason)；否則 None。在 gate stack Gate 2.7 region（final_qty 已知後）
    /// 呼叫，與 check_global_notional_cap 並列。
    ///
    /// 為什麼 hard reject 而非 scale：effective qty 已是 min(target, Kelly, P1) 保守值；
    /// 超過此 label-conditional cap 代表「即使被通用 P1 夾過仍超 pilot 收緊上限」=
    /// 結構性異常，fail-closed 拒整單。**此 cap 是 ADDITIVE 收緊，非 survival floor**
    /// （label-conditional，可被 mislabel 繞過）；真 floor = P1(2%)/position_size +
    /// max_order_notional_usdt（label-independent，已 denylist，由 check_order_allowed
    /// + global cap 強制）。reducing 單不受此 cap（降風險）。
    fn check_flash_dip_notional_cap(
        &self,
        strategy: &str,
        final_qty: f64,
        price: f64,
        balance: f64,
        is_reducing: bool,
    ) -> Option<String> {
        if is_reducing || strategy != "flash_dip_buy" {
            return None;
        }
        let pct = self
            .risk_config
            .limits
            .flash_dip_buy_max_notional_pct_equity;
        // pct <= 0 不可能（validate 守住），但 defense-in-depth：非正即不啟用 cap
        // 反而危險，故 <= 0 視為「最嚴」直接拒（fail-closed）。
        if !(pct > 0.0) || !balance.is_finite() || balance <= 0.0 {
            return Some(format!(
                "flash_dip_buy_notional_cap fail-closed: invalid pct={pct} or balance={balance}"
            ));
        }
        let order_notional = final_qty * price;
        let max_notional = balance * pct;
        // Bybit / UI / audit strings settle this cap at cent precision. Comparing raw
        // binary floats would reject display-equivalent sub-cent drift while the
        // reason itself prints both sides equal to two decimals.
        let order_notional_cents = (order_notional * 100.0).round() as i64;
        let max_notional_cents = (max_notional * 100.0).round() as i64;
        if order_notional_cents > max_notional_cents {
            Some(format!(
                "flash_dip_buy_notional_cap: order_notional={order_notional:.2} > \
                 {pct:.4} * equity({balance:.2}) = {max_notional:.2} (band-external hard cap)"
            ))
        } else {
            None
        }
    }

    /// EXIT-FEATURES-TABLE-1: Read-only accessor for the currently loaded
    /// shrunk-edge table. Used by `emit_close_fill` to stamp the `est_net_bps`
    /// feature onto `learning.exit_features` — the same table the cost_gate
    /// reads for pre-open gating, kept as a single source of truth so train-
    /// time labels and runtime gates never drift.
    /// EXIT-FEATURES-TABLE-1：當前 JS 收縮邊際表的唯讀取用器；emit_close_fill
    /// 以此填 `learning.exit_features.est_net_bps`，與 cost_gate 開倉前讀的
    /// 同一張表為單一來源，確保訓練標籤與執行時 gate 永不漂移。
    pub fn edge_estimates(&self) -> &crate::edge_estimates::EdgeEstimates {
        &self.edge_estimates
    }

    /// PH5-WIRE-1: Inject / refresh JS shrunk edge estimates.
    /// Called at startup and optionally via IPC reload trigger.
    /// PH5-WIRE-1：注入/刷新 JS 收縮邊際估計。啟動時調用，可通過 IPC 觸發刷新。
    pub fn set_edge_estimates(&mut self, estimates: crate::edge_estimates::EdgeEstimates) {
        let n = estimates.n_cells();
        let gm = estimates.grand_mean_bps();
        self.edge_estimates = estimates;
        tracing::info!(
            n_cells = n,
            grand_mean_bps = gm,
            "PH5-WIRE-1: edge estimates injected / 邊際估計已注入"
        );
    }

    /// W-3: Plug in a LinUCB runtime (read-only). When set, callers may invoke
    /// `select_arm_after_gates` after gate approval to record the arm picked
    /// for the current intent without changing any decision logic.
    /// W-3：注入 LinUCB 運行時（唯讀）。設定後 caller 可在 gate 通過後呼叫
    /// `select_arm_after_gates` 記錄當前 intent 對應的 arm，不改變任何決策邏輯。
    pub fn set_linucb_runtime(&mut self, rt: std::sync::Arc<crate::linucb::LinUcbRuntime>) {
        self.linucb = Some(rt);
    }

    /// W-3: After gates pass, record the LinUCB arm selection for the given
    /// regime + strategy + context. Fail-soft (logs warn, returns None on miss).
    /// W-3：gate 通過後記錄當前 regime+strategy+context 對應的 LinUCB arm。
    /// Fail-soft（miss 時 log warn 並返回 None）。
    pub fn select_arm_after_gates(
        &mut self,
        regime: &str,
        strategy: &str,
        context: &[f64],
    ) -> Option<crate::linucb::ArmSelection> {
        let rt = self.linucb.as_ref()?;
        let sel = rt.select_for_intent(regime, strategy, context);
        if sel.is_none() {
            tracing::warn!(
                regime = %regime,
                strategy = %strategy,
                "linucb arm not found in intent_processor select"
            );
        }
        self.last_arm_selection = sel.clone();
        sel
    }

    /// W-3: Read the most recent LinUCB selection (consumed by downstream
    /// DecisionContextMsg producers if they choose to pull from here).
    /// W-3：讀最近一次 LinUCB 選擇（下游 DecisionContextMsg producer 可選用）。
    pub fn last_arm_selection(&self) -> Option<&crate::linucb::ArmSelection> {
        self.last_arm_selection.as_ref()
    }

    /// Set P1 risk cap percentage (e.g. 0.03 = 3%, 0.05 = 5%).
    /// 設定 P1 風險上限百分比。
    pub fn set_p1_risk_pct(&mut self, pct: f64) {
        self.p1_risk_pct = pct.clamp(
            crate::config::MIN_PER_TRADE_RISK_PCT,
            crate::config::MAX_PER_TRADE_RISK_PCT,
        );
    }

    /// Get Guardian config for read-modify-write updates.
    /// 獲取守護者配置用於讀取-修改-寫回更新。
    pub fn guardian_config(&self) -> &openclaw_core::guardian::GuardianConfig {
        self.guardian.config()
    }

    /// Update Guardian config at runtime. / 運行時更新守護者配置。
    pub fn update_guardian_config(&mut self, config: openclaw_core::guardian::GuardianConfig) {
        self.guardian.update_config(config);
    }

    /// Phase 2b: Set Kelly sizing config.
    /// Phase 2b：設定 Kelly 倉位配置。
    pub fn set_kelly_config(&mut self, config: crate::ml::kelly_sizer::KellyConfig) {
        self.kelly_config = Some(config);
    }

    /// RRC-1-B4: Update risk config at runtime (ARCH-RC1).
    /// Also pulls the per-trade risk cap out of `limits.per_trade_risk_pct`
    /// and pushes it through the existing clamped setter so Gate 2.6 sees the
    /// patched value on the next tick (single source of truth = ConfigStore).
    /// RRC-1-B4：運行時更新風控配置；同時把 limits.per_trade_risk_pct 透過既有
    /// 帶 clamp 的 setter 灌進去，讓 Gate 2.6 在下一個 tick 看到新值。
    pub fn update_risk_config(&mut self, config: RiskConfig) {
        let new_p1 = config.limits.per_trade_risk_pct;
        self.risk_config = config;
        self.set_p1_risk_pct(new_p1);
        if self.kelly_config.is_some() {
            self.kelly_config = Some(crate::ml::kelly_sizer::KellyConfig::from_risk_config(
                &self.risk_config,
            ));
        }
    }

    /// RRC-1-B4: Read-only access to risk config.
    /// RRC-1-B4：風控配置的唯讀訪問。
    pub fn risk_config(&self) -> &RiskConfig {
        &self.risk_config
    }

    /// Accepted Demo USDT equity snapshot for order-cap envelope derivation.
    /// Returns None until the AccountManager has a positive finite balance.
    pub fn accepted_demo_equity_usdt(&self) -> Option<f64> {
        let accepted_demo_equity_usdt = self.account_manager.as_ref()?.usdt_equity();
        if accepted_demo_equity_usdt.is_finite() && accepted_demo_equity_usdt > 0.0 {
            Some(accepted_demo_equity_usdt)
        } else {
            None
        }
    }

    /// Scanner/risk pre-gate helper for fresh strategy entries.
    /// scanner/risk 新開倉前置門控 helper。
    pub fn per_strategy_new_entry_rejection(&self, intent: &OrderIntent) -> Option<String> {
        crate::config::per_strategy_new_entry_rejection(
            &self.risk_config,
            &intent.strategy,
            &intent.symbol,
        )
    }

    /// EDGE-P2-3 Phase 1B-5: Push a fresh MakerKpiConfig snapshot (called by
    /// TickPipeline's `sync_maker_kpi_config_if_changed` on store version bump).
    /// The router reads this snapshot inside `process_with_features` when
    /// evaluating the PostOnly KPI gate, so the next intent routed after a
    /// patch lands already sees the new thresholds without a restart.
    /// EDGE-P2-3 Phase 1B-5：推入最新 MakerKpiConfig 快照；由 TickPipeline 在
    /// store 升版時呼叫。router 在 `process_with_features` 裡評估 PostOnly KPI
    /// gate 時讀此快照，patch 落地後下一筆意圖即見新門檻、無需重啟。
    pub fn update_maker_kpi_config(&mut self, config: crate::paper_state::MakerKpiConfig) {
        self.maker_kpi_config = config;
    }

    /// EDGE-P2-3 Phase 1B-5: Read-only access to the live MakerKpiConfig
    /// snapshot consulted by the router KPI gate.
    /// EDGE-P2-3 Phase 1B-5：router KPI gate 使用的 MakerKpiConfig 唯讀存取。
    pub fn maker_kpi_config(&self) -> &crate::paper_state::MakerKpiConfig {
        &self.maker_kpi_config
    }

    /// PNL-7: Patch the dynamic-stop / RR tunables in-place. Each Some(v) is
    /// validated and applied; None leaves the field untouched. Returns the
    /// number of fields actually changed (for IPC ack).
    /// PNL-7：原地更新動態止損 / RR 三個可調參數，逐個驗證後生效。
    pub fn patch_dynamic_stop_params(
        &mut self,
        base_ratio: Option<f64>,
        cap_ratio: Option<f64>,
        trailing_min_rr_ratio: Option<f64>,
    ) -> u32 {
        let mut changed = 0;
        if let Some(v) = base_ratio {
            if v.is_finite() && (0.05..=1.0).contains(&v) {
                self.risk_config.dynamic_stop.base_ratio = v;
                changed += 1;
            }
        }
        if let Some(v) = cap_ratio {
            if v.is_finite() && (0.1..=1.0).contains(&v) {
                self.risk_config.dynamic_stop.cap_ratio = v;
                changed += 1;
            }
        }
        if let Some(v) = trailing_min_rr_ratio {
            if v.is_finite() && (0.0..=2.0).contains(&v) {
                self.risk_config.dynamic_stop.trailing_min_rr = v;
                changed += 1;
            }
        }
        changed
    }

    /// Session 12: Patch cost-gate + regime tunables in-place with validation.
    /// Each Some(v) is range-checked; invalid values silently dropped.
    /// Session 12：原地更新成本門 + regime 三類參數，逐個範圍校驗。
    pub fn patch_cost_gate_params(
        &mut self,
        min_confidence: Option<f64>,
        k_base: Option<f64>,
        k_medium: Option<f64>,
        k_small: Option<f64>,
        adx_trending_threshold: Option<f64>,
    ) -> u32 {
        let mut changed = 0;
        if let Some(v) = min_confidence {
            if v.is_finite() && (0.0..=1.0).contains(&v) {
                self.risk_config.cost_gate.min_confidence = v;
                changed += 1;
            }
        }
        if let Some(v) = k_base {
            if v.is_finite() && (0.5..=10.0).contains(&v) {
                self.risk_config.cost_gate.k_base = v;
                changed += 1;
            }
        }
        if let Some(v) = k_medium {
            if v.is_finite() && (0.5..=20.0).contains(&v) {
                self.risk_config.cost_gate.k_medium = v;
                changed += 1;
            }
        }
        if let Some(v) = k_small {
            if v.is_finite() && (0.5..=50.0).contains(&v) {
                self.risk_config.cost_gate.k_small = v;
                changed += 1;
            }
        }
        if let Some(v) = adx_trending_threshold {
            if v.is_finite() && (0.0..=100.0).contains(&v) {
                self.risk_config.cost_gate.adx_trending = v;
                changed += 1;
            }
        }
        changed
    }

    /// RRC-1-B2: Update daily start balance (called on each tick, resets at UTC midnight).
    /// RRC-1-B2：更新每日起始餘額（每 tick 調用，UTC 午夜重置）。
    pub fn maybe_reset_daily_balance(&mut self, balance: f64, ts_ms: u64) {
        let day = ts_ms / 86_400_000; // UTC day number / UTC 天數
        if day != self.daily_reset_day {
            self.daily_start_balance = balance;
            self.daily_reset_day = day;
        }
    }

    /// RRC-1-B2: Compute current daily loss percentage (internal).
    /// RRC-1-B2：計算當前日損百分比（內部）。
    fn daily_loss_pct(&self, current_balance: f64) -> f64 {
        if self.daily_start_balance <= 0.0 {
            return 0.0;
        }
        let loss = self.daily_start_balance - current_balance;
        if loss <= 0.0 {
            0.0
        } else {
            loss / self.daily_start_balance * 100.0
        }
    }

    /// RRC-1-C2: Public accessor for daily loss percentage (used by tick_pipeline Step 6).
    /// RRC-1-C2：日損百分比公開訪問器（用於 tick_pipeline 步驟 6）。
    pub fn daily_loss_pct_pub(&self, current_balance: f64) -> f64 {
        self.daily_loss_pct(current_balance)
    }

    /// P1-PORTFOLIO-RESTING-EXPOSURE-1：計算「有效 long / short notional」
    /// （= filled positions ± resting maker pending 的 netting 結果）。本 helper
    /// 是 `compute_exposure_pct` 與 `compute_correlated_exposure_pct` 的單一 SoT，
    /// 避免兩個 caller 各自累加導致行為漂移。
    ///
    /// 設計動機（A3 verify report `2026-05-15--f_fa_2_portfolio_var_exposure_sot_verify.md` §2/§7/§8）：
    /// 修前 portfolio gate 只看 `paper_state.positions()`（filled qty），對
    /// `paper_state.resting_limit_orders` 完全 invisible。entry-side maker
    /// pending 還沒 fill 時 filled 邊 = 0 → portfolio under-estimate；close-side
    /// maker pending 還沒 fill 時 filled 邊保留 full → portfolio over-estimate。
    /// 兩種方向的盲區都隨 EDGE-P2-3 Phase 1B-4.2 entry-side resting 落地後逐步
    /// 暴露面擴大，close-maker-first 進場後會再放大；本 helper 把 resting 納入
    /// 計算後行為更保守（生存 > 利潤 原則 5/6 + 組合級風險意識 原則 16）。
    ///
    /// Netting 規則（per symbol）：
    /// 1. filled position：`PaperPosition.qty × price` 直接歸入對應方向。
    /// 2. resting order，視「相對於該 symbol 已有 filled position」的方向：
    ///    - **同向 / 該 symbol 無倉**：視為 entry-side resting，預期成交後會
    ///      增加同方向 notional → `resting.qty × limit_price` 加進對應方向。
    ///    - **反向（is_reducing）**：視為 close-side resting，預期成交後會
    ///      減少對立方向 filled notional → 從對立 filled 邊扣減 resting 量。
    ///      扣減封頂 = 對立 filled 邊未抵銷的餘額，避免出現負值（保守版本，
    ///      A3 §8 設計要點 1「symbol-level netting」）。
    /// 3. 整體仍 `≥ 0`（負值會被 clamp 為 0），避免下游 `.min(999.0)` 之外的
    ///    異常輸入流向 caller。
    ///
    /// P2-PORTFOLIO-RESTING-ROUTER-CACHE（2026-05-18）：visibility 升 `pub(crate)`
    /// 配合 router 端 caller 一次 netting → 三百分比共用 tuple 的快取重構。
    /// P2-PORTFOLIO-RESTING-E5-BENCH（2026-05-18）：bench harness 為 external crate
    /// target，無法看見 `pub(crate)`；故再升為 `#[doc(hidden)] pub`，但 doc-hidden
    /// 明示「僅供 bench / 內部使用，非業務 API surface」，IPC / GUI / Python 不暴露。
    #[doc(hidden)]
    pub fn compute_effective_long_short_notional(paper_state: &PaperState) -> (f64, f64) {
        use std::collections::HashMap;

        // 先按 symbol 收 filled 邊（同 symbol 同向才會出現重複，這層 grouping
        // 主要是給後續 resting netting 用：必須知道對立 filled 邊還剩多少可扣）。
        // 注意 PaperPosition 每 symbol 至多 1 筆，但保留 HashMap 結構是給未來
        // 多 leg / hedge mode 留 headroom，不額外引入假設。
        let mut filled_long_by_sym: HashMap<&str, f64> = HashMap::new();
        let mut filled_short_by_sym: HashMap<&str, f64> = HashMap::new();
        for p in paper_state.positions() {
            let price = paper_state.latest_price(&p.symbol).unwrap_or(p.entry_price);
            let notional = p.qty * price;
            if !notional.is_finite() || notional <= 0.0 {
                continue;
            }
            if p.is_long {
                *filled_long_by_sym.entry(p.symbol.as_str()).or_insert(0.0) += notional;
            } else {
                *filled_short_by_sym.entry(p.symbol.as_str()).or_insert(0.0) += notional;
            }
        }

        // resting 邊：先累 entry-side（加），再累 close-side（從對立 filled 邊扣）。
        // 兩階段分開掃 iterator 兩次，邏輯清晰且避免單次掃描內 partial 結果
        // 互相干擾（同 symbol 多筆 resting 時各自累加才不會因順序差異產生 drift）。
        let mut entry_long_by_sym: HashMap<&str, f64> = HashMap::new();
        let mut entry_short_by_sym: HashMap<&str, f64> = HashMap::new();
        let mut close_reduces_long_by_sym: HashMap<&str, f64> = HashMap::new();
        let mut close_reduces_short_by_sym: HashMap<&str, f64> = HashMap::new();

        for r in paper_state.resting_limit_orders_iter() {
            if !r.qty.is_finite() || r.qty <= 0.0 {
                continue;
            }
            if !r.limit_price.is_finite() || r.limit_price <= 0.0 {
                continue;
            }
            let notional = r.qty * r.limit_price;
            if !notional.is_finite() || notional <= 0.0 {
                continue;
            }

            let sym = r.symbol.as_str();
            // 判定 is_reducing 與 router.rs:261-265 / 752-756 完全對齊：
            // 該 symbol 已有 filled position 且 resting.is_long ≠ position.is_long → close-side。
            let opposite_filled_present = if r.is_long {
                filled_short_by_sym.contains_key(sym)
            } else {
                filled_long_by_sym.contains_key(sym)
            };

            if opposite_filled_present {
                // close-side resting：從對立 filled 邊扣（封頂於對立 filled 餘額）。
                if r.is_long {
                    *close_reduces_short_by_sym.entry(sym).or_insert(0.0) += notional;
                } else {
                    *close_reduces_long_by_sym.entry(sym).or_insert(0.0) += notional;
                }
            } else {
                // entry-side resting（含 symbol 無倉 / 同向加倉）：加到對應方向。
                if r.is_long {
                    *entry_long_by_sym.entry(sym).or_insert(0.0) += notional;
                } else {
                    *entry_short_by_sym.entry(sym).or_insert(0.0) += notional;
                }
            }
        }

        // 收口 per-symbol effective：close 扣減封頂於對立 filled 餘額（保守）。
        let mut total_effective_long = 0.0_f64;
        let mut total_effective_short = 0.0_f64;

        // 同時遍歷所有出現過的 symbol（filled long/short + entry long/short + close reduces）。
        let mut all_syms: std::collections::HashSet<&str> = std::collections::HashSet::new();
        all_syms.extend(filled_long_by_sym.keys().copied());
        all_syms.extend(filled_short_by_sym.keys().copied());
        all_syms.extend(entry_long_by_sym.keys().copied());
        all_syms.extend(entry_short_by_sym.keys().copied());
        all_syms.extend(close_reduces_long_by_sym.keys().copied());
        all_syms.extend(close_reduces_short_by_sym.keys().copied());

        for sym in all_syms {
            let f_long = filled_long_by_sym.get(sym).copied().unwrap_or(0.0);
            let f_short = filled_short_by_sym.get(sym).copied().unwrap_or(0.0);
            let e_long = entry_long_by_sym.get(sym).copied().unwrap_or(0.0);
            let e_short = entry_short_by_sym.get(sym).copied().unwrap_or(0.0);
            let red_long = close_reduces_long_by_sym.get(sym).copied().unwrap_or(0.0);
            let red_short = close_reduces_short_by_sym.get(sym).copied().unwrap_or(0.0);

            // 扣減封頂於該方向 filled 餘額（保守，避免出現負值）。
            let red_long_capped = red_long.min(f_long).max(0.0);
            let red_short_capped = red_short.min(f_short).max(0.0);

            let eff_long = (f_long + e_long - red_long_capped).max(0.0);
            let eff_short = (f_short + e_short - red_short_capped).max(0.0);

            total_effective_long += eff_long;
            total_effective_short += eff_short;
        }

        (total_effective_long, total_effective_short)
    }

    /// P2-PORTFOLIO-RESTING-ROUTER-CACHE（2026-05-18）：曝險百分比的「已快取
    /// netting」版本。caller 在熱路徑（router Gate 2.7）先呼一次
    /// `compute_effective_long_short_notional` + `paper_state.balance()`，把
    /// `(eff_long, eff_short, balance)` 同時餵給三個 `_from_netting` 變體，
    /// 從而把原本「三次重建 HashMap netting」削成「一次重建 + 三次純算術」。
    /// 算術結果與 `compute_exposure_pct(&PaperState)` 完全等價（保留既有 wrapper
    /// 供 replay/risk_adapter 與測試 fixture 使用）。
    ///
    /// 為什麼三個變體都收 `balance` 而非自取：避免 caller 與 helper 對
    /// `paper_state.balance()` 各取一次造成 race（FA/PA 對 RRC-1 評審要求所有
    /// portfolio 百分比同 SoT 同 snapshot）。
    #[doc(hidden)]
    pub fn compute_exposure_pct_from_netting(eff_long: f64, eff_short: f64, balance: f64) -> f64 {
        if balance <= 0.0 {
            return 0.0;
        }
        ((eff_long + eff_short) / balance * 100.0).min(999.0)
    }

    /// P2-PORTFOLIO-RESTING-ROUTER-CACHE：相關曝險的快取版本，數學等價
    /// `compute_correlated_exposure_pct(&PaperState)`。
    #[doc(hidden)]
    pub fn compute_correlated_exposure_pct_from_netting(
        eff_long: f64,
        eff_short: f64,
        balance: f64,
    ) -> f64 {
        if balance <= 0.0 {
            return 0.0;
        }
        (eff_long.max(eff_short) / balance * 100.0).min(999.0)
    }

    /// P2-PORTFOLIO-RESTING-ROUTER-CACHE：槓桿的快取版本，數學等價
    /// `compute_leverage(&PaperState)`（exposure_pct / 100）。
    #[doc(hidden)]
    pub fn compute_leverage_from_netting(eff_long: f64, eff_short: f64, balance: f64) -> f64 {
        Self::compute_exposure_pct_from_netting(eff_long, eff_short, balance) / 100.0
    }

    /// RRC-1-B3：總曝險改用「effective long + short」（filled + resting netting），
    /// 與 `compute_correlated_exposure_pct` 共用同一 SoT
    /// （`compute_effective_long_short_notional`）避免兩個 helper 漂移。
    /// P1-PORTFOLIO-RESTING-EXPOSURE-1 引入 effective notional 路徑。
    /// P2-PORTFOLIO-RESTING-ROUTER-CACHE：本 wrapper 現在委派給
    /// `compute_exposure_pct_from_netting`，保留簽名供 replay/risk_adapter
    /// （`replay/risk_adapter.rs` doc 鏡射）與既有測試 fixture（tests.rs ×8）使用。
    fn compute_exposure_pct(paper_state: &PaperState) -> f64 {
        let (eff_long, eff_short) = Self::compute_effective_long_short_notional(paper_state);
        Self::compute_exposure_pct_from_netting(eff_long, eff_short, paper_state.balance())
    }

    /// RG-2：從持倉計算實際帳戶槓桿（總名義值 / 餘額），替代硬編碼 1.0；
    /// 替換後 leverage check 才會真正觸發。
    /// P1-PORTFOLIO-RESTING-EXPOSURE-1：間接吃 effective notional，所以 leverage
    /// 也會反映 resting maker pending 的預期影響。
    /// P2-PORTFOLIO-RESTING-ROUTER-CACHE：保留 wrapper 給 router.rs 296/784 兩處
    /// guardian-leverage 用（非 Gate 2.7 cluster，掃描重構之外）。
    fn compute_leverage(paper_state: &PaperState) -> f64 {
        let (eff_long, eff_short) = Self::compute_effective_long_short_notional(paper_state);
        Self::compute_leverage_from_netting(eff_long, eff_short, paper_state.balance())
    }

    /// FIX-05：計算相關曝險 — max(多頭名義值, 空頭名義值) / 餘額；
    /// 加密貨幣高度相關，同方向持倉風險疊加。
    /// P1-PORTFOLIO-RESTING-EXPOSURE-1：long/short 兩邊都改吃 effective notional
    /// （filled + resting netting）。close-side resting 仍只扣減 same-symbol 對立
    /// filled 邊（不跨 symbol 假設對沖），保留「同方向風險疊加」的核心語意。
    /// P2-PORTFOLIO-RESTING-ROUTER-CACHE：委派至 `_from_netting` 變體。
    fn compute_correlated_exposure_pct(paper_state: &PaperState) -> f64 {
        let (eff_long, eff_short) = Self::compute_effective_long_short_notional(paper_state);
        Self::compute_correlated_exposure_pct_from_netting(
            eff_long,
            eff_short,
            paper_state.balance(),
        )
    }

    /// Phase 2b: Record a closed trade for Kelly stats.
    /// Phase 2b：記錄已平倉交易用於 Kelly 統計。
    pub fn record_trade(&mut self, symbol: &str, pnl: f64) {
        self.trade_stats
            .entry(symbol.to_string())
            .or_default()
            .record(pnl);
    }

    /// Set dynamic fee rate post-creation (for hot-reload).
    /// 創建後設定動態費率（用於熱重載）。
    pub fn set_fee_rate(&mut self, rate: f64) {
        self.taker_fee_rate = Some(rate);
    }

    /// Set live AccountManager for per-symbol API-fetched fee rates.
    /// 設置 AccountManager 用於 per-symbol 真實費率。
    pub fn set_account_manager(
        &mut self,
        am: std::sync::Arc<crate::account_manager::AccountManager>,
    ) {
        self.account_manager = Some(am);
    }

    pub(crate) fn fee_rate_staleness_rejection(&self, now_ms: u64) -> Option<String> {
        let am = self.account_manager.as_ref()?;
        let last = am.last_fee_refresh_ms();
        if last == 0 {
            return Some("cost_gate: fee rates unavailable (cold boot, fail-closed)".to_string());
        }
        let now = if now_ms > 0 {
            now_ms
        } else {
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64
        };
        let age_ms = now.saturating_sub(last);
        if age_ms > MAX_FEE_RATE_STALENESS_MS {
            // Bybit demo endpoints do not support `/v5/account/fee-rate`.
            // Once conservative defaults exist in cache, treat that explicit
            // model as usable instead of freezing Demo/LiveDemo on timestamp
            // age; mainnet remains strict.
            if matches!(
                self.endpoint_env,
                Some(
                    crate::bybit_rest_client::BybitEnvironment::Demo
                        | crate::bybit_rest_client::BybitEnvironment::LiveDemo
                )
            ) && am.fee_rate_count() > 0
            {
                return None;
            }

            Some(format!(
                "cost_gate: fee rates stale age_ms={} > max_ms={} (fail-closed)",
                age_ms, MAX_FEE_RATE_STALENESS_MS
            ))
        } else {
            None
        }
    }

    /// EDGE-P3-1 A4: Wire the per-engine EdgePredictorStore. None → gate skipped.
    /// EDGE-P3-1 A4：注入逐引擎 EdgePredictorStore。None → 跳過 gate。
    pub fn set_edge_predictor_store(&mut self, store: Arc<EdgePredictorStore>) {
        self.edge_predictor_store = Some(store);
    }

    /// EDGE-P3-1 A4: Set the pipeline kind (Paper uniquely runs ε-greedy branch).
    /// EDGE-P3-1 A4：設定管線種類（僅 Paper 跑 ε-greedy 分支）。
    pub fn set_pipeline_kind(&mut self, kind: PipelineKind) {
        self.pipeline_kind = kind;
    }

    /// Bind this processor to a concrete Bybit endpoint so DB writes
    /// (decision_feature snapshots, shadow-fill rows) tag with the
    /// endpoint-aware engine_mode. Called by `TickPipeline::set_endpoint_env`.
    /// 綁定 Bybit 端點；DB 寫入使用 endpoint-aware engine_mode。
    pub fn set_endpoint_env(&mut self, env: crate::bybit_rest_client::BybitEnvironment) {
        self.endpoint_env = Some(env);
    }

    /// DB engine_mode tag for this processor (endpoint-aware). Mirrors
    /// `TickPipeline::effective_engine_mode`.
    /// 本處理器的 DB engine_mode 標籤（endpoint 感知）。
    #[inline]
    pub fn effective_engine_mode(&self) -> &'static str {
        crate::mode_state::effective_engine_mode(self.pipeline_kind, self.endpoint_env)
    }

    /// EDGE-P3-1 A4: Seed the predictor RNG (spec §7.3 F9 — `seed_for_engine(...)`).
    /// EDGE-P3-1 A4：seed predictor RNG（spec §7.3 F9）。
    pub fn set_predictor_rng_seed(&mut self, seed: u64) {
        self.predictor_rng = Mutex::new(SmallRng::seed_from_u64(seed));
    }

    /// EDGE-P3-1 A4: Read the current pipeline kind this processor was built
    /// for (what `GateInputs.engine_kind` reports into the predictor gate).
    /// Exposed for bootstrap regression tests that verify `TickPipeline::with_kind`
    /// forwards the kind correctly — production callers should not need it.
    /// EDGE-P3-1 A4：讀取目前 pipeline kind（gate 用於判斷是否走 ε-greedy 分支）。
    pub fn pipeline_kind(&self) -> PipelineKind {
        self.pipeline_kind
    }

    /// Test-only accessor: lock the predictor RNG so regression tests can draw
    /// bits off two differently-seeded processors and verify the streams
    /// diverge. Production callers consume the RNG exclusively through the
    /// gate inside `evaluate_predictor_gate`.
    /// 僅測試用：鎖預測器 RNG 供回歸測試比較兩條獨立 seed 的抽樣流。
    #[cfg(test)]
    pub fn predictor_rng_lock_for_tests(&self) -> parking_lot::MutexGuard<'_, SmallRng> {
        self.predictor_rng.lock()
    }

    /// EDGE-P3-1 A4: Inject a PipelineCommand sender for `EmitShadowFill` dispatch.
    /// EDGE-P3-1 A4：注入 PipelineCommand 發送通道用於 `EmitShadowFill`。
    pub fn set_shadow_fill_tx(&mut self, tx: UnboundedSender<PipelineCommand>) {
        self.shadow_fill_tx = Some(tx);
    }

    /// EDGE-P3-1 Step 7a + W-AUDIT-4b-M1 split (V082)：注入 production
    /// `DecisionFeatureMsg` writer 通道。**現為 intent-only emit**：caller
    /// （tick_pipeline step_4_5_dispatch）於 success path（result.submitted）
    /// 才呼叫 `emit_decision_feature_intent_emitted`。
    /// `evaluate_predictor_gate` 內**不再**寫此通道；改用
    /// `decision_feature_evaluation_tx`（evaluation log）。
    /// None → emission no-op（fail-soft，不影響交易）。
    /// Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
    ///       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
    pub fn set_decision_feature_tx(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::DecisionFeatureMsg>,
    ) {
        self.decision_feature_tx = Some(tx);
    }

    /// W-AUDIT-4b-M1 split (V082)：注入 candidate evaluation log writer 通道。
    /// `evaluate_predictor_gate` 頂端對每次評估發射一條（無論 outcome），
    /// 寫入 learning.decision_features_evaluations。
    /// None → emission no-op（fail-soft；evaluation 不採集但不影響交易）。
    /// Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
    ///       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
    pub fn set_decision_feature_evaluation_tx(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::DecisionFeatureEvaluationMsg>,
    ) {
        self.decision_feature_evaluation_tx = Some(tx);
    }

    // Sprint 1B Earn Wave C：setter + process_earn_intent 於
    // earn_router.rs 內 cross-file impl block 提供，避免 mod.rs 超 2000 LOC hard cap。
    // 對齊 CLAUDE.md §九「2000 lines is the per-file review/split threshold」原則：
    // split 到 sibling file 是允許的反模式之一。

    /// EDGE-P3-1 A4: Evaluate the predictor gate for an intent. Returns a
    /// `PredictorAction` the caller uses to decide whether to skip/continue/reject.
    /// Emits `EmitShadowFill` when gate returns ε-greedy ShadowFill and a tx is wired.
    ///
    /// Policy (spec §7.3 · §7.4):
    /// - `!cfg.use_edge_predictor || store=None || features=None` → UseLegacyGate.
    /// - `cfg.shadow_mode=true` → always UseLegacyGate (Stage 3 observation).
    /// - Outcome=Accept → SkipLegacyGate (predictor decides).
    /// - Outcome=Reject/RejectAdd → Reject.
    /// - Outcome=ShadowFill → emit IPC, Reject("epsilon_greedy_exploration").
    /// - Outcome=Fallback(reason) → Shrinkage config: UseLegacyGate;
    ///   FailClosed config: Reject("predictor_fallback_fail_closed:<metric>").
    ///
    /// EDGE-P3-1 A4：評估預測器 gate 並翻譯為 caller 動作。
    pub(super) fn evaluate_predictor_gate(
        &self,
        intent: &OrderIntent,
        paper_state: &PaperState,
        features: Option<&FeatureVectorV1>,
        context_id: &str,
        now_ms: u64,
        cost_bps: f64,
    ) -> PredictorAction {
        // W-AUDIT-4b-M1 split (V082)：先短路所有不能 emit evaluation 的場景，
        // 真正評估 gate 後 emit 一條 evaluation row（無論 outcome）。
        //
        // 與舊行為差異（root cause: 99.32% orphan rows）：
        //   - 舊：emit 到 learning.decision_features（PK=context_id, ON CONFLICT
        //     DO NOTHING），所有評估都寫，無論 intent 是否真正 emit。
        //   - 新：emit 到 learning.decision_features_evaluations（BIGSERIAL PK，
        //     append-only），保 evaluation 流量；
        //     learning.decision_features 改由 caller (step_4_5_dispatch) 在
        //     intent 真正 emit (success path) 時呼叫
        //     `emit_decision_feature_intent_emitted`。
        //
        // 邏輯重構：原本前段「short-circuit 不評估」+「跳出回 UseLegacyGate」
        // 全混在一起；現在把 outcome 字串化為 V082 enum 後寫 evaluation log，
        // 再返回 PredictorAction。
        // Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
        //       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
        let cfg = &self.risk_config.edge_predictor;
        let no_predictor =
            !cfg.use_edge_predictor || self.edge_predictor_store.is_none() || features.is_none();
        if no_predictor {
            // emit evaluation log 然後返回（與舊路徑相容）
            self.try_emit_evaluation_log(
                intent,
                features,
                context_id,
                now_ms,
                "use_legacy_no_predictor",
                "evaluation_log",
            );
            return PredictorAction::UseLegacyGate;
        }

        // 經短路後 store / features 一定 Some（unwrap 安全，no_predictor=false）
        let store = self.edge_predictor_store.as_ref().expect("store checked");
        let features_ref = features.expect("features checked");

        // is_add: intent side matches existing position → would add to it. Used by
        // `require_q10_positive_for_adds` (gate ignores when flag is off).
        // is_add：意圖方向與現有持倉相同視為加倉。
        let is_add = paper_state
            .get_position(&intent.symbol)
            .map(|p| p.is_long == intent.is_long)
            .unwrap_or(false);

        let inputs = GateInputs {
            engine_kind: self.pipeline_kind,
            strategy: &intent.strategy,
            symbol: &intent.symbol,
            context_id,
            cost_bps,
            is_add_to_existing: is_add,
            now_ms,
        };

        let outcome = {
            let mut rng = self.predictor_rng.lock();
            edge_predictor_gate(
                &inputs,
                features_ref,
                store.as_ref(),
                &mut *rng,
                cfg,
                // EDGE-P3-1 A5: serialize full 17-dim vector for shadow-fill
                // JSONB payload. Lazy closure — cost only paid on ε-greedy branch.
                // EDGE-P3-1 A5：lazy 序列化完整 17 維 feature；僅 ε-greedy 分支付代價。
                || features_ref.to_jsonb(),
            )
        };

        // W-AUDIT-4b-M1：把 outcome 字串化（V082 §CHECK enum）寫 evaluation log
        let (outcome_str, evidence_tier) = match &outcome {
            PredictorGateOutcome::Accept => ("accept", "evaluation_log"),
            PredictorGateOutcome::Reject(_) => ("reject", "evaluation_log"),
            PredictorGateOutcome::RejectAdd(_) => ("reject_add", "evaluation_log"),
            PredictorGateOutcome::ShadowFill(_) => ("shadow_fill", "shadow_synthetic"),
            PredictorGateOutcome::Fallback(_) => match cfg.fallback_on_error {
                EdgePredictorFallback::Shrinkage => ("fallback_use_legacy", "evaluation_log"),
                EdgePredictorFallback::FailClosed => ("fallback_fail_closed", "evaluation_log"),
            },
        };
        self.try_emit_evaluation_log(
            intent,
            features,
            context_id,
            now_ms,
            outcome_str,
            evidence_tier,
        );

        if cfg.shadow_mode {
            tracing::debug!(
                strategy = %intent.strategy, symbol = %intent.symbol,
                ?outcome, "edge_predictor: shadow_mode — observation, JS gate decides / shadow 模式觀察"
            );
            return PredictorAction::UseLegacyGate;
        }

        match outcome {
            PredictorGateOutcome::Accept => PredictorAction::SkipLegacyGate,
            PredictorGateOutcome::Reject(reason) => PredictorAction::Reject(reason),
            PredictorGateOutcome::RejectAdd(reason) => PredictorAction::Reject(reason),
            PredictorGateOutcome::ShadowFill(payload) => {
                self.emit_shadow_fill(payload);
                PredictorAction::Reject(
                    "predictor_epsilon_greedy_exploration: paper shadow-fill dispatched".into(),
                )
            }
            PredictorGateOutcome::Fallback(reason) => self.apply_fallback(reason),
        }
    }

    /// EDGE-P3-1 A4: Emit an `EmitShadowFill` IPC command; drops fail-soft on
    /// missing tx or closed channel.
    /// EDGE-P3-1 A4：發送 `EmitShadowFill` IPC；tx 缺失/關閉則 fail-soft 丟棄。
    fn emit_shadow_fill(&self, payload: ShadowFillPayload) {
        let tx = match self.shadow_fill_tx.as_ref() {
            Some(t) => t,
            None => {
                tracing::warn!(
                    strategy = %payload.strategy, symbol = %payload.symbol,
                    "edge_predictor: ShadowFill dropped — no tx wired / 無 tx 丟棄 shadow fill"
                );
                return;
            }
        };
        let cmd = PipelineCommand::EmitShadowFill {
            context_id: payload.context_id,
            strategy: payload.strategy,
            symbol: payload.symbol,
            side: payload.side,
            features_jsonb: payload.features_jsonb,
            prediction_q10: payload.prediction_q10,
            prediction_q50: payload.prediction_q50,
            prediction_q90: payload.prediction_q90,
            cost_bps: payload.cost_bps,
            ts_ms: payload.ts_ms,
        };
        if let Err(e) = tx.send(cmd) {
            tracing::warn!(err = %e,
                "edge_predictor: EmitShadowFill send failed / 發送失敗");
        }
    }

    /// EDGE-P3-1 Step 7a + W-AUDIT-4b-M1 split (V082)：推送一條
    /// `DecisionFeatureMsg` 到 production `learning.decision_features` writer
    /// task。**現為 intent-only emit**：caller (tick_pipeline 的 step_4_5_dispatch)
    /// 於 success path（result.submitted）才呼叫；evaluate_predictor_gate 內
    /// 不再呼叫此 method（改寫 evaluation log 通道）。
    ///
    /// 用 `try_send` 避免意圖循環被 DB 背壓阻塞；通道滿 → best-effort drop + warn。
    /// tx 未接線時靜默 no-op（fail-soft）。
    ///
    /// Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
    ///       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
    pub(crate) fn emit_decision_feature_intent_emitted(
        &self,
        intent: &OrderIntent,
        features: &FeatureVectorV1,
        context_id: &str,
        now_ms: u64,
    ) {
        let tx = match self.decision_feature_tx.as_ref() {
            Some(t) => t,
            None => return, // fail-soft no-op
        };
        // Skip obviously invalid timestamps to match DB-RUN-6 rejection policy
        // at the writer side — avoids emitting rows the writer will drop anyway.
        // 與 writer DB-RUN-6 對齊：無效時間戳不發射，節省通道容量。
        if now_ms == 0 {
            tracing::warn!(
                ctx_id = %context_id, symbol = %intent.symbol,
                "decision_feature snapshot skipped: now_ms=0 / 時間戳 0，跳過"
            );
            return;
        }

        let msg = crate::database::DecisionFeatureMsg {
            context_id: context_id.to_string(),
            ts_ms: now_ms,
            engine_mode: self.effective_engine_mode().to_string(),
            strategy_name: intent.strategy.clone(),
            symbol: intent.symbol.clone(),
            side: if intent.is_long { 1 } else { -1 },
            feature_schema_version: crate::edge_predictor::features::FEATURE_SCHEMA_VERSION
                .to_string(),
            feature_schema_hash: crate::edge_predictor::features::feature_schema_hash().to_string(),
            feature_definition_hash: crate::edge_predictor::features::feature_definition_hash()
                .to_string(),
            features_jsonb: features.to_jsonb(),
            // M1 success path：label 三欄全 None / false，由 backfill 補。
            label_close_tag: None,
            label_net_edge_bps: None,
            label_filled_at_now: false,
            // ── W6-3c V086 reject/close_reason_code 兩欄 intent-only path 全 None ──
            // 後續 close 走 backfill (`edge_label_backfill.py`) 或下游 W6-3d Python 端寫
            // close_reason_code 並 dual-write 到此 column。
            reject_reason_code: None,
            close_reason_code: None,
        };

        if let Err(e) = tx.try_send(msg) {
            tracing::warn!(
                ctx_id = %context_id, symbol = %intent.symbol, error = %e,
                "decision_feature snapshot drop — writer channel full/closed \
                 / 特徵快照丟棄，writer 通道已滿/關閉"
            );
        }
    }

    /// W-AUDIT-4b-M3 (2026-05-09)：在 governance / cost-gate reject path 推送
    /// 一條帶 negative label 的 `DecisionFeatureMsg` 到
    /// `learning.decision_features` writer task。Mirror
    /// `emit_decision_feature_intent_emitted` 但 carry 三 label 欄位：
    ///   - `label_close_tag = "rejected_governance"`
    ///   - `label_net_edge_bps = 0.0`（reject 沒成交）
    ///   - `label_filled_at_now = true`（writer 用 server-side NOW() 寫
    ///     `label_filled_at`，避免用 emit 時間戳造成 backfill 語意混淆）
    ///
    /// Caller 為 tick_pipeline `step_4_5_dispatch` 三 reject path：
    ///   1. pre_risk reject（`per_strategy_new_entry_rejection`，demo / live_demo）
    ///   2. exchange gate reject（`gate.rejected_reason`）
    ///   3. paper gate reject（`result.rejected_reason`）
    ///
    /// 安全策略：與 `emit_decision_feature_intent_emitted` 對齊：
    ///   - tx 未接線 → 靜默 no-op（fail-soft，不影響交易）
    ///   - now_ms = 0 → 跳過（DB-RUN-6 epoch leak 防線）
    ///   - try_send 滿 → best-effort drop + warn
    ///
    /// 動機：M1 land 後 24h 12,681 intent 中只 175 fill (1.38%) 寫
    /// `learning.decision_features`；98.6% reject path 完全沒寫 → ML training
    /// pool 70× 偏差 + attribution_chain_ok ratio 0.5%。M3 補 reject path 寫
    /// negative label + V084 sample_weight UDF 配套，恢復 70:1 imbalance。
    ///
    /// `reject_reason` 當前**不入 schema**（V017 鎖死），保留參數方便未來
    /// extend；當前作為 audit trail 寫 verdict_writer trace（非 schema 改動）。
    ///
    /// Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
    ///       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M3
    pub(crate) fn emit_decision_feature_intent_rejected(
        &self,
        intent: &OrderIntent,
        features: &FeatureVectorV1,
        context_id: &str,
        now_ms: u64,
        reject_reason: &str,
    ) {
        let tx = match self.decision_feature_tx.as_ref() {
            Some(t) => t,
            None => return, // fail-soft no-op
        };
        // 與 writer DB-RUN-6 對齊：無效時間戳不發射，節省通道容量。
        if now_ms == 0 {
            tracing::warn!(
                ctx_id = %context_id, symbol = %intent.symbol,
                "decision_feature reject snapshot skipped: now_ms=0 / 時間戳 0，跳過"
            );
            return;
        }
        // 空 context_id 不發射（防孤兒 row）。
        if context_id.is_empty() {
            tracing::warn!(
                symbol = %intent.symbol,
                "decision_feature reject snapshot skipped: empty context_id / 空 ctx_id，跳過"
            );
            return;
        }

        // ── W6-3c V086 (2026-05-10): reject_reason_code producer-side mapping ──
        // reject_reason: &str → V086 §4.1 12 enum 之一；無匹配走 'reject_other'。
        // evaluation order 鏡像 V086 SQL backfill CASE WHEN（line 316-333），E2 必驗。
        // close_reason_code 在 reject path 永遠 None（與 V086 §3 互斥不變式對齊）。
        let reject_code = map_reject_reason_to_code(reject_reason);

        let msg = crate::database::DecisionFeatureMsg {
            context_id: context_id.to_string(),
            ts_ms: now_ms,
            engine_mode: self.effective_engine_mode().to_string(),
            strategy_name: intent.strategy.clone(),
            symbol: intent.symbol.clone(),
            side: if intent.is_long { 1 } else { -1 },
            feature_schema_version: crate::edge_predictor::features::FEATURE_SCHEMA_VERSION
                .to_string(),
            feature_schema_hash: crate::edge_predictor::features::feature_schema_hash().to_string(),
            feature_definition_hash: crate::edge_predictor::features::feature_definition_hash()
                .to_string(),
            features_jsonb: features.to_jsonb(),
            // ── W-AUDIT-4b-M3 negative label payload ──
            label_close_tag: Some("rejected_governance".to_string()),
            label_net_edge_bps: Some(0.0),
            label_filled_at_now: true,
            // ── W6-3c V086 reject_reason_code（12 enum）+ close_reason_code（None for reject path）──
            reject_reason_code: Some(reject_code.to_string()),
            close_reason_code: None,
        };

        if let Err(e) = tx.try_send(msg) {
            tracing::warn!(
                ctx_id = %context_id, symbol = %intent.symbol,
                reason = %reject_reason, error = %e,
                "decision_feature reject snapshot drop — writer channel full/closed \
                 / 拒絕特徵快照丟棄，writer 通道已滿/關閉"
            );
        } else {
            tracing::debug!(
                ctx_id = %context_id, symbol = %intent.symbol,
                strategy = %intent.strategy, reason = %reject_reason,
                "decision_feature reject snapshot emitted (negative label) \
                 / 拒絕特徵快照已發送（負樣本）"
            );
        }
    }

    /// W-AUDIT-4b-M1 split (V082)：對每次 evaluate_predictor_gate 評估發射
    /// 一條 `DecisionFeatureEvaluationMsg` 到 evaluation log 通道
    /// (`learning.decision_features_evaluations`)。
    ///
    /// 與 `emit_decision_feature_intent_emitted` 不同：
    ///   - 對應每次 gate 評估（無論 outcome），不論 intent 是否真實 emit
    ///   - 無 dedup（BIGSERIAL PK），同 context_id 可多次寫
    ///   - 攜 `evaluation_outcome` + `evidence_source_tier`
    ///   - **不可作 ML training data**（pool 含 reject path 污染）
    ///
    /// 安全策略：與 `emit_decision_feature_intent_emitted` 對齊：
    ///   - tx 未接線 → 靜默 no-op（fail-soft）
    ///   - features=None → 跳過（無 jsonb）
    ///   - context_id 空 → 跳過
    ///   - now_ms=0 → 跳過（DB-RUN-6 epoch leak）
    ///   - try_send 滿 → best-effort drop + warn
    ///
    /// Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
    ///       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
    fn try_emit_evaluation_log(
        &self,
        intent: &OrderIntent,
        features: Option<&FeatureVectorV1>,
        context_id: &str,
        now_ms: u64,
        evaluation_outcome: &str,
        evidence_source_tier: &str,
    ) {
        let tx = match self.decision_feature_evaluation_tx.as_ref() {
            Some(t) => t,
            None => return, // fail-soft no-op
        };
        // 短路：無 features / 空 context_id / epoch 0
        let features = match features {
            Some(f) => f,
            None => return,
        };
        if context_id.is_empty() {
            return;
        }
        if now_ms == 0 {
            tracing::warn!(
                ctx_id = %context_id, symbol = %intent.symbol,
                "decision_feature_evaluation skipped: now_ms=0 / 時間戳 0，跳過"
            );
            return;
        }

        let msg = crate::database::DecisionFeatureEvaluationMsg {
            context_id: context_id.to_string(),
            ts_ms: now_ms,
            engine_mode: self.effective_engine_mode().to_string(),
            strategy_name: intent.strategy.clone(),
            symbol: intent.symbol.clone(),
            side: if intent.is_long { 1 } else { -1 },
            feature_schema_version: crate::edge_predictor::features::FEATURE_SCHEMA_VERSION
                .to_string(),
            feature_schema_hash: crate::edge_predictor::features::feature_schema_hash().to_string(),
            feature_definition_hash: crate::edge_predictor::features::feature_definition_hash()
                .to_string(),
            features_jsonb: features.to_jsonb(),
            evaluation_outcome: evaluation_outcome.to_string(),
            evidence_source_tier: evidence_source_tier.to_string(),
            // M1 producer 一律 None；M2 trigger 才回填
            entry_context_id: None,
        };

        if let Err(e) = tx.try_send(msg) {
            tracing::warn!(
                ctx_id = %context_id, symbol = %intent.symbol, error = %e,
                "decision_feature_evaluation drop — writer channel full/closed \
                 / 評估 log 丟棄，writer 通道已滿/關閉"
            );
        }
    }

    /// W-AUDIT-8a Phase B B-4：panel 不可用時寫 producer-debug evaluation row。
    ///
    /// 這條路徑發生在 strategy 尚未形成真實 OrderIntent 前，因此 side=0、
    /// features_jsonb 使用最小診斷 payload。`panel_fail_closed` tier 和
    /// `oi_panel_unavailable` outcome 由 V093 allowlist 擴展；evaluations
    /// 表仍是 non-training surface。
    pub(crate) fn emit_panel_unavailable_evaluation(
        &self,
        strategy_name: &str,
        symbol: &str,
        now_ms: u64,
        panel_name: &str,
        reason: &str,
    ) {
        let tx = match self.decision_feature_evaluation_tx.as_ref() {
            Some(t) => t,
            None => return,
        };
        if strategy_name.is_empty() || symbol.is_empty() || now_ms == 0 {
            return;
        }

        let context_id = format!("panel_fail_closed:{strategy_name}:{symbol}:{now_ms}");
        let features_jsonb = serde_json::json!({
            "panel": panel_name,
            "reason": reason,
            "strategy_name": strategy_name,
            "symbol": symbol
        })
        .to_string();
        let msg = crate::database::DecisionFeatureEvaluationMsg {
            context_id,
            ts_ms: now_ms,
            engine_mode: self.effective_engine_mode().to_string(),
            strategy_name: strategy_name.to_string(),
            symbol: symbol.to_string(),
            side: 0,
            feature_schema_version: "panel_fail_closed_v1".to_string(),
            feature_schema_hash: crate::edge_predictor::features::feature_schema_hash().to_string(),
            feature_definition_hash: crate::edge_predictor::features::feature_definition_hash()
                .to_string(),
            features_jsonb,
            evaluation_outcome: "oi_panel_unavailable".to_string(),
            evidence_source_tier: "panel_fail_closed".to_string(),
            entry_context_id: None,
        };

        if let Err(e) = tx.try_send(msg) {
            tracing::warn!(
                strategy = %strategy_name,
                symbol = %symbol,
                panel = %panel_name,
                error = %e,
                "panel unavailable evaluation drop — writer channel full/closed \
                 / panel 不可用評估 log 丟棄，writer 通道已滿/關閉"
            );
        }
    }

    /// EDGE-P3-1 A4 · spec §7.4: apply first-level Fallback policy.
    /// Shrinkage → UseLegacyGate; FailClosed → Reject with metric-name suffix.
    /// EDGE-P3-1 A4 · §7.4：第一級 Fallback 策略。
    fn apply_fallback(&self, reason: FallbackReason) -> PredictorAction {
        let metric = reason.metric_name();
        match self.risk_config.edge_predictor.fallback_on_error {
            EdgePredictorFallback::Shrinkage => {
                tracing::info!(
                    fallback_reason = metric,
                    "edge_predictor: fallback → shrinkage gate / 回退 JS shrinkage"
                );
                PredictorAction::UseLegacyGate
            }
            EdgePredictorFallback::FailClosed => {
                tracing::warn!(
                    fallback_reason = metric,
                    "edge_predictor: fail-closed rejection / fail-closed 拒絕"
                );
                PredictorAction::Reject(format!("predictor_fallback_fail_closed:{}", metric))
            }
        }
    }

    /// Effective taker fee rate for a symbol. Resolution order:
    ///   1. Live `AccountManager.taker_fee(symbol)` (Bybit API, refreshed hourly)
    ///   2. Legacy single-rate fallback (`taker_fee_rate`)
    ///   3. `DEFAULT_TAKER_FEE_RATE` constant (cold-boot before API responds)
    /// 有效 taker 費率（per-symbol）。優先序：API → legacy → 常量。
    pub fn fee_rate(&self, symbol: &str) -> f64 {
        if let Some(ref am) = self.account_manager {
            return am.taker_fee(symbol);
        }
        self.taker_fee_rate.unwrap_or(DEFAULT_TAKER_FEE_RATE)
    }

    /// Effective maker fee rate for a symbol. Resolution order:
    ///   1. Live `AccountManager.maker_fee(symbol)` (Bybit API, refreshed hourly)
    ///   2. `DEFAULT_MAKER_FEE_RATE` constant (cold-boot before API responds)
    /// EDGE-P2-3 Phase 1a: Separate maker path from taker so cost estimates
    /// for PostOnly/Limit entries reflect the ~5× lower fee.
    /// 有效 maker 費率（per-symbol）：API → 常量。
    pub fn maker_fee_rate(&self, symbol: &str) -> f64 {
        if let Some(ref am) = self.account_manager {
            return am.maker_fee(symbol);
        }
        DEFAULT_MAKER_FEE_RATE
    }

    /// Pick maker vs taker fee based on the intent's TimeInForce. PostOnly
    /// means the order will only rest on book (maker); anything else pays taker.
    /// EDGE-P2-3 Phase 1a：依 TIF 選擇 maker/taker 費率。PostOnly→maker，其餘→taker。
    pub fn fee_rate_for_intent(&self, symbol: &str, intent: &OrderIntent) -> f64 {
        self.fee_rate_for_tif(symbol, intent.time_in_force)
    }

    /// Estimate slippage for cost gates. PostOnly maker orders rest on the book,
    /// so do not add the taker-style turnover slippage tier on top of maker
    /// fees; maker execution quality is tracked separately by MakerKpi.
    /// 成本門滑點估計。PostOnly maker 掛單不再疊加 taker-style turnover 滑點；
    /// maker 執作品質由 MakerKpi 另行監控。
    pub(crate) fn slippage_rate_for_intent(&self, intent: &OrderIntent, volume_24h: f64) -> f64 {
        self.slippage_rate_for_tif(intent.time_in_force, volume_24h)
    }

    pub(crate) fn slippage_rate_for_tif(
        &self,
        tif: Option<crate::order_manager::TimeInForce>,
        volume_24h: f64,
    ) -> f64 {
        if matches!(tif, Some(crate::order_manager::TimeInForce::PostOnly)) {
            0.0
        } else {
            lookup_slippage(&self.risk_config.slippage, volume_24h)
        }
    }

    /// Pick maker vs taker fee from a raw TimeInForce. Used on the fill path
    /// (`event_consumer/loop_handlers.rs`) where only `&PendingOrder` is
    /// available, not `&OrderIntent`. `None` falls back to taker: a Bybit Fill
    /// event can arrive before OrderUpdate has populated `order_id_to_link`,
    /// so matched_key lookup may fail and TIF is unknown — degrading to
    /// current pre-fix behaviour is safe (accounts fee at taker rate, which
    /// is the more conservative estimate for PnL).
    /// FIX-FEE-POSTONLY-1 (G7-09)：從原始 TIF 選費率；fill 路徑 race
    /// (Fill 先於 OrderUpdate) → TIF=None → taker 保本。
    pub fn fee_rate_for_tif(
        &self,
        symbol: &str,
        tif: Option<crate::order_manager::TimeInForce>,
    ) -> f64 {
        if matches!(tif, Some(crate::order_manager::TimeInForce::PostOnly)) {
            self.maker_fee_rate(symbol)
        } else {
            self.fee_rate(symbol)
        }
    }
}

impl Default for IntentProcessor {
    fn default() -> Self {
        Self::new()
    }
}
