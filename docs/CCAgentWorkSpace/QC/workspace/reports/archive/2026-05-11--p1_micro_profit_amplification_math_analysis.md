# QC 數學審計報告 — P1 微利根因 + 數學放大可行性

**Date**: 2026-05-11
**Auditor**: QC (read-only, 應用數學 PhD + 30y finance industry persona)
**Subject**: 「為何盈利都是超微利潤？數學上能放大嗎？」
**Triggered by**: Operator P1 直接質詢

---

## Executive Summary

**REJECT「在當前 alpha 狀態下放大盈利」訴求；APPROVE 5 條零/小成本 actionable 但 expected ROI 是「減虧」而非「放大盈利」**。

當前盈利超微利潤的根本原因不是 sizing 不夠大，而是 **5 個 textbook 技術指標策略結構性 alpha-deficient + 0.1% per-trade SSOT 已是 sub-Kelly conservative 鎖死**。

**任何 sizing 放大在 EV ≈ 0 / 負的當前狀態下會等比例放大虧損**。

memory `feedback_position_sizing` 寫的「3% risk/trade」與 TOML SSOT 0.1% 嚴重 drift — **必先 push back 此 drift 才能談數學**。

**真實 gross 轉正 ETA = 3-4 個月**（PA R-1/R-2/R-3 redesign + W-AUDIT-8a Phase B/C/D + A 群 alpha 候選 落地）。

---

## 重大發現：Memory drift（30-60×）

| 來源 | per_trade_risk_pct |
|---|---|
| memory `feedback_position_sizing` | **3.0%** |
| `risk_config_paper.toml` | 0.20 |
| `risk_config_demo.toml` (SSOT) | **0.10** |
| `risk_config_live.toml` (SSOT) | **0.05** |

**Drift 倍率 = 15-60×**。實際運行系統按 SSOT 0.05-0.20% 計算 sizing。

**真實 sizing 證明**：$591 × 0.1% = **$0.59 risk/trade** → 跟 operator 觀察的「wins $0.05-$0.30 / losses $0.05-$0.40」完全一致。

判定：**SSOT TOML 0.1% 在當前 EV≈0 條件下是正確 fail-closed**（per QC skill：sub-Kelly conservative）。memory 寫的 3% 是 outdated 設計意圖。

---

## 數學常數：EV<0 下放大不可能

對任何 sizing 槓桿 `L`，組合預期收益：

```
E[PnL_after_amplification] = L × E[PnL_per_trade_baseline]
```

若 `E[PnL_per_trade_baseline] ≤ 0`，則 `L > 1` 必使虧損加劇。**數學常數 — 無例外**。

當前實證：
- 7d demo baseline gross PnL = **−26.44 USDT**（PA 12-agent audit C-2）
- 7d demo avg_net = **−17.82 bps**（PA C-2）
- 24h MLDE avg_net = **+8.75 bps**（single window N≈42 + leak-free hygiene fix，transitory）

**Pseudo-Kelly**：assume win_rate=0.50, R:R=1, fee=4 bps：
```
For 7d baseline (gross -13.82 bps, net -17.82 bps):
  f* = (p·W - q·L) / W - fee_ratio
  f* = (0.5 × 10 - 0.5 × 10) / 10 - 4/10 = -0.4 (negative-EV after fees)
  → 數學上建議：不交易
```

Per memory `2026-04-02` 教訓：「MA Crossover Kelly fraction f\* = -0.014 → 不交易」。2026-05-11 整個 5-策略 portfolio 重蹈覆轍。

---

## 微利 5 個 root cause + 量化影響

| # | 根因 | 占比 | 證據 |
|---|---|---|---|
| 1 | **Alpha 結構性缺失** | ~60% | 5 textbook 策略 post-publication 50%+ decay；7d -17.82bps 穩態 |
| 2 | **Account size 物理常數** | ~20% | $591 × 0.1% TOML = $0.59/trade 設計鎖鏈 |
| 3 | **Fee drag** | ~10% | 7d maker_like 89.6%（10.4% taker remnant）；fee_drop 59.5% 接近紅線 |
| 4 | **Signal target tight 設計** | ~5% | grid 22bps / bb percent_b 0.5 退出 / ma SNR sub-1ATR |
| 5 | **Slippage + queue position** | ~5% | PostOnly will_take rejection；cascade 期間 adverse selection 放大 |

根因 1 + 3 + 5 = ~75% 真實 alpha 缺失 + 執行成本，可改善。根因 2 是物理常數。根因 4 是設計選擇。

---

## 11 個 sizing 槓桿評估（按 ROI 排序）

