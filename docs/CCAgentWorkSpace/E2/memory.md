# E2 Memory — 工作記憶

## 項目上下文（2026-03-31 更新）

- 當前 Wave：Wave 6 Sprint 1a+1b 審查完成（Sprint 1a CONDITIONAL PASS，P1 修復後 commit）
- 測試基準：2614 passed（Sprint 0 TD-1 後）；Sprint 1a+1b 全部通過後預期 2623 passed
- 系統模式：demo_only

## 審查強制清單（每次 Code Review 必查項）

### 雙語注釋合規（必查，不通過則打回 E1/E1a）
以下情況必須打回重做：
- [ ] 新建函數/類缺少中英雙語 docstring
- [ ] 模塊頂部缺少 `MODULE_NOTE`（中英雙語模塊說明）
- [ ] fail-closed 路徑沒有注釋說明 fallback 原因
- [ ] 安全相關代碼（認證/授權/參數化查詢）沒有注釋說明用意
- [ ] 修改了已有函數但沒更新 docstring（過時的注釋比沒注釋更危險）

注釋質量標準：
- 注釋應說明「為什麼」，而非只是翻譯「是什麼」
- 中英兩段都要有實質內容，不接受機器翻譯式的逐字對照

### 安全審查（必查）
- [ ] innerHTML 賦值：必須有 ocEsc() 包裝
- [ ] SQL 查詢：必須參數化（無字符串拼接）
- [ ] 異常處理：無 `except: pass` / 無吞異常
- [ ] HTTPException：有 `except HTTPException: raise` 穿透

### 架構合規（必查）
- [ ] 新的 governance 路徑：有 `_require_operator_role()` 驗證
- [ ] 任何 `submit_order()` 調用：前面有 `acquire_lease()` 且 fail-closed
- [ ] 治理不可通過環境變量禁用（無 OPENCLAW_GOVERNANCE_ENABLED 類型的 flag）

### 測試合規（必查）
- [ ] 新功能有對應測試，測試數 ≥ 任務前基準（當前 2555）
- [ ] 邊界用例：None 注入、超時、崩潰路徑有測試

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-03-31 | Sprint 0 G-05+G-01 審查 | workspace/reports/2026-03-31--sprint0_g05_g01_review.md |
| 2026-03-31 | Sprint 5a 完整審查 | workspace/reports/2026-03-31--sprint5a_review.md |
| 2026-03-31 | Sprint 5b 完整審查 | workspace/reports/2026-03-31--sprint5b_review.md |
| 2026-03-31 | Wave 6 Sprint 0 TD-1 審查 | workspace/reports/2026-03-31--sprint0_td1_review.md |
| 2026-03-31 | Wave 6 Sprint 1a+1b 審查 | workspace/reports/2026-03-31--sprint1a1b_review.md |
| 2026-04-26 | Wave 3 G2-02 + G8-02 審查 | workspace/reports/2026-04-26--wave3_e1_review.md |
| 2026-04-26 | Wave 3 G2-06 bb_breakout 永久 disable 審查 | workspace/reports/2026-04-26--g2_06_disable_review.md |
| 2026-04-26 | Wave 3 第四波三軌 adversarial review（EDGE-P1b + EDGE-P2-flip + G2-03）| workspace/reports/2026-04-26--wave3_w4_three_tracks_review.md |
| 2026-04-26 | Wave 3 W5 兩軌（EDGE-P2-flip T2 + G2-FUP-IPC-LEGACY-MS-FIX）adversarial review | workspace/reports/2026-04-26--wave3_w5_two_tracks_review.md |
| 2026-04-26 | Phase 1+2 batch review 10 commits (df1d629..bd5ce56) | workspace/reports/2026-04-26--phase1_2_batch_review.md |
| 2026-04-26 | Tier 3 batch review 5 commits (7564d07..31fa96c) + G9-05 PUSH-BACK | workspace/reports/2026-04-26--tier3_batch_review.md |
| 2026-04-26 | Tier 4 batch review 6 commits (eb65e1e..4689fc8) + MIT EXIT-FEATURES-WRITER-BUG-1 audit + PM merge | workspace/reports/2026-04-26--tier4_batch_review.md |

## 歷史審查關鍵發現（累積記憶）

### 2026-03-31 Sprint 0 G-05 + G-01
- **結論**: PASS，可進入 E4
- **測試基準**: 2561 passed（G-05 新增 6 個 Decision Lease 測試 test_26~31）
- **G-05 架構確認**: acquire_lease() 在 submit_order() 之前，lease=None 時 early return（fail-closed 正確），hub=None 時 fail-open（向後兼容，設計意圖明確）
- **G-01 確認**: DEFAULT_DAILY_HARD_CAP_USD=2.0，DOC-08 §4 來源注釋在位，tab-ai.html `|| 15` 迭代預設值未被修改，定價 `15.00` per_mtok 未被修改
- **WARN（P2 追蹤）**: `error=f"Execution error: {e}"` 動態異常字符串在外層 exception 捕獲路徑（executor_agent.py:415）。Batch 11 原有代碼模式，建議 P2 改為固定字符串。
- **WARN（P2 追蹤）**: `error=f"Order rejected: {rejected_reason}"` 同上，来源為 paper engine 返回值，風險可控但不理想。

