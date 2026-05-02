# P0-DATA-INDICATOR-SWEEP — Final Verdict

**日期：** 2026-05-03
**任務 ID：** P0-DATA-INDICATOR-SWEEP
**Owner：** QC（quant 視角主審）+ E3（adversarial 副審）+ PM（compute_indicators body 驗證）
**Verdict：** ✅ **5/5 PASS（leak-free）**
**阻塞解除：** REF-20 V3 §3 G6 + §7 P2 precondition · P0-EDGE-1/2 邊評決策

---

## 1. 範圍

對 5 個 runtime-registered 策略做 indicator leak-free sweep：

1. `grid_trading/`
2. `ma_crossover/`
3. `bb_breakout/`
4. `bb_reversion/`
5. `funding_arb.rs`

加共用 helpers（`common/`、`grid_helpers.rs`、`confluence.rs`、`maker_rejection.rs`）+ IndicatorEngine（`openclaw_core/src/indicators/`）+ KlineManager（`openclaw_core/src/klines.rs`）+ TickPipeline `compute_indicators` body（`on_tick_helpers.rs:453`）。

---

## 2. 驗證鏈完整證據（最關鍵盲點）

QC 主審指出最大盲點是 `compute_indicators(sym)` body — 該 method 決定餵入 IndicatorEngine 的 close[] 是否含 currently-forming bar。本次補位驗證完整鏈：

```
Strategy::on_tick(ctx)
    └─> ctx.indicators (IndicatorSnapshot, by-value, immutable)
            └─ produced by:
                TickPipeline::compute_indicators(sym)             ← on_tick_helpers.rs:453
                    └─> self.kline_manager.get_ohlcv(sym, "1m", Some(100))
                            └─> KlineManager::get_ohlcv(...)       ← klines.rs:552
                                    └─> aggregator.buffer().ohlcv_arrays(n)   ← klines.rs:562
                                            └─> KlineBuffer::ohlcv_arrays(n)   ← klines.rs:200
                                                    └─> self.bars[start..len]    ← bars 是 closed-only buffer
                            └─> KlineBuffer::append(bar)           ← klines.rs:128
                                    "Append a CLOSED bar"          ← only closed
            └─ NEVER reads:
                KlineManager::get_current_bar(...)                 ← klines.rs:543（grep confirmed: 0 callers in compute_indicators path）
                aggregator.get_current_bar()                       ← klines.rs:375
```

**結論**：`compute_indicators` body 100% 從 closed-bar buffer 拿 OHLCV，**絕不**含 currently-forming bar。所有 4 個 active 策略的 Bollinger / ATR / RSI / EMA / Hurst / ADX / Volume Ratio / KAMA 都基於 closed bars 計算。

---

## 3. Strategy Inventory（runtime-registered）

| # | 策略 | 主檔 | indicator 依賴 | 狀態 |
|---|---|---|---|---|
| 1 | grid_trading | `strategies/grid_trading/` (5 file, 2343 LOC) | `ind.adx` / `ind.atr_14` / `ind.bollinger.bandwidth` | active |
| 2 | ma_crossover | `strategies/ma_crossover/` (5 file, 2345 LOC) | `ind.ema_12/26` / `ind.adx` / `ind.kama` / `ind.rsi_14` / `ind.atr_14` | active |
| 3 | bb_breakout | `strategies/bb_breakout/` (6 file, 3297 LOC) | `ind.bollinger` / `ind.donchian_prior` / `ind.atr_14` / `ind.hurst` / `ind.adx` | active |
| 4 | bb_reversion | `strategies/bb_reversion/` (3 file, 1580 LOC) | `ind.bollinger.percent_b/bandwidth` / `ind.rsi_14` / `ind.hurst` | active |
| 5 | funding_arb | `funding_arb.rs` (988 LOC) | **無 rolling indicator**（純 event-driven `ctx.funding_rate / index_price`） | dormant（V2 棄策略路徑） |

註冊 SSOT：`strategies/registry.rs:55,85,105,173,218`。

---

## 4. Per-Strategy Verdict 矩陣

| Strategy | QC verdict | E3 verdict | PM compute_indicators verify | Final |
|---|---|---|---|---|
| grid_trading | Conditional → PASS | PASS（0 finding） | closed-bar only ✅ | **✅ PASS** |
| ma_crossover | Conditional → PASS | PASS（0 finding） | closed-bar only ✅ | **✅ PASS** |
| bb_breakout | Conditional → PASS（Donchian shift(1) 已修） | PASS（FIX-26-DEADLOCK-1 已修 + 14d 0 fires 主因不在 leak） | closed-bar only ✅ | **✅ PASS** |
| bb_reversion | Conditional → PASS | PASS（0 finding） | closed-bar only ✅ | **✅ PASS** |
| funding_arb | PASS（架構級） | PASS（無 indicator） | N/A（不消費 indicator） | **✅ PASS** |

---

## 5. 三角驗證（QC vs E3 vs PM 補位）

