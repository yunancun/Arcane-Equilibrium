---
date: 2026-04-01
topic: Symbol → Category 映射策略
status: DECIDED
participants: PM / PA / FA
---

## 問題定義

Bybit V5 API 有四個合法 category：`linear`（USDT 永續）、`spot`（現貨）、`inverse`（幣本位永續）、`option`。
`BTCUSDT` 這類 symbol 命名格式在 `linear` 和 `spot` 之間完全相同——純靠名稱規則**無法區分**。

當前 `PipelineBridge._infer_category_from_symbol()` 的實作（pipeline_bridge.py:1678–1700）採用命名啟發式：
- `endswith("USD")` 且非 USDT/USDC → inverse
- 包含 `-` → option
- 其餘 → **fallback linear**（BTCUSDT 現貨也會被推斷為 linear）

隨著 Wave 7a 啟用 Spot 品類、系統覆蓋數百個 symbol，這個 fallback 會導致：
現貨 symbol 的 K 線查詢、資金費率跳過、submit_order 路由，全部走錯 category。

---

## FA（Functional Auditor）業務層分析

### category 在哪裡「誕生」

代碼審查確認，category 有**兩條產生路徑**：

**路徑 A（正常路徑，掃描器驅動）：**
```
MarketScanner.scan()
  → 按 self._categories 迴圈呼叫 Bybit /v5/market/tickers?category={cat}
  → ticker 的 api_category 直接來自 API 回應對應的 cat（market_scanner.py:130–138）
  → SymbolOpportunity.api_category 設為該值（market_scanner.py:182）
  → StrategyAutoDeployer._deploy_strategy()
      api_category = getattr(opp, "api_category", "linear")
      if api_category != "linear":
          strategy._default_metadata["category"] = api_category
      （strategy_auto_deployer.py:474–476）
  → TradeIntent.metadata["category"] = api_category
  → PipelineBridge._process_pending_intents()
      category = intent.metadata.get("category", "linear")（pipeline_bridge.py:737）
  → submit_order(category=category)（pipeline_bridge.py:752）
```

**路徑 B（補丁路徑，_infer_category_from_symbol 介入）：**
```
PipelineBridge._refresh_kline_volume()（pipeline_bridge.py:1729）
  → kline_category = self._infer_category_from_symbol(symbol)
  → Bybit /v5/market/kline?category={kline_category}&symbol={symbol}

PipelineBridge._fetch_single_funding_rate()（pipeline_bridge.py:1782）
  → resolved_category = category or self._infer_category_from_symbol(symbol)
```

此外，`strategy_auto_deployer.py:475` 有一個隱性 bug：
`if api_category != "linear":` — **spot category 不會被注入** 到 `_default_metadata`，
因為 `"spot" != "linear"` 是 True，這段邏輯看起來正確；但**注意反向**：
如果掃描器配置只掃 `linear`（預設），`BTCUSDT` spot 根本不會出現在掃描結果裡，
所以正常路徑目前並不產生 spot intents——這反而是「未來啟用 spot 掃描後才會觸發」的問題。

### Operator 和 Agent 什麼時候需要知道 category

| 時機 | 需要 category 的原因 |
|------|---------------------|
| K 線查詢（REST）| `/v5/market/kline?category={cat}` — 用錯 category 返回空資料 |
| 資金費率查詢 | `/v5/market/tickers?category={cat}` — spot 無資金費率，要提前跳過 |
| submit_order | `/v5/order/create?category={cat}` — category 錯誤 → Bybit retCode 非零，訂單失敗 |
| H0 Gate check | `pipeline_bridge.py:510–515` — H0 需要 category 做健康/冷卻判斷 |
| 對賬（reconcile）| Bybit `/v5/position/list?category={cat}` — category 錯誤返回空列表，倉位對賬永遠失敗 |

### 失敗模式分析

**現在（Wave 7a 前）的實際影響：**
- `_refresh_kline_volume`（路徑 B）：已部署 SPOT-4 補丁，會呼叫 `_infer_category_from_symbol`，
  但 `BTCUSDT` spot symbol 會被推斷為 `linear`，K 線查到 linear 永續的資料（數據混淆，不崩潰）。
