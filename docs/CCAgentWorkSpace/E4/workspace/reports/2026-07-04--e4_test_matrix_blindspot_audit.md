# E4 測試矩陣盲區審計(主審計 wf_6dc68c2f-4a0 補審 · P1-8 前置)· 2026-07-04

- 凍結基線:Mac HEAD `d68a13298`(代碼面;其後僅 docs commits)· Linux runtime checkout `262596c69` · AUDIT_DATE=2026-07-03(本補審 07-04 執行)。
- 模式:read-only 盲區審計。**不重建 BASELINE、本輪零測試執行**(E4 BASELINE 2026-07-03 passed=5492 failed=0 rust workspace Linux debug / Mac 副基準 srv tests/=805/0/2, structure=380/0 照引不動)。
- 邊界遵守:零修復、零 runtime mutation;Linux 證據全部 ssh trade-core read-only(檔案讀/proc 讀/ps/crontab -l);無 psql、無 rebuild、無 restart。
- 靶向:06-30 connector cutover 引入/變更的 Rust↔Python 訊息型別 vs contract test 覆蓋對比;fail-closed/timeout/retCode/concurrency/stale-data/auth-expiry/replay-promotion 盲區;v739 首批真 fill 未測路徑。

## 0. 結論(一句話)

Rust 側與 Python 側各自單元覆蓋充分(retCode/timeout/soak 圍欄/envelope fail-closed/admission mirror 全有測),但 **跨語言 seam 本身零 contract test**(無任何 golden vector / 共用 fixture / 路徑契約測試),且 runtime 證據顯示這條 seam 已經在漂移中真實出血(雙 plan 檔分裂、67k 筆 PLAN_STALE 洪灌、engine 36% CPU/2.5GB RSS、ledger 472MB 無界成長)。PA P1-8 放行判準「新/變更 message 型別 100% 有 contract test」目前不成立。

## 1. Cutover 窗口 Rust↔Python 訊息型別盤點 vs contract test 覆蓋

窗口:`26caf8ec4`(06-27)→ `d68a13298`(凍結 HEAD)。IPC method registry 窗口內新增 23 個方法全部 `stock_etf.*` dormant fixture(diff 證,零 removed),不在 Bybit demo fill 路徑。v739 fill 路徑的跨語言 crossing 型別及覆蓋現狀:

| # | Crossing 型別 | Rust 端 | Python 端 | Rust 單測 | Py 單測 | **跨語言 contract test** |
|---|---|---|---|---|---|---|
| C1 | Plan/envelope JSON(soak+admission)| `DemoLearningLanePlan`/`BoundedProbeOperatorAuthorization`(demo_learning_lane.rs:71-133,783-910)| policy.py 產出、runtime_adapter.py:255-297 鏡像判準 | ✅ lane7+gate10(07-03 E4)| ✅ policy 套件(evaluate_probe_admission 26 處)| ❌ **無**(無共用 fixture;等價性靠人工鏡像,demo_learning_lane.rs:845-848 註記自認) |
| C2 | probe_ledger.jsonl 雙寫者行格式 | `LedgerRecord` serde(demo_learning_lane.rs:262-315)| build_ledger_record/append_jsonl_ledger(runtime_adapter.py:148-170,677-692)+ outcome_writer/refresh/reject_materializer | ✅ 手寫 JSON 行 | ✅ 自產行 | ❌ **無**(兩側 fixture 各自自洽;Rust 測試 grep include_str/fixtures=0) |
| C3 | order_link_id 5 段格式 + FNV-1a lineage hash | bounded_probe_active_order.rs:518-539,605-632 | proof_exclusion.py:130-205(逐字元重實現)| ✅ 自產 id | ✅ 自產 id | ❌ **無 golden vector**(兩側同演算法但零共享測試向量) |
| C4 | 契約常量(PLAN_SCHEMA_VERSION/ADMIT_DECISION/ORDER_AUTHORITY_GRANTED/…)| demo_learning_lane.rs:17-26 | contract.py:3-16 | — | — | ❌(wiring contract 只掃 Rust token **名**,不比對值;tests/structure 63 檔 0 檔釘 demo-lane parity) |
| C5 | AdmissionConfig 默認值(24h/2/50.0/0.0)| demo_learning_lane.rs:40-46 | runtime_adapter.py:42-48 | ✅ validate | ✅ | ❌ 雙份字面量無 parity 釘 |
| C6 | Plan 檔路徑解析(env override 矩陣)| `OPENCLAW_DEMO_LEARNING_LANE_PLAN` override + data_dir 默認(writer.rs:40-42,207-231)| `_default_plan_path` **只認 OPENCLAW_DATA_DIR**(runtime_adapter.py:695-697)| ✅ 同源單點(Rust 內)| — | ❌ **無**——且 runtime 已真實分裂(見 §3 R2) |
| C7 | cutover 閘鍵 BYBIT_MODE / BYBIT_CONNECTOR_WRITE_ENABLED | **Rust 0 消費者**(全 rust grep=0)| settings_routes.py:993-1035 persist/status;restart_all.sh:826-863 只傳 API 進程 | n/a | ✅ settings 面(test_settings_bybit_demo_connector_mode.py)+ static | ❌ 無 runtime 強制點可測(見 F4) |
| C8 | PG fills → promotion 證據(`candidate_matched_demo_fills`)| engine 寫 fills(窗口未變)| learning_candidate_proof_evidence.py:265-273 消費 | ✅ apply_fill 既有 | ✅ gate/evidence 測試 | ❌ **producer 不存在於 repo**(全倉 grep 僅 2 consumer+2 test;lineage 斷點) |

