# GUI 大改 P0.2 批次 4 — learning/replay/paper/earn inline style 清理

> E1a 實作;規格正本 `docs/execution_plan/gui_redesign/design/05_utilities.md`。日期 2026-07-10。
> 狀態:主體清理 + 全部驗證完成,待 E2 對抗審查 + A3 UX 審 + E4 回歸。

## 一、範圍與度量

實測基線與 PM 快照差異:PM 計 99;實測 HTML 92(paper 35 非 32、其餘相符),
JS `style="…"` 屬性 10(handoff 5 / earn 5);PM「5+5」對 JS 指的是 `.style.`/模板,實測 JS
模板 `style="…"` 各 5。全站 `style="…"` 972→870,淨減 **102**(=92 HTML + 10 JS,精確吻合)。

| 檔 | 前 | 後 |
|---|---|---|
| tab-learning.html | 27 | **0** |
| tab-replay.html | 1 | **0** |
| tab-paper.html | 35 | **0** |
| tab-earn.html | 29 | **0** |
| handoff_helper.js | 5 | **0** |
| earn-tab.js | 5 | **0** |
| **合計** | **102** | **0** |

- `app-paper.js`=**NO-OP 確認**(0 `style="…"`、0 `.style.` 寫點;replay+paper 載入但無 inline style;
  其 className/classList 僅動 `active`/`status-chip`,不與本批任何轉換元素耦合)。
- `app-learning.js`=**故意跳過**(2 個模板 `style="background:${color}"`;它是 index.html 載入的孤兒檔,
  Phase 2 revive/retire 未決 → 不清可能退役的碼)。合法殘留 §7:無 custom-property-only 形式殘留。

## 二、詞彙表增補(§11 append-only)

- **§A 新增 `.ml-3{margin-left:var(--sp-3)!important}`**(家族 7 margin,`10px→sp-3=12`;tab-paper 餘額標籤
  margin-left:10px 消費)。oc-utilities.css §A + 規格 §4 fence **同 commit byte-identical 鏡像**;
  spec-drift guard 2/2 綠。批次 2 已立 ml-2 先例,ml-3 為 sp-3 檔位補全。**A3/PA 需認可此 append。**
- annex(§B)未動;`.oc-btn--xs`(batch 1 既有)複用於 6 個小按鈕(learning 3 審核鈕 + paper 3 重試鈕)。

## 三、兩鐵則自查(逐元素)

**鐵則一(JS 軸同批原子化)——**
- `earn-tab.js _show/_hide`:`e.style.display=''/'none'` → `classList.remove/add('hidden')`;
  對映 19 個狀態殼(balance/preflight/products/positions/records 的 loading/error/empty/data + submit-loading),
  HTML 同批改 class:error/empty/data/submit-loading 帶 `hidden`(初始隱),loading 不帶(初始顯),§3.3 引理成立。
  jsdom 兩態閉合驗證 PASS(show→回落 CSS/inline-flex、hide→none)。
- `tab-paper.html paper-confirm-modal`:自檔 inline script `style.display='flex'/'none'`(顯式 flex,§6 分支 b)
  → `classList.remove/add('hidden')`;overlay 補 `.paper-confirm-overlay{display:flex}` 供給置中佈局,
  `class="hidden paper-confirm-overlay"`。jsdom:open=flex / close=none PASS。
