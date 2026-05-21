# 玄衡 · Arcane Equilibrium — Commercial Evidence Sprint v4.3

> **🔴 RETRACTION NOTICE 2026-05-20**：Operator 明確告知 IP sale 不現實、不可能。
> Stream 3 IP Sale Prep **整段 retract**。下方 §3 內容保留為 audit trail 但**不執行**。
> - Capacity 重分配：原 Stream 3 10% → Stream 1 +10%（**Stream 1 變 70% / Stream 2 30%**）
> - W8 Joint Verdict matrix 簡化：2×2×2 → **2×2**（technical × demand 兩軸）
> - W12 hard kill triggers 減為 2-condition AND（無 edge + 無 demand）
> - 修訂 EV 算式：drop IP sale 5% × $5-15k 那條 = $250-750 expected
> - 真實 active stream 數 = 2，不是 3
> - 詳見 AMD-2026-05-20-05 retraction（待 land）

**Reframe note**: 不再叫「Dual-Track Architecture」。v4.3 是 **8-12 週商業證據衝刺**，不是長期架構願景。

**日期**：2026-05-20
**Author**：Claude（after 3rd strategic-level audit + operator approval to apply 8/11 reviewer points + 4 push-backs）
**Status**：DRAFT — supersedes v4.2；待 AMD-2026-05-20-04 ratify
**Operator 約束**：要主動追尋最優解、不盲信 reviewer、基於 cost/time/profit
**核心轉變 vs v4.2**：
- ✅ Reframe：「8-12 週商業證據衝刺」（不是「雙軌長期架構」）
- ✅ W8 + W12 **economic gates**（加在 statistical gate 上）
- ✅ Monetization Demand Test 並行 sprint（**整輪 audit 最有價值的新 idea**）
- ✅ Track B 全 cancel（連 schema 都不留 `learning.hypotheses`，只留 `hypothesis_preregistration`）
- ✅ IP sale prep 作 third parallel stream（10% time，不爭工程資源）
- ✅ ADR-0027 Plan Mode（**TIME-based 而非 DOLLAR-cycling**）
- 🔴 **push back** reviewer 訂閱 cost cycling 模型（subscription = sunk cost，不可月度 cycle）
- 🔴 **push back** 8-12 週 calendar timebox（改綁 evidence maturity）
- 🔴 **push back** reviewer monetization demand test 口號式描述（v4.3 給真實 spec）
- 🔴 **add** IP sale prep（reviewer 漏掉的 option value）

---

## §0 v4.2 → v4.3 三句話總結

1. **不再是架構**：v4.2 隱含「dual-track architecture」鼓勵 keep-going；v4.3 是「commercial evidence sprint」強迫 binary fork。
2. **加雙軌驗證**：技術 edge（LCS event-study + demo Sharpe）+ 商業 demand（Telegram/Copy Trading waitlist）**並行**測；W8 看雙重證據，不只看 statistical。
3. **誠實 cost framing**：subscription $400/mo 是 sunk cost（operator 跨項目共用），不是此項目可控；Plan Mode 管 operator hour budget，不是 dollar burn。

---

## §1 三條並行工作流（取代雙軌制）

```
┌─────────────────────────────────────────────────────────────┐
│   Stream 1: Technical Edge Sprint (60% capacity)            │
│   - LCS isolated cluster (ADR-0026 v3 thesis)               │
│   - NLE listing watcher shadow                              │
│   - Phase 0 V097/V098 catch-up                              │
│   - V101 11 表（drop hypotheses 表）+ V102                   │
│   - Tier 0 microstructure + Tier 1 RegimeClassifier         │
│   Goal: W4 event-study + W8 14d demo verdict                │
├─────────────────────────────────────────────────────────────┤
│   Stream 2: Monetization Demand Test (30% capacity)         │
│   - Telegram channel + landing page + Substack newsletter   │
│   - 每週 1-2 篇 demo evidence post（live PnL screenshots）   │
│   - Waitlist signup with explicit pricing ($39 basic / $99 pro)│
│   - Stripe checkout intent measurement                      │
│   - Legal: ToS + disclaimer + no-financial-advice           │
│   Goal: W8 demand verdict（subs intent count + paid pre-order）│
├─────────────────────────────────────────────────────────────┤
│   Stream 3: IP Sale Prep (10% capacity, low effort)        │
│   - README cleanup + architecture diagram + demo video      │
│   - Landing page "玄衡 framework for sale" (private)        │
│   - Quiet outreach to 5-10 crypto quant networks            │
│   Goal: W12 buyer signal + offer count                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
              W8 Joint Verdict (edge × demand × IP) 2×2×2 matrix
                          ↓
              W12 Hard Kill / Continue / Pivot
```

