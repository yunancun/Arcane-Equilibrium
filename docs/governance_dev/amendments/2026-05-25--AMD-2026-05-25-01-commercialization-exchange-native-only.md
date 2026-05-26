# AMD-2026-05-25-01 — Commercialization Boundary: Exchange-Native Only

Date: 2026-05-25
Status: **Proposed-pending-operator-confirm**
Operator Sign-off: 2026-05-25 directive — 「我們現在不考慮任何交易所提供功能外的商業化模式」
PM Sign-off: 本 draft；批准前 cascade 不執行

Supersedes:
- `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-04-v4.3-commercial-evidence-sprint.md` §1 Stream 2 (Monetization Demand Test 30% capacity) — 整段 retire
- `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-05-retract-stream-3-ip-sale.md` — extend scope from「IP sale only retract」to「all non-exchange-native commercialization retire」
- `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v4.4.md` D7 constraint (「NO content/subscription monetization」) — formalize as AMD-level governance（先前僅 execution-plan 文本提及，未 AMD 化）

Related:
- ADR-0030 Copy Trading Y1末 4-gate evidence (Bybit-native commercialization retain)
- ADR-0006 Bybit-only exchange + ADR-0033 Binance amendment (定義「交易所」範疇)
- ADR-0040 Multi-Venue Gate Spec (DEX/Hyperliquid 從 venue enum 根源拒絕)
- ADR-0031/0032 Bybit Earn governance (Bybit-native retain)

---

## 1. Status

**Proposed-pending-operator-confirm**

本 AMD 為商業化邊界正式 governance 化。Operator 2026-05-25 在 V1→V5.8 drift audit 過程中明示「不考慮任何交易所提供功能外的商業化模式」— 此 directive 補完 v4.4 D7 constraint 在 AMD-04/05 chain 的 governance gap。AMD-05 (2026-05-20) 僅 retract Stream 3 IP sale，未涵蓋 Stream 2 (Telegram subscription / Substack / Stripe pre-order) 與其他 v3 提案商業化路徑；本 AMD 將商業化邊界正式收緊為「交易所平台官方提供的方案」。

---

## 2. Context

### 2.1 商業化路徑歷史 chain

| AMD/v# | Stage | 商業化 scope |
|---|---|---|
| v3 lean-direct-alpha-v3 (5/20) §3+§4 | DRAFT proposal | Telegram subscription「玄衡 Signal」$39/$99；Substack newsletter；codebase sale $2-5k；signal feed integration / webhook；MEV/DEX 套利 |
| v4 dual-track-v4 (5/20) | Discontinued | Track-based attribution；商業化未 specified |
| AMD-2026-05-20-04 v4.3 commercial-evidence-sprint | Accepted | Stream 1 Technical 60% + Stream 2 Monetization Demand Test 30% + Stream 3 IP Sale 10%；Stream 2 含 Telegram bot + landing + Stripe pre-order + Substack/Beehiiv |
| AMD-2026-05-20-05 retract-stream-3-ip-sale | Accepted | Stream 3 IP Sale retract；Stream 1 70% + Stream 2 30%（**Stream 2 仍 active**）|
| v4.4 execution-plan §0 D7 constraint (5/20) | Execution-plan-level | 「NO content/subscription monetization」— 未 AMD 化 |
| v5.0-v5.6 (5/20-5/21) | v5 lineage | 5 candidates portfolio + Bybit Copy Trading；implicit 不再 push Stream 2 |
| v5.7 + v5.8 active (5/20-5/21) | dispatch-of-record + autonomy supplement | ADR-0030 Bybit Copy Trading evidence-gated；Stream 2 demand test 完全 0 mention |

**Governance gap**：AMD-05 only retract Stream 3；v4.4 D7 constraint 未 AMD 化；v5.x 隱式不 push Stream 2 但無 explicit retire。本 AMD 補完 chain。

### 2.2 為什麼需要這個 AMD（Operator 2026-05-25 rationale）

