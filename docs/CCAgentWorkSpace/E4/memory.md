# E4 Memory — 工作記憶

## 項目上下文（2026-04-01）

- 當前 Phase：Phase 3 Batch 3A 完成
- 測試基準：**3310 passed / 21 failed / 17 errors**（3349 collected）
- Pre-existing failures：17（與 March 31 一致）
- New failures：4 FAILED + 17 ERRORS（回歸問題）
- 系統模式：demo_only

## 工作記憶

### 2026-04-26 Wave 3 W5 兩軌（EDGE-P2-flip T2 + G2-FUP-IPC-LEGACY-MS-FIX）回歸驗證

**結論：E4 Pass with conditions（軌獨立 + 整體驗證綠；條件 = PM commit + push 後 Linux smoke 重跑）**

**Baseline 對齊：**
- Linux HEAD `60fdf74` (W4 三軌 commit 已 push)：cargo test 兩遍同綠 **2161 passed / 0 failed**（W5 純 Python 改動，Rust 不變符合預期）
- Mac local working tree 5 changes：軌 1 `passive_wait_healthcheck.py` +101 / `shadow_disagreement_breakdown.py` 新 592；軌 2 `ipc_client.py` +24/-1 / `test_ipc_client_hmac_ts_unit.py` 新 360；E1 memory.md 1 個

**§1 cargo test：** Linux 兩遍 2161/0 同綠，W4 已 push 進 baseline，W5 純 Python ✅
**§2 healthcheck [15]：** 4 次連跑 PASS dormant 訊息「decision_shadow_exits 24h=0 (Phase 1a dormant)」；軌 1 T2 升級 GROUP BY 切片屬 pre-warm code，dormant 路徑出口走 G6-02 baseline 一致 message（設計）
**§3 shadow_disagreement_breakdown.py 真機：** Linux HEAD 不含 W5 → MISSING；Mac sandbox 拒 scp（同 W4 教訓 #2）；Mac local psycopg2 缺 → 採靜態 ast.parse + MODULE_NOTE 結構審查 + Phase 1a dormant 出口設計驗證；E1 自跑 Linux dormant PASS 為 trust 基線
**§4 IPC HMAC unit test：** Linux 待 push（Step 4 規則明確跳過）；**Mac local 兩遍 3/3 PASS in 0.02s**（等效驗證 + 非 flaky）
**§5 ast.parse：** Mac local 4/4 全綠；Linux 2/4（2 W5 新檔尚未 push）
**§6 Rust verifier 對照：** mod.rs:534 verify_ipc_token + L621-628 ts 30s 容差 + L637 verify_slice constant-time；軌 2 testfile L73-90 _rust_verifier_accepts() 1:1 移植 0 偏差
**§7 async path :553 比對：** L553 一直 `int(time.time())` 秒制（E1 立場 ✅）；軌 2 fix 把 sync L809 從 `int(time.time() * 1000)` 對齊到 `int(time.time())` — 三者（async + sync + Rust）一致 Unix epoch 秒

**Mock 安全審查（PASS）：**
- `_FakeSocket` mock socket OS IO（合 E4 規則「✅ Mock 外部 IO OK」）
- `_rust_verifier_accepts()` **真跑 Python HMAC + abs 計算**（非 mock 業務邏輯）— mirror 對 verifier 真實覆蓋
- E4 規則「mock vs 真實 verifier 差異 = WARN」**0 WARN**

**1200 硬上限觀察（WARN 不 FAIL）：**
- `passive_wait_healthcheck.py` 2286（W5 +101 vs W4 2185）— PRE-EXISTING WARN（W4 已記錄，in-place 升級不阻塞）
- 其餘 3 檔皆 < 1200 OK

**條件 6 條（PM 必看）：**
1. PM commit + push 必須執行（W5 全 Mac local）
2. Linux git pull --ff-only 重跑 §4 軌 2 unit test（3/3 預期）
3. Linux git pull --ff-only 重跑 §3 dormant 路徑（exit 0 + JSON artifact）
4. [15] dormant message 是 W4 baseline 不是 T2 升級驗證 — T2 GROUP BY 真實運行需 shadow_enabled=true flip 後 cron 第一輪
5. passive_wait_healthcheck.py 2286 行建議下個 refactor wave 拆 dispatch_18_checks 子模組
6. E1 軌 2 testfile fixture 行數 self-report 325 vs 實 360（與 W3 G8-02 661 vs 838 同模式，建議 PA/E2 sanity check）

