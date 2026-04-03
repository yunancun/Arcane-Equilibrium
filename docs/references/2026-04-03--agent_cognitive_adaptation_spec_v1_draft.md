# Agent 認知自適應與急迫感驅動規範

**日期**: 2026-04-03
**版本**: V1.1-REVISED + R1 修正（基於 PM/PA/FA/E5/QC 五角色交叉審查 + Round 1 審計）
**基於**: OPENCLAW_IMPROVEMENT_REPORT_V3_FINAL + 多輪架構討論
**定位**: V3 報告的補充規範，新增三個模組 + 對現有模組的整合修改
**原則**: 永遠不限制 Agent 能力，只改變 Agent 思考的深度和廣度

---

# V1.1 修訂摘要（2026-04-03，五角色審查後）

```
QC 數學修正（6 項）：
  Q1. 多因子叠加 sum → max 單因子（防止隱性停機）
  Q2. 虛擬 PnL 扣除 2x estimated_fee_pct（修正系統性高估）
  Q3. 1.5x 硬閾值 → 歸一化比較（消除止盈/止損不對稱偏差）
  Q4. 每參數值最少 30 輪模擬（原 3 輪無統計意義）
  Q5. 啟發式置信度 → binomial test（統計學正確）
  Q6. 所有調製輸出加 EMA 平滑 alpha=0.3（抑制極限環振盪）

E5 代碼修正（6 項）：
  E1. CognitiveModulator.update() 拆分為 4 個 _compute_*() 方法
  E2. regret_from_overtrading 重命名為 bullets_dodged（修正語義矛盾）
  E3. OpportunityTracker 增加 _flush_closed() 批量移轉
  E4. get_alerts() 讀緩存而非重算
  E5. DreamEngine 加 threading.Lock + 修正 cycles 計數
  E6. _simulate_single_run 方向改隨機 + TODO 標記

FA 復用標記（3 項）：
  F1. DreamEngine 應復用 EvolutionEngine/BacktestEngine 模擬邏輯
  F2. CognitiveModulator 注入 shadow_decision_builder 現有門檻框架
  F3. consecutive_loss 數據源復用 strategy_auto_deployer

PA 架構決策（2 項）：
  P1. 三模組放 local_model_tools/（與 indicator_engine 同層）
  P2. Phase 1 無 ContextDistiller 時，Strategist 直連讀取（Phase 2 遷移）

Round 1 審計修正（10 項，2026-04-03）：
  R1-1. _compute_scan_interval 加 overtrading 減速分支（修正單向 bug）
  R1-2. record_skipped() 末尾清除 _cached_summary（修正緩存失效遺漏）
  R1-3. DreamEngine 防重入互斥（is_running 檢查）
  R1-4. run_cycle() 標註用 asyncio.to_thread() 包裝 + §5.1.5 代碼同步修正
  R1-5. 連虧 ≥3 時忽略負向調整（防止壓力期反降門檻）
  R1-6. import math/threading 標註移至模組頂層
  R1-7. DreamEngine 估時 1.5d → 2.0d
  R1-8. Q3 最少樣本 3 → 5
  R1-9. ESTIMATED_FEE_PCT 加注釋說明含滑點
  R1-10. DreamEngine 加可選 seed 參數 + 獨立隨機源
```

---

# Claude Code 快速入口

```
本文件是 V3 報告的擴展 SPEC。

核心思想：
  Agent 的「急迫感」不來自虛擬門檻或人工注入的壓力文字，
  而來自三個機制的協同作用——
    1. L0 認知調製（改變決策參數的邊界，不改變能力）
    2. 遺憾追蹤（具體的、可歸因的「我本可以做得更好」的證據）
    3. 夢境循環（把閒置成本轉化為認知積累）

開發位置：Phase 1 可並行組 B（1.10 / 1.11 / 1.12）
依賴關係：不依賴其他新模組，僅依賴已有的 Scout 輸出和 K 線數據
硬件開銷：全部 L0 計算，零 API 成本，零額外 LLM 調用

閱讀順序：
  1. §1 設計哲學（理解為什麼不用代謝模型和內部經濟體）
  2. §2-4 三個新模組的代碼定義
  3. §5 與 V3 報告的整合點（哪些現有代碼需要修改）
  4. §6 與 Ollama JSON 通信的整合（跳過自然語言）
  5. §7 開發路線圖
```

---

# 第一部分：設計哲學

## 1.1 被否決的方案

### 代謝模型（Metabolic Agent）— 否決

每個 Agent 持有虛擬 energy_pool，能力綁定能量水平。

**否決理由**：虛擬稀缺性疊加在真實稀缺性之上。Scout 能量耗盡的那天，恰好出現本月最佳機會——真實世界裡算力充足、資金充足、風控允許，但 Scout 因為虛擬規則「掃不了」。虛擬約束和市場節奏之間沒有因果關係，最好的機會往往出現在最難受的時候——恰恰是虛擬能量最低的時候。

### 內部經濟體（Agent Internal Economy）— 否決

5 個 Agent 之間用虛擬貨幣交易信息和決策權。

**否決理由**：任何 40% 勝率的策略都可能連虧 6-8 筆（統計學正常現象）。內部經濟體把正常的統計波動懲罰成「信譽降級」，Strategist 被迫縮手，恰好錯過第 9 筆的大盈利。市場突然轉向需要所有 Agent 全力運作時，內部經濟的「預算」已經在低谷——Agent 集體處於「節能模式」，而這正是最需要全速運轉的時刻。

### 核心教訓

正確的模型不是限制 Agent 的**能力**，而是改變 Agent 的**認知方式**。優秀的交易員在連虧之後，眼睛還能看、手還能下單、腦子還能算。改變的是注意力分配和自我審視的深度。

## 1.2 採納的方案：認知調製（Cognitive Modulation）

**Agent 的所有能力永遠完整可用**。硬性邊界只有 P0/P1（真實的、必要的）。

改變的是 Agent 做決策時的**參數空間**和**信息構成**：

```
代謝模型說：「你能量不夠了，你不能做這件事。」
認知調製說：「你可以做任何事，但你的決策門檻根據歷史表現動態調整了。」

效果相似（壓力下更審慎），但認知調製永遠不會錯過真正的好機會，
因為它不鎖門——它只是把門檻提高了。
Agent 在看到足夠強的信號時，仍然可以跨過更高的門檻。
```

## 1.3 三個機制的分工

```
CognitiveModulator（L0 確定性代碼）
  職責：根據歷史表現動態調整 Strategist 的決策參數
  方式：改變 confidence 門檻、qty 上界、止損倍率、掃描頻率
  時機：每個決策周期開始時調用，在 Ollama 推理之前生效
  成本：零（微秒級浮點運算）
  
OpportunityTracker（L0 數據追蹤）
  職責：追蹤未執行機會的虛擬表現，計算遺憾和躲過的子彈
  方式：Scout 每輪存入被篩掉的機會快照，每 tick 更新虛擬 PnL
  時機：持續後台運行
  成本：零（環形緩衝區 + 浮點更新）
  
DreamEngine（L0 蒙特卡洛模擬）
  職責：閒置時用真實 K 線跑 what-if 模擬，輸出參數優化建議
  方式：隨機抽取最近 7 天 K 線片段 × 不同參數組合 → 統計最優
  時機：系統無活躍交易決策時
  成本：零 API 成本（純本地計算），CPU 低優先級
```

三者的共同特點：**永遠不限制 Agent 能做什麼，只改變 Agent 思考的深度和廣度。**

## 1.4 工具分類（遵循 V3 報告 §1.3 規範）

| 模組 | 類別 | 誰可用 | 規則 |
|------|------|--------|------|
| CognitiveModulator | **只讀** | Strategist, Conductor | 無副作用，返回當前調製參數 |
| OpportunityTracker | **受限寫** | Scout → 寫入快照；Analyst → 只讀查詢 | Scout 每輪存入被篩掉的機會 |
| DreamEngine | **只讀** | Strategist, Analyst | 輸出建議，不修改任何策略參數 |

---

# 第二部分：CognitiveModulator

## 2.1 設計原則

```
1. 純 L0 確定性代碼，不調用任何 LLM
2. 所有計算 < 1ms
3. 只輸出數字（門檻、上界、倍率），不輸出文字
4. 所有調製方向都有上下限（夾緊），防止極端值
5. 調製只能讓 Agent 更審慎或更積極地優化，
   不能讓 Agent 突破 P0/P1 風控邊界
```

## 2.2 代碼定義

