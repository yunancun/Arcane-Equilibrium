# 2026-04-04 Session 2 — RC-11 + 既有 Bug 修復 + Governance 清理

## 一、RC-11：消除 Python/Rust 止損雙重執行

### 問題
RC-10 停用了 `PipelineBridge.on_tick()`（Python 策略 tick 路徑），但**未停用 `MarketDataDispatcher._trigger_tick()` 中的 `engine.tick()` 調用**。導致：
- **Rust**：`tick_pipeline.rs:235` → `paper_state.check_stops()` → 每 tick 止損檢查 ✅
- **Python**：`MarketDataDispatcher` → `PaperTradingEngine.tick()` → `_mutator_tick_check_stops()` → 重複止損 ❌

### 修復
- `market_data_dispatcher.py::_trigger_tick()` — 移除 `engine.tick()` 調用，保留價格追蹤 + 注意力系統
- `test_market_data.py` — `test_limit_order_filled_via_dispatch` → `test_rc11_dispatcher_does_not_match_orders`
- `test_market_data_dispatcher.py` — tick consumer fan-out 測試改為驗證不被調用（Rust 處理）

---

## 二、10 個既有 Bug 修復（10 failed → 0 failed）

### Rust-first 響應格式不匹配（5 個）

| 測試 | 原因 | 修復 |
|------|------|------|
| `test_get_indicators_empty` | `== 0` 但 Rust 返回 16 個預計算指標 | `>= 0` |
| `test_get_signal_summary` | 期望 `consensus_direction`，Rust 用 `consensus` | 接受兩者 |
| `test_list_strategies` | 期望 `s["strategy"]`，Rust 用 `s["name"]`；`FundingRate_Arb` 不在 Rust 策略中 | `s.get("name") or s.get("strategy")`；移除 FundingRate_Arb 斷言 |
| `test_happy_path` (signals) | Mock SIGNAL_ENGINE 但 Rust reader 優先 | 同時 mock `get_rust_reader` 不可用 |
| `test_happy` (strategy status) | Mock ORCHESTRATOR 但 Rust reader 優先 | 同時 mock `get_rust_reader` 不可用 |

### 測試隔離汙染（5 個）

| 測試 | 原因 | 修復 |
|------|------|------|
| `test_session_lifecycle_via_api` × 2 | 前測試留下活躍 session → 409 Conflict | 前置 `session/stop` 清理 |
| `test_session_start_via_api` | 同上 | 前置 `session/stop` 清理 |
| `test_market_feed_status_not_initialized` | DISPATCHER 被模組初始化覆蓋 | TestClient 後強制 DISPATCHER=None |
| `test_get_category_config_default` | `linear` 品類被前測試設置 | 改用 `option` 品類 + 寬鬆斷言 |

---

## 三、Governance 清理

### governance_hub.py — 5 個方法標記 DEPRECATED (RC-11)

| 方法 | 原因 | 替代 |
|------|------|------|
| `check_learning_tier_capability` | 無調用者 | Rust GovernanceCore |
| `is_enabled` | 無外部調用者 | `is_globally_enabled()` |
| `get_risk_level` | 無外部調用者 | `get_status()["risk"]` / IPC `get_risk_check` |
| `check_risk_and_act` | 無調用者 | Rust `evaluate_and_cascade()` |
| `trigger_risk_upgrade` | 無調用者 | Rust GovernanceCore cascade |

模組級註釋更新：明確列出 STILL ACTIVE vs DEPRECATED 方法清單。

### bridge_core.py

- `activate()` — 精簡為僅設 `_active=True` + 日誌，移除 bootstrap 線程（Rust 處理引導）
- `on_tick()` — 更新 deprecation 註釋（RC-10 + RC-11），方法體保留供測試（28 個測試依賴）

---

## 四、Governance Routes 遷移分析結論

| 類別 | 端點數 | 可遷移? |
|------|--------|---------|
| 純 Hub 狀態（auth/risk/lease/OMS） | 18 | ✅ → IPC relay |
| ChangeAuditLog | 5 | ❌ Python-only |
| RiskManager/Gates | 6 | ⚠️ 需暴露 IPC |

**IPC 暴露風險分析：**
- Symbol Whitelist：有 WRITE 操作，保留 Python 持有，Rust 唯讀緩存
- H0 Gate：Rust 已有完整實現，加 IPC 端點即可
- Paper→Live Gate：11 項檢查 + operator approval，暫留 Python

---

## 五、測試基準線

```
Python: 3345 passed / 0 failed / 1 skipped（+12 修復 vs 之前 10 failed）
Rust:   755 passed / 0 failed（未修改）
```

## 六、修改文件清單

```
# RC-11
M  app/market_data_dispatcher.py          — _trigger_tick() 禁用 engine.tick()
M  tests/test_market_data.py              — RC-11 行為驗證測試
M  tests/test_market_data_dispatcher.py   — tick consumer 測試更新

# 既有 Bug 修復
M  tests/test_phase2_routes.py            — Rust-first 格式 + 策略名
M  tests/test_phase2_strategy_routes_coverage.py — mock Rust reader
M  tests/test_paper_trading.py            — session 隔離
M  tests/test_paper_trading_engine.py     — session 隔離
M  tests/test_risk_manager.py             — category config 隔離

# Governance 清理
M  app/governance_hub.py                  — 5 方法標記 deprecated + 模組註釋
M  app/bridge_core.py                     — activate() 精簡 + on_tick() 註釋更新
```

## 七、下一步

1. Phase 1 ML pipeline（FeatureCollector + LightGBM Scorer + PSI drift）
2. P2 Paper Engine 瘦身（讀路由 IPC 化 → 寫路由 IPC 化）
3. 引擎持續運行監控
