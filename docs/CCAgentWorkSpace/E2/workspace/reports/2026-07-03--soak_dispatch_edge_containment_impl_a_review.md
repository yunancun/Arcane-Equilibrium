# E2 對抗審查 — soak dispatch-edge containment(IMPL-A / Part 1)· 2026-07-03

- 審查對象:工作樹未 commit 改動 vs HEAD=`2a012deeb`(10 檔,+1051/−112,含新檔 `demo_learning_lane_soak_gate.rs` 307 行)
- 設計正本:`docs/execution_plan/2026-07-02--soak_dispatch_edge_containment_and_drift_gate_design.md` Part 1
- E1 報告:`docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-03--soak_dispatch_edge_containment_impl_a.md`
- 測試環境:Mac(cargo 1.95.0,toolchain 直呼——`~/.cargo/bin/cargo` symlink 損壞與本審無關)

## 裁決:RETURN_TO_E1(1 MAJOR-設計前提級 + 1 MAJOR-測試 bite + 2 LOW;withhold 核心機制本身逐行驗證正確)

---

## §5 multi-session race check:5/5 PASS

- 5a:fetch 後 HEAD==origin/main==`2a012deeb`,無 sibling 衝突;時間窗內 push 全為 stock ETF test-guard 系列(file scope 零重疊)。
- 5b:unstaged rust 檔 = 任務 scope 10 檔精確吻合;並行 session 檔(helper_scripts/SCRIPT_INDEX/TODO/memory/E1+E2 memory.md)按派工指示零觸碰、零評論。
- 5c:4 個 stash 全 pre-existing(2026-05/06 era),未動。
- 5d:N/A(未 commit)。
- 5e:審查結束前重 fetch,origin/main 無新 commit。
- mutation 探針(見 F2)以 scratchpad backup cp 還原,`git diff --stat` 恢復 +79/−32 與初審一致,無 MUTATION 殘留(grep 證)。

## 測試親跑(不採信自報)

- `cargo test -p openclaw_engine --lib`:**4254 passed / 0 failed / 1 ignored** — 與 E1 宣稱逐位一致。
- `cargo test -p openclaw_engine`(全套 lib+integration+bins):**exit 0 全綠**(tail 截斷僅存後 19 target,exit code 為全 target 綠的決定性證據)。
- soak filter 25 測全綠;mutation 輪見 F2。

---

## Findings

### F1(MAJOR / confidence HIGH)writer in-memory cache 盲於外部 ledger 寫者 —「唯一寫者」設計前提不成立

**位置**:`demo_learning_lane_writer.rs:263-271`(啟動讀一次)+ `:294`(admission 只讀 cache)。

**前提出處**:設計 §1.3 + panel raw json(`2026-07-02--soak_fix_design_panel_raw.json` 內文:「writer task 是 ledger 唯一寫者的前提使其安全」)。E1 忠實按設計實作——**此為設計前提錯誤,非 E1 私自偏離**,但 E2 必須擋下。

**前提破裂證據鏈(§3.10 caller-proof)**:
1. cron `helper_scripts/cron/cost_gate_learning_lane_cron.sh:5,17-18,28`:`OPENCLAW_DATA_DIR=/tmp/openclaw`,`LEDGER=$DATA/cost_gate_learning_lane/probe_ledger.jsonl` —— 與 engine writer(`main.rs:1028-1030` 同 env 同默認)**同一檔案**。
2. cron 默認開啟的外部寫入:`:102 APPEND_MATERIALIZED_REJECTS 默認 1`(reject_materializer `--append-ledger`)、`:105 APPEND_OUTCOMES 默認 1`(outcome_refresh `--append-ledger`,`outcome_writer.py:340/366` 寫 `probe_outcome` / `blocked_signal_outcome` row)、`:106 RECORD_PROBE_OUTCOMES 默認 0`(soak 觀測期預期開啟以閉合 outcome loop)。另 `runtime_adapter.py:700-702` 默認同路徑且 `:793/:825` append。
3. Rust production caller chain 消費被盲行:`run_writer → build_runtime_admission_result → evaluate_probe_admission → summarize_side_cell_runtime_state`(`demo_learning_lane.rs`):
   - `:546` `record_type=="probe_outcome"` → `:581-585` auto-disable(`realized_probe_outcomes_fail_learning_threshold`,`min_failed_outcomes_to_disable=2`);
   - `:566` `record_type=="side_cell_disabled"` → manual disable(operator/Python 側 per-cell soft-kill,producer:`runtime_adapter.py:399`);
   - `:534-537` admit rows → budget/cooldown。

