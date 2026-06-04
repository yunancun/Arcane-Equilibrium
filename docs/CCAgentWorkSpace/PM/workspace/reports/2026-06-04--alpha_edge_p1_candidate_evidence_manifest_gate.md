# 2026-06-04 Alpha-Edge P1 Candidate EvidenceManifest Gate

## PM 結論

本批完成 `candidate_evidence_manifest` 在 MLDE live-candidate producer 與 LG-5 reviewer 的 fail-closed 接入。

裁決邊界：
- 不做 DSL。
- 不生成 fake manifest。
- 不改 DB migration / schema。
- 不 bump `live_candidate_eval_v1`。
- 不碰 runtime、DB write、deploy、rebuild/restart、live auth/order/risk config。
- 只接受 canonical `candidate_evidence_manifest`，不接受 alias。
- producer 與 LG-5 必須同時要求 manifest `promotion_ready`，且 manifest 必須綁定合法 canonical `demo_residual_alpha_report`。

## 前置審核整合

`CC(default)` verdict：`NARROW_SCOPE`。P1 可做純 metadata contract 與 fail-closed classification tests；不能把 V049 NULL columns 或 partial lineage 當成 hidden OOS 已落地。

`FA(default)` verdict：`RETURN_FOR_DESIGN`。若 manifest 只是 JSON / lineage pass-through 而不接 producer + LG-5，仍然可繞過；必須在 `should_create_live_candidate()` 和 LG-5 review 兩端重驗。

`PA(default)` verdict：可派 E1，建議新增小型共享 module `program_code/ml_training/candidate_evidence_manifest.py` 與 verdict taxonomy。

PM 裁決採納 FA 的 blocking 要求與 PA 的小 module 方案；拒絕把 manifest 當只讀 metadata，也拒絕為兼容 legacy missing manifest 而放行。

## 落地內容

- 新增 `program_code/ml_training/candidate_evidence_manifest.py`：
  - canonical extractor 只讀 `candidate_evidence_manifest`。
  - canonical JSON sha256 排除頂層 `manifest_hash`。
  - 要求 `schema_version=candidate_evidence_manifest_v1`、`verdict=promotion_ready`、`candidate_id`、`family_id`、stable `spec_hash`、`replay_experiment_id`、hidden OOS split/window/embargo/K、hex64 `manifest_hash`。
  - 要求同時存在且通過 `demo_residual_alpha_report` validator。
  - 缺 lineage / schema 欄位回 `pending_schema`，hidden OOS reuse / not passed 回 `research_only`，hash / residual 失敗回 `invalid`。
- `program_code/ml_training/mlde_demo_applier.py`：
  - `should_create_live_candidate()` 在 expected/confidence/sample 門檻與 residual report 後，要求 manifest validation `promotion_ready`。
  - `_build_live_candidate_payload()` 只複製 validator 通過的 manifest，不合成、不修補、不接受 alias。
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub_live_candidate_review.py`：
  - LG-5 在 residual alpha gate 後、R1-R6 / R-meta / `hub.acquire_lease()` 前重驗 manifest。
  - missing / pending_schema → defer；research_only / invalid → reject；均不取得 lease。
  - audit snapshot 記錄 manifest validation reason、verdict、reasons、lineage_downgraded。
- 測試：
  - 新增 manifest contract tests，覆蓋 canonical-only、hash stability、hash mismatch、nested hash tamper、missing fields、hidden OOS reuse、missing/bad residual、non-promotion verdict。
  - 擴展 MLDE producer tests，覆蓋 missing manifest、research_only、bad hash、payload builder 不複製 invalid manifest、missing residual 不複製 manifest。
  - 擴展 LG-5 tests，覆蓋 missing manifest、alias-only manifest、invalid manifest hash 均不拿 lease。

## Dispatch 與補位

`E1(worker)` 已派發但未落地 patch；PM 在同一 scope 內補位實作，未擴大到 migration/runtime。

`E2(explorer)` 對抗審查 verdict：`ACCEPT_WITH_RISK`，無 blocker。

E2 remaining risks：
- 多重錯誤時 `manifest_hash_mismatch` 不一定是第一 reason；不影響 fail-closed，只影響 audit reason ordering。
- `mlde_demo_applier.py` 仍依賴既有 `PYTHONPATH=program_code` 啟動契約；非本 patch 新 blocker。
- approve snapshot 可再增加 compact `manifest_hash/family_id/candidate_id`，目前 fail path audit 已足夠定位。

PM 已補兩個 E2 optional tests：
- nested `manifest_hash` tamper 必須 invalid。
- LG-5 alias-only manifest 必須 defer missing 且不 acquire lease。

`E4(worker)` 驗證 verdict：`PASS`，未修改文件。

## 驗證

E4 驗證：
- focused suite before PM supplemental tests：97 passed。
- source `py_compile`：PASS。
- `git diff --check`：PASS。
- `program_code/ml_training/tests`：469 passed / 2 failed / 31 skipped；2 failures 是已知 `synthetic_replay` allowlist drift。

PM 補充驗證：
- `python3 -m pytest program_code/ml_training/tests/test_candidate_evidence_manifest.py program_code/ml_training/tests/test_mlde_demo_applier.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_review_live_candidate.py -q` = 99 passed。
- `python3 -m py_compile program_code/ml_training/candidate_evidence_manifest.py program_code/ml_training/mlde_demo_applier.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub_live_candidate_review.py` = PASS。
- `git diff --check -- <changed P1 files>` = PASS。
- `python3 -m pytest program_code/ml_training/tests -q` = 470 passed / 2 failed / 31 skipped。

已知 unrelated failures：
- `program_code/ml_training/tests/test_evidence_filter_capability.py::test_case1_full_capability_all_true_emits_full_block_b`
- `program_code/ml_training/tests/test_evidence_filter_capability.py::test_case3_block_a_only_evidence_source_tier_allowlist_no_block_b`

兩者都是 `synthetic_replay` 是否屬於 `EVIDENCE_SOURCE_TIER_ALLOWLIST` 的既有期望差異，非本批 manifest gate 引入。

## 保留風險

本批是 source/test/docs-only 的 fail-closed gate，不證明 hidden OOS registry 已完整落地，也不證明 manifest 來源已被真實 producer 生成。現狀若真實 upstream row 缺 manifest，結果會是 live candidate / LG-5 promotion 被阻斷，而不是自動修復。

後續 P1 真正要補的是 manifest producer / hidden OOS registry / row-level lineage persist；但在這些未完成前，嚴格 fail-closed 比 legacy pass 更符合 Alpha-Edge 的證據要求。
