# E1a GUI 改動 — P0.2 批次 1:殼層 inline style 清理 + oc-utilities.css 建立 · 2026-07-10

範圍:`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`
規格正本:`docs/execution_plan/gui_redesign/design/05_utilities.md`(下稱 §N 均指該檔)
狀態:**E1a IMPLEMENTATION DONE — 待 E2 + A3 + E4 review;未 commit**

## 一、觸碰檔案(每檔一行)

| 檔案 | 改動 |
|---|---|
| `oc-utilities.css`(新建) | §A 詞彙表與規格 §4 **byte-identical**(程式 diff 驗證)+ §B annex 首兩員 `.oc-btn--xs`(帶 !important,原因見四.5)/`.oc-cat-tag`(中性化);檔頭中文 MODULE_NOTE 註明 spec-of-record + append-only |
| 22 份完整文檔 HTML | 統一插 `<link rel="stylesheet" href="/static/oc-utilities.css" />` 於 tokens-compat 之後(三連順序程式斷言 22/22);**P0.1 後全檔已統一 `/static/` 前綴,任務所述混合前綴情況不存在**;fragments(`_dashboard_card`/`cards/*`)未接 |
| `console.html` | 20 處 style= → 0;頁內新 CSS:`.mc--sm/.mc--md .mc-val` 父層修飾類 + `.sp-btn`/`.sp-btn--live.active`/`.sp-btn--demo.active`;JS:L782-783 display→`classList.toggle('hidden')`、六條按鈕 style 寫入→`classList.toggle('active')`、三條 `style.opacity='1'`→`classList.remove('is-stale')` |
| `common-modals.js` | 9 處 style= → 0;oc-gp-* 四個 display 寫點 + counter 兩寫點 + oc-tc-meta 兩寫點全部 classList 化;hint/input 冗餘宣告親證後刪(見四.3) |
| `common-formatters.js` | 2 處 → 0;`ocCategoryTag` 中性化 `<span class="oc-cat-tag">`(刻意視覺變更,PM 已批);`ocPnlCell` 破折號 td→`t-dim` |
| `common.js` | 1 處 → 0;ocLoadError 重試鈕→`oc-btn oc-btn--xs` |
| `index.html` | 7 處 → 0;`row gap-2`/`fs-section`/`flex-1 t-warn`/`t-accent fw-semi` + 三組件入 styles.css |
| `styles.css` | 檔尾追加 `.idx-logout-btn`/`.idx-banner`/`.idx-banner-cta`(§8 階梯第 4 級;全語義 token 零 hex) |
| `trading.html` | 11 處 → 0;頁內新 CSS `.card--md .card-val` + `.kv-line`;markup 5 處 + JS 模板 6 處 |
| `login.html` | style= 清理 NO-OP(本 0);僅插 link 1 行——**該檔有兄弟 session 髒改動(login error fallbacks),diff 隔離驗證:我只加了 link 行** |
| `tab-settings.html` | 僅刪頁內 `.hidden{display:none!important}` 副本(規格 §2 已收編逐字相同定義);其 141 處 style= 屬該檔所屬批次,未動 |

## 二、驗證(逐項)

1. **度量(§0 口徑 `grep -c 'style="'`)**:console 20→**0**;common-modals 9→**0**;common-formatters 2→**0**;common.js 1→**0**;index 7→**0**;trading 11→**0**;login 0→0。合法殘留(scoped-var 屬性形式)= 無;DEFER 清單 = **空**(全部 display 轉換點的寫點都在本批檔案內)。
2. **node --check**:common-modals.js / common-formatters.js / common.js 直檢 PASS;console(33,461 chars)/index/trading/tab-settings 四檔 inline `<script>`(排除 src=)抽取合檢 PASS。console 註釋修訂後真重跑(帶抽取長度斷言)再 PASS。
3. **HTML 結構**:22/22 檔 HTMLParser tag-stack residue=0;22/22 三連 link 順序 tokens→compat→utilities 程式斷言;oc-utilities/styles/三檔頁內 style 塊 brace 平衡全 OK。
4. **JS 路徑兩態閉合(jsdom headless,25/25 PASS;runtime smoke 屬 P1.0)**:
   - 側欄切換:初態 live 顯+btnLive active → `toggleSidePanel('demo')` → live 掛 hidden+btnPaper active → `toggleSidePanel('live')` 復原(事件 onclick → classList.toggle → `.hidden`/`.sp-btn--*.active` CSS)。
   - modal 顯隱:openPromptModal 單行/多行/counter 四配置 hidden 加減閉合;openTypedConfirmModal meta 有/無 metadata 兩態閉合。
   - is-stale:三卡 markup 初態掛 is-stale → remove 後 un-dim;`style.opacity` 代碼寫點殘留=0。
5. **零裸 hex / 零新 inline**:git diff added lines hex 掃描=0、`style="` 掃描=0;oc-utilities.css §A 與規格 §4 diff 級一致(byte-identical);新 CSS 全部 var() 剝註釋後 26/26 解析到 tokens.css 真 token(雙主題皆有定義);§3.1 已知 !important 面(entry-grid/oc-diff-changed)零重疊。
6. **範圍**:未動 Python/Rust;repo 兄弟髒改動(auth.py、helper_scripts 等)未觸碰;17 個非本批 tab 檔 diff 斷言 +1/-0(僅 link 行)。

## 三、鐵則自查(每元素一行)

