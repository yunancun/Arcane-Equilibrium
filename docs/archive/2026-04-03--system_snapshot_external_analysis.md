# OpenClaw / Bybit AI Agent 交易系統 — 系統現狀快照
# 生成日期：2026-04-03
# 用途：供外部 Claude session 分析系統架構與改進方向

---

## 1. 項目結構樹

```
srv/
├── CLAUDE.md                      ← 項目指令文件（核心規則）
├── README.md                      ← GitHub 入口
├── TODO.md                        ← 當前工作計劃
├── SYSTEM_SNAPSHOT.md             ← 本文件
├── database_files/
│   ├── postgres_data/             ← PostgreSQL 數據（Grafana 指標）
│   ├── redis_data/                ← Redis（目前未使用）
│   └── vector_database_data/      ← Qdrant（未啟用）
├── docker_projects/
│   ├── monitoring_services/       ← Grafana + dashboards + docker-compose.yml
│   └── trading_services/          ← PostgreSQL + runtime artifacts
│       ├── connector_logs/        ← 系統快照 JSON
│       ├── decision_packets/      ← 決策封包 JSON
│       ├── runtime/               ← 運行時狀態
│       └── verdicts/              ← 觀察判定 JSON
├── docs/
│   ├── CCAgentWorkSpace/          ← 16 Agent 工作空間（A3/AI-E/CC/E1-E5/FA/PA/PM/QA/QC/R4/TW）
│   ├── decisions/                 ← 22 份治理規格文件（DOC-01~08, EX-01~07, SM-01~04）
│   ├── governance_dev/            ← Phase 0-12 開發記錄 + audits/
│   ├── references/                ← 外部改善報告
│   ├── worklogs/                  ← 工作日誌
│   ├── CLAUDE_CHANGELOG.md        ← 變更歷史
│   └── CLAUDE_REFERENCE.md        ← 技術參考索引
├── helper_scripts/
│   ├── start_paper_trading.sh     ← 一鍵啟動
│   ├── cron_observer_cycle.sh     ← Observer 自動化
│   ├── cron_daily_report.sh       ← 日報 → Telegram
│   └── maintenance_scripts/       ← 清理/修復腳本
└── program_code/
    ├── ai_agents/
    │   └── bybit_thought_gate/    ← H1-H5 AI 治理層（60+ contract check 文件）
    ├── exchange_connectors/
    │   └── bybit_connector/
    │       └── control_api_v1/    ← ★ 主要代碼目錄
    │           ├── app/           ← FastAPI 應用（50+ 模組，~50,000 行）
    │           ├── tests/         ← 99 個測試文件，3,704 tests
    │           ├── scripts/       ← 運行時快照生成
    │           ├── requirements.txt
    │           └── requirements.lock
    ├── governance/                ← Phase 2 治理狀態機源碼
    ├── local_model_tools/         ← 策略工具包
    │   ├── indicator_engine.py    ← 7 指標協調
    │   ├── signal_generator.py    ← 8 信號規則
    │   ├── kline_manager.py       ← K線聚合
    │   ├── stop_manager.py        ← Hard/Trailing/Time Stop
    │   ├── strategy_orchestrator.py ← 策略編排
    │   ├── strategies/            ← 5 策略實現
    │   └── tests/                 ← 14 測試文件
    ├── risk_control/              ← H0 本地判斷
    └── trade_executor/            ← I 決策租約
```

### app/ 目錄核心模組清單（50+ .py 文件）

| 類別 | 文件 |
|------|------|
| **入口** | main.py, main_legacy.py |
| **交易引擎** | paper_trading_engine.py, paper_trading_routes.py, paper_trading_metrics.py |
| **管線** | pipeline_bridge.py, market_data_dispatcher.py, bybit_public_ws_listener.py |
| **風控** | risk_manager.py, risk_routes.py, h0_gate.py, portfolio_risk_control.py |
| **治理** | governance_hub.py, governance_routes.py, governance_events.py |
| **狀態機** | authorization_state_machine.py, decision_lease_state_machine.py, risk_governor_state_machine.py, oms_state_machine.py |
| **Agent** | multi_agent_framework.py, strategist_agent.py, guardian_agent.py, analyst_agent.py, executor_agent.py, scout_worker.py, scout_routes.py |
| **AI** | ollama_client.py, model_router.py, h1_thought_gate.py, h4_validator.py, layer2_engine.py, layer2_cost_tracker.py, layer2_routes.py, layer2_tools.py, layer2_types.py |
| **學習/進化** | learning_tier_gate.py, learning_auto_pipeline.py, learning_ops.py, learning_queries.py, learning_records.py, experiment_ledger.py, experiment_routes.py, evolution_auto_scheduler.py, evolution_routes.py, truth_source_registry.py |
| **策略路由** | phase2_strategy_routes.py, backtest_routes.py |
| **外部連接** | bybit_demo_connector.py, bybit_demo_sync.py, telegram_alerter.py, grafana_data_writer.py |
| **輔助** | state_compiler.py, state_store.py, state_models.py, state_helpers.py, auth.py, control_ops.py, pnl_ops.py, shadow_decision_builder.py, trade_attribution.py, symbol_category_registry.py, scanner_rate_limiter.py |
| **審計/恢復** | audit_persistence.py, change_audit_log.py, reconciliation_engine.py, recovery_approval_gate.py, ttl_enforcer.py, incident_event_model.py, perception_data_plane.py, data_source_enforcer.py, protective_order_manager.py, paper_live_gate.py |

---

## 2. 核心模組簽名

### 2.1 PipelineBridge — 管線橋接器（核心編排器）

**路徑**: `app/pipeline_bridge.py`

