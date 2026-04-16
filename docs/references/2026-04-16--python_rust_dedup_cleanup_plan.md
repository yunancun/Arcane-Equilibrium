# Python–Rust 重複代碼清理計劃

**日期**：2026-04-16（路徑與事實修正版；原稿路徑/importer 數誤差已校正）
**狀態**：計劃級（Tier A stub 替換法，尚未動工）
**預估效益**：Python 有效計算代碼 ~8,136 → ~2,100 行（淨減 ~6,000+）

---

## 第一部分：初始評估 vs 實際情況

### ❌ 初始評估錯誤的 3 個模組（不能砍）

| 模組 | 實際路徑 | 行數 | 實際情況 |
|------|---------|------|---------|
| `h0_gate.py` | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/h0_gate.py` | 971 | Python 進程獨立的 H0 確定性門控。~8 個外部消費者（main.py / strategy_wiring / governance_routes / governance_extended_routes / risk_routes / paper_trading_wiring / risk_view_client / shared_types）。Rust `h0_gate.rs` 運行在 engine 進程，兩者同演算法不同上下文，缺一不可。 |
| `hurst_exponent.py` | `program_code/local_model_tools/hurst_exponent.py` | 164 | 被 `market_regime.py` 間接依賴鏈使用；與 `ewma_vol_estimator` 同屬 Python 端獨立計算鏈。 |
| `ewma_vol_estimator.py` | `program_code/local_model_tools/ewma_vol_estimator.py` | 159 | 同上。 |

**關於 `market_regime.py`**（實際路徑 `control_api_v1/app/market_regime.py`）：
- 實測 importer ~7 個（原稿誤寫 35+）：`paper_trading_metrics.py` / `layer2_engine.py` / `shadow_decision_builder.py` / `ai_agents/bybit_thought_gate/{prompt_prep_builder,prompt_prep_tighten,response_check,governed_decision}.py`
- Rust 對應 `rust/openclaw_core/src/risk/regime.rs` 僅 59 行靜態乘數查找表，不等價
- 結論：**不能砍**，但「核心計算」敘事應降級為「AI 治理與 paper 指標層依賴」。

### ✅ 確認可清理的模組（Tier A）

以下模組形成一個**緊密耦合的計算集群**，全部被 Rust engine 的對應模組替代，
目前在 Python 端僅作為「Rust 離線時的降級備援」（`strategy_read_routes.py` 明確標注
`"Rust-first — Python 僅作降級備援"`）。

| # | Python 模組 | 行數 | Rust 對應（根目錄 `rust/`）| 外部消費者（control_api_v1/app/） |
|---|------------|------|-----------|-------------------------------|
| 1 | `indicators/` (7 files) | 1,606 | `rust/openclaw_core/src/indicators/{trend,momentum,volatility,volume}.rs` | 無直接外部消費者，全經 indicator_engine.py |
| 2 | `indicator_engine.py` | 472 | Rust tick_pipeline 統一計算 | `strategy_read_routes.py`(fallback), `strategy_wiring.py`(singleton) |
| 3 | `signal_generator.py` | 1,174 | `rust/openclaw_core/src/signals/{mod,rules}.rs` | `strategy_read_routes.py`(fallback), `strategy_wiring.py`(singleton) |
| 4 | `signal_engine.py` | 315 | 同上 | `strategy_read_routes.py`(fallback) |
| 5 | `kline_manager.py` | 1,055 | `rust/openclaw_engine/src/market_data_client/` | `strategy_read_routes.py`(fallback), `strategy_wiring.py`(singleton), `grafana_data_writer.py`(legacy param) |
| 6 | `market_scanner.py` | 340 | `rust/openclaw_engine/src/scanner/` | `scout_worker.py`, `strategy_wiring.py` |
| 7 | `position_sizer.py` | 315 | `rust/openclaw_engine/src/position_manager.rs` + `risk_checks.rs` | 僅 `strategy_auto_deployer.py` |
| 8 | `strategy_orchestrator.py` | 564 | `rust/openclaw_engine/src/orchestrator.rs` + `strategies/` | `strategy_wiring.py`(singleton) |
| 9 | `strategy_auto_deployer.py` | 1,164 | Rust scanner + strategy lifecycle | `evolution_routes.py`, `strategy_read_routes.py`, `strategy_wiring.py`, `strategy_write_routes.py` |
| 10 | `backtest_engine.py` + `backtest_types.py` | 1,142 + 239 = 1,381 | `rust/openclaw_core/src/backtest.rs`（~490 lines） | `backtest_routes.py`(直接用), `evolution_auto_scheduler.py`, `strategy_wiring.py`, `evolution_engine.py`, tests |
| 11 | `strategies/base.py` + `__init__.py` | ~120 | `rust/openclaw_engine/src/strategies/` | 僅 `strategy_orchestrator.py` + `test_phase2_routes.py` |

**Tier A 合計：~8,506 行可清理**

---

## 第二部分：為什麼不能直接刪除

### 問題：strategy_wiring.py 的 singleton 鏈

```
strategy_wiring.py (FastAPI 啟動時執行)
  ├── KLINE_MANAGER = KlineManager(...)        ← line 90
  ├── INDICATOR_ENGINE = IndicatorEngine(...)   ← line 91
  ├── SIGNAL_ENGINE = SignalEngine()            ← line 92
  ├── ORCHESTRATOR = StrategyOrchestrator(...)  ← line 98
  ├── MARKET_SCANNER = MarketScanner(...)       ← line 446 (lazy)
  └── AUTO_DEPLOYER = StrategyAutoDeployer(...) ← line 447 (lazy)
