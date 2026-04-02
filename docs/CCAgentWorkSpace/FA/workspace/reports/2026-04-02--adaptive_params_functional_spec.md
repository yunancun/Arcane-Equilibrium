# FA 功能規格書：自適應參數架構（基於 QC 審查）
# FA Functional Spec: Adaptive Parameter Architecture (Based on QC Review)

> 審查人：FA（Functional Auditor）
> 日期：2026-04-02
> 基於：QC 審查報告 `2026-04-02--adaptive_params_architecture_review.md`
> 前置：FA GAP 審計 `2026-04-01--fa_completion_gap_audit.md`

---

## 總覽

QC 報告結論為 **PROCEED WITH REVISIONS**，核心觀點：
1. 確定性適應（ATR 縮放、成本門檻、regime 映射）立即可做
2. 統計適應（歷史表現回饋參數）暫緩到 200+ trades/regime
3. 策略本身缺乏可論證 edge 是更根本的問題

本規格書聚焦 QC 確認的 **確定性適應** 項目，將每項建議轉化為可實現、可驗收的功能規格。

---

## A. ATR 縮放止損/追蹤止損

### 現狀

**`compute_dynamic_stop_pct()`**（risk_manager.py:274-323）：
- 使用 ATR 單窗口（14 期），倍數 **1.5x**，硬編碼
- 上限 = `hard_stop_pct * 0.8`（正確，與 Operator 硬止損關聯）
- 有 regime 乘數（REGIME_STOP_MULTIPLIERS：trending=1.0, volatile=1.5, ranging=0.7, squeeze=0.6）
- 有反聚集隨機偏移（deterministic hash-based offset）
- 下限 0.1%

**追蹤止損**（risk_manager.py:1160-1195）：
- 啟動 = `trailing_stop_activation_pct`（默認 1.0%，固定值）
- 距離 = ATR * 1.2x，上限 `hard_sl * 0.8`（正確）
- 啟動和距離之間**無成本約束**

**AgentRiskParams**（risk_manager.py:466-513）：
- `trailing_stop_activation_pct: float = 1.0`（固定 1%）
- `trailing_stop_distance_pct: float = 0.8`（固定 0.8%）
- 無 ATR 倍數配置，倍數硬編碼在邏輯中

### 與 QC 建議的差距

| 現有 | QC 建議 | 差距 |
|------|---------|------|
| ATR 單窗口 14 期 | ATR 快/慢雙窗口（5/14 期），取 max | 缺少快窗口 |
| k_sl = 1.5（硬編碼） | k_sl 應可配置，初始值可保持 1.5 | 缺可配置性 |
| 追蹤啟動 1.0%（固定） | 啟動 = max(c_round_pct * 2.5, k_act * atr_pct) | 無成本感知 |
| 追蹤距離 0.8%（固定基線，ATR overlay） | 距離 = max(c_round_pct, min(k_trail * atr_pct, hard_stop * 0.8)) | 無成本下限 |
| 無利潤鎖定檢查 | activation - distance > c_round_pct（M1 約束） | **缺失** |
| 無 jump detection | K 線 body > 3 sigma → 加寬 50% | 缺失（N3，NICE-TO-HAVE） |

### 功能規格

**A1. ATR 雙窗口**
- IndicatorEngine 已有 ATR(14)。新增 ATR(5) 快窗口到默認指標集。
- `compute_dynamic_stop_pct()` 新增參數 `atr_fast_pct: float | None = None`。
- 當兩個 ATR 都有值時，取 `max(atr_pct, atr_fast_pct)` 作為有效 ATR。
- 理由：快窗口在 regime 切換時反應更快，取 max 是保守策略。
- 影響範圍：`risk_manager.py` 的 `compute_dynamic_stop_pct()` + `_check_stops()` 中兩處 ATR 讀取。
- pipeline_bridge.py 的 `on_tick()` 需傳遞 ATR(5) 數據（或由 RiskManager 自行從 PriceTracker 取）。

