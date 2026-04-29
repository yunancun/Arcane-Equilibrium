//! G3-09 cost_edge_advisor boot-time wiring (extracted from main.rs +
//! main_boot_tasks.rs).
//! G3-09 cost_edge_advisor 啟動期接線（從 main.rs + main_boot_tasks.rs 抽出）。
//!
//! MODULE_NOTE (EN): Sibling module to `main_boot_tasks` (intentionally NOT
//!   `cost_edge_advisor::boot` to avoid pulling boot-time deps —
//!   ``ipc_server`` slot types, ``risk_stores``, env-gated tokio spawn — into
//!   the engine library crate; sibling pattern keeps ``cost_edge_advisor``
//!   library-only). Holds two pieces:
//!     1. ``CostEdgeAdvisorDbSlot`` type alias — ``Arc<RwLock<Option<DbPool>>>``
//!        for the late-injected DbPool handoff between main.rs and the
//!        cost_edge_advisor daemon.
//!     2. ``spawn_cost_edge_advisor_if_enabled`` — env-gated 3-stage spawn
//!        (advisor handle inject → wait for h_state_cache slot → wait for
//!        DbPool slot up to 30s → spawn periodic poll daemon).
//!
//!   Pure refactor of G3-09 Phase B Wave 1 land — 0 production behavior
//!   change. Splits to bring `main.rs` under §九 1200-line hard limit
//!   (1230 → ~1010) and `main_boot_tasks.rs` back near §九 800-line warn
//!   line (1015 → ~865).
//!
//! MODULE_NOTE (中): `main_boot_tasks` 的 sibling 模組（**不**放
//!   `cost_edge_advisor::boot` 以免將啟動期依賴 — ipc_server slot type、
//!   risk_stores、env-gated tokio spawn — 拉進 engine library crate；sibling
//!   pattern 讓 ``cost_edge_advisor`` 純 library）。包含：
//!     1. ``CostEdgeAdvisorDbSlot`` type alias — ``Arc<RwLock<Option<DbPool>>>``
//!        late-inject 通道（main.rs ↔ cost_edge_advisor daemon）。
//!     2. ``spawn_cost_edge_advisor_if_enabled`` — env-gated 三階段 spawn
//!        （advisor handle 注入 → 等 h_state_cache slot → 最多 30s 等
//!        DbPool slot → spawn 定期 poll daemon）。
//!
//!   純 G3-09 Phase B Wave 1 已落地碼之 location refactor — 0 production
//!   behavior 變化。為將 `main.rs` 壓在 §九 1200 行硬上限下（1230 → ~1010）+
//!   讓 `main_boot_tasks.rs` 回到 §九 800 行 warn 線附近（1015 → ~865）。

use openclaw_engine::config::{ConfigStore, RiskConfig};
use openclaw_engine::cost_edge_advisor::{
    is_advisor_env_enabled, spawn_cost_edge_advisor_with_persistence, CostEdgeAdvisor,
    DEFAULT_POLL_INTERVAL as COST_EDGE_DEFAULT_POLL_INTERVAL,
};
use openclaw_engine::database::pool::DbPool;
use openclaw_engine::ipc_server::{CostEdgeAdvisorSlot, HStateCacheSlot, PerEngineRiskStores};
use std::sync::Arc;
use std::time::Duration;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

const H_STATE_CACHE_SLOT_TIMEOUT_WARNING: &str = "cost_edge_advisor: h_state_cache_slot never populated after 10s; daemon NOT spawned (G3-08 env-gate likely off; G3-09 advisor needs H5 snapshot to function) / cost_edge_advisor: h_state_cache 10s 內未注入；daemon 未 spawn";

/// Late-injected DbPool slot type for the cost_edge_advisor daemon.
/// cost_edge_advisor daemon 用的 late-injected DbPool slot type。
///
/// EN: Mirrors `HStateCacheSlot` pattern — daemon polls the slot at spawn
///   time and proceeds with persistence only once main.rs writes the pool
///   handle (post `DbPool::connect`). When the slot stays empty after 30s
///   the daemon spawns **without** persistence (in-memory counters only).
///
/// 中：對齊 ``HStateCacheSlot`` pattern — daemon 於 spawn 時 poll slot，
///   main.rs 在 ``DbPool::connect`` 完成後寫入 pool handle，daemon 才啟動
///   persistence。slot 30s 仍空 → daemon **不啟用** persistence 直接 spawn
///   （counter 仍 in-memory tick）。
pub type CostEdgeAdvisorDbSlot = Arc<tokio::sync::RwLock<Option<Arc<DbPool>>>>;

