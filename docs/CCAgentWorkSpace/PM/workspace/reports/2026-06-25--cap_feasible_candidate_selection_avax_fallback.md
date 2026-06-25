# PM Report: Cap-Feasible AVAX Fallback Selection

Date: 2026-06-25
Status: DONE
Active blocker: `P0-BOUNDED-PROBE-CAP-FEASIBLE-CANDIDATE-REROUTE-DEMO-ONLY`

## Decision

Closed the cap-feasible fallback candidate selection checkpoint. ETHUSDT Buy remains a high-upside research lead, but it is excluded from the current bounded Demo path under the `10 USDT` cap. The selected bounded Demo fallback candidate is `grid_trading|AVAXUSDT|Sell`.

## Actions

- E3 reviewed the runtime/PG surface and returned `DONE_WITH_CONCERNS`.
- PM performed read-only PG `SELECT` only with `PGOPTIONS="-c default_transaction_read_only=on"`.
- Generated timestamped artifacts only under `/tmp/openclaw/cost_gate_learning_lane`.
- Did not overwrite `_latest` pointers.
- Generated a cap-feasible false-negative candidate universe screen.
- Generated an AVAX false-negative operator review packet for preflight review only.
- Generated a wrapper selection packet tying the universe, AVAX review, and ETH cap exclusion together.

## Evidence

- Candidate universe: `/tmp/openclaw/cost_gate_learning_lane/candidate_universe_instrument_screen_false_negative_cap_feasible_20260625T214943Z.json`
  - sha256 `09627dcd46526e7c15d1084883aa034fa6bc2e0323667206f2ef59bdefa83ecb`
  - schema `bounded_probe_candidate_universe_instrument_screen_input_v1`
  - `fits_current_cap_count=8`
  - top fit `grid_trading|AVAXUSDT|Sell`
  - read-only PG source, `pg_write_performed=false`, `bybit_call_performed=false`
- AVAX operator review: `/tmp/openclaw/cost_gate_learning_lane/false_negative_operator_review_avax_sell_cap_feasible_20260625T214943Z.json`
  - sha256 `3e7cbb774cb351eb184f5aea07d8f723abcf69132d423ba0a74397c792037b9b`
  - status `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`
  - selected `grid_trading|AVAXUSDT|Sell`, false-negative rank `2`
  - review scope is preflight only, not probe/order authority
- Selection wrapper: `/tmp/openclaw/cost_gate_learning_lane/cap_feasible_candidate_selection_avax_sell_20260625T214943Z.json`
  - sha256 `909651b8428c0903b7d0e415b17e65cec6f95d2f73fde6e7290a87fd49c9d01e`
  - status `CAP_FEASIBLE_CANDIDATE_SELECTED_FOR_PREFLIGHT_REVIEW`
  - AVAX current cap `10.0`, minimum required notional `5.0`, min positive qty notional `0.6209`
  - avg net `73.5511bps`, net-positive `100.0%`, outcomes `48`
  - ETH exclusion source: `CANDIDATE_CONSTRUCTION_NOT_FEASIBLE_UNDER_CAP`

## Verification

- Focused helper tests: `27 passed`.
- py_compile on false-negative/preflight/order-construction/reroute helpers: PASS.
- Artifact validation confirmed explicit no-authority answers, no Bybit call, no PG write, no Cost Gate lowering, no live authority, and no promotion proof.

## Boundary

Read-only PG plus timestamped `/tmp/openclaw` artifacts and docs only. No Bybit call, no order/cancel/modify, no PG write, no `_latest` overwrite, no service restart, no env/crontab mutation, no Cost Gate lowering, no cap widening, no Rust writer/adapter enablement, no probe/order/live authority, and no promotion proof.

## Next Safe Action

Build or refresh an AVAX candidate-specific no-order construction preview before any bounded-probe authorization or order path. If that requires public Bybit quote/BBO refresh, stop for PM -> E3 -> BB review first.
