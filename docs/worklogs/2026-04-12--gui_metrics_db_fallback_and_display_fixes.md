# 2026-04-12 工程日誌：GUI 指標 DB 降級 + 顯示修復

## 概要 / Summary

本次 session 修復了 4 個 GUI/API 問題，橫跨 Rust engine、PyO3 bridge、Python API、前端 JS 四層。核心改動是為 Performance Metrics 加入 DB 降級讀取，解決引擎重啟後歷史交易數據丟失的問題。

---

## 修復清單

### 1. Live engine 顯示「已暫停」+ 啟動按鈕未灰掉

| 項目 | 內容 |
|------|------|
| 影響 | Live tab 右上角狀態顯示「已暫停」，Start 按鈕可點擊（應灰掉） |
| 根因 | `get_live_session_status()` 用 `rust.get_paper_state(engine="live")` 讀取狀態，該函數只返回嵌套的 `paper_state` 子對象 `{balance, positions, ...}`，不含頂層的 `paper_paused` 字段。`rust_state.get("paper_paused", True)` 因找不到 key 而默認 `True` → session_state="paused" |
| 修復 | 額外讀取 `engine_snap = rust.get_engine_snapshot(engine_kind)`，從完整快照頂層取 `paper_paused` |
| 文件 | `live_session_routes.py` L568-590 |
| 驗證 | API 返回 `session_state: "active"`；GUI badge 顯示「實盤運行中」；Start 按鈕灰掉 |

### 2. Performance Metrics 全部為 0（Paper / Live / Demo）

| 項目 | 內容 |
|------|------|
| 影響 | Paper 和 Live 的性能指標頁面（總成交、勝率、夏普比率等）全部顯示 0 |
| 根因 | `compute_full_metrics(state)` 期望 `state` 中有 `fills`/`orders`/`pnl` 列表，但 Rust engine 的 `paper_state` 只有 `{balance, peak_balance, total_realized_pnl, total_fees, trade_count, positions}`。交易數據直接寫入 PostgreSQL `trading.fills`，不在快照中累積。且引擎重啟後計數器歸零。DB 實際有 paper: 1336 fills / demo: 68 fills |
| 修復 | (a) 新增 `fetch_fills_from_db(engine_mode)` — 使用 psycopg2 從 `trading.fills` 讀取歷史成交；(b) `compute_full_metrics()` 新增 `engine_mode` 參數，snapshot 無 fills 時自動 DB 降級；(c) 從 DB fills 重建 PnL summary；(d) `restart_all.sh` 傳遞 `OPENCLAW_DATABASE_URL` 給 API server |
| 文件 | `paper_trading_metrics.py` (+60 行 DB 讀取 + compute_full_metrics 改造)、`paper_trading_routes.py` L771、`live_session_routes.py` L1183-1185、`restart_all.sh` L23-31 |
| 驗證 | Paper metrics: 1336 fills / 753 round trips / 32.75% win rate / Sharpe 0.029 / PnL 497199。Live metrics: 1 fill |

### 3. Live 掛單 Price 和 Status 顯示 "--"

| 項目 | 內容 |
|------|------|
| 影響 | Live tab 掛單表格的 Price 和 Status 列全部顯示 "--" |
| 根因 | (a) **Price**: Rust `OrderInfo` struct 缺少 `trigger_price` 字段。停損單 `price=0.0` 在 JS 中 falsy → 嘗試 `o.triggerPrice`（不存在）→ "--"。(b) **Status**: JS 用 camelCase `o.orderStatus` 但 Rust serde 序列化為 snake_case `o.order_status` → undefined → "--" |
| 修復 | (a) `OrderInfo` 新增 `pub trigger_price: f64` + `parse_order_info_item` 解析 Bybit `triggerPrice`；(b) JS 改為優先 snake_case（`o.order_status \|\| o.orderStatus`），price 用 `parseFloat()` 避免 falsy 0.0 問題 |
| 文件 | `rust/openclaw_engine/src/order_manager.rs` L197-225, L689；`tab-live.html` L494-497 |
| 驗證 | API 返回 `trigger_price: 0.2146`；GUI 正確顯示觸發價和 Untriggered 狀態 |
| 附帶 | PyO3 bridge 需要 `maturin develop --release` 重新安裝到 API venv（`.venv/`）才能生效。此前 `.so` 停留在 4 月 4 日版本 |

### 4. Demo 夏普比率硬編碼 N/A

| 項目 | 內容 |
|------|------|
| 影響 | Demo tab Performance Metrics 中夏普比率永遠顯示 N/A |
| 根因 | `tab-demo.html` L597 硬編碼 `'N/A'`（原始佔位符，未實現） |
| 修復 | 基於 round-trip PnL 計算 Sharpe（≥2 筆交易時啟用），`mean/std` 比率 |
| 文件 | `tab-demo.html` L582-596 |
| 備注 | AI cost 維持 N/A — 確實未接入每引擎成本追蹤，屬 TODO |

---

## 上一次 session 遺留（同日稍早）

### DB 跨管線 ID 碰撞修復（commit `d670759`）

所有 DB record ID（context_id / intent_id / verdict_id / fill_id / order_id）嵌入 `engine_mode` 前綴，防止三管線同 tick 時 ID 重複被 `ON CONFLICT DO NOTHING` 靜默丟棄。Signal 寫入限 Paper-only（V015 Signal Diamond 對齊）。

---

## 改動文件匯總

| 文件 | 改動類型 | 行數 |
|------|---------|------|
| `rust/openclaw_engine/src/order_manager.rs` | Rust struct + parser | +5 |
| `app/paper_trading_metrics.py` | DB fallback + compute 改造 | +65 |
| `app/live_session_routes.py` | session_state 修復 + metrics engine_mode | +8/-3 |
| `app/paper_trading_routes.py` | engine_mode 參數 | +1/-1 |
| `app/static/tab-live.html` | snake_case 兼容 + trigger_price | +5/-3 |
| `app/static/tab-demo.html` | Sharpe 計算 | +12/-1 |
| `helper_scripts/restart_all.sh` | API server DB URL 傳遞 | +5/-1 |

## 測試基準線

- Rust engine lib: **935** passed, 0 failed
- Rust core: **366** passed
- Python paper_metrics: **22** passed
- 0 cargo warnings

## 發現但未修復（非阻塞）

1. **Engine 重啟後 `paper_state` 計數器歸零** — `total_realized_pnl` / `total_fees` / `trade_count` 不持久化。DB 降級已繞過此問題，但根本修復應讓引擎啟動時從 DB 恢復累計值。
2. **Demo AI cost 無追蹤** — 前端硬編碼 N/A，後端無 per-engine AI 成本歸因。
3. **PyO3 .so 部署流程** — maturin 安裝到系統 Python（`~/.venv`），API server 用另一個 venv（`control_api_v1/.venv`），需手動 `maturin develop` 到正確 venv。應統一或自動化。
4. **Paper engine paper_state 的 `total_realized_pnl` 異常** — DB 顯示 paper 總 PnL 497199（10000 起始、max drawdown 245%），疑似 paper 模式未正確限制槓桿/倉位，導致 PnL 遠超初始餘額。需檢查 paper 風控配置。
