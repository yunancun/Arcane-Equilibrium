# 2026-06-22 -- Bounded Probe Result Review Alpha Ingestion

## Verdict

PASS. v399 把 `bounded_demo_probe_result_review_v1` 接入主 profitability / alpha / worklist 閉環，而不是再新增一個孤立診斷工具。

## What Changed

- `profitability_path_scorecard.py` 新增 `--bounded-probe-result-review-json`，在 top path evidence 和 `profitability_engineering_closure_v1` 中呈現 result-review 狀態、完成樣本數、realized net、operator-review / stop / learning-review flags。
- `runtime_runner.py` 會讀 canonical 或 dated `bounded_probe_result_review_latest.json`，把結果帶入 Cost Gate learning arm detail。
- `discovery_loop.py` 讓 fresh result review 優先於 preflight：realized edge failed 會停住並保持 Cost Gate blocked；collect-more 進 sample gate；first/learning review 進 operator-gated review。
- `learning_worklist.py` 攜帶 result-review evidence，並修正 Cost Gate `rejected_no_edge` 不再被誤分類成 learning activation。

## Verification

- Mac: `python3 -m py_compile` touched alpha modules passed.
- Mac: `python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py helper_scripts/research/tests/test_cost_gate_bounded_probe_result_review.py helper_scripts/research/tests/test_profitability_path_scorecard.py` = `71 passed`.
- Mac: `git diff --check` passed.
- Linux source fast-forwarded to `f968aaf2`.
- Linux: py_compile touched alpha modules passed.
- Linux focused pytest = `11 passed`.
- Linux profitability smoke: `/tmp/openclaw/profitability_refresh/20260622T031320Z/bounded_probe_result_ingestion_v399/profitability_path_scorecard_latest.json`, sha256 `b093d25118ab65299c10dae56f491477560f2cd51877b87a0835fc17302ff039`.
- Linux alpha smoke: `/tmp/openclaw/alpha_discovery_throughput/bounded_probe_result_ingestion_v399/alpha_discovery_latest.json`, sha256 `80be82ed7a4058426c9f997955a62684050aa71697d2d2fbd3a6c460d396aada`.

## Runtime Read

Current bounded result review is still `NO_PROBE_OUTCOMES_RECORDED` with completed outcomes `0`. The scorecard therefore stays at `COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_REVIEW`; it does not recommend Cost Gate lowering, does not create promotion proof, and does not grant probe/order authority.

## Boundary

Source/test/docs plus `/tmp/openclaw` artifact-only smoke only. No CI run, PG write/schema migration, Bybit private/signed/trading call, deploy/rebuild/restart, cron install, env/auth/risk/order/strategy/runtime mutation, Cost Gate lowering, probe/order authority, or promotion proof.
