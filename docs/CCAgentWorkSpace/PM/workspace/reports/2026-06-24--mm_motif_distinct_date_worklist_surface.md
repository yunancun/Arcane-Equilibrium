# MM Motif Distinct-Date Worklist Surface

日期：2026-06-24
Active blocker：`P1-MM-MOTIF-DISTINCT-DATE-WORKLIST-SURFACE`
角色鏈：PM -> E2 -> E4 -> E3 -> PM（BB skipped：本輪無 exchange-facing 動作）
狀態：`DONE_WITH_CONCERNS`

## 結論

Learning worklist now exposes the MM low-friction motif distinct-date accumulation path as its own no-authority research task.

Source commit `52b572eda6c5652c97d2e822de9a9670250629a6` lets one alpha blocker row emit both:

- `mm_current_fee_confirmation`
- `mm_motif_distinct_date_accumulation`

Runtime is clean at the same head. Crontab expected-head pins are synced, and alpha cron-shape refresh wrote `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json` at `2026-06-24T15:12:51Z` with:

- `runtime_source.expected_head_status=MATCH`
- `runtime_source.git_head=52b572eda6c5652c97d2e822de9a9670250629a6`
- `runtime_source.git_status=SYNCED_CLEAN`
- `worklist_status=OPERATOR_GATED_LEARNING_READY`
- `task_type_counts.mm_current_fee_confirmation=1`
- `task_type_counts.mm_motif_distinct_date_accumulation=1`
- both MM tasks `requires_operator_authorization=false`
- both MM tasks `runtime_mutation_required=false`
- `killboard.runtime_probe_authority_found=false`
- `killboard.runtime_order_authority_found=false`
- `killboard.promotion_evidence_found=false`
- `killboard.cost_gate_mutation_found=false`

Concern：this is autonomy visibility, not profit proof. The MM path still needs distinct-date repeats, current-fee repeat windows, OOS/walk-forward evidence, and maker-execution realism before any bounded Demo review or later live-applicable claim.

## Session Loop State

```json
{
  "session_goal": "Profit-first Demo-learning Autonomy Improvement Loop + Aggressive Alpha Expansion Mode",
  "active_blocker_id": "P1-MM-MOTIF-DISTINCT-DATE-WORKLIST-SURFACE",
  "blocker_goal": "Surface MM motif distinct-date accumulation as a separate no-authority learning worklist task.",
  "profit_relevance": "The current-fee MM path has small positive after-fee evidence in one window, while the low-friction motif may identify a broader maker/microstructure route with higher upside if it repeats across distinct dates and clears fees/slippage.",
  "completed_blockers": [
    "P1-MM-MOTIF-DISTINCT-DATE-ACCUMULATION-DESIGN",
    "P1-RUNTIME-SOURCE-SYNC-MM-MOTIF-DESIGN-ARTIFACT-REFRESH",
    "P1-RUNTIME-SOURCE-SYNC-KILLBOARD-AUTHORITY-SEMANTICS-REFRESH",
    "P1-ALPHA-CRON-RUNTIME-RUNNER-EXPECTED-HEAD-PROPAGATION",
    "P1-MM-MOTIF-DISTINCT-DATE-WORKLIST-SURFACE"
  ],
  "blocked_blockers": [
    "P0-PROFIT-OUTCOME-REVIEW"
  ],
  "previous_report_paths": [
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--mm_motif_distinct_date_accumulation_design.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_mm_motif_design_artifact_refresh.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--alpha_cron_expected_head_runtime_closure.md"
  ],
  "source_head": {
    "local": "52b572eda6c5652c97d2e822de9a9670250629a6",
    "origin": "52b572eda6c5652c97d2e822de9a9670250629a6",
    "runtime_before": "44a337e3cca07c8c984f6c3af0a702d7550628a5",
    "runtime_after": "52b572eda6c5652c97d2e822de9a9670250629a6"
  },
  "runtime_timestamp": "2026-06-24T15:12:51Z",
  "pg_snapshot_timestamp": "not required; no PG read/write",
  "artifact_mtimes": {
    "/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json": "2026-06-24T15:12:51Z",
    "/tmp/openclaw/alpha_discovery_throughput/mm_motif_amplification_latest.json": "2026-06-24T15:12:51Z",
    "/tmp/openclaw/alpha_discovery_throughput/mm_current_fee_confirmation_latest.json": "2026-06-24T15:12:51Z"
  },
  "operator_action_required": false,
  "new_evidence_delta_required": "For the proof blocker, a new distinct-date/repeat-window/OOS/maker-realism evidence delta would be required. For this source-only blocker, the actionable delta was a worklist visibility gap.",
  "new_evidence_delta_found": "Latest runtime artifacts carried MM motif distinct-date design, but learning_worklist emitted only the current-fee confirmation task for the same MM blocker row.",
  "acceptance_criteria": [
    "one blocker row can emit multiple worklist tasks",
    "MM motif task appears only when motif amplification requires distinct-date history",
    "task sorts after current-fee confirmation and before generic MM signal search",
    "task is recommendation-only and grants no order/probe/runtime authority",
    "completion evidence excludes single-window, artifact-count, and replay-only proof",
    "Mac and runtime focused/adjacent tests pass",
    "runtime source and expected-head pins are synced",
    "alpha artifact shows both MM tasks and no authority/proof/mutation flags"
  ],
  "next_blocker_id": "P1-MM-MOTIF-DISTINCT-DATE-EVIDENCE-ACCUMULATION"
}
```