**Capacity v4.3 N+1-N+3**: Stream 1 60% / Stream 2 30% / Stream 3 10%

對比 v4.2: 取消 Track B 10%（schema-only 也是死表），轉到 Stream 2 demand test。

---

## §2 Stream 2 Monetization Demand Test — 完整 spec

reviewer 提出但口號式；v4.3 給真實 spec（這條是新 work，需 PA dispatch）。

### §2.1 平台架構

| Surface | Tool | 月成本 | 設立時間 |
|---|---|---|---|
| Landing page | Cloudflare Pages + Astro | $0 | 4 hr |
| Email list | Substack / Beehiiv | $0 (< 1k subs) | 1 hr |
| Telegram channel | Telegram free | $0 | 1 hr |
| Paid pre-order | Stripe Checkout link | 2.9%+30c per txn | 2 hr |
| Demo PnL screenshot pipeline | bash + cron + matplotlib | $0 | 6 hr |
| Disclaimer + ToS | Free template + 30 min legal review | $0 | 4 hr |
| **Total setup** | | **$0/mo + 2.9% txn fee** | **~18 hr** |

### §2.2 Demand signal measurement

5 levels of demand strength（越深越有效 signal）：

| Level | Signal | 量化 |
|---|---|---|
| L1 | Landing page visit | Cloudflare Analytics |
| L2 | Email signup | Substack/Beehiiv list growth |
| L3 | Telegram channel join | TG bot 統計 |
| L4 | **Paid pre-order $1**（refundable）| Stripe → 真實 commercial intent |
| L5 | **Paid subscription start** | Stripe MRR |

W8 demand verdict thresholds：
- L4 ≥ 20 → strong commercial demand → PIVOT 可行
- L4 = 5-20 → weak demand → 持續觀察
- L4 < 5 → 0 commercial demand → Stream 2 KILL

### §2.3 內容策略（每週發布）

每週 1-2 個 demo evidence post：
- LCS demo trade screenshots（PnL chart + entry/exit reasoning）
- "Why this trade worked" educational tone（不是 hype）
- Cumulative demo Sharpe / DD chart
- 不發 live trades（live 還沒 deploy）
- 不發 forward signal（only 事後解析）—— 避免 financial advice 法律風險

### §2.4 法律 / ToS / Disclaimer 標準語言

```
"This is for educational purposes only. Past performance does not 
guarantee future results. We do not provide financial advice. Trading 
crypto perpetual futures involves significant risk including total 
loss of capital. Subscribers act at their own discretion. Demo data 
shown is paper trading; live trading may differ materially. We do not 
custody subscriber funds; signals are for self-execution only."
```

Operator 4 hr 設立 + 律師朋友 0.5 hr review。**這是 GO/NO-GO**，不繞。

### §2.5 W8 demand fork

```
W8 verdict (parallel to Stream 1 technical verdict):

L4 paid pre-orders ≥ 20:
  → "demand signal exists" mark
  → 後續按 Stream 1 technical verdict 決定：
     - Stream 1 PASS + demand PASS → SCALE
     - Stream 1 FAIL + demand PASS → PIVOT (do signal service without own trading)
     - Stream 1 PASS + demand FAIL → CONTINUE Stream 1 Observe Mode（賺自有 P&L）
     - Stream 1 FAIL + demand FAIL → KILL Stream 1 + 2，all-in Stream 3 IP sale

L4 paid pre-orders < 5:
  → "demand signal absent"
  → Stream 2 KILL（W8 即 retire landing page + telegram channel）
  → Stream 1 verdict 獨立決定
```

