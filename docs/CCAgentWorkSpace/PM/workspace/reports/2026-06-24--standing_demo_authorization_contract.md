# Standing Demo Authorization Contract

日期：2026-06-24
Active blocker：`P0-BOUNDED-PROBE-AUTHORIZATION-STANDING-DEMO-CONTRACT`
角色鏈：PM -> PA -> E1/PM -> E2 -> E4 -> E3 -> PM（BB skipped：本輪無 exchange-facing 動作）
狀態：`DONE_WITH_CONCERNS`

## 結論

Operator 的 standing Demo/API operational authorization 已被轉成可審計的 source/runtime contract，但沒有被轉成裸 order/probe 權限。

Source/runtime commit `bdc1e1568431797cd1001e4484bf2da7ae6df7c4` adds opt-in `standing_demo_operator_authorization_v1` ingestion to `bounded_probe_operator_authorization`. It can replace the exact typed-confirm only when the standing artifact is:

- fresh and schema/status valid
- environment `demo` or `live_demo`
- scope `demo_api_only_bounded_probe`
- top-level `demo_only=true`
- top-level `candidate_scoping_required=true`
- top-level `max_authorized_probe_orders_per_candidate` present
- operator-aligned
- short-TTL
- budget <= source plan and <= standing cap
- recursively free of live/runtime/order/probe/PG/Bybit/service/writer/Cost Gate/promotion contamination

The emitted object is still one `bounded_demo_probe_operator_authorization_v1` for one candidate, one budget, and one TTL. Packet-layer answers remain:

- `active_runtime_probe_authority=false`
- `active_runtime_order_authority=false`
- `plan_mutation_performed=false`
- `writer_enabled=false`
- `order_submission_performed=false`
- `runtime_mutation_performed=false`

Concern：this closes a repeat-authorization ergonomics gap. It is not order execution, not Cost Gate proof, not live permission, and not promotion evidence.

## Session Loop State

```json
{
  "session_goal": "Profit-first Demo-learning Autonomy Improvement Loop + Aggressive Alpha Expansion Mode",
  "active_blocker_id": "P0-BOUNDED-PROBE-AUTHORIZATION-STANDING-DEMO-CONTRACT",
  "blocker_goal": "Convert the operator's standing Demo/API operational authorization into a structured, candidate-scoped, reconstructable bounded Demo authorization confirmation source without granting active runtime authority.",
  "profit_relevance": "A bounded Demo probe is the fastest safe path for high-upside false-negative candidates, but the authorization layer must preserve live-applicability by binding every Demo experience to exact candidate, budget, TTL, fee/slippage, lineage, and controls.",
  "completed_blockers": [
    "P1-MM-MOTIF-DISTINCT-DATE-WORKLIST-SURFACE",
    "P0-BOUNDED-PROBE-AUTHORIZATION-STANDING-DEMO-CONTRACT"
  ],
  "blocked_blockers": [
    "P0-PROFIT-OUTCOME-REVIEW"
  ],
  "previous_report_paths": [
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--bounded_probe_authorization_broad_demo_fail_closed.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--mm_motif_distinct_date_worklist_surface.md"
  ],
  "source_head": {
    "local": "bdc1e1568431797cd1001e4484bf2da7ae6df7c4",
    "origin": "bdc1e1568431797cd1001e4484bf2da7ae6df7c4",
    "runtime_before": "52b572eda6c5652c97d2e822de9a9670250629a6",
    "runtime_after": "bdc1e1568431797cd1001e4484bf2da7ae6df7c4"
  },
  "runtime_timestamp": "2026-06-24T15:56:03Z",
  "pg_snapshot_timestamp": "not required; no PG read/write",
  "artifact_mtimes": {
    "/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json": "2026-06-24T15:56:04Z",
    "/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json": "2026-06-24T15:56:02Z"
  },
  "operator_action_required": false,
  "new_evidence_delta_required": "An operator authorization revision or source-only authorization contract gap is required; old broad-authorization fail-closed audit must not be repeated unchanged.",
  "new_evidence_delta_found": "Operator supplied standing Demo/API operational authorization and required Demo experience to remain later live-applicable. Existing helper only accepted exact typed-confirm, causing repeated operator-blocker loops.",
  "acceptance_criteria": [
    "standing Demo authorization is opt-in JSON input, not implicit chat text",
    "wrong non-empty typed confirm still fails",
    "standing JSON must be demo/live_demo only, bounded-probe scoped, top-level explicit, capped, fresh, short-TTL, and operator-aligned",
    "truthy strings and nested authority/proof/mutation contamination fail closed",
    "emitted authorization object remains candidate-scoped and budget/TTL bounded",
    "packet answers keep active runtime order/probe authority false",
    "no cron default consumes standing JSON",
    "Mac and runtime focused/adjacent tests pass",
    "runtime expected-head pins and alpha killboard prove source freshness and no authority/proof/mutation flags"
  ],
  "next_blocker_id": "P0-BOUNDED-PROBE-AUTHORIZATION-CANDIDATE-SCOPED-STANDING-ARTIFACT"
}
```