**Import 內部模組**:
```python
from .risk_manager import REGIME_TIME_MULTIPLIERS
from .utils.time_utils import now_ms
from .multi_agent_framework import DataQualityLevel, SentimentScore
```

**被以下模組 import**: `phase2_strategy_routes.py`（創建實例），多個測試文件

```python
class PipelineBridge:
    def __init__(self, kline_manager, indicator_engine, signal_engine, orchestrator,
                 paper_engine, stop_manager=None, *, auto_submit_intents=True, max_intents_per_tick=20)

    # 依賴注入（setter injection pattern）
    def set_telegram(self, alerter) -> None
    def set_observation_writer(self, fn) -> None
    def set_auto_deployer(self, deployer) -> None
    def set_demo_connector(self, connector) -> None
    def set_governance_hub(self, hub) -> None
    def set_perception_plane(self, plane) -> None
    def set_scanner_rate_limiter(self, limiter) -> None
    def set_trade_attribution(self, attribution_engine) -> None
    def set_scout_agent(self, agent) -> None
    def set_message_bus(self, bus) -> None
    def set_learning_tier_gate(self, gate) -> None
    def set_strategist_agent(self, agent) -> None
    def set_guardian_agent(self, agent) -> None
    def set_ollama_client(self, client) -> None
    def set_analyst_agent(self, agent) -> None
    def set_executor_agent(self, agent) -> None
    def set_h0_gate(self, gate) -> None
    def set_symbol_registry(self, registry) -> None

    def register_symbol_category(self, symbol: str, category: str) -> None
    def activate(self) -> None
    def deactivate(self) -> None
    def on_tick(self, event) -> None  # ★ 核心入口：每個 tick 觸發
    @property
    def is_active(self) -> bool
```

**on_tick 內部分為 4 步**:
1. `_tick_update_market_data()` — KlineManager + IndicatorEngine + PerceptionPlane + H0Gate
2. `_tick_run_strategies()` — Orchestrator.dispatch_tick → _process_pending_intents
3. `_tick_check_risk()` — StopManager 止損檢查
4. `_tick_update_stats()` — Scout 掃描 + Analyst L2 cron + Auto-deployer

### 2.2 RiskManager — 風控管理器

**路徑**: `app/risk_manager.py`

**Import**: `portfolio_risk_control.py`, `utils.time_utils`
**被 import**: `pipeline_bridge.py`, `conftest.py`, 多個測試

```python
# 模組級常量
ALL_CATEGORIES: list[str]
AI_TAX_RATES: dict[str, float]
REGIME_STOP_MULTIPLIERS: dict[str, float]
REGIME_TP_MULTIPLIERS: dict[str, float]
REGIME_TIME_MULTIPLIERS: dict[str, float]

# 模組級函數
def cost_efficiency_grade(ratio: float) -> str
def compute_dynamic_stop_pct(base_stop_pct, atr_pct, symbol, entry_ts_ms, regime="unknown", hard_stop_pct=5.0) -> float
def compute_round_trip_cost_pct(volume_24h=0.0) -> float

@dataclass
class GlobalRiskConfig:
    max_stop_loss_pct: float = 5.0
    max_take_profit_pct: float = 20.0
    tp_enabled: bool = False
    # ...更多字段

class PriceHistoryTracker:
    def __init__(self, window_sec=ATR_WINDOW_SECONDS)
    def record(self, symbol: str, price: float) -> None
    def bootstrap_from_klines(self, symbol: str, klines: list) -> int
    def get_prices(self, symbol: str) -> list[tuple[float, float]]
    def compute_atr_pct(self, symbol: str) -> float | None
    def detect_spike(self, symbol: str, current_price: float) -> dict | None
```

### 2.3 GuardianAgent — 風控守衛

**路徑**: `app/guardian_agent.py`

**Import**: `multi_agent_framework` (AgentMessage, AgentRole, MessageBus, TradeIntent, RiskVerdict, etc.)
**被 import**: `phase2_strategy_routes.py`

```python
@dataclass
class GuardianConfig:
    max_leverage: float = 5.0
    max_drawdown_pct: float = 15.0
    max_correlation: float = 0.85
    max_same_direction_positions: int = 3
    # ...

class GuardianAgent:
    def __init__(self, *, config=None, message_bus=None, risk_manager=None,
                 ollama_client=None, governance_hub=None, audit_callback=None)
    def start(self) -> None
    def pause(self) -> None
    def stop(self) -> None
    def on_message(self, message: AgentMessage) -> None
    def review_intent(self, intent: TradeIntent) -> RiskVerdict  # ★ 核心：審查交易意圖
```

### 2.4 StrategistAgent — 策略師

**路徑**: `app/strategist_agent.py`

**Import**: `h1_thought_gate`, `h4_validator`, `model_router`, `multi_agent_framework`, `strategist_models`
**被 import**: `phase2_strategy_routes.py`

```python
class StrategistAgent:
    _REGIME_STRATEGY_PREFERENCES: Dict[str, Dict[str, float]]  # regime → strategy → weight

    def __init__(self, *, config=None, message_bus=None, ollama_client=None,
                 audit_callback=None, cost_tracker=None)
    def start(self) -> None
    def pause(self) -> None
    def stop(self) -> None
    def on_message(self, message: AgentMessage) -> None
```

### 2.5 MessageBus + ScoutAgent + Conductor — 多 Agent 框架

**路徑**: `app/multi_agent_framework.py`

**Import**: 僅 stdlib（logging, threading, time, uuid, dataclasses, enum）
**被 import**: `pipeline_bridge.py`, `scout_routes.py`, `guardian_agent.py`, `strategist_agent.py`, `analyst_agent.py`, `executor_agent.py`

