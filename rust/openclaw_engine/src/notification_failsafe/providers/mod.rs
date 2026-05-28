//! Wave 5 Packet C / C3 — runtime providers stub mod root.
//!
//! 為什麼此檔現為 stub：PM 在派 E1-PC3 之前 pre-stage 本子模塊宣告，避免 4 E1
//! 並行衝突。E1-PC3 將補：
//!   - `position_provider.rs`：實 `PositionSnapshotProvider` — 從 `paper_state` 或
//!     Bybit REST `PositionManager::get_positions` 拉真實倉位 → map 為 `PositionSnapshot`
//!     （注意 PositionSnapshot.side 是 `&'static str`，必須在 caller 端 match "Buy" / "Sell"）
//!   - `exchange_stop_sync.rs`：實 `ExchangeStopSync` — wrap
//!     `PositionManager::set_trading_stop(TradingStopRequest)`；per-symbol Result
//!     回 mock-pattern 但對接真實 BybitRestClient
//!   - `wall_clock.rs`：實 `FailsafeClock::now_ms()`（chrono / std::time）
//!   - `single_watcher.rs`：對 operator Q4.1 拍 single shared，封裝給 main_pipelines 用
//!     （single instance with shared state，per AMD §Decision 3.1）
//!   - tests/：mock + integration
//!
//! 不變量（per CLAUDE.md §二 + §四）：
//!   - 不 panic 不 unwrap；REST error → ExchangeStopError::Transport / Rejected
//!   - 不繞 5-gate（不直接寫 Live；ExchangeStopSync 只在 active=true watcher 啟用後跑）
//!   - 倉位快照 timeout 硬限，避免阻塞 watcher 主迴圈
//!
//! ref: docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §4
