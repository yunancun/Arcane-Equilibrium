# Alpha Cron Expected-Head Runtime Closure

日期：2026-06-24
Active blocker：`P1-ALPHA-CRON-RUNTIME-RUNNER-EXPECTED-HEAD-PROPAGATION`
角色鏈：PM -> E2 -> E4 -> E3 -> PM（BB skipped：本輪無 exchange-facing 動作）
狀態：`DONE_WITH_CONCERNS`

## 結論

Natural alpha cron no longer loses runtime source freshness evidence.

Source commit `44a337e3cca07c8c984f6c3af0a702d7550628a5` makes `alpha_discovery_throughput_cron.sh` pass expected-head into `runtime_runner`. Runtime is clean at the same head, demo-learning expected-head pins are synced, and alpha natural cron line 57 now includes:

```text
OPENCLAW_EXPECTED_SOURCE_HEAD=44a337e3cca07c8c984f6c3af0a702d7550628a5
```

Cron-shape wrapper refresh wrote `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json` at `2026-06-24T14:52:50Z` with:

- `runtime_source.expected_head_status=MATCH`
- `runtime_source.git_head=44a337e3cca07c8c984f6c3af0a702d7550628a5`
- `runtime_source.git_status=SYNCED_CLEAN`
- `killboard.ready_for_probe=1`
- `killboard.operator_probe_review_ready_found=true`
- `killboard.runtime_probe_authority_found=false`
- `killboard.runtime_order_authority_found=false`
- `killboard.promotion_evidence_found=false`
- `killboard.cost_gate_mutation_found=false`
- `killboard.actionable_probe_semantics=OPERATOR_REVIEW_READY_NO_RUNTIME_AUTHORITY`

Concern：legacy `ready_for_probe=1` remains review readiness only. It is not probe/order authority and cannot be used as bounded-probe proof or promotion proof.

## Session Loop State

```json
{
  "session_goal": "Profit-first Demo-learning Autonomy Improvement Loop + Aggressive Alpha Expansion Mode",
  "active_blocker_id": "P1-ALPHA-CRON-RUNTIME-RUNNER-EXPECTED-HEAD-PROPAGATION",
  "blocker_goal": "Ensure alpha cron preserves runtime source expected-head evidence instead of overwriting alpha_discovery_latest with NOT_PROVIDED.",
  "profit_relevance": "Profit-first autonomy needs reconstructable, source-fresh killboard evidence before any learned candidate can become a bounded Demo proposal. Losing expected-head evidence weakens auditability and live-applicability of demo learning.",
  "completed_blockers": [
    "P1-KILLBOARD-PROBE-AUTHORITY-SEMANTICS-SOURCE-HARDENING",
    "P1-RUNTIME-SOURCE-SYNC-KILLBOARD-AUTHORITY-SEMANTICS-REFRESH",
    "P1-ALPHA-CRON-RUNTIME-RUNNER-EXPECTED-HEAD-PROPAGATION"
  ],
  "blocked_blockers": [
    "P0-BOUNDED-PROBE-AUTHORIZATION",
    "P0-PROFIT-OUTCOME-REVIEW"
  ],
  "previous_report_paths": [
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--killboard_probe_authority_semantics_runtime_sync.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_mm_motif_design_artifact_refresh.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--bounded_probe_authorization_broad_demo_fail_closed.md"
  ],
  "source_head": {
    "local": "44a337e3cca07c8c984f6c3af0a702d7550628a5",
    "origin": "44a337e3cca07c8c984f6c3af0a702d7550628a5",
    "runtime_before": "7d118e812d59d76e1c3049a735d3522ab59e481c",
    "runtime_after": "44a337e3cca07c8c984f6c3af0a702d7550628a5"
  },
  "runtime_timestamp": "2026-06-24T14:52:50Z",
  "pg_snapshot_timestamp": "not required; no PG read/write",
  "artifact_mtimes": {
    "/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json": "2026-06-24T14:52:50Z",
    "/tmp/openclaw/alpha_discovery_throughput/mm_motif_amplification_latest.json": "2026-06-24T14:52:50Z",
    "/tmp/openclaw/alpha_discovery_throughput/mm_current_fee_confirmation_latest.json": "2026-06-24T14:52:50Z"
  },
  "operator_action_required": false,
  "new_evidence_delta_required": "alpha latest must show NOT_PROVIDED after natural cron or source/runtime must differ",
  "new_evidence_delta_found": "natural 2026-06-24T14:30:04Z alpha cron overwrote the direct v483 MATCH artifact with expected_head_status=NOT_PROVIDED",
  "acceptance_criteria": [
    "source wrapper passes expected-head into runtime_runner without breaking no-env paths",
    "E2 approves Bash 3.2 / set -u behavior",
    "E4 focused tests pass on Mac and runtime",
    "E3 approves ff-only runtime sync and exact crontab mutations",
    "runtime is clean at 44a337e3",
    "alpha natural cron line supplies OPENCLAW_EXPECTED_SOURCE_HEAD",
    "cron-shape wrapper refresh produces expected_head_status=MATCH",
    "runtime probe/order authority, promotion evidence, and Cost Gate mutation remain false"
  ],
  "next_blocker_id": "P1-MM-MOTIF-DISTINCT-DATE-EVIDENCE-ACCUMULATION"
}
```

