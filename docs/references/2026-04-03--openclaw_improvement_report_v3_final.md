# OpenClaw Bybit 全面改善建議報告 V3

**日期**: 2026-04-03
**版本**: V3-FINAL（五輪三人審批定稿）
**基於**: SYSTEM_STATUS_REPORT.md + 多輪架構討論 + 五輪專家審批（34 項修正）
**範圍**: Agent 自主化架構 + 策略升級 + 系統模組 + L0-L2 計算路徑
**交易所**: 僅 Bybit

---

# Claude Code 快速入口

```
本報告是開發 SPEC。使用方式：

1. 先讀 §1（架構原則）+ §3（Agent 決策流程）
   → 理解工具分類和雙層決策架構

2. 按 Phase 順序開發（§10 路線圖）：
   1.0 → 策略基準測試（跑 Paper，不寫碼）
   1.1-1.9 → 基礎模組（按 附錄C.6 依賴圖並行）
   2.1-2.9 → 策略升級 + Agent 整合
   3.1-3.7 → API + 分析 + 框架

3. 每個模組開發 checklist：
   □ 讀 §5 的代碼定義
   □ 確認工具分類（§1.3 表格）
   □ 確認關聯 Agent
   □ 查附錄 B/C/D/E 是否有該模組的修正
   □ 實現 get_schema() + get_alerts()
   □ 寫單元測試

4. 絕對不可違反：
   - §1.3「絕對禁止」項
   - Guardian 無寫權限
   - 快速通道規則不可被 Agent 修改（MappingProxyType）
   - fail-closed：不確定 → 拒絕交易
   - is_simulated=True 不變量
   - 雙語註釋規範

5. Strategist intent 生成必須用確定性代碼做 qty 計算
   （見附錄 E.1），不依賴 LLM 輸出的絕對數值

6. 所有附錄修正已反映在對應章節描述中，
   附錄保留作為決策審計記錄。
```

---

# 第一部分：架構根原則

## 1.1 Agent-Centric 設計哲學

所有新增模組的定位是 **Agent 的感知器和工具箱**，不是管線中的確定性規則引擎。

```
正確：新模組 → Agent 的工具 → Agent 推理 → 判斷 → Guardian 審核 → 執行
錯誤：新模組 → 管線 if-else → 直接覆寫 intent 參數（架空 Agent 自主權）
```

## 1.2 雙層決策架構

```
┌─────────────────────────────────────────────────┐
│ 硬性層（確定性，不經 Agent，Agent 不可覆蓋）     │
│                                                  │
│ H0 Gate (<1ms)          P0/P1 風控上限           │
│ Kill Switch             保證金安全線              │
│ Strategist 快速通道      system_mode 門控         │
│ 修改權：僅 Operator                              │
├─────────────────────────────────────────────────┤
│ 軟性層（Agent P2 自主空間）                      │
│                                                  │
│ 用什麼策略、交易什麼、交易多少、什麼時候         │
│ 是否對沖、風控微調（只能收緊不能放鬆）           │
│ 約束：所有行動在 P0/P1 邊界以內                  │
└─────────────────────────────────────────────────┘
```

## 1.3 工具分類

| 類別 | 誰可用 | 規則 | 示例 |
|------|--------|------|------|
| **只讀** | 所有 Agent | 無副作用，隨意調用 | IndicatorEngine, PositionSizer, HedgingEngine, TSR.query, SignalEngine |
| **受限寫** | 指定 Agent + 指定條件 | Strategist → emit Intent（經 Guardian）；Analyst → TSR.register（confidence ≤ 0.85/0.90）；Executor → submit_order（僅 APPROVED_INTENT）；Conductor → STRATEGY_DIRECTIVE |
| **危險操作** | 僅系統級/Operator | Agent 可建議不可執行 | P0/P1 修改、Kill Switch、system_mode、Risk Governor 降級 |
| **絕對禁止** | 無 | 任何條件下不可 | 放鬆 P0/P1、繞過 H0/Guardian、訪問 secrets/、刪除審計日誌 |

---

# 第二部分：四階段遞進式放權

| | 階段 1：監控 | 階段 2：P2 調參 | 階段 3：完整 P2 | 階段 4：策略創造 |
|---|---|---|---|---|
| **Agent 能力** | 僅監控報告 | P2 收緊 + 策略權重 | 獨立交易決策 + 對沖 | 新模式發現 + 新幣種 |
| **交易決策** | 確定性代碼 | 確定性 + Agent 微調 | Agent 主導 | Agent 完全自主 |
| **進入條件** | 系統部署完成 | 4 週 + 500 筆 + 影子 Sharpe > 實際 80% | 前階 4 週 + 正 PnL + WR>35% + Sharpe>0.7 + DD<15% | 前階 8 週 + Sharpe>1.0 + Operator 批准 |
| **回退觸發** | — | 滾動 4 週 Sharpe < 0 | 滾動 4 週 Sharpe < 0.3 | 滾動 4 週 Sharpe < 0.5 |

**治理規則**：
- 升級：量化條件全滿足 + Operator 確認（階段 4 必須 Operator）
- 降級：條件觸發自動降級（fail-closed），不等 Operator
- 當前階段持久化到 GovernanceHub 的磁盤狀態文件
- 重啟後恢復階段 + 累計指標（從持久化狀態讀取）

---

# 第三部分：Agent 完整決策流程

## 3.1 Phase 0 → Scout 感知

```
觸發：定時 30min + 事件驅動
工具：✅ MarketScanner（只讀）✅ BybitDemoConnector（只讀）
輸出：MARKET_SCAN_RESULT → MessageBus
兜底：Scout 離線 → 不影響已有持倉；數據延遲 → H0 freshness 阻止
```

## 3.2 Phase 1 → Analyst 分析

```
觸發：收到 MARKET_SCAN_RESULT
工具（只讀）：IndicatorEngine, EWMAVolEstimator, HurstCalculator,
             StrategyHealthMonitor, TSR, L1 Ollama
寫操作：TSR.register()（insights，confidence ≤ 0.85）

輸出：
  MARKET_ASSESSMENT: {regime, hurst, vol_state, confidence, ts_ms, ttl_ms}
  STRATEGY_HEALTH_REPORT: {per_strategy data from HealthMonitor}
  OPPORTUNITY_LIST: {ranked opportunities}

L1→L2 升級：市場異動 > 8% + 原因不明 → ContextDistiller + Claude API
兜底：離線 → 使用上次有效 ASSESSMENT；推理超時 → {regime: "unknown", confidence: 0.3}
```

## 3.3 Phase 2 → Conductor 分配 + Strategist 決策

**Conductor**：讀取 MARKET_ASSESSMENT → 推理策略權重 → 發送 STRATEGY_DIRECTIVE

**Strategist 雙軌機制**：

### 快速通道（L0，< 10ms，Agent 不可修改的 P0/P1 規則）

```
觸發條件（任一）：
  Risk Governor ≥ DEFENSIVE
  價格變動 > 5% / 5min
  保證金使用率 > 80%

預定義規則（不可變，使用 MappingProxyType 保護）：
  DEFENSIVE       → reduce_all 50%
  CIRCUIT_BREAKER → close_all 100%
  flash_crash     → close_losing positions
  margin_critical → reduce_largest 30%

生成 intent 標記 priority=URGENT → Guardian 優先審核
```

### 正常通道（L1 Ollama，2-8s/symbol，優先級隊列）

```
優先級：P1 平倉減倉 > P2 對沖 > P3 新開倉 > P4 參數調整
隊列壓力大時：跳過 P4，縮小 P3 batch，P1/P2 始終處理

Ollama 通信格式（結構化 JSON + 強制 reasoning）：
{
  "decision": "trade" / "hold" / "close",
  "symbol": "BTCUSDT",
  "direction": "long" / "short",
  "qty_fraction": 0.8,          // 相對 PositionSizer 建議的比例
  "confidence": 0.72,
  "reasoning": "Hurst=0.61 trending + MA_Cross long + ...",
  "signals_used": ["MA_Crossover:long:0.65"],
  "signals_ignored": ["BB_Reversion"],
  "ignore_reason": "regime=trending, reversion unfit"
}

解析失敗 → fail-closed（不交易）

L1→L2 升級（不阻塞當前 intent）：
  if confidence < 0.5 and decision_value > account_5pct → API 調用
  Claude 回答寫入 TSR，影響後續決策周期（非立即執行）
```

