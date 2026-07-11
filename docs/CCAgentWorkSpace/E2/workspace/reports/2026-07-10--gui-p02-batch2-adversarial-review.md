# E2 PR Adversarial Review — GUI P0.2 批次 2(working-tree 未提交)· 2026-07-10

STATUS: **RETURN to E1a(1 HIGH 待修;其餘全綠)**

- HEAD:`3541bb142`(> 派工基準 aa79eb8eb);origin/main = `aa79eb8eb`,review 前後兩次 fetch 無 sibling push(§5a/5e PASS)。
- 審查面(5 檔,與 E1a 申報一致):`tab-monitoring.html`(63±)/`tab-system.html`(105±)/`tab-settings.html`(417±)/`oc-utilities.css`(+4)/`docs/execution_plan/gui_redesign/design/05_utilities.md`(+4,本審查另 +5 doc 註記)。governance.js NO-OP 程式證實(style= dq/sq、`.style.`、setAttribute('style') 全 0)。
- 規格:`docs/execution_plan/gui_redesign/design/05_utilities.md`;E1a 報告:`docs/CCAgentWorkSpace/E1a/workspace/reports/2026-07-10--gui-p02-batch2-monitoring-system-settings.md`。

## 全綠面(全部親證,非採信報告)

1. **度量**:per-file HEAD→now:monitoring 27→0、system 43→0、settings 140(同行 regex)+1 跨行=141 真屬性→0、governance.js 0→0;全站 `style="…"` 1420→1210(−210,與跨行 1 處 line-based regex 不可數對賬吻合)。四檔 `style='`、`setAttribute('style')` 全 0。殘留 `.style.` 寫點 system 6 + settings 6 = 逐一比對申報留置清單完全一致(mode-control-card display / live-hold-bar width ×5;apikey-hint peek color ×2 / alert-config-loading display+color ×4),各元素零同軸 utility(axis-conflict 0)。
2. **§A/§4 同批追加治理**:兩處 diff 純 ADD(0 刪改,append-only ✓,§A 尾+批次註記 ✓);`tests/structure/test_gui_utilities_spec_drift_static.py` 親跑 **2/2 PASS**(byte-identical,強於 E1a 的 normalized);`ml-2`(6/8→8,§5.2 合)與 `cursor-not-allowed` 均真被消費(disabled chip+mode-flow span;disabled restart 按鈕)。
3. **JS 軸殘留=0(跨檔)**:38 個轉換/掛載元素 id 對 common.js/common-modals/common-formatters/common-mode-badge/governance.js/fetch_with_csrf 全 grep = 0 hit。
4. **鐵則二窮舉反查**:三檔全部 `className =` 寫點逐一核——monitoring(grafana-badge/pipe/tg/oc-*)、system(m-mode/m-auth/m-prot/m-engine/qa-feed-chip:977/badge/chip/dots)、settings(dc-valid:966/sys-decision-lease:1007,1012/badges/alert chips:1555,1667-74,1697-1703)——wipe 目標零 utility 直掛;字級全走父層 `mv--sm/--md`(`.oc-metric` 包裹層無任何 JS 觸碰,metric 容器無 innerHTML 重生);alert 三 chip 走 `.alert-ch-head .oc-chip`(0,2,0) 後代選擇器,**每個重寫串都保留 `oc-chip`** 親證;`qa-chip-sm` 在 :977 重寫串內(HEAD 死引用,本批補正本=baseline sweep 唯一命中,申報一致);`b-cost30` 唯一寫點=ocSetText:1008(直掛 fs-md 合法);mbtn-live_reserved 僅 classList.toggle('active')(:794)非 wipe。
5. **新類名 baseline sweep**:42 名(E1a 報 30+enum 展開)× HEAD 全 static 64 檔 exact-token —— 僅 qa-chip-sm 命中(上述申報死引用),0 未申報碰撞。
6. **拼寫/解析**:三檔 added-line 全 class token(markup+JS 模板+classList+enum 槽位展開)對定義集(§A/§B+tokens.css 原子+頁內塊+ocInjectBaseCSS)全解析,unresolved 僅 JS 串接 regex 噪音;added-line `var(--*)` 全數在 tokens.css/compat 有定義(雙主題兩態均定義)。
7. **node --check 親跑**:3 檔 inline script(6996/34460/49837 chars,含抽取長度斷言)+ governance.js 全 PASS;HTMLParser tag-stack residue=0、errors=0 ×3;三連 link(tokens→compat→utilities)未擾動。
8. **收斂全在 §5 對照表/申報清單內**:逐行讀全部三個 diff(871+105+63 行)核每個轉換點——exact 匹配(12/13/14/16px、opacity、flex 家族、w-full、flex:1≡flex-1、min-height 18、lh 1.8/line-height 2 刻意留組件層)或已申報收斂(10→11、10→12、14→12、6→8、18→16、18→20、48→32、lh→1.6、圓角 6→5、GitHub 紅綠黃→--neg/--pos/--warn、藍系→accent-weak/border-subtle、槽灰→border-strong/oc-chip-neutral/bg-hover、#fff→text-primary、舊黃→--warn/warn-bg)。compat 等值鏈親證:--border→border-subtle、--text-dim→text-secondary、--bg→bg-app、--card-bg→bg-surface、--green/--red/--yellow→--pos/--neg/--warn(gf-bar/mode-flow/alert-ch-box/apikey-card 等「看似變值」實為同值)。
9. **added-line hex/style= 掃描**:hex/rgba 僅 2 行=tab-system 紫 verbatim relocation(:85/:86,值與原 inline 逐字同,帶 P0.4 註記);style= 0;新增註釋 0 靶字面(批次 1 教訓已吸收)。
10. **紫色處置**:①system 5 處——3 文字重用 `.purple{color:#a855f7}`(:52,值 exact=零觀感)+2 border 按原值遷入頁內塊(warn-box--live (0,2,0) 同權後載勝 :61 `.confirm-body .warn-box` 親證,injection 進 #confirm-body :488/714 containment 成立);但 mode-btn--live 有 cascade 態問題(見 HIGH-1)。②settings 紫 sweep=0 殘(apikey live-demo 注記為唯一紫,→`.apikey-note-live{color:var(--live)}` 語義升級,已列 A3 #1,無誤傷)。
11. **三紅紀律(canon 9)**:--live(apikey-card--live/apikey-note-live)、--neg(rst-banner/confirm-block--risk/t-neg/pf-cap--neg/apikey-warn--live/alert-note--warn)、--warn(琥珀非紅);紫=palette 外隔離帶 P0.4 註記;**無第四紅**。rst-banner .92→--neg 全濃度+confirm-block--risk 全濃度承批次 1 idx-banner 先例一致。
12. **pre-existing 抽查**:`id="restart-status"` HEAD=0 hit(死路徑非本批引入,openRestartModal guard-return 可證);`.confirm-close` 宣告與 dlg-apikey 原關閉鈕 inline 逐字同(複用合法);`.confirm-modal-dialog`/`.oc-dialog` 各僅 1 markup 消費點(width/max-width 收入既有規則零誤傷);cascade 前提「頁內 `<style>` 在 body、ocInjectBaseCSS append 到 head(common.js:1008)」親證成立(card--flush/qa-chip-sm 等同權 tie 由本塊勝)。
13. **§5 race**:5a/5e 兩次 fetch,origin/main 恆 `aa79eb8eb`,0 sibling push;5b 本批 5 檔 scope 乾淨,worktree 其餘髒檔=兄弟 session(login.html=auth 錯誤映射 hunks 親證、auth*.py/tests/memory 檔)未觸碰;5c 4 stash 全 pre-existing 未動;5d N/A(未 commit)。

## Findings

| # | 嚴重性 | 位置 | 描述 | 修法方向 |
|---|---|---|---|---|
| 1 | **HIGH** | `tab-system.html:85`(vs `:44/:45`) | `.mode-btn--live`(0,1,0) 輸給 `.mode-btn:hover`/`.mode-btn.active`(0,2,0)。原 inline `border-color:rgba(168,85,247,0.4)` 對一切非 !important 規則無條件勝 → 紫框全狀態恆在;現 hover 態與 **live_reserved 為當前模式(active,:794 toggle 掃全按鈕)** 時紫框變 accent 青銅。破 E1a「verbatim relocation 零觀感變更」claim(四.1),恰發生在 live 風險識別元素的最要緊狀態;jsdom 僅斷 class 共存,斷不到 computed winner。 | 選擇器升為 `.mode-btn.mode-btn--live`(0,2,0),留在 :45 之後(同權後載勝)即全狀態復現原 inline 行為;若改判為刻意變更則必須列 A3+四.9(不建議,違 relocation 契約) |
| 2 | LOW(report) | E1a 報告 §二.1 | 「per-file `grep -o` 有數到(141)」不可重現:同 regex 對 HEAD settings=140;跨兩物理行的 rst-banner style 屬性 line-based grep 兩行皆抓不到(首行無閉引號/次行無 `style="`)。實質不變:141 真屬性(含跨行 1)全清、global −210 對賬吻合。 | E1a 報告一行更正量測歸因(不動代碼) |
| 3 | INFO | settings ×7(key hint/各輸入框) | `font-family:monospace`(generic)→`.mono`=var(--font-mono)("SF Mono" 等具名 stack):§4 家族 4 詞彙歸宿正確,但屬可見字形差,四.9 刻意變更清單漏列。 | 補入 A3 過目面 |
| 4 | INFO | `tab-settings.html` `.confirm-block--risk` | 邊框 rgba(239,68,68,.3) 按 §5.5 機械行應→`--live`,E1a 判語義(重啟風險≠live 模式)落 `--neg`:合理且值變更已列四.9/A3,但 §5.5-row 偏離本身未點名。 | A3 複核色相時一併裁,無需改碼 |
| 5 | NIT(PM) | commit 編排 | §9 步 5+§11:詞彙追加(05_utilities.md+oc-utilities.css,含本審查 §5.2 註記)應獨立小 commit 先行,再 3 tab 批次 commit;worktree 兄弟髒檔(login.html auth hunks/auth*.py/tests/memory)必 narrow-stage 排除。 | PM 提交時執行 |

## 裁決項(授權內 doc 級修,已執行)

**§5.2 規則 vs 對照表 10px 矛盾 → 表值 12 正確**。證據:§4 `gap-3` 註記逐字寫 `10/12/14px → 12`(spec-of-record 詞彙,批次 1 已 merge 入 CSS);§5.2 表 10 列於 `--sp-3`;批次 1 先例 oc-tc-meta 10→12 已 shipped(E2 PASS+PM merge);「等距取小」行文僅在 14→12/20→16 有示範,對 10 逐字適用得 8 與三處工件+先例矛盾=規則行文 outlier。已在 §5.2 表後加中文釐清註記(blockquote,散文區不觸 §4 fence;spec-drift guard 重跑 2/2 綠)。**E1a 本批全部按 12 的轉換點維持有效,無需重做。**

## 8 條 checklist / OpenClaw §3

GUI-only 批次:適用項全過(無 except:pass/f-string log/API 端點/私有穿透/asyncio 議題;innerHTML 模板動態值全走 ocEsc 未擾動;0 硬編路徑;新註釋中文優先且解釋 why;三檔行數受檔案治理既有態,未新增超限)。不適用項:SQL/migration/Rust/IPC/Bybit API。

## 結論

**RETURN to E1a — 1 HIGH 待修**:
1. `tab-system.html:85` — `.mode-btn--live` 改 `.mode-btn.mode-btn--live`(或等效使其在 hover/active 態仍勝),並補一條「active 態 computed border-color 仍為 rgba(168,85,247,0.4)」型斷言(class 共存斷言不足);順帶更正報告 finding-2 的量測歸因一行。

Fix 後 narrow re-review 限此 delta。其餘面(含 §A 追加、紫色處置②、三紅紀律、全部收斂)已審結,無需重驗。
