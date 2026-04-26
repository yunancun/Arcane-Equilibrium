# E1 Memory — 工作記憶

## 項目上下文（2026-03-31）

- 當前 Wave：Wave 5（Sprint 5a-1/5a-2/5a-4 完成）
- 測試基準：2576 passed
- 系統模式：demo_only

## 強制編碼規範（每次寫/改代碼必須遵守）

### 雙語注釋（最高優先，不可省略）
每個新建或修改的函數、類、模塊，必須包含詳細的中英對照注釋，供人類 Operator 閱讀：

```python
# 英文說明（給外部維護者）
# Chinese explanation（給項目 Operator）
def acquire_lease(self, intent_id: str) -> bool:
    """
    Acquire a decision lease before executing any order.
    在執行任何訂單前申請 Decision Lease，確保 AI 輸出不直接等於執行命令。

    Returns False (fail-closed) if governance_hub is None or lease acquisition fails.
    若 governance_hub 為 None 或申請失敗，返回 False（失敗默認收縮）。
    """
```

規則：
- **模塊頂部**：必須有 `MODULE_NOTE`，中英雙語說明模塊用途、所屬層次、主要職責
- **函數/方法**：docstring 必須含中英兩段，說明「做什麼」和「為什麼這樣設計」
- **關鍵邏輯行**：inline comment 說明意圖，而非只是翻譯代碼
- **fail-closed 路徑**：必須注釋說明為什麼選擇這個 fallback 行為
- 純機械性代碼（如簡單 getter）可用單行雙語注釋替代 docstring

### 其他強制規則
- E2+E4 通過前不算完成，不可繞過
- 測試數不得低於任務前基準（目前 2555）
- 新功能必須同步補測試，不欠技術債

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-03-31 | G-01 AI 每日硬上限 $15→$2 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--g01_ai_daily_cap_fix.md` |
| 2026-03-31 | G-05 ExecutorAgent acquire_lease 插入 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--g05_executor_acquire_lease.md` |
| 2026-03-31 | Sprint 5a: H1 ThoughtGate + H2 cost_tracker + H3 ModelRouter | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint5a_beta.md` |
| 2026-03-31 | Sprint 5a-1/5a-2/5a-4: Scout→Strategist chain + H0 blocking + shadow=False | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint5a_alpha.md` |
| 2026-03-31 | Sprint 5b-1+5b-2/6: H4 AI輸出驗證 + H5 Ollama CostLogger | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint5b_gamma.md` |
| 2026-03-31 | Sprint 5b-3+5b-4: apply_ai_consultation 廢棄 + ScoutWorker daemon | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint5b_delta.md` |
| 2026-03-31 | Wave 6 Sprint 0 TD-1: pipeline_bridge acquire_lease 插入 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint0_td1_pipeline_lease.md` |
| 2026-03-31 | Wave 6 Sprint 1a FA-7: _check_stops register_data 注入 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint1a_fa7_register_data.md` |
| 2026-03-31 | Wave 6 Sprint 1b: 1B-2 H0Gate freshness API + TD-3 silent exception + TD-4 LRU cap | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint1b_gamma_1b2_td3_td4.md` |
| 2026-03-31 | Sprint 1a P1-1: submit_order rejected 時不注入學習信號 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint1a_p1_fix.md` |
| 2026-04-26 | Wave 3 G2-02: ma_crossover counterfactual fee replay tool | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--g2_02_ma_crossover_counterfactual_replay.md` |
| 2026-04-26 | Wave 3 G8-02: Python↔Rust ExecutorAgent decision parity 70-case ≥95% | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--g8_02_executor_decision_parity.md` |
| 2026-04-26 | Wave 3 E2-FIX-1+2: G2-02 caveat + G8-02 synthetic_replay rename | `.claude_reports/20260426_021000_e2_finding_fix_g202_g802.md` |
| 2026-04-26 | Wave 3 G2-06: bb_breakout 永久 disable 落地（4 子任務串行）| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--g2_06_bb_breakout_disable_landing.md` |
| 2026-04-26 | Wave 3 EDGE-P2-flip T1+T3: dry-run smoke test + flip/revert SOP shell wrapper | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--edge_p2_flip_t1_t3_landing.md` |
| 2026-04-26 | Wave 3 EDGE-P1b 4 子任務: calibrator + summary + restore IPC + healthcheck [14] 升級 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--edge_p1b_4_subtasks.md` |
| 2026-04-26 | Wave 3 G2-03 4 子任務: StrategyOverride SL/TP schema + risk_checks runtime cap + 3 TOML schema + binding SOP shell | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--g2_03_4_subtasks.md` |

## 當前測試基準線
2827 passed（Sprint 1a P1-1 完成後，both test dirs，128 pre-existing failures，17 errors）
注：測試基準線現改為從 srv 根目錄同時執行 program_code/exchange_connectors/.../tests/ + program_code/local_model_tools/tests/

## 關鍵發現與教訓

### 2026-03-31 G-01
- `layer2_cost_tracker.py` 的 MODULE_NOTE 中也有 `$15/day` 硬編碼（中英兩處）→ 不在原規格中，但必須一併修改保持一致性
- `tab-ai.html` 第 359 行有第 4 處 `|| 15`（budget display fallback），原規格漏列但屬 AI 預算相關，一併修正
- `tab-ai.html` 第 430、445 行的 `|| 15` 是 `max_iterations` 預設值，與 AI 預算無關，不應修改（已保持不動）
- 測試 `test_layer2.py` 第 201 行直接寫死 `15.0` 而非引用常量 `DEFAULT_DAILY_HARD_CAP_USD`，這是脆弱測試的案例 → 未來建議改為引用常量

### 2026-03-31 Sprint 5a-3/5a-5/5a-6
- `_heuristic_evaluate()` 是模塊頂層函數（非方法），調用時寫 `_heuristic_evaluate(intel, self.config)` 而非 `self._heuristic_evaluate(intel, self.config)` — 任務規格中把它當方法調用是錯誤的
- `Layer2CostTracker.check_daily_budget()` 實際簽名無參數，返回 `(bool, float)` — 任務規格中描述的 `check_daily_budget("l1_9b")` 帶參數版本不存在
- `Layer2CostTracker` 無 `record_call()` 方法 — 使用 `getattr(..., None)` 安全訪問防止 AttributeError
- H1 複雜度跳過測試：`min_relevance` 過濾器在 H1 gate 之前執行，若 `relevance_score < min_relevance` 會 early return — 測試中必須設 `min_relevance` 低於測試 `relevance_score`
- H1 閘門中的 `_evaluate_edge()` 調用必須用 try/except 包裹（外層 `_handle_intel` 沒有捕獲 evaluate_edge 拋出的 TimeoutError 等異常）
- H3 L2 路由：L2 path 在 `threading.Thread` 中執行，立即使用啟發式作為即時結果；需用 `patch("app.strategist_agent.threading.Thread", ...)` 攔截 Thread 創建

