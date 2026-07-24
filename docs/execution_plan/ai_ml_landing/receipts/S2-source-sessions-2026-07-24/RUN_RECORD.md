# AIML Sprint-2 — Source-Session Run Record

**Date**: 2026-07-24
**Program**: `AIML-LONG-LIVED-LANDING-V2`
**Scope**: Advance Sprint-2 from `S1_CLOSED` as far as source/`NONE`-effect work
allows; stop at the operator/external-authority wall for the effect sessions.
**Terminal**: S2.2A + S2.3 `SOURCE_READY` (merged); **S2 is NOT `S2_CLOSED`**.

## W0 baseline (verified)
- Task checkpoint `2a471f37…` was already superseded by legitimate concurrent
  forward progress. True `origin/main` at start = `2a471f37` → advanced under a
  concurrent "workflow-maintenance / TODO-selfcheck" session; verified clean
  forward-only ancestry (no history rewrite). Work baselined off the then-current
  true `origin/main` in isolated linked worktrees.
- Three source sides (Mac / GitHub `origin/main` / Linux `trade-core`) were in
  sync at `2a471f37` at intake; the primary Mac checkout carried unrelated
  concurrent-session dirty `memory/` files that were preserved untouched.
- Runtime engine **DOWN** (four-head probe `INDETERMINATE`:
  `engine_process_not_found`, `engine_build_sha_unavailable`) — the real S2
  runtime gap, not a source-sync issue.
- Preserve branch `local/preserve-reference-pr-merge-gates-20260724` @ `58c5e65df`
  left untouched.
- An independent CC constitutional verdict confirmed the authority wall before
  any work (see "Blocker determination").

## Sessions delivered

### S2.2A / LR1 — Scoped Compatibility Identity — `SOURCE_READY`
- **Effect**: `NONE` (source-only). Replaces whole-repo-HEAD liveness with a
  positive `learning_runtime_digest` over learning code + V151–V160 fingerprints
  + feature/label/action-policy contracts + dependency spec + runtime config,
  bound at preflight/spawn/finalize. Docs-only HEAD advance no longer stops
  ingestion; an incompatible training contract quarantines fit while compatible
  Scanner capture continues. Fills the previously-uncomputed `learning_runtime_digest`
  field in the S1.2 WORM sink.
- **Branch** `agent/aiml-s2-2a-lr1-compat`; **reviewed head** `7054a3b075171d9374fea935802d99740c0ef5da`;
  **PR #121 merge** `87a3a2503f7ef6e47cffdac3db80bbd3b1b1762b`.
- **Receipt** `receipts/S2.2A-source-compatibility-receipt-v1.json` — `status
  SOURCE_READY`, self `sha256:a8fba423…`, `learning_runtime_digest
  sha256:6cf76b60a763035d26d0d4e9e0e6aa0aa8877d99966367c778420e5f63a79595`,
  10 V151–V160 fingerprints; reproduces byte-for-byte from the checkout.
- **Review**: PA design → E1 build → E2 (adversarial) + E3 (security) → E1 fix
  round → E2 recheck **PASS** + E3 delta **PASS** + E4 **PASS_WITH_CONCERNS**.
  E2's P1 (receipt built at base before allowlisted-file edits → stale digest,
  would false-quarantine fit in S2.2B) was independently PM-reproduced and fixed
  (regenerate at final head + non-tmp_path drift-guard test). Three P2 closed
  (validator inner-digest anti-forgery; single authoritative `evaluate_compatibility`
  replacing a divergent scalar path; firing negatives for all three bind edges).
- **Evidence** `LOCAL_REPRODUCIBLE`: 415 passed / 1 skipped core set; full
  `program_code/ml_training/tests` tree 2259 / 36. Narrow-Python → no specialized
  CI gate (protocol §5); PR ran the unconditional cheap gates + CodeQL, all green.
