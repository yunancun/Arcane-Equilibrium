# Soak 派單邊界圍欄 + Post-Approval Drift Gate 設計正本(2026-07-02)

**狀態**:operator 已裁決方向(#1 修 soak 自斷糧道不觸 guarding boundary/#2 放寬 drift 判準),設計經 3 獨立 PA 案 × 3 鏡頭評審團(正確性+數據完整性/E3 邊界/治理+精簡)合成。評審原始記錄:`docs/CCAgentWorkSpace/PA/workspace/2026-07-02--soak_fix_design_panel_raw.json`。
**背景**(已確診,見 `docs/CCAgentWorkSpace/Operator/2026-07-02--soak_disarm_flash_dip_reenable_operator_decision.md`):soak isolation guard(c5ca8a541)在 pre-risk 攔所有 Open intent,餓死 bounded probe writer 唯一候選 feed(exchange gate cost_gate reject),soak 空轉 5 天無退出條件;每日 13-17 萬筆 identical reject verdict 洪水。**當前 runtime 已臨時解除 soak(flag=0),本設計 landed 後按新語義重新武裝。**

---

## Part 1:soak 修復 — dispatch-edge containment + envelope 同鐘(合成案)

骨架=設計1(fail-closed 最嚴)+ 設計2 的 DRY 抽取 + 設計0 的 writer 修復;評審團修正全部採納。

### 1.1 機制
1. **刪除 pre-risk guard 塊**(step_4_5_dispatch.rs:801-827):普通 Open intent 恢復流經完整 pipeline(scanner→risk→exchange gate 含 cost_gate)。cost_gate reject 重新產出 eligible RejectEvent → probe writer feed 自然恢復(事故前 1.9萬~12.9萬筆/日)。
2. **Withhold 點移到 `if gate.approved {` 分支最頂端**——**必須釘死在任何副作用之前**(exchange_seq 遞增、Approved verdict persist、persist_intent、spine lineage、tx.send、proactive_mirror_insert 全部尚未執行;評審團指出這是 [27] false-wedge 審計形狀鐵則的硬前提:被 withhold 的 intent 只能留 rejected qty=0 記錄,絕不能同時留 Approved verdict)。命中時:
   - `strategy.on_rejection(intent, reason)` 回滾 eager-mutate(QTY-ZERO-SKIP-1 先例);
   - 釋放 gate 已取得的 RouterLeaseGuard lease,**用 `LeaseOutcome::Failed`**(評審親 grep 證實 :1190/:1204 先例均為 Failed,全檔無 Cancelled;不引入新 outcome 值)+ 獨特 reason 字串 `bounded_probe_soak_isolation_withheld`;
   - 復用 record_pre_risk_rejection helper(更名 `record_undispatched_rejection`)寫 typed rejected verdict + qty=0 intent,**新常量** `bounded_probe_soak_isolation:approved_entry_withheld_at_dispatch`(與舊 pre-risk 全攔語義區分,利數據考古);
   - **不寫** decision_features 負標籤(gate 已批准,非真負樣本,防 ML 污染);
   - TickStats 新增 `soak_withheld_opens` 計數 + throttled log;`continue`。
3. **邊界更強**:dispatch 邊界是普通 Open→交易所唯一咽喉(:1110 tx.send 唯一普通 entry sender);probe writer 直送 order_dispatch_tx=被授權例外,order_link_id 帶獨特前綴可審計。未來 pre-risk 後新增旁路也逃不過本圍欄。

### 1.2 soak 窗口定義(退出條件內建,無限空轉結構性不可能)
soak 生效 = `flag OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=1(硬前提兼 kill switch)` ∧ `envelope 狀態`:
- **可讀+有效** → 圍欄武裝;緩存 `last_good_expires_ms`。
- **可讀+已過期,或 now > last_good_expires_ms** → 圍欄解除(operator 親簽的到期時刻=確定性退出;**即使 plan 檔事後被刪,last_good 緩存保證 soak 必在簽署到期時刻結束**——設計1 的硬上界,三案中最優雅的抗空轉機制)。
- **不可讀/缺檔/壞 JSON/schema 錯/從未可讀** → **fail-closed 照攔** + 節流 WARN(評審一致否決設計0 的「NotFound=確定缺席→放行」——那是 fail-open 邊,違 operator 鐵則 2)。misconfig 態(flag=1 但 envelope 從未可讀)=無限攔但方向安全,由 healthcheck 哨兵補時間上界告警(見 1.4)。
- 讀取:30s TTL 惰性緩存,僅 demo/live_demo+flag=1+遇 approved Open 時觸發讀檔。
- envelope 核心判定**從 `validate_operator_authorization` 抽出共用純函數**(設計2 的 DRY:guard 與 admission 同一實現,杜絕判準漂移;原函數改呼共用核心,行為不變)。plan 路徑解析同步抽共用(PLAN_PATH_ENV+default),杜絕雙路徑漂移。

### 1.3 伴生修復(部署阻斷級,同批必修)
**writer probe_ledger O(n²)**:writer.rs:379 每事件全量 read_ledger_rows,feed 恢復 12.9萬筆/日下自爆。修=writer task(ledger 唯一寫者)啟動讀一次,維護 in-memory Vec,append 檔案同步 push,消除重讀。附等價性測試(dedup 語義不變)。

### 1.4 verdict 洪水治理
- 源頭消除:pre-risk 每日 13-17 萬筆同 reason 雙寫隨塊刪除而消失。
- 新增寫入有界:withhold 只寫 gate.approved 倖存者(cost_gate 拒絕率 99.9%+,每日數十~數百筆)。
- healthcheck 哨兵(graft 自設計2,條件修正):「soak 武裝中但 N 小時零 probe 候選/零 admission 活動」告警;**條件不得用 probe_ledger 有無新行**(writer capture-error rows 會餵飽它使哨兵失明——評審實證),改用 admission 結果分布或 withheld/candidate 比值。

### 1.5 測試計劃(E4)
- dispatch-edge withhold 矩陣:envelope Active→無 OrderDispatchRequest+lease Failed 釋放+typed rejected verdict+qty=0 intent+無 Approved verdict 殘留;Expired/last_good 超時→放行;Indeterminate(壞檔/缺檔)→攔;flag=0→全滅;live/paper 模式恆不攔(既有 :151-158 矩陣保留)。
- feed 恢復釘子:cost_gate reject→writer channel 收到 RejectEvent。
- soak_envelope_state 全矩陣(有效/過期/缺 auth/缺檔/壞 JSON/schema 錯/staleness/未來時間戳/last_good 緩存行為)。
- [27] 審計形狀:withhold 路徑零 Approved verdict、零 decision_features 負標籤。

### 1.6 部署與回滾
Mac 實作→E2 對抗審→E4 回歸→push→Linux pull+`restart_all.sh --engine-only --rebuild --keep-auth`。重新武裝 soak 前置:新 envelope 簽署(見 Part 3)。回滾=revert commit+rebuild(env flag 不變,当前=0)。

---

## Part 2:Post-Approval Drift Gate(operator 已批准放寬方向)

**v734 source-impact guard 為何無效**:①從未接線到消費點(定位是 E3/BB review 前置輸入,批准後 final check 仍是 exact-sha 等式);②即使接線也必 BLOCKED(`.codex/` 在其 POLICY_SENSITIVE_PREFIXES,而 codex 每個 commit 都改 `.codex/MEMORY.md`)。

**新判準**(deny-by-default,詳規格見 PA panel raw json 之 drift_design):批准延續 ⇔ approved_head 是 origin/main ancestor ∧ `git diff --name-status approved_head..origin/main` 每個 path(rename 兩端都算)命中豁免集 ∧ 無 binary/submodule 歧義 ∧ packet sha256 相符且內含 `post_approval_drift_policy: "docs_tests_codex_exempt_v1"`。分類順序:
1. **hard-deny**(觸即 ROTATED,即使 .md):路徑含 `/src/` 的 rust 檔、`settings/`、`sql/`、`.github/`、`docker*/`、`scripts/`、`tools/`、`venvs/`、`.claude/`、`.env*`、`*.toml`、`*.lock`、`requirements*.txt`、`package*.json`、`pytest.ini`、`skills-lock.json`。
2. **test 豁免**:精確目錄 segment `tests/`(rust integration/program_code/helper_scripts/頂層)且不在 1 內。
3. **docs/記憶豁免**:`docs/**`、`.codex/**`、頂層 `*.md`、`helper_scripts/SCRIPT_INDEX.md`。
4. **默認**:其餘一切=ROTATED。

**落地**:新腳本 `helper_scripts/research/cost_gate_learning_lane/standing_envelope_post_approval_drift_gate.py`(schema v1,CLI 全參數必填無默認寬鬆值)+ temp-git 測試 + SCRIPT_INDEX 登記 + TODO refresh SOP Step 1 改兩段式(sha 相等直接 pass;前進則跑 gate,EXEMPT 才續)+ **下輪 E3/BB packet 起新增 `post_approval_drift_policy` 字段使放寬條款明示納入批准內容**(堵「批准 exact packet、PM 事後單方放寬」的治理洞)。

---

## Part 3:envelope answers 全 false = DESIGN(調查結論,非 bug)

生成器硬編碼 false(`standing_demo_authorization_refresh_guardrail.py:576-577` 等),且驗證器把 true 判為 contamination 直接失效——standing envelope 本來就是「損失控制包」不是「下單授權」。**真正的簽署點在下游** `bounded_probe_operator_authorization_cli.py`(typed-confirm+operator_id 一致+cap≤standing cap+TTL≤24h),簽出的 bounded auth 才有 order_authority_granted=true。operator 需拍:候選確認、簽 bounded authorize、TTL 與續簽方式(06-27 教訓:bounded TTL ~11h 短於 72h soak 期,中途過期無人能續)。

---

## 實作派工(待啟)
- **IMPL-A(Rust,本設計 Part 1)**:E1 實作→E2 對抗審→E4 回歸→PM 收。改動面 ~6 檔 ~250 行+~290 行測試。
- **IMPL-B(Python,Part 2)**:E1 實作 drift gate+測試→E2→E4。與 IMPL-A 無依賴,可並行。
- Part 3 無代碼改動,operator 簽署動作。
