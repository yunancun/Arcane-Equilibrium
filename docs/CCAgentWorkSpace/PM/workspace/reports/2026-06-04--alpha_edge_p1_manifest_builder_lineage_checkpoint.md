# 2026-06-04 Alpha-Edge P1 Manifest Builder / Lineage Checkpoint

## PM 結論

本批完成 `candidate_evidence_manifest` producer-facing builder 與 row-level replay lineage pass-through 的 source/test-only checkpoint。

裁決邊界：
- 不讀 DB、不查 `replay.experiments`。
- 不做 DB migration / schema change。
- 不碰 runtime、deploy、rebuild/restart、live auth/order/risk config。
- 不生成 fake hidden OOS / fake residual report。
- 不把 replay registry `manifest_hash` 當 candidate manifest canonical `manifest_hash`。
- 不放寬 MLDE producer gate 或 LG-5 reviewer gate。

## Scope 審核

`CC(default)` verdict：`APPROVE_NARROW_SCOPE`。只允許把真實 upstream row/payload 的 lineage/replay 欄位傳遞、顯示、測試鎖住；禁止 fake OOS、runtime/DB/migration、gate 放寬。

`FA(default)` verdict：`APPROVE_WITH_RISK`。只新增 dead-code builder 無效；必須接到 `should_create_live_candidate()` 與 `_build_live_candidate_payload()`，但不得從 lineage/payload hash 補出 `promotion_ready`。

`PA(default)` 建議新增 sibling module `candidate_evidence_manifest_builder.py`，保留 validator 的 extract/hash/validate 職責乾淨。

## 落地內容

- 新增 `program_code/ml_training/candidate_evidence_manifest_builder.py`：
  - row-level canonical manifest 優先於 payload canonical manifest。
  - existing canonical manifest 只驗證，不修補。
  - 無 canonical manifest 時，只用明確 source fields 建 draft。
  - 必須有 `replay_experiment_id` 與 replay manifest hash；缺 replay manifest hash 直接 `pending_schema / replay_manifest_hash_missing`。
  - 不從 payload `lineage.replay_experiment_id` 或 `lineage.manifest_hash` 升級成 promotion evidence。
  - row-level replay `manifest_hash` 只進 `replay_manifest_hash`，candidate `manifest_hash` 仍由 candidate manifest canonical JSON 計算。
- `program_code/ml_training/mlde_demo_applier.py`：
  - `should_create_live_candidate()` 改用 builder validation。
  - `_build_live_candidate_payload()` 只在 builder `promotion_ready` 且 manifest 非空時放入 canonical `candidate_evidence_manifest`。
  - 刪除已無 caller 的舊 `_extract_candidate_evidence_manifest_from_source_row()`。
- `program_code/ml_training/mlde_demo_applier_evidence_filter.py`：
  - `_fetch_pending` SELECT forward-compatible 帶回 row-level `context_id`、`intent_id`、`evidence_source_tier`、`replay_experiment_id`、`manifest_hash`。
  - `evidence_source_tier/replay_experiment_id/manifest_hash` 缺欄位時用 `NULL::text AS ...`，避免 legacy schema break。
  - V051 `manifest_hash` bytea 用 `encode(manifest_hash, 'hex') AS manifest_hash`。
- 測試：
  - 新增 builder tests，覆蓋 canonical pass-through、row manifest priority、explicit source fields、alias 不接受、lineage replay id 不升級、缺 replay hash downgrade、hidden OOS missing/reused、missing residual。
  - 擴展 MLDE tests，覆蓋 builder 接入 `should_create_live_candidate()`、payload builder 只放 promotion-ready manifest、缺 replay hash 不 pass / 不寫 canonical manifest。
  - 修正 `test_evidence_filter_capability.py` stale expectation：storage enum 仍含 `synthetic_replay`，但 demo-applier default accepted tiers 排除 synthetic。

## E2/E4 結論

`E2(explorer)` 第一輪 verdict：`BLOCK`。

Blocker：draft builder 在沒有 canonical manifest 時自行計算 candidate `manifest_hash`，但 replay lineage hash 只是 optional；這會讓 row 有 `replay_experiment_id`、hidden OOS、residual report 但缺 row-level replay `manifest_hash` 時仍可能 `promotion_ready`。

PM 修復：
- draft path 在計算 candidate manifest hash 前先要求 replay manifest hash。
- 缺 replay manifest hash 直接回 `pending_schema / replay_manifest_hash_missing`，`lineage_downgraded=True`。
- 補三個回歸測試。

`E2(explorer)` 復審 verdict：`PASS`。

`E4(worker)` 驗證 verdict：`PASS`。E4 首輪在 blocker 修復前跑到 74 passed / 1 skipped；PM 最終修復後重新跑全套驗證如下。

## 驗證

PM final verification：
- `python3 -m pytest program_code/ml_training/tests/test_candidate_evidence_manifest_builder.py program_code/ml_training/tests/test_candidate_evidence_manifest.py program_code/ml_training/tests/test_mlde_demo_applier.py program_code/ml_training/tests/test_mlde_demo_applier_source_filter.py program_code/ml_training/tests/test_evidence_filter_capability.py -q` = 77 passed / 1 skipped。
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_review_live_candidate.py -q` = 59 passed。
- `python3 -m pytest program_code/ml_training/tests -q` = 484 passed / 31 skipped。
- `python3 -m py_compile program_code/ml_training/candidate_evidence_manifest_builder.py program_code/ml_training/candidate_evidence_manifest.py program_code/ml_training/mlde_demo_applier.py program_code/ml_training/mlde_demo_applier_evidence_filter.py` = PASS。
- `git diff --check -- <changed files>` = PASS。

## 保留風險

本批仍不證明 hidden OOS registry 已落地，也不證明 replay manifest hash 真的與 sealed hidden OOS split 同源；它只把 producer-facing source fields / replay metadata 的 contract 收窄並接入現有 gate。

下一步仍應補真實 manifest producer、hidden OOS registry 狀態機、row-level lineage persistence / registry verification；在這些完成前，缺欄位會被正確阻斷，而不是自動產生 promotion-ready evidence。
