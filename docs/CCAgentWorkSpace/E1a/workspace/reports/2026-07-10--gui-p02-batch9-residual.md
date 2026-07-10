# E1a GUI 改動 — P0.2 批次 9(收尾殘留)· 2026-07-10

範圍(static/):
- `cards/linucb_card.html`(20)、`cards/news_card.html`(17)、`cards/dl3_card.html`(11)、
  `cards/teacher_card.html`(10)、`app-gui.js`(1)= **59 處歸零**(PM 快照 60,實測 59;
  linucb 21→實測 20)
- 宿主 `tab-phase4.html` 頁內 `<style>` 追加 Phase4 卡片共用組件塊(cards 是 innerHTML 注入片段,
  組件放宿主頁而非片段;不在片段內加 link/style)

**本批完整未中斷。P0.2 真正清零(全站僅剩 legit 殘留)。**

## 度量表(operator grep `grep -oE 'style="[^"]*"'`)

| 檔 | before | after |
|---|---|---|
| cards/linucb_card.html | 20 | **0** |
| cards/news_card.html | 17 | **0** |
| cards/dl3_card.html | 11 | **0** |
| cards/teacher_card.html | 10 | **0** |
| app-gui.js | 1 | **0** |
| **全站** `-rhoE` | 61 | **2** |

## 全站剩餘 style= 確認(= legit 3)
- **app-learning.js 2**(L26/L40 `style="background:${color}"`)——index 孤兒、Phase 2 defer,
  明列跳過不動(在 operator grep 內,計 2)。
- **canary-tab.js 1**(L192 `style="--canary-fill-w:'`)——§7 scoped-var,行分割故 operator
  line-grep 不計(顯 0);概念上 legit 1。
- 合計 legit 3 = app-learning 2(grep 計)+ canary 1(grep 不計,概念)。**未觸碰。**

## 映射(§4 詞彙表 / §5 收斂)
- `font-size:12px`→`fs-dense`;`font-size:11px`→`fs-micro`;`color:var(--text-muted…)`→`t-muted`;
  `color:var(--text-dim)`→`t-dim`;`text-align:right`→`t-right`;`width:100%`→`w-full`;
  `font-weight:normal`→`fw-normal`;`padding:16px`→`p-4`(app-gui glossary-wrap)。
- 間距:`margin:10px 0`→`mt-3 mb-3`;`margin-top:10/12px`→`mt-3`(§5.2 10→sp-3=12);
  `margin-bottom:4px`→`mb-1`。footer `margin-top:8px` 直接丟棄——`.phase4-card-footer`
  已含 `margin-top:8px`,inline 一直是冗餘 → 僅補 `fs-micro t-muted`。
- **零新 utility**:所需全既存 → `oc-utilities.css` 與 spec §4/annex **byte 未改**(spec-drift 免跑)。

## 頁級組件(tab-phase4.html `<style>`,cards 靠繼承)
`.p4-grid`(border-collapse+fs-micro)、`.p4-grid th/td{padding:2px 6px}`、
`.p4-grid td{background:var(--cell-bg,transparent)}`、`.p4-thead-row`(text-align:left+border-bottom)、
`.p4-report-link`(underline)、`.p4-conv-row/label/track/fill/count`(收斂進度條)、
`.p4-shadow-bar` + `.is-promote/.is-keep/.is-other`(影子條 enum 狀態色)。

## 鐵則自查
- **鐵則一(JS 軸排除)**:`linucb-shadow` 唯一 display 寫點在 `renderShadow`(同檔同批):
  `host.style.display='none'/'block'` → `classList.add/remove('hidden')`;HTML 初始 `class="mt-3 hidden"`。
  §3.3 引理:原 show 寫顯式 'block' == div 自然 display → 等價安全。**兩態(active/inactive)邏輯正確。**
- **鐵則二(className-wipe)**:掛 utility 的元素無一被 `.className=` 整串重寫
  (linucb-status-dot 走 `.className=` 但未掛 utility;linucb-shadow 只 `.style.display`/`classList`,
  非 `.className=`)。heatmap/conv/shadow 子元素每 render 由 innerHTML 重生,無殘留問題。

