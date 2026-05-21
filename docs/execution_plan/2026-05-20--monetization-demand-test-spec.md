# Monetization Demand Test Spec — Stream 2 Parallel Sprint

**日期**: 2026-05-20
**對應 AMD**: AMD-2026-05-20-04 (v4.3 commercial evidence sprint)
**Status**: SPEC READY — N+1 W1 launch concurrent with Stream 1
**Owner**: Operator (primary) + E1a (tech setup) + legal friend (ToS review, 0.5 hr)

---

## 1. Goal

平行於 Stream 1 技術 evidence sprint，獨立測試**是否有付費 demand for crypto trading signals + governance framework**，提供 W8 Joint Verdict 中的 demand axis 資料。

**核心命題**：v4.2 之前所有設計都只測「我們有沒有 alpha」。Demand Test 測「即使有 alpha，市場願意付費嗎？」。

---

## 2. 5-Level Demand Signal Pyramid

按 commercial intent 強度從弱到強：

| Level | Signal | 量化方式 | W8 threshold (低/中/高) |
|---|---|---|---|
| **L1** | Landing page visit | Cloudflare Analytics unique visitor | 100 / 300 / 1000+ |
| **L2** | Email signup | Substack/Beehiiv list growth | 20 / 100 / 300+ |
| **L3** | Telegram channel join | TG bot member count | 50 / 200 / 500+ |
| **L4** | **Paid pre-order $1** (refundable) | Stripe Checkout count | **5 / 20 / 50+** |
| **L5** | Paid subscription start ($39+/mo) | Stripe MRR | 0 / 3 / 10+ |

**L4 是 W8 decision pivot**：< 5 = 0 demand → Stream 2 KILL；≥ 20 = strong commercial demand → PIVOT viable。

---

## 3. 技術設施 setup（N+1 W3-W4 land）

### 3.1 Landing page

**Stack**: Cloudflare Pages + Astro static site

**內容結構**:
```
Hero: "玄衡 Signal — Liquidation Cascade + New Listing Alpha for Bybit Perp"
Demo proof:
  - Cumulative demo PnL chart (auto-updated from trading.fills WHERE
    track='direct_exploit' AND is_paper=true)
  - Sharpe / DD / win rate widget
  - Last 10 demo trades table (entry/exit/PnL)
Pricing:
  - Free tier: 24h delayed signals (1 per day max)
  - Basic $39/mo: real-time signals via Telegram
  - Pro $99/mo: + entry/exit precise levels + position size guidance
CTA:
  - "Reserve your spot $1 (refundable)" → Stripe Checkout
  - "Free preview" → Telegram channel join
  - "Newsletter" → Substack signup
Disclaimer (footer, every page):
  - "Educational purposes only. No financial advice. ..." (per §6)
```

**LOC**: ~150 HTML/Astro + Tailwind CSS
**Setup time**: 4 hr operator + 2 hr E1a

### 3.2 Demo PnL screenshot pipeline

每日 UTC 00:00 自動產生:
- Cumulative PnL chart (matplotlib + agg backend)
- Stats table (n_trades, Sharpe, DD, win rate, avg edge bps)
- Upload to landing page via Cloudflare Pages deploy hook

```python
# helper_scripts/monetization/generate_demo_evidence.py
SELECT
    date_trunc('day', ts) AS day,
    SUM(realized_pnl - fee) AS daily_net_pnl,
    COUNT(*) AS n_trades,
    SUM(realized_pnl - fee) OVER (ORDER BY day) AS cum_pnl
FROM trading.fills
WHERE track = 'direct_exploit'
  AND is_paper = true
  AND ts > now() - INTERVAL '90 days'
GROUP BY 1 ORDER BY 1;
```

**LOC**: ~100 bash + matplotlib
**Setup time**: 6 hr E1

### 3.3 Telegram channel

