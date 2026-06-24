# 2026-06-24 -- Demo Learning Autonomy PA Architecture Verdict And Next Plan

Bound role: `PA(default)`
Scope owner: architecture / next-work sequencing for demo-learning autonomy closure
Task shape: synthesis / architecture audit, no implementation
Boundary: read-only PM audit synthesis. No PG write, no Linux cargo, no restart/deploy, no crontab/config edit, no Bybit write, no commit/push. The only write is this requested report artifact.

## Verdict

STATUS: DONE_WITH_CONCERNS

Architecture verdict: the system is now **evidence-active and safety-gated**, not silent, but it is **not yet mature enough to claim sustainable autonomous profit generation or autonomous parameter evolution**. The right next move is not promotion or global Cost Gate relaxation; it is a narrow sequence that first cleans exchange/evidence risk, then closes the artifact-to-decision learning loop, then asks the operator for one exact bounded probe contract.

Maturity against the core requirement:

| Requirement axis | Current maturity | PA verdict |
|---|---:|---|
| Demo order/signal activity | Active | Demo has fresh signals, orders, and fills; the old blanket "Demo is not ordering" diagnosis is superseded. |
| Runtime safety / live separation | Strong but needs hygiene | True live remains closed; no hidden AI/order/risk mutation found. Demo pilot order path is separate from bounded Cost Gate authority. |
| Continuous learning | Partial | Cost Gate learning crons and JSONL/artifact materialization are active; Rust hot-path writer is disabled and no PG-backed Cost Gate learning ledger was observed. |
| Autonomous evolution | Not achieved | No material autonomous strategy/risk parameter adjustment, no AI/model parameter suggestion ledger activity, and no learned candidate-to-approved-change loop. |
| Profit proof | Not achieved | Candidates are promising, but no candidate-matched bounded probe outcomes, no repeat/OOS confirmation, and latest attributed fill sequence is not promotion-grade. |
| Reconstructability | Partial | Decision/risk/order/fill evidence exists, but unattributed fills and deep working-order overhang block promotion-grade lineage. |
| Promotion readiness | Blocked | Operator review, bounded authorization, clean execution evidence, and post-probe review are all missing. |

## FACT

- FA/QC/MIT/E3/BB agree that current Demo runtime is not order/fill silent: recent PG windows show fresh signals, intents, orders, fills, and decision/risk rows.
- E3 observed Linux source clean at `c88deea7`, demo engine alive, true live closed with `OPENCLAW_ALLOW_MAINNET=0`, no live auth artifact under checked roots, and no true-live orders/fills in 30 days.
- Demo-learning / Cost Gate cron stack is installed and firing; JSONL/artifact evidence is accumulating from runtime rows.
- Installed cron expected-head pins are stale (`1b6173e3` vs current `c88deea7`), causing persisted health artifacts to report misleading `SOURCE_NOT_READY` while direct healthcheck reports active source readiness.
- Rust hot-path demo-learning writer is disabled (`OPENCLAW_DEMO_LEARNING_LANE_WRITER=` empty); current Cost Gate learning is artifact/JSONL-level, not PG-backed autonomous decision-impact learning.
- Cost Gate false-negative candidates exist, but all authority/proof flags remain false: no global Cost Gate lowering, no probe authority, no order authority, no promotion evidence.
- Bounded probe result review currently has no probe outcomes.
- BB found exchange-facing evidence issues: same-day deep `Working` order overhang and unattributed SOL/ETH fills.
- PM-supplied AI-E/CC facts: no hidden live/order authority, no direct AI-to-order mutation, no unauthorized risk mutation; 7d AI/model call and parameter-suggestion ledgers are zero; strategist rows are mostly metadata/no-op.

## INFERENCE

- The architecture has crossed from "inert evidence plumbing" to "active evidence and candidate generation," but not to "autonomous trading improvement." The missing layer is a controlled candidate-to-parameter/probe application loop with clean outcomes.
- There are two different Demo truths that must not be conflated:
  - ordinary Demo `flash_dip_buy` pilot is active and placing orders/fills through source/config/runtime paths;
  - bounded Cost Gate learning/probe authority remains closed and artifact-only.
- The highest-risk next failure mode is not absence of signals. It is prematurely treating artifact candidates or flash-dip fills as proof while lineage, overhang, repeat/OOS, and bounded authorization are incomplete.
- Source/runtime hygiene issues are now blocking decision quality more than code availability: stale expected-head pins, unattributed fills, and working-order overhang can make correct operator decisions hard.

