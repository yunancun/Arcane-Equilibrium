# 玄衡 · Arcane Equilibrium — Dual-Track 雙軌制架構 v4

**日期**：2026-05-20
**Author**：Claude
**Status**：DRAFT — Supersedes v3 lean，把 v2 ASDS 願景 + v3 Direct Exploit 整合為雙軌並行
**Operator 約束**：要 v3 短期現金流 **且** 要 v2 長期 ASDS 規模化；雙軌數據獨立計算、獨立顯示
**核心轉向**：兩軌共享 governance moat，但 attribution / risk budget / GUI / kill criteria 完全隔離

---

## §0 一張圖看懂雙軌制

```
┌─────────────────────────────────────────────────────────────┐
│              Shared Infrastructure (existing, untouched)     │
│   Guardian │ Decision Lease │ H0 Gate │ Replay │ Risk SM    │
│   GovernanceHub 4 SMs │ 5-gate live boundary │ Stage 0/0R/1 │
└──────┬──────────────────┬──────────────────┬───────────────┘
       │                  │                  │
┌──────▼──────────┐ ┌─────▼─────────┐ ┌─────▼──────────────┐
│ Track A          │ │ Track B       │ │ Track C            │
│ Direct Exploit   │ │ ASDS Factory  │ │ Baseline           │
│ (v3 lean)        │ │ (v2 long-term)│ │ (textbook frozen)  │
│                  │ │               │ │                    │
│ • NLE strategy   │ │ • Hypothesis  │ │ • ma_crossover     │
│ • LCS strategy   │ │   Generator   │ │ • bb_breakout      │
│ • DCF (future)   │ │   (L1+L2 LLM) │ │ • bb_reversion     │
│ • Hard Rust impl │ │ • DSL spec    │ │ • grid (retired)   │
│ • Cash flow focus│ │ • Auto-       │ │ • funding_arb (×)  │
│                  │ │   Validator   │ │                    │
│                  │ │ • Thompson    │ │ • Demo-only        │
│                  │ │ • Auto-Retire │ │ • A/B baseline     │
└──────┬───────────┘ └──────┬────────┘ └──────┬─────────────┘
       │                    │                  │
       └────────────────────┴──────────────────┘
                            │
              ┌─────────────▼────────────────┐
              │  Track-Aware Attribution     │
              │  • track enum on every row   │
              │  • independent P&L ledgers   │
              │  • independent GUI tabs      │
              │  • independent kill criteria │
              │  • independent risk budget   │
              └──────────────────────────────┘
```

**關鍵理解**：
- Track A、B、C **共用** Guardian/Lease/Risk SM/Stage gates → 一致的安全標準
- Track A、B、C **不共用** P&L 計算、GUI、kill 觸發、risk budget → 互不污染
- A 不會被 B 的「研究中虧損」拖累現金流評估
- B 不會被 A 的「短期 win streak」誤導為 alpha factory 有效
- C frozen 跑著當 baseline，提供「textbook 死局」對照

---

## §1 Track 定義與職責

### Track A — Direct Exploit（v3）

**目的**：8 週內 deliver 可衡量 live P&L；現金流優先

**內容**：
- NLE（New Listing Exploit）3 子策略
- LCS（Liquidation Cascade Scalper）
- DCF（DEX→CEX Front-run）— W8 後 SCALE 階段才上

**特性**：
- 工程師手寫 Rust struct（不走 DSL）
- 直接接 Strategy trait
- 短週期 retire（單個策略 alpha 半衰 4-12 週，到期 retire 不挽救）
- 風險容忍：每策略 30d 累計 < -10% allocated budget → 自動 PAUSE

**Owner**：PA→E1 標準鏈

### Track B — ASDS Factory（v2）

**目的**：12 個月內建成「策略發現工廠」，為將來 size 規模化做準備

**內容**：
- Tier 0 MarketStateSnapshot
- Tier 1 RegimeClassifier
- Tier 2 Hypothesis Generator（L1 Ollama + L2 via Cowork sub）
- Tier 3 Auto-Validator（CPCV + DSR）
- Tier 4 Thompson Sampling Paper allocator
- Tier 5-7 Demo/Live/Auto-Retire

