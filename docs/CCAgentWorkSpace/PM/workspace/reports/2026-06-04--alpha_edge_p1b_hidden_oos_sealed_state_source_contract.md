# 2026-06-04 Alpha-Edge P1-B Hidden OOS Sealed-State Source Contract

## 結論

本 checkpoint 在 P1-A registry-verified source contract 上再收緊一層：
MLDE live-candidate producer 現在要求 `replay_registry_manifest_jsonb`
內有 canonical `hidden_oos_state`，且該 state 必須是未開封的 `sealed`、
`open_count=0`，並與 registry OOS window / embargo / K 完全一致。

這是 migration-free 的 producer gate，不是完整 durable hidden OOS state
machine。它能先阻止「沒有 committed hidden OOS sealed state 的 replay
manifest」升級成 live candidate，但還不能在 DB 中記錄 opened / consumed /
invalidated 的狀態轉移。

## 完成內容

- `candidate_evidence_source_contract.py`
  - 新增 `hidden_oos_state_v1` source contract。
  - promotion-ready 必須滿足：
    - `state == "sealed"`
    - `open_count == 0`
    - `opened_for_iteration / consumed / invalidated` 都不是 true
    - `split_hash` 是 stable hash
    - `family_id` 存在，且與 candidate manifest 的 `family_id` 一致
    - `window_start/window_end` 與 replay registry OOS window 一致
    - `embargo_seconds` 與 replay registry embargo 一致
    - `total_candidates_k` 與 replay registry K 一致且 > 0
  - source-fields draft 的 `hidden_oos` 現在由 committed `hidden_oos_state`
    hydrate，不再用 replay manifest hash 代替 split hash。
  - payload / manifest 若使用另一個 hidden OOS split、window、K 或 embargo，
    會以 `hidden_oos_registry_state_mismatch` fail-closed。

- 測試
  - 更新 MLDE live-candidate producer fixtures，讓有效 replay registry
    snapshot 帶上 sealed `hidden_oos_state`。
  - 新增 missing state、opened state、nonzero open_count、state window mismatch、
    family mismatch 等回歸測試。

## 為什麼先不做 migration

V049 `replay.experiments` 目前有 OOS window / embargo / K / manifest hash，
但沒有 `sealed/opened/consumed/invalidated/open_count/opened_by_role` 等 durable
狀態欄位。直接在本 checkpoint 加 migration 會擴大風險，需要 Linux PG dry-run、
migration idempotency、狀態轉移 SQL/API、審計事件與回滾策略一起設計。

本批選擇先把 producer promotion gate 收緊到「manifest-committed sealed
state」，以最小代價堵住舊 replay manifest 自證問題。下一步如果要真正解決
hidden OOS 重複打開/消費，需要新增 alpha-specific OOS state registry 或擴充
V049 狀態表，並把 opened/consumed mutation 接到 promotion/review 流程。

## 驗證

- `python3 -m pytest program_code/ml_training/tests -q`
  - `505 passed, 31 skipped`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_review_live_candidate.py -q`
  - `59 passed`
- `python3 -m py_compile` on touched producer / validator / MLDE files
  - PASS

## 邊界

- 無 DB migration。
- 無 DB write / apply。
- 無 runtime deploy / rebuild / restart。
- 無 auth、order、risk/strategy config、paper/live 狀態變更。
- 本 checkpoint 仍不得宣稱 alpha edge 已解決；它只把缺 sealed hidden OOS
  commitment 的 live-candidate promotion path fail-closed。
