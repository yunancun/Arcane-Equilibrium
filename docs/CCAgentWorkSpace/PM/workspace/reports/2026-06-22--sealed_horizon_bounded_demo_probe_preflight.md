# Sealed Horizon Bounded Demo-Probe Preflight

## 結論

v391 把 sealed horizon candidate 的下一步從文字 gate 變成可重跑 artifact：`sealed_horizon_bounded_demo_probe_preflight_v1`。

它不是 probe approval。它只回答：sealed evidence 是否 ready、profit-learning decision packet 是否對齊、operator review 是否已記錄、production learning lane 是否真的在積累、以及所有輸入是否仍然沒有 Cost Gate lowering / probe authority / order authority / promotion proof。

## Source Changes

- `helper_scripts/research/cost_gate_learning_lane/sealed_horizon_probe_preflight.py`
  - 新增 artifact-only preflight builder。
  - 輸入：`sealed_horizon_learning_evidence_v1`、`cost_gate_profit_learning_decision_packet_v1`、activation/stack-health artifact、optional `sealed_horizon_operator_review_v1`。
  - 輸出：`sealed_horizon_bounded_demo_probe_preflight_v1`。
  - 主要 status：`OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED`、`OPERATOR_REVIEW_REQUIRED`、`PRODUCTION_LEARNING_LANE_NOT_READY`、`READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`、`AUTHORITY_BOUNDARY_VIOLATION`。

- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - Ingests `cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json`。

- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - Fresh preflight status supersedes packet-only sealed-horizon blocker。
  - If both operator review and production lane are missing, primary blocker becomes `sealed_horizon_probe_preflight_requires_operator_review_and_learning_lane`。

- `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
  - Carries preflight fields into task evidence。
  - Emits sealed-preflight objectives such as `operator_review_sealed_horizon_preflight_and_activate_production_learning_lane`。

## Verification

- `python3 -m py_compile ...` passed.
- `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_cost_gate_sealed_horizon_probe_preflight.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py -q` = `59 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_cost_gate_sealed_horizon_probe_preflight.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py helper_scripts/research/tests/test_cost_gate_sealed_horizon_learning_evidence.py helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py -q` = `72 passed`.
- Linux `trade-core` fast-forwarded and ran the same focused suites:
  - preflight/alpha/worklist = `59 passed`
  - related Cost Gate/scorecard/alpha = `72 passed`
- Linux artifact smoke:
  - preflight JSON：`/tmp/openclaw/profitability_refresh/20260622T031320Z/sealed_horizon_probe_preflight_v391/sealed_horizon_probe_preflight_latest.json`
  - preflight sha256：`09b498b1b254f75e6c3de04ce7ea8206735b547e5bce0f465c7f5a2c287e2fbc`
  - status：`OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED`
  - blocking gates：`operator_sealed_horizon_review_recorded`, `production_learning_lane_accumulating`
  - alpha smoke latest：`/tmp/openclaw/profitability_refresh/20260622T031320Z/alpha_discovery_v391_smoke/alpha_discovery_latest.json`
  - alpha smoke sha256：`cc0966b2bbdf34fb54b53ff4efcf9a5138afccc8a26a6b84e95cb65f2c398f1c`
  - alpha blocker：`sealed_horizon_probe_preflight_requires_operator_review_and_learning_lane`
  - worklist objective：`operator_review_sealed_horizon_preflight_and_activate_production_learning_lane`

## Boundary

- No PG write/schema migration.
- No Bybit private/signed/trading call.
- No deploy/rebuild/restart.
- No env/auth/risk/order/strategy mutation.
- No Cost Gate lowering.
- No probe/order authority.
- No promotion proof.

## Role Note

Per repo workflow this kind of change can justify E1/E2/E4 separation. I kept it PM-local because the operator explicitly asked to avoid repeated work and this batch is narrow, artifact-only, and covered by focused regression. The remaining higher-risk step, any actual bounded demo probe authorization, still requires separate operator/Rust-authority review.