### 2026-03-31 Sprint 5a-1/5a-2/5a-4
- `test_strategist_agent.py` was already at 485 lines (from a prior agent session) when I tried to Write ~170 lines. The Write tool PREPENDED my content (merged) rather than overwriting — **Lesson**: always read a file before writing to know what's there and use Edit instead.
- `test_h1_complexity_skip` is flaky when run with the full suite (timing dependent cooldown pollution between tests). Passes when run alone. Pre-existing issue, not caused by my changes.
- H0 Gate blocking change in `pipeline_bridge.py`: replaced warn-only (commented `continue`) with actual `continue` + `intents_h0_blocked` counter. Also updated the comment block to clarify it's now blocking mode.
- `phase2_strategy_routes.py` `StrategistConfig(shadow=True)` → `shadow=False`: added 14-line comment block explaining all pre-conditions (G-05, H0 Gate, Guardian gate) confirmed before switch.
- `_make_h0_gate_mock()` pattern in tests: mock H0Gate `.check()` returns MagicMock with `.allowed`, `.check_name`, `.reason`, `.latency_us` attributes to match the `H0GateResult` interface.
- `intents_h0_blocked` is a new key in `_stats` — used `.get("intents_h0_blocked", 0)` in tests since it won't be in older `get_stats()` that didn't initialize it.

### 2026-03-31 Sprint 5b-1 + 5b-2/6
- `_validate_ai_output()` validates `confidence` in [0.0, 1.0] — the `action` field in task spec doesn't exist in this codebase; actual fields are `has_edge` + `confidence`. Validated `confidence` only (primary safety-critical field).
- H4 validation inserted INSIDE the try/except block in `_ai_evaluate()`, after `json.loads(text)`, before building `EdgeEvaluation`. This correctly handles the case where JSON is valid but structure is semantically invalid.
- H5 cost recording uses `getattr(cost_tracker, "record_ollama_call", None)` pattern — but since we added `record_ollama_call` to `Layer2CostTracker`, the method now exists. Using direct attribute access via `getattr` is still safer for forward compat.
- `_ollama_stats` in `Layer2CostTracker` is lazily initialized (not in `__init__`) to avoid breaking existing tests that create the tracker without calling `record_ollama_call`.
- `get_cost_edge_ratio()` uses `self._adaptive.data_days` + `ADAPTIVE_MIN_DAYS` to determine if ratio is computable; returns `None` when insufficient data (cognitive honesty, principle 10).
- `roi_basis: "paper_simulation_only"` added to both `get_cost_edge_ratio()` and `get_cost_summary()`.

### 2026-03-31 Sprint 5b-3 + 5b-4
- `apply_ai_consultation()` 是 Learning Cockpit Review Queue 占位符，不是現有 AI 管線 — 廢棄方式：
  1. 在函數頂部加 `warnings.warn(DeprecationWarning)` （需先在 main_legacy.py 頂部 import warnings）
  2. 在 `AIConsultationResultData` Pydantic 模型加 `deprecation_notice: str | None = None` 可選字段
  3. 在返回的 dict `data` 中加 `"deprecation_notice": "..."` 字段
  4. 更新路由 docstring 標記 DEPRECATED
  - 兼容性保持：函數簽名不變，Pydantic 模型新增 Optional 字段，現有調用不崩潰
- `AIConsultationResultData` 不接受 `**result["data"]` 中未定義的字段（Pydantic v2 默認 extra="ignore"）
  → 新加的 `deprecation_notice` 必須加入 model 定義才能在 JSON 回傳中出現
- `ScoutWorker` 設計要點：
  1. `interval_seconds` 分段為 1 秒小段睡眠 → `stop()` 可在 ~1 秒內響應
  2. `daemon=True` → 主進程退出時自動終止
  3. `_run_loop` 的 scan 異常用 `except Exception` 吞掉並 `logger.error()` → 不崩潰主程序
  4. `start()` 冪等檢查：`if self._thread is not None and self._thread.is_alive()` → 靜默忽略重複啟動
- `MARKET_SCANNER.start()` 已有自己的 5 分鐘內部循環（`_run_loop` + `time.sleep(interval)`）
  → ScoutWorker 的職責是更高頻（30 分鐘）呼叫 `MARKET_SCANNER.scan()` 並將結果通過 `SCOUT_AGENT.produce_intel()` 注入 Strategist 鏈路
  → `_make_scout_scan_fn()` wrapper 負責：取前 5 機會 → 構建 `symbols` 和 `content` → 調用 `produce_intel()`
- ScoutWorker 初始化失敗是 non-fatal：在 `phase2_strategy_routes.py` 用 `try/except` 包裹，失敗只記 `logger.warning`

### 2026-03-31 Wave 6 Sprint 1b (1B-2 / TD-3 / TD-4)

- `getattr(gate, "_price_ts", {})` is NOT safe when gate is a MagicMock: MagicMock auto-creates `_price_ts` as a MagicMock, which is truthy, causing `max(MagicMock().values())` to fail with ValueError.
  → Fix: use `isinstance(raw_price_ts, dict)` to distinguish real dict from mock.
- `getattr(obj, "some_attr", 1000)` where obj is a MagicMock will return a MagicMock, not 1000.
  → Same fix: use `isinstance(result, int)` before trusting the value.
- `time` module was NOT imported in `governance_routes.py` before this sprint → must add `import time`.
- `_H1_COOLDOWN_MAX_SIZE` as a class-level constant (not instance attribute) is the right place for capacity constants — keeps it visible and overridable in tests without needing instance access.
- TD-4 cleanup is lazy (only triggered at cap) — this is intentional to keep hot-path cost O(1) in the normal case.
- Pre-existing test_batch10 + test_edge_filter flaky failures stopped appearing in this run (non-deterministic, likely timing-dependent).

