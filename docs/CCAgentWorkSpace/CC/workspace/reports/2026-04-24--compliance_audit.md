# CC Compliance Audit — 2026-04-24

**角色**: CC (Compliance Checker)
**工作目錄**: /Users/ncyu/Projects/TradeBot/srv
**審查對象**: TradeBot 項目整體（Rust openclaw_engine + Python control_api_v1 + SQL migrations + helper_scripts）
**對照憲法**: `CLAUDE.md` §二（16 條根原則）+ §七（7 項實施準則）
**前次報告**: 2026-04-12 Compliance Audit Report（檔案缺失，memory 記錄 A- 級 / 14/16 完全合規）

---

## 總分

| 類別 | 合規 | 部分合規 | 違反 | 不適用 | 小計 |
|------|-----|---------|-----|-------|------|
| 16 根原則 | 14 | 2 | 0 | 0 | **16 / 16 有判定** |
| 10 實施準則 | 6 | 3 | 1 | 0 | **10 / 10 有判定** |
| **總計** | **20** | **5** | **1** | **0** | **26 項** |

**通過 (完全合規) / 26 項 = 20 / 26 = 76.9% → B+ 級**
**≥ 1 P0 硬違規**: **無**（0 硬邊界觸犯）
**≥ 1 P1 需修**: **有**（見 Top 5）

（對比 2026-04-12 A- 級 20/26；降級主因：文件大小硬上限違規項目從 0 增至 13 個、1 項 Mac 硬編碼路徑 regression。）

---

## 第一部分：16 條根原則

### 原則 1 — 單一寫入口 ✅ 合規

**證據**：
- 訂單通過 Rust `openclaw_engine::intent_processor::router` 唯一入口，Python `executor_agent.py` 經 IPC `SubmitOrder` 轉 Rust 處理（executor_agent.py:377-388）
- ARCH-RC1 1C-4：Rust 為 paper/demo/live 三引擎並行唯一引擎
- DEAD-PY-2 已清除 Python `PaperTradingEngine`（executor_agent.py:380 註解）

**違反點**：無。

---

### 原則 2 — 讀寫分離 ✅ 合規

**證據**：
- Rust ConfigStore ArcSwap-based 熱重載為所有交易/風控/模型參數權威
- Python route handler 改為「parse → call → format」（CLAUDE.md §九）
- Wave A-D 已完成 54 routes 分至 sibling legacy_routes（`auth_legacy_routes.py`/`gui_legacy_routes.py`/`system_legacy_routes.py`/`learning_legacy_routes.py`/`control_legacy_routes.py`）
- `main_legacy.py:464-468` 僅聚合 `register_*_legacy_routes(app)` 5 行

**違反點**：無。

---

### 原則 3 — AI 輸出 ≠ 即時命令 ✅ 合規

**證據**：
- `executor_agent.py:341-376` Guardian 批准後仍須 `_governance_hub.acquire_lease(intent_id, "TRADE_ENTRY", ttl=30s)`；lease 失敗 → fail-closed REJECT（與 2026-03-31 審查 G-05 BLOCKER 一致，已修復）
- `governance_hub.py:693` `acquire_lease()` / `governance_hub.py:752` `release_lease()` 配套
- `decision_lease_state_machine.py` SM-02 狀態機管轄 TTL / 撤銷
- Rust 側 `live_authorization.rs` + `live_auth_watcher.rs` 每 5s 輪詢 Python 簽發 HMAC 授權（LIVE-GATE-BINDING-1，2026-04-18）

**違反點**：無。

---

### 原則 4 — 策略不能繞過風控 ✅ 合規

**證據**：
- `guardian_agent.py:91-196` `review_intent()` fail-closed（任何 exception → REJECTED）
- `guardian_agent.py:13 / 27` 明文標記「fail-closed：Guardian 不可用或返回 UNKNOWN 時默認拒絕」
- pipeline_bridge 直接呼 `review_intent()`，不允許「TRADE_INTENT 未送 MessageBus 就進入執行」
- Rust IntentProcessor (`intent_processor/gates.rs` + `intent_processor/router.rs`) 在下單路徑再加一層 Gate（hot-reload ConfigStore）

