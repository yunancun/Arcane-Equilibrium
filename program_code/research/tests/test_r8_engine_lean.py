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
