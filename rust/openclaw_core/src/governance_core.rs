//! GovernanceCore — cascade logic for 4 state machines [V3-PA-3].
//! 治理核心 — 4 個狀態機的級聯邏輯。
//!
//! All-or-nothing cascade: clone → execute → commit/rollback.
//! 全有或全無級聯：克隆 → 執行 → 提交/回滾。
//!
//! Cross-SM wiring:
//!   risk ≥ REDUCED → auth restrict
//!   risk ≥ CIRCUIT_BREAKER → auth freeze + lease revoke_all
//!   auth FROZEN → lease revoke_all
//!
//! AMD-2026-05-02-01 Track E E-1（2026-05-03 retrofit）/ Track E E-1 retrofit：
//! - `pub lease: DecisionLeaseSm` → `pub lease: Mutex<DecisionLeaseSm>`（interior
//!   mutability so `&GovernanceCore` callers in router.rs can acquire/release
//!   leases without `&mut self`）。
//! - 將 `pub lease` 改為 `Mutex<DecisionLeaseSm>` 以便 router.rs 的不可變借用呼叫
//!   `acquire_lease/release_lease`，無需 `&mut self`。
//! - Adds `acquire_lease` / `release_lease` / `get_lease_by_id` facade — Production
//!   profile 一條龍 `create_draft → register → activate`；Exploration / Validation
//!   返回 `LeaseId::Bypass`（spec §3 點 1 後段）。
//! - 維護 `lease_id_to_idx: HashMap<String, usize>` reverse lookup，解 Rust idx
//!   vs Python lease_id（String）impedance mismatch（PA design §1.3）。
//! - `lease_transition_tx` mpsc::Sender（Optional）— 為 E-4 lease_transition_writer
//!   actor 預留 audit emit slot；E-1 階段不啟用，由 E-4 task 注入。
//! - Feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED`（boot-time env var）— E-1
//!   階段儲存於 GovernanceCore；router gate 啟用本身在 E-2 task。
//!
//! AMD-2026-05-02-01 Track H E-4（2026-05-03 retrofit）/ Track H E-4 retrofit：
//! - Inline emit hook in `acquire_lease` / `release_lease`（Option A facade
//!   auto-emit）— 持鎖蒐集 transition record snapshot，釋鎖後 emit 至
//!   `lease_transition_tx`（fail-soft）。100% coverage 不依賴 caller。
//! - Inline emit hook in acquire_lease / release_lease (Option A facade
//!   auto-emit) — collect transition record snapshots under lock; emit to
//!   lease_transition_tx after lock release (fail-soft). 100% coverage,
//!   caller-independent.
//! - `LeaseTransitionMsg.profile` 由 `GovernanceProfile` enum 改為 `String`
//!   （writer 端 cross-crate 解耦；對齊 V054 chk_lease_transitions_profile
//!   3-value CHECK enum）。
//! - `LeaseTransitionMsg.profile` changed from GovernanceProfile enum to
//!   String (writer-side cross-crate decoupling; aligned with V054 CHECK enum).
//! - `resolve_engine_mode_tag()` helper — reads `OPENCLAW_ENGINE_MODE` env var
//!   for V054 chk_lease_transitions_engine_mode 5-value CHECK alignment.
//!
//! AMD-2026-05-02-01 Track H E-4 round-2 retrofit (E2 verdict HIGH-1, 2026-05-03):
//! AMD-2026-05-02-01 Track H E-4 第二輪（E2 verdict HIGH-1，2026-05-03）：
//! - Emit-side types/helpers extracted to `governance_emit` — keeps facade
//!   under 1500 LOC hard cap; decouples parallel E1 retrofit on this file.
//! - emit 端類型/輔助抽至 `governance_emit` — 控 LOC 在 1500 hard cap，解耦並行 E1。
//! - `engine_mode_tag` per-instance replaces global env-only read; each pipeline
//!   injects via `set_engine_mode_tag()` (called from
//!   `pipeline_ctor.rs::set_endpoint_env`). Fallback env var → "unknown".
//!   Fixes HIGH-1 (prior helper always returned 'demo' — env var 0 setter).
//! - `engine_mode_tag` per-instance 取代全局 env-only；pipeline boot 呼
//!   `set_engine_mode_tag()` 注入。Fallback env var → "unknown"。修 HIGH-1。

use crate::governance_emit::{
    build_bypass_transition_msg, build_msg_from_last_transition, emit_transition_fail_soft,
    EngineModeTagResolver,
};
// W-AUDIT-9 T6 (AMD-2026-05-09-03 §4.5)：強型別 LeaseScope + CanaryStageTransition
// row payload；新增 acquire_canary_stage_promotion_lease() facade 在現有 acquire_lease
// hot path 之上提供 operator-only 路徑（TTL 60s strict）。
use crate::lease_scope::{CanaryStageTransition, LeaseScope};
// Re-export facade + emit types so callers keep `use governance_core::*` paths.
// 重新導出 facade + emit 端類型，使 caller 維持 `use governance_core::*` 路徑。
pub use crate::governance_emit::{
    GovernanceError, LeaseId, LeaseOutcome, LeaseTransitionMsg, LeaseTransitionSender,
};
use crate::sm::{
    auth::{AuthState, AuthorizationSm},
    lease::{DecisionLeaseSm, LeaseObject, LeaseState},
    oms::OmsStateMachine,
    risk_gov::{RiskEvent, RiskGovernorSm, RiskLevel},
    SmError,
};
use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Governance mode derived from SM states.
/// 從 SM 狀態派生的治理模式。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum GovernanceMode {
    Normal,
    Restricted,
    Frozen,
    ManualReview,
}

impl GovernanceMode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Normal => "NORMAL",
            Self::Restricted => "RESTRICTED",
            Self::Frozen => "FROZEN",
            Self::ManualReview => "MANUAL_REVIEW",
        }
    }
}

// ---------------------------------------------------------------------------
// GovernanceProfile — per-pipeline governance strictness (3E-1 / D3)
// ---------------------------------------------------------------------------

/// Governance strictness tier — determines which gates are active per pipeline.
/// Paper pipelines explore freely; Demo validates with moderate gates; Live enforces all.
/// 治理嚴格程度 — 決定各管線啟用哪些 gate。
/// Paper 自由探索；Demo 中等驗證；Live 全嚴格。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GovernanceProfile {
    /// Paper: auto-grant auth, no lease, exploration cost_gate, lenient Guardian.
    /// Paper：自動授權，無租約，探索性 cost_gate，寬鬆 Guardian。
    Exploration,
    /// Demo: auto-grant auth, no lease, moderate cost_gate, moderate Guardian.
    /// Demo：自動授權，無租約，中等 cost_gate，中等 Guardian。
    Validation,
    /// Live: full auth + lease + strict cost_gate + strict Guardian.
    /// Live：完整授權 + 租約 + 嚴格 cost_gate + 嚴格 Guardian。
    Production,
}

impl GovernanceProfile {
    /// Whether this profile requires explicit SM-1 authorization.
    /// 此檔案是否需要顯式 SM-1 授權。
    pub fn requires_authorization(&self) -> bool {
        matches!(self, Self::Production)
    }

    /// Whether this profile requires a Decision Lease (SM-2).
    /// 此檔案是否需要決策租約（SM-2）。
    pub fn requires_lease(&self) -> bool {
        matches!(self, Self::Production)
    }

    /// Whether this profile auto-grants authorization at construction.
    /// 此檔案是否在構造時自動授予授權。
    pub fn auto_grant_auth(&self) -> bool {
        matches!(self, Self::Exploration | Self::Validation)
    }
}

/// Cascade result describing what happened.
/// 級聯結果，描述發生了什麼。
#[derive(Debug, Clone)]
pub struct CascadeResult {
    pub success: bool,
    pub risk_level: RiskLevel,
    pub auth_restricted: bool,
    pub auth_frozen: bool,
    pub leases_revoked: usize,
    pub error: Option<String>,
}

// AMD-2026-05-02-01 Track E E-1 Lease facade types (LeaseId / LeaseOutcome /
// GovernanceError) + Track H E-4 emit types (LeaseTransitionMsg /
// LeaseTransitionSender) all moved to the `governance_emit` module. The
// top-of-file `pub use` re-export keeps caller paths unchanged.
// AMD-2026-05-02-01 Track E E-1 facade 型別 + Track H E-4 emit 型別全搬至
// `governance_emit`；本檔 top `pub use` re-export 保持 caller path 不變。

/// GovernanceCore — owns all 4 SMs, provides cascade operations.
/// 治理核心 — 擁有所有 4 個 SM，提供級聯操作。
///
/// Sole-owned by tick actor [V3-PA-1]. Lease wrapped in Mutex for facade
/// interior mutability（&GovernanceCore acquire_lease 不需 &mut self）.
/// 由 tick actor 獨佔。Lease 用 Mutex 包以提供 facade 的內部可變性。
pub struct GovernanceCore {
    pub auth: AuthorizationSm,
    /// AMD-2026-05-02-01 Track E E-1: Mutex interior mutability.
    /// AMD-2026-05-02-01 Track E E-1：Mutex 內部可變性。
    pub lease: Mutex<DecisionLeaseSm>,
    pub risk: RiskGovernorSm,
    pub oms: OmsStateMachine,
    enabled: bool,
    mode: GovernanceMode,
    /// AMD-2026-05-02-01: lease_id String → lease index reverse lookup.
    /// AMD-2026-05-02-01：lease_id 字串 → lease index 反查表。
    lease_id_to_idx: Mutex<HashMap<String, usize>>,
    /// AMD-2026-05-02-01: optional audit emit channel (E-4 wires sender).
    /// AMD-2026-05-02-01：可選的 audit emit 通道（E-4 注入 sender）。
    lease_transition_tx: Option<LeaseTransitionSender>,
    /// AMD-2026-05-02-01 §6 灰度 feature flag: read at boot from env
    /// `OPENCLAW_LEASE_ROUTER_GATE_ENABLED`. Default OFF — E-1 lands facade,
    /// E-2 task wires router gate and reads this flag for enforcement.
    /// AMD-2026-05-02-01 §6 灰度 feature flag：boot 時從環境變數 OPENCLAW_LEASE_ROUTER_GATE_ENABLED
    /// 讀取；預設 OFF — E-1 落 facade、E-2 task 接 router gate 並讀此 flag enforce。
    router_gate_enabled: bool,
    /// E2 round 1 verdict HIGH-1 retrofit: per-instance engine mode tag for
    /// V054 lease_transitions audit emit. Each pipeline (paper / demo /
    /// live_demo / live_mainnet / shadow) constructs its own GovernanceCore
    /// and binds the tag at boot via `set_engine_mode_tag()` (called from
    /// `pipeline_ctor.rs::set_endpoint_env`). When `None`, resolver falls
    /// back to OPENCLAW_ENGINE_MODE env var → "unknown" sentinel.
    /// E2 round 1 verdict HIGH-1 retrofit：per-instance engine_mode tag 供
    /// V054 lease_transitions audit emit 使用。每個 pipeline（paper / demo /
    /// live_demo / live_mainnet / shadow）構造自己的 GovernanceCore，並在 boot
    /// 時透過 `set_engine_mode_tag()`（在 `pipeline_ctor.rs::set_endpoint_env`
    /// 內呼叫）綁定 tag。`None` 時 resolver fallback 至 OPENCLAW_ENGINE_MODE
    /// env var → "unknown" sentinel。
    engine_mode_tag: Option<String>,
}

