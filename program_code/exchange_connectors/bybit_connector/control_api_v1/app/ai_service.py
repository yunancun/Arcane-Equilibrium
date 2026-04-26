"""
R01-7 — AIService: Python-side AI evaluation service for Rust engine IPC
=========================================================================
Governance refs: DOC-04 §G Multi-Agent, Rust Migration R-01

MODULE_NOTE (EN/中):
  Top-level facade for the AI service. Owns shared constants, the local LLM
  singleton, system prompts, the socket-path resolver, and the public factory.
  ``AIService`` and ``AIServiceListener`` are re-exported from sibling files for
  backward-compatible imports (``from app.ai_service import AIService``).
  AI 服務頂層 facade。持有常數、本地 LLM 單例、system prompts、socket 路徑解析、
  公開 factory；``AIService`` / ``AIServiceListener`` 由姊妹檔 re-export，外部
  imports 不變。

  Receives Rust engine JSON-RPC requests, dispatches to 5 Agent handlers
  (Strategist/Analyst/Conductor/Scout/Guardian), returns structured responses.
  接收 Rust 引擎 JSON-RPC 請求，分派到 5 個 Agent 處理器，返回結構化結果。

  Per-handler TTL: strategist=15s, analyst=30s, conductor=10s, scout=10s, guardian=5s.
  Safety: fail-closed, error msgs truncated to 200 chars, no hardcoded paths.
  安全：fail-closed，錯誤截斷 200 字符，路徑不硬編碼。

  Migration / 遷移：
  - R-02 (S6): strategist + guardian → Ollama L1
  - C1-C2 (S7): analyst → AnalystAgent.analyze_trade(), scout → ScoutAgent intel/alerts
  - R-06 remaining / 剩餘: conductor still stub (W23+)

  Split layout (G5-04, 2026-04-24): this file kept thin (≤350 lines) per §九
  1200-line cap; ``AIService`` lives in ``ai_service_dispatch`` and
  ``AIServiceListener`` in ``ai_service_listener`` — pure structural extraction,
  no behaviour change.
  G5-04 拆分（2026-04-24）：本檔精簡至 ≤350 行對應 §九 1200 上限；``AIService``
  搬至 ``ai_service_dispatch``、``AIServiceListener`` 搬至 ``ai_service_listener``，
  純結構性拆分，行為不變。
"""

from __future__ import annotations

import logging
import os
from typing import Any, TYPE_CHECKING

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Local LLM client lazy singleton / 本地 LLM 客戶端懶加載單例
# LLM-ABC-MIGRATION-1: routed via local_llm_factory (LOCAL_LLM_PROVIDER env);
# variable name kept as _OLLAMA_CLIENT for §九 singleton-table grep-stability.
# LLM-ABC-MIGRATION-1：統一經 local_llm_factory（LOCAL_LLM_PROVIDER env 切換）；
# 變數名保留 _OLLAMA_CLIENT 以維持 §九 單例表的 grep 穩定性。
# ═══════════════════════════════════════════════════════════════════════════════

_OLLAMA_CLIENT: Any = None  # LocalLLM client singleton (Ollama | LMStudio) | None
_OLLAMA_INIT_ATTEMPTED: bool = False


def _get_ollama_client() -> Any:
    """Lazy-init local LLM client singleton. Returns None if unavailable (fail-open).
    懶加載本地 LLM 客戶端單例。不可用時返回 None（失敗開放）。"""
    global _OLLAMA_CLIENT, _OLLAMA_INIT_ATTEMPTED
    if _OLLAMA_INIT_ATTEMPTED:
        return _OLLAMA_CLIENT
    _OLLAMA_INIT_ATTEMPTED = True
    try:
        from .local_llm_factory import get_local_llm_client
        _OLLAMA_CLIENT = get_local_llm_client()
        logger.info("Local LLM client initialized for AIService / AIService 的本地 LLM 客戶端已初始化")
    except Exception as exc:
        logger.warning("Local LLM client init failed (AI handlers will use heuristics): %s", exc)
        _OLLAMA_CLIENT = None
    return _OLLAMA_CLIENT


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常數
# ═══════════════════════════════════════════════════════════════════════════════