**失敗場景**:soak 武裝、engine 連續運行 N 天(常態)。修前語義=每事件重讀檔案,cron 每小時 append 的 `probe_outcome` 兩筆失敗結果 → 下一事件即 auto-disable 該 side-cell;operator append `side_cell_disabled` row → 立即生效。修後=cache 只含啟動快照+自寫行,**兩條 disable 路徑對運行中 engine 全盲直到重啟**;probes 繼續打到 envelope 簽署預算耗盡。另 dedup 對 materializer 行失明 → 可能寫 attempt_id 重複行(數據衛生)。

**為何非 CRITICAL**:demo-only lane;絕對單量仍受自寫 admission row 計數 + operator 親簽 `max_authorized_probe_orders` 雙重硬約束;operator 保有更強 kill switch(flag=0 / envelope 刪除=Indeterminate fail-closed)。但這是對修前語義的真實回退,且 E1 報告「dedup / 預算判定語義與修前一致」的等價性宣稱只對自寫行成立。

**修法方向(不代寫)**:cache 加 stat 級失效——記錄 last-known file len/mtime,每事件(或節流)`fs::metadata` 比對,外部增長才增量/全量重讀;攤還仍 O(1),完整保留設計「消除每事件全量重讀」目的。或 PM/operator 明文接受盲窗+把 disable 路徑遷出 ledger(需設計修訂記錄)。**建議 E1 修復時知會 PM 回寫設計正本(前提修正)。**

### F2(MAJOR / confidence HIGH,mutation 親證)withhold lease 釋放零測試 bite;報告兩處宣稱與測試不符

**位置**:`step_4_5_dispatch_tests.rs` `soak_withhold_active_envelope_blocks_dispatch_with_clean_audit_shape` 的 lease 斷言;E1 報告 §四⑤。

**mutation 實證**:整段刪除 withhold 塊的 `release_decision_lease_for_governance(...)` 呼叫 → `cargo test --lib soak` **25/25 全綠**(已還原,還原後 diff 與原改動 byte 一致)。根因:`OPENCLAW_LEASE_ROUTER_GATE_ENABLED` 默認 OFF(`governance_core.rs:205`),測試未開啟 → gate 從不取 lease → `gate.lease_id=None` → 釋放是 no-op → `governance.lease.lock().len()==0` **恆真(vacuous)**。

