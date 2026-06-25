//! OpenClaw Engine — trading engine main body (R01).
//! OpenClaw 引擎 — 交易引擎主體。
//!
//! MODULE_NOTE (EN): Library crate re-exporting engine modules: config (ArcSwap hot-reload),
//!   ipc_server (Unix socket JSON-RPC 2.0), ws_client (Bybit WS with auto-reconnect).
//!   The binary entry point is in main.rs.
//! MODULE_NOTE (中): 庫 crate 重新導出引擎模組：config（ArcSwap 熱加載）、
//!   ipc_server（Unix 套接字 JSON-RPC 2.0）、ws_client（Bybit WS 自動重連）。
//!   二進制入口在 main.rs。

// P2-CLIPPY-CLEANUP-1：先把 Apple Silicon `cargo clippy -- -D warnings`
// gate 恢復為可執行；本 checkpoint 不重寫歷史文檔與交易路徑複雜度。
// 未列入的新增 lint 類別仍會失敗，需後續明確審查才可加入 allowlist。
#![allow(
    clippy::borrow_deref_ref,
    clippy::collapsible_if,
    clippy::collapsible_match,
    clippy::derivable_impls,
    clippy::doc_lazy_continuation,
    clippy::doc_overindented_list_items,
    clippy::drain_collect,
    clippy::empty_line_after_doc_comments,
    clippy::explicit_auto_deref,
    clippy::field_reassign_with_default,
    clippy::large_enum_variant,
    clippy::len_without_is_empty,
    clippy::manual_clamp,
    clippy::manual_contains,
    clippy::manual_inspect,
    clippy::manual_is_multiple_of,
    clippy::manual_range_patterns,
    clippy::match_like_matches_macro,
    clippy::needless_borrow,
    clippy::neg_cmp_op_on_partial_ord,
    clippy::new_without_default,
    clippy::question_mark,
    clippy::redundant_closure_call,
    clippy::result_large_err,
    clippy::should_implement_trait,
    clippy::too_many_arguments,
    clippy::type_complexity,
    clippy::unnecessary_map_or,
    clippy::unwrap_or_default,
    clippy::useless_conversion,
    clippy::useless_format
)]

