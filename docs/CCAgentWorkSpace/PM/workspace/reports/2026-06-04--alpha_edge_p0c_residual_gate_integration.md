# 2026-06-04 Alpha-Edge P0-C Residual Gate Integration

## PM 結論

本批完成 `demo_residual_alpha_report` 在 promotion / MLDE live-candidate producer / LG-5 reviewer 的 validation-only 接入。

裁決保持原設計邊界：
- 不做 DB migration。
- 不 bump `live_candidate_eval_v1`。
- promotion / LG-5 path 不計算 residual alpha，不合成 fake report。
- 缺 canonical `demo_residual_alpha_report` 必須 fail-closed。
- 不改 live/auth/order/risk runtime。

## 落地內容

- 新增 `program_code/ml_training/residual_alpha_report_contract.py`：共享 canonical extractor 與 fail-closed validator。
- `promotion_pipeline.py`：demo graduation、operator `APPROVED`、`LIVE_ACTIVE` promote 均要求合法 residual report。
- `promotion_evidence.py`：只從 JS row / payload pass-through canonical report；summary 明示 missing/verdict/pass/reason；DB persistence 仍只寫 selection/tail，不寫 residual SQL。
- `mlde_demo_applier.py`：live candidate creation 必須有合法 canonical report；payload builder 只拷貝真實 canonical report。
- `governance_hub_live_candidate_review.py`：LG-5 在 `hub.acquire_lease()` 前驗 residual；missing/defer/fail/core diagnostic 先 defer/reject，無 lease。

## E2 對抗審查

第一輪 E2 找到 blocker：shared extractor 接受 alias-only `residual_alpha_report`，會違反 PM 裁決中的 canonical required field。

PM 修復後：
- extractor 只讀 `demo_residual_alpha_report`。
- production path 不再讀 alias literal。
- 新增 alias-only regression 覆蓋 promotion、promotion evidence、MLDE producer、LG-5 reviewer。

E2 最終 verdict：`ACCEPT_WITH_RISK`，無 blocker。

保留風險：
- repo 外 producer 若仍輸出 alias-only，會 fail-closed；這符合 canonical-only 裁決。
- no-migration 下 DB restore 不會恢復 residual report；process restart 後相關 entry 會 defer，而不是 pass。

## 驗證

PM 本地驗證：
- `python3 -m pytest program_code/ml_training/tests/test_residual_alpha_report_contract.py -q` = 9 passed
- `python3 -m pytest program_code/ml_training/tests/test_mlde_demo_applier.py -q` = 23 passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_review_live_candidate.py -q` = 56 passed
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_promotion_pipeline.py -q` = 52 passed
- `python3 -m pytest program_code/ml_training/tests/test_promotion_evidence.py -q` = 7 passed
- focused combined suite = 147 passed
- control_api wider suite = 122 passed
- source `py_compile` = PASS
- `git diff --check` = PASS
- `python3 -m pytest program_code/ml_training/tests -q` = 453 passed / 2 failed / 31 skipped；2 failures 是既有 `synthetic_replay` evidence-source allowlist drift，非本批引入。

E4 最新必跑驗證：
- 前 5 組聚焦 pytest 已 PASS：9 / 23 / 56 / 52 / 7 passed。
- 合併 suite PASS：147 passed。
- source `py_compile` PASS。
- `git diff --check` PASS。
- optional control_api wider suite PASS：122 passed。
- optional `program_code/ml_training/tests` = 453 passed / 2 failed / 31 skipped；2 failures 仍是既有 `synthetic_replay` evidence-source allowlist drift。

## 邊界

本批 source/test/docs only。沒有 migration apply、DB write、runtime deploy、rebuild/restart、live auth/order/risk config mutation、paper/live enable、promotion state mutation。