### 2026-03-31 Sprint 5a（H0 blocking + H1 ThoughtGate + shadow=False + H3 ModelRouter）
- **結論**: PASS，可進入 E4
- **測試基準**: 2879 passed（新增 15 個 Sprint 5a 測試）
- **H0 blocking 確認**: pipeline_bridge.py `continue` 已替換 warn-only；`intents_h0_blocked` 統計正確；4 個 TestH0GateBlocking 全部通過
- **H1 ThoughtGate 確認**: 三個 gate（budget/complexity/cooldown）均正確降級到 `_heuristic_evaluate()`；`should_call_ai=False` 路徑無 allow-all
- **架構約束確認**: 整個 H1/H2/H3 鏈路零 `await`；L2 在 `threading.Thread(daemon=True)` 執行
- **shadow=False 確認**: 前置條件（G-05 acquire_lease + H0 blocking）均已驗證
- **WARN-1（P2）**: `cost_tracker.record_call()` 的 `except Exception: pass` 缺少 logger（L485）
- **WARN-2（P2）**: `_h1_cooldown` 字典無容量上限（650 符號場景安全，但建議 P2 追蹤加 LRU cap）
- **重要觀察**: Sprint 5a 代碼順帶修復了 11 個 pre-existing test failures（34 → 23 FAILED）

### 2026-03-31 Sprint 5b（H4 validate_output + H5 record_ollama_call + ScoutWorker + P14 集成測試）
- **結論**: PASS，可進入 E4
- **測試基準**: 2609 passed（新增 54 個 Sprint 5b 測試）
- **H4 fail-closed 確認**: `_validate_ai_output()` 返回 False → `_heuristic_evaluate()`（無 allow-all）；h4_validation_fail + heuristic_evaluations 雙重計數器在位
- **原則 10 roi_basis 確認**: `get_cost_summary()` 和 `get_cost_edge_ratio()` 均含 `roi_basis: "paper_simulation_only"` + `roi_disclaimer` 中文字段
- **ScoutWorker daemon 確認**: daemon=True + except Exception 吞但記錄日誌 + phase2 初始化在 try/except 包裹 + 非致命
- **新 failure 調查**: 18 FAILED = 17 pre-existing + 0 Sprint 5b 新增（git stash diff 驗證）
- **WARN-1（P2）**: `_ollama_stats` 懶初始化在方法體，建議遷移至 `__init__`（功能正確，純可讀性）
- **WARN-2（P2）**: ScoutWorker interval 不可運行時配置（建議 P3 環境變量覆蓋）
- **WARN-3（P2 繼承）**: `cost_tracker.record_call()` 的 `except Exception: pass`（Sprint 5a 遺留）

### 2026-03-31 Wave 6 Sprint 0 TD-1（pipeline_bridge acquire_lease 門控）
- **結論**: PASS，可進入 E4
- **測試基準**: 2614 passed（Sprint 0 TD-1 新增 4 個 TestPipelineBridgeDecisionLease 測試）
- **架構確認**: acquire_lease() 在 submit_order() 之前，APPROVED/MODIFIED 兩分支共用同一 acquire_lease 門控（L697），REJECTED 分支直接 continue 不到達門控（正確）
- **fail-open/fail-closed 確認**: hub=None → fail-open 正確；lease=None → fail-closed + 計數器；異常 → try/except logger.error + 計數器（無吞異常）
- **WARN（P2）**: `intents_lease_failed` 未在 `__init__` self._stats 初始化塊預設為 0，其他 stats 均預初始化。功能正確（.get() 防 KeyError），但 GUI/API 消費者若期待 key 始終存在可能遇到 None。建議 P2 在 L114 的 `_stats` dict 中加 `"intents_lease_failed": 0`。

### 2026-03-31 Wave 6 Sprint 1a（FA-7）+ Sprint 1b（1B-2/TD-3/TD-4）
- **結論**: CONDITIONAL PASS — Sprint 1b 全 PASS；Sprint 1a 有 1 個 P1 問題需修復後方可提交
- **測試基準**: 預期 2614 + 4 + 3 + 2 = 2623 passed（4 FA-7 + 3 freshness + 2 TD-4）
- **Sprint 1a P1 問題**: `_check_stops()` FA-7 塊在 `submit_order()` 返回 rejected_reason 時仍調用 `_emit_round_trip()`，注入假的學習信號。應在 L954 before the `try:` block 加 `if result.get("rejected_reason"): skip _emit_round_trip`。
- **Sprint 1a 架構確認**: `_emit_round_trip()` 在 `submit_order()` 之後（不在失敗分支），try/except non-fatal，perception_plane=None 路徑安全（不崩潰），PnL 方向正確（Sell=多頭，Buy=空頭）
- **Sprint 1a 雙語注釋**: PASS（FA-7 塊 + except 路徑均有中英雙語）
- **Sprint 1b freshness 確認**: getattr 安全鏈（_price_ts / _config / max_data_age_ms），None config 路徑 getattr(None, "max_data_age_ms", 1000) = 1000 正確，HTTPException 穿透在位
- **Sprint 1b TD-3 確認**: except Exception: pass → logger.warning (with `as e`)，非致命路徑繼續不 re-raise，正確
- **Sprint 1b TD-4 確認**: 觸發時機 `>= _H1_COOLDOWN_MAX_SIZE` 正確，清理策略（過期條目，30s window），熱路徑（len < cap）零額外開銷，雙語注釋在位
- **pre-existing `except Exception: pass` at L885**: 覆蓋狀態讀取（非 submit_order），有說明注釋，非新引入，P2 追蹤
- **WARN（P2）**: FA-7 tests 缺少 short position PnL 符號測試（Buy side = 空頭止損）
- **WARN（P2）**: freshness tests 缺少 `_price_ts` 屬性完全不存在（del）的覆蓋路徑

