# PA Report — Sprint N+0 Sign-off Invariant 17 Closure 4 Governance Docs Land

Date: 2026-05-10
Owner: PA
Status: ✅ Drafted + Local commit `75b6e5f2` LAND on main; ⚠️ push origin main blocked by permission rule (operator manual push needed)
Trigger: Sprint N+0 sign-off invariant 17 closure-blocking action — 4 governance docs (ADR + ARCH + 2 AMD) 起草

---

## 1. 任務範圍

Operator 拍板 Sprint N+0 sign-off invariant 17 closure-blocking action：起草
4 governance docs：

| # | Doc | 原任務指定 | Actual land |
|---|---|---|---|
| 1 | ADR | ADR-0021 strategist cap 30%→50% wide_parameter_adjustment skill | **ADR-0022**（編號衝突 — ADR-0021 已被 alpha-source-architecture-upgrade 占用 2026-05-09） |
| 2 | ARCH | ARCH-04 graduated canary 5-stage architecture | **ARCH-04**（新建在 architecture/） |
| 3 | AMD | AMD-2026-05-09-03 配套 invariant 5 wording amendment | **AMD-2026-05-10-03**（AMD-03 編號已 = graduated-canary-default land 2026-05-09；新編號 2026-05-10-series） |
| 4 | AMD | AMD-2026-05-09-03 配套 TOML drift fix SOP | **AMD-2026-05-10-04**（同上 series） |

---

## 2. Land Artifacts

### 2.1 4 docs（local commit `75b6e5f2`）

| File | Path |
|---|---|
| ADR-0022 | `/Users/ncyu/Projects/TradeBot/srv/docs/adr/0022-strategist-cap-wide-parameter-adjustment-skill.md` |
| ARCH-04 | `/Users/ncyu/Projects/TradeBot/srv/docs/architecture/2026-05-10--ARCH-04-graduated-canary-5-stage.md` |
| AMD-03 | `/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-10--AMD-2026-05-10-03-invariant-5-wording-n0-scope.md` |
| AMD-04 | `/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-10--AMD-2026-05-10-04-toml-drift-fix-sop.md` |

### 2.2 Index 修正（同 commit）

`/Users/ncyu/Projects/TradeBot/srv/docs/README.md` line 169-173 替換：
- 修 phantom AMD-03/04 entries（標 `strategist_wide_adjustment_skill.md` 為 AMD-03、`demo_promotion_evidence_push.md` 為 AMD-04，但實際檔不存在 — 該 path 標籤錯）
- 加 ADR-0022 + ARCH-04 + AMD-03/04 4 entry

### 2.3 PA memory 追加

`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/memory.md` head 加新章節「Sprint N+0 sign-off invariant 17 closure 4 governance docs land（2026-05-10）」（含 4 docs 核心設計決策 + commit status + 未動的檔註明 + E2 重點審查 3 點 + PM 接手後續動作）。

---

## 3. 核心設計決策

### 3.1 ADR-0022 — Strategist Cap Wide Parameter Adjustment Skill (Freedom-not-Gate)

- **核心**：30%→50% 是 Strategist LLM payload skill 升級，不是風控 ceiling 放鬆
- **雙 zone 教學**：normal_range_pct (0-30%) + wide_skill_range_pct (30-50%)
- **wide skill invocation 必填**：`wide_skill_reason: WideSkillReason` enum (RegimeShift / LiquidationCascade / CrossAssetDivergence / Other)
- **SM-05 invariants 完全保留**：IPC failure / cache miss / schema fail / provider exception → fail-closed 對 wide skill 同 normal 提案一視同仁
- **50% 偏離監測 ledger**：`agent.strategist_wide_skill_invocations` PG schema + index；monthly threshold N=10/month → trigger Guardian veto review；count > 20/month → 強制 Layer2 manual escalation per ADR-0020
- **healthcheck 配套**：`[59] strategist_wide_skill_drift_detection`（W-AUDIT-7 IMPL 期間 land）
- **§二 16 原則合規**：11 條全綠（1/2/3/4/5/6/7/8/9/11/13）

### 3.2 ARCH-04 — Graduated Canary 5-Stage Architecture

- **5-stage 狀態機**：Stage 0 shadow / 1 paper × 7d / 2 demo single × 14d / 3 demo full × 21d / 4 LIVE_PENDING；每 stage 條件 fail-closed（auto-promote AND + auto-rollback OR）
- **Component**：Rust `ExecutorCanaryConfig` (ArcSwap hot-reload) + PG `governance.canary_stage_log` + `canary_stage_metric_registry` + Python `shadow_mode_provider` stage-aware + `LeaseScope::CanaryStagePromotion` + healthcheck `[58]` + GUI surface
- **Boundary 4 範圍仍硬不變**：DOC-08 §12 9 條安全不變量 / SM-04 ladder / Live boundary 5-gate / §二 16 原則的硬不變式（原則 1/2/4/5/7/9/13/14）
- **Auto-rollback 永遠回 Stage 0**（不是 stage-1）— 與 §二 原則 6 「失敗默認收縮」一致
- **W-AUDIT-9 IMPL 7 sub-task 對應**：T1 Rust schema / T2 V### migration / T3 stage-aware provider / T4 healthcheck `[58]` / T5 GUI / T6 LeaseScope / T7 regression

