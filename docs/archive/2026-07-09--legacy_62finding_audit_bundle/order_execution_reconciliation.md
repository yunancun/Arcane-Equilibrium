# Order Execution and Reconciliation Audit

Created: 2026-04-28
Status: complete for this audit slice
Scope: Rust exchange order dispatch, private WebSocket order/fill ingestion, close/reduce-only paths, API close-all/orphan sweeps, and trading DB persistence for orders, fills, intents, and risk verdicts.

## Flow Summary

Order submission starts in `TickPipeline` close/open paths by sending `OrderDispatchRequest` into the event consumer dispatch task. For primary exchange orders, dispatch registers a `PendingOrder` before calling Bybit REST `place_order`. The event consumer handles that registration by writing a `trading.orders` row and a `Working` `trading.order_state_changes` row, then later reconciles Bybit private WebSocket `order` and `execution` events back to the pending map.

Fill ingestion comes from Bybit private WebSocket topics `execution` and `execution.fast`. `execution_listener` forwards parsed private events into the event consumer. The event consumer deduplicates in memory by `exec_id`, matches fills by `order_id -> order_link_id` when available, falls back to a symbol/side pending-order match, then calls `TickPipeline::apply_confirmed_fill()` and emits `TradingMsg::Fill` to the DB writer.

Reconciliation is split across several mechanisms: Bybit `order` terminal statuses clear pending orders, `DcpTriggered` clears pending order state after exchange-side auto-cancel, periodic pending sweeps remove stale market/maker trackers, position reconciliation aligns `paper_state` to exchange positions, and API orphan sweeps attempt to close exchange positions that are not tracked in `paper_state`.

DB durability for trading rows is centralized in `trading_writer.rs`, which batches messages into inserts through `batch_insert_chunked()`.

## Confirmed Findings

### OE-001

Severity: P1
Status: open
Area: Private WebSocket fill/order ingestion
Files:

- `rust/openclaw_engine/src/bybit_private_ws.rs`
- `rust/openclaw_engine/src/execution_listener.rs`

Summary:

The private WebSocket parser returns only one `PrivateWsEvent` per message, while Bybit sends topic payloads as `data` arrays. For `order`, `execution`, `execution.fast`, `position`, and `wallet`, the parser loops over `data` but immediately returns the first successfully parsed item.

Evidence:

- `parse_private_message()` returns `Option<PrivateWsEvent>`.
- The topic handlers at `bybit_private_ws.rs:723`, `:734`, `:742`, `:750`, and `:760` return from inside the first successful `for item in data` iteration.
- `execution_listener.rs` consumes one event at a time and has no later opportunity to recover discarded array items.

Impact:

If Bybit delivers a batch with multiple executions, order updates, or position updates, all parsed items after the first are silently dropped. This can miss fills, leave pending orders uncleared, skip terminal order states, and make runtime state and `trading.fills` diverge from exchange truth.

Reproduction or trigger:

A single private WS message with `topic: "execution"` or `topic: "order"` and `data` length greater than one.

Recommended fix:

Change the parser/dispatch contract from `Option<PrivateWsEvent>` to a multi-event outcome, for example `Vec<PrivateWsEvent>` or `SmallVec`, and send every parsed item in the WebSocket read loop. Cover `order`, `execution`, `execution.fast`, `position`, and `wallet`.

Verification:

Static trace only. Add parser tests with two execution records and two order records in one `data` array.

### OE-002

Severity: P1
Status: open
Area: Order dispatch failure recovery
Files:

- `rust/openclaw_engine/src/event_consumer/dispatch.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs`

Summary:

Primary orders are registered as pending and written as `Working` before REST submission succeeds. If REST dispatch returns `Structural` or `TransientExhausted`, dispatch only logs the failure and does not emit a terminal failure event. Separately, close paths ignore `tx.send(...)` errors but still insert the symbol into `pending_close_symbols`.

Evidence:

- `dispatch.rs:399-425` registers `PendingOrder` before `place_order()`.
- `loop_handlers.rs:217-241` writes the order and `Submitted -> Working` state on pending registration.
- `dispatch.rs:542-588` logs structural and exhausted transient failures without removing pending state or writing a failed state transition.
- `commands.rs:668-689`, `:767-787`, and `:899-919` ignore `tx.send(...)` results and still mark primary close symbols pending.
- `reconcile_pending_exchange_orders()` only clears pending-close flags when the position is gone; if no close order was sent and the position remains open, later strategy/risk close attempts can be skipped by the pending-close guard.

