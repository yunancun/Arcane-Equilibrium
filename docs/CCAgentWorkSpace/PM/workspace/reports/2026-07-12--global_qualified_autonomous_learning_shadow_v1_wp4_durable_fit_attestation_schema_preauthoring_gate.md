# WP4 Durable Fit-Attestation Schema — Preauthoring Gate

Date: 2026-07-12
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP4-DURABLE-FIT-ATTESTATION-SCHEMA-DESIGN-PREAUTHORING-GATE`
Reviewed source head: `0c90de9c20052afab7f715a055f2df6a9d0d190b`
Status: `DONE_DESIGN_ACCEPTED_DURABLE_FIT_ATTESTATION_SCHEMA_PREAUTHORING_GATE`

## Gate result

The fail-closed forward design is accepted for **source and test authoring
only**. E3 and BB returned `APPROVE_SOURCE_AUTHORING_ONLY`; PA, CC, FA, and MIT
accepted the repaired architecture and final consistency refinements. Final
P0/P1/P2 are `0/0/0`.

The E3-reviewed baseline was `9ba80a470c34a8fab1a362589ec1267f73428796`.
One unrelated IBKR source commit advanced the reviewed head to `0c90de9c2`;
the exact scoped diff was empty. BB's current-head Context artifact is
`sha256:e4c2aa195530adc702c4bf376b27eb0bde7d3c992baf33cf5f3aaac0a8b6ed6d`
with task contract
`sha256:802cf1779a0d675ef56eb1350b65bee3c59ce5fcf4abe9b00943a115d60c05a3`.
The E3 Context artifact was
`sha256:f2e6631ac102d04106eb5818922c69b5a9161a2beac130c463b2e59fe659c9da`.

A fresh current-head source scan found `140` migrations, maximum V158, zero
duplicate versions, and V159 absent. This observation does not reserve V159;
the scan must be repeated immediately before source authoring.

## Frozen forward design

The next forward migration must fail closed unless the complete V158 object,
function, overload, owner, ACL, and trigger posture is exact. It must take
fixed-order `ACCESS EXCLUSIVE` locks on the V158 run, artifact, and registry
tables before proving all three are empty. Partial state, drift, nonzero rows,
or a migration-version collision aborts the migration.

The design adds an immutable `learning.alr_challenger_fit_attestations`
relation with one-to-one lineage over the durable receipt/training key,
structural result and fit-capture identities, structural candidate identity,
runner identity, actual-input material set, ordered q10/q50/q90 artifact set,
issuer and trust-policy identities, external receipt digest, verification
interval, canonical payload, all-false authority, and all-zero counters.

Only `PLATFORM_OR_EXTERNAL_ATTESTED` is eligible. The externally authenticated,
bounded, byte-exact signed receipt envelope is the source of truth; PostgreSQL
must recompute its digest. A JSONB projection is allowed only when exact and
lossless and is never a substitute for the signed bytes. The exact
`ALR_FIT_EXECUTION_ATTESTATION_V1` claim binds literal true values for actual
input consumption, fit execution, model training, artifact readback, and ONNX
semantic validation to the exact subject hashes. Session role and hash checks
provide containment, not proof of platform execution.

The immutable state is derived: a receipt row alone is `ATTESTED_UNBOUND`, and
only one atomic run + q10/q50/q90 + `NOT_SERVING` registry bundle is
`BOUND_COMPLETE`. Database-owned time is captured once for a new binding and
must satisfy `verified_at <= bound_at < expiry`. An expired orphan is unusable.
An exact retry after expiry may only return an already complete immutable
binding without mutation; divergent reuse always conflicts.

The hash DAG remains acyclic: structural result and fit-capture/candidate
identities feed the authenticated receipt digest, then durable attestation,
durable run, and durable challenger identities. The c64 run/challenger hashes
remain explicitly structural. Because durable attestation follows model
readback, artifact paths bind the pre-fit structural run identity; durable
rows carry both structural and attestation-bound identities.

Every V158 v1 writer and reader overload must lose all application-reachable
non-superuser execution grants and become an unconditional hard failure. A
separate membership-free attestor owner/caller may invoke only the fixed
attestation writer; the trainer caller may invoke only the fixed v2 result
writer/reader. No PUBLIC, `alr_shadow`, generic DML/EXECUTE, legacy registry,
or cross-seam privilege is introduced. PostgreSQL superuser bypass is
explicitly outside the application-path claim.

The fixed v2 writer must recompute receipt, durable, lineage, and ordered
artifact-set identities inside PostgreSQL and generate no-authority/counter
payloads internally. Tests must cover exact forward/replay posture, every v1
overload, role membership and ACLs, direct DML denial, signed byte/digest
parity, issuer/policy/claim/hash failures, expiry boundaries, structural versus
durable identities, path binding, deferred completeness, atomicity, exact and
divergent concurrency/replay, complete v2 readback, and false/zero authority.

## Deliberate no-effect boundary

This gate did not reserve, author, or apply V159. It did not contact
PostgreSQL, Linux, runtime services, or Bybit; run a trainer or fit; create or
read model/ONNX/filesystem artifacts; write a durable row or registry; create
a symlink; serve/promote a model; touch Guardian, Decision Lease, risk, or Cost
Gate; or grant trading/live authority. V158 remains unapplied. G3 and G4 remain
failed.

## Next safe action

Advance to `WP4-DURABLE-FIT-ATTESTATION-SCHEMA-SOURCE-TDD`. Re-run the exact
migration collision scan at the then-current head, then author only the
forward migration and isolated/static tests under the frozen design. Migration
application, any PostgreSQL/runtime contact, and any real fit remain separate
future gates.
