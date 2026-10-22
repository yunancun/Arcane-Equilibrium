"""U5 離線驗收；預期值來自增補指令與獨立手算。"""
from decimal import Decimal
from pathlib import Path
import socket
import sys
import hashlib
import json
import subprocess
import ast

import pytest

# 受控驗證移除工作目錄時仍以受審倉庫載入。
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from program_code.research.r8_engine.lean_algo import rules
from program_code.research.r8_ledger.ledger import canonical


def assemble_cash_residuals(config, cash_steps, residuals, *, finish=None, exit_code=0):
    """以手寫 U5 事件測 assemble_run；現金與殘差均不由受測實作推算。"""
    from program_code.research.r8_engine import lean_runner as runner
    steps = [{"t": t, "cash": cash, "equity": "1000000000", "positions": {}}
             for t, cash in cash_steps]
    events = [{"section": "steps", "record": step} for step in steps]
    events += [{"section": "cash_residual", "record": row} for row in residuals]
    events.append({"section": "finished", "record": finish or {
        "status": "completed", "failure_reason": None, "failure_t": None}})
    return runner.assemble_run(config, {}, [], "0" * 64, 0, 10, exit_code, b"", events)


@pytest.mark.parametrize("cash,ulp", [
    pytest.param("99999.99", Decimal("1e-23"), id="e4"),
    pytest.param("100000", Decimal("1e-22"), id="e5"),
    pytest.param("0", Decimal("1e-28"), id="zero-cash"),
    pytest.param("0.00001", Decimal("1e-28"), id="ulp-floor"),
    pytest.param("-100000", Decimal("1e-22"), id="negative-cash"),
])
@pytest.mark.parametrize("multiple,status", [
    (0, "completed"), (100, "completed"), (101, "failed"),
    (-100, "completed"), (-101, "failed"),
])
def test_fix5_cash_residual_100_ulp_boundary(inputs, cash, ulp, multiple, status):
    # §16.2 手算：e=4 -> 10^(4-27)=1e-23，界限1e-21；
    # e=5（含負現金）-> 1e-22，界限1e-20；零現金及e=-5
    # 取下限1e-28，界限1e-26。101 ulp分別為1.01e-21/1.01e-20/1.01e-26。
    residual = format(Decimal(multiple) * ulp, "f")
    row = {"t": 1, "residual": residual}
    run = assemble_cash_residuals(inputs[2], [(1, cash)], [row])
    assert run["status"] == status
    assert run["failure_reason"] == ("lean_error" if status == "failed" else None)
    assert run["failure_t"] == (1 if status == "failed" else None)
    assert run["unexplained_cash_residual"] == {
        "per_step": [row] if multiple else [],
        "total": format((Decimal(multiple) * ulp).normalize(), "f") if multiple else "0"}


def test_fix5_cash_residual_uses_recorded_cash_before_magnitude_crossing(inputs):
    # 框架cash的e=4，100 ulp=1e-21；加1e-20後LEAN cash會跨1e5，
    # 但不得改用LEAN cash、equity或最後一步(e=5)的1e-20界限。
    cash = "99999.9999999999999999999999999"
    row = {"t": 1, "residual": format(Decimal("1e-20"), "f")}
    run = assemble_cash_residuals(inputs[2], [(1, cash), (2, "100000")], [row])
    assert (run["status"], run["failure_reason"], run["failure_t"]) == ("failed", "lean_error", 1)
    assert run["steps"][0]["cash"] == cash


@pytest.mark.parametrize("last_cash,residual,status", [
    ("100000", Decimal("1e-20"), "completed"),
    ("99999.99", Decimal("1.01e-21"), "failed"),
    ("0", Decimal("1e-26"), "completed"),
])
def test_fix5_cash_residual_at_end_uses_last_chronological_step(inputs, last_cash, residual, status):
    # 最後一步e=5界限1e-20、e=4界限1e-21、零現金界限1e-26。
    # 結束事件t=3沒有同時刻step；傳入steps逆序，必須取時間上最後的t=2。
    row = {"t": 3, "residual": format(residual, "f")}
    run = assemble_cash_residuals(inputs[2], [(2, last_cash), (1, "0.1")], [row])
    assert run["status"] == status
    assert run["failure_t"] == (3 if status == "failed" else None)
    assert run["unexplained_cash_residual"] == {"per_step": [row], "total": row["residual"]}


def test_fix5_cash_residual_failure_t_skips_representation_errors(inputs):
    # t=1/2/3: e=4界限1e-21；t=4: e=5界限1e-20，1.01e-20才失敗。
    rows = [{"t": t, "residual": format(Decimal(value), "f")}
            for t, value in [(1, "1e-21"), (2, "-1e-21"), (3, "1e-23"),
                             (4, "1.01e-20"), (5, "2e-20")]]
    run = assemble_cash_residuals(inputs[2], [
        (1, "99999"), (2, "99999"), (3, "99999"), (4, "100000"), (5, "100000")], rows)
    assert (run["status"], run["failure_reason"], run["failure_t"]) == ("failed", "lean_error", 4)
    assert run["unexplained_cash_residual"]["per_step"] == rows
    assert Decimal(run["unexplained_cash_residual"]["total"]) == Decimal("3.011e-20")


def test_fix5_cash_residual_total_is_not_a_failure_threshold(inputs):
    # e=4每筆界限1e-21；逐筆加總4e-21不作判定，t=3結束重複記錄仍保留。
    rows = [{"t": t, "residual": format(Decimal("1e-21"), "f")} for t in (1, 2, 3, 3)]
    run = assemble_cash_residuals(inputs[2], [(t, "99999") for t in (1, 2, 3)], rows)
    assert (run["status"], run["failure_reason"], run["failure_t"]) == ("completed", None, None)
    assert run["unexplained_cash_residual"] == {
        "per_step": rows, "total": format(Decimal("4e-21"), "f")}


def test_fix5_cash_residual_cancellation_does_not_hide_failure(inputs):
    # e=4界限1e-21；兩筆±101 ulp相消為0仍應在t=1失敗。
    rows = [{"t": 1, "residual": format(Decimal("1.01e-21"), "f")},
            {"t": 2, "residual": format(Decimal("-1.01e-21"), "f")}]
    run = assemble_cash_residuals(inputs[2], [(1, "99999"), (2, "99999")], rows)
    assert (run["status"], run["failure_t"]) == ("failed", 1)
    assert run["unexplained_cash_residual"] == {"per_step": rows, "total": "0"}


