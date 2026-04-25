---
name: crypto-microstructure-knowledge
description: Crypto perpetual / spot 微結構知識手冊 — Funding rate 動態、Liquidation cascade、Basis trading、Cross-CEX & CEX↔DEX 套利、Perpetual term structure、Execution optimization (TWAP/VWAP/Implementation Shortfall)、PostOnly/IOC fee 計算。QC + BB agent 合用。
allowed-tools: Read, Grep, Glob, WebSearch
---

# Crypto Microstructure Knowledge（Crypto 微結構手冊）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

> **S6 P0/P1/P2 cross-ref**：三層風控定義見 `srv/docs/decisions/EX-01_..._V2.md` §2.1-§2.3；本 skill 引用屬語意重述。

## 何時觸發

- QC 評估涉 funding / basis / liquidation 動態的策略
- 執行成本爭議（PostOnly vs IOC、maker rebate、tier-based fee）
- 跨所套利 / 期現套利 / 三角套利提案
- BB 審計新 endpoint 跟 Bybit 微結構交集場景
- OpenClaw `funding_arb` 重評（CLAUDE.md §三 G-2 結案 negative 後）

## 1. Funding Rate 動態

### 1.1 結算機制
- **Bybit 8h cycle**：00:00 / 08:00 / 16:00 UTC，整點 snapshot
- **計算公式**（簡化）：`F = clamp(premium_index + interest_rate, -0.75%, 0.75%)`
- **方向**：F > 0 → long 付 short；F < 0 → short 付 long
- **應用 / 收取時**：持倉跨越 settlement instant 才算

### 1.2 結構性來源（為何不歸零）
- **Long-bias market**（牛市）：spot 買盤強 + perp 槓桿多 → premium > 0 → F > 0 持續
- **Short-squeeze**：強烈 short interest + 拉升 → F 急劇翻負
- **Listing pump**：新幣列入 perp 後 24h 多為極端 funding（兩個方向都可能）

### 1.3 Funding arb 設計要點
- **Carry trade**：long spot + short perp → 賺 F > 0 的 funding；要求 ｜F｜ > 借幣成本 + 兩腿 fee
- **Spread harvest**：F 極端時反向倉位賺 mean revert
- **OpenClaw G-2 funding_arb 結案 negative 教訓**：v2 n=13 提前結案 -36.76 bps / 0 勝率（memory `project_g2_funding_arb_monitor.md`）— **再做前必排查**：
  1. 假設「F 極端會 mean revert」是否真實（13 樣本太少結論 noisy）
  2. 兩腿 fee + slippage 是否吃掉 F 收益
  3. spot 借貸成本是否已計入

### 1.4 Bybit funding 取數
- REST `/v5/market/funding/history`：歷史 F
- WS `tickers` topic：`fundingRate` + `nextFundingTime`
- BB 確認 endpoint 跟 OpenClaw `bybit_api_reference.md` 一致

## 2. Liquidation Cascade & ADL

### 2.1 Liquidation 觸發
- **MMR (Maintenance Margin Ratio)**：倉位 margin / position value < MMR → liquidation
- **Insurance Fund 接管**：清算單先進 IF
- **ADL (Auto-Deleveraging)**：IF 不足時對手側獲利倉強行平倉

### 2.2 Cascade 動態
- **Long squeeze**：價跌 → long liquidation → 賣壓加劇 → 更多 long liq → 更多賣壓 ...
- 在 thin orderbook 下幾分鐘可洗 -10% 到 -30%（2020-03-12、2021-05-19、2022-06 LUNA、2022-11 FTX）
- **OpenClaw 警覺**：1m 突破策略在 cascade 中容易誤判為 trend；P1-16 HALT-SESSION CROSS-SYMBOL 已部分修護

### 2.3 信號
- **Open Interest 急降**：cascade 進行中
- **Funding rate 翻負**（long squeeze）/ 翻正（short squeeze）
- **Liquidation feed**（Bybit WS `allLiquidation`）：實時清算事件
- **Spread 爆**：bid-ask 從 ~0.01% 跳到 ~0.5%+

### 2.4 防禦設計（對齊 EX-01 §6.2 + RiskConfig）

**所有風控數值以 `settings/risk_control_rules/risk_config_<env>.toml` 為 SSOT**；以下為 EX-01 §6.2（`srv/docs/decisions/EX-01_..._V2.md`）+ 治理框架：

