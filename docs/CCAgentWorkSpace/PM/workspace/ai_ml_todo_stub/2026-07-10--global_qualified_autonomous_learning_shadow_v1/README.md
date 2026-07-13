# Global Qualified Autonomous Learning Shadow V1

Date: 2026-07-10
Owner: PM
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Codex Goal thread: `019f4b6d-1e5b-7551-9fce-7a2f029a1675`
Status: `ACTIVE_WP4_V160_STYLE_ATOMIC_CONSUMPTION_SOURCE_TDD_GATE`

This is the durable PM-owned queue and state surface for the active Goal. It
supersedes the old ALR P2 completion/terminal interpretation, but does not edit
or erase the historical P2 queue, AMD-2026-07-10-02, exact SUI packet, or their
reviews.

The Goal is an engineering and learning-shadow mandate. It is not standing,
generic, candidate, Demo, exchange, or order authority. ALR may write only
validated `learning.alr_*` evidence, challenger-registry, health/state, and
gated derived-cache retention records. It has no exchange, trading,
order/probe, Decision Lease, Guardian mutation, RiskConfig mutation, global
Cost Gate, live/mainnet, serving, promotion, `_latest`, protected-evidence
deletion, or direct parameter-apply authority.

`ProofPacket`/Reward generation is evidence production, not promotion
authority. `CHALLENGER_ACCEPT` is not serving, deployment, live eligibility, or
order authority.

## WP3 source acceptance and active WP4 basis

WP3's first source-only bridge checkpoint is accepted at
`8999aa2b7e4a3bba3841f4c72cf054d88cb69c5c`.  The new pure
`candidate_proof_adapter_v1` validates a complete B2.2c projection through the
existing public projection-plan validator, requires its immutable handoff, and
derives candidate/context identity from the selected identity/context hashes.
It only summarizes caller-provided ProofPacket and RewardLedger artifacts: no
proof, reward, fill, receipt, durable record, training, service, runtime, or
broker fact is created. Exact artifact/decision/handoff provenance, PIT
candidate scope and decision-time causality, no-fill-as-non-reward, canonical
reward-set ordering, and all-false/zero authority summaries are fail-closed.

Focused tests passed `10`; the one current-generation integrated suite passed
`263`. E2, QC, and QA final P0/P1 are `0/0`. This is a source checkpoint only:
actual proof/reward/training/OOS runtime evidence remains zero and the B2.2c
runtime gate remains pending. At that checkpoint the next source-only scope
was `WP3-PROOF-REWARD-REPOSITORY-ADAPTERS`; it is now accepted below.

The remaining WP3 repository seam is source accepted at
`c2bdefbfdb52eeaab4e801de783719ecfe0da7bc`. It selects the newest candidate
projection family before exact-v2 validation, reconstructs complete bounded
`training_input` lineage from immutable source rows, derives the proof binding
internally, and validates existing V153 outcome-bridge containers without
reusing their run-bound kind/edge semantics for a new write. A final single
PostgreSQL snapshot rechecks the projection head, lineage identities, and
bounded bridge set before any semantic receipt is returned. Exact reward bytes
retain their container order; a separately labelled canonical copy feeds the
pure adapter. More than 64 bridge or lineage rows yields an explicit
schema-required condition with no positive receipt.

The result is only a hash-bound in-memory receipt. It states
`receipt_persisted=false`, `runtime_or_exchange_attested=false`, preserves
`unverified_source_only`, writes zero rows/bytes, and grants no proof, reward,
training, serving, promotion, trading, lease, Cost Gate, or exchange authority.
Focused verification passed `66` with one Darwin-only skip; the complete ML
suite passed `1818` with `36` platform/optional skips. E2, QA, and CC/FA final
P0/P1/P2 are `0/0/0`. No Linux, PostgreSQL, service, Bybit, or runtime action
occurred.