Free Telegram channel + admin bot:
- Auto-post daily summary at UTC 00:00
- Post selected demo trades with "Why this trade worked" educational tone
- DO NOT post forward signals during demand test phase (legal risk)
- Auto-track member count via Bot API

**Setup time**: 1 hr operator + 1 hr E1a

### 3.4 Substack / Beehiiv newsletter

Pick one (Beehiiv has better free tier):
- Weekly post: "玄衡 Demo Week Report — what worked, what didn't"
- Include charts + 2-3 trade case studies
- CTA at end of every post: "Reserve spot ($1)" + "Join Telegram"

**Setup time**: 1 hr operator (signup) + 2 hr/week operator (writing)

### 3.5 Stripe Checkout

- Product: "玄衡 Signal Reservation - $1"
- Refundable per request
- Webhook → `agent.ai_invocations`-style ledger table:

```sql
CREATE TABLE IF NOT EXISTS monetization.demand_signals (
    signal_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_type     TEXT NOT NULL CHECK (signal_type IN (
                        'page_visit', 'email_signup', 'telegram_join',
                        'paid_preorder', 'paid_subscription'
                    )),
    source          TEXT,
    email           TEXT,
    amount_usd      NUMERIC,
    stripe_session_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    refunded_at     TIMESTAMPTZ,
    details         JSONB
);
CREATE INDEX IF NOT EXISTS idx_demand_signals_type_ts
    ON monetization.demand_signals (signal_type, created_at DESC);
```

(新 schema `monetization.*` — V101.5 minor migration or rolled into V102)

**Setup time**: 2 hr E1a + Stripe account 0.5 hr operator

### 3.6 ToS + Disclaimer

