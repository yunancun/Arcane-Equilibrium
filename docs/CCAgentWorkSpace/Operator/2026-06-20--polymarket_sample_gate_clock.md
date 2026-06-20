# Polymarket Sample-Gate Clock

v270 adds `sample_gate_eta_utc` for the Polymarket lead-lag IC lane. Latest Linux v0.7 artifact is still `INSUFFICIENT_SAMPLE`: adjusted sample `10 / 30`, ETA to gate if cadence holds `2026-06-20T19:52:03.862Z`.

The key finding is negative but useful: the prior v269 pre-gate watch did not persist. `pre_gate_hac_watchlist_count` is now 0, and the old `other|BTCUSDT|15m` watch decayed to HAC t≈0.401 / q≈0.765 after the 10th sample.

No promotion, no probe, no trading change. Boundary stayed artifact-only/read-only.