---

## §3 Stream 3 IP Sale Prep — light parallel work

reviewer 漏掉的 option value。冷酷算式：

```
Cost:
  - operator 8 週 × 2-3 hr/週 = 16-24 hr setup
  - 0 額外訂閱

Expected value (probability-weighted):
  - 30% chance buyer signal in 8 週: $5-15k IP sale
  - 70% chance 0 buyer interest: 0
  - EV: $1.5-4.5k

ROI per hour: $1500/24 = $62/hr ~ $4500/16 = $280/hr
  → 顯著高於 Track A live $1k expected annual $50-200 ROI
```

### §3.1 Deliverables（W1-W8 漸進，不堵 Stream 1）

W1-W2：
- README.md 整理（external-facing 版本）
- Architecture diagram （從既有 docs/architecture 摘）
- 5-minute demo video（screen recording 跑 demo + governance 解說）

W3-W4：
- Private landing page（password-gated；"governance framework for crypto quant traders"）
- Pricing: $5k-15k source license + $1k/yr support

W5-W8：
- Quiet outreach（不公開 broadcast）：
  - QuantConnect community / forums
  - Crypto Twitter quant accounts (DM 5-10 個)
  - Discord crypto trading communities

W8 verdict: count of unsolicited inquiries（不算自己 cold reach 的 follow-up）

### §3.2 IP 不可移除部分

賣的是 **governance framework + Rust engine skeleton**，不包：
- Operator-specific alpha signals (LCS / NLE 內部參數)
- Bybit API credentials / secrets
- Trade history data

買家拿到的是 "build your own crypto quant bot starting from operating system level"，operator 保留 alpha-bearing logic。

---

## §4 ADR-0027 Plan Mode（TIME-based，不是 DOLLAR-cycling）

reviewer 提 Build / Observe / Low Activity 三模式管理 burn，但用 dollar 數字（$220-300 / $100-150 / $40-120）— 我 push back：subscription 是 sunk cost。

v4.3 Plan Mode 重新定義為 **operator weekly hour budget**：

| Mode | Operator hr/week | API spend cap/mo | Trigger |
|---|---|---|---|
| Build | 20-30 hr | $30 | active dev sprint (N+1-N+3) |
| Observe | 5-10 hr | $10 | W8 PASS but waiting for P0/LG/OPS clear |
| Low Activity | 1-3 hr | $5 | indefinite background; only check-ins |
| Deep Dev Exception | up to 50 hr/wk | $50 | P0 incident / live gate / monetization sprint, operator manual approve |

### §4.1 為何 TIME-based 才對

- Claude Max / GPT Plus 訂閱無法月度 cycle（無 prorated cancel）
- operator 跨項目用，不能單獨歸 this-project 成本
- **真正可控的是 operator hours，不是 dollar burn**
- API 邊際 spend ($10-30/mo) 已小到 noise level

### §4.2 Mode transition rules

```
Default：N+1-N+3 = Build Mode
W8 verdict:
  - PASS (technical + demand) → CONTINUE Build Mode N+4-N+5
  - PASS (technical only) → switch to Observe Mode（demo 持續累積，等 live gate / 等 demand）
  - FAIL → switch to Low Activity Mode (Stream 1 dormant) + go-no-go Stream 3 IP

W12 verdict:
  - Build Mode 已連續 2 個月 → 強制 cooldown 至 Observe Mode（防架構補丁延長未證明項目）
  - 除非 Deep Dev Exception (operator manual approve)

W24 verdict:
  - Low Activity 連續 4 個月 → operator 主動決議 KILL or revival
```

---

## §5 W8 + W12 Joint Verdict（2×2×2 matrix）

reviewer 提 W8 economic gate + W12 hard gate，v4.3 形式化：

### §5.1 W8 verdict matrix

