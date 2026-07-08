---
name: project_2026_07_06_maker_first_nogo
description: "maker-first/做市執行軸經 fill_sim 雙窗實測判 NO-GO;不賺錢=無方向alpha+執行edge被費用階梯鎖住,非「缺AI/太機械」"
metadata: 
  node_type: memory
  heat: 0
  type: project
  originSessionId: e4edc993-6380-45df-9d97-f38b704f30ed
---

operator 問「能否用 maker-first / 做市把 bot 從不盈利+太機械救起來,達到 institutional AI trading」。主會話派 read-only $0 四-agent wave(QC/BB/MIT/PA)+ 跑既有 `fill_sim`(program_code/research/microstructure/fill_sim.py)雙窗(fast-3h + winA-72h,~3400 萬筆 recorded `market.l1_events`)。

**裁決:maker-first 作為工程盈利槓桿 = NO-GO @ Bybit VIP0,三重確認**：
- BB:VIP0 maker = **+2.0bps 費用非 rebate**;常規 VIP 階梯到 Supreme($500M/30d)才 0.0%,永不轉負;真 rebate 只有 institution-gated MM program(KYB 法人+BD+搶全站 maker 佔比)=operator 資本/BD 槓桿非工程。API 不是 blocker(linear 20/s、無 cancel-ratio 罰則、PostOnly 合規)。
- QC:流動性大幣半價差 ≈ +2bps 費用,毛激勵 ≈0。
- `fill_sim`:**0/172 格淨正**(fast 0/72 + winA 0/100),最佳格 ADAUSDT −3.2bps,front-of-queue 也負,51 個 walk-forward feature 0 個過 holdout,break-even 需 maker fee ≤~0.4bps/side。**寬價差救不了**(adverse selection 隨價差同步放大=工具預登記的 wide-spread tension)。

**對兩問題的硬答案**:不賺錢**不是**因「缺 AI/太機械」,而是 (a) 無方向 alpha(承 profit-diagnosis)+ (b) 執行 edge 被鎖在我們用交易量爬不上的費用階梯後。往下單路徑塞 LLM/agent 造不出被費用牆+alpha 缺口排除的 edge。真正缺的 institutional 能力=dormant M12 `order_router.rs` 自適應 router(0-caller `unimplemented!()`)——但那是**成本削減非 alpha**。

**仍開著(未判死,守 mandate 不從一角落判全市場)**:①全新上市頭幾小時寬價差捕捉(20-100bps,不在成熟永續集,$0 可離線螢幕);②CP-3 完整多-regime 累積(recorder+cron 被動累,費用牆 regime-無關故難翻);③infra-tier 改(資本→VIP/MM,operator 決策)。

**演變軌跡**:本 session 我初始 thesis「熱路徑硬編碼 naive taker + 執行智能全 dormant」被 PA 代碼層半-證偽——maker/PostOnly entry 其實 live(`use_maker_entry=true` demo+live);我 grep 到的 `order_type:"market"` 全在 `#[cfg(test)]` fixture;taker 牆在**出場腿**且是微結構現實(passive 出場不可靠成交)非代碼缺陷;真 dormant 只有 M12 自適應層。教訓:grep 表象≠結論,對抗驗證(BB×QC×PA×fill_sim)把樂觀 pitch 削回地面。

**運維教訓**:detached 長 research job(fill_sim,reparent 到 init)存活於啟動它的 agent 之 idle-kill;其 liveness=遠端 PID+輸出 artifact,與 agent 無關——**TaskStop 前先診斷**。我這次誤停了正在恢復的 QC,靠主會話讀 durable JSON 救回(零數據丟失)。

證據 SHA:repo commit `5d1622994`(PM 報告+Operator pointer+per-symbol CSV+BB/MIT/PA wave memory,三端同步)。報告:`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--maker_first_microstructure_feasibility_verdict.md`。承 [[feedback_active_profit_unconventional_mandate]]、[[project_openclaw_positioning]];補 profit 弧(alpha 搜索軸先前已窮盡,本次補執行軸)。

**演變軌跡(2026-07-09):** 本 NO-GO 事實不變(TODO 留 mature-perp pivot no-repeat 標記),但「仍開著」的 niche + mandate 已被後續主動建設接手:operator 2026-07-05+ 指令 standing profit-first 自主 loop([[project_2026_07_08_profit_first_autonomy_loop]])+ AI/ML 成熟度路線圖 WP1-WP7([[project_2026_07_07_ai_ml_maturity_roadmap]]);另闢非-Bybit 資產類 IBKR stock/ETF read-only 軸([[project_2026_07_08_ibkr_stock_etf_readonly]])。「alpha 搜索軸已窮盡」是點狀,非當前姿態。
