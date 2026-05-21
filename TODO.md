# 玄衡 TODO — 活躍派工佇列

版本：v57.3-zh（v57.2 dual-track v4.2 RATIFY 結構保留 + v56 P0-ENGINE-HALTSESSION-STUCK-FIX 完整 cycle CLOSED 2026-05-20 ~02:15 UTC）
日期：2026-05-20
狀態：本檔僅保留 ACTIVE / PENDING / ACTIVE-WATCH 項目；所有歷史 ✅ DONE 詳情已歸檔。**v56 P0 unblocks §-0.C Sequencing 後續 PHASE-0-MIGRATION-DRIFT-RECONCILE**。

## §-0 v57.2 雙軌制 v4.2 RATIFY（2026-05-20 — 3 amendments）

**Operator 2026-05-20 三次 ratify**：
- 上午：v4 dual-track ratify（AMD-01）
- 下午：1st reviewer parallel audit 提 5 critique；接受 5 全 + push-back 2；v4.1 ratify（AMD-02）
- 傍晚：**2nd reviewer parallel audit 提 10 critique；接受 9.5/10（reviewer ssh + grep + row count 工作扎實）；v4.2 ratify（AMD-03）**

### §-0.A 三輪修正核心點

| 維度 | v4 (上午) | v4.1 (下午) | v4.2 (傍晚) |
|---|---|---|---|
| V101 scope | 假表名 | 9 真表 | **12 真表**（+ signals/decision_outcomes/risk_verdicts）|
| V102 column | 假欄位 | 假欄位（spec 內已警告） | **真欄位**（ts/fee/realized_pnl；net_edge_bps view computed）|
| Migration drift | 未明確 | 概述 reconcile | **明確** Linux V096 → repo V098 catch-up + V096 不可逆 |
| ADR-0026 prereg | manual review | 7 fields | **15 fields**（+code_hash/config_hash/trigger_rule/variance_estimator/immutable_trigger 等）|
| LCS thesis | 30-180s fade | 同 v4 | **isolated cluster + book recovery + PostOnly maker**（避速度戰）|
| Replay match | 三件套 gate | 三件套 gate | **DEFER 到 Phase 1.5**（function 未實作）|
| W8 milestone | first live deploy | demo evidence + live-ready proof | **14d demo verdict only** |
| Capacity | 60/30/10 | 50/10/40 | **60/0/40**（Track B schema-only N+1-N+3）|
| GUI | 4 tabs skeleton N+1 | 1 tab summary N+1 | **SQL views + REST endpoint N+1**；summary tab N+2 |
| ADR-0024 | 完整版延後 | 完整版延後 | **ADR-0024-lite 立即 land**（Cowork sub = operator-assistant 非 autonomous L2）|
| W12 PIVOT spec | 提及 §3 | 提及 §3 | **DEFER to W8 fork trigger**（Claude push-back，不 speculative）|

### §-0.B governance artifacts 全清單（active）

| Type | 文件 | Status |
|---|---|---|
| AMD-01 | `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-01-dual-track-architecture.md` | Accepted（被 AMD-02/03 部分 supersede）|
| AMD-02 | `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-02-v4.1-reviewer-corrections.md` | Accepted（被 AMD-03 部分 supersede）|
| **AMD-03** | `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-03-v4.2-second-reviewer-corrections.md` | **Accepted active planning authority** |
| ADR-0024-lite | `docs/adr/0024-cowork-subscription-operator-assistant.md` | **NEW Accepted-pending-commit** |
| ADR-0025 v3 | `docs/adr/0025-track-based-strategy-attribution.md` | Accepted-pending-commit（rewrite） |
| ADR-0026 v3 | `docs/adr/0026-direct-exploit-bypass-cpcv.md` | Accepted-pending-commit（rewrite） |
| V101/V102 spec v3 | `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md` | SPEC READY v3 |
| **規劃權威 v4.2** | `srv/2026-05-20--dual-track-architecture-v4.2.md` | **active** |
| 歷史 v1/v2/v3/v4/v4.1 | `srv/2026-05-20--*.md` | audit trail，非 active |

### §-0.C Sequencing v4.2