```python
class CognitiveModulator:
    """
    L0 確定性認知調製器。
    根據歷史表現、遺憾數據、夢境建議，動態調整 Strategist 的決策參數。
    
    工具分類：只讀（Agent 讀取調製值，不可覆寫公式）
    延遲：< 1ms
    API 成本：$0
    
    設計哲學：不限制能力，只調整門檻。
    Agent 在看到足夠強的信號時，仍然可以跨過更高的門檻做出決策。
    
    V1.1 修正：
      [Q1] 多因子叠加 sum → max 單因子（防止連虧+週虧+遺憾三重叠加導致隱性停機）
      [Q6] 所有輸出加 EMA 平滑 alpha=0.3（抑制 2-3 週極限環振盪）
      [E1] update() 拆分為 4 個 _compute_*() 私有方法（便於單元測試）
      [F2] 注入點：shadow_decision_builder 現有 confidence 門檻框架
      [F3] consecutive_loss 數據源：strategy_auto_deployer._consecutive_losses
    """
    
    # --- 可配置常量（Operator 可調，Agent 不可調）---
    BASE_CONFIDENCE_FLOOR = 0.60      # 正常模式的最低 confidence 門檻
    BASE_QTY_CEILING = 1.0            # 正常模式的 qty_fraction 上界
    BASE_STOPLOSS_MULTIPLIER = 1.0    # 正常模式的止損距離倍率
    BASE_SCAN_INTERVAL_S = 1800       # 正常模式的掃描間隔（30min）
    
    # 調製邊界（防止極端值）
    MAX_CONFIDENCE_FLOOR = 0.85       # confidence 門檻不能高到讓 Agent 什麼都不做
    MIN_CONFIDENCE_FLOOR = 0.45       # 也不能低到讓 Agent 什麼都做
    MIN_QTY_CEILING = 0.3             # qty 上界不能低到讓倉位毫無意義
    MAX_STOPLOSS_MULTIPLIER = 2.0     # 止損不能放太寬
    MIN_SCAN_INTERVAL_S = 300         # 最快 5 分鐘掃一次
    MAX_SCAN_INTERVAL_S = 3600        # 最慢 1 小時掃一次
    
    # [Q6] EMA 平滑係數（0 = 不平滑，1 = 完全跟隨新值）
    EMA_ALPHA = 0.3
    
    def __init__(self):
        self._confidence_floor = self.BASE_CONFIDENCE_FLOOR
        self._qty_ceiling = self.BASE_QTY_CEILING
        self._stoploss_multiplier = self.BASE_STOPLOSS_MULTIPLIER
        self._scan_interval_s = self.BASE_SCAN_INTERVAL_S
    
    def update(self,
               recent_trades: list[dict],
               regret_data: dict,
               dream_data: dict,
               weekly_net_pnl: float,
               consecutive_losses: int) -> None:
        """
        每個決策周期開始時調用一次。
        基於最新數據重新計算所有調製參數。
        
        [E1] 拆分為 4 個 _compute_*() 方法，各自可獨立測試。
        [Q6] 所有目標值通過 EMA 平滑後才寫入，避免突變引發振盪。
        
        Parameters:
            recent_trades: 最近 N 筆交易的結果
                [{pnl, fee, strategy, symbol, ts_ms}, ...]
            regret_data: OpportunityTracker.get_regret_summary() 的輸出
                {bullets_dodged, regret_from_undertrading, 
                 top_missed, net_regret_direction}
            dream_data: DreamEngine.get_insights() 的輸出
                {strategy_name: {param: value, confidence: float}, ...}
            weekly_net_pnl: 本週淨 PnL（已扣除所有成本）
            consecutive_losses: 當前連續虧損筆數（0 表示上一筆是盈利的）
        """
        target_floor = self._compute_confidence_floor(
            regret_data, weekly_net_pnl, consecutive_losses)
        target_ceiling = self._compute_qty_ceiling(
            weekly_net_pnl, consecutive_losses)
        target_sl = self._compute_stoploss_multiplier(dream_data)
        target_scan = self._compute_scan_interval(
            regret_data, weekly_net_pnl)
        
        # [Q6] EMA 平滑：new = alpha * target + (1 - alpha) * old
        a = self.EMA_ALPHA
        self._confidence_floor = a * target_floor + (1 - a) * self._confidence_floor
        self._qty_ceiling = a * target_ceiling + (1 - a) * self._qty_ceiling
        self._stoploss_multiplier = a * target_sl + (1 - a) * self._stoploss_multiplier
        self._scan_interval_s = int(a * target_scan + (1 - a) * self._scan_interval_s)
    
    def _compute_confidence_floor(self, regret_data: dict,
                                   weekly_net_pnl: float,
                                   consecutive_losses: int) -> float:
        """
        [Q1] 多因子取 max 而非 sum，防止三重叠加導致隱性停機。
        [R1-5] 連虧 ≥3 時忽略負向調整，防止壓力期反降門檻。
        
        最壞情況（V1 sum）：overtrading(+0.05) + 連虧7(+0.10) + 週虧(+0.02) = +0.17
          → floor = 0.77，配合 qty_ceiling 降至 0.75，Agent 實質停擺。
        
        修正後（V1.1 max）：max(0.05, 0.10, 0.02) = +0.10
          → floor = 0.70，Agent 仍可對 0.70+ confidence 的信號行動。
        """
        pos_adjustments = []
        neg_adjustments = []
        
        # 遺憾信號
        direction = regret_data.get("net_regret_direction")
        if direction == "overtrading":
            pos_adjustments.append(+0.05)
        elif direction == "undertrading":
            neg_adjustments.append(-0.03)  # 降低幅度小於提高幅度（保守偏好）
        
        # 連續虧損調製：連虧越多，門檻越高
        if consecutive_losses >= 3:
            loss_adj = 0.02 * min(consecutive_losses - 2, 5)
            pos_adjustments.append(+loss_adj)
            # 連虧 3 筆 +0.02, 連虧 5 筆 +0.06, 連虧 7 筆 +0.10（封頂）
        
        # 週度表現調製
        if weekly_net_pnl < 0:
            pos_adjustments.append(+0.02)
        
        # [Q1] 正向調整取 max（最大壓力因子）
        pos_net = max(pos_adjustments) if pos_adjustments else 0
        
        # [R1-5] 連虧 ≥3 時忽略負向調整（壓力期不應降門檻）
        # 理由：連虧中 undertrading 信號可能是噪音（虛擬 PnL 不含市場環境變化）
        if consecutive_losses >= 3:
            neg_net = 0
        else:
            neg_net = min(neg_adjustments) if neg_adjustments else 0
        
        floor = self.BASE_CONFIDENCE_FLOOR + pos_net + neg_net
        return max(self.MIN_CONFIDENCE_FLOOR, min(self.MAX_CONFIDENCE_FLOOR, floor))
    
    def _compute_qty_ceiling(self, weekly_net_pnl: float,
                              consecutive_losses: int) -> float:
        """[Q1] qty_ceiling 同樣使用 max 單因子而非 sum。"""
        adjustments = []
        
        if consecutive_losses >= 3:
            adjustments.append(-0.05 * min(consecutive_losses - 2, 5))
        
        if weekly_net_pnl < 0:
            adjustments.append(-0.1)
        
        # [Q1] 負向調整取 min（最大壓力因子）
        net_adj = min(adjustments) if adjustments else 0
        ceiling = self.BASE_QTY_CEILING + net_adj
        return max(self.MIN_QTY_CEILING, min(self.BASE_QTY_CEILING, ceiling))
    
    def _compute_stoploss_multiplier(self, dream_data: dict) -> float:
        """止損倍率調製（基於 DreamEngine 建議）。"""
        multiplier = self.BASE_STOPLOSS_MULTIPLIER
        
        dream_sl = dream_data.get("global", {}).get("stoploss_multiplier")
        dream_conf = dream_data.get("global", {}).get("confidence", 0)
        if dream_sl is not None and dream_conf > 0.6:
            multiplier = (multiplier * (1 - dream_conf * 0.3) +
                         dream_sl * dream_conf * 0.3)
        
        return max(0.8, min(self.MAX_STOPLOSS_MULTIPLIER, multiplier))
    
    def _compute_scan_interval(self, regret_data: dict,
                                weekly_net_pnl: float) -> int:
        """
        掃描間隔調製。
        [R1-1] 修正：overtrading 時減慢掃描（原版只有加速沒有減速）。
        """
        direction = regret_data.get("net_regret_direction")
        
        interval = self.BASE_SCAN_INTERVAL_S
        
        # 加速因子（看得更多）
        if weekly_net_pnl < 0:
            interval = min(interval, int(self.BASE_SCAN_INTERVAL_S * 0.5))
        if direction == "undertrading":
            interval = min(interval, int(self.BASE_SCAN_INTERVAL_S * 0.7))
        
        # [R1-1] 減速因子（減少頻率，配合高門檻）
        if direction == "overtrading":
            interval = max(interval, int(self.BASE_SCAN_INTERVAL_S * 1.5))
        
        return max(self.MIN_SCAN_INTERVAL_S, min(self.MAX_SCAN_INTERVAL_S, interval))
    
    # === 只讀查詢接口 ===
    
    def get_confidence_floor(self) -> float:
        """Strategist 在生成 intent 前檢查：
           if decision.confidence < this_value → 不生成 intent"""
        return self._confidence_floor
    
    def get_qty_ceiling(self) -> float:
        """Strategist 在計算 qty 時：
           fraction = max(0.1, min(this_value, raw_fraction))"""
        return self._qty_ceiling
    
    def get_stoploss_multiplier(self) -> float:
        """Strategist 在設定止損距離時：
           actual_stoploss = base_stoploss * this_value"""
        return self._stoploss_multiplier
    
    def get_scan_interval_seconds(self) -> int:
        """Scout 的掃描間隔：
           下一次掃描 = 上一次掃描 + this_value"""
        return self._scan_interval_s
    
    def get_all_params(self) -> dict:
        """用於 ContextDistiller 壓縮和審計日誌"""
        return {
            "confidence_floor": round(self._confidence_floor, 4),
            "qty_ceiling": round(self._qty_ceiling, 4),
            "stoploss_multiplier": round(self._stoploss_multiplier, 4),
            "scan_interval_s": self._scan_interval_s,
        }
    
    def get_schema(self) -> dict:
        """AgentTool 接口（V3 報告 B.3.2 規範）"""
        return {
            "name": "CognitiveModulator",
            "schema_version": 1,
            "description": "動態決策參數調製（L0 確定性）",
            "output_fields": {
                "confidence_floor": "最低 confidence 門檻",
                "qty_ceiling": "qty_fraction 上界",
                "stoploss_multiplier": "止損距離倍率",
                "scan_interval_s": "掃描間隔秒數",
            }
        }
    
    def get_alerts(self) -> list:
        """告警條件（V3 報告 B.3.4 規範）"""
        alerts = []
        if self._confidence_floor > 0.75:
            alerts.append({
                "severity": "warning",
                "msg": f"Confidence floor elevated to {self._confidence_floor:.2f}, "
                       f"Agent entering cautious mode"
            })
        if self._qty_ceiling < 0.5:
            alerts.append({
                "severity": "warning",
                "msg": f"Qty ceiling reduced to {self._qty_ceiling:.2f}, "
                       f"position sizes significantly limited"
            })
        return alerts
```