- **Deferred to S2.2B** (non-blocking, by design): the spawn value-guard pin
  wiring at the production call site; the handshake value-check (value drift is
  caught at finalize); a PR-time receipt-freshness check (drift test exists +
  passes locally but S2.2A's narrow-Python CI runs no ml_training tests).

### S2.3 / LR2 — Immutable Runtime And Least Privilege — `SOURCE_READY`
- **Effect**: `NONE` (source + build-verification). Seals the S1.6-selected
  `content_addressed_fixed_path` runtime (NOT OCI) from a real hash-pinned
  `requirements-ml.lock` and binds it to the S1.3 identity matrix. Emits
  `sealed_build_receipt_v1` + `expected_identity_receipt_v1`; explicitly NOT a
  production install (S2.4) and NOT a running attestation (S2.5/LR6).
- **Branch** `agent/aiml-s2-3-lr2-sealed`; **reviewed head** `73b083e9b76b6f0a6c7971cc9f06d1c8c0651f66`;
  **PR #122 merge** `051df8262da85123213bd0937ad03c206152f5a3`.
- **Receipts**: `receipts/S2.3-sealed-build-receipt-v1.json` (self
  `sha256:169d2e6c…`, runtime_content `sha256:8b2092e8…`, closure
  `sha256:26307134…`, target `x86_64-unknown-linux-gnu`) and
  `receipts/S2.3-expected-identity-receipt-v1.json` (self `sha256:a08c6965…`).
  `requirements-ml.lock` = 38 pinned / 0 unpinned / hashed. All
  `production_*`/`running_attested.*`/`load_verified_on_target` const false;
  `observation_owner` const `S2.5_LR6`; nine authorities false. Both reproduce
  from the checkout and are drift-guarded + CI-caught (`sealed_build` classifier
  fires the offline drift test on receipt/module/schema edits).
- **Review**: PA design → E1 build → **five reviewers** E2/E3/E4/CC/OPS
  (CC CLEAN; others PASS_WITH_CONCERNS, no P0/P1) → consolidated fix round
  (committed-receipt authentication against the real lock; offline lineage
  binding of the S1.3/S1.4-B ground-truth digests; `--only-binary=:all:` CI
  hardening — which surfaced + fixed a real YAML parse bug; CI-wiring + const
  negatives) → E2 recheck **PASS** (both demonstrated forgeries closed) →
  2 Codex P2 (pin `target_platform` to the Linux lock; verify the S1.6
  schema-level digest offline) fixed + threads resolved → FA/CC final
  cross-cutting audit **CLEAN**.
- **Evidence**: local `LOCAL_REPRODUCIBLE` (112 required / 248 regression, zero
  regression). Full CI green including the heavy `learning-runtime-sealed-build`
  job — the real fetch-once/clean-offline `--require-hashes` install +
  `python3 -I` import of lightgbm/scikit-learn/onnx/onnxruntime on the Linux
  target (no pip↔uv resolver drift).
- `aiml_gate_receipt_validator.py` was **not** touched in-session — S2.3
  self-validates; central-validator registration is a serialized follow-up.

## Blocker determination (operator/external authority)
Independently CC-verified (initial verdict + final cross-cutting audit) as the
honest, correct terminal — no advanceable NONE/source work was skipped:
- **S2.0** `PG_OBSERVER_BOOTSTRAP` — a production PG observer role/auth/ACL is one
  minimal typed **external-admin** effect requiring operator-held DB-superuser-class
  authority; the governance Adapter is fail-closed; a development agent cannot
  self-authorize it. **Unblock root.**
- **S2.1** `QUIESCE_FENCE` — depends on S2.0; runtime quiesce/recover effect.
- **S2.4** `CREDENTIAL_PG_UNIT_INSTALL` — credential/PG-role/unit/install effects
  + an intermediate exact-head three-side source checkpoint; fresh operator
  authority + signing.
- **S2.5** `WATCHDOG_ROLLBACK_TEST` — running-runtime attestation; requires the
  live runtime brought up by S2.4 (engine currently DOWN).
- **S2.2B** `REMOTE_READONLY` — the only row that issues the LR1 runtime `DONE`
  + `ingestion_compatibility_receipt_v1`; depends on S2.5.
S1's SSHSIG / disposable apply-permit / historical runtime evidence are expired,
domain-separated and intent-pinned and **cannot** be reused as S2 effect
authority; the nine AIML authorities remain false. `S2_CLOSED` requires real
platform-attested running runtime (S2.5) + `ingestion_compatibility_receipt_v1`
(S2.2B), both gated on the blocked effect sessions — hence **unreachable this
session**.

## Sync posture
- Mac + GitHub `origin/main` advanced through PR #121 (`87a3a2503`) and PR #122
  (`051df8262`) via exact-head `--match-head-commit` merges (no force, no admin
  bypass).
- The Mac primary checkout ("Mac main") is a shared, concurrently-dirty worktree;
  it was **not** force-ff'd — it catches up naturally.
- Linux `trade-core` intentionally left behind: per delivery-protocol §7,
  intermediate three-side sync is only at S2.4 (blocked), and the single final
  global sync is S8.4. This is prescribed, not drift.

## Accepted coverage debt / follow-ups (closure_quality)
- S2.3 central-validator registration (register `sealed_build_receipt_v1` +
  `expected_identity_receipt_v1` into `aiml_gate_receipt_validator.py`) —
  serialized follow-up (audit-blessed as deferred; S2.3 self-validates like
  S1.3/S1.4).
- S2.2A `feature_contract_digest` binds the feature name-set + schema version,
  not `parquet_etl` compute logic (a disclosed false-compatible hole mitigated by
  the schema-version-bump convention + a frozen source-static-tested allowlist);
  re-point its deferral to a real owner (an LR1 follow-up or S3.2/LR4 Scanner),
  not "LR2/S2.3".
- S2.2A `dependency_lock_digest` hashes the spec text (`requirements-ml.txt`),
  not the sealed lock; consider renaming to `dependency_spec_digest` when S2.4
  rebinds the real `requirements-ml.lock`.
- Add a PR-time source-compatibility receipt-freshness check before S2.2B
  activates the preflight.
