# P1.3 雙主題(玄夜/帛晝)硬 gate — 設計正本

> 作者:PA-design-writer(R79 spec-first,read-only 調查)。狀態:**SPEC READY**。
> 供 E1a/E4 直接照做,零臆測。**本文只寫規格,不改任何 static 實作檔。**
> 上游:PROGRESS.md P1.3(line 151)+ A3 P0 驗收 H-1/H-2(line 58)+ LOOP-DRIVER §6 Phase 1 特則。
> 權威:`tokens.css`(調色正本)/ working doc §3 canon 6·9·10 / P0.6 ratchet 紀律。

---

## 0 · Gate 定義與本 spec 交付邊界

P1.3 = 主題/密度切換上線。**硬 gate(A3 驗收,三綠才解 22 文檔的 `data-theme="dark"` 釘死、才宣稱雙主題可用)**:

- **①** 泛用 **α-overlay token** 並遷移 H-2 冷調面板底(硬編碼 rgba)。→ §2 + §4
- **②** 帛晝 `--warn`/`--live`/`--muted`/`--seal` **AA retune**(objective 算術)。→ §3
- **③** token-pair AA 對比寫成 **P0.6 式靜態 ratchet 測試**(純算術 CI 化)。→ §5

**本 spec 交付(objective,自主可驗)**:token 設計、完整 inventory、對比算術、ratchet test 設計、實作拆輪、切分表。
**本 spec 不 attest(A3+Linux runtime,driver §6 V5-defer)**:帛晝真渲染可讀性走查、三態真值、解 data-theme 釘死。§7 明列切分。

---

## 1 · 範圍判定(先讀,決定 inventory 大小)

P1.3 帛晝實際生效的是 **原生殼表面(native shell surface)**,不是 legacy iframe 後備。經源碼核實:

| 表面 | 檔 | 帛晝生效? | 處置 |
|---|---|---|---|
| 新殼 chrome | shell.html/shell.css/shell.js | 是 | 已 born-clean(冷 rgba 零) |
| 原生 view 頁級 CSS | `view-*.css`(demo/governance/risk/paper/stock/settings 等) | **是** | **in-scope**;含 H-2 冷 rgba |
| 殼載共用 JS 注入 | common-modals.js / common-mode-badge.js / common-formatters.js / app-paper.js / handoff_helper.js | **是**(殼 `<script src>` 載入,執行期注入 `<style>`/inline) | **in-scope** |
| fetch-as-text 併入 IIFE 的 tab JS | risk-tab.js(view-risk 併入)/ governance-tab.js 等 | **是**(在殼 context 執行) | **in-scope**(risk-tab.js:224 inline style) |
| `common.js` `ocInjectBaseCSS()` | common.js:713 大 `<style>` 注入 | **否(dormant)** | **in-scope-但-gate-optional**;見下 |
| legacy `tab-*.html` 頁內 `<style>` | tab-demo/governance/live/… | **否(玄夜釘死 iframe)** | **out-of-scope**;見下 |
| legacy 殼 | console.html/trading.html/index.html/login.html | **否(Phase 3 刪除目標)** | **out-of-scope**(C6e defer,styles.css 冷 119 hex 隨 legacy 死,driver §6) |

**關鍵事實(源碼核實)**:
- `ocInjectBaseCSS()` 只由 legacy `tab-*.html` 的 `<script>ocAuthCheck(); ocInjectBaseCSS();</script>` 呼叫(22 檔);**殼刻意不呼**,原生 view render 時明確跳過該 bootstrap(`view-demo.js:232`/`view-risk.js:255`/… `if (txt.indexOf('ocInjectBaseCSS') !== -1) return;`)。故 common.js:750–959 的冷 rgba 在原生表面 **dormant**——已被逐字 port 進各 `view-*.css`(port 註「對 ocInjectBaseCSS 同名規則的**重複(非移動)**:legacy iframe 續靠 ocInjectBaseCSS」)。
- 早期唯讀 view(gates/monitor/development/learning/agents)是**原生重寫**,用 `shell-components.css` + `oc-utilities.css` class emit DOM,**零冷 rgba**、不呼 ocInjectBaseCSS → 不在 inventory。
- legacy `tab-*.html` 經 iframe 後備載入自身文檔(各自 `<link tokens.css>` + `<html data-theme="dark">` 釘死)→ **帛晝永不觸及**,其頁內 `<style>` 冷 rgba **無需遷移**(Phase 3 隨 iframe 刪)。

**結論**:in-scope ≈ **74 處**冷 rgba(§4 逐一)。其中已審 `view-*.css` **20 處**(遷移須 E2 byte-parity 復審);common.js ocInjectBaseCSS **21 處**(dormant,gate-optional,建議同批機械遷但不阻塞三綠)。out-of-scope 明列 §4.4。

---

## 2 · 【item ①】α-overlay token 設計

### 2.1 核心設計:RGB-三元組 token + inline alpha(byte-parity 與 token 爆炸的解)

**問題**:近黑冷底跨 12 個不同 α 級(0.34/0.38/0.40/0.42/0.45/0.46/0.50/0.55/0.58/0.60/0.65/0.70)。
- 若「一 α 一 token」→ 12+ token 爆炸。
- 若「歸併 α 級」(如 0.42/0.45/0.46 併一值)→ **破玄夜 computed byte-identical**(硬約束),E2 byte-parity 復審與 ratchet 皆會抓。

**解**:token 只承載 **RGB 三元組**(顏色身分),**α 留在呼叫點 inline**。

```css
/* 玄夜:token 展開 = 原字面,byte-identical */
:root[data-theme="dark"]{ --ov-panel-rgb: 13,17,23; }
/* 用法 */ background: rgba(var(--ov-panel-rgb), 0.55);  /* → rgba(13,17,23,0.55) 逐位元相同 */
/* 帛晝:同一 α,三元組翻成暖淺 */
:root{ --ov-panel-rgb: 224,214,196; }
/* 用法展開 → rgba(224,214,196,0.55) = 暖紙淺凹,深字可讀 */
```