## 2.3 關鍵設計決策

**[V1.1 新增] 為什麼多因子取 max 而非 sum？（Q1 修正）**

V1 的 sum 模式在最壞情況下（overtrading + 連虧 7 + 週虧）會將 floor 推到 0.77，配合 qty_ceiling 降至 0.75，Agent 實質停擺——這違反「封頂確保行動能力」的設計初衷。取 max 確保只有最強的單一壓力信號生效，floor 最多到 0.70，Agent 仍可對高 confidence 信號行動。

**[V1.1 新增] 為什麼加 EMA 平滑？（Q6 修正）**

無平滑時，三模塊耦合後可能產生極限環振盪：連虧 → floor 升高 → 跳過機會 → 7 天後 regret 顯示 undertrading → floor 降低 → 開始交易 → 再次連虧 → 重複（週期 ~2-3 週）。EMA alpha=0.3 使每次調製只向目標值移動 30%，自然阻尼振盪。

**為什麼降低門檻的幅度（-0.03）小於提高門檻的幅度（+0.05）？**

保守偏好。在不確定時偏向「少做」比「多做」安全。人類交易員也是這樣——從虧損中恢復信心需要的正面證據，比失去信心需要的負面證據更多。

**為什麼連續虧損的調製有封頂（max 5 次額外加碼）？**

如果連虧 20 筆把 confidence_floor 推到 0.90 以上，Agent 幾乎什麼都做不了。但連虧 20 筆可能意味著市場結構性變化——這時候需要的是 Analyst 做深度分析和策略重組（L1/L2），而不是無限提高門檻。封頂確保 Agent 始終保有行動能力。

**為什麼掃描頻率在虧損時加快而不是放慢？**

虧損時的正確反應是**更積極地尋找機會**（但更謹慎地篩選和執行），而不是「躲起來不看市場」。掃描加速 + 門檻提高 = 看得更多但做得更少 = 只做最有把握的交易。

---

# 第三部分：OpportunityTracker

## 3.1 設計原則

```
1. 追蹤「沒做的事」和「做了的事」一樣重要
2. 遺憾數據的價值在於精確歸因，不是模糊的「表現不好」
3. 環形緩衝區設計，內存佔用恆定，長期運行不膨脹
4. 虛擬 PnL 用 L0 計算，不增加任何 LLM 調用
5. 第一天就開始積累數據（Phase 1 部署）
```

## 3.2 代碼定義

