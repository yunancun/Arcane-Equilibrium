# GUI 大改 · 自動推進 Loop Driver(玄衡儀 · 2026-07-10 起)

> 本檔是 `/loop` 每輪喚醒的執行協議正本。持久狀態在同目錄 `PROGRESS.md`(帳本);
> 設計權威在同目錄 `GUI-DESIGN-WORKING-DOC.md`(§0 裁決 + §3 canon 1-11)+ `tokens.css`。
> Loop 指令(operator 用):
> `/loop 執行 GUI 大改自動推進輪:嚴格按 srv/docs/execution_plan/gui_redesign/LOOP-DRIVER.md 協議做本輪工作,更新 PROGRESS.md,自排下次喚醒;全部完成即停`

## 0 · 終態定義(全部滿足才算完成,缺一不停)
1. 18 個 tab 全部完成玄衡儀化遷移(新 IA=lane×environment),交易關鍵 tab(live/demo/risk/governance)最後遷移且 flag 後備 iframe。
2. 雙主題(玄夜/帛晝)+雙密度全站生效;衡樑/朱印/銘文按 canon 9-11 落地。
3. 前後端對齊矩陣全綠:每個 view 的 fetch 路徑 ↔ control_api_v1 路由逐條核對(路徑存在+方法對+響應字段被正確消費);寫路徑全部打到 Rust authority,零 Python fake-success。
4. Bybit 面 read-write 功能核驗;IBKR 面在治理允許範圍內全部落地(見 §3 邊界);本地功能(引擎狀態/風控/審計/學習)讀寫核驗。
5. 代碼企業級:零 inline `style=` 新增(存量清完)、零裸 hex、tokens 單一正本、檔案 <800 行(硬頂 2000)、死代碼按證據處置、新注釋全中文。
6. 終驗收全過:A3 UX 全審 PASS、E3 auth 面掃描 PASS、E4 回歸無退步、node --check 全綠、GUI smoke tests 建立並綠、docs/README 與 manifest 更新。
7. `PROGRESS.md` 標 `STATUS: COMPLETE` → 停 loop(ScheduleWakeup stop)+ 最終報告。

## 1 · 每輪協議(嚴格順序)
1. **同步**:`git fetch` + `git pull --ff-only`(Mac 規則:禁 merge/rebase/reset)。讀 `PROGRESS.md` 狀態欄。若他 session 已推進,以 repo 為準修正帳本。**--ff-only 失敗(分岔)處置**:先 `git diff <本地獨有> <遠端尖>` 內容比對——若本地獨有 commit 內容 ⊆ origin(重複提交模式,R40 先例)→ `git checkout -B main origin/main` 對齊(髒檔保留);否則本輪改動走 worktree-from-origin 提交推送(R33 先例),主樹分岔留給該 session 自行 reconcile,絕不 merge/rebase。
2. **選項**:取帳本最上方未完成且未 BLOCKED 的工作項(一項=一個可在單輪內完成+可驗的 checkpoint;過大就先拆再做)。AWAITING-OPERATOR 項跳過。
3. **派工**:按 role chain 用 subagent 執行,主會話只做 PM+Conductor。**角色名已按新治理框架遷移(2026-07-11;舊 PA/E4 agent type 已不存在)**:
   - 調查/接口分析 → **PA-investigator**(read-only);寫規格/設計正本 → **PA-design-writer**;
   - 實作 → E1a(讀 srv:gui-style-guide + bilingual-comment-style);
   - 每個實作後 → E2 對抗審查(srv:pr-adversarial-review),issue 退回 E1a 修,不代寫;
   - E2 過 → 寫測試 **E4-writer** / 跑回歸+獨立證據複核 **E4-verifier**(read-only;node --check 全部觸碰 JS/HTML + 回歸對基線)。
   - 角色綁定以 `.codex/agent_registry_v1.json` 為準;harness 拒絕某角色名時查 registry 修正並記帳本。完成回報守四態契約(STATUS 首行)。
   - dispatch prompt 一律留 NO-OP exit(「若發現已完成,回報 NO-OP 並說明證據」)。
   - 前台阻塞等待收工(desktop idle-pause 會殺後台 agent,勿散養)。
   - **防中斷紀律(R3/R4/R8 固化)**:E1a 屢在「報告階段」被殺(spend-limit/401/user-interrupt)→ ①E1a 指令必含「主體每完成一檔即落樹;最終報告先寫入 workspace 檔再回覆」;②E1a 中斷不重跑主體——PM 依 diff 判斷完整度,派 E2 窮舉審查補位(逐元素親證;grep style=0 不可信,裸屬性破版是 grep 盲區,R8 實錘);③中斷殘留的 HIGH 由 PM 親修或退回,報告由 PM 依 diff+E2+回歸重建。
   - **批次上限(R8 固化)**:單批 inline style >250 或觸碰 >5 檔必先拆(governance 521→7a/7b 先例);開工先實測該批計數,不信 07-08 快照。
