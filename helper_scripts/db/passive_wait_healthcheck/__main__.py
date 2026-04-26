"""Entry point for ``python3 -m passive_wait_healthcheck``.
``python3 -m passive_wait_healthcheck`` 入口點。

MODULE_NOTE (EN/中): Allows the package to be invoked as
``python3 -m helper_scripts.db.passive_wait_healthcheck`` (or any other
path the operator's PYTHONPATH happens to land on). The cron entry
remains the thin shim ``passive_wait_healthcheck.py``; this module is a
convenience for ad-hoc invocation.
允許用 ``python3 -m`` 形式呼叫；cron 入口仍走 thin shim
``passive_wait_healthcheck.py``，本檔僅供臨時 ad-hoc 呼叫便利。
"""

from __future__ import annotations

import sys

from .runner import main

if __name__ == "__main__":
    sys.exit(main())
