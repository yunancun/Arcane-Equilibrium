#!/usr/bin/env python3
"""Compatibility wrapper for the W-AUDIT-8b Stage 0R report CLI."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE / "w_audit_8b"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from funding_skew_stage0r_report import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
