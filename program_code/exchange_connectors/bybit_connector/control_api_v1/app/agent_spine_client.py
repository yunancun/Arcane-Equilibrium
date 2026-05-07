"""Fail-soft Python client for the Agent Decision Spine store.

MAG-033 intentionally exposes typed publish/consume helpers only. It does not
grant Python agents trading authority; execution authority remains Rust-owned.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from .agent_contracts import (
    AgentSpineMode,
    AnalystInsight,
    DecisionEdgeType,
    ExecutionPlan,
    ExecutionReport,
    GuardianVerdict,
    SpinePayload,
    StrategistDecision,
    StrategySignal,
    payload_dict,
)
from .db_pool import get_pg_conn

try:  # pragma: no cover - exercised when psycopg2 is installed
    from psycopg2.extras import Json
except Exception:  # pragma: no cover - local static tests may omit psycopg2
    Json = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = {
    "api_key",
    "api_secret",
    "authorization",
    "cookie",
    "password",
    "prompt",
    "raw_prompt",
    "raw_response",
    "refresh_token",
    "secret",
    "stack_trace",
    "token",
    "traceback",
}


@dataclass
class AgentSpineClientStats:
    disabled: int = 0
    object_rows: int = 0
    edge_rows: int = 0
    transition_rows: int = 0
    idempotency_rows: int = 0
    write_failures: int = 0
    serialization_failures: int = 0
    last_error: Optional[str] = None


def _env_enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip() == "1"


def _utc_from_ms(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _stable_id(prefix: str, parts: Iterable[str]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part).encode("utf-8", errors="replace"))
        h.update(b"\0")
    return f"{prefix}:{h.hexdigest()[:32]}"


class AgentSpineClient:
    """Typed, bounded, fail-soft writer/reader for MAG-032 V064 tables."""

    def __init__(
        self,
        *,
        enabled: Optional[bool] = None,
        authority_mode: AgentSpineMode = "shadow",
        max_payload_bytes: Optional[int] = None,
    ) -> None:
        self.enabled = (
            _env_enabled("OPENCLAW_AGENT_SPINE_CLIENT_ENABLED")
            if enabled is None
            else bool(enabled)
        )
        self.authority_mode = authority_mode
        self.max_payload_bytes = int(
            max_payload_bytes
            if max_payload_bytes is not None
            else os.getenv("OPENCLAW_AGENT_SPINE_PAYLOAD_MAX_BYTES", "65536")
        )
        self.stats = AgentSpineClientStats()
        self._lock = threading.Lock()

    def publish_strategy_signal(self, signal: StrategySignal) -> bool:
        return self._publish_object(
            signal,
            object_id=signal.signal_id,
            object_type="strategy_signal",
            object_version=signal.schema_version,
            ts_ms=signal.ts_ms,
            engine_mode=signal.engine_mode,
            symbol=signal.symbol,
            strategy=signal.strategy,
            signal_id=signal.signal_id,
            decision_id=None,
            verdict_id=None,
            verdict_version=None,
            order_plan_id=None,
            execution_report_id=None,
            lease_id=None,
            state="observed",
            source_agent="strategy",
            idempotency_key=f"strategy_signal:{signal.engine_mode}:{signal.signal_id}",
        )

    def publish_strategist_decision(self, decision: StrategistDecision) -> bool:
        ok = self._publish_object(
            decision,
            object_id=decision.decision_id,
            object_type="strategist_decision",
            object_version=decision.schema_version,
            ts_ms=decision.ts_ms,
            engine_mode=decision.engine_mode,
            symbol=decision.symbol,
            strategy=decision.strategy,
            signal_id=decision.signal_id,
            decision_id=decision.decision_id,
            verdict_id=None,
            verdict_version=None,
            order_plan_id=None,
            execution_report_id=None,
            lease_id=None,
            state="proposed",
            source_agent="strategist",
            idempotency_key=f"strategist_decision:{decision.engine_mode}:{decision.decision_id}",
        )
        edge_ok = self.publish_edge(
            from_object_id=decision.signal_id,
            to_object_id=decision.decision_id,
            edge_type="signal_for",
            engine_mode=decision.engine_mode,
            decision_id=decision.decision_id,
            details={"source": "python_agent_spine_client"},
            created_at_ms=decision.ts_ms,
        )
        return ok and edge_ok

    def publish_guardian_verdict(self, verdict: GuardianVerdict) -> bool:
        state = "approved" if verdict.allow else "rejected"
        ok = self._publish_object(
            verdict,
            object_id=verdict.verdict_id,
            object_type="guardian_verdict",
            object_version=verdict.schema_version,
            ts_ms=verdict.ts_ms,
            engine_mode=verdict.engine_mode,
            symbol=verdict.symbol,
            strategy=verdict.strategy,
            signal_id=None,
            decision_id=verdict.decision_id,
            verdict_id=verdict.verdict_id,
            verdict_version=verdict.verdict_version,
            order_plan_id=None,
            execution_report_id=None,
            lease_id=None,
            state=state,
            source_agent="guardian",
            idempotency_key=(
                f"guardian_verdict:{verdict.engine_mode}:"
                f"{verdict.decision_id}:{verdict.verdict_version}"
            ),
        )
        edge_ok = self.publish_edge(
            from_object_id=verdict.decision_id,
            to_object_id=verdict.verdict_id,
            edge_type="reviewed_by",
            engine_mode=verdict.engine_mode,
            decision_id=verdict.decision_id,
            details={"allow": verdict.allow, "risk_level": verdict.risk_level},
            created_at_ms=verdict.ts_ms,
        )
        return ok and edge_ok

    def publish_execution_plan(self, plan: ExecutionPlan, *, reserve_idempotency: bool = True) -> bool:
        ok = self._publish_object(
            plan,
            object_id=plan.order_plan_id,
            object_type="execution_plan",
            object_version=plan.schema_version,
            ts_ms=plan.ts_ms,
            engine_mode=plan.engine_mode,
            symbol=plan.symbol,
            strategy=plan.strategy,
            signal_id=None,
            decision_id=plan.decision_id,
            verdict_id=plan.verdict_id,
            verdict_version=None,
            order_plan_id=plan.order_plan_id,
            execution_report_id=None,
            lease_id=plan.lease_id,
            state="planned",
            source_agent="executor",
            idempotency_key=plan.idempotency_key,
        )
        edge_ok = self.publish_edge(
            from_object_id=plan.verdict_id,
            to_object_id=plan.order_plan_id,
            edge_type="planned_by",
            engine_mode=plan.engine_mode,
            decision_id=plan.decision_id,
            details={"order_type": plan.order_type, "time_in_force": plan.time_in_force},
            created_at_ms=plan.ts_ms,
        )
        idem_ok = True
        if reserve_idempotency:
            idem_ok = self.reserve_execution_key(
                idempotency_key=plan.idempotency_key,
                order_plan_id=plan.order_plan_id,
                decision_id=plan.decision_id,
                engine_mode=plan.engine_mode,
                first_seen_at_ms=plan.ts_ms,
                details={"verdict_id": plan.verdict_id, "symbol": plan.symbol},
            )
        return ok and edge_ok and idem_ok

    def publish_execution_report(self, report: ExecutionReport) -> bool:
        ok = self._publish_object(
            report,
            object_id=report.execution_report_id,
            object_type="execution_report",
            object_version=report.schema_version,
            ts_ms=report.ts_ms,
            engine_mode=report.engine_mode,
            symbol=report.symbol,
            strategy=None,
            signal_id=None,
            decision_id=report.decision_id,
            verdict_id=None,
            verdict_version=None,
            order_plan_id=report.order_plan_id,
            execution_report_id=report.execution_report_id,
            lease_id=None,
            state=report.status,
            source_agent="executor",
            idempotency_key=f"execution_report:{report.engine_mode}:{report.execution_report_id}",
        )
        edge_ok = self.publish_edge(
            from_object_id=report.order_plan_id,
            to_object_id=report.execution_report_id,
            edge_type="executed_by",
            engine_mode=report.engine_mode,
            decision_id=report.decision_id,
            details={"status": report.status, "fill_id": report.fill_id},
            created_at_ms=report.ts_ms,
        )
        return ok and edge_ok

    def publish_analyst_insight(self, insight: AnalystInsight) -> bool:
        ok = self._publish_object(
            insight,
            object_id=insight.insight_id,
            object_type="analyst_insight",
            object_version=insight.schema_version,
            ts_ms=insight.ts_ms,
            engine_mode=insight.engine_mode,
            symbol=insight.symbol,
            strategy=insight.strategy,
            signal_id=None,
            decision_id=insight.decision_id,
            verdict_id=None,
            verdict_version=None,
            order_plan_id=insight.order_plan_id,
            execution_report_id=insight.execution_report_id,
            lease_id=None,
            state="observed",
            source_agent="analyst",
            idempotency_key=f"analyst_insight:{insight.engine_mode}:{insight.insight_id}",
        )
        parent_id = insight.execution_report_id or insight.order_plan_id or insight.decision_id
        if parent_id is None:
            return ok
        edge_ok = self.publish_edge(
            from_object_id=parent_id,
            to_object_id=insight.insight_id,
            edge_type="analyzed_by",
            engine_mode=insight.engine_mode,
            decision_id=insight.decision_id,
            details={"insight_level": insight.insight_level},
            created_at_ms=insight.ts_ms,
        )
        return ok and edge_ok

    def publish_edge(
        self,
        *,
        from_object_id: str,
        to_object_id: str,
        edge_type: DecisionEdgeType,
        engine_mode: str,
        decision_id: str | None,
        details: dict[str, Any] | None = None,
        created_at_ms: int | None = None,
    ) -> bool:
        if not self.enabled:
            self._inc_disabled()
            return False
        try:
            safe_details = self._bounded_payload(details or {})
            edge_id = _stable_id("edge", [edge_type, from_object_id, to_object_id])
            sql = """
                INSERT INTO agent.decision_edges (
                    edge_id, created_at, from_object_id, to_object_id, edge_type,
                    engine_mode, decision_id, payload_hash, details
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (from_object_id, to_object_id, edge_type) DO NOTHING
            """
            params = (
                edge_id,
                _utc_from_ms(created_at_ms or int(datetime.now(tz=timezone.utc).timestamp() * 1000)),
                from_object_id,
                to_object_id,
                edge_type,
                engine_mode,
                decision_id,
                _sha256_json(safe_details),
                self._json_param(safe_details),
            )
            self._execute(sql, params)
            with self._lock:
                self.stats.edge_rows += 1
            return True
        except Exception as exc:  # noqa: BLE001 - fail-soft spine writer
            self._record_failure("publish_edge", exc)
            return False

    def reserve_execution_key(
        self,
        *,
        idempotency_key: str,
        order_plan_id: str,
        decision_id: str,
        engine_mode: str,
        first_seen_at_ms: int,
        details: dict[str, Any] | None = None,
        status: str = "reserved",
    ) -> bool:
        if not self.enabled:
            self._inc_disabled()
            return False
        try:
            safe_details = self._bounded_payload(details or {})
            sql = """
                INSERT INTO agent.execution_idempotency_keys (
                    idempotency_key, order_plan_id, decision_id, engine_mode,
                    first_seen_at, status, details
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
            """
            params = (
                idempotency_key,
                order_plan_id,
                decision_id,
                engine_mode,
                _utc_from_ms(first_seen_at_ms),
                status,
                self._json_param(safe_details),
            )
            self._execute(sql, params)
            with self._lock:
                self.stats.idempotency_rows += 1
            return True
        except Exception as exc:  # noqa: BLE001 - fail-soft spine writer
            self._record_failure("reserve_execution_key", exc)
            return False

    def fetch_object(self, object_id: str) -> dict[str, Any] | None:
        sql = """
            SELECT object_id, object_type, object_version, engine_mode, symbol,
                   strategy, signal_id, decision_id, verdict_id, verdict_version,
                   order_plan_id, execution_report_id, lease_id, state,
                   source_agent, authority_mode, idempotency_key, payload_hash,
                   payload
              FROM agent.decision_objects
             WHERE object_id = %s
        """
        rows = self._query(sql, (object_id,))
        return rows[0] if rows else None

    def fetch_chain_by_signal(self, signal_id: str) -> list[dict[str, Any]]:
        sql = """
            SELECT obj.object_id, obj.object_type, obj.state, obj.payload
              FROM agent.decision_objects sig
              JOIN agent.decision_edges e1
                ON e1.from_object_id = sig.object_id
               AND e1.edge_type = 'signal_for'
              JOIN agent.decision_objects decision_obj
                ON decision_obj.object_id = e1.to_object_id
              LEFT JOIN agent.decision_edges e2
                ON e2.from_object_id = decision_obj.object_id
               AND e2.edge_type IN ('reviewed_by', 'modified_by')
              LEFT JOIN agent.decision_objects verdict_obj
                ON verdict_obj.object_id = e2.to_object_id
              LEFT JOIN agent.decision_edges e3
                ON e3.from_object_id = verdict_obj.object_id
               AND e3.edge_type = 'planned_by'
              LEFT JOIN agent.decision_objects plan_obj
                ON plan_obj.object_id = e3.to_object_id
             CROSS JOIN LATERAL (
                VALUES
                  (sig.object_id, sig.object_type, sig.state, sig.payload, 0),
                  (decision_obj.object_id, decision_obj.object_type, decision_obj.state, decision_obj.payload, 1),
                  (verdict_obj.object_id, verdict_obj.object_type, verdict_obj.state, verdict_obj.payload, 2),
                  (plan_obj.object_id, plan_obj.object_type, plan_obj.state, plan_obj.payload, 3)
             ) AS obj(object_id, object_type, state, payload, chain_order)
             WHERE sig.signal_id = %s
               AND obj.object_id IS NOT NULL
             ORDER BY obj.chain_order
        """
        return self._query(sql, (signal_id,))

    def _publish_object(
        self,
        payload_model: SpinePayload,
        *,
        object_id: str,
        object_type: str,
        object_version: str,
        ts_ms: int,
        engine_mode: str,
        symbol: str,
        strategy: str | None,
        signal_id: str | None,
        decision_id: str | None,
        verdict_id: str | None,
        verdict_version: int | None,
        order_plan_id: str | None,
        execution_report_id: str | None,
        lease_id: str | None,
        state: str,
        source_agent: str,
        idempotency_key: str,
    ) -> bool:
        if not self.enabled:
            self._inc_disabled()
            return False
        try:
            payload = self._bounded_payload(payload_dict(payload_model))
            sql = """
                INSERT INTO agent.decision_objects (
                    created_at, object_id, object_type, object_version,
                    engine_mode, symbol, strategy, signal_id, decision_id,
                    verdict_id, verdict_version, order_plan_id,
                    execution_report_id, lease_id, state, source_agent,
                    authority_mode, idempotency_key, payload_hash, payload
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (object_type, idempotency_key) DO NOTHING
            """
            params = (
                _utc_from_ms(ts_ms),
                object_id,
                object_type,
                object_version,
                engine_mode,
                symbol,
                strategy,
                signal_id,
                decision_id,
                verdict_id,
                verdict_version,
                order_plan_id,
                execution_report_id,
                lease_id,
                state,
                source_agent,
                self.authority_mode,
                idempotency_key,
                _sha256_json(payload),
                self._json_param(payload),
            )
            self._execute(sql, params)
            with self._lock:
                self.stats.object_rows += 1
            return True
        except Exception as exc:  # noqa: BLE001 - fail-soft spine writer
            self._record_failure(f"publish_{object_type}", exc)
            return False

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        with get_pg_conn() as conn:
            if conn is None:
                raise RuntimeError("pg_unavailable")
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()

    def _query(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        try:
            with get_pg_conn() as conn:
                if conn is None:
                    raise RuntimeError("pg_unavailable")
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
                    columns = [desc[0] for desc in (cur.description or [])]
                if not columns:
                    return []
                return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:  # noqa: BLE001 - fail-soft reader
            self._record_failure("query", exc)
            return []

    def _bounded_payload(self, value: Any) -> Any:
        try:
            redacted = self._redact(value)
            encoded = json.dumps(redacted, sort_keys=True, default=str).encode("utf-8")
            if len(encoded) <= self.max_payload_bytes:
                return redacted
            return {
                "payload_truncated": True,
                "original_bytes": len(encoded),
                "max_payload_bytes": self.max_payload_bytes,
                "summary_hash": hashlib.sha256(encoded).hexdigest(),
            }
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self.stats.serialization_failures += 1
                self.stats.last_error = f"serialization:{type(exc).__name__}"
            raise

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                key_lower = key_text.lower()
                if (
                    key_lower in _SENSITIVE_KEYS
                    or key_lower.endswith("_secret")
                    or key_lower.endswith("_token")
                    or key_lower.endswith("_password")
                ):
                    out[key_text] = "[REDACTED]"
                else:
                    out[key_text] = self._redact(item)
            return out
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        if isinstance(value, tuple):
            return [self._redact(item) for item in value]
        return value

    def _json_param(self, payload: Any) -> Any:
        if Json is None:
            return payload
        return Json(payload)

    def _inc_disabled(self) -> None:
        with self._lock:
            self.stats.disabled += 1

    def _record_failure(self, op: str, exc: Exception) -> None:
        with self._lock:
            self.stats.write_failures += 1
            self.stats.last_error = f"{op}:{type(exc).__name__}"
        logger.warning("agent_spine_client %s failed (fail-soft): %s", op, exc)