```python
import time
from collections import deque
from dataclasses import dataclass, field

@dataclass
class SkippedOpportunity:
    """被 Scout/Strategist 篩掉的機會快照"""
    symbol: str
    direction: str                    # "long" / "short"
    entry_price: float                # 被篩掉時的價格
    signal_confidence: float          # 原始信號的 confidence
    skip_reason: str                  # 為什麼被篩掉（≤80 字符）
    skip_source: str                  # "scout_filter" / "strategist_hold" / "guardian_reject"
    ts_ms: int                        # 被篩掉的時間戳
    strategy_name: str                # 關聯的策略
    
    # 追蹤欄位（後續 tick 更新）
    peak_favorable_pnl: float = 0.0   # 如果做了，最大浮盈是多少
    peak_adverse_pnl: float = 0.0     # 如果做了，最大浮虧是多少
    current_virtual_pnl: float = 0.0  # 當前虛擬 PnL
    last_update_ts_ms: int = 0        # 最後更新時間
    closed: bool = False              # 是否已結算（超過 TTL 或觸及虛擬止損/止盈）
    final_pnl: float = 0.0           # 結算時的虛擬 PnL

class OpportunityTracker:
    """
    追蹤未執行機會的虛擬表現。
    
    工具分類：受限寫
      Scout → record_skipped()（存入快照）
      Strategist → record_skipped()（hold 決策也記錄）
      Guardian → record_skipped()（reject 也記錄）
      Analyst/CognitiveModulator → get_regret_summary()（只讀查詢）
    
    延遲：record < 0.1ms, update_all < 5ms (100 條), query < 1ms
    API 成本：$0
    內存：~100 條 × ~200 bytes ≈ 20KB（恆定）
    
    V1.1 修正：
      [Q2] 虛擬 PnL 扣除 2x ESTIMATED_FEE_PCT 摩擦成本（修正系統性高估）
      [Q3] 遺憾方向判斷改為歸一化比較（消除止盈/止損不對稱偏差）
      [E2] regret_from_overtrading 重命名為 bullets_dodged（修正語義矛盾）
      [E3] 新增 _flush_closed() 批量移轉已結算項（遍歷中不修改集合）
      [E4] get_alerts() 讀 _cached_summary 而非重新計算
    """
    
    MAX_TRACKED = 100                  # 同時追蹤的最大機會數
    TTL_MS = 7 * 24 * 3600 * 1000     # 7 天後自動結算
    VIRTUAL_STOPLOSS_PCT = 5.0        # 虛擬止損 5%（假設的合理止損）
    VIRTUAL_TAKEPROFIT_PCT = 10.0     # 虛擬止盈 10%
    ESTIMATED_FEE_PCT = 0.075         # [Q2] 預估單邊手續費（Bybit VIP0 taker 0.055% + 滑點估算 0.02%）
                                       # [R1-9] 刻意偏高：寧可高估費用抑制虛假 regret，勿「修正」為真實費率
    
    def __init__(self):
        self._opportunities: deque[SkippedOpportunity] = deque(maxlen=self.MAX_TRACKED)
        self._settled: deque[SkippedOpportunity] = deque(maxlen=500)  # 已結算的歷史
        self._cached_summary: dict | None = None  # [E4] 緩存摘要
    
    def record_skipped(self, symbol: str, direction: str,
                       entry_price: float, signal_confidence: float,
                       skip_reason: str, skip_source: str,
                       strategy_name: str) -> None:
        """
        Scout/Strategist/Guardian 篩掉一個機會時調用。
        
        skip_source 枚舉：
          "scout_filter"    — Scout L0 預篩階段篩掉
          "strategist_hold" — Strategist 推理後決定 hold
          "guardian_reject"  — Guardian 審核拒絕
        """
        opp = SkippedOpportunity(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            signal_confidence=signal_confidence,
            skip_reason=skip_reason[:80],
            skip_source=skip_source,
            strategy_name=strategy_name,
            ts_ms=int(time.time() * 1000),
            last_update_ts_ms=int(time.time() * 1000),
        )
        self._opportunities.append(opp)
        self._cached_summary = None  # [R1-2] 新記錄加入後清除緩存
    
    def update_virtual_pnl(self, current_prices: dict[str, float]) -> None:
        """
        每個 tick 或每分鐘調用一次。
        用當前市場價格更新所有未結算機會的虛擬 PnL。
        
        [Q2] 虛擬 PnL 扣除 2x ESTIMATED_FEE_PCT（開倉+平倉），
             防止系統性高估 regret_from_undertrading 推動 Agent 更激進。
        [E3] 遍歷中只標記 closed，遍歷後批量移轉到 _settled。
        
        Parameters:
            current_prices: {symbol: current_price, ...}
        """
        now_ms = int(time.time() * 1000)
        
        for opp in self._opportunities:
            if opp.closed:
                continue
            
            price = current_prices.get(opp.symbol)
            if price is None or opp.entry_price <= 0:
                continue
            
            # 計算虛擬 PnL（百分比）
            if opp.direction == "long":
                raw_pnl_pct = (price - opp.entry_price) / opp.entry_price * 100
            else:  # short
                raw_pnl_pct = (opp.entry_price - price) / opp.entry_price * 100
            
            # [Q2] 扣除 round-trip 摩擦成本（開倉 + 平倉 = 2x fee）
            pnl_pct = raw_pnl_pct - 2 * self.ESTIMATED_FEE_PCT
            
            opp.current_virtual_pnl = pnl_pct
            opp.peak_favorable_pnl = max(opp.peak_favorable_pnl, pnl_pct)
            opp.peak_adverse_pnl = min(opp.peak_adverse_pnl, pnl_pct)
            opp.last_update_ts_ms = now_ms
            
            # 結算條件：觸及虛擬止損/止盈 或 超過 TTL
            should_close = False
            if pnl_pct <= -self.VIRTUAL_STOPLOSS_PCT:
                should_close = True  # 虛擬止損觸發
            elif pnl_pct >= self.VIRTUAL_TAKEPROFIT_PCT:
                should_close = True  # 虛擬止盈觸發
            elif now_ms - opp.ts_ms > self.TTL_MS:
                should_close = True  # TTL 到期
            
            if should_close:
                opp.closed = True
                opp.final_pnl = pnl_pct
        
        # [E3] 批量移轉已結算項（遍歷後修改，避免遍歷中改集合）
        self._flush_closed()
    
    def _flush_closed(self) -> None:
        """[E3] 將已結算的機會從 _opportunities 移轉到 _settled。"""
        closed_items = [o for o in self._opportunities if o.closed]
        for item in closed_items:
            self._opportunities.remove(item)
            self._settled.append(item)
        if closed_items:
            self._cached_summary = None  # [E4] 數據變更，清除緩存
    
    def get_regret_summary(self, window_days: int = 7) -> dict:
        """
        計算遺憾摘要。CognitiveModulator 和 ContextDistiller 使用。
        
        [E2] regret_from_overtrading → bullets_dodged（語義修正）
        [Q3] 遺憾方向判斷改為歸一化比較（消除止盈/止損不對稱偏差）
        [E4] 結果緩存到 _cached_summary
        
        Returns:
            {
                "bullets_dodged": float,             # [E2] 因篩選器避免的虧損（%累積）
                "regret_from_undertrading": float,   # 因過度保守錯過的收益（%累積）
                "net_regret_direction": str,          # "overtrading" / "undertrading" / "balanced"
                "top_missed": str,                    # 最佳錯過機會的 compact 描述（≤80字符）
                "total_tracked": int,                 # 當前追蹤中的機會數
                "total_settled": int,                 # 已結算的機會數
                "hit_rate_if_taken": float,           # 如果全部執行，勝率是多少
            }
        """
        # [E4] 緩存命中
        if self._cached_summary is not None:
            return self._cached_summary
        
        cutoff_ms = int(time.time() * 1000) - window_days * 24 * 3600 * 1000
        
        # 合併活躍和已結算的機會（[E5 建議] 用 itertools.chain 避免拷貝）
        from itertools import chain
        relevant = [o for o in chain(self._opportunities, self._settled)
                    if o.ts_ms >= cutoff_ms]
        
        if not relevant:
            result = {
                "bullets_dodged": 0.0,
                "regret_from_undertrading": 0.0,
                "net_regret_direction": "balanced",
                "top_missed": "no data",
                "total_tracked": len(self._opportunities),
                "total_settled": len(self._settled),
                "hit_rate_if_taken": 0.0,
            }
            self._cached_summary = result
            return result
        
        # 分類：如果做了會賺的 vs 如果做了會虧的
        would_profit = [o for o in relevant
                        if (o.final_pnl if o.closed else o.current_virtual_pnl) > 0]
        would_loss = [o for o in relevant
                      if (o.final_pnl if o.closed else o.current_virtual_pnl) <= 0]
        
        # 遺憾 = 錯過的盈利總額（undertrading 的代價）
        regret_undertrading = sum(
            o.final_pnl if o.closed else o.current_virtual_pnl
            for o in would_profit
        )
        
        # [E2] 躲過的子彈 = 避免的虧損總額
        bullets_dodged = sum(
            abs(o.final_pnl if o.closed else o.current_virtual_pnl)
            for o in would_loss
        )
        
        # [Q3] 歸一化遺憾方向判斷
        # V1 用 1.5x 硬閾值，但止盈 10% vs 止損 5% 的不對稱會讓
        # undertrading 幾乎永遠佔上風。改為各自除以樣本數得到平均值比較。
        avg_regret = (regret_undertrading / len(would_profit)) if would_profit else 0
        avg_dodged = (bullets_dodged / len(would_loss)) if would_loss else 0
        
        # [R1-8] 最少 5 個樣本才判斷方向（原 3 個，平均值標準誤過大）
        if avg_regret > avg_dodged * 1.3 and len(would_profit) >= 5:
            direction = "undertrading"   # 平均錯過收益 > 平均躲過虧損
        elif avg_dodged > avg_regret * 1.3 and len(would_loss) >= 5:
            direction = "overtrading"    # 篩選器做得好
        else:
            direction = "balanced"
        
        # 最佳錯過機會
        best_missed = max(relevant,
                          key=lambda o: o.final_pnl if o.closed else o.current_virtual_pnl)
        best_pnl = best_missed.final_pnl if best_missed.closed else best_missed.current_virtual_pnl
        days_ago = (int(time.time() * 1000) - best_missed.ts_ms) // (24 * 3600 * 1000)
        top_missed = (f"{best_missed.symbol} {best_missed.direction} "
                     f"{days_ago}d ago, would_pnl {best_pnl:+.1f}%")[:80]
        
        # 勝率
        hit_rate = (len(would_profit) / len(relevant)) if relevant else 0.0
        
        result = {
            "bullets_dodged": round(bullets_dodged, 2),
            "regret_from_undertrading": round(regret_undertrading, 2),
            "net_regret_direction": direction,
            "top_missed": top_missed,
            "total_tracked": len(self._opportunities),
            "total_settled": len(self._settled),
            "hit_rate_if_taken": round(hit_rate, 4),
        }
        self._cached_summary = result  # [E4] 緩存
        return result
    
    def get_schema(self) -> dict:
        return {
            "name": "OpportunityTracker",
            "schema_version": 1,
            "description": "追蹤未執行機會的虛擬表現（含摩擦成本扣除）",
            "output_fields": {
                "bullets_dodged": "[E2] 因篩選器避免的虧損（%累積）",
                "regret_from_undertrading": "因過度保守錯過的收益（%累積）",
                "net_regret_direction": "overtrading/undertrading/balanced（[Q3] 歸一化比較）",
                "top_missed": "最佳錯過機會摘要（≤80字符）",
                "hit_rate_if_taken": "如果全部執行的虛擬勝率",
            }
        }
    
    def get_alerts(self) -> list:
        """[E4] 讀緩存摘要，不重新計算。"""
        alerts = []
        summary = self._cached_summary or self.get_regret_summary(window_days=7)
        if summary["regret_from_undertrading"] > 50.0:
            alerts.append({
                "severity": "warning",
                "msg": f"High undertrading regret: {summary['regret_from_undertrading']:.1f}% "
                       f"missed in 7d. Agent may be too conservative."
            })
        return alerts
```

## 3.3 數據流

```
Scout 掃描 650+ 符號 → 篩選出 10 個候選
  ↓
  被篩掉的 640 個中，取 signal_confidence 最高的 top-5
  → OpportunityTracker.record_skipped(skip_source="scout_filter")

Strategist 評估 10 個候選 → 決定 3 個 trade、7 個 hold
  ↓
  7 個 hold 決策
  → OpportunityTracker.record_skipped(skip_source="strategist_hold")

Guardian 審核 3 個 intent → 2 個 APPROVED、1 個 REJECTED
  ↓
  1 個 REJECTED
  → OpportunityTracker.record_skipped(skip_source="guardian_reject")

每分鐘（或每 tick）：
  OpportunityTracker.update_virtual_pnl(current_prices)

每個決策周期開始時：
  regret_data = OpportunityTracker.get_regret_summary(window_days=7)
  → 餵給 CognitiveModulator.update()
  → 壓縮進 ContextDistiller（只在 L1 推理時使用）
```

---

# 第四部分：DreamEngine

## 4.1 設計原則

```
1. 把閒置時間從純成本變成投資
2. 純 L0 計算，不調用任何 LLM
3. 低 CPU 優先級（nice +15），不影響任何交易路徑
4. 輸出是參數建議（數字），不是決策指令
5. Agent 可以完全忽略夢境建議
```

## 4.2 代碼定義

