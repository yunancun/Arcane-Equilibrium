# PA 技術方案：自適應參數系統
# PA Technical Design: Adaptive Parameter System

> 架構師：PA (Project Architect)
> 日期：2026-04-02
> 輸入：QC 審查報告 `2026-04-02--adaptive_params_architecture_review.md`
> 狀態：設計完成，待 PM/FA 確認後派發 E1

---

## 0. 設計原則

基於 QC 報告的核心結論，本方案**只實施確定性適應**（ATR 縮放、成本門檻、regime 映射表），**不實施統計適應**（歷史表現反饋），原因：

1. 當前僅 20 筆交易，任何統計學習都不可信（QC §2.3 過擬合風險量化）
2. 確定性適應有充分數學基礎，不依賴歷史數據
3. 統計適應架構預留但不啟用，待 200+ trades/regime 後由 Operator 手動開啟

---

## A. 架構決策

### A1. 新模塊 vs 現有模塊改造

| 決策項 | 結論 | 理由 |
|--------|------|------|
| `agent_param_bounds` 配置 | **擴展 `operator_risk_config.json`**，新增 `adaptive_params` 頂層鍵 | 同一文件統一管理 Operator 硬邊界，避免配置散落；向後兼容（新鍵可選） |
| ATR 縮放邏輯 | **擴展現有 `compute_dynamic_stop_pct()`** + **新增 `compute_adaptive_trailing()`** | `compute_dynamic_stop_pct` 已有 ATR×1.5 + regime 邏輯，直接加入成本約束；trailing 需要新函數因為參數不同 |
| 成本感知入場門檻 | **新增 `cost_gate.py`**（~150 行，獨立模塊） | 成本門檻是一個獨立的 gate 概念，不應塞進 risk_manager（已 1553 行，接近警告線）；在 `_gate_intent()` 中調用 |
| Regime 參數表 | **常量放 `risk_manager.py`** 現有 `REGIME_*_MULTIPLIERS` 旁 | 與現有 regime 常量同源管理 |
| 統計適應預留 | **不新建模塊** | 數據不足，僅在 round-trip 記錄中增加字段，架構預留 |

### A2. 數據流設計

```
┌─────────────────────────────────────────────────────────────────────┐
│ 數據流：ATR → 參數 → 門控                                           │
│                                                                     │
│ [KlineManager] → [IndicatorEngine] → ATR(14) indicator              │
│                                          │                          │
│ [PriceHistoryTracker] → compute_atr_pct(symbol) ──┐                │
│                                                     │                │
│ [RegimeDetectorRule] → orchestrator._current_regime ─┤               │
│                                                      ▼               │
│ [pipeline_bridge._gate_intent()] ──────────────► cost_gate.py       │
│   │                                               check_cost_gate() │
│   │  ATR + regime + slippage                       ↓                │
│   │                                            PASS / REJECT        │
│   │                                                                  │
│   ▼                                                                  │
│ [risk_manager.on_tick_risk_check()]                                  │
│   compute_dynamic_stop_pct()  ← ATR + regime（已有）                 │
│   compute_adaptive_trailing() ← ATR + regime + 成本約束（新增）       │
└─────────────────────────────────────────────────────────────────────┘
```

**ATR 數據來源（兩條路徑，不同用途）：**

1. **`PriceHistoryTracker.compute_atr_pct(symbol)`** — 基於 tick 級數據（5 分鐘窗口）。已被 `risk_manager.on_tick_risk_check()` 使用。用於止損/trailing 的即時調整。
2. **`IndicatorEngine` ATR(14)** — 基於 K 線（14 期）。被 `RegimeDetectorRule` 和策略使用。用於入場成本門檻判斷（因為入場決策需要更穩定的 ATR 估計）。

**Regime 數據來源：**
- `strategy_orchestrator._current_regime` — 由 `RegimeDetectorRule` 信號更新
- 已通過 `signal.metadata["_regime"]` 注入到信號中
- 持倉記錄中 `pos["regime"]` 已存在（`risk_manager` 讀取）
- intent 的 metadata 中可攜帶 `regime` 字段

