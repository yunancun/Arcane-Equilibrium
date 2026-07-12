# WP4 Trusted Ed25519 Verifier — Source Preauthoring Gate

Date: 2026-07-12
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP4-TRUSTED-ED25519-VERIFIER-SOURCE-PREAUTHORING-GATE`
Reviewed source head: `75f3db2b55cd1d9737d83c811d291abecb67ad49`
Status: `DONE_DESIGN_ACCEPTED_TRUSTED_ED25519_VERIFIER_SOURCE_PREAUTHORING_GATE`

## Gate result

The repaired source/test seam is accepted. The next separately governed TDD
gate may author one isolated Rust verification-only crate, its exact locked
dependencies, one static source guard, and dedicated CI coverage. No source was
authored in this gate.

Acceptance is deliberately narrower than production readiness. The source
receipt can prove only strict Ed25519 verification over caller-supplied bounded
signed-material bytes and bind separate envelope/evidence identities. It cannot
parse envelope JSON, establish envelope-to-payload parity, attest policy or
time, consume a request, write PostgreSQL, run fit, establish model training,
or make a coordinator command eligible.

Goal and WP4 remain `ACTIVE`. G1/G2 remain partial; G3/G4 and G5-G7 remain
failed; G8/G9 remain partial. Production/runtime V159 remains unapplied and
unrefreshed. V160 remains absent and unreserved.

## Frozen isolated crate

The only accepted placement is the new workspace library
`rust/openclaw_alr_fit_verifier`. It has no dependency on
`openclaw_types`, `openclaw_core`, `openclaw_engine`, `tokio`, `sqlx`,
`reqwest`, `chrono`, filesystem, environment, process, socket, or database
code. No existing crate may depend on it in this slice. This keeps the new
crypto dependency out of the live-engine graph.

The package is private, library-only, and freezes
`build=false`, `autobins=false`, `autoexamples=false`, `autobenches=false`,
and `autotests=false`, with one explicit library and one explicit test target.
First-party source begins with `#![forbid(unsafe_code)]` and
`#![deny(missing_debug_implementations)]`.

Only these exact normal dependencies are allowed:

- `base64 = =0.22.1`, default features disabled;
- `ed25519-dalek = =2.2.0`, default features disabled; and
- `sha2 = =0.10.9`, default features disabled.

`serde_json = =1.0.149` is dev-only for an independent fixed-schema receipt
oracle. Production source may call only `VerifyingKey::from_bytes`,
`Signature::from_bytes`, and `VerifyingKey::verify_strict`. Signing, private
keys, key generation, ordinary `Verifier::verify`, prehash/digest, batch,
hazmat, legacy compatibility, PKCS8, PEM, and rand surfaces are forbidden.

The first-party no-build-script/no-unsafe rule is not misrepresented as a
whole-transitive-closure property. The later lock review must separately
inventory the expected `curve25519-dalek` build script, targets, features,
checksums, licenses, unsafe implementation, and advisories.

## Exact later source slice

The next source gate is limited to nine paths:

1. `rust/Cargo.toml`;
2. `rust/Cargo.lock`;
3. `rust/openclaw_alr_fit_verifier/Cargo.toml`;
4. `rust/openclaw_alr_fit_verifier/src/lib.rs`;
5. `rust/openclaw_alr_fit_verifier/src/contract.rs`;
6. `rust/openclaw_alr_fit_verifier/src/verifier.rs`;
7. `rust/openclaw_alr_fit_verifier/tests/strict_verifier_contract.rs`;
8. `tests/structure/test_alr_fit_verifier_source_static.py`; and
9. `.github/workflows/ci.yml`.

The core/engine/types crates, Python handshake behavior, SQL, V160,
migrations, runtime configuration, services, trainer, model, registry,
serving, broker, order, risk, Guardian, Lease, and Cost Gate remain out of
scope.

## Public Interface and phase ownership

One deep Interface accepts one declared phase, one bounded key binding, one
bounded evidence binding, and one exact ordered borrowed job slice:

```rust
pub fn verify_unattested_phase_v1(
    input: PhaseVerificationInputV1<'_>,
) -> Result<UnattestedVerificationOutputV1, VerificationErrorCodeV1>;
```