Operator 在 V1→V5.8 drift audit 過程中（主會話 sub-agent 多路 verify 後）明示三個邏輯：

1. **聚焦交易效能 vs 分散精力**：Telegram bot / Substack newsletter / Stripe pre-order / landing page / codebase sale outreach 等需要 marketing + community building + customer support 等非交易能力，與 OpenClaw / 玄衡 「single product 完整 quant bot」(per AMD-2026-05-25-02 v5.5 reframe formalize) 定位衝突
2. **MEV/DEX 與 venue governance 對齊**：ADR-0040 Multi-Venue Gate Spec 已從 venue enum 根源拒絕 DEX/Hyperliquid；MEV 套利不在 venue scope，本 AMD 顯式統一
3. **平台官方方案具備 ToS / KYC / regulatory clarity**：Bybit Copy Trading / Master Trader / Earn / Competitions 是 Bybit 官方提供功能，operator 在 Bybit ToS 範圍內合法運作；非平台原生方案 (subscription / IP sale / signal service) 涉及單獨 ToS / 法律 / 報稅複雜性

### 2.3 v4.4 D7 constraint 在 execution-plan 文本提及未 AMD 化

`docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v4.4.md` §0 D7 constraint 寫「NO content/subscription monetization」但只在 execution-plan 級，不在 AMD 級 governance。本 AMD 正式 land 為 AMD-level，與 D7 constraint 對齊。

---

## 3. Decision 1 — Commercialization Scope Retire (顯式)

### 3.1 Retire list（全部正式 retire，不再 evaluate）

| # | 路徑 | 原 source | Retire reason |
|---|---|---|---|
| 1 | IP sale / codebase sale $2-5k | v3 §4 + AMD-04 Stream 3 | AMD-05 已 retract；本 AMD reaffirm 並擴 scope |
| 2 | Telegram subscription「玄衡 Signal」$39/$99 | v3 §3 + AMD-04 Stream 2 | Non-exchange-native；違 operator 2026-05-25 directive |
| 3 | Substack / Beehiiv newsletter | v3 §4 + AMD-04 Stream 2 | Non-exchange-native；marketing overhead 與 single product 定位衝突 |
| 4 | Signal feed integration / webhook | v3 §4 | Non-exchange-native |
| 5 | MEV / DEX arbitrage | v3 §4 | 違 ADR-0040 venue enum；DEX 從根源拒絕 |
| 6 | Stripe pre-order $1 refundable demand test | AMD-04 Stream 2 Monetization Demand Test | Non-exchange-native；marketing infrastructure |
| 7 | Cloudflare Pages + Astro landing for demand test | AMD-04 Stream 2 spec ~150 LOC | Non-exchange-native |
| 8 | Twitter / Discord outreach for IP sale | AMD-04 §3 (已 retract by AMD-05) | reaffirm retire |

### 3.2 Retain list（Bybit / Binance 平台官方提供）

| # | 路徑 | Source | Status |
|---|---|---|---|
| 1 | Bybit Copy Trading / Master Trader Cadet-Bronze-Silver-Gold tier ladder | ADR-0030 Y1末 4-gate evidence | Active per ADR-0030 |
| 2 | Bybit Earn cash management (dynamic APR + Guardian asset movement) | ADR-0031 framework + ADR-0032 Earn Guardian | Active per ADR-0031/0032 |
| 3 | Bybit competitions sporadic participation | v4.4 stream | Retain（Bybit-native event）|
| 4 | Binance Copy Trading equivalent (future) | conditional per ADR-0033 Binance trade enable Y3+ + ADR-0040 venue gate | Reserve Y3+ |
| 5 | Binance Earn equivalent (future) | conditional per ADR-0033/0040 | Reserve Y3+ |
| 6 | Prop firm (Breakout / HyroTrader / etc.) | v4.4 stream | **特例 retain**：prop firm 不是 marketing/subscription monetization 而是 trading capital 來源；雖非「交易所原生」但屬「trading capital channel」與本 AMD scope 不衝突 |

