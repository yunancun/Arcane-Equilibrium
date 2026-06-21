# Cost-Gate Price Observation Builder

## PM Verdict

Implemented a source-only improvement to the cost-gate demo-learning lane feedback loop.

This does not lower the main Cost Gate. It makes the blocked-signal learning loop less manual: recorded rejects can now be mapped to the exact local market observation windows needed before `runtime_adapter --record-blocked-outcomes` appends `blocked_signal_outcome` rows.

## Why This Matters

The previous state had the right ledger and outcome row type, but local price observations still had to be hand-assembled. That is a shallow seam: the caller had to know which attempts were missing outcomes, which horizon window to slice, which symbols mattered, and which rows were already labeled.

The new Module concentrates that logic:

- ledger admission rows -> required price observation windows
- local price/kline rows -> normalized observations
- JSON/JSONL artifact -> directly consumable by the existing outcome writer

This improves locality and gives us a clear future Adapter slot for read-only PG extraction without mixing database access into `runtime_adapter.py`.

## Changed

- Added `helper_scripts/research/cost_gate_learning_lane/price_observations.py`.
- Default behavior targets recorded but not order-authorized rejects that still need `blocked_signal_outcome`.
- Already labeled attempts are skipped by target outcome record type.
- `--include-admitted` can opt into admitted probe windows for `probe_outcome`.
- JSON output preserves both `windows` and `observations`.
- JSONL output writes observations only, matching `runtime_adapter --price-observations`.
- Updated alpha-discovery admission-only next trigger to `build_price_observations_then_record_blocked_signal_outcomes`.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` -> 18 passed.
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> 34 passed.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/price_observations.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py` -> passed.
- `PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.price_observations --help` -> passed.
- `git diff --check` -> passed.

## Boundary

- No PG table write or schema migration.
- No Bybit private, signed, or trading call.
- No engine/API rebuild, restart, deploy, or runtime flag change.
- No credential, authorization, risk, order, strategy, or config mutation.
- Not signal proof, execution proof, promotion proof, or Cost Gate relaxation.

## Next

After the runtime ledger writer is deployed/enabled and `probe_admission_decision` rows exist, run the price observation builder against a local price/kline export, then run `runtime_adapter --record-blocked-outcomes`. If blocked outcomes repeatedly show positive net bps in selected side-cells, the next review should be side-cell-specific demo probe authority, not global Cost Gate lowering.