```
✅ v56 P0-ENGINE-HALTSESSION-STUCK-FIX 完整 cycle CLOSED 2026-05-20 ~02:15 UTC（Layer A + B 都 LIVE，real-event verified）
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

**Hard precondition unchanged**：v56 P0 cycle 中**不啟動 dispatch**。

## §-0 (LEGACY) v57.1 雙軌制 v4.1 RATIFY → 已被 v4.2 supersede

詳情歸檔於 `docs/archive/2026-05-20--todo_v57_3_closure_cleanup_archive.md` §D。Active planning authority 走 §-0 v4.2 + AMD-2026-05-20-03。

---

## §-1 v56 緊急狀態 — P0 trading-inert incident → ✅ CLOSED 2026-05-20

2026-05-19 ~12:27-20:09 UTC 7h43m TRADING-INERT，operator restart_all.sh 救活。修復鏈 Layer A + Layer B 於 2026-05-20 ~02:15 UTC LIVE 並 real-event verified（drawdown halt 27.51% 觸發 forensic log + governance_audit_log INSERT，operator GUI 平倉 + Resume 全鏈通）。Halt 觸發根因仍 UNRESOLVED → `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`。詳情歸檔於 §E（同上 archive）。

---

## §0 v55 / 之前的完工狀態（一段話留底）

v55（2026-05-19 上半段）operator 授權的 4 條並行軌道全收口：

- **#5 watchdog RCA**（DNS/HTTP transport outage 誤判為 `ENGINE_CRASH`）
- **#6 entry-path RCA**（entry-close 0% maker fill 為 path-specific，非全局 PostOnly 壞）
- **#7 tab-live extract**（tab-live.html 2171→543 LOC，內聯 JS 抽到 tab-live.js 1645 LOC）
- **#9 stress fails RCA + #12 E1 R2 fix**（stress_integration.rs 修 2 helper；35/35 PASS）

關鍵 commit：`9bf4fd62` / `c1f47722` / `d927bf7f`。

**QC P2-ENTRY-PATH critical reframe**：原 QA「entry-close vs risk-exit by ID prefix」拆法是結構性人為造成的；兩者都走同一 `execute_position_close()` 路径。真實是 6 maker attempts / 3 fills = 50% Wilson CI [18.8%, 81.2%] 覆蓋 sim 70.8% → 21pp 偏差非 70pp gap。Sample velocity ~0.44 grid_close/hr → 首個可信 verdict 推到 **T+96h~T+120h（2026-05-22~23 UTC）**。

**v55 衍生 backlog**：見 §11.3 / §12（P1-WATCHDOG-EXIT-CODE-CLARIFY / FA-WATCHDOG-3STRIKE-ESCALATION-POLICY / P2-QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX / P2-SIM-QUEUE-AWARE-ADJUSTMENT / P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS）。

**Governance flag**：`cargo test --lib` 不覆蓋 tests/ integration crate；建議 sign-off SOP 加 `cargo test -p openclaw_engine --release`（no --lib）。

## 翻譯與歸檔說明

- 本次 v56→v56-zh 改寫：全文中文化 + 嚴格清理 ✅ DONE 詳情。
- 已完成項目（含 commit hash、E2/E4 鏈、AMD 修文記錄）轉存到：
  `docs/archive/2026-05-19--todo_v55_translation_archive.md`
- 上次大規模歸檔已在以下文件累積，本次不再重複收納：
  - `docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`
  - `docs/archive/2026-05-15--todo_v24_stale_rows_archive.md`
  - `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`
  - `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`
  - `docs/archive/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`
  - `docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md`
  - `docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md`

維護契約：依 `docs/agents/todo-maintenance.md` 將本檔保持為活躍派工佇列；穩定專案脈絡寫進 `README.md`，agent 操作規則寫進 `CLAUDE.md` / `.codex/MEMORY.md`。

---

## §0.0 PM Freeze — Demo-Only Stage 1 + A4-C Tombstone Guard

**狀態**：ACTIVE PM freeze；AMD-2026-05-15-01 持有 rebase 權威。

- Stage 1 promotion evidence **僅限 Demo**：Stage 0 shadow → Stage 0R replay preflight（`eligible_for_demo_canary=true/false`）→ Stage 1 Demo micro-canary（1 策略 × 1 symbol × 7d）。Stage 0R 不是 Stage 1 PASS。
- Paper 不是 active promotion lane。任何計畫 / 命令 / env / 腳本 / runtime 若設 `OPENCLAW_ENABLE_PAPER=1` 為 promotion 用，**BLOCKED**，除非未來 operator 明示重啟 paper 作非 promotion 診斷用途。
- **A4-C tombstone**：`W-AUDIT-8d` BTC→Alt Lead-Lag 退出 active promotion，封存 no-revive（BTC 1m return + xcorr feature shape）。`panel.btc_lead_lag_panel` / `[57]` 僅保 diagnostic；不得作 Stage 0R 候選或 Stage 1 Demo cohort 來源。
- 未來 A4-C 重啟需：materially new predictive variable + preregistered validation + 全新 strategy×symbol Stage 0R packet 且 `eligible_for_demo_canary=true`。
- 當前 active alpha gates：W-AUDIT-8b Stage 0R 已 tombstoned；W-AUDIT-8a C1 transport proof `PASS_C1_PROOF_CANDIDATE`；W-AUDIT-8c source/test + V095 apply + production `allLiquidation.{symbol}` writer revival 已 DONE。writer revival 不蘊含 liquidation 策略可上線。

---

## §1 Sprint Milestone Banner — v57.1 Dual-Track v4.1（業務鏈 65% → 88%）

**取代於 AMD-2026-05-20-02**：v4.1 修正後 sprint plan。Track A 順序改 LCS-first；NLE 改 shadow-collect；capacity 改 50/10/40；W8 milestone 改 demo evidence (not live)。

| Sprint | Week | Track A 任務 | Track B 任務 | Shared 任務 | Milestone |
|---|---|---|---|---|---|
| **N+0** | W1-W2 | FOUNDATION HEAVY（已完成；歸檔 v21/v36 cleanup） | — | — | 65% |
| **N+1** | W3-W4 | LCS event-study + replay + pre-registration / NLE listing watcher (shadow only) | learning.hypotheses + preregistration schema | **Phase 0 migration drift reconcile** + V101 + Tier 0 microstructure + Tier 1 RegimeClassifier (classical) + GUI summary tab + Execution hardening | 67% |
| **N+2** | W5-W6 | LCS demo deploy + 14d soak / NLE 收 5+ events shadow | Hypothesis Ledger CRUD API minimal | V102 + Tier 0/1 Ollama narrative + GUI exploit tab | 70% |
| **N+3** | W7-W8 | LCS 14d evidence packet + NLE first event-study report / **W8 fork review** | manual hypothesis 寫入 ledger 試跑 | Stage 0R replay tooling enhance + cross-track conflict resolver | 75% / **W8 verdict** |
| **N+4** | W9-W10 | branch: LCS Stage 1 prep / NLE expand / PIVOT signal service / KILL | branch: Tier 2 spec start（若 SCALE） | GUI asds tab if SCALE | 80% |
| **N+5** | W11-W12 | branch-dependent | branch-dependent | per branch | 85% |
| **N+6** | W13-W14 | 6-month review + W24 prep | review | review | 88% |

**Capacity split v4.1**: 50% Track A / 10% Track B（Hypothesis Ledger only）/ 40% Shared（Tier 0/1 共享基建 + V101 + GUI + execution hardening + Phase 0 reconcile）

**Stand-by E1 啟用條件**（operator 拍板 2026-05-09 (a)，仍 valid）：Phase 0 reconcile 翻車 / Track A LCS event-study 卡 / 任一 active E1 health incident → stand-by 即時補位。

**Track A W8 kill ladder v4.1**（per AMD-2026-05-20-02 §4.1，**reframe from "first live" to "demo evidence"**）：
- W2: LCS event-study t-stat < 1.5 OR pre-reg miss > 2σ → KILL LCS，all-in NLE shadow
- W2: t-stat ≥ 1.5 + replay match ≥ 80% → LCS demo deploy approved
- W6: demo 14d cum net edge < -5 bps → WARN, size reduce 50%
- W8: **demo Sharpe > 1.0 + DSR > 0.85 → Stage 1 micro-canary 預備**（live deploy 等 P0-LG/OPS clear）
- W8: demo Sharpe < 0.5 + NLE event-study 失敗 → KILL Track A → PIVOT signal service
- W12 (PIVOT path): signal subs < 5 → KILL Track A entirely
- W24: Track A revenue (live or signal) < $500 → HARD KILL → IP sale

**Track B kill ladder v4.1**（per AMD-2026-05-20-02 §4.2，**極簡無強壓**）：
- W4: learning.hypotheses schema 未 land → block Track B 進度
- W8: 0 hypothesis written → DEFER all Track B Tier 2+ to Year 2
- W24: < 10 hypothesis registered → downgrade Track B to dormant
- W24: ≥ 10 hypothesis + ≥1 demo Sharpe > 1.0 → GRADUATE → consider Tier 2 LLM generator build

**Live deploy 條件式**（取代 v4「W8 first live」承諾）：P0-EDGE-1 + P0-LG-1/2/3 + P0-OPS-1..4 全清 + Track A 完成 Stage 1+2 demo canary → operator 決議是否啟動 $200 live envelope。預期最早 N+5～N+6（W10-W14），悲觀帶 N+7+。

---

## §2 架構邊界

- 正式產品：`玄衡 · Arcane Equilibrium`。
- 交易所目標僅 Bybit。
- Rust `openclaw_engine` 是交易 / 風控 / 策略 config / 執行的權威。
- Python/FastAPI 是 control plane / bridge / GUI 後端 / replay+orchestration surface / 本地 5-Agent runtime host。不是交易事實層。
- 標準 GUI = FastAPI console `trade-core:8000/console`（OpenClaw Control Console）。
- 外部 OpenClaw Gateway 僅做通訊 / mobile / supervisor / proposal relay。不是交易 conductor，不是本地 5-Agent runtime，不是第二 GUI。
- 本地 Scout / Strategist / Guardian / Analyst / Executor 留在 TradeBot 內。Cloud L2 呼叫須走一次 supervisor escalation packet + 顯式 budget/model config + durable `agent.ai_invocations` ledger reservation。
- Scanner 是 always-on 基礎設施（市場脈絡 / active-universe attribution / route fitness / opportunity evidence / legacy would-block audit）。不是交易權威，無法 hard-gate opens / closes / live auth / order dispatch。
- `MessageBus` = legacy/advisory trace。權威 agent promotion 須 typed lineage：StrategySignal → StrategistDecision → GuardianVerdict → ExecutionPlan → Decision Lease / idempotency → ExecutionReport。
- Replay 是 advisory / diagnostic。可加速 preflight；不能取代 runtime lineage 或授權 live promotion。
- **Graduated Canary rebase**（AMD-2026-05-15-01 取代 AMD-2026-05-09-03 Stage 1 paper 語意）：alpha-bearing 走 Stage 0 shadow → Stage 0R Replay Preflight（`eligible_for_demo_canary=true/false`，非 Stage 1 PASS）→ Stage 1 Demo micro-canary（1 策略 × 1 symbol × `Environment::Demo` × 7d）→ Stage 2 demo extended ×14d → Stage 3 demo full ×21d → Stage 4 LIVE_PENDING。DOC-08 §12 9 條安全不變量 / SM-04 ladder / Live boundary 5-gate / §二 16 原則硬不變式 4 範圍**仍強制 binary fail-closed**，不被 graduated canary 觸碰。

---

## §3 當前活躍狀態

- W-C MAG-082 Stage 2 **WINDOW_PASS 2026-05-11** 與 W-D MAG-083/MAG-084 **DONE 2026-05-11**：已關閉；proposal / mobile / Stage 3+ / true-live gates 仍另立，被 edge/LG/ops 前置卡。
- A4-C BTC→Alt Lead-Lag active-promotion marker 移除：Step 5b 與 RCA 封存 **GATE-RED / no-revive**；`panel.btc_lead_lag_panel` 留 diagnostic-only。OI-confirmed 5m packet 僅是 replay spec，不改變 eligibility。
- `[55]` 已被 `P1-HEALTHCHECK-55-INVARIANT` source-cleared；`[67]` 經 feature baseline apply 後恢復 PASS；`[4]` phys lock 與 `[Xb]` triangulation 在 `7108035d` 之後 PASS。
- V079 / `learning.strategy_trial_ledger` runtime 已在 `trade-core` 應用（migrations 已到 V090）；觀察到 16,212 ledger rows。舊「V079 未 apply / engine 仍 5/8 binary」敘述已歸檔。
- **業務根因**：5 textbook 策略仍欠持續正 net edge。`P0-EDGE-1`、`P0-LG-1/2/3`、`P0-OPS-1..4`、Alpha Surface Phase C/D、替代 alpha 候選為當前路徑。
- **EDGE-P2-3 Phase 1b**：Round 1 Design/Governance + Worktree B 部署已 CLOSED（細節見 archive 2026-05-16 + 2026-05-19 v55 translation archive）。本 refactor 是 execution-quality optimization（fee saving ~$50-$200/年，per E3 empirical），不解 trading losses root cause；真實治癒走 W-AUDIT-8a/8b/8c alpha source 軸。
- **Trading losses Round 2 — Alpha Source Push**：Option A source/test + W-AUDIT-8c correction + V095 apply 已 DONE。C1 transport proof passed 2026-05-17，writer revival 已上線（`0e8a8ae8` / `bedc40c3`）。
- **2026-05-18 EDGE-P2-3 Phase 1b RUNTIME ACTIVATOR**：RESOLVED via deploy chain CLOSED；engine PID 1143103；`runtime.use_maker_close=true`。AC-A 24h 統計顯著性窗口已通過 INSUFFICIENT_SAMPLE 階段。
- **2026-05-18 W-AUDIT round 2 結局**：
  - W-AUDIT-8b Round 2 RED_FINAL **TOMBSTONED**（4-agent 4/4 APPROVE concur；spec v0.4 + AMD v0.7）
  - W-AUDIT-8a Phase B/C/D Wave 1 **MERGED**（B-REM-1 / B-REM-5 + ADR-0023 / C1-LIQ-WRITER + `[67]`）
- **2026-05-18 multi-agent dispatch race incident**：lesson learned = 不再多 E1 同時並行；single-agent sequential + E2 鏈完才下個（已 enforce）。
- **2026-05-18 Phase 1b parameter calibration**：12H sample 100% timeout_taker fallback → P0 calibration DONE 2026-05-18 13:50 UTC（top cell `G-AB-01-C90` fill 70.8% / +3.37 bps simulated；Grid family `timeout_ms 30s → 90s` deployed）。Phase 2a 14d observation clock reset @ 13:50 UTC。
- **2026-05-19 v55 sprint**：4 軌道 closure（見 §0）。
- **2026-05-19 ~20:00 UTC v56 incident**：engine 7h43m trading-inert（見 §-1）；新 P0 `P0-ENGINE-HALTSESSION-STUCK-FIX`；PA spec 已派；engine PID 2099215 自 20:09:36 起恢復；Phase 1b verification 繼續累積。
- **2026-05-20 v57 ratify**（見 §-0）：operator 補資金 demo $10k + live $1k；批准 v4 dual-track 取代 v2 ASDS 純路徑 + v3 lean 純路徑；4 governance artifacts（AMD-2026-05-20-01 + ADR-0025/26 + V101/V102 spec）land；業務根因更新為「**5 textbook 策略仍欠正 edge → Track A direct exploit (NLE/LCS) 8 週現金流 + Track B ASDS factory 12 個月規模化長線並行**」。舊「Alpha Surface Phase C/D + 替代 alpha 候選」敘事被 dual-track 重組吸收。

---

## §4 活躍派工佇列

**狀態圖示**：✅ DONE / ⏳ PENDING / 🟡 PARTIAL / 🔵 ACTIVE / ⛔ DEFER

### §4.1 Wave Roster（v57 雙軌制重組 + 8a-8h legacy entries）

**Track 標記**：A = Direct Exploit / B = ASDS Factory / C = Baseline / shared = 共用 infra

| 序 | Wave | Track | Owner | 狀態 | 出口條件 |
|---:|---|---|---|---|---|
| **T1** | `TRACK-SCHEMA` V101/V102 + Rust enum + Decision Lease attribution | shared | PA→E1→E2→MIT | ⏳ **PENDING**（v56 P0 完整 cycle 後 dispatch）| V101 apply + 7d soak + V102 apply + 5 acceptance pass per spec §5 |
| **T2** | `TRACK-A-NLE` New Listing Exploit（3 子策略 + listing watcher + risk carve-out）| A | PA→E1→E2→QA | ⏳ **PENDING**（依賴 T1 + v56 P0）| W2 demo deploy + W6 14d demo Sharpe > 1.0 + W8 first live |
| **T3** | `TRACK-A-LCS` Liquidation Cascade Scalper（cluster detector + LCS strategy）| A | PA→E1→E2→QA | ⏳ **PENDING**（依賴 T1 + T2 in-progress）| W4 demo deploy + Sharpe > 1.0 14d |
| **T4** | `TRACK-B-TIER0` CrossAssetPanel + Microstructure features + Universe tier classifier | B | PA→E1→E2 | ⏳ **PENDING**（依賴 T1）| Per-tick MarketStateSnapshot 落 metrics + universe split 落 PG |
| **T5** | `TRACK-B-TIER1` RegimeClassifier L0 (classical) + L1 (Ollama narrative) | B | PA→E1→E2 | ⏳ **PENDING**（N+2）| 5-class RegimeTag 落 tick_pipeline_metrics |
| **T6** | `TRACK-B-TIER2-3` Hypothesis Generator (L1 + Cowork sub) + Auto-Validator (CPCV + DSR) | B | PA→AI-E→E1→QC→E2 | ⏳ **PENDING**（N+3）| 第一個 L1 mutation + L2 novel hypothesis 通過 validator |
| **T7** | `TRACK-GUI` 4 tab skeleton（summary / exploit / asds / baseline）| shared | E1a→A3 | ⏳ **PENDING**（N+1 shared 10%）| 4 tabs 顯示 per-track P&L 獨立、無 cross-track 滲透 |
| **T8** | `TRACK-RISK-GUARDIAN6` Guardian check 6（per-track envelope enforcement）| shared | PA→E1→E2→BB | ⏳ **PENDING**（依賴 T1）| risk_config_*.toml 加 [track_budgets]；Guardian veto 超 envelope trade |
| **T9** | `TRACK-CONFLICT-RESOLVER` Cross-track conflict detection at Decision Lease | shared | PA→E1→E2 | ⏳ **PENDING**（N+2-N+3）| A 優先；B intent 標 BLOCKED_CROSSTRACK 落 audit log |
| — | — | — | — | — | — |
| 1 | `W-F` Edge/data quality + Live Gate 基座 | shared | PM→QC/MIT/PA→E1/E4→PM | ⏳ **PENDING**（true-live 前置；與雙軌制並行不衝突）| H0 production caller / pricing binding / supervised-live state machine |
| 2 | `W-G` Proposal/approval/mobile relay | shared | PM→CC/FA/PA→E1/E2/E4→PM | 🟡 **BACKEND 基座 DONE**（待 mobile relay）| Gateway/console proposal/approval relay；不可直發 order/config/live-auth |
| 3 | `W-AUDIT-4` ML 基座 + dead schema | B | E1×6 + MIT + E2 + E4 | 🟡 **PARTIAL**（W-AUDIT-4b retained 範圍歸 Track B 治理）| 修正後保留範圍見 §11.2；長尾治理 mount 進 `W-AUDIT-8f` → T6 |
| 4 | `W-AUDIT-8a` Alpha Surface 基座 | B | PA→E1→E2→E4 + MIT/QC/CC/BB→PM | ✅ Wave 1 MERGED；🟡 Wave 2 部分被 v57 frozen | per AMD-2026-05-20-01 §2.4：Tier 2 (FundingSkew/Basis) + Tier 4 (Sentiment) **FROZEN**；Tier 3 LiquidationCascade → T3；Tier 3 OrderflowImbalance → T4 |
| 5 | `W-AUDIT-8b` A4-A Funding Skew Directional | — | — | ⛔ **TOMBSTONED 2026-05-18 + FROZEN 2026-05-20**（v57 確認 no-revive）| — |
| 6 | `W-AUDIT-8c` A4-B Liquidation Cluster Reaction | A | PA→E1→E2/E4→MIT→BB→PM | ✅ writer DONE；🔄 **策略 launch redirect → T3 Track A LCS** | per AMD-2026-05-20-01 §2.5：launch 走 Track A direct exploit（bypass CPCV per ADR-0026），不走 ASDS Tier 3 |
| 7 | `W-AUDIT-8e`（R-2）Strategist Alpha Source Orchestrator | B | PA spec→E1 IMPL | ⛔ **重新 mapping → T6 Track B Tier 2/3** | 不再單獨追蹤；融入雙軌 Track B Tier 2 Hypothesis Generator |
| 8 | `W-AUDIT-8f`（R-3）Hypothesis Pipeline + W-AUDIT-4 ML | B | PA spec→E1 IMPL + MIT spec | 🔄 **拉前 → T6 + N+5 Tier 4/5/6/7** | per AMD-2026-05-20-01 §2.7：N+3 起 Tier 2-3 first cycle，N+5 full pipeline |
| 9 | `W-AUDIT-8g`（R-4）Per-alpha-source Live Promotion Gate | B | PA spec→E1 IMPL | ⛔ **DEFER N+5+**；簡化版 mount 進 T8（per-hypothesis live budget cap）| LiveBudget(hypothesis_id, slice) — per AMD-2026-05-20-01 §4.2 line "Track B $100 cap" |
| 10 | `W-AUDIT-8h` Alpha Sources GUI tab + Hypothesis Lab GUI tab | shared | E1a + A3 | 🔄 **被 T7 Track GUI 吸收** | 不再單獨追蹤 |
| 11 | `W-AUDIT-10`（R-5）Spec-as-Code + Module Lifecycle SM | alpha-neutral | PA spec→E1 IMPL | ⛔ **DEFER** 中期（v57 不衝突）| CI gate spec drift > 7d auto-fail + 模組/表 lifecycle 標頭 |
| 12 | `EDGE-P2-3 Phase 1b` Close-Maker-First Refactor | shared | PA→E1→E2→E4→QA→PM | ✅ **DEPLOY DONE**；Phase 2a observation 中（受益兩軌）| Phase 2a 14d clock reset @ 2026-05-18 13:50 UTC |

### §4.2 跨 Wave 衝突仲裁（4 條，PA §3.3 必繼承）

| # | 衝突 | 範圍 | 解 |
|---|---|---|---|
| 1 | W-AUDIT-8a Phase A migration ↔ W-AUDIT-6d mid-ground 5 策略改動 | `bb_breakout/mod.rs` / `ma_crossover/strategy_impl.rs` / `bb_reversion/mod.rs` | 序列化：先 6d mid-ground，再 8a Phase A |
| 2 | W-AUDIT-9 T3 shadow_mode_provider stage-aware ↔ ExecutorAgent shadow_mode 接線 | `executor_config_cache.py` / `executor_agent.py` | W-AUDIT-3b 必先 land；T3 結束前 ExecutorAgent shadow=true 不動 |
| 3 | W-AUDIT-8a Phase B+C ↔ W-AUDIT-5b 性能 wave | `tick_pipeline/mod.rs` | Phase B+C 並行於 N+1，5b 性能 catch-up reserved slot |
| 4 | A 群策略候選 ↔ W-AUDIT-9 Stage 1 Demo cohort 選擇 | governance/canary | **RESOLVED 2026-05-16**：Stage 1 為 Demo-only；A4-C tombstoned，不可作 cohort 來源 |
| 5 | TODO `W-AUDIT-8b/8c` ↔ legacy execution_plan `8b/8c` 檔名 | `docs/execution_plan` | **TODO IDs 為 SoT 2026-05-15**：`8b` = A4-A Funding Skew，`8c` = A4-B Liquidation Cluster；舊 `w_audit_8b_strategist...` / `w_audit_8c_hypothesis...` 是 R-2/R-3 alias（現為 `8e/8f`），不可拿來當策略 spec |

---

## §5 Sign-off Delta

完整 Sprint N+0 22-invariant ledger 已歸檔（v21 cleanup archive）。當前 delta：

- ⛔ **A4-C active-promotion marker 已移除 2026-05-16**：Step 5b / RCA 封存 no-revive；只留 tombstone guard 與 diagnostic panel 引用。
- 🟡 **OI-confirmed 5m Stage 0R packet 非 promotional**：定義 `bb_breakout_oi_confirmed_5m` replay 接受規則；read-only feasibility probe 樣本量 < Stage 0R 下限（`n=9` pooled；每 symbol < 100）且 gross 15m 為負，不能作 promotion 證據。
- ⏳ **A 群 alpha-source 不變量**：`declared_alpha_sources()` vs real logic re-check 待新 alpha 候選 land 後再啟。
- 🟡 **W-AUDIT-4b 修正後範圍**：透過 §11.2 retained tables/views/drop scope 維持 active；`P1-WA4B-INSERT-1` 已完成。
- `[55]`、W-AUDIT-3b、F-08 cron、`P0-MIT-LABEL-CLOSE-TAG-1` 細節已歸檔（v36 cleanup archive）；剩餘 edge 風險仍由 `P0-EDGE-1` 追蹤。

---

## §6 當前 W-AUDIT 優先順序

PM/PA/FA 三方交叉檢查後：

1. **True-live 仍 blocked**：被 `P0-EDGE-1`、`P0-LG-1/2/3`、`P0-OPS-1..4` 卡住。v56 `P0-ENGINE-HALTSESSION-STUCK-FIX` 已 CLOSED 2026-05-20；halt trigger 根因 follow-up 走 `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`。
2. **Stage 1 Demo micro-canary 仍 blocked**（非 active execution）：無 active paper cohort，無 A4-C cohort 候選；launch 需未來 strategy×symbol Stage 0R packet 且 `eligible_for_demo_canary=true` + AMD-2026-05-15-01 內 runtime/lineage/operator gates 全通。
3. **Alpha path 雙軌重組**：原 `W-AUDIT-8a..8h` 已 mount 進 v4.2 dual-track（見 §-0.B / §4.1 wave roster）。`W-AUDIT-8b` tombstoned；`W-AUDIT-8c` writer revival DONE；Track A LCS-first（per ADR-0026 v3）；Track B Hypothesis Ledger schema-only。業務鏈根因為 5 textbook 策略結構性 alpha-deficient。
4. **Runtime blocker 更新**：`[27]`、`[55]`、`[67]` 已 closed；不解鎖 Stage 1 Demo（無綠燈 alpha Stage 0R cohort）。v56 P0 cycle 完整收口後 unblock §-0.C Sequencing PHASE-0-MIGRATION-DRIFT-RECONCILE。
5. **Maintenance**：P2 hygiene 排在 alpha / LG / ops gates 之後；2026-05-20 P2 sweep 6 項 closure 已 land（§12.4 列表）。

### §6.1 A4-C BTC→Alt Lead-Lag Tombstone（2026-05-16）

`W-AUDIT-8d` A4-C 非 active promotion task。active docs 僅保以下 guard：

- 狀態：archived from promotion；diagnostic-only / no-revive（BTC 1m return + xcorr feature shape）
- 保留：`panel.btc_lead_lag_panel`、`[57] btc_lead_lag_panel_health`、歷史 rows（供未來 Hypothesis Pipeline 探索）
- 不保留：Stage 0R 候選 / Stage 1 Demo cohort 來源 / paper-based promotion 措辭 / threshold-only revive tasks
- 未來重啟：materially new predictive variable + preregistered validation + 全新 strategy×symbol Stage 0R packet 且 `eligible_for_demo_canary=true`

詳細 Step 5b / RCA / PM+QC+MIT verdicts 歸檔於 `docs/execution_plan/2026-05-15--a4c_btc_alt_lead_lag_archive_verdict.md` 與相應 archive。

---

## §7 W-AUDIT-6d Mid-Ground

詳細 保 6 / 砍 6 ledger 與 DSR K -12 推導已歸檔（v21 cleanup archive）。

**保留 active rule**：6 polishing 項仍 REJECT，未經未來 QC/PM 決議不可重啟；不可新增 per-symbol / per-threshold sweep（會膨脹 DSR trial count）。

---

## §8 D-02 Layer 2 手動 7d 試運行 SOP（Operator 自執行）

完整 6 步 SOP 見 FA report `2026-05-09--full_dispatch_business_chain_validation.md` §2。摘要：

1. **API key 取得**：Anthropic Console → Create Key（命名 `openclaw-layer2-manual-7d-trial`，monthly budget $5）
2. **寫入**：`echo "sk-ant-xxx..." > $OPENCLAW_SECRETS_ROOT/secret_files/anthropic/api_key && chmod 600`
3. **每日手動觸發 7d**：`curl -X POST http://localhost:8000/api/v1/layer2/run_session -d '{"trigger_kind":"manual_daily_probe","scope":"L1_triage","max_cost_usd":0.50}'`
4. **7d 4 指標觀察**：cost_today / decisions_assisted / avoided_loss / false_positive_rate
5. **Pass**：alpha > 2× cost + false_positive < 40% + 0 critical incident；**Fail**：alpha < cost OR false_positive > 60% OR ≥1 layer2 建議致 > 5 USDT 虧損
6. **Fail rollback**：`rm api_key && restart_all.sh --keep-auth`

