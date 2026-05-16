# MIT-AC-19 Close-Maker Stratification Plan

**Reviewer**: MIT(default)  
**Date**: 2026-05-16  
**Scope**: C-2 / MIT-AC-19 stratification for close-maker healthcheck SQL  
**Verdict**: **BLOCKED-BY-B3** — report-only branch; close-maker healthcheck implementation files are absent.

## 1. Race / Repo State

- Repo root used: `/Users/ncyu/Projects/TradeBot/srv`.
- PM pre-dispatch state from prompt accepted: local `main` aligned with `origin/main` at `abaa4de7`.
- At MIT execution time, the worktree had a pre-existing unrelated dirty file: `.claude/agents/E3.md`. MIT did not inspect, stage, revert, stash, or edit it. PM later committed that C-1 guard separately as `197ca14d`.
- `helper_scripts/db/passive_wait_healthcheck/checks_close_maker_*.py` does **not** exist.
- Existing code already uses `[65]` for `chain_integrity_post_audit_4b_m3` in `helper_scripts/db/passive_wait_healthcheck/runner.py`. B-3 must resolve the healthcheck slot collision before registering literal `[65] close_maker_reject_samples`.

## 2. Required Source Alignment

Read / checked:

- `AGENTS.md`, `CLAUDE.md`, `TODO.md`, `.codex/MEMORY.md`
- `.codex/agents/MIT.md`, `.claude/agents/MIT.md`, MIT profile/memory/latest report index
- `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-15--amd_v0_3_spec_v1_2_v094_mit_short_re_review.md`
- `docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`
- `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- Current passive healthcheck runner/modules.

Relevant governing facts:

- V094 close-maker schema is a hybrid contract: `trading.fills.close_maker_attempt BOOLEAN NOT NULL DEFAULT FALSE`, `trading.fills.close_maker_fallback_reason TEXT NULL`, plus audit JSONB keys in `trading.fills.details`.
- `[62] close_maker_fill_rate` is a Wilson-CI/sample-size healthcheck. Existing spec gates remain per strategy / exit reason; MIT-AC-19 adds only a supplementary strategy x symbol breakdown.
- `[65] close_maker_reject_samples` is a BB-MF-5 / AC-15 reject sample coverage healthcheck. MIT-AC-19 adds only a supplementary strategy x symbol breakdown.
- The supplementary report is **non-normative** and **not a deployment gate**. It must not change PASS/WARN/FAIL semantics by itself.

## 3. BLOCKED-BY-B3 Reason

B-3 close-maker healthcheck files are not present, so there is no safe narrow patch target under the user-owned scope:

- Expected module does not exist: `helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py` or equivalent `checks_close_maker_*.py`.
- Expected functions do not exist:
  - `check_close_maker_fill_rate`
  - `check_close_maker_reject_samples`
- The actual runner still maps `[65]` to an older W-AUDIT-4b chain-integrity check, so adding a close-maker `[65]` in this MIT task would require runner/ID governance outside the allowed file scope.

Therefore MIT should not fabricate placeholder code. The correct deliverable is this ready-to-apply patch plan for B-3.

## 4. Expected B-3 Insertion Points

After B-3 creates the close-maker healthcheck module, add MIT-AC-19 at these exact points:

1. In `helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py`, near shared helpers:
   - add `_wilson_bounds(successes: int, total: int, z: float = 1.96) -> tuple[float, float]` if B-3 has not already added it;
   - add `_format_stratified_cells(rows, max_cells: int = 8) -> str` for compact message output;
   - keep both helpers private to the close-maker module.

2. In `check_close_maker_fill_rate`, after the existing normative query/verdict:
   - run an additional per-strategy x per-symbol query;
   - append the weakest cells to the message;
   - do **not** let per-symbol cells independently fail the check unless B-3/PM later makes that normative.

3. In `check_close_maker_reject_samples`, after the existing per-env category query:
   - run an additional per-strategy x per-symbol category query;
   - append missing or sparse categories to the message;
   - do **not** make a zero-count symbol cell a deployment blocker by itself.

4. In `helper_scripts/db/passive_wait_healthcheck/runner.py`, B-3/PM must resolve the existing `[65]` collision before registration. MIT recommends either:
   - allocate a new close-maker slot and update V094/spec references, or
   - migrate the existing W-AUDIT-4b `[65]` chain-integrity check to a non-conflicting ID through PM governance.

## 5. SQL Contract For `[62]` Supplement

Use actual V094 schema names, not prose aliases:

- timestamp column: `trading.fills.ts`
- mode column: `trading.fills.engine_mode`
- strategy column: `trading.fills.strategy_name`
- symbol column: `trading.fills.symbol`
- attempt flag: `trading.fills.close_maker_attempt`
- fallback reason: `trading.fills.close_maker_fallback_reason`
- optional exit reason: `trading.fills.details->>'close_maker_eligible_reason'`

Recommended supplementary SQL:

```sql
WITH cells AS (
    SELECT
        engine_mode,
        COALESCE(NULLIF(strategy_name, ''), 'unknown') AS strategy_name,
        symbol,
        COUNT(*) AS attempts,
        COUNT(*) FILTER (WHERE close_maker_fallback_reason IS NULL) AS maker_fills,
        COUNT(*) FILTER (WHERE close_maker_fallback_reason IS NOT NULL) AS fallbacks
    FROM trading.fills
    WHERE ts > NOW() - INTERVAL '7 days'
      AND engine_mode IN ('demo', 'live_demo', 'live')
      AND close_maker_attempt = TRUE
    GROUP BY 1, 2, 3
)
SELECT
    engine_mode,
    strategy_name,
    symbol,
    attempts,
    maker_fills,
    fallbacks,
    maker_fills::float8 / NULLIF(attempts, 0) AS fill_rate,
    (
      ((maker_fills::float8 / attempts) + (1.96 * 1.96) / (2 * attempts)
       - 1.96 * sqrt((((maker_fills::float8 / attempts) * (1 - (maker_fills::float8 / attempts)))
                      + (1.96 * 1.96) / (4 * attempts)) / attempts))
      / (1 + (1.96 * 1.96) / attempts)
    ) AS wilson_lower,
    (
      ((maker_fills::float8 / attempts) + (1.96 * 1.96) / (2 * attempts)
       + 1.96 * sqrt((((maker_fills::float8 / attempts) * (1 - (maker_fills::float8 / attempts)))
                      + (1.96 * 1.96) / (4 * attempts)) / attempts))
      / (1 + (1.96 * 1.96) / attempts)
    ) AS wilson_upper,
    CASE
      WHEN attempts < 30 THEN 'NEUTRAL_LOW_SAMPLE'
      WHEN (
        ((maker_fills::float8 / attempts) + (1.96 * 1.96) / (2 * attempts)
         - 1.96 * sqrt((((maker_fills::float8 / attempts) * (1 - (maker_fills::float8 / attempts)))
                        + (1.96 * 1.96) / (4 * attempts)) / attempts))
        / (1 + (1.96 * 1.96) / attempts)
      ) >= 0.60 THEN 'PASS_CELL'
      WHEN (
        ((maker_fills::float8 / attempts) + (1.96 * 1.96) / (2 * attempts)
         + 1.96 * sqrt((((maker_fills::float8 / attempts) * (1 - (maker_fills::float8 / attempts)))
                        + (1.96 * 1.96) / (4 * attempts)) / attempts))
        / (1 + (1.96 * 1.96) / attempts)
      ) < 0.40 THEN 'FAIL_CELL_DIAGNOSTIC'
      ELSE 'WARN_CELL_DIAGNOSTIC'
    END AS diagnostic_cell_status
