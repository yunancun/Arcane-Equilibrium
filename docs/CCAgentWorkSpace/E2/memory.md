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
| 2026-04-26 | Tier 5 batch review 7 commits (af48ee1..f2ed286) — T5.1 EXIT-FEATURES-FIX + T5.2 G3-08-PHASE-1C + T5.3 Phase 2 H1+H3 | workspace/reports/2026-04-26--tier5_batch_review.md |
| 2026-04-26 | Tier 6 batch review 4 commits (306b549..56104de) — T6.1 Track 1 4 LOW + T6.2 Track 2 H3 schema design + T6.3 Track 3 dust audit design | workspace/reports/2026-04-26--tier6_batch_review.md |
| 2026-04-26 | Tier 7 batch review 3 commits (4b30f5e/8241133/c6ed0b3) — T7.1 Rust H3 schema align T7.2 healthcheck [21] dust inventory T7.3 PA Phase 3 sub-task split | workspace/reports/2026-04-26--tier7_batch_review.md |
| 2026-04-26 | Tier 8 batch review 4 commits (8cd257e/cf39415/71faf4c/79a808a) — T8.1 Sub-task 3-1 H2 + T8.2 Sub-task 3-2 H4 silent gap + T8.3 RFC §7.4 amend | workspace/reports/2026-04-26--tier8_batch_review.md |
| 2026-04-26 | Tier 8 Track 4 supplementary 1-commit review (d1a2252) — Sub-task 3-3 H5 cost_logging / Phase 3 COMPLETE / G3-09 unblock | workspace/reports/2026-04-26--tier8_track4_e2_review.md |
| 2026-04-26 | Rust P0 Wave 4-PR adversarial review (F2/F3/F4/F6) — 直接 final message 回 PA/PM（system prompt 限制不寫 .md report）| inline final message · 3 PASS / 1 RETURN（F4）|
| 2026-04-26 | Python P0 Wave 2-PR review (F5 GUI + F7 healthchecks) — F5 RETURN 1 HIGH/1 MEDIUM/1 LOW + F7 PASS-with 1 MEDIUM cross-cut + 2 LOW + 1 size warning | workspace/reports/2026-04-26--python_p0_wave_review.md |

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

### 2026-04-26 Rust P0 Wave 4-PR adversarial review（F2 cross-symbol-price / F3 phantom-dust-evict / F4 trading-writer-live / F6 edge-reload-daemon）— 3 PASS / 1 RETURN
- **結論**：F2 PASS / F3 PASS / **F4 RETURN E1** / F6 PASS。
- **F2 PASS with 1 LOW**：3 層 fallback `latest_price → entry_price → event.last_price` + NaN-aware filter + 5 audit sites + 4 regression test 全綠。LOW = step_4_5_dispatch:334 audit comment 提「未來新增策略需改 paper_state.latest_price」但 debug_assert 在 release strip — 建議升級 release-time `assert_eq!(intent.symbol, ctx.symbol)` 但不阻 merge
- **F3 PASS with 2 LOW**：4 trigger（T1 reduce_position 後 / T2a apply_fill 反向 / T2b 同向加倉 / T3 boot reaper / T4 status arm 30s）+ 13 unit test + ML hygiene（不寫 trading.fills）+ schema reuse（af48ee1 ft_dust_qty_floor_usd 不新增）+ fail-closed 4 邊界（floor=0 / NaN / price=0 / position absent）。LOW = (a) tests.rs 1645 行超 §九 1200（test file 慣例容忍）(b) evict_all_dust 內存 candidate Vec 對 N≥50 active symbols 有 GC 壓力可優化為 retain pattern
- **F4 RETURN E1 — 1 MEDIUM logic bug + 1 §九 hard violation + 2 LOW**：
  - **🛑 §九 hard limit violation**：F4 alone 1304 行 > 1200 hard limit（超 104 行）；F3+F4 merged 預測 1333 行（超 133 行）。E1 commit msg 完全沒提。**強制 Path A：F4 PR 內 split helper（line 78-200 抽到 sibling unattributed_emit.rs）**，F4 改 ~1h 重審 ~30min；不可 defer
  - **MEDIUM logic bug — dedup race + try_send drop**：seen_exec_set.insert(exec_id) 在 line 413（emit branch upstream）→ try_send 通道滿時 audit row drop，WS 重連被 dedup 攔住不再走 emit branch → audit row **永久遺失**。F4 commit msg 「reconnect re-emit; fill_id PK keeps DB idempotent」claim **錯**：fill_id PK 保護「同條 emit 命中 ON CONFLICT」非「重連後再到達 emit branch」。修法：try_send → `send().await`（背壓不丟）
  - **LOW commit msg amend**：「funding payment」非真實 unmatched WS source（Bybit V5 funding 走 wallet ledger 不走 execution stream）；改為 dust scrub / liquidation / 人工 GUI close / orphan auto 補單
  - **LOW healthcheck implicit dependency**：`check_close_fills_24h` baseline 用 `realized_pnl != 0` 過濾，**隱式排除** F4 audit row（hardcoded `realized_pnl=0`）— coincidental safe；F4 commit msg 應 acknowledge 此依賴
