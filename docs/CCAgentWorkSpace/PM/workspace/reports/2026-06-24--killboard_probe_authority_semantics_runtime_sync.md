# Killboard Probe Authority Semantics Runtime Sync

日期：2026-06-24
Active blocker：`P1-RUNTIME-SOURCE-SYNC-KILLBOARD-AUTHORITY-SEMANTICS-REFRESH`
角色鏈：PM -> E2 -> E4 -> E3 -> PM（E1 was PM-local source patch; BB skipped：本輪無 exchange-facing 動作）
狀態：`DONE_WITH_CONCERNS`

## 結論

`alpha_discovery_runtime_killboard_v10` now separates operator review readiness from actual runtime probe/order authority.

Runtime is clean at `7d118e812d59d76e1c3049a735d3522ab59e481c`, demo-learning cron expected-head pins are synced to that head, and `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json` now reports:

- `ready_for_probe=1`
- `actionable_probe_found=true`
- `operator_probe_review_ready_count=1`
- `operator_probe_review_ready_found=true`
- `runtime_probe_authority_found=false`
- `runtime_order_authority_found=false`
- `promotion_evidence_found=false`
- `cost_gate_mutation_found=false`
- `probe_review_ready_without_authority=true`
- `actionable_probe_semantics=OPERATOR_REVIEW_READY_NO_RUNTIME_AUTHORITY`

Concern：legacy `ready_for_probe` / `actionable_probe_found` remains true for backward compatibility. Future authority-sensitive consumers must use `runtime_probe_authority_found`, `runtime_order_authority_found`, and `actionable_probe_semantics`; legacy fields alone are not authority.

## Session Loop State

```json
{
  "session_goal": "Profit-first Demo-learning Autonomy Improvement Loop + Aggressive Alpha Expansion Mode",
  "active_blocker_id": "P1-RUNTIME-SOURCE-SYNC-KILLBOARD-AUTHORITY-SEMANTICS-REFRESH",
  "blocker_goal": "Fast-forward runtime to source commit 7d118e81 and refresh alpha_discovery_latest so killboard separates operator review readiness from actual runtime probe/order authority.",
  "profit_relevance": "The killboard is the autonomy loop's routing surface; ambiguous probe-readiness labels can cause unsafe future optimization, so live-applicable demo learning needs explicit no-authority semantics.",
  "completed_blockers": [
    "P1-RUNTIME-ALPHA-DESIGN-KILLBOARD-REFRESH",
    "P1-KILLBOARD-PROBE-AUTHORITY-SEMANTICS-SOURCE-HARDENING",
    "P1-RUNTIME-SOURCE-SYNC-MM-MOTIF-DESIGN-ARTIFACT-REFRESH",
    "P1-MM-MOTIF-DISTINCT-DATE-ACCUMULATION-DESIGN"
  ],
  "blocked_blockers": [
    "P0-BOUNDED-PROBE-AUTHORIZATION",
    "P0-PROFIT-OUTCOME-REVIEW"
  ],
  "previous_report_paths": [
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_mm_motif_design_artifact_refresh.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--mm_motif_distinct_date_accumulation_design.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--bounded_probe_authorization_broad_demo_fail_closed.md"
  ],
  "source_head": {
    "local": "7d118e812d59d76e1c3049a735d3522ab59e481c",
    "origin": "7d118e812d59d76e1c3049a735d3522ab59e481c",
    "runtime_before": "8077dc9c39cf66fa8a5b474421c326c84b7448a3",
    "runtime_after": "7d118e812d59d76e1c3049a735d3522ab59e481c"
  },
  "runtime_timestamp": "2026-06-24T14:26:23Z",
  "pg_snapshot_timestamp": "not required; no PG read/write",
  "artifact_mtimes": {
    "/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json": 1782311185,
    "/tmp/openclaw/alpha_discovery_throughput/mm_motif_amplification_latest.json": 1782310504,
    "/tmp/openclaw/alpha_discovery_throughput/mm_current_fee_confirmation_latest.json": 1782310504
  },
  "operator_action_required": false,
  "new_evidence_delta_required": "runtime source behind source commit containing authority-semantics hardening",
  "new_evidence_delta_found": "runtime head was 8077dc9c; local/origin source was 7d118e81",
  "acceptance_criteria": [
    "E2 reviews field semantics and fail-closed naming",
    "E4 verifies source regression",
    "E3 approves ff-only runtime sync and targeted artifact refresh",
    "Runtime fast-forwards cleanly to 7d118e81",
    "Demo-learning cron expected-head pins update from 8077dc9c to 7d118e81 only",
    "Refresh only alpha_discovery_latest/history through runtime_runner, not the broader alpha cron",
    "Killboard emits OPERATOR_REVIEW_READY_NO_RUNTIME_AUTHORITY with runtime_probe_authority_found=false and runtime_order_authority_found=false",
    "No service restart, daemon-reload, API POST, PG write, Bybit call, or order/probe/live authority"
  ],
  "next_blocker_id": "P1-MM-MOTIF-DISTINCT-DATE-EVIDENCE-ACCUMULATION"
}
```