## Anti-Repeat Decision

Initial old blocker：`P0-BOUNDED-PROBE-AUTHORIZATION`.

Decision：do not rerun the previous exact-confirm audit as-is. Previous report already established broad Demo language was not enough and returned `TYPED_CONFIRM_REQUIRED`.

New decision：`DONE_WITH_CONCERNS` for the source/runtime contract blocker because there is a real evidence delta: the operator supplied standing Demo/API authorization and explicitly required Demo experience to be live-applicable later.

This did not create an actual candidate authorization artifact. It created the safe artifact format and parser path for a future candidate-scoped standing authorization packet.

## Source Change

Changed:

- `helper_scripts/research/cost_gate_learning_lane/contract.py`
- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_operator_authorization.py`
- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_operator_authorization_cli.py`
- `helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py`

Key behavior:

- adds `standing_demo_operator_authorization_v1`
- adds CLI opt-in `--standing-demo-authorization-json`
- records standing source path and sha256
- rejects truthy authority strings such as `"true"` / `1` / `"authorized"`
- rejects top-level false fields even if `answers` says true
- requires top-level cap instead of accepting `answers` cap
- rejects operator mismatch
- keeps exact typed-confirm path unchanged
- preserves defer/default behavior when no standing JSON is supplied

E2 first returned `CHANGES_REQUESTED` for truthy-string authority contamination and top-level field/cap fallback via `answers`. PM fixed both. E2 final：`APPROVE`.

E4：`PASS`.

Mac verification:

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py
18 passed

PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_false_negative_candidate_friction_scorecard.py helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py helper_scripts/research/tests/test_cost_gate_bounded_probe_result_review.py helper_scripts/research/tests/test_cost_gate_bounded_probe_execution_realism_review.py
136 passed

python3 -m pytest -q --import-mode=importlib helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py
15 passed

