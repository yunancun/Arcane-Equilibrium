# Axis (a) Beta/Residual 分解 + Axis (d) 兩流尾部共依存 — 數字報告

**日期**：2026-06-17 | **執行**：E1（research analysis）| **性質**：$0 OFFLINE 唯讀實證
**目標**：以最廉價的決定性測試，判定 operator「收割 managed-beta + 結合 cross-sectional
market-neutral 為兩條正交、Sharpe-additive 流」的方向是否可行，抑或只是 down-beta trap 換名。
**範圍**：只跑 QC 協議的 axis (a) + (d)；**不建** conditioning-signal 搜索（gated on 本測通過）。
**最終 verdict 不由本報告下**——交 QC 在 MIT 審 leak-free 完整性後裁。

**Runtime**：Linux trade-core，PG `trading_ai`（唯讀 session），numpy 2.4.4 / Python 3.12.3。
**腳本**（新增，唯讀研究）：
- `helper_scripts/research/beta_decomp_tail_dependence/step0_coverage.py`
- `helper_scripts/research/beta_decomp_tail_dependence/analysis.py`
- 復用 `program_code/ml_training/residual_alpha_producer_db.py`（contained-bar / bucket-by-exit /
  BTC-factor / FIFO round-trip 載入）+ `realized_edge_stats.py`（FIFO 配對）+
  `helper_scripts/research/multiday_trend_diagnostic`（leak-free 紀律參照）。

> **偏差註記**：prompt 指 residual producer 在 `program_code/research/...`，實際在
> `program_code/ml_training/residual_alpha_producer_db.py`（grep 確認）。最小安全解：用實際路徑。

---

## STEP 0 — 資料覆蓋（誠實，未造假）

### (i) market.klines 覆蓋
| timeframe | rows | symbols | span |
|---|---|---|---|
| 1m | 15,558,306 | 155 | 2026-04-05 → 2026-06-17 |
| 5m | 3,106,192 | 153 | 2026-04-05 → 2026-06-17 |
| 15m | 1,035,305 | 153 | 2026-04-05 → 2026-06-17 |
| 1h | 258,784 | 153 | 2026-04-05 → 2026-06-17 |
| 4h | 64,618 | 153 | 2026-04-05 → 2026-06-17 |
| 1d | 18,885 | 26 | 2024-06-02 → 2026-06-09 |

**關鍵**：所有 intraday klines（1m–4h）只回溯到 **2026-04-05**。只有 1d 有 ~2 年歷史（且僅 26 symbol）。

### (ii) demo / live_demo fills
| engine_mode | fills | span |
|---|---|---|
| demo | 5,166 | 2026-04-18 → 2026-06-17 |
| live_demo | 3,700 | 2026-04-17 → 2026-06-12 |

FIFO 配對出 **3,208 筆 demo round-trips**（net_pnl_bps 已扣費帶方向）：

| strategy | round-trips | symbols | mean net bps | entry span |
|---|---|---|---|---|
| grid_trading | 2,072 | 85 | **−12.61** | 2026-04-18 → 06-17 |
| ma_crossover | 893 | 72 | **−3.95** | 2026-04-18 → 06-17 |
| funding_arb | 135 | 14 | **−20.39** | 2026-04-28 → 06-17 |
| bb_reversion | 64 | 24 | **−13.70** | 2026-04-21 → 06-17 |
| bb_breakout | 41 | 12 | **+9.46** | 2026-04-29 → 06-12 |

（4/5 策略均值負；唯一正的 bb_breakout 樣本最小 n=41。）

### (iii) residual_alpha_producer
可 import + 可跑：`build_bucketed_residual_report` / `bucket_round_trips_by_exit` /
`build_residual_alpha_report` 全存在（Linux 探測 True）。

### (iv) 5 個歷史崩盤日 kline 覆蓋
| 崩盤日 | kline 覆蓋 |
|---|---|
| 2020-03-12 (COVID) | **無（零行）** |
| 2021-05-19 (519) | **無（零行）** |
| 2022-05-09 (LUNA) | **無（零行）** |
| 2022-11-08 (FTX) | **無（零行）** |
| 2024-08-05 (carry unwind) | 有，**僅 1d，25 symbol** |