### 3.3 邊界 ambiguity resolve

**Q: Bybit / Binance 之外的平台（OKX / Coinbase / Kraken / 其他）的官方 Copy Trading / Earn 是否允許？**
**A**：受 ADR-0006 + ADR-0033 venue scope 限制 — Y1 Bybit primary / Binance market data only / Y3+ Binance trade enable conditional。其他平台不在當前 venue scope，**implicit retire**。如未來 evaluation 是否擴 venue，須走 ADR-0033/0040 amendment chain，不繞本 AMD。

**Q: Bybit referral link / affiliate commission 是否算商業化？**
**A**：本 AMD 不顯式 scope，但 referral / affiliate 是 Bybit 官方提供的回饋 channel（trading volume rebate / VIP tier），與 trading 直接相關，**implicit retain**。Future 如有 operator decision 走 referral 推廣，須在 AMD-25-01 amendment 或新 ADR clarify。

---

## 4. Decision 2 — Engineering Implication

### 4.1 取消既有 scope

- AMD-2026-05-20-04 Monetization Demand Test spec（~360 LOC + 18 hr operator setup；Cloudflare Pages 150 HTML/JS / Telegram bot 30 LOC Py / Stripe 80 LOC / Demo PnL screenshot cron 100 LOC bash matplotlib / weekly post template）— **完整 cancel**
- Sprint 1A-10 內無 Stream 2 / demand test 相關 task；確認 v5.7 §8 + v5.8 §3 不含

### 4.2 Y1末 evidence packet

Y1末 (Sprint 10 W36-39) 商業化 evidence 只 evaluate **Bybit Copy Trading** per ADR-0030 4-gate (Alpha + Governance + Infrastructure + Regulatory)；不再含 Stream 2 demand test gate。

### 4.3 不觸發 cascade patch

本 AMD 為 scope retire 性質，不引入新 engineering work；不需 V### schema migration / Rust new module / Python new script。Cascade patch 範圍：
- `docs/README.md` 索引更新（AMD list 加本條目）
- `docs/governance_dev/SPECIFICATION_REGISTER.md` AMD count 更新
- TODO.md 移除任何 Stream 2 / Telegram bot / demand test 殘留 task（如有）

---

## 5. Alternatives Considered

| Alternative | 棄因 |
|---|---|
| 保留 AMD-05 only retract IP sale，Stream 2 不動 | 違 operator 2026-05-25 directive；v5.x 已 implicit drop Stream 2 但無 explicit AMD，governance drift 風險（future sub-agent dispatch 可能誤反 implicit 改 active）|
| 拆 2 個 AMD (一個 retire Stream 2 / 一個 retire MEV/DEX) | scope 過度切碎；operator directive 是「不考慮任何交易所提供功能外」覆蓋整個 non-exchange-native 範疇，單一 AMD 對齊 |
| 不立 AMD 改用 ADR | 商業化 scope 是 strategy-level directive 非 architecture decision；AMD 是正確 governance level |
| 改 CLAUDE.md baseline 加「商業化必須 exchange-native」原則 | over-engineering；CLAUDE.md baseline 字面已寫定不動原則（per AMD-2026-05-21-01 v2 §6.3 Q1 amendment 並存路徑）；商業化邊界是 strategy 層治理，不上升到 root principle |

---

## 6. Consequences

### 6.1 Positive

- **Single product focus**：對齊 AMD-2026-05-25-02 v5.5 reframe formalize「完整 quant bot 單一產品」定位；不分散 engineering capacity 到 marketing / community / subscription infrastructure
- **法律 / ToS 風險降低**：Bybit Copy Trading 在 Bybit ToS 範圍內合法運作；non-native subscription / IP sale 涉及單獨 ToS / 報稅 / KYC 複雜性
- **Governance gap 補完**：v4.4 D7 constraint 從 execution-plan 級升為 AMD 級；AMD-05 retract scope 從 IP sale 擴 to all non-native
- **Sprint 1A-10 dispatch packet 簡化**：移除 Stream 2 demand test spec 360 LOC + 18 hr，capacity 釋出
- **Y1末 evidence packet 對齊**：只 evaluate Bybit Copy Trading per ADR-0030 4-gate

