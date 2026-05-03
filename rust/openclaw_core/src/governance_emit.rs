//! GovernanceEmit — audit emit primitives for V054 lease_transitions.
//! GovernanceEmit — V054 lease_transitions 的 audit emit 基礎元件。
//!
//! MODULE_NOTE (EN): Extracted from governance_core.rs to (1) keep the facade
//!   under the 1500 LOC hard cap; (2) decouple the emit payload + helpers so
//!   E1 retrofit (release_lease cleanup line + periodic sweeper) and E4
//!   retrofit (engine_mode_tag wiring) can land independently without
//!   colliding on governance_core.rs LOC budget; (3) give cross-crate writer
//!   (`openclaw_engine::database::lease_transition_writer`) a single import
//!   point that does not require pulling in the whole governance_core module.
//!
//!   Contents:
//!     - `LeaseTransitionMsg` struct (V054 14-col payload row).
//!     - `LeaseTransitionSender` type alias (std::sync::mpsc::Sender).
//!     - `EngineModeTagResolver::resolve(...)` — Track H E-4 retrofit Option A:
//!       reads self-injected tag → env var fallback → "unknown" fail-soft.
//!     - `build_msg_from_last_transition(...)` — converts the most recent
//!       SM TransitionRecord on a LeaseObject into an emit payload.
//!     - `emit_transition_fail_soft(...)` — fire-and-forget send that drops
//!       the msg silently when the channel is `None` or the receiver is
//!       gone (audit completeness is best-effort, never blocks hot path).
//!
//! MODULE_NOTE (中): 從 governance_core.rs 抽取，目的：(1) 把 facade 控制在
//!   1500 LOC hard cap 之下；(2) 解耦 emit payload 與 helper，讓 E1 retrofit
//!   （release_lease cleanup line + periodic sweeper）與 E4 retrofit
//!   （engine_mode_tag wiring）可獨立 land 不撞 governance_core.rs LOC 預算；
//!   (3) 給跨 crate writer
//!   （`openclaw_engine::database::lease_transition_writer`）一個單一 import
//!   入口，無需拉整個 governance_core module。
//!
//!   內容：
//!     - `LeaseTransitionMsg` struct（V054 14-col payload row）。
//!     - `LeaseTransitionSender` type alias（std::sync::mpsc::Sender）。
//!     - `EngineModeTagResolver::resolve(...)` — Track H E-4 retrofit Option A：
//!       讀取 self-injected tag → env var fallback → "unknown" fail-soft。
//!     - `build_msg_from_last_transition(...)` — 將 LeaseObject 最近一筆 SM
//!       TransitionRecord 轉為 emit payload。
//!     - `emit_transition_fail_soft(...)` — fire-and-forget send；channel
//!       為 None 或 receiver dropped 時靜默丟棄（audit completeness 是
//!       best-effort，永不阻塞 hot path）。
//!
//! 上層治理 SoT：CLAUDE.md §三 18 Live Blocker #6（agent 三表 / lease_transitions
//! all-time 0 row）+ amendment AMD-2026-05-02-01 §3 點 5 + §4 AC-1（5 distinct
//! states / 24h）+ E2 round 1 verdict HIGH-1（OPENCLAW_ENGINE_MODE 沒 setter）。
//! Upper governance SoT: CLAUDE.md §3 18 Live Blocker #6 + amendment §3 point 5
//! + §4 AC-1 (5 distinct states / 24h) + E2 round 1 verdict HIGH-1.

use crate::sm::lease::LeaseObject;
use crate::sm::SmError;
use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// Lease facade types — moved here from governance_core.rs round-2 retrofit
// （E2 verdict HIGH-1，2026-05-03）to keep the facade under 1500 LOC hard cap.
// 從 governance_core.rs 第二輪 retrofit 搬來，控 facade 在 1500 LOC hard cap。
// ---------------------------------------------------------------------------

