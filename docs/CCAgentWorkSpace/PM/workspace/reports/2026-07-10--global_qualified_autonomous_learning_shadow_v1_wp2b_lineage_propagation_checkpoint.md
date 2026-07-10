# GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 — WP2-B Lineage Propagation Checkpoint

Date: 2026-07-10
Owner: PM
State: `ACTIVE_WP2B_COLD_EVALUATION_BOARD_V2`
Source checkpoint: `38ccd014c5ce974fbd395625b9597e12832395ee`
Gate status: G2 `PARTIAL_SOURCE_ACCEPTED`

## Acceptance

WP2-B B2.2a validated-lineage propagation is source accepted. Mac and
`origin/main` matched the full checkpoint SHA at acceptance. The accepted
source preserves a valid prospective `candidate_event_context_v1` losslessly
across this path:

```text
raw reject event -> admission decision -> JSONL ledger -> blocked outcome
```

The adapter binds the outer event to the raw context using exactly seven
semantic fields:

| Outer field | Context field |
|---|---|
| `strategy_name` | `strategy_name` |
| `symbol` | `symbol` |
| `side` | `side` |
| `context_id` | `context_id` |
| `signal_id` | `signal_id` |
| `engine_mode` | `evidence_engine_mode` |
| `ts_ms` | `captured_at_ms` |

There are no aliases, trimming, case normalization, type coercion, timestamp
fallback, or field backfill. Missing or grafted outer bindings, invalid event
hashes, and conflicting summary copies fail closed. A valid context is copied
without enrichment and retains its exact `event_hash` through the blocked
outcome.

## Provenance and historical treatment

Only a row explicitly marked with exact `explicit_source_rows` provenance may
carry prospective context through the reject materializer. PostgreSQL
`learning.decision_features`, pipeline-snapshot recent intents, and unmarked
historical rows cannot carry or reconstruct the context. Newly materialized
contextless rows are explicitly labeled
`candidate_event_context_status=UNQUALIFIED_CONTEXT_MISSING`; legacy
contextless ledger rows retain their old shape.

No `candidate_evaluation_context` or
`candidate_learning_context_projection` is synthesized in this slice. The
shared canonical fixture now includes a complete valid event context that is
parsed into the typed Rust contract and checked against its canonical hash.

Production code in `candidate_board.py`, `outcome_writer.py`, and
`price_observations.py` was unchanged. The already-existing generic outcome
transport is what preserves the validated candidate summary; this checkpoint
does not claim a new outcome-writer implementation.

## Gate evidence

- E1 focused Python: `220 passed, 1 skipped`; the skip was pre-existing.
- E2 found one P1 provenance bypass, E1 closed it, and E2's final finding count
  was P0/P1/P2 `0/0/0`.
- Replacement E4 Python: `303 passed, 1 skipped`.
- Replacement E4 targeted typed Rust fixture: `1 passed`.
- Root targeted Rust candidate-event-context module: `10/10 passed`.
- QA executed `41/41 passed` and returned
  `PASS_SOURCE_CHECKPOINT_TO_PM`.

The accepted commit changes three production modules and five contract/test
artifacts. It does not change candidate-board, outcome-writer, or
price-observation production code.

## Boundaries and freshness

This is source acceptance only. No Linux, service, PostgreSQL, Bybit, order,
probe, Decision Lease, Guardian, RiskConfig, global Cost Gate, training,
serving, promotion, retention, or authority action occurred. No runtime,
data-freshness, training, model, serving, promotion, or profit fact was
refreshed.

The last accepted Linux checkout and `openclaw-alr-shadow.service` pin remains
the historical WP1 target
`7d1c247947f0fb6c139f8a0583c5e6ed6ae62c70`. It is not evidence that B2.2a is
deployed or active in runtime.

## Next safe action

Proceed with B2.2b as a distinct source/test scope:

1. explicitly attach a validated cold `candidate_evaluation_context_v1` to the
   accepted prospective event context;
2. version the candidate-board schema and arbiter input to v2 so strict lineage
   eligibility cannot silently alter the v1 contract;
3. only after that, implement the restart-safe event-driven primary handoff.

Cron remains reconciliation only. B2.2b grants no runtime, exchange, order,
training, serving, promotion, or parameter-apply authority.
