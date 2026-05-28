# Wave 7 — Demo 同步修復 + Spot 品類啟用 + 釘選幣種
# 2026-04-01 工程日誌

---

## 背景 (Background)

用戶啟動 Paper + Demo 雙引擎後發現三類問題：
1. Paper 內部平倉（風控止損/止盈）不同步到 Demo，導致 Demo 殘留幽靈倉位
2. 停止引擎時 Demo 倉位不清空
3. 系統只支持 Linear Perp（U 本位合約），需要擴展到 Spot 現貨

另外，用戶希望強制 Agent 始終監控 BTCUSDT 和 ETHUSDT，因為這兩個最活躍的市場
對學習和進化最有價值。

---

## 問題分析 + 修復

### Fix-1: Paper Engine 內部平倉 Demo 同步（CRITICAL）

**根因**：Paper Trading Engine 有兩條平倉路徑繞過 PipelineBridge：
- `RiskManager.check_positions_on_tick()` → `risk_auto_close`（硬止損/軟止損/止盈/trailing/time stop）
- TP/SL trigger on filled orders → `tp_sl_triggered`

這兩條路徑直接在 Paper state 裡建立平倉訂單，完全不經過 PipelineBridge，
所以 Wave 5b 在 PipelineBridge `_check_stops()` 加的 Demo 同步代碼永遠不會被觸發。

**修復**：
- `_sync_close_to_demo()` — 共用 helper，發送 reduce_only Market 訂單到 Demo
- `risk_auto_close` 路徑末尾加入調用
- `tp_sl_triggered` 路徑末尾加入調用
- 所有 Demo 同步均 fail-open（本地安全優先）

### Fix-2: stop_session() 自動清倉

**根因**：`stop_session()` 只取消 Paper working orders 和結算 PnL，沒有清 Demo 倉位。

**修復**：`_close_all_demo_positions()` 雙遍歷清倉策略：
- Pass 1：根據 Paper 持倉數據平 Demo（已知倉位）
- Pass 2：查 Demo API 找殘留/分歧倉位並清掉（兜底）

### Fix-3: RiskManager max_single_position_pct 對齊

**問題**：動態 qty 公式算出 ~15% 倉位，但 RiskManager 硬上限 10% → 所有訂單被拒。
**修復**：10% → 15%（與 deployer 的 `max_qty_pct=15%` 對齊）。
同時通過 runtime API 即時生效，無需重啟。

---

### Fix-4: Spot 品類全鏈路啟用

**Bybit V5 API 品類確認**：
| Category | 數量 | 狀態 |
|----------|------|------|
| linear   | 600+ | ✅ 已啟用 |
| spot     | 634  | ✅ 本次啟用 |
| inverse  | 27   | 📋 已規劃（TODO） |
| option   | 有   | ❌ 未計劃 |

`margin` 不是獨立 category（API 返回 Illegal category），保證金交易是 spot 的子功能。

**改動**：

**Scanner 多品類掃描**：
- `MarketScanner.__init__` 新增 `categories` 參數
- `scan()` 遍歷所有配置品類，分別抓取 ticker
- `SymbolOpportunity` 新增 `api_category` 字段（"linear"/"spot"）
- Spot ticker 的 `fundingRate` 為 null，graceful 降級為 0
- 驗證結果：14 linear + 6 spot 機會，共 20 個

**Strategy 品類透傳**：
- `StrategyBase._default_metadata` 字典 — `_emit_intent()` 自動合併到每個 intent
- Deployer 在部署時注入 `api_category` 到 `strategy._default_metadata`
- 所有 spot 策略的 intent 自動攜帶 `metadata["category"]="spot"`

**Paper Engine 持倉品類**：
- `project_position_after_fill()` 新增 `category` 參數
- 新建持倉記錄 `category` 字段
- `submit_order()` 透傳 category

**完整鏈路**：
```
Scanner(spot tickers) → Opportunity(api_category="spot")
  → Deployer → strategy._default_metadata["category"]="spot"
    → Intent.metadata["category"]="spot"
      → PipelineBridge → Paper Engine(category="spot") → Demo Connector(category="spot")
        → Position(category="spot")
```

---

### Fix-5: 產品族 demo_reserved 模式解鎖