```

這些 singleton 被 `__all__` 導出，被 `strategy_read_routes.py` 引用作為 fallback，
被 `evolution_routes.py`、`scout_worker.py`、`backtest_routes.py` 引用。

**直接刪除文件 → `ImportError` → 整個 FastAPI 進程啟動失敗。**

### 問題：strategy_read_routes.py 的 Rust-first + Python-fallback 模式

```python
# 每個端點的模式（以 get_klines 為例，line 49-66）：
async def get_klines(...):
    reader = get_rust_reader()           # 1. 嘗試 Rust
    if reader:
        rust_klines = reader.get_klines(sym, n=n)
        if rust_klines:
            return {"source": "rust_engine", ...}
    # 2. Fallback 到 Python
    klines = KLINE_MANAGER.get_latest_klines(sym, timeframe, n=n)
    return {"source": "python_fallback", ...}
```

`strategy_read_routes.py` 至少 8 處 `"source": "rust_engine"` 分支對應 Python fallback。
Python fallback 對象不存在 → Rust 離線時端點 500。

---

## 第三部分：安全執行策略 — Stub 替換法

### 核心思路

**不刪除文件，替換為 thin stub。** 每個 stub：
- 保留原始 class name 和 method signature
- 方法體返回空數據 / no-op
- 加入明確的 deprecation warning log
- 所有 import 保持有效，系統正常啟動

### 執行順序（由內到外，每步可獨立驗證）

#### Step 1：indicators/ → stub（最內層，零外部依賴風險）

替換 7 個指標文件為 stub，保留 `base.py` 的 interface：

```python
# indicators/rsi.py (stub)
"""STUB: RSI computation moved to Rust openclaw_core::indicators::momentum.
    Python fallback disabled — returns empty dict."""
import logging
logger = logging.getLogger(__name__)

class RSIIndicator:
    def __init__(self, **kwargs): pass
    def compute(self, *args, **kwargs):
        logger.debug("RSI stub: computation in Rust engine")
        return {}
```

**驗證**：`pytest program_code/local_model_tools/tests/test_indicators.py` 會失敗
（預期中，因為 stub 返回空值），但 `import` 不會失敗。

#### Step 2：indicator_engine.py → stub

```python
class IndicatorEngine:
    def __init__(self, kline_manager=None, **kw): pass
    def register_on_update(self, cb): pass
    def get_indicators(self, symbol, timeframe=None):
        return {}  # Rust engine is primary source
    def on_kline_close(self, *args, **kw): pass
```

**驗證**：`strategy_wiring.py:91` `IndicatorEngine(kline_manager=...)` 正常實例化。
`strategy_read_routes.py` fallback 路徑返回空 dict → 前端顯示 "data unavailable"。

#### Step 3：signal_generator.py + signal_engine.py → stub

```python
# signal_generator.py stub
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class Signal:
    symbol: str = ""
    strategy: str = ""
    direction: str = ""
    strength: float = 0.0
    timeframe: str = ""
    timestamp_ms: int = 0
    metadata: dict = None
    def __post_init__(self):
        self.metadata = self.metadata or {}

class SignalEngine:
    def __init__(self, **kw): pass
    def on_indicators_update(self, *args, **kw): pass
    def get_latest_signals(self, symbol=None, n=10):
        return []  # Rust engine is primary source
```

**注意**：`Signal` dataclass 可能被其他模組 import 用於類型標注。
必須保留 `Signal` 的完整欄位定義。

**驗證**：`strategy_wiring.py:92+95` 正常。

#### Step 4：kline_manager.py → stub

```python
class KlineBar:
    """Minimal stub for type compatibility."""
    ...

