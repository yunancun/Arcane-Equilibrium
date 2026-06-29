# Operator Summary - IBKR Stock/ETF Tiny-Live ADR Eligibility Contract

Date: 2026-06-29
Status: **Future ADR discussion gate done; tiny-live/live still blocked**

PM added a Rust source contract for `tiny_live_adr_eligibility_v1`.

It validates that a future tiny-live ADR discussion candidate contains:

- Phase 5 release packet hash
- scorecard, DQ, and statistical preregistration hashes
- QC/MIT review hashes and pass flags
- complete paper/shadow window
- positive benchmark-relative after-cost lower confidence bound
- enough independent observations
- positive conservative cost-stress result
- paper-vs-shadow divergence inside threshold
- concentration/regime/freshness labels passed
- decision exactly `adr_discussion_only`
- no serialized secret content
- sealed artifact

Safety result:

- default template blocks
- template is secret-free
- positive scorecard alone still blocks if window/reviews/hashes are missing
- `tiny_live_authorized` is rejected
- `live_authorized` is rejected

Verified:

- targeted rustfmt: pass
- tiny-live eligibility acceptance tests: 6 passed

Still blocked:

- no immutable Phase 2 PASS artifact
- no real secret/topology evidence
- no IBKR API call or healthcheck
- no secret creation or secret-content read
- no connector
- no paper order
- no DB migration apply
- no evidence clock
- no GUI lane authority
- no tiny-live/live/margin/short/options/CFD/transfer/account-management/Client Portal path

This contract only defines when a future ADR discussion may be opened. It is not execution approval.
