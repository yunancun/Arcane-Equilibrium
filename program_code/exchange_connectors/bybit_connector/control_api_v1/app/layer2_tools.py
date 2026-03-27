from __future__ import annotations

"""
Layer 2 AI Reasoning Engine — Agent Tools / Agent 工具
8 个 Agent 工具的 Anthropic schema 定义、执行器、4 个 SearchProvider 实现

MODULE_NOTE (中文):
  本模块实现 Layer 2 Agent 循环中可用的 8 个工具：
  数据读取（零外部调用）：get_market_state / get_account_state / get_recent_decisions / get_experience
  外部信息（SearchProvider 抽象）：web_search / fetch_url
  输出：submit_recommendation / record_insight

  4 层 SearchProvider 降级体系：
  1. Perplexity Search API + Claude 推理（带引用+时间戳，~$0.005/次）
  2. 本地 LLM (Ollama) + web-pilot（零 API 成本）
  3. 本地 LLM 搜索（零 API 成本）
  4. DuckDuckGo（零成本兜底）

MODULE_NOTE (English):
  Implements 8 tools available in the Layer 2 Agent loop:
  Data reads (zero external calls): get_market_state / get_account_state / get_recent_decisions / get_experience
  External info (SearchProvider abstraction): web_search / fetch_url
  Outputs: submit_recommendation / record_insight

  4-tier SearchProvider degradation:
  1. Perplexity Search API + Claude reasoning (citations+timestamps, ~$0.005/query)
  2. Local LLM (Ollama) + web-pilot (zero API cost)
  3. Local LLM search (zero API cost)
  4. DuckDuckGo (zero cost fallback)
"""

import json
import logging
import os
import subprocess
import time
from typing import Any

