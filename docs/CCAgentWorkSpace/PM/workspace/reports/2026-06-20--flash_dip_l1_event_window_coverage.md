# FlashDip L1 Event-Window Coverage

Date: 2026-06-20

## Summary

The prior L1 replay status could be misread because it reported broad symbol-level L1 rows. The latest live artifact has L1 rows for all candidate symbols, but none inside the actual candidate maker-entry windows. This checkpoint fixes that diagnostic gap and surfaces the L1 replay as an independent alpha-discovery arm.

## Changes

- Added event-window coverage fields to `shallow_retune_l1_short_exit_replay.py`:
  - `events_with_l1_in_event_window`
  - `events_missing_l1_in_event_window`
  - distinct day counts
  - `event_window_l1_rows_by_symbol_date`
  - missing event-window sample rows
- Added verdict reasons:
  - `no_l1_rows_for_candidate_event_windows`
  - `partial_l1_event_window_coverage`
- Added compact event-window fields to `flash_dip_l1_short_exit_replay_cron.sh` status JSONL.
- Added independent alpha-discovery arm `flash_dip_l1_short_exit_replay`.

## Runtime Evidence

Linux read-only wrapper smoke:

- Artifact: `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_l1_short_exit_replay_20260620T085948Z.json`
- SHA256: `417a4ee7b76191e1e8e2a3ac9a2285bc9fbd47558aabe8ae185115db0bf79c18`
- Verdict: `L1_SHORT_EXIT_INSUFFICIENT_SAMPLE`
- Fail reasons: `no_l1_rows_for_candidate_event_windows`, `gate_horizon_sample_below_min_filled`, `gate_horizon_sample_below_min_days`
- Candidate events: 6 across 2 days and 5 symbols
- Trades: 2,757,781
- Loaded L1 rows: 173,749
- Symbols missing L1: none
- Event windows with L1: 0
- Event windows missing L1: 6

Alpha-discovery smoke:

- Arm: `flash_dip_l1_short_exit_replay`
- Gate status: `CAPTURING`
- Action: `RUN_READ_ONLY_CAPTURE`
- Rank: 2
- Reason: `sample_count_below_gate`
- Sample count: 0

## Interpretation

This corrects the diagnosis from "L1 coverage exists, but no fills" to "L1 exists broadly, but not in the candidate event windows." The 240m short-exit path remains data-gated and is not disproven by queue/fill realism.

## Verification

- Mac: `test_tail_dislocation_shallow_retune.py` = 13 passed.
- Mac: `test_alpha_discovery_throughput.py` = 16 passed.
- Mac: `test_flash_dip_l1_short_exit_replay_cron_static.py` = 6 passed; cron bash syntax PASS.
- Mac: replay/runtime py_compile PASS.
- Linux: same focused pytest/py_compile checks PASS after selective sync.
- Linux: read-only wrapper smoke + alpha-discovery extraction PASS.

## Boundary

No engine/API restart, no rebuild, no strategy parameter change, no PG table write/schema migration, no Bybit private/signed/trading call, and no credential/auth/risk/order/trading mutation. This is not promotion proof.

## Next Trigger

Keep the daily replay cron running. A useful next state is candidate maker windows with actual L1 overlap, then measured queue fills and 240m exits. Only `L1_SHORT_EXIT_CONDITIONAL_PASS` with the configured sample gate can move to formal QC/MIT/AI-E review.
