# v5.8 13-Module Autonomy Expansion 執行性審核 — QC 視角

**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：13 module DESIGN-only Sprint 1A 範圍 governance OK，但 5 個 module 觸碰嚴格 QC 數學門檻（M4 false discovery + M6 Bayesian 樣本不足 + M9 mSPRT 自相關偏差 + M11 ad-hoc threshold + M10 Tier D regime auto-classify 隱伏 HMM 黑名單）；4 module 完全 OK（M1/M2/M3/M7/M8）；M5/M12/M13 interface stub 無 QC 異議。

## 0. 13 module 數學 / 統計基礎評估

| Module | Verdict | 核心理由 |
|---|---|---|
| **M1** Lease Tier auto-approval gate | VALID | 30 prior Advisory + 80% yes-rate + 90d no incident + opt-in 結構 governance-sound |
| **M2** Overlay enable state machine | VALID | counterfactual t-stat ≥ 1.5 sustained 60d + 30 events 為 conservative threshold；auto-disable Sharpe<0 路徑 fail-safe |
| **M3** Health auto-degradation | VALID | 健康域指標 observability 標準；NORMAL→DEGRADED→CRITICAL ladder 對齊 SM-04 |
| **M4** Self-supervised hypothesis discovery | **QUESTIONABLE** | rolling cross-corr / event-window / clustering 在 24mo crypto 樣本 false discovery rate 預估 40-60%；DRAFT 階段不過濾 power < 0.5 = 噪音淹沒；ex-ante 過濾 minimum bar 未定義 |
| **M5** Online learning interface stub | VALID (stub) | Sprint 1A 8-12 hr interface reservation 無數學成本 |
| **M6** Bayesian reward weight tuning | **QUESTIONABLE** | 5D Bayesian opt 在 6mo data 樣本量不足；bounds [0.5, 5.0] Sharpe sensitivity 未驗；30%-change rollback 在 regime shift 期錯誤回滾 |
| **M7** Decay detection | VALID-WITH-CAVEAT | 30d Sharpe + envelope + counterfactual M11 多源確認可降誤判；但 "N consecutive losing > 2σ" 在 fat tail crypto 會 normal losing streak 誤觸發 |
| **M8** Anomaly detection | **QUESTIONABLE** | Hurst + **GARCH break = 黑名單觸發**；isolation forest base-rate 失衡偏差未提；Y1 read-only OK；Y2+ 主動觸發前必修 |
| **M9** A/B mSPRT framework | **QUESTIONABLE** | mSPRT 假設 i.i.d. — crypto fills 高自相關必違反；early stopping 偏差未修正；Bonferroni 損失 power 30-50% |
| **M10** Capital scaling Tier A-E | **QUESTIONABLE** | Tier C cointegration 60-90d 樣本不足；**Tier D "regime auto-classify" 隱伏 HMM / Markov-switching = QC 黑名單** |
| **M11** Continuous counterfactual replay | **QUESTIONABLE** | PnL/decision/slippage 3 個 threshold 純 ad-hoc；與 M7 30d Sharpe 信號重複 60-70% |
| **M12** Adaptive order routing stub | VALID (stub) | Sprint 1A 20-30 hr interface |
| **M13** Multi-venue stub | VALID (stub) | AssetClass + Venue enum 工程抽象 |

## 1. Top 3 執行性風險

### Risk 1：M10 Tier D「regime auto-classify」未指明模型，隱伏 HMM 黑名單
- **位置**：v5.8 §2 M10 Tier D
- **問題**：「auto-classify market regime」最常見實作 = HMM / Markov-switching；本 skill 黑名單已寫：HMM (hidden state non-identifiability + crypto regime shift 太快) / GARCH (normality 假設失效)
- **替代**：ATR-quantile-based vol regime + Funding rate state + BTC dominance regime
- **must-fix**：M10 Tier D ADR 必明寫 "no HMM / Markov-switching / GARCH"；基底 = ATR vol regime + funding state 雙 axis 矩陣

### Risk 2：M4 self-supervised pattern miner false discovery rate 未控制
- **位置**：v5.8 §2 M4
- **問題**：
  1. Rolling cross-correlation 100 feature × 5 forward = 500 hypothesis；α=0.05 naive 期望 25 false positives；Bonferroni/FDR 未提
  2. Event-window N<30 → t-test power < 0.5
  3. Clustering K 選擇未提；K=3 vs K=5 結果差
  4. DRAFT auto-surface 不過濾 → operator inbox 飽和
  5. Replication crisis：M4 surface 多半已 published（Harvey-Liu-Zhu 2016 ~50% factor 不能 replicate）
- **must-fix**：DRAFT minimum bar：N ≥ 30、p < 0.05/K Bonferroni、effect size ≥ 0.2、6mo sub-period stability；ex-ante graveyard filter（SSRN / Harvey-Liu-Zhu / McLean-Pontiff 命中標記 publication decay risk: HIGH）；Cluster K 選擇 5-fold CV silhouette

### Risk 3：M11 ad-hoc divergence thresholds + 與 M7 信號重複
- **位置**：v5.8 §2 M11
- **問題**：
  1. 3 個 threshold 純 ad-hoc，無 statistical justification
  2. 與 M7 30d Sharpe + counterfactual baseline 信號重複 60-70%；2 個 trigger 同時 fire = alert fatigue
  3. 30d Sharpe in crypto SNR 不足；Bailey-Lopez de Prado PSR 校正前不可單獨用作 decay trigger
- **must-fix**：M11 ADR 明寫 3 個 threshold statistical derivation（noise floor empirical + 2.5σ-3σ）；M11 daily divergence event 應 input 給 M7 multi-source confirmation，**不**獨立 demote；M7 為 single decision authority；M7 decay trigger 不單用 30d Sharpe，必並用 PSR(0) ≥ 0.95 lost + counterfactual divergence + N consecutive losing > 3σ

