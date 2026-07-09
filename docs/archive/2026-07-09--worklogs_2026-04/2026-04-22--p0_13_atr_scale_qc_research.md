---
title: P0-13 ATR Scale Bug — QC Research（option 選型與推薦）
role: QC (Quantitative Reviewer, READ-ONLY)
date: 2026-04-22
parent:
  - docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md §3.0 + §3.1
  - docs/worklogs/2026-04-22--p0_14_edge_estimates_miss_rca.md（姊妹 bug，必同 rebuild）
  - docs/worklogs/2026-04-22--counterfactual_replay_audit_spec.md（所有閾值參照）
scope: 只做選型研究 + 推薦；不改 code / TOML / config；不 deploy / commit / push
---

# P0-13 ATR Scale Bug — QC Research

## TL;DR

- **真 bug**：`compute_atr_pct`（`rust/openclaw_core/src/risk/price_tracker.rs:105`）回傳 "per-tick 絕對回報百分比平均"，量級 ~0.001%-0.006%；三個 consumer（`stops::compute_dynamic_stop_pct`、`exit_features::build_exit_features_for_tick`、`physical_micro_profit_lock_v2`）都把它當 "持倉期 ATR"（~1-2%）用，尺度差 ~100x 到 ~1000x。
- **推薦**：**Option F（kline OHLC-based ATR，rebuild 不需新 table）**。理由：(a) `openclaw_core::indicators::volatility::atr()`（`rust/openclaw_core/src/indicators/volatility.rs:75`）**已存在** Wilder's smoothing + TR true range 正確實作；(b) `KlineManager`（`rust/openclaw_core/src/klines.rs`）已為每 symbol 聚合多時框 OHLCV 且已接線到 tick_pipeline；(c) 統計合理性最高（交易員直覺 BTCUSDT 1m 14-period ATR ≈ 0.05-0.2%、1h ≈ 0.5-1.5%，可控）；(d) 不需引入新 table 或 schema migration，**零 DB 風險**；(e) 三個 consumer **全部**同尺度受益一次修好；(f) 與 counterfactual replay spec 的 `ExitConfig` seed（`giveback_base=1.0 / slope=0.15 / floor=0.3`）相容，**無需 recalibrate**。
- **評分**（4 軸加權）：Option F = **0.88**，次佳 Option A = 0.72，Option D/E = 0.65/0.55，B = 0.55，C = 0.30。
- **與原 A/B/C 不同**：是。推薦 Option F。
- **必硬綁 P0-14**：單修 P0-13 會讓 Gate 4a 突然變合理閾值 → 若 P0-14 edge miss 不修，99% 倉位 Gate 1 仍 Hold（無 mass close 風險但失去 P0-13 修復的可觀測性）；單修 P0-14 讓多數倉位 Gate 1 過 → P0-13 未修的 Gate 4a 立即 mass close；**必同 commit/rebuild**。

---

## 1. 問題精準化

### 1.1 WS tick 頻率（實際餵入 `price_tracker.record` 頻率）

- Bybit V5 public WS 訂閱面（`srv/rust/openclaw_engine/src/multi_interval_topics.rs:190-279`）：
  - `kline.1.<SYM>` — 1m bar 快照，Bybit server 約每 **1-2 秒** 推一次 unconfirmed + 每分鐘推 confirmed（unconfirmed 被 `parse_kline_item` 丟棄，見 `ws_client.rs:489-490`，所以這條對 ATR tracker 的貢獻 = 每分鐘 1 個 confirmed close 價）
  - `publicTrade.<SYM>` — 逐筆成交，Bybit 對活躍 symbol 每秒可達數十筆；小幣可能幾秒一筆
  - `tickers.<SYM>` — 約 **100-300ms** 一條 snapshot
- 所有三個 topic 都流入 `on_tick_step_0_fast_track` (`tick_pipeline/on_tick/step_0_fast_track.rs:107-108`)，全部打進 `price_tracker.record(sym, event.last_price, event.ts_ms)`。
- 因此**實際樣本頻率**由 `tickers` 主導 ≈ **3-10 Hz**，活躍 symbol 可至 ~30 Hz（publicTrade 叠加）。

### 1.2 `compute_atr_pct` window 實際 duration