### 跨審查觀察（模式記憶）
- ExecutorAgent 的異常 error 字段格式問題已出現兩次，建議建立統一規範：審計字段使用固定 snake_case 錯誤碼，動態信息僅進入 logger。
- phase2_strategy_routes.py 的模塊初始化（`try: from ... except ImportError: pass`）模式貫穿全文件，是已驗證的安全 fallback 模式，E2 不需要每次審查都標記。

### 2026-04-26 Wave 3 G2-06 bb_breakout 永久 disable — PASS to E4 with separate ticket recommendation
- **結論**：PASS to E4（with 1 separate ticket recommendation）
- **必查 3 點全 PASS**：(a) TOML 三環境（demo/paper/live）`[bb_breakout].active=false` 同方向 ✅ (b) healthcheck [12] 改判邏輯不擴張（fail-soft + 早 return PASS skip + StubCur 驗 SQL 0 次執行）✅ (c) CLAUDE.md §三 G6-04 drift 規則符合（採集時間 + healthcheck id + commit hash）✅
- **E1 funding_arb push back 判定**：技術上正確（不擴大 G2-06 scope），但 adversarial 視角揭發 F2（MEDIUM）— paper TOML `[funding_arb].active=true` 是 v1 (2026-04-14) → v2 (2026-04-18) 結案 NEGATIVE EDGE 過渡期 sync miss，非「三 config 故意分開」。memory `feedback_env_config_independence` 適用於 risk threshold（fee/cost/freshness），不適用於 `active` binary 開關。建議 PM 開 G2-FUP-FUNDING-ARB-PAPER-SYNC（~5min）
- **F1 (LOW)**：[18] inventory 只讀 demo TOML 單檔，跨環境誤導風險（E1 5.6 已 self-disclose）
- **F3 (LOW)**：healthcheck.py 文件 2103 行 > §九 1200 硬上限（既存技術債，非 G2-06 引入）
- **F4 (LOW)**：[18] 在 `--quiet` 模式下被 hide（drift 防線設計打折），但 cron 6h default 無 quiet → 實際運作 OK
- **F5 (INFO)**：Rust comment block 設計合理 — `///` + `//` + `#[derive]` sandwich pattern 不破壞 doc-attribute attachment（cargo doc + 最小 reproducer diff 0 byte 雙重驗證）
- **判定方法論教訓（補 §三 累積）**：
  - `feedback_env_config_independence` 三 config 故意分開 protocol 適用於**風控閾值**（fee/cost/freshness/buffer），**不適用於策略 active 開關**（active 是 binary 結案/啟用）
  - 凡是「策略結案 disable」必須**全環境同步 disable**，不享受三 config 分開保護
  - 收到 E1 push back 時必獨立做 evidence chain（memory + TOML comment + 結案歷史）— 不以 E1 詮釋為準
  - Rust `///` doc-comment + `//` plain comment + `#[derive]` 三明治 pattern 是合法的，但若不確定 → 用最小 reproducer + cargo doc diff 雙重驗證

### 2026-04-26 Wave 3 G2-02 + G8-02 — 兩交付 PASS with conditions
- **結論**：PASS with conditions（兩交付主體 OK，但 2 個 MEDIUM finding 必修）
- **G2-02 (counterfactual replay)**：
  - E1 push back（PM SQL spec schema 錯）✅ 正確且必要 — 我獨立 grep V003/V008/V015/V017 schema 確認 PM spec 7 個欄位都不存在
  - 「`realized_pnl` 是 GROSS」結論 ✅ 屬實 — 我獨立讀 `fill_engine.rs::apply_fill` line 264/273-279/`trading_writer.rs:307` 三點交叉確認
  - **新揭發 (G2-02-F1, MEDIUM)**：partial-close（fast_track ReduceToHalf）+ accumulate（多筆 entry）下，counterfactual 公式假設「1 entry × 1 close per JOIN row」會偏差；E1 docstring 沒揭露
  - LOW: JOIN 缺 `entry.engine_mode/symbol` 防禦（理論 collision，極端 edge）
  - LOW: exit code 寬鬆解讀 — E1 已聲明 PM 接受
- **G8-02 (parity test)**：
  - E1 push back（cap/pct deferred to G3-08）✅ 技術正確 — 我獨立 grep `intent_processor/` 確認 cap/pct 0 命中 + Python `_execute_via_ipc` 0 cap/pct check
  - **70 case 100% agree 是 trivially guaranteed**（兩側都讀同一 boolean），但**仍有價值** — 保護 G3-03 修復不被 regression
  - **新揭發 (G8-02-F1, MEDIUM)**：「synthetic_replay」嚴重命名誤導 — 40 case 全是手寫 YAML 字面量，無 seed/generator/replay。文檔欺騙性強
  - LOW: dead imports `asyncio` / `os` — E2 已直接 fix
  - LOW: setup/teardown `_reset_for_tests()` 是 dead code（本地 cache 實例不是 singleton）
- **判定方法論教訓**：
  - 凡是 SQL JOIN 的 counterfactual 工具，必查 partial close / accumulate / cross-strategy 三類 edge case 對 row count 的影響
  - 凡是「parity test」名稱，必驗證兩側是否真的跨進程（Python ↔ Rust runtime），不是「Python ↔ Python schema-spec mock」
  - 凡是「synthetic / replay / generated」字眼，必驗證實際代碼是否有 generator / seed / 真實資料源
  - E1 push back 即使技術正確，也要 adversarial 重審其副作用（命名 / doc 透明度）— PM 接受不代表 E2 不能找新問題

