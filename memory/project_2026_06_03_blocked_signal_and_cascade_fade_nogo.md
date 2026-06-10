

---

## [index-archive 2026-06-10] 原 MEMORY.md 索引條目全文(壓縮索引前歸檔,內容為當時點狀態)

- [被攔信號反事實 + H2 cascade fade 雙線 NO-GO (2026-06-03)](project_2026_06_03_blocked_signal_and_cascade_fade_nogo.md) — operator 要求嚴格深挖被 gate 攔下信號若放行盈虧(dream 反事實,盈利導向)；建 12h live monitor(trade-core:/tmp/openclaw/monitor_12h/)。**兩條結構性 alpha 線雙雙 NO-GO，同根因=down-market beta 偽裝 edge**：①被攔信號 grid_short_60m MIT beta 分解 demeaned-α −1.25bps t=−0.56(零)、鏡像 short+20.5/long−25.4 翻號=beta，cost_gate 0 誤殺(與 [[project_2026_06_01_fail_closed_gate_stack_root_cause]] 收斂，blocked-space=gate 校準檢查非 alpha 礦)②H2 cascade fade 280 事件(40× 先驗) 全\|t\|<1.3、payoff 負 Kelly、dominant_side 不對稱 short-fade 隨 horizon 放大=beta(與 QC 05-30 observe_more 收斂)。**元發現 BTC 17d −13.92% 此 regime 任何方向策略短 bias=趨勢 beta→強制 beta 中性化**。陷阱:label_net_edge_bps blocked=V084 佔位0、cost_gate「拒99.9%」tick 偽複製~150x、**pg_stat n_live_tup 不可靠須 count(*)**、market.klines(1m/140萬)/liquidations(140k/17天)其實滿的。既有 Dream 管線(V031) MIT 指控「expected_net_bps=噪音公式」**經獨立核查證偽=過度警報**(噪音公式在不INSERT的replay路徑;7505 dream row 是啟發式投影 abs(avg)×min(0.5,conf) grounded 真avg;blast=demo-only advisory;結構=FILLED-cell 提案不評 blocked 屬 by-design)→Option A 落 cd01eb92(payload 加 kind 欄+註解防誤讀,E1→E2 PASS);**教訓 MIT 行號+框架需 grep 核查**。資產 dream_counterfactual.py+beta_quant.py+cascade_fade_eval.py+QC 8-gate stack；剩 H3 funding carry 未評；承 [[project_2026_05_31_v58_alpha_pivot]]