## Anti-Repeat Decision

Proceed decision：`DONE_WITH_CONCERNS`.

Skipped:

- `P0-BOUNDED-PROBE-AUTHORIZATION`：still requires exact candidate-scoped typed-confirm; broad Demo/API authorization is not a bounded-probe authorization object.
- `P0-PROFIT-OUTCOME-REVIEW`：no authorized bounded probe outcomes exist.
- repeating v483 runtime-runner-only refresh：blocked by new evidence that natural cron overwrote `MATCH` with `NOT_PROVIDED`; the correct next action was source + crontab propagation, not another direct refresh.

## Source Change

Changed:

- `helper_scripts/cron/alpha_discovery_throughput_cron.sh`
- `helper_scripts/cron/tests/test_alpha_discovery_throughput_cron_static.py`

Behavior:

- Expected-head source precedence:
  1. `OPENCLAW_EXPECTED_SOURCE_HEAD`
  2. `OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD`
  3. `OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD`
- If nonempty, wrapper passes `--expected-head "$EXPECTED_SOURCE_HEAD"` to `runtime_runner`.
- If empty, wrapper preserves the previous no-expected-head invocation.

E2 first returned `CHANGES_REQUESTED` because empty bash arrays under `set -u` can fail on Bash 3.2. PM replaced the array expansion with explicit `if/else` and added a subprocess wrapper test that runs the full wrapper with temp `BASE/DATA` and fake `PYBIN` for both empty-env and demo-stack-env paths.

Verification on Mac:

```text
bash -n helper_scripts/cron/alpha_discovery_throughput_cron.sh
python3 -m pytest -q --import-mode=importlib helper_scripts/cron/tests/test_alpha_discovery_throughput_cron_static.py
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py
python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/cron/tests/test_alpha_discovery_throughput_cron_static.py
git diff --check
```

Results：cron static `7 passed`; alpha/worklist `95 passed`; all other checks passed.

## Runtime Chain

E3 approved bounded sync with conditions:

- fetch and block unless runtime origin/main is `44a337e3`, runtime head is `7d118e81`, worktree is clean, and `HEAD` is ancestor.
- merge only by `git merge --ff-only origin/main`.
- fetched diff must contain only docs plus alpha cron wrapper/test.
- crontab expected-head replacement must preserve line count and existing flags.
- one-shot alpha wrapper verification must assert `MATCH` and no authority/proof/mutation flags.

Preflight after fetch:

```text
HEAD=7d118e812d59d76e1c3049a735d3522ab59e481c
ORIGIN=44a337e3cca07c8c984f6c3af0a702d7550628a5
STATUS_LINES=0
ANCESTOR=yes
```

Runtime sync:

```text
git merge --ff-only origin/main
HEAD=44a337e3cca07c8c984f6c3af0a702d7550628a5
STATUS_LINES=0
```

Runtime verification:

- bash syntax：PASS
- cron static：`7 passed`
- alpha/worklist：`95 passed`
- py_compile：PASS
- `git diff --check`：PASS