**特性**：
- 策略以 DSL spec 表達，engine 編譯為 `GenericHypothesisStrategy` interpreter
- 每週產 5-15 hypothesis，多數 REJECTED
- 長週期實驗：每個 hypothesis 至少 7d paper + 14d demo evidence
- 風險容忍：track-level budget 嚴格 envelope；單 hypothesis < -20% → auto retire

**Owner**：PA→E1+MIT 鏈（含 AI-E for LLM prompt engineering）

### Track C — Baseline（既有 5 策略）

**目的**：對照組；證明「textbook 已死」這個 hypothesis；不投入新工程

**內容**：
- ma_crossover、bb_breakout、bb_reversion（demo only）
- grid v1（已 retire）、funding_arb（已 dormant，permanent retire）

**特性**：
- 完全 frozen：不調參、不改 indicator、不加 confluence
- Demo-only：永不 live
- 數據持續收集供 Track B 對照分析

**Owner**：無 active engineer；ops 只跑 healthcheck

---

## §2 Schema 設計（attribution 傳播）

### §2.1 新增 `track` enum

Rust（在 `openclaw_types/` 或 `openclaw_core/`）：

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Track {
    #[serde(rename = "direct_exploit")]
    DirectExploit,
    #[serde(rename = "asds_factory")]
    AsdsFactory,
    #[serde(rename = "baseline")]
    Baseline,
}

impl Track {
    pub const fn as_label(self) -> &'static str { ... }
}
```

PG enum：

```sql
CREATE TYPE strategy_track AS ENUM (
    'direct_exploit',
    'asds_factory',
    'baseline'
);
```

### §2.2 Schema migration（新 V100 / V101）

需要在以下表加 `track` 欄位（NOT NULL，default `'baseline'` for 既有 rows）：

| 表 | 加 track 欄位 | 理由 |
|---|---|---|
| `strategy_metadata`（或對應的 strategy registry）| ✅ | 每個 active strategy instance tag track |
| `decision_leases` | ✅ | lease attribution 跨入 fills |
| `fills` | ✅ | 真實 P&L 歸因 |
| `learning.strategy_trial_ledger` | ✅ | 16,212 rows backfill `baseline` |
| `learning.hypotheses` (new) | ✅ NOT NULL = `asds_factory` | 只 Track B 用 |
| `cost_edge_advisor_log` | ✅ | 分軌 cost gate evidence |
| `agent.ai_invocations` | ✅ | 分軌 LLM cost ledger |
| `executions_reports` / `execution_reports` | ✅ | slippage/latency per track |
| `positions` | ✅ | 持倉 attribution |

**migration 設計**：
- V100：CREATE TYPE + ALTER TABLE ADD COLUMN track NULL（先 nullable，避免 lock）
- 後台 backfill：`UPDATE ... SET track = 'baseline' WHERE track IS NULL`（既有 5 策略全標 baseline）
- V101：ALTER TABLE ALTER COLUMN track SET NOT NULL + DEFAULT
- 加 `CREATE INDEX ... ON (track)` 用於 GUI 查詢

Idempotent（per ADR-0011）：每個 ALTER 用 Guard B（`ADD COLUMN IF NOT EXISTS`）+ Linux PG dry-run preflight。

### §2.3 Decision Lease attribution 串接

在 `governance/decision_lease.py` 與 Rust 對應 struct：

```python
@dataclass
class DecisionLease:
    lease_id: str
    strategy_name: str
    track: Track          # NEW
    hypothesis_id: Optional[str]  # NEW (only AsdsFactory)
    symbol: str
    ...
```

Pipeline 在 `step_4_5_dispatch.rs` emit StrategyIntent 時自動填 track（從 strategy registry lookup）。

### §2.4 P&L view 分軌

新建 PG views：

```sql
-- Track A view
CREATE VIEW track_direct_exploit_daily AS
SELECT date_trunc('day', fill_ts) as day,
       SUM(realized_pnl_usdt) as daily_pnl,
       COUNT(*) as n_fills,
       AVG(net_edge_bps) as avg_edge_bps
