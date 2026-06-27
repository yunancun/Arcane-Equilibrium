# Reconciler Flat Baseline Recovery Fix

## Status

`DONE_WITH_CONCERNS`

已把 runtime Guardian 卡在 reconciler drift 之後的 source bug 修掉並部署到 Demo runtime。這是 runtime/風控恢復路徑修復，不是交易決策或 admission proof。

## Root Cause

Runtime log 顯示在空倉狀態下，每 30s 反覆輸出：

- `baseline reseeded (staleness or empty) seeded=0 stale=false`

對照 source 後確認：`position_reconciler` 在 `baseline.is_empty()` 時直接 reseed 並 `continue`。當 baseline 空且 current 也空時，這不是需要播種的冷啟動真倉，而是乾淨驗證週期。舊邏輯讓 `evaluate_actions()` 永遠看不到 clean cycles，因此 reconciler-driven `CAUTIOUS` 可能在所有倉位已平後仍無法自然恢復。

## Source Change

- Code commit: `724c78b5a6c9213a60baa1c4a26633d55342d079`
- Changed files:
  - `rust/openclaw_engine/src/position_reconciler/mod.rs`
  - `rust/openclaw_engine/src/position_reconciler/tests.rs`
- Added helper: `should_reseed_baseline_before_classify(stale, baseline_empty, current_empty)`
- Policy:
  - stale baseline still reseeds.
  - empty baseline + non-empty current still reseeds to avoid cold-start orphan storm.
  - empty baseline + empty current now reaches classification/action evaluation as a clean cycle.

## Verification

- Local: `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine position_reconciler::tests -- --nocapture`
  - Result: `56 passed`
- Local: `git diff --check`
  - Result: pass
- Runtime: `/home/ncyu/.cargo/bin/cargo test --manifest-path rust/Cargo.toml -p openclaw_engine position_reconciler::tests -- --nocapture`
  - Result: `56 passed`

## Runtime Sync / Deploy

- Runtime source sync manifest: `/tmp/openclaw/runtime_source_sync_reconciler_flat_baseline_recovery_20260627T063619Z/runtime_sync_manifest.json`
- Runtime source sync manifest sha: `1a067cb916912f6c898d69f162c0f6ffefd2e143c1a4fcf5a4c9115bdcb63c77`
- Runtime fast-forward: `d0c04983170a3dfd07b365168e4a31a66c38e510 -> 724c78b5a6c9213a60baa1c4a26633d55342d079`
- Crontab expected-head pins: old `5 -> 0`, new `0 -> 5`, line count `70 -> 70`
- Runtime deploy manifest: `/tmp/openclaw/runtime_deploy_reconciler_flat_baseline_recovery_20260627T064435Z/runtime_deploy_manifest.json`
- Runtime deploy manifest sha: `5b7990faac0574e3b5dc46e30eac66c9396fe3d14889fcb89bc19cb52cc851d2`
- Release binary sha: `4c36195d3f0b9b3dbee9888fe257be76dbc4620d883f213e3e5d7a3794d556ea -> 826a2fe8cfb580c371cf3cd8d74b6de80651ba15a16981e4d4e47168f1ebfb9a`
- Engine restart: `2432529 -> 3795702`
- API PID unchanged: `3727506`
- Watchdog PID unchanged: `1538268`

First deploy attempt failed before restart because non-login shell PATH lacked `cargo`; second attempt used `/home/ncyu/.cargo/bin` and completed.

## Runtime Evidence

- Pre-sync governance snapshot: `/tmp/openclaw/reconciler_flat_baseline_recovery_pre_sync_20260627T063551Z/runtime_governance_snapshot.json`
- Pre-sync governance snapshot sha: `0e015e15ddd9ff47af5ece18e641a788407ea820be6289eef945831b062dd11a`
- Pre-sync state: Guardian `CAUTIOUS`, multiplier `0.7`, `lease_live_count=0`, `oms_active_count=0`
- Post-deploy governance snapshot: `/tmp/openclaw/reconciler_flat_baseline_recovery_post_deploy_20260627T064233Z/runtime_governance_snapshot.json`
- Post-deploy governance snapshot sha: `3787c521661600c160164b62a8cacfa83354c43e051ad348b3605a422cbba673`
- Post-deploy state: Guardian `NORMAL`, multiplier `1.0`, `lease_live_count=0`, `oms_active_count=0`
- Post-deploy log check: warmup seeded `0`; no `baseline reseeded (staleness or empty)` tail; no `reconcile drift detected` tail.

The post-deploy `NORMAL` state is recorded as restart-after-deploy state only. It is not admission proof and does not clear the need for a fresh active current-candidate Demo Decision Lease plus fresh proposed-sizing/admission gate evidence.

## Session State

- Session state: `/tmp/openclaw/session_loop_state_20260627T064435Z_reconciler_flat_baseline_recovery_fix/session_loop_state.json`
- Session state sha: `1960d3166ed6f997d129b67906d535e350252cde065f90cdd033e4478835f8a1`
- State transition: `DONE_WITH_CONCERNS`

## Boundary

No order/cancel/modify, Decision Lease acquire/release, PG write, Cost Gate change, risk expansion, live/mainnet authority, writer/adapter enablement, or profit proof occurred. The only runtime mutation was Demo engine source sync, release rebuild, and engine-only restart.

## Next

Do not use post-restart Guardian `NORMAL` alone as admission evidence. Next admissible progress is a fresh active current-candidate Demo Decision Lease plus fresh GUI-derived proposed-sizing/Guardian gate evidence, then actual-admission BBO and audit/reconstructability review before any bounded Demo order.