/// LeaseId — facade-level identifier returned by `acquire_lease()`.
/// LeaseId — `acquire_lease()` 回傳的 facade 級識別符。
///
/// `Active(String)`：Production profile 真實 SM 路徑，需匹配 `release_lease()`。
/// `Bypass`：Exploration / Validation profile short-circuit；release no-op。
/// `Active(String)`: Production real SM path; `Bypass`: non-Production short-circuit.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum LeaseId {
    /// Active production lease — caller must release. / 啟用 production lease — 呼叫端必 release。
    Active(String),
    /// Bypass for non-Production profile — release is no-op. / 非 Production profile bypass — release 為 no-op。
    Bypass,
}

impl LeaseId {
    /// Extract underlying String for serialization / IPC payload.
    /// 提取底層 String 供序列化 / IPC payload 使用。
    pub fn as_str(&self) -> &str {
        match self {
            Self::Active(s) => s.as_str(),
            Self::Bypass => "bypass",
        }
    }

    /// Whether this is a real production lease that requires release.
    /// 是否為真實 production lease（需要 release）。
    pub fn is_active(&self) -> bool {
        matches!(self, Self::Active(_))
    }
}

/// LeaseOutcome — release reason classification.
/// LeaseOutcome — release 原因分類。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum LeaseOutcome {
    /// Successful execution → SM transition Bridged → Consumed.
    /// 成功執行 → SM transition Bridged → Consumed。
    Consumed,
    /// Execution failed (exchange reject / dispatch error) → Active → Revoked.
    /// 執行失敗（交易所拒絕 / dispatch 錯誤）→ Active → Revoked。
    Failed,
    /// Caller-initiated cancellation → Active → Revoked.
    /// 呼叫端主動取消 → Active → Revoked。
    Cancelled,
}

/// GovernanceError — facade-level error variants.
/// GovernanceError — facade 級錯誤分支。
#[derive(Debug, Clone, thiserror::Error)]
pub enum GovernanceError {
    /// Authorization not effective (SM-1 not active / mode != Normal).
    /// 授權未生效（SM-1 未啟用 / mode != Normal）。
    #[error("authorization not effective")]
    AuthNotEffective,

    /// Lease scope (e.g. TRADE_ENTRY) not permitted under current auth.
    /// 當前授權不允許此 lease scope（例如 TRADE_ENTRY）。
    #[error("lease scope not permitted: {0}")]
    LeaseScopeNotPermitted(String),