## 2. Replication crisis check（13 module 是否引入已 priced-in alpha）

- **M4 pattern miner**：HIGH 風險引入已 priced-in alpha
  - Rolling cross-correlation 已是學術 / KOL / 量化基金共同檢查標的 → published alpha 全網皆知
  - Event-window FOMC / unlock / cascade — 都是已公開 anomaly
- **M6 Bayesian reward**：LOW 風險 — internal portfolio config
- **M10 Tier C-D**：MID 風險
  - Tier C cointegration → crypto pair 隨 LUNA / FTX 後 break
  - Tier D regime → 若用 HMM 必違 graveyard + 黑名單
- **M9 A/B mSPRT**：N/A — A/B framework 是 method
- **M11 counterfactual replay**：N/A — validation tool

**結論**：v5.8 13 module 主要是 governance / autonomy infra；M4 唯一引入 alpha discovery 的 module，必走完整 graveyard filter

## 3. Blacklist method check（per math-model-audit skill）

| 黑名單方法 | v5.8 隱伏命中 | 處置 |
|---|---|---|
| **HMM regime detection** | M10 Tier D — HIGH 風險 | M10 ADR 必明寫 "no HMM / Markov-switching"；替代 = ATR-vol regime + funding state |
| **GARCH 家族** | M8 "GARCH break" — HIGH 風險 | M8 ADR 移除 GARCH；替代 = realized vol + block bootstrap |
| **VPIN** | 無命中 | OK |
| **波動率均值回歸（單獨）** | 無命中 | OK |
| **獨立 Donchian** | 無命中 | OK |

**M4 隱伏黑名單觸碰風險**：rolling cross-correlation 本身非黑名單，但若 IMPL 採 "rolling N max" 等 look-ahead bias = 必 mean-revert false signal。M4 DESIGN ADR 必明寫所有 rolling stat 強制 shift(1) leak-free

## 4. 樣本量 / power 分析

**M4 pattern miner**：
- 24mo crypto data + 5 forward × 100 feature = 500 hypothesis
- Bonferroni α/K = 0.0001 → 要求 t-stat > 3.9 → 多數 feature 不過 → DRAFT 數量驟降 → operator inbox sane
- Event-window class：FOMC N≈24 / unlock N≈30 / cascade N≈8 / funding flip 不定。**N<30 class 必標 "insufficient sample, archive不 surface"**

**M9 A/B mSPRT**：
- mSPRT 對 i.i.d. — crypto fills 自相關必違反；解 = block bootstrap-corrected mSPRT
- early stopping bias：alpha-spending function 必納；naive early stop 高估 effect size 20-40%
- 多 A/B 並行：建議用 BH (FDR=0.10) 而非 Bonferroni 留 power

**M6 Bayesian reward 5D opt**：
- 6mo ÷ 30d monthly tune = 6 iter 不足；GP-based Bayesian 建議 ≥ 50-100 iter
- 解：合併 12mo data；或降維（fix λ_decay first，4D opt）
- λ_tail 在 fat tail crypto 應 [1.0, 10.0]

**M11 nightly divergence**：
- Noise floor：5d backtest replay → empirical divergence distribution；σ_noise = X bps；trigger = 2.5σ
- N for noise floor 千級 sample OK
- 2.5σ daily FPR ≈ 1.2%；30d 累積 36% — **HIGH** → 降至 3σ (0.27%/day → 8%/30d) 或 multi-day confirmation

## 5. 對 PA+FA+PM 匯總必收 top 3

1. **M10 Tier D 黑名單 hardening (Risk 1)**：ADR 明寫 "no HMM"；Sprint 1A-γ 30-50 hr 內 absorb，不增工時
2. **M4 DRAFT minimum bar + ex-ante graveyard filter (Risk 2)**：6 條規範；Sprint 1A 30-50 hr + M4 IMPL Sprint 2-3 +20-30 hr filter logic
3. **M11 divergence threshold statistical derivation + M7 dedup (Risk 3)**：M11 daily threshold 必走 statistical derivation；M7 single authority on demote

## 6. v5.8 派發前 must-fix

1. **M10 Tier D ADR text-fix**：blacklist HMM/GARCH/Markov-switching；替代 = ATR-vol + funding state matrix
2. **M8 ADR-0036 GARCH 移除**：Hurst leak-free shift(1) + Bonferroni K=N corrected；GARCH break 替換為 realized vol break + block bootstrap
3. **M4 minimum bar 規範**：DRAFT 必附 6 attribute（N / Bonferroni p / effect size / sub-period / graveyard flag / cluster K silhouette）
4. **M11 divergence threshold + M7 dedup 規範**：M11 statistical derivation；M11 為 M7 input 非 independent demote

## 7. Sprint 1A-β-ε 期間 should-fix

1. M6 Bayesian opt 樣本不足 buffer：Sprint 1A-β M6 設計時必加 "Sprint 7 IMPL 前累積 ≥ 9mo reward outcome data"
2. M9 mSPRT 自相關修正：block bootstrap-corrected mSPRT 或 cluster-robust adaptation
3. M7 N consecutive losing > 2σ → > 3σ：crypto fat tail
4. M4 cluster K SOP：5-fold CV silhouette + K [2, 10]
5. M11 daily replay 2.5σ → 3σ 或 multi-day confirmation
6. M10 Tier C cointegration sample requirement：≥ 90d hourly + ≥ 30d daily
7. M2 overlay auto-disable Sharpe<0 補 PSR(0) < 0.5：純 Sharpe<0 易誤觸發

---

**END v5.8 QC Audit**