# Handler TTLs (seconds) / 處理器超時時間（秒）
HANDLER_TTLS: dict[str, float] = {
    "strategist_evaluate": 15.0,   # Strategy evaluation / 策略評估
    "analyst_evaluate": 30.0,      # Deep analysis / 深度分析
    "conductor_evaluate": 10.0,    # Orchestration / 編排決策
    "scout_scan": 10.0,            # Market scanning / 市場掃描
    "guardian_check": 5.0,         # Risk check (fastest) / 風控檢查（最快）
    # G3-08 Phase 1 Sub-task B: H-state aggregator stub. Short TTL because the
    # handler is a pure-function read (Phase 1 returns empty shell). Phase 2-4
    # may revisit if singleton snapshot reads grow expensive, but should stay
    # ≤ 1s to honour PA §G2 (≤ 5ms reverse-pull SLA).
    # G3-08 Phase 1 Sub-task B：H 狀態聚合器 stub。短 TTL，因為 handler 為
    # 純函式讀取（Phase 1 回空殼）。Phase 2-4 若 snapshot 讀取變昂貴再
    # 評估，但應維持 ≤ 1s 以對齊 PA §G2（reverse-pull SLA ≤ 5ms）。
    "query_h_state_full": 2.0,
}

# Socket path defaults / Socket 路徑默認值
# Honour OPENCLAW_DATA_DIR for cross-platform dev (Mac: $HOME/.openclaw_runtime).
# 支援 OPENCLAW_DATA_DIR 跨平台開發（Mac：$HOME/.openclaw_runtime）。
_DEFAULT_SOCKET_DIR = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
_DEFAULT_SOCKET_NAME = "ai_service.sock"

JSONRPC_VERSION = "2.0"                   # JSON-RPC protocol version
MAX_LINE_BYTES = 16 * 1024 * 1024         # Max line size 16 MB / 最大行長度 16 MB
ERROR_MSG_MAX_LEN = 200                   # Truncate errors (security) / 截斷錯誤訊息（安全）

# ── Strategist system prompt for param tuning / 策略師參數調優系統 prompt ──
_STRATEGIST_SYSTEM_PROMPT = (
    "You are an algorithmic trading strategy tuner. "
    "Given a strategy's recent performance metrics and adjustable parameters, "
    "recommend parameter adjustments to improve performance.\n"
    "Rules:\n"
    "1. Respond with ONLY a JSON object of param_name: new_value pairs.\n"
    "2. Only include params you want to change.\n"
    "3. Keep changes conservative — each param within ±30% of its current value.\n"
    "4. Weight params (weight_adx, weight_regime, weight_volume, weight_momentum) must sum to exactly 65.\n"
    "5. All values must be within the min/max range provided.\n"
    "6. If performance is acceptable or insufficient data, respond with {}.\n"
    "7. No explanation, no commentary — pure JSON only."
)