**A2. ATR 倍數可配置化**
- 新增 dataclass `ATRMultipliers`：
  ```python
  @dataclass
  class ATRMultipliers:
      k_sl: float = 1.5    # 止損 ATR 倍數
      k_tp: float = 2.5    # 止盈 ATR 倍數
      k_act: float = 2.0   # 追蹤啟動 ATR 倍數
      k_trail: float = 1.2  # 追蹤距離 ATR 倍數
  ```
- 存入 `AgentRiskParams`，Agent 可在 Operator 範圍內調整。
- `operator_risk_config.json` 新增 `atr_multiplier_bounds`：每個倍數的 min/max。
- 不做動態搜索（QC M3 結論：數據不足前禁止統計適應）。

**A3. 追蹤止損 ATR 化（啟動 + 距離）**
- 修改 `_check_stops()` 追蹤止損部分（risk_manager.py:1160-1195）：
  ```python
  # 啟動門檻：取 ATR 計算值與成本安全線的較大者
  activation = max(c_round_pct * 2.5, k_act * effective_atr_pct)
  # 距離：ATR 計算值，下限為成本
  distance = max(c_round_pct, min(k_trail * effective_atr_pct, hard_sl * 0.8))
  ```
- `c_round_pct` 計算見 B 項（成本感知入場門檻）。
- 保留 `AgentRiskParams.trailing_stop_activation_pct` 和 `trailing_stop_distance_pct` 作為「無 ATR 數據時」的 fallback。

### 驗收標準

- [ ] AC-A1：ATR(5) 出現在 IndicatorEngine 默認指標集中，`compute_dynamic_stop_pct()` 接收雙 ATR 並取 max
- [ ] AC-A2：ATRMultipliers dataclass 存在且被 `compute_dynamic_stop_pct()` 和 `_check_stops()` 使用
- [ ] AC-A3：追蹤止損啟動/距離使用 ATR 公式 + c_round_pct 下限
- [ ] AC-A4：所有 ATR 倍數在 `operator_risk_config.json` 中有 bounds，Agent 不可超越
- [ ] AC-A5：ATR 為 None 時回退到固定值（現有行為不破壞）
- [ ] AC-A6：新增/修改函數有中英雙語注釋
- [ ] AC-A7：測試覆蓋：ATR 雙窗口取 max、ATR None fallback、倍數邊界、Operator 上限 clamp

### 影響的文件

| 文件 | 改動 |
|------|------|
| `risk_manager.py` | `compute_dynamic_stop_pct()` 參數擴展 + `_check_stops()` 追蹤止損重寫 + `ATRMultipliers` dataclass |
| `risk_manager.py` | `AgentRiskParams` 新增 `atr_multipliers: ATRMultipliers` |
| `operator_risk_config.json` | 新增 `atr_multiplier_bounds` 節 |
| `pipeline_bridge.py` | `on_tick()` 傳遞 ATR(5) 或確認 RiskManager 自行取得 |
| `indicator_engine.py` 或等效 | 確認 ATR(5) 已在默認指標集 |

### 與現有 GAP 的關係

- 與 FA GAP-4（交易所條件單未實作）互補但獨立 — 本項改善本地止損品質，條件單是另一層防線
- 與 FA GAP-1（學習反饋閉環斷開）無直接關聯 — 本項是確定性適應，不依賴學習
- 原則 5（生存>利潤）強相關 — 更好的止損 = 更好的生存

---

## B. 成本感知入場門檻

### 現狀

