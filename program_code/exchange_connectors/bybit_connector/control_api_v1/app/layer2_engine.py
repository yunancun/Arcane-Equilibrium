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
import re as _re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .layer2_types import (
    CRITIC_VERDICT_REPLAN,
    CRITIC_VERDICT_STOP,
    DEFAULT_SESSION_BUDGET_OPUS_USD,
    DEFAULT_SESSION_BUDGET_SONNET_USD,
    ENV_L2_LESSON_STORE_ENABLED,
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
from .context_distiller import ContextDistiller
from .layer2_cost_tracker import Layer2CostTracker
from .layer2_tools import TOOL_SCHEMAS, ToolExecutor
from .local_llm_factory import get_local_llm_client
from . import provider_client as _pc
# B 工作流（Reflexion critic + lesson store）：critic / 教訓庫的純邏輯層。
# 旗標預設關閉時下方 hook 全部短路，行為與原碼 byte-identical。
from . import layer2_critic as _critic
from .layer2_tools_g3_07 import is_tool_enabled as _is_flag_enabled
# D3 取證帳本：L2 Advisory Mesh Phase 1。把本 session 首個模型呼叫的完整
# （已消毒）prompt/response 落 agent.l2_calls（唯一 sanctioned 寫入口）。
from .l2_call_ledger_writer import get_l2_call_ledger_writer as _get_l2_ledger_writer
from .l2_memory_recall_context import (
    apply_memory_recall_to_prompt as _apply_memory_recall_to_prompt,
    build_context_hint as _build_memory_recall_hint,
    build_l2_memory_recall as _build_l2_memory_recall,
    with_memory_recall_audit_context as _with_memory_recall_audit_context,
)

logger = logging.getLogger(__name__)

# ── D3 PromptContract / output-schema 版本（PA 設計 §E.1）──
# 為什麼是常數：ledger 的 contract_ver / schema_ver 為 NOT NULL，記錄本次呼叫所
# 依的 prompt 契約版本與輸出 schema 版本，供日後 contract drift 時逐列追溯。
# 任何 SYSTEM_PROMPT / 輸出契約變更應 bump 對應版本。
L2_PROMPT_CONTRACT_VER = "l2_contract.v1"
L2_OUTPUT_SCHEMA_VER = "l2_schema.v1"
# P1 capability registry 尚未落地（P2 才建）；manual-trigger 呼叫歸到此 capability id。
L2_DEFAULT_CAPABILITY_ID = "l2.manual_reasoning"

# ── Precompiled word-boundary regexes for L1 triage text parsing ──
# 詞邊界正則：防止 "know" / "unknown" 等詞誤觸發否定匹配
# Word-boundary regexes: prevent false negation matches from "know", "unknown", etc.
_NEGATION_RE = _re.compile(
    r"\b(not|no|don't|doesn't|won't|isn't|aren't|cannot|can't|never|avoid)\b"
)
_POSITIVE_RE = _re.compile(
    r"\b(true|yes|worth|worthy|worthwhile|recommend|investigate|promising)\b"
)


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


L1_LOCAL_TRIAGE_PROMPT = (
    "You are a quick market triage filter. Given market context, determine if it's worth "
    "running a deeper AI analysis. Respond with JSON only:\n"
    '{"worth_investigating": true/false, "reason": "brief reason", "confidence": 0.0-1.0}\n'
    "Be conservative: only return true if there's a clear signal worth investigating."
)


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
        context_distiller: ContextDistiller | None = None,
    ):
        self._cost_tracker = cost_tracker
        self._paper_engine = paper_engine
        self._shadow_consumer = shadow_consumer
        self._context_distiller = context_distiller or ContextDistiller()
        self._session_lock = asyncio.Lock()
        self._current_session: Layer2Session | None = None

    @property
    def is_running(self) -> bool:
        return self._current_session is not None and self._current_session.state == SESSION_STATE_RUNNING

    def get_current_session(self) -> Layer2Session | None:
        return self._current_session

    # ── Provider 路由（含 tier 2/3 預算降級）───────────────────────

    def _daily_spend_pct(self) -> float:
        """回今日累計花費佔 daily_hard_cap 的比例（0.0–∞）。"""
        try:
            summary = self._cost_tracker.get_cost_summary()
            spent = float(summary.get("today", {}).get("total_usd", 0.0))
            cap = float(summary.get("budget", {}).get("daily_hard_cap_usd", 0.0))
            return (spent / cap) if cap > 0 else 0.0
        except Exception as exc:
            logger.warning("daily spend pct read failed: %s", exc)
            return 0.0

    def _resolve_effective_provider(
        self,
        *,
        base_provider: str,
        base_tier: str,
        role: str,
    ) -> tuple[str, str]:
        """
        根據 daily_spend % 與 fallback_tier2/3 config 決定 effective (provider, tier_key)。

        role:
          - "agent"  → 直接用 base_tier；fallback 觸發時用 fallback tier
          - "triage" → 不論 base_tier 是什麼，都用 effective_provider 的 cheapest tier
                       （L1 triage 與 model-upgrade triage 都應走最便宜路徑）
        """
        config = self._cost_tracker.get_config()
        pct = self._daily_spend_pct()

        # 從高到低檢查 threshold
        if pct >= float(config.fallback_tier3_threshold_pct):
            eff_provider = config.fallback_tier3_provider or base_provider
            eff_tier = config.fallback_tier3_model or base_tier
        elif pct >= float(config.fallback_tier2_threshold_pct):
            eff_provider = config.fallback_tier2_provider or base_provider
            eff_tier = config.fallback_tier2_model or base_tier
        else:
            eff_provider = base_provider
            eff_tier = base_tier

        # provider 不在 L2 白名單（如 perplexity/google/local_llm）→ 退到 anthropic
        if eff_provider not in _pc.L2_PROVIDERS:
            logger.info(
                "fallback provider %s not in L2 whitelist; routing to anthropic",
                eff_provider,
            )
            eff_provider = _pc.PROVIDER_ANTHROPIC
            if eff_tier not in _pc.PROVIDER_TIERS[_pc.PROVIDER_ANTHROPIC]:
                eff_tier = _pc.TIER_HAIKU if role == "triage" else _pc.TIER_SONNET

        # tier 與 provider 不匹配 → 跨 provider 映射
        if eff_tier not in _pc.PROVIDER_TIERS.get(eff_provider, []):
            eff_tier = _pc.map_tier_to_provider(eff_tier, eff_provider)

        # triage 角色：強制降到該 provider 的 cheapest tier
        if role == "triage":
            tiers = _pc.PROVIDER_TIERS.get(eff_provider, [])
            if tiers:
                eff_tier = min(tiers, key=lambda t: _pc.TIER_RANK.get(t, 99))

        return eff_provider, eff_tier

    async def _provider_complete(
        self,
        *,
        provider_name: str,
        tier: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        timeout: float,
    ) -> _pc.L2Response | None:
        """asyncio-friendly 包裝 + 全鏈路 fail-soft。回 None 由呼叫端決定 fallback。"""
        try:
            provider = _pc.get_provider(provider_name)
        except ValueError:
            logger.warning("unknown L2 provider: %s", provider_name)
            return None
        if not provider.is_available():
            logger.warning("L2 provider %s 不可用（SDK 缺 / key 缺）", provider_name)
            return None
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    provider.complete,
                    tier=tier,
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    timeout=timeout,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.error("L2 provider %s 呼叫超時 %ss (tier=%s)", provider_name, timeout, tier)
            return None

    # ── D3 取證帳本接線 / D3 forensic ledger wiring ──

    def _record_l2_call_to_ledger(
        self,
        *,
        session: Layer2Session,
        system_prompt: str,
        messages: list[dict[str, Any]],
        response: _pc.L2Response,
        eff_model: str,
        latency_ms: int | None,
        memory_recall: Any = None,
    ) -> None:
        """把本 session 首個模型呼叫落 agent.l2_calls（D3 唯一 sanctioned 寫入口）。

        為什麼在引擎這裡接線：layer2_engine 是真正攜帶 system_prompt + input
        context + raw response 的呼叫路徑（D3 中心缺口正是此處從不持久化）。在此
        鑄造 session 的 root l2_reply_id 並寫帳，讓今天 manual-trigger 的 L2 呼叫
        即被捕捉入庫（證明 writer reachable 非死碼）。消毒在 writer INSERT 之前跑。

        fail-soft：任何失敗（DB 不可用 / writer 異常）只記 warning，NEVER raise——
        D3 寫失敗不得阻斷 L2 session（lineage gap 由 health_monitoring 後續觀測）。
        """
        try:
            reply_id = f"l2r:{uuid.uuid4().hex[:12]}"
            # input_context：本次送模型的結構化輸入（messages）+ 提供的 tool defs。
            # 整塊在 writer 內過 redact_jsonb 消毒所有 string leaf 後才落 jsonb 欄。
            input_context: dict[str, Any] = {
                "messages": messages,
                "offered_tools": [t.get("name") for t in TOOL_SCHEMAS if isinstance(t, dict)],
            }
            input_context = _with_memory_recall_audit_context(input_context, memory_recall)
            writer = _get_l2_ledger_writer()
            # P2 wiring delta（PA 設計 §A.2）：contract_ver/schema_ver 改由 contract registry
            # 解析而非硬編。manual-trigger（l2.manual_reasoning）解析結果就是既有
            # l2_contract.v1 / l2_schema.v1（值不變，來源變 registry）→ 零回歸。lazy import
            # 避免 import cycle（l2_prompt_contract_registry import 本模塊的常數）；registry
            # 不可用時 fallback 既有常數（fail-soft，仍寫得出 D3 row）。
            contract_ver, schema_ver = L2_PROMPT_CONTRACT_VER, L2_OUTPUT_SCHEMA_VER
            try:
                from .l2_prompt_contract_registry import (  # noqa: PLC0415
                    resolve_contract_versions as _resolve_cv,
                )

                contract_ver, schema_ver = _resolve_cv(capability_id=L2_DEFAULT_CAPABILITY_ID)
            except Exception as _cv_exc:  # noqa: BLE001 — registry 不可用 → 既有常數兜底
                logger.warning(
                    "contract registry 解析失敗，fallback 既有常數（D3 仍寫得出）：%s", _cv_exc
                )
            res = writer.record_l2_call(
                l2_reply_id=reply_id,
                session_id=session.session_id,
                capability_id=L2_DEFAULT_CAPABILITY_ID,
                trigger=getattr(session, "trigger", "manual"),
                created_at=datetime.now(timezone.utc),
                model=eff_model,
                contract_ver=contract_ver,
                schema_ver=schema_ver,
                system_prompt=system_prompt,
                input_context=input_context,
                raw_response=response.text or "",
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=latency_ms,
                guard_verdict=None,
                consequential_at_creation=False,
            )
            # 只有確定落庫（含合法 skip 視為未鑄造）才把 reply_id 綁到 session，
            # 供 persist_lessons 映射 context_id；DB 不可用時 session.l2_reply_id 維持 None。
            if res.get("ok"):
                session.l2_reply_id = reply_id
        except Exception as exc:  # noqa: BLE001 — D3 寫失敗不得阻斷 session
            logger.warning("D3 ledger record skipped (fail-soft): %s", exc)

    # ── L1 Triage / L1 快速分诊 ──

    async def l1_triage(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Quick Haiku triage: is it worth running a full L2 session?
        快速 Haiku 分诊：是否值得运行完整 L2 session？
        """
        config = self._cost_tracker.get_config()

        triage_context = self._build_triage_context(context)

        try:
            # 走 provider abstraction：default_provider + tier 2/3 fallback；triage 強制 cheapest tier
            base_provider = config.default_provider or _pc.PROVIDER_ANTHROPIC
            eff_provider, eff_tier = self._resolve_effective_provider(
                base_provider=base_provider,
                base_tier=MODEL_HAIKU,
                role="triage",
            )
            response = await self._provider_complete(
                provider_name=eff_provider,
                tier=eff_tier,
                system_prompt=L1_TRIAGE_PROMPT,
                messages=[{"role": "user", "content": triage_context}],
                tools=None,
                max_tokens=256,
                timeout=60.0,
            )
            if response is None:
                # Provider 不可用 → 本地 LLM 兜底（Ollama / LM Studio）
                return await self._l1_triage_local(triage_context)

            input_tokens = response.input_tokens
            output_tokens = response.output_tokens
            try:
                cost = self._cost_tracker.get_pricing().models[eff_tier].cost_for_tokens(input_tokens, output_tokens)
            except KeyError:
                logger.warning("triage tier %s 不在 pricing table，cost=0", eff_tier)
                cost = 0.0

            try:
                result = json.loads(response.text or "{}")
            except json.JSONDecodeError:
                result = {"worth_investigating": False, "reason": "Failed to parse triage response"}

            if cost > 0:
                triage_session = Layer2Session(trigger="triage")
                self._cost_tracker.record_claude_cost(triage_session, input_tokens, output_tokens, eff_tier)

            result["triage_cost_usd"] = cost
            result["input_tokens"] = input_tokens
            result["output_tokens"] = output_tokens
            result["provider"] = eff_provider
            result["tier"] = eff_tier
            return result

        except Exception as e:
            logger.error("L1 triage error: %s", e)
            return {"worth_investigating": False, "reason": f"Triage error: {str(e)[:100]}", "error": True}

    async def _l1_triage_local(self, context: str) -> dict[str, Any]:
        """
        L1 triage via local LLM (Ollama/Qwen | LM Studio, fallback when Anthropic unavailable).
        本地 LLM L1 分诊（Anthropic 不可用时的回退路径，provider 由 LOCAL_LLM_PROVIDER 決定）。
        """
        try:
            client = get_local_llm_client()
            if not client.is_available():
                logger.warning("L1 local triage: local LLM not available / 本地 LLM 不可用")
                return {
                    "worth_investigating": False,
                    "reason": "Local LLM not available for L1 local triage",
                    "error": True,
                    "triage_cost_usd": 0.0,
                }

            # Run in thread to avoid blocking event loop
            # 在线程中运行避免阻塞事件循环
            resp = await asyncio.wait_for(
                asyncio.to_thread(
                    client.generate,
                    context,
                    system=L1_LOCAL_TRIAGE_PROMPT,
                    max_tokens=100,  # triage JSON is short; was 256
                    think=False,     # quick yes/no, no chain-of-thought needed
                    timeout=12,
                ),
                timeout=35.0,
            )

            if not resp.success:
                logger.warning("L1 local triage failed: %s", resp.error)
                return {
                    "worth_investigating": False,
                    "reason": f"Local triage error: {resp.error}",
                    "error": True,
                    "triage_cost_usd": 0.0,
                }

            # Parse response
            try:
                result = json.loads(resp.text)
            except json.JSONDecodeError:
                # Try to extract yes/no from free text
                text_lower = resp.text.lower()
                # FIX P0-7: 使用詞邊界正則，防止 "know"/"unknown" 等詞誤觸發否定
                # FIX P0-7: use word-boundary regex to avoid false matches from
                #            "know" (contains "no "), "unknown" (contains "no"), etc.
                has_negation = bool(_NEGATION_RE.search(text_lower))
                has_positive = bool(_POSITIVE_RE.search(text_lower))
                worth = has_positive and not has_negation
                result = {
                    "worth_investigating": worth,
                    "reason": resp.text[:200],
                }

            result["triage_cost_usd"] = 0.0
            result["triage_source"] = "local_ollama"
            result["triage_model"] = resp.model
            result["triage_latency_ms"] = resp.latency_ms
            logger.info(
                f"L1 local triage: worth={result.get('worth_investigating')} "
                f"model={resp.model} latency={resp.latency_ms:.0f}ms"
            )
            return result

        except asyncio.TimeoutError:
            logger.error("L1 local triage timed out / L1 本地分诊超时")
            return {
                "worth_investigating": False,
                "reason": "Local triage timed out",
                "error": True,
                "triage_cost_usd": 0.0,
            }
        except Exception as e:
            logger.error("L1 local triage error: %s", e)
            return {
                "worth_investigating": False,
                "reason": f"Local triage error: {str(e)[:100]}",
                "error": True,
                "triage_cost_usd": 0.0,
            }

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
        if self._session_lock.locked():
            session = Layer2Session(state=SESSION_STATE_FAILED)
            session.final_summary = "Another L2 session is already running"
            return session

        async with self._session_lock:
            return await self._run_session_inner(
                trigger=trigger, symbol=symbol, context=context, market_prices=market_prices,
            )

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
            base_provider = config.default_provider or _pc.PROVIDER_ANTHROPIC

            # ── B-Hook 1：lesson store 檢索（旗標開啟才跑）──
            # 為什麼只追加到 context 字串：不改 _build_user_message 內部結構，
            # 把過往教訓當作「額外脈絡」前置注入，旗標關閉時這段完全不執行。
            if _is_flag_enabled(ENV_L2_LESSON_STORE_ENABLED):
                try:
                    lessons = await _critic.retrieve_lessons(
                        symbol=symbol,
                        context_hint=context or symbol,
                    )
                    lesson_text = self._format_lessons_for_context(lessons)
                    if lesson_text:
                        context = (
                            f"{context}\n{lesson_text}" if context else lesson_text
                        )
                except Exception as exc:  # noqa: BLE001 — 檢索失敗不得阻斷 session
                    logger.warning("B-Hook lesson retrieval skipped: %s", exc)

            memory_recall = await _build_l2_memory_recall(
                symbol=symbol,
                context_hint=_build_memory_recall_hint(
                    symbol=symbol, mode=trigger, context=context or ""
                ),
            )
            user_message = self._build_user_message(symbol=symbol, context=context)
            system_prompt, user_message = _apply_memory_recall_to_prompt(
                system_prompt=SYSTEM_PROMPT,
                user_message=user_message,
                recall=memory_recall,
            )
            messages: list[dict[str, Any]] = [
                {"role": "user", "content": user_message},
            ]

            # Agent loop（每輪重新解析 effective provider/tier，允許 budget 觸發降級）
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

                # 解析本輪 effective (provider, tier_key)；budget% 越線會自動降級
                eff_provider, eff_tier = self._resolve_effective_provider(
                    base_provider=base_provider,
                    base_tier=session.current_model,
                    role="agent",
                )

                # tools 在不支援的 tier 上會被 adapter 自動 None-out（DeepSeek-reasoner）
                response = await self._provider_complete(
                    provider_name=eff_provider,
                    tier=eff_tier,
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    max_tokens=4096,
                    timeout=120.0,
                )
                if response is None:
                    session.state = SESSION_STATE_FAILED
                    session.final_summary = (
                        f"L2 provider {eff_provider} 不可用或超時（iter {iteration}）"
                    )
                    break

                # 記帳：用實際 effective tier_key（DeepSeek 走 deepseek-chat 條目）
                self._cost_tracker.record_claude_cost(
                    session, response.input_tokens, response.output_tokens, eff_tier,
                )

                # ── D3 取證帳本：捕捉本 session 首個模型呼叫的完整 prompt/response ──
                # 為什麼只記首呼叫：D3 中心缺口是「完整 prompt/response 從不持久化」；
                # 首輪攜帶 SYSTEM_PROMPT + 初始 input context + 首個 raw response，鑄造
                # session 的 root l2_reply_id 並落 agent.l2_calls（消毒在 writer INSERT 前）。
                # fail-soft：D3 寫失敗（DB 不可用等）絕不阻斷 session（writer 內已吞）。
                if session.l2_reply_id is None:
                    self._record_l2_call_to_ledger(
                        session=session,
                        system_prompt=system_prompt,
                        messages=messages,
                        response=response,
                        eff_model=eff_tier,
                        latency_ms=None,
                        memory_recall=memory_recall,
                    )

                # 記下這輪用了誰（debug / GUI 顯示）
                if not hasattr(session, "provider_chain"):
                    setattr(session, "provider_chain", [])
                session.provider_chain.append({  # type: ignore[attr-defined]
                    "iter": iteration, "provider": eff_provider, "tier": eff_tier,
                    "in_tok": response.input_tokens, "out_tok": response.output_tokens,
                })

                # 把 assistant 回應接回 messages（provider 自己決定 raw vs 合成 blocks）
                provider = _pc.get_provider(eff_provider)
                provider.append_assistant_message(messages, response)

                if response.stop_reason == "end_turn":
                    if response.text:
                        session.final_summary = response.text[:2000]
                    session.state = SESSION_STATE_COMPLETED
                    break
                if response.stop_reason != "tool_use":
                    session.state = SESSION_STATE_COMPLETED
                    session.final_summary = f"Agent stopped: {response.stop_reason}"
                    break

                # 處理 tool calls
                tool_results: list[dict[str, Any]] = []
                # B-Hook：本輪 critic 判定（None=未跑 critic 或一律 continue）。
                # 在 tool 迴圈外初始化；迴圈內以「最嚴重」聚合（stop>replan>continue，
                # 見 _critic.merge_critic_verdict），迴圈後統一處置（見 B-Hook 3）。
                # 為什麼不 last-wins：同輪某 tool 判 STOP 後又有 tool 判 CONTINUE 時，
                # last-wins 會蓋掉 STOP 而漏煞車。
                critic_result = None
                for tu in response.tool_uses:
                    call_start = time.time()
                    result_str = await executor.execute(tu.name, tu.input)
                    call_latency = (time.time() - call_start) * 1000

                    session.tool_calls.append(ToolCallRecord(
                        tool_name=tu.name,
                        input_args=tu.input,
                        output=result_str[:500] if len(result_str) > 500 else result_str,
                        latency_ms=round(call_latency, 1),
                    ))

                    # ── B-Hook 2：Reflexion critic（旗標開啟且未被 skip 才發 LLM）──
                    # should_skip_critic 內已含旗標判斷；放在 ToolCallRecord append 之後，
                    # 確保 tool-call 計數已含當前這筆。任何失敗 run_critic 回 CONTINUE。
                    try:
                        if not _critic.should_skip_critic(
                            tu.name, result_str, session, config,
                        ):
                            this_tool_verdict = await _critic.run_critic(
                                self, session, tu.name, tu.input, result_str,
                            )
                            # 以最嚴重聚合：本 tool 的判定不可降級先前已得的更嚴重判定。
                            critic_result = _critic.merge_critic_verdict(
                                critic_result, this_tool_verdict,
                            )
                    except Exception as exc:  # noqa: BLE001 — critic 不得拋進迴圈
                        logger.warning("B-Hook critic skipped: %s", exc)

                    if tu.name == TOOL_WEB_SEARCH:
                        try:
                            search_result = json.loads(result_str)
                            search_cost = search_result.get("cost_usd", 0.0)
                            if search_cost > 0:
                                self._cost_tracker.record_search_cost(
                                    session, search_result.get("provider_used", ""), search_cost,
                                )
                        except json.JSONDecodeError:
                            pass

                        # Model upgrade triage after search（沿用 Anthropic 升級語意；
                        # 跨 provider 時 _resolve_effective_provider 會 map 到對應 tier）
                        if config.allow_opus_upgrade and not session.model_upgraded:
                            should_upgrade = await self._model_upgrade_triage(
                                session, result_str,
                            )
                            if should_upgrade:
                                session.current_model = MODEL_OPUS
                                session.model_upgraded = True
                                _, fresh_remaining = self._cost_tracker.check_daily_budget()
                                session.session_budget_usd = min(
                                    self._cost_tracker.get_effective_session_budget(MODEL_OPUS),
                                    fresh_remaining,
                                )

                    tool_results.append({
                        "tool_use_id": tu.id,
                        "output_str": result_str,
                        "is_error": False,
                    })

                # 由 adapter 把 tool_results 變成 provider 對應格式（Anthropic blocks / OpenAI tool msgs）
                provider.append_tool_results(messages, tool_results)

                # ── B-Hook 3：依 critic 判定處置（旗標關閉時 critic_result 恆 None）──
                # REPLAN：只「追加」一則 user 提示，絕不 pop/改動既有 messages，
                #   讓 agent 帶著 critic note 重新規劃。
                # STOP：提早收斂為 COMPLETED（非 FAILED），break 跳出迴圈且不進
                #   else 分支（不會被標成 max-iterations）。
                # critic 永遠不能下單，至多追加訊息或收斂 session。
                if critic_result is not None:
                    try:
                        if critic_result.verdict == CRITIC_VERDICT_REPLAN:
                            messages.append({
                                "role": "user",
                                "content": f"CRITIC NOTE: {critic_result.reason}",
                            })
                        elif critic_result.verdict == CRITIC_VERDICT_STOP:
                            session.state = SESSION_STATE_COMPLETED
                            if not session.final_summary:
                                session.final_summary = (
                                    f"Critic stopped session: {critic_result.reason}"
                                )
                            break
                    except Exception as exc:  # noqa: BLE001 — 處置失敗不得阻斷迴圈
                        logger.warning("B-Hook critic verdict handling skipped: %s", exc)

            else:
                # Max iterations reached
                session.state = SESSION_STATE_COMPLETED
                session.final_summary = f"Reached max iterations ({config.max_iterations})"

        except Exception as e:
            logger.error("L2 session error: %s", e)
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

        # ── B-Hook 4：lesson store 落庫（旗標開啟才寫）──
        # 把本 session 的 insight 落為 agent.lessons row。session.insights 已在
        # finally 區塊填好；symbol 取 run_session 參數。寫入失敗 fail-soft，
        # 不影響 session 回傳。旗標關閉時完全不執行（無 DB 寫入）。
        if _is_flag_enabled(ENV_L2_LESSON_STORE_ENABLED):
            try:
                await _critic.persist_lessons(session.insights, session, symbol)
            except Exception as exc:  # noqa: BLE001 — 落庫失敗不得阻斷回傳
                logger.warning("B-Hook lesson persist skipped: %s", exc)

        return session

    # ── Model Upgrade Triage / 模型升级判断 ──

    async def _model_upgrade_triage(
        self,
        session: Layer2Session,
        search_results_str: str,
    ) -> bool:
        """
        用 cheapest tier 判斷是否值得從 sonnet → opus 升級。
        走 provider abstraction（與 default_provider 同；triage role 強制最便宜 tier）。
        """
        try:
            config = self._cost_tracker.get_config()
            base_provider = config.default_provider or _pc.PROVIDER_ANTHROPIC
            eff_provider, eff_tier = self._resolve_effective_provider(
                base_provider=base_provider,
                base_tier=MODEL_HAIKU,
                role="triage",
            )
            triage_input = f"Search results:\n{search_results_str[:3000]}"
            response = await self._provider_complete(
                provider_name=eff_provider,
                tier=eff_tier,
                system_prompt=MODEL_UPGRADE_TRIAGE_PROMPT,
                messages=[{"role": "user", "content": triage_input}],
                tools=None,
                max_tokens=256,
                timeout=60.0,
            )
            if response is None:
                return False

            try:
                self._cost_tracker.record_claude_cost(
                    session, response.input_tokens, response.output_tokens, eff_tier,
                )
            except KeyError:
                logger.warning("upgrade triage tier %s 不在 pricing table", eff_tier)

            try:
                result = json.loads(response.text or "{}")
                upgrade = result.get("upgrade_to_opus", False)
                if upgrade:
                    session.upgrade_reason = result.get("reason", "haiku_triage_recommended")
                    logger.info("Model upgrade: → Opus. Reason: %s", session.upgrade_reason)
                return upgrade
            except json.JSONDecodeError:
                return False

        except Exception as e:
            logger.warning("Model upgrade triage error: %s", e)
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
            logger.info("Recommendation confidence %s below threshold %s", rec.confidence, config.confidence_threshold)
            return
        if rec.edge_bps < config.edge_threshold_bps:
            logger.info("Recommendation edge %sbps below threshold %sbps", rec.edge_bps, config.edge_threshold_bps)
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

        # Consume decision — ShadowDecisionConsumer.consume is async (1C-3-F).
        try:
            consumption = await self._shadow_consumer.consume(decision, market_prices)
            session.shadow_decision_id = decision["decision_id"]
            session.paper_order_id = consumption.get("order_id")
            logger.info(
                "L2 session %s → shadow decision %s → order %s",
                session.session_id, decision["decision_id"], consumption.get("order_id"),
            )
        except Exception as e:
            logger.error("Paper submission error: %s", e)

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
            compact_context = self._context_distiller.distill_for_prompt(context, max_chars=2000)
            parts.insert(1, f"Additional context: {compact_context}")
        return "\n".join(parts)

    @staticmethod
    def _format_lessons_for_context(lessons: list[dict[str, Any]]) -> str:
        """
        把撈回的教訓格式化為一段精簡文字（B-Hook 1 用，唯讀）。

        為什麼是 staticmethod 且 bounded：教訓只是「額外脈絡」，最多取 5 條、
        每條截斷，避免吃掉 prompt 預算；空 list 回空字串（呼叫端不會注入）。
        """
        if not lessons:
            return ""
        lines = ["Past lessons (most relevant first):"]
        for item in lessons[:5]:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            lines.append(f"- {content[:240]}")
        # 只有標題沒有任何有效 content → 視為無教訓。
        return "\n".join(lines) if len(lines) > 1 else ""

    def _build_triage_context(self, context: dict[str, Any] | None = None) -> str:
        """Build the bounded L1 triage context payload."""
        triage_context = "Current market context:\n"
        if context:
            triage_context += self._context_distiller.distill_for_prompt(context, max_chars=2000)
        else:
            triage_context += (
                "No specific context provided. Check if general conditions warrant investigation."
            )
        return triage_context

    def update_context_after_cycle(self, cycle_data: dict[str, Any]) -> None:
        """Update the cached ContextDistiller summary from a runtime cycle."""
        self._context_distiller.update_after_each_cycle(cycle_data)


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