| 領域 | QC 證據 | E3 證據 | PM 補位驗證 |
|---|---|---|---|
| **Donchian leak-free**（F3 RETRACT 是否真修） | `indicators/trend.rs:212 donchian_prior` 用 `&high[..n-1]` shift(1) ✅ | `bb_breakout/mod.rs:417-423` expiry auto-clear 在 `is_none()` guard 前跑 ✅ + tests_p1_11.rs 544 行覆蓋 | — |
| **策略不直接讀 KlineManager** | — | grep `kline_manager / get_ohlcv / ohlcv_arrays / get_current_bar` 在 `strategies/` 目錄 0 hit ✅ | — |
| **IndicatorEngine 餵入 close[] 是否含 current bar**（QC 最大盲點）| 未定位 ⚠️ | 看到 `KlineBuffer.append()` 只接 closed bar 但未定位 `compute_indicators` body | `compute_indicators` body @ `on_tick_helpers.rs:453` → `get_ohlcv` → `buffer().ohlcv_arrays(n)` 只從 closed bars ✅ |
| **state mutation race** | — | 5 策略無 `Arc<Mutex>` 共享 indicator state；單執行緒 ✅ | — |
| **first-detection deadlock**（FIX-26 type） | — | bb_breakout 已修 + 其他 4 策略無此 pattern ✅ | — |
| **Mac/Linux byte-equality** | — | rustflags 空 + 無 fast-math + IEEE-754 → 預期 byte-equal（未實測） | 列為 V3 §6.4 baseline 隨 P2a 一併補 reproducibility test |

---

## 6. 影響評估

### REF-20 V3 阻塞解除

- **§3 G6 「5-strategy indicator leak-free audit before P2 runner」**：✅ PASS
- **§7 P2 Precondition: Indicator Leak-Free Sweep**：✅ PASS（5/5 verdict=pass，無策略需 retract / fix-required）
- **§12 #13 `strategy_indicator_leak_free` healthcheck**：可寫 static SQL probe：

  ```sql
  -- 簡化版：fixture 驗證模式（P2b 開工時補 SQL probe）
  SELECT strategy_name, verdict, audited_at
  FROM replay.indicator_audit
  WHERE verdict != 'pass';
  -- expected: 0 rows
  ```

### P0-EDGE 邊評決策

- **5 策略 7d gross net -6.98 USDT 不是 indicator leak 問題**：
  - QC：「最便宜解釋是策略邏輯/cost/maker fill 三者」
  - E3：「§三 36.6% maker fill 7d、24h slippage -92.47bps，與 PNL-FIX 後 gross 負 edge 結論一致」
- **P0-EDGE-1/2 可使用現有 edge 估計**，不需重算。
- 真因排查方向：
  - maker fill rate live_demo 7d 36.6% < 40% PASS 線（[33] healthcheck WARN）
  - bb_breakout live_demo 14d 0 fires（G2-02 結論待）
  - ma_crossover ATR-SNR 後仍負（G2-01 結論待）
  - grid_trading 唯一 +5.77 但其他 4 策略合計 -11.96

---

## 7. Follow-up（非 P0 阻塞）

### LOW findings（E3）→ 升 P2

| ID | 嚴重 | 位置 | 說明 |
|---|---|---|---|
| **L-01** | 🟡 P2 | `bb_breakout/tests.rs:33` 等 | 測試用 `Box::leak(IndicatorSnapshot)` 跳過 KlineManager streaming → 策略邏輯有 coverage、streaming 整合無 coverage。建議補 1-2 端對端 streaming integration test。**建議綁 REF-20 P2b deliverable**（為每策略補 1 deterministic replay window fixture，符合 V3 §7 fixture 要求）。 |
| **L-02** | 🟡 P2 | `pipeline_ctor.rs:67` | `feature_version: "v1.0".into()` 硬編碼；indicator 代碼改不會自動 bump → MLDE training data 隱性混版本。建議綁 `env!("CARGO_PKG_VERSION")` 或 git-sha-derived。**獨立 P2 task**。 |

### Mac/Linux byte-equality（E3 補審 #4）→ 綁 REF-20 V3 §6.4

- 預期 byte-equal（rustflags 空 + IEEE-754 + 無 fast-math），但未實測。
- 建議在 REF-20 P2a baseline reproducibility test 一併確認；不獨立 task。

---

## 8. 三方 Sign-off

- **QC**（quant 主審）：5/5 verdict pass conditional on `compute_indicators` body 驗證；PM 補位驗證後改 unconditional pass。
- **E3**（adversarial 副審）：5/5 verdict pass，0 CRITICAL / 0 HIGH / 0 MEDIUM / 2 LOW（升 P2）。
- **PM**（compute_indicators body 補位）：證據鏈閉合，5/5 leak-free。

**Final Verdict：✅ 5/5 PASS — 解除 REF-20 V3 §3 G6 + §7 P2 阻塞 / P0-EDGE-1/2 可繼續使用現有 edge 估計。**

---

## 9. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| v1.0 | 2026-05-03 | PM | QC + E3 並行 audit 後 PM 補位驗證 `compute_indicators` body；5/5 PASS verdict 確立；REF-20 G6 + §7 解封 |
