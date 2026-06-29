# Operator Summary - IBKR Stock/ETF Scorecard Input Contracts

Date: 2026-06-29
Status: **Scorecard input contracts done; collector/evidence clock still blocked**

PM added Rust source contracts for future stock/ETF scorecard inputs.

They validate:

- IBKR paper/read-only cash ledger evidence
- cost model version hashes and conservative fill penalty
- benchmark version hashes and matched-control rule
- shadow fill reconstruction with `synthetic_shadow=true`
- storage/capacity plan and capacity-breach policy
- combined scorecard input bundle with derived-only scorecard status
- paper/shadow fill separation
- no live fill claim

Safety result:

- default template blocks
- template is secret-free
- live account environment is rejected
- shadow fills cannot link to broker paper fills or live fills
- scorecard cannot be treated as an atomic source of truth
- capacity breach must block evidence clock

Verified:

- targeted rustfmt: pass
- scorecard input acceptance tests: 7 passed

Still blocked:

- no immutable Phase 2 PASS artifact
- no real secret/topology evidence
- no IBKR API call or healthcheck
- no secret creation or secret-content read
- no connector
- no paper order
- no DB migration apply
- no collector
- no scorecard writer
- no evidence clock
- no GUI lane authority
- no tiny-live/live/margin/short/options/CFD/transfer/account-management/Client Portal path

This is source contract work only. It makes future scorecard evidence harder to misread as live proof.