## Anti-Repeat Decision

Skipped:

- `P0-BOUNDED-PROBE-AUTHORIZATION`：still blocked by exact candidate-scoped authorization. Broad Demo/API permission is not an authorization object.
- `P0-PROFIT-OUTCOME-REVIEW`：still no candidate-matched bounded-probe outcomes.
- `P1-MM-MOTIF-DISTINCT-DATE-EVIDENCE-ACCUMULATION`：no new independent-date evidence; motif still requires two distinct dates and current-fee cell still requires one independent repeat window.

Proceeded because natural 16:15 CEST cron produced a new killboard with the MM design ingested, while the source had a new no-authority semantics hardening not yet present on runtime.

## Source Change

Changed:

- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
- `helper_scripts/research/tests/test_alpha_discovery_throughput.py`

New killboard/history fields:

- `operator_probe_review_ready_count`
- `operator_probe_review_ready_found`
- `runtime_probe_authority_found`
- `runtime_order_authority_found`
- `promotion_evidence_found`
- `cost_gate_mutation_found`
- `probe_review_ready_without_authority`
- `actionable_probe_semantics`

Compatibility kept:

- `ready_for_probe`
- `actionable_probe_found`

The new fields are recursively derived from worklist, profitability, and Cost Gate artifact spine summaries so lower-priority contaminated artifacts cannot be hidden by a benign top task.

## Review Chain

E2 verdict：`DONE_WITH_CONCERNS`

E2 conditions adopted:

- use `runtime_*_authority_found` names, not ambiguous authority names.
- use upper-case enum values such as `OPERATOR_REVIEW_READY_NO_RUNTIME_AUTHORITY`.
- keep legacy fields compatible.
- carry the new fields into `_history_row()`.
- add contamination coverage where runtime authority true is exposed and planner remains fail-closed.

E4 / PM-local verification:

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q \
  helper_scripts/research/tests/test_alpha_discovery_throughput.py \
  helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py \
  helper_scripts/research/tests/test_mm_current_fee_confirmation.py \
  helper_scripts/research/tests/test_mm_motif_amplification.py
```

Result：`111 passed`

Additional checks:

- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/tests/test_alpha_discovery_throughput.py`：PASS
- `git diff --check`：PASS

## Runtime Chain

E3 verdict：`APPROVE with conditions`

BB skipped because no exchange-facing API, order path, cancel/modify, connector semantics, or Bybit retCode handling changed.

Preflight:

```text
HEAD=8077dc9c39cf66fa8a5b474421c326c84b7448a3
ORIGIN=7d118e812d59d76e1c3049a735d3522ab59e481c
STATUS=
ANCESTOR=yes
preflight=PASS
```

Runtime sync:

```text
git merge --ff-only origin/main
HEAD=7d118e812d59d76e1c3049a735d3522ab59e481c
ORIGIN=7d118e812d59d76e1c3049a735d3522ab59e481c
STATUS_LINES=0
ff_only_merge=PASS
```

Runtime Python-only verification:

- focused/adjacent tests：`111 passed in 0.78s`
- py_compile：PASS
- `git diff --check`：PASS

Crontab expected-head replacement:

```text
old_count_before=10
new_count_before=0
line_count_before=70
line_count_after=70
old_count_after=0
new_count_after=10
OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0 count=1
OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=1 count=0
crontab_expected_head_replacement=PASS
```

Refresh command shape:

```text
python3 -m alpha_discovery_throughput.runtime_runner \
  --data-dir /tmp/openclaw \
  --repo-root /home/ncyu/BybitOpenClaw/srv \
  --expected-head 7d118e812d59d76e1c3049a735d3522ab59e481c \
  --out-dir /tmp/openclaw/alpha_discovery_throughput
```

This writes only `alpha_discovery_latest.json`, a dated alpha discovery JSON, and `alpha_discovery_history.jsonl`.

## Runtime Artifact Result

`/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`:

- `schema_version=alpha_discovery_runtime_killboard_v10`
- `created_at_utc=2026-06-24T14:26:23.336248+00:00`
- `runtime_source.git_head=7d118e812d59d76e1c3049a735d3522ab59e481c`
- `runtime_source.expected_head_status=MATCH`
- `runtime_source.expected_head_matches=true`
- `ready_for_probe=1`
- `actionable_probe_found=true`
- `operator_probe_review_ready_count=1`
- `operator_probe_review_ready_found=true`
- `runtime_probe_authority_found=false`
- `runtime_order_authority_found=false`
- `promotion_evidence_found=false`
- `cost_gate_mutation_found=false`
- `probe_review_ready_without_authority=true`
- `actionable_probe_semantics=OPERATOR_REVIEW_READY_NO_RUNTIME_AUTHORITY`
- `top_learning_task_probe_authority_granted=false`
- `top_learning_task_order_authority_granted=false`
- `profitability_global_cost_gate_lowering_recommended=false`
- `profitability_order_authority_granted=false`
- `profitability_promotion_evidence=false`

## API Service Sanity

Read-only post-check:

```text
openclaw-trading-api.service: active running enabled
MainPID=2218842
NRestarts=0
OPENCLAW_ALLOW_MAINNET=1 count=0
health_http=401
```

No service restart, daemon-reload, process signal, unit edit, or API POST was performed.

## Aggressive Profit Hypotheses

### 1. MM current-fee cell with explicit no-authority routing

- `why_it_might_make_money`：`SOXLUSDT|back|informed_skip|fill_only` still has `+0.715bps` after current maker fees, and the killboard now prevents review-ready status from being mistaken for runtime authority.
- `fastest_safe_test`：wait for or produce the next independent-window history refresh, then rerun current-fee confirmation.
- `required_data`：fresh fill_sim history summaries, exact candidate identity, maker fee schedule, L1 adverse-selection sample.
- `failure_condition`：same exact key fails to repeat or net after realistic fees/slippage turns negative.
- `authority_required`：none for research; exact candidate-scoped bounded Demo authority only after review.
- `max_safe_next_action`：repeat-window evidence accumulation.
- scoring：expected_net_pnl_upside 3/5, evidence_strength 3/5, execution_realism 2/5, cost_after_fees 3/5, time_to_test 4/5, risk_to_account 1/5, risk_to_governance 1/5, autonomy_value 4/5.

### 2. Same-motif distinct-date accumulation

- `why_it_might_make_money`：the `low_friction_motif|spread_combo|recent_trade_imbalance` motif may represent a repeatable maker microstructure regime, but still needs two distinct dates.
- `fastest_safe_test`：read-only motif refresh after new dated fill_sim history exists.
- `required_data`：fresh L1, fill_sim history, motif axes, train/holdout sample gates.
- `failure_condition`：distinct-date repetition fails or min train/holdout gross remains below current fees.
- `authority_required`：none for research; no bounded Demo until review.
- `max_safe_next_action`：accumulate distinct-date history, not order authority.
- scoring：expected_net_pnl_upside 4/5, evidence_strength 2/5, execution_realism 2/5, cost_after_fees 2/5, time_to_test 3/5, risk_to_account 1/5, risk_to_governance 1/5, autonomy_value 4/5.

### 3. False-negative candidate review path with safer routing

- `why_it_might_make_money`：the Cost Gate false-negative path still ranks `grid_trading|AVAXUSDT|Sell` with high blocked-control edge, but requires exact authorization and candidate-matched outcomes.
- `fastest_safe_test`：operator-review packet only; no mutation unless exact candidate-scoped authority artifact is emitted and runtime admission accepts it.
- `required_data`：typed-confirm artifact, candidate-matched fills, matched controls, fee/slippage lineage.
- `failure_condition`：authorization absent, fills unmatched, realized net PnL fails after fees/slippage, or execution realism under-captures control edge.
- `authority_required`：candidate-scoped bounded Demo probe authority; no live/mainnet.
- `max_safe_next_action`：do not rerun authorization audit; keep no-authority review surface clear.
- scoring：expected_net_pnl_upside 4/5, evidence_strength 3/5, execution_realism 3/5, cost_after_fees 3/5, time_to_test 2/5, risk_to_account 2/5, risk_to_governance 2/5, autonomy_value 4/5.

## Status Transition

- status：`DONE_WITH_CONCERNS`
- next_blocker_id：`P1-MM-MOTIF-DISTINCT-DATE-EVIDENCE-ACCUMULATION`
- why_not_repeating_current_blocker：runtime now emits explicit no-authority probe semantics and expected-head pins are synced; repeating this blocker would add no new evidence until killboard source changes or a new authority/evidence artifact appears.

## Boundary

Source/test + ff-only runtime source sync + expected-head-only crontab replacement + direct runtime_runner killboard refresh + docs only. No Bybit call/order/cancel/modify, no API POST, no PG read/write/schema migration, no service restart/daemon-reload/process signal, no unit edit, no live/mainnet, no global Cost Gate lowering, no probe/order authority, no Rust writer, and no promotion proof.