| Stream 1 (技術) | Stream 2 (demand) | Stream 3 (IP) | Action |
|---|---|---|---|
| ✅ Sharpe > 1.0 | ✅ L4 ≥ 20 | (any) | **SCALE**：寫 PIVOT spec + scale Stream 1 live |
| ✅ Sharpe > 1.0 | ❌ L4 < 5 | (any) | **OBSERVE Mode**：demo 持續，等 live gate（不擴投入） |
| ❌ Sharpe < 0.5 | ✅ L4 ≥ 20 | (any) | **PIVOT to Signal Service**（Stream 2 接管，Stream 1 KILL） |
| ❌ Sharpe < 0.5 | ❌ L4 < 5 | ✅ buyer signal | **KILL Stream 1+2，ALL-IN Stream 3** IP sale |
| ❌ Sharpe < 0.5 | ❌ L4 < 5 | ❌ no buyer | **HARD KILL**（推到 W12 final review） |

### §5.2 W12 hard verdict

```
W12 hard kill triggers (3-condition AND):
  - Stream 1 12-week demo cum net edge < 0 bps
  - Stream 2 L4 paid pre-orders < 10 over 8 weeks
  - Stream 3 0 buyer inquiry over 12 weeks

→ KILL self-built trading mainline + monetization stream
→ Operator 重配時間：
  - 此 $5760/年 burn 轉投資 index fund / 自我 reskilling
  - Codebase 變 sunk asset; 可選低成本維持作 portfolio show piece
```

### §5.3 W12 partial conditions

```
W12 1-of-3 success → CONTINUE conditional:
  - Stream 1 only → Observe Mode 6 個月（不擴）
  - Stream 2 only → Pivot 全力 signal service
  - Stream 3 only → 全力 IP sale closing

W12 0-of-3 success → HARD KILL
```

---

## §6 Stream 1 變更（vs v4.2）

### §6.1 Drop `learning.hypotheses` table

per reviewer #4，Track B schema-only 也死表。drop `learning.hypotheses` from V101。

**保留**：`learning.hypothesis_preregistration`（Track A direct_exploit 強制 per ADR-0026 v3）。

V101 scope: **11 既存表 + 1 新表**（不是 12+2）

修訂 V101 spec v4：drop `learning.hypotheses` 段落 + 相關 backfill。

### §6.2 W8 milestone reframe（再次）

v4.2 已 reframe 為「14d demo verdict only」；v4.3 進一步：

```
W8 Stream 1 verdict（technical only）：
  - LCS demo 14d cumulative Sharpe / DSR / DD / win rate
  - LCS event-study CAR + HAC t-stat from W4-W6
  - NLE shadow event count + first event-study preview
  - Replay match rate (若 Phase 1.5 function 已 land；否則 N/A)
  - 不再聲稱「live-ready proof」；不再隱含 live deploy 時間表
```

### §6.3 LCS / NLE / Tier 0 / Tier 1 / V101 / V102 / Phase 0

全部 inherit v4.2 設計（per ADR-0025 v3 + ADR-0026 v3 + V101 spec v3）。**唯一修改**：drop `learning.hypotheses` table from V101 schema list。

---

## §7 修訂 Sprint Plan（v4.3）

| Sprint | Week | Stream 1 (60%) | Stream 2 (30%) | Stream 3 (10%) | Milestone |
|---|---|---|---|---|---|
| N+0 | 已過 | — | — | — | 65% |
| **N+1** | W3-W4 | Phase 0 V097/V098 + V101 (11+1 表) + Tier 0/1 + LCS code shadow + NLE watcher shadow | Landing page + Telegram + Substack + Stripe + ToS+disclaimer **land** | README + diagram + demo video draft | 67% |
| **N+2** | W5-W6 | V102 + LCS event-study (market.liquidations 14d) + LCS demo deploy W6 | 每週 1-2 evidence post + waitlist 累積 | Private landing page + pricing | 70% |
| **N+3** | W7-W8 | LCS 14d demo evidence + NLE event-study first report | Demand metrics: L1-L5 counts | Outreach 5-10 networks（DM）| **W8 Joint Verdict** |
| **N+4** | W9-W10 | branch per W8 verdict matrix (§5.1) | branch | branch | per branch |
| **N+5** | W11-W12 | branch | branch | branch | **W12 hard verdict** |
| **N+6** | W13-W14 | (if KILL) sunset + IP transfer / (if CONTINUE) Observe Mode 6 個月計畫 | per branch | per branch | per branch |

