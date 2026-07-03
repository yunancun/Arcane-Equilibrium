# IMPL-A:soak dispatch-edge containment(Part 1)實作報告

- 日期:2026-07-03(設計正本 2026-07-02;**已含 E2 RETURN 修復輪 F1-F4,見 §十**)
- 角色:E1(Backend Developer)
- 設計正本:`docs/execution_plan/2026-07-02--soak_dispatch_edge_containment_and_drift_gate_design.md` Part 1(§1.1-§1.3、§1.5)
- E2 審查:`docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-03--soak_dispatch_edge_containment_impl_a_review.md`(RETURN_TO_E1:2 MAJOR + 2 LOW;本報告 §十為修復記錄)
- 基線:main @ `2a012deeb`;**未 commit / 未 push**(改動留工作樹,待 E2 narrow re-review→E4→PM)
- 範圍外(按派工明示):§1.4 healthcheck 哨兵、Part 2(drift gate)、Part 3、任何 env/.env/settings 改動

---

## 一、任務摘要

按設計 Part 1 把 soak isolation 從 pre-risk 全攔改為 dispatch-edge withhold:
普通 Open 恢復流經完整 pipeline(cost_gate reject 重新產出 eligible RejectEvent
→ probe writer feed 恢復),僅在 `gate.approved` 後、任何副作用之前被截留;
soak 生效與 operator authorization envelope 同鐘(三態 fail-closed + last_good
硬上界);伴生修復 writer probe_ledger O(n²) 全量重讀。

## 二、修改清單