```python
import random
import time
from dataclasses import dataclass

@dataclass
class DreamInsight:
    """單個夢境洞察"""
    strategy_name: str
    param_name: str           # "stoploss_pct" / "takeprofit_pct" / "grid_spacing" / ...
    current_value: float      # 當前使用的參數值
    suggested_value: float    # 模擬建議的最優值
    improvement_pct: float    # 建議值比當前值好多少（期望收益提升百分比）
    confidence: float         # 基於模擬輪數和一致性的置信度（0-1）
    sample_size: int          # 模擬輪數
    ts_ms: int

class DreamEngine:
    """
    閒置時的蒙特卡洛 what-if 模擬引擎。
    
    用最近 7 天的真實 K 線數據，在不同參數組合下跑快速模擬，
    找出當前市場環境下的最優參數配置。
    
    工具分類：只讀（輸出建議，不修改任何策略參數）
    觸發：系統無活躍交易決策時（由 Conductor/GovernanceHub 調度）
    CPU 優先級：nice +15（最低）
    API 成本：$0
    
    設計哲學：閒置時間不是成本，是自我訓練期。
    Agent 醒來時（市場出現機會時）已經提前準備好了更優的參數配置。
    
    V1.1 修正：
      [Q4] MIN_SAMPLES_PER_PARAM 從 3 提到 30（統計最低要求）
      [Q5] 置信度公式改為 binomial test（統計學正確）
      [E5] 加 threading.Lock（後台運行安全）+ 修正 cycles 計數
      [E6] _simulate_single_run 方向改隨機（消除系統性偏差）
      [F1] TODO: Phase 2 復用 EvolutionEngine/BacktestEngine 模擬邏輯
    """
    
    # 可配置常量
    CANDLE_WINDOW_DAYS = 7              # 使用最近 N 天的 K 線
    CYCLES_PER_BATCH = 300              # [Q4] 每批模擬輪數（原 100，提高以支撐 30/param）
    MAX_CYCLES_PER_IDLE = 10000         # 單次閒置期最大模擬輪數
    MIN_CYCLES_FOR_CONFIDENCE = 200     # 最少多少輪模擬才產生建議
    PARAM_GRID_SIZE = 10                # 每個參數的搜索網格大小
    MIN_SAMPLES_PER_PARAM = 30          # [Q4] 每個參數值最少模擬輪數（原 3，無統計意義）
    
    # 可調參數的搜索空間定義
    PARAM_SEARCH_SPACE = {
        "MA_Crossover": {
            "stoploss_pct": (0.5, 5.0),        # 止損距離 0.5% - 5%
            "takeprofit_pct": (1.0, 15.0),      # 止盈距離 1% - 15%
        },
        "BB_Reversion": {
            "stoploss_pct": (0.5, 4.0),
            "takeprofit_pct": (0.5, 8.0),
            "rsi_threshold": (20, 40),           # RSI 入場閾值
        },
        "GridTrading": {
            "grid_spacing_pct": (0.1, 1.0),      # 網格間距
            "grid_levels": (3, 15),               # 網格層數
        },
        # 全局參數（影響所有策略）
        "global": {
            "stoploss_multiplier": (0.8, 2.0),
        },
    }
    
    def __init__(self, seed: int | None = None):  # [R1-10] 可選 seed 支持可重複測試
        # [R1-6] import 移至模組頂層：import threading, import math, import random
        self._lock = threading.Lock()  # [E5] 後台運行線程安全
        self._rng = random.Random(seed)  # [R1-10] 獨立隨機源
        self._insights: dict[str, dict[str, DreamInsight]] = {}
        # {strategy_name: {param_name: DreamInsight}}
        self._total_cycles = 0
        self._actual_sim_count = 0  # [E5] 實際模擬次數（非批次數）
        self._is_running = False
        self._last_run_ts_ms = 0
    
    def run_cycle(self,
                  recent_candles: dict[str, list[dict]],
                  current_params: dict[str, dict],
                  strategy_signals: dict = None) -> dict:
        """
        執行一批蒙特卡洛模擬。
        
        由 Conductor/GovernanceHub 在系統閒置時調用。
        每次調用跑 CYCLES_PER_BATCH 輪模擬。
        可以被多次調用，直到 MAX_CYCLES_PER_IDLE 或系統恢復忙碌。
        
        Parameters:
            recent_candles: {symbol: [{open, high, low, close, volume, ts_ms}, ...]}
                最近 7 天的 K 線數據
            current_params: {strategy_name: {param_name: current_value, ...}}
                當前正在使用的策略參數
            strategy_signals: {strategy_name: signal_function}（可選）
                策略的信號生成函數（用於模擬中判斷入場出場）
        
        Returns:
            {"cycles_completed": int, "new_insights": int}
        """
        # [R1-3] 防重入：兩個線程同時調用時只有一個執行
        with self._lock:
            if self._is_running:
                return {"cycles_completed": 0, "total_cycles": self._total_cycles,
                        "total_simulations": self._actual_sim_count, "new_insights": 0}
            self._is_running = True
            self._last_run_ts_ms = int(time.time() * 1000)
        
        # [R1-4] 注意：run_cycle() 是同步阻塞操作。
        # Conductor async 調度時必須用 asyncio.to_thread(engine.run_cycle, ...) 包裝，
        # 否則會阻塞事件循環。§5.1.5 的調度代碼應相應修改。
        
        new_insights = 0
        batch_sim_count = 0  # [E5] 本批次實際模擬次數
        
        for strategy_name, param_space in self.PARAM_SEARCH_SPACE.items():
            for param_name, (lo, hi) in param_space.items():
                # 生成參數網格
                grid = [lo + (hi - lo) * i / (self.PARAM_GRID_SIZE - 1)
                        for i in range(self.PARAM_GRID_SIZE)]
                
                # 加入當前值（確保和當前值的對比是公平的）
                current_val = current_params.get(strategy_name, {}).get(param_name)
                if current_val is not None and lo <= current_val <= hi:
                    grid.append(current_val)
                
                # [Q4] 對每個參數值跑至少 MIN_SAMPLES_PER_PARAM 輪
                results = {}  # {param_value: [simulated_pnl_list]}
                
                for val in grid:
                    pnls = []
                    for _ in range(self.MIN_SAMPLES_PER_PARAM):
                        pnl = self._simulate_single_run(
                            recent_candles, strategy_name, param_name, val)
                        if pnl is not None:
                            pnls.append(pnl)
                        batch_sim_count += 1
                    if pnls:
                        results[val] = pnls
                
                # 找出最優參數
                if results:
                    best_val, best_insight = self._analyze_results(
                        results, strategy_name, param_name, current_val)
                    if best_insight is not None:
                        with self._lock:  # [E5]
                            self._insights.setdefault(strategy_name, {})[param_name] = best_insight
                        new_insights += 1
        
        with self._lock:  # [E5]
            self._actual_sim_count += batch_sim_count
            self._total_cycles += 1  # [E5] 修正：_total_cycles 計批次數，_actual_sim_count 計模擬數
            self._is_running = False
        
        return {
            "cycles_completed": batch_sim_count,  # [E5] 返回實際模擬次數
            "total_cycles": self._total_cycles,
            "total_simulations": self._actual_sim_count,
            "new_insights": new_insights,
        }
    
    def _simulate_single_run(self,
                              candles: dict[str, list[dict]],
                              strategy_name: str,
                              param_name: str,
                              param_value: float) -> float | None:
        """
        用隨機抽取的 K 線片段跑一次模擬。
        
        核心邏輯（簡化版）：
          1. 從可用符號中隨機選一個
          2. 從最近 7 天的 K 線中隨機選一個起點
          3. 截取 24-72 小時的連續 K 線
          4. 用指定的參數值模擬策略行為
          5. 返回模擬 PnL（百分比）
        
        注意：完整實現需要接入各策略的信號邏輯。
        V1 版本可以用簡化的 threshold 模型近似。
        """
        # 選擇符號和時間片段
        symbols = list(candles.keys())
        if not symbols:
            return None
        
        symbol = self._rng.choice(symbols)
        data = candles[symbol]
        if len(data) < 60:  # 至少 60 根 K 線
            return None
        
        # 隨機起點，截取 24-72 根 K 線
        run_length = self._rng.randint(24, min(72, len(data) - 1))
        start = self._rng.randint(0, len(data) - run_length - 1)
        segment = data[start:start + run_length]
        
        # 簡化模擬：假設策略在第一根 K 線入場
        entry_price = segment[0]["close"]
        
        # 根據 param_name 設定退出條件
        if param_name in ("stoploss_pct", "stoploss_multiplier"):
            sl_pct = param_value
        else:
            sl_pct = 2.0  # 默認
        
        if param_name == "takeprofit_pct":
            tp_pct = param_value
        else:
            tp_pct = 6.0  # 默認
        
        # [E6] 隨機方向（V1 用 K 線顏色判斷，引入系統性偏差）
        # TODO(phase-2): 接入真實策略信號函數替代隨機方向
        direction = self._rng.choice(["long", "short"])  # [R1-10] 用獨立隨機源
        
        # 走過 K 線，檢查止損/止盈
        for candle in segment[1:]:
            if direction == "long":
                pnl_high = (candle["high"] - entry_price) / entry_price * 100
                pnl_low = (candle["low"] - entry_price) / entry_price * 100
            else:
                pnl_high = (entry_price - candle["low"]) / entry_price * 100
                pnl_low = (entry_price - candle["high"]) / entry_price * 100
            
            if pnl_low <= -sl_pct:
                return -sl_pct  # 止損觸發
            if pnl_high >= tp_pct:
                return tp_pct  # 止盈觸發
        
        # 到期未觸發，按最後一根 K 線結算
        final_price = segment[-1]["close"]
        if direction == "long":
            return (final_price - entry_price) / entry_price * 100
        else:
            return (entry_price - final_price) / entry_price * 100
    
    def _analyze_results(self,
                          results: dict[float, list[float]],
                          strategy_name: str,
                          param_name: str,
                          current_value: float | None) -> tuple:
        """
        分析模擬結果，找出最優參數。
        
        [Q4] 最少 MIN_SAMPLES_PER_PARAM 輪才有統計意義（原 3 輪）
        [Q5] 置信度改為 binomial test p-value（原啟發式公式無統計基礎）
        """
        # 每個參數值的期望收益
        expectations = {}
        for val, pnls in results.items():
            if len(pnls) >= self.MIN_SAMPLES_PER_PARAM:  # [Q4] 至少 30 輪
                expectations[val] = sum(pnls) / len(pnls)
        
        if not expectations:
            return None, None
        
        best_val = max(expectations, key=expectations.get)
        best_exp = expectations[best_val]
        
        # 和當前值對比
        current_exp = expectations.get(current_value, 0.0)
        improvement = best_exp - current_exp
        
        # [Q5] 置信度改為 binomial test
        # H0: 該參數值的勝率 ≤ 0.5（即不比隨機好）
        # 如果 p-value < 0.1，則 confidence = 1 - p_value
        best_pnls = results.get(best_val, [])
        n = len(best_pnls)
        wins = sum(1 for p in best_pnls if p > 0)
        
        if n < self.MIN_SAMPLES_PER_PARAM:
            confidence = 0.0
        else:
            # Binomial test: P(X >= wins | n, p=0.5)
            # 使用正態近似（n >= 30 時有效）
            # z = (wins/n - 0.5) / sqrt(0.25/n)
            # [R1-6] math 已在模組頂層 import
            p_hat = wins / n
            z = (p_hat - 0.5) / math.sqrt(0.25 / n)
            # 單尾 p-value 近似（標準正態 CDF 的互補）
            # 使用 erfc 近似: P(Z > z) ≈ 0.5 * erfc(z / sqrt(2))
            p_value = 0.5 * math.erfc(z / math.sqrt(2))
            confidence = max(0.0, min(1.0, 1.0 - p_value))
        
        # 只有在明顯改善且統計顯著時才產生建議
        if improvement < 0.5 or confidence < 0.4:
            return best_val, None
        
        insight = DreamInsight(
            strategy_name=strategy_name,
            param_name=param_name,
            current_value=current_value or 0.0,
            suggested_value=round(best_val, 4),
            improvement_pct=round(improvement, 2),
            confidence=round(confidence, 4),
            sample_size=len(best_pnls),
            ts_ms=int(time.time() * 1000),
        )
        
        return best_val, insight
    
    def get_insights(self) -> dict:
        """
        返回當前所有夢境洞察。
        CognitiveModulator 和 ContextDistiller 使用。
        
        Returns:
            {
                "strategy_name": {
                    "param_name": {
                        "current": float,
                        "suggested": float,
                        "improvement_pct": float,
                        "confidence": float,
                    },
                    ...
                },
                "_meta": {
                    "total_cycles": int,
                    "last_run_ts_ms": int,
                    "is_running": bool,
                }
            }
        """
        result = {}
        for strategy, params in self._insights.items():
            result[strategy] = {}
            for param_name, insight in params.items():
                result[strategy][param_name] = {
                    "current": insight.current_value,
                    "suggested": insight.suggested_value,
                    "improvement_pct": insight.improvement_pct,
                    "confidence": insight.confidence,
                }
        
        result["_meta"] = {
            "total_cycles": self._total_cycles,
            "total_simulations": self._actual_sim_count,  # [E5] 實際模擬次數
            "last_run_ts_ms": self._last_run_ts_ms,
            "is_running": self._is_running,
        }
        return result
    
    def get_schema(self) -> dict:
        return {
            "name": "DreamEngine",
            "schema_version": 1,
            "description": "閒置時蒙特卡洛模擬引擎（L0 純本地計算）",
            "output_fields": {
                "{strategy}.{param}.suggested": "建議的最優參數值",
                "{strategy}.{param}.improvement_pct": "預期改善幅度",
                "{strategy}.{param}.confidence": "建議的置信度",
                "_meta.total_cycles": "累計模擬輪數",
            }
        }
    
    def get_alerts(self) -> list:
        alerts = []
        if self._actual_sim_count > 1000:  # [E5] 用實際模擬數而非批次數
            # 檢查是否有高置信度的重大改善建議
            for strategy, params in self._insights.items():
                for param_name, insight in params.items():
                    if insight.confidence > 0.7 and insight.improvement_pct > 3.0:
                        alerts.append({
                            "severity": "info",
                            "msg": f"Dream suggests {strategy}.{param_name}: "
                                   f"{insight.current_value}→{insight.suggested_value} "
                                   f"(+{insight.improvement_pct}%, conf={insight.confidence})"
                        })
        return alerts
```

