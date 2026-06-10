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


def test_write_db_import_seam_package_mode_subprocess():
    """E2 MEDIUM-2/LOW 第三版（真 bite，subprocess）：在乾淨 package-mode context 行使
    _write_db 的 dual-path import seam。

    為什麼必須 subprocess：tests/conftest 把 research/ 插進 sys.path，in-process 下
    「原始差層絕對形」與「relative-only 形」兩個歷史壞 import 都可解析——bite 結構性
    不可能（E2 第三輪 mutation 實證兩壞形全存活）。本測試 spawn 乾淨直譯器、cwd=srv 根、
    不插 research/，以 `helper_scripts.research...harness` 真 package member import →
    函數內 relative import 是唯一通路：mutation 回「原始差層絕對形」（燒掉 V127 populate
    的那個）必 ModuleNotFoundError 非 sentinel = 真紅。

    誠實範圍註記：direct-file 執行模式（python3 harness.py）的 fallback 分支不在本測
    覆蓋（需直跑 main+CLI，過重）；該分支由生產 dual-path 結構保證、E2 上輪已 PASS。
    """
    import subprocess
    import sys
    import textwrap
    from pathlib import Path

    srv_root = Path(__file__).resolve().parents[3]
    prog = textwrap.dedent(
        """
        import sys, types
        import psycopg2

        class _Sentinel(Exception):
            pass

        def _boom(*a, **k):
            raise _Sentinel("seam-passed")

        psycopg2.connect = _boom
        from helper_scripts.research.aeg_regime_runner.harness import _write_db
        args = types.SimpleNamespace(dsn="postgresql://sentinel-not-used")
        try:
            _write_db(args, labels=[], transitions=[])
        except _Sentinel:
            print("SEAM_OK")
            sys.exit(0)
        except Exception as exc:  # ModuleNotFoundError 等 = import seam 壞
            print(f"SEAM_FAIL:{type(exc).__name__}:{exc}")
            sys.exit(1)
        print("SEAM_FAIL:no-exception")
        sys.exit(1)
        """
    )
    r = subprocess.run(
        [sys.executable, "-c", prog], cwd=str(srv_root),
        capture_output=True, text=True, timeout=120,
    )
    assert "SEAM_OK" in r.stdout, f"stdout={r.stdout!r} stderr={r.stderr[-500:]!r}"
