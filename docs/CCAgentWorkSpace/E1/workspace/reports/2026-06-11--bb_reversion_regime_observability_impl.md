# E1 IMPL — P1-BB-REVERSION-REGIME-OBSERVABILITY（2026-06-11）

**Branch**: `feat/bb-regime-observability` @ `52727d82`（worktree `/tmp/wt-bb-regime`，base `62085d17`，已 commit 未 push 未 merge）
**PA 設計**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-11--bb_reversion_regime_observability_design.md`（嚴格照辦，0 scope 偏移）

## 任務摘要

把 gate 同 tick 消費的 Hurst regime 判定（`IndicatorSnapshot.hurst`）持久化進 `trading.intents.details` JSON：`persist_intent` +1 參數（`Option<&openclaw_core::indicators::HurstResult>` 引用搬運），details 加 `hurst_label` + `hurst_value` 兩鍵；dispatch 4 個透傳點全接同一份 snapshot。全策略統一加；缺失/non-finite 映 null；fail-soft 結構不變（`try_send` 非阻塞，0 新 early-return/unwrap/panic 路徑）。0 migration / 0 OrderIntent / 0 IPC / 0 策略碼 / commands.rs 未碰。

## 修改清單（3 檔，+217/−1）

| 檔 | 改動 |
|---|---|
| `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`（792→809 行） | `persist_intent` 簽名 +`hurst` 第 12 參數 + `#[allow(clippy::too_many_arguments)]`（同檔 dispatch:91 先例，PA §4.8 授權）；details json 在 `signal_id` 前加 `"hurst_label": hurst.map(\|h\| h.regime.as_str())` + `"hurst_value": hurst.map(\|h\| h.hurst)`；FUP-8 過期註釋修正（regime 已落地，刪「等 OrderIntent」誤導） |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`（1813→1819 行） | `record_pre_risk_rejection` +`hurst` 參數（置 `scanner_gate` 後 `reason` 前，鏡像 persist_intent 參數序）並透傳進內部 `persist_intent`（透傳點 1）；3 個 call site 各 +1 行實參 `indicators.and_then(\|i\| i.hurst.as_ref())`（:546 pre-risk caller / :748 exchange / :1054 paper = 透傳點 2-4） |
| `rust/openclaw_engine/src/tick_pipeline/tests/fast_track_reduce.rs`（666→859 行） | 3 既有 persist_intent 契約測試補第 12 實參 `None`（兼作既有鍵不變回歸證明）；+4 新測試（下） |

## 測試（4 新，全綠；驗收逐條對照）

1. `test_persist_intent_records_hurst_regime_details` — 驗收①：`Some(HurstResult{0.33,"mean_reverting"})` → 兩鍵=同 tick snapshot 原值；併入 PA test (b) 既有鍵不變斷言（strategy/confidence/submitted_qty/is_long）。
2. `test_persist_intent_hurst_none_keys_present_null_and_intent_still_persisted` — 驗收②（fail-soft bite）：`None` → `.get()` 斷言兩鍵 **present-null**（區分缺鍵；`details ? 'hurst_label'` 部署分界標記語義）+ intent 照常入列。
3. `test_persist_intent_hurst_nan_value_maps_null_no_panic` — PA test (c)：`f64::NAN` → hurst_value=null 不 panic，label 不受影響。
4. `test_dispatch_forwards_hurst_at_all_persist_intent_call_sites` — 驗收③（4 透傳點覆蓋）：`include_str!` 結構測試（對齊 database writers 自審先例）斷言 dispatch 內轉發表達式 count==3 + `record_pre_risk_rejection` 段宣告 `hurst` 參數且內部 persist_intent 呼叫含 `hurst,`。編譯器強制 arity，本測試補「被改傳 None」的縫。

**Mutation bite 雙證**：(A) paper site 改傳 `None` → 結構測試紅（n=2）；(B) 移除 `hurst_value` 鍵 → 3 契約測試紅；還原全綠（還原用 git checkout HEAD——已 commit 後才做 mutation，承 2026-06-11 慘痛教訓）。

