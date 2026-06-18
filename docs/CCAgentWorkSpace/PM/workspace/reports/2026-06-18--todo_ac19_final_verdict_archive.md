# TODO v187 AC19 final-verdict active-row archive

Date: 2026-06-18
Owner: PM-local TODO lifecycle pass
TODO row: `P2-AC19-ALT-BUCKET-FINAL-VERDICT`

## Decision

`P2-AC19-ALT-BUCKET-FINAL-VERDICT` no longer belongs in TODO §5 active
engineering queue. Its evidence/verdict acceptance work is complete; the
remaining question is a future PA/QC/operator policy choice.

## Evidence Checked

- QA final verdict:
  `docs/CCAgentWorkSpace/QA/workspace/reports/2026-06-10--ac19_alt_bucket_14d_final_verdict.md`
  - alt bucket FAIL: 42 attempts, 10 fills, 28 timeout->taker, fill 23.8%,
    Wilson lower 13.5%.
  - large_cap = INCONCLUSIVE-LOW-N, not "large_cap is broken".
  - suggested α/β/C follow-up is PA/QC/operator scope, not QA execution.
- BB demo-vs-mainnet audit:
  `docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-10--demo_vs_mainnet_depth_matching_audit.md`
  - demo public market data mirrors mainnet.
  - demo maker fills are pessimistic because demo orders have no real queue
    position.
  - β premise must be rewritten; α-light timeout reduction has the lowest
    transfer risk; C can treat 23.8% as a conservative lower bound.
- Expired AC19 cron cleanup already closed in v165.

## TODO Change

- Removed `P2-AC19-ALT-BUCKET-FINAL-VERDICT` from TODO §5.
- Added §7 conditional follow-up:
  `P2-AC19-ALT-BUCKET-FINAL-VERDICT-FOLLOWUP`.
- Updated the expired-triage note to stop pointing at a §5 row.
- Bumped TODO to v187 and recorded changelog/memory.

## Boundary

- No strategy decision was made.
- No code, deploy, rebuild, restart, DB, auth, risk, order, or trading mutation.
- If PA/QC/operator chooses α/β/C later, open a new implementation/review row
  with the normal PA/QC/FA/BB -> E1/E2/E4/QA chain.
