# Profitability Scorecard Operator-Authorization Gate Ingestion

日期：2026-06-23  
PM scope：source/test/docs + Mac/origin/Linux source sync + artifact-only alpha cron smoke

## 結論

本輪把 `bounded_probe_operator_authorization_latest.json` 接入 `alpha_profitability_path_scorecard_v1`，讓主盈利閉環直接看到「翻越 Cost Gate」前的具體 operator-authorization gates，而不是只停在泛化的 sealed-preflight/operator-review blocker。

當前 canonical Linux scorecard 已從 v428 的 `COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_REVIEW` 變成：

- `closure=BOUNDED_DEMO_PROBE_OPERATOR_AUTHORIZATION_GATES_NOT_READY`
- leading path：`horizon_edge_amplification:ma_crossover|BTCUSDT|Sell`
- operator authorization status：`SEALED_HORIZON_PREFLIGHT_NOT_READY`
- blocking gates：`sealed_horizon_preflight_ready`、`placement_repair_plan_ready`、`authority_path_patch_readiness_ready`
- `operator_authorization_object_emitted=false`
- active runtime order/probe authority：false
- `main_cost_gate_adjustment=NONE`
- promotion proof：false

盈利讀法：下一步不是全局降低 Cost Gate，而是讓 sealed preflight、near-touch placement repair、Rust authority-path readiness 三個前置 artifact fresh/aligned，之後才有資格進 explicit bounded Demo operator authorization review，再用 candidate-matched fills、fee/slippage、matched controls、edge capture、execution-realism review 來證明可捕獲收益。

## Source Changes

- `helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py`
  - 新增 `--bounded-probe-operator-authorization-json`
  - 將 operator authorization packet 依 side-cell 接入 path evidence
  - 將 packet status/risk gates 映射進 `profitability_engineering_closure_v1`
  - 保留 no-authority guard：active runtime authority、writer/order/runtime mutation、Cost Gate lowering、promotion proof 均 fail-closed
- `helper_scripts/cron/alpha_discovery_throughput_cron.sh`
  - refresh scorecard 時傳入 canonical `cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json`
- `runtime_runner.py`
  - Cost Gate arm summary 和 killboard top-level 鏡像 operator authorization status/gates/object/active-authority fields
- `discovery_loop.py` / `learning_worklist.py`
  - blocker/worklist evidence 攜帶新的 profitability closure operator-authorization fields
- Tests
  - scorecard regression 覆蓋 gates-not-ready 和 ready-for-review no-authority states
  - alpha discovery regression 覆蓋 killboard top-level mirror

## Verification

Mac:

- `python3 -m py_compile ...` PASS
- `bash -n helper_scripts/cron/alpha_discovery_throughput_cron.sh` PASS
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_profitability_path_scorecard.py`：14 passed
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py`：62 passed
- combined scorecard + alpha after mirror patch：76 passed
- `python3 -m pytest -q helper_scripts/cron/tests/test_alpha_discovery_throughput_cron_static.py`：3 passed
- artifact-only alpha cron smoke under `/tmp/openclaw_alpha_scorecard_auth_smoke_20260623` exited 0
- `git diff --check` PASS

Linux `trade-core`:

- source fast-forwarded clean to `4251c9a0`
- py_compile PASS
- bash syntax PASS
- research focused suite：76 passed
- alpha cron static：3 passed
- canonical artifact-only alpha cron smoke exited 0
- latest scorecard generated `2026-06-23T12:15:29.511823+00:00`
- Linux checkout clean after smoke

## Commits

- `d4dc4197` `Ingest operator authorization into profitability scorecard [skip ci]`
- `4251c9a0` `Mirror operator authorization scorecard fields [skip ci]`

## Boundary

No CI run. No PG write/schema migration. No Bybit private/signed/trading call. No deploy/rebuild/restart. No crontab install. No env/auth/risk/order/strategy mutation. No global Cost Gate lowering. No active probe/order authority. No actual order. No promotion proof.