WP4's first source slice remains accepted at
`f36379b9ddf10ee1055daeda27805c409c6ee8bd`.
`alr_challenger_training_contract_v1` binds only repository-derived
proof/reward receipts to exact PIT/data/split/reward/code/config/resource
hashes. It rejects forged or split lineage and remains `SCHEMA_REQUIRED`, with
training/model/registry/runtime authority false.

The exact E3/BB pre-authoring gate subsequently authorized source/tests only.
Forward-only V158 source is published at
`beeb77325c83a157c74cf54e79b7146876ed5e27`; repository source now contains
140 migrations through V158 with zero duplicates. V158 defines isolated
durable receipt, completed training-run, exact q10/q50/q90 artifact, and
NOT_SERVING challenger-registry tables plus fixed APIs, replay/immutability,
deferred completeness, exact role/ACL, and no-authority guards. It does not
edit V152/V153 or reuse the legacy serving registry.

Focused tests passed `37`; full ML passed `1850` with `36` skips; the Rust
schema harness compiled without running PG; independent final P0/P1/P2 are
`0/0/0`. V158 was not applied, and PostgreSQL/Linux/runtime state was not
refreshed. This source publication created no receipt/run/artifact/registry
rows, fit, model bytes, symlink, serving/promotion state, or authority. G4
remains failed. At that V158 checkpoint, the next source slice was the
fake-connection durable-receipt repository tracer; it is now accepted at the
checkpoint below. Trainer, fit, filesystem publication, migration apply, and
runtime remained gated.

The repository-only fixed-writer tracer is now source accepted at
`c0aec6813b59f3c17b1fb93350794a3581ccd5ae`. It snapshots and fully validates
the existing receipt-only training contract, independently derives the exact
schema-versioned reward-set and 30-field durable-receipt payload hashes, and
calls only `learning.persist_alr_qualified_training_receipt_v1` with its exact
15 TEXT plus JSONB arguments. It accepts only exact PERSISTED/DUPLICATE full
rows after typed response parity and requires a dedicated clean psycopg2 IDLE
transaction so it cannot commit or roll back unrelated work.

Focused verification passed `31`; adjacent contract/repository/V158 checks
passed `121`; the optional-LightGBM-unavailable full ML posture passed `1920`
with `28` skips, exactly `31` more passes than the same-environment baseline.
Two exact-byte final reviews reported P0/P1/P2 `0/0/0`. This was fake-DB source
TDD only: V158 was not applied, PostgreSQL was not contacted, and no durable
receipt row, reader proof, fit, artifact, registry, filesystem, runtime, or
authority fact was created. Its then-next V158 fixed receipt reader is now
accepted at the checkpoint below.

The contract-bound qualified-receipt reader is source accepted at
`fb842a36f006ad58249ff536a455232d2c455f8b`. It snapshots and validates the
same training contract, derives both durable-receipt and training-key lookup
identities internally, and calls only
`learning.read_alr_qualified_training_receipt_v1` with exactly two TEXT
arguments. `FOUND` must reproduce the exact typed 20-field row and canonical
payload; `NOT_FOUND` must be the exact two-key null-receipt response. The same
dedicated clean psycopg2 ownership contract closes success with commit and
failures with one rollback without touching rejected pending work.

Two RED-to-GREEN cycles covered the missing API and the initially rejected
`NOT_FOUND` branch. Focused `61`, adjacent `130`, full ML `1911 passed/36
skipped`, same-environment baseline `1881 passed/36 skipped`, exact reader
delta `+30`; E2/E4/MIT and independent P0/P1/P2 `0/0/0`. This was source and
fake-connection work only: V158 was not applied and no PostgreSQL, Linux,
runtime, exchange, trainer, fit, model/file, registry, serving, promotion, or
authority effect occurred. Its then-next pure result contract is now accepted
below.

The pure post-fit observation contract is source accepted at
`c64c5e28be80bad1093c39c90eda161004ab34d5`. It reuses a public pure validator
for the exact `FOUND` receipt and preserves the complete bound training
contract snapshot. Caller observations contain no hashes, paths, status, or
authority switches: raw q10/q50/q90 bytes derive their own SHA-256 identities
and the exact V158 ordered set hash; a closed LightGBM trainer spec uses
exact-decimal parameters and a non-Boolean admitted seed; metrics and resource
usage use closed canonical shapes.

