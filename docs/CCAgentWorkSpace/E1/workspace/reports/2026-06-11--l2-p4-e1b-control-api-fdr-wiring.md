# E1 報告 — L2 P4 online-FDR E1-B（control_api app 接線）

日期：2026-06-11 ｜ 角色：E1 ｜ branch `feat/l2-p4-e1b`（base `5f49d4bb`）｜ 狀態：**IMPLEMENTATION DONE，待 E2**

兩段 commit 已 push origin（抗死亡紀律）：
- 段1 `ac6d5291`：新檔 store + fdr routes + main.py 掛載 + 測試（4 檔 +1373）
- 段2 `5eaba216`：6 既有檔接線 + TOML + 2 測試檔（9 檔 +2050/−38）

## 任務摘要

按 PA P4 設計（§4.2/§5/§6/§7/§8.1 E1-B 行）+ MIT ratification（#3 MODIFY/§5a FIX-3.1 四條件/N-4/N-8）+ QC sign-off（FIX-1.1/1.2/1.3/2.1b 重裁版），把 hypothesize cascade 包上 online-FDR 統計紀律：precheck 免費 skip → sealed-boundary → pre-registration → wealth admission → math gate（N_eff + α_i threshold）→ debit 記帳，加 bind-demo/wealth routes 與 tier 唯讀投影。C 線（V137 sql/reconciler）他人負責未碰；A 線（learning_engine 純數學）僅作 import 點，測試以契約 fake mock。

## 修改清單（±行數）

| 檔 | Δ | 內容 |
|---|---|---|
| `app/l2_alpha_wealth_store.py` | 新 +547 | PG 帳本層（append-only INSERT+SELECT；0 UPDATE/DELETE） |
| `app/l2_fdr_routes.py` | 新 +152 | POST bind-demo（operator-scope 第一行）+ GET wealth 唯讀 |
| `app/main.py` | +4 | fdr_router 掛載（:148-149；**最小必要偏差**，見 deviation 1） |
| `tests/test_l2_p4_alpha_wealth_store.py` | 新 +~670 | 41 tests |
| `app/l2_ml_advisory_executor.py` | 1274→**1817** | STAGE 3.55/3.58/3.6/3.7/4/4.5 + mint + N-8 |
| `app/l2_candidate_evidence_adapter.py` | 662→825 | evidence_window + N_eff seam + sealed boundary |
| `app/l2_prompt_contract_registry.py` | 359→419 | hypothesize v2（v1 保留） |
| `app/l2_out_of_bound_guard.py` | 375→432 | clause F + clause E falsification 形更新 |
| `app/l2_advisory_orchestrator.py` | 760→806 | tier_provider（fail-closed L1） |
| `app/layer2_routes.py` | 861→886 | `_governance_tier_projection` + `_get_orchestrator` 注入 |
| `settings/l2_capability_registry.toml` | 1 行 | hypothesize `prompt_contract_ref` v1→v2（同 commit） |
| `tests/test_l2_p4_online_fdr.py` | 新 +~800 | 66 tests（binding golden 全套） |
| `tests/test_l2_p3b_hypothesize.py` | +118/−38 | 10 tests 更新至 v2 形 + FDR 語義（更新斷言非繞過） |

## Binding AC 落點對照（file:line，段2 commit 後）

