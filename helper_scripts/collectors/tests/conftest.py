"""listing capture collector 測試 fixtures。

MODULE_NOTE:
  模塊用途：把 ``helper_scripts/collectors/listing_capture/`` 與
    ``helper_scripts/research/`` 加進 sys.path，讓 collector module 與 reuse 的
    gate_b_* 純邏輯能以模組名互相 import（兩目錄皆非可匯入 package path）。
  依賴：pytest + 標準庫。
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_COLLECTORS_DIR = _TESTS_DIR.parent
_LISTING_DIR = _COLLECTORS_DIR / "listing_capture"
_RESEARCH_DIR = _COLLECTORS_DIR.parent / "research"

for _p in (_LISTING_DIR, _RESEARCH_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
