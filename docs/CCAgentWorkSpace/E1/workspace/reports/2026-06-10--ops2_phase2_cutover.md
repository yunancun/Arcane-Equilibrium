# E1 IMPL — OPS-2 secret-split Phase 2 cutover

**Date**: 2026-06-10
**Branch/worktree**: `fix/ops2-phase2-cutover` @ `/tmp/wt-ops2-cutover`（off main `28e376c0`）
**Commit**: `a3d27729`（on branch，NOT pushed / NOT merged — operator-gated）
**Status**: E1 IMPLEMENTATION DONE — 待 E2 審查（後續鏈 per runbook §13.3：CC review + BB sign-off + PM approve）

---

## 任務摘要

D+14 soak 達成（PM 已驗：Linux engine.log + api.log `grep -c ops2_secret_split_phase1_fallback` = 0，含 06-03/06-07/06-08 三次全量重啟）→ 依 runbook `docs/runbooks/credential_rotation.md` §13.3 + spec `docs/execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md` §3.2 移除 Phase 1 legacy fallback 與陳舊 panic/reason 變體。cutover 後新 env 缺失 = **fail loud**（Rust 啟動 panic / Python sign raise / verify 回新 reason），不靜默退回 `OPENCLAW_IPC_SECRET`。

## 修改清單（9 檔，+365/−306）

| 檔 | 改動 |
|---|---|
| `rust/openclaw_engine/src/live_authorization.rs` | `read_live_auth_signing_key` 純讀 `OPENCLAW_LIVE_AUTH_SIGNING_KEY`（刪 fallback 分支 + `FALLBACK_WARN_INTERVAL_SECS` + `LAST_FALLBACK_WARN_TS` + `tracing::warn`/atomic import）；刪 `AuthError::IpcSecretMissing` 變體 + Display arm + `auth_error_kind` `"ipc_secret_missing"` arm；`BadSignature` / `sig` 欄位文案對齊新 key 名；tests 同步（刪 1 fallback 測試、新增 IPC-only→None 負向、missing-variant 測試強化為「legacy IPC 在也救不了」、雙 set 清理） |
| `rust/openclaw_engine/src/main.rs` | 新 helper `enforce_live_auth_signing_key_or_panic` + 呼叫點緊跟 FIX-10 IPC panic（LiveAuthWatcher spawn 之前，spec §9.5）；新 `#[cfg(test)] mod ops2_phase2_cutover_tests` 3 測試（含 runbook §13.4 指名 `live_auth_signing_key_missing_panics_when_live`，catch_unwind + env restore 確定性） |
| `rust/openclaw_engine/src/live_auth_watcher_tests.rs` | `set_test_env`/`clear_test_env` 只 set/clear `OPENCLAW_LIVE_AUTH_SIGNING_KEY`（runbook §13.3「不再雙 set」） |
| `.../app/live_trust_routes.py` | `_read_live_auth_signing_key` 純讀新 env（刪 fallback + `_fallback_warn_state` rate-limit）；sign 路徑 RuntimeError 文案更新（不再提 Phase 1 fallback）；verify 路徑 reason `ipc_secret_missing` → `live_auth_signing_key_missing`（:473 rename，對齊 Rust kind）；touched 區 local `ipc_secret` → `signing_key` |
| `.../app/live_preflight.py` | 陳舊 Phase-1 fallback 錯誤訊息 + docstring 對齊新語義（**runbook §13.3 未列此檔**——P1-01 後新增的 caller，晚於 runbook；grep `_read_live_auth_signing_key` 全 caller 抓到） |
| `.../app/executor_routes.py` | 1 行 docstring「含 Phase-1 fallback」→「OPS-2 Phase 2 後無 IPC fallback」 |
| `.../tests/test_live_trust_routes_secret_split.py` | 重寫為 Phase 2：刪 3 個 fallback WARN 行為測試；新增 IPC-only→`""`、sign raise even-when-IPC-set（含「不留部分寫入授權檔」）、verify 端到端新 reason、fallback 機制移除斷言（hasattr 反證）；保留 cross-lang HMAC pinned fixture `1b2b18d7...78fc`（永久 invariant） |
| `.../tests/test_live_authorization_signing.py` | **collateral**：fixture 原只 setenv `OPENCLAW_IPC_SECRET`（吃 Phase 1 fallback）→ 7 測紅；換 `OPENCLAW_LIVE_AUTH_SIGNING_KEY` + 負向測試 rename `test_write_fails_without_live_auth_signing_key` |
| `.../tests/test_executor_shadow_toggle_api.py` | **collateral**：live-flip 5-gate 鏈 6 處 env 注入用 IPC 當 verify key → 2 測紅（all-gates-green / expired）；6 處全換 LIVE_AUTH key |

