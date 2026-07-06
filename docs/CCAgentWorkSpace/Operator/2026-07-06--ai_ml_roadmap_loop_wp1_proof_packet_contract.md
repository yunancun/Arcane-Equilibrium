# 2026-07-06 AI/ML Roadmap Loop — ProofPacket Contract

本輪自治工程 loop 選了 `WP1-PROOF-PACKET-V1`。

原因：`TODO.md` 的 standing Demo authorization 已過期，runtime/order-capable
路徑仍必須走 PM->E3->BB；在 source-only 範圍內，ProofPacket 是最高優先 P0
roadmap dependency。

完成內容：

- 新增 `program_code/ml_training/proof_packet_contract.py`。
- 新增 `proof_packet_v1` validator、hash、extractor 與 validation result。
- `proof_ready` 現在必須有 candidate identity、order/fill/context lineage、
  maker/taker fee、slippage、funding、markout、realized net PnL、controls、OOS
  split、source/input artifact hashes、code commit、Rust build SHA。
- cleanup / unattributed / proof-excluded fills 不能通過。
- `NO_MATCHED_FILLS` 是 blocker artifact，不是 training label 或 positive/negative
  proof。
- ProofPacket 不能宣稱 promotion_ready，也不能授予 order/probe/live/Cost Gate/runtime
  authority。

驗證結果：

- py_compile PASS。
- ProofPacket focused tests：`15 passed`。
- ML evidence adjacent tests：`60 passed`。
- cost-gate proof/promotion adjacent tests：`20 passed`。
- `git diff --check` PASS。

狀態：`ADVANCED`。本輪未停止，因此沒有輸出 stop packet。

機器可讀 artifacts：

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp1_proof_packet_contract.work_item.json`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp1_proof_packet_contract.effect_review.json`

PM report 正本：

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp1_proof_packet_contract.md`

邊界：沒有 runtime mutation、DB write、exchange/private read、MCP server、secret
access、order/probe、Cost Gate change、deploy、live/mainnet。

下一個 source-only work item：`WP2-PIT-DATASET-MANIFEST`。Runtime outcome collection
仍被 standing Demo envelope refresh 擋住，不能繞過 PM->E3->BB。
