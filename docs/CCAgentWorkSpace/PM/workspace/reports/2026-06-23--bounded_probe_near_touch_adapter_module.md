# Bounded Probe Near-Touch Adapter Module

## Summary

- Added source commit `0cc749db`: pure Rust `openclaw_engine::bounded_probe_near_touch`.
- The Module implements future bounded Demo probe placement math only; it does not read runtime plans, call Bybit, write ledgers, submit orders, lower Cost Gate, or grant probe/order authority.
- Updated `bounded_demo_probe_authority_patch_readiness_v1` so Adapter presence and tick-dispatch authority-path wiring are separate gates.

## PM Read

This is a Depth increase, not an authorization change. We now have a tested Implementation for the near-touch placement rule that v422 identified as missing, but source readiness still fails closed until the exchange dispatch path is explicitly wired under operator review.

Profitability path:

1. Keep global Cost Gate unchanged.
2. Concentrate bounded learning on side-cell/horizon candidates with blocked-signal edge evidence.
3. Use post-only near-touch-or-skip placement to make Demo attempts fill-capable without crossing the spread.
4. Record both `bounded_probe_attempt` and `bounded_probe_touchability_block` lineage.
5. Promote nothing until candidate-matched fill/fee/slippage, matched blocked controls, result review, and execution-realism review pass.

## Runtime Smoke

- Runtime source: Linux `trade-core` fast-forwarded clean to `0cc749db`.
- Canonical artifact: `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_authority_patch_readiness_latest.{json,md}`.
- Smoke generated: `2026-06-23T10:21:42.832275+00:00`.
- Status: `RUST_PATCH_REQUIRED_AUTHORITY_PATH_WIRING_MISSING`.
- Existing authority seams present: `true`.
- Near-touch Adapter present: `true`.
- Authority path wiring present: `false`.
- Probe/order authority granted: `false` / `false`.

## Verification

- Mac `python3 -m py_compile ...` passed.
- Mac bounded readiness focused tests: `7 passed`.
- Mac related bounded-probe suite: `18 passed`.
- Mac Rust focused test: `cargo test -p openclaw_engine bounded_probe_near_touch --lib` = `7 passed`.
- Linux py_compile passed.
- Linux related bounded-probe suite: `18 passed`.
- Linux Rust focused test with `/home/ncyu/.cargo/bin/cargo`: `7 passed`.

## Boundary

Source/test/docs + Linux source sync + canonical `/tmp/openclaw` artifact writes only. No CI run, no PG query/write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab install, no env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.
