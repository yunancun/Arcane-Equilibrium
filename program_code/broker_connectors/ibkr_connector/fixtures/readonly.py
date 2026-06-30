"""Blocked, secret-free IBKR read-only connector fixture."""

from __future__ import annotations

from ..models import IbkrReadOnlyEndpointConfig, blocked_readonly_status


def blocked_readonly_fixture() -> dict[str, object]:
    config = IbkrReadOnlyEndpointConfig()
    return blocked_readonly_status(config=config).to_dict()
