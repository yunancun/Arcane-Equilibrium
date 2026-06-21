# Cost-Gate Materializer Cron Wiring

## 結論

v338 的 reject materializer 已能把 PG recorded cost-gate rejects 轉成 learning ledger rows；這次把它接入既有 `cost_gate_learning_lane_cron.sh`。

新的 source-level loop：

1. historical scorecard review
2. PG reject materialization
3. blocked-signal outcome refresh
4. blocked-outcome review

這讓 operator-approved cron activation 後，系統可以從 PG rejects 自動走到 per-signal blocked-outcome evidence，而不是還需要人工手動先 materialize ledger。

## 改動

- `cost_gate_learning_lane_cron.sh` 新增 materializer step。
- 產生 dated/latest `reject_materializer_*.json`。
- Status JSONL 新增 materializer rc/status/input/materialized/appended/decision-count fields。
- Installer dry-run entry 新增：
  - `OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS`
  - `OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS`
- Activation preflight source readiness 新增 `reject_materializer.py`。

## 邊界

- Source/test/docs only。
- 不 runtime source sync。
- 不安裝 cron。
- 不改 runtime env。
- 不啟 writer。
- 不 append ledger。
- 不寫 PG / schema migration。
- 不連 Bybit private/signed/trading API。
- 不下單。
- 不改 auth / risk / strategy / runtime config。
- 不降低 main Cost Gate。
- 不構成 execution proof 或 promotion proof。

## 驗證

- `python3 -m pytest helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py -q`：9 passed
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q`：58 passed
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py -q`：42 passed
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/reject_materializer.py helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`：PASS
- `bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh helper_scripts/cron/install_cost_gate_learning_lane_cron.sh`：PASS
- `git diff --check`：PASS

Note：cron static + research tests 在同一 pytest command 會觸發本地 collection import-name 衝突；已分開執行並各自通過。
