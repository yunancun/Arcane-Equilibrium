---
name: ml_training_maintenance cron 是 weekly Sunday 非 daily
description: ML training cron 週期辨識；Session N+1 baseline 誤判教訓；下次驗 0-row 前先確認 cron 週期定義
type: project
originSessionId: 853ac2a2-5e69-474d-b1c1-e47bcfeb8051
---
ml_training_maintenance cron 表面看像 daily（crontab `17 3 * * *`）但 5 個 audit job 內部 by design **是 weekly Sunday**（UTC weekday=6 才實質執行，其他 6 天 fire 但 early-return）。

**Why**：Session N+1 起手時 prompt baseline 把 cron 當 daily，主會話也誤判，連帶得出「24h 後 4 表第一次 fire」的錯誤期待。E1 ml_training cron RCA（2026-05-09 commit `3d8d543e`）查 root cause 才挖出 weekly Sunday 設計，並補了 IPC __auth handshake 的真 bug。

**How to apply**：
- 任何 ml_training 表 0-row issue 先 grep `weekday()` / `is_sunday` / `7 *` / cron sh 內 weekday 守衛，**不要假設 daily**
- 5 個 audit job：thompson_sampling / optuna_optimizer / cpcv_validator / dl3_foundation / weekly_report_generator 全 weekly Sunday
- 真實 fire 觀察：用 `cat /tmp/openclaw/status/ml_training_maintenance_status.json | jq '.jobs[]'` 看 detail.status 的 `insufficient_data` / `not_sunday` / `ok`
- ml_parameter_suggestions 需 fills>=80（業務樣本，非 IPC bug）；fills<80 是合法 insufficient_data 不算 0-row 違規
- prompt 給下個 session 時別寫「daily」字樣
