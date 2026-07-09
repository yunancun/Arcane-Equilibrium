# E3 Review - ALR P2-4 Shadow Apply R2

Date: 2026-07-09
Verdict: `APPROVE_EXACT_SCOPE_R2`

E3 approves the R2 request only at
`cf2fb7607b5bacf35bc2a50f168453f10dfbada9`. The apply must stop unless Linux
fast-forwards cleanly to that head before V152. The migration remains one
`ON_ERROR_STOP` transaction; the role contract remains scanner SELECT plus ALR
SELECT/INSERT only; the replacement unit must carry exactly that source head.

Only `openclaw-alr-shadow.service` may be daemon-reloaded/restarted. The engine,
scanner, orders/probes, Decision Lease, Cost Gate, external APIs, serving,
promotion, proof, `_latest`, and deletion remain prohibited. The postcheck must
show zero authority counters and unchanged scanner source count.
