---
name: 可調參數必須真實可調，禁止假功能
description: Agent 可調參數必須在 Phase 3a 中真正被 Agent 發現和調整，不能又做成死代碼/假功能
type: feedback
---

所有標記為 "Agent-adjustable" 或 "pub" 的策略參數，必須滿足：

1. **Agent 必須知道它能調什麼** — Phase 3a StrategyParams.param_ranges() 必須真實列出所有可調參數及其範圍
2. **Agent 必須在部署前真實調整** — 不能用默認值直接上線，Optuna/Agent 必須在 Paper 環境中跑過調參
3. **調參結果必須持久化** — 調好的參數寫入 DB，下次啟動從 DB 讀取，不回退默認值
4. **驗證 checklist** — 每個 "Agent-adjustable" 參數在 Phase 3a E2 審查時必須驗證：
   - param_ranges() 是否包含此參數？
   - Optuna search space 是否覆蓋此參數？
   - Agent update_params() 是否能修改此參數？
   - 測試是否驗證非默認值下策略行為正確？

**Why:** Python V2 的 BB Reversion limit orders 就是典型的假功能——參數存在但代碼無分支。EMA alpha=0.01 也差點成為寫死的錯誤值。用戶明確要求：發現問題→解決問題，不留問題，不做假功能。

**How to apply:** Phase 3a 開發 StrategyParams 實現時，每個策略的 param_ranges() 必須覆蓋所有 pub 參數。E2 審查必須對照策略 struct 的 pub 字段和 param_ranges() 返回值做交叉驗證。
