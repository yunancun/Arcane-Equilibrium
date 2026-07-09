# E1 Report: WP-06 E5-P-2 + WP-08 MIT-DB-6 + MIT-P1-2

Date: 2026-05-16
Status: IMPL DONE, awaiting E2 review

## Task A: WP-06 E5-P-2 state_compiler deepcopy reduction

### Problem
`compile_state()` in state_compiler.py had 3 `copy.deepcopy` calls on every
non-cached compilation path, which is expensive on hot paths (every GUI read
and mutator response).

### Analysis
- Line 627: `return copy.deepcopy(_compile_cache)` -- cache hit path. NEEDED:
  multiple callers may mutate the returned dict.
- Line 630: `compiled = copy.deepcopy(state)` -- input protection. NEEDED:
  `_do_compile_core` mutates in-place; must protect caller's original dict.
- Line 635: `return copy.deepcopy(result)` -- output copy. ELIMINABLE:
  `result` is already a fresh deepcopy of input (from line 630). The caller
  receives it directly; we just need to store a separate copy in the cache.

### Fix
Reduced from 3 deepcopy to 2 by inverting the storage pattern:
- Caller receives `result` directly (already a fresh deepcopy from line 630)
- Cache stores `copy.deepcopy(result)` to protect against caller mutation
- Net effect: same safety guarantees, 1 fewer deepcopy on every cache-miss path

### Files Modified
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/state_compiler.py`
  (636 -> 642 LOC, under 800 warning line)

---

## Task B: WP-08 MIT-DB-6 Training SQL engine_mode fix

### Problem
`realized_edge_stats.py` SQL queries used `= %(engine_mode)s` single-value
equality. When callers pass `"demo"`, only rows with `engine_mode='demo'` are
found, missing `'live_demo'` rows. Per project memory: LiveDemo writes
`engine_mode='live_demo'`.

### Audit of all files
| File | Status | Notes |
|------|--------|-------|
| linucb_trainer.py | OK | Already uses `engine_mode_scope()` + `ANY(%s)` |
| run_training_pipeline.py | OK | Already uses `engine_mode_scope()` from parquet_etl |
| parquet_etl.py | OK | Already uses `engine_mode_scope()` + `ANY(...)` |
| mlde_shadow_advisor.py | OK | Already uses `_engine_mode_scope()` + `ANY(%s)` |
| **realized_edge_stats.py** | **FIXED** | Was `= %(engine_mode)s`, now `ANY(%(engine_modes)s)` |
| edge_estimate_validation.py | N/A | No SQL queries, pure math validation |
| james_stein_estimator.py | OK | Delegates to `compute_edge_stats()` which is now fixed |
| ml_training_maintenance.py:896 | OK | audit_engine_modes defaults to `"demo,live_demo"` |

### Fix
1. Added `_engine_mode_scope()` function in `realized_edge_stats.py` (consistent
   with the pattern in `linucb_trainer.py` and `parquet_etl.py`)
2. Changed `_FILLS_QUERY` and `_FUNDING_QUERY` from `= %(engine_mode)s` to
   `= ANY(%(engine_modes)s)`
3. Updated `compute_edge_stats()` to call `_engine_mode_scope(engine_mode)` and
   pass `engine_modes` list to SQL
4. Function signature unchanged -- callers unaffected

### Files Modified
- `program_code/ml_training/realized_edge_stats.py` (680 -> 694 LOC)

---

## Task C: WP-08 MIT-P1-2 Walk-forward purge gap

### Problem
`_walk_forward_oos_values()` in edge_estimate_validation.py had no purge gap
between the training window end and OOS test window start. Autocorrelated
return series can leak look-ahead information without a gap.

### Fix
1. Added `purge_days: int = 0` field to `ValidationConfig` (default 0 for
   backward compatibility)
2. Modified `_walk_forward_oos_values()` to insert `purge` timedelta between
   `train_end` and `test_start`
3. With `purge_days=0`, behavior is identical to before (no regression)
4. Callers can set `purge_days > 0` when needed for stricter validation

### Files Modified
- `program_code/ml_training/edge_estimate_validation.py` (241 -> 253 LOC)

---

## Test Results
- `test_realized_edge_stats_mode.py`: 12/12 PASS
- `test_unattributed_filter.py`: 7/7 PASS
- `test_edge_estimate_validation.py`: 2/2 PASS
- `test_learning_chapter.py`: 42/42 PASS
- AST parse: all 3 modified files PASS
- LOC: all under 800 warning line

## Governance
- No hard boundary changes (max_retries, live_execution_allowed, etc.)
- No new singletons
- Chinese-only comments for new code (per 2026-05-05 governance change)
- No scope expansion beyond PA task spec