# ── Guardian system prompt for event classification / 守衛事件分類系統 prompt ──
_GUARDIAN_SYSTEM_PROMPT = (
    "You are a crypto market risk classifier. "
    "Given a market event, classify its risk level and provide a brief assessment.\n"
    "Respond with ONLY a JSON object: "
    "{\"risk_level\": \"low|medium|high|critical\", \"assessment\": \"brief reason\"}\n"
    "Be conservative: when in doubt, classify higher risk."
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: default socket path / 輔助函數：默認 socket 路徑
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_socket_path(explicit: str | None = None) -> str:
    """Resolve socket path: explicit > env > default. / 解析 socket 路徑：顯式 > 環境變量 > 默認值。"""
    if explicit:
        return explicit
    env_path = os.environ.get("OPENCLAW_AI_SERVICE_SOCKET")
    if env_path:
        return env_path
    return os.path.join(_DEFAULT_SOCKET_DIR, _DEFAULT_SOCKET_NAME)


# ═══════════════════════════════════════════════════════════════════════════════
# Re-exports for backward-compatible imports / 向後相容 re-export
# Tests + external callers import ``AIService`` / ``AIServiceListener`` /
# ``_probe_unix_listener_alive`` from this module — keep names stable.
# 測試與外部呼叫端從本模組匯入 ``AIService`` 等名稱，須保持穩定。
# ═══════════════════════════════════════════════════════════════════════════════

# Lazy ``from … import …`` placed *after* this module's constants so the sibling
# files (which do ``from . import ai_service as core``) see fully populated
# globals when their class/function bodies reference ``core.HANDLER_TTLS`` etc.
# Sibling 在 import 後才會用到 ``core.<name>``，因此在常數定義完成後再做 re-export
# 不會構成循環。
from .ai_service_dispatch import AIService  # noqa: E402
from .ai_service_listener import (  # noqa: E402
    AIServiceListener,
    _probe_unix_listener_alive,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Factory / convenience / 工廠 / 便利函數
# ═══════════════════════════════════════════════════════════════════════════════

def create_ai_service_listener(
    socket_path: str | None = None,
) -> tuple["AIService", "AIServiceListener"]:
    """
    Create an AIService + AIServiceListener pair ready to start.
    創建一對準備啟動的 AIService + AIServiceListener。

    Attempts to inject MessageBus from strategy_wiring for Guardian L1 relay (B4).
    嘗試從 strategy_wiring 注入 MessageBus 以供 Guardian L1 事件中繼（B4）。

    Usage::

        service, listener = create_ai_service_listener()
        await listener.start()
        # ... later ...
        await listener.stop()

    Args:
        socket_path: Optional explicit socket path. Falls back to env var
                     or default (/tmp/openclaw/ai_service.sock).
                     可選的顯式 socket 路徑。回退到環境變量或默認值。

    Returns:
        Tuple of (AIService, AIServiceListener).
        (AIService, AIServiceListener) 元組。
    """
    # B4: Inject MessageBus for Guardian event relay (fail-open)
    # B4：注入 MessageBus 供 Guardian 事件中繼（失敗開放）
    message_bus = None
    try:
        from .strategy_wiring import MESSAGE_BUS
        message_bus = MESSAGE_BUS
        logger.info("MessageBus injected into AIService for Guardian L1 relay / 已注入 MessageBus")
    except Exception as bus_exc:
        logger.debug("MessageBus not available for AIService (non-fatal): %s", bus_exc)

    # C1: Inject AnalystAgent for trade attribution (fail-open)
    analyst_agent = None
    try:
        from .strategy_wiring import ANALYST_AGENT
        analyst_agent = ANALYST_AGENT
        logger.info("AnalystAgent injected (C1) / 已注入 AnalystAgent")
    except Exception as analyst_exc:
        logger.debug("AnalystAgent not available (non-fatal): %s", analyst_exc)

    # C2: Inject ScoutAgent for intelligence scan (fail-open)
    scout_agent = None
    try:
        from .strategy_wiring import SCOUT_AGENT
        scout_agent = SCOUT_AGENT
        logger.info("ScoutAgent injected (C2) / 已注入 ScoutAgent")
    except Exception as scout_exc:
        logger.debug("ScoutAgent not available (non-fatal): %s", scout_exc)

    # R-06-v2: Inject Conductor for orchestration (fail-open)
    conductor = None
    try:
        from .strategy_wiring import CONDUCTOR
        conductor = CONDUCTOR
        logger.info("Conductor injected (R-06-v2) / 已注入 Conductor")
    except Exception as cond_exc:
        logger.debug("Conductor not available (non-fatal): %s", cond_exc)

    service = AIService(
        message_bus=message_bus,
        analyst_agent=analyst_agent,
        scout_agent=scout_agent,
        conductor=conductor,
    )
    listener = AIServiceListener(service, socket_path=socket_path)
    return service, listener


__all__ = [
    "AIService",
    "AIServiceListener",
    "_probe_unix_listener_alive",
    "_resolve_socket_path",
    "create_ai_service_listener",
    "HANDLER_TTLS",
    "JSONRPC_VERSION",
    "MAX_LINE_BYTES",
    "ERROR_MSG_MAX_LEN",
]
