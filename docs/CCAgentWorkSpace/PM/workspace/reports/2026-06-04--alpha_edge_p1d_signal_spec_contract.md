# 2026-06-04 Alpha-Edge P1-D SignalSpec Contract

## 結論

本 checkpoint 把 Candidate EvidenceManifest 的 `spec_hash` 從「可任意填入
的穩定 hash 字串」收緊為 canonical `signal_spec` body 的 SHA-256。MLDE
live-candidate producer 與 LG-5 reviewer 現在都要求 payload 內有 canonical
`signal_spec`，且該 spec 必須與 manifest 的 `spec_hash`、`candidate_id`、
`family_id` 一致。

這仍不是 DSL、不是 durable hidden OOS state machine、不是 durable residual
report registry。它是 no-migration 的 metadata contract：避免只靠
`signal_spec_hash` 或 `factor_spec_hash` 字串就宣稱 candidate family /
PIT / residualization / hidden OOS policy 已被承諾。

## 完成內容

- 新增 `program_code/ml_training/candidate_signal_spec.py`
  - canonical 欄位為 `signal_spec`，schema 為 `signal_spec_v1`。
  - canonical hash 排除頂層 `spec_hash`，使用 sorted compact JSON。
  - 驗證欄位包含 candidate/family、hypothesis、horizon、inputs、
    `pit_contract`、universe/regime/cost lineage、feature schema、
    residualization、failure taxonomy、hidden OOS policy。
  - `future_data_allowed=True`、candidate/family mismatch、hash mismatch 皆
    fail-closed。

- `candidate_evidence_manifest.py`
  - `validate_candidate_evidence_manifest()` 新增 `signal_spec` 參數。
  - manifest `spec_hash` 必須等於 canonical signal spec hash。
  - 缺 spec → `pending_schema`；hash/candidate/family mismatch → `invalid`。

- `candidate_evidence_manifest_builder.py`
  - builder 從 source row / payload 讀 canonical `signal_spec`。
  - 有 spec body 時用 canonical spec hash 生成 `spec_hash`。
  - 只有 `signal_spec_hash` / `factor_spec_hash` 而無 spec body 時不能
    promotion-ready。

- `candidate_evidence_source_contract.py`
  - producer result 顯式攜帶 `signal_spec`。

- `mlde_demo_applier.py`
  - live-candidate payload 在 evidence source contract promotion-ready 時
    同步寫入 `signal_spec`、`demo_residual_alpha_report`、
    `candidate_evidence_manifest`。

- `governance_hub_live_candidate_review.py`
  - LG-5 reviewer 讀 payload `signal_spec`，並用它重新驗證 manifest。

## 驗證

- `python3 -m pytest program_code/ml_training/tests/test_candidate_signal_spec.py program_code/ml_training/tests/test_candidate_evidence_manifest.py program_code/ml_training/tests/test_candidate_evidence_manifest_builder.py program_code/ml_training/tests/test_candidate_evidence_source_contract.py -q`
  - `56 passed`
- `python3 -m pytest program_code/ml_training/tests/test_mlde_demo_applier.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_review_live_candidate.py -q`
  - `86 passed`
- `python3 -m pytest program_code/ml_training/tests -q`
  - `516 passed, 31 skipped`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_review_live_candidate.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py -q`
  - `77 passed, 1 skipped`
- `python3 -m py_compile` on touched source
  - PASS
- `git diff --check`
  - PASS

## 邊界

- 無 DB migration。
- 無 DB write/apply。
- 無 runtime deploy / rebuild / restart。
- 無 auth、order、risk/strategy config、paper/live 狀態變更。
- 本 checkpoint 不證明存在 alpha edge；只降低 evidence metadata 被字串
  hash / alias / payload 自證繞過的風險。

## 後續

- Durable residual report registry/table 比繼續堆 manifest contract 更急；
  需要 V### migration、Linux PG dry-run、double-apply、report body FK/hash、
  producer run lineage。
- Durable hidden OOS state machine 仍未落地；V049 欄位能承載 window/embargo/K，
  但缺 `sealed/opened/consumed/invalidated` 狀態轉移、`open_count`、actor、
  timestamps、audit event taxonomy。
- `orderLinkId` hardening 是 P2 exchange-facing 工作，應另走 BB/E3/E4。
