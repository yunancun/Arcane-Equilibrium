//! Late-injected `Arc<RwLock<Option<...>>>` slots used by the IPC server.
//! IPC 伺服器使用的延後注入 `Arc<RwLock<Option<...>>>` 槽位。
//!
//! MODULE_NOTE (EN): The IpcServer is constructed *before* the database pool,
//!   BudgetTracker, Teacher consumer loop, audit pool, and StrategistScheduler
//!   exist (because every one of them depends on a DB pool that itself is
//!   built later in `main.rs`). To keep the IpcServer construction sequence
//!   simple and avoid a deep dependency tree at boot, each downstream
//!   subsystem is exposed as a `*Slot` typedef around `Arc<RwLock<Option<T>>>`.
//!   `main.rs` swaps the inner `Option` from `None` → `Some(handle)` once the
//!   underlying subsystem is ready, and IPC handlers fail-soft (return a
//!   `{"status":"uninitialized"}` payload) when reading from a still-empty
//!   slot.
//! MODULE_NOTE (中)：IpcServer 在資料庫池 / BudgetTracker / Teacher loop /
//!   audit pool / StrategistScheduler 都還沒建好之前就先建好（因為這些都
//!   依賴一個更晚才在 `main.rs` 構造的 DB 池）。為了讓 IpcServer 構造序列
//!   單純化、避免啟動期深度依賴樹，每個下游子系統都包成
//!   `Arc<RwLock<Option<T>>>` 的 `*Slot` typedef。`main.rs` 在子系統就緒
//!   後將內部 `Option` 由 `None` 寫成 `Some(handle)`；IPC handler 在 slot
//!   仍空時 fail-soft（回 `{"status":"uninitialized"}`）。
//!
//! Split out of `ipc_server/mod.rs` as part of G5-FUP-IPC-MOD-SPLIT (2026-04-26)
//! to bring the parent file under the §九 1200-line hard cap.
//! 於 G5-FUP-IPC-MOD-SPLIT（2026-04-26）從 `ipc_server/mod.rs` 拆出，
//! 使父檔行數回到 §九 1200 行硬上限以下。

use crate::ai_budget::BudgetTracker;
use crate::claude_teacher::ConsumerLoopStatus;
use std::sync::atomic::AtomicBool;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Phase 4 (4-15): Shared, late-injected slot for the AI BudgetTracker.
/// Phase 4 (4-15)：共享的、延後注入的 AI BudgetTracker 槽位。
///
/// MODULE_NOTE (EN): The IpcServer is constructed before the database pool exists, so
///   the BudgetTracker (which needs the pool) is injected after construction via
///   `IpcServer::budget_tracker_slot()`. The slot is wrapped in `Arc<RwLock<Option<...>>>`
///   so the same handle can be cloned into per-connection tasks. None = uninitialized
///   (e.g., DB unavailable) and IPC handlers fail-soft with a `{"status":"uninitialized"}`
///   response on read, fail-closed (-32603) on write.
/// MODULE_NOTE (中)：IpcServer 在資料庫池建立之前就構造，因此需要池的 BudgetTracker
///   透過 `IpcServer::budget_tracker_slot()` 在構造後注入。槽位用
///   `Arc<RwLock<Option<...>>>` 包裝，以便複製到每個連線任務。None = 未初始化
///   （例如 DB 不可用），讀取 IPC 以 `{"status":"uninitialized"}` fail-soft，
///   寫入則回傳 -32603 fail-closed。
pub type BudgetTrackerSlot = Arc<RwLock<Option<Arc<BudgetTracker>>>>;

/// Phase 4.1: Late-injected handles for the Teacher consumer loop.
/// Phase 4.1：延後注入的 Teacher consumer loop 句柄。
///
/// MODULE_NOTE (EN): main.rs constructs the consumer loop AFTER the IPC server
///   is spawned (because BudgetTracker must be ready first). The loop's
///   enabled flag and status counters are then written into this slot so the
///   IPC handlers `set_teacher_loop_enabled` / `get_teacher_loop_status` can
///   reach them. None = loop not yet wired (IPC fail-soft response).
/// MODULE_NOTE (中)：main.rs 在 IPC server spawn 之後才構造 consumer loop
///   （因為 BudgetTracker 必須先就緒）。Loop 的 enabled 旗標與 status 計數器
///   會寫入此槽位，供 IPC handler `set_teacher_loop_enabled` /
///   `get_teacher_loop_status` 取用。None = loop 尚未接線（IPC fail-soft）。
#[derive(Clone)]
pub struct TeacherLoopHandles {
    pub enabled: Arc<AtomicBool>,
    pub status: Arc<ConsumerLoopStatus>,
}

pub type TeacherLoopSlot = Arc<RwLock<Option<TeacherLoopHandles>>>;

/// ARCH-RC1 1C-2-E: late-injected slot for the audit DB pool used by V014
/// engine_events writes. None = audit disabled (DB unavailable at boot or
/// pool not yet initialized).
/// ARCH-RC1 1C-2-E：V014 engine_events 寫入用的審計 DB pool 延後注入槽位。
/// None = 審計停用（啟動時 DB 不可用或 pool 尚未初始化）。
pub type AuditPoolSlot = Arc<RwLock<Option<sqlx::PgPool>>>;