**FA constraint**（invariant 15）：D-02 SOP 不可自動化為 cron / event-trigger（會違 ADR-0020 manual+supervisor-only）。預期 +2-5 USDT/week alpha；7d < 1 USDT/week 不值人工成本 → 建議 abort。

---

## §9 Dormant D-XX 區（FA §5.2 必 explicit + reason）

| D-XX | 描述 | 狀態 | 原因 | 最早重啟 |
|---|---|---|---|---|
| D-13 | Cognitive Modulator | DORMANT | 3-Tier `consecutive_loss/weekly_pnl` 數據源未接齊 + alpha 無依賴 | Sprint N+8+ |
| D-14 | DreamEngine 完整自主進化 | DORMANT | Foundation Model + L4 跨策略 meta-learning（ADR-0020 限 manual）；Foundation Model 未 ready | long-tail |
| D-15 | OpportunityTracker 全 Agent 注入 | DORMANT | 不影響 supervised live；Sprint N+5 可選 | Sprint N+5 可選 |
| D-16 | openclaw_core 9 模組 sunset cleanup | DORMANT | ADR-0015 已標 permanent sunset candidates；其中 7 模組已被 `P2-DEAD-RUST-CLEANUP-1`（2026-05-18 commit `449f628b`）清除，餘 2 待 PA 下 sprint 確認 | Sprint N+6+ |
| D-17 | Layer 2 自主推理循環自動觸發 | **PERMANENT DORMANT** | ADR-0020 manual+supervisor-only by design | **不解** |