## 3.4 Phase 3 → Guardian 審核

```
工具（全部只讀）：5 項既有檢查 + delta 驗證 + qty 驗證
無寫權限。裁決：APPROVED / REJECTED / MODIFIED
MODIFIED 約束：只能縮小 qty、降低槓桿，不能改方向/symbol
URGENT intent 優先審核
Guardian 離線 → 所有 intent 默認 REJECTED（fail-closed）
```

## 3.5 Phase 4 → Executor 執行

```
唯一寫操作：PaperTradingEngine.submit_order()
不可修改方向/symbol，qty 只能減不能增
Paired Execution：同組 intent 同時提交/同時放棄
  第一腿成功 + 第二腿失敗 → 回滾第一腿
  回滾失敗 → INCIDENT → Risk Governor 升級
```

---

# 第四部分：L0→L2 計算路徑與 API 整合

## 4.1 四層路由

| 層級 | 延遲 | 成本 | 用途 | 硬件 |
|------|------|------|------|------|
| L0 | < 1ms | $0 | H0 Gate, Guardian, 快速通道, 指標計算 | 任何 |
| L1 | 2-8s | $0 | Strategist 日常, Analyst 分析 | 當前：2×Qwen7B；未來：72B+7B×3+32B |
| L1.5 | 1-3s | ~$0.02 | 跨策略仲裁, Regime 確認, 中等回撤分析 | Claude Sonnet API |
| L2 | 3-10s | ~$0.10 | 策略衰減確認, 進化驗證, 新策略評估, 周度複盤 | Claude Opus API |

**升級條件**（滿足任一 + 未被阻止）：
- 本地 confidence < 0.5 且決策金額 > 賬戶 5%
- EvolutionEngine 參數變更 > 20% Sharpe 提升
- CUSUM 觸發策略衰減
- 市場日波動 > 8% 原因不明
- 新幣種/新策略首次評估
- 周 PnL 跌破 -5%

**阻止條件**（即使滿足升級條件）：
- 1 小時冷卻期內
- 快速通道模式中
- 月預算用完

## 4.2 Context Distillation

```python
class ContextDistiller:
    """
    壓縮系統狀態為 ~450 tokens 的摘要
    調用 API 時只發送此摘要 + 具體問題
    """
    def __init__(self):
        self._summary = {}
        self._lock = threading.Lock()  # [工程師審批：線程安全]

    def update_after_each_cycle(self, cycle_data: dict) -> None:
        with self._lock:
            self._summary = {
                "market": {
                    "btc_price": cycle_data["btc_price"],
                    "btc_24h_change": cycle_data["btc_change"],
                    "regime": cycle_data["regime"],
                    "hurst": round(cycle_data["hurst"], 2),
                    "vol_state": cycle_data["vol_state"],
                },
                "portfolio": {
                    "balance": cycle_data["balance"],
                    "delta_pct": cycle_data["delta_pct"],
                    "positions": len(cycle_data["positions"]),
                    "daily_pnl": cycle_data["daily_pnl"],
                    "weekly_pnl": cycle_data["weekly_pnl"],
                    "drawdown": cycle_data["current_dd"],
                },
                "health": {
                    n: {"sharpe": m["sharpe"], "wr": m["win_rate"],
                        "cusum": m["cusum_detected"]}
                    for n, m in cycle_data["strategy_metrics"].items()
                },
                "events": cycle_data.get("notable_events", [])[-5:],
                "ts": int(time.time()),
            }

    def get_context_for_api(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._summary)
```

## 4.3 Claude 回答閉環

```
Claude 回答格式（system prompt 強制 JSON）：
{
  "judgment": "reduce_weight",
  "confidence": 0.75,
  "reasoning": "...",
  "action_params": {"strategy": "...", "new_weight": 0.3, "duration_hours": 48,
                     "revert_condition": "hurst > 0.58 for 6h"},
  "knowledge_update": {"claim": "...", "epistemic_level": "INFERENCE",
                        "confidence": 0.65, "ttl_hours": 24}
}

流向：
  action_params → Strategist 下一輪推理的強輸入（非立即執行）
  knowledge_update → TSR（帶 TTL + source="cloud_api"）
  全部 → audit_log

原則：Claude 不直接控制系統，通過 TSR 間接影響後續決策。
```

## 4.4 API 預算管理

```python
class APIBudgetManager:
    """月度預算管理，持久化到磁盤防止重啟重置"""
    # [工程師審批：新增月度重置 + 持久化]

    def __init__(self, monthly_budget: float = 50.0,
                 costs: dict = None, cooldown_s: int = 3600,
                 persist_path: str = "api_budget_state.json"):
        self._budget = monthly_budget
        self._costs = costs or {"L1.5": 0.02, "L2": 0.10}
        self._cooldown = cooldown_s
        self._persist_path = persist_path
        self._spent = 0.0
        self._last_call_ts = 0
        self._current_month = time.strftime("%Y-%m")
        self._load()

    def can_call(self, tier: str) -> bool:
        self._check_month_reset()
        cost = self._costs.get(tier, 0.10)
        if self._spent + cost > self._budget:
            return False
        if time.time() - self._last_call_ts < self._cooldown:
            return False
        return True

    def record_call(self, tier: str) -> None:
        self._spent += self._costs.get(tier, 0.10)
        self._last_call_ts = time.time()
        self._save()

    def _check_month_reset(self):
        current = time.strftime("%Y-%m")
        if current != self._current_month:
            self._spent = 0.0
            self._current_month = current
            self._save()

    def _save(self):
        data = {"spent": self._spent, "month": self._current_month,
                "last_call": self._last_call_ts}
        try:
            with open(self._persist_path, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _load(self):
        try:
            with open(self._persist_path) as f:
                data = json.load(f)
            if data.get("month") == self._current_month:
                self._spent = data.get("spent", 0.0)
                self._last_call_ts = data.get("last_call", 0)
        except Exception:
            pass
```

## 4.5 LLM 客戶端抽象（兼容 Ollama + LM Studio）

```python
from abc import ABC, abstractmethod

class LocalLLMClient(ABC):
    @abstractmethod
    async def chat(self, messages: list, model: str,
                   temperature: float = 0.3,
                   response_format: str = "json") -> dict:
        ...

class OllamaLLMClient(LocalLLMClient):
    """現有 OllamaClient 適配"""
    def __init__(self, base_url="http://localhost:11434"):
        self._base_url = base_url
    # ... 現有代碼適配

class LMStudioLLMClient(LocalLLMClient):
    """LM Studio 適配（OpenAI 兼容 API）"""
    def __init__(self, base_url="http://localhost:1234"):
        self._base_url = base_url
    # ... 同接口，不同 base_url
```

**切換方式**：config 文件中設定 `llm_backend: "ollama"` 或 `"lmstudio"`，工廠函數創建對應實例。

---

# 第五部分：新增模組（Agent 工具化設計）

## 5.1 PositionSizer — Strategist 工具（P0）