class KlineManager:
    def __init__(self, symbols=None, timeframes=None, **kw): pass
    def get_latest_klines(self, symbol, timeframe, n=100): return []
    def get_current_bar(self, symbol, timeframe): return None
    def register_on_kline_close(self, callback): pass
```

**注意**：`KlineBar` 可能被 `backtest_engine.py` 和其他模組 import。
須保留 `KlineBar` 的欄位定義。

#### Step 5：market_scanner.py → stub

```python
class MarketScanner:
    def __init__(self, **kw): pass
    def start(self): pass
    def stop(self): pass
    def register_on_scan(self, cb): pass
    def get_scan_results(self): return []
```

**驗證**：`scout_worker.py` 中 `MARKET_SCANNER.register_on_scan(...)` 正常。

#### Step 6：position_sizer.py → stub

```python
class PositionSizer:
    def __init__(self, **kw): pass
    def compute(self, *args, **kw): return {"qty": 0.0, "reason": "stub"}
```

#### Step 7：strategy_orchestrator.py → stub

```python
class StrategyOrchestrator:
    def __init__(self, kline_manager=None, indicator_engine=None,
                 signal_engine=None, **kw): pass
    def set_ai_engine(self, engine): pass
    def get_active_strategies(self): return []
    def get_strategy_performance(self, name=None): return {}
```

#### Step 8：strategy_auto_deployer.py → stub

最複雜的 stub，因為被 4 個 route 文件引用。

```python
class StrategyAutoDeployer:
    def __init__(self, orchestrator=None, kline_manager=None, **kw): pass
    def on_scan_results(self, results): pass
    def set_backtest_engine(self, engine, min_sharpe=0.0): pass
    def get_deployed_strategies(self): return []
    def get_deployment_history(self): return []
```

#### Step 9：backtest_engine.py + backtest_types.py → stub

**新增消費者**：`backtest_routes.py:56` 直接 `from local_model_tools.backtest_engine import BacktestEngine, BacktestConfig`。stub 必須保留 `BacktestEngine` 類名和 `BacktestConfig` / `BacktestResult` 的 dataclass 定義。

保留 dataclass 定義（其他模組 import 用），計算方法返回空結果：

```python
# backtest_types.py — KEEP full dataclass definitions (BacktestConfig / BacktestResult / ...)
# backtest_engine.py — stub the engine class
class BacktestEngine:
    def __init__(self, **kw): pass
    def run(self, config) -> BacktestResult:
        return BacktestResult(...)  # empty/zero result