**N+1 Stream 2 deliverables**（new work 必須 PA 派 spec）：

| Task | LOC / hr | Owner |
|---|---|---|
| Cloudflare Pages + Astro landing | ~150 HTML/JS + 4 hr | E1a / operator |
| Telegram bot setup | 30 LOC Python + 1 hr | E1a |
| Substack/Beehiiv signup + integration | 0 LOC, 1 hr admin | operator |
| Stripe checkout link + webhook | ~80 LOC + 2 hr | E1a |
| ToS / disclaimer template + legal review | 0 LOC, 4 hr | operator + legal friend |
| Demo PnL screenshot cron pipeline | ~100 LOC bash + matplotlib + 6 hr | E1 |
| Weekly post template + first 2 posts | 0 LOC, 4 hr | operator |
| **Total Stream 2 N+1 setup** | ~360 LOC + 18 hr operator | E1+E1a+operator |

---

## §8 Kill Criteria 統一（v4.3 最終版）

| Phase | Trigger | Action |
|---|---|---|
| W4 | Phase 0 catch-up V097/V098 失敗 + healthcheck issue | block all 3 streams；revisit dependencies |
| W4 | Stream 2 ToS/legal not approved | block Stream 2 W4+；Stream 1+3 continue |
| W6 | Stream 1 event-study t-stat < 1.5 | block LCS demo deploy；NLE shadow continue |
| W8 | per §5.1 matrix | per matrix action |
| W12 | per §5.2 3-condition AND | HARD KILL |
| W12 | 1-of-3 only | per §5.3 conditional CONTINUE |
| W24 | (if Observe Mode) demo 持續 < 0 bps net edge | KILL Observe |
| W24 | (if Stream 2 signal service) MRR < $200 | KILL signal service |
| W24 | (if Stream 3 IP sale) no closed deal + 0 active inquiry | KILL IP sale |

**Plan Mode enforcement**（per ADR-0027）：
- N+1-N+3 Build Mode auto-expire W8（max 2 個月連續 Build）
- W8 後預設 Observe Mode；continue Build 需 Deep Dev Exception
- Low Activity Mode 連續 4 個月觸發 operator 主動 KILL/revival 決議

---

## §9 governance artifacts 更新清單

| Artifact | v4.2 | v4.3 |
|---|---|---|
| AMD-2026-05-20-04 | — | **NEW**（記錄 3rd reviewer audit + v4.3 ratify）|
| ADR-0027 Plan Mode | — | **NEW**（TIME-based budgeting + Build/Observe/Low Activity/Deep Dev modes）|
| Monetization Demand Test spec | — | **NEW**（Stream 2 完整 spec）|
| ADR-0024-lite | Accepted | unchanged |
| ADR-0025 v3 | Accepted | **v4 minor**（drop `learning.hypotheses` from scope；變 11+1 表）|
| ADR-0026 v3 | Accepted | unchanged |
| V101/V102 spec v3 | SPEC READY | **v4 minor**（drop hypotheses table；變 11 existing + 1 new）|
| v4.2 doc | active | **superseded by v4.3** |
| TODO.md §-0 / §1 | v57.2 | **v57.3** |

---

## §10 不做的事（v4.3 specific）

對 reviewer 主張的 push backs，必須明確不做：

19. ❌ **不要月度 cycle Claude Max / GPT Plus 訂閱**（subscription 是 sunk cost）
20. ❌ **不要把 Plan Mode 寫成 dollar burn 控制**（TIME budget 才對）
21. ❌ **不要等 8 週才做 demand test**（W1 平行 launch）
22. ❌ **不要把 IP sale 留到 W12 fallback**（W1 漸進 prep）
23. ❌ **不要在 Stream 2 跑 forward signal service before demand verified**（先測 demand 後賣產品）
24. ❌ **不要把 Stream 1 + 2 + 3 KILL gate 互相耦合**（3 stream 獨立 verdict，combined matrix 決定 action）
25. ❌ **不要承諾 W12 必有 commercial revenue**（W12 是 verdict point，不是 deliverable timeline）
26. ❌ **不要把 v4.3 賣為「最終方案」**（v4.3 是 evidence sprint，本來就準備被 superseded by 結果）

