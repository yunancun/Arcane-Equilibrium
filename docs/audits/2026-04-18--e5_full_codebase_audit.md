# E5 全盤優化審核報告（2026-04-18）

**審核範圍**：OpenClaw 整個活躍 codebase（Rust engine 78k 行 + Python control_api 54k 行 + 其他 crate 19k 行 ≈ 15 萬行活躍代碼）
**審核方法**：9 個 Explore sub-agent 並行審核無重疊分片，由主會話 PM+Conductor 匯總
**審核目的**：不是「能跑起來」的驗證，而是找「模塊化合理、引用合理、無大段重複、設計漂亮」層次的優化空間

---

## 一、分派結構

| 分片 | 職責 | 核心文件 | 行數 |
|---|---|---|---|
| R1 | 策略 + 編排層 | `strategies/` + `orchestrator` + `fast_track` + `edge_estimates` + `dynamic_risk_sizer` | 10,046 |
| R2 | Tick Pipeline + Intent + Event Consumer | `tick_pipeline/` + `intent_processor/` + `event_consumer/` | ~8,800 |
| R3 | IPC + Config + Startup + Live Auth | `ipc_server/` + `config/` + `startup.rs` + `main.rs` + `live_authorization.rs` + `tasks.rs` | ~7,900 |
| R4 | 市場數據 + WS/REST + Scanner + News | `ws_client` + `bybit_rest_client` + `bybit_private_ws` + `market_data_client/` + `scanner/` + `news/` | ~7,500 |
| R5 | 狀態 + 持久化 + 資料庫 | `paper_state` + `position_*` + `order_manager` + `account_manager` + `database/` | 12,103 |
| R6 | Risk + AI + ML | `risk_checks` + `ai_budget/` + `claude_teacher/` + `edge_predictor/` + `linucb/` + `ml/` | ~6,800 |
| P1 | Python Routes | 所有 `*_routes.py` + `legacy_routes.py` | 13,181 |
| P2 | Python State Machines + Wiring | `ipc_client` + 4 state machines + `governance_hub*` + gates + wiring | 12,753 |
| P3 | Python Agents + Layer2 | 5 Agent + `ai_service` + `layer2_*` + `learning_*` | ~13,700 |

---

## 二、總體結論

**系統架構地基健康**，不屬於「堆起來能跑」的類型。多個模塊達到「設計漂亮」標準（見 §六乾淨模塊清單）。

**真正的債務集中在兩類**：
1. **大量樣板在 N 處重複**（跨策略的冷卻/持倉追蹤、WS 重連、HMAC 簽名、JSON-RPC handler、DB writer 批量插入、state machine transition、Agent 初始化）
2. **少數超肥檔承載多職責**（`paper_state.rs` 2380 · `tick_pipeline/mod.rs` 1786 · `event_consumer/handlers.rs` 1722 · `main.rs` 1515 · `bybit_rest_client.rs` 1538 · `live_session_routes.py` 1229 · `legacy_routes.py` 1179 · `governance_hub.py` 1052）

這些不是 bug，是維護成本問題，與 operator 訴求（追求「寫得漂亮」）吻合。

---

## 三、Master P0 — 最高 ROI（立即做，低風險）

| # | 主題 | 去重行數 | 涉及分片 | 建議新模塊 |
|---|---|---|---|---|
| **P0-1** | **3 個 Python state machine 共性抽取** | ~350 | P2 | `state_machine_base.py` |
| **P0-2** | **策略層樣板去重**（冷卻/持倉/confidence） | ~400 | R1 | `strategies/common/per_symbol_state.rs` + `confidence_builder.rs` + `trend_cooldown.rs` |
| **P0-3** | **WS + HMAC 簽名基建** | ~100 | R4 | `common/ws_backoff.rs` + `common/bybit_signer.rs` |
| **P0-4** | **database writer 批量插入統一** | ~150 | R5 | `database/batch_insert.rs` |
| **P0-5** | **legacy_routes.py 拆 5 檔** | 1179 → 5×~200 | P1 | `auth_/gui_/system_/learning_/control_legacy_routes.py` |

共同特徵：**去重 + 抽一個定義**，對行為零改動，原 test 不動即可回歸；每一項都關掉一條「未來誰動都要同步多處」的持續痛點。5 項互不干擾，可並行派 E1。

---

## 四、Master P1 — 結構改善（可排期）

| # | 主題 | 來源 | 備註 |
|---|---|---|---|
| **P1-1** | `paper_state.rs` 2380 行拆 5 子模塊（accessor / owner_attribution / fill_engine / snapshots / 容器） | R5 | 全專案最大單檔；要分階段 PR |
| **P1-2** | `main.rs` 1515 行 → `app/bootstrap.rs` | R3 | 初始化集中，main 降至 ~400 行 |
| **P1-3** | `event_consumer/handlers.rs` 1722 行按 domain 拆 | R2 | ai_budget / risk / paper / system / strategy |
| **P1-4** | Python `BaseAgent` + `llm_call_wrapper.py` | P3 | 5 Agent 初始化/LLM 調用統一 |
| **P1-5** | JSON-RPC handler 樣板 + `ipc_error_handler.py` + `tasks/supervised_spawn.rs` | R3/R6/P1 | 跨層樣板基建 |
| **P1-6** | `gate_pipeline.py` — h0_gate + paper_live_gate 共用 | P2 | 利於 G-1 H1-H5 新增 gates |