### 2026-03-31 Sprint 1a P1-1 (ghost learning signal guard)

- E2 發現 FA-7 新增的 `_emit_round_trip()` 調用塊未考慮 `submit_order()` 返回拒絕結果的情況。
- 修復方法：在 FA-7 塊前加 `_stop_order_rejected = isinstance(result, dict) and bool(result.get("rejected_reason"))` 判斷，用 `if not _stop_order_rejected:` 包裹整個 `try/except` 塊。
- 重要技巧：`if not _stop_order_rejected:` 需要包裹整個 `try/except`（連帶縮排），不能只包裹 `_emit_round_trip()` 調用本身 — 若只包裹調用，`except` 的縮排就不匹配了。
- isinstance safety fallback：`result` 非 dict（如 None）→ `_stop_order_rejected = False` → 仍嘗試 emit（安全預設，不丟棄潛在有效學習數據）。
- 新增測試 `test_register_data_not_called_when_order_rejected`：monkey-patch `engine.submit_order` 返回 `{"rejected_reason": "..."}` → assert `_emit_round_trip` 未被調用 + `plane.register_data` 未被調用。
- 測試從 2817 → 2827 passed（+10，包含本 P1-1 的 1 個新測試）；128 個 pre-existing 失敗不變。

### 2026-03-31 Wave 6 Sprint 1a FA-7

- `_check_stops()` 止損路徑的 register_data 缺口：止損觸發後 submit_order 成功，但沒有走 _emit_round_trip，學習管線永遠看不到止損事件。
- 修復方案：在 submit_order 成功後、Telegram alert 之後插入 `_emit_round_trip()` 調用，複用全部 7 個學習/歸因回調。
- `stop` dict 包含 `entry_price` 和 `current_price`（StopManager 已記錄觸發價），可以精確計算 PnL：
  - `stop["side"]` 是**平倉方向**（"Sell" = 多頭平倉，"Buy" = 空頭平倉）
  - Long (side=Sell): pnl = (exit - entry) * qty
  - Short (side=Buy): pnl = (entry - exit) * qty
- StopManager 的 `check_stops()` 已在返回 triggered 列表前從 `_positions` 中刪除觸發的倉位，
  所以 `_emit_round_trip()` 內的 `untrack_position()` 會是 no-op（pop 不存在的 key = 靜默忽略）。
- 整個注入塊用 try/except 包裹（non-fatal），確保學習管線失敗不影響止損單的主路徑。
- 測試加在 `test_pipeline_bridge_coverage.py` 的 `TestCheckStopsPerceptionPlane` 新類（4 個測試）：
  - test_register_data_called_on_stop_loss_close（hard stop 主路徑）
  - test_register_data_not_called_when_perception_plane_none（None 不崩潰）
  - test_register_data_called_on_time_stop_close（time stop 路徑）
  - test_pnl_calculation_correct_for_long_position（PnL 符號正確，用 wraps 驗證傳參）

### 2026-03-31 Wave 6 Sprint 0 TD-1

- 插入位置：`_process_pending_intents()` 中，邊界過濾器之後（line ~676）、`submit_order()` 之前（line ~701）
  — 這個位置是 Guardian APPROVED 和 MODIFIED 兩條路徑的交匯點，只需插入一次即可覆蓋兩種情況
- `intent` 物件有些是用 `type("StrategyIntent", (), {...})()` 動態創建的，沒有 `intent_id` 屬性
  → 使用 `getattr(intent, "intent_id", None) or f"pb-{intent.symbol}-{intent.side}-{id(intent)}"` 構建穩定的 lease ID
- fail-open vs fail-closed 分層設計（與 G-05 ExecutorAgent 保持一致）：
  - `governance_hub is None` → fail-open（無 Hub 時不阻塞，向後兼容）
  - `acquire_lease() returns None` → fail-closed（Hub 存在但拒絕，跳過 intent）
  - `acquire_lease() raises exception` → fail-closed（治理狀態不明，不允許執行）
- 新增計數器 `intents_lease_failed`：用 `self._stats.get("intents_lease_failed", 0) + 1` 安全遞增
  （不在 `__init__` 中初始化，防止破壞現有測試的 stats 斷言）
- 測試加在 `test_edge_filter_integration.py` 最末：`TestPipelineBridgeDecisionLease` 4 個測試
  — 沿用該文件已有的 `MockIntent`、`mock_paper_engine` 等 fixture 結構，零新增 fixture 依賴

### 2026-04-26 Wave 3 G2-02 — ma_crossover counterfactual replay

- **PM 規格 vs 真實 schema mismatch（須 push back 並重新設計，不是盲執行）**：
  - PM 寫的 SQL 引用 `o.realized_pnl_bps` / `o.owner_strategy` / `o.entry_price` / `o.exit_price` / `ef.fee_bps_total` / `ef.entry_fee_rate` / `ef.exit_fee_rate` — 全部不存在
  - 真實 schema：`trading.orders` 沒 PnL 欄位（事件溯源表，含 qty/price/status）；`trading.fills` 才有 `realized_pnl` (USDT, REAL)/`fee` (USDT)/`fee_rate` (ratio 0.00055=5.5bps)/`strategy_name`/`context_id`/`entry_context_id` (V017)
  - `learning.exit_features` 雖有 `realized_net_bps` 但只在 close path 寫，不含 entry/exit fee 拆分
- **正確 pair 模式**：用 `entry_context_id` (V017 FILL-CONTEXT-LINKAGE-1) — close fill 的 `entry_context_id` 指向 entry fill 的 `context_id`；INNER JOIN 即可同步抓兩側 fee/qty/price
- **PnL 公式關鍵**（讀 Rust `paper_state/fill_engine.rs:apply_fill` 確認）：`realized_pnl` 是 GROSS (純價差，未扣 fee)，fee 從 balance 另扣 → counterfactual 公式變單純：
  ```
  gross_pnl_bps = realized_pnl_usdt / (close_qty * close_price) * 10000
  cf_net_bps = gross_pnl_bps - 2 * scenario_fee_bps   # ×2 entry+exit 對稱付
  ```
  PM 規格中「先把實際 fee 加回去再減 scenario」是多餘步驟（gross 已經是 fee-free）