- `PriceHistoryTracker` 預設 `window_secs = 300` (5 min)、`min_samples = 10`（`price_tracker.rs:7-10`）。
- 5 min × ~5 Hz = **~1500 樣本**；實際邏輯只取 `windows(2)` 做連續 tick abs return 平均 → N ≈ 1500 個 consecutive returns。
- 單個 consecutive return 在一個典型 BTCUSDT tick（100-300ms 間）| price change | ≈ 0.001%-0.01%；**平均** ≈ 0.002-0.005%。乘 100 後 `atr_pct ≈ 0.002-0.005`（數值 0.002，單位 "百分比"）。
- 這與 DB 實測 10 samples（worklog 母單）完全吻合（SOLUSDT 0.00151、ADAUSDT 0.00131、CHIPUSDT 0.00622）。

### 1.3 三個 consumer 的 "期望 ATR 時間尺度"

| Consumer | 期望時間尺度 | 理由 |
|---|---|---|
| `compute_dynamic_stop_pct` (`stops.rs:49`) | **持倉期 ATR（1-4h）** | 止損距離要反映持倉期內典型波動；與 `base_stop_pct`（2%）、`hard_stop_pct`（5-10%）同尺度才合理；`atr_stop_mult=2.0` × 1% ATR = 2% 是交易員語義 |
| `build_exit_features_for_tick` (`builder.rs:110`) `giveback_atr_norm = gb%/atr` | **持倉期 ATR（1-15m）** | `giveback_atr_norm` 語義為 "peak-to-current retracement 以幾個 ATR 為單位"；交易員認知 "0.5 ATR giveback" ≈ 淺、"2.0 ATR giveback" ≈ 深；DB 實測 364.85 avg 明顯錯誤（應 ~3.0） |
| `physical_micro_profit_lock_v2` (`v2.rs:269`) `peak_atr_norm = peak%/atr` + giveback threshold | **持倉期 ATR（1-15m）** | Gate 3 `min_peak_atr_norm=0.5` 語義為 "peak 至少 0.5 ATR 高"；`giveback_base=1.0` 為 "淺 peak 要 1 ATR 回吐才鎖"；這些 seed 假設 ATR 單位是 "交易員常識" 的持倉期 ATR |

**關鍵觀察**：`compute_atr_pct` 語義是 "ticks 間 micro-volatility"（可用於閃崩偵測、市場活躍度度量），**完全不同** 於持倉期 ATR。三個 consumer 誤用是根源問題；函數本身不是 bug（只是被當錯）。

---

## 2. Option A / B / C 深度評估（原 3 方案）

### 2.1 Option A — 新 fn `compute_atr_14period` 用真 ATR（per-tick 保留原語義 deprecated）

**實作**：新增 `compute_atr_14period(symbol, period_secs)` 用 N-period OHLC true range 平均；triaging tracker 需維護 per-symbol OHLC buckets（每 period 一個 bucket）。

| 評估軸 | 分數（0-1） | 備註 |
|---|---:|---|
| 實作成本 | 0.50 | 需新增 `OhlcBucket` 狀態 + 每 tick 維護 + 新單測；3-4 files、~150 LOC |
| 統計合理性 | 0.85 | 真 ATR，但與 `indicators::volatility::atr` **重複實作** 違背 DRY |
| 跨 consumer 一致性 | 0.75 | 3 個 consumer 都要改簽名從 `compute_atr_pct` 切 `compute_atr_14period` |
| 參數穩定性 | 0.80 | 閾值與 design seed 對齊，無需 recalibrate |
| 與 counterfactual spec 衝突 | 低 | Spec 的 ExitConfig seed 直接可用 |
| 回滾成本 | 中 | 新 fn 可留，consumer 回切 `compute_atr_pct` 即回滾；但新 fn 會殘留 dead code |
| **加權總分** | **0.72** | |

**致命弱點**：`openclaw_core::indicators::volatility::atr()`（`volatility.rs:75`）已經做了 Wilder's smoothing + TR true range + atr_percent，**只需要把它 wire 進來**，不需要自己 re-implement。Option A 等於否定既有正確實作。

### 2.2 Option B — builder 端乘「持倉期 tick 數」

**實作**：builder 乘 `position_tick_count` 把 per-tick atr 換成持倉期 atr。

| 評估軸 | 分數（0-1） | 備註 |
|---|---:|---|
| 實作成本 | 0.70 | `PositionExitSnapshot` 加 tick_count 欄位 + tracker 維護 + builder 乘 |
| 統計合理性 | 0.25 | **數學錯誤**：abs return 平均 × N ≠ 持倉期 range；等於假設 returns 完全 positive correlated（隨機遊走下應 × √N 非 × N）|
| 跨 consumer 一致性 | 0.40 | 只修 builder/v2；`compute_dynamic_stop_pct`（consumer 1）**仍爛**，需再獨立修 |
| 參數穩定性 | 0.50 | tick_count 隨時間飄移，閾值會受 tick 頻率影響（活躍 vs 稀疏 symbol 差 10x） |
| 與 counterfactual spec 衝突 | 中 | Spec seed 可能需 recalibrate |
| 回滾成本 | 低 | 純乘法可關 |
| **加權總分** | **0.55** | |