py_compile and git diff --check passed
```

Local artifact-only smoke produced `BOUNDED_DEMO_PROBE_AUTHORIZED` with `authorization_confirmation_source=standing_demo_authorization`, while packet answers kept active runtime probe/order false, Cost Gate `NONE`, and promotion false. The smoke wrote only under `/tmp/openclaw_standing_demo_auth_smoke_*`.

## Runtime Sync

E3 approved bounded runtime sync. BB skipped because this was not exchange-facing.

Runtime preflight after fetch:

```text
HEAD=52b572eda6c5652c97d2e822de9a9670250629a6
ORIGIN=bdc1e1568431797cd1001e4484bf2da7ae6df7c4
STATUS_LINES=0
ANCESTOR=yes
```

Sync action:

```text
git merge --ff-only origin/main
HEAD=bdc1e1568431797cd1001e4484bf2da7ae6df7c4
STATUS_LINES=0
```

Runtime verification:

```text
auth focused: 18 passed
adjacent bounded/profitability/alpha/worklist: 136 passed
cron static: 15 passed
py_compile: PASS
git diff --check: PASS
```

Crontab expected-head patch:

```text
old 52b572eda6c5652c97d2e822de9a9670250629a6: 11 -> 0
new bdc1e1568431797cd1001e4484bf2da7ae6df7c4: 0 -> 11
line_count: 70 -> 70
OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0: 1 -> 1
OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=1: 0
```

Backups:

- `/tmp/openclaw/runtime_hygiene/crontab_pre_standing_demo_auth_20260624T155538Z.txt`
- `/tmp/openclaw/runtime_hygiene/crontab_post_standing_demo_auth_20260624T155538Z.txt`
- `/tmp/openclaw/runtime_hygiene/crontab_standing_demo_auth_summary_20260624T155538Z.json`

The first crontab replacement script exited before install because `grep` returned nonzero on a zero-match count under `set -e`. PM verified installed crontab was still unchanged, then reran with Python counts and installed only after all invariants passed.

## Runtime Artifact Result

Alpha refresh command shape:

```text
OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv \
OPENCLAW_DATA_DIR=/tmp/openclaw \
OPENCLAW_EXPECTED_SOURCE_HEAD=bdc1e1568431797cd1001e4484bf2da7ae6df7c4 \
$HOME/BybitOpenClaw/srv/helper_scripts/cron/alpha_discovery_throughput_cron.sh
```

`/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`:

```text
created_at_utc=2026-06-24T15:56:03.085805+00:00
expected_head_status=MATCH
git_head=bdc1e1568431797cd1001e4484bf2da7ae6df7c4
git_status=SYNCED_CLEAN
worklist_status=OPERATOR_GATED_LEARNING_READY
task_type_counts={'candidate_evidence_build': 1, 'data_capture': 2, 'event_wait': 1, 'mm_current_fee_confirmation': 1, 'mm_motif_distinct_date_accumulation': 1, 'operator_probe_review': 1, 'reject_or_archive': 2, 'sample_accumulation': 1}
runtime_probe_authority_found=false
runtime_order_authority_found=false
promotion_evidence_found=false
cost_gate_mutation_found=false
actionable_probe_semantics=OPERATOR_REVIEW_READY_NO_RUNTIME_AUTHORITY
```

`/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json` after default/defer refresh:

```text
status=READY_FOR_OPERATOR_AUTHORIZATION_REVIEW
decision=defer
authorization_confirmation_source=null
operator_authorization_object_emitted=false
bounded_demo_probe_authorized=false
active_runtime_probe_authority=false
active_runtime_order_authority=false
plan_mutation_performed=false
writer_enabled=false
order_submission_performed=false
runtime_mutation_performed=false
global_cost_gate_lowering_recommended=false
main_cost_gate_adjustment=NONE
promotion_evidence=false
standing_demo_authorization_present=false
standing_demo_authorization_valid=false
operator_authorization_present=false
```

API service sanity:

```text
openclaw-trading-api.service active/enabled
MainPID=2218842
NRestarts=0
OPENCLAW_ALLOW_MAINNET=1 count=0
```

## Aggressive Profit Hypotheses

| Hypothesis | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action | Score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AVAX false-negative bounded Demo probe with standing auth packet | Prior false-negative evidence had large after-cost cushion; standing contract removes repeat authorization friction while preserving candidate-scope. | Generate structured standing Demo auth JSON for exactly `grid_trading|AVAXUSDT|Sell`, then defer-mode packet review; no order until runtime admission. | Fresh preflight, placement, authority readiness, standing auth JSON, candidate max orders, TTL, lineage plan. | Any candidate mismatch, no candidate-matched fill, net after fees/slippage <= control, or lineage contamination. | Structured Demo-only candidate-scoped auth artifact; no live. | `prepare_candidate_scoped_standing_demo_authorization_packet_for_operator_review` | upside 5, evidence 3, realism 2, cost 3, time 3, account risk 2, governance risk 2, autonomy 5 |
| SOXLUSDT current-fee repeat-window MM path | Exact cell has one positive current-fee window; second independent repeat may validate low-cost maker edge. | Replay/accumulate same-key independent window with current fee and maker realism. | Fill-sim history, same candidate key, fee/slippage, sample/OOS split. | Repeat window non-positive, insufficient sample, or maker realism fails. | None for research. | `accumulate_or_replay_independent_windows_for_same_current_fee_mm_cell` | upside 3, evidence 3, realism 3, cost 4, time 4, account risk 1, governance risk 1, autonomy 4 |
| Low-friction MM motif distinct-date expansion | Repeating motif across dates may reveal broader microstructure edge rather than one exact cell. | Distinct-date replay for `low_friction_motif|spread_combo|recent_trade_imbalance`. | Motif windows, train/holdout, date diversity, fee schedule, maker/taker attribution. | Distinct dates remain insufficient or gap to current fee persists. | None for research. | `accumulate_distinct_window_history_for_repeated_low_friction_motif` | upside 4, evidence 2, realism 3, cost 3, time 3, account risk 1, governance risk 1, autonomy 5 |

## Boundary

Performed:

- source/test contract change
- commit and push
- E2/E4 verification
- E3-approved ff-only runtime source sync
- expected-head-only crontab patch
- artifact-only alpha refresh in defer/default mode
- docs update

Not performed:

- no Bybit call/order/cancel/modify
- no API POST
- no PG write/schema migration
- no service restart/daemon-reload/process signal
- no live/mainnet
- no Cost Gate lowering
- no active probe/order authority
- no Rust writer enablement
- no promotion proof
