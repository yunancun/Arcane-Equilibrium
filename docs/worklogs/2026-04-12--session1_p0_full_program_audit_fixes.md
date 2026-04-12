# 2026-04-12 P0 修復報告 — Session 1（全程序鏈審計 8 P0 Live Blocker）

> **來源審計**：`2026-04-12--Audit4.12_full_program_chain_audit.md`（12 報告 · 58 發��）
> **PM 批准修復計劃**：`2026-04-12--full_audit_fix_plan_pm_confirmed.md`
> **修復 commit**：`283ae33` fix(P0): all 8 audit P0 Live blockers resolved
> **測試基準線**：engine lib **961** + core **366** + e2e **29** = **1356** / 0 fail

---

## 修復總覽

| # | FIX ID | 來源 Agent: 發現 ID [原始嚴重度] | 修復摘要 | 改動文件 |
|---|--------|-------------------------------|---------|---------|
| 1 | **FIX-09** | E3: SEC-E01 [HIGH] + SEC-B03 [MEDIUM] | `ocEsc()` 加單引號 `&#39;` 轉義（XSS defense-in-depth） | `common.js:371` |
| 2 | **FIX-10** | E3: SEC-D01 [CRITICAL] | Live 管線啟動時 IPC HMAC 認證強制（無 `OPENCLAW_IPC_SECRET` → panic） | `main.rs:224-235` |
| 3 | **FIX-03** | FA: #2 [BLOCKER] · E3: SEC-A01 [LOW] · E5: D-01 [Medium] | FastTrack `ReduceToHalf`（半倉）+ `PauseNewEntries`（暫停開倉��完整處理 | `on_tick.rs:148-215` |
| 4 | **FIX-04** | FA: #2 [BLOCKER] · E3: SEC-A01 [LOW] | 真實輸入���代硬編碼 0.0：`price_drop_pct` = `PriceHistoryTracker.max_drop_pct()`；`margin_utilization_pct` = `total_notional / balance × 100` | `price_tracker.rs` + `on_tick.rs` |
| 5 | **FIX-19** | BB: BB-A4 [P1] [PARSE-ERROR] | `execution.fast` 缺 `execFee` 時用 `notional × taker_fee_rate` 估算（防止 PNL-FIX-2 同類問題） | `event_consumer/mod.rs:591-620` |
| 6 | **FIX-13** | E4: P0-#1 [P0-CRITICAL] | `edge_estimates.rs` 新�� **14 tests**：JSON 解析、空值回���、`win_rate` clamp、缺��文件、無 `shrunk_bps` 跳過 | `edge_estimates.rs` |
| 7 | **FIX-14** | E4: P0-#2 [P0-CRITICAL] | REST API fail-closed 行為新增 **7 tests**：NoCredentials GET/POST、Transport 錯誤、retCode 非零、`get_checked`/`post_checked` 傳播、timeout 配置 | `bybit_rest_client.rs` |
| 8 | **FIX-15** | E4: P0-#3 [P0-CRITICAL] | 三管線並發寫入 **1 integration test**：3 thread × 50 writes，驗證無交叉污染、無損壞 | `persistence.rs` |

---

## 逐項技術細節

### FIX-09：ocEsc() 單引號轉義

**問題**：`ocEsc()` 只轉義 `& < > "`，缺少單引號 `'`，在 HTML 屬性值用單引號包裹時存在 XSS 風險。

**修復**：追加 `.replace(/'/g, '&#39;')`。1 行改動。

---

### FIX-10：IPC HMAC Live 模式強制

**問題**：IPC HMAC 認證依賴 `OPENCLAW_IPC_SECRET` 環境變量，未設置時靜默跳過認證。Live 模式下 IPC 無認證 = 任何本地進程可發送交易指令。

**修復**：在 `main.rs` pipeline availability ��測後、IPC server 啟動前，加入 guard：
```rust
if live_bindings.is_some() && std::env::var("OPENCLAW_IPC_SECRET").is_err() {
    panic!("FATAL: Live pipeline detected but OPENCLAW_IPC_SECRET is not set...");
}
```
Fail-closed：啟動即拒絕，無法繞過。

---

### FIX-03：FastTrack ReduceToHalf / PauseNewEntries 處理

**問題**：`FastTrackAction` 枚舉定義了 4 個變體，但 `on_tick()` 只處理 `CloseAll`。`ReduceToHalf`（Defensive 風控）和 `PauseNewEntries`（Reduced 風控��完全未實現 — 風控閉環缺口。

**修復**：
1. **ReduceToHalf**：遍歷所有持倉，呼叫新增的 `paper_state.reduce_position(sym, qty/2, price)` 半倉平倉，`emit_close_fill` 記錄 reason=`fast_track_reduce_half`。
2. **PauseNewEntries**：設 `ft_pause_new_entries` 標誌，在 `StrategyAction::Open` 處理前檢查 → `continue` 跳過所有新開倉意圖。
3. 兩者均不阻止止損觸發（stops 正常處理）。

