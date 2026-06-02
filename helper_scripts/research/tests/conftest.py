"""Gate-B 探針測試 fixtures。

MODULE_NOTE:
  模塊用途：把 ``helper_scripts/research/`` 加進 sys.path，讓 gate_b_* module 能以
    模組名互相 import（research/ 不是 Python package，無 __init__.py）。
  依賴：pytest + 標準庫。
"""

from __future__ import annotations

import sys
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parent.parent
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))
