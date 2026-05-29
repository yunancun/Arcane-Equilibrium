# 2026-05-17 -- Bybit API Compatibility Audit

Role: BB(default)  
Repo root: `/Users/ncyu/Projects/TradeBot/srv`  
Audit mode: read-only; no trading endpoint calls; no runtime/config/auth edits  
Report created: 2026-05-29 Europe/Madrid, under the PM baseline date prefix

## Executive Summary

P0: 0. No P0 findings.

P1: 3.

P2: 4.

Blockers before LiveDemo/Mainnet exchange-facing promotion:
- `BB-API-001`: LiveDemo uses the live secret slot but still permits process env credential fallback.
- `BB-API-002`: exchange-side `/v5/position/trading-stop` prices bypass tick-size rounding and validation.
- `BB-API-003`: exchange-mutating order create has retry paths for timeout/transient failures, conflicting with the repo hard boundary wording.

Official Bybit docs checked read-only:
- `https://bybit-exchange.github.io/docs/v5/order/create-order`
- `https://bybit-exchange.github.io/docs/v5/order/pre-check-order`
- `https://bybit-exchange.github.io/docs/v5/rate-limit`
- `https://bybit-exchange.github.io/docs/v5/websocket/private/order`
- `https://bybit-exchange.github.io/docs/v5/demo`

Local startup/baseline inputs read:
- `AGENTS.md`, `CLAUDE.md`, `TODO.md`
- `.codex/MEMORY.md`, `.codex/agents/INDEX.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.codex/agents/BB.md`, `.claude/agents/BB.md`
- PM baseline, R4 report, TW report
- `docs/references/2026-04-04--bybit_api_reference.md`

## Scope Verdict

REST endpoint paths: mostly compatible for active order create/cancel/amend/trading-stop paths, with doc drift on pre-check.

WS endpoint semantics: source code environment split is safer than the dictionary; dictionary still says Demo/LiveDemo/Testnet subscribe `dcp`.

retCode handling: checked wrappers fail on nonzero `retCode`; dispatch retry policy is the exception and is reported below.

Timeout fail-closed behavior: raw client errors are returned, but close dispatch wraps per-attempt timeout into retryable `10019`, reported below.

Qty/price/tick/minNotional rounding: create order path is strong; trading-stop and amend paths are weaker.

Demo/live/mainnet auth: Mainnet hard gate exists; LiveDemo boundary is weaker than the repo's live-grade policy.

Rate limit handling: headers are parsed and groups tracked, but proactive wait is not group/path-aware.

Conditional order semantics: regular order TP/SL fields are emitted; exchange-side conditional SL sync has tick rounding risk; PostOnly reject via private WS remains the expected confirmation path.

## Findings

### BB-API-001 -- LiveDemo live slot can be overridden by process env credentials

Classification: FACT

Severity: P1

Affected path + line:
- `rust/openclaw_engine/src/bybit_rest_client.rs:139` maps `Mainnet | LiveDemo` to the `live` secret slot.
- `rust/openclaw_engine/src/bybit_rest_client.rs:901` sets `is_mainnet` only for `BybitEnvironment::Mainnet`.
- `rust/openclaw_engine/src/bybit_rest_client.rs:929` and `rust/openclaw_engine/src/bybit_rest_client.rs:943` allow `BYBIT_API_KEY` / `BYBIT_API_SECRET` fallback whenever `is_mainnet == false`, which includes LiveDemo.

Evidence command / inspection method:
- `nl -ba rust/openclaw_engine/src/bybit_rest_client.rs | sed -n '80,155p;890,970p'`
- Official demo docs read-only check: Bybit says demo uses `https://api-demo.bybit.com` and private WS `wss://stream-demo.bybit.com`, with independent demo keys.

Impact:
- LiveDemo uses demo endpoints, so this is not direct real-fund exposure.
- It is still a live-grade rehearsal path using the `live` secret slot by design. Process env credentials can silently take precedence over the Operator-managed live slot, weakening auditability, key rotation, and live-demo/live boundary testing.

Why real, not false positive:
- The code explicitly maps LiveDemo to `live` slot, then explicitly disables env fallback only for Mainnet.
- Repo hard boundaries state LiveDemo does not relax auth/TTL/risk/audit controls. This path relaxes the credential source boundary for LiveDemo.

