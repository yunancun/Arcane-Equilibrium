---
name: Position Sizing 偏好（含 2026-05-11 SSOT drift 修正）
description: 用戶對交易倉位大小和智能資本管理的偏好設定；含 SSOT TOML vs 設計意圖的 drift 註記
type: feedback
originSessionId: 94355942-947a-4f2e-b6ed-f1ea1ed16910
---
## ⚠️ 重要：設計意圖 vs SSOT TOML（2026-05-11 QC drift 修正）

| 環境 | 設計意圖（歷史 memory）| TOML SSOT（當前 risk_config_*.toml）|
|---|---|---|
| paper | 3.0% | **per_trade_risk_pct = 0.20**（0.20%）|
| demo | 3.0% | **per_trade_risk_pct = 0.10**（0.10%）|
| live | 3.0% | **per_trade_risk_pct = 0.05**（0.05%）|

**Drift 倍率 = 15-60×**。實際運行系統按 SSOT TOML 0.05-0.20% 計算 sizing — 與設計意圖 3% 嚴重不一致。

**判斷準則（per QC 2026-05-11 audit）**：
- **當前 5 textbook 策略 7d EV<0**（demo -17.82 bps）→ TOML 0.05-0.20% 是**正確 fail-closed 保守**，不可動
- 升 TOML → 3% 在 EV<0 下 = **每 trade 虧損放大 15-60×**（數學常數）
- 待 alpha 修好（PA R-1/R-2/R-3 + W-AUDIT-8a Phase B/C/D + A 群 alpha 候選）後，**可考慮**逐步升回 3% 設計意圖
- ETA = 12-17 sprint（3-4 個月）

**OPERATOR / Agent 守則**：
- 任何提案需先明確說明欲調哪一層（design intent vs SSOT）
- 不要看見 memory「3%」就直接套到 TOML / 業務邏輯
- 信 config，不信 memory（per `math-model-audit` S1 風控數字 SSOT 守則）
- 若有人提「修 memory 對齊 TOML」= 反向同樣錯（設計意圖也有價值）

## 設計意圖（保留作未來目標）

用戶偏好每筆交易最大虧損 = 總額的 3%，同時部署最多 25 個幣種。

**Why:** 之前 risk_per_trade_pct=1-2% 加上除以 active_count，導致每筆只有 ~$20 名義，手續費吃掉所有利潤。設計意圖是讓 sizing 與機會匹配。

**How to apply (when alpha allows)**:
- risk_per_trade_pct = 3.0（max loss per trade as % of balance）
- max_symbols = 25
- qty 必須動態計算（每次下單時根據當前餘額重算，不在啟動時鎖死）
- 用戶希望 AI 能自動做資本再分配：當餘額不足但有好機會時，自動關閉低潛力盈利單或無望虧損單以投入新機會
- 用戶不希望設太多硬限制，偏好 Agent 根據市場狀況自主判斷

## 當前運行 sizing（fail-closed protective）

- paper: `per_trade_risk_pct = 0.20`，`position_size_max_pct = 50.0`
- demo: `per_trade_risk_pct = 0.10`，`position_size_max_pct = 25.0`
- live: `per_trade_risk_pct = 0.05`，`position_size_max_pct = 15.0`

## 為何當前盈利「超微利潤」

5 個 root cause（QC 2026-05-11 audit）：
1. **Alpha 結構性缺失（~60%）** — 5 textbook 策略 post-publication decay
2. **Account size × 0.1% TOML 物理上限（~20%）** — $591 × 0.1% = $0.59/trade
3. **Fee drag（~10%）** — 10.4% taker remnant + PostOnly missed-trade
4. **Signal target tight 設計（~5%）** — grid 22bps / bb 1-2σ / ma sub-1ATR
5. **Slippage + queue position adverse selection（~5%）**

放大 sizing 不解決 root cause 1+3+5。先修 alpha 才能談 size。
