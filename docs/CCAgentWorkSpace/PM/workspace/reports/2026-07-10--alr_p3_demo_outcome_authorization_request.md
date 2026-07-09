# PM P3 Request - Bounded Demo Outcome Authorization

Date: 2026-07-10
State: `WAIT_OPERATOR_DEMO_AUTH`
Authority chain required: PM -> E3 -> BB -> PM -> Operator

P2 is complete but supplies research challengers only: all current runs are
`DEFER_EVIDENCE`, with no proof packet, reward record, or trading authority.
Scanner ranking and ALR candidates cannot be promoted into a trade instruction.
Accordingly, this file is an authorization request, not an order plan or an
approval to contact a venue.

The historical P0 reference is `ma_crossover|NEARUSDT|Buy`; it is expired and
must be replaced by a fresh, source-head-bound candidate before E3 review. The
future exact packet must provide all of the following atomically: a current
candidate and side; Demo-only instrument/order type/price/quantity/notional;
one bounded time window; fresh GUI/Rust RiskConfig and loss-control envelope;
active Decision Lease; fresh instrument/BBO and exchange-mode checks; Guardian
and Rust authority; cancellation/rollback and audit/reconstruction rules; and
explicit E3, BB, PM, and Operator approvals. Any mismatch rotates the request.

No candidate, side, order shape, lease, loss cap, runtime authorization, or
exchange contact is granted here. The post-P2 external engine PID drift also
requires a fresh runtime preflight before this request can advance.