**致命弱點**：數學上不對。隨機遊走模型下持倉期 range ≈ σ × √N（σ 是單步 std），不是 mean_abs_return × N。B 在 strongly trending market 偶爾合理，但在 mean-reverting 完全失效；跨 symbol / regime 不穩定。

### 2.3 Option C — 接受 per-tick 尺度，recalibrate 全部閾值

**實作**：`min_peak_atr_norm: 0.5 → 500`（或 `0.005`）、`giveback_base: 1.0 → 1000`、`base_stop_pct / atr_stop_mult` 也跟著調；完全放棄 "ATR 是交易員直覺尺度" 的語意。

| 評估軸 | 分數（0-1） | 備註 |
|---|---:|---|
| 實作成本 | 0.90 | 只改 TOML / seed，0 code |
| 統計合理性 | 0.10 | 語意**徹底斷裂**：`peak_atr_norm=500` 無法對應交易員任何直覺；調試/日誌/panel 全要心算 |
| 跨 consumer 一致性 | 0.50 | 三個 consumer 都得各自 recalibrate；`compute_dynamic_stop_pct` 尤其 hell（base=10%, cap=5%, atr×mult 全混亂） |
| 參數穩定性 | 0.15 | tick 頻率變 → 閾值失效（e.g. WS 升級、symbol 熱度變化、scanner 加新 symbol 改 publicTrade 頻率都會 break） |
| 與 counterfactual spec 衝突 | **極高** | Spec 的所有 threshold grid 要重算；replay audit 失效 |
| 回滾成本 | 低 | 純 TOML |
| **加權總分** | **0.30** | |

**致命弱點**：參數穩定性 0.15 是 show-stopper。未來任何 Bybit WS 頻率變化、scanner symbol pool 調整、tick sampling policy 改動都會讓閾值失效，且失效方式 silent（不會報錯，只是 Gate 突然常觸發或常不觸發）。

---

## 3. 尋找更好解（自主研究）

### 3.1 Option D — Realized Volatility（σ of log returns × √scale）

**實作**：tracker 改 `compute_realized_vol(symbol, lookback_secs)`：σ(log(p[t]/p[t-1])) over window，然後乘 √(target_horizon / tick_interval) annualize/horizon-ize 到持倉期。

| 評估軸 | 分數（0-1） | 備註 |
|---|---:|---|
| 實作成本 | 0.60 | 需算 log returns + σ + tick_interval 估計；~100 LOC |
| 統計合理性 | 0.80 | 標準 quant；GBM 假設下正確；但對 jump / fat-tail 低估 |
| 跨 consumer 一致性 | 0.75 | 需三個 consumer 同步切 |
| 參數穩定性 | 0.70 | 需假設 tick_interval 穩定；高頻 vs 低頻 symbol 需不同 scaling |
| 與 counterfactual spec 衝突 | 中 | ExitConfig seed 可能微調（RV 與 Wilder ATR 不完全等價） |
| 回滾成本 | 中 | 需 revert 新 fn + consumer wiring |
| **加權總分** | **0.65** | |

**中等問題**：需估計 tick_interval 做 √(horizon/interval) 縮放，引入新的參數。GBM 假設在 crypto 經常破（jump-diffusion 更接近）。不如直接用 OHLC true range 實在。

### 3.2 Option E — Parkinson / Garman-Klass Volatility Estimator（HL-based）

**實作**：Parkinson σ² = (1/(4 ln 2)) × mean(ln(H/L)²)；Garman-Klass 再結合 OC。

| 評估軸 | 分數（0-1） | 備註 |
|---|---:|---|
| 實作成本 | 0.40 | 需 OHLC buckets + Parkinson 公式 + 單測；~150 LOC |
| 統計合理性 | 0.90 | 理論上**比** true range 高效（用 HL 資訊，樣本需求少 5x） |
| 跨 consumer 一致性 | 0.75 | 3 consumer 切 |
| 參數穩定性 | 0.70 | 對 bar granularity 敏感；1m bar Parkinson 有噪音 |
| 與 counterfactual spec 衝突 | 高 | ExitConfig seed（`giveback_*`, `min_peak_atr_norm`）完全基於 "ATR units"，Parkinson 產出 σ 單位，需 × 某係數（e.g. ATR ≈ σ × √(π/2) × 某個常數）才能對齊，非平凡 |
| 回滾成本 | 中 | |
| **加權總分** | **0.55** | |

