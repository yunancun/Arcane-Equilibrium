#!/usr/bin/env python3
"""Tests for grid_trading blocked-symbol config alignment."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python <3.11 fallback
    import tomli as tomllib  # type: ignore[no-redef]

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = Path(os.path.dirname(_HELPER_SCRIPTS_DIR))
sys.path.insert(0, str(_SRV_ROOT))


class TestGridBlockedSymbolsConfig(unittest.TestCase):
    def test_labusdt_blocked_for_grid_across_three_strategy_param_files(self) -> None:
        for kind in ("paper", "demo", "live"):
            path = _SRV_ROOT / "settings" / f"strategy_params_{kind}.toml"
            with path.open("rb") as f:
                data = tomllib.load(f)
            blocked = data["grid_trading"]["blocked_symbols"]
            self.assertIn("LABUSDT", blocked, f"{kind} grid blocklist missing LABUSDT")


if __name__ == "__main__":
    unittest.main()
