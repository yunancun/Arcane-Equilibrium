# 2026-04-15 工程日誌 — GUI P&L 可視化 Step 1（PnL 欄 + 拉高 trend + 三模式統一）
# Worklog — GUI P&L Visibility Step 1 (per-fill PnL column + enlarged trend + three-mode parity)

**Session**: /compact 後續會話
**Commits**: 本 session 單一 commit（5 檔 src + 1 檔 worklog）
**Branch**: `main`（本地領先 `origin/main`，未 push）

---

## 一、背景 / Context

Operator 反映 Paper tab 成交歷史「最近 50 筆」表格看不出哪筆賺哪筆虧、沒有每日曲線或百分比顯示。

審計後端（Explore agent）得出四點現況：
1. **Paper `/api/v1/paper/fills`**：Rust `TimestampedFill` struct 欄位僅 `timestamp_ms/symbol/is_long/qty/price/fee/strategy` — **沒有 `realized_pnl`**。前端 `f.realized_pnl || 0` fallback 永遠拿到 0。
2. **DB `trading.fills`**：早就有 `realized_pnl`（real 欄位），按 `engine_mode` 分區（V015）。近 7 日統計：paper 1443 closes / 699 wins / 744 losses，demo 599 closes / 310 wins / 289 losses。**數據在 DB、不在 Rust in-memory buffer**。
3. **Demo/Live `/api/v1/strategy/demo/fills` & `/api/v1/live/fills`**：直接透傳 Bybit v5 execution API response，字段叫 `closedPnl`（string，"0" for opens，非零 for closes）。
4. **Paper 已有 sparkline**（tab-paper.html:77-82 SVG），但 height=48 被壓扁，Demo/Live 無此元件。

兩階段方案推給 operator：
- **Step 1（本 session）**：純前端 + 一次 Python 端點改寫，零 Rust 改動，零引擎重啟。
- **Step 2（未做）**：新增 `/api/v1/{mode}/daily-pnl` 日聚合端點 + Chart.js 柱狀圖 + equity curve。

Operator 指令：「先做 step1」→ 加欄位 → 跑出全 `—` → 發現 Rust struct 缺欄位 → 改走 PG → 再加需求「拉高 Paper sparkline + 複製到 Demo/Live」。

---

## 二、改動 / Changes

### 1. `common.js` 新增兩個共用 helper（+75 行）

**`ocPnlCell(raw)`** — 單一 `<td>` 渲染：
- `|pnl| < 0.0001` 或非數 → 灰色 `—`（開倉單或無數據）
- `pnl ≥ 0` → 綠色 `+x.xxxx`
- `pnl < 0` → 紅色 `-x.xxxx`
- 接受 number 或 string（`parseFloat` 處理 Bybit 的字串 `closedPnl`）

**`ocPnlTrend(lineId, labelId, fills, zeroLineId)`** — 累計 PnL 折線：
- fallback 鏈：`realized_pnl || closedPnl || pnl || 0`
- 最舊在左、最新在右（`fills.reverse().slice(0, 50)`）
- y 軸 `[min(series, 0), max(series, 0)]` — **強制包含 0**，零線永遠在範圍內
- 傳 `zeroLineId` 自動調 `<line>` 的 y 座標（虛線零基準）
- 最終值決定整條線顏色（綠/紅）+ 下方 label 文字

### 2. `tab-paper.html`（-40 / +20 行淨減）

- 表頭加 `<th>盈亏 / PnL</th>`，colspan 7→8（3 個 empty/loading row 都改）
- `loadFills` 渲染每筆加 `+ ocPnlCell(f.realized_pnl)`
- **SVG height 48 → 120**，viewBox `0 0 400 48` → `0 0 400 120`，stroke-width 1.5→2
- 新增 `<line id="pnl-sparkline-zero">` 虛線零線（`stroke-dasharray="3,3"`）
- label font-size 8→10，x=4 y=114（原 y=42 適配 48 高）
- **刪除** 原 inline `updatePnlSparkline()` 函數（~35 行），call site 改呼叫 `ocPnlTrend('pnl-sparkline-line', 'pnl-sparkline-label', fills, 'pnl-sparkline-zero')`

### 3. `tab-demo.html`（+24 行）

- 表頭加 PnL 欄位 + colspan 7→8
- `loadDemoFills` 渲染加 `ocPnlCell(f.closedPnl != null ? f.closedPnl : f.realized_pnl)`（優先 Bybit API 欄位）
- PnL Overview 卡片底部新增 SVG 塊（與 paper 同規格，ID prefix 為 `demo-pnl-*`）
- 渲染表格後呼叫 `ocPnlTrend('demo-pnl-line', 'demo-pnl-label', fills, 'demo-pnl-zero')`

### 4. `tab-live.html`（+37 行）