4. **驗證軸**(每 checkpoint 必過,失敗不 commit):
   - `node --check` 觸碰的每個 JS;HTML 結構完整(自檢首尾標籤);
   - 禁新增 inline `style=`/裸 hex/`<style>`(唯一豁免:JS 寫 scoped var);禁引入任何框架;
   - 涉及 fetch 的改動:grep control_api_v1 路由確認路徑+方法存在;寫路徑核實走 Rust IPC,非 Python 直寫;
   - canon 7 資料狀態:未接數據顯示 —/stale/blocked 標籤,絕不假 0.00/假成功;
   - 需 Linux runtime 才能驗的項:僅 `ssh trade-core` 只讀查驗(讀日誌/curl 本地端點);**不重啟引擎、不 rebuild、不改 DB**——這類需求記入帳本 `NEEDS-LINUX-RUNTIME` 等 operator。
5. **提交**:綠即 commit(窄化 staging/`--only`;訊息中文+證據;doc-only 加 `[skip ci]`),push 前 re-fetch;push origin main 並記 SHA 入帳本。
6. **記帳**:更新 `PROGRESS.md`(勾選+狀態欄+證據 SHA+一行備註),與代碼同輪 commit。
7. **排下輪**:context 尚充足 → 同輪繼續下一項;不足或輪結 → ScheduleWakeup(接續工作 60-270s;僅剩 AWAITING-OPERATOR/NEEDS-LINUX-RUNTIME → 1800s+ 並在帳本置頂寫明等什麼);終態達成 → stop。
8. **異常**:技術卡點→記 BLOCKERS 換下一項;連續兩輪零推進→帳本寫診斷+改小步長;治理禁區→絕不越過,記錄並繼續其他項。

## 2 · 設計權威(每輪必讀的最小集)
- `GUI-DESIGN-WORKING-DOC.md` §0(玄衡儀裁決)、§1(鎖定決策)、§3(canon 1-11)、§9(phase 計劃)。
- `tokens.css`=調色/字體/密度唯一正本;樣品=`2026-07-10--xuanheng_live_view_sample.html`(組件形制參照)。
- 深度規格按需:排級 `design/01`、排版 `design/02`、文案 `design/03`(canonical labels)、識別 `design/04`。
- 內容守恆:210 面 KEEP115/RELOCATE38/MERGE26/COLLAPSE12/FLAG-DEAD19(§5)——**遷移零靜默丟失**;FLAG-DEAD 須證據才刪;`app-learning.js` 孤兒須顯式復活/退役決策。

