from __future__ import annotations

"""Runtime secret resolution helpers.

MODULE_NOTE (English):
  Reads high-value runtime secrets from either direct env vars or companion
  ``*_FILE`` env vars. Batch B uses this to keep DB URLs and IPC HMAC secrets
  out of long-lived child process environments; launch scripts pass file paths
  while the application reads the 0600 file locally.

MODULE_NOTE (中文):
  從直接環境變量或 ``*_FILE`` companion 環境變量解析高價值 runtime secret。
  Batch B 用它把 DB URL / IPC HMAC secret 從長壽命子進程環境移出；啟動腳本只
  傳 file path，應用在本機讀 0600 secret file。
"""

import os
from pathlib import Path


def get_secret_value(name: str) -> str | None:
    """Return ``name`` from env, falling back to ``name_FILE``.

    Empty direct env values are ignored so deployments can intentionally switch
    to file-backed secrets without leaking values through process env.
    """
    value = os.environ.get(name)
    if value:
        return value

    file_path = os.environ.get(f"{name}_FILE", "").strip()
    if not file_path:
        return None

    try:
        secret = Path(file_path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return secret or None
