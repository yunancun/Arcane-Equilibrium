# E4 Regression — soak dispatch-edge containment(IMPL-A)commit 前全量驗收 · 2026-07-03

- 被驗:工作樹未 commit 改動(rust 10 M + 1 ?? = 11 檔,+1384/−122),基準 HEAD=`2a012deeb`。驗收中途並行 session 推進 HEAD `db80212f4`→`2bc69697c`(Python/docs/TODO hygiene,`git diff 2a012deeb..2bc69697c -- rust/` = **0 檔**,rust 基線態不受影響)。未 pull、未 commit、未 push、未動 env。
- 鏈:設計正本 §1.5(2026-07-02)→ E1 報告(含 §十 F1-F4 修復輪)→ E2 APPROVE(Re-review)→ 本 E4。
- 環境:Mac,cargo 1.95.0(toolchain 直呼,`~/.cargo/bin/cargo` symlink 損壞與 E2 同觀察),debug profile(與 E1/E2 同口徑);py3.10 pytest。

## 裁決:PASS(ready for PM commit + push)

---

## 1. Test 結果(計數表)

| 引擎 | passed | failed | ignored/skipped | baseline(修前,同 commit 親測) | delta |
|---|---|---|---|---|---|
| Rust full(lib+integration+bins,47 targets,`--no-fail-fast`)run1 | **4667** | 0 | 6 ign | 4636/0/6 | +31 |
| Rust full run2 | **4667** | 0 | 6 ign | 同上 | +31 |
| Rust lib(兩輪皆) | **4258** | 0 | 1 ign | 4227/0/1 | +31 |
| Python srv tests/(快速確認) | 804 | 1 | 2 skip | 1f = pre-existing @HEAD(見 §5) | 非本批 |
| Python helper_scripts/research/tests(全量) | **1417** | 0 | 3 skip | BASELINE 1417/0/3 | 0(逐位一致) |

- **跑兩遍**:run1 == run2,47 target `test result:` 行剔除 timing 後 **byte-identical**,exit 0 ×2,零 FAILED 行。非 flaky。
- **base 親測(不信 E1 推得值)**:`git stash push` 10 tracked 檔 + 暫移 untracked 新檔(同 commit 同樹同 target dir),rust 樹 `git diff HEAD -- rust/`=0 後實跑 → full **4636/0/6**、lib **4227/0/1**(exit 0)。E1 宣稱「修前 lib 4254/全套 4663 = 首輪後;真 base 4227/4636;+27+4=+31」**逐位吻合**。還原後 11 檔 md5 對照 before/after **byte-identical**,stash dropped,樹回 10M+1?? 原態。
- **名字級對賬**(`--lib -- --list` base vs head):**REMOVED=0 / ADDED=31**,逐檔 = soak_gate 模組 10 + lane 純函數 7 + writer 5(首輪 4 + F1 釘子 1)+ dispatch 9(首輪矩陣/feed 6 + F2 三層 3)= 31,attribution 到 0 unexplained。0 個 `#[ignore]`(6 個改動測試檔 grep = 0)。既有 live/paper flag 矩陣測試 `bounded_probe_soak_isolation_blocks_only_explicit_demo_adapter_runtime` base/head 皆在(保留未動)。
- **非 lib target 無擾動**:38 個可對齊 target base==head 全同;非 lib 合計 base 409 == head 409。
- **基線只增不減**:E4 memory 前 Rust `BASELINE:`(2026-06-18,4087 = Linux release lib 口徑)→ 本輪 Mac debug lib base 4227 → head 4258,兩口徑內皆只增不減。**本輪建立 Mac debug 全套口徑基線 4667**(Linux release full = owed-post-push,歷史慣例)。

## 2. §1.5 測試矩陣盤點(逐組)

