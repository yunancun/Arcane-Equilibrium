# GUI 大改 P0.2 批次 7a — risk 群 inline style 清理

> **記錄狀態**:batch 7(governance/risk,521 styles)因過大拆為 7a-risk / 7b-governance。
> 7a 的 E1a 實作 agent 完成機械清理後**被中斷,未寫報告**;本報告由主會話(PM)依
> 「已落工作樹 diff + E2 對抗審查 + PM 本地驗證」重建。日期 2026-07-10。
> 規格正本 `docs/execution_plan/gui_redesign/design/05_utilities.md`。

## 一、度量

| 檔 | 前 | 後 |
|---|---|---|
| tab-risk.html | 209 | **0** |
| risk-tab.js | 10 | **0** |
| **合計** | **219** | **0** |

零新 utility(oc-utilities.css/§4 未動);頁內 `<style>` 塊新增 `rc-*`/`is-active`/`etab-btn`/`rtab-nav-btn` 等組件類(語義 token)。governance.js NO-OP(risk-tab 載入但未動)。

## 二、E2 對抗審查(APPROVE→PASS to E4;1 HIGH 由 E2 修復)

E1a 中斷無自報,E2 補完整對抗層:
- **鐵則一(JS 軸殘留=0)完整**:每個移除 inline display/opacity/width 的元素,其 JS 寫點全數同批 classList/setProperty 化,全 static/ 殘留=0。餘留 `.style.*` 均為 pre-existing 動態寫點且無同屬性 !important utility 衝突(in-take-profit opacity/etab-paper display/rc-engine-badge bg 等,逐一核)。**中斷最高風險(半轉致靜默隱藏/永暗)未發生**。
- **鐵則二 className-wipe**:4 個每刷新 `className=` 整串重寫的 chip(r-engine-status/h0-status/dr-status/engine-risk-loaded-badge)走 `#id` 選擇器抗抹除;rc-engine-badge 非 wipe(querySelectorAll 依賴類存活),fs-micro/ml-auto 存活。
- **HIGH-1(中斷「改一半」,E2 已修)**:18 個 width token 被寫成裸 HTML 屬性 `<input class="oc-input" oc-input--num ...>`(瀏覽器當 boolean 空屬性→class 不生效),inline width 已移除→18 個風控 config 輸入失去限寬渲染全寬破版;`grep style=`=0 掩蓋此問題。E2 改為 `class="oc-input oc-input--num"`(×15)+`rc-input-wide`(×3),PM 覆核:0 裸屬性殘留、precedence(!important/頁內塊 source-order)正確。
- 色映射 compat alias 等值(--red→--neg/--yellow→--warn 無變色);`#1a1a1a`/`#fff` verbatim from HEAD 帶 P0.4 註記;三紅無第四紅;live 面 --red→--live(canon 9)。
- **風控邏輯零觸碰**:無 fetch/endpoint/target_level/reason/auth/de-escalation/事件改動;submitRiskOverride/live-confirm gate/override-button gate 全保留。

## 三、PM 裁決(LOW/for-PA)

E2 LOW:7 張卡(P0/P1/P2 + Position/H0/auto-adjust/AI-consult)的 `border-color:rgba(...)` 語義色框被移除→回落 .oc-card 中性框。**PM 裁決 ACCEPT**:border tint 是 h3 標題色(t-neg/t-warn 仍在)的裝飾性重複,移除符合 canon 1(色=數據 claim 非 chrome),與 --blue/category-tag 中性化先例一致;優先級信號由標題色承載未丟失。**交 A3 Phase 0 UX 審**(標題色是否足夠 scannable),不 revert。

## 四、驗證(PM 本地,全綠)

- node --check:risk-tab.js + tab-risk 2 inline scripts 全 PASS(E2 修後重驗)。
- tag 平衡 OK;三連 link 順序 OK;spec-drift 2/2;G0.5 static-gui guard 綠。
- 回歸:structure/ + G0.5 = **406 passed / 5 failed**(5F=pre-existing stock_etf_ipc/stable_boundary_docs/strategy_blocked_symbols,與 static/ 零關);零新失敗。
- 新增行零裸 hex(除 #1a1a1a/#fff verbatim P0.4);tab-risk style= 殘留=0。
- 零 Python/Rust 觸碰。

## 五、A3 必審 / 待辦

1. 7 張卡中性框後 P0/P1/P2 優先級 scannability(標題色-only)。
2. live 面 --red→--live 熱紅雙主題觀感。
3. pre-existing `var(--bg-card)` 懸空(P0.4,未修)。
4. **7b-governance 待做**(tab-governance 213/governance-tab.js 75/autonomy-posture.js 7/canary-tab.js 7=302)。

## 六、記錄異常

E1a agent 第三次「報告階段前後中斷」(batch 2 spend-limit / batch 3 401 / 7a user-interrupt-during-tool);三次主體工作均落樹,E2 窮舉補 E1a 缺失自報,PM 依 diff+E2+回歸收尾。7a 的中斷尤其驗證了「E2 窮舉不可省」——HIGH-1(裸屬性破版)是 grep style= 度量盲區,只有 E2 逐元素親證才抓得到。