Suggested fix direction:
- Gate env-var credential fallback on the secret slot, not only on Mainnet. If `env.secret_slot() == "live"`, ignore process env credentials and require explicit params or live slot files.
- Keep `OPENCLAW_ALLOW_MAINNET=1` as Mainnet-only, because LiveDemo should not need real-mainnet opt-in.
- Add a test that LiveDemo with env vars but no live slot does not construct a credentialed client.

Fix owner role: E1

Verification owner role: BB + E3

### BB-API-002 -- Exchange-side trading-stop prices bypass tick-size rounding and validation

Classification: FACT

Severity: P1

Affected path + line:
- `rust/openclaw_engine/src/position_manager.rs:226` builds `/v5/position/trading-stop`.
- `rust/openclaw_engine/src/position_manager.rs:232`, `:235`, `:244`, `:247` serialize TP/SL/trailing/active prices with raw `format!("{}", value)`.
- `rust/openclaw_engine/src/notification_failsafe/providers/exchange_stop_sync.rs:76` and `:84` build exchange stop sync requests directly from `StopAdjustment.new_sl`.
- `rust/openclaw_engine/src/event_consumer/bootstrap.rs:757` and `:761` pass raw `req.stop_loss` into `TradingStopRequest`.
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:1302` through `:1310` compute percentage stop prices from entry price and send them without tick rounding.
- Contrast: `rust/openclaw_engine/src/order_manager.rs:354` and `:661` through `:742` validate and round normal `/v5/order/create` qty/price before sending.

Evidence command / inspection method:
- `nl -ba rust/openclaw_engine/src/position_manager.rs | sed -n '210,275p'`
- `nl -ba rust/openclaw_engine/src/notification_failsafe/providers/exchange_stop_sync.rs | sed -n '60,120p'`
- `nl -ba rust/openclaw_engine/src/event_consumer/bootstrap.rs | sed -n '745,775p'`
- `nl -ba rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs | sed -n '1288,1315p'`
- `nl -ba rust/openclaw_engine/src/order_manager.rs | sed -n '330,430p;650,745p'`
- Official order docs read-only check: Bybit order price precision comes from `priceFilter.tickSize` in instruments-info; demo docs list `/v5/position/trading-stop` as an available demo position endpoint.

Impact:
- Raw percentage-derived stops can be off tick. Bybit can reject the exchange-side conditional stop, leaving the system with only the local stop rail.
- This directly affects the dual-rail protection model and Packet C style exchange-side conditional SL sync.

Why real, not false positive:
- Tick rounding helpers exist in `instrument_info.rs` (`round_price`, `floor_price`, `ceil_price`), and normal order create uses instrument validation. The trading-stop path does not hold or use `InstrumentInfoCache`.
- Stop prices are computed from floating-point percentage math, which commonly lands off tick.

Suggested fix direction:
- Inject/share `InstrumentInfoCache` into `PositionManager` or a small trading-stop normalizer.
- Round stop fields before REST. Use side-aware conservative rounding where side is known: long SL floor, short SL ceil; TP opposite if added.
- Validate price bounds and fail closed locally with explicit reason if instrument spec is missing.

Fix owner role: E1, with PA for side-aware rounding policy

Verification owner role: BB + E4

### BB-API-003 -- Exchange-mutating order create retries timeout/transient failures despite hard-boundary wording

Classification: FACT + INFERENCE

Severity: P1

Affected path + line:
- `rust/openclaw_engine/src/event_consumer/dispatch.rs:28` and `:46` define retry budgets for open and close intents.
- `rust/openclaw_engine/src/event_consumer/dispatch.rs:201` through `:210` classify transport and JSON parse failures as transient.
- `rust/openclaw_engine/src/event_consumer/dispatch.rs:227` through `:235` classify `10006` and `10016`-`10019` as transient.
- `rust/openclaw_engine/src/event_consumer/dispatch.rs:314` through `:318` converts close dispatch timeout into `ret_code=10019`.
- `rust/openclaw_engine/src/event_consumer/dispatch.rs:352` through `:420` runs the retry loop.
- `rust/openclaw_engine/src/event_consumer/dispatch.rs:638` through `:668` applies the retry loop to production `order_mgr.place_order(...)`.

Evidence command / inspection method:
- `nl -ba rust/openclaw_engine/src/event_consumer/dispatch.rs | sed -n '20,60p;190,235p;300,420p;620,680p'`
- Official order docs read-only check: Bybit says place-order acknowledgement is asynchronous and WebSocket should be used to confirm order status.

Impact:
- For exchange-mutating order create, an after-send timeout or response parse failure can leave order state unknown. The current code retries with the same `orderLinkId`, relying on idempotency/dedup behavior.
- This conflicts with repo hard-boundary language: timeout or nonzero `retCode` must fail closed and there must be no hidden retry paths for trading effects.

Why real, not false positive:
- This is not speculative; the retry loop is active around `order_mgr.place_order`.
- The code comments document the intended idempotency rationale, so this may be an intentionally accepted design. The finding is that the implementation and repo hard-boundary policy are not aligned.

Suggested fix direction:
- PA/CC must ratify one of two directions:
  - strict policy: remove automatic retry for exchange-mutating create and route unknown-after-send to reconciliation before any resend; or
  - explicit exception: document the idempotent retry policy as allowed only with stable `orderLinkId`, bounded attempts, and mandatory WS/order reconciliation after exhaustion.
- If retained, verify duplicate `orderLinkId` semantics across Demo, LiveDemo, and Mainnet for the exact product categories used.

Fix owner role: PA + CC for policy, E1 for implementation

Verification owner role: BB + E2 + E4

### BB-API-004 -- Amend order falls back to raw qty/price when instrument cache misses

Classification: FACT

Severity: P2

Affected path + line:
- `rust/openclaw_engine/src/order_manager.rs:536` through `:543` use `round_qty(...).unwrap_or(q)` and `round_price(...).unwrap_or(p)` for `/v5/order/amend`.
- `rust/openclaw_engine/src/order_manager.rs:661` through `:742` show the stronger create-order fail-closed path for missing instrument specs.

Evidence command / inspection method:
- `nl -ba rust/openclaw_engine/src/order_manager.rs | sed -n '520,555p;650,745p'`

Impact:
- Amend requests can send off-step qty or off-tick price if the instrument cache misses, instead of failing closed or lazily fetching specs.
- This can trigger Bybit rejects and create inconsistent behavior between create and amend paths.

Why real, not false positive:
- The fallback to raw values is explicit in code.
- The create path already documents that missing spec must fail closed because raw qty/price previously caused Bybit `Qty invalid` rejects.

Suggested fix direction:
- Reuse the create-order validation/rounding path or add an amend-specific lazy `ensure_symbol` + fail-closed branch.
- Apply the same tick/min qty/min notional discipline where amend fields are present.

Fix owner role: E1

Verification owner role: BB + E4

### BB-API-005 -- Proactive rate-limit wait is not path/group aware

Classification: FACT + INFERENCE

Severity: P2

Affected path + line:
- `rust/openclaw_engine/src/bybit_rest_client.rs:1105` and `:1165` call `wait_if_rate_limited()` before signed GET/POST without passing `path`.
- `rust/openclaw_engine/src/bybit_rest_client.rs:1267` through `:1272` expose group near-limit checks.
- `rust/openclaw_engine/src/bybit_rest_client.rs:1282` through `:1313` checks only the last global `remaining` value.
- `rust/openclaw_engine/src/bybit_rest_client.rs:1317` through `:1327` updates per-group remaining by path after the response.

Evidence command / inspection method:
- `nl -ba rust/openclaw_engine/src/bybit_rest_client.rs | sed -n '1075,1235p;1255,1335p'`
- Official rate-limit docs read-only check: Bybit publishes per-endpoint quotas and returns limit headers including remaining-status semantics; current docs list `/v5/position/trading-stop` at 10/s and order endpoints as distinct quota rows.

Impact:
- A near-exhausted order/position quota can be overwritten by the last response from a different endpoint group before the next trading endpoint request. The preflight wait may then skip even though the target group is near depletion.
- This can increase avoidable `10006` rate-limit rejects on mutating order/position paths.

Why real, not false positive:
- The client already tracks `group_remaining`, but the only pre-request gate ignores it and lacks a `path` parameter.
- Bybit quotas are endpoint/path-specific, so a last-response global value is insufficient for target-path throttling.

Suggested fix direction:
- Change `wait_if_rate_limited(path)` to derive `RateLimitGroup::from_path(path)` and consult the matching `group_remaining`.
- Track reset timestamp per group if relying on group remaining; otherwise use a conservative fallback when group reset is unknown.

Fix owner role: E1

Verification owner role: BB + E4

### BB-DOC-006 -- API reference still advertises removed `pre_check_order` using real create-order path

Classification: FACT

Severity: P2

Affected path + line:
- `docs/references/2026-04-04--bybit_api_reference.md:823` through `:826` document `client.pre_check_order(params)` as a dry-run concept over `POST /v5/order/create`.
- `docs/references/2026-04-04--bybit_api_reference.md:1333` repeats that code uses `/v5/order/create` to simulate pre-check.
- `rust/openclaw_engine/src/platform_client.rs:355` through `:359` says the old `pre_check_order()` was removed because it called real `/v5/order/create` and risked accidental live order placement.

Evidence command / inspection method:
- `nl -ba docs/references/2026-04-04--bybit_api_reference.md | sed -n '815,830p;1328,1340p'`
- `nl -ba rust/openclaw_engine/src/platform_client.rs | sed -n '345,365p'`
- Official pre-check docs read-only check: current Bybit docs list a real `POST /v5/order/pre-check` endpoint with limitations.

Impact:
- The repo's Bybit reference can mislead future work into reintroducing a dangerous fake pre-check over real order create.
- It also misses the current official `/v5/order/pre-check` endpoint semantics and limitations.

Why real, not false positive:
- Source and reference directly contradict each other.
- The reference is specifically in the exchange-facing compatibility corpus used by BB/E roles.

Suggested fix direction:
- TW/BB should update the reference to remove the fake `/v5/order/create` dry-run claim.
- If the project wants pre-check support, specify the real `/v5/order/pre-check` endpoint separately with category/margin/conditional-order limitations and explicit non-use as a trading safety gate.

Fix owner role: TW + BB

Verification owner role: BB + R4

### BB-DOC-007 -- API reference says Demo/LiveDemo/Testnet private WS includes `dcp`; source excludes it

Classification: FACT

Severity: P2

Affected path + line:
- `docs/references/2026-04-04--bybit_api_reference.md:1119` through `:1122` says Demo / LiveDemo / Testnet topics include `dcp`.
- `rust/openclaw_engine/src/bybit_rest_client.rs:119` through `:128` returns `["order", "execution", "position", "wallet"]` for Demo/LiveDemo/Testnet and only includes `dcp` on Mainnet.

Evidence command / inspection method:
- `nl -ba docs/references/2026-04-04--bybit_api_reference.md | sed -n '1115,1125p'`
- `nl -ba rust/openclaw_engine/src/bybit_rest_client.rs | sed -n '95,130p'`
- Official demo docs read-only check: demo private WS uses `wss://stream-demo.bybit.com`; source comments record demo `dcp` rejection and prior live subscribe validation.