- 資金費率：`_fetch_single_funding_rate` 對 spot symbol 呼叫 `_infer_category_from_symbol`，
  推斷為 `linear`，會去拉一個不正確的 tickers endpoint，回傳 fundingRate=0 而非跳過。
  功能上看似「正常」，但語義錯誤。

**Wave 7a 啟用 Spot 掃描後的新失敗模式：**
1. **K 線靜默出錯**：`_refresh_kline_volume` 對 spot symbol 查 `linear` endpoint → 返回空 → 指標計算失敗 → 策略信號中斷
2. **submit_order 失敗**：若 intent 沒有攜帶 `metadata["category"]`（手動訂單、舊路徑），
   pipeline_bridge 預設 `"linear"` → Bybit API 拒絕 spot 訂單 → `retCode != 0`
3. **資金費率錯誤累計**：spot symbol 被誤算為有資金費率，影響 funding_arb 策略評分
4. **對賬永久失敗**：reconcile 用 `linear` 查 spot 倉位 → 永遠查不到 → 誤判倉位分歧

---

## PA（Project Architect）方案比較

### 方案 A：Symbol Registry（中央真相源）
在啟動時從 Bybit API 批量獲取所有 symbol 的 category 映射，存入本地字典快取。

```python
class SymbolCategoryRegistry:
    _cache: dict[str, str] = {}   # "BTCUSDT" → "linear" 或 "spot"

    def get(self, symbol: str) -> str:
        return self._cache.get(symbol, "linear")

    def refresh(self):
        for cat in ("linear", "spot", "inverse"):
            r = requests.get(f"/v5/market/instruments-info?category={cat}")
            for item in r["result"]["list"]:
                self._cache[item["symbol"]] = cat
```

- **優點**：
  - 完全正確，包含「同名 symbol 在不同 category 的區分」（如若未來出現 BTCUSDT spot+linear 共存）
  - 符合原則 10（認知誠實）：明確知道真相而非推斷
  - 符合原則 5（真相源）：單一權威來源
- **缺點**：
  - 啟動時需 3 次 HTTP 請求（linear/spot/inverse）；網路故障時啟動降級
  - 快取可能過期（新上市幣種需刷新）；需要定期 TTL 或手動 refresh
  - 需要注入到 `PipelineBridge` 和 `MarketScanner` 兩個類
  - 工時估算：**~3 小時**（Registry 類 + 注入兩處 + TTL + 測試 ~15 個）

### 方案 B：Category 跟著 SymbolOpportunity 走（現有設計延伸）
強化掃描器路徑，確保 `api_category` 在**整個生命週期**都被傳遞，不允許任何地方「重新推斷」。

目前的問題是：strategy_auto_deployer.py:475 有 `if api_category != "linear":` 條件，
`"spot"` 會觸發這個條件（因為 `"spot" != "linear"` 是 True），所以掃描路徑理論上**是正確的**。
真正的問題在於**路徑 B**（`_refresh_kline_volume`、`_fetch_single_funding_rate`）
這兩個函數只拿到 `symbol`，沒有 `api_category`——它們查不到掃描器的上下文。

延伸方案：在 `PipelineBridge` 內部維護一個 `_symbol_category_map: dict[str, str]`，
由掃描器路徑（strategy_auto_deployer 部署時）填入，`_refresh_kline_volume` 等函數從中查詢。

```python
# PipelineBridge 新增
self._symbol_category_map: dict[str, str] = {}

# StrategyAutoDeployer 部署時通知
bridge.register_symbol_category("BTCUSDT", "spot")

# _refresh_kline_volume 使用
kline_category = self._symbol_category_map.get(symbol) or self._infer_category_from_symbol(symbol)
```

- **優點**：
  - 零新增外部 HTTP 請求
  - 架構上「category 跟著 symbol 進入系統時確定」，語義清晰
  - 符合現有設計意圖（掃描器是 category 的真相源）
  - 工時估算：**~1.5 小時**（新增 dict + 注入點 + 測試 ~8 個）
- **缺點**：
  - 手動訂單（非掃描器路徑）沒有 category → 仍需 fallback
  - 服務重啟後 `_symbol_category_map` 清空，需重新部署策略才能恢復（對持倉對賬有影響）
  - 不解決啟動時對賬的 category 問題

### 方案 C：命名啟發式擴展（現有方案延伸）
在 `_infer_category_from_symbol` 加入白名單或黑名單。例如：