```python
class PositionSizer:
    """
    四層倉位計算。只讀，無副作用。
    Strategist 參考結果後自主決定 qty（≤ max_allowed_qty）。
    Guardian 在 P0/P1 上限內審核。
    """

    def compute_kelly_fraction(self, win_rate: float, avg_win: float,
                                avg_loss: float, trade_count: int = 0) -> float:
        # [數學家審批：根據交易數量調整 Kelly 比例]
        aw = abs(avg_win)
        al = abs(avg_loss)  # [工程師審批：abs 保護]
        if aw <= 0 or al <= 0:
            return 0.0
        b = aw / al
        f_star = (b * win_rate - (1 - win_rate)) / b
        f_star = max(0.0, f_star)

        # [數學家審批：根據樣本量調整 Kelly 分數]
        if trade_count < 200:
            return f_star / 8   # 1/8 Kelly（數據不足）
        elif trade_count < 500:
            return f_star / 6   # 1/6 Kelly
        else:
            return f_star / 4   # 1/4 Kelly（充分數據）

    def compute_volatility_adjusted_qty(self, balance: float, atr: float,
                                         risk_pct: float = 1.0) -> float:
        risk_amount = balance * (risk_pct / 100)
        stop_distance = atr * 2
        if stop_distance <= 0:
            return 0.0
        return risk_amount / stop_distance

    def compute_risk_parity_weights(self,
                                     vols: dict[str, float]) -> dict[str, float]:
        inv = {k: 1/v for k, v in vols.items() if v > 0}
        total = sum(inv.values())
        return {k: v/total for k, v in inv.items()} if total > 0 else {}

    def compute_max_allowed_qty(self, balance: float, price: float,
                                 p1_max_pct: float = 2.0) -> float:
        """P1 硬上限"""
        return (balance * p1_max_pct / 100) / price if price > 0 else 0.0

    def compute_recommendation(self, strategy_name: str, balance: float,
                                metrics: dict, atr: float,
                                price: float) -> dict:
        m = metrics.get(strategy_name, {})
        tc = m.get("trade_count", 0)
        kelly = self.compute_kelly_fraction(
            m.get("win_rate", 0), m.get("avg_win", 0),
            m.get("avg_loss", 0), tc)
        kelly_qty = (balance * kelly) / price if price > 0 else 0.0
        vol_qty = self.compute_volatility_adjusted_qty(balance, atr)
        max_qty = self.compute_max_allowed_qty(balance, price)
        return {
            "kelly_qty": round(kelly_qty, 8),
            "vol_adjusted_qty": round(vol_qty, 8),
            "max_allowed_qty": round(max_qty, 8),
            "recommended_qty": round(min(kelly_qty, vol_qty, max_qty), 8),
            "kelly_fraction": round(kelly, 6),
            "sample_size": tc,
        }
```

## 5.2 StrategyHealthMonitor — Analyst 工具（P0）

```python
class StrategyHealthMonitor:
    """
    只讀健康度數據。Analyst 解讀，Conductor 決策。
    硬性兜底：CUSUM + 連續虧損超 P1 → 自動暫停（不等 Agent）。
    """

    def __init__(self, window: int = 50):
        self._window = window
        self._returns: dict[str, list[float]] = {}
        self._cusum: dict[str, dict] = {}

    def update(self, name: str, ret: float) -> None:
        rs = self._returns.setdefault(name, [])
        rs.append(ret)
        if len(rs) > self._window:
            rs.pop(0)
        self._update_cusum(name, ret)

    def _update_cusum(self, name: str, ret: float) -> None:
        s = self._cusum.setdefault(name, {
            "S_h": 0.0, "S_l": 0.0, "mean": 0.0, "n": 0, "detected": False})
        s["n"] += 1
        s["mean"] += (ret - s["mean"]) / s["n"]
        slack = 0.005
        s["S_h"] = max(0, s["S_h"] + ret - s["mean"] - slack)
        s["S_l"] = max(0, s["S_l"] - ret + s["mean"] - slack)
        if s["S_h"] > 0.1 or s["S_l"] > 0.1:
            s["detected"] = True

    def reset_cusum(self, name: str) -> None:
        # [工程師審批：新增重置方法，Analyst 判斷恢復後調用]
        if name in self._cusum:
            self._cusum[name] = {
                "S_h": 0.0, "S_l": 0.0, "mean": 0.0, "n": 0, "detected": False}

    def get_health_data(self, name: str) -> dict:
        rs = self._returns.get(name, [])
        cs = self._cusum.get(name, {})
        if len(rs) < 5:
            return {"status": "insufficient_data", "trade_count": len(rs)}
        mean = sum(rs) / len(rs)
        wins = sum(1 for r in rs if r > 0)
        var = sum((r - mean)**2 for r in rs) / (len(rs) - 1) if len(rs) > 1 else 0
        std = var ** 0.5
        return {
            "rolling_sharpe": round(mean / std, 4) if std > 0 else 0.0,
            "rolling_win_rate": round(wins / len(rs), 4),
            "mean_return": round(mean, 6),
            "cusum_detected": cs.get("detected", False),
            "cusum_S_h": round(cs.get("S_h", 0), 4),
            "cusum_S_l": round(cs.get("S_l", 0), 4),
            "trade_count": len(rs),
        }

    def get_all_health_data(self) -> dict[str, dict]:
        return {n: self.get_health_data(n) for n in self._returns}

    def check_hard_limit(self, name: str, max_consec: int = 15) -> bool:
        """P1 硬性兜底（不經 Agent）"""
        rs = self._returns.get(name, [])
        if len(rs) < max_consec:
            return False
        return all(r <= 0 for r in rs[-max_consec:])
```

## 5.3 EWMAVolEstimator — 感知工具（P0）

```python
class EWMAVolEstimator:
    """只讀波動率估計"""

    # [數學家審批：根據時間框架調整 lambda]
    LAMBDA_BY_TIMEFRAME = {
        "1m": 0.90,   # 半衰期 ~7 bars
        "5m": 0.92,
        "1h": 0.94,   # 半衰期 ~11 bars
        "1d": 0.97,
    }

    def __init__(self, timeframe: str = "1m"):
        self._lambda = self.LAMBDA_BY_TIMEFRAME.get(timeframe, 0.94)
        self._variance: dict[str, float] = {}
        # [工程師審批：加快長期均值適應速度]
        self._hist_mean: dict[str, float] = {}
        self._hist_decay = 0.995  # 半衰期 ~138 bars（非 0.999 的 693 bars）

    def update(self, symbol: str, return_: float) -> float:
        if symbol not in self._variance:
            self._variance[symbol] = return_ ** 2
        else:
            self._variance[symbol] = (self._lambda * self._variance[symbol]
                                      + (1 - self._lambda) * return_ ** 2)
        if symbol not in self._hist_mean:
            self._hist_mean[symbol] = self._variance[symbol]
        else:
            self._hist_mean[symbol] = (self._hist_decay * self._hist_mean[symbol]
                                       + (1 - self._hist_decay) * self._variance[symbol])
        return self._variance[symbol] ** 0.5

    def get_vol(self, symbol: str) -> float:
        return self._variance.get(symbol, 0.0) ** 0.5

    def get_vol_regime(self, symbol: str) -> str:
        vol = self.get_vol(symbol)
        mean = self._hist_mean.get(symbol, 0.0) ** 0.5
        if mean <= 0:
            return "normal"
        ratio = vol / mean
        if ratio > 1.5:
            return "high"
        elif ratio < 0.5:
            return "low"
        return "normal"
```

## 5.4 Hurst Exponent — 感知工具（P0）

```python
import math

def compute_hurst_exponent(prices: list[float],
                            min_lag: int = 10,
                            max_lag: int = 100) -> float:
    """
    R/S 分析法。每 100 bars 更新一次。
    [數學家審批：min_lag 從 2 改為 10 避免小樣本偏差]
    [數學家審批：max_lag 從 20 改為 100 提高穩定性]
    [數學家審批：判斷閾值改為 0.60/0.40 增加確定性]

    H > 0.60 → 確認趨勢
    H < 0.40 → 確認均值回歸
    0.40~0.60 → 不確定（視為隨機，縮倉）
    """
    if len(prices) < max_lag * 2:
        return 0.5

    returns = [(prices[i] / prices[i-1]) - 1 for i in range(1, len(prices))]
    log_lags, log_rs = [], []

    for lag in range(min_lag, max_lag + 1):
        rs_list = []
        n_seg = len(returns) // lag
        for si in range(n_seg):
            seg = returns[si * lag : (si + 1) * lag]
            if len(seg) < 2:
                continue
            m = sum(seg) / len(seg)
            cumdev, running = [], 0.0
            for r in seg:
                running += (r - m)
                cumdev.append(running)
            R = max(cumdev) - min(cumdev)
            S = (sum((r - m)**2 for r in seg) / len(seg)) ** 0.5
            if S > 1e-12:
                rs_list.append(R / S)
        if rs_list:
            avg_rs = sum(rs_list) / len(rs_list)
            if avg_rs > 0:
                log_lags.append(math.log(lag))
                log_rs.append(math.log(avg_rs))

    if len(log_lags) < 3:
        return 0.5

    n = len(log_lags)
    sx = sum(log_lags)
    sy = sum(log_rs)
    sxy = sum(x * y for x, y in zip(log_lags, log_rs))
    sx2 = sum(x * x for x in log_lags)
    denom = n * sx2 - sx * sx
    if abs(denom) < 1e-12:
        return 0.5
    H = (n * sxy - sx * sy) / denom
    return max(0.0, min(1.0, H))
```

