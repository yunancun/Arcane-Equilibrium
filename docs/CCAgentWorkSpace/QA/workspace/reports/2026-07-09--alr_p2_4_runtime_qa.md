# QA Runtime Acceptance - ALR P2-4

Date: 2026-07-09
Verdict: `PASS_P2_4_OPERATIONAL_SHADOW`

Linux production evidence shows V152 applied, the ALR service active with
`ALR_SOURCE_HEAD=cf2fb7607...`, and one durable research-only challenger run.
The run is explicitly `DEFER_EVIDENCE`; it has no after-cost proof, no model
promotion, no serving readiness, and no profitability claim.

Checks passed: scanner count unchanged (`79744` before/after), 32 source
lineage edges, five derived artifact kinds, zero duplicate source keys, exact
false/zero authority records, and denied shadow UPDATE/DELETE/scanner INSERT.
The engine PID/start time remained unchanged. P2-5 is the next acceptance item;
P2-8 remains blocked on a safe no-order engine notifier activation path.