```python
class AgentRole(str, Enum):
    SCOUT, STRATEGIST, GUARDIAN, ANALYST, EXECUTOR, CONDUCTOR

class MessageType(str, Enum):
    INTEL_OBJECT, EVENT_ALERT, TRADE_INTENT, RISK_VERDICT, APPROVED_INTENT,
    EXECUTION_REPORT, ROUND_TRIP_COMPLETE, PATTERN_INSIGHT, RISK_PATTERN,
    STRATEGY_PROPOSAL, SYSTEM_DIRECTIVE

class DataQualityLevel(str, Enum):
    FACT, INFERENCE, HYPOTHESIS

class AgentState(str, Enum):
    INITIALIZING, RUNNING, DEGRADED, PAUSED, STOPPED

@dataclass
class AgentMessage:    # sender, receiver, message_type, timestamp_ms, priority, payload
class IntelObject:     # intel_id, source, data_quality, sentiment, relevance_score, content, symbols
class EventAlert:      # alert_id, event_type, severity, affected_symbols, lead_time_hours
class TradeIntent:     # intent_id, symbol, strategy, direction, size, confidence, thesis
class RiskVerdict:     # verdict_id, intent_id, result(APPROVED/REJECTED/MODIFIED), risk_score

class MessageBus:
    def __init__(self, *, audit_callback=None)
    def validate_route(self, sender, receiver, msg_type) -> bool
    def send(self, message: AgentMessage) -> bool
    def subscribe(self, role: AgentRole, callback: Callable) -> None
    def get_messages(self, *, receiver=None, msg_type=None, since_ms=0) -> list[AgentMessage]
    @property
    def total_messages(self) -> int

class ScoutAgent:
    def __init__(self, config=None, message_bus=None)
    def start(self) -> None / pause() / stop()
    def produce_intel(self, source, content, symbols, *, data_quality, sentiment, ...) -> IntelObject
    def produce_event_alert(self, event_type, severity, affected_symbols, ...) -> EventAlert
    def record_scan(self) -> None
    def get_recent_intel(self, limit=20) -> list[IntelObject]
    def get_stats(self) -> dict

def arbitrate_conflict(scenario, strategist_action=None, guardian_action=None) -> ArbitrationResult
```

### 2.6 PaperTradingEngine — 紙面交易引擎

**路徑**: `app/paper_trading_engine.py`

**Import**: `protective_order_manager`, `utils.time_utils`
**被 import**: `market_data_dispatcher.py`, `risk_manager.py`, 多個路由和測試

```python
# 狀態常量
ORDER_STATE_CREATED / SUBMITTED / WORKING / PARTIALLY_FILLED / FILLED / CANCELED / REJECTED
SESSION_ACTIVE / PAUSED / COMPLETED / INACTIVE
OMS_SM03_ENABLED: bool  # 是否啟用 OMS 11 態映射

# 模組級函數
def compute_dynamic_slippage(volume_24h: float) -> float
def create_paper_order(symbol, side, order_type, qty, price=None, leverage=1.0, ...) -> dict
def compute_fill_price(order, market_price, slippage_rate) -> float
def compute_fee(fill_qty, fill_price, is_taker=True, ...) -> float
def execute_fill(order, fill_qty, fill_price, fee) -> dict  # 返回 fill record

class PaperStateStore:
    def __init__(self, file_path: str)
    def read(self) -> dict
    def write(self, state: dict, force=False) -> dict
    def flush(self) -> None
    def mutate(self, mutator: Callable) -> dict  # ★ 核心：原子讀→改→寫
```

**Order 生命週期（7 態）**: created → submitted → working → partially_filled → filled/canceled/rejected
**OMS SM-03 映射（11 態）**: CREATED → PENDING → APPROVED → SUBMITTED → WORKING → FILLED/CANCELED/...

### 2.7 GovernanceHub — 治理中樞

**路徑**: `app/governance_hub.py`

**Import**: `change_audit_log`, `recovery_approval_gate`, `governance_events`, `utils.time_utils`
**被 import**: `pipeline_bridge.py`, `phase2_strategy_routes.py`

```python
class GovernanceMode(str, Enum):
    NORMAL, RESTRICTED, FROZEN, MANUAL_REVIEW

@dataclass
class GovernanceStatus:
    timestamp_ms, enabled, mode, auth_state, risk_level, active_leases_count, ...
    def to_dict(self) -> dict

class GovernanceHub:
    def __init__(self, *, audit_dir: str, enabled=True)

    # 授權（SM-01）
    def is_authorized(self) -> bool           # ★ 熱路徑：50ms TTL 快取
    def grant_paper_authorization(self) -> ...

    # 租約（SM-02）
    def acquire_lease(self, intent_id, scope, ttl_seconds=30.0) -> str | None
    def release_lease(self, lease_id, consumed=True) -> None

    # 風控（SM-04）
    def get_risk_level(self) -> int
    def escalate_risk(self, reason) -> None

    # 對賬（EX-04）
    def reconcile(self) -> dict

    # 狀態
    def get_status(self) -> GovernanceStatus
```

### 2.8 MarketDataDispatcher — 市場數據分發

**路徑**: `app/market_data_dispatcher.py`

**Import**: `bybit_public_ws_listener` (PriceEvent, BybitPublicWsListener), `paper_trading_engine`
**被 import**: `paper_trading_routes.py`

