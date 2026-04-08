---
date: 2026-04-08
type: session-handoff
scope: ARCH-RC1 1C-3-E F-mini → 1C-3-F 接手指引
---

# 1C-3-E F-mini 收尾 + 1C-3-F 接手指引

## 本 session 完成

緊接 4/8 PM 1C-3-D session 之後的同日延續。全部 1C-3-E "easy wins" 收掉，為下個 session 的 1C-3-F (徹底退場 Python paper engine) 鋪路。

### 完成項
1. **`d8fb7f2` step 1**: `bridge_core.py:294` 死引用清除（`_engine.risk_manager._price_tracker`）
2. **step 2 自動**: 6 個 1C-3-C skipped TestRiskRoutes 隨 1C-3-D `test_risk_manager.py` 整檔 cull 一起消失
3. **F-mini 三小修**（待 commit · 0 regression）：
   - `paper_trading_routes.py` -4 dead imports
   - `risk_routes.py::unhalt_session` -deprecated PAPER_STORE.mutate block
   - `paper_trading_wiring.py::_h0_db_probe` PAPER_STORE.read() → os.stat()

### 測試
- Python control_api: **2944 passed / 22 fail / 1 skip** (與 baseline byte-for-byte 一致)
- Rust 未動，engine lib 748 持續綠燈

## Rust engine readiness audit（B-full 前置）

跑了 13 capability 完整審計（Explore agent），結論：**Rust 引擎已足夠 paper / demo / live 三模式**。詳細在 CLAUDE_CHANGELOG.md 1C-3-E F-mini session 條目。

關鍵發現：
- `get_paper_state` IPC RPC **已存在** (`ipc_server.rs:422-428`)
- `recent_intents` / `recent_fills` 在 `tick_pipeline.rs:230-233` 已是 ring buffer (max 50)，已包在 `PipelineSnapshot` 內 → 通過 snapshot file 已可讀
- **缺**：paper-side `submit_order` IPC RPC（shadow_decision_builder.py 重接需要）

## 1C-3-F 接手指引（下個 session · ~5h · 需 fresh context）

### 為何拆 session
今天 context 已過半，1C-3-F 涉及：
- Rust 新增 IPC RPC + cargo test 迭代
- Python 重接 shadow_decision_builder.py
- 刪 14 個測試檔 + 2248 行主檔
- 大量 grep / read / edit + 全量 pytest 回歸

硬塞容易半成品。fresh context 從容做 ~5h 一氣呵成更穩。

### F 五子批

**F-a · Rust 補 paper-side submit_order IPC RPC**（~1.5-2h）
1. `rust/openclaw_engine/src/tick_pipeline.rs` PaperSessionCommand enum 加 variant：
   ```rust
   SubmitOrder {
       symbol: String,
       side: String,         // "Buy" / "Sell"
       qty: f64,
       order_type: String,   // "Market" / "Limit"
       price: Option<f64>,
       leverage: f64,
       strategy: String,     // for tagging
       response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,  // returns order_id JSON
   }
   ```
2. `rust/openclaw_engine/src/event_consumer/handlers.rs` 加 handler arm — 走現有 intent_processor 路徑（grep `process_intent`），返回 order_id
3. `rust/openclaw_engine/src/ipc_server.rs` 加 dispatch entry：
   ```rust
   "submit_paper_order" => handle_submit_paper_order(id, params, paper_cmd_tx).await,
   ```
   template: `handle_risk_runtime_status` lines 1015-1040
4. `rust/openclaw_engine/src/event_consumer/tests.rs` 加 2-3 個 e2e tests via `handle_paper_command` + oneshot
5. `cargo test --workspace --exclude openclaw_pyo3` → 750+ 綠

**F-b · shadow_decision_builder.py 改 IPC**（~30min）
- 移除 `PaperTradingEngine` import
- `ShadowDecisionConsumer.__init__` 改接 `EngineIPCClient` 而非 `engine`
- `consume()` 內部呼叫 `client.submit_paper_order(...)` 取代 `engine.submit_order(...)`
- `_engine.get_state()` 改用 `client.get_paper_state()` 已有 RPC
- `_engine.store.mutate(...)` 那行（append shadow_decision 到 audit）：要嘛改 IPC append（需新 RPC），要嘛改寫到獨立 audit log file —— 簡單起見建議後者
- layer2_engine.py 注入點 `shadow_consumer` 不變，只是 wiring 時建構參數從 ENGINE 換成 IPC_CLIENT

