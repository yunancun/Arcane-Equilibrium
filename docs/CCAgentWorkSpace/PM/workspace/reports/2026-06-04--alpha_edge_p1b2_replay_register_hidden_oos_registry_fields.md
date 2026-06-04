# 2026-06-04 Alpha-Edge P1-B2 Replay Register Hidden OOS Registry Fields

## 結論

本 checkpoint 修正 P1-B 後暴露出的真實 register helper 缺口：V049
`replay.experiments` 已有 train / OOS / candidate window、embargo、K 欄位，
但 `register_experiment()` 先前仍把 train/candidate/embargo/K 寫成 `NULL`。

現在當 `manifest_jsonb.hidden_oos_state` 存在時，register helper 會把它視為
alpha candidate evidence path，並要求該 state 能填滿 V049 既有欄位；普通
replay manifest 不帶 `hidden_oos_state` 時仍保持 legacy NULL 行為。

## 完成內容

- `replay/experiment_registry.py`
  - 新增 `hidden_oos_state_v1` → V049 欄位映射 helper。
  - `hidden_oos_state` 存在時要求：
    - `schema_version == hidden_oos_state_v1`
    - `state == sealed`
    - `family_id` / `split_hash` 存在
    - `open_count == 0`
    - 未 `opened_for_iteration` / `consumed` / `invalidated`
    - `calibration_train_window_start/end` 存在且 start < end
    - `window_start/end` 與 request `data_window_start/end` 一致
    - `candidate_window_start/end` 存在且 start < end
    - `embargo_seconds` 與 request `embargo_days` 一致
    - `total_candidates_k` > 0
  - INSERT 不再固定寫 `NULL,NULL,NULL,NULL,NULL,NULL`；改用 helper 輸出的
    train/candidate/embargo/K 欄位，legacy path 則 helper 回 `None`。
  - `alpha_hidden_oos_state_*` error 映射成 400，不當成 503 runtime failure。

- 測試
  - 新增 alpha hidden OOS state 註冊正向測試：驗 INSERT params 寫入 V049
    train/OOS/candidate/embargo/K。
  - 新增缺 `candidate_window_start` fail-closed 400 測試。
  - 同步 INSERT params index，因 manifest_jsonb / manifest_hash 位置從
    `[12]/[13]` 移到 `[18]/[19]`。
  - 更新舊 R7 capability E2E mock，從 6-key probe 對齊 P1-A 的 12-key
    registry snapshot probe。

## 驗證

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_experiments_register.py -q`
  - `24 passed`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_strategy_param_delta.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_risk_param_delta.py -q`
  - `6 passed`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay -q`
  - `114 passed, 7 skipped`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py -q`
  - `18 passed, 1 skipped`
- `python3 -m py_compile` on touched replay registry / tests
  - PASS

## 邊界

- 無 DB migration；只使用 V049 已存在欄位。
- 無 DB write/apply；測試均為 mock / hermetic，live PG 測試仍 opt-in skipped。
- 無 runtime deploy / rebuild / restart。
- 無 auth、order、risk/strategy config、paper/live 狀態變更。
- 本 checkpoint 仍不是 durable hidden OOS state machine；它只是讓 register
  path 寫出 P1-B producer gate 需要的 registry snapshot。
