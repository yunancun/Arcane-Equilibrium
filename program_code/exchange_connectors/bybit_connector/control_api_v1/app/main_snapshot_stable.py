from __future__ import annotations

"""
MODULE_NOTE (中文):
  兼容性入口 — 保留此模組使舊的 `uvicorn app.main_snapshot_stable:app` 命令
  繼續工作。僅 re-export main.py 的 app 實例，不包含任何獨立邏輯。

MODULE_NOTE (English):
  Compatibility entrypoint — kept so existing commands using
  `uvicorn app.main_snapshot_stable:app` continue to work.
  Only re-exports the app instance from main.py; contains no independent logic.
"""

from .main import app
