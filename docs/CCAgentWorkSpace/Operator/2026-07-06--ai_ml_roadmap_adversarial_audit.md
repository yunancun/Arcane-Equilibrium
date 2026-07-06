# 2026-07-06 AI/ML 路線圖對抗性審計摘要

PM verdict: `PASS-WITH-CONDITIONS`

完整報告：

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_adversarial_audit.md`

## 結論

方案有效，但只能按 gate 推進，不能按日曆硬推。

沒有發現根本性錯誤。它抓住了真正 blocker：缺 candidate-matched、after-cost、可重建 outcome。它也沒有越過 Rust authority、Decision Lease、Guardian、Cost Gate、MCP/交易所邊界。

## 必須收緊的點

1. `ProofPacket` 不是現有完整類型，第一張工程票應該先做 `proof_packet_v1` 契約/validator/tests。
2. PIT manifest 是硬 blocker；現有 training path 仍有 trailing `now()` 類窗口，不能 promotion。
3. q10/q50/q90 與 ORT loader 已有基礎，但 registry-authorized serving 還要補 dataset/label/split/leakage/serving metadata。
4. `DemoMutationEnvelope` 需要正式化，或明確映射到現有 `mlde_demo_applier` application record。
5. new-listing/event screen 必須 pre-register，否則會變成挑窗。
6. M12 router 先做 spec refresh，定位 cost reduction，不是 rebate/alpha。
7. MCP 只能 pinned source-only matrix；不得 credentials/server/API/private read/order。

## 下一步建議

下一個安全工程入口只能是三選一：

- `proof_packet_v1` source contract；
- PIT dataset manifest contract；
- current-head standing envelope refresh under E3/BB。

不要先做 RL、MCP runtime、M12 implementation、bandit runtime、model promotion、live/tiny-live 或 Cost Gate lowering。