- 跨檔寫點:`tab-learning.html banner.style.display`(#lg-redirect-notice)= 該元素**無 inline style=**、不在本批轉換清單 → 不觸碰(非鐵則一標的)。

**鐵則二(className-wipe)——**
- `tab-paper #feed-badge`:`loadFeed` 每刷新 `fb.className=/badge.className=` 整串重寫 → **禁直掛 utility**;
  改頁內 `#feed-badge{margin-left:var(--sp-2);font-size:var(--fs-micro)}` id 選擇器(不隨 className 抹除,承 batch3 exp-status-badge 先例)。
- 其餘 className 重寫元素(earn verdict/stage0r-row/badge、form input/hint;paper session-badge、app-paper status-chip;
  handoff banner/overlay)**均非**本批加 utility 的目標;加 utility 者(state 殼、模板 `<td>/<code>/<span>`、
  h3/modal box)全走 `_show/_hide`(classList,保 class)或 innerHTML 整段重渲染(class 在模板串內存活),窮舉無衝突。

## 四、palette 外色 / 動態值(§5.5 / §7)

新頁內組件遷入的 rgba(無 token,verbatim,**全帶 P0.4 註記**):paper modal scrim `rgba(0,0,0,.6)`、
box-shadow `rgba(0,0,0,.5)`、藍色 info tint `rgba(56,139,253,.08/.2)`、sparkline bg `rgba(13,17,23,.5)`。
邊框/表面 hex 全 §5.5 token 化(`#161b22→--card-bg`、`#30363d→--border-strong`、`#21262d→--border-subtle`)。
**新增行零裸 hex(#rrggbb)**;無真動態值硬轉(sparkline 幾何/progress 未觸)。
opacity:0.6(handoff「選填」)→ `o-50`(0.5,§13 機械過渡,P0.4 複審是否改色階)。

## 五、驗證(全綠)

1. 度量:六檔 = 0(前後計數見 §一);app-paper.js NO-OP 確認;app-learning.js 明列跳過。
2. `node --check`:handoff_helper.js / earn-tab.js + 4 HTML inline script 抽取(含長度斷言防空流假 PASS)全 PASS。
3. HTML tag 平衡:4 檔 HTMLParser residue=[]、errors=[]。三連 link(tokens→compat→utilities)8/9/10 順序未擾。
4. spec-drift `test_gui_utilities_spec_drift_static.py` 2/2 PASS(§A↔§4 byte-identical,含 ml-3)。
5. jsdom 兩態閉合 10/10(earn 殼 show/hide + submit-loading inline-flex + paper modal open/close)。
6. 全 utility 名解析(35 個全定義於 oc-utilities.css);新頁內組件名全站 0 碰撞(sweep)。
7. `tests/structure/` 381 passed / 5 failed — 5F 與 batch3 **完全相同**(stock_etf_ipc×3 / stable_boundary_docs /
   strategy_blocked_symbols,全 Rust/docs,零 static/ 關聯),**零新失敗**。
8. 零 Python/Rust 觸碰;未 commit。

## 六、頁內組件清單(§8 level-3)

- tab-earn:`.earn-h3-note`(font-weight:normal 無 utility)、`.earn-form-select--sm`(min-height 非檔位)。
- tab-learning:`.lg-cell-ellipsis`(max-width/ellipsis)、`.lg-feed-item`(border-bottom token 化)、`.lg-metrics-2col`(grid-template)。
- tab-paper:`#paper-init-bal`(定寬 90px §5.4)、`#feed-badge`(id 選擇器抗 wipe)、`.paper-pnl-sparkline`、`.paper-confirm-{overlay,box,header,close,info,footer}`(平倉 modal)。

## 七、A3 / E2 必審項

- **ml-3 append 認可**(§11,spec §4 + CSS 已鏡像)。
- earn 狀態殼 error 文字色 `--yellow`→`t-warn`(§5.5 收斂)在玄夜/帛晝雙主題觀感。
- paper 平倉 modal 遷 token 後(`--card-bg`/`--border-strong` 表面 + verbatim scrim/藍 tint)雙主題觀感;A3 anti-fake:modal 仍走 typed-confirm 前置的 confirmPaperClose,顯隱行為 jsdom 已證等價。
- handoff「選填」opacity→o-50(0.5)是否需改色階(t-muted),留 A3 裁。
- learning feed-item / cell-ellipsis 截斷在窄欄表格的可讀性。
