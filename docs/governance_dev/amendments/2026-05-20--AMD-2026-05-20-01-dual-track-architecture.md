# Amendment AMD-2026-05-20-01 — Dual-Track Architecture (Direct Exploit + ASDS Factory)

**對應 spec**: `srv/2026-05-20--dual-track-architecture-v4.md`（規劃權威來源）
**修訂對象**: TODO.md §1 Sprint Milestone Banner（N+1 ~ N+5 主題替換）+ TODO.md §4.1 Wave Roster（alpha-bearing wave 重組）+ W-AUDIT-8 系列 wave 角色重定位
**Supersedes**:
- `srv/2026-05-20--strategy-architecture-redesign-recommendation.md` v1（discipline executor 方向被 operator REJECT）
- `srv/2026-05-20--autonomous-strategy-system-v2.md` v2（pure ASDS 12-month timeline 與 burn rate 約束衝突）
- `srv/2026-05-20--lean-direct-alpha-capture-v3.md` v3（pure lean，砍掉 v2 浪費 ASDS 願景）
- TODO.md §1 N+1 ~ N+5 既有 sprint 主題（ALPHA SURFACE PANEL WIRING / 8a Phase D / 等）

**日期**: 2026-05-20
**作者**: Claude（外部 review）→ Operator approval 2026-05-20
**狀態**: Accepted — planning authority + sprint banner authority；ADR-0025 / ADR-0026 / V101+V102 migration spec 同日批准
**索引**: `docs/governance_dev/SPECIFICATION_REGISTER.md` Amendments section（待新增）
**TODO 連結**: 新建 active queue 條目（見 §8）

---

## 1. Executive Decision

玄衡 engine 採行 **雙軌制（Dual-Track）策略開發架構**。即日起所有 alpha-bearing 工程 capacity 切分為兩條獨立的開發軌道，各自有獨立的 attribution、risk budget、kill criteria、GUI 顯示，但共用既有 governance moat（Guardian、Decision Lease、H0 Gate、Replay、Stage 0/0R/1/2/3/4 canary、5-gate live boundary）。

Track 定義：

| Track | 代號 | 內容 | 開發週期 | 目標 |
|---|---|---|---|---|
| A | `direct_exploit` | NLE / LCS / DCF（未來）；手寫 Rust struct | 4 sprint（8 週） | 短期現金流 |
| B | `asds_factory` | ASDS 7-tier pipeline；LLM 產 DSL spec | 12 sprint（6 個月+） | 長期規模化 alpha factory |
| C | `baseline` | 現有 5 textbook（ma/bb_brk/bb_rev/grid/funding_arb） | frozen | A/B 對照組 |

**Operator 2026-05-20 同時批准的 6 項決議**：
1. v4 雙軌制取代 v2 + v3 並排放法
2. ADR-0025 Track-based attribution
3. ADR-0026 Direct Exploit bypass CPCV
4. V101/V102 Track schema migration
5. W8 fork criteria + W24 hard kill（per v4 §7.1 / §7.2）
6. Risk budget 切分（per v4 §3.1 / §3.2）

**Operator 同日延遲決議**：
- Sprint N+1 詳細 plan §8.1（待本 AMD ratify 後 PA refresh dispatch plan）
- ADR-0024 L2 autonomous in envelope（可延至 N+2 sprint kickoff 再決）

---

## 2. Removed / Frozen Paths

### 2.1 Removed: v2 ASDS as sole alpha strategy

v2 pure ASDS timeline（12-month）與 operator burn rate（$480/月）衝突。v4 把 ASDS 降為 Track B（30%~60% capacity，跟隨 W8 fork branch），不再是 100% capacity 路徑。

### 2.2 Removed: v3 lean 砍掉所有 ASDS

v3 完全放棄 hypothesis factory 是不必要的；v4 證明 ASDS 與 Direct Exploit 可在同一 engine 並行而不互相污染。

### 2.3 Frozen: Track C 五策略所有新工程

`ma_crossover` / `bb_breakout` / `bb_reversion` 維持 demo-only 跑，不投入新工程。`grid_trading` v1 維持 retire 狀態。`funding_arb` 維持 permanent dormant per ADR-0018。

### 2.4 Frozen: W-AUDIT-8a Tier 2 (FundingSkew / Basis) + Tier 4 (Sentiment)

per v1/v2/v3 共識，這幾條 alpha source 已被機構工業化套利，retail 無 edge。重新編入 Year 2 backlog，本 sprint 序列不再分配 capacity。

