# GUI 大改 · 進度帳本(loop 持久狀態;協議見 LOOP-DRIVER.md)

## 狀態欄
- **STATUS**: IN_PROGRESS
- **CURRENT**: P0.2 批次 4(learning/replay/paper/earn)
- **LAST-COMMIT**: 783acd9b3(P0.2 批次 3)
- **BLOCKERS**: —
- **AWAITING-OPERATOR**: —
- **NEEDS-LINUX-RUNTIME**: —
- 行數基線:static/ 61 檔 36,337 行(tag `gui-baseline-2026-07-09`);當前:未量測

## Phase 0 · token 統一+清污(可逆,iframe 內,零架構風險)
- [x] P0.1 `tokens.css` 玄衡儀版複製入 `static/`,全部 18 tab+console.html+index.html+login.html `<link>` 引入;刪三處 token fork(styles.css :root / common.js ocInjectBaseCSS 內 :root / console.html inline :root),消 unstyled-flash race
  - 證據 `ead521f86`:E1a→E2 APPROVE(0 退修)→E4 PASS(guard 25/25、GUI/static 137/0、srv 812/5/2,5F=HEAD pre-existing)。實作要點:①`tokens-compat.css` 過渡映射 16 條舊名→新語義(P0.4 收斂後**整檔刪除**);②22 文檔 `<html data-theme="dark">` 釘玄夜(P1.3 主題切換上線後移除);③console.html fork 先前已除=NO-OP;④正本 tokens.css 補 color-scheme 主題連動(E2 Finding 2);⑤新 guard 測試鎖 `:root` 定義唯一性(+2)
  - **P0.4 追加項(來自 P0.1 findings)**:tab-risk.html:158 `--bg-card` 懸空(pre-existing)、tab-phase4.html:50,75 `--bg-elevated` 懸空、common.js L776-780 class-scoped `--strategy-*` 收斂、`--blue`→`--text-secondary` 41 消費點逐一複審、tokens link 無 `?v=` cache-bust(迭代 tokens 檔時注意)
  - **A3 Phase 0 全審必查(來自 E1a/E2)**:玄夜釘死後各 tab 對比度(尤 tab-governance 125 var 點)、`--blue` 中性化後資訊層級感、login.html `--card/--dim` 別名鏈、prefers-reduced-motion 全停+青銅 focus-visible 全站生效知悉
- [ ] P0.2 inline `style=` 清理(基線**實測 1,469**(07-08 快照 1,375 已漂移)→0;per-file ratchet;按批次,每批一 checkpoint)
  - [x] 批次 1 console/common 殼層(50→0)——證據 `fcb931ee2`:PA 規格正本 `design/05_utilities.md`(16 family+全體 !important+兩鐵則:JS 軸同批原子化/className-wipe 禁直掛)+oc-utilities.css+22 檔第三連 link+2 個 spec-drift guard 測試;ocCategoryTag 四 hex→中性 chip=唯一刻意可見變更(canon 1,operator 要品類色需新 token 裁決);E1a→E2 APPROVE-WITH-NITS(0 blocker)→E4 PASS(srv 814/5/2,+2 零退步)
  - [x] 批次 2 monitoring/system/settings(211→0)——證據 `3d1e53147`:PA(規格已存,直接套用)→E1a→E2 退回 1 HIGH(.mode-btn--live specificity 輸給 hover/active→雙類升權復現原恆紫)+1 LOW(報告量測歸因)已修→回歸 PASS;語義升級 settings 紫→--live;spend-limit 中斷後 HIGH 修復+回歸門由 PM 親跑本地完成(E2 對抗判斷門中斷前已過);全站 style= 1,420→1,210
  - [x] 批次 3 agents/ai/development/phase4(232→0)——證據 `783acd9b3`:tab-agents 30/tab-ai 129/tab-development 11/agent-tracker.js 59/openclaw-agent-control.js 3;phase4 NO-OP;E1a 完成主體後撞 401 未及自報(報告由 PM 依 diff+E2+回歸重建)→E2 APPROVE-WITH-NITS 0 blocker(鐵則一/二窮舉零殘留;1 LOW=4 CJK 空格越界已 PM 還原)→回歸 PASS(406 passed/5F pre-existing);`.oc-input--num` 進 annex;gradient 四色 verbatim P0.4
  - [ ] 批次 4 learning/replay/paper/earn
  - [ ] 批次 5 edge-gates/strategy
  - [ ] 批次 6 stock-etf
  - [ ] 批次 7 governance/risk
  - [ ] 批次 8 demo/live(交易關鍵,最後)
  - 批次規則(PA 規格 §11):開工先實測該批檔案 style= 計數;`.oc-input--num` 組件隨 tab-ai/tab-risk 所屬批次落地;E1a 報告須含「全局新類 baseline 使用 sweep」節(E2 R2 LOW-1)
- [ ] P0.3 數字排版 pass:全站數值 `.num`(mono+tabular+右對齊)+第二通道(▲▼/LONG-SHORT/±);精度紀律 USD 2dp/BTC 6dp/% 2dp/bps 2dp
- [ ] P0.4 樣式 fork 合併:`live-*`/`se-*`/`rc-*`/`gov-*` → `oc-*` 原語;83 裸 hex → 語義 token;半徑歸 5/8/12
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
