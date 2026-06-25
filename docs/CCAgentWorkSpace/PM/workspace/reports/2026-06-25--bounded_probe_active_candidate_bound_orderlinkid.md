# PM Report: Bounded Probe Active Candidate-Bound OrderLinkId

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Active blocker: `P0-BOUNDED-PROBE-ACTIVE-CALLER-ID-RECONSTRUCTION-CONTRACT-DEMO-ONLY`

## Decision

Closed the source-only orderLinkId/reconstruction slice. Active bounded Demo order drafts now require an `orderLinkId` that is locally Bybit-safe and candidate-bound before a draft can be submitted to the dormant dispatch helper.

This is not runtime authority. It only makes any future one-order bounded Demo probe easier to dedupe, reconstruct, and attribute to the exact side-cell/context/signal.

## Change

- Added `bounded_probe_order_link_id_for_candidate(...)` for deterministic active-probe IDs.
- Added `is_candidate_bound_bounded_probe_order_link_id(...)` and made `candidate_matched_bounded_probe_order(...)` reject IDs that do not match engine mode, event timestamp, canonical base36 sequence, side-cell, context id, and signal id.
- Kept the generic `is_bybit_safe_order_link_id_for_engine_mode(...)` unchanged for non-active-probe callers.
- Updated active bounded-probe dispatch tests so `OrderDispatchRequest.order_link_id` preserves the candidate-bound ID.
- Updated the dormant demo-learning writer active helper fixture to use the same candidate-bound ID helper.

PA found that hashing only context id + signal id was not strict enough; PM fixed the patch to include `side_cell_key` in the lineage hash.
E2 found that non-canonical leading-zero seq strings could validate and that the writer helper fixture still used the old 4-part ID; PM fixed both.

## Remaining Concerns

- Actual `adapter_enabled=true` active bounded-probe caller is still not wired or reviewed.
- Post-round bounded cap enforcement remains separate work.
- Post-restart pending-order reconciliation for created-but-unobserved bounded probes remains separate work.
- Candidate-matched bounded-probe outcome/proof review remains separate work.

## Boundary

Source/test/docs only. No runtime sync, no `/tmp` runtime artifact, no latest/plan/admission/ledger mutation, no PG read/write, no Bybit API call, no order/cancel/modify, no service/env/crontab mutation, no Rust writer enablement, no global Cost Gate lowering, no live/mainnet action, no active probe/order authority, and no promotion proof.

## Verification

- PA(default): `DONE_WITH_CONCERNS`; side-cell hash concern fixed.
- E2(explorer): `DONE` after follow-up; canonical seq + writer fixture findings fixed, no remaining blocker or authority broadening found in reviewed scope.
- E4(worker): `DONE` after follow-up; changed-file rustfmt check PASS, Rust active-order `11 passed`, dispatch helper `2 passed`, writer active helper `1 passed`, Python active-order/readiness scanner suite `40 passed`, `git diff --check` PASS.
- PM local verification after fixes: Rust active-order `11 passed`, dispatch helper `2 passed`, writer active helper `1 passed`, Python scanner suite `40 passed`, changed-file rustfmt check PASS, `git diff --check` PASS.

## Next Safe Action

Open `P0-BOUNDED-PROBE-ACTIVE-POSTROUND-CAP-CALLER-CONTRACT-DEMO-ONLY`: source-only post-round cap enforcement, actual active caller contract, post-restart reconciliation, and bounded outcome proof hook. Do not enable runtime adapter or order authority from this checkpoint.