**3 條教訓：**
1. **W4 教訓 #2 重現驗證**：scp 被 Mac sandbox 阻擋是規則設計，**不繞過**，採等效驗證（Mac local pytest = Linux pytest 邏輯等效，純 Python + mock socket 無 Linux 特殊依賴）
2. **dormant 路徑 cron log 驗證 ≠ T2 升級邏輯驗證**：T2 GROUP BY runtime 需 shadow_enabled=true 翻轉，[15] 24h=0 fixed-message exit 是 G6-02/T2 共用 dormant guard。E4 必明示這條，避免 PM 誤以為 cron PASS = T2 已驗
3. **fixture self-report 行數**：W3 G8-02 fixture 661 報 / 838 實，W5 軌 2 testfile 325 報 / 360 實 — recurring pattern，建議 E1 task report template 加 `wc -l` exact 預填欄位

**Working tree 狀態：** 5 changes 全 Mac local，Linux HEAD `60fdf74`（不含 W5）。PM commit + push + Linux git pull --ff-only + ssh smoke test 應全綠。

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_w5_two_tracks_regression.md`

---

### 2026-04-26 Wave 3 W4 三軌（EDGE-P1b + EDGE-P2-flip + G2-03）回歸驗證

**結論：E4 PASS（三軌全綠 + 兩遍同綠 = 非 flaky）**

**Baseline 對齊：**
- Linux HEAD `55801fe` Rust release：**2138 passed / 0 failed**（不含三軌；Mac local working tree 21 changes 未 push）
- Mac local cargo test --release（含三軌 +23 tests）：**2161 passed / 0 failed**（兩遍同綠；對齊 E1 報告 2161 數字）
- 軌 1 +3（T3 IPC restore_exit_config_defaults handler tests）+ 軌 3 +20（防線 A 12 + 防線 B 8）= +23 ✅

**§1 cargo test 驗證：**
- 派發指定的 ssh Linux 跑 cargo PATH 缺失（ssh non-login shell 不載 ~/.cargo/env），workaround `source ~/.cargo/env` 後 Linux 端 baseline 2138 / 0 failed（HEAD 不含三軌符合預期）
- Mac local 第一次 2138（cargo cache 給舊 binary） / 第二次 rebuild 2161 — 兩遍同綠
- Sibling module 接線 grep：risk_checks.rs:1019 / risk_config.rs:579 / risk_config_tests.rs:1050 三 #[path] re-export 全在 cargo --lib 路徑

**§2 healthcheck 18 check：**
- 軌 1 [14] per-strategy 切片實測 deploy（cron log 03:02:15 CEST 跑出）：grid_trading=282[READY], ma_crossover=146[GROWING], bb_reversion=7[SPARSE], risk_close:fast_track_reduce_half=7[SPARSE], orphan_frozen=4[SPARSE] (READY_frac=63%)
- READY 閾值 ≥200 = calibrator min（對齊 ✅）
- SUMMARY 從 02:33 FAIL → 03:02 WARN（[12] G2-06 deploy 後 PASS；[11] 既有 WARN 與本軌無關）
- 18 check 完整：[1]-[15] + [16] + [Xa]/[Xb] + [18] = 18 PASS/WARN（不含 FAIL）

**§3 EDGE-P2-flip dry-run：**
- ssh Linux 跑 helper 報「No such file or directory」（檔案仍 Mac local，不在 Linux HEAD）
- artifact `/tmp/openclaw/edge_p2_flip_dry_run.json`（先前 E1 自跑留下）含 5/5 PASS：current_shadow_enabled=false / config_version=0 / IPC channel live / engine alive / revert payload symmetric

**§4 shell bash -n：3/3 wrapper 全綠（edge_p2_flip.sh 283 / edge_p2_revert.sh 208 / g2_03_bind_ma_sltp.sh 256）**
**§5 Python ast.parse：4/4 helper 全綠**
**§6 calibrator + summary：**
- calibrator smoke：synthetic 1-strategy 250-row → CALIBRATED（exit 0）
- summary 14d demo（scp + Linux PG, trading_admin user）：per-strategy markdown report 完整（dim×percentile 6×10 + profit cohort 子表 + tier 標籤 + Notes 防誤用警示）

**§7 1200 行硬上限驗（WARN 不 FAIL，per E4 規則 #3）：**
- ipc_server/mod.rs：1251（軌 1 +11 PRE-EXISTING）— WARN
- passive_wait_healthcheck.py：2185（軌 1 +99 PRE-EXISTING）— WARN
- risk_config.rs：1071（軌 3 抽 sibling 後實減 6 行 vs 1077 baseline）— OK
- risk_checks.rs：1020（軌 3 加 thin wrapper +140）— OK
- 三 sibling 全在 800 警告線內（191 / 294 / 308）

**6 條 push back / WARN 觀察（非阻塞）：**
1. 三軌仍只在 Mac local working tree — PM 必須統一 commit + push
2. ipc_server/mod.rs 1251 + passive_wait_healthcheck.py 2185 PRE-EXISTING — 建議 E5 refactor wave 拆 dispatch_request / check_*() 子模組
3. 軌 1 §5.1 stale_peak_ms / shadow_enabled 不在 IPC（toml_only）— 建議 follow-up 擴 update_risk_config IPC
4. 軌 2 §5.1 IPC HMAC ts unit legacy bug（app/ipc_client.py:786 毫秒 vs Rust 秒）— 建議 E5 修 legacy sync_ipc_call
5. 軌 3 §5.3 step_6_risk_checks.rs 未升級為 _with_override — 屬 G2-03 binding 真實啟用 PR 範圍，schema-only 此本輪 OK
6. summary 用 trading_admin user 連 PG（cron wrapper 範式）— 工具自身沒 wire DSN 構造路徑，需依賴外部 env

**3 條教訓：**
1. **派發鏈說明**：PM 直派 E1 → E4 跳過 E2，E4 須兼任 E2 必查 5 點 + E4 主驗 7 步驟（21 changes 全覆蓋）
2. **檔案不在 Linux 的應對**：軌 2/6 派發指定 ssh Linux 跑但檔案還在 Mac → 替代路徑 = (a) 跑 Mac local cargo test 驗 Rust （b) scp + 設 OPENCLAW_DATABASE_URL + activate venv 跑 Python helper 真機（c) 從 artifact JSON 反推 dry-run pass 狀態
3. **Linux PG user 注意**：`trading_admin`（per cron wrapper）非 `openclaw`；E4/E5 跑 ssh Linux SQL 工具須對齊 cron wrapper DSN 構造路徑

**Working tree 狀態：** 三軌 21 changes（11 modified + 10 new + 3 reports） 全 Mac local，Linux HEAD 仍 `55801fe`（不含三軌）。PM commit + push + Linux git pull --ff-only + ssh cargo test 重驗應 2161 / 0 failed 同綠。

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_w4_three_tracks_regression.md`

