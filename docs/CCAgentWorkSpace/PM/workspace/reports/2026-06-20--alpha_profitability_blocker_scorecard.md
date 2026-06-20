# Alpha Profitability Blocker Scorecard

## Conclusion

v278 adds a cross-arm `profitability_blocker_scorecard` to alpha discovery. The intent is to stop treating "not profitable yet" as one opaque state. Every discovery arm now reports the primary blocker, secondary blockers where useful, and the next trigger.

Runtime answer: there is no actionable alpha or probe now. The dominant blocker is MM signal-family failure, not merely missing a hidden in-window filter. The rest of the system is split between sample gates, data coverage, event waits, robustness wait, and one rejected family.

## Implementation

- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - Adds `classify_profitability_blocker()`.
  - Adds `build_profitability_blocker_scorecard()`.
  - Adds the scorecard to every `build_discovery_plan()` result.
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - Mirrors `profitability_blocker_scorecard` at top-level in `alpha_discovery_latest.json`.
  - Passes MM `fee_path_feasibility` into arm detail.
- `helper_scripts/research/tests/test_alpha_discovery_throughput.py`
  - Covers ready/rejected semantics, runtime multi-arm blocker classification, MM secondary blockers, and runtime artifact passthrough.

The scorecard is additive. It does not change action decisions, sampling gates, promotion gates, strategy parameters, order behavior, or runtime authority.

## Runtime Evidence

- Artifact: `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`
- Sha256: `64a04a70f674042a426c7f31f584a0f15345e773dfc6c9caab2ff515d781a869`
- Created: `2026-06-20T17:02:16.424355+00:00`
- Killboard: `ready_for_aeg_chain=0`, `ready_for_probe=0`, `run_read_only_capture=4`, `wait=2`, `block=1`
- Scorecard status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`

Blocker counts:

- `feature_family_no_edge=1`
- `sample_gate=1`
- `data_coverage=1`
- `event_wait=2`
- `robustness_wait=1`
- `rejected_no_edge=1`

Top blockers:

- `mm_verdict_maker_edge`: `feature_family_no_edge`, primary `no_train_positive_walk_forward_feature_cell`, sample_count 16.
  - Secondary cost wall: best symbol `ARBUSDT`, fee round-trip shortfall `0.0357bp`.
  - Secondary fee/scale path: break-even maker fee `1.135bp/side`, fee reduction needed `0.865bp/side`, first clearing standard tier VIP5.
- `polymarket_leadlag_ic`: `sample_gate`, adjusted sample_count 18/30, ETA `2026-06-20T19:52:03.067000+00:00`.
- `flash_dip_l1_short_exit_replay`: `data_coverage`, primary `candidate_window_before_symbol_l1_range`.

Other rows:

- `flash_dip_buy_demo`: `event_wait`, configured flash-dip limit not touchable.
- `gate_b_listing_fade`: `event_wait`, `WATCH_ONLY`.
- `aeg_robustness_matrix`: `robustness_wait`, no durable AEG candidate rows.
- `vol_event_order_flow`: `rejected_no_edge`, `NO_EDGE_SURVIVES`.

## PM Read

This changes the search process. The next profitable path should not spend another cycle on the same MM threshold family unless one of these changes:

- fee/rebate path becomes real enough to evaluate beyond a capacity proxy;
- a materially new MM signal family is introduced;
- a fresh fill_sim window shows a different primary blocker.

Near-term alpha-search priority:

- Polymarket: wait for the 18/30 sample gate to mature, then rerun HAC/BH/partial-control gate. If it survives, it becomes the next AEG-chain candidate path.
- FlashDip: short-exit path remains data-gated; the next useful evidence is a candidate maker window with continuous L1 overlap, not a parameter change.
- Gate-B: still event-waiting for a fresh actionable listing/prelaunch alert.
- Vol-event: current family is rejected until new evidence changes `NO_EDGE_SURVIVES`.

## Verification

- Mac focused suite: `49 passed`
- Linux focused suite: `49 passed`
- Mac and Linux `py_compile`: passed
- Mac and Linux diff-check: passed
- Linux manual artifact-only cron refresh: passed

Boundary: source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact write only. No PG table write, schema migration, Bybit private/signed/trading call, engine/API restart, credential/auth/risk/order/strategy mutation, or promotion proof.
