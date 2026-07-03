# E4 Regression Test Report — Part 2 post-approval drift gate (IMPL-B, 未 commit) · 2026-07-03

被驗：`docs/execution_plan/2026-07-02--soak_dispatch_edge_containment_and_drift_gate_design.md` Part 2 實作（E2 鏈：2026-07-03 首輪 RETURN 2H+2M+2L → E1 修 → re-review APPROVE_WITH_NITS → 3 nits 已收）。HEAD=origin/main=`2a012deeb`（0/0）。全 Python-only。

受驗檔（md5 快照 2026-07-02T22:44Z）：
- 新 `helper_scripts/research/cost_gate_learning_lane/standing_envelope_post_approval_drift_gate.py`（untracked，695L，md5 `13a0f7d8`）
- 新 `helper_scripts/research/tests/test_standing_envelope_post_approval_drift_gate.py`（untracked，63 tests，md5 `d9e34b86`）
- M `current_candidate_e3_bb_signoff_request_packet.py`（+9：policy 常量單源 import + packet 字段，md5 `6396cf48`）+ 其測試（+2：字段斷言，md5 `6f49d93c`）
- M `helper_scripts/SCRIPT_INDEX.md`（+5，含四家族收緊描述=nit 已收）、`TODO.md`（單 row 兩段式 Step 1 SOP）

## 範圍裁定（明示披露）
1. **不跑 cargo test**：工作樹含並行 session IMPL-A Rust 在製品（`demo_learning_lane*.rs`、`lib.rs`、`tick_pipeline/*` 等 10 檔 M）——未完成交付物，跑了結果無意義且會誤歸因；本驗收 Python-only diff 與 Rust 零 import 交集。Rust 面留待 IMPL-A 自己的 E2/E4 鏈。最後 Rust BASELINE（2026-06-18 lib 4087）不因本 commit 變動（本 diff 不觸 Rust）。
2. memory/ 重組髒檔（另一 session 的 35 檔 D + archive/ 新增）不碰不驗。
3. **★ 驗收中途範圍漂移（CONFLICT，非本交付缺陷）**：本驗收開始時親證 v734 guard 兩檔 `git diff` 空（任務前提成立，時間 ~00:20 local）；**00:36-00:38 local 另一並行 session 開始修 v734 guard 自身的同源缺陷**（`standing_envelope_source_impact_guard.py` +118/-6、其測試 +98L/+4 tests；即 PM 2026-07-03 裁決「另立 task 追蹤」那案，方向 fail-closed：SAFE_FILE_MODES 白名單 + --no-renames + unmatched 安全網）。該改動**不在本驗收範圍、未經本 E4 鏈覆蓋**，但因 drift gate import 其 `collect_git_impact_inputs`，我對組合面做了漂移後重驗（見下）。**PM commit 本交付時必須 `git commit --only` 六檔，勿掃入 v734 guard fix（它需自己的 E2→E4）。**

## Test 結果
| Suite | passed | failed | skipped | error | baseline | delta |
|---|---:|---:|---:|---:|---|---|
| focused 4-suite（scope-freeze，v734 未漂移態） | **96** ×2 | 0 | 0 | 0 | 任務預期 96 | 精確命中 |
| focused 4-suite（漂移後終態） | **100** ×2 | 0 | 0 | 0 | 96 + 並行 guard +4 | +4 全出自並行 session，非本 diff |
| `helper_scripts/research/tests/` 全量（終態，py3.10） | **1415** ×2 | 1 | 3 | 0 | base worktree @2a012deeb = 1348/1/3 ×2 | **+63 全新測，REMOVED=0**（node-ID diff 親證）；+4 並行 guard 測另計 |
| 同套件 mac_dev py3.12（資訊性） | 1416 | 1 | 2 | 0 | — | hftbacktest skip→pass；同一 fail |
| srv root `tests/`（importlib mode） | 789 ×3 | 16 | 2 | 0 | base @2a012deeb = 789/16/2，fail 名單 byte-identical ×3 | **0 delta；16 全 pre-existing at clean HEAD** |
| `program_code/ml_training/tests` + `learning_engine/tests` | **1154** ×2 | 0 | 31 | 0 | 舊記錄 855/31（06-09 branch，stale）| 0 failed；Codex 時代淨增，基線重建 |
| `helper_scripts/cron/tests` | **225** ×2 | 0 | 0 | 0 | 舊記錄 53（stale） | 0 failed；基線重建 |

跑兩遍紀律：全部 suite ×2 決定性 identical（fail 名單逐條 byte-identical），無 flaky。