**Per-symbol 成本數據來源：**
- 手續費：`DEFAULT_TAKER_FEE_RATE = 0.00055`（paper_trading_engine.py，全局常量）
- 滑點：`compute_dynamic_slippage(volume_24h)` → `SLIPPAGE_TIERS`（paper_trading_engine.py）
- 已有 `_slippage_cache[symbol]` 存儲 per-symbol 滑點率
- 成本門檻需要：`c_round_pct = (taker_fee × 2 + slippage × 2)`

### A3. 配置格式設計

**在 `operator_risk_config.json` 中新增 `adaptive_params` 鍵（向後兼容 — 缺失時用代碼默認值）：**

```json
{
  "global_config": { ... },
  "category_configs": { ... },
  "adaptive_params": {
    "enabled": true,
    "cost_gate_enabled": true,
    "cost_gate_safety_margin": 1.3,
    "cost_gate_min_win_rate": 0.3,
    "atr_stop_multiplier": 1.5,
    "atr_trailing_activation_multiplier": 2.5,
    "atr_trailing_distance_multiplier": 1.2,
    "regime_stop_params": {
      "trending":  {"k_sl": 2.0, "k_act": 3.0, "k_trail": 1.5, "max_hold_h": 72},
      "volatile":  {"k_sl": 3.0, "k_act": 4.0, "k_trail": 2.0, "max_hold_h": 24},
      "ranging":   {"k_sl": 1.5, "k_act": 2.0, "k_trail": 1.0, "max_hold_h": 48},
      "squeeze":   {"k_sl": 1.0, "k_act": 1.5, "k_trail": 0.8, "max_hold_h": 12},
      "unknown":   {"k_sl": 1.5, "k_act": 2.5, "k_trail": 1.2, "max_hold_h": 48}
    },
    "statistical_adaptation_enabled": false,
    "statistical_min_trades_per_regime": 200
  },
  "saved_ts_ms": ...
}
```

**設計要點：**
- `adaptive_params` 整塊可選（向後兼容）
- `regime_stop_params` 覆蓋現有 `REGIME_STOP_MULTIPLIERS`（從倍數改為 ATR 倍數）
- `statistical_adaptation_enabled = false`（硬關閉，數據充足後 Operator 手動開啟）
- 所有倍數都有代碼默認值（`adaptive_params` 缺失時回退）

---

## B. 代碼變更清單

### B0. 對 QC 建議項的逐一回應

| QC # | 建議 | PA 決策 | 理由 |
|------|------|---------|------|
| M1 | `trail_activation - trail_distance > c_round_pct` | **採納** | 數學硬約束，防止追蹤止損鎖定利潤 < 成本 |
| M2 | 成本感知公式替代 2x 手續費 | **採納** | 新建 `cost_gate.py` 實現 |
| M3 | 統計適應 200+ trades 硬門檻 | **採納（且預設關閉）** | `statistical_adaptation_enabled=false` |
| M4 | 動態參數值寫入 round-trip | **採納** | 在 `_emit_round_trip` 中追加字段 |
| S1 | ATR max(fast, slow) | **延後** | 需要額外指標計算基礎設施（fast ATR 窗口），非核心改動 |
| S2 | 參數空間加 step 字段 | **延後** | 統計適應關閉時不需要 |
| S3 | 精算 FundingRateArb | **記錄為 TODO** | 獨立任務，非本批次 scope |
| S4 | Kelly fraction GUI 展示 | **延後** | 需要 50+ trades 數據，非本批次 |
| N1-N3 | Walk-forward / DSR / Jump detection | **延後** | 中長期項目 |

### B1. 新建文件

#### `cost_gate.py`（~150 行）

位置：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/cost_gate.py`

```
職責：
  - check_cost_gate(symbol, atr_pct, slippage_rate, taker_fee, win_rate_est, safety_margin) → (allowed, reason)
  - 計算 c_round_pct = (taker_fee × 2 + slippage × 2)
  - 計算 min_move_pct = c_round_pct / max(0.3, win_rate_est) × safety_margin
  - 若 atr_pct < min_move_pct → (False, "insufficient_volatility_vs_cost")
  - 純函數，無副作用，無外部依賴

