# S2-WP1 — Production-Effect-Seams Source Debt Closure (S2.2A / S2.3)

Status: `SOURCE_READY` proposal (source-only, `NONE` effect at land time). Session
`P0-S2-PRODUCTION-EFFECT-SEAMS-SOURCE`, WP1. Owner role: E1 (backend, Python pack).

This closes the three items the S2.2A RUN_RECORD explicitly deferred to S2.2B as
"non-blocking, by design": the spawn value-guard pin wiring at the production call
site, the handshake value-check, and a PR-time receipt-freshness check — plus two
identity-coverage defects in the frozen LR1 manifest and the central-validator
registration gap for the S2.3 receipts. Everything here is **additive**: no v1
manifest constant/function, no `source_compatibility_receipt_v1`, and no
`aiml_effect_classifier_digest()` input changes byte.

## 1. Defects closed

- **D1 — S2.3 receipts unreachable from the central gate.** The two SSOT validators
  `validate_sealed_build_receipt` / `validate_expected_identity_receipt`
  (`helper_scripts/maintenance_scripts/agent_governance_sealed_build.py`) existed and
  both schema JSONs were on disk, but `aiml_gate_receipt_validator.SCHEMA_FILES` had
  no key for `sealed_build_receipt_v1` / `expected_identity_receipt_v1`, so
  `validate_aiml_artifact()` rejected them as an unsupported `schema_version`.
- **D2 — LR1 `dependency_lock` binds only the spec text.** The v1
  `dependency_lock_digest` hashes ONLY `requirements-ml.txt`
  (`learning_runtime_manifest.py`), while S2.3 seals BOTH `requirements-ml.txt` and
  `requirements-ml.lock`. The reviewed runtime identity therefore did not bind the
  hash-pinned sealed lock.
- **D3 — feature identity binds names, not COMPUTE.** `_feature_contract_digest()`
  binds feature NAMES + schema version, not `parquet_etl.py`'s compute logic, so an
  ETL-compute change was invisible to `learning_runtime_digest`.
- **D4 — the production spawn never pins a value.**
  `run_event_consumer(..., expected_learning_runtime_digest=None)` fails closed on a
  pin mismatch, but the production launcher passed `None`, so the value-guard was
  inert; there was no PR-time proof that a committed pin still reproduces from the
  checkout.

## 2. Additive v2 mechanism

Because `dependency_lock_digest` feeds `training_contract_digest` →
`manifest_self_digest`, editing it in place would move `learning_runtime_digest` off
the immutable `sha256:6cf76b60…` lineage. So D2/D3 are fixed only under a **new
identity**, never in place:

- `learning_runtime_manifest.py` (v1 left byte-frozen):
  - `SCHEMA_VERSION_V2 = "learning_runtime_manifest_v2"`,
    `RECEIPT_SCHEMA_VERSION_V2 = "source_compatibility_receipt_v2"`.
  - `_dependency_lock_v2()` emits an object
    `{"spec_digest": sha256(requirements-ml.txt), "lock_digest": sha256(requirements-ml.lock)}`.
    It reuses `agent_governance_sealed_build.verify_lock_closure` (fail-closed gate:
    fully-pinned / fully-hashed / closed graph, same ruler as S2.3) and
    `lock_target_platform`; it does not re-parse the lock, so LR1↔LR2 cannot diverge.
  - `LEARNING_CODE_INPUTS_V2 = LEARNING_CODE_INPUTS + ("program_code/ml_training/parquet_etl.py",)`
    folds ETL COMPUTE through `learning_code_digest` (v2 path only).
  - `build_learning_runtime_manifest_v2` / `try_..._v2` /
    `build_source_compatibility_receipt_v2` mirror the v1 builders; the v2 receipt's
    top-level shape equals v1's so the version-agnostic validator recompute covers it.
  - Since `schema_version` is inside `manifest_self_digest`, v2 is a distinct identity
    by construction; v1 stays valid and unchanged.
- New schema `program_code/ml_training/schemas/aiml_gate_receipts/source_compatibility_receipt_v2.schema.json`
  (mirrors v1; embeds the v2 manifest; `dependency_lock` object replaces the scalar).