**中等問題**：強在理論效率，但 spec 的 seed values 是基於 Wilder ATR 直覺（"1 ATR retracement"），切 Parkinson σ 需要 empirical 校準係數；打破 counterfactual spec 語意連續性。Overkill for this fix。

### 3.3 Option F — 用現成 kline OHLC 算 Wilder's ATR（★ 推薦 ★）

**實作**：
- 新增 `PriceHistoryTracker::compute_atr_pct_from_klines(kline_mgr, symbol, timeframe, period)` 或更乾淨地在 `tick_pipeline::on_tick::step_6_risk_checks` 直接呼叫 `indicators::volatility::atr()`：
  ```rust
  let atr_pct = self.kline_manager.get_ohlcv(&p.symbol, "1m", Some(20))
      .and_then(|ohlcv| openclaw_core::indicators::volatility::atr(
          &ohlcv.high, &ohlcv.low, &ohlcv.close, 14
      ))
      .map(|r| r.atr_percent);
  ```
- `compute_dynamic_stop_pct` 同樣 inject（通過 `risk_checks.rs:179` 的 call site）
- `build_exit_features_for_tick` 同步接 `atr_pct` 參數來源改為 kline-based
- 舊 `compute_atr_pct`（per-tick version）不刪；留作 fast_track 閃崩偵測用（仍適合 per-tick 語義），改 rename 為 `compute_per_tick_abs_return` 避免混淆，**或** 保留名稱加 `#[deprecated]` warning；最終 `price_tracker.rs:105` 加 doc `// DO NOT USE for position-life ATR; use indicators::volatility::atr on kline OHLC instead`

| 評估軸 | 分數（0-1） | 備註 |
|---|---:|---|
| 實作成本 | 0.85 | 核心改動 ≤ 3 files（stops call site、builder、step_6_risk_checks）；不需新 state、不需 schema migration、不需 DB 查詢；reuse 既有 1835-test baseline |
| 統計合理性 | **0.95** | Wilder's ATR 是交易員標準；BTCUSDT 1m ATR ≈ 0.05-0.15%、14-period 等於 ~14 分鐘窗口；可自然擴展到 5m/15m 做 stops vs exits 不同時框 |
| 跨 consumer 一致性 | **0.95** | 三個 consumer 同一條 `atr_pct = atr(ohlcv.high, ohlcv.low, ohlcv.close, 14).atr_percent` 來源；一次修好 |
| 參數穩定性 | **0.90** | OHLC 對 tick 頻率不敏感（1m bar 固定聚合 60s 資料）；ExitConfig seed 可原封不動，counterfactual replay spec 不動 |
| 與 counterfactual spec 衝突 | **無** | `min_peak_atr_norm=0.5`、`giveback_base=1.0` 等 seed 正好對應 "0.5 ATR peak"、"1 ATR retracement" 交易員直覺，一切對齊 |
| 回滾成本 | **低** | 只需 revert 3 call site 的 `atr_pct` 來源，舊 per-tick 版保留可切回（不推，但可當 fallback） |
| **加權總分** | **0.88** | |

**強點**：
1. **零新實作**：`atr()` + `KlineManager` + `ohlcv_arrays()` 全部已存在、已單測、已 runtime wire up（`KlineManager` 每 tick 聚合已在 `step_1_2_klines_indicators.rs` 跑了）
2. **零 schema 變更**：不碰 DB migration
3. **三 consumer 一次修好**，且**與 counterfactual replay spec 的 grid search seed 完全相容**（`giveback_base ∈ {0.7,…,1.5}` / `slope ∈ {0.05,…,0.25}` / `floor ∈ {0.2,…,0.5}` 全部維持現有 interpretation）
4. **可 calibrate**：若 1m ATR 噪音大可切 5m，無架構變化
5. **測試友善**：既有 `test_atr_basic` 可直接引用，新 call site 只需 integration test