- **全局 taker 費率**：`DEFAULT_TAKER_FEE_RATE = 0.00055`（0.055%），定義在 `paper_trading_engine.py:108` 和 `legacy_routes.py:134`
- **滑點分級**：`SLIPPAGE_TIERS`（paper_trading_engine.py:118-123），按 24h turnover 分 5 級（1bps-30bps）
- **成本感知**：`cost_edge_ratio` 在 tab-ai.html 前端展示 + L2 觸發條件，但**入場時不強制檢查**
- **入場過濾**：pipeline_bridge `_process_pending_intents()` 有 H0/H1/Guardian/Lease 門控，但無成本門檻
- **市場掃描器**：MarketScanner `_classify()` 用簡單評分，無成本過濾
- `operator_risk_config.json` 有 `max_cost_edge_ratio: 0.8`（全局），但僅用於 L2 觸發

### 與 QC 建議的差距

| 現有 | QC 建議 | 差距 |
|------|---------|------|
| 無入場成本檢查 | `min_move_pct = c_round_pct / win_rate * safety_margin`，ATR < min_move → reject | **完全缺失** |
| 全局 taker fee | per-symbol 成本（taker + slippage） | 有 SLIPPAGE_TIERS 但未組合使用 |
| 固定 "2x 手續費" 概念 | 公式化成本門檻（QC §1.4） | 需實現 |

### 功能規格

**B1. 成本計算函數**
- 新增 `compute_round_trip_cost_pct(symbol, volume_24h, category) -> float`
  ```python
  def compute_round_trip_cost_pct(symbol: str, volume_24h: float, category: str = "linear") -> float:
      """
      計算一筆完整交易的往返成本百分比（開倉+平倉）。
      Compute round-trip cost as % of notional (open + close).
      """
      taker_fee = DEFAULT_TAKER_FEE_RATE  # 0.055% per side
      slippage = compute_dynamic_slippage(volume_24h)  # per side
      if category == "spot":
          taker_fee = 0.001  # Bybit VIP0 spot taker 0.10%
      return (taker_fee + slippage) * 2 * 100  # 轉為百分比
  ```
- 函數放在 `risk_manager.py`（與風控邏輯同模組）。
- `compute_dynamic_slippage` 已在 `paper_trading_engine.py`，需 import 或複製。

**B2. 成本感知入場門檻**
- 在 `pipeline_bridge._process_single_intent()` 中（已是意圖處理的核心路徑），追加成本檢查：
  ```python
  c_round_pct = compute_round_trip_cost_pct(symbol, volume_24h, category)
  estimated_win_rate = max(0.3, self._get_recent_win_rate(symbol, regime, n=50))
  safety_margin = 1.3
  min_move_pct = c_round_pct / estimated_win_rate * safety_margin
  
  atr_pct = self._risk_manager._price_tracker.compute_atr_pct(symbol)
  if atr_pct is not None and atr_pct * 100 < min_move_pct:
      # 波動率不足以覆蓋成本，拒絕入場
      self._stats["intents_cost_rejected"] += 1
      return  # reject
  ```
- 勝率估計初期用全局默認 0.5（50%），待 round-trip 數據積累後切換到 per-symbol/regime。
- QC M3 約束：`estimated_win_rate` 下限 0.3（防除零、防過度樂觀）。

**B3. volume_24h 數據來源**
- pipeline_bridge 的 `_market_prices` dict 已追蹤每 symbol 的市場價格。
- 需確認 `volume_24h` 可從 KlineManager 或 MarketDataDispatcher 獲取。
- 若不可用，使用 SLIPPAGE_TIERS 的中位數滑點（5 bps）作為 fallback。

### 驗收標準

- [ ] AC-B1：`compute_round_trip_cost_pct()` 函數存在，per-symbol 返回百分比
- [ ] AC-B2：`_process_single_intent()` 在 Guardian 審批後、下單前檢查成本門檻
- [ ] AC-B3：ATR < min_move_pct 的意圖被拒絕，`intents_cost_rejected` 統計遞增
- [ ] AC-B4：volume_24h 不可用時 fallback 到保守估計
- [ ] AC-B5：spot 品類使用 0.10% taker fee（非 linear 的 0.055%）
- [ ] AC-B6：不使用 magic number "2x"，使用公式化門檻
- [ ] AC-B7：測試覆蓋：BTC（低成本通過）、小幣種（高成本拒絕）、ATR None fallback、spot vs linear 費率

