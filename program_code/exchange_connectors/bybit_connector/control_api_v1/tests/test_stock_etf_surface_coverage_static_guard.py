from __future__ import annotations

from pathlib import Path

from stock_etf_static_guard_helpers import (
    CONTROL_API_DIR,
    SRV_ROOT,
    candidate_stock_etf_control_api_python_files,
    candidate_stock_etf_ibkr_python_files,
    candidate_stock_etf_static_gui_files,
)


def _relative(paths: list[Path]) -> set[str]:
    return {path.relative_to(SRV_ROOT).as_posix() for path in paths}


def test_stock_etf_python_static_guard_candidate_scope_is_complete() -> None:
    app_dir = CONTROL_API_DIR / "app"
    expected = {
        path.relative_to(SRV_ROOT).as_posix()
        for path in app_dir.iterdir()
        if path.is_file()
        and path.suffix == ".py"
        and ("stock_etf" in path.name or "ibkr" in path.name)
    }
    expected.add(
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/stock_etf_routes.py"
    )

    assert _relative(candidate_stock_etf_control_api_python_files()) == expected


def test_stock_etf_ibkr_python_static_guard_candidate_scope_includes_connector_package() -> None:
    connector_dir = SRV_ROOT / "program_code/broker_connectors/ibkr_connector"
    expected = {
        path.relative_to(SRV_ROOT).as_posix()
        for path in connector_dir.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    expected.update(_relative(candidate_stock_etf_control_api_python_files()))

    assert _relative(candidate_stock_etf_ibkr_python_files()) == expected


def test_stock_etf_static_gui_guard_candidate_scope_is_complete() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    expected = {
        path.relative_to(SRV_ROOT).as_posix()
        for path in static_dir.iterdir()
        if path.is_file() and path.name.startswith("tab-stock-etf")
    }

    assert _relative(candidate_stock_etf_static_gui_files()) == expected


def test_stock_etf_surface_guard_scope_excludes_bybit_runtime_modules() -> None:
    all_candidates = (
        _relative(candidate_stock_etf_control_api_python_files())
        | _relative(candidate_stock_etf_ibkr_python_files())
        | _relative(candidate_stock_etf_static_gui_files())
    )

    forbidden_fragments = (
        "bybit_rest_client",
        "bybit_private_ws",
        "order_manager",
        "order_router",
        "bounded_probe_active_order",
    )
    violations = [
        path
        for path in all_candidates
        if any(fragment in path for fragment in forbidden_fragments)
    ]

    assert violations == []