## 5.5 HedgingEngine — Strategist 工具（P2）

```python
class HedgingEngine:
    """只讀 delta 計算 + 對沖建議。Strategist 決定是否採納。"""

    def compute_portfolio_delta(self, positions: dict) -> dict:
        long_e = sum(abs(p.get("qty",0) * p.get("current_price",0))
                     for p in positions.values() if p.get("side") == "Buy")
        short_e = sum(abs(p.get("qty",0) * p.get("current_price",0))
                      for p in positions.values() if p.get("side") == "Sell")
        gross = long_e + short_e
        net = long_e - short_e
        pct = (abs(net) / gross * 100) if gross > 0 else 0
        return {
            "net_delta_usdt": round(net, 2),
            "gross_exposure": round(gross, 2),
            "net_delta_pct": round(pct, 2),
            "direction": "long" if net > 0 else ("short" if net < 0 else "neutral"),
            "long_exposure": round(long_e, 2),
            "short_exposure": round(short_e, 2),
        }

    def compute_hedge_suggestion(self, delta: dict,
                                  target_pct: float = 20.0,
                                  cost_bps: float = 12.0,
                                  daily_vol: float = 2.0) -> dict:
        cur = delta["net_delta_pct"]
        if cur <= target_pct:
            return {"should_hedge": False, "reason": "within target"}
        notional = delta["gross_exposure"] * (cur - target_pct) / 100
        cost = notional * cost_bps / 10000
        benefit = notional * daily_vol / 100
        ratio = benefit / cost if cost > 0 else 0
        return {
            "should_hedge": ratio > 2.0,
            "hedge_notional": round(notional, 2),
            "cost_est": round(cost, 4),
            "benefit_est": round(benefit, 4),
            "benefit_ratio": round(ratio, 2),
            "side": "Sell" if delta["direction"] == "long" else "Buy",
        }
```

## 5.6 PnL Attribution — Analyst 工具（P2）

```python
class PnLAttributor:
    """只讀，分解 PnL 到策略/幣種/時段"""

    def attribute(self, fills: list[dict]) -> dict:
        by_s, by_sym, by_h = {}, {}, {}
        for f in fills:
            strat = f.get("strategy_name", "unknown")
            sym = f.get("symbol", "unknown")
            hour = (f.get("ts_ms", 0) // 3_600_000) * 3_600_000
            pnl, fee = f.get("realized_pnl", 0), f.get("fee", 0)
            for g, k in [(by_s, strat), (by_sym, sym), (by_h, hour)]:
                e = g.setdefault(k, {"pnl": 0.0, "fees": 0.0, "trades": 0})
                e["pnl"] += pnl; e["fees"] += fee; e["trades"] += 1
        return {"by_strategy": by_s, "by_symbol": by_sym, "by_hour": by_h}
```

---

# 第六部分：策略升級（分步驗證）

> 原則：每層升級獨立 Paper Trade 2 週。胜率提升比例 > 交易次數減少比例才合併。

## 6.1 MA_Crossover V2

Step 1: KAMA 替代 EMA（如表現不理想→P3 考慮 Kalman）
Step 2: ADX > 20 過濾
Step 3: 多時間框架確認（日線→4H→1H）

## 6.2 BB_Reversion V2

RSI<30 確認 + Regime 感知（trending 不交易）+ Limit order

## 6.3 BB_Breakout V2

Volume ratio>1.5 確認 + ATR trailing stop + Donchian 確認信號（非獨立策略）

## 6.4 FundingRateArb V2

雙腿同步 Paired Execution + Basis Trading 擴展

## 6.5 GridTrading V2

OU 動態間距（`σ/√θ + 2×fee_pct` 為下限）+ 趨勢偏移
[數學家審批：間距公式加入交易成本修正]

## 6.6 Indicator Engine 擴展（P0）

新增：KAMA, ADX, Hurst, EWMA Vol, Volume Ratio, Donchian（全部 L0 本地計算）

---

# 第七部分：學習系統整合

**TSR 雙向橋梁**：本地 LLM（≤0.85）和 Claude API（≤0.90）都向 TSR 寫入 insights，帶 TTL 和 source 標記。Strategist 查詢時不區分來源。

**ExperimentLedger**：回測結果不明確時（Sharpe 0.3-0.7），觸發 L1.5/L2 評估。

**EvolutionEngine**：Sharpe 提升 >20% 的參數變更 → L2 驗證過擬合風險 → 結果決定是否部署。

**反饋迴路修復（P0）**：TSR insights 注入 `_make_shadow_decision()` 的 confidence 調整 + Evolution→Deploy 事件連接。

---

# 第八部分：明確不做的項目

| 項目 | 理由 |
|------|------|
| HMM Regime | 過擬合風險，crypto regime 切換太快，無人持續驗證 |
| GARCH | 跳躍太多，EWMA 更鲁棒 |
| VPIN | 中頻系統預測價值低 |
| 波動率均值回歸 | 需期權，Bybit 流動性差 |
| Donchian/VolBreakout 獨立策略 | 降為 BB_Breakout 確認信號 |
| Guardian 寫權限 | 架構決策：所有 intent 由 Strategist 發起 |
| Binance 相關 | 專攻 Bybit |

---

# 第九部分：完整模組地圖

```
┌─────────────────────────────────────────────────────────────────┐
│                 硬性治理層（確定性，不經 Agent）                  │
│                                                                 │
│  H0 Gate [已有]     P0/P1 RiskManager [已有]     Kill Switch    │
│  Risk Governor [已有] Strategist 快速通道 [NEW]                  │
│  Portfolio Risk [已有] + EWMA Vol→Governor [NEW]                │
├─────────────────────────────────────────────────────────────────┤
│                 Agent 自主層（P2 空間）                          │
│                                                                 │
│  Conductor → STRATEGY_DIRECTIVE                                │
│  Strategist（雙軌）→ TradeIntent → Guardian → Executor         │
│                                                                 │
│  Agent 工具箱：                                                 │
│  ┌─ Strategist 工具 ───────────────────────────────┐           │
│  │ PositionSizer [NEW P0]    SignalEngine [已有]    │           │
│  │ HedgingEngine [NEW P2]    TSR [已有+修復]       │           │
│  │ ContextDistiller [NEW]                           │           │
│  └──────────────────────────────────────────────────┘           │
│  ┌─ Analyst 工具 ──────────────────────────────────┐           │
│  │ IndicatorEngine [已有+擴展]  EWMAVol [NEW P0]   │           │
│  │ HurstCalc [NEW P0]  HealthMonitor [NEW P0]      │           │
│  │ PnLAttributor [NEW P2]                           │           │
│  └──────────────────────────────────────────────────┘           │
│  ┌─ Executor 工具 ─────────────────────────────────┐           │
│  │ OB Imbalance [NEW P2]   Paired Execution [NEW P1]│          │
│  └──────────────────────────────────────────────────┘           │
├─────────────────────────────────────────────────────────────────┤
│                 L0→L2 計算路徑                                  │
│                                                                 │
│  L0→L1(Ollama/LMStudio)→L1.5(Sonnet)→L2(Opus)                 │
│  LocalLLMClient 抽象  ContextDistiller  APIBudgetManager       │
│  Claude→TSR 閉環（knowledge_update→TTL insight）               │
├─────────────────────────────────────────────────────────────────┤
│                 策略信號層                                       │
│  MA_Cross V2 + BB_Rev V2 + BB_Break V2 + FundArb V2 + Grid V2 │
│  + PairsTrading [P3 條件性]                                     │
├─────────────────────────────────────────────────────────────────┤
│                 數據/感知層                                       │
│  IndicatorEngine [+6 指標]  RegimeTracker [+Hurst/EWMA]        │
│  MarketDataDispatcher [+Orderbook WS P2]                        │
├─────────────────────────────────────────────────────────────────┤
│                 學習層                                           │
│  TSR [修復]  ExperimentLedger  EvolutionEngine [修復→Deploy]    │
│  BacktestEngine  L2 AI Engine [+API 擴展]                       │
├─────────────────────────────────────────────────────────────────┤
│                 基礎設施                                         │
│  PaperTradingEngine  BybitDemo  OMS SM  GovernanceHub           │
│  Control API  GUI  PostgreSQL+Redis+Qdrant+Grafana              │
│  當前：AMD AI MAX 395 (128GB) — 2×7B                           │
│  未來：Mac Studio M5 Ultra — 72B+7B×3+32B                      │
└─────────────────────────────────────────────────────────────────┘
```

