# 2026-06-27 -- GUI Active Supplier Runtime Sync

## Summary

State transition: `DONE_WITH_CONCERNS`.

This checkpoint synced the GUI-derived active bounded-probe supplier source to the Linux runtime checkout and updated runtime crontab expected-head pins. It did not rebuild or restart the running engine binary and did not enable any order path.

## Runtime Sync

- Runtime host: `trade-core`
- Runtime repo: `/home/ncyu/BybitOpenClaw/srv`
- Old runtime head: `a1b19a82460f1e4febdc5a7c62c117af996a4c6e`
- New runtime head: `b3a71ccd040e8b720eb8beba8d8c6d23d6777667`
- Sync method: `git merge --ff-only origin/main`
- Runtime worktree after sync: clean, `HEAD == origin/main`

Crontab expected-head pins:

- line count: `70 -> 70`
- old full-SHA occurrences: `11 -> 0`
- new full-SHA occurrences: `0 -> 11`

Runtime sync manifest:

- `/tmp/openclaw/rt_sync_gui_active_supplier_source_ready_20260627T115126Z/runtime_sync_manifest.json`
- sha256 `53c53cd8226778a3b9ef3c988ea34960838876d18007a4f57d9b79f501be46c2`

## Runtime Verification

On `trade-core` after sync:

- `python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py`
  - `37 passed`
- Adjacent GUI-cap/supplier Python suite
  - `87 passed`
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/bounded_probe_authority_patch_readiness.py`
- `git diff --check`

Services remained active:

- `openclaw-trading-api.service`: `active`
- `openclaw-watchdog.service`: `active`

Linux `cargo` was intentionally not run in this checkpoint.

## Runtime Readiness Artifact

Timestamped runtime-synced readiness:

- JSON: `/tmp/openclaw/gui_active_supplier_runtime_synced_readiness_20260627T115211Z/bounded_probe_authority_patch_readiness_runtime_synced.json`
  - sha256 `a3b9be3d067ee853ff1c24d0d30f129e7b38182877aa535f46427f2e45473f99`
- Markdown: `/tmp/openclaw/gui_active_supplier_runtime_synced_readiness_20260627T115211Z/bounded_probe_authority_patch_readiness_runtime_synced.md`
  - sha256 `165abf3b5962fd89c3ef70411503d14ad4b57a4939e3691f9d247ec759d3f855`

Important fields:

- top-level `status=AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`
- active caller `status=ACTIVE_CALLER_SOURCE_READY_FOR_E3_BB_REVIEW`
- `runtime_active_order_request_supplier_present=true`
- missing supplier contract fields `[]`
- suspicious hardcoded local `10 USDT` matches `[]`
- `allowed_to_submit_order=false`

Session state:

- `/tmp/openclaw/session_loop_state_20260627T1153Z_gui_active_supplier_runtime_sync.json`
- sha256 `7f2a5c592a73ccab164caebefbda4e0d21bcdcc1805d1ba4c15c2f7f47b02519`
- status `DONE_WITH_CONCERNS`

## Risk Semantics

GUI/Rust RiskConfig remains the source of truth:

- GUI `P1 Risk/Trade=10.0%` is Rust `per_trade_risk_pct=0.1`, not `10 USDT`.
- GUI `Max Single Position=25%` is Rust `position_size_max_pct=25.0`.
- Any order-capable request must resolve cap from accepted Demo equity plus GUI/Rust RiskConfig and preserve Decision Lease, Guardian, Rust authority, auditability, and reconstructability gates.

## Boundaries

No release rebuild, no service restart, no writer/adapter enablement, no Bybit call, no PG write, no order/cancel/modify, no Cost Gate lowering, no risk expansion, no live/mainnet action, no execution, no fill, no PnL, and no profit proof occurred.

## Next Blocker

Before any order-capable Demo action:

1. Perform reviewed release rebuild/restart.
2. Prove post-restart pending-order reconciliation and book cleanliness.
3. Submit source-ready supplier to E3/BB enablement review.
4. Revalidate same-window Decision Lease, Guardian, Rust authority, actual BBO, GUI cap, auditability, and reconstructability gates.
