# QA Acceptance - ALR P2-2 Persistence

Date: 2026-07-09
Verdict: PASS_TO_PREAPPLY_ALIGNMENT
Scope: P2-2 persistence acceptance only, not the P2 operational terminal state.

| Chain stage | Evidence | Status |
|---|---|---|
| Scanner source boundary | Repository query is bounded, read-only, and selects only scanner identities absent from the ALR ledger. | PASS |
| Append-only persistence | V151 creates five `learning.alr_*` tables; public and `trading_ai` UPDATE/DELETE are revoked. | PASS |
| Idempotency and conflict | Real PostgreSQL run proved persisted/duplicate/restart/conflict behavior; E2 closed concurrent insert handling. | PASS |
| Provenance and recovery | Source artifact -> ingest artifact edge plus immutable watermark events reconstruct processed keys/cursor. | PASS |
| Isolated migration | Linux disposable PostgreSQL V151 double-apply and privilege probe passed; containers/tunnels removed. | PASS |
| Existing PG apply and scanner consumption | Not yet performed; Linux source is stale until post-commit alignment. | WAITING_PREAPPLY |
| Service/training/outcome/retention/health/soak | P2-3 through P2-8 remain unimplemented. | WAITING |

E4 passed the focused plus adjacent ALR suite twice at `160 passed`. No exchange,
official MCP, credential, order/probe, Decision Lease, Cost Gate, serving,
promotion, `_latest`, or profit/proof action occurred. Existing-PG migration
apply is fail-closed until the reviewed source commit is pushed, Linux is
fast-forwarded source-only, and all three heads/cleanliness are rechecked.

QA role memory is pre-existing dirty and was not edited.
