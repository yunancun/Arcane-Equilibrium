"""Static guard for the P2-AUDIT-VERIFY-5 blocked-symbol freeze."""

from __future__ import annotations

import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "docs" / "governance_dev" / "strategy_blocked_symbols_freeze.json"


def _load_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def _load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _assert_symbol_list_shape(symbols: list[str]) -> None:
    assert symbols, "blocked symbol freeze cannot be empty"
    assert len(symbols) == len(set(symbols)), f"duplicate blocked symbols: {symbols}"
    for symbol in symbols:
        assert symbol == symbol.upper(), f"symbol must be uppercase: {symbol}"
        assert symbol.endswith("USDT"), f"blocked symbol must be a USDT pair: {symbol}"


def test_registry_policy_requires_rfc_counterfactual_and_dsr_pbo() -> None:
    registry = _load_registry()

    assert registry["status"] == "frozen"
    assert registry["scope"] == "new_entries_only"

    requirements = " ".join(registry["policy"]["new_block_requirements"]).lower()
    assert "rfc" in requirements
    assert "counterfactual" in requirements
    assert "dsr/pbo" in requirements

    report = ROOT / registry["counterfactual_report"]
    assert report.exists(), f"counterfactual report missing: {report}"


def test_grid_blocked_symbols_match_frozen_registry_across_three_strategy_param_files() -> None:
    registry_symbols = _load_registry()["frozen_cells"]["grid_trading"]["symbols"]
    _assert_symbol_list_shape(registry_symbols)

    for kind in ("paper", "demo", "live"):
        path = ROOT / "settings" / f"strategy_params_{kind}.toml"
        data = _load_toml(path)
        actual = data["grid_trading"]["blocked_symbols"]
        assert actual == registry_symbols, (
            f"{path} grid_trading.blocked_symbols changed. "
            "P2-AUDIT-VERIFY-5 freezes this list; new cells require RFC + "
            "7d counterfactual + DSR/PBO evidence before config mutation."
        )


def test_ma_crossover_blocked_symbols_match_frozen_registry_across_risk_configs() -> None:
    registry_symbols = _load_registry()["frozen_cells"]["ma_crossover"]["symbols"]
    _assert_symbol_list_shape(registry_symbols)

    risk_dir = ROOT / "settings" / "risk_control_rules"
    for name in (
        "risk_config.toml",
        "risk_config_paper.toml",
        "risk_config_demo.toml",
        "risk_config_live.toml",
    ):
        path = risk_dir / name
        data = _load_toml(path)
        actual = data["per_strategy"]["ma_crossover"]["blocked_symbols"]
        assert actual == registry_symbols, (
            f"{path} per_strategy.ma_crossover.blocked_symbols changed. "
            "P2-AUDIT-VERIFY-5 freezes this list; new cells require RFC + "
            "7d counterfactual + DSR/PBO evidence before config mutation."
        )
