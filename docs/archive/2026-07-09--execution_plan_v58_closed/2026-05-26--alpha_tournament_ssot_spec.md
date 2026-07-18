> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）

# Alpha Tournament SSOT Spec — Sprint 2 Profit Spine

**Date**: 2026-05-26  
**Author**: PM main session  
**Status**: SPEC-FINAL / IMPL-PENDING  
**Operator directive**: 補齊 v5.8 Sprint 2 Alpha Tournament 缺口；先確定現在能確定的盈利主線，不再讓後續 agent 只看單一文檔而漏治理邊界。

> **狀態拆分（P1-16 防誤判，2026-05-29 TW）**：本 SSOT 的 `IMPL-PENDING` 指
> Alpha Tournament 主邏輯與 candidate IMPL 仍未動工，不可被 SCRIPT_INDEX 中
> 「scaffold done」字樣升級為「mostly done」。逐項真實狀態：
> - **source scaffold = done**：`alpha_tournament/` package + `attribution_daily.py`
>   + `tournament_orchestrator.py`（Sprint 2 stub return 0）+ `14d_bucket_split.sql`
>   已落地（見 `helper_scripts/SCRIPT_INDEX.md` 2026-05-25 區塊）。
> - **active = false**：tournament 尚未啟動評選；`tournament_orchestrator.py` 仍是
>   stub，未產生任何 candidate verdict。
> - **Stage 0R evidence = pending**：尚無任一 candidate 通過 §5 evidence gates 取得
>   Stage 0R replay preflight 證據。
> - **M11 Stage-A smoke cron = installed**：runtime crontab `0 4 * * *
>   m11_replay_runner_daily_cron.sh` 已安裝，僅作 `[48]` liveness heartbeat。
> - **M11 Stage-B divergence output = pending**：`replay.experiments` 已積但
>   `completed=0` / `replay_divergence_log=0`，divergence 物化未完成。
>
> **硬邊界**：M11 Stage-A smoke 只證明 cron 還活著（liveness-only），**不是**
> promotion / divergence evidence。任何 Stage 0R 或 Stage 1 升級不得引用 Stage-A
> smoke 心跳作為證據；scaffold 落地 ≠ 評選結果 ≠ replay divergence 結論。

---

## 0. Read This First

This file is the **single source of truth** for Sprint 2 Alpha Tournament. It does not supersede v5.8; it fills the missing Alpha Tournament block referenced there.

Required read order for any PA / QC / MIT / E1 / E2 / E4 / QA agent touching Sprint 2 alpha work:

