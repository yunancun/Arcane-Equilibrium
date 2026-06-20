# FlashDip L1 Timing-Relation Diagnostics

Date: 2026-06-20

## Summary

v248 proved that broad symbol-level L1 rows are not enough; this checkpoint explains why the current event-window replay still has 0 covered windows. The missing maker windows are all before each candidate symbol's loaded L1 range, so the short-exit path remains data-gated rather than rejected by queue/fill realism.

## Changes

- Bumped `shallow_retune_l1_short_exit_replay.py` artifact version to `v0.2`.
- Added per-candidate event-window timing diagnostics:
  - `event_window_l1_relation_counts`
  - `event_window_l1_relation_by_symbol_date`
  - per-symbol loaded L1 first/last timestamps
  - missing-window `window_start_ts`, `window_end_ts`, `l1_relation`, and `l1_gap_hours`
- Added compact cron/runtime fields:
  - `event_window_l1_relation_counts`
  - `dominant_missing_event_window_l1_relation`
- Preserved the fields in alpha-discovery `flash_dip_l1_short_exit_replay` detail.

## Runtime Evidence

Linux read-only replay:

- Artifact: `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_l1_short_exit_replay_20260620T110856Z.json`
- Latest SHA256: `43992d40987e61a737b109721b4f079347bddb382fa71c69631cae3a19c75afd`
- Version: `tail_dislocation_meanrev.shallow_retune_l1_short_exit_replay.v0.2`
- Generated: `2026-06-20T11:09:06.045084+00:00`
- Verdict: `L1_SHORT_EXIT_INSUFFICIENT_SAMPLE`
- Fail reasons: `no_l1_rows_for_candidate_event_windows`, `gate_horizon_sample_below_min_filled`, `gate_horizon_sample_below_min_days`
- Candidate events: 6 across 2 days and 5 symbols
- Loaded L1 rows: 173,749
- Trades: 2,757,781
- Event windows with L1: 0
- Event windows missing L1: 6
- Relation counts: `candidate_window_before_symbol_l1_range=6`
- Loaded L1 range: `2026-06-20T00:18:11.624Z` to `2026-06-20T03:59:59.804Z`

Alpha discovery refreshed at `2026-06-20T11:09:22.028600+00:00` and preserves:

- `flash_dip_l1_short_exit_replay.gate_status=CAPTURING`
- `sample_count=0`
- `dominant_missing_event_window_l1_relation=candidate_window_before_symbol_l1_range`
- Killboard remains `ready_for_probe=0`, `ready_for_aeg_chain=0`, `run_read_only_capture=3`, `wait=1`, `block=2`.

## Interpretation

The useful correction is timing, not strategy promotion. For the 2026-06-18 candidate windows, symbol L1 starts about 24.3 hours after the maker window ended. For the 2026-06-19 candidate windows, symbol L1 starts about 18.2 minutes after the maker timeout ended. This matches the L1 recorder repair timeline: L1 recording restarted after the relevant maker-entry windows had already started or ended.

The next real test is a future K6/N2/C3/nf0.5% candidate whose maker window overlaps continuous recorder L1 from the start of the UTC day.

## Verification

- Local: `PYTHONPATH=helper_scripts/research/tail_dislocation_meanrev:helper_scripts/research python3 -m pytest -q --import-mode=importlib helper_scripts/research/tests/test_tail_dislocation_shallow_retune.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/cron/tests/test_flash_dip_l1_short_exit_replay_cron_static.py` = 36 passed.
- Local: `bash -n helper_scripts/cron/flash_dip_l1_short_exit_replay_cron.sh` PASS.
- Local: replay/runtime `py_compile` PASS.
- Local: `git diff --check` PASS.
- Linux selective sync: same 36 focused tests PASS.
- Linux: cron bash syntax and replay/runtime `py_compile` PASS.
- Linux: 6 synced source/test files match local SHA256.
- Linux: manual read-only replay wrapper and alpha-discovery refresh PASS.

## Boundary

Source/test/docs plus selective Linux source sync and local `/tmp/openclaw` research/status artifacts only. No engine/API restart, no rebuild, no strategy parameter change, no PG table write/schema migration, no Bybit private/signed/trading call, and no credential/auth/risk/order/trading mutation. This is not promotion proof.