## 4.3 閒置調度邏輯

```
由 Conductor / GovernanceHub 控制：

  每個決策周期結束後：
    if 沒有活躍的 Strategist 推理 and
       沒有待處理的 Guardian 審核 and
       沒有待執行的 Executor 訂單:
        
        while 仍然閒置 and dream_cycles < MAX_CYCLES_PER_IDLE:
            DreamEngine.run_cycle(recent_candles, current_params)
            
            # 每批次後檢查是否需要回到工作模式
            if 有新的 Scout 掃描結果 or 有 P1 事件:
                break

  系統啟動時的初始化：
    DreamEngine 讀取最近 7 天 K 線數據到內存
    每天凌晨 4:00（低活躍時段）刷新 K 線數據
```

## 4.4 Rust 遷移標記

```
# TODO(rust-migration): DreamEngine 是 Rust 遷移的最高優先級模組
# 原因：蒙特卡洛吞吐量直接決定夢境洞察質量
# Python: ~3000 輪/秒 → Rust: ~150000 輪/秒（50 倍）
# 同樣的閒置時間，Rust 產生的洞察質量高一個數量級
# 
# Rust 遷移接口（PyO3）：
#   from openclaw_core import DreamEngine
#   engine = DreamEngine()
#   result = engine.run_cycle(candles_json, params_json)
#   insights = engine.get_insights()
# 
# Python 調用接口不變，只是底層實現切換
```

---

# 第五部分：與 V3 報告的整合點

## 5.1 需要修改的現有代碼

### 5.1.1 ContextDistiller（V3 §4.2）— 擴展 `_summary` 結構

> **[P2] PA 架構決策**：ContextDistiller 目前不存在（Phase 2 規劃項）。
> Phase 1 實現時，Strategist 直連 CognitiveModulator.get_all_params() 讀取調製值，
> 並手動嵌入 Ollama prompt context。Phase 2 ContextDistiller 就緒後遷移。

```python
# 在 update_after_each_cycle() 中新增兩個 key：

"pressure": {
    "confidence_floor": 0.63,       # CognitiveModulator 當前值
    "qty_ceiling": 0.85,            # CognitiveModulator 當前值
    "stoploss_mult": 1.15,          # CognitiveModulator 當前值
    "scan_interval_s": 900,         # CognitiveModulator 當前值
    "regret_direction": "undertrading",  # OpportunityTracker 摘要（[Q3] 歸一化判斷）
    "regret_score": 12.5,           # 累積遺憾百分比值（已扣除 [Q2] 摩擦成本）
},
"dream": {
    "cycles": 847,                  # DreamEngine 累計模擬輪數
    "top_suggestion": "MA_Cross.sl:1.5→2.0(+3.2%,c=0.71)",  # compact 格式
    "last_ts": 1712100000,
}

# Token 開銷：+40-50 tokens，總計仍 < 500 tokens
```

### 5.1.2 Strategist 正常通道（V3 §3.3 + 附錄 E.1）— 決策前注入 L0 調製

```python
# === 修改位置：Strategist intent 生成邏輯（V3 附錄 E.1）===

# 在 PositionSizer.compute_recommendation() 之後、intent 創建之前插入：

# [NEW] L0 認知調製：動態提高 confidence 門檻
min_conf = self._cognitive_modulator.get_confidence_floor()
if decision.get("confidence", 0) < min_conf:
    logger.info("CogMod: confidence %.2f < floor %.2f, skipping intent",
                decision["confidence"], min_conf)
    # 記錄為 OpportunityTracker 的 strategist_hold
    self._opportunity_tracker.record_skipped(
        symbol=decision["symbol"],
        direction=decision.get("direction", "unknown"),
        entry_price=current_price,
        signal_confidence=decision.get("confidence", 0),
        skip_reason=f"confidence {decision['confidence']:.2f} < floor {min_conf:.2f}",
        skip_source="strategist_hold",
        strategy_name=decision.get("strategy", "unknown"),
    )
    return None  # 不生成 intent，靜默跳過

# [MODIFIED] qty 計算加入認知調製
raw_fraction = decision.get("qty_fraction", 0.5)
# L0 認知調製：動態收緊上界
modulated_ceiling = self._cognitive_modulator.get_qty_ceiling()  # [NEW]
fraction = max(0.1, min(modulated_ceiling, raw_fraction))        # [MODIFIED]

final_qty = sizing["recommended_qty"] * fraction
final_qty = min(final_qty, sizing["max_allowed_qty"])

# [EXISTING] 系統降級時額外縮減（V3 附錄 D.1）
sys_health = self._health_aggregator.get_status()
if sys_health["should_reduce_activity"]:
    final_qty *= 0.5

# [NEW] 止損距離調製
sl_multiplier = self._cognitive_modulator.get_stoploss_multiplier()
actual_stoploss = base_stoploss_distance * sl_multiplier
```