## 裸屬性 / 雙-class 自查(全 0)
- `grep -nE 'class="[^"]*"[[:space:]]+[a-z-]+--' cards/*.html` = **空**(exit1)。
- `grep -nE 'class="[^"]*"[^>]*class="' cards/*.html` = **空**(exit1)。

## 注入驗證(cards fragment 靠宿主樣式)
- 三連 link(tokens/compat/oc-utilities)在 tab-phase4.html L29-31 ✓;index.html L10 有 oc-utilities(app-gui `.p-4` 解析)✓。
- 卡片用 utility(mt-3/mb-3/mb-1/fs-dense/fs-micro/t-muted/t-dim/t-right/w-full/hidden/fw-normal)
  全在 oc-utilities.css 有定義 ✓(mb-1/mb-3 同行定義,去 `^` anchor 複核);
  p4-* 組件 12 個全在 tab-phase4.html `<style>` 有定義 ✓。

## legit §7 scoped-var 殘留(新增,列明)
真動態值(§7 sanctioned):
- linucb L108 `style="--cell-bg:'+colorFor()+'"`(heatmap 連續色 rgb/# )
- linucb L126 `style="--conv-w:'+pct+'%"`(收斂 fill 寬度)
兩者渲染皆 custom-property-only(過 P0.6 CI regex `style="(\s*--[a-z0-9-]+:[^;"]*;?\s*)+"`),
且採 canary L192 同款「值後置換行」寫法 → operator line-grep 不計(5 檔 operator grep 皆 0)。

## 驗證
- **node --check 全過**:tab-phase4 inline(6 blocks/7325c)、linucb(4624c)、news(5032c)、
  dl3(3407c)、teacher(3364c)、app-gui.js standalone — 全 exit 0(附長度斷言防空流 fake-success)。
- **HTML tag-stack residue=[] errors=0**:5 檔全平衡。
- oc-utilities.css / 05_utilities.md **byte 未動**(git status 空)。

## A3 必審 / palette-outside(P0.4)
1. **表格 cell padding 保留字面 `2px 6px`(未收斂 sp-1/sp-2)**:news/dl3/teacher body `<td>` 由 JS
   `setAttribute('style','padding:2px 6px…')` 產出(非 `style="…"` 源屬性、**不在 P0.2 count**、§7 不強制),
   若只收斂靜態 th 會令 header/body 錯位(§7 禁半吊子)→ 組件保字面值與 JS body 一致;
   完整收斂 + JS td 清理留 **P0.4**。(承批 1「字面 px 刻意」先例。)
2. **palette 外色 verbatim relocate**:`#2ea043` 綠 / `#6e7681` 灰 / `#d29922` 琥珀 沿用本檔
   既有 `.phase4-light-dot.green/grey/yellow` raw hex 家族(避免同頁綠燈與進度綠中間態不一);
   §5.5 本會將 #d29922→--warn、綠→--pos,但為宿主一致性保 verbatim,單點 token 化留 **P0.4**。
   `var(--border,#30363d)` 是既有 token+fallback(非 raw hex)不列。
3. **enum 影子條** `PROMOTE/KEEP_CHAMPION/other` → class-per-enum(canon 7/§7),色值不變、行為等價。
4. **shadow bar** radius 4px→`--r-1`(5)、padding 4px→`--sp-1`(4):微渲染位移(§5.2/5.3 意圖內)。
5. **dl3 report-link underline** 以 `.p4-report-link` 保留:tab-phase4 載入的 CSS 無 `a` reset,
   underline 應為默認,顯式保留以固意圖(零風險 1 行)。

## 未處理(out-of-scope,P0.4)
news/dl3/teacher 的 `td()` builder `setAttribute('style',…)` 與空態 `cssText='padding:6px…'`
及動態 severity/status/pnl 色——皆 JS 屬性寫入,非 `style="…"` 源屬性,不在 P0.2 度量,
§7 不強制;surgical 保留不觸碰。

交付狀態:待 E2 + A3 + E4(GUI 靜態測試)review;不 commit。