### 2026-04-26 Wave 3 第四波三軌（EDGE-P1b + EDGE-P2-flip + G2-03）— 3 軌獨立 PASS with conditions
- **3 軌 PASS to E4**（不綁包）：軌 1 EDGE-P1b 4 子任務 / 軌 2 EDGE-P2-flip T1+T3 / 軌 3 G2-03 4 子任務
- **HMAC ts bug 完整驗證**（軌 2 最關鍵）：legacy `app/ipc_client.py:786 sync_ipc_call` 用毫秒、Rust verifier 用秒（30s 容差量級差 1000x）→ **legacy 100% fail auth**。E2 grep 確認 2 個 production caller（`live_trust_routes.py:296 trigger_live_auth_recheck` + `control_ops.py:515 set_system_mode`）皆「fire-and-forget + try/except 吞錯誤 + 5s watcher poll backstop」設計 → 系統不崩潰但 fast-path optimization 100% 失效（authorization 5s 延遲生效 / system_mode 只能等 engine restart 經 snapshot 同步）。E1 在新檔內嵌 helper 用秒對齊 Rust 正確；legacy 修建議 **PM 立即開 P1 separate ticket**
- **PA vs PM schema 分歧處理**（軌 3）：PM prompt 引用「P1_HARD_*_MAX_BPS constants」**不存在**；E1 採 PA RFC §2.1 pct 型 4 字段 schema（完美 1:1 match）正確判斷
- **G2-03 staging 判定**：schema + 防線 A+B + 抽分完整，但 `check_position_on_tick_with_override` **0 production caller**（grep 確認，只被自己 thin wrapper + 8 unit tests 呼）→ 「runtime path 沒走 override，schema-only landing」屬正確 staging 不是半成品。**PM commit message 必明標 staging 狀態**
- **§九 1200 硬上限管理**：`ipc_server/mod.rs 1251` PRE-EXISTING 超 +11 dispatch route → MEDIUM；E1 嚴守不擴張認可，但 E5 wave 必拆
- **判定方法論教訓**：
  - 凡是「100% fail 但未察覺」結論必 grep 完整 caller list 驗證 fail 路徑是否有 backstop 吞掉錯誤；無 backstop = silent system bug，有 backstop = optimization path 失效但功能正確
  - 凡是「thin wrapper + 0 caller 改動」必 grep 新 fn 是否真有 production caller（grep `_with_override` 在 src/ 排除 tests/）；0 caller = 「實質效用 = 0」必明標 staging
  - PA vs PM schema 分歧時必 grep PM prompt 引用的 constants 是否存在；不存在即 PM 寫錯，採 PA 為 source-of-truth
  - dry-run script 必驗 mutating payload 構造 vs 真實 IPC call 路徑是否分離（line 510-516 構造 mutating + line 532-537 真送 唯讀 = 安全）
  - schema-only landing 與 runtime active 是兩個獨立狀態 — schema land 不等於 binding 啟用；必在 commit message 標清楚

### 2026-04-26 Phase 1+2 batch review (10 commits, df1d629..bd5ce56) — 9/10 PASS, 1 RETURN

- **結論**：9 PASS / 1 RETURN E1（commit 7 92ea90b banner stale doc, MEDIUM）
- **驗證 metric**：cargo lib 2161 → **2166 / 0 failed**（+1 c2ca032 stale_peak_ms test + 4 bd5ce56 verify_ipc_token tests），cron healthcheck 19 check 全跑通（17 PASS / 1 WARN [11] 96% / 1 FAIL [3] pre-existing）
- **退回 commit 7 (92ea90b) MEDIUM finding**：calibrator banner「IPC bind only covers 6/7 dimensions」在 commit 6 (c2ca032) 加 stale_peak_ms 進 IPC 後**已過時**。commit 6 commit msg 明示「Banner removable once IPC schema extended」但 PM 代 commit 漏執行。banner lines 173/184-186/188-191 三處內容矛盾於 ipc_server/handlers/risk.rs:316-323 toml_only_fields_skipped 從 2→1 element 的真實狀態。建議選項 A 完全移除 banner + 1-2 行 reference c2ca032 inline comment 替代
- **PM 代 commit 風險獨立驗證**：
  - commit 2 (0cda2d9 G9-01 TW)：grep position_manager.rs:307-335 確認 Rust 用 confirm-pending-mmr ✅；Python 0 usage ✅；TW memory 與 commit msg 不一致（LOW，0 production 影響，下次 TW 接手 update 即可）
  - commit 6 (c2ca032 EDGE-P1b-FUP-STALE-PEAK-IPC E1)：8 wire site 全改到 ✅（tick_pipeline + handlers/mod + handlers/risk + ipc_server/handlers/risk + 4 tests）；u64→i64 cast fail-closed by validate() ✅；restore handler 7→8 fields_restored + 2→1 toml_skipped 同步 ✅；+1 dedicated round-trip test 驗 5 點（lossless cast / version bump / additive merge / shadow_enabled unchanged / shadow_enabled-only 剩餘 TOML-only）✅
