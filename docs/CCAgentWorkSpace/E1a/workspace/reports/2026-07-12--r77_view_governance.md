# R77 · view-governance 遷移(iframe→原生玄衡 view)— E1a 交付報告 · 2026-07-12

STATUS: DONE_WITH_CONCERNS

> E1a(前端實作)。承 spec `docs/execution_plan/gui_redesign/design/11_governance_migration.md`(§A-§10 + PM 裁 R76)。
> 交付即 source 事實;真渲染 / 12 寫真行為 / typed-confirm 真閘 / 三態 / 雙輪詢 = NEEDS-LINUX runtime + operator(E2+E3+operator Linux 批驗才 cutover)。

## 交付檔(2 新檔,均 untracked ??)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/view-governance.js` — **380 行**(thin wrapper,類比 view-risk.js)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/view-governance.css` — **485 行**(2 style 塊 scoped + oc-* shim)

**五源檔零改(git numstat 全 0):** tab-governance.html / governance-tab.js / canary-tab.js / autonomy-posture.js = 0-0 no diff;governance.js 我全程未觸(他 session 編輯,現已 clean)。shell.js / shell.html 未動(registry wiring 不在本刀,見 concern C)。

## 如何滿足規格

**4 路併入序(§A.1,固定):** `[inline(html:1250-1716) , autonomy-posture.js , governance-tab.js , canary-tab.js].join('\n;\n')` → 單一外層 IIFE 重跑。governance.js **不併入**(殼 shell.html:215 已 `<script src>` 載,IIFE 內以上層作用域引用其全域裸名 govGetStatus/govPost*/GOV_*)。skip:首個 inline(ocAuthCheck/ocInjectBaseCSS,破殼 chrome)、外部 `<script src>`(common*/governance.js 殼已載;autonomy/govtab/canary 的 text 另 fetch 併入不重載)、兩 `<style>` 塊(→ CSS)。TDZ 硬序:autonomy 早於 govtab(gov-tab self-init `loadAll()→loadAutonomyPosture()` 讀 autonomy 頂層 `const AUTONOMY_*`)。**經真源檔模擬:inline 非-ocInjectBaseCSS 塊數=1(= Live-Auth 塊),串接正確。**

**IIFE 隔離(§2,R71 空集):** combined 包 IIFE → 頂層 const/let/function 全 IIFE-local。實測 `topLevelDeclaredNames(combined)`=111 名(含 `loadAll`、`_currentRiskLevel` 等撞名)全 IIFE-local,不進 global lexical → 過 R71 跨-view guard,governance 判 isolated 貢獻空集(同 view-risk.js)。canary 自成 IIFE(其 `(function(){` 令內部 depth≥1)→ 亦貢獻空集。

**loadAll clone-rebind(§3.B′ / PM 裁 OPEN-1=PRIMARY):** governance **永不寫 window.loadAll**;IIFE 尾曝 `window.__ocGovLoadAll = loadAll`;注入 DOM 後對**已 clone 進宿主**的節點掃 `[onclick]`,把唯一 `onclick="loadAll()"`(html:407,whitespace-normalized 比對)`setAttribute('onclick','__ocGovLoadAll()')`,rebound 計數(!=1 warn)。**唯一** onclick 重綁,其餘 34 名走標準 re-export。源 tab-governance.html 檔零改(rollback 錨完好);paper 的 window.loadAll 從不被 governance 觸碰(paper 恆安全)。MODULE_NOTE 明記此唯一重綁 + 理由。

**強化 discover 濾保留字(§3.A / PM 裁 OPEN-2=必改):** **不**原樣複製 view-risk.js 的 `discoverOnHandlerNames`。實作:掃 `htmlText ∪ combined`、對每個 on* 屬性值(有界取值:引號後至同型未轉義引號/換行,防模板字串 `onclick="auditApprove(\'` 貪婪吞噬)抓**所有非 member** `ident(`、交集 `topLevelDeclaredNames`(**已擴充捕頂層 function 宣告名**,並加 `async` 入 kwRegex 修 `async function` 漏捕)+ 濾 `JS_RESERVED` + 排 `loadAll`。**真源檔模擬硬核驗證(全 PASS):**
- `exportNames` = **恰 spec 35 名**(零缺漏 / 零額外);
- `if` **未** re-export(擋 `window["if"]=if` parse-error 整段 IIFE 死 blocker)——保留字濾 + 交集頂層函式雙保險;
- 非首 token `loadAuditTrail`(html:1091)**捕獲**;模板注入 `auditApprove`/`auditReject`/`confirmApproveRecovery`(gov-tab:1521/1523/1090)**全捕獲**;
- `event`/`loadCanaryCohorts`/`loadAll` 全**未** re-export(canary 自曝 window;loadAll 走 clone-rebind);
- F1 born-safety 交集 = **∅**(§4:無裸賦值到頂層 binding);`loadAll ∈ topFnNames`(供 `__ocGovLoadAll`)。

