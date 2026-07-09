# RFC — LG-3 Provider Pricing Table Binding

Date: 2026-05-01
Owner: PA
Status: Ready for PM/E2/E4 review
Scope: Wave 4 pre-stage RFC for formal Bybit fee/pricing binding before supervised live gates.

## Executive Summary

LG-3 makes the provider pricing table explicit and testable. The current engine already has the key pieces:

- `AccountManager::refresh_fee_rates()` calls Bybit V5 `GET /v5/account/fee-rate`.
- `AccountManager::maker_fee()` and `taker_fee()` provide per-symbol cached reads.
- `IntentProcessor::fee_rate_for_intent()` uses PostOnly `TimeInForce` to choose maker fees and taker-like orders to choose taker fees.
- Demo/LiveDemo unsupported fee endpoint behavior is handled by conservative default seeding; mainnet must remain fail-closed.

The missing part is a formal binding contract: category mapping, staleness thresholds, healthcheck semantics, and startup assertions.

## Pricing Sources

| Source | Runtime Function | Purpose |
|---|---|---|
| Bybit account fee-rate | `GET /v5/account/fee-rate?category=linear` | maker/taker per symbol |
| Cached account manager | `AccountManager::{maker_fee,taker_fee}` | zero-latency hot-path reads |
| Conservative demo defaults | `seed_default_fee_rates()` | demo/live_demo fallback when endpoint unsupported |
| Slippage tiers | `RiskConfig.slippage` | taker-style turnover slippage estimate |
| TIF selection | `IntentProcessor::fee_rate_for_intent()` | PostOnly -> maker, otherwise taker |

## Binding Contract

### Category

Initial LG-3 scope is Bybit linear contracts only:

```text
Bybit category = linear
OpenClaw engine modes = demo, live_demo, live
```

Any future spot/inverse category must add an explicit category map and tests; no implicit fallback.

### Refresh Cadence

| Engine | Refresh | Stale Policy |
|---|---:|---|
| demo | hourly | seed conservative defaults if demo endpoint returns known unsupported response |
| live_demo | hourly | same as demo endpoint behavior |
| live/mainnet | hourly | fail closed if fee table stale beyond max age |

Recommended max age:

- demo/live_demo: 120 minutes before WARN, because defaults can be conservative and explicit.
- live/mainnet: 30 minutes WARN, 60 minutes FAIL until operator approves a different SLA.

### Fail-Closed Rules

Mainnet must not use default fee rates as an availability workaround. If Bybit fee-rate refresh fails or becomes stale:

- cost gate blocks new opens;
- closes/reduces remain allowed through existing protective paths;
- healthcheck marks the pricing binding FAIL;
- operator sees the last successful refresh timestamp and affected symbols.

Demo/live_demo may use conservative defaults only when the endpoint is the known unsupported demo response. Other business errors remain failures.

## Required Tests

| Test | Assertion |
|---|---|
| fee endpoint parser | parses `makerFeeRate` and `takerFeeRate` into `FeeRate` |
| category binding | only `linear` is active in LG-3 |
| PostOnly fee choice | PostOnly intent uses maker fee |
| non-PostOnly fee choice | market/GTC intent uses taker fee |
| demo unsupported fallback | seeds defaults and stamps refresh time |
| mainnet unsupported failure | does not seed defaults and blocks |
| stale startup assertion | active live engine cannot start/promo without fresh pricing |
| healthcheck report | exposes age, source, category, and fallback source |

## Healthcheck Shape

Add or extend a pricing healthcheck with this output:

```text
pricing_binding: mode=live_demo category=linear source=bybit|demo_default
last_refresh_age=12.4m symbols=128 stale_limit=120m verdict=PASS
```

For live/mainnet:

```text
pricing_binding: mode=live category=linear source=bybit
last_refresh_age=64.1m stale_limit=60m verdict=FAIL
new opens fail-closed; closes/reduces unaffected
```

## Implementation Plan

### T1 — Contract Tests

Pin the current behavior in Rust tests:

- Bybit response parse;
- maker/taker path from TimeInForce;
- demo unsupported endpoint fallback;
- mainnet unsupported endpoint refusal.

### T2 — Healthcheck / Status Surface

Expose the current fee cache age and source. If no source marker exists today, E1 should add a small enum or string in `AccountManager`:

- `bybit_api`;
- `demo_conservative_default`;
- `cold_default`.

`cold_default` is acceptable only during startup warmup and must not pass live acceptance.

### T3 — Startup / Promotion Assertion

Before LG-4 supervised live approval can apply, assert:

- category is `linear`;
- active symbols have fee lookup available;
- `last_fee_refresh_ms` is within the live threshold;
- live/mainnet did not use a default fallback.

## Rollback

LG-3 implementation is mostly validation and healthcheck logic. Rollback path:

- disable the new healthcheck fail if it false-reds, but keep runtime fee cache unchanged;
- never switch live/mainnet to conservative defaults as rollback;
- leave existing demo default seeding intact.

## Root-Principle Check

| Principle | Verdict |
|---|---|
| #5 Survival over profit | Fresh cost model blocks bad opens before live. |
| #6 Fail conservative | Mainnet stale pricing fails closed. |
| #8 Explainability | Fee source and age become auditable. |
| #13 Cost awareness | Maker/taker binding is formalized. |
| #14 Zero external cost | No paid dependency; Bybit account endpoint only. |

## Open Questions

- Whether stale thresholds should live in RiskConfig, BudgetConfig, or a dedicated pricing config.
- Whether startup should block only live/mainnet or also live_demo when fee source is `cold_default`.