### 影響的文件

| 文件 | 改動 |
|------|------|
| `risk_manager.py` | 新增 `compute_round_trip_cost_pct()` |
| `pipeline_bridge.py` | `_process_single_intent()` 新增成本門檻檢查 |
| `paper_trading_engine.py` | `compute_dynamic_slippage()` 可能需提為公共 utility（或 risk_manager import） |

### 與現有 GAP 的關係

- 與原則 13（AI 資源成本感知）強相關 — 擴展到交易成本感知
- 與 FA GAP-7（L2 觸發門檻過高）互補 — 成本門檻在 L0 層阻擋無意義交易，減少 L2 負擔

---

## C. Regime-aware 參數映射表

### 現狀

**Regime 檢測已有完整實現：**
- `RegimeDetectorRule`（signal_generator.py:573-652）：基於 ATR + BB bandwidth + EMA spread 分類為 trending/ranging/volatile/squeeze
- `MarketRegimeTracker`（market_regime.py）：完整的多時間框架追蹤 + 轉換記錄 + 衝突檢測
- `MarketRegime` 枚舉（9 種）：TRENDING_UP/DOWN, RANGING, SQUEEZE, HIGH/LOW_VOLATILITY, BREAKOUT, REVERSAL, UNKNOWN

**Regime 已用於止損/止盈/持倉時間：**
- `REGIME_STOP_MULTIPLIERS`：trending=1.0, volatile=1.5, ranging=0.7, squeeze=0.6
- `REGIME_TP_MULTIPLIERS`：trending=1.5, volatile=0.8, ranging=0.7, squeeze=0.5
- `REGIME_TIME_MULTIPLIERS`：trending=1.5, volatile=0.8, ranging=0.8, squeeze=1.0

**Regime 已用於策略選擇：**
- `StrategistAgent._REGIME_STRATEGY_PREFERENCES`：per-regime 策略偏好權重
- `_apply_regime_weights()` 已在 StrategistAgent 中實現

### 與 QC 建議的差距

| 現有 | QC 建議 | 差距 |
|------|---------|------|
| 止損/止盈/時間 3 個乘數表（代碼常量） | 統一參數映射表含 k_sl/k_act/k_trail/持倉上限 | 缺 ATR 倍數 per-regime |
| RegimeDetectorRule 分 4 類 | 4 類 + 各自的 ATR 倍數映射 | 需統一到 ATRMultipliers |
| 乘數硬編碼在 risk_manager.py | JSON 配置 vs 代碼常量 | 需評估 |
| 現有 MarketRegimeTracker 未被風控使用 | 風控應讀取 MarketRegimeTracker 的正式 regime | MarketRegimeTracker 與 RiskManager 未集成 |

### 功能規格

**C1. 統一 Regime 參數映射表**
- 新增 `REGIME_ATR_MULTIPLIERS` 在 `risk_manager.py`：
  ```python
  REGIME_ATR_MULTIPLIERS: dict[str, ATRMultipliers] = {
      "trending":  ATRMultipliers(k_sl=2.0, k_tp=3.0, k_act=3.0, k_trail=1.5),
      "volatile":  ATRMultipliers(k_sl=3.0, k_tp=2.0, k_act=4.0, k_trail=2.0),
      "ranging":   ATRMultipliers(k_sl=1.5, k_tp=1.5, k_act=2.0, k_trail=1.0),
      "squeeze":   ATRMultipliers(k_sl=1.0, k_tp=1.0, k_act=1.5, k_trail=0.8),
      "unknown":   ATRMultipliers(k_sl=1.5, k_tp=2.5, k_act=2.0, k_trail=1.2),
  }
  ```
