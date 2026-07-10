# GUI 大改 P0.2 批次 5 — edge-gates / strategy inline style 清理

> E1a 實作;規格正本 `docs/execution_plan/gui_redesign/design/05_utilities.md`。日期 2026-07-10。
> 狀態:主體清理 + 全部驗證完成,待 E2 對抗審查 + A3 UX 審 + E4 回歸。未 commit。

## 一、範圍與度量

實測基線 vs PM 快照:PM 計 84;實測 **86**(edge-gates 3 + strategy 83)。全站 `style="…"` 870→**784**,
淨減 **86**(=3+83,精確吻合)。

| 檔 | 前 | 後 |
|---|---|---|
| tab-edge-gates.html | 3 | **0** |
| tab-strategy.html | 83 | **0** |
| **合計** | **86** | **0** |

- 兩檔皆只載 common*.js,自成一體,無獨立 JS 渲染檔要清(符 PM 交底)。
- 合法殘留 §7:兩檔源碼態零殘留;sh-bar 進度填充改 `setProperty('--fill-w/--fill-x')`,runtime 生成的
  `style="--fill-w:…"` 屬 §7 form-1(canon 唯一豁免,不入計數;靜態源碼無此屬性,故計數=0)。

## 二、詞彙表:零增補

**本批不需任何新 utility** — 所用 utility(fw-semi/flex-1/fs-dense/t-dim/fs-micro/row/wrap/gap-1·2/
row-between/m-0/hidden/p-3/fs-base·md/block/mt-1·2·3/mb-1·2·3/py-2/px-3/ml-2·3/ml-auto/t-primary·warn·pos·neg/
nowrap/mono)+ annex `oc-btn--xs` 全部**既存**。故 **§4/annex 未動、oc-utilities.css byte 不變**
(md5 `56eecfd9…`,129 行),spec-drift 測試非必需(未觸 fence)。

## 三、放置階梯裁決 + 一項規格偏離(A3/E2 必審)

- **tab-strategy 是唯一無頁內 `<style>` 塊的在清 tab**(其餘 monitoring/system/settings/paper/earn/learning/replay/edge-gates 均有)。
  §8 level-3 字面「無塊文檔升第 4 級(styles.css)」以 index.html 為例——但 styles.css 定義為
  **殼層文檔共享組件**,把 strategy 專屬選擇器寫入會污染殼層 CSS 且違 level-4 語義。
- **裁決(自主小決策,已註明理由)**:為 tab-strategy **新建一個頁內 `<style>` 塊**承載其多屬性頁組件,
  與全部其他 tab 一致(各有本頁塊),契合 §8「inline→塊,朝正確方向」與 P0.4 收斂目標。
  **此為對 §8「只寫既有塊」字面的刻意偏離,列 A3/E2 裁決點。** 塊置於 body(`ocInjectBaseCSS` head 注入之後),
  文檔序制勝,零 `!important`(批次 2 先例)。
- 頁組件(全 var() token、零 hex):`sh-summary-card`(緊湊卡內距)、`sh-dist-bar`+`sh-dist-fill(--active/--paused)`
  (迷你分布條 + scoped-var 進度)、`strat-create-panel`(建立表單卡)、`strat-form-row`(底對齊 flex,align-end 非 center 故不套 .row)、
  `strat-id-num`(margin-right,全站僅 4 處不升 utility)、`#new-symbol/#new-qty`(§5.4 定寬 px 字面)、
  `strat-cycle-footer`、`strat-engine-grid`(1fr 1fr)、`strat-reason-cell`(ellipsis)、`strat-detail-card`(Diff/Effect 卡)。
- edge-gates:唯一頁組件 `.edge-scroll-x{overflow-x:auto}`(§4 無 overflow-x utility)入其**既有**塊。
- **baseline sweep**:11 個新類名全 static/ 掃描 = **0 既存碰撞**。

## 四、兩鐵則自查(逐元素)

**鐵則一(JS 軸同批原子化)——**
- `#create-form`(strategy):inline `display:none` + `toggleCreateForm()` 的 `.style.display=''/'none'`
  → `class="hidden …"` + `classList.toggle('hidden')`。§3.3 引理(唯一 inline display 來源)成立。jsdom 4/4 PASS。
