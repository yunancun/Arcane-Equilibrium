from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import demo_exchange_inventory_readonly as inv


def _args(tmp_path: Path, environment: str = "demo") -> argparse.Namespace:
    return argparse.Namespace(
        environment=environment,
        category="linear",
        settle_coin="USDT",
        max_pages=50,
        output_dir=tmp_path,
        json_output=tmp_path / "inventory.json",
        md_output=tmp_path / "inventory.md",
    )


def test_build_packet_rejects_non_demo_before_client(monkeypatch, tmp_path: Path):
    """The environment gate must fire before any client/credential use."""

    def _forbidden_client(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("BybitClient should not be constructed")

    monkeypatch.setattr(inv, "BybitClient", _forbidden_client)
    with pytest.raises(SystemExit, match="Refusing non-demo environment"):
        inv.build_packet(_args(tmp_path, environment="mainnet"))


def test_build_packet_rejects_non_demo_base_url(monkeypatch, tmp_path: Path):
    """A normalized/unexpected base URL drift must fail closed."""

    class FakeClient:
        def base_url(self) -> str:
            return "https://api.bybit.com"

        def close(self) -> None:
            return None

    monkeypatch.setattr(inv, "BybitClient", lambda environment: FakeClient())
    with pytest.raises(SystemExit, match="Refusing non-demo Bybit base URL"):
        inv.build_packet(_args(tmp_path))


def test_build_packet_success_uses_only_full_scan_get_helpers(monkeypatch, tmp_path: Path):
    """Successful inventory should call only the two read-only full-scan helpers."""
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeClient:
        def base_url(self) -> str:
            return inv.DEMO_BASE_URL

        def get_active_orders_full_scan(self, **kwargs):  # noqa: ANN003, ANN201
            calls.append(("orders", dict(kwargs)))
            return [{
                "symbol": "ARBUSDT",
                "side": "Buy",
                "orderType": "Limit",
                "orderStatus": "New",
                "price": "0.1",
                "qty": "10",
                "leavesQty": "10",
                "reduceOnly": False,
            }]

        def get_positions_full_scan(self, **kwargs):  # noqa: ANN003, ANN201
            calls.append(("positions", dict(kwargs)))
            return [{
                "symbol": "FILUSDT",
                "side": "Sell",
                "size": "2",
                "positionValue": "1.50",
                "unrealisedPnl": "-0.25",
            }]

        def close(self) -> None:
            calls.append(("close", {}))

    monkeypatch.setattr(inv, "BybitClient", lambda environment: FakeClient())
    packet = inv.build_packet(_args(tmp_path))
    assert [name for name, _ in calls] == ["orders", "positions", "close"]
    assert calls[0][1] == {
        "category": "linear",
        "settle_coin": "USDT",
        "open_only": 0,
        "limit": 50,
        "max_pages": 50,
    }
    assert calls[1][1] == {
        "category": "linear",
        "settle_coin": "USDT",
        "limit": 200,
        "max_pages": 50,
    }
    assert packet["boundary"]["private_get_only"] is True
    assert packet["boundary"]["cancel_or_modify_used"] is False
    assert packet["orders"]["summary"]["count"] == 1
    assert packet["positions"]["summary"]["nonzero_count"] == 1


def test_summarize_orders_conditional_count_ignores_unknown_zero_trigger():
    rows = [
        {
            "symbol": "ARBUSDT",
            "side": "Buy",
            "orderType": "Limit",
            "orderStatus": "New",
            "stopOrderType": "UNKNOWN",
            "triggerPrice": "0.00",
            "price": "0.1",
            "qty": "10",
            "leavesQty": "10",
        },
        {
            "symbol": "FILUSDT",
            "side": "Buy",
            "orderType": "Market",
            "orderStatus": "Untriggered",
            "stopOrderType": "UNKNOWN",
            "triggerPrice": "0.00",
            "price": "0",
            "qty": "1",
            "leavesQty": "1",
        },
        {
            "symbol": "ICPUSDT",
            "side": "Sell",
            "orderType": "Market",
            "orderStatus": "New",
            "stopOrderType": "Stop",
            "triggerPrice": "2.0",
            "price": "0",
            "qty": "1",
            "leavesQty": "1",
        },
    ]
    summary = inv.summarize_orders(rows)
    assert summary["conditional_count"] == 2


def test_main_bybit_error_returns_rc2_without_outputs(monkeypatch, tmp_path: Path, capsys):
    """Bybit failures must not write a success artifact."""
    json_path = tmp_path / "inventory.json"
    md_path = tmp_path / "inventory.md"

    def _raise_bybit_error(args):  # noqa: ANN001
        raise inv.BybitError("transport failed")

    monkeypatch.setattr(inv, "build_packet", _raise_bybit_error)
    rc = inv.main([
        "--json-output", str(json_path),
        "--md-output", str(md_path),
    ])
    captured = capsys.readouterr()
    assert rc == 2
    assert "Bybit inventory failed closed" in captured.err
    assert not json_path.exists()
    assert not md_path.exists()