/// G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 (2026-04-25): Late-injected slot
/// for the StrategistScheduler `CycleCounters` Arc.
///
/// MODULE_NOTE (EN): The IpcServer's `run()` future is detached BEFORE
///   `main_boot_tasks::spawn_strategist_scheduler` runs (scheduler depends
///   on db_pool readiness which is sequenced after IPC server detach in
///   main.rs). The slot is wrapped in `Arc<RwLock<Option<...>>>` so the
///   scheduler's counters Arc can be late-written without restarting IPC.
///   None = scheduler not yet spawned (Demo unbound) → IPC method returns
///   `{"status":"scheduler_unavailable"}` (fail-soft).
/// MODULE_NOTE (中)：IPC server `run()` 在 scheduler spawn 之前 detach；
///   slot 用 `Arc<RwLock<Option<...>>>` 讓 main.rs 在 scheduler spawn 後
///   late-inject。None = 未 spawn → IPC 回 scheduler_unavailable。
pub type StrategistCountersSlot =
    Arc<RwLock<Option<Arc<crate::strategist_scheduler::CycleCounters>>>>;

/// G3-08 H State Gateway (2026-04-26, Phase 1): late-injected slot for the
/// Rust-side cache of Python H1-H5 + 5-Agent state.
///
/// MODULE_NOTE (EN): The poller + cache are spawned only when the env-gate
///   `OPENCLAW_H_STATE_GATEWAY=1` is set (DEFAULT-OFF). When disabled the
///   slot stays `None` and the three IPC handlers (query_h_state_full /
///   get_h_state_status / invalidate_h_state) return a structured
///   `gateway_disabled` payload — never an error — so Python callers can
///   render a grey-state without raising. The Rust hot path never reaches
///   this slot in Phase 1; query is reserved for Phase 2-4 wiring.
///
///   Mirrors the G3-03 ExecutorConfigCache slot pattern but flow-direction
///   is reversed: G3-08 has Python as SSOT and Rust pulls (G3-03 is the
///   inverse — Rust SSOT, Python pulls).
///
///   See `h_state_cache::HStateCache` docstring for the full design.
///
/// MODULE_NOTE (中)：poller + cache 只在 env-gate
///   `OPENCLAW_H_STATE_GATEWAY=1` 時 spawn（DEFAULT-OFF）。關閉時 slot 保持
///   `None`，三個 IPC handler（query_h_state_full / get_h_state_status /
///   invalidate_h_state）會回結構化 `gateway_disabled` payload — 不報錯 —
///   讓 Python caller 顯示灰燈不 raise。Phase 1 Rust hot path 不讀此 slot；
///   Phase 2-4 接線時才開放查詢。
///
///   鏡射 G3-03 ExecutorConfigCache slot pattern，但流向相反：G3-08 是
///   Python 為 SSOT、Rust pull；G3-03 反之。完整設計詳
///   `h_state_cache::HStateCache` docstring。
pub type HStateCacheSlot = Arc<RwLock<Option<Arc<crate::h_state_cache::HStateCache>>>>;

/// G3-09 Phase A (2026-04-27): late-injected slot for the cost_edge_advisor
/// `Arc<CostEdgeAdvisor>`.
///
/// MODULE_NOTE (EN): Spawned only when env-gate
///   `OPENCLAW_COST_EDGE_ADVISOR=1` is set (DEFAULT-OFF). When disabled the
///   slot stays `None` and the IPC handler `get_cost_edge_advisor_status`
///   returns a structured `advisor_disabled` payload — never an error — so
///   Python callers (healthcheck [22], GUI) can render dormant state without
///   raising. Phase A advisory only — no hot-path consumer reads this slot.
///
///   Mirrors the G3-08 `HStateCacheSlot` pattern (env-gate + late-inject).
///
/// MODULE_NOTE (中)：advisor 只在 env-gate `OPENCLAW_COST_EDGE_ADVISOR=1` 時
///   spawn（DEFAULT-OFF）。關閉時 slot 維持 `None`，IPC handler
///   `get_cost_edge_advisor_status` 回結構化 `advisor_disabled` payload —
///   不報錯 — 讓 Python caller（healthcheck [22] / GUI）顯示 dormant
///   不 raise。Phase A 純 advisory，hot-path 不讀此 slot。
///
///   鏡射 G3-08 `HStateCacheSlot` pattern（env-gate + late-inject）。
pub type CostEdgeAdvisorSlot = Arc<RwLock<Option<Arc<crate::cost_edge_advisor::CostEdgeAdvisor>>>>;

