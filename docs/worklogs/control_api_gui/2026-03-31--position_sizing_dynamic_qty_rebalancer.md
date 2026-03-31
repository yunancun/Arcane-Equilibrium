# Position Sizing 重構 + 動態倉位 + 智能資本再分配
# 2026-03-31 工程日誌

---

## 背景 (Background)

Paper Trading 運行 ~13 小時後，數據顯示 9 筆交易中 8 筆虧損，但其中 6 筆毛利為正——
虧損完全由手續費造成。根因：每筆交易名義價值僅 ~$20 USDT（帳戶餘額 100,000 USDT 的 0.02%），
手續費佔比 >0.1%，幾乎不可能盈利。

**三個結構性問題：**
1. `risk_per_trade_pct` 過低（1-2%），再除以 active symbol 數量 → 每筆交易極小
2. qty 在部署時計算一次，之後永不更新（餘額變化不影響交易大小）
3. 無資本再分配機制（槽位滿後新機會無法進場）

---

## 修改內容 (Changes)

### 1. 參數調整
| 參數 | 修改前 | 修改後 | 檔案 |
|------|--------|--------|------|
| `risk_per_trade_pct` | 2.0 | 3.0 | `phase2_strategy_routes.py` / `strategy_auto_deployer.py` |
| `max_symbols` | 10 | 25 | `phase2_strategy_routes.py` / `strategy_auto_deployer.py` |
| `MarketScanner.max_symbols` | 10 | 25 | `phase2_strategy_routes.py` |

### 2. Sizing 公式重構 (`strategy_auto_deployer.py`)

**修改前：**
```python
base_usdt = balance * (risk_pct / 100)  # risk% 直接作為名義金額
allocated = base_usdt * score_mult / active_symbol_count  # 再除以活躍品種數
```

**修改後：**
```python
risk_amount = balance * (risk_pct / 100)    # 3% risk = 最大可接受虧損
base_usdt = risk_amount / 0.05              # ÷ 5% hard stop = 反推名義金額
allocated = base_usdt * score_mult          # 不再除以 active count
allocated = min(allocated, balance * max_qty_pct / 100)  # cap at 15%
```

**效果：**
| 帳戶 | 修改前 | 修改後 |
|------|--------|--------|
| $100,000 | ~$20/trade | ~$10,000-15,000/trade |
| $1,000 | ~$20/trade | ~$100-150/trade |

### 3. 動態 qty 計算 (`pipeline_bridge.py` + `strategy_auto_deployer.py`)

新增 `compute_dynamic_qty(symbol, price)` 方法。
`pipeline_bridge._process_pending_intents()` 在提交每筆訂單前調用此方法，
根據**當前餘額**重新計算倉位大小，不再使用部署時的固定值。

### 4. 智能資本再分配 / Portfolio Rebalancer (`strategy_auto_deployer.py`)

**新增方法：**
- `_get_open_positions()` — 從 paper engine 讀取當前持倉
- `_score_existing_position(symbol, pos)` — 評估持倉保留價值（0-100 分）
  - 考慮因素：未實現盈虧比例、持倉時間（>4h 遞減）、連續虧損次數
- `_find_weakest_position(exclude)` — 找到保留價值最低的持倉
- `_close_position_for_rebalance(symbol)` — 提交反向市價單平倉 + 清理策略

**觸發條件（`on_scan_results` 內）：**
1. 所有 25 個槽位已滿
2. 新機會分數 ≥ 70（高品質機會）
3. 新機會正規化分數顯著優於最弱持倉（差距 > 15 分）

**安全設計：**
- 只有高品質機會（score ≥ 70）才觸發再平衡
- 新機會必須「顯著優於」而非「略優於」最弱持倉
- 平倉失敗時靜默跳過，不影響正常流程
- RiskManager `max_total_exposure_pct=50%` 仍作為總曝險安全閥

---

## 修改檔案清單

| 檔案 | 變更 |
|------|------|
| `program_code/local_model_tools/strategy_auto_deployer.py` | +210 行：sizing 重構 + dynamic qty + rebalancer |
| `program_code/.../app/phase2_strategy_routes.py` | 參數調整 + BTC 預註冊策略 sizing 更新 |
| `program_code/.../app/pipeline_bridge.py` | +9 行：動態 qty 注入點 |

---

## 測試結果

```
2555 passed / 17 failed（全部 pre-existing）/ 23 warnings
策略部署器專項測試：3 passed（notify_fill + position_sizing）
手動驗算：$100k 和 $1k 餘額下 sizing 結果正確
```

---

## 設計決策記錄

1. **不除以 active symbol 數** — RiskManager 的 `max_total_exposure_pct=50%` 已控制總曝險，
   single-trade sizing 不需要人為分散。之前的除法是過度保守的雙重限制。

2. **hard_stop_pct=0.05 寫死** — 與 StopManager 的 `hard_stop_pct=5.0` 對齊。
   如果未來 hard stop 變動，此處應同步。

3. **Rebalancer 閾值保守** — 只對 score ≥ 70 觸發，且要求 15 分差距。
   寧可錯過一些機會，也不頻繁平倉造成手續費損耗。