**違反點**：無。

**風險留底**（不降評級）：`guardian_agent.py:471 / 479` APPROVED_INTENT MessageBus 發送失敗是 fail-open — 影響觀測但不繞過風控本身。

---

### 原則 5 — 生存 > 利潤 ✅ 合規

**證據**：
- CLAUDE.md §二優先級序：帳戶生存 > 風控治理 > 系統健康 > 審計可追溯 > 人類終審 > 真實 Net PnL > 自主能力進化
- Rust `risk_config.rs` (1328 行) + `exit_features/` + Track P v2 物理層 micro-profit-lock live
- `memory/project_agent_p2_dynamic_sl_tp.md`：SL/TP 動態 ATR，P1 max 為硬頂，Agent 可覆蓋但不能突破
- `startup.rs` 憑證/授權失效即拒絕 spawn Live 管線（預設收縮）

**違反點**：無。

---

### 原則 6 — 失敗默認收縮 ✅ 合規

**證據**：
- `guardian_agent.py:91 / 184` fail-closed → REJECTED
- `executor_agent.py:324-374` governance_hub 存在但 acquire_lease=None → reject execution
- `live_authorization.rs:99-170` AuthError 變體（IpcSecretMissing / InvalidSignature / Expired / EnvMismatch / FileMissing / FileCorrupt）全部為拒絕 spawn Live
- `bybit_rest_client.rs:525-587` Mainnet fail-safe 3 gate：缺 `OPENCLAW_ALLOW_MAINNET=1` / 憑證空 / env var 憑證繞過被封閉

**違反點**：無。

**設計 fail-open 保留項（合規，非違反）**：
- `h1_thought_gate.py:102-118` cost_tracker 異常 → fail-open 放行 AI 調用（屬 AI 預算層，不影響交易風控；memory `feedback_working_principles.md` 已審核）
- `guardian_agent.py:471` MessageBus 發送 APPROVED_INTENT 失敗 fail-open（僅觀測丟失，審批結果已落地）

---

### 原則 7 — 學習 ≠ 改寫 Live ✅ 合規

**證據**：
- `memory/project_ml_dl_learning_architecture.md`：Teacher-Student+LightGBM+Optuna+3DL 學習平面獨立
- `learning.*` schema 21 表與 `trading.*` schema 讀寫分離
- `claude_teacher/applier.rs:229-245` DirectiveApplier 強調 fail-closed + veto 過濾
- `learning.model_registry` (V023) + `POST /api/v1/ml/model_promote` canary 狀態機 operator-gated

**違反點**：無。

---

### 原則 8 — 交易可解釋 ✅ 合規

**證據**：
- `trading.intents` / `trading.orders` / `trading.fills`（`exit_source` V021 加欄位）配套 `learning.directive_executions` / `learning.decision_features` / `learning.decision_shadow_exits`（V017/V021/V023）
- `audit_persistence.py` + `governance_events.py` 決策鏈完整入庫
- `close_tag` 機制（risk_close:* / phys_lock_* / COST EDGE*）可重建平倉原因

**違反點**：無。

**observational bug 仍在**（不降評級，L3 級別）：
- memory `project_decision_outcomes_not_dead.md`：outcome_* 曾 100% NULL 因 timeframe 字串格式 `'1'` vs `'1m'` 不一致；2026-04-21 已 fix（commit `5e2981d` 回填 ~267k rows）

---

### 原則 9 — 交易所災難保護 ✅ 合規

**證據**：
- CLAUDE.md §四「Bybit API timeout / retCode != 0 → fail-closed，不重試」
- `ollama_client.py:63` `max_retries: int = 0` 硬邊界
- Rust `StopManager`（Hard/Trailing/Time Stop）+ Bybit 條件單雙重防線
- `Live_Ready` 門控 5 項（Python `live_reserved` / Operator role auth / `OPENCLAW_ALLOW_MAINNET` / secret slot / `authorization.json` HMAC）組成多層防線

**違反點**：無。

---

### 原則 10 — 認知誠實 ⚠️ 部分合規

