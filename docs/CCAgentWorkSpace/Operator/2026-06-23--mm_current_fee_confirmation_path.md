# 2026-06-23 MM Current-Fee Confirmation Path

## 結論

本次修復的是盈利閉環裡的 evidence-routing gap：fill_sim/history/alpha 已經保存了 sample-gated current-fee-positive MM cell，但 profitability scorecard 沒有把它作為一條可追蹤的盈利候選路徑浮出。

現在 `alpha_profitability_path_scorecard_v1` 會輸出 `mm_current_fee_cell_confirmation`，路徑類別為 `mm_current_fee_confirmation`。它是明確的 Cost Gate crossing lead，但不是 promotion proof，也不授予 probe/order authority。

## Runtime Evidence

- Runtime source：`SYNCED_CLEAN b0b803ea`
- Latest profitability artifact：`/tmp/openclaw/alpha_discovery_throughput/profitability_path_scorecard_latest.json`
- Generated：`2026-06-23T17:58:25.268154+00:00`
- Scorecard status：`PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING`
- Global Cost Gate lowering：`false`
- Main Cost Gate adjustment：`NONE`
- Order authority：`false`
- Promotion evidence：`false`
- Primary root blocker：`demo_learning_stack_operator_apply_required`

MM confirmation path:

- Rank：`3`
- Candidate：`edge_scorecard|per_symbol_primary_queue|SOXLUSDT|back|informed_skip|fill_only`
- Gross edge：`4.715bps`
- Current round-trip fee：`4.0bps`
- Net cushion：`0.715bps`
- Sample：`43`
- Break-even maker fee：`2.357bp/side`
- History status：`HISTORY_SINGLE_WINDOW_CURRENT_FEE_POSITIVE_NEEDS_CONFIRMATION`
- Current-fee positive windows：`1`
- Repeated positive keys：`0`
- Next action：`confirm_mm_current_fee_positive_cell_across_independent_windows_before_any_authority`

## Source Changes

- Added extraction and ranking for current-fee-positive MM cells in `helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py`.
- Added status ranks:
  - `MM_REPEATED_CURRENT_FEE_POSITIVE_NEEDS_EXECUTION_REALISM`
  - `MM_CURRENT_FEE_REPEAT_NEEDS_OOS`
  - `MM_SINGLE_WINDOW_CURRENT_FEE_POSITIVE_NEEDS_CONFIRMATION`
- Added same-key evidence enrichment so maker-fee/history break-even fields are preserved even when the selected positive-net cell comes from `edge_scorecard`.
- Added focused regression coverage in `helper_scripts/research/tests/test_profitability_path_scorecard.py`.

## Verification

- Mac：`PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py` -> `92 passed`
- Mac：`python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py helper_scripts/research/tests/test_profitability_path_scorecard.py` -> pass
- Mac：`git diff --check` -> pass
- Linux：same related pytest suite -> `92 passed`
- Linux：artifact-only `alpha_discovery_throughput_cron.sh` refresh -> pass
- Mac/origin/Linux source all clean at `b0b803ea`

## Boundary

No CI run. No PG write/schema migration. No Bybit private/signed/trading call. No deploy/rebuild/restart. No crontab install. No env/auth/risk/order/strategy mutation. No global Cost Gate lowering. No probe/order authority. No actual order. No promotion proof.

## Next Gate

The MM path needs independent-window repeat, OOS/walk-forward confirmation, inventory-risk review, and maker execution-realism proof. The broader system blocker remains operator review/apply of the demo-learning stack so rejected signals, matched controls, fills, fees, slippage, and execution-realism evidence can accumulate continuously.