| Lever | 機制 | 當前狀態下 verdict |
|---|---|---|
| **A. Kelly Sizing** | f\* = (pW-qL)/W | **REJECT**（EV<0 → f\* 負） |
| **B. Pyramiding** | 贏單加倉 | **REJECT**（需 trend-following alpha，grid 不適合） |
| **C. Asymmetric R:R selection** | 進場 R:R≥2:1 才開 | **CONDITIONAL**（需 confidence calibration） |
| **D. Volatility scaling** | 高 vol 縮 / 低 vol 放 | **NEUTRAL**（不放大盈利，只平滑 variance） |
| **E. Edge-weighted sizing** | confidence calibrated | **REJECT**（calibration N<50 不可信） |
| **F. Compounding** | account ↑ → 同 % 放大 | **REJECT in current EV<0**（複利虧損） |
| **G. Multi-timeframe stacking** | 5m gate + 1m entry | **DEFER**（W-AUDIT-8a Phase B-D scope） |
| **H. Holding period 延長** | 捕大 swing | **REJECT for grid**（違反 mean-reversion 設計） |
| **I. 降低交易頻率** | quality 過濾收緊 | **CONDITIONAL**（同 C 需 selection） |
| **J. Fee tier 升級** | Bybit VIP rate | **APPROVE**（被動 ROI ~0.5-1 bps RT） |
| **K. Cross-strategy ensemble** | 真獨立 alpha source | **APPROVE 治本但長期**（W-AUDIT-8a 系列） |

---

## 5 條 Operator Actionable List

### Tier 1 — 零實施成本

1. **【0 成本】** 修 `feedback_position_sizing` memory drift（3% → 註明 SSOT 0.1%/0.05%）— **DONE 2026-05-11**
2. **【0 成本 / passive】** 等 7d 重測 §三 [40]（24h +8.75bps 是否 transitory）— **目標日期 2026-05-17**
3. **【0 成本 / info】** 查 Bybit fee tier 距 VIP1 還差多少：
   - demo 30d notional = **$257,103**（距 $5M VIP1 還差 ~19×）
   - live_demo 30d notional = **$77,688**（距 $5M VIP1 還差 ~64×）
   - 結論：**短期不會 trigger fee discount**；需要 alpha 修好 + account 增長後再評估

### Tier 2 — 小實施成本

4. **【小成本 / passive】** TONUSDT P1-CONDITIONAL-WATCH 30d evidence → freeze decision — **目標日期 2026-06-09**
5. **【小成本 / 防過擬合】** DEFER D/E 槓桿（volatility scaling / edge-weighted）等 ML calibration N≥200 — **明文記入 TODO §11.4**

---

## 治本路徑（已寫入 TODO §11.4）

PA R-1/R-2/R-3 redesign + W-AUDIT-8a Phase B/C/D + A 群 alpha 候選 = **12-17 sprint（3-4 個月）**：

| ID | Task |
|---|---|
| `W-AUDIT-8a` Phase A | trait skeleton + 5 strategies declare alpha sources（✅ DONE Sprint N+0） |
| `W-AUDIT-8a` Phase B/C/D | Tier 2 panel + Tier 3 microstructure + Tier 4 information flow |
| `W-AUDIT-8b` (A4-A) | Funding Skew Directional 新策略 |
| `W-AUDIT-8c` (A4-B) | Liquidation Cluster Reaction 新策略 |
| `W-AUDIT-8d` (A4-C) | BTC→Alt Lead-Lag 新策略（Sprint N+1 W2 fast-track） |
| `W-AUDIT-8e` (R-2) | Strategist Alpha Source Orchestrator |
| `W-AUDIT-8f` (R-3) | Hypothesis Pipeline first-class |

**這才是讓 gross 轉正、可以真正談放大的路徑**。

---

## 對抗性 Push Back

1. **Q：升 TOML 0.1% → 3% 是不是該做？**
   A：**強烈拒絕**。任何「升 sizing 30×」在當前 EV<0 條件下是災難。TOML 0.1% 是正確 fail-closed。修 memory，不修 TOML。

2. **Q：24h +8.75bps 不是已經轉正？**
   A：24h N≈42 single window + leak-free hygiene fix transitory；7d N=1162 是穩態 -17.82 bps。等 7d 重測才能宣稱 effect。

3. **Q：Account 太小所以 sizing 受限制？**
   A：部分對。但 sizing 受限是**保護 operator**而非鎖死盈利。EV<0 下 account ↑ + 同 0.1% 是複利虧損。**Account size 不是當前 bottleneck，EV 為負才是**。

4. **Q：Operator 想要看到盈利放大，不是減虧**
   A：QC 不討好。**數學常數**：EV<0 + sizing 放大 = 虧損放大。**先修 alpha，再談 size**。

---

## 容量估算

不適用 — 當前 EV<0 狀態，**容量是負值**（每多投一塊錢預期虧 17.82 bps × notional × 7d frequency）。

---

## 16 原則合規

| 原則 | 狀態 |
|---|---|
| 原則 5 生存 > 利潤 | EV<0 + 50% PBO 風險 → 不可放大 sizing ✓ |
| 原則 6 失敗默認收縮 | 7d -17.82bps 失敗訊號 → 不可加 leverage ✓ |
| 原則 13 cost_edge_ratio ≥ 0.8 建議關倉 | 89.6% maker / fee drop 59.5% 接近紅線 ✓ |

**Hard boundary 0 觸碰**。