---

# 第十部分：實施路線圖

## Phase 1（1-2 週）

| # | 任務 | 估時 |
|---|------|------|
| 1.1 | PositionSizer | 1d |
| 1.2 | StrategyHealthMonitor | 1d |
| 1.3 | EWMAVolEstimator | 0.5d |
| 1.4 | Hurst 計算 | 0.5d |
| 1.5 | Indicator Engine 擴展（6 指標） | 1.5d |
| 1.6 | 學習反饋迴路修復 | 0.5d |
| 1.7 | Evolution→Deploy 連接 | 0.5d |
| 1.8 | LocalLLMClient 抽象 | 0.5d |
| 1.9 | 影子決策追踪接入（階段 1 退出條件需要） | 0.5d |
| | **合計** | **~7d** |

## Phase 2（2-3 週）

| # | 任務 | 估時 |
|---|------|------|
| 2.1 | MA_Crossover V2（3 步驗證） | 3d |
| 2.2 | BB_Reversion V2 | 1.5d |
| 2.3 | BB_Breakout V2 | 1.5d |
| 2.4 | FundingRateArb V2 + Paired Execution | 4d |
| 2.5 | GridTrading V2 | 1.5d |
| 2.6 | Regime Detection 升級 | 2d |
| 2.7 | Strategist 雙軌 + 優先級隊列 | 2d |
| 2.8 | ContextDistiller | 1d |
| 2.9 | Strategist/Analyst Ollama prompt 模板 | 1.5d |
| | **合計** | **~18d** |

[優化師審批：Paired Execution 從 2.5d 調整到 4d（含回滾+錯誤處理）]
[優化師審批：新增 2.9 prompt 模板——Agent 架構的核心]

## Phase 3（2-3 週）

| # | 任務 | 估時 |
|---|------|------|
| 3.1 | Claude API 客戶端 + APIBudgetManager | 1.5d |
| 3.2 | L1→L2 路由邏輯 | 1d |
| 3.3 | Claude→TSR 閉環 | 1d |
| 3.4 | HedgingEngine | 1.5d |
| 3.5 | PnLAttributor + API + GUI | 2d |
| 3.6 | OB Imbalance + Orderbook WS | 2d |
| 3.7 | 四階段框架（GovernanceHub + 持久化） | 2d |
| | **合計** | **~11d** |

[優化師審批：Orderbook 建議用 orderbook.1 (100ms) 而非 orderbook.50 (20ms) 減少 CPU 負擔]

## Phase 4（條件性）

| # | 任務 | 前置條件 |
|---|------|---------|
| 4.1 | PairsTrading | 3 月歷史協整穩定性驗證 |
| 4.2 | Beta Hedging | HedgingEngine 穩定 1 月 |
| 4.3 | Kalman Filter | KAMA 表現不理想 |
| 4.4 | JSON→PostgreSQL | 數據量瓶頸 |
| 4.5 | Mac Studio 遷移 + 大模型 | 硬件到手 |

---

# 第十一部分：風險提醒

**最根本風險**：No proven strategy alpha（報告 §16.2）。所有策略用標準 TA，無統計邊際驗證。再好的架構，底層無 edge → 淨虧損。Paper 4 週後合併淨 PnL 為負 → 暫停新模組，聚焦 alpha 驗證。

**複雜度稅**：Phase 1-3 新增 ~10 模組。每個增加代碼維護、交互 debug、監控、治理文件更新負擔。

**驗證紀律**：不批量上線。每模組/每層升級在 Paper 中 A/B 驗證。理論更好 ≠ 實際更好。

---

# 附錄：三層專家審批修正總結

| 來源 | 問題 | 修正 |
|------|------|------|
| 數學家 | Hurst R/S min_lag=2 小樣本偏差 | min_lag=10, max_lag=100 |
| 數學家 | Hurst 分界 0.45/0.55 無統計顯著性 | 改為 0.40/0.60，中間為不確定 |
| 數學家 | EWMA lambda=0.94 對分鐘數據太慢 | 按時間框架調整：1m=0.90, 1h=0.94, 1d=0.97 |
| 數學家 | Quarter Kelly 在小樣本下仍太激進 | <200 筆 1/8 Kelly, 200-500 筆 1/6, >500 筆 1/4 |
| 數學家 | OU Grid 間距未計入交易成本 | 下限 = σ/√θ + 2×fee_pct |
| 工程師 | PositionSizer avg_loss 可能為負 | abs() 保護 |
| 工程師 | CUSUM 無重置機制 | 新增 reset_cusum() |
| 工程師 | EWMA hist_mean 衰減太慢（0.999） | 改為 0.995 |
| 工程師 | ContextDistiller 無線程安全 | 加 threading.Lock + deepcopy |
| 工程師 | 快速通道規則 dict 可被修改 | 使用 MappingProxyType 保護 |
| 工程師 | APIBudgetManager 無月度重置/持久化 | 新增 _check_month_reset + 磁盤持久化 |
| 優化師 | 缺少 Strategist prompt 模板開發項 | 新增 Phase 2.9 |
| 優化師 | 缺少影子決策追蹤機制 | 新增 Phase 1.9 |
| 優化師 | 缺少四階段持久化設計 | Phase 3.7 明確包含 GovernanceHub 持久化 |
| 優化師 | Paired Execution 估時偏低 | 從 2.5d 調整到 4d |
| 優化師 | Orderbook WS 頻率過高 | 建議 orderbook.1 (100ms) |

---

# 附錄 B：第二輪專家審批修正（11 項）

## B.1 高嚴重度修正（3 項）

### B.1.1 快速通道/正常通道競態條件（工程師）

**問題**：正常通道正在 Ollama 推理某 symbol 的做多 intent，此時閃崩觸發快速通道生成 close_all。兩個 intent 幾乎同時到達 Guardian。若 Guardian 先處理做多 → APPROVED → 開倉，再處理 close_all → 平倉，白付兩次手續費。

**修正**：快速通道觸發時立即設置 `_emergency_mode` 原子標誌。正常通道在 emit intent 前檢查此標誌——若為 True，丟棄所有正在處理和待處理的正常通道 intent。快速通道結束後重置。

```python
# Strategist 內部
self._emergency_mode = threading.Event()  # 原子性

# 快速通道觸發時
self._emergency_mode.set()
# 清空正常通道隊列
with self._queue_lock:
    self._normal_queue.clear()
# 生成緊急 intent...
# 快速通道結束後
self._emergency_mode.clear()

# 正常通道 emit 前
if self._emergency_mode.is_set():
    return  # 丟棄，不 emit
```

**影響**：§3.3 Strategist 雙軌機制，Phase 2.7。

### B.1.2 Kelly Criterion 的生存偏差（數學家）

**問題**：`win_rate` 和 `avg_win/avg_loss` 來自已平倉交易統計。當前持有的虧損倉位不在統計中。若策略快速止盈但慢速止損，win_rate 被高估，avg_loss 被低估，Kelly 基於樂觀數據計算偏大倉位。

**修正**：PositionSizer 新增未實現虧損折算邏輯。

```python
def compute_kelly_fraction(self, win_rate: float, avg_win: float,
                            avg_loss: float, trade_count: int = 0,
                            unrealized_loss: float = 0.0,
                            avg_holding_period: float = 0.0,
                            current_run_time: float = 0.0) -> float:
    # 如果運行時間不足一個完整的平均持倉周期，不信任 Kelly
    if avg_holding_period > 0 and current_run_time < avg_holding_period * 2:
        return 0.0  # 退化為 Fixed Fractional 接管

    # 將未實現虧損折算為等效虧損交易
    if unrealized_loss < 0 and trade_count > 0:
        equiv_losses = abs(unrealized_loss) / abs(avg_loss) if abs(avg_loss) > 0 else 1
        adjusted_trade_count = trade_count + equiv_losses
        adjusted_loss_count = (trade_count * (1 - win_rate)) + equiv_losses
        win_rate = 1 - (adjusted_loss_count / adjusted_trade_count)

    # ... 其餘 Kelly 計算邏輯不變
```