- **存放位置決策：代碼常量，非 JSON 配置**。
  - 理由：(1) 這些是數學關係，不是 Operator 偏好；(2) QC 明確指出初始值需 walk-forward 驗證後固定；(3) 避免 Operator 隨意改動導致風控模型崩壞。
  - Operator 只控制 `atr_multiplier_bounds`（上下界），不控制 per-regime 映射。
- 保留現有 `REGIME_STOP_MULTIPLIERS`/`REGIME_TP_MULTIPLIERS`/`REGIME_TIME_MULTIPLIERS` 作為向後兼容 fallback，但 `_check_stops()` 在有 ATR 時優先使用 `REGIME_ATR_MULTIPLIERS`。

**C2. RegimeDetectorRule 輸出標準化**
- 現有 RegimeDetectorRule 輸出 4 種 regime（trending/ranging/volatile/squeeze）。
- 現有 MarketRegime 枚舉有 9 種（含 trending_up/trending_down 分離）。
- **映射規則**：
  - RegimeDetectorRule "trending" + trend_direction "up" → 風控用 "trending"（不區分方向）
  - MarketRegimeTracker TRENDING_UP/TRENDING_DOWN → 風控用 "trending"
  - MarketRegimeTracker HIGH_VOLATILITY → 風控用 "volatile"
  - MarketRegimeTracker BREAKOUT → 風控用 "volatile"（保守）
  - MarketRegimeTracker REVERSAL → 風控用 "volatile"（保守）
  - MarketRegimeTracker LOW_VOLATILITY → 風控用 "squeeze"
- 新增 `normalize_regime_for_risk(regime: str) -> str` helper 函數。

**C3. 不做的事（明確排除）**
- 不在運行時動態搜索最優 regime 倍數（QC M3：200+ trades 前禁止）
- 不引入 per-symbol × per-regime 參數組合（QC §2.1 參數空間膨脹風險）
- 不改變現有 `_REGIME_STRATEGY_PREFERENCES`（策略選擇層已有 regime 感知）

### 驗收標準

- [ ] AC-C1：`REGIME_ATR_MULTIPLIERS` 存在且被 `_check_stops()` 使用
- [ ] AC-C2：`normalize_regime_for_risk()` 將 9 種 MarketRegime 映射為 5 種風控 regime
- [ ] AC-C3：ATR 為 None 時回退到現有 `REGIME_STOP_MULTIPLIERS` 乘數邏輯
- [ ] AC-C4：`compute_dynamic_stop_pct()` 接受 ATRMultipliers 參數
- [ ] AC-C5：測試覆蓋：4 種 regime 各自的倍數正確性、枚舉映射、fallback

### 影響的文件

| 文件 | 改動 |
|------|------|
| `risk_manager.py` | 新增 `REGIME_ATR_MULTIPLIERS` + `normalize_regime_for_risk()` + 修改 `_check_stops()` |
| `risk_manager.py` | `compute_dynamic_stop_pct()` 改接 `ATRMultipliers` |

### 與現有 GAP 的關係

- 與 StrategistAgent `_REGIME_STRATEGY_PREFERENCES` 互補 — 策略層已有 regime 感知，風控層補齊 regime 感知
- 與 MarketRegimeTracker 的集成是新增功能 — 目前 RiskManager 只從 `pos.get("regime")` 讀取字符串

---

## D. 追蹤止損成本陷阱修復（QC M1）

### 現狀

追蹤止損邏輯（risk_manager.py:1160-1195）：
- `activation = self._agent_params.trailing_stop_activation_pct`（默認 1.0%）
- `distance`：ATR 動態或固定 0.8%
- **無 `activation - distance > c_round_pct` 約束**

QC 指出的陷阱場景：
> 若 activation = 0.3%（ATR 低的幣種）, distance = 0.2%
> → 啟動後只要回撤 0.2% 就退出 → 實際鎖定利潤 0.1% → 手續費 0.13% → 淨虧損

### 功能規格