## 驗證數字（Mac，rustc 1.95.0）

- **lib base-vs-HEAD**：base(62085d17) 3787 passed/0 failed/1 ignored → HEAD **3791/0/1**，delta=+4 恰為新測試，**0 回歸**（驗收④）。
- **全 target `--no-fail-fast`**：43 targets，42 綠 + 1 fail = `stress_tick_latency_benchmark`（debug 閾值 1000μs）。**base 同機同樣紅**（base 1053.6μs vs HEAD 1053.7/1058.0μs，delta 0.1-4.4μs=噪音帶）= pre-existing flake 非我回歸（memory 2026-06-10 已兩輪紅綠前科）；同時兼作熱路徑非回歸初證（E4 Linux 對跑為權威）。
- **clippy**：我 3 檔 0 警告（lib+tests targets，`-->` 位置行 grep 證）。
- **fmt**：我 3 檔 clean；dispatch :1632/:1708 兩處 pre-existing drift 未碰（diff hunks 全在 :103-126/:560/:764/:1071，git 可證）。

## 治理對照

- 熱路徑紀律：純值搬運（`Option<&HurstResult>` 共享引用），0 鎖/0 IO/0 重算/0 await；新代碼僅 intent 發射分支執行。
- 硬邊界：max_retries/live_execution_allowed/execution_authority/system_mode 0 接觸；禁區（OrderIntent/commands.rs/策略碼/trading_writer/openclaw_types）0 觸碰（diff 自證）。
- 注釋：Chinese-first，含 fail-soft「為什麼」與軸別命名 rationale（hurst_ 前綴 vs scanner market_regime/AEG main_regime）。
- LOC：on_tick_helpers.rs 809（>800 review-attention，PA §4.7 已預申報，不拆檔）；fast_track_reduce.rs 859（>800 review-attention，測試檔，E2 知悉）；dispatch 1819（<2000 cap）。
- 無新 singleton / 無 migration / 無 SQL。

## 與 PA 設計的偏差（2 處，均最小安全解）

1. **測試位置**：PA §6 指 on_tick_helpers「既有測試模塊（:96/:732）」——代碼現實該兩處是 `sigma helper cfg(test)` 與 `liquidation_tests`，persist_intent 既有契約測試實際全在 `tests/fast_track_reduce.rs`（:404/:462/:517）。新測試置於該處（同函數契約測試聚一檔 + 簽名改動本就必改該檔），非 helpers 內另起模塊。
2. **FUP-8 註釋修正**：設計未明列，但 §2.3 已論證該註釋的「等 OrderIntent 再加 regime」計劃被推翻——留著=誤導性治理軌跡（memory 長期教訓），comment-only 順改。

## 不確定之處 / E2 注意

- **origin/main 已前進**：worktree 建立後 main 走到 `d46b5cee0`（P4 merge）。`62085d17..d46b5cee0` 與我 3 檔 **0 重疊**（name-only diff 證），merge 預期零衝突；是否 rebase 由 PM 裁。
- 結構測試 count==3 對未來合法重構（如第 5 個 persist site）會紅——這是有意的 fail-loud 設計（斷言訊息已指路），E2 確認接受。
- pre-existing：base clippy 整鏈被 openclaw_core `price_tracker.rs:132 deprecated(since="2026-04-22")` 非 semver 阻斷（clippy 1.95 deny-by-default `deprecated_semver`）——我以臨時本地修補跑完 clippy 後還原；該修補**不在本 commit**，修復屬 follow-up（建議 PM 開單，1 行改 `since="0.1.0"`）。

## Operator / 鏈下一步

E2 對抗審（PA §E2 三點：熱路徑斷言/fail-soft 不變式/call-site 完備+scope 紀律）→ E4（Linux rebuild + 43 targets 基線對照 + stress base-vs-HEAD + 部署後 §3 驗收 SQL）→ QA B 複查翻正 → PM merge+commit。部署需 `--rebuild`（可與 OPS-2 pending rebuild 同車，PM 調度）。