---

### 2026-04-26 Wave 3 G2-06 bb_breakout 永久 disable 回歸驗證

**結論：E4 PASS**

**測試結果：**
- Linux baseline (HEAD 8946e47, 不含 G2-06)：**2138 passed / 0 failed**（與 TODO L10 完全一致）
- Mac local cargo test --release（含 G2-06 5 行 Rust comment）：**2138 passed / 0 failed**（兩遍同綠 = 非 flaky）
- Mac cargo check：0 new warning（9 既有 warnings 與 G2-06 無關）
- Mac cargo doc + rendered HTML 驗證：`pub enum BbBreakoutProfile` 上方 `///` doc + `//` G2-06 plain block + `#[derive]` 排列下，rustdoc 完整保留 Conservative/Balanced/Aggressive/嚴格/寬鬆/當前生產 — `//` plain 不汙染 ✓
- Mac local Python 3.12 兩遍 healthcheck 函數測試：
  - `_read_bb_breakout_active_from_toml()` → `(False, "ok")` 同綠
  - `[18] check_disabled_strategy_inventory()` → PASS `disabled strategies: bb_breakout, funding_arb (active count=3: ...)` 同綠
  - `[12] check_bb_breakout_post_deadlock_fix(StubCur)` → PASS `disabled by G2-06 ... fill check skipped` 同綠（StubCur execute() 故意 raise — 證 active=false 早 return SQL 不執行 ✓）
