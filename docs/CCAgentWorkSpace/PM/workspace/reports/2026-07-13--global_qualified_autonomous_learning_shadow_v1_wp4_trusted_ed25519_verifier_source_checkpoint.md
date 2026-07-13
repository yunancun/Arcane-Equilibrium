# WP4 Trusted Ed25519 Verifier — Source Checkpoint

Date: 2026-07-13
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP4-TRUSTED-ED25519-VERIFIER-SOURCE-TDD-GATE`
Source checkpoint: `0b9038c78a9e1a5256895901aa22376d645adbd4`
Source base: `a393159a327b624112e3b76b1f644b9d2f8cf6de`
Branch: `agent/alr-wp4-contracts`
Status: `DONE_SOURCE_ACCEPTED_TRUSTED_ED25519_VERIFIER`

## Accepted source effect

The exact nine-path source slice accepted by the v806 preauthoring gate is now
implemented. It adds one isolated, private, library-only
`openclaw_alr_fit_verifier` crate, its exact locked dependencies, a structured
non-regex Rust source lexer/parser guard, and dedicated hosted CI coverage. No
existing engine, core, types, Python runtime, SQL, migration, service, trainer,
model, registry, broker, order, risk, or authority path consumes the crate.

The crate constructs the frozen request, signed-status, outer-terminal, and
V159-inner Ed25519 preimages internally and uses only
`VerifyingKey::from_bytes`, `Signature::from_bytes`, and
`VerifyingKey::verify_strict`. The four closed phases remain
`REQUEST_ONLY`, `SIGNED_STATUS`, `TERMINAL_SUCCESS`, and
`TERMINAL_NO_INNER`; missing, extra, duplicate, reordered, or wrong-role jobs
fail before crypto.

Its maximum success verdict remains
`STRICT_SIGNATURES_VALID_INPUT_BINDINGS_CAPABILITY_UNATTESTED` with
`capability_authenticity=SOURCE_ONLY_UNATTESTED`. Source compilation and hosted
CI do not establish semantic phase, canonical envelope/payload parity,
policy/revocation adjudication, trusted time, production platform attestation,
coordinator eligibility, durable consumption, persistence, fit, training, or
model execution. All 17 authority fields remain false, all 17 authority
counters remain zero, and `model_training_performed_claim` remains
`NOT_ESTABLISHED`.

## Exact source generation

The source commit changed only the accepted nine paths. Frozen SHA-256 values:

- `.github/workflows/ci.yml`:
  `cd6ec5e87df6c9a09898122d5d56e40318e8a594d6fa878de0fd5addc7c1bfcb`;
- `rust/Cargo.toml`:
  `a0336d0623ee65d9aed77d6e81d91062a9dd8a619985f71a618ef8f318de8f09`;
- `rust/Cargo.lock`:
  `27ed7364041fc17c14e0b27f19d54f247a61c12b78a567d2abcc0b11038b27f8`;
- `rust/openclaw_alr_fit_verifier/Cargo.toml`:
  `24ebf0b61ec5559ed0c0ad9cebbf39c53c4dfea73e48f42be01623c6a5797754`;
- `rust/openclaw_alr_fit_verifier/src/lib.rs`:
  `e547de860b89c9a750fc6d0b6eadcac9431f1d6b6898e610abafcc93ac5467b1`;
- `rust/openclaw_alr_fit_verifier/src/contract.rs`:
  `b0abc1a08835cbeee730e753349145bb722262136c8538d39d80c2f82c7f5e69`;
- `rust/openclaw_alr_fit_verifier/src/verifier.rs`:
  `d390a31ce316c0ae053735dc31ffaf48fe38a25fda7b4042b0a1b31aae31c766`;
- `rust/openclaw_alr_fit_verifier/tests/strict_verifier_contract.rs`:
  `c19bdfe4f476fb5abd9196a26d713f4dcfac4fed5ae2c8623224d434cc02f675`;
- `tests/structure/test_alr_fit_verifier_source_static.py`:
  `baa134fec15ce19fa2d3797b9c52223d108f31fc032d1e450239ed8a22fd9eab`.

The normal dependency pins remain default-feature-disabled `base64 0.22.1`,
`ed25519-dalek 2.2.0`, and `sha2 0.10.9`; `serde_json 1.0.149` remains dev-only.
The one-time public crates.io dependency fetch and hosted public dependency
fetch are disclosed network effects. No private or authenticated external
surface was contacted.

## TDD, offline, and supply-chain verification

The accepted source went through RED-to-GREEN contract and mutation testing.
Final local evidence at the exact source bytes is:

- Rust unit tests: `5 passed`;
- Rust integration tests: `28 passed`;
- structured scanner without metadata: `10 passed`;
- structured scanner with locked offline metadata: `10 passed`;
- locked offline cargo test from the isolated target: PASS;
- `cargo check` with `-Dwarnings`: PASS;
- direct stable `rustfmt --check`: PASS;
- direct scanner CLI, `py_compile`, and `git diff --check`: PASS.

The scanner parses bounded Rust tokens, scopes, use trees, macro declarations
and metavariable paths, `cfg` binding, hoisted block imports, physical module
paths, and output-macro aliases without accumulating regex patches. It also
parses Cargo metadata and lock data to enforce dependency kinds, features,
sources, checksums, reverse reachability, target layout, and the dedicated
online/offline CI contract. The final exact repair closes renamed/grouped/raw/
visible/re-exported root-`std` output macro aliases while preserving non-root
controls.

Hosted CI run `29213814965` (#1101) completed successfully with `8/8` jobs
SUCCESS. This includes the isolated verifier's locked online test, clean
distinct-target offline replay, metadata/lock assertions, focused scanner
pytest, Linux Rust check, and PR-only macOS verifier test. Hosted CI attests
that CI execution; it does not attest a production verifier binary, trusted
runtime identity, issuer, runner, fit, or model.

## Independent reviews

Final source/security/regression reviews all accept the exact final scanner and
source generation with P0/P1/P2=`0/0/0`:

- E2 final verdict SHA-256:
  `7a85dba8272edcfda274f8af62da8012e50c18c293eb8934d35288e4872f7e36`;
- E3 final verdict SHA-256:
  `fa4992d24fee595a57c705d92033c0632a33aef2af1c775de563f3c48804caca`;
- E4 final verdict SHA-256:
  `ee3b1cfaf640bb3f514a4fc0c1e603bfddbbe816657fe792444d272c5895bcb3`.

The isolated governance adapters lacked pytest in some controlled Python
environments. Those attempts were recorded honestly as tooling failures, not
test PASS. The final semantic verdicts reuse and independently inspect the
exact-generation green E1 evidence, both 10/10 directly executed suites,
compiler probes, direct CLI, and diff checks. No failed capture is relabelled
as successful execution.

FA, CC, and MIT source-boundary reviews remain accepted because the Rust source
and integration contracts did not change after their final reviews. MIT's
classification remains source-ready only: runtime, training, serving,
promotion, and profit are `NOT_ESTABLISHED`.

## Deliberate unexecuted boundary

The new crate is a source-only unattested verifier. No trusted platform wrapper
or same-process `verify_and_attest(original_inputs)` host exists. No real
issuer/runner request, status, terminal, or inner V159 bytes were created,
verified, consumed, or persisted. No V160 migration was reserved, authored, or
applied. Production/runtime V159 remains unapplied and unrefreshed.

No PostgreSQL or Linux runtime was contacted by this source checkpoint. No
trainer or fit ran; `model_training_performed=false`; no model artifact,
registry row, serving state, promotion, broker/order, risk/Guardian/Lease/Cost
Gate, or authority effect occurred. Production proof/reward/model row counts
remain exactly `0/0/0`. Source and test PASS do not establish training.

## G1-G9 adjudication

- G1 remains `PARTIAL`.
- G2 remains `PARTIAL_DISPOSABLE_PG_VERIFIED`.
- G3 remains `FAIL_DISPOSABLE_PG_VERIFIED_NO_REAL_RECEIPT_OR_OUTCOME_CHAIN`.
- G4 remains `FAIL_DISPOSABLE_PG_VERIFIED_EXECUTION_NOT_ESTABLISHED`.
- G5, G6, and G7 remain `FAIL`.
- G8 and G9 remain `PARTIAL_WP1_PASS`.

The Goal and WP4 remain `ACTIVE`; terminal eligibility remains false.

## Next safe action

Advance directly, without another design-only gate, to
`WP4-V160-STYLE-ATOMIC-CONSUMPTION-SOURCE-TDD-GATE`, state
`ACTIVE_WP4_V160_STYLE_ATOMIC_CONSUMPTION_SOURCE_TDD_GATE`. Reuse the accepted
v805 atomic-consumption design, perform the required fresh migration collision
and effect authorization, then author only the fixed guarded V160 coordinator
and its functional/concurrency/ACL/deletion tests.

This checkpoint itself does not authorize or claim V160 apply, production PG,
trusted issuer/runner activation, real fit, model/registry creation, serving,
promotion, broker/order/risk changes, Cost Gate changes, or authority. With zero
qualified candidates, the runtime may only collect evidence or ROTATE; it must
not force a fit.