## Anti-Repeat Decision

Initial proof blocker decision：`NO-OP_NO_EVIDENCE_DELTA`.

The active evidence artifacts still show:

- MM motif `low_friction_motif|spread_combo|recent_trade_imbalance`
- `MM_MOTIF_AMPLIFICATION_REQUIRES_DISTINCT_DATE_HISTORY`
- `top_distinct_dates_remaining=2`
- top frontier current-fee gap about `2.608bps`
- MM current-fee candidate `SOXLUSDT|back|informed_skip|fill_only`
- current-fee positive independent windows observed `1`
- remaining repeat windows `1`

There was no new proof-quality distinct-date or repeat-window evidence, so PM did not rerun the same evidence audit. PM moved to the source-only worklist-surface blocker because it could advance autonomy without runtime/order authority.

## Source Change

Changed:

- `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
- `helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py`

Behavior:

- Added task type `mm_motif_distinct_date_accumulation`.
- Added `_has_mm_motif_distinct_date_work(row)` for MM verdict rows where motif amplification reports distinct-date history still needed.
- Added `_task_types_for_row(row)` so one blocker row can emit the primary task plus the secondary motif task.
- Added motif task semantics:
  - objective `accumulate_distinct_date_low_friction_mm_motif_evidence_before_walk_forward_review`
  - blocker `low_friction_motif_lacks_distinct_date_confirmation`
  - completion gate `repeat_low_friction_motif_across_distinct_dates_before_walk_forward_review`
  - side-effect boundary `recommendation_only_no_order_authority_no_runtime_mutation`

Mac verification:

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_mm_motif_amplification.py helper_scripts/research/tests/test_mm_current_fee_confirmation.py
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_mm_motif_amplification.py helper_scripts/research/tests/test_mm_current_fee_confirmation.py
python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/learning_worklist.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py
git diff --check
```

Results：focused `11 passed`; related suite `111 passed`; py_compile and diff-check passed.

E2 result：`APPROVE`.

## Runtime Chain

E3 approved bounded sync with conditions:

- fetch and block unless runtime origin/main is `52b572eda6c5652c97d2e822de9a9670250629a6`.
- block unless runtime head is `44a337e3cca07c8c984f6c3af0a702d7550628a5`, worktree clean, and ancestor check passes.
- merge only with `git merge --ff-only origin/main`.
- crontab mutation limited to expected-head token replacement.
- run focused related tests and alpha cron-shape artifact refresh.
- assert no service restart, PG write, Bybit/API POST, Rust writer, Cost Gate lowering, order/probe/live authority, or promotion proof.

Preflight:

```text
HEAD=44a337e3cca07c8c984f6c3af0a702d7550628a5
ORIGIN=52b572eda6c5652c97d2e822de9a9670250629a6
STATUS_LINES=0
ANCESTOR=yes
```

Runtime sync:

```text
git merge --ff-only origin/main
HEAD=52b572eda6c5652c97d2e822de9a9670250629a6
STATUS_LINES=0
```

Runtime verification:

- related Python suite：`111 passed`
- py_compile：PASS
- `git diff --check`：PASS

Demo-learning crontab expected-head replacement:

```text
line_count=70
old_count_before=11
old_count_after=0
new_count_before=0
new_count_after=11
probe0_after=1
probe1_after=0
```

Crontab backups:

- `/tmp/openclaw/runtime_hygiene/crontab_pre_mm_motif_worklist_20260624T151241Z.txt`
- `/tmp/openclaw/runtime_hygiene/crontab_post_mm_motif_worklist_20260624T151241Z.txt`

Alpha cron-shape refresh:

```text
OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv \
OPENCLAW_DATA_DIR=/tmp/openclaw \
OPENCLAW_EXPECTED_SOURCE_HEAD=52b572eda6c5652c97d2e822de9a9670250629a6 \
$HOME/BybitOpenClaw/srv/helper_scripts/cron/alpha_discovery_throughput_cron.sh
```

Result：`alpha_cron_shape_refresh=PASS`.

## Aggressive Profit Hypotheses

| Hypothesis | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action | Score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Low-friction MM motif repeats across distinct dates | `spread_combo + recent_trade_imbalance` may identify maker windows where queue/friction is low enough to clear fees with stable gross edge. | Accumulate/replay distinct-date windows for the same motif, no orders. | MM verdict history, fill-sim windows, fee schedule, maker/taker attribution, spread/imbalance axes. | Motif fails repeat, gap stays > current-fee edge, or maker fill realism collapses. | None for research; bounded Demo only after review. | `accumulate_distinct_window_history_for_repeated_low_friction_motif` | upside 4, evidence 2, realism 3, cost 3, time 3, acct risk 1, gov risk 1, autonomy 5 |
| SOXLUSDT current-fee exact-cell repeat window | It already shows positive current-fee net in one independent window; a second window would strengthen after-fee path without lowering Cost Gate. | Recompute/replay independent windows for exact key `SOXLUSDT|back|informed_skip|fill_only`. | Same-key window summaries, current fee/slippage, sample counts, OOS split. | Second window non-positive after cost or insufficient sample. | None for replay/research. | `accumulate_or_replay_independent_windows_for_same_current_fee_mm_cell` | upside 3, evidence 3, realism 3, cost 4, time 4, acct risk 1, gov risk 1, autonomy 4 |
| False-negative AVAX bounded demo path remains high-upside but needs candidate-matched lineage | Prior after-cost false-negative score is large, but current candidate-matched fill lineage and bounded outcome proof are absent. | Create a machine-readable candidate-scoped Demo authorization packet only after exact candidate selection; then collect one bounded candidate-matched outcome. | Authorization object, candidate-matched orders/fills, fees/slippage, controls, fill lineage. | No candidate-matched fills, net after fees/slippage <= control, or lineage contaminated. | Demo-only candidate-scoped authority; no live. | Prepare review packet; do not count unattributed or cleanup fills. | upside 5, evidence 3, realism 2, cost 3, time 2, acct risk 2, gov risk 3, autonomy 4 |

## Boundary

Performed:

- source/test change
- commit and push
- ff-only runtime source sync
- expected-head-only crontab patch
- artifact-only alpha wrapper refresh
- docs update

Not performed:

- no Bybit call/order/cancel/modify
- no API POST
- no PG read/write/schema migration
- no service restart/daemon-reload/process signal
- no Cost Gate lowering
- no probe/order/live authority
- no Rust writer enablement
- no promotion proof

User's standing Demo API authorization is recorded as demo-only operational permission for future bounded Demo work. It is not live/mainnet permission and does not relax proof, lineage, fee/slippage, Guardian, Decision Lease, Rust authority, or reconstructability requirements.
