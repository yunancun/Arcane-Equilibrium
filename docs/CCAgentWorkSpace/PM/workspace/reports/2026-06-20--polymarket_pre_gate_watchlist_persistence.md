# Polymarket Pre-Gate Watchlist Persistence

日期：2026-06-20
角色：PM
範圍：artifact-only Polymarket lead-lag 診斷；不改 candidate gate / strategy / order / risk。

## 結論

本批把 `polymarket_leadlag` 升到 v0.13，新增 `pre_gate_watchlist_persistence_scorecard`。它回答一個具體問題：pre-gate HAC watchlist 不是偶然閃一下，還是跨多次報告反覆出現？

Runtime 答案是：有 recurring/persistent，但樣本 floor 太薄。最新 Polymarket artifact 仍是 `INSUFFICIENT_SAMPLE`，sample=19/30；persistence status 是 `LOW_SAMPLE_RECURRING_PRE_GATE_WATCHLIST`。5 個 current watch cells 都 recurring / persistent，但 floor-qualified recurring=0，因為當前 floor qualification threshold 是 8，而 top cells 的 current floor 只有 1。

所以這不是 promotion proof，也不是 probe 權限；它只把「為何不能賺錢/不能推進」說得更精確：Polymarket 看起來有反覆出現的 pre-gate 線索，但目前仍被 overlap-adjusted sample floor 擋住。

## 變更

- `helper_scripts/research/polymarket_leadlag/__init__.py`
  - runner/schema bump 到 v0.13。
- `helper_scripts/research/polymarket_leadlag/harness.py`
  - 新增 `load_recent_report_history()`，只讀 dated reports，排除 `polymarket_leadlag_latest.json`。
  - pre-gate HAC watchlist 保留 price-feedback / partial-control 診斷欄位。
  - 新增 `build_pre_gate_watchlist_persistence_scorecard()`。
  - persistence status 只有在 current overlap-adjusted floor 達 `max(3, ceil(min_points*0.25))` 時才升級成 `RECURRING_PRE_GATE_WATCHLIST` / `PERSISTENT_PRE_GATE_WATCHLIST`。
- `helper_scripts/cron/polymarket_leadlag_ic_cron.sh`
  - status JSONL pass through persistence scorecard/status/counts。
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - Polymarket arm detail pass through persistence scorecard。
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - sample-gate blocker rows now include persistence status/counts and best current persistent cell。
- Tests
  - Added persistence reducer tests, low-floor recurrence test, recent-history loader ordering/exclusion test, cron static passthrough, and alpha-discovery blocker passthrough assertions。

## Runtime Evidence

Polymarket latest:

- Path: `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`
- sha256: `c64314139cac2349fdb1983de593a20c58fcac5813b0511d56c4ad4ae3ea65f5`
- `created_at_utc`: `2026-06-20T17:17:02.986979+00:00`
- runner: `polymarket_leadlag.v0.13`
- verdict: `INSUFFICIENT_SAMPLE`
- sample: `19/30`, remaining `11`
- persistence: `LOW_SAMPLE_RECURRING_PRE_GATE_WATCHLIST`
- recurring / persistent: `5 / 5`
- floor-qualified recurring / persistent: `0 / 0`
- current floor threshold for status: `8`

Top cells:

- `other|BTCUSDT|240`: consecutive=4, presence=4, current floor=1, floor-qualified=false, HAC t≈-24.99
- `other|SOLUSDT|240`: consecutive=4, presence=4, current floor=1, floor-qualified=false, HAC t≈-5.70
- `price_target|XRPUSDT|240`: consecutive=4, presence=4, current floor=1, floor-qualified=false, HAC t≈5.68

Alpha discovery latest:

- Path: `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`
- sha256: `76d8778a1964faaa93dcd81060ecc7afcbb3dcf08e52fbfeb269b9d166f319b8`
- status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- Polymarket sample: `19`
- persistence: `LOW_SAMPLE_RECURRING_PRE_GATE_WATCHLIST`
- floor-qualified recurring: `0`
- best cell: `other|BTCUSDT|240`

## Verification

Mac:

- `env PYTHONPATH=helper_scripts/research python3 -m pytest -q --import-mode=importlib program_code/research/tests/test_fill_sim_cost_wall.py helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_polymarket_leadlag.py helper_scripts/cron/tests/test_polymarket_leadlag_ic_cron_static.py` → `78 passed`
- `python3 -m py_compile helper_scripts/research/polymarket_leadlag/harness.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
- `bash -n helper_scripts/cron/polymarket_leadlag_ic_cron.sh`
- `git diff --check`

Linux selective sync:

- Same focused pytest suite → `78 passed`
- Same py_compile / bash syntax / targeted diff-check passed

Runtime smoke:

- Ran Polymarket lead-lag cron wrapper and alpha-discovery cron wrapper on `trade-core` with `OPENCLAW_DATA_DIR=/tmp/openclaw`。

## Boundary

This batch wrote source/tests/docs and `/tmp/openclaw` research/status artifacts only. It did not write PG tables, run migrations, call Bybit private/signed/trading endpoints, rebuild/restart engine/API, or mutate credential/auth/risk/order/strategy state.

## Next Trigger

Wait for Polymarket sample gate to mature and for any recurring/persistent pre-gate cell to become floor-qualified. With current `min_points=30`, the reducer requires current overlap-adjusted floor >=8 for stronger watch status and full candidate review still requires the existing min_points/HAC/BH gates.