The envelope remains explicitly non-authoritative. Trainer, seed, timestamps,
metrics, resources, ONNX semantics, and artifact bytes are all `UNVERIFIED`;
`execution_claim` and `model_training_performed_claim` are
`NOT_ESTABLISHED`; persistence is false; trusted fit attestation, actual
dataset/row/split/code/config/schema rehash, artifact readback, and a durable
V158 attestation-binding schema are required. The validator is total over
malformed deep, wide, cyclic, exploding, and infinite container inputs under
bounded snapshot budgets. It exposes no V158 result writer or legacy 28-arg
surface.

Focused repository/result verification passed `105`; adjacent
training-contract/repository/result/V158 checks passed `174`; full ML passed
`1955` with `36` platform/optional skips, exactly `44` more passes than the
same-environment reader baseline. PA, E2, E4, and MIT final P0/P1/P2 are
`0/0/0`. This remains source-only synthetic-fixture evidence. V158 was not
applied; no PostgreSQL, Linux, runtime, exchange, fit, model/ONNX file,
artifact readback, attestation, registry, symlink, serving, promotion, or
authority effect occurred.

The pure fit-capture candidate is source accepted at
`a09c70f243723fea1645b597e96c6cf08795fd6c`. It revalidates the complete
result contract and internally derives source-head, canonical input-lineage,
dataset/row/split/code/config/feature/label, runner-identity, and q10/q50/q90
readback hashes from bounded raw bytes. Raw materials are absent from the
serialized candidate.

The serialized status is fixed to `OUT_OF_BAND_FIT_ATTESTATION_REQUIRED`.
Literal verifier `True` produces only `FIT_CAPTURE_ATTESTED_EPHEMERAL` with
`EXTERNAL_HOST_UNCHECKED` authenticity. Execution and model-training claims
remain `NOT_ESTABLISHED`, persistence is false, every authority flag is false,
and every authority counter is zero. Callback exceptions, truthy aliases,
mutation, and malformed bounded structures fail closed.

Focused `43`, adjacent `217`, and full ML `1998 passed/36 skipped` passed.
Current-head E2/E4/CC/MIT final P0/P1/P2 are `0/0/0`; governed E4 capture is
`9250f3ab31b17ec557f613629c7eb3eb70a4625e70e6677a4094c81daef61447`.
This remains source-only synthetic evidence. It did not run a trainer/fit,
create/read model files, apply V158, contact PostgreSQL/Linux/runtime/Bybit,
write a durable row/registry, create a symlink, or grant serving/promotion or
trading authority.

The durable schema design and preauthoring gate are now accepted at reviewed
head `0c90de9c20052afab7f715a055f2df6a9d0d190b`. PA/CC/FA/MIT accepted the
repaired architecture; E3 and BB returned `APPROVE_SOURCE_AUTHORING_ONLY`, and
BB confirmed the verdict after the unrelated IBKR source advance. Final
P0/P1/P2 are `0/0/0`.

The frozen design requires exact V158 posture, fixed-order locks, zero result
rows, an immutable attestation relation, byte-exact authenticated receipt SSOT,
`PLATFORM_OR_EXTERNAL_ATTESTED` only, database-recomputed durable identities,
structural-run artifact paths, atomic attestation/run/q10-q50-q90/NOT_SERVING
binding, strict database-time expiry and replay behavior, and hard failure for
every application-reachable v1 writer/reader overload. It introduces no generic
DML/EXECUTE or authority.

A fresh current-head scan found 140 migrations through V158, zero duplicate
versions, and V159 absent/unreserved. The gate itself did not reserve, author,
or apply V159 and created no PG/Linux/runtime/Bybit/fit/model/registry/serving
effect. The next safe slice is
`WP4-DURABLE-FIT-ATTESTATION-SCHEMA-SOURCE-TDD`: repeat that scan at the
then-current head, then author only the forward migration and isolated/static
tests. Migration apply, runtime contact, and real fit remain separately gated.