FROM fills
WHERE track = 'direct_exploit'
GROUP BY 1;

-- Track B view（類似）
-- Track C view（類似）

-- Cross-track summary
CREATE VIEW track_summary_daily AS
SELECT day, track, daily_pnl, n_fills, avg_edge_bps
FROM (
    track_direct_exploit_daily UNION ALL
    track_asds_factory_daily UNION ALL
    track_baseline_daily
);
```

GUI 直接 query 這些 views，互相隔離。

---

## §3 Risk Budget 分軌切分

### §3.1 $10k Demo

```
Demo total:                 $10,000
├─ Track A DirectExploit:   $4,000 (40%)
│   ├─ NLE budget:          $2,000
│   ├─ LCS budget:          $1,500
│   └─ Reserve (future):    $500
├─ Track B AsdsFactory:     $5,000 (50%)
│   ├─ Paper Tier 4:        $3,000 (spread over active hypothesis)
│   └─ Demo Tier 5 canary:  $2,000 (1 hypothesis at a time)
├─ Track C Baseline:        $1,000 (10%)
│   ├─ ma_crossover:        $400
│   ├─ bb_breakout:         $300
│   └─ bb_reversion:        $300
```

### §3.2 $1k Live

```
Live total:                 $1,000
├─ Track A DirectExploit:   $700 (70%) ← cash flow priority
│   ├─ NLE budget:          $400
│   ├─ LCS budget:          $300
│   └─ DCF (W8+ unlock):    reserved
├─ Track B AsdsFactory:     $100 (10%)
│   └─ 1 PROMOTED hypothesis at a time, $100 cap
├─ Track C Baseline:        $0
│   └─ Never live (frozen demo only)
└─ Operator Reserve:        $200 (20%) ← discretionary
```

### §3.3 Per-track risk envelope enforcement

新增到 risk_config_*.toml：

```toml
[track_budgets.demo]
direct_exploit_max_pct = 40
asds_factory_max_pct = 50
baseline_max_pct = 10

[track_budgets.live]
direct_exploit_max_pct = 70
asds_factory_max_pct = 10
baseline_max_pct = 0
reserve_pct = 20

[track_kill_thresholds]
direct_exploit_w8_min_pnl_usdt = -100
asds_factory_w24_min_promoted_count = 3
```

**Guardian check 6（新）**：拒絕任何讓 track 累計 notional 超過 track budget 的 trade。

LOC：~200 Rust + ~100 Python + ~80 SQL migration

---

## §4 Engineering Capacity 切分

### §4.1 Sprint N+1 ~ N+2（8 週 = v3 critical window）

```
E1 capacity 5 active + 1 stand-by:

Track A:    60%  (3 E1)
  - NLE listing watcher + 3 子策略 + risk carve-out
  - LCS cluster detector + scalper
  - Demo soak + 第一筆 live deploy

Track B:    30%  (1.5 E1)
  - Tier 0 MarketStateSnapshot (cross-asset panel)
  - Tier 1 RegimeClassifier L0 (classical only)
  - V100/V101 migration + Track schema

Shared:     10%  (0.5 E1)
  - Execution hardening (PostOnly 85%, slippage tier)
  - GUI tab framework + 3 Track tabs skeleton
```

### §4.2 Sprint N+3（W8 fork moment）

```
Operator W8 decision branches:

If Track A SCALE (live cum P&L > $50):
  Track A: 40% — add DCF, scale to $700 live
  Track B: 50% — Tier 2 Hypothesis Generator first cycle
  Shared:  10%

If Track A PIVOT (demo good, live disappointing):
  Track A: 30% — maintenance only; build signal service infra
  Track B: 60% — accelerate ASDS
  Signal Service Track (new): 10% — Telegram + Stripe

If Track A KILL (demo & live both fail):
  Track A: 0%  — retire all
  Track B: 80% — ASDS becomes sole hope
  Codebase IP sale prep: 20%
