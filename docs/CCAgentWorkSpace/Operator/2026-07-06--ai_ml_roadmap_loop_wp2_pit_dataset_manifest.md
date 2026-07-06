# 2026-07-06 AI/ML Roadmap Loop — WP2 PIT Dataset Manifest

本輪 continuous loop 選了 `WP2-PIT-DATASET-MANIFEST`。

原因：WP1 ProofPacket 已有 source contract，但 E2 指出 provenance 仍太 generic；
必須先有 named PIT dataset manifest、rebuild/hash、feature/schema lineage、
matched-control artifact hash、row-backed fill source artifact hash，才能讓
ProofPacket 真的可作機器檢查的 proof input。

完成內容：

- 新增 `program_code/ml_training/pit_dataset_manifest.py`。
- 新增 `pit_dataset_manifest_v1` validator、hash、extractor。
- 新增 `program_code/ml_training/pit_dataset_manifest_builder.py`。
- builder 只吃 caller-provided source mapping / synthetic rows，不讀 env、DB、檔案、
  runtime、network、exchange 或 secret。
- ProofPacket `PROOF_READY` 現在必須帶 valid
  `provenance.pit_dataset_manifest`。
- PIT manifest candidate_scope 必須和 ProofPacket candidate_identity cross-bind。
- `order_allowed` / `promotion_allowed` / `live_enabled` 等 authority alias 會
  fail closed。
- `NO_MATCHED_FILLS` 仍是 blocker artifact，不要求 PIT manifest。

派工結果：

- PA design：ready with concerns。
- E1/E1a implementation：PASS。
- 初次 E2/QA 找到 cross-bind / authority alias 問題。
- E1a 修補後，E2 PASS、E4 PASS、QA ACCEPT。

驗證結果：

- py_compile PASS。
- focused PIT/ProofPacket tests：`36 passed`。
- adjacent ML evidence tests：`81 passed, 1 skipped`。
- cost-gate proof/promotion tests：`20 passed`。
- `git diff --check` PASS。

本輪 state：

- `ADVANCED`
- next work：`WP3-REGISTRY-SERVING-PARITY`

機器可讀 artifacts：

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp2_pit_dataset_manifest.work_item.json`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp2_pit_dataset_manifest.effect_review.json`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp2_pit_dataset_manifest.state_packet.json`

PM report：

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp2_pit_dataset_manifest.md`

邊界：沒有 runtime mutation、DB read/write、exchange/private read、MCP server、
secret access、order/probe、Cost Gate change、deploy、live/mainnet。