- Python ast.parse: passive_wait_healthcheck.py / bb_breakout_threshold_sweep.py 兩檔 OK
- TOML 三環境 grep: demo/paper/live 全部 `[bb_breakout].active = false` + 雙語 G2-06 disable comment 模板一致

**3 條 non-blocking drift 觀察（PM commit 時可選 sweep）：**

1. **CLAUDE.md L488 §十一 一句話狀態「17 check」**：實測 main() 內 19 次 check_*() 呼叫（含 [Xa]/[Xb] 18，加 [18] 後 19）— 過期，但 §十一 是 2026-04-24 採集快照，G6-04 §三 drift 規則範圍但**不在 E1 任務界內**
2. **CLAUDE.md L82 「engine lib 1939 → 1980 passed」**：應為 2138（已 baseline）
3. **paper.toml `[funding_arb].active = true`**：demo/live 都 disabled 但 paper 仍 active —— 獨立 drift（per G-2 結案 2026-04-18 殘留），G2-06 範疇外，E1 沒擴大正確

**設計亮點 / 學到的事：**
- E1 §3.4「合法 orphan comment」風險點獨立驗證為真：rustdoc 仍 attach `///` doc 到 enum，`//` plain block 不汙染 — 但**驗證需要 cargo doc + 渲染 HTML grep**，光 cargo check 0 warning 不夠
- StubCur 反向 mock guard：故意 raise execute() 來**證明** active=false 時 SQL 路徑根本不執行，比 mock 業務邏輯更乾淨
- [18] disabled_strategy_inventory 只讀 demo TOML 是 Phase 1a 局限（paper/live 各自 disabled 看不到）— 適合當前 scope，未來可加 [19]/[20]
- baseline 數字源優先級：**TODO L10（2138）> Linux cargo 實測（2138）> CLAUDE.md §三 內各種中段數字（1939/1980 過期）**；E4 驗 baseline 必跑命令拿真數字，不信 CLAUDE.md 寫死

**派發鏈說明：** PM 直接從 E1 派 E4 跳過 E2 review，但本 E4 報告對 E2 必查 5 點（TOML 同方向 / [12] 不擴張 / [18] 純 observability / Rust doc-attribute / drift 規則）全部驗了一遍，等同 E2 + E4 合一通過。

**Working tree 狀態：** 所有 G2-06 改動仍 Mac local，Linux HEAD 8946e47（不含 G2-06）— 採 Mac local 直驗 + Linux baseline grep 雙路徑驗證。

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--g2_06_disable_regression.md`

---

### 2026-04-26 Wave 3 G8-02 ExecutorAgent decision parity 回歸驗證

**結論：E4 Pass with conditions**

**測試結果：**
- G8-02 testfile 獨立：5 passed / 2 skipped / agree=70/70 (100%) — 不 flaky（兩次同綠）
- control_api_v1 子集 baseline：2749→**2754 passed**（+5），35 pre-existing failed 不變（與 G8-02 無關）
- Rust engine lib：2138 / 0 fail 不變（G8-02 不動 Rust 代碼）

**35 pre-existing failed root cause（與 G8-02 無關，建議 PM 開新 ticket）：**
- `test_executor_shadow_toggle_api.py`（17）+ `test_strategist_promote_api.py`（18）
- 獨立跑 → 全綠；與 G8-02 + 兩檔組合 40 個一起跑 → 全綠
- 全量跑時 fail = test ordering pollution（推測 module-scope fixture 或 STORE / shadow_mode_provider singleton mutation）

**4 大 WARN（PM 必須清楚理解，oversell 風險）：**

1. **G8-02 是 Python runtime ↔ Rust schema spec parity，不是 Python ↔ Rust runtime parity**
   - `_reference_decide()` 是純 Python function 寫的 schema intent
   - 完全不打 Rust 引擎（無 cargo run / IPC dispatch / Rust deserialize 驗）
   - testfile line 35-40 自己 honest 標明：「it is *not* a re-implementation of Rust runtime, **it *is* the schema's intent**」
   - 真 Rust runtime parity 屬 G3-08

2. **70 case 100% agree 是邏輯上的必然，非 statistical confidence**
   - 兩邊都只判一個 bool（shadow_mode）
   - max_position_pct / per_symbol_cap 全 case 不 gate（Wave-3 scope，golden_15 自承「Rust catches」）
   - 95% binary threshold 寫進 test 是 future-proof（將來 shadow_mode 邏輯增複雜時的 regression 邊界）

3. **「synthetic_replay」術語 misleading**
   - 40 case 並非真實 `decision_outcomes` table dump
   - 是 procedurally generated boundary cases（隨機 ~20 symbol，shadow_mode true/false 各半）
   - PA RFC Q2 若定義廣義 synthetic OK，否則需與 PA 對齊

4. **E1 fixture 行數 self-report 誤差**：報 661 / 實 838

**Mock 邊界（PASS）：**
- ExecutorConfigCache._inject_snapshot_for_tests() 繞 IPC socket — OK
- paper_trading_routes._ipc_command 用 _IpcCallRecorder — OK
- ExecutorAgent.execute_order() / _execute_via_ipc() / shadow_mode_provider lambda chain 全真跑 — OK
- 不算 mock 業務邏輯

**Conditions（PM 合併前釐清）：**
1. close-out 報告 / TODO 條目加註 G8-02 不是真 runtime parity
2. synthetic_replay 術語校準
3. G3-08 必須補 cargo `tests/executor_parity_test.rs` 真 IPC dispatch
4. 35 pre-existing failed test isolation 開新 ticket
5. 教訓：fixture self-report 行數 PA/E2 必做 sanity check

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_g8_02_regression.md`

