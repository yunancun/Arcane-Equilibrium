# PM Report: AVAX Candidate-Scoped Reroute Source Patch

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Active blocker: `P0-BOUNDED-PROBE-AVAX-CANDIDATE-SPECIFIC-REROUTE-CHAIN-SOURCE-ONLY`
Next blocker: `P0-BOUNDED-PROBE-AVAX-CANDIDATE-SCOPED-CHAIN-SMOKE-DEMO-ONLY`

## Decision

Implemented the narrow source patch needed to stop AVAX from being forced back through the stale `bounded_demo_probe_order_construction_repair_v1` packet. `bounded_probe_lower_price_reroute_review.py` can now consume a fresh `bounded_demo_probe_cap_feasible_candidate_selection_review_v1` wrapper as the candidate source for lower-price reroute review.

This is an enabler only. It does not create a fresh AVAX runtime chain, does not run a quote, and does not prove profitability.

## Source Changes

- Added optional `cap_feasible_selection` / `--cap-feasible-selection-json` input to `bounded_probe_lower_price_reroute_review.py`.
- Added schema/status gate for `CAP_FEASIBLE_CANDIDATE_SELECTED_FOR_PREFLIGHT_REVIEW`.
- Added source-bound readiness: if cap-feasible selection is the candidate source, that selection itself must be fresh/schema-valid/status-ready/feasible. It cannot borrow readiness from a separate fresh repair packet.
- Kept all downstream gates unchanged: false-negative preflight, operator review, placement repair plan, operator-authorization review, authority patch readiness, and touchability preflight must still be fresh and candidate-aligned.
- Scoped the read-only PG evidence exception to `cap_feasible_selection.answers.pg_query_performed` only. Nested/root `pg_query_performed=true` still fails closed.

## Review Chain

- `PA(default)`: `DONE_WITH_CONCERNS`; no blocking design issue after source-bound readiness was present. Requested the PG evidence exception be narrowed to `answers.pg_query_performed`; PM fixed it.
- `E1(worker)`: `DONE`; fixed the E2 blocker by tying readiness to the selected candidate source. Noted file length is above the 800-line review-attention threshold, but a split would be unrelated refactor.
- `E2(explorer)`: `DONE_WITH_CONCERNS`; found a real stale-selection bug where stale cap selection could borrow fresh repair readiness. Fixed with regression coverage.
- `E4(worker)`: `DONE`; initial focused/adjacent tests passed before E2 fix. PM reran the final suite after fixes.
- `QA/PM`: `DONE_WITH_CONCERNS`; source patch is green, but final runtime evidence remains incomplete until the no-authority timestamped chain smoke is run.

## Verification

Final PM-run verification after E1/E2/PA fixes:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research \
  python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_lower_price_reroute_review.py
```

Result: `18 passed`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research \
  python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_lower_price_reroute_review.py \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_order_construction_repair.py \
  helper_scripts/research/tests/test_cost_gate_false_negative_bounded_probe_preflight.py \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_touchability_preflight.py \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_placement_repair_plan.py \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py \
  helper_scripts/research/tests/test_public_quote_market_snapshot_adapter.py \
  helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py
```

Result: `179 passed`.

Additional checks:

- `python3 -m py_compile ...`: PASS
- `git diff --check`: PASS

## Boundary

Source/test/docs only. No Bybit call, no private/auth endpoint, no order/cancel/modify, no PG query/write by this helper, no `_latest` runtime artifact overwrite, no service/env/crontab/runtime mutation, no Cost Gate lowering, no cap/freshness-gate widening, no Rust writer/adapter enablement, no probe/order/live authority, and no promotion proof.

## Remaining Concern

The source file is now `860` lines, above the repo's `800`-line review-attention threshold. PM did not split it because the change is narrow and a structural split would add unrelated blast radius.

## Aggressive Profit Hypotheses

| Hypothesis | Why it might make money | Fastest safe test | Required data | Failure condition | Authority | Score |
|---|---|---|---|---|---|---|
| AVAX cap-feasible false-negative chain | AVAX rank 2 remains cap-feasible with `73.5511bps` avg net and `48/48` positive outcomes. Removing stale repair dependency lets the system test the candidate-specific path sooner. | Timestamped no-authority chain smoke using fresh cap selection and AVAX review; expected blocker is candidate touchability/placement. | Fresh cap selection, AVAX review, candidate-scoped proposal/preflight, touchability/order-gap evidence. | Chain remains blocked on candidate-matched touchability or stale downstream artifacts. | Source/local artifact smoke only; E3/BB for any later quote. | upside high; evidence medium; realism medium; cost good; time short; account risk low; governance risk low; autonomy high |
| Candidate touchability near-touch contract | If current Demo flow has fills but no candidate-matched AVAX orders, a near-touch-or-skip design may create learning without broad overhang. | Source-only touchability/placement repair design from current order-gap artifact; no order authority. | Order-to-fill gap, candidate side-cell, placement limits, BBO gap stats. | No candidate-compatible near-touch route under cap or risk gates. | Source-only until separate bounded probe review. | upside medium-high; evidence medium; realism medium; cost medium; time medium; account risk low; governance risk low; autonomy high |
| MM current-fee repeat-window | Current-fee-positive maker cells may survive fees through maker ratio and adverse-selection control. | Independent repeat-window and OOS/maker-realism scorecard. | MM history windows, fill_sim, maker fee assumptions. | Single-window effect or net disappears after realistic fees. | Source/research only. | upside medium; evidence low-medium; realism medium; cost medium; time medium; account risk low; governance risk low; autonomy medium |

## Next Safe Action

Run `P0-BOUNDED-PROBE-AVAX-CANDIDATE-SCOPED-CHAIN-SMOKE-DEMO-ONLY`: a timestamped, no-authority chain smoke that uses the fresh cap-feasible selection wrapper and records the exact remaining blocker. Do not overwrite `_latest`; do not run a public quote or any runtime write without the normal gate.