    /// Lease SM internal failure (forbidden transition / approval needed / etc.).
    /// Lease SM 內部錯誤（禁止 transition / 需要批准 / 等）。
    #[error("lease SM failure: {0}")]
    LeaseSmFailure(#[from] SmError),

    /// lease_id not found in reverse lookup table.
    /// 反查表中找不到 lease_id。
    #[error("lease id not found: {0}")]
    LeaseNotFound(String),

    /// Invalid TTL (must be 100..=300_000 ms per spec §3).
    /// TTL 不合法（spec §3 規定 100..=300_000 ms）。
    #[error("invalid TTL: {0} ms (must be 100..=300_000)")]
    InvalidTtl(u32),
}

// ---------------------------------------------------------------------------
// LeaseTransitionMsg — V054 14-col audit row payload
// ---------------------------------------------------------------------------

/// LeaseTransitionMsg — audit emit payload for `lease_transition_writer` actor.
/// LeaseTransitionMsg — `lease_transition_writer` actor 的 audit emit payload。
///
/// E-1 階段定義 struct 但不註冊 sender；E-4 task 才注入 mpsc::Sender + emit logic。
/// E-1 phase defines the struct but does not register sender; E-4 task injects
/// mpsc::Sender and adds emit logic in acquire_lease/release_lease.
///
/// E-4 微調（2026-05-03 Track H）：profile field 由 GovernanceProfile enum 改為
/// String（"Production" / "Validation" / "Exploration"），讓 openclaw_engine 端
/// writer 不必 import openclaw_core::GovernanceProfile，降低交叉 crate 耦合。
/// E-4 retrofit (2026-05-03 Track H): profile field changed from
/// GovernanceProfile enum → String to keep the engine-side writer free of
/// openclaw_core::GovernanceProfile import.
#[derive(Debug, Clone)]
pub struct LeaseTransitionMsg {
    /// `tx:xxxx` — TransitionRecord ID. / 遷移記錄 ID。
    pub transition_id: String,
    /// `lease:xxxx` — Lease object ID. / 租約對象 ID。
    pub lease_id: String,
    /// SM state before transition（None for initial draft）。/ 遷移前狀態（initial draft 為 None）。
    pub from_state: Option<String>,
    /// SM state after transition. / 遷移後狀態。
    pub to_state: String,
    /// SM event triggering this transition. / 觸發此遷移的 SM 事件。
    pub event: String,
    /// Initiator role. / 發起者角色。
    pub initiator: String,
    /// Reason codes attached to transition. / 遷移所附理由碼。
    pub reason_codes: Vec<String>,
    /// Whether transition required approval. / 遷移是否需要批准。
    pub requires_approval: bool,
    /// Operator / system who approved. / 批准者。
    pub approved_by: Option<String>,
    /// GovernanceProfile snapshot serialized as String — "Production" /
    /// "Validation" / "Exploration"（V054 chk_lease_transitions_profile 3-value
    /// CHECK enum aligned）。
    /// GovernanceProfile snapshot 序列化為 String — V054 schema CHECK enum 對齊。
    pub profile: String,
    /// Engine mode for filtering shadow path（PA design §4 #2）.
    /// "paper" / "demo" / "live_demo" / "live_mainnet" / "shadow" / "unknown"
    /// （V054 chk_lease_transitions_engine_mode 5-value CHECK enum aligned；
    /// "unknown" fallback when neither self-injected tag nor env var set —
    /// caller-side V054 INSERT layer maps "unknown" to "demo" before the
    /// CHECK constraint kicks in to keep audit row writes never lost）.
    /// 引擎模式，用於過濾 shadow path（PA design §4 #2）；V054 CHECK enum 對齊；
    /// "unknown" 為 fail-soft fallback（caller-side writer 在 INSERT 前映射為
    /// "demo" 防 CHECK constraint reject，確保 audit row 永不丟）。
    pub engine_mode: String,
    /// DCS context_id for cross-row join. / DCS context_id 跨行 join 用。
    pub context_id: String,
    /// ms-since-epoch timestamp. / 自 epoch 起的毫秒時間戳。
    pub ts_ms: u64,
}

/// Sender alias for lease_transition_writer actor.
/// lease_transition_writer actor 的 sender 別名。
///
/// E-1 階段使用 std::sync::mpsc 而非 tokio::sync::mpsc — `openclaw_core` 不依賴 tokio。
/// E-1 phase uses std::sync::mpsc rather than tokio::sync::mpsc — `openclaw_core` is tokio-free.
/// E-4 task 若需要 async writer，可在 `openclaw_engine` 端 wrap 一層 tokio bridge。
/// If E-4 needs an async writer, wrap a tokio bridge in `openclaw_engine`.
pub type LeaseTransitionSender = std::sync::mpsc::Sender<LeaseTransitionMsg>;

// ---------------------------------------------------------------------------
// EngineModeTagResolver — Track H E-4 retrofit (round 2 HIGH-1 fix)
// ---------------------------------------------------------------------------

/// Engine mode tag resolution policy — pipeline-aware injection with env-var
/// fallback. Each pipeline (paper / demo / live_demo / live mainnet) constructs
/// its own GovernanceCore instance and binds the tag via
/// `GovernanceCore::set_engine_mode_tag` during pipeline boot
/// (pipeline_ctor.rs::set_endpoint_env). Without injection — e.g. in unit
/// tests, headless CLI runs, or freshly-constructed cores — the resolver
/// falls back to `OPENCLAW_ENGINE_MODE` env var and finally to "unknown".
///
/// V054 CHECK enum permits {paper, demo, live_demo, live_mainnet, shadow}. The
/// "unknown" sentinel is converted to "demo" by the writer's INSERT layer
/// before CHECK kicks in, so audit rows are never rejected at the constraint
/// level. The sentinel surfaces in operator dashboards as a "tag not wired"
/// signal pointing at unwired pipelines (drift catch).
///
/// E2 round 1 verdict HIGH-1 fix path A (preferred) — instance-method
/// resolver (no global state, no static OnceLock, no system_mode.json
/// dependency). The system_mode.json file referenced in HIGH-1 task
/// description does NOT exist in this repository (verified by grep across
/// rust/, program_code/, helper_scripts/, $HOME/.openclaw_runtime/, and
/// /tmp/openclaw on Linux trade-core); the real source-of-truth for
/// per-pipeline engine mode is `crate::mode_state::effective_engine_mode`
/// in openclaw_engine, accessed at boot time via the pipeline's
/// `set_endpoint_env` wiring.
///
/// Engine mode tag 解析策略 — 管線感知注入 + env var fallback。每個管線
/// （paper / demo / live_demo / live mainnet）構造自己的 GovernanceCore
/// 實例，並在 pipeline boot（pipeline_ctor.rs::set_endpoint_env）透過
/// `GovernanceCore::set_engine_mode_tag` 注入 tag。未注入時（單元測試、
/// CLI headless、剛構造的 core）resolver fallback 到 `OPENCLAW_ENGINE_MODE`
/// env var，最後 fallback 到 "unknown"。
///
/// V054 CHECK enum 允許 {paper, demo, live_demo, live_mainnet, shadow}。
/// "unknown" sentinel 由 writer INSERT layer 在 CHECK 之前映射為 "demo"，
/// 確保 audit row 不被 constraint 拒。Sentinel 在 operator dashboard 上
/// 顯示為「tag 未 wire」訊號，指出未接線的管線（drift catch）。
///
/// E2 round 1 verdict HIGH-1 修法路徑 A（首選）— instance-method resolver
/// （無全局狀態 / 無 static OnceLock / 無 system_mode.json 依賴）。HIGH-1
/// task description 提到的 system_mode.json 在本 repo **不存在**（grep
/// rust/, program_code/, helper_scripts/, $HOME/.openclaw_runtime/, Linux
/// /tmp/openclaw 全 0 hit 已驗證）；per-pipeline engine mode 真實
/// source-of-truth 是 openclaw_engine 的 `crate::mode_state::effective_engine_mode`，
/// 透過 pipeline `set_endpoint_env` wiring 在 boot 時取得。
pub struct EngineModeTagResolver;

impl EngineModeTagResolver {
    /// Set of valid V054 chk_lease_transitions_engine_mode tags.
    /// Caller passes the injected tag (Option) and gets a guaranteed-valid
    /// String back — invalid raw env values silently fall through to "unknown".
    /// V054 chk_lease_transitions_engine_mode 合法 tag 集合。caller 傳入
    /// 注入 tag（Option），回傳保證合法的 String — 不合法 env 值靜默 fallback
    /// 到 "unknown"。
    const VALID_TAGS: [&'static str; 6] = [
        "paper",
        "demo",
        "live_demo",
        "live_mainnet",
        "shadow",
        "unknown",
    ];

