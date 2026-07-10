# PM Source Checkpoint - GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 WP2-A

Date: 2026-07-10
Code checkpoint: `c84e14f5de67f8a6e55d3759d307087323118f86`
Status: `WP2A_DONE_SOURCE_ACCEPTED_PROVISIONAL_BRIDGE`
Goal status: `ACTIVE_WP2B_PROSPECTIVE_EVENT_LINEAGE`

## Accepted source effect

WP2-A is source-accepted under the candidate-selection semantics and
`PA -> E1 -> E2 -> AI-E -> E4 -> QA -> PM` gates.  The source now builds a
typed candidate board from blocked-signal outcomes, keeps target-regime
evaluations distinct from the stable family used for cooldown, and adjudicates
R3 candidates with distinct-entry sufficiency, day concentration, hidden OOS,
proof gap, EVI, explicit resource budgets, economic cost, portfolio context,
and deterministic tie-breaking.  Missing or invalid policy, identity,
resources, portfolio, hidden-OOS, or lineage fails closed.

The board/policy rendezvous uses immutable stamped files, canonical hashes,
secure same-file reads, non-replacing publication, destination-scoped locking,
monotonic timestamps, bounded count/byte retention, and directory durability.
There is no mutable `_latest` alias.  Missing policy or no qualified candidate
persists a durable repair/no-candidate decision while the long-lived listener
continues.

A true active source chain was exercised:

```text
outcome review
  -> stamped candidate-board publisher
  -> bounded evidence adapter
  -> active event-consumer operational cycle
  -> candidate-learning projection
  -> real operational repository
```

Candidate logic was not mocked.  Only PostgreSQL connectivity and unrelated
feedback/retention/health boundaries were mocked.  The chain created no
training run, used no statistical-training fallback, and left every order,
probe, exchange, serving, promotion, Guardian, Decision Lease, Rust-authority,
and global Cost Gate claim false or zero.

## Verification

- Integrated focused and adjacent suite: `458 passed`.
- Cron static bridge suite: `17 passed`.
- Publisher, policy, and true full-chain focused rerun: `35 passed`.
- True full-chain rerun: `5 passed`.
- `py_compile`, cron `bash -n`, intended-scope `git diff --check`: PASS.
- E2: PASS, P0/P1/P2 `0/0/0`.
- AI-E final source recheck: PASS, P0/P1/P2 `0/0/0`.
- E4: `PASS_TO_QA`, P0/P1/P2 `0/0/0`.
- QA: `PASS_SOURCE_CHECKPOINT_TO_PM`, P0/P1/P2 `0/0/0`.

## Boundary and next dispatch

This is not a runtime or Goal-terminal checkpoint.  No Linux, PostgreSQL,
Bybit, network, service, cron installation, order, probe, training, serving,
promotion, or protected-evidence action occurred.  Mac and origin matched at
the source checkpoint.  The last accepted WP1 Linux and ALR-service target was
`7d1c247947f0fb6c139f8a0583c5e6ed6ae62c70`; WP2-A did not inspect or mutate
runtime.

The cron publisher is a provisional cold reconciliation bridge only.  It does
not prove event-driven primary behavior.  WP2-B is active and must first
extract candidate-board construction behind a narrow Interface/Adapter with
byte-identical output and hashes.  It must then add immutable Rust
`candidate_event_context_v1`, cold Python `candidate_evaluation_context_v1`,
and a restart-safe event-driven primary handoff.  Legacy recovery rows without
event-time identity remain R3-ineligible; current HEAD/config must never be
used as historical backfill.