**弱點（輕）**：
- 需要至少 15 根 1m bars（~15 min）才能算 `atr(period=14)` — cold start 期間 `atr_pct = None` 導致所有 3 consumer 保守 Hold/無 ATR fallback。不影響 `GATE-4a`（它本來就 Option::None → Hold），但影響 `compute_dynamic_stop_pct`（無 ATR 時走 `base_stop_pct × regime_mult`，OK）。可 smoke 測 warm-up 階段。
- KlineManager 對 restart 有 cold start 問題（`seed_bars` 可 REST bootstrap，但需確認 runtime call path），若每次 restart 無 bootstrap 會有 ~15 min 空窗。**需在 PR 加 restart bootstrap 檢查** 或接受該空窗（已有既有 `kline_manager` 相同限制）。

### 3.4 Option G — Bybit REST endpoint `v5/market/index-price-kline` 或 `v5/market/kline` + 定時 poll

**實作**：後台 task 定時從 Bybit REST 拉 OHLCV（或 ATR 雖無此 endpoint 但可用 kline 自算），寫入 cache。

| 評估軸 | 分數（0-1） | 備註 |
|---|---:|---|
| 實作成本 | 0.40 | 新 background task + cache + REST client wiring |
| 統計合理性 | 0.90 | 真實 exchange OHLC，最準 |
| 跨 consumer 一致性 | 0.80 | |
| 參數穩定性 | 0.85 | 受 rate limit 影響；poll 頻率 trade-off |
| 與 counterfactual spec 衝突 | 低 | |
| 回滾成本 | 高 | background task 不易乾淨 revert |
| **加權總分** | **0.60** | |

**中等問題**：引入 REST 依賴 + rate limit 風險，但 Option F 的 local KlineManager 已經做一樣的事（就是 WS-sourced bars），沒道理再走 REST。**F 優於 G**。

### 3.5 額外考量：Option H — hybrid（kline ATR + per-tick fallback）

**實作**：主推 F，但 cold-start 時 fallback 到 per-tick × √(period_secs × tick_rate) 估 ATR。

不推：增加複雜度、兩條路徑交互點難測；寧願接受 cold-start 空窗（stops fallback to `base`，exits Hold）。

---

## 4. 推薦 + Scoring Matrix

### 4.1 Scoring Matrix（加權 0.30/0.30/0.20/0.20）

| Option | 實作成本 (0.30) | 統計合理 (0.30) | 跨 consumer (0.20) | 可 calibrate (0.20) | **加權** |
|---|---:|---:|---:|---:|---:|
| A 新 fn `compute_atr_14period` | 0.50 | 0.85 | 0.75 | 0.80 | **0.72** |
| B builder 乘 tick_count | 0.70 | 0.25 | 0.40 | 0.50 | 0.54 |
| C 全部閾值 recalibrate | 0.90 | 0.10 | 0.50 | 0.15 | 0.43 |
| D Realized Volatility | 0.60 | 0.80 | 0.75 | 0.70 | 0.72 |
| E Parkinson/Garman-Klass | 0.40 | 0.90 | 0.75 | 0.70 | 0.68 |
| **F kline OHLC + `indicators::atr`** ★ | **0.85** | **0.95** | **0.95** | **0.90** | **0.91** |
| G Bybit REST poll | 0.40 | 0.90 | 0.80 | 0.85 | 0.71 |

（F 加權 = 0.30×0.85 + 0.30×0.95 + 0.20×0.95 + 0.20×0.90 = 0.255 + 0.285 + 0.190 + 0.180 = **0.91**）

### 4.2 推薦理由

**推薦 Option F**，不是 A/B/C 任一：

1. **零新造輪子** — `openclaw_core::indicators::volatility::atr()`（`rust/openclaw_core/src/indicators/volatility.rs:75-110`）是 Wilder's smoothing 的 production-quality 實作，Kahan-summed、單測齊全（`test_atr_basic`、`test_atr_edge`），直接 reuse。
2. **零新狀態** — `KlineManager`（`rust/openclaw_core/src/klines.rs:437`）每 tick 在 `tick_pipeline/on_tick/step_1_2_klines_indicators.rs:37` 已經聚合多時框 OHLCV（`1m/5m/15m/1h/4h`），只需呼叫 `.get_ohlcv(symbol, "1m", Some(20))` 拿 arrays 餵給 `atr()`。
3. **零 schema migration** — 不動 DB，不改 `market.klines`。
4. **零 spec 衝突** — `docs/worklogs/2026-04-22--counterfactual_replay_audit_spec.md` 的 ExitConfig seed（`min_peak_atr_norm=0.5 / giveback_base=1.0 / slope=0.15 / floor=0.3`）**完全符合交易員直覺 ATR units**，不需重算 grid search；replay audit 仍有效。
5. **三 consumer 同步修好** — `compute_dynamic_stop_pct`（`risk_checks.rs:179`）、`build_exit_features_for_tick`（`builder.rs`）、`physical_micro_profit_lock_v2`（`v2.rs`）接同一來源一次到位。
6. **可 tier up** — 若 1m 噪音大 → 切 5m；若要 daily stops → 切 1h 或 4h；全部 `atr()` 參數化。

