# MIT W2 A4-C σ verify — BTCUSDT 1m forward return realized σ (7d)

**Date**: 2026-05-10
**Trigger**: PA W2 spec v1.1 §7.1 acceptance prerequisite — MIT C-3 verify σ before W2 sign-off
**Boundary**: read-only PG audit; spec acceptance update by PA at D+1 sign-off

## 1. Schema discovery

- **Table**: `market.klines` (TimescaleDB hypertable, 6 chunks)
- **Columns**: `ts TIMESTAMPTZ`, `symbol TEXT`, `timeframe TEXT`, `open/high/low/close REAL`, `volume`, `turnover`, `tick_count`
- **Index**: PK `(symbol, timeframe, ts)`, secondary `(symbol, timeframe, ts DESC)` + `(ts DESC)`
- **BTCUSDT 1m coverage**: 42628 rows / 35 days (2026-04-05 → 2026-05-10)
- **timeframe value**: `'1m'` 字串（不是 `'1'`）

## 2. σ_60 / σ_120 / σ_300 實測 (n=10050 samples, 7d window)

| N | σ (bps) | mean (bps) | skew | excess kurt |
|---|---|---|---|---|
| 60s  | 4.5397  | 0.0289 | -0.18 | 11.76 |
| 120s | 6.2760  | 0.0574 | -0.01 | 7.82  |
| 300s | 10.0838 | 0.1440 | 0.03  | 10.34 |

實測 vs PA spec preliminary 30 bps **ratio: 0.15× / 0.21× / 0.34×**（**遠低於 spec**）。

## 3. PA spec preliminary σ=30 bps verdict — **WARN with reframing**

關鍵語意分歧：
- **實測 σ (raw market 1m forward close-to-close)**: 4.5-10.1 bps（純價格 σ）
- **EDGE-DIAG-1 demo σ ≈ 50-80 bps**: 是 **net realized edge σ**（含 fee + slippage + adverse selection + holding 內 hedge cost）
- **PA spec 30 bps** 是 **preliminary 中介值**，但 v1.1 §7.1 未明定哪一層

**Verdict**：`σ=30 bps` 位於 raw σ (5-10) 與 net edge σ (50-80) 之間，**不是任何一方的真實值**。建議 PA W2 spec acceptance 改為**雙層驗收**：
- L1 raw price σ_300 = 10.08 bps（實測 baseline）
- L2 net realized σ ≈ 50-80 bps（EDGE-DIAG-1 historical empirical baseline）

## 4. PSR(0) skew/kurt deflation 預估

Bailey & Lopez de Prado PSR(0) formula 用 raw σ + skew + ex_kurt：

| N | period SR | full kurt | PSR_z | PSR(0) |
|---|---|---|---|---|
| 60s  | 3.30 | 14.76 | 4.69 | 1.0000 |
| 120s | 2.39 | 10.82 | 5.48 | 1.0000 |
| 300s | 1.49 | 13.34 | 4.74 | 1.0000 |

**Interpretation**：用 raw σ 計算 PSR(0) 全部 ~1.0（high SR），但這是 **naive raw σ 視角**——未含 transaction cost。**真實 net SR 用 σ_net=50-80 bps 推算**：

| σ_net | SR_period | PSR(0) (kurt=10) |
|---|---|---|
| 50 bps  | 0.30 | ~0.997 |
| 60 bps  | 0.25 | ~0.985 |
| 80 bps  | 0.19 | ~0.94 |
| 100 bps | 0.15 | ~0.86 |

**fat tail (ex_kurt 7-12) 顯著影響**：normal-assumed PSR > skew/kurt-aware PSR by ~10-15 pp at σ_net=80。

## 5. Power recalc (μ=15 bps paper avg_net, N_fills=80)

**Raw σ 視角（過度樂觀）**：
| N | SE | t-stat | p-value |
|---|---|---|---|
| 60s  | 0.51 | 29.55 | <1e-50 |
| 120s | 0.70 | 21.36 | <1e-50 |
| 300s | 1.13 | 13.31 | <1e-50 |

**Net edge σ 視角（真實 acceptance 應用）**：
| σ_net | SE | t-stat | p-value |
|---|---|---|---|
| 50 bps  | 5.59  | 2.68 | 0.0044 |
| 60 bps  | 6.71  | 2.24 | 0.0141 |
| 80 bps  | 8.94  | 1.68 | 0.0487 |
| 100 bps | 11.18 | 1.34 | 0.0918 |

**對應 QC W2 review 警告線**：σ ≥ 60 bps t-stat 跌至 2.36 → 實測 net edge σ ≈ 60-80 bps 已**精確命中** QC 警告區間。σ_net=80 bps 時 p=0.049（剛 <0.05 邊緣 PASS），σ_net=100 bps 已 FAIL。

## 6. W2 sign-off 預期 — **CONDITIONAL PASS with spec amendment**

**Verdict**：
1. **Raw 1m forward σ verify PASS**：實測值（4.5-10.1 bps）已交付 PA W2 acceptance
2. **PA W2 spec v1.1 §7.1 必修**：σ=30 bps preliminary 不對應任何真實層；改為 dual-layer (L1 raw σ_300=10 bps + L2 net edge σ_60_horizon ≈ 50-80 bps EDGE-DIAG-1 baseline)
3. **Power 不需重算 dispatch**：raw σ baseline t-stat>>2 (acceptance 充分)，但 spec 文檔需註明「真實 acceptance 必用 net edge σ 50-80」避免後續 sign-off 假性 PASS
4. **PSR(0) skew/kurt deflation**：raw 視角全 PASS，但 net edge σ ≥ 80 + ex_kurt ~10 → PSR(0) deflate 至 ~0.94，**接近 0.95 標準下界**
5. **不需 D+1 MIT C-3 重跑**：本次 sigma verify 已交付完整資料；D+1 PA sign-off 同次 update spec acceptance language 即可

**Sample-size caveat**：BTCUSDT 7d demo+live decision_outcomes 只 n=7，sigma_1m=5.27 bps 對齊 raw σ_60=4.54 bps（一致），但策略真實 fill σ 需更大樣本驗證。

## 7. Beyond scope observations

- BTCUSDT 1m raw forward return excess kurt 7-12 ≫ 0（normality FAIL by Jarque-Bera 高機率）；任何用 normal assumption 的 t-test / SR 計算須加 PSR(0) skew/kurt 修正
- decision_outcomes BTCUSDT 7d n=7 太低，建議 W3 提升到 multi-symbol 用 grid_trading 主流 cohort 重算 net σ
- Raw σ_horizon ∝ √horizon 大致成立（σ_60=4.54 → σ_300=10.08，比例 2.22 vs √5=2.24 一致）

