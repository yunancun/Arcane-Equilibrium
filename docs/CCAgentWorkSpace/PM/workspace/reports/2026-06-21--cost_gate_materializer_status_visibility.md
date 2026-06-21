# 2026-06-21 -- Cost-Gate Materializer Status Visibility

## 結論

本批修的是 v339 之後的可觀測性缺口：cron 已經會跑 reject materializer，但 status / preflight / killboard 還不能直接看見 materializer 是否跑過、是否 append、產生了多少 rows、decision 分佈是什麼。

現在 `cost_gate_learning_lane.status` 會讀：

- `cost_gate_learning_lane/reject_materializer_latest.json`
- `logs/cost_gate_learning_lane.log` 裡的 `materializer_*` 欄位

並把 materializer enablement、append enablement、rc、status、input/materialized/appended counts、decision counts 帶到 activation preflight 和 alpha-discovery cost-gate blocker row。

## Runtime Read-Only Smoke

2026-06-21T19:52Z 重新跑了一次 runtime read-only smoke。邊界是：只透過 `ssh trade-core` 做 runtime `cat` / PG `SELECT`，本機內存跑 materializer -> blocked-outcome refresh -> review；沒有寫 ledger、沒有寫 PG、沒有 Bybit private/signed/trading call、沒有下單、沒有降低 Cost Gate。

結果：

- `plan_status=READY_FOR_DEMO_LEARNING_PROBE`
- `plan_ranking_source=derived_from_scorecard_rows`
- runtime PG feature rows：`20`
- symbols：`["BTCUSDT"]`
- materialized rows：`20`
- materializer decision counts：`{"SIDE_CELL_NOT_SELECTED": 20}`
- refresh windows：`20`
- blocked-signal outcomes：`20`
- review status：`NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE`
- top reviewed side-cell：`ma_crossover|BTCUSDT|Buy`
- outcome count：`20`
- avg net：`-0.1183bp`
- net-positive pct：`0.0`
- side-cell status：`KEEP_COST_GATE_BLOCKED`

解讀：真實 PG reject rows 可以進入學習鏈路並被 outcome review 檢驗；當前這批 BTCUSDT Buy 樣本支持維持 Cost Gate block，不支持盲目降低 gate。工程方向仍然是讓 blocked signals 持續積累並被市場結果驗證，而不是純本地測算後放寬主 gate。

## Source Changes

- `helper_scripts/research/cost_gate_learning_lane/status.py`
  - 新增 materializer latest artifact / status-log summary。
  - activation preflight 新增 `reject_materializer_ran/enabled/append_enabled/latest_available/status/materialized_records/appended_records`。
  - materializer rc 非 0 會使 learning loop 進入 error。
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - cost-gate blocker row 帶出 materializer rc/status/input/materialized/appended/decision counts。
- `helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`
  - 覆蓋 latest artifact fallback、status-log materializer fields、preflight answers、killboard row fields。

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = `58 passed`
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py -q` = `42 passed`
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` passed
- `git diff --check` passed

## Boundary

本批不做 runtime source sync、不安裝 cron、不改 env、不 deploy / rebuild / restart、不 append ledger、不寫 PG、不連 Bybit、不下單、不啟 learning writer、不授予 order authority、不降低 main Cost Gate。

## Next

下一個硬步驟仍是 operator-approved runtime activation：source sync/reconcile -> install/enable learning cron -> enable append path -> 觀察 materialized/appended/outcome/review counts 是否穩定增長。只有被 blocked-outcome review 證明有正期望的 side-cell，才進入 demo probe authority review。