**FA constraint**：靜默漏寫 = 6 個月後 lobby 重新 review；explicit 標 dormant + reason + earliest reactivate = 防 strategy drift。

---

## §10 P0 — True-Live Blockers

| ID | 狀態 | 任務 | 接收條件 |
|---|---|---|---|
| `P0-ENGINE-HALTSESSION-STUCK-FIX` | ✅ **DONE 2026-05-20 ~02:15 UTC**（Layer A + B 都 LIVE，real-event verified）| Layer A `6cf476c4` + Layer B `fec63743/8ad70090`；watchdog PID 2222237；Halt trigger 根因仍 UNRESOLVED → P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1。**詳情歸檔** `docs/archive/2026-05-20--todo_v57_3_closure_cleanup_archive.md` §A |
| `P3-AGENT-SPINE-BENCH` | ⏳ scheduled N+3 | emit_entry_lineage / emit_fill_completion bench harness | E5：當前只有 tick_pipeline hot_path_baseline；補 1000×100 sample SLA monitoring |
| `P3-SPINE-COUNTER-CACHE-ALIGN` | ✅ **DONE 2026-05-20**（待 Linux rebuild）| `channel.rs` 三 AtomicU64 改 `#[repr(align(64))]`；21/21 agent_spine unit tests pass；commit `879e3852`；歸檔 §B.1 |
| `LG-1` H0 production caller | ✅ **IMPL LANDED 2026-05-11** (`a11a4df6` + closure `0fb661d3`) — 待 7d observation | T1+T2+T3+T4 E1×4 並行 IMPL DONE；E2+E4+E5+A3 全 APPROVE；runbook `docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md` ship；**2026-05-19 PM audit TODO 同步斷裂修正** | per PA plan §1.4 |
| `LG-2` Provider pricing binding | ✅ **IMPL LANDED 2026-05-11** (`a11a4df6` + closure `0fb661d3`) — 待 7d observation | T1+T2+T3+T4 全 land；FeeSource enum + query_fee_source IPC + PricingConfig + Live spawn assertion；runbook `docs/runbooks/2026-05-11--lg2_pricing_assertion_failure.md` ship；**2026-05-19 PM audit TODO 同步斷裂修正** | per PA plan §2.4 |
| `LG-3` Supervised live SM | ⚠️ **SPEC v2 READY 8 days, Wave 2.4 IMPL DISPATCH PENDING** — 2026-05-19 PM audit catch silent stall | PA spec v2 final `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md`（1767 行，26 caveats incorporated：10 QC + 9 MIT + 7 BB）+ QC/MIT/BB 3-review 全 APPROVE 2026-05-11；**V094 號被 W-AUDIT-8c 佔用→必改 V099/V100**；Wave 2.4 IMPL E1×7 需 PA refresh dispatch plan（V### 號 + multi-E1 race-aware 排程 + 與 v56 P0 序列化）；**序列化於 v56 P0-ENGINE-HALTSESSION 完整 cycle 之後**派 | per PA plan §3.6 + §6.1 + §6.4；refresh plan dispatched 2026-05-19 |
| `P0-EDGE-1` | ACTIVE | Edge net-positive 決議 | 策略 edge 須 net-positive 或限定 supervised path；根因連到 `P0-MIT-LABEL-CLOSE-TAG-1` 1-day fix（最高 ROI） |
| `P0-LG-1` | 🟢 **IMPL LANDED, 待 7d observation closure** | H0 wired into production decision path + metrics + fail-closed (LANDED 2026-05-11) | E2+E4+E5+A3 APPROVE；evidence: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--wave2_2_lg1_lg2_e2_review.md` |
| `P0-LG-2` | 🟢 **IMPL LANDED, 待 7d observation closure** | Fee/pricing source 綁定、freshness 檢查、startup assert (LANDED 2026-05-11) | FeeSource enum + IPC + PricingConfig + Live spawn assertion 全 ship |
| `P0-LG-3` | ⚠️ **SPEC READY, Wave 2.4 IMPL DISPATCH PENDING** | Live authorization / lease / drawdown / revoke / operator approval 全顯式且測過 | spec finalize 2026-05-11；2026-05-19 PM audit catch 8d silent stall；Wave 2.4 IMPL 序列化於 v56 P0 完整 cycle 之後派 |
| `P0-OPS-1..4` | ACTIVE | HTTPS / credential rotation / legal+ToS / first-day runbook | True-live 前置 |

已完成 P0 條目（如 `P0-PHASE-1B-PARAM-CALIBRATION-1`）已歸檔於 `docs/archive/2026-05-19--todo_v55_translation_archive.md` 與 v36 cleanup archive。

---

## §11 P1 — 下個工程佇列

### §11.1 Sprint N+0 Active

已標完成歸檔於 v21 cleanup archive。當前活躍工作從 §10 / §11.2 / §11.3 開始。

### §11.2 W-AUDIT-4b 修正後保留範圍（invariant 19）

| ID | 物件 | 修正後分類 | Owner | 備註 |
|---|---|---|---|---|
| `P1-WA4B-INSERT-2` | `learning.cost_edge_advisor_log` | retained INSERT table / row-growth 已驗 | E1 | Writer live at `cost_edge_advisor/mod.rs`；2026-05-14 runtime 6091 rows。當前 demo `[cost_edge].enabled=false` → rows 為 `Disabled` / `ratio=NULL`；ratio-present rows 需另立 config 決議 |
| `P1-WA4B-INSERT-3` | `observability.drift_events` | retained INSERT table / readiness gated | E1 | Writer 在 `drift_detector.rs` 並在 `tasks.rs` spawn；依賴 active `feature_baselines` 與配置的 ADWIN burn-in（預設 30d）。不可未經 operator 同意移除 burn-in |
| `P1-WA4B-VIEW-1` | `learning.mlde_edge_training_rows` | companion VIEW | E1/MIT | 唯讀投影，非 INSERT 路徑。合約掛 ML training-data healthcheck |
| `P1-WA4B-VIEW-2` | `learning.scorer_training_features` | companion VIEW | E1/MIT | 唯讀投影；full unbounded count 成本高，請用 bounded/metadata probe |
| `P1-WA4B-DROP-1` | `learning.scorer_predictions` | dropped / no-DDL target | E1/MIT | V069 已 drop；無 producer 接線目標，除非未來 spec 重建 |

`P1-WA4B-INSERT-1` 完成細節歸檔於 v36 cleanup archive。

### §11.3 P1 — 其他活躍

| ID | 優先級 | 任務 | 備註 |
|---|---:|---|---|
| `P1-DATA-1..3-WATCH` | 3 | Runtime-reloaded WARN cluster row-rolloff watch | source 已修；保留 observation-only watch |
| `P1-EDGE-1..2` | 3 | ma_crossover/grid blocked_symbols 已 frozen + funding_arb 14d audit 2026-05-16 | 維持 freeze + 2026-05-16 audit |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch | source 活躍；audit-row 健康 |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | spec §5.4 完整 dynamic backoff state machine IMPL（per-symbol 1s exp → 60s + ≥10 symbol cascade → 5min global pause + audit row `rate_limit_scope="global"`）| Phase 1b 初版（commit `27f02a07`）取 per-symbol 5min 固定避 scope creep；Phase 2a Demo PASS 後另開 PR；PA 估 ~50 LOC state machine + ~80 LOC integration test |
| `P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX` | 2 | **NEW**：STATUS2 RCA 衍生 source-only follow-up。`engine_watchdog.py` 當前需 ≥5 連續 network-error lines in active `/tmp/openclaw/engine.log`；rotated/interleaved DNS outage 證據可能 default 到 `engine_crash` 觸發 restart storm。需 recent-log classifier 加固 + regression test，再依 3-strike stability 動作 |
| `P1-WATCHDOG-EXIT-CODE-CLARIFY` | ✅ **DONE 2026-05-20** | `engine_watchdog.py` exit codes 語意分區（`--status` 0/1；lock 10-19；rollback 20-29）；shell wrappers/systemd 不受影響；commit `dc33eb2d` + `232c3aff`；歸檔 §B.2 |
| `P1-LEASE-1` | 3 | **升級自 P2-LEASE-1（2026-05-20 PM-conducted P2 sweep operator 拍板升 P1）**：清掃 terminal `rust/openclaw_core/src/sm/lease.rs:303` `DecisionLeaseSm.objects: Vec<LeaseObject>` entries 避免長 soak memory growth + E2 memory SM-02 leak（HashMap `lease_id_to_idx` 不清）。**依賴 P0-LG-3 Wave 2.4 IMPL DISPATCH 完成後**才排專案（否則觸碰 Decision Lease 核心會干擾 LG-1/LG-2 7d obs + LG-3 IMPL 前置）。spec 需含：(1) terminal state 定義（哪些 `LeaseState` 不可再 transition 可 prune）/ (2) `lease_id_to_idx` HashMap 同步策略 / (3) audit-preserving prune（被刪 lease 必先 ship 到 PG `governance_audit_log` 或 audit log file，不可純失）/ (4) prune 觸發時機（gc tick / 時間閾值 / size 閾值）/ (5) Python `_lease_sm` 對等同步。工時估 4-6h IMPL + E1→E2 對抗（A3）→E4 regression chain。Ticket source: §12.1 deferred + FA 5-OQ-style 5 條 spec 需求 |

> v55 衍生：`FA-WATCHDOG-3STRIKE-ESCALATION-POLICY` 待 FA 設計後分配優先級。

歸檔的 P1 條目：v36 cleanup archive + 2026-05-19 v55 translation archive。

### §11.4 P0-MICRO-PROFIT — 微利根因治本路徑（2026-05-11 QC audit 拍板）

**背景**：QC 2026-05-11 audit verdict — 「為何盈利都是超微利潤」+「能否放大」。判定：當前 5 textbook 策略 7d EV<0（-17.82 bps demo）；**任何 sizing 槓桿 L>1 必放大虧損**（數學常數）。先修 alpha，再談 size。

**5 root cause + 占比**：
1. **Alpha 結構性缺失（~60%）** — 5 textbook 策略 post-publication decay
2. **Account size × 0.1% TOML 物理上限（~20%）** — $591 × 0.1% = $0.59/trade 設計上限
3. **Fee drag（~10%）** — 10.4% taker remnant + PostOnly missed-trade
4. **Signal target tight 設計（~5%）** — grid 22bps / bb 1-2σ / ma sub-1ATR
5. **Slippage + queue position adverse selection（~5%）**

**治本路徑 = PA R-1/R-2/R-3 redesign（已映射 W-AUDIT-8a..8f wave 矩陣）**：

| ID | 任務 | Spec 來源 | ETA |
|---|---|---|---|
| `W-AUDIT-8a` Phase B/C/D | Tier 2 panel collector + Tier 3 microstructure + Tier 4 information flow | Sprint N+1 W2 起 | 4-6 sprint |
| `W-AUDIT-8b`（A4-A）| Funding Skew Directional（R-1 IMPL）| ⛔ **TOMBSTONED 2026-05-18** | — |
| `W-AUDIT-8c`（A4-B）| Liquidation Cluster Reaction | ✅ source/test + V095 apply + writer revival DONE | 策略 launch 仍另立 Stage 0R/design gate |
| `W-AUDIT-8d`（A4-C tombstone）| BTC→Alt Lead-Lag diagnostic panel | Archived guard only | ⛔ 不再 active；diagnostic-only |
| `W-AUDIT-8e`（R-2）| Strategist Alpha Source Orchestrator | W-AUDIT-8b/8c/8d 後 | N+3-N+4 |
| `W-AUDIT-8f`（R-3）| Hypothesis Pipeline first-class（含 W-AUDIT-4 ML 6 dead schema 併入）| 序列化於 R-2 後 | N+4 |

**Total ETA = 12-17 sprint（3-4 月）** — 真實 gross 轉正最早窗口。

**Operator 5 zero/small cost action（2026-05-11 拍板）**：
1. ✅ DONE：修 `feedback_position_sizing` memory drift（3% → 註明 SSOT 0.1%/0.05%）
2. ⏳ PASSIVE wait：等 7d 重測 §3 [40]
3. ⏳ INFO gathering：Bybit fee tier 距 VIP1 還差多少 30d trading volume（被動 ROI ~0.5-1 bps RT）
4. ⏳ PASSIVE wait：TONUSDT 30d evidence → P1-CONDITIONAL-WATCH freeze 決議（2026-06-09 收口）
5. ✅ DEFER 記錄：D/E sizing 槓桿等 ML calibration N≥200 — 寫入 backlog 防過早 commit

**11 sizing 槓桿全 REJECT in current EV<0 state**（A/B/E/F = REJECT；C/I = CONDITIONAL；D = NEUTRAL；G/H/K = DEFER；J = APPROVE 被動）。

**Operator 守則**：
- 看見 memory「3%」**不要**直接套到 TOML（先讀 risk_config_*.toml SSOT）
- 任何「升 TOML sizing」提案在 EV<0 條件下 = 災難（先修 alpha）
- 信 config，不信 memory（per `math-model-audit` S1）

**Source**：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--p1_micro_profit_amplification_math_analysis.md`