### 生產代碼
| 檔 | 改動 |
|---|---|
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` (+79/−32) | ① 刪 pre-risk soak guard 塊(原 :801-827)與舊常量 `BOUNDED_PROBE_SOAK_ISOLATION_REJECT_REASON`;② `record_pre_risk_rejection` 更名 `record_undispatched_rejection`(+doc,:754 呼叫點同步);③ `if gate.approved {` 頂端插 withhold 塊(on_rejection 回滾 → lease `Failed` 釋放 → record_undispatched_rejection → `soak_withheld_opens+=1` → 60s 節流 warn → `continue`);④ 新常量 `BOUNDED_PROBE_SOAK_WITHHELD_REJECT_REASON = "bounded_probe_soak_isolation:approved_entry_withheld_at_dispatch"` 與 lease stage `"bounded_probe_soak_isolation_withheld"` |
| `rust/openclaw_engine/src/demo_learning_lane.rs` (+88/−15) | 抽共用純函數 `validate_operator_authorization_envelope`(candidate 無關檢查全集,回 `Ok(expires_at_ms)`);`validate_operator_authorization` 改呼核心 + 留 side_cell/candidate 預算檢查;新 `SoakEnvelopeState{Active/Expired/Indeterminate}` + 純分類函數 `soak_envelope_state`(讀檔結果進、三態出,模組零 IO 契約不破);新常量 `OPERATOR_AUTHORIZATION_EXPIRED_REASON`(字面值不變) |
| `rust/openclaw_engine/src/demo_learning_lane_soak_gate.rs` (新檔 307 行含測試) | `SoakEnvelopeGate`:30s TTL 惰性讀檔 + `last_good_expires_ms` 硬上界 + indeterminate 節流 WARN + withhold log 節流;MODULE_NOTE 完整 |
| `rust/openclaw_engine/src/demo_learning_lane_writer.rs` (+255/−54) | ① plan 路徑解析抽共用 `demo_learning_lane_plan_path(_from_env)`(spawn 與 soak gate 同源);② O(n²) 修:`run_writer` 啟動 `read_ledger_rows` 一次,維護 in-memory `Vec<LedgerRecord>`;`build_runtime_admission_result` 改收 `&[LedgerRecord]`;寫檔成功後 `push_ledger_cache`(parse-back 保證與重啟後讀檔等價;admission row 與 capture-error row 都入 cache);③ `#[cfg(test)] handle_for_test()` + `WriterMsg` 提為 `pub(crate)`(feed 釘子測試用) |
| `rust/openclaw_engine/src/tick_pipeline/mod.rs` (+11) | `TickStats.soak_withheld_opens: u64`(`#[serde(default)]` 向後相容);`TickPipeline.soak_envelope_gate` 欄位(per-pipeline 實例,非全局 singleton → 無 singleton 登記義務) |
| `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs` (+3) | ctor 初始化 `soak_envelope_gate: Default::default()` |
| `rust/openclaw_engine/src/lib.rs` (+3) | 註冊 `pub mod demo_learning_lane_soak_gate` |

### 測試代碼
| 檔 | 新增 |
|---|---|
| `step_4_5_dispatch_tests.rs` (+413) | pipeline 級 withhold 矩陣 6 測(見 §四⑤);`AlwaysOpenStrategy` 測試策略(emit AtomicBool 可開關)+ 40 根 1m bar 暖機 harness + `with_soak_flag`(test_env_lock 包裹 env 讀寫) |
| `demo_learning_lane_soak_gate.rs` 內測 | 10 測:有效/過期/缺檔/壞 JSON/欄位無效/last_good 硬上界/TTL 緩存/簽署時刻即時解除/plan-stale 不解除/log 節流 |
| `demo_learning_lane_tests.rs` (+182) | `soak_envelope_state` 純函數 7 測(含 admission↔soak 同鎖步釘子) |
| `demo_learning_lane_writer.rs` 測試 | dedup 等價性 3 測(同 run 內/既有行/capture-error)+ 路徑解析默認分支 1 測;既有 2 個直呼 `build_runtime_admission_result` 測試改傳 `&[]`(語義等價:原 ledger 檔不存在) |
| `ipc_server/tests/mod.rs` (+2) | TickStats fixture 補 `soak_withheld_opens: 0` |
| `tick_pipeline/tests/fast_track_reduce.rs` (+15/−11) | include_str! 源碼掃描契約測試更新:helper 新名 + 透傳點角色改述(計數仍 =4:policy pre-risk / withhold / exchange / paper) |

## 三、關鍵 diff(withhold 塊核心)

```rust
if gate.approved {
    // 必須釘死在任何副作用之前(exchange_seq/Approved verdict/persist_intent/
    // spine lineage/tx.send/proactive_mirror_insert 全部尚未執行)。
    if bounded_probe_soak_isolation_enabled(em) {
        let wall_now_ms = openclaw_core::now_ms();   // 牆鐘,禁 event.ts_ms(Fix-4)
        if self.soak_envelope_gate.should_withhold_approved_open(wall_now_ms) {
            strategy.on_rejection(intent, BOUNDED_PROBE_SOAK_WITHHELD_REJECT_REASON);
            release_decision_lease_for_governance(&self.governance,
                gate.lease_id.as_deref(), LeaseOutcome::Failed,
                BOUNDED_PROBE_SOAK_WITHHELD_LEASE_STAGE);
            record_undispatched_rejection(/* typed rejected verdict + qty=0 intent */);
            self.stats.soak_withheld_opens += 1;
            /* 60s 節流 warn */
            continue;
        }
    }
    self.exchange_seq = self.exchange_seq.wrapping_add(1);
    ...
```

envelope 判定(`SoakEnvelopeGate::should_withhold_approved_open`):
- `Active{expires}` → `now < expires` 攔(到期時刻落 TTL 窗口內也即時解除);
- `Expired` → 解除;
- `Indeterminate` → 若 `last_good_expires_ms` 已過 → 解除(硬上界);否則 fail-closed 照攔 + 60s 節流 WARN。

## 四、設計要點逐條對照

| 要點 | 落實 | 偏離 |
|---|---|---|
| ① 刪 pre-risk guard 塊 | DONE(:801-827 + 舊常量;`bounded_probe_soak_isolation_enabled(_from_values)` 保留作 flag+mode 硬前提) | 無 |
| ② withhold 移 gate.approved 頂端 | DONE:副作用前置零(零 Approved verdict 測試斷言;**exchange_seq 斷言初版缺失,E2 F2 指出後於修復輪補真斷言**,withhold 測=0/放行測=1);on_rejection 回滾;lease `LeaseOutcome::Failed` + 獨特 stage(**lease 測試覆蓋初版 vacuous,修復輪補三層,見 §十 F2**);helper 更名 + 新 reason 常量;不寫 decision_features(withhold 路徑 `continue` 於兩個 emit 之前);TickStats 計數 + 節流 log | §十 F2(初版報告兩處宣稱不實,已修正) |
| ③ envelope 三態 fail-closed | DONE:可讀+有效→武裝+緩存 last_good;可讀+過期 / now≥last_good→解除;不可讀/缺檔/壞 JSON/schema 錯/欄位無效/從未可讀→照攔+節流 WARN;30s TTL 僅 demo/live_demo+flag=1+approved Open 觸發;核心抽 `validate_operator_authorization_envelope`(原函數改呼,字面 reason 不變);plan 路徑解析抽共用 | 見 §五 D1/D2(小決策) |
| ④ writer O(n²) 修復 | DONE:啟動讀一次 + in-memory Vec + 寫後 parse-back push;等價性 3 測(dedup 語義逐位一致,含 capture-error row 參與 dedup 的修前語義) | 見 §五 D3(啟動讀失敗行為) |
| ⑤ 測試全矩陣 | DONE(修復輪修正兩處宣稱):withhold 矩陣(Active→無 dispatch+typed rejected verdict+qty=0 intent+零 Approved verdict+exchange_seq=0 真斷言;Expired→放行且 Approved verdict 恢復+exchange_seq=1;缺檔→攔;flag=0→全滅;paper→恆不攔+submit 路徑不受影響;live/paper flag 矩陣既有測試保留原樣);**lease 覆蓋=三層**(gate-ON pipeline BYPASS 可觀測+零 live lease / 真 Active lease seam revoke(execution_failed) / 源碼契約 mutation-bite,見 §十 F2——初版「lease Failed 無洩漏」宣稱 vacuous,E2 mutation 親證);feed 恢復釘子(soak 武裝下 cost_gate reject → writer channel 收到 eligible RejectEvent,舊 guard 下此測試必紅);soak_envelope_state 全矩陣;[27] 形狀;**F1 外部寫者可見釘子**(修前 cache 版本必紅,mutation 親證) | §十 F1/F2 |

## 五、小決策與最小安全解(供 E2 重點審)

- **D1(時鐘源)**:withhold/envelope 判定用 `openclaw_core::now_ms()` 牆鐘而非 `event.ts_ms`。理由:envelope 到期是牆鐘授權語義,WS payload ts 不可作授權時鐘(flash_dip Fix-4 教訓);失效方向安全(event.ts_ms 滯後只會多攔)。admission 鏈維持既有 event.ts_ms 語義未動。
- **D2(reason 先後順序)**:`validate_operator_authorization` 抽核心後,多重缺陷 envelope 的 reason 先後與抽取前略異(核心檢查先於 side_cell/candidate 預算)。accept/reject 語義逐位不變;既有測試全部單缺陷 fixture,全綠。已在代碼注釋標明。
- **D3(writer 啟動讀失敗)**:ledger cache 啟動載入失敗 → warn + writer task 退出(fail-closed),鏡像同函數 `open_writer` 失敗先例。修前語義是「每事件讀失敗→逐筆 capture-error row」;壞 ledger 下兩者都不可能 admit probe,新行為少了 capture-error 證據軌但方向更保守。
- **D4(plan 路徑注入方式)**:設計原文之一提 main.rs 注入 plan_path;實作改為 gate 首次使用時經共用 `demo_learning_lane_plan_path_from_env()` 惰性解析(OPENCLAW_DATA_DIR 默認 `/tmp/openclaw` 鏡像 main.rs 既有慣例)。理由:達成「單一解析函數杜絕雙路徑漂移」的設計目的,又免去 main.rs→main_pipelines→bootstrap 三層參數穿線(最小影響)。
- **D5(gate 放置)**:`SoakEnvelopeGate` 為 TickPipeline 欄位(per-pipeline 實例),非全局 singleton → 不觸發 singleton 登記義務。
- **D6(節流參數)**:indeterminate WARN 與 withhold log 均 60s 節流(設計未定值,自選)。
- **D7(fast_track_reduce.rs 契約測試更新)**:該檔有 include_str! 源碼掃描測試釘死舊 helper 名——rename 是設計明令,更新此測試屬 rename 的必要伴隨,非 scope 擴張。

## 六、治理對照

- 硬邊界零觸碰:max_retries=0 / live_execution_allowed / execution_authority / system_mode 全未動(grep 自證);live 5-gate、admission 鏈(evaluate_probe_admission 判定順序)未動。
- fail-closed 方向:任何存疑態=照攔;唯二解除證據=可讀確定過期 or last_good 超時(operator 親簽時刻=結構性硬上界,plan 檔被刪也必終止)。
- flag=0 kill switch 語義與現狀一致(`bounded_probe_soak_isolation_enabled` 未改)。
- 無 env/.env/settings 改動;無 SQL migration;無 commit/push。
- 生產代碼零機器路徑硬編碼(grep 自證;`/tmp/openclaw` 為 main.rs 既有默認慣例鏡像)。
- 注釋全中文(技術名詞/常量保英文);新檔 MODULE_NOTE 完整。
- 檔案大小:step_4_5_dispatch.rs 2130→2177(+47,淨增主因 withhold 塊注釋;測試全在 tests 檔)。已超 2000 之既有文檔化例外檔,本次未逆轉但小幅加深——E2 若判定不可接受,可把 withhold 塊抽 free fn 減行。

## 七、驗證結果

- `cargo build`(openclaw_engine):green,0 新 warning。
- `cargo clippy --lib --tests -p openclaw_engine`:本人觸碰檔零新 warning(writer :765-766 兩條為既有測試 `&& true` 樣式,行號位移非新增;openclaw_types 32 條 pre-existing 未觸碰)。
- `cargo test`(openclaw_engine 全套,lib+integration+bins):**4663 passed / 0 failed**。
  - lib 目標:4254 passed / 0 failed / 1 ignored(ignored 為 pre-existing)。
  - 新增測試 27(gate 模組 10 + lane 純函數 7 + dispatch 整合 6 + writer 4),移除 0;推得修前 lib 基線 4227(main @2a012deeb 假定綠,+27 = 4254 吻合)。
  - 途中唯一非 soak 紅測:`test_dispatch_forwards_hurst_at_all_persist_intent_call_sites`(源碼掃描釘舊 helper 名)——按 D7 更新後全綠;非掩蓋,屬 rename 的直接後果。

## 八、遺留疑點(E2 重點審查位置)

1. **withhold 塊借用與副作用審計**:`step_4_5_dispatch.rs` `if gate.approved {` 頂端 —— 請對抗性驗證塊內確無任何先於 continue 的持久化/計數/channel 副作用遺漏(尤其 features 構造只是純組裝、無 emit)。
2. **D2 reason 順序**:`demo_learning_lane.rs` `validate_operator_authorization` —— 確認無外部消費者依賴多缺陷 envelope 的 reason 先後。
3. **D3 writer 啟動失敗語義**:`demo_learning_lane_writer.rs` run_writer 開頭 —— 壞 ledger 檔 fail-closed 退出 vs 修前逐筆 capture-error,E2 裁是否可接受(方向更保守但少證據軌)。
4. **flush 失敗時 cache 已 push**:寫檔成功但 flush 失敗 → cache 已 dedup,修前(讀檔)可能重試 append。方向=不重複 admission(更保守),請確認接受。
5. **測試 env 面**:`with_soak_flag` 持 `test_env_lock::guard()` 全程包 on_tick;若未來有其他並行測試在 demo pipeline 觸發 approved Open 而未持鎖,可能受 flag 泄漏影響(現無此類測試)。
6. **step_4_5_dispatch.rs +47 行**(超 2000 例外檔小幅加深),見 §六。

## 九、Operator 下一步(經 PM)

E2 narrow re-review(限 F1-F4 delta)→ E4 回歸(Linux 真 engine,含部署後 1h SQL/ledger mtime 實證清單,見設計 §1.6)→ PM 收。重新武裝 soak 前置:Part 3 新 envelope 簽署(operator 動作,非本任務)。設計正本 §1.3「writer 唯一寫者」前提修正由 PM 收尾時回寫(E2 F1 證偽,E1 不改設計文檔)。

---

## 十、E2 RETURN 修復輪(2026-07-03,F1-F4)

### F1(MAJOR)writer cache 盲於外部 ledger 寫者 → stat 級失效

- **修法**(`demo_learning_lane_writer.rs`):新 `LedgerStat{len, mtime}` + `stat_ledger()` + `refresh_ledger_cache_if_externally_changed()`。每事件 `fs::metadata` 比對 last-known (len,mtime);任何外部變化(增長/截斷/替換/刪除)→ **先 `bw.flush()` 自寫緩衝**(否則重讀會把已 push cache 但未落盤的自寫行丟失 → dedup 回退)→ 全量重讀刷新 cache → 重 stat 更新快照。自寫落盤後同步更新快照(否則下一事件把自己的寫入誤判為外部變化 → 每事件重讀 = 退回 O(n²))。
- **取捨(PM 裁定範圍內的小決策)**:①全量重讀而非增量——同時覆蓋四種外部變化,語義與修前「每事件讀檔」一致;外部 append 低頻(cron 每小時級)攤還 O(1),設計目的保留。②per-event stat 不節流——單次 syscall ~µs 級,129k events/日成本可忽略,且外部 disable 即時生效(最貼修前語義)。③stat/重讀失敗 → Err 走既有 capture-error 分支(鏡像修前每事件讀檔失敗行為),cache/快照維持原狀下一事件重試。
- **釘子測試** `ledger_cache_sees_external_side_cell_disable_without_restart`:run_writer 同一 run 內,事件 A 落盤後外部 append `side_cell_disabled` row(runtime_adapter.py 形狀)→ 事件 B admission 必判 `SIDE_CELL_DISABLED`/`manual_disable`。**mutation 親證**:把 refresh 條件改 `if true ||`(恆用 cache)→ 測試紅(row B = `ADAPTER_DISABLED`,即 E2 描述的全盲行為)→ 還原(cmp byte-identical)→ 綠。
- **殘留邊界(供 E2 覆核)**:mtime 粒度粗的檔案系統上「同秒內同長度改寫」不可偵測——len 比對抓 append/截斷,此病態案例接受(E2 F1 修法方向即 stat 級);外部寫者與本 task 同毫秒交錯寫入由「重讀前先 flush」+下一事件重試覆蓋。

### F2(MAJOR)withhold lease 釋放零測試 bite + 報告兩處不實宣稱

- **架構事實(修正 E2 F2 的一處前提,非抗辯——測試照補)**:withhold 可達模式(demo/live_demo)經 `effective_governance_profile` 恆為 **Validation** profile;router gate ON 時 `acquire_lease` 對非 Production profile 短路回 `LeaseId::Bypass`(`governance_core.rs acquire_lease` 開頭,emit 合成 BYPASS 轉移),`release_lease(Bypass)` 為**設計上 no-op**。真 Active lease 在今日接線下於 withhold 路徑結構性不可達(Production 僅 Live+Mainnet,而 em="live" 被 mode 檢查排除)。因此「刪 release 呼叫」的**行為級**黑箱 bite 不可得——E2 的 mutation 25/25 綠有兩層原因:測試 gate OFF(E2 已證)+ 即使 gate ON 也是 Bypass(本輪補證)。
- **三層覆蓋修法**(`step_4_5_dispatch_tests.rs`,module 註記已寫明架構事實):
  1. `soak_withhold_with_router_gate_on_leaves_no_live_lease`——`set_router_gate_enabled_for_test(true)` + `set_lease_transition_tx`:withhold 語義不變、BYPASS 轉移可觀測(證 lease facade 真被走到)、零 SM 物件/零 live lease。
  2. `withhold_failed_release_revokes_active_lease_without_leak`——真 Active lease seam(authorized core + Production profile 參數取真 SM lease),以 withhold 塊逐字同款的 `release_decision_lease_for_governance(...Failed, BOUNDED_PROBE_SOAK_WITHHELD_LEASE_STAGE)` 釋放:斷言 revoke(非 consume)、`get_live()` 歸零、`REVOKED`/`revoke_requested` 轉移可觀測。未來 profile 接線若改變,釋放語義已釘。
  3. `soak_withhold_block_lease_release_contract`——源碼契約(include_str! 範式,先例 fast_track_reduce.rs):withhold 塊(判定命中至 `continue`)必含 `release_decision_lease_for_governance`/`LeaseOutcome::Failed`/stage 常量/`gate.lease_id.as_deref()`/`record_undispatched_rejection`/計數遞增。
- **mutation 自證**:整段刪除 withhold 塊的 release 呼叫 → `soak_withhold_block_lease_release_contract` **紅**(層 1/2 維持綠,符合三層設計)→ 還原(cmp byte-identical)→ 綠。
- **報告宣稱修正**:①初版 §四⑤「測試斷言 exchange_seq 不變」不實(僅註釋)——本輪補真斷言:withhold 測 `exchange_seq==0`、放行測 `exchange_seq==1`;②「lease store 空」斷言 vacuous——原斷言保留但改註誠實說明(gate OFF 下僅證無 SM 物件殘留),真覆蓋由上述三層承擔。§四②/⑤ 已同步改寫。

### F3(LOW)跨實現 reason 順序註記

`demo_learning_lane.rs` `validate_operator_authorization` 註釋補一段:Python 平行判準(`runtime_adapter.py:274-296`、`bounded_probe_plan_inclusion_review.py:310-325`)保持舊檢查順序,多缺陷 envelope 兩實現 reason 字串可能不同,離線對賬屬預期噪音,accept/reject 逐位等價。**未動 Python 兩檔**(並行 session 工作面)、未改邏輯。

### F4(LOW)plan_path 測試條件空轉

`plan_path_resolution_defaults_under_data_dir` 改為持 `test_env_lock::guard()` + save/remove/restore `PLAN_PATH_ENV`(同檔既有範式),斷言無條件執行;移除 `if env 缺席` 包裹。

### 修復輪驗證

- `cargo build`:綠,0 新 warning。
- `cargo clippy --lib --tests`:觸碰檔零新 warning(writer `&& true` 兩條為既有測試行位移)。
- `cargo test --lib`:**4258 passed / 0 failed / 1 ignored**(修復輪前 4254,+4 = F1 釘子 1 + F2 三層 3;F4 為原測試改寫非新增)。
- `cargo test` 全套(lib+integration+bins):**4667 passed / 0 failed**(修復輪前 4663,+4)。首輪跑出 1 flake:`stress_tick_latency_benchmark` 1000.7µs vs 1000µs 門檻(debug 全套並行負載下的邊際 wall-clock flake;隔離跑綠、全套重跑綠;該 benchmark 走 paper 路徑,withhold 檢查在 `matches!(em,"demo"|"live_demo")` 即短路,本 diff 對其零新增成本)。如實記錄非掩蓋。
- mutation 自證 2 輪(F1 refresh 失能→釘子紅;F2 release 呼叫刪除→契約紅),均以 scratchpad backup 還原並 cmp byte-identical。
- scope:改動仍限任務 10+1 檔(git status 親證);並行 session 檔案(helper_scripts/*.py、TODO.md、memory/、E1/E2 memory.md)零觸碰;無 commit/push/env 改動。

### 供 E2 narrow re-review 重點

1. F1 stat 失效的並發窗口論證(`refresh_ledger_cache_if_externally_changed` 的 flush-before-reread + 重讀後重 stat;mtime 粒度病態案例接受聲明)。
2. F2 架構事實(Validation→Bypass→release no-op)是否認可;三層覆蓋 + 源碼契約 bite 是否滿足「load-bearing claim 必有 test bite」紀律,或 E2 另裁(如:要求把 Bypass 事實回寫設計文檔——屬 PM 收尾)。
3. F2-② seam 測試用 Production profile 參數在 Validation core 上取真 lease 的手法是否可接受(鏡像未來接線,非現實路徑)。

---

## 十一、殘留修復輪(2026-07-03,operator 裁決「殘留項不留」;基準 = HEAD `77c7ce95b`)

出處:E2 narrow re-review + E4 報告殘留項(設計正本 §1.7 登記)。本輪改 3 檔:`demo_learning_lane_writer.rs`、`step_4_5_dispatch.rs`、`step_4_5_dispatch_tests.rs`。

### L-R2:capture-error 分支無條件推進 stat 快照吞掉重試不變量

修法:`run_writer` 以 `refresh_ok` 記住 refresh 成敗;capture-error 分支**僅 refresh 成功時**推進快照,失敗保留舊 stat → 下一事件 stat 必不匹配 → 必重試重讀。
誠實聲明:與 L-R1 的 expected-len 採納機制疊加後,`refresh_ok` gate 無獨立可觀測失效模式(refresh 失敗 + 外部行存在時,expected-len 必不符 → 本就不採納;唯一 gate 獨佔場景 = 「stat 瞬時失敗且無外部變化」,該場景 cache 本就不 stale)。屬 belt+suspenders 的字面落實,行為級 bite 由 L-R1 兩測承擔,未另造假測試。

### L-R3:refresh 內 `let _ = bw.flush()` 靜默吞錯

修法:改 `if let Err(e) = bw.flush() { warn!(...) }`(比照檔內既有 flush warn 風格)。**節流取捨**:未加額外節流狀態——此 flush 僅在「偵測到外部變化」時執行(cron 每小時級),觸發頻率天然受限;檔內既有 run_writer flush warn 亦無節流。flush 失敗不中斷重讀(讀到缺自寫緩衝行的檔案時快照取讀前 stat,下一事件必重試),註釋已寫明。無 log 斷言測試(純觀測面)。

### L-R1(TOCTOU):自寫 flush 與 stat 快照之間的外部 append 盲窗

修法 = coordinator 建議的預期檔長法,雙側消除:
- **自寫側**:新 `advance_ledger_stat_after_self_write(path, stat, written_bytes)`——以「寫前快照長度 + 自寫 bytes(json.len()+1)」推算預期檔長,實際 stat **僅在 len 恰等於預期時採納**;不等(外部行擠進窗口 / flush 未全落盤)保留舊快照 → 下一事件必重讀。mtime 陷阱解法:mtime 只在採納時隨 actual 一起收,不合成、不單獨比對 → 無 spurious re-read(O(1) 保留,由對照組測試釘死)。
- **refresh 側**(同類窗口,順帶消除):快照改取「讀之前」的 stat(原為讀後)——讀後外部 append 只造成下一事件過觸發一次重讀(方向安全),不再可能把讀不到的行 bytes 吞進快照。
- **失效方向**:兩側任何不確定都收斂為「多一次重讀」,永不產生盲窗。
- 測試:`self_write_snapshot_does_not_swallow_racing_external_append`(確定性重現窗口結局:自寫+外部行都已落盤後才推進快照 → 外部行必於下一 refresh 可見;**mutation 親證**:把 advance 改回修前 stat-as-snapshot 語義 → 紅)+ `self_write_snapshot_adopts_without_race_and_avoids_spurious_reread`(cache 標記行技巧證無競態時零無謂重讀)。

### L-1:withhold 契約測試補負向釘子

`soak_withhold_block_lease_release_contract` 增 `assert!(!block.contains("emit_decision_feature"))`。**mutation 親證**:往 withhold 塊插入 `emit_decision_feature_intent_rejected` 呼叫 → 紅 → 還原。

### NOTE-1:QTY-ZERO-SKIP 路徑 lease 洩漏(pre-existing 不對稱)

修法:`if final_qty <= 0.0` 塊 `continue` 前補 `release_decision_lease_for_governance(..., LeaseOutcome::Failed, QTY_ZERO_SKIP_LEASE_STAGE)`(新常量 `"qty_zero_skip"`,獨特 stage 利審計)。live(Production)下 lease 為真 Active,本修復消除 ExpiryGuardian TTL 兜底的真實洩漏窗口;demo/live_demo(Validation)為 Bypass no-op。
測試:`qty_zero_skip_block_lease_release_contract`(源碼契約,手法同 F2-③;**mutation 親證**:刪釋放呼叫 → 紅 → 還原);Failed 釋放語義(revoke 非 consume、零 live 殘留)由既有 F2-② seam 測試共同覆蓋(同一 helper 同一 outcome)。未做 pipeline 級 qty-zero 整合測試(需 instrument cache 取整到 0 的重 fixture,契約+seam 已覆蓋 load-bearing claim)。

### R3-1(E2 第三輪):qty-zero 契約測試補 skip-not-reject 負向釘

`qty_zero_skip_block_lease_release_contract` 增兩斷言:`!block.contains("record_undispatched_rejection")` + `!block.contains("emit_decision_feature")`——QTY-ZERO-SKIP-1 的核心語義(skip-not-reject,防 trading.intents label 與 ML 污染)修前零測試咬(E2 驗證插回呼叫全套仍綠)。塊內註釋已預先 grep 證不含此二字串(無假紅)。**mutation 親證**:把 `record_undispatched_rejection` 呼叫插回 qty-zero 塊 → 該契約測必紅 → 還原 cmp byte-identical → lib 4261/0 全綠。

### 驗證(殘留修復輪)

- `cargo build` 綠;clippy 觸碰檔零新 warning(writer `&& true` 兩條 pre-existing 行位移)。
- `cargo test --lib`:**4261 passed / 0 failed / 1 ignored**(基線 4258,+3 = L-R1 兩測 + NOTE-1 契約 1;L-1 為既有測試內加斷言)。
- `cargo test` 全套:**4670 passed / 0 failed**(基線 4667,+3),零 FAILED target。
- mutation 自證 3 輪(L-R1 stat-as-snapshot 回退→紅 / NOTE-1 刪釋放→紅 / L-1 插 emit→紅),均 scratchpad backup 還原 cmp byte-identical。
- scope:本輪僅 3 檔(git status 親證);無 env/commit/push;並行 session 檔案零觸碰(本輪紀律含各 agent memory.md → memory 追加再次跳過,待 PM 裁定補記)。