窗口內已補好的(公平面,不再要求加閘):dispatch_retcode.rs 抽出 + dispatch_retcode_tests.rs(+598 行,10001/110001/110017/110043/110072 分類、Transport/JsonParse=Transient、NoCredentials/Signing/Other=Structural,close timeout 錯誤構造)、step_4_5_dispatch withhold 矩陣(+648 行測)、soak gate lane7+gate10、IMPL-B drift gate(E4 07-03 兩份回歸報告 PASS)。timeout/retCode/fail-closed/auth-expiry 四軸在**單語言層**無新增盲區。

## 2. v739 首批真 fill 將首次行經的未測路徑(P1-8 清單)

runtime ledger 實證(trade-core,read-only):388,798 行中 **ADMIT 決策 = 0 筆(兩種寫者格式皆 0)** → admit→probe 派單→Bybit demo 下單→fill→PG→proof 全鏈 runtime 從未走過。分段:

1. `evaluate_probe_admission` ADMIT 分支 → writer 直送 order_dispatch_tx(Rust 單測有;runtime 零流量)。
2. bounded probe 單 → bybit_rest_client demo REST 真下單 → retCode 真值(單測覆蓋分類;真連線 owed,Mac dev_disabled fail-closed by design)。
3. fill → private WS → apply_fill → PG trading.fills 帶 5 段 orderLinkId(C3 格式跨語言無 golden vector)。
4. fills → `candidate_matched_demo_fills` 證據匯出(**C8:producer 缺失,無實作無測試**)。
5. proof_exclusion 以 lineage hash 匹配 fill(C3 鏡像實現,drift 無測試防護)。
6. **且**:runtime 引擎 binary = 06-29 build(見 §3 R1),IMPL-A/IMPL-B 新測代碼根本不在運行 → v739 若不 rebuild+restart,首批 fill 行經的是「已被源碼取代、測試已對不上的舊二進位路徑」(deploy gate owed,呼應 E4 07-03 報告 I-4)。

## 3. Runtime read-only 證據(修正/補充凍結事實)