**P1-2（main.rs 重構）不建議現在做** — 初始化路徑是 P0-9 停電 RCA 後唯一沒被重組的模塊，觀察其穩定性比急著重構重要。

---

## 五、Master P2 — 小收益（順手做）

- `PipelineCommand` enum 31 variants → 按 domain 分組（R2）
- `ml/onnx_inference.rs` 抽取 + input/output 名稱 cache（R6）
- ✅ **`market_data_client` 移除 5 個未使用 REST endpoint**（R4，**本次已執行**，見 §八）
- `multi_interval_ws.rs` → 更名 `multi_interval_topics.rs`（R4）
- 策略層 magic number（`default_qty = 1e9` 等）接線到 config（R1）
- `governance_hub.py` 5 個 deprecated method 標記 `@deprecated`（P2）

---

## 六、乾淨的模塊（確認保留不動，避免誤傷）

### Rust
`orchestrator.rs` · `fast_track.rs` · `dynamic_risk_sizer.rs` · `confluence.rs` · `grid_helpers.rs` · **`risk_checks.rs`（★ 特別漂亮，726 行優先級鏈清晰，95 測試）** · `live_authorization.rs` · `persistence.rs` · `account_manager.rs` · `mode_state.rs` · `canary_writer.rs` · `ws_client.rs`（主體）· `scanner/scorer.rs` · `scanner/registry.rs` · `feature_collector.rs`

### Python
`earned_trust_engine.py` · `paper_live_gate.py` · `state_compiler.py` · `layer2_cost_tracker.py` · `change_audit_log.py` · `market_regime.py` · `learning_tier_gate.py` · `phase2_strategy_routes.py` · `attribution_routes.py` · `evolution_routes.py`

---

## 七、審核順帶發現的 3 個**非純優化**問題（功能面潛在缺陷）

這 3 項不在「E5 優化」範疇，但被 sub-agent 掃出，值得 operator 評估是否開 ticket：

### 7.1 live_authorization 啟動同步驗證缺失（R3 P1）
- **現況**：`main.rs` 5 min ticker re-verify，但 Live pipeline **spawn 時無同步驗證**
- **窗口風險**：憑證失效後最多 5 分鐘內 pipeline 仍在跑
- **建議**：`startup.rs` 新增 `verify_live_authorization_or_fail()`，spawn 前同步驗一次
- **影響面**：與 LIVE-GATE-BINDING-1 的「閉合旁通漏洞」設計意圖一致性相關

### 7.2 ai_budget `record_usage()` 無 request_id 去重（R6 P2）
- **現況**：5 個 scope 共享一條寫入路徑，`learning.ai_usage_log` 無 `UNIQUE(request_id)` constraint
- **風險**：consumer_loop 重試或 DB 分段失敗 → **同一次 AI 調用計帳兩次** → USD 超支未警告
- **建議**：DB 層加 UNIQUE + consumer 統一 request_id 生成格式（如 `{ts_ms}_{scope}_{model_hash}`）

### 7.3 5 Agent 決策點未貫通 `change_audit_log`（P3 P1）
- **現況**：`change_audit_log.py` 模塊完整，但只有 learning pipeline 在寫
- **風險**：Strategist/Analyst/Executor/Guardian 決策無審計軌跡 → 違反根原則 #8「交易可解釋」
- **建議**：`agent_audit_bridge.py` + 每個 `_handle_*` 補 audit callback

---

## 八、本次已執行的優化

### 8.1 market_data_client 刪除 5 個死 REST endpoint（Master P2）
**執行日期**：2026-04-18
**動機**：這 5 個 method 在整個 Rust+Python workspace grep 後**無任何 caller**（僅在定義檔 `mod.rs` 自身出現），且其支撐 types 亦無外部引用

**刪除清單**：

| Method | 原 endpoint | 備註 |
|---|---|---|
| `get_mark_price_klines` | `/v5/market/mark-price-kline` | funding arb 備用，未接線 |
| `get_premium_index_klines` | `/v5/market/premium-index-price-kline` | 資金費率預測備用，未接線 |
| `get_adl_alert` | `/v5/market/adl-alert` | Bybit V5 此端點可能不存在（FIX-58 註記），已用 Private WS position topic 取代 |
| `get_delivery_price` | `/v5/market/delivery-price` | 交割分析備用，未接線 |
| `get_index_price_klines` | `/v5/market/index-price-kline` | 基差分析備用，未接線 |

**關聯刪除**：
- `types::AdlAlert` struct（僅此一處使用）
- `types::DeliveryPrice` struct（僅此一處使用）
- `tests::test_delivery_price_serde` + `tests::test_parse_delivery_price_list`（測試對應已刪 type）
- `mod.rs` re-export list 同步調整