```

### §4.3 Sprint N+4 ~ N+5

Track B 接力，把 Tier 2-5 build out，N+5 上線首個 ASDS-generated hypothesis 進 demo。

---

## §5 GUI 設計（獨立顯示）

### §5.1 三個獨立 tab + 一個總覽

在 OpenClaw Control Console 加 4 個 tab：

| Tab name | URL | 內容 |
|---|---|---|
| `tab-track-summary` | `/console#tracks` | 3 track 並排 cumulative P&L、active strategies count、sharpe、DD |
| `tab-track-exploit` | `/console#tracks/exploit` | NLE/LCS 即時面板、近 30d listing events、cluster trigger log、per-strategy daily P&L |
| `tab-track-asds` | `/console#tracks/asds` | Hypothesis tree（DRAFT/REGISTERED/EXPERIMENTING/EVIDENCE_GATE/PROMOTED/EXPIRED）、active paper bandit allocations、LLM cost ledger |
| `tab-track-baseline` | `/console#tracks/baseline` | 5 textbook 策略 demo P&L、與 Track A/B 對比、A/B test outcomes |

既有 `tab-strategy` 改為 track-aware（按 track filter strategies）。

### §5.2 Summary tab mock

```
┌─────────────────────────────────────────────────────────────┐
│ Track Performance Dashboard                  [Live | Demo]  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Track A: Direct Exploit       Live: +$42 (+4.2%)  ↗        │
│  ─────────────────────         Demo: +$387 (+3.9%)  ↗       │
│    Active: NLE, LCS            Sharpe (30d): 1.42           │
│    Trades 7d: 47                Max DD: -1.8%                │
│                                                              │
│  Track B: ASDS Factory         Live: $0 (n/a)                │
│  ─────────────────────         Demo: -$23 (-0.5%)  →        │
│    Active hypothesis: 12       LLM cost MTD: $4.30          │
│    State: EXPERIMENTING        ✓ Within envelope             │
│                                                              │
│  Track C: Baseline             Live: $0 (frozen)             │
│  ─────────────────────         Demo: -$45 (-4.5%)  ↘        │
│    Active: ma/bb_brk/bb_rev    Note: confirming textbook    │
│                                       dead hypothesis        │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  Cross-Track Insights:                                       │
│  • Track A outperforming Track C by +8.4 pp/30d (alpha real) │
│  • Track B hypothesis #h_lcs_v2 in EVIDENCE_GATE — review    │
│  • Track B suggested NLE mutation: shorten timeout 300→180s  │
└─────────────────────────────────────────────────────────────┘
```

LOC：~1200 JS（4 tabs，純前端，後端複用既有 REST endpoint with `?track=` filter）。

### §5.3 Mobile / Gateway relay

Gateway 不變（per ADR-0013），只 push aggregated track summary 到 mobile（操作員夜間查看現金流即可）。

---

## §6 跨軌互動規則（critical）

兩軌**共享 infrastructure，但不互相覆蓋**。明確規則：

### §6.1 允許的跨軌互動

✅ **Track B 可以「mutate」Track A 的策略 → 產生新 hypothesis**：
- Track B LLM 讀 Track A NLE 表現數據 → 提議 `nle_mutation_v2: shorten timeout 300→180s, add btc_dom filter` → 寫入 `learning.hypotheses` (track=asds_factory)
- 這個 mutation hypothesis 走 ASDS pipeline，**不影響原 NLE Rust struct**
- 如果 mutation hypothesis 在 demo 跑贏原 NLE，operator 可以決定「人工 port back」改 Track A NLE 參數

✅ **Track A 數據 feed Track B regime classifier 訓練**：
- Track A 的 fills + P&L 是 ground truth label，可以 train Track B regime classifier 識別 "NLE-favorable regime"
- 數據單向流：A → B，不反向

✅ **共享 cost_edge_advisor**：
- 同一個 cost gate 服務兩軌，但 log row 分 track
- Track A breakeven α calculation 用同一公式

### §6.2 禁止的跨軌互動

❌ **Track B hypothesis 不能修改 Track A 策略**（即使 mutation 證明更好）：
- LLM 永遠不寫 Rust code
- 任何 port back 都需 operator + PA 人工 review + 走 E2/E4 鏈

