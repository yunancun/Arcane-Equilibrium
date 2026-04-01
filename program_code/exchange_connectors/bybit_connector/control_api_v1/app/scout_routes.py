from __future__ import annotations

"""
Scout Routes — ScoutAgent REST API / Scout 代理 REST API

MODULE_NOTE (中文):
  本模块定义 ScoutAgent 的所有 REST 接口（5 条），OpenClaw 可通过 HTTP 推送外部情报。

  POST /scout/market-signal      — OpenClaw 推送市场信号（新闻、情报、情绪）
  POST /scout/event-alert        — OpenClaw 推送事件警报（交易所公告、宏观事件）
  GET  /scout/status             — 获取 ScoutAgent + MessageBus 状态
  GET  /scout/intel              — 查询最近的情报对象（可分页）
  GET  /scout/alerts             — 查询最近的事件警报（可分页）

MODULE_NOTE (English):
  Defines all REST interfaces (5 routes) for ScoutAgent. OpenClaw can push external
  intelligence via HTTP REST endpoints.

  POST /scout/market-signal      — OpenClaw pushes market intelligence (news, signals, sentiment)
  POST /scout/event-alert        — OpenClaw pushes event alerts (exchange announcements, macros)
  GET  /scout/status             — Get ScoutAgent + MessageBus status
  GET  /scout/intel              — Query recent IntelObjects (paginated)
  GET  /scout/alerts             — Query recent EventAlerts (paginated)

SYSTEM MODE: read_only
  This module uses token-based authentication. ScoutAgent and MessageBus must be
  injected via set_scout_agent() and set_message_bus() before routes are called.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator

from . import main_legacy as base
from .multi_agent_framework import (
    DataQualityLevel,
    EventAlert,
    IntelObject,
    MessageBus,
    ScoutAgent,
    SentimentScore,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Router & Shared State / 路由与共享状态
# ═══════════════════════════════════════════════════════════════════════════════

scout_router = APIRouter(
    prefix="/api/v1/scout",
    tags=["Scout Agent / Scout 代理"],
)

# Module-level state for dependency injection
# Will be set by external initialization code (e.g., E1b-B)
SCOUT_AGENT: Optional[ScoutAgent] = None
MESSAGE_BUS: Optional[MessageBus] = None
# Batch 9: Perception Plane for cognitive level marking / 感知平面用于认知级别标记
PERCEPTION_PLANE: Optional[Any] = None


def set_scout_agent(agent: ScoutAgent) -> None:
    """
    Inject the ScoutAgent instance.
    注入 ScoutAgent 实例。
    """
    global SCOUT_AGENT
    SCOUT_AGENT = agent
    logger.info("ScoutAgent injected into scout_routes")


def set_message_bus(bus: MessageBus) -> None:
    """
    Inject the MessageBus instance.
    注入 MessageBus 实例。
    """
    global MESSAGE_BUS
    MESSAGE_BUS = bus
    logger.info("MessageBus injected into scout_routes")


def set_perception_plane(plane: Any) -> None:
    """
    Batch 9: Inject PerceptionPlane for cognitive level marking on intel/events.
    Batch 9：注入感知平面用于对情报/事件进行认知级别标记。
    """
    global PERCEPTION_PLANE
    PERCEPTION_PLANE = plane
    logger.info("PerceptionPlane injected into scout_routes / 感知平面已注入 scout_routes")


def _check_agent_ready() -> None:
    """
    Check that ScoutAgent and MessageBus are initialized.
    If not, raise 503 Service Unavailable.
    检查 ScoutAgent 和 MessageBus 是否已初始化。
    """
    if SCOUT_AGENT is None or MESSAGE_BUS is None:
        logger.error("ScoutAgent or MessageBus not initialized")
        raise HTTPException(
            status_code=503,
            detail={
                "reason_codes": ["scout_service_unavailable"],
                "message": "ScoutAgent or MessageBus not ready",
            },
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Models / 请求响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class MarketSignalRequest(BaseModel):
    """
    Request body for POST /scout/market-signal
    市场信号请求体
    """

    source: str = Field(
        ...,
        max_length=100,
        description="Source of the signal (e.g., 'openClaw', 'news_feed', 'sentiment_engine')",
    )
    content: str = Field(
        ...,
        max_length=5000,
        description="Content/description of the market signal",
    )
    symbols: list[str] = Field(
        ...,
        min_items=1,
        max_items=50,
        description="List of affected symbols (e.g., ['BTCUSDT', 'ETHUSDT'])",
    )
    sentiment: str = Field(
        default="neutral",
        description="Sentiment: 'positive', 'negative', or 'neutral'",
    )
    relevance_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Relevance score (0.0-1.0)",
    )
    data_quality: str = Field(
        default="inference",
        description="Data quality level: 'fact', 'inference', or 'hypothesis'",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata",
    )

    @validator("sentiment")
    def validate_sentiment(cls, v: str) -> str:
        if v not in ("positive", "negative", "neutral"):
            raise ValueError("Sentiment must be 'positive', 'negative', or 'neutral'")
        return v

    @validator("data_quality")
    def validate_data_quality(cls, v: str) -> str:
        if v not in ("fact", "inference", "hypothesis"):
            raise ValueError("data_quality must be 'fact', 'inference', or 'hypothesis'")
        return v


class EventAlertRequest(BaseModel):
    """
    Request body for POST /scout/event-alert
    事件警报请求体
    """

    event_type: str = Field(
        ...,
        max_length=100,
        description="Type of event (e.g., 'exchange_announcement', 'macro_event', 'incident')",
    )
    severity: str = Field(
        default="medium",
        description="Severity level: 'low', 'medium', 'high', or 'critical'",
    )
    affected_symbols: list[str] = Field(
        ...,
        min_items=1,
        max_items=50,
        description="List of affected symbols",
    )
    event_time_ms: int = Field(
        ...,
        ge=0,
        description="Event timestamp in milliseconds since epoch",
    )
    lead_time_hours: float = Field(
        default=0.0,
        ge=0.0,
        le=720.0,
        description="How many hours in advance the event was detected (0-720 hours)",
    )
    data_quality: str = Field(
        default="inference",
        description="Data quality level: 'fact', 'inference', or 'hypothesis'",
    )
    description: str = Field(
        ...,
        max_length=2000,
        description="Detailed description of the event",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata",
    )

    @validator("severity")
    def validate_severity(cls, v: str) -> str:
        if v not in ("low", "medium", "high", "critical"):
            raise ValueError("severity must be 'low', 'medium', 'high', or 'critical'")
        return v

    @validator("data_quality")
    def validate_data_quality(cls, v: str) -> str:
        if v not in ("fact", "inference", "hypothesis"):
            raise ValueError("data_quality must be 'fact', 'inference', or 'hypothesis'")
        return v


class IntelObjectResponse(BaseModel):
    """
    Response model for IntelObject
    情报对象响应模型
    """

    intel_id: str
    source: str
    content: str
    symbols: list[str]
    sentiment: str
    relevance_score: float
    data_quality: str
    created_at_ms: int
    metadata: dict[str, Any]

    class Config:
        from_attributes = True


class EventAlertResponse(BaseModel):
    """
    Response model for EventAlert
    事件警报响应模型
    """

    alert_id: str
    event_type: str
    severity: str
    affected_symbols: list[str]
    event_time_ms: int
    lead_time_hours: float
    data_quality: str
    description: str
    created_at_ms: int
    metadata: dict[str, Any]

    class Config:
        from_attributes = True


class ScoutStatusResponse(BaseModel):
    """
    Response model for GET /scout/status
    状态响应模型
    """

    agent_role: str
    agent_state: str
    message_bus_total_messages: int
    recent_intel_count: int
    recent_alerts_count: int
    is_running: bool
    last_activity_ms: int


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions / 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _sentiment_str_to_enum(sentiment: str) -> SentimentScore:
    """
    Convert string sentiment to SentimentScore enum.
    将字符串情绪转换为 SentimentScore 枚举。
    """
    mapping = {
        "positive": SentimentScore.POSITIVE,
        "neutral": SentimentScore.NEUTRAL,
        "negative": SentimentScore.NEGATIVE,
    }
    return mapping.get(sentiment, SentimentScore.NEUTRAL)


def _quality_str_to_enum(quality: str) -> DataQualityLevel:
    """
    Convert string data quality to DataQualityLevel enum.
    将字符串数据质量转换为 DataQualityLevel 枚举。
    """
    mapping = {
        "fact": DataQualityLevel.FACT,
        "inference": DataQualityLevel.INFERENCE,
        "hypothesis": DataQualityLevel.HYPOTHESIS,
    }
    return mapping.get(quality, DataQualityLevel.INFERENCE)


# ═══════════════════════════════════════════════════════════════════════════════
# Routes / 路由
# ═══════════════════════════════════════════════════════════════════════════════


@scout_router.post("/market-signal")
def post_market_signal(
    req: MarketSignalRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    OpenClaw pushes market intelligence to ScoutAgent.

    OpenClaw 推送市场情报到 ScoutAgent。

    OpenClaw provides external intelligence (news, market signals, sentiment analysis)
    which ScoutAgent integrates with local Bybit market data and routes through
    MessageBus to downstream consumers (traders, analyzers, etc.).

    OpenClaw 提供外部情报（新闻、市场信号、情绪分析），ScoutAgent 将其与本地 Bybit
    市场数据整合，通过 MessageBus 路由给下游消费者（交易员、分析器等）。

    Returns the created IntelObject on success.
    成功时返回创建的 IntelObject。
    """
    _check_agent_ready()

    try:
        # Validate symbols list
        if not req.symbols or len(req.symbols) == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "reason_codes": ["invalid_symbols"],
                    "message": "symbols list cannot be empty",
                },
            )

        # Convert sentiment and quality to enums
        sentiment_enum = _sentiment_str_to_enum(req.sentiment)
        quality_enum = _quality_str_to_enum(req.data_quality)

        # Call ScoutAgent to produce intel
        intel_obj = SCOUT_AGENT.produce_intel(
            source=req.source,
            content=req.content,
            symbols=req.symbols,
            sentiment=sentiment_enum,
            relevance_score=req.relevance_score,
            data_quality=quality_enum,
            metadata=req.metadata,
        )

        logger.info(
            f"Market signal received from {req.source}, "
            f"intel_id={intel_obj.intel_id}, symbols={req.symbols}"
        )

        # Batch 9: Register intel as INFERENCE in Perception Plane (EX-07 §1)
        # Batch 9：将情报注册为 INFERENCE 到感知平面（认知诚实）
        if PERCEPTION_PLANE is not None:
            try:
                from .perception_data_plane import DataSourceType, CognitiveLevel
                # Intel from external sources = INFERENCE by default
                # 来自外部来源的情报 = 默认 INFERENCE
                _cog_level = CognitiveLevel.INFERENCE
                if req.data_quality == "hypothesis":
                    _cog_level = CognitiveLevel.HYPOTHESIS
                PERCEPTION_PLANE.register_data(
                    source_type=DataSourceType.SEARCH_WEB,
                    content={"intel_id": intel_obj.intel_id, "source": req.source, "content": req.content[:200]},
                    source_detail=f"scout_intel:{req.source}",
                    cognitive_level=_cog_level,
                    symbols=req.symbols,
                    marked_by="scout_routes.post_market_signal",
                    marking_reason=f"External intelligence = {_cog_level.value} (EX-07 §1)",
                )
            except Exception as _pp_err:
                logger.debug("Perception registration error (non-fatal): %s", _pp_err)

        return {
            "api_version": "v1",
            "action_result": "success",
            "reason_codes": [],
            "module": "scout_agent",
            "data": {
                "intel_id": intel_obj.intel_id,
                "source": intel_obj.source,
                "content": intel_obj.content,
                "symbols": intel_obj.symbols,
                "sentiment": intel_obj.sentiment.name.lower(),
                "relevance_score": intel_obj.relevance_score,
                "data_quality": intel_obj.data_quality.name.lower(),
                "created_at_ms": intel_obj.created_at_ms,
                "metadata": intel_obj.metadata,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error processing market signal: %s", e)
        raise HTTPException(
            status_code=500,
            detail={
                "reason_codes": ["internal_error"],
                "message": str(e),
            },
        )


@scout_router.post("/event-alert")
def post_event_alert(
    req: EventAlertRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    OpenClaw pushes event alerts to ScoutAgent.

    OpenClaw 推送事件警报到 ScoutAgent。

    Event alerts represent external events (exchange announcements, macroeconomic
    announcements, compliance events, etc.) that affect markets. ScoutAgent
    integrates with local data and routes through MessageBus.

    事件警报代表影响市场的外部事件（交易所公告、宏观经济公告、合规事件等）。
    ScoutAgent 与本地数据整合并通过 MessageBus 路由。

    Returns the created EventAlert on success.
    成功时返回创建的 EventAlert。
    """
    _check_agent_ready()

    try:
        # Validate affected_symbols list
        if not req.affected_symbols or len(req.affected_symbols) == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "reason_codes": ["invalid_symbols"],
                    "message": "affected_symbols list cannot be empty",
                },
            )

        # Convert quality to enum
        quality_enum = _quality_str_to_enum(req.data_quality)

        # Call ScoutAgent to produce event alert
        alert_obj = SCOUT_AGENT.produce_event_alert(
            event_type=req.event_type,
            severity=req.severity,
            affected_symbols=req.affected_symbols,
            event_time_ms=req.event_time_ms,
            lead_time_hours=req.lead_time_hours,
            data_quality=quality_enum,
            description=req.description,
            metadata=req.metadata,
        )

        logger.info(
            f"Event alert received: event_type={req.event_type}, "
            f"alert_id={alert_obj.alert_id}, severity={req.severity}, "
            f"symbols={req.affected_symbols}"
        )

        # Batch 9: Register event alert as INFERENCE in Perception Plane (EX-07 §1)
        # Batch 9：将事件警报注册为 INFERENCE 到感知平面（认知诚实）
        if PERCEPTION_PLANE is not None:
            try:
                from .perception_data_plane import DataSourceType, CognitiveLevel
                PERCEPTION_PLANE.register_data(
                    source_type=DataSourceType.EVENT_CALENDAR,
                    content={"alert_id": alert_obj.alert_id, "event_type": req.event_type, "severity": req.severity},
                    source_detail=f"scout_event:{req.event_type}",
                    cognitive_level=CognitiveLevel.INFERENCE,
                    symbols=req.affected_symbols,
                    marked_by="scout_routes.post_event_alert",
                    marking_reason="External event alert = INFERENCE (EX-07 §1)",
                )
            except Exception as _pp_err:
                logger.debug("Perception registration error (non-fatal): %s", _pp_err)

        return {
            "api_version": "v1",
            "action_result": "success",
            "reason_codes": [],
            "module": "scout_agent",
            "data": {
                "alert_id": alert_obj.alert_id,
                "event_type": alert_obj.event_type,
                "severity": alert_obj.severity,
                "affected_symbols": alert_obj.affected_symbols,
                "event_time_ms": alert_obj.event_time_ms,
                "lead_time_hours": alert_obj.lead_time_hours,
                "data_quality": alert_obj.data_quality.name.lower(),
                "description": alert_obj.description,
                "created_at_ms": alert_obj.created_at_ms,
                "metadata": alert_obj.metadata,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error processing event alert: %s", e)
        raise HTTPException(
            status_code=500,
            detail={
                "reason_codes": ["internal_error"],
                "message": str(e),
            },
        )


@scout_router.get("/status")
def get_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Get ScoutAgent and MessageBus status.

    获取 ScoutAgent 和 MessageBus 的状态。

    Returns agent state, message counts, recent intelligence/alert counts,
    and runtime status.

    返回代理状态、消息计数、最近情报/警报计数和运行时状态。
    """
    _check_agent_ready()

    try:
        # Get agent info
        agent_role = SCOUT_AGENT.role.name if hasattr(SCOUT_AGENT.role, "name") else str(SCOUT_AGENT.role)
        agent_state = SCOUT_AGENT.state.name if hasattr(SCOUT_AGENT.state, "name") else str(SCOUT_AGENT.state)
        is_running = SCOUT_AGENT.is_running

        # Get message bus stats
        total_messages = MESSAGE_BUS.total_messages() if hasattr(MESSAGE_BUS, "total_messages") else 0

        # Get recent intel and alerts
        recent_intel = SCOUT_AGENT.get_recent_intel(limit=100)
        recent_alerts = SCOUT_AGENT.get_recent_alerts(limit=100)

        # Get last activity timestamp
        last_activity_ms = SCOUT_AGENT.last_activity_ms if hasattr(SCOUT_AGENT, "last_activity_ms") else 0

        return {
            "api_version": "v1",
            "action_result": "success",
            "reason_codes": [],
            "module": "scout_agent",
            "data": {
                "agent_role": agent_role,
                "agent_state": agent_state,
                "is_running": is_running,
                "message_bus_total_messages": total_messages,
                "recent_intel_count": len(recent_intel),
                "recent_alerts_count": len(recent_alerts),
                "last_activity_ms": last_activity_ms,
            },
        }

    except Exception as e:
        logger.exception("Error getting status: %s", e)
        raise HTTPException(
            status_code=500,
            detail={
                "reason_codes": ["internal_error"],
                "message": str(e),
            },
        )


@scout_router.get("/intel")
def get_intel(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Get recent IntelObjects from ScoutAgent.

    从 ScoutAgent 获取最近的情报对象。

    Returns a paginated list of recent IntelObjects ordered by creation time
    (most recent first).

    返回按创建时间排序的最近情报对象的分页列表（最新优先）。
    """
    _check_agent_ready()

    try:
        # Get recent intel with limit + offset
        all_intel = SCOUT_AGENT.get_recent_intel(limit=limit + offset)

        # Apply offset
        intel_slice = all_intel[offset : offset + limit]

        # Convert to response format
        intel_list = []
        for intel_obj in intel_slice:
            intel_list.append({
                "intel_id": intel_obj.intel_id,
                "source": intel_obj.source,
                "content": intel_obj.content,
                "symbols": intel_obj.symbols,
                "sentiment": intel_obj.sentiment.name.lower(),
                "relevance_score": intel_obj.relevance_score,
                "data_quality": intel_obj.data_quality.name.lower(),
                "created_at_ms": intel_obj.created_at_ms,
                "metadata": intel_obj.metadata,
            })

        return {
            "api_version": "v1",
            "action_result": "success",
            "reason_codes": [],
            "module": "scout_agent",
            "data": {
                "intel": intel_list,
                "count": len(intel_list),
                "limit": limit,
                "offset": offset,
                "total_available": len(all_intel),
            },
        }

    except Exception as e:
        logger.exception("Error getting intel: %s", e)
        raise HTTPException(
            status_code=500,
            detail={
                "reason_codes": ["internal_error"],
                "message": str(e),
            },
        )


@scout_router.get("/alerts")
def get_alerts(
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Get recent EventAlerts from ScoutAgent.

    从 ScoutAgent 获取最近的事件警报。

    Returns a paginated list of recent EventAlerts ordered by creation time
    (most recent first).

    返回按创建时间排序的最近事件警报的分页列表（最新优先）。
    """
    _check_agent_ready()

    try:
        # Get recent alerts with limit + offset
        all_alerts = SCOUT_AGENT.get_recent_alerts(limit=limit + offset)

        # Apply offset
        alerts_slice = all_alerts[offset : offset + limit]

        # Convert to response format
        alerts_list = []
        for alert_obj in alerts_slice:
            alerts_list.append({
                "alert_id": alert_obj.alert_id,
                "event_type": alert_obj.event_type,
                "severity": alert_obj.severity,
                "affected_symbols": alert_obj.affected_symbols,
                "event_time_ms": alert_obj.event_time_ms,
                "lead_time_hours": alert_obj.lead_time_hours,
                "data_quality": alert_obj.data_quality.name.lower(),
                "description": alert_obj.description,
                "created_at_ms": alert_obj.created_at_ms,
                "metadata": alert_obj.metadata,
            })

        return {
            "api_version": "v1",
            "action_result": "success",
            "reason_codes": [],
            "module": "scout_agent",
            "data": {
                "alerts": alerts_list,
                "count": len(alerts_list),
                "limit": limit,
                "offset": offset,
                "total_available": len(all_alerts),
            },
        }

    except Exception as e:
        logger.exception("Error getting alerts: %s", e)
        raise HTTPException(
            status_code=500,
            detail={
                "reason_codes": ["internal_error"],
                "message": str(e),
            },
        )