**後端**：`ALLOWED_MODE_SWITCHES` 新增 `demo_reserved`（`live_reserved` 仍鎖定）
**前端**：Mode 下拉選單解鎖 demo_reserved，Spot 標記為 agentReady

---

### Fix-6: GUI 品類標籤

**common.js** 新增 `ocCategoryTag(category)` 共用函數：
- Linear = 🔵 藍色 `#3b82f6`
- Spot = 🟢 綠色 `#22c55e`
- Inverse = 🟡 橙色 `#f59e0b`
- Option = 🟣 紫色 `#a855f7`

6 個表格新增「品类」列：
- tab-paper.html：持倉 / 訂單 / 成交
- tab-demo.html：持倉 / 訂單 / 成交

---

### Fix-7: BTCUSDT + ETHUSDT 釘選幣種

**需求**：BTC 和 ETH 是最活躍最競爭的市場，持續曝光對學習和進化最有價值。

**實現**：`StrategyAutoDeployer.pinned_symbols` 參數
- 首次掃描回調自動部署 MA_Crossover 策略
- `_find_weakest_position()` 排除釘選幣種（不可被再平衡驅逐）
- 風控條件仍然完整生效（H0 Gate / Guardian / risk checks）
- 釘選 = 「始終監控並嘗試交易」，不是「無視條件強制交易」

---

## 修改檔案清單

| 檔案 | 變更 |
|------|------|
| `app/paper_trading_engine.py` | +113 行：_sync_close_to_demo + _close_all_demo_positions + stop_session 清倉 + risk/tp_sl 路徑同步 + position category |
| `app/risk_manager.py` | max_single_position_pct 10→15 |
| `app/main_legacy.py` | ALLOWED_MODE_SWITCHES +demo_reserved |
| `market_scanner.py` | +categories 參數，多品類掃描，api_category 字段 |
| `strategies/base.py` | +_default_metadata，_emit_intent 自動合併 |
| `strategy_auto_deployer.py` | +pinned_symbols，首次部署+再平衡保護+api_category 注入 |
| `app/phase2_strategy_routes.py` | categories=["linear","spot"], pinned_symbols=["BTCUSDT","ETHUSDT"] |
| `app/static/common.js` | +ocCategoryTag() 品類標籤函數 |
| `app/static/tab-paper.html` | 持倉/訂單/成交 +品类列 |
| `app/static/tab-demo.html` | 持倉/訂單/成交 +品类列 |
| `app/static/tab-settings.html` | demo_reserved 解鎖 + Spot agentReady + 品類狀態更新 |

---

## 測試結果

```
2677 passed / pre-existing failures unchanged / 0 新增失敗
Scanner 驗證：14 linear + 6 spot = 20 opportunities（live API 測試通過）
```

---

## Commits

| Hash | 說明 |
|------|------|
| `ab31353` | fix(sync): Paper Engine 內部平倉 Demo 同步 + stop_session 自動清倉 |
| `2b28ab9` | docs: Wave 7 Demo 同步 + Spot/Inverse 品類規劃寫入 TODO/CLAUDE |
| `be7d4d7` | feat(spot): Scanner 多品類 + 策略品類透傳 + Position category |
| `2fe3b7a` | fix(scanner): tickers variable rename |
| `ca0f862` | feat(gui): demo_reserved 模式解鎖 + Spot agentReady |
| `6d06430` | feat(gui): 持倉/訂單/成交品類標籤（顏色區分） |
| `b57ddbb` | feat(agent): BTCUSDT + ETHUSDT 釘選幣種 |

---

## 未修復項目（已規劃，非本次範圍）

| 項目 | 狀態 | 說明 |
|------|------|------|
| INV-1: Inverse PnL 公式 | TODO | 幣本位 PnL = qty × (1/entry - 1/exit) |
| INV-2: Scanner inverse 支持 | TODO | USDT 過濾器排除 inverse 合約 |
| INV-3: qty 步長精度 | TODO | BTCUSD step=1（整數合約） |
| SPOT-3: Spot 保證金邏輯 | TODO | 現貨無槓桿，margin = 100% notional |
| qty step cache | 已編碼但被 linter 還原 | 需要重新實現 |