**D1. 利潤鎖定約束**
- 在 `_check_stops()` 的追蹤止損部分，計算完 `activation` 和 `distance` 後，追加：
  ```python
  # QC M1: 追蹤止損鎖定的利潤必須大於來回成本
  # Trailing stop locked profit must exceed round-trip cost
  c_round_pct = compute_round_trip_cost_pct(symbol, volume_24h, category)
  locked_profit = activation - distance
  if locked_profit <= c_round_pct:
      # 成本陷阱：追蹤止損鎖定的利潤不夠覆蓋成本，提高啟動門檻
      # Cost trap: raise activation so locked profit > cost
      activation = distance + c_round_pct * 1.1  # 10% 額外安全邊際
  ```
- 這是一個**自動修正**，不是拒絕交易 — 只是確保追蹤止損啟動後能鎖定正利潤。

**D2. 現有追蹤止損改動量**
- 追蹤止損核心邏輯（peak tracking + drawback check）不需要改 — 機制正確。
- 僅在啟動/距離計算階段插入成本約束。
- 改動行數：~10 行插入。

### 驗收標準

- [ ] AC-D1：`activation - distance > c_round_pct` 約束存在
- [ ] AC-D2：當約束不滿足時，activation 被自動提高（非拒絕交易）
- [ ] AC-D3：`c_round_pct` 計算復用 B1 的 `compute_round_trip_cost_pct()`
- [ ] AC-D4：測試：activation=0.3%, distance=0.2%, cost=0.13% → activation 被提高到至少 0.34%
- [ ] AC-D5：測試：activation=2.0%, distance=0.8%, cost=0.13% → 無修正（locked_profit=1.2% > 0.13%）

### 影響的文件

| 文件 | 改動 |
|------|------|
| `risk_manager.py` | `_check_stops()` 追蹤止損部分，~10 行插入 |

### 與現有 GAP 的關係

- 直接修復 QC M1（MUST 級別）
- 依賴 B 項的 `compute_round_trip_cost_pct()`
- 與原則 5（生存>利潤）強相關

---

## E. FundingRateArb 成本模型

### 現狀

`FundingRateArbStrategy`（funding_rate_arb.py）**已有完整實現**：
- Delta-Neutral 雙腿（perp + spot）
- 費用模型：perp 11bps + spot 20bps = 31bps 總來回
- 入場條件：|funding_rate| > threshold (5bps) + edge_bps > 0 + 距結算 >= 2h
- 出場條件：rate 反轉 / rate 太小 / 持倉超時
- 狀態持久化 + reject 回滾

### 與 QC 建議的差距

| 現有 | QC 建議 | 差距 |
|------|---------|------|
| 固定 threshold 5bps | 應考慮多周期持倉的費用攤薄 | 部分缺失 |
| 無 basis risk 監控 | basis risk（perp-spot 價差偏離）應實時監控 | 缺失 |
| 入場只看當前 funding rate | 應看 funding rate 歷史（如 7 天均值）預測持續性 | 缺失 |
| 固定 spot fee 20bps | 應用 per-symbol 費用 | 硬編碼 |
| `record_funding_payment()` 存在但調用者不明 | 需確認 funding 收入實際被記錄 | **調用鏈可能斷開** |

### 功能規格

**E1. Funding Rate 歷史數據**
- 新增 `funding_rate_history: dict[str, list[float]]` 到策略內部狀態。
- 入場前檢查近 N 期（默認 7 天 = 21 個 8h 周期）funding rate 方向一致率。
- 一致率 < 60% → 不入場（funding 不穩定，持倉可能虧費用）。
- 數據來源：pipeline_bridge 的 `_fetch_funding_rate()` 已存在。

**E2. Basis Risk 監控**
- 在策略內新增 `_check_basis_risk(perp_price, spot_price) -> bool`：
  ```python
  basis_pct = abs(perp_price - spot_price) / spot_price * 100
  if basis_pct > 0.5:  # >0.5% 價差 → 風險過大
      return False  # 不入場或觸發出場
  ```
