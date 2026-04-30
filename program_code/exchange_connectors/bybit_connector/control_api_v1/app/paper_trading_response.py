"""Shared paper-trading response envelope helpers."""

from __future__ import annotations

from typing import Any


def paper_response(
    data: Any,
    action_result: str = "success",
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Build a simplified response envelope for paper trading routes."""
    return {
        "api_version": "v1",
        "action_result": action_result,
        "reason_codes": reason_codes or [],
        "data_category": "paper_simulated",
        "is_simulated": True,
        "data": data,
    }
