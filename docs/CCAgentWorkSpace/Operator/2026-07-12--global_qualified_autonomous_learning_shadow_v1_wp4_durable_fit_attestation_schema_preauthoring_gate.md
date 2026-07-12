# Operator Mirror — WP4 Durable Fit-Attestation Schema Preauthoring Gate

Status:
`DONE_DESIGN_ACCEPTED_DURABLE_FIT_ATTESTATION_SCHEMA_PREAUTHORING_GATE` at
reviewed head `0c90de9c20052afab7f715a055f2df6a9d0d190b`.

E3 and BB approved later **source/test authoring only**; PA, CC, FA, and MIT
accepted the repaired design. Final P0/P1/P2 are `0/0/0`. A fresh scan found
140 migrations through V158, zero duplicate versions, and V159 absent. V159 is
not reserved and must be rescanned immediately before authoring.

The accepted design makes byte-exact authenticated signed receipt bytes the
source of truth, admits only `PLATFORM_OR_EXTERNAL_ATTESTED`, and derives a
one-to-one immutable attestation/run/q10-q50-q90/`NOT_SERVING` bundle. It keeps
structural artifact paths separate from later durable identities, uses
database-owned bind time and strict expiry/replay semantics, recomputes all
durable hashes inside PostgreSQL, hard-disables every V158 v1 reader/writer
overload for application roles, and preserves false/zero authority.

This is not execution proof. It did not author/apply a migration, contact PG,
Linux, runtime, or Bybit, run fit/training, create model files or rows, mutate a
registry, serve/promote a model, or grant trading/live authority. V158 remains
unapplied; G3/G4 remain failed.

The Goal remains active. Next is
`WP4-DURABLE-FIT-ATTESTATION-SCHEMA-SOURCE-TDD`: repeat the collision scan, then
author only the forward migration and source tests. Migration apply, runtime
contact, and any real fit require separate future gates.