### 3.3 AMD-2026-05-10-03 — invariant 5 Wording N+0 Scope (Option A)

- **MIT push back 採納**：FA spec 的「feature_baselines first → ... → 3 advisor 並行」對應 N+1+ scope，不是 N+0 actual IMPL
- **invariant 5 wording amend**（commit `0b9a03ef` 已 land）：對齊 N+0 actual M1→M2→M3 串行 IMPL（decision_features producer + V082 + entry_context_id INSERT + V083 NOT VALID + V084 + 6 Rust producer file）
- **invariant 5b N+1 預告**：W-AUDIT-8f Hypothesis Pipeline IMPL 同 wave 串行 land 6 表 INSERT path（feature_baselines / drift_events / scorer_predictions / 3 advisor）

### 3.4 AMD-2026-05-10-04 — TOML Drift Gap 治理 SOP (Option B-later)

- **CC condition 3 採納**：`risk_config_demo.toml:244 shadow_mode = true` 與 AMD-03 §2.3「demo 預設 canary_stage = 1」spec drift
- **Operator 拍板 B-later**：Sprint N+1 W3 cohort 拍板階段做（不是現在升 Stage 1）；Sprint N+0 sign-off 守 Stage 0 baseline
- **Atomic patch SOP**（per §2.2）：cohort 拍板後同 commit 4 欄位（shadow_mode = false / canary_stage = 1 / canary_cohort / stage_entered_at_ms / observation_period_ms）
- **W-AUDIT-9 T7 regression 6 test**：Stage 0→1 promote / 觀察期 active / Stage 1→2 auto-promote / lease IPC failure rollback / SM-04 L3 escalate rollback / cohort 外 strategy × symbol 仍 shadow
- **W-AUDIT-3b runtime smoke pre-launch**：ssh trade-core run + engine restart + log evidence 證 `[55] chains_with_lease > 0`
- **Supersedes 文字修訂**：AMD-2026-05-09-03 §2.3 「demo 預設 canary_stage = 1」改為「demo TOML 預設 Stage 0 直到 cohort 拍板；Sprint N+1 cohort 啟動時同 commit atomic patch 升至 Stage 1」

---

## 4. 副作用識別

### 4.1 對既有 governance docs 的影響

| 既有 doc | 是否觸碰 | 處置 |
|---|---|---|
| AMD-2026-05-09-03 graduated-canary-default | §2.3 文字 supersedes（per AMD-04 §3.1） | 保留原檔，AMD-04 自身 supersedes 註明 |
| TODO v19 §5.3 invariant 17 | wording 仍 reference ADR-0021 | **不動**（per dispatch 守則）；建議 PM commit Sprint N+0 sign-off 時順手補正為 ADR-0022 |
| TODO v19 §5.1 invariant 5 | 已 amend by `0b9a03ef` 2026-05-10 11:04 UTC | AMD-03 正式記錄該 amendment + 補 5b N+1 預告 |
| TODO v19 §5.1 invariant 4 | wording 不變；但「cohort active 起算」改為 N+1 W3 | AMD-04 §3.2 explicit 補註 |
| docs/README.md index | 修 line 169-173 phantom + 加 4 新 entry | 同 commit 修正 |
| CLAUDE.md §三 / §四 / §五 | 不動 | 4 docs 互引足夠；W-AUDIT-9 IMPL land 後同 commit 加 healthcheck `[58]` 時順手 cross-ref ARCH-04 |

### 4.2 對 Sprint N+0 dispatch 影響

- **invariant 17 closure 解除 Sprint N+0 sign-off blocker**（per TODO v19 §5.3）
- **不影響** W-AUDIT-9 T1-T7 IMPL 派發（per TODO v19 §6 Day-by-Day dispatch）
- **不影響** W-AUDIT-8a Phase A trait 升級（per TODO v19 §6 Day 5-7 dispatch）
- **不影響** W-AUDIT-4b M1/M2/M3 串行 IMPL（已 land per `0b9a03ef`）

### 4.3 對 Sprint N+1 + 後續 dispatch 影響

- **Sprint N+1 W3** 必新增 step：PA cohort 拍板 + QC review + PM operator approval + atomic patch commit + W-AUDIT-9 T7 regression + W-AUDIT-3b runtime smoke pre-launch
- **W-AUDIT-7** IMPL 期間必加 ADR-0022 配套：V### migration `agent.strategist_wide_skill_invocations` + healthcheck `[59]` + GUI 面板
- **Sprint N+5 W-AUDIT-8f IMPL** 完整 land 後新增 invariant 5b 至 TODO §5.1