| AC | 落點 |
|---|---|
| **MIT #3** debit=`overall∈{pass,fail}` OR `stage_verdicts["dsr"]∈{pass,fail}` | executor:1382（`conducted =`）；B1 key 用 `beta_neutral`（QN-6，:1053 既有） |
| MIT #3 純輸入缺失 DEFER 不扣 | executor:1384-1386（`deferred_no_debit`）；golden=test_pure_input_missing_dsr_defer_no_debit |
| **MIT N-8** `:1003` docstring 訂正 | executor:1511（「五 stage 全跑、無 short-circuit」實況） |
| **FIX-3.1 ①** precheck 在 STAGE 3.7（α_i 指派）之前 | executor:1272（3.55）<:1292（3.6）<:1332（3.7）；test_prereg_before_gate_render + golden(a) 斷 preregs==[] |
| **FIX-3.1 ②** value-invariance 謂詞 | executor:1097 `_run_doomed_input_precheck`（candidate/btc/altcap is None、aligned 日曆 span<180d via `_min_down_span_days`=beta_neutral_check 常數單源、leak 雙 None、evidence_window schema 完備性；0 值函數——另有 source-token 斷言） |
| **FIX-3.1 ③** total skip | executor:1228 `_skipped_math_res`（無 `dsr` 鍵）+ :1274 log |
| **FIX-3.1 ④** golden a/b/c | test_l2_p4_online_fdr.py：TestFix31Precheck（a=5 變體+span、c=雙向 mutation）+ TestMit3DebitCondition::test_golden_b |
| **FIX-2.1b** 區間算術 | adapter:453 `load_sealed_boundary_flag`（:510 `bar_end=window_end+1d`、:523 `bar_end > anchored`）；`==` off-by-one + 非午夜 straddle 雙 golden + mutation（點比較）證 bite；多 row 任一重疊 DEFER 記 min(window_start)；無 row=`no_sealed_split_for_cell` 不阻；查詢失敗 fail-closed True |
| FIX-2.1b executor 渲染前短路 + gate 防禦縱深 | executor:1280-1284（3.58 skip）+ :1583-1589（STEP5，僅帶鍵時渲染=legacy 零波及） |
| **FIX-1.1** supersedes 鏈 head | store:428 `register_pre_registration`（exact-hit head 檢查 + core-match 全 superseded → DEFER `pre_registration_superseded`） |
| **FIX-1.2** 窗入 hash payload + 單調 + hash 先於渲染 | store spec `evidence_window`（executor:1171 `_build_pre_reg_spec` 全字串 spec）+ store 窗單調（start 相等、end 僅向後；ISO 字串字典序=日期序）+ 庫內 jsonb hash 對賬；次序由 test_prereg_before_gate_render 鎖 |
| **FIX-1.3** dead-mode mint | executor:1437 `_mint_dead_mode_lesson`（source=`dead_mode_seed`、lesson_type=`dead_mode`=novelty 檢索鍵、英文主幹+三欄、`WHERE NOT EXISTS` 冪等、redact 後落庫）；call site=fail 分支（P3b b1_fail test 驗 cascade 面） |
| **MIT N-4** debit_id 確定性 | store:115 `deterministic_debit_id`=sha256(f"{pre_reg_id}:{ws}:{we}")[:16]，無隨機無 attempt；重放同 id（test_debit_id_deterministic） |
| **MIT #2 Option B** | executor:1373 `threshold=awc.dsr_threshold_for(alpha_i)` → :1600 `_run_dsr_stage(threshold=)` → compute_dsr 透傳；marginal-sharpe 真咬合 test + threshold=1.0 fail-soft DEFER test |
| STAGE 3.6 canonical hash byte-identical | store:92 `canonical_spec_sha256`（sort_keys/separators/ensure_ascii 與 bridge `_canonical_sha256` 同字面；source-pin test） |
| STAGE 3.7 wealth admission | executor:1332-1371（ensure init→SUM→assign_alpha_i→can_test；枯竭=DEFER `alpha_wealth_exhausted`；store 不可達/controller 缺=DEFER `alpha_wealth_store_unavailable`） |
| STAGE 4 N_eff 注入 | adapter:402 `_compute_n_eff`（**共享 ordinal int key 跨 variant 對齊**）；缺/壞=raw k_trials+reason `n_eff_unavailable_raw_k_trials`（:177）；0 標量合成 |
| contract v2 + TOML 同 commit | registry:305-306 v2（v1 保留）；TOML :120；executor `_MODE_CONTRACT_REF`:95——三點同步 test |
| guard clause F | guard:317（三欄非空 + primary_axis ∈ 假說 axes（退 top-level）；MIT #4 反鑄幣） |
| tier_provider fail-closed L1 | orchestrator:222（參數）/:476 set-if-absent/:486 `_resolve_tier`/:616 Stage 5 消費；默認 None=byte-identical（test 矩陣：L3+flag 解鎖/flag False 鎖/raise 退 L1/garbage 退 L1） |
| layer2_routes 注入 | :108 `_governance_tier_projection`（module-attr late-read 防 stale）+ :134 注入 |
| fdr routes auth | l2_fdr_routes:92 bind-demo（`require_scope_and_operator` 第一行，source-grep test）；GET wealth 唯讀 authenticated |
| PG 全 to_thread | executor 全部 store 呼叫 `asyncio.to_thread`；routes 同 |
| grep 指紋 AC | 兩個 fingerprint test（tokenize 剝註解）跨 6 模組 0 命中 |
| P3a 零波及 | test_p3a_modes_never_touch_fdr_machinery + P3a 全家族 159 passed 不變 |
| hidden_oos 0 寫點 | test_l2_modules_zero_writes_to_hidden_oos_registry（adapter 唯一 SELECT window_start 邊界元資料） |

