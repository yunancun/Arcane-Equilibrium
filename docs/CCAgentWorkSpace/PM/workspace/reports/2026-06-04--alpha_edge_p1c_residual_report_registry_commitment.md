# 2026-06-04 Alpha-Edge P1-C Residual Report Registry Commitment

## 結論

本 checkpoint 把 residual alpha report 從「payload report + payload manifest
互相 hash」收緊為「replay registry manifest 必須承諾同一份 residual report
hash」。MLDE live-candidate producer 現在要求
`replay_registry_manifest_jsonb.demo_residual_alpha_report_hash` 存在，且必須等於
canonical `demo_residual_alpha_report` 的 SHA-256。

這仍不是 durable residual report table；它是 migration-free 的 registry
manifest commitment。好處是 report hash 已納入 replay manifest hash 的承諾面，
producer 不能只靠 payload 自證 residual alpha evidence。

## 完成內容

- `candidate_evidence_source_contract.py`
  - 新增 `REGISTRY_RESIDUAL_ALPHA_HASH_FIELD =
    "demo_residual_alpha_report_hash"`。
  - source contract 在 replay registry snapshot 通過後，先驗 registry
    residual report hash，再驗 hidden OOS state。
  - 缺 registry residual hash → `pending_schema`。
  - malformed / mismatch → `invalid`。
  - hash 計算使用 canonical JSON：`sort_keys=True`、compact separators、
    `ensure_ascii=True`，與 candidate evidence manifest tests 對齊。

- `experiment_registry.py`
  - alpha `hidden_oos_state` register path 現在同時要求
    `demo_residual_alpha_report_hash` 存在且為 64 hex。
  - 這避免 register helper 產生下游 source contract 必然 fail 的 alpha
    registry manifest。

- 測試
  - MLDE source contract fixture 的 registry manifest 加入 residual report hash。
  - 新增缺 registry residual hash 與 mismatch 的 fail-closed 測試。
  - register helper 新增 alpha hidden OOS state 缺 residual hash 400 測試。

## 驗證

- `python3 -m pytest program_code/ml_training/tests -q`
  - `507 passed, 31 skipped`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay -q`
  - `114 passed, 7 skipped`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_review_live_candidate.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py -q`
  - `77 passed, 1 skipped`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_experiments_register.py -q`
  - `25 passed`
- `python3 -m py_compile` on touched source / tests
  - PASS

## 邊界

- 無 DB migration。
- 無 DB write/apply；live PG 測試仍 opt-in skipped。
- 無 runtime deploy / rebuild / restart。
- 無 auth、order、risk/strategy config、paper/live 狀態變更。
- 本 checkpoint 不是 durable residual report registry；它只把 residual report
  hash 承諾拉進 replay registry manifest。
