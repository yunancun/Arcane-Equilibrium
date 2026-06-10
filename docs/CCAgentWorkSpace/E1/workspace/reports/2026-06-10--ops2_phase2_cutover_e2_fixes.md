# E1 IMPL — OPS-2 Phase-2 cutover E2 退回三項修復

**Date**: 2026-06-10
**Branch/worktree**: `fix/ops2-phase2-cutover` @ `/tmp/wt-ops2-cutover`（off main `28e376c0`）
**Commit**: `cf1b9320`（疊在 `a3d27729` 上的**新 commit**，未 amend——審查軌跡保留；NOT pushed / NOT merged）
**Status**: E1 IMPLEMENTATION DONE — 待 re-E2（預期快速 PASS，後續鏈 §13.3：CC → BB → PM）
**E2 依據**: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-06-10--ops2_phase2_cutover_review.md`（RETURN：1 HIGH + 1 MEDIUM + 1 LOW）

---

## 任務摘要

修復 E2 對 cutover commit `a3d27729` 的退回三項。全部機械修復、E2 已精確定位行號與修法，嚴格按清單執行未擴 scope。3 檔 +11/−7。

## 修改清單

| # | 嚴重性 | 檔:行 | 修復 |
|---|---|---|---|
| 1 | HIGH | `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_promote_api.py:574` | `"OPENCLAW_IPC_SECRET": secret` → `"OPENCLAW_LIVE_AUTH_SIGNING_KEY": secret`（+2 行中文注釋說明 cutover 後 IPC secret 無 fallback 作用）。grep 證該檔唯一 env-key 注入點（E2 斷言複核屬實） |
| 2 | MEDIUM | `rust/openclaw_engine/src/live_authorization.rs:285,287,316,334` | `compute_signature`/`verify_in_memory` 參數 `ipc_secret: &str` → `live_auth_signing_key`（4 處：兩簽名 + 兩函數體引用）。spec §4.1.1 Phase 2 欄指名 rename |
| 3 | LOW | `helper_scripts/fresh_start.sh:79-83` | 陳舊註釋「若 file 缺 → engine 走 Phase 1 fallback path」改 Phase-2 語義：缺 key → live 拒 spawn（log kind `live_auth_signing_key_missing`）/ Python sign raise；operator 走 runbook §13.5 seed 或 §5.2.2 urandom。comment-only 中文，`bash -n` 過 |

## 關鍵 diff

```rust
// live_authorization.rs（4 處 rename，行為零改動）
-pub fn compute_signature(auth: &LiveAuthorization, ipc_secret: &str) -> String {
+pub fn compute_signature(auth: &LiveAuthorization, live_auth_signing_key: &str) -> String {
-    let mut mac = HmacSha256::new_from_slice(ipc_secret.as_bytes())
+    let mut mac = HmacSha256::new_from_slice(live_auth_signing_key.as_bytes())
...
-    ipc_secret: &str,            // verify_in_memory 參數
+    live_auth_signing_key: &str,
-    let expected_sig = compute_signature(auth, ipc_secret);
+    let expected_sig = compute_signature(auth, live_auth_signing_key);
```

```python
# test_strategist_promote_api.py:572-577
             ), patch.dict(os.environ, {
                 "OPENCLAW_SECRETS_DIR": str(secrets_root),
-                "OPENCLAW_IPC_SECRET": secret,
+                # OPS-2 Phase 2 cutover：授權驗證 key 改讀
+                # OPENCLAW_LIVE_AUTH_SIGNING_KEY（IPC secret 已無 fallback 作用）。
+                "OPENCLAW_LIVE_AUTH_SIGNING_KEY": secret,
             }), patch(
```

**Finding-2 caller 確認**：唯一外部 caller `live_auth_watcher_tests.rs:179` = `compute_signature(&auth, TEST_SECRET)` 位置實參 → rename 零影響零改動（E2 預判一致）。檔內殘餘 `ipc_secret` 字串 6 處（:114/:220/:749/:761/:803/:988）全為 IPC-transport 域概念引用（comment / 負向測試名 `ipc_secret_alone_no_longer_provides_signing_key` 等），非參數殘留，按 E2 軸 1 結論保留。

## 測試結果（E2 升級 SOP 全照做）

| 驗證 | 結果 |
|---|---|
| Rust full `cargo test -p openclaw_engine --no-fail-fast` | **43 targets，4155 passed / 0 failed**。`stress_tick_latency_benchmark` 本輪綠（上輪紅 1038μs vs 1000μs）= 非確定性 perf flake 再證；4154+1=4155 與 E2 親跑數字自洽。log `Compiling openclaw_engine` 確認 rename 已真編譯 |
| Rust targeted | lib live_authorization **24/24**；bin `ops2_phase2_cutover_tests` **3/3**；watcher **12/12**（採 E2 校正計數） |
| Python 全套 HEAD（修後） | `pytest tests/ --ignore=tests/replay` = **66 failed / 4256 passed / 6 skipped** |
| Python 全套 base（`28e376c0` 臨時 worktree `/tmp/wt-ops2-base`，同 venv，跑畢已移除） | **66 failed / 4255 passed / 6 skipped**（passed 差 1 = cutover commit 本身淨增 1 測試，非回歸軸） |
| **base-vs-HEAD FAILED 清單 diff** | 兩側各 66 條 `^FAILED` sort 後 **diff = 空**（逐條一致）。Finding-1 新紅 `TestApplyLiveGateChain::test_live_apply_all_gates_green_succeeds` 消失，0 新增回歸 |
| 點名檔 | `test_strategist_promote_api.py` **18/18**（含先前紅的 gate-chain 測試） |

venv = `venvs/mac_dev`（Python 3.12.13）。66 紅 = Mac 環境既有（PG/engine.sock 缺，CLAUDE §六），與 E2 base 記錄一致。

## 治理對照

- 硬邊界 0 觸碰（max_retries / live_execution_allowed / execution_authority / system_mode）；Finding-2 為純 rename 行為零改動（HMAC 計算逐字節不變，cross-lang pinned fixture 測試在 full run 內綠）。
- 0 migration / 0 新 singleton / 0 硬編路徑；新注釋全中文；0 scope 擴張（worktree porcelain 僅 3 目標檔）。
- 主 checkout `/Users/ncyu/Projects/TradeBot/srv` 代碼未動（僅按完成序列寫 E1 memory/report）。

## 不確定之處

- 無實質。三項皆 E2 精確定位的機械修復，全部按清單執行並驗證。
- （非本輪）E2 advisory A1-A4 屬 PA/PM 域（runbook §13.4/§13.5 措辭校準等），未動。

## Operator 下一步

1. re-E2（E2 預期快速 PASS）→ §13.3 鏈 CC → BB → PM。
2. 部署前 gate 不變（已在 `a3d27729` commit body）：runbook §13.2 外部 alert rule 加新 kind 字串；merge + Linux `--rebuild` operator-gated。
