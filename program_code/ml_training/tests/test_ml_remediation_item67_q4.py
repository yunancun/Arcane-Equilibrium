"""Mac-runnable unit tests for the ML remediation follow-up trio.

涵蓋（無需真 PG，全 mock/monkeypatch）：
  - Item 6：CPCV 持久化 DSN threading（統一 OPENCLAW_DATABASE_URL）+ distinct
    persist_status + PG_PASSWORD/PG_PASS 相容。
  - Item 7：model_registry register 路徑寫入非空 PIT lineage 三欄
    （training_window_start / training_window_end / pit_manifest_hash）。
  - Q4：quantile_reports 每道 gate 蓋上 in-sample provenance；canary_promoter
    對 two-way in-sample 退路產物封鎖 auto-promotion。
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


# =====================================================================
# Item 6 — CPCV persistence DSN threading + loud distinct status
# =====================================================================

from program_code.ml_training.cpcv_validator import (
    CPCVConfig,
    CPCVResult,
    _persist_cpcv_result,
    _resolve_persist_dsn,
    validate_cpcv,
)


def _cpcv_result() -> CPCVResult:
    return CPCVResult(
        fold_metrics=[{"sharpe": 0.4, "fold": 0}],
        mean_sharpe=0.4,
        std_sharpe=0.1,
        power_estimate=0.9,
        passed=True,
        n_folds=4,
        embargo_hours=24,
        strategy_type="trending",
    )


def test_resolve_persist_dsn_precedence(monkeypatch):
    for var in ("OPENCLAW_DATABASE_URL", "OPENCLAW_PG_DSN", "PG_DSN"):
        monkeypatch.delenv(var, raising=False)
    # explicit 最優先
    monkeypatch.setenv("OPENCLAW_DATABASE_URL", "dsn://canonical")
    assert _resolve_persist_dsn("dsn://explicit") == "dsn://explicit"
    # 無 explicit → OPENCLAW_DATABASE_URL（canonical）
    assert _resolve_persist_dsn(None) == "dsn://canonical"
    # canonical 缺 → legacy OPENCLAW_PG_DSN
    monkeypatch.delenv("OPENCLAW_DATABASE_URL", raising=False)
    monkeypatch.setenv("OPENCLAW_PG_DSN", "dsn://legacy1")
    assert _resolve_persist_dsn(None) == "dsn://legacy1"
    # 再缺 → PG_DSN
    monkeypatch.delenv("OPENCLAW_PG_DSN", raising=False)
    monkeypatch.setenv("PG_DSN", "dsn://legacy2")
    assert _resolve_persist_dsn(None) == "dsn://legacy2"
    monkeypatch.delenv("PG_DSN", raising=False)
    assert _resolve_persist_dsn(None) is None


def test_persist_status_skipped_no_driver(monkeypatch):
    # psycopg2 不可 import → distinct benign skip 狀態（非 write_failed）。
    monkeypatch.setitem(sys.modules, "psycopg2", None)
    assert _persist_cpcv_result(_cpcv_result()) == "skipped_no_driver"


def test_persist_status_connect_failed_when_dsn_present(monkeypatch):
    # 有明確 DSN 目標卻連不上 = 真脆弱性 → connect_failed（呼叫端會 LOUD WARN）。
    fake = types.SimpleNamespace(
        connect=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no route"))
    )
    monkeypatch.setitem(sys.modules, "psycopg2", fake)
    status = _persist_cpcv_result(_cpcv_result(), dsn="postgresql://x/y")
    assert status == "connect_failed"


def test_persist_status_skipped_no_target_without_dsn(monkeypatch):
    # 無 DSN、host/port 直連也失敗（Mac 無本地 PG）→ benign skipped_no_target。
    for var in ("OPENCLAW_DATABASE_URL", "OPENCLAW_PG_DSN", "PG_DSN"):
        monkeypatch.delenv(var, raising=False)
    fake = types.SimpleNamespace(
        connect=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("refused"))
    )
    monkeypatch.setitem(sys.modules, "psycopg2", fake)
    status = _persist_cpcv_result(_cpcv_result(), dsn=None)
    assert status == "skipped_no_target"


def test_persist_prefers_pg_password_over_pg_pass(monkeypatch):
    # 密碼 env 統一：PG_PASSWORD（規範名，與 realized_edge_stats 對齊）優先於舊 PG_PASS。
    for var in ("OPENCLAW_DATABASE_URL", "OPENCLAW_PG_DSN", "PG_DSN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PG_PASSWORD", "canonical_pw")
    monkeypatch.setenv("PG_PASS", "legacy_pw")
    captured = {}

    def _connect(*_a, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after capturing kwargs")

    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=_connect))
    _persist_cpcv_result(_cpcv_result(), dsn=None)
    assert captured.get("password") == "canonical_pw"


def test_persist_falls_back_to_pg_pass_when_pg_password_unset(monkeypatch):
    for var in ("OPENCLAW_DATABASE_URL", "OPENCLAW_PG_DSN", "PG_DSN", "PG_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PG_PASS", "legacy_pw")
    captured = {}

    def _connect(*_a, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop")

    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=_connect))
    _persist_cpcv_result(_cpcv_result(), dsn=None)
    assert captured.get("password") == "legacy_pw"


def test_validate_cpcv_threads_dsn_and_records_status(monkeypatch):
    # validate_cpcv 不再吞掉持久化結果：dsn 一路 thread 進去，狀態落 result.persist_status。
    import numpy as np

    seen = {}

    def _spy_persist(result, model_name="", model_version="", dsn=None):
        seen["dsn"] = dsn
        return "connect_failed"

    monkeypatch.setattr(
        "program_code.ml_training.cpcv_validator._persist_cpcv_result", _spy_persist
    )

    n = 240
    X = np.random.default_rng(0).normal(size=(n, 3))
    y = np.random.default_rng(1).normal(size=n)
    ts = np.arange(n, dtype=np.float64) * 3600.0

    def _model_fn(X_tr, y_tr, X_te, y_te):
        return {"sharpe": 0.3}

    result = validate_cpcv(
        X, y, ts, "trending", _model_fn, CPCVConfig(), dsn="postgresql://threaded/dsn"
    )
    assert seen["dsn"] == "postgresql://threaded/dsn"
    assert result.persist_status == "connect_failed"


# =====================================================================
# Item 7 — model_registry PIT lineage columns
# =====================================================================

import program_code.ml_training.model_registry as _model_registry_mod
from program_code.ml_training.model_registry import (
    VERDICT_SHADOW_ONLY,
    register_model,
    register_quantile_trio_from_onnx_out,
)


@pytest.fixture(autouse=True)
def _reset_lineage_probe_cache():
    # Item 7 tolerance：_lineage_columns_present 用進程級快取，測試間須歸零，
    #   否則前一測試的探測結果會滲漏到下一測試。
    _model_registry_mod._LINEAGE_COLUMNS_PRESENT = None
    yield
    _model_registry_mod._LINEAGE_COLUMNS_PRESENT = None


class _FakeCursor:
    def __init__(self, lineage_present: bool = True):
        # lineage_present 模擬 V157 是否已 apply：True → schema 探測回一列（走 full
        #   SQL）；False → 探測回 None（走 legacy SQL，V157 pending）。
        self.params = []
        self.sqls = []
        self._lineage_present = lineage_present
        self._last_was_probe = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        if "information_schema.columns" in sql:
            # schema 探測 query：不計入 insert params，只設旗標供 fetchone 回應。
            self._last_was_probe = True
            return
        self._last_was_probe = False
        self.sqls.append(sql)
        self.params.append(params)

    def fetchone(self):
        if self._last_was_probe:
            # 欄位存在 → 回一列；不存在 → None（觸發 legacy 路徑）。
            return (1,) if self._lineage_present else None
        return (len(self.params),)


class _FakeConn:
    def __init__(self, lineage_present: bool = True):
        self.cursor_obj = _FakeCursor(lineage_present=lineage_present)
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_register_model_writes_non_null_lineage_columns():
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    end = datetime(2026, 6, 20, tzinfo=timezone.utc)
    fake = _FakeConn()
    with patch("program_code.ml_training.model_registry._connect", return_value=fake):
        row_id = register_model(
            strategy="grid_trading",
            engine_mode="demo",
            quantile="q50",
            schema_version="v1",
            train_date="2026-06-20",
            artifact_path="/tmp/does_not_exist_q50.onnx",
            verdict=VERDICT_SHADOW_ONLY,
            training_window_start=start,
            training_window_end=end,
            pit_manifest_hash="a" * 64,
        )
    assert row_id == 1
    params = fake.cursor_obj.params[0]
    # 位序不變性：quantile 仍在 [2]，report_jsonb 仍在 [8]（既有測試依此讀）。
    assert params[2] == "q50"
    # 三個 lineage 欄 append 在最後三位且非空。
    assert params[-3] == start
    assert params[-2] == end
    assert params[-1] == "a" * 64


def test_register_quantile_trio_threads_lineage_to_each_row():
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    end = datetime(2026, 6, 20, tzinfo=timezone.utc)
    onnx_out = {
        "train_date": "2026-06-20",
        "artifacts": {
            "q10": {"written": True, "path": "/tmp/q10.onnx"},
            "q50": {"written": True, "path": "/tmp/q50.onnx"},
            "q90": {"written": True, "path": "/tmp/q90.onnx"},
        },
    }
    fake = _FakeConn()
    with patch("program_code.ml_training.model_registry._connect", return_value=fake):
        ids = register_quantile_trio_from_onnx_out(
            onnx_out=onnx_out,
            strategy="grid_trading",
            engine_mode="demo",
            schema_version="v1",
            verdict=VERDICT_SHADOW_ONLY,
            training_window_start=start,
            training_window_end=end,
            pit_manifest_hash="b" * 64,
        )
    assert ids == [1, 2, 3]
    for params in fake.cursor_obj.params:
        assert params[-3] == start
        assert params[-2] == end
        assert params[-1] == "b" * 64


def test_register_model_tolerant_when_lineage_columns_absent():
    # V157 tolerance：schema 探測回報三欄尚未存在時，register 必須改走 legacy SQL
    #   （14 param、無 lineage 欄）且仍回傳 id——即 register 不因欄位缺席而失敗。
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    end = datetime(2026, 6, 20, tzinfo=timezone.utc)
    fake = _FakeConn(lineage_present=False)
    with patch("program_code.ml_training.model_registry._connect", return_value=fake):
        row_id = register_model(
            strategy="grid_trading",
            engine_mode="demo",
            quantile="q50",
            schema_version="v1",
            train_date="2026-06-20",
            artifact_path="/tmp/does_not_exist_q50.onnx",
            verdict=VERDICT_SHADOW_ONLY,
            # 即使 caller 帶了 lineage 值，legacy 路徑也應丟棄它們而非把 SQL 撐爆。
            training_window_start=start,
            training_window_end=end,
            pit_manifest_hash="c" * 64,
        )
    # 註冊成功（未拋、有 id）= 容忍性成立。
    assert row_id == 1
    params = fake.cursor_obj.params[0]
    # legacy 只綁 14 個 param（drop 掉三個 lineage 值）。
    assert len(params) == 14
    # 位序不變性：quantile 仍在 [2]，created_by 是最後一個 param。
    assert params[2] == "q50"
    assert params[-1] == "run_training_pipeline"
    # lineage 值確實不在 param tuple 內。
    assert start not in params
    assert end not in params
    assert ("c" * 64) not in params
    # 使用的是 legacy SQL：INSERT column list 不含 lineage 欄。
    used_sql = fake.cursor_obj.sqls[0]
    assert "pit_manifest_hash" not in used_sql
    assert "training_window_start" not in used_sql
    assert "training_window_end" not in used_sql


# =====================================================================
# Q4 — per-gate in-sample provenance + canary two-way promotion guard
# =====================================================================

from program_code.ml_training.quantile_reports import (
    GATE_METRIC_SOURCE_IN_SAMPLE_TWO_WAY,
    GATE_METRIC_SOURCE_OOS,
    _stamp_gate_metric_provenance,
)


def _gates_fixture() -> dict:
    return {
        "pinball_skill": {"passed": True, "per_quantile": {}},
        "coverage_error": {"passed": True, "per_quantile": {}},
        "decile_lift": {"passed": True, "point_estimate": 1.6},
        "crossing_rate": {"passed": True, "crossing_rate": 0.0},
        "lgbm_vs_linear_qr": {"passed": True, "per_quantile": {}},
        "label_composition": {"passed": True, "source": "unavailable"},
    }


def test_stamp_two_way_marks_each_gate_in_sample():
    gates = _gates_fixture()
    _stamp_gate_metric_provenance(gates, "two_way_shadow_capped")
    for name, detail in gates.items():
        assert detail["metric_partition_source"] == GATE_METRIC_SOURCE_IN_SAMPLE_TWO_WAY
        assert detail["in_sample"] is True
    # 既有 gate 級 source 不被覆寫（獨立 key 不衝突）。
    assert gates["label_composition"]["source"] == "unavailable"


def test_stamp_three_way_marks_each_gate_oos():
    gates = _gates_fixture()
    _stamp_gate_metric_provenance(gates, "three_way")
    for detail in gates.values():
        assert detail["metric_partition_source"] == GATE_METRIC_SOURCE_OOS
        assert detail["in_sample"] is False


from program_code.ml_training.canary_promoter import (
    CanaryDecision,
    CanaryThresholds,
    _is_in_sample_two_way_artifact,
    evaluate_canary_eligibility,
)
from program_code.ml_training.model_registry import CANARY_SHADOW, VERDICT_SHADOW_ONLY

_NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def _shadow_row(acceptance_report: dict) -> dict:
    return {
        "id": 7,
        "strategy": "grid_trading",
        "engine_mode": "demo",
        "quantile": "q50",
        "schema_version": "v1",
        "canary_status": CANARY_SHADOW,
        "verdict": VERDICT_SHADOW_ONLY,
        "acceptance_report": acceptance_report,
        "train_date": (_NOW - timedelta(days=5)).date(),
        "training_sample_size": 600,
        "created_at": _NOW - timedelta(days=5),
    }


def test_is_in_sample_two_way_detects_partition_mode():
    assert _is_in_sample_two_way_artifact({"partition_mode": "two_way_shadow_capped"})
    assert _is_in_sample_two_way_artifact(
        {"ship_gate_metric_source": "holdout_two_way_shadow_capped"}
    )
    assert _is_in_sample_two_way_artifact(
        {"gates": {"pinball_skill": {"in_sample": True}}}
    )
    assert not _is_in_sample_two_way_artifact({"partition_mode": "three_way"})
    assert not _is_in_sample_two_way_artifact(None)


def test_canary_blocks_auto_promotion_of_two_way_artifact():
    row = _shadow_row({"partition_mode": "two_way_shadow_capped"})
    res = evaluate_canary_eligibility(row, cur=None, thresholds=CanaryThresholds(), now=_NOW)
    assert res.decision is CanaryDecision.HOLD
    assert res.metrics.get("in_sample_two_way") is True


def test_canary_still_promotes_normal_three_way_shadow():
    # 防過度封鎖：正常 three_way shadow 產物仍照常評估為 PROMOTE（guard 不誤傷）。
    row = _shadow_row({"partition_mode": "three_way", "metrics": {"brier_score": 0.2}})
    res = evaluate_canary_eligibility(row, cur=None, thresholds=CanaryThresholds(), now=_NOW)
    assert res.decision is CanaryDecision.PROMOTE