### §11.5 EDGE-P2-3 Phase 1b — Final Dispatch Plan 摘要

**Status**：Round 1（Design + Governance）closure + 30+ commit timeline + 4-agent verdict + IMPL Prereq status + next-round scope → 歸檔 `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`。Phase 1b main source/test 完成於 `ea4ceca6`；V094 Linux apply + engine-only deploy/restart 完成 2026-05-17。

**仍 active**：
1. ❌ `P0-EDGE-1` — `[40]` negative realized edge 仍 active
2. ⛔ `W-AUDIT-8b Stage 0R` — **TOMBSTONED**（細節歸檔）
3. ✅ `W-AUDIT-8a C1` — v2 24h proof technical PASS + writer revival DONE 2026-05-17
4. ✅ `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG` — DONE 2026-05-16
5. ✅ `P1-BBMF3-WIRE-1` — source/test + V094 apply + engine-only rebuild/restart DONE 2026-05-17
6. ✅ `W-AUDIT-8c` — source/test 修正 + V095 dry-run/MIT re-sign + Linux apply + writer revival DONE 2026-05-17。策略 launch/promotion 仍 future gate

**Runtime kickoff status**（精簡）：
- V094 Linux migration/deploy 授權 → deploy-chain regression → post-deploy healthcheck → PM sign-off：✅ DONE 2026-05-17
- Phase 1b runtime activation：✅ **DEPLOY DONE 2026-05-17 23:54 UTC**（engine PID 1143103）
- Calibration sweep + Rust timeout deploy：✅ **DONE 2026-05-18 13:50 UTC**（engine PID 1506208；grid family timeout 30s→90s）
- **Phase 2a 14d observation clock 已 reset @ 2026-05-18 13:50 UTC**；24h post-deploy AC-A SQL verification target ~2026-05-19 13:50 UTC
- Cross-wave consistency check pending（QA recommendation #3）
- Outstanding anomaly investigations（low-priority parallel SD agent 2026-05-18 dispatch）：SD-1 A axis（offset_bps）dead-variable / SD-2 PS family（phys_lock_gate4_stale_roc_neg）100% n_skip / 0 fill — 報告 `2026-05-18--phase_1b_calibration_sweep_anomalies_sd_report.md`
- 後續：24h AC-A real verdict → if PASS 繼續 Phase 2a 14d / if FAIL revert timeout 90s→30s 或 PA tune-further；Phase 2b LiveDemo / operator + AMD live carve-out / Phase 3 Mainnet 仍 future gate
- **v56 incident 衝擊**：2026-05-19 ~12:27-20:09 UTC 7h43m trading-inert 中斷 Phase 1b verification；engine 自 20:09:36 起新 PID 2099215 恢復，sample 繼續累積（n=13 起）。verdict 視窗（T+96h~T+120h，2026-05-22~23 UTC）不受影響但 sample velocity 有缺口。

