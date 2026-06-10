# E4 Regression — OPS-2 Phase-2 cutover · `fix/ops2-phase2-cutover` · 2026-06-10

**被驗**：worktree `/tmp/wt-ops2-cutover`，commits `a3d27729`+`cf1b9320`（base main `28e376c0`）。E2 兩輪 ACCEPT 後全回歸。
**E4 新增**：+1 測試 commit `e34a8772`（見 §6）。
**VERDICT: PASS**（退 E1 清單：無）。

---

## 1. Test 結果（全部親跑）

| 引擎 | passed | failed | skipped | baseline（親測 base `28e376c0`） | delta |
|---|---|---|---|---|---|
| Python `pytest tests/ --ignore=tests/replay`（venvs/mac_dev 3.12.13 / pytest 9.0.3，control_api_v1） | **4257**（含 E4 +1；cf1b9320 時點 = 4256 ×2 runs） | **66**（pre-existing） | 6 | 66 failed / 4255 passed / 6 skipped | **+2 passed（+1 cutover 已記帳 / +1 E4）；failed ±0** |
| Rust `cargo test -p openclaw_engine --no-fail-fast`（43 targets，debug） | **4154** ×2 runs | **1**（`stress_tick_latency_benchmark`，見 §2） | 4 ignored | base 同測同紅（親驗 §2） | **total 4155 兩輪一致 = E1/E2 記錄；0 測試消失** |

跑兩遍：Python run1 == run2（66/4256/6，FAILED 清單 byte-identical）；Rust run1 == run2（4154/1/4，唯一紅同名同位）。非 flaky 漂移。

**66 紅 base 一致性**（任務要求抽 5 條，實做全量）：自建 throwaway worktree `/tmp/wt-ops2-base-e4` @ `28e376c0` 同 venv 全套親跑 → base FAILED 66 條 sort 後與 HEAD **整列 diff = 空**（非僅抽驗）。抽 1 條 probe 失敗模式：`test_post_demo_relock` = 403 Forbidden on write endpoint = documented Mac CSRF-enforcement-mode 環境 artifact（無 `OPENCLAW_CSRF_SHADOW=1`；F-NEW-1 既有 debt）。E1 的 diff 證明獨立複現屬實。

## 2. Rust stress flake 裁定（任務指定處理）

`stress_tick_latency_benchmark`（tests/stress_integration.rs:982，debug 閾值 <1000μs）兩輪 full run 皆紅（1135.5 / 1117.3μs）。裁定 = **環境性非回歸**，證據（全親跑，非沿用 E1 stash 證據）：
- 結構：PR 11 檔 **0 觸碰** stress 檔（`git diff --name-only | grep stress` = 0）。
- HEAD standalone ×3（低負載）：1059.3 / 1072.7 / 1068.0μs 全紅。
- **base `28e376c0` standalone ×3**（throwaway worktree 重編）：1076.1 / 1068.0 / 1072.9μs **全紅** —— base 在本機今日同樣破閾值，且 HEAD 值不劣於 base（均值 1066.7 vs 1072.3）→ tick path 零劣化。
- 跨 session 非確定性：E1 首輪紅(1038)/E2 紅/E1-fix 輪綠(<1000) 橫跨 base-HEAD 差 → session 噪音。
- 測試未刪未改；follow-up 已由 E1 flag（非本 PR）。

## 3. 測試數對賬（base → HEAD，名字級）

| 計數 | base | HEAD(cf1b9320) | +E4(e34a8772) | 分解 |
|---|---|---|---|---|
| Python `def test_`（control_api_v1/tests） | 4316 | 4317 (+1) | 4318 | secret_split 8→9（−4：3 fallback-WARN 刪 + 1 primary-wins rename；+5 新負向）；signing 13→13（1 rename）；toggle 20→20；promote 18→18 |
| Rust `#[test]`/`#[tokio::test]`（openclaw_engine） | 4186 | 4189 (+3) | — | main.rs 0→3（ops2_phase2_cutover_tests）；live_authorization 24→24（−2：`phase1_fallback_reads_ipc_secret_when_live_auth_unset` 刪 + `…primary_wins_over_ipc_fallback` rename；+2：`ipc_secret_alone_no_longer_provides_signing_key` + `…primary_read_ignores_ipc_secret`）；watcher 12→12 |

被刪測試**全部**為 Phase-1 fallback 行為測試（被移除功能的測試），且每條都有對應「fallback 已死」負向測試取代 ── 合法刪除類；**0 靜默消失**，與 commit body 記帳逐條一致。

## 4. Mock 審查（4 改動測試檔）