- basis risk 出場條件加入 `evaluate_funding_opportunity()` 的出場邏輯。

**E3. Per-symbol 費率**
- spot fee 從硬編碼 20bps 改為參數化，允許初始化時傳入。
- 不同品類的 VIP 等級費率差異暫不處理（保守用 VIP0 最高費率）。

**E4. `record_funding_payment()` 接通確認**
- 審計 pipeline_bridge 和 paper_trading_engine：確認 funding payment 是否真正被記錄。
- 若未接通，在 paper_trading_engine 的 funding 模擬邏輯中調用 `record_funding_payment()`。

### 驗收標準

- [ ] AC-E1：入場前檢查 funding rate 歷史一致率，< 60% 不入場
- [ ] AC-E2：basis risk > 0.5% 時觸發出場
- [ ] AC-E3：spot fee 參數化，非硬編碼
- [ ] AC-E4：`record_funding_payment()` 有至少一個實際調用者
- [ ] AC-E5：測試：funding 歷史不穩定 → 不入場；basis risk 過大 → 出場

### 影響的文件

| 文件 | 改動 |
|------|------|
| `strategies/funding_rate_arb.py` | funding 歷史 + basis risk + 費率參數化 |
| `pipeline_bridge.py` | 確認 funding rate 數據傳遞到策略 |
| `paper_trading_engine.py` | 確認 `record_funding_payment()` 接通 |

### 與現有 GAP 的關係

- QC 強調 FundingRateArb 是**唯一有可論證 edge 的策略**（QC §4.3）
- 完善此策略的優先級應**高於** MA Crossover 參數優化
- 與 FA GAP-6（Backtest 生產環境未啟用）相關 — FundingRateArb 需要 backtest 驗證成本模型

---

## F. Round-Trip 記錄增強（QC M4）

### 現狀

`_emit_round_trip()`（pipeline_bridge.py:1883+）當前記錄的字段：
- `symbol`, `strategy`, `direction`, `entry_price`, `exit_price`, `pnl`, `hold_ms`, `regime`, `timestamp_ms`

通過 `_observation_writer` 回調：
- `symbol`, `strategy_name`, `close_pnl`, `hold_ms`, `regime`

通過 Trade Attribution（pipeline_bridge.py:1944-1986）：
- `trade_id`, `symbol`, `strategy`, `entry_price`, `exit_price`, `quantity`, `entry_timestamp`, `exit_timestamp`
- `fees_paid=0.0`（**硬編碼 0**）, `slippage=0.0`（**硬編碼 0**）, `ai_cost=0.0`（**硬編碼 0**）

### 與 QC 建議的差距

| 現有 | QC 需要 | 差距 |
|------|---------|------|
| regime 字符串 | regime + regime_at_entry + regime_at_exit（可能不同） | 只有 entry regime |
| 無動態參數記錄 | 使用的 stop_pct, trail_activation, trail_distance, atr_pct | **完全缺失** |
| fees_paid=0.0 | 實際費用（taker fee + slippage） | **硬編碼零** |
| 無成本細分 | taker_fee_pct, slippage_pct, c_round_pct 分開記錄 | 缺失 |

### 功能規格

**F1. 擴展 round-trip payload**
- ROUND_TRIP_COMPLETE MessageBus payload 新增：
  ```python
  {
      # 現有字段保留
      ...
      # 新增字段
      "atr_pct_at_entry": float,        # 入場時 ATR
      "atr_pct_at_exit": float,         # 出場時 ATR
      "stop_pct_used": float,           # 實際使用的止損百分比
      "trail_activation_used": float,   # 實際使用的追蹤啟動
      "trail_distance_used": float,     # 實際使用的追蹤距離
      "regime_at_entry": str,           # 入場時 regime
      "regime_at_exit": str,            # 出場時 regime
      "taker_fee_pct": float,           # taker 費率
      "slippage_pct": float,            # 滑點百分比
      "c_round_pct": float,             # 來回總成本百分比
      "exit_reason": str,               # 出場原因（hard_stop/trailing/time/signal）
  }
  ```