### §11.6 12-Agent Full System Audit WPs（2026-05-16）— follow-ups

- **Source**：`srv/2026-05-16--full-system-audit-fix-plan.md`（PA consolidated + PM sign-off）
- **Wave 1-4 source/test**：完成並歸檔於 v36 cleanup archive

**剩餘 active follow-up**：
- WP-11 Phase 2 residual → §12 P2 backlog
- WP-12 ONNX 仍 deferred；rule-based fallback 為當前行為
- PA audit drift hardening → `P2-PA-CALLPATH-GREP-RULE`（已 DONE）
- LOC follow-up → `P2-COMMON-JS-LOC`（DONE）、`P2-TAB-LIVE-LOC`（DONE via JS extract）

---

## §12 P2 — 維護 backlog

### §12.1 Active backlog（3 項 deferred — operator push back rationale）

| ID | 任務 | 觸發 | Deferred 理由（2026-05-20 sweep） |
|---|---|---|---|
| `P2-LEASE-1` | ⬆️ **升 P1** 2026-05-20（見 §11.3 `P1-LEASE-1`）| 長期 soak 出現 memory growth 或 high-volume live 前 | operator 拍板升 P1；依賴 P0-LG-3 Wave 2.4 IMPL DISPATCH 完成；歷史 P2 級觸發條件保留作 reference |
| `P2-AUDIT-DEAD-CODE` | openclaw_core 9 模組 sunset（D-16 dormant）| ADR-0015 + AMD-2026-05-09-02 accept；Sprint N+6+ | **ADR-0015 治理硬不變式**：D-16 dormant 觀察期未跑完，提前 sunset 破壞觀察協議；保留待 Sprint N+6+；E5 2026-05-20 zombie inventory 確認 commit `449f628b` 已清乾淨 7 modules，剩餘 sunset 在觀察期 |
| `P2-WP05-CSP-UNSAFE-INLINE` | 🟡 SRI 部分 DONE 2026-05-18；完整 CSP nonce-based refactor 待 live-gate 前 P1 | live-gate 前 | §10 P0-OPS-1..4（HTTPS / cred rotation / legal）尚未做完；HTTP 環境下 nonce-based CSP 防護無實效；保留待 live-gate prereq 完成後升 P1 |