## ASSUMPTION

- "Sustainable autonomous learning/evolution" requires at least one governed loop where runtime evidence creates a bounded proposal, the proposal is accepted inside explicit authority/bands, and outcome review closes the loop.
- "Profit proof" means candidate-matched, fill-backed, fee/slippage-aware, matched-control, repeat/OOS-confirmed evidence under current Demo governance.
- Promotion evidence must be Demo/current-runtime evidence, not Paper archive or source-smoke evidence.
- Existing first-wave AI-E and CC facts are accepted as PM-supplied audit inputs because no matching 2026-06-24 AI-E/CC report files were available in this repo snapshot.

## P0 Next Work

### Safety / Compliance

| Work | Role chain | Authorization | Acceptance |
|---|---|---|---|
| Adjudicate deep working-order overhang before any bounded probe authorization. | `PM -> E3(explorer) -> BB(default) -> CC(default) -> PM` | Operator authorization required for any Bybit cancel/modify/write. Read-only inventory needs no operator write auth. | Current exchange/DB working-order state is reconciled; stale/deep orders are either cancelled by an approved path or explicitly quarantined/excluded from proof; exposure cannot exceed intended demo caps if a crash touches old orders. |
| Preserve live hard-boundary posture while clarifying Demo authority split. | `PM -> CC(default) -> PA(default) -> E3(explorer) -> PM` | Source-only for docs/tests/dashboards; operator auth required for runtime env or service changes. | Reports and health surfaces distinguish `flash_dip_buy` Demo pilot activity from bounded Cost Gate probe authority; no artifact can be read as live/mainnet/probe authorization. |

### Evidence Quality

| Work | Role chain | Authorization | Acceptance |
|---|---|---|---|
| Root-cause and future-proof unattributed fill lineage. | `PM -> BB(default) -> PA(default) -> E1(worker) -> E2(explorer) -> E4(worker) -> QA(worker) -> PM` | Source-only implementation can improve future attribution and proof exclusion; PG backfill of existing rows requires operator/PM data-write authorization. | Every future proof-eligible fill links candidate id, OpenClaw order id, exchange order id, intent, risk verdict, fees/slippage, and close state; unattributed fills are automatically excluded from promotion/probe proof. |

### Profit / Probe Proof

| Work | Role chain | Authorization | Acceptance |
|---|---|---|---|
| Select exactly one bounded-probe candidate packet for operator review after safety/evidence blockers are cleared. | `PM -> QC(default) -> MIT(default) -> BB(default) -> PA(default) -> CC(default) -> PM -> Operator` | Operator authorization required for bounded probe/order authority. | One contract names side-cell/strategy/symbol/side/horizon, max notional, max concurrency, time window, cancel rules, matched controls, stop conditions, and typed confirm. No global Cost Gate change. |

## P1 Next Work

### Runtime / Evidence Hygiene

| Work | Role chain | Authorization | Acceptance |
|---|---|---|---|
| Reconcile cron expected-head pins. | `PM -> E3(explorer) -> PM` | Crontab/runtime config edit requires operator authorization. Source-only installer/checker patch does not. | Persisted healthcheck latest reports `EVIDENCE_STACK_ACTIVE` from the installed cron path, not only manual direct healthcheck; expected-head policy is explicit. |
| Clean API service ownership evidence. | `PM -> E3(explorer) -> PM` | Service restart/systemd changes require operator authorization. | Uvicorn process and `openclaw-trading-api.service` state agree, or the intentional out-of-unit process is documented with a healthcheck. |

### Autonomy / Learning Closure

| Work | Role chain | Authorization | Acceptance |
|---|---|---|---|
| Decide durable learning materialization architecture: artifact SSOT with strict provenance vs PG-backed Cost Gate learning ledger. | `PM -> PA(default) -> MIT(default) -> FA(default) -> CC(default) -> PM` | Source-only design no operator auth; runtime PG migration/apply or writer enablement requires operator/PM deploy authorization. | Decision record states SSOT, schema/manifest, idempotency, duplicate policy, retention, and exact non-authority guarantees. |
| Build learned-candidate-to-bounded-proposal contract. | `PM -> PA(default) -> QC(default) -> MIT(default) -> AI-E(default) -> CC(default) -> E1(worker) -> E2(explorer) -> E4(worker) -> PM` | Source-only for contract and tests; operator auth for any runtime apply, risk-band activation, writer enablement, or probe authority. | A candidate can become a bounded proposal with validation evidence, allowed parameter bands, rollback path, audit trail, and no direct learning-to-order/risk mutation. |