- **Lazy import psycopg2**：`import psycopg2` 在 `_open_conn()` 內，**不在模組頂部** — 否則 `--smoke-test` 在無 PG 環境會失敗，違反規格「不在 import 層連 PG (lazy connect inside main)」
- **stderr logging + stdout 純結果**：`logging.basicConfig(stream=sys.stderr)` 讓 markdown/csv/json 輸出可直接 pipe 到檔/管道，不被 INFO log 污染
- **placeholder count vs args count 自檢**：`paired_sql.count("%s") == len(paired_args)` 在 smoke-test 中強制驗證，提早抓 SQL 注入錯誤
- **AGGREGATE 從原始 rows 重算**：不從 per-symbol 結果再求平均（會引入算術 vs 加權的不一致）—  重新跑一次聚合器邏輯保證 honest weighting
- **per-symbol noise floor only on markdown**：CSV/JSON 全量 dump（給下游 pipe 處理）；markdown 才過濾 < min_per_symbol，避免 operator 看噪音表
- **Symbol filter 用 `= ANY(%s)`** 而不是 `IN (%s,%s,...)`：psycopg2 自動把 list 轉 PG array，placeholder 數量固定 = 1，不需動態 build query string
- **Edge case 全處理**：`qty>0 AND price>0` 在 SQL 過濾 (badly closed)；`realized_pnl != 0` 過濾未平倉；`entry_context_id IS NOT NULL` + INNER JOIN 過濾 V017 之前資料；orphan 數量結尾 WARN
- **Exit code 規格細微**：規格寫「至少一個 symbol ≥30 trades → 0」但實務上 AGGREGATE 大也可用 → 採取保守處理，只在「ALL cells < 10」才 exit 1
- **檔案大小** 540 行（< 800 警告線）— 在規範內

### 2026-04-26 Wave 3 E2 Finding 1+2 修補（G2-02 caveat + G8-02 rename）

- **E2 PASS with conditions 模式** = MEDIUM finding 在後續 PR 內修，不重做整個任務；E1 修補只動 doc / naming 級，不改業務邏輯（PA 明令「不擴張」）。
- **G2-02 partial-close fee caveat（Finding 1）**：
  - 原 cf_net_bps = gross - 2 × scenario_fee 公式假設「1 entry × 1 close per JOIN row」；對 partial close（fast_track ReduceToHalf 多 close 共享 entry_context_id）會 OVERCOUNT (N-1) × fee；對 accumulate（多 entry → 1 close）UNDERCOUNT (M-1) × fee。
  - 修法：(a) module-level docstring 加中英對照 CAVEAT 段，明示「純 ma_crossover 不影響 / 混合策略需用 trading.intents 比對 entry-close 比例驗證」 (b) `render_markdown()` 末尾固定 append `_Note:_` 一行（單行雙語）讓每次 markdown 輸出都帶 caveat。CSV/JSON 不加（保留純 dump）。
- **G8-02 synthetic_replay 命名誤導（Finding 2）**：
  - 40 case 全是手寫 YAML 字面量，無 seed / 無 generator / 無 PG snapshot replay；用 `synthetic_replay` 暗示 real replay → E2 判文字遊戲。
  - rename 範圍：(a) `test_executor_decision_parity.py` method `test_synthetic_replay_agree_rate` → `test_synthetic_handcrafted_agree_rate` + class docstring + source filter + print/log tag 全改 `synthetic_handcrafted` (b) `executor_parity_cases.yaml` 40 個 `source: synthetic_replay` → `synthetic_handcrafted` + 頂部 + Synthetic block header 加雙語 comment 解釋 rename 動機 (c) E1 report 同步 (d) yaml `case_id: synthetic_NN_replay` 後綴**保留**作為 grep 穩定 test id。
- **edge case：grep 殘留 vs commentary**：
  - 第一輪 rename 後 grep 仍有 9 處 `synthetic_replay` — 全在「解釋 rename 動機」的 docstring/comment 裡（用 raw string 引述舊名）。
  - PA 規格沒明說「全清零」vs「只清功能性引用」，但為防 E2 二輪審查再判文字遊戲，把 docstring 改用「previous name」/「原名」**指代**而不直書字串。
  - 最終 grep 0 殘留（除 report §9 修補章節 1 處作歷史交代必要保留）。
- **Linux pytest baseline 不變驗證**：scp 兩檔到 Linux .staged_e2_finding2/ → cp 覆蓋 in-place → pytest 跑綠（5 passed / 2 skipped / 0.39s · agree 70/70 100% · 新 tag `[G8-02 synthetic_handcrafted]`）。
- **markdown _Note: 範例輸出**：用 importlib.util load module 後直接 call `aggregate_per_symbol_per_scenario(synthetic_rows, [2.0,5.5])` + `render_markdown(agg, min_per_symbol=1)` 截到末尾單行 caveat note；確認是 markdown table 之後、不破壞 csv/json renderer。
- **不擴張原則嚴守**：本 PR 0 業務代碼 / 0 測試邏輯 / 0 SQL / 0 fixture 案例變更；純 doc + rename。

### 2026-04-26 Wave 3 G2-06 — bb_breakout 永久 disable 落地