- 表頭加 PnL 欄位 + colspan 7→8（3 處 empty/loading/error 都改）
- `loadFills` 渲染加 PnL 欄（`closedPnl || realized_pnl` fallback）
- PnL Overview 卡片底部新增 SVG 塊（ID prefix `live-pnl-*`）
- **關鍵行為變更**：`refreshPage()` 現在每 15s 無條件呼叫 `loadFills()` 讓 trend chart 保持即時；但表格本身仍是折疊懶加載（`toggleFills()` 路徑不變）。Bybit API 每 15s 加一次 `v5/execution/list` 呼叫，成本可忽略
- trend chart 呼叫點：`loadFills()` 成功分支 + 空數據分支都呼叫（空數據讓 chart 顯示 "no data"）

### 5. `paper_trading_routes.py:596` `/api/v1/paper/fills` 改寫（+43 行）

**原行為**：從 Rust IPC 讀 `recent_fills`（in-memory ring buffer，50 上限）。
**新行為**：優先從 PG 讀 `trading.fills WHERE engine_mode='paper' ORDER BY ts DESC LIMIT ?`，Rust IPC 降為 DB 不可用時的備援。

理由：
- DB 由 Rust `trading_writer` 同步寫入，延遲 μs 級，與 in-memory buffer 實質等效
- DB 有 `realized_pnl` 欄位，Rust struct 沒有
- **避免 Rust rebuild**（上次 14:55 剛 rebuild，避免二度擾動 G-2 監控 daemon）

PG 回傳欄位映射到 GUI 期望：
- `ts` (timestamptz) → `timestamp_ms` (int ms since epoch)
- `side` (text "Buy"/"Sell") → 直透，同時塞 `is_long = (side == "Buy")` 給 GUI fallback
- `realized_pnl` (real) → `float()` 轉換
- `category` 根據 symbol 後綴推斷：`*USDT → linear`，純 `*USD → inverse`
- `fill_id` / `order_id` 沒帶（GUI 不用）

響應包 `source: "pg_trading_fills"` 方便 DevTools 驗證新舊路徑。

---

## 三、驗證 / Verification

### Pre-flight

| 項目 | 結果 |
|------|------|
| DB 有 realized_pnl 分佈 | paper 1443 closes / 7 日（699 wins / 744 losses），demo 599 closes（310 wins / 289 losses） |
| `db_pool.get_conn()` API | `program_code/.../app/db_pool.py:79` 存在，sig 兼容 |
| common.js 被三 tab 共載 | 15/15 html 都引用 `common.js` |
| `.green` / `.red` CSS class | 定義於 `common.js:531` + `styles.css:8`，可用 |

### Deploy

- **API 重啟**：`bash helper_scripts/restart_all.sh --api-only` → uvicorn PID 857922，4 workers，listening :8000
- **Rust 引擎無變動**：PID 693387 繼續跑（14:55 rebuild 的 FIX-PHASE1 binary）
- **Watchdog / G-2 daemon / canary rotation 皆未受影響**

### Post-flight

| 驗證項 | 結果 |
|--------|------|
| 後端 `/api/v1/paper/fills` 走 PG 路徑 | 代碼靜態驗證 ✅；用戶端視覺驗證 ⏳（懷疑瀏覽器 cache） |
| Paper tab 前端 PnL 欄位 | colspan 一致、`ocPnlCell` 調用 ✅ |
| Paper sparkline 高度 | SVG `height="120"` ✅ |
| Demo tab SVG 結構 | 內嵌於 PnL Overview 卡片 ✅ |
| Live tab SVG 結構 + 懶加載解除 | `refreshPage` 加 `loadFills()` ✅ |
| 401 未測到真實 response body | curl 無 auth token，回 401 屬預期 |

**已知未解**：用戶最後回報 Paper tab 仍顯示全 `—`。可能原因：
1. **瀏覽器 cache**（最常見）— 需 `Ctrl+Shift+R` / `Cmd+Shift+R` 硬刷
2. **DB 查詢 silent fallback** — 若 `db_pool.get_conn()` 拋異常會走 Rust 備援，response `source` 會是 `rust_engine` 而非 `pg_trading_fills`。接手時在 DevTools Network tab 檢查該欄位可快速判別

**未做視覺驗證**：無法從 CLI 進入瀏覽器確認渲染，只能靜態推理 + DB 數據驗證 + API 重啟成功。已明確告知 operator。

---

## 四、留尾 / Follow-ups

1. **用戶硬刷後視覺確認**：
   - Paper tab：PnL 欄應有綠 `+x.xxxx` / 紅 `-x.xxxx`，sparkline 變 2.5× 高，有虛線零線
   - Demo tab：同樣 sparkline 顯示（若 Bybit recent 50 執行含 close，就有曲線）
   - Live tab：PnL Overview 卡片底部有 sparkline，表格展開前即顯示

