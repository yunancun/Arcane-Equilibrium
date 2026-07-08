---
name: feedback_active_profit_unconventional_mandate
description: "operator 鐵則——市場必然可主動盈利,禁範式陷阱,須用各 lens 原生數學探結構性/機械性 edge,discover AND implement"
metadata: 
  node_type: memory
  heat: 0
  type: feedback
  originSessionId: e4edc993-6380-45df-9d97-f38b704f30ed
---

operator 鐵則(2026-06-14):**市場必然可主動盈利**,「增加投入 / 被動等數據」= 消極,不接受。

**Why:** 我被抓的失敗模式=所有 NO-GO 都死於同一個測試(線性 IC × OHLCV × beta 殘差 × taker 成本牆 = 只為「方向性 taker 預測」設計),窮盡那一個角落卻誤判整個市場無 edge——這是範疇錯誤(category error),不是市場真的無 edge。

**How to apply:** 須用各 lens 的**原生數學**評估,而非把每個 lens 都塞回「方向預測」的測試:做市(Avellaneda-Stoikov 庫存/spread capture)、統計套利、Hawkes、資訊論、delta-carry、跨所。偏**結構性·機械性 edge**(靠市場結構,非靠預測)。要 **discover AND implement**,不是只研究。

**演變軌跡(mandate 的真實世界檢驗,非推翻):**
- 2026-07-06:依此 mandate 探**做市原生數學**(非 taker 角落)——`fill_sim` 3400 萬筆 L1 雙窗,結果=maker-first 在我們 VIP0 費用階梯下 NO-GO(0/172 格淨正,break-even 需 maker≤0.4bps)。**這不違反 mandate**:我們正確地用了原生數學、避開了 taker 陷阱,得到的是「edge 存在但被 infra-tier(費用階梯)鎖住」的誠實結論——即「可盈利」的真實約束是**資本/交易所 tier**(operator 槓桿),非模型或執行智能。詳見 [[project_2026_07_06_maker_first_nogo]]。仍未探:新上市寬價差 niche、事件/跨所軸。承 [[project_2026_06_13_profit_diagnosis_searchspace_reconfirm]]。
- 2026-07-05+:operator 把 mandate 的「implement」正式落地——指令 TradeBot 跑 standing **profit-first 自主 loop**(discover→admit→execute→review→learn,[[project_2026_07_08_profit_first_autonomy_loop]])+ 建 **AI/ML 成熟度路線圖 WP1-WP7**(證據閉環,[[project_2026_07_07_ai_ml_maturity_roadmap]]);另開非-Bybit **IBKR stock/ETF read-only** 研究軸([[project_2026_07_08_ibkr_stock_etf_readonly]])。mandate 由「探索受 infra-tier 約束」進入「主動工程建設」階段,非被推翻。
