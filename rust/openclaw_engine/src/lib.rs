//! OpenClaw Engine — trading engine main body (R01).
//! OpenClaw 引擎 — 交易引擎主體。
//!
//! MODULE_NOTE (EN): Library crate re-exporting engine modules: config (ArcSwap hot-reload),
//!   ipc_server (Unix socket JSON-RPC 2.0), ws_client (Bybit WS with auto-reconnect).
//!   The binary entry point is in main.rs.
//! MODULE_NOTE (中): 庫 crate 重新導出引擎模組：config（ArcSwap 熱加載）、
//!   ipc_server（Unix 套接字 JSON-RPC 2.0）、ws_client（Bybit WS 自動重連）。
//!   二進制入口在 main.rs。

pub mod account_manager;
pub mod ai_budget;
pub mod ai_service_client;
pub mod bybit_private_ws;
pub mod bybit_rest_client;
pub mod claude_teacher;
pub mod config;
pub mod database;
pub mod decision_context_producer;
pub mod edge_estimates;
pub mod edge_predictor;
pub mod event_consumer;
pub mod execution_listener;
pub mod fast_track;
pub mod feature_collector;
pub mod instrument_info;
pub mod intent_processor;
pub mod ipc_server;
pub mod linucb;
pub mod market_data_client;
pub mod ml;
pub mod mode_state;
pub mod multi_interval_ws;
pub mod news;
pub mod orchestrator;
pub mod order_manager;
pub mod paper_state;
pub mod persistence;
pub mod pipeline_types;
pub mod platform_client;
pub mod position_manager;
pub mod position_reconciler;
pub mod position_risk_evaluator;
pub mod risk_checks;
pub mod scanner;
pub mod strategies;
pub mod strategist_scheduler;
pub mod tick_pipeline;
pub mod ws_client;

pub use openclaw_core;
pub use openclaw_types;