Impact:

The DB can show a `Working` order that never reached Bybit. A failed close dispatch can also lock the symbol in `pending_close_symbols`, causing later close, risk-close, halt-close, or operator close attempts to be skipped while the exchange position remains open.

Reproduction or trigger:

REST transport failure, structural Bybit rejection before an order is accepted, exhausted transient retries, or a closed order-dispatch receiver during any primary close path.

Recommended fix:

Make dispatch failure produce an explicit terminal event, for example `OrderDispatchFailed`, consumed by the event loop to remove pending state, write `Working -> Rejected/Failed`, and clear pending-close for close orders. Treat `tx.send(...)` failure as an immediate close dispatch failure and do not insert pending-close unless enqueue succeeds.

Verification:

Static trace only. Add tests for failed REST dispatch after pending registration and for closed dispatch-channel close attempts.

### OE-003

Severity: P1
Status: open
Area: Trading DB durability
Files:

- `rust/openclaw_engine/src/database/batch_insert.rs`
- `rust/openclaw_engine/src/database/trading_writer.rs`

Summary:

Batch insert failures are logged but not propagated, and the caller clears the buffer after every attempted flush. The same pattern applies to high-value trading rows including intents, fills, risk verdicts, orders, and order state changes.

Evidence:

- `batch_insert.rs:179-197` logs insert errors and records pool failure, then continues and returns only `total_affected`.
- `trading_writer.rs:214-220`, `:268-269`, `:272-350`, `:470-526`, `:531-585`, and `:590-638` clear buffers after write attempts, including when the DB pool is unavailable or a batch insert failed.

Impact:

Transient DB errors can permanently drop trading intents, fills, order rows, state changes, and risk verdicts. This creates durable audit gaps and can make restart restore undercount realized PnL, fees, trade counts, and order lifecycle state.

Reproduction or trigger:

Any DB outage, schema mismatch, serialization error, network interruption, or pool unavailability during a writer flush.

Recommended fix:

Have batch insert return per-chunk success/failure and retain failed rows for retry, or write them to a dead-letter queue with explicit operator alerting. Do not clear buffers on pool absence or failed insert. Add metrics and a circuit-breaker style health signal for trading-writer durability failures.

Verification:

Static trace only. Add tests where `batch_insert_chunked()` fails and rows remain queued or are dead-lettered.

### OE-004

Severity: P1
Status: open
Area: Fill idempotency and restore correctness
Files:

- `rust/openclaw_engine/src/bybit_private_ws.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`
- `rust/openclaw_engine/src/database/trading_writer.rs`
- `sql/migrations/V003__trading_agent_tables.sql`

Summary:

Exchange-confirmed fill rows do not use Bybit `exec_id` as the durable idempotency key. Runtime dedup uses `exec_id`, but `TradingMsg::Fill` uses `fill-{engine_mode}-{symbol}-{ts_ms}` and the DB suppresses conflicts on `(fill_id, ts)`.

Evidence:

- `ExecutionUpdate` contains `exec_id`.
- `loop_handlers.rs:418-425` deduplicates only in process memory using `exec_id`.
- `commands.rs:530-548` emits `TradingMsg::Fill` with `make_fill_id(em, symbol, ts_ms)`.
- `on_tick_helpers.rs:110-112` defines that fill ID as mode, symbol, and timestamp only.
- `trading_writer.rs:345` uses `ON CONFLICT (fill_id, ts) DO NOTHING`.
- `trading.fills` primary key is `(fill_id, ts)`.

Impact:

Two executions for the same engine mode and symbol in the same millisecond can both update runtime state while only one persists in `trading.fills`. Restart restore can then undercount fees, realized PnL, and trade count. Process restart also loses `seen_exec_set`, so replay/idempotency is incomplete.

Reproduction or trigger:

Partial fills or multiple same-symbol orders with execution timestamps landing in the same millisecond.

Recommended fix:

Thread Bybit `exec_id` into attributed exchange fill persistence and use it in `fill_id`, for example `bybit-{exec_id}`, or add an `exec_id` column with a unique constraint scoped by engine/exchange. Keep generated IDs for purely synthetic paper fills separate.