```python
# 注意力級別（動態節流）
ATTENTION_DORMANT = "dormant"   # 60s  — 無活躍 session
ATTENTION_LOW     = "low"       # 10s  — 有 session 無訂單
ATTENTION_MEDIUM  = "medium"    # 3s   — 有持倉
ATTENTION_HIGH    = "high"      # 500ms — 限價單接近觸發
ATTENTION_CRITICAL = "critical" # 0ms  — 波動率突刺

class MarketDataDispatcher:
    def __init__(self, engine: PaperTradingEngine, symbols=None, ws_url=None)
    def start(self) -> None
    def stop(self) -> None
    def is_running(self) -> bool
    def get_status(self) -> dict
    def add_symbol(self, symbol: str) -> None
    def remove_symbol(self, symbol: str) -> None
    def register_tick_consumer(self, consumer) -> None  # PipelineBridge 通過此注冊
```

### 2.9 BybitPublicWsListener — WebSocket 監聽器

**路徑**: `app/bybit_public_ws_listener.py`

**Import**: 僅 stdlib + `websocket-client`
**被 import**: `market_data_dispatcher.py`

```python
class PriceEvent:
    symbol: str; last_price: float; mark_price: float | None
    bid1_price: float | None; ask1_price: float | None
    volume_24h: float; turnover_24h: float; price_24h_pct: float
    timestamp_ms: int; received_ts_ms: int

class BybitPublicWsListener:
    def __init__(self, symbols=None, on_price=None, ws_url=PUBLIC_WS_URL)
    def start(self) -> None       # 啟動 daemon thread 連接 WS
    def stop(self) -> None
    def is_running(self) -> bool
    def get_latest_price(self, symbol) -> PriceEvent | None
    def get_all_latest_prices(self) -> dict[str, float]
    def add_symbol(self, symbol) -> None
    def remove_symbol(self, symbol) -> None
```

### 2.10 OllamaClient — 本地 LLM 客戶端

**路徑**: `app/ollama_client.py`

**Import**: 僅 stdlib
**被 import**: `layer2_engine.py`, `pipeline_bridge.py`, `layer2_routes.py`, `phase2_strategy_routes.py`, `guardian_agent.py`, `layer2_tools.py`

```python
@dataclass
class OllamaConfig:
    base_url: str; model: str; timeout_seconds: int; temperature: float; max_retries: int

@dataclass
class OllamaResponse:
    text: str; model: str; success: bool; latency_ms: float; error: str
    @property
    def tokens_per_second(self) -> float
    @property
    def cost_usd(self) -> float

class OllamaClient:
    def __init__(self, config=None)
    def is_available(self, *, force_check=False) -> bool
    async def is_available_async(self, *, force_check=False) -> bool
    def list_models(self) -> list[str]
    def generate(self, prompt, *, system=None, model=None, temperature=None,
                 max_tokens=1024, timeout=None, think=False) -> OllamaResponse
    def chat(self, messages, ...) -> OllamaResponse
```

### 2.11 AnalystAgent — 分析師

**路徑**: `app/analyst_agent.py`

**Import**: `multi_agent_framework`
**被 import**: `pipeline_bridge.py`, `phase2_strategy_routes.py`

```python
@dataclass
class TradeRecord:
    trade_id, symbol, strategy, direction, entry_price, exit_price, pnl, hold_ms,
    regime, timestamp_ms, fees_paid, param_snapshot
    @property
    def is_win(self) -> bool
    @property
    def net_pnl(self) -> float

@dataclass
class PatternInsight:
    insight_id, observations_count, winning_patterns, losing_patterns, regime_strategy_matrix

class AnalystAgent:
    def __init__(self, *, config=None, message_bus=None, ollama_client=None,
                 learning_tier_gate=None, audit_callback=None)
    def start(self) / pause(self) / stop(self)
    def on_message(self, message: AgentMessage) -> None
    def analyze_trade(self, record: TradeRecord) -> dict
    def compute_strategy_metrics(self, strategy: str) -> dict
    def get_strategy_rankings(self) -> list[dict]
    def analyze_patterns(self, *, force=False) -> PatternInsight | None  # ★ L2 模式分析
    def set_truth_registry(self, registry) -> None
    def set_experiment_ledger(self, ledger) -> None
```

### 2.12 ExecutorAgent — 執行者

**路徑**: `app/executor_agent.py`

**Import**: `multi_agent_framework`
**被 import**: `pipeline_bridge.py`, `phase2_strategy_routes.py`

```python
@dataclass
class ExecutionReport:
    report_id, intent_id, symbol, side, requested_qty, filled_qty,
    expected_price, actual_price, slippage_bps, fill_time_ms, success, error

class ExecutorAgent:
    def __init__(self, *, config=None, message_bus=None, paper_engine=None,
                 audit_callback=None, governance_hub=None)
    def start(self) / pause(self) / stop(self)
    def on_message(self, message: AgentMessage) -> None
    def execute_order(self, *, intent_id, symbol, side, qty, order_type="market", ...) -> ExecutionReport
    def get_stats(self) -> dict
```

### 2.13 H0Gate — 確定性門控（<1ms SLA）

**路徑**: `app/h0_gate.py`

**Import**: 僅 stdlib
**被 import**: `main.py`, `pipeline_bridge.py`, `phase2_strategy_routes.py`, `risk_manager.py`, `governance_routes.py`

```python
@dataclass
class H0GateConfig:
    max_data_age_ms, max_cpu_pct, min_memory_mb, max_db_latency_ms, max_network_loss_pct,
    allowed_categories, max_open_positions, max_total_exposure_pct

class H0Gate:
    def __init__(self, config=None)
    def update_health(self, snapshot: H0GateHealthSnapshot) -> None
    def update_risk(self, snapshot: H0GateRiskSnapshot) -> None
    def update_price_ts(self, symbol, ts_ms) -> None
    def check(self, symbol, category="linear") -> H0GateCheckResult  # ★ 5 項檢查 <1ms
    def check_freshness(self, symbol, now_ms) -> tuple[bool, str]
    def check_health(self, now_ms) -> tuple[bool, str]
    def check_eligibility(self, symbol, category) -> tuple[bool, str]
    def check_risk_envelope(self) -> tuple[bool, str]
    def check_cooldown(self, now_ms) -> tuple[bool, str]

class H0HealthWorker:
    def start(self) -> None  # daemon thread 定期採樣 CPU/Memory
    def stop(self) -> None
```

