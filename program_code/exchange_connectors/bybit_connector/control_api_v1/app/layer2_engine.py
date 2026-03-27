from __future__ import annotations

"""
Layer 2 AI Reasoning Engine — Core Agent Loop / 核心 Agent 循环
三层架构中的 L2 深度推理引擎：Agent 循环 + 模型升级判断 + Shadow Decision 集成

MODULE_NOTE (中文):
  本模块实现 Layer 2 AI 推理引擎的核心 Agent 循环：
  1. L1 Haiku triage — 快速判断"值得深入吗？"（~$0.01）
  2. L2 Sonnet/Opus Agent 循环 — 调用工具、搜索、迭代推理
  3. 搜索后模型升级判断 — Haiku triage 决定是否从 Sonnet 升级到 Opus
  4. submit_recommendation → build_shadow_decision → ShadowDecisionConsumer → Paper Order
  5. PnL 归因回填 → 自适应预算调整

  安全保证：
  - 全程 is_simulated=True / lease_mode=shadow_only
  - system_mode / execution_state / execution_authority 不可改变
  - 并发控制：同一时间仅一个 L2 session
  - Session 预算 + 每日硬上限双重限制

MODULE_NOTE (English):
  Core agent loop for the Layer 2 AI Reasoning Engine:
  1. L1 Haiku triage — quick "worth investigating?" check (~$0.01)
  2. L2 Sonnet/Opus agent loop — call tools, search, iterative reasoning
  3. Post-search model upgrade judgment — Haiku triage decides Sonnet → Opus
  4. submit_recommendation → build_shadow_decision → ShadowDecisionConsumer → Paper Order
  5. PnL attribution backfill → adaptive budget adjustment

  Safety guarantees:
  - Always is_simulated=True / lease_mode=shadow_only
  - system_mode / execution_state / execution_authority unchanged
  - Concurrency control: only one L2 session at a time
  - Session budget + daily hard cap dual enforcement
"""

import asyncio
import hashlib
import json
import logging
import threading
import time
from typing import Any

from .layer2_types import (
    DEFAULT_SESSION_BUDGET_OPUS_USD,
    DEFAULT_SESSION_BUDGET_SONNET_USD,
    MAX_AGENT_ITERATIONS,
    MODEL_HAIKU,
    MODEL_IDS,
    MODEL_OPUS,
    MODEL_SONNET,
    SESSION_STATE_BUDGET_EXCEEDED,
    SESSION_STATE_COMPLETED,
    SESSION_STATE_FAILED,
    SESSION_STATE_RUNNING,
    TOOL_SUBMIT_RECOMMENDATION,
    TOOL_WEB_SEARCH,
    Insight,
    Layer2Config,
    Layer2Session,
    Recommendation,
    ToolCallRecord,
)
from .layer2_cost_tracker import Layer2CostTracker
from .layer2_tools import TOOL_SCHEMAS, ToolExecutor

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# System Prompt / 系统提示词
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are the Layer 2 AI Reasoning Engine for the OpenClaw trading system.
Your role is to analyze crypto market conditions and generate trade recommendations for the paper trading system.

## Your Capabilities
- Read current market state (observer verdicts, prices)
- Read paper trading account state (positions, balance, PnL)
- Review recent shadow decisions and their outcomes
- Query the learning system for accumulated experience
- Search the web for recent news and market events
- Fetch detailed articles from URLs
- Submit structured trade recommendations
- Record market insights for the learning system

## Important Rules
1. ALL recommendations are for PAPER TRADING only (simulated, not real money)
2. Always check market data freshness before making decisions
3. Distinguish clearly between facts, inferences, and hypotheses
4. Consider costs — your API calls cost real money, be efficient
5. Use web_search when you need current information (news, events, prices)
6. Submit a recommendation ONLY when you have sufficient evidence
7. If the situation is unclear, recommend "hold" with your reasoning
8. Record notable insights for the learning system even if you don't trade
9. Consider recent shadow decision history to avoid redundant or conflicting signals
10. Always factor in fees (taker 0.055%, maker 0.02%) and slippage (0.05%) in edge calculations