## 3 · 治理硬邊界(loop 永不越過;違反=立即中止該項)
- **IBKR(2026-07-11 更新,依 AMD-2026-07-11-01+CLAUDE.md 硬邊界)**:授權開發 production-wired `stock_etf_cash` 能力(readonly/paper/shadow/tiny-live/live 模式),但**未激活**——激活唯一路徑=Rust 驗證 `ibkr_activation_envelope_v1`(nonce/expiry/revocation/kill-switch epoch),credentials/sessions 永不自動激活;margin/short/options/cfd/transfer/帳戶管理寫**永 DENIED**。GUI 鐵則:**Python/FastAPI/GUI 永不成為 IBKR order/risk/activation 權威**;憑證 custody Rust-only(GUI 零明文 ingress/序列化/log/回顯);Guardian/Decision Lease/Cost Gate 不可弱化。GUI 本 loop 可做:讀面/狀態 chips/治理 banner/激活狀態顯示(`EXTERNAL_VERIFICATION_PENDING` 按 canon 7 顯式呈現);**IBKR 寫類 UI(下單/激活操作面)須該 Rust IPC 權威路徑先存在,且逐項過 IB(venue reviewer)+CC 審後才開工**——Bybit 面 BB 審,IBKR 面 IB 審,不可互替。
- **Live 硬化面只換皮不改邏輯**:五閘/授權 TTL/typed-confirm/緊急停止與平倉分離/REAL FUNDS 常駐標識全保留;`--live` 熱紅雙主題永不稀釋;LiveDemo 不因 endpoint 降級。
- **寫面走 Rust authority**:GUI 寫入必經既有 Rust IPC 權威路徑;發現 Python fake-success 面=修復項(打到 Rust 或顯式標記 read-only),不得沿用。
- **不 fake 任何東西**:AI 調用/交易活動/fills/健康檢查/測試結果。
- **engine restart / rebuild / DB migration / cron 改動**:一律不做,記 NEEDS-LINUX-RUNTIME 等 operator。
- 憑證/密鑰:GUI 不顯示明文,不入 log,不入 commit(E3 secret-leak 紀律)。

## 4 · 質量門(企業級「優化+精簡」的定義)
- **精簡**:重複樣式歸併 tokens/共用 class;每 phase 結束派 E5 做一次體檢(檔案大小/重複度/hot path);合併後淨行數應下降(基線 61 檔 36,337 行,帳本追蹤)。
- **注釋**:新/實質改動注釋一律中文;模塊頭 MODULE_NOTE 規範;不順手清未觸碰的雙語塊。
- **UX(邏輯清晰直觀用戶友好)**:導航=lane×environment 心智模型;每 phase 完成派 A3 按 srv:ux-checklist 全審(首次可用性/術語友好/防誤操作),findings 進帳本作下輪工作項;表單/危險操作按 design/03 文案規範。
- **測試**:GUI smoke tests 從零建立(現狀零覆蓋=最大執行風險,P1 前置項);E4 回歸計數只增不減。

## 5 · 帳本紀律
- `PROGRESS.md` 是唯一進度真相;每輪至少一次更新;狀態欄六字段(STATUS/CURRENT/LAST-COMMIT/BLOCKERS/AWAITING-OPERATOR/NEEDS-LINUX-RUNTIME)必須時新。
- 勾選必附證據 SHA;跳過/NO-OP 必註原因;operator 中途指示以新裁決記入 working doc §0 追加行,帳本引用之。
- **回歸計數引用紀律(E4-verifier P0 驗收 gap 固化)**:引用一律以「失敗者身分基線」(哪幾個測試失敗+根因 pre-existing 與否)為準,不引 passed 絕對數(測試集持續成長,絕對數不可重放)。

## 6 · Phase 1 特則(2026-07-11 P0 驗收後生效)
- 順序鐵律:P1.pre-1(殼層紫小補丁)→ P1.pre-2(C6f 掃尾)→ P1.0(smoke tests 先於一切遷移)→ P1.1+。
- **新殼=新檔**(如 shell.html/shell.js),不改造 legacy console.html(strangler-fig);legacy 只接 flag 跳轉;styles.css 冷調 119 hex 隨 legacy 死,不 re-theme(C6e defer 維持)。
- **P1.3 硬 gate 三條**(帳本 Phase 1 節):α-overlay token+帛晝 AA retune+AA ratchet CI 測試;三綠前不解 data-theme="dark" 釘死、不宣稱雙主題可用。
- 衡樑數據源=風控包絡真值;無真值按 canon 7 顯 blocked 態,不 fake 傾角。
- 視覺驗證:靜態樣可用 artifact 截圖輔助;真渲染三態/鍵盤走查/帛晝全站=V5 defer 清單(A3 報告 8 項),需 Linux runtime。
- A3 findings 的 Phase 2 綁定項(M-3 uppercase copy pass/M-4 品類眉標)在 Phase 2 各 tab 遷移時隨批處理,不提前。