No public constructor accepts a verified Boolean, caller preimage, attestation,
verdict, authority map, receipt digest, persistence/training switch, or forged
verified state. Issuer/key/policy IDs, generation/epoch, usage, public key,
provider digest, adjudication claim, raw policy/overlay bytes, envelope bytes,
signed-material bytes, and signatures have exact shapes and bounds.

The verifier constructs each preimage internally as frozen domain, NUL,
unsigned 64-bit big-endian signed-material length, then exact signed-material
bytes. The phase matrix is closed and ordered:

- `REQUEST_ONLY`: request;
- `SIGNED_STATUS`: request, signed status;
- `TERMINAL_SUCCESS`: request, outer terminal, V159 inner; and
- `TERMINAL_NO_INNER`: request, outer terminal.

Missing, extra, duplicate, reordered, or wrong-role jobs fail before crypto.
Status and terminal intentionally share
`ALR_ISOLATED_FIT_TERMINAL_RECEIPT_V1`; therefore a successful signature can
never prove semantic phase by itself.

## Cryptographic and receipt ceiling

The only source success verdict is
`STRICT_SIGNATURES_VALID_INPUT_BINDINGS_CAPABILITY_UNATTESTED`, with
`capability_authenticity=SOURCE_ONLY_UNATTESTED`. It makes no local
reproducibility, provenance, governance-assurance, platform-attestation,
semantic, persistence, training, fit, or coordinator claim.

Every success receipt fixes, among other closed fields:

- `platform_attested=false`;
- `semantic_phase_established=false`;
- `canonical_input_bytes_established=false`;
- `envelope_payload_binding_established=false`;
- `policy_overlay_adjudication_established=false`;
- `trusted_time_established=false`;
- `coordinator_eligible=false`;
- `durable_consumption_established=false`;
- `persistence_allowed=false`;
- `training_allowed=false`; and
- `model_training_performed_claim=NOT_ESTABLISHED`.

The exact `alr_fit_ed25519_verification_receipt_v1` top-level, evidence, job,
`no_authority`, and `authority_counters` schemas are lexicographically frozen.
All 17 authority fields are literal false and all 17 counters are literal zero,
including Guardian, RiskConfig, live/mainnet, protected-evidence deletion,
direct-parameter, and latest-pointer families.

Receipt bytes are compact safe-ASCII UTF-8 with no BOM, whitespace, trailing
newline, escapes, floats, nulls, maps, extensions, unknown/omitted/duplicate
keys, or caller-selected schema. Booleans and unsigned decimal integers have
one exact grammar. Receipt output is capped at 32,768 bytes and SHA-256 is
computed internally.

The primitive is named accurately as
`ed25519_dalek_2.2.0_verify_strict_zip215`: the source does not claim RFC/NIST
public-key-validation equivalence.

## Error, allocation, and disclosure closure

The exhaustive V1 errors cover only phase shape, closed metadata/byte fields,
aggregate cap, public-key base64url/point validation, role-tagged signature
base64url/strict verification, length overflow, allocation failure, receipt
encoding invariant, and receipt cap. First-error precedence is fixed from phase
shape through aggregate arithmetic, metadata, byte bounds, key, signatures,
strict verification, and receipt encoding.

All raw slices together are checked and capped at 10,485,760 bytes. Preimages
are constructed and dropped sequentially; envelopes are hashed without copies;
all caller-influenced allocations use checked sizing and fallible reservation.
Manual redacted `Debug` implementations expose only tags, lengths, `<redacted>`,
and safe output identity. Sentinel tests must prove no raw input appears in any
implemented public `Debug` or `Display` path.

## Future attestation cannot launder source receipts

Any future platform wrapper is a separate gate and may expose only same-process
`verify_and_attest(original_inputs)`. It must invoke this verifier itself. There
is no `attest_receipt(bytes)`, caller-supplied receipt/digest, or caller-visible
attestation key.

The separate attestation equality-binds the typed output, exact canonical bytes
and digest, verifier binary measurement, source head, dependency lock, nonce,
provider evidence, and trusted time. It cannot rewrite, overlay, omit, or
promote any source-receipt field or replace any false/zero literal.

## TDD, offline, and supply-chain proof

The next gate begins RED with synthetic public vectors only. Required coverage
includes RFC 8032 plus protocol preimages, weak/small-order and malleability
boundaries promised by `verify_strict`, base64url canonicality, phase splice and
ordering, one-field crypto mutations, evidence-only identity mutations, exact
JSON grammar, authority deletion/mutation, aggregate and field caps, total
multi-fault precedence, forced allocation failure, panic resistance, repeat
identity, and raw-debug leakage.