/// Construct a fresh, empty `CostEdgeAdvisorDbSlot`.
/// 建立一個全新空的 `CostEdgeAdvisorDbSlot`。
///
/// EN: Tiny helper used by main.rs to keep boot-time wiring tidy. The slot
///   is intentionally created BEFORE `DbPool::connect` so we can pass an
///   ``Arc`` clone into ``spawn_cost_edge_advisor_if_enabled`` and
///   late-inject the pool once it is ready.
///
/// 中：main.rs 用的小幫手，將 slot 建立與 daemon spawn 解耦。slot 於
///   ``DbPool::connect`` 前建立，傳 ``Arc`` clone 給
///   ``spawn_cost_edge_advisor_if_enabled``，pool 連線完成後 late-inject。
#[inline]
pub(crate) fn create_db_pool_slot() -> CostEdgeAdvisorDbSlot {
    Arc::new(tokio::sync::RwLock::new(None))
}

/// Late-inject the connected `DbPool` into the cost_edge_advisor daemon's
/// slot. Called by main.rs immediately after `DbPool::connect` returns.
/// 將連線完成的 `DbPool` late-inject 至 cost_edge_advisor daemon 的 slot；
/// main.rs 於 `DbPool::connect` 完成後立即呼叫。
///
/// EN: Unconditional + safe — the daemon's INSERT path internally checks
///   ``pool.get()`` and silently skips persistence when None, so injecting
///   even an unusable pool causes no harm.
///
/// 中：無條件注入；daemon INSERT path 內部檢查 ``pool.get()``，None 時
///   靜默跳過 persistence，注入不可用的 pool 亦無害。
#[inline]
pub(crate) async fn inject_db_pool(slot: &CostEdgeAdvisorDbSlot, pool: &Arc<DbPool>) {
    *slot.write().await = Some(Arc::clone(pool));
}