    /// Resolve the engine_mode tag using the layered fallback policy:
    ///   1. caller-injected `tag` (set via `GovernanceCore::set_engine_mode_tag`)
    ///   2. `OPENCLAW_ENGINE_MODE` env var (validated against VALID_TAGS)
    ///   3. `"unknown"` sentinel (fail-soft; writer maps to "demo" pre-INSERT)
    ///
    /// 按分層 fallback 政策解析 engine_mode tag：
    ///   1. caller 注入的 `tag`（透過 `GovernanceCore::set_engine_mode_tag`）
    ///   2. `OPENCLAW_ENGINE_MODE` env var（對 VALID_TAGS 驗證）
    ///   3. `"unknown"` sentinel（fail-soft；writer 在 INSERT 前映射為 "demo"）
    pub fn resolve(injected: Option<&str>) -> String {
        // 1. Self-injected tag (preferred — pipeline-aware via set_endpoint_env).
        // 1. 自注入 tag（首選 — 透過 set_endpoint_env 取得 pipeline 感知）。
        if let Some(t) = injected {
            if Self::is_valid(t) {
                return t.to_string();
            }
        }

        // 2. OPENCLAW_ENGINE_MODE env var fallback (validated).
        // 2. OPENCLAW_ENGINE_MODE env var fallback（驗證）。
        if let Ok(raw) = std::env::var("OPENCLAW_ENGINE_MODE") {
            if Self::is_valid(&raw) {
                return raw;
            }
        }

        // 3. "unknown" sentinel — caller-side INSERT mapper resolves to "demo".
        // 3. "unknown" sentinel — caller-side INSERT mapper 解析為 "demo"。
        "unknown".to_string()
    }

