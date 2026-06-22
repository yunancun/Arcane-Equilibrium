# Sealed Horizon Preflight Refresh Wrapper

## 結論

已新增 artifact-only wrapper：`helper_scripts/cron/sealed_horizon_probe_preflight_cron.sh`。

它會刷新 canonical sealed preflight latest/status/heartbeat，讓 leading cost-gate escape path 不再依賴手工 one-off 命令。這不安裝 cron、不啟 writer、不改 runtime、不降低 Cost Gate、不授權 probe/order。

## Linux Smoke

- Source：`1f82f87c2b4a069043865e8ef7b6316ee223c1ea`
- Latest：`/tmp/openclaw/cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json`
- sha256：`5cae49e9837285aced6835ff8199e3b2183c669846b5fd8a59cd0c11a47b157d`
- status：`OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED`
- selected decision packet：`/tmp/openclaw/profitability_refresh/20260622T031320Z/profit_learning_decision_packet_v389/profit_learning_decision_packet_v389_latest.json`
- `decision_packet_aligned=true`
- remaining gates：`operator_sealed_horizon_review_recorded`, `production_learning_lane_accumulating`

## Meaning

The system can now autonomously refresh the preflight evidence for the sealed BTCUSDT Sell/240m path. It still cannot trade from this evidence.

Remaining proof gates:

- real operator approval review;
- production learning-lane ledger/outcome accumulation;
- separate bounded demo-probe authorization only after those gates.

No CI, deploy, restart, crontab install, PG write, Bybit trading call, Cost Gate lowering, probe/order authority, or promotion proof was performed.