FROM cells
ORDER BY
    CASE WHEN attempts >= 30 THEN 0 ELSE 1 END,
    wilson_lower NULLS FIRST,
    attempts DESC,
    engine_mode,
    strategy_name,
    symbol;
```

Implementation note: this query is supplementary. It should produce message text such as:

```text
stratified_weak_cells=demo/grid_trading/1000PEPEUSDT n=42 fill=0.214 wilson_low=0.113 status=WARN_CELL_DIAGNOSTIC; ...
```

## 6. SQL Contract For `[65]` Supplement

Reject sample stratification must use the same source table and window as the B-3 base check. If B-3 stores raw Bybit reject codes in `details`, prefer those codes; otherwise map the V094 fallback enum to the AC-15 categories.

Recommended category mapping:

- `postonly_will_take`: `close_maker_fallback_reason = 'postonly_reject'` or `details->>'reject_reason' = 'EC_PostOnlyWillTakeLiquidity'`
- `reach_max_pending`: `close_maker_fallback_reason IN ('rate_limit_pause', 'rate_limit_pause_global', 'rate_limit_backoff_per_symbol')` or `details->>'reject_reason' = 'EC_ReachMaxPendingOrders'`
- `other_reject_or_fallback`: any other non-null fallback reason not in safety-only categories

Recommended supplementary SQL:

```sql
WITH reject_events AS (
    SELECT
        engine_mode,
        COALESCE(NULLIF(strategy_name, ''), 'unknown') AS strategy_name,
        symbol,
        CASE
          WHEN close_maker_fallback_reason = 'postonly_reject'
            OR details->>'reject_reason' = 'EC_PostOnlyWillTakeLiquidity'
          THEN 'postonly_will_take'
          WHEN close_maker_fallback_reason IN (
              'rate_limit_pause',
              'rate_limit_pause_global',
              'rate_limit_backoff_per_symbol'
            )
            OR details->>'reject_reason' = 'EC_ReachMaxPendingOrders'
          THEN 'reach_max_pending'
          WHEN close_maker_fallback_reason IS NOT NULL
            AND close_maker_fallback_reason NOT IN (
              'fast_escalate_safety_upgrade',
              'not_attempted_safety_path',
              'engine_shutdown_safety'
            )
          THEN 'other_reject_or_fallback'
          ELSE NULL
        END AS reject_category
    FROM trading.fills
    WHERE ts > NOW() - INTERVAL '7 days'
      AND engine_mode IN ('demo', 'live_demo', 'live')
      AND close_maker_attempt = TRUE
)
SELECT
    engine_mode,
    strategy_name,
    symbol,
    COUNT(*) FILTER (WHERE reject_category = 'postonly_will_take') AS postonly_will_take,
    COUNT(*) FILTER (WHERE reject_category = 'reach_max_pending') AS reach_max_pending,
    COUNT(*) FILTER (WHERE reject_category = 'other_reject_or_fallback') AS other_reject_or_fallback,
    COUNT(*) FILTER (WHERE reject_category IS NOT NULL) AS total_reject_or_fallback_samples
