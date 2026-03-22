#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

RUNTIME_BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return read_json(path)


def unique_list(items: List[Any]) -> List[Any]:
    seen = set()
    out: List[Any] = []
    for item in items:
        if item is None:
            continue
        key = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def mkcheck(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "detail": detail,
    }


def write_report(prefix: str, obj: Dict[str, Any]) -> Tuple[Path, Path]:
    RUNTIME_BASE.mkdir(parents=True, exist_ok=True)
    ts_ms = obj.get("ts_ms")
    latest = RUNTIME_BASE / f"{prefix}_latest.json"
    dated = RUNTIME_BASE / f"{prefix}_{ts_ms}.json"
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    latest.write_text(text, encoding="utf-8")
    dated.write_text(text, encoding="utf-8")
    print(text)
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")
    return latest, dated