The forward durable-attestation schema source is now accepted and published at
`27bfe34b608b732071205c351dd1aa3fdd7d2283` on
`origin/agent/alr-wp4-contracts`, based on `origin/main`
`b83ddee0d2c1e74db52355fbcce9ff0c49cee44f`. V159 contractually closes the
direct V158 unattested persistence surface through exact authenticated receipt
bytes, immutable attestation lineage, structural/durable identity separation,
atomic complete binding, database-time expiry/replay, v1 hard closure, least
privilege, and false/zero authority. The collision scan is `max159/duplicates0`
and frozen V158 remains byte-identical at SHA-256 `b1ff8e2d...`.

Source/static verification passed `232/232`, V158+V159 passed `269/269`, and
the governed Rust schema harness passed `7/7`; E2/CC/E3/MIT final P0/P1/P2 are
`0/0/0`, with E4 `SOURCE_ONLY_PASS`. The V006 `trading_ai` CI precondition was
caught with `4 RED` and repaired to `4 GREEN`. The Rust run used an isolated
HOME but fetched public crates.io dependencies; an offline retry failed before
tests because that home lacked a cache. Zero-network/offline reproducibility is
therefore not proven.

V159 was not applied and neither disposable probe ran. Beyond the expected
GitHub source fetch/push, no private trading/runtime or broker endpoint,
PG/Linux/runtime, trainer/fit, model/file, durable row, registry,
serving/promotion, or authority effect occurred. G3/G4 remain failed. The next
highest-ROI safe item is
`WP4-DURABLE-FIT-ATTESTATION-DISPOSABLE-PG-VERIFICATION-GATE`: governed,
isolated PG16/Timescale execution of the functional and concurrency probes
only. External issuer evidence and a real fit remain a later separate gate.

## Disposable PostgreSQL verification checkpoint

Exact head `74d8475e32ff89b67e2b6a1346e0839bbcfa646f` passed hosted run
`29195892105` and schema job `86658665742`. Functional and concurrency probes
ran against distinct disposable PG16/Timescale databases; both force-drop
cleanups, schema consumer, and teardown passed. The migration audit executed
informational-only/non-gating. Intended transient
fixture writes were destroyed, surviving rows are `0`, and production/runtime
writes are `0`. The green run was attempt 12 after `11` same-scope failed-safe
repairs. Current hashes are V158 `7ed70599...`, V159 `2e11d0ae...`, functional
probe `d29d4b81...`, concurrency probe `5965ae7e...`, and static contract
`f6ffc199...`.

Completed gate is `DONE_DISPOSABLE_PG_VERIFIED`; Goal and WP4 remain `ACTIVE`.
The fixtures were synthetic: no external real receipt, isolated runner use,
fit, model training, production row, serving/promotion, profit, or authority
was established. G1 is partial; G2 is partial with disposable-PG verification;
G3/G4 and G5-G7 remain failed; G8/G9 remain partial. Production/runtime V159
is still unapplied and unrefreshed.

## Trusted-issuer / isolated-runner handshake design checkpoint

Reviewed head `2189c996101da680a8ac9ec426d28c1028b3557d` completed
`DONE_DESIGN_ACCEPTED_TRUSTED_ISSUER_ISOLATED_RUNNER_HANDSHAKE_PREAUTHORING_GATE`.
The design freezes an issuer-signed pre-fit request whose hash is the only
`attempt_id`/runner invocation, a 256-bit nonce and immutable policy snapshot,
pre-fit runner-target constraints, an atomic pre-fit claim, a
trusted-issuer-signed terminal receipt, exact replay/conflict/timeout rules,
Ed25519-only handshake v1, and a pure
`AUTHENTICATED_UNCONSUMED` verification ceiling.

V159 remains the inner containment layer. It does not cryptographically verify
the signer or durably bind request/nonce/audience/policy-snapshot consumption.
A future V160-style companion seam must atomically consume those identities
with the exact V159 result; no such migration was reserved or authored.