Verification:

Static trace only. Add tests with two distinct `exec_id` values at the same millisecond and assert two DB rows.

### OE-005

Severity: P2
Status: open
Area: Fill attribution race
Files:

- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`

Summary:

When a fill arrives before the corresponding order update has populated `order_id_to_link`, the fallback match chooses the first pending order with the same symbol and side.

Evidence:

`loop_handlers.rs:458-474` falls back from `order_id_to_link.get(exec.order_id)` to an iterator search over pending orders where `po.symbol == exec.symbol`, side matches, and `cum_filled_qty < po.qty`.

Impact:

If multiple same-symbol, same-side pending orders exist, an early fill can attach to the wrong `PendingOrder`. That can misattribute strategy, context ID, maker/taker fee fallback, and order lifecycle state.

Reproduction or trigger:

Two or more same-symbol, same-side pending orders, with an execution event arriving before the order update mapping for the filled order.

Recommended fix:

Only use the symbol/side fallback when it identifies exactly one candidate. Otherwise hold the fill briefly for order mapping, query order details by exchange `order_id`, or persist it as unattributed and reconcile later.

Verification:

Static trace only. Add an event-ordering test with two same-side pending orders and a fill before order update.

### OE-006

Severity: P2
Status: open
Area: Close order timeout budget
Files:

- `rust/openclaw_engine/src/event_consumer/dispatch.rs`
- `rust/openclaw_engine/src/bybit_rest_client.rs`

Summary:

Close retry comments and constants describe a 500 ms retry sleep budget, but each REST attempt can wait on the global 10 second HTTP client timeout. A close order can therefore spend roughly 30 seconds across the initial attempt plus two retries before reporting failure.

Evidence:

- `dispatch.rs:33-43` defines close retry delays as `[100, 400]` ms and documents a 500 ms sleep budget.
- `dispatch.rs:478-483` applies those delays to close dispatch retry.
- `bybit_rest_client.rs:589-591` sets the reqwest client timeout to 10 seconds for each request.

Impact:

Risk exits and operator close commands can block far longer than the close retry documentation implies. During exchange degradation, this can delay subsequent failure handling and operator feedback.

Reproduction or trigger:

Bybit REST requests that hang until HTTP timeout during close dispatch.

Recommended fix:

Use a lower per-attempt timeout for close orders, wrap `place_order()` in a close-specific timeout, or update the retry design to account for request timeout as part of the exit budget.

Verification:

Static trace only. Add a timeout-controlled test around close retry budgeting.

### OE-007

Severity: P1
Status: open
Area: Live close write guard and REST fallback
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_account_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py`

Summary:

Live close endpoints can use direct REST fallback with the live API key slot when the Rust live engine/channel is not running, as long as the live slot is configured. This bypasses the Rust live dispatch path and its runtime authorization/channel boundary for reduce-only close orders.

Evidence:

- `live_session_account_routes.py:171-179` blocks only when the engine is not live and the live endpoint is unconfigured.
- `live_session_routes.py:250-279` chooses the live slot client when live credentials exist, independent of engine state.
- `live_session_account_routes.py:487-507` falls back to direct REST reduce-only close when the live channel is unavailable and position hints exist.
- `live_session_account_routes.py:557-579` performs close-all REST orphan sweep fallback when the live channel is unavailable.

Impact:

An operator API request can issue live reduce-only REST close orders while the Rust live engine is not authorized or not running. Even though reduce-only limits the direction of exposure, this is still live exchange mutation outside the primary live execution control path.

Reproduction or trigger:

Live key slot configured, Rust live channel unavailable, and a live close or close-all endpoint called with enough exchange position hints or orphan sweep data.

Recommended fix:

Require an explicit live-engine authorized/running state for all live write paths, including REST fallback, or split REST fallback behind a separate emergency-close authorization with clear mode, endpoint, and operator acknowledgement. The guard should not pass solely because the live secret slot is configured.

Verification:

Static trace only. Add route tests for live slot configured plus live engine offline.

### OE-008

