from __future__ import annotations

"""
Context distillation for Layer 2 prompt inputs.

This module is intentionally a pure stdlib leaf:
- no provider/network calls
- no database or IPC dependency
- no trading authority

It turns noisy runtime dictionaries into a compact, deterministic JSON prompt
section for manual/supervisor Layer 2 analysis.
"""

import copy
import json
import math
import threading
from dataclasses import dataclass
from typing import Any


_SECTION_ORDER = ("market", "portfolio", "health", "events", "pressure", "dream")


@dataclass(frozen=True)
class ContextDistillationConfig:
    max_events: int = 8
    max_positions: int = 8
    max_health_items: int = 12
    max_str_chars: int = 160
    max_prompt_chars: int = 2000


class ContextDistiller:
    """Thread-safe compact context cache for L2 prompt construction."""

    def __init__(self, config: ContextDistillationConfig | None = None) -> None:
        self._config = config or ContextDistillationConfig()
        self._summary: dict[str, Any] = {}
        self._lock = threading.Lock()

    def update_after_each_cycle(self, cycle_data: dict[str, Any]) -> None:
        """Replace the cached summary with a compact copy of the latest cycle."""
        summary = self.distill_mapping(cycle_data)
        with self._lock:
            self._summary = summary

    def snapshot(self) -> dict[str, Any]:
        """Return a deep copy so caller mutation cannot leak into the cache."""
        with self._lock:
            return copy.deepcopy(self._summary)

    def build_prompt_context(
        self,
        *,
        question: str = "",
        extra_context: dict[str, Any] | str | None = None,
        max_chars: int | None = None,
    ) -> str:
        """Build a bounded JSON prompt context from cached and extra context."""
        payload: dict[str, Any] = {}
        cached = self.snapshot()
        if cached:
            payload["cached"] = cached
        if extra_context:
            if isinstance(extra_context, str):
                payload["extra"] = self._bounded_str(extra_context)
            else:
                payload["extra"] = self.distill_mapping(extra_context)
        if question:
            payload["question"] = self._bounded_str(question)
        return self._to_prompt_json(payload, max_chars=max_chars)

    def distill_for_prompt(
        self,
        context: dict[str, Any] | str,
        *,
        max_chars: int | None = None,
    ) -> str:
        """Compact an ad-hoc context object for direct prompt insertion."""
        if isinstance(context, str):
            parsed = self._parse_json_object(context)
            if parsed is None:
                return self._bounded_str(context, max_chars=max_chars)
            return self._to_prompt_json(self.distill_mapping(parsed), max_chars=max_chars)
        return self._to_prompt_json(self.distill_mapping(context), max_chars=max_chars)

    def distill_mapping(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize known V3 ContextDistiller sections into compact JSON."""
        if not isinstance(data, dict):
            return {}

        result: dict[str, Any] = {}

        market = self._distill_market(data)
        if market:
            result["market"] = market

        portfolio = self._distill_portfolio(data)
        if portfolio:
            result["portfolio"] = portfolio

        health = self._distill_health(data)
        if health:
            result["health"] = health

        events = self._distill_events(data)
        if events:
            result["events"] = events

        pressure = self._distill_section(data, "pressure", max_items=self._config.max_health_items)
        if pressure:
            result["pressure"] = pressure

        dream = self._distill_section(data, "dream", max_items=self._config.max_health_items)
        if dream:
            result["dream"] = dream

        return {key: result[key] for key in _SECTION_ORDER if key in result}

    def _distill_market(self, data: dict[str, Any]) -> dict[str, Any]:
        source = data.get("market") if isinstance(data.get("market"), dict) else data
        fields = (
            "symbol",
            "btc_price",
            "price",
            "last_price",
            "btc_change",
            "btc_24h_change",
            "change_24h_pct",
            "regime",
            "hurst",
            "vol_state",
            "funding_rate",
            "open_interest",
        )
        return self._pick_fields(source, fields)

    def _distill_portfolio(self, data: dict[str, Any]) -> dict[str, Any]:
        source = data.get("portfolio") if isinstance(data.get("portfolio"), dict) else data
        fields = (
            "balance",
            "equity",
            "delta_pct",
            "daily_pnl",
            "weekly_pnl",
            "drawdown",
            "current_dd",
            "margin_usage_pct",
        )
        result = self._pick_fields(source, fields)
        positions = source.get("positions") if isinstance(source, dict) else None
        if isinstance(positions, list):
            result["positions"] = [
                self._compact_position(pos) for pos in positions[: self._config.max_positions]
            ]
            result["position_count"] = len(positions)
        elif isinstance(positions, int):
            result["position_count"] = max(0, positions)
        return result

    def _distill_health(self, data: dict[str, Any]) -> dict[str, Any]:
        for key in ("health", "strategy_health", "system_health"):
            if isinstance(data.get(key), dict):
                return self._compact_dict(data[key], max_items=self._config.max_health_items)
        return {}

    def _distill_events(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        raw = data.get("events", data.get("recent_events", []))
        if not isinstance(raw, list):
            return []
        return [self._compact_event(item) for item in raw[: self._config.max_events]]

    def _distill_section(
        self,
        data: dict[str, Any],
        key: str,
        *,
        max_items: int,
    ) -> dict[str, Any]:
        value = data.get(key)
        if not isinstance(value, dict):
            return {}
        return self._compact_dict(value, max_items=max_items)

    def _pick_fields(self, source: Any, fields: tuple[str, ...]) -> dict[str, Any]:
        if not isinstance(source, dict):
            return {}
        result: dict[str, Any] = {}
        for field in fields:
            if field in source and source[field] is not None:
                result[field] = self._compact_value(source[field])
        return result

    def _compact_position(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {"value": self._compact_value(value)}
        return self._pick_fields(
            value,
            (
                "symbol",
                "side",
                "qty",
                "notional_usd",
                "entry_price",
                "mark_price",
                "unrealized_pnl",
                "unrealized_pnl_pct",
            ),
        )

    def _compact_event(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {"summary": self._bounded_str(str(value))}
        event = self._pick_fields(
            value,
            (
                "ts_ms",
                "timestamp_ms",
                "event_type",
                "type",
                "symbol",
                "severity",
                "confidence",
                "reason",
                "summary",
                "headline",
            ),
        )
        if "reason" not in event and "message" in value:
            event["reason"] = self._bounded_str(str(value["message"]))
        return event

    def _compact_dict(self, value: dict[str, Any], *, max_items: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in sorted(value.keys())[:max_items]:
            result[str(key)] = self._compact_value(value[key])
        return result

    def _compact_value(self, value: Any) -> Any:
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return round(value, 6) if math.isfinite(value) else None
        if isinstance(value, str):
            return self._bounded_str(value)
        if isinstance(value, list):
            return [self._compact_value(item) for item in value[: self._config.max_events]]
        if isinstance(value, dict):
            return self._compact_dict(value, max_items=self._config.max_health_items)
        return self._bounded_str(str(value))

    def _bounded_str(self, value: str, *, max_chars: int | None = None) -> str:
        limit = max_chars or self._config.max_str_chars
        if len(value) <= limit:
            return value
        suffix = "...<truncated>"
        return value[: max(0, limit - len(suffix))] + suffix

    def _to_prompt_json(self, payload: dict[str, Any], *, max_chars: int | None = None) -> str:
        limit = max_chars or self._config.max_prompt_chars
        text = self._json(payload)
        if len(text) <= limit:
            return text

        slim = copy.deepcopy(payload)
        for path in (
            ("events",),
            ("cached", "events"),
            ("extra", "events"),
            ("dream",),
            ("cached", "dream"),
            ("extra", "dream"),
        ):
            self._drop_path(slim, path)
            text = self._json(slim)
            if len(text) <= limit:
                return text

        suffix = "...<truncated>"
        return text[: max(0, limit - len(suffix))] + suffix

    @staticmethod
    def _json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _drop_path(payload: dict[str, Any], path: tuple[str, ...]) -> None:
        cur: Any = payload
        for key in path[:-1]:
            if not isinstance(cur, dict):
                return
            cur = cur.get(key)
        if isinstance(cur, dict):
            cur.pop(path[-1], None)

    @staticmethod
    def _parse_json_object(value: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