## Pre-existing 紅清單（全列，不自行剔除；與本 diff 零交集，base worktree @clean HEAD 逐條同名重現）
1. `research/tests/test_runtime_governance_ipc_readonly_snapshot.py::test_dispatch_ipc_method_preserves_protocol_error_reason` — **env-dependent 假紅**（severity LOW / confidence HIGH）：test 內 dispatcher 做 bare `from app.ipc_client import EngineProtocolError`，Mac 從 srv root 跑無 control_api_v1 於 sys.path → ModuleNotFoundError 被 SUT 包裝。加 `PYTHONPATH=program_code/.../control_api_v1` 後 6/6 全綠（親證）。修復建議（owed，非本批）：test 改絕對 import 或 conftest 補路徑。
2. `research/tests/test_tail_dislocation_shallow_retune.py` — **collection error**（LOW/HIGH）：bare `import screen` 需 `tail_dislocation_meanrev/` 於 sys.path（committed 2026-06-20 Codex 時代）；本輪以 `PYTHONPATH=helper_scripts/research/tail_dislocation_meanrev` 繞過後其 tests 全綠。
3. srv `tests/` 16 failed（clean HEAD base 同名 byte-identical）：(a) `test_spike_cross_lang_rust_binding.py` ×5 = `FileNotFoundError: 'cargo'`（shell PATH 無 cargo，env-dependent，LOW/HIGH）；(b) `structure/test_stock_etf_ipc_tests_split_static.py` ×3 + `test_stock_etf_route_fixtures_split_static.py` = 已 commit 的 stock_etf fixture 拆分與靜態測試 EXPECTED_MODULES 不符（**真 pre-existing red at HEAD，Codex 時代 drift**，MEDIUM/MEDIUM——與 IMPL-A 並行 Rust 檔同域，可能由 IMPL-A 鏈收，需 PM 裁）；(c) `confirm_modal_a11y`/`prompt_modal`/`strategy_action_visual` ×2/`event_consumer_split`/`new_vuln_3_4`/`v072_writer` ×7 = GUI/結構靜態測試 pre-existing red at clean HEAD（MEDIUM/MEDIUM，未逐條深挖根因，全列供 PM/operator 裁決）。
4. `tests/misc_tools/test_pure_utils.py` 重名 collection error — 已知互斥（memory 長期教訓），`--import-mode=importlib` 解。

## 驗收項逐項
1. focused 四 suite：**96/0/0 ×2 精確命中預期**（drift gate 63 + source_impact_guard 14@freeze + window_guard 14 + packet 5）。
2. 全量回歸：見上表；research/tests delta +63 = 100% 新增（collect-only node-ID diff base 1352 → HEAD 1415，REMOVED=0/ADDED=63，6 條 parametrize ID 含 `/` 已逐一對回同一新檔）；packet 測試 +1 斷言 0 新 node。其餘套件 0 delta。
3. **mock 檢查 PASS**：新測檔 grep mock/Mock/monkeypatch/patch = **0 hit**。temp-git 整合測 9 條真跑 `git init/add/commit/update-ref/mv/update-index`（subprocess，非 stub）；CLI 端到端走真 `mod.main()`；builder 單測以純資料 dict 餵真 `build_post_approval_drift_gate`（IO-boundary-equivalent，受測邏輯全真跑）。兩條真實回放**非 skip 真跑 PASSED**（`-v` 親證）：bfbbd343..70f0f375=EXEMPT（changed_path_count>0）、c0a827b6..92959379=ROTATED（斷言 `rust_src_surface_changed`+`unclassified_post_approval_drift`）。packet 測試唯一 monkeypatch=sys.argv（CLI IO 邊界，允許）。
4. **CLI 煙測 PASS**：真 repo-root、tmp packet 含 `post_approval_drift_policy: "docs_tests_codex_exempt_v1"`（sha256 `6b3298eb...`）、`--approved-source-head bfbbd343`（親證 ancestor of origin/main `2a012deeb`）。exit 0；packet schema_version/status/blockers/mode_aware_diff/source_state/approved_request/answers 齊全；**status=ROTATED（正確行為）**，blockers=`['rust_src_surface_changed','unclassified_post_approval_drift']`（rust src ×5 含 `src/ipc_server/tests/` 正確不豁免；program_code IBKR connector 等 ×8 unclassified deny）；sha256_match=True/policy_field_present=True 證 ROTATED 純由 drift 觸發；worktree dirty 僅記錄不阻斷；mode_aware collected=True/errors=[]；answers 全 no-authority。**漂移後重跑：packet 與漂移前 byte-identical（ex-timestamp）**——新 v734 collector 組合下行為不變。
5. 衛生 PASS：py_compile 4 檔 OK；`git diff --check` exit 0（全樹+scoped）；v734 guard 兩檔+其測試於 scope-freeze 時 `git diff` 空 = 0 改動（其後漂移屬並行 session，見範圍裁定 3）。
6. 測試缺口：無需補測（63 測含表驅動 30 路徑分類、rename/copy 雙端、mode-aware 三攻擊面 repro、packet/policy fail-closed 矩陣、temp-git 整合、真實回放雙向）。**E4 獨立 mutation-bite（不盲信 E2 三個）**：neuter `sha256_match` blocker（批准錨點）→ 恰 `test_request_sha256_mismatch_rotated` + `test_temp_git_request_sha_mismatch_rotated` 2 紅 / 61 綠（精準非 tautology）；還原後 md5 `13a0f7d8` byte-identical、E4-MUTATION grep=0、focused 全綠 ×2。

## 其他
- cross-language float：N/A（純 Python source-only gate，無 Rust hot path/共用浮點）。SLA 壓測：N/A（非 hot path，一次性 CLI gate）。node --check：N/A（0 .js）。
- Linux owed：無 runtime/PG/migration 面；gate 為 source-only git 比對，Mac 驗證充分。真實消費（TODO Step 1 兩段式 SOP）屬 PM refresh cycle，非本批。
- in-scope 檔案於驗收全程 md5 穩定（gate `13a0f7d8` 貫穿 mutation 前後）；並行 session 曾 touch mtime 但內容未動（md5 親證）。

## 結論
**PASS（ready for PM `git commit --only` 六檔：2 新 py + 2 M py + SCRIPT_INDEX.md + TODO.md）**。退 E1 清單：無。
附帶警示：commit 時勿掃入並行 v734 guard fix（需自己的 E2→E4 鏈）；srv tests/ 16 條 pre-existing 紅與 2 條 sys.path collection 問題留 PM 裁決派工。
