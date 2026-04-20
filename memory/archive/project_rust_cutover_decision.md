---
name: Rust 切換決策 + QA 審計結論
description: 2026-04-04 決策：放棄修 Python V2，全力 Rust。Python 真實成熟度 62/100，6 項功能是 FAKE/DEAD/UNREACHABLE。Kelly 延後 Phase 2（需 DB+Scorer）。
type: project
---

## Operator 決策（2026-04-04）

**放棄修復 Python V2，直接在 Rust 中做對。** Python 交��引擎將被淘汰。

## QA 審計結論

Python V2 真實成熟度：62/100。6 大謊言：
1. BB Reversion limit orders = FAKE
2. Kelly = UNREACHABLE (需 50+ trades)
3. FundingArb handle_leg_failure = DEAD CODE
4. BB Breakout volume/Donchian = UNREACHABLE (metadata 斷裂)
5. Shadow Decision Tracking = DEAD CODE
6. Dream Engine = ISOLATED

**Why:** Python V2 聲稱的功能有近一半是假的/死的/���可達的。Rust 引擎已 99.9% 獨立，直接在 Rust 中正確實現比修 Python 更有價值。

## 延後項（依賴 DB/DL）

- Kelly → Phase 2 (需 trading.fills + Scorer calibrated_prob)
- FundingArb 雙腿回滾 → Phase 1 (需執行狀態機 + trading.orders)
- Agent 調參 → Phase 3a (AGT-1 update_params)
- Shadow/Dream → Phase 2

**How to apply:** 所有新策略開發只在 Rust 中進行。Python 端只維護 API/GUI 層直到全面遷移。