## Output Format
Call submit_recommendation when ready with: action, symbol, confidence (0-1), edge_bps, reasoning.
Call record_insight for notable observations that should be remembered.
If you cannot form a recommendation, explain why in your final message.

## Current Context
This is a paper trading session. system_mode=read_only, execution_authority=not_granted.
All trades are simulated. Focus on learning and signal quality."""


L1_TRIAGE_PROMPT = """You are a quick triage filter for the OpenClaw trading system.
Given the current market context, answer ONLY with a JSON object:
{"worth_investigating": true/false, "reason": "brief explanation", "suggested_focus": "what to investigate"}

Criteria for worth_investigating=true:
- Significant price movement (>2% in 24h)
- Notable news or events affecting crypto markets
- Current positions that need attention (unrealized PnL change)
- Learning system has untested hypotheses relevant to current conditions
- It's been >4 hours since last L2 session

Criteria for worth_investigating=false:
- Market is calm and range-bound
- No relevant news or events
- Recent L2 session already covered this scenario
- System health issues suggest caution"""


MODEL_UPGRADE_TRIAGE_PROMPT = """You are a model upgrade decision filter.
Based on the search results the agent just retrieved, decide if we should upgrade from Sonnet to Opus.

Answer ONLY with a JSON object:
{"upgrade_to_opus": true/false, "reason": "brief explanation"}

Upgrade criteria (need at least one):
- Major macroeconomic event (rate decisions, regulatory actions, major hacks)
- Search results contain contradictory information that needs deep analysis
- Multiple correlated factors require cross-domain reasoning
- Current position is large (>5% of portfolio) and at risk
- Novel market regime not seen in recent experience

Do NOT upgrade for:
- Routine market movements
- Simple trend continuation
- Low-confidence signals where more data wouldn't help"""


# ═══════════════════════════════════════════════════════════════════════════════
# Engine / 引擎
# ═══════════════════════════════════════════════════════════════════════════════

