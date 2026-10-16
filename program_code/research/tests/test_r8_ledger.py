"""研究帳的離線契約測試；樣本均為合成資料。"""
import ast
import copy
import json
from pathlib import Path
import socket
import sys

import pytest

from program_code.research.r8_ledger import ledger as mod


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("測試禁止網路")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


@pytest.fixture
def registration():
    members = ["h1", "h2", "h3", "h4"]
    return {
        "hypothesis_id": "h1", "family": "carry", "economic_mechanism": "合成機制",
        "decision_period": {"unit": "hour", "value": 1}, "expected_holding_seconds": 3600,
        "expected_turnover": 1.0, "pessimistic_cost_ratio": 0.5,
        "data_range": {"start": mod.DEFAULT_BOUNDARIES[0], "end": mod.DEFAULT_BOUNDARIES[-1]},
        "time_splits": mod.split_intervals(), "primary_metric": "after_cost_sharpe",
        "candidate_thresholds": {"sharpe": 1.0},
        "multiple_testing": {"method": "BH", "fdr": 0.05, "members": members, "members_sha256": mod.sha256(members)},
        "max_lookback_seconds": 3600, "label_period_seconds": 3600, "max_holding_seconds": 3600,
        "selection": {"type": "time_series", "rule": "期初已知合約", "known_at_period_start": mod.DEFAULT_BOUNDARIES[0]},
        "previous_no_go": None, "split_rationale": "採預設切分", "power_estimate": "日線樣本少，須另估統計力",
    }


@pytest.fixture
def trial():
    config = {"strategy_parameters": {"window": 2}, "cost_model_parameters": {"fee": 0.001}}
    return {
        "trial_id": "t1", "hypothesis_id": "h1", "generation": 1, "parent_trial_id": None,
        "variant_parameters": {}, "data_window": {"start": "2022-01-01T00:00:00Z", "end": "2025-07-01T00:00:00Z"},
        "manifest_sha256": "1"*64, "data_files": {"data.csv.gz": "2"*64}, "code_commit": "3"*40,
        "cost_model": {"id": "cost", "version": "v1"}, "fill_model": {"id": "fill", "version": "v1"},
        "configuration": config, "configuration_sha256": mod.sha256(config),
        "engine": {"id": "synthetic", "version": "v1"}, "dependencies": {},
        "time_semantics": {"known_at": "bar close", "fill_at": "next bar", "simulated_latency_ms": 300},
        "random_seed": None, "status": "completed", "result_summary": {"net": 1},
        "started_at": "2026-10-16T01:00:00Z", "ended_at": "2026-10-16T02:00:00Z",
        "sharpe": 0.1, "sharpe_frequency": {"unit": "hour", "seconds": 3600, "annualized": False},
        "return_count": 100, "skewness": 0, "excess_kurtosis": 0, "returns_sha256": "4"*64, "p_value": 0.01,
    }


@pytest.fixture
def book(tmp_path, registration):
    b = mod.ResearchLedger(tmp_path)
    b.preregister(registration, "2026-10-16T00:00:00Z")
    return b


def test_canonical_identity_is_order_independent(registration, tmp_path):
    a = mod.ResearchLedger(tmp_path / "a")
    b = mod.ResearchLedger(tmp_path / "b")
    assert a.preregister(registration, "2026-10-16T00:00:00Z") == b.preregister(dict(reversed(list(registration.items()))), "2026-10-16T00:00:00Z")


@pytest.mark.parametrize("field", [
    "hypothesis_id", "family", "economic_mechanism", "decision_period", "expected_holding_seconds", "expected_turnover",
    "pessimistic_cost_ratio", "data_range", "time_splits", "primary_metric", "candidate_thresholds", "multiple_testing",
    "max_lookback_seconds", "label_period_seconds", "max_holding_seconds", "selection", "previous_no_go", "split_rationale", "power_estimate",
])
def test_preregistration_required_fields(tmp_path, registration, field):
    del registration[field]
    with pytest.raises(mod.LedgerError):
        mod.ResearchLedger(tmp_path).preregister(registration, "2026-10-16T00:00:00Z")


@pytest.mark.parametrize("unit", ["second", "minute"])
def test_fast_period_needs_non_speed_reason(tmp_path, registration, unit):
    registration["decision_period"]["unit"] = unit
    b = mod.ResearchLedger(tmp_path)
    with pytest.raises(mod.LedgerError):
        b.preregister(registration, "2026-10-16T00:00:00Z")
    registration["non_speed_edge"] = "優勢來自持續的風險補償"
    b.preregister(registration, "2026-10-16T00:00:00Z")


