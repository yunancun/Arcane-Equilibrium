# E3 — P2-6 GUI fake-success 全量掃(93 endpoints / handler 級) · 2026-07-04

範圍：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/*`(GUI 寫入面)
      × 對應 Python handler 實現。判準與 A3 共用。
基準：Mac dev repo(多 session 髒樹);read-only 源碼級,**未跑 runtime**。
方法：從 GUI 前端枚舉所有 POST/PUT/DELETE 呼叫(~69 call sites → ~60 distinct endpoints,計 method 變體與 family 子路由約對應歷史 93 計數),
      **真讀 handler 實現 + 前端 response-handling**,非只看路由名。

## 判準(fake-success 四分類)
- **real**：後端真做事 + 前端成功語義與後端 effect 一致。
- **fake**：後端沒做事/no-op 卻回 ok:true,前端顯「已完成」。
- **partial**：後端部分做事(partial_failure/pending)但回 ok:true 且前端顯完整成功。
- **degraded-honest**：後端降級但前端措辭誠實反映(如「指令已發送」而非「已完成」)。

## 摘要
總計 **0 CRITICAL / 0 HIGH / 3 MEDIUM / 4 LOW** + 大量 real/honest。
無「直接繞過執行授權/風控」的漏洞(所有 fake 皆誠實性/UX 面,非授權繞過)。
最強一例(risk/override)安全方向 fail-safe(等級停在較安全側),但誠實性違規確認。

排除(P1-9 已另排,本輪不重掃)：緊急停止=`/live/session/stop` 同 endpoint(tab-live.js:1065/1093)、mode-tag 硬編碼(console.html:183)。

---

## 全量 verdict 表(按 live 操作面優先排序)

| # | Endpoint | 前端錨點 | 後端錨點 | verdict | 證據/攻擊(信任)路徑 |
|---|---|---|---|---|---|
| 1 | POST /live/session/start | tab-live.js:1034 | live_session_endpoints | **real** | classifyLiveMutation(common.js:655)判 partial/rust_synced;未授權顯常駐橫幅 |
| 2 | POST /live/session/stop(停止+緊急停止共用) | tab-live.js:1065/1093 | live_session_endpoints | **real**(P1-9 已排) | 兩處皆走 classifyLiveMutation;殘留風險常駐橫幅 |
| 3 | POST /live/close-all-positions | tab-live.js:1123 | live_session_account_routes.py:653 | **real** | classifyLiveMutation;殘留顯紅 blocking |
| 4 | POST /live/positions/{symbol}/close | tab-live.js:1164/1179 | live_session_account_routes.py:558 | **partial(LOW)** | 後端 :645 回 `closed:True` 不檢 IPC result(dust 拒單仍 True);FE 措辭「指令已發送」誠實→FE 側 degraded-honest,後端 payload 為問題面 |
| 5 | POST /strategy/demo/close-all-positions | tab-demo.html:1338 | strategy_ai_routes.py:694 | **FAKE-2(MEDIUM)** | 後端誠實算 partial_failure/closed_all(:724-745);**FE 只 `if(d&&d.data)`→綠 ✓ success,忽略 partial_failure** → 殘留 demo 倉位不曝光。live tab 有 classifyLiveMutation,demo tab 沒有 |
| 6 | POST /strategy/demo/positions/{symbol}/close | tab-demo.html:1368/1384 | strategy_ai_routes.py:612 | **degraded-honest** | FE「指令已發送」措辭誠實 |
| 7 | POST /strategy/demo/session/{action} | tab-demo.html:1259 | strategy_ai_routes.py | real(未深讀 handler 逐分支;session 控制) | — |
| 8 | POST /paper/close-all-positions | tab-paper.html:597 | paper_trading_routes.py:843 | **FAKE-3(MEDIUM,低實錢)** | **後端 :858 無條件回「所有 Paper 持倉已平」不檢 result**;FE 顯綠 success。雙側 fake,paper 無真錢故降 MEDIUM |
| 9 | POST /paper/positions/{symbol}/close | tab-paper.html:579 | paper_trading_routes.py:871 | 未深讀逐分支(結構同 demo close) | — |
| 10 | POST /paper/session/start\|stop\|pause\|resume | app-paper.js:46-52; tab-system.html:654/656 | paper_trading_routes | real(session 控制) | — |
| 11 | POST /paper/session/stop-all | tab-paper.html:404 | paper_trading_routes | 未深讀 | — |
| 12 | POST /paper/risk/reset-cooldown | risk-tab.js:588 | risk_routes.py:546 | **real**(FE `if(d)` 略粗) | 走 Rust IPC clear_consecutive_losses,raise on fail;FE 未讀 result 但 paper-only |
| 13 | POST /paper/risk/unhalt-session | risk-tab.js:595 | risk_routes.py:1027 | real(同上) | — |
| 14 | POST /paper/layer2/trigger | risk-tab.js:548; tab-ai.html:541 | layer2_routes | **real** | FE 顯真實 result 文本 |
| 15 | POST /paper/layer2/config | tab-ai.html:822/951 | layer2_routes | 未深讀 handler(config 寫) | — |
| 16 | DELETE /paper/layer2/providers/{provider} | tab-ai.html:903 | layer2_routes | 未深讀 | — |
| 17 | **POST /governance/risk/override** | risk-tab.js:82; governance.js:78→governance-tab.js:480 | governance_routes.py:846 | **FAKE-1(MEDIUM,anchored 確認)** | 兩條 no-op 回 ok:true 但 FE 皆顯「已降級」綠 success:(a):918 `de_escalation_pending_approval`(零變更);(b):929 `_risk_governor_sm is None`→跳過 escalate_to 仍回 `override_applied`。詳見下方 |
| 18 | POST /governance/auth/request | governance.js:64 | governance_routes | real(狀態機 DRAFT→PENDING) | — |
| 19 | POST /governance/auth/approve | governance-tab.js:457 | governance_routes | real(auth SM) | — |
| 20 | POST /governance/reconcile | governance-tab.js:497 | governance_routes.py:1076 | **real** | 回真 report,`report.ok=false`→error();FE 讀 d.ok |
| 21 | POST /governance/health-check | governance.js:122 | governance_extended_routes.py:391 | **real**(讀取型) | 回真 SM 狀態 |
| 22 | POST /governance/autonomy-level/switch | governance.js:152; autonomy-posture.js:226 | governance_autonomy_service.py:598 | **real** | TOTP backend down→raise HTTPException(fail-closed) |
| 23 | POST /governance/learning-tier/promote | governance-tab.js:1009 | governance_extended_routes.py:316 | **partial(LOW)** | :352 回 `promoted: result is not None`;若 gate 拒(promoted:false)仍 HTTP200 ok:true,FE:1010 顯「submitted」success(措辭軟但未反映 no-op) |
| 24 | POST /governance/recovery/{id}/approve | governance-tab.js:1803 | governance_routes.py:1162 | **real** | approval None→error();req None→404 |
| 25 | POST /governance/audit/approve/{id} | governance.js:188 | governance_routes | real(audit SM) | — |
| 26 | POST /governance/audit/reject/{id} | governance.js:193 | governance_routes | real | — |
| 27 | POST /governance/audit/dismiss-all | governance.js:198 | governance_routes | 未深讀(批量 approve) | — |
| 28 | POST /governance/canary/manual_promote | canary-tab.js:389 | governance_canary_routes.py:394 | **real** | fail-closed 5-step:operator role + payload 校驗 + lease(60s,SHADOW_BYPASS 拒 409/423)+ audit row + release |
| 29 | POST /governance/paper-live-gate/evaluate | governance-tab.js:874 | governance_extended_routes | 未深讀(evaluate 讀取型可能) | — |
| 30 | POST /strategy/create | tab-strategy.html:310 | strategy_ai_routes/write | 未深讀 handler | — |
| 31 | DELETE /strategy/{name} | tab-strategy.html:326/337 | strategy_write_routes | 未深讀 | — |
| 32 | POST /strategy/dynamic-risk/toggle | risk-tab.js:960 | strategy_write_routes.py:162 | **partial(LOW)** | 後端 :215 IPC 未 raise 即回 success envelope,不檢 `resp.ok`;FE `if(d)`→「已啟用」success。live 分支有 5-gate(:187),demo/paper 無 token |
| 33 | POST /settings/api-key/{slot} | tab-settings.html:1334 | settings_routes | **real** | FE 檢 `d.saved`;經 Bybit 真驗證 |
| 34 | POST /settings/paper-engine | tab-settings.html:1124 | settings_routes.py:1514 | **partial(LOW)** | FE:1126 顯「已啟用」即使 `data.restart_required=true`(config 存了 runtime 未生效);status 行有另顯 restart_required |
| 35 | POST /control/product-family/{family}/config | tab-settings.html:1052; app-actions.js:116 | control_legacy_routes.py:366 | **real/honest** | Python STORE;summarizeActionResult(app.js:279)顯真實 applied_changes |
| 36 | POST /control/demo/validate\|arm | app-actions.js:87/104; tab-settings.html:777 | control_legacy_routes.py:200/218 | **honest** | summarizeActionResult 明說「仍未放開執行/moved closer not open」 |
| 37 | POST /control/safe-recheck-bundle | app-actions.js:89; tab-settings.html:812 | control_legacy_routes.py:272 | **honest** | 同上,「no authority directly opened」 |
| 38 | POST /system/scheduled-restart | tab-settings.html:723 | control_legacy_routes.py:89 | **real** | FE:730 檢 `d.action_result==='scheduled'`,顯真 closedN/skippedN |
| 39 | POST /input/config-change | app-actions.js:91/232/250; tab-system.html:737 | control_legacy_routes.py:346 | **honest** | Python STORE + envelope action_result |
| 40 | POST /input/cost | app-actions.js:182; tab-settings.html:871 | control_legacy_routes.py:292 | honest | — |
| 41 | POST /input/pnl-entry | app-actions.js:209; tab-settings.html:882 | learning_legacy_routes.py:410 | honest | — |
| 42 | POST /input/pnl-period-snapshot | app-learning.js:404 | learning_legacy_routes | honest(STORE) | — |
| 43 | POST /input/observation\|lesson\|hypothesis\|experiment | app-learning.js:229/256/282/311 | learning_legacy_routes | honest(STORE) | — |
| 44 | POST /learning/review/{id}/decide | app-review.js:176/198 | learning_records/routes | 未深讀 | — |
| 45 | POST /learning/review/{...} | tab-learning.html:207/213 | learning_legacy_routes | 未深讀 | — |
| 46 | POST /learning/auto/... | tab-learning.html:219 | learning_auto_pipeline | 未深讀 | — |
| 47 | POST /learning/experiment/{id}/complete\|approve | app-learning.js:345/383 | experiment_routes | 未深讀 | — |
| 48 | POST /learning/hypothesis/{id}/verdict | app-learning.js:330 | learning_records | 未深讀 | — |
| 49 | POST /earn/stake | earn-tab.js:530 | earn_routes.py:1097 | **real/honest** | FE 區分 `wave_d_pending`(已發出鏈路未閉)橙色 warn,非綠 ✓ |
| 50 | POST /evolution/run | tab-ai.html:1374 | evolution_routes.py:149 | **real** | FE 顯真 best_sharpe/evaluated_combinations |
| 51 | POST /ai_budget/config | risk-tab.js:1086 | ai_budget_routes | **real** | FE 檢 `r.ok`,非 ok throw |
| 52 | POST /replay/full-chain/coverage\|run | app-paper.js:1319/1326 | replay_full_chain_routes | 未深讀(replay 計算型) | — |
| 53 | POST /replay/experiments/register | app-paper.js:1391 | replay_routes | 未深讀 | — |
| 54 | POST /replay/run + /run/{id}/finalize | app-paper.js:1415/1445 | replay_routes | 未深讀 | — |
| 55 | POST /replay/handoff | handoff_helper.js:636 | handoff_routes | **honest** | 404→友好降級「endpoint 待上線」,不假成功 |
| 56 | POST /auth/login | login.html:116 | auth_routes | real(登入) | — |
| 57 | POST /auth/logout | index.html:36; common.js:151 | auth_routes | real | — |

> 「未深讀」= 本輪讀了路由 + 前端 response-handling,但未逐分支追 handler 內部 no-op/partial 語義。**按全量輸出紀律列出交 PM/operator 裁決是否補掃**;非判 clean。

---

## MEDIUM 詳述

### [FAKE-1] risk/override no-op 回 ok:true 顯「已降級」success(anchored 確認)
**位置**：`governance_routes.py:846` `override_risk_level`
- **分支 A(:915-926)**：de-escalation 未過 `_check_de_escalation_gate`(有 pending 審批)→回
  `GovernanceResponse.success(data={status:"de_escalation_pending_approval"}, message="de_escalation_pending_approval")`。**ok:true 但風控等級零變更**。
- **分支 B(:929)**：`if hub._risk_governor_sm:` 為 falsy(SM 未初始化)→**整個 escalate_to 被跳過**,直落 :946 回
  `success(data={status:"override_applied"})`。**回 override_applied 但實際沒調用 SM**。
**前端**：`risk-tab.js:82` 與 `governance-tab.js:480` 皆 `if(d && d.ok){ ocToast('已降級/de-escalated','success') }`。
  兩前端都**不讀 `data.status`**,故 pending / SM-missing no-op 皆顯綠色「已降級」。
**攻擊/信任路徑**：operator 點降級→系統顯「已降級」success→實際等級停在原(較高)值或僅 pending 審批。
**嚴重性判定 MEDIUM(非 HIGH)**：安全方向 **fail-safe**——等級停留在較嚴格側,不會意外放鬆風控閘門;
  故無「繞過風控」硬後果。但符合 fake-success 判準(no-op 顯完整成功),誠實性違規。confidence=HIGH。
**修法**：
- 後端:分支 A 改用 `GovernanceResponse` 帶明確 `pending` 語義(建議 `ok:true` 但 `data.applied=false`+`data.status`),
  分支 B 若 `_risk_governor_sm is None` 應回 503/error(不可宣告 override_applied)。
- 前端:兩 caller 改讀 `data.status`——`de_escalation_pending_approval`→顯「待審批」(warn)、`override_applied`→綠、
  其餘→error。

### [FAKE-2] demo close-all 忽略後端 partial_failure 顯綠 success
**位置**：後端 `strategy_ai_routes.py:694`(誠實,已算 `partial_failure`/`closed_all`/`status`/`orphan_sweep`,:724-745);
  前端 `tab-demo.html:1338` `doDemoCloseAll`。
**問題**：FE 只 `if(d && d.data){ ocToast('✓ '+msg,'success') }`——**不讀 `data.partial_failure`/`data.closed_all`**。
  後端 message 於 partial 時雖含「部分失敗」字樣,但 severity 仍是綠色 `success` + `✓`,操作員易錯過。
**對比**：live tab 用 `classifyLiveMutation`(common.js:655)專門接住 partial_failure/closed_all/rust_synced 並顯紅 blocking;
  demo/paper tab **沒接**。
**嚴重性 MEDIUM**：demo=live-grade rigor(operator 政策),demo 是真 Bybit demo 下單;殘留倉位顯綠成功=誠實性 gap。confidence=HIGH。
**修法**：demo close-all(及 demo/paper 單倉平倉)前端改走 `classifyLiveMutation` 同款判讀,partial→顯紅殘留橫幅。

### [FAKE-3] paper close-all 後端不檢 result 無條件宣告「已平」
**位置**：`paper_trading_routes.py:843`。IPC `close_all_positions` 未 raise 即回
  `message:"所有 Paper 持倉已平"`,**不檢 `result` 內是否部分失敗/殘留**(對比 demo close-all :724 有算)。
  前端 tab-paper.html:597 顯綠 success。
**嚴重性 MEDIUM(低實錢)**：paper 無真錢,但雙側(後端+前端)皆 fake,語義誠實性缺失。confidence=HIGH。
**修法**：後端仿 demo close-all 計 partial_failure/closed_all(orphan sweep 可選);前端同 FAKE-2 走 classify。

---

## LOW 詳述
- **[L-1] dynamic-risk/toggle**(`strategy_write_routes.py:162`,FE risk-tab.js:960)：後端 :215 IPC 未 raise 即回 success envelope,不檢 `resp.ok`;FE `if(d)`→success。live 分支有完整 5-gate(:187-201),demo/paper 無 token 但也無 result 校驗。修:後端讀 `resp` 成功旗標;FE 讀 `data.ipc_response`。
- **[L-2] settings/paper-engine**(`settings_routes.py:1514`,FE tab-settings.html:1124)：FE:1126 顯「Paper Engine 已啟用」即使 `data.restart_required=true`(config 存了但 runtime 未生效)。status 行(:1113)另顯 restart_required 但 toast 誤導。修:toast 改讀 `data.runtime_enabled`,restart_required 時顯「已保存,需重啟生效」。
- **[L-3] learning-tier/promote**(`governance_extended_routes.py:316`)：:352 回 `promoted:false` 時仍 ok:true,FE governance-tab.js:1010 顯「submitted」success(措辭軟)。修:FE 讀 `data.promoted`,false→顯「未晉升(不符資格)」。
- **[L-4] live/positions/{symbol}/close 後端 closed:True**(`live_session_account_routes.py:645`)：IPC 未 raise 即回 `closed:True`,不檢 IPC result(dust 拒單場景)。FE 措辭「指令已發送」誠實故 FE 側無害;後端 payload `closed:True` 為潛在下游誤信面。修:後端 `closed` 改讀 IPC result 真值,或改欄名 `dispatched:True`。

---

## real/honest 正面樣本(供 A3/PM 對照,確認多數寫入面誠實)
- **live 操作面全部 hardened**:session start/stop/close-all + emergency 皆走 `classifyLiveMutation`,partial/未授權顯常駐橫幅(P1-04 修果)。
- **earn/stake**:區分 `wave_d_pending`(已發出鏈路未閉)橙色 warn,不與完整成功混淆——**fake-success 防範模範**。
- **scheduled-restart**:FE 檢 `action_result==='scheduled'`,顯真 closed/skipped 計數。
- **canary/manual_promote**:fail-closed 5-step(operator role + lease 60s + SHADOW_BYPASS 拒 + audit row + release)。
- **reconcile / recovery approve / autonomy switch**:皆 error()/raise on 失敗,前端誠實反映。
- **/control/* + /input/* Python STORE**:summarizeActionResult 明說「moved closer, execution still not open / no authority opened」——正確傳達控制平面≠放權(呼應 2026-04-08 盤點:P 類多為合法 STORE 非 fake,本輪確認結論仍成立)。

---

## 給 E1a/E1 批量修 spec

1. **共用 helper 統一化(E1a)**：把 live tab 的 `classifyLiveMutation`(common.js:655)提升為所有平倉/mutation 面的統一判讀器;
   demo close-all(tab-demo.html:1338)、paper close-all(tab-paper.html:597)、demo/paper 單倉平倉改走它。
   驗收:partial_failure/closed_all=false/rust_synced=false 任一→顯紅殘留橫幅(非綠 ✓)。node --check 過。
2. **risk/override 語義修(E1a 前端 + E1 後端)**：
   - 後端 `governance_routes.py:915-926`(分支A)保留 ok:true 但加 `data.applied=false`;`:929` 分支 B `_risk_governor_sm is None`→改回 503 error(不宣告 override_applied)。
   - 前端 risk-tab.js:82 + governance-tab.js:480 改讀 `data.status`/`data.applied` 區分 pending/applied/error。
   驗收:pending 顯「待審批」warn、SM-missing 顯 error、真 applied 才綠。
3. **paper close-all 後端補 partial(E1)**：`paper_trading_routes.py:843` 仿 `strategy_ai_routes.py:724` 計算 partial_failure/closed_all,回結構欄。
4. **LOW 批(E1a/E1)**：dynamic-risk toggle 後端檢 resp/前端讀 ipc_response;paper-engine toast 讀 runtime_enabled;learning-tier promote FE 讀 promoted;live single-close 後端 closed 讀真值或改欄名 dispatched。
5. **未深讀補掃(交 PM 決策)**：表中 15+「未深讀」endpoint(strategy create/delete、paper layer2 config、replay 系列、learning review/experiment/hypothesis)本輪未逐分支追 handler no-op 語義;若 PM 要求 100% 覆蓋,派後續窄掃。

## 硬約束核對
- 未動任何業務代碼(read-only)。
- 無 secret 洩漏(本掃無觸 credential 面)。
- 5 hard gate 未觸(所有 fake 皆誠實性/UX,非授權繞過);risk/override 安全方向 fail-safe。
- API withdraw permission 面未涉。

E3 AUDIT DONE: 0 CRITICAL / 0 HIGH / 3 MEDIUM / 4 LOW · report: docs/CCAgentWorkSpace/E3/workspace/reports/2026-07-04--gui_fake_success_full_scan_p26.md
