# Global Qualified Autonomous Learning Shadow V1

Date: 2026-07-10
Owner: PM
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Codex Goal thread: `019f4b6d-1e5b-7551-9fce-7a2f029a1675`
Status: `ACTIVE_WP4_VERSIONED_TRAINING_REGISTRY_CONTRACTS`

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

WP4's first source slice is accepted at
`f36379b9ddf10ee1055daeda27805c409c6ee8bd`. The collision scan found 139
migrations through V157, zero duplicates, and no observed V158 reservation;
V158 is provisional only. `alr_challenger_training_contract_v1` now binds only
repository-derived proof/reward receipts to exact PIT/data/split/reward/code/
config/resource hashes. It rejects forged or split lineage and always remains
`SCHEMA_REQUIRED`, with training/model/registry/runtime authority false.

Focused tests passed `32`; full ML passed `1850` with `36` skips; independent
E2 and QA final P0/P1/P2 are `0/0/0`. No migration, fit, model, registry,
runtime, or authority action occurred. V152/V153 bytes remain frozen. The next
step is a fresh exact `E3 -> BB` gate for provisional forward-schema
reservation/creation plus isolated no-symlink trainer/repository design.

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