## 測試計數（mac_dev venv 3.12 實跑）

- `test_l2_p4_alpha_wealth_store.py` **41 passed**
- `test_l2_p4_online_fdr.py` **66 passed**
- `test_l2_p3b_hypothesize.py` **10 passed**（更新後）
- l2/layer2 全家族（`-k "l2 or layer2" --ignore=tests/replay`）**648 passed + 4 xfailed + 0 failed**（tests/replay 4 collection error=pre-existing import-path，與本任務無關）
- mutation 三證全 bite 後還原全綠：①debit 條件去 dsr 臂→2 紅；②區間算術改點比較→off-by-one+straddle 2 紅；③precheck 停用→6 紅。

## 治理對照

硬邊界 0 觸碰（fingerprint test 鎖）；append-only store 0 UPDATE/DELETE（test 鎖）；一切失敗收縮向 DEFER（store 不可達/debit 寫失敗/tier 投影故障/sealed 查詢失敗全 fail-closed）；新注釋全中文；0 硬編 user path；無新 mutable singleton（store stateless=PA §2.1 判定，tier_provider 是 orchestrator 既登記 singleton 的注入槽）。executor **1817 行**（>800 review 線、<2000 hard cap；超 PA 估 ~1450——precheck/mint/wealth-stage 注釋密度所致），**請 E2 評 sibling-extract 時機**（§8.1 既定義務）。

## 不確定之處 / deviation（最小安全解，供 E2 裁）

1. **main.py +4 行**（超出列名清單）：新 route 檔必須有掛載點，照 layer2_router 同模式；不掛=死碼。
2. **precheck 置於 STAGE 3.6 之前**（MIT 只要求「3.7 之前」）：skip run 零 DB 寫、total-skip 語義最乾淨；pre-reg 窗釘的是 conducted look，skipped run 無 look。
3. **debit 寫失敗 → verdict 強制 DEFER**：MIT 前提(c) 被破壞時不得放行結論性 verdict（未付費 discovery 禁鑄）；fail 同被降 DEFER（不 mint dead-mode）——寬於精確語義但收縮向。
4. **overall fail 而 dsr 未渲染且 n_trials 缺 → ledger n_eff=1 + evidence `absent_default_1`**：V137 CHECK 要 n_eff≥1，此時無 K 消費，1 為審計佔位非 deflation。
5. **取第一個合法假說做 pre-reg/family**（多假說時）：與 novelty 取首條 statement 同慣例；單 evidence row=單 test=單 debit（G.1.2）。
6. **sealed 檢查無 cell（strategy/symbol 缺）→ 不阻 +reason**：對齊「查無 sealed row 不阻」語義；gate-to-P5「證實」仍要求真實 cell 走通。
7. **`alpha_wealth_remaining` 只在 3.7 後注入 context**（STAGE 5 cloud + D3 可見；STAGE 2 generate 看不到）——informational 鍵位的最小實現。
8. **sealed 查詢失敗 fail-closed→DEFER `sealed_registry_check_failed`**（無法證明盲視不放行）；reason code 為新增（非契約原文）。
9. A 線真模組（alpha_wealth_controller/n_eff_cluster）本 branch 不存在：lazy import 不可得=DEFER `alpha_wealth_store_unavailable` / raw-K fallback；測試以契約 fake mock import 點。**merge 後 E4 必須以真模組跑全鏈**（兩 branch 合流是 E4 前置）。

## Operator / PM 下一步

1. E2 對抗審（重點：§14 三點——記帳冪等、不鬆閘單調、sealed clip+測試隔離；executor 行數 sibling-extract）。
2. 與 A 線（origin/feat/l2-p4-e1a）+ C 線（V137）合流後 E4 Linux 全鏈迴歸（V137 dry-run double-apply 在 C 線 owed）。
3. E4 golden：merge 後以真 alpha_wealth_controller 重跑本檔 66+41 測試（fake 契約 vs 真簽名一致性）。

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-11--l2-p4-e1b-control-api-fdr-wiring.md）