from .layer2_types import (
    SEARCH_PROVIDER_LOCAL_LLM,
    SEARCH_PROVIDER_LOCAL_LLM_WEB,
    SEARCH_PROVIDER_PERPLEXITY,
    SEARCH_PROVIDER_WEBPILOT,
    TOOL_FETCH_URL,
    TOOL_GET_ACCOUNT_STATE,
    TOOL_GET_EXPERIENCE,
    TOOL_GET_MARKET_STATE,
    TOOL_GET_RECENT_DECISIONS,
    TOOL_RECORD_INSIGHT,
    TOOL_SUBMIT_RECOMMENDATION,
    TOOL_WEB_SEARCH,
    Insight,
    Recommendation,
    SearchProvider,
    SearchResponse,
    SearchResult,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Anthropic Tool Schemas (for messages API) / Anthropic 工具 schema
# ═══════════════════════════════════════════════════════════════════════════════

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": TOOL_GET_MARKET_STATE,
        "description": (
            "Get current market state including observer verdict, microstructure analysis, "
            "and latest prices. Zero cost, reads local data only. "
            "获取当前市场状态，包括 observer verdict、微结构分析与最新价格。零成本，仅读本地数据。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading symbol, e.g. BTCUSDT",
                    "default": "BTCUSDT",
                },
            },
            "required": [],
        },
    },
    {
        "name": TOOL_GET_ACCOUNT_STATE,
        "description": (
            "Get paper trading account state including positions, balance, PnL, and recent orders. "
            "Zero cost, reads paper trading engine state. "
            "获取纸上交易账户状态，包括持仓、余额、PnL 和近期订单。零成本，读取 paper trading 引擎状态。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": TOOL_GET_RECENT_DECISIONS,
        "description": (
            "Get recent shadow decisions and their outcomes. "
            "Useful for understanding recent trading signals and their accuracy. "
            "获取近期影子决策及其结果。用于了解近期交易信号与准确率。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max number of decisions to return",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
    {
        "name": TOOL_GET_EXPERIENCE,
        "description": (
            "Query the learning system for relevant observations, lessons, hypotheses, or experiments. "
            "Useful for leveraging accumulated trading experience. "
            "查询学习系统中的相关观察、教训、假设或实验。用于利用已积累的交易经验。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["observation", "lesson", "hypothesis", "experiment", "all"],
                    "description": "Category to query",
                    "default": "all",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max records to return",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
    {
        "name": TOOL_WEB_SEARCH,
        "description": (
            "Search the web for recent news, market events, or analysis related to crypto markets. "
            "Uses 4-tier provider degradation (Perplexity → local LLM+web → local LLM → DuckDuckGo). "
            "Cost varies by provider. Results include source timestamps for freshness assessment. "
            "搜索网络以获取近期加密市场新闻、事件或分析。使用 4 层 provider 降级体系。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, be specific for better results",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": TOOL_FETCH_URL,
        "description": (
            "Fetch and extract text content from a specific URL. "
            "Useful for reading detailed articles found via web_search. "
            "抓取并提取指定 URL 的文本内容。用于阅读通过 web_search 发现的详细文章。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Max characters to extract",
                    "default": 5000,
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": TOOL_SUBMIT_RECOMMENDATION,
        "description": (
            "Submit a structured trade recommendation. This is the primary output tool. "
            "Only call this when you have sufficient evidence and reasoning for a trade action. "
            "提交结构化交易推荐。这是主要输出工具。仅在有充分证据和推理时调用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["buy", "sell", "hold", "close_long", "close_short"],
                    "description": "Recommended trade action",
                },
                "symbol": {
                    "type": "string",
                    "description": "Trading symbol",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence level 0.0-1.0",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "edge_bps": {
                    "type": "number",
                    "description": "Expected edge in basis points",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Detailed reasoning for the recommendation",
                },
                "freshness_note": {
                    "type": "string",
                    "description": "Assessment of data freshness used",
                    "default": "",
                },
                "risk_factors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key risk factors identified",
                    "default": [],
                },
                "suggested_size_fraction": {
                    "type": "number",
                    "description": "Suggested position size as fraction of balance (0.01 = 1%)",
                    "default": 0.02,
                },
                "time_horizon": {
                    "type": "string",
                    "description": "Expected time horizon for the trade",
                    "default": "",
                },
            },
            "required": ["action", "symbol", "confidence", "edge_bps", "reasoning"],
        },
    },
    {
        "name": TOOL_RECORD_INSIGHT,
        "description": (
            "Record a market insight or observation to the learning system. "
            "Use for notable patterns, correlations, or events discovered during analysis. "
            "记录市场洞察或观察到学习系统。用于记录分析中发现的显著模式、关联或事件。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["macro", "sentiment", "technical", "correlation", "event", "anomaly"],
                    "description": "Insight category",
                },
                "title": {
                    "type": "string",
                    "description": "Brief title for the insight",
                },
                "detail": {
                    "type": "string",
                    "description": "Detailed description",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence in this insight (0-1)",
                    "default": 0.5,
                },
                "relevance_window": {
                    "type": "string",
                    "description": "How long this insight remains relevant (e.g. '24h', '7d')",
                    "default": "",
                },
            },
            "required": ["category", "title", "detail"],
        },
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# Search Providers / 搜索 Provider 实现
# ═══════════════════════════════════════════════════════════════════════════════

class PerplexitySearchProvider(SearchProvider):
    """
    Tier 1: Perplexity Search API — best quality, citations + timestamps.
    层级 1：Perplexity 搜索 API — 最高质量，带引用+时间戳。
    """

    @property
    def name(self) -> str:
        return SEARCH_PROVIDER_PERPLEXITY

    def is_available(self) -> bool:
        return bool(os.getenv("PERPLEXITY_API_KEY", ""))

    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        start = time.time()
        try:
            import httpx
        except ImportError:
            return SearchResponse(
                query=query, provider_used=self.name,
                providers_tried=[self.name],
                error="httpx not installed",
            )

        api_key = os.getenv("PERPLEXITY_API_KEY", "")
        if not api_key:
            return SearchResponse(
                query=query, provider_used=self.name,
                providers_tried=[self.name],
                error="PERPLEXITY_API_KEY not set",
            )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "sonar",
                        "messages": [
                            {"role": "system", "content": "You are a financial news search assistant. Return concise, factual results with source timestamps."},
                            {"role": "user", "content": query},
                        ],
                        "max_tokens": 1024,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            citations = data.get("citations", [])

            results = []
            # Parse Perplexity response into search results
            if content:
                results.append(SearchResult(
                    title=query,
                    snippet=content[:2000],
                    provider=self.name,
                    confidence=0.8,
                ))
            for i, cite in enumerate(citations[:max_results]):
                if isinstance(cite, str):
                    results.append(SearchResult(
                        title=f"Citation {i+1}",
                        snippet="",
                        url=cite,
                        provider=self.name,
                        citation_id=str(i+1),
                    ))

            latency = (time.time() - start) * 1000
            return SearchResponse(
                query=query,
                results=results,
                provider_used=self.name,
                providers_tried=[self.name],
                cost_usd=0.005,
                latency_ms=round(latency, 1),
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return SearchResponse(
                query=query, provider_used=self.name,
                providers_tried=[self.name],
                error=str(e), latency_ms=round(latency, 1),
            )


class LocalLLMWebSearchProvider(SearchProvider):
    """
    Tier 2: Local LLM (Ollama) + web-pilot script.
    层级 2：本地 LLM (Ollama) + web-pilot 脚本。
    """

    @property
    def name(self) -> str:
        return SEARCH_PROVIDER_LOCAL_LLM_WEB

    def is_available(self) -> bool:
        # Check if Ollama is running and web-pilot script exists
        try:
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, timeout=3,
            )
            if result.returncode != 0:
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        # Check web-pilot
        web_pilot = os.path.expanduser("~/.local/bin/web-pilot")
        return os.path.isfile(web_pilot)

    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        start = time.time()
        try:
            web_pilot = os.path.expanduser("~/.local/bin/web-pilot")
            proc = subprocess.run(
                [web_pilot, "search", query, "--max", str(max_results)],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                return SearchResponse(
                    query=query, provider_used=self.name,
                    providers_tried=[self.name],
                    error=f"web-pilot error: {proc.stderr[:200]}",
                )

            # Parse web-pilot output (JSON expected)
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                data = {"results": [{"title": "Search Result", "snippet": proc.stdout[:2000]}]}

            results = []
            for item in data.get("results", [])[:max_results]:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    snippet=item.get("snippet", ""),
                    url=item.get("url", ""),
                    provider=self.name,
                ))

            latency = (time.time() - start) * 1000
            return SearchResponse(
                query=query, results=results,
                provider_used=self.name, providers_tried=[self.name],
                cost_usd=0.0, latency_ms=round(latency, 1),
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return SearchResponse(
                query=query, provider_used=self.name,
                providers_tried=[self.name],
                error=str(e), latency_ms=round(latency, 1),
            )


class LocalLLMSearchProvider(SearchProvider):
    """
    Tier 3: Local LLM only (Ollama), no web access.
    层级 3：仅本地 LLM (Ollama)，无网络访问。
    """

    @property
    def name(self) -> str:
        return SEARCH_PROVIDER_LOCAL_LLM

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, timeout=3,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        start = time.time()
        try:
            proc = subprocess.run(
                ["ollama", "run", "llama3.2", f"Briefly answer: {query}"],
                capture_output=True, text=True, timeout=60,
            )
            content = proc.stdout.strip() if proc.returncode == 0 else ""
            if not content:
                return SearchResponse(
                    query=query, provider_used=self.name,
                    providers_tried=[self.name],
                    error="Ollama returned empty response",
                )

            results = [SearchResult(
                title=query,
                snippet=content[:2000],
                provider=self.name,
                confidence=0.4,  # Lower confidence — no web source
            )]
            latency = (time.time() - start) * 1000
            return SearchResponse(
                query=query, results=results,
                provider_used=self.name, providers_tried=[self.name],
                cost_usd=0.0, latency_ms=round(latency, 1),
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return SearchResponse(
                query=query, provider_used=self.name,
                providers_tried=[self.name],
                error=str(e), latency_ms=round(latency, 1),
            )


class WebPilotSearchProvider(SearchProvider):
    """
    Tier 4: DuckDuckGo via duckduckgo-search library (zero cost fallback).
    层级 4：通过 duckduckgo-search 库使用 DuckDuckGo（零成本兜底）。
    """

    @property
    def name(self) -> str:
        return SEARCH_PROVIDER_WEBPILOT

    def is_available(self) -> bool:
        try:
            from duckduckgo_search import DDGS  # noqa: F401
            return True
        except ImportError:
            return False

    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        start = time.time()
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))

            results = []
            for item in raw_results:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    snippet=item.get("body", ""),
                    url=item.get("href", ""),
                    provider=self.name,
                    confidence=0.5,
                ))

            latency = (time.time() - start) * 1000
            return SearchResponse(
                query=query, results=results,
                provider_used=self.name, providers_tried=[self.name],
                cost_usd=0.0, latency_ms=round(latency, 1),
            )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return SearchResponse(
                query=query, provider_used=self.name,
                providers_tried=[self.name],
                error=str(e), latency_ms=round(latency, 1),
            )


