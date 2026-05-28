# 2026-04-02 工程日誌：Batch 9A 確定性自適應風控
# Engineering Log: Batch 9A Deterministic Adaptive Risk Controls

> 日期：2026-04-02
> 觸發：Demo 交易診斷（70% 勝率但 net PnL -$3.67）
> 方法：QC 量化審查 → PM/FA/PA 三方規劃 → 4 E1 並行實現 → E2+E4 回歸
> 結果：commit d9b102f · +66 新測試 · 3637→3703 passed · 0 新回歸

---

## 1. 問題診斷

### 1.1 Demo 交易數據分析

Session 自 2026-04-02 啟動，63 筆訂單，20 筆 round-trip 完成：

| 指標 | 值 |
|------|-----|
| 勝率 | 70%（14W / 6L）|
| 平均贏利 | +$0.42 |
| 平均虧損 | -$0.995 |
| Win/Loss ratio | 0.42（贏的只有虧的 42%）|
| Profit factor | 0.98（< 1 = 虧錢）|
| Gross PnL | -$0.09 |
| 手續費 | -$3.58 |
| **Net PnL** | **-$3.67** |

### 1.2 三個根因

1. **贏小虧大**：14 次贏共 $5.88，6 次虧共 $5.97。TAUSDT 一筆 -$4.67 吃掉大部分利潤
2. **手續費吃掉利潤**：11/14 筆贏利交易的 gross profit < 手續費（$0.19）
3. **持倉波動太小就平倉**：多數贏利只有 0.01%~0.09%，trailing stop 來不及啟動（activation=1.0%）

### 1.3 參數分析

關鍵交易參數全部硬編碼，Agent 無權根據市場條件調整：
- `trailing_stop_activation_pct = 1.0%`（hardcoded in risk_manager.py）
- `trailing_stop_distance_pct = 0.8%`（hardcoded）
- `min_confidence = 0.55`（hardcoded in strategy_auto_deployer.py）
- 最小利潤門檻：不存在

---

## 2. QC 量化審查

### 2.1 審查結論：PROCEED WITH REVISIONS

QC（Quantitative Consultant）從量化角度審查了「三層自適應參數架構」提案，核心發現：

- **ATR-based stops 有理論基礎**（Kestner 2003, Kaufman 2013），但倍數需 walk-forward 驗證
- **追蹤止損成本陷阱**：若 `activation - distance < round_trip_cost`，追蹤止損鎖定的利潤 < 手續費
- **「2x 手續費」門檻是 magic number**，應改為 `c_round / win_rate × 1.3`
- **統計適應暫緩**：20 筆數據做參數搜索 → Deflated Sharpe 修正後幾乎肯定是噪音
- **MA Crossover Kelly fraction = -0.014**（數學上建議不交易），唯一有可論證 edge 的是 FundingRateArb

### 2.2 兩步路徑

- **Step 1（立即做）**：確定性適應（ATR 縮放 + 成本門檻 + regime 映射表）
- **Step 2（暫緩）**：統計適應（等數據積累到 200+/regime）