FROM reject_events
GROUP BY 1, 2, 3
HAVING COUNT(*) FILTER (WHERE reject_category IS NOT NULL) > 0
ORDER BY
    total_reject_or_fallback_samples DESC,
    engine_mode,
    strategy_name,
    symbol;
```

Message output should include both global/env category verdicts from the normative B-3 check and a compact cell drill-down:

```text
reject_samples_by_cell=demo/grid_trading/BTCUSDT postonly=2 max_pending=1 other=0; demo/bb_breakout/1000BONKUSDT postonly=0 max_pending=1 other=3
```

## 7. Data-Rigor Requirements

- Do not use `env` or `created_at` unless B-3 proves those columns exist on the runtime table. Current V094 contract is `engine_mode` and `ts`.
- Do not count pre-V094 rows with default `close_maker_attempt = FALSE` as denominator rows.
- Do not treat `close_maker_fallback_reason IS NULL` as a reject sample. In the V094 contract, NULL means maker success when `close_maker_attempt = TRUE`.
- Do not send any close-maker audit fields to ML training, replay simulated fills, or agent spine tables. MIT short re-review already classified these fields as ops audit metadata only.
- Per-symbol output is diagnostic. It can drive human investigation and future PM tickets, but it must not silently become a hard deployment gate.

## 8. Ready Patch Plan For B-3

Once B-3 exists, MIT recommends this exact narrow diff:

1. Patch only `helper_scripts/db/passive_wait_healthcheck/checks_close_maker_*.py`.
2. Add `_wilson_bounds` if missing.
3. Add `_fetch_close_maker_fill_rate_cells(cur, window='7 days')`.
4. Add `_fetch_close_maker_reject_sample_cells(cur, window='7 days')`.
5. In `[62]`, append `stratified_weak_cells=...` to the existing message.
6. In `[65]`, append `reject_samples_by_cell=...` to the existing message.
7. Add targeted tests only if B-3 already has a close-maker healthcheck test file; otherwise leave test ownership with B-3.

Expected implementation size: 60-110 LOC inside the close-maker healthcheck module, no schema changes, no runtime config changes, no risk/TOML changes, no Rust changes.

## 9. Dependency Status

- **B-3 healthcheck module**: missing, blocks code patch.
- **V094 schema/writer implementation**: spec-final, but not assumed implemented by this report.
- **Healthcheck `[65]` slot**: conflict in current runner, requires PM/B-3 resolution before literal close-maker `[65]` registration.
- **MIT-AC-19**: ready for implementation as a supplementary non-gate drill-down after B-3 lands.

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-16--mit_ac_19_close_maker_stratification_plan.md