### §12.2 2026-05-20 P2 sweep 結算 — 6 項 DONE → §12.4 列表

詳情歸檔於 `docs/archive/2026-05-20--todo_v57_3_closure_cleanup_archive.md` §C。本次 sweep 包括：QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX / STRUCT-2 zombie inventory / AUDIT-VERIFY-3 V069 drop verify / ENTRY-CLOSE-MAKER analysis / STRESS-BB-BREAKOUT-FALSE-SQUEEZE / SIM-QUEUE-AWARE-ADJUSTMENT。Commit chain `12dcdcbc` + `e2d213b5` + `a39dd11b` + `c3f25496`。

### §12.3 2026-05-20~21 P2 sweep 衍生 follow-up（從 FA P2-ENTRY-CLOSE-MAKER 分析衍生）

| ID | 來源 | 任務 | 優先 | 狀態 |
|---|---|---|---|---|
| `P1-OBS-PLACEMENT-BBO-V094` | FA OBS-1 | 補 placement-time BBO 進 V094 audit `details` JSONB（append-only schema-compat） | P1 | ⏳ Phase 1b 14d freeze 後 |
| `P1-OBS-PRE-STOPOUT-RATE` | FA OBS-2 | 新 healthcheck `66_close_maker_pre_stopout_rate.py`（FA round 1 #5 緩解未掛 AC） | P1 | ✅ DONE 2026-05-21（E1 R1+R2 / E2 R1 RETURN + R2 APPROVE-COND / E4 regression；slot [71]→[66] 防 passive_wait 碰撞）|
| `P1-OBS-FILL-RATE-STRATIFY` | FA OBS-3 | `62_close_maker_fill_rate.py` 加 `--stratify {hour,dow,both,none}` flag | P1 | ✅ DONE 2026-05-21（同上）|
| `P1-SPEC-DEAD-ENUM-ADR` | FA SPEC-1 | V094 fallback_reason 3 dead enum 寫 ADR reservation note；不 sunset | P1 | ✅ DONE 2026-05-21（ADR-0028 Accepted-pending-commit）|
| `P2-EVID-TRADE-TAPE-ADR` | FA EVID-1 | ADR：`market.public_trades` + `market.orderbook_l2_snapshot` 寫盤策略（PA+MIT 起草） | P2 | ✅ DONE 2026-05-21（ADR-0029 Proposed；故意不 finalize schema 等 MIT calibration；6 步 dispatch 路徑 per PA report）|
| `P2-EVID-A-AXIS-IMPL-CHECK` | FA EVID-2 | offset_bps 變量是否進入 cross 判定（25% probability IMPL bug） | P2 | ✅ AUDIT DONE 2026-05-21（FA verdict：**IMPL WIRED FOR LOG ONLY** — 100% silent dead；升級為 OQ-C4-1..5 5 條 follow-up；建議 sweep prune A axis + spec v1.4 mark deprecated）|
| `P2-SPEC-PHYS-LOCK-AUDIT` | FA SPEC-2 | Phase 1b spec §4.3 補 `phys_lock_gate4_stale_roc_neg` audit | P2 | ✅ AUDIT DONE 2026-05-21（FA verdict：**spec PRESENT but incomplete** — emit point v2.rs:359 production wiring 完整；spec §4.3 缺 observability SLA；建議 v1.4 加 §4.3.1 + [72] healthcheck + per-reason kill-switch）|
| `P2-SPEC-HOUR-DISTRIBUTION-AC` | FA OQ-5 | spec v1.4 加 secondary AC | P2 | ✅ DONE 2026-05-21（TW v1.3→v1.4 加 AC-20 hour distribution ≥ 18h cover + ≥ 3 attempts；secondary AC，違反僅 WARN）|

### §12.3a P2 sweep 衍生新增 follow-up（C 批 2026-05-21 完成後派生）

| ID | 來源 | 任務 | 優先 |
|---|---|---|---|
| `P2-OBS-PRE-STOPOUT-WILSON-SUBCLAUSE` | E2 R2 MEDIUM-D1 deferred | `66_close_maker_pre_stopout_rate.py` 補 Wilson upper bound sub-clause（mirror [62] AC-18 風格）；E2 已接受 raw rate 設計，但 min_sample=30 對 0.10 boundary 不 conservative | P2 |
| `P1-SWEEP-A-AXIS-PRUNE` | FA C4 verdict + SD-1 | 下一輪 phase_1b sweep 把 A axis (`offset_bps` 0/+1/+2) collapse 到 1-value；可省 ~58 cells × ~17ms；spec v1.4 mark `offset_bps` as deprecated config field | P1 |
| `P2-PHYS-LOCK-72-HEALTHCHECK` | FA C6 OQ-C6-2 | 新 standalone healthcheck（slot 待 PA 分配，建議 [68]/[69]/[76]）監測 `phys_lock_gate4_stale_roc_neg` trigger rate vs `gate4_giveback`；daily cron | P2 |
| `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` | ADR-0028 §6 cadence | 90d 後（2026-08-21）re-audit V094 `close_maker_fallback_reason` 3 dead variants；確認仍 dead-by-design 非 missing-data；若 EngineShutdownSafety 仍 0 → confirm；FastEscalate/NotAttempted 須 ops scenario sim 驗 emit path | P2 |

### §12.4 已完成 P2 條目（細節歸檔於 2026-05-19 v55 translation archive / 2026-05-20 v57.3 archive）

- `P2-DEAD-SCHEMA-DROP-1` ✅
- `P2-DEAD-RUST-CLEANUP-1` ✅
- `P2-PERCEPTION-DEPRECATE-1` ✅
- `P2-H0-DISPLAY-LABEL-1` ✅
- `P2-ORDERS-INTENT-ID-WRITER-GAP-1` ✅
- `P2-WP05-FUP-1` ✅ 32/32 全收
- `P2-COMMON-JS-LOC` ✅
- `P2-ENTRY-PATH-0PCT-MAKER-FILL-RCA` ✅
- `P2-TAB-LIVE-LOC` ✅ via `P2-TAB-LIVE-JS-EXTRACT`
- `P2-CROSSTAB-I18N` ✅
- `P2-STOCHASTIC-LEAK` ✅
- `P2-START-LOCAL-HELPER` ✅
- `P2-PA-CALLPATH-GREP-RULE` ✅
- 5 個 `P2-PORTFOLIO-RESTING-*` follow-up ✅
- `P2-QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX` ✅ 2026-05-20
- `P2-STRUCT-2` ✅ 2026-05-20
- `P2-AUDIT-VERIFY-3` ✅ 2026-05-20
- `P2-ENTRY-CLOSE-MAKER-REAL-FILL-FIX` ✅ ANALYSIS 2026-05-20
- `P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS` ✅ 2026-05-20
- `P2-SIM-QUEUE-AWARE-ADJUSTMENT` ✅ 2026-05-20