### 2.14 TruthSourceRegistry — 真相源注冊表

**路徑**: `app/truth_source_registry.py`

**Import**: 僅 stdlib
**被 import**: `main.py`, `phase2_strategy_routes.py`

```python
class CognitiveLevel(str, Enum):
    FACT, INFERENCE, HYPOTHESIS

@dataclass
class PatternClaim:
    claim_id, pattern_text, cognitive_level, evidence_source, observation_count,
    confidence, applies_to_regime, applies_to_strategy, falsification_count
    def is_expired(self, now_ms=None) -> bool

class TruthSourceRegistry:  # Singleton
    def record_falsification(self, claim_id) -> None
    def expire_stale_claims(self) -> int
    def get_stats(self) -> dict
    def save_snapshot(self, path) -> bool
    def load_snapshot(self, path) -> int
```

### 2.15 策略工具包（local_model_tools/）

**IndicatorEngine** (`indicator_engine.py`):
```python
class IndicatorEngine:
    def __init__(self, kline_mgr=None)
    def compute_all(self, symbol, klines=None) -> dict  # 7 指標一次計算
    def compute_single(self, symbol, indicator_name) -> Any
    def get_cached(self, symbol) -> dict
    # 指標：SMA, EMA, RSI, MACD, Bollinger, ATR, Volume
```

**SignalEngine** (`signal_generator.py`):
```python
class SignalEngine:
    def __init__(self, indicator_engine)
    def evaluate_all(self, symbol) -> list[Signal]
    def evaluate_single(self, symbol, rule_name) -> Signal | None
    # 8 規則：MACross, RSIOverbought/Oversold, MACD, BB, Volume, Momentum, TrendStrength
```

**StrategyOrchestrator** (`strategy_orchestrator.py`):
```python
class StrategyOrchestrator:
    def __init__(self, indicator_engine, signal_engine)
    def register_strategy(self, strategy: StrategyBase) -> None
    def deploy(self, symbol, strategy_name, params=None) -> bool
    def undeploy(self, symbol, strategy_name) -> bool
    def dispatch_tick(self, symbol, price, ts_ms) -> list[OrderIntent]
    def get_all_intents(self) -> list[OrderIntent]
    def get_deployed_strategies(self) -> dict
```

**5 策略** (`strategies/`):
```python
class StrategyBase(ABC):
    def on_tick(self, symbol, price, ts_ms, indicators, signals) -> list[OrderIntent]
    def on_intent_rejected(self, intent, reason) -> None

# 具體策略：
class MACrossoverStrategy(StrategyBase)    # 趨勢跟隨
class GridTradingStrategy(StrategyBase)     # 網格交易
class BollingerReversionStrategy(StrategyBase)  # 均值回歸
class BBBreakoutStrategy(StrategyBase)      # 突破交易
class FundingRateArbStrategy(StrategyBase)  # 資金費率套利
```

**BacktestEngine** (`backtest_engine.py`):
```python
class BacktestEngine:
    def __init__(self, indicator_engine, signal_engine, strategy, config=None)
    def run(self, klines: list[dict]) -> BacktestResult
    # 純函數、無副作用、完全隔離
```

**EvolutionScheduler** (`evolution_auto_scheduler.py`):
```python
class EvolutionScheduler:
    def start(self) -> None   # 後台 daemon thread
    def stop(self) -> None
    # Sunday UTC cron 自動觸發參數搜索
```

---

## 3. 入口點和啟動流程

### 主入口：`app/main.py`

```
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 啟動順序

```
Phase 1: 配置 & Singleton 創建（main_legacy.py）
  ├─ Settings dataclass 從環境變量/默認值
  ├─ API Token 解析（env → file → auto-generate）
  ├─ Auth credentials 從 ~/BybitOpenClaw/secrets/gui_auth.env
  ├─ JsonStateStore（控制狀態 JSON 文件）
  ├─ FastAPI app 創建 + CORS + Rate limiter
  └─ Static files 掛載

Phase 2: Runtime Bridge 補丁（main.py）
  ├─ JsonStateStore.read/.write/.mutate monkey-patch
  ├─ Snapshot identity stability
  ├─ Runtime fact overlay
  └─ envelope_response 包裝

Phase 3: Router 注冊（main.py lines 136-171）
  ├─ paper_trading_routes   → Paper Trading API
  ├─ layer2_routes          → Layer 2 AI
  ├─ risk_routes            → Risk Control
  ├─ phase2_strategy_routes → Strategy Toolkit（★ 創建所有 Agent 實例）
  ├─ governance_routes      → Governance Hub
  ├─ scout_routes           → Scout Agent
  ├─ backtest_routes        → Backtest Engine
  ├─ experiment_routes      → Experiment Ledger
  └─ evolution_routes       → Evolution Engine

Phase 4: @app.on_event("startup") async handler
  ├─ 4a. 依賴驗證（<100ms 硬截止）
  │   ├─ 硬依賴：GOV_HUB, ENGINE, RISK_MANAGER（缺失 → 啟動失敗）
  │   └─ 軟依賴：PIPELINE_BRIDGE, H0_GATE（缺失 → 降級模式）
  ├─ 4b. Paper Session 自動重授權（fail-open）
  ├─ 4c. SymbolCategoryRegistry 後台初始化（daemon thread，非阻塞）
  ├─ 4d. ExperimentLedger 自動播種（fail-open）
  ├─ 4e. EvolutionScheduler 啟動（fail-open）
  └─ 4f. 啟動時長監控（>500ms 告警）