- **G5 refactor 三件 hot-path 保留驗證**：
  - bd5ce56 ipc_server split：`use crate::ipc_server::{IpcServer, PerEngineRiskStores, EngineCommandChannels}` 從 main.rs / main_boot_tasks.rs / main_pipelines.rs 全部解析 OK；mod.rs facade `pub use` 4 + `pub(crate) use` 10+ + `pub(in crate::ipc_server) use handlers::*` 確保 `super::super::*` 從 handlers/ 接得到所有 pre-split 名稱；macro re-export 限制由 handlers/teacher.rs + handlers_config.rs 各自 `use tracing::{info, warn};` 處理；4 verify_ipc_token unit tests 新加（pre-existing 0 coverage）；patch_risk_config / EDGE-P1b 8 exit_* / HMAC verify / accept loop byte-identical
  - cc4c2d2 passive_wait_healthcheck split：cron 12:40 跑 19 check 全部跑通；shim 36 行 sys.path prepend OK；`__init__.py.__all__` 19 check_* 全列；runner.py invocation order byte-identical（13 cursor + 6 post-conn-close）；隨機抽 check_close_fills_24h 對照 pre/post SQL byte-identical
  - a5b6f17 tick_pipeline tests split：120 test attributes pre = post（含 #[test] / #[tokio::test] / #[serial]）；on_tick_helpers 路徑 super::super:: 從 sibling 上兩層 = tick_pipeline 正確；shared make_event / make_signal 在 mod.rs 用 pub(super)；0 production touched
- **時序 hazard 教訓（PM 改進建議）**：commit 7 (12:17) → commit 6 (12:36) 19 分鐘間隔；commit 6 invalidates commit 7 banner 但 PM 漏執行 commit msg 自己寫的「Banner removable」動作。對「commit B 應 invalidate commit A doc」依賴對，PM 編排建議：(A) 合併同次 push (B) commit B 完成手動補 patch 移除 commit A stale doc (C) commit A 加 TODO 標記 + 後續 ticket 提醒
- **判定方法論教訓**：
  - 凡 PM 代 commit（E1/TW push back 或 staging dir）必獨立驗證：(1) E1 改動完整性 grep 對照 (2) 任何聲明「verified」必獨立 reproduce (3) commit msg 預告的「removable」「to be done」必檢查是否真執行
  - 凡 commit 在 19min 內依賴另一 commit 必檢查 invalidation chain：A 加 banner 警 X → B 修 X → A banner 是否 stale？
  - 凡「fail-closed by downstream validate」設計 pattern 必驗：(a) Python wrapper 是否預 check（typed wrapper 應該主動拒絕，下游 validate 是 last line of defense） (b) Rust IPC handler 對 cast fail 是 silent None vs explicit error
  - Hot-path refactor split 必對照原 mod.rs 的所有 `pub use` / `pub(crate) use` 與新 facade 是否字段對齊（不只看 `super::super::*` glob 解析能不能編譯，要看具體 pub item 集合是否一致）
  - macro re-export 不繼承 `super::super::*` glob — 拆 mod.rs 時若原本 mod.rs use tracing 內部 macro，sibling 必各自 `use tracing::{info, warn};`（commit 11 commit msg 已說明此點）

### 2026-04-26 Wave 3 W5 兩軌（EDGE-P2-flip T2 + G2-FUP-IPC-LEGACY-MS-FIX）— 兩軌獨立 PASS with conditions
- **結論**：軌 1 EDGE-P2-flip T2（[15] per-strategy 切片 + breakdown.py 新工具）+ 軌 2 IPC HMAC ms→s 兩軌主體 OK，可 PASS to E4
- **軌 1 [15] dormant 路徑驗證**：stub test scenario 1 證 `total == 0` 早 return PASS，per-strategy SQL 不執行（_call_count=2 而非 3）→ **0 dormant/per-strategy 衝突風險**
- **軌 1 [14] vs [15] design divergence MEDIUM finding (T2-MED-1)**：E1 docstring 「mirrors [14]」誤導 — [14] per-strategy 純 informational（從不 promote status），[15] per-strategy WARN promotion 是 design **divergence**。讀者會以為 [14] 也有同樣升級邏輯
- **軌 1 PM vs PA 立場分歧處理**：PA RFC §2.3 推 FAIL，PM 派發 spec 採 WARN（fail-soft），E1 採 WARN 正確；flag promotion 點極乾淨（line 2104-2109，1 個 return tuple，未來改 FAIL 改字串即可）
- **軌 1 GROUP BY 對齊驗證**：PM prompt 推測「[14] 升級用 owner_strategy prefix」**錯**；[14]+[15] 都用 strategy_name 完整字串 GROUP BY（精確匹配，非 prefix LIKE），無對齊問題
- **軌 1 sparse_threshold=5 邊界**：n=4 SPARSE / n=5 inclusive 進 PASS/WARN / disagreed_n=0 reason rows 不出現（sentinel 路徑只 1-4）/ aggregator 5 case stub 全 PASS
- **軌 2 Rust verifier mirror byte-perfect**：對照 mod.rs:534-548 真實實作驗 5 點全 mirror — secret bytes / ts.to_string payload / Hmac<Sha256> / hex format / constant-time（mac.verify_slice ↔ compare_digest）/ tolerance abs(now-ts)>30
- **軌 2 caller 影響**：grep 確認僅 2 production caller（live_trust_routes:296 + control_ops:515）；修前 100% PermissionError + 5s watcher poll / engine restart 兜底 → 修後 fast-path 即時生效；Rust handler advisory 設計（trigger_live_auth_recheck 永不錯誤回應 / set_system_mode 廣播 + snapshot 雙寫）→ **system behavior change but by-design**
- **軌 2 commit message LOW finding (T2-LOW-3)**：應明示 `set_system_mode` 從 snapshot fallback (mins) → IPC fast-path (secs) 的 latency 改變，避免 operator 誤認「只是 typo fix」
- **軌 2 test 邊界 LOW finding (T2-LOW-2)**：3 case 用 25/60 跨度避開 exact 30s；建議補 +30s pass + 31s fail boundary 增強保護
- **§九 1200 上限管理**：healthcheck.py 2286 既存超 +101 不擴張範圍認可（純 [15] 升級 + per-strategy slice），G6-04 後續 wave 必拆（建議按 check ID 切到 sibling）
- **判定方法論教訓**：
  - 凡 docstring 說「mirrors [X]」必驗 [X] 與本 check 行為差異 — 不接受 happy-path「都 fail-soft 所以 mirror」籠統描述
  - 凡 IPC ms→s 修復必查所有 caller 修前 silent fail 機制是否吞錯誤 + 修後 fast-path 生效是否引發 system behavior change（latency 變化等）
  - Rust verifier mirror 必驗 byte-perfect（secret bytes / payload encoding / hex format / constant-time / tolerance）— 不接受「應該對齊」的籠統判斷
  - §九 1200 既存超檔接收 PR 加注釋/小邏輯修必嚴守不擴範圍 + 後續 wave 必拆（不能無止境累加）
  - PM prompt 推測「對齊既有 check 用 prefix 切片」必獨立 grep 驗證 — PM 推測有誤時必 push back（[14]+[15] 兩者用 strategy_name 完整匹配無 prefix）

