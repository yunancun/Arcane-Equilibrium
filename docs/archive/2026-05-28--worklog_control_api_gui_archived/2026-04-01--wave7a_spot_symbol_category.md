# Wave 7a Spot 品類啟用 + 方案 A/B Symbol-Category 映射工程日誌
# Engineering Log: Wave 7a Spot Category Enablement + Symbol-Category Mapping (Plan A/B)
# 日期：2026-04-01

---

## 背景（Context）

品類基礎設施審計（2026-04-01）發現 Bybit V5 API 四個合法 category 中，系統僅啟用了
`linear`（USDT 永續合約）。Spot（634 幣對）完成度約 70%，存在三個 blocker；
Inverse（27 幣對）完成度約 40%，存在五個 blocker。

Wave 7a 目標：先啟用 Spot 品類（阻力最小、市場規模最大），Inverse 留 Wave 7b。

審計同時發現系統對 category 的推斷完全依賴 symbol 命名規則（如 "1000PEPEUSDT" → linear），
這在 spot 引入後容易產生混淆。PM/PA/FA 三方決定同步實施雙層映射架構：
- 方案 B（短期）：PipelineBridge 運行時維護 `_symbol_category_map`，部署時由 StrategyAutoDeployer 登記
- 方案 A（長期）：`SymbolCategoryRegistry`，服務啟動時從 Bybit `/v5/market/instruments-info` 批量填充

---

## 設計決策摘要（PM/PA/FA 三方決定）

決策文件：`docs/decisions/2026-04-01--symbol_category_mapping_design.md`

| 面向 | 決策 |
|------|------|
| 短期（Wave 7a）| 方案 B：部署時登記，覆蓋 active 幣種 |
| 長期（方案 A）| 批量 API 填充，TTL 6h，refresh 失敗保留舊快取 |
| 原則對齊 | 原則 6（失敗默認收縮）· 原則 7（學習/研究隔離 live）· 原則 10（認知誠實，未知→None） |
| fallback 行為 | 命名推斷保留，但升級為 `logger.warning`（不靜默） |
| Wave 7b 待辦 | `TradeIntent.metadata["category"]` 改為必填欄位（有 Registry 後才安全做） |

---

## 工作內容（Work Done）

### SPOT-1：市場掃描器品類注入

- `market_scanner.py`：`categories` 參數預設改為 `["linear", "spot"]`，並確認注入路徑正確
- 補充 `test_market_scanner.py`：16 個新測試，覆蓋 spot symbol 過濾、categories 傳遞、
  threshold 差異（spot 無 funding rate）

### SPOT-2：Paper Engine flip 路徑 category 保留

- `paper_trading_engine.py`：flip 平倉再開倉流程確認 `category` 字段從原有 intent 正確透傳
- 補充測試 3 個：flip 後 category 不遺失的 round-trip 測試

### SPOT-3：Spot 保證金邏輯修正

- `risk_manager.py`：Spot 品類保證金 = notional（等同 100% margin），不除以 leverage
  - 新增 `max_leverage` P0 override：spot 強制 `max_leverage = 1.0`，防止系統錯誤開槓桿
- 補充 `test_risk_manager.py`：+6 個測試（spot margin 計算、leverage override、邊界值）

### SPOT-4：PipelineBridge kline/funding category 修正

- `pipeline_bridge.py`：
  - kline 訂閱 category 從硬編碼 `"linear"` 改為依 symbol 動態查詢（優先 `_symbol_category_map`）
  - Spot funding rate 請求：偵測 spot category 後直接跳過 HTTP 請求（spot 無 funding rate）
  - 引入 `_infer_category_from_symbol()` helper，統一命名推斷邏輯

### SPOT-5：測試補全

- `test_pipeline_bridge_spot.py`（新建）：20 個測試
  - spot symbol 的 kline category 正確傳遞
  - spot symbol 的 funding rate 跳過邏輯
  - `_symbol_category_map` 查詢優先於命名推斷
- `test_risk_manager.py`：+6（見 SPOT-3）
- `test_paper_trading_engine.py`：+3（見 SPOT-2）

### 方案 B：PipelineBridge 運行時映射