**F2. _open_positions 擴展**
- `_on_position_open()` 記錄的 pos_info 新增 ATR、動態參數快照。
- 這些值在入場時 snapshot，出場時讀取（不用出場時重新計算）。

**F3. Trade Attribution 費用修正**
- `_emit_round_trip()` 中 `fees_paid` 和 `slippage` 改為實際計算值：
  ```python
  notional = exit_price * qty
  fees_paid = notional * DEFAULT_TAKER_FEE_RATE * 2
  slippage = notional * compute_dynamic_slippage(volume_24h) * 2
  ```

### 驗收標準

- [ ] AC-F1：ROUND_TRIP_COMPLETE payload 包含上述所有新字段
- [ ] AC-F2：`_open_positions` 在開倉時記錄 ATR 和動態參數快照
- [ ] AC-F3：Trade Attribution `fees_paid` 和 `slippage` 不再為 0
- [ ] AC-F4：新字段為 None-safe（缺失時填默認值，不崩潰）
- [ ] AC-F5：測試：round-trip 完整生命週期，驗證所有新字段非零

### 影響的文件

| 文件 | 改動 |
|------|------|
| `pipeline_bridge.py` | `_on_position_open()` 擴展 + `_emit_round_trip()` 擴展 |
| `pipeline_bridge.py` | Trade Attribution 費用計算修正 |

### 與現有 GAP 的關係

- 與 FA GAP-1（學習反饋閉環）直接相關 — round-trip 記錄是學習管線的數據源
- 與原則 8（交易可解釋）強相關 — 每筆交易的參數快照 = 可重建
- QC M4 是 MUST 級別，不做就不應上線

---

## 實施優先級建議

| 批次 | 項目 | 工時估計 | 依賴 |
|------|------|----------|------|
| **Batch 1** | D（成本陷阱修復）+ B1（成本函數） | 3h | 無 |
| **Batch 2** | F（round-trip 增強） | 4h | 無 |
| **Batch 3** | A（ATR 雙窗口 + 倍數可配置） | 5h | B1 |
| **Batch 4** | C（regime 映射表統一） | 3h | A2 |
| **Batch 5** | B2-B3（成本門檻入場檢查） | 3h | B1 |
| **Batch 6** | E（FundingRateArb 完善） | 5h | B1 |

**總計：~23h**

**排序理由：**
1. D 是 QC MUST 且改動最小（10 行），投入產出比最高
2. F 是 QC MUST 且影響所有後續學習（記錄不全 → 無法分析）
3. A 是核心改進但改動量大
4. C 建立在 A 之上
5. B 的入場檢查在有成本數據後才有意義
6. E 是獨立策略改進，可並行但優先級由 QC "先找 alpha" 建議提高

---

## 明確排除項（QC 審查後決定不做）

| 項目 | 原因 |
|------|------|
| 統計適應（歷史表現→參數調整） | QC M3：200+ trades/regime 前禁止，數據完全不足 |
| 動態參數搜索 | QC §2.3：過擬合風險，Deflated SR 修正後可能無 edge |
| Kelly Criterion 替代 risk_per_trade_pct | QC §5.3-G：當前 f* < 0，不適用；待策略改善後考慮 |
| MA Crossover 大改 | QC §4.2：70% 勝率 + 0.42 R:R = 零 edge，應把精力放在 FundingRateArb |
| Walk-forward harness（BacktestEngine 增強） | QC N1：NICE-TO-HAVE，待數據積累 |
| Jump detection（3 sigma 加寬） | QC N3：NICE-TO-HAVE，待核心改進完成 |

---

> FA (Functional Auditor)
> 2026-04-02