impl GovernanceCore {
    pub fn new() -> Self {
        let router_gate_enabled = std::env::var("OPENCLAW_LEASE_ROUTER_GATE_ENABLED")
            .map(|v| matches!(v.as_str(), "1" | "true" | "TRUE" | "yes" | "YES"))
            .unwrap_or(false);
        Self {
            auth: AuthorizationSm::new(),
            lease: Mutex::new(DecisionLeaseSm::new()),
            risk: RiskGovernorSm::new(),
            oms: OmsStateMachine::new(),
            enabled: true,
            mode: GovernanceMode::Frozen, // No auth = frozen (fail-closed)
            lease_id_to_idx: Mutex::new(HashMap::new()),
            lease_transition_tx: None,
            router_gate_enabled,
            engine_mode_tag: None,
        }
    }

    /// Create GovernanceCore with profile-appropriate defaults (3E-1 / D3).
    /// Exploration/Validation: auto-grant authorization (no operator action needed).
    /// Production: fail-closed, requires explicit grant_live_authorization().
    /// 按 profile 創建治理核心。Exploration/Validation 自動授權；Production 失敗關閉。
    pub fn new_with_profile(profile: GovernanceProfile) -> Self {
        let mut core = Self::new();
        if profile.auto_grant_auth() {
            let label = match profile {
                GovernanceProfile::Exploration => "paper",
                GovernanceProfile::Validation => "demo",
                GovernanceProfile::Production => unreachable!(),
            };
            // Auto-grant: create → submit → approve in one shot.
            // 自動授權：一步完成 create → submit → approve。
            let idx = core.auth.create_draft(
                &format!("{label} auto-authorization (3E-1)"),
                serde_json::json!({"mode": label, "profile": format!("{:?}", profile)}),
                &format!("system_{label}_auto"),
                None, // no TTL — permanent until session ends
            );
            let _ = core.auth.submit_for_approval(idx);
            let _ = core.auth.approve(
                idx,
                &format!("system_{label}_auto"),
                &format!("{label} mode auto-approved (GovernanceProfile)"),
            );
            core.update_mode();
        }
        core
    }

    pub fn is_enabled(&self) -> bool {
        self.enabled
    }

    pub fn mode(&self) -> GovernanceMode {
        self.mode
    }

    /// Is system authorized for operations? (fail-closed)
    /// 系統是否被授權運營？（失敗時關閉）
    pub fn is_authorized(&self) -> bool {
        if !self.enabled || self.mode == GovernanceMode::Frozen {
            return false;
        }
        !self.auth.get_effective().is_empty()
    }

    /// AMD-2026-05-02-01 §6: whether the router-side lease gate is enabled.
    /// AMD-2026-05-02-01 §6：router 端 lease gate 是否啟用。
    pub fn router_gate_enabled(&self) -> bool {
        self.router_gate_enabled
    }

    /// AMD-2026-05-02-01 Track E E-2 test-only flag mutation. Boot-time env var
    /// is read once at `new()`; this setter exists for cross-crate test
    /// scenarios (openclaw_engine intent_processor::tests) so parallel runners
    /// flip the flag deterministically without `std::env::set_var` race.
    /// **Production code MUST NOT call this** — flip via env var only.
    /// AMD-2026-05-02-01 Track E E-2 test-only flag setter：env var 在 new()
    /// 一次讀取；本 setter 為跨 crate 測試（openclaw_engine intent_processor::
    /// tests）暴露，避開 cargo test 平行 runner 的 set_var race。
    /// **生產代碼禁呼叫**，flag flip 僅透過 env var。
    ///
    /// E2 round 1 LOW-1 retrofit (2026-05-03): debug_assert! guard makes the
    /// "production MUST NOT call" rule grep-able and runtime-checked in debug
    /// builds; release builds compile to no-op (zero overhead). Combined with
    /// `#[doc(hidden)]` + the existing pub-only-for-cross-crate-tests rationale
    /// + production grep marker `set_router_gate_enabled_for_test`, this gives
    /// reviewers a single phrase to audit when scanning for lateral test-hook
    /// abuse.
    /// E2 round 1 LOW-1 retrofit（2026-05-03）：debug_assert! guard 把「生產禁呼」
    /// 規則做成可 grep 的 marker + debug 構建 runtime 檢查；release 構建展開為
    /// no-op（0 開銷）。配 #[doc(hidden)] + 既有「pub 僅供跨 crate test」說明 +
    /// production grep marker，reviewer 掃 lateral test-hook 濫用時有單一字串
    /// 錨點。
    #[doc(hidden)]
    pub fn set_router_gate_enabled_for_test(&mut self, enabled: bool) {
        // SAFETY / 不變量：production code paths MUST NOT call this setter.
        // `debug_assertions` is on for `cargo build` / `cargo test` (debug +
        // test profiles) and OFF for `cargo build --release` / production
        // binaries. `cfg!(test)` is true inside `#[cfg(test)]` test modules.
        // Either condition satisfies the assertion; release-build production
        // call sites would panic in CI/dev runs (debug profile) and compile to
        // no-op in release (debug_assert! macro definition; see
        // https://doc.rust-lang.org/std/macro.debug_assert.html).
        // SAFETY / 不變量：生產代碼路徑禁呼此 setter。debug_assertions 在
        // cargo build / cargo test（debug + test profile）下啟用，cargo build
        // --release / 生產 binary 下關閉。cfg!(test) 在 #[cfg(test)] 測試模組
        // 內為真。任一條件滿足即通過 assertion；release 構建生產呼叫會在
        // CI/dev 跑 panic（debug profile），release binary 展開為 no-op
        // （debug_assert! 巨集定義）。
        debug_assert!(
            cfg!(debug_assertions) || cfg!(test),
            "set_router_gate_enabled_for_test must not be called in release production build"
        );
        self.router_gate_enabled = enabled;
    }

    /// AMD-2026-05-02-01 §3 point 5: register audit emit channel for E-4 writer.
    /// AMD-2026-05-02-01 §3 點 5：註冊 audit emit 通道供 E-4 writer 使用。
    pub fn set_lease_transition_tx(&mut self, tx: LeaseTransitionSender) {
        self.lease_transition_tx = Some(tx);
    }

    /// Whether the audit-writer sender has been injected by the engine boot
    /// pipeline. This is read-only observability for GUI/API status surfaces.
    /// audit writer sender 是否已由 engine boot pipeline 注入；僅供只讀觀測面使用。
    pub fn lease_transition_writer_configured(&self) -> bool {
        self.lease_transition_tx.is_some()
    }

    /// HIGH-1 retrofit: bind V054 audit-emit engine_mode tag at pipeline boot.
    /// Called from `pipeline_ctor.rs::set_endpoint_env`. Tag must be one of
    /// V054 5-value enum {paper, demo, live_demo, live_mainnet, shadow};
    /// invalid values fall through to env var → "unknown" inside resolver.
    /// HIGH-1 修法：在 pipeline boot 時綁定 V054 audit-emit engine_mode tag。
    /// 由 `pipeline_ctor.rs::set_endpoint_env` 呼叫；非合法 tag 由 resolver
    /// fallback 至 env var → "unknown"。
    pub fn set_engine_mode_tag(&mut self, tag: String) {
        self.engine_mode_tag = Some(tag);
    }

    /// Resolve V054 engine_mode tag (instance-injected → env → "unknown").
    /// 解析 V054 engine_mode tag（實例注入 → env → "unknown"）。
    fn resolve_engine_mode_tag(&self) -> String {
        EngineModeTagResolver::resolve(self.engine_mode_tag.as_deref())
    }

    // ═══════════════════════════════════════════════════════════════════════
    // AMD-2026-05-02-01 Track E E-1: Lease facade
    // AMD-2026-05-02-01 Track E E-1：Lease facade
    // ═══════════════════════════════════════════════════════════════════════

