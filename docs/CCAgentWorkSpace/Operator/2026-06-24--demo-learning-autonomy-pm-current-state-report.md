# 2026-06-24 Demo Learning Autonomy PM Current-State Report

STATUS: DONE_WITH_CONCERNS

PM verdict: the system is no longer demo-silent. It is evidence-active and
safety-gated, with fresh demo orders/fills and a working Cost Gate learning
artifact loop. It is not yet a sustainable autonomous profit system: profit
proof, autonomous parameter evolution, clean fill lineage, and bounded probe
outcomes are still missing.

## Dispatch

Read-only audit chain used:

- Quant / ML / data: `PM -> QC(default) -> MIT(default) -> AI-E(default) -> PM`
- Runtime / exchange: `PM -> E3(explorer) -> BB(default) -> PM`
- Compliance / architecture: `PM -> CC(default) -> FA(default) -> PA(default) -> PM`

Skipped implementation chain `E1/E2/E4/QA` because this turn was audit-only and
made no code/runtime changes.

## Current Facts

- Linux `trade-core` source is clean and synced at `c88deea7`.
- Demo engine and watchdog are running. True live is closed:
  `OPENCLAW_ALLOW_MAINNET=0`, no true-live orders/fills in the checked 30d
  window, and no live authorization artifact found under checked roots.
- Demo is active. Runtime PG evidence around 2026-06-24 01:01Z showed:
  - 1h: `760` decision/risk rows, `3` intents, `4` orders, `3` fills.
  - 24h: `39,395` decision/risk rows, `33` intents, `34+` orders, `3-5` fills
    depending on snapshot timing.
- `flash_dip_buy` is the active demo order path. MA/grid flow remains mostly
  Cost Gate rejected and becomes blocked-outcome / false-negative learning
  material.
- Demo-learning / Cost Gate crons are installed and firing; JSONL/artifact
  evidence is accumulating.
- Cost Gate learning ledger is currently artifact/JSONL based:
  `probe_ledger.jsonl` has about `92,105` valid rows, including about `45,938`
  blocked-signal outcomes.
- Rust hot-path demo-learning writer is disabled
  (`OPENCLAW_DEMO_LEARNING_LANE_WRITER=` empty). No dedicated PG-backed Cost
  Gate learning ledger was observed.
- Cost Gate false-negative candidates exist: `16` ranked candidates, with
  authority/proof flags still false:
  `global_cost_gate_lowering=false`, `probe_authority=false`,
  `order_authority=false`, `promotion_evidence=false`.
- Bounded probe result review still has `NO_PROBE_OUTCOMES_RECORDED`.
- AI/model autonomy is not materially active: 7d evidence showed zero
  `agent.ai_invocations`, `learning.ai_usage_log`, teacher directives, and ML
  parameter suggestions. Strategist/shadow rows are mostly metadata/no-op.
- BB found execution evidence concerns: same-day deep `Working` order overhang
  and unattributed SOL/ETH fills. These weaken promotion-grade lineage.
- E3 found runtime hygiene drift: installed cron expected-head pins still
  reference `1b6173e3` while current source is `c88deea7`, causing some
  persisted health artifacts to report misleading `SOURCE_NOT_READY`.
- API is reachable through a uvicorn process, but `openclaw-trading-api.service`
  itself is inactive. This is service ownership hygiene, not engine death.

## Answer To Operator Questions

### Has demo stopped ordering?

No. The blanket statement is now false. Demo has fresh orders and fills through
`flash_dip_buy`. The more precise statement is:

- Ordinary demo pilot order flow is active.
- Bounded Cost Gate probe authority is still closed and has no probe outcomes.

### Is the backend learning engine continuously learning?

Partially. It is continuously refreshing artifact-level learning from runtime
PG rows and markout proxies. It is not yet a durable autonomous backend learning
loop with decision impact, because the Rust hot-path writer is disabled, the
ledger is not PG-backed, and no bounded probe result has closed the loop.

### Are strategy agents drafting order signals?

Yes for strategy/runtime flow: PG shows fresh decision features, risk verdicts,
approved `flash_dip_buy` intents, orders, and fills. For AI/Strategist autonomy,
evidence is weaker: strategist/shadow rows exist, but AI/model invocation and
parameter-suggestion ledgers do not show material recent self-adjustment.

## Core Requirement Gap

| Requirement | PM classification | Reason |
|---|---|---|
| Long-term continuous learning | PARTIAL | Cron/artifact learning is active, but backend writer and PG-backed decision-impact loop are not proven. |
| Sustainable autonomous evolution | PARTIAL / NOT PROVEN | The system ranks candidates and worklists, but does not yet apply learned parameter changes. |
| Profit generation | NOT ACHIEVED | Demo fills exist, but no candidate-matched, repeat/OOS, fee/slippage-positive bounded probe proof. |
| Autonomous trading parameter tuning | NOT ACHIEVED | No Cost Gate/probe/order authority and no material parameter suggestions. |
| Controllable risk parameters | PARTIAL | Safety gates work; autonomous risk tuning inside operator bands is not demonstrated. |
| Explainable trade evidence | PARTIAL | Many rows/artifacts exist, but unattributed fills and working-order overhang block promotion-grade reconstruction. |
| Demo/live promotion readiness | BLOCKED | Operator review, bounded authorization, clean execution evidence, and post-probe review are missing. |

## P0/P1 Next Work

P0:

- Read-only inventory and operator decision packet for deep working-order
  overhang. Any cancel/modify requires operator authorization.
- Fix future fill lineage/proof exclusion so unattributed fills cannot count as
  promotion or bounded-probe proof.
- Do not authorize a bounded probe until overhang/lineage and stale health pins
  are resolved.

P1:

- Reconcile installed cron expected-head pins so persisted health artifacts
  report the same truth as direct runtime source probes.
- Decide the durable learning SSOT: artifact ledger with strict provenance vs
  PG-backed Cost Gate learning ledger.
- Build the learned-candidate-to-bounded-proposal contract before any autonomous
  parameter mutation.

## Do Not Do

- Do not lower global Cost Gate.
- Do not promote to live or open true-live gates.
- Do not treat `flash_dip_buy` demo fills as bounded Cost Gate probe proof.
- Do not count unattributed fills or deep working orders as profit proof.
- Do not enable Rust writer, edit crons, write PG, restart services, cancel
  orders, or grant probe/order authority as an audit shortcut.

PM SIGN-OFF: CONDITIONAL. Current system is active and safer than a silent
black box, but it remains below the operator's target of long-term sustainable
autonomous profit and autonomous parameter evolution.
