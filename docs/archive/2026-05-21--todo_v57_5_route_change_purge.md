# TODO v57.5-zh → v58-zh 路線變更清理歸檔

**歸檔日期**：2026-05-21（UTC）
**動因**：Operator 2026-05-21 要求清理 TODO「亂變更」段；隔壁路線敲定後重新填回。本檔收納所有被 purge 的路線變更歷史（v4 / v4.1 / v4.2 / v4.3 / v4.4 / v5.0 / v5.2~v5.6）。

---

## §A v57.2 雙軌制 v4.2 RATIFY 全文

**Operator 2026-05-20 三次 ratify**：
- 上午：v4 dual-track ratify（AMD-01）
- 下午：1st reviewer parallel audit 提 5 critique；接受 5 全 + push-back 2；v4.1 ratify（AMD-02）
- 傍晚：2nd reviewer parallel audit 提 10 critique；接受 9.5/10（reviewer ssh + grep + row count 工作扎實）；v4.2 ratify（AMD-03）

### §A.1 三輪修正核心點

| 維度 | v4 (上午) | v4.1 (下午) | v4.2 (傍晚) |
|---|---|---|---|
| V101 scope | 假表名 | 9 真表 | 12 真表（+ signals/decision_outcomes/risk_verdicts）|
| V102 column | 假欄位 | 假欄位（spec 內已警告） | 真欄位（ts/fee/realized_pnl；net_edge_bps view computed）|
| Migration drift | 未明確 | 概述 reconcile | 明確 Linux V096 → repo V098 catch-up + V096 不可逆 |
| ADR-0026 prereg | manual review | 7 fields | 15 fields（+code_hash/config_hash/trigger_rule/variance_estimator/immutable_trigger 等）|
| LCS thesis | 30-180s fade | 同 v4 | isolated cluster + book recovery + PostOnly maker（避速度戰）|
| Replay match | 三件套 gate | 三件套 gate | DEFER 到 Phase 1.5（function 未實作）|
| W8 milestone | first live deploy | demo evidence + live-ready proof | 14d demo verdict only |
| Capacity | 60/30/10 | 50/10/40 | 60/0/40（Track B schema-only N+1-N+3）|
| GUI | 4 tabs skeleton N+1 | 1 tab summary N+1 | SQL views + REST endpoint N+1；summary tab N+2 |
| ADR-0024 | 完整版延後 | 完整版延後 | ADR-0024-lite 立即 land（Cowork sub = operator-assistant 非 autonomous L2）|
| W12 PIVOT spec | 提及 §3 | 提及 §3 | DEFER to W8 fork trigger（Claude push-back，不 speculative）|

### §A.2 governance artifacts 全清單（active 彼時）

| Type | 文件 | Status |
|---|---|---|
| AMD-01 | `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-01-dual-track-architecture.md` | Accepted（被 AMD-02/03 部分 supersede）|
| AMD-02 | `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-02-v4.1-reviewer-corrections.md` | Accepted（被 AMD-03 部分 supersede）|
| AMD-03 | `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-03-v4.2-second-reviewer-corrections.md` | 彼時 Accepted active planning authority |
| AMD-04 | `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-04-v4.3-commercial-evidence-sprint.md` | Accepted（v4.3 reframe，部分被 AMD-05 retract）|
| AMD-05 | `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-05-retract-stream-3-ip-sale.md` | Accepted（IP sale 不現實 retract）|
| ADR-0024-lite | `docs/adr/0024-cowork-subscription-operator-assistant.md` | Accepted-pending-commit |
| ADR-0025 v3 | `docs/adr/0025-track-based-strategy-attribution.md` | Accepted-pending-commit（rewrite）|
| ADR-0026 v3 | `docs/adr/0026-direct-exploit-bypass-cpcv.md` | Accepted-pending-commit（rewrite）|
| ADR-0027 | `docs/adr/0027-ai-plan-mode-time-based-budgeting.md` | Accepted（time-based plan mode）|
| V101/V102 spec v3 | `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md` | SPEC READY v3 |

### §A.3 Sequencing v4.2

```
✅ v56 P0-ENGINE-HALTSESSION-STUCK-FIX 完整 cycle CLOSED 2026-05-20 ~02:15 UTC
   ↓
PHASE-0-MIGRATION-DRIFT-RECONCILE（V097 + V098 catch-up serial, low-write window UTC 04-06）
   ↓
PA refresh dispatch plan（V### final + 4 placeholder time column grep final 鎖定）
   ↓
V101 apply（12 既存表 + 2 新表，real column names）
   ↓
7d soak（writer 上線後填 track）
   ↓
V102 apply（NOT NULL + indexes CONCURRENTLY + views computed net_edge_bps）
   ↓
REST endpoint /api/v1/tracks/summary go-live + console banner
   ↓
Track A LCS isolated cluster IMPL（per ADR-0026 v3 thesis）
+ NLE listing watcher shadow
+ Tier 0 microstructure + Tier 1 RegimeClassifier classical
+ Track B schema-only（0 額外 engineering）
```

