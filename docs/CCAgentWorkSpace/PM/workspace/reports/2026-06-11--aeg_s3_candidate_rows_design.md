# PM Report — AEG-S3 Candidate Direct Rows Design

Date: 2026-06-11
Role: PM(default)
Scope: AEG-S3 candidate interface design before implementation.
Mode: design only. No runtime deploy, DB write, auth change, strategy enablement, or trading action.

## Verdict

Proceed with a narrow AEG-S3 infrastructure slice:

1. Add a generic artifact-only builder that converts candidate-owned independent sample returns into a direct `candidate_regime_metrics` block.
2. Feed that block through the existing `aeg_candidate_metrics` adapter and `aeg_robustness_matrix`.
3. Do not implement listing collector runtime, production scanner linkage, order path, or promotion scoring.

This is the correct next code-bearing step because `AEG-S2` is green enough to consume candidate metrics, while current candidate reports still lack true matrix-ready direct rows.

## Claude Workflow Sync Check

Before this design, PM checked the Claude-side memory / sub-agent workflow updates visible in the current Mac worktree.

Facts:

- `.claude/agents/PM.md` now includes the four-state sub-agent contract: `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, `BLOCKED`.
- `.claude/workflows/agent-wave.js` now appends the four-state footer, supports `contextPath`, and returns a `statuses` index.
- `.codex/MEMORY.md` mirrors Claude Code hook / rtk hints.
- `.codex/SUBAGENT_EXECUTION_RULES.md` mirrors the four-state completion contract.
- `.claude/settings.json` and `.claude/hooks/*` exist locally for Claude Code hooks, but they are uncommitted.
- These changes are visible to this Codex session from the filesystem, but they are not a clean committed checkpoint and are not currently active as Codex `exec_command` hooks.

PM implication:

- Use the four-state contract in future real sub-agent prompts.
- Do not rely on rtk-compressed output in this Codex tool path.
- Do not touch or mix the dirty Claude workflow batch with AEG-S3 implementation commits.

## Problem

Existing AEG infrastructure already has the downstream shape:

- `helper_scripts/research/aeg_candidate_metrics/` accepts direct `candidate_regime_metrics` blocks.
- `helper_scripts/research/aeg_robustness_matrix/` consumes `candidate_regime_metrics.csv` and fails closed on missing matrix-critical fields.
- L2 P3b design already identified a gap: AEG-S3 candidate sources do not yet emit daily/sample return series, and scalar rows alone are not enough for beta-neutral or falsification checks.

The dangerous shortcut is to synthesize a return series from `mean_daily_bps`. That would create constant returns and can fake beta neutrality. This is prohibited.

## Design Target

Create a small package:

```text
helper_scripts/research/aeg_s3_candidate_rows/
  __init__.py
  builder.py
  artifact.py
  harness.py
helper_scripts/research/tests/test_aeg_s3_candidate_rows.py
```

Update `helper_scripts/SCRIPT_INDEX.md`.

### Input Contract

The package consumes a candidate evidence JSON with explicit sample returns:

```json
{
  "candidate_id": "listing_fade_v0",
  "strategy_family": "listing_fade",
  "parameter_cell_id": "v0",
  "selected_variant": "fade_after_pump_500bps",
  "k_trials": 8,
  "annualization_factor": 365,
  "samples": [
    {
      "sample_id": "2026-06-11:SYMBOL:window0",
      "sample_ts_utc": "2026-06-11T00:00:00Z",
      "regime": "chop",
      "independence_bucket": "2026-06-11",
      "gross_bps": 8.0,
      "cost_bps": 2.0,
      "net_bps": 6.0,
      "is_oos": true
    }
  ],
  "daily_returns": {
    "unit": "fraction",
    "values": {"2026-06-11": 0.0006}
  },
  "pbo_candidates": {
    "cell_a": {"2026-06-11": 0.0006}
  }
}
```

Rules:

- `samples` are the candidate-defined independent economic samples. For listing fade this is an event/window. For multiday/funding candidates this is a non-overlapping holding window or another candidate-declared independent unit.
- `net_bps` is the mean of explicit sample-level net bps, not a substitute for `mean_daily_bps`.
- `mean_daily_bps` is computed only from `daily_returns` when present.
- `n_independent` is computed from unique `independence_bucket` values, not from row count and not from symbol count.
- `daily_returns` is optional. Missing daily returns means L2/B1 may defer; it must not be fabricated.
- `pbo_candidates` is optional. Missing or insufficient PBO input leaves `pbo=None`, causing downstream fail-closed.

### Output Contract

The package writes an intermediate direct report:

```text
candidate_direct_metrics_report.json
candidate_sample_returns.csv
candidate_daily_returns.json
manifest.json
artifact_index.json
```

`candidate_direct_metrics_report.json` contains top-level `candidate_regime_metrics`, so it can be passed unchanged to:

```bash
python3 -m aeg_candidate_metrics.harness \
  --diagnostic-report-json candidate_direct_metrics_report.json \
  ...
```

Per regime row fields match the existing adapter contract:

- `regime`
- `n_days`
- `gross_bps`
- `cost_bps`
- `net_bps`
- `net_to_cost_ratio`
- `mean_daily_bps`
- `annualized_net_sharpe`
- `oos_sharpe`
- `psr_0`
- `dsr_k`
- `pbo`
- `k_trials`
- `n_independent`
- `sample_unit`
- `recent_90d_net_bps`
- `recent_180d_net_bps`

### Statistics

Use existing `helper_scripts/lib/stats_common.py` where possible:

- `psr_bailey_ldp(values, 0.0)` on sample net returns in fraction units.
- `dsr_with_k(values, k_trials)` on the same sample series.
- `pbo_cscv(pbo_candidates, seed=...)` only when candidate cells and days are sufficient.

Compute internally:

- mean gross/cost/net bps per explicit sample unit.
- `net_to_cost_ratio = mean_net_bps / mean_cost_bps` when cost is positive.
- annualized Sharpe only when `annualization_factor` is explicit and there are enough sample returns.
- OOS Sharpe only from samples marked `is_oos=true`; otherwise `None`.
- recent 90d / 180d mean net bps from sample timestamps relative to max sample timestamp.

### Fail-Closed Behavior

The builder must not raise a false PASS when evidence is missing.

Examples:

- no `independence_bucket` -> `n_independent=None`
- no `daily_returns` -> `mean_daily_bps=None`
- no `is_oos` samples -> `oos_sharpe=None`
- no `pbo_candidates` or insufficient cells -> `pbo=None`
- non-finite sample value -> sample rejected and listed in summary
- aggregate-only regime -> output rows still possible, but matrix will not promote aggregate rows

### Candidate Mapping

Initial implementation should be candidate-agnostic. Candidate-specific producers come after:

1. `listing_fade`: blocked on Gate-B 24h true capture or future production capture evidence. The builder can support it, but cannot create true listing rows without data.
2. `oi_delta`: can be wired after PA/QC/MIT define the sample unit and source series.
3. `funding_revive`: can reuse funding history only after QC defines a materially new hypothesis; closed funding-tilt must not be silently reopened.
4. `multiday_trend` / `funding_tilt`: may be used as regression fixtures or dead-mode diagnostics, not promotion candidates unless a future hypothesis materially changes.

## Implementation Slice

Implement only `AEG-S3 candidate rows v0.1`:

- new generic package + tests
- SCRIPT_INDEX entry
- no DB access
- no runtime import from `control_api_v1`
- no Bybit API call
- no mutation of existing dead candidate verdicts

Suggested local command:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts \
  python3 -m pytest helper_scripts/research/tests/test_aeg_s3_candidate_rows.py \
  helper_scripts/research/tests/test_aeg_candidate_metrics.py -q
```

## Acceptance Criteria

1. Synthetic candidate evidence with complete fields produces direct rows that pass `aeg_candidate_metrics` adapter.
2. Missing `daily_returns` does not synthesize `mean_daily_bps`.
3. Missing `independence_bucket` does not use row count as `n_independent`.
4. Missing PBO inputs produces `pbo=None` and downstream fail-closed reasons.
5. Recent 90d / 180d windows are computed from sample timestamps.
6. No forbidden runtime/DB/trading tokens appear in the new package.
7. Existing `aeg_candidate_metrics` tests stay green.

## Dispatch Chain

Normal chain for code-bearing work should be:

```text
PM -> PA/QC/MIT local design read -> E1 implementation -> E2 review -> E4 tests -> PM
```

In this Codex run, sub-agent spawning is available only if explicitly requested by the operator. If PM implements locally, final sign-off must be honest: it is a local implementation plus local verification, not independent E2/E4 sign-off.