### 5.1.3 Scout（V3 §3.1）— 輸出保留未執行機會的快照

```python
# === 修改位置：Scout 掃描完成後 ===

# [EXISTING] 篩選後的候選列表
candidates = self._filter_candidates(scan_results)  # 從 650+ 篩到 ~10

# [NEW] 記錄被篩掉的 top-N 高置信度機會
skipped = [r for r in scan_results if r not in candidates]
skipped_top = sorted(skipped, key=lambda r: r.get("signal_confidence", 0),
                     reverse=True)[:5]
for s in skipped_top:
    self._opportunity_tracker.record_skipped(
        symbol=s["symbol"],
        direction=s.get("direction", "unknown"),
        entry_price=s.get("price", 0),
        signal_confidence=s.get("signal_confidence", 0),
        skip_reason=s.get("filter_reason", "unknown")[:80],
        skip_source="scout_filter",
        strategy_name=s.get("strategy", "unknown"),
    )

# [NEW] 掃描間隔使用認知調製的值
next_scan_delay = self._cognitive_modulator.get_scan_interval_seconds()
```

### 5.1.4 Guardian（V3 §3.4）— REJECTED 時記錄到 OpportunityTracker

```python
# === 修改位置：Guardian 裁決為 REJECTED 時 ===

if verdict == "REJECTED":
    # [EXISTING] 審計日誌
    self._log_rejection(intent, reason)
    
    # [NEW] 記錄到 OpportunityTracker
    self._opportunity_tracker.record_skipped(
        symbol=intent.symbol,
        direction=intent.side,
        entry_price=intent.price,
        signal_confidence=intent.confidence,
        skip_reason=reason[:80],
        skip_source="guardian_reject",
        strategy_name=intent.strategy_name,
    )
```

### 5.1.5 Conductor / GovernanceHub — DreamEngine 閒置調度

```python
# === 修改位置：Conductor 主循環 ===

async def _main_loop(self):
    while True:
        # [EXISTING] 正常決策流程
        scan_result = await self._wait_for_scan()
        await self._run_decision_pipeline(scan_result)
        
        # [NEW] 決策完成後，如果系統閒置，啟動 DreamEngine
        # [R1-4] 用 asyncio.to_thread() 包裝同步阻塞的 run_cycle()
        while self._is_idle() and not self._has_pending_events():
            result = await asyncio.to_thread(
                self._dream_engine.run_cycle,
                recent_candles=self._candle_cache,
                current_params=self._get_current_strategy_params(),
            )
            if result["cycles_completed"] == 0:
                break  # 無有效數據，停止
            
            # 每批次後讓出事件循環，檢查是否需要回到工作模式
            await asyncio.sleep(0.1)

    def _is_idle(self) -> bool:
        return (not self._strategist.has_pending_intents() and
                not self._guardian.has_pending_reviews() and
                not self._executor.has_pending_orders())
```

## 5.2 與 V3 報告的模組地圖更新

```
V3 報告 §9 模組地圖中，Agent 工具箱新增：

┌─ Strategist 工具 ───────────────────────────────────────┐
│ PositionSizer [NEW P0]    SignalEngine [已有]             │
│ HedgingEngine [NEW P2]    TSR [已有+修復]                │
│ ContextDistiller [NEW]                                    │
│ CognitiveModulator [NEW P1, §本文件]  ◀── 新增           │
└───────────────────────────────────────────────────────────┘
┌─ Analyst 工具 ────────────────────────────────────────────┐
│ IndicatorEngine [已有+擴展]  EWMAVol [NEW P0]            │
│ HurstCalc [NEW P0]  HealthMonitor [NEW P0]               │
│ PnLAttributor [NEW P2]                                    │
│ OpportunityTracker [NEW P1, §本文件]  ◀── 新增            │
└───────────────────────────────────────────────────────────┘
┌─ 後台引擎 ────────────────────────────────────────────────┐
│ DreamEngine [NEW P1, §本文件]  ◀── 新增                   │
│ BacktestEngine [已有]                                     │
└───────────────────────────────────────────────────────────┘
```

---

# 第六部分：與 Ollama JSON 通信的整合

## 6.1 設計原則：跳過自然語言

```
認知調製的 90% 在 Ollama 被調用之前就生效了（L0 數字調製）。
剩下的 10% 是在 Ollama 的 JSON 輸入中加幾個數字欄位。

LLM 看到的不是：「你最近表現不好請謹慎」
LLM 看到的是：  min_confidence: 0.68, regret_bias: "undertrading"

LLM 甚至不知道自己被調製了——它只是在更嚴格的參數空間裡做決策。
```

## 6.2 Ollama 輸入 JSON 擴展

```json
// V3 報告 §3.3 的現有輸入（不變）
{
  "market": { "btc_price": 84500, "regime": "trending", "hurst": 0.62, "vol_state": "normal" },
  "portfolio": { "balance": 10000, "delta_pct": 15, "positions": 2, "daily_pnl": 12.5 },
  "health": { "MA_Crossover": { "sharpe": 0.8, "wr": 0.42, "cusum": false } },
  "events": [ ... ],
  
  // ===== 新增欄位（來自三個新模組，V1.1 修正後）=====
  
  "cognitive": {
    "confidence_floor": 0.68,       // [Q1] max 單因子 + [Q6] EMA 平滑後的值
    "qty_ceiling": 0.85,
    "sl_mult": 1.15,
    "regret_direction": "undertrading",  // [Q3] 歸一化比較結果
    "bullets_dodged": 8.3,          // [E2] 重命名（原 regret_from_overtrading）
    "regret_score": 12.5            // 已扣除 [Q2] 摩擦成本
  },
  
  "dream": {
    "MA_Crossover": { "stoploss_pct": { "current": 1.5, "suggested": 2.0, "conf": 0.71 } },
    "GridTrading": { "spacing_pct": { "current": 0.5, "suggested": 0.35, "conf": 0.65 } }
  }
}
```

## 6.3 Ollama 輸出 JSON（不需要修改）

```json
// V3 報告 §3.3 定義的輸出格式完全不變
{
  "decision": "trade",
  "symbol": "BTCUSDT",
  "direction": "long",
  "qty_fraction": 0.8,
  "confidence": 0.72,
  "reasoning": "Hurst=0.61 trending + MA_Cross long + dream_sl=2.0 adopted",
  "signals_used": ["MA_Crossover:long:0.65"],
  "signals_ignored": ["BB_Reversion"],
  "ignore_reason": "regime=trending, reversion unfit"
}
```

LLM 可以在 `reasoning` 中提到它參考了夢境建議，但這是 LLM 自主決定的——我們不強制它一定要用。`confidence` 值如果低於 `confidence_floor`，會被 L0 代碼在**外部**攔截，不需要 LLM 自己判斷。

## 6.4 Token 開銷分析

```
新增 JSON 欄位的 token 估算：
  "cognitive" block:  ~30 tokens
  "dream" block:      ~40 tokens（2 個策略的建議）
  ─────────────────────────────
  總增加：           ~70 tokens

V3 報告的 ContextDistiller 目標：~450 tokens
新增後總計：                      ~520 tokens

影響：
  L1 Ollama 推理時間增加 ~0.5 秒（從 9s → 9.5s）
  L1.5/L2 API 費用增加 ~$0.001/次（可忽略）
  
結論：不需要為了節省 token 壓縮這些欄位。
      70 tokens 的信息密度極高（全是數字，沒有自然語言）。
```

---

# 第七部分：開發路線圖

## 7.1 在 V3 報告 Phase 1 中的位置

```
Phase 1 修正後依賴圖：

  1.0 Alpha 基準測試 → [2 週 Paper，並行於所有開發]

  ┌─ 可並行組 A ──────────────┐
  │ 1.1 PositionSizer           │
  │ 1.2 HealthMonitor           │
  │ 1.3 EWMAVol                 │
  │ 1.4 Hurst                   │
  └─────────────────────────────┘
           ↓
  1.5 Indicator Engine（依賴 1.3/1.4 接口）
  
  ┌─ 可並行組 B ──────────────────────┐
  │ 1.6 學習迴路修復                    │
  │ 1.7 Evo→Deploy                     │
  │ 1.8 LocalLLMClient                 │
  │ 1.10 CognitiveModulator ◀── NEW    │  0.5d
  │ 1.11 OpportunityTracker ◀── NEW    │  1.0d
  │ 1.12 DreamEngine        ◀── NEW    │  1.5d
  └─────────────────────────────────────┘
  
  1.9 影子決策追蹤（依賴 1.2 + 1.11）◀── 新增依賴

  關鍵路徑不受影響：組A(2d) → 1.5(1.5d) = 3.5d
  新模組在組B中並行開發，總計 +3d
```

## 7.2 開發任務明細

