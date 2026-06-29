# 2026-06-29 -- IBKR Stock/ETF Paper+Shadow Plan PA Review

STATUS: DONE_WITH_CONCERNS

PA verdict: the proposed `stock_etf_cash` paper+shadow lane is directionally sound as an isolated research lane, but it is not ready for E1 implementation. The only ready next step is Phase 0 governance/spec work. E1 should not start until the ADR explicitly amends the current Bybit-only execution doctrine for IBKR paper/shadow research, and until the Rust IPC/order-lifecycle interface, DB lineage contract, feature-flag enforcement points, and GUI lane semantics are narrowed enough to be testable.

Severity count: Critical 1, High 6, Medium 8, Low 2.

## Review Scope

Bound role: PA(default). Scope owner: technical architecture and implementation sequencing review.

Requested sources read:

- `AGENTS.md`
- `CLAUDE.md`
- `.codex/MEMORY.md`
- `README.md`
- `docs/agents/context-loading.md`
- `docs/execution_plan/2026-05-21--m13_asset_class_venue_design_spec.md`
- `docs/adr/0040-multi-venue-gate-spec.md`
- `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`

Additional context used for architecture vocabulary and current state:

- `CONTEXT.md`
- `TODO.md`
- `.codex/agents/PM.md`
- `.codex/agents/PA.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `.codex/SUBAGENT_EXECUTION_RULES.md`
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-24--demo-learning-autonomy-pa-next-plan.md`
- Key implementation anchors in `rust/openclaw_types`, `rust/openclaw_engine`, `sql/migrations`, and `program_code/exchange_connectors/bybit_connector/control_api_v1/app`.

No code or runtime files were changed by this review. This report is the only intended filesystem change.

## Executive Verdict

The plan's strongest architectural choice is the lane separation: `crypto_perp` remains the active Bybit lane, while `stock_etf_cash` is proposed as a paper/shadow research lane with no live, margin, short, options, CFD, transfer, or non-Bybit true-live authority. That shape is compatible with the Engine/Bridge doctrine if the seam is drawn in Rust and Python stays an adapter/Control Plane surface.

The plan's main weakness is that several proposed Modules are still names rather than Interfaces. `asset_lane_router`, `broker_order_lifecycle`, `stock_shadow_engine`, `ibkr_paper_execution_adapter`, and the Python IBKR connector are plausible, but the caller obligations, fail-closed errors, lineage fields, and ordering rules are underspecified. If implemented as named pass-throughs, they will be shallow Modules and will spread lane knowledge through callers.

E1 should therefore be re-scoped as "ADR + interface contract + migration design source only", not as runtime integration. IBKR read-only/paper connectivity belongs after those contracts are accepted.

## Architectural Area Assessment

### Rust Types And Core Seams

Directionally sound: adding an `AssetLane` concept above existing `AssetClass`/`Venue` is the right seam. It avoids treating equities/ETFs as just another crypto venue variant.

Current-state conflict: M13 is already implemented in `rust/openclaw_types/src/asset_venue.rs:25` and `rust/openclaw_types/src/asset_venue.rs:65`. It is an interface reservation for crypto/Bybit/Binance-era asset/venue taxonomy, with explicit no-dispatch scope in `rust/openclaw_types/src/asset_venue.rs:5` and `rust/openclaw_types/src/asset_venue.rs:12`. The IBKR plan must not casually extend that `Venue` enum with broker-paper/live states. That would blur the existing ADR-0040 seam and make paper/live environment look like venue identity.

Recommended shape:

- Keep `AssetLane::{CryptoPerp, StockEtfCash, CfdMarginReserved}` as a separate type.
- Prefer `Broker::{Bybit, Ibkr}` plus `BrokerEnvironment::{ReadOnly, Paper, LiveReserved}` over `BrokerVenue::{Bybit, IbkrPaper, IbkrLiveReserved}`.
- Keep `IbkrLiveReserved` out of concrete runtime routing. If a reserved value exists for serialization/future-proofing, parsing or using it in any order path must return a typed governance-denied error.
- Put pure deterministic cost/calendar/risk predicates in `openclaw_core` only when they have a small Interface and broad reuse. Runtime admission, config loading, and broker lifecycle belong in `openclaw_engine`.

### Engine Routing And Order Lifecycle

Not E1-ready. The proposed `asset_lane_router` and `ibkr_paper_execution_adapter` need a defined external Interface before implementation.

The existing router anchor is not production routing. `rust/openclaw_engine/src/order_router.rs:1` is the M12 interface stub, and its own comments say method bodies remain deferred/fail-loud until a later implementation phase (`rust/openclaw_engine/src/order_router.rs:5`). Its `OrderRequest` is still venue/asset-class shaped (`rust/openclaw_engine/src/order_router.rs:51`). It should not be treated as the place to "just add IBKR".

