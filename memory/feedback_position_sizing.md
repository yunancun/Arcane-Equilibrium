---
name: Position Sizing 偏好
description: 用戶對交易倉位大小和智能資本管理的偏好設定
type: feedback
---

用戶偏好每筆交易最大虧損 = 總額的 3%，同時部署最多 25 個幣種。

**Why:** 之前 risk_per_trade_pct=1-2% 加上除以 active_count，導致每筆只有 ~$20 名義，手續費吃掉所有利潤。

**How to apply:**
- risk_per_trade_pct = 3.0（max loss per trade as % of balance）
- max_symbols = 25
- qty 必須動態計算（每次下單時根據當前餘額重算，不在啟動時鎖死）
- 用戶希望 AI 能自動做資本再分配：當餘額不足但有好機會時，自動關閉低潛力盈利單或無望虧損單以投入新機會
- 用戶不希望設太多硬限制，偏好 Agent 根據市場狀況自主判斷
