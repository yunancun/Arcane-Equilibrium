# Live/Demo PnL Series Refresh Fix

Date: 2026-05-10

- PnL table now falls back to recent fills (`limit=200`) when the running backend has not loaded the new `/pnl-series` route yet.
- Refresh no longer clears existing Demo/Live panels back to loading on every poll.
- Performance Metrics avoid redundant same-HTML replacement, reducing visible flicker.
- Live Today PnL is preserved during transient metrics fetch failure instead of flashing to `--`.
- Verified with targeted static/Python tests, JS parse, and `git diff --check`.
- No restart or rebuild performed.