The existing paper IPC path is also unsuitable for stock/ETF broker-paper orders. Python `submit_paper_order` sends only symbol/side/qty/order_type/confidence/strategy (`program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client.py:435`), and Rust converts that into `PipelineCommand::SubmitOrder` (`rust/openclaw_engine/src/ipc_server/handlers/strategy.rs:157` and `rust/openclaw_engine/src/ipc_server/handlers/strategy.rs:197`). There is no asset lane, broker, environment, instrument identity, currency, listing venue, fee model version, or shadow-vs-paper execution source in the Interface.

Required before E1 implementation:

- Define a lane-scoped Rust command/IPC method instead of overloading `submit_paper_order`.
- Define order lifecycle states for broker-paper separately from archived Paper mode.
- Define typed rejection reasons: lane disabled, broker disabled, live reserved, instrument not tradable, market closed, currency/FX unavailable, cost model missing, universe version mismatch, credentials unavailable, connector unavailable.
- Add acceptance tests at the Rust Interface: default flags reject; `IbkrLiveReserved` rejects; unknown `asset_lane` rejects; broker-paper cannot write `trading.fills`; synthetic shadow and IBKR paper fill paths are distinguishable.

### Python Connector Placement

Directionally sound with strict constraints. Placing IBKR code under `program_code/broker_connectors/ibkr_connector/` is better than hiding it under the Bybit connector path.

The catch is that the current FastAPI app lives under a Bybit-named directory, and its existing paper routes are explicitly tied to Rust as the sole Paper engine (`program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py:141`). New Python modules must therefore be thin adapters and Control Plane routes only:

- Health/read-only status.
- Credential presence checks without secret disclosure.
- Paper account/fill import into Rust/DB-approved evidence Interfaces.
- Fixtures for deterministic tests.

Python must not become a trading authority, not hold broker order state as truth, and not decide risk/cost/tradability. It should not manage TWS/Gateway lifecycle as a side effect of route calls. Reconnect logic must never resubmit orders.

### DB Schema

Directionally correct to isolate broker/research/audit tables, but the table list is not yet a migration contract.

Do not reuse `trading.orders` / `trading.fills` as the canonical stock/ETF proof store. The existing trading schema has `category` and `is_paper`, but lacks asset lane, broker environment, instrument identity, fill provenance, and cost-model lineage. The stronger precedent is `replay.simulated_fills`, which keeps simulated evidence out of true trading fills, and `learning.decision_shadow_fills`, which explicitly marks paper-only shadow evidence.

Missing before migration implementation:

- Primary keys and uniqueness for `broker_order_id`, `broker_fill_id`, `instrument_id`, `listing_venue`, `currency`, and environment.
- CHECK constraints for `asset_lane='stock_etf_cash'`, `environment IN ('readonly','paper')`, and no live/margin/short/options/CFD values.
- Explicit `execution_source` or equivalent enum distinguishing `ibkr_paper_fill` from `synthetic_shadow_fill`.
- Cost lineage: cost model version, fee schedule source, FX rate source/time, commission estimate vs observed commission, slippage model version.
- Universe lineage: universe version, inclusion reason, exclusion reason, tradability status, freeze timestamp.
- Append-only or supersede policy for corporate actions and market sessions.
- Linux PostgreSQL dry-run plan and double-apply/idempotency verification per repo rules.

### Feature Flags

The flag list is broadly right, but the enforcement model is underspecified.

The existing runtime forwards selected environment values explicitly through scripts such as `helper_scripts/restart_all.sh`; new flags will not matter unless they are forwarded, surfaced, and tested. A feature flag is not Authorization and not operator sign-off.

Recommended enforcement:

- `OPENCLAW_ASSET_LANE_DEFAULT=crypto_perp` remains the only default.
- `OPENCLAW_STOCK_ETF_LANE_ENABLED=0` gates only visibility/readiness until ADR acceptance.
- `OPENCLAW_IBKR_READONLY_ENABLED=0` and `OPENCLAW_IBKR_PAPER_ENABLED=0` must require the lane flag plus the ADR gate.
- `OPENCLAW_STOCK_ETF_SHADOW_ONLY=1` should be a mode assertion, not a bypass.
- `OPENCLAW_IBKR_LIVE_ENABLED` should not be a functional enable flag. If present before a live ADR, it should be ignored with a loud denied status, not wired as a dormant switch.

### GUI Routing

Directionally sound to expose lane context, but risky if implemented as a first-screen lane selector with authority implications.