---

### 2026-04-24 全程序範圍測試檢驗（full-chain testing audit）

**結論：A-（優秀）— 測試充分，但 CI 完全不存在 + 6 個 error-path 缺口阻塞 Live**

**覆蓋面快照（grep-based，非實跑）：**
- Rust engine inline：149 檔 / ~2,103 `#[test]`/`#[tokio::test]`（對應 §三 lib 1980 passed 基準，差值為 `#[ignore]` / feature-gated）
- Rust engine integration：`tests/*.rs` 7 檔 / **85 測**（stress 35 / reconciler_e2e 19 / edge_predictor_ort ~10 / micro_profit_fix 7 / migrations 5 / phase4 3 / rrc1 ~6）
- Python pytest：121 檔 / **~3,006** 測（控制 API 93/2687 + ml_training 26/292 + audit+local_model_tools 2/31；與 §十一 pytest 2996 承襲基準吻合）
- Healthcheck：`passive_wait_healthcheck.py` 12 checks（[1]~[12]，[8] shadow_exits L2-5 TOML 主動診斷 / [10] 4/17 post-mortem / [11] EDGE-DIAG-1 Phase 3 auto-gate / [12] FIX-26 驗收）
- **CI：0 workflow 檔**（`.github/workflows/` 不存在）
- **獨立 smoke 腳本：0**（canary `test_canary.py` 未驗；rollback_drill.sh 是 operational）

**5 項評估維度結果：**
1. 正常路徑：A-（tick_pipeline 120 測 / 策略 5 個全備 / 5-Agent 齊 / Decision Lease + Auth + hot-reload 完整）
2. 邊界：B+（qty=0/HMAC/leader lock 已覆蓋；funding_rate 極端 / ATR NaN/Inf / balance=0 / UTC 時邊界 / auth TTL=exp 未補）
3. 異常：B-（REST fail-closed 齊；但 **WS 斷線止損 / DB 斷線 / IPC 超時 / config 破損熱重載 / authorization 篡改 / intents writer 失敗** 全缺）
4. 並發：A-（leader lock multiprocess 齊 / Reconciler 100-cycle + 50 symbols + 20 rapid 齊；ArcSwap torn-read + IPC 多 worker 共享 slot 缺）
5. 回歸：A-（FIX-26 7測 + FA-PHANTOM-1/2 + MICRO-PROFIT 7 + PNL-FIX 隱含 + RUST-DOUBLE-PREFIX healthcheck 守門；STRATEGY-CLOSE-TAG-FIX `strip_phys_lock_prefix` 缺 unit）

