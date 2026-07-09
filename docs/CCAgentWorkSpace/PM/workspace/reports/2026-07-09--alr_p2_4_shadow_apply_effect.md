# PM Apply Effect - ALR P2-4 Operational Shadow

Date: 2026-07-09
State: `P2_4_OPERATIONAL_SHADOW_COMPLETE_P2_5_ACTIVE`
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

R1 disposable PostgreSQL exposed a timestamp-contract defect before any
production write. Commit `cf2fb7607` corrected it; R2 passed `218` adjacent
tests and the disposable container produced one real P2-4 run. Fresh R2 gate
then applied V152 and the reviewed role contract at the aligned Linux source
head `cf2fb7607b5bacf35bc2a50f168453f10dfbada9`.

Only `openclaw-alr-shadow.service` restarted. It is active with a literal
`ALR_SOURCE_HEAD` pin, and appended one `scanner_novelty_statistical_baseline`
run: status `DEFER_EVIDENCE`, source count `32`, five derived artifacts, and
32 source-to-target plus four downstream lineage edges. Scanner count remained
`79744`; source-key duplicates are `0`; all stored authority maps/counters are
exactly false/zero. `alr_shadow` has no UPDATE, DELETE, or scanner INSERT.

The existing engine remained PID `1561777` with its original start time. No
engine change, scanner mutation, Bybit/MCP call, order/probe, Decision Lease,
Cost Gate, proof, serving, promotion, `_latest`, or deletion occurred.

P2-5 is active: consume existing ProofPacket/RewardLedger only as outcome
feedback, record granular evidence gaps, and rotate beyond a deferred target.
