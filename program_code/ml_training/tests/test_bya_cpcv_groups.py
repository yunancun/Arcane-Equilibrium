"""Adversarial sample identity regressions for the public CPCV interface."""
import numpy as np
from program_code.ml_training import cpcv_validator as cv


def test_replicating_one_timestamp_cannot_make_cpcv_pass(monkeypatch):
    monkeypatch.setattr(cv, '_persist_cpcv_result', lambda *a, **k: 'skipped_no_dsn')
    ts = np.full(400, 1_700_000_000.0)
    folds = cv.generate_folds(ts, 'trending')
    for train, test in folds:
        assert not set(ts[train]) & set(ts[test])
    result = cv.validate_cpcv(np.ones((400, 2)), np.ones(400), ts,
                              'trending', lambda *a: {'sharpe': 1.0})
    assert not result.passed
    assert result.power_estimate < 0.5


def test_uneven_replicas_do_not_split_groups_or_inflate_power(monkeypatch):
    monkeypatch.setattr(cv, '_persist_cpcv_result', lambda *a, **k: 'skipped_no_target')
    ts = 1.7e9 + np.arange(200) * 3600
    repeated = np.repeat(ts, np.arange(200) % 7 + 1)
    powers = []
    for axis in (ts, repeated, ts * 1000):
        normalized = cv.validated_timestamps(axis)
        for train, test in cv.generate_folds(axis, 'trending'):
            assert not set(normalized[train]) & set(normalized[test])
            assert min(abs(normalized[a] - normalized[b]) for a in train for b in test) > 24 * 3600
        r = cv.validate_cpcv(np.ones((len(axis), 2)), np.ones(len(axis)), axis,
                              'trending', lambda *a: {'sharpe': 1.0})
        powers.append(r.power_estimate)
        assert r.passed
    assert powers[0] == powers[1] == powers[2]


def test_too_few_groups_and_nonfinite_metrics_cannot_pass(monkeypatch):
    monkeypatch.setattr(cv, '_persist_cpcv_result', lambda *a, **k: 'skipped_no_target')
    for n in (3, 20, 400):
        ts = 1.7e9 + np.arange(n) * 3600
        r = cv.validate_cpcv(np.ones((n, 2)), np.ones(n), ts,
                              'trending', lambda *a: {'sharpe': float('nan')})
        assert not r.passed


def test_exact_replicas_do_not_reweight_model_evaluation(monkeypatch):
    monkeypatch.setattr(cv, '_persist_cpcv_result', lambda *a, **k: 'skipped_no_target')
    ts = 1.7e9 + np.arange(200) * 3600
    x = np.arange(400, dtype=float).reshape(200, 2)
    y = np.arange(200, dtype=float)
    consumed = []
    for multiplicity in (np.ones(200, dtype=int), np.arange(200) % 5 + 1):
        sizes = []
        def model(a, b, c, d):
            sizes.append((len(b), len(d), float(np.mean(b)), float(np.mean(d))))
            return {'sharpe': 1.0}
        cv.validate_cpcv(np.repeat(x, multiplicity, axis=0), np.repeat(y, multiplicity),
                         np.repeat(ts, multiplicity), 'trending', model)
        consumed.append(sizes)
    assert consumed[0] == consumed[1]
