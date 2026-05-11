//! IPC server test suite — split by topical area (IPC-SERVER-TESTS-SPLIT-1).
//! IPC 伺服器測試套件 — 按 topical 領域拆分（IPC-SERVER-TESTS-SPLIT-1）。
//!
//! ## 模組佈局（IPC-SERVER-TESTS-SPLIT-1, 2026-04-23）
//!
//! 本目錄 (`ipc_server/tests/`) 於 2026-04-23 由單一 1847 行
//! `ipc_server/tests.rs` 拆出，以遵守 §九 1200 行硬上限（舊檔超出 647 行）。
//! 拆分參照 `tick_pipeline/on_tick/` 的 sibling child-module pattern：
//! `mod.rs` 保留所有共用 fixture helpers（`make_test_config` /
//! `make_test_data_dir` / `empty_budget_slot` / `empty_teacher_slot` /
//! `write_test_snapshot`），各 sibling subfile 透過 `use super::*` 存取。
//! 零 test 新增/刪除 — 純機械 move，test name / assertions / id 一字不動，
//! 維持 1860 passed / 0 failed baseline。
//!
//! This directory was split from a single 1847-line `ipc_server/tests.rs`
//! on 2026-04-23 to honour §九's 1200-line hard cap (the old file exceeded
//! by 647 lines). The split follows the `tick_pipeline/on_tick/` sibling
//! child-module pattern: `mod.rs` owns the shared fixture helpers
//! (`make_test_config` / `make_test_data_dir` / `empty_budget_slot` /
//! `empty_teacher_slot` / `write_test_snapshot`); sibling subfiles access
//! them via `use super::*`. Zero tests were added or removed — pure
//! mechanical move, test names / assertions / ids unchanged, keeping the
//! 1860 passed / 0 failed baseline.
//!
//! ```text
//! ipc_server/tests/
//! ├── mod.rs          # 共用 fixture + re-export / shared fixtures + re-exports
//! ├── dispatch.rs     # dispatch / JSON-RPC 基本請求與 (de)serialization (10 tests)
//! │                   # dispatch / JSON-RPC basic request + (de)serialization
//! ├── snapshot.rs     # paper_state / latest_prices / tick_stats 快照讀取 (4 tests)
//! │                   # paper_state / latest_prices / tick_stats snapshot reads
//! ├── risk.rs         # risk_runtime_status + clear_losses + governor tier override (7 tests)
//! │                   # risk_runtime_status + clear_losses + governor tier override
//! ├── strategy.rs     # update/get_strategy_params + get_param_ranges (5 tests)
//! │                   # update/get_strategy_params + get_param_ranges
//! ├── phase4.rs       # get_phase4_status 儀表板骨架 (3 tests)
//! │                   # get_phase4_status dashboard skeleton
//! ├── config.rs       # ARCH-RC1 1C-2-C / LIVE-P2-1 統一 config IPC (8 tests)
//! │                   # ARCH-RC1 1C-2-C / LIVE-P2-1 unified config IPC
//! ├── budget.rs       # AI budget status/update/record_usage (7 tests)
//! │                   # AI budget status/update/record_usage
//! ├── teacher.rs      # Phase 4.1 teacher consumer loop (5 tests)
//! │                   # Phase 4.1 teacher consumer loop
//! ├── scanner.rs      # IPC-SCAN-1 get_active_symbols / get_scanner_status (4 tests)
//! │                   # IPC-SCAN-1 get_active_symbols / get_scanner_status
//! └── risk_update.rs  # E4-5 audit FUP: handle_update_risk_config (2 tests)
//!                     # E4-5 audit FUP: handle_update_risk_config
//! ```

use super::*;
use std::collections::HashMap;

mod budget;
mod config;
mod dispatch;
mod phase4;
mod risk;
mod risk_update;
mod scanner;
mod snapshot;
mod strategy;
mod teacher;

pub(super) fn make_test_config() -> Arc<ConfigManager> {
    Arc::new(ConfigManager::load(Some("/tmp/nonexistent_openclaw_ipc_test.toml")).unwrap())
}

pub(super) fn make_test_data_dir() -> Arc<PathBuf> {
    Arc::new(PathBuf::from("/tmp/oc_ipc_test_nonexistent"))
}

