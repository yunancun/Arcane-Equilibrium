---
name: crypto-microstructure-knowledge
description: QC agent 主用：評估涉 funding/basis/liquidation 的策略、執行成本/fee 爭議、套利提案時讀；BB 涉微結構時 cross-ref（政策面歸 bybit-policy-compliance）。
allowed-tools: Read, Grep, Glob, WebSearch
---

# Crypto Microstructure Knowledge（Crypto 微結構手冊）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：funding / liquidation / ADL / basis / term structure / TWAP-VWAP 執行算法 / market impact 模型等機制通識不在本檔重述；本檔只列本專案的偏離、判準與 SSOT 指針。

> **S6 P0/P1/P2 cross-ref**：三層風控定義見 `srv/docs/decisions/EX-01_..._V2.md` §2.1-§2.3；本 skill 引用屬語意重述。

## 何時觸發

- QC 評估涉 funding / basis / liquidation 動態的策略
- 執行成本爭議（PostOnly vs IOC、maker rebate、tier-based fee）
- 跨所套利 / 期現套利 / 三角套利提案
- BB 審計新 endpoint 跟 Bybit 微結構交集場景
- OpenClaw `funding_arb` 重評（歷史 G-2 結案 negative 後；當前狀態查 `TODO.md` / reports）

## 1. Funding Rate — Bybit 專案判準

- **結算週期 per-symbol**：`fundingInterval` 因 symbol 而異（1h / 4h / 8h 不等）；**不可假設普適 8h cycle**，以 `instruments-info` 即時查
- **funding cap/floor per-symbol**：`upperFundingRate` / `lowerFundingRate`（`instruments-info` 即時查），不是固定 clamp 值；cap 誤判教訓與公式正本見 `quant-strategy-design` funding 專段（2026-05-31 ERRATUM）
- 取數：REST `/v5/market/funding/history`；WS `tickers` topic `fundingRate` + `nextFundingTime`；endpoint 對照 `docs/references/2026-04-04--bybit_api_reference.md`
- **Funding arb 設計前必排查**：①「F 極端會 mean revert」在當前樣本期是否真實（n<30 結論 noisy）②兩腿 fee + slippage 是否吃掉 F 收益 ③spot 借貸成本已計入 ④settlement instant 前後 ≤5 min 高波動的跨倉風險。OpenClaw 過往 funding_arb 實驗結論查 `TODO.md` / reports + git log，**不引本 skill 內過期數字**

## 2. Liquidation Cascade — OpenClaw 判準

- **OpenClaw 警覺**：1m 突破策略在 cascade 中容易誤判為 trend；P1-16 HALT-SESSION CROSS-SYMBOL 已部分修護
- Cascade 進行中信號：OI 急降、funding 翻號、Bybit WS `allLiquidation` feed、spread 從 ~0.01% 跳 ~0.5%+
- **防禦設計對齊 EX-01 §6.2 + RiskConfig**——所有風控數值以 `settings/risk_control_rules/risk_config_<env>.toml` 為 SSOT（具體值 sub-agent 必跑命令拿，本 skill 不寫死）：
  - Single-position cap ↔ `[limits].position_size_max_pct`；相關曝險上限 ↔ `[limits].correlated_exposure_max_pct`；Leverage ↔ `[limits].leverage_max`（EX-01 §3 Guardian 動態收縮）
  - **Reserve buffer 是 reserve 不是 cap**：「N% 不投資」而非「倉位上限 N%」；具體 N 讀 EX-01 §6.2 + RiskConfig
  - Per-trade risk ↔ `[limits].per_trade_risk_pct`；memory 內任何「X% per trade」與 config 衝突 → **信 config，不信 memory**
  - Stop loss：必設交易所側（DOC-01 §5.9 雙重防線）+ 本地 tick() 隱身（EX-01 §4.2）
  - Funding settlement 前 N min 不開新倉（建議 default，strategy 可 override，**非 hard rule**）
  - Risk Governor 狀態觸發：見 SM-04 §3-§9（6 states），不是 % threshold

## 3. Basis / Cross-Exchange — 專案邊界

- **Bybit demo 沒有 spot lending** → cash-and-carry 對 OpenClaw demo 是 dead
- **OpenClaw 不接 cross-CEX**：`CLAUDE.md` Product Boundary「Bybit 為唯一交易所」，跨所策略 out of scope
- CEX↔DEX：MEV bot 主導，個人策略打不過（awareness only）

## 4. Execution — 專案判準

- Fee 真值：API `/v5/account/fee-rate` 或字典手冊 `docs/references/2026-04-04--bybit_api_reference.md`；官方 fee schedule 動態變動（BB 可 WebFetch），本檔不寫死數字
- **PostOnly 部署評估**：Demo / paper / live 三環境 PostOnly 配置以 RiskConfig TOML `[agent].post_only_limit` 為 SSOT（收盤 maker 路徑另見 `[close_maker_backoff]`）；當前部署狀態查 git log + TOML 實值，**本 skill 不寫死部署狀態**
- **Maker fill rate 建議起點 ≥ 60%（非治理硬規範）**：低於此值 PostOnly 反而吃 missed-trade opportunity cost；具體閾值依 strategy 進場頻率 + edge size 動態調整，由 QC 提替代
- OpenClaw 當前單筆 size 小，MARKET 一拳搞定，TWAP/VWAP 暫不必要。**警告**：未來 portfolio scale 上 → 必須切片，否則 market impact 吃掉 edge（crypto 流動性差於 equity，同 size impact 大 5-10x）
- Bybit 各 symbol tick size 不同，影響 maker rebate 策略；iceberg 在 crypto 無 reg 限制 → 常見。**spoofing 屬市場操縱，本專案禁止且 BB 合規審查必拒**（分類正本 `bybit-policy-compliance`）；本 skill 只涉 spoofing **偵測**（他人操縱行為的防禦性識別），不得作為執行手法

## 5. Bybit Specific 機制（與 `bybit-policy-compliance` 互補）

UTA vs Standard margin 不同；Cross vs Isolated 同帳戶可混用；Hedge mode 同 symbol 雙向（OpenClaw 暫不開）；Reduce-only flag 避免方向偏移；Risk limit tier（size 越大 MMR 越嚴）；Auto-margin 動態 vs 手動。

## 6. 穩定平台結構 rule（不會 drift）

Bybit 為唯一交易所（`CLAUDE.md` Product Boundary；cross-CEX 策略 out of scope）；Bybit demo 不支援 spot lending（cash-and-carry 在 demo 不可行）；funding settlement 前後高波動是 perp 結構性現象（不是 OpenClaw 特有）。

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
（risk_config TOML `[cost_edge]` 段：≥ 0.8 建議關倉）

## 結論
Approve / Conditional（修 X）/ Reject
```
