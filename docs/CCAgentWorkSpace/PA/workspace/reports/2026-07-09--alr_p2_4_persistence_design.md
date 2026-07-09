# PA Design - ALR P2-4 Operational Artifact Persistence

Date: 2026-07-09
Verdict: `FEASIBLE_WITH_V152_GATE`
Mode: `ROLE_FALLBACK_SINGLE_SESSION`

V151 intentionally accepts only scanner-cycle and ingest-event artifact kinds.
P2-4 needs V152 to add ALR-only target, PIT dataset, statistical experiment,
candidate artifact, and defer-evidence kinds; broaden the provenance edge roles
only for source-to-training and internal artifact lineage; and add one
append-only training-run table. The migration must grant `alr_shadow` only
SELECT/INSERT on that table and retain UPDATE/DELETE revocation.

The repository will select only unconsumed ALR source artifacts, persist the
entire artifact bundle and graph atomically, and suppress a repeated run by its
canonical source-set/run hash. Applying V152 or letting the running service
write P2-4 artifacts needs a fresh exact E3/BB gate.