- **Single-position cap**：P1 = 20% of equity；具體值讀 RiskConfig `[limits].position_size_max_pct`（base 15% / demo 25%）
- **Sector allocation cap**：P2 adaptive = 40%；對應 RiskConfig `[limits].correlated_exposure_max_pct = 60%`
- **Reserve buffer**（注意：是 reserve **不是** cap）：最少 30% of equity 不分配（margin calls + opportunities）— **不是「倉位上限 30%」，而是「30% 不投資」**
- **Per-trade risk**：讀 RiskConfig `[limits].per_trade_risk_pct`（base 0.1%）；memory `feedback_position_sizing` 寫的「3% per trade」與 config 衝突 → **信 config，不信 memory**
- **Stop loss**：必設交易所側（DOC-01 §5.9 雙重防線）+ 本地 tick() 隱身（EX-01 §4.2）
- **Funding settlement**：不在前 5 min 開新倉（建議 default，可由 strategy override，**非 hard rule**）
- **Leverage**：讀 RiskConfig `[limits].leverage_max`（base 9.9× / demo 50×）；EX-01 §3 Guardian 動態收縮
- **Risk Governor 狀態觸發**：見 SM-04 §3-§9（NORMAL / CAUTIOUS / REDUCED / DEFENSIVE / CIRCUIT_BREAKER / MANUAL_REVIEW），不是 % threshold

## 3. Basis Trading & Cross-Exchange Arb

### 3.1 Basis = Perp – Spot
- **Contango**：perp > spot（牛市常態）
- **Backwardation**：perp < spot（極端恐慌）
- **Cash-and-carry**：long spot + short perp 賺 basis converge to 0 + funding

### 3.2 期現套利約束
- 兩腿同時成交（leg risk）
- spot 借貸成本（如做空 spot）
- 清算風險（perp 腿被清算 spot 腿裸露）
- Bybit demo 沒有 spot lending → 對 OpenClaw 是 dead

### 3.3 Cross-CEX
- **延遲套利**：A 所先 react 訊息，B 所慢 → 但 HFT 早佔，個人玩家不接
- **規模套利**：A 所大單 impact 高 → B 所同價未動 → 反向倉位
- **OpenClaw 不接 cross-CEX**：CLAUDE.md §一 「Bybit 為唯一交易所」，跨所策略 out of scope

### 3.4 CEX↔DEX (僅作 awareness)
- DEX 滑點高 + gas 不確定 → 個人套利門檻高
- MEV bot 主導 — 普通策略打不過

## 4. Perpetual Term Structure

### 4.1 Perp vs Spot premium curve
- 1m / 1h / 1d basis 變動可建模（mean-revert 假設）
- crypto 有 perp、quarterly、bi-quarterly 期貨（Bybit 都有）
- 期貨之間 calendar spread 可交易（OpenClaw 暫不做）

### 4.2 Funding rate 期限結構
- Short-term funding 跳動劇 → mean-revert
- Long-term funding 趨向結構性水準

## 5. Execution Optimization

### 5.1 Order types & fee implications

| Order type | Fee 分類 | OpenClaw 適用 |
|---|---|---|
| **IOC market** | Taker fee（高）| EDGE-P2-3 前 default，drag 大 |
| **PostOnly limit** | Maker fee（rebate）| EDGE-P2-3 部署後 demo/paper=true |
| **GTC limit** | Maker（成）/ Taker（cross spread）| 不主動 cross 即 maker |
| **Reduce-only** | 同上 | 平倉用，避免反向開倉 |

**Bybit fee tier**（spot/derivatives 各別；**reference snapshot，verify 以 Bybit 官方 fee schedule 為準**）：
- Tier 0：0.10% taker / 0.10% maker
- Tier 1+：volume tier 越高 maker rebate 越多
- VIP rebate 最高可達 −0.0050%（rebate）

> 真實當前 fee：登入 Bybit account → API 查 `/v5/account/fee-rate` 或字典手冊 `docs/references/2026-04-04--bybit_api_reference.md`

**OpenClaw EDGE-P2-3 PostOnly 部署細節**：
- Demo / paper=true（已 2026-04-21 部署）
- Live=false（CLAUDE.md memory `project_track_p_runtime_live` 教訓：PostOnly 配置反向是 G1-05 fix 範疇）
- 預期 fee 從 ~6.5 bps/side 降至 ~1 bps/side（drag 降 5.5 bps）
- Maker fill rate 至少 ≥ 60% 才算成功

