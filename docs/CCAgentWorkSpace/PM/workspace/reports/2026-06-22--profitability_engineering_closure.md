# Profitability Engineering Closure

## 結論

v392 把「我們如何盈利」從靜態 scorecard 推進成工程閉環：`alpha_profitability_path_scorecard_v1` 現在會讀 `sealed_horizon_bounded_demo_probe_preflight_v1`，並輸出 `profitability_engineering_closure_v1`。

當前 leading path 不是降低全局 Cost Gate，而是：`ma_crossover|BTCUSDT|Sell@240m` 的 horizon retiming / side-cell filter 路徑，在 sealed evidence + preflight 下進入 bounded demo probe review 前檢查。它目前還差兩個 gate：

- operator sealed-horizon review record
- production learning lane ledger/outcome accumulation

## Source Changes

- `helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py`
  - 新增 `--sealed-horizon-probe-preflight-json`。
  - Horizon retiming path now consumes sealed probe preflight and emits preflight-specific statuses:
    - `SEALED_HORIZON_PREFLIGHT_REQUIRES_OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE`
    - `SEALED_HORIZON_PREFLIGHT_REQUIRES_OPERATOR_REVIEW`
    - `SEALED_HORIZON_PREFLIGHT_PRODUCTION_LANE_NOT_READY`
    - `SEALED_HORIZON_PREFLIGHT_READY_FOR_OPERATOR_AUTHORIZATION`
    - `SEALED_HORIZON_PREFLIGHT_AUTHORITY_BOUNDARY_VIOLATION`
  - 新增 `profitability_engineering_closure_v1`：
    - profit thesis
    - leading path
    - remaining proof gates
    - cost-gate escape strategy
    - edge-amplification levers
    - autonomous-learning requirements

- `helper_scripts/research/tests/test_profitability_path_scorecard.py`
  - 覆蓋 preflight blocked by operator + production lane。
  - 覆蓋 preflight ready 仍不授予 probe/order authority。

## Linux Smoke

Artifact：

- `/tmp/openclaw/profitability_refresh/20260622T031320Z/profitability_closure_v392/profitability_path_scorecard_latest.json`
- sha256：`9afb127096f78d20f31bdf2a39fdc5bec4a89784fb4842026150a354ed3534aa`

Key fields：

- scorecard status：`PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING`
- top path：`horizon_edge_amplification:ma_crossover|BTCUSDT|Sell`
- top path status：`SEALED_HORIZON_PREFLIGHT_REQUIRES_OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE`
- closure status：`COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_AND_PRODUCTION_LEARNING_LANE`
- remaining proof gates：2
- bounded demo probe preflight ready：`false`
- global Cost Gate lowering：`false`
- probe authority：`false`
- order authority：`false`

## Verification

- Mac `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py` passed.
- Mac `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_profitability_path_scorecard.py -q` = `6 passed`.
- Mac related suite：
  `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_cost_gate_sealed_horizon_probe_preflight.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py -q` = `65 passed`.
- Mac `git diff --check` passed.
- Linux source fast-forwarded to `80dde8b5`.
- Linux py_compile passed.
- Linux same related suite = `65 passed`.
- Linux artifact smoke passed.

## Boundary

- No PG write/schema migration.
- No Bybit private/signed/trading call.
- No deploy/rebuild/restart.
- No env/auth/risk/order/strategy mutation.
- No Cost Gate lowering.
- No probe/order authority.
- No promotion proof.

## Next Gate

Do not globally lower Cost Gate. The next engineering closure is to make production learning lane accumulation real and auditable, then separately record operator review. Only after both pass should a future, separate Rust-authority bounded demo probe authorization be considered.