**Required content**:
- Educational purposes only
- Past performance disclaimer
- No financial advice statement
- No guaranteed returns
- Crypto perp risk acknowledgment
- Self-execution clause (we don't custody funds or auto-trade for users)
- Refund policy (full refund within 30 days of pre-order)
- Privacy: email used only for newsletter; no resale
- Jurisdiction: operator decides (Hong Kong / Singapore / etc.)

**Setup**: Free templates (TermsFeed / Termly) + 30-min friend lawyer review

**Time**: 4 hr operator + 0.5 hr legal review

### 3.7 Total setup

| Item | LOC | Time |
|---|---|---|
| Landing page | 150 | 6 hr |
| Demo PnL pipeline | 100 | 6 hr |
| Telegram channel | 30 | 2 hr |
| Substack newsletter | 0 | 1 hr |
| Stripe Checkout + webhook | 80 | 2.5 hr |
| Schema migration (monetization.*) | 50 SQL | 1 hr |
| ToS + disclaimer | 0 | 4.5 hr |
| **Total** | **~410 LOC** | **23 hr** |

N+1 sprint Stream 2 capacity 30% = ~30 hr / 8 weeks = 3.75 hr/week. setup phase concentrated in W1-W2 (operator + E1a peak); maintenance W3-W8 is 2-3 hr/week post-writing.

---

## 4. 內容策略

### 4.1 每週發布 schedule

W1-W2: "玄衡 is coming" teaser
- 1 newsletter: project introduction + why this niche (LCS / NLE alpha)
- Telegram: "soon" announcement + countdown

W3-W4: First evidence post
- 1 newsletter + 1 Telegram post: "Our LCS demo started Week N"
- Initial PnL data (may be small sample)
- Educational: "What is liquidation cascade?"

W5-W8: Weekly evidence drumbeat
- 1 newsletter per week with cumulative chart
- 2-3 Telegram posts per week with specific trade case studies
- Always include CTA (reserve spot / Telegram join)

### 4.2 Legal-safe content rules

**禁止**:
- Forward signals (e.g. "BUY BTCUSDT NOW at 65000")
- Specific entry/exit prices for trades not yet executed
- "Guaranteed" / "risk-free" / "definite profit" 語言
- Personal financial advice DM responses

**允許**:
- Past trade explanation ("This trade hit +25 bps because...")
- Statistical aggregates (Sharpe, win rate, etc.)
- Educational content (what is liquidation cascade, what is funding rate)
- Pre-order CTA

### 4.3 Brand tone

- Educational > hype
- Honest about loss (publish losing trades too)
- Disciplined ("not financial advice" baked into every post)
- Tech-forward (charts, Sharpe, DD — appeal to numerate audience)

---

## 5. Channels for organic reach

Cold outreach low-cost channels (no paid ads in evidence sprint):
- Crypto Twitter (operator posts demo evidence)
- Reddit r/cryptocurrency / r/algotrading / r/Bybit (organic, no spam)
- Discord crypto trading communities (operator participates organically)
- HackerNews if interesting tech post (governance moat angle)

**Time cost**: ~3 hr/week operator W2-W8 = 18 hr total

---

## 6. W8 Demand Verdict Reading

W8 verdict per Joint Matrix (v4.3 §5.1) reads:

```sql
-- W8 demand snapshot
SELECT
    signal_type,
    COUNT(*) AS count,
    COUNT(*) FILTER (WHERE created_at > now() - INTERVAL '7 days') AS last_7d
FROM monetization.demand_signals
GROUP BY 1 ORDER BY 1;
```

Pivot decision based on **L4 paid_preorder count**:

| L4 count | Verdict |
|---|---|
| < 5 | **DEMAND FAIL** — Stream 2 KILL W8 |
| 5-19 | **DEMAND WEAK** — continue Observe Mode 4 wks |
| 20-49 | **DEMAND OK** — PIVOT viable if Stream 1 fails |
| ≥ 50 | **DEMAND STRONG** — aggressive PIVOT regardless Stream 1 outcome |

Also factor:
- L5 paid subscription count (if any) — major weight
- Refund rate from L4 (high refund = soft demand)
- Newsletter open rate (engagement quality)

---

## 7. Risk Register

| Risk | Mitigation |
|---|---|
| Legal: signal service in operator's jurisdiction requires license | Friend-lawyer 0.5 hr review at setup; jurisdiction choice; if blocker → license-free regions only (educational content always free) |
| Brand damage from demo losses | Publish honestly; educational tone; emphasize "experiment" framing |
| Scam-adjacent perception | No "guaranteed returns"; transparent disclaimer; refundable pre-orders demonstrate good faith |
| Stripe account flagged | Use legitimate business entity; clear product description; refund honored promptly |
| Bybit ToS conflict (selling signals based on their exchange) | Bybit ToS allows third-party signal services; verify in setup |
| Demand exists but only at $9-19/mo (not $39+) | Pricing flexibility; reduce tier to $19 if needed |

---

## 8. Acceptance Criteria

| AC | Verification |
|---|---|
| W1-AC1 | Landing page live + 90 days SSL |
| W1-AC2 | Telegram channel live + bot operational |
| W1-AC3 | Substack/Beehiiv signup functional |
| W1-AC4 | Stripe Checkout integration tested with $1 transaction |
| W2-AC5 | ToS + disclaimer reviewed by legal friend |
| W2-AC6 | First newsletter sent |
| W4-AC7 | Daily demo PnL chart auto-update functional |
| W4-AC8 | L1-L5 ledger populated with non-zero entries |
| W8-AC9 | demand verdict report generated; L4 count > 0 (any sample) |
| W8-AC10 | refund rate < 50% if any L4 events |

---

## 9. References

- v4.3 spec: `srv/2026-05-20--commercial-evidence-sprint-v4.3.md` §2
- AMD-2026-05-20-04
- ADR-0027 Plan Mode (Stream 2 in Build Mode N+1-N+3)
- Cloudflare Pages: https://pages.cloudflare.com/
- Beehiiv: https://www.beehiiv.com/
- Stripe Checkout: https://stripe.com/checkout
- Bybit ToS (third-party signals allowed): https://www.bybit.com/en/terms-service

---

**END Monetization Demand Test Spec**