- **F6 PASS with 3 LOW**：1h periodic daemon + DEFAULT-OFF 嚴格 "1" env-gate + IPC `reload_edge_estimates` advisory（accepted/coalesced/reloader_closed/reloader_disabled 4 種 response）+ mode isolation handler 端 `pipeline.pipeline_kind.db_mode()` 結構性保證 + fail-soft 保留前份 + slot late-inject mirror G3-08 H state pattern。LOW = (a) `interval.tick().await` 第一次 skip → 第一次真實 reload 在 1h 後（boot 與 Python scheduler 新寫 JSON 之間有 gap，可在 boot 結束 emit 立即 trigger）(b) main_boot_tasks.rs 815 行接近 800 警告線 (c) dispatch_request 16+ args propagation 累積反模式
- **5 cross-cutting findings**：
  - CC-1 §九 1200 violation（**最重，CRITICAL**）：F4 必 PR 內 split；tests.rs 後續 G5 wave 拆
  - CC-2 paper_state 視角：F2 用 latest_price accessor / F3 加 2 field+3 accessor / F6 不動 → **0 衝突**
  - CC-3 F4 audit + F3 evict ML 視角：F3 不寫 fills（ML hygiene）/ F4 寫 audit row 同時 5 ML pipeline filter NOT LIKE 'unattributed:%' → **互補無衝突**；次生發現 healthcheck check_close_fills_24h 隱式依賴 realized_pnl != 0
  - CC-4 engine lib test 數一致性：4 branch 從不同 main baseline 切（W2/W3 移動），cumulative 不能直接比，E4 跑 combined regression
  - CC-5 雙語注釋 + 跨平台 grep + commit 即 push：4 PR 全 PASS
- **Merge order 建議**：F2 first（lowest risk paper_state 不動）→ F6 second（DEFAULT-OFF env-gate 隔離）→ F3 third（loop_handlers +25 仍 < 1200）→ **F4 last，且必先 split helper + 修 MEDIUM logic bug + 重 E2**
- **判定方法論教訓**：
  - 凡是 channel-based audit emit + 上游 dedup_set，必 grep dedup mark 點是否在 emit upstream／downstream；upstream + try_send drop = silent loss
  - 凡是「reconnect 會重發所以 idempotent」claim 必驗：(1) 上游 dedup 是否阻擋第二次到達 emit (2) PK ON CONFLICT 是否真覆蓋「重連後再到達」場景（不是「同一 emit 命中 ON CONFLICT」）
  - 凡是 `try_send` 用於「不可丟失的 audit / observability event」必 push back；改用 `send().await` 背壓更乾淨
  - §九 1200 hard limit 不可妥協 — E1 commit msg 沒提不代表可豁免；F3 + F4 merged 預測算法需 E2 主動算（兩 branch 改同檔不同 hunk）
  - 跨 PR baseline 漂移時 cumulative 測試數比較無意義；只看「branch 自身是否從 own baseline 加測試 + 通過」
  - mode isolation 在 handler 端讀（pipeline_kind.db_mode）vs producer 端路由 — handler 端讀更 robust（producer 誤路由也不會污染）
  - DEFAULT-OFF 嚴格 "1" env-gate（拒 true/yes/on/0/" 1"/"1 "）是新代碼標準 pattern，G3-08 H state poller + F6 reload daemon 都用此（避免 typo 誤啟用）

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

### 2026-04-26 Tier 5 batch review (7 commits, af48ee1..f2ed286) — 3 PASS / 0 RETURN / 3 FUP tickets

