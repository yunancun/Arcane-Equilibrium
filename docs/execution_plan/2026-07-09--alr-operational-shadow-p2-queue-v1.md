# ALR Operational Shadow P2 Queue v1

Date: 2026-07-09
Authority: `TODO.md` controls the live status of this workstream. This file pins the versioned acceptance contract and is not a replacement queue.
Boundary: ADR-0049 and AMD-2026-07-09-02.

## Completion Rule

The only normal P2 terminal state is `DONE_OPERATIONAL_SHADOW`. It requires all rows below, including a Linux shadow soak. `DEFER_EVIDENCE`, an empty backlog, a source-only completion marker, and `model_training_performed=false` are not terminal states.

| ID | Status | Owner chain | Acceptance |
|---|---|---|---|
| P2-0 | DONE | PM -> CC -> FA -> PA -> PM | ADR/AMD, root TODO import, and this versioned queue establish the operational boundary without granting trading authority. |
| P2-1 | ACTIVE | PM -> PA -> E1 -> E2 -> E4 -> QA -> PM | Read `trading.scanner_snapshots` as the Rust scanner source through `(ts, scan_id)`, canonical hash, watermark, and fail-closed schema validation; do not mutate scanner. |
| P2-2 | WAITING_P2-1 | PM -> PA -> E1 -> E2 -> E4 -> QA -> PM; E3 -> BB -> PM before apply | Append-only `learning.alr_*` migration and repository prove idempotency, duplicate handling, crash/restart recovery, and provenance graph. |
| P2-3 | WAITING_P2-2 | PM -> PA -> E1 -> E2 -> E4 -> QA -> PM | User-level event/backlog/novelty consumer has backpressure, resource budget, one-instance lock, graceful shutdown, and fail-closed recovery; no cron or fixed learning scheduler. |
| P2-4 | WAITING_P2-3 | PM -> QC -> MIT -> AI-E -> PA -> E1 -> E2 -> E4 -> QA -> PM | LearningTarget -> PIT dataset -> existing training/statistical pipeline -> after-cost evaluation -> challenger artifact with no serving/promotion. |
| P2-5 | WAITING_P2-4 | PM -> QC -> MIT -> E1 -> E2 -> E4 -> QA -> PM | ProofPacket/RewardLedger feedback records gaps, rotates on `DEFER_EVIDENCE`, and never treats missing evidence as proof. |
| P2-6 | WAITING_P2-2 | PM -> PA -> E1 -> E2 -> E4 -> QA -> PM; E3 -> BB -> PM before sweep | Reference graph -> quarantine -> grace/recheck -> sweep deletes only ALR-owned rebuildable unreferenced derived cache. |
| P2-7 | WAITING_P2-3 | PM -> PA -> E1 -> E2 -> E4 -> QA -> PM | Health/state/metrics expose watermark, backlog, target, runs, evidence gaps, failures, restart recovery, retention bytes, and all authority counters. |
| P2-8 | WAITING_P2-2..7 | PM -> E3 -> BB -> QA -> PM | Linux shadow soak consumes at least three real new scanner cycles, survives restart, suppresses duplicates, makes a target decision, and keeps authority counters at zero. |
| P3-GATE | BLOCKED_UNTIL_P2_COMPLETE | PM -> E3 -> BB -> PM -> Operator | Emit a bounded Demo authorization request with candidate, side, order shape, window, loss control, Decision Lease, and rollback. Stop at `WAIT_OPERATOR_DEMO_AUTH`. |

## Shared Guards

- Scanner ranking, snapshots, and registry never become trade/proof authority.
- Every target/evaluation retains controls, negative cells, OOS, and lineage.
- No `_latest` reads or writes are accepted as ALR source authority.
- Any runtime mutation is preceded by a fresh source/runtime head alignment and a scoped E3/BB review; stale approvals do not carry forward.