1. `CLAUDE.md` §二 / §四 — root principles + live hard boundaries.
2. `TODO.md` — current P0/P1 queue, runtime evidence, and latest blockers.
3. `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §2 M4/M10/M11 + §4 Sprint 2 row.
4. `docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md`.
5. **This file** — Alpha Tournament scope, scoring, stage rules, and handoff contract.
6. Relevant ADRs: ADR-0024, ADR-0034, ADR-0036, ADR-0037, ADR-0038, ADR-0040, ADR-0045.

If any source conflicts, use this priority:

`CLAUDE hard boundary > accepted ADR/AMD > TODO latest runtime state > this Alpha SSOT > older execution plan prose`.

---

## 1. Purpose

Alpha Tournament exists to solve `P0-EDGE-1`: existing textbook strategies are structurally alpha-deficient and cannot be the only route to true live.

The tournament is not a dashboard feature, not a generic research framework, and not a proof that alpha exists. It is a controlled evidence machine:

- compare candidate alpha sources under one scoring contract;
- reject fee-dragged or non-replayable ideas quickly;
- promote only candidates with demo evidence into Stage 0 / Stage 0R planning;
- feed M4/M10/M11/M7 with clean attribution data.

No candidate in this tournament receives trading authority from this spec. Trading authority still requires the existing Stage ladder, Decision Lease, Guardian, and five live gates.

---

## 2. Locked Decisions

These are now fixed for Sprint 2 unless a new AMD/ADR explicitly amends them.

| Decision | Locked value | Reason |
|---|---|---|
| Sprint 2 focus | PnL-led Alpha Tournament + M4 stage 1 + M10 Tier A + M8 read-only | v5.8 §4 already names this as business Sprint 2; this file makes the alpha lane executable. |
| Tournament authority | Evidence and recommendation only | Learning must not rewrite live state directly. |
| Output state | `DRAFT` hypothesis / candidate verdict / Stage 0 dispatch recommendation | No auto promotion and no auto trial activation. |
| Initial IMPL count | 1-2 candidates max after spec review | Avoid spreading engineering across unproven strategies. |
| Baseline role | 5 textbook strategies are baseline/control only | TODO and QC history show current slices remain negative; no new engineering goes into textbook revival unless tournament evidence contradicts this. |
| Paper lane | Not promotion evidence | Per `CLAUDE.md`; paper can be diagnostic fixture only. |
| Live gate | Unchanged five-gate boundary | Alpha evidence does not unlock true live alone. |

---

## 3. Current Candidate Pool

The Sprint 2 candidate pool is intentionally small. Additions require PA + QC sign-off and must update this file.

| ID | Candidate | Sprint 2 role | Current status | Main risk |
|---|---|---|---|---|
| A0 | C10 funding harvest | Baseline / carry source | Demo observation in progress; C10 closure chain is separate from Alpha Tournament | Thin APR; does not solve high-return target alone. |
| A1 | Funding short-only v2 | Primary Sprint 2 candidate | IMPL-ready after PA/MIT spec | Funding threshold may be rare; fee + borrow/carry drag can erase edge. |
| A2 | Liquidation cascade fade | Primary Sprint 2 candidate | IMPL-ready after PA/MIT spec | Adverse selection; event definition leakage; maker fill may be unavailable at best moments. |
| A3 | BTC/ETH pairs | DRAFT / stats-first | Needs cointegration + half-life precheck before IMPL | Correlation breakdown; fee drag on two-leg turnover. |
| A4 | C13 defined-risk options / VRP | Sprint 2-6 candidate | Data/liquidity verification first | Options liquidity and tail risk; not Sprint 2 quick IMPL unless data gate passes. |
| A5 | Token unlock short | Sprint 3+ candidate | Depends on external unlock feed | Paid/vendor data quality; event sample sparsity. |
| B0 | 5 textbook strategies | Control group only | Keep collecting baseline evidence | Do not spend engineering on parameter rescue without tournament-grade evidence. |

Sprint 2 default implementation recommendation:

1. Implement A1 and A2 only after PA/MIT final candidate specs.
2. Keep A3 as statistical DRAFT unless cointegration and fee-adjusted replay pass.
3. Keep A4/A5 out of Sprint 2 IMPL unless their data gates finish early with clear evidence.

---

## 4. Scoring Contract

Every candidate must produce the same scorecard. A candidate without a complete scorecard is not eligible for Stage 0 recommendation.

Required fields:

| Field | Requirement |
|---|---|
| `candidate_id` | Stable ID from §3. |
| `alpha_thesis` | One paragraph, falsifiable. |
| `data_window` | Exact start/end, source tables, and row counts. |
| `engine_mode` | Demo / LiveDemo only for promotion evidence; paper diagnostic must be separated. |
| `n_events` / `n_fills` | Count and confidence interval. |
| `gross_bps` | Before fee/slippage. |
| `fee_bps` | Bybit VIP0 fee model or actual fee source. |
| `slippage_bps` | Measured or conservative assumption; assumption must be flagged. |
| `net_bps` | Gross minus fee/slippage. |
| `max_dd` | Candidate-level and portfolio impact. |
| `turnover` | Daily and weekly turnover; fee sensitivity included. |
| `capacity_estimate` | Capital where edge likely decays. |
| `implementation_hours` | PA/E1 estimate including test/review. |
| `replay_coverage` | Whether M11 / Stage 0R can replay the candidate. |
| `failure_mode` | Why this edge disappears. |
| `verdict` | `reject`, `draft_only`, `stage0_ready`, or `observe_more`. |

Primary ranking metric:

`risk_adjusted_net_edge = net_bps_per_trade * expected_trades_per_month - expected_drawdown_penalty - implementation_tax`

This is not a mathematical absolute. It is the standardized tie-breaker so the system does not prefer elegant but low-capacity ideas over fee-adjusted profitable candidates.

---

## 5. Minimum Evidence Gates

These gates apply before a candidate can be recommended for Stage 0.

| Gate | Pass condition | Fail behavior |
|---|---|---|
| Data gate | Source rows available, timestamp ordered, no partial-bar leakage | `reject` or `draft_only`. |
| Fee gate | Net edge stays positive after Bybit VIP0 fee + conservative slippage | `reject`. |
| Sample gate | `n >= 30` events/fills for a preliminary verdict, unless explicitly marked event-rate constrained | `observe_more`. |
| Replay gate | Candidate can be replayed or has a written reason replay is not applicable | no Stage 0 recommendation. |
| Governance gate | Candidate path uses Decision Lease + Guardian; no direct live mutation | hard reject. |
| Portfolio gate | Candidate does not concentrate all P0-EDGE-1 logic in one correlated failure mode | lower ranking or reject. |

Statistical notes:

- Any rolling feature must be leak-free (`shift(1)` or SQL equivalent).
- Multiple hypothesis testing must use Bonferroni or FDR correction.
- Stage 0R cannot be replaced by M4/M10 statistics.
- Weak evidence is not a live blocker by itself, but it is a no-capital-scale verdict.

---

## 6. Stage Output Rules

Alpha Tournament has four output lanes:

| Output | Meaning | Allowed next step |
|---|---|---|
| `reject` | Negative or unusable after fee/replay/governance checks | Archive with reason; no retry unless new data changes the premise. |
| `draft_only` | Plausible but incomplete | Write/update `learning.hypotheses` DRAFT; no trading activation. |
| `observe_more` | Edge may exist but sample is too small | Continue data collection with healthcheck/review date. |
| `stage0_ready` | Enough evidence for controlled Stage 0 planning | PA produces Stage 0 dispatch; still no automatic trading. |

`stage0_ready` is not `Stage 0R`, not Demo, not LiveDemo, and not true live. It only authorizes a follow-up design/implementation chain.

---

## 7. Minimal Preconditions

Alpha Tournament spec work can proceed immediately. Candidate IMPL must respect the following minimum preconditions:

| Layer | Must be true before | Preconditions |
|---|---|---|
| L0 | Spec/design work | None beyond reading the required docs in §0. |
| L1 | M4 DRAFT writer | `learning.hypotheses` table present; writer proves DRAFT-only behavior; no auto promotion. |
| L1 | Candidate statistics | Relevant source tables fresh enough for the candidate; stale sources produce `observe_more`. |
| L1 | C10 baseline use | Current 7d observation window completes or interim evidence is clearly marked partial. |
| L2 | Candidate IMPL | PA/MIT candidate spec + E1 implementation + E2 review + E4 regression plan. |
| L2 | Stage 0 recommendation | Scorecard complete; fee gate pass; governance gate pass; replay plan written. |
| L3 | Stage 0R / Demo / LiveDemo | Existing Stage ladder and P0 gates; this spec does not change them. |

Do not wait for full M8/M9/M12/M13 implementation before Alpha Tournament. Those are enhancers, not prerequisites for the initial alpha evidence machine.

---

## 8. Engineering Chain

Default chain for each candidate:

`PM -> PA -> QC -> MIT -> E1 -> E2 -> E4 -> QA -> PM`

Role responsibilities:

| Role | Responsibility |
|---|---|
| PA | Candidate scope, implementation boundary, Stage output mapping. |
| QC | Alpha plausibility, fee-adjusted edge, false-positive risk. |
| MIT | Data windows, leakage checks, statistical test design. |
| E1 | Implementation only after PA/QC/MIT scope is fixed. |
| E2 | Adversarial review: leakage, bypass, hidden retries, overfitting. |
| E4 | Regression and replay/test execution. |
| QA | Acceptance evidence and handoff verdict. |
| PM | Integrates verdict into TODO / Sprint plan / operator decision. |

Shortening the chain is allowed only for pure documentation edits. Strategy implementation must not skip E2/E4.

---

## 9. Cross-Document Pointers

Future agents must not use this file in isolation.

| Document | Required update / dependency |
|---|---|
| `TODO.md` | Active status and blockers for Sprint 2 Alpha Tournament. |
| `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` | Sprint 2 row points to this SSOT. |
| `docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md` | Stream A no longer remains implicit; it is governed by this SSOT. |
| `docs/README.md` | Document index includes this SSOT. |
| `docs/governance_dev/SPECIFICATION_REGISTER.md` | Register includes ARCH-05 Alpha Tournament SSOT. |
| `docs/adr/0024-cowork-subscription-operator-assistant.md` | M4/Cowork remains DRAFT-only. |
| `docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md` | Replay/counterfactual validation source. |
| `docs/adr/0045-m4-hypothesis-discovery-governance.md` | DRAFT writeback governance. |

---

## 10. Acceptance Criteria For This Spec

This spec is complete when:

1. v5.8 points to this file from its Sprint 2 row or nearby note.
2. Sprint 2 dispatch packet points to this file and removes the ambiguity that Alpha Tournament has no SSOT.
3. TODO points to this file from the active Sprint 2 status.
4. docs README and SPECIFICATION_REGISTER include this file.
5. No code or runtime state is changed by this documentation patch.

---

## 11. Explicit Non-Goals

- Do not implement a new strategy in this patch.
- Do not enable Paper as a promotion lane.
- Do not relax P0-EDGE-1, P0-LG-3, P0-OPS-1..4, or the five true-live gates.
- Do not let M4/M10/M11 auto-promote a candidate.
- Do not expand candidate pool beyond §3 without PA + QC sign-off.
- Do not prioritize GUI/governance cosmetics over candidate fee-adjusted edge.

---

**END Alpha Tournament SSOT Spec**
