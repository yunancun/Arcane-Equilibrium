#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from bybit_path_policy import get_thought_gate_runtime_dir

RUNTIME_BASE = get_thought_gate_runtime_dir()


def read_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def unique_list(items: List[Any]) -> List[Any]:
    seen = set()
    out: List[Any] = []
    for item in items or []:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else repr(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def mkcheck(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def write_report(prefix: str, report: Dict[str, Any]) -> None:
    raw_ts = report.get("ts_ms")
    ts_ms = int(raw_ts) if raw_ts is not None and raw_ts != 0 else int(time.time() * 1000)
    latest = RUNTIME_BASE / f"{prefix}_latest.json"
    dated = RUNTIME_BASE / f"{prefix}_{ts_ms}.json"
    write_json(latest, report)
    write_json(dated, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")
