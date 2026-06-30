# 2026-06-30 IBKR Stock/ETF IPC Readiness Allowlist Trace Checkpoint

VERDICT: PASS
CONFIDENCE: high

## Result

- Stock/ETF engine IPC readiness now exposes the source-only `non_bybit_api_allowlist_v1` verdict under `phase2.api_allowlist`.
- The readiness payload records exact allowlist `contract_id`, `source_version`, accepted verdict, blocker list, read/paper-write/denied action counts, `ibkr_contact_performed=false`, `secret_content_serialized=false`, and `bybit_live_execution_protected=true`.
- `phase2_ibkr_external_surface_gate_v1` still remains blocked because there is no immutable PASS artifact, no secret/topology evidence, and no first-contact authorization.
- Existing legacy `submit_paper_order` behavior remains unchanged and still uses the existing channel path.

## Boundary

- No IBKR contact, healthcheck, socket, connector construction, secret read/create/serialization, paper order, fill import, audit writer, DB apply, GUI authority, release, tiny-live, or live authority was added or exercised.
- No Bybit live execution behavior was changed.
- Linux `trade-core` runtime checkout was not touched or fast-forwarded.
- This is a Phase 1D source/runtime-fixture trace improvement only; it does not start Phase 2.

## Verification

- `rustfmt --edition 2021 --check rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs` - passed
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine ipc_server::tests::stock_etf`
  - `4 passed`
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`
  - `5 passed`
  - Existing unrelated warnings observed: `async_trait::async_trait` unused in `m3_emitter_replay_forbidden.rs`; `ScriptedSpawn` private-interface warning in `live_auth_watcher_tests.rs`.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_phase2_gate_acceptance --test stock_etf_lane_scoped_ipc_acceptance`
  - `18 passed`
- `cargo check --manifest-path rust/Cargo.toml --workspace`
  - passed
- `git diff --check`
  - passed

## Dispatch Note

Sub-agent E2 was not spawned because the available sub-agent tool policy allows spawning only when the user explicitly asks for sub-agents or parallel agent work. This checkpoint is narrow and source-only; local diff review plus focused engine/types tests covered the regression surface.

## Next Gate

Continue Phase 1 source-fixture/readiness hardening. Do not proceed to Phase 2 IBKR read-only contact until the immutable external-surface PASS artifact and real secret/topology evidence exist.
