---
name: project_2026_07_08_profit_first_autonomy_loop
description: "承 maker-nogo 但拒『窮盡剩 operator-hand』;standing profit-first 自主 loop——TradeBot 自跑 discover→admit→execute→review→learn,現 READY_FOR_PM_E3_DISPATCH 卡 stale BBO manifest,零 order/fill proof"
metadata:
  node_type: memory
  heat: 0
  type: project
  originSessionId: b8f94432-3891-440a-ba13-f17896dd26d5
---

maker-first NO-GO(2026-07-06)後,operator **拒**「不賺錢=無可工程化方向、剩餘全 operator-hand」的外推,改指令把盈利責任交回 bot 自主循環。標準化為 standing 自主 loop:spec `docs/agents/profit-first-autonomy-loop.md`(穩定行為契約)+ 加速器 `docs/agents/profit-first-fast-demo-promotion-loop.md`;current task state 在 `TODO.md`(v763)。承 [[project_2026_07_06_maker_first_nogo]]、[[feedback_active_profit_unconventional_mandate]](這是 mandate「implement」的落地)、[[project_2026_06_13_profit_diagnosis_searchspace_reconfirm]](推翻其「operator-hand only」終態)。

**loop 做什麼**:TradeBot 自主 discover(動態選候選)→ admit(過 gate)→ execute(bounded Demo)→ review(after-cost)→ learn,全程鎖在 operator loss-control envelope / standing 授權 / Rust authority / Decision Lease / auditability 邊界內。穩定 loop 行為寫在 agent 文檔,**當前候選細節不寫進 spec**(TODO 才是活狀態)。

**當前動態候選**:`ma_crossover|NEARUSDT|Buy`,avg net **64.983bps** / outcome_count **5058**(來自 runtime `_latest` Cost Gate artifacts;candidate packet sha `02c7eec6`)。注意這是 loop 內部 after-conservative-cost 篩選數,**非**已實現真成交。

**現狀=大部分管線 DONE,但零盈利 proof、尚未 order-capable**:
- standing Demo 授權真實且候選對齊:runtime `standing_demo_operator_authorization.json` sha `05fe07f5`,mode 0600,cap `954.46746768` USDT,expiry `2026-07-09T00:12:30Z`,**不授予 order/probe/live 權限**。
- machine-readable loss-control envelope、bounded-probe preflight、touchability、placement、authority-readiness、canonical soak plan(sha `a296365e`)、active-order wiring contract(sha `cf2c9ff2`)全部已建且 `READY`。
- posture `READY_FOR_PM_E3_DISPATCH`,substatus `ORDER_CAPABLE_PACKET_BLOCKED_ONLY_BY_STALE_NOORDER_WINDOW`——order-capable packet sha `305774b2` 唯一 blocker=stale renewed BBO manifest(`17a3a426`,綁舊 checkpoint `08f7e957`,不能在 `c66338e8` 重用)。
- **關鍵誠實事實**:strict NEAR 掃描 sha `ca4bf9cb` 有 **零 candidate-matched order/fill/fee/slippage 證據**;34,574 rows 是 stale ETH ledger 非 proof。**至今無任何 Bybit 呼叫 / Decision Lease / order / probe 執行過**。全 fail-closed:無 live、無降 Cost Gate、無 `_latest` promotion。

**How to apply**:這是現行盈利工程主線,不是 dormant;但它「有候選、有學習列、無盈利 proof」。任何 order-capable 動作仍需獨立 same-window PM→E3→BB packet + 新鮮 Decision Lease/BBO/order-shape + Guardian/Rust authority,一個 invocation window 內完成。read/write 分離不因 loop 而鬆動。
