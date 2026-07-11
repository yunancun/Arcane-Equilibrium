# 10 · Phase 2 tab 遷移 recipe(iframe → 原生玄衡 view)

> PM(R55,2026-07-11)。承 P1.1-a 殼(design/09)+ P1.4 組件庫(shell-components.css)+ 四層測試套。
> 本檔=**18-tab 遷移的可重複 recipe**;每 tab 一 checkpoint(E1a→E2→E4)。
> **⚠ verify-first 邊界**:原生 view 的**渲染正確性/真值/狀態=NEEDS-LINUX runtime + operator 視覺**;
> 純 Mac 自主只能靜態驗(結構/語法/fetch 路徑/ratchet)。故 recipe 定「**先遷 1 個→operator Linux 驗證→再規模化**」。

## 0 · 遷移機制(shell.js router)
現 VIEWS 全 `iframe:true`,router(`navigate`/`onHashChange`)建 lazy iframe。遷移一個 view=:
1. 為該 view 寫**原生 render fn**(`renderView_<id>(hostEl)`),用組件庫 class 建 DOM,fetch 既有 GET 填真值。
2. VIEWS 該 entry `iframe:true`→`iframe:false` + 加 `render: renderView_<id>`(或 `module: 'view-<id>.js'`)。
3. router 分派:`iframe:false` 的 view 呼 render fn 注入 `#oc-view-host` 的原生容器(非 iframe);**router/visibility 機制不動**(注:原生 view 無 iframe,`notifyViewVisibility` 對其改為呼 view 自身 pause/resume hook——遷移時同步接,勿讓原生 view 隱藏仍輪詢=freshness 退步,鏡像 iframe visibility 語義)。
4. **second-adapter 穩定接口**(design/09 §1):render fn 是 P2 遷移的唯一新增擴充點,router 為其穩定宿主。

## 1 · 原生 view pattern(每個遷移 view 遵循)
- **fetch**:走既有 GET 路由(**必 ∈ 5b 對齊 ratchet authoritative**,否則測試紅);per-view fetch(P1.1-a 模式;shared WS=P1.2 後續,首批不依賴)。復用 `ocApi`/`ocAuthCheck`/formatter,不重造。
- **render**:用 **P1.4 組件庫**(`.panel`/`.panel-t`/`.kpis`/`.kpi`/`.tbl`/`.tag`/`.fresh-badge`/`.logblock`/`.note`)+ tokens.css 原子(`.num`/`.seal-mark`)。**零 inline style/裸 hex**(ratchet 0/0/0;動態值走 `setProperty` scoped-var)。
- **canon 7 狀態**(硬要求):loading=skeleton/spinner;無真值=`—`/blocked 標籤;stale=fresh-badge;error=不崩顯錯;**絕不假 0.00/假成功**。
- **canon 6/9**:若 view 含虧損/風險/live marker,用 `--neg`/`--warn`/`--live`;**交易關鍵 view(live/demo/governance/risk)最後遷 + flag**(§1),且遷移須過 **live-hardening snapshot 守衛**(R53)不稀釋。
- **寫路徑**:read-only view 零寫;含寫的 view 走既有 Rust authority IPC(殼不新增寫路徑),typed-confirm 用既有 common-modals。

## 2 · 靶 tab 選序(交易關鍵最後)
**首批=最簡單 read-only cross-cutting**(無寫/無 typed-confirm/少 GET/純狀態展示)。候選(執行輪實測其 fetch 複雜度後定):
`monitor`(tab-monitoring 系統狀態)、`gates`(tab-edge-gates 封驗狀態)、`ai`(tab-ai 狀態)、`phase4`。
**首個遷移=證明 pattern**(組件庫+router+fetch+canon7 全鏈)。之後:其餘 read-only cross → crypto read-only(overview/replay/earn/strategy)→ **交易關鍵最後**(paper→demo→live/governance/risk,各 flag+live-hardening 守衛)。
內容守恆:遷移零丟失(對 legacy tab 逐元素);`charts`(/trading?embed=1 外部 lightweight-charts)可續 iframe 至 Phase 3(CDN 依賴,非急遷)。

## 3 · 每遷移 checkpoint 驗收
**Mac 靜態(自主可驗)**:node --check 新 JS;ratchet 0/0/0(新 view JS/CSS);smoke asset-ref(新引用存在);**5b 對齊 ratchet**(新 fetch call-site ∈ authoritative 或 allowlist);registry smoke(VIEWS visId 若動 visibility 消費者則守);live-hardening 守衛(若觸 live)。E2 對抗審查(canon 守恆/零寫路徑/組件正確用/visibility 語義);E4 回歸零退步。
**NEEDS-LINUX + operator(執行輪後必須)**:原生 view 真渲染(真資料/三態/版式)、視覺回歸對 legacy、鍵盤走查、（含 live 者）五閘真 enforced。**首個遷移完成後 loop 暫停,待 operator Linux 驗證 pattern 通過再規模化其餘 17。**

## 4 · 為何先 recipe 後暫停(verify-first)
盲建 18 原生 view(無 Linux 渲染驗證)= 系統性 bug 風險 + 違 verify-first。故:①本 recipe 立可重複模式;②執行輪建**第 1 個**原生 view(Mac 靜態驗全綠);③**operator Linux 驗第 1 個**(渲染/資料/視覺)——pattern 驗證後,其餘 17 照 recipe 規模化。此前 loop 於「首遷完成/待 Linux 驗」長 wakeup 暫停,不盲量產。

## 5 · 前置依賴狀態
✅ 殼 router(design/09)· ✅ 組件庫(P1.4)· ✅ 四層測試套 · ✅ 對齊 authoritative 路由清單(5b)。
⏳ P1.2 shared WS(真遙測/衡樑真值,原生 view 真新鮮度徽章升級)=NEEDS-LINUX,首批用 per-view fetch 不阻塞。
⏳ operator:①Linux runtime 供渲染驗證 ②殼 chrome 視覺回饋(mass 遷移前確認 lane/rail/衡樑形制)③首遷 pattern 驗證 go。
