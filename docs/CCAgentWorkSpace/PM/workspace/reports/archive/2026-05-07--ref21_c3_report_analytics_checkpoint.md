# REF-21 C3 Replay Report Analytics Checkpoint

## Scope

This checkpoint adds report-level analytics needed by later baseline/candidate
comparison and ML/Dream ranking. It reads only the immutable
`replay_report.json` payload already returned by `/api/v1/replay/report/*`.

## Implemented

- Added `replay/report_analytics.py`.
  - Computes fee-net bps from `pnl_summary.net_pnl / starting_balance`.
  - Counts positive fills, qty=0 ghost fills, maker misses, and risk rejects.
  - Computes total fee, gross notional, fee bps, q50 slippage, and a
    development-sandbox verdict.
  - Explicitly marks drawdown and run-band analytics as unavailable until a
    balance curve / bootstrap series exists.
- Wired `/api/v1/replay/report/{experiment_id}` to overlay
  `replay_result_analytics` into both artifact payload and `payload.result`.
- Updated Replay GUI report summary to show:
  - Net Bps,
  - Verdict,
  - Miss/Reject count.

## Verification

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/replay/report_analytics.py program_code/exchange_connectors/bybit_connector/control_api_v1/replay/report_route.py`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_report_analytics.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_replay_subtab_static_assets.py -q`
  - 46 passed.
- `git diff --check`

## Boundary

This is not yet baseline-vs-candidate comparison. The overlay intentionally
sets `baseline_comparison_status=not_configured` and does not emit promotion,
handoff, or live/demo mutation signals.