**影響**：§5.1 PositionSizer。

### B.1.3 Paired Execution 部分成交回滾（工程師）

**問題**：第一腿 limit order 只部分成交（下 0.1 BTC 成交 0.06），回滾時應平 0.06 而非 0.1。

**修正**：Executor 追蹤每腿實際成交量，回滾基於 `filled_qty`。

```python
# Paired Execution 回滾邏輯
class PairedExecutionState:
    def __init__(self, group_id: str):
        self.group_id = group_id
        self.legs: dict[str, dict] = {}  # leg_id → {requested_qty, filled_qty, status}

    def record_fill(self, leg_id: str, filled_qty: float):
        self.legs[leg_id]["filled_qty"] = filled_qty

    def compute_rollback_qty(self, leg_id: str) -> float:
        """回滾量 = 實際成交量，非請求量"""
        return self.legs.get(leg_id, {}).get("filled_qty", 0.0)
```

**影響**：Phase 2.4 Paired Execution。

---

## B.2 中嚴重度修正（4 項）

### B.2.1 Hurst Regime 切換 Whipsaw 保護（數學家）

**問題**：Hurst 從 0.62 掉到 0.38 又彈回 0.55，Conductor 來回切換策略權重。每次切換都有冷啟動適應期，期間表現最差。

**修正**：在 MarketRegimeTracker 層面加入 hysteresis（滯後保護）。regime 切換需要 H 在新閾值外**連續 N 個週期**才確認。

```python
# MarketRegimeTracker 新增
class HurstHysteresis:
    def __init__(self, trend_threshold: float = 0.60,
                 revert_threshold: float = 0.40,
                 required_consecutive: int = 6):  # 6 個 1h bar = 6 小時
        self._trend_th = trend_threshold
        self._revert_th = revert_threshold
        self._required = required_consecutive
        self._consecutive_trend = 0
        self._consecutive_revert = 0
        self._current_regime = "uncertain"

    def update(self, hurst: float) -> str:
        if hurst > self._trend_th:
            self._consecutive_trend += 1
            self._consecutive_revert = 0
        elif hurst < self._revert_th:
            self._consecutive_revert += 1
            self._consecutive_trend = 0
        else:
            # 在不確定區間，緩慢衰減計數（不立即歸零）
            self._consecutive_trend = max(0, self._consecutive_trend - 1)
            self._consecutive_revert = max(0, self._consecutive_revert - 1)

        if self._consecutive_trend >= self._required:
            self._current_regime = "trending"
        elif self._consecutive_revert >= self._required:
            self._current_regime = "mean_reverting"
        # 不滿足任一條件時保持當前 regime 不變

        return self._current_regime
```

所有消費者（Conductor、Strategist、策略）讀取的 regime 已經帶滯後，不需要各自實現。

**影響**：§5.4 / Phase 2.6 Regime Detection。

### B.2.2 API 冷卻期按 Tier 分離（工程師）

**修正**：`_last_call_ts` 從單一值改為按 tier 的 dict。

```python
class APIBudgetManager:
    def __init__(self, ...):
        # ...
        self._cooldowns = {"L1.5": 1800, "L2": 3600}  # 各自獨立
        self._last_call_ts = {"L1.5": 0, "L2": 0}     # 各自計時

    def can_call(self, tier: str) -> bool:
        self._check_month_reset()
        cost = self._costs.get(tier, 0.10)
        if self._spent + cost > self._budget:
            return False
        cooldown = self._cooldowns.get(tier, 3600)
        if time.time() - self._last_call_ts.get(tier, 0) < cooldown:
            return False
        return True

    def record_call(self, tier: str) -> None:
        self._spent += self._costs.get(tier, 0.10)
        self._last_call_ts[tier] = time.time()
        self._save()
```

**影響**：§4.4 APIBudgetManager。

### B.2.3 階段 0 定義（優化師）

**修正**：在 §2 四階段框架前增加階段 0。

```
階段 0：開發/部署期
  - Paper Trading 可以運行（用現有確定性邏輯）
  - 數據不計入階段 1 的退出評估
  - 階段 1 的計時從所有 P0 模組部署完成 + 冒煙測試通過後開始
  - GovernanceHub 中記錄 stage=0，deploy_complete_ts=None
  - 當 deploy_complete_ts 被設定時，自動切換到階段 1
```

**影響**：§2 四階段框架。

### B.2.4 NotableEvent 結構化定義（工程師）

**修正**：定義事件格式，防止 ContextDistiller 中的 token 爆炸。

```python
@dataclass
class NotableEvent:
    ts_ms: int
    event_type: str    # "volatility_spike" / "regime_change" / "strategy_pause"
                       # "cusum_alert" / "api_call" / "hard_limit_breach"
    summary: str       # 最大 80 字符，超出截斷
    severity: str      # "info" / "warning" / "critical"

    def to_compact_dict(self) -> dict:
        return {
            "ts": self.ts_ms,
            "type": self.event_type,
            "msg": self.summary[:80],
            "sev": self.severity,
        }
```

所有產生事件的模組統一使用此格式。ContextDistiller 中 `recent_events` 存儲 `NotableEvent.to_compact_dict()` 的結果。

**影響**：§4.2 ContextDistiller + 所有新模組。

---

## B.3 低嚴重度修正（4 項）

### B.3.1 OU 參數估計方法（數學家）

**修正**：明確指定使用 OLS 回歸。

```python
def estimate_ou_params(prices: list[float], dt: float = 1.0) -> dict:
    """
    OLS 回歸估計 OU 參數
    ΔX = α + β·X_{t-1} + ε
    θ = -β/dt,  μ = -α/β,  σ = std(ε) / sqrt(dt)
    """
    if len(prices) < 20:
        return {"theta": 0.0, "mu": 0.0, "sigma": 0.0, "valid": False}

    X = prices[:-1]
    dX = [prices[i+1] - prices[i] for i in range(len(prices)-1)]

    n = len(X)
    sum_x = sum(X)
    sum_dx = sum(dX)
    sum_x_dx = sum(x * dx for x, dx in zip(X, dX))
    sum_x2 = sum(x * x for x in X)

    denom = n * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-12:
        return {"theta": 0.0, "mu": 0.0, "sigma": 0.0, "valid": False}

    beta = (n * sum_x_dx - sum_x * sum_dx) / denom
    alpha = (sum_dx - beta * sum_x) / n

    theta = -beta / dt
    mu = -alpha / beta if abs(beta) > 1e-12 else prices[-1]

    residuals = [dx - alpha - beta * x for dx, x in zip(dX, X)]
    sigma = (sum(r * r for r in residuals) / (n - 2)) ** 0.5 / (dt ** 0.5)

    return {"theta": max(0, theta), "mu": mu, "sigma": sigma, "valid": theta > 0}
```

**影響**：§6.5 GridTrading V2。

### B.3.2 Prompt 模板動態 Schema 注入（優化師）

**修正**：每個工具提供 `get_schema()` 方法，Strategist prompt 動態包含。

```python
# 工具基類
class AgentTool(ABC):
    @abstractmethod
    def get_schema(self) -> dict:
        """返回工具的輸入輸出 schema，用於 LLM prompt"""
        ...

# PositionSizer 示例
class PositionSizer(AgentTool):
    def get_schema(self) -> dict:
        return {
            "name": "PositionSizer",
            "description": "計算最優倉位大小",
            "output_fields": {
                "kelly_qty": "Kelly 建議量",
                "vol_adjusted_qty": "波動率調整量",
                "max_allowed_qty": "P1 硬上限",
                "recommended_qty": "綜合建議（三者最小值）",
            }
        }

# Strategist prompt 動態生成
def build_strategist_prompt(tools: list[AgentTool]) -> str:
    tool_schemas = [t.get_schema() for t in tools]
    return f"""你是 Strategist Agent。可用工具：
{json.dumps(tool_schemas, ensure_ascii=False, indent=2)}

決策框架：
Step 1: 收集感知（調用只讀工具）
Step 2: 判斷是否交易
Step 3: 如果交易，確定參數（調用 PositionSizer）
Step 4: 生成 JSON 決策
"""
```