```
1.10 CognitiveModulator（0.5d）
  □ 實現 CognitiveModulator 類（~100 行）
  □ 實現 get_schema() + get_alerts()
  □ 單元測試：各調製公式的邊界條件
  □ 確認 Strategist 的注入點（§5.1.2）
  
  前置依賴：無
  後續影響：Phase 2.7 Strategist 雙軌 + Phase 2.9 Prompt 模板

1.11 OpportunityTracker（1.0d）
  □ 實現 SkippedOpportunity 數據結構
  □ 實現 OpportunityTracker 類（~200 行）
  □ 實現 get_schema() + get_alerts()
  □ 單元測試：環形緩衝區滿時的行為、虛擬 PnL 計算、遺憾摘要
  □ 接入 Scout（§5.1.3）、Guardian（§5.1.4）的調用點

  前置依賴：無（但 1.9 影子決策追蹤依賴 1.11）
  後續影響：1.10 的 regret_data 輸入

1.12 DreamEngine（2.0d）  # [R1-7] 原 1.5d，因 Q4/Q5/E5 增加測試量調至 2.0d
  □ 實現 DreamInsight 數據結構
  □ 實現 DreamEngine 類（~300 行）
  □ 實現蒙特卡洛模擬核心邏輯
  □ 實現 get_schema() + get_alerts()
  □ 單元測試：模擬結果的統計分布、參數搜索空間覆蓋
  □ 實現閒置調度邏輯（§5.1.5）
  □ [Q5] 實現 binomial test 置信度判定（替代啟發式公式）
  □ [R1-3] 實現防重入互斥 + [R1-4] asyncio.to_thread() 包裝文檔
  □ 加 Rust 遷移 TODO 標記（§4.4）

  前置依賴：K 線數據緩存（已有的 MarketDataDispatcher）
  後續影響：1.10 的 dream_data 輸入
```

## 7.3 Phase 2 中的整合工作

```
Phase 2.7 Strategist 雙軌（V3 報告已有）
  新增任務：
  □ 在正常通道的 intent 生成邏輯中整合 CognitiveModulator（§5.1.2）
  □ 在快速通道中確認 CognitiveModulator 不介入（快速通道不受調製影響）
  估時影響：+0.5d

Phase 2.9 Prompt 模板（V3 報告已有）
  新增任務：
  □ 在 Ollama 輸入 JSON 中加入 cognitive 和 dream 欄位（§6.2）
  □ 確認 token 預算仍在 500 以內
  估時影響：+0.25d

Phase 2 總估時影響：從 ~20d 增加到 ~20.75d（可忽略）
```

---

# 第八部分：風險與限制

## 8.1 認知調製的風險

| 風險 | 描述 | 緩解措施 |
|------|------|----------|
| 參數振盪 | 連虧→提高門檻→錯過機會→遺憾顯示 undertrading→降低門檻→重複 | [Q1] 多因子取 max 抑制叠加 + [Q6] EMA alpha=0.3 阻尼振盪 + 降低幅度(-0.03)<提高幅度(+0.05) |
| 極端鎖死 | 極端市場下所有調製都推到上限，Agent 幾乎停止交易 | [Q1] max 單因子下 floor 最多到 0.70（原 sum 模式可達 0.77）+ MAX_CONFIDENCE_FLOOR = 0.85 硬夾緊 |
| 滯後反應 | 市場已經轉好但認知調製仍在高門檻 | 使用短期窗口（7 天）+ [Q6] EMA 每次向目標移動 30%，約 7 個周期收斂 |

## 8.2 遺憾追蹤的風險

| 風險 | 描述 | 緩解措施 |
|------|------|----------|
| 虛擬 PnL 不等於真實 PnL | 滑點、手續費、流動性問題在虛擬追蹤中被忽略 | [Q2] 虛擬 PnL 扣除 2x ESTIMATED_FEE_PCT（0.15%），防止系統性高估推動激進 |
| 止盈/止損不對稱偏差 | 止盈 10% vs 止損 5% 導致 undertrading 方向永遠佔優 | [Q3] 歸一化比較（avg_regret vs avg_dodged）+ 最少 5 個樣本才判斷方向（[R1-8]） |
| 倖存者偏差反轉 | 只追蹤「沒做的」，忽略「做了但虧了的」 | CognitiveModulator 同時使用 consecutive_losses 和 weekly_net_pnl |
| 數據遞歸 | 遺憾數據影響決策→決策改變→遺憾數據改變→... | [Q6] EMA 平滑 + 調製幅度夾緊上下限，防止正反饋失控 |

## 8.3 夢境循環的風險

| 風險 | 描述 | 緩解措施 |
|------|------|----------|
| 過擬合 | 7 天數據的最優參數可能是噪聲 | [Q4] 每參數值最少 30 輪 + [Q5] binomial test 置信度（非啟發式）+ confidence < 0.4 不產生建議 |
| 簡化模擬失真 | V1 的簡化模擬不含策略完整信號邏輯 | [E6] 方向改隨機消除偏差 + TODO: Phase 2 接入真實策略信號函數 + [F1] 復用 EvolutionEngine |
| CPU 搶佔 | 蒙特卡洛計算在高頻時佔用過多 CPU | nice +15 + [E5] threading.Lock + 每批次後 yield 事件循環 |

---

# 第九部分：驗證標準

## 9.1 CognitiveModulator

```
通過條件：
  □ 連虧 5 筆後 confidence_floor > BASE + 0.04
  □ 連虧 0 筆時 confidence_floor == BASE
  □ 所有參數在夾緊範圍內（任何輸入組合）
  □ update() 執行時間 < 0.1ms
  □ 調製不影響快速通道（快速通道 intent 繞過所有調製）
  □ [Q1] 多因子叠加：連虧7 + 週虧 + overtrading 時 floor ≤ 0.70（非 0.77）
  □ [Q6] EMA 平滑：連續調用 update() 10 次相同輸入，輸出收斂到目標值 ±1%
  □ [R1-5] 連虧 ≥3 + undertrading 信號時，floor 不低於 BASE（負向調整被忽略）
  □ [E1] 4 個 _compute_*() 方法各自可獨立單元測試
```

## 9.2 OpportunityTracker

```
通過條件：
  □ record_skipped() 在 deque 滿時正確淘汰最舊記錄
  □ update_virtual_pnl() 正確處理 long/short 方向
  □ [Q2] 虛擬 PnL = raw_pnl - 2 * ESTIMATED_FEE_PCT（驗證扣費正確）
  □ 虛擬止損/止盈觸發後機會被標記為 closed
  □ [E3] _flush_closed() 後 _opportunities 中無 closed=True 的項
  □ get_regret_summary() 在空數據時返回安全默認值
  □ [Q3] 止盈10%/止損5% 不對稱場景下 net_regret_direction 不永遠偏向 undertrading
  □ [E4] 連續調用 get_alerts() 不重複計算（驗證緩存命中）
  □ [E2] 輸出欄位名為 bullets_dodged（非 regret_from_overtrading）
  □ 7 天外的數據不影響 regret_summary
  □ 內存佔用恆定（長期運行 72 小時後）
```

## 9.3 DreamEngine

```
通過條件：
  □ 對已知 K 線數據的模擬結果具有統計可重複性（固定 seed 下）
  □ run_cycle() 不阻塞交易決策路徑
  □ [Q4] 每個參數值至少 30 輪模擬（驗證 results[val] 長度 ≥ 30）
  □ [Q5] confidence 基於 binomial test（n=30, wins=20 時 conf ≈ 0.95，非啟發式 0.76）
  □ [E5] threading.Lock：兩個線程同時調用 run_cycle() 不產生數據競爭
  □ [E5] _actual_sim_count 準確反映實際模擬次數（非批次數）
  □ [E6] 方向為隨機（long/short 各約 50%，1000 次模擬 χ² 檢驗 p > 0.05）
  □ get_insights() 在無模擬數據時返回空 dict（不是 None 或異常）
  □ is_running 狀態在異常退出後正確重置
  □ CPU 佔用在 nice +15 下不影響 Ollama 推理速度（基準對比）
```

---

# 附錄 A：名詞對照

| 中文 | English | 定義 |
|------|---------|------|
| 認知調製 | Cognitive Modulation | 通過 L0 代碼動態調整 Agent 的決策參數邊界 |
| 遺憾追蹤 | Regret Tracking | 追蹤未執行機會的虛擬表現，提供歸因學習信號 |
| 夢境循環 | Dream Cycle | 閒置時用蒙特卡洛模擬探索最優參數配置 |
| 急迫感 | Urgency Pressure | Agent 因感知到成本/表現壓力而產生的行為變化 |
| 決策門檻 | Decision Threshold | Agent 願意行動的最低信號強度 |
| 參數空間 | Parameter Space | Agent 可用的決策參數範圍（被認知調製動態收緊/放寬） |

# 附錄 B：與 Rust 遷移的關係

```
Phase 3 完成後、Live Trading 前的 Rust 遷移優先級：

Tier 2（強烈建議）：
  DreamEngine → Rust PyO3 模組
    Python: ~3000 輪/秒
    Rust:   ~150000 輪/秒
    收益：夢境洞察質量提升 50 倍

Tier 3（建議）：
  CognitiveModulator → Rust PyO3 模組
    收益：消除 GC 抖動（已經很快，主要是確定性保證）
  
  OpportunityTracker → Rust PyO3 模組
    收益：確定性內存管理，長期運行不膨脹

三個模組打包進同一個 Rust crate：openclaw_core
Python 調用接口不變，只是底層實現切換。
```
