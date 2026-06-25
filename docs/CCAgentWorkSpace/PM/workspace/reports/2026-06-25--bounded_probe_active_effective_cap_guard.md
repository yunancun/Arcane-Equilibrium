# PM Report: Bounded Probe Active Effective Cap Guard

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Active blocker: `P0-BOUNDED-PROBE-ACTIVE-POSTROUND-CAP-CALLER-CONTRACT-DEMO-ONLY`

## Decision

Closed the source-only effective/post-round cap slice. Active bounded Demo drafts now share a fail-closed effective-notional cap helper, and the dormant active dispatch seam rechecks the cap immediately before sending an `OrderDispatchRequest`.

This is not runtime or order authority. It only prevents any future caller-mutated or post-round effective draft from leaving the source seam if `effective_qty * limit_price` exceeds the approved bounded cap.

## Change

- Added `active_bounded_probe_effective_notional_within_cap(...)`.
- Reused that helper in `candidate_matched_bounded_probe_order(...)`.
- Updated `dispatch_admitted_bounded_probe_order(...)` to return `Ok(false)` without sending when the final effective draft breaches cap.
- Updated `active_bounded_probe_order_submission(...)` to map that no-send result to `Ok(None)`.
- Added a dispatch test that mutates an admitted draft above cap and confirms no `OrderDispatchRequest` is sent.

## Remaining Concerns

- Actual `adapter_enabled=true` active bounded-probe caller is still not wired or reviewed.
- Post-restart pending-order reconciliation for created-but-unobserved bounded probes remains separate work.
- Candidate-matched bounded-probe outcome/proof review remains separate work.

## Boundary

Source/test/docs only. No runtime sync, no `/tmp` runtime artifact, no latest/plan/admission/ledger mutation, no PG read/write, no Bybit API call, no order/cancel/modify, no service/env/crontab mutation, no Rust writer enablement, no global Cost Gate lowering, no live/mainnet action, no active probe/order authority, and no promotion proof.

## Verification

- PA(default): `DONE_WITH_CONCERNS`; design sane, no safety blocker; unrelated rustfmt churn was removed.
- E2(explorer): `DONE`; no findings, no authority broadening.
- E4(worker): `DONE`; Rust active-order `12 passed`, active bounded submission `2 passed`, effective cap no-send dispatch `1 passed`, writer active helper `1 passed`, Python active-order/readiness scanner suite `40 passed`, `git diff --check` PASS.
- PM local verification matched E4.

## Next Safe Action

Open the remaining source-only active caller/reconciliation/outcome-proof slice. Do not enable the runtime adapter, submit Demo orders, or treat this checkpoint as probe/order authority.
