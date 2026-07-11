# 07 — 樣式 fork 合併 + 收斂契約(P0.4 · spec-of-record)

> **地位**:GUI 大修 Phase 0 **P0.4**(全站級收斂 pass,承 P0.1 token 統一 / P0.2 inline 清理 / P0.3
> 數值排版)的唯一 spec-of-record。P0.4 各子批的 E1a 一律按本檔的映射表、裁決、子批範圍執行;
> 契約/映射變更走 §12 append-only,不得原地改寫。
> **上游正本**:`../GUI-DESIGN-WORKING-DOC.md`(§0 裁決 / §1 鎖定 / §3 canon 1-11 / §9 phase)、
> `../tokens.css`(token 唯一正本)、`../../static/tokens-compat.css`(過渡映射,**P0.4 目標=整檔刪**)、
> `05_utilities.md`(utility 詞彙,§5.3/§5.5 半徑與 hex 收斂規則)、`06_numerics.md`(數值契約,§6 邊界)。
> **撰寫**:PA,2026-07-11。所有裁決附 static/ HEAD `01dcc43cf` 當日 grep 實測;PM 快照數字與本檔實測
> 差異見 §0.3,以本檔實測為準。

---

## 0 · 範圍、度量與 PM 快照對賬

### 0.1 P0.4 擁有 / 不擁有

| P0.4 擁有(本檔) | 不擁有(邊界) |
|---|---|
| tokens-compat.css 舊名 → tokens.css 語義名遷移 + **整檔刪除** | 單文檔殼 / view-router / 共享 WS(P1) |
| 裸 hex → 語義 token(palette 內)+ palette 外色逐色裁決 | 共用組件凍結 panel/KPI/table/chip(**P1.4**;fork bulk-rename 併入,見 §4) |
| 全站 border-radius 收斂 5/8/12 | IBKR lane 語義 chips + 治理 banner(**P0.5**,見 §9) |
| 死代碼 / 懸空 var / 混合哨兵 / 越界文字常量 / enum-painting 收尾 | CI grep 禁 `style=`/`<style`/新 hex(**P0.6**;本檔 §10 只預埋 guard 接口) |
| POST payload 量級猜測 ×2 的**歸屬裁決**(執行需後端契約,見 §8) | 死面 FLAG-DEAD 19 面裁決(**P3.2**) |

### 0.2 操作性度量(2026-07-11 static/ HEAD `01dcc43cf`)

工作目錄根:`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`

- **tokens-compat 舊名消費 = 688**(16 舊名,精確 `var\(--x[,)]` 邊界,已排除 tokens-compat.css 定義本身)。
- **裸 hex**:html+js = **265**;shell `styles.css` = **119**;三正本檔(tokens.css 42 / tokens-compat.css 0 /
  oc-utilities.css 0)= 合法值源不計。**待收斂總量 ≈ 384**(html+js+styles.css)。
- **border-radius literal**:off-scale(非 5/8/12,非 999/50%/0/2-seal)≈ **102**;on-scale 但寫字面
  (8px/12px/5px 未 token 化)≈ **69**;合計 **≈ 171** 個 literal 需觸碰;已 token 化 `var(--r-*)` = 53。
- **fork class** 選擇器定義:`se-` 20 / `rc-` 24 / `gov-` 67 / `live-` 30 = **141 distinct**;raw 出現次數
  `se-`441 / `live-`370 / `gov-`255 / `rc-`72 = **≈ 1138**。**全部 tab-local**(定義在各 tab 頁內 `<style>`
  或該 tab 專屬 JS;styles.css 0 個 fork 選擇器);唯一跨 tab 共用 = common.js `.live-metric*` 家族 11 條。
- **死代碼**:tab-demo.html `_ocMetricPct/_ocMetricRatio/_ocMetricBps`(3,**0 caller 確認**);
  `_OC_CAT_CONFIG` color/bg **欄位**死(common-formatters.js:427,`.label` 仍在用);
  `_formatSignedMoneyValue` **已於 B6/E 刪除,0 殘留**;`ocPnlClass` **非死碼**(7 caller,見 §5)。

### 0.3 PM 快照 vs 實測對賬(裁決前必讀)

| 項目 | PM 快照 | 本檔實測 | 差異解讀 |
|---|---|---|---|
| tokens-compat 舊名 | ~753 | **688** | PM 高估 ~65;疑似 `var(--x` 前綴誤中新名(`var(--bg)` 命中 `var(--bg-app)`)。本檔用 `[,)]` 邊界精確計。 |
| 裸 hex | ~367 | **265**(html/js)+119(styles.css shell)=**384** | PM ~367 ≈ html+js+styles.css 量級;數量級一致。 |
| off-scale 半徑 | ~118 | **102** off-scale + **69** on-scale-literal = **171** 觸碰點 | PM 僅計真 off-scale;實際需連 8/12px 字面一起 token 化。 |
| fork class(4 前綴) | ~449 | **141 distinct / ≈1138 raw** | **重大低估**。~449 ≈ `se-` 單前綴 raw(441)。全部 tab-local ⇒ canon 4「併 oc-*」在 Phase 0 幾乎不適用(見 §4)。 |
| dead helper | 5 | **3 真死**(_ocMetric×3)+ 1 死數據(_OC_CAT_CONFIG 欄位) | `_formatSignedMoneyValue` 已刪;`ocPnlClass` 是**活碼待遷移非刪除**。PM 清單需修正(§5)。 |