2. **Rust `TimestampedFill` struct 缺 `realized_pnl`**（`rust/openclaw_engine/src/pipeline_types.rs:72`）：
   - 本 session 走 PG 旁路繞過，但 Rust 這個缺口本身是**資訊不對稱**的設計缺陷
   - `push_capped` 兩處構建 `TimestampedFill`（`commands.rs:187` 和 `:395`）時 `realized_pnl` 都在 scope 內
   - 下次有 Rust rebuild 機會時可一併補欄位，那時 `/api/v1/paper/fills` 可選擇退回用 Rust IPC（DB 讀會省下來）
   - **非阻塞**，Python 旁路已可用

3. **Step 2 尚未啟動**：日 P&L 端點 + Chart.js equity curve 都未做。Operator 可隨時拉起，建議實作：
   - `GET /api/v1/{mode}/daily-pnl?days=30` → 回傳 `[{date, realized_pnl, fill_count, starting_balance}]`
   - SQL：`SELECT DATE(ts) d, SUM(realized_pnl) pnl, COUNT(*) n FROM trading.fills WHERE engine_mode=$1 AND ts > NOW()-'30d' GROUP BY 1 ORDER BY 1 DESC`
   - starting_balance 若要精準需加 `paper_state.balance` 日照快照寫入；退而求其次可從 fills 累積反推（含不實倉 noise）

4. **CSP 噪音**（operator 提到但未處理）：`common.js:282` 拉 CoinGecko 匯率違反 `connect-src 'self'`。`catch(_)` 已兜底功能不掛，但 console 吵。選項：
   - 加 `api.coingecko.com` 到 `connect-src` header
   - 移除外部依賴，匯率從內部 endpoint 供

5. **未相關未 commit 檔案**（本 commit 未收錄，屬另一 lane 工作）：
   - `program_code/ml_training/{calibration,onnx_exporter,run_training_pipeline,quantile_trainer,quantile_reports}.py` + settings snapshots
   - `docs/worklogs/2026-04-15--lane_a_ml_mit_26_trainer_handover.md`
   - 這些是 ML-MIT #26 lane 的進行中工作，不納入 GUI P&L commit 範圍

---

## 五、經驗提煉 / Lessons

- **Audit 別信片面結論**：Explore agent 初審引用舊 sparkline 代碼時寫「`realized_pnl` stored in `f.realized_pnl` field」，但 `f.realized_pnl || 0` 是前端 fallback、不代表後端真的有吐。**根因 grep 要追到 struct 定義**，Python response 包裝只是中間層。這次多繞了 20 分鐘，下次直接 `rg 'struct TimestampedFill'` 起手會更快。

- **DB 是 authoritative read path 的自然候選**：in-memory buffer 設計假設是低延遲讀取，但資料完整度輸 DB。當 GUI 需要的欄位 in-memory 沒有時，**直接改讀 DB** 比 rebuild Rust 便宜 10 倍（尤其剛 rebuild 過）。搭配 Rust IPC 作為 PG 不可用時的 graceful fallback，行為退化可控。

- **三 tab 的複製粘貼要抽 helper**：`ocPnlCell` + `ocPnlTrend` 兩個 helper 抽到 common.js 後，三個 tab 只各加 1-2 行 wire call。若是 inline 三份相同邏輯，未來 y 軸加格線、hover tooltip、滑動窗口等增強會變三倍修改成本。**抽象的 threshold = 3 個相同調用點且未來會擴展**，這次剛好。

- **Live 的 lazy-fills 和 always-on trend 衝突處理**：原設計 `_fillsLoaded = false` → 只在折疊展開時 fetch。加了 trend chart 後需要 always-on，但表格懶加載是有意為之。最終決策：`refreshPage()` 無條件呼叫 `loadFills`（便宜），但 DOM 渲染對 collapsed `<div>` 不可見，不影響 UX。一行代碼的事，比建第二條路徑簡單。

- **瀏覽器 cache 這道坎**：API 重啟後 operator 回報「還是 —」，高機率是 browser cache。Step 1 的 validate loop 應包含「DevTools Network 看 `source` 欄位」這一步，不能只靠人眼看渲染。下次交付前端改動時 proactively 在 worklog 留這個 debug hint。

---

**作者**：Claude（main session，PM+Conductor）
**接手指引**：
1. 若 operator 硬刷後 PnL 仍 `—`：DevTools Network 看 `/api/v1/paper/fills` response 的 `source` 欄位；`pg_trading_fills` → 有 PnL 應該顯示，檢查 CSS 載入；`rust_engine` → DB pool 有問題，查 API log
2. 若視覺 OK：TODO 加 Step 2（日 PnL 端點 + equity curve）排程
3. CSP 噪音 + Rust struct 補欄位兩個留尾都是非阻塞，下次相關改動時順手處理