**F-c · 刪 paper_trading_engine.py + 14 測試**（~1h）
14 個目標測試檔（皆建構 PaperTradingEngine）：
- `test_shadow_decision.py`
- `test_shadow_decision_builder.py`
- `test_winrate_param_fixes.py`（注意：仍消費 `REGIME_TIME_MULTIPLIERS` from risk_manager.py，這不影響）
- `test_batch10_learning_oms.py`
- `test_batch12_e2e_smoke.py`
- `test_paper_trading_engine_edge.py`
- `test_paper_trading.py`
- `test_integration_phase2.py`（部分，仍有 `test_portfolio_risk_control_present` 不依賴 engine — 留下）
- `test_integration_phase7.py`
- `test_integration_phase9.py`
- `test_integration_phase11.py`
- `test_integration_governance.py`
- `local_model_tools/tests/test_session9_fixes.py`
- conftest.py 第 87/97 行 PaperStateStore/PaperTradingEngine fixtures

刪除策略 = 1C-3-D approach A aggressive cull：邏輯已 100% 在 Rust 748+ tests 覆蓋，Python 測試純為已死 PaperTradingEngine 建構，0 production value。

`bridge_stats.py` + `test_winrate_param_fixes.py` 仍 consume `REGIME_TIME_MULTIPLIERS`（從 risk_manager.py 53 行 shim 內），這不影響 paper_trading_engine 刪除。

**F-d · paper_trading_wiring.py 清理**（~30min）
- 移除 `PaperStateStore` / `PaperTradingEngine` import
- 移除 `PAPER_STORE = PaperStateStore(...)` (line 44)
- 移除 `ENGINE = None` 模組級宣告 + 所有相關註解 (line 62-72)
- 移除 `SHADOW_CONSUMER: ShadowDecisionConsumer | None = None`（如已被 F-b wiring 取代）
- 清理 `__all__` 中的 PAPER_STORE / ENGINE / SHADOW_CONSUMER
- paper_trading_routes.py 同步移除 `PAPER_STORE` / `ENGINE` 從 wiring re-export 的 import

**F-e · E4 + 文檔同步 + commit**（~1h）
- `cargo test --workspace --exclude openclaw_pyo3` → 750+ 綠
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ -q` → 預期 ~2700-2900 passed (取決於刪了多少測試) / 22 pre-existing fail
- 22 failures 須再次 baseline 對照驗證（git stash）
- CLAUDE.md §三 + §十一 / TODO.md / CLAUDE_CHANGELOG.md / daily_summary 同步
- commit 拆分建議：F-a / F-b+c+d / F-e 文檔 三個 commit

## 已知陷阱

1. **Layer 2 wire-ready 但未啟動**：MEMORY 標註「待儀表板+成本追蹤完成後啟動」。F-b 必須保留 Layer 2 invocation path 完整，只換 ShadowDecisionConsumer 內部從 engine call 改 IPC call。
2. **`risk_manager.py` 53 行 shim 不動**：1C-3-D 已落地，仍 export `REGIME_TIME_MULTIPLIERS` 供 bridge_stats / test_winrate_param_fixes 消費。F 不動它。
3. **22 pre-existing failures**：19× grafana_data_writer mock 環境 + test_session_start_via_api 401 + test_is_stale_initially。每次回歸都要 byte-for-byte 對照。
4. **Rust IPC dispatch async**：read-side 用 `handle_snapshot_field` 同步即可；write-side（submit_order）必須 async + oneshot 等回應。模板看 `handle_risk_runtime_status`。

## 1C-3 完成全景

```
1A 前:      Python RiskManager 1633 + 6 套 Rust 並行 = 7 套
1A:         刪 3 套確認死碼
1C-1:       1 Rust Config 權威 + Python RiskManager 1633（待空殼化）
1C-2-F:     1 Config 權威 + 5 engines 同步熱重載
1C-3-D:     1 Rust ConfigStore 權威 + 53 行 Python RiskViewClient shim
1C-3-E F-mini: 邊角死代碼清除（bridge_core / routes imports / PAPER_STORE.mutate / H0 probe）
1C-3-F:     【下個 session】Python paper_trading_engine.py (2248) 徹底退場
            → Rust 引擎成為 paper / demo / live 三模式唯一引擎
```

完成 F 之後，1C-3 全部收尾，可開 1C-4：Reconciler + News + e2e + Governor cooldown PG 持久化 + E2/E4/QA。