- Central validator (`aiml_gate_receipt_validator.py`):
  - `SCHEMA_FILES` gains `sealed_build_receipt_v1`, `expected_identity_receipt_v1`,
    `source_compatibility_receipt_v2` (schema lookup only). `PROGRAM_SCHEMA_PATHS`
    unchanged.
  - Two delegation branches validate the S2.3 receipts in **OFFLINE-STRUCTURE** mode:
    they call the SSOT validators without `lock_path` and without a paired sealed
    receipt (structure / integrity / const-false / S1.3·S1.4 ground-truth binding /
    self_digest only). These are **build-identity / source** receipts
    (content-addressed, reproducible, `production_running_attested=false`,
    `observation_owner=S2.5_LR6`) — exactly like `source_compatibility` — so the gate
    passes `now=None` and does **not** apply a wall-clock freshness window: a committed
    receipt carries a fixed 30-minute TTL, and wall-clock-expiring it at the central
    gate would be a time-bomb that rejects committed build evidence for any consumer
    passing wall-clock `now`. The SSOT still checks structural time invariants (ttl
    range, `observed < expires`). The real offline-install / recency proof stays in the
    green `learning-runtime-sealed-build` CI job.
  - A `source_compatibility_receipt_v2` branch reuses the version-agnostic
    `_source_compatibility_receipt_errors` (its `manifest_self_digest` recompute is
    driven by the manifest's own `schema_version`) plus a v2 `dependency_lock`
    object-shape assertion.

## 3. Production spawn value-guard (D4)

`alr_event_consumer.py` (deliberately outside `CAPTURE_INPUTS` /
`LEARNING_CODE_INPUTS`, so editing it does not move any manifest digest):

- `resolve_pinned_learning_runtime_digest()` reads the committed v2 receipt, validates
  it through the central gate, rebuilds the v2 manifest from the checkout
  (HEAD-independent, dummy head → no git dependency), and returns the pinned
  `learning_runtime_digest` only when the rebuild reproduces it; any miss → `None`.
- The launcher contract: env `ALR_EXPECTED_LEARNING_RUNTIME_DIGEST_V2` /
  `--expected-learning-runtime-digest-v2` (the systemd unit S2.4 installs sets it).
  When set, `main()` resolves the pinned digest and, before any DB work, fails closed
  (`FAIL_CLOSED_UNRESOLVED` / `FAIL_CLOSED_PIN_MISMATCH` / `FAIL_CLOSED_ERROR` for an
  unexpected exception, exit 1, `run_event_consumer` never entered) unless the operator
  pin equals the reproduced committed identity (`PASS`). Absent the env var the guard is
  `DISABLED` (backward compatible). The `source_value_guard` sub-object of the
  `alr_event_consumer_result_v2` stdout envelope carries its own
  `schema_version="source_value_guard_v1"`.

Source-truth note (WP4/WP5 consumers): `validate_aiml_artifact` on the S2.3 and v2
source-compat receipts is INTERNAL-CONSISTENCY + STRUCTURE only (offline-structure); a
pass is not proof the receipt matches the real repo. Source-truth binding is (i) the
launcher's recompute-from-checkout (`try_build_learning_runtime_manifest_v2`) + operator
pin, and (ii) the `learning-runtime-sealed-build` CI job's `verify_lock_closure(lock_path=)`
re-derivation. Both the validator delegation branches and the resolver docstring state this.

Scope note: the guard is a **launcher-level** proof deliberately kept orthogonal to
the frozen v1 `_preflight_source_compatibility` / `evaluate_compatibility` path
(those are v1 semantics and must stay byte-frozen). Threading the v2 identity through
the runtime capture/fit comparison belongs to S2.2B (LR1 runtime `DONE` +
`ingestion_compatibility_receipt_v1`), which is `BLOCKED_ON_OPERATOR_EXTERNAL_AUTHORITY`.

## 4. Digest-safety argument

- `aiml_effect_classifier_digest()` hashes ONLY the six S0.3 constants, not
  `SCHEMA_FILES` / `PROGRAM_SCHEMA_PATHS`. Registering schemas is byte-invisible to the
  frozen classifier digest `sha256:1cf8c021…d0ddbc` by construction; a regression test
  pins the exact value after the change.
- v1 `learning_runtime_digest` stays `sha256:6cf76b60…` and v1 receipt self stays
  `sha256:a8fba423…`: no v1 constant/function is touched; a rebuild proves it.
- The new v2 receipt is emitted from THIS checkout and reproduces byte-for-byte.

## 5. Test plan (all `LOCAL_REPRODUCIBLE`)

- `test_aiml_gate_receipt_validator.py`: classifier digest-drift guard; both S2.3
  schema files (+ v2) resolve via `SCHEMA_FILES`; committed S2.3 receipts validate at
  ANY wall-clock / `now=None` / no `now` (no freshness time-bomb); freshly-built S2.3
  receipts validate at wall-clock; const-false forgery (sealed `load_verified_on_target`,
  identity `production_provisioned.uid`) rejected regardless of clock.
- `test_learning_runtime_manifest.py`: v2 distinct identity + v1 byte-frozen;
  `dependency_lock` binds both files; parquet_etl folded into `learning_code_digest`;
  v2 receipt round-trip; v2 fail-closed without a valid lock; committed v2
  HEAD-independent digests match rebuild; committed v2 receipt rebuilds byte-for-byte
  (PR-time freshness); `dependency_lock.lock_digest` forgery rejected.
- `test_alr_event_consumer.py`: resolver reads the committed v2 pin; fail-closed on
  absent receipt / checkout drift; launcher guard `DISABLED` / `PASS` /
  `FAIL_CLOSED_PIN_MISMATCH` / `FAIL_CLOSED_UNRESOLVED` (guard failures never enter
  `run_event_consumer`).
- `test_learning_runtime_manifest_source_static.py`: additive v2 allowlist projection
  pin (v1 pin untouched); v2 files exist; v2 is the v1 superset + `parquet_etl.py`.

## 6. Boundary

Source-only, `NONE` effect. No production PG / runtime / broker / order; no network;
no git effect. `TODO.md`, `PROGRESS.md`, `memory/`, and Rust are untouched;
`PROGRAM_SCHEMA_PATHS` is unchanged.