    /// Check if a tag is in the valid V054 CHECK enum set.
    /// 檢查 tag 是否在 V054 CHECK enum 合法集合內。
    fn is_valid(tag: &str) -> bool {
        Self::VALID_TAGS.contains(&tag)
    }
}

// ---------------------------------------------------------------------------
// build_msg_from_last_transition — convert TransitionRecord → LeaseTransitionMsg
// ---------------------------------------------------------------------------

/// Build a LeaseTransitionMsg from the most recent TransitionRecord on a
/// LeaseObject. Used by acquire_lease/release_lease to convert SM-level
/// transition records into engine-level audit messages.
/// 從 LeaseObject 最近一筆 TransitionRecord 構造 LeaseTransitionMsg。
/// acquire_lease/release_lease 用此函數將 SM 級 transition record 轉為
/// engine 級 audit 訊息。
///
/// Why facade emit / 為何 facade emit:
///   PA design §3.1 + E-1 §7.3 留 emit 策略給 E-4 自選；E-4 選 Option A
///   (facade 自動 emit) — 100% coverage 不依賴 caller，避免 amendment §4
///   AC-1「distinct count >= 5」假綠（caller 漏 emit 風險）。
///   PA design §3.1 + E-1 §7.3 leave emit strategy to E-4. E-4 selects
///   Option A (facade auto-emit) for 100% coverage independent of caller.
///
/// SAFETY / 不變量：
/// - 回 None 表示 LeaseObject.transitions 為空（純粹防禦性，acquire/release
///   路徑必然 push transition before invoke 此函數）；caller 必略過 None。
/// - Returns None when LeaseObject.transitions is empty (purely defensive;
///   acquire/release paths always push a transition before invoking this);
///   caller MUST skip None.
pub fn build_msg_from_last_transition(
    lease_id: &str,
    obj: &LeaseObject,
    profile: &str,
    engine_mode: &str,
    context_id: &str,
) -> Option<LeaseTransitionMsg> {
    let rec = obj.transitions.last()?;
    Some(LeaseTransitionMsg {
        transition_id: rec.transition_id.clone(),
        lease_id: lease_id.to_string(),
        from_state: if rec.from_state == "NONE" {
            None
        } else {
            Some(rec.from_state.clone())
        },
        to_state: rec.to_state.clone(),
        event: rec.event.clone(),
        initiator: rec.initiator.clone(),
        reason_codes: rec.reason_codes.clone(),
        requires_approval: rec.requires_approval,
        approved_by: rec.approved_by.clone(),
        profile: profile.to_string(),
        engine_mode: engine_mode.to_string(),
        context_id: context_id.to_string(),
        ts_ms: rec.timestamp_ms,
    })
}

// ---------------------------------------------------------------------------
// emit_transition_fail_soft — fire-and-forget send (no panic, no block)
// ---------------------------------------------------------------------------

/// AMD-2026-05-02-01 §3 point 5 + Track H E-4: fail-soft emit of a
/// LeaseTransitionMsg to the audit writer channel.
/// AMD-2026-05-02-01 §3 點 5 + Track H E-4：fail-soft 將 LeaseTransitionMsg
/// 推送至 audit writer channel。
///
/// Track H E-4 emit strategy = "Option A inside facade"（自動 emit，
/// caller 0 改動）。若 channel 未注入或滿、失敗 → drop（永不阻塞 facade）。
/// E-4 emit strategy = "Option A inline within facade" — automatic emit,
/// 0 caller change. Fail-soft on send failure (no panic, no block).
///
/// SAFETY / 不變量：
/// - std::sync::mpsc::Sender::send 為 fire-and-forget；Receiver dropped
///   → SendError，靜默丟棄（fail-soft）。
/// - 失敗 = silently drop msg（不 raise，不 log unless tracing 開啟），符合
///   amendment §6 條件 #1「lease IPC 中位延遲 > 100µs」回退 SLA。
/// - lease IPC median latency budget = ~10µs；channel send 為 lock-free queue
///   ~50ns，writer 端 spawn_blocking thread 解 lock 也 ~微秒級。
pub fn emit_transition_fail_soft(
    sender: Option<&LeaseTransitionSender>,
    msg: LeaseTransitionMsg,
) {
    if let Some(tx) = sender {
        // std::sync::mpsc::Sender::send is fire-and-forget; on dropped
        // Receiver returns SendError which we silently swallow (fail-soft).
        // std::sync::mpsc::Sender::send 為 fire-and-forget；Receiver dropped
        // → SendError 靜默吸收（fail-soft）。
        let _ = tx.send(msg);
    }
    // sender=None → silently skip（E-1 預留模式，writer 未注入時為 no-op）。
    // sender=None → silently skip (E-1 reservation pattern; no-op when writer
    // not yet injected).
}

// ═══════════════════════════════════════════════════════════════════════════
// Tests — engine_mode_tag resolver coverage (E2 round 1 verdict HIGH-1)
// 測試 — engine_mode_tag resolver 覆蓋（E2 round 1 verdict HIGH-1）
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper to mutate OPENCLAW_ENGINE_MODE under a process-wide Mutex so
    /// cargo test default parallel runner doesn't race on the env var.
    /// 在跨測試 Mutex 下變動 OPENCLAW_ENGINE_MODE，避免 cargo test 預設並行
    /// runner 對 env var 競態。
    ///
    /// SAFETY / 不變量：
    /// - lock + save + mutate + run + restore + unlock：lock 範圍涵蓋整個
    ///   test 邏輯，避免 test A set value, test B remove_var 兩條 thread
    ///   交叉污染。
    /// - lock + save + mutate + run + restore + unlock: lock spans the entire
    ///   test body so test A setting and test B removing the var cannot
    ///   interleave across threads.
    fn with_env_var<R>(value: Option<&str>, f: impl FnOnce() -> R) -> R {
        use std::sync::Mutex;
        // process-wide ENV_LOCK serialises all tests in this module that
        // touch OPENCLAW_ENGINE_MODE.
        // 進程級 ENV_LOCK 序列化所有觸碰 OPENCLAW_ENGINE_MODE 的測試。
        static ENV_LOCK: Mutex<()> = Mutex::new(());
        let _guard = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
        let key = "OPENCLAW_ENGINE_MODE";
        let original = std::env::var(key).ok();
        match value {
            Some(v) => std::env::set_var(key, v),
            None => std::env::remove_var(key),
        }
        let result = f();
        match original {
            Some(v) => std::env::set_var(key, v),
            None => std::env::remove_var(key),
        }
        result
    }