### 2026-04-26 Tier 3 batch review (5 commits, 7564d07..31fa96c) + G9-05 PUSH-BACK — 4 PASS / 1 PASS-with-MEDIUM / G9-05 CLOSE-PASS

- **結論**：5 commit PASS to E4 / QA / PM Sign-off；G9-05 TW PUSH-BACK CLOSE-PASS（無 drift 需修）；建議 PM 開 4 follow-up tickets（非 BLOCKER）
- **驗證 metric**：cargo lib `2176/0`（baseline 2166 + G9-02 ws_unknown_handler_guard 10 tests，commit message 完全對齊）；Python pytest `test_layer2 + test_layer2_escalation + test_layer2_tools = 136/0`（含 1 e2e @pytest.mark.slow warning，未阻塞）
- **8-Axis audit 結果**：A 跨平台 PASS / B 雙語 PASS / C 範圍 PASS / D SQL Guard PASS（無新 V### migration）/ E Hot-path PASS（reconnect/subscribe/heartbeat/parse 0 動）/ F Test PASS / G E1/PA 11 review point 詳細結論 / H G9-05 CLOSE-PASS
- **MEDIUM Finding G9-02-MED-1**：ws_client.rs 1108 → 1227 行（+119）超 §九 1200 hard cap +27 行；E1 memory.md 已 self-disclose 行數但略誤宣稱 +39。**ACCEPT-with-FOLLOWUP**（不退回 E1，hot-path 改動 surgical 再拆會擴張）；建議 PM 開 G9-02-FUP-WS-CLIENT-SPLIT ticket（split process_message 路由 / run() 內部結構，0.5-1d，Wave 4 收尾或 G5 refactor wave 帶走）
- **G3-07 6 review points 結論**：6 ACCEPT / 0 REQUIRE-FIX / 0 REJECT
  - #1 OPENCLAW_BYBIT_ENV namespace ACCEPT-with-NOTE（production 走 file-based 不 conflict + future polish ticket）
  - #2 oi_24h_change_pct 不接 history endpoint ACCEPT（誠實標 data-unavailable per §二 #10）
  - #3 liquidations_24h 不接 third-party ACCEPT（防擴範圍）
  - #4 e2e network test ACCEPT（@pytest.mark.slow 已可 filter，warning 是 minor）
  - #5 layer2_tools.py 1032 > 800 警告 ACCEPT（< 1200 hard cap 安全，sibling pattern 已最乾淨）
  - #6 Mac httpx fail 不要求補 ACCEPT（Mac dev-only 本來不依賴 production deps，Linux SSOT 36/36 全綠）
- **G9-02 5 review points 結論**：3 ACCEPT / 1 ACCEPT-with-FOLLOWUP / 1 OPEN-FOLLOW-UP / 0 REQUIRE-FIX
  - #1 ws_client.rs 1227 cap → ACCEPT-with-FOLLOWUP（MED-1，開 split ticket）
  - #2 force reconnect cooldown OPEN-FOLLOW-UP（既有 BackoffConfig::ws_public_default 3-60s 指數退避有基礎保護；DEFAULT-ON 後監控 forced_reconnect_total 1-2 週再決定是否需 cooldown）
  - #3 DEFAULT-OFF env-gate 嚴格 "1" ACCEPT（vs G3-07 loose "1/true/yes/on"，差異合理：G9-02 是行為改動 strict / G3-07 是只讀工具 loose）
  - #4 Auth phase 不啟 force reconnect ACCEPT（防 fresh connection 風暴）
  - #5 ws_unknown_handler_guard.rs 共享 sibling ACCEPT（純 stand-alone module，pattern 對齊 ws_backoff.rs）