- **結論**：T5.1 EXIT-FEATURES-FIX (3 commits) PASS / T5.2 G3-08-PHASE-1C (2 commits) PASS / T5.3 G3-08 Phase 2 H1+H3 (2 commits) PASS-with-FOLLOWUP；3 follow-up tickets 推薦 PM 開
- **驗證 metric**：cargo lib `2210/0`（baseline 2198 + EXIT-FEATURES-FIX +12 unit tests）+ integration `12/0`；pytest `75/0`（H1/H3/h_state_query_handler）+ strategist regression `36/36`；healthcheck [20] env=0/env=1 smoke 兩態都驗
- **8-Axis audit 結果**：A 跨平台 PASS（7/7 commits 0 hit）/ B 雙語 PASS（11/11 modified files ≥5 中 markers + MODULE_NOTE）/ C 範圍 PASS（3 task 各自獨立 sequential 不擴張）/ D SQL Guard PASS（無新 V###）/ E Hot-path PASS-with-FOLLOWUP / F Test PASS / G PA design PASS-with-MEDIUM（H3 schema mismatch dormant）/ H MIT audit PASS（A1+A3+B1' 對齊）
- **EXIT-FEATURES-FIX RCA-A audit**：(a) Gate 1 USD floor active in ALL branches（封住 entry_notional==0 fail-open 漏洞）(b) Gate 2 ratio gate 仍對 entry_notional > 0 生效（保留 pre-FIX legacy real position）(c) ft_dust_qty_floor_usd schema validate [0, 100_000] + reject NaN/Inf（hot-reloadable via patch_risk_config）(d) bootstrap migrate_legacy_entry_notional idempotent（only entry_notional <= 0 && qty > 0）(e) stale tick fall-through（last_price <= 0.0 → return true 保留倉位下 tick 重評估）
- **EXIT-FEATURES-FIX RCA-B audit**：(a) is_partial_reduce_tag exact-match 不誤判 PHYS-LOCK / strategy exit (b) emit_close_fill 仍寫 trading.fills（operator visibility + PnL 帳）只 EF skip (c) E1 採 B1' 變體（partial_reduce_tag exact match）比 MIT B1 (`realized_pnl == 0`) 更精準避誤封 break-even 邊界 case
- **G3-08 Phase 1C audit**：condition spawn 模式對齊 G3-03 ExecutorConfigCache（資源流相反）/ DEFAULT-OFF env=0 zero overhead（嚴格 `=="1"` strict eq → singleton stays None → invalidate_async no-op）/ healthcheck [20] 三態 PASS/WARN/FAIL pure-Python no live IPC（對齊 [16] log-tail-parse 哲學）
- **G3-08 Phase 2 H1+H3 audit**：H1/H3 invalidate_async hooks 在 public method exit fire-and-forget never-blocks / get_*_snapshot 純讀無副作用 / lazy-import strategy_wiring 避 bootstrap circular（worker boot 序列死鎖風險）/ _safe_snapshot defensive 防 snapshot raise / schema v0→v1 升級含 `version != 0 + h_states keys ≠ 0` 觸發
- **MEDIUM Finding T5.3-MED-1 H3 schema mismatch (DORMANT)**：Python keys 0/7 match Rust H3RouteStats（Python `l1_9b_count` vs Rust `l1_9b`，Python `l2_cache_hit/expired/stored` vs Rust `cache_hit/expired`，Python 多 `total_routes/budget_denied_count/l2_cache_stored`）；runtime impact = 0（Rust 仍用 StubHStateFetcher）但 Phase 3+ 接 real fetcher 時 silent regression。建議 PM 開 G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN（30min, before Phase 3 lands real fetcher，PA-led design A/B/C decision）
- **MEDIUM Finding T5.3-MED-2 私有屬性穿透 (CLAUDE.md §九 #8 violation)**：h_state_query_handler:247-249 用 `getattr(strategist, "_h1_gate")` + `getattr(strategist, "_model_router")` 直讀 StrategistAgent 私有屬性；PA §5.1 spec line 397-405 期望 PUBLIC facade `STRATEGIST_AGENT.get_h1_stats_snapshot() / get_h3_route_stats_snapshot()`；E1 跳過 facade layer。functional impact = 0（_safe_snapshot defensive）但 contract 違規（後續 strategist refactor 改名 `_h1_gate` → `_thought_gate` 會 silent break）。**PM 二選一**：(A) RETURN E1 加 facade method ~15min ; (B) ACCEPT-with-FOLLOWUP 開 G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE (P2)
- **LOW Finding T5.1-LOW-1 helpers.rs 1315 §九 violation**：pre-existing 1182 + af48ee1 +133；hot-path 抽 helper surgical 不可隨便拆，ACCEPT-with-FOLLOWUP 對齊 G9-02 ws_client.rs 1227 方法論（同樣是 hot-path 非線性堆積、sibling pattern 可拆 helpers/{tags.rs, phys_lock.rs, shadow.rs}）；PM 開 EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT (~0.5d, Wave 4 G5 refactor)
- **LOW Finding T5.2-LOW-1 healthcheck [20] expected sync after 9120948**：5943337 期望 stub Phase 1 形狀（version=0 + h_states={}），9120948 升級為 version=1 + real H1+H3 snapshots when env=1 → [20] env=1 path 永遠 WARN「Phase 2-4 progress? update [20] expectations」。E1 寫的 WARN 邏輯吸收成功但 [20] expected 應同步更新；PM 開 G3-08-PHASE-1C-FUP-CHECK20-SYNC (~10min)
- **LOW Finding T5.3-LOW-1 model_router redundant f-string**：`counter_key = f"l1_9b_count" if ... else f"l1_27b_count"...` 無 placeholder；功能等同 plain string 但 ruff PLF0901 / W1309 會報；E2 留給 PM 決定是否強制修
- **PM merge ACCEPT 推薦選項 B**（T5.3 PASS-with-FOLLOWUP）：functional impact = 0 + lazy-import 避 bootstrap circular 設計合理 + 1822 行 + 61 tests 重派 review cycle 開銷大 + PA §5.1 命名與 follow-up 一併處理符合 G2-02 / G9-02 / OBSERVER 慣例
- **判定方法論教訓**：
  - 凡 RCA-A 修法 layered Gate 設計必驗 5 個 invariants：(1) Gate 1 active in ALL branches 包含 fail-open 漏洞 path (2) Gate 2 仍對 valid path 生效保留 pre-FIX 行為 (3) schema validate boundary（NaN/Inf/range）(4) bootstrap migrate idempotent（only touch broken state）(5) stale data fall-through safety
  - 凡 RCA-B 修法「跳過特定 tag」必驗 3 個 invariants：(1) tag exact-match 無誤判其他 close path (2) downstream side-effects（trading.fills / PnL accounting）仍正常 (3) 改進 vs MIT 原 spec（如 B1 → B1' 用 tag 而非 PnL）邏輯更嚴謹
  - 凡 condition spawn pattern 必驗 4 個 invariants：(1) DEFAULT-OFF env-gate strict eq vs loose eq（行為改動 strict / 唯讀工具 loose）(2) singleton 為 None 時 method early return zero overhead (3) reverse channel 無條件註冊 vs push channel env-gated (4) ImportError + Exception fail-closed 不 crash
  - 凡 schema v0→v1 升級必對照 (a) Python 推送的 keys (b) Rust 接收的 fields (c) PA design plan 規定的 spec naming —— 三者 mismatch = silent regression latent；本批 H3 keys 0/7 match Rust H3RouteStats 是教科書級 schema drift hazard
  - 凡「跨進程 IPC handler」呼叫 SSOT 進程內 component 必驗 (a) 公有 facade method 路徑 (b) PA spec naming convention (c) §九 私有屬性穿透禁忌；本批 h_state_query_handler 直讀 _h1_gate / _model_router 違 §九 #8 + 偏 PA §5.1 spec
  - 凡「commit B 19min 內 invalidate commit A 期望值」（Tier 5 [20] expected sync 是繼 Phase 1+2 banner 後第二例）— PM 編排建議「同 push wave / commit B 完成手動補 commit A patch / commit A 加 TODO 標記」
  - 凡 §九 1200 hard cap violation 必判 (a) sibling 已預抽且 hot-path surgical 不可拆 → ACCEPT-with-FOLLOWUP（如 helpers.rs 6 個 free fns 可拆 sibling）(b) 沒做 sibling 預抽且純線性堆積 → REQUIRE-FIX 退回；本批 helpers.rs 屬 (a) 對齊 G9-02 ws_client.rs 慣例
  - 凡 H 狀態 cache fetcher 從 stub → real 的演化 — 必在 stub 階段建立 schema parity 測試（不只測 default）防 future Phase 接線時 silent drift；本批 PA 設計 forward-compat unknown fields drop 是雙刃劍
  - 凡 lazy-import 在 IPC handler 內必驗 3 個 invariants：(1) top-level import 不觸 circular（boot 序列死鎖）(2) ImportError + getattr None 多層 try/except 兜底 (3) never-raises contract 維持（IPC handler 對 caller 永不 propagate snapshot bug）
  - 凡 PM 派發 7 commits 中含 3 個獨立 task 必查 commit time-order：本批 5943337 (15:43) → af48ee1 (15:48, parent=deee78e) → 9120948 (15:58)；3 task sequential 不是 cohesive PR，避免 §C 範圍判定誤套用 cohesive 標準

### 2026-04-26 Tier 7 batch review (3 commits, 4b30f5e/8241133/c6ed0b3) — 3 PASS / 0 RETURN / 1 LOW FUP

- **結論**：T7.1 Track 1 Rust H3RouteStats schema align (`4b30f5e`) PASS / T7.2 Track 2 healthcheck [21] dust inventory (`8241133`) PASS-with-LOW / T7.3 Track 3 PA Phase 3 sub-task split design (`c6ed0b3`) PASS。1 FUP optional（T7-FUP-DUST-SQL-DEVIATION-DOC，PA 10min 補 PA RFC §7.4 註記 E1 cleaner SQL）
- **Track 1 4 強 claim 獨立驗證 100%**：(1) 10 keys aligned — 讀 `model_router.py:114-124` 9 stats keys + line 480 `cache_size` 注入 = 10 ✅ (2) 0 production hot-path consumer — `grep H3RouteStats rust/src/` 5 hits 全 internal + ipc h_state.rs:69 用 opaque struct via serde 無 field-name 依賴 ✅ (3) Schema parity test 真效 — BTreeSet 比對硬編碼 Python keys list，order-independent，drift 即 RED ✅ (4) Python 0 改動 — `git show --stat 4b30f5e` 1 file (types.rs) 167+/7- ✅。Linux cargo lib h_state_cache 17/0 (baseline 2195 + 17 = 2212)。閉合 E2 Tier 5 T5.3-MED-1
- **Track 2 SQL 偏離 PA spec 但屬改善**：E1 在 `COUNT(DISTINCT symbol)` 加 `FILTER (WHERE realized_pnl=0)`（PA spec 沒）+ 棄 `partial_reduce_real_count` 欄。改善理由：filtered distinct 才真是 dust spiral fan-out signal（unfiltered 會被 partial_reduce_real 活動 inflate）。Linux production cron 16:09 UTC 印 `PASS [21] ... dust_spiral_count=0` LIVE 驗證。Slot [21] 唯一性 grep 確認（[17] 從未 assign，[16][18][19][20] 已佔）。三態 verdict 邊界 14 unit tests 覆蓋 1/10/11/2/3 + null + cursor None 完整無 off-by-one。Supersede note 在 docstring + TODO.md 4 處同步
- **Track 3 PA Pattern B 決策論證 + 3 silent claim 獨立驗證**：(1) Pattern A 9-task α 全空 (Phase 1A 已建 schema) ✅ correct critique (2) Pattern C 4-task audit prelude 與 RFC §2.3 已併入的 H4 drift / H5 metadata 重複 ✅ correct judgment (3) H4 silent gap CONFIRMED — `grep validation_pass program_code/` 0 hits ✅ Sub-task 3-2 必補 (4) strategist_agent.py 1170 LOC + 25 = 1195 距 §九 1200 hard cap 5 line ✅ Phase 4 必先拆 (5) 3-1 + 3-3 file overlap CONFIRMED — `record_claude_cost layer2_cost_tracker.py:227` 是 H2 + H5 共同 hook 點 ✅ serial 強制正確 (6) Prompt template self-contained 抽 3-1 通讀 6 段式齊備
- **判定方法論教訓**：
  - 凡 sub-agent 自驗「0 production consumer」必獨立 grep 同範圍排除 def/test/re-export 確認；本 batch Track 1 + Tier 6 Track 2 兩次驗證皆成立 → pattern 收斂為「Rust mirror schema 在 Phase N stub 階段改 dormant struct 是黃金窗口」
  - 凡 PA「ready-to-deploy SQL」E1 落地時改寫必逐 token diff，分清「invariant preserved 改善（如 filter 更精準）」vs「規範違反（如 verdict 邊界改）」；前者 LOW + 文件補 follow-up；後者 RETURN
  - 凡 healthcheck 新增必驗 (a) Linux production cron 真跑通 (b) slot 編號 grep `__init__.py` 全 list 確認唯一 (c) supersede 既有 ticket 必 docstring + TODO.md 雙處留 audit trail
  - 凡 PA RFC pattern A/B/C 決策 E2 不否定設計判斷但驗證底層 claim：本 batch H4 silent gap + 1170 LOC 餘地 + file overlap 全 grep 驗證屬實 — claim-based decision 站得住腳 = PASS；若 claim 假（如「0 hot-path consumer」實際有）= 退回 PA 重 design
  - 凡 prompt template self-containedness 6 段式（前置驗證 + 文件 + 實作 + 完成標準 + commit msg + 一行回報）可作 E2 機械 check 標準 — 缺任一段 = LOW finding
  - 凡 schema parity test 用 BTreeSet 而非 list 是 order-independent 設計，未來 PA 推類似 mirror schema fix 必鏡此 pattern 否則重新 排序 fields 即破測

### 2026-04-26 Tier 8 batch review (4 commits, 8cd257e/cf39415/71faf4c/79a808a) — 3 PASS / 0 RETURN / 1 MEDIUM + 1 LOW FUP

- **結論**：T8.1 Sub-task 3-1 H2 (`8cd257e`+`cf39415`) PASS to E4 / T8.2 Sub-task 3-2 H4+silent gap (`71faf4c`) PASS-with-MEDIUM (T8-MED-1 strategist_agent.py == 1200 LOC §九 hard cap exact-touch) / T8.3 RFC §7.4 amend (`79a808a`) PASS-with-LOW (typo). Linux pytest 188/0 + cargo h_state_cache 17/0 baseline 不變 + production cron [21] LIVE PASS dust=0
- **Multi-track absorb pattern verified**：Track 1 sub-agent claim「absorbed Track 2 in-flight H4 edits to h_state_query_handler.py + test_h_state_query_handler.py via git commit --only」獨立 cross-diff 驗 TRUE — Track 1 含 H4 wiring + Track 2 0 touch shared files = atomic merge 成功，未來 PM 派 2-track parallel on shared files 可採此 pattern
- **§九 1200 hard cap exact-touch 判定為 MEDIUM 不 LOW**：strategist_agent.py wc -l = 1200（commit msg + memory + PA §10.4 三重 self-disclose），boundary itself 在 `>1200 reject` 標準下 OK，但任何 Phase 4 +1 LOC = silent violation；MUST 開 split ticket 作 Phase 4 hard pre-condition；bilingual readability 抽 1180-1200 + 945-970 spot-check NOT degraded（trim 1234→1206→1200 通過）
- **Silent gap 雙保險修法 (counter + invalidate hint pair)**：Track 2 H4 從 PA-prompted `validation_pass` grep 0 hits → 13 hits（init dict + pass branch counter + pass branch invalidate_async + get_h4_snapshot + docstring）；fail/pass 兩路徑對稱加 hint，防次級 silent gap（counter 動但 Rust 不知變化）— 此 pattern 通用化推廣
- **判定方法論教訓**：(a) sub-agent 「absorbed in-flight edits to shared files」強 claim 必 cross-diff 兩 commit 對照不接受 face value (b) §九 hard cap exact-touch 默認 MEDIUM-with-mandatory-split-FOLLOWUP，警示下次 +1 LOC silent violation (c) bilingual trim 在 §九 壓力下 spot-check 1-2 段 docstring + invariant + import 即可判 readability degraded vs not (d) silent gap fix 必 dual-pattern (counter + hint) 對稱補 fail/pass 兩路 (e) PA RFC amend §13 Deviation Log + 不重寫 §7.x in place 是非破壞性 SSOT drift correction template

### 2026-04-26 Tier 6 batch review (4 commits, 306b549..56104de) — 3 PASS / 0 RETURN / 2 FUP tickets
- **結論**：T6.1 Track 1 (4 LOW + memory) PASS-with-LOW / T6.2 Track 2 H3 schema design PASS / T6.3 Track 3 dust audit design PASS-with-LOW。FUP：T6-FUP-WARN-ZONE-FILES-SPLIT (checks_derived 869 + ipc_client 899 兩檔進警告區漸增) + T6-FUP-PA-MEMORY-INDEX-SYNC (dd4d64a 缺 PA memory append)
- **Pivot 對抗驗證 2 條**：(1) TIER4-OBSERVER 「postmortem readability 改善 ≠ 修不存在 overshadow bug」獨立 grep tier4_L309 + cron exit code 語意 byte-identical 驗證 ✅ (2) EDGE-P1b-FUP-NEGATIVE-GUARD 「ipc_client.py 真無既有 7 guard pattern 可鏡射」獨立 grep `exit_` 確認只 `exit_stale_peak_ms` typed-wrapper 暴露（L474 doc 自證）+ grep calibrator producer-side clamping ≠ ipc_client guard，故是 **typed-wrapper 第一個** ✅
- **Track 3 PA push back 5-axis 獨立 SSOT 驗證 100% 站得住腳**：fill_engine.rs:220-243 restore 只 3 scalar counters / V018:30-39 paper_state_checkpoint 4 欄無倉位 / fill_engine.rs:44-75 import_positions 唯一倉位來源 / fill_engine.rs:377 reduce_position 1e-12 threshold (0.1 dust 不刪) / owner_attribution.rs:112 SYNTHETIC_OWNER_LABELS guard (Option C real-strategy flip 真實風險)
- **Track 2 PA RFC schema mismatch 獨立驗證**：Rust H3RouteStats 7 fields + 0 hot-path consumer + Python 9 keys + cache_size = 10 + StrategistAgent 共用 L2 keys (Option A scope 風險 CONFIRMED)
- **判定方法論教訓**：(a) sub-agent 主動 pivot 必查 PA prompt vs codebase grep 對照 + 屬「精準 framing」vs「修錯需求」(b) PA push back upstream 必 5 重 SSOT 獨立驗證，不依賴 PA 字面 (c) typed-wrapper guard 必三軸驗（field 是否真暴露 / 既有 fields 是否真有 guard / producer-side clamping 是否替代 wrapper guard）(d) PA workspace report commit 必查同 commit 內 PA memory.md 索引同步

### 2026-04-26 Tier 8 Track 4 supplementary review (d1a2252) — Sub-task 3-3 H5 / Phase 3 COMPLETE — PASS-with-LOW
- **結論**：Track 4 (`d1a2252`) PASS-with-LOW to E4 (1 LOW T8T4-LOW-1 §九 layer2_cost_tracker.py 930 LOC warning zone +130, headroom 270)
- **驗證 metric**：Mac pytest **196/196 PASS** (independently re-run by E2: test_layer2 82 + test_h_state_query_handler 52 + test_h_state_invalidator 21 + test_strategist_agent 41); Rust H5CostStats schema 4 fields independently verified at types.rs:167-178 byte-identical
- **7 PM-prompted adversarial points 全 verified PASS**：(A) 4-field schema parity (B) dual hook race-window safe by daemon-thread fire-and-forget + Rust handler 無 ordering contract + set test (C) cost_tracker SSOT 共享 H2+H5 同 drop by design (D) `with_h5=False` default-off pattern 三 sub-task 一致 (E) metadata drop 不破壞下游因 get_cost_edge_ratio 仍是 SSOT (F) search hook position 在 record_search_cost 末尾 + Sub-task 3-1 H2 contract 保留 (G) `test_all_raise_drops_all_keys_version_zero` rename 5 桶 invariant 升級正確
- **lockless-read pattern 驗證**：`get_h5_snapshot` 不取 lock，鏈接 `get_cost_edge_ratio` 既有 lockless pattern；docstring 明確記錄契約「writer recalculate_adaptive 在 self._lock 下原子 replace whole self._adaptive reference」（line 588+636 grep verified） — CPython GIL 保證 attribute reference assignment 原子性
- **判定方法論教訓**：(a) Single-commit Tier review template 適合「Tier batch 後晚到 cross-tier track」76s 時序差場景 (b) Dual invalidate hook 同 callsite 必 set comparison 反映無 ordering contract (c) Hot-path snapshot lockless-read pattern 適用 SSOT 持有 value-object 屬性 + writer 始終原子 replace whole reference 場景 (d) §九 800 warning line 應作 LOC 累積信號開 follow-up `G3-08-PHASE-4-COST-TRACKER-SPLIT` LOW with Strategist split — 不無視避免重演 strategist 1200 hard-cap 直撞教訓 (e) SSOT 共享 + degradation 一致性 by design 不退回，但 test 必顯式驗證共享 drop 路徑 (f) Metadata projection at Python boundary 是設計選擇 trade-off (Rust serde forward-compat 已容忍 unknown key, 但 pre-filter 帶來窄 wire payload + 清晰 schema contract)，design judgment acceptable

### 2026-04-26 Python P0 Wave: F5 GUI + F7 healthchecks adversarial review — F5 RETURN / F7 PASS-with-MED+LOW

- **結論**：F5 (`51be82f`+`3d1fb1f`) **RETURN to E1** (3 issues：1 HIGH server-side write guard gap / 1 MEDIUM client-guard bypass / 1 LOW import-in-fn) · F7 (`4085442`+`f572edc`) **PASS to E4 with FUP** (1 MEDIUM cross-cutting [23] vs F4 audit row + 2 LOW [26]/[28] design-time concern)。F7 38 unit tests Mac worktree 跑 `OK 0.014s`

- **F5 critical gap — server-side phantom guard 漏寫入路徑（HIGH）**：5 個 GET endpoint (`/balance` `/positions` `/orders` `/fills` `/metrics`) 全套 `_phantom_view_guard()`，但 **2 個寫入 POST endpoint (`/positions/{symbol}/close` + `/close-all-positions`) 完全沒套**。違反 §二 #6 fail-closed + #2 讀寫分離。攻擊路徑：curl 直接 POST → IPC `close_all_positions {engine:"live"}` → IPC fail（live pipeline not authorized）→ `_sweep_live_orphan_positions` REST fallback **用 demo client → 誤平 demo 帳戶倉位**。Client-side `_applyLiveActionGuards()` 只 disable 按鈕 attribute（dev tools console / dynamic re-render 都可繞）。HIGH 嚴重性 RETURN

- **F5 - 個別倉位「平倉」按鈕 + closeLiveOnePosition 完全繞過 client guard（MEDIUM）**：`_applyLiveActionGuards()` 只查 3 種 button id (btn-live-stop / btn-emergency-stop / `button[onclick="openCloseAllDialog()"]`). `closeLivePosition` 走 `closeLiveOnePosition` onclick string 不在 query 範圍 — phantom 模式 client side 也可觸 POST。配合 server-side 缺 phantom guard → 雙重沒守。MEDIUM finding

- **F5 - `_resolve_live_endpoint_label` import-in-function 違反 [R1-6]（LOW）**：line 28-29 `import os` + `from pathlib import Path` 在 fn 內。`os` / `pathlib` 模組頂層 unused（已 grep 驗）。LOW finding。額外風險：import 在 try block 內，import fail（如 sys.path 異常）silently 吞回 "unconfigured"

- **F5 - test 設計缺陷 `test_phantom_guard_allows_demo_engine_with_configured_mainnet_slot`**：注解明白標出「Mainnet slot configured + Rust live engine 沒跑」場景 backend 不擋（slot configured） → balance/positions endpoint **會打真實 Mainnet REST API 拿到真實 Mainnet 帳戶資料 + 注入 actual_engine_kind=demo marker**。前端依 marker swap 到 integrity-fail view 不渲染，但 **API response payload 已含 Mainnet wallet 資料** → 攻擊者直接 curl 仍能拿到。違反 §二 #2 讀寫分離。設計 trade-off acceptable for fast development，但需明確 backlog ticket 防 production 漏（已寫進 RETURN issue）

- **F7 cross-cutting [23] vs F4 audit row 衝突（MEDIUM）**：F4 emit `unattributed:bybit_auto` audit row 進 trading.fills（context_id=`unattrib-{exec_id}-{ts}` non-NULL，**沒對應 order_state_changes**）。F7 [23] LEFT JOIN `trading.fills f LEFT JOIN trading.orders o ON o.context_id = f.context_id` → audit row fills_n=1 / orders_n=0 → 計入 `pairs_with_missing_orders`。1h 內 ≥6 個 F4 audit fill 跨多 symbol → F7 [23] 誤 FAIL「orders writer dropping rows across >5 pairs」。修法：`AND f.strategy_name NOT LIKE 'unattributed:%'` 排除 audit row。MEDIUM cross-cutting finding（需 F4 + F7 兩 PR coordinate）

- **F7 [26] brittle constant `realized_net_bps = -5.5`（LOW）**：源於 `bybit_sync` adopted positions 的 `entry_fee = 0.0`（`fill_engine.rs:62/142`）→ `realized_net_bps = 0 (gross) - 5.5 (close) - 0 (entry) = -5.5`。耦合於當前 adopted-pos 實作。如未來修「給 adopted position 補 entry_fee 追蹤」→ `-5.5 → -11`，[26] 就 silently 漏抓 regression。建議改 `realized_net_bps BETWEEN -12 AND -4` 範圍 match。LOW finding

- **F7 [28] per-symbol min_qty 通用閾值 `1e-3` 漏抓較大 symbol（LOW）**：BTC min_qty 0.001 = 1e-3 邊界 OK；ETH min_qty 0.01 → phantom 0.005 通不過 [28]（0.005 ≥ 1e-3）但 0.005 < ETH min_qty。設計上 [28] 是 fast triage 而非 full coverage，acceptable，但 docstring 應註明「fast triage; 較大 symbol 由 [21] dust inventory 接力」。LOW finding

- **F7 mock pattern 健康**：MagicMock cursor + `cur.connection.rollback = MagicMock()` 配對 defensive rollback 慣例；`fetchall.return_value = [tuples]` 直設、`cur.execute.side_effect = Exception` 模擬 schema drift；38 tests 覆蓋 PASS/WARN/FAIL/empty/exception 各 5 case；boundary value（dcs_1h=100/101 / pairs_missing=5/6）沒測 edge — 屬 minor 不阻 PASS

- **F7 [22] `engine_mode IN` schema 安全 verified**：5 表（fills/intents/orders/risk_verdicts/decision_context_snapshots）全在 V015 加 engine_mode column（含 risk_verdicts L20-23 + DCS L58-62 verified via grep）。SQL filter 不會撞 UndefinedColumn

- **F7 file size 1154 / 1200 close to cap**：`checks_strategy.py` 距硬限 46 行；下次新 check 加進去會超。建議 follow-up `F7-FUP-CHECKS-STRATEGY-SPLIT` ticket 預計畫 split timing，避免重蹈 strategist 1200 exact-touch 教訓

- **判定方法論教訓**：(a) GUI fake-success eliminate PR 必同時驗 GET (read) + POST (write) 兩面，前端 disable 按鈕不是真 guard 因 dev tools / dynamic re-render 可繞 (b) `closeLiveOnePosition` / `closeLivePosition` 雙函數命名近似但 callsite 不同 → client-guard 用 querySelector onclick string 必窮舉所有 onclick attribute 反例 (c) phantom guard 雙重判據（engine != live AND slot unconfigured）邊界邏輯 5 種狀態（mainnet/live_demo/unconfigured × engine in {live/demo/paper/unknown}）需各一 test case 完整覆蓋 (d) MIT spec 寫死的 magic number constant（如 -5.5）E2 必驗其推導鏈是否耦合於當前實作 invariant；耦合即 brittle (e) F4 + F7 並行落地時 cross-cutting 互動必驗：strategy_name pattern + context_id NULL 行為 + LEFT JOIN 結果 三軸交叉 (f) per-symbol invariant（如 min_qty）的通用閾值 [28] 1e-3 = fast triage acceptable，但 docstring 必說明 coverage 邊界 + sister check 接力
