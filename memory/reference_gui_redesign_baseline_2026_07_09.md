---
name: gui-redesign-baseline-2026-07-09
description: GUI 大修基線備份指針(git tag gui-baseline-2026-07-09 回滾錨點)+S1 Terminal 方向+設計正本/樣品/IBKR 交接位置;Phase 0 未開工
metadata: 
  node_type: memory
  type: reference
  originSessionId: a478be41-ca11-4d17-b0fc-662328258b4b
---

改版前的 Console GUI 已做完整基線備份(operator 要求,用於後續開發對比參考+極端回滾),並鎖定重設計方向。

## 基線備份(durable,repo 內)
- **git tag `gui-baseline-2026-07-09`** @ commit `d077949fc`(61 files / 36,337 lines,scope=`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`)。三端已同步 + Linux 驗證。
- **回滾**:`git checkout gui-baseline-2026-07-09 -- <static path>`;**對比**:`git diff gui-baseline-2026-07-09 -- <path>`。
- 清單 + rollback/compare 指令 + 便攜鏡像 sha256 `d6a15818…`:`docs/archive/2026-07-09--gui_baseline_pre_redesign_manifest.md`(README 亦有指針)。便攜 tarball 未入 git,可用 `git archive` 在 tag 重生。

## 重設計方向(已鎖定,Phase 0 未開工)
- 視覺 = **S1「Terminal」**(單色 chrome+語義色+等寬數字+髮絲線扁平,冷調近黑);架構終局 = **絞殺 iframe→單文件 shell**(strangler-fig);框架 = **保留 Vanilla JS**;資訊架構 = **lane × environment**。
- 冷審計根因:iframe-per-tab / token 三處分叉+1,375 內聯 / KV 牆。內容守恒已證:210 面 KEEP115·RELOCATE38·MERGE26·COLLAPSE12·FLAG-DEAD19(零丟失;`app-learning.js` 孤兒=復活或退役決策)。

## 設計正本 & 樣品(位置)
- 設計正本 = `GUI-DESIGN-WORKING-DOC.md`(決策+canonical tokens+8 規則+守恒圖+Phase0 計劃+§10 待深化議程)+ 4 份深度規格 `design/{01_typography,02_layout,03_copy,04_identity}.md`(排級/排版/文字/美學)+ decision brief。**現於 session scratchpad(ephemeral)+ operator 有 SendUserFile 副本;Phase 0 開工時提交進 repo(建議 `docs/execution_plan/`)才 durable。** 下一步入口 = §10 議程(accent/icon/密度/hero KPI/圖表/雙語/亮色/空狀態/lane 切換/motion)。
- 樣品(durable URL):S1 採用 `https://claude.ai/code/artifact/07c769ec-b340-4118-812f-27decdaa2ea8`;S2 備參 `https://claude.ai/code/artifact/23c24c3a-8b5e-4586-ac35-e33a06a82b7b`。
- **設計參考圖鑑 v2「玄衡儀」(2026-07-09 探索 session,repo 正本)** = `docs/references/2026-07-09--gui_redesign_reference_board_v2.html`(commit `68de12122`;artifact 版本記錄含 v1 五方向 `https://claude.ai/code/artifact/8da08872-cab2-4a34-9f99-257f6a8384a8`)。frontend-design skill 已裝 `~/.claude/skills/frontend-design/`。
- **✅ 2026-07-10 operator 裁決:玄衡儀主張認可+暖調近黑+light/dark 雙主題真目標;Phase 0 放行**(取代上行「S1 冷調 current authority」的等待態)。**設計正本已全部入 repo `docs/execution_plan/gui_redesign/`**(commit `a35ec287b`):working doc(§0 裁決+canon 9-11 朱印/青銅/銘文紀律)+ design/ 四規格(scratchpad 救援)+ **tokens.css 雙主題正本(玄夜=玄底帛字/帛晝=帛底玄字)** + Live 視圖高保真樣品 `2026-07-10--xuanheng_live_view_sample.html`(雙主題+雙密度+衡樑+朱印;artifact `https://claude.ai/code/artifact/d6177c16-5840-42ee-82d4-a17c03132ab7`,fragment 版;repo 版是完整 HTML 文檔,artifact 需去殼——完整文檔直接發 artifact 會嵌套渲染全黑)。**next=Phase 0 工程執行(tokens.css 抽取進 61 檔+1375 inline style 清理)按 working doc §9 role chain PM→PA→E1a→E2→E4 派發**。
- **2026-07-10 loop 基建(`dcdc20b93`)**:自動推進協議=`docs/execution_plan/gui_redesign/LOOP-DRIVER.md`(每輪協議/終態七條/治理硬邊界:IBKR read-only·AMD-2026-07-09-01 未 ACK 不做凭證寫 UI·engine restart 類只記 NEEDS-LINUX-RUNTIME 不執行);持久進度帳本=同目錄 `PROGRESS.md`(P0-P3+18 tab 矩陣+終驗收 V1-V8+輪次日誌)。operator loop 指令:`/loop 執行 GUI 大改自動推進輪:嚴格按 srv/docs/execution_plan/gui_redesign/LOOP-DRIVER.md 協議做本輪工作,更新 PROGRESS.md,自排下次喚醒;全部完成即停`。

## IBKR 後端線(已交接他 session)
承 [[project_2026_07_08_ibkr_stock_etf_readonly]]:AMD-2026-07-08-01 已 land(G0/G0.5/P0 @ `c66338e8b`,只讀/零真錢/live 拒絕),next=P1 密鑰槽 loader。啟動 prompt = `scratchpad/gui/IBKR-BACKEND-STARTUP-PROMPT.md`。GUI 大修與 IBKR 後端是兩條並行線,本索引屬 GUI 線。
