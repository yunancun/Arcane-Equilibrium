# 2026-07-06 AI/ML 交易工程路線圖：挑戰 Maker-First 後的 PM 結論

PM sign-off: `SIGNED-WITH-GATES`

完整報告：

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_trade_engineering_roadmap_after_maker_challenge.md`

## 核心判斷

我不推翻 maker-first 報告的窄結論：在當前 Bybit 費率、成熟 perp universe、以被動吃
spread 作為主盈利槓桿，仍是 `NO-GO`。

但我拒絕把它外推成「AI 沒用」或「bot 沒有可工程化方向」。真正結論是：

1. mature-perp maker-first MM 不是主線。
2. M12 adaptive router 可保留為成本治理，不是 alpha。
3. AI/ML 方向要推，但必須從證據閉環開始，而不是讓 LLM/RL/MCP 直接交易。

## 建議主線

1. **P0：ProofPacket / candidate-matched outcome**
   - 先刷新過期 Demo loss-control envelope。
   - 只在 fresh E3/BB + same-window lease/BBO/order shape/Guardian/Rust authority 全齊後做 bounded Demo。
   - 產生 candidate-matched fill/fee/slippage，或明確 `NO_MATCHED_FILLS` blocker。

2. **P0/P1：Point-in-time evidence foundation**
   - dataset manifest、query/source/hash、label hash、split hash、proof exclusion、hidden-OOS 都要落地。
   - 沒有 PIT manifest 的訓練結果只能 research-only。

3. **P1：Supervised advisory**
   - 先做 q10/q50/q90 supervised edge/risk scorer。
   - Rust serving 只能吃 registry-approved artifact。
   - LLM/DreamEngine 只做 hypothesis、diagnosis、experiment design，輸出 `not_authority=true`。

4. **P1：Controlled Demo learning**
   - LinUCB/Thompson/bandit 只在真實 after-cost outcomes 出現後使用。
   - 每個變更都必須走 DemoMutationEnvelope、bounded delta、rollback、matched controls。

5. **P1/P2：挑戰剩餘 niche**
   - new-listing/event microstructure screen：offline、$0、pre-registered、holdout。
   - M12 router：shadow-only cost-reduction design。
   - MCP：source-only capability matrix，不進 runtime。

## 90 天節奏

- 0-14 天：解除 expired standing auth blocker，跑出第一個可重建 outcome 或明確 fail-closed artifact。
- 15-30 天：PIT manifest + outcome ledger + leakage/split gates。
- 31-60 天：registry-authorized supervised advisory + Python/Rust feature parity。
- 61-90 天：controlled Demo bandit + new-listing/event screen + M12 router shadow design。

## 不做

- 不做直接 AI trader。
- 不做 RL runtime。
- 不用 Bybit/IBKR MCP 下單、讀私有賬戶、做 proof 或 Cost Gate。
- 不因為想訓練 AI 而降低 Cost Gate 或繞過 Rust authority。

下一個實際可執行 blocker 仍是：

`P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`