**4/5 崩盤日完全無資料。** 唯一覆蓋的 2024-08-05 僅 1d，且 **demo fills 從 2026-04 才開始** →
無任何 round-trip 落在該日 → stress 表對歷史崩盤**結構性不可跑**。

---

## AXIS (a) — 歷史 PnL 的 beta/residual 分解

方法：每筆 round-trip 把 realized `net_pnl_bps` 對該筆 [entry,exit] 窗的 BTC 報酬（leak-free
contained-bar，僅用完全落窗內的 1m bar）做 OLS；兩維 cluster（symbol × day，Cameron-Gelbach-Miller）
穩健 SE。對齊 2,451 / 3,208 筆（757 筆因窗太短無 contained 1m bar 丟棄）。

### Pooled（leak-free）
| 量 | 值 |
|---|---|
| BTC beta（b） | **−0.0180**（t = −2.77，clustered） |
| **R²（beta 解釋的 PnL 變異）** | **0.00066 ≈ 0.07%** |
| 殘差均值 e（= 截距，x=0 預期 net） | **−12.47 bps**（t = **−5.02**） |
| mean net PnL | −12.21 bps |
| clusters | 80 symbol × 59 day |

### leak-free vs naive 雙軌
- naive（窗 ±60s 放寬）：R² = 0.00065，殘差 −12.47 bps。
- **dual-track R² 背離 = 9.2e-6（≪ 30% 閾值）→ 無 look-ahead 旗標。**
- **強化 leak 對照**（額外驗證）：把 BTC 報酬換成 **[exit, exit+dur] 未來窗**（真洩漏軌），
  R² = 0.00004 < leak-free 0.00067 → 證明 PnL 不依賴 BTC 未來窗、contained-bar 無前視。

### per-strategy（leak-free）
| strategy | n | beta（t） | R²_beta | 殘差 e bps（t） |
|---|---|---|---|---|
| grid_trading | 1,614 | −0.0154 (−2.09) | 0.0008 | **−15.11 (−4.46)** |
| ma_crossover | 707 | −0.0285 (−2.20) | 0.0007 | −6.47 (−1.07) |
| bb_reversion | 39 | −0.0086 (−0.94) | 0.0131 | **−14.17 (−2.24)** |
| funding_arb | 64 | −0.0157 (NaN¹) | 0.0003 | −13.28 (−1.11) |
| bb_breakout | 27 | — | — | insufficient_aligned (<30) |

¹ funding_arb beta SE=0（day cluster 退化，n=64 / 8 day），t 不可解讀。

### Axis (a) 解讀（**與先驗預期相反，必須誠實標**）
先驗（QC priors / down-beta trap 假說）預期：**beta 解釋大部分 PnL，殘差 ≈ 0 或負**。
**實測相反**：BTC beta 解釋 PnL 變異 **≈ 0%（R²=0.0007）**，PnL **幾乎全是殘差**，且殘差
**顯著為負（−12.5 bps，t=−5.0）**。

含義：這批 demo PnL 的虧損**不是 BTC 同期 beta 的副產品**——per-trade 持倉窗短，PnL 由策略
特有結構 + 成本主導，與同窗 BTC 漂移幾乎無關。這比「down-beta trap」更基本：扣掉（微小的）
BTC 曝險後，**per-trade 殘差 alpha 本身就顯著為負**。對 operator 方向的意涵見「綜合」節。

> 注意尺度差異：此處 beta 是「per-trade 短窗 net_pnl_bps 對同窗 BTC return（bps）」的迴歸，
> 量測的是**逐筆執行層**的 beta 暴露，**不是**日 PnL 的 portfolio-level beta。兩者不同；axis (d)
> 的 stream 是日層，分開看。

---

## AXIS (d) — 兩流尾部共依存（決定性部分）

- **stream_F**（managed-beta 代理）= **constant-vol-target buy-and-hold BTC 日 PnL**，leak-free
  shift(1) sizing：`size_t = clamp(2%/vol_{t-1}, 0, 3x)`，vol 用 [t-30, t-1] 不含當日；日 PnL =
  size×r_t。選此代理因 demo book 自身的 beta-exposure 日 PnL 無乾淨拆分，而 vol-target BHODL BTC
  是最簡可辯護、純 leak-free 的 managed-beta 流。**單位 = 日報酬 fraction**（~0.02 量級）。