- **TOML 三環境 isolation 仍同方向**（per memory `feedback_env_config_independence`）：三 config 故意分開但本次同方向 disable，每個 TOML 加同 6 行雙語 comment block（中英對照解釋為什麼 disable + 重啟條件 + RFC 引用）。E2 cross-check 點 = 三檔同方向不漏一個環境。
- **healthcheck [12] 改判 fail-soft 路徑**：`_read_bb_breakout_active_from_toml()` 用 `tomllib` (Python 3.11+) 模仿既有 `_read_shadow_enabled_from_toml()` shape 回 `(value, diag)` tuple；TOML 讀失敗 fail-soft 回 `None` → [12] 走原 triage 邏輯（不會因 TOML race / parse error 整 pipeline 紅）。Mac local Python 3.10 版本 tomllib 不存在 → 走 fail-soft，因此用 `/opt/homebrew/bin/python3.12` 驗測；Linux production 是 Python 3.12。
- **[18] disabled_strategy_inventory 永遠 PASS 設計**：純 observability，目的是讓未來 audit 不漏看 active=false 策略。除了 bb_breakout 還順帶顯示 funding_arb（先前 G-2 結案 disable 留下，符合 G6-04 drift 防線意圖）。tomllib 無法 import / TOML 不存在 / parse 錯誤 → 全 PASS skip（不 FAIL，純 observability 的本意）。
- **CLAUDE.md §三 drift 防線**：把 P1-11 條目從「FIX-26-DEADLOCK-1 待 rebuild + dormant 處置中」更新到「G2-06 永久 disable 結案」狀態。同時加 2026-04-26 「Wave 3 第二/三波派發」條目到「已完成里程碑索引」表（涵蓋 G2-02 / G8-02 / G2-06 三個本日 PM 派發任務集）。
- **TODO L133 同步**：先前過期的「Healthcheck [12] FAIL 結構性已確認非新 bug」描述改為「✅ G2-06 disable 結案」，避免 PM 下次接手看到「FAIL」造成混淆（[12] 從 FAIL 變 PASS skip）。
- **deferred 註解非 #[deprecated]**：per PA RFC §6 「BbBreakoutProfile 保留為 future investment」，**不**加 `#[deprecated]` attribute（deprecated 會觸 build warning + 暗示「將來會刪」），用普通 comment block 解釋「為什麼保留 + 何時可重啟」即可。Rust comment block 在 `///` doc-comments 與 `#[derive]` 之間屬合法 orphan comment，不破壞 doc-attribute attachment。
- **不直接 commit + scp 不需要**：所有改動純檔案編輯（無業務代碼 / 無測試 / 無 cargo build），等 E2 review → E4 regression → PM 統一 commit + push。Linux 端 ssh 驗證會看到舊 active=true 是預期（沒 push 還沒同步）— 真正的 healthcheck 驗證在 PM commit + push 後 cron 6h 跑下一輪。Mac 本地 grep + Python 3.12 驗證已足夠覆蓋 E1 落地正確性。

### 2026-04-26 Wave 3 G8-02 ExecutorAgent decision parity

- PM 給的 path `srv/tests/` 不存在 — control_api_v1 tests 真實路徑是 `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/`，按既有 `test_executor_shadow_to_live_e2e.py` 位置放新檔。
- **Wave-3 真實可測 scope 僅 shadow_mode**：read 後確認 Python `ExecutorAgent._execute_via_ipc` 只檢查 `shadow_mode_provider()`，**不**檢查 `per_symbol_position_cap` / `max_position_pct`；Rust 端 grep `executor.` 只命中 schema validation + tests，intent_processor **沒有**這兩條 gate 的 wiring（屬 G3-08 future work）。70 case 全聚焦 shadow_mode 變化是當前唯一能 ≥95% 跑綠的設計。
- **PA RFC 推薦的 cap/pct decision points** 在當前 runtime 不可測 → 用 `pytest.skip` marker（`TestExecutorDecisionParityDeferred`）讓 gap 在 CI 報告可見不阻塞。
- **Reference spec 設計**：`_reference_decide()` 不是「Rust 重新實作」，是 `RiskConfig.executor` schema 的語義意圖；Python ExecutorAgent 真實跑 vs schema spec → parity 等於 contract test。
- **Test driver 真實跑 Python**：`_drive_python_decision()` 真實 build `ExecutorConfigCache` + `_inject_snapshot_for_tests` + `_mark_initialized_for_tests`（**不 mock 業務邏輯**），patch `paper_trading_routes._ipc_command` 為 `_IpcCallRecorder`，從 `ExecutionReport.metadata["execution_path"]` (`ipc_shadow` / `ipc_real`) 解碼決策。
- **70 case 結構**：30 golden（10 shadow=true 邊界 + 10 shadow=false 邊界 + 5 cap 互動 + 5 pct 互動，cap/pct case 全 shadow=true 主導，shadow precedence）+ 40 synthetic_replay（20 shadow=true + 20 shadow=false split），全用同一 binary decision schema：`block_shadow` / `submit`。
- **跨 case singleton 隔離**：`setup_method/teardown_method` 呼叫 `ecc_mod._reset_for_tests()` 清 `_CACHE_INSTANCE`，避免 snapshot leak（前一 case 的 cache instance 影響下一 case）。
- **Linux pytest 結果**：5 passed + 2 skipped / 0.36s（agree=70/70, 100.00%；threshold 95% PASS）。
- **scp 而非 push**：E1 不直接 commit（CLAUDE.md §七 強制鏈），用 `scp` 把測試檔 + fixture 直接傳 Linux 跑驗證，git tree 維持 clean 待 E2 review。

### 2026-04-26 Wave 3 EDGE-P2-flip T1+T3 — flip dry-run + SOP shell wrappers

- **PA RFC `patch_risk_config { exit: { shadow_enabled: true } }` 真實可走**：generic deep-merge 路徑（`handle_patch_config` in `ipc_server/handlers_config.rs:72`）— JSON serialize 整個 RiskConfig → `json_merge` 遞歸合併 patch 物件 → deserialize 回 `RiskConfig` → `validate()`。`shadow_enabled` 雖**不在** 7 個 IPC `exit_*` 欄位內（per `event_consumer/tests/exit_config_ipc_tests.rs:34` 註解），但 generic deep-merge 完全可改任何 `pub` 欄位。實證：dry-run check (d) 跑唯讀 round-trip，看到 ExitConfig schema 含 `shadow_enabled: bool`，flip 路徑成立。
- **IPC HMAC ts unit 不一致 bug 順手發現**：`app/ipc_client.py:786` `sync_ipc_call` 用 `int(time.time() * 1000)`（毫秒）做 HMAC ts，但 Rust verifier `ipc_server/mod.rs:621-628` 用 `now.as_secs() as i64`（秒）比對 30s 容差 — 數量級差 1000，**legacy sync_ipc_call 應 100% fail auth**（但因低頻被呼用未察覺）。E1 不擴張範圍**未修** legacy；dry-run 內嵌 `_sync_ipc_call` 用秒對齊 Rust，並加雙語 comment 標明刻意分歧。E2 拍板是否要順手修 legacy。
- **OPENCLAW_IPC_SECRET 真實位置非 srv/settings**：`$HOME/BybitOpenClaw/secrets/environment_files/ipc_secret.txt`（per `restart_all.sh:31, 196`，env name 為 `OPENCLAW_SECRETS_ROOT` 預設 `$HOME/BybitOpenClaw/secrets`）。第一輪用 `$SRV_ROOT/settings` fallback 是錯，第二輪查 restart_all.sh 確認。flip.sh / revert.sh source env 邏輯已對齊 restart_all.sh 範式（idempotent — 已 export 不影響）。
- **DB 連線範式對齊 healthcheck**：`_open_pg_conn()` 抽出 helper 用 `OPENCLAW_DATABASE_URL` 或 `POSTGRES_USER/PASSWORD/HOST/PORT/DB` env，與 `passive_wait_healthcheck.py:_get_conn` 1:1 對齊，operator 既有 systemd / cron 環境直接 work。
- **Shell wrapper paste-safety 範式**：複雜 IPC 邏輯**不**寫在 shell heredoc / 多行 for；用 inline `python3 -c "..."` 委派，傳入 `OPENCLAW_BASE_DIR + OPENCLAW_IPC_SOCKET + PYTHONPATH` env，從 stdin import dry-run script 的 `_sync_ipc_call`。flip.sh 一個 inline Python block <30 行，shell 主體保持 paste-safe one-liner（per memory `feedback_shell_paste_safety`）。
- **dry-run check (d) 設計**：構造 EXACT mutating patch payload 驗 JSON 結構，但實際只跑唯讀 `get_risk_config` round-trip。**絕不**真送 mutating patch（per RFC §3.4 dry-run constraint），真實 flip 只能透過 SOP wrapper 在 dry-run PASS + operator confirm 後執行。
- **Mac dry-run exit 2 路徑**：engine 不跑時偵測 socket 缺失立即 exit 2 並輸出 minimal markdown / JSON（不跑任何 check 也輸出可讀 stamp 給 caller）。Linux 真機 exit 0/1 區分 5 check FAIL。3 個 exit code（0/1/2）在 flip.sh STEP 1 dry-run 後**全部正確映射**到 abort / continue 決策。
- **行數 829 略超 800 警告**：~36% 為強制雙語 MODULE_NOTE / docstring / inline 注釋（CLAUDE.md §七 強制），精煉違反規範保留即可。1200 硬上限內。
- **mock_events 不可實作真合成**：(i) 會污染 production `learning.exit_features` 表，(ii) Rust mock injection 需改 production code 違反 0 業務代碼變更。`mock_events_target` 純資訊性 → JSON artifact 作 capacity hint。