The current console tab registry is static and includes `Legacy Paper` as a hidden/conditional trading tab (`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/console.html:351` and `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/console.html:357`). Existing user workflow is Bybit-first and Demo-focused. Introducing a login-success selector can create accidental mental-model drift: selecting a lane in the Control Plane must not look like enabling a trading lane.

Safer first GUI slice:

- Show a lane badge/filter defaulted to `crypto_perp`.
- Add a read-only stock/ETF readiness/status page after backend status endpoints exist.
- Keep `Legacy Paper` separate from IBKR broker-paper terminology.
- Require all new stock/ETF routes to accept and validate `asset_lane=stock_etf_cash`; unknown or omitted values default to `crypto_perp` for existing routes and reject for stock routes.
- Never let localStorage, query params, or tab selection imply trading authority.

### Phase Ordering

The plan's Phase 0 is correct and should be treated as a hard stop, not a preface. Phase 1 is too broad as written.

Recommended re-ordering:

1. Phase 0: ADR/AMD only, no runtime/API/schema changes.
2. Phase 1A: Rust type reservation and denial tests only.
3. Phase 1B: config/feature-flag parser and readiness-status contract, all default OFF.
4. Phase 1C: DB migration source design and dry-run plan, no runtime writes.
5. Phase 1D: Rust IPC/order-lifecycle Interface for lane-scoped broker-paper/shadow commands, no IBKR connector.
6. Phase 2A: Python read-only connector fixtures and health checks only.
7. Phase 2B: IBKR read-only account/instrument/session observation after E3/security/operator checklist.
8. Phase 3: shadow collector + scorecard after universe/cost model freeze.
9. Phase 4: GUI views after backend Interface and DB lineage are stable.
10. Phase 5: evidence collection clock starts only after data completeness, frozen universe, frozen cost model, and scorecard reproducibility pass.

## Findings

### Critical

**C1. Governance unlock is a hard E1 precondition, not just a Phase 0 task.**

Current project doctrine still says Rust Engine owns trading truth, Python is Bridge/Control Plane, Bybit is the only execution exchange, and old Paper is not a promotion lane. M13/ADR-0040 reserve multi-asset/multi-venue concepts only in the Bybit/Binance trajectory; they do not approve a stock broker. The IBKR plan correctly acknowledges a required ADR, but E1 must not start until that ADR/operator approval exists and TODO carries the accepted row. Any implementation before that would create a product-scope change without Authorization.

### High

**H1. The type taxonomy mixes broker identity with environment.**

`BrokerVenue::{Bybit, IbkrPaper, IbkrLiveReserved}` is too coarse. It forces paper/live state into venue identity and makes fail-closed rules harder to express. Use `Broker` + `BrokerEnvironment` + `AssetLane`, and keep live reserved states unrouteable.

**H2. Engine routing Interface is underspecified and cannot reuse current Paper IPC.**

The current `submit_paper_order` path is a Bybit-shaped Paper mode command, not a lane-neutral broker-paper order Interface. A new lane-scoped IPC/Rust command is required before connector work. Overloading the current path would leak stock/ETF semantics into callers and make the Module shallow.

**H3. Broker-paper terminology collides with archived Paper mode.**

The Rust paper pipeline currently writes disabled markers saying Paper is archived and to use Replay Stage 0R + Demo micro-canary (`rust/openclaw_engine/src/main_pipelines.rs:266`). IBKR "paper" must be named and displayed as broker-paper/rehearsal evidence, not as a restart of the legacy Paper promotion lane.

**H4. DB schema proposal is a table inventory, not an evidence contract.**

The plan needs exact constraints, lineage columns, uniqueness rules, and write ownership before migration work. Without those, implementation will likely spread evidence semantics across routes, scorecard code, and ad-hoc SQL.

**H5. Feature flags are listed, but the fail-closed state machine is not defined.**

Flags must be parsed, forwarded, surfaced, and tested at the Engine seam. `OPENCLAW_IBKR_LIVE_ENABLED` is especially risky as a normal env var name; before a live ADR, it should be a denied/reserved status, not an enable path.

**H6. Python connector authority needs an explicit no-trading Interface.**

The connector placement is right, but the allowed operations need to be narrow: read-only health, account/instrument observation, and paper-fill import through Rust/DB-approved Interfaces. No Python-side risk, scorecard authority, order truth, or reconnect-driven order behavior.

### Medium

**M1. `openclaw_core::calendar` is over-generalized for the first slice.**

A broad calendar Module will be shallow unless it hides real complexity. Start with a stock/ETF market-session Interface needed by risk and evidence clocks, then deepen only after more than one caller needs it.

**M2. `equity_instrument` risks front-loading too much product taxonomy.**