pub mod account_manager;
pub mod agent_spine;
pub mod ai_budget;
pub mod ai_service_client;
// PA daily-kline backfill（2026-06-02）：日線歷史回填（timeframe='1d'）— 分頁取數 +
// C-3 strict-parse（fake-zero/非有限/損壞 bar 不寫）+ market.klines/provenance 寫層。
pub mod backfill;
// Sprint 1B Earn first stake B3（2026-05-23）：Flexible Saving only / 5 endpoint
// 走共用 BybitRestClient（HMAC + rate limit + retCode 觀測）。
pub mod bybit_earn_client;
pub mod bybit_private_ws;
pub mod bybit_private_ws_status_writer;
pub mod bybit_rest_client;
pub mod bounded_probe_active_order;
pub mod bounded_probe_near_touch;
pub mod canary_writer;
pub mod claude_teacher;
pub mod combine_layer;
pub mod common;
pub mod config;
pub mod cost_edge_advisor;
// Sprint 1B Earn first stake (2026-05-23)：cron-like scheduler 命名空間。
// 首個成員 `cron::earn_reconciliation` 每日 UTC 02:00 對 Bybit Earn 餘額 vs
// V100 `learning.earn_movement_log` 做 reconciliation。
pub mod cron;
pub mod database;
pub mod decision_context_producer;
pub mod demo_learning_lane;
pub mod demo_learning_lane_hot_path;
pub mod demo_learning_lane_ledger;
pub mod demo_learning_lane_writer;
#[cfg(test)]
mod demo_learning_lane_hot_path_tests;
#[cfg(test)]
mod demo_learning_lane_tests;
pub mod drawdown_revoke;
pub mod dynamic_risk_sizer;
pub mod edge_estimates;
pub mod edge_predictor;
pub mod event_consumer;
pub mod execution_listener;
pub mod exit_features;
pub mod fast_track;
pub mod feature_collector;
pub mod h_state_cache;
// P0-ENGINE-HALTSESSION-STUCK-FIX (2026-05-19): halt forensic logger.
// P0-ENGINE-HALTSESSION-STUCK-FIX（2026-05-19）：halt 取證記錄器。
pub mod halt_audit;
// Sprint 1A-ζ Phase 2 Track A：M1 Decision Lease LAL state machine skeleton。
// Sub-module `lal` 含 LalTier enum / from_i32 / numeric_value / Tier 0→1 transition stub
// + Tier 0 fill RETIRED blocker stub（per ADR-0034 Decision 6）。
pub mod governance;
// Sprint 1A-ζ Phase 2 Track B：M3 health monitoring 4-state ladder skeleton。
// engine_runtime domain IMPL + 5 stub (per ADR-0042 Decision 3) + amplification
// cap (per ADR-0042 Decision 4 + ADR-0036 1-anomaly = 1-state-change/24h)。
pub mod health;
pub mod instrument_info;
pub mod intent_processor;
pub mod ipc_server;
pub mod linucb;
pub mod live_authorization;
// LG-2 T2 (2026-05-11)：Live spawn pricing binding assertion module。
// build_exchange_pipeline 對 Live (Mainnet + LiveDemo) 路徑加裝的 pre-check。
pub mod live_spawn_assert;
pub mod market_data_client;
pub mod ml;
pub mod mode_state;
// Sprint 1A-δ M5：ModelClient trait stub（6 method default panic）per ADR-0035。
pub mod model_client;
pub mod multi_interval_topics;
pub mod news;
// Wave 5 Packet C engine integration (2026-05-28) — wires
// `RiskEvent::NotificationFailsafeTimeout` to engine副作用鏈：3-way fail observe
// → 1h timer → SM-04 Defensive → active lock-profit → exchange conditional SL
// sync → audit emit `auto_escalated_to_sm04_defensive`。純邏輯 + 5 trait seam
// + 14 條 unit/integration mock 測試；尚未接 pipeline_ctor / tasks (下一 wave)。
pub mod notification_failsafe;
pub mod orchestrator;
pub mod order_manager;
// Sprint 1A-δ M12：OrderRouter trait stub（6 method default panic）per ADR-0039。
pub mod order_router;
pub mod paper_state;
// Sprint N+1 W1 + W2：cross-asset / cross-strategy panel aggregator namespace
// （funding_curve / oi_delta / btc_lead_lag panel collector + producer）。
pub mod panel_aggregator;
pub mod persistence;
pub mod pipeline_types;
pub mod platform_client;
pub mod position_manager;
pub mod position_reconciler;
pub mod position_risk_evaluator;
pub mod regime;
// REF-20 Wave 1 R20-P0-T3 — replay subsystem scaffold (spec only, no IMPL).
// Wave 3 R20-P2b-S7/S8/S9/S10 will add forbidden_guard + mac_policy_guard.
// REF-20 Wave 1 R20-P0-T3 — replay 子系統骨架（純規格，無 IMPL）。
// Wave 3 R20-P2b-S7/S8/S9/S10 將加 forbidden_guard + mac_policy_guard。
pub mod replay;
pub mod restart_kind;
pub mod risk_checks;
pub mod risk_cusum;
pub mod scanner;
pub mod secret_env;
// P0-LG-3 Wave 2.4.A T4：supervised-live 不可變稽核軌跡 writer（V104 supervised_live_audit）。
// T1 後續另加 `pub mod supervised_live_sm;`（SM 核心），兩者檔案零 overlap。
pub mod supervised_live_audit_writer;
pub mod strategies;
pub mod strategist_scheduler;
// LG-3 Wave 2.4.A T1（2026-05-30）：supervised-live 7-state 狀態機核心。
// supervised-live session 的 control-plane meta state（SoT #1）+ 30s 5-SoT 對賬
// reconciler。純狀態機，不下單、不繞 5-gate live 邊界、不繞 Decision Lease；
// audit 經 `AuditSink` trait seam 接 T4 的 V104 writer（T1 不寫 V104/writer 本體）。
pub mod supervised_live_sm;
pub mod tick_pipeline;
pub mod ws_client;
pub mod ws_unknown_handler_guard;

pub use openclaw_core;
pub use openclaw_types;

// P1-OPS-2-CI-FLAKINESS-TEST-LOCK（2026-05-29）：全 crate 共用的 env-mutating
// 測試互鎖。
//
// 為什麼必要：`cargo test --lib` 把 lib crate 的所有 `#[cfg(test)]` 測試編進
// 「單一」測試 binary，預設多執行緒並行跑。`std::env::set_var` /
// `std::env::remove_var` 是 process 全局且非執行緒安全（Rust 2024 起更直接
// 標 set_var 為 unsafe）。若各 module 各自宣告一把 local Mutex，A module 持
// 自己的鎖並不會排除 B module 持「另一把」鎖 → 兩者同時改 process env 仍 race
// （latent；24/24 實測未觸但 UB 存在）。本 module 提供單一入口，所有 lib 測試
// 統一鎖它，跨 module 真正串行。
//
// 邊界：僅涵蓋 lib 測試 binary。bin crate（main.rs + main_boot_tasks /
// live_auth_watcher / startup 等 `mod` 兄弟）是「獨立」compilation unit + 獨立
// 測試 process，無法存取本 `#[cfg(test)]` pub(crate) 項，也不與 lib 測試共享
// static，故不在此鎖範圍內（各自仍用其 module-local guard）。
#[cfg(test)]
pub(crate) mod test_env_lock {
    /// 全 crate（lib 測試 binary）唯一的 env-mutating 測試互鎖。
    static ENV_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    /// 取共用鎖；poisoned（前一測試 panic 留下）時用 `into_inner` 強解 —
    /// 測試場景下毒化不影響 prod，且強解才能讓後續測試繼續串行而非連鎖 panic。
    pub(crate) fn guard() -> std::sync::MutexGuard<'static, ()> {
        ENV_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner())
    }
}
