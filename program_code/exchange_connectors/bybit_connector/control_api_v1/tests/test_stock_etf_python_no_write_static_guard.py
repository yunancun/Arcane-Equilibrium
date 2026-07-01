"""
Stock/ETF IBKR Python no-write static guard.

This test locks the ADR-0048 boundary that Python may expose display/readiness
surfaces only at the current phase. It intentionally scans only Stock/ETF/IBKR
Python surfaces and future IBKR connector paths, not the existing Bybit modules.
"""

from __future__ import annotations

import ast

from stock_etf_static_guard_helpers import (
    FORBIDDEN_FUNCTION_NAMES,
    FORBIDDEN_IBKR_CONNECTOR_RUNTIME_IMPORT_PREFIXES,
    FORBIDDEN_IPC_METHOD_STRINGS,
    candidate_stock_etf_control_api_python_files,
    candidate_stock_etf_ibkr_python_files,
    imported_module_names,
    is_forbidden_module,
    literal_dynamic_import_module,
    record_forbidden_call,
    record_forbidden_dynamic_import,
    record_forbidden_file_write_call,
    record_forbidden_import,
    record_forbidden_os_environ_access,
    record_forbidden_persistence_dynamic_import,
    record_forbidden_persistence_import,
    record_forbidden_runtime_side_effect_call,
    record_forbidden_runtime_side_effect_dynamic_import,
    record_forbidden_runtime_side_effect_import,
    record_forbidden_secret_env_call,
    record_forbidden_secret_env_import,
)


def test_stock_etf_ibkr_python_surface_has_no_direct_broker_write_api() -> None:
    files = candidate_stock_etf_ibkr_python_files()
    assert files, "expected at least the display-only stock_etf_routes.py surface"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in FORBIDDEN_FUNCTION_NAMES:
                    violations.append(f"{path}: function defines forbidden broker write {node.name}()")
            elif isinstance(node, ast.Call):
                record_forbidden_call(path, node, violations)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                record_forbidden_import(path, node, violations)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in FORBIDDEN_IPC_METHOD_STRINGS:
                    violations.append(f"{path}: string exposes forbidden IPC method {node.value!r}")

    assert violations == []


def test_stock_etf_ibkr_python_surface_has_no_network_client_imports() -> None:
    files = candidate_stock_etf_ibkr_python_files()
    assert files, "expected at least the display-only stock_etf_routes.py surface"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                record_forbidden_import(path, node, violations)
            elif isinstance(node, ast.Call):
                record_forbidden_dynamic_import(path, node, violations)

    assert violations == []


def test_stock_etf_ibkr_python_surface_has_no_persistence_or_file_writers() -> None:
    files = candidate_stock_etf_ibkr_python_files()
    assert files, "expected at least the display-only stock_etf_routes.py surface"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                record_forbidden_persistence_import(path, node, violations)
            elif isinstance(node, ast.Call):
                record_forbidden_persistence_dynamic_import(path, node, violations)
                record_forbidden_file_write_call(path, node, violations)

    assert violations == []


def test_stock_etf_ibkr_python_surface_has_no_secret_or_env_material_access() -> None:
    files = candidate_stock_etf_ibkr_python_files()
    assert files, "expected at least the display-only stock_etf_routes.py surface"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                record_forbidden_secret_env_import(path, node, violations)
            elif isinstance(node, ast.Call):
                record_forbidden_secret_env_call(path, node, violations)
            elif isinstance(node, (ast.Attribute, ast.Subscript)):
                record_forbidden_os_environ_access(path, node, violations)

    assert violations == []


def test_stock_etf_ibkr_python_surface_has_no_clock_or_concurrency_side_effects() -> None:
    files = candidate_stock_etf_ibkr_python_files()
    assert files, "expected at least the display-only stock_etf_routes.py surface"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                record_forbidden_runtime_side_effect_import(path, node, violations)
            elif isinstance(node, ast.Call):
                record_forbidden_runtime_side_effect_dynamic_import(path, node, violations)
                record_forbidden_runtime_side_effect_call(path, node, violations)

    assert violations == []


def test_stock_etf_control_api_surface_does_not_import_ibkr_connector_runtime_skeleton() -> None:
    files = candidate_stock_etf_control_api_python_files()
    assert files, "expected Stock/ETF control-api Python surface files"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for module in imported_module_names(node):
                    if is_forbidden_module(
                        module, FORBIDDEN_IBKR_CONNECTOR_RUNTIME_IMPORT_PREFIXES
                    ):
                        violations.append(
                            f"{path}:{node.lineno}: imports connector runtime skeleton {module}"
                        )
            elif isinstance(node, ast.Call):
                module = literal_dynamic_import_module(node)
                if module and is_forbidden_module(
                    module, FORBIDDEN_IBKR_CONNECTOR_RUNTIME_IMPORT_PREFIXES
                ):
                    violations.append(
                        f"{path}:{node.lineno}: dynamically imports connector runtime skeleton {module}"
                    )

    assert violations == []