未動：`helper_scripts/restart_all.sh` seed 邏輯（runbook §13.5 rollback 依賴，§13.3 不在列）/ runbook 文檔（PA 域）/ TODO.md（PM 域）/ `verify_in_memory`/`compute_signature` 參數名 `ipc_secret`（見「不確定之處」）。

## 測試結果

- **Rust**：`cargo test -p openclaw_engine --no-fail-fast` = **4154 passed / 1 failed**。唯一失敗 `stress_tick_latency_benchmark`（tests/stress_integration.rs:982，1038μs vs 1000μs debug 閾值）= **既有 perf flake**：`git stash` 基線同樣紅（同 panic 同量級）→ 與本改動無關。targeted：lib live_authorization 24/24、bin ops2_phase2_cutover 3/3、watcher 15/15。
- **Python**（venvs/mac_dev 3.12.13）：受影響 5 檔 **62 passed / 0 failed**（secret_split 9 + signing 16 + recheck 7 + batchB 10 + toggle 20）。

## fail-loud 行為驗證方式

- Rust 啟動：`live_auth_signing_key_missing_panics_when_live`（panic message 含 `OPENCLAW_LIVE_AUTH_SIGNING_KEY`）+ 非 Live 不 panic + key 在不 panic。runtime 等價驗證 = runbook §13.4 sandbox cargo test one-liner（禁 production 直觸）。
- Rust 驗證路徑：`live_auth_signing_key_missing_returns_specific_variant`（**legacy IPC 設置也回 `LiveAuthSigningKeyMissing`**）+ `ipc_secret_alone_no_longer_provides_signing_key`。
- Python sign：`test_write_signed_live_authorization_raises_even_when_ipc_secret_set`（raise + 不留部分檔）。
- Python verify：`test_verify_status_reason_is_live_auth_signing_key_missing`（先簽後刪 key → `unverifiable` + 新 reason + `valid_for_engine=False`）。

## 治理對照

- 硬邊界 0 觸碰（max_retries / live_execution_allowed / execution_authority / system_mode）；fail-closed 語義強化非放鬆。
- 0 migration / 0 新 singleton / 0 硬編路徑；注釋中文；main.rs 1784 行（<2000 cap，>800 既有）。
- 5-gate #5（signed authorization）key 域分離完成：簽名 key 單一來源，IPC 純 transport。

## 不確定之處 / E2 重點

1. **spec §4.1.1 列了 `verify_in_memory`/`compute_signature` 參數 `ipc_secret: &str` → `live_auth_signing_key` rename（標 Phase 1），Phase 1 IMPL 沒做、runbook §13.3 也沒列** → 我不做只 flag（naming debt，pub fn 參數，需 PA/E2 決定是否補）。
2. toggle 測試 6 處注入我全換（非只失敗 2 處）：其餘 4 處僥倖綠是因 schema gate 先 trip，留 IPC 注入會誤導未來 gate-order 變更——E2 確認此 scope 判斷。
3. `stress_tick_latency_benchmark` 既有 flake 建議另開 follow-up（非本 PR）。

## Operator 下一步（部署前 gate）

1. runbook §13.2：外部 Grafana/journald alert rule 加 `live_auth_signing_key_missing` + `AuthError::LiveAuthSigningKeyMissing`（repo 內 grep 不到外部規則，必須 operator 親手）；舊字串留 14d buffer。
2. E2 → CC → BB → PM 鏈後 operator 拍 merge + Linux `--rebuild` 部署；§13.6 D+15~D+44 verify SOP；first urandom rotation due **2026-09-08**。
