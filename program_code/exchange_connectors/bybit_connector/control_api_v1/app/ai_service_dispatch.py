"""
ai_service_dispatch — AIService core class (split from ai_service.py per §九 1200-line cap)
==========================================================================================
Governance refs: DOC-04 §G Multi-Agent, Rust Migration R-01

MODULE_NOTE (EN/中):
  Sibling module of ``ai_service``. Hosts the ``AIService`` class which dispatches
  Rust engine JSON-RPC requests to the 5 Agent handlers (Strategist/Analyst/
  Conductor/Scout/Guardian) and returns structured responses.
  ``ai_service`` 的姊妹模組。承載 ``AIService`` 類，分派 Rust 引擎 JSON-RPC 請求到 5
  個 Agent 處理器，回傳結構化結果。

  Per-handler TTL: strategist=15s, analyst=30s, conductor=10s, scout=10s, guardian=5s.
  Safety: fail-closed, error msgs truncated to 200 chars, no hardcoded paths.
  安全：fail-closed，錯誤截斷 200 字符，路徑不硬編碼。

  This file is purely a structural extraction — no logic changes.
  External callers should keep importing from ``app.ai_service`` (re-export preserved).
  此檔僅做結構性拆分，不改邏輯；外部仍應從 ``app.ai_service`` 匯入（保留 re-export）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Callable

from . import ai_service as core
from . import ai_service_guardian

logger = logging.getLogger(__name__)


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
            # G3-08 Phase 1 Sub-task B: reverse IPC route for Rust h_state_cache
            # poller. Always registered (route reachable regardless of env-gate)
            # — only the Python-side invalidator + Rust-side poller daemon are
            # gated by ``OPENCLAW_H_STATE_GATEWAY``. Phase 1 returns an empty
            # shell; Phase 2-4 progressively populate H1-H5 + 5-Agent stats.
            # G3-08 Phase 1 Sub-task B：Rust h_state_cache poller 的 reverse IPC
            # 路由。**永遠註冊**（route 不受 env 閘控可達）—— 只有 Python 端
            # invalidator 與 Rust 端 poller daemon 受 ``OPENCLAW_H_STATE_GATEWAY``
            # 閘控。Phase 1 回空殼；Phase 2-4 逐步填入 H1-H5 + 5-Agent 統計。
            "query_h_state_full": self._handle_query_h_state_full,
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

        ttl = core.HANDLER_TTLS.get(method, 15.0)
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
            error_msg = str(exc)[:core.ERROR_MSG_MAX_LEN]
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

        ollama = await asyncio.to_thread(core._get_ollama_client)

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
                system=core._STRATEGIST_SYSTEM_PROMPT,
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
                str(exc)[:core.ERROR_MSG_MAX_LEN], str(exc)[:core.ERROR_MSG_MAX_LEN],
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
        """Guardian L1 information layer. / Guardian L1 信息層。"""
        return await ai_service_guardian.handle_guardian(self, params)

    @staticmethod
    def _parse_guardian_response(text: str, fallback_severity: str) -> dict[str, str]:
        """Parse Ollama guardian classification response. / 解析 Ollama 守衛分類回應。"""
        return ai_service_guardian.parse_guardian_response(text, fallback_severity)

    # ─── G3-08 Phase 1 Sub-task B: H-state reverse IPC handler ───
    # G3-08 Phase 1 Sub-task B：H 狀態 reverse IPC 處理器

    async def _handle_query_h_state_full(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Reverse IPC handler for Rust ``h_state_cache`` poller.
        Rust ``h_state_cache`` poller 的 reverse IPC 處理器。

        Phase 1 always returns the empty-shell shape from
        :func:`h_state_query_handler.build_h_state_full_response`. Phase 2-4
        populate progressively. The handler is registered unconditionally —
        only the Python-side invalidator + Rust-side poller daemon are gated
        by ``OPENCLAW_H_STATE_GATEWAY`` (per PA design §10.1 completion
        criteria).

        Phase 1 永遠回 :func:`h_state_query_handler.build_h_state_full_response`
        定義的空殼結構；Phase 2-4 漸進填入。本 handler **無條件註冊**，
        只有 Python 端 invalidator 與 Rust 端 poller daemon 受
        ``OPENCLAW_H_STATE_GATEWAY`` 閘控（PA design §10.1 完成標準）。

        Pure-function path — never raises. Lazy import of
        ``h_state_query_handler`` to avoid bootstrap cycles in test fixtures.
        純函式路徑，永不 raise。延遲匯入 ``h_state_query_handler`` 以避免
        測試 fixture 中的 bootstrap 循環。
        """
        include = params.get("include") if isinstance(params, dict) else None
        if include is not None and not isinstance(include, list):
            # Defensive: ignore malformed ``include`` payloads. Don't raise —
            # the Rust caller treats a stale/empty response as "skip this poll".
            # 防禦：忽略畸形 ``include``；Rust 呼叫端視空/過時回應為「跳過此 poll」。
            include = None
        # Lazy import keeps this module importable even when the H-state
        # query handler is absent (e.g. during partial Phase 1 deploy).
        # 延遲匯入：即使 H 狀態查詢 handler 缺席（如 Phase 1 部分部署）
        # 本模組仍可匯入。
        from .h_state_query_handler import build_h_state_full_response  # noqa: PLC0415
        result = build_h_state_full_response(include=include)
        # AIService.dispatch wraps response with ``_elapsed_ms``; we just
        # return the payload. Per PA §4.2.1 schema.
        # AIService.dispatch 會包 ``_elapsed_ms``；此處只回 payload，對齊
        # PA §4.2.1 schema。
        return result

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
        return dict(core.HANDLER_TTLS)

    def reset_stats(self) -> None:
        """Reset all call statistics to zero. / 重置所有調用統計為零。"""
        for key in self._stats:
            self._stats[key] = 0
        self._last_dispatch_at = 0.0
        logger.info("AIService stats reset")
