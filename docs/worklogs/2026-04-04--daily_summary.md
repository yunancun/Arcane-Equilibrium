# 2026-04-04 Daily Summary

## 一、完成項

### P0 緊急修復：V2 策略功能死代碼 + Kelly 倉位計算
- [x] **審計發現**：14.5/16 V2 功能為死代碼（策略消費 enriched metadata 但信號管線從未填充）
- [x] **審計發現**：交易鏈 5 個環節 Rust 有缺口（Kelly sizing / intent processing / order execution / risk / PnL）
- [x] **FA 確認**：全部 6 項死代碼斷言驗證通過
- [x] **signal_generator.py**：`_enrich_signal_metadata()` 注入 ADX/RSI/volume_ratio/donchian/hurst/BB 到信號 metadata
- [x] **strategy_orchestrator.py**：注入 `_hurst_regime` 到信號 metadata
- [x] **strategy_auto_deployer.py**：`_compute_qty()` 接入 Kelly PositionSizer（有數據用 Kelly，無數據回退舊公式）
- [x] **intent_processor.rs**：Gate 2.5 position sizing（P1 cap 2% balance/price，min 0.001）
- [x] **grid_trading.rs**：`new_adaptive()` 自適應初始化 + OU 動態間距
- [x] **grid_trading.py**：`ou_dynamic` 默認 True + 週期性 `update_grid_spacing()`
- [x] **main.rs**：`GridTrading::new_adaptive()` 替換硬編碼範圍

### Rust 引擎交易邏輯修復（昨日遺留）
- [x] `apply_fill()` 同方向累加（加權平均 entry）替代覆蓋
- [x] `intent_processor` 重複持倉攔截（同方向已有倉直接拒絕）
- [x] Watchdog threshold 30s→60s 修正假告警

### 灰度驗證狀態
- 引擎存活，~193k ticks 已處理
- Watchdog 修正後零假告警
- Go/No-Go: 2026-04-10

## 二、關鍵決策

| # | 決策 | 依據 |
|---|------|------|
| 1 | 信號 metadata 在 SignalEngine 層補全（非單個 rule） | PA：SRP + 集中管理，sub-μs 開銷 |
| 2 | Kelly sizing 作為 fallback（非替代） | 無歷史交易數據時回退固定 risk% |
| 3 | Rust Kelly 用 P1 cap（非完整 Kelly） | Rust 側無 win_rate/payoff 數據，用 2% balance 上限 |
| 4 | Grid OU 自適應模式 | 首次價格 ±10% 初始化，OU 20 觀察後自動調整 |

## 三、測試基準線

```
Python: 3839 passed / 0 failed / 0 errors / 1 skipped
Rust:   563 passed / 0 failed（+8 new: Kelly sizing + Grid adaptive）
Total:  4402 tests 全綠
```

## 四、Commits

```
697a09e fix: apply_fill accumulates same-direction + reject duplicate intents
6fa9c4f fix(P0): activate V2 strategy features + Kelly sizing + Grid OU
```

### P0 第二輪：消除剩餘 9 項死代碼

- [x] A1: Donchian data 加入 Python signal metadata
- [x] A2: close price 加入 signal metadata（BB middle band）
- [x] A3: Rust BB_Breakout 使用 `ind.donchian` 確認突破
- [x] A4: Rust BB_Reversion + BB_Breakout 使用 `ind.hurst` 體制過濾
- [x] B1: 新增 `KAMACrossoverRule`（KAMA vs EMA 交叉）
- [x] B2: `htf_direction` 注入 orchestrator（緩存每 symbol/tf 方向）
- [x] B3: `check_trailing_stop()` 在 bb_breakout `on_signal()` 中調用
- [x] B4: CognitiveModulator 實例化並接入 phase2_strategy_routes
- [x] B5: FundingArb `evaluate_funding_opportunity()` 傳入 spot/perp prices

## 五、測試基準線（最終）

```
Python: 3839 passed / 0 failed / 0 errors / 1 skipped
Rust:   563 passed / 0 failed
Total:  4402 tests 全綠
V2 死代碼：0（全部消除）
```

## 六、Commits

```
697a09e fix: apply_fill accumulates same-direction + reject duplicate intents
6fa9c4f fix(P0): activate V2 strategy features + Kelly sizing + Grid OU
ccce81d docs: 2026-04-04 daily summary
2f39690 fix(P0): eliminate all remaining V2 dead code — 9/9 fixes
```

## 七、下一步

1. 重啟服務使全部修復生效
2. 觀察修復後策略表現（V2 全功能 + Kelly + Hurst regime + Donchian）
3. Day 7（04-10）Go/No-Go