---

## §11 對 reviewer 主張的 push back 紀錄

| Reviewer 主張 | 我的 push back | v4.3 處理 |
|---|---|---|
| Build $220-300 / Observe $100-150 / Low $40-120 cycle | subscription = sunk cost，不可月度 cycle | ADR-0027 改 TIME-based: 20-30hr / 5-10hr / 1-3hr 週時間 budget |
| 6 月 burn $1.1-1.6k / 1 年 $2.1-3.2k | 取決於 cycle 可行性；若不可 cycle 數字 invalid | 不在 v4.3 doc 內 fix dollar 數字；改寫 hour budgeting |
| 8-12 週 timebox | calendar timebox 太武斷 | 改綁 evidence maturity (LCS 14d data + 14d demo = 28d = W4 + W8) |
| Monetization demand test 口號式 | 需真實 spec | §2 完整 spec（5 levels demand + Stripe pre-order + L4 threshold） |
| IP sale 留 W12+ fallback | 機會成本浪費 | §3 Stream 3 從 W1 漸進並行 |

---

## §12 預期 outcome 真實算式（不畫餅）

W8 Joint Verdict 真實機率分佈（基於 cold realistic estimate）：

| Stream 1 (技術) | Stream 2 (demand) | Stream 3 (IP) | 機率 | Action |
|---|---|---|---|---|
| ✅ | ✅ | (any) | ~5% | SCALE |
| ✅ | ❌ | (any) | ~25% | OBSERVE Mode |
| ❌ | ✅ | (any) | ~10% | PIVOT |
| ❌ | ❌ | ✅ | ~5% | All-in IP sale |
| ❌ | ❌ | ❌ | ~55% | HARD KILL trigger W12 |

**Expected EV** (probability-weighted 1-year P&L):
- SCALE: 5% × ~$500-2000 = $25-100
- OBSERVE: 25% × ~$50-200 = $13-50
- PIVOT: 10% × ~$2000-12000 (signal service MRR×12) = $200-1200
- IP sale: 5% × ~$5000-15000 = $250-750
- HARD KILL: 55% × $0 = $0
- **Total EV: $488-2100 / year**

對比 burn (若 Plan Mode 嚴執行)：
- 6 月 Build + 6 月 Observe = ~$300 + $100 = $400 hosting/API + sunk $4800 subscriptions
- **真實 marginal burn**: $400-500/year
- **EV - marginal burn = +$0 to +$1700** annual

→ 雖然 sunk subscription 仍 dominate，但 **marginal ROI 正常**。Operator 不會因此項目額外大虧。

**冷酷結論**：v4.3 不是「賺錢機器」，是「**8-12 週成本受限的證據衝刺，三條獨立路徑各有 5-25% 命中機率**」。期望 EV 不大但 marginal burn 控制好，**最壞情況也只是 8-12 週時間機會成本 + $400-500 marginal $**。這是 acceptable bet。

---

## §13 References

- v1/v2/v3/v4/v4.1/v4.2: `srv/2026-05-20--*.md`（audit trail）
- AMD-01/02/03: `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-0{1,2,3}*.md`
- **AMD-04** (NEW): `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-04-v4.3-commercial-evidence-sprint.md`
- **ADR-0027** (NEW): `docs/adr/0027-ai-plan-mode-time-based-budgeting.md`
- **Monetization Demand Test spec** (NEW): `docs/execution_plan/2026-05-20--monetization-demand-test-spec.md`
- ADR-0024-lite / ADR-0025 v3 / ADR-0026 v3 / V101 spec v3+minor (drop hypotheses table)
- Bybit Copy Trading: https://www.bybit.com/copyTrade
- Substack / Beehiiv / Cloudflare Pages references

---

**END v4.3**

**3 streams ready; Plan Mode set; W8/W12 joint verdict gates locked.**
