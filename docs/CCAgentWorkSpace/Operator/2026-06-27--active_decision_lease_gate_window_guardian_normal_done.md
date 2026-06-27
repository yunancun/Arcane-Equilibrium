# Operator Note: Active Lease Gate Window Guardian NORMAL

State: `DONE_WITH_CONCERNS`.

The GUI risk correction is enforced: `10.0%` resolved to `955.1588095 USDT`, not `10 USDT`; max single position `25%` resolved to `2387.89702374 USDT`.

Guardian is now `NORMAL`. The active Decision Lease + Guardian gate passed during a bounded short Demo lease window, and the lease was released. Post-check shows `lease_live_count=0`, so there is no persistent order/probe authority.

Next safe step is still no-order: fresh actual-admission BBO/instrument refresh inside a fresh current-candidate Demo Decision Lease window. No execution or profit proof happened in this round.