/// F6 PH5-WIRE-1 RELOAD (2026-04-26): late-injected slot for the edge
/// estimates reloader's manual-trigger sender. Wraps a buffer-1
/// `tokio::sync::mpsc::Sender<()>` so multiple rapid IPC `reload_edge_estimates`
/// requests coalesce into a single fan-out.
///
/// MODULE_NOTE (EN): The reloader daemon spawns AFTER the IPC server detaches
///   (because all three pipeline `cmd_tx` must already exist for fan-out).
///   Slot pattern allows main.rs to late-inject the sender without restarting
///   IPC. The `reload_edge_estimates` IPC handler reads this slot per
///   connection (cheap Arc clone), reports `reloader_disabled` when None
///   (env=0 or no pipelines bound) and `accepted` / `coalesced` /
///   `reloader_closed` when set — same advisory shape as
///   `trigger_live_auth_recheck` (PIPELINE-SLOT-1 Phase 3).
///
/// MODULE_NOTE (中)：reloader daemon 在 IPC server detach 後 spawn（因為三條
///   pipeline cmd_tx 必須先就緒）。Slot pattern 讓 main.rs 不擾動運行中
///   IPC server 也能 late-inject sender。`reload_edge_estimates` IPC handler
///   每連線讀此 slot，None 時（env=0 或無 pipeline 綁定）回 `reloader_disabled`，
///   有值時依 `try_send` 結果回 `accepted` / `coalesced` / `reloader_closed`，
///   對齊 `trigger_live_auth_recheck`（PIPELINE-SLOT-1 Phase 3）advisory shape。
pub type EdgeReloadSenderSlot = Arc<RwLock<Option<tokio::sync::mpsc::Sender<()>>>>;

// =============================================================================
// Sprint N+1 W1 + W2 panel slot insertion anchors
// PA D+0 預留 anchor，避免 W1/W2 五個 E1 sub-agent 並行 IMPL 時撞 line collision
// 詳 srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md §6 + §7
// =============================================================================

// === W1 FundingCurvePanelSlot insertion point ===
// W1 E1-α (B-1) 在此下方加 `pub type FundingCurvePanelSlot = Arc<RwLock<Option<...>>>;`
// 對應 `panel.funding_rates_panel` (V085 migration) + Python collector

/// W-AUDIT-8a Phase B B-1: late-injected slot for FundingCurveSnapshot panel。
///
/// MODULE_NOTE：funding_curve panel aggregator 在 IPC server detach 後 spawn；
///   slot 用 `Arc<RwLock<Option<FundingCurveSnapshot>>>` 讓 main.rs late-inject。
///   None = uninitialized，dispatch step_4_5 取 None → surface.funding_curve
///   = None → declared FundingSkew tag 的策略 fail-closed 寫
///   evaluation_outcome='funding_panel_unavailable'（per W1 spec §2.4）。
///
///   Aggregator 負責 flush 寫 PG (audit) + write slot (hot path)；slot 寫入
///   是 latest snapshot replace 語意（不 append），dispatch step_4_5 直接
///   `RwLock::read().clone()` 取 Option<FundingCurveSnapshot>。
///
/// W1 sub-task 1 (本 PR) 階段：typedef declare only；late-inject 寫入由
/// sub-task 3 (E1-γ) 完成。
pub type FundingCurvePanelSlot =
    Arc<RwLock<Option<openclaw_core::alpha_surface::FundingCurveSnapshot>>>;

// === W1 OIDeltaPanelSlot insertion point ===
// W1 E1-β (B-2) 在此下方加 `pub type OIDeltaPanelSlot = Arc<RwLock<Option<...>>>;`
// 對應 `panel.oi_delta_panel` (V087 migration) + Python collector

/// W-AUDIT-8a Phase B B-2: late-injected slot for OIDeltaPanel。
///
/// MODULE_NOTE：oi_delta panel aggregator 在 IPC server detach 後 spawn；
///   slot 用 `Arc<RwLock<Option<OIDeltaPanel>>>` 讓 main.rs late-inject。
///   None = uninitialized，dispatch step_4_5 取 None → surface.oi_delta_panel
///   = None → declared OiDeltaPanel tag 的策略（bb_breakout）fail-closed 寫
///   evaluation_outcome='oi_panel_unavailable'（per W1 spec §4.1）。
///
///   Aggregator 負責 flush 寫 PG (audit) + write slot (hot path)；slot 寫入
///   是 latest snapshot replace 語意（不 append），dispatch step_4_5 直接
///   `RwLock::read().clone()` 取 Option<OIDeltaPanel>。
///
///   與 FundingCurvePanelSlot 區別：OIDeltaPanel.symbols / oi_abs / oi_delta_*_pct
///   是 Vec<...>（cross-symbol panel；25 sym 同一 snapshot），FundingCurveSnapshot
///   是 per-snapshot single value（funding_rate_bps / next_funding_ms）。
///
/// W1 sub-task 2 (本 PR) 階段：typedef declare only；late-inject 寫入由
/// sub-task 3 (E1-γ) 完成。
pub type OIDeltaPanelSlot =
    Arc<RwLock<Option<openclaw_core::alpha_surface::OIDeltaPanel>>>;

// === W2 BtcLeadLagPanelSlot insertion point ===
// W2 E1-δ (C-IMPL-2) 在此下方加 `pub type BtcLeadLagPanelSlot = Arc<RwLock<Option<...>>>;`
// 對應 `panel.btc_lead_lag_panel` (V088 migration) + BTC lead-lag aggregator