- `rgba(var(--x), α)` 語法在所有現代瀏覽器合法;inline `element.style` 亦支援 `var()`。
- **ratchet 合法**:token 值 `13,17,23` 是逗號三元組非 `#hex`;`rgba(var(...),α)` 非裸 hex(view-risk.css:29 已立「ratchet 只禁 #hex,rgba 合法」)。α 字面非顏色,不受 ratchet 管。
- **byte-parity 自動**:每呼叫點保留自己的 α;玄夜三元組 = 原字面 → 逐位元相同,不論 α。**這是唯一能同時滿足「零 α 爆炸」+「玄夜零視覺回歸」的形。**

### 2.2 四個 token(依玄夜三元組身分命名;α 承載 role)

| token | 玄夜值 | 帛晝值 | 覆蓋 role(α 承載深淺) | 覆蓋源字面 |
|---|---|---|---|---|
| **`--ov-panel-rgb`** | `13,17,23` | `224,214,196` | 凹陷面板/表頭/banner/cell/sparkline 底/深井 input(α 0.34–0.70) | `rgba(13,17,23,α)` 全部 |
| **`--ov-panel-b-rgb`** | `22,27,34` | `224,214,196` | 同上之 byte-parity 變體(僅為保 22,27,34 玄夜逐位元) | `rgba(22,27,34,α)`(~5 處) |
| **`--ov-accent-rgb`** | `56,139,253` | `124,100,52`(青銅=--accent rgb) | info/active/selected 底與框、pnl-range 高亮、engine=paper 標記 | `rgba(56,139,253,α)` 全部 |
| **`--ov-muted-rgb`** | `139,148,158` | `150,140,126`(暖中性灰) | neutral chip 底/框、action-cluster-state、sentinel 底、trend-zero stroke | `rgba(139,148,158,α)` 全部 |

**命名對齊**:tokens.css 現有 `--bg-*`/`--*-bg`/`--border-*`/`--accent-weak`。新 token 用 `--ov-*-rgb` 前綴,`-rgb` 後綴明示「這是給 `rgba()` 的三元組」,`--ov-` = overlay。與現有色 token(完整 hex/rgba)區隔清楚。

**⚠ 玄夜三處都要放(E1a 必守)**:玄夜值須同時寫入 **`:root[data-theme="dark"]`**(顯式 toggle)**與 `@media(prefers-color-scheme:dark){ :root:not([data-theme="light"]) }`**(OS 偏好無顯式選擇)兩塊——否則 OS-dark 未顯式選主題的用戶會繼承 `:root` 的帛晝三元組=玄夜視覺破裂。帛晝值只在頂層 `:root`。此與現有 `--bg-*`/`--live` 等的三處定義慣例一致。

**帛晝值算術依據**(§3 同法計算;worst-case α 最深):
- `--ov-panel-rgb=224,214,196`:α=0.70 疊 `--bg-app` → bg=(229,220,204),`--text-secondary`(#5C544B)對比 **5.47**、`--text-primary` **12.47**(全 ≥4.5)。α=0.40 → text-secondary 5.82。**H-2 消解**(原帛晝下 1.0–2.6 不可讀 → 5.47–5.82)。
- `--ov-accent-rgb=124,100,52`:α=0.10–0.15 疊 `--bg-surface`,text-secondary **5.55–5.98**。
- `--ov-muted-rgb=150,140,126`:α=0.10–0.15 疊 surface,text-secondary **5.87–6.19**。
- 玄夜側復算:`--ov-panel-rgb=13,17,23` 疊最亮暗底 `--bg-raised`,text-secondary 6.78–7.03、text-primary 13.98–14.49 → **玄夜健康且 byte-identical**。

### 2.3 映射規則(E1a 機械照做,勿一對一爆炸)

1. **`rgba(13,17,23,α)` → `rgba(var(--ov-panel-rgb), α)`**(α 原樣保留)。
2. **`rgba(22,27,34,α)` → `rgba(var(--ov-panel-b-rgb), α)`**(α 原樣)。
3. **`rgba(56,139,253,α)` → `rgba(var(--ov-accent-rgb), α)`**(α 原樣)。⚠ 帛晝語義由藍翻青銅=**§9 OPEN-1**(A3/operator 確認識別語義)。
4. **`rgba(139,148,158,α)` → `rgba(var(--ov-muted-rgb), α)`**(α 原樣)。
5. **scrim 例外(不動)**:modal overlay 的 `rgba(0,0,0,0.6)` 與 box-shadow 的 `rgba(0,0,0,α)` 是**主題中性純黑 scrim**,兩主題皆正確可讀,**不遷、不 tokenize**(降churn;非 H-2)。若要形式完整,可選加 `--ov-scrim-rgb:0,0,0`(兩主題同值,no-op),但**建議不做**。
6. **非冷家族色不動**:同一 `<style>` 內的 `rgba(248,81,73,*)`(--neg 系)/`rgba(210,153,34,*)`(--warn 系)/`rgba(63,185,80,*)`(--pos 系)/strategy 身分色(58a6ff/a855f7…族C DEFER)**皆非本三家族**,不在本遷移(維持 P0.4 既定 DEFER)。

**deletion test**:刪 `--ov-panel-rgb` → H-2 冷底在帛晝退回不可讀,且失去「單一改點翻兩主題凹陷語義」的能力。刪 `--ov-accent-rgb` → 藍 tint 在帛晝無法一次中性化到青銅。四 token 各有不可替代 invariant,無 ceremonial。
**second-adapter test**:未來第三主題(如高對比)只需在該主題 scope 補四個三元組,呼叫點零改。通過。

---

## 3 · 【item ②】帛晝 AA retune(objective,附算術)

方法:WCAG 相對亮度 `L = 0.2126·R' + 0.7152·G' + 0.0722·B'`(gamma-expanded),對比 `(L_hi+0.05)/(L_lo+0.05)`。閾值:**文字 ≥4.5**、大字/粗體 ≥3.0、**UI/圖形(框/圖示/朱印)≥3.0**。retune **只改帛晝(`:root`)值,玄夜塊不動**(玄夜已健康,見下)。

### 3.1 現況實測(帛晝,`--bg-surface #F8F4EB` 為主卡底 / `--bg-app #F1EBE0` 為最深平底=worst)

| token | 值 | on-app | on-surface | 疊自身 α-bg(over surface) | 判定 |
|---|---|---|---|---|---|
| `--text-muted` | #8A8073 | 3.27 | 3.53 | — | FAIL(文字閾)|
| `--warn` | #9A6700 | **4.10** | **4.43** | warn-bg 上 **3.82** | **FAIL** |
| `--live` | #D93036 | **4.00** | **4.32** | live-bg 上 **3.62** | **FAIL** |
| `--seal` | #A63A26 | 5.44 | 5.88 | seal-bg 上 5.21 | PASS(帛晝健康)|
| `--pos` | #1E7F5C | 4.17 | 4.51 | pos-bg 上 **3.92** | 平底 PASS / 疊 tint FAIL |
| `--neg` | #C13A3A | 4.50 | 4.86 | neg-bg 上 **4.22** | 平底 PASS / 疊 tint FAIL |

玄夜復算確認健康:warn 6.64 / live 5.64 / muted 4.24–4.71 / pos 7.01 / neg 4.54(全 ≥ 對應閾;muted 4.24 見 3.4 豁免)。

### 3.2 retune 提案(保 hue/canon,before → after)

| token | 帛晝 before | **帛晝 after** | after on-app | after on-surface | after 疊自身 α-bg | 備註 |
|---|---|---|---|---|---|---|
| **`--warn`** | #9A6700(4.43)| **`#7A5200`** | 5.83 | 6.30 | **5.43** | 保琥珀 hue,加深;solid margin |
| **`--live`** | #D93036(4.32)| **`#BE1E27`** | 5.20 | 5.62 | **4.71** | **加深熱紅**(canon 6 salience↑非稀釋);⚠**A3 canon-6 salience 複核**(§9 OPEN-2)|
| **`--live-bg`** | rgba(217,48,54,.12)| **`rgba(190,30,54,.12)`** | — | — | — | 隨 `--live` 加深(rgb=BE1E27 之 190,30,39;此處給 190,30,54 保紅相略暖,E1a 取 `190,30,39` 對齊亦可)⚠隨 §9 OPEN-2 |
| **`--muted`** | #8A8073(3.53)| **不改值** | — | — | — | **文檔化豁免**(3.4);ratchet 以 ≥3.0 檢 |
| **`--seal`** | #A63A26(5.88)| **不改帛晝** | — | — | — | 帛晝健康;seal 議題在玄夜(3.3)|

**warn 保守替代**:若 A3 嫌 `#7A5200` 過深,`#8A5C00`(on-surface 5.30 / 疊 tint 4.57)亦 ≥4.5 但 margin 薄;**建議取 `#7A5200`** 留 margin。

### 3.3 `--seal` 議題在玄夜(M-2),非帛晝

A3 M-2:玄夜 `--seal #B8442E` 對比 3.05–3.47(復算:on-app 3.47 / surface 3.31 / **raised 3.12**)。canon 9:**朱印只以方印形制出現,絕不做文字色**(`.seal-mark` = 16px 方框 + 10px「印」字形 = **圖形/圖示**)。→ 正確閾值 **UI/圖形 ≥3.0**,玄夜 3.12(worst)**PASS**。
- **主建議:不改 `--seal` 值**,將 `.seal-mark` pair 於 ratchet 歸 **≥3.0(圖形)**,文檔記 canon-9 理由。保朱砂 hue(身分負載)。
- 選配(A3 若要文字級 margin):玄夜 `--seal` 提亮 `#D9694A`(raised 4.85)——但偏橙、弱化「朱砂印泥」身分 → **不建議**,列 §9 OPEN-4 由 A3/operator 裁。

### 3.4 `--muted` 文檔化豁免(canon:非必讀文字專用)

`--muted` 依設計是「**非必讀文字專用**」(metadata/次要 label/佔位),**刻意低對比**以與 `--text-secondary`(主要次文字)拉開層級。
- **政策**:`--muted` **不受 4.5 文字硬閾**;其 pair 在 ratchet 以 **≥3.0**(incidental/UI 級)檢。帛晝 3.27–3.72 / 玄夜 4.24–4.71 全 ≥3.0 → PASS。
- 實作紀律:**凡承載必讀語義的文字禁用 `--muted`**(用 `--text-secondary`)。此為 E1a/E2/A3 review 準則(非 ratchet 可完全機械擋;ratchet 只擋 muted 自身不低於 3.0)。
- 選配(operator 若要 muted 亦達 4.5):帛晝 `#726A5C`(surface 4.87)——但侵蝕 muted/secondary 區辨,**不建議**。

### 3.5 `--pos`/`--neg` 疊自身 tint FAIL(H-1「其他失敗 pair」,次優先)

pos/neg 在**平卡底 PASS**(4.51/4.86,即 PnL 數字主場景 OK),僅在**疊自身 α-tint 的 chip**(如 `.oc-chip-*`,text=語義色 + bg=語義-bg)降到 3.92/4.22。提案(保 hue,加深,帛晝 only):

| token | before(疊 tint)| **after** | after 平底 surface | after 疊 tint |
|---|---|---|---|---|
| `--pos` | #1E7F5C(3.92)| `#166B4C` | 5.90 | **5.13** |
| `--neg` | #C13A3A(4.22)| `#A83232` | 6.04 | **5.24** |

⚠ pos/neg 是 PnL 重負載色、canon 9 三紅之一(neg)。加深後「健康綠/虧損紅」語義感須 A3 確認 → **§9 OPEN-3**。替代:只加深 chip 內文字或改 chip label 用 `--text-secondary`。**本 spec 建議加深值**,但列 lower-priority + OPEN。

---

## 4 · 【item ②/inventory】完整 rgba 遷移 inventory

格式:`檔:行` — 現值 — role — 目標。**role**:panel-bg=凹陷面板底/scrim=遮罩/tint=語義或 accent 疊色/border=框色/well=深井底。
**AUDITED**=已審 view CSS(遷移須 E2 byte-parity 復審);**DORMANT**=common.js ocInjectBaseCSS(原生表面不注入,gate-optional);**INLINE**=JS 寫 element.style(用 var() 亦合法)。

### 4.1 近黑家族 → `--ov-panel-rgb`(13,17,23)/ `--ov-panel-b-rgb`(22,27,34)〔~29 處〕

**A. 已審 view CSS(E2 byte-parity 復審必要)**
| 檔:行 | 現值 | role | 目標 |
|---|---|---|---|
| view-demo.css:54 | rgba(13,17,23,0.5) | panel-bg(pnl sparkline 底)| `rgba(var(--ov-panel-rgb),0.5)` |
| view-governance.css:46 | rgba(13,17,23,0.58) | panel-bg(gov-boundary-note)| `rgba(var(--ov-panel-rgb),0.58)` |
| view-governance.css:145 | rgba(13,17,23,0.55) | panel-bg(canary-stage-chip)| `rgba(var(--ov-panel-rgb),0.55)` |
| view-governance.css:184 | rgba(22,27,34,0.65) | panel-bg(stage-4 var() 後備)| `rgba(var(--ov-panel-b-rgb),0.65)` |
| view-governance.css:276 | rgba(13,17,23,0.4) | panel-bg(gov panel)| `rgba(var(--ov-panel-rgb),0.4)` |
| view-governance.css:473 | rgba(13,17,23,0.5) | panel-bg(oc-table th)| `rgba(var(--ov-panel-rgb),0.5)` |

⚠ view-governance.css:184 現為 `var(--bg-surface, rgba(22,27,34,0.65))`——rgba 是 var() **後備**;token 恆定義故後備從不觸發,可**直接刪後備留 `var(--bg-surface)`**(born-clean,零 rgba)或改 `rgba(var(--ov-panel-b-rgb),0.65)`。**E1a 裁**;刪後備最乾淨,但屬「值變更」須 E2 確認 var 恆解析。

**B. 殼載共用 JS(active in native;byte-identical 遷)**
| 檔:行 | 現值 | role | 目標 |
|---|---|---|---|
| common-modals.js:470 | rgba(22,27,34,0.7) | well(disabled-card 底)| `rgba(var(--ov-panel-b-rgb),0.7)` |
| common-modals.js:470 | rgba(13,17,23,0.55) | panel-bg(banner)| `rgba(var(--ov-panel-rgb),0.55)` |
| common-modals.js:470 | rgba(13,17,23,0.4) | panel-bg(metric)| `rgba(var(--ov-panel-rgb),0.4)` |
| app-paper.js:1519 | rgba(22,27,34,0.7) | well(replay disabled-card)| `rgba(var(--ov-panel-b-rgb),0.7)` |
| app-paper.js:1531 | rgba(13,17,23,0.55) | panel-bg(ready-banner)| `rgba(var(--ov-panel-rgb),0.55)` |
| app-paper.js:1538 | rgba(13,17,23,0.4) | panel-bg(replay-cell)| `rgba(var(--ov-panel-rgb),0.4)` |
| app-paper.js:1556 | rgba(13,17,23,0.45) | panel-bg(replay-badge)| `rgba(var(--ov-panel-rgb),0.45)` |
| app-paper.js:1560 | rgba(13,17,23,0.46) | panel-bg(quick-grid)| `rgba(var(--ov-panel-rgb),0.46)` |
| app-paper.js:1575 | rgba(13,17,23,0.42) | panel-bg(run-row)| `rgba(var(--ov-panel-rgb),0.42)` |
| app-paper.js:1584 | rgba(13,17,23,0.4) | panel-bg(workflow-grid)| `rgba(var(--ov-panel-rgb),0.4)` |
| app-paper.js:1597 | rgba(13,17,23,0.4) | panel-bg(load-row)| `rgba(var(--ov-panel-rgb),0.4)` |
| handoff_helper.js:874 | rgba(22,27,34,0.7) | well(handoff disabled-card)| `rgba(var(--ov-panel-b-rgb),0.7)` |
| handoff_helper.js:882 | rgba(13,17,23,0.55) | panel-bg(empty-notice)| `rgba(var(--ov-panel-rgb),0.55)` |
| handoff_helper.js:886 | rgba(13,17,23,0.4) | panel-bg(field)| `rgba(var(--ov-panel-rgb),0.4)` |
| handoff_helper.js:895 | rgba(13,17,23,0.55) | well(notes textarea)| `rgba(var(--ov-panel-rgb),0.55)` |
| handoff_helper.js:921 | rgba(13,17,23,0.4) | panel-bg(recent-row)| `rgba(var(--ov-panel-rgb),0.4)` |
| handoff_helper.js:959 | rgba(13,17,23,0.5) | panel-bg(modal-summary)| `rgba(var(--ov-panel-rgb),0.5)` |
| handoff_helper.js:975 | rgba(13,17,23,0.7) | well(modal-input)| `rgba(var(--ov-panel-rgb),0.7)` |
| handoff_helper.js:983 | rgba(13,17,23,0.6) | well(modal-meta code)| `rgba(var(--ov-panel-rgb),0.6)` |

**C. common.js ocInjectBaseCSS(DORMANT,gate-optional)**
| 檔:行 | 現值 | role | 目標 |
|---|---|---|---|
| common.js:750 | rgba(13,17,23,0.45) | panel-bg(mini-trend 底)| `rgba(var(--ov-panel-rgb),0.45)` |
| common.js:839 | rgba(13,17,23,0.5) | panel-bg(oc-table th)| `rgba(var(--ov-panel-rgb),0.5)` |
| common.js:848 | rgba(13,17,23,0.6) | well(oc-explain-simple)| `rgba(var(--ov-panel-rgb),0.6)` |
| common.js:854 | rgba(13,17,23,0.4) | panel-bg(oc-explain-content)| `rgba(var(--ov-panel-rgb),0.4)` |

### 4.2 冷藍家族 → `--ov-accent-rgb`(56,139,253)〔~33 處;⚠帛晝→青銅=OPEN-1〕

**A. 已審 view CSS(E2 復審)**
| 檔:行 | 現值 | role | 目標 |
|---|---|---|---|
| view-demo.css:52 | rgba(56,139,253,0.45) | border(demo-risk-btn)| `rgba(var(--ov-accent-rgb),0.45)` |
| view-demo.css:156 | rgba(56,139,253,0.12) | tint(fill-tab.active)| `rgba(var(--ov-accent-rgb),0.12)` |
| view-governance.css:161 | rgba(56,139,253,0.5) | border(stage-active)| `rgba(var(--ov-accent-rgb),0.5)` |
| view-governance.css:162 | rgba(56,139,253,0.06) | tint(stage-active 底)| `rgba(var(--ov-accent-rgb),0.06)` |
| view-governance.css:217 | rgba(56,139,253,0.15) | tint(stage-badge 底)| `rgba(var(--ov-accent-rgb),0.15)` |
| view-governance.css:220 | rgba(56,139,253,0.4) | border(stage-badge)| `rgba(var(--ov-accent-rgb),0.4)` |
| view-governance.css:449 | rgba(56,139,253,0.12) | tint(oc-chip-info 底)| `rgba(var(--ov-accent-rgb),0.12)` |
| view-governance.css:449 | rgba(56,139,253,0.25) | border(oc-chip-info)| `rgba(var(--ov-accent-rgb),0.25)` |
| view-governance.css:476 | rgba(56,139,253,0.04) | tint(oc-table hover)| `rgba(var(--ov-accent-rgb),0.04)` |
| view-risk.css:158 | rgba(56,139,253,0.12) + 0.25 | tint+border(oc-chip-info)| `rgba(var(--ov-accent-rgb),0.12)` / `,0.25)` |
| view-settings.css:130 | rgba(56,139,253,0.3) | tint(pf-toggle checked slider)| `rgba(var(--ov-accent-rgb),0.3)` |

**B. 殼載共用 JS / 組件 CSS(active)**
| 檔:行 | 現值 | role | 目標 |
|---|---|---|---|
| shell-components.css:191 | rgba(56,139,253,0.15) | tint(oc-btn-primary 底)| `rgba(var(--ov-accent-rgb),0.15)` |
| shell-components.css:192 | rgba(56,139,253,0.3) | tint(oc-btn-primary:hover)| `rgba(var(--ov-accent-rgb),0.3)` |
| common-modals.js:470 | rgba(56,139,253,0.15) | tint(phase-p3 chip 底)| `rgba(var(--ov-accent-rgb),0.15)` |
| common-modals.js:470 | rgba(56,139,253,0.4) | border(phase-p3 chip)| `rgba(var(--ov-accent-rgb),0.4)` |
| common-formatters.js:640 | rgba(56,139,253,0.75) | border(pnl-range active)【INLINE】| `rgba(var(--ov-accent-rgb),0.75)` |
| common-formatters.js:641 | rgba(56,139,253,0.16) | tint(pnl-range active 底)【INLINE】| `rgba(var(--ov-accent-rgb),0.16)` |
| app-paper.js:1561 | rgba(56,139,253,0.22) | border(replay quick-grid)| `rgba(var(--ov-accent-rgb),0.22)` |
| handoff_helper.js:910 | rgba(56,139,253,0.1) | tint(dual-banner.pending 底)| `rgba(var(--ov-accent-rgb),0.1)` |
| handoff_helper.js:911 | rgba(56,139,253,0.3) | border(dual-banner.pending)| `rgba(var(--ov-accent-rgb),0.3)` |
| handoff_helper.js:972 | rgba(56,139,253,0.08) | tint(modal-template 底)| `rgba(var(--ov-accent-rgb),0.08)` |
| handoff_helper.js:973 | rgba(56,139,253,0.25) | border(modal-template)| `rgba(var(--ov-accent-rgb),0.25)` |
| risk-tab.js:224 | rgba(56,139,253,0.15) + 0.5 | tint+border(engine=paper 標記)【INLINE】| `rgba(var(--ov-accent-rgb),0.15)` / `,0.5)` |

**C. common.js ocInjectBaseCSS(DORMANT,gate-optional)**
| 檔:行 | 現值 | role | 目標 |
|---|---|---|---|
| common.js:767 | rgba(56,139,253,0.12) + 0.25 | tint+border(oc-chip-info)| `rgba(var(--ov-accent-rgb),…)` |
| common.js:794 | rgba(56,139,253,0.12) | tint(fill-tab.active)| 同上 |
| common.js:808 | rgba(56,139,253,0.15) | tint(oc-btn-primary)| 同上 |
| common.js:809 | rgba(56,139,253,0.3) | tint(oc-btn-primary:hover)| 同上 |
| common.js:842 | rgba(56,139,253,0.04) | tint(oc-table hover)| 同上 |
| common.js:957 | rgba(56,139,253,0.12) + 0.3 | tint+border(oc-curr-badge)| 同上 |
| common.js:959 | rgba(56,139,253,0.25) | tint(oc-curr-badge:hover)| 同上 |

### 4.3 冷灰家族 → `--ov-muted-rgb`(139,148,158)〔~12 處〕

| 檔:行 | 現值 | role | 目標 | 類 |
|---|---|---|---|---|
| view-paper.css:186 | rgba(139,148,158,0.06)+0.18 | tint+border(action-cluster-state)| `rgba(var(--ov-muted-rgb),…)` | AUDITED |
| view-stock.css:18 | rgba(139,148,158,.16) | border(se-kv th/td 底線)| **已改 `--border-subtle`**(見下)| AUDITED |
| common-mode-badge.js:343 | rgba(139,148,158,0.12) | tint(sentinel badge 底)| `rgba(var(--ov-muted-rgb),0.12)` | active |
| common.js:751 | rgba(139,148,158,0.45) | border(mini-trend-zero stroke)| `rgba(var(--ov-muted-rgb),0.45)` | DORMANT |
| common.js:766 | rgba(139,148,158,0.1)+0.2 | tint+border(oc-chip-neutral)| `rgba(var(--ov-muted-rgb),…)` | DORMANT |
| common.js:772/773/775 | rgba(139,148,158,0.22/0.1/0.1) | border/tint(strategy chip **fallback**)| `rgba(var(--ov-muted-rgb),…)` | DORMANT ⚠ |
| common.js:826 | rgba(139,148,158,0.06)+0.18 | tint+border(action-cluster-state)| `rgba(var(--ov-muted-rgb),…)` | DORMANT |

⚠ view-stock.css:18 依 MODULE_NOTE 該冷灰**已改語義 `--border-subtle`**(玄衡 skin);此列為**已完成/確認**,非待遷(E1a 核實現值,若已 `--border-subtle` 則 NO-OP)。
⚠ common.js:772–780 strategy chip:**只有 fallback 中性色(139,148,158)在本家族**;per-strategy override(58a6ff/a855f7…)是**族C DEFER**,不動。

### 4.4 明確 OUT-OF-SCOPE(不遷,列此供 PM 核)

- **legacy `tab-*.html` 頁內 `<style>` 冷 rgba**(tab-agents/demo/development/earn/governance/live/paper 等)—— iframe 後備,`data-theme="dark"` 釘死,帛晝永不觸;Phase 3 隨 iframe 刪。
- **console.html / trading.html / index.html / login.html 冷 rgba**——legacy 殼,Phase 3 刪除目標(C6e defer,driver §6)。
- **rgba(0,0,0,α) scrim / box-shadow**——主題中性,兩主題正確(§2.3 規則 5)。
- **strategy 身分色 / --neg·--warn·--pos 系 rgba**——非冷家族,P0.4 既定 DEFER/保留。

---

## 5 · 【item ③】AA ratchet 靜態測試設計

新增 `tests/structure/test_gui_theme_aa_contrast_static.py`(P0.6 式,純算術,零 runtime/DOM)。

### 5.1 結構

1. **Parser**:讀 `tokens.css`,抽兩主題 token→值:
   - 帛晝 base = 頂層 `:root{…}` 塊(注意排除 `[data-theme]`/`[data-density]`/`@media` 塊)。
   - 玄夜 = `:root[data-theme="dark"]{…}` 塊(**權威**;顯式 toggle 態,與 media query 塊同值)。
   - 解析 `#rgb`/`#rrggbb`→(r,g,b);`--ov-*-rgb`→三元組;`rgba(...)`/`var(...)` 後備按需展開。
2. **合成器**:`composite(fg_rgba_or_hex, [α-overlay chain], base_hex)` → 實色(疊 α over parent);`contrast(c1,c2)` = WCAG。
3. **PAIRS 清單**(見 5.2)逐條 assert `contrast >= threshold`,fail 訊息含 `theme/fg/bg/got/need`。
4. **anti-vacuous**(5.4)。

### 5.2 檢查 pair 清單(fg, bg-鏈, threshold, theme)

worst-case 背景取法:**帛晝取最深平底 `--bg-app`**(語義暗字對比最低);**玄夜取最亮暗底 `--bg-raised`**。

**文字級(≥4.5)**
| # | fg | bg(worst)| 主題 |
|---|---|---|---|
| 1 | --text-primary | --bg-app | 帛晝 |
| 2 | --text-secondary | --bg-app | 帛晝 |
| 3 | --warn | --bg-app | 帛晝 |
| 4 | --live | --bg-app | 帛晝 |
| 5 | --pos | --bg-app | 帛晝(§9 OPEN-3 決後)|
| 6 | --neg | --bg-app | 帛晝(同上)|
| 7 | --warn | --warn-bg over --bg-surface | 帛晝(疊 tint chip)|
| 8 | --live | --live-bg over --bg-surface | 帛晝 |
| 9 | --pos | --pos-bg over --bg-surface | 帛晝(OPEN-3)|
| 10 | --neg | --neg-bg over --bg-surface | 帛晝(OPEN-3)|
| 11–16 | 上述 text/warn/live/pos/neg + secondary | --bg-raised | 玄夜 |
| 17 | --text-secondary | `--ov-panel-rgb`@0.70 over --bg-app | 帛晝(overlay 最深井,item① 帛晝值閘)|
| 18 | --text-primary | `--ov-panel-rgb`@0.70 over --bg-app | 帛晝 |
| 19 | --text-secondary | `--ov-panel-rgb`@0.70 over --bg-raised | 玄夜(byte-parity 健康復算)|

**UI/圖形級(≥3.0)**
| # | fg | bg | 主題 | 備 |
|---|---|---|---|---|
| 20 | --seal | --bg-raised | 玄夜 | 朱印方印(canon 9 圖形)|
| 21 | --seal | --bg-app | 帛晝 | |
| 22 | --text-muted | --bg-app | 帛晝 | **豁免:≥3.0**(3.4)|
| 23 | --text-muted | --bg-raised | 玄夜 | 同 |
| 24 | --accent(focus 環)| --bg-app | 帛晝 | :focus-visible outline |
| 25 | --border-strong | --bg-app | 帛晝 | 分隔線可辨 |

（overlay accent/muted 疊色屬 tint 底非文字前景,text-secondary 疊其上已由 #17/#18 型 pair 涵蓋;E1a 可加 `--text-secondary` on `--ov-accent-rgb`@0.15 / `--ov-muted-rgb`@0.15 各一條加固,選配。）

### 5.3 閾值常量與 baseline 紀律(P0.6 式)

```
THRESH_TEXT = 4.5
THRESH_UI   = 3.0
```
- **紀律選 (a):retune 先於 test 上線 → test 上線即全綠**(對齊 P0.6「ratchet 全綠引入、只增不減」;避免 red baseline 與豁免清單膨脹)。
- 依賴序保證全綠:**item ②(§3 retune)+ item ①帛晝 overlay 值(§2.2)必須先 land**,test 才 land。§6 排序強制此。
- **不採**「帛晝 gated-until-retune 分段」——會留紅、易腐;retune 是純算術(本 spec 已給值),無理由拖到 test 之後。
- 若 PM 決 pos/neg(OPEN-3)不 retune:pair #5/#6/#9/#10 改掛 **≥3.0(chip 內大字/UI 論)** 或移出 enforced 段並記 `# OPEN-3 pending` 明列——**由 PM 一次定,不留隱性紅**。

### 5.4 anti-vacuous(防空洞綠)

1. `contrast('#000','#fff') == 21.0 ±0.05` 且 `contrast('#777','#777') < 1.05`(公式自檢)。
2. 帛晝 dict 與 玄夜 dict 各解析到 **≥15** 個 token(含全部 `--ov-*-rgb` 四個 + warn/live/seal/muted/text-*);缺任一 gate token → FAIL(防 parser 靜默漏)。
3. 實際評估 pair 數 **≥ len(PAIRS)** 且 ≥ 20(防清單被清空)。
4. **red-proof**(隨附註釋 + 一個 xfail 或斷言):把某 fg 換成刻意過淺值 → 對應 assert 必 FAIL(證有牙)。E4-writer 落地時附「合成注入 → 精確定位失敗 pair → 還原全綠」證據(比照 P0.6 `test_gui_style_ratchet_static.py`)。
5. `--ov-*-rgb` 解析出的**玄夜三元組必等於原字面**(13,17,23 / 22,27,34 / 56,139,253 / 139,148,158)——把 byte-parity 錨進 test(改壞玄夜值即紅)。

---

## 6 · 【item ④】實作順序 / 拆輪 / 角色分工

依賴序:**retune 值定(§3,本 spec 已給)→ token 定義入 tokens.css(§2.2)→ 遷移呼叫點(§4)→ test 鎖(§5)**。

| 輪 | 工作 | 角色 | 觸已審 view CSS? | 備註 |
|---|---|---|---|---|
| **P1.3-a** | ① tokens.css 加 4 個 `--ov-*-rgb`(兩主題)+ ② 帛晝 retune(`--warn`/`--live`/`--live-bg`;pos/neg/seal 待 OPEN)| E1a→E2 | 否 | 純 tokens.css;E2 核玄夜三元組=原字面、帛晝值=§3 表 |
| **P1.3-b** | §4.1B/4.2B/4.3 active 共用 JS + shell-components.css 遷移(app-paper/handoff/common-modals/common-mode-badge/common-formatters/risk-tab.js + shell-components.css)| E1a→E2 | 否 | INLINE(common-formatters/risk-tab)用 var() |
| **P1.3-c** | §4.1A/4.2A/4.3 **已審 view-*.css** 遷移(demo/governance/risk/paper/settings/stock)| E1a→**E2 byte-parity 復審** | **是** | 玄夜 computed byte-identical 逐點親證(word-diff + var 解析);governance:184 後備裁決 |
| **P1.3-d** | §4.1C/4.2C/4.3 common.js ocInjectBaseCSS(**gate-optional**,dormant)| E1a→E2 | 否 | 可併 P1.3-b 或延後;不阻塞三綠 |
| **P1.3-e** | ③ ratchet test(§5)| **E4-writer**→E4-verifier | 否 | 全綠引入 + red-proof;**必在 a–c 之後** |
| **(gate)** | A3 帛晝全站視檢 + 解 data-theme 釘死 | A3 + operator/Linux runtime | — | §7;**本 spec 不 attest** |

- **可單輪**:P1.3-a(小)。P1.3-b 與 -d 可合。
- **必拆**:P1.3-c 觸 6 個已審 view CSS,**E2 byte-parity 復審是硬邊界**(不破 R74/R77/R78 已審 byte-parity),建議獨立輪或按 view 細拆(governance CSS 最大)。
- **E1a vs E4**:遷移/retune=E1a(gui-style-guide + bilingual-comment-style);ratchet test=E4-writer;回歸+獨立複核=E4-verifier(node --check 觸碰 JS + `test_gui_style_ratchet_static.py` 不回退 + 新 AA test 有牙)。
- **ratchet 教訓(R77)**:實作檔註釋**勿留字面 `#hex`/`<style>`**(E4-verifier ratchet 會抓註釋字面);本 spec doc 內引用 hex 正常。token 值寫逗號三元組(非 hex),ratchet 安全。

---

## 7 · 【item ⑤】objective vs A3/operator-runtime-signoff 切分

| 項 | 類別 | 產出者 | 何以足夠 |
|---|---|---|---|
| 4 個 α-overlay token 命名/兩主題值 | **objective** | 本 spec / E1a | 值由 WCAG 算術定;玄夜 byte-parity 可靜態證 |
| §4 完整 inventory(file:line:role:target)| **objective** | 本 spec(grep 核實)| 源碼枚舉 |
| §3 對比算術 before→after | **objective** | 本 spec(WCAG 公式)| 純數學,CI 可復算 |
| §5 ratchet test | **objective** | E4-writer | 純算術,node/pytest 可跑 |
| 玄夜 computed byte-identical | **objective(靜態)** | E2 byte-parity 復審 | word-diff + var 解析證,無需渲染 |
| **帛晝實際視覺可讀性走查** | **A3 + Linux runtime** | A3 / operator | 需真渲染三態(V5-defer,driver §6)|
| **三態真值渲染(canon 7)** | **runtime** | operator/Linux | Mac 不可誠實跑 |
| **解 22 文檔 data-theme 釘死** | **A3 三綠 + operator** | operator | gate 動作,非本 spec 範疇 |
| **`--live` 帛晝加深(#BE1E27)salience** | **A3 canon-6 複核** | A3 | 加深保 salience 屬 canon-6 判斷,標記待 A3 簽 |

**本 spec attest**:token 設計、inventory、對比算術、test 設計 = 自主可交付。
**本 spec 不 attest**:帛晝真渲染/三態/解釘死 = gate 三綠後 A3 + runtime。

---

## 8 · 硬約束(實作須守)

1. **玄夜遷移零視覺回歸(computed byte-identical)**:RGB-三元組 + inline α 保證;已審 view CSS(§4.1A/4.2A/4.3 AUDITED)遷移**須 E2 byte-parity 復審**(不破 R74/R77/R78)。
2. **canon 6**:`--live` 不稀釋——帛晝走**加深**(#D93036→#BE1E27,salience↑),`--live-bg` 隨之;A3 canon-6 salience 複核。
3. **canon 9**:三紅(--neg/--live/--seal)不增第四紅;朱印 `--seal` 只方印形制,retune 走 UI≥3.0 或不動值。
4. **零裸 hex 新增於錯處 / ratchet 教訓(R77)**:token 值用逗號三元組(非 hex);實作檔註釋勿留字面 `#hex`/`<style>`;spec doc 內引用 hex 正常。
5. **不動 22 文檔 data-theme 釘死**(解釘 = gate 三綠 + A3 + runtime,非本 spec)。
6. **scrim `rgba(0,0,0,α)` 不遷**(主題中性)。

---

## 9 · OPEN(供 PM 裁)

- **OPEN-1(冷藍帛晝語義)**:`--ov-accent-rgb` 玄夜=藍(56,139,253,byte-parity 必留)、帛晝=青銅(124,100,52)。此為**跨主題識別語義翻轉**(info/active 在玄夜藍、帛晝青銅)。理由:working doc 已中性化 `--blue`、canon 10 青銅=焦點/選中、玄夜 byte-parity 是硬約束不可改藍。**風險**:同一「選中/info」語義兩主題不同色相。建議接受(各主題內自洽;玄夜零回歸優先)。A3/operator 確認。
- **OPEN-2(`--live` 帛晝加深值)**:#BE1E27 + `--live-bg` rgba(190,30,39/54,.12)。canon-6 salience 複核由 A3。若 A3 要更貼原色相可取 #C1272D(疊 tint 4.46,margin 薄)。
- **OPEN-3(pos/neg 疊 tint FAIL)**:平底 PASS、僅 chip 疊自身 tint FAIL(3.92/4.22)。選項:(a) 帛晝加深 --pos→#166B4C/--neg→#A83232(§3.5);(b) chip 內文改 `--text-secondary`;(c) 接受 chip 例外(≥3.0)。PM 一次定,ratchet pair #5/#6/#9/#10 隨之(§5.3)。**建議 (a)**(最少特例)。
- **OPEN-4(玄夜 --seal)**:主建議「不改值 + UI≥3.0 閾 + canon-9 文檔」;若 A3 要文字級 margin 才提亮(#D9694A,弱化朱砂身分,不建議)。
- **OPEN-5(common.js ocInjectBaseCSS 是否本輪遷)**:dormant in native、Phase 3 刪除目標。建議**同批機械遷**(byte-identical,legacy iframe 亦受益)但**不阻塞三綠**;或全 defer Phase 3。PM 裁 P1.3-d 排入或延後。
- **OPEN-6(view-governance.css:184 var() 後備)**:`var(--bg-surface, rgba(22,27,34,0.65))` 後備恆不觸發;可刪後備(born-clean 零 rgba)或改 `--ov-panel-b-rgb`。屬「值變更」須 E2 確認 token 恆解析。建議刪後備(最乾淨)。

---

## 10 · PM 裁決(R79,2026-07-12)

6 OPEN 皆屬 P1.3 token/AA 設計選擇(objective 推導為主;帛晝真渲染視覺=A3+Linux runtime downstream gate,本裁不 attest 視覺,只定實作方向)。PM/Conductor 逕裁;E1a/E4 照此,E2 據此核。

- **OPEN-1 → 採 PA 建議(接受)**:`--ov-accent-rgb` 玄夜藍(byte-parity 硬約束不可改)/帛晝青銅——**非 bug,是正確主題適配**(各主題用自身 accent:玄夜現冷藍 tint、帛晝 玄衡青銅 --accent;canon 10 青銅=焦點/選中)。跨主題色相不同 = 主題本質,用戶不同屏對比。玄夜零回歸優先。玄夜 blue→bronze 統一屬**未來獨立視覺清理**(visual change,defer,非 P1.3)。A3 帛晝視覺複核 downstream。
- **OPEN-2 → 採 #BE1E27 加深**(5.62/4.71 AA 達標,canon-6 加深保熱紅 salience 非稀釋)+ `--live-bg` rgba(190,30,39,.12)。**標「A3 canon-6 salience 複核」**(downstream,同遷移 cutover gate)。#C1272D 薄 margin 選項不採(4.46 太貼閾)。
- **OPEN-3 → 採 (a) 帛晝最少加深** `--pos`/`--neg`(§3.5 值 #166B4C/#A83232)使 chip 疊自身 tint 達 AA;ratchet pair #5/#6/#9/#10 掛 **enforced 帛晝 ≥4.5**(不留隱性紅、不採 chip 例外)。玄夜側 pos/neg 若健康不動(E1a 復算確認)。
- **OPEN-4 → 採「不改值」**:玄夜 --seal=朱印方印**圖形**(非必讀文字),ratchet 掛 **UI ≥3.0 PASS**;canon-9 朱砂身分保留,不提亮。
- **OPEN-5 → DEFER common.js ocInjectBaseCSS 21 rgba 到 Phase 3**:native 殼**不呼** ocInjectBaseCSS→這 21 處在帛晝**永不渲染**(dormant,legacy iframe 綁定,Phase-3 刪除目標)。**不排入 P1.3-d,不阻塞三綠,不計入帛晝-native gate**;ratchet/inventory **明列為 out-of-scope 記錄**(coverage-debt,legacy 隨殼死)。P1.3 有效 native 遷移面 = 74 − 21 dormant = **~53**(view CSS 20 + active shared JS + shell)。
- **OPEN-6 → 採「刪後備」**:view-governance.css:184 `var(--bg-surface, rgba(...))` → `var(--bg-surface)`(token 恆定義,computed byte-identical),併入 P1.3-c(已審 view CSS 批,E2 byte-parity 復審)。

**實作拆輪(采 PA §6,OPEN-5 移除 -d)**:**P1.3-a**(tokens.css:4 α-token 兩主題定義 + AA retune --warn/--live/--live-bg/--pos/--neg 帛晝值;E1a→E2 對比算術+玄夜 byte-parity 核)→ **P1.3-b**(active 共用 JS 冷 rgba→token;E1a→E2)→ **P1.3-c**(已審 view CSS 20 處 rgba→token + OPEN-6;**E2 byte-parity 復審=硬邊界**,獨立輪)→ **P1.3-e**(AA ratchet test;E4-writer→E4-verifier,**必最後**,retune 落定後上線=全綠引入 baseline (a))。common.js dormant(舊 -d)=Phase-3 defer。**三綠達成**=①α-token+53 遷移 ②AA retune 值 ③ratchet 綠;**解 data-theme 釘死 + 帛晝真渲染走查 = A3 + Linux runtime downstream(V5-defer,不在自主 loop 範疇)**。

---

## 附:算術可復現(WCAG)

相對亮度 `L=0.2126R'+0.7152G'+0.0722B'`,`C'=C/255; C'≤0.03928 ? C'/12.92 : ((C'+0.055)/1.055)^2.4`;對比 `(L_hi+0.05)/(L_lo+0.05)`;α 合成 `out=α·fg+(1−α)·parent`。自檢:黑/白=21.00。以上所有數值由此式復算,E4-writer 的 test 用同式即與本 spec 逐位吻合。