1. **withhold 矩陣 — 齊**:Active 攔(`soak_withhold_active_envelope_blocks_dispatch_with_clean_audit_shape`:無 OrderDispatchRequest + 恰 1 筆 typed rejected verdict 帶 withheld reason + qty=0 intent + 零 Approved verdict + `exchange_seq==0` 真斷言 + on_rejection 回滾 + 計數=1)/ Expired 放行(+`exchange_seq==1` 成對 + Approved verdict 恢復)/ Indeterminate 缺檔攔 / flag=0 全滅 / paper 恆不攔(`total_intents==1` 證 submit 路徑不受影響)+ 既有 live/paper 矩陣保留;lease 三層(gate-ON BYPASS 可觀測、真 Active lease seam revoke、源碼契約 6 token)。
2. **feed 恢復釘子 — 齊**:`soak_cost_gate_reject_feeds_probe_writer_channel_while_armed` 走真 on_tick 全鏈,writer channel 收到 normalize 後的 eligible RejectEvent;舊 pre-risk guard 下結構性必紅(E2 已裁定)。
3. **soak_envelope_state 全矩陣 — 齊**:lane 7 測(有效→Active 帶精確 expiry ms/過期→Expired/不可讀→Indeterminate/壞 JSON+schema 錯/缺 auth+欄位無效+expiry 格式錯/staleness 忽略/admission↔soak lockstep 同常量)+ gate 10 測(last_good 硬上界含刪檔中途、TTL 緩存+過期改寫、TTL 窗內親簽時刻即時解除、log 節流)。「未來時間戳」字面項無獨立同名測試,substance 映射 =(a)Active{expires>now} 即未來到期時間戳案例(lane+gate 皆測)、(b)expiry malformed→Indeterminate;狀態空間內無第三種「未來時間戳」語義(小決策:substance 等效即 PASS,依 E4 教訓「檔名/spec 字面非核實標準」)。
4. **[27] 審計形狀 — 齊(一項為結構性驗證非直接斷言,見 finding L-1)**:零 Approved verdict 直接斷言 ✓;「零 decision_features 負標籤」= withhold 塊(:894-:939)內零 `emit_decision_feature*` 呼叫、兩個 emit 點(:1054/:1337)皆在 `continue` 之後(本人 grep + 親讀塊本體,與 E2 line-level 覆核一致),但**無測試直接斷言**(emit 走 intent_processor 非 trading channel,pipeline 測試結構上觀察不到)。

## 3. Mock 審查(抽查 3 條指定測試 + harness)

| Test | 真 vs stub 分界 | OK? |
|---|---|---|
| `soak_cost_gate_reject_feeds_probe_writer_channel_while_armed` | 真 TickPipeline.on_tick 全鏈(40-bar 暖機→真 scanner/exchange gate cost_gate);負 edge estimates 為 config 注入非邏輯 stub;`handle_for_test()` = 純 channel 接收端(IO 邊界捕捉,不 stub writer/dispatch 邏輯);斷言咬 normalize 後 reason code | ✅ |
| `ledger_cache_sees_external_side_cell_disable_without_restart` | 真 `run_writer` task + 真 tempfile IO + 真 admission 鏈(`evaluate_probe_admission`);「外部寫者」= 直接檔案 append(即外部行為本體);斷言 parse-back 真 ledger 內容 row B decision==SIDE_CELL_DISABLED;E2 mutation(`if true \|\|`→紅)已證 bite | ✅ |
| `soak_withhold_with_router_gate_on_leaves_no_live_lease` | 真 pipeline + `set_router_gate_enabled_for_test(true)`(test-only setter,防 env race 正當手法);transition channel = telemetry 捕捉;斷言 withhold 語義不變 + BYPASS 轉移可觀測 + 零 live lease | ✅ |
| harness 通道真實性 | `set_shadow_channel` 實為設 `order_dispatch_tx`(生產接線 event_consumer/dispatch.rs:631 同一方法)——`order_rx` 捕的是真派單通道,名稱是 legacy | ✅ |

無一測試 stub 受測對象;fixture plan JSON 全走真 envelope 核心(`soak_envelope_state`→`validate_operator_authorization_envelope`)。E2 已做 4 輪 mutation 親證,本輪不重跑(獨立抽查職責已履行)。

## 4. Flake 覆核(E1 記錄的 `stress_tick_latency_benchmark`)