    // ─── HIGH-1 必測 4 case：4 trading_mode tag ───────────────────────────

    #[test]
    fn test_resolve_engine_mode_tag_paper_injected() {
        // Case 1: Paper pipeline injects "paper" via set_engine_mode_tag.
        // Case 1：Paper 管線透過 set_engine_mode_tag 注入 "paper"。
        with_env_var(None, || {
            let tag = EngineModeTagResolver::resolve(Some("paper"));
            assert_eq!(tag, "paper");
        });
    }

    #[test]
    fn test_resolve_engine_mode_tag_demo_injected() {
        // Case 2: Demo pipeline injects "demo".
        // Case 2：Demo 管線注入 "demo"。
        with_env_var(None, || {
            let tag = EngineModeTagResolver::resolve(Some("demo"));
            assert_eq!(tag, "demo");
        });
    }

    #[test]
    fn test_resolve_engine_mode_tag_live_demo_injected() {
        // Case 3: LiveDemo pipeline injects "live_demo" — distinguishes
        // demo-endpoint Live traffic from real mainnet live (project memory
        // engine_mode_tag_live_demo 2026-04-16 fix preserved).
        // Case 3：LiveDemo 管線注入 "live_demo" — 區分 demo 端點 Live 流量
        // 與真 mainnet live（保留 project memory engine_mode_tag_live_demo
        // 2026-04-16 修復）。
        with_env_var(None, || {
            let tag = EngineModeTagResolver::resolve(Some("live_demo"));
            assert_eq!(tag, "live_demo");
        });
    }