The design gate created no request/receipt bytes, source/tests/SQL, PG,
files/network/runtime contact, fit/model/registry, serving/promotion, or
authority effect. G3/G4 remain failed and production/runtime V159 remains
unapplied.

That source gate is now accepted below.

## Trusted-issuer / isolated-runner handshake source checkpoint

Source checkpoint `c900d1ecb2eac495994b8715f09ad10bee6d9583` completed
`DONE_SOURCE_ACCEPTED_TRUSTED_ISSUER_ISOLATED_RUNNER_HANDSHAKE_CONTRACT`.
The pure `alr_trusted_fit_handshake` module implements the frozen signed
request, accepted-in-progress status, terminal receipt, replay, immutable
trust-policy plus current revocation-overlay, V158 admission, complete V159
success projection, runner lineage, time/resource/artifact binding, and closed
success/reject/failure branch contracts. It performs no I/O and imports only
stdlib plus existing pure public validators.

The synthetic fixture ceiling remains deliberately below execution proof.
Final fixture verification is `EXTERNAL_HOST_UNCHECKED`, signatures are not
production-valid, `AUTHENTICATED_UNCONSUMED` is never emitted from the fixture
path, persistence and durable consumption remain false, execution and model
training remain `NOT_ESTABLISHED`, and every authority field/counter remains
false/zero. Source/test SHA-256 values are `32181c5f...` and `ac7ac687...`.

Verification passed focused `105`, adjacent five-contract `285`, and full ML
`2103 passed/36 skipped`. Independent E2, E3, E4, CC, and MIT final reviews
reported P0/P1/P2 `0/0/0`. E4 governed record digests are focused
`52d304f1...`, adjacent `a036fcfc...`, full `9df8dcea...`, full stdout
`b3c12f99...`, and full replay `4247b5a1...`.

This was source/test work only. It created or consumed no real issuer/runner
bytes, contacted no PostgreSQL, Linux, runtime, network, broker, or exchange,
ran no trainer/fit, created no model or model-artifact file, registry,
serving/promotion state,
persisted no request/receipt, and granted no authority. Production/runtime
V159 remains unapplied and unrefreshed; G3/G4 remain failed.

That design gate is now accepted below.

## V160-style atomic-consumption design checkpoint

Reviewed clean head `9a41c8d2abf34dbdce01fde010a500b4c19ba4f4`
completed
`DONE_DESIGN_ACCEPTED_V160_STYLE_ATOMIC_CONSUMPTION_PREAUTHORING_GATE`.
The design freezes one mutation Interface with bounded `REGISTER_REQUEST`,
`CLAIM_REQUEST`, `RECORD_STATUS`, `CONSUME_TERMINAL`,
`EXPIRE_UNCLAIMED`, and audit-only `MARK_RECONCILE_REQUIRED` actions. No
PostgreSQL transaction spans fit.

A dedicated platform-attested Rust verifier must use a pinned strict Ed25519
primitive and emit one closed phase receipt: `REQUEST_ONLY`, `SIGNED_STATUS`,
`TERMINAL_SUCCESS`, or `TERMINAL_NO_INNER`. Each binds only the bytes and
verification results available in that phase. Bool callbacks, database roles,
caller-supplied verification claims, and the current synthetic fixture are not
production trust.

The persistence design is append-only and byte-exact. It separates request,
status/reconciliation, and terminal-consumption records; reserves admission,
request, issuer/nonce, generation, and one-terminal identities; and retains the
existing V159 attestation/run/q10-q50-q90/`NOT_SERVING` tables as the success
sink. `SUCCEEDED` atomically binds the exact outer and independently verified
inner receipt to the complete V159 bundle. Reject and expiry create zero V159
success state. `FAILED_AFTER_START` atomically persists terminal failure plus
reconciliation and forbids retry.

