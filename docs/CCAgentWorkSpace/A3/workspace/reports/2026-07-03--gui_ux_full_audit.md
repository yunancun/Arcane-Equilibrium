# 2026-07-03 GUI UX 全盤審計(A3 軸)——冷酷對抗審計 R2

> 出處聲明:本檔由 conductor 於 2026-07-04 自 Stage 2 run `wf_6dc68c2f-4a0` 原始結果代為落盤——A3 軸 agent 因月度 spend limit 中斷未寫出報告檔;finding 內容為該軸 agent 原文,對抗複核 verdict 為 resume 補票後全票結果。正本:PM/workspace/reports/2026-07-03--cold_audit_stage2_raw_result.json(v1)+ 本輪 resume v2。

## Confirmed(雙質疑者全票,4 條)

- **[HIGH]** Console header 全局 mode badge 硬編碼 'shadow_only'，永不更新 — 常駐頂欄的假模式資訊
  - anchor: `mode-tag` | defect_type: hardcoded-config, fake-success, drift-source-runtime
- **[HIGH]** 「緊急停止」與「停止 Live」呼叫完全相同的 endpoint+body，但 modal 承諾不同語義（封鎖引擎/需手動解除 vs 停止授權租約）
  - anchor: `doEmergencyStop` | defect_type: duplicate-logic, fake-success, doc-stale, other
- **[MEDIUM]** Risk Governor 降級 override：pending_approval 分支回 ok:true，前端顯示『風險等級已降級』成功 toast（fake-success）
  - anchor: `submitRiskOverride` | defect_type: fake-success, over-gate
- **[MEDIUM]** README tab 表（A3 的 tab 結構權威源）與 console 實際 TABS 漂移：漏 stock-etf 與 charts、仍列已移除的 phase4
  - anchor: `TABS` | defect_type: doc-stale, dead-code, lineage-gap

## MEDIUM/LOW/INFO(未進對抗複核,16 條)

- [INFO] A3 總評 7.5/10（術語友好 7 / 操作流完整 7 / 學習曲線 7.5 / 錯誤提示 8）— 較 2026-05-30 的 8.0 下調 | `a3_score_v20260703`
- [MEDIUM] Risk Governor 降級 override：pending_approval 分支回 ok:true，前端顯示『風險等級已降級』成功 toast（fake-success） | `submitRiskOverride`
- [MEDIUM] README tab 表（A3 的 tab 結構權威源）與 console 實際 TABS 漂移：漏 stock-etf 與 charts、仍列已移除的 phase4 | `TABS`
- [MEDIUM] Stock/ETF IBKR tab：18 個第一屏 metric 卡全英文工程術語、零中文、零解說 — 全 console 唯一無雙語的 tab，且認知密度超標 | `se-metric`
- [MEDIUM] Rust 引擎宕機無全域跨 tab 告警：engine_alive 只在 system tab 一張 metric 卡 + agents tab chip，console 側欄/header 無引擎狀態燈 | `loadEngineAlive`
- [MEDIUM] 源碼-runtime 漂移：本輪全部『已修復』判定僅對 Mac 源碼 head 成立，trade-core runtime 落後 origin/main 164 commits，線上 console 是否含這些修復未驗證 | `BUILD_TS`
- [LOW] 側欄footer『Auto-refresh 15s』與實際 SIDEBAR_REFRESH_MS=30000 不符 | `SIDEBAR_REFRESH_MS`
- [LOW] 破壞性操作 modal 缺『具體影響』數據：Demo/Live close-all 確認框無持倉數量與預估 UPL | `doDemoCloseAll`
- [LOW] 審計感知 UX（ux-checklist §5）系統性缺席：寫操作 toast 無 trace_id、無『最近 5 次 actor+ts+結果』、多數 dashboard 無採集時間 footer | `ocToast`
- [LOW] 簡繁中文混排遍佈治理/風控視圖，同一畫面同一概念兩種字形 | `gov-sm-note`
- [LOW] 首次進入 console 僅見 core group 3 tabs（含最生僻的 Stock/ETF），交易/治理 group 默認折疊；Global Mode Control 卡藏於 dev-support 開關後 | `TAB_GROUP_DEFAULT_OPEN`
- [LOW] UTC+local 雙時區標註基本缺席：console 時鐘僅 zh-CN 本地時間，全 GUI 僅 4 處 UTC 字樣 | `clock`
- [LOW] 設置/風控殘留英文-only placeholder 與 toast | `cost-note`
- [INFO] Legacy GUI /gui（index.html）仍註冊路由並保留 disabled paper 下單表單 | `gui_index`
- [INFO] tab-governance.html:1159-1160 stale 註釋仍引用不存在的 loadGovernance()（2026-05-30 advisory 未清） | `loadGovernance`
- [INFO] 正向確認：既往 A3 findings 全數修復且守住 — A3-GUI-009/010/011 已修（源碼含 A3 編號註釋）、native confirm()/prompt() 全滅、SM 術語加解說、學習 Tab 雙語、engine_alive 上第一屏、Demo close-all modal 補齊 | `classifyLiveMutation`