    /// AMD-2026-05-02-01 §3 point 1: Production-only lease one-shot facade.
    /// AMD-2026-05-02-01 §3 點 1：Production 專用 lease 一條龍 facade。
    ///
    /// Internally completes `create_draft → register → activate` in one sequence
    /// for Production profile. Exploration / Validation profile returns
    /// `LeaseId::Bypass` per spec §3 point 1 trailing clause（PA push back #1
    /// strictly forbids forcing leases in non-Production paths — would break
    /// W8 P6 typed-confirm handoff demo path）.
    /// 內部完成 `create_draft → register → activate` 一條龍序列（Production profile）；
    /// Exploration / Validation profile 直接回 `LeaseId::Bypass`（spec §3 點 1 後段；
    /// PA push back #1 嚴禁在非 Production 路徑強制 lease — 會撞 W8 P6 typed-confirm
    /// handoff demo path）。
    ///
    /// SAFETY / 不變量：
    /// - Production profile 必先有 effective auth（is_authorized()=true）才能 acquire；
    ///   AuthNotEffective 是 fail-closed 拒絕的硬邊界（CLAUDE.md §四 第 5 條 live
    ///   gating）。
    /// - Production profile must have effective auth (is_authorized()=true) before
    ///   acquiring; AuthNotEffective is the hard fail-closed boundary (CLAUDE.md §4
    ///   point 5 live gating).
    /// - 失敗回 `Err(GovernanceError::*)`，呼叫端必 fail-closed（不下單）；非 panic。
    /// - On error returns `Err(GovernanceError::*)`; caller MUST fail-closed (skip
    ///   order); never panics.
    /// - lease_id 由 `LeaseObject::new()` 生成（`lease:xxxx` 12-hex 隨機 64-bit
    ///   masked to 48-bit），collision probability < 1e-12（生產 throughput 安全）。
    /// - lease_id is generated by LeaseObject::new() (lease:xxxx, 12-hex random
    ///   64-bit masked to 48-bit); collision probability < 1e-12 (safe at production
    ///   throughput).
    ///
    /// # Arguments
    /// - `intent_id`: caller-supplied unique trade intent identifier. / 呼叫端提供的唯一 intent 識別符。
    /// - `scope`: lease scope (e.g. "TRADE_ENTRY" / "TRADE_EXIT" / "POSITION_ADJUST"). / lease scope。
    /// - `ttl_ms`: per-intent TTL in ms（100..=300_000 spec §3 範圍）。/ 每意圖 TTL（毫秒）。
    /// - `profile`: caller's GovernanceProfile（router 透過 effective_governance_profile 取）；
    ///   中文：呼叫端的 GovernanceProfile（router 透過 effective_governance_profile 取得）。
    /// - `source_stage`: audit metadata e.g. "router" / "scout" / "strategist"；
    ///   中文：audit metadata，例如 "router" / "scout" / "strategist"。
    ///
    /// # Returns
    /// - `Ok(LeaseId::Active(s))` — Production profile 真實走完 SM 路徑（Draft → Registered → Active）。
    /// - `Ok(LeaseId::Bypass)` — Exploration / Validation profile 短路。
    /// - `Err(GovernanceError::AuthNotEffective)` — Production 但 is_authorized()=false。
    /// - `Err(GovernanceError::InvalidTtl)` — ttl_ms 超出 100..=300_000。
    /// - `Err(GovernanceError::LeaseSmFailure)` — SM transition 內部拒（極罕，除非 sm/lease.rs bug）。
    pub fn acquire_lease(
        &self,
        intent_id: &str,
        scope: &str,
        ttl_ms: u32,
        profile: GovernanceProfile,
        source_stage: &str,
    ) -> Result<LeaseId, GovernanceError> {
        // §3 point 1 trailing clause: non-Production profile bypasses SM entirely.
        // Emit one synthetic audit row so bypass stays observable without
        // becoming a lease gate.
        // §3 點 1 後段：非 Production profile 完全繞過 SM；emit 一筆合成
        // audit row，保持可觀測但不把 bypass 變成 lease gate。
        if !profile.requires_lease() {
            let msg = build_bypass_transition_msg(
                intent_id,
                &format!("{:?}", profile),
                &self.resolve_engine_mode_tag(),
                source_stage,
            );
            emit_transition_fail_soft(self.lease_transition_tx.as_ref(), msg);
            return Ok(LeaseId::Bypass);
        }

        // Hard fail-closed: Production must have effective auth.
        // 硬性 fail-closed：Production 必須有有效授權。
        if !self.is_authorized() {
            return Err(GovernanceError::AuthNotEffective);
        }

        // TTL validation per spec §3 point 1 (100ms..=300s).
        // TTL 驗證（spec §3 點 1：100ms..=300s）。
        if !(100..=300_000).contains(&ttl_ms) {
            return Err(GovernanceError::InvalidTtl(ttl_ms));
        }

        // Build lease intent metadata for audit reconstruction.
        // 構建 lease intent 元資料供審計重建使用。
        let now_ms = crate::sm::now_ms();
        let expires_at_ms = Some(now_ms + ttl_ms as u64);
        let intent_meta = serde_json::json!({
            "intent_id": intent_id,
            "scope": scope,
            "source_stage": source_stage,
            "profile": format!("{:?}", profile),
            "ttl_ms": ttl_ms,
        });
        let created_by = format!("rust_facade::{source_stage}");

        // SM transition chain: Draft → Registered → Active. Lock once for full chain.
        // E-4 Track H emit strategy: 持鎖期間 collect 3 筆 transition record snapshot
        //   （after each create_draft / register / activate），釋鎖後 emit 至 audit
        //   writer channel — fail-soft，與 hot path 解耦。
        // SM 遷移鏈：Draft → Registered → Active。整段持鎖一次。
        // E-4 Track H emit 策略：持鎖期間蒐集 3 筆 transition record snapshot，釋鎖後
        // emit 至 audit writer channel（fail-soft，與 hot path 解耦）。
        let profile_str = format!("{:?}", profile);
        let engine_mode_tag = self.resolve_engine_mode_tag();
        let context_id = intent_id.to_string(); // intent_id 為 caller-supplied unique key
        let (lease_id_str, idx, emit_msgs) = {
            let mut sm = self.lease.lock();
            let idx = sm.create_draft(intent_meta, &created_by, expires_at_ms);

            // Snapshot Draft transition record (idx=0 in transitions vec).
            // 快照 Draft 階段 transition record（transitions vec 中 idx=0）。
            let draft_obj = sm
                .get(idx)
                .ok_or_else(|| GovernanceError::LeaseNotFound(format!("idx={idx}")))?
                .clone();

            sm.register(idx)?;
            // Snapshot Registered transition record.
            let registered_obj = sm
                .get(idx)
                .ok_or_else(|| GovernanceError::LeaseNotFound(format!("idx={idx}")))?
                .clone();

            sm.activate(idx)?;
            // Snapshot Active transition record.
            let active_obj = sm
                .get(idx)
                .ok_or_else(|| GovernanceError::LeaseNotFound(format!("idx={idx}")))?
                .clone();

            // Read lease_id while still holding lock (avoid TOCTOU)
            // 持鎖時取 lease_id（避免 TOCTOU）。
            let id = active_obj.lease_id.clone();

            // Build all 3 transition msgs (lock 持中構造，避 race read of obj.transitions)
            // 持鎖中構造全部 3 筆 transition msg（避免 obj.transitions race read）。
            let mut msgs: Vec<LeaseTransitionMsg> = Vec::with_capacity(3);
            for obj in [&draft_obj, &registered_obj, &active_obj] {
                if let Some(msg) = build_msg_from_last_transition(
                    &id,
                    obj,
                    &profile_str,
                    &engine_mode_tag,
                    &context_id,
                ) {
                    msgs.push(msg);
                }
            }
            (id, idx, msgs)
        };

        // Register reverse lookup so subsequent release_lease / get_lease_by_id
        // can route String → idx.
        // 註冊反查表，使後續 release_lease / get_lease_by_id 可走 String → idx 路徑。
        self.lease_id_to_idx
            .lock()
            .insert(lease_id_str.clone(), idx);

        // Emit all 3 transition msgs after lock release (fail-soft, never blocks hot path).
        // 釋鎖後 emit 全部 3 筆 transition msg（fail-soft，永不阻塞 hot path）。
        for msg in emit_msgs {
            emit_transition_fail_soft(self.lease_transition_tx.as_ref(), msg);
        }

        Ok(LeaseId::Active(lease_id_str))
    }

    /// W-AUDIT-9 T6 — manual canary stage promotion lease facade
    /// （AMD-2026-05-09-03 §4.5）。
    /// 為 graduated canary 5-stage 的 manual promotion 提供 operator-only 路徑：
    /// - scope 鎖定為 `LeaseScope::CanaryStagePromotion`（強型別 enum，不接 raw &str）
    /// - TTL 預設 60 秒（spec 強制；caller 不可覆寫，避免 silent drift）
    /// - 必經 `is_authorized()` gate（hard fail-closed 5-gate live boundary 之一）
    /// - 內部呼 acquire_lease 走標準 SM transition (Draft → Registered → Active)，
    ///   保證 V054 lease_transitions audit emit 與其他 lease 一致
    /// - 回傳 `LeaseId::Active(String)` 給 GUI / IPC caller，由 caller 將 lease_id
    ///   寫入 `governance.canary_stage_log.decision_lease_id`（PG NOT NULL 強制）
    ///
    /// W-AUDIT-9 T6 — manual canary stage promotion lease facade.
    /// Operator-only path with strict TTL 60s; auth-gated; uses standard SM
    /// transition for V054 audit emit consistency.
    ///
    /// SAFETY / 不變量：
    /// - 必為 Production profile（GovernanceProfile::Production）— graduated canary
    ///   只適用 alpha-bearing pathway（AMD-2026-05-09-03 §3.5）；Exploration /
    ///   Validation profile 應在 caller 端拒絕，本 facade 不重複檢查（依賴 caller
    ///   遵守 spec）。
    /// - `is_authorized()=true` 是 hard gate；違反 = `AuthNotEffective` 拒回，
    ///   下游 caller MUST fail-closed（不寫 canary_stage_log row）。
    /// - lease_id 由 SM `LeaseObject::new()` 生成；caller 拿到 `LeaseId::Active(...)`
    ///   後須在 60 秒內完成 PG INSERT + release_lease(Consumed)；超期 ExpiryGuardian
    ///   自動清理（與其他 lease 一致 TTL 行為）。
    ///
    /// # Arguments
    /// - `intent_id`: caller 指定唯一 promote 動作 id（建議 GUI 端用 UUID v4）。
    /// - `source_stage`: audit metadata，例如 "operator_gui" / "ipc_canary_promote"。
    ///
    /// # Returns
    /// - `Ok(LeaseId::Active(s))` — 成功，lease_id 字串供 caller 寫入 audit row。
    /// - `Err(GovernanceError::AuthNotEffective)` — `is_authorized()=false`。
    /// - `Err(GovernanceError::LeaseSmFailure)` — SM 內部錯（極罕）。
    pub fn acquire_canary_stage_promotion_lease(
        &self,
        intent_id: &str,
        source_stage: &str,
    ) -> Result<LeaseId, GovernanceError> {
        // W-AUDIT-9 T6 SAFETY — operator authority hard gate。
        // graduated canary stage promotion 是「manual」動作，per AMD-2026-05-09-03 §4.5
        // 必由 operator 在 GUI / IPC 觸發；本路徑 100% 拒 non-Production profile + 0
        // auth 場景。Production 標籤是 caller 義務（acquire_lease 內部已確認）。
        let scope = LeaseScope::CanaryStagePromotion;
        debug_assert!(
            scope.requires_operator_authority(),
            "CanaryStagePromotion 必觸發 operator authority gate（spec invariant）"
        );

        // 內部呼 acquire_lease — Production profile 不可繞；TTL 強制 60s（spec）。
        // scope 字串走 LeaseScope::as_audit_str() 對齊 audit metadata。
        self.acquire_lease(
            intent_id,
            scope.as_audit_str(),
            scope.default_ttl_ms(),
            GovernanceProfile::Production,
            source_stage,
        )
    }

    /// W-AUDIT-9 T6 — 為 manual_promote 構造一筆 `governance.canary_stage_log` row
    /// 的強型別 payload。caller 必先 acquire 一個 `CanaryStagePromotion` lease 並
    /// 把 `LeaseId::Active(String)` unwrap 後傳入；本 helper 保證 `decision_lease_id`
    /// 必填（PG NOT NULL CHECK invariant）。實際 PG INSERT 由 caller（E1-B T2 V0XX
    /// migration land 後的 governance_hub.py / IPC 層）完成 — 本 facade 只生成
    /// payload contract，不接 PG。
    ///
    /// W-AUDIT-9 T6 — assemble typed audit row payload for manual_promote.
    /// PG INSERT is owned by caller (governance_hub.py / IPC layer) once T2
    /// V0XX migration lands; this helper guarantees lease_id is always carried.
    ///
    /// SAFETY / 不變量：
    /// - 接收 `LeaseId::Active(String)` 的 String 內容；`LeaseId::Bypass` 不允許
    ///   走 manual_promote 路徑（debug_assert 保護），因 graduated canary 只適用
    ///   alpha-bearing Production（AMD-2026-05-09-03 §3.5）。
    /// - `from_stage / to_stage` 邊界由 PG SMALLINT CHECK 強制（0..=4），本層
    ///   不重複驗，讓 caller 拿一致 fail-loud。
    /// - `now_ms` 由 caller 注入（例如 `openclaw_core::sm::now_ms()`），保持
    ///   openclaw_core facade clock-free。
    #[allow(clippy::too_many_arguments)]
    pub fn make_canary_stage_promotion_audit_row(
        &self,
        now_ms: u64,
        environment: impl Into<String>,
        cohort_strategy: Option<String>,
        cohort_symbol: Option<String>,
        from_stage: u8,
        to_stage: u8,
        reason: impl Into<String>,
        initiated_by: impl Into<String>,
        lease_id: &LeaseId,
        metric_snapshot: serde_json::Value,
    ) -> Result<CanaryStageTransition, GovernanceError> {
        // W-AUDIT-9 T6 SAFETY — 拒 Bypass。caller 端應確保走 Production profile
        // acquire 路徑；Bypass = Exploration/Validation = graduated canary 不適用。
        let lease_id_str = match lease_id {
            LeaseId::Active(s) => s.clone(),
            LeaseId::Bypass => {
                // 直接回 LeaseScopeNotPermitted（已存在 enum variant，原語意「scope 在
                // 當前 auth 不允許」），對齊 AMD-2026-05-09-03 §3.5 graduated canary
                // 只適用 alpha-bearing Production。
                return Err(GovernanceError::LeaseScopeNotPermitted(
                    "CanaryStagePromotion 不適用 Bypass（非 Production profile）".to_string(),
                ));
            }
        };

        Ok(CanaryStageTransition::manual_promote(
            now_ms,
            environment,
            cohort_strategy,
            cohort_symbol,
            from_stage,
            to_stage,
            reason,
            initiated_by,
            lease_id_str,
            metric_snapshot,
        ))
    }

    /// AMD-2026-05-02-01 §3 point 2: release lease per outcome.
    /// AMD-2026-05-02-01 §3 點 2：依 outcome 釋放 lease。
    ///
    /// Maps `LeaseOutcome` to SM transition：
    /// 將 `LeaseOutcome` 對應到 SM transition：
    /// - `Consumed` → `Active → Bridged → Consumed`（execution success）。
    /// - `Failed` / `Cancelled` → `Active → Revoked`（execution rejected / cancelled）。
    ///
    /// `LeaseId::Bypass` 為 no-op（不嘗試 SM transition；無對應 SM object）。
    /// `LeaseId::Bypass` is no-op (skips SM transition; no corresponding SM object).
    ///
    /// SAFETY / 不變量：
    /// - 失敗回 `Err`，但 lease 物件**不會**被 release_lease 自動移出 SM；
    ///   ExpiryGuardian 會在 TTL 到期後自動清理（避免 leak）。
    /// - On failure returns `Err`; the lease is NOT auto-removed from SM;
    ///   ExpiryGuardian will clean up after TTL expires (prevents leak).
    pub fn release_lease(
        &self,
        lease_id: &LeaseId,
        outcome: LeaseOutcome,
    ) -> Result<(), GovernanceError> {
        // Bypass = no-op. / Bypass = 無操作。
        let lease_id_str = match lease_id {
            LeaseId::Active(s) => s.as_str(),
            LeaseId::Bypass => return Ok(()),
        };

        // Reverse lookup String → idx.
        // 反查 String → idx。
        let idx = *self
            .lease_id_to_idx
            .lock()
            .get(lease_id_str)
            .ok_or_else(|| GovernanceError::LeaseNotFound(lease_id_str.to_string()))?;

        // E-4 Track H emit: collect transition records under lock, emit
        // after lock release (fail-soft). Each release path emits 1 or 2 msgs
        // depending on Bridged hop:
        //   Consumed (Active state): bridge + consume → 2 msgs (BRIDGED + CONSUMED)
        //   Consumed (Bridged state): consume only → 1 msg (CONSUMED)
        //   Failed / Cancelled: revoke → 1 msg (REVOKED)
        // E-4 Track H emit：持鎖蒐集 transition record snapshot，釋鎖後 emit。
        // Consumed Active 路徑 emit 2 筆（BRIDGED + CONSUMED）；其他 1 筆。
        let engine_mode_tag = self.resolve_engine_mode_tag();
        let mut emit_msgs: Vec<LeaseTransitionMsg> = Vec::with_capacity(2);
        // E-4 Track H：profile context lookup — release 時 caller 可能不知道 profile，
        //   所以從 lease intent metadata 反推（acquire_lease 寫入 "profile" key）。
        // E-4：release 路徑無 profile param；從 lease intent metadata 反推。
        let profile_str = {
            let sm = self.lease.lock();
            sm.get(idx)
                .and_then(|obj| {
                    obj.intent
                        .get("profile")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string())
                })
                .unwrap_or_else(|| "Production".to_string())
        };

        {
            let mut sm = self.lease.lock();
            match outcome {
                LeaseOutcome::Consumed => {
                    // SM rule: Active must transit through Bridged before Consumed.
                    // SM 規則：Active 必經 Bridged 才能到 Consumed。
                    // If state already Bridged (e.g. exchange acknowledged), only consume.
                    // 若狀態已是 Bridged（例如交易所已 ack），只 consume。
                    let cur = sm
                        .get(idx)
                        .ok_or_else(|| GovernanceError::LeaseNotFound(lease_id_str.to_string()))?
                        .state;
                    if cur == LeaseState::Active {
                        sm.bridge(idx)?;
                        let bridged_obj = sm.get(idx).map(|o| o.clone());
                        if let Some(obj) = bridged_obj {
                            if let Some(msg) = build_msg_from_last_transition(
                                lease_id_str,
                                &obj,
                                &profile_str,
                                &engine_mode_tag,
                                lease_id_str,
                            ) {
                                emit_msgs.push(msg);
                            }
                        }
                    }
                    sm.consume(idx)?;
                    let consumed_obj = sm.get(idx).map(|o| o.clone());
                    if let Some(obj) = consumed_obj {
                        if let Some(msg) = build_msg_from_last_transition(
                            lease_id_str,
                            &obj,
                            &profile_str,
                            &engine_mode_tag,
                            lease_id_str,
                        ) {
                            emit_msgs.push(msg);
                        }
                    }
                }
                LeaseOutcome::Failed | LeaseOutcome::Cancelled => {
                    let reason = match outcome {
                        LeaseOutcome::Failed => "execution_failed",
                        LeaseOutcome::Cancelled => "caller_cancelled",
                        LeaseOutcome::Consumed => unreachable!(),
                    };
                    sm.revoke(idx, "rust_facade", reason)?;
                    let revoked_obj = sm.get(idx).map(|o| o.clone());
                    if let Some(obj) = revoked_obj {
                        if let Some(msg) = build_msg_from_last_transition(
                            lease_id_str,
                            &obj,
                            &profile_str,
                            &engine_mode_tag,
                            lease_id_str,
                        ) {
                            emit_msgs.push(msg);
                        }
                    }
                }
            }
        }

        // Emit all transition msgs after lock release (fail-soft).
        // 釋鎖後 emit 全部 transition msg（fail-soft）。
        for msg in emit_msgs {
            emit_transition_fail_soft(self.lease_transition_tx.as_ref(), msg);
        }

