#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared utility functions for I-chapter (Decision Lease) modules.
I 章（决策租约）模块的共享工具函数。

MODULE_NOTE / 模块说明
---------------------
Consolidates read_json, save_report, as_list, merged_unique, uniq
that were previously copy-pasted across 30+ files in this directory.
将之前在本目录 30+ 个文件中重复定义的工具函数统一到此处。

Functions / 函数
----------------
- read_json(path) -> Optional[Dict]   安全读取 JSON，缺失/损坏返回 None
- read_json_required(path) -> Dict     读取 JSON，缺失/损坏返回 {}
- save_report(report, latest_path)     保存 latest + dated 两份 JSON（参数化路径）
- save_report_stem(obj, base, stem)    保存 latest + dated 两份 JSON（STEM 模式）
- as_list(value) -> List               值转列表
- merged_unique(*parts) -> List        合并去重（保序，支持 dict/list 元素）
- uniq(items) -> List[str]             字符串列表去重（保序）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    """
    Read a JSON file safely. Returns None if file missing or corrupt.
    安全读取 JSON 文件。文件缺失或损坏时返回 None。
    """
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_json_required(path: Path) -> Dict[str, Any]:
    """
    Read a JSON file, raising on read errors but returning {} if missing.
    For backward compat with scripts that did: ``json.loads(path.read_text())``.
    读取 JSON 文件，文件缺失时返回空字典。
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(
    report: Dict[str, Any],
    latest_path: Path,
    *,
    print_json: bool = False,
) -> None:
    """
    Save a report as JSON to both a latest file and a dated file.
    Path is passed explicitly. Optionally prints the full JSON to stdout.
    保存报告为 JSON：同时写入 latest 文件和 dated 文件（路径参数化）。
    """
    ts_ms = report.get("ts_ms")
    dated_path = latest_path.with_name(
        latest_path.stem.replace("_latest", f"_{ts_ms}") + latest_path.suffix
    )
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(content, encoding="utf-8")
    dated_path.write_text(content, encoding="utf-8")
    if print_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")


def save_report_stem(obj: Dict[str, Any], base: Path, stem: str) -> None:
    """
    Save a report using BASE + STEM naming convention (legacy pattern).
    Also prints the full JSON to stdout.
    使用 BASE + STEM 命名惯例保存报告（旧模式），同时打印 JSON 到标准输出。
    """
    latest = base / f"{stem}_latest.json"
    dated = base / f"{stem}_{obj['ts_ms']}.json"
    content = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    latest.write_text(content, encoding="utf-8")
    dated.write_text(content, encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


def as_list(value: Any) -> List[Any]:
    """Coerce a value to a list. Non-list values become []. / 将值转为列表。"""
    return value if isinstance(value, list) else []


def merged_unique(*parts: Any) -> List[Any]:
    """
    Merge multiple lists/values into a deduplicated list preserving order.
    Supports dict/list elements via JSON serialization for dedup keys.
    合并去重（保序），支持 dict/list 元素。
    """
    out: List[Any] = []
    seen: set[str] = set()
    for part in parts:
        for item in as_list(part):
            if item is None:
                continue
            key = (
                json.dumps(item, ensure_ascii=False, sort_keys=True)
                if isinstance(item, (dict, list))
                else str(item)
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def uniq(items: List[str]) -> List[str]:
    """Deduplicate a string list preserving order. / 字符串列表去重（保序）。"""
    return list(dict.fromkeys(items))