接口：
  def check_cost_gate(
      atr_pct: float,
      slippage_rate: float = 0.0005,
      taker_fee_rate: float = 0.00055,
      estimated_win_rate: float = 0.5,
      safety_margin: float = 1.3,
  ) -> tuple[bool, str]:
      ...

  def compute_round_trip_cost_pct(
      slippage_rate: float = 0.0005,
      taker_fee_rate: float = 0.00055,
  ) -> float:
      ...

依賴方向：零依賴（純函數），被 pipeline_bridge 調用
§14 合規：~150 行，遠低於 800 行警告線
```

### B2. 修改文件清單

#### (1) `risk_manager.py`（1553 行 → ~1620 行）

改動範圍：~70 行新增

```
新增：
  - compute_adaptive_trailing() 函數（~40 行）：
    ATR-based trailing activation + distance，含 M1 成本約束
    activation = max(c_round_pct × 2.5, k_act × atr_pct)
    distance = max(c_round_pct, min(k_trail × atr_pct, hard_stop × 0.8))
    約束：activation - distance > c_round_pct

  - REGIME_ATR_PARAMS dict（~15 行）：
    regime → {k_sl, k_act, k_trail, max_hold_h} 映射
    從 operator_risk_config.json 的 adaptive_params.regime_stop_params 載入
    代碼默認值作為 fallback

修改：
  - compute_dynamic_stop_pct()：
    改用 REGIME_ATR_PARAMS[regime]["k_sl"] 替代固定 1.5
    （向後兼容：若 REGIME_ATR_PARAMS 未載入則用原邏輯）

  - on_tick_risk_check() trailing stop 段落（~1160-1195 行）：
    改用 compute_adaptive_trailing() 計算 activation + distance
    現有 1.0/0.8 硬編碼改為自適應值

  - _load_operator_config()：
    解析 adaptive_params 新鍵（可選，缺失時跳過）

Breaking change：無。compute_dynamic_stop_pct 簽名不變，內部邏輯平滑升級。
§14 合規：1553 + 70 = ~1620 行，超過 1200 硬上限。
  ⚠️ 需要將 PriceHistoryTracker（125-272 行，~148 行）拆到獨立文件。
  拆分後：risk_manager.py ~1472 行，仍超 1200。
  進一步拆分 compute_dynamic_stop_pct + compute_adaptive_trailing 到 stop_computation.py（~120 行）。
  → risk_manager.py ~1350 行，仍超 1200。
  ★ 結論：risk_manager.py 已超 1200 硬上限，本次改動前需先拆分。
  PA 建議：先執行 risk_manager.py 拆分任務（E1-0），再做功能改動。
```

**risk_manager.py 拆分方案：**

| 拆出模塊 | 內容 | 行數 |
|---------|------|------|
| `price_tracker.py` | PriceHistoryTracker class + ATR/spike 常量 | ~170 行 |
| `stop_computation.py` | compute_dynamic_stop_pct + compute_adaptive_trailing + REGIME_* 常量 | ~130 行 |
| `risk_manager.py`（殘留） | GlobalRiskConfig + CategoryRiskConfig + AgentRiskParams + RiskManager class | ~1250 行 |

拆分後 risk_manager.py 剛好在 1200 附近。新增 ~70 行功能代碼後約 1320 行 — 仍然超限。

**修正方案：** 額外拆出 `risk_configs.py`（GlobalRiskConfig + CategoryRiskConfig + AgentRiskParams + resolve_effective_limit，~210 行），risk_manager.py 降到 ~1110 行，加 70 行新增 = ~1180 行，低於 1200。

最終拆分：

| 新模塊 | 內容 | 行數 |
|---------|------|------|
| `price_tracker.py` | PriceHistoryTracker + ATR/spike 常量 | ~170 行 |
| `stop_computation.py` | compute_dynamic_stop_pct + compute_adaptive_trailing + REGIME_* 常量 + anti-cluster | ~150 行 |
| `risk_configs.py` | GlobalRiskConfig + CategoryRiskConfig + AgentRiskParams + resolve_effective_limit | ~220 行 |
| `risk_manager.py`（殘留） | RiskManager class + AI tax + cost_efficiency_grade | ~1080 行（含新增） |

#### (2) `pipeline_bridge.py`（2305 行）

改動範圍：~25 行新增

```
修改：
  - _gate_intent()：在 Guardian 判決之前（edge filter 附近），加入 cost_gate 調用
    from .cost_gate import check_cost_gate
    atr_pct = self._risk_manager._price_tracker.compute_atr_pct(intent.symbol) if self._risk_manager else None
    if atr_pct is not None:
        slippage = self._paper_engine._get_slippage(intent.symbol) if self._paper_engine else 0.0005
        allowed, reason = check_cost_gate(atr_pct=atr_pct, slippage_rate=slippage)
        if not allowed:
            _bump(_local_stats, "intents_cost_rejected")
            self._mark_intent(intent, f"rejected_cost_gate:{reason}")
            return None

  ★ 注意：cost_gate 應放在 H0 Gate 和 Governance 之後、Guardian 之前。
    位置理由：H0/Governance 是系統級門控（必須先過），cost gate 是策略級門控（在 qty 計算之後）。
    但 cost gate 應在 Guardian 之前，因為發送不值得交易的 intent 到 Guardian 浪費 AI 資源。

