#!/usr/bin/env python3
"""
Compatibility import shim / 兼容导入转发层

Purpose:
- keep legacy import path `scripts/bybit_h1_report_utils.py`
- re-export canonical helpers from `misc_tools/bybit_h1_report_utils.py`

Do NOT use runpy here, because many canonical modules import this file as a normal module.
这里不能使用 runpy 包装器，因为很多正式模块会把这里当普通可导入模块使用。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_REAL = (
    Path(__file__).resolve().parents[1]
    / "misc_tools"
    / "bybit_h1_report_utils.py"
)

if not _REAL.exists():
    raise FileNotFoundError(f"Canonical helper not found: {_REAL}")

_spec = importlib.util.spec_from_file_location("_bybit_h1_report_utils_real", str(_REAL))
if _spec is None or _spec.loader is None:
    raise ImportError(f"Unable to load canonical helper: {_REAL}")

_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

THOUGHT_GATE_DIR = _mod.THOUGHT_GATE_DIR
read_json = _mod.read_json
write_json = _mod.write_json
save_latest_and_dated = _mod.save_latest_and_dated
preview_text = _mod.preview_text
make_check = _mod.make_check
try_parse_json_object = _mod.try_parse_json_object

__all__ = [
    "THOUGHT_GATE_DIR",
    "read_json",
    "write_json",
    "save_latest_and_dated",
    "preview_text",
    "make_check",
    "try_parse_json_object",
]
