# Session Progress — ARCH-RC1 1C-3-F SHIPPED

**Date**: 2026-04-08 深夜
**Commits**: `accf625` (F-a) · `8ff93e0` (F-b) · `de1ec69` (F-c/d/e)
**Net**: -8915 / +16

## 完成項

### F-a — Rust submit_paper_order IPC RPC（`accf625`）
- `tick_pipeline.rs`: `PaperSessionCommand::SubmitOrder` variant + `submit_external_order()` 方法（~150 行），走 IntentProcessor 全 gate（governance/Guardian/Kelly/P1/cost gate），instrument-aware 取整，apply_fill，stats 累計，trading_tx 廣播。Order ID `ext-{symbol}-{ts_ms}`。
- `event_consumer/handlers.rs`: SubmitOrder 分支（side 字串解析、confidence 默認 1.0、snapshot.force_write 成功時）
- `ipc_server.rs`: `submit_paper_order` JSON-RPC dispatch + 5s timeout
- `event_consumer/tests.rs`: 4 e2e tests (happy / paused / no_price / invalid_side) + 將 1C-3-D 4 個 guard tests 統一改用 `authorize()` helper
- engine lib: 748 → **752**

### F-b — shadow_decision_builder rewire（`8ff93e0`）
- `ipc_client.py`: `submit_paper_order` async wrapper
- `shadow_decision_builder.py`: 砍 `from .paper_trading_engine import (...)`，常量內聯（`ORDER_TYPE_MARKET` / `SIDE_BUY` / `SIDE_SELL` / `SESSION_ACTIVE`），`ShadowDecisionConsumer.__init__` 改吃 `EngineIPCClient`，`consume()` 改 async（await get_paper_state + await submit_paper_order）。刪 `_engine.store.mutate(...)` 影子審計 append。
- `layer2_engine.py:669`: `await self._shadow_consumer.consume(...)`
- `layer2_routes.py`: 移除 `from .paper_trading_routes import ENGINE as PAPER_ENGINE, SHADOW_CONSUMER`，加 `_build_shadow_consumer()` helper

### F-c/d/e — Python 紙盤引擎徹底刪除（`de1ec69`）
- `app/paper_trading_engine.py` 2248 行 ❌
- `paper_trading_routes.py`: 內聯 `DEFAULT_INITIAL_BALANCE_USDT = 10_000.0`
- `paper_trading_wiring.py`: 刪 `PaperStateStore`/`PaperTradingEngine` import；`PAPER_STORE = None`；`ENGINE = None` 維持原狀
- 13 個 paper-engine-specific test 文件刪除：
  - `test_paper_trading.py` / `test_paper_trading_engine_edge.py`
  - `test_shadow_decision.py` / `test_shadow_decision_builder.py`
  - `test_batch10_learning_oms.py` / `test_batch12_e2e_smoke.py`
  - `test_winrate_param_fixes.py`
  - `test_integration_phase{7,9,11}.py` / `test_integration_governance.py`
  - `local_model_tools/tests/test_session9_fixes.py`
- conftest.py PAPER TRADING ENGINE FIXTURES 整塊刪除（4 fixtures）
- pytest 回歸：**2944 → 2694 passed / 22 → 21 fail / 0 regression**
  - -250 = 13 個被刪測試檔的 250 個 case
  - -1 fail = 其中一個原本在 22 baseline fail 內

## 關鍵決策

1. **scope 擴張**：handoff 文檔列 14 個 test，實際 grep 後是 13（一個重複），但發現 conftest.py 有 4 個 paper engine fixtures 需整塊刪。額外 7 個疑似 test（test_batch11_executor_exchange / test_edge_filter_integration / test_u05 / test_executor_agent_unit / test_grafana_data_writer / test_evolution_engine / test_pipeline_bridge*）審計後**確認只有 mock 註釋無真實 import**，無需動。
2. **PAPER_STORE / ENGINE 留 None stub**：3 個生產消費者（main.py / governance_routes.py / strategy_wiring.py）全部已 `if ENGINE is not None` 短路，留 stub 而非物理刪除可避免不必要的 import-site 改動。
3. **local_model_tools/ 4 個生產文件**（cost_gate / backtest_engine / evolution_engine / strategy_auto_deployer）全部只有 docstring/註釋級引用，**零真實 import**，無需動。

## 留尾移交 1C-4

- Position Reconciler（trading.open_positions + Bybit 對帳 + cooldown 重建）
- **Governor cooldown PG 持久化**（1C-3-B-2 known limitation；live 前必做）
- NewsPipeline `run_once` 60s scheduler spawn
- 熱重載 e2e 驗收測試
- E-Merge-4（可選）Guardian config 退化為 RiskConfig sub-view
- **註釋級殘留 sed 清理**：main.py / tab-governance.html / strategy_wiring.py / pipeline_bridge.py / executor_agent.py 等仍有 "RC-10 ENGINE removed — Python PaperTradingEngine disabled" 字樣，現在不再準確（不是 "disabled"，是 "deleted"）
- E2 + E4 + QA Audit

## 測試基準線（更新）

- engine lib **752** (+4 vs F-a 前)
- core 387 · types 27 · ml_training 35
- Python control_api **2694 passed / 21 pre-existing fail / 0 regression**
- Live 前唯一 blocker：**7d paper trading 數據觀察期**

## 下一步起點

打開 `TODO.md`，第一個 `[ ]` 在 1C-4 區塊（Position Reconciler 或 Governor cooldown PG 持久化）。本 session 的所有 1C-3-F sub-batches 全部 `[x]` 完成。