Demo-learning crontab expected-head replacement:

```text
line_count=70
old_count_before=10
old_count_after=0
new_count_before=0
new_count_after=10
probe0_after=1
probe1_after=0
```

E3 then approved a separate crontab-only durable alpha closure. Line 57 changed only by inserting `OPENCLAW_EXPECTED_SOURCE_HEAD=44a337e3...` after `OPENCLAW_DATA_DIR=/tmp/openclaw`.

Post-check:

```text
line_count=70
target_count_before=10
target_count_after=11
old_count_after=0
probe0_after=1
probe1_after=0
```

Cron-shape alpha refresh:

```text
OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv \
OPENCLAW_DATA_DIR=/tmp/openclaw \
OPENCLAW_EXPECTED_SOURCE_HEAD=44a337e3cca07c8c984f6c3af0a702d7550628a5 \
$HOME/BybitOpenClaw/srv/helper_scripts/cron/alpha_discovery_throughput_cron.sh
```

Result：`alpha_cron_shape_refresh=PASS`.

## Runtime Artifact Result

`/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`:

```text
created_at_utc=2026-06-24T14:52:50.300993+00:00
expected_head_status=MATCH
expected_head_matches=True
git_head=44a337e3cca07c8c984f6c3af0a702d7550628a5
git_status=SYNCED_CLEAN
ready_for_probe=1
operator_probe_review_ready_found=True
runtime_probe_authority_found=False
runtime_order_authority_found=False
promotion_evidence_found=False
cost_gate_mutation_found=False
actionable_probe_semantics=OPERATOR_REVIEW_READY_NO_RUNTIME_AUTHORITY
```

User-service sanity:

```text
systemctl --user is-active openclaw-trading-api.service -> active
systemctl --user is-enabled openclaw-trading-api.service -> enabled
MainPID=2218842
NRestarts=0
```

## Aggressive Profit Hypotheses

1. `MM low-friction motif distinct-date accumulation`
   - why it might make money：current-fee MM motif has a repeatable low-friction structure but lacks distinct-date confirmation.
   - fastest safe test：continue artifact-only accumulation for the same motif and require independent dates before review.
   - required data：fillsim history windows, maker/fill realism, current fee schedule.
   - failure condition：frontier gap remains above fee/cost wall or independent dates fail.
   - authority required：none for accumulation; candidate-scoped operator authorization only after review packet.
   - max safe next action：`accumulate_distinct_window_history_for_same_low_friction_motif`.
   - scores：upside 7, evidence 4, execution 5, cost 5, time 6, account risk 1, governance risk 1, autonomy value 8.

2. `False-negative bounded candidate clean-subset mining`
   - why it might make money：blocked Cost Gate side-cells may contain high-edge subsets after excluding unattributed/proof-ineligible fills.
   - fastest safe test：source-only ranking over proof-eligible rows with matched-control requirements.
   - required data：Cost Gate rejects, clean attributed demo fills, proof-exclusion ledger.
   - failure condition：net after fees/slippage becomes nonpositive or attribution is incomplete.
   - authority required：none for ranking; exact typed-confirm for any bounded Demo probe.
   - max safe next action：build review-only candidate packet.
   - scores：upside 8, evidence 5, execution 4, cost 4, time 5, account risk 1, governance risk 2, autonomy value 9.

3. `Maker placement repair before bounded probe`
   - why it might make money：shadow placement shows touchability mechanics can be improved before spending probe budget.
   - fastest safe test：artifact-only shadow placement impact with candidate-matched constraints.
   - required data：order-to-fill gap audit, BBO freshness, shadow placement impact, authority readiness packet.
   - failure condition：candidate-matched sample remains zero or queue slippage erases edge.
   - authority required：none for shadow; exact bounded authorization for real probe.
   - max safe next action：rerun shadow placement after candidate-matched flow.
   - scores：upside 6, evidence 5, execution 6, cost 6, time 4, account risk 1, governance risk 1, autonomy value 7.

## Boundary

No Bybit call/order/cancel/modify, no API POST, no PG read/write/schema migration, no service restart/daemon-reload/process signal, no Rust writer enablement, no Cost Gate lowering, no probe/order/live authority, and no promotion proof.