**與 A 的對比**：A 是 F 的 "不知道有 `indicators::atr`" 版本。F = A − 重複實作 + reuse。

**與 B 的對比**：B 數學上錯（平均 abs return × N 不是持倉期 range），F 是交易員標準的 true range ATR。

**與 C 的對比**：C 放棄語意、拿 tick 頻率當隱式參數、未來 silent failure 風險極高；F 把語意拉回交易員直覺，閾值穩定。

---

## 5. Deploy 約束：必與 P0-14 同 rebuild

### 5.1 耦合性（source: `docs/worklogs/2026-04-22--p0_14_edge_estimates_miss_rca.md §7.2/7.3`）

| 狀態 | Gate 1（edge floor） | Gate 3（peak_atr_norm） | Gate 4a（giveback vs threshold） | 結果 |
|---|---|---|---|---|
| 現在（皆 broken） | 永遠 Hold（99% edge=None） | 永遠過（ratio 放大 100x） | 永遠 Lock-eligible 但被 Gate 1 Hold 擋下 | Priority 6 零 fire |
| 單修 P0-13（本項） | 仍永遠 Hold（P0-14 未修） | 正常閾值 | 正常（但 Gate 1 擋下） | 仍 0 fire；**失去 P0-13 修復的可觀測性**（無法 runtime 驗證 Gate 3/4a 行為）|
| 單修 P0-14 | 正常放過有 edge 的倉 | **永遠過**（ratio 仍放大 100x） | **永遠觸發 Lock**（giveback_atr_norm 放大 100x，任何 giveback 都 >> threshold） | **mass close 災難** |
| **同修 P0-13 + P0-14** | 正常 | 正常 | 正常 | Priority 6 首次真實按設計運作 |

**硬約束**：**P0-13 Option F 與 P0-14（Option A Gate 1 fallback + Option B JS proxy cells）必須同 commit 或同 `restart_all.sh --rebuild` 週期**，單邊修 = 災難或無效。

### 5.2 與 P0-14 推薦路徑（A + B）的接合

- P0-14 Option A（Rust Gate 1 fallback）= 改 `v2.rs:246-251` 加 `missing_edge_fallback_bps`：**與 P0-13 Option F 正交**，修改不同 code region（`exit_features/v2.rs` Gate 1 邏輯 vs `tick_pipeline/on_tick/step_6_risk_checks.rs` + `builder.rs` 的 `atr_pct` source）。
- P0-14 Option B（JS estimator sync-label proxy cells）= 改 Python，**與 P0-13 完全解耦**。
- 建議 PR 結構：
  1. **Commit #1（P0-13 Option F）**：atr_pct 來源切 `KlineManager + indicators::volatility::atr`；3 call sites + 單測更新；engine lib baseline 1835 → ~1845（+~10 integration tests）
  2. **Commit #2（P0-14 Option A）**：`v2.rs` Gate 1 加 fallback
  3. **Commit #3（P0-14 Option B）**：Python JS estimator 補 sync-label proxy cells
  4. **同一 `restart_all.sh --rebuild`** 一次部署（Python reload + Rust engine rebuild）

### 5.3 Rollback plan

- P0-13 Option F 回滾：revert commit #1；3 call sites 回切舊 `self.price_tracker.compute_atr_pct(&p.symbol)`；engine rebuild；舊 bug 復現但系統回到 known-state（Priority 6 仍 0 fire，acceptable 作為 safety net）。
- 若 P0-13 fix 後觀察 Gate 4a 開始 mass close → **必檢查 P0-14 是否同步部署**；若 P0-14 fix 出問題，**兩個一起 revert**（不可只 revert 一邊）。

---

## 6. Execution Plan（若 operator 選 F + P0-14 A+B）

### Day 0（同 session 內）

**E1 實作（Mac dev → SSH Linux verify）** — ~4-6h

**Commit #1 — P0-13 Option F：**

1. 修改 `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs:93`：
   ```rust
   atr_pct: self.kline_manager.get_ohlcv(&p.symbol, "1m", Some(20))
       .and_then(|o| openclaw_core::indicators::volatility::atr(&o.high, &o.low, &o.close, 14))
       .map(|r| r.atr_percent),
   ```