**三個影響架構的意外**(詳 §4 / §1.4 / §5):
1. **fork 全 tab-local**:Phase 0(iframe-per-tab)無跨 tab dedup 空間,bulk-rename=純 churn + 高 JS 引用風險;
   canon 4 的 fork-delete 應併入 P1.4 共用組件凍結。P0.4 只做清單 + 唯一共用家族(common.js `.live-metric*`)。
2. **tokens-compat 遷移 computed-value-identical**:別名解析到同一 token 值(`--text-dim:var(--text-secondary)`),
   故 `var(--text-dim)`→`var(--text-secondary)` 在**兩主題都同值**,遷移可證明零視覺變更 ⇒ 驗證極廉、安全(§1)。
3. **裸 hex 是主題正確性 bug 非純美學**:硬編 GitHub-primer 深色(#21262d 等)在帛晝(light)破版;
   hex→token 是**修主題破版**,在 light 主題**有可見變化**(desirable),須雙主題目視 + A3(§2)。

---

## 1 · tokens-compat.css 退場路徑(P0.4 核心;問題 1)

### 1.1 核心不變量:遷移是 computed-value-identical

tokens-compat.css 每條都是 `舊名: var(新語義名)` 純別名,不含任何 hex(§0.2 實測 0 hex)。因此把消費點的
`var(--舊名)` 直接換成 `var(--新語義名)`,在**玄夜與帛晝兩主題下解析出的計算值完全相同**——只是移除一層
別名 indirection。這是本子批可證明安全的根據(同 P0.2 byte-exact 別名 swap 先例),使遷移**驗證成本 = grep +
resolved-value 論證**,不需逐點目視。

### 1.2 遷移映射表(舊 → canonical;與 tokens-compat.css §1 逐條一致)

| 舊名 | tokens-compat 現映射 | canonical 目標 | 精確消費點 | 類別 |
|---|---|---|---|---|
| `--bg` | `var(--bg-app)` | `--bg-app` | 58 | 機械 |
| `--card-bg` | `var(--bg-surface)` | `--bg-surface` | 31 | 機械 |
| `--card` | `var(--bg-surface)` | `--bg-surface` | 4 | 機械 |
| `--border` | `var(--border-subtle)` | `--border-subtle` | 118 | 機械 |
| `--text` | `var(--text-primary)` | `--text-primary` | 90 | 機械 |
| `--text-dim` | `var(--text-secondary)` | `--text-secondary` | 163 | 機械 |
| `--dim` | `var(--text-secondary)` | `--text-secondary` | 4 | 機械 |
| `--muted` | `var(--text-muted)` | `--text-muted` | 32 | 機械 |
| `--neutral` | `var(--text-muted)` | `--text-muted` | 3 | 機械 |
| `--green` | `var(--pos)` | `--pos` | 46 | 機械 |
| `--good` | `var(--pos)` | `--pos` | 4 | 機械 |
| `--red` | `var(--neg)` | `--neg` | 61 | 機械 + **canon 6 子集 E2**(見 1.3) |
| `--bad` | `var(--neg)` | `--neg` | 1 | 機械 |
| `--yellow` | `var(--warn)` | `--warn` | 27 | 機械 |
| `--blue` | `var(--text-secondary)` | `--text-secondary` | 32 | 機械(**identical**)+ **A3 選配**(見 1.3) |
| `--card-radius` | `var(--r-2)` | `--r-2` | 14 | 機械 |
| **合計** | | | **688** | |

### 1.3 有語義爭議的兩個舊名(分開處理,**不阻塞刪檔**)

**① `--blue`(32 點)——canon 1 中性化早已在 compat 層發生。**
- 現況 `--blue: var(--text-secondary)`,故所有 `var(--blue)` **當前已解析為中性 text-secondary**。
  機械遷移 `var(--blue)`→`var(--text-secondary)` **兩主題同值,零視覺變更**,直接進 C3/C4。
- **選配增益(A3-gated,獨立於刪檔)**:少數消費點語義是「連結/CTA/選中態」(如 tab-learning.html:43 底線連結、
  common-formatters.js:330/636 active-state、governance:199 `var(--blue,#58a6ff)` 帶字面 fallback),
  canon 10 允許 `--accent` 給「連結性 CTA / 焦點 / 選中」。把這些點**升級**為 `var(--accent)` 是**值變更**
  (青銅化),須 A3 目視。**裁決**:機械遷移一律先 →text-secondary(identical);accent 升級是**獨立可選 A3 項**,
  逐點列清單(≤6 點),**不得阻塞 tokens-compat 刪除**。

**② `--red`(61 點)——canon 6 real-money marker 子集。**
- compat 映射 `--red: var(--neg)`,故當前所有 `var(--red)` 已解析為 `--neg`(**非**神聖 `--live` 熱紅)。
  機械遷移 `var(--red)`→`var(--neg)` 兩主題同值,零視覺變更。
- **但**存在語義應為 live-marker 的點(risk-tab.js:226 `live: {text:'var(--red)'}` 的「live 模式」徽章文字、
  tab-live.js:90/99/138 auth 過期色),canon 6 的正解可能是 `--live`(真金熱紅永不稀釋)。
- **裁決**:C4(交易關鍵)先做**機械 `--red`→`--neg`(identical)**;**canon 6 正確性升級**(特定 live/real-money
  marker →`--live`)是**獨立值變更**,由 **E2 硬邊界親算**逐點分類(loss/alert→`--neg` vs live-mode/real-money
  marker→`--live`),可與 C4 同批但須 E2 明列 truth-table。**不得阻塞刪檔**(升不升 --live,消費點都已 = 0 舊名)。

> 注意:REAL FUNDS banner 熱紅是硬編 `rgba(239,68,68)`(P0.3 B6/E 已驗 byte-identical 保全),**不經 --red/--live
> token**,C4 不觸碰;canon 6 硬邊界維持。

### 1.4 刪除 tokens-compat.css 的前置條件(C5 gate)

**全部滿足才可刪**:
1. **全站 old-name grep = 0**:`grep -rE 'var\(--(bg|card-bg|card|border|text|text-dim|dim|muted|neutral|green|good|red|bad|yellow|blue|card-radius)[,)]'`
   在 html+js+styles.css(含 common*.js 注入 CSS 字串)命中 = 0。**含殼層/legacy 檔**(見下 legacy 裁決)。
2. 22 檔 `<link href="/static/tokens-compat.css">` 全移除(固定三連降為二連 tokens.css → oc-utilities.css)。
3. `--blue`/`--red` 語義子集裁決已執行或明文 defer(不阻塞,但清單留檔)。
4. **cache-bust**:同批對 tokens.css / oc-utilities.css `<link>` 補 `?v=`(P0.6 衛生預付);common.js/
   common-formatters.js 若在本批被改則 bump `?v=`(防 stale HTML 引已刪 compat)。
5. **CI guard 上線**:per-file ratchet 加「16 舊名 = 0」軸(§10),防回潮。

**legacy 殼層裁決(阻塞刪檔的隱藏耦合)**:老名消費有 96 點在 **common.js**(注入 CSS,殼層共用)、
46 點在 **trading.html**、37 點在 **console.html**、index.html/`_dashboard_card.html`/app-learning.js 亦有。
- `console.html` = **當前殼**(TABS array),必遷。
- `trading.html`/`index.html`/`_dashboard_card.html` = **legacy 殼**(Phase 3 刪除目標),`app-learning.js` = 孤兒
  (僅 index.html 載,Phase 2 復活/退役未決,見 §5)。
- **裁決**:P0.4 要「整檔刪 compat」就必須讓**所有現存消費點 = 0**,含 legacy。因遷移 computed-identical(legacy
  檔仍能正常渲染),**C3 一併遷 legacy 殼層老名**(機械、安全、解除刪檔阻塞)。這是「觸碰 Phase-3-doomed 檔」的
  可接受 churn(機械 + 零視覺 + 解鎖核心交付)。**替代方案(operator 若不願動 legacy)**:C5 刪檔 defer 到 Phase 3,
  P0.4 只遷 served 面——但這讓 compat indirection 多留數月。**PA 建議 C3 含 legacy、C5 立刻刪**;若 OPS 確認
  index/trading **未被服務(dead)**,則排除它們並 C5 defer(二選一,E1a 開批前向 OPS 取 served-status)。

### 1.5 一次 sed vs 分批(問題 1①)

**裁決:不做一次全站 sed;分「file-risk-tier × 機械性」子批。**
- 純機械 1:1(14 個無爭議舊名,~595 點)可用**確定性腳本替換**(逐舊名 `sed`),但**按檔案風險層拆批**
  (非交易 + 殼層 JS = C3;交易關鍵 = C4)以分離 review 粒度與 rollback 單位。
- `--blue`/`--red` 爭議子集**不進機械 sed**(§1.3):blue 機械部分同 →text-secondary,accent 升級手動;
  red 機械 →neg,canon6 升級 E2 手動。
- 理由:交易關鍵檔(tab-governance/tab-risk/risk-tab.js/tab-live*/tab-demo/governance-tab.js)須 E2 硬邊界親算,
  不可與非交易檔同一 blind sed;殼層 common.js(96 點,注入 CSS)blast 面大須獨立核。

---

## 2 · 裸 hex → token(問題 2)

### 2.1 分類原則

hex 分三類:(A) **palette 內**(對得上 tokens.css 語義)→ token 化;(B) **palette 外**(五色系外)→ 逐色裁決;
(C) **功能性非調色**(scrim/透明疊層)→ 保留或單獨 token。**canon 8**:模板/JS 內禁裸 hex;**canon 9/10**:
不新增第四紅、accent 只青銅 ⇒ **禁新增彩色 token**。

**主題正確性注記**:硬編的 GitHub-primer 深色(#21262d/#161b22/#8b949e/#f85149…)是**玄夜單主題值**,在帛晝
(light)破版。hex→token 把它們換成主題自適應 token,**在 light 主題有可見(且正確)變化** ⇒ hex 批屬**設計敏感**,
須雙主題目視 + A3(不同於 §1 compat 的兩主題 identical)。

### 2.2 palette 內 hex → token 對照(承 05_utilities §5.5,擴充)

| inline hex/rgba(頻次) | token | 語義 |
|---|---|---|
| `#21262d`(39)/`#30363d`(21)/`#1c2128`(3) | `--border-subtle`(強界 `--border-strong`) | 髮絲線(逐點判 subtle/strong) |
| `#161b22`(9)/`#0d1117`(2)/`#1a1a1a`(2) | `--bg-surface`/`--bg-raised`/`--bg-sunken` | 深色地面(逐點判海拔) |
| `#8b949e`(12)/`#6e7681`(6)/`#94a3b8`(7)/`#6b7280`(2)/`#95a5a6`(1)/`#999`(2)/`#888`(1) | `--text-secondary`/`--text-muted` | 次要/最暗文字 |
| `#c9d1d9`(3)/`#f0f6fc`(2)/`#fff`(6) | `--text-primary` | 主文字(#fff 逐點判是否真純白) |
| `#f85149`(14)/`#da3633`(3)/`#e74c3c`(2)/`#f78166`(2)/`#ff7b72`(2)/`#ffa198`(2)/`#8b1a1a`(1) | `--neg`(canon6 real-money marker 子集 →`--live`,E2) | 紅族 |
| `#f87171`(13) | `--neg` | 虧損紅 |
| `#3fb950`(11)/`#2ea043`(6)/`#27ae60`(3) | `--pos` | 綠族 |
| `#d29922`(10)/`#eab308`(4)/`#f59e0b`(5)/`#f39c12`(3)/`#f97316`(3)/`#fbbf24`(2)/`#f0c040`(1)/`#d2691e`(1) | `--warn`(`--warn-bg`) | 琥珀/橙 warn(canon 10 必附 ⚠) |
| `#58a6ff`(6)/`#3b82f6`(3)/`#60a5fa`(2)/`#3498db`(2)/`#93c5fd`(1) | 中性資訊→`--text-secondary`;連結/CTA/選中→`--accent`(A3 逐點) | 藍(承 --blue 中性化) |

> **`--warn` 有家、不是 palette 外**:琥珀屬五色系(tokens.css `--warn`),故所有黃/橙/琥珀 hex 皆 token 化,
> **非** verbatim。唯一真 palette 外問題是紫(§2.3)。

### 2.3 palette 外色逐色裁決(問題 2②;canon 9/10 約束)

| 色 | 頻次/位置 | 語義 | **裁決** |
|---|---|---|---|
| **紫 `#a855f7`/`#c084fc`/`#9b59b6`** | 17+2+2;tab-live(`.live-btn-purple`/`.live-t-purple`)、tab-governance(`.gov-purple-*` + autonomy L3 map `3:{fg:#a855f7}`)、tab-system(`.purple`)、console/common/tab-live.js/app-learning | **T3 authority / Live-Auth 識別色** | **中性化,不新增 --purple token**(canon 9/10)。authority 是 chrome 級身分區隔非 risk/PnL 數據 claim ⇒ 用**朱印形制 `.seal-mark`(canon 9,sealed/authority 態)+ 文字 label(T3/AUTHORITY)+ 中性 chrome** 承載,**去掉紫色相**。text-purple → `--text-secondary`/`--text-primary`;btn-purple 邊框/底 → 中性 `--border-strong`/`--bg-raised` 或(若確為授權態)`--seal`/`--seal-bg` 方印。**此為可見美學變更 ⇒ A3-gated**(同 ocCategoryTag 四色中性化先例,operator 若要保 authority 色須新 token 裁決)。 |
| **深紅漸層 `#3d0d0d`/`#5c1a1a`/`#8b1a1a`** | 2+2+1;risk-tab.js、tab-agents.html | danger-zone 漸層底 | **塌平漸層**(canon 5 近黑上漸層/陰影「punch holes」;canon 1 禁裝飾)→ 扁平 `--neg-bg`/`--live-bg`/`--bg-sunken`(逐點判 danger 強度)。risk-tab.js 屬交易關鍵 ⇒ **E2**。 |
| **藍 tint 底 `#1a2f5c`/`#0d1f3d`** | 3+2;tab-agents.html | info tint 底 | **中性化** → `--bg-raised` 或 `--accent-weak`(canon 1)。非交易。 |
| **scrim `rgba(0,0,0,α)`** | 24;α∈{0.2,0.4,0.5,0.6,0.7} modal/overlay 背幕 | 功能性疊層 | **保留 verbatim**(疊層機制,主題不變黑幕正確,非 palette 色)+ 永久註記;**順手收斂 5 個 α 到 ≤2 檔**(0.5 標準幕 / 0.6 強幕),消 α 濫用。**不新增 token**(選配:未來 `--scrim` 單 token,低優)。 |
| 邊角 `#9888`/`#9940`/`#feed`/`#feed`... | 各 1;疑 4-digit rgba 短碼或誤值 | 待驗 | E1a **逐點驗**真實用途(可能是 `#RRGGBBAA` 短碼或筆誤),對得上語義→token,對不上→報告列 defer。 |

### 2.4 hex→token vs 保留 對照(總表)

- **token 化(絕大多數,~360)**:§2.2 全表 + §2.3 紫/深紅/藍 tint。
- **保留 verbatim(帶永久註記)**:§2.3 scrim `rgba(0,0,0,α)`(功能疊層);tokens.css 42 hex(palette 正本源);
  P0.3 B6/E 已保全的 REAL FUNDS `rgba(239,68,68)` 熱紅(canon 6,C4/hex 批**不觸碰**)。
- **styles.css shell 119 hex**:是殼層 CSS(index/login/console/trading/_dashboard 共用),同 §2.2 表 token 化,
  但 blast 面 = 殼層,**須雙主題目視 + 確認 served 面**;legacy-only 選擇器可 defer(見 §1.4 legacy 裁決)。

---

## 3 · 半徑收斂(問題 3)

### 3.1 映射表(承 05_utilities §5.3,補全非標值)

| literal | → | token | 註 |
|---|---|---|---|
| 2px | | `--r-seal`(2) | 朱印方印專用,**保留**(非收斂對象) |
| 3px / 4px / 5px / 6px | → | `--r-1`(5) | 6→5、4→5、3→5;5px 字面亦 token 化 |
| 7px / 8px / 9px / 10px | → | `--r-2`(8) | 7→8、9→8、10→8;8px 字面亦 token 化 |
| 12px / 14px / 18px | → | `--r-3`(12) | 14→12、18→12;12px 字面亦 token 化 |
| 999px / `50%` | | `--r-full`(9999)/ `50%` | **狀態點/toggle/圓 avatar 專用**,canon 5 允許,**保留** |
| 0 | | 0 | 無圓角,**保留** |

### 3.2 整組轉鐵則(承 B4 LOW-1)

**半徑轉換 = 檔案級原子**:一個檔案內**所有** border-radius literal 在同一 commit 全轉,避免單點轉造成
鄰居 5/6 錯位(如 sparkline 6→5 但同組 feed-price 仍 6)。映射確定性(§3.1),E1a 不得自由裁量。
交易關鍵頁(tab-live/tab-demo/tab-governance/tab-risk + risk-tab.js/governance-tab.js)的半徑轉換 **E2 硬邊界親算**
(半徑純視覺不碰硬邊界,但交易頁一律 E2 過目 + 雙主題)。

---

## 4 · style fork class 合併(問題 4)

### 4.1 現況判定(推翻 PM「~449 可歸 oc-*」預設)

實測 141 distinct fork 選擇器 / ~1138 raw,**全部 tab-local**:定義在各 tab 頁內 `<style>`(tab-live.html /
tab-governance.html / tab-risk.html / tab-stock-etf.html)或該 tab 專屬 JS(risk-tab.js / governance-tab.js /
canary-tab.js)。styles.css(殼層共用)**0 個 fork 選擇器**。唯一跨 tab 共用 = **common.js `.live-metric*` 家族
11 條**(`.live-metrics/.live-metric/.live-metric-label/.live-metric-val/.live-metric-sub`,經 ocInjectBaseCSS
注入,demo/live/paper 可能共用)。

### 4.2 裁決:P0.4 **不做 bulk fork rename**;併入 P1.4 共用組件凍結

**deletion test**:把「fork bulk-rename」從 P0.4 移除,是否丟失目標?**否**——
1. **無跨 tab dedup 空間**:Phase 0 仍 iframe-per-tab,每 tab 是獨立文檔,`.live-card` 與 `.gov-card` 不共享
   渲染上下文;把 tab-local `.live-*` 改名 `.oc-*` 在單 tab 內是**純 churn**,無共用收益。
2. **高 JS 引用風險**:fork class 大量被 `classList`/`querySelector('.live-…')`/`className='…'` 引用(§越界
   enum-painting);改名須同步全部 JS 引用,blast 面 = 整 tab 的 JS,風險/收益極不對稱。
3. **canon 4 的真義是 P1.4**:working doc §9 step 4「delete forks + freeze section-header/card/metric/chip」把
   fork-delete 與**組件凍結**綁在一起,而組件凍結 = PROGRESS **P1.4**,且跨 tab 共用只在**單文檔殼(P1.1)**後成立。
   ⇒ **DRIFT 標記**:working doc §9 把 fork-delete 掛 Phase 0,與 PROGRESS P1.4 相衝;**PA 裁決以 P1.4 為準**
   (fork bulk-rename 在共用組件凍結時做,最廉最安全),並建議 PM 更新 working doc §9 註記。

**P0.4 的 fork 工作 = 只做兩件低風險項(§4.3),其餘 DEFER P1.4。**

### 4.3 P0.4 fork 範圍(C7,最小)

1. **共用家族收斂(選配,低風險)**:common.js `.live-metric*`(11,真跨 tab 共用)→ `.oc-metric-*` 語義中性名。
   須:同批改全部 JS `classList`/模板引用 + 元素級原子(05_utilities 鐵則一)+ node --check + demo/live/paper 三面
   目視。**若 E1a 判引用面過廣,可整體 DEFER P1.4**(不強制)。
2. **fork→未來 oc-* 對照清單(inventory,零代碼變更)**:產出 `se-/rc-/gov-/live-` → 未來共用組件(panel/card/
   metric/chip/section-header/table/badge)的對照表,**入本檔 §4.4 附錄或批次報告**,供 P1.4 凍結時直接消費。
   前綴一致性只**記錄**(哪些該歸哪個 oc-* 組件),P0.4 **不改名**。
3. **enum-painting 收尾**:JS `el.style.color/background = 'var(--x)'` 的 enum 上色(12 處,如 tab-live.js:90/99
   `style.color='var(--red)'`、mode/status 色)→ class-per-enum(`.mode-*`/`.is-*`,05_utilities §7.3),與所屬 tab
   的 token/hex 批**元素級原子同批**做;交易關鍵 E2。

### 4.4 stock-etf(`se-`)特別協調

`se-` 441 raw 屬 IBKR lane,與 **P0.5**(IBKR 語義 chips DENIED/PRESENT/MISSING/OK + 治理 banner)重疊。
**裁決**:`se-` fork 不在 C7 動;其語義 chip 化交 **P0.5**;fork rename 交 Phase 2 stock-etf 遷移。P0.4 只 inventory。

---

## 5 · 死代碼處置(問題 5;修正 PM 清單)

| 標的 | 實測 | **裁決** |
|---|---|---|
| `_ocMetricPct`/`_ocMetricRatio`/`_ocMetricBps` | tab-demo.html:1219/1224/1229,**0 caller 確認** | **刪除**(3 函數)。tab-demo 交易關鍵 ⇒ E2 親算 0-caller + 硬邊界 IDENTICAL(純刪死碼不碰 onclick/gate)。 |
| `_formatSignedMoneyValue` | **grep 0 殘留**(B6/E 已刪) | **NO-OP**(已完成);若有註釋提及則順手清。 |
| `ocPnlClass` | **7 caller 活碼**(tab-learning:354/364、tab-system:1004、common-formatters:558/559、agent-tracker:676/699);回舊 green/red class | **非刪除,是遷移**:輸出 `green/red` → `val-pos/val-neg`(canon,承 P0.3 第二通道)。屬 §1 色 class 遷移範疇,由所屬檔批次做;common-formatters:558/559 在表格 helper 內,交易鄰接須核。**PM 清單「ocPnlClass 刪除候選」修正為「遷移候選」。** |
| `_OC_CAT_CONFIG` color/bg 欄位 | common-formatters.js:427,`.label` 仍用(:435),color/bg 死(ocCategoryTag 已中性化) | **刪 color/bg 欄位**,保 label;同步 :435 fallback 物件的 color/bg。純數據清理,非交易。 |
| `ocPnlClass`/paper-positive **註釋殘留** | tab-learning:352、tab-demo:580 註釋提及舊名 | 觸碰該檔時順手更新註釋(指向 val-*);非獨立批。 |
| **`app-learning.js` 孤兒** | 僅 index.html:285 載;16 hex + 2 legit scoped-var(P0.2 defer) | **P0.4 不動**。Phase 2 復活/退役未決(PROGRESS Phase2 row 6);其 hex/fork/token 全 **DEFER Phase 2**。理由:touching 一個 revive/retire 未決的孤兒 = 賭注;deletion test 過(不動不丟目標)。 |

---

## 6 · 懸空 var / 混合哨兵 / 越界常量(問題 7)

| 項 | 位置 | **裁決** |
|---|---|---|
| 懸空 `--bg-card` | tab-risk.html:67(`.rc-dlg-detail`) | 無定義(**非** tokens-compat,tokens-compat 只有 `--card-bg`/`--card`)⇒ 解析失敗。→ `var(--bg-surface)`。**tab-risk 交易關鍵 ⇒ 併 C4/E2**。 |
| 懸空 `--bg-elevated` | tab-phase4.html:51/76(`var(--bg-elevated,#161b22)`) | 無定義,fallback 硬編深色 #161b22(破帛晝)。→ `var(--bg-raised)`,**刪 hex fallback**。tab-phase4 非交易 ⇒ C1。 |
| 混合哨兵 `'--'` vs `OC_EMPTY('—')` | 279 處 `'--'` 字面 / 55 處 OC_EMPTY | P0.3 已把顯示層假零 → OC_EMPTY;**殘留**:ocFormatPerformanceMetric 內部 3 blank guard 仍回 `'--'`、governance `_formatValue ''→'--'`(intended)、ocDate/ocTime `'--'`(契約外)。→ **統一內部 blank guard → OC_EMPTY**(common-formatters.js,非交易顯示語義),ocDate/ocTime 契約外保留 `'--'`(附註記)。**多數 279 是 input-guard 比對**(`=== '--'`,ocIsBlank 已相容),非顯示,不強改。 |
| 越界文字常量 | common-modals.js oc-tc-meta whiteSpace 常量、btn.style enum(12 處) | whiteSpace 常量 → `.pre-line`/`.nowrap` utility(已在 §A);enum-painting → §4.3.3 class-per-enum。所屬檔批次順手。 |

---

## 7 · (併入 §6,無獨立問題 7 內容)

---

## 8 · POST payload 量級猜測 ×2(問題 6)

| 點 | 現況 | 性質 | **裁決** |
|---|---|---|---|
| governance-tab.js:822 | `(Math.abs(winRate)<=1 ? winRate*100 : winRate)` 送 POST body | **送出格式**(非顯示);06_numerics §1.1 禁此啟發式(真 0.5% 可能是 0.005 或 0.5) | **剝離出 P0.4 機械批**。需**後端契約確認**:該 endpoint 期望 fraction 或 percent?→ 定型後移除猜測,呼叫端顯式送對格式。**P0.4 不 blind 改**(改錯 = 送錯風控/治理值)。 |
| risk-tab.js:836 | `rRisk.p1_risk_pct<1 ? *100 : ...` snapshot fallback | **雙來源慣例衝突**:fresh `gc.p1_risk_pct`(route 已轉 percent)vs stale snapshot `rRisk.p1_risk_pct`(fraction)。是**顯示 fallback** 非 POST(POST 在 :420 送 percent) | 根因 = 兩數據源型別不一致,非純顯示。需 **route/後端契約**確認 snapshot 欄位型別後,顯式轉換取代猜測。同上剝離。 |

**裁決:兩點合成獨立子批 C8,前置 = 後端/route 契約確認,派 E1(source)+ 需要時 BB/後端 pair;可能不在 P0.4
主線完成**(依契約取得時機)。C8 **不阻塞** C1-C7(它們是純前端收斂,C8 是前後端語義)。若契約短期不可得,C8
以 GitHub Issue 掛起 + review date(TODO passive-wait 規則),P0.4 主線照收斂其餘。

---

## 9 · 與 P0.5 / P0.6 邊界

- **P0.5(IBKR lane)**:語義 chips(DENIED/PRESENT/MISSING/OK)+ 治理 banner。P0.4 的 `se-` fork **只 inventory**
  (§4.4),chip 語義化 = P0.5;fake-$0 修復已 shipped(P0.5 核對即可)。stock-etf 11 JS 模組建於 G0.5 guard 期,
  hex/style 面已淨,P0.4 不動。
- **P0.6(CI guard)**:本檔 §10 只**預埋 guard 接口**。P0.6 正式上線三軸禁令:`style="`(白名單 §7 custom-prop
  形式)/ `<style`(白名單殼層過渡)/ 新增裸 hex / **新增 16 舊名**(C5 後)。cache-bust CI-guard(shared static
  改動 → bump `?v=`)= P0.6,C5 先付首期(§1.4)。

---

## 10 · 驗證 / CI guard 接口

### 10.1 每子批 Definition of Done

某子批完成 ⇔ 該批檔案:
1. **本批類別 grep = 0**:C1 死碼 0-caller 已刪 / C2 該檔非標半徑 = 0(只剩 var(--r-*)/999/50%/0/2)/
   C3-C4 該檔 16 舊名 = 0 / C6 該檔 palette 內裸 hex = 0(palette 外依裁決)。
2. `node --check` 全部被改 JS(含 .html 內嵌 script 抽驗)全綠。
3. **兩主題目視**:玄夜 + 帛晝各過一遍(hex 批尤其,主題正確性)。
4. 交易關鍵批:**E2 硬邊界親算**(onclick/endpoint/typed-confirm/五閘/emergency count IDENTICAL;canon 6 熱紅
   byte-identical;canon 9 朱印不誤轉)+ truth-table。
5. JS 切換元素兩態實測(enum-painting 轉 class 後);死碼刪除後功能面無回歸。

### 10.2 CI ratchet(承 05_utilities §10 / 06_numerics §5.3)

- 續用 per-file ratchet 白名單,新增軸:`raw-hex`(html/js/styles.css,排除三正本檔 + §2.3 verbatim 白名單)、
  `border-radius-offscale`、`old-token-name`(16 名)。某批完成即把該批檔對應軸基線降 0,**永不回升**。
- C5 後 `old-token-name` 全站 = 0 併入 P0.6 硬 guard;`raw-hex` 併入 canon 8 軸。

### 10.3 guard 測試

- tokens-compat 刪除前加 guard:斷言 `tokens-compat.css` 不存在時全站無 dangling old-name(靜態掃)。
- `:root` 唯一性 guard(P0.1 既有,+2)續綠;**注記**:styles.css 現存 1 個 `:root`(§0 實測)——E1a **C3 開批前驗**
  其是否含 token 定義(P0.1 應已刪 styles.css token :root):若僅 `color-scheme`/base 非 token = 良性;若含 token
  = P0.1 逃逸 DRIFT,補刪 + 記錄。

---

## 11 · 子批次計劃(問題 8)

編號 `P0.4-C*`(免與 P0.2 batch 1-9 / P0.3 B0-E 混淆)。每批 = 檔案盡量互不重疊的獨立 commit(rollback 單位)。
排序:低風險機械(死碼/懸空/半徑)先 → tokens-compat 遷移中段(大但機械 identical)→ 刪 compat →
hex + palette 外裁決(設計敏感 A3)後段 → fork 只做最小 → POST payload 剝離最後/掛起。

| 批 | 範圍 | 內容 | checkpoint | 風險 | gate |
|---|---|---|---|---|---|
| **C1** 死碼+懸空+哨兵(非交易) | common-formatters.js、tab-phase4.html、非交易顯示 | 刪 _OC_CAT_CONFIG color/bg 欄位;`--bg-elevated`→`--bg-raised`(刪 hex fallback);內部 blank guard→OC_EMPTY;whiteSpace 常量→utility | node --check;grep 死欄=0;懸空 var 解析;視覺 identical | **低** | E1a→E2 |
| **C1b** 死碼(交易) | tab-demo.html、tab-risk.html | 刪 tab-demo `_ocMetric×3`(0-caller);tab-risk 懸空 `--bg-card`→`--bg-surface` | 同上 + 硬邊界 IDENTICAL(純刪死碼/單 var) | 低(交易檔) | E1a→**E2 親算** |
| **C2** 半徑收斂 | 全站(非交易先,交易後或同批標記) | border-radius literal → var(--r-*)(§3.1);**檔案級整組轉**;999/50%/0/2 保留 | 該檔非標半徑=0;雙主題;交易頁 E2 | 低(純視覺) | E1a→E2(交易 E2 親算) |
| **C3** tokens-compat 機械 A | 非交易 tab + 殼層(console.html + common.js 注入 CSS + common-modals/formatters + trading/index/legacy 殼 + login) | 14 無爭議舊名 → canonical(computed-identical);`--blue`→text-secondary(identical) | 該批檔 16 舊名=0;resolved-value 論證;雙主題 identical | 中(量大但 identical;殼層 blast) | E1a→E2 |
| **C4** tokens-compat 機械 B(交易) | tab-governance/tab-risk/risk-tab.js/governance-tab.js/tab-live.html/tab-live.js/tab-demo.html | 同 C3 機械遷移 + **`--red` 分類 E2 親算**(neg vs canon6 live→--live);`--bg-card` 若未在 C1b 則此處 | 16 舊名=0;**E2 truth-table**(--red 逐點;硬邊界 IDENTICAL;canon6 熱紅不碰) | **高(交易 + canon6)** | E1a→**E2 硬邊界親算** |
| **C5** 刪 tokens-compat.css | 22 檔 `<link>` + tokens-compat.css | 前置 §1.4 全滿足;移 22 link;刪檔;tokens/oc-utilities `<link>` 補 `?v=`;CI guard old-name=0 上線 | 全站 old-name grep=0;22 檔載入正常;guard 綠;雙主題 | 中(刪檔;stale-cache) | E1a→E2→E4 回歸 |
| **C6a** hex→token(palette 內) | 非交易先,交易(tab-live/demo/governance/risk)E2;styles.css shell | §2.2 表 token 化;**主題正確性**(硬編深色→自適應) | 該檔 palette 內裸 hex=0;**雙主題目視 A3**;交易 E2 | 中-高(設計敏感 + 交易) | E1a→E2→**A3 雙主題** |
| **C6b** palette 外色裁決 | 紫(tab-live/governance/system…)、深紅漸層(risk-tab.js/tab-agents)、藍 tint、scrim | 紫**中性化**(seal-form+label,§2.3);漸層塌平;scrim α 收斂 verbatim | 紫色相=0;**A3 + operator 知悉**(可見美學變更,同 ocCategoryTag 先例);交易(risk-tab)E2 | **高(美學決策)** | E1a→E2→**A3/operator** |
| **C7** fork 最小 | common.js `.live-metric*`(選配)+ inventory + enum-painting | `.live-metric*`→`.oc-metric-*`(選配,引用面廣可 DEFER P1.4);fork→oc-* 對照清單;enum→class | node --check;三面目視;inventory 入報告 | 中(JS 引用;多數 DEFER) | E1a→E2 |
| **C8** POST 量級猜測 ×2 | governance-tab.js:822、risk-tab.js:836 | **前置後端/route 契約**;定型後移除猜測 | 契約文件 + 送值正確性核 | 高(前後端語義) | **剝離**;E1+BB/後端;可掛 Issue defer |

**排序理由**:C1/C1b/C2 機械近零視覺先建信心;C3/C4 大但 computed-identical(驗證廉),C4 交易 canon6 壓在 C3 後;
C5 刪檔須 C3+C4 全清;C6a/C6b 設計敏感(主題正確性 + 美學)壓後段走 A3;C7 fork 只做最小(bulk DEFER P1.4);
C8 前後端語義剝離最後/掛起,不阻塞前端收斂。

---

## 12 · 契約治理 / Rollback

- 本檔映射表(§1.2)、hex→token 表(§2.2)、半徑表(§3.1)、子批表(§11)= **append-only**:新增映射/子批允許
  (檔尾追記 + 批次註記 + PA 認可);**改既有映射/刪除**一律禁,直到 P0.4 統一複審。
- 每子批獨立 commit;rollback 單位 = 批次 commit `git revert`。C5(刪 compat)撤銷須連同 C3/C4 一起撤(否則舊名
  無定義破版);**緊急止血序**:先 revert C5(復原 compat 檔 + link),C3/C4 的 canonical 名仍解析(tokens.css 有定義)
  ⇒ 前端不破,再擇機處理。
- C6b 紫中性化 / C6a 主題正確性是**值變更**,revert = 復原舊 hex/紫;無 runtime/schema/API 依賴,iframe 架構未觸碰。
- 視覺回滾錨點:git tag `gui-baseline-2026-07-09`。

---

*變更記錄:2026-07-11 PA 初版(P0.4 子批 C1 前定稿)。度量對賬見 §0.3;fork/dead-helper PM 清單修正見 §4.1/§5。
映射/子批變更走 §12 append-only。*