**onclick 零交集復核(§3.C):** re-export 35 名與 paper/settings/overview/risk 的 onclick 集無交集(spec §3.C grep 證;35 名皆 toggle*/show*/hide*/submit*/audit*/gov*/autonomy* 專屬)→ 無 last-writer-win。

**§3 byte-parity(§6):** 12 活躍寫全走復用未改 JS text(經 Rust IPC),本檔零新增 call-site。typed-confirm phrase 逐字保留:`CONFIRM`(bulkAudit gov-tab:1614 / confirmApproveRecovery :1764)、`PROMOTE`(canary:41/334 case-sensitive)、`CONFIRM SWITCH`(autonomy:219/228)——皆在未改 JS,IIFE-wrap 不觸碰。五閘 / Live boundary / 緊急熔斷·防禦分離 / signed-auth·authorization.json / Paper 無真實資金 文案在復用 DOM/JS 逐字保留。governance 無 `--live` CSS 類(live/halt/T3 朱印 seal-mark 態配色由 reused inline 塊執行期 `.style` 設,屬未改 JS 的 byte-parity 執行期行為,非本檔新 inline-style ratchet 違規)。

**postMessage 第二輪詢(§9 / PM 裁 OPEN-3):** pause 停**兩**輪詢:① `ocStopRefresh()`(清 common.js 全域單例 10s `_ocRefreshTimer`);② `window.postMessage({type:'openclaw-tab-visibility', tab:'governance', visible:false}, origin)` → inline 塊 message listener(html:1677,跑於殼 window)`stopGovLiveAuthLoop()`(清 30s IIFE-local `_govLiveAuthTimer`,ocStopRefresh 清不到)。resume:postMessage visible:true(inline listener 啟 30s loop + force load)+ `__ocGovLoadAll()` + `ocStartRefresh(__ocGovLoadAll,10000)`(用命名空間非 window.loadAll,隔離 paper;!built||!wired no-op)。零源修改復用既有 visibility 語義。

**registry 契約:** `window.OC_NATIVE_VIEWS['governance'] = {render:renderGovernanceView, resume:resumeGovernanceView, pause:pauseGovernanceView}` + 具名 window 導出。render(sec) 契約鏡像 shell.js:248 `api.render(sec)`;POLL_MS=10000(byte-parity gov-tab ocStartRefresh(loadAll,10000))。

## 驗證結果
- `node --check view-governance.js` → **SYNTAX OK**。
- view-governance.css:零 hex(grep `#[0-9a-fA-F]{3,8}` 空)、零 inline style 屬性、括號平衡 146=146、全選擇器 `.governance-view` scoped、首尾標籤完整。(唯一 `!important` 命中在**註釋文字**「不設 !important」非宣告。)
- 強化 discover 真源檔模擬 = **綜合 PASS**(見上「如何滿足」硬核)。

## 與 spec / 源的出入(以源碼為準,誠實指出)

**C1(concern,已補實作)· spec §8「2 style 塊」為必要但不充分——oc-* 結構 shim 必補。** 實測 `oc-card / oc-metric* / oc-chip* / oc-explain* / oc-grid-2 / oc-table* / oc-subtab-placeholder / subtitle` 在殼全域 CSS(shell-components/oc-utilities/shell/tokens)**零定義**(它們原只在 common.js `ocInjectBaseCSS()`,殼刻意不呼)。**4 個已遷 view CSS(view-risk/overview/settings/paper.css)各自 port `.{view}-view` scoped 同款 shim**,否則卡片/表格全裸。view-governance.css 照「類比 view-risk.css」補 block ②(§8 ratchet 慣例:色字面→token、暗底 rgba→--bg-sunken、無 token tint 保 rgba;oc-table 補自 ocInjectBaseCSS)。**此為 spec §8 undercount,非缺陷。**`oc-tabs-wrapper` 全域無定義=無樣式 wrapper(byte-parity),刻意不新增(同 spec §8 `.trust-tier-badge` 冗餘類處置)。