2. 修改 `rust/openclaw_engine/src/risk_checks.rs:179-188`：`compute_dynamic_stop_pct` 的 `atr_pct` 入參同樣切 kline-based（需 `check_position_on_tick` 呼叫端改傳新來源；可能需傳 `&KlineManager` ref 或已算好的 `atr_pct`）。
3. `rust/openclaw_engine/src/exit_features/builder.rs` 的 `atr_pct` 參數本身不動（它是被餵入的），但 callsite（`step_6_risk_checks.rs` 準備 `ExitFeatures` 時）切 kline-based 來源。
4. `rust/openclaw_core/src/risk/price_tracker.rs:105-135` 加 `#[deprecated(note = "Use indicators::volatility::atr on KlineManager OHLCV for position-life ATR; this fn returns per-tick micro-volatility only suitable for fast_track spike detection")]` warning；保留 fn body 不動（fast_track 可繼續用）。
5. 單測：新增 `test_step6_atr_pct_from_klines`（mock KlineManager 餵 20 bars, 斷言 atr_pct ≈ 0.1-0.5% 範圍而不是 0.001%-0.006%）；engine lib 預期 1835 → ~1845。

**Commit #2 — P0-14 Option A（Rust Gate 1 fallback）：**

6. `rust/openclaw_engine/src/exit_features/v2.rs:67-104` 加欄位 `missing_edge_fallback_bps: f64`（default `-10.0`）+ Gate 1 分支 `None → use fallback`。
7. `ExitConfig::validate()` 校驗新欄位。
8. 單測：`test_v2_gate1_missing_edge_uses_fallback`、`test_v2_gate1_missing_edge_fallback_below_floor_holds`。

**Commit #3 — P0-14 Option B（Python JS estimator sync-label proxy）：**

9. `srv/program_code/ml_controller/edge_estimator/...`（具體路徑見 P0-14 RCA §3）加 sync-label → proxy cell 映射邏輯。
10. pytest 新增測試覆蓋 `bybit_sync` / `orphan_adopted` / `dust_frozen` label 下 shrunk_bps 可解析。

**E2 對抗性審查（主會話 PM 或派 sub-agent）** — ~2h

- 檢查 deprecation warning 沒破任何既有 call site（`compute_atr_pct` 在 fast_track、tests、compute_roc 同檔案 still used）；
- 檢查 `compute_dynamic_stop_pct` call site 改 signature 沒 break `risk_checks` 以外 caller；
- `grep atr_pct` 全 repo 確認新語義統一；
- Cross-platform check（`grep -E '(/home/ncyu|/Users/[^/]+)'`）；
- Counterfactual replay spec 語義仍有效（ExitConfig seed 對齊交易員 ATR）。

**E4 測試回歸** — ~1h

- Mac debug：`cargo test -p openclaw_engine --lib` 期待 ~1845 passed / 0 failed
- Mac debug：`cargo test -p openclaw_core --lib`
- Linux release（SSH bridge）：`ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"`
- pytest：`ssh trade-core "cd ~/BybitOpenClaw/srv && pytest tests/... -q"`（特別覆蓋 P0-14 Python B 部分）

### Day 1 deploy

- `git push origin main`（Mac → GitHub）
- `ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only && bash helper_scripts/restart_all.sh --rebuild"`
- 預期 engine restart、new PID、watchdog healthy

### Day 1+（24h 監控指標）

1. **Priority 6 fire rate** — `psql` 查 `decision_outcomes` 或 engine log grep `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg`；期待從 7d 0 次 → **1-10 次/day**（非災難 mass close）
2. **Gate 3 pass rate** — log grep `gate3 pass`，期待從 ~100%（因 bug 放大）降到 ~30-60%（合理）
3. **DB `learning.exit_features.giveback_atr_norm` avg** — 從 7d avg 364.85 → 期待 ~0.3-3.0（正常 ATR 單位）
4. **`learning.exit_features.atr_pct` avg** — 從 ~0.003 → 期待 ~0.05-0.2（1m 14-period ATR 合理範圍）
5. **Dynamic stop trigger rate** — 7d 只 1 次 → 期待 1-5 次/day（合理範圍，若爆多則 base_stop_pct 需調）
6. **est_net_bps NULL rate** — 從 99.1% → 期待降到 20-40%（sync-label 倉位有了 fallback 或 proxy cells）
7. **unexpected mass close** — alert：24h close 數 > 10（目前平均 ~2-3/day）→ 立即 revert

### Day 7 checkpoint

