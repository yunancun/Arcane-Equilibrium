# REF-20 Paper Replay Lab Implementation Workplan V1

**日期：** 2026-05-03
**狀態：** P0 commit-ready implementation workplan（合成 PA + FA + QC + A3 + E3 五份專業 breakdown）
**Owner：** PM
**契約上游：** `2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`（V3 contract baseline）
**UX SoT：** `2026-05-02--ref20_ux_subdoc_v1.md`
**前置已過：** `docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md`（5/5 PASS, V3 §3 G6 解封）
**5 份子報告：**
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_v3_implementation_breakdown.md`（PA file landed）
- FA / QC / A3 / E3 各自 finding 已綜合進本文檔 §3-§7

---

## 0. TL;DR

REF-20 V3 拆 **9 個 Wave / 76 個 atomic task**（≤2 sprint 每 task），總工時 **12-14 sprint**（不含 P5 等 LG-2/3/4 stable 期；含等期 14-18 sprint）。所有 task 標明 owner + reviewer chain（per CLAUDE.md §八 強制工作鏈）+ parallel / sequential 標記 + V3 §12 acceptance check 綁定。

**Wave 1 立刻可開**（P0 docs amendment + scaffold 設計），Wave 2 起需要 5 個 hard prerequisites 中至少 1 個 GREEN（Wave 5+ 才需要全部 GREEN）。

---

## 1. 9-Wave 排程帶（PA 主筆）

| Wave | Sprint | Phase 內容 | 並行度 | Hard Prereq |
|---|---|---|---|---|
| **Wave 1** | 1 | P0 全 9 task 並行（docs only）| 高 | 無（V3 已 land） |
| **Wave 2** | 2-3 | P1 IA shell + P2a 三 schema 起頭 | 高（P1 內 Wave 2-4 多軸並行） | UX subdoc 已 land |
| **Wave 3** | 3-5 | P2a 收尾 + P2b 起頭 | 中（P2a S2 signer land 後 P2b 開工） | migration V### PM 預留完成 |
| **Wave 4** | 5-6 | P2b 收尾 + Compare/Mac 路徑 | 高 | 無新 prereq |
| **Wave 5** | 6-8 | P3a + P3b 並行 | 中（P3a 內 sequential gate） | **FUP-2 attribution writer deploy** + **decision_outcomes timeframe fix** + **21d demo unlock 2026-05-07** |
| **Wave 6** | 8-10 | P4 advisory（DSR/PBO/Dream/MLDE） | 中 | P3b green |
| **Wave 7** | 事件觸發 | P5 5-Agent 抽出 | 低 | **LG-2/3/4 frontend merged + 7d stable** |
| **Wave 8** | 10-12 | P6 demo handoff | 中 | P4 green + Decision Lease retrofit (AMD-2026-05-02-01) deploy |
| **Wave 9** | 12-14 | 14d gradient observation + 收尾 | 低 | P6 deploy |

---

## 2. 跨 Phase 並行 DAG

```
                    HARD PREREQS
                    ┌─[FUP-2 attribution writer deploy]──────────────┐
                    ├─[decision_outcomes timeframe '1' vs '1m' fix]──┤
                    ├─[21d demo unlock 2026-05-07]───────────────────┤
                    ├─[migration V### PM reservation]────────────────┤
                    ├─[Decision Lease retrofit AMD-2026-05-02-01]────┤
                    └─[indicator leak-free sweep ✅ PASS 2026-05-03]─┘

Wave 1 (sprint 1)
  P0-T1 (PA+PM) REF-19/20 v2 amendment draft   ⫴
  P0-T2 (PA+E1) replay_runner binary scaffold  ⫴
  P0-T3 (PA+E3) ReplayProfile cfg gate design  ⫴
  P0-T4 (PA+E1a) UX subdoc placeholder ack     ⫴
  P0-T5 (PM)    migration V### reservation     ⫴
  P0-T6 (E1)    既有 mlde_shadow INSERT grep 清單 ⫴ (E3 §6 unknown #1 解決)
  P0-T7 (E1)    既有 source 分類 SELECT DISTINCT ⫴ (E3 §6 unknown #7 解決)
  P0-T8 (PM+QC) signature_key 部署 plan        ⫴
  P0-T9 (PA+E3) replay_runner crate 邊界白名單  ⫴ → E2 sign-off

Wave 2 (sprint 2-3) — P1 + P2a 起頭
  P1-U1  shell 結構 ───┐
                       ├──→ ⫴並行 → P1-U2/U4/U5/U6/U7/U8/U9
  P1-U10 a11y          │
  P2a-S1 signing key gen + deploy ⫴
  P2a-S2 HMAC sign/verify module  ⫴
  P2a-S3 8 routes auth scaffold   ⫴

Wave 3 (sprint 3-5) — P2a 收尾 + P2b
  P2a-S4 DB role REVOKE/GRANT (3-PR sequence) → S5 quota → S6 retrofit migration
                                              │
  P2b-S7 ReplayProfile::Isolated cfg gate     │
  P2b-S8 fail-closed enforcement              │ ⫴ 3 並行
  P2b-S9 Mac policy guard                     │
  P2b-S10 nm/objdump symbol grep (CI step)    │

Wave 4 (sprint 5-6) — P2b 收尾
  P2b-T1 isolated runner wrapper land
  P2b-T2 baseline-vs-candidate comparison route
  P2b-T3 canary/diagnostic artifacts registered
  P1-U3 移除 manual submit/cancel (依 P2b shell 完整) → close P1

Wave 5 (sprint 6-8) — P3a + P3b 並行
  P3a-Q1 half-life ─┐
  P3a-Q3 bootstrap  ├──→ P3a-Q4 shrinkage tree ─→ P3a-Q6 freshness/power gate
  P3a-Q5 fee model ─┘
  P3a-Q2 embargo (independent, ⫴)
                    ↓ (Q1+Q3+Q4 land)
  P3b-Q1 cell n=30 gate ──→ P3b-Q2 NumPyro hierarchical
  P3b-Q3 S1 spec stub (PM)
  RGM-Q1 warmup ──→ RGM-Q2 CUSUM ──→ RGM-Q3 Kupiec ──→ RGM-Q4 PSR (sequential 4)

Wave 6 (sprint 8-10) — P4
  P4-Q4 DreamEngine API ──→ P4-Q5 MLDE veto ──→ P4-Q1+Q2+Q3+Q6 (4 並行收尾)
  P4-S11 mlde_demo_applier source filter
  P4-S12 safe_query mirror (P2a 已起，P4 完整 binding)

Wave 7 (事件觸發) — P5
  Wait: LG-2/3/4 frontend merged + 7d stable
  P5-A1 12-Tab 抽出位置決策 ─→ P5-A2/A3 ⫴ → P5-A4 icon

Wave 8 (sprint 10-12) — P6
  P6-H1 Typed confirm modal ─┐
  P6-H2 Cooldown + 雙 actor   ├──→ P6-H4 idempotency
  P6-H3 Footer recent 5      ─┘
  P6-S13/S14/S15 security trio (typed phrase regex / unique constraint / audit row)

Wave 9 (sprint 12-14)
  14d gradient observation (replay_no_live_mutation continuous)
  business KPI 採集 + Phase exit sign-off
  PM Wave 9 sign-off → REF-20 P6 closure
```

`⫴` = 並行可開 / `→` = sequential dependency

---

## 3. Multi-Agent 工作流

### 3.1 強制工作鏈（per CLAUDE.md §八）

每個 task：

```
  PM (主會話) → @FA spec gap → @PA tech design → @E1/@E1a 實作 (parallel ≤5)
                                                       ↓
                                                  @E2 review (強制)
                                                       ↓
                                                  @E4 regression (強制)
                                                       ↓
                                                  @E5 optimization (≥3 task / phase 強制)
                                                       ↓
                                                  @QA 整合驗收
                                                       ↓
                                                  PM 確認 → commit + push
```

P0 快速通道：`@PA → @E1 → @E2 → @E4 → PM`（可省 FA / E5 / E3 / CC，但 E2 + E4 永不跳）

按需插入：`@E3`（每個 P2a/P2b/P4/P6 安全 task 必活）/ `@CC`（每個 phase exit 必查 16 原則）/ `@A3`（P1/P5/P6 frontend）/ `@MIT`（P3a/P3b ML pipeline + DB schema）/ `@QC`（P3a/P3b/P4 量化必活）/ `@BB`（Bybit API/fee 對賬）/ `@TW`（雙語注釋 + i18n key）/ `@R4`（每 wave 完成 docs 索引）

### 3.2 派 sub-agent 並行準則

- **單實例 sub-agent 操作單檔** → NOT isolation
- **並行 ≥2 sub-agent 操作不重疊檔** → NOT isolation
- **並行 ≥2 操作可能重疊檔**（如 Wave 2 P1-U2/U4/U5/U6 都改 `tab-paper.html`）→ 對重疊組加 `isolation: worktree`
- **destructive 動作**（git reset / 大量 rm / 跨檔重構）→ 加 isolation
- **純審查類** → 永不需要 isolation

### 3.3 派發前檢查（CLAUDE.md §八）

- `git fetch --prune origin` + `git branch -r | grep <topic>` 防 sibling CC 重複工作
- meta-doc 改動用 `git commit --only <file>` 隔絕 multi-session race

---

## 4. Per-Wave Task List

### Wave 1 (Sprint 1) — P0 Docs Amendment + Scaffold Design

| Task ID | 名稱 | Owner | 修改檔案 | Sprint | V3 Hard Gate |
|---|---|---|---|---|---|
| **R20-P0-T1** | REF-19 v2 + REF-20 v2 amendment draft | PA + PM | `docs/references/2026-05-XX--reality_calibrated_fast_replay_governance_v2.md` + REF-20 v2 | 0.5 | G2/G3/G5 |
| **R20-P0-T2** | `replay_runner` Rust binary scaffold 設計 | PA + E1 | `rust/openclaw_engine/src/bin/replay_runner.rs`（scaffold only）+ Cargo.toml feature `replay_isolated` | 0.5 | G7 |
| **R20-P0-T3** | `ReplayProfile::Isolated` cfg gate 設計 review | PA + E3 | `rust/openclaw_engine/src/replay/profile.rs`（spec only） | 0.5 | G7/G8 |
| **R20-P0-T4** | UX subdoc V1 operator acceptance | A3 + Operator | docs review | 0.5 | G10 |
| **R20-P0-T5** | Migration V### PM 集中分配 | PM | `sql/migrations/` ledger（reserve V0XX-V0ZZ for replay） | 0.25 | G5 |
| **R20-P0-T6** | 既有 `mlde_shadow_recommendations` INSERT 路徑 grep + 清單 | E1 + E3 | grep report inline | 0.25 | G3 prereq |
| **R20-P0-T7** | 既有 `source` distinct 分類 SELECT + ambiguous review | E1 + PM 分類 | SQL probe + classification table | 0.25 | G3 prereq |
| **R20-P0-T8** | `replay_signing_key` 部署 plan + key generation 流程 | PM + Operator | `helper_scripts/operator/generate_replay_signing_key.sh` | 0.25 | G9 |
| **R20-P0-T9** | `replay_runner` crate 邊界白名單 + E2 sign-off | PA + E3 | crate dependency graph + symbol allowlist | 0.5 | G7/G8 |

**Wave 1 Exit Criteria**：
- ✅ 9 task PM sign-off + docs commit
- ✅ V3 §3 G2/G3/G5/G7/G8/G9/G10 全部 design 階段 GREEN
- ✅ 0 runtime change（docs only + scaffold spec only）
- 🚫 任何 runtime IMPL 派發前必停（hard gate）

### Wave 2 (Sprint 2-3) — P1 Frontend IA + P2a Foundation

#### P1 部分（A3 主筆 10 task）

| Task ID | 名稱 | Owner | 修改檔案 | Sprint | V3 §12 |
|---|---|---|---|---|---|
| **R20-P1-U1** | Sub-tab shell 結構（vanilla JS show-hide）| E1a + A3 review | `tab-paper.html` + `app-paper.js` | 1 | UX §11.1 |
| **R20-P1-U2** | Session sub-tab 內容遷入 | E1a + A3 review | `tab-paper.html` L23-37 | 0.5 | #19 |
| **R20-P1-U4** | Replay sub-tab disabled placeholder | E1a + A3 review | `tab-paper.html`（new section） | 0.5 | UX §11.4 |
| **R20-P1-U5** | Compare sub-tab disabled placeholder（12 metrics layout）| E1a + A3 review | `tab-paper.html` | 0.5 | UX §11.5 |
| **R20-P1-U6** | Handoff sub-tab disabled state | E1a + A3 review | `tab-paper.html` | 0.5 | UX §11.7 / #20 |
| **R20-P1-U7** | Mode badge component（4 維 inline pill 化） | E1a + A3 + TW i18n | `common.js` + `tab-paper.html` | 1 | UX §7 / #25 |
| **R20-P1-U8** | Disabled state component（grey card + banner）| E1a + A3 review | `common.js` shared helper | 0.5 | UX §8 |
| **R20-P1-U9** | Terminology i18n（9 對照表）| TW + E1a + A3 review | `i18n_zh.js`（new） | 0.5 | UX §9 |
| **R20-P1-U10** | Accessibility audit（8 條 + axe-core） | A3 + E1a fix | `tab-paper.html` | 0.5 | UX §10 |

並行：U1 必先 land；U2/U4/U5/U6 並行（worktree isolation 同檔）；U7/U8/U9 並行（不同檔不需 isolation）；U10 收尾。

#### P2a 部分起頭（E3 主筆 6 task）

| Task ID | 名稱 | Owner | 修改檔案 | Sprint | V3 §12 |
|---|---|---|---|---|---|
| **R20-P2a-S1** | Signing key 生成 + 部署 + 90d rotation script + 180d retention | E1 + E3 + Operator | `helper_scripts/operator/generate_replay_signing_key.sh` + runbook | 0.5 | #1/#2 |
| **R20-P2a-S2** | HMAC sign+verify module（Rust + Python 雙端，4 fail-mode） | E1 + E3 | `rust/.../replay/manifest_signer.rs` + `python/.../replay/manifest_signer.py` | 1 | #2 |
| **R20-P2a-S3** | 8 routes auth scaffolding（global=1, per-actor=1） | E1 + E3 + A3 review | `replay_routes.py` | 1 | #3/#22 |

#### P2a Wave 3 收尾（後續 Wave 接力）

### Wave 3 (Sprint 3-5) — P2a 收尾 + P2b 起頭

| Task ID | 名稱 | Owner | 修改檔案 | Sprint | V3 §12 |
|---|---|---|---|---|---|
| **R20-P2a-S4** | DB role REVOKE/GRANT + `verify_replay_evidence_and_insert()` PL/pgSQL（**SECURITY INVOKER**，3-PR sequence: function+grant → producer 切換 → REVOKE） | E1 + E3 + MIT 必審 + FA review | `sql/migrations/V0XX__replay_evidence_source_guard.sql` | 1.5 | #5/#6/#7 |
| **R20-P2a-S5** | Manifest quota / TTL 30d / per-actor=20 / global storage cap / prune cron（read role 讀 + write role 刪） | E1 + E3 | `replay/quota_enforcer.py` + `helper_scripts/cron/replay_artifact_prune.py` | 0.5 | #4 |
| **R20-P2a-S6** | `evidence_source_tier` retrofit migration（3-step: ADD nullable → backfill allowlist → ALTER NOT NULL+CHECK） | E1 + E3 + MIT 必審 + PM ambiguous classify | `sql/migrations/V0YY__add_evidence_source_tier.sql` + `V0YZ__finalize.sql` + healthcheck | 1 | #5 |
| **R20-P2b-S7** | `ReplayProfile::Isolated` cfg gate 實裝（5 acceptance proofs unit-tested） | E1 + PA review + E3 review | `rust/.../replay/profile.rs` + `bin/replay_runner.rs` + `intent_processor/router.rs` | 1.5 | #8/#9/#11 |
| **R20-P2b-S8** | Forbidden path fail-closed enforcement（startup + runtime panic） | E1 + E3 | `rust/.../replay/forbidden_guard.rs` | 0.5 | #10 |
| **R20-P2b-S9** | Mac policy guard（`OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` default） | E1 + E3 | `rust/.../replay/mac_policy_guard.rs` | 0.5 | #12 |
| **R20-P2b-S10** | `nm` / `objdump` symbol grep（CI step，defense-in-depth） | E1 + E3 | `helper_scripts/ci/replay_runner_symbol_audit.sh` | 0.25 | #8 補強 |

### Wave 4 (Sprint 5-6) — P2b 收尾 + 既有 Paper 控制移除

| Task ID | 名稱 | Owner | 修改檔案 | Sprint | V3 §12 |
|---|---|---|---|---|---|
| **R20-P2b-T1** | isolated replay process wrapper land | E1 + E2 | `rust/.../bin/replay_runner.rs` | 1 | #8/#10 |
| **R20-P2b-T2** | run/status/cancel/report routes wired | E1 + E1a + E3 review | `replay_routes.py` | 1 | #3 |
| **R20-P2b-T3** | canary/diagnostic artifacts registered（Linux only） | E1 + MIT review | `replay_routes.py` + `replay.report_artifacts` | 0.5 | #7 |
| **R20-P1-U3** | 移除 manual submit/cancel button + grep `submitOrder/cancelOrder` 0 hit | E1a + A3 review + E2 grep | `tab-paper.html` + `app-paper.js` | 0.5 | #19 |

### Wave 5 (Sprint 6-8) — P3a + P3b 並行

#### P3a Global Calibration（QC 主筆 6 task）

| Task ID | 名稱 | Owner | 修改檔案 | Sprint |
|---|---|---|---|---|
| **R20-P3a-Q1** | Half-life estimation pipeline（PnL decay / Sharpe decay / default 14d 三 fallback） | QC + E1a + E2 + E4 + MIT 副審 | `learning_engine/half_life_estimator.py` | 1 |
| **R20-P3a-Q2** | OOS embargo `max(7d, 2 × half_life)` enforcement（DB CHECK + Python validator） | QC + E1 + MIT 副審 | V### migration + `replay_routes.py` | 0.5 |
| **R20-P3a-Q3** | Block bootstrap CI（Politis-Romano `arch.bootstrap` 1000 iter） | QC + E1a + E2 + E4 + MIT 副審 | `learning_engine/quantile_bootstrap.py` | 1 |
| **R20-P3a-Q4** | Shrinkage decision tree（**NumPyro hierarchical** + James-Stein + empirical Bayes router） | QC + MIT + E1a + E4 | `learning_engine/shrinkage_router.py` | 2 |
| **R20-P3a-Q5** | Fee model + maker/taker execution estimates（含 BUSDT 110017 reject loop excluded） | QC + BB 副審 + E1 + E4 | `learning_engine/fee_execution_calibrator.py` | 1 |
| **R20-P3a-Q6** | Calibration freshness ≤72h + sample power ≥200 strategy-window gate | QC + E1 + E4 | `replay_routes.py::generate_handoff_verdict` | 0.5 |

#### P3b Cell-Level（QC 主筆 3 task）

| Task ID | 名稱 | Owner | 修改檔案 | Sprint |
|---|---|---|---|---|
| **R20-P3b-Q1** | Cell calibration n≥30 gate（187 cells incremental update） | QC + MIT + E1a + E4 | `learning_engine/cell_calibrator.py` | 1 |
| **R20-P3b-Q2** | NumPyro hierarchical Bayesian implementation | QC + MIT 主審 + E1a + E4 | `learning_engine/hierarchical_bayes.py` | 2 |
| **R20-P3b-Q3** | S1 recorder dependency stub（REF-21 spec pointer） | PM + QC | `docs/execution_plan/2026-05-XX--ref21_s1_recorder_spec.md` placeholder | 0.5 |

#### Regime Controls（QC 主筆 4 task，sequential state machine）

| Task ID | 名稱 | Owner | 修改檔案 | Sprint |
|---|---|---|---|---|
| **R20-RGM-Q1** | First 500 fills warmup per cell（防 negative-edge env 永久 frozen） | QC + E1 + E2 + E4 | `learning_engine/regime_controller.py` | 1 |
| **R20-RGM-Q2** | CUSUM ±3σ break → freeze handoff（**不** freeze model） | QC + E1 + E4 | 同上 | 1 |
| **R20-RGM-Q3** | Kupiec POF n≥250 cell（不從 PBO sample 借） | QC + MIT 副審 + E1 + E4 | 同上 | 0.5 |
| **R20-RGM-Q4** | PSR(0)<0.95 across 3×250 windows → refit + PM alert | QC + E1 + E4 | 同上 | 1 |

### Wave 6 (Sprint 8-10) — P4 MLDE/Dream Advisory

| Task ID | 名稱 | Owner | 修改檔案 | Sprint | V3 §12 |
|---|---|---|---|---|---|
| **R20-P4-Q4** | DreamEngine `generate_replay_candidates()` API 整合（**不 fork**） | QC API spec + PA + E1 + MIT 副審 | DreamEngine module + verified insert function | 2 | #6 |
| **R20-P4-Q5** | MLDE rank/veto on replay candidates（advisory only） | MIT 主審 + QC 副審 + E1a + E4 | `mlde_shadow_recommender.py` extension + `replay.mlde_replay_veto_log` | 2 | #6 |
| **R20-P4-Q1** | DSR(K) > 0.95 promotion gate | QC + E1 + E4 | `replay_routes.py::generate_handoff_verdict` | 0.5 | #17 |
| **R20-P4-Q2** | PBO < 0.5 gate（K≥10, total trades ≥320） | QC + MIT 副審 + E1a + E4 | `learning_engine/pbo_gate.py`（CSCV 自寫） | 1 | #17 |
| **R20-P4-Q3** | Selection bias correction metadata（manifest CHECK） | QC + E1 | manifest schema column | 0.5 | #17 |
| **R20-P4-Q6** | `cost_edge_ratio >= 0.8` gate（與 P1-FAKE-3 env gate 耦合） | QC + E1 + E2 + E4 | `cost_edge_advisor.py` hooks | 0.5 | #24 |
| **R20-P4-S11** | `mlde_demo_applier` source filter（WHERE clause 含 registry FK + manifest_hash + expires_at + status check） | E1 + E3 + FA 必審 | `mlde_demo_applier.py` | 0.5 | #6 |
| **R20-P4-S12** | `replay_routes_use_safe_query_pattern` mirror `agents_routes` | E1 + E3 | `replay_routes.py` | 0.25 | #22 |

### Wave 7 (事件觸發) — P5 Agents Monitor 抽出

**Entry：** LG-2/3/4 frontend merged + 7d frontend stable healthcheck PASS。

| Task ID | 名稱 | Owner | 修改檔案 | Sprint | V3 §12 |
|---|---|---|---|---|---|
| **R20-P5-A1** | 抽出位置決策（**12-Tab top-level**，A3 推薦） | A3 + FA arch + E1a | `console.html` nav + `tab-agents.html`（new） | 0.5 | UX consistency |
| **R20-P5-A2** | Learning Tab 內 redirect notice（90d, top banner div, worktree isolation） | E1a + A3 + TW i18n | `tab-learning.html` | 0.5 | V3 §11 P5 KPI |
| **R20-P5-A3** | 既有 `agent-tracker.js` 行為保留（5 卡 + feed + budget） | E1a + A3 + E4 regression | `tab-agents.html` + `agent-tracker.js` | 0.5 | #21 |
| **R20-P5-A4** | 新 Tab icon（🤖 robot 或既有 agent-tracker icon set 一致） | A3 | `console.html` + `tab-agents.html` | 0.1 | UX consistency |

### Wave 8 (Sprint 10-12) — P6 Bounded Demo Handoff

| Task ID | 名稱 | Owner | 修改檔案 | Sprint | V3 §12 |
|---|---|---|---|---|---|
| **R20-P6-H1** | Typed confirmation modal（9 字段 + phrase `HANDOFF <experiment_id>` 含 sanity check） | E1a + A3 + FA security | `tab-paper.html` Handoff sub-tab + new modal | 1 | #20 |
| **R20-P6-H2** | Cooldown ≥30s + 雙 actor 政策（對齊 §四防誤等級 4） | E1a + FA + A3 | modal + backend coordination | 0.5 | §四等級 4 |
| **R20-P6-H3** | Footer recent 5 handoff list（actor + ts + result + trace_id） | E1a + A3 | Handoff sub-tab footer | 0.5 | UX 可審計 |
| **R20-P6-H4** | Idempotency key handling（DB UNIQUE + return cached） | E1a + FA + E2 | modal + backend | 0.5 | #20 |
| **R20-P6-S13** | Server-side regex 嚴驗 `^HANDOFF [a-z0-9-]{36}$` + cooldown enforcement | E1 + E3 | `replay/handoff_routes.py` | 0.5 | #20 |
| **R20-P6-S14** | DB UNIQUE constraint on `(actor, idempotency_key)` | E1 + E3 + MIT review | `sql/migrations/V0ZZ__handoff_idempotency_unique.sql` | 0.25 | #20 |
| **R20-P6-S15** | Audit row 寫 `learning.governance_audit_log`（append-only, GRANT INSERT only） | E1 + E3 + FA | `replay/handoff_routes.py` | 0.25 | DOC-08 §12 |

### Wave 9 (Sprint 12-14) — Gradient Observation + 收尾

| Task | Owner |
|---|---|
| 14d gradient observation: `replay_no_live_mutation` continuous（V3 §12 #14） | FA + E4 |
| Business KPI 7d/14d 採集 + Phase exit sign-off | FA + PM |
| `learning.governance_audit_log` 14d 0 incident 驗收 | FA + QA |
| PM Wave 9 sign-off → REF-20 P6 closure | PM |

---

## 5. Acceptance & KPI（FA 主筆）

### 5.1 V3 §12 25 條 Acceptance — SQL Probe Templates

每條 acceptance check 詳細 SQL probe / unit test / integration test template 見 FA 子報告（綜合進此節）。**摘要表**：

| 類型 | 數量 | 範例 |
|---|---|---|
| 直接 SQL probe（healthcheck.py 加 check_*） | 17 | #1 manifest_contract / #4 quota / #5 evidence_tier_completeness / #6 replay_source_guard / #7 registry_fk / #11 confidence_label / #12 mac_non_actionable / #14 no_live_mutation / #15 freshness / #16 power / #18 regime_gate / #22 safe_query / #23 baseline_provenance / #24 cost_gate |
| 部分可測（需新表/物理欄位） | 6 | #2 signature_verify（4 fail-mode unit test）/ #3 route_auth（integration）/ #8 resource_isolation（unit + nm grep）/ #9 no_lease_acquire（log grep + unit test）/ #10 fail_closed（chaos test）/ #17 cv_protocol（calibration model output assert） |
| GUI E2E（Playwright + a11y） | 4 | #19 no_order_submit（Playwright）/ #20 typed_confirm / #21 agents_monitor_read_only / #25 ml_maturity_label（雙驗 DB + UI） |
| 不可測 → V3.1 改寫 | 0 | （Round 3 audit 已 close）|

### 5.2 V3 §11 Per-Phase Business KPI 量化

依 V3 §11 + FA 補完量化閾值：

| Phase | KPI | 採集點 | 窗口 | PASS/WARN/FAIL |
|---|---|---|---|---|
| P0 | docs-only land 速度 | git log | 1 sprint | PASS=1sp / WARN=2sp / FAIL=>2sp |
| P1 | Paper session regression | `trading.fills` daily count vs prior 7d baseline | 7d post-deploy | PASS=0 / WARN=1 / FAIL=≥2 |
| P1 | Mode badges render | Playwright snapshot 8 badge slots | per commit | PASS=8/8 |
| P2a | Dangling FK | SQL probe (#7) | per migration | PASS=0 |
| P2a | NULL evidence_source_tier | SQL probe (#5) | hourly | PASS=0 |
| P2a | PG-degraded behavior | chaos drill (#22) | weekly | PASS=200+degraded / FAIL=5xx |
| P2b | Operator runs/week | `replay.experiments` count | 7d rolling | PASS=≥5 / WARN=3-4 / FAIL=<3 |
| P2b | Mean run time | `AVG(completed_at-started_at)` | 7d, n≥5 | PASS=<5min, p95<10min |
| P2b | Decision Lease leak | grep log + #9 | per run | PASS=0 |
| P3a | Calibration coverage | DISTINCT(strategy,symbol) | 7d | PASS=≥3×10 |
| P3a | CI tightness | bootstrap span vs naive | per calibration | PASS=tighter (Welch p<0.05) |
| P3b | Per-cell green coverage | green/eligible cells | 30d S0 累積 | PASS=≥40% |
| P4 | Advisory rows/week | `mlde_shadow_recommendations` w/ replay_experiment_id | 7d | PASS=≥10 |
| P4 | Unverified rows reaching applier | `mlde_applier_log` | continuous | PASS=0 |
| P5 | Agent monitor regression | UI telemetry + healthcheck | 7d | PASS=0 |
| P5 | Redirect click-through | UI telemetry ratio | 7d | PASS=≥80% |
| P6 | Demo handoff/week with typed confirm | `governance_audit_log` | 7d | PASS=≥1 |
| P6 | Live mutation count | `trading.live_orders WHERE source LIKE 'replay_%'` | continuous | PASS=0 |
| P6 | 14d 0 incident | incident DB | 14d post-deploy | PASS=0 / FAIL=≥1 major |

### 5.3 Cross-Phase Regression（每 phase exit 必跑）

| Phase N | 必跑前 phase regression |
|---|---|
| P1 | Paper session legacy regression（既有 paper engine `trading.fills` 寫入路徑）|
| P2a | P1 #19 + 既有 8 governance routes auth contract |
| P2b | P2a #1-#7, #22, #23 + 既有 path alias `OPENCLAW_SRV_ROOT`/`OPENCLAW_BASE_DIR` 不 fallback 行為 |
| P3a | P2a + P2b 全部 + FUP-2 attribution writer healthcheck + 既有 5 strategy fill DB 寫不受影響 |
| P3b | P3a 全部 + CUSUM/Kupiec/PSR healthcheck baseline 不漂移 |
| P4 | P3a + P3b 全部 + 既有 `mlde_demo_applier` 對 `real_outcome` row 接受路徑不破（baseline ±10%） |
| P5 | P4 全部 + 既有 5-Agent API schema 不變 + `/api/v1/agents/*` shape 不破 |
| P6 | P5 全部 + GovernanceHub.acquire_lease + Decision Lease retrofit 回歸 + live gate 4 項 fail-closed 仍守 |

**全 phase continuous regression**（不分 phase 一律每 commit + nightly）：
- #14 `replay_no_live_mutation`
- 16 根原則 #1 / #4 / #7 grep
- 跨平台路徑：`grep -E '(/home/ncyu|/Users/[^/]+)' <diff>` per commit

---

## 6. Hard Prerequisites（Wave 5+ 才需全部 GREEN）

| # | Prereq | 真實狀態 | Gate by |
|---|---|---|---|
| 1 | **LG5-W3-FUP-2 attribution writer deploy** | sibling CC FUP-2 in flight；`learning.exit_features.est_net_bps` 100% NULL（FA-H6） | P3a Q1/Q5/Q6 attribution_chain_ok ≥ 0.7 數據源 |
| 2 | **decision_outcomes timeframe '1' vs '1m' fix** | P1-DATA TODO 條目；100% NULL outcome_* 已知 root cause | P3a Q1/Q5 fills attribution chain |
| 3 | **demo 21d 解鎖（2026-05-07）** | passive countdown，4 day after V3 commit | P3a Q6 power gate (n>=200) 大解鎖時點 |
| 4 | **migration V### PM 集中分配** | Wave 1 R20-P0-T5 落地 | Wave 2+ 任何 SQL migration |
| 5 | **Decision Lease retrofit (AMD-2026-05-02-01)** | 路徑 A 簽核 ✅；retrofit pending；~05-15 派發 / ~05-30 deploy / ~06-06 灰度完 | P6 entry（Wave 8）|
| 6 | **Indicator leak-free sweep（V3 G6）** | ✅ **DONE 2026-05-03**（`docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md`） | P2 runner（Wave 3）已解 |
| 7 | **LG-2/3/4 frontend merged + 7d stable** | LG-2/3/4 RFC only，0% IMPL | P5 entry（Wave 7）|
| 8 | **UX subdoc V1 operator accept** | landed 2026-05-02；待 operator 正式 accept | P1 entry（Wave 2） |

---

## 7. 風險 / Unknowns（5-Agent 合併）

### 7.1 結構性風險（PA 提）

1. **`replay_runner` crate 邊界白/黑名單模糊**：V3 §6.1 措辭過糢糊，P0-T9 設計 review 必須 sign-off 明確 mod list，否則 G7/G8 fail-closed test 抓不到細粒度違規。
2. **`ReplayProfile::Isolated` 雙層 cfg gate**：建議單一 `replay_isolated` feature flag（編譯時排除 IPC/dispatch）+ runtime ProfileEnum 雙層；避免 CI matrix 爆。
3. **DB role REVOKE/GRANT 必拆 3 PR**：(1) verified insert function + GRANT EXECUTE → (2) 既有 producer 切換 → (3) REVOKE INSERT FROM PUBLIC；單 PR 直接 REVOKE 會 break live demo 寫入。
4. **Manifest TTL 30d vs key retention 180d 不一致**：P2a-S2 signer 必須明訂 key version table（同 manifest 的 signing_key_ref 必 trace 到 key archive）。
5. **Mac fixture baseline 目錄不存在**：`srv/research_notes/replay_fixtures/` Wave 1 必須先建 PM-curated sha-pin 流程，否則 Mac smoke 第一個 baseline 就 block。

### 7.2 量化方法論風險（QC 提）

6. **5 策略 negative edge calibration**：不需 augmentation（augmented 假數據會失真），靠 warmup phase + 21d unlock + Sharpe-decay fallback。
7. **bb_breakout live_demo 14d 0 fires**：half-life 必走 `default_14d` fallback；`low_confidence=true`；P3b 該策略所有 cell block from handoff。
8. **funding_arb dormant**：所有 task skip（V2 棄策略路徑 commit `a19797d`，2026-05-16 EDGE-DIAG-2 後重評）。
9. **NumPyro 學習成本**：P3a-Q4 / P3b-Q2 是新依賴；MIT 必審 trade-core install 是否已有 + 收斂時間 budget（≤60s/cell）。
10. **`cost_edge_ratio` gate vs P1-FAKE-3 env gate 耦合**：P4 啟動前必 `OPENCLAW_COST_EDGE_ADVISOR_*` env=on。

### 7.3 安全風險（E3 提）

11. **既有 `mlde_shadow_recommendations` INSERT 路徑數量未知**：P2a-S4 必先 grep（**Wave 1 R20-P0-T6 已派**），數量影響 sprint 估算。
12. **`SECURITY DEFINER` vs `INVOKER`**：選 INVOKER（V3 §4.2 #4 要求保留既有 producer 寫 real_outcome）；DEFINER 會 bypass 既有 role grant。
13. **Mac fixture-only 路徑與 symbol grep 衝突**：CI runner 平台必 Linux（aarch64-apple-darwin Mac dev 不跑 release strip 驗證）。
14. **`OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` 命名過長**：建議 P0 review，但**不 block** 啟動實作。
15. **Concurrent run cap=1 vs operator UX 不友善**：5 操作員同 run → 序列化；UX subdoc 已隱含說明（mean run time <5min KPI）。

### 7.4 UX 風險（A3 提）

16. **Cognitive overload**：右上 Live/Demo/Paper badge + 4 mode badge + 5 verdict label = 1 屏 ≥10 visual chip；緩解 = inline pill 化 + grey-tone + execution_confidence='none' 用警告色。
17. **`execution_confidence='none'` 認知欺詐**：純文字「無」極易忽略，A3 強制要求灰底 + ⚠️ icon + tooltip + 卡片右上紅邊。
18. **P5 file 鎖中度風險**：tab-learning.html 是 LG-2/3/4 主戰場；worktree isolation + redirect notice 獨立 div + freeze 7d 緩解。
19. **`HANDOFF <experiment_id>` typed phrase**：UX subdoc §6 沒指定，A3 推薦此格式（含 sanity check + 與既有 Live close pattern 一致），需 PM final approve。

### 7.5 業務邏輯風險（FA 提）

20. **`replay_ml_maturity_label`（#25）UI surface 自動驗證**：需 GUI E2E + DB metadata 雙驗（FA §2 #25 已寫 probe template）。
21. **18 Live Blocker 整合**：本 plan 與 #6 audit writer fix（agent.messages all-time 0 row）獨立但同 sprint 推進；P6-S15 audit 寫法須與 #6 fix 對齊（同 governance_audit_log table 規約）。

---

## 8. PM 整合判定

**APPROVE FOR P0 COMMIT BASELINE.**

V3 + UX subdoc V1 + 本 implementation workplan 三檔組成 REF-20 完整 P0 amendment。Wave 1 立刻可開（無外部 prereq），Wave 5+ 才需 LG5-FUP-2 + decision_outcomes fix + 21d unlock 三 prereq GREEN。

**派發排序建議**：
1. 立刻派 Wave 1 全 9 task 並行（`@PA` + `@E1` + `@E3` + `@A3` + PM 多 owner）— 全 docs/scaffold，無 runtime risk。
2. UX subdoc V1 operator 接受後，啟 Wave 2 P1 IA 與 P2a 起頭（10+3 task 高並行）。
3. Wave 3 PM 集中 V### 預留完成後啟（P2a 收尾 + P2b cfg gate）。
4. Wave 5 阻塞於 LG5-FUP-2 deploy；其餘 Wave 2-4 可繼續推進。
5. Wave 7 純事件觸發，不在 critical path。

**單一 task 修改大量檔案的 worktree isolation 強制**：P1-U1/U2/U4/U5/U6 + P5-A2 必 isolation。

**E2 必查 3 點**（PA 提）：
- P2b S7：`grep acquire_lease|ipc_server|build_exchange_pipeline` 在 `replay_runner.rs` 依賴閉包必須 0
- P2a S6：`grep INSERT INTO learning.mlde_shadow_recommendations` 全 codebase 0 直接 INSERT，全走 `verify_replay_evidence_and_insert()`
- P2a S3 + P4 S12：`replay_routes.py` PG 操作必經 `_safe_query` wrapper；E2 跑 PG kill simulation 驗 degrade

---

## 9. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **V1** | 2026-05-03 | PM（合成 PA + FA + QC + A3 + E3 五份子報告） | REF-20 V3 9-Wave 76-task implementation workplan；Multi-Agent 工作流 + 並行 DAG + acceptance binding + cross-phase regression + hard prereq + 21 條風險 |

---

## 附錄 A — 5 份子報告路徑（SoT）

| Agent | 視角 | 報告路徑 / 形式 |
|---|---|---|
| **PA** | Engineering structural breakdown | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_v3_implementation_breakdown.md`（landed） |
| **FA** | Acceptance + KPI binding | inline（已綜合進 §5；25 acceptance probe templates + per-phase KPI + cross-phase regression） |
| **QC** | Quant implementation tasks | inline（已綜合進 §4 Wave 5/6；16 task across P3a/P3b/RGM/P4） |
| **A3** | Frontend / UX implementation | inline（已綜合進 §4 Wave 2/4/7/8；18 task across P1/P5/P6） |
| **E3** | Security implementation | inline（已綜合進 §4 Wave 2/3/4/6/8；15 task + 4-phase pen test plan） |

## 附錄 B — 已 unblock 前置

- ✅ V3 P0 commit baseline land（4083a6b）
- ✅ UX subdoc V1 land（5d6e1bd）
- ✅ P0-DATA-INDICATOR-SWEEP 5/5 PASS（4083a6b）
- ✅ Round 3 audit 12 must-fix 全 closed（V3 §14）
- ✅ 7-agent 4 輪 confirm 全 APPROVE