- **G9-05 PUSH-BACK CLOSE-PASS 獨立驗證**：(1) grep `docs/references/2026-04-04--bybit_api_reference.md` 章節編號全為 1.X（9 子章 1.1~1.9），0 命中 L-[0-9] (2) set_trading_stop 字典 9 fields vs Bybit V5 真實 16+ fields 是 simplified subset（OpenClaw 未實作 partial TP/SL / limit-price TP/SL / order_type TP/SL）— TW 兩主張獨立驗證成立；BB 不需 re-audit
- **判定方法論教訓**：
  - 凡 PA design plan only commit 仍要驗：(a) 跨平台 grep (b) 章節結構完整 (c) phase rollout / risk / E2 重點審查 章節有實質內容；G3-08 自帶 §14「E2 重點審查 Top 3」可作為未來 E2 對抗式對照表
  - 凡 §九 1200 hard cap 違反必判 ACCEPT-with-FOLLOWUP vs 退回 E1：(a) sibling 已預抽且 hot-path surgical 不可拆 → ACCEPT + open split ticket（如 G9-02-MED-1） (b) 沒做 sibling 預抽且純線性堆積 → REQUIRE-FIX 退回 (c) 有 sibling 但抽得不徹底 → 視 reviewer 判斷
  - 凡 G3-07 類「pure-function tool」改 vs G9-02 類「Rust hot-path state machine」改的 sibling 預抽效果差異：前者 sibling pattern 完美（schema/handler 留主，fetch/parse 拆 sibling），後者 process_message 路由本身嵌在 select! 裡受限不可拆 — 應為未來 PA design 決策依據
  - 凡 PM prompt 章節編號 vs doc 真實章節不一致（L-2~L-5 vs 1.2~1.5）：E2 不為 PM prompt 字面負責，為真實系統一致性負責 — 以 doc 原文為準
  - 凡 caller graph 三層追蹤（self → import → cron pipeline）：v1 dead 不等於 v2 也 dead；v1 commit 必明示「v2 留尾 to broader cleanup ticket」（G9-04 commit message 範例好）
  - 凡批次 review N commit + M review point + K PUSH-BACK 工作量管理：先 git fetch 拿物件 + git show 讀內容（Mac side 不 pull 避免動 working tree）+ ssh trade-core 跑 cargo test + pytest 驗 baseline + grep 驗 caller graph + namespace clash 雙端執行

### 2026-04-26 Tier 4 batch review (6 commits, eb65e1e..4689fc8) + MIT findings + PM merge — 5 PASS / 1 PASS-merge / 0 RETURN

- **結論**：6 commits **全 PASS to QA**（5 work commits + 1 PM merge accept union strategy）；MIT findings ACCEPT；PM merge ACCEPT；3 LOW finding 全 P3 future polish 不退回 E1
- **驗證 metric**：cargo lib `2198/0`（baseline 2176 + 22 h_state_cache tests，post-merge Linux 驗）；pytest h_state `35/0`；layer2 chain `136/0` 不變；healthcheck cron pipeline 19→20 check Linux 跑通
- **8-Axis audit 結果**：A 跨平台 PASS（生產代碼 0 hit，2 hit 在 c53c3f9 docs 屬政策反例引用白名單）/ B 雙語 PASS（5 Rust + 4 Python + 6 ws_client sibling + 5 OBSERVER 修改檔全中英對照）/ C 範圍 PASS（每 commit 嚴守邊界，G3-08 Sub-task B 不擴 Sub-task C 範圍 + OBSERVER 留尾 BB-M-3 合理）/ D SQL Guard PASS（無新 V### migration）/ E Hot-path PASS（G3-08 select! biased race=0 / G9-02-FUP 5 hot-path byte-identical 含 FA-1 risk #2 雙路徑非對稱性 / OBSERVER cron noise pattern 完全移除）/ F Test PASS / G PM merge ACCEPT（union 0 條目丟失 + cargo 2198/0 不破壞）/ H MIT findings ACCEPT（5 hypothesis 完整 + 雙因 RCA + STRKUSDT 7d lineage + 3 修復路徑 trade-off）
- **3 LOW findings**：
  - L-1 cron_observer_cycle.sh 76-79 BRIDGE_RC overshadow OBSERVER_RC at exit（只影響 cron daemon /var/log/cron exit code, log 行有 BRIDGE 細節）— P3 cosmetic 改 `[ $OBS -ne 0 -o $BRIDGE -ne 0 ] && exit 1`
  - L-2 ai_service_dispatch.py 868 行 進 §九 800 警告區（pre-existing ~813 + G3-08 +55）— P3 split ticket 對齊 G5 refactor wave 收尾
  - L-3 MIT 報告 H1 reject `build_exit_features_for_tick` 不寫 DB 結論未給 grep snippet 證據（E2 獨立驗證屬實）— MIT 下次補 grep snippet 教訓