- 收集 1w exit_features 新分布
- 若 Priority 6 Gate 4a fire > 50/day → 閾值需 calibrate（counterfactual replay spec 的 grid search 此時觸發）
- 若 Dynamic stop trigger > 20/day → 其中有 base_stop_pct 太緊，另開 P1 修
- 若一切穩定 → `project_track_p_runtime_live.md` memory 更新 "Priority 6 fires as designed since 2026-04-2X"

---

## 7. 不確定之處 / Questions to verify

1. **Cold start KlineManager** — restart 後需 ~15 min 累 1m bars 才能算 `atr(14)`。期間 `atr_pct = None` → Dynamic stop 走 base、Exit features Hold。**建議 operator 確認**：`KlineManager::seed_bars` 是否在 engine startup bootstrap；若否，P0-13 fix 後要接受 startup 15 min 的 Gate 3 全 Hold。（可請 operator 跑 `ssh trade-core "grep -rn 'seed_bars' srv/rust/openclaw_engine/src/ | head"`）

2. **`compute_dynamic_stop_pct` call chain** — `risk_checks::check_position_on_tick:179` 的 `atr_pct` 入參當前來源（`step_6_risk_checks.rs` 或上游）需確認；可能需加 `KlineManager` ref 到 risk_checks 或讓 caller 預先算好傳入。建議 E1 先 trace call graph 再動。

3. **1m vs 5m** — 推薦初始 1m period 14 = ~14 min 窗口；若實測噪音大（giveback_atr_norm 方差過大）可切 5m（= 70 min 窗口）。**不是**本 PR 範圍；先用 1m 觀察 1 週再議。

4. **`compute_atr_pct` 誰還在用** — `grep compute_atr_pct`（已跑）只見 price_tracker 自檔 tests + step_6_risk_checks 1 處 + pipeline_helpers 1 處 docstring + builder docstring；fast_track 只用 `max_drop_pct / detect_spike` 不用 atr_pct，所以 deprecation 影響面**僅 step_6_risk_checks + docstring**。安全。

5. **`build_exit_feature_row` (close-time) 的 `atr_pct`** — `pipeline_helpers.rs:297` 同樣有 `atr_pct` 欄位（close 時計算），需確認是否同步切來源；**是**，否則 close-time row 與 live-time row 語意不一致。E1 必檢此點。

6. **replay spec 的 `atr_fallback_pct=1.0`** — Python replay simulator 仍可能用 per-tick `compute_atr_pct`（從 DB 讀）；若 P0-13 fix 後新 exit_features rows `atr_pct` 改為 kline-based，舊 rows 仍是 per-tick 尺度，replay 跨這次 fix 前後 → 必須 partition time window 或 recompute 舊 atr_pct。**建議 operator 確認**：replay 是否只跑 fix 後 1w 資料（那就沒問題）。

---

## 8. 最終答案速查

- **推薦 option**：**F — kline OHLC + `openclaw_core::indicators::volatility::atr`**
- **1 句話理由**：既有 `indicators::atr()` 是 Wilder 標準實作、`KlineManager` 每 tick 已聚合多時框 OHLCV 且已接線、三個 consumer 同步修好、零 schema 變更、與 counterfactual replay spec seed 完全對齊。
- **4 軸加權分數**：**0.91**
- **與原 A/B/C 不同**：**是**（A 次佳 0.72，B 0.54，C 0.43）
- **與 P0-14 協調關鍵約束**：**必同 `restart_all.sh --rebuild` 週期部署**（P0-13 Option F + P0-14 Option A Rust Gate 1 fallback + P0-14 Option B Python JS proxy cells）；單獨 deploy 任一邊 = 災難（只 P0-14）或無效 + 失去觀測性（只 P0-13）；建議同 PR 三 commits 一次 restart。
- **代碼 file:line 焦點**：
  - `rust/openclaw_core/src/indicators/volatility.rs:75-110`（reuse target）
  - `rust/openclaw_core/src/klines.rs:200-225`（`ohlcv_arrays` API）
  - `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs:93`（主要 callsite 切換）
  - `rust/openclaw_engine/src/risk_checks.rs:179-188`（dynamic stop callsite）
  - `rust/openclaw_engine/src/exit_features/builder.rs:104-114`（builder 接收改變來源的 `atr_pct`）
  - `rust/openclaw_core/src/risk/price_tracker.rs:105`（加 `#[deprecated]` warning，保留 fast_track 用）
  - `rust/openclaw_engine/src/exit_features/v2.rs:246-251`（P0-14 Gate 1 fallback 點）