# Provider registry / Provider 注册表
SEARCH_PROVIDERS: dict[str, SearchProvider] = {
    SEARCH_PROVIDER_PERPLEXITY: PerplexitySearchProvider(),
    SEARCH_PROVIDER_LOCAL_LLM_WEB: LocalLLMWebSearchProvider(),
    SEARCH_PROVIDER_LOCAL_LLM: LocalLLMSearchProvider(),
    SEARCH_PROVIDER_WEBPILOT: WebPilotSearchProvider(),
}


async def search_with_degradation(
    query: str,
    *,
    enabled_providers: list[str] | None = None,
    max_results: int = 5,
) -> SearchResponse:
    """
    Execute search with automatic provider degradation.
    使用自动降级执行搜索。
    """
    from .layer2_types import SEARCH_PROVIDER_PRIORITY

    providers_to_try = enabled_providers or SEARCH_PROVIDER_PRIORITY
    all_tried: list[str] = []

    for provider_name in providers_to_try:
        provider = SEARCH_PROVIDERS.get(provider_name)
        if provider is None:
            continue
        if not provider.is_available():
            all_tried.append(provider_name)
            continue

        all_tried.append(provider_name)
        response = await provider.search(query, max_results=max_results)

        if response.error is None and response.results:
            response.providers_tried = all_tried
            response.is_degraded = provider_name != providers_to_try[0]
            return response

    # All failed
    return SearchResponse(
        query=query,
        providers_tried=all_tried,
        error="All search providers failed or unavailable",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Tool Executor / 工具执行器
# ═══════════════════════════════════════════════════════════════════════════════

class ToolExecutor:
    """
    Executes agent tool calls against the local system.
    执行 Agent 工具调用。
    """

    def __init__(
        self,
        paper_engine: Any = None,
        shadow_consumer: Any = None,
        learning_store_reader: Any = None,
        search_providers: list[str] | None = None,
        search_max_results: int = 5,
    ):
        self._paper_engine = paper_engine
        self._shadow_consumer = shadow_consumer
        self._learning_reader = learning_store_reader
        self._search_providers = search_providers
        self._search_max_results = search_max_results

        # Collected outputs
        self.recommendation: Recommendation | None = None
        self.insights: list[Insight] = []

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """
        Execute a tool call and return the result as a string for the AI.
        执行工具调用，将结果作为字符串返回给 AI。
        """
        handlers = {
            TOOL_GET_MARKET_STATE: self._get_market_state,
            TOOL_GET_ACCOUNT_STATE: self._get_account_state,
            TOOL_GET_RECENT_DECISIONS: self._get_recent_decisions,
            TOOL_GET_EXPERIENCE: self._get_experience,
            TOOL_WEB_SEARCH: self._web_search,
            TOOL_FETCH_URL: self._fetch_url,
            TOOL_SUBMIT_RECOMMENDATION: self._submit_recommendation,
            TOOL_RECORD_INSIGHT: self._record_insight,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        try:
            result = await handler(tool_input)
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Tool {tool_name} error: {e}")
            return json.dumps({"error": str(e)})

    # ── Data Reads / 数据读取 ──

    async def _get_market_state(self, args: dict[str, Any]) -> dict[str, Any]:
        """Read latest observer verdict + runtime snapshot / 读取最新 observer verdict + runtime 快照"""
        symbol = args.get("symbol", "BTCUSDT")
        result: dict[str, Any] = {"symbol": symbol, "source": "local_files"}

        # Try reading latest verdict
        verdict_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..",
            "trading_services", "bybit_connector", "observer_verdicts",
        )
        verdict_dir = os.path.abspath(verdict_dir)
        latest_verdict_path = os.path.join(verdict_dir, "observer_verdict_latest.json")
        if os.path.isfile(latest_verdict_path):
            try:
                with open(latest_verdict_path, "r") as f:
                    result["verdict"] = json.load(f)
            except (json.JSONDecodeError, OSError):
                result["verdict"] = None
                result["verdict_error"] = "Failed to read verdict file"
        else:
            result["verdict"] = None
            result["verdict_note"] = "No verdict file found"

        # Try reading runtime snapshot for market prices
        runtime_dir = os.path.join(os.path.dirname(__file__), "..", "runtime")
        snapshot_path = os.path.join(runtime_dir, "runtime_snapshot.json")
        if os.path.isfile(snapshot_path):
            try:
                with open(snapshot_path, "r") as f:
                    snap = json.load(f)
                result["market_prices"] = snap.get("market_prices", {})
                result["snapshot_ts"] = snap.get("timestamp_ms")
            except (json.JSONDecodeError, OSError):
                pass

        return result

    async def _get_account_state(self, args: dict[str, Any]) -> dict[str, Any]:
        """Read paper trading account state / 读取纸上交易账户状态"""
        if self._paper_engine is None:
            return {"error": "Paper trading engine not available"}

        try:
            status = self._paper_engine.get_session_status()
            positions = self._paper_engine.get_positions()
            pnl = self._paper_engine.get_pnl()
            orders = self._paper_engine.get_orders(state_filter=None)
            recent_orders = orders[:10] if orders else []
            return {
                "session": status,
                "positions": positions,
                "pnl": pnl,
                "recent_orders": recent_orders,
                "is_simulated": True,
            }
        except Exception as e:
            return {"error": str(e)}

    async def _get_recent_decisions(self, args: dict[str, Any]) -> dict[str, Any]:
        """Read recent shadow decisions / 读取近期影子决策"""
        limit = min(args.get("limit", 10), 50)
        decisions_dir = os.path.join(
            os.path.dirname(__file__), "..", "runtime", "shadow_decisions",
        )
        decisions_dir = os.path.abspath(decisions_dir)

        if not os.path.isdir(decisions_dir):
            return {"decisions": [], "note": "No shadow decisions directory found"}

        try:
            files = sorted(
                [f for f in os.listdir(decisions_dir) if f.endswith(".json")],
                reverse=True,
            )[:limit]
            decisions = []
            for fname in files:
                fpath = os.path.join(decisions_dir, fname)
                try:
                    with open(fpath, "r") as f:
                        decisions.append(json.load(f))
                except (json.JSONDecodeError, OSError):
                    continue
            return {"decisions": decisions, "count": len(decisions)}
        except OSError as e:
            return {"error": str(e)}

    async def _get_experience(self, args: dict[str, Any]) -> dict[str, Any]:
        """Query learning system records / 查询学习系统记录"""
        category = args.get("category", "all")
        limit = min(args.get("limit", 10), 50)

        # Read from main control state learning records
        state_path = os.path.join(os.path.dirname(__file__), "..", "runtime", "openclaw_bybit_control_state.json")
        state_path = os.path.abspath(state_path)

        if not os.path.isfile(state_path):
            return {"records": [], "note": "Control state file not found"}

        try:
            with open(state_path, "r") as f:
                state = json.load(f)
            records = state.get("records", {})
            result: dict[str, Any] = {}

            categories_to_read = (
                ["observations", "lessons", "hypotheses", "experiments"]
                if category == "all"
                else [{"hypothesis": "hypotheses", "observation": "observations", "lesson": "lessons", "experiment": "experiments"}.get(category, category + "s")]
            )

            for cat in categories_to_read:
                items = records.get(cat, [])
                result[cat] = items[-limit:] if items else []

            return result
        except (json.JSONDecodeError, OSError) as e:
            return {"error": str(e)}

    # ── External Search / 外部搜索 ──

    async def _web_search(self, args: dict[str, Any]) -> dict[str, Any]:
        """Search web via degradation chain / 通过降级链搜索网络"""
        query = args.get("query", "")
        if not query:
            return {"error": "query is required"}

        max_results = min(args.get("max_results", self._search_max_results), 10)
        response = await search_with_degradation(
            query,
            enabled_providers=self._search_providers,
            max_results=max_results,
        )

        return {
            "query": response.query,
            "provider_used": response.provider_used,
            "providers_tried": response.providers_tried,
            "is_degraded": response.is_degraded,
            "cost_usd": response.cost_usd,
            "latency_ms": response.latency_ms,
            "error": response.error,
            "results": [
                {
                    "title": r.title,
                    "snippet": r.snippet[:1000],
                    "url": r.url,
                    "source_ts": r.source_ts,
                    "confidence": r.confidence,
                }
                for r in response.results
            ],
        }

    async def _fetch_url(self, args: dict[str, Any]) -> dict[str, Any]:
        """Fetch and extract text from URL / 抓取并提取 URL 文本"""
        url = args.get("url", "")
        if not url:
            return {"error": "url is required"}
        max_chars = min(args.get("max_chars", 5000), 10000)

        # SSRF protection: block private/internal URLs
        # SSRF 防护：阻止私有/内部 URL
        try:
            from urllib.parse import urlparse
            import ipaddress
            parsed = urlparse(url)
            if parsed.scheme.lower() not in ("http", "https"):
                return {"error": f"blocked_scheme_{parsed.scheme}"}
            hostname = parsed.hostname or ""
            if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0", ""):
                return {"error": "blocked_localhost"}
            if any(hostname.endswith(d) for d in (".local", ".internal", ".corp")):
                return {"error": "blocked_internal_domain"}
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return {"error": "blocked_private_ip"}
            except ValueError:
                pass  # hostname is a domain, not IP — OK
        except Exception:
            return {"error": "url_validation_failed"}

        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError:
            return {"error": "httpx or beautifulsoup4 not installed"}

        try:
            import httpx as _httpx
            # follow_redirects=False to prevent SSRF via redirect
            async with _httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                resp = await client.get(url, headers={"User-Agent": "OpenClaw-Research/1.0"})
                resp.raise_for_status()
                html = resp.text

            soup = BeautifulSoup(html, "html.parser")
            # Remove script and style elements
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            text = text[:max_chars]

            return {
                "url": url,
                "text": text,
                "chars": len(text),
                "truncated": len(soup.get_text()) > max_chars,
            }
        except Exception as e:
            return {"error": f"Failed to fetch URL: {str(e)[:200]}"}

    # ── Outputs / 输出 ──

    async def _submit_recommendation(self, args: dict[str, Any]) -> dict[str, Any]:
        """Accept a trade recommendation / 接受交易推荐"""
        try:
            rec = Recommendation(
                action=args["action"],
                symbol=args["symbol"],
                confidence=args["confidence"],
                edge_bps=args["edge_bps"],
                reasoning=args["reasoning"],
                freshness_note=args.get("freshness_note", ""),
                risk_factors=args.get("risk_factors", []),
                suggested_size_fraction=args.get("suggested_size_fraction", 0.02),
                time_horizon=args.get("time_horizon", ""),
                source_tools=args.get("source_tools", []),
            )
            self.recommendation = rec
            return {
                "status": "recommendation_accepted",
                "action": rec.action,
                "symbol": rec.symbol,
                "confidence": rec.confidence,
                "edge_bps": rec.edge_bps,
                "will_auto_submit": True,
            }
        except (KeyError, TypeError) as e:
            return {"error": f"Invalid recommendation: {e}"}

    async def _record_insight(self, args: dict[str, Any]) -> dict[str, Any]:
        """Record a market insight / 记录市场洞察"""
        try:
            insight = Insight(
                category=args["category"],
                title=args["title"],
                detail=args["detail"],
                confidence=args.get("confidence", 0.5),
                relevance_window=args.get("relevance_window", ""),
            )
            self.insights.append(insight)
            return {
                "status": "insight_recorded",
                "category": insight.category,
                "title": insight.title,
                "total_insights": len(self.insights),
            }
        except (KeyError, TypeError) as e:
            return {"error": f"Invalid insight: {e}"}