❌ **Risk budget 不能跨軌借用**：
- Track A 用完 $700 live 就 cap，**不允許**從 Track B 的 $100 借
- 一個 trade 必須屬於一個 track

❌ **Kill criteria 不互鎖**：
- Track A W8 KILL **不**自動 KILL Track B
- Track B 6-month abort **不**影響 Track A 繼續跑

### §6.3 跨軌衝突仲裁

若 Track A NLE 策略和 Track B 某 hypothesis 同 tick emit 對同一 symbol 的相反方向 intent：

1. Decision Lease state machine 已內建 conflict-detection
2. **規則**：Direct Exploit 優先（cash flow > experimentation）
3. Track B intent 被 Lease state machine 標為 `BLOCKED_CROSSTRACK`，落 audit log
4. Guardian veto 仍可獨立 fire

LOC：~120 Rust conflict resolver。

---

## §7 Kill Criteria 隔離（per-track 獨立觸發）

### §7.1 Track A（Direct Exploit）kill ladder

```
W4:  Demo evidence check
     if NLE + LCS demo cumulative < 0 bps net edge:
         WARN: 縮減 size 50%，繼續 4 週觀察
     else: continue full size

W8:  Live cumulative review
     if Live cum P&L < -$100:
         KILL Track A → strategies retire, PIVOT to signal service
     if Live cum P&L $-100 to $0:
         PAUSE: 縮到 $200 live，4 週 retry
     if Live cum P&L > $0:
         SCALE: 增 budget 或加 DCF

W12: PIVOT 後 4 週
     if PIVOTED to signal service:
         signal service subs < 5 → KILL Track A entirely

W24: Hard final review
     if Track A 累計 live revenue + signal service revenue < $500:
         HARD KILL → IP sale / shutdown
```

### §7.2 Track B（ASDS Factory）kill ladder

```
N+3 (W6):  First hypothesis end-to-end
     if no hypothesis 通過 Auto-Validator (Tier 3):
         WARN: review LLM prompt engineering

N+5 (W10): First Demo canary
     if 0 hypothesis 達 EVIDENCE_GATE:
         WARN: extend Tier 4 paper observation 14d

N+6 (W12): Tier 5 first demo
     if 0 hypothesis 達 PROMOTED in 4 weeks demo:
         REDUCE Track B capacity from 30% → 10%

W24 (6 month): Major review
     if PROMOTED hypothesis count < 3:
         ABORT Track B → archive schema, retire LLM jobs, push to Year 3
     if PROMOTED ≥ 3 AND ≥1 達 Sharpe > 1.0 demo 30d:
         GRADUATE Track B → operator review for live promotion
```

### §7.3 Track C（Baseline）kill

Frozen 不啟動 kill；C 永遠跑當對照。只 7d run 不消耗 engineering capacity。

### §7.4 Kill 隔離保證

新增 PG check constraint：

```sql
-- 確保 kill 事件只影響該 track 的 strategy
CREATE TABLE track_kill_events (
    track strategy_track NOT NULL,
    event_ts TIMESTAMPTZ NOT NULL,
    trigger TEXT NOT NULL,  -- 'W8_cum_pnl' / 'W24_review' etc
    affected_strategies TEXT[] NOT NULL,
    operator_signoff TEXT,
    CHECK (track IS NOT NULL)
);

-- 任何 strategy retire 操作必須記錄 track，且不能跨軌
CREATE FUNCTION retire_strategy(...) ...
  -- 在 SQL function 內 assert source_strategy.track = retire_event.track
```

LOC：~150 SQL + ~200 Python kill orchestrator。

---

## §8 修訂 Sprint Plan（雙軌並行）

替換 TODO.md §1 sprint banner：