/// G3-09 Phase A (2026-04-27): conditionally spawn the cost_edge_advisor
/// daemon, gated by `OPENCLAW_COST_EDGE_ADVISOR=1`.
///
/// EN: DEFAULT-OFF: when env var missing or any value other than `"1"`
///   (strict comparison) this fn returns immediately, allocating zero
///   memory and spawning zero tasks. Mirrors `spawn_h_state_poller_if_enabled`
///   pattern for structural consistency.
///
///   When env=1: build `Arc<CostEdgeAdvisor>` (initial Uninitialized state),
///   late-inject into `IpcServer::cost_edge_advisor_slot()`, then spawn the
///   periodic poll daemon. Daemon polls H state cache every 10s + evaluates
///   threshold + emits transition logs.
///
///   Dual safeguard (PA RFC §9.2): even when env=1, daemon respects
///   `RiskConfig.cost_edge.enabled` flag — when false, advisor enters
///   Disabled state and short-circuits H state read.
///
///   The daemon takes a clone of the demo `Arc<ConfigStore<RiskConfig>>`
///   per PA RFC §8 (cross-env config independence; demo is the canonical
///   read source for ratio because demo is the main edge accumulation per
///   memory `feedback_demo_over_paper_for_edge`). Phase B/C may extend to
///   per-env advisors.
///
/// 中：DEFAULT-OFF：env 未設或非 `"1"` 時立即回 `None`，0 記憶體 0 task。
///   對齊 `spawn_h_state_poller_if_enabled` pattern。env=1 時建
///   `Arc<CostEdgeAdvisor>`、late-inject 到 IpcServer slot，spawn 每 10s
///   poll daemon。雙保險（RFC §9.2）：env=1 仍須 `RiskConfig.cost_edge.enabled
///   = true` 才完整 evaluate；false 走 Disabled short-circuit。
///   Daemon 取 demo `ConfigStore<RiskConfig>` clone（RFC §8 cross-env 獨立；
///   demo 為 ratio canonical read source，per memory
///   `feedback_demo_over_paper_for_edge`）。Phase B/C 可擴 per-env advisor。
pub(crate) fn spawn_cost_edge_advisor_if_enabled(
    advisor_slot: &CostEdgeAdvisorSlot,
    h_state_cache_slot: &HStateCacheSlot,
    risk_stores: &PerEngineRiskStores,
    cancel: &CancellationToken,
    // Phase B (G3-09 2026-04-28): late-injected DbPool slot. main.rs
    // pre-creates the slot, calls this fn (which spawns a poller task),
    // then writes the pool handle once `DbPool::connect` returns. The
    // daemon's INSERT path activates as soon as the slot is populated;
    // up to that point the cycle counters still tick (in-memory only).
    // Phase B：late-injected DbPool slot。main.rs 預建 slot，呼叫本 fn
    // （spawn 一個 poller task），DbPool 連線完寫入 slot；slot 寫入後
    // daemon INSERT path 啟動，在此之前 counter 仍 in-memory tick。
    db_pool_slot: &CostEdgeAdvisorDbSlot,
) {
    if !is_advisor_env_enabled() {
        // Zero-overhead path / 零負擔路徑
        info!(
            "cost_edge_advisor disabled (OPENCLAW_COST_EDGE_ADVISOR != \"1\"), daemon not spawned \
             / cost_edge_advisor 未啟用，daemon 未啟動",
        );
        return;
    }

    // Daemon needs an Arc<HStateCache>. Read the slot synchronously at boot
    // time — when env-gate G3-09 is on we expect G3-08 H State Gateway also
    // on (cost_edge_advisor is meaningless without H5 snapshot data).
    // Daemon 需 Arc<HStateCache>。Boot 時同步讀 slot — G3-09 env-gate 開時
    // 預期 G3-08 H State Gateway 也開（advisor 沒 H5 資料就無意義）。
    let h_state_cache_slot_clone = Arc::clone(h_state_cache_slot);
    let db_pool_slot_clone = Arc::clone(db_pool_slot);
    let advisor = CostEdgeAdvisor::new_arc();
    let advisor_clone = Arc::clone(&advisor);
    let advisor_slot_clone = Arc::clone(advisor_slot);

    // Demo store is the canonical risk source per PA RFC §8 (memory
    // `feedback_demo_over_paper_for_edge` — demo is the main edge
    // accumulation environment, paper is exploration noise).
    // Demo store 為 canonical risk source（RFC §8 + memory：demo 為主 edge
    // 累積、paper 為探索噪音）。
    let risk_demo: Arc<ConfigStore<RiskConfig>> = Arc::clone(&risk_stores.demo);

    let cancel_for_task = cancel.clone();

    // Two-stage spawn: (1) inject advisor handle into IPC slot so handler
    // can read state immediately (returns Uninitialized until first poll
    // cycle stores OK/Trigger/...). (2) spawn the daemon, but ONLY after
    // h_state_cache slot is populated (poll await loop).
    // 兩階段 spawn：(1) 注入 advisor handle 到 IPC slot（首輪 poll 前
    // handler 讀回 Uninitialized）；(2) spawn daemon，但需等 h_state_cache
    // slot 寫入完成。
    tokio::spawn(async move {
        // Step (1): inject advisor handle into IPC slot.
        // 步驟 (1)：注入 advisor handle 到 IPC slot。
        advisor_slot_clone
            .write()
            .await
            .replace(Arc::clone(&advisor_clone));

        // Step (2): wait for h_state_cache slot to be populated by
        // spawn_h_state_poller_if_enabled. Poll every 100ms up to 10s.
        // 步驟 (2)：等 h_state_cache slot 由 spawn_h_state_poller_if_enabled
        // 寫入；100ms poll 一次最多 10s。
        let h_state_cache = {
            let mut attempts = 0u32;
            loop {
                if let Some(c) = h_state_cache_slot_clone.read().await.as_ref() {
                    break Arc::clone(c);
                }
                attempts += 1;
                if attempts > 100 {
                    warn!("{}", H_STATE_CACHE_SLOT_TIMEOUT_WARNING);
                    return;
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        };

        // Phase B (G3-09 2026-04-28) Step (2.5): wait up to 30s for the
        // DbPool slot to populate. main.rs creates the pool ~lines below
        // 510 (between IPC server detach and writer-task init); 30s is
        // a generous bound that allows for slow PG handshake without
        // blocking the daemon spawn forever. If the slot stays empty
        // (DbPool not configured / paper mode without DB), spawn the
        // daemon **without** persistence — counters still maintained.
        // Phase B Step (2.5)：最多等 30s 給 DbPool slot 寫入。main.rs 建 pool
        // 在 line 510 下方（IPC server detach 與 writer-task init 之間）；
        // 30s 寬鬆讓 PG handshake 慢時不無限 block daemon spawn。slot 一直
        // 空（DbPool 未配 / paper 無 DB）時 daemon **不啟用** persistence
        // 仍 spawn，counter 仍維護。
        let db_pool: Option<Arc<DbPool>> = {
            let mut attempts = 0u32;
            loop {
                if let Some(pool) = db_pool_slot_clone.read().await.as_ref() {
                    break Some(Arc::clone(pool));
                }
                attempts += 1;
                if attempts > 300 {
                    // 30s elapsed (300 × 100ms) — proceed without persistence.
                    // 超過 30s — 不啟用 persistence 直接 spawn。
                    warn!(
                        "cost_edge_advisor: db_pool_slot not populated after 30s; \
                         spawning daemon WITHOUT learning.cost_edge_advisor_log \
                         persistence (Phase B observability degrades to in-memory \
                         counters only) / cost_edge_advisor: db_pool_slot 30s 內未注入；\
                         daemon 不啟用 persistence 直接 spawn（Phase B observability 降級為\
                         記憶體 counter only）"
                    );
                    break None;
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        };

        // Determine engine_mode label from the demo store binding (advisor
        // is per-engine via demo store; "demo" is the canonical choice
        // unless operator explicitly switches). Stamped into every INSERT
        // row so ratio histograms split correctly per environment.
        // 從 demo store binding 推 engine_mode 標籤（advisor 以 demo store
        // per-engine；除非 operator 顯式切換，"demo" 為 canonical 選擇）。
        // 蓋章到每筆 INSERT row 讓 ratio histogram 跨環境正確切分。
        // RFC §6.1 R-B9：advisor 在 spawn 時 bind engine_mode；mid-run 不變。
        let engine_mode = "demo".to_string();

        // Step (3): spawn the daemon now that all dependencies are ready.
        // 步驟 (3)：依賴全到位後 spawn daemon。
        let _handle = spawn_cost_edge_advisor_with_persistence(
            advisor_clone,
            h_state_cache,
            risk_demo,
            COST_EDGE_DEFAULT_POLL_INTERVAL,
            cancel_for_task,
            db_pool,
            engine_mode,
        );

        info!(
            poll_interval_ms = COST_EDGE_DEFAULT_POLL_INTERVAL.as_millis() as u64,
            // Phase tag advanced from "A_advisory" → "B_shadow" by Phase B
            // Wave 1 land. Still 0 trade impact — Phase B is observation only;
            // Phase C will do shadow IntentProcessor reject check.
            // Phase 標籤隨 Phase B Wave 1 推進到 "B_shadow"；仍 0 trade impact —
            // Phase B 純觀察，Phase C 才做 shadow IntentProcessor reject 檢查。
            phase = "B_shadow",
            "cost_edge_advisor spawned (env=1) — Phase B observation only \
             (no IntentProcessor wiring) / cost_edge_advisor 已啟動（env=1）— \
             Phase B 純觀察（不接 IntentProcessor）"
        );
    });
}

#[cfg(test)]
mod tests {
    use super::H_STATE_CACHE_SLOT_TIMEOUT_WARNING;

    #[test]
    fn h_state_timeout_warning_mentions_h5_dependency_and_no_spawn() {
        assert!(H_STATE_CACHE_SLOT_TIMEOUT_WARNING.contains("h_state_cache_slot never populated"));
        assert!(H_STATE_CACHE_SLOT_TIMEOUT_WARNING.contains("daemon NOT spawned"));
        assert!(H_STATE_CACHE_SLOT_TIMEOUT_WARNING.contains("H5 snapshot"));
    }
}