- **R1(修正凍結事實)**:現存在獨立 engine 進程 PID 2368227 `rust/target/release/openclaw-engine`,07-03 起,**CPU 36.1% / RSS 2.5GB**;binary mtime **06-29 19:28** → 落後源碼(不含 IMPL-A O(n²) ledger cache 修復與 soak 圍欄)。「主機無獨立 openclaw_engine 進程」在 07-03 凍結時點為真,現已過時。
- **R2(雙 plan 檔分裂,C6 實錘)**:engine env `OPENCLAW_DEMO_LEARNING_LANE_PLAN=/tmp/openclaw/cost_gate_learning_lane/bounded_demo_probe_soak_plan.json`(/proc/2368227/environ);該檔 generated_at=06-30T21:43Z(**stale>24h**)、envelope expires=07-01T09:02Z(**已過期**)。Python cron lane 每小時重寫的是**另一檔** `demo_learning_lane_plan_latest.json`(07-04T11:29Z,READY,無 envelope)。兩檔狀態互相矛盾;engine 以 stale 檔持續判 `PLAN_STALE_OR_MISSING_GENERATED_AT`(67,089 筆 Rust 行),Python 端自認 READY。
- **R3**:probe_ledger.jsonl = **472,803,902 bytes / 388,798 行**,始於 06-22;Python 格式行 62,761 筆(最新 07-04T11:29Z,cron 活著)+ Rust 格式行(最新 11:57Z,nanosecond RFC3339);決策直方圖(Rust 行):PLAN_STALE 67,089 / SIDE_CELL_NOT_SELECTED 63,846 / ADAPTER_DISABLED 1,184 / RISK_STATE_NOT_NORMAL 99 / OPERATOR_AUTHORIZATION_INVALID 64 / **ADMIT 0**。兩側 grep rotate/truncate/retention = 0。
- **R4**:crontab 5 條確認;cost_gate_learning_lane_cron 無 EXPECTED_HEAD 閘(實跑中);4 條 pin `OPENCLAW_EXPECTED_SOURCE_HEAD=00a78d92` vs runtime head 262596c6(stale pin);兩 cron log 0 bytes(06-24 起)。
- **R5**:engine env `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0`(probe 派單總開關 runtime OFF,對齊 1,184 筆 ADAPTER_DISABLED)。
- **R6**:uvicorn(PID 1038429,06-30 起)env 含 `BYBIT_MODE=demo`/`BYBIT_CONNECTOR_WRITE_ENABLED=true`——僅 API 狀態面(C7)。

## 4. 全量 findings

| # | title | severity | class | conf | defect_type |
|---|---|---|---|---|---|
| F1 | demo-lane 跨語言契約(C1-C5)零 golden-vector/parity test,等價性全靠人工鏡像 | HIGH | FACT | high | test-blindspot, drift-source-runtime, duplicate-logic |
| F2 | probe_ledger 無界成長(472MB/389k 行)+ 兩側全量重讀,零 rotation、零 scale/SLA 測試;runtime 已見 36% CPU/2.5GB RSS | HIGH | FACT(gap)/INFERENCE(CPU 歸因) | high/med | perf-hotpath, evolution-blocker, test-blindspot |
| F3 | Plan 檔路徑 env-override 跨語言不對稱(C6)→ runtime 雙檔分裂實錘(R2),無路徑契約測試 | HIGH | FACT | high | drift-source-runtime, hardcoded-config, test-blindspot, lineage-gap |
| F4 | ledger all-or-nothing 解析 + 型別/RFC3339 容忍不對稱(Rust 嚴/Py 寬),單壞行=Rust learning lane 靜默死亡;無毒行/torn-line 測試 | MEDIUM | FACT | high | test-blindspot, schema-issue, other(concurrency) |
| F5 | cutover 閘鍵 BYBIT_CONNECTOR_WRITE_ENABLED/BYBIT_MODE 零 runtime 強制消費者,治理語義=純表示層 | MEDIUM | FACT(0 consumer)/INFERENCE(表示層定性) | high/med | doc-stale, missing-gate |
| F6 | soak withhold 計數/envelope Indeterminate 無哨兵消費者;Rust warn 自述「healthcheck 哨兵另補」未兌現 → over-gate 誤殺不可觀測 | MEDIUM | FACT | high | missing-gate, over-gate, test-blindspot |
| F7 | markout exit 價無 max-delay 上界(entry 有 5min,exit 任意延遲),學習閾值輸入可被觀測缺口污染;無邊界測試 | MEDIUM | FACT(代碼)/INFERENCE(污染程度) | high/med | math-error, leakage, test-blindspot |
| F8 | candidate_matched_demo_fills producer 缺失(C8),fills→promotion 證據鏈斷點 | MEDIUM | FACT | high | lineage-gap, test-blindspot |
| F9 | v739 前置:runtime binary=06-29 build,IMPL-A/B 已測代碼未上線;PLAN_STALE 洪灌持續 | MEDIUM | FACT(binary mtime)/INFERENCE(v739 影響) | high | drift-source-runtime, other(deploy-gate) |
| F10 | engine_mode 正規化不對稱(Rust trim+lower vs Py exact-match dict) | LOW | FACT | high | duplicate-logic, drift-source-runtime |
| F11 | `is_bybit_safe_order_link_id_for_engine_mode`(4 段版)零生產 caller | LOW | FACT | med | dead-code |
| F12 | 4/5 cron pin stale EXPECTED_SOURCE_HEAD=00a78d92 + 兩 cron log 0-byte;head-gated cron 行為未驗 | LOW | FACT(pin)/ASSUMPTION(行為) | med/low | drift-source-runtime, other |
| F13 | 學習 SSOT(plan+ledger)在 /tmp(reboot 即滅)——corroboration,主審計他軸應已錄 | INFO | FACT | high | lineage-gap |
| F14 | probe_outcome 以 admission 時價 markout,未以真 fill 對賬(admitted-but-unfilled 同權計入);execution realism 有 review 模組但無 reconcile 測試 | LOW | INFERENCE | med | leakage, test-blindspot |