Exact committed replay returns the original server-owned result. Divergent
reuse creates no terminal/V159 mutation; the pre-existing immutable occupied
request/nonce/generation/claim/terminal identity is the durable conflict oracle
and blocks eligibility even when no optional reconcile audit marker is written.
Expiry uses database time with `clock_timestamp() >= accept_by` and requires a
registered request with no claim/status/terminal/reconcile/V159 state.

The ACL design uses a membership-free `NOLOGIN NOINHERIT` coordinator owner and
a `LOGIN NOINHERIT` connection-limit-one caller with only schema USAGE plus
fixed coordinator/read EXECUTE. A forward migration must revoke and hard-close
all old V159 application wrappers and direct write paths while preserving only
the V158 qualified-receipt writer/reader still used by the repository adapter.
Removing coordinator EXECUTE or the real verifier capability leaves no V159
application write path.

FA first found three P1 and one P2 lifecycle defects; repaired PA/FA returned
`0/0/0`. CC then found one P1 atomic-reconcile dependency; the immutable
conflict-oracle repair closed it. Final PA, FA, CC, E3, and MIT P0/P1/P2 are
`0/0/0`. Governed task/route digests are `dba068f0...` / `9a1c318b...`; final
PA/FA/CC/E3/MIT context-artifact digests are `7905eb3b...`, `b6404d8b...`,
`32196714...`, `48efa818...`, and `dc415a8e...`.

This gate created only design documentation. It did not create a verifier,
reserve/author/apply V160, change V158/V159, contact PG/Linux/runtime/network/
issuer/runner/broker, run fit, create a model or model-artifact file, mutate a
registry, serve/promote, or grant authority. G3/G4 remain failed.

The design is accepted but source authoring remains `NOT_AUTHORIZED_YET`.
Next is only read-only
`WP4-TRUSTED-ED25519-VERIFIER-SOURCE-PREAUTHORING-GATE`: bind the exact Rust
verifier module/dependency, phase receipt API, negative controls, and source-only
test boundary before any source is written. It does not authorize V160, PG,
runtime capability activation, real request/receipt bytes, fit/model, serving,
promotion, broker/order/risk, Cost Gate, or authority.

That source preauthoring gate is now accepted below.

## Trusted Ed25519 verifier source-preauthoring checkpoint

Reviewed clean head `75f3db2b55cd1d9737d83c811d291abecb67ad49`
completed
`DONE_DESIGN_ACCEPTED_TRUSTED_ED25519_VERIFIER_SOURCE_PREAUTHORING_GATE`.
The design selects one isolated `rust/openclaw_alr_fit_verifier` library with
no core/engine/types or runtime dependency and no existing-crate consumer. Its
only normal dependencies are exact-pinned, default-feature-disabled `base64
0.22.1`, `ed25519-dalek 2.2.0`, and `sha2 0.10.9`; `serde_json 1.0.149` is
dev-only for an independent receipt oracle.

One deep Interface accepts exact bounded key/evidence inputs and an exact
ordered job slice for `REQUEST_ONLY`, `SIGNED_STATUS`, `TERMINAL_SUCCESS`, or
`TERMINAL_NO_INNER`. It constructs every frozen domain/NUL/u64be-length
preimage internally and allows only `VerifyingKey::from_bytes`,
`Signature::from_bytes`, and `verify_strict`. Missing, extra, duplicate,
reordered, or wrong-role jobs fail before crypto.

The maximum receipt verdict is
`STRICT_SIGNATURES_VALID_INPUT_BINDINGS_CAPABILITY_UNATTESTED` with
`capability_authenticity=SOURCE_ONLY_UNATTESTED`. Semantic phase, canonical
input, envelope/payload parity, policy/overlay adjudication, trusted time,
platform attestation, coordinator eligibility, durable consumption,
persistence, training, and model execution remain false or `NOT_ESTABLISHED`.
Exact nested canonical JSON, all 17 false authority fields, all 17 zero
counters, a 10 MiB aggregate bound, fallible allocations, total first-error
precedence, and redacted Debug are frozen.