The one-time crates.io fetch must be recorded as a public network effect. CI
then uses distinct build outputs:

1. `CARGO_TARGET_DIR=target/alr-online cargo test --locked -p openclaw_alr_fit_verifier`;
2. `CARGO_NET_OFFLINE=true CARGO_TARGET_DIR=target/alr-offline cargo test --locked -p openclaw_alr_fit_verifier` from an initially absent target; and
3. locked offline metadata plus parsed metadata/lock/static assertions.

The guard must inspect all dependency kinds, features, sources, checksums,
targets, and reverse workspace reachability; reject git/path/patch/replace
substitution; and prove no engine/core/types path to the verifier or its crypto
dependencies. The PR/scheduled macOS verifier test preserves the current
no-push cost policy.

## Independent review record

Governance task-contract digest:
`sha256:f52552dcae71880051a13d9e7a76e3defd00fa4c556309bc272f526c3db04492`.
Route DAG digest:
`sha256:9a1c318b0df5dad246ee8116e4b0ae0a42795987543d1b368bb7e958eb5e9f4c`.
Repaired design-fragment SHA-256:
`9d957cf70f9beba5a9c48e66fd64bcef772f3e550cc1c636d9bcddf56d6de361`.

The final PA/FA/CC/E3/MIT context-artifact digests are:

- PA: `sha256:23a0b13179a868f3975697d15bc145da84c7ad65a94ff789a402ad2324aeb81f`;
- FA: `sha256:4df5dec17eb6ff9da102607f04e9c20a96048d2cb16a1b22c71cc7a35513f2fe`;
- CC: `sha256:f1fc0e06ff7a3e20b1b72ff1e6aa07e8b6129a1c14b5c9745abbfc5aacf37c8b`;
- E3: `sha256:b6e56b513cd95b6fc661f702e2c43b5891438ddb577287dcb839e5718e540b3b`;
- MIT: `sha256:41d336bbf64b5e4531c2c3f00bd0f11158a77e8e4c21ae06c3bb9842540702b8`.

FA initially found P0/P1/P2 `0/5/1`, CC `0/2/0`, and E3 `0/4/4`.
Repairs closed trust overclaim, exact nested schema/grammar, total errors and
fallible allocation, evidence-mutation semantics, redacted Debug, targeted
unsafe checks, clean offline compilation, metadata/lock inspection, and
attestation laundering. Final PA, FA, CC, E3, and MIT each returned
`ACCEPT`, P0/P1/P2=`0/0/0`.

## Effects and G1-G9 adjudication

This gate changed no repository source, test, Cargo, lock, workflow, SQL,
migration, runtime, service, or authority file before this checkpoint. It
performed read-only repository/cache inspection and public official
crate/advisory documentation lookup only. It did not fetch a crate, contact
PostgreSQL or Linux `trade-core`, contact a private issuer/runner/broker, sign
or verify real bytes, run a trainer/fit, create model bytes, write a row or
registry, update a symlink, serve/promote, place an order, change risk/Guardian/
Lease/Cost Gate, or grant authority.

- G1 remains `PARTIAL`.
- G2 remains `PARTIAL_DISPOSABLE_PG_VERIFIED`.
- G3 remains `FAIL_DISPOSABLE_PG_VERIFIED_NO_REAL_RECEIPT_OR_OUTCOME_CHAIN`.
- G4 remains `FAIL_DISPOSABLE_PG_VERIFIED_EXECUTION_NOT_ESTABLISHED`.
- G5, G6, and G7 remain `FAIL`.
- G8 and G9 remain `PARTIAL_WP1_PASS`.

## Next safe action

Advance to the separately governed
`WP4-TRUSTED-ED25519-VERIFIER-SOURCE-TDD-GATE`. Repeat source/lock/CI baseline
checks, begin with RED tests, record the public crates.io fetch, implement only
the nine-path slice, prove a distinct-target offline replay, inventory the lock
and advisories, and obtain independent source/security/regression review.

That gate still cannot author V160, apply PostgreSQL, activate a runtime
capability, contact real issuer/runner/broker surfaces, consume real bytes, run
fit, create model/registry/serving state, or grant authority.
