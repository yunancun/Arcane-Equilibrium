# Cost-Gate Demo-Learning Lane Runtime Ledger Writer

## Summary

This batch wires an env-gated Rust runtime writer for the cost-gate demo-learning lane.

Eligible demo/live_demo cost-gate rejects can now become append-only `probe_admission_decision` JSONL learning evidence when the writer is explicitly enabled. The writer is disabled by default and cannot submit orders or grant order authority.

## Why

The demo no-order diagnosis showed that many useful signals die at the cost gate before order creation. Earlier batches created the counterfactual scorecard, bounded plan, Python adapter, Rust policy, admission ledger builder, outcome writer, and hot-path reject adapter.

The missing runtime piece was durable capture: once the Rust hot path recognizes an eligible rejected signal, it needs a non-blocking sink so the system can accumulate learning evidence instead of silently losing new rejects.

## Implementation

- Added `rust/openclaw_engine/src/demo_learning_lane_writer.rs`.
- Exported `openclaw_engine::demo_learning_lane_writer`.
- Spawned a global writer handle in `main.rs`.
- Wired the handle through `PipelineSpawnContext`, `EventConsumerDeps`, `bootstrap_runtime`, and `TickPipeline`.
- Added `TickPipeline::set_demo_learning_lane_writer`.
- `step_4_5_dispatch` now sends recognized eligible rejects to the writer handle.
- The writer is enabled only by `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1|true`.
- Default paths:
  - plan: `$OPENCLAW_DATA_DIR/cost_gate_learning_lane/demo_learning_lane_plan_latest.json`
  - ledger: `$OPENCLAW_DATA_DIR/cost_gate_learning_lane/probe_ledger.jsonl`
- Env overrides:
  - `OPENCLAW_DEMO_LEARNING_LANE_PLAN`
  - `OPENCLAW_DEMO_LEARNING_LANE_LEDGER`
- Producers use bounded `try_send`, so the tick path does not block on disk IO.
- The writer task loads the plan and ledger off hot path, evaluates the existing Rust admission policy, dedupes by `attempt_id`, appends one JSONL row, and flushes after successful writes.

## Guardrails

- Disabled by default.
- No PG writes or schema migration.
- No Bybit private/signed/trading call.
- No order submission.
- No main cost-gate relaxation.
- No runtime config mutation.
- No credential/auth/risk mutation.
- Writer enablement is not order authority.
- The writer passes `adapter_enabled=false` into admission evaluation, so even if a future plan grants order authority before an order bridge exists, this writer still cannot produce an allowed order decision.
- Current plan remains `order_authority=NOT_GRANTED`; matching selected side-cells record `ORDER_AUTHORITY_NOT_GRANTED`.

## Verification

- `cargo test -p openclaw_engine demo_learning_lane --lib` -> 19 passed.
- `cargo test -p openclaw_engine test_cost_gate_moderate --lib` -> 26 passed.
- `rustfmt --edition 2021 --check rust/openclaw_engine/src/demo_learning_lane_writer.rs` -> passed.
- `git diff --check` -> passed.

Note: broader rustfmt checks on legacy root/module files still surface pre-existing formatting drift outside this batch, so the formatting gate was limited to the new writer plus whitespace diff-check.

## Boundary

Source/test/docs only. No deploy, rebuild, restart, PG write, Bybit private/signed/trading call, order/risk/auth/runtime mutation, signal proof, execution proof, or promotion proof.

## Next

1. Operator-reviewed source sync/deploy/enable decision for `OPENCLAW_DEMO_LEARNING_LANE_WRITER`.
2. Runtime observation that eligible rejects append JSONL rows with `ORDER_AUTHORITY_NOT_GRANTED`.
3. Fill-backed outcome writer and edge-estimator feedback.
4. Only after outcome learning works should demo-only probe order authority be considered.
