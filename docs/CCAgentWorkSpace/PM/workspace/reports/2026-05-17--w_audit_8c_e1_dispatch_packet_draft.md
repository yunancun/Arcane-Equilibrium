# W-AUDIT-8c E1 Dispatch Packet Draft

**Date**: 2026-05-17T07:19Z  
**Role**: PM(default)  
**Status**: DRAFT / DO NOT EXECUTE UNTIL C1 FINAL PASS + BB/MIT SIGN-OFF + PM AUTHORIZATION  
**Source spec**: `docs/execution_plan/2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md`

## Gate

This packet is intentionally prepared early so dispatch can happen quickly after C1. It is not implementation authorization.

Hard prerequisites before sending this to `E1(worker)`:

1. C1 final report returns `PASS_C1_PROOF_CANDIDATE`.
2. BB signs topic safety and side semantics for `allLiquidation.{symbol}`.
3. MIT signs the payload-to-`market.liquidations` mapping or provides a V09X schema delta.
4. PM explicitly authorizes the E1 task after checking current repo/runtime state.

## Dispatch Chain

Recommended chain:

`PM -> E1(worker) -> E2(explorer) + BB(default) + MIT(default) -> E4(worker) -> PM`

Skip `PA` only if the final C1/BB/MIT evidence matches the current spec with no schema delta. If MIT requests schema changes, route back through `PA(default)` for a V09X migration spec before E1 implementation.

## E1-C1-REVIVE

**Bound role**: `E1(worker)`  
**Task shape**: implementation  
**Ownership**: Bybit public WS parser/dispatch, market liquidation writer revival, in-memory liquidation pulse provider plumbing.  
**Expected output**: patch + self-report; no commit/push by E1 unless PM explicitly grants.

Likely file ownership, to be verified by E1 before editing:

| Area | Likely files |
|---|---|
| topic guard / production subscription | `rust/openclaw_engine/src/multi_interval_topics.rs`, `rust/openclaw_engine/src/config/mod.rs` |
| parser | `rust/openclaw_engine/src/ws_client/parsers.rs`, `rust/openclaw_engine/src/ws_client/tests.rs` |
| dispatch | `rust/openclaw_engine/src/ws_client/dispatch.rs` |
| DB message / writer | `rust/openclaw_engine/src/database/mod.rs`, `rust/openclaw_engine/src/database/market_writer.rs` |
| AlphaSurface pulse | `rust/openclaw_core/src/alpha_surface.rs`, `rust/openclaw_engine/src/tick_pipeline/*` or a new provider module if local patterns require it |
| replay fail-closed regression | `rust/openclaw_engine/src/replay/strategy_adapter.rs` |

Minimum implementation requirements:

1. Parse official `allLiquidation.{symbol}` payload with `data[]` items carrying `T/s/S/v/p`.
2. Keep legacy `liquidation.{symbol}` disabled unless BB explicitly authorizes otherwise.
3. Restore a writer path into existing `market.liquidations(ts, symbol, side, qty, price)` or implement MIT-signed schema delta first.
4. Populate an in-memory rolling 60s `LiquidationPulseProvider`; strategy hot path must not poll PG.
5. Preserve fail-closed behavior: missing/stale/mixed pulse means no action and no TA fallback.
6. Keep all production topic enablement behind the post-C1 authorization path; no paper/live/mainnet enablement.
7. Add tests for parser shape, data array handling, timestamp conversion, positive numeric guards, disabled legacy topic behavior, and empty-pulse fail-closed.

Forbidden:

- enabling demo/live trading
- setting `OPENCLAW_ENABLE_PAPER=1`
- using synthetic liquidation pulses as alpha evidence
- PG hot-path reads inside strategy `on_tick`
- removing guard rails for `price-limit.*` or `adl-notice.*`
- treating C1 interim health as PASS

## E1-8C-STAGE0R

**Bound role**: `E1(worker)`  
**Task shape**: read-only tooling implementation  
**Ownership**: W-AUDIT-8c Stage 0R query/report packet only.  
**Expected output**: read-only helper/report tooling + tests.

Start this only after `market.liquidations` has real rows from the signed path.

Likely files:

| Area | New or modified files |
|---|---|
| query | `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql` |
| report tooling | `helper_scripts/reports/w_audit_8c_liquidation_cluster_stage0r.py` and/or package under `helper_scripts/reports/w_audit_8c/` |
| tests | targeted smoke tests under `helper_scripts/reports/` or `tests/` matching local patterns |
| script index | `helper_scripts/SCRIPT_INDEX.md` if a new script is added |

Stage 0R packet must emit:

- C1 proof id and BB/MIT sign-off references
- source topic and symbol set
- BB-signed side mapping
- cluster construction parameters
- pooled/per-symbol `n` and `n_eff`
- primary mean-reversion branch and momentum sensitivity branch if inspected
- avg gross/net bps after conservative cost
- PSR(0), DSR with explicit `K_total`, PBO, block-bootstrap CI
- stale/missing/mixed/quiet-window exclusion counts
- `eligible_for_demo_canary=true/false`

Acceptance:

- empty `market.liquidations` must produce `eligible_for_demo_canary=false`
- as-of joins only; no forward leakage
- no single lucky threshold without plateau support
- primary mean-reversion branch must pass independently

## Review Assignment

`E2(explorer)` review:

- no TA fallback when `liquidation_pulse` missing/stale/mixed
- no REST/PG polling loop in strategy hot path
- no multiple actions from one cluster id
- strict as-of replay and quiet-window handling
- no accidental paper/live/mainnet enablement

`BB(default)` review:

- topic syntax and guard removal are exactly scoped
- `S=Buy/Sell` side semantics and strategy direction mapping
- no handler-not-found / poisoning regression
- production builder changes wait for C1 final PASS

`MIT(default)` review:

- writer schema mapping
- dedupe and timestamp precision
- `K_prior`, DSR/PBO/bootstrap/sample-floor math
- market.liquidations rows are real signed-path data, not synthetic fixtures

`E4(worker)` regression:

- targeted Rust tests for parser/dispatch/provider/replay fail-closed
- helper script smoke tests if Stage 0R tooling is added
- `cargo check -p openclaw_engine`
- `git diff --check`

PM STATUS: DRAFT READY / EXECUTION BLOCKED UNTIL C1 FINAL PASS.