**Top 10 Blocking Gaps（排序對齊 Live 日期 W24 末 ~2026-05-23）：**
1. **[P0] CI 完全不存在**（`.github/workflows/` 缺）
2. **[P0] ExecutorAgent shadow→live 切換契約無測**（阻 G-1）
3. **[P1] WS 斷線期間止損安全性**（§四 E-1）
4. **[P1] PostgreSQL 斷線期間 Rust writer 行為**（§四 E-2）
5. **[P1] trading.intents 寫失敗 unit regression**（只靠 healthcheck [10]）
6. **[P1] authorization 簽名篡改 engine 行為**（§四 E-10）
7. **[P1] ArcSwap torn-read under tick spike**（§五 C-1）
8. **[P1] 21d demo 穩定 aggregate healthcheck**（違 §七「被動等待必附 check」）
9. **[P1] PostOnly maker fill rate healthcheck**（違 §七）
10. **[P2] STRATEGY-CLOSE-TAG-FIX `strip_phys_lock_prefix` unit regression**

**關鍵對齊：**
- 12 healthcheck 對應 §三 active 被動等待 90%；H-1/H-2/H-3 違 §七 新被動等待規則，必補
- Python stop_manager.py 已退役（3E-ARCH 後）— 2026-04-01 報告敘述「319 LOC」過期
- IPC handlers inline 0 測，但 `ipc_server/tests/` sub-dir 覆蓋（dispatch 10 / config 8 / risk 7 / budget 7）— 分位正常

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-24--full_chain_testing_audit.md`

---

### 2026-04-01 全程序測試審計

**結論：PASS（有條件）— 整體進步顯著，但有 4 個新回歸需修復**
- 測試文件：71 → 96（+25）
- 測試 cases：~2,480 → 3,349（+869）
- passed：~2,480 → 3,310（+830）
- 估算覆蓋率：~62% → ~68%（+6pp）
- 關鍵改善：pipeline_bridge 15%→50%，governance_routes 10%→45%，ws_listener 20%→65%，demo_connector 8%→60%
- 新增回歸：4 FAILED（h0_gate sync、inverse leverage、session9 count、strategies OrderIntent）+ 17 ERRORS（session9 import）
- 最大缺口：strategy_auto_deployer 685 LOC 零測試、bybit_demo_sync 269 LOC 僅 1 間接
- 報告位置：docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-01--testing_audit.md + docs/audit/April01/E4_testing_report_2026-04-01.md

### 2026-03-31 Sprint 5b 全量回歸

**結論：PASS**
- 總計：2610 passed, 17 failed（全部 pre-existing）, 1 skipped
- 收集：2628 tests collected
- 執行時間：~59.65s
- 目標 ≥ 2600：✅ 達成（2610 passed）
- 17 pre-existing failures 清單與預期完全一致，無新增 failure
- 測試基準更新：**2610 passed**（較上次 2599 +11）

**新增測試（相較上次基準 2599）：+11 tests**
- test_h_chain_integration.py（TestPrinciple14OllamaFallback × 6）：全部 PASS
- test_scout_worker.py（× 10）：全部 PASS
- roi_basis / cost_tracker / ollama_call 標記測試（7 個）：全部 PASS

### 2026-03-31 Sprint 5b-5 根原則 14 集成測試（Principle 14 Ollama Fallback）

**結論：PASS**
- 新增測試：6（TestPrinciple14OllamaFallback）
- 文件位置：`tests/test_h_chain_integration.py`
- 全量回歸：2599 passed, 17/18 failed（全部 pre-existing），1 skipped
- 目標 ≥ 2576 + 6 = 2582：✅ 達成（2599 passed）

**6 個測試行為驗證：**
1. `test_ollama_unavailable_strategist_uses_heuristic`：is_available=False → judge_edge 不被調用，heuristic_evaluations 遞增
2. `test_ollama_unavailable_h1_budget_check_passes`：cost_tracker=None → _h1_check_budget() 返回 True（fail-open）
3. `test_ollama_unavailable_pipeline_bridge_processes_intents`：PipelineBridge._process_pending_intents() 無 Ollama 時不崩潰
4. `test_ollama_unavailable_h0_gate_still_blocks_bad_intents`：H0 Gate 確定性邏輯不依賴 Ollama，freshness check 仍阻擋
5. `test_ollama_unavailable_executor_still_applies_fail_closed`：acquire_lease()=None → ExecutorAgent 拒絕執行（原則 3 不依賴 Ollama）
6. `test_ollama_crash_mid_evaluation_falls_back`：_ai_evaluate 中 ConnectionError → catch + heuristic fallback + error 計數

**關鍵發現：**
- PipelineBridge 需要 3 個必填位置參數（kline_manager/indicator_engine/signal_engine）
- 所有降級邏輯均在 _evaluate_edge() 中正確實現（is_available=False 或異常均走 heuristic）
- H0 Gate 完全不依賴 Ollama（純確定性）
- ExecutorAgent 的 Principle 3 執行與 Ollama 狀態無關

**測試基準更新：2599 passed**（較上次 2576 +23）

### 2026-03-31 Sprint 5a 回歸（Position Sizing + Paper/Demo Sync）

**結論：PASS**
- 總計：2576 passed, 17 failed（pre-existing）, 1 skipped
- 收集：2594 tests collected
- 執行時間：~37.60s
- 目標 ≥ 2575：✅ 達成（2576 passed）
- 17 pre-existing failures 清單與預期完全一致，無新增 failure

**新增測試（相較上次基準 2561）：+15 tests**
- test_strategist_agent.py：15 tests（TestScoutStrategistChain 2 + TestH1ThoughtGate 11 + TestStrategistShadowFalse 2）
- H0 Gate 測試（test_h0_gate.py）：94 tests，全部通過

**已知 pre-existing failures（17 個，全部歸屬明確）：**
- test_batch10_learning_oms.py（2）：TestL2CronTrigger（asyncio event loop deprecation）
- test_edge_filter_integration.py（1）：test_edge_filter_respects_timeout
- test_integration_phase11.py（2）：TestEngineTierEnforcement（L1 reject submit/cancel）
- test_learning_tier_gate.py（1）：test_l1_capabilities
- test_ollama_integration.py（11）：LocalLLMSearchProvider（3）+ L1TriageLocalFallback（8）

### 2026-03-31 Sprint 0 回歸（G-05 + G-01）

**結論：PASS**
- 總計：2561 passed, 17 failed（pre-existing）, 1 skipped
- G-05 TestExecutorAgentDecisionLease：6/6 PASS（test_26～test_31）
- G-01 test_layer2.py：79/79 PASS
- 17 pre-existing failures 清單與預期完全一致，無新增 failure

**重要教訓：**
- pytest 收集 `test_app` 時有 PytestCollectionWarning（fastapi app instance，非真正問題）
- Pydantic V1 deprecated warnings 在 scout_routes.py（不影響功能）

### 2026-03-31 Wave 6 Sprint 0 TD-1 全量回歸（pipeline_bridge acquire_lease）

**結論：PASS**
- 總計：2614 passed, 17 failed（全部 pre-existing）, 1 skipped
- 收集：2632 tests collected
- 執行時間：~63.27s
- 目標 ≥ 2614：✅ 達成（2614 passed）
- 17 pre-existing failures 清單與預期完全一致，無新增 failure
- 測試基準更新：**2614 passed**（較上次 2610 +4）

**4 個 TestPipelineBridgeDecisionLease 測試（全部 PASS）：**
1. `test_td1_no_hub_fail_open_submit_proceeds`：hub=None → fail-open，submit 繼續
2. `test_td1_acquire_lease_none_fail_closed_submit_blocked`：acquire_lease()=None → fail-closed，submit 阻擋
3. `test_td1_acquire_lease_success_submit_proceeds`：acquire_lease() 成功 → submit 繼續
4. `test_td1_acquire_lease_exception_fail_closed`：acquire_lease() 拋異常 → fail-closed，submit 阻擋

**位置：** `tests/test_edge_filter_integration.py::TestPipelineBridgeDecisionLease`

### 2026-03-31 Wave 6 Sprint 1b 1B-1 Cooldown 聯動煙霧測試

**結論：PASS**
- 5 個測試全部 PASS（test_h0_gate_cooldown_integration.py）
- 全量回歸：2624 passed, 17 failed（全部 pre-existing）, 1 skipped（第二次穩定跑，無新增 failure）
- 目標 ≥ 2614：✅ 達成（2624 passed）
- 測試基準更新：**2619 passed**（保守估計：2614 + 5 新增；最新穩定跑 2624 但有測試順序影響波動）

**5 個新增測試（TestH0GateCooldownIntegration）：**
1. `test_risk_manager_pushes_cooldown_to_h0gate`：RiskManager 3連敗 → mock H0Gate.update_risk() 被調用，snapshot.cooldown_until > now ✅
2. `test_h0gate_blocks_during_cooldown`：update_risk(future cooldown) → check() allowed=False, check_name="cooldown" ✅
3. `test_h0gate_allows_after_cooldown_expires`：update_risk(past cooldown) → check() allowed=True ✅
4. `test_h0gate_cooldown_zero_does_not_block`：cooldown_until_ts_ms=0 → check() allowed=True ✅
5. `test_h0gate_cooldown_check_includes_reason`：blocked → reason.lower() contains "cooldown", check_name="cooldown" ✅

**關鍵發現：**
- H0Gate.check() 冷卻期判斷邏輯：`cooldown_until > 0 and now_ms < cooldown_until` → 正確
- RiskManager.record_fill_result() 在 consecutive_losses >= cooldown_count 時呼叫 H0Gate.update_risk()，保留現有 open_position_count/total_exposure_pct/kill_switch_active 不變 → 設計正確
- test_h0_gate.py::TestGovernanceRoutesH0GateStatus 在全量跑時偶發 3 失敗（模組狀態干擾），單獨跑全部通過，為 pre-existing 間歇性問題，與本 Sprint 無關

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-04-26 | Wave 3 W5 兩軌（EDGE-P2-flip T2 + G2-FUP-IPC-LEGACY-MS-FIX）回歸驗證（E4 Pass with conditions / Linux cargo 2161 兩遍同綠 / Mac local pytest 兩遍 3/3 / [15] dormant 路徑 PASS / Rust verifier 1:1 mirror / async :553 一直秒制 / 6 conditions for PM commit+push 後 Linux 重跑） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_w5_two_tracks_regression.md` |
| 2026-04-26 | Wave 3 W4 三軌（EDGE-P1b + EDGE-P2-flip + G2-03）回歸驗證（E4 PASS / Mac local 2138→2161 +23 兩遍同綠 / 18 check 含 [14] per-strategy READY_frac 63% / dry-run 5/5 / bash -n 3/3 / ast.parse 4/4 / calibrator 250-row CALIBRATED / summary 14d markdown / 2 PRE-EXISTING WARN 1200 hard limit non-blocking） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_w4_three_tracks_regression.md` |
| 2026-04-26 | Wave 3 G2-06 bb_breakout 永久 disable 回歸驗證（E4 PASS / Rust 2138 不變兩遍 / Mac local Python 3.12 兩遍 healthcheck 同綠 / cargo doc 證 //G2-06 plain 不汙染 ///doc / 3 條 non-blocking drift） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--g2_06_disable_regression.md` |
| 2026-04-26 | Wave 3 G8-02 ExecutorAgent decision parity 回歸驗證（E4 Pass with conditions / +5 passed / Rust 2138 不變 / 4 WARN oversell 風險） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_g8_02_regression.md` |
| 2026-04-24 | Full-chain Testing Audit（Rust 2103 inline + 85 integration / Python 3006 / HC 12 checks / CI 0 / Top 10 gaps） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-24--full_chain_testing_audit.md` |
| 2026-04-01 | 全程序測試覆蓋評估（3310 passed / 96 test files / 18 無測模塊） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-01--testing_audit.md` |
| 2026-03-31 | Wave 6 Sprint 1b 1B-1 Cooldown 聯動煙霧測試（5 tests，2624 passed） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint1b_cooldown_smoketest.md` |
| 2026-03-31 | Wave 6 Sprint 0 TD-1 全量回歸（2614 passed，acquire_lease 修復驗收） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint0_td1_regression.md` |
| 2026-03-31 | Sprint 5b 全量回歸（2610 passed，Sprint 5b 最終驗收） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5b_regression.md` |
| 2026-03-31 | Sprint 5b-5 根原則 14 集成測試（Principle 14 Ollama Fallback，6 tests） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5b_p14_tests.md` |
| 2026-03-31 | Sprint 5a 全量回歸（Position Sizing + Paper/Demo Sync） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5a_regression.md` |
| 2026-03-31 | Sprint 0 全量回歸（G-05 + G-01） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint0_regression.md` |
