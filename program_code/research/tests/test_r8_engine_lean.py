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
            "neighborhood": {"numeric": {"n": list(range(len(scores)))}, "categorical": {}},
            "internal_validation_days": 182, "internal_gap_days": 8}


@pytest.mark.parametrize("scores,selected", [
    (["-1", "100", "-1", "-1"], None), (["100", "-1", "-1"], None),
    (["-1", "-2"], None), (["1", "1", "1"], 0), (["1", "2", "3"], 2)])
def test_grid_qualification_plateau_and_tie(scores, selected):
    s = strategy(scores)
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
        rules.select_grid_point([value], [{"n": 1}], {"numeric": {}, "categorical": {}})


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
    path, _, config, query = inputs
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
                                    {"numeric": {"n": [1, 2]}, "categorical": {"type": ["A", "B"]}})
    assert result["qualified"] == [False, False, True] and result["selected"] == 2
    with pytest.raises(ValueError):
        rules.select_grid_point(["1"] * 21, [{"n": i} for i in range(21)],
                                {"numeric": {"n": list(range(21))}, "categorical": {}})


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
        def __init__(self, bars, schedule=(), folds=(), strategy_config=None, end=None, funding=None, initial='100000', hypothesis_source=None):
            self.bars = bars
            self.algorithm = framework.R8Algorithm()
            self.t0 = base_t
            names = sorted(bars)
            end = end if end is not None else base_t + 6 * HOUR
            config = {'initial_cash': initial, 'leverage': '10', 'cost': cost,
                      'score_windows': [f['score_window'] for f in folds] if folds else [{'start': base_t, 'end': end}],
                      'folds': list(folds), 'model_artifact': None, 'random_seed': 1,
                      'algorithm': {'path': 'hypothesis.py', 'class': 'FixedSchedule'},
                      'strategy': strategy_config or {'schedule': list(schedule)},
                      'decision_resolution': 'hour', 'gross_exposure_cap': '1'}
            info = {'symbols': names, 'strategy_symbols': names, 'first_bar': {s: 0 for s in names},
                    'delistings': {}, 'warmup': {'start': base_t - HOUR, 'end': base_t},
                    'window': {'start': base_t, 'end': end}, 'validation_example': True,
                    'properties': {s: {'qty_step': '0.001', 'min_qty': '0.001'} for s in names},
                    'min_notional': {s: '0' for s in names}, 'funding_interval_ms': {s: 8 * HOUR for s in names}}
            mounted('/r8/output').mkdir(parents=True)
            for file, obj in [('algorithm_config.json', config), ('framework.json', info)]:
                mounted('/r8/' + file).write_bytes(canonical(obj))
            path = mounted('/r8/src/hypothesis.py')
            path.parent.mkdir(parents=True)
            source = (ROOT / 'program_code/research/r8_engine/lean_algo/examples/fixed_schedule.py').read_text()
            # 構造相鄰折，一折合格、一折不交易；其餘沿用正式範例的介面。
            source = source.replace('return params["score"]',
                                    'return "-1" if validation_window["end"] >= params.get("no_trade_at", 10**20) else params["score"]')
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


@pytest.mark.parametrize('fit_at_boundary', [False, True])
def test_fix2_framework_no_trade_boundary_cancels_before_native_fill(fake_lean, fit_at_boundary):
    t = fake_lean.t0
    bar = ['100'] * 4 + ['1']
    fit_end = t + (2 if fit_at_boundary else 1) * HOUR
    config = strategy(['1'])
    config['grid'][0].update(no_trade_at=fit_end, schedule=[
        {'t': t + HOUR, 'targets': {'X': {'quantity': '1'}, 'Y': {'quantity': '2'}}}])
    folds = [{'fit_window': {'start': -400 * DAY, 'end': t - HOUR},
              'score_window': {'start': t, 'end': t + 2 * HOUR}},
             {'fit_window': {'start': -400 * DAY, 'end': fit_end},
              'score_window': {'start': t + 2 * HOUR, 'end': t + 6 * HOUR}}]
    driver = fake_lean.Driver({'X': {t + i * HOUR: bar for i in (-1, 0, 1, 2)},
                               'Y': {t + i * HOUR: bar for i in (-1, 0, 2)}},
                              folds=folds, strategy_config=config,
                              funding={s: [[t, t, '0']] for s in ('X', 'Y')})
    for step in (0, 1, 2, 3):
        driver.step(t + step * HOUR)
    driver.finish()
    assert driver.algorithm.stops == []
    assert driver.records('fills') == []
    assert [(r['symbol'], r['status'], r['cancel_reason'], r['cancel_t'])
            for r in driver.records('orders')] == [
                ('X', 'cancelled', 'no_trade', t + 2 * HOUR),
                ('Y', 'cancelled', 'no_trade', t + 2 * HOUR)]
    assert driver.records('cash_residual') == []