Severity: P2
Status: open
Area: Operator close-all result reporting
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_account_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py`

Summary:

Close-all and session-stop responses can report successful closure even when orphan-sweep or close errors were recorded or per-symbol close failures were swallowed.

Evidence:

- `strategy_ai_routes.py:570-576` returns "All positions closed" even when `errors` is non-empty.
- `strategy_ai_routes.py:643-653` logs per-symbol orphan sweep close failures but does not append them to `errors`.
- `live_session_account_routes.py:584-591` returns "All positions closed" with `errors` only as payload data.
- `live_session_endpoints.py:292-300` returns "Live session stopped - positions closed" even when `errors` is non-empty.

Impact:

Operators can receive a success message while some positions remain open. This weakens incident response because the API envelope does not force callers to treat partial close failure as failure.

Reproduction or trigger:

Any orphan sweep per-symbol close failure, IPC close-all failure followed by a response containing errors, or live stop with close errors.

Recommended fix:

Return an explicit `closed_all: false` and non-success status for partial failures, or use a structured partial-success response that frontends and scripts must surface. Append per-symbol orphan sweep failures to the error list.

Verification:

Static trace only. Add route tests for partial orphan sweep failure and IPC close-all failure.

### OE-009

Severity: P2
Status: open
Area: Risk verdict audit fidelity
Files:

- `sql/migrations/V003__trading_agent_tables.sql`
- `rust/openclaw_engine/src/database/trading_writer.rs`

Summary:

The `trading.risk_verdicts` schema has `risk_level`, `checks_passed`, and `checks_failed`, but the writer never populates those columns. Risk score and modified quantity are stored inside JSONB `details` instead.

Evidence:

- `V003__trading_agent_tables.sql:184-197` defines the extra risk verdict columns.
- `trading_writer.rs:486-521` inserts only `ts`, `verdict_id`, `intent_id`, `context_id`, `symbol`, `verdict`, `reason`, `details`, and `engine_mode`.

Impact:

Risk audit queries over the dedicated schema columns will see null values, even when the runtime made detailed risk decisions. This can make later risk-control audits and dashboards underreport control behavior.

Reproduction or trigger:

Any `TradingMsg::RiskVerdict` flush.

Recommended fix:

Either populate the dedicated columns from the runtime verdict structure or remove/deprecate them and document `details` as the canonical source. Prefer structured columns for checks that operators need to query.

Verification:

Static trace only.

## Additional Follow-ups

- No runtime REST execution/order history backfill was found on private WebSocket reconnect. The Rust `OrderManager` exposes order and execution history APIs, but the reviewed runtime path appears to rely on WS reconnect, DCP handling, and position reconciliation. Position reconciliation can repair quantities, but it cannot reconstruct missing fill ledger rows.
- Unattributed fills use `unattrib-{exec_id}`, which is stronger than attributed fill IDs. The fix for OE-004 should align attributed and unattributed durability semantics.
- Demo and live single-symbol close endpoints return 404 when REST hints are absent after IPC returns, even though IPC might have accepted a close for a position known only to Rust `paper_state`. This needs route-level confirmation during API audit.

## Reviewed Files

- `rust/openclaw_engine/src/bybit_private_ws.rs`
- `rust/openclaw_engine/src/execution_listener.rs`
- `rust/openclaw_engine/src/startup/private_ws.rs`
- `rust/openclaw_engine/src/event_consumer/dispatch.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/event_consumer/bootstrap.rs`
- `rust/openclaw_engine/src/event_consumer/paper_state_restore.rs`
- `rust/openclaw_engine/src/event_consumer/funding_settlement.rs`
- `rust/openclaw_engine/src/event_consumer/unattributed_emit.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs`
- `rust/openclaw_engine/src/bybit_rest_client.rs`
- `rust/openclaw_engine/src/order_manager.rs`
- `rust/openclaw_engine/src/database/batch_insert.rs`
- `rust/openclaw_engine/src/database/trading_writer.rs`
- `rust/openclaw_engine/src/database/mod.rs`
- `rust/openclaw_engine/src/position_reconciler/mod.rs`
- `rust/openclaw_engine/src/position_reconciler/orphan_handler.rs`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_account_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_demo_sync.py`
- `sql/migrations/V003__trading_agent_tables.sql`
- `sql/migrations/V027__funding_settlements.sql`

## Verification Performed

Static audit only. No runtime tests were executed for this slice.
