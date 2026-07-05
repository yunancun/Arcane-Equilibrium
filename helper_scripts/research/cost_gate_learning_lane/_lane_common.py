"""cost-gate demo-learning-lane 內部共用純函數葉節點。

MODULE_NOTE:
  模塊用途：集中放置跨檔逐字節相同、無狀態的小工具函數，消除 lane 腳本群
    重複繳付的樣板 token 稅。只收錄經 AST 驗證跨檔 byte-identical 的 helper。
  主要函數：utc_now、as_dict、as_list、as_str、file_sha256。
  依賴：僅標準庫（datetime、hashlib、pathlib、typing）。
  硬邊界：本檔為純葉節點，不 import 套件內任何其他檔（防 import cycle）；
    schema 版本字串 / authority 集合 / boundary 文字屬各腳本自身契約面，
    一律不得移入此檔（移入即改動 Rust 讀取的 emitted bytes，違反凍結契約）。

命名決策：匯出名去掉前導底線（utc_now 而非 _utc_now），呼叫端以
  ``from ..._lane_common import utc_now as _utc_now`` alias-import，讓函數體內
  ``_utc_now()`` / ``_dict(...)`` 等引用保持逐字節不變 —— 這是 byte-identity
  parity oracle 的載重點：只有 top-of-file 的 def 消失、只多一行 import。

以下 5 個函數體逐字節取自套件內主流變體（AST 驗證：utc_now 87/87、
list 68/68、sha256 20/20、dict 78 主流、str 65 主流），不得改寫成「更乾淨」版本。
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path
from typing import Any


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_str(value: Any) -> str:
    return str(value or "").strip()


def file_sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()
