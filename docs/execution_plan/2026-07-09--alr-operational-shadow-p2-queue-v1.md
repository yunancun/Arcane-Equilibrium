# ALR Operational Shadow P2 Queue v1

Date: 2026-07-09
Authority: `TODO.md` controls the live status of this workstream. This file pins the versioned acceptance contract and is not a replacement queue.
Boundary: ADR-0049 and AMD-2026-07-09-02.

## Completion Rule

The only normal P2 terminal state is `DONE_OPERATIONAL_SHADOW`. It requires all rows below, including a Linux shadow soak. `DEFER_EVIDENCE`, an empty backlog, a source-only completion marker, and `model_training_performed=false` are not terminal states.

| ID | Status | Owner chain | Acceptance |
|---|---|---|---|
| P2-0 | DONE | PM -> CC -> FA -> PA -> PM | ADR/AMD, root TODO import, and this versioned queue establish the operational boundary without granting trading authority. |
| P2-1 | DONE | PM -> PA -> E1 -> E2 -> E4 -> QA -> PM | Source adapter validates the exact V030 row fields, binds `(scan_id, ts)` to a canonical SHA-256 payload hash, handles duplicate and late cycles without watermark rewind, and exposes only evidence-only/zero-authority output. It does not open DB/network/runtime access or mutate scanner. |
| P2-2 | DONE | PM -> E3 -> BB -> PM -> PA -> E1 -> E2 -> E4 -> QA -> PM | V151 applied once after three-head alignment and clean Linux precheck. One actual scanner cycle was read with limit=1, persisted, duplicate-checked, and restart-reconstructed; postapply ALR ledger counts are `3/1/2/1/1` (artifact/source/ingest/watermark/edge), and authority counters remain zero. |
| P2-3 | SERVICE_RUNNING_ENGINE_NOTIFIER_DORMANT | PM -> E3 -> BB -> PM -> PA -> E1 -> E2 -> E4 -> QA -> PM | Fresh service-only E3/BB approved `alr_shadow`, 0600 DSN, and user listener. It is active and restart-reconstructed 64 new durable source cycles without duplicate or scanner mutation. Engine notifier source remains dormant: current engine Demo writer/bounded-probe/connector-write flags prohibit its restart under the hard no-order boundary. |
| P2-4 | DONE | PM -> QC -> MIT -> AI-E -> PA -> E1 -> E2 -> E4 -> QA -> PM; PM -> E3 -> BB -> PM | V152 and the source-head-pinned ALR service applied after a fresh R2 gate. One durable 32-cycle scanner recurrence/novelty statistical run produced LearningTarget, research-only PIT, experiment, challenger, and defer artifacts; it is `DEFER_EVIDENCE`, never a profit/proof/serving/promotion claim. Scanner count remained `79744`, source duplicates `0`, and authority maps/counters false/zero. |
| P2-5 | DONE | PM -> QC -> MIT -> E1 -> E2 -> E4 -> QA -> PM; PM -> E3 -> BB -> PM | V153 and the source-head-pinned service applied after a fresh gate. Missing canonical proof/reward inputs became one explicit `DEFER_EVIDENCE` feedback record with a rotation edge, then the listener selected one next scanner-backed target. No proof/promotion/serving claim exists. |
| P2-6 | DONE | PM -> PA -> E1 -> E2 -> E4 -> QA -> PM; E3 -> BB -> PM | V154 adds ALR-owned rebuildable cache only. Disposable PostgreSQL proved quarantine -> grace/recheck -> sweep while retaining artifact/event lineage; production zero-entry apply has zero cache/events and grants UPDATE/DELETE only on that cache table. |
| P2-7 | DONE | PM -> PA -> E1 -> E2 -> E4 -> QA -> PM; PM -> E3 -> BB -> PM | V155 health ledger persists watermark, backlogs, target/run, evidence gaps, failure/recovery, retention, and authority counters. Production recorded one health snapshot with zero authority mismatches. |
| P2-8 | DONE | PM -> E3 -> BB -> QA -> PM | Closed Linux window reconciled five real post-baseline Rust scanner cycles exactly once (`5/5/0/0` raw/ALR/raw-only/ALR-only), survived two ALR-only starts, made two scanner-backed `DEFER_EVIDENCE` target decisions, and persisted zero-authority health. The temporary cursor drop-in was removed. An external engine restart after the closed window is a P3 revalidation input, not ALR authority. |
| P3-GATE | WAIT_OPERATOR_DEMO_AUTH | PM -> E3 -> BB -> PM -> Operator | Request emitted. A new source/runtime-bound candidate, side, order shape, window, loss control, Decision Lease, and rollback must be approved atomically. The historical NEAR reference is expired and cannot be consumed. |

## Shared Guards

- Scanner ranking, snapshots, and registry never become trade/proof authority.
- Every target/evaluation retains controls, negative cells, OOS, and lineage.
- No `_latest` reads or writes are accepted as ALR source authority.
- Any runtime mutation is preceded by a fresh source/runtime head alignment and a scoped E3/BB review; stale approvals do not carry forward.