    #[test]
    fn test_resolve_engine_mode_tag_live_mainnet_injected() {
        // Case 4: Real mainnet Live pipeline injects "live_mainnet" — strict
        // production audit. Note: V054 enum naming "live_mainnet" not "live"
        // to avoid the historical 952k row collision masking real-money
        // traffic from demo-endpoint Live (memory engine_mode_tag_live_demo).
        // Case 4：真 mainnet Live 管線注入 "live_mainnet" — 嚴格 production
        // 審計。註：V054 enum 命名為 "live_mainnet" 非 "live"，避免歷史
        // 952k 行 collision 把真錢流量與 demo 端點 Live 混淆。
        with_env_var(None, || {
            let tag = EngineModeTagResolver::resolve(Some("live_mainnet"));
            assert_eq!(tag, "live_mainnet");
        });
    }

    #[test]
    fn test_resolve_engine_mode_tag_shadow_injected() {
        // Bonus case: shadow pipeline (PA design §4 #2 filter `engine_mode !=
        // 'shadow'` for AC-1 distinct-count query). shadow tag must round-trip
        // unchanged so the AC-1 filter functions.
        // 額外 case：shadow 管線（PA design §4 #2 過濾 `engine_mode != 'shadow'`
        // 用於 AC-1 distinct-count query）。shadow tag 必須原樣 round-trip
        // 才能讓 AC-1 過濾起作用。
        with_env_var(None, || {
            let tag = EngineModeTagResolver::resolve(Some("shadow"));
            assert_eq!(tag, "shadow");
        });
    }

    // ─── HIGH-1 必測 5th case：fail-soft fallback ─────────────────────────

    #[test]
    fn test_resolve_engine_mode_tag_no_injection_no_env_fallback_unknown() {
        // Case 5: file (system_mode.json) doesn't exist + no env var + no
        // injection → return "unknown" fail-soft (NOT panic, NOT log error).
        // Writer-side INSERT layer maps "unknown" → "demo" before V054 CHECK
        // constraint kicks in, so audit rows are never lost.
        // Case 5：file（system_mode.json）不存在 + 無 env var + 無注入 →
        // 返 "unknown" fail-soft（非 panic、非 log error）。Writer-side
        // INSERT layer 在 V054 CHECK 之前映射 "unknown" → "demo"，audit
        // row 永不丟。
        with_env_var(None, || {
            let tag = EngineModeTagResolver::resolve(None);
            assert_eq!(tag, "unknown");
        });
    }

    // ─── 額外 robustness case：env var 覆蓋 / 不合法 tag 的 fail-soft ─────

    #[test]
    fn test_resolve_engine_mode_tag_env_var_fallback_when_no_injection() {
        // Env var fills the gap when no injection — for headless CLI runs
        // (e.g. cargo test fixture without pipeline boot wiring) operator
        // can `export OPENCLAW_ENGINE_MODE=demo` to suppress the "unknown"
        // sentinel.
        // 無注入時 env var 補位 — headless CLI 跑（例：cargo test fixture
        // 無 pipeline boot wiring）operator 可 `export OPENCLAW_ENGINE_MODE=demo`
        // 來抑制 "unknown" sentinel。
        with_env_var(Some("demo"), || {
            let tag = EngineModeTagResolver::resolve(None);
            assert_eq!(tag, "demo");
        });
    }