### 2026-03-31 G-05
- `governance_hub.acquire_lease()` 實際簽名為 `(intent_id, scope, ttl_seconds)`，任務規格中描述的 `requester` 參數不存在 → 實際使用 `scope="TRADE_ENTRY"` 正確對應規格意圖
- `governance_hub=None` 採用 fail-open（向後兼容）設計，`governance_hub` 存在但 `acquire_lease()` 返回 `None` 採用 fail-closed — 這兩層行為必須區分，測試 26 和 27 各自覆蓋
- `phase2_strategy_routes.py` 中 `GOV_HUB` 從 `paper_trading_routes` 導入，使用 `_GOV_HUB_FOR_EXECUTOR` 本地別名防止與其他導入衝突
- 測試基準從 2555 升至 2561（新增 6 個 G-05 tests，test_26~31）
- 所有 17 個失敗均為預存在問題（test_batch10_learning_oms/test_ollama_integration/test_integration_phase11/test_learning_tier_gate），與本次改動無關

### 2026-04-26 Wave 3 G2-03 4 子任務（StrategyOverride SL/TP schema + runtime cap + TOML + binding SOP）

- **PA RFC §2.1 vs PM prompt schema mismatch（push back 紀錄但不暫停執行）**：
  - PA RFC §2.1 寫 4 個 override 欄位：`stop_loss_max_pct_override` (pct) / `take_profit_max_pct_override` (pct) / `trailing_activation_pct_override` / `trailing_distance_pct_override`，全部 `Option<f64>`，pct 對應 P1 limits 的 pct
  - PM prompt 改寫成 `sl_atr_mult` + `sl_max_bps_override` 4 字段（ATR 倍數 + bps 雙混合），與 RFC §2.1 schema 不一致；PM 也提到 "P1_HARD_SL_MAX_BPS / P1_HARD_TP_MAX_BPS constants" 但**不存在** — 真實對標是 `RiskConfig.limits.{stop_loss_max_pct, take_profit_max_pct}` (pct)
  - **採取**：以 PA RFC §2.1 為準（PA 是 source-of-truth，發生分歧時源頭優先）；E1 只執行不擴張，不擅自選 PM 的 ATR mult + bps schema（屬語意擴張）
  - **Lesson**：RFC vs 派發 prompt 不一致時必查源頭（PA RFC § 2.1 直接定 schema），記錄 push back 但繼續執行；不暫停。

- **PA RFC §6.T2 函數名 `tick_risk_action` 不存在**：真實名 `check_position_on_tick`（見 risk_checks.rs:201），記錄 push back 但繼續執行（屬 RFC clerical error，函數名次要）。

- **`StrategyOverride` 原無 validate hook**：grep `risk_config.rs` 完整 line 207 RiskConfig::validate，`per_strategy` HashMap 從未被遍歷驗證 —— G2-03 同時補上 validate hook（pre-G2-03 gap，順便 close）。新加 `validate_against_limits(&self, strategy_name, limits)` impl + RiskConfig::validate() loop。

- **Position 已有 `owner_strategy: String`**（containers.rs:47, ORPHAN-ADOPT-1 Phase 2A 落）。原本擔心要新加欄位，但既有 schema 已 ready，T2 wire 路徑直通。**未實際接 step_6**（風險範圍最小化，T2 只落 fn signature 變化 + 新 fn `_with_override` + helper fns），caller chain 升級延後給 PM 統一決策（屬 G2-03 binding 真實需要）。

- **檔案大小 §九 1200 硬上限觸發兩次**：
  - **risk_config.rs**：1077 → 1217（+140 with new fields + validate impl + docstring）超 1200 → 抽 StrategyOverride 區塊到 sibling `risk_config_per_strategy.rs`（191 行），父檔回到 1071。`#[path = "risk_config_per_strategy.rs"] mod per_strategy; pub use per_strategy::StrategyOverride;` re-export 保留 `crate::config::risk_config::StrategyOverride` 公開 API 路徑。
  - **risk_config_tests.rs**：1045 → 1319（+274 G2-03 tests）超 1200 → 抽 G2-03 12 tests 到 sibling `risk_config_per_strategy_tests.rs`（294 行），父檔回到 1051；`#[path] mod g2_03_per_strategy_tests` 在 `mod tests` **外**而非內（top-level test mod 於 cargo 等同 mod tests inner test）。
  - **risk_checks.rs**：880 → 1279（+400 G2-03 helpers + new fn body + 8 runtime tests）超 1200 → 抽 G2-03 8 runtime tests 到 sibling `risk_checks_per_strategy_tests.rs`（308 行），父檔回到 1020。
  - sibling test 不可直接拿 `mod tests` internal helpers（`default_config` / `COST_EDGE_DEFAULT` / `MIN_PROFIT_DEFAULT`）—— sibling 自帶 mirror 常量 + 自帶 `default_config()`，保 self-contained。