### 修復方向(不動手,交 E1)

- F1/C1-C5:建 checked-in golden fixtures(`rust/openclaw_engine/tests/fixtures/demo_lane_contract/`):(a) order_link_id 向量(輸入 side_cell/context/signal → 期望 id 字串);(b) envelope accept/reject 矩陣 JSON;(c) 兩側真實 writer 產出的 ledger 行樣本;(d) 常量清單 JSON。Rust include_str! 斷言 + Python 同檔斷言。任一側漂移即紅。
- F2:retention/rotation(段檔或 size cap)+ Rust 增量 tail 讀 + 100MB 合成 ledger 的 p50/p99 refresh SLA 測試。
- F3:跨語言路徑契約測試(env 矩陣:override set/unset × 兩語言解析結果一致)+ Python `_default_plan_path` 認 `OPENCLAW_DEMO_LEARNING_LANE_PLAN`;短期 ops:統一兩檔(屬 runtime mutation,PM/E3 裁)。
- F4:兩側各加「對方寫入樣本+毒行」fixture:Rust 讀 Python 真輸出、Python 讀 Rust 真輸出;毒行策略決策(skip-with-quarantine vs fail-closed)交 PA。
- F6:healthcheck 消費 soak_withheld_opens + Indeterminate 時齡上界告警(兌現 warn 註記承諾)。
- F7:exit 加 max_exit_delay_ms + 邊界測試(缺口→丟棄該 outcome 而非誤標)。
- F8:實作 fills→evidence 匯出器(read-only SELECT)+ 契約測試,或明文降級為 operator-hand 步驟。

## 5. 誠實聲明

- 本輪**零測試執行**(brief 指令:不重建 BASELINE 只審盲區;凍結 HEAD 自 07-03 基線後代碼未變)。「跑兩遍」協議 N/A。
- GUI 靜態(node --check)N/A:審計路徑零 .js 改動。
- 跨語言浮點 1e-4:demo lane 唯一共用數值=lineage hash(整數運算)與 markout bps(不跨語言),N/A 聲明。
- FNV-1a/base36 兩側等價性由逐行代碼比對確認(未以執行驗證——見 negative-space)。

## 6. Negative-space(本域應覆蓋但未展開)

1. 未以執行驗證 FNV hash/base36 跨語言等價(僅 code-read);re-probe:寫一組向量分別跑 python3 與 cargo test 快速比對。
2. 未掃 472MB ledger 是否已存在 torn/malformed 行(全檔 parse 成本);re-probe:trade-core 上 python3 逐行 json.loads 計數。
3. 未驗 head-gated cron(healthcheck/evidence audit)在 stale pin 下的實際行為(no-op vs 照跑);log 0-byte 無法區分。
4. 未深審 IBKR stock_etf fixture 方法的測試深度(dormant lane,窗口內 23 個新 IPC 方法僅確認 registry 測試存在)。
5. 未對 PG trading.fills 欄位 vs proof-evidence 期望鍵做 schema 對賬(producer 缺失使其暫為紙面契約)。
6. 未驗 uvicorn 4-worker 下 settings env 檔並發寫(_write_env_file_value 無鎖)的 race 測試缺口。
7. TW 軸(文檔去重)完全未碰——屬 TW agent 職域,本報告不越界。

## 7. 基線聲明

BASELINE 不變:`2026-07-03 passed=5492 failed=0`(rust workspace Linux debug, 8 ignored, 95 targets)。本輪無新基線行。

E4 AUDIT DONE: FINDINGS · report: docs/CCAgentWorkSpace/E4/workspace/reports/2026-07-04--e4_test_matrix_blindspot_audit.md
