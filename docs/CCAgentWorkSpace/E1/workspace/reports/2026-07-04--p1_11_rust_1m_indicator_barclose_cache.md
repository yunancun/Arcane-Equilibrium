# E1 報告 — P1-11：1m 指標 bar-close gated 快取（PERF-1 5m 半邊補全）

日期：2026-07-04
Branch：`fix/rust-1m-recompute-0704`（isolation worktree，禁 push，待 conductor 合併）
Commit：`8f002a907`
出處：冷審計 R2 修復計劃 Addendum v2 §C「新 P1-11」（E5 HIGH 補票轉正）

## 任務摘要

PERF-1（2026-06-14，`471c1811b`）只對 5m 指標做了 bar-close gated 快取；1m 側
`step_1_2` 仍每 tick 無條件呼 `compute_indicators`（= 100 根窗口全指標套件重算，
含 Hurst R/S）。本補丁把同一機制鏡像到 1m 側，語義零改變。

## 修改清單

| 檔 | 改動 |
|---|---|
| `rust/openclaw_engine/src/tick_pipeline/mod.rs` | 新增 `perf1_indicators_1m_cache` / `perf1_indicators_1m_epoch` 欄位（同構 5m 側） |
| `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs` | ctor 空 map 初始化；`remove_symbol` 同步清 1m 快取+epoch |
| `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs` | 新增 `cached_or_recompute_indicators_1m`（重算端複用既有 `compute_indicators`） |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_1_2_klines_indicators.rs` | 唯一生產呼叫點 `compute_indicators(sym)` → `cached_or_recompute_indicators_1m(sym)` |
| `rust/openclaw_engine/src/tick_pipeline/tests/mod.rs` | 註冊新測試模組 |
| `rust/openclaw_engine/src/tick_pipeline/tests/perf1_indicators_1m_cache.rs` | 新增 7 條回歸測試 |

## 關鍵設計（對照 5m 側 PERF-1）

- epoch key = `(1m 最後收盤 bar open_time_ms, ewma_lambda("1m"))`：open_time_ms
  防緩衝長度凍結；lambda 入 key 防 RiskConfig 熱重載後服務過期快照。
- **只快取 `Some`**（never-cache-None）：暖機期 / 未知幣種不寫快取。無已關閉
  1m bar 時 `last_closed_open_time_ms` 回 None 直接短路——此時直接重算也必回
  None（compute 端 <30 根 fail-closed），兩路徑等價。
- **scope fence（1m 特有的關鍵點）**：只 gate「指標重算」。`apply_hurst_regime_label_for`
  （hurst 滯回 `detector.push`）、`latest_indicators` 鏡像、`FeatureSnapshot` 發送
  每 tick 照舊在回傳的 **owned clone** 上執行——打標頻率與語義完全不變，且快取
  內永遠是未打標原始快照（Rust 所有權保證 clone mutation 不回污染快取）。
  若把整段（compute+打標）一起 gate，`detector.push` 會從每 tick 降為每 bar，
  改變滯回語義——故刻意不那樣做。

## 測試證據

- `cargo check -p openclaw_engine`：綠。
- 焦點：`tick_pipeline::tests::perf1_indicators`（1m 7 條 + 5m 既有 7 條）= 14 passed / 0 failed。
- 全量：`cargo test -p openclaw_engine --lib` = **4268 passed / 0 failed / 1 ignored**（ignored 為既有）。
- 驗收要求「同一 bar 內多 tick 不觸發重算」由
  `p1_11_sentinel_proves_no_recompute_within_same_1m_bar` 直接證明：竄改快取為
  哨兵值後同 bar 內 5 次呼叫全回哨兵（任何重算都會覆寫回真值），新 1m 收盤後
  哨兵被真值覆蓋。
- 「重算時機外結果 bit-一致」由 `p1_11_cache_on_vs_cache_off_bit_identical_over_tick_sequence`
  證明：cache-on vs cache-off（=舊每 tick 直接重算路徑）逐 tick serde
  byte-identical，含跨 bar 邊界（byte-identical 嚴格強於 spec 的 1e-4 容差，故未
  複製 5m 測試檔的 scalar 容差 helper——避免 55 行測試代碼重複）。
- 紅→綠說明：本任務無法寫出「先紅」的行為測試（快取欄位/哨兵法皆依賴新結構才可
  編譯），紅相位僅為編譯失敗，無資訊量，故實作與測試同批落地後跑綠。

## 熱路徑 SLA（<1ms H0 / <0.3ms tick 不得劣化）

- cache-hit（絕大多數 tick）：2 次 HashMap 查 + `IndicatorSnapshot` clone（小型
  定長結構 + regime String），**取代** OHLCV `get_ohlcv`（5×Vec≤100 拷貝）+
  全指標套件（含 Hurst R/S）——嚴格更廉。
- recompute tick（每 symbol 每分鐘一次）：多一次 snapshot clone 入快取，與 5m
  側已接受的成本同級（每 bar 一次，可忽略）。
- 結論：分析面只升不降；與 5m 側 PERF-1 上線時同一論證。E4 如需實測可跑既有
  H0 latency 記錄面對照。

## 治理對照

- 不碰 max_retries=0 / live_execution_allowed / execution_authority / system_mode：未觸及。
- 無 SQL migration、無 singleton 新增、無跨平台路徑硬編碼。
- 注釋全中文（技術詞保留），新測試檔含模組級意圖說明。
- 檔案大小：`on_tick_helpers.rs` 改後行數增 ~54（原已超 800 之既有例外檔，未新增例外）。

## 不確定之處

1. isolation scratchpad 有並行 agent 互擦現象（本 worktree 曾被整目錄清空一次，
   已重建並即時 commit 保全；若 conductor 合併時發現 worktree 目錄缺失，branch
   `fix/rust-1m-recompute-0704` @ `8f002a907` 在主 repo `.git` 內完整可 checkout）。
2. E1 memory.md 追加省略：任務約束「不碰 memory/」與主樹禁改衝突，留待 PM 統一。

## Operator 下一步

E2 對抗審查 → E4 回歸（可加 H0 latency 對照）→ PM 合併。部署側注意：本修復
屬引擎熱路徑，需隨下次 `--rebuild` 重啟才生效（呼應 P0-1 運行世代結論）。