Any future attestation wrapper must call
`verify_and_attest(original_inputs)` in-process. It cannot accept caller-made
receipt bytes/digests or rewrite/promote source false/zero fields. Source CI
must test online, rebuild from a distinct initially absent offline target, then
parse metadata and Cargo.lock for every dependency kind, feature, source,
checksum, target, reverse edge, license, build script, unsafe implementation,
and advisory. First-party `forbid(unsafe_code)` is kept distinct from audited
transitive crypto internals.

FA initially found `0/5/1`, CC `0/2/0`, and E3 `0/4/4`. The repaired fragment
closed all trust, schema, allocation, mutation, Debug, offline, graph, and
attestation-laundering findings. Final PA/FA/CC/E3/MIT P0/P1/P2 are
`0/0/0`; task/route digests are `f52552dc...` / `9a1c318b...`.

This gate authored no Rust, Cargo, lock, test, workflow, SQL, or V160 and
fetched no crate. Read-only public official-document research occurred, but no
PG/Linux/private runtime/issuer/runner/broker/real-byte/fit/model/registry/
serving/order/risk/Cost Gate or authority effect occurred. G3/G4 remain failed.

The next separately governed state is
`ACTIVE_WP4_TRUSTED_ED25519_VERIFIER_SOURCE_TDD_GATE`. It may author only the
accepted nine paths, begins RED, records the public crates.io fetch, proves a
distinct-target offline replay and supply-chain inventory, and obtains
independent source reviews. V160, PG apply/runtime activation, real bytes,
issuer/runner contact, fit/model, serving/promotion, broker/order/risk, and
authority remain separate gates.

That source gate is now accepted below.

## Trusted Ed25519 verifier source checkpoint

Source checkpoint `0b9038c78a9e1a5256895901aa22376d645adbd4`
completed `DONE_SOURCE_ACCEPTED_TRUSTED_ED25519_VERIFIER`. The exact accepted
nine-path slice adds the isolated `openclaw_alr_fit_verifier` crate, its locked
default-off dependencies, closed phase/API/receipt/error/allocation contracts,
a bounded structured lexer/parser source guard, and dedicated online/offline
CI. No engine/core/types or runtime consumer can reach the crate.

The source success ceiling remains
`STRICT_SIGNATURES_VALID_INPUT_BINDINGS_CAPABILITY_UNATTESTED` and
`SOURCE_ONLY_UNATTESTED`. Source and hosted build/test success do not establish
semantic phase, canonical envelope parity, policy/time adjudication, production
platform attestation, durable consumption, persistence, fit, training, or
model execution. All authority values remain false/zero and model training
remains `NOT_ESTABLISHED`.