Breaking change：無。新增一個可選 gate，不改變現有接口。
§14 合規：2305 + 25 = 2330 行，已嚴重超限，但這是 pre-existing 問題，非本次引入。
```

#### (3) `paper_trading_engine.py`（2243 行）

改動範圍：~5 行修改

```
修改：
  - _get_slippage() 改為 public 方法 get_slippage()（或保留 private 但提供 public wrapper）
    理由：pipeline_bridge 需要讀取 per-symbol slippage 給 cost_gate
    最小改動：在 class 中加 get_slippage = _get_slippage（別名）

Breaking change：無（新增公開別名，不改私有方法）。
```

#### (4) `operator_risk_config.json`

改動範圍：新增 `adaptive_params` 鍵

```
向後兼容：是。缺失 adaptive_params 時用代碼默認值。
現有的 global_config / category_configs 不變。
```

#### (5) `_emit_round_trip` 相關（pipeline_bridge.py 內）

改動範圍：~10 行

```
修改：
  - 在 round-trip 記錄中追加字段（M4）：
    "adaptive_params": {
      "atr_pct": ...,
      "regime": ...,
      "dynamic_sl_pct": ...,
      "trail_activation_pct": ...,
      "trail_distance_pct": ...,
      "cost_gate_passed": True/False,
      "c_round_pct": ...
    }
```

### B3. 不改的文件

| 文件 | 理由 |
|------|------|
| `stop_manager.py`（319 行） | 策略級止損管理器，與 risk_manager 的風控止損是獨立層。本次改動在 risk_manager 層面。 |
| `strategy_auto_deployer.py`（932 行） | 部署邏輯不受參數自適應影響。`hard_stop_pct = 0.05` 是 sizing 計算用的，與 ATR 止損不同層面。 |
| `strategy_orchestrator.py` | Regime 數據已在此處正確產生和分發，不需要改動。 |
| `signal_generator.py` | RegimeDetectorRule 已正確實現，不需要改動。 |

---

## C. 副作用分析

### C1. 改 trailing stop 邏輯影響

**下游影響鏈：**
```
risk_manager.on_tick_risk_check()
  → trailing stop 觸發 → close_orders 列表
    → paper_trading_engine 執行平倉
      → pipeline_bridge._check_stops() → Demo 同步
        → _emit_round_trip() → 學習管線
```

**風險點：**
- ATR-adaptive trailing 可能比固定 1.0%/0.8% 更寬或更窄
- 更寬：高波動幣種（如 SIREN ATR=5.7%）trailing 可能延遲觸發 → 持倉時間更長 → 利潤/虧損放大
- 更窄：低波動幣種（如 BTC ATR=0.16%）trailing 更緊 → 更快鎖利 → 也可能更頻繁被噪音踢出

**緩解：**
- Operator 硬邊界不變（max_stop_loss_pct=20%）
- 硬止損永遠第一位（risk_manager 第 1098 行 `pnl_pct <= -hard_sl`），不受 adaptive 影響
- M1 約束保證 `trail_activation - trail_distance > c_round_pct`，確保鎖定利潤 > 成本

### C2. pipeline_bridge 加成本門檻是否阻塞正常交易

**風險：** 若 ATR 數據不可用（冷啟動），cost_gate 會怎樣？

**設計：** `atr_pct is None` 時 **跳過 cost gate**（fail-open）。
- 原因：ATR 不可用說明 PriceHistoryTracker 還沒有足夠 tick 數據
- 冷啟動有 `bootstrap_from_klines()` 注入歷史 K 線，通常幾分鐘後即可用
- 但即使不可用，也不應阻塞交易（原則 6：不確定時保守，但「不交易」不一定是保守的 — 可能錯過止損機會）
- 統計量：`intents_cost_rejected` 計數器，Operator 可觀察

**結論：不會阻塞。** 設計為 fail-open（ATR 不可用時放行）+ 計數器可觀察。

### C3. operator_risk_config.json 向後兼容

**完全向後兼容。** `adaptive_params` 是新的頂層鍵：
- 缺失時：所有代碼使用默認值（與當前行為一致）
- 存在但部分字段缺失：每個字段都有獨立默認值
- `_load_operator_config()` 已有 `config_data.get(key, default)` 模式

### C4. 現有測試影響

**預期影響：**

| 測試區域 | 影響 | 原因 |
|---------|------|------|
| `test_risk_manager.py` | **中等** | import 路徑會變（拆分模塊後），但 re-export 可緩解 |
| `test_pipeline_bridge*.py` | **微小** | 新增 cost_gate 不影響現有 gate 測試（新 gate 在無 risk_manager 時跳過） |
| `test_paper_trading_engine*.py` | **無** | 不改 paper engine 核心邏輯 |
| `test_session9_fixes.py` | **中等** | 直接測試 REGIME_STOP_MULTIPLIERS 和 compute_dynamic_stop_pct，拆分後需更新 import |

**緩解策略：**
- `risk_manager.py` 保留 re-export：`from .price_tracker import PriceHistoryTracker`
- `from .stop_computation import compute_dynamic_stop_pct`
- `from .risk_configs import GlobalRiskConfig, CategoryRiskConfig, AgentRiskParams`
- 這樣現有 `from ... import risk_manager` 或 `from ...risk_manager import XXX` 不受影響

---

## D. 任務派發設計

### D1. 任務列表

| 任務 ID | 描述 | 前置依賴 | E1 實例 | 預估時間 |
|---------|------|---------|---------|---------|
| E1-0 | risk_manager.py 拆分（price_tracker + stop_computation + risk_configs） | 無 | E1-Alpha | 1.5h |
| E1-1 | cost_gate.py 新建 | 無 | E1-Beta | 0.5h |
| E1-2 | compute_adaptive_trailing() + REGIME_ATR_PARAMS（在 stop_computation.py 中） | E1-0 | E1-Alpha | 1h |
| E1-3 | risk_manager trailing stop 段落改用 adaptive trailing | E1-0, E1-2 | E1-Alpha | 1h |
| E1-4 | pipeline_bridge _gate_intent 注入 cost_gate | E1-1 | E1-Beta | 0.5h |
| E1-5 | operator_risk_config.json 擴展 + _load_operator_config 解析 | E1-0 | E1-Gamma | 0.5h |
| E1-6 | _emit_round_trip 追加 adaptive_params 字段（M4） | E1-2, E1-3 | E1-Gamma | 0.5h |
| E1-7 | paper_trading_engine get_slippage public alias | 無 | E1-Gamma | 0.1h |
| E4-1 | 全部新代碼的測試 + 回歸 | E1-0~7 全部 | E4 | 2h |

### D2. 並行度分析

```
批次 1（最大並行 = 3）：
  E1-Alpha: risk_manager.py 拆分（E1-0）
  E1-Beta:  cost_gate.py 新建（E1-1）
  E1-Gamma: paper_trading_engine alias + operator_config（E1-5, E1-7）

批次 2（最大並行 = 2，依賴批次 1）：
  E1-Alpha: compute_adaptive_trailing + trailing 改造（E1-2, E1-3）
  E1-Beta:  pipeline_bridge cost_gate 注入（E1-4）
  E1-Gamma: round-trip 字段追加（E1-6）

批次 3（串行）：
  E4: 測試 + 回歸
  E2: 代碼審查
```

### D3. 每個任務的輸入/輸出

**E1-0（risk_manager 拆分）：**
- 輸入：現有 risk_manager.py（1553 行）
- 輸出：4 個文件（price_tracker.py / stop_computation.py / risk_configs.py / risk_manager.py），re-export 保持向後兼容
- 驗收：所有現有 import risk_manager 的測試不報錯，`pytest` 回歸通過

**E1-1（cost_gate.py）：**
- 輸入：QC §1.4 成本感知公式
- 輸出：cost_gate.py（~150 行）+ test_cost_gate.py（~80 行）
- 驗收：純函數測試，覆蓋邊界（ATR=0, slippage=0, win_rate 極端值）

**E1-2（adaptive trailing）：**
- 輸入：QC §5.1.A 偽代碼 + REGIME_ATR_PARAMS 映射表
- 輸出：stop_computation.py 中新增 compute_adaptive_trailing()
- 驗收：M1 約束 `activation - distance > c_round_pct` 在所有 regime 下成立

**E1-3（trailing stop 改造）：**
- 輸入：risk_manager.py 第 1160-1195 行現有 trailing 邏輯
- 輸出：改用 compute_adaptive_trailing() 的值
- 驗收：回歸測試 + 新測試（ATR 高/低/None 三種情況）

**E1-4（pipeline_bridge cost_gate）：**
- 輸入：cost_gate.py 的 check_cost_gate 接口
- 輸出：_gate_intent() 新增 cost gate 步驟
- 驗收：intents_cost_rejected 計數器正確遞增；ATR=None 時 fail-open

**E1-5（config 擴展）：**
- 輸入：A3 節的 JSON schema
- 輸出：operator_risk_config.json 新增 adaptive_params + 解析代碼
- 驗收：缺失 adaptive_params 時回退默認值；部分字段缺失時回退

**E1-6（round-trip 字段）：**
- 輸入：M4 字段列表
- 輸出：_emit_round_trip / _on_round_trip_complete 追加 adaptive_params dict
- 驗收：round-trip 記錄中包含新字段

**E1-7（slippage alias）：**
- 輸入：paper_trading_engine._get_slippage
- 輸出：public get_slippage(symbol) 方法
- 驗收：pipeline_bridge 可調用

### D4. 最大並行度

**批次 1：3 個 E1 並行**（E1-Alpha, E1-Beta, E1-Gamma）
**批次 2：3 個 E1 並行**（依賴批次 1 各自的輸出）
**批次 3：1 個 E4 + 1 個 E2**（串行後並行質量檢查）

**總預估工時：** ~8 小時（含測試和審查）

---

## E. 風險登記簿

| 風險 | 概率 | 影響 | 緩解 |
|------|------|------|------|
| risk_manager 拆分導致大量測試 import 失敗 | 中 | 中 | re-export 策略 + 提前跑全部測試 |
| ATR-adaptive trailing 對現有 Paper 持倉的影響 | 低 | 低 | 已有持倉的 trailing state 保持不變，新邏輯只影響新計算 |
| cost_gate 過度拒絕低波動幣種 | 中 | 中 | safety_margin 可配置 + 計數器監控 + Operator 可關閉 |
| Operator 不知道參數在自動調整 | 低 | 中 | M4 round-trip 記錄 + GUI 後續可展示（本批次不含） |

---

## F. 不在本批次範圍的項目（記錄為 TODO）

1. **S1 ATR max(fast, slow) 雙窗口** — 需要 PriceHistoryTracker 支持多窗口
2. **S3 FundingRateArb 精算** — 獨立任務，需 FA 規格
3. **S4 Kelly fraction GUI** — 需要 50+ trades 數據
4. **N1 Walk-forward harness** — BacktestEngine 增強
5. **N2 Deflated Sharpe Ratio** — EvolutionEngine 增強
6. **N3 Jump detection** — PriceHistoryTracker 增強
7. **統計適應啟用** — 待 200+ trades/regime

---

> PA (Project Architect)
> 2026-04-02