### 2.5 Retained: W-AUDIT-8a Tier 3 LiquidationCascade

直接 mapping 到 Track A LCS 策略，採用既有 `allLiquidation` writer revival。設計重定位為 Direct Exploit 而非 ASDS source（即不走 Tier 3 CPCV validator，per ADR-0026）。

### 2.6 Retained: W-AUDIT-8a Tier 3 OrderflowImbalance

延至 Track B Tier 0 Microstructure features 階段（N+1 W3-W4），作為 RegimeClassifier 輸入，非獨立策略。

### 2.7 Retained: W-AUDIT-8f Hypothesis Pipeline

直接 mapping 到 Track B Tier 2-7。從原 TODO §4.1 DEFER N+5 IMPL 拉前到 Sprint N+3（Tier 2-3 first cycle）+ N+5（Tier 4-7 full pipeline）。

### 2.8 Retained: ADR-0024 草稿

Track B Tier 2 Hypothesis Generator 需要 L2 autonomous 才能完整運作；ADR-0024 草稿仍 valid 但 operator 延至 N+2 sprint 再決。N+1 + N+2 Track B 仍可用 L1 Ollama + Cowork scheduled task（既有 Claude Max 訂閱）替代 L2 API，不阻擋 N+1 啟動。

---

## 3. Schema and Attribution（per ADR-0025）

### 3.1 Track enum 部署

per ADR-0025 + 對應 migration spec V101/V102（`docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md`）。

涉及 9 個表加 `track` 欄位：strategy_metadata / decision_leases / fills / learning.strategy_trial_ledger / learning.hypotheses (new) / cost_edge_advisor_log / agent.ai_invocations / execution_reports / positions。

Migration 分兩步（Guard B + idempotent，per ADR-0011）：
- V101：CREATE TYPE + ADD COLUMN nullable + backfill `baseline`
- V102：NOT NULL + DEFAULT 'baseline' + index

### 3.2 Decision Lease attribution

每個 Decision Lease 在 emit 時自動帶 `track` tag（從 strategy registry lookup）。state machine 邏輯不變；attribution 增量。

### 3.3 P&L view 分軌

新建 `track_direct_exploit_daily` / `track_asds_factory_daily` / `track_baseline_daily` / `track_summary_daily` views。GUI 查詢分軌；無 cross-track aggregate query 除非 operator UI 明確控制。

---

## 4. Risk Budget Envelope（per v4 §3.1 / §3.2）

### 4.1 Demo $10,000 切分

| Track | Budget | Note |
|---|---:|---|
| Direct Exploit | $4,000 (40%) | NLE $2k + LCS $1.5k + reserve $500 |
| ASDS Factory | $5,000 (50%) | Tier 4 paper $3k + Tier 5 demo canary $2k |
| Baseline | $1,000 (10%) | ma $400 + bb_brk $300 + bb_rev $300 |

### 4.2 Live $1,000 切分

| Track | Budget | Note |
|---|---:|---|
| Direct Exploit | $700 (70%) | NLE $400 + LCS $300 |
| ASDS Factory | $100 (10%) | 1 PROMOTED hypothesis at a time |
| Baseline | $0 | Frozen, never live |
| Reserve | $200 (20%) | Operator discretionary |

### 4.3 Guardian check 6（新）

per ADR-0025 implementation，Guardian 拒絕任何讓 track 累計 notional 超過 envelope 的 trade。Envelope 來自 `risk_config_*.toml` 新 section `[track_budgets.{demo|live}]`。

跨軌 budget 借用 **禁止**；envelope 硬執行。

---

## 5. Kill Criteria Ladder（per v4 §7.1 / §7.2）

### 5.1 Track A Direct Exploit kill ladder

| Phase | Threshold | Action |
|---|---|---|
| W4 | NLE+LCS demo cum < 0 bps | WARN, size reduce 50% |
| W4 | NLE+LCS demo cum ≥ 0 bps | Continue full size |
| W8 | Live cum P&L < -$100 | **KILL Track A → PIVOT signal service** |
| W8 | Live cum P&L -$100 ~ $0 | PAUSE, size $200, 4-week retry |
| W8 | Live cum P&L > $0 | **SCALE → add DCF + 增 budget** |
| W12 | (PIVOT path) signal subs < 5 | KILL Track A entirely |
| W24 | Track A total revenue < $500 | **HARD KILL → IP sale / shutdown** |

### 5.2 Track B ASDS Factory kill ladder

