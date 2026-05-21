# 玄衡 · Arcane Equilibrium — Dual-Track Architecture v4.1（reviewer corrections incorporated）

**日期**：2026-05-20
**Author**：Claude（after reviewer parallel audit + operator approval to apply corrections）
**Status**：DRAFT — Supersedes v4；待 AMD-2026-05-20-02 ratify 後成 active planning authority
**Operator 約束**：demo $10k + live $1k；要 v3 短期現金流 + v2 長期 ASDS 並行；雙軌數據獨立計算、獨立顯示
**核心改動 vs v4**：
- ✅ Schema 對齊真實 DB 表名（grep verified `trading.* / learning.* / agent.*`）
- ✅ Phase 0 加 migration drift reconcile（V096-V098 already in repo，須 Linux DB 對齊）
- ✅ ADR-0026 tighten：bypass CPCV → 強制 event-study + pre-registration + replay 三件套
- ✅ Track 順序：LCS-first，NLE 改 watch-only 收 shadow 樣本
- ✅ W8 milestone reframe：demo evidence + live-ready proof，**不**承諾 first live deploy
- 🟡 Capacity split 50/10/40（Track A 50% / Track B 10% Hypothesis Ledger only / Shared 40%）
- 🟡 GUI 漸進式：N+1 只 1 tab summary，N+2 補 exploit tab，後面 defer

---

## §0 What changed from v4 — One-page diff

| 議題 | v4 原稿 | **v4.1 修正** | 來源 |
|---|---|---|---|
| Schema 表名 | `strategy_metadata / decision_leases / execution_reports / positions` (虛構) | `trading.fills/intents/orders/position_snapshots + learning.lease_transitions/strategy_trial_ledger/cost_edge_advisor_log + agent.ai_invocations/decision_objects` (grep verified) | reviewer #1 |
| Migration drift | 隱含假設 head=V095 | 明確 Phase 0：repo V098 ↔ Linux DB head reconcile，**先對齊再 dispatch** | reviewer #2 |
| W8 Track A 目標 | "first live deploy" | "demo evidence + live-ready proof packet"（live deploy 推到 P0-LG/OPS 全清之後）| reviewer #3 |
| CPCV bypass | "manual backtest review by PA + QC" | **event-study + pre-registration + replay** 三件套 | reviewer #4 |
| Track A 順序 | NLE first / LCS second | **LCS first**（DB 已有 data 可立即 replay）/ NLE shadow-collect 排第二 | reviewer #5 |
| Capacity split | 60/30/10 | **50/10/40**（Track B 縮為 Hypothesis Ledger only；shared 加重） | 我的 push-back vs reviewer 0% Track B |
| GUI | 4 tabs skeleton N+1 land | 1 tab summary N+1 / exploit tab N+2 / 後續 defer | 我的 push-back vs reviewer SQL-only |

---

## §1 五個 reviewer corrections — 為什麼接受

### §1.1 Schema 名稱對齊真實 DB（accepted）

v4 原稿用了我從 Rust 命名 pattern 推測的表名，沒做 DB introspection。grep `sql/migrations/V*.sql` 結果：

**Reviewer 對的部分**：
- ❌ `strategy_metadata` 不存在
- ❌ `decision_leases` 不存在；真實是 `learning.lease_transitions`（V054） + `agent.decision_objects`（V064）
- ❌ `execution_reports` 不存在
- ❌ `positions` 不存在；真實是 `trading.position_snapshots`

**真實表 inventory**（用作 V101 attribution target）：

```
trading.fills                  ← P&L attribution row authority
trading.intents                ← StrategyIntent emit
trading.orders                 ← Bybit order lifecycle
trading.position_snapshots     ← position attribution（取代 fake `positions`）
trading.signals                ← Strategy.on_tick raw signal（optional Phase 1.5）
learning.lease_transitions     ← Decision Lease state transitions（取代 fake `decision_leases`）
learning.strategy_trial_ledger ← edge estimation cycle（16,212 rows）
learning.cost_edge_advisor_log ← cost gate evidence
agent.ai_invocations           ← LLM cost ledger
agent.decision_objects         ← Decision Lease canonical store（typed lineage 根節點）
learning.hypotheses (NEW)      ← Track B hypothesis registry
```