**Hard precondition**：v56 P0 cycle 中不啟動 dispatch（已滿足）。

---

## §B Sprint Milestone Banner v57.1 Dual-Track v4.1（業務鏈 65% → 88%）

**取代於 AMD-2026-05-20-02**：v4.1 修正後 sprint plan。Track A 順序改 LCS-first；NLE 改 shadow-collect；capacity 改 50/10/40；W8 milestone 改 demo evidence (not live)。

| Sprint | Week | Track A 任務 | Track B 任務 | Shared 任務 | Milestone |
|---|---|---|---|---|---|
| N+0 | W1-W2 | FOUNDATION HEAVY（已完成；歸檔 v21/v36 cleanup）| — | — | 65% |
| N+1 | W3-W4 | LCS event-study + replay + pre-registration / NLE listing watcher (shadow only) | learning.hypotheses + preregistration schema | Phase 0 migration drift reconcile + V101 + Tier 0 microstructure + Tier 1 RegimeClassifier (classical) + GUI summary tab + Execution hardening | 67% |
| N+2 | W5-W6 | LCS demo deploy + 14d soak / NLE 收 5+ events shadow | Hypothesis Ledger CRUD API minimal | V102 + Tier 0/1 Ollama narrative + GUI exploit tab | 70% |
| N+3 | W7-W8 | LCS 14d evidence packet + NLE first event-study report / W8 fork review | manual hypothesis 寫入 ledger 試跑 | Stage 0R replay tooling enhance + cross-track conflict resolver | 75% / W8 verdict |
| N+4 | W9-W10 | branch: LCS Stage 1 prep / NLE expand / PIVOT signal service / KILL | branch: Tier 2 spec start（若 SCALE）| GUI asds tab if SCALE | 80% |
| N+5 | W11-W12 | branch-dependent | branch-dependent | per branch | 85% |
| N+6 | W13-W14 | 6-month review + W24 prep | review | review | 88% |

**Capacity split v4.1**: 50% Track A / 10% Track B（Hypothesis Ledger only）/ 40% Shared

### §B.1 Track A W8 kill ladder v4.1
- W2: LCS event-study t-stat < 1.5 OR pre-reg miss > 2σ → KILL LCS，all-in NLE shadow
- W2: t-stat ≥ 1.5 + replay match ≥ 80% → LCS demo deploy approved
- W6: demo 14d cum net edge < -5 bps → WARN, size reduce 50%
- W8: demo Sharpe > 1.0 + DSR > 0.85 → Stage 1 micro-canary 預備（live deploy 等 P0-LG/OPS clear）
- W8: demo Sharpe < 0.5 + NLE event-study 失敗 → KILL Track A → PIVOT signal service
- W12 (PIVOT path): signal subs < 5 → KILL Track A entirely
- W24: Track A revenue (live or signal) < $500 → HARD KILL → IP sale

### §B.2 Track B kill ladder v4.1
- W4: learning.hypotheses schema 未 land → block Track B 進度
- W8: 0 hypothesis written → DEFER all Track B Tier 2+ to Year 2
- W24: < 10 hypothesis registered → downgrade Track B to dormant
- W24: ≥ 10 hypothesis + ≥1 demo Sharpe > 1.0 → GRADUATE → consider Tier 2 LLM generator build

---

## §C v4 Wave Roster T1-T9 (路線變更專屬 Wave entries)

| 序 | Wave | Track | Owner | 狀態 | 出口條件 |
|---:|---|---|---|---|---|
| T1 | TRACK-SCHEMA V101/V102 + Rust enum + Decision Lease attribution | shared | PA→E1→E2→MIT | PENDING（v56 P0 後 dispatch）| V101 apply + 7d soak + V102 apply + 5 acceptance pass per spec §5 |
| T2 | TRACK-A-NLE New Listing Exploit（3 子策略 + listing watcher + risk carve-out）| A | PA→E1→E2→QA | PENDING（依賴 T1 + v56 P0）| W2 demo deploy + W6 14d demo Sharpe > 1.0 + W8 first live |
| T3 | TRACK-A-LCS Liquidation Cascade Scalper | A | PA→E1→E2→QA | PENDING | W4 demo deploy + Sharpe > 1.0 14d |
| T4 | TRACK-B-TIER0 CrossAssetPanel + Microstructure features + Universe tier classifier | B | PA→E1→E2 | PENDING（依賴 T1）| Per-tick MarketStateSnapshot 落 metrics + universe split 落 PG |
| T5 | TRACK-B-TIER1 RegimeClassifier L0 (classical) + L1 (Ollama narrative) | B | PA→E1→E2 | PENDING（N+2）| 5-class RegimeTag 落 tick_pipeline_metrics |
| T6 | TRACK-B-TIER2-3 Hypothesis Generator (L1 + Cowork sub) + Auto-Validator (CPCV + DSR) | B | PA→AI-E→E1→QC→E2 | PENDING（N+3）| 第一個 L1 mutation + L2 novel hypothesis 通過 validator |
| T7 | TRACK-GUI 4 tab skeleton（summary / exploit / asds / baseline）| shared | E1a→A3 | PENDING（N+1 shared 10%）| 4 tabs 顯示 per-track P&L 獨立、無 cross-track 滲透 |
| T8 | TRACK-RISK-GUARDIAN6 Guardian check 6（per-track envelope enforcement）| shared | PA→E1→E2→BB | PENDING（依賴 T1）| risk_config_*.toml 加 [track_budgets]；Guardian veto 超 envelope trade |
| T9 | TRACK-CONFLICT-RESOLVER Cross-track conflict detection at Decision Lease | shared | PA→E1→E2 | PENDING（N+2-N+3）| A 優先；B intent 標 BLOCKED_CROSSTRACK 落 audit log |

