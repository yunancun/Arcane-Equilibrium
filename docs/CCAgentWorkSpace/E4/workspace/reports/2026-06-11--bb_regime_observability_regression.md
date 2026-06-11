# E4 Regression — feat/bb-regime-observability @ 52727d82 · 2026-06-11

**對象**：hurst regime 觀測欄（P1-BB-REVERSION-REGIME-OBSERVABILITY）。Worktree `/tmp/wt-bb-regime`，base `62085d17`，3 檔 +217/−1 純 Rust。E2 已 PASS（0 需修 finding）。
**Linux 同步做法**：Mac `git push origin feat/bb-regime-observability`（task 授權）→ trade-core fetch → `/tmp` detached worktree ×2（base+HEAD）+ **逐 rev 隔離 `CARGO_TARGET_DIR`**（prod checkout 與 prod target dir 全程零觸碰）。

## Verdict：**PASS**（0 真回歸；+4 測試全綠；stress HEAD 不劣於 base 噪音帶）

## Test 結果

| 引擎 | passed | failed | ignored | baseline（對照） | delta |
|---|---|---|---|---|---|
| Mac debug 全 target（43，`-p openclaw_engine --no-fail-fast`）run1 | 4158 | 1 | 4 | OPS-2 era 4154/1/4（total 4155） | +4 = 恰新測試 |
| Mac 同上 run2 | 4158 | 1 | 4 | — | run1==run2，FAILED 名單 byte-identical |
| Mac engine lib（×2 同值） | 3791 | 0 | 1 | E1 base 實測 3787/0/1 | +4 |
| **Linux release 全 workspace（54 targets）base `62085d17`（親跑）** | **4665** | **0** | 6 | memory 基線 4665/0/6ign 精確匹配 | — |
| **Linux release HEAD `52727d82` run1** | **4669** | **0** | 6 | base 4665 | **+4** |
| **Linux release HEAD run2** | **4669** | **0** | 6 | — | run1==run2（雙跑 0 failed） |
| Linux engine lib（×2 同值） | 3792 | 0 | 1 | base 親測 3788/0/1 | +4（鏡像 Mac +4；平台差 +1 為既有 cfg 差） |

Mac 唯一紅 = `stress_tick_latency_benchmark`（debug 閾值 1000μs；1067.6/1076.2μs，落 E1 1053.6–1058.0 / E2 1076.8 同噪音帶；E1 已證 base 同機同紅）= pre-existing debug flake，非本 diff；Linux release 為權威（下表全綠）。

## 測試數對賬（名字級，三層）

1. **檔級 fn parse**：whole diff 恰 3 檔（name-only 證）；3 檔內 `#[test]` fn 22→26，diff = **+4/−0**，4 個 ADDED 逐名=4 新測試。
2. **Linux `--list` 全 54 targets node 級（權威）**：base 4671 → HEAD 4675，**ADDED=4（恰 4 新測名）/ REMOVED=0**；口徑閉合（4671=4665p+6ign）。
3. **outcome 算術**：Mac lib 3787→3791、Linux lib 3788→3792、Linux 全套 4665→4669，三處 delta 同 +4。
0 靜默消失；test 檔 diff 0 刪行（既有 3 契約測試恰各 +1 行 `None,`）；0 `#[ignore]`/skip 注入。

## Stress tick_latency base-vs-HEAD（Linux release，standalone `--exact`，各 6 輪含 3 輪交錯）

| 輪 | base 62085d17 (μs) | HEAD 52727d82 (μs) | 備註 |
|---|---|---|---|
| 1 | 58.2 | 61.4 | 各自 block 連跑 |
| 2 | 66.6 | 57.7 | |
| 3 | 57.8 | 86.0 | HEAD 高值落 05:17 噪音窗 |
| 4（交錯） | 87.4 | 84.8 | **同窗 base 87.4 > HEAD 84.8** |
| 5（交錯） | 58.3 | 72.9 | |
| 6（交錯） | 57.9 | 58.0 | |
| **min** | **57.8** | **57.7** | HEAD 略優 0.1μs（min=最乾淨本徵成本估計，噪音只加不減） |
| **p50** | 58.25 | 67.15 | 差異由高值輪落窗位置驅動（高值按時間窗聚集非按 binary） |
| mean | 64.4 | 70.1 | |
| 閾值 | <100μs | <100μs | **12/12 輪全 PASS** |

判準「HEAD 不劣於 base 噪音帶」**成立**：兩分布完全重疊（base 57.8–87.4 vs HEAD 57.7–86.0）、全域最大值屬 base（87.4）、min-vs-min 相等（0.1μs）、交錯 pair 1 勝 1 負 1 平。結構佐證：E2 軸 1 已證非 intent tick 0 新指令（新代碼僅 intent 發射分支執行，benchmark 場景 intent 稀少）。另有 3 輪 hash 證實為 base binary 的補充樣本（57.6/57.7/64.6，作廢 run 重歸類）與 base 帶一致。

## Mutation-bite 抽驗（E1/E2 未打過的點）

打點 = dispatch **:560 pre-risk caller**（`record_pre_risk_rejection` 實參；E1 打過 paper :1054、E2 打過 exchange :748，三透傳 call site 至此全鏈獨立咬過）：`indicators.and_then(|i| i.hurst.as_ref())` → `None` ⇒ `test_dispatch_forwards_hurst_at_all_persist_intent_call_sites` **紅 n=2**（訊息精確指「被改傳 None」），3 條契約測試不受擾（分工非 tautology）。還原（`git checkout HEAD --`）後 porcelain 空、`E4-MUTATION` grep=0、diff vs `52727d82` 空、hurst-filtered lib 35/0 綠。

## Mock 審查

| Test | mock 內容 | OK? |
|---|---|---|
| 3 契約測試（records/none-null/nan） | 僅 `tokio::mpsc::channel` 作 trading_tx sink（IO 邊界；正是 production 真通道型別），收到的 `TradingMsg::Intent` 為真 `persist_intent` 業務邏輯（details JSON 構造）產物 | ✅ |
| 結構測試（forwards_hurst） | `include_str!` 真源碼，0 mock | ✅ |

0 業務邏輯 mock。

## 跑兩遍

Mac：run1 4158/1/4 == run2 4158/1/4，FAILED 名單 byte-identical（唯一條目=stress debug flake）。
Linux HEAD：run1 4669/0/6 == run2 4669/0/6（0 failed 雙跑）。flaky=N（除已歸因的 Mac debug stress 閾值 flake，pre-existing）。

## ★ 過程抓到的測試基建陷阱（已修正，記 memory）

第一次 Linux HEAD 跑與 base **共享** `CARGO_TARGET_DIR`：HEAD worktree 檔案 mtime（worktree add 05:07）早於 base build 寫入的 fingerprint（05:08–09）+ cargo `-C metadata` hash 不含 workspace 路徑（同名 binary hash 完全相同）→ cargo 視 HEAD 為 fresh，**靜默重用 base 二進位，HEAD 測試 0 執行**（假象：HEAD 數字==base、名單 diff 空）。由三重 tripwire 抓出：HEAD 應 +4 未 +4、新測名 grep run-log=0、binary hash 相同。修正=HEAD 用獨立 fresh `CARGO_TARGET_DIR` 重做（本報告 Linux HEAD 數字全為重做後真值，作廢 run 已棄）。

## 清理確認

- Linux：`git worktree remove` ×2（`git worktree list`=僅 prod）；`/tmp/e4-bb-*`+`/tmp/e4_linux_*` 殘留=0；prod porcelain=0 @ `62085d17` 不變；engine PID 2223263 運行未擾（全程 0 restart，soak epoch 不受影響）；prod `rust/target` 未觸碰（build 全在隔離 dir）。
- Mac：`/tmp/wt-bb-regime` 還原 byte-clean @ `52727d82`（PM worktree 保留）；E4 temp log 已刪。
- Branch `feat/bb-regime-observability` 已 push origin（task 授權之同步手段，兼 PM merge 之用）。

## 不部署聲明

依 task：不部署、不 restart（soak 進行中）。部署後 PA §3 驗收 SQL（`details ? 'hurst_label'` 分界 + gate-on 100% mean_reverting）歸 deploy gate（owed-post-deploy）。

## 退 E1 修復清單

無。

**E4 REGRESSION DONE: PASS**
