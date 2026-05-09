from __future__ import annotations

import json

import pytest

from program_code.ml_training.promotion_evidence import (
    build_strategy_promotion_evidence,
    push_promotion_evidence_from_js_results,
)


def _js_results():
    return {
        ("ma_crossover", "BTCUSDT"): {
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "raw_bps_series": [15.0, 20.0, 17.0, 19.0, 22.0, 18.0] * 32,
        },
        ("ma_crossover", "ETHUSDT"): {
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "raw_bps_series": [12.0, 14.0, 16.0, 13.0, 15.0, 17.0] * 32,
        },
        ("grid_trading", "SOLUSDT"): {
            "strategy_name": "grid_trading",
            "symbol": "SOLUSDT",
            "raw_bps_series": [5.0, -2.0, 7.0, 4.0],
        },
    }


class _FakeGate:
    def __init__(self):
        self.registered: list[str] = []
        self.selection_calls: list[dict] = []
        self.tail_calls: list[dict] = []

    def register_strategy(self, strategy_name: str, *args, **kwargs):
        self.registered.append(strategy_name)

    def update_demo_selection_bias_evidence(self, strategy_name: str, **kwargs):
        self.selection_calls.append({"strategy_name": strategy_name, **kwargs})
        return True, {"verdict": "promote", "passes": True, "reasons": []}

    def update_demo_tail_risk_evidence(self, strategy_name: str, **kwargs):
        self.tail_calls.append({"strategy_name": strategy_name, **kwargs})
        return False, {
            "verdict": "defer_data",
            "passes": False,
            "reasons": ["stress_exposures_missing"],
        }


def test_build_strategy_promotion_evidence_uses_real_raw_series():
    evidence = build_strategy_promotion_evidence(_js_results(), engine_mode="demo")

    ma = evidence["ma_crossover"]
    assert ma.n_trials == 2
    assert ma.n_observations == 384
    assert len(ma.trial_sharpes) == 2
    assert len(ma.candidate_oos_returns) == 2
    assert all(len(series) == 192 for series in ma.candidate_oos_returns)
    assert ma.observed_sharpe > 0.0


def test_push_updates_gate_with_trial_sharpes_and_pbo_returns():
    gate = _FakeGate()
    summary = push_promotion_evidence_from_js_results(
        _js_results(),
        engine_mode="demo",
        gate=gate,
        stress_exposures_by_strategy={
            "ma_crossover": {"crypto_beta": 0.02, "liquidity": 0.01}
        },
    )

    assert summary["status"] == "ok"
    ma_call = next(c for c in gate.selection_calls if c["strategy_name"] == "ma_crossover")
    assert ma_call["n_trials"] == 2
    assert len(ma_call["trial_sharpes"]) == 2
    assert len(ma_call["candidate_oos_returns"]) == 2
    tail_call = next(c for c in gate.tail_calls if c["strategy_name"] == "ma_crossover")
    assert tail_call["stress_exposures"] == {"crypto_beta": 0.02, "liquidity": 0.01}


def test_push_without_stress_exposure_is_honest_fail_closed_not_fake_pass():
    summary = push_promotion_evidence_from_js_results(
        _js_results(),
        engine_mode="demo",
        gate=None,
        stress_exposures_by_strategy=None,
        n_bootstrap=24,
        seed=7,
    )

    assert summary["status"] == "ok"
    assert summary["details"]["ma_crossover"]["selection_verdict"] in {
        "promote",
        "borderline",
        "block",
        "defer_data",
    }
    assert summary["details"]["ma_crossover"]["tail_verdict"] in {"defer_data", "block"}
    assert summary["details"]["ma_crossover"]["tail_passes"] is False


class _FakeCursor:
    def __init__(self):
        self.executed: list[tuple[str, object]] = []
        self._fetchone_queue: list[tuple | None] = []
        self._fetchall_queue: list[list[tuple]] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "to_regclass" in sql:
            self._fetchone_queue.append((True,))
        elif "information_schema.columns" in sql:
            self._fetchall_queue.append(
                [
                    ("demo_selection_bias_report",),
                    ("demo_tail_risk_report",),
                ]
            )
        elif "SELECT pipeline_id" in sql:
            self._fetchone_queue.append((123,))
        elif "SELECT observed_sharpe" in sql:
            self._fetchall_queue.append([(0.25,), (0.30,)])

    def executemany(self, sql, rows):
        self.executed.append((sql, list(rows)))

    def fetchone(self):
        return self._fetchone_queue.pop(0) if self._fetchone_queue else None

    def fetchall(self):
        return self._fetchall_queue.pop(0) if self._fetchall_queue else []


class _FakeConn:
    def __init__(self):
        self.cur = _FakeCursor()
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def rollback(self):
        raise AssertionError("rollback should not be called")

    def close(self):
        self.closed = True


def test_push_persists_trial_ledger_and_reports_when_v079_exists(monkeypatch):
    conn = _FakeConn()
    monkeypatch.setattr(
        "program_code.ml_training.promotion_evidence._connect_dsn",
        lambda dsn: conn,
    )

    summary = push_promotion_evidence_from_js_results(
        _js_results(),
        engine_mode="demo",
        dsn="postgresql://unit-test",
        n_bootstrap=24,
        seed=7,
    )

    assert summary["ledger_rows"] >= 2
    assert summary["persisted_reports"] >= 1
    assert conn.committed is True
    assert conn.closed is True
    sql_text = "\n".join(sql for sql, _ in conn.cur.executed)
    assert "learning.strategy_trial_ledger" in sql_text
    assert "demo_selection_bias_report" in sql_text
    update_params = [
        params
        for sql, params in conn.cur.executed
        if "UPDATE learning.promotion_pipeline" in sql
    ][0]
    json.loads(update_params[0])
    json.loads(update_params[1])
