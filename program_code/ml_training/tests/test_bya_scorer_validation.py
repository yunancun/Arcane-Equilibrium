"""Scorer eligibility must require valid evaluation inputs."""
import numpy as np
import pytest
from program_code.ml_training.scorer_trainer import ScorerConfig, train_scorer
from program_code.ml_training.tests.test_item5_scorer_cpcv_cap_e4 import _install_fake_lightgbm


@pytest.mark.parametrize('timestamps', [None, np.arange(599, dtype=float), np.full(600, np.nan), np.arange(600)[::-1], np.r_[np.full(300, 1.7e9), np.full(300, 1.7e12)]])
def test_missing_or_mismatched_time_axis_cannot_export_eligible_model(monkeypatch, tmp_path, timestamps):
    _install_fake_lightgbm(monkeypatch)
    x = np.arange(1200, dtype=float).reshape(600, 2)
    result = train_scorer(x, x[:, 0], ['a', 'b'],
                          ScorerConfig(output_dir=str(tmp_path)), timestamps=timestamps)
    assert not result.success
    assert result.status == 'reference_only'
    assert result.metrics.get('ship_eligible', 0) == 0
    assert not (tmp_path / 'scorer_lgb.txt').exists()


def test_sealed_outer_holdout_never_enters_lightgbm_training_or_validation(monkeypatch, tmp_path):
    from program_code.ml_training import cpcv_validator as cv
    _install_fake_lightgbm(monkeypatch)
    import lightgbm as lgb
    original = lgb.Dataset
    consumed_labels = []

    def capture_dataset(data, label=None, **kwargs):
        consumed_labels.extend(np.asarray(label).tolist())
        return original(data, label=label, **kwargs)

    monkeypatch.setattr(lgb, 'Dataset', capture_dataset)
    monkeypatch.setattr(cv, '_persist_cpcv_result', lambda *a, **k: 'skipped_no_target')
    n = 600
    x = np.arange(n * 2, dtype=float).reshape(n, 2) / n
    y = x[:, 0].copy()
    y[480:] = 1_000_000.0 + np.arange(120)
    ts = 1_700_000_000_000.0 + np.arange(n) * 3_600_000
    result = train_scorer(x, y, ['a', 'b'],
                          ScorerConfig(output_dir=str(tmp_path)), timestamps=ts)
    assert result.success, result.error
    assert consumed_labels and max(consumed_labels) < 1_000_000.0


@pytest.mark.parametrize("duplicate_holdout", [False, True])
def test_real_lightgbm_outer_labels_do_not_change_model_hash(monkeypatch, tmp_path, duplicate_holdout):
    from hashlib import sha256
    from pathlib import Path
    pytest.importorskip('lightgbm')
    from program_code.ml_training import cpcv_validator as cv
    monkeypatch.setattr(cv, '_persist_cpcv_result', lambda *a, **k: 'skipped_no_target')
    rng = np.random.default_rng(19)
    x = rng.normal(size=(600, 2))
    y = 2 * x[:, 0] - x[:, 1] + rng.normal(scale=.05, size=600)
    ts = 1.7e12 + np.arange(600) * 3_600_000
    if duplicate_holdout:
        repeats = np.r_[np.ones(480, dtype=int), np.full(120, 2)]
        x, y, ts = np.repeat(x, repeats, axis=0), np.repeat(y, repeats), np.repeat(ts, repeats)
    results = []
    for trial in range(2):
        labels = y.copy()
        if trial:
            # Changing only one copy alters dedup row count, but must not move
            # the time-group split or change the development model.
            labels[480::2] = -labels[480::2] + 30
        r = train_scorer(x, labels, ['a', 'b'],
                         ScorerConfig(output_dir=str(tmp_path / str(trial)), n_estimators=12),
                         timestamps=ts)
        assert r.success, r.error
        results.append(r)
    a, b = results
    assert sha256(Path(a.model_path).read_bytes()).digest() == sha256(Path(b.model_path).read_bytes()).digest()
    assert a.status == b.status
    for key in ('cpcv_passed', 'cpcv_power', 'best_iteration', 'ship_eligible'):
        assert a.metrics[key] == b.metrics[key]
    assert a.metrics['rmse'] != b.metrics['rmse']