@pytest.mark.parametrize("kind", ["cross_sectional", "filtered"])
def test_selection_requires_point_in_time_delisting_evidence(tmp_path, registration, kind):
    registration["selection"] = {"type": kind, "rule": "合成選取"}
    b = mod.ResearchLedger(tmp_path)
    with pytest.raises(mod.LedgerError):
        b.preregister(registration, "2026-10-16T00:00:00Z")
    registration["selection"]["point_in_time_universe_source"] = "合成含下架清單的雜湊來源"
    b.preregister(registration, "2026-10-16T00:00:00Z")


@pytest.mark.parametrize("missing", ["decision_ref", "differences"])
def test_no_go_reregistration_requires_reference_and_difference(tmp_path, registration, missing):
    registration["previous_no_go"] = {"decision_ref": "NOGO-1", "differences": "不同機制"}
    del registration["previous_no_go"][missing]
    with pytest.raises(mod.LedgerError):
        mod.ResearchLedger(tmp_path).preregister(registration, "2026-10-16T00:00:00Z")


@pytest.mark.parametrize("field", [
    "trial_id", "hypothesis_id", "generation", "parent_trial_id", "variant_parameters", "data_window", "manifest_sha256", "data_files",
    "code_commit", "cost_model", "fill_model", "configuration", "configuration_sha256", "engine", "dependencies", "time_semantics", "random_seed",
    "status", "result_summary", "started_at", "ended_at", "sharpe", "sharpe_frequency", "return_count", "skewness", "excess_kurtosis", "returns_sha256", "p_value",
])
def test_trial_required_identity_and_dsr_fields(book, trial, field):
    del trial[field]
    with pytest.raises(mod.LedgerError):
        book.record_trial(trial)


@pytest.mark.parametrize("started", ["2026-10-15T23:59:59Z", "2026-10-16T00:00:00Z"])
def test_trial_must_be_after_registration(book, trial, started):
    trial["started_at"] = started
    with pytest.raises(mod.LedgerError):
        book.record_trial(trial)


def test_count_includes_variants_failure_and_abort(book, trial):
    for i, status in enumerate(("completed", "failed", "aborted")):
        trial.update(trial_id="t"+str(i), status=status, variant_parameters={"window": i+1})
        book.record_trial(trial)
    assert book.family_trial_count("carry") == 3
    inputs = book.dsr_inputs("carry")
    assert inputs["trial_count"] == 3
    assert [t["status"] for t in inputs["trials"]] == ["completed", "failed", "aborted"]
    assert inputs["trials"][0]["return_count"] == 100
    assert inputs["trials"][0]["excess_kurtosis"] == 0


@pytest.mark.parametrize("name", mod.LEDGERS)
@pytest.mark.parametrize("mutation", ["rewrite", "delete", "insert"])
def test_pinned_heads_detect_tampering_in_all_three_books(book, trial, registration, name, mutation):
    registration["hypothesis_id"] = "h2"
    book.preregister(registration, "2026-10-16T00:00:00Z")
    book.record_trial(trial)
    trial["trial_id"] = "t2"
    book.record_trial(trial)
    book.seal_holdout("h1", "holdout-1")
    book.seal_holdout("h1", "holdout-2")
    heads = book.export_heads()
    path = book.out / (name + ".jsonl")
    rows = path.read_bytes().splitlines(keepends=True)
    if mutation == "rewrite":
        row = json.loads(rows[0]); row["payload"]["tampered"] = True
        rows[0] = mod.canonical(row) + b"\n"
    elif mutation == "delete":
        rows.pop(0)
    else:
        rows.insert(1, rows[0])
    path.write_bytes(b"".join(rows))
    with pytest.raises(mod.LedgerError):
        book.verify_heads(heads)


def test_pinned_prefix_remains_valid_after_append_and_truncation_is_detected(book, trial):
    book.record_trial(trial)
    heads = book.export_heads()
    trial["trial_id"] = "t2"
    book.record_trial(trial)
    current = book.verify_heads(heads)
    assert current == book.export_heads()
    assert current["trials"] != heads["trials"]
    path = book.out / "trials.jsonl"
    rows = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(rows[0])
    with pytest.raises(mod.LedgerError):
        book.verify_heads(current)


def test_seal_open_and_repeat_denial_records_no_authorized_interval(book):
    book.seal_holdout("h1", "holdout-1")
    result = book.open_holdout("h1", "holdout-1", 1, "a"*64)
    assert result == {"start": "2026-01-08T00:00:00Z", "end": "2026-05-15T00:00:00Z"}
    with pytest.raises(mod.HoldoutDenied) as exc:
        book.open_holdout("h1", "holdout-1", 1, "a"*64)
    assert not hasattr(exc.value, "interval")
    row = json.loads((book.out / "holdouts.jsonl").read_text().splitlines()[-1])["payload"]
    assert row["action"] == "denied"
    assert "interval" not in row