- 位置:integration target `tests/stress_integration.rs`(paper 路徑,不進 exchange 分支 withhold 塊——E2 已裁定比「matches! 短路」更強的零新增成本論證)。
- 本輪 **3 次全套運行(head ×2 + base ×1)全綠**,E1 的單次邊際超標(1000.7µs vs 1000µs)未重現。兩輪 head 結果 byte-identical → 無「兩遍不一致」測試,不觸發 3 次隔離重跑協議。
- 判定:E1 記錄 = debug 全套並行負載下的 wall-clock 邊際毛刺,**與本 diff 無關**(paper 路徑零新增代碼),誠實披露非掩蓋。非 FLAKY 標記對象。

## 5. Python 面(快速確認)與 GUI

- `helper_scripts/research/tests/` 全量(純淨 harness,srv root)= **1417/0/3 == BASELINE 逐位一致**——此 suite 含多個掃 IMPL-A 觸碰 rust 源碼的 cost-gate-lane 契約測試(`test_cost_gate_bounded_probe_active_order_wiring_contract` 等),是 Python 面唯一真實連帶風險點,全綠。
- `tests/`(srv root)= 804/1/2。唯一紅 = `tests/structure/test_event_consumer_split_static.py::test_event_consumer_hot_files_stay_split_under_limit`(assert 1108<=800)。**歸屬:非 IMPL-A** —— 該測只讀 `event_consumer/` 四檔,該目錄 working-tree 零改動(= HEAD 態),dispatch.rs 1108 / dispatch_tests.rs 1008 / loop_handlers.rs 1541 在 **clean HEAD 即超 800**(committed 歷史增長);IMPL-A scope 與 event_consumer 零交集。屬 hygiene lane(並行 commit `2bc69697c` 修 18 條 pre-existing 紅後仍餘此條)。
- ml_training/learning_engine/cron 未重跑(與 rust diff 零耦合、無 rust 源掃描,昨日 BASELINE 全綠;小決策:快速確認範圍取「有真實耦合面的兩個 suite」)。
- **GUI:N/A** —— 本改動 0 個 .js(git status grep = 0),node --check 按任務聲明跳過。

## 6. 全量 findings(含 LOW/INFO)

| # | severity | confidence | 內容 |
|---|---|---|---|
| L-1 | LOW | HIGH | §1.5 [27]「零 decision_features 負標籤」無直接測試斷言(withhold 測試經 trading channel 觀察不到 intent_processor 的 emit;源碼契約測試釘 6 個 positive token 但無 negative token 禁 emit 進塊)。現行為正確(結構性驗證 ×2:E2 line-read + 本人 grep)。建議日後 E1 觸碰該檔時在 `soak_withhold_block_lease_release_contract` 加一條 `!block.contains("emit_decision_feature")` negative 斷言,一行閉合 |
| I-1 | INFO | HIGH | 「未來時間戳」字面項的 substance 映射見 §2 第 3 組(判定為已覆蓋,非缺項) |
| I-2 | INFO | — | E2 交接的 L-R1/L-R2/L-R3(writer stat 快照 TOCTOU/capture-error 分支快照/靜默 flush)LOW 殘留:本輪未處置,PM 裁量(E2 已裁不擋 E4) |
| I-3 | INFO | HIGH | Python 1 pre-existing 紅(event_consumer split static)歸屬 hygiene lane,詳 §5;非本 IMPL 失敗 |
| I-4 | INFO | — | Linux release 全量 + 部署後 1h 實證清單(設計 §1.6)= owed post-push/deploy gate(Mac source-land 驗收已閉,慣例同前批) |
| I-5 | INFO | HIGH | 驗收中途並行 session commit `2bc69697c`(零 rust);PM commit 本批時必用 `git commit --only`(11 rust 檔 + E1/E2/E4 報告),勿掃入 memory/ 大批並行殘留 |

## 7. 跑兩遍結果

- Rust full:1st = 4667/0/6(exit 0);2nd = 4667/0/6(exit 0);per-target ex-timing byte-identical。flaky? **N**。
- base(stash 窗口單跑,exit 0,零 FAILED):4636/0/6——基線測量非回歸對象,單跑 + 與 E1/E2 雙口供吻合即定論。

## 結論

**PASS**。退 E1 清單:無。基線 +31 全新增測試、0 removed、0 regression;§1.5 四組實質齊備(1 個 LOW 級斷言縫隙不阻塞);mock 抽查全真路徑;flake 未重現且與 diff 無關;Python/GUI 面零連帶破壞。