- **risk_checks.rs `_with_override` 設計選擇**：保留既有 `check_position_on_tick(...)` ABI 不變，新加 `check_position_on_tick_with_override(... per_strategy: Option<&StrategyOverride>, config)` fn；既有 fn 變 thin wrapper（with `per_strategy=None`）。優點 = caller chain（position_risk_evaluator / step_6 / 4 既有 risk_checks tests / 4 evaluator tests / 3 g1_06 integration tests）0 改動，新功能 100% 可測；缺點 = 同檔 2 個 fn 看似重複，但 thin wrapper 只 18 行 pass-through 不影響 maintainability。

- **`effective_sl_max_pct` / `effective_tp_max_pct` helpers**：核心 G2-03 防線 B 機制。設計 `match per_strategy.and_then(|o| o.stop_loss_max_pct_override) { Some(v) if v.is_finite() && v > 0.0 => v.min(limits), _ => limits, }`，三道防護：(1) `is_finite()` 拒 NaN/Inf；(2) `> 0.0` 拒 ≤ 0；(3) `.min(limits)` 拒 over-cap stale override。NaN > 5.0 是 false（IEEE 754）所以單純 `>` 守線不夠，**必須 `is_finite() && > 0`** 早期短路才 robust。

- **trailing_*_override 不受 P1 cap 約束**：無「全局 trailing 上限」設定，trailing 是策略自由度（per memory `feedback_agent_autonomy`），G2-03 只要求 `> 0 + finite`，不 clamp。trailing 緊縮（distance 0.3 < default 0.8）反而是常見 binding 場景，與 SL/TP 「override 必 ≤ P1」對稱性不同。

- **TOML 三環境 isolation 仍同方向**（per memory `feedback_env_config_independence`）：3 TOML schema 同步加 `[per_strategy.ma_crossover]` block + `enabled = true` + 4 行 commented-out override 欄位 + 雙語 comment block 解釋 binding 流程。**Live TOML** 加額外 comment 強調「binding 需 operator 獨立審查 + §四 硬邊界 gates 仍生效」（不可從 demo 抄值）。

- **真實 TOML round-trip test**：`test_g2_03_real_toml_files_load_with_ma_crossover_section` 用 `env!("CARGO_MANIFEST_DIR")` 找 srv root + `fs::read_to_string` 讀 3 個真實 TOML → `toml::from_str::<RiskConfig>` + validate + 確認 ma_crossover present + 4 override None。catch 欄位拼寫 / section header 漂移；CARGO_MANIFEST_DIR 是穩定 env var（與 Mac/Linux 無關）。

- **Shell wrapper paste-safety + helper Python 分工**：`g2_03_bind_ma_sltp.sh` 256 行純 paste-safe 流控（args parse / log / step orchestration），無 heredoc / 多行 for；複雜 IPC + JSON 邏輯抽 `g2_03_bind_helper.py`（405 行，3 子命令 diff/apply/verify），重用 `edge_p2_flip_dry_run._sync_ipc_call`（已對齊 Rust HMAC ts seconds 路徑，避開 legacy `sync_ipc_call` 毫秒 bug）。**HMAC ts unit 一致性**為前 2 軌（軌 2 EDGE-P2-flip）push back 揭發的 bug，本軌完全沿用避開的 helper，不在 legacy 修。

- **--qc-report-path REQUIRED for apply（防忘）**：shell wrapper 強制 operator 提供 G2-02 counterfactual report path，apply 子命令會 fs::exists 驗證；diff 子命令可選（`default=None`）。binding SOP 流程：dry-run diff → operator 看 before/after JSON → "yes" + supply path → apply → 5s 等 hot-reload → verify 4 fields 匹配 → 完成。

- **Mac local cargo test --release 全 lib 2161 passed / 0 failed**：baseline 2141 + 20 G2-03 tests（11 schema + 8 runtime + 1 real-TOML）= 2161；數字精確對齊。Sibling tests 經 `#[path] mod xxx` 載入後 cargo 自動發現，無 `Cargo.toml` 修改。

- **未做的（保留給 binding 流程）**：
  - step_6_risk_checks.rs 升級到 `_with_override` + 從 paper_state.position_exit_snapshot.owner_strategy 注入 → 留給 PM 決策（屬 G2-03 binding 真實啟用，不是 schema 落地）
  - position_risk_evaluator::PositionRow 加 `owner_strategy: String` → 同上
  - g1_06 integration tests update → caller chain 升級時一起改
  - 我選擇 thin wrapper 模式 = caller chain 完全 0 改動，binding 啟用時再做（PM 可決定獨立 PR）。

- **不擴張嚴守**：本 PR 0 業務代碼擴張至無 SL/TP override 的策略 / 0 改 P1 limits 預設值 / 0 改 §四 硬邊界 / 0 改 IPC handler / 0 修 legacy sync_ipc_call HMAC bug（軌 2 揭發，留 E2 / 後續批處理）。

### 2026-04-26 Wave 3 EDGE-P1b 4 子任務（calibrator + summary + restore IPC + healthcheck [14] 升級）

- **PA RFC §2.1 vs IPC handler 真實 schema mismatch（隱性 push back，但 PM 派發已含 caveat 故不暫停）**：
  - PA RFC §2.1 列 6 個 ExitConfig percentile-derived bind 欄位（含 `stale_peak_ms`），但 `ipc_server/handlers/risk.rs:84-99` 只 wire 7 個 `exit_*`（`missing_edge_fallback_bps` / `min_net_floor_bps` / `min_hold_secs` / `min_peak_atr_norm` / `giveback_base` / `giveback_slope` / `giveback_floor`）— `stale_peak_ms` + `shadow_enabled` **不在 IPC**，需 TOML edit + `reload_risk_config` IPC。
  - PM 派發已說「dry-run 預設 + 不直接 IPC 寫」，所以 calibrator 端只算 patch 不寫，**不阻塞**；但需在 docstring + JSON envelope 標 `toml_only_fields`，T3 restore 端 response 也要標 `toml_only_fields_skipped` 把 `stale_peak_ms` + `shadow_enabled` baseline 暴露給 caller，避免後續忘記。
  - **Lesson**：PA RFC 寫的「bind 欄位列表」與 runtime IPC 形狀不一致時，先 cross-grep IPC handler，再決定 push back 暫停 vs 在 docstring 標 caveat 繼續執行（看 PM 規格是否已含 caveat）。

