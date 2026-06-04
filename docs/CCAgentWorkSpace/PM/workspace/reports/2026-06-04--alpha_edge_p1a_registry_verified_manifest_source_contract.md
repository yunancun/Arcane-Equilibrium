# 2026-06-04 Alpha-Edge P1-A Registry-Verified Manifest Source Contract

## 結論

本 checkpoint 把 MLDE live-candidate producer 從「row/payload 明確欄位可建
manifest」收緊為「必須有 replay registry snapshot 驗證後才可產生
promotion-ready evidence」。這是 P1-A 的第一個實作閉環，但仍不是完整 hidden
OOS registry 狀態機，也不是 residual report 的 durable registry。

## 完成內容

- `CandidateEvidenceManifest` validator 新增必填：
  - `replay_manifest_hash`
  - `demo_residual_alpha_report_hash`
  - residual report hash 必須與 canonical `demo_residual_alpha_report` 匹配。
- 新增 `candidate_evidence_source_contract.py`：
  - 只接受 `calibrated_replay` / `counterfactual_replay` 作 promotion source。
  - `real_outcome`、`synthetic_replay`、缺 source tier / replay id / replay hash 全部 fail-closed。
  - 要求 `replay.experiments` snapshot：`status=completed`、`expires_at` 未過期、
    registry manifest hash 與 row manifest hash 一致、`manifest_jsonb` 與 OOS window/K/embargo 欄位存在。
  - 用 registry OOS window/K/embargo 生成或校驗 `hidden_oos`，避免 payload lineage 或 payload hidden_oos 自證。
- `mlde_demo_applier`：
  - `should_create_live_candidate()` 改走 source contract。
  - `_build_live_candidate_payload()` 只在 source contract promotion-ready 時附帶 residual report + candidate manifest。
- `mlde_demo_applier_evidence_filter`：
  - capability probe 從 6-key 擴展到 12-key registry snapshot。
  - full schema 時 LEFT JOIN `replay.experiments`，帶出 status/expires/manifest/hash/OOS window/K/embargo。
  - 缺 FK 欄位時不引用 registry alias，保持 forward-compatible fail-closed。

## E2 對抗審意見處理

E2 指出 `10863cd4` 仍只是低階 builder，不驗 `replay.experiments`。本批採納：

- 把最小 patch 接點放在 MLDE producer read/hydration 層。
- source contract 要求 registry snapshot，不再只信 row id/hash。
- 保留 LG5 consumer gate，不在消費端補假 source。

未完成但明確保留：

- residual report 仍是 canonical payload/row pass-through + hash check，尚未落 durable residual report registry。
- hidden OOS registry 的 sealed/opened/consumed/invalidated 狀態機仍屬下一步 P1-B。

## 驗證

- `python3 -m pytest program_code/ml_training/tests -q`
  - `500 passed, 31 skipped`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_review_live_candidate.py -q`
  - `59 passed`
- `python3 -m py_compile` on touched producer / validator / LG5 files
  - PASS

## 邊界

- 無 DB migration。
- 無 DB write / runtime deploy / rebuild / restart。
- 無 auth、order、risk/strategy config、paper/live 狀態變更。
- 新 contract 會讓缺 registry snapshot 的候選 fail-closed；這是預期行為。
