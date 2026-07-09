# GUI 大改 · 進度帳本(loop 持久狀態;協議見 LOOP-DRIVER.md)

## 狀態欄
- **STATUS**: NOT_STARTED(loop 首輪未跑)
- **CURRENT**: —
- **LAST-COMMIT**: a35ec287b(設計正本入 repo)
- **BLOCKERS**: —
- **AWAITING-OPERATOR**: —
- **NEEDS-LINUX-RUNTIME**: —
- 行數基線:static/ 61 檔 36,337 行(tag `gui-baseline-2026-07-09`);當前:未量測

## Phase 0 · token 統一+清污(可逆,iframe 內,零架構風險)
- [ ] P0.1 `tokens.css` 玄衡儀版複製入 `static/`,全部 18 tab+console.html+index.html+login.html `<link>` 引入;刪三處 token fork(styles.css :root / common.js ocInjectBaseCSS 內 :root / console.html inline :root),消 unstyled-flash race
- [ ] P0.2 inline `style=` 清理(基線 1,375 個→0;按批次:console/common 殼層 → monitoring/system/settings → agents/ai/development/phase4 → learning/replay/paper/earn → edge-gates/strategy → stock-etf → governance/risk → demo/live 最後)每批一 checkpoint
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