---

## §D §3 active state 中路線變更 entry

**2026-05-20 v57 ratify**：operator 補資金 demo $10k + live $1k；批准 v4 dual-track 取代 v2 ASDS 純路徑 + v3 lean 純路徑；4 governance artifacts（AMD-2026-05-20-01 + ADR-0025/26 + V101/V102 spec）land；業務根因更新為「5 textbook 策略仍欠正 edge → Track A direct exploit (NLE/LCS) 8 週現金流 + Track B ASDS factory 12 個月規模化長線並行」。舊「Alpha Surface Phase C/D + 替代 alpha 候選」敘事被 dual-track 重組吸收。

---

## §E §11.4 P0-MICRO-PROFIT — W-AUDIT-8a..8f wave 矩陣（路線變更映射）

當時治本路徑 = PA R-1/R-2/R-3 redesign（已映射 W-AUDIT-8a..8f wave 矩陣）：

| ID | 任務 | Spec 來源 | ETA |
|---|---|---|---|
| W-AUDIT-8a Phase B/C/D | Tier 2 panel collector + Tier 3 microstructure + Tier 4 information flow | Sprint N+1 W2 起 | 4-6 sprint |
| W-AUDIT-8b（A4-A）| Funding Skew Directional（R-1 IMPL）| TOMBSTONED 2026-05-18 | — |
| W-AUDIT-8c（A4-B）| Liquidation Cluster Reaction | source/test + V095 apply + writer revival DONE | 策略 launch 仍另立 Stage 0R/design gate |
| W-AUDIT-8d（A4-C tombstone）| BTC→Alt Lead-Lag diagnostic panel | Archived guard only | 不再 active；diagnostic-only |
| W-AUDIT-8e（R-2）| Strategist Alpha Source Orchestrator | W-AUDIT-8b/8c/8d 後 | N+3-N+4 |
| W-AUDIT-8f（R-3）| Hypothesis Pipeline first-class | 序列化於 R-2 後 | N+4 |

**Total ETA = 12-17 sprint（3-4 月）— 真實 gross 轉正最早窗口。**

---

## §F §14 v4.2 dispatch 排程

| 日期 | 工作 | Gate |
|---|---|---|
| 2026-05-21..27 | v4.2 dispatch W3-W4：PHASE-0 reconcile + V101 apply + Track A LCS event-study + NLE shadow watcher + Tier 0/1 shared + GUI summary tab | 序列化於 §-0.C |
| 2026-05-28..06-03 | v4.2 W5-W6：LCS demo deploy + 14d soak start / NLE 收 5+ events shadow / Hypothesis Ledger CRUD / V102 apply / GUI exploit tab | Sprint N+2 |
| 2026-06-04..10 | v4.2 W7-W8 fork review：LCS 14d evidence packet + NLE first event-study report；W8 verdict（demo Sharpe / DSR gates）| Sprint N+3；W8 milestone = demo evidence + live-ready proof |
| 2026-06-11..17 | v4.2 W9-W10：branch by W8 verdict — LCS Stage 1 prep / PIVOT signal service / KILL | Sprint N+4 |
| 2026-06-18..07-01 | v4.2 W11-W14：6-month review + W24 prep | Sprint N+5..N+6 |

---

## §G untracked V5.x 規劃文件（operator 範圍）

`srv/2026-05-20--*.md` 路線變更系列截至 2026-05-21 ~14:00 UTC 已 untracked 在 Mac working tree 的：
- `2026-05-20--execution-plan-v5.2.md`
- `2026-05-20--execution-plan-v5.3.md`
- `2026-05-20--execution-plan-v5.4.md`
- `2026-05-20--execution-plan-v5.5.md`
- `2026-05-20--execution-plan-v5.6.md`

Operator 隔壁敲定後重新填回 TODO active 區。本檔不複製內容（檔案本身仍在 working tree，下次 active 路線拍板時參考）。

---

**Maintenance contract**：依 `docs/agents/todo-maintenance.md`。本歸檔不再回收進 active。Operator 路線敲定後可在新 §-0 / §1 / §14 直接重填新內容。