| 元素 | 鐵則 | 結果 |
|---|---|---|
| side-panel-live / side-panel-paper | 一(display 軸) | 寫點僅 L782-783,同批 classList 化,殘留=0;§3.3 引理成立(`.side-panel` 無 display 宣告,show 端原寫 `''`) |
| spbtn-live / spbtn-paper | 一(bg/border/color 軸) | 六條寫點同批全轉 `classList.toggle('active')`,殘留=0 |
| live-section / live-balance-section / live-pnl-section | 一(opacity 軸) | 寫點僅 L856-858,同批轉 remove('is-stale'),殘留=0(jsdom 斷言) |
| oc-gp-body/-input/-textarea/-select/-counter | 一(display 軸) | 全部寫點在 openPromptModal 單函數內,7 寫點同批 classList 化,殘留=0 |
| oc-tc-meta | 一(display 軸) | 兩寫點同批 classList 化;L393 `style.whiteSpace='pre-line'` 常量寫留置(PA 計劃未列;無 white-space utility 掛此元素,無軸衝突;P0.4 候選) |
| s-live-mode(L904 wipe) | 二 | 零直掛;父 `#live-section` 掛 `mc--sm`;L905 `style.color` 留 P0.4(color 軸無 utility 掛此元素,無衝突) |
| s-live-pnl / s-pnl / s-api / s-oc / s-engine-alive(wipe) | 二 | 零直掛;font-size 走父層 `mc--md`(s-live-pnl 無字級修飾,父僅掛 is-stale) |
| s-live-balance / s-paper-balance / s-cost(僅 textContent,未 wipe) | 二(預防) | 按 PA 計劃統一走父層 mc--md,未直掛 |
| regime-val(trading L509 wipe) | 二 | 零直掛;父 `#regime-card` 掛 `card--md` |
| 全部 59 個 added-line class token | 三(拼寫) | 程式核對 59/59 可解析到定義(oc-utilities/頁內/styles.css/注入 CSS) |

## 四、小決策與備註(理由)

1. **前綴**:22 檔 tokens link 已全為 `/static/` 形式(P0.1 統一),oc-utilities 照抄同款;任務所述「相對前綴」檔不存在。
2. **新 CSS 用新語義 token**(--border-subtle/--text-secondary),不用 compat 別名(--border/--text-dim):compat 層 P0.4 整檔刪除,不擴其消費面;渲染值同。
3. **冗餘刪除親證**:注入 CSS `.oc-prompt-label{display:block;font-size:12px;color:var(--text-dim);…}`、`.oc-prompt-input{width:100%;…}`(common.js L999-1000)與 oc-tc-hint/oc-tc-input 原 inline 宣告逐字重複,故只餘 `mt-2` / `mono ls-wide`。
4. **父層修飾類寫字面 px**(13px/14px,照 PA 計劃):不用 var(--fs-base/--fs-md) 因兩 token 在 `data-density="compact"` 下漂移(12/13px),會改變側欄現渲染;P0.4 收斂時再議 token 化。
5. **`.oc-btn--xs` 帶 !important**:`.oc-btn` 的 padding/font-size 由 ocInjectBaseCSS 運行時注入,注入 `<style>` 永遠後載、同 specificity 勝出,annex 必須壓回(§3.1 同一結構論證);`.oc-cat-tag` 為全新類無競爭,不帶。
6. **ocCategoryTag 中性化副作用**:`_OC_CAT_CONFIG` 的 color/bg 欄位(#3b82f6/#22c55e/#f59e0b/#a855f7/#94a3b8 系)自此僅 label 在用——palette 外色清單即此五組,已按計劃棄用,hex 字面留在 dead data 內(非新增行),P0.4 清理;已加註釋標記。
7. **刻意視覺變更(§5 收斂,均為規格捨入/歸位)**:sp-btn 圓角 6→5;h2 下距 5→4;側欄註腳上距 6→8;btn-row 上距 14→12;oc-tc-meta 邊距 6/10→8/12;typed-confirm input 字距 1px→0.08em、字族 monospace→--font-mono;cat-tag/重試鈕字號 10→11、cat-tag 圓角 3→5+中性配色;idx-logout/idx-banner-cta 圓角 4/6→5;**idx-banner 邊框 rgba(210,153,34,.3)→var(--warn) 全濃度**(token 集無中间 alpha 檔,PA 指定 token 表;A3 可複核觀感);banner emoji 16→15(fs-section);sym-hint 9→11px、上距 3→4;kv-line 髮絲線 rgba(48,54,61,.3)→--border-subtle;disabled-card 英文小標上距 2→4。
8. **雙主題**:本批新 CSS 全 token 化,tokens.css 兩主題均有定義;存量文檔仍 `data-theme="dark"` 釘死(P0.1 決策),帛晝實看留 P1.3 解釘後。

## 五、A3 必審項

1. idx-banner 邊框由 30% alpha 琥珀升為全濃度 --warn 的觀感(上文四.7)。
2. ocCategoryTag 中性化後,tab-demo/tab-paper 持倉表的品類辨識依賴文字(U本位/現货/币本位/期權)而非顏色——可用性複核(canon 1 之刻意結果)。
3. 側欄 Live/Demo 切換鈕 active 配色語義:live=熱紅 --live 系、demo=--accent 選中系(舊藍中性化),Trading-Aware 色語義複核。
4. typed-confirm input 字距/字族 token 化後的可讀性(phrase 鍵入場景)。

## 六、E4 回歸建議面

console 側欄(切換/30s 刷新 un-dim/mc 字級)、openPromptModal 三模式 + openTypedConfirmModal(metadata 有無)、tab-demo/tab-paper 持倉品類標籤、ocLoadError 重試鈕、index legacy banner、trading 側欄(regime 卡/指標 KV/空態)、tab-settings restartModal 顯隱(頁內 .hidden 副本已刪,改吃全局)。