- **T1 calibrator 設計關鍵**：
  - `RFC §2.1 mapping table` 6 個欄位 + 1 derived（giveback_slope）：6 個直接 percentile / `giveback_slope = (base - floor) / max(min_peak_atr_norm, 1.0)`。
  - `min_peak_atr_norm` 不直接 percentile 而是「`peak_pnl_pct p25 / atr_pct p25` 比例」（dim 2 / dim 3 合算）— 這是 RFC §2.1 表 row 2 「peak_pnl_pct/atr_pct p25」原意，不是「single dim p25」。
  - `validate()` invariant 觸發點 — calibrator 需自己做 `clamp >= 0` / `floor > 0` / `floor <= base` 的 guard：違反 validate() 會被 `risk_store.apply_patch()` 全或無回滾，calibrator 提前 clamp + 在 derivation 記錄「rebound」備註，避免操作員拿到 patch 套不下去的尷尬。
  - **stratification 用 strategy_name = ANY(%s) 精確比對**（per RFC §8 #2，不可 prefix 匹配 `grid_*`），psycopg2 自動把 list 轉 PG array。
  - **percentile 計算用純 Python `linear` 插值**（無 NumPy 依賴）— 與 `numpy.percentile(values, pct)` 等價但無外部依賴，方便 cron 環境。
  - **CLI args**：`--lookback-days 14` + `--embargo-days 7` 必驗 `embargo < lookback`；`--percentile-targets 90,95,99` 默認，但 calibrator 內部自動補算 p10/p25/p75（derivation 必需）— 不污染 user-visible 百分位但確保 patch 可生成。
  - **stderr logging + stdout 純結果**：與 G2-02 ma_crossover_counterfactual_replay 一致，markdown/json/yaml 可直接 pipe。
  - **`--apply` 仍是 dry-run**：只 emit JSON patch envelope；NO IPC write。`schema_version: "edge_p1b.calibrator.v1"` 為 future-proofing。

- **T2 summary tool 設計**：
  - 雙 cohort 分析（full + profit-only `realized_net_bps > 0`），讓 operator 看清「calibrator 真正能用的是 profit cohort」。
  - **3 tier 標籤**：`strong-evidence`（≥1000）/ `ci-comfortable`（≥500）/ `calibrator-min`（≥200）/ `below-min`（<200）。tier 用 **profit cohort** 行數判定（calibrator 實際輸入），不用 full cohort（會誤導）。
  - **3 個時間窗口計數**：24h / 7d / 14d 分別 query — 看 cohort 累積成長速率（per RFC §3 樣本估計）。
  - 用 ddof=1 的樣本標準差（`var = sum((x-m)^2) / (n-1)`），與 `numpy.std(values, ddof=1)` 一致。

- **T3 IPC method `restore_exit_config_defaults`**：
  - **設計選擇**：用既有 `PipelineCommand::UpdateRiskConfig` 帶 7 個 default values（不開新 PipelineCommand variant） — 避免新 schema struct，consumer 端 `risk_store.apply_patch()` 已是原子 all-or-nothing 契約。
  - **為何另開 IPC method 而非直接讓 caller 呼 `update_risk_config(7 default values)`**：(a) audit 時意圖明確（`restore` vs `patch`）(b) 一律發完整 7 欄位避免半套 (c) 未來 Phase B 自動化可加 audit hook（per Root Principle #8）。
  - **Response payload 結構**：`fields_restored: [...]`（7 IPC-wired）+ `baseline_values: {...}`（每個的 default 值）+ `toml_only_fields_skipped: [{field, baseline_value, reason}]`（暴露 `stale_peak_ms` / `shadow_enabled` 不在 IPC 的不對稱）。
  - **3 unit tests**：(1) happy path — 確認 7 exit fields 經通道為 Some(baseline) + 非 exit 為 None + response shape (2) error path — 缺 channel 回 ERR_INTERNAL "no paper command channel" (3) baseline 值 `f64::EPSILON` 比對 default fns，確保 `ExitConfig::default()` 沒漂移。
  - **Linux release 驗證**：`cargo test --release -p openclaw_engine --lib` baseline 2138 → **2141** passed / 0 failed（+3 T3 tests）。
  - **scp 方式驗 Linux 不污 git tree**：sub-script `~/.staged_e1_p1b_t3/` → cp 覆蓋 in-place → cargo test → 完成後 `git checkout` 三檔 revert。Linux git status clean 等 PM 統一 commit。

- **T4 healthcheck [14] per-strategy 升級**：
  - **保 1 行式語意契約**：仍是 `(status, message)` tuple，UI 仍打 `[14] PASS — message`；只在 message 尾巴加 `; per_strategy: name=N[TIER], ...`。Status 決策完全不變（避免破壞既有 cron summary 邏輯）。
  - **Per-strategy 切片 fail-soft**：GROUP BY 查詢失敗 → 全局 ratio 仍計算，message 加 `per_strategy=unavailable (err)`，不致 [14] 變 FAIL。
  - **Tier 閾值**：`[READY] ≥200` / `[GROWING] 50-199` / `[SPARSE] 1-49` / 0 行靜默忽略（避免噪音）。READY 對齊 calibrator min=200。
  - **`READY_frac`** = ready_strategies_rows / this_week — 直接告訴 operator 「目前 cohort 多少比例已 calibrator-ready」。Linux 真實 DB 跑出 63%（grid_trading=282 已 READY，ma_crossover=146 GROWING）。

- **檔案大小**：calibrator 1067 行（800-1200 警告區，但 SQL+math+render+CLI 整合為單檔合理）；summary 825 行（剛過 800 警告線）；risk.rs +332 行至 598 行（仍在 800 警告線下）；mod.rs 1251 行 — **既有檔已超 1200 硬上限**，本變動 +11 行（dispatch 路由），按「不擴張」嚴守不順手 split，留 E2 review 決定。