```python
_KNOWN_SPOT_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT", ...})
if symbol in _KNOWN_SPOT_SYMBOLS:
    return "spot"
```

- **優點**：零依賴，改動最小，1 小時可完成
- **缺點**：
  - 硬編碼靜態清單，Bybit 有 634+ spot 品對，無法全覆蓋
  - 維護成本指數上升；命名規則無法保證唯一性
  - 根本上是「用補丁修補補丁」，技術債持續積累
  - **不推薦**（PA 明確反對）

### 方案 D：TradeIntent 強制 category 字段
將 `TradeIntent` dataclass 的 `category` 改為必填（非 Optional）。

```python
@dataclass
class TradeIntent:
    symbol: str
    side: str
    category: str          # 必填，不再有默認值
    ...
```

- **優點**：
  - 靜態分析即發現遺漏；任何創建 intent 的地方必須明確提供
  - 從設計層面消除「忘記帶 category」的可能性
- **缺點**：
  - 需修改**所有** TradeIntent 創建點（影響範圍廣，存在多個策略類）
  - 單獨使用不解決路徑 B（K 線查詢、資金費率查詢）的問題
  - 工時估算：**~2 小時**（影響 5-8 個文件 + 回歸測試修改）
  - 適合作為**補充措施**，而非主要方案

### 方案比較矩陣

| 方案 | 正確性 | 實作成本 | 維護成本 | 覆蓋範圍 |
|------|--------|---------|---------|---------|
| A Symbol Registry | 最高 | ~3h | 低（TTL 自動刷新） | 全覆蓋（含手動訂單） |
| B 掃描器路徑強化 | 高（掃描路徑） | ~1.5h | 低 | 覆蓋掃描路徑；手動路徑需 fallback |
| C 命名啟發式擴展 | 低 | ~1h | 極高 | 不完整 |
| D TradeIntent 必填 | 高（intent 路徑）| ~2h | 低 | 只覆蓋 intent 路徑 |

---

## PM（Project Manager）優先順序與決策

### 現有緊迫度評估

Wave 7a Spot 品類啟用是**當前進行中的工作**（CLAUDE.md §十三.4）。
如果在 Spot 掃描器啟用前不解決 category 映射問題，Wave 7a 上線後：
- K 線資料靜默出錯（不崩潰，但策略信號錯誤）
- submit_order 對 spot symbol 可能失敗（Bybit retCode 非零）
- 資金費率語義錯誤（spot 被當 linear 查）

這三個後果在 Paper/Demo 模式下**不會引發安全事故**（live_execution_allowed=false），
但會導致 Wave 7a 功能實際上是壞掉的，無意義運行。

### 決策：方案 B（短期）+ 方案 A（長期）組合

**原因：**

1. **方案 B 先行（Wave 7a 前完成）**：
   - 1.5 小時工時，Wave 7a 合理範圍內
   - 解決掃描器路徑（佔 99% 的正常交易流量）
   - `_symbol_category_map` 作為運行時「已知 symbol 的 category 快取」
   - `_infer_category_from_symbol` 降格為真正的 last-resort fallback（且記錄 warning）

2. **方案 A 後補（Wave 7b 或獨立任務）**：
   - 解決服務重啟後快取丟失問題（對賬路徑）
   - 解決手動訂單路徑的 category 缺失
   - 啟動時填充 `_symbol_category_map` 從 API，之後由掃描器更新維護

3. **方案 D 作為補充**：
   - 在方案 B 實作時，同步讓 `_infer_category_from_symbol` 的 fallback 路徑加 `logger.warning`
   - TradeIntent 的 `metadata["category"]` 缺失時，也加 warning（而非靜默 fallback）
   - 正式改為必填字段放在方案 A 一起完成（屆時 Registry 提供了完整映射，才能安全做到）

### 與系統原則的對齊

| 原則 | 對齊說明 |
|------|---------|
| 原則 10（認知誠實）| 方案 B 讓「已知的 category」從掃描時的確定性來源傳遞，不再猜測；方案 A 徹底消除猜測 |
| 原則 8（交易可解釋）| category 錯誤 → submit_order 失敗 → 訂單無法重建原因；修復後可解釋 |
| 原則 6（失敗默認收縮）| fallback 加 warning 而非靜默 fallback；category 不明時觸發 warning 而非錯誤猜測 |
| 原則 5（生存優先）| spot 訂單因 category 錯誤被 Bybit 拒絕，是比靜默出錯更好的失敗模式 |