    #[test]
    fn test_resolve_engine_mode_tag_invalid_injection_falls_through_to_env() {
        // Invalid injected tag (not in VALID_TAGS) falls through to env var.
        // Defensive — pipeline_ctor.rs always feeds a valid tag from
        // effective_engine_mode but ill-typed callers (test fixtures) get
        // graceful fallback.
        // 不合法 injected tag（不在 VALID_TAGS 內）fallback 至 env var。
        // 防禦性 — pipeline_ctor.rs 透過 effective_engine_mode 必餵合法 tag，
        // 但類型錯的 caller（測試 fixture）獲得 graceful fallback。
        with_env_var(Some("paper"), || {
            let tag = EngineModeTagResolver::resolve(Some("not_a_real_tag"));
            assert_eq!(tag, "paper");
        });
    }

    #[test]
    fn test_resolve_engine_mode_tag_invalid_env_falls_through_to_unknown() {
        // Invalid env var ("garbage") + no injection → "unknown" fail-soft.
        // 不合法 env var ("garbage") + 無注入 → "unknown" fail-soft。
        with_env_var(Some("garbage"), || {
            let tag = EngineModeTagResolver::resolve(None);
            assert_eq!(tag, "unknown");
        });
    }

    #[test]
    fn test_resolve_engine_mode_tag_injection_overrides_env() {
        // When both injected and env are set, injected wins (pipeline-aware
        // SoT > global env var).
        // injected 與 env 皆設時，injected 勝（pipeline-aware SoT > 全局 env）。
        with_env_var(Some("paper"), || {
            let tag = EngineModeTagResolver::resolve(Some("live_mainnet"));
            assert_eq!(tag, "live_mainnet");
        });
    }

    #[test]
    fn test_emit_transition_fail_soft_no_sender_no_panic() {
        // sender=None → silent no-op (E-1 reservation pattern; writer not yet
        // injected). Must NOT panic.
        // sender=None → 靜默 no-op（E-1 預留模式；writer 未注入）。不 panic。
        let msg = LeaseTransitionMsg {
            transition_id: "tx:test".to_string(),
            lease_id: "lease:test".to_string(),
            from_state: None,
            to_state: "DRAFT".to_string(),
            event: "create_draft".to_string(),
            initiator: "test".to_string(),
            reason_codes: vec![],
            requires_approval: false,
            approved_by: None,
            profile: "Production".to_string(),
            engine_mode: "demo".to_string(),
            context_id: "ctx:test".to_string(),
            ts_ms: 1_000_000,
        };
        emit_transition_fail_soft(None, msg);
        // No panic = pass.
    }

    #[test]
    fn test_emit_transition_fail_soft_dropped_receiver_swallows_error() {
        // Receiver dropped → Sender::send returns SendError → silently
        // swallowed by fail-soft. Must NOT panic, must NOT block.
        // Receiver dropped → Sender::send 回 SendError → fail-soft 靜默吸收。
        // 不 panic、不 block。
        let (tx, rx) = std::sync::mpsc::channel::<LeaseTransitionMsg>();
        drop(rx); // 提前 drop receiver，模擬 writer crashed scenario
        let msg = LeaseTransitionMsg {
            transition_id: "tx:test2".to_string(),
            lease_id: "lease:test2".to_string(),
            from_state: Some("DRAFT".to_string()),
            to_state: "REGISTERED".to_string(),
            event: "register".to_string(),
            initiator: "test".to_string(),
            reason_codes: vec![],
            requires_approval: false,
            approved_by: None,
            profile: "Production".to_string(),
            engine_mode: "demo".to_string(),
            context_id: "ctx:test2".to_string(),
            ts_ms: 1_000_001,
        };
        emit_transition_fail_soft(Some(&tx), msg);
        // No panic = pass.
    }
}
