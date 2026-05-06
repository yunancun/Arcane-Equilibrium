"""
Durable event-store writer for the 5-Agent advisory/event foundation.

MODULE_NOTE (中文):
  AgentEventStore 是 MAG-010..012 的唯一寫入口，負責把 legacy/advisory
  MessageBus、Agent lifecycle、AI invocation 寫入既有 agent.* 表。
  M1 階段默認關閉；啟用後 DB / serialization 失敗只影響可觀測性，不改交易行為。
  禁止在此持久化 raw prompt、raw response、secret、token、cookie、stack trace。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

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
class AgentEventStoreStats:
    """In-process counters used for logs/tests; DB remains source of truth."""

    disabled: int = 0
    message_rows: int = 0
    state_rows: int = 0
    ai_rows: int = 0
    write_failures: int = 0
    serialization_failures: int = 0
    last_error: Optional[str] = None


def _env_enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip() == "1"


def _utc_from_ms(ts_ms: Optional[int]) -> datetime:
    if not ts_ms:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)


def _sha256_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _safe_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


class AgentEventStore:
    """Single writer for `agent.messages`, `agent.state_changes`, and AI calls."""

    def __init__(
        self,
        *,
        enabled: Optional[bool] = None,
        max_payload_bytes: Optional[int] = None,
    ) -> None:
        self.enabled = (
            _env_enabled("OPENCLAW_AGENT_EVENT_STORE_ENABLED")
            if enabled is None
            else bool(enabled)
        )
        self.max_payload_bytes = int(
            max_payload_bytes
            if max_payload_bytes is not None
            else os.getenv("OPENCLAW_AGENT_EVENT_STORE_MAX_PAYLOAD_BYTES", "65536")
        )
        self.stats = AgentEventStoreStats()
        self._lock = threading.Lock()

    def record_message(self, message: Any, *, engine_mode: Optional[str] = None) -> bool:
        if not self.enabled:
            self._inc_disabled()
            return False
        try:
            payload = self._bounded_payload(getattr(message, "payload", {}) or {})
            context_id = payload.get("context_id") if isinstance(payload, dict) else None
            if engine_mode and isinstance(payload, dict):
                payload.setdefault("engine_mode", engine_mode)
            sql = """
                INSERT INTO agent.messages (
                    ts, message_id, from_agent, to_agent, message_type,
                    priority, payload, context_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                _utc_from_ms(getattr(message, "timestamp_ms", None)),
                str(getattr(message, "message_id", "")),
                self._enum_value(getattr(message, "sender", "")),
                self._enum_value(getattr(message, "receiver", "")),
                self._enum_value(getattr(message, "message_type", "")),
                str(getattr(message, "priority", "")),
                self._json_param(payload),
                context_id,
            )
            self._execute(sql, params)
            with self._lock:
                self.stats.message_rows += 1
            return True
        except Exception as exc:  # noqa: BLE001 - fail-soft observability writer
            self._record_failure("record_message", exc)
            return False

    def message_sink(self, message: Any) -> None:
        """Callback shape for MessageBus; never raises to caller."""
        self.record_message(message)

    def record_state_change(
        self,
        *,
        agent_name: str,
        from_state: Optional[str],
        to_state: str,
        trigger_event: str,
        details: Optional[dict[str, Any]] = None,
        engine_mode: Optional[str] = None,
    ) -> bool:
        if not self.enabled:
            self._inc_disabled()
            return False
        try:
            payload = dict(details or {})
            if engine_mode is not None:
                payload.setdefault("engine_mode", engine_mode)
            sql = """
                INSERT INTO agent.state_changes (
                    ts, agent_name, from_state, to_state, trigger_event, details
                )
                VALUES (now(), %s, %s, %s, %s, %s)
            """
            params = (
                agent_name,
                from_state,
                to_state,
                trigger_event,
                self._json_param(self._bounded_payload(payload)),
            )
            self._execute(sql, params)
            with self._lock:
                self.stats.state_rows += 1
            return True
        except Exception as exc:  # noqa: BLE001 - fail-soft observability writer
            self._record_failure("record_state_change", exc)
            return False

    def record_ai_invocation(
        self,
        *,
        invocation_id: Optional[str] = None,
        provider: str,
        model: str,
        tier: Optional[str] = None,
        purpose: str,
        prompt_hash: Optional[str] = None,
        prompt_material: Optional[str] = None,
        response_hash: Optional[str] = None,
        response_material: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        cost_usd: Decimal | float | int | None = None,
        latency_ms: Optional[int | float] = None,
        success: bool,
        response_summary: Optional[str] = None,
        context_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        engine_mode: Optional[str] = None,
    ) -> bool:
        if not self.enabled:
            self._inc_disabled()
            return False
        try:
            detail_payload = dict(details or {})
            resolved_response_hash = response_hash or _sha256_text(response_material)
            if resolved_response_hash:
                detail_payload.setdefault("response_hash", resolved_response_hash)
            safe_details = self._bounded_payload(detail_payload)
            resolved_prompt_hash = prompt_hash or _sha256_text(prompt_material)
            sql = """
                INSERT INTO agent.ai_invocations (
                    ts, invocation_id, provider, model, tier, purpose,
                    prompt_hash, input_tokens, output_tokens, cost_usd,
                    latency_ms, success, response_summary, context_id,
                    details, engine_mode
                )
                VALUES (
                    now(), %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s
                )
            """
            params = (
                invocation_id or f"ai_{uuid.uuid4().hex[:16]}",
                provider,
                model,
                tier,
                purpose,
                resolved_prompt_hash,
                int(input_tokens or 0),
                int(output_tokens or 0),
                _safe_float(cost_usd),
                int(latency_ms or 0),
                bool(success),
                self._safe_summary(response_summary),
                context_id,
                self._json_param(safe_details),
                engine_mode,
            )
            self._execute(sql, params)
            with self._lock:
                self.stats.ai_rows += 1
            return True
        except Exception as exc:  # noqa: BLE001 - fail-soft observability writer
            self._record_failure("record_ai_invocation", exc)
            return False

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        with get_pg_conn() as conn:
            if conn is None:
                raise RuntimeError("pg_unavailable")
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()

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
        except Exception as exc:  # noqa: BLE001 - event should drop safely
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

    def _json_param(self, value: Any) -> Any:
        if Json is None:
            return value
        return Json(value)

    @staticmethod
    def _enum_value(value: Any) -> str:
        return str(getattr(value, "value", value))

    @staticmethod
    def _safe_summary(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return str(value)[:512]

    def _inc_disabled(self) -> None:
        with self._lock:
            self.stats.disabled += 1

    def _record_failure(self, op: str, exc: Exception) -> None:
        with self._lock:
            self.stats.write_failures += 1
            self.stats.last_error = f"{op}:{type(exc).__name__}"
        logger.warning("AgentEventStore %s failed: %s", op, type(exc).__name__)


_AGENT_EVENT_STORE: Optional[AgentEventStore] = None
_AGENT_EVENT_STORE_LOCK = threading.Lock()


def get_agent_event_store() -> AgentEventStore:
    global _AGENT_EVENT_STORE
    with _AGENT_EVENT_STORE_LOCK:
        if _AGENT_EVENT_STORE is None:
            _AGENT_EVENT_STORE = AgentEventStore()
        return _AGENT_EVENT_STORE
