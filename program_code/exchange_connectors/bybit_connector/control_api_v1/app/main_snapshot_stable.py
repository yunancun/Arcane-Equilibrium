from __future__ import annotations

"""
Compatibility entrypoint for OpenClaw / Bybit Control API.
OpenClaw / Bybit 控制 API 的兼容入口。

This module is kept so existing commands using
`uvicorn app.main_snapshot_stable:app` continue to work.
"""

from .main import app
