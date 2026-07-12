# Global Qualified Autonomous Learning Shadow V1

Date: 2026-07-10
Owner: PM
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Codex Goal thread: `019f4b6d-1e5b-7551-9fce-7a2f029a1675`
Status: `ACTIVE_WP4_DURABLE_FIT_ATTESTATION_DISPOSABLE_PG_VERIFICATION_GATE`

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