### Profit / Probe Proof

| Work | Role chain | Authorization | Acceptance |
|---|---|---|---|
| Run bounded result-review chain on only candidate-matched outcomes after authorized probe exists. | `PM -> BB(default) -> MIT(default) -> QC(default) -> FA(default) -> PM` | Probe execution/order writes require operator authorization; post-run artifact review is source/runtime read-only. | Result review and execution-realism review both positive; net PnL includes fee/slippage; matched blocked controls are present; no unattributed fills included. |

## P2 Next Work

### Autonomy / Learning Closure

| Work | Role chain | Authorization | Acceptance |
|---|---|---|---|
| Reopen AI/ML-assisted parameter suggestions only after deterministic learning loop is auditable. | `PM -> AI-E(default) -> QC(default) -> MIT(default) -> CC(default) -> PA(default) -> PM` | Source-only for ledger/routing/budget fixes; operator auth for enabling paid model calls or applying parameter changes. | Pre-call budget gate, append-only invocation ledger, no direct order/risk mutation, and model output can only produce reviewable proposals. |

### Evidence Quality

| Work | Role chain | Authorization | Acceptance |
|---|---|---|---|
| Add dashboard/reporting guardrails so artifact proof flags cannot be misread. | `PM -> FA(default) -> PA(default) -> E1(worker) -> E2(explorer) -> E4(worker) -> PM` | Source-only unless deploying to runtime. | UI/report surfaces show `artifact-only`, `operator-defer`, `probe-authority=false`, and `promotion-evidence=false` as first-class states. |

## What Not To Do Next

- Do not lower global Cost Gate or retune its thresholds from blocked-outcome artifacts.
- Do not promote to live, open true-live gates, or treat Demo fills as live-readiness evidence.
- Do not treat `flash_dip_buy` Demo fills as bounded Cost Gate probe proof.
- Do not count unattributed fills or deep overhang orders as promotion-grade evidence.
- Do not enable the Rust demo-learning writer, apply PG migrations, backfill rows, edit crons, restart services, or cancel orders as an audit shortcut.
- Do not activate AI/model parameter suggestions or paid model calls as a substitute for deterministic candidate validation.
- Do not increase demo notional/concurrency or relax PostOnly/near-touch guardrails before exchange overhang and attribution are clean.
- Do not use Paper archive, source-smoke artifacts, or single-window MM positives as promotion proof.

## Operator Authorization vs Source-Only Work

Requires operator authorization:

- Any Bybit cancel/modify/order action, including clearing the deep working-order overhang.
- Any bounded demo probe/order authority grant.
- Any Cost Gate threshold/risk-band/runtime config change.
- Any crontab edit, service restart, deploy, writer enablement, or runtime env mutation.
- Any PG write/backfill/migration apply on runtime.
- Any true-live authorization, live gate opening, or secret/auth artifact action.
- Any paid model-call activation if it changes AI-E budget posture.

Source-only implementation or audit can proceed after PM dispatch:

- Fill-attribution future-proofing and proof-exclusion logic.
- Artifact schema/reporting guards that make authority/proof flags unambiguous.
- Durable learning architecture design and source tests.
- PG migration source files and Mac/unit validation, before runtime apply.
- Bounded-proposal contract source implementation with all authority flags false by default.
- Cron installer/checker source hardening, before installed crontab mutation.

## PM Dispatch Recommendation

Recommended sequence:

1. `PM -> E3 -> BB -> CC -> PM`: read-only overhang/authority split verification and operator decision packet.
2. `PM -> BB -> PA -> E1 -> E2 -> E4 -> QA -> PM`: source-only fill lineage and proof-exclusion fix plan/implementation, if PM opens implementation.
3. `PM -> E3 -> PM`: operator-approved cron expected-head reconcile only after step 1 decision; otherwise source-only checker patch.
4. `PM -> PA -> MIT -> FA -> CC -> PM`: durable learning SSOT decision.
5. `PM -> QC -> MIT -> BB -> PA -> CC -> PM -> Operator`: exact bounded probe contract for one candidate.
6. After authorized probe only: `PM -> BB -> MIT -> QC -> FA -> PM` result/execution-realism/profit verdict.

PA conclusion: continue evidence build, but gate it behind exchange/evidence cleanup. The architecture is close enough to justify a narrow bounded-probe review path, and too immature to justify promotion, global gate relaxation, or autonomous parameter mutation.