完成的 Sprint N+2 P2 條目（`P2-N2-1..4`）歸檔於 v36 cleanup archive。

---

## §13 Push Back / Risk 治理記錄（不可漏失，FA §5.6）

### PA Push Back（已 RESOLVED 2026-05-09 operator (a)）
- **原 risk**：Sprint N+0 5/5 HOT capacity = 任一 E1 故障 = 阻塞 critical path
- **Operator 拍板 (a)**：提供 1 stand-by E1，Sprint N+0 capacity 升 6 並行（5 active + 1 stand-by）
- **記錄**：v19 §0 Sprint Banner / §5.4 invariant 22 / §6 Day 0-3 dispatch

### FA Push Back（採納，記入治理）
1. Track W vs Track A 預算 — Track W 92h 是 supervised live 前置門檻（合規 / 安全 / 可觀測 baseline），**不能被 Track A lobby 取代**
2. D-02 SOP 預期上限 +2-5 USDT/week；7d < 1 USDT/week 不值人工 fixed cost → 建議 abort
3. A/B/C 候選預期 +3-7% 業務鏈是中位估，新 alpha source **0% PASS 率歷史不支持「三都 PASS」樂觀情境**
4. W-AUDIT-6d 砍 6 polishing 是 DSR 數學意義 right move（K -12），不是省工時妥協

### 4-agent loss audit cross-fact-check（撤銷的 stale belief）
- **QC v2-NEW-4 Donchian「runtime contaminated」過期 belief**：MIT 校核 + PM 直接驗證確認 runtime 自 `75741eff`（2026-04-28）起 leak-free 11 天；`ad14db07` 僅補 regression test。後續 audit / push back 不可再引此 finding 為 active runtime issue。

---

## §14 排程

| 日期 | 工作 | Gate |
|---|---|---|
| 2026-05-21..27 | v4.2 dispatch W3-W4：PHASE-0 reconcile + V101 apply + Track A LCS event-study + NLE shadow watcher + Tier 0/1 shared + GUI summary tab | 序列化於 §-0.C；migration drift V096-V098 catch-up serial |
| 2026-05-28..06-03 | v4.2 W5-W6：LCS demo deploy + 14d soak start / NLE 收 5+ events shadow / Hypothesis Ledger CRUD / V102 apply / GUI exploit tab | Sprint N+2 |
| 2026-06-04..10 | v4.2 W7-W8 fork review：LCS 14d evidence packet + NLE first event-study report；W8 verdict（demo Sharpe / DSR gates）| Sprint N+3；W8 milestone = demo evidence + live-ready proof（非首 live） |
| 2026-06-11..17 | v4.2 W9-W10：branch by W8 verdict — LCS Stage 1 prep / PIVOT signal service / KILL | Sprint N+4 |
| 2026-06-18..07-01 | v4.2 W11-W14：6-month review + W24 prep | Sprint N+5..N+6；業務鏈 85-88% |
| 2026-06-15 | Supervised live 樂觀帶（業務鏈 75%+）| conditional on P0-LG-1/2/3 + P0-OPS-1..4 + Track A demo Sharpe > 1.0 |
| 2026-06-30 | Supervised live 中位帶（業務鏈 80%+）| ~40% probability per FA |
| 2026-07-15 | Supervised live 悲觀帶（業務鏈 85%+）| ~25% probability per FA |

---

## §15 派工規則 + Handoff 檢查

### 派工規則
- PM-first triage for every wave
- 實作工作：`PM → PA → E1/E1a → E2 → E4 → QA → PM`，跳過角色需 explicit justify
- 安全 / 部署 / runtime：`PM → E3 → BB（若涉交易所）→ PM`
- 量化 / 資料決議：`PM → QC → MIT → AI-E（若涉模型成本）→ PM`
- 每個 green checkpoint 提交 subject + body，push origin，再以 fast-forward 同步 Linux
- 非 CI-relevant commit（doc / governance / TODO update / report land）加 `[skip ci]` 保 CI 額度
- 不可 rebuild / restart / 動 live auth / 改 scanner evidence contract / 解鎖 executor shadow / 啟 lease-router / 新增 OpenClaw write/proposal 路徑，除非 operator 顯式授權
- W-AUDIT-6d 砍 6 子項：E2 必 grep blacklist；命中即 reject merge
- **新增（v55 governance flag）**：sign-off SOP 加 `cargo test -p openclaw_engine --release`（no --lib）以覆蓋 tests/ integration crate

### Handoff 檢查

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

## §16 References

### 4-Agent Loss Audit（2026-05-09）
- **PA dispatch plan**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md`（commit `d3bf7be2`，689 行）
- **PA architectural redesign**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`
- **PA merge analysis**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--todo_qctodo_merge_analysis.md`
- **FA business chain validation**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_dispatch_business_chain_validation.md`（commit `5a2dee98`）
- **FA dormant alpha inventory**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_loss_dormant_alpha_features_inventory.md`
- **FA merge advice**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--todo_qctodo_merge_business_chain_advice.md`
- **4-agent loss audit worklog**：`docs/worklogs/2026-05-09--4_agent_loss_audit_and_5_actions.md`
- **QCTODO archived**：`docs/archive/2026-05-09--qctodo_sprint_n0_n5_archive.md`

### Spec / Amendment
- **W-AUDIT-8a spec**：`docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`（commit `c13c811e`）
- **AMD-2026-05-09-02**（5 P0-DECISION-AUDIT closure）：`docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md`
- **AMD-2026-05-09-03**（Graduated Canary Default）：`docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`（commit `b1891023`）
- **AMD-2026-05-15-01**（Canary Rebase Replay Preflight + Demo Micro-Canary）：`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`
- **AMD-2026-05-15-02 v0.7**（EDGE-P2-3 Phase 1b Close-Maker-First + Runtime Activation Layer + W-AUDIT-8b tombstone clause）：`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- **EDGE-P2-3 Phase 1b spec v1.3**：`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`
- **V094 hybrid schema migration spec**：`docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- **Round 1 Closure Archive**：`docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`
- **W-AUDIT-8b Funding Skew Directional spec v0.4 tombstone**：`docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`
- **v56 P0 Engine HaltSession TTL spec**：`docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md`（~600-1000 LOC，PA drafting，ETA 2-3h from 2026-05-19 20:30 UTC）
- **ADR-0015** openclaw_core sunset / **ADR-0017** scanner authority retirement / **ADR-0018** funding_arb retire / **ADR-0020** Layer 2 manual+supervisor-only / **ADR-0022** strategist cap / **ADR-0023** SourceAvailability schema

### Close-Maker-First 3-agent Verdicts（2026-05-15 round 1 — Spec）
- **PM verdict**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--close_maker_first_pm_verdict.md`
- **PA verdict + spec outline**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md`
- **FA verdict + AC**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--close_maker_first_fa_verdict.md`

### Close-Maker-First 4-agent AMD Adversarial Review（2026-05-15 round 2 — AMD）
- **QC**：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_qc.md`
- **FA round 2**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_fa.md`
- **BB**：`docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_bb.md`
- **MIT**：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_mit.md`
- **Consolidated 4-agent summary**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_consolidated.md`

### v56 P0 incident
- **E2 RCA verdict**：`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-19--engine_watchdog_respawn_loop_and_trading_inert_rca.md`
- **PA spec（drafting）**：`docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md`

### Adversarial Verification
- **v3 PM Sign-off summary**：`2026-05-09--audit_fix_verification_v3_summary.md`
- **v2 PM Sign-off summary**：`2026-05-09--audit_fix_verification_v2_summary.md`
- **v1 PM Sign-off summary**：`2026-05-09--audit_fix_verification_summary.md`
- **PA Fix Plan v2（DUAL-TRACK）**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md`
- **2026-05-08 12-Agent Full Audit + PA Fix Plan**：`2026-05-08--full_audit_fix_plan.md`
- **Verified-closed archives**：`docs/archive/2026-05-09--w_audit_verified_closed_archive_{,v2,v3}.md`

### Bybit / API
- **Bybit API 字典/審計**：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`

### Process
- **Operator G3-08 enable evidence**：commit `dddc5dc1` restart_all.sh wire + 2026-05-09 17:27 UTC engine.log `cost_edge_advisor spawned env=1 phase=B_shadow`

### v55 翻譯歸檔
- **歷史 ✅ DONE 詳情**：`docs/archive/2026-05-19--todo_v55_translation_archive.md`（本次同步建立，收納 v37-v55 之 carry-forward 全文 + §11 / §12 已完成 commit chain）
