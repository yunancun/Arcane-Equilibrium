#!/usr/bin/env python3
"""Thin shim that delegates to the ``passive_wait_healthcheck`` package.
薄殼，將呼叫委派給 ``passive_wait_healthcheck`` package。

Pre-split this file was a 2294-line monolith holding 19 healthchecks
(G5-FUP-PASSIVE-HEALTH split, 2026-04-26 — 91% over CLAUDE.md §九 1200
hard cap). Implementation moved to the sibling
``passive_wait_healthcheck/`` package; this file remains as the cron
entry point so the path stays identical:

  0 */6 * * * .../helper_scripts/db/passive_wait_healthcheck_cron.sh
                  └─ python3 helper_scripts/db/passive_wait_healthcheck.py

Cron invokes by absolute path, which does not put this file's directory
on ``sys.path`` — we prepend it before importing the sibling package so
the existing wrapper scripts work unchanged.

拆分前 2294 行（CLAUDE.md §九 91% 超標）。實作移到同級
``passive_wait_healthcheck/`` package；本檔留為 CLI 入口維持 cron 路徑。
"""
from __future__ import annotations

import sys
from pathlib import Path

# Prepend this file's directory so ``passive_wait_healthcheck`` package
# resolves when cron invokes by absolute path (sys.path otherwise misses it).
# Prepend 本檔目錄，讓 cron 絕對路徑呼叫時 sibling package 仍 import 得到。
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from passive_wait_healthcheck import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
