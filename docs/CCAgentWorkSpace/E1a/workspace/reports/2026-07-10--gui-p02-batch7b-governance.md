# GUI 大改 P0.2 批次 7b — governance 群 inline style 清理

> **記錄狀態**:batch 7 拆 7a-risk[已完成 `0b432dde6`] / 7b-governance。7b 的 E1a agent
> 完成清理但因 harness「不寫 report .md」指令未落報告檔(結論在 `E1a/memory.md` 7b 節);
> 本報告由主會話(PM)依 E1a 內聯自報 + E2 對抗審查 + PM 本地驗證重建。2026-07-10。
> 規格正本 `docs/execution_plan/gui_redesign/design/05_utilities.md`。

## 一、度量

| 檔 | 前 | 後 |
|---|---|---|
| tab-governance.html | 205 | **0** |
| governance-tab.js | 78 | **0** |
| autonomy-posture.js | 6 | **0** |
| canary-tab.js | 6 | **0**(+1 合法 §7 scoped-var `--canary-fill-w`,唯一允許形式)|
| **合計** | **295** | **0** |

governance-tab.js **1921→1877 行**(toggle 簡化淨減,< 2000 硬頂親證)。§4 append `.fw-normal`(--weight-regular)+`.px-4`(--sp-4),spec↔oc-utilities.css byte-identical(spec-drift 2/2)。

## 二、E2 對抗審查(a4e2cd6f5,PASS to E4,0 blocker)

- **鐵включ一(JS 軸殘留=0)**:9 個折疊 toggle 全走 classList(**讀值陷阱**核實:舊 `body.style.display==='none'` 判態全移除,新 `classList.toggle('hidden')?'▶':'▼'`,初態↔箭頭↔語義三者一致,無反向失效);5 modals(oc-modal hidden,.oc-modal base=display:flex 非-important,.hidden !important 勝);lt-progress/canary-fill 走 setProperty scoped-var CSS 消費對得上;10 個 JS `.style.*` 色/邊框寫故意不掛同屬性 utility(走非-important 頁組件供預設,per-element 判別正確)。
- **鐵則二**:4 檔 0 個 `.className=`(無 wipe)。
- **裸屬性(7a HIGH 復現檢查)**:`class="…" x--y` 4 檔 0、double class= 0——7a 教訓已內化。
- **順帶 bug 修(E2 裁決可接受,A3 簽核)**:risk-badge 原 `background:var(--red)+'22'`=無效 CSS(var() 無法追加 alpha hex→宣告被丟棄→背景透明)=pre-existing broken;改 `gov-risk-high/med/low/none`→--neg/warn/pos + -bg;三紅無第四紅;operator-facing 視覺變更(Audit Trail/Pending Audit 徽章現有真底色)。
- 治理邏輯零觸碰(fetch/授權/lease/gate/de-escalation/autonomy-toggle/canary 邏輯與事件全不動,onclick 名不變);XSS 無新面(class 串靜態字面,ocEsc/ocSanitizeClass 對動態值維持)。
- 朱印(canon 9):governance 無既存方印;authority 紫 `#a855f7` 是文字/按鈕 tint 非方印形制,**不轉 --seal**(轉=誤用),verbatim 入 gov-purple-* 頁類+P0.4。

## 三、PM 裁決 + A3 必審

- **risk-badge 視覺變更(E2 LOW)**:PM ACCEPT——等價修復 pre-existing broken CSS(徽章本應有色底,invalid CSS 使其透明),修為語義色底是正確 intent;交 A3 視覺簽核。
- **A3 追加**:①blue→accent 二分(pending/selected 語義,gov-pending-note/gov-level-badge 的 accent 已 CSS 註記 defer P0.4 中性化複審);②palette 外色 verbatim(紫/琥珀/slate,P0.4);③line-height→lh-cjk、9/10px 徽章→fs-micro 收斂微變;④gov-trust-expires/signed-auth 初始 placeholder「--」由 t-dim 改預設字色(首次 poll 前/poll 失敗,色交 JS=鐵則一正確取捨)。

## 四、驗證(PM 本地,全綠)

- node --check:governance-tab.js/autonomy-posture.js/canary-tab.js + tab-governance inline 全 PASS。
- 四檔 style= 各 0(canary +1 合法 §7 scoped-var);governance-tab.js 1877<2000。
- 回歸:structure/ + G0.5 = **392 passed / 5 failed**(5F=pre-existing,與 static/ 零關);零新失敗。spec-drift 2/2。
- 零 Python/Rust 觸碰(diff 中 .py 全屬兄弟 auth/alr/cost_gate session)。

## 五、記錄

E1a batch 7b 完整完成未中斷(7a 三次中斷後首個乾淨大批);7a 的裸屬性 HIGH 教訓被 E1a 主動內化(自查 0)+E2 復現檢查(0),證中斷教訓已沉澱進流程。
