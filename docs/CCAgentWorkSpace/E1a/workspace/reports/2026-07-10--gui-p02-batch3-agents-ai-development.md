# GUI 大改 P0.2 批次 3 — agents/ai/development/phase4 inline style 清理

> **記錄狀態說明**:E1a 實作 agent 完成全部機械清理後,在**寫本報告前撞 401 auth 中斷**,未及自報。
> 本報告由主會話(PM)依「已落工作樹的 diff + E2 對抗審查結果 + PM 本地驗證」重建,保審計連續性。
> 日期 2026-07-10;規格正本 `docs/execution_plan/gui_redesign/design/05_utilities.md`。

## 一、範圍與度量

| 檔 | 前 | 後 |
|---|---|---|
| tab-agents.html | 30 | **0** |
| tab-ai.html | 129 | **0** |
| tab-development.html | 11 | **0** |
| tab-phase4.html | 0 | **0**(NO-OP,確認不在 diffstat)|
| js/agent-tracker.js | 59 | **0** |
| js/openclaw-agent-control.js | 3 | **0** |
| **合計** | **232** | **0** |

oc-utilities.css:annex(§B)append-only 追加 `.oc-input--num{width:80px!important}`(規格 §5.4 裁決,tab-ai 7 個數字欄位消費;!important 因 `.oc-input` 寬度由 `ocInjectBaseCSS()` 運行時注入後載勝出,定寬修飾須壓回;帶 `P0.4: 併入組件層` 註記)。§4 fence 未動 → spec-drift guard 綠。

## 二、E2 對抗審查(af6bc92c8,APPROVE-WITH-NITS,0 blocker)

E2 因無 E1a 自報,全程親證:
- **鐵則一(JS 軸殘留=0)窮舉全綠**:`hidden` 化元素僅 `setLoadingState`/`_openclawSetState` 的 loading/empty/error/data 殼(agent-roster/feed/budget/shadow-live/governance、openclaw-control-*);markup 已配對 `class="hidden …"`(§3.3 引理成立),全 static/ 對這些 id 的 `.style.display` 殘留寫點=0。`at-budget-fill`(`.style.width`)、`evo-dot`(`.style.background`)掛非-!important 頁內類,JS inline 勝出無壓死。
- **鐵則二(className-wipe)窮舉全綠**:新掛 utility 只落在 `ocSetText`(改 textContent,class 存活)或 `innerHTML` 整段重渲染;唯一 `className` 整串重寫又需樣式的 `exp-status-badge` 正確走 `#exp-status-badge` id 選擇器(不隨 className 抹除)。
- 收斂全落規格 §5;三紅紀律無第四紅(--red→--neg / --yellow→--warn / 'green'→--pos);gradient 四色 verbatim 核對 HEAD agent-tracker.js 逐值相符;`#21262d→--border-subtle` 已 token 化。
- E2 透明記錄一個自撤回誤報(`.subtitle` 字號/色由 `ocInjectBaseCSS()` 注入供給,渲染正確)。

## 三、LOW nit 修復(PM apply)

E2 findings 唯一 LOW:tab-ai.html 4 個標籤越界去 CJK 前空格(`Tier 2 供應商`→`Tier 2供應商` 等,非 style→class 範圍,違 surgical-change)。PM 已還原 4 空格(`Tier 2 供應商`/`Tier 2 模型`/`Tier 3 供應商`/`Tier 3 模型`),批次回歸純機械。

## 四、驗證(PM 本地,全綠)

- `node --check`:agent-tracker.js/openclaw-agent-control.js + 三 HTML inline script 抽取全 PASS(nit 修復後 tab-ai 重驗)。
- spec-drift guard 2/2;root-fork guard(含在 structure/);G0.5 25/25。
- 回歸:`tests/structure/` + G0.5 = **406 passed / 5 failed**,5F=已記錄 pre-existing(stock_etf_ipc split×2 / ipc_tests / stable_boundary_docs / strategy_blocked_symbols,全掃 Rust/docs,與 static/ HTML 零關);零新失敗。
- 三 HTML tag 平衡 OK;三連 link(tokens→compat→utilities)順序 OK;新增 inline style==0;裸 hex 僅 4 個 gradient(verbatim relocation,P0.4 註記)。
- 零 Python/Rust 觸碰(git diff --stat 親證)。

## 五、A3 必審項(交 Phase 0 UX 全審)

- agent-card live/shadow gradient 底色(palette 外色,P0.4 待 token 化)在玄夜/帛晝雙主題觀感。
- tab-ai 降級 Tier 2/3 面板紅/黃語義色 → --neg/--warn 後的層級感。
- `.oc-input--num` 定寬數字欄位對齊。

## 六、記錄異常

E1a agent 兩次不同故障(spend-limit 於批次 2、401 auth 於批次 3)均在**寫報告階段**中斷,主體工作已落樹。教訓:大批次應在實作主體完成後即時 checkpoint,報告與驗證分離;PM 依 diff+E2+本地回歸可完成收尾,但 E1a 自報的鐵則自查表缺失由 E2 窮舉補上(本批 E2 因此做了比常規更重的親證)。
