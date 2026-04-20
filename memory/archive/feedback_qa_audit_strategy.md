---
name: 策略/模型改動強制 QA Audit
description: 任何涉及策略或模型的改動，E2+E4 之後必須額外跑一輪 QA 嚴格審計，再 commit
type: feedback
---

任何涉及策略（strategies）或模型（indicators/signals/ML）的改動，完成 E2 審查 + E4 回歸後，必須額外派發一輪 QA Audit。

**Why:** 策略和模型是直接影響交易損益的核心邏輯，Python V2 的 6 項 FAKE/DEAD 功能就是缺乏嚴格 QA 的後果。用戶要求對這類改動有更高的驗證標準。

**How to apply:** 工作鏈變為 E1 → E2 → E4 → **QA Audit** → commit。QA 審計需檢查：邏輯正確性、邊界條件、與其他策略的交互、參數合理性、是否有 FAKE/DEAD code。