- **stream_ε**（cross-sectional residual）= demo round-trips 經 residual producer 的非重疊
  exit-keyed 4h bucket → BTC-beta 殘差化（e = candidate − (a+b·BTC)，β_btc=0.182，截距 −124 bps）
  → 殘差按 bucket exit 日聚到日。**單位 = 日 residual bps 加總**（量級數百–數千）。

### 重疊窗
- stream_F：699 日（2024–2026，1d）；stream_ε：60 日；**重疊 = 44 日（2026-04-18 → 2026-06-01）**。
- 264 個對齊 bucket 進殘差化。

### 無條件相關（**勿被安撫**）
| 量 | 值 |
|---|---|
| Pearson ρ | **0.242** |
| Spearman ρ | 0.112 |

→ 並非 ~0；已是 modest-positive。（協議要求：不可因無條件 ρ 低就放心。）

### 下尾依存 λ_L = P(ε 最差 q% | F 最差 q%)
| q | λ_L | F-tail 天數 | co-exceedance | 獨立期望 |
|---|---|---|---|---|
| 5% | 0.00 | 3 | 0 | 0.15 |
| 10% | **0.20** | 5 | 1 | 0.50 |

→ q=5% 看似 0，但 **tail 只有 3 天**；q=10% λ_L=0.20 **恰在 bar 邊界**，tail 5 天 1 命中。
**n 極小 → 無 power，不可解讀為「尾部獨立」**。

### crash 子集條件 ρ（**決定性 red flag，但 power 不足**）
- crash 子集定義：BTC 日報酬 < −5% **OR** realized-vol 頂十分位。
- **重疊 44 日內 BTC 日報酬 < −5% 的天數 = 0**（最差單日 −3.07%）→ crash 子集全由 vol 頂十分位
  的**溫和**日組成（n=5）。
| 量 | 值 |
|---|---|
| full-sample Pearson ρ | 0.242 |
| **crash-subset Pearson ρ** | **0.767** |
| **Δρ** | **+0.525** |

→ 條件相關在高 vol 子集**暴增 0.24 → 0.77**——**正是 down-beta trap 指紋**（平時去相關、壓力下
同步崩）。**但 n=5 且無真崩盤 → INCONCLUSIVE，不可作決定性證據**，只能作方向警告。

### Stress 表（覆蓋窗內 crash 日）
| date | BTC ret | stream_F | stream_ε bps | both negative |
|---|---|---|---|---|
| 2026-04-18 | −1.78% | −0.0163 | −162.1 | **是** |
| 2026-04-19 | −2.49% | −0.0230 | −1726.6 | **是** |
| 2026-04-20 | +2.74% | +0.0240 | +4174.6 | 否 |
| 2026-04-21 | +0.67% | +0.0059 | +258.0 | 否 |
| 2026-04-22 | +2.42% | +0.0215 | +276.3 | 否 |

→ 5 個 crash 日中 **2 日兩流同號為負**（04-18/04-19，溫和下跌日）；同號性與 BTC 方向一致
（跌日兩流齊跌、漲日兩流齊漲）= **兩流並非正交，在方向性日同步**。
**單位不同**（F=fraction、ε=bps-sum），combined PnL 不可直接相加；表只供**同號性**判讀。

> 5 個歷史崩盤日 stress 表（2020/2021/2022×2/2024）**無法產出**：4 日零 kline、2024-08-05 早於
> demo fills。本表只能用覆蓋窗內的溫和 vol 日代理，**這正是資料覆蓋 gap 的直接後果**。

### 初判 pass/fail（QC bar；**非最終 verdict**）
| QC bar | 結果 |
|---|---|
| λ_L < 0.2（q=5% 與 q=10% 皆） | **未過**（q=10% = 0.20 邊界；且 n 太小無 power） |
| crash-subset ρ 不顯著大於 full-sample | **未過**（Δρ = +0.525；但 n=5 INCONCLUSIVE） |
| 無覆蓋情境出現兩流同號虧損 | **未過**（2 日兩流同號為負） |
| **all_bars_pass** | **False** |