| Phase | Threshold | Action |
|---|---|---|
| N+3 (W8) | 0 hypothesis 通過 Auto-Validator | WARN, prompt engineering iteration |
| N+5 (W12) | 0 hypothesis 達 EVIDENCE_GATE | WARN, extend Tier 4 paper 14d |
| W12 | 0 PROMOTED in 4 weeks demo | REDUCE Track B capacity 30% → 10% |
| W24 | PROMOTED count < 3 | **ABORT Track B → archive, push Year 3** |
| W24 | PROMOTED ≥ 3 + ≥1 Sharpe > 1.0 demo 30d | **GRADUATE → operator live promotion review** |

### 5.3 Kill 隔離保證

Track A 任何 kill threshold 觸發 **不影響** Track B 進度；Track B abort **不影響** Track A 持續運行。per ADR-0025 implementation 新建 `track_kill_events` 表記錄獨立事件。

---

## 6. Engineering Capacity Split（per v4 §4）

### 6.1 Sprint N+1 ~ N+2（v3 critical 8-week 窗口）

```
E1 capacity 5 active + 1 stand-by:
  Track A:  60% (3 E1)
  Track B:  30% (1.5 E1)
  Shared:   10% (0.5 E1)
```

### 6.2 Sprint N+3（W8 fork moment 後）

依 Track A W8 verdict 分支：

| Verdict | Track A | Track B | Shared |
|---|---:|---:|---:|
| SCALE | 40% | 50% | 10% |
| PIVOT | 30%（signal service infra） | 60% | 10% |
| KILL | 0% | 80% | 20%（IP sale prep） |

### 6.3 Sprint N+4 ~ N+6

Track B 接力為主，Tier 2-7 build out。N+6 hard kill 觸發或 graduate 觸發。

---

## 7. Cross-Track Interaction Rules（per v4 §6）

### 7.1 允許

- Track B LLM 可分析 Track A 表現 → 提議 mutation hypothesis（不影響 Track A Rust struct）
- Track A 數據 feed Track B regime classifier 訓練（單向 A → B）
- 共享 cost_edge_advisor（log row 分軌）
- 共享 Guardian / Decision Lease / Stage canary

### 7.2 禁止

- LLM 寫 Rust（A 或 B 都不行；LLM 只寫 DSL spec）
- Risk budget 跨軌借用
- 一軌 kill 觸發另一軌 retire
- 衝突 intent 時 Track B 凌駕 Track A（規則：Direct Exploit 優先；Track B 被標 BLOCKED_CROSSTRACK）

### 7.3 衝突仲裁

Decision Lease state machine 新增 cross-track conflict detection（~120 LOC Rust）。Track A 優先；Track B 落 audit log，operator 可審視。

---

## 8. Active TODO Queue Entries（新增）

新建 active 條目於 TODO §10 / §11 / §4：

```
AMD-2026-05-20-01-RATIFY      🔵 IN_PROGRESS  [PM]
  - 本 AMD land + 4 governance artifacts ship
  - 完成標準：5 個 file committed + TODO §1 banner updated

ADR-0025-LAND                  🔵 IN_PROGRESS  [PM]
  - `docs/adr/0025-track-based-strategy-attribution.md` committed

ADR-0026-LAND                  🔵 IN_PROGRESS  [PM]
  - `docs/adr/0026-direct-exploit-bypass-cpcv.md` committed

V101-V102-TRACK-MIGRATION      ⏳ PENDING       [PA→E1]
  - Spec: `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md`
  - Acceptance: Linux PG dry-run PASS + apply idempotent ×2
  - Sequence: 必須在 v56 P0-ENGINE-HALTSESSION-STUCK-FIX 完整 cycle 之後

TRACK-A-NLE-IMPL               ⏳ PENDING       [PA→E1]
  - NLE 3 子策略 + listing watcher + risk carve-out
  - 依賴：V101/V102 完成 + Track Rust enum land

TRACK-A-LCS-IMPL               ⏳ PENDING       [PA→E1]
  - Liquidation cluster detector + LCS strategy
  - 依賴：V101/V102 + Track A NLE 首步驟 land

TRACK-B-TIER0-IMPL             ⏳ PENDING       [PA→E1]
  - CrossAssetPanel collector + Microstructure features + Universe tier classifier
  - 平行於 Track A N+1 工作

TRACK-B-TIER1-IMPL             ⏳ PENDING       [PA→E1]
  - RegimeClassifier L0 (classical) + L1 (Ollama narrative)
  - N+2

TRACK-GUI-TABS                 ⏳ PENDING       [E1a→A3]
  - 4 個 GUI tab skeleton（summary / exploit / asds / baseline）
  - N+1 shared 10% 配額

PA-REFRESH-DISPATCH-N+1        ⏳ PENDING       [PA]
  - 依 v4 §8.1 重新出 N+1 dispatch plan（取代既有 TODO §1 banner）
  - 必須含：V### 號 final 決議 + 與 v56 P0 序列化 + multi-E1 race-aware 排程
```

