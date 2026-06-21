# Runtime Demo Cost Gate Read-Only Audit

## Summary

Fresh read-only runtime evidence explains why demo has not been ordering:

- the demo engine is alive
- demo/live_demo decision/risk rows are still recorded in the recent 4h window
- those rows are all Cost Gate rejects
- intents/orders/fills are absent in the recent 4h window
- latest 1h had no new decision/risk/order/fill rows at audit time
- Cost Gate learning/demo-learning evidence crons are not installed
- latest runtime alpha artifact is stale schema v1 and must not be trusted for actionability

## Runtime Facts

- Local source HEAD: `4ba1d56c162c66bc5b0f1a4288b56360ac6afa1b`
- Runtime source: `main...origin/main [behind 5]`, dirty/untracked, HEAD `917be4cc9a3d3549328155f1863d42400c70267f`
- Watchdog: `engine_alive=true`, demo `alive=true`, snapshot age about 18s
- Control API service: inactive
- Latest runtime alpha artifact: `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`
  - schema `alpha_discovery_runtime_killboard_v1`
  - created `2026-06-21T22:45:01.621261+00:00`
  - `actionable_alpha_found=true`
  - `actionable_probe_found=true`
  - missing runtime-source and learning-worklist fields

## PG Counts

Collected at runtime `now() = 2026-06-22 00:52:29.181351+02`.

| Window | Evidence | Count | Latest |
|---|---:|---:|---|
| 1h | decision/risk/intents/orders/fills | 0 | - |
| 4h | `learning.decision_features` | 2,496 | `2026-06-21 23:15:59.991+02` |
| 4h | `trading.risk_verdicts` | 2,496 | `2026-06-21 23:15:59.991+02` |
| 4h | intents / orders / fills | 0 / 0 / 0 | - |
| 24h | `learning.decision_features` | 53,597 | `2026-06-21 23:15:59.991+02` |
| 24h | `trading.risk_verdicts` | 53,597 | `2026-06-21 23:15:59.991+02` |
| 24h | intents / orders / fills | 3 / 3 / 0 | intents latest `2026-06-21 02:00:00.003+02` |

The 4h Cost Gate side-cell was:

- `demo | ma_crossover | BTCUSDT | -1 | cost_gate_js_demo_negative_edge | 2,496`
- risk reason: `cost_gate(JS-demo): estimated=-6.01bps < 0 — blocked / 負估計阻擋`

## Cost Gate Learning Lane

Runtime artifact state:

- `/tmp/openclaw/cost_gate_learning_lane/demo_learning_lane_plan_latest.json`
  - schema `cost_gate_demo_learning_lane_plan_v1`
  - status `READY_FOR_DEMO_LEARNING_PROBE`
  - `probe_candidate_count=4`
  - `main_cost_gate_adjustment=NONE`
- `/tmp/openclaw/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.json`
  - generated `2026-06-21T10:32:30+00:00`
  - old format with `learning_lane_scorecard`
  - coverage: risk verdicts / decision features `181,989`, joined contexts `352`, joined outcomes `0`
  - top historical probe candidate: `ma_crossover | ETHUSDT | Sell`, avg net `97.9788bps`, n `13,487`

Missing runtime activation evidence:

- no `demo_learning_evidence_audit` cron entry
- no `cost_gate_learning_lane` cron entry
- no cost-gate learning heartbeat
- no cost-gate learning status log
- no reject materializer artifact
- no blocked outcome refresh artifact
- no blocked outcome review artifact
- no learning-lane ledger rows visible in runtime artifacts

## Interpretation

Fact: rejected signals are not being silently discarded at the Risk/Cost Gate record layer; they are recorded in `learning.decision_features` and `trading.risk_verdicts`.

Fact: no recent order-flow evidence exists. The system is not gathering enough real demo order/fill validation data while Cost Gate rejects dominate.

Fact: latest 1h was not accumulating even rejected decision/risk rows at audit time, despite the demo engine being alive.

Inference: current runtime cannot be used to judge probe/actionability because source and artifact schema are stale. The v1 alpha artifact false-positive `actionable_*` fields are untrusted.

## Next Action

The next useful step is not another source-only visibility layer. It is operator-approved runtime work:

1. Reconcile/sync runtime source carefully, preserving or reviewing dirty paths.
2. Refresh the read-only demo-learning evidence heartbeat.
3. Run Cost Gate learning preinstall refresh and activation preflight.
4. Install/enable the bounded evidence crons only after preflight passes.
5. Review the blocked outcome evidence before any bounded demo probe.

## Boundary

Read-only runtime git/artifact/PG/process checks plus docs only. No runtime source sync, artifact refresh, crontab/env edit, deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, Cost Gate lowering, order authority, execution proof, or promotion proof.