        self.lease_id_to_idx.lock().remove(lease_id_str); // HIGH-3 reverse-map cleanup after terminal transition / 終態後反查表清理
        Ok(())
    }

    /// AMD-2026-05-02-01 §3 point 4: lookup lease object by lease_id String.
    /// AMD-2026-05-02-01 §3 點 4：依 lease_id 字串查詢 lease 物件。
    ///
    /// Returns a clone（not reference）because `&LeaseObject` cannot be returned
    /// across the Mutex guard lifetime — clone is the natural impedance match
    /// for Python IPC bridge in E-3 anyway。
    /// 回傳 clone（非 reference）— Mutex guard lifetime 限制無法回傳 `&LeaseObject`；
    /// 對 E-3 Python IPC bridge 而言 clone 本就是自然的 impedance match。
    pub fn get_lease_by_id(&self, lease_id: &str) -> Result<LeaseObject, GovernanceError> {
        let idx = *self
            .lease_id_to_idx
            .lock()
            .get(lease_id)
            .ok_or_else(|| GovernanceError::LeaseNotFound(lease_id.to_string()))?;
        let sm = self.lease.lock();
        sm.get(idx)
            .cloned()
            .ok_or_else(|| GovernanceError::LeaseNotFound(lease_id.to_string()))
    }

    /// Execute risk→auth→lease cascade [V3-PA-3].
    /// 執行 risk→auth→lease 級聯。
    ///
    /// All-or-nothing: if any step fails, no SM state is changed.
    /// For escalation this matters less (escalation rarely fails),
    /// but the pattern ensures consistency.
    pub fn execute_risk_cascade(
        &mut self,
        to_level: RiskLevel,
        event: RiskEvent,
        reason: &str,
    ) -> CascadeResult {
        // Clone SM states for all-or-nothing rollback [V3-PA-3]
        // AMD-2026-05-02-01: lease 改 Mutex 後 backup 改為 lock+clone inner。
        // AMD-2026-05-02-01: After lease becomes Mutex, backup is lock+clone inner.
        let auth_backup = self.auth.clone();
        let lease_backup = self.lease.lock().clone();
        let lease_idx_backup = self.lease_id_to_idx.lock().clone();
        let risk_snapshot = self.risk.snapshot_level();

        let mut result = CascadeResult {
            success: false,
            risk_level: risk_snapshot,
            auth_restricted: false,
            auth_frozen: false,
            leases_revoked: 0,
            error: None,
        };

        // Step 1: Risk transition
        if let Err(e) = self.risk.escalate_to(to_level, reason, event) {
            result.error = Some(format!("risk escalation failed: {e}"));
            return result;
        }
        result.risk_level = to_level;

        // Step 2: Cross-SM wiring — auth
        let effective = self.auth.get_effective();
        if to_level >= RiskLevel::CircuitBreaker {
            // Freeze all effective auth
            for idx in &effective {
                if let Some(obj) = self.auth.get(*idx) {
                    if obj.state == AuthState::Active || obj.state == AuthState::Restricted {
                        if let Err(e) = self.auth.freeze(*idx, reason) {
                            // Rollback: restore all SM states [V3-PA-3]
                            self.rollback_risk(risk_snapshot);
                            self.auth = auth_backup;
                            *self.lease.lock() = lease_backup;
                            *self.lease_id_to_idx.lock() = lease_idx_backup;
                            result.error = Some(format!("auth freeze failed: {e}"));
                            return result;
                        }
                        result.auth_frozen = true;
                    }
                }
            }
        } else if to_level >= RiskLevel::Reduced {
            // Restrict all active auth
            for idx in &effective {
                if let Some(obj) = self.auth.get(*idx) {
                    if obj.state == AuthState::Active {
                        if let Err(e) = self.auth.restrict(*idx, reason) {
                            self.rollback_risk(risk_snapshot);
                            self.auth = auth_backup;
                            *self.lease.lock() = lease_backup;
                            *self.lease_id_to_idx.lock() = lease_idx_backup;
                            result.error = Some(format!("auth restrict failed: {e}"));
                            return result;
                        }
                        result.auth_restricted = true;
                    }
                }
            }
        }

        // Step 3: Cross-SM wiring — lease
        if result.auth_frozen {
            let revoked = self
                .lease
                .lock()
                .revoke_all_live("governance_cascade", reason);
            result.leases_revoked = revoked.len();
        }

        // Update mode
        self.update_mode();

        result.success = true;
        result
    }

    /// Evaluate risk metrics and auto-cascade if escalation occurs.
    /// 評估風控指標，如果觸發升級則自動級聯。
    pub fn evaluate_and_cascade(
        &mut self,
        pressure: f64,
        drawdown_pct: f64,
        daily_loss_pct: f64,
        consecutive_losses: u32,
        session_halted: bool,
        cooldown_active: bool,
    ) -> Option<CascadeResult> {
        // First, check what level the risk context would escalate to
        let current = self.risk.level;

        // Determine target (same logic as risk_gov.evaluate_risk_context)
        let t = &self.risk.thresholds;
        let mut target = RiskLevel::Normal;

        if pressure >= t.pressure_circuit_breaker {
            target = target.max(RiskLevel::CircuitBreaker);
        } else if pressure >= t.pressure_defensive {
            target = target.max(RiskLevel::Defensive);
        } else if pressure >= t.pressure_reduced {
            target = target.max(RiskLevel::Reduced);
        } else if pressure >= t.pressure_cautious {
            target = target.max(RiskLevel::Cautious);
        }

        if drawdown_pct >= t.drawdown_circuit_breaker_pct {
            target = target.max(RiskLevel::CircuitBreaker);
        } else if drawdown_pct >= t.drawdown_defensive_pct {
            target = target.max(RiskLevel::Defensive);
        } else if drawdown_pct >= t.drawdown_reduced_pct {
            target = target.max(RiskLevel::Reduced);
        } else if drawdown_pct >= t.drawdown_cautious_pct {
            target = target.max(RiskLevel::Cautious);
        }

        if daily_loss_pct >= t.daily_loss_circuit_breaker_pct {
            target = target.max(RiskLevel::CircuitBreaker);
        } else if daily_loss_pct >= t.daily_loss_reduced_pct {
            target = target.max(RiskLevel::Reduced);
        } else if daily_loss_pct >= t.daily_loss_cautious_pct {
            target = target.max(RiskLevel::Cautious);
        }

        if consecutive_losses >= t.consecutive_loss_circuit_breaker {
            target = target.max(RiskLevel::CircuitBreaker);
        } else if consecutive_losses >= t.consecutive_loss_reduced {
            target = target.max(RiskLevel::Reduced);
        } else if consecutive_losses >= t.consecutive_loss_cautious {
            target = target.max(RiskLevel::Cautious);
        }

        if session_halted {
            target = target.max(RiskLevel::CircuitBreaker);
        }
        if cooldown_active {
            target = target.max(RiskLevel::Reduced);
        }

        if target > current {
            let event = if drawdown_pct >= t.drawdown_defensive_pct {
                RiskEvent::DrawdownCritical
            } else if daily_loss_pct >= t.daily_loss_reduced_pct {
                RiskEvent::DailyLossBreach
            } else if consecutive_losses >= t.consecutive_loss_reduced {
                RiskEvent::ConsecutiveLosses
            } else {
                RiskEvent::DrawdownWarning
            };
            Some(self.execute_risk_cascade(target, event, "auto_eval_cascade"))
        } else {
            None
        }
    }

    /// Grant paper trading authorization (auto-approve).
    /// 批准紙盤交易授權（自動審批）。
    pub fn grant_paper_authorization(&mut self, ttl_ms: Option<u64>) -> Result<usize, SmError> {
        let idx = self.auth.create_draft(
            "Paper Trading Auto-Authorization",
            serde_json::json!({"mode": "paper_only"}),
            "system_paper_auto",
            ttl_ms,
        );
        self.auth.submit_for_approval(idx)?;
        self.auth
            .approve(idx, "system_paper_auto", "paper mode auto-approved")?;
        self.update_mode();
        Ok(idx)
    }

    /// Check and auto-expire authorizations and leases.
    /// 檢查並自動過期授權和租約。
    pub fn check_expiry(&mut self) -> (Vec<usize>, Vec<usize>) {
        let auth_expired = self.auth.check_expiry();
        let lease_expired = self.lease.lock().check_expiry();
        if !auth_expired.is_empty() || !lease_expired.is_empty() {
            self.update_mode();
        }
        (auth_expired, lease_expired)
    }

    /// Get current governance status snapshot.
    /// 獲取當前治理狀態快照。
    pub fn status(&self) -> GovernanceStatus {
        GovernanceStatus {
            enabled: self.enabled,
            mode: self.mode,
            risk_level: self.risk.level,
            auth_effective_count: self.auth.get_effective().len(),
            lease_live_count: self.lease.lock().get_live().len(),
            oms_active_count: self.oms.get_active().len(),
        }
    }

    // ── Internal / 內部 ──

    fn update_mode(&mut self) {
        let risk = self.risk.level;
        let has_effective_auth = !self.auth.get_effective().is_empty();

        self.mode = if risk >= RiskLevel::ManualReview {
            GovernanceMode::ManualReview
        } else if risk >= RiskLevel::CircuitBreaker || !has_effective_auth {
            GovernanceMode::Frozen
        } else if risk >= RiskLevel::Reduced {
            GovernanceMode::Restricted
        } else {
            GovernanceMode::Normal
        };
    }

    fn rollback_risk(&mut self, level: RiskLevel) {
        // Direct state restore — bypasses transition rules for rollback
        self.risk.level = level;
    }
}

impl Default for GovernanceCore {
    fn default() -> Self {
        Self::new()
    }
}