### 5.2 Execution benchmark

| 算法 | 公式 / 概念 | 何時用 |
|---|---|---|
| **TWAP** | uniform 切片下單 | 流動性穩定、無 alpha decay |
| **VWAP** | 按歷史 volume 分布切片 | 有 volume 預期，常規大單 |
| **Implementation Shortfall (Almgren-Chriss)** | 平衡 market impact 和 timing risk | 有 alpha 衰減的單 |
| **POV (Percentage of Volume)** | 跟隨即時 volume 一定比例 | 動態流動性 |

OpenClaw 當前單筆 size 小（3% risk），MARKET 一拳搞定，TWAP/VWAP 暫不必要。**警告**：未來若 portfolio scale 上 → 必須切片，否則 market impact 吃掉 edge。

### 5.3 Market Impact 模型
- **Linear impact**：`Δprice = λ · size`，small order
- **Square-root impact (Almgren-Chriss)**：`Δprice = η · σ · sqrt(size / V_daily)`，large order
- crypto 流動性差於 equity，impact 比 equity 同 size 大 5-10x

### 5.4 Order Book Dynamics
- **Queue position**：limit order 在 same price level 的排隊位次決定 fill 優先序
- **Spoofing detection**：大單放又撤是 manipulation，crypto 沒有 reg 限制 → 常見
- **Iceberg detection**：表面小單實則大單，看 trade size 跟 quote size mismatch
- **Tick size discovery**：Bybit 各 symbol tick size 不同，影響 maker rebate 策略

## 6. Bybit Specific 機制（與 BB skill `bybit-policy-compliance` 互補）

- **UTA (Unified Trading Account)** vs Standard Account margin 不同
- **Cross vs Isolated margin**：同帳戶可混用（isolated 配置策略獨立風險）
- **Hedge mode**：同 symbol 同時 long + short 開倉（OpenClaw 暫不開）
- **Reduce-only flag**：避免方向偏移意外
- **Risk limit tier**：position size 越大 MMR 要求越嚴
- **Auto-margin**：保持 margin 動態調整 vs 手動

## 7. OpenClaw 特定核心

- **funding_arb dead**：G-2 v2 n=13 結案 negative；待 R-02 Strategist 重評三參數（memory `project_g2_funding_arb_monitor.md`）
- **PostOnly EDGE-P2-3**：demo/paper=true 已部署，Live 配置反向是 G1-05 todo（memory `project_2026_04_24_todo_refactor`）
- **Bybit 為唯一交易所**：CLAUDE.md §一；cross-CEX 策略 out of scope
- **demo lacks spot lending**：cash-and-carry 在 demo 不可行，cancel
- **fee tier 起步**：Tier 0 預設，需累積 volume 升 tier；策略設計不能假設 VIP rebate
- **liquidation cascade 時段警覺**：funding settlement 前 5 min + 整點 / 半點 高波動

## 反模式（見即 Reject）

- 策略假設「funding rate 永遠 mean revert」（13 樣本就結論）
- 把 spot lending 進 demo 模型（不存在）
- 設計大單 MARKET 執行（market impact 未估）
- PostOnly 但沒驗 maker fill rate（反而錯過機會 net loss）
- 跨所策略提案（OpenClaw 只接 Bybit）
- 沒考慮 funding settlement 5 min 前後高波動
- liquidation cascade 中 trend follow（會被洗）
- 假設 fee = 0 的 PnL chart

## 輸出格式（執行成本評估範本）

```markdown
# Execution Cost Audit — <strategy> · <date>

## Order type 分布
| Type | Pct | Fee/side |
| IOC market | X% | Y bps |
| PostOnly | X% | Y bps |

## Maker fill rate
（PostOnly 提交數 / 成交數，目標 ≥ 60%）

## Market impact 估計
size: X / V_daily: Y → impact ≈ Z bps

## Funding cost（如倉位 cross settlement）
持倉時數 × F_avg = X bps

## Total cost / side
fee + slippage + impact + funding = Y bps

## cost_edge_ratio
edge: P bps，cost: Q bps，ratio: Q/P
（CLAUDE.md §二 原則 13：≥ 0.8 建議關倉）

## 結論
Approve / Conditional（修 X）/ Reject
```
