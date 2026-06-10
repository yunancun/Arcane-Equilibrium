"""AEG-S2 regime runner tests.

MODULE_NOTE:
  模塊用途：以 synthetic data 驗證 regime runner 的三個硬不變量：
    1) 每個 signal 只用 prior close，尾部追加未來極端波動不得改早期 label；
    2) feature_lineage 必須 lag >= 一根完整 daily bar；
    3) V127 詞表只接受 AEG regime，不接受 V002 legacy vocabulary。
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from aeg_regime_runner import BAR_MS_1D, CLASSIFIER_VERSION, feature_rules_digest
from aeg_regime_runner.classifier import (
    build_label_rows,
    compute_feature_rows_for_symbol,
    validate_label_row,
)
from aeg_regime_runner.lineage import (
    build_feature_lineage_rows,
    validate_feature_lineage,
)
from aeg_regime_runner.harness import _filter_alive
from aeg_regime_runner import artifact as artifact_mod


UTC = dt.timezone.utc


def _series(n: int, *, start: float = 100.0, step: float = 0.003) -> list[tuple[dt.datetime, float]]:
    out = []
    price = start
    base = dt.datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(n):
        price *= 1.0 + step
        out.append((base + dt.timedelta(days=i), price))
    return out


def test_future_extreme_volatility_does_not_change_prefix_labels():
    base = _series(260)
    extended = list(base)
    price = base[-1][1]
    last_ts = base[-1][0]
    for i in range(60):
        price *= 0.92
        extended.append((last_ts + dt.timedelta(days=i + 1), price))

    base_rows, _ = build_label_rows({"BTCUSDT": base}, run_id="r1")
    ext_rows, _ = build_label_rows({"BTCUSDT": extended}, run_id="r1")

    base_by_ts = {r["signal_ts"]: r for r in base_rows}
    ext_by_ts = {r["signal_ts"]: r for r in ext_rows}
    for ts, row in base_by_ts.items():
        assert ext_by_ts[ts]["main_regime"] == row["main_regime"]
        assert ext_by_ts[ts]["rv_30d_percentile_365"] == row["rv_30d_percentile_365"]


def test_current_bar_close_does_not_affect_same_signal_label():
    closes = _series(220)
    mutated = list(closes)
    signal_ts = mutated[-1][0]
    mutated[-1] = (signal_ts, mutated[-1][1] * 100.0)

    original = compute_feature_rows_for_symbol("BTCUSDT", closes, run_id="r1")[-1]
    changed = compute_feature_rows_for_symbol("BTCUSDT", mutated, run_id="r1")[-1]

    assert changed["signal_ts"] == original["signal_ts"]
    assert changed["ret_90d"] == original["ret_90d"]
    assert changed["ma_50"] == original["ma_50"]


def test_feature_lineage_requires_one_complete_bar_lag():
    rows, _ = build_label_rows({"BTCUSDT": _series(120)}, run_id="r1")
    lineage = build_feature_lineage_rows(rows[-1:])

    ok, reason = validate_feature_lineage(lineage)

    assert ok is True
    assert reason == "pass"
    assert all(r["lag_ms"] >= BAR_MS_1D for r in lineage)

    bad = [dict(lineage[0], lag_ms=BAR_MS_1D - 1, leak_violation_count=1)]
    ok, reason = validate_feature_lineage(bad)
    assert ok is False
    assert reason.startswith("feature_lineage_leak:BTCUSDT")


def test_v002_legacy_vocabulary_is_rejected():
    with pytest.raises(ValueError, match="invalid_aeg_regime:TRENDING_UP"):
        validate_label_row({"main_regime": "TRENDING_UP"})


def test_fnd2_alive_mask_filters_labels_after_delist():
    labels, _ = build_label_rows({"BTCUSDT": _series(10)}, run_id="r1")
    alive_to = labels[4]["signal_ts"]

    filtered = _filter_alive(labels, {"BTCUSDT": (labels[0]["signal_ts"], alive_to)})

    assert len(filtered) == 5
    assert filtered[-1]["signal_ts"] == alive_to


def test_artifact_writer_outputs_manifest_and_index(tmp_path: Path):
    labels, transitions = build_label_rows({"BTCUSDT": _series(100)}, run_id="r1")
    lineage = build_feature_lineage_rows(labels)
    written = artifact_mod.write_all(
        labels=labels,
        transitions=transitions,
        lineage=lineage,
        summary={
            "run_id": "r1",
            "classifier_version": CLASSIFIER_VERSION,
            "feature_rules_digest": feature_rules_digest(),
        },
        run_id="r1",
        repo_root=Path("."),
        runtime_host="test",
        artifact_root=tmp_path,
    )

    assert Path(written["regime_labels"]).exists()
    assert Path(written["feature_lineage"]).exists()
    index = Path(written["artifact_index"]).read_text(encoding="utf-8")
    assert "regime_labels_csv" in index
    assert "feature_lineage_csv" in index


def test_write_db_import_seam_truly_executes(monkeypatch):
    """E2 MEDIUM-2 + re-review LOW 真 bite 版：實際執行 _write_db 走過 dual-path import。

    舊碼絕對 import 差一層 research → package 模式 --write-db 必 ModuleNotFoundError
    （V127 從未被 populate 故 deploy 至今未暴露）。本測試 monkeypatch psycopg2.connect
    為 sentinel raise——sentinel 到達 = `from .db_writer import persist_regime_rows`
    （或 fallback）**已成功解析並越過**（import 在 connect 之前）；revert 成壞 import
    時本測試以 ModuleNotFoundError（非 sentinel）失敗 = 真 regression bite。
    """
    import types

    import psycopg2
    import pytest as _pytest

    from aeg_regime_runner import harness as _h

    class _Sentinel(Exception):
        pass

    def _boom(*a, **k):
        raise _Sentinel("import-seam-passed")

    monkeypatch.setattr(psycopg2, "connect", _boom)
    args = types.SimpleNamespace(dsn="postgresql://sentinel-not-used")
    with _pytest.raises(_Sentinel):
        _h._write_db(args, labels=[], transitions=[])
