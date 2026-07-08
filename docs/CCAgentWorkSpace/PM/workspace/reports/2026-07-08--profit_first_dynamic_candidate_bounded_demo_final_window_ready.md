# Profit-First Dynamic Candidate Bounded Demo Final-Window Ready

Status: `READY_FOR_BOUNDED_DEMO_FINAL_WINDOW`

## Summary

E3 and BB have now both passed the current dynamic-candidate preparation chain:

- E3 verdict: `APPROVE_FOR_PM_MATERIALIZATION_PREP`
- BB verdict: `APPROVE_FOR_BOUNDED_DEMO_FINAL_WINDOW_PREP`
- Latest selected candidate at BB review time: `ma_crossover|NEARUSDT|Buy`

This does not authorize a bounded Demo execution by itself. It means PM may prepare the next same-window final gate packet. That next packet must recheck source/runtime heads, latest candidate selection, artifact shas, standing auth freshness, active Decision Lease, Guardian/Rust authority, fresh BBO, instrument filters, exact order shape, book cleanliness, auditability, reconstructability, proof exclusion, and operator authorization before any exchange-facing action.

## Current Runtime Chain

| Surface | Evidence |
|---|---|
| Standing auth | sha `05fe07f5ad4f92c459c4c6f67bfe534a04b0ea4b4e8f2d8aa43879d87009152f`, mode `600`, expires `2026-07-09T00:12:30.886090+00:00` |
| Candidate packet | sha `1387ae73d65c7ba5f476a8b562e787089673d484528c2d132e4789de11af67ae` |
| Proposal packet | sha `676f6c3ec91aae33542314fd435bb929fa5140feaf3c3c12fedd4a1b7b260282` |
| Operator review | sha `1cd8cd53845240ee58318326a3c27cd608a143086d0a2584526cb3ade5bd1c0d`, preflight-approved |
| Bounded preflight | sha `6eb1d507c18f24cf1668af6bdcf6457f3114c9dd7a345b25c66d18fb94eda36e`, READY |
| Placement plan | sha `50f6a6585e37e95a0ab12022faaed8352b3e7adb754bec2cd9cc2e8344c6a4d0`, READY |
| Authority readiness | sha `f8c3e6ee1d559f2188505f8dbe67892f9fda85b31590e050de97545b3339a167`, source READY |
| Operator auth readiness | sha `0438247d3a696d420e8272bf16d549ead70403d773fc903d97639efc75f72bd4`, `decision=defer` |

## Final-Window Requirements

The next same-window final gate must prove, in one invocation window:

- latest candidate still resolves to `ma_crossover|NEARUSDT|Buy`
- source/runtime heads remain aligned and Linux is clean
- standing auth is fresh, candidate-matched, and no-authority except loss-control envelope
- operator authorization state is exact and not silently promoted from `defer`
- active Decision Lease is acquired only inside the final gate if approved
- Guardian/Rust authority path is preserved
- fresh BBO and instrument status/filters are captured in-window
- order shape is exact, PostOnly, maker-side, near-touch-or-skip
- skip if touch gap is greater than `75bps`
- max probe intents `2`
- max notional per order `954.46746768` USDT
- audit/reconstruction paths are present
- first-attempt bootstrap is not proof

## Boundary

Not performed:

- No public/private Bybit call.
- No Decision Lease acquire/release.
- No order/probe/cancel/modify.
- No bounded Demo final window.
- No operator auth `authorize`.
- No adapter enablement.
- No service restart/build.
- No DB write/migration.
- No Cost Gate lowering.
- No live/mainnet.
- No proof/promotion.