**影響**：Phase 2.9 + 所有工具模組。

### B.3.3 API 調試預算（優化師）

**修正**：APIBudgetManager 新增 `debug_mode`。

```python
class APIBudgetManager:
    def __init__(self, ..., debug_budget: float = 30.0):
        # ...
        self._debug_budget = debug_budget
        self._debug_spent = 0.0
        self._debug_mode = False

    def set_debug_mode(self, enabled: bool) -> None:
        self._debug_mode = enabled

    def can_call(self, tier: str) -> bool:
        self._check_month_reset()
        cost = self._costs.get(tier, 0.10)
        budget = self._debug_budget if self._debug_mode else self._budget
        spent = self._debug_spent if self._debug_mode else self._spent
        if spent + cost > budget:
            return False
        cooldown = 300 if self._debug_mode else self._cooldowns.get(tier, 3600)
        if time.time() - self._last_call_ts.get(tier, 0) < cooldown:
            return False
        return True

    def record_call(self, tier: str) -> None:
        cost = self._costs.get(tier, 0.10)
        if self._debug_mode:
            self._debug_spent += cost
            # debug 調用不寫入 TSR，不影響交易
        else:
            self._spent += cost
        self._last_call_ts[tier] = time.time()
        self._save()
```

**影響**：§4.4 APIBudgetManager。

### B.3.4 新模組告警條件 Checklist（優化師）

**修正**：每個新模組開發時必須定義告警條件。

```
模組開發 Checklist（新增項）：
  □ 定義 1-3 條告警條件
  □ 指定嚴重等級（INFO / WARNING / CRITICAL）
  □ 實現 get_alerts() → list[NotableEvent] 方法
  □ 接入 Control API 告警推送

示例告警條件：
  StrategyHealthMonitor:
    WARNING: CUSUM 觸發（某策略可能衰減）
    CRITICAL: 硬性連續虧損觸發（策略自動暫停）

  APIBudgetManager:
    INFO: 月預算使用 > 50%
    WARNING: 月預算使用 > 80%
    CRITICAL: 月預算用完

  EWMAVolEstimator:
    WARNING: 波動率進入 "high" regime（> 1.5x 歷史均值）

  HedgingEngine:
    WARNING: net_delta_pct > 30%（接近需要對沖）
    CRITICAL: net_delta_pct > P1 硬上限
```

**影響**：所有新模組的開發規範。

---

## B.4 第二輪修正對路線圖的影響

| Phase | 任務 | 變更 |
|-------|------|------|
| 2.4 | Paired Execution | 新增 `PairedExecutionState` + 部分成交回滾邏輯 |
| 2.6 | Regime Detection | 新增 `HurstHysteresis` 滯後保護 |
| 2.7 | Strategist 雙軌 | 新增 `_emergency_mode` 原子標誌 + 隊列清空邏輯 |
| 2.9 | Prompt 模板 | 改為動態 schema 注入方式 |
| 3.7 | 四階段框架 | 新增階段 0 定義 |
| 所有 | 模組開發 | 新增告警條件 checklist |

估時影響：Phase 2 總估時從 18d 增加到 **~20d**（主要是 HurstHysteresis 和 emergency_mode 的額外測試）。

---

# 附錄 C：第三輪專家審批修正（5 項）

## C.1 策略 Alpha 基準測試前置（優化師 — 高嚴重度）

**問題**：Phase 1-3 合計 ~38 工作日 ≈ 8 週開發，加上 Paper 驗證總體 3-4 個月。期間核心問題「No proven strategy alpha」一直未正面解決。如果策略本身沒有 edge，所有基礎設施投入是空中樓閣。

**修正**：Phase 1 新增前置任務 `1.0 策略 Alpha 基準測試`。

```
1.0 策略 Alpha 基準測試
  時機：在部署任何新模組之前
  方法：現有 5 個策略的固定參數，跑 2 週 Paper Trading
  目的：建立基準 PnL，判斷策略是否存在 edge
  
  結果判讀：
    基準 PnL > 0 → 策略有初步 edge，繼續 Phase 1
    基準 PnL ≈ 0 → 邊際不明，繼續但密切監控
    基準 PnL < -3% → 策略可能無 edge
      → 暫緩 Phase 1，優先投入策略 alpha 研究
      → 用 BacktestEngine 做更長期的歷史回測
      → 用 L2 Claude API 協助分析策略失效原因
```

不增加開發工時（只是 Paper Trading 運行），但把驗證前置。

**影響**：Phase 1 路線圖新增 1.0。

## C.2 OU theta≤0 時 Grid 應暫停（數學家 — 中嚴重度）

**問題**：B.3.1 中 `theta = max(0, theta)` 但 theta≤0 返回 `valid=True, theta=0`。theta=0 → `σ/√0 = ∞` → 間距無窮大 → 不交易但系統以為 Grid「正常運行只是不下單」。更危險的是 theta<0 意味著價格發散，Grid 完全不適用。

**修正**：

```python
# estimate_ou_params 修正
if theta <= 0:
    return {"theta": 0.0, "mu": mu, "sigma": sigma, "valid": False}
return {"theta": theta, "mu": mu, "sigma": sigma, "valid": True}

# GridTrading.recalibrate_grid() 中
params = estimate_ou_params(recent_prices)
if not params["valid"]:
    # 保持上一次有效間距，不重新校準
    logger.warning("OU params invalid (theta<=0), keeping previous grid. "
                   "Symbol may not be suitable for grid trading.")
    # 通知 Analyst
    self._emit_event(NotableEvent(
        ts_ms=now_ms, event_type="ou_invalid",
        summary=f"{self._symbol} theta<=0, grid may be unsuitable",
        severity="warning"))
    return
```

**影響**：§6.5 GridTrading V2 + B.3.1 OU 估計函數。

## C.3 HurstHysteresis 不確定區間改為凍結（數學家 — 低嚴重度）

**問題**：B.2.1 中不確定區間使用 `-1` 衰減，一次噪聲就推遲確認。

**修正**：不確定區間凍結兩個計數，不加不減。

```python
# HurstHysteresis.update() 修正
if hurst > self._trend_th:
    self._consecutive_trend += 1
    self._consecutive_revert = 0       # 對立方向歸零
elif hurst < self._revert_th:
    self._consecutive_revert += 1
    self._consecutive_trend = 0        # 對立方向歸零
else:
    pass  # 凍結：不加不減，噪聲不推遲也不加速確認
```

**影響**：附錄 B.2.1 HurstHysteresis 代碼替換。

## C.4 emergency_mode asyncio 遷移標記（工程師 — 低嚴重度）

**問題**：`threading.Event` 對 asyncio 任務不可見。未來遷移到 Mac Studio + async 推理時可能遺漏。

**修正**：代碼註釋標記。

```python
# Strategist 內部
# NOTE: 當前使用 threading.Event（系統全 threading 架構）
# TODO(mac-studio-migration): 遷移 asyncio 時替換為 asyncio.Event
#   或使用雙標誌 threading.Event + asyncio.Event 的橋接
self._emergency_mode = threading.Event()
```

**影響**：Phase 2.7 代碼註釋。

## C.5 工具 Schema 版本控制（工程師 — 低嚴重度）

**問題**：工具 `get_schema()` 字段名修改後，緩存的 prompt 可能用舊字段名靜默失敗。

**修正**：schema 帶版本號，Strategist 啟動時校驗。

```python
class AgentTool(ABC):
    @abstractmethod
    def get_schema(self) -> dict:
        """必須包含 schema_version 字段"""
        ...

# Strategist 啟動校驗
class Strategist:
    def _verify_tool_schemas(self):
        for tool in self._tools:
            schema = tool.get_schema()
            cached = self._cached_schemas.get(schema["name"])
            if cached and cached["schema_version"] != schema["schema_version"]:
                logger.warning(
                    "Tool schema version changed: %s %s→%s. Refreshing prompt.",
                    schema["name"], cached["schema_version"],
                    schema["schema_version"])
                self._refresh_prompt = True
            self._cached_schemas[schema["name"]] = schema
```

**影響**：Phase 2.9 prompt 模板 + 所有工具模組。

---

## C.6 第三輪修正對路線圖的影響