**驗證**：
- `cargo build --lib` 乾淨通過（5 個 pre-existing warnings，非本次引入）
- `cargo test --lib market_data_client` 16/16 passed
- `cargo test --lib`（全量）1452 passed / 0 failed

**效果**：
- `mod.rs` 747 → 532 行（-215）
- `types.rs` 225 → 194 行（-31）
- `tests.rs` 341 → 290 行（-51）
- 總刪 **297 行 dead code**

**可恢復性**：若未來任何策略需要這些 endpoint，從 git history 還原即可（`git show HEAD^:.../market_data_client/mod.rs`）。

---

## 九、通用模塊藍圖（完整去重後）

### Rust
```
rust/openclaw_engine/src/
├── common/                              ← 新
│   ├── ws_backoff.rs                   # P0-3 · R4
│   ├── bybit_signer.rs                 # P0-3 · R4
│   ├── retry_policy.rs                 # 順手 · R4
│   └── bybit_error.rs (可選)           # P2 · R4
├── strategies/
│   └── common/                          ← 新
│       ├── per_symbol_state.rs         # P0-2 · R1
│       ├── confidence_builder.rs       # P0-2 · R1
│       └── trend_cooldown.rs           # P0-2 · R1
├── tick_pipeline/
│   ├── command_dispatch.rs             # P1 · R2
│   └── fill_context_builder.rs         # P2 · R2
├── intent_processor/
│   └── rejection_coding.rs             # P1 · R2
├── ipc_server/
│   ├── param_extractor.rs              # P1 · R3
│   └── handlers/ (按 domain 拆分)       # P1 · R2/R3
├── tasks/
│   └── supervised_spawn.rs             # P1 · R3
├── app/
│   └── bootstrap.rs                    # P1-2（延後）· R3
├── database/
│   └── batch_insert.rs                 # P0-4 · R5
├── position_owner_attribution.rs       # P1-1 · R5
├── position_fill_engine.rs             # P1-1 · R5
├── position_snapshots.rs               # P1-1 · R5
├── dust_gate.rs                        # P1 · R5
├── claude_teacher/
│   └── directive_handler.rs            # P2 · R6
└── ml/
    └── onnx_inference.rs               # P2 · R6
```

### Python
```
control_api_v1/app/
├── state_machine_base.py               # P0-1 · P2
├── auth_routes_common.py               # P0/P1 · P1
├── ipc_error_handler.py                # P1 · P1
├── ipc_dispatch.py                     # P1 · P2
├── gate_pipeline.py                    # P1-6 · P2
├── governance_hub_event_handlers.py    # P1 · P2
├── base_agent.py                       # P1-4 · P3
├── llm_call_wrapper.py                 # P1-4 · P3
├── learning_batch_writer.py            # P2 · P3
├── agent_audit_bridge.py               # §7.3 · P3
├── auth_legacy_routes.py               # P0-5 · P1
├── gui_legacy_routes.py                # P0-5 · P1
├── system_legacy_routes.py             # P0-5 · P1
├── learning_legacy_routes.py           # P0-5 · P1
└── control_legacy_routes.py            # P0-5 · P1
```

---

## 十、建議執行順序

**本週內**（如 operator 批准啟動）：
批次 P0-1 ~ P0-5 並行派 E1，每個獨立 commit，E2 背靠背審。5 項互不干擾。

**本週之後**：
P1-1（paper_state 拆分）優先 — 這是「每次改一點就越欠越多」的複利型債務。其他 P1 按 operator 排序。

**不建議現在做**：
P1-2（main.rs bootstrap 拆分）— Live 真實流量跑穩再動，觀察 P0-9 RCA 後初始化路徑穩定性比重構優先。

---

## 十一、Stub vs Dead Code 特別判定（G-1 AI Agent 未展開前）

**必須保留的骨架 stub**（W22+ R-06 激活）：
- `ai_service.py::_conductor` stub fallback
- `guardian_agent.py` EventAlert 消費邏輯（Ollama fallback 完整）
- `layer2_engine.py` L1/L2 agent loop 全部

**可明確標記 DORMANT（但不刪除）**：
- `ai_service.py:462-525` AnalystAgent stub fallback（source 已標示 "ai_service_stub"）
- `ml/kelly_sizer.rs` → 歸入既有 LEARNING-PIPELINE-DORMANT-1 項目追蹤

**可明確刪除**：
- ✅ market_data_client 5 個 REST endpoint（§八，已執行）

---

## 附錄：9 份分片原始報告摘要

每份報告完整內容保留在本次 session 的 agent transcript，核心發現摘要已並入 §三/§四/§五。若需原始細節可從 `/tmp/claude-1000/-home-ncyu-BybitOpenClaw-srv/7c05d736-4788-46a8-b62d-30efc56dda85/tasks/` 讀取對應 agent 的 output 檔案（9 個 task-id 對應 R1/R2/R3/R4/R5/R6/P1/P2/P3）。