/// Empty BudgetTracker slot for tests that don't exercise 4-15 paths.
/// 給不演練 4-15 路徑的測試使用的空 BudgetTracker 槽位。
pub(super) fn empty_budget_slot() -> BudgetTrackerSlot {
    Arc::new(RwLock::new(None))
}

pub(super) fn empty_teacher_slot() -> TeacherLoopSlot {
    Arc::new(RwLock::new(None))
}

/// G3-08 H State Gateway Phase 1: empty cache slot for tests that don't
/// exercise the gateway path. Mirrors `empty_budget_slot` /
/// `empty_teacher_slot`.
/// G3-08 H State Gateway Phase 1：給未演練 gateway 路徑的測試使用的空 cache slot。
pub(super) fn empty_h_state_cache_slot() -> HStateCacheSlot {
    Arc::new(RwLock::new(None))
}

/// G3-09 Phase A: empty cost_edge_advisor slot for tests that don't
/// exercise the advisor path. Mirrors `empty_h_state_cache_slot`.
/// G3-09 Phase A：給未演練 advisor 路徑的測試使用的空 advisor slot。
pub(super) fn empty_cost_edge_advisor_slot() -> CostEdgeAdvisorSlot {
    Arc::new(RwLock::new(None))
}

/// LG-2 T3 (2026-05-11): 給未演練 query_fee_source 路徑的測試使用的空
/// AccountManager slot。對齊 `empty_cost_edge_advisor_slot` pattern。
pub(super) fn empty_account_manager_slot() -> super::slots::AccountManagerSlot {
    Arc::new(RwLock::new(None))
}

/// Write a test snapshot file to a temp dir, return the dir path.
/// 寫入測試快照文件到臨時目錄，返回目錄路徑。
pub(super) fn write_test_snapshot() -> (Arc<PathBuf>, tempfile::TempDir) {
    let dir = tempfile::tempdir().unwrap();
    let snapshot = PipelineSnapshot {
        schema_version: "2.0.0".into(),
        written_at_ms: 1700000050000,
        paper_state: crate::paper_state::PaperStateSnapshot {
            balance: 9500.0,
            initial_balance: 10000.0,
            peak_balance: 10000.0,
            total_realized_pnl: -500.0,
            total_fees: 12.5,
            total_funding_pnl: 0.0,
            trade_count: 3,
            positions: vec![crate::paper_state::PositionSnapshot {
                position: crate::paper_state::PaperPosition {
                    symbol: "BTCUSDT".into(),
                    is_long: true,
                    qty: 0.01,
                    entry_price: 65000.0,
                    best_price: 66000.0,
                    entry_fee: 3.25,
                    entry_ts_ms: 1700000000000,
                    unrealized_pnl: 10.0,
                    entry_context_id: String::new(),
                    owner_strategy: "test".into(),
                    entry_notional: 650.0,
                    max_favorable_pnl_pct: 0.0,
                    peak_reached_ts_ms: 1700000000000,
                },
                api_pnl: None,
            }],
            bybit_sync_balance: None,
        },
        latest_prices: HashMap::from([("BTCUSDT".into(), 66000.0), ("ETHUSDT".into(), 3200.0)]),
        stats: crate::tick_pipeline::TickStats {
            total_ticks: 5000,
            total_intents: 15,
            total_fills: 3,
            total_stops: 1,
            last_tick_ms: 1700000050000,
        },
        source: "rust_engine".into(),
        indicators: HashMap::new(),
        signals: vec![],
        strategies: vec![],
        recent_intents: vec![],
        recent_fills: vec![],
        klines: HashMap::new(),
        paper_paused: false,
        pipeline_kind: crate::tick_pipeline::PipelineKind::Paper,
        h0_gate_stats: None,
        stop_config: None,
        guardian_config: None,
        risk_manager_config: None,
        consecutive_losses: HashMap::new(),
        session_halted: false,
        daily_loss_pct: 0.0,
        session_drawdown_pct: 0.0,
        mode_snapshots: HashMap::new(),
        system_mode: "live_reserved".into(),
    };
    let json = serde_json::to_string_pretty(&snapshot).unwrap();
    std::fs::write(dir.path().join("pipeline_snapshot.json"), &json).unwrap();
    (Arc::new(dir.path().to_path_buf()), dir)
}
