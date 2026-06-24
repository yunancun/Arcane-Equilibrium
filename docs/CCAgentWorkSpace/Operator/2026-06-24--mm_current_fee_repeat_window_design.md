# Operator Note — MM Current-Fee Repeat-Window Design

Date: 2026-06-24

## What Changed

Source commit `09d0536bdae54884368b332b772fc3b20a41baa0` hardens the MM current-fee confirmation packet.

The SOXLUSDT maker candidate is still only a one-window current-fee-positive lead, not profit proof. The packet now requires exact same-candidate repeat evidence from `fill_sim_history_scorecard.window_summaries` before it can advance:

- exact `candidate_key`
- source/scope/symbol/queue/policy/track identity match
- positive current-fee net bps
- nonzero sample count
- independent window dates

Missing, malformed, or internally inconsistent history fails closed and cannot produce `repeat_window_confirmed=true`.

## Authority Boundary

No authority was granted or used.

This checkpoint did not:

- lower global Cost Gate
- grant probe/order/live authority
- call Bybit
- write PG or change schema
- edit crontab
- restart service
- mutate runtime env/auth/risk/order/strategy state
- enable Rust writer
- create promotion proof

Broad Demo API authorization is recorded as operational permission, but this packet still does not become candidate-specific bounded probe/order authority.

## Verification

- E2 final review: PASS
- E4 final review: PASS
- MM confirmation tests: `13 passed`
- Learning worklist tests: `11 passed`
- Alpha throughput tests: `83 passed`
- Profitability scorecard tests: `18 passed`
- py_compile: passed
- `git diff --check`: passed
- Runtime copied-artifact smoke: current SOXLUSDT packet remains `MM_CURRENT_FEE_CONFIRMATION_REQUIRES_REPEAT_WINDOW`, observed independent windows `1`, malformed count `0`, `repeat_window_confirmed=false`, and authority flags false.

## Next Safe Action

Next blocker: `P1-MM-CURRENT-FEE-REPEAT-WINDOW-EVIDENCE-ACCUMULATION`.

The next useful evidence is a new independent valid same-candidate fill_sim window, or a source-only aggressive-alpha pivot. Do not treat this as order/probe authority or profitability proof.
