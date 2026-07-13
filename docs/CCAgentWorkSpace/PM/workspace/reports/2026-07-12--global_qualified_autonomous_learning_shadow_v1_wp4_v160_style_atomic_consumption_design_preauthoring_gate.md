# WP4 V160-Style Atomic Consumption — Design Preauthoring Gate

Date: 2026-07-12
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP4-V160-STYLE-ATOMIC-CONSUMPTION-DESIGN-PREAUTHORING-GATE`
Reviewed source head: `9a41c8d2abf34dbdce01fde010a500b4c19ba4f4`
Status: `DONE_DESIGN_ACCEPTED_V160_STYLE_ATOMIC_CONSUMPTION_PREAUTHORING_GATE`

## Gate result

The read-only architecture is accepted. It freezes one fixed guarded
coordinator that can later consume an authenticated request and nonce, record
the exact trusted terminal receipt, independently reverify a successful inner
V159 receipt, and expose the complete V159 success bundle atomically.

This is a design checkpoint only. It does not authorize source or test
authoring, reserve or create V160, apply PostgreSQL, contact an issuer or
runner, run fit, create model state, or mutate runtime or authority. A real
platform-attested Ed25519 verifier does not yet exist. Goal and WP4 remain
`ACTIVE`; G3 and G4 remain failed.

Fresh migration inspection found `141` eligible files, maximum version `159`,
zero duplicate versions, and no V160 file.

## Why V159 cannot be composed directly

The accepted pure handshake can validate production-shaped values, but it
cannot persist or consume a request. V159 validates the final structural
projection, yet it trusts caller claims that cryptography was verified. Its
attestation and result wrappers also require distinct exact session users, so
sequential application calls cannot provide one atomic success transition.

The accepted design therefore rejects bool callbacks, role-name assertions,
and sequential wrapper composition as durable authenticity or consumption
evidence.

## Frozen verifier capability

A dedicated Rust capability must perform strict Ed25519 verification against
the exact request, outer response, and decoded inner bytes using the immutable
policy snapshot and the current `PLATFORM_OR_EXTERNAL_ATTESTED` key-status
overlay. The intended primitive is strict verification equivalent to
`ed25519-dalek::VerifyingKey::verify_strict`; the implementation and dependency
choice remain subject to the next source preauthoring gate.

The capability emits a closed
`alr_fit_ed25519_verification_receipt_v1` in exactly one phase:

- `REQUEST_ONLY` binds request bytes, request preimage, key/policy/overlay,
  provider evidence, adjudication time, and request verification result;
- `SIGNED_STATUS` additionally binds the exact signed status bytes, preimage,
  and result;
- `TERMINAL_SUCCESS` additionally binds exact outer-terminal and decoded-inner
  bytes, all three domain-separated preimages, and independent request/outer/
  inner results; and
- `TERMINAL_NO_INNER` binds request and terminal response while forbidding
  inner material.

Each coordinator action accepts only its exact phase. Production persistence
requires platform or external attestation of the verifier capability itself.
Synthetic fixture claims remain `EXTERNAL_HOST_UNCHECKED` and ineligible.

## Frozen lifecycle and transaction boundary

One coordinator Interface exposes six closed actions, each in one bounded
transaction. No database transaction may span fit:

1. `REGISTER_REQUEST` authenticates and stores exact request bytes and reserves
   admission, generation, request, and issuer/nonce identities without fit
   authority.
2. `CLAIM_REQUEST` durably claims the registered request before any input
   consumption or fit.
3. `RECORD_STATUS` appends an authenticated, monotonic
   `ACCEPTED_IN_PROGRESS` response for an existing claim.
4. `CONSUME_TERMINAL` handles one authenticated terminal response.
5. `EXPIRE_UNCLAIMED` records database-time expiry for a never-claimed request.
6. `MARK_RECONCILE_REQUIRED` appends optional audit evidence for an ambiguous
   response. It is never the eligibility or retry safety gate.

Request, status, reconciliation, verifier-receipt, and terminal bytes are
append-only. Uniqueness covers the admission plus generation, request hash,
issuer plus nonce digest, and one terminal consumption per request.

## Closed terminal branches

- `SUCCEEDED` requires a prior claim, request/outer/inner strict verification,
  canonical decoding, V158 admission, exhaustive typed outer-to-inner equality,
  and the complete existing V159 projection. Its terminal row, attestation,
  completed run, ordered q10/q50/q90 artifacts, and `NOT_SERVING` registry row
  commit together. No new-path `ATTESTED_UNBOUND` state may be visible.
- `REJECTED_PRE_FIT` commits only the authenticated no-execution terminal and
  permits a greater generation after commit. It writes no V159 row.
- `FAILED_AFTER_START` commits the authenticated terminal and a reconcile event
  atomically, writes no V159 row, and forbids autonomous retry.
- `EXPIRED_UNCLAIMED` requires a registered request, database time at or after
  `accept_by`, and no claim, status, terminal, reconcile, runner receipt, or
  V159 state. It writes only expiry and permits a greater generation.
- missing, malformed, conflicting, or timed-out response leaves the immutable
  request/claim identity blocking retry. The optional reconcile marker only
  enriches audit evidence.

Status generation is strictly monotonic. Exact byte replay returns the
original server result; divergent reuse conflicts. A status must expire no
later than `complete_by`, cannot extend request clocks, and carries no terminal,
fit, artifact, or V159 authority.

## Replay, concurrency, and durable conflict oracle

The later coordinator must take sorted locks over admission, request,
issuer/nonce, generation, and V159 identities. Unique constraints remain the
final oracle, and database time is captured after locking.

Exact committed replay is idempotent even after later expiry. Any divergent
bytes, nonce, generation, projection, verifier evidence, structural identity,
or artifact set returns `DURABLE_CONSUMPTION_CONFLICT` with zero terminal/V159
mutation. The already committed request, nonce, generation, claim, or terminal
identity is itself the durable conflict oracle. This keeps safety atomic: no
transaction rolls back a conflict and then claims that a second reconcile
write made the conflict durable.

## Fixed ownership and reachability

The future source must use two membership-free roles:

- `alr_challenger_consumption_coordinator`: `NOLOGIN NOINHERIT`, function owner,
  with only narrow table `SELECT/INSERT`; and
- `alr_challenger_consumption_caller`: `LOGIN NOINHERIT`, connection limit one,
  with schema `USAGE` and coordinator/read-function `EXECUTE` only.

The incompatible current paths are explicit: V159
`persist_alr_challenger_fit_attestation_v1` is owned by the attestor path and
requires the fit-attestor caller, while
`persist_alr_challenger_training_result_v2` and its reader are owned by the
writer path and require the trainer caller. They cannot be treated as an
atomic application transaction merely because both functions are individually
guarded.

The caller receives no table DML, schema `CREATE`, membership, or
`session_replication_role` path. Functions use fully qualified objects and a
fixed safe search path. A future forward migration must revoke and hard-close
all current V159 application-wrapper overloads and INSERT paths from existing
callers, `PUBLIC`, generic roles, `trading_ai`, and `alr_shadow`, while
preserving the exact V158 qualified-receipt writer/reader. A fixed read-only
projection may expose reconciliation state.

Deletion tests are mandatory: removing coordinator `EXECUTE` must leave no
application V159 write path, and removing or failing the real verifier must
make request and terminal consumption fail closed.

## Later source-test obligations

Any separately authorized implementation must cover collision and double
apply; exact and divergent replay; concurrency and lock ordering; partial
failure; malformed canonical bytes; stale/revoked/wrong keys; phase mismatch;
status monotonicity; all terminal branches; direct wrapper and table-DML bypass;
owner, overload, ACL, trigger, constraint, and partial-schema inventory; and
all false/zero authority assertions.

It must reuse frozen V158/V159 identities and the public pure handshake
validators without redefining hashes. A future migration reservation requires
a fresh collision scan plus separate E3/BB authorization.

## Independent review record

Governance task digest is
`sha256:dba068f0a6c4d3933eae034e0c7c3e3fe18673cf93c4bbad0be3af225e68dcb3`;
route DAG digest is
`sha256:9a1c318b0df5dad246ee8116e4b0ae0a42795987543d1b368bb7e958eb5e9f4c`.
PA and FA context artifacts are
`sha256:7905eb3b42f9dcae07b9a30f7a5fd387835026432fe25348bdd4854424b61071`
and
`sha256:b6404d8b9045679c2eb5dfde38f3b829a50d6bf46a30c0b43799b3a04daaa967`.

FA initially found phase-timing, status-reachability, conflict/reconcile, and
expiry ambiguities. CC then found a second-write atomicity defect in reconcile
handling. The design was repaired with phase-specific receipts, explicit
registration/status actions, closed failure and `accept_by` expiry rules, and
the immutable identity as the safety oracle with reconcile as audit only.

PA, FA, CC, E3, and MIT final reviews all accept the repaired design with
P0/P1/P2=`0/0/0`. The CC/E3/MIT context-artifact digests that bound their
independent review inputs are:

- `sha256:32196714771f258dcfb1165eab4baf1625ddc85cf74fb6ab5327e1199d8f5259`;
- `sha256:48efa81810b503a7f267dbe3af3309d5365acb9a07f3b81e18ad606aa70ec5a8`;
- `sha256:dc415a8e536b012050a0334e7e02111a66503c78e7c1d26ec4a65067d0f5f288`.

E3 treats connection limit one as defense in depth only and requires direct
DML/overload deletion tests. MIT confirms that no training claim exists.

## Effect and G1-G9 adjudication

No source, test, migration, workflow, SQL reservation, PostgreSQL, filesystem
transport, network, Linux `trade-core`, runtime service, issuer, runner,
broker, request/receipt bytes, signature verification, trainer, fit, model,
model artifact, row, registry, serving/promotion, order, risk/Cost Gate, or
authority effect occurred. Production/runtime V159 remains unapplied and
unrefreshed. V160 remains absent.

- G1 remains `PARTIAL`.
- G2 remains `PARTIAL_DISPOSABLE_PG_VERIFIED`.
- G3 remains `FAIL_DISPOSABLE_PG_VERIFIED_NO_REAL_RECEIPT_OR_OUTCOME_CHAIN`.
- G4 remains `FAIL_DISPOSABLE_PG_VERIFIED_EXECUTION_NOT_ESTABLISHED`.
- G5, G6, and G7 remain `FAIL`.
- G8 and G9 remain `PARTIAL_WP1_PASS`.

The Goal and WP4 remain active and terminal eligibility remains false.

## Next safe action

Advance only to the read-only
`WP4-TRUSTED-ED25519-VERIFIER-SOURCE-PREAUTHORING-GATE`. It must freeze the
exact Rust crate/module/API, byte ownership, strict-verification result and
error taxonomy, attestation input boundary, dependency/offline posture,
FFI/subprocess prohibition or explicit seam, and mutation-biting tests before
any source authoring is permitted.

It may not author source/tests or V160, reserve a migration, contact
PostgreSQL/runtime/issuer/runner/broker, sign or verify real request bytes, run
fit, create model/registry state, serve/promote, change order/risk/Cost Gate,
or grant authority.