def test_wrong_generation_and_unsealed_are_denied(book):
    with pytest.raises(mod.HoldoutDenied):
        book.open_holdout("h1", "holdout-1", 1, "a"*64)
    book.seal_holdout("h1", "holdout-1")
    with pytest.raises(mod.HoldoutDenied):
        book.open_holdout("h1", "holdout-1", 2, "a"*64)
    assert book.open_holdout("h1", "holdout-1", 1, "a"*64)


def test_another_hypothesis_cannot_reopen_same_data(book, registration):
    registration["hypothesis_id"] = "h2"
    book.preregister(registration, "2026-10-16T00:00:00Z")
    book.seal_holdout("h1", "holdout-1")
    book.open_holdout("h1", "holdout-1", 1, "a"*64)
    with pytest.raises(mod.HoldoutDenied):
        book.open_holdout("h2", "holdout-1", 1, "b"*64)


def test_default_splits_shift_later_start_and_respect_longer_periods():
    splits = mod.split_intervals(label_period_seconds=10*86400, max_holding_seconds=12*86400)
    assert splits[0]["end"] == "2025-07-01T00:00:00Z"
    assert splits[1]["start"] == "2025-07-13T00:00:00Z"
    assert splits[2]["start"] == "2026-01-13T00:00:00Z"
    assert splits[3]["start"] == "2026-05-27T00:00:00Z"


def test_preregister_adjusts_insufficient_gap(book, registration, tmp_path):
    registration["label_period_seconds"] = 14*86400
    b = mod.ResearchLedger(tmp_path / "new")
    b.preregister(registration, "2026-10-16T00:00:00Z")
    b.seal_holdout("h1", "holdout-1")
    assert b.open_holdout("h1", "holdout-1", 1, "a"*64)["start"] == "2026-01-15T00:00:00Z"


@pytest.mark.parametrize("mode", ["reverse", "overlap", "empty_after_embargo"])
def test_invalid_splits_are_rejected(tmp_path, registration, mode):
    if mode == "reverse":
        registration["time_splits"][0]["end"] = "2021-01-01T00:00:00Z"
    elif mode == "overlap":
        registration["time_splits"][1]["start"] = "2025-06-01T00:00:00Z"
    else:
        registration["max_holding_seconds"] = 365*86400
    with pytest.raises(mod.LedgerError):
        mod.ResearchLedger(tmp_path).preregister(registration, "2026-10-16T00:00:00Z")


def test_split_boundaries_out_of_order_rejected():
    with pytest.raises(mod.LedgerError):
        mod.split_intervals(tuple(reversed(mod.DEFAULT_BOUNDARIES)))


def test_bh_known_example_and_binding(book, registration):
    p = {"h1": .01, "h2": .04, "h3": .03, "h4": .2}
    digest = registration["multiple_testing"]["members_sha256"]
    result = book.benjamini_hochberg("h1", p, digest, .05)
    assert [result[x]["adjusted_p"] for x in p] == pytest.approx([.04, .05333333333333334, .05333333333333334, .2])
    assert [x for x in p if result[x]["rejected"]] == ["h1"]
    for args in ((p, "b"*64, .05), (p, digest, .1), ({"h1": .01}, digest, .05)):
        with pytest.raises(mod.LedgerError):
            book.benjamini_hochberg("h1", *args)


@pytest.mark.parametrize("value", [-.01, 1.01, float("nan"), float("inf"), True])
def test_bad_p_values_are_rejected(book, trial, value):
    trial["p_value"] = value
    with pytest.raises(mod.LedgerError):
        book.record_trial(trial)


def test_configuration_hash_and_annualized_sharpe_rejected(book, trial):
    trial["configuration_sha256"] = "b"*64
    with pytest.raises(mod.LedgerError):
        book.record_trial(trial)
    trial["configuration_sha256"] = mod.sha256(trial["configuration"])
    trial["sharpe_frequency"]["annualized"] = True
    with pytest.raises(mod.LedgerError):
        book.record_trial(trial)


def test_stdlib_only_ast():
    package = Path(mod.__file__).parent
    for path in package.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                assert all(x.name.split(".")[0] in sys.stdlib_module_names for x in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level:
                assert node.module.split(".")[0] in sys.stdlib_module_names


def test_holdout_generations_must_follow_time_order():
    with pytest.raises(mod.LedgerError):
        mod.split_intervals(generations=(2, 1))


def test_failed_trial_without_observed_statistics_is_rejected_explicitly(book, trial):
    trial["status"] = "failed"
    trial["sharpe"] = None
    with pytest.raises(mod.LedgerError, match="sharpe"):
        book.record_trial(trial)
