# GUI 大改 · 進度帳本(loop 持久狀態;協議見 LOOP-DRIVER.md)

## 狀態欄
- **STATUS**: IN_PROGRESS
- **CURRENT**: P0.4 C6d-1/2/3 ⚠**AWAITING-OPERATOR gate**(族B real-money 標記→--live[PA 強推]vs 灰;T3 是否加 .seal-mark render 變更)——R32 本輪 AskUserQuestion 提 operator;答覆後開 C6d-1(族A)→C6d-2(tab-system 最高審)→C6d-3(common.js)
- **LAST-COMMIT**: 004e08936(P0.4 C6d-4 漸層塌平+killswitch→--neg;E2 獨立對抗核 PASS 零 finding)
- **C6d micro-spec 已出(§13,`493864cb3`)+ 子批拆分**:PA grep 細化 §2.3「紫=authority」為三族——**族A** authority chrome→中性化(T3 fg→--text-secondary/gov-btn→青銅·中性/live-btn→--accent,6 檔)、**族B** live/real-money→**--live**(tab-system 實盤 labels/confirm-live-guard/warn-box--live/mode-btn--live/oc-chip-live;PA canon 6 保 salience 裁決)、**族C** strategy 紫→DEFER(dead-data 建議刪)。漸層→--live-bg/--bg-raised、killswitch→--neg。子批序:**C6d-4**(機械,先)→ **⚠operator gate**(族B --live vs 灰§2.3-literal;T3 是否加 .seal-mark render 變更)→ C6d-1(族A)→ C6d-2(tab-system real-money,最高審)→ C6d-3(common.js 共用)。**gate 將於 C6d-1/2/3 開批前提 operator**(C6d-4 無需 gate)
- **C6 子批(hex→token,大批分)**:C6a 非交易 tab ✅ / C6c 共用 JS ✅ / C6b 交易 tab ✅ / C6d 可見美學(拆 C6d-1~4,§13 micro-spec;C6d-4 先做,C6d-1/2/3 operator-gated)/ C6e 殼層 styles.css 119(Phase3 目標,defer or 非-legacy);A3 雙主題目視全 defer Phase0 全審(Mac 無法真渲染)
- **帛晝(亮主題)就緒前置(C6c 五-lens MED+LOW forward-pointer)**:多面板底仍硬編碼冷調 rgba(13,17,23,α)/rgba(56,139,253,α)/rgba(139,148,158,α),tokens.css 無泛用 alpha/overlay token 可機械映射→帛晝下深字疊深底低對比(WCAG <4.5:1,尤 --text-secondary/--muted 標籤);**非本批回歸**(diff 未觸這些 rgba),但帛晝可交付前須新增專屬 alpha token 並 tokenize(PA 決策,非機械 swap);strategy 身份色整組(common-formatters 5 dead-data hex+common.js 4 --strategy-color)defer C6b/C6d,建議刪 dead-data 勿當權威暖色(defer-audit#0/#1)
- **canon 6 --live pass 待辦(來自 C3a/C4b/C6b forward-pointer)**:live/auth marker 現落 --neg,未來獨立 pass 逐點裁決升 --live(A3+operator canon6):tab-agents(C3a)+ gov:1352/1360/1446 auth 狀態/tab-live.js:90/99/138 live auth/risk-tab.js:226 live 徽章(C4b 7 點)+ **C6b 新增 tab-live.html:58 live全平/172 mainnet border-bottom/185 warn-bar strong/192 real-funds-badge(mainnet 真金身分文字現落 --neg 應升 --live)**;**canon 9 待決:risk-tab.js killswitch #8b1a1a 未 tokenize 深血紅(疑第四紅)——升 --seal(權威)或併 --neg 或新 halt token,需 A3/operator 裁**;--live 升級=增強非修復,不阻塞刪檔
- **殼層/C5 裁決(已查證)**:gui_legacy_routes.py 仍 served /console(active 主殼)·/gui(index.html)·/trading(trading.html);**C5 刪 tokens-compat.css defer Phase3**(殼層舊名由 compat 續服務,無害;避免遷移註定 Phase3 刪的 legacy 殼白工)——PM 自主裁決,不阻塞
- **回歸基線漂移(2026-07-11)**:structure/ 4F→浮動 **7-9F**——兄弟 session commit `aa67c3afd` 引入 test_development_agent_governance(新治理框架)**order-dependent** 測試(solo 2F/混跑 3-5F,不掃 GUI 檔);GUI 面基線=formatter/spec-drift/gui guard 全綠(48/0),用 `-k gui or numeric or utilities or tokens or fork` 或 comm 對照法驗 GUI 零新失敗
- **DRIFT/待裁(P0.4 PA findings)**:①working doc §9 step4 fork-delete 掛 Phase0 vs P1.4 共用組件凍結相衝→PA 以 P1.4 為準(fork bulk-rename 移 P1.4),建議更新 §9;②legacy 殼(console/trading/index=Phase3 刪除目標)仍消費舊 token 名,阻塞刪 tokens-compat.css→**C3/C5 開批前須向 OPS/operator 取 index/trading served-status**(遷 legacy vs defer 刪檔到 Phase3 二選一);③styles.css 仍 1 個 `:root`(疑 P0.1 逃逸)C3 驗;④POST 量級猜測×2 需後端契約=C8 defer Issue
- **AWAITING-OPERATOR/QC**: demo/paper(B5/D)+ live(B6/E)顯示精度變更(4dp→2dp 聚合、bps 2dp、qty 6dp、負號 U+2212、closed-pnl per-trade 隨幣別 FX 轉換)需 QC/operator 知悉;deploy 須確認 cache-buster 已 bump(common-formatters.js 站點 p03-numerics;tab-live.js 自身 p03-b6e-live;CSS/common.js 見 P0.6)
- 回歸基線更新:structure/ 6F→**4F**(兄弟 session commit 修掉 test_development_agent_governance+stable_boundary_docs;現 4F=stock_etf_ipc×2/ipc_tests/strategy_blocked_symbols 全 pre-existing 非 GUI)
- **BLOCKERS**: —
- **AWAITING-OPERATOR**: ⚠**C6d gate**(R32 AskUserQuestion 已提):①**族B live/real-money 標記**(tab-system 實盤 labels/confirm-live-guard/warn-box--live/mode-btn--live/oc-chip-live)紫中性化→**--live**(PA 強推,canon6 保真錢警示 salience,root 5/6)vs **灰化**(§2.3-literal 去色);②**T3 authority 徽章**→純 CSS 中性化(不動 render)vs 加 **.seal-mark 方印**(動 renderTrustTier)。答覆前 C6d-1/2/3 不開批;C6d-4 已完成不受影響
- **NEEDS-LINUX-RUNTIME**: —
- 行數基線:static/ 61 檔 36,337 行(tag `gui-baseline-2026-07-09`);當前:未量測

## Phase 0 · token 統一+清污(可逆,iframe 內,零架構風險)
- [x] P0.1 `tokens.css` 玄衡儀版複製入 `static/`,全部 18 tab+console.html+index.html+login.html `<link>` 引入;刪三處 token fork(styles.css :root / common.js ocInjectBaseCSS 內 :root / console.html inline :root),消 unstyled-flash race
  - 證據 `ead521f86`:E1a→E2 APPROVE(0 退修)→E4 PASS(guard 25/25、GUI/static 137/0、srv 812/5/2,5F=HEAD pre-existing)。實作要點:①`tokens-compat.css` 過渡映射 16 條舊名→新語義(P0.4 收斂後**整檔刪除**);②22 文檔 `<html data-theme="dark">` 釘玄夜(P1.3 主題切換上線後移除);③console.html fork 先前已除=NO-OP;④正本 tokens.css 補 color-scheme 主題連動(E2 Finding 2);⑤新 guard 測試鎖 `:root` 定義唯一性(+2)
  - **P0.4 追加項(來自 P0.1 findings)**:tab-risk.html:158 `--bg-card` 懸空(pre-existing)、tab-phase4.html:50,75 `--bg-elevated` 懸空、common.js L776-780 class-scoped `--strategy-*` 收斂、`--blue`→`--text-secondary` 41 消費點逐一複審、tokens link 無 `?v=` cache-bust(迭代 tokens 檔時注意)
  - **P0.4 半徑整併群(來自各批 findings)**:tab-paper.html sparkline/feed-price/oc-subtab-btn 等 `6px`→`--r-1`(5)整組轉(避免單點轉造成 5/6 錯位;E2 批次 4 LOW-1);半徑全站歸 5/8/12;各批 palette 外色 verbatim(purple/gradient/scrim/藍 tint)逐一 token 化或裁決保留
  - **P0.4 越界文字/常量殘留(來自各批)**:批次 1 oc-tc-meta whiteSpace 常量、批次 2 tab-system 5 處紫 relocation 單點裁決、_OC_CAT_CONFIG dead color data、批次 1/2 btn.style.* enum painting
  - **A3 Phase 0 全審必查(來自 E1a/E2)**:玄夜釘死後各 tab 對比度(尤 tab-governance 125 var 點)、`--blue` 中性化後資訊層級感、login.html `--card/--dim` 別名鏈、prefers-reduced-motion 全停+青銅 focus-visible 全站生效知悉
- [x] P0.2 inline `style=` 清理(基線**實測 1,469**→**全站 operator-grep 剩 5=全 legit**:app-learning 孤兒 2[Phase2 defer]+linucb §7 scoped-var 2+canary §7 scoped-var 1)——9 批全過 E1a→E2(→E4/PM 回歸),每批 commit;證據見各批 SHA;**P0.2 完結 `aa20dbf85`**
  - [x] 批次 1 console/common 殼層(50→0)——證據 `fcb931ee2`:PA 規格正本 `design/05_utilities.md`(16 family+全體 !important+兩鐵則:JS 軸同批原子化/className-wipe 禁直掛)+oc-utilities.css+22 檔第三連 link+2 個 spec-drift guard 測試;ocCategoryTag 四 hex→中性 chip=唯一刻意可見變更(canon 1,operator 要品類色需新 token 裁決);E1a→E2 APPROVE-WITH-NITS(0 blocker)→E4 PASS(srv 814/5/2,+2 零退步)
  - [x] 批次 2 monitoring/system/settings(211→0)——證據 `3d1e53147`:PA(規格已存,直接套用)→E1a→E2 退回 1 HIGH(.mode-btn--live specificity 輸給 hover/active→雙類升權復現原恆紫)+1 LOW(報告量測歸因)已修→回歸 PASS;語義升級 settings 紫→--live;spend-limit 中斷後 HIGH 修復+回歸門由 PM 親跑本地完成(E2 對抗判斷門中斷前已過);全站 style= 1,420→1,210
  - [x] 批次 3 agents/ai/development/phase4(232→0)——證據 `783acd9b3`:tab-agents 30/tab-ai 129/tab-development 11/agent-tracker.js 59/openclaw-agent-control.js 3;phase4 NO-OP;E1a 完成主體後撞 401 未及自報(報告由 PM 依 diff+E2+回歸重建)→E2 APPROVE-WITH-NITS 0 blocker(鐵則一/二窮舉零殘留;1 LOW=4 CJK 空格越界已 PM 還原)→回歸 PASS(406 passed/5F pre-existing);`.oc-input--num` 進 annex;gradient 四色 verbatim P0.4
  - [x] 批次 4 learning/replay/paper/earn(102→0)——證據 `a5c5f15f4`:tab-learning 27/tab-replay 1/tab-paper 35/tab-earn 29/handoff_helper.js 5/earn-tab.js 5;app-paper.js NO-OP;app-learning.js(2 style=)跳過=index 孤兒 Phase 2 未決;E1a(自報完整,報告階段未再中斷)→E2 APPROVE-WITH-NITS 0 blocking→回歸 PASS(406P/5F);`.ml-3` 進 §A;LOW=sparkline 6px→r-1 defer P0.4
  - [x] 批次 5 edge-gates/strategy(86→0)——證據 `e0b0d328c`:tab-edge-gates 3/tab-strategy 83;兩檔僅載 common*.js 自成一體,零新 utility;E1a DONE_WITH_CONCERNS(兩裁決點)→E2 PASS 0 finding(兩裁決點 APPROVE:tab-strategy 新建頁內塊正確/`.oc-diff-changed` 復用 blast=0)→回歸 PASS(406P/5F);進度條走 setProperty scoped-var(§7 form-1);autonomy-posture.js/canary-tab.js(各 7)歸批次 7(tab-governance 載入)
  - [x] 批次 6 stock-etf(2→0,近-NO-OP)——證據 `7a1dbb87b`:tab-stock-etf.html 2 個 inline style→0(se-muted mb-2/se-blocker-list mt-3);11 個 stock-etf JS 模組本就 0 inline style(建於 G0.5 guard 期);PM 直接 apply(trivial-edit 例外);治理驗證 **G0.5 guard 25/25 全綠**(IBKR read-only 邊界 margin 類無法觸及);structure 381P/5F
  - [x] 批次 7 governance/risk(521→0,過大拆 7a/7b,均完成)
    - [x] 7a risk(219→0)——證據 `0b432dde6`:tab-risk.html 209/risk-tab.js 10;E1a 完成主體後被中斷未自報(第三次報告階段中斷)→E2 抓中斷「改一半」HIGH(18 width token 寫成裸 HTML 屬性 class 不生效破版,grep style=0 掩蓋)並修復→鐵則一/二窮舉零殘留→回歸 PASS(406P/5F);PM 裁決 7 卡語義框移除=canon 1 中性化(交 A3);報告 PM 重建
    - [x] 7b governance(295→0)——證據 `3eb95ad8e`:tab-governance.html 205/governance-tab.js 78(1921→1877<2000)/autonomy-posture.js 6/canary-tab.js 6;E1a 未中斷(7a 裸屬性教訓已內化,自查 0)→E2 PASS 0 blocker(讀值陷阱核實、順帶修 pre-existing broken risk-badge=A3 簽核、朱印紫不轉 --seal)→回歸 PASS(392P/5F);`.fw-normal`/`.px-4` 進 §4
  - [~] 批次 8 demo/live(交易關鍵,最後;拆 8a-demo/8b-live)
    - [x] 8a demo(51→0)——證據 `b1e8ad4a6`:tab-demo.html;E1a 未中斷→E2 PASS 0 blocking(硬邊界親算 HEAD↔working:onclick 21↔21/endpoint 9↔9/confirm·gate·ocEsc 計數全 IDENTICAL;canon 6 全平框琥珀 verbatim 非熱紅;裸屬性 0)→回歸 392P/5F;零新 utility
    - [x] 8b live(107→0)——證據 `e351afa91`:tab-live.html 68/tab-live.js 39(1886→1882<2000);E1a 未中斷+硬邊界+canon6 自查→E2 PASS 0 blocking(親算重核:onclick/endpoint sorted-diff 空、openTypedConfirmModal/classifyLiveMutation/doEmergencyStop/ocEsc 72 全 IDENTICAL、typed-confirm phrase+全 modal 文案 byte-IDENTICAL、淨 −4=4 冗餘 badge display 純刪;canon 6 熱紅逐點 HEAD=WORKING 構造性保全、--live/--neg 未互換;讀值陷阱 truth-table 等價)→回歸 392P/5F
  - [x] 批次 9 P0.2 收尾殘留(59→0)——證據 `aa20dbf85`:cards/linucb 20/news 17/dl3 11/teacher 10(tab-phase4 注入 fragment,批 3 漏)+app-gui.js 1(glossary padding→p-4);E1a 未中斷→E2 PASS 0 blocking(注入正確性 p4-* 後代選擇器解析、p-4 來源 oc-utilities L67 等值、鐵則一二/裸屬性全綠;2 LOW=conv-track 透明度+雙主題目視待 A3)→回歸零 delta;新增 legit §7 scoped-var 2(linucb --cell-bg/--conv-w);**P0.2 清零完結,operator-grep 剩 5 全 legit**
  - 批次規則(PA 規格 §11):開工先實測該批檔案 style= 計數;`.oc-input--num` 組件隨 tab-ai/tab-risk 所屬批次落地;E1a 報告須含「全局新類 baseline 使用 sweep」節(E2 R2 LOW-1)
- [x] P0.3 數字排版 pass:全站數值 `.num`+第二通道(sign/▲▼-via-ocSide/val-*);精度 USD 2dp/BTC 6dp/%2dp/bps 2dp——**設計正本 `design/06_numerics.md`(PA `f63f4b60b`)**;B0 契約→B1-B6 應用全過 E1a→E2;**P0.3 完結 `9f1a82019`**(gated demo/live 硬邊界親算+canon 6+ocEsc 逐點;移除量級猜測/合一 bps 3 套/消 XSS 面;QC 知悉顯示精度變更)
  - [x] B0 formatter 契約落地——證據 `1f85b382d`:common-formatters.js(ocPct 1dp→2dp/ocMoney ASCII→U+2212/新 ocQty·ocBps·ocPctVal·ocPrice/OC_EMPTY='—'/第二通道 ocSignParts·ocSigned·ocSide)+oc-utilities §C CSS+guard 測試(node vm 真執行鎖 dp)+ocIsBlank 遷移 7 處;E1a→E2 PASS 0 blocker(§1.5 塌零裁決 SAFE:money_abs 僅 2 聚合 metric 非 per-fill)→回歸零 delta;惰性零 tab 重接
  - [x] B1 非資金 A(monitor/system 實改;replay/settings/app-actions NO-OP)——證據 `4d6ab4ceb`:tab-system b-cost 4dp column 例外(AI 成本 sub-cent)+b-cost30 2dp+.num×6/tab-monitoring .num×6;第二通道 0(計數/水位無漲跌);E1a→E2 PASS 0 blocker(4dp 例外正確、.num 皆 data-value、b-orders 計數對齊不違 gating)→回歸零 delta;E2 OBS 留 P0.4(靜態 -- 佔位→OC_EMPTY/AI 成本 FX 轉換/oc-agents unit-span defer)
  - [x] B2 非資金 B(risk/governance/earn 實改;learning/autonomy NO-OP)——證據 `6dc50bd8c`:**移除 risk-tab.js fmtPctOrUnknown 量級猜測**(1 呼叫=Drawdown,判 fraction→ocPct);fraction→ocPct/already-%→ocPctVal(15+ cell)判定=舊碼 ×100-or-not 已編碼型別逐一匹配零量級變更;earn 假零→OC_EMPTY;governance:822 winRate*100 刻意留(POST payload 非顯示);E1a→E2 PASS 0 blocker(分類逐點 VERIFIED 零 100×)→回歸零 delta;**E2 LOW:E1a 遺留 10 node-check scratch 檔於 served dir(PM 已刪未提交,教訓:node-check 抽取檔須落 scratchpad)**
  - [x] B3 analytics(strategy/ai/edge-gates 實改;canary NO-OP)——證據 `f066da5b1`:fraction/percent 分類後端生產者親證(**同名陷阱** ai win_rate=fraction vs edge win_rate_24h_pct=already-% 未搞反);metricValue bps→ocBps/%→ocPctVal 抽出(消 bps 重複);**第二通道首真應用**(edge avg_net/strategy Net PnL val-*+sign、intents side→ocSide 三通道 CVD-safe,零 ▲▼ delta 壓 D/E);E1a→E2 PASS no RETURN(分類+同名陷阱+第二通道 XSS/CVD/邊界全親證)→回歸零 delta;2 LOW 留 P0.4(gate-40 .num 雙掛冪等/readinessValue 帶號 bps 無色)
  - [x] B4 stock-etf ×11 — **NEAR-NO-OP 零 source**(E1a 判定+PM 獨立 sanity 核):0 toFixed/0 pct;stock-etf 是 key/value 狀態/布林/compact-debug-label 儀表板,無 tabular/KPI 數值格;39 bps 提及全=欄名/scaffold 物件字面/se-code packed label(硬套 ocBps 會 `benchmark=0.00 bps` 冗長+右對齊破複合 label 違 §3.2);.num 應用 0;G0.5 guard 25/25 續綠;canon 7 假零=Phase2 read-only scaffold 佔位保留。**交接**:Phase2 真帳戶頭條數值格(cash/buying_power/PnL)引入時走 B0 契約新批
  - [x] B5/D demo/paper(gated 倒二)——證據 `d766df666`+cache-bust `74f9cff53`:app-paper/tab-demo/tab-paper 契約;app-paper:876 0dp bps→ocBps;per-fill 4dp 例外(demo fill 2dp→4dp 升防塌零、fee 6dp、聚合 2dp);**ocEsc 移除 13 處全 SAFE**(E2 逐點:side/qty/price/pnl→typed formatter,XSS 消除非削弱,ocSide 未回顯順帶修 non-Buy→SHORT 舊瑕疵);0 numeric ▲▼(無方向 delta)+ocSide 方向 badge;E1a→E2 PASS no RETURN(硬邊界 IDENTICAL/per-fill 防塌零/canon 6 琥珀);**站點級 cache-buster bump**(common-formatters.js ?v=,19+2 檔,防 pre-B0 快取 ReferenceError 頁破)
  - [x] B6/E live(gated 最後)——證據 `9f1a82019`:tab-live.js(1882→1908<2000)+tab-live.html;**硬邊界 E2 親算全 IDENTICAL**(onclick/typed-confirm phrase/五閘/emergency/flatten/authorization byte-identical);**canon 6 熱紅 byte-identical**(rgba(239,68,68)<style> 零 diff、REAL FUNDS 原樣、色類 green/red→val-* 非稀釋);**ocEsc 移除 21 處全 SAFE**(typed formatter,外來字串保 ocEsc);per-fill 4dp(ocPnlCell/fee 6dp/price 階梯無塌零)、刪 _formatSignedMoneyValue=canon7 改善;_edgeMetricValue bps helper #2 消除、fee!=='--'→ocIsBlank 修;E1a→E2 PASS no RETURN(6 lens 全過)→回歸零 delta;closed-pnl per-trade 現隨幣別 FX 轉換(QC 知悉)
  - **✅ P0.3 完結**:B0 契約+B1-B6 應用;全站精度紀律(USD 2dp/BTC 6dp/%2dp/bps 2dp)、第二通道(sign/▲▼-via-ocSide/val-*)、U+2212 負號、OC_EMPTY 假零消除、per-fill 4dp 例外;7 批全過 E1a→E2(gated 批含硬邊界親算+canon 6);移除 fraction/percent 量級猜測(顯示層)、bps 3 套實作合一、ocEsc XSS 面消除
  - **B0 QC 知悉**:perf-metric grid(live/demo/paper)7D TOTAL FEES/AI COST 兩格 money_abs 4dp→2dp(聚合非 per-fill,§1.5 SAFE)
  - **E2 B0 LOW 留 D/E**:ocFormatPerformanceMetric 內部 3 blank guard 仍回 '--' 非 OC_EMPTY(混合哨兵)、ocDate/ocTime 保 '--'(契約外)、governance _formatValue ''→'--'(intended)
  - **P0.4 量級猜測整併(來自 B2)**:governance-tab.js:822(winRate*100 POST payload)+risk-tab.js:836(snapshot-fallback p1_risk_pct<1?*100)兩處同類 fraction/percent 量級猜測——B2 因屬 POST/邏輯層刻意未碰,P0.4 統一(需後端契約確認送出格式,非純顯示)
  - **P0.6 CI-guard/cache-bust 衛生(來自 B5/D)**:①oc-utilities.css/tokens.css/tokens-compat.css 為 `<link>` 無 ?v=(CSS stale 只樣式舊非頁破,低優)+ common.js ?v=20260527 P0.1 改動宜 deploy 複核——建立「shared static 改動→cache-buster bump」CI-guard;②`_ocMetric*`×3 dead helper(B5/D)+ ocPnlClass/paper-positive 註釋殘留 刪除候選;③E2 B0 混合哨兵('--' vs OC_EMPTY)統一
- [~] P0.4 樣式收斂——**設計正本 `design/07_consolidation.md`(PA `6f8fb17fb`)**;實測度量:裸 hex ~367/off-scale 半徑 ~118/fork class ~1138(全 tab-local,**bulk-rename 移 P1.4**)/tokens-compat 舊名消費 688;C1-C8 子批:
  - [x] C1 非交易死碼/懸空 var/blank guard/越界常量——證據 `aaa784f09`:common-formatters 刪 _OC_CAT_CONFIG color/bg 死欄(0-caller)+3 blank guard→OC_EMPTY;tab-phase4 --bg-elevated→--bg-raised(刪 #161b22 primer hex);common-modals oc-tc-meta whiteSpace→.pre-line;E1a→E2 PASS 0 blocker(死欄/懸空/哨兵/whiteSpace 全親證,零邏輯改動)→GUI structure guard 48/0 綠、C1 零新失敗(comm 對照;基線漂移=兄弟 governance 框架 order-dependent);E2 LOW 留 sentinel sweep(呼叫端 '--' 殘留)
  - [x] C1b 交易死碼(tab-demo _ocMetric×3/tab-risk 懸空 --bg-card)——證據 `325ed2cea`:三死函數 0-caller 親證(rg ocMetric 全站 0 code caller;B5/D 後成死碼,−17 行)+tab-risk .rc-dlg-detail --bg-card→--bg-surface(懸空修正);E1a→E2 硬邊界親算 PASS no RETURN(含隱藏調用掃描/canon 6 熱紅未觸/刪除邊界乾淨)→PM 親跑 node --check 4/4(補 E2 治理路徑限制)+GUI guard 48/0+comm 對照零新失敗
  - [x] C2 半徑收斂(180 literal→var(--r-*))——證據 `b131fe683`:23 檔確定性映射(3/4/5/6→r-1、7/8/9/10→r-2、12/14/18→r-3;多值逐非零 0 保留);保留 2px seal/999/50%/0;交易檔 E2 硬邊界親算(每 ±行含 border-radius,canon 6 熱紅 verbatim,邊界防誤 border-width/padding/box-shadow 未誤轉)→E2 PASS no RETURN、GUI guard 48/0、node --check 全 OK;var(--card-radius)屬 C3/C4 未動;login.html 排除
  - [x] C3a tokens-compat 遷移-非交易 tab(158 舊名→canonical,13 檔)——證據 `cc44ecef3`:純機械 computed-identical(別名解析同 canonical 零視覺);boundary 防誤傷(E2 negative lookahead 0 殘留);fallback hex 保留(C6);13 個 --red→--neg 機械不升 --live;E1a 逆映射 SURGICAL→E2 PASS no blocker→PM 補跑 node --check 13/13(E2 治理禁寫 probe)+GUI guard 48/0+G0.5 25/25;E2 NOTE:tab-agents live-marker 落 --neg 待 canon6 --live pass 逐點裁決(forward-pointer)
  - [x] C4a tokens-compat 遷移-共用 JS(169 舊名→canonical,5 檔)——證據 `81aebe9d2`:common.js 96/handoff 40/formatters 15/modals 14/badge 4;computed-identical E2 親算 airtight(雙向 override 空→注入交易零視覺);--red 23 點全 loss/alert(防詐 sentinel 非 live-marker)機械→--neg;--blue→text-secondary 不升 accent;零邏輯改動(134 ins/134 del 平衡,formatter 契約 dp 未觸);E1a→E2 PASS no blocker→formatter+spec-drift 3 passed+GUI guard 50/0+node --check 5/5;E2 LOW defer(oc-toast-warn 註釋 stale)
  - [x] C4b tokens-compat 遷移-交易 tab(170 舊名→canonical,8 檔)——證據 `98ad2fb64`:governance 65/live.html 24/live.js 9/paper 18/app-paper 37/demo 7/risk 4/risk-tab.js 6;零邏輯改動(E2 word-diff 逐 hunk 全量,交易控制流原封 154 ins/154 del);canon 6 熱紅 rgba HEAD↔WORK 逐檔相等+var(--live)未動;--red 14 分類(7 loss/alert→--neg+7 live-marker forward-pointer 機械--neg 不升);E1a→E2 PASS no issue→GUI guard 50/0+guard 5 passed+node --check 全綠(PM 補 5 HTML inline);**活躍 tab 遷移完結,剩殼層 console 37/trading 46 defer C5**
  - **殼層遷移**:defer(compat 續服務 console/index/trading);**C5 刪 tokens-compat.css defer Phase3**(PM 自主裁決,served 查證見狀態欄)
  - [ ] C4 tokens-compat 遷移-交易(live/demo/governance/risk,E2 硬邊界親算)
  - [ ] C5 刪 tokens-compat.css(gate:全站 16 舊名 grep=0+移 link+cache-bust+guard)
  - [~] C6 裸 hex→token(~380,大批分 C6a-e;primer 冷調→暖玄衡 token=執行 operator 暖調裁決,A3 雙主題目視 defer Phase0)
    - [x] C6a 非交易 tab(49 hex→token,6 檔)——證據 `7df893916`:red→neg/琥珀→warn/綠→pos/灰→secondary/海拔 raised·subtle 逐點判;E1a→E2 PASS no 退回(49 映射逐檔親證/熱紅未觸/added 與 removed 鏡像零邏輯/殘餘=保留集);GUI guard 50/0;紫/漸層/scrim/fallback 保留
    - [x] C6c 共用 JS(3 檔 32 hex→token)——證據 `a04c4cb16`:common.js 20/common-modals 1/handoff 11;--border-subtle×22/--text-primary×4/--neg×3(三紅收斂 canon9:destructive #ff7b72/confirm-h3 #f85149/live-metric.neg #f87171→--neg 消第四 salmon 紅)/--bg-surface×1/--bg-raised×1/--text-secondary×1;modal 外緣 #30363d→--border-strong(04_identity §2.3 浮層 recipe);**五-lens 對抗驗證全 PASS**(computed-value/canon6熱紅位元完整/雙主題定義齊/語法-rgba鏡像net0-交易語義未動/defer稽核):9 findings→3 誤報反駁+6 存活全 LOW/MED 非本 diff 回歸;node --check×3+GUI guard 50/0;紫/scrim/REAL-FUNDS rgba(248,81,73)位元不動/fallback/strategy 身份色保留
    - [x] C6b 交易 tab hex→token(5 檔 29+2)——證據 `e3ac77b4b`:tab-live.html 12/tab-live.js 3/tab-demo.html 2/tab-governance.html 8/risk-tab.js 4(tab-risk.html 0);紅→--neg/琥珀→--warn/綠→--pos/銀灰·藍→--text-secondary/border→--border-subtle;JS enum(TRUST_TIER/GOV/colorMap)→var();**SVG sparkline zero-line #30363d→var(--border-subtle)×2**(五-lens 揭 E1a「SVG attr 不吃 var()」誤判,同 SVG 兄弟已用 var());**五-lens 對抗驗證全 PASS**(canon6 熱紅 rgba 位元不動 15=15/4=4、--live 未觸、mainnet live-marker→--neg 政策合規):9 findings→5 誤報反駁+4 存活全 LOW;GUI guard 5 passed+node --check+rgba 鏡像;紫(C6d)/漸層/scrim/fallback/killswitch #8b1a1a/對比 #fff 保留
    - [~] C6d 可見美學決策(A3/operator,拆 C6d-1~4,§13 micro-spec;canon 9/10 禁 --purple/新彩 token)
      - [x] C6d-4 漸層塌平+killswitch→--neg——證據 `004e08936`:tab-agents 4 條漸層(深紅→--live-bg 真倉/藍 tint→--bg-raised,欄 border→--live·--border-strong,agent-breathing 保留)+risk-tab.js killswitch #8b1a1a→--neg(併 hard_limit,label 承載,了結第四紅);PM 按 §13.5/13.6→E2 獨立對抗核 PASS 零 finding(spec 一致/canon6 熱紅+--live 未觸/canon9 三紅/var() proven/appliers 零影響/雙主題);GUI guard 5 passed
      - [ ] C6d-1 族A authority chrome 中性化(6 檔;operator-gated T3 seal-mark)→ E2→A3
      - [ ] C6d-2 tab-system live/real-money+confirm(最高審;operator-gated 族B --live)→ E2 truth-table→A3
      - [ ] C6d-3 common.js 共用紫(寬 blast)+ 族C strategy DEFER(dead-data 建議刪)
    - [ ] C6e 殼層 styles.css 119+console/trading(Phase3 目標,defer or 非-legacy 部分)
  - [ ] C7 enum-painting 收尾+共用 .live-metric*(選配)
  - [ ] C8 POST 量級猜測×2(需後端契約,defer Issue 不阻塞)
  - PA 死碼修正:僅 _ocMetric×3 真死;**ocPnlClass=7-caller 活碼遷移非刪**;_OC_CAT_CONFIG=死欄;_formatSignedMoneyValue 已刪
- [ ] P0.5 IBKR lane 語義 chips(DENIED/PRESENT/MISSING/OK)+治理 banner 統一(fake-$0 修復已 shipped,核對即可)
- [ ] P0.6 CI 守衛升級:grep 禁 `style="`/`<style`(白名單殼層過渡)/裸 hex 新增

## Phase 1 · 單文檔殼(strangler-fig 起步;交易 tab 仍走 iframe)
- [ ] P1.0 **GUI smoke tests 從零建立**(現狀零覆蓋=最大風險;先於一切遷移)
- [ ] P1.1 新殼 shell:玄衡頂欄(品牌+lane 切換+**衡樑**+engine/lease 狀態)+ rail(lane×environment IA)+ 底部狀態帶;view-router(hash 路由;未遷移 view 掛 iframe 後備)
- [ ] P1.2 共享數據層:單一 WebSocket+按 view 訂閱;每 view 新鮮度徽章(canon 7)
- [ ] P1.3 主題/密度切換(玄夜/帛晝+舒適/緊湊,持久化 localStorage)+ ⌘K 命令面板(跳轉 view/常用查詢)
- [ ] P1.4 共用組件凍結:panel/KPI/table/chip/badge/logblock/朱印/typed-confirm modal(形制=樣品正本)
- [ ] P1.5 Live 硬化快照+client audit events 先行快照(§9 Guard)

## Phase 2 · 18 tab 遷移矩陣(舊 tab → 新 IA view;內容守恆零丟失;交易關鍵最後+flag)
| # | 舊 tab | 新 home(lane×env/cross-cutting) | 遷移 | E2 | E4 | A3 | 證據 |
|---|---|---|---|---|---|---|---|
| 1 | tab-monitoring | cross·監控 | [ ] | [ ] | [ ] | [ ] | |
| 2 | tab-system | cross·設置(與 settings 併,global-mode 單一 home) | [ ] | [ ] | [ ] | [ ] | |
| 3 | tab-settings | cross·設置 | [ ] | [ ] | [ ] | [ ] | |
| 4 | tab-agents | cross·AI(與 ai 併評估) | [ ] | [ ] | [ ] | [ ] | |
| 5 | tab-ai | cross·AI | [ ] | [ ] | [ ] | [ ] | |
| 6 | tab-learning | cross·學習(app-learning.js 孤兒復活/退役決策在此) | [ ] | [ ] | [ ] | [ ] | |
| 7 | tab-development | cross·開發(FLAG-DEAD 候選審查) | [ ] | [ ] | [ ] | [ ] | |
| 8 | tab-phase4 | cross·開發(併/歸檔評估) | [ ] | [ ] | [ ] | [ ] | |
| 9 | tab-replay | crypto·replay | [ ] | [ ] | [ ] | [ ] | |
| 10 | tab-paper | crypto·paper(默認關,保留入口+狀態) | [ ] | [ ] | [ ] | [ ] | |
| 11 | tab-earn | crypto·earn | [ ] | [ ] | [ ] | [ ] | |
| 12 | tab-edge-gates | cross·治理(gate/封驗登記,朱印形制) | [ ] | [ ] | [ ] | [ ] | |
| 13 | tab-strategy | crypto·策略 | [ ] | [ ] | [ ] | [ ] | |
| 14 | tab-stock-etf(+10 子 JS 整併) | **stock lane·IBKR**(read-only;chips+banner;凭證寫=conditional 見下) | [ ] | [ ] | [ ] | [ ] | |
| 15 | tab-governance ⚑ | cross·治理(risk-deescalate 單一 home) | [ ] | [ ] | [ ] | [ ] | |
| 16 | tab-risk ⚑ | cross·風控(衡樑數據源) | [ ] | [ ] | [ ] | [ ] | |
| 17 | tab-demo ⚑ | crypto·demo | [ ] | [ ] | [ ] | [ ] | |
| 18 | tab-live ⚑ | crypto·live(三態紀律;樣品=形制正本) | [ ] | [ ] | [ ] | [ ] | |

⚑=交易關鍵,最後遷移且 feature-flag+iframe 後備(P2 全程保留)。
- [ ] P2.C1(conditional)IBKR 凭證寫 UI —— **前置:operator ACK AMD-2026-07-09-01**;ACK 前不做

## Phase 3 · 收尾
- [ ] P3.1 刪 iframe 機制+legacy index.html(全部 view 穩定後;flag 灰度期 ≥7 天無回退)
- [ ] P3.2 死代碼處置:FLAG-DEAD 19 面逐一證據裁決(grep 調用+路由存活),留審計記錄
- [ ] P3.3 E5 全站體檢:行數對基線淨降、hot path、重複度;800 行超標檔拆分
- [ ] P3.4 中文注釋補全 pass(觸碰過的檔案 MODULE_NOTE+關鍵邏輯)

## 終驗收(全綠才 COMPLETE)
- [ ] V1 前後端對齊矩陣:每 view fetch↔control_api_v1 路由逐條核對表(存在/方法/消費字段),入 repo 存檔
- [ ] V2 寫路徑審計:全部寫面走 Rust authority 清單;Python fake-success=0
- [ ] V3 A3 UX 全審 PASS(lane×environment 直觀性/術語/防誤操作)
- [ ] V4 E3 掃描 PASS(auth 面+secret-leak)
- [ ] V5 雙主題+雙密度全站視檢(玄夜/帛晝各過一遍;live 熱紅不稀釋核對)
- [ ] V6 E4 終回歸+smoke tests 綠;node --check 全綠
- [ ] V7 文檔:docs/README 索引、baseline manifest 追加「改版後」對照、working doc §7 更新
- [ ] V8 NEEDS-LINUX-RUNTIME 清單移交 operator(引擎重啟類)

## 輪次日誌(每輪一行:日期/輪次/完成項/SHA/備註)
| 日期 | 輪 | 完成 | SHA | 備註 |
|---|---|---|---|---|
| 2026-07-10 | R1 | P0.1 | ead521f86 | 三門全過;PA 跳過(接口設計=映射表+級聯序,PM 以檔案證據親定);login.html narrow-staging 排除兄弟 auth hunks;agent memory.md 混髒全未入 commit |
| 2026-07-10 | R2 | P0.2 批次 1 | fcb931ee2 | PA→E1a→E2→E4 四門;utility 詞彙=七批跨批接口一次定準;login.html 再度 hunk 級 staging;推送順帶兄弟 session 4 個本地 commit(多 session 協議正常);E4 順帶發現 pre-existing test_snapshot_stable_entrypoint order-dependence(非 GUI,已交獨立 ticket 流) |
| 2026-07-10 | R3 | P0.2 批次 2 | 3d1e53147 | E1a 於 E2 退回後修 HIGH 時撞 spend-limit 中斷;主體 211→0 已在樹;PM 親做 HIGH 修復(selector specificity)+LOW 報告更正+本地回歸門(structure 381P/5F pre-existing、G0.5 25/25、guards 4/4、node --check 全綠、零 Python/Rust)——E2 對抗判斷門已於中斷前完成故不重跑;推送順帶兄弟 R3 docs commit 3541bb142 |
| 2026-07-10 | R4 | P0.2 批次 3 | 783acd9b3 | E1a 完成主體 232→0 後撞 401 auth 未及自報(第二次「報告階段中斷」);PM 本地驗證後**重試 E2 成功**(auth 為 transient)→E2 窮舉 APPROVE-WITH-NITS 0 blocker;PM 還原 4 CJK 空格 nit+重建報告+回歸(406P/5F)。**環境觀察**:E1a 連兩批在寫報告階段掛(spend-limit→401);對策=大批次主體完成即 checkpoint,E2 窮舉補 E1a 缺失自報,PM 依 diff 收尾 |
| 2026-07-10 | R5 | P0.2 批次 4 | a5c5f15f4 | 上輪防中斷指令生效:E1a 自報完整(報告先寫再回覆);E2 APPROVE-WITH-NITS 0 blocking(語義別名 byte-exact 無變色親證);LOW=sparkline 6px 半徑 defer P0.4 群改;P0.4 清單擴充(半徑整併群/越界文字常量);全站 style= 累進批 1-4 完成 |
| 2026-07-10 | R6 | P0.2 批次 5 | e0b0d328c | 乾淨輪(無 agent 中斷);E1a 兩裁決點自標 concerns→E2 全 APPROVE 0 finding;架構決策記錄:tab(iframe)專屬選擇器入頁內 `<style>` 塊而非殼層 styles.css(§8 字面以 index=殼層文檔舉例,tab 不適用);全站 style= 累進批 1-5 完成,剩 stock-etf/governance-risk/demo-live 三批 |
| 2026-07-10 | R7 | P0.2 批次 6 | 7a1dbb87b | 近-NO-OP(stock-etf 11 JS 模組建於 G0.5 guard 期本就 0 inline);僅 tab HTML 2 swap,PM trivial-edit 直接 apply+G0.5 25/25 治理驗證(未派 E1a/E2,因 2 個既存 utility swap 屬例外且治理面由 guard 守);剩 governance-risk(批 7,含 autonomy-posture/canary-tab.js)+demo-live(批 8,交易關鍵) |
| 2026-07-10 | R8 | P0.2 批次 7a risk | 0b432dde6 | batch 7 拆 7a/7b;E1a 第三次報告階段中斷(user-interrupt-during-tool),主體 219→0 落樹;E2 補審抓中斷「改一半」HIGH(裸屬性破版=grep 盲區,唯逐元素親證可抓)並修+鐵則窮舉零殘留;PM 裁決卡框中性化+重建報告+回歸(406P/5F);背景 task_29034ec8(snapshot 修)另一 session 完成=3 passed |
| 2026-07-10 | R9 | P0.2 批次 7b governance | 3eb95ad8e | E1a 未中斷(7a 三次中斷後首個乾淨大批,裸屬性教訓已內化自查 0);295→0 四檔;E2 PASS 0 blocker(讀值陷阱核實=toggle 邏輯無反向、順帶修 pre-existing broken risk-badge invalid CSS=A3 簽核、canon 9 朱印紫不轉 --seal);governance-tab.js 1921→1877<2000;回歸 392P/5F;**批 7 完結,P0.2 只剩批 8 demo/live 交易關鍵** |
| 2026-07-10 | R10 | P0.2 批次 8a demo | b1e8ad4a6 | batch 8 拆 8a-demo/8b-live;8a tab-demo.html 51→0;E1a 未中斷+硬邊界自查(onclick/endpoint/confirm 計數 HEAD↔working IDENTICAL)→E2 PASS 0 blocking(親算重核硬邊界、canon 6 全平框琥珀非熱紅 verbatim、confirm 3→5=CSS class 名假陽性);零新 utility;回歸 392P/5F;剩 8b-live 最高風險 |
| 2026-07-10 | R11 | P0.2 批次 8b live | e351afa91 | P0.2 最高風險子批完成;tab-live 107→0;E2 最嚴親算 PASS 0 blocking(硬邊界 sorted-diff 空+typed-confirm/五閘/emergency 文案 byte-IDENTICAL、canon 6 熱紅構造性保全逐點 HEAD=WORKING、讀值陷阱等價);**8 批主體完結**;收尾審計揭 batch 9 殘留(cards 59 tab-phase4 fragment 漏+app-gui 1)+2 legit(canary scoped-var/app-learning 孤兒) |
| 2026-07-10 | R12 | P0.2 批次 9 收尾 | aa20dbf85 | **P0.2 完結**;cards 59+app-gui 1→0;E1a 未中斷→E2 PASS 0 blocking(注入正確性/p-4 來源/鐵則親證);回歸零 delta(6F 全 pre-existing,新 6th test_development_agent_governance FileNotFound 非 GUI,stash 驗同);全站 operator-grep style= 剩 5 全 legit;operator 指示 batch9 後三端同步 |
| 2026-07-10 | R12.5 | 三端同步 | — | operator 指示:Mac=origin=Linux 全 `c525cd38f`;Linux ff 14 commits(7d1c24794→),pristine repo;on-disk 玄衡儀 tokens.css 驗證+control_api 運行中(uvicorn Tailscale 100.91.109.86:8000,靜態檔 disk 服務免 rebuild);401=login gate 正常 |
| 2026-07-10 | R13 | P0.3 設計 | f63f4b60b | PA 出 P0.3 spec-of-record `design/06_numerics.md`(精度契約/第二通道雙層 API/.num 應用/批次 B0-E/驗證);findings:ocMoney ASCII hyphen 違 canon3、ocPct 1dp、bps 3 套、risk-tab 量級猜測、LIVE 4dp→2dp 塌零;設計 checkpoint 完成,B0 下輪 |
| 2026-07-10 | R14 | P0.3 B0 formatter 契約 | 1f85b382d | 契約基建落地(9 新/修 formatter+第二通道雙層+§C CSS+node vm guard 測試);E1a→E2 PASS 0 blocker(§1.5 塌零親查 SAFE=money_abs 僅 2 聚合、per-fill ocPnlCell 未動;契約 codepoint 核、第二通道零 XSS、ocIsBlank 等價、guard 有牙);回歸零 delta;惰性零重接;3 LOW 留 D/E;perf-metric grid 兩格 4dp→2dp 需 QC 知悉。E2 附記:agent_governance.py authorize-command dispatcher bug(args.check AttributeError,非本任務) |
| 2026-07-10 | R15 | P0.3 B1 非資金 A | 4d6ab4ceb | monitor/system 契約應用(b-cost 4dp 例外+.num×12);replay/settings/app-actions NO-OP;E1a→E2 PASS 0 blocker;回歸 structure 6F→4F(兄弟修 2 個 pre-existing,B1 零新失敗);E2 OBS 留 P0.4 |
| 2026-07-10 | R16 | P0.3 B2 非資金 B | 6dc50bd8c | **移除 risk-tab fmtPctOrUnknown 量級猜測**(correctness);fraction/percent 分類逐一匹配舊碼零 100× 變更(E2 全 VERIFIED);earn 假零→OC_EMPTY;governance:822 POST payload 刻意留;E1a→E2 PASS 0 blocker;回歸零 delta 4F;E2 LOW=10 scratch 檔已刪;P0.4 量級猜測整併×2 入帳 |
| 2026-07-10 | R17 | P0.3 B3 analytics | f066da5b1 | strategy/ai/edge-gates 契約應用;fraction/percent 後端生產者親證(同名陷阱 ai win_rate vs edge win_rate_24h_pct 未搞反);metricValue bps/% 抽出消重複;**第二通道首真應用**(val-*+sign+ocSide,零 ▲▼);E1a→E2 PASS no RETURN;回歸零 delta 4F;2 LOW 留 P0.4;static/ clean(B2 教訓生效) |
| 2026-07-11 | R18 | P0.3 B4 stock-etf | (doc-only) | **NEAR-NO-OP 零 source**:stock-etf 無 tabular/KPI 數值格,39 bps 全欄名/scaffold/packed-label(硬套違 §3.2);E1a 判定+PM 獨立 sanity 核(無漏 $ /headline/toFixed);G0.5 guard 25/25 續綠;doc-only commit(E1a 報告+帳本);Phase2 真帳戶數值格交接記錄。E2 略(零 diff 無可審,PM 親核 NO-OP 判定) |
| 2026-07-11 | R19 | P0.3 B5/D demo/paper | d766df666 +cache `74f9cff53` | gated LiveDemo 顯示精度變更;app-paper 0dp bps→ocBps、per-fill 4dp 例外(demo fill 2dp→**4dp** 升防塌零);**ocEsc 移除 13 處 E2 逐點全 SAFE**(typed formatter,XSS 消除非削弱,ocSide 順帶修 non-Buy→SHORT 舊瑕疵);E1a→E2 PASS no RETURN(硬邊界 IDENTICAL);**站點級 cache-buster bump 21 檔**(E2 NEEDS-DEPLOY:pre-B0 快取 ReferenceError 頁破防護);QC/operator 知悉+P0.6 cache-bust CI-guard 入帳 |
| 2026-07-11 | R20 | P0.3 B6/E live | 9f1a82019 | **P0.3 完結**;gated REAL FUNDS 顯示精度變更;E2 最嚴親算:硬邊界全 IDENTICAL(typed-confirm/五閘/emergency/flatten byte-identical)、canon 6 熱紅 <style> 零 diff、**ocEsc 移除 21 處全 SAFE**、per-fill 4dp 無塌零、_edgeMetricValue bps helper #2 消除、fee!=='--'→ocIsBlank、刪 _formatSignedMoneyValue=canon7 改善;tab-live.js 1908<2000;E1a→E2 PASS no RETURN 6 lens;回歸零 delta;CURRENT=P0.4 累積收斂(需 PA 組織) |
| 2026-07-11 | R21 | P0.4 設計 | 6f8fb17fb | PA 出 P0.4 spec-of-record `design/07_consolidation.md`(C1-C8 子批+tokens-compat 遷移映射/hex→token 對照/半徑表/fork 策略/死碼修正);重估 fork 449→~1138 全 tab-local→bulk-rename 移 P1.4(縮小 P0.4);紫中性化/琥珀→--warn;POST 量級猜測剝 C8 defer;DRIFT×3(§9 vs P1.4/legacy 殼阻塞刪 compat/styles.css :root);設計 checkpoint 完成,C1 下輪 |
| 2026-07-11 | R22 | P0.4 C1 | aaa784f09 | 非交易死碼/懸空/哨兵/常量收斂(3 檔);_OC_CAT_CONFIG color/bg 死欄刪+3 blank guard→OC_EMPTY+--bg-elevated→--bg-raised(刪 primer hex)+oc-tc-meta whiteSpace→.pre-line;E1a→E2 PASS 0 blocker;GUI structure guard 48/0 綠、C1 零新失敗(comm 對照);**基線漂移 4F→7-9F=兄弟 aa67c3afd governance 框架 order-dependent 非 GUI**;E2 LOW 呼叫端 '--' 留 sentinel sweep |
| 2026-07-11 | R23 | P0.4 C1b | 325ed2cea | 交易檔死碼刪除+懸空 var 修復(tab-demo 三死函數 0-caller/tab-risk --bg-card→--bg-surface);E1a→E2 硬邊界親算 PASS no RETURN(隱藏調用掃描/canon 6 熱紅未觸/刪除乾淨);PM 親跑 node --check 4/4 補 E2 治理路徑限制+GUI guard 48/0+comm 零新失敗 |
| 2026-07-11 | R24 | P0.4 C2 半徑 | b131fe683 | 全站 border-radius 180 literal→var(--r-*)確定性 token 化(23 檔);保留 2px seal/999/50%/0;交易檔 E2 硬邊界親算(每 ±行含 border-radius/canon6 熱紅 verbatim/邊界防誤)→E2 PASS no RETURN、GUI guard 48/0、node --check 全 OK(E2 用治理 authorize-command preflight 親跑) |
| 2026-07-11 | R25 | P0.4 C3a compat 遷移 | cc44ecef3 | 非交易 13 tab 舊名 158→canonical 機械遷移(computed-identical 別名同值零視覺);boundary 防誤傷(E2 negative lookahead 0 殘留)、fallback hex 保留 C6、--red→--neg 機械不升 --live;E1a 逆映射 SURGICAL→E2 PASS no blocker(158 逐條核/零邏輯改動);PM 補跑 node --check 13/13(E2 治理禁寫 probe)+GUI guard 48/0+G0.5 25/25;殼層+C5 刪檔 defer Phase3(served 查證);forward-pointer:tab-agents live-marker 待 canon6 --live pass |
| 2026-07-11 | R26 | P0.4 C4a compat 遷移共用 JS | 81aebe9d2 | 5 共用 JS(注入所有 tab 含交易)169 舊名→canonical 機械遷移;E2 親算 computed-identical airtight(雙向 override 空→注入交易零視覺);--red 23 點全 loss/alert(防詐 sentinel 非 live-marker)機械→--neg;零邏輯改動 134 ins/134 del 平衡 formatter 契約未觸;E1a→E2 PASS no blocker→formatter+spec-drift 3 passed+GUI guard 50/0+node --check 5/5(E2 親跑無治理限制) |
| 2026-07-11 | R27 | P0.4 C4b compat 遷移交易 tab | 98ad2fb64 | 8 交易 tab 170 舊名→canonical 機械遷移(computed-identical);E2 交易面最嚴 word-diff 逐 hunk 全量零邏輯改動(控制流原封 154 ins/154 del)、canon 6 熱紅 rgba HEAD↔WORK 逐檔相等 var(--live)未動、--red 14 分類(7 loss/alert+7 live-marker forward-pointer 機械--neg 不升 --live)→E2 PASS no issue→GUI guard 50/0+node --check 全綠;**活躍 tab tokens-compat 遷移完結**(C3a+C4a+C4b),剩殼層 defer C5 |
| 2026-07-11 | R28 | P0.4 C6a hex→token 非交易 | 7df893916 | 6 非交易 tab 49 palette 內裸 hex→主題自適應 token(red→neg/琥珀→warn/綠→pos/灰→secondary/海拔逐點判);視覺變更=執行 operator 暖調裁決(冷 primer→暖玄衡)修正非退化 A3 雙主題 defer Phase0;E1a→E2 PASS no 退回(49 映射逐檔親證/熱紅未觸/零邏輯鏡像/殘餘=保留集無遺漏/token 雙主題定義齊備)→GUI guard 50/0;紫/漸層/scrim/fallback 保留;C6 分 C6a-e 子批 |
| 2026-07-11 | R29 | P0.4 C6c hex→token 共用 JS | a04c4cb16 | 3 共用 JS(注入所有 tab 含交易)32 裸 hex→token;--border-subtle×22/--text-primary×4/三紅收斂--neg×3(destructive#ff7b72+confirm#f85149+live-metric#f87171,消第四 salmon 紅)/surface·raised·secondary;modal 外緣 #30363d→--border-strong(浮層 recipe 校正);**ultracode 五-lens 對抗驗證 workflow 全 PASS**(computed-value/canon6熱紅位元完整/雙主題/語法-rgba鏡像net0-交易語義0動/defer稽核)→9 findings 對抗複核 3 誤報反駁+6 存活全 LOW/MED 且非本 diff 回歸;node --check×3+GUI guard 50/0+rgba 鏡像 net=0;**帛晝亮主題就緒需專屬 alpha token**(冷 rgba 面板底,PA 決策 forward-pointer);多 session 分岔→detached worktree cherry-pick 救援推送(主樹 155 dirty=兄弟 governance 改,不碰) |
| 2026-07-11 | R30 | P0.4 C6b hex→token 交易 tab | e3ac77b4b | 5 交易檔(tab-live/demo/governance+risk-tab.js)29+2 裸 hex→token;紅→--neg/琥珀→--warn/綠→--pos/銀灰藍→--text-secondary/border→--border-subtle/JS enum→var();**SVG sparkline zero-line #30363d→var(--border-subtle)×2**(五-lens 揭 E1a SVG-attr 誤判,同 SVG 兄弟已用 var()→就地修);**ultracode 五-lens 對抗驗證全 PASS**(canon6 tab-live REAL FUNDS 熱紅 rgba 位元不動 15=15、--live 未觸、mainnet live-marker 文字機械落 --neg=既定政策合規非違反)→9 findings 對抗複核 5 誤報反駁+4 存活全 LOW(SVG-attr 已修/帛晝 --text-inverse+killswitch #8b1a1a canon9/login.html=兄弟 auth 非本批);GUI guard 5 passed+node --check+rgba 鏡像;canon-6 --live pass forward-pointer +4 點、canon-9 killswitch 待決入帳;worktree cherry-pick 推送(主樹兄弟 dirty 保全) |
| 2026-07-11 | R31 | P0.4 C6d 設計(PA micro-spec §13) | 493864cb3 | design checkpoint(同 R13/R21):PA 出 C6d 逐處映射 spec-of-record §13(21 紫+漸層+killswitch+藍 tint 皆 pin class:行+token+授權態+交易面+A3 描述);**grep 細化 §2.3「紫=authority」為三族**(A authority→中性化/B live-real-money→--live canon6 保 salience/C strategy→DEFER);漸層→--live-bg·--bg-raised、killswitch #8b1a1a→--neg(了結 C6b 第四紅);.seal-mark 只 T3;**子批拆分 C6d-4(機械先)→operator gate(族B --live vs 灰)→C6d-1/2/3**;PA 標主 gate=族B real-money 標記 --live(PA 強推,root 5/6 保生存訊號)vs §2.3-literal 灰,將於 C6d-1/2/3 前提 operator;零 static 改動 |
| 2026-07-11 | R32 | P0.4 C6d-4 漸層塌平+killswitch | 004e08936 | tab-agents 4 條 palette 外漸層塌平(深紅#3d0d0d/#5c1a1a→--live-bg 真倉/藍#0d1f3d/#1a2f5c→--bg-raised,欄 border→--live·--border-strong;agent-breathing 動效保留)+risk-tab.js killswitch #8b1a1a→--neg(併 hard_limit,嚴重度區辨改 label 承載)——**了結 C6b canon-9 第四紅 forward-pointer**;PM 按 §13.5/13.6 spec 實作→**E2 獨立對抗核 PASS 零 HIGH/MED/LOW**(spec 逐點一致/canon6 熱紅 rgba+--live 未觸/canon9 三紅/var() 解析 proven=其餘 3 enum 已用 var()/appliers class 名穩定零影響/零邏輯改動/殘留全清/雙主題齊);node --check+GUI guard 5 passed;**C6d-1/2/3 前 operator gate 本輪 AskUserQuestion 提**(族B --live vs 灰) |