報告：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-04-02--adaptive_params_architecture_review.md`

---

## 3. PM/FA/PA 三方規劃

### 3.1 PM 執行計劃

統一排序 18 項（QC 建議 × FA GAP 交叉），分 4 批次：

| 批次 | 內容 | 工時 | 並行 E1 |
|------|------|------|---------|
| 9A | 確定性風控加固（U-03/04/05/09） | 9h | 4 |
| 9B | 學習閉環接通（U-01/02） | 8h | 2 |
| 9C | 管線連通（U-06/07/08/15） | 6h | 4 |
| 9D | 策略 Edge 驗證（U-10/11/14） | 15h | 3 |

### 3.2 Operator 決策（4 項）

1. 成本門檻可以接受低波動幣種不開倉，但不能造成看盤一天沒有成交
2. 進化參數自動重部署：Paper/Demo 免確認，人工只確認 demo→live
3. H0 Gate：先 shadow 觀察 1 週再切 blocking
4. 策略資本分配：選項 C — Agent 根據 Kelly fraction 全自動分配

### 3.3 FA 關鍵發現

- **Trade Attribution fees_paid 全部硬編碼 0.0** — 學習管線收到的成本數據全假
- 追蹤止損成本陷阱對小幣種是真實 bug（cost ~0.6% 時 locked profit=0.2% < cost）
- Regime 檢測已完整（4 種），但 ATR 倍數缺 per-regime 映射

### 3.4 PA 技術方案

- 新建 `cost_gate.py`（~150 行），pipeline_bridge 注入
- `risk_manager.py` 已 1553 行超 1200 行硬上限，需後續拆分
- 0 breaking change，全部通過 re-export 保持向後兼容

報告：
- PM: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-02--adaptive_params_execution_plan.md`
- FA: `docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-02--adaptive_params_functional_spec.md`
- PA: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-02--adaptive_params_technical_design.md`

---

## 4. Batch 9A 實現（4 E1 完全並行）

### 4.1 U-03：追蹤止損利潤約束（E1-Alpha）

**改動**：`risk_manager.py` +24 行
- `compute_round_trip_cost_pct(volume_24h)` — per-symbol 成本計算
- `_SLIPPAGE_TIERS` 鏡像（避免 cross-module import）
- 追蹤止損 check 處加入約束：locked_profit < cost × 1.5 → 自動提高 activation
- activation 提高後不超過 hard_stop

**測試**：`test_trailing_stop_cost_constraint.py` — 12 個測試

### 4.2 U-04：成本感知入場門檻（E1-Beta）

**新建**：`cost_gate.py`（185 行）
- `compute_round_trip_cost_pct(symbol, volume_24h)` — (taker_fee + slippage) × 2 × 100
- `should_reject_for_cost(symbol, atr_pct, win_rate, daily_trade_count)` — 核心決策
  - Fail-open：ATR 不可用時放行
  - 安全閥：daily_trade_count=0 且 ATR > cost/2 → 放行（防零成交）
  - 核心：ATR% < c_round / max(0.3, win_rate) × 1.3 → 拒絕

**注入**：`pipeline_bridge.py` +207 行
- `_gate_intent()` 中 governance 之後、Guardian 之前注入
- `_maybe_reset_daily_trade_count()` UTC 日期重置
- `intents_cost_rejected` 統計計數器

**測試**：`test_cost_gate.py` — 22 個測試

### 4.3 U-05：Round-trip 記錄增強（E1-Gamma）

**改動**：`pipeline_bridge.py` + `analyst_agent.py`
- `_on_position_open()`：捕獲 entry_fee + param_snapshot（ATR/stops/regime/confidence/cost）
- `_emit_round_trip()`：fees_paid = entry_fee + close_fee（不再硬編碼 0）
- `_check_stops()`：從 fill 記錄提取 close_fee
- `analyst_agent.py`：TradeRecord 新增 fees_paid + param_snapshot + net_pnl，.get() 向後兼容

**測試**：`test_u05_round_trip_fees_params.py` — 16 個測試

### 4.4 U-09：ATR 快/慢雙窗口（E1-Delta）

**改動**：`indicator_engine.py` +71 行
- `ATR_FAST_PERIOD = 5`、`ATR_SLOW_PERIOD = 14` 常量
- `create_default_indicators()` 註冊 ATR(5) + ATR(14)
- `get_conservative_atr(symbol, timeframe)` → max(ATR_fast, ATR_slow)

**Bug 修復**：`pipeline_bridge.py` ATR 止損死代碼
- `_on_position_open()` 中 `get_indicators().get("atr")` 永遠返回 None（key 是 `"ATR(14)"` 不是 `"atr"`）
- ATR 止損一直 fallback 到 5.0% 默認值 — 現在用 `get_conservative_atr()` 正確取值

**測試**：`test_atr_dual_window.py` — 18 個測試

---

## 5. E2 審查 + E4 回歸

### 5.1 E2 發現並修復

- `test_h0_gate.py` 中 `PipelineBridge.__new__()` 構造的測試實例缺少 `_daily_trade_date` / `_daily_trade_count` 屬性（E1-Beta 新增）→ 補入 2 處初始化

### 5.2 E4 回歸結果

| 指標 | 值 |
|------|-----|
| Passed | **3703**（基準 3637 → +66） |
| Failed | 24（全部 pre-existing） |
| Errors | 17（全部 pre-existing） |
| **新引入回歸** | **0** |

---

## 6. 文件清單

### 新建文件
| 文件 | 行數 | 用途 |
|------|------|------|
| `program_code/local_model_tools/cost_gate.py` | 185 | 成本感知入場門檻 |
| `tests/test_trailing_stop_cost_constraint.py` | ~200 | U-03 測試 |
| `tests/test_u05_round_trip_fees_params.py` | ~250 | U-05 測試 |
| `tests/test_atr_dual_window.py` | ~300 | U-09 測試 |
| `tests/test_cost_gate.py` | ~264 | U-04 測試 |

### 修改文件
| 文件 | 改動 |
|------|------|
| `app/risk_manager.py` | +24 行（trailing stop cost constraint） |
| `app/pipeline_bridge.py` | +245 行（cost gate 注入 + round-trip 費用） |
| `app/analyst_agent.py` | +27 行（TradeRecord 新字段） |
| `indicator_engine.py` | +71 行（ATR 雙窗口 + get_conservative_atr） |
| `tests/test_h0_gate.py` | +4 行（__new__ 缺屬性修復） |
| `operator_risk_config.json` | 格式更新 |

### Agent Workspace 報告
| 報告 | 角色 |
|------|------|
| `docs/CCAgentWorkSpace/QC/workspace/reports/2026-04-02--adaptive_params_architecture_review.md` | QC |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-02--adaptive_params_execution_plan.md` | PM |
| `docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-02--adaptive_params_functional_spec.md` | FA |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-02--adaptive_params_technical_design.md` | PA |

---

## 7. 下一步

| 批次 | 內容 | 狀態 |
|------|------|------|
| **9A** | 確定性風控加固 | **✅ 完成** |
| 9B | 學習閉環接通（_apply_pattern_insight + Evolution→Deployer） | ⬜ 下一步 |
| 9C | 管線連通（H0 shadow + Scanner→Deployer + Backtest + L2） | ⬜ |
| 9D | 策略 Edge 驗證（FundingRateArb + 條件單 + Kelly GUI） | ⬜ |