### 6.2 Negative / Risk

- **失去 demand test pivot option**：若 Bybit Copy Trading 4-gate Y1末 evaluation FAIL，無 Stream 2 demand test 作為 pivot fallback；mitigation = `2026-05-20--v4.3 §10` 已說「subscription = sunk cost」+ operator 2026-05-25 確認接受
- **未來商業化評估收緊**：如 operator 未來想重啟 Stream 2 / signal service，須走 AMD-25-01 amendment chain；mitigation = amendment 機制本身存在，governance 可調整
- **Bybit 平台依賴度升**：商業化全靠 Bybit Copy Trading / Earn / Competitions = single venue 依賴；mitigation = ADR-0033 + ADR-0040 Y3+ Binance equivalent reserve

### 6.3 與既存設計協作

| 既存元素 | 與本 AMD 關係 |
|---|---|
| ADR-0030 Copy Trading evidence-gated | **核心 active** Y1末 4-gate；本 AMD reaffirm |
| ADR-0006 Bybit-only + ADR-0033 Binance amendment | **venue scope 對齊**；本 AMD 定義「交易所」= Bybit Y1 + Binance Y3+ |
| ADR-0040 Multi-Venue Gate Spec | **DEX/Hyperliquid 拒絕路徑同步**；本 AMD §3.1 #5 MEV/DEX retire 與 ADR-0040 venue enum 根源拒絕對齊 |
| AMD-2026-05-25-02 v5.5 reframe formalize | **single product 定位對齊**；本 AMD 是 v5.5 「完整 quant bot 單一產品」的商業化邊界落地 |
| ADR-0027 AI Plan Mode time-based | 不衝突；Cowork subscription 是 operator overhead 非 project monetization |
| v5.7 §10 ADR-0028 (proposed) | **編號順移**：v5.7/v5.6 寫的 ADR-0028 proposed 實際 land 為 ADR-0030 (per drift audit verify)；本 AMD 對齊 ADR-0030 |

---

## 7. Sign-off

| Role | Status | Date | Note |
|---|---|---|---|
| Operator | DIRECTIVE GIVEN | 2026-05-25 | 「我們現在不考慮任何交易所提供功能外的商業化模式」+ 「IP sale 也排除掉，我們只考慮 Bybit 或者 Binance 平台提供的方案」|
| PM | DRAFT | 2026-05-25 | Pending operator confirm before commit + cascade |
| CC | PENDING | — | 16 root principles compliance walkthrough（特別 #11 Agent autonomy + #14 baseline operable）|
| R4 | PENDING | — | docs/README + SPECIFICATION_REGISTER cascade |
| TW | PENDING | — | TODO.md / KNOWN_ISSUES.md cleanup（Stream 2 殘留 task 如有）|

---

## 8. Cascade Patch Checklist

待 operator confirm 後執行：

1. **docs/README.md**：AMD list 加本條目（amendments table）
2. **SPECIFICATION_REGISTER.md**：Active AMD count 更新
3. **TODO.md**：grep + 移除 Stream 2 / Telegram bot / Substack / Stripe / MEV / demand test 相關殘留 task
4. **KNOWN_ISSUES.md**：如有相關 known issue，標 superseded by AMD-25-01
5. **CLAUDE.md**：不動（per amendment 並存路徑，baseline 字面不動）
6. **docs/CCAgentWorkSpace/PM/workspace/reports/**：產一份 PM sign-off report 引用本 AMD

---

**END AMD-2026-05-25-01**

Author: 主會話 PM (per operator 2026-05-25 directive during V1→V5.8 drift audit)
Co-Authored-By: Claude Opus 4.7 (1M context)