---

## 9. TODO.md §1 Sprint Banner 替換內容

替換 TODO.md §1 表格內容為：

```
| Sprint | Week | 主題 | E1 cap | Milestone |
|---|---|---|---|---|
| N+0 | W1-W2 | FOUNDATION HEAVY（已過）| 5+1 | 65% |
| N+1 | W3-W4 | ⚡ Track A NLE + Track B Tier 0 + V101/V102 + GUI skeleton + Execution hardening | 5+1（60/30/10） | 67% |
| N+2 | W5-W6 | ⚡ Track A LCS + Track B Tier 1 + AutoRetire + Demo 14d soak | 5+1（60/30/10） | 70% |
| N+3 | W7-W8 | 🚀 Track A first live deploy + W8 fork review + Track B Tier 2/3 first cycle | 5+1（60/30/10）→ branch | 75% / **W8 verdict** |
| N+4 | W9-W10 | (Branch SCALE: DCF + Track B Tier 4) / (PIVOT: signal service) / (KILL: IP sale prep) | per branch | 80% |
| N+5 | W11-W12 | Track A maintenance + Track B Tier 5/6/7 + 首個 ASDS hypothesis demo end-to-end | per branch | 85% |
| N+6 | W13-W14 | 雙軌 6-month aggregate review + W24 prep | 5+1 | 88% |
```

---

## 10. Push Back / Risk 治理紀錄

### 10.1 Operator Push Back（accepted）

- v2 "12-month PoC, etc 1 年" 與 $480/月 burn rate 不可調和 → 修訂為 v3 短期 + v2 長期並行
- Bot must auto-trade / auto-analyze / auto-draft strategy → reject "discipline executor" reframe → Track B ASDS Factory 仍是長期路徑
- 需要雙架構並行 → v4 dual-track 出爐

### 10.2 Claude Push Back（recorded for operator visibility）

- $1k live 規模下，**任何**策略路徑 12 個月內期望 P&L < monthly burn rate（$480 × 12 = $5760 vs ~$50-300/year live P&L）；ASDS 的真實 ROI 取決於 demo evidence 後 operator 是否擴 live size 到 $5k+ → $25k+
- v3 PIVOT 路徑（signal service）月入 $2-15k 是繞開 size 物理上限的唯一 viable 商業化方向；W8 fork 必須真實考慮，不只是 KILL 退場
- Track B Tier 2 真實 autonomous 需要 ADR-0024（L2 within envelope）；N+1 ~ N+2 用 Cowork scheduled task 替代是 OK 但 Tier 2 full pipeline 需 ADR-0024 ratify

### 10.3 governance 不變式（仍強制）

- 16 條根原則（CLAUDE.md §二）全保留
- 5-gate live boundary 共用
- Guardian veto authority 共用，不分 track
- Decision Lease state machine 邏輯不變，僅增 track 欄位
- Stage 0 / 0R / 1 / 2 / 3 / 4 canary 共用
- AMD-2026-05-15-01 Demo micro-canary 共用
- ADR-0011 V### migration Linux PG dry-run mandatory（V101/V102 套用）

---

## 11. References

- v4 spec authority: `srv/2026-05-20--dual-track-architecture-v4.md`
- ADR-0025: `docs/adr/0025-track-based-strategy-attribution.md`
- ADR-0026: `docs/adr/0026-direct-exploit-bypass-cpcv.md`
- V101/V102 migration spec: `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md`
- v1 / v2 / v3 historical drafts: 同日 `srv/2026-05-20--*.md`（保留為 audit trail，不再 active）
- ADR-0011 V### migration dry-run
- ADR-0018 funding_arb retire（Track C 適用）
- ADR-0020 Layer 2 manual-only（Track B Tier 2 需 ADR-0024 carve-out）
- AMD-2026-05-15-01 canary rebase（兩軌共用）
- AMD-2026-05-15-02 EDGE-P2-3 Phase 1b（Track A NLE/LCS execution path 受益）

---

**END AMD-2026-05-20-01**