---

## 決策

**選擇：方案 B（主）+ 方案 A（後補）+ 方案 D 部分（fallback warning 強化）**

不選擇方案 C（技術債，明確排除）。
不立即做完整方案 D（全局必填改動，等方案 A 完成後一起做更安全）。

---

## 實施路線

### 短期（Wave 7a 內，~1.5-2 小時，E1 執行）

**改動 1：PipelineBridge 新增 `_symbol_category_map`**
- 文件：`pipeline_bridge.py`
- 新增 `self._symbol_category_map: dict[str, str] = {}` 實例屬性
- 新增公開方法 `register_symbol_category(symbol: str, category: str) -> None`
- 修改 `_refresh_kline_volume`（行 1729）：
  ```python
  kline_category = self._symbol_category_map.get(symbol) or self._infer_category_from_symbol(symbol)
  ```
- 修改 `_fetch_single_funding_rate`（行 1782）：
  ```python
  resolved_category = category or self._symbol_category_map.get(symbol) or self._infer_category_from_symbol(symbol)
  ```
- `_infer_category_from_symbol` 的 `return "linear"` 改為加 warning：
  ```python
  logger.warning("Category inferred as linear for %s — may be incorrect for spot symbols", symbol)
  return "linear"
  ```

**改動 2：StrategyAutoDeployer 部署時通知 PipelineBridge**
- 文件：`strategy_auto_deployer.py`
- `_deploy_strategy()` 行 474 附近，注入 api_category 到 `_default_metadata` 之後：
  ```python
  if hasattr(self, "_bridge") and self._bridge is not None:
      self._bridge.register_symbol_category(symbol, api_category)
  ```
- 需確認 `StrategyAutoDeployer` 是否持有 bridge 引用；若無，通過構造函數注入

**改動 3：`_process_pending_intents` category 缺失時加 warning**
- 文件：`pipeline_bridge.py` 行 737
  ```python
  category = intent.metadata.get("category", "linear") if intent.metadata else "linear"
  if category == "linear" and intent.symbol not in self._symbol_category_map:
      logger.warning("Intent for %s has no explicit category; defaulting to linear", intent.symbol)
  ```

**測試（E4 補充，~5-8 個）：**
- `test_register_symbol_category_updates_kline_category`
- `test_infer_category_fallback_emits_warning`
- `test_process_intents_no_category_warning`
- `test_spot_symbol_uses_registered_category_over_infer`

### 長期（Wave 7b 或獨立任務，~3 小時，E1 執行）

**改動：SymbolCategoryRegistry 類**
- 新建 `app/symbol_category_registry.py`（或合入 `pipeline_bridge.py` 作為內嵌類）
- 啟動時呼叫 `refresh()`，從 Bybit `/v5/market/instruments-info` 拉取 linear/spot/inverse 完整列表
- 結果填充 `PipelineBridge._symbol_category_map`
- TTL 設 6 小時（盤中新上市幣種不影響已有交易）
- `_startup_integrity_check`（main.py）中加入 registry 初始化（soft dep，失敗 → warning，不阻啟動）

**改動：TradeIntent 強化**
- `TradeIntent.metadata["category"]` 缺失 → 嘗試從 Registry 查詢 → 仍未知 → reject intent
- 評估是否改為必填字段（需回歸所有 intent 創建點）

---

## 不做什麼（及理由）

| 排除方案 | 理由 |
|---------|------|
| 方案 C（命名啟發式擴展）| 根本上無法解決問題，硬編碼清單維護成本不可接受，Bybit 隨時更改命名規則 |
| 立即完整方案 D（全局必填）| 影響範圍廣（5-8 個文件），在方案 A 的 Registry 提供完整映射之前，強制必填會讓非掃描路徑（手動訂單）無法正常運作 |
| 立即方案 A（跳過方案 B）| 啟動時 HTTP 請求增加複雜度，而方案 B 能以更低成本在 Wave 7a 時間窗口內解決主要問題 |
| 維持現狀 | Wave 7a Spot 啟用後，K 線資料混淆 + 資金費率語義錯誤會讓 Spot 策略無法正常運作 |
