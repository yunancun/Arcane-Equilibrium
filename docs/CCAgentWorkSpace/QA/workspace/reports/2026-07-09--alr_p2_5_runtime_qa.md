# QA Runtime Acceptance - ALR P2-5

Date: 2026-07-09
Verdict: `PASS_P2_5_DEFER_AND_ROTATE`

Linux evidence confirms V153, an active ALR service pinned to `2787042d0`, one
append-only deferred feedback event, and one subsequent target run. Feedback
fields are `DEFER_EVIDENCE`, no proof packet, zero reward records, rotation true,
and global stop false. Two research-only runs have 64 source lineage edges.

No proof/promotion/serving claim exists. `alr_shadow` UPDATE/DELETE on feedback
and scanner INSERT remain denied. A concurrent scanner count increase was
attributable only to the unchanged engine process, not ALR. P2-6 is next; P2-8
still awaits a separately safe no-order engine notifier activation path.