**C2(concern,已處置)· born-clean「零 hex」vs byte-parity 的 3 處 var() hex 後備。** 源塊 3 處 `var(--token, #hexfallback)`(canary-stage-badge active/stage-4 color、canary-progress-bar-fill background,分別 #58a6ff/#f85149/#58a6ff)。ratchet「新檔零 hex」硬要求 + 四姊妹 view CSS 零 hex 慣例 → 本檔**移除後備** → `var(--token)`;殼恆載 tokens.css → token 必定義 → 後備永不觸發 → 視覺 **byte-identical**(非 re-tokenize,primary token 不動)。另 3 處 hex 註釋(琥珀/紫/銀灰 palette 對照)改寫為不含 hex 碼的等義中文。所有 `rgba()` 色字面逐字保留(pre-existing,P0.4)。

**C3(已補——見下「殼接線」節)· registry wiring。** 原報告 C3 標「未做」;coordinator 後續授權(除 live 外全 tab 遷移,governance 走 `flag: true, iframe: false` opt-in+fallback=協議內建風控)後**已補 3 處殼接線**。shell.js/shell.html 現有增改(numstat 見下),五源檔仍 0-0。**opt-in flag 保留 → operator Linux 批驗才真 cutover,Mac 靜態未逕自強制 flip。**

**C4(核實,成立)· spec §5「12 活躍寫」正確**(brief「6」undercount);#12 canary manual_promote 走 `ocApi(url,{method:'POST'})` 非 ocPost。全在未改 JS text,本檔零新增 call-site。

## 規格未覆蓋的新發現
- **inline 塊自帶 `document.visibilitychange` listener(html:1704)** 為 live-auth loop 的瀏覽器層雙保險——與 shell `document.visibilitychange`(shell.js:195)並存不衝突(前者只管 live-auth 30s,後者呼 notifyViewVisibility 驅動 native pause/resume)。
- **shell native pause=ocStopRefresh 的單例序** 為既有共享行為(view-risk/paper/overview/settings 同構),本檔 byte-parity 沿用不 deviate;非本刀引入或修復範疇。

## 殼接線(coordinator 後續授權補完;mirror risk 先例)
3 處接線,只改 shell.html + shell.js,五源檔零觸:
1. **shell.html `<link>` 區(view-risk.css 行 58 後)** 加 `<link rel="stylesheet" href="/static/view-governance.css?v=20260712.p2-governance" />` + 中文註釋(說明 `.governance-view` 兩層[頁內塊 + oc-* shim]、oc-tabs-wrapper 不 port、3 處 hex 後備移除緣由,對齊 view-risk.css 註釋風格)。
2. **shell.html `<script src>` 區(view-risk.js 行 225 後、shell.js 前)** 加 `<script src="/static/view-governance.js?v=20260712.p2-governance"></script>` + 中文註釋(4 路併入 IIFE / autonomy 早於 govtab TDZ / loadAll 唯一重綁 / **autonomy-posture.js·governance-tab.js·canary-tab.js 不在此以 <script src> 載**由 IIFE fetch-text 復用 / **governance.js :215 已載勿重複** / 於 shell.js 前載註冊 OC_NATIVE_VIEWS / 五源檔零改回滾錨)。
3. **shell.js VIEWS entry(原行 119)** governance entry 加 `iframe: false`(保留 `flag: true`)= `{ id: 'governance', …, flag: true, iframe: false }`,對齊 risk 行 128 形制;上方新增「Phase 2 第 16 個原生遷移(iframe:false;交易關鍵/12 寫治理,共享 IIFE 復用)——render/pause/resume 由 view-governance.js 註冊」風格註釋。

**驗證:**
- `node --check shell.js` → **SHELL.JS SYNTAX OK**。
- shell.html 實際 tag 計數:`<link ...view-governance.css>`=**1**、`<script ...view-governance.js>`=**1**、`<script src="/static/governance.js">`=**1(未重複)**。載入序 **governance.js(224) < view-governance.js(246) < shell.js(247)** ✔。
- shell.js governance entry `flag: true, iframe: false` 並存(現行 131)✔。
- git numstat:`shell.js`=**13 add / 1 del**、`shell.html`=**21 add / 0 del**;五源檔(tab-governance.html/governance-tab.js/canary-tab.js/autonomy-posture.js/governance.js)全 **0-0 無 diff**;view-governance.js/css untracked。**只改 shell.html+shell.js,五源檔零觸 ✔。**

## 誠實邊界(NEEDS-LINUX + operator)
真渲染 / 12 寫真行為 / typed-confirm 真閘 / 三態徽 / Trust TTL 配色 / T3 朱印形制 / 雙輪詢真停啟 / loadAll clone-rebind 真效果 / paper 隔離真守恆 = 需 Linux runtime + operator 實證。Mac 靜態(node --check + ratchet 0/0 + R71 空集 + discover 模擬)只證 source 事實。**不 commit(PM 統一提交);交易關鍵 E1a→E2→E3→E4 全鏈 + operator Linux 批驗才 cutover。**