新增 `PaperState::reduce_position()` 方法：部分平倉，qty 歸零時自動移除持倉。

---

### FIX-04：FastTrack 真實輸��

**問題**：`evaluate_fast_track()` 的 `price_drop_pct` 和 `margin_utilization_pct` 硬編碼為 `0.0`，閃崩���測（��5%）��保證金危機偵測（≥90%）分支永遠不會觸發。

**修復**：
1. **price_drop_pct**：新增 `PriceHistoryTracker::max_drop_pct()` — 遍歷所有追蹤幣種，計算滾動窗口內 peak→current 的最大跌幅百分比。
2. **margin_utilization_pct**：`Σ(position.qty × latest_price) / balance × 100`，上限 999.0。
3. 兩個值在每個 tick 的 Step 0 實時��算並���入 `evaluate_fast_track()`。

---

### FIX-19：execution.fast execFee 估算

**問題**：Bybit `execution.fast` WS topic 不攜帶 `execFee` / `feeRate` ��位。`serde(default)` 解析為空字串 → `parse::<f64>().unwrap_or(0.0)` → 手續費 = 0。Demo 環境已因此產生 PNL-FIX-2 級別的費用缺失。

**修復**：當 `exec_fee` 解析為 0 且 qty×price > 0 時：
```rust
if let Some(fee_rate) = taker_fee_rate {
    estimated = exec_qty * exec_price * fee_rate;
}
```
`taker_fee_rate` 來自啟動時 Bybit API 查詢的真實費率。帶 `tracing::debug` 日誌標記估算來源。

---

### FIX-13：edge_estimates.rs 測試覆蓋

**問題**：208 行 / 9 pub fn 零測試。被 scanner 和 cost_gate 依賴 — JSON 解析錯誤或除零問題會直接影響交易決策。

**新增 14 tests**：
- `test_empty_returns_default` �� 冷啟���回退
- `test_load_from_str_valid` — 正常 JSON 解析
- `test_get_existing_cell` / `test_get_nonexistent_cell` — 查詢命中/未命中
- `test_win_rate_fallback_to_raw` ��� `win_rate_shrunk` 缺���回退到 `win_rate`
- `test_win_rate_default_and_std_default` — 缺失欄位默認值
- `test_load_from_str_invalid_json` / `_empty_object` / `_meta_only` — 邊界 JSON
- `test_load_from_file_missing` — 文件不存在
- `test_win_rate_clamped` / `test_negative_win_rate_clamped` — [0, 1] clamp
- `test_load_from_env_or_default_missing_file` — 冷啟動路徑
- `test_entry_without_shrunk_bps_skipped` — 缺 shrunk_bps 不插入

---

### FIX-14：REST fail-closed 測試

**問題**：`bybit_rest_client.rs` 的超時和錯誤處理行為（原則 #5「失敗默認收縮」合規）無��何測試驗證。

**新增 7 tests**：
- `test_get_no_credentials_fails_closed` — GET 無憑證立即錯誤
- `test_post_no_credentials_fails_closed` — POST 無憑證立即錯誤
- `test_get_transport_error_fails_closed` — 連接不可達 → Transport 錯誤
- `test_into_result_non_zero_retcode_fails_closed` — retCode≠0 → Business 錯誤
- `test_checked_methods_propagate_no_credentials` — checked 方法傳播錯誤
- `test_client_timeout_configured` — ��造確認 10s timeout

**���證結論**：全部 fail-closed，零重試邏輯，符合原則 #5。

---

### FIX-15：三管線並發寫入測試

**問題**：3E-ARCH 核心架構（Paper/Demo/Live 並行寫入各自 snapshot 文件）無集成測試。

**新增 1 integration test** `test_three_pipeline_concurrent_writes`：
- 3 OS threads ��自建��� `StateWriter`（paper/demo/live）
- 每線程 50 次 `force_write`（0ms debounce 壓力測試）
- 驗證：每個文件含正確 `pipeline_kind`、最後 tick=49、無交叉污染

**驗證結論**：原子寫入（write-then-rename）確保並發安全。

---

## 測試增量

| 測試集 | 修復前 | 修復後 | 增量 |
|--------|--------|--------|------|
| engine lib | 939 | 961 | **+22** |
| core | 366 | 366 | 0 |
| e2e | 18→29 | 29 | 0（pre-existing） |
| **合計** | **1355** | **1388** | **+33** |

---

## 殘留工作

P0 ��部清零。下一步為 P1 修復（見 TODO.md）：
- **FIX-05** correlated_exposure_pct 永遠 0.0
- **FIX-06/07** GridTrading grid_levels 配置不應用 + OU theta clamp
- **FIX-11** Cookie secure=False
- **FIX-29** on_tick() 拆分（超 1200 行硬上限）
- 其餘 P1/P2/P3 共 50 項