```

#### Step 10：strategies/ → stub

```python
# strategies/base.py
class StrategyBase: ...
class OrderIntent: ...
STRATEGY_ACTIVE = "active"
```

---

## 第四部分：驗證清單

每完成一個 Step，執行以下驗證：

### 1. Import 驗證（必須全過）
```bash
cd ~/BybitOpenClaw/srv
python -c "from program_code.local_model_tools.indicators import rsi, bollinger_bands, macd, atr, stochastic, moving_averages, extended"
python -c "from program_code.local_model_tools.indicator_engine import IndicatorEngine"
python -c "from program_code.local_model_tools.signal_generator import SignalEngine, Signal"
python -c "from program_code.local_model_tools.kline_manager import KlineManager"
python -c "from program_code.local_model_tools.market_scanner import MarketScanner"
python -c "from program_code.local_model_tools.position_sizer import PositionSizer"
python -c "from program_code.local_model_tools.strategy_orchestrator import StrategyOrchestrator"
python -c "from program_code.local_model_tools.strategy_auto_deployer import StrategyAutoDeployer"
python -c "from program_code.local_model_tools.backtest_engine import BacktestEngine, BacktestConfig, BacktestResult"
```

### 2. Wiring 驗證（FastAPI 能啟動）
```bash
cd ~/BybitOpenClaw/srv
python -c "
import sys; sys.path.insert(0, '.')
from program_code.exchange_connectors.bybit_connector.control_api_v1.app.strategy_wiring import (
    KLINE_MANAGER, INDICATOR_ENGINE, SIGNAL_ENGINE, ORCHESTRATOR
)
print('All singletons created OK')
print(f'  KlineManager: {type(KLINE_MANAGER).__name__}')
print(f'  IndicatorEngine: {type(INDICATOR_ENGINE).__name__}')
print(f'  SignalEngine: {type(SIGNAL_ENGINE).__name__}')
print(f'  Orchestrator: {type(ORCHESTRATOR).__name__}')
"
```

### 3. Route 驗證（Fallback 路徑不 crash）
```bash
# 啟動 FastAPI 後測試
curl -s http://localhost:8000/api/v1/strategy/klines/BTCUSDT | jq .source
# 預期: "rust_engine"（Rust 在線時）或空 response（Rust 離線，不應 500）
```

### 4. 現有測試（預期部分失敗）
```bash
pytest program_code/local_model_tools/tests/ -v --tb=short 2>&1 | tail -20
# 預期：test_indicators, test_signal_generator 等會失敗（stub 返回空值）
# 這些測試本身也應標記為 skip/deprecated
```

---

## 第五部分：不動的模組（確認保留清單）

| 模組 | 實際路徑 | 行數 | 保留原因 |
|------|---------|------|---------|
| `h0_gate.py` | `control_api_v1/app/h0_gate.py` | 971 | FastAPI 進程獨立的 H0 確定性門控，~8 個 app 檔案消費者 |
| `market_regime.py` | `control_api_v1/app/market_regime.py` | ~706 | ~7 importers（paper_trading_metrics / layer2_engine / shadow_decision_builder / bybit_thought_gate × 4）；Rust `risk/regime.rs` 僅 59 行查找表，不等價 |
| `hurst_exponent.py` | `local_model_tools/hurst_exponent.py` | 164 | market_regime 內部依賴鏈 |
| `ewma_vol_estimator.py` | `local_model_tools/ewma_vol_estimator.py` | 159 | market_regime 內部依賴鏈 |
| `hurst_hysteresis.py` | `control_api_v1/app/hurst_hysteresis.py` | ~200 | 被 `market_regime.py:54` import |
| `cognitive_modulator.py` | `local_model_tools/cognitive_modulator.py` | 193 | strategist_agent 依賴，無 Rust 對應 |
| `evolution_engine.py` | `local_model_tools/evolution_engine.py` | 567 | 參數優化引擎；依賴 BacktestEngine（見下方警告）|
| `local_llm_client.py` | `local_model_tools/local_llm_client.py` | 251 | Ollama 客戶端，無 Rust 對應 |

### ⚠️ evolution_engine.py 的特殊處理

`evolution_engine.py` import `BacktestEngine`。Stub 化 backtest_engine 後，
evolution_engine 的 `_evaluate()` 方法會收到空結果。需要：
- 在 evolution_engine.py 中加入「engine offline」判斷
- 或延遲 backtest stub 化（Step 9），先只做 Step 1-7

---

## 第六部分：預期效果

| 指標 | 清理前 | 清理後 |
|------|--------|--------|
| local_model_tools/ 有效代碼行數 | 8,136 | ~2,500 (stubs ~600 + 保留模組 ~1,900) |
| indicators/ 有效代碼行數 | 1,606 | ~100 (stubs) |
| 可刪除測試代碼 | ~5,000+ | 0 (測試標記 skip) |
| Import 破壞 | — | 0 |
| 運行時 crash | — | 0 |

淨減少有效計算代碼：**~6,000+ 行**（從 8,136 降到 ~2,100）

附帶可清理：
- 對應的 `test_*.py` 文件標記 `@pytest.mark.skip("Python compute replaced by Rust engine")`
- `contract_check` 文件中涉及這些模組的可以直接刪除

---

## 建議執行節奏

**Phase 1（首階段）**：Step 1-3（indicators + indicator_engine + signals）— 最安全，最少外部依賴
**Phase 2（Phase 1 穩定後）**：Step 4-6（kline_manager + market_scanner + position_sizer）
**Phase 3（最後）**：Step 7-10（orchestrator + auto_deployer + backtest + strategies）— 涉及最多外部消費者

每個 Phase 之間：在 trade-core 上跑完整個 import 驗證 + FastAPI 啟動測試。

---

## 修正紀錄（vs 原稿 2026-04-15）

| 修正項 | 原稿 | 修正後 |
|--------|------|--------|
| `h0_gate.py` 路徑 | `program_code/local_model_tools/h0_gate.py` | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/h0_gate.py` |
| `market_regime.py` 路徑 | `program_code/local_model_tools/market_regime.py` | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/market_regime.py` |
| `market_regime.py` importer 數 | 35+ | ~7（實測） |
| Rust indicators 路徑 | `program_code/rust_engine/openclaw_core/src/indicators/` | `rust/openclaw_core/src/indicators/` |
| Rust engine 路徑 | `program_code/rust_engine/openclaw_engine/src/...` | `rust/openclaw_engine/src/...` |
| Step 9 消費者 | 未列 `backtest_routes.py` | 明確列出 `backtest_routes.py:56` 直接 import |
| backtest_engine 行數 | 1,381（混合計數） | 拆分 1,142（engine）+ 239（types） |