class Layer2Engine:
    """
    Core Layer 2 AI Reasoning Engine.
    Layer 2 AI 推理引擎核心。
    """

    def __init__(
        self,
        cost_tracker: Layer2CostTracker,
        paper_engine: Any = None,
        shadow_consumer: Any = None,
    ):
        self._cost_tracker = cost_tracker
        self._paper_engine = paper_engine
        self._shadow_consumer = shadow_consumer
        self._session_lock = threading.Lock()
        self._current_session: Layer2Session | None = None

    @property
    def is_running(self) -> bool:
        return self._current_session is not None and self._current_session.state == SESSION_STATE_RUNNING

    def get_current_session(self) -> Layer2Session | None:
        return self._current_session

    # ── L1 Triage / L1 快速分诊 ──

    async def l1_triage(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Quick Haiku triage: is it worth running a full L2 session?
        快速 Haiku 分诊：是否值得运行完整 L2 session？
        """
        config = self._cost_tracker.get_config()

        # Build triage context
        triage_context = "Current market context:\n"
        if context:
            triage_context += json.dumps(context, ensure_ascii=False, indent=2)[:2000]
        else:
            triage_context += "No specific context provided. Check if general conditions warrant investigation."

        try:
            client = _get_anthropic_client()
            if client is None:
                return {"worth_investigating": False, "reason": "Anthropic client not available", "error": True}

            # Add timeout to prevent hanging / 添加超时防止挂起
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.messages.create,
                    model=MODEL_IDS[MODEL_HAIKU],
                    max_tokens=256,
                    system=L1_TRIAGE_PROMPT,
                    messages=[{"role": "user", "content": triage_context}],
                ),
                timeout=60.0,  # 1 minute for triage
            )

            # Track cost
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cost = self._cost_tracker.get_pricing().models[MODEL_HAIKU].cost_for_tokens(input_tokens, output_tokens)

            # Parse response
            text = response.content[0].text if response.content else "{}"
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                result = {"worth_investigating": False, "reason": "Failed to parse triage response"}

            result["triage_cost_usd"] = cost
            result["input_tokens"] = input_tokens
            result["output_tokens"] = output_tokens
            return result

        except asyncio.TimeoutError:
            logger.error("L1 triage timed out after 60s / L1 分诊超时")
            return {"worth_investigating": False, "reason": "Triage timed out after 60s", "error": True}
        except Exception as e:
            logger.error(f"L1 triage error: {e}")
            return {"worth_investigating": False, "reason": f"Triage error: {str(e)[:100]}", "error": True}

    # ── L2 Agent Loop / L2 Agent 循环 ──

    async def run_session(
        self,
        *,
        trigger: str = "manual",
        symbol: str = "BTCUSDT",
        context: str = "",
        market_prices: dict[str, float] | None = None,
    ) -> Layer2Session:
        """
        Run a complete L2 reasoning session.
        运行一次完整的 L2 推理 session。
        """
        if not self._session_lock.acquire(blocking=False):
            session = Layer2Session(state=SESSION_STATE_FAILED)
            session.final_summary = "Another L2 session is already running"
            return session

        try:
            return await self._run_session_inner(
                trigger=trigger, symbol=symbol, context=context, market_prices=market_prices,
            )
        finally:
            self._session_lock.release()

    async def _run_session_inner(
        self,
        *,
        trigger: str,
        symbol: str,
        context: str,
        market_prices: dict[str, float] | None,
    ) -> Layer2Session:
        config = self._cost_tracker.get_config()

        # Budget check
        allowed, remaining = self._cost_tracker.check_daily_budget()
        if not allowed:
            session = Layer2Session(state=SESSION_STATE_BUDGET_EXCEEDED)
            session.final_summary = "Daily budget exceeded"
            return session

        # Create session
        session = Layer2Session(
            trigger=trigger,
            initial_model=config.default_model,
            current_model=config.default_model,
            session_budget_usd=self._cost_tracker.get_effective_session_budget(config.default_model),
        )
        session.state = SESSION_STATE_RUNNING
        session.started_at_ms = int(time.time() * 1000)
        self._current_session = session

        # Create tool executor
        executor = ToolExecutor(
            paper_engine=self._paper_engine,
            shadow_consumer=self._shadow_consumer,
            search_providers=config.search_providers_enabled,
            search_max_results=config.search_max_results,
        )

        try:
            client = _get_anthropic_client()
            if client is None:
                session.state = SESSION_STATE_FAILED
                session.final_summary = "Anthropic client not available (ANTHROPIC_API_KEY not set)"
                return session

            # Build initial user message
            user_message = self._build_user_message(symbol=symbol, context=context)

            messages: list[dict[str, Any]] = [
                {"role": "user", "content": user_message},
            ]

            # Agent loop
            for iteration in range(config.max_iterations):
                session.iterations = iteration + 1

                # Budget check
                if not self._cost_tracker.check_session_budget(session):
                    session.state = SESSION_STATE_BUDGET_EXCEEDED
                    session.final_summary = f"Session budget exceeded after {iteration} iterations"
                    break

                if not self._cost_tracker.check_daily_hard_cap():
                    session.state = SESSION_STATE_BUDGET_EXCEEDED
                    session.final_summary = "Daily hard cap reached during session"
                    break

                # Call Claude (with timeout to prevent hanging)
                # 调用 Claude（带超时防止挂起）
                model_id = MODEL_IDS.get(session.current_model, MODEL_IDS[MODEL_SONNET])
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.messages.create,
                            model=model_id,
                            max_tokens=4096,
                            system=SYSTEM_PROMPT,
                            tools=TOOL_SCHEMAS,
                            messages=messages,
                        ),
                        timeout=120.0,  # 2 minute timeout per iteration
                    )
                except asyncio.TimeoutError:
                    logger.error("L2 Claude call timed out after 120s (iteration %d) / L2 Claude 调用超时", iteration)
                    session.state = SESSION_STATE_FAILED
                    session.final_summary = f"Claude API call timed out after 120s at iteration {iteration}"
                    break

                # Track tokens & cost
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                self._cost_tracker.record_claude_cost(session, input_tokens, output_tokens, session.current_model)

                # Process response
                assistant_content = response.content
                stop_reason = response.stop_reason

                # Build assistant message
                messages.append({"role": "assistant", "content": assistant_content})

                if stop_reason == "end_turn":
                    # Agent finished — extract final text
                    for block in assistant_content:
                        if hasattr(block, "text"):
                            session.final_summary = block.text[:2000]
                    session.state = SESSION_STATE_COMPLETED
                    break

                if stop_reason != "tool_use":
                    session.state = SESSION_STATE_COMPLETED
                    session.final_summary = "Agent stopped without tool use"
                    break

                # Process tool calls
                tool_results: list[dict[str, Any]] = []
                for block in assistant_content:
                    if block.type != "tool_use":
                        continue

                    tool_name = block.name
                    tool_input = block.input
                    tool_id = block.id

                    call_start = time.time()
                    result_str = await executor.execute(tool_name, tool_input)
                    call_latency = (time.time() - call_start) * 1000

                    # Record tool call
                    tc = ToolCallRecord(
                        tool_name=tool_name,
                        input_args=tool_input,
                        output=result_str[:500] if len(result_str) > 500 else result_str,
                        latency_ms=round(call_latency, 1),
                    )
                    session.tool_calls.append(tc)

                    # Track search costs
                    if tool_name == TOOL_WEB_SEARCH:
                        try:
                            search_result = json.loads(result_str)
                            search_cost = search_result.get("cost_usd", 0.0)
                            if search_cost > 0:
                                self._cost_tracker.record_search_cost(
                                    session, search_result.get("provider_used", ""), search_cost,
                                )
                        except json.JSONDecodeError:
                            pass

                        # Model upgrade triage after search
                        if config.allow_opus_upgrade and not session.model_upgraded:
                            should_upgrade = await self._model_upgrade_triage(
                                session, result_str, client,
                            )
                            if should_upgrade:
                                session.current_model = MODEL_OPUS
                                session.model_upgraded = True
                                # Re-check daily budget at upgrade time (stale `remaining` from session start)
                                # 升级时重新检查每日预算（session 开始时的 remaining 可能已过时）
                                _, fresh_remaining = self._cost_tracker.check_daily_budget()
                                session.session_budget_usd = min(
                                    self._cost_tracker.get_effective_session_budget(MODEL_OPUS),
                                    fresh_remaining,
                                )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result_str,
                    })

                messages.append({"role": "user", "content": tool_results})

            else:
                # Max iterations reached
                session.state = SESSION_STATE_COMPLETED
                session.final_summary = f"Reached max iterations ({config.max_iterations})"

        except Exception as e:
            logger.error(f"L2 session error: {e}")
            session.state = SESSION_STATE_FAILED
            session.final_summary = f"Error: {str(e)[:500]}"
        finally:
            session.completed_at_ms = int(time.time() * 1000)
            session.recommendation = executor.recommendation
            session.insights = executor.insights
            self._current_session = None

        # Post-session: submit to paper trading if applicable
        if session.recommendation and config.auto_submit_to_paper:
            await self._submit_to_paper(session, market_prices or {})

        # Record session
        self._cost_tracker.record_session(session)

        return session

    # ── Model Upgrade Triage / 模型升级判断 ──

    async def _model_upgrade_triage(
        self,
        session: Layer2Session,
        search_results_str: str,
        client: Any,
    ) -> bool:
        """
        Use Haiku to decide if Sonnet should be upgraded to Opus.
        使用 Haiku 快速判断是否从 Sonnet 升级到 Opus。
        """
        try:
            triage_input = f"Search results:\n{search_results_str[:3000]}"

            # Add timeout to prevent hanging / 添加超时防止挂起
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.messages.create,
                    model=MODEL_IDS[MODEL_HAIKU],
                    max_tokens=256,
                    system=MODEL_UPGRADE_TRIAGE_PROMPT,
                    messages=[{"role": "user", "content": triage_input}],
                ),
                timeout=60.0,  # 1 minute for upgrade triage
            )

            # Track cost
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            self._cost_tracker.record_claude_cost(session, input_tokens, output_tokens, MODEL_HAIKU)

            text = response.content[0].text if response.content else "{}"
            try:
                result = json.loads(text)
                upgrade = result.get("upgrade_to_opus", False)
                if upgrade:
                    session.upgrade_reason = result.get("reason", "haiku_triage_recommended")
                    logger.info(f"Model upgrade: Sonnet → Opus. Reason: {session.upgrade_reason}")
                return upgrade
            except json.JSONDecodeError:
                return False

        except Exception as e:
            logger.warning(f"Model upgrade triage error: {e}")
            return False

    # ── Paper Trading Integration / 纸上交易集成 ──

    async def _submit_to_paper(
        self,
        session: Layer2Session,
        market_prices: dict[str, float],
    ) -> None:
        """
        Convert recommendation to shadow decision and submit to paper trading.
        将推荐转化为影子决策并提交到纸上交易。
        """
        if session.recommendation is None:
            return
        if self._shadow_consumer is None:
            logger.info("Shadow consumer not available, skipping paper submission")
            return

        rec = session.recommendation

        # Skip hold recommendations
        if rec.action == "hold":
            return

        config = self._cost_tracker.get_config()
        if rec.confidence < config.confidence_threshold:
            logger.info(f"Recommendation confidence {rec.confidence} below threshold {config.confidence_threshold}")
            return
        if rec.edge_bps < config.edge_threshold_bps:
            logger.info(f"Recommendation edge {rec.edge_bps}bps below threshold {config.edge_threshold_bps}bps")
            return

        # Map recommendation to governed_observation for shadow decision builder
        from .shadow_decision_builder import build_shadow_decision

        # Map action to bias
        action_to_bias = {
            "buy": "buy_bias",
            "sell": "sell_bias",
            "close_long": "sell_bias",
            "close_short": "buy_bias",
        }
        bias = action_to_bias.get(rec.action, "flat_bias")

        governed_observation = {
            "market_regime": "layer2_analyzed",
            "action_bias": bias,
            "confidence_0_to_1": rec.confidence,
            "edge_assessment_bps": rec.edge_bps,
            "key_reasons": [rec.reasoning[:200]],
            "risk_notes": rec.risk_factors[:3],
            "why_not_trade": [],
            "analysis_mode": "layer2_agentic",
        }

        decision = build_shadow_decision(
            governed_observation=governed_observation,
            market_prices=market_prices,
            symbol=rec.symbol,
        )

        # Consume decision
        try:
            consumption = self._shadow_consumer.consume(decision, market_prices)
            session.shadow_decision_id = decision["decision_id"]
            session.paper_order_id = consumption.get("order_id")
            logger.info(
                "L2 session %s → shadow decision %s → order %s",
                session.session_id, decision["decision_id"], consumption.get("order_id"),
            )
        except Exception as e:
            logger.error(f"Paper submission error: {e}")

    # ── Helper / 辅助 ──

    def _build_user_message(self, *, symbol: str, context: str) -> str:
        """Build the initial user message for the agent / 构建 Agent 的初始用户消息"""
        parts = [
            f"Analyze the current market conditions for {symbol} and determine if there's a trading opportunity.",
            "",
            "Available tools: get_market_state, get_account_state, get_recent_decisions, get_experience, web_search, fetch_url, submit_recommendation, record_insight",
            "",
            "Start by checking the current market state and account state, then decide if web search for recent news is warranted.",
        ]
        if context:
            parts.insert(1, f"Additional context: {context}")
        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# Anthropic Client / Anthropic 客户端
# ═══════════════════════════════════════════════════════════════════════════════

_anthropic_client = None
_client_lock = threading.Lock()


def _get_anthropic_client() -> Any:
    """Get or create Anthropic client (singleton) / 获取或创建 Anthropic 客户端（单例）"""
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client

    with _client_lock:
        if _anthropic_client is not None:
            return _anthropic_client
        try:
            import anthropic
            import os
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY not set, Layer 2 engine will not function")
                return None
            _anthropic_client = anthropic.Anthropic(api_key=api_key)
            return _anthropic_client
        except ImportError:
            logger.warning("anthropic package not installed")
            return None


def reset_anthropic_client() -> None:
    """Reset client (for testing) / 重置客户端（用于测试）"""
    global _anthropic_client
    with _client_lock:
        _anthropic_client = None