Exact local verification passed Rust unit/integration `5+28`, structured
scanner `10/10` metadata-free plus `10/10` metadata-aware, locked offline
replay, `cargo check -Dwarnings`, rustfmt, direct CLI, pycompile, and diff
checks. E2/E3/E4 final P0/P1/P2 is `0/0/0`. Hosted CI run `29213814965`
(#1101) completed `8/8` jobs SUCCESS. Public crates.io dependency fetch is
disclosed; no private/authenticated external contact occurred.

The source checkpoint created no trusted platform wrapper, real issuer/runner
bytes, V160 migration, PG/runtime state, fit, model artifact, registry row,
serving/promotion state, broker/order/risk effect, Cost Gate change, or
authority. Production/runtime V159 remains unapplied. G3/G4 remain failed,
production proof/reward/model rows remain `0/0/0`, and
`model_training_performed=false`. Source PASS is not training.

The next state is directly
`ACTIVE_WP4_V160_STYLE_ATOMIC_CONSUMPTION_SOURCE_TDD_GATE`, reusing the accepted
v805 design without a new design-only gate. It must first obtain the required
fresh migration collision/effect authorization, then author the fixed guarded
V160 coordinator and proceed to disposable PostgreSQL verification. With no
qualified candidate, only evidence collection or ROTATE is lawful; a fit must
not be forced.

## Earlier B2.2c event-primary reconciliation

After the WP3 validation adapter landed, source reconciliation proved that
`origin/main` still handled scanner-idle candidate boards by five-second idle
polling. The stale seven-file local implementation was not pushed or
cherry-picked. Instead, two narrow current-origin commits closed only the
remaining gaps:

- `03ef761bf92a6055ef3555d68d47a1f075b2298b` repairs READY-board
  decision-time fallback when a missing/invalid policy leaves the arbiter time
  empty. The validated board time remains hash-bound and the exact handoff
  causality gate remains active.
- `1b85318f29a16d5a7575b27cb158486fdfd47331` replaces candidate polling
  with bounded PostgreSQL/inotify multiplexing. Startup, overflow, and watch
  invalidation trigger full adapter reconciliation; the watch is bound through
  a held directory fd to resist pathname ABA; event names never carry learning
  content.

The pristine origin test file reproduced `6 failed, 17 passed`. The repaired
projection file passed `23`; the event suite passed `33` with one real-Linux
test skipped on Darwin; the complete ML suite passed `1790` with `36`
platform/optional skips. Two independent reviews reported P0/P1/P2 `0/0/0`.
This is source acceptance only. Linux inotify, service, PostgreSQL, natural
cycles, runtime proof/reward, and authority facts were not refreshed. WP3 is
source accepted and WP4 versioned training/registry contracts are active.

## Earlier B2.2c handoff checkpoint

WP2-B B2.2c restart-safe event-driven handoff is source accepted at
`328125a08e0f15057a110c69266d6a6ea71c8826`; Mac and `origin/main` matched at
source push. A validated v2 candidate board now has a canonical immutable
handoff identity tied to source/policy/prior-decision state. Exact replay is
zero-write only after existing artifact and provenance-edge integrity checks;
scanner-idle board deltas may evaluate through bounded immutable source rows.

B2.2c source criteria are accepted: focused `109 passed`, final integration
`190 passed`, and E2/QC/QA PASS with P0/P1 `0/0`. Runtime deployment/receipt
is pending a fresh exact E3/BB gate. This is not candidate qualification,
proof, reward, training, OOS, serving, promotion, or profit evidence. The next
source-only scope at that checkpoint was the now-accepted WP3 validation and
repository work; current work is WP4 versioned training/registry contracts.

This checkpoint refreshed no Linux, service, PostgreSQL, Bybit, data-freshness,
training, serving, promotion, or profit fact. The last accepted WP1 Linux and
ALR-service pin remains `7d1c247947f0fb6c139f8a0583c5e6ed6ae62c70`.

## Durable loop files

- `queue.md`: WP0-WP7 order, gates, transitions, retries, and next actions.
- `gap_matrix.md`: G1-G9 evidence and terminal eligibility.
- `baseline_state_packet.json`: immutable WP0 read-only source/runtime baseline.
- `loop_state_packet.json`: current Goal state and safe-work inventory.
- `effect_review.json`: delta and anti-repeat verdict for the current loop.
- `manifest.json`: machine-readable directory contract.

Every completed loop refreshes `queue.md`, `manifest.json`,
`loop_state_packet.json`, and `effect_review.json`, plus a PM report and an
Operator summary. `ADVANCED`, `DEFER_EVIDENCE`, `NO_ELIGIBLE_CACHE`,
`WAIT_OPERATOR_DEMO_AUTH_EXACT`, `DONE_SOURCE_ONLY`,
`DONE_OPERATIONAL_SHADOW`, and `BACKLOG_EXHAUSTED` are never Goal terminals.

## Goal terminals

- `DONE_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW`: G1-G9 all machine-verified.
- `HARD_BLOCKED_OPERATOR_ACTION_REQUIRED_CURRENT`: same current external
  operator-only blocker proven for three consecutive Goal turns, with no safe
  source/test/data/governance work remaining.
- `SAFETY_ABORT_BOUNDARY_CONFLICT`: a concrete requested action conflicts with
  a hard boundary and no safe narrowing exists.

The Goal remains active while any safe WP0-WP7 action exists.
