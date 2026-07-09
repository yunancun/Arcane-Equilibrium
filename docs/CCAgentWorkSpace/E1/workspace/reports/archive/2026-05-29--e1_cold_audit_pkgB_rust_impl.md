# E1 IMPL — Cold Audit Package B (Rust side) · 2026-05-29

Role: E1. Scope: Rust-only (`rust/openclaw_engine/`). Python call-site owned by a
separate E1. PA spec: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--cold_audit_pkgB_exchange_semantics_spec.md`.
Findings: P1-03 (Rust side), P1-06, P1-07, P1-08, P2-02, P2-03. NOT committed (chain E1→E2→E4→QA→PM).

## 1. Files changed + LOC (net additions, surgical)

| File | Finding(s) | What |
|---|---|---|
| `bybit_rest_client.rs` | P1-08, P2-03 | is_live_slot env-cred guard; group_reset_ms + path-aware wait_if_rate_limited + group threshold |
| `order_manager.rs` | P1-03, P2-02 | `cancel_all_scoped(category, symbol, settle_coin)`; amend fail-closed on spec miss + round SL/TP/trigger |
| `position_manager.rs` | P1-06 | `instruments` field + `new(client, instruments)`; `TradingStopRequest.side_is_long`; set_trading_stop normalizes every price field |
| `instrument_info.rs` (+`_tests.rs`) | P1-06 | new free fn `normalize_trading_stop_price`; 6 unit tests |
| `tick_pipeline/mod.rs` | P1-03 | `PipelineCommand::CancelAllOrders{category,settle_coin}`; `cancel_all_order_mgr` field |
| `tick_pipeline/pipeline_ctor.rs` / `pipeline_helpers.rs` | P1-03 | init None; `set_cancel_all_order_mgr` / `cancel_all_order_mgr` getter |
| `event_consumer/dispatch.rs` | P1-03, P1-07 | inject order_mgr Arc into pipeline; OPEN single-attempt (empty slice); delete `RETRY_DELAY_MS` |
| `event_consumer/dispatch_tests.rs` | P1-07 | rewrite const tests; +2 OPEN single-attempt tests |
| `event_consumer/loop_handlers.rs` | P1-03 | async intercept `CancelAllOrders` → cancel_all_scoped |
| `event_consumer/handlers/mod.rs` | P1-03 | defensive log-only arm for match exhaustiveness |
| `event_consumer/bootstrap.rs` | P1-03, P1-06 | (P1-03 N/A here) PositionManager::new(client, instruments) + side_is_long=req.is_long |
| `notification_failsafe/providers/exchange_stop_sync.rs` | P1-06 | side_is_long from adjustment.side; test updated |
| `tasks.rs`, `startup/mod.rs` | P1-06 | PositionManager::new fan-out (empty default cache; these paths don't set stops) |
| `ipc_server/dispatch.rs` | P1-03 | `"cancel_all_orders"` JSON-RPC arm |

## 2. cancel_all_orders IPC + PipelineCommand wiring (as implemented)

- IPC arm `ipc_server/dispatch.rs`: `"cancel_all_orders"` reads `category` (default `linear`),
  `settle_coin` (default `USDT`), `extract_engine_tx` → `handle_paper_cmd(id, &tx,
  PipelineCommand::CancelAllOrders{category, settle_coin}, "cancel_all_sent")`. Mirrors `close_all_positions`.
- `PipelineCommand::CancelAllOrders{category, settle_coin}` — fire-and-forget, no response_tx (like CloseAll).
- Handle reachability (PA's flagged unknown — RESOLVED): pipeline does NOT own an OrderManager
  (`ipc_close_all` enqueues OrderDispatchRequest). cancel-all is `/v5/order/cancel-all`, not an
  OrderDispatchRequest. Solution: in `spawn_order_dispatch` the existing `order_mgr` Arc (built from
  shared_client at the line PA cited) is cloned into the pipeline via `set_cancel_all_order_mgr`
  BEFORE the spawn move — REUSES the shared live client, no new client.
- Execution path = async intercept in `loop_handlers::handle_pipeline_command` (NOT the sync
  `handle_paper_command`). DEVIATION from PA spec (PA said handlers/mod.rs match arm), because
  `handle_paper_command` is sync and cancel-all is a real `.await` REST call — same pattern as
  ResetDrawdownBaseline/DisableEdgePredictorAll. Paper mode (no mgr) = log only. Unknown category =
  fail-closed skip. NOT gated by execution_authority (works post-revoke). Failure = warn, no retry.

## 3. Retry policy diff (P1-07)

- OPEN (`req.is_close==false`): now `const OPEN_NO_RETRY: [u64;0] = []` → `run_dispatch_retry` returns
  TransientExhausted after attempt 1 (0 retries). Any timeout/parse/transport/nonzero retCode →
  fail-closed; lease released `LeaseOutcome::Failed` (non-Consumed) via the unchanged Structural/
  TransientExhausted arms; no second create.
- CLOSE (`req.is_close==true`): UNCHANGED `CLOSE_RETRY_DELAY_MS=[100,400]` (2 retries) — documented
  reduce-only idempotent exception (principle 5).
- `RETRY_DELAY_MS=[200,800,3200]` const DELETED (no production caller; rg clean). NoOp classifications kept.
- Tests: `test_retry_delay_constants` now pins CLOSE only; `test_close_retry_delay_constants` drops
  RETRY_DELAY_MS comparison; +2 new tests (OPEN transient + structural = attempts==1, single place call).

## 4. Normalizer signature + threading (P1-06)

`pub fn normalize_trading_stop_price(cache: &InstrumentInfoCache, symbol: &str, price: f64,
side_is_long: Option<bool>, is_stop_loss: bool) -> Option<f64>`. SL long→floor, SL short→ceil,
TP/trailing/active→nearest round, side None→nearest round. Missing spec OR rounded==0.0/non-finite → None
(caller fail-closed: skip exchange stop, keep local StopManager, warn). `set_trading_stop` normalizes
every price field. `PositionManager::new(client, instruments)`. Two PA call sites threaded: bootstrap.rs
(dual-rail stop, side_is_long=req.is_long) + exchange_stop_sync.rs (side from adjustment.side "Buy"/"Sell").
Note: step_4_5_dispatch needed NO change — it only builds StopRequest (carries is_long); side lands at the
bootstrap consumer. Extra fan-out (constructor required): tasks.rs reconciler + startup seed use empty
default cache (those paths query/close positions, never set stops).

## 5. cargo (honest; Mac advisory, E4 Linux authoritative)

- `cargo build -p openclaw_engine`: PASS (exit 0).
- `cargo test -p openclaw_engine --lib`: 3583 passed, 0 failed, 1 ignored (baseline 3569 + new). The 8
  new tests (6 normalizer + 2 OPEN single-attempt) verified passing individually.
- `cargo clippy -p openclaw_engine --no-deps`: my diff lines = 0 hits. Two `empty line after doc comment`
  warnings (pipeline_helpers.rs:657 orphan `set_trading_mode` doc, commands.rs:1606) are PRE-EXISTING,
  outside my diff — not touched (minimal impact).

## 6. Blockers

- None hard. The OrderManager handle reachability PA flagged is RESOLVED (reuse spawn_order_dispatch's
  order_mgr Arc; no new client). One DEVIATION to confirm in review: cancel-all intercepted in async
  loop_handlers, not sync handlers/mod.rs (justified by await requirement).
- End-to-end IPC probe + live cancel-all are deploy/operator-gated (out of scope per CLAUDE.md §六).

## 7. Handoff to E2

Review focus per PA E2-top-3: (1) cancel-all not behind execution_authority + reuses live client + no
Python REST fallback; confirm async-intercept deviation acceptable. (2) OPEN single-attempt + lease
released non-Consumed; CLOSE exception only retained retry. (3) P1-06 dual-rail: missing spec → exchange
stop skipped, local stop active; constructor fan-out compiles at all 4 sites. Also P1-08 is_live_slot,
P2-02 amend fail-closed, P2-03 group-aware preflight. Then E4 Linux regression (authoritative).

E1 IMPLEMENTATION DONE: 待 E2 審查
