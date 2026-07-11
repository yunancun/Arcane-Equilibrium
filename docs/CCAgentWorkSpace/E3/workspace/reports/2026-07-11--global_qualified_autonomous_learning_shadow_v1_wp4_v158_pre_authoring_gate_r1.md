# E3 R1 V158 Pre-authoring Gate — GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 WP4

Date: 2026-07-11
Reviewed source head: `53771890c3ea522f278046752e376dacf5dfafd8`
Reviewed `origin/main`: `53771890c3ea522f278046752e376dacf5dfafd8`
Reviewed request SHA-256: `a033656c126306030b764fee1b073ca394e07c40fdfdfaa3d964b44ad3441d5f`
Verdict: `REJECT_WITH_FINDINGS`
Severity: `P0=0 / P1=2 / P2=1`

E3 verified a clean exact-head review target, exact origin alignment, the
provisional and unreserved status of V158, and continued isolation from
V152/V153/V157 and the legacy model registry. No PostgreSQL, Linux, runtime,
exchange, fit, registry, serving, or promotion action occurred.

## Findings

1. **P1 — direct post-fit DML could fabricate training truth.** The request
   granted `INSERT` on all four proposed tables to `trading_ai` and
   `alr_shadow`. A holder could therefore fabricate `TRAINING_PERFORMED`, model
   artifact, or registry rows without executing the intended real-fit path.
   Repair requires a dedicated non-login writer identity, no application-role
   table DML, and fixed transactional writer functions with exact privilege and
   ownership guards.
2. **P1 — lineage and exact-trio invariants were not relationally complete.**
   The proposed single-column foreign keys allowed a run, receipt, registry,
   and artifact set to disagree on `training_key_hash` or
   `model_artifact_set_hash`; one or two quantile artifacts could also commit.
   Repair requires composite keys and foreign keys plus a deferred,
   commit-time invariant that admits exactly one registry row and exactly the
   distinct `q10`, `q50`, and `q90` artifacts whose canonical set hash matches
   the run and registry.
3. **P2 — PostgreSQL and filesystem bytes are not one atomic transaction.**
   The request described post-fit persistence as atomic without defining the
   cross-boundary failure modes. Repair must scope atomicity to PostgreSQL and
   define staged writes, file and directory `fsync`, no-overwrite atomic rename,
   immutable final-path verification, and deterministic recovery or quarantine
   for pre-rename staging residue and post-rename/pre-commit orphan bytes.

## Disposition

No source-authoring, migration reservation, apply, runtime, fit, registry,
serving, or promotion authority is granted. PM must issue a new request packet
that closes all three findings and obtain a fresh exact-head E3 decision. BB
must not begin until E3 approves that repaired packet.