- `#sh-bar-active`(strategy):JS `.style.width` → `setProperty('--fill-w')`,`.sh-dist-fill{width:var(--fill-w,0%)}` 消費(§7 form-1)。jsdom PASS。
- `#sh-bar-paused`(strategy):JS width+left → `--fill-w`/`--fill-x`(`left:var(--fill-x,0)`)。jsdom PASS。
- 殘留自驗:`.style.display`=0、`.style.width|.left`=0(全轉 classList/setProperty)。**本批無 is-stale 標的。**

**鐵則二(className-wipe)——**
- tab-strategy 唯一 `.className=` 整串重寫標的 = `regimeBadge`(`#orch-regime`,L473/476)——**未對其掛任何 utility**
  (保留原 `class="oc-chip oc-chip-neutral"`),不違鐵則二。
- 所有掛 utility/頁類的元素皆非 className-wipe 標的:或走 textContent/innerHTML(自身 class 不動),
  或在 innerHTML 模板串內(class 隨串重生),或僅 setProperty。窮舉無衝突。
- edge-gates:`.className=` 僅在 metric-val(edge-crisis/pass/readiness/health-val),與我改的 3 元素
  (edge-health-body/edge-readiness-list/overflow wrapper)不相干。

## 五、palette 外色 / hex(§5.5 / §7)

- **新增行零裸 hex、零 rgba**。inline `#21262d`(4 處)→ `var(--border-subtle)`(§5.5);
  `background:var(--green)/var(--yellow)`(進度條)→ `var(--pos)/var(--warn)`;確認 `21262d` 全站於本檔=0。
- diff-changed 行高亮 `rgba(210,153,34,0.06)` → **復用既有 canon `.oc-diff-changed`**(common.js:986,
  背景 rgba .12 + border-color .4 `!important`)。**A3 注意**:tint 由 .06→.12(略深)+ 理論上 tr border-color 提示
  (實測 `.oc-table td` 邊框自帶色,tr border-color 不繼承覆蓋 → 視覺淨效果僅背景加深);語義=「參數變更行」與其原用途(風控表單 diff)完全一致,故選復用而非新造。
- edge-gates 既有塊內 pre-existing rgba(邊框色卡)非本批新增、非 inline style=,不觸碰。

## 六、驗證(全綠)

1. 度量:兩檔 = 0(§一);全站 870→784(−86 精確)。源碼態零 §7 殘留。
2. `node --check`:兩檔 inline `<script>` 抽取(排除 src=;含 >200 char 長度斷言防空流假 PASS)——
   edge-gates 12475 char/2 block、strategy 28126 char/2 block,exit 0。
3. HTML tag 平衡:兩檔 HTMLParser residue=[]、errors=[]。三連 link(tokens→compat→utilities)8/9/10 順序未擾。
4. §4/annex 未動 → spec-drift 測試非必需;oc-utilities.css md5 不變(129 行)佐證。
5. jsdom 兩態閉合 **9/9 PASS**(create-form hidden toggle 4 + sh-bar scoped-var 3 + §7 custom-property-only 斷言 2)。
6. 全 utility 名解析(含去 `^\.` anchor 複核 mb-1/2/3 同行定義,承 batch 4 教訓);11 個頁類 0 碰撞。
7. 零 Python/Rust 觸碰;未 commit。

## 七、A3 / E2 必審項

1. **§8 偏離**:tab-strategy 新建頁內 `<style>` 塊(vs 字面「升 styles.css」)——見 §三理由,請裁認。
2. **`.oc-diff-changed` 復用**於 strategy 參數 diff 表(tint .06→.12 + 語義對齊),見 §五;是否接受該微收斂。
3. 進度條由絕對定位雙 fill + scoped-var(--fill-w/--fill-x)重建,雙主題(玄夜/帛晝)下 --pos/--warn 觀感。
4. `strat-reason-cell` ellipsis 截斷(max-width 260px)在窄欄的可讀性;`strat-create-panel` 收斂後(radius 8→r-2、border→--border-subtle)觀感。
5. `sh-summary-card` 內距 10/16→12/16、`strat-cycle-footer` radius 6→r-1(5) 等 §5.2/§5.3 收斂微變。