**Phase 1 V101 minimal scope**：8 個既有表 + 1 個新表 = 9 表 add `track` column。

`trading.signals` 和 `agent.decision_edges/state_changes/execution_idempotency_keys` 等 lineage-tracing 表暫不加 `track`（attribution 可由上游 fills/orders/lease_transitions join 推導出），降低 V101 surface area。

### §1.2 Migration drift reconcile 為 Phase 0（accepted）

grep verified：repo `sql/migrations/` 已有 V096（drop_dead_learning_tables）、V097（lg5_attribution_healthcheck_indexes）、V098（governance_audit_log_halt_event_types）。

Reviewer 指出 Linux DB `_sqlx_migrations` 可能只到 V096。在這個 drift 下直接 dispatch V101 會：
1. 違反 ADR-0011（Linux PG dry-run mandatory）
2. 可能觸發 sqlx 認為「migration 序列 broken」拒絕 apply
3. 給 PA refresh dispatch plan 留下挖坑

**v4.1 強制 Phase 0**：
```
Phase 0 Migration Drift Reconcile（before Sprint N+1 任何 IMPL）：
  Step 1: ssh trade-core → SELECT version FROM _sqlx_migrations ORDER BY version DESC LIMIT 5
  Step 2: 對比 repo sql/migrations/V*.sql head
  Step 3: 若 drift > 1 → 列出 missing migration，PA 排程 catch-up apply
  Step 4: 所有 catch-up migration 完成 + healthcheck passed → 才解鎖 V101 dispatch
  Step 5: V101 號碼 PA dispatch 時 final 鎖定（可能 V101 / V102 / 更後依 LG-3 + W-AUDIT-8a 殘留決定）
```

### §1.3 W8 milestone 從「first live」改「demo evidence + live-ready proof」（accepted）

Reviewer 完全對。當前 active P0/LG/OPS blockers：
- `P0-ENGINE-HALTSESSION-STUCK-FIX`（v56 incident，PA spec 已派）
- `P0-EDGE-1`（edge net-positive 決議）
- `P0-LG-1/2/3`（H0 production caller / pricing binding / supervised live SM；LG-3 IMPL dispatch pending）
- `P0-OPS-1..4`（HTTPS / credential rotation / legal+ToS / first-day runbook）

任何「W8 first live deploy」承諾隱含這些 blocker 8 週內清完——**根本不成立**，LG-3 IMPL 連 dispatch 都沒派。

**v4.1 W8 milestone reframe**：

| Original v4 W8 target | v4.1 修正 W8 target |
|---|---|
| Track A first live fills | Track A LCS demo 14d evidence packet：cumulative net edge / Sharpe / DD / replay match rate |
| Track A live cum P&L < -$100 → KILL | Track A LCS demo cum net edge < -10 bps → KILL |
| Track A live cum P&L > $0 → SCALE | Track A LCS demo Sharpe > 1.0 + DSR > 0.85 → 進 Stage 1 Demo micro-canary; live deploy 等 P0/LG/OPS clear |

「Live deploy」時間表改為**條件式**：
- P0-LG/OPS gates 全清 + Track A 完成 Stage 1+2 demo canary → operator 決議是否啟動 $200 live envelope
- 預期最早 N+5～N+6（W10-W14）；悲觀帶 N+7+

### §1.4 ADR-0026 tighten event-study + pre-registration + replay（accepted）

Reviewer 對：「manual backtest review」是 reviewer-bias 高的軟門檻。替換為三件套：

**1. Event-study methodology**（Brown & Warner 1985；MacKinlay 1997）：
- 對每個 event（listing announcement / liquidation cluster）定義 estimation window + event window + post-event window
- Cumulative Abnormal Return (CAR) 統計 vs benchmark
- t-test on average CAR with appropriate variance correction