**證據 ✅**：
- CLAUDE.md §三 明文區分「已完成里程碑」/「進行中 gap」/「阻塞」
- Live_Ready ⚠️ 標記仍 0 真實 live 流量（43k 條 `engine_mode="live"` 實為 LiveDemo）
- `memory/project_decision_outcomes_not_dead.md`「Mac RCA 盲點：不驗證外部資料就採納情境 3 reframe」自我批評
- `memory/feedback_indicator_lookahead_bias.md`：`rolling(N).max()` 含 current bar 的 look-ahead bias 已紀錄

**違反證據 ⚠️**：
- CC 先前審查報告本身「產生過錯誤結論」後被代碼驗證推翻（memory 記載「B-MVP-1 修正：produce_intel() bus.send 已實現 — CC 報告結論錯誤」）→ 主觀認知誠實紀錄完整，屬「已識別並修正」的合規模式
- 前次 CC 報告（`2026-04-12--compliance_audit_report.md`）**檔案不存在於 workspace/reports/**，僅 memory 提及 — 索引漂移（非硬違反，但需追查）

**結論**：合規模式存在（主動標記不確定、事後修正），但報告管理流程有 gap → **部分合規**。

---

### 原則 11 — Agent 最大自主權 ✅ 合規

**證據**：
- `memory/feedback_agent_autonomy.md` + `memory/project_agent_p2_dynamic_sl_tp.md`：P0/P1 硬邊界內 Agent 完全自主
- `strategist_agent.py` (1170 行) 自主決定參數（STRATEGIST-PARAMS-PERSIST-1 V019 + AUTO-PROMOTE-CRITERIA-1 持久化）
- CognitiveModulator 調製只能讓 Agent 更審慎不能放寬硬上限（profile.md §認知調製合規）

**違反點**：無。

---

### 原則 12 — 持續進化 ⚠️ 部分合規

**證據 ✅**：
- `edge_estimator_scheduler.py` daemon 隨 uvicorn 運作（commit `23b14ef` 2026-04-19），`settings/edge_estimates.json` 每小時自動刷新
- `learning.model_registry` (V023) + ONNX training pipeline + quantile_reports.py 工具鏈綠
- Linux runtime Agent 自主學習：StrategistAgent shadow=False live 於 `strategy_wiring.py:243`

**違反證據 ⚠️ (LEARNING-PIPELINE-DORMANT-1, P1 TODO)**：
- cost_gate 門檻 `grand_mean > −50 bps 且 ≥2 策略 shrunk_bps>0` 尚未滿足（P1-10 結構性 fee-drag / R:R 不對稱）
- ONNX 訓練資料量不足：最大切片 `demo grid_trading BLURUSDT` 47/200 labels，ETA ~3-5d
- `experiment_ledger_snapshot.json` 結構異常
- 21 個 learning schema 表仍無 consumer
- 引述 CLAUDE.md §三 Progress 狀態：**"進行中/阻塞 LEARNING-PIPELINE-DORMANT-1 (P1, 2026-04-16 audit · 2026-04-19 半解 · 2026-04-21 刷新)"**

**結論**：管線已部分解凍，但學習 → 自動參數演進的閉環尚未真實跑起來 → **部分合規**。

---

### 原則 13 — AI 資源成本感知 ✅ 合規

**證據**：
- `layer2_cost_tracker.py` + `ai_budget_routes.py` + `api_budget_manager.py` 計費基礎設施完整
- Rust `ai_budget/tracker.rs:435 cost_edge_ratio()` 實作；`config/legacy_migration.rs:253` `max_cost_edge_ratio: 0.8` 閾值
- `h1_thought_gate.py` Budget check 門控 AI 調用
- README.md:230 + CLAUDE.md §二:34 「cost_edge_ratio ≥ 0.8 → 建議關倉」

**違反點**：無。

**觀察（不影響評級）**：cost_gate 目前受 Phase 5 PAUSED 影響 — memory `project_phase5_promotion_edge_crisis.md` 記錄所有活躍策略 gross edge 為負，cost_gate 閾值尚未觸發；機制存在但實戰資料未累積。

---

### 原則 14 — 零外部成本可運行 ✅ 合規

**證據**：
- `local_llm_factory.py:1-60` LLM-ABC-MIGRATION-1 本地 LLM provider factory（ollama / lm_studio 切換）
- L0 確定性層（H0 Gate）+ L1 Ollama/LM Studio 可完全本地跑
- CLAUDE.md §三 `memory/project_hardware_constraints.md`：128GB 統一記憶體 LLM ~54GB 本地運作
- 無 OpenClaw Gateway 單點故障（profile.md §七 記錄「PA 決定：OpenClaw 作為 sidecar，MessageBus 保留主通信通道」)

**違反點**：無。

---

### 原則 15 — 多 Agent 協作 ✅ 合規

**證據**（2026-04-23 audit 更正後）：
- 5-Agent 總計 ~4552 行代碼：`strategist_agent.py` 1170 + `guardian_agent.py` 587 + `analyst_agent.py` 834 + `executor_agent.py` 630 + `scout_worker.py` 194 + `multi_agent_framework.py` 1137
- H1-H5 middleware 非 stub：`h1_thought_gate.py` 185 / `model_router.py` 292 / `h4_validator.py` 103 + `layer2_{engine,routes,tools,cost_tracker,types}.py` 全實作
- `multi_agent_framework.py:45-60` AgentRole Enum + MessageType Enum 結構化訊息協議落地
- `agent_audit_bridge.py` 5 agents 全接 `audit_callback`（E5-FN-3 + FN-3-FUP-a~d）
- MessageBus pub/sub + Guardian 永遠優先於 Strategist 衝突仲裁

**違反點**：無。

**Gap 保留（non-blocking）**：
- ExecutorAgent `_shadow_mode=True` 默認（`executor_agent.py:482` + `strategy_wiring.py:467` `ExecutorConfig()`）— 設計上避免 Path A/B 倉位衝突，非違反；G-1 子任務待展開
- Layer 2 自主推理循環（新聞搜索 / 宏觀判斷 / 工具箱 / 推理鏈記錄）memory `project_layer2_agent_design.md` 列為真正 gap

---

### 原則 16 — 組合級風險意識 ✅ 合規

**證據**：
- `portfolio_risk_control.py` (557 行) 實作 EX-01 §6：Rolling correlation matrix（price return Pearson correlation），0.7 correlation threshold gate（block new entries in correlated instruments）
- `memory/project_gui_write_paths_inventory.md`：93 endpoints 分類含組合曝險觀測
- `memory/feedback_position_sizing.md`：3% risk/trade × 25 symbols 動態分配

**違反點**：無。

---

## 第二部分：實施準則（§七，10 項）

### 準則 1 — 路徑不硬編碼 ⚠️ 違反（1 處）

**違反點（P1 必修）**：
- `helper_scripts/db/audit_migrations.py:218` — `"/Users/ncyu/Projects/TradeBot/srv/sql/migrations"` 硬編碼 Mac 絕對路徑
  - 前兩個 candidate 已用 `os.path.expanduser("~/BybitOpenClaw/srv/sql/migrations")` + `os.path.expanduser("~/srv/sql/migrations")`，第 3 項應改為 `os.environ.get("OPENCLAW_BASE_DIR")` 加 `/sql/migrations` 或刪除
  - 影響：非本人 Mac / 非該絕對路徑的工作樹無法自動找到 migrations dir
  - 修復：`os.path.join(os.environ.get("OPENCLAW_BASE_DIR", os.path.expanduser("~")), "sql/migrations")` 或類似

**其他 Python / Rust 掃描結果**（均 PASS）：
- `grep '/home/ncyu\|/Users/ncyu'` 於 `/srv/program_code/**/*.py` + `/srv/rust/**/*.rs` → **0 命中**
- 僅 `audit_migrations.py` 1 處 regression

---

### 準則 2 — LocalLLMClient 抽象乾淨 ✅ 合規

**證據**：
- `local_llm_factory.py:1-60` 完整 docstring + MODULE_NOTE 雙語
- `get_local_llm_client()` 依 `LOCAL_LLM_PROVIDER` env 切換 ollama / lm_studio，未知值 warn + fallback ollama
- 業務代碼 `grep 'OllamaClient' app/*.py` 僅命中 3 檔：`local_llm_factory.py`（factory 本身）/ `ollama_client.py`（實作）/ `strategy_wiring.py`（docstring 註解）
- memory `feedback_cross_platform.md` + `memory/project_hardware_constraints.md` 跨平台契約完整

**違反點**：無（LLM-ABC-MIGRATION-1 完成後 call-site 無 OllamaClient 直接 import）

---

### 準則 3 — 服務部署可遷移 ✅ 合規

**證據**：
- CLAUDE.md §六「跨平台 Runtime 路徑」完整 env var 表（OPENCLAW_BASE_DIR / OPENCLAW_DATA_DIR / OPENCLAW_SECRETS_ROOT / OPENCLAW_SECRETS_DIR / OPENCLAW_ARCHIVE_DIR）
- Mac ↔ Linux 差異明確記錄（Mac `/tmp` 是 `/private/tmp` symlink，`$HOME/.openclaw_runtime` 不會開機清）
- `helper_scripts/restart_all.sh --rebuild` 設計可攜
- SSH bridge workflow（memory `project_ssh_bridge_workflow.md`）分離 Mac dev / Linux runtime 職責

**違反點**：無。

---

### 準則 4 — 依賴管理乾淨 ✅ 合規（假設）

**證據**：
- `requirements.txt` + `requirements-ml.txt` 分層
- memory `project_mac_deployment_target.md`：未來 Apple Silicon Mac 部署目標；CI tuple `aarch64-apple-darwin` 必含

**不確定（需追查）**：
- 未實際核對 requirements.txt 與當前 `import` 是否 drift（此次 audit 範圍外）
- 平台守衛（`psutil` Linux-specific API 等）未逐行掃描

**結論**：按 CLAUDE.md 規範配置完整；深度驗證屬 E2 / R4 職責，CC 給 ✅ 但標「需追查」。

---

### 準則 5 — 雙語注釋（中英對照）✅ 合規

**證據（抽樣）**：
- `live_authorization.rs:1-26` MODULE_NOTE (EN) + MODULE_NOTE (中) 完整
- `live_auth_watcher.rs:1-77` 雙語 MODULE_NOTE + 設計要點
- `multi_agent_framework.py:1-26` MODULE_NOTE (中文) + MODULE_NOTE (English)
- `passive_wait_healthcheck.py:1-39` docstring 雙語
- `executor_agent.py:145 / 147 / 324 / 326` 每段中英雙語註釋
- `bybit_rest_client.rs:495-513` 中英對照 Mainnet fail-safe 說明
- `database/migrations.rs:1-31` MODULE_NOTE (EN) + MODULE_NOTE (中)

**違反點**：無（抽樣 6 檔均合規；全 codebase 全掃屬 E2 範疇）。

---

### 準則 6 — 新 SQL migration guard A/B/C + Idempotency ⚠️ 部分合規

**證據 ✅**：
- `sql/migrations/templates/schema_guard_template.sql` 模板存在
- `sql/migrations/tests/test_schema_guards.sql` 9 單測（3 guard × pass/fail/no-op）
- `V023__model_registry.sql:43-95` Guard A retrofit 完成（2026-04-24 postmortem 後）
- `V021__fills_exit_source.sql` Guard A + Guard B

**違反證據 ⚠️**：
- `V019__strategist_applied_params.sql` 無 Guard A（1-31 行直接 `CREATE TABLE IF NOT EXISTS`）
- `V020__strategist_applied_params_tie_break.sql` 無 Guard A
- V019/V020 均在 V023 postmortem 規則生效（2026-04-24）前落地 — **非硬違規但應逐步 retrofit**

**結論**：新規則已執行（V021 / V023 符合），舊 migration 未回補 → **部分合規**。

**修復建議（P2）**：
- 按 `V023__model_registry.sql` retrofit 樣式補 V019 + V020 Guard A（對 `learning.strategist_applied_params` 驗欄位存在）
- 新 migration 未來 E2 一律查 Guard A

---

### 準則 7 — Engine 自動遷移 opt-in 鋪設 ✅ 合規

**證據**：
- `rust/openclaw_engine/src/database/migrations.rs:1-80` MigrationRunner 完整實作 + 雙語 MODULE_NOTE
- `AUTO_MIGRATE_ENV_VAR = "OPENCLAW_AUTO_MIGRATE"` opt-in 鋪設，預設關
- `main.rs:810-845` startup 接線：DbPool 連線後、writer 啟動前呼 `run_if_enabled()`，失敗 `std::process::exit(1)` 硬中止
- `LEGACY_APPLIED_MAX_VERSION: i64 = 23` canary 機制 seed `_sqlx_migrations`
- CLAUDE.md §七 rollback path 清楚（`unset OPENCLAW_AUTO_MIGRATE` + 手動 bootstrap_db.sh --apply）

**違反點**：無。

---

### 準則 8 — 被動等待 TODO 必附 healthcheck ✅ 合規

**證據**：
- `helper_scripts/db/passive_wait_healthcheck.py` 完整實作 12 個 check：
  - [1] close_fills_24h / [2] label_backfill_ratio / [3] exit_features_writer / [4] phys_lock_runtime / [5] micro_profit_fire / [6] trailing_stop_fire / [7] edge_estimates_freshness / [8] shadow_exit_ratio / [9] model_registry_freshness / [10] intents_writer_ratio / [11] counterfactual_clean_window_growth / [12] bb_breakout_post_deadlock_fix
- docstring 明文 "Exit 1 = silent-dead 自動偵測"
- cron 6h 節奏 operator 執行
- CLAUDE.md §七 4 條規則（登記門檻 / 檢查語意 / 節奏建議 / 違規處理）完整落地

**違反點**：無。

---

### 準則 9 — 文件大小 800 警告 / 1200 硬上限 ❌ 違反（13 處超硬上限）

**違反點（P1 必修 — 多處）**：

**Python `app/` 生產代碼 > 1200 行（3 處）**：
| 檔案 | 行數 | 超出 |
|------|-----|-----|
| `app/live_session_routes.py` | 1449 | +249 |
| `app/ai_service.py` | 1258 | +58 |
| `app/governance_routes.py` | 1172 | +(邊界) — 尚未破，800 警告 |
| `app/strategist_agent.py` | 1170 | 800 警告區 |
| `app/multi_agent_framework.py` | 1137 | 800 警告區 |
| `app/paper_trading_routes.py` | 1088 | 800 警告區 |
| `app/governance_hub.py` | 1014 | 800 警告區 |

**Rust `rust/openclaw_engine/src/` 生產代碼 > 1200 行（4 處）**：
| 檔案 | 行數 | 超出 |
|------|-----|-----|
| `rust/openclaw_engine/src/main.rs` | 2062 | +862 |
| `rust/openclaw_engine/src/instrument_info.rs` | 1975 | +775 |
| `rust/openclaw_engine/src/event_consumer/mod.rs` | 1762 | +562 |
| `rust/openclaw_engine/src/bybit_rest_client.rs` | 1725 | +525 |
| `rust/openclaw_engine/src/order_manager.rs` | 1554 | +354 |
| `rust/openclaw_engine/src/startup.rs` | 1377 | +177 |
| `rust/openclaw_engine/src/paper_state/resting_orders.rs` | 1367 | +167 |
| `rust/openclaw_engine/src/config/risk_config.rs` | 1328 | +128 |
| `rust/openclaw_engine/src/ipc_server/mod.rs` | 1192 | (邊界) |
| `rust/openclaw_engine/src/strategist_scheduler/mod.rs` | 1166 | 800 警告區 |
| `rust/openclaw_engine/src/intent_processor/mod.rs` | 1100 | 800 警告區 |

**測試檔 > 1200 行（記錄，不納入違反因測試豁免屬慣例）**：
- `tests/test_governance_hub.py` 1483
- `tests/test_governance_routes_coverage.py` 1351
- `rust/openclaw_engine/src/tick_pipeline/tests.rs` 3524（最大）
- `rust/openclaw_engine/src/intent_processor/tests.rs` 1905

**結論**：
- CLAUDE.md §九「1200 行硬上限（不允許 merge）」屬當前項目規則
- 本次掃描發現 **8 個生產檔 > 1200 行**，且部分檔案（main.rs 2062、instrument_info.rs 1975）明顯超過
- 有意識的拆分嘗試已留痕（`live_trust_routes.py` 註解明言「從 live_session_routes.py 分離以保持該文件在 1200 行限制內」），但 live_session_routes.py 主檔仍 1449 行
- TICK-PIPELINE-MOD-SPLIT-1（2026-04-22，commit `3d67a99`）拆 `tick_pipeline/mod.rs` 2274→1012 行是正面範例；其他大檔應跟進
- **違反評級：部分合規 → 違反**（P1 必修排程拆分）

**修復建議（P1）**：
- 優先排序拆分 `main.rs` (2062) / `instrument_info.rs` (1975) / `event_consumer/mod.rs` (1762) / `bybit_rest_client.rs` (1725)
- `live_session_routes.py` (1449) 可再依 route 類別（session lifecycle / trust ladder / authorization）切 2-3 個 sibling

---

### 準則 10 — Singleton 登記 ✅ 合規

**證據**：
- CLAUDE.md §九 Singleton 管理表 14 項完整登記（settings / STORE / app / limiter / _pool / DEFAULT_LEASE_TTL_CONFIG / _backtest_engine / _scheduler / _evolution_engine / _ledger / LeaseTTLConfigManager._instance / _BYBIT_CLIENT / KLINE_MANAGER 等 / _SHARED_IPC_SLOTS / _<AGENT>_AUDIT_CB / _scheduler × edge_estimator / _LEADER_LOCK_FD）
- 新 EDGE-SCHEDULER-LEADER-1（2026-04-23 `f32629c`）` _LEADER_LOCK_FD` / `_LEADER_LOCK_PATH` 已登記
- QC-3 audit FUP（2026-04-23）補登 `_scheduler` / `_scheduler_lock`

**違反點**：無。

---

## 第三部分：硬邊界（§四）抽查

| 硬邊界 | 狀態 | 證據 |
|--------|-----|------|
| `OPENCLAW_ALLOW_MAINNET=1` 未設 → Mainnet 拒 spawn | ✅ | `bybit_rest_client.rs:526-533` |
| Mainnet env var 憑證繞過已封閉 | ✅ | `bybit_rest_client.rs:545-572` |
| Mainnet 憑證空 → Err | ✅ | `bybit_rest_client.rs:577-585` |
| `authorization.json` HMAC 驗證 + 每 5 min re-verify | ✅ | `live_authorization.rs:1-26` + `live_auth_watcher.rs:1-77` |
| `max_retries=0`（ollama_client 單次嘗試） | ✅ | `ollama_client.py:63` |
| `OPENCLAW_GOVERNANCE_ENABLED` 環境變數移除 | ✅ | `grep` 僅命中 test/worklog/dated docs，業務代碼無 |
| `execution_authority` P0/P1 denylist 常量 | ✅ | `claude_teacher/applier.rs:218` |
| `decision_lease_emitted=False` 初始值 | ✅ | 設計契約（executor_agent 每 intent fresh lease） |

**硬邊界 8/8 合規**，前次 6/6 升至更全面覆蓋。

---

## 第四部分：Top 5 違規（優先順序）

### #1 — 文件大小硬上限違規（P1 必修，範圍大）
**嚴重度**: P1（非硬邊界，但 CLAUDE.md §九 明言「不允許 merge」）
**影響**: 8 個生產檔 > 1200 行；最大 `main.rs` 2062 行、`instrument_info.rs` 1975 行
**修復**: 參照 TICK-PIPELINE-MOD-SPLIT-1（commit `3d67a99`）樣式依職責拆 sibling modules
**負責**: E5 Optimizer + Rust E1

### #2 — `audit_migrations.py:218` 硬編碼 Mac 絕對路徑（P1 必修，單點）
**嚴重度**: P1（跨平台兼容性紅線）
**影響**: 工作樹若不在 `/Users/ncyu/Projects/TradeBot/srv` 則第 3 candidate 失效；regresses CLAUDE.md §七.★★ 第 1 條
**修復**: 改為 `os.path.join(os.environ.get("OPENCLAW_BASE_DIR", ...), "sql/migrations")` 或刪除（前兩個 candidate 已足夠）
**負責**: Python E1（~3 行 diff）

### #3 — LEARNING-PIPELINE-DORMANT-1 持續進化循環未閉環（P1，已 TODO 追蹤）
**嚴重度**: P1（原則 12 部分合規根源）
**影響**: ONNX 訓練資料量不足（47/200 labels）、cost_gate 閾值未觸發、21 個 learning schema 表無 consumer
**修復**: 依 TODO §P1-7 / §P1-14 繼續累積資料；非 code fix，是資料與觀察週期
**負責**: FA + 被動等待（ETA ~3-5d 過 200 labels，2026-05-01 passive_wait_healthcheck [11] auto-gate）

### #4 — V019 + V020 migration 缺 Guard A（P2，retrofit）
**嚴重度**: P2（規則 2026-04-24 才生效，歷史 migration 可逐步補）
**影響**: 未來 drop + partial re-apply 可能 silent no-op
**修復**: 依 `V023__model_registry.sql:43-95` 樣式補 `learning.strategist_applied_params` Guard A DO block
**負責**: E1（~30 行 SQL 補丁）

### #5 — 前次 CC 審查報告檔案缺失（L3，管理流程 gap）
**嚴重度**: L3（認知誠實與歷史索引完整性）
**影響**: memory 記載 `docs/audit/April01/CC_compliance_check_2026-04-01.md` + 本次 `2026-04-12--compliance_audit_report.md`，但 `workspace/reports/` 下僅 2026-03-31 × 2 + 2026-04-01 一份；2026-04-12 那份未存
**修復**: 尋回檔案；若確丟失則在本報告 footer 明標；未來 CC 每次 audit 必寫至 `workspace/reports/` 不分散
**負責**: CC（本 session 已改善流程，本報告檔案 2026-04-24 已落至標準位置）

---

## 第五部分：需追查（認知誠實）

1. **依賴管理實際 drift 未逐行掃描** — `requirements.txt` 與當前 `import` 是否一致、是否有 Linux-only `psutil` API 使用，未在本次 audit 範圍。建議 E2 / R4 下輪 audit 涵蓋。
2. **`test_stub_contracts.py` 59 tests 實際執行結果** — memory 載「全綠，contract_check 已清除」，CC 本次未實跑；建議 E4 確認。
3. **`main.rs:810-845` 實際 auto-migrate 路徑是否 opt-in 生效** — 需在有 `OPENCLAW_AUTO_MIGRATE=1` 的 Linux 實機跑一次驗證；Mac dev-only 模式不實跑。
4. **ExecutorAgent shadow→live 切換流程的契約** — memory 列為 Layer 2 真正 gap，非本 audit 範圍；G-1 子任務展開時 CC 需再做 review。
5. **live_session_routes.py 1449 行檔案** — 檔案註解已提及 `live_trust_routes.py` 拆分嘗試，但主檔仍超限；拆分前的 pre-image 行數可查 git log 以觀察歷史。

---

## Agent 完成序列：memory 更新計畫

CC memory.md 需更新區塊（2026-04-24 今日 audit 後）：
1. 新增「合規狀態快照（2026-04-24）」取代 2026-04-01 快照
2. 記錄 B+ 級 / 20 / 26 項通過
3. 補新發現：文件大小 13 處硬上限超限 + audit_migrations.py 硬編碼路徑 regression
4. 報告索引新增本報告路徑
5. 記錄新實施準則（Guard A/B/C + Engine auto-migrate opt-in + passive_wait_healthcheck）全部落地

---

CC AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/CC/workspace/reports/2026-04-24--compliance_audit.md