- `pipeline_bridge.py`：新增 `_symbol_category_map: dict[str, str]`
  - `register_symbol_category(symbol, category)` 公開方法，供 StrategyAutoDeployer 調用
  - `get_symbol_category(symbol)` 查詢方法，priority：注冊表 > 命名推斷 > None
- `strategy_auto_deployer.py`：部署 intent 時自動調用 `bridge.register_symbol_category()`
  實現雙向注入（deployer 知道 category，bridge 需要 category）

### 方案 A：SymbolCategoryRegistry（新模組）

- 新建 `app/symbol_category_registry.py`：
  - `SymbolCategoryRegistry` 類，啟動時從 Bybit `/v5/market/instruments-info` 批量填充
  - 支持 `linear` / `spot` / `inverse` 三個 category（option 暫不收錄）
  - TTL 6 小時；`refresh()` 失敗時保留舊快取（原則 6：失敗默認收縮）
  - `get(symbol)` 查不到時返回 `None`（原則 10：認知誠實，不猜測）
  - 零 live 模組 import（原則 7：隔離）
  - 模組級單例 `_registry_instance`
- `main.py`：
  - `_startup_integrity_check()` 新增 soft dep 初始化 SymbolCategoryRegistry
  - 使用 `asyncio.to_thread`，fail-open（初始化失敗不阻塞服務啟動）
- `pipeline_bridge.py`：
  - `_infer_category_from_symbol()` 查詢 Registry 優先，命名推斷降級為 `logger.warning`
- 測試：`test_symbol_category_registry.py`（10 個新測試）
  - TTL 過期重刷、refresh 失敗保留快取、get 未知返回 None、單例模式

---

## 並行化工作流（E1 多 Agent 執行）

```
E1-Alpha：SPOT-1 市場掃描器（test_market_scanner.py +16）
E1-Beta：SPOT-3 保證金邏輯（risk_manager.py，test_risk_manager.py +6）
E1-Gamma：SPOT-4 pipeline kline/funding（pipeline_bridge.py 方案 B）
E1-Delta：SPOT-2 paper engine flip + SPOT-5 測試補全

E2 第一輪 Review（Wave 7a SPOT-1~5 + 方案 B）
→ E4 回歸驗證（基準 3103 → 3151，+48）

E1-Alpha（方案 A）：symbol_category_registry.py 新建
E1-Beta（方案 A）：main.py 初始化 + pipeline_bridge.py fallback warning
E1-Gamma（方案 A）：test_symbol_category_registry.py +10

E2 第二輪 Review（方案 A）
→ E4 回歸驗證（基準 3151 → 3161，+10）
```

---

## 測試結果（Test Results）

| 階段 | 基準 | 新增 | 結果 |
|------|------|------|------|
| Wave 7a SPOT-1~5 + 方案 B | 3103 | +48 | 3151 passed |
| 方案 A SymbolCategoryRegistry | 3151 | +10 | 3161 passed |

Pre-existing 失敗說明：commit `1aec8ea` 引入的 9 個測試失敗為已知問題，
與本次工作無關，不列為新增 failure。

---

## 提交記錄（Commits）

| Commit | 內容 |
|--------|------|
| `054d1ae` | Wave 7a：SPOT-1~5 + 方案 B _symbol_category_map 雙向注入，3103→3151 tests |
| `a0f87b6` | 方案 A：SymbolCategoryRegistry 啟動填充 + main.py soft dep + pipeline warning，3151→3161 tests |

---

## 遺留待辦（Wave 7b）

1. **INV-1 CRITICAL**：Paper Engine Inverse 合約 PnL 公式修正（coin-margined 與 USDT-margined 計算不同）
2. **INV-2**：掃描器支持 `inverse` category
3. **INV-3**：qty 步長處理（Inverse 使用合約數量，非幣量）
4. **INV-4**：Symbol 命名規則（BTCUSD 非 BTCUSDT）
5. **INV-5**：Inverse 專屬策略評估
6. **方案 A 補完**：`TradeIntent.metadata["category"]` 改為必填欄位（現有 Registry 後安全執行）
7. **方案 A 補完**：spot `/v5/market/instruments-info` 分頁支持（spot >1000 symbols 需多頁）