Primary exchange, PRIIPs/KID, fractional eligibility, UCITS, corporate actions, and tradability are valid concepts, but E1 should reserve only what the initial frozen universe and evidence reconstruction need. CFD/margin/options should remain reserved-denied, not partially modeled.

**M3. `stock_etf_risk` placement needs a pure/runtime split.**

Pure predicates can live in `openclaw_core`; runtime config, gate status, and admission decisions belong in `openclaw_engine`. The Interface should return typed denial reasons so GUI and evidence tables do not reimplement risk interpretation.

**M4. GUI lane selector should not be the first visible behavior change.**

Start with a status badge/filter and explicit stock/ETF read-only views. A login-time selector can imply the Control Plane chooses trading authority, which contradicts the Engine/Authorization model.

**M5. Evidence clock start conditions need quantitative completeness thresholds.**

"5 trading days" is not enough. The plan should define session completeness, stale-data tolerance, paper-vs-shadow divergence thresholds, symbol concentration limits, benchmark definitions, and event-day handling before the clock starts.

**M6. Phase 1 should be split into no-connector slices.**

Type/config/schema/IPC should land before any IBKR connectivity. This reduces blast radius and lets reviewers test fail-closed semantics without broker credentials.

**M7. Cost model must treat unknown costs as blocking or conservative.**

Zero-fee placeholders must be disallowed unless the fee schedule explicitly says zero. Missing commission, exchange fee, regulatory fee, FX conversion, borrow/margin, tax, or slippage inputs must produce typed unavailable/conservative status.

**M8. Broker/security ownership is not named.**

The plan includes E3/QC/MIT review but does not assign a broker integration/security owner equivalent to the current Bybit adapter audit responsibility. IBKR credentials, TWS/Gateway behavior, account permissions, and paper/live account separation need explicit ownership before external connectivity.

### Low

**L1. Connector directory requires docs/index updates.**

`program_code/broker_connectors/ibkr_connector/` is the right direction, but README/developer docs should explain that this is a Bridge adapter, not the Engine or trading authority.

**L2. Naming should avoid `BrokerVenue`.**

`BrokerVenue` is likely to age poorly because broker, venue/listing exchange, and environment are separate concepts in equities. Prefer narrower names even if the first implementation has only one broker adapter.

## Implementation Slices Before E1

E1 should be preceded by these slices, in order:

1. Governance slice: accepted ADR/AMD, operator approval, TODO row, and explicit statement that this is paper/shadow research only.
2. Taxonomy slice: minimal Rust types for `AssetLane`, `Broker`, `BrokerEnvironment`, `InstrumentKind`, and `EquityInstrumentId`; denial tests for live/margin/short/options/CFD.
3. Flag/readiness slice: parse and surface flags, all default OFF, live reserved ignored/denied, restart script forwarding covered.
4. DB contract slice: migration source plus dry-run/idempotency plan; no writes from runtime yet.
5. IPC/order-lifecycle slice: lane-scoped Rust Interface with typed denial reasons and no IBKR connector dependency.
6. Read-only adapter slice: Python IBKR fixtures and health/read-only status; no order methods.
7. Scorecard-shadow slice: synthetic shadow collector and deterministic scorecard using frozen fixtures.
8. GUI status slice: lane badge/readiness page only; no broker-paper controls until backend Interfaces are stable.
9. IBKR paper rehearsal slice: only after read-only stability, E3/security checklist, universe freeze, cost model freeze, and evidence schema are accepted.

## Missing Preconditions Before E1 Work

- Accepted ADR/operator approval amending Bybit-only doctrine for IBKR paper/shadow research only.
- PM row in `TODO.md` after Phase 0, not before.
- Explicit non-reuse decision for legacy Paper mode and `submit_paper_order`.
- Rust Interface spec for lane-scoped broker-paper/shadow commands.
- Migration number/head confirmation and Linux PostgreSQL dry-run plan.
- Secret-slot policy and redaction tests for `$OPENCLAW_SECRETS_DIR/external/ibkr/...`.
- Feature-flag propagation plan through startup scripts and status endpoints.
- Frozen initial universe definition and evidence completeness thresholds.
- Named broker/security owner for IBKR account/API/TWS/Gateway behavior.

## Final PA Verdict

Proceed with Phase 0 only. Do not dispatch E1 implementation yet.

The module split is architecturally plausible if the `AssetLane` seam is kept above existing M13 `Venue`, broker identity is separated from environment, Rust owns lane routing/order lifecycle/evidence truth, Python remains a thin adapter, and DB evidence stays out of true trading tables. The current proposal needs one more hardening pass before implementation: make the Interfaces concrete, shrink Phase 1, define fail-closed denial states, and lock evidence lineage before touching IBKR connectivity.