| Sprint | Week | Track A 任務 | Track B 任務 | Shared | Milestone |
|---|---|---|---|---|---|
| **N+0** | 已過 | — | — | — | 65% |
| **N+1** | W3-W4 | NLE 3 子策略 + listing watcher + carve-out risk | V100/V101 Track schema migration + Tier 0 cross-asset panel | Execution hardening + GUI Track tabs skeleton | 67% |
| **N+2** | W5-W6 | LCS cluster detector + LCS strategy + Track A 14d demo soak | Tier 1 RegimeClassifier L0 + HypothesisSpec schema + AutoRetire scaffolding | Decision Lease track attribution + cost_edge_advisor track tag | 70% |
| **N+3** | W7-W8 | **Track A first live deploy** + W8 fork review | Tier 2 L1 Ollama mutator + Tier 3 Auto-Validator (CPCV + DSR) | Cross-track conflict resolver + Summary GUI tab | 75% / **W8 verdict** |
| **N+4** | W9-W10 | (Branch: SCALE add DCF / PIVOT signal service / KILL) | Tier 2 L2 via Cowork integration + Tier 4 Paper Thompson allocator | Multi-agent Scout dynamic universe (benefits both) | 80% |
| **N+5** | W11-W12 | Track A maintenance + scale-up (if SCALE) | Tier 5 auto Demo Canary + first hypothesis end-to-end | Per-hypothesis live budget (W-AUDIT-8g lite) | 85% |
| **N+6** | W13-W14 | Track A 6-month review + W24 prep | Tier 6 Live promotion (if any hypothesis ready) + Tier 7 AutoRetire | ASDS dashboard + 6-month aggregate review | 88% |

### §8.1 N+1 詳細（兩軌並行第一 sprint）

| Task | Track | LOC | Owner |
|---|---|---|---|
| V100 migration: Track enum + ADD COLUMN nullable | shared | 200 SQL | E1 |
| V101 migration: backfill + NOT NULL + index | shared | 100 SQL | E1 |
| Bybit announcement API watcher (5min poll) | A | 200 Py | E1a |
| `learning.new_listings` table + historical backfill | A | 100 SQL | E1 |
| NLE Strategy A (overshoot fade) Rust struct | A | 280 Rust | E1 |
| NLE risk carve-out: first-1h vol estimate, PostOnly disable, size cap | A | 180 Rust | E1 |
| Tier 0 CrossAssetPanel collector + per-tick snapshot | B | 400 Rust | E1 |
| Tier 0 Microstructure features (orderflow imbalance proxy) | B | 250 Rust | E1 |
| Universe tier classifier (tier_A/B/C) | shared | 150 Rust | E1 |
| PostOnly success-rate hardening (existing audit Phase 1) | shared | 300 Rust | E1 |
| GUI Track tab skeleton (4 tabs empty shell) | shared | 400 JS | E1a |

**Total**: ~2560 LOC across shared + 2 tracks. 1 sprint 完成 doable with 5+1 E1 capacity at 60/30/10 split.

### §8.2 後續 sprint 細節省略（同邏輯延展）

每個 sprint 內部按 60/30/10（W8 前）or branch-dependent 配置；具體 task breakdown 在 N+2 / N+3 sprint kickoff 時 PA 出 dispatch plan。

---

## §9 Acceptance Criteria（per track 獨立）

### §9.1 Track A acceptance

| Phase | Acceptance | Owner |
|---|---|---|
| W2 | NLE A active in demo + listing watcher daily-poll OK | E1+QC |
| W4 | NLE B/C + LCS active；4 active strategies in Track A | E1 |
| W6 | Track A demo 14d Sharpe > 1.0；W6 operator review | QC+PM |
| W8 | Track A first live fills；live cum P&L 公開（任何數字都 acceptable）；fork verdict signed | operator |
| W12 | (if SCALE) Track A live cum P&L > $100 | operator |
| W12 | (if PIVOT) signal service launched + ≥5 subs | ops |
| W24 | Track A or PIVOT total revenue ≥ $500 | operator |

### §9.2 Track B acceptance

| Phase | Acceptance | Owner |
|---|---|---|
| W4 | Track schema migrated + Tier 0 snapshot live | E1+MIT |
| W6 | RegimeClassifier 5-class output 落 metrics | QC |
| W8 | HypothesisSpec validator pass synthetic + first L1 mutation hypothesis 通過 | AI-E+QC |
| W10 | Tier 4 Thompson allocator 跑 ≥4 hypothesis paper | E1+MIT |
| W12 | First hypothesis 進 EVIDENCE_GATE | PM |
| W20 | First hypothesis PROMOTED to demo | PM |
| W24 | ≥3 hypothesis PROMOTED；major review verdict | operator |