## Negative-space 自審 assumptions(9 條)

- {'note': '報告未落盤：本輪 A3 toolset 為 read-only（無 Write/Edit/Bash），無法寫 workspace report 與 memory.md 追加。全文以本結構化輸出承載，report_path 為建議持久化目標；沿用 2026-05-30 precedent 由 PM 驗證後 verbatim 持久化並補 memory 3 行結論。', 'why_unproven': '工具硬限制，非證據不足', 'axis': 'A3'}
- {'note': 'runtime 實際 GUI 版本未驗證（trade-core 線上 console 的 BUILD_TS / 是否含本輪確認的修復）。允許的 ssh trade-core read-only 本輪未執行。', 'why_unproven': '本輪優先覆蓋源碼全 tab 靜態走查；TODO v738 顯示 runtime behind 164 commits，已列為獨立 ASSUMPTION finding，PA 可用單條 ssh grep BUILD_TS 快速 re-probe', 'axis': 'A3'}
- {'note': '無 browser/preview 工具 — 全部結論來自 click-handler→API→state 靜態 trace；實際渲染（CSS 疊層、toast 遮擋、mobile <860px sidebar 隱藏後關鍵資訊是否可達、iframe 懶載入競態）未經實操驗證。', 'why_unproven': '環境未提供 browser 類工具；ux-checklist 工作流已預留此降級模式並要求標註', 'axis': 'A3'}
- {'note': 'node --check / 等效語法檢查未跑：本輪引用的 JS 檔（tab-live.js、risk-tab.js、earn-tab.js、tab-stock-etf*.js）語法健康未驗證。', 'why_unproven': '無 Bash 工具；per GUI sign-off SOP 該步屬 E1/E2 職責，A3 只標記', 'axis': 'A3'}
- {'note': 'WCAG 2.1 AA 對比度/鍵盤導航全量未測（design:accessibility-review 未展開）：僅確認 mode-badge 元件有 role/aria/tabindex 與 residual banner 的 role=alert；色彩對比值、focus order、SR 動線未量測。', 'why_unproven': '無渲染環境無法取 computed color；建議下輪帶 browser 工具專項', 'axis': 'A3'}
- {'note': '認知自適應 UX 三元件（CognitiveModulator 壓力水平 / OpportunityTracker 錯過機會 / DreamEngine 建議標示）僅做檔案級 grep 定位（tab-paper/tab-risk/tab-agents/common-modals 有命中），未逐一走查其呈現是否符合『非指令標示、不造 FOMO』要求。', 'why_unproven': '命中面多在 requiresPaperEngine 的 legacy paper 視圖（默認隱藏），本輪時間預算讓位給新 stock-etf surface 與 live 寫路徑；PA 可 re-probe tab-paper.html + risk-tab.js 的 cognitive 區塊', 'axis': 'A3'}
- {'note': '後端回應契約僅抽驗 3 條（risk/override、live session/stop、GovernanceResponse）；其餘 40+ 寫 endpoint 的 200-with-error 形態沿用 2026-05-30 深查結論未逐條重驗。', 'why_unproven': '上次 deep-dive 已全表掃過且本輪抽驗未發現該表結論被推翻；重掃全表成本高、邊際低', 'axis': 'A3'}
- {'note': 'Earn tab 5-gate 即時性、canary promote、auth renew T3 流程本輪未重走（上輪 CLEAN）。tab-replay / tab-monitoring / tab-edge-gates / tab-phase4（無入口）只確認 read-only 屬性未逐行審。', 'why_unproven': '增量審計策略：優先新 surface 與上輪 OPEN/NEEDS-MORE 項；read-only tab 的誤操作風險為零', 'axis': 'A3'}
- {'note': 'i18n_zh.js 對照表覆蓋率未與各 tab 實際 key 使用 diff（mode_badge.* fallback 鏈已讀，全表未驗）。', 'why_unproven': '需要腳本化 key 抽取比對，read-only 環境下人工 diff 成本不成比例', 'axis': 'A3'}

## Stage 3/4 銜接
- 分級與修復排程見 PA/workspace/reports/2026-07-03--cold_audit_validated_fix_plan.md;終審見 PM/workspace/reports/2026-07-03--cold_audit_pm_final.md。