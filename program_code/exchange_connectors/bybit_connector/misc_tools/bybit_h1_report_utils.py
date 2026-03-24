#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from bybit_path_policy import get_thought_gate_runtime_dir

THOUGHT_GATE_DIR = get_thought_gate_runtime_dir()


def read_json(path: Path, default: Optional[Any] = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_latest_and_dated(prefix: str, obj: Dict[str, Any]) -> None:
    ts_ms = int(obj.get("ts_ms") or int(time.time() * 1000))
    latest = THOUGHT_GATE_DIR / f"{prefix}_latest.json"
    dated = THOUGHT_GATE_DIR / f"{prefix}_{ts_ms}.json"
    write_json(latest, obj)
    write_json(dated, obj)
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


def preview_text(value: Optional[str], limit: int = 1600) -> Optional[str]:
    if value is None:
        return None
    s = str(value)
    return s if len(s) <= limit else s[:limit] + "...[truncated]"


def make_check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def try_parse_json_object(text: Optional[str]) -> Optional[Dict[str, Any]]:
    if not text or not str(text).strip():
        return None
    raw = str(text).strip()

    candidates = [raw]
    if raw.startswith("```"):
        trimmed = raw.strip("`").strip()
        if trimmed.lower().startswith("json"):
            trimmed = trimmed[4:].strip()
        candidates.append(trimmed)

    for candidate in candidates:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return None