### §9.3 Track C acceptance

| Phase | Acceptance | Owner |
|---|---|---|
| Ongoing | 5 textbook 跑 demo，無 engineering touch | ops |
| W12 | 對比 report: Track A vs Track C alpha differential | QC |
| W24 | 確認「textbook 已死」evidence ≥ p=0.95 | QC |

---

## §10 GUI Acceptance（獨立顯示驗證）

操作員任何時間打開 `tab-track-summary` 應該能看到：

✅ **3 個 track 並排 cumulative P&L** — 數字不互相滲透
✅ **Per-track active strategies count** — track 邊界清楚
✅ **Per-track Sharpe + DD + win rate** — 獨立計算
✅ **LLM cost ledger per track** — Track B cost ≠ Track A cost
✅ **Cross-track insight section**（可選 advisory）— 不是強制，只是給 operator 看 cross-comparison

如果某天 Track A 大賺 +$200，Track B 大虧 -$50，summary 應該各自顯示，不會混算 +$150 誤導 operator。

---

## §11 修訂 LLM 經濟學（雙軌共享 envelope）

```
Monthly LLM costs:

Track A (Direct Exploit):
  - Daily Cowork session for NLE/LCS parameter tuning: $0 (uses Claude Max sub)
  - Local Ollama for parameter mutation: $0
  Subtotal:   $0/mo

Track B (ASDS Factory):
  - L1 Ollama hypothesis mutation (continuous): $0
  - L2 via Cowork sub (daily hypothesis review): $0
  - L2 emergency API (regime shift, postmortem): $5-15/mo
  Subtotal:   $5-15/mo

Track C: $0

Total new spend:  $5-15/mo (down from v2 plan's $30-50/mo)
```

**關鍵**：v3 lean 的「用訂閱不付 API」原則延伸到 v4——Cowork scheduled tasks 用你已付的 $400/月 subs；只有 special trigger 才動 API。

---

## §12 ADR / governance changes

新需要 ADR：

| ADR | 內容 | Status |
|---|---|---|
| **ADR-0024** | Layer 2 autonomous hypothesis generation within envelope（v2 草稿，仍 needed for Track B） | PROPOSED |
| **ADR-0025** | Track-based strategy attribution and isolation（本文 §1-§7 形式化） | PROPOSED |
| **ADR-0026** | Direct Exploit strategies bypass Tier 3 Auto-Validator（NLE/LCS 走人工 backtest review，因為 capacity-constrained niche 不適合 CPCV） | PROPOSED |

修改既有 ADR：
- ADR-0018 funding_arb retire → 加 carve-out 註：「Track C frozen 不適用，可作 baseline demo run」

---

## §13 與既有 governance 不變式關係

雙軌制**完全相容**既有不變式：

| 不變式 | 雙軌制下狀態 |
|---|---|
| 16 條根原則（CLAUDE.md §二） | ✅ 全保留；Track 只影響 attribution，不影響 priority order |
| 5-gate live boundary | ✅ 共用；Track A/B 都走同樣 5 gate |
| Guardian veto authority | ✅ 共用；Guardian 不分 track 一律 veto |
| Decision Lease state machine | ✅ 增 track 欄位，但 state transition 邏輯不變 |
| Stage 0 / 0R / 1 / 2 / 3 / 4 canary | ✅ 兩軌都走完整 canary（A 比 B 快因為策略簡單） |
| Replay engine | ✅ 共用；按 track filter |
| AMD-2026-05-15-01 Demo micro-canary | ✅ 共用；Stage 1 仍 1 strategy × 1 symbol × 7d |
| ADR-0020 Layer 2 manual-only | ⚠️ Track B 需 ADR-0024 carve-out（仍 in progress） |

**沒有任何不變式被打破**。

---

## §14 不做的事（v4 specific）