- **G3-08 Phase 1A Rust race risk 反駁**：PA §14.1 Top 3 #1 提「10s daemon poll + invalidation push 競態」實測無風險 — `tokio::select!` 同 task 同時只 select 一個 branch，`run_one_poll` sequential await 不可 reentrant；timer + invalidation 同時觸發只取 biased 順序首先 ready 那條，另一條等下一輪 select。Race=0
- **G3-08 Phase 1B IPC route 真相教訓**：reverse IPC route 註冊位置是 `ai_service_dispatch.py:_register_handlers()` 的 `self._handlers` dict（不是 ipc_dispatch.py / dispatch.rs），這是 Rust→Python JSON-RPC server handler registry。E2 對抗 review 必驗 route 是否「永遠註冊」（PA §10.1 規定 env=0 時 route 仍可達），E1 此處對齊正確
- **G9-02-FUP 5 hot-path byte-identical 對抗驗證**：grep run_loop.rs:66-70 (WS-TIMEOUT) + run_loop.rs:97-103,156-169 (subscribe HashSet O(1) + 10-batch + 500ms gap) + dispatch.rs:135-147 (process_message ShouldReconnect::No,Yes) + run_loop.rs:78-86,247-251 (BackoffConfig 雙路徑 FA-1 risk #2 順序非對稱性 — timeout-path sleep→after-incr / main-exit-path before-incr→delay) + run_loop.rs:200 (ProcessOutcome::ForceReconnect close-frame + break) — 5/5 byte-identical 對照原 1227 行內嵌實作
- **OBSERVER cron-time env var 陷阱教訓**：cron 預設 cwd=$HOME（非 REPO），shell var fallback `OPENCLAW_SRV_ROOT="."` 在 cron context 解到完全不同 path → cycle JSON 寫到 `$HOME/docker_projects/` 而非 `REPO/docker_projects/` → healthcheck 找不到新鮮 JSON 是 path 偏移、不是 stale。修法：cron wrapper 顯式 export env var 給子程序，**不依賴** systemd / cron daemon 繼承
- **OBSERVER `if ... ; then ... else echo "non-fatal" ; fi` 是 noise wrapper 反模式**：把 exit code 譯成 log 行 + 整段 exit 0 是 silent-fail 教科書級。CLAUDE.md §七「被動等待 TODO 必附 healthcheck」+「連續 3 FAIL 中止」要防的就是這 pattern。任何「failed (non-fatal)」字眼在 cron wrapper 都該被 grep 出來重 review。E2 cron wrapper review 必先 grep `non-fatal` / `set -e` 邏輯
- **OBSERVER healthcheck 設計兩選一教訓**：(a) 真實狀態暴露（預設 FAIL，operator opt-out）vs (b) 環境感知（預設 PASS，operator opt-in）— silent-fail 修復場景必選 (a)，否則 healthcheck 自己變 silent-fail 二線共犯。E1 在 [19] 選 (a) + `OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1` opt-out 正確
- **PM merge union strategy 驗證**：parent 1 (main `0765d0a` 含 Sub-task B + OBSERVER) + parent 2 (worktree `fbfb56f` 含 Sub-task A) → merge result `87fccdb` 兩段「報告檔位置」line 並列保留（worktree 用「直接傳給 parent agent」+ main 用「`.claude_reports/<ts>...`」雙引兩段）。3 條目（A/B/OBSERVER）全保留無丟失。E2 必查 union: (a) parent 1 + parent 2 各條目 grep 驗對應 (b) merge commit message 標明來源 worktree (c) cargo test post-merge baseline 不破壞
- **MIT 5 hypothesis + 雙因 RCA 結構**：H1-H5 涵蓋 builder bug / detection / retry duplicate / SQL bug / engine_mode mismatch；雙因 RCA-A (FastTrack ReduceToHalf 對 dust legacy 倉位無限半倉，step_0_fast_track.rs:317 fail-open) + RCA-B (EF writer 對 partial reduce 也寫 row，pipeline_helpers.rs:217)；3 修復路徑 1+2 cohesive PR 對齊 RCA 結構合理。對抗 review 必獨立 grep H1 reject 證據鏈（`build_exit_features_for_tick` 是否真不寫 DB / `try_emit_exit_feature_row` 是否唯一 EF 寫 DB 路徑），不依賴 MIT 報告字面結論
- **判定方法論教訓**：
  - 凡 PM 派發 5 並行 sub-agent 中含 worktree isolation 一個 → 必查 PM merge 是否：(a) E1 memory.md 三段全保留 (b) merge commit message 標明來源 worktree branch (c) cargo test 不破壞 baseline；union 策略可接受但「報告檔位置」雙引 line 屬可容忍 cosmetic（不退回 PM）
  - 凡「reverse IPC route」實作必查 (a) 註冊位置（`_register_handlers()` 而非 ipc_dispatch.py） (b) 是否「永遠註冊」（PA §10.1 規定 env=0 時 route 仍可達） (c) HANDLER_TTLS 是否 ≤ SLA target （5ms target → 2.0s deadlock guard） (d) lazy import 是否防 bootstrap cycle
  - 凡 Rust `tokio::select!` race claim → 必驗 (a) `biased` 順序語意 (b) `run_one_poll` sequential await 不可 reentrant (c) await 點之間 task 不可中斷 — 三條皆滿足 race=0；不接受 happy-path 「應該不會 race」籠統判斷
  - 凡 cron wrapper review → 必先 grep (a) `non-fatal` / `set -e` 邏輯 (b) `export OPENCLAW_*` env var 完整 (c) 任一段 RC 顯式捕捉 + wrapper 整體非零；發現 `if ... ; then ... else echo "non-fatal" ; fi` pattern 立即標 silent-fail 教科書級反模式
  - 凡 healthcheck 預設 FAIL vs PASS-skip 取捨 → silent-fail 修復場景必選預設 FAIL + operator 主動 opt-out（`OPENCLAW_*_OPTIONAL=1`），不選預設 PASS
  - 凡 MIT findings audit → 對 H1-H5 reject 結論必獨立 grep 證據鏈（不依賴 MIT 字面結論）；推 MIT 下次報告補 grep snippet 對齊 §7 smoking gun SQL 同等地位
  - 凡 hot-path byte-identical 改動 → 必獨立 grep 對照 5+ hot-path 在新 sibling 中的確切 line（非籠統「保留」），FA-1 / WS-TIMEOUT 等 risk-tagged 點順序語意特別需驗