@pytest.mark.parametrize("finish,exit_code,reason", [
    ({"status": "failed", "failure_reason": "algorithm_exception", "failure_t": 2},
     0, "algorithm_exception"),
    ({"status": "completed", "failure_reason": None, "failure_t": None}, 1, "lean_error"),
])
def test_fix5_cash_residual_within_tolerance_keeps_container_failure(inputs, finish, exit_code, reason):
    # e=4界限1e-21；100 ulp不可把容器的失敗改為completed。
    row = {"t": 1, "residual": format(Decimal("1e-21"), "f")}
    run = assemble_cash_residuals(inputs[2], [(1, "99999")], [row], finish=finish, exit_code=exit_code)
    assert run["status"] == "failed"
    assert run["failure_reason"] == reason
    assert run["failure_t"] == finish["failure_t"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("測試禁止網路")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def test_g1_open_quantity_price_fee():
    quantity = rules.target_quantity("0.5", "100000", "99.50", "0.1")
    assert rules.number(quantity) == "502.5"
    price = rules.fill_price("100", quantity, "10")
    assert rules.number(price) == "100.1"
    assert rules.number(rules.fee(quantity, price, "0.00055")) == "27.6651375"


def test_g2_close_price_fee():
    price = rules.fill_price("101", "-502.5", "10")
    assert rules.number(price) == "100.899"
    assert rules.number(rules.fee("-502.5", price, "0.00055")) == "27.885961125"


@pytest.mark.parametrize("before,after,price,rate,expected", [
    ("502.5", "0", "101", "0.0001", "-5.176755"),
    ("-502.5", "-502.5", "101", "0.0001", "4.973745"),
    ("0", "502.5", "101", "0.0001", "-5.176755"),
    ("502.5", "0", "1", "0.02", "-10.251"),
    ("502.5", "0", "1", "-0.02", "0"),
], ids=["G3", "G4", "G5", "G6-positive", "G6-negative"])
def test_g3_g6_funding(before, after, price, rate, expected):
    assert rules.number(rules.funding_amount(before, after, price, rate, "0.02")) == expected


def test_g7_delisting():
    price = rules.delisting_price("502.5", {"low": "0.95", "high": "1.05"},
                                 {"low": "0.97", "high": "1.03"}, "60", "1")
    assert rules.number(price) == "0.9443"
    assert rules.number(rules.fee("502.5", price, "0.00055")) == "0.2609809125"


@pytest.fixture
def cost():
    return {
        "taker_fee_rate": "0.00055", "stress_fee_rate": "0.00075",
        "slippage_tiers_bps": [
            {"min_turnover": "100000000", "bps": "5"},
            {"min_turnover": "10000000", "bps": "10"},
            {"min_turnover": "1000000", "bps": "20"}],
        "untradeable_below_turnover": "1000000", "order_cap_fraction": "0.01",
        "forced_reduce_penalty_bps": "60", "slippage_multiplier": "1",
        "funding_delta": "0.02", "funding_blank_min_rate": "0.0001",
        "liquidity_window_days": 12,
    }


def test_g8_reversal_keeps_reduction(cost):
    segments = rules.order_segments("100", "-50", "1", "1", "1", "0",
                                    "untradeable", "20", "100000000", cost)
    assert [(s["quantity"], s["reason"]) for s in segments] == [
        ("-100", None), ("-50", "untradeable")]
    assert segments[0]["kind"] == "forced_reduce_penalty"
    assert rules.effective_target("100", segments) == Decimal("0")


HOUR = 3600000
DAY = 24 * HOUR


def test_next_open_gap_day_decision_and_exposure():
    assert rules.next_open(5 * HOUR, 4 * HOUR, 5 * HOUR) is None
    assert rules.next_open(5 * HOUR, 7 * HOUR, 8 * HOUR) == 7 * HOUR
    assert rules.decision_due("day", DAY)
    assert not rules.decision_due("day", DAY + HOUR)
    assert rules.exposure({"X": "2", "Y": "-1"}, {"X": "100", "Y": "100"}, "1000", "1") == Decimal("0.3")
    with pytest.raises(ValueError, match="gross_exposure_cap"):
        rules.exposure({"X": "11"}, {"X": "100"}, "1000", "1")


@pytest.mark.parametrize("turnover,bps,reason", [
    ("100000000", "5", None), ("10000000", "10", None),
    ("1000000", "20", None), ("999999", "20", "untradeable")])
def test_liquidity_tiers(cost, turnover, bps, reason):
    rows = [{"t": i * DAY, "known_at": (i + 1) * DAY, "value": turnover} for i in range(12)]
    assert rules.liquidity(12 * DAY, 0, rows, cost) == (reason, Decimal(bps))
    assert rules.liquidity(11 * DAY, 0, rows, cost)[0] == "insufficient_history"
    assert rules.liquidity(12 * DAY, 0, rows[:5], cost)[0] == "untradeable"


@pytest.mark.parametrize("current,target,min_qty,min_notional,hour,reason", [
    ("0", "0.1", "1", "0", "100000", "min_qty"),
    ("0", "1", "1", "101", "100000", "min_notional"),
    ("0", "2", "1", "0", "1000", "order_cap"),
    ("2", "1.9", "1", "0", "100000", "min_qty"),
    ("0.1", "0", "1", "1000", "0", None)])
def test_minima_cap_flatten_exception(cost, current, target, min_qty, min_notional, hour, reason):
    s = rules.order_segments(current, target, "100", "0.1", min_qty, min_notional,
                             None, "5", hour, cost)[0]
    assert s["reason"] == reason


def test_penalty_and_endpoint_liquidation(cost):
    cost["slippage_multiplier"] = "3"
    s = rules.order_segments("1", "0", "100", "0.1", "1", "0",
                            "insufficient_history", "20", "0", cost)[0]
    assert s["slippage_bps"] == "180"
    assert rules.number(rules.score_end_price("1", "100", cost)) == "98.2"
    assert rules.number(rules.delisting_price("-1", {"high": "101", "low": "90"},
                                           {"high": "103", "low": "91"}, "60", "2")) == "104.236"


def test_funding_gap_short_positions_edges_and_delivery():
    rows = [{"t": t * HOUR, "rate": rate} for t, rate in [
        (8, "0.0002"), (16, "-0.0003"), (32, "0.0001"), (40, "0.0001")]]
    schedule = rules.funding_schedule(rows, 3 * HOUR, 48 * HOUR, 8 * HOUR, "0.0001")
    assert [(r["t"] // HOUR, r["rate"]) for r in schedule if r["estimated"]] == [
        (24, "0.0003"), (48, "0.0001")]
    assert rules.number(rules.funding_amount("-2", "-3", "100", "0.0003", "0.02", True)) == "-0.0918"
    cut = rules.funding_schedule(rows, 3 * HOUR, 48 * HOUR, 8 * HOUR, "0.0001", delivery=32 * HOUR)
    assert max(r["t"] for r in cut) == 32 * HOUR
    assert [r["t"] // HOUR for r in rules.funding_schedule([], 3 * HOUR, 24 * HOUR, 8 * HOUR, "0.0001")] == [8, 16, 24]
    assert [r["t"] // HOUR for r in rules.funding_schedule(rows[:1], 0, 16 * HOUR, 8 * HOUR, "0.0001") if r["estimated"]] == [0, 16]


def test_funding_interval_change_and_half_up():
    schedule = rules.funding_schedule(
        [{"t": h * HOUR, "rate": "0.001"} for h in (0, 8, 16, 20)], 0, 20 * HOUR, 8 * HOUR, "0.0001")
    assert [r["t"] // HOUR for r in schedule if r["estimated"]] == [12]
    half = rules.funding_schedule(
        [{"t": h * HOUR, "rate": "0.001"} for h in (0, 2, 7, 9)], 0, 9 * HOUR, 2 * HOUR, "0.0001")
    assert [r["t"] // HOUR for r in half if r["estimated"]] == [4, 6]


def test_positions_funding_price_and_contiguous_windows():
    fills = [{"symbol": "X", "change_t": 5, "quantity": "3"},
             {"symbol": "X", "change_t": 8, "quantity": "-3"}]
    assert rules.positions_at(fills, "X", 8) == (Decimal("3"), Decimal("0"))
    assert rules.funding_price([{"end": 4, "close": "9"}, {"end": 10, "close": "12"}], 8) == (Decimal("9"), True)
    assert rules.merge_windows([{"start": 1, "end": 3}, {"start": 3, "end": 5}, {"start": 7, "end": 9}]) == [
        {"start": 1, "end": 5}, {"start": 7, "end": 9}]


def strategy(scores):
    return {"grid": [{"n": i, "score": s} for i, s in enumerate(scores)],
            "neighborhood": {"numeric": {}, "categorical": ["n", "score"]},
            "internal_validation_days": 182, "internal_gap_days": 8}


@pytest.mark.parametrize("scores,selected", [
    (["-1", "100", "-1", "-1"], None), (["100", "-1", "-1"], None),
    (["-1", "-2"], None), (["1", "1", "1"], 0), (["1", "2", "3"], 2)])
def test_grid_qualification_plateau_and_tie(scores, selected):
    s = {"grid": [{"n": i} for i in range(len(scores))],
         "neighborhood": {"numeric": {"n": list(range(len(scores)))}, "categorical": []}}
    result = rules.select_grid_point(scores, s["grid"], s["neighborhood"])
    assert result["selected"] == selected
    assert result["no_trade"] == (selected is None)
    assert set(result) == {"grid_scores", "neighborhood_means", "qualified",
                           "selected", "selected_minus_neighborhood", "no_trade"}


def test_readonly_view_fit_isolation_selection_and_model_roundtrip(cost):
    from program_code.research.r8_engine import lean_runner as runner
    calls = []

    class Fake(rules.R8Hypothesis):
        def score(self, params, train_window, validation_window, data, cost):
            calls.append(("score", self, params, train_window, validation_window, data, cost))
            self.changed = True
            return params["score"]

        def fit(self, fit_window, data, params):
            calls.append(("fit", self, params))
            return {"fit_end": fit_window["end"]}

        def on_decision(self, time, data, model, params):
            return {"X": {"weight": str(params["n"])}}

    original = Fake(123)
    fit_window = {"start": 0, "end": 400 * DAY}
    data = {"X": {"kline_day": [
        {"known_at": 200 * DAY, "close": "1"},
        {"known_at": 400 * DAY, "close": "999"}]}}
    result = rules.fit_fold(Fake, 123, fit_window, data, strategy(["1", "2", "3"]), cost)
    assert [c[2]["n"] for c in calls if c[0] == "score"] == [0, 1, 2]
    assert calls[0][3] == {"start": 0, "end": 210 * DAY}
    assert calls[0][4] == {"start": 218 * DAY, "end": 400 * DAY}
    assert len(calls[0][5]["X"]["kline_day"]) == 1
    assert calls[0][6]["taker_fee_rate"] == "0.00055"
    assert list(calls[0][6]["slippage_tiers_bps"]) == cost["slippage_tiers_bps"]
    assert not hasattr(original, "changed")
    assert all(c[1] is not original for c in calls)
    with pytest.raises(TypeError):
        calls[0][5]["X"]["kline_day"][0]["close"] = "3"
    model, sha = runner.serialize_model(result["artifact"])
    assert runner.deserialize_model(model, sha) == result["artifact"]
    with pytest.raises(ValueError, match="模型"):
        runner.deserialize_model(model + b" ", sha)
    assert rules.decide(original, 400 * DAY, data, result["artifact"]) == {"X": {"weight": "2"}}
    data["X"]["kline_day"][1]["close"] = "12345"
    assert rules.fit_fold(Fake, 123, fit_window, data, strategy(["1", "2", "3"]), cost) == result
    calls.clear()
    no_trade = rules.fit_fold(Fake, 123, fit_window, data, strategy(["-1"]), cost)
    assert no_trade["artifact"] is None
    assert not [c for c in calls if c[0] == "fit"]
    with pytest.raises(AttributeError):
        original.random_seed = 12


@pytest.mark.parametrize("value", [None, 1.2, "NaN", "Infinity", "not-a-number"])
def test_grid_score_rejects_invalid(value):
    with pytest.raises(ValueError):
        rules.select_grid_point([value], [{"n": 1}], {"numeric": {}, "categorical": ["n"]})


@pytest.mark.parametrize("body", [
    "open('x')", "data._secret", "self.market_order('X', 1)",
    "global shared\n        shared = 1", "nonlocal shared",
    "Strategy.shared = 1", "random.random()", "random.Random()",
    "getattr(data, 'secret')", "__import__('os')",
])
def test_static_check_rejects_unsafe_hypothesis(body):
    from program_code.research.r8_engine import lean_runner
    source = ("from program_code.research.r8_engine.lean_algo.framework import R8Hypothesis\n"
              "import random\nclass Strategy(R8Hypothesis):\n"
              "    def on_decision(self, time, data, model, params):\n        " + body + "\n")
    with pytest.raises(ValueError):
        lean_runner.check_algorithm(source)


def test_static_check_module_class_state_and_safe_seed():
    from program_code.research.r8_engine import lean_runner
    for source in ("shared = []", "class Strategy:\n    shared = []", "import os"):
        with pytest.raises(ValueError):
            lean_runner.check_algorithm(source)
    lean_runner.check_algorithm(
        "from program_code.research.r8_engine.lean_algo.framework import R8Hypothesis\n"
        "import random\nclass Strategy(R8Hypothesis):\n"
        "    def on_decision(self, time, data, model, params):\n"
        "        rng = random.Random(self.random_seed)\n"
        "        self.last = rng.random()\n"
        "        return None\n")


def test_symbol_properties_replaces_same_key():
    from program_code.research.r8_engine import lean_runner
    base = b"# header\nbybit,X,cryptofuture,old,USDT,1,0.1,1,X,1,\nbybit,X,crypto,spot,USDT,1,0.1,1,X,1,\n"
    overlay = b"bybit,X,cryptofuture,new,USDT,1,0.01,0.1,X,0.1,\nbybit,Y,cryptofuture,Y,USDT,1,0.01,1,Y,1,\n"
    merged = lean_runner.merge_properties(base, overlay)
    assert b"old" not in merged
    assert merged.count(b"bybit,X,cryptofuture,") == 1
    assert b",crypto,spot," in merged and b"bybit,Y,cryptofuture," in merged


@pytest.fixture
def inputs(tmp_path, cost):
    from program_code.research.r8_engine import lean_runner as runner
    materialization = tmp_path / "materialization"
    materialization.mkdir()
    files = {}
    for name, raw in {
        "lean/cryptofuture/bybit/hour/x_trade.zip": b"constructed-zip",
        "custom/funding/x.csv": b"0,0,0.0001\n",
        "source/x.csv": b"timestamp,value\n0,1\n",
    }.items():
        path = materialization / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        files[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "rows": 1, "first": 0,
                       "last": 0, "source_file": "x.csv.gz", "source_sha256": "1" * 64}
    overlay = b"bybit,X,cryptofuture,X,USDT,1,0.01,0.1,X,0.1,\n"
    (materialization / "symbol_properties_overlay.csv").write_bytes(overlay)
    manifest = {
        "schema_version": "r8_materialization_v1", "u1_manifest_sha256": "1" * 64,
        "u1_tool_version": "r8-public-data-2", "ledger_id": "test-ledger",
        "hypothesis_id": "test-hypothesis", "generation": 1, "purpose": "research",
        "window": {"start": 0, "end": 500 * DAY}, "warmup": {"start": -13 * DAY, "end": 0},
        "readable": {}, "symbols": ["X"], "strategy_symbols": ["X"], "files": files,
        "gaps": {}, "first_bar": {"X": 0}, "min_notional": {"X": "0"},
        "funding_interval_ms": {"X": 8 * HOUR}, "delistings": {},
        "symbol_properties_overlay_sha256": hashlib.sha256(overlay).hexdigest(), "limitations": [],
    }
    raw = canonical(manifest)
    (materialization / "materialization.json").write_bytes(raw)
    config = {
        "trial_id": "trial-1", "materialization_sha256": hashlib.sha256(raw).hexdigest(),
        "code_commit": "a" * 40, "engine_commit": "a" * 40, "symbols": ["X"],
        "initial_cash": "100000", "leverage": "10", "gross_exposure_cap": "1",
        "decision_resolution": "hour", "sharpe_frequency_seconds": 604800,
        "warmup": manifest["warmup"],
        "score_windows": [{"start": 400 * DAY, "end": 500 * DAY}],
        "folds": [{"fit_window": {"start": 0, "end": 392 * DAY},
                   "score_window": {"start": 400 * DAY, "end": 500 * DAY}}],
        "model_artifact": None, "random_seed": 5, "strategy": strategy(["1"]),
        "algorithm": {"path": "hypotheses/example.py", "class": "Strategy"}, "mode": "trial",
        "cost": cost,
    }
    identity = {
        "trial_id": "trial-1", "hypothesis_id": "test-hypothesis", "generation": 1,
        "manifest_sha256": config["materialization_sha256"],
        "data_files": {k: v["sha256"] for k, v in files.items()},
        "code_commit": config["code_commit"], "random_seed": 5,
        "data_window": manifest["window"], "fit_window": {"start": 0, "end": 392 * DAY},
        "score_window": config["score_windows"][0], "folds": config["folds"],
        "evaluation_kind": "out_of_sample", "variant_parameters": config["strategy"],
        "sharpe_frequency": {"unit": "week", "seconds": 604800, "annualized": False},
        "configuration": {
            "strategy_parameters": {"run": {k: config[k] for k in (
                "initial_cash", "leverage", "gross_exposure_cap", "decision_resolution",
                "sharpe_frequency_seconds", "algorithm", "engine_commit")},
                "strategy": config["strategy"]}, "cost_model_parameters": cost},
        **rules.RUNTIME_METADATA,
    }
    identity["configuration_sha256"] = hashlib.sha256(canonical(identity["configuration"])).hexdigest()
    return materialization, manifest, config, {"record": identity, "finished": False, "status": "started"}


def test_injected_trial_identity_and_modes(inputs):
    from program_code.research.r8_engine import lean_runner as runner
    path, manifest, config, query = inputs
    calls = []
    def lookup(trial):
        calls.append(trial)
        return query
    runner.validate_config(config, manifest, lookup)
    assert calls == ["trial-1"]
    trial_bytes = runner.algorithm_config(config)
    config["mode"] = "verification"
    with pytest.raises(ValueError, match="結束"):
        runner.validate_config(config, manifest, lookup)
    query["finished"] = True
    query["status"] = "completed"
    runner.validate_config(config, manifest, lookup)
    assert runner.algorithm_config(config) == trial_bytes
    assert "mode" not in json.loads(trial_bytes)
    config["mode"] = "trial"
    with pytest.raises(ValueError, match="結束"):
        runner.validate_config(config, manifest, lookup)


@pytest.mark.parametrize("key,value", [
    ("random_seed", None), ("random_seed", True), ("random_seed", 1.2),
    ("symbols", ["Y"]), ("warmup", {"start": -1, "end": 0}),
    ("score_windows", []), ("code_commit", "short"), ("gross_exposure_cap", "1.01"),
    ("algorithm", {"path": "hypotheses/other.py", "class": "Other"}),
    ("initial_cash", "999"), ("random_seed", 6),
])
def test_runner_rejects_identity_drift(inputs, key, value):
    from program_code.research.r8_engine import lean_runner as runner
    _, manifest, config, query = inputs
    config[key] = value
    with pytest.raises(ValueError):
        runner.validate_config(config, manifest, lambda t: query)


def test_runner_missing_trial_and_metadata(inputs):
    from program_code.research.r8_engine import lean_runner as runner
    _, manifest, config, query = inputs
    for lookup in (lambda t: None, lambda t: {}):
        with pytest.raises(ValueError):
            runner.validate_config(config, manifest, lookup)
    query["record"]["engine"] = {"id": "lean", "version": "wrong"}
    with pytest.raises(ValueError):
        runner.validate_config(config, manifest, lambda t: query)


def test_validation_mode_and_materialization_purpose(inputs):
    from program_code.research.r8_engine import lean_runner as runner
    _, manifest, config, query = inputs
    manifest["purpose"] = "validation"
    for mode in ("trial", "verification"):
        config["mode"] = mode
        with pytest.raises(ValueError, match="purpose"):
            runner.validate_config(config, manifest, lambda t: query)
    config.update(mode="validation", trial_id=None)
    with pytest.raises(ValueError, match="範例"):
        runner.validate_config(config, manifest, lambda t: query)
    config["algorithm"] = {"path": runner.EXAMPLE, "class": "FixedSchedule"}
    runner.validate_config(config, manifest, lambda t: pytest.fail("驗證不查研究帳"))
    config["trial_id"] = "trial-1"
    with pytest.raises(ValueError):
        runner.validate_config(config, manifest, lambda t: query)


def test_materialization_hash_inventory_and_paths(inputs):
    from program_code.research.r8_engine import lean_runner as runner
    path, manifest, config, _ = inputs
    assert runner.read_materialization(path, config["materialization_sha256"]) == manifest
    with pytest.raises(ValueError, match="雜湊"):
        runner.read_materialization(path, "0" * 64)
    extra = path / "custom" / "extra.csv"
    extra.write_text("extra")
    with pytest.raises(ValueError, match="清單"):
        runner.read_materialization(path, config["materialization_sha256"])
    extra.unlink()
    target = path / "custom/funding/x.csv"
    target.write_text("tampered")
    with pytest.raises(ValueError, match="雜湊"):
        runner.read_materialization(path, config["materialization_sha256"])
    target.unlink()
    with pytest.raises(ValueError, match="清單"):
        runner.read_materialization(path, config["materialization_sha256"])


@pytest.fixture
def git_fixture(tmp_path):
    from program_code.research.r8_engine import lean_runner as runner
    repo = tmp_path / "repo"
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.STDOUT).decode().strip()
    git("init", "-q")
    git("config", "user.name", "Offline Test")
    git("config", "user.email", "test@example.invalid")
    for path in (runner.FRAMEWORK, runner.ENGINE_ROOT + "/lean_algo/rules.py",
                 runner.ENGINE_ROOT + "/lean_runner.py", runner.LEDGER_ROOT + "/ledger.py",
                 runner.EXAMPLE, "hypotheses/example.py"):
        f = repo / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('"""構造的受審來源。"""\n')
    git("add", ".")
    git("commit", "-qm", "test baseline")
    head = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/main", head)
    return repo, git, head


def test_source_commit_and_engine_ancestor(inputs, git_fixture):
    from program_code.research.r8_engine import lean_runner as runner
    _, _, config, _ = inputs
    repo, git, head = git_fixture
    config.update(code_commit=head, engine_commit=head)
    hashes = runner.verify_source(repo, config)
    assert runner.FRAMEWORK in hashes and runner.LEDGER_ROOT + "/ledger.py" in hashes
    f = repo / "hypotheses/example.py"
    f.write_text("changed = True\n")
    with pytest.raises(ValueError, match="來源"):
        runner.verify_source(repo, config)
    git("add", ".")
    git("commit", "-qm", "algorithm only")
    config["code_commit"] = git("rev-parse", "HEAD")
    runner.verify_source(repo, config)
    (repo / (runner.ENGINE_ROOT + "/lean_runner.py")).write_text("changed = True\n")
    git("add", ".")
    git("commit", "-qm", "unreviewed engine")
    config["code_commit"] = git("rev-parse", "HEAD")
    with pytest.raises(ValueError, match="引擎"):
        runner.verify_source(repo, config)
    config["engine_commit"] = config["code_commit"]
    with pytest.raises(ValueError, match="祖先"):
        runner.verify_source(repo, config)
    config["mode"] = "validation"
    runner.verify_source(repo, config)


def test_untracked_engine_and_output_in_repo(inputs, git_fixture):
    from program_code.research.r8_engine import lean_runner as runner
    path, _, config, _ = inputs
    repo, _, head = git_fixture
    config.update(code_commit=head, engine_commit=head, mode="validation", trial_id=None,
                  algorithm={"path": runner.EXAMPLE, "class": "FixedSchedule"})
    extra = repo / (runner.ENGINE_ROOT + "/untracked.py")
    extra.write_text("changed = True")
    with pytest.raises(ValueError, match="來源"):
        runner.verify_source(repo, config)
    extra.unlink()
    with pytest.raises(ValueError, match="倉庫"):
        runner.execute(config, path, repo / "output", repo=repo,
                       process=lambda *a, **k: pytest.fail("不可呼叫 docker"))


def test_mock_process_docker_and_run_json(inputs, git_fixture, tmp_path):
    from program_code.research.r8_engine import lean_runner as runner
    path, _, config, _ = inputs
    repo, _, head = git_fixture
    config.update(code_commit=head, engine_commit=head, mode="validation", trial_id=None,
                  algorithm={"path": runner.EXAMPLE, "class": "FixedSchedule"})
    calls = []
    out = tmp_path / "run"
    def process(argv, **kwargs):
        calls.append(argv)
        if argv[-1] == "/Lean/Data/symbol-properties/symbol-properties-database.csv":
            return subprocess.CompletedProcess(argv, 0, b"# header\n", b"")
        (out / "events.jsonl").write_bytes(
            canonical({"section": "steps", "record": {"t": DAY, "equity": "100000", "cash": "100000", "positions": {}}}) + b"\n"
            + canonical({"section": "finished", "record": {"status": "completed", "failure_reason": None, "failure_t": None}}) + b"\n")
        return subprocess.CompletedProcess(argv, 0, b"synthetic LEAN log", b"")
    result = runner.execute(config, path, out, repo=repo, process=process)
    assert result["status"] == "completed" and result["schema_version"] == "r8_lean_run_v1"
    assert result["steps"][0]["equity"] == "100000"
    assert result["unexplained_cash_residual"] == {"per_step": [], "total": "0"}
    assert (out / "run.json").read_bytes() == canonical(result)
    assert result["algorithm_config_sha256"] == hashlib.sha256(runner.algorithm_config(config)).hexdigest()
    assert result["lean_log_sha256"] == hashlib.sha256(b"synthetic LEAN log").hexdigest()
    for argv in calls:
        assert argv[:5] == ["docker", "run", "--rm", "--network", "none"]
        assert runner.IMAGE in argv
    mounts = [calls[-1][i + 1] for i, a in enumerate(calls[-1][:-1]) if a == "--mount"]
    assert all("readonly" in m for m in mounts if "dst=/r8/output" not in m)
    assert not any("dst=/Lean/Data," in m for m in mounts)
    assert any("dst=/Lean/Data/cryptofuture/bybit/hour," in m for m in mounts)


def test_host_imports_only_stdlib_and_approved_packages():
    files = ["program_code/research/r8_engine/lean_algo/__init__.py",
             "program_code/research/r8_engine/lean_algo/rules.py",
             "program_code/research/r8_engine/lean_runner.py"]
    for name in files:
        tree = ast.parse((ROOT / name).read_text())
        for n in ast.walk(tree):
            modules = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module] if isinstance(n, ast.ImportFrom) else []
            for module in modules:
                assert module.split(".")[0] in sys.stdlib_module_names or module.startswith((
                    "program_code.research.r8_engine", "program_code.research.r8_ledger"))


def test_runtime_metadata_exact():
    assert rules.RUNTIME_METADATA == {
        "cost_model": {"id": "r8_cost_rules", "version": "r8-p4-v1"},
        "fill_model": {"id": "r8_next_open_fill", "version": "r8-p4-v1"},
        "engine": {"id": "lean", "version": "sha256:2657ed3355efb78d78bd0a5d4f126b01367a635e01bccd220b654d7742d182b6"},
        "dependencies": {"lean_image_digest": "sha256:2657ed3355efb78d78bd0a5d4f126b01367a635e01bccd220b654d7742d182b6"},
        "time_semantics": {"known_at": "bar_end", "fill_at": "next_bar_open", "simulated_latency_ms": 0},
    }


def test_future_accounting_reduction_reversal_and_addition():
    assert rules.apply_fill("2", "100", "1", "130") == (
        Decimal("3"), Decimal("110"), Decimal("0"))
    assert rules.apply_fill("3", "110", "-1", "120") == (
        Decimal("2"), Decimal("110"), Decimal("10"))
    assert rules.apply_fill("2", "110", "-3", "100") == (
        Decimal("-1"), Decimal("100"), Decimal("-20"))
    assert rules.apply_fill("-1", "100", "1", "90") == (
        Decimal("0"), Decimal("0"), Decimal("10"))


def test_record_assembly_fails_closed_on_missing_end_error_or_fill_forward(inputs):
    from program_code.research.r8_engine import lean_runner as runner
    _, _, config, _ = inputs
    for events, code, reason in [
        ([], 0, "lean_error"),
        ([{"section": "finished", "record": {"status": "completed", "failure_reason": None, "failure_t": None}}], 1, "lean_error"),
        ([{"section": "fill_forward_bars", "record": {"t": 1, "symbol": "X"}}], 0, "fill_forward_bar"),
        ([{"section": "cash_residual", "record": {"t": 2, "residual": "1"}},
          {"section": "finished", "record": {"status": "completed", "failure_reason": None, "failure_t": None}}], 0, "lean_error"),
    ]:
        result = runner.assemble_run(config, {}, [], "a" * 64, 0, 1, code, b"", events)
        assert result["status"] == "failed" and result["failure_reason"] == reason


def test_default_query_does_not_create_ledger(tmp_path):
    from program_code.research.r8_engine import lean_runner as runner
    with pytest.raises(ValueError, match="已存在"):
        runner.trial_lookup(tmp_path / "missing")
    assert not (tmp_path / "missing").exists()


def test_trial_verification_container_inputs_and_arguments_identical(inputs, git_fixture, tmp_path):
    from program_code.research.r8_engine import lean_runner as runner
    path, manifest, config, query = inputs
    config['materialization_sha256'], _ = dv5_materialization(path, manifest)
    query['record'].update(manifest_sha256=config['materialization_sha256'],
        data_files={k:v['sha256'] for k,v in manifest['files'].items()}, preregistration_sha256='c'*64)
    repo, _, head = git_fixture
    config.update(code_commit=head, engine_commit=head)
    query["record"]["code_commit"] = head
    query["record"]["configuration"]["strategy_parameters"]["run"]["engine_commit"] = head
    query["record"]["configuration_sha256"] = hashlib.sha256(canonical(query["record"]["configuration"])).hexdigest()
    seen = []
    def process(argv, **kwargs):
        if argv[-1] == "/Lean/Data/symbol-properties/symbol-properties-database.csv":
            return subprocess.CompletedProcess(argv, 0, b"# base\n", b"")
        mounts = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--mount"]
        output = next(m for m in mounts if "dst=/r8/output" in m).split("src=", 1)[1].split(",dst=", 1)[0]
        config_file = next(m for m in mounts if "dst=/r8/algorithm_config.json" in m).split("src=", 1)[1].split(",dst=", 1)[0]
        seen.append((list(argv), Path(config_file).read_bytes()))
        (Path(output) / "events.jsonl").write_bytes(canonical({
            "section": "finished", "record": {"status": "completed", "failure_reason": None, "failure_t": None}}) + b"\n")
        return subprocess.CompletedProcess(argv, 0, b"test", b"")
    trial = runner.execute(config, path, tmp_path / "trial", repo=repo, query=lambda t: query, process=process)
    config["mode"], query["finished"], query["status"] = "verification", True, "completed"
    verification = runner.execute(config, path, tmp_path / "verification", repo=repo, query=lambda t: query, process=process)
    assert seen[0][1] == seen[1][1]
    assert b'turnover_decisions' not in seen[0][1] and b'family' not in seen[0][1]
    mounts = [seen[0][0][i+1] for i, arg in enumerate(seen[0][0][:-1]) if arg=='--mount']
    assert any('dst=/r8/framework-inputs,readonly' in m for m in mounts)
    assert not any('dst=/r8/verification' in m or 'dst=/r8/source' in m for m in mounts)
    def without_output(argv):
        return [arg if "dst=/r8/output" not in arg else "output-mount" for arg in argv]
    assert without_output(seen[0][0]) == without_output(seen[1][0])
    assert trial["algorithm_config_sha256"] == verification["algorithm_config_sha256"]
    assert set(trial) == {
        "schema_version", "materialization_sha256", "run_config_sha256", "run_config", "image_digest",
        "docker_argv", "algorithm_config_sha256", "algorithm_files", "base_symbol_properties_sha256",
        "started_at", "ended_at", "exit_code", "lean_log_sha256", "mode", "status", "failure_reason",
        "failure_t", "steps", "decisions", "orders", "fills", "voided", "funding", "endpoint_funding",
        "unexplained_cash_residual", "fits", "fill_forward_bars",
    }


def test_negative_funding_and_positive_short_estimates():
    assert rules.number(rules.funding_amount("2", "2", "100", "-0.01", "0.02")) == "1.96"
    assert rules.number(rules.funding_amount("-2", "-2", "100", "-0.01", "0.02")) == "-2.04"
    assert rules.number(rules.funding_amount("2", "0", "100", "0", "0.02")) == "0"


def test_future_and_unlisted_symbols_absent_from_view():
    data = {"X": {"funding": [{"known_at": 1, "value": "0.1"}, {"known_at": 3, "value": "0.2"}]},
            "FUTURE": {"funding": [{"known_at": 4, "value": "0.3"}]}}
    view = rules.data_view(data, 3, strict=True)
    assert list(view) == ["X"] and len(view["X"]["funding"]) == 1
    assert list(rules.data_view(data, 10, symbols=["X"])) == ["X"]


def test_grid_categorical_axis_and_limit():
    grid = [{"n": 1, "type": "A"}, {"n": 2, "type": "A"}, {"n": 1, "type": "B"}]
    result = rules.select_grid_point(["-1", "-1", "1"], grid,
                                    {"numeric": {"n": [1, 2]}, "categorical": ["type"]})
    assert result["qualified"] == [False, False, True] and result["selected"] == 2
    with pytest.raises(ValueError):
        rules.select_grid_point(["1"] * 21, [{"n": i} for i in range(21)],
                                {"numeric": {"n": list(range(21))}, "categorical": []})


@pytest.mark.parametrize("mode", ["trial", "verification", "validation"])
def test_e2_model_cannot_bypass_fold_fit(inputs, mode):
    from program_code.research.r8_engine import lean_runner as runner
    _, manifest, config, query = inputs
    config["mode"] = mode
    query["finished"] = mode == "verification"
    if mode == "validation":
        config.update(trial_id=None, algorithm={"path": runner.EXAMPLE, "class": "FixedSchedule"})
    config["model_artifact"] = {"path": "arbitrary.json", "sha256": "1" * 64}
    with pytest.raises(ValueError, match="模型"):
        runner.validate_config(config, manifest, lambda t: query)


@pytest.mark.parametrize("source", [
    "from program_code.research.r8_engine.lean_algo.rules import datetime\nclass S:\n    def f(self):\n        return datetime.now()\n",
    "import program_code.research.r8_engine.lean_algo.rules as r\nclass S:\n    def f(self):\n        return r.datetime.now()\n",
    "from program_code.research.r8_engine.lean_algo.rules import canonical\n",
    "import statistics as s\nclass S:\n    def f(self):\n        return s.sys\n",
    "import random\nclass S:\n    def f(self):\n        alias = random\n        return alias.random()\n",
    "import random\nclass S:\n    def f(self):\n        factory = random.Random\n        return factory()\n",
])
def test_e2_static_reexports_and_module_aliases_denied(source):
    from program_code.research.r8_engine import lean_runner as runner
    with pytest.raises(ValueError):
        runner.check_algorithm(source)


def test_e2_rules_strictly_standard_library():
    tree = ast.parse((ROOT / "program_code/research/r8_engine/lean_algo/rules.py").read_text())
    for node in ast.walk(tree):
        modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) else []
        assert all(module.split(".")[0] in sys.stdlib_module_names for module in modules)


def test_fix1_validation_without_folds_requires_materialized_window(inputs):
    from program_code.research.r8_engine import lean_runner as runner
    _, manifest, config, _ = inputs
    config.update(mode="validation", trial_id=None, folds=[],
                  algorithm={"path": runner.EXAMPLE, "class": "FixedSchedule"},
                  score_windows=[manifest["window"]])
    runner.validate_config(config, manifest)
    for windows in ([], [{"start": 0, "end": DAY}], [manifest["window"]] * 2):
        config["score_windows"] = windows
        with pytest.raises(ValueError, match="score_windows"):
            runner.validate_config(config, manifest)


def test_fix1_run_sections_sorted_with_reduction_first(inputs):
    from program_code.research.r8_engine import lean_runner as runner
    config = inputs[2]
    records = {
        "orders": [{"order_id": 9, "_leg_index": 1, "quantity": "-50"},
                   {"order_id": 3}, {"order_id": 9, "_leg_index": 0, "quantity": "-100"}],
        "fills": [{"change_t": 10, "order_id": 9, "_leg_index": 1, "quantity": "-50"},
                  {"change_t": 5, "order_id": 3},
                  {"change_t": 10, "order_id": 9, "_leg_index": 0, "quantity": "-100"}],
        "voided": [{"order_id": 9}, {"order_id": 3}],
        "funding": [{"t": 10, "symbol": "B"}, {"t": 5, "symbol": "Z"}, {"t": 10, "symbol": "A"}],
        "endpoint_funding": [{"t": 10, "symbol": "B"}, {"t": 10, "symbol": "A"}],
        "decisions": [{"t": 10}, {"t": 5}], "steps": [{"t": 10}, {"t": 5}],
        "fits": [{"fold": 2}, {"fold": 0}],
    }
    events = [{"section": section, "record": record} for section, rows in records.items() for record in rows]
    result = runner.assemble_run(config, {}, [], "0" * 64, 0, 20, 0, b"", events)
    assert [r["order_id"] for r in result["orders"]] == [3, 9, 9]
    assert [r.get("quantity") for r in result["orders"]] == [None, "-100", "-50"]
    assert [r.get("quantity") for r in result["fills"]] == [None, "-100", "-50"]
    assert [r["order_id"] for r in result["voided"]] == [3, 9]
    assert [(r["t"], r["symbol"]) for r in result["funding"]] == [(5, "Z"), (10, "A"), (10, "B")]
    assert [r["symbol"] for r in result["endpoint_funding"]] == ["A", "B"]
    assert [r["t"] for r in result["steps"]] == [5, 10]
    assert [r["t"] for r in result["decisions"]] == [5, 10]
    assert [r["fold"] for r in result["fits"]] == [0, 2]
    assert all("_leg_index" not in r for key in records for r in result[key])


@pytest.mark.parametrize("t", [2 * HOUR, DAY])
def test_fix1_gap_symbols_hidden_until_current_hour_arrives(t):
    info = {"strategy_symbols": ["X", "Y"], "first_bar": {"X": 0, "Y": 0}, "delistings": {}}
    assert rules.decision_symbols(info, t, {"X": t, "Y": t - HOUR}) == ["X"]
    assert rules.decision_symbols(info, t + HOUR, {"X": t + HOUR, "Y": t + HOUR}) == ["X", "Y"]
    info["delistings"] = {"Y": {"deliveryTime": t}}
    assert rules.decision_symbols(info, t, {"X": t, "Y": t}) == ["X"]


def test_fix1_no_trade_flatten_is_not_a_decision():
    targets = {"X": {"weight": "0"}}
    assert rules.decision_record(HOUR, targets, "no_trade_flatten") is None
    assert rules.decision_record(HOUR, targets, "strategy") == {"t": HOUR, "targets": targets}


def test_fix1_zero_delta_cancellation_has_null_replacement(cost):
    segments = rules.order_segments("1", "1", "100", "1", "1", "0", None, "5", "100000", cost)
    assert segments == []
    counter, replacement = rules.replacement_order(7, segments)
    assert (counter, replacement) == (7, None)
    assert rules.cancellation_record({"order_id": 6, "decision_t": 0, "symbol": "X", "quantity": "2", "order_kind": "strategy", "_leg_index": 0}, HOUR, "replaced", replacement) == {
        "order_id": 6, "decision_t": 0, "symbol": "X", "quantity": "2", "_leg_index": 0,
        "kind": "strategy", "status": "cancelled", "cancel_t": HOUR,
        "cancel_reason": "replaced", "replaced_by": None}
    assert rules.replacement_order(counter, [{"quantity": "1"}]) == (8, 8)


def test_fix1_decimal_boundary_and_framework_equity():
    class NetDecimal:
        def GetType(self):
            return type("NetType", (), {"FullName": "System.Decimal"})()
        def ToString(self, format_spec, culture):
            assert format_spec == "G29" and culture is invariant
            return "99997.072904693755"
    invariant = object()
    cash = rules.lean_decimal(NetDecimal(), invariant)
    assert cash == Decimal("99997.072904693755")
    with pytest.raises(ValueError, match="NEEDS_CONTEXT"):
        rules.lean_decimal(99997.07290469375, invariant)
    assert rules.account_equity(cash, {"X": "0.123", "UNLISTED": "0"},
                                {"X": "43268.2233"}, {"X": "43246.6"}) == Decimal("99994.413238793755")
    assert rules.number(rules.fee("0.123", "43268.2233", "0.00055")) == "2.927095306245"
    tree = ast.parse((ROOT / "program_code/research/r8_engine/lean_algo/framework.py").read_text())
    # §13 允許把物化價轉為浮點作一致性比對；現金與成交不得讀回浮點。
    assert not any(isinstance(n, ast.Attribute) and n.attr in {"fill_price", "fill_quantity", "order_fee"}
                   and isinstance(n.ctx, ast.Load) and isinstance(n.value, ast.Name)
                   and n.value.id == "event" for n in ast.walk(tree))


@pytest.mark.parametrize("attribute", "gi_frame gi_code gi_yieldfrom cr_frame cr_await cr_code ag_frame ag_code f_back f_locals f_globals f_builtins f_code tb_frame tb_next".split())
def test_fix1_static_check_rejects_frame_access(attribute):
    from program_code.research.r8_engine import lean_runner as runner
    with pytest.raises(ValueError):
        runner.check_algorithm("def probe(x):\n    return x." + attribute)


@pytest.mark.parametrize("default", ["[]", "{}", "{1}", "list()", "dict()", "set()", "([],)", "[x for x in ()]"])
def test_fix1_static_check_rejects_mutable_defaults(default):
    from program_code.research.r8_engine import lean_runner as runner
    for signature in ("x=" + default, "*, x=" + default):
        with pytest.raises(ValueError):
            runner.check_algorithm("def probe(" + signature + "):\n    return x")


@pytest.mark.parametrize("name", ["getcontext", "setcontext", "localcontext"])
def test_fix1_static_check_rejects_decimal_context(name):
    from program_code.research.r8_engine import lean_runner as runner
    for source in (f"import decimal as d\ndef probe():\n    return d.{name}()",
                   f"from decimal import {name} as c\ndef probe():\n    return c()"):
        with pytest.raises(ValueError):
            runner.check_algorithm(source)


def test_fix1_indexed_view_scaling_and_readonly_prefix():
    from timeit import repeat
    datasets = []
    for size in (1000, 100000):
        data = {"X": {"kline_hour": [{"known_at": i, "t": i, "close": "1"} for i in range(size)]}}
        # 舊實作沒有一次性索引；保留其原路徑以量出重現比值。
        if hasattr(rules, "index_data"):
            data = rules.index_data(data)
        elapsed = min(repeat(lambda: rules.data_view(data, size), number=50, repeat=3))
        datasets.append((data, elapsed))
    assert datasets[1][1] / datasets[0][1] <= 10
    view = rules.data_view(datasets[1][0], 3)["X"]["kline_hour"]
    assert [r["t"] for r in view] == [0, 1, 2, 3]
    assert [r["t"] for r in view[::-1]] == [3, 2, 1, 0]
    with pytest.raises(TypeError):
        view[0]["close"] = "2"
    with pytest.raises(IndexError):
        _ = view[4]
    assert [r["t"] for r in rules.data_view(datasets[1][0], 3, strict=True)["X"]["kline_hour"]] == [0, 1, 2]


def test_fix1_position_and_turnover_index_queries():
    history = rules.PositionHistory()
    for t, qty in [(10, "2"), (30, "-1"), (20, "-0.5"), (20, "1")]:
        history.append({"symbol": "X", "change_t": t, "quantity": qty})
    assert history.at("X", 20) == (Decimal("2"), Decimal("2.5"))
    assert history.at("X", 30) == (Decimal("2.5"), Decimal("1.5"))
    assert history.at("Y", 20) == (Decimal(0), Decimal(0))
    rows = rules.KnownRows([{"known_at": 30, "value": "3"}, {"known_at": 10, "value": "1"}])
    assert rules.turnover_at(rows, 20) == "0"
    assert rules.turnover_at(rows, 30) == "3"
    prefix = rows.prefix(30)
    rows.append({"known_at": 40, "value": "4"})
    assert len(prefix) == 2


def test_fix1_score_end_gap_blocks_late_fill_and_uses_prior_close(cost):
    assert rules.next_open(HOUR, 2 * HOUR, 3 * HOUR, score_end=2 * HOUR) is None
    assert rules.next_open(HOUR, HOUR, 2 * HOUR, score_end=2 * HOUR) == HOUR
    bars = [{"t": 0, "end": HOUR, "close": "100"},
            {"t": 3 * HOUR, "end": 4 * HOUR, "close": "999"}]
    assert rules.settlement_bars(bars, 2 * HOUR) == (bars[0], None)
    last, _ = rules.settlement_bars(bars, 2 * HOUR)
    assert rules.number(rules.score_end_price("1", last["close"], cost)) == "99.4"
    events = rules.due_boundaries([{"start": 0, "end": 2 * HOUR}],
                                  {"X": {"deliveryTime": 3 * HOUR}}, 4 * HOUR, set(), set())
    assert events == [(2 * HOUR, "score_end", None), (3 * HOUR, "delivery", "X")]
    assert rules.due_boundaries([{"start": 0, "end": 2 * HOUR}], {}, 2 * HOUR, set(), set()) == [(2 * HOUR, "score_end", None)]
    assert rules.due_boundaries([{"start": 0, "end": 2 * HOUR}], {}, 4 * HOUR, {2 * HOUR}, set()) == []


def test_fix1_asynchronous_exposure_checked_after_delisting():
    # 同步回呼前 X 延後成交、Y 尚待下架結算；先結算 Y 後才判曝險。
    with pytest.raises(ValueError, match="gross_exposure_cap"):
        rules.exposure({"X": "6", "Y": "6"}, {"X": "100", "Y": "100"}, "1000", "1")
    assert rules.exposure({"X": "6", "Y": "0"}, {"X": "100", "Y": "100"}, "1000", "1") == Decimal("0.6")
    tree = ast.parse((ROOT / "program_code/research/r8_engine/lean_algo/framework.py").read_text())
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "on_data")
    calls = [n for n in ast.walk(method) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    boundary = next(n.lineno for n in calls if n.func.attr == "_boundaries")
    exposure = next(n.lineno for n in calls if n.func.attr == "exposure")
    assert boundary < exposure


def test_fix1_trial_rejects_hypothesis_inside_engine(inputs):
    from program_code.research.r8_engine import lean_runner as runner
    _, manifest, config, query = inputs
    config["algorithm"]["path"] = runner.EXAMPLE
    # 保持帳本身份一致，證明拒絕來自引擎目錄界線。
    query["record"]["configuration_sha256"] = runner.sha256(canonical(query["record"]["configuration"]))
    with pytest.raises(ValueError, match="引擎目錄"):
        runner.validate_config(config, manifest, lambda _: query)


@pytest.mark.parametrize("value", [Decimal("1"), 1, 1.0, None, True])
def test_fix1_score_requires_decimal_string(cost, value):
    class Hypothesis(rules.R8Hypothesis):
        def score(self, *args):
            return value
        def fit(self, *args):
            return None
    with pytest.raises(ValueError, match="invalid_decision"):
        rules.fit_fold(Hypothesis, 1, {"start": 0, "end": 400 * DAY}, {}, strategy(["1"]), cost)


def test_fix1_launcher_fixed_image_commented_algorithm_location(tmp_path):
    from program_code.research.r8_engine import lean_runner as runner
    # 記錄者 P4-D0 在固定映像讀出的第 9、12、15、18、19 行，保留原文。
    # 映像 sha256:2657ed3355efb78d78bd0a5d4f126b01367a635e01bccd220b654d7742d182b6。
    fragment = '''  "environment": "backtesting", // "live-paper", "backtesting", "live-interactive", "live-interactive-iqfeed"
  "algorithm-type-name": "BasicTemplateFrameworkAlgorithm",
  "algorithm-language": "CSharp",
  "algorithm-location": "QuantConnect.Algorithm.CSharp.dll",
  //"algorithm-location": "../../../Algorithm.Python/BasicTemplateFrameworkAlgorithm.py",
'''
    path = tmp_path / "config.json"
    path.write_text(fragment)
    # 只執行啟動器內的 Python 改寫片段；不執行 shell、dotnet 或 docker。
    rewrite = runner.LAUNCH_SCRIPT.split("python3 - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    completed = subprocess.run([sys.executable, "-c", rewrite], cwd=tmp_path, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    rewritten = path.read_text()
    assert '  //"algorithm-location": "../../../Algorithm.Python/BasicTemplateFrameworkAlgorithm.py",' in rewritten
    assert '"algorithm-location": "/r8/src/program_code/research/r8_engine/lean_algo/framework.py"' in rewritten
    assert '"algorithm-type-name": "R8Algorithm"' in rewritten
    assert '"algorithm-language": "Python"' in rewritten
    assert '"close-automatically": true' in rewritten
    assert ' // "live-paper", "backtesting", "live-interactive", "live-interactive-iqfeed"' in rewritten


def test_fix1_container_adapter_wires_host_rules_without_execution():
    # 保留 FIX1 的接線檢查；§13 另以假 LEAN 流程驗收，不取代 P4-D0。
    tree = ast.parse((ROOT / "program_code/research/r8_engine/lean_algo/framework.py").read_text())
    methods = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    def calls(name):
        return [n.func.attr for n in ast.walk(methods[name]) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert "decision_symbols" in calls("_visible")
    assert "decision_record" in calls("_submit_targets")
    assert "replacement_order" in calls("_submit_targets")
    assert "cancellation_record" in calls("_cancel")
    assert "KnownRows" in calls("_load_custom")
    assert "turnover_at" in calls("_submit_targets")
    assert "at" in calls("_funding") and "positions_at" not in calls("_funding")
    assert "settlement_bars" in calls("_settle")
    assert "_boundaries" in calls("on_end_of_algorithm")
    assert "Parse" in calls("to_lean")
    assert "lean_decimal" in calls("d")
    assert "account_equity" in calls("_equity")
    next_open = next(n for n in ast.walk(methods["_market_fill"]) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr == "next_open")
    assert isinstance(next_open.args[-1], ast.Subscript) and next_open.args[-1].slice.value == "score_end"


@pytest.mark.parametrize('attribute', ['format', 'format_map'])
def test_fix2_static_check_rejects_format_attribute_escape(attribute):
    from program_code.research.r8_engine import lean_runner as runner
    with pytest.raises(ValueError):
        runner.check_algorithm('def probe(data):\n    access = "{0._rows}".' + attribute + '\n    return access(data)')


@pytest.mark.parametrize('name', 'getattr setattr delattr vars dir globals locals eval exec compile __import__ open'.split())
def test_fix2_static_check_rejects_dynamic_builtins_even_when_aliased(name):
    from program_code.research.r8_engine import lean_runner as runner
    with pytest.raises(ValueError):
        runner.check_algorithm('def probe(data):\n    access = ' + name + '\n    return access(data)')


def test_fix2_view_public_operations_cannot_read_future_rows():
    rows = rules.KnownRows([{'t': t, 'known_at': t, 'close': str(t)} for t in range(6)])
    view = rules.data_view({'X': {'kline_hour': rows}}, 2)['X']['kline_hour']
    rows.append({'t': 6, 'known_at': 6, 'close': '6'})
    assert [r['t'] for r in view] == [0, 1, 2]
    assert [r['t'] for r in view[::-1][:100]] == [2, 1, 0]
    assert view.count({'t': 3, 'known_at': 3, 'close': '3'}) == 0
    with pytest.raises(ValueError):
        view.index({'t': 3, 'known_at': 3, 'close': '3'})
    assert all(name in {'index', 'count'} for name in dir(view) if not name.startswith('_'))


@pytest.fixture
def fake_lean(monkeypatch, tmp_path, cost):
    """只替換 LEAN/.NET 與掛載邊界；真正驅動 initialize、成交、on_data 與結束。"""
    import importlib.util
    import types
    import csv
    import io
    import zipfile
    from datetime import datetime, timezone
    ns = types.SimpleNamespace

    class Cash:
        def __init__(self, value):
            self.exact = Decimal(value)
        @property
        def amount(self):
            return float(self.exact)
        def add_amount(self, value):
            assert isinstance(value, Decimal)
            self.exact += value

    class Portfolio:
        def __init__(self):
            self.cash_book = {'USDT': Cash('0')}
            self.holdings = {}
        def __getitem__(self, symbol):
            if symbol not in self.holdings:
                holding = ns(quantity=Decimal(0), average=Decimal(0))
                def set_holdings(average, quantity):
                    holding.average, holding.quantity = Decimal(average), Decimal(quantity)
                holding.set_holdings = set_holdings
                self.holdings[symbol] = holding
            return self.holdings[symbol]

    class TradeBar:
        def __init__(self, t, values):
            self.time = datetime.fromtimestamp(t / 1000, timezone.utc).replace(tzinfo=None)
            self.end_time = datetime.fromtimestamp((t + HOUR) / 1000, timezone.utc).replace(tzinfo=None)
            self.is_fill_forward = False
            for key, value in zip(('open', 'high', 'low', 'close', 'volume'), values):
                setattr(self, key, float(value))

    class OrderEvent:
        def __init__(self, order, now, fee):
            self.order_id, self.status, self.order_fee = order.id, 'submitted', fee

    class QCAlgorithm:
        def __init__(self):
            self.portfolio = Portfolio()
            self.orders, self.securities, self.stops = {}, {}, []
            self.transactions = ns(get_order_by_id=self.orders.__getitem__)
        def set_time_zone(self, *args): pass
        def set_account_currency(self, *args): pass
        def set_start_date(self, *args): pass
        def set_end_date(self, *args): pass
        def set_cash(self, value): self.portfolio.cash_book['USDT'] = Cash(value)
        def quit(self, reason): self.stops.append(reason)
        def add_crypto_future(self, name, *args, **kwargs):
            security = ns(symbol=name, bar=None)
            security.set_fee_model = lambda value: None
            security.set_margin_interest_rate_model = lambda value: None
            security.set_fill_model = lambda value: setattr(security, 'fill_model', value)
            security.get_last_data = lambda: security.bar
            self.securities[name] = security
            return security
        def market_order(self, symbol, quantity, asynchronous, tag):
            order = ns(id=len(self.orders) + 1, symbol=symbol, quantity=quantity,
                       time=self.utc_time, tag=tag, status='submitted')
            def cancel(reason):
                order.status = 'cancelled'
                return ns(is_success=True)
            order.cancel = cancel
            self.orders[order.id] = order
            return order

    imports = types.ModuleType('AlgorithmImports')
    for name, value in dict(QCAlgorithm=QCAlgorithm, FillModel=object, TradeBar=TradeBar,
                            OrderEvent=OrderEvent, OrderStatus=ns(FILLED='filled', INVALID='invalid'),
                            OrderFee=lambda value: ns(value=value),
                            CashAmount=lambda amount, currency: ns(amount=amount),
                            TimeZones=ns(UTC='UTC'), Resolution=ns(HOUR='hour'), Market=ns(BYBIT='bybit'),
                            ConstantFeeModel=lambda value: value,
                            MarginInterestRateModel=ns(NULL=None)).items():
        setattr(imports, name, value)
    system = types.ModuleType('System')
    system.Decimal = ns(Parse=lambda value, *args: Decimal(value))
    culture = types.ModuleType('System.Globalization')
    culture.CultureInfo, culture.NumberStyles = ns(InvariantCulture=object()), ns(Number=object())
    json_net = types.ModuleType('Newtonsoft.Json')
    json_net.JsonConvert = ns(SerializeObject=lambda cash: '{"Amount":' + str(cash.exact) + '}')
    for name, module in [('AlgorithmImports', imports), ('System', system),
                         ('System.Globalization', culture), ('Newtonsoft.Json', json_net)]:
        monkeypatch.setitem(sys.modules, name, module)
    module_name = 'program_code.research.r8_engine.lean_algo.framework'
    spec = importlib.util.spec_from_file_location(module_name, ROOT / 'program_code/research/r8_engine/lean_algo/framework.py')
    framework = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, framework)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    spec.loader.exec_module(framework)
    mount = tmp_path / 'mount'
    def mounted(value):
        path = Path(value)
        if str(path).startswith(('/r8', '/Lean/Data')):
            return mount / str(path).lstrip('/')
        return path
    monkeypatch.setattr(framework, 'Path', mounted)
    base_t = 20 * DAY

    class Driver:
        def __init__(self, bars, schedule=(), folds=(), strategy_config=None, end=None, funding=None, initial='100000', hypothesis_source=None, verification=None):
            self.bars = bars
            self.algorithm = framework.R8Algorithm()
            self.t0 = base_t
            names = sorted(bars)
            end = end if end is not None else base_t + 6 * HOUR
            config = {'initial_cash': initial, 'leverage': '10', 'cost': cost,
                      'score_windows': [f['score_window'] for f in folds] if folds else [{'start': base_t, 'end': end}],
                      'folds': list(folds), 'model_artifact': None, 'random_seed': 1,
                      'algorithm': {'path': 'hypothesis.py', 'class': 'FixedSchedule'},
                      'strategy': strategy_config or {
                          'schedule': list(schedule), 'grid': [{'schedule': list(schedule)}],
                          'neighborhood': {'numeric': {}, 'categorical': ['schedule']}},
                      'decision_resolution': 'hour', 'gross_exposure_cap': '1'}
            info = {'symbols': names, 'strategy_symbols': names, 'first_bar': {s: 0 for s in names},
                    'delistings': {}, 'warmup': {'start': base_t - HOUR, 'end': base_t},
                    'window': {'start': base_t, 'end': end}, 'validation_example': True,
                    'properties': {s: {'qty_step': '0.001', 'min_qty': '0.001'} for s in names},
                    'min_notional': {s: '0' for s in names}, 'funding_interval_ms': {s: 8 * HOUR for s in names}}
            if verification is not None:
                info['verification'] = {'family': verification['family'], 'policy_sha256':'a'*64}
                table_path = mounted('/r8/framework-inputs/turnover_decisions.jsonl')
                table_path.parent.mkdir(parents=True)
                table_path.write_text(json.dumps(verification['turnover'])+'\n')
                for name in names:
                    listing_path = mounted('/r8/custom/listing_regime')/(name.lower()+'.csv')
                    listing_path.parent.mkdir(parents=True, exist_ok=True)
                    listing_path.write_text('known_at,day_start,stage,reason_code,cooling,policy_sha256\n'+verification['listing'])
            mounted('/r8/output').mkdir(parents=True)
            for file, obj in [('algorithm_config.json', config), ('framework.json', info)]:
                mounted('/r8/' + file).write_bytes(canonical(obj))
            path = mounted('/r8/src/hypothesis.py')
            path.parent.mkdir(parents=True)
            source = (ROOT / 'program_code/research/r8_engine/lean_algo/examples/fixed_schedule.py').read_text()
            path.write_text(hypothesis_source or source)
            for name, rows in bars.items():
                datasets = {'kline_day': [], 'funding': (funding or {}).get(name, []), 'open_interest': [],
                            'turnover_hour': [[t + HOUR, t, '100000000'] for t in rows],
                            'turnover_day': [[i * DAY, (i - 1) * DAY, '100000000'] for i in range(1, 23)]}
                for dataset, values in datasets.items():
                    file = mounted('/r8/custom') / dataset / (name.lower() + '.csv')
                    file.parent.mkdir(parents=True, exist_ok=True)
                    with file.open('w') as stream:
                        csv.writer(stream).writerows(values)
                output = io.StringIO()
                csv.writer(output).writerows([[datetime.fromtimestamp(t / 1000, timezone.utc).strftime('%Y%m%d %H:%M'), *v]
                                             for t, v in sorted(rows.items())])
                file = mounted('/Lean/Data/cryptofuture/bybit/hour') / (name.lower() + '_trade.zip')
                file.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(file, 'w') as archive:
                    archive.writestr(name.lower() + '_trade_perp.csv', output.getvalue())
            self.algorithm.initialize()
        def step(self, t, visible=None, corrupt=None, poison_event=False):
            algo = self.algorithm
            algo.utc_time = datetime.fromtimestamp(t / 1000, timezone.utc)
            delivered = {}
            for name, rows in self.bars.items():
                if t - HOUR in rows and (visible is None or name in visible):
                    delivered[name] = TradeBar(t - HOUR, rows[t - HOUR])
                    if corrupt:
                        setattr(delivered[name], *corrupt)
                    algo.securities[name].bar = delivered[name]
            # 模擬原生順序：先成交回呼，再進 on_data。
            for order in list(algo.orders.values()):
                if order.status != 'submitted' or order.symbol not in delivered:
                    continue
                event = algo.securities[order.symbol].fill_model.market_fill(algo.securities[order.symbol], order)
                if event.status != 'filled':
                    continue
                holding = algo.portfolio[order.symbol]
                qty, price, fee = event.fill_quantity, event.fill_price, event.order_fee.value.amount
                old = holding.quantity
                if old * qty < 0:
                    realized = min(abs(old), abs(qty)) * (price - holding.average) * (1 if old > 0 else -1)
                else:
                    realized = Decimal(0)
                if old == 0 or old * qty > 0:
                    holding.average = (abs(old) * holding.average + abs(qty) * price) / abs(old + qty)
                elif old + qty == 0:
                    holding.average = Decimal(0)
                holding.quantity += qty
                algo.portfolio.cash_book['USDT'].add_amount(realized - fee)
                order.status = 'filled'
                # pythonnet 讀回浮點數；極端污染值證明框架沒有讀回它們。
                event.fill_quantity = float(qty) if not poison_event else 987.0
                event.fill_price = float(price) if not poison_event else 999.0
                event.order_fee.value.amount = float(fee) if not poison_event else 999.0
                algo.on_order_event(event)
            algo.on_data(ns(bars=delivered))
        def records(self, section):
            return [r['record'] for r in map(json.loads, mounted('/r8/output/events.jsonl').read_bytes().splitlines())
                    if r['section'] == section]
        def finish(self):
            self.algorithm.on_end_of_algorithm()
    return ns(Driver=Driver, t0=base_t, framework=framework, json_net=json_net, mounted=mounted)


def test_fix2_framework_cash_json_preserves_exact_decimal(fake_lean):
    t = fake_lean.t0
    driver = fake_lean.Driver({'X': {t - HOUR: ['100', '100', '100', '100', '1']}}, initial='99997.072904693755')
    driver.step(t)
    assert driver.algorithm.stops == []
    assert driver.records('cash_residual') == []
    assert driver.records('steps')[0]['cash'] == '99997.072904693755'


def test_fix2_framework_materialized_prices_and_owned_fill_precision(fake_lean):
    t = fake_lean.t0
    bars = {'X': {t - HOUR: ['43246.6'] * 4 + ['1'], t: ['43246.6'] * 4 + ['1']}}
    driver = fake_lean.Driver(bars, [{'t': t, 'targets': {'X': {'quantity': '0.123'}}}],
                              funding={'X': [[t, t, '0']]})
    driver.step(t)
    driver.step(t + HOUR, poison_event=True)
    assert driver.algorithm.stops == []
    fill = driver.records('fills')[0]
    assert (fill['quantity'], fill['price'], fill['fee']) == ('0.123', '43268.2233', '2.927095306245')
    assert driver.records('steps')[-1]['cash'] == '99997.072904693755'
    assert driver.records('cash_residual') == []


@pytest.mark.parametrize('corrupt', [('close', 101.0), ('open', float('nan'))])
def test_fix2_framework_price_mismatch_is_lean_error(fake_lean, corrupt):
    t = fake_lean.t0
    driver = fake_lean.Driver({'X': {t - HOUR: ['100'] * 4 + ['1']}})
    driver.step(t, corrupt=corrupt)
    assert driver.algorithm.stops == ['lean_error']


def test_fix2_framework_cash_read_failure_is_lean_error(fake_lean):
    t = fake_lean.t0
    driver = fake_lean.Driver({'X': {t - HOUR: ['100'] * 4 + ['1']}})
    fake_lean.json_net.JsonConvert.SerializeObject = lambda cash: '{"Amount":"invalid"}'
    driver.step(t)
    assert driver.algorithm.stops == ['lean_error']


def test_fix2_framework_missing_materialized_bar_is_lean_error(fake_lean):
    t = fake_lean.t0
    driver = fake_lean.Driver({'X': {t - HOUR: ['100'] * 4 + ['1']}})
    # LEAN 送達一根不在物化檔案裡的線。
    driver.bars['X'][t] = ['100'] * 4 + ['1']
    driver.step(t + HOUR)
    assert driver.algorithm.stops == ['lean_error']


@pytest.mark.parametrize('pending_quantity,expected', [('100', []), ('800', ['gross_exposure_cap'])])
def test_fix2_framework_delayed_fill_exposure_keeps_missing_pending_price(fake_lean, pending_quantity, expected):
    t = fake_lean.t0
    bar = ['100'] * 4 + ['1']
    driver = fake_lean.Driver({'X': {t - HOUR: bar, t: bar, t + HOUR: bar},
                               'Y': {t - HOUR: bar, t + HOUR: ['200'] * 4 + ['1']}},
                              [{'t': t, 'targets': {'X': {'quantity': '0'}, 'Y': {'quantity': pending_quantity}}},
                               {'t': t + HOUR, 'targets': {'X': {'quantity': '500'}}}],
                              funding={'X': [[t, t, '0']], 'Y': [[t, t, '0']]})
    driver.step(t)
    driver.step(t + HOUR)
    driver.step(t + 2 * HOUR)
    assert driver.algorithm.stops == expected
    assert [(r['symbol'], r['quantity']) for r in driver.records('fills')] == [('Y', pending_quantity), ('X', '500')]
    assert driver.records('cash_residual') == []


@pytest.mark.parametrize('all_invisible', [False, True])
def test_fix2_framework_no_trade_cancels_all_and_flattens_on_first_visibility(fake_lean, all_invisible):
    t = fake_lean.t0
    bar = ['100'] * 4 + ['1']
    schedule = [{'t': t, 'targets': {s: {'quantity': q} for s, q in [('X', '1'), ('Y', '2'), ('Z', '3'), ('W', '0')]}}]
    config = strategy(['1'])
    config['grid'][0].update(schedule=schedule, no_trade_at=t + HOUR)
    config['neighborhood']['categorical'] = ['n', 'score', 'schedule', 'no_trade_at']
    folds = [{'fit_window': {'start': -400 * DAY, 'end': t - HOUR},
              'score_window': {'start': t, 'end': t + 2 * HOUR}},
             {'fit_window': {'start': -400 * DAY, 'end': t + HOUR},
              'score_window': {'start': t + 2 * HOUR, 'end': t + 6 * HOUR}}]
    bars = {'X': {t + i * HOUR: bar for i in [-1, 0, 1, 3, 4]},
            'Y': {t + i * HOUR: bar for i in [-1, 0, 2, 3, 4]},
            'Z': {t - HOUR: bar},
            'W': {t + i * HOUR: bar for i in [-1, 0, 1, 2, 3, 4]}}
    driver = fake_lean.Driver(bars, folds=folds, strategy_config=config,
                              funding={s: [[t, t, '0']] for s in bars})
    driver.step(t)
    driver.step(t + HOUR)
    driver.step(t + 2 * HOUR, visible=[] if all_invisible else None)
    cancelled = [r for r in driver.records('orders') if r['status'] == 'cancelled']
    assert [(r['symbol'], r['cancel_reason'], r['cancel_t']) for r in cancelled] == [('Z', 'no_trade', t + 2 * HOUR)]
    for step in (3, 4, 5):
        driver.step(t + step * HOUR)
    driver.finish()
    assert driver.algorithm.stops == []
    flattened = [r for r in driver.records('orders') if r['kind'] == 'no_trade_flatten']
    assert sorted((r['symbol'], r['quantity']) for r in flattened) == [('X', '-1'), ('Y', '-2')]
    by_symbol = {r['symbol']: r for r in flattened}
    assert by_symbol['X']['decision_t'] == t + (4 if all_invisible else 2) * HOUR
    assert by_symbol['Y']['decision_t'] == t + 3 * HOUR
    assert len(driver.records('decisions')) == 1
    assert driver.records('steps')[-1]['positions'] == {}
    assert driver.records('cash_residual') == []
    assert driver.records('finished') == [{'status': 'completed', 'failure_reason': None, 'failure_t': None}]


def test_fix2_framework_window_end_funding_after_last_step_and_exact_endpoint(fake_lean):
    t = fake_lean.t0
    end = t + 4 * HOUR
    driver = fake_lean.Driver({'X': {t - HOUR: ['100'] * 4 + ['1'], t: ['100'] * 4 + ['1']}},
                              [{'t': t, 'targets': {'X': {'quantity': '2'}}}], end=end,
                              funding={'X': [[t, t, '0'], [t + 2 * HOUR, t + 2 * HOUR, '0.001'],
                                             [end, end, '0.002']]})
    driver.step(t)
    driver.step(t + HOUR)
    driver.finish()
    assert driver.algorithm.stops == []
    assert [(r['t'], r['amount']) for r in driver.records('funding')] == [(t, '0'), (t + 2 * HOUR, '-0.204')]
    assert [(r['t'], r['amount']) for r in driver.records('endpoint_funding')] == [(end, '-0.408')]
    assert driver.algorithm.portfolio.cash_book['USDT'].exact == Decimal('99998.276605')
    assert driver.records('fills')[-1]['kind'] == 'score_end_liquidation'
    assert driver.records('fills')[-1]['change_t'] == end
    assert driver.records('steps')[-1]['t'] == t + HOUR
    assert driver.records('cash_residual') == []


@pytest.mark.parametrize('targets', [[], {'Y': {'weight': '0'}}, {'X': None}, {'X': {'weight': 0.5}},
                                     {'X': {'weight': 'NaN'}}, {'X': {'quantity': 'bad'}}])
def test_fix2_framework_invalid_targets_are_decision_errors(fake_lean, targets):
    t = fake_lean.t0
    source = ('from program_code.research.r8_engine.lean_algo.rules import R8Hypothesis\n'
              'class FixedSchedule(R8Hypothesis):\n'
              '    def on_decision(self, *args):\n'
              '        return ' + repr(targets) + '\n')
    driver = fake_lean.Driver({'X': {t - HOUR: ['100'] * 4 + ['1']}}, hypothesis_source=source)
    driver.step(t)
    assert driver.algorithm.stops == ['invalid_decision']
    assert driver.records('orders') == []


def test_fix2_framework_malformed_score_is_decision_error(fake_lean):
    t = fake_lean.t0
    driver = fake_lean.Driver({'X': {t - HOUR: ['100'] * 4 + ['1']}},
                              folds=[{'fit_window': {'start': -400 * DAY, 'end': t - HOUR},
                                      'score_window': {'start': t, 'end': t + 6 * HOUR}}],
                              strategy_config=strategy(['not-a-number']))
    driver.step(t)
    assert driver.algorithm.stops == ['invalid_decision']


def test_fix2_framework_hypothesis_exception_is_not_a_boundary_or_decision_error(fake_lean):
    t = fake_lean.t0
    source = ('from program_code.research.r8_engine.lean_algo.rules import R8Hypothesis\n'
              'class FixedSchedule(R8Hypothesis):\n'
              '    def on_decision(self, *args):\n'
              '        raise ValueError("hypothesis bug")\n')
    driver = fake_lean.Driver({'X': {t - HOUR: ['100'] * 4 + ['1']}}, hypothesis_source=source)
    driver.step(t)
    assert driver.algorithm.stops == ['algorithm_exception']


def test_fix2_framework_fill_boundary_failure_has_current_time(fake_lean):
    t = fake_lean.t0
    driver = fake_lean.Driver({'X': {t - HOUR: ['100'] * 4 + ['1'], t: ['100'] * 4 + ['1']}},
                              [{'t': t, 'targets': {'X': {'quantity': '1'}}}])
    driver.step(t)
    driver.step(t + HOUR, corrupt=('open', 101.0))
    driver.finish()
    assert driver.records('finished') == [{'status': 'failed', 'failure_reason': 'lean_error', 'failure_t': t + HOUR}]
    assert driver.records('fills') == []


def test_fix2_framework_cash_write_failure_is_lean_error(fake_lean):
    t = fake_lean.t0
    driver = fake_lean.Driver({'X': {t + i * HOUR: ['100'] * 4 + ['1'] for i in range(-1, 3)}},
                              [{'t': t, 'targets': {'X': {'quantity': '1'}}}],
                              funding={'X': [[t, t, '0'], [t + 2 * HOUR, t + 2 * HOUR, '0.001']]})
    driver.step(t)
    driver.step(t + HOUR)
    def reject(value):
        raise RuntimeError('fake LEAN cash write error')
    driver.algorithm.portfolio.cash_book['USDT'].add_amount = reject
    driver.step(t + 3 * HOUR)
    assert driver.algorithm.stops == ['lean_error']


# §14.2 第 2 點的 JSON 原文，不另行生成軸或網格。
FIX3_STRATEGY_JSON = """
{
  "neighborhood": {
    "numeric": {"lookback": ["10", "20"]},
    "categorical": ["mode"]
  },
  "grid": [
    {"lookback": "10", "mode": "trend"},
    {"lookback": "20", "mode": "trend"},
    {"lookback": "10", "mode": "revert"},
    {"lookback": "20", "mode": "revert"}
  ]
}
"""


def test_fix3_neighborhood_contract_json_selection():
    config = json.loads(FIX3_STRATEGY_JSON)
    assert rules.select_grid_point(['1', '3', '2', '8'], config['grid'], config['neighborhood']) == {
        'grid_scores': ['1', '3', '2', '8'], 'neighborhood_means': ['2', '2', '5', '5'],
        'qualified': [True, True, True, True], 'selected': 2,
        'selected_minus_neighborhood': '-3', 'no_trade': False}


@pytest.mark.parametrize('neighborhood,grid', [
    ({'numeric': {}, 'categorical': {'mode': ['trend']}}, [{'mode': 'trend'}]),
    ({'numeric': {}, 'categorical': []}, [{'undeclared': 'value'}]),
    ({'numeric': {'n': ['1']}, 'categorical': ['n']}, [{'n': '1'}]),
    ({'numeric': {'n': ['2', '1']}, 'categorical': []}, [{'n': '1'}]),
    ({'numeric': {'n': ['1', '1.0']}, 'categorical': []}, [{'n': '1'}]),
    ({'numeric': {'n': []}, 'categorical': []}, [{'n': '1'}]),
    ({'numeric': {'n': '12'}, 'categorical': []}, [{'n': '1'}]),
    ({'numeric': {'n': ['1']}, 'categorical': []}, [{'n': '2'}]),
    ({'numeric': {}, 'categorical': ['mode']}, [{}]),
    ({'numeric': {}, 'categorical': ['mode', 'mode']}, [{'mode': 'trend'}]),
    ({'numeric': {}, 'categorical': [], 'extra': []}, [{}]),
    ({'numeric': {}}, [{}]),
    ({'categorical': []}, [{}]),
    ({}, [{}]),
    (None, [{}]),
    ({'numeric': [], 'categorical': []}, [{}]),
    ({'numeric': {}, 'categorical': [None]}, [{}]),
], ids=['categorical_mapping', 'undeclared_key', 'overlap', 'descending', 'decimal_duplicate',
        'empty_numeric', 'numeric_not_list', 'unlisted_value', 'missing_axis', 'duplicate_category',
        'extra_section', 'missing_categorical', 'missing_numeric', 'empty_neighborhood',
        'null_neighborhood', 'numeric_not_mapping', 'invalid_axis_name'])
def test_fix3_neighborhood_rejects_invalid_shape(neighborhood, grid):
    with pytest.raises(ValueError):
        rules.select_grid_point(['1'] * len(grid), grid, neighborhood)


@pytest.mark.parametrize('mode', ['validation', 'trial', 'verification'])
@pytest.mark.parametrize('with_folds', [False, True])
@pytest.mark.parametrize('invalid', ['empty_neighborhood', 'categorical_mapping', 'undeclared_key',
                                    'bool_true', 'bool_false'])
def test_fix3_runner_rejects_neighborhood_before_lean(inputs, git_fixture, tmp_path, mode, with_folds, invalid):
    from program_code.research.r8_engine import lean_runner as runner
    materialization, manifest, config, query = inputs
    repo, _, head = git_fixture
    config.update(mode=mode, code_commit=head, engine_commit=head)
    if mode == 'validation':
        config.update(trial_id=None, algorithm={'path': runner.EXAMPLE, 'class': 'FixedSchedule'})
    if not with_folds:
        config.update(folds=[], fit_window={'start': 0, 'end': 392 * DAY},
                      score_windows=[manifest['window']] if mode == 'validation' else [])
    if invalid == 'empty_neighborhood':
        config['strategy']['neighborhood'] = {}
    elif invalid == 'categorical_mapping':
        config['strategy']['neighborhood']['categorical'] = {'n': [0], 'score': ['1']}
    elif invalid in ('bool_true', 'bool_false'):
        value = invalid == 'bool_true'
        config['strategy']['neighborhood'] = {'numeric': {'n': [int(value)]}, 'categorical': ['score']}
        config['strategy']['grid'][0]['n'] = value
    else:
        config['strategy']['grid'][0]['undeclared'] = 'extra'
    # 試驗身份與來源皆有效，使拒絕只來自鄰域檢查。
    record = query['record']
    record.update(code_commit=head, folds=config['folds'])
    record['configuration']['strategy_parameters']['run']['engine_commit'] = head
    record['configuration_sha256'] = runner.sha256(canonical(record['configuration']))
    query['finished'] = mode == 'verification'
    out = tmp_path / 'invalid-run'
    calls = []
    def process(*args, **kwargs):
        calls.append(args)
        pytest.fail('無效鄰域不得啟動 LEAN')
    with pytest.raises(ValueError, match='鄰域|網格'):
        runner.execute(config, materialization, out, repo=repo, query=lambda _: query, process=process)
    assert calls == []
    assert not out.exists()
    assert not (out / 'run.json').exists()


@pytest.mark.parametrize('value,option', [(True, 1), (False, 0)])
def test_fix3_numeric_grid_rejects_boolean_alias(value, option):
    with pytest.raises(ValueError, match='數值軸'):
        rules.select_grid_point(['1'], [{'n': value}], {'numeric': {'n': [option]}, 'categorical': []})


@pytest.mark.parametrize('offset,expected', [(-HOUR, False), (0, True), (HOUR, True)])
def test_fix3_example_no_trade_at_selects_by_validation_end(fake_lean, cost, offset, expected):
    from program_code.research.r8_engine.lean_algo.examples.fixed_schedule import FixedSchedule
    config = strategy(['1'])
    config['grid'][0]['no_trade_at'] = 400 * DAY
    config['neighborhood']['categorical'] = ['n', 'score', 'no_trade_at']
    result = rules.fit_fold(FixedSchedule, 1, {'start': 0, 'end': 400 * DAY + offset}, {}, config, cost)
    assert result['selection']['grid_scores'] == ['-1' if expected else '1']
    assert result['selection']['no_trade'] is expected
    assert (result['artifact'] is None) is expected


def test_fix3_example_without_no_trade_at_keeps_score(fake_lean, cost):
    from program_code.research.r8_engine.lean_algo.examples.fixed_schedule import FixedSchedule
    config = strategy(['2'])
    result = rules.fit_fold(FixedSchedule, 1, {'start': 0, 'end': 400 * DAY}, {}, config, cost)
    assert result['selection']['grid_scores'] == ['2']
    assert result['selection']['no_trade'] is False


@pytest.mark.parametrize('all_invisible', [False, True])
def test_fix3_no_trade_zero_position_reappearance_preserves_exposure_reference(fake_lean, all_invisible):
    t = fake_lean.t0
    bar = ['100'] * 4 + ['1']
    config = strategy(['1'])
    config['grid'][0].update(no_trade_at=t + HOUR, schedule=[
        {'t': t, 'targets': {'X': {'quantity': '1'}, 'Y': {'quantity': '0'}}}])
    config['neighborhood']['categorical'] = ['n', 'score', 'schedule', 'no_trade_at']
    folds = [{'fit_window': {'start': -400 * DAY, 'end': t - HOUR},
              'score_window': {'start': t, 'end': t + 2 * HOUR}},
             {'fit_window': {'start': -400 * DAY, 'end': t + HOUR},
              'score_window': {'start': t + 2 * HOUR, 'end': t + 6 * HOUR}}]
    bars = {'X': {t + i * HOUR: bar for i in [-1, 0, 1, 3, 4]},
            'Y': {t - HOUR: bar, **{t + i * HOUR: ['200'] * 4 + ['1'] for i in [2, 3, 4]}}}
    driver = fake_lean.Driver(bars, folds=folds, strategy_config=config,
                              funding={'X': [[t, t, '0'], [t + HOUR, t + HOUR, '0.001']]})
    driver.step(t)
    driver.step(t + HOUR)
    driver.step(t + 2 * HOUR, visible=[] if all_invisible else None)
    prices = dict(driver.algorithm._last_decision_prices)
    equity = driver.algorithm._last_decision_equity
    decisions = driver.records('decisions')
    orders = driver.records('orders')
    # 只有零部位的 Y 恢復可見；不得形成新的平倉決策或更新曝險參照。
    driver.step(t + 3 * HOUR)
    assert driver.records('decisions') == decisions
    assert driver.records('orders') == orders
    assert driver.algorithm._last_decision_prices == prices
    assert driver.algorithm._last_decision_equity == equity
    assert len(driver.algorithm.orders) == (1 if all_invisible else 2)
    for step in (4, 5):
        driver.step(t + step * HOUR)
    driver.finish()
    assert driver.algorithm.stops == []
    flattened = [r for r in driver.records('orders') if r['kind'] == 'no_trade_flatten']
    assert [(r['symbol'], r['quantity'], r['decision_t']) for r in flattened] == [
        ('X', '-1', t + (4 if all_invisible else 2) * HOUR)]
    assert driver.records('steps')[-1]['positions'] == {}


@pytest.mark.parametrize('fit_at_boundary', [False, True])
def test_fix3_fold_boundary_fills_previous_bar_before_no_trade(fake_lean, fit_at_boundary):
    t = fake_lean.t0
    s = t + 2 * HOUR
    fit_end = s if fit_at_boundary else s - HOUR
    config = strategy(['1'])
    config['grid'][0].update(no_trade_at=fit_end, schedule=[
        {'t': s - HOUR, 'targets': {'X': {'quantity': '10'}, 'Y': {'quantity': '3'}}}])
    config['neighborhood']['categorical'] = ['n', 'score', 'schedule', 'no_trade_at']
    folds = [{'fit_window': {'start': -400 * DAY, 'end': t - HOUR},
              'score_window': {'start': t, 'end': s}},
             {'fit_window': {'start': -400 * DAY, 'end': fit_end},
              'score_window': {'start': s, 'end': s + 2 * HOUR}}]
    bar = ['100'] * 4 + ['1']
    bars = {'X': {t - HOUR: bar, t: bar, s - HOUR: bar, s: ['101'] * 4 + ['1']},
            'Y': {t - HOUR: bar, t: bar, s: bar}}
    driver = fake_lean.Driver(bars, folds=folds, strategy_config=config, end=s + 2 * HOUR,
                              funding={name: [[t, t, '0']] for name in bars})
    driver.step(t)
    driver.step(s - HOUR)
    assert driver.records('fills') == []
    driver.step(s)
    assert driver.algorithm.stops == []
    fills = driver.records('fills')
    assert [(r['symbol'], r['quantity'], r['change_t'], r['price']) for r in fills] == [
        ('X', '10', s - HOUR, '100.05')]
    cancelled = [r for r in driver.records('orders') if r['status'] == 'cancelled']
    assert [(r['symbol'], r['cancel_reason'], r['cancel_t']) for r in cancelled] == [('Y', 'no_trade', s)]
    # X 已入帳，折界才下平倉單；Y 的下一根開始於 s，仍未成交而取消。
    assert driver.records('steps')[-1]['positions'] == {'X': '10'}
    assert [r['selection']['no_trade'] for r in driver.records('fits')] == [False, True]
    driver.step(s + HOUR)
    driver.finish()
    assert driver.algorithm.stops == []
    assert [(r['symbol'], r['quantity'], r['change_t'], r['price']) for r in driver.records('fills')] == [
        ('X', '10', s - HOUR, '100.05'), ('X', '-10', s, '100.9495')]
    flatten = [r for r in driver.records('orders') if r['kind'] == 'no_trade_flatten']
    assert [(r['symbol'], r['decision_t'], r['quantity'], r['status']) for r in flatten] == [
        ('X', s, '-10', 'filled')]
    assert driver.records('decisions') == [
        {'t': s - HOUR, 'targets': {'X': {'quantity': '10'}, 'Y': {'quantity': '3'}}}]
    assert driver.records('steps')[-1]['positions'] == {}
    assert driver.records('steps')[-1]['cash'] == '100007.88950275'
    assert driver.records('cash_residual') == []
    assert driver.records('finished') == [{'status': 'completed', 'failure_reason': None, 'failure_t': None}]


@pytest.fixture
def fix4_driver(fake_lean, monkeypatch):
    """保留 FIX3 驅動器；只在掛載邊界提供構造 CSV，走原框架的載入與視圖。"""
    import csv

    initialize = fake_lean.framework.R8Algorithm.initialize

    def create(dataset, rows, probe, schedule=(), folds=()):
        def initialize_with_custom_rows(algorithm):
            path = fake_lean.mounted('/r8/custom') / dataset / 'x.csv'
            with path.open('w') as stream:
                csv.writer(stream).writerows(rows)
            initialize(algorithm)

        monkeypatch.setattr(fake_lean.framework.R8Algorithm, 'initialize', initialize_with_custom_rows)
        params = {'score': '1', 'schedule': list(schedule)}
        categorical = ['score', 'schedule']
        if probe is not None:
            params['visibility_probe'] = probe
            # §15.2：探針是整個 JSON 值的類別軸，不是數值鄰域。
            categorical.append('visibility_probe')
        config = {**params, 'grid': [params],
                  'neighborhood': {'numeric': {}, 'categorical': categorical}}
        if folds:
            config.update(internal_validation_days=2, internal_gap_days=1)
        t = fake_lean.t0
        bars = {s: {t + i * HOUR: ['100'] * 4 + ['1'] for i in range(-1, 7)}
                for s in ('X', 'Y', 'Z')}
        return fake_lean.Driver(bars, strategy_config=config, folds=folds)

    return create


@pytest.mark.parametrize('dataset,field,offset,lookahead,scheduled,expected', [
    ('kline_day', 'close', HOUR, False, True, '2'),
    ('kline_day', 'close', HOUR, True, True, '7'),
    ('open_interest', 'value', HOUR, False, False, '2'),
    ('open_interest', 'value', HOUR, True, False, '7'),
    ('open_interest', 'value', 4 * HOUR, False, False, '7'),
], ids=['daily_visible', 'daily_lookahead_control', 'oi_visible',
        'oi_lookahead_control', 'oi_exact_four_hour_boundary'])
def test_fix4_visibility_probe_observes_framework_view(
        fake_lean, fix4_driver, dataset, field, offset, lookahead, scheduled, expected):
    t, probe_t = fake_lean.t0, fake_lean.t0 + offset
    # 日線：前日完成於 T、當日完成於 T+1d；OI：T-4h、T，分別於 T、T+4h 可見。
    delay = DAY if dataset == 'kline_day' else 4 * HOUR
    values = [['10', '40', '5', '100', '1'], ['20', '80', '6', '900', '1']] if field == 'close' else [['100'], ['900']]
    rows = [[t, t - delay, *values[0]], [t + delay, t, *values[1]]]
    if lookahead:
        # 故意提早公開第二列的反例；若視圖前視，策略必須輸出另一數量。
        rows[1][0] = probe_t
    probe = {'t': probe_t, 'symbol': 'X', 'dataset': dataset, 'field': field,
             'map': {'100': '2', '900': '7'}}
    schedule = [{'t': probe_t, 'targets': {'X': {'quantity': '99'}, 'Y': {'quantity': '3'}}}] if scheduled else []
    driver = fix4_driver(dataset, rows, probe, schedule)
    for now in range(t, probe_t + 2 * HOUR, HOUR):
        driver.step(now)
    targets = {'X': {'quantity': expected},
               'Y': {'quantity': '3'} if scheduled else {'weight': '0'}, 'Z': {'weight': '0'}}
    assert driver.algorithm.stops == []
    assert driver.records('decisions') == [{'t': probe_t, 'targets': targets}]
    assert [(r['quantity'], r['change_t']) for r in driver.records('fills') if r['symbol'] == 'X'] == [(expected, probe_t)]
    driver.finish()
    assert driver.records('cash_residual') == []
    assert driver.records('finished') == [{'status': 'completed', 'failure_reason': None, 'failure_t': None}]


@pytest.mark.parametrize('dataset,field', [('kline_day', 'close'), ('open_interest', 'value')])
@pytest.mark.parametrize('failure', ['unmapped_value', 'no_visible_row'])
def test_fix4_visibility_probe_missing_lookup_is_algorithm_exception(
        fake_lean, fix4_driver, dataset, field, failure):
    from program_code.research.r8_engine.lean_algo.examples.fixed_schedule import FixedSchedule

    t = fake_lean.t0
    # 無可見列的檔案仍含未來資料，不能繞過視圖去取檔案的最後一列。
    known_at = t if failure == 'unmapped_value' else t + DAY
    values = ['100'] * 4 + ['1'] if field == 'close' else ['100']
    rows = [[known_at, t - DAY, *values]]
    probe = {'t': t, 'symbol': 'X', 'dataset': dataset, 'field': field, 'map': {'900': '7'}}
    driver = fix4_driver(dataset, rows, probe)
    view = rules.data_view({'X': {dataset: [{'known_at': known_at, 't': t - DAY, field: '100'}]}}, t)
    with pytest.raises((KeyError, IndexError, ValueError)):
        FixedSchedule(1).on_decision(t, view, None, {'visibility_probe': probe})
    driver.step(t)
    driver.finish()
    assert driver.algorithm.stops == ['algorithm_exception']
    assert driver.records('decisions') == []
    assert driver.records('orders') == []
    assert driver.records('fills') == []
    assert driver.records('finished') == [
        {'status': 'failed', 'failure_reason': 'algorithm_exception', 'failure_t': t}]


def test_fix4_visibility_probe_categorical_grid_reaches_decision(fake_lean, fix4_driver):
    t = fake_lean.t0
    probe = {'t': t, 'symbol': 'X', 'dataset': 'open_interest', 'field': 'value',
             'map': {'100': '2', '900': '7'}}
    folds = [{'fit_window': {'start': 0, 'end': t - HOUR},
              'score_window': {'start': t, 'end': t + 6 * HOUR}}]
    driver = fix4_driver('open_interest', [[t, t - 4 * HOUR, '100']], probe, folds=folds)
    driver.step(t)
    driver.step(t + HOUR)
    driver.finish()
    assert driver.algorithm.stops == []
    fit, = driver.records('fits')
    assert fit['selection']['selected'] == 0
    assert fit['params']['visibility_probe'] == probe
    assert driver.records('decisions') == [
        {'t': t, 'targets': {'X': {'quantity': '2'}, 'Y': {'weight': '0'}, 'Z': {'weight': '0'}}}]
    assert driver.records('fills')[0]['quantity'] == '2'
    assert driver.records('finished') == [{'status': 'completed', 'failure_reason': None, 'failure_t': None}]


@pytest.mark.parametrize('with_probe', [False, True], ids=['without_probe', 'outside_probe_time'])
def test_fix4_schedule_behavior_unchanged(fake_lean, fix4_driver, with_probe):
    t = fake_lean.t0
    probe = {'t': t + 5 * HOUR, 'symbol': 'X', 'dataset': 'open_interest', 'field': 'value',
             'map': {}} if with_probe else None
    schedule = [
        {'t': t, 'targets': {'X': {'quantity': '3'}, 'Y': {'quantity': '1'}, 'NOT_VISIBLE': {'quantity': '9'}}},
        {'t': t, 'targets': {'X': {'quantity': '99'}}},
        {'t': t + 2 * HOUR, 'targets': {'X': {'quantity': '0'}, 'Y': {'quantity': '0'}}}]
    driver = fix4_driver('open_interest', [], probe, schedule)
    for now in range(t, t + 4 * HOUR, HOUR):
        driver.step(now)
    driver.finish()
    assert driver.algorithm.stops == []
    assert driver.records('decisions') == [
        {'t': t, 'targets': {'X': {'quantity': '3'}, 'Y': {'quantity': '1'}, 'Z': {'weight': '0'}}},
        {'t': t + 2 * HOUR, 'targets': {'X': {'quantity': '0'}, 'Y': {'quantity': '0'}, 'Z': {'weight': '0'}}}]
    assert [(r['symbol'], r['quantity']) for r in driver.records('fills')] == [
        ('X', '3'), ('Y', '1'), ('X', '-3'), ('Y', '-1')]
    assert driver.records('finished') == [{'status': 'completed', 'failure_reason': None, 'failure_t': None}]


def test_fix4_example_passes_runner_static_check():
    from program_code.research.r8_engine.lean_runner import EXAMPLE, check_algorithm

    check_algorithm((ROOT / EXAMPLE).read_text())

# DV5: literal §8.4 consumer fixtures, not DV2/DV6 interoperability evidence.
def dv5_data(future=True):
    stages = [(HOUR if i==0 else i*DAY, i*DAY,
               'initial' if i<3 else 'middle' if i<15 else 'stabilizing' if i<30 else 'ordinary',
               None if i<15 else i<30) for i in range(401 if future else 15)]
    listing = [dict(known_at=k, day_start=t, stage=s, reason_code='BOUNDARY', cooling=c,
                    policy_sha256='a'*64) for k, t, s, c in stages]
    bars = [dict(t=t, known_at=t+HOUR, close='1', volume='2') for t in (0, 2*DAY, 14*DAY, 29*DAY, 30*DAY)]
    return {'X': {'listing_regime': listing, 'kline_hour': bars,
                  'kline_day': [dict(t=r['t'], known_at=r['t']+DAY, close='1') for r in bars],
                  'turnover_hour': [dict(t=r['t'], known_at=r['known_at'], value='3') for r in bars],
                  'turnover_day': [dict(t=r['t'], known_at=r['t']+DAY, value='3') for r in bars]}}


@pytest.mark.parametrize('cutoff,stage,cooling', [(HOUR-1,None,None), (HOUR,'initial',None),
    (3*DAY-1,'initial',None), (3*DAY,'middle',None), (15*DAY,'stabilizing',True), (30*DAY,'ordinary',False)])
def test_dv5_listing_closed_prefix_and_boundaries(cutoff, stage, cooling):
    view = rules.data_view(dv5_data(), cutoff, family='listing')
    rows = view.get('X', {}).get('listing_regime', ())
    assert (rows[-1]['stage'] if rows else None) == stage
    assert (rows[-1]['cooling'] if rows else None) == cooling
    assert all(set(r) == {'known_at','day_start','stage','reason_code','cooling'} for r in rows)
    if cutoff < 15*DAY:
        shorter = rules.data_view(dv5_data(False), cutoff, family='listing')
        assert {s: {k: list(v) for k,v in ds.items()} for s,ds in view.items()} == {s: {k: list(v) for k,v in ds.items()} for s,ds in shorter.items()}


def test_dv5_three_entry_mask_keeps_targets_and_never_restores_listing_history(cost):
    class Probe(rules.R8Hypothesis):
        def score(self, params, train_window, validation_window, data, cost):
            self.inspect(data); return '1'
        def fit(self, fit_window, data, params):
            self.inspect(data); return 'fitted'
        def on_decision(self, time, data, model, params):
            self.inspect(data); return {s: {'weight':'0'} for s in data}
        def inspect(self, data):
            assert list(data) == ['X']
            for name in ('kline_hour','kline_day','turnover_hour','turnover_day'):
                assert [r['t'] for r in data['X'][name]] == [30*DAY]
            assert data['X']['listing_regime'][-1]['stage'] == 'ordinary'
    result = rules.fit_fold(Probe, 1, {'start':0,'end':400*DAY}, dv5_data(), strategy(['1']), cost, family='ordinary')
    assert result['artifact']['model'] == 'fitted'
    assert rules.decide(Probe(1), 400*DAY, dv5_data(), result['artifact'], ['X'], family='ordinary') == {'X': {'weight':'0'}}
    view = rules.data_view(dv5_data(), 2*HOUR, family='ordinary')
    assert list(view) == ['X'] and 'kline_hour' not in view['X']
    assert len(dv5_data()['X']['kline_hour']) == 5


@pytest.mark.skip(reason='待 DV2／DV6 真實實作：DV2 materialize.py 的真實物化、listing_regimes.jsonl、custom/listing_regime、hypothesis_binding.json 及 turnover_decisions.jsonl，經 U5 score/fit/decision')
def test_dv5_pending_real_dv2_materialization_views():
    pass


@pytest.mark.skip(reason='待 DV2／DV6 真實實作：DV2 真實物化及 DV5 真實 run.json 交給 DV6 series.py recompute，核對 recompute_passed=true 與 differences=[]')
def test_dv5_pending_real_dv6_recompute():
    pass


def dv5_turnover(value='10000000', hourly='9000000', triggered=True, sufficient=True):
    return dict(schema_version='r8_turnover_decision_v1',symbol='X',decision_utc_day=20*DAY,
        known_at=20*DAY,policy_sha256='a'*64,history_sufficient=sufficient,
        inputs=[dict(day_start=i*DAY,exchange_reported=value,effective_reported=value,
            sum_hourly_reported=hourly if triggered else None,daily_status='VALID',
            hourly_status='VALID' if triggered else 'NOT_EVALUATED',source_refs=[]) for i in range(8,20)],
        m_d=value,m_e=value,m_h=hourly if triggered else None,tier_d='GE_10M',tier_e='GE_10M',
        tier_h='GE_1M' if triggered else None,triggered=triggered,
        selected_source='hourly_sum' if triggered else 'effective_daily',selected_median=hourly if triggered else value,
        selected_tier=('GE_1M' if triggered else 'GE_10M') if sufficient else 'NO_OPEN',status='READY',reason_codes=[])


@pytest.mark.parametrize('sufficient', [True,False])
def test_dv5_turnover_independent_selection_and_history(cost, sufficient):
    row = dv5_turnover(sufficient=sufficient)
    first = 0 if sufficient else 15*DAY
    assert rules.turnover_liquidity(row, 20*DAY+HOUR, first, cost) == ((None if sufficient else 'insufficient_history'), Decimal('20'))
    row['selected_tier'] = 'GE_100M'
    with pytest.raises(ValueError, match='TURNOVER'):
        rules.turnover_liquidity(row, 20*DAY, first, cost)


@pytest.mark.parametrize('amount,trigger', [('9500000',True),('10500000',True),('10500000.0001',False)])
def test_dv5_turnover_trigger_inclusive_and_same_tier(cost, amount, trigger):
    row=dv5_turnover(amount,amount,trigger)
    tier='GE_1M' if amount=='9500000' else 'GE_10M'
    row.update(tier_d=tier,tier_e=tier,tier_h=tier if trigger else None,
               selected_source='effective_daily',selected_median=amount,selected_tier=tier)
    assert rules.turnover_liquidity(row,20*DAY,0,cost) == (None,Decimal('20' if tier=='GE_1M' else '10'))


@pytest.mark.parametrize('mutation', ['blocked','future','duplicate','wrong_median','missing_hours','bool_time','unknown_key'])
def test_dv5_turnover_rejects_untrusted_rows(cost, mutation):
    row=dv5_turnover()
    if mutation=='blocked': row.update(status='BLOCKED',selected_source=None,selected_median=None,selected_tier=None,reason_codes=['TURNOVER_INPUT_INCOMPLETE'])
    if mutation=='future': row['known_at']+=DAY
    if mutation=='duplicate': row['inputs'][1]=row['inputs'][0]
    if mutation=='wrong_median': row['m_h']='1'
    if mutation=='missing_hours': row['inputs'][0]['hourly_status']='NOT_EVALUATED'
    if mutation=='bool_time': row['known_at']=True
    if mutation=='unknown_key': row['tail_count']=1
    with pytest.raises(ValueError, match='TURNOVER'):
        rules.turnover_liquidity(row,20*DAY,0,cost)


def dv5_materialization(path, manifest, family='ordinary', v2=False, wrong_type=None):
    """Hand-authored §8.4 files; real DV2 integration remains explicitly skipped."""
    from program_code.research.r8_engine import lean_runner as runner
    def put(name, raw, rows=1, first=None, last=None):
        target=path/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
        manifest['files'][name]=dict(sha256=runner.sha256(raw),rows=rows,first=first,last=last,
            source_file='manifest.json',source_sha256=manifest['u1_manifest_sha256'])
    def wire(obj): return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()+b'\n'
    policy=dict(schema_version='r8_data_verification_policy_v1',standard_sha256='b'*64,
        approval_event='RH-20261022-04',p3b_manifest_sha256=manifest['u1_manifest_sha256'],
        listing=dict(x_pct='50',y_pct='20',z_pct='20',cooling_days=7,quantity='hourly_base_volume_daily_mean',
                     variation='mean_relative_difference',stage_end_ranges=[[1,3],[7,15],[15,30]]),
        sampling=dict(seed=20261022,base_per_stratum=300,max_per_stratum=900,max_expansions=1,confidence='0.95',upper_limit='0.025'),
        turnover=dict(window_days=12,thresholds=['1000000','10000000','100000000'],trigger_pct='5',general='exchange_reported',suspect='sum_hourly_reported'),l4_price_threshold_pct='1')
    if v2:
        policy.update(schema_version='r8_data_verification_policy_v2', approval_event='RH-20261022-05',
                      volume_semantics_policy='v2-terminal-suffix-20261022')
    if wrong_type == 'bool': policy['listing']['stage_end_ranges'][0][0]=True
    if wrong_type == 'float': policy['listing']['cooling_days']=7.0
    put('verification/policy.json',wire(policy)); digest=runner.sha256(wire(policy))
    verification=dict(schema_version='r8_data_verification_v2' if v2 else 'r8_data_verification_v1',
        status='READY',policy_sha256=digest,p3b_manifest_sha256=manifest['u1_manifest_sha256'],
        sample_plan_sha256=None,previous_corrections_sha256=None,review_refs=[],tool_commit='a'*40,
        readable=manifest['window'],counts=dict(input_rows=0,checked_days=0,flagged_days=0,corrected_fields=0,unresolved_rows=0),
        files={},reason_codes=[])
    if v2:
        verification.update(standard_sha256=policy['standard_sha256'],volume_semantics_policy=policy['volume_semantics_policy'])
        put('verification/volume_semantics.jsonl',b'',0)
        verification['files']['volume_semantics.jsonl']=dict(sha256=runner.sha256(b''),rows=0)
    put('verification/verification.json',wire(verification))
    binding=dict(schema_version='r8_verification_hypothesis_binding_v1',hypothesis_id=manifest['hypothesis_id'],
                 policy_sha256=digest,family=family,registration_sha256='c'*64)
    put('verification/hypothesis_binding.json',wire(binding))
    listing=dict(schema_version='r8_listing_regime_v1',symbol='X',day_start=0,known_at=HOUR,
        observed_listing_at=0,launch_time=0,listing_time_mismatch=False,origin_refs=[],stage='initial',
        reason_code='OBSERVED_LISTING',cooling=None,quantity_inputs=[],policy_sha256=digest)
    put('verification/listing_regimes.jsonl',wire(listing),first=HOUR,last=HOUR)
    put('custom/listing_regime/x.csv',f'known_at,day_start,stage,reason_code,cooling,policy_sha256\n{HOUR},0,initial,OBSERVED_LISTING,null,{digest}\n'.encode(),first=HOUR,last=HOUR)
    row=dv5_turnover(); row['policy_sha256']=digest
    put('verification/turnover_decisions.jsonl',wire(row),first=20*DAY,last=20*DAY)
    header='timestamp,open,high,low,close,volume,turnover\n'
    daily=header+''.join(f'{i*DAY},1,1,1,1,24,10000000\n' for i in range(8,20))
    hourly=header+''.join(f'{i*HOUR},1,1,1,1,1,375000\n' for i in range(8*24,20*24))
    for prefix in ('source','verification/original'):
        put(prefix+'/kline_X_D.csv',daily.encode(),12,8*DAY,19*DAY)
    put('source/kline_X_60.csv',hourly.encode(),288,8*DAY,20*DAY-HOUR)
    for resolution, count, step, start, amount in [('day',12,DAY,8*DAY,'10000000'),('hour',288,HOUR,8*DAY,'375000')]:
        raw=''.join(f'{start+(i+1)*step},{start+i*step},{amount}\n' for i in range(count)).encode()
        put('custom/turnover_'+resolution+'/x.csv',raw,count,start,start+(count-1)*step)
    raw=canonical(manifest); (path/'materialization.json').write_bytes(raw)
    return runner.sha256(raw),binding


@pytest.mark.parametrize('mutation', ['valid','missing_binding','wrong_hypothesis','wrong_policy','wrong_registration',
    'missing_table','forged_tier','forged_input','projection','unknown_key','v2_leak'])
def test_dv5_runner_validates_binding_sources_and_projection(inputs, mutation):
    from program_code.research.r8_engine import lean_runner as runner
    path,manifest,config,query=inputs
    digest,binding=dv5_materialization(path,manifest)
    target=None
    if mutation=='missing_binding':
        del manifest['files']['verification/hypothesis_binding.json']; (path/'verification/hypothesis_binding.json').unlink()
    if mutation in ('wrong_hypothesis','wrong_policy','wrong_registration'):
        binding[{'wrong_hypothesis':'hypothesis_id','wrong_policy':'policy_sha256','wrong_registration':'registration_sha256'}[mutation]]='d'*64
        target='verification/hypothesis_binding.json'; raw=json.dumps(binding,sort_keys=True,separators=(',',':')).encode()+b'\n'
    if mutation=='missing_table':
        del manifest['files']['verification/turnover_decisions.jsonl']; (path/'verification/turnover_decisions.jsonl').unlink()
    if mutation in ('forged_tier','forged_input','unknown_key','v2_leak'):
        target='verification/turnover_decisions.jsonl'; row=json.loads((path/target).read_bytes())
        if mutation=='forged_tier': row['selected_tier']='GE_100M'
        if mutation=='forged_input': row['inputs'][0]['exchange_reported']='999'
        if mutation in ('unknown_key','v2_leak'): row['tail_count']=1
        raw=json.dumps(row,sort_keys=True,separators=(',',':')).encode()+b'\n'
    if mutation=='projection':
        target='custom/listing_regime/x.csv'; raw=(path/target).read_bytes().replace(b'initial',b'ordinary')
    if target:
        (path/target).write_bytes(raw); manifest['files'][target]['sha256']=runner.sha256(raw)
    raw=canonical(manifest); (path/'materialization.json').write_bytes(raw)
    config['materialization_sha256']=runner.sha256(raw)
    query['record']['manifest_sha256']=config['materialization_sha256']
    query['record']['data_files']={k:v['sha256'] for k,v in manifest['files'].items()}
    query['record']['preregistration_sha256']='c'*64
    if mutation=='valid':
        assert runner.read_materialization(path,config['materialization_sha256'])==manifest
        runner.validate_config(config,manifest,lambda _:query)
        assert runner.verification_inputs(path,manifest,config,lambda _:query)['family']=='ordinary'
    else:
        with pytest.raises(ValueError):
            checked=runner.read_materialization(path,config['materialization_sha256'])
            runner.verification_inputs(path,checked,config,lambda _:query)


@pytest.mark.parametrize('family', ['ordinary','listing'])
def test_dv5_framework_loads_header_masks_and_uses_private_decisions(fake_lean, family):
    source = """from program_code.research.r8_engine.lean_algo.rules import R8Hypothesis
class FixedSchedule(R8Hypothesis):
    def on_decision(self,time,data,model,params):
        assert set(data['X']) <= {'kline_hour','kline_day','turnover_hour','turnover_day','funding','open_interest','listing_regime'}
        assert data['X']['listing_regime'][-1]['stage']=='stabilizing'
        assert 'policy_sha256' not in data['X']['listing_regime'][-1]
        assert ('kline_hour' in data['X']) == LISTING
        return {'X':{'weight':'0.001'}}
""".replace('LISTING',str(family=='listing'))
    row=dv5_turnover(); t=20*DAY
    listing=dv5_listing_csv()
    driver=fake_lean.Driver({'X':{t:['100','101','99','100','1'],t+HOUR:['100','101','99','100','1']}}, hypothesis_source=source,
                           verification=dict(family=family,listing=listing,turnover=row))
    driver.step(t+HOUR)
    assert driver.algorithm._failure is None
    driver.step(t+2*HOUR)
    assert driver.algorithm._failure is None
    fills=driver.records('fills')
    assert fills and fills[0]['slippage_bps']=='20'
    assert fills[0]['price']=='100.2'


@pytest.mark.parametrize('path', ['/r8/framework-inputs/turnover_decisions.jsonl',
    '/r8/custom/listing_regime/x.csv','/r8/verification/volume_semantics.jsonl'])
def test_dv5_hypothesis_file_bypass_rejected(path):
    from program_code.research.r8_engine import lean_runner as runner
    with pytest.raises(ValueError):
        runner.check_algorithm(f'def probe():\n    return open({path!r}).read()\n')


def test_dv5_legacy_artifact_read_only_regression_not_new_trial(inputs):
    from program_code.research.r8_engine import lean_runner as runner
    path,manifest,config,query=inputs
    with pytest.raises(ValueError,match='VERIFICATION_MISSING'):
        runner.verification_inputs(path,manifest,config,lambda _:query)
    config['mode']='verification'
    assert runner.verification_inputs(path,manifest,config,lambda _:query) is None


def test_dv5_missing_days_zero_and_missing_hour_no_fallback(cost):
    row=dv5_turnover('0','0',False)
    row.update(tier_d='NO_OPEN',tier_e='NO_OPEN',selected_tier='NO_OPEN')
    for item in row['inputs']:
        item.update(exchange_reported=None,effective_reported=None,daily_status='MISSING')
    assert rules.turnover_liquidity(row,20*DAY,0,cost)==('untradeable',Decimal('20'))
    row=dv5_turnover()
    row['inputs'][0].update(sum_hourly_reported=None,hourly_status='MISSING')
    row['reason_codes']=['TURNOVER_INPUT_INCOMPLETE']
    assert rules.turnover_liquidity(row,20*DAY,0,cost)==(None,Decimal('20'))


@pytest.mark.parametrize('mutation',['stage_regression','future_quantity','duplicate_key','no_header','unknown_binding','bad_meta','empty_table'])
def test_dv5_runner_strict_schema_and_causal_listing(inputs,mutation):
    from program_code.research.r8_engine import lean_runner as runner
    path,manifest,config,query=inputs; dv5_materialization(path,manifest)
    query['record']['preregistration_sha256']='c'*64
    runner.verification_inputs(path,manifest,config,lambda _:query)
    target='verification/listing_regimes.jsonl'; row=json.loads((path/target).read_bytes())
    if mutation=='stage_regression':
        row.update(stage='ordinary')
        raw=json.dumps(row,sort_keys=True,separators=(',',':')).encode()+b'\n'
        (path/'custom/listing_regime/x.csv').write_bytes((path/'custom/listing_regime/x.csv').read_bytes().replace(b'initial',b'ordinary'))
        manifest['files']['custom/listing_regime/x.csv']['sha256']=runner.sha256((path/'custom/listing_regime/x.csv').read_bytes())
    if mutation=='future_quantity':
        row['quantity_inputs']=[dict(day_start=0,volume_sum='24',hour_count=24,status='FULL',source_refs=[])]
        raw=json.dumps(row,sort_keys=True,separators=(',',':')).encode()+b'\n'
    if mutation=='duplicate_key': raw=(path/target).read_bytes().replace(b'"stage":"initial"',b'"stage":"initial","stage":"initial"')
    if mutation=='no_header': target='custom/listing_regime/x.csv'; raw=(path/target).read_bytes().split(b'\n',1)[1]
    if mutation=='unknown_binding':
        target='verification/hypothesis_binding.json'; obj=json.loads((path/target).read_bytes());obj['tail_count']=2
        raw=json.dumps(obj,sort_keys=True,separators=(',',':')).encode()+b'\n'
    if mutation=='bad_meta': manifest['files'][target]['rows']=999; raw=(path/target).read_bytes()
    if mutation=='empty_table': target='verification/turnover_decisions.jsonl'; raw=b''; manifest['files'][target].update(rows=0,first=None,last=None)
    (path/target).write_bytes(raw);manifest['files'][target]['sha256']=runner.sha256(raw)
    with pytest.raises(ValueError): runner.verification_inputs(path,manifest,config,lambda _:query)


@pytest.mark.parametrize('family',['ordinary','listing'])
def test_dv5_framework_score_and_fit_share_mask(fake_lean,family):
    t=20*DAY
    source="""from program_code.research.r8_engine.lean_algo.rules import R8Hypothesis
class FixedSchedule(R8Hypothesis):
    def inspect(self,data):
        assert ('kline_hour' in data['X']) == LISTING
        assert data['X']['listing_regime'][-1]['stage']=='stabilizing'
    def score(self,params,train_window,validation_window,data,cost):
        self.inspect(data); return '1'
    def fit(self,fit_window,data,params):
        self.inspect(data); return 'MASK_CHECKED'
    def on_decision(self,time,data,model,params):
        return {'X':{'weight':'0'}}
""".replace('LISTING',str(family=='listing'))
    listing=dv5_listing_csv()
    strat=strategy(['1']);strat.update(internal_validation_days=1,internal_gap_days=1)
    folds=[dict(fit_window=dict(start=16*DAY,end=t+2*HOUR),score_window=dict(start=t+3*HOUR,end=t+5*HOUR))]
    driver=fake_lean.Driver({'X':{t:['100','101','99','100','1'],t+HOUR:['100','101','99','100','1']}},
        folds=folds,strategy_config=strat,hypothesis_source=source,
        verification=dict(family=family,listing=listing,turnover=dv5_turnover()))
    driver.step(t+HOUR);driver.step(t+2*HOUR)
    assert driver.algorithm._failure is None
    assert driver.records('fits')[0]['model_sha256'] is not None
    assert b'MASK_CHECKED' in fake_lean.mounted('/r8/output/model.json').read_bytes()


@pytest.mark.parametrize('mutation',['valid','missing_evidence','schema_downgrade','wrong_policy'])
def test_dv5_v2_evidence_identity_remains_private(inputs,mutation):
    from program_code.research.r8_engine import lean_runner as runner
    path,manifest,config,query=inputs;dv5_materialization(path,manifest,v2=True)
    query['record']['preregistration_sha256']='c'*64
    target='verification/verification.json';obj=json.loads((path/target).read_bytes())
    if mutation=='missing_evidence':
        del manifest['files']['verification/volume_semantics.jsonl'];(path/'verification/volume_semantics.jsonl').unlink()
    if mutation=='schema_downgrade': obj['schema_version']='r8_data_verification_v1'
    if mutation=='wrong_policy': obj['volume_semantics_policy']='v1-strict'
    raw=json.dumps(obj,sort_keys=True,separators=(',',':')).encode()+b'\n'
    (path/target).write_bytes(raw);manifest['files'][target]['sha256']=runner.sha256(raw)
    if mutation=='valid':
        assert runner.verification_inputs(path,manifest,config,lambda _:query)['family']=='ordinary'
    else:
        with pytest.raises(ValueError): runner.verification_inputs(path,manifest,config,lambda _:query)


def test_dv5_unknown_stage_keeps_complete_target_symbols():
    data={'X':{'kline_hour':[dict(t=0,known_at=HOUR,close='1')]}}
    class Empty(rules.R8Hypothesis):
        def on_decision(self,t,data,model,params):
            assert dict(data['X']) == {}
            return {symbol:{'weight':'0'} for symbol in data}
    assert rules.decide(Empty(1),HOUR,data,dict(model=None,params={}),['X'],family='ordinary') == {'X':{'weight':'0'}}


@pytest.mark.parametrize('resolution',['day','hour'])
def test_dv5_runner_binds_custom_amounts_to_independent_source(inputs,resolution):
    from program_code.research.r8_engine import lean_runner as runner
    path,manifest,config,query=inputs;dv5_materialization(path,manifest)
    query['record']['preregistration_sha256']='c'*64
    runner.verification_inputs(path,manifest,config,lambda _:query)
    target='custom/turnover_'+resolution+'/x.csv'
    raw=(path/target).read_bytes().replace(b',10000000\n',b',1\n').replace(b',375000\n',b',1\n')
    (path/target).write_bytes(raw);manifest['files'][target]['sha256']=runner.sha256(raw)
    with pytest.raises(ValueError,match='TURNOVER'):
        runner.verification_inputs(path,manifest,config,lambda _:query)


def test_dv5_unknown_original_with_valid_effective_day(cost,inputs):
    from program_code.research.r8_engine import lean_runner as runner
    path,manifest,config,query=inputs;dv5_materialization(path,manifest)
    query['record']['preregistration_sha256']='c'*64
    target='verification/turnover_decisions.jsonl';row=json.loads((path/target).read_bytes())
    for item in row['inputs']: item['exchange_reported']=None
    row.update(m_d='0',tier_d='NO_OPEN')
    assert rules.turnover_liquidity(row,20*DAY,0,cost)==(None,Decimal('20'))
    raw=json.dumps(row,sort_keys=True,separators=(',',':')).encode()+b'\n'
    (path/target).write_bytes(raw);manifest['files'][target]['sha256']=runner.sha256(raw)
    target='verification/original/kline_X_D.csv'
    raw=(path/target).read_bytes().replace(b',10000000\n',b',NaN\n')
    (path/target).write_bytes(raw);manifest['files'][target]['sha256']=runner.sha256(raw)
    assert runner.verification_inputs(path,manifest,config,lambda _:query)['family']=='ordinary'


def test_dv5_untriggered_hourly_comparison_does_not_change_selection(cost):
    row=dv5_turnover('20000000','9000000',True)
    row.update(triggered=False,selected_source='effective_daily',selected_median='20000000',selected_tier='GE_10M')
    assert rules.turnover_liquidity(row,20*DAY,0,cost)==(None,Decimal('10'))


def test_dv5_missing_current_listing_day_cannot_reuse_old_cooling():
    data=dv5_data()
    data['X']['listing_regime']=[r for r in data['X']['listing_regime'] if r['day_start']<15*DAY]
    with pytest.raises(ValueError,match='LISTING'):
        rules.data_view(data,20*DAY,family='listing')


def dv5_listing_csv():
    return ''.join(f"{r['known_at']},{r['day_start']},{r['stage']},{r['reason_code']},{str(r['cooling']).lower() if r['cooling'] is not None else 'null'},{r['policy_sha256']}\n"
                   for r in dv5_data()['X']['listing_regime'])


@pytest.mark.parametrize('kind',['bool','float'])
def test_dv5_policy_rejects_numeric_type_aliases(inputs,kind):
    from program_code.research.r8_engine import lean_runner as runner
    path,manifest,config,query=inputs;dv5_materialization(path,manifest,wrong_type=kind)
    query['record']['preregistration_sha256']='c'*64
    with pytest.raises(ValueError,match='POLICY'):
        runner.verification_inputs(path,manifest,config,lambda _:query)
