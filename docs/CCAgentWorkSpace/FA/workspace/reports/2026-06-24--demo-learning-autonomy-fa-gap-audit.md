# 2026-06-24 -- Demo Learning Autonomy FA Gap Audit

Bound role: `FA(default)`
Scope: functional gap audit against operator core requirement
Mode: audit / synthesis. No code patch, no runtime mutation, no PG write, no Bybit write, no crontab/config edit.

## Verdict

STATUS: DONE_WITH_CONCERNS

The operator core requirement is only partially satisfied. The system has a real demo evidence and artifact-learning substrate, plus closed live safety gates, but it has not yet proven sustainable autonomous profit generation, autonomous parameter evolution, promotion readiness, or fully reconstructable bounded-probe trade evidence.

## Sources Read

- Repo instructions and role context: `AGENTS.md`, `CLAUDE.md`, `.codex/MEMORY.md`, `README.md`, `docs/agents/context-loading.md`, `TODO.md`, `.codex/agents/FA.md`, `.claude/agents/FA.md`, `docs/CCAgentWorkSpace/FA/profile.md`, `docs/CCAgentWorkSpace/FA/memory.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`.
- PM context: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--demo-learning-autonomy-audit-context.md`.
- First-wave reports present in repo: QC, MIT, BB, and E3 2026-06-24 demo-learning autonomy reports.
- First-wave facts supplied by PM for AI-E and CC were used because no matching 2026-06-24 AI-E/CC report files were present in this repo.

## FACT

- Current runtime is not signal-silent: QC observed last-24h PG activity with `39,395` signals, `33` intents, `35` orders, `5` fills, and `56,600` decision outcomes.
- Demo is placing orders now. E3 observed last-1h demo `orders=5`, `fills=5`; BB observed same-day `flash_dip_buy` PostOnly orders/fills and a current demo state with no open positions after the latest close.
- True live remains closed: E3 observed `OPENCLAW_ALLOW_MAINNET=0`, no live authorization artifact under checked roots, and no live orders/fills in 30 days.
- The demo-learning / Cost Gate stack is installed and firing. E3 found demo evidence, sealed preflight, Cost Gate learning lane, healthcheck, and alpha discovery crons with fresh heartbeats/artifacts.
- Installed cron expected-head pins are stale: E3/MIT found some cron env pins still at `1b6173e3` while Linux source is clean at `c88deea7`, causing persisted health artifacts to report `SOURCE_NOT_READY` despite direct healthcheck returning `EVIDENCE_STACK_ACTIVE`.
- Cost Gate learning rows are accumulating in JSONL/artifacts, not dedicated PG learning tables. MIT observed `92,105` valid JSONL rows in `probe_ledger.jsonl`, including `45,938` blocked-signal outcomes, while no dedicated PG Cost Gate learning ledger/outcome/review tables were observed.
- Rust hot-path demo-learning writer is disabled: MIT observed `OPENCLAW_DEMO_LEARNING_LANE_WRITER=` empty.
- Ranked Cost Gate false-negative candidates exist but grant no authority. QC/MIT observed `16` false-negative candidates, `probe_authority_granted=false`, `order_authority_granted=false`, `global_cost_gate_lowering_recommended=false`, and `promotion_evidence=false`.
- Bounded probe outcomes do not exist yet. QC/MIT observed bounded result review status `NO_PROBE_OUTCOMES_RECORDED`.
- Profit evidence is promising but not promotion-grade: QC found sealed-horizon replay evidence for `ma_crossover|BTCUSDT|Sell@240m`, a SOXLUSDT current-fee MM lead, and ranked false-negative side-cells, but no bounded-probe result, no repeated/OOS MM confirmation, and no promotion proof.
- AI-E first-wave fact: 7d `agent.ai_invocations=0`, `learning.ai_usage_log=0`, no teacher directives, no ML parameter suggestions, and no material strategy/risk parameter evolution.
- BB found execution evidence-quality concerns: 25 same-day deep `Working` orders, unattributed SOL/ETH fills, and fill lineage gaps.
- CC first-wave fact: no hidden live/order authority, no AI direct-to-order mutation, no unauthorized risk mutation, and a separate `flash_dip_buy` real demo order path from artifact-only Cost Gate learning.

## Functional Gap Matrix

| Operator requirement | Classification | Facts / inferences | Next acceptance evidence |
|---|---|---|---|
| 1. Long-term continuous learning | PARTIAL | FACT: crons are installed/firing, PG decision/risk/reject rows accumulate, and JSONL/artifact ledgers are fresh. FACT: Rust hot-path writer is disabled and Cost Gate learning is not PG-backed. INFERENCE: current learning is continuous at artifact level, not yet a durable autonomous backend learning loop with decision impact. | Reconciled cron expected-head with persisted `EVIDENCE_STACK_ACTIVE`; monotonic ledger/outcome/review deltas across at least two natural cron cycles; duplicate/idempotency checks; explicit decision on Rust writer or PG-backed ledger; evidence that a runtime consumer uses the learning output without granting unauthorized authority. |
| 2. Sustainable autonomous evolution | PARTIAL | FACT: the system ranks false-negative candidates, preserves blocked outcomes, emits worklists, and produces sealed-horizon/MM candidate evidence. FACT: AI-E reports no AI invocations, teacher directives, ML parameter suggestions, or material parameter evolution. INFERENCE: the system can discover and queue evolution work, but does not autonomously evolve strategy/risk behavior yet. | A candidate-to-change loop where a learned hypothesis produces a bounded parameter proposal, passes QC/MIT/AI-E style validation, is applied only inside an approved envelope, and later re-evaluates with repeat/OOS/fill-backed outcome evidence. |
| 3. Profit generation evidence | NOT ACHIEVED | FACT: demo fills exist, but the attributed XRP open/close sequence closed negative after fee/slippage; other SOL/ETH fills are unattributed or risk/IPC close related. FACT: sealed replay and MM leads exist but have no bounded-probe outcomes, no repeated/OOS confirmation, and no promotion evidence. INFERENCE: current evidence supports continued exploration, not profit-generation proof. | Candidate-matched demo fills for the selected side-cell; net PnL after fees/slippage; matched blocked controls; repeated independent windows or OOS/walk-forward confirmation; bounded result and execution-realism reviews both positive. |
| 4. Autonomous trading parameter adjustment | NOT ACHIEVED | FACT: no Cost Gate lowering, no bounded probe/order authority, no ML parameter suggestions, and no material strategy parameter evolution are present. FACT: recent `flash_dip_buy` demo behavior changed via source/config/runtime path, not as proven autonomous learning output. INFERENCE: trading parameter adjustment remains human/source governed or artifact-proposed, not autonomous. | A governance-approved autonomous parameter proposal with before/after bounds, deterministic replay/shadow evidence, operator or lease authorization where required, runtime apply evidence, rollback path, and post-apply outcome review. |
| 5. Controllable risk parameter adjustment | PARTIAL | FACT: CC found no unauthorized risk mutation and no hidden live/order authority. FACT: risk rejects are accumulating and Cost Gate remains fail-closed; true live is closed. INFERENCE: controllability and safety boundaries are functioning, but autonomous risk-parameter adjustment is not yet active or demonstrated inside operator-defined bands. | Operator/QC-defined risk adjustment bands; typed authorization and Decision Lease/Rust authority path for any risk-config change; append-only audit trail; no direct learning-to-live mutation; replay/healthcheck proof that out-of-band changes fail closed. |
| 6. Explainable / reconstructable trade evidence | PARTIAL | FACT: PG rows, JSONL ledgers, risk verdicts, order/fill rows, scorecards, and review artifacts exist. FACT: BB found unattributed SOL/ETH fills and 25 deep working orders that weaken lineage and exposure reconstruction. INFERENCE: evidence is reconstructable for many decisions/rejects, but not yet clean enough for promotion-grade bounded-probe trade attribution. | Every selected order has stable strategy/candidate id, OpenClaw order id, exchange order id, intent, risk verdict, fee, slippage, fill, close, position state, matched control, and source-head artifact linkage; working-order overhang is explicitly resolved or excluded. |
| 7. Demo/live promotion readiness | BLOCKED | FACT: promotion-proof flags are false; bounded operator authorization is `defer`; sealed-horizon operator review is pending; bounded probe result review has no outcomes; true live gates are closed. INFERENCE: demo can collect evidence, but promotion is blocked by missing operator review, missing bounded authorization, missing candidate-matched execution proof, and incomplete lineage. | Operator review of ranked false-negative/sealed-horizon packet; bounded demo probe authorization for one exact contract; candidate-matched fill-backed positive evidence; execution realism positive; repeated/OOS confirmation; clean live gate review before any live promotion. |

## Blocking Gaps

| Priority | Gap | Why it blocks the operator requirement |
|---|---|---|
| P0 | No promotion-grade profit proof | Without bounded probe outcomes, repeated/OOS confirmation, and fill-backed fee/slippage lineage, the system cannot claim sustainable profit generation. |
| P0 | No autonomous parameter application loop | Candidate artifacts do not currently become approved strategy/risk parameter changes. This blocks "autonomous evolution" in the product sense. |
| P1 | Evidence lineage defects | Unattributed fills and deep working-order overhang weaken reconstructability and exposure accounting. |
| P1 | Learning materialization is artifact-only | JSONL/artifacts are useful, but disabled hot-path writer and lack of PG-backed Cost Gate learning tables limit durability and backend decision-impact claims. |
| P1 | Runtime health drift | Stale cron expected-head pins can make operator dashboards report `SOURCE_NOT_READY` even when direct source probes are clean. |
| P2 | API service hygiene | E3 found uvicorn listening while `openclaw-trading-api.service` is inactive, which is operationally messy though not the main learning/profit blocker. |

## INFERENCE

- The current system is best described as "evidence-active and safety-gated", not "autonomously profit-producing".
- The most important functional distinction is between the real demo `flash_dip_buy` order path and the artifact-only Cost Gate learning / bounded-probe path. The former has recent demo fills; the latter still has no probe authority or outcomes.
- The operator requirement cannot be signed off by observing more artifacts alone. The missing acceptance evidence is candidate-matched execution with clean lineage and post-trade review.
- The absence of unauthorized live/order/risk mutation is a positive safety result, not a fulfillment of autonomous adjustment.

## ASSUMPTION

- "Long-term continuous learning" requires durable, repeated runtime learning evidence and some controlled decision impact, not just one-off scripts or source smokes.
- "Profit generation evidence" means net-positive, fee/slippage-aware, candidate-matched, repeatable/OOS evidence under current governance.
- "Promotion readiness" requires the repo's active Demo lane criteria, not Paper archive results.
- PM-provided first-wave AI-E and CC facts are valid prior findings for this synthesis because matching 2026-06-24 AI-E/CC report files were not present in `srv`.

## Functional Verdict

Overall classification: PARTIAL, with promotion BLOCKED.

The learning and evidence collection substrate is materially better than a silent or dead system: it produces signals, rejects, candidates, artifacts, worklists, demo orders, and some fills. The core operator requirement remains unmet because autonomous parameter evolution, controllable risk adjustment bands, promotion-grade profit evidence, and clean bounded-probe trade reconstruction are not yet demonstrated.

FA AUDIT DONE: docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-24--demo-learning-autonomy-fa-gap-audit.md
