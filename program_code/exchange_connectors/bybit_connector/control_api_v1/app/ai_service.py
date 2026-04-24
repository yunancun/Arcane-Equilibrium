"""
R01-7 — AIService: Python-side AI evaluation service for Rust engine IPC
=========================================================================
Governance refs: DOC-04 §G Multi-Agent, Rust Migration R-01

MODULE_NOTE (EN/中):
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
"""

from __future__ import annotations

import asyncio
import errno
import json
import logging
import os
import re
import socket as _socket_stdlib

import time
from typing import Any, Callable

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
# AIService — Core dispatch logic / 核心分派邏輯
# ═══════════════════════════════════════════════════════════════════════════════

class AIService:
    """
    AI Service — bridges Rust engine IPC requests to Python AI Agents.
    AI 服務 — 橋接 Rust 引擎 IPC 請求到 Python AI Agent。

    Receives JSON-RPC requests from the Rust engine, dispatches to the
    appropriate agent, and returns structured responses.
    接收 Rust 引擎的 JSON-RPC 請求，分派到對應的 Agent，返回結構化結果。

    Thread safety: single-threaded asyncio — no locks needed for stats dict.
    線程安全：單線程 asyncio — 統計 dict 不需要鎖。

    Usage::

        service = AIService()
        result = await service.dispatch("strategist_evaluate", {"intel": {...}})

    Migration: R-02 strategist+guardian L1. C1-C2 analyst+scout. R-06-v2 conductor+feedback.
    遷移：R-02 strategist+guardian。C1-C2 analyst+scout。R-06-v2 conductor+反饋閉環。
    """

    def __init__(
        self,
        *,
        message_bus: Any = None,
        analyst_agent: Any = None,
        scout_agent: Any = None,
        conductor: Any = None,
    ) -> None:
        self._message_bus = message_bus      # Guardian L1 relay (B4)
        self._analyst_agent = analyst_agent  # C1 trade attribution
        self._scout_agent = scout_agent      # C2 intelligence scan
        self._conductor = conductor          # R-06-v2 orchestration

        # Handler registry: method name -> async handler callable
        # 處理器註冊表：方法名 -> 異步處理器
        self._handlers: dict[str, Callable[..., Any]] = {}

        # Call statistics — single-threaded asyncio, no lock needed
        # 調用統計 — 單線程 asyncio，不需要鎖
        self._stats: dict[str, int] = {
            "strategist_calls": 0,
            "analyst_calls": 0,
            "conductor_calls": 0,
            "scout_calls": 0,
            "guardian_calls": 0,
            "errors": 0,
            "timeouts": 0,
            "total_dispatches": 0,
        }

        # Timestamps for observability / 可觀測性的時間戳
        self._created_at: float = time.time()
        self._last_dispatch_at: float = 0.0

        self._register_handlers()
        logger.info("AIService initialized with %d handlers", len(self._handlers))

    # ─── Handler registration / 處理器註冊 ───

    def _register_handlers(self) -> None:
        """
        Register all JSON-RPC method handlers.
        註冊所有 JSON-RPC 方法處理器。
        """
        self._handlers = {
            "strategist_evaluate": self._handle_strategist,
            "analyst_evaluate": self._handle_analyst,
            "conductor_evaluate": self._handle_conductor,
            "scout_scan": self._handle_scout,
            "guardian_check": self._handle_guardian,
        }

    # ─── Main dispatch / 主分派入口 ───

    async def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Dispatch an IPC method call to the appropriate handler with per-method TTL.
        將 IPC 方法調用分派到對應的處理器，帶每方法 TTL。

        Returns JSON-serializable dict with "status" or "error" key.
        返回可序列化 dict，包含 "status" 或 "error" 鍵。
        """
        self._stats["total_dispatches"] += 1
        self._last_dispatch_at = time.time()

        handler = self._handlers.get(method)
        if handler is None:
            self._stats["errors"] += 1
            logger.warning("Unknown IPC method: %s", method)
            return {
                "error": f"unknown_method: {method}",
                "available_methods": list(self._handlers.keys()),
            }

        ttl = HANDLER_TTLS.get(method, 15.0)
        t0 = time.monotonic()

        try:
            result = await asyncio.wait_for(handler(params), timeout=ttl)
            elapsed_ms = (time.monotonic() - t0) * 1000
            result["_elapsed_ms"] = round(elapsed_ms, 2)
            return result

        except asyncio.TimeoutError:
            self._stats["timeouts"] += 1
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.error(
                "Handler timeout: method=%s ttl=%.1fs elapsed=%.0fms",
                method, ttl, elapsed_ms,
            )
            return {
                "error": "timeout",
                "method": method,
                "ttl_seconds": ttl,
                "_elapsed_ms": round(elapsed_ms, 2),
            }

        except Exception as exc:
            self._stats["errors"] += 1
            elapsed_ms = (time.monotonic() - t0) * 1000
            # Truncate error message to prevent stack trace leakage
            # 截斷錯誤訊息防止堆疊追蹤洩漏
            error_msg = str(exc)[:ERROR_MSG_MAX_LEN]
            logger.error(
                "Handler error: method=%s error=%s elapsed=%.0fms",
                method, error_msg, elapsed_ms,
            )
            return {
                "error": error_msg,
                "method": method,
                "_elapsed_ms": round(elapsed_ms, 2),
            }

    # ─── Agent handlers (stubs) / Agent 處理器（stub 實現）───
    # These will be wired to real agents in R-02/R-06.
    # 這些將在 R-02/R-06 階段接入真實 Agent。

    async def _handle_strategist(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Strategist as Configurator: evaluate strategy×symbol metrics, recommend param adjustments.
        策略師作為配置器：評估策略×symbol 指標，推薦參數調整。

        Input from Rust StrategistScheduler (B0):
          params.intel = {symbol, strategy, win_rate, avg_pnl, fill_count}
          params.model_tier = "l1_9b"
          params.current_params = {...}  (B3: current strategy params for context)
          params.param_ranges = [...]    (B3: valid ranges for each param)

        Returns: flat dict of param_name→value for Rust validate_recommendation().
        Rust does range/delta/weight_sum validation — Python just recommends.
        返回：param_name→value 的平面 dict，供 Rust validate_recommendation() 驗證。
        Rust 做範圍/delta/weight_sum 驗證 — Python 只推薦。

        Fail-closed: Ollama unavailable or error → return empty dict (retain current params).
        失敗關閉：Ollama 不可用或出錯 → 返回空 dict（保留當前參數）。
        """
        self._stats["strategist_calls"] += 1

        intel = params.get("intel", {})
        symbol = intel.get("symbol", "unknown")
        strategy = intel.get("strategy", "unknown")
        win_rate = intel.get("win_rate", 0.0)
        avg_pnl = intel.get("avg_pnl", 0.0)
        fill_count = intel.get("fill_count", 0)
        model_tier = params.get("model_tier", "l1_9b")

        # B3: current params and ranges from Rust (optional — absent before B3 enhancement)
        # B3：來自 Rust 的當前參數和範圍（可選 — B3 增強前可能不存在）
        current_params = params.get("current_params", {})
        param_ranges = params.get("param_ranges", [])

        ollama = await asyncio.to_thread(_get_ollama_client)

        # If Ollama unavailable → empty recommendation (retain current params)
        # Ollama 不可用 → 空推薦（保留當前參數）
        if ollama is None or not await ollama.is_available_async():
            logger.info(
                "Strategist: Ollama unavailable, returning empty recommendation for %s/%s / "
                "Ollama 不可用，返回空推薦",
                strategy, symbol,
            )
            return {
                "status": "evaluated",
                "agent": "strategist",
                "symbol": symbol,
                "strategy": strategy,
                "source": "heuristic_no_ollama",
                "reasoning": "Ollama unavailable — retain current params",
            }

        # Build structured prompt for param tuning / 構建參數調優的結構化 prompt
        prompt = self._build_strategist_prompt(
            strategy, symbol, win_rate, avg_pnl, fill_count,
            current_params, param_ranges,
        )
        # R-06-v2: enrich prompt with analyst insights + guardian rejection stats
        # R-06-v2：用 Analyst 洞察 + Guardian 拒絕統計增強 prompt
        try:
            from .ai_service_feedback import get_feedback_section
            fb = await asyncio.to_thread(get_feedback_section, strategy)
            if fb:
                prompt += "\n\n" + fb
        except Exception:
            pass  # fail-open / 失敗開放

        try:
            response = await asyncio.to_thread(
                ollama.generate,
                prompt,
                system=_STRATEGIST_SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=512,
                timeout=12,
                think=False,
            )

            if not response.success:
                logger.warning(
                    "Strategist Ollama call failed: %s / 策略師 Ollama 調用失敗",
                    getattr(response, "error", "unknown"),
                )
                return {
                    "status": "evaluated",
                    "agent": "strategist",
                    "symbol": symbol,
                    "strategy": strategy,
                    "source": "ollama_error",
                    "reasoning": "Ollama call failed — retain current params",
                }

            # Parse JSON param recommendations from Ollama response
            # 從 Ollama 回應中解析 JSON 參數推薦
            recommended = self._parse_strategist_response(response.text, strategy, symbol)
            return recommended

        except Exception as exc:
            logger.error(
                "Strategist evaluation error (fail-closed → empty): %s / 策略師評估錯誤: %s",
                str(exc)[:ERROR_MSG_MAX_LEN], str(exc)[:ERROR_MSG_MAX_LEN],
            )
            self._stats["errors"] += 1
            return {
                "status": "evaluated",
                "agent": "strategist",
                "symbol": symbol,
                "strategy": strategy,
                "source": "error",
                "reasoning": f"Exception: {str(exc)[:100]} — retain current params",
            }

    @staticmethod
    def _build_strategist_prompt(
        strategy: str,
        symbol: str,
        win_rate: float,
        avg_pnl: float,
        fill_count: int,
        current_params: dict[str, Any],
        param_ranges: list[dict[str, Any]],
    ) -> str:
        """Build prompt for Ollama strategy param tuning. / 構建 Ollama 策略參數調優 prompt。

        STRATEGIST-TUNE-CAP-ENFORCE-1 (2026-04-24): pre-compute ±30% allowed range
        for each adjustable param and list it explicitly. Earlier prompt only said
        "conservative (within ±30%)" and LLM proposals 100% violated it; Rust-side
        cap (strategist_scheduler/mod.rs:48 MAX_PARAM_DELTA_PCT=0.30) rejected all
        → strategist_applied_params永遠空表。Math should not be LLM's job.
        預先算好邊界再讓 LLM 填值，不要讓 LLM 自己算 ±30%。
        """
        # Format adjustable param ranges for the prompt, including pre-computed
        # ±30% delta cap bounds so the LLM doesn't have to do math.
        # 為 prompt 格式化可調參數範圍，預算 ±30% cap 邊界避免 LLM 算錯。
        adjustable = [
            r for r in param_ranges
            if r.get("agent_adjustable", False)
        ]
        # Must mirror rust/openclaw_engine/src/strategist_scheduler/mod.rs:48
        # MAX_PARAM_DELTA_PCT = 0.30 — if Rust cap changes, update here.
        # 須與 Rust 端 MAX_PARAM_DELTA_PCT 對齊；若 Rust 調 cap 此處亦改。
        max_delta_pct = 0.30
        range_lines = []
        for r in adjustable:
            name = r["name"]
            cur_val = current_params.get(name, None)
            outer_min = r.get("min", "?")
            outer_max = r.get("max", "?")
            # Pre-compute ±30% inner bounds when current is numeric.
            # current 為數值時預算 ±30% 內部邊界。
            if isinstance(cur_val, (int, float)) and cur_val != 0:
                lo = cur_val * (1.0 - max_delta_pct)
                hi = cur_val * (1.0 + max_delta_pct)
                # Clip to outer min/max when provided.
                if isinstance(outer_min, (int, float)):
                    lo = max(lo, outer_min)
                if isinstance(outer_max, (int, float)):
                    hi = min(hi, outer_max)
                range_lines.append(
                    f"  - {name}: current={cur_val}, "
                    f"allowed_range=[{lo:g}, {hi:g}] "
                    f"(±30% cap, outer bounds min={outer_min} max={outer_max})"
                )
            else:
                range_lines.append(
                    f"  - {name}: current={cur_val}, min={outer_min}, max={outer_max} "
                    f"(zero/unknown current — skip unless certain)"
                )
        ranges_text = "\n".join(range_lines) if range_lines else "  (no adjustable params available)"

        return (
            f"Strategy: {strategy}\n"
            f"Symbol: {symbol}\n"
            f"Performance (last 7 days):\n"
            f"  - Win rate: {win_rate:.2%}\n"
            f"  - Average PnL per fill: {avg_pnl:.6f}\n"
            f"  - Fill count: {fill_count}\n"
            f"\nAdjustable parameters with PRE-COMPUTED allowed ranges:\n{ranges_text}\n"
            f"\nRecommend parameter adjustments to improve this strategy's performance.\n"
            f"Respond with ONLY a JSON object of param_name: new_value pairs.\n"
            f"\n"
            f"HARD RULES (violation → rejected, your suggestion wasted):\n"
            f"  1. Each new value MUST be WITHIN the allowed_range shown above.\n"
            f"     Example: if allowed_range=[42000, 78000], values like 30000 or 150000 are REJECTED.\n"
            f"  2. Do not guess bounds — use the pre-computed allowed_range exactly.\n"
            f"  3. Only include params you want to change.\n"
            f"  4. Weight params (weight_adx, weight_regime, weight_volume, weight_momentum) must sum to 65.\n"
            f"  5. If performance is acceptable or data is insufficient, respond with {{}} (empty object).\n"
        )

    @staticmethod
    def _parse_strategist_response(
        text: str,
        strategy: str,
        symbol: str,
    ) -> dict[str, Any]:
        """Parse Ollama response into param recommendation dict. / 解析 Ollama 回應為參數推薦 dict。"""
        text = text.strip()
        # Strip markdown code fences if present / 移除 markdown 代碼圍欄
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON object from mixed text / 嘗試從混合文本中提取 JSON
            match = re.search(r"\{[^{}]*\}", text)
            if match:
                try:
                    result = json.loads(match.group())
                except json.JSONDecodeError:
                    result = {}
            else:
                result = {}

        if not isinstance(result, dict):
            logger.warning("Strategist response not a dict: %s", type(result).__name__)
            result = {}

        # Filter to only numeric values (param recommendations).
        # 只保留數值類型（參數推薦）。
        #
        # STRATEGIST-TUNE-CAP-ENFORCE-1-FUP (2026-04-24): preserve integer-ness
        # instead of force-cast to float. Rust side uses typed params (`u64` /
        # `u32` for e.g. `cooldown_ms`); if we force every numeric to float,
        # `78000.0` fails serde `u64` deserialize with "invalid type: floating
        # point, expected u64". LLM naturally returns `78000` (int) in JSON;
        # the bug was the blanket `float(v)` cast here.
        #
        # Rule: if value is int-typed OR float that equals its int round,
        # store as int; otherwise keep as float (for fractional weights).
        # 修 bug：舊 `float(v)` 強轉讓整數參數（如 cooldown_ms u64）在 Rust
        # serde 反序列化失敗。改為保留整數性：值為 int 或 float.is_integer()
        # 為 True 時存為 int，其餘保 float（分數權重仍可帶小數）。
        filtered: dict[str, Any] = {}
        for k, v in result.items():
            if isinstance(v, bool):
                # bool 是 int 的子類，必須排除避免 True/False 當 0/1 混入
                logger.debug("Skipping bool param recommendation: %s=%s", k, v)
                continue
            if isinstance(v, int):
                filtered[k] = v
            elif isinstance(v, float):
                if v.is_integer():
                    filtered[k] = int(v)
                else:
                    filtered[k] = v
            else:
                logger.debug("Skipping non-numeric param recommendation: %s=%s", k, v)

        # Add metadata for Rust-side logging / 添加元數據供 Rust 側日誌
        filtered["status"] = "evaluated"
        filtered["agent"] = "strategist"
        filtered["symbol"] = symbol
        filtered["strategy"] = strategy
        filtered["source"] = "ollama_l1"
        filtered["reasoning"] = f"AI-recommended params for {strategy}/{symbol}"

        return filtered

    async def _handle_analyst(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        C1: Forward to AnalystAgent for trade attribution. Stub fallback.
        C1：轉發到 AnalystAgent 進行交易歸因。不可用時回退到 stub。
        """
        self._stats["analyst_calls"] += 1
        trade_data = params.get("trade_data", {})
        analysis_type = params.get("analysis_type", "round_trip")
        symbol = trade_data.get("symbol", "unknown")

        if self._analyst_agent is not None and analysis_type == "round_trip":
            try:
                from .analyst_agent import TradeRecord
                import uuid
                record = TradeRecord(
                    trade_id=trade_data.get("trade_id", f"ipc_{uuid.uuid4().hex[:12]}"),
                    symbol=symbol,
                    strategy=trade_data.get("strategy", "unknown"),
                    direction=trade_data.get("direction", ""),
                    entry_price=float(trade_data.get("entry_price", 0.0)),
                    exit_price=float(trade_data.get("exit_price", 0.0)),
                    pnl=float(trade_data.get("pnl", 0.0)),
                    hold_ms=int(trade_data.get("hold_ms", 0)),
                    regime=trade_data.get("regime", "unknown"),
                    timestamp_ms=int(trade_data.get("timestamp_ms", int(time.time() * 1000))),
                    fees_paid=float(trade_data.get("fees_paid", 0.0)),
                    param_snapshot=trade_data.get("param_snapshot", {}),
                )
                # analyze_trade() is synchronous (threading.Lock inside)
                metrics = await asyncio.to_thread(self._analyst_agent.analyze_trade, record)
                rankings = []
                try:
                    rankings = await asyncio.to_thread(self._analyst_agent.get_strategy_rankings)
                except Exception:
                    pass
                # R-06-v2: persist patterns to DB for Strategist feedback loop
                # R-06-v2：寫入 DB 供 Strategist 反饋閉環
                try:
                    from .ai_service_feedback import persist_analyst_feedback
                    await asyncio.to_thread(persist_analyst_feedback, record.strategy, symbol, metrics)
                except Exception:
                    pass  # fail-open / 失敗開放
                logger.debug("Analyst C1: symbol=%s strategy=%s", symbol, record.strategy)
                return {
                    "status": "analyzed", "agent": "analyst", "symbol": symbol,
                    "analysis_type": analysis_type,
                    "observations": metrics.get("total_trades", 0),
                    "winning_patterns": [], "losing_patterns": [],
                    "regime_strategy_matrix": {}, "recommendations": [],
                    "strategy_metrics": metrics,
                    "strategy_rankings": rankings[:5],
                    "source": "analyst_agent_l1",
                }
            except Exception as exc:
                logger.warning("Analyst C1 failed, stub fallback: %s", str(exc)[:200])

        logger.debug("Analyst stub: symbol=%s type=%s", symbol, analysis_type)
        return {
            "status": "analyzed", "agent": "analyst", "symbol": symbol,
            "analysis_type": analysis_type, "observations": 0,
            "winning_patterns": [], "losing_patterns": [],
            "regime_strategy_matrix": {}, "recommendations": [],
            "source": "ai_service_stub",
        }

    async def _handle_conductor(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        R-06-v2: Forward to real Conductor for agent health + feedback loop status.
        R-06-v2：轉發到真實 Conductor 獲取 Agent 健康 + 反饋閉環狀態。
        """
        self._stats["conductor_calls"] += 1
        decision_type = params.get("decision_type", "priority")

        if self._conductor is not None:
            try:
                health = await asyncio.to_thread(self._conductor.get_agent_health)
                status = await asyncio.to_thread(self._conductor.get_status)
                # Check for degraded agents / 檢查退化的 Agent
                degraded = [k for k, v in health.items() if v.get("stale")]
                action = "scale_down" if len(degraded) > 2 else "maintain_current"
                return {
                    "status": "decided", "agent": "conductor",
                    "decision_type": decision_type, "action": action,
                    "agent_health": health,
                    "agents_running": status.get("agents_running", 0),
                    "degraded_agents": degraded,
                    "source": "conductor_real",
                }
            except Exception as exc:
                logger.warning("Conductor evaluate failed, stub fallback: %s", str(exc)[:200])

        return {
            "status": "decided", "agent": "conductor",
            "decision_type": decision_type, "action": "maintain_current",
            "source": "ai_service_stub",
        }

    async def _handle_scout(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        C2: Forward to ScoutAgent for market intelligence.
        C2：轉發到 ScoutAgent 進行市場情報收集。
        Retrieves recent intel/alerts from agent's in-memory log. Stub fallback.
        """
        self._stats["scout_calls"] += 1
        symbols = params.get("symbols", [])
        scan_type = params.get("scan_type", "full")
        limit = params.get("limit", 20)

        if self._scout_agent is not None:
            try:
                recent_intel = await asyncio.to_thread(
                    self._scout_agent.get_recent_intel, limit
                )
                recent_alerts = await asyncio.to_thread(
                    self._scout_agent.get_recent_alerts, 10
                )
                stats = await asyncio.to_thread(self._scout_agent.get_stats)

                intel_dicts = self._serialize_intel_list(recent_intel)
                alert_dicts = self._serialize_alert_list(recent_alerts)

                # Filter by requested symbols / 按請求 symbols 過濾
                if symbols:
                    sym_set = set(symbols)
                    intel_dicts = [
                        i for i in intel_dicts
                        if not i.get("symbols") or sym_set.intersection(i["symbols"])
                    ]

                logger.debug(
                    "Scout C2: intel=%d alerts=%d scans=%d",
                    len(intel_dicts), len(alert_dicts),
                    stats.get("scans_completed", 0),
                )
                return {
                    "status": "scanned", "agent": "scout",
                    "scan_type": scan_type,
                    "symbols_scanned": stats.get("scans_completed", 0),
                    "intel_objects": intel_dicts,
                    "event_alerts": alert_dicts,
                    "source": "scout_agent_live",
                }
            except Exception as exc:
                logger.warning("Scout C2 failed, stub fallback: %s", str(exc)[:200])

        logger.debug("Scout stub: symbols=%d scan_type=%s", len(symbols), scan_type)
        return {
            "status": "scanned", "agent": "scout", "scan_type": scan_type,
            "symbols_scanned": 0, "intel_objects": [], "event_alerts": [],
            "source": "ai_service_stub",
        }

    @staticmethod
    def _serialize_intel_list(intel_list: list) -> list[dict[str, Any]]:
        """Serialize IntelObject dataclasses to JSON-safe dicts. 序列化情報對象。"""
        result = []
        for intel in intel_list:
            try:
                result.append({
                    "source": intel.source,
                    "content": intel.content[:500],
                    "symbols": intel.symbols,
                    "sentiment": (
                        intel.sentiment.value if hasattr(intel.sentiment, "value")
                        else str(intel.sentiment)
                    ),
                    "relevance_score": intel.relevance_score,
                    "data_quality": (
                        intel.data_quality.value if hasattr(intel.data_quality, "value")
                        else str(intel.data_quality)
                    ),
                })
            except Exception:
                pass
        return result

    @staticmethod
    def _serialize_alert_list(alert_list: list) -> list[dict[str, Any]]:
        """Serialize EventAlert dataclasses to JSON-safe dicts. 序列化警報對象。"""
        result = []
        for alert in alert_list:
            try:
                result.append({
                    "event_type": alert.event_type,
                    "severity": (
                        alert.severity.value if hasattr(alert.severity, "value")
                        else str(alert.severity)
                    ),
                    "affected_symbols": alert.affected_symbols,
                    "description": str(getattr(alert, "description", ""))[:300],
                })
            except Exception:
                pass
        return result

    async def _handle_guardian(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Guardian L1 information layer: classify market events via Ollama.
        守衛 L1 信息層：通過 Ollama 分類市場事件。

        IMPORTANT: This is INFORMATIONAL ONLY — does NOT block trades.
        重要：這僅是信息層 — 不阻擋交易。
        Trade blocking authority stays entirely in Rust Guardian (4-check deterministic).
        交易阻擋權完全在 Rust Guardian（4 項確定性檢查）。

        Input from Rust:
          params.event = {event_type, severity, description, affected_symbols}
          params.check_type = "event_classification" (B4: informational)

        Returns: classification result with risk_level and assessment.
        返回：包含 risk_level 和 assessment 的分類結果。

        Fail-closed: Ollama unavailable → classify as severity from input (conservative).
        失敗關閉：Ollama 不可用 → 使用輸入的 severity 分類（保守）。
        """
        self._stats["guardian_calls"] += 1

        event = params.get("event", params.get("intent", {}))
        check_type = params.get("check_type", "event_classification")
        event_type = event.get("event_type", "unknown")
        severity = event.get("severity", "medium")
        description = event.get("description", "")
        affected_symbols = event.get("affected_symbols", [])
        symbol = event.get("symbol", affected_symbols[0] if affected_symbols else "unknown")

        ollama = await asyncio.to_thread(_get_ollama_client)

        # Default: use input severity as risk_level (fail-closed conservative)
        # 默認：使用輸入 severity 作為 risk_level（失敗關閉保守）
        risk_level = severity
        assessment = f"Fallback classification from input severity: {severity}"
        source = "heuristic"

        if ollama is not None and await ollama.is_available_async():
            try:
                classify_text = (
                    f"Event type: {event_type}\n"
                    f"Severity reported: {severity}\n"
                    f"Description: {description}\n"
                    f"Affected symbols: {', '.join(affected_symbols) if affected_symbols else 'unknown'}"
                )
                response = await asyncio.to_thread(
                    ollama.generate,
                    classify_text,
                    system=_GUARDIAN_SYSTEM_PROMPT,
                    temperature=0.1,
                    max_tokens=128,
                    timeout=4,
                    think=False,
                )
                if response.success:
                    parsed = self._parse_guardian_response(response.text, severity)
                    risk_level = parsed["risk_level"]
                    assessment = parsed["assessment"]
                    source = "ollama_l1"
                else:
                    logger.debug(
                        "Guardian Ollama call unsuccessful, using fallback / "
                        "守衛 Ollama 調用未成功，使用回退"
                    )
            except Exception as exc:
                logger.warning(
                    "Guardian classification error (fallback to severity): %s / "
                    "守衛分類錯誤（回退到 severity）: %s",
                    str(exc)[:100], str(exc)[:100],
                )

        logger.info(
            "Guardian L1: event=%s risk=%s source=%s / 守衛 L1：event=%s risk=%s",
            event_type, risk_level, source, event_type, risk_level,
        )

        # B4: Relay high/critical events to agents via MessageBus (informational)
        # B4：通過 MessageBus 將高/嚴重事件中繼給其他 Agent（信息用途）
        if risk_level in ("high", "critical") and self._message_bus is not None:
            try:
                from .multi_agent_framework import (
                    AgentMessage,
                    AgentRole,
                    MessageType,
                )
                alert_msg = AgentMessage(
                    sender=AgentRole.GUARDIAN,
                    receiver=AgentRole.STRATEGIST,
                    message_type=MessageType.EVENT_ALERT,
                    priority=1,
                    payload={
                        "event_type": event_type,
                        "severity": severity,
                        "risk_level": risk_level,
                        "assessment": assessment,
                        "affected_symbols": affected_symbols,
                        "source": "guardian_l1_ipc",
                    },
                )
                self._message_bus.send(alert_msg)
                logger.info(
                    "Guardian L1: relayed %s event to Strategist via MessageBus / "
                    "守衛 L1：已通過 MessageBus 將 %s 事件中繼給策略師",
                    risk_level, risk_level,
                )
            except Exception as relay_exc:
                # Fail-open: relay failure does not block classification response
                # 失敗開放：中繼失敗不阻擋分類回應
                logger.warning("Guardian MessageBus relay failed (fail-open): %s", relay_exc)

        return {
            "status": "checked",
            "agent": "guardian",
            "symbol": symbol,
            "check_type": check_type,
            "risk_level": risk_level,
            "assessment": assessment,
            "event_type": event_type,
            "affected_symbols": affected_symbols,
            "source": source,
            # NOT a trade verdict — informational only
            # 非交易裁決 — 僅信息用途
            "is_informational": True,
        }

    @staticmethod
    def _parse_guardian_response(text: str, fallback_severity: str) -> dict[str, str]:
        """Parse Ollama guardian classification response. / 解析 Ollama 守衛分類回應。"""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        valid_levels = ("low", "medium", "high", "critical")
        try:
            result = json.loads(text)
            level = str(result.get("risk_level", fallback_severity)).lower()
            if level not in valid_levels:
                level = fallback_severity
            return {
                "risk_level": level,
                "assessment": str(result.get("assessment", "AI classification"))[:200],
            }
        except (json.JSONDecodeError, AttributeError):
            # Try single-word response (like classify() output)
            # 嘗試單詞回應（類似 classify() 輸出）
            word = text.strip().lower()
            if word in valid_levels:
                return {"risk_level": word, "assessment": f"Classified as {word}"}
            return {"risk_level": fallback_severity, "assessment": f"Parse failed, fallback: {fallback_severity}"}

    # ─── Stats & introspection / 統計與自省 ───

    def get_stats(self) -> dict[str, Any]:
        """
        Return call statistics and service metadata.
        返回調用統計和服務元數據。
        """
        uptime = time.time() - self._created_at
        return {
            **self._stats,
            "uptime_seconds": round(uptime, 1),
            "last_dispatch_at": self._last_dispatch_at or None,
            "handler_count": len(self._handlers),
        }

    def get_handler_methods(self) -> list[str]:
        """List registered handler method names. / 列出已註冊的處理方法名稱。"""
        return list(self._handlers.keys())

    def get_handler_ttls(self) -> dict[str, float]:
        """Return TTL configuration for each handler. / 返回每個處理器的 TTL 配置。"""
        return dict(HANDLER_TTLS)

    def reset_stats(self) -> None:
        """Reset all call statistics to zero. / 重置所有調用統計為零。"""
        for key in self._stats:
            self._stats[key] = 0
        self._last_dispatch_at = 0.0
        logger.info("AIService stats reset")


# ═══════════════════════════════════════════════════════════════════════════════
# AIServiceListener — Unix socket IPC listener / Unix socket IPC 監聽器
# ═══════════════════════════════════════════════════════════════════════════════

def _probe_unix_listener_alive(path: str, timeout: float = 0.1) -> bool:
    """
    Non-blocking probe: does `path` have a live Unix-socket listener right now?
    非阻塞探測：當下 `path` 是否有活的 Unix socket listener？

    Returns True only on a successful connect (a peer process is accepting).
    僅在成功 connect 時回 True（有 peer process 正在 accept）。

    Any of these conditions → False (safe to bind ourselves):
      - File missing (FileNotFoundError)
      - File exists but nobody listening (ConnectionRefusedError)
      - File not a socket / permission error (OSError)
      - Connect hangs past timeout (socket.timeout)
    任一條件 → False（可安全 bind）：檔案不存在、無 listener、非 socket/權限、超時。
    """
    probe = _socket_stdlib.socket(_socket_stdlib.AF_UNIX, _socket_stdlib.SOCK_STREAM)
    try:
        probe.settimeout(timeout)
        probe.connect(path)
        return True
    except (FileNotFoundError, ConnectionRefusedError, _socket_stdlib.timeout):
        return False
    except OSError:
        return False
    finally:
        probe.close()


class AIServiceListener:
    """
    Listens on a Unix socket for incoming AI requests from the Rust engine.
    在 Unix socket 上監聽來自 Rust 引擎的 AI 請求。

    Python-side counterpart to the Rust IPC client. Protocol: length-prefixed
    JSON-RPC (4-byte big-endian u32 header + UTF-8 JSON payload).
    Rust IPC 客戶端的 Python 側對應物。協議：長度前綴 JSON-RPC。

    Request (Rust→Python): {"jsonrpc":"2.0","id":N,"method":"...","params":{...}}
    Response (Python→Rust): {"jsonrpc":"2.0","id":N,"result":{...}} or "error":{...}

    Usage: ``await listener.start()`` ... ``await listener.stop()``
    """

    def __init__(
        self,
        service: AIService,
        socket_path: str | None = None,
    ) -> None:
        self._service = service
        self._socket_path = _resolve_socket_path(socket_path)
        self._server: asyncio.AbstractServer | None = None
        self._active_connections: int = 0
        self._running: bool = False

        # Stats for the listener itself / 監聽器自身的統計
        self._listener_stats: dict[str, int] = {
            "connections_accepted": 0,
            "connections_closed": 0,
            "requests_received": 0,
            "responses_sent": 0,
            "protocol_errors": 0,
            "payload_too_large": 0,
        }

        logger.info(
            "AIServiceListener configured: socket_path=%s", self._socket_path,
        )

    # ─── Lifecycle / 生命週期 ───

    async def start(self) -> None:
        """
        Start listening on the Unix socket. Creates dir, removes stale socket.
        開始在 Unix socket 上監聽。創建目錄，移除殘留 socket。

        Multi-worker safe: under uvicorn --workers N, only one worker successfully
        binds; peers probe-detect the live listener and passively no-op.
        多 worker 安全：uvicorn --workers N 下僅一個 worker 綁定成功，其餘探測到
        活 listener 後被動跳過（不 unlink、不 bind、不告警）。
        """
        if self._running:
            logger.warning("AIServiceListener already running, ignoring start()")
            return

        # Ensure socket directory exists / 確保 socket 目錄存在
        socket_dir = os.path.dirname(self._socket_path)
        if socket_dir:
            os.makedirs(socket_dir, exist_ok=True)

        # Multi-worker guard: peer worker already serving → passive no-op.
        # 多 worker 守衛：peer worker 已在服務 → 被動跳過（不 unlink、不 bind）。
        if _probe_unix_listener_alive(self._socket_path):
            logger.info(
                "AIServiceListener: peer worker already listening at %s, "
                "running as passive worker / 另一 worker 已監聽，被動模式",
                self._socket_path,
            )
            return

        # Remove stale socket file if present / 移除殘留 socket 文件
        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass

        try:
            self._server = await asyncio.start_unix_server(
                self._handle_connection,
                path=self._socket_path,
            )
        except OSError as bind_exc:
            if bind_exc.errno == errno.EADDRINUSE:
                # Lost the narrow probe→bind race with a peer worker.
                # 與 peer worker 的窄 probe→bind 競速敗北，降級被動模式。
                logger.info(
                    "AIServiceListener: lost bind race at %s, "
                    "running as passive worker / 綁定競速敗北，被動模式",
                    self._socket_path,
                )
                return
            raise
        self._running = True
        logger.info("AIServiceListener started: %s", self._socket_path)

    async def stop(self) -> None:
        """Gracefully stop: close server, drain active connections (5s max). / 優雅停止：關閉服務器，排空連線（最多 5 秒）。"""
        if not self._running:
            logger.debug("AIServiceListener not running, ignoring stop()")
            return

        self._running = False

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Wait briefly for active connections to finish / 短暫等待活躍連線完成
        drain_deadline = time.monotonic() + 5.0
        while self._active_connections > 0 and time.monotonic() < drain_deadline:
            await asyncio.sleep(0.1)

        if self._active_connections > 0:
            logger.warning(
                "AIServiceListener stopped with %d active connections",
                self._active_connections,
            )

        # Clean up socket file / 清理 socket 文件
        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass

        logger.info("AIServiceListener stopped")

    # ─── Connection handler / 連線處理 ───

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """
        Handle a single client connection (read→dispatch→write loop).
        處理單個客戶端連線（讀取→分派→寫入循環）。
        """
        self._active_connections += 1
        self._listener_stats["connections_accepted"] += 1
        peer = "unknown"

        try:
            while self._running:
                # Read newline-delimited JSON-RPC request (matches Rust IPC protocol)
                # 讀取換行分隔的 JSON-RPC 請求（與 Rust IPC 協議一致）
                raw_line = await reader.readline()
                if not raw_line:
                    # EOF — client disconnected / 客戶端斷連
                    break

                # Validate line size / 驗證行大小
                if len(raw_line) > MAX_LINE_BYTES:
                    self._listener_stats["payload_too_large"] += 1
                    logger.error(
                        "Line too large: %d bytes > %d max",
                        len(raw_line), MAX_LINE_BYTES,
                    )
                    await self._write_error(writer, None, -32600, "payload_too_large")
                    break

                line = raw_line.strip()
                if not line:
                    continue

                self._listener_stats["requests_received"] += 1

                # Parse JSON-RPC request / 解析 JSON-RPC 請求
                try:
                    request = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as parse_err:
                    self._listener_stats["protocol_errors"] += 1
                    logger.error("JSON parse error: %s", str(parse_err)[:100])
                    await self._write_error(writer, None, -32700, "parse_error")
                    continue

                # Extract JSON-RPC fields / 提取 JSON-RPC 字段
                request_id = request.get("id")
                method = request.get("method")
                params = request.get("params", {})

                if not method:
                    self._listener_stats["protocol_errors"] += 1
                    await self._write_error(
                        writer, request_id, -32600, "missing_method",
                    )
                    continue

                # Dispatch to AIService / 分派到 AIService
                result = await self._service.dispatch(method, params)

                # Build JSON-RPC response / 構建 JSON-RPC 回應
                if "error" in result:
                    response = {
                        "jsonrpc": JSONRPC_VERSION,
                        "id": request_id,
                        "error": {
                            "code": -32000,
                            "message": result["error"],
                            "data": {
                                k: v for k, v in result.items() if k != "error"
                            },
                        },
                    }
                else:
                    response = {
                        "jsonrpc": JSONRPC_VERSION,
                        "id": request_id,
                        "result": result,
                    }

                await self._write_response(writer, response)
                self._listener_stats["responses_sent"] += 1

        except asyncio.IncompleteReadError:
            # Client disconnected — normal in IPC lifecycle
            # 客戶端斷連 — IPC 生命週期中的正常情況
            logger.debug("Client disconnected (incomplete read): peer=%s", peer)

        except ConnectionResetError:
            # Client reset — normal during shutdown
            # 客戶端重置 — 關機期間的正常情況
            logger.debug("Client connection reset: peer=%s", peer)

        except Exception as exc:
            # Unexpected error — log but don't crash
            # 意外錯誤 — 記錄但不崩潰
            logger.error(
                "Connection handler error: %s", str(exc)[:ERROR_MSG_MAX_LEN],
            )

        finally:
            self._active_connections -= 1
            self._listener_stats["connections_closed"] += 1
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    # ─── Wire protocol helpers / 線路協議輔助 ───

    async def _write_response(
        self,
        writer: asyncio.StreamWriter,
        response: dict[str, Any],
    ) -> None:
        """
        Write a newline-delimited JSON response (matches Rust IPC protocol).
        寫入換行分隔的 JSON 回應（與 Rust IPC 協議一致）。
        """
        payload = json.dumps(response, separators=(",", ":")) + "\n"
        writer.write(payload.encode("utf-8"))
        await writer.drain()

    async def _write_error(
        self,
        writer: asyncio.StreamWriter,
        request_id: int | None,
        code: int,
        message: str,
    ) -> None:
        """
        Write a JSON-RPC error response.
        寫入 JSON-RPC 錯誤回應。
        """
        response = {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": code, "message": message},
        }
        await self._write_response(writer, response)

    # ─── Listener stats / 監聽器統計 ───

    def get_listener_stats(self) -> dict[str, Any]:
        """
        Return listener-level statistics.
        返回監聽器級別的統計。
        """
        return {
            **self._listener_stats,
            "socket_path": self._socket_path,
            "running": self._running,
            "active_connections": self._active_connections,
        }

    @property
    def socket_path(self) -> str:
        """
        Return the resolved socket path.
        返回解析後的 socket 路徑。
        """
        return self._socket_path

    @property
    def is_running(self) -> bool:
        """
        Whether the listener is currently running.
        監聽器是否正在運行。
        """
        return self._running


# ═══════════════════════════════════════════════════════════════════════════════
# Factory / convenience / 工廠 / 便利函數
# ═══════════════════════════════════════════════════════════════════════════════

def create_ai_service_listener(
    socket_path: str | None = None,
) -> tuple[AIService, AIServiceListener]:
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