---

## 綜合（初步，交 QC 裁）

1. **Axis (a) 反轉先驗**：BTC beta 解釋 demo PnL 變異 ≈ 0%；PnL 幾乎全是**顯著為負的殘差**
   （−12.5 bps，t=−5.0）。即「過去 PnL 多少是 beta vs 殘差」的答案是：**幾乎全殘差、且殘差負**。
   這不是「賺到的是 beta」——是「逐筆執行層在扣掉 BTC 後仍系統性虧損」。leak-free 紀律乾淨
   （naive/leak-free 背離 9e-6、future-window 對照 R² 更低）。

2. **Axis (d) 三條 QC bar 全初判未過**，但**三條都被同一資料 gap 重創**：重疊僅 44 日、且窗內
   **零真崩盤**（最差 −3.07%）。唯一能算的高 vol 子集顯示條件 ρ 由 0.24 暴增到 0.77（down-beta
   trap 指紋），**但 n=5、power 不足**，是 red flag 非定論。

3. **「最廉價決定性測試」在此資料上無法決定性**：tail co-dependence（「THE decisive part」）需要
   真崩盤樣本，而 4/5 歷史崩盤零覆蓋、demo 窗無崩盤。**現有資料既不能證實也不能證偽
   Sharpe-additive，但目前所有可量到的訊號（無條件 ρ=0.24、tail Δρ=+0.52、2/5 同號負）都偏向
   「兩流在壓力下並非正交」= down-beta trap 換名的方向**，只是 power 不足以下鐵口。

---

## 資料限制（明確）

- **重疊窗僅 44 日**（demo fills 起點 2026-04 ∩ 殘差 bucket 對齊），axis (d) power 嚴重受限。
- **窗內零真崩盤**（BTC 最差日 −3.07%）；crash 子集全是溫和 vol 頂十分位日，n=5。
- **4/5 歷史崩盤日（2020/2021/2022 LUNA/2022 FTX）零 kline**；2024-08-05 僅 1d 且早於 demo fills
  → 跨真崩盤 stress 表結構性不可跑。
- **兩流單位不同**（stream_F=日報酬 fraction、stream_ε=日 residual bps-sum）；相關 / Spearman /
  λ_L / crash-ρ 皆 scale-invariant 有效，但 combined-PnL / combined-max-DD **不可直接相加**
  （已標註，只用同號性判讀）。
- stream_F 用 **vol-target BHODL BTC 代理** managed-beta，非 demo book 真 beta-exposure 流
  （後者無乾淨拆分）；代理選擇已聲明。
- axis (a) 的 beta 是 **per-trade 短窗執行層** beta，非 portfolio 日層 beta；兩者不可混為一談。
- funding_arb day-cluster 退化（SE=0），其 beta t 不可解讀。
- leak-free 完整性的**最終裁定屬 MIT**（本報告自證 naive/future-window 對照乾淨，非取代 MIT 審）。

## Operator 下一步（建議，非自行決策）
1. **交 QC**：在 MIT 審 leak-free 完整性後下最終 verdict。本報告強烈傾向「現有資料不足以解鎖
   conditioning-signal 搜索」——所有可量訊號偏向 down-beta trap 但 power 不足以鐵口。
2. **若要讓 tail co-dependence 測試真正具決定性**：需 backfill 真崩盤期 intraday klines（至少
   2024-08-05、2022 LUNA/FTX），且需要跨真崩盤的 demo/live_demo 持倉——後者 demo book 不存在，
   只能靠**歷史 replay** 在崩盤期重建兩流（屬 QC/MIT 範疇，非本 axis）。
3. **conditioning-signal 搜索維持 GATED**（未通過本測，依 prompt 不建）。

---
**產物**：
- 報告：本檔。
- 腳本：`helper_scripts/research/beta_decomp_tail_dependence/{step0_coverage,analysis}.py`（唯讀）。
- ephemeral artifact（Linux，非永久）：`trade-core:/tmp/openclaw/beta_decomp/{step0_coverage,analysis}.json`。
