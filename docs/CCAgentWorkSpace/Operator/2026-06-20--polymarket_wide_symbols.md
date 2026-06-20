# Polymarket Wide-Symbol Universe

v271 widens the Polymarket lead-lag IC lane from BTC/ETH to BTC/ETH/SOL/XRP by default. Same-data comparison shows this matters: BTC/ETH-only had 114 joined rows; BTC/ETH/SOL/XRP had 190 joined rows on the same 11285 snapshot rows.

Latest Linux v0.8 artifact is still `INSUFFICIENT_SAMPLE`: adjusted sample `11 / 30`, ETA to gate if cadence holds `2026-06-20T19:52:01.390Z`, candidate_count `0`.

There is one new diagnostic watch, `event_reg|XRPUSDT|60m`, but it has floor `2 / 30`; it is not a probe or promotion signal.

No trading change, no crontab reinstall, no restart. Boundary stayed artifact-only/read-only.
