"""U6：只使用構造資料，驗收值來自 P4 增補的固定案例。"""

import ast
import socket
import sys
from pathlib import Path

import pytest

# 受控擷取移除 cwd 時仍以目前受審版本作絕對匯入。
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from program_code.research.r8_engine import series


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("離線測試禁止 socket 連線")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def test_g1_target_quantity_fill_and_fee():
    quantity = series.target_quantity("100000", "0.5", "99.50", "0.1")
    assert series.decimal_text(quantity) == "502.5"
    price, fee = series.fill_cost(quantity, "100", "10", "0.00055")
    assert series.decimal_text(price) == "100.1"
    assert series.decimal_text(fee) == "27.6651375"


def test_g2_closing_sell():
    price, fee = series.fill_cost("-502.5", "101", "10", "0.00055")
    assert series.decimal_text(price) == "100.899"
    assert series.decimal_text(fee) == "27.885961125"


@pytest.mark.parametrize(
    "before,after,price,rate,expected",
    [
        pytest.param("502.5", "0", "101", "0.0001", "-5.176755", id="G3"),
        pytest.param("-502.5", "-502.5", "101", "0.0001", "4.973745", id="G4"),
        pytest.param("0", "502.5", "101", "0.0001", "-5.176755", id="G5"),
        pytest.param("502.5", "0", "1", "0.02", "-10.251", id="G6-positive"),
        pytest.param("502.5", "0", "1", "-0.02", "0", id="G6-negative"),
    ],
)
def test_g3_g6_funding_uses_adverse_position(before, after, price, rate, expected):
    amount = series.funding_amount(before, after, price, rate, "0.02")
    assert series.decimal_text(amount) == expected


def test_g7_delisting_uses_adverse_extreme():
    price, fee = series.delisting_cost(
        "502.5", {"low": "0.95", "high": "1.02"},
        {"low": "0.97", "high": "1.04"}, "60", "0.00055",
    )
    assert series.decimal_text(price) == "0.9443"
    assert series.decimal_text(fee) == "0.2609809125"


def cost_parameters():
    return {
        "taker_fee_rate": "0.00055", "stress_fee_rate": "0.00075",
        "slippage_tiers_bps": [
            {"min_turnover": "100000000", "bps": "5"},
            {"min_turnover": "10000000", "bps": "10"},
            {"min_turnover": "1000000", "bps": "20"},
        ],
        "untradeable_below_turnover": "1000000",
        "order_cap_fraction": "0.01",
        "forced_reduce_penalty_bps": "60",
        "slippage_multiplier": "1", "funding_delta": "0.02",
        "funding_blank_min_rate": "0.0001", "liquidity_window_days": 12,
    }


def test_g8_reversal_keeps_reducing_leg_when_increase_is_voided():
    legs = series.order_segments(
        "100", "-50", "100", "0.1", "5", "500000", "10000000",
        True, cost_parameters(),
    )
    assert legs == [
        {"quantity": "-100", "slippage_bps": "60",
         "kind": "forced_reduce_penalty"},
        {"quantity": "-50", "reason": "untradeable"},
    ]


@pytest.mark.parametrize("value", [0.5, float("nan"), True, "NaN", "Infinity", "bad"])
def test_rejects_float_and_nonfinite_inputs(value):
    with pytest.raises(series.SeriesError):
        series.decimal_value(value)


def test_negative_target_rounds_toward_zero():
    assert series.decimal_text(
        series.target_quantity("100000", "-0.5", "99.50", "0.1")
    ) == "-502.5"


@pytest.mark.parametrize(
    "position,target,minimum,notional,daily,hourly,history,expected",
    [
        ("100", "99.95", "0.1", "0", "100000000", "10000000", True, "min_qty"),
        ("100", "99.9", "0.1", "11", "100000000", "10000000", True, "min_notional"),
        ("0", "100", "0.1", "0", "100000000", "999999", True, "order_cap"),
        ("0", "1", "0.1", "0", "100000000", "10000000", False, "insufficient_history"),
    ],
)
def test_void_reasons(position, target, minimum, notional, daily, hourly,
                      history, expected):
    legs = series.order_segments(
        position, target, "100", minimum, notional, daily, hourly,
        history, cost_parameters(),
    )
    assert len(legs) == 1
    assert legs[0]["reason"] == expected


def test_full_close_bypasses_minima_and_stresses_penalty():
    cost = {**cost_parameters(), "slippage_multiplier": "3"}
    assert series.order_segments(
        "0.05", "0", "100", "0.1", "100", "0", "0", False, cost,
    ) == [{"quantity": "-0.05", "slippage_bps": "180",
           "kind": "forced_reduce_penalty"}]


def test_estimated_funding_is_adverse_for_short():
    assert series.decimal_text(
        series.funding_amount("-100", "-50", "10", "0.0001", "0.02",
                              estimated=True)
    ) == "-0.102"


def test_short_delisting_uses_high_and_buy_slippage():
    price, fee = series.delisting_cost(
        "-100", {"low": "0.95", "high": "1.02"},
        {"low": "0.97", "high": "1.04"}, "60", "0.00055",
    )
    assert series.decimal_text(price) == "1.04624"
    assert series.decimal_text(fee) == "0.0575432"


def test_host_imports_are_standard_library_or_approved_packages():
    tree = ast.parse(Path(series.__file__).read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            modules.append(node.module)
    allowed = ("program_code.research.r8_engine", "program_code.research.r8_ledger")
    for module in modules:
        assert module.split(".")[0] in sys.stdlib_module_names or any(
            module == prefix or module.startswith(prefix + ".") for prefix in allowed
        )
        assert not (module.endswith(".rules") or module.endswith(".materialize"))
