# ALR P2-2 Fresh Persistence Gate

P2-2 source implementation and an isolated PostgreSQL container test are now
approved. The gate does not authorize any exchange call, order, Decision Lease,
Cost Gate change, proof, serving, promotion, scanner read, existing-PG write,
service start, or retention sweep.

Linux is reachable but its clean source checkout is stale. Before any existing
database apply, P2-2 must first complete source verification, push, align
Mac/GitHub/Linux, and pass the exact preapply recheck.