Impact:
- Current source is safer, but the dictionary can drive future regression: re-adding `dcp` to demo/live-demo subscriptions can poison or reject private WS subscribe behavior.
- This is directly in the live_demo vs live WS boundary.

Why real, not false positive:
- The mismatch is explicit: dictionary includes `dcp`; source excludes it and documents rejection.
- The reference itself claims the subscription list is decided by `BybitEnvironment::private_ws_topics()`, but it does not match that function.

Suggested fix direction:
- Update the reference to match source: Demo/LiveDemo/Testnet use `order`, `execution`, `position`, `wallet`; Mainnet uses `order`, `execution.fast`, `position`, `wallet`, `dcp`.
- Keep a note that demo private WS does not support public data or WS Trade, per Bybit demo docs.

Fix owner role: TW + BB

Verification owner role: BB + R4

## Non-Findings / Positive Controls

- `BybitResponse::into_result()` and `get_checked`/`post_checked` enforce nonzero `retCode` as errors for checked paths.
- `/v5/order/create` path validates normal order qty/price against `InstrumentInfoCache`, including `qtyStep`, `tickSize`, min/max, and min notional.
- Mainnet REST/WS URLs are distinct from Demo/LiveDemo/Testnet, and source uses mainnet-only `execution.fast`/`dcp`.
- No mutating trading endpoints were called during this audit.
