# PA Implementation Spec — Cold Audit Package B: Bybit Exchange Write Semantics + Authority

Date: 2026-05-29 Europe/Madrid. Role: PA(default). Repo root: `/Users/ncyu/Projects/TradeBot/srv`.
HEAD at synthesis: `b2e0651022d7ac5773cab285a0176bc62914ec52`, `## main...origin/main` (TODO.md dirty, ignored).
Mutation scope of this task: this report file only. No code, no TODO/memory/TOML/secrets, no deploy/restart/cargo build.

Source of decisions: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--cold_audit_validated_fix_plan.md`
(P1-03, P1-06, P1-07, P1-08, P2-02, P2-03, P2-04). Operator decisions for P1-03 (MOVE TO RUST AUTHORITY)
and P1-07 (STRICT FAIL-CLOSED) are fixed inputs and are NOT re-litigated here.

This is an implementation spec for E1. It does not contain implementation code.

---

## 0. PA recheck note vs. fix-plan line cites

The fix plan cited `live_session_routes.py:686-710` + `bybit_rest_client.py:681-715` for P1-03. PA recheck of
current source found the actual REST cancel-all body lives in **`strategy_ai_routes.py:1813` `_sweep_orphan_orders`**
(calls `rc.cancel_all_orders("linear", settle_coin="USDT")`). `live_session_routes.py:686-710`
(`_sweep_live_orphan_orders`) is the live-slot wrapper that delegates to that helper; the actual Stop-flow
**call site** is `live_session_endpoints.py:282`. E1 must scope to those three locations, not the stale
`bybit_rest_client.py` line range. All other P1-06/07/08/P2-02/03/04 line ranges verified accurate.

---

## P1-03 — Move Python live cancel-all behind Rust execution authority

### Current state (verified)
- `live_session_endpoints.py:282` (Live Stop flow, Phase 1): `cancel_orders_result = core._sweep_live_orphan_orders(errors)`.
- `live_session_routes.py:686-710` `_sweep_live_orphan_orders()`: synchronous; resolves live-slot `BybitClient`
  via `_get_rust_client_safe()` then delegates to `strategy_ai_routes._sweep_orphan_orders(rc, "live", errors)`.
- `strategy_ai_routes.py:1813-1864` `_sweep_orphan_orders(rc, env_label, errors)`: snapshots `rc.get_active_orders("linear")`
  then issues the mutating write `rc.cancel_all_orders("linear", settle_coin="USDT")` → Bybit `/v5/order/cancel-all`.
- Position-side sweep already moved to Rust: `live_session_routes.py:657` issues `await _ipc_command("close_position", ...)`
  and `:286` issues `await _ipc_command("close_all_positions", {"engine":"live"})`. The cancel-all order sweep is the
  **last remaining Python live exchange-mutating REST write** in the Stop path.
- Existing IPC plumbing (the model to copy): `_ipc_command(method, params)` at `live_session_routes.py:180-213`
  (5s timeout, raises HTTPException on failure). Rust side: `ipc_server/dispatch.rs:206-241` dispatches
  `close_all_positions`/`close_position` → `PipelineCommand::CloseAll`/`CloseSymbol` via `handle_paper_cmd`
  → consumed in `event_consumer/handlers/lifecycle.rs:71` `handle_close_all` (which already does exchange-side
  reduce-only dispatch in Demo/Live via `pipeline.ipc_close_all()`). Rust `OrderManager::cancel_all`
  (`order_manager.rs:489-506`, `POST /v5/order/cancel-all`) is the existing exchange primitive — it is NOT yet
  reachable from an IPC command, only from internal engine paths.

### Design — new IPC command `cancel_all_orders`

Add a new JSON-RPC IPC method that routes cancel-all through the engine's order authority, mirroring `close_all_positions`.

IPC contract (JSON-RPC 2.0 over the existing Unix socket; same envelope as `close_all_positions`):

```
method: "cancel_all_orders"
params: {
  "engine": "live"            // required; "paper"|"demo"|"live" — routes to the pipeline cmd channel
                              //   via extract_engine_tx(&req.params, cmd_channels)
  "category": "linear",       // optional; default "linear" (only linear is in scope today)
  "settle_coin": "USDT"       // optional; default "USDT" — account-scope cancel-all
}
result (success): { "cancel_all_sent": true }   // command accepted onto the pipeline channel
error: standard JSON-RPC error (ERR_INTERNAL "channel send failed" / "paper command channel not configured")
```

Rust-side wiring (3 edits, all behavior-additive):
1. **`tick_pipeline/mod.rs` `enum PipelineCommand`** (~:199): add a fail-safe variant
   `CancelAllOrders { category: String, settle_coin: String }`. Risk-reducing only; no `response_tx` needed
   (fire-and-forget like `CloseAll`), matching the existing `CloseAll` shape.
2. **`event_consumer/handlers/mod.rs` match arm** (~:54): route `PipelineCommand::CancelAllOrders { .. }` to a new
   `lifecycle::handle_cancel_all_orders(...)`. In `lifecycle.rs`, the handler must:
   - Paper mode: no exchange client → log only (parity with `handle_close_all` paper branch).
   - Demo/Live mode: call the live/demo `OrderManager::cancel_all(OrderCategory::Linear, …)` reachable from
     the pipeline's exchange client. E1 must locate the existing exchange-mode `OrderManager`/client handle that
     `ipc_close_all()` already uses for reduce-only dispatch (same handle that places exchange orders) and call
     `cancel_all` against it. **Account-scope cancel-all by settleCoin**: `OrderManager::cancel_all` currently
     takes `(category, symbol)`. Because the Python path used `settleCoin=USDT` (no per-symbol loop), E1 must add a
     settle-coin-scoped variant — either extend `cancel_all` to accept an optional `settle_coin` (preferred:
     `cancel_all_scoped(category, symbol: Option<&str>, settle_coin: Option<&str>)`) or add a sibling method.
     Body must send `{"category","settleCoin":"USDT"}` matching the prior Python request. Do not loop per active
     symbol — the whole point of the existing helper was single-call account scope.
   - This handler is **risk-reducing (cancel only), never order-placing** — it does not require Decision Lease and
     is permitted under root principle 1 because the write now goes through Rust execution authority, not Python REST.
3. **`ipc_server/dispatch.rs`** (~:206, next to `close_all_positions`): add the `"cancel_all_orders"` arm:
   `let tx = extract_engine_tx(&req.params, cmd_channels); handle_paper_cmd(id, &tx, PipelineCommand::CancelAllOrders{..}, "cancel_all_sent")`.

Python-side change (call-site dispatch via IPC, mirroring `close_all_positions` at `:286`):
- **`live_session_endpoints.py:282`**: replace `cancel_orders_result = core._sweep_live_orphan_orders(errors)`
  with an `await core._ipc_command("cancel_all_orders", {"engine":"live"})` call wrapped in the same
  try/except + `_is_live_channel_unavailable_error` handling already used for `close_all_positions` at `:286-300`.
  On live-channel-unavailable: set `cancel_orders_result = {"skipped": True, "reason":"live_pipeline_not_authorized",
  "rest_fallback_disabled": True}` and append `"live_channel_unavailable"` to errors — same fail-closed posture as close.
- **`live_session_routes.py:686-710` `_sweep_live_orphan_orders`**: delete (no other live caller after :282 changes).
  Note the misleading comment block at :700-704 claiming "cancel-all is fail-safe so Python REST is allowed" — that
  rationalization is exactly what the operator decision overrides; remove it with the function.
- **`strategy_ai_routes.py:1813 `_sweep_orphan_orders` / :1867 `_sweep_demo_orphan_orders``**: KEEP for the demo
  Stop path (`_sweep_demo_orphan_orders` at `:1871` calls it with `"demo"`). Demo is a learning/data lane and is not
  under the P1-03 live-authority constraint; out of scope. Do NOT delete the shared helper. (If E1 wants symmetry,
  a demo IPC move can be a separate follow-up, but it is NOT in this package.)

### What E1 changes (P1-03)
- Rust: `tick_pipeline/mod.rs` (enum variant), `event_consumer/handlers/mod.rs` (match arm),
  `event_consumer/handlers/lifecycle.rs` (new `handle_cancel_all_orders`), `order_manager.rs`
  (settle-coin-scoped cancel-all variant), `ipc_server/dispatch.rs` (new method arm).
- Python: `live_session_endpoints.py:282` (IPC dispatch), `live_session_routes.py` (delete dead wrapper + comment).
- Tests: see acceptance.

### Verification (P1-03)
- cargo: new dispatch test asserting `"cancel_all_orders"` with `engine=live` produces `PipelineCommand::CancelAllOrders`
  on the channel (mirror existing close_all dispatch test); lifecycle test that paper mode is log-only and exchange
  mode calls the cancel-all primitive (mock OrderManager). Verify body carries `settleCoin=USDT`, `category=linear`.
- Python: update/replace `test_session_stop_cancel_verify.py` live-path assertions — `_sweep_live_orphan_orders`
  no longer exists; the live Stop flow must now assert an IPC `cancel_all_orders` call is dispatched and that
  live-channel-unavailable yields `rest_fallback_disabled=True` + error append (no REST). Demo tests at
  `test_session_stop_cancel_verify.py:131-161` stay (still exercise `_sweep_orphan_orders` for demo).
- BB review: confirm `/v5/order/cancel-all` body (settleCoin scope) matches Bybit v5 contract; confirm cancel-all
  remains category=linear and is reduce-side only.

### Acceptance criteria (P1-03)
1. No Python code path issues a **live** Bybit `/v5/order/cancel-all` (or any live order mutation) directly; grep
   `cancel_all_orders\|/v5/order/cancel-all` in `program_code/` shows only demo + IPC dispatch, zero live REST.
2. Live Stop Phase 1 cancel goes through the engine; when the live IPC channel is unavailable the cancel is
   skipped fail-closed (no silent REST fallback), matching the close path.
3. Demo Stop path unchanged.

### Risk / blockers for E1 (P1-03)
- **HIGH risk (cross-IPC schema + execution authority).** Mandatory E2 review point.
- Open question for E1 to resolve by reading `pipeline.ipc_close_all()`: does `handle_close_all` exchange branch
  hold a usable `OrderManager`/client handle, or does it dispatch via the same OrderDispatchRequest channel as
  strategy orders? `cancel_all` is a position/order-management call, NOT an OrderDispatchRequest. If the pipeline
  does not already own a position/order-mgmt client for cancel-all, E1 must thread the existing live `BybitRestClient`
  Arc (the one `spawn_order_dispatch`/bootstrap already constructs an `OrderManager` from) into the lifecycle handler.
  This is the one genuine wiring unknown; PA confirms the client Arc exists in bootstrap (`bootstrap.rs:742`
  constructs a `PositionManager` from `shared_client` for trading-stop), so the handle is reachable — E1 should
  reuse that shared-client plumbing rather than create a new client.
- Ordering invariant: `execution_authority` is revoked BEFORE Phase 1 (comment at `:279`), so the engine cannot
  place new orders during the cancel window. The new IPC command must NOT be gated behind execution_authority
  (cancel must still work after authority revoke) — it is risk-reducing. E1 must verify the cancel path is not
  accidentally blocked by an authority check in the pipeline command consumer.

---

## P1-07 — Strict fail-closed on mutating order-create retry

### Operator decision (fixed input)
Timeout / parse / transport / nonzero retCode on a **mutating order-create** must fail closed. Remove/tighten
`run_dispatch_retry` so order-create (OPEN intents) is NOT retried. Align CLAUDE.md hard boundary with code + tests.

### Current state (verified)
- `dispatch.rs:633-668`: production wraps `om.place_order(req_for_attempt)` in `run_dispatch_retry(delays, …)`.
  Delay schedule chosen by `req.is_close`: OPEN → `RETRY_DELAY_MS = [200,800,3200]` (3 retries, 4 attempts);
  CLOSE → `CLOSE_RETRY_DELAY_MS = [100,400]` (2 retries, 3 attempts, `reduce_only=true`, per-attempt 500ms timeout).
- `classify_dispatch_error` (`:201-221`) + `classify_business_retcode` (`:227-312`): Transport/JsonParse → Transient
  (retried); 10006/10016-19 → Transient; 10002 recv_window/timestamp → Transient; 10001 "duplicate" → NoOp; others → Structural.
- Tests `dispatch_tests.rs:371-530` lock the retry loop semantics (Ok-on-3rd-attempt, transient exhaustion=4 attempts,
  close budget=3 attempts).

### Retry policy spec (precise diff intent)

**OPEN (create) intents — `req.is_close == false` AND `req.is_primary == true`: NO RETRY, fail closed.**
- The OPEN branch must call `om.place_order(...)` exactly ONCE (1 attempt, 0 retries) regardless of error class.
- Any error — `Transport`, `JsonParse`, business nonzero retCode (incl. 10006 rate-limit, 10016-19 maintenance,
  10002 recv_window), or per-attempt timeout — terminates the dispatch as a failure. Decision Lease is released with
  a fail-closed outcome (NOT `Consumed`); position is not opened; no second create is sent.
- Rationale (matches CLAUDE.md): a mutating create whose response was ambiguous (timeout/parse/transport) MUST NOT be
  re-sent — `order_link_id` idempotency is a Bybit-side mitigation, not a license to add a hidden retry path for
  trading effects. An ambiguous-outcome create is reconciled by the position reconciler / pending-order tracking, not
  by blind re-create.

**Exception that MAY keep retry (narrow, must be documented):**
- **CLOSE intents** (`req.is_close == true`) are risk-reducing, idempotent (`reduce_only=true`), and the dual-rail
  exit path. The operator decision text targets "order-create"; CLOSE is order-reduce. PA recommendation: KEEP the
  tight close retry budget (`CLOSE_RETRY_DELAY_MS`, 2 retries) for CLOSE only, because failing a close closed would
  leave a live position un-reduced — strictly more dangerous than a re-attempted reduce-only close. This is a
  documented idempotent exception, narrowly scoped to reduce-only closes. **E1 must NOT remove close retry; only the
  OPEN/create path becomes single-attempt.** If operator wants closes fail-closed too, that is a follow-up decision;
  this spec keeps closes retried per principle 5 (survival > profit).
- **Non-mutating ops** (GET position/account/instrument, `get_active_orders`) are not in `run_dispatch_retry` and may
  keep their existing client-level rate-limit backoff; untouched by this fix.
- **NoOp classification stays.** 10001 "duplicate" (idempotent re-arrival) and 110001/110009/110043 on close → NoOp
  (equivalent success) remain — these are not retries, they are terminal success classifications and are correct.

### Precise diff intent (`dispatch.rs:633-668`)
- Replace the `delays = if req.is_close { &CLOSE_RETRY_DELAY_MS } else { &RETRY_DELAY_MS }` selection with:
  - CLOSE: `run_dispatch_retry(&CLOSE_RETRY_DELAY_MS, …)` (unchanged).
  - OPEN: call the place closure ONCE without the retry loop, OR call `run_dispatch_retry(&[], …)` (empty schedule =
    1 attempt, 0 retries — `run_dispatch_retry` already returns `TransientExhausted` immediately when
    `attempt >= delays_ms.len()` with empty slice). PA prefers the empty-slice form to reuse the same outcome
    matching/logging machinery and avoid a parallel un-tested code path. Then `RETRY_DELAY_MS` becomes dead for
    production OPEN and should be removed (or retained only if a test still needs it — see below).
- `RETRY_DELAY_MS` const: if no production caller remains, delete it (and its doc comment at `:28-34`). Verify no
  other module references it (`rg RETRY_DELAY_MS rust/`).

### CLAUDE.md alignment (the doc edit)
- CLAUDE.md §四 already states: "Bybit API timeout or nonzero `retCode` fails closed; do not add hidden retry paths
  for trading effects." This is currently CONTRADICTED by OPEN retry. After the code change the boundary is satisfied
  for creates. **Add a one-line clarification** (PM/TW owns the actual edit; PA specifies intent): note that
  reduce-only **close** dispatch retains a bounded idempotent retry as the documented exception under principle 5,
  so the boundary text and code do not appear to conflict to a future auditor. Do not weaken the create rule.

### What E1 changes (P1-07)
- `dispatch.rs:633-668` (OPEN single-attempt), `:28-34` + `RETRY_DELAY_MS` const removal if dead.
- `dispatch_tests.rs:371-530`: tests that lock OPEN multi-retry must be rewritten to assert OPEN = 1 attempt /
  fail-closed on first Transport/JsonParse/10006/timeout. The generic `run_dispatch_retry` unit tests
  (`test_run_dispatch_retry_*`) exercise the helper directly with explicit delay slices — those stay valid as
  helper-level tests (the helper itself still supports retry for the close path). Add a new test asserting the
  OPEN production path passes an empty (or len-0) schedule so a single Transport error yields a fail-closed,
  lease-not-consumed outcome with attempts==1.
- CLAUDE.md: PM/TW one-line close-exception clarification (PA does not edit CLAUDE.md in this task).

### Verification (P1-07)
- cargo: OPEN single-attempt fail-closed test (Transport, 10006, timeout each → 1 attempt, no second place call,
  lease released non-Consumed); CLOSE budget test unchanged (still 3 attempts). E4 regression on dispatch suite.
- BB review: confirm no retCode class is silently retried on create; confirm the close exception is reduce-only.

### Acceptance criteria (P1-07)
1. A mutating OPEN create is attempted at most once; timeout/parse/transport/nonzero-retCode → fail closed, no
   second create, Decision Lease NOT marked Consumed.
2. CLOSE (reduce-only) retains the bounded idempotent budget; documented as the sole exception.
3. CLAUDE.md hard-boundary wording and dispatch implementation no longer conflict; close exception is explicit.

### Risk / blockers (P1-07)
- **HIGH risk (hard boundary, execution path).** Mandatory E2 + E4. The decision-lease release-outcome on OPEN
  fail-closed must be verified to actually release (not leak) the lease — E1 must trace `send_decision_lease_release`
  for the `TransientExhausted`/`Structural` arms to ensure OPEN failures release with a non-Consumed outcome so the
  lease does not stay held.

---

## P1-06 — Shared trading-stop normalizer (side-aware conservative rounding, fail-closed)

### Current state (verified)
- `position_manager.rs:226-263` `set_trading_stop`: serializes `take_profit`/`stop_loss`/`trailing_stop`/`active_price`
  with raw `format!("{}", value)` — NO tick rounding. Create-order path DOES round (`order_manager.rs:538-543`
  via `instruments.round_price`). `PositionManager` struct (`:127-137`) holds only `client: Arc<BybitRestClient>` —
  **no instrument cache today.**
- Callers that build `TradingStopRequest`:
  - `event_consumer/bootstrap.rs:757-768` (dual-rail SL after open; has `req.is_long`, `req.stop_loss`).
  - `notification_failsafe/providers/exchange_stop_sync.rs:79-107` (`build_trading_stop_request` from `StopAdjustment`;
    has `adjustment.new_sl`; side derivable from adjustment).
  - `tick_pipeline/on_tick/step_4_5_dispatch.rs:1302-1310, 1354-1355` (SL price `sl_price`).
- Side-aware rounding helpers ALREADY EXIST on `SymbolSpec` (`instrument_info.rs`): `floor_price` (`:83`,
  "conservative for long stop-loss"), `ceil_price` (`:93`, "conservative for short stop-loss"), `round_price`
  (`:73`, nearest — used by create path). The conservative direction is already encoded; this fix wires it into
  the trading-stop path.

### Normalizer design
Add a shared normalizer that takes side + raw price and returns a tick-aligned, conservatively-rounded price, failing
closed when the instrument spec is missing.

Recommended signature (free function in `instrument_info.rs` or a method on `InstrumentInfoCache`, Rust-first):

```rust
/// 交易所端止損價規範化：依方向保守取整到 tick；無 instrument spec 時回 None（fail-closed）。
/// is_long_stop_loss=true → 多頭 SL，floor（向下，不放鬆停損）；false → 空頭 SL，ceil（向上）。
pub fn normalize_trading_stop_price(
    cache: &InstrumentInfoCache,
    symbol: &str,
    price: f64,
    side_is_long: bool,   // position side; SL conservative = floor for long, ceil for short
    is_stop_loss: bool,   // SL uses conservative direction; TP/trailing/active use nearest round_price
) -> Option<f64>          // None = spec missing → caller fails closed (skip exchange stop, keep local stop)
```

Conservative semantics:
- **stop_loss, long position**: `floor_price` (round AWAY from price toward worse fill = does not tighten stop
  beyond intent and is always a valid tick; for a long SL below entry, flooring keeps it <= requested, an acceptable
  conservative rounding that Bybit accepts).
- **stop_loss, short position**: `ceil_price`.
- **take_profit / trailing_stop / active_price**: use nearest `round_price` (TP precision is not survival-critical;
  Bybit just needs tick alignment). E1 may apply the same fail-closed-on-missing-spec rule.
- **Missing spec → `None`**: caller MUST treat `None` as fail-closed: skip the exchange-side stop for that field,
  log a warning, and rely on the local StopManager (root principle 9 dual-rail — local stop still active). It must
  NOT send the raw unrounded value.

### Wiring
- `PositionManager` must gain access to the instrument cache. Cleanest: add `instruments: Arc<InstrumentInfoCache>`
  to the `PositionManager` struct and `PositionManager::new(client, instruments)`. Then `set_trading_stop` normalizes
  each price field via the normalizer before `format!`. This is a constructor-signature change — find all
  `PositionManager::new` callers (`rg 'PositionManager::new' rust/`); PA found `bootstrap.rs:742`
  (`shared_client.map(crate::position_manager::PositionManager::new)`) and `exchange_stop_sync.rs` usage. Both
  construct from a shared client that already has access to the engine's instrument cache (the same cache the
  OrderManager uses). E1 must thread the cache Arc through these two construction sites.
- Side info: `set_trading_stop` does not currently receive side. Two options — (a) add `side_is_long: Option<bool>`
  to `TradingStopRequest` and have the three callers populate it (bootstrap has `req.is_long`; exchange_stop_sync has
  adjustment side; step_4_5 has the position side), or (b) normalize at each caller before building the request.
  PA prefers (a): single normalization point inside `set_trading_stop`, callers just supply side. `side_is_long: None`
  → fall back to nearest `round_price` (still tick-aligned, never raw) so a caller that genuinely lacks side does not
  fail closed unnecessarily but also never sends a non-tick value.

### What E1 changes (P1-06)
- `instrument_info.rs` (new `normalize_trading_stop_price`), `position_manager.rs` (struct + `new` + `set_trading_stop`
  + `TradingStopRequest` side field), `bootstrap.rs:742,757-768` (pass cache + side), `exchange_stop_sync.rs:79-107`
  (pass side), `step_4_5_dispatch.rs:1302-1310` (pass side).

### Verification (P1-06)
- cargo: unit tests for `normalize_trading_stop_price` (long SL floors, short SL ceils, missing spec → None);
  `set_trading_stop` test asserting serialized body uses tick-aligned strings (extend existing
  `test_trading_stop_request_serde` at `position_manager.rs:827`); exchange_stop_sync `build_trading_stop_request`
  test (`:221-250`) updated for side field. BB review: confirm Bybit `/v5/position/trading-stop` accepts the
  conservatively-rounded values and rejects sub-tick (validates the bug premise).
- QC review: confirm conservative direction does not weaken protective stop semantics (floor-for-long does not move
  the stop further from price in a way that increases loss beyond design).

### Acceptance criteria (P1-06)
1. Every `/v5/position/trading-stop` price field is tick-aligned (no raw `format!("{}", value)`).
2. Missing instrument spec → exchange stop skipped fail-closed, local stop retained, warning logged; no raw value sent.
3. SL rounding is side-aware conservative; TP/trailing tick-aligned.

### Risk (P1-06)
- MEDIUM-HIGH (touches dual-rail protection + constructor signature fan-out). E2 must verify the two
  `PositionManager::new` callers compile and that the fail-closed path keeps the local stop active.

---

## P1-08 — Disable env-credential fallback whenever secret slot is "live"

### Current state (verified)
- `bybit_rest_client.rs:901` `let is_mainnet = matches!(env, BybitEnvironment::Mainnet);`
- `:139-144` `secret_slot()`: both `Mainnet` and `LiveDemo` → `"live"`.
- `:929-941` api_key fallback: env-var `BYBIT_API_KEY` fallback disabled only `if is_mainnet`.
- `:943-955` api_secret: same `if is_mainnet` guard.
- Defect: **LiveDemo** maps to the `"live"` slot but `is_mainnet == false`, so process env-var credentials can
  override the operator-managed live slot — bypassing live-slot provenance/audit. CLAUDE.md §四:
  "Mainnet env-var fallback as the only credential source is closed" — the spirit covers all live-grade flows; LiveDemo
  is live-grade control flow.

### Design
- Introduce `let is_live_slot = env.secret_slot() == "live";` (covers Mainnet + LiveDemo).
- Replace the two `if is_mainnet { None } else { env::var(...) }` guards (`:932`, `:946`) with `if is_live_slot`.
- Keep the `OPENCLAW_ALLOW_MAINNET` gate and the empty-credential fail-closed (`:908-920`, `:957+`) keyed on
  `is_mainnet` (those are mainnet-real-money specific and must NOT widen to LiveDemo).

### What E1 changes (P1-08)
- `bybit_rest_client.rs:901` (add `is_live_slot`), `:932` + `:946` (guard swap). ~3 lines.

### Verification (P1-08)
- cargo: test constructing a `LiveDemo` client with `BYBIT_API_KEY`/`BYBIT_API_SECRET` set in env and an empty
  passed key → env must NOT be used (assert it falls through to `read_secret_file(slot,…)` / empty, not the env value).
  Mirror existing mainnet-fallback test. BB + E3 review for credential-provenance correctness.

### Acceptance criteria (P1-08)
Env-var credentials never satisfy a `"live"`-slot client (Mainnet or LiveDemo); demo/testnet env fallback unchanged.

### Risk (P1-08)
LOW-MEDIUM. Isolated. E3 confirms no test/dev workflow depended on LiveDemo env override (if it did, that workflow
must move to the live secret slot, which is the intended posture).

---

## P2-02 — Amend order fail-closed on instrument cache miss

### Current state (verified)
- `order_manager.rs:536-543` amend: `self.instruments.round_qty(&req.symbol, q).unwrap_or(q)` and
  `:541-543` `round_price(...).unwrap_or(p)`. On cache miss → sends RAW qty/price (off-step/off-tick), unlike the
  create path which has the same `unwrap_or` but PA should align both to the chosen policy. `:551-552` stop_loss is
  `format_price(sl)` directly (no rounding at all on amend SL).

### Design
- On instrument cache miss for an amend that carries qty or price, **fail closed**: return a structural
  `BybitApiError::Business { ret_code: -1, ret_msg: "amend rejected: instrument spec missing for <symbol>" }`
  rather than `.unwrap_or(raw)`. This mirrors the create-validation intent (reuse `SymbolSpec::validate_order`
  semantics where possible). Do NOT silently send raw fields.
- Apply tick rounding to amend `stop_loss`/`take_profit`/`trigger_price` too (currently `format_price` without
  `round_price`), consistent with P1-06 normalizer — but at minimum align with the qty/price policy.

### What E1 changes (P2-02)
- `order_manager.rs:536-553`. Replace `unwrap_or(q/p)` with fail-closed Err on `None`; round SL/TP/trigger via cache.

### Verification (P2-02)
- cargo: amend with uncached symbol + qty → Err (not raw); amend with cached symbol → rounded body. BB review +
  E4 regression.

### Acceptance criteria (P2-02)
Amend never sends off-step/off-tick fields; cache miss → fail closed.

### Risk (P2-02): LOW. Co-locate with P1-06 (same file/concept). E2 verifies no caller relied on amend succeeding
on uncached symbols (instrument cache is normally warm; cache-miss amend is a degraded path that should fail loud).

---

## P2-03 — Path/group-aware rate-limit preflight

### Current state (verified)
- `bybit_rest_client.rs:1105, 1165` call `self.wait_if_rate_limited()` (no path arg, GET and POST).
- `wait_if_rate_limited` (`:1282-1313`) only inspects GLOBAL `rate_limit.remaining` + global `reset_ms`.
- Per-group state EXISTS: `RateLimitGroup` enum (`:221-234`) + `from_path` (`:244-262`) +
  `group_remaining: [AtomicI64; 6]` (`:276`) + `update_group_rate_limit(path,…)` (`:1317-1328`). BUT there is NO
  per-group `reset_ms` — only a single global `reset_ms`. The mutating Order group (10 req/s) can be near-limit while
  the global counter looks healthy → avoidable 10006 on `/v5/order/*`.

### Design
- Change signature to `async fn wait_if_rate_limited(&self, path: &str)`; both call sites pass `path`.
- Inside: resolve `let group = RateLimitGroup::from_path(path); let idx = group as usize;`. Check
  `group_remaining[idx]` against a group-appropriate threshold (Order/Position/Account 10 req/s → low threshold like
  2-3; Market 120; Asset 5). If near the group limit, back off.
- Per-group reset timestamp: `RateLimitState` needs a `group_reset_ms: [AtomicU64; 6]` parallel to `group_remaining`,
  populated in `update_group_rate_limit` from the `x-bapi-limit-reset-timestamp` header (currently only stored to the
  global `reset_ms` in `update_rate_limit`). E1 must add the per-group reset store and read it in the preflight,
  falling back to global `reset_ms` when the group reset is 0/unknown.
- Keep the global check as a coarse outer guard (defensive); group check is the precise inner guard.

### What E1 changes (P2-03)
- `bybit_rest_client.rs`: `RateLimitState` struct (+`group_reset_ms`), `RateLimitState::default`,
  `update_group_rate_limit` (store group reset), `wait_if_rate_limited(path)` (group-aware), call sites `:1105,:1165`.

### Verification (P2-03)
- cargo: unit test that a near-limit Order group triggers backoff while Market group is healthy (and vice versa) —
  group isolation; test `from_path` mapping for `/v5/order/create`, `/v5/position/trading-stop`, `/v5/market/*`.
  BB review for correct per-group limits.

### Acceptance criteria (P2-03)
Preflight backs off based on the request path's group state, not only global; mutating-path 10006 reduced.

### Risk (P2-03): LOW-MEDIUM. Atomics already present; additive. E4 confirms no latency regression on hot path
(`wait_if_rate_limited` is called per request — keep it allocation-free / branch-cheap).

---

## P2-04 — Bybit reference doc patch (TW owns the edit)

This is a documentation finding. PA specifies exactly what TW must change so a future exchange-facing change does not
reintroduce the unsafe fake pre-check or the wrong demo WS topics. PA does not edit the doc in this task; spec only.

### Drift 1 — fake pre-check (`docs/references/2026-04-04--bybit_api_reference.md:823-829`)
- Doc currently documents `pre_check_order` as a live method that "calls POST /v5/order/create (dry-run concept)"
  with `關聯程式: platform_client.rs:362`.
- Source truth (`platform_client.rs:355-359`): `pre_check_order()` was REMOVED in FIX-20 precisely because it hit
  the real `/v5/order/create` (Bybit has no dry-run) → accidental-order risk in Live.
- TW must: delete/strike the `pre_check_order` entry, OR replace it with a clearly-marked "REMOVED (FIX-20): Bybit
  has no order dry-run; do not reintroduce — calling /v5/order/create as a pre-check places a real order" warning.
  Fix the stale `關聯程式` line.

### Drift 2 — demo `dcp` WS topic (`docs/references/2026-04-04--bybit_api_reference.md:1119-1123`)
- Doc line 1121 lists demo topics as `["order","execution","position","wallet","dcp"]` (includes `dcp`).
- Source truth (`bybit_rest_client.rs:119-128` `private_ws_topics`): Demo/LiveDemo/Testnet =
  `["order","execution","position","wallet"]` — **no `dcp`** (Bybit demo rejects `dcp` with "topic does not exist";
  `dcp` and `execution.fast` are mainnet-only). The source doc-comment at `:108-117` is authoritative.
- TW must: remove `dcp` from the demo topic list in the reference doc; keep `dcp` + `execution.fast` mainnet-only;
  reconcile any `1333` mention of the same.

### Verification (P2-04)
TW patch reviewed by BB + R4; doc matches source exactly (grep the two topic lists agree).

### Acceptance criteria (P2-04)
Reference doc has no live `pre_check_order` method and no demo `dcp` topic; mainnet-only features correctly scoped.

### Risk (P2-04): LOW (doc-only). Owner TW + BB; not E1.

---

## E1 dispatch plan (max parallelism, file-disjoint where possible)

| Lane | Findings | Files | Risk | Depends on |
|---|---|---|---|---|
| B1 (Rust IPC) | P1-03 | `tick_pipeline/mod.rs`, `event_consumer/handlers/{mod,lifecycle}.rs`, `order_manager.rs` (cancel-all scoped), `ipc_server/dispatch.rs`, Python `live_session_endpoints.py`, `live_session_routes.py` | HIGH | none |
| B2 (Rust dispatch) | P1-07 | `event_consumer/dispatch.rs`, `dispatch_tests.rs` | HIGH | none |
| B3 (Rust stop/amend) | P1-06, P2-02 | `instrument_info.rs`, `position_manager.rs`, `bootstrap.rs`, `exchange_stop_sync.rs`, `step_4_5_dispatch.rs`, `order_manager.rs` (amend) | MED-HIGH | none |
| B4 (Rust client) | P1-08, P2-03 | `bybit_rest_client.rs` | LOW-MED | none |
| B5 (Doc) | P2-04 | reference doc | LOW | none — TW not E1 |

File-overlap caution: B1 and B3 both touch `order_manager.rs` (B1 adds cancel-all scoped variant ~:489; B3 amend
~:536). Serialize B1→B3 on that file, OR have a single E1 own both `order_manager.rs` edits to avoid a merge race.
`bootstrap.rs` is touched only by B3. CLAUDE.md close-exception clarification (P1-07) is PM/TW, not E1.

## E2 must-review top 3
1. **P1-03 IPC + authority**: cancel-all must NOT be gated behind execution_authority (must work post-revoke), must
   reach the exchange via the engine's existing live client (no new client, no Python REST fallback), and the dead
   Python wrapper + its "cancel-all is fail-safe so Python REST is allowed" comment must be fully removed.
2. **P1-07 fail-closed lease**: OPEN create = single attempt; verify the Decision Lease is RELEASED (non-Consumed) on
   OPEN fail-closed so it does not leak; confirm CLOSE reduce-only exception is the only retained retry and is documented.
3. **P1-06 dual-rail integrity**: missing instrument spec → exchange stop skipped fail-closed with local stop still
   active (not raw value sent); `PositionManager::new` constructor fan-out compiles at both call sites.

## Linux empirical verification needed (no Mac cargo authority for runtime)
Per CLAUDE.md §六 + Data/Migrations rules, Mac cannot authoritatively run cargo for runtime semantics. Before
package-B sign-off, on `ssh trade-core` (read-only / build-only; NO deploy, NO restart, NO mutating Bybit calls):
- `cargo test` for the touched Rust crates (dispatch, position_manager, instrument_info, bybit_rest_client) — Linux is
  the authoritative build/test machine; Mac `cargo` is advisory only.
- Confirm engine binary builds (`cargo build --release` build-only, do NOT restart the running engine) so the new
  IPC method + PipelineCommand variant compile against the live tree.
- Python: targeted pytest for the live Stop route changes on Linux (mocked IPC) — but PG/IPC runtime semantics
  (does `cancel_all_orders` IPC actually reach the engine) require a controlled non-mutating IPC probe, which is
  deploy/restart-gated and therefore OUT of scope until operator approves a deploy.
- Do NOT provoke any live/demo trading call to validate cancel-all end-to-end; that is operator-gated.

PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--cold_audit_pkgB_exchange_semantics_spec.md