11. ❌ **不要為 Track A 寫 DSL spec**（A 是 Rust hand-coded，不入 hypothesis pipeline）
12. ❌ **不要混算 P&L**（任何 dashboard query 必須 `WHERE track=...`）
13. ❌ **不要 Track B kill 觸發 Track A retire**（反之亦然）
14. ❌ **不要在 GUI 顯示「total P&L」當主指標**——必須分軌呈現
15. ❌ **不要等 Track B 才上 Track A**（A 是 first，B 是 follow）
16. ❌ **不要為 Track C 投入 engineering**（A/B 已耗盡 capacity）
17. ❌ **不要讓 LLM 寫 Rust（Track A 或 B 都不行）**——LLM 只寫 DSL spec
18. ❌ **不要 risk budget 從 Track A 借給 B**（envelope 是 hard）

---

## §15 立即下一步（operator decisions）

按重要性排序：

1. ✅ **批准 v4 雙軌制取代 v2 + v3 並排放法**
2. ✅ **批准 ADR-0025 Track-based attribution**（新 ADR 草稿）
3. ✅ **批准 ADR-0026 Direct Exploit bypass CPCV**（新 ADR 草稿；NLE/LCS 不走 ASDS validator）
4. ⏸️ **批准 ADR-0024 L2 autonomous in envelope**（Track B 所需；可 N+2 再決）
5. ✅ **批准 V100/V101 Track schema migration**（最緊；先 land 才能後續 attribution）
6. ✅ **批准 Sprint N+1 plan §8.1（60/30/10 capacity split + 2560 LOC scope）**
7. ✅ **批准 W8 fork criteria + W24 hard kill**（per §7.1 / §7.2）
8. ✅ **批准 risk budget 切分（§3.1 / §3.2）**

完成 1-3 + 5-8（4 可 defer），可立即 dispatch PA 拆 Sprint N+1 詳細 spec。預計 W2 第一個 NLE 上線 demo，W6 Track A demo evidence + W8 第一筆 live。

---

## §16 結語：為什麼雙軌制是對的決定

**冷酷理由 1：風險分散**
- Track A 8 週後可能 KILL；Track B 12 個月後可能 abort
- 兩軌獨立 kill ladder = 一軌死另一軌活
- 比 v3 純 lean（all eggs in NLE/LCS basket）安全
- 比 v2 純 ASDS（all eggs in factory basket）有現金流

**冷酷理由 2：時間維度互補**
- Track A：8 週 first live P&L，月度現金流
- Track B：12 個月 first PROMOTED hypothesis，但規模化後 unlocking unbounded alpha space
- 短期養活長期，長期撐起短期天花板

**冷酷理由 3：infrastructure 重用率最大化**
- Guardian、Decision Lease、Replay、5 SM 全部 shared
- 額外工程 = Track schema + GUI tabs（~600 LOC overhead）
- 比起 v3 砍 v2 浪費已寫的 hypothesis pipeline schema，雙軌完美 amortize

**冷酷理由 4：給 operator 真實 optionality**
- W8 fork：A SCALE / PIVOT / KILL，B 不受影響
- W24 review：A 信號服務 viable / B 找到真 alpha source
- 任何 branch 都不會全盤皆輸

**這是我 v1-v4 設計裡最 mature 的版本。** v1 太 conservative、v2 太 academic、v3 太 aggressive；v4 把三者各自最強的部分組合，給你**短期現金流 + 長期 moat + 明確 fork 點**的最大 surface area。

---

## §17 References

- v1: `srv/2026-05-20--strategy-architecture-redesign-recommendation.md`
- v2: `srv/2026-05-20--autonomous-strategy-system-v2.md`
- v3: `srv/2026-05-20--lean-direct-alpha-capture-v3.md`
- ADR-0011 V### migration mandatory Linux PG dry-run
- ADR-0020 Layer 2 manual-only（待 ADR-0024 amend）
- AMD-2026-05-15-01 Canary rebase replay preflight + demo micro-canary
- CLAUDE.md §二 16 root principles

---

**END v4**

**Sprint N+1 雙軌並行 ready to dispatch on operator approval.**