| Phase | 任務 | 變更 |
|-------|------|------|
| **1.0** | **策略 Alpha 基準測試** | **新增（前置於所有開發）** |
| 2.4 | Paired Execution | OU theta≤0 保護已含在 Grid V2 中 |
| 2.6 | Regime Detection | HurstHysteresis 凍結邏輯微調 |
| 2.7 | Strategist 雙軌 | asyncio 遷移 TODO 註釋 |
| 2.9 | Prompt 模板 | schema 版本校驗 |

**Phase 並行路徑**（優化師建議）：

```
Phase 1 依賴圖：
  1.0 Alpha 基準測試 → [2 週 Paper，並行於 1.1-1.9 開發]

  ┌─ 可並行組 A ──────────┐
  │ 1.1 PositionSizer      │
  │ 1.2 HealthMonitor      │
  │ 1.3 EWMAVol            │
  │ 1.4 Hurst              │
  └────────────────────────┘
           ↓
  1.5 Indicator Engine（依賴 1.3/1.4 接口）
  
  ┌─ 可並行組 B ──────────┐
  │ 1.6 學習迴路修復       │
  │ 1.7 Evo→Deploy         │
  │ 1.8 LocalLLMClient     │
  └────────────────────────┘
  
  1.9 影子追蹤（依賴 1.2）

  關鍵路徑：A 組(2d) → 1.5(1.5d) → 完成 ≈ 4d
  1.0 基準測試在旁邊跑 2 週，不佔開發時間
```

---

# 附錄 D：第四輪專家審批修正（2 項）

## D.1 系統健康度聚合（工程師 — 中嚴重度）

**問題**：各模組分別定義了 fail-closed 行為，但缺少統一的「系統降級矩陣」。當 Analyst 離線 + EWMAVol 異常 + Hurst 數據不足同時發生時，Strategist 不知道自己的感知數據全面降級，可能基於不可靠數據做決策。

**修正**：新增 `SystemHealthAggregator`，Strategist 推理前讀取。

```python
class SystemHealthAggregator:
    """追蹤感知工具的健康狀態"""

    def __init__(self, tool_names: list[str]):
        self._tools = set(tool_names)
        self._degraded: set[str] = set()
        self._lock = threading.Lock()

    def report_degraded(self, tool: str, reason: str = "") -> None:
        with self._lock:
            self._degraded.add(tool)

    def report_healthy(self, tool: str) -> None:
        with self._lock:
            self._degraded.discard(tool)

    def get_status(self) -> dict:
        with self._lock:
            return {
                "total_tools": len(self._tools),
                "degraded_count": len(self._degraded),
                "degraded_tools": list(self._degraded),
                "health_ratio": round(
                    1.0 - len(self._degraded) / len(self._tools), 2
                ) if self._tools else 1.0,
                "should_reduce_activity": len(self._degraded) > len(self._tools) / 2,
            }
```

Strategist 使用方式：

```python
# Strategist 正常通道推理前
sys_health = self._health_aggregator.get_status()
if sys_health["should_reduce_activity"]:
    # 超過 50% 感知工具降級 → 所有 qty 自動減半
    qty_multiplier = 0.5
    reasoning_prefix = "DEGRADED_MODE: "
else:
    qty_multiplier = 1.0
    reasoning_prefix = ""
```

各模組在異常時調用 `report_degraded()`，恢復時調用 `report_healthy()`。

**影響**：Phase 1 新增 SystemHealthAggregator（~0.5d），歸入可並行組 B。

## D.2 Claude Code 快速入口（優化師 — 中嚴重度）

**修正**：已移至報告開頭「Claude Code 快速入口」section。

---

## D.3 收斂記錄

| 輪次 | 問題數 | 最高嚴重度 | 狀態 |
|------|--------|-----------|------|
| 第一輪 | 15 | 代碼錯誤（高） | 基礎修正 |
| 第二輪 | 11 | 競態/偏差（高） | 跨模組交互 |
| 第三輪 | 5 | Alpha 前置（高） | 全局優化 |
| 第四輪 | 2 | 降級/入口（中） | 錦上添花 |
| **第五輪** | **1** | **低** | **收斂確認** |

---

# 附錄 E：第五輪 Final Audit（1 項 + 三方簽核）

## E.1 qty_fraction 乘法顯式化（工程師 — 低嚴重度）

**問題**：Strategist Ollama 輸出 `qty_fraction`（如 0.8），需乘以 `PositionSizer.recommended_qty` 得到絕對 qty。如果 Strategist 代碼直接把 `qty_fraction` 當作絕對 qty 寫入 intent，0.8 會被當作 0.8 BTC。雖然 Guardian 的 `max_allowed_qty` 會擋住，但不如顯式化安全。

**修正**：Strategist 的 intent 生成用確定性代碼做乘法，不依賴 LLM 輸出的絕對數值。

```python
# Strategist intent 生成（確定性代碼，不在 Ollama 推理內）
sizing = self._position_sizer.compute_recommendation(
    strategy_name=decision["strategy"],
    balance=account_balance,
    metrics=strategy_metrics,
    atr=current_atr,
    price=current_price,
)

# LLM 只輸出比例，絕對值由確定性代碼計算
raw_fraction = decision.get("qty_fraction", 0.5)
# 夾緊到 [0.1, 1.0]，防止 LLM 輸出異常值
fraction = max(0.1, min(1.0, raw_fraction))

final_qty = sizing["recommended_qty"] * fraction
final_qty = min(final_qty, sizing["max_allowed_qty"])  # 雙重保護

# 系統降級時額外縮減（附錄 D.1）
sys_health = self._health_aggregator.get_status()
if sys_health["should_reduce_activity"]:
    final_qty *= 0.5

intent = TradeIntent(
    symbol=decision["symbol"],
    side=decision["direction_to_side"],
    qty=final_qty,
    # ...
)
```

**關鍵設計原則**：LLM 只輸出「比例」和「方向」等定性判斷，所有定量計算（絕對 qty、價格、止損距離）由確定性代碼完成。這確保即使 LLM 產生異常輸出，通過 `max(0.1, min(1.0, ...))` 夾緊 + `min(final_qty, max_allowed_qty)` 雙重保護 + Guardian 審核三道防線，不會造成危險的倉位。

**影響**：Phase 2.7 Strategist 雙軌機制中的 intent 生成邏輯。

---

## E.2 五輪審批最終簽核

| 審批人 | 第五輪結論 | 簽核 |
|--------|-----------|------|
| 應用數學家 | 所有數學模型完備，無新增問題 | ✅ 通過 |
| 資深工程師 | 1 項低嚴重度微調（qty 顯式化），已修正 | ✅ 通過 |
| 資深優化師 | 完整性、一致性、可操作性全部通過 | ✅ 通過 |

## E.3 五輪審批累計修正統計

```
總修正數：34 項
  數學相關：10 項（Hurst×4, EWMA×2, Kelly×2, OU×3, Grid×1，部分跨類）
  工程相關：13 項（線程安全×2, 保護×2, 持久化×2, 競態×1,
                   回滾×1, 格式×1, 版本×1, 降級×1, 抽象×1, qty×1, 標記×1）
  優化相關：11 項（估時×1, 遺漏任務×3, 階段×1, 並行×1,
                   入口×1, 預算×1, 告警×1, schema×1, 基準測試×1）

嚴重度分布：
  高：5 項（第 1-3 輪）
  中：13 項（第 1-4 輪）
  低：16 項（第 1-5 輪）

收斂趨勢：15 → 11 → 5 → 2 → 1
```

---

# 定稿聲明

本報告經五輪三方專家審批（應用數學家、資深工程師、資深優化師），累計 34 項修正後定稿。

報告涵蓋：
- Agent 自主化架構設計（雙層決策 + 工具分類 + 四階段遞進）
- 完整決策流程（Scout→Analyst→Conductor→Strategist→Guardian→Executor）
- L0→L2 四層計算路徑 + Claude API 整合 + Token 節省方案
- 10 個新增模組的代碼實現（全部 Agent 工具化設計）
- 5 個現有策略的 V2 升級方案
- 硬件適配（AMD AI MAX 395 → Mac Studio M5 Ultra）
- LLM 軟件適配（Ollama → LM Studio 抽象接口）
- 三階段實施路線圖（~36 工作日 + 2 週基準測試）
- 明確不做清單（8 項）
- 風險提醒 + 驗證紀律