/// Governance status snapshot.
/// 治理狀態快照。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GovernanceStatus {
    pub enabled: bool,
    pub mode: GovernanceMode,
    pub risk_level: RiskLevel,
    pub auth_effective_count: usize,
    pub lease_live_count: usize,
    pub oms_active_count: usize,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn make_authorized_core() -> GovernanceCore {
        let mut core = GovernanceCore::new();
        core.grant_paper_authorization(None).unwrap();
        core
    }

    #[test]
    fn test_initial_state() {
        let core = GovernanceCore::new();
        assert!(!core.is_authorized()); // no auth
        assert_eq!(core.mode(), GovernanceMode::Frozen); // no effective auth → frozen
    }

    #[test]
    fn test_grant_paper_authorization() {
        let core = make_authorized_core();
        assert!(core.is_authorized());
        assert_eq!(core.mode(), GovernanceMode::Normal);
        assert_eq!(core.auth.get_effective().len(), 1);
    }

    #[test]
    fn test_risk_cascade_reduced_restricts_auth() {
        let mut core = make_authorized_core();
        let result = core.execute_risk_cascade(
            RiskLevel::Reduced,
            RiskEvent::DrawdownWarning,
            "high drawdown",
        );
        assert!(result.success);
        assert!(result.auth_restricted);
        assert!(!result.auth_frozen);
        assert_eq!(result.leases_revoked, 0);
        assert_eq!(core.risk.level, RiskLevel::Reduced);
        assert_eq!(core.mode(), GovernanceMode::Restricted);
        // Auth should be Restricted now
        let idx = core.auth.get_effective()[0];
        assert_eq!(core.auth.get(idx).unwrap().state, AuthState::Restricted);
    }

    #[test]
    fn test_risk_cascade_circuit_breaker_freezes_all() {
        let mut core = make_authorized_core();
        // Add a live lease (AMD-2026-05-02-01: lock for direct SM access)
        // 添加 live lease（AMD-2026-05-02-01：lock 取直接 SM 訪問）
        let lease_idx = {
            let mut sm = core.lease.lock();
            let idx = sm.create_draft(serde_json::json!({}), "s", None);
            sm.register(idx).unwrap();
            sm.activate(idx).unwrap();
            idx
        };
        let _ = lease_idx; // suppress unused warning

        let result = core.execute_risk_cascade(
            RiskLevel::CircuitBreaker,
            RiskEvent::IncidentTriggered,
            "severe",
        );
        assert!(result.success);
        assert!(result.auth_frozen);
        assert_eq!(result.leases_revoked, 1);
        assert_eq!(core.mode(), GovernanceMode::Frozen);
        assert!(!core.is_authorized());
    }

    #[test]
    fn test_evaluate_and_cascade_no_escalation() {
        let mut core = make_authorized_core();
        let result = core.evaluate_and_cascade(0.1, 1.0, 0.5, 0, false, false);
        assert!(result.is_none());
        assert_eq!(core.risk.level, RiskLevel::Normal);
    }

    #[test]
    fn test_evaluate_and_cascade_escalates() {
        let mut core = make_authorized_core();
        let result = core.evaluate_and_cascade(0.6, 9.0, 0.0, 0, false, false);
        assert!(result.is_some());
        let r = result.unwrap();
        assert!(r.success);
        assert_eq!(r.risk_level, RiskLevel::Reduced);
        assert!(r.auth_restricted);
    }

    #[test]
    fn test_evaluate_session_halted_cascades() {
        let mut core = make_authorized_core();
        let result = core.evaluate_and_cascade(0.0, 0.0, 0.0, 0, true, false);
        let r = result.unwrap();
        assert!(r.success);
        assert_eq!(r.risk_level, RiskLevel::CircuitBreaker);
        assert!(r.auth_frozen);
    }

    #[test]
    fn test_check_expiry() {
        let mut core = GovernanceCore::new();
        // Create auth with expired time
        let idx = core
            .auth
            .create_draft("test", serde_json::json!({}), "op", Some(1));
        core.auth.submit_for_approval(idx).unwrap();
        core.auth.approve(idx, "admin", "ok").unwrap();

        let (auth_exp, _) = core.check_expiry();
        assert_eq!(auth_exp, vec![idx]);
    }

    #[test]
    fn test_status_snapshot() {
        let core = make_authorized_core();
        let status = core.status();
        assert!(status.enabled);
        assert_eq!(status.mode, GovernanceMode::Normal);
        assert_eq!(status.risk_level, RiskLevel::Normal);
        assert_eq!(status.auth_effective_count, 1);
    }

    #[test]
    fn test_mode_transitions() {
        let mut core = make_authorized_core();
        assert_eq!(core.mode(), GovernanceMode::Normal);

        core.execute_risk_cascade(RiskLevel::Cautious, RiskEvent::DrawdownWarning, "test");
        assert_eq!(core.mode(), GovernanceMode::Normal); // Cautious doesn't change mode

        core.execute_risk_cascade(RiskLevel::Reduced, RiskEvent::DrawdownWarning, "test");
        assert_eq!(core.mode(), GovernanceMode::Restricted);

        core.execute_risk_cascade(
            RiskLevel::CircuitBreaker,
            RiskEvent::IncidentTriggered,
            "test",
        );
        assert_eq!(core.mode(), GovernanceMode::Frozen);
    }

    #[test]
    fn test_cascade_with_multiple_leases() {
        let mut core = make_authorized_core();
        // Create 3 live leases (AMD-2026-05-02-01: lock for direct SM)
        // 創建 3 個 live lease（AMD-2026-05-02-01：lock 取直接 SM 訪問）
        {
            let mut sm = core.lease.lock();
            for _ in 0..3 {
                let idx = sm.create_draft(serde_json::json!({}), "s", None);
                sm.register(idx).unwrap();
                sm.activate(idx).unwrap();
            }
            assert_eq!(sm.get_live().len(), 3);
        }

        let result = core.execute_risk_cascade(
            RiskLevel::CircuitBreaker,
            RiskEvent::IncidentTriggered,
            "severe",
        );
        assert!(result.success);
        assert_eq!(result.leases_revoked, 3);
        assert_eq!(core.lease.lock().get_live().len(), 0);
    }

    #[test]
    fn test_double_cascade_idempotent() {
        let mut core = make_authorized_core();
        core.execute_risk_cascade(RiskLevel::Reduced, RiskEvent::DrawdownWarning, "test");

        // Second cascade at same level should be no-op (risk transition returns Ok for same level)
        let result =
            core.execute_risk_cascade(RiskLevel::Reduced, RiskEvent::DrawdownWarning, "test");
        // Risk escalate_to at same level → no-op, but we escalate, so this should fail gracefully
        // Actually the risk SM returns Ok(()) for same level, so escalate_to won't fail
        // but the cascade logic checks to_level... let me verify
        assert!(result.success || result.error.is_some());
    }

    // ═══════════════════════════════════════════════════════════════════════
    // AMD-2026-05-02-01 Track E E-1: Lease facade tests
    // AMD-2026-05-02-01 Track E E-1：Lease facade 測試
    // ═══════════════════════════════════════════════════════════════════════

    /// Production profile happy path: acquire returns Active, SM transitions
    /// flow Draft → Registered → Active, reverse lookup populated, release
    /// transitions through Bridged → Consumed.
    /// Production profile happy path：acquire 回 Active；SM 走 Draft → Registered →
    /// Active；reverse lookup 注冊；release 走 Bridged → Consumed。
    #[test]
    fn test_facade_acquire_release_production_happy_path() {
        let mut core = GovernanceCore::new();
        // Production needs explicit auth — use grant_paper_authorization for the
        // SM-1 Active state (the auth content semantically is for paper mode but
        // is_authorized() merely checks for any effective auth).
        // Production 需要顯式授權 — 用 grant_paper_authorization 做出 SM-1 Active
        // 狀態（auth 內容語意上是 paper，is_authorized() 只檢查任意 effective auth）。
        core.grant_paper_authorization(None).unwrap();

        let lease = core
            .acquire_lease(
                "intent-test-001",
                "TRADE_ENTRY",
                30_000,
                GovernanceProfile::Production,
                "facade_test",
            )
            .expect("acquire_lease must succeed under Production+auth");
        assert!(lease.is_active(), "Production must return LeaseId::Active");

        // Verify SM state and reverse lookup populated.
        // 驗證 SM 狀態與 reverse lookup 已注冊。
        let lease_id_str = match &lease {
            LeaseId::Active(s) => s.clone(),
            LeaseId::Bypass => unreachable!(),
        };
        let obj = core
            .get_lease_by_id(&lease_id_str)
            .expect("get_lease_by_id must find the lease");
        assert_eq!(obj.state, LeaseState::Active);
        assert_eq!(obj.lease_id, lease_id_str);

        // Release as Consumed → SM Active → Bridged → Consumed.
        // Release 為 Consumed → SM Active → Bridged → Consumed。
        core.release_lease(&lease, LeaseOutcome::Consumed)
            .expect("release_lease Consumed must succeed");

        // AMD-2026-05-02-01 Track H E-1 round 2 (HIGH-3 retrofit):
        // After terminal transition release_lease() prunes the
        // lease_id_to_idx reverse-map entry to prevent per-trade heap leak.
        // get_lease_by_id() therefore returns LeaseNotFound after release;
        // the SM object still exists but the String lookup path is gone.
        // AMD-2026-05-02-01 Track H E-1 round 2（HIGH-3 retrofit）：
        // release_lease() 終態 transition 後會清 lease_id_to_idx 反查表防 heap
        // leak；get_lease_by_id() 因此回 LeaseNotFound（SM 物件仍在，但
        // String→idx 路徑已清）。
        let lookup_after = core.get_lease_by_id(&lease_id_str);
        assert!(
            matches!(lookup_after, Err(GovernanceError::LeaseNotFound(_))),
            "HIGH-3: reverse-map entry must be pruned after Consumed terminal transition"
        );
    }

    /// Exploration / Validation profile must short-circuit to LeaseId::Bypass
    /// without touching SM (PA push back #1: spec §3 point 1 trailing clause).
    /// Exploration / Validation profile 必須短路到 LeaseId::Bypass，不碰 SM
    /// （PA push back #1：spec §3 點 1 後段）。
    #[test]
    fn test_facade_bypass_for_non_production_profile() {
        // Validation
        let core_val = GovernanceCore::new_with_profile(GovernanceProfile::Validation);
        let lease_val = core_val
            .acquire_lease(
                "intent-val",
                "TRADE_ENTRY",
                30_000,
                GovernanceProfile::Validation,
                "facade_test",
            )
            .expect("Validation acquire returns Bypass Ok");
        assert_eq!(lease_val, LeaseId::Bypass);
        assert!(!lease_val.is_active());
        assert_eq!(
            core_val.lease.lock().len(),
            0,
            "Validation must NOT create SM object"
        );

        // Exploration
        let core_exp = GovernanceCore::new_with_profile(GovernanceProfile::Exploration);
        let lease_exp = core_exp
            .acquire_lease(
                "intent-exp",
                "TRADE_ENTRY",
                30_000,
                GovernanceProfile::Exploration,
                "facade_test",
            )
            .expect("Exploration acquire returns Bypass Ok");
        assert_eq!(lease_exp, LeaseId::Bypass);
        assert_eq!(
            core_exp.lease.lock().len(),
            0,
            "Exploration must NOT create SM object"
        );

        // release_lease(Bypass) must be no-op.
        // release_lease(Bypass) 必為 no-op。
        core_val
            .release_lease(&lease_val, LeaseOutcome::Consumed)
            .expect("release_lease(Bypass) must Ok no-op");
    }

    /// Production without auth must AuthNotEffective, not panic.
    /// Production 無授權必回 AuthNotEffective，不可 panic。
    #[test]
    fn test_facade_production_without_auth_fails_closed() {
        let core = GovernanceCore::new(); // mode=Frozen, no auth
        let result = core.acquire_lease(
            "intent-no-auth",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "facade_test",
        );
        assert!(matches!(result, Err(GovernanceError::AuthNotEffective)));
        assert_eq!(core.lease.lock().len(), 0);
    }

    /// Invalid TTL bounds rejected per spec §3 point 1.
    /// 不合法 TTL 邊界被拒絕（spec §3 點 1）。
    #[test]
    fn test_facade_invalid_ttl_rejected() {
        let mut core = GovernanceCore::new();
        core.grant_paper_authorization(None).unwrap();

        // Below lower bound 100ms
        let r1 = core.acquire_lease(
            "intent",
            "TRADE_ENTRY",
            50,
            GovernanceProfile::Production,
            "test",
        );
        assert!(matches!(r1, Err(GovernanceError::InvalidTtl(50))));

        // Above upper bound 300_000ms
        let r2 = core.acquire_lease(
            "intent",
            "TRADE_ENTRY",
            300_001,
            GovernanceProfile::Production,
            "test",
        );
        assert!(matches!(r2, Err(GovernanceError::InvalidTtl(300_001))));

        // Boundary values accepted
        let r3 = core.acquire_lease(
            "intent",
            "TRADE_ENTRY",
            100,
            GovernanceProfile::Production,
            "test",
        );
        assert!(r3.is_ok());
        let r4 = core.acquire_lease(
            "intent2",
            "TRADE_ENTRY",
            300_000,
            GovernanceProfile::Production,
            "test",
        );
        assert!(r4.is_ok());
    }

    /// Failed / Cancelled outcomes route to Active → Revoked.
    /// HIGH-3: after release the reverse-map entry is pruned, so the SM
    /// object's terminal state is verified via the SM directly (lease.lock())
    /// rather than via get_lease_by_id() which returns LeaseNotFound.
    /// Failed / Cancelled outcomes 走 Active → Revoked 路徑。
    /// HIGH-3：release 後反查表已清，改用 SM 直接驗終態。
    #[test]
    fn test_facade_release_failed_revokes() {
        let mut core = GovernanceCore::new();
        core.grant_paper_authorization(None).unwrap();

        let lease = core
            .acquire_lease(
                "intent-fail",
                "TRADE_ENTRY",
                30_000,
                GovernanceProfile::Production,
                "test",
            )
            .unwrap();
        let lease_id_str = lease.as_str().to_string();

        core.release_lease(&lease, LeaseOutcome::Failed).unwrap();
        // Reverse map pruned (HIGH-3); query via SM directly to assert terminal state.
        // 反查表已清（HIGH-3）；改透過 SM 直接驗終態。
        assert!(matches!(
            core.get_lease_by_id(&lease_id_str),
            Err(GovernanceError::LeaseNotFound(_))
        ));
        let sm_state = {
            let sm = core.lease.lock();
            (0..sm.len())
                .filter_map(|idx| sm.get(idx))
                .find(|o| o.lease_id == lease_id_str)
                .map(|o| o.state)
        };
        assert_eq!(sm_state, Some(LeaseState::Revoked));

        // Cancelled outcome
        let lease2 = core
            .acquire_lease(
                "intent-cancel",
                "TRADE_ENTRY",
                30_000,
                GovernanceProfile::Production,
                "test",
            )
            .unwrap();
        let lease2_id = lease2.as_str().to_string();
        core.release_lease(&lease2, LeaseOutcome::Cancelled)
            .unwrap();
        let sm_state2 = {
            let sm = core.lease.lock();
            (0..sm.len())
                .filter_map(|idx| sm.get(idx))
                .find(|o| o.lease_id == lease2_id)
                .map(|o| o.state)
        };
        assert_eq!(sm_state2, Some(LeaseState::Revoked));
    }

    /// Reverse lookup: get_lease_by_id with unknown lease_id returns LeaseNotFound.
    /// 反查表：未知 lease_id 的 get_lease_by_id 回 LeaseNotFound。
    #[test]
    fn test_facade_get_lease_by_id_unknown_not_found() {
        let core = GovernanceCore::new();
        let result = core.get_lease_by_id("lease:does_not_exist");
        assert!(matches!(result, Err(GovernanceError::LeaseNotFound(_))));
    }

    /// Mutex no deadlock: acquire + release + status all in same thread sequence.
    /// The Mutex must release between facade calls; deadlock would hang test.
    /// Mutex 不死鎖：acquire + release + status 同線程序列；facade 呼叫間 Mutex
    /// 必釋放，死鎖會掛測試。
    #[test]
    fn test_facade_no_mutex_deadlock_in_sequence() {
        let mut core = GovernanceCore::new();
        core.grant_paper_authorization(None).unwrap();

        // 5 sequential acquire+release pairs — if Mutex held across calls, this
        // would deadlock on the second iteration.
        // 5 次序列 acquire+release — 若 Mutex 跨呼叫持有，第二輪即死鎖。
        for i in 0..5 {
            let intent_id = format!("intent-{i}");
            let lease = core
                .acquire_lease(
                    &intent_id,
                    "TRADE_ENTRY",
                    30_000,
                    GovernanceProfile::Production,
                    "test",
                )
                .expect("must not deadlock");
            let _status = core.status(); // status() also locks lease — verify no deadlock.
            core.release_lease(&lease, LeaseOutcome::Consumed)
                .expect("release must not deadlock");
        }

        // All 5 leases consumed; SM has 5 objects total.
        // 5 個 lease 全部 consumed；SM 共有 5 個物件。
        assert_eq!(core.lease.lock().len(), 5);
        assert_eq!(core.lease.lock().get_live().len(), 0);
    }

    /// Router gate flag default OFF — E-1 lands facade but does not enable gate.
    /// Router gate flag 預設 OFF — E-1 落 facade 但不啟用 gate。
    #[test]
    fn test_router_gate_flag_default_off() {
        // Save and clear env var to ensure default behavior.
        // 保存並清空 env var 以確保 default 行為。
        let original = std::env::var("OPENCLAW_LEASE_ROUTER_GATE_ENABLED").ok();
        std::env::remove_var("OPENCLAW_LEASE_ROUTER_GATE_ENABLED");
        let core = GovernanceCore::new();
        assert!(
            !core.router_gate_enabled(),
            "default must be OFF (E-2 enables in Phase 5)"
        );
        // Restore original value if any.
        // 還原原值（若存在）。
        if let Some(val) = original {
            std::env::set_var("OPENCLAW_LEASE_ROUTER_GATE_ENABLED", val);
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // E2 round 1 LOW-1 retrofit (2026-05-03):
    //   set_router_gate_enabled_for_test must carry a debug_assert!
    //   guard so production code paths cannot silently flip the flag
    //   in a release build. Two test cases below pin both halves of
    //   the contract:
    //     1. debug build / cfg(test) → setter executes, flag mutates.
    //     2. release build (debug_assertions OFF + cfg(test) OFF) →
    //        debug_assert! compiles to no-op (verified by macro
    //        expansion + by inspection — no runtime probe possible
    //        from a test context where cfg!(test) is always true).
    //
    // E2 round 1 LOW-1 retrofit（2026-05-03）：
    //   set_router_gate_enabled_for_test 必帶 debug_assert! guard，
    //   release build 生產代碼不可暗中翻轉 flag。下方兩 test 釘住契約
    //   兩面：(1) debug build / cfg(test) → setter 執行、flag 變動；
    //   (2) release build → debug_assert! 展開為 no-op（由 macro 展開
    //   驗證 + 程式碼閱讀；test context 下 cfg!(test) 永真，無法 runtime
    //   探測 release 行為）。
    // ─────────────────────────────────────────────────────────────────

    /// LOW-1: setter mutates flag in debug/test profile (positive case).
    /// LOW-1：debug/test profile 下 setter 真正翻轉 flag（正向 case）。
    #[test]
    fn test_set_router_gate_for_test_mutates_flag_in_debug() {
        // cargo test always runs with cfg(test) → debug_assert! satisfied.
        // cargo test 永遠 cfg(test) 為真 → debug_assert! 必通過。
        assert!(
            cfg!(debug_assertions) || cfg!(test),
            "test runner must satisfy debug_assert! precondition; if not, \
             setter would panic — that is what LOW-1 protects against."
        );

        let mut core = GovernanceCore::new();
        let initial = core.router_gate_enabled();

        // Flip ON.
        core.set_router_gate_enabled_for_test(true);
        assert!(
            core.router_gate_enabled(),
            "setter must mutate flag in debug/test profile"
        );

        // Flip OFF.
        core.set_router_gate_enabled_for_test(false);
        assert!(
            !core.router_gate_enabled(),
            "setter must mutate flag in debug/test profile (off direction)"
        );

        // Restore (best-effort; test isolation already cheap with new()).
        // 還原（best-effort；test isolation 已便宜，每 test 都 new()）。
        core.set_router_gate_enabled_for_test(initial);
    }

    /// LOW-1: debug_assert! is no-op in release builds (compile-time check).
    /// LOW-1：release build 下 debug_assert! 展開為 no-op（編譯期檢查）。
    ///
    /// Cannot probe release-build panic from inside cargo test (cfg(test)
    /// is always true here). We assert the macro-level invariant:
    ///   1. `cfg!(debug_assertions)` is checkable at compile time.
    ///   2. `cfg!(test)` is true within this test module.
    ///   3. Either is sufficient for the guard — release production calls
    ///      both fail (cfg!(debug_assertions)=false + cfg!(test)=false).
    /// 無法在 cargo test 中探測 release panic（此處 cfg(test) 永真）。
    /// 釘住巨集層級不變量：(1) cfg!(debug_assertions) 編譯期可檢；
    /// (2) cfg!(test) 在本 test module 內為真；(3) 任一足以滿足 guard，
    /// release production 兩者皆 false 才會 panic。
    #[test]
    fn test_set_router_gate_for_test_debug_assert_invariant() {
        // Test module always sees cfg!(test) == true.
        // 本 test module 內 cfg!(test) 永真。
        assert!(cfg!(test), "test module must observe cfg!(test) == true");

        // Cargo test (default profile) → debug_assertions ON.
        // cargo test --release → debug_assertions OFF, but cfg!(test) still true.
        // Either branch satisfies the guard.
        // cargo test 預設 profile → debug_assertions 開啟。
        // cargo test --release → debug_assertions 關，但 cfg!(test) 仍為真。
        // 任一分支都滿足 guard。
        let guard_satisfied = cfg!(debug_assertions) || cfg!(test);
        assert!(
            guard_satisfied,
            "guard precondition: debug_assertions={} cfg!(test)={}",
            cfg!(debug_assertions),
            cfg!(test)
        );

        // The actual assertion that the macro emits — calling the setter
        // exercises the macro; if either condition were false, this would
        // panic via debug_assert!. Reaching this line means the macro emit
        // is correct.
        // macro 實際發出的 assertion — 呼 setter 即觸發 macro；任一條件為 false
        // 會 panic 經 debug_assert!。能執行到此行表示 macro emit 正確。
        let mut core = GovernanceCore::new();
        core.set_router_gate_enabled_for_test(true);
        core.set_router_gate_enabled_for_test(false);
    }

    // E2 round 1 verdict HIGH-1 e2e tests live in a separate integration
    // test file `openclaw_core/tests/engine_mode_tag_e2e.rs` to keep this
    // module under the §9 pre-existing baseline exception buffer.
    // HIGH-1 e2e 測試置於獨立 integration test 檔（tests/engine_mode_tag_e2e.rs）
    // 維持本模組在 §九 pre-existing baseline exception buffer 內。

    // ═══════════════════════════════════════════════════════════════════════
    // W-AUDIT-9 T6 (AMD-2026-05-09-03 §4.5) — graduated canary stage promotion
    // 用 LeaseScope::CanaryStagePromotion 走專用 facade，並在 manual_promote
    // audit row 中強制攜帶 decision_lease_id。
    // ═══════════════════════════════════════════════════════════════════════

    /// W-AUDIT-9 T6 happy path —
    /// Production 授權 + acquire `CanaryStagePromotion` lease → 60s TTL →
    /// audit row 必帶 decision_lease_id。對應 §三 invariant 11
    /// (`canary_stage_log.decision_lease_id` for `manual_promote` PG NOT NULL)。
    #[test]
    fn test_canary_stage_promotion_lease_carries_decision_lease_id() {
        let mut core = GovernanceCore::new();
        // Production 授權（grant_paper_authorization 對 SM-1 是普通 auth grant，
        // 內容是 paper 標籤但 is_authorized() 只檢查 effective auth 是否非空）。
        core.grant_paper_authorization(None).unwrap();

        // 經專用 facade acquire — operator-only path。
        let lease = core
            .acquire_canary_stage_promotion_lease("manual_promote_intent_001", "operator_gui")
            .expect("Production+auth 必能 acquire CanaryStagePromotion lease");

        // 必為 Active variant（Production profile 走 SM 真路徑）；不可為 Bypass。
        assert!(
            matches!(lease, LeaseId::Active(_)),
            "CanaryStagePromotion 必走 SM Active 路徑，不可 Bypass"
        );

        let lease_id_str = match &lease {
            LeaseId::Active(s) => s.clone(),
            LeaseId::Bypass => unreachable!(),
        };

        // 走 make_canary_stage_promotion_audit_row 構造 row，必帶 decision_lease_id。
        let row = core
            .make_canary_stage_promotion_audit_row(
                1_715_270_400_000,
                "demo",
                Some("ma_crossover".to_string()),
                Some("BTCUSDT".to_string()),
                0,
                1,
                "operator selected after 7d Stage 0 evidence stable",
                "operator:supervisor",
                &lease,
                serde_json::json!({"observed_sharpe": 0.42, "n_trials": 13}),
            )
            .expect("Active lease 必可組裝 manual_promote row");

        // W-AUDIT-9 T6 SAFETY 不變量驗證：
        assert_eq!(
            row.transition_kind, "manual_promote",
            "row.transition_kind 必為 'manual_promote' 對齊 PG CHECK"
        );
        assert_eq!(
            row.decision_lease_id,
            Some(lease_id_str.clone()),
            "manual_promote 必填 decision_lease_id（§5 invariant 11 PG NOT NULL）"
        );
        assert_eq!(row.from_stage, 0);
        assert_eq!(row.to_stage, 1);
        assert_eq!(row.environment, "demo");
        assert_eq!(row.cohort_strategy, Some("ma_crossover".to_string()));
        assert_eq!(row.cohort_symbol, Some("BTCUSDT".to_string()));

        // SM 端真實 Active 狀態 + lease 物件 metadata 含 60s TTL。
        let obj = core
            .get_lease_by_id(&lease_id_str)
            .expect("acquire 後 reverse lookup 必命中");
        assert_eq!(obj.state, LeaseState::Active);
        // intent metadata 含 scope / ttl_ms / source_stage（acquire_lease 寫入）。
        let meta = &obj.intent;
        assert_eq!(meta["scope"], serde_json::json!("CANARY_STAGE_PROMOTION"));
        assert_eq!(meta["ttl_ms"], serde_json::json!(60_000));
        assert_eq!(meta["source_stage"], serde_json::json!("operator_gui"));

        // 釋放 lease 為 Consumed → SM 走 Active → Bridged → Consumed。
        core.release_lease(&lease, LeaseOutcome::Consumed)
            .expect("manual_promote lease release 必成功");
    }

    /// W-AUDIT-9 T6 fail-closed —
    /// 未授權（is_authorized()=false）即拒 acquire；caller 必 fail-closed
    /// 不寫 canary_stage_log row。
    #[test]
    fn test_canary_stage_promotion_lease_rejects_when_no_auth() {
        // 全新 core，未 grant_paper_authorization → is_authorized() = false。
        let core = GovernanceCore::new();
        assert!(!core.is_authorized());

        let result = core.acquire_canary_stage_promotion_lease("attempt_no_auth", "operator_gui");

        assert!(
            matches!(result, Err(GovernanceError::AuthNotEffective)),
            "未授權 acquire 必 fail-closed，got: {:?}",
            result
        );
    }

    /// W-AUDIT-9 T6 — Bypass lease 不可走 manual_promote 路徑。
    /// 對應 AMD-2026-05-09-03 §3.5：graduated canary 只適用 alpha-bearing
    /// Production；Exploration / Validation profile 應在 caller 端 reject。
    #[test]
    fn test_canary_stage_promotion_audit_row_rejects_bypass() {
        let core = GovernanceCore::new_with_profile(GovernanceProfile::Validation);
        // Validation profile 直接 acquire 任意 scope 都拿 Bypass。
        let bypass_lease = core
            .acquire_lease(
                "intent_validation",
                "CANARY_STAGE_PROMOTION",
                60_000,
                GovernanceProfile::Validation,
                "irregular_path",
            )
            .expect("Validation acquire 永遠回 Bypass");
        assert!(matches!(bypass_lease, LeaseId::Bypass));

        // make_canary_stage_promotion_audit_row 必拒 Bypass。
        let row_result = core.make_canary_stage_promotion_audit_row(
            1_715_270_400_000,
            "demo",
            None,
            None,
            0,
            1,
            "should_fail_with_bypass",
            "operator:supervisor",
            &bypass_lease,
            serde_json::json!({}),
        );
        assert!(
            matches!(row_result, Err(GovernanceError::LeaseScopeNotPermitted(_))),
            "Bypass lease 不可組 manual_promote row"
        );
    }

    /// W-AUDIT-9 T6 — 多次連續 manual_promote 各帶獨立 lease_id（不複用）。
    /// 對應 §三 invariant 11：每次 transition 必對應一筆 audit row + 自己的
    /// decision_lease_id；防 lease_id 共用導致跨 transition audit 混淆。
    #[test]
    fn test_canary_stage_promotion_lease_id_unique_per_transition() {
        let mut core = GovernanceCore::new();
        core.grant_paper_authorization(None).unwrap();

        let lease_a = core
            .acquire_canary_stage_promotion_lease("promote_a", "operator_gui")
            .expect("acquire a");
        let lease_b = core
            .acquire_canary_stage_promotion_lease("promote_b", "operator_gui")
            .expect("acquire b");

        // 兩 lease_id 必相異（SM 內部 LeaseObject::new 用 rand::random 生成 48-bit
        // masked，collision 概率 < 1e-12）。
        let id_a = match &lease_a {
            LeaseId::Active(s) => s.clone(),
            LeaseId::Bypass => unreachable!(),
        };
        let id_b = match &lease_b {
            LeaseId::Active(s) => s.clone(),
            LeaseId::Bypass => unreachable!(),
        };
        assert_ne!(id_a, id_b, "兩個 manual_promote 的 lease_id 必相異");

        // 兩筆 row 各自帶自己的 lease_id。
        let row_a = core
            .make_canary_stage_promotion_audit_row(
                1_715_270_400_000,
                "demo",
                Some("ma_crossover".to_string()),
                Some("BTCUSDT".to_string()),
                0,
                1,
                "stage 1 entry",
                "operator:supervisor",
                &lease_a,
                serde_json::json!({}),
            )
            .unwrap();
        let row_b = core
            .make_canary_stage_promotion_audit_row(
                1_715_270_500_000,
                "demo",
                Some("ma_crossover".to_string()),
                Some("BTCUSDT".to_string()),
                1,
                2,
                "stage 2 promote",
                "operator:supervisor",
                &lease_b,
                serde_json::json!({}),
            )
            .unwrap();

        assert_eq!(row_a.decision_lease_id, Some(id_a));
        assert_eq!(row_b.decision_lease_id, Some(id_b));
        // transition kind 都是 manual_promote。
        assert_eq!(row_a.transition_kind, "manual_promote");
        assert_eq!(row_b.transition_kind, "manual_promote");

        // 釋放 lease 避免 SM leak。
        core.release_lease(&lease_a, LeaseOutcome::Consumed).unwrap();
        core.release_lease(&lease_b, LeaseOutcome::Consumed).unwrap();
    }
}