**為何要修**:production `restart_all.sh:569/646` 從 secrets env 顯式轉發該 flag 進 engine——prod 開啟時 withhold+lease 是真實路徑,現在零覆蓋;把釋放呼叫整段刪掉全套仍綠 = load-bearing claim 無 test bite(E2 長期教訓 #1)。

**報告不符**:§四⑤ 宣稱「測試斷言 exchange_seq 不變」——測試檔 grep 僅 :756 註釋提及,**無對應斷言**;「lease store 空」斷言如上 vacuous。

**修法**:新增(或改造)一條 withhold 測試,經 test-only setter `set_router_gate_enabled(true)`(`governance_core.rs:319`,正是為避開 env race 而存在)開啟 router gate;斷言 lease 曾被取得且 withhold 後 store 歸零 / revoke transition 出現。修後親跑「刪釋放呼叫→紅」自證。

**代碼本身裁定**:withhold 的 lease 處理**讀碼正確**——gate 成功路徑 `consume()` 移出 guard(`router.rs:1216`,Drop 不釋放),withhold 以 lease_id 釋放 `Failed`→SM revoke("execution_failed")+transition telemetry+反查表清理(`governance_core.rs:744-748`);None→no-op;`continue` 後無二次釋放。問題只在測試證據缺失。

### F3(LOW)D2 reason 順序:Rust 核心與 Python 平行實現跨語言分歧(多缺陷 envelope)

`demo_learning_lane.rs` 核心現在 expiry 檢查先於 side_cell/candidate-budget(wrapper 尾部);Python 平行判準 `runtime_adapter.py:274-296` / `bounded_probe_plan_inclusion_review.py:310-325` 保持舊序(side_cell 先於 expired)。同一多缺陷 envelope(如過期+side_cell 錯)兩實現 reason 字串不同。accept/reject 逐位等價(核心檢查集 15 條與抽取前 byte-等價,親比 `git show HEAD:` 前像)。**失敗場景**:離線 Rust-vs-Python admission 對賬腳本按 reason 字串 diff 時出噪音。修法:E1 修 F1/F2 時順帶在 Python 兩檔或 Rust 註釋補一行跨實現順序說明即可(不強制對齊邏輯)。

### F4(LOW)`plan_path_resolution_defaults_under_data_dir` 測試在外部已設 `PLAN_PATH_ENV` 時靜默降級為空測

`demo_learning_lane_writer.rs:1380-1391` `if std::env::var(PLAN_PATH_ENV).is_err()` 包裹斷言——環境已設該 var 時測試恆綠什麼都不驗。修法:持 `test_env_lock::guard()` + save/remove/restore(同檔既有範式),使斷言無條件執行。

### NOTE-1(INFO,pre-existing 非本 diff 引入)QTY-ZERO-SKIP 路徑 lease 不釋放

`step_4_5_dispatch.rs:980-994` `continue` 前無 lease 釋放(靠 ExpiryGuardian TTL 兜底),與緊鄰的新 withhold 塊(正確釋放)形成不對稱。本 diff 未觸碰該塊,不阻塞;建議登記 follow-up。

### NOTE-2(INFO)D3 writer 啟動讀失敗 fail-closed 退出:裁定接受;告警消費缺口屬 §1.4 範圍外

方向更保守(壞 ledger 下修前逐筆 capture-error 也不可能 admit),鏡像 open_writer 先例,E2 接受。但退出僅 warn log,無告警消費者——§1.4 healthcheck 哨兵(範圍外)落地時應涵蓋「writer task 已死」信號。與 F1 複合的殘餘風險(外部寫者寫入 Rust 不可 parse 行→重啟後全檔 fail)經查極低:`LedgerRecord` 全欄位 `#[serde(default)]` 無 deny_unknown_fields,Python json object 恆可 parse。

### NOTE-3(INFO)step_4_5_dispatch.rs 2130→2177(+47,超 2000 之既有文檔化例外加深)

裁定:本次接受(withhold 塊+註釋為設計核心,拆出反而割裂 [27] 上下文);E1 自報的「withhold 塊抽 free fn」留作 F1/F2 修復輪或後續 split debt,不單獨阻塞。writer.rs 1082→1391(超 800 注意線,主增測試)一併留意。

---

## 逐項核心驗證(全部親讀/親跑,非採信報告)

1. **withhold 位置鐵則:PASS**。`:890-940` 塊內 `continue` 前僅 on_rejection/lease 釋放/record_undispatched_rejection/stats+throttled log;exchange_seq(:942)、Approved verdict persist(:997)、push_display_intent(:1009)、persist_intent(:1031)、`emit_decision_feature_intent_emitted`(:1054)、spine lineage(:1084)、tx.send(:1157)、proactive_mirror_insert(:1220)全在 continue 之後不可達。features(:830)僅純組裝無 emit。`persist_strategy_signal`(:751)在 gate 前,屬既有「一切 intent 皆記 signal」形狀(pre-risk reject 同寫),非 withhold 特有殘留。[27] 審計形狀測試斷言:恰 1 筆 Rejected verdict(帶 withheld reason)+ 0 Approved + intent 全 qty=0 + total_intents=0;withhold 路徑無 decision_features 負標籤(兩個 emit 呼叫點均不在該路徑)。
2. **lease 生命週期:代碼 PASS / 測試證據 FAIL(F2)**。無 double-release、無「lease 未取得即釋放」問題(None→no-op)。
3. **fail-closed 邊界窮舉:PASS,未找到 fail-open 反例**。關鍵:`soak_envelope_state` 的 Expired 分類要求 envelope **其餘 15 項檢查全部通過**(expiry 檢查位於核心最後)→「壞 envelope 帶過期字串」= Indeterminate 照攔,不是解除;缺檔/IO 錯/壞 JSON/plan schema 錯/欄位無效/expiry 缺失或格式錯 → 全 Indeterminate;last_good 覆寫(非取 max)使 operator 重簽短窗正確收縮上界;`expires==now` 邊界兩處判定一致(分類 `<=now`→Expired;Active arm `now<expires`);flag=0 全滅、paper kind 恆不攔均 pipeline 級測試釘死;live 由 `matches!(em,"demo"|"live_demo")` 排除(既有矩陣測試保留)。
4. **時鐘與緩存:PASS**。牆鐘=授權語義正確(envelope 到期是 operator 親簽的牆鐘時刻,WS payload ts 不可作授權時鐘);replay/backtest 不經 demo/live_demo dispatch 路徑,paper 恆不攔;`saturating_sub` 防時鐘回撥 panic(回撥→沿用緩存,方向=多攔);Active 緩存到期 TTL 窗內即時解除(測試釘);TTL 30s 內檔案態變化最壞 30s 延遲且僅影響「多攔」方向,無 TOCTOU fail-open 窗口。
5. **writer O(n²) 修:自寫行等價 PASS(F1 外部行除外)**。3 條等價測試走真 `run_writer` task(同 run dedup/既有行 dedup/capture-error dedup);`read_ledger_rows` NotFound→Ok(empty) 親證,測試 `&[]` 替換等價;flush 失敗仍 push cache=只多 dedup(方向安全);parse-back 與重啟 read 同構。
6. **共用純函數抽取:PASS**。前像 vs 新核心逐條比對:15 條 candidate 無關檢查全保留、判定字面不變(`OPERATOR_AUTHORIZATION_EXPIRED_REASON` 字面 byte 同);side_cell/candidate-budget 移 wrapper 尾部;admission accept/reject 語義逐位不變;lockstep 釘子測試(同常量同分類)成立;plan 路徑單一入口(`demo_learning_lane_plan_path(_from_env)`,writer spawn 與 gate 同源,`main.rs:1028-1030` 同 env 同默認親證)。
7. **測試真實性:大部分真 bite,lease 斷言除外(F2)**。feed 恢復釘子邏輯成立(舊 pre-risk guard 在 exchange gate 前 continue → 無 RejectEvent → `writer_rx.try_recv()` 必 Err → 必紅);audit-shape 測試對「withhold 移到 persist_verdict 之後」「移到 tx.send 之後」等關鍵錯位均會紅;state 矩陣(gate 10 測+lane 7 測)覆蓋充分。
8. **E1 自報 6 位置裁決**:①副作用審計 PASS;②D2 → F3(LOW);③D3 → NOTE-2 接受;④flush-fail push → 接受(寧多 dedup);⑤test env 面 → 接受(with_soak_flag 全程持 test_env_lock,現無並行讀 flag 的 demo approved-open 測試);⑥+47 行 → NOTE-3 接受。
9. **規約面:PASS**。新注釋全中文優先(技術名詞保英文);新檔 MODULE_NOTE 完整;diff 零 `/home/ncyu`//`Users/` 硬編碼(`/tmp/openclaw` 為 main.rs 既有慣例鏡像);硬邊界 token(live_execution_allowed/execution_authority/system_mode/max_retries)零觸碰(grep 證);無 env/settings/SQL 改動;無 scope 蔓延(fast_track_reduce.rs 契約測試更新=rename 的必要伴隨,D7 成立;`WriterMsg` pub(crate) 提升+`handle_for_test` 為 cfg(test) 測試件);新 prod 代碼零 unsafe/unwrap(unwrap 全在 #[cfg(test)]);TickStats 新欄位 `#[serde(default)]` 向後相容且 Python 側零 pin(grep 證);SoakEnvelopeGate per-pipeline 欄位非全局 singleton,無登記義務。

## 退回 E1 修復清單

1. **F1**:`demo_learning_lane_writer.rs` run_writer cache 對外部寫者的失效機制(建議 stat len/mtime 比對增量重讀;或經 PM 裁決明文接受盲窗+設計正本前提修正)。附:等價性測試補一條「外部行 append 後 admission 可見」釘子。
2. **F2**:withhold+router-gate-ON 測試(`set_router_gate_enabled(true)`),證 lease 真取得→Failed 釋放→store 歸零;修正 E1 報告 §四⑤ 兩處宣稱(exchange_seq 斷言不存在/lease 斷言 vacuous)。
3. **F3**:跨實現 reason 順序分歧註記(Rust 註釋或 Python 兩檔,一行即可)。
4. **F4**:`plan_path_resolution_defaults_under_data_dir` 改持鎖 save/remove/restore,消除條件空測。

修復後回 E2 narrow re-review(限 fix delta)。

---

# Re-review(narrow,F1-F4 修復 delta)· 2026-07-03

## 裁決:APPROVE — PASS to E4(F1/F2/F3/F4 全數閉合;3 個新 LOW/NOTE 殘留,不阻塞)

範圍紀律:只審修復 delta(writer.rs +182、dispatch_tests.rs +157、lane.rs +4 註釋、F4 測試改寫);首輪已 PASS 面未重審。dispatch.rs 生產代碼修復輪 **0 改動**(diff 仍 +79/−32,親驗)。

## §5 race check(re-review 輪)

- 5a/5e:fetch 後 origin/main 前進 2 commits(`d0eeafb41` IMPL-B drift gate + `db80212f4` guard fix)——**全 Python/docs,與本 rust 10+1 檔 file scope 零重疊**(`git diff --name-only 2a012deeb..origin/main` 親驗)。HEAD 落後 origin/main 屬預期,未做任何 git 寫操作。
- 5b:working tree rust 檔集與首輪一致(10 M + 1 ??);並行 session 檔零觸碰。
- mutation 探針 2 輪均 cp backup + `cmp` byte-identical 還原親驗。

## F2 前提對抗覆核(coordinator 重點 1)= E1 主張成立,反例窮盡不存在

- `GovernanceProfile::requires_lease()` = **僅 Production**(`governance_core.rs:131-133` 親讀)。
- `acquire_lease` 開頭 `if !profile.requires_lease()` → emit 合成 BYPASS 轉移 + `return Ok(LeaseId::Bypass)`(`governance_core.rs:414-423` 親讀);`release_lease(LeaseId::Bypass)` 直接 `return Ok(())`(首輪已讀)。
- 反例窮舉:`effective_engine_mode`(`mode_state.rs:39-53`)與 `effective_governance_profile`(`mode_state.rs:87-98`)是**同一 `(pipeline_kind, endpoint_env)` 輸入對的兩個全函數**,dispatch 在同 tick 用同一 `self.pipeline_kind/self.endpoint_env` 計算兩者 → 配對結構性鎖死:em="demo"⇒(Demo,_)⇒Validation;em="live_demo"⇒(Live,非Mainnet/None)⇒Validation;Production⇔(Live,Mainnet)⇔em="live",被 withhold 的 `matches!(em,"demo"|"live_demo")` 排除;em="live_testnet" 同樣被排除。**不存在任何配置使 withhold 在 Production profile 下執行**。E1 的「行為級 bite 結構性不可得」主張正確——首輪 F2 修法的前提確實需要修正,三層替代方案是正解。
- 層②seam 測試真咬 Active 路徑:Validation core(auto-auth)+ Production profile 參數取**真 SM lease**(`lease.is_active()` + `get_live().len()==1` 前置斷言),用與 withhold 塊逐字同款的 `release_decision_lease_for_governance(...Failed, BOUNDED_PROBE_SOAK_WITHHELD_LEASE_STAGE)` 釋放,斷言 `get_live()` 空 + 全 states==REVOKED(非 CONSUMED)+ `revoke_requested` 轉移可觀測(dispatch_tests.rs:1043-1094)。未來 profile 接線若改變使真 lease 流入 withhold,釋放語義已被此測釘死。
- 層①gate-ON pipeline 測(:1000-1037):`set_router_gate_enabled_for_test(true)`(`governance_core.rs:300`)+ transition channel,斷言 withhold 語義不變 + BYPASS/`non_production_bypass` 轉移可觀測(證 lease facade 真走到)+ 零 SM 物件/零 live lease。
- 層③源碼契約(:1101-1124):span=`.should_withhold_approved_open(` 至首個 `continue;`(withhold 塊內無其他 continue,span 正確),釘 6 個必要 token。「移到 continue 後」「Failed→Cancelled」「整段刪除」均會紅。源碼契約可被塊內註釋 game,但配合層②語義釘與結構性不可達論證,覆蓋組合完備——裁定滿足「load-bearing claim 必有 test bite」紀律。
- **mutation 2 親跑**:刪除 withhold 塊 release 呼叫 → `soak_withhold_block_lease_release_contract` **紅**(精準訊息),層①與其餘 26 測綠(符合三層設計)→ cmp byte-identical 還原。
- 報告宣稱修正確認:withhold 測補真斷言 `exchange_seq==0`、expired 放行測 `exchange_seq==1`(成對);原 vacuous lease 斷言改誠實註記(:791-800),不實宣稱已消除。

## F1 stat 失效覆核(coordinator 重點 2)= 機制成立 + 釘子真咬;3 個殘留邊界列 LOW

- **機制**(writer.rs `refresh_ledger_cache_if_externally_changed`):stat(len+mtime)不等 → flush 自寫緩衝 → 全量重讀 → 重 stat。flush-before-reread 順序正確(否則自寫 buffered 行從 cache 丟失→dedup 回退)。每事件一次 `fs::metadata`(µs 級 syscall,129k/日可忽略,無節流=外部 disable 最快生效)成本裁定可接受。refresh 函數本身失敗不動 cache/快照(下一事件重試)、Err 走 capture-error 分支鏡像修前語義——函數層面正確。
- **mtime 粒度**:len 比對抓 append/截斷(外部寫者現實全為 append);「同秒同長度改寫」病態案例接受聲明成立(APFS/ext4 mtime ns 級,實際窗口更小)。
- **釘子測試**真 task 級(run_writer 同 run:事件A落盤→外部 append `side_cell_disabled`→事件B admission 判 SIDE_CELL_DISABLED/manual_disable),deterministic(len 必變,不依賴 mtime 粒度)。**mutation 1 親跑**:refresh 條件改 `if true ||` → 釘子測**紅**(其餘 15 writer 測綠)→ cmp byte-identical 還原。
- **殘留 LOW(全量輸出;均為有界自癒 race,不阻塞)**:
  - **L-R1(LOW,confidence MED)post-write stat 快照 TOCTOU**:自寫 flush 與 `ledger_stat = stat_ledger(...)` 之間外部寫者恰好 append(µs 級窗口)→ 快照把該外部行「吞進」len 而 cache 無此行 → 該行不可見**直到下一次外部檔案變化**(默認 cron 每小時 append → 盲窗 ≤1h,非首輪的 blind-until-restart)。硬化方向:自寫後快照改用「前快照 len + 本次寫入 bytes」推算,不符即留舊快照迫使下事件重讀。
  - **L-R2(LOW,confidence HIGH)capture-error 分支吞掉失敗的 refresh**:refresh Err(外部變化已偵測但重讀失敗)→ capture-error row 寫入後該分支**無條件** `ledger_stat = stat_ledger(...)` → 快照跳到含未讀外部行的檔案態 → E1 自報「快照維持原狀下一事件重試」不變量被 capture-error 分支破壞;同樣 ≤下次外部變化自癒。修法:僅當本事件 refresh 成功才在 capture-error 分支更新快照(小改)。
  - **L-R3(LOW/NOTE)`let _ = bw.flush()` 靜默吞 flush 錯誤**(refresh 內):與修前語義等價(dedup 只見磁碟態)但屬 silent-fail 族;建議補 warn。
- 裁定:首輪 F1 核心危害(disable 路徑盲到重啟,無界)已閉;殘留均為罕見觸發+有界自癒(≤下次外部 append),demo-only+envelope 預算硬上限兜底。列 PM 裁量(fix-in-passing 或接受),不擋 E4。

## F3/F4 快速確認(coordinator 重點 4)

- F3:`demo_learning_lane.rs` wrapper 註釋補跨實現註記(含 Python 兩檔 file:line),未動 Python、未改邏輯——與退回要求一致。
- F4:測試改持 `test_env_lock::guard()` + save/remove/restore,斷言無條件執行(diff 親讀)——閉合。

## 驗證(全部親跑)

- lib:**4258 passed / 0 failed / 1 ignored**(4254+4,與宣稱逐位一致)。
- 全套(lib+integration+bins):**4667 passed / 0 failed**(awk 逐 target 加總親算;本輪多次運行 `stress_tick_latency_benchmark` 均綠,E1 flake 記錄=誠實披露非掩蓋;其機制解釋一處小不精確:paper 路徑根本不進 exchange 分支的 withhold 塊,比「matches! 短路」更強,零新增成本結論不變)。
- mutation 2 輪(F1 refresh 失能→釘子紅;F2 release 刪除→契約紅)親跑親還原,E1 自證誠實。
- 新測試/註釋中文優先;工作樹恢復 10+1 檔、+1384/−122。

## E4 交接備註

1. L-R1/L-R2/L-R3 為 LOW 殘留,PM 裁量處置(建議 E1 任一後續觸碰 writer.rs 時折入)。
2. F2 架構事實(withhold 恆 Validation→Bypass)建議 PM 收尾時回寫設計正本(E1 報告 §十亦提)。
3. Linux 部署後 1h 實證清單照設計 §1.6(E4 執行面)。

## 附:報告偏離聲明

- 按派工指示,E2/memory.md 屬並行 session 改動中檔案「絕不觸碰」——本輪完成序列的 memory 追加**跳過**,結論以本報告+inline 回報為準,待並行 session 收手後由 PM 裁定補記。
- E2 未改任何業務代碼;唯一寫檔 = 本報告。mutation 探針經 scratchpad backup 完整還原(git diff --stat 親驗)。