---

## 5. Commit + Push Status

### 5.1 Local commit ✅ LAND

```
75b6e5f2 pa-gov: ADR-0022 + ARCH-04 + AMD-03/04 + README index land [skip ci]
```

5 files / 1189 insertions / 3 deletions：
- docs/adr/0022-strategist-cap-wide-parameter-adjustment-skill.md (created)
- docs/architecture/2026-05-10--ARCH-04-graduated-canary-5-stage.md (created)
- docs/governance_dev/amendments/2026-05-10--AMD-2026-05-10-03-invariant-5-wording-n0-scope.md (created)
- docs/governance_dev/amendments/2026-05-10--AMD-2026-05-10-04-toml-drift-fix-sop.md (created)
- docs/README.md (line 169-173 修正 + 加 4 entry)

### 5.2 Push origin main ⚠️ BLOCKED

`git push origin main` 被 permission rule 阻擋（main = default branch protected）。
**Operator 手動執行**：

```bash
cd /Users/ncyu/Projects/TradeBot/srv && git push origin main
```

或 operator 拍板開 feature branch + PR：

```bash
cd /Users/ncyu/Projects/TradeBot/srv && \
git checkout -b pa-gov-invariant17-closure 75b6e5f2 && \
git push origin pa-gov-invariant17-closure && \
gh pr create --title "PA gov: ADR-0022 + ARCH-04 + AMD-03/04 + README index" \
  --body "Sprint N+0 sign-off invariant 17 closure-blocking action 4 governance docs"
```

### 5.3 race-safe 守則

- 用 `git commit --only` 隔絕 BB WIP（per `feedback_git_commit_only_for_metadoc.md`）
- 4 docs untracked 用 `git add` 個別檔（不用 `git add -A`）
- 不動 TODO.md / CLAUDE.md / 隔壁 BB worklog
- BB / E1 untracked 檔仍在 worktree（status `M`/`??`），不被本 commit 吸收

---

## 6. PM 接手後續動作

| # | 動作 | Owner | 時點 |
|---|---|---|---|
| 1 | Operator 手動 push origin main（或拍板開 PR）| operator | Sprint N+0 W2 sign-off 前 |
| 2 | TODO §5.3 invariant 17 wording 補正：「ADR-0021」→「ADR-0022」（或加 cross-ref note）| PM | Sprint N+0 sign-off 同 commit |
| 3 | Sprint N+0 sign-off report 明文記入 invariant 17 closed by ADR-0022 + ARCH-04 + AMD-03/04 4 docs land | PM | Sprint N+0 sign-off 時 |
| 4 | 通知 FA invariant 5b N+1 預告（per AMD-03 §2.2）| PM | Sprint N+0 sign-off 同 batch |
| 5 | 通知 PA Sprint N+1 W3 cohort 拍板 dispatch（per AMD-04 §2.1）| PM | Sprint N+1 dispatch 起點 |

---

## 7. E2 重點審查 3 點（PA 標）

1. **ADR-0022 §配套機制 V### migration spec**：`agent.strategist_wide_skill_invocations` schema 是 W-AUDIT-7 IMPL land 時拍板，現在只是 spec；E2 不應 reject「未 IMPL」（與 ADR-0021 同 spec-only 模式）

2. **ARCH-04 §3.3 `shadow_mode_provider` exception path fail-closed Stage 0 invariant**（不是 Stage 1）— 是雞蛋死循環防線（per AMD-2026-05-09-03 §1.2 FA push back），break 即整 W-A demo fail-closed default 雞蛋死循環復活；W-AUDIT-9 T3 IMPL 必逐字實踐 + unit test 必涵蓋此 fail-closed path

3. **AMD-04 §2.4 W-AUDIT-3b runtime smoke pre-launch mandatory**：Stage 1 cohort launch 必先 ssh trade-core run `pytest -k test_executor_fail_closed` + engine restart with `--rebuild --keep-auth` + log evidence 證 `[55] chains_with_lease > 0`；不可只跑 Mac mock（per `feedback_v_migration_pg_dry_run.md` 教訓 — Mac mock + static review 不夠）

---

## 8. Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| PA | 本文件作者 | 2026-05-10 | ✅ 4 docs Drafted + local commit `75b6e5f2` LAND |
| Operator | 拍板 4 docs scope（ADR + ARCH + 2 AMD）| 2026-05-09 / 2026-05-10 | ✅ Accepted scope |
| PM | TBD（commit + push 後）| 2026-05-10 | 🟡 Pending sign-off post-push |

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--governance_4docs_invariant17_closure.md

---

*PA Workspace Report — Sprint N+0 Sign-off Invariant 17 Closure 4 Governance Docs Land*