```

### Singleton 注冊表

| Singleton | 創建位置 | 導入方式 |
|-----------|---------|---------|
| `settings` | main_legacy.py | `base.settings` |
| `STORE` | main_legacy.py（main.py 重建） | `base.STORE` |
| `app` | main_legacy.py | `base.app` |
| `limiter` | main_legacy.py | `base.limiter` |
| `ENGINE` | paper_trading_routes.py | module-level |
| `GOV_HUB` | phase2_strategy_routes.py | module-level |
| `RISK_MANAGER` | phase2_strategy_routes.py | module-level |
| `PIPELINE_BRIDGE` | phase2_strategy_routes.py | module-level |
| `H0_GATE` | phase2_strategy_routes.py | module-level |
| `MESSAGE_BUS` | phase2_strategy_routes.py | module-level |
| 5 Agents | phase2_strategy_routes.py | module-level |

### 進程模型

```
單一進程，FastAPI + uvicorn
├─ 主線程：asyncio event loop（FastAPI 路由處理）
├─ WS daemon thread：BybitPublicWsListener（WebSocket 連接 Bybit）
├─ H0 daemon thread：H0HealthWorker（CPU/Memory 定期採樣）
├─ Registry daemon thread：SymbolCategoryRegistry 初始化
├─ Reconciler daemon thread：ReconciliationEngine 定期對賬
├─ Evolution daemon thread：EvolutionScheduler cron
├─ L2 daemon thread：ModelRouter L2 推理（避免阻塞 on_tick）
└─ Timer threads：TruthSourceRegistry debounced save
```

**注意：所有交易邏輯（策略、風控、下單）在 WS 回調線程中同步執行，不在 asyncio loop 中。**

---

## 4. 數據流和通信方式

### 4.1 通信機制

**三種通信模式並存：**

1. **直接函數調用**（主要模式）
   - PipelineBridge 直接調用 KlineManager/IndicatorEngine/SignalEngine/Orchestrator
   - PipelineBridge 直接調用 PaperTradingEngine.submit_order()
   - GovernanceHub 直接調用各狀態機

2. **MessageBus 消息傳遞**（Agent 間通信）
   - ScoutAgent → INTEL_OBJECT → StrategistAgent
   - ScoutAgent → EVENT_ALERT → GuardianAgent
   - StrategistAgent → TRADE_INTENT → GuardianAgent
   - GuardianAgent → RISK_VERDICT → ExecutorAgent
   - ExecutorAgent → EXECUTION_REPORT → AnalystAgent
   - AnalystAgent → PATTERN_INSIGHT → TruthSourceRegistry

3. **Setter 注入**（依賴鏈接）
   - PipelineBridge 通過 20+ set_xxx() 方法注入所有依賴
   - 在 phase2_strategy_routes.py 中集中配線

### 4.2 WebSocket 數據完整路徑

```
Bybit V5 Public WS (wss://stream.bybit.com/v5/public/linear)
    │ topic: "tickers.BTCUSDT" (snapshot/delta)
    ▼
BybitPublicWsListener._handle_message(raw_json)
    │ 解析 → PriceEvent(symbol, last_price, mark_price, volume_24h, ...)
    │ 更新 _latest_prices[symbol]
    ▼
MarketDataDispatcher._on_price_event(event)
    │ 1. _update_price_history → 60s 滑動窗口
    │ 2. _assess_attention → 動態節流（0ms~60s）
    │ 3. 節流檢查：time_since_last < throttle_interval → 跳過
    ▼
MarketDataDispatcher._trigger_tick(event)
    │ 1. ENGINE.tick(market_prices) → Paper Engine 成交模擬
    │ 2. Fan-out: consumer.on_tick(event)
    ▼
PipelineBridge.on_tick(event)
    ├─ _tick_update_market_data
    │   ├─ KlineManager.on_price_event → K線聚合
    │   ├─ IndicatorEngine 更新
    │   ├─ PerceptionPlane.register_data（認知標記）
    │   └─ H0Gate.update_price_ts
    ├─ _tick_run_strategies
    │   ├─ Orchestrator.dispatch_tick → 5 策略各自計算
    │   └─ _process_pending_intents → 見下方 §4.3
    ├─ _tick_check_risk
    │   └─ StopManager 止損檢查
    └─ _tick_update_stats
        ├─ Scout 掃描（每 300s）
        ├─ Analyst L2 cron（每 3600s）
        └─ Auto-deployer 風險調整
```

### 4.3 信號 → 下單完整路徑

```
Orchestrator.dispatch_tick(symbol, price, ts_ms)
    │ 策略 on_tick → 生成 OrderIntent
    ▼
PipelineBridge._process_pending_intents()
    ├─ 1. [可選] OllamaClient L1 edge filter
    ├─ 2. [可選] StrategistAgent AI 評估
    ├─ 3. [可選] GuardianAgent 風控審查 → RiskVerdict(APPROVED/REJECTED/MODIFIED)
    ├─ 4. [必須] H0Gate.check(symbol) → 確定性門控 <1ms
    ├─ 5. [必須] GovernanceHub.is_authorized() → 50ms TTL 快取
    ├─ 6. [必須] GovernanceHub.acquire_lease(intent_id, scope, ttl=30s)
    ├─ 7. ENGINE.submit_order(symbol, side, type, qty, price, ...)
    │      └─ PaperStateStore.mutate(mutator)
    │          ├─ 驗證 session/tier/governance
    │          ├─ 模擬成交（市價立即 / 限價等待）
    │          ├─ 計算滑點（volume_24h 動態）
    │          ├─ 計算手續費（taker 0.055% / maker 0.02%）
    │          ├─ 更新持倉 / PnL
    │          └─ OMS SM-03 狀態轉換（如啟用）
    └─ 8. GovernanceHub.release_lease(lease_id, consumed=True)
```

### 4.4 風控檢查完整路徑

```
[層次 0] H0 Gate（確定性，<1ms）
    ├─ check_freshness：數據是否過期（max_data_age_ms）
    ├─ check_health：CPU/Memory/DB/Network
    ├─ check_eligibility：symbol 是否允許 + category 是否支持
    ├─ check_risk_envelope：持倉數量 / 總曝險
    └─ check_cooldown：冷卻期

[層次 1] Guardian Agent（AI 輔助，~10-100ms）
    ├─ 槓桿檢查：max_leverage
    ├─ 回撤檢查：max_drawdown_pct
    ├─ 相關性檢查：max_correlation
    ├─ 同方向持倉檢查：max_same_direction_positions
    └─ [可選] Ollama L1 評估

[層次 2] Governance Hub（狀態機，~1ms）
    ├─ is_authorized()：授權狀態機 SM-01
    ├─ acquire_lease()：租約狀態機 SM-02
    └─ get_risk_level()：風控狀態機 SM-04

[層次 3] RiskManager（持倉級）
    ├─ compute_dynamic_stop_pct()：ATR 動態止損
    ├─ compute_round_trip_cost_pct()：回程成本
    ├─ cost_efficiency_grade()：成本效率評級
    └─ PriceHistoryTracker.detect_spike()：異常波動
```

### 4.5 FastAPI 和交易邏輯在同一進程

是的，**單一進程**。FastAPI 路由（asyncio）和交易邏輯（同步線程）共存：
- FastAPI async handlers 處理 HTTP 請求
- WS 回調在獨立 daemon thread 中觸發交易邏輯
- `asyncio.to_thread()` 用於 L2 AI 推理等阻塞操作
- `threading.Lock/RLock` 保護共享狀態

---

## 5. Threading/Async 架構

### 線程使用清單（source code only，不含測試）

```
# Daemon Threads
bybit_public_ws_listener.py:205  — threading.Thread(target=_run_loop, daemon=True, name="bybit-ws")
h0_gate.py:734                   — threading.Thread(target=_run, daemon=True, name="h0-health")
main.py:343                      — threading.Thread(target=_registry_init_bg, daemon=True, name="registry-init")
reconciliation_engine.py:902     — threading.Thread(target=_loop, daemon=True, name="reconciler")
model_router.py:95               — threading.Thread(target=_l2_dispatch, daemon=True)  # L2 推理不阻塞 on_tick
pipeline_bridge.py:325           — threading.Thread(target=..., daemon=True)  # 後台任務

# Locks
pipeline_bridge.py:125           — threading.Lock()
market_data_dispatcher.py:122    — threading.Lock()
multi_agent_framework.py:287,401,665 — threading.Lock() (MessageBus, ScoutAgent)
ollama_client.py:111,463         — threading.Lock() (client + singleton)
truth_source_registry.py:342,928 — threading.Lock() (registry + singleton)
reconciliation_engine.py:232     — threading.Lock()
market_regime.py:317             — threading.RLock()
layer2_cost_tracker.py:92        — threading.RLock()
decision_lease_state_machine.py:402 — threading.Lock()
authorization_state_machine.py:355  — threading.Lock()
risk_governor_state_machine.py:434  — threading.Lock()
audit_persistence.py:123         — threading.Lock()
incident_event_model.py:304      — threading.Lock()
recovery_approval_gate.py:216    — threading.Lock()
learning_tier_gate.py:345        — threading.Lock()

# Async (FastAPI layer)
main.py:197       — async def _startup_integrity_check()
main.py:407       — async def _system_startup_status()
main.py:441       — async def openclaw_proxy()  # asyncio.to_thread() for blocking HTTP
layer2_engine.py  — 全 async：l1_triage(), run_session(), _submit_to_paper()
                    使用 asyncio.to_thread() 包裝同步 Ollama 調用
                    使用 asyncio.Lock() 保護 session 狀態
layer2_types.py:146 — async def search() (SearchProvider ABC)
ollama_client.py:172 — async def is_available_async() (asyncio.to_thread wrapper)

# Timer
truth_source_registry.py:884 — threading.Timer(30.0, _do_save) for debounced persistence
```

### 關鍵架構特徵

1. **WS 回調 → 同步交易**：WebSocket daemon thread 直接調用 PipelineBridge.on_tick()，整個策略→風控→下單鏈是同步的
2. **FastAPI → async**：HTTP 路由是 async，通過 `asyncio.to_thread()` 調用同步阻塞操作
3. **L2 AI → 獨立線程**：ModelRouter 在 daemon thread 中執行 L2 推理，避免阻塞 on_tick 主線程
4. **狀態保護**：所有共享狀態用 `threading.Lock` 或 `threading.RLock` 保護

---

## 6. 性能敏感路徑

### 6.1 Tick → 策略信號路徑

```
BybitPublicWsListener._handle_message()           # WS thread, ~0.1ms
  → PriceEvent 解析
  → MarketDataDispatcher._on_price_event()         # ~0.5ms
    → _assess_attention() + throttle check
    → _trigger_tick()
      → ENGINE.tick(market_prices)                 # ~1ms（遍歷訂單匹配）
      → PipelineBridge.on_tick()                   # ~5-50ms
        → KlineManager.on_price_event()            # ~0.5ms
        → IndicatorEngine.compute_all()            # ~1-5ms（7 指標）
        → Orchestrator.dispatch_tick()             # ~1-10ms（5 策略）
        → _process_pending_intents()               # ~1-100ms（含 AI 如啟用）
          → H0Gate.check()                         # <0.001ms（確定性）
          → GovernanceHub.is_authorized()          # <0.05ms（TTL 快取）
          → GovernanceHub.acquire_lease()          # ~0.1ms
          → ENGINE.submit_order()                  # ~1ms
```

**總延遲**: ~10-60ms（無 AI）/ ~100-500ms（含 L1 Ollama）

### 6.2 信號 → Paper 下單路徑

見 §4.3，關鍵瓶頸：
- Ollama L1 調用：~1.9s（9B）/ ~9.9s（27B）— 在 daemon thread 中
- PaperStateStore.mutate()：~0.5ms（內存）+ 5s debounced 磁盤寫入
- GovernanceHub 鎖：~0.01ms（快速路徑）

### 6.3 Risk Check 路徑

```
H0Gate.check()                    # <1μs（5 項確定性檢查）
  → check_freshness()             # dict lookup + timestamp compare
  → check_health()                # cached snapshot compare
  → check_eligibility()           # set membership + dict lookup
  → check_risk_envelope()         # cached counter compare
  → check_cooldown()              # timestamp compare

GuardianAgent.review_intent()     # ~1-10ms
  → 槓桿/回撤/相關性/同方向 檢查
  → [可選] Ollama 評估 → 1.9-9.9s

RiskManager checks (per tick)     # ~0.5ms
  → compute_dynamic_stop_pct()
  → PriceHistoryTracker.compute_atr_pct()
  → StopManager.check_stops()
```

---

## 7. 配置和狀態管理

### 7.1 配置文件

| 文件 | 格式 | 用途 |
|------|------|------|
| `~/BybitOpenClaw/secrets/gui_auth.env` | KEY=VALUE | GUI 登入認證 |
| `.secrets/api_token` | plain text | API Token |
| `runtime/openclaw_bybit_control_state.json` | JSON | 主控狀態 |
| Paper state file | JSON | Paper Trading 狀態 |
| `audit_*.jsonl` | JSONL (append-only) | 審計日誌 |

**環境變量** (主要):
```
OPENCLAW_API_TOKEN          — API Token
OPENCLAW_STATE_FILE         — 狀態文件路徑
OPENCLAW_AUTH_ACTOR_ID      — 操作者 ID
BYBIT_API_HOST              — Bybit API 端點
BYBIT_DEMO_API_KEY          — Demo API Key
BYBIT_DEMO_API_SECRET       — Demo API Secret
ANALYST_L2_MIN_OBS          — L2 觸發門檻
```

### 7.2 運行時狀態持久化

| 數據 | 方式 | 詳情 |
|------|------|------|
| 控制狀態 | JSON 文件 | atomic write + debounced（5s）|
| Paper Trading | JSON 文件 | PaperStateStore + debounced |
| 審計日誌 | JSONL 文件 | append-only + 自動輪轉 |
| 治理快照 | JSON 文件 | GovernanceHub 內存 + 快照 |
| TruthSource | JSON 文件 | debounced save（30s Timer）|
| Grafana 指標 | PostgreSQL | GrafanaDataWriter（可選）|

**不使用 Redis**（database_files/redis_data 存在但代碼中未引用）。
**不使用 ORM/SQLAlchemy**。PostgreSQL 通過 psycopg2 直接 SQL。

### 7.3 Secrets 管理

```
~/BybitOpenClaw/secrets/gui_auth.env    — GUI 認證（file permission 0600）
.secrets/api_token                       — API Token（auto-generated，0600）
BYBIT_DEMO_API_KEY/SECRET               — 環境變量（不寫入代碼）
settings/ 目錄                           — .gitignore，本地 only
```

---

## 8. 外部依賴

### requirements.txt

```
# Core (required)
fastapi>=0.115.0
uvicorn[standard]>=0.27.0
pydantic>=2.11.0

# HTTP client (optional, L2 web search)
httpx>=0.28.0

# Rate limiting
slowapi>=0.1.9

# WebSocket client (Bybit WS listener)
websocket-client>=1.8.0

# PostgreSQL client (optional, Grafana + demo sync)
psycopg2-binary>=2.9.0

# System monitoring (optional, H0 health worker)
psutil>=5.9.0

# HTML scraping (optional, L2 web search fallback)
beautifulsoup4>=4.12.0

# Testing
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

### 已安裝版本（key packages）

```
fastapi==0.135.2
uvicorn==0.27.1
pydantic==2.12.5
httpx==0.28.1
slowapi==0.1.9
websocket-client==1.9.0
bcrypt==3.2.2
requests==2.31.0
pytest==9.0.2
```

### 外部工具（非 pip）

| 工具 | 用途 | 必須？ |
|------|------|--------|
| **Ollama** | 本地 LLM 推理（Qwen 3.5 9B/27B） | 可選（降級為純確定性） |
| **PostgreSQL** | Grafana 指標 + Demo 同步 | 可選 |
| **Grafana** | 運營監控儀表板 | 可選 |
| **Tailscale** | 遠程 VPN 訪問 | 可選 |

---

## 附錄：當前硬狀態

```python
system_mode            = "demo_only"
execution_state        = "disabled"
execution_authority    = "not_granted"
live_execution_allowed = False
decision_lease_emitted = False

# 測試基準線
tests_passed  = 3704
tests_failed  = 23   # pre-existing
tests_errors  = 17   # pre-existing
api_routes    = 126+
code_lines    = ~50,000 (app/ directory)
code_complete = ~82%
biz_complete  = ~52%
agents        = 5/6 (Scout/Strategist/Guardian/Analyst/Executor, Conductor 編排待完善)
```
