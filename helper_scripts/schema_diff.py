#!/usr/bin/env python3
"""
schema_diff.py — CI Schema Diff: Python shared_types vs golden JSON schema
CI 類型一致性檢查：Python shared_types 與黃金基準 JSON 比對

MODULE_NOTE:
    [中文] 比對 shared_types.py 中的 Python 類型定義與 golden schema (rust/schemas/shared_types.json)。
           用於 CI 管線防止 Python/Rust 類型漂移。任何欄位/枚舉不一致立即報錯退出。
    [English] Compares Python type definitions in shared_types.py against the golden schema
              (rust/schemas/shared_types.json). Used in CI to prevent Python/Rust type drift.
              Any field/enum mismatch causes immediate failure with clear diagnostics.

Usage:
    python3 helper_scripts/schema_diff.py
    python3 helper_scripts/schema_diff.py --schema /path/to/shared_types.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Resolve paths / 解析路徑
# ---------------------------------------------------------------------------
_SRV_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_SCHEMA = _SRV_DIR.parent / "rust" / "schemas" / "shared_types.json"
_SHARED_TYPES_DIR = (
    _SRV_DIR
    / "program_code"
    / "exchange_connectors"
    / "bybit_connector"
    / "control_api_v1"
    / "app"
)

# ---------------------------------------------------------------------------
# Import shared_types dynamically / 動態載入 shared_types
# ---------------------------------------------------------------------------

def _import_shared_types() -> Any:
    """Import shared_types.py without relying on package structure.
    不依賴包結構直接匯入 shared_types.py。"""
    import importlib.util
    import sys as _sys
    spec = importlib.util.spec_from_file_location(
        "shared_types", _SHARED_TYPES_DIR / "shared_types.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load shared_types.py from {_SHARED_TYPES_DIR}")
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["shared_types"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Type mapping helpers / 類型映射工具
# ---------------------------------------------------------------------------
_PY_TYPE_MAP = {
    int: "int",
    float: "float",
    str: "string",
    bool: "bool",
}


def _resolve_annotation(annotation: Any, globalns: dict | None = None) -> Any:
    """Resolve string annotations (from __future__ annotations) to real types.
    解析字串型別註釋為實際類型（因 __future__ annotations 導致延遲求值）。"""
    if isinstance(annotation, str):
        import typing
        ns = {**vars(typing), "frozenset": frozenset}
        if globalns:
            ns.update(globalns)
        try:
            return eval(annotation, ns)  # noqa: S307
        except Exception:
            return annotation
    return annotation


def _python_type_str(annotation: Any, globalns: dict | None = None) -> str:
    """Convert a Python type annotation to a schema type string.
    將 Python 型別註釋轉為 schema 類型字串。"""
    annotation = _resolve_annotation(annotation, globalns)

    # Still a string after resolution — unknown
    if isinstance(annotation, str):
        return "unknown"

    origin = getattr(annotation, "__origin__", None)

    # Handle Union (X | None) for optional types
    # 處理 Union 型別（可選欄位）
    import types as _types
    if isinstance(annotation, _types.UnionType):
        args = annotation.__args__
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and type(None) in args:
            base = _PY_TYPE_MAP.get(non_none[0], "unknown")
            return f"optional_{base}"
    # typing.Union fallback
    import typing
    if origin is typing.Union:
        args = annotation.__args__
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and type(None) in args:
            base = _PY_TYPE_MAP.get(non_none[0], "unknown")
            return f"optional_{base}"

    # frozenset / list of strings
    if annotation is frozenset or (origin in (frozenset, list)):
        return "list_string"

    return _PY_TYPE_MAP.get(annotation, "unknown")


def _extract_python_schema(mod: Any) -> dict[str, Any]:
    """Extract type schema from loaded shared_types module.
    從已載入的 shared_types 模組提取類型 schema。"""
    schema: dict[str, Any] = {}
    exported = getattr(mod, "__all__", [])

    # Build namespace for resolving stringified annotations
    # 建構命名空間以解析字串化的型別註釋
    mod_globals = vars(mod)

    for name in exported:
        cls = getattr(mod, name, None)
        if cls is None:
            continue

        # IntEnum
        if isinstance(cls, type) and issubclass(cls, IntEnum):
            schema[name] = {
                "kind": "int_enum",
                "variants": {m.name: m.value for m in cls},
            }
        # str Enum
        elif isinstance(cls, type) and issubclass(cls, Enum):
            schema[name] = {
                "kind": "str_enum",
                "variants": {m.name: m.value for m in cls},
            }
        # dataclass
        elif dataclasses.is_dataclass(cls) and isinstance(cls, type):
            fields_schema: dict[str, Any] = {}
            for f in dataclasses.fields(cls):
                finfo: dict[str, Any] = {"type": _python_type_str(f.type, mod_globals)}
                if (
                    f.default is not dataclasses.MISSING
                    and not callable(f.default)
                ):
                    finfo["default"] = f.default
                elif f.default_factory is not dataclasses.MISSING:
                    # Evaluate factory for simple defaults
                    # 對簡單預設值執行 factory
                    pass  # list_string has no scalar default
                schema[name] = schema.get(name, {"kind": "struct", "fields": {}})
                fields_schema[f.name] = finfo
            schema[name] = {"kind": "struct", "fields": fields_schema}
        # __slots__ class (PriceEvent)
        elif hasattr(cls, "__slots__"):
            fields_schema = {}
            import inspect
            sig = inspect.signature(cls.__init__)
            for pname, param in sig.parameters.items():
                if pname == "self":
                    continue
                ann = param.annotation
                if ann is inspect.Parameter.empty:
                    ftype = "unknown"
                else:
                    ftype = _python_type_str(ann, mod_globals)
                finfo = {"type": ftype}
                if param.default is not inspect.Parameter.empty:
                    finfo["default"] = param.default
                fields_schema[pname] = finfo
            schema[name] = {"kind": "struct", "fields": fields_schema}

    return schema


# ---------------------------------------------------------------------------
# Comparison / 比較邏輯
# ---------------------------------------------------------------------------

def _compare(golden: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Compare golden schema types against actual extracted schema.
    比較黃金基準與實際提取的 schema，回傳差異列表。"""
    errors: list[str] = []

    for type_name, gdef in golden.items():
        if type_name not in actual:
            errors.append(f"MISSING type: {type_name} not found in Python shared_types")
            continue

        adef = actual[type_name]
        if gdef["kind"] != adef["kind"]:
            errors.append(
                f"{type_name}: kind mismatch — golden={gdef['kind']}, actual={adef['kind']}"
            )
            continue

        if gdef["kind"] in ("int_enum", "str_enum"):
            gv = gdef["variants"]
            av = adef["variants"]
            if gv != av:
                missing = set(gv) - set(av)
                extra = set(av) - set(gv)
                if missing:
                    errors.append(f"{type_name}: missing variants: {sorted(missing)}")
                if extra:
                    errors.append(f"{type_name}: extra variants: {sorted(extra)}")
                for k in set(gv) & set(av):
                    if gv[k] != av[k]:
                        errors.append(
                            f"{type_name}.{k}: value mismatch — golden={gv[k]}, actual={av[k]}"
                        )

        elif gdef["kind"] == "struct":
            gfields = gdef["fields"]
            afields = adef["fields"]
            gmissing = set(gfields) - set(afields)
            gextra = set(afields) - set(gfields)
            if gmissing:
                errors.append(f"{type_name}: missing fields: {sorted(gmissing)}")
            if gextra:
                errors.append(f"{type_name}: extra fields: {sorted(gextra)}")
            for fname in set(gfields) & set(afields):
                gf = gfields[fname]
                af = afields[fname]
                if gf["type"] != af["type"]:
                    errors.append(
                        f"{type_name}.{fname}: type mismatch — "
                        f"golden={gf['type']}, actual={af['type']}"
                    )

    # Check for types in actual but not in golden
    # 檢查 actual 中有但 golden 中沒有的類型
    extra_types = set(actual) - set(golden)
    if extra_types:
        errors.append(f"Extra types not in golden schema: {sorted(extra_types)}")

    return errors


# ---------------------------------------------------------------------------
# Main / 主程式
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Python shared_types against golden JSON schema"
    )
    parser.add_argument(
        "--schema", type=Path, default=_DEFAULT_SCHEMA,
        help="Path to golden shared_types.json"
    )
    args = parser.parse_args()

    # Load golden schema / 載入黃金基準
    schema_path: Path = args.schema
    if not schema_path.exists():
        print(f"ERROR: Golden schema not found: {schema_path}", file=sys.stderr)
        return 1

    with open(schema_path) as f:
        golden_raw = json.load(f)
    golden_types = golden_raw.get("types", {})

    # Extract Python schema / 提取 Python schema
    try:
        mod = _import_shared_types()
    except ImportError as e:
        print(f"ERROR: Cannot import shared_types: {e}", file=sys.stderr)
        return 1

    py_schema = _extract_python_schema(mod)

    # Compare / 比較
    errors = _compare(golden_types, py_schema)

    if errors:
        print(f"SCHEMA DRIFT DETECTED — {len(errors)} issue(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"OK: {len(golden_types)} types validated, Python matches golden schema.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
