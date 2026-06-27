# Bounded Probe Caller False Positive Guard

## 結論

本輪把 current-candidate `grid_trading|AVAXUSDT|Sell` 的下一步從「可準備 order-capable runtime invocation」重新收斂為 `BLOCKED_BY_RUNTIME`。

原因：Rust active order draft / dispatch seam 存在，但 runtime writer 目前只把 eligible reject 寫成 admission/placement evidence；實際 `build_runtime_admission_record(...)` 的 runtime caller 仍傳入 `None` 作為 `active_order_request`。因此 readiness scanner 先前會把 draft seam 誤讀成 runtime caller readiness。

## 變更

- Source commit `b26dc76ed94074d9d8b95a0b689e82140621574d` 更新 `bounded_probe_authority_patch_readiness.py`。
- 新增 scanner 規則：除 active order seam 與 env gate 外，還必須存在 runtime call site 供應非 `None` 的 `active_order_request`。
- Regression 更新 current repo 預期：`active_order_submission_ready=true` 但 `active_caller_source_ready_for_review=false`。

## Runtime Evidence

- Runtime source synced to `b26dc76ed94074d9d8b95a0b689e82140621574d`.
- Crontab expected-head pins: old `502463a9...` occurrences `0`, new `b26dc76e...` occurrences `11`, line count `70`.
- Runtime sync manifest: `/tmp/openclaw/rt_sync_bpcfp_110040Z/runtime_sync_manifest.json`
  - sha256 `e6b48b7415223ea3d255ba441aa568363bd2d7e933d0aac2089fe58b2b091b12`
- Runtime readiness artifact: `/tmp/openclaw/current_candidate_bounded_probe_caller_false_positive_guard_20260627T110131Z/bounded_probe_authority_patch_readiness_runtime_after_supplier_guard.json`
  - sha256 `b04b9c355471aafac7d2299634444a2eb3e4694e08e1b07b0f8528dbebfa4336`
  - `status=AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`
  - `active_order_submission_ready=true`
  - `active_caller_source_ready_for_review=false`
  - `runtime_active_order_request_supplier_present=false`
  - `runtime_admission_propagation_ready_for_e3_bb_review=false`
- Session state: `/tmp/openclaw/current_candidate_bounded_probe_caller_false_positive_guard_20260627T110131Z/session_loop_state.json`
  - sha256 `0955ce0e81d84b09d71f8d41a5085f5479362bd06e525f7c597c56c68b1e0fee`
  - `status=BLOCKED_BY_RUNTIME`

## Verification

- Local focused scanner tests: `36 passed`
- Local adjacent suite: `73 passed`
- Runtime adjacent suite: `73 passed`
- `python3 -m py_compile ...bounded_probe_authority_patch_readiness.py ...test_cost_gate_bounded_probe_authority_patch_readiness.py`: passed locally and on runtime
- `git diff --check`: passed locally and on runtime
- Runtime API/watchdog remained active; no service restart.

## Boundary

No order/cancel/modify, no Bybit private/order call, no PG write, no service restart, no Cost Gate lowering, no risk expansion, no writer/adapter enablement, no live/mainnet action, and no profit proof.

Next action: implement or explicitly review a runtime active-order request supplier before any order-capable Demo invocation. After that, rerun the same-window Decision Lease, Guardian, Rust authority, actual BBO, GUI cap, book cleanliness, auditability, and reconstructability checks.