| Test 檔 | mock 內容 | 業務邏輯真跑? | 判定 |
|---|---|---|---|
| test_strategist_promote_api（gate chain） | `_fetch_latest_applied_row`(DB row) / `_get_global_mode_state`(mode 源) / `one_shot_ipc_call`(IPC sink) / env | **真**：靜態鏈 promote→`executor_routes._verify_live_gate`→Gate5→`live_preflight.verify_signed_authorization`→`ltr._read_live_auth_signing_key`；**mutation-bite 親驗**：reader 毒成 `""` → 測試紅 403 `gate_failed=authorization` + Phase-2 hint → 還原 byte-clean | PASS，非 mock 短路 |
| test_live_trust_routes_secret_split（重寫） | env(monkeypatch) + tmp_path 檔案 IO | 全測試直驅真 `_read_live_auth_signing_key`/`_write_signed_live_authorization`/`_read_signed_live_authorization_status`/`_sign_authorization_payload` | PASS |
| test_live_authorization_signing | fixture env rename + delenv 衛生（LIVE_AUTH_FILE/IPC/IPC_FILE 清）| assertion 零弱化；負向 rename 後 match 新 env 名 | PASS |
| test_executor_shadow_toggle_api | 6 處純 env-key 換名 | assertion 零改動；gate 鏈真跑 | PASS |

Rust ops2 3 測試直驅真 `enforce_live_auth_signing_key_or_panic` + `test_env_lock::guard()` + catch_unwind 確定性 env 還原（符 de32b27c 教訓）；call site 親驗已接線 main.rs:470（緊跟 FIX-10、watcher spawn 前）。

## 5. fail-loud 四象限 + 跨語言

| 象限 | 測試 | 結果 |
|---|---|---|
| Rust panic（live+缺 key） | `live_auth_signing_key_missing_panics_when_live`（panic msg 含 env 名） | 綠（×2 full + targeted 3/3） |
| Rust 非 live 不 panic | `…does_not_panic_when_not_live` + `…present_does_not_panic_when_live` | 綠 |
| Python sign raise | `…raises_when_both_envs_unset` + `…raises_even_when_ipc_secret_set`（含不留部分寫入） | 綠（named-run 親驗） |
| Python verify unverifiable | `test_verify_status_reason_is_live_auth_signing_key_missing` | 綠（named-run 親驗） |

Rust verify 路徑負向另有 `live_auth_signing_key_missing_returns_specific_variant`（legacy IPC 在也回 missing）+ `ipc_secret_alone_no_longer_provides_signing_key`（lib 24/24）。
**跨語言**：pinned HMAC fixture `1b2b18d7…78fc` —— Rust `cross_lang_hmac_fixture_is_byte_identical`（live_authorization.rs:697）+ Python `test_cross_lang_hmac_fixture_matches_rust_compute_signature`（同 payload/key/hex，真 `compute_signature`/`_sign_authorization_payload`）雙端綠 = 簽名語義零漂移。

## 6. E4 新增測試（1 條，commit `e34a8772`）

**缺口**：四象限單元層全鎖，但 gate-chain 層（GUI 真實路徑）負向只有 no-file/expired/schema；cutover 代表性失敗面「**授權檔有效 + 簽名 key env 缺失**」無永久測試（grep 全 tests/ 0 檔引用 live_preflight）——E2 Finding-1 正是在此 surface 顯形，卻只靠 collateral 修復間接覆蓋。
**新增**：`test_live_flip_signing_key_missing_403_authorization`（toggle 檔 gate-5 負向 cluster）：有效簽名授權檔 + key/_FILE 清除 + legacy IPC 故意在場 → 403 `gate_failed=authorization` + hint 含新 env 名（對齊 §13.2 alert 字串）。
**bite 親驗**：暫時重加 IPC fallback（Phase-1 回歸方向）→ 本測試紅（IPC 救活 gate）→ 還原綠、porcelain 僅測試檔。業務代碼 0 改動。

## 7. 結論

**PASS**。兩端數字複現 E1/E2 宣稱（Rust 4155 total 一致、Python 66/4256/6 + base 66/4255/6 全列 diff 空）；測試數對賬 0 靜默消失；mock 0 掩蓋（gate-chain mutation-bite 證真路徑）；四象限+跨語言 fixture 全綠；stress 紅 = base 同紅之環境 flake 非回歸。
**Owed（非 blocker）**：Linux full regression 隨 PM merge + `--rebuild` 部署 gate 補（Mac dev box；本 PR 無 migration/無 IPC schema 改）；origin/main 已前進至 L2 Mesh commits（E2 §5e 證 0 overlap），merge 後全套自然涵蓋。
下一步：§13.3 鏈 CC → BB → PM。

E4 REGRESSION DONE: PASS · report path: srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-06-10--ops2_phase2_cutover_regression.md
