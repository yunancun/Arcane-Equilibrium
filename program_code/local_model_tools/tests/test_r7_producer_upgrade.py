"""REF-20 Sprint C2 R7 W1 — 3 producer 升級單元測試。

測試範圍：
  - dream_engine.persist_dream_insights：
    * test_dream_engine_calibrated_replay_path
    * test_dream_engine_none_label_skips_insert
    * test_dream_engine_no_provider_fallback_real_outcome
  - opportunity_tracker.persist_regret_summary：
    * test_opportunity_tracker_calibrated_replay_path
    * test_opportunity_tracker_no_provider_fallback
  - mlde_shadow_advisor._persist_recommendations：
    * test_mlde_shadow_advisor_calibrated_replay_path
    * test_mlde_shadow_advisor_no_provider_fallback
    * test_mlde_shadow_advisor_none_label_skips_rec

測試模式：
  - Mac dev mock pattern：以 monkeypatch 改 psycopg2.connect → fake conn /
    cur，捕捉 cur.execute 內 SQL string + arg tuple。
  - 不開實際 PG（V055 V036 路徑由 Linux operator 後續 OPENCLAW_TEST_LIVE_PG
    smoke 驗）。

重點驗證：
  1. R7 path：tier='calibrated_replay'、metadata 4-tuple 同步傳給 V036。
  2. NONE label：skip INSERT；不寫 V036。
  3. backward-compat：不傳 provider → tier='real_outcome'，metadata 全
     None；既有 18 月生產行為不破。

CLAUDE.md §七 governance（2026-05-05 中文 default）：MODULE_NOTE +
docstring 全中文。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.calibration_label import (
    CalibrationResult,
    ExecutionConfidence,
)


# ─────────────────────────────────────────────────────────────────────
# 共用 fixture / helper
# ─────────────────────────────────────────────────────────────────────


def _calibrated_result(
    label: ExecutionConfidence = ExecutionConfidence.CALIBRATED,
    ttl_days: int = 7,
    sample_count: int = 1162,
) -> CalibrationResult:
    """構造測試 CalibrationResult。"""
    return CalibrationResult(
        label=label,
        sample_count=sample_count,
        last_fill_age_ms=12_345,
        fee_bps_mad=2.0,
        fee_bps_iqr=5.0,
        net_bps_p5=-3.0,
        net_bps_p50=0.5,
        net_bps_p95=4.0,
        ttl=timedelta(days=ttl_days),
    )


class FakeCursor:
    """模擬 psycopg2 cursor — 捕捉 cur.execute 呼叫序列。"""

    def __init__(self, manifest_hash_bytes: bytes | None = None):
        # SELECT V049 manifest_hash 預設回值
        self._manifest_hash = manifest_hash_bytes
        self.execute_calls: list[tuple[str, tuple]] = []
        self._next_fetchone: object = None

    def execute(self, sql: str, params: tuple = ()) -> None:  # noqa: D401
        self.execute_calls.append((sql, params))
        # 自動 dispatch SELECT manifest_hash 回 fetchone
        if "SELECT manifest_hash" in sql or "manifest_hash" in sql.lower() and "FROM replay.experiments" in sql:
            self._next_fetchone = (self._manifest_hash,) if self._manifest_hash is not None else None

    def fetchone(self):
        return self._next_fetchone

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConn:
    """模擬 psycopg2 connection — 提供 cursor() + commit()。"""

    def __init__(self, cur: FakeCursor):
        self._cur = cur
        self.commit_called = False

    def cursor(self):
        return self._cur

    def commit(self):
        self.commit_called = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# ─────────────────────────────────────────────────────────────────────
# dream_engine.persist_dream_insights tests
# ─────────────────────────────────────────────────────────────────────


def _patch_dream_engine_dsn(monkeypatch, summary_fn):
    """patch dream_engine 環境：DSN + summary。"""
    import program_code.local_model_tools.dream_engine as de_mod

    monkeypatch.setattr(de_mod, "_resolve_dsn", lambda x: "postgresql://fake")
    monkeypatch.setattr(de_mod, "get_latest_dream_summary", summary_fn)
    return de_mod


def test_dream_engine_calibrated_replay_path(monkeypatch):
    """provider 回 CALIBRATED → SQL 寫 calibrated_replay tier + metadata。"""
    import program_code.local_model_tools.dream_engine as de_mod

    fake_hash = bytes.fromhex("aa" * 32)
    cur = FakeCursor(manifest_hash_bytes=fake_hash)
    conn = FakeConn(cur)

    summary = {
        "insights": [
            {
                "strategy_name": "grid_trading",
                "expected_improvement_bps": 5.0,
                "confidence": 0.8,
                "sample_count": 1162,
                "replay_experiment_id": "00000000-0000-0000-0000-000000000001",
            },
        ],
    }

    _patch_dream_engine_dsn(monkeypatch, lambda *a, **k: summary)
    monkeypatch.setattr(
        de_mod.psycopg2, "connect", lambda *a, **k: conn,
    )

    cal = _calibrated_result()

    def provider(strategy, symbol):
        return cal

    result = de_mod.persist_dream_insights(
        engine_mode="demo",
        R6_calibration_provider=provider,
    )

    assert result["inserted"] == 1
    assert result["calibrated_inserted"] == 1
    assert result["skipped_none_label"] == 0
    assert conn.commit_called

    # cur.execute 預期 2 次：SELECT V049 + V036 INSERT
    assert len(cur.execute_calls) == 2

    # 第 1 次：SELECT manifest_hash FROM replay.experiments
    sql_select, params_select = cur.execute_calls[0]
    assert "SELECT manifest_hash" in sql_select
    assert "replay.experiments" in sql_select
    assert params_select == ("00000000-0000-0000-0000-000000000001",)

    # 第 2 次：V036 INSERT 19 args，tier='calibrated_replay'
    sql_insert, params_insert = cur.execute_calls[1]
    assert "verify_replay_evidence_and_insert" in sql_insert
    # params_insert tuple 結構：
    # (engine_mode, strategy, expected_bps, confidence, sample_count,
    #  payload, tier, replay_exp_id, hash_hex, expires_at)
    assert len(params_insert) == 10
    assert params_insert[6] == "calibrated_replay"  # tier
    assert params_insert[7] == "00000000-0000-0000-0000-000000000001"
    assert params_insert[8] == "aa" * 32  # manifest_hash hex
    assert isinstance(params_insert[9], datetime)  # expires_at


def test_dream_engine_none_label_skips_insert(monkeypatch):
    """provider 回 NONE label → skip insert，0 V036 call。"""
    import program_code.local_model_tools.dream_engine as de_mod

    cur = FakeCursor(manifest_hash_bytes=bytes.fromhex("aa" * 32))
    conn = FakeConn(cur)

    summary = {
        "insights": [
            {
                "strategy_name": "bb_reversion",
                "expected_improvement_bps": -1.0,
                "confidence": 0.1,
                "sample_count": 7,
                "replay_experiment_id": "00000000-0000-0000-0000-000000000002",
            },
        ],
    }

    _patch_dream_engine_dsn(monkeypatch, lambda *a, **k: summary)
    monkeypatch.setattr(
        de_mod.psycopg2, "connect", lambda *a, **k: conn,
    )

    cal_none = _calibrated_result(
        label=ExecutionConfidence.NONE, ttl_days=0, sample_count=7,
    )

    def provider(strategy, symbol):
        return cal_none

    result = de_mod.persist_dream_insights(
        engine_mode="demo",
        R6_calibration_provider=provider,
    )

    # 預期 inserted=0，skipped_none_label=1
    assert result["inserted"] == 0
    assert result["skipped_none_label"] == 1
    assert result["calibrated_inserted"] == 0

    # NONE label 短路：不該 SELECT V049（helper 直接回 None）
    select_count = sum(
        1 for sql, _ in cur.execute_calls if "SELECT manifest_hash" in sql
    )
    assert select_count == 0
    # 0 V036 INSERT
    insert_count = sum(
        1 for sql, _ in cur.execute_calls
        if "verify_replay_evidence_and_insert" in sql
    )
    assert insert_count == 0


def test_dream_engine_no_provider_fallback_real_outcome(monkeypatch):
    """不傳 R6_calibration_provider → backward-compat real_outcome。"""
    import program_code.local_model_tools.dream_engine as de_mod

    cur = FakeCursor()
    conn = FakeConn(cur)

    summary = {
        "insights": [
            {
                "strategy_name": "grid_trading",
                "expected_improvement_bps": 5.0,
                "confidence": 0.8,
                "sample_count": 1000,
            },
        ],
    }

    _patch_dream_engine_dsn(monkeypatch, lambda *a, **k: summary)
    monkeypatch.setattr(
        de_mod.psycopg2, "connect", lambda *a, **k: conn,
    )

    # 不傳 provider
    result = de_mod.persist_dream_insights(engine_mode="demo")

    assert result["inserted"] == 1
    # backward-compat: result 不含 R7-only key
    assert "calibrated_inserted" not in result
    assert "skipped_none_label" not in result

    # 1 V036 INSERT，tier='real_outcome'
    insert_calls = [
        (sql, params) for sql, params in cur.execute_calls
        if "verify_replay_evidence_and_insert" in sql
    ]
    assert len(insert_calls) == 1
    _, params = insert_calls[0]
    # legacy path: tier 在 params[6]，metadata 全 None
    assert params[6] == "real_outcome"
    assert params[7] is None  # replay_experiment_id
    assert params[8] is None  # manifest_hash
    assert params[9] is None  # expires_at


# ─────────────────────────────────────────────────────────────────────
# opportunity_tracker.persist_regret_summary tests
# ─────────────────────────────────────────────────────────────────────


def _patch_opp_tracker_dsn(monkeypatch, summary_fn):
    """patch opportunity_tracker 環境：DSN + summary。"""
    import program_code.local_model_tools.opportunity_tracker as ot_mod

    monkeypatch.setattr(ot_mod, "_resolve_dsn", lambda x: "postgresql://fake")
    monkeypatch.setattr(ot_mod, "get_recent_regret_summary", summary_fn)
    return ot_mod


def test_opportunity_tracker_calibrated_replay_path(monkeypatch):
    """provider + experiment_id → 寫 calibrated_replay tier。"""
    import program_code.local_model_tools.opportunity_tracker as ot_mod

    fake_hash = bytes.fromhex("cc" * 32)
    cur = FakeCursor(manifest_hash_bytes=fake_hash)
    conn = FakeConn(cur)

    summary = {
        "rejected_sample_count": 50,
        "avg_regret_bps": -3.5,
    }

    _patch_opp_tracker_dsn(monkeypatch, lambda *a, **k: summary)
    monkeypatch.setattr(
        ot_mod.psycopg2, "connect", lambda *a, **k: conn,
    )

    cal = _calibrated_result()

    def provider(strategy, symbol):
        return cal

    exp_id = "00000000-0000-0000-0000-0000000000aa"

    result = ot_mod.persist_regret_summary(
        engine_mode="demo",
        R6_calibration_provider=provider,
        replay_experiment_id=exp_id,
    )

    assert result["inserted"] == 1
    assert result["calibrated_inserted"] == 1
    assert conn.commit_called

    # cur.execute 預期 2 次
    assert len(cur.execute_calls) == 2
    sql_insert, params_insert = cur.execute_calls[1]
    assert "verify_replay_evidence_and_insert" in sql_insert
    assert params_insert[5] == "calibrated_replay"  # tier (對應 sql 第 12 個 % 是 tier)
    # opportunity_tracker SQL params 順序：
    # (engine_mode, expected_bps, confidence, sample_count, payload,
    #  tier, replay_exp_id, hash_hex, expires_at)
    assert params_insert[6] == exp_id
    assert params_insert[7] == "cc" * 32
    assert isinstance(params_insert[8], datetime)


def test_opportunity_tracker_no_provider_fallback(monkeypatch):
    """不傳 provider → real_outcome backward-compat。"""
    import program_code.local_model_tools.opportunity_tracker as ot_mod

    cur = FakeCursor()
    conn = FakeConn(cur)

    summary = {
        "rejected_sample_count": 50,
        "avg_regret_bps": -3.5,
    }

    _patch_opp_tracker_dsn(monkeypatch, lambda *a, **k: summary)
    monkeypatch.setattr(
        ot_mod.psycopg2, "connect", lambda *a, **k: conn,
    )

    result = ot_mod.persist_regret_summary(engine_mode="demo")

    assert result["inserted"] == 1
    # backward-compat: 沒 R7-only key
    assert "calibrated_inserted" not in result

    insert_calls = [
        (sql, params) for sql, params in cur.execute_calls
        if "verify_replay_evidence_and_insert" in sql
    ]
    assert len(insert_calls) == 1
    _, params = insert_calls[0]
    # 第 6 個 = tier='real_outcome'
    assert params[5] == "real_outcome"
    assert params[6] is None  # replay_experiment_id
    assert params[7] is None  # manifest_hash
    assert params[8] is None  # expires_at


# ─────────────────────────────────────────────────────────────────────
# mlde_shadow_advisor._persist_recommendations tests
# ─────────────────────────────────────────────────────────────────────


def _make_shadow_recommendation():
    """構造測試 ShadowRecommendation。"""
    from program_code.ml_training.mlde_shadow_advisor import ShadowRecommendation

    return ShadowRecommendation(
        engine_mode="demo",
        source="ml_shadow",
        recommendation_type="rank",
        strategy_name="grid_trading",
        symbol="BTCUSDT",
        expected_net_bps=4.5,
        confidence=0.75,
        sample_count=500,
        payload={"rank_top_k": 3},
    )


def test_mlde_shadow_advisor_calibrated_replay_path(monkeypatch):
    """provider + experiment_id_provider → 寫 calibrated_replay tier。"""
    import program_code.ml_training.mlde_shadow_advisor as msa_mod

    fake_hash = bytes.fromhex("dd" * 32)
    cur = FakeCursor(manifest_hash_bytes=fake_hash)
    conn = FakeConn(cur)

    monkeypatch.setattr(
        msa_mod.psycopg2, "connect", lambda *a, **k: conn,
    )

    rec = _make_shadow_recommendation()
    cal = _calibrated_result()

    def cal_provider(strategy, symbol):
        return cal

    def exp_id_provider(rec):
        return "00000000-0000-0000-0000-0000000000bb"

    inserted = msa_mod._persist_recommendations(
        "postgresql://fake",
        [rec],
        R6_calibration_provider=cal_provider,
        replay_experiment_id_provider=exp_id_provider,
    )

    assert inserted == 1
    # 2 execute call: SELECT V049 + V036 INSERT
    assert len(cur.execute_calls) == 2

    sql_insert, params_insert = cur.execute_calls[1]
    assert "verify_replay_evidence_and_insert" in sql_insert
    # mlde_shadow_advisor params 順序：
    # (engine_mode, symbol, strategy, source, rec_type, expected_bps,
    #  confidence, sample_count, payload, tier, exp_id, hash_hex, expires_at)
    assert params_insert[9] == "calibrated_replay"
    assert params_insert[10] == "00000000-0000-0000-0000-0000000000bb"
    assert params_insert[11] == "dd" * 32


def test_mlde_shadow_advisor_no_provider_fallback(monkeypatch):
    """不傳 provider → real_outcome backward-compat。"""
    import program_code.ml_training.mlde_shadow_advisor as msa_mod

    cur = FakeCursor()
    conn = FakeConn(cur)
    monkeypatch.setattr(
        msa_mod.psycopg2, "connect", lambda *a, **k: conn,
    )

    rec = _make_shadow_recommendation()
    inserted = msa_mod._persist_recommendations("postgresql://fake", [rec])

    assert inserted == 1
    insert_calls = [
        (sql, params) for sql, params in cur.execute_calls
        if "verify_replay_evidence_and_insert" in sql
    ]
    assert len(insert_calls) == 1
    _, params = insert_calls[0]
    # tier 'real_outcome' + metadata 全 None
    assert params[9] == "real_outcome"
    assert params[10] is None
    assert params[11] is None
    assert params[12] is None


def test_mlde_shadow_advisor_none_label_skips_rec(monkeypatch):
    """provider 回 NONE label → skip 此 rec，0 INSERT。"""
    import program_code.ml_training.mlde_shadow_advisor as msa_mod

    cur = FakeCursor(manifest_hash_bytes=bytes.fromhex("ee" * 32))
    conn = FakeConn(cur)
    monkeypatch.setattr(
        msa_mod.psycopg2, "connect", lambda *a, **k: conn,
    )

    rec = _make_shadow_recommendation()
    cal_none = _calibrated_result(
        label=ExecutionConfidence.NONE, ttl_days=0, sample_count=0,
    )

    def cal_provider(strategy, symbol):
        return cal_none

    def exp_id_provider(rec):
        return "00000000-0000-0000-0000-0000000000cc"

    inserted = msa_mod._persist_recommendations(
        "postgresql://fake",
        [rec],
        R6_calibration_provider=cal_provider,
        replay_experiment_id_provider=exp_id_provider,
    )

    # 0 INSERT；rec 被 skip
    assert inserted == 0
    insert_count = sum(
        1 for sql, _ in cur.execute_calls
        if "verify_replay_evidence_and_insert" in sql
    )
    assert insert_count == 0
