---
name: ml_training_maintenance cron 是 hybrid (5 training daily + 5 audit weekly Sunday)
description: ML training cron 週期辨識；2026-05-09 過度簡化結論「全 weekly」修正為 hybrid；MIT 2026-05-10 W6 RFC 預跑補完
type: project
originSessionId: 853ac2a2-5e69-474d-b1c1-e47bcfeb8051
---
ml_training_maintenance cron 真實 schedule（per `srv/helper_scripts/cron/ml_training_maintenance_cron.sh:5,77,83`）：

**Crontab**：`17 3 * * *` daily 03:17 (server local TZ, UTC+2 → 01:17 UTC)

**10 個 job 拆兩類**：
- **5 ML training jobs DAILY**（每天 fire 真跑）：
  - `linucb_trainer` / `scorer_trainer` / `quantile_trainer` / `mlde_shadow_advisor` / `mlde_demo_applier`
  - daily retrain + ONNX export
- **5 audit jobs DAILY fire 但 weekday-6 (Sunday) audit gate**（其他 6 天 early-return）：
  - `thompson_sampling` / `optuna_optimizer` / `cpcv_validator` / `dl3_foundation` / `weekly_report_generator`
  - 由 `OPENCLAW_ML_CRON_AUDIT_WEEKDAY=6` env 控制 (Python `datetime.weekday()` Mon=0..Sun=6)

**Why**：2026-05-09 Session N+1 起手 prompt baseline 把 cron 當 daily，主會話誤判，連帶得出「24h 後 4 表第一次 fire」的錯誤期待。E1 ml_training cron RCA（2026-05-09 commit `3d8d543e`）查 root cause 才挖出 audit gate；同 audit 簡化為「全 weekly」也不準。MIT 2026-05-10 W6 RFC 預跑補完細節：5 training daily 本來就在跑，audit weekly only。

**How to apply**：
- 任何 ml_training 表 0-row issue 先 grep `weekday()` / `is_sunday` / cron sh 內 weekday 守衛，**不要假設全 daily 也不要全 weekly**
- 訓練數據累積問題：5 training jobs daily 已在累；4/5 策略仍不過 `MIN_SAMPLES=200` per-strategy gate 是真 sample 不足非 cron 排程問題（per MIT W6 RFC Q4）
- audit insight 累積問題：5 audit jobs weekly Sunday；本週 audit 結果在 next Sunday 才見
- 真實 fire 觀察：`cat /tmp/openclaw/status/ml_training_maintenance_status.json | jq '.jobs[]'` 看 detail.status 的 `insufficient_data` / `not_sunday` / `ok`
- `ml_parameter_suggestions` 需 fills>=80（業務樣本，非 IPC bug）；fills<80 是合法 insufficient_data 不算 0-row 違規
- prompt 給下個 session 時用「hybrid: 5 daily training + 5 weekly Sunday audit」描述

**Sample rate baseline (per MIT 2026-05-10 W6 RFC PG 實測)**：
- fills 24h demo+live_demo = 112 row
- fills 7d demo+live_demo = 652 row
- 全期 5-strategy labeled fill = 615 row
- decision_features labeled = 9267, rejected = 7038
- per-strategy fill 5d 估算: grid 374 (PASS 200 gate) / ma 167 (FAIL) / bb_breakout 27 (FAIL) / bb_reversion 4 (FAIL) / funding_arb 43 (FAIL, ADR-0018 退役 dormant by design)