**2. Pre-registration**（OSF / AsPredicted style）：
- 在跑 backtest 之前 **寫死** 進 PG `learning.hypothesis_preregistration` 表：
  ```sql
  expected_alpha_bps NUMERIC NOT NULL,
  expected_n_events_min INT NOT NULL,
  expected_sharpe_min NUMERIC NOT NULL,
  decision_threshold_pct NUMERIC NOT NULL,  -- e.g. 0.05
  registered_at TIMESTAMPTZ NOT NULL,
  ```
- 結果 vs pre-registration 比對；若實際 effect size 顯著偏離預期 → 不 pass
- 防 p-hacking、防 garden-of-forking-paths

**3. Replay engine（既有 Stage 0R）**：
- 用真實歷史 fills / orderbook / liquidation 數據跑 replay
- replay match rate（replay 預測 fill vs 歷史實際 fill）≥ 80%
- Stage 0R 既有 infrastructure 不需新建

**ADR-0026-v2 gate sequence**：
```
Track A strategy 進 paper：
  1. Pre-registration 寫死 → PG
  2. Replay run 30d 歷史 data
  3. Event-study CAR + t-test → 統計顯著（p < 0.05）
  4. Replay match rate ≥ 80%
  5. PA + QC 5-day window review（仍保留人工監督，但不再是唯一門檻）
  → PASS 才進 Stage 0 paper
```

統計嚴格性現在 ≥ CPCV，且適配 event-driven niche（CPCV 在事件驅動數據上 violation i.i.d. 假設）。

### §1.5 Track A 順序改 LCS-first（accepted）

Reviewer 的 framing 完全正確：**「能不能立即 replay」是排序維度，不是「單筆 alpha 高低」**。

**LCS 為什麼可以立即動工**：
- V095 `market_liquidations_identity` 已 land
- Bybit allLiquidation WS 500ms stream + orderbook + publicTrade 全部都有歷史 row 在 `trading.fills` / `trading.signals` 旁邊的 raw data
- 30-180s reaction window 可以對 60+ days 歷史完整 replay
- 第 2 週就能出第一個 event-study 統計報告

**NLE 為什麼不能立即動工**：
- 沒有 listing event table（V101 需新建）
- announcement watcher 需要寫 + 找穩定來源（Bybit RSS / API polling 可能限速）
- 樣本累積：~5-10 listing/月 → 第一個可信統計報告至少 W6-W8 才有
- 替代方案：用過去 6 個月歷史 listing 反推，但 Bybit 沒對外暴露 historical listing API，需 scrape

**v4.1 順序**：

```
W1-W2:
  Track A: LCS event-study + replay (60d historical) + pre-registration
  Track A 平行: NLE listing watcher 上線（不交易，只收 shadow events）

W3-W4:
  Track A: LCS demo deploy（依 W1-W2 event-study pass 結果）
  Track A: NLE 第一個 listing event shadow log

W5-W6:
  Track A: LCS 14d demo soak（cumulative evidence）
  Track A: NLE 累積 3-5 listing events → 第一個 event-study report

W7-W8:
  Track A: LCS evidence packet → operator W8 review
  Track A: NLE demo deploy 決議（若 event-study pass）

W8 fork：
  LCS demo Sharpe > 1.0 → Stage 1 micro-canary 預備
  LCS demo Sharpe < 0.5 → KILL LCS，all-in NLE
  Both fail → KILL Track A，PIVOT signal service
```

NLE 的 alpha 高（80-150 bps）仍是真的，但 ROI per engineering hour 不如 LCS 即可驗證的優勢。LCS 證明可行後，NLE 是 sprint N+3-N+5 的擴展，不是 N+1-N+2 的 first bet。

---

## §2 兩個 push-back（不接受 reviewer 過度保守）

### §2.1 Track B 不歸零，縮為 10% Hypothesis Ledger only

Reviewer 主張「Track B 完全砍掉，只做 Hypothesis Ledger」。**我半接受**：

接受：
- Tier 2 LLM Hypothesis Generator → DEFER 到 W8 fork 之後
- Tier 3 Auto-Validator (CPCV + DSR) → 不在 N+1 ~ N+2 build
- Tier 4 Thompson allocator → DEFER
- Tier 5-7 Demo/Live canary / AutoRetire → DEFER

不接受：
- **Tier 0 + Tier 1 不能砍**——這兩條是 Track A LCS 也需要的共享基礎建設：
  - Tier 0 Microstructure features（orderflow imbalance、liquidation cluster encoding）= **LCS 訊號的核心** instrumentation
  - Tier 1 RegimeClassifier L0（classical only，ATR percentile + ADX + Hurst）= LCS 的 regime gate filter

→ **這兩個我把分類從「Track B」改為「Shared」**，capacity 從 Track B 30% 抽走、轉到 Shared 40%。

剩下的 Track B 10% capacity 只做：
1. `learning.hypotheses` table（V101 內含，0 額外 cost）
2. `learning.hypothesis_preregistration` table（per ADR-0026-v2 §1.4）
3. Hypothesis Ledger CRUD API（~100 LOC Python）
4. 接 Cowork scheduled task 每日寫 1 個 manual hypothesis（無 LLM auto-generation）

**reviewer 想要的「不在 live blockers 未清時吃太多」是對的，但「歸零」過頭——Tier 0/1 是 cross-cutting 基礎建設，不是 ASDS-only 投資。**

### §2.2 GUI 不砍到 SQL views + CLI，採漸進式

Reviewer 主張「先只做 SQL views + CLI/簡單 dashboard，不做 4 個完整 GUI tab」。**我不接受全砍**：

理由：
1. operator 明確說「沒時間人工分析」，CLI 違反這條
2. 既有 OpenClaw Control Console framework 已建好，加 tab marginal cost 低
3. 24/7 visibility on per-track P&L 是基本需求

**v4.1 漸進式 GUI**：
- **N+1**：1 個 tab — `tab-track-summary`（3 軌並排 cum P&L，純讀 V101 view，~250 LOC JS）
- **N+2**：補 `tab-track-exploit`（NLE/LCS 即時面板，~400 LOC JS）
- **N+3+**：依需求補 `tab-track-asds` 和 `tab-track-baseline`（若 Track B 真的有 hypothesis ledger 內容值得專屬顯示）

這比 v4 的 4 tabs N+1 land 溫和，比 reviewer 的「不做 GUI」務實。

---

## §3 修訂 Capacity Split

```
v4 原 N+1 ~ N+2:                    v4.1 修正 N+1 ~ N+2:
  Track A:    60% (3 E1)              Track A:    50% (2.5 E1) ← LCS first
  Track B:    30% (1.5 E1)            Track B:    10% (0.5 E1) ← Hypothesis Ledger only
  Shared:     10% (0.5 E1)            Shared:     40% (2 E1)   ← Tier 0/1 + GUI summary tab
                                                                + V101 reconcile
                                                                + Execution hardening
```

理由：v4.1 真實重心是 **「找可複驗 edge」**，而不是「同時建兩條軌道」。Track A 拿一半 capacity 全力衝 LCS event-study，Shared 拿 40% 把基礎建設打底（這些 LCS 用得到、Track B 後續也用得到），Track B 自己只佔 10% 養活 Hypothesis Ledger 表結構不死。

---

## §4 修訂 Sprint Plan（v4.1）

| Sprint | Week | Track A | Track B | Shared | Milestone |
|---|---|---|---|---|---|
| **N+0** | 已過 | — | — | — | 65% |
| **N+1** | W3-W4 | LCS event-study + replay + pre-registration / NLE listing watcher (shadow) | learning.hypotheses + preregistration schema | **Phase 0 migration drift reconcile** + V101 + Tier 0/1 classical + GUI summary tab + Execution hardening | 67% |
| **N+2** | W5-W6 | LCS demo deploy + 14d soak 開始 / NLE 收 5+ events shadow | Hypothesis Ledger CRUD API | V102 + Tier 0/1 Ollama narrative + GUI exploit tab | 70% |
| **N+3** | W7-W8 | LCS 14d evidence packet + NLE first event-study report / **W8 fork review** | manual hypothesis 寫入 ledger 試跑 | Stage 0R replay tooling enhance + cross-track conflict resolver | 75% / **W8 verdict** |
| **N+4** | W9-W10 | branch: LCS Stage 1 prep / NLE expand / PIVOT signal service / KILL | branch: Tier 2 spec start（若 SCALE）| GUI asds tab if SCALE | 80% |
| **N+5** | W11-W12 | branch-dependent | branch-dependent | per branch | 85% |
| **N+6** | W13-W14 | 6-month review + W24 prep | review | review | 88% |

**hard precondition** （unchanged from v4）: v56 P0-ENGINE-HALTSESSION-STUCK-FIX 完整 cycle 收口。

---

## §5 修訂 Kill Criteria

### §5.1 Track A v4.1 kill ladder

| Phase | Threshold | Action |
|---|---|---|
| W2 | LCS event-study CAR t-stat < 1.5 OR pre-registration miss > 2σ | **KILL LCS，all-in NLE** |
| W2 | LCS event-study t-stat ≥ 1.5 + replay match ≥ 80% | LCS demo deploy approved |
| W6 | LCS demo 14d cum net edge < -5 bps | WARN, size reduce 50% |
| W6 | LCS demo 14d Sharpe < 0.3 | PAUSE, 14d retry |
| W8 | **demo evidence**: LCS Sharpe > 1.0 + DSR > 0.85 | Stage 1 micro-canary 預備（live deploy 仍等 P0-LG/OPS gates） |
| W8 | demo Sharpe < 0.5 + NLE 也沒 event-study evidence | KILL Track A → PIVOT signal service |
| W12 | (PIVOT path) signal subs < 5 | KILL Track A entirely |
| W24 | Track A revenue (live or signal) < $500 | HARD KILL → IP sale |

### §5.2 Track B v4.1 kill ladder（極簡）

| Phase | Threshold | Action |
|---|---|---|
| W4 | learning.hypotheses schema 未 land | block Track B 進度 |
| W8 | 0 hypothesis written to ledger（含 manual） | DEFER all Track B Tier 2+ work to Year 2 |
| W24 | < 10 hypothesis registered total | downgrade Track B to dormant |
| W24 | ≥ 10 hypothesis + ≥1 達 demo Sharpe > 1.0 | GRADUATE → consider Tier 2 LLM generator build |

Track B 不再有「PROMOTED count < 3 → ABORT」這種強制；reviewer 對：Track B 在 live blockers 未清前 不該有強執行壓力。

---

## §6 governance artifacts 更新

v4.1 land 後，4 個既存 artifacts 需 supersede / amend：

| Artifact | v4 版本 | v4.1 處理 |
|---|---|---|
| AMD-2026-05-20-01 | Accepted | 補 AMD-2026-05-20-02 修訂條款（取代 §9 sprint banner + §3 schema scope + §5 kill ladder） |
| ADR-0025 | Accepted-pending-commit | **rewrite**（schema 名稱對齊真實 DB） |
| ADR-0026 | Accepted-pending-commit | **rewrite**（event-study + pre-registration + replay 三件套）|
| V101/V102 spec | SPEC READY | **rewrite**（基於真實表名 + Phase 0 migration drift reconcile） |

---

## §7 References

- v1: `srv/2026-05-20--strategy-architecture-redesign-recommendation.md`（歷史）
- v2: `srv/2026-05-20--autonomous-strategy-system-v2.md`（歷史）
- v3: `srv/2026-05-20--lean-direct-alpha-capture-v3.md`（歷史）
- v4: `srv/2026-05-20--dual-track-architecture-v4.md`（superseded by 本文）
- AMD-2026-05-20-01: `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-01-dual-track-architecture.md`
- AMD-2026-05-20-02: `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-02-v4.1-reviewer-corrections.md`（新）
- ADR-0025-v2: `docs/adr/0025-track-based-strategy-attribution.md`（rewrite）
- ADR-0026-v2: `docs/adr/0026-direct-exploit-bypass-cpcv.md`（rewrite）
- V101/V102 spec v2: `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md`（rewrite）
- Event-study methodology: Brown & Warner (1985), "Using daily stock returns: The case of event studies", JFE 14(1)
- Pre-registration: Nosek et al. (2018), "The preregistration revolution", PNAS 115(11)

---

**END v4.1**

**Open to next parallel audit round**
