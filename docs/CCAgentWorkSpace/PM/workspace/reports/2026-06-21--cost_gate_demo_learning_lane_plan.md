# Cost-Gate Demo-Learning Lane Plan

## 結論

本輪把 v304 的 cost-gate reject scorecard 往前推成可被 runtime killboard 消費的 bounded demo-learning plan。這不是全局 lower cost gate，也不是 order authority；它只把「值得在 demo 裡學」的 side-cell 變成明確、可審核、可後續接 adapter 的 artifact。

## 實作

- 新增 `helper_scripts/research/cost_gate_learning_lane/policy.py`。
- 新增 schema `cost_gate_demo_learning_lane_plan_v1`。
- plan 固定標示：
  - `main_cost_gate_adjustment=NONE`
  - `order_authority=NOT_GRANTED`
  - `learning_gate_adjustment=SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING`
- `LEARNING_PROBE_CANDIDATE` 進 selected side-cells。
- `BLOCK_CONFIRMED` 進 `do_not_probe_side_cells`。
- `DATA_COVERAGE_BLOCKER` 進 `data_coverage_tasks`。
- `alpha_discovery_throughput.runtime_runner` 新增 optional arm `cost_gate_demo_learning_lane`。
- `discovery_loop` 對該 arm 產生專用 blocker row：`cost_gate_learning_probe_candidates_ready`。

## Linux Evidence

- Plan artifact: `/tmp/openclaw/cost_gate_learning_lane/demo_learning_lane_plan_latest.json`
- Plan sha256: `66d07781be9885b777c6dd0cd2e5add5823514ac4b9a90dee9ef710f42859b7b`
- Plan status: `READY_FOR_DEMO_LEARNING_PROBE`
- Gate status: `OPERATOR_REVIEW`
- Selected side-cells:
  - `ma_crossover|ETHUSDT|Sell`
  - `ma_crossover|NEARUSDT|Sell`
  - `grid_trading|LTCUSDT|Sell`
  - `grid_trading|ATOMUSDT|Sell`
- Per-side-cell proposal: 2 demo-only probe orders.

Alpha-discovery artifact after consuming the plan:

- Latest sha256: `5802ed5ef0e0f6208efd491d0405804df710ec782aa8399a9011f2bda253740e`
- Created: `2026-06-21T10:49:45.501231+00:00`
- Scorecard status: `ACTIONABLE_PROBE_READY`
- `actionable_alpha_found=false`
- `actionable_probe_found=true`
- `ready_for_probe=1`
- `promotion_ready_count=0`

## Verification

- Mac focused suites: `43 passed`
- Linux focused suites: `37 passed`
- Mac/Linux `py_compile`: passed
- `git diff --check`: passed
- Linux policy artifact smoke: passed
- Linux artifact-only alpha runtime smoke: passed

## Boundary

Source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact writes only.

No PG table write or schema migration. No Bybit private/signed/trading call. No engine/API rebuild or restart. No credential/auth/risk/order/strategy mutation. This is not signal, execution proof, or promotion proof.

## Next

Implement the runtime adapter that consumes this plan in demo only, logs probe attempts/outcomes durably, auto-disables side-cells after budget/stop conditions, and feeds realized labels back into edge estimates.
