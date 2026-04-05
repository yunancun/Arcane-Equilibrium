"""
Phase 2 Local Strategy Toolkit — Facade (TD-02 split)
Phase 2 本地策略工具包 — 外觀模式（TD-02 拆分）

TD-02 Split: This file is now a thin facade that re-exports from:
  - strategy_wiring.py       — module-level singletons + DI wiring (~1179 lines)
  - strategy_read_routes.py  — GET route handlers (~396 lines)
  - strategy_write_routes.py — POST/state-changing route handlers (~223 lines)
  - strategy_ai_routes.py    — Demo/AI/Telegram route handlers (~141 lines)

All existing imports (`from .phase2_strategy_routes import X`) remain valid.
所有既有的 import 路徑不變。
"""

# ── Re-export all singletons and wiring from strategy_wiring ──
# 從 strategy_wiring 重新導出所有單例和接線結果
from .strategy_wiring import *  # noqa: F401,F403

# ── Import route modules to trigger route registration on phase2_router ──
# 導入路由模組以觸發路由註冊到 phase2_router
# IMPORTANT: _ai must be imported BEFORE _read so that static /demo/* routes
# are registered before the /{name}/* wildcard routes in strategy_read_routes.
# 重要：_ai 必須在 _read 之前導入，以確保 /demo/* 靜態路由
# 在 strategy_read_routes 的 /{name}/* 通配符路由之前註冊。
from . import strategy_ai_routes as _ai  # noqa: F401
from . import strategy_read_routes as _read  # noqa: F401
from . import strategy_write_routes as _write  # noqa: F401

# ── Explicit re-exports for common direct imports ──
# 顯式重新導出常見的直接導入
from .strategy_wiring import (  # noqa: F811
    phase2_router,
    PIPELINE_BRIDGE,
    PAPER_ENGINE,
    KLINE_MANAGER,
    INDICATOR_ENGINE,
    SIGNAL_ENGINE,
    ORCHESTRATOR,
    TRADE_ATTRIBUTION,
    SCOUT_AGENT,
    MESSAGE_BUS,
    CONDUCTOR,
    OLLAMA_CLIENT,
    STRATEGIST_AGENT,
    GUARDIAN_AGENT,
    ANALYST_AGENT,
    DEMO_CONNECTOR,
    TELEGRAM,
    PAPER_LIVE_GATE,
)

# Re-export route functions for test imports
# 重新導出路由函數供測試導入
from .strategy_read_routes import (  # noqa: F811
    get_klines,
    get_indicators,
    get_signals,
    get_signal_summary,
    list_strategies,
    get_strategy_status,
    get_intents,
    get_orchestrator_status,
    get_pipeline_stats,
    get_scanner_opportunities,
    get_auto_deployed,
    get_kelly_recommendations,
    get_dynamic_risk_status,
)
from .strategy_write_routes import (  # noqa: F811
    activate_strategy,
    pause_strategy,
    stop_strategy,
    create_strategy,
    delete_strategy,
    toggle_dynamic_risk,
)
from .strategy_ai_routes import (  # noqa: F811
    get_telegram_status,
    get_ai_consultation_status,
    get_demo_status,
    get_demo_balance,
    get_demo_positions,
    get_demo_orders,
    get_demo_fills,
)
