"""Tests for DL-3 foundation model wrapper.
DL-3 基礎模型包裝器測試。

Verifies fail-soft behavior across 6+ failure modes — wrapper must NEVER raise.
驗證 6+ 種失敗模式下的 fail-soft 行為 — wrapper 絕不拋異常。
"""

from __future__ import annotations

import asyncio
import time

import pytest

from ml_training.dl3_foundation import (
    Dl3Config,
    Dl3ForecastResult,
    _clear_predictor_cache,
    _inject_predictor_for_testing,
    run_forecast,
)


def _run(coro):
    """Helper: run coroutine to completion (avoids pytest-asyncio dep).
    輔助函式：跑 coroutine（避免依賴 pytest-asyncio）。
    """
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset predictor cache between tests / 測試間清快取。"""
    _clear_predictor_cache()
    yield
    _clear_predictor_cache()


# ---------------------------------------------------------------------------
# 1. Unavailable model -> fail-soft / 不可用模型 → fail-soft
# ---------------------------------------------------------------------------
def test_run_forecast_unavailable_model_returns_fail_soft():
    cfg = Dl3Config(model_name="__unavailable__")
    result = _run(
        run_forecast(cfg, "BTCUSDT", [1.0, 2.0, 3.0], timestamp_ms=1_700_000_000_000)
    )
    assert isinstance(result, Dl3ForecastResult)
    assert result.ok is False
    assert result.error_msg == "model_unavailable"
    assert result.pred_mean == []


# ---------------------------------------------------------------------------
# 2. Timeout -> fail-soft / 超時 → fail-soft
# ---------------------------------------------------------------------------
def test_run_forecast_timeout_returns_fail_soft():
    def _slow_predictor(history, horizon):
        time.sleep(10)
        return {"pred_mean": [0.0] * horizon, "pred_std": None}

    _inject_predictor_for_testing("fake-slow", _slow_predictor)
    cfg = Dl3Config(model_name="fake-slow", timeout_seconds=1)
    result = _run(
        run_forecast(cfg, "BTCUSDT", [1.0, 2.0, 3.0], timestamp_ms=1_700_000_000_000)
    )
    assert result.ok is False
    assert result.error_msg == "timeout"


# ---------------------------------------------------------------------------
# 3. Inference exception -> fail-soft / 推理異常 → fail-soft
# ---------------------------------------------------------------------------
def test_run_forecast_inference_exception_returns_fail_soft():
    def _bad_predictor(history, horizon):
        raise RuntimeError("simulated model crash")

    _inject_predictor_for_testing("fake-bad", _bad_predictor)
    cfg = Dl3Config(model_name="fake-bad")
    result = _run(
        run_forecast(cfg, "ETHUSDT", [1.0, 2.0], timestamp_ms=1_700_000_000_000)
    )
    assert result.ok is False
    assert result.error_msg is not None
    assert "inference_error" in result.error_msg
    assert "simulated model crash" in result.error_msg


# ---------------------------------------------------------------------------
# 4. Default config values / 預設配置值
# ---------------------------------------------------------------------------
def test_dl3_config_defaults():
    cfg = Dl3Config(model_name="chronos-t5-tiny")
    assert cfg.horizon_minutes == 60
    assert cfg.timeout_seconds == 300
    assert cfg.batch_size == 1


# ---------------------------------------------------------------------------
# 5. Persist skipped when dsn None / 無 dsn 時不寫 DB
# ---------------------------------------------------------------------------
def test_persist_to_db_skipped_when_pool_none():
    def _ok_predictor(history, horizon):
        return {"pred_mean": [1.0] * horizon, "pred_std": [0.1] * horizon}

    _inject_predictor_for_testing("fake-ok", _ok_predictor)
    cfg = Dl3Config(model_name="fake-ok", horizon_minutes=3)
    # dsn=None should not raise, even with no Postgres reachable.
    # dsn=None 時即使無 PG 也不應該拋。
    result = _run(
        run_forecast(
            cfg,
            "BTCUSDT",
            [10.0, 11.0, 12.0, 13.0],
            timestamp_ms=1_700_000_000_000,
            dsn=None,
        )
    )
    assert result.ok is True
    assert len(result.pred_mean) == 3
    assert result.pred_std is not None and len(result.pred_std) == 3


# ---------------------------------------------------------------------------
# 6. Fuzz fail-soft contract / 模糊測試 fail-soft 契約
# ---------------------------------------------------------------------------
def test_run_forecast_does_not_raise_on_any_error():
    """Throw a variety of inputs at the wrapper; it must always return a result.
    向 wrapper 投擲各種輸入；必須永遠返回結果而非拋異常。
    """

    def _picky_predictor(history, horizon):
        if not history:
            raise ValueError("empty history")
        if any(h < 0 for h in history):
            raise ArithmeticError("negative price")
        if horizon <= 0:
            raise ValueError("bad horizon")
        return {"pred_mean": [sum(history) / len(history)] * horizon, "pred_std": None}

    _inject_predictor_for_testing("fake-picky", _picky_predictor)

    fuzz_cases: list[tuple[list[float], int]] = [
        ([], 5),
        ([-1.0, -2.0], 5),
        ([1.0, 2.0, 3.0], 0),
        ([1.0, 2.0, 3.0], 5),  # only one that should succeed
        ([float("nan")], 5),
    ]

    for hist, horizon in fuzz_cases:
        cfg = Dl3Config(model_name="fake-picky", horizon_minutes=horizon)
        result = _run(
            run_forecast(cfg, "BTCUSDT", hist, timestamp_ms=1_700_000_000_000)
        )
        assert isinstance(result, Dl3ForecastResult)
        # Wrapper must always return; ok may be True or False.
        # Wrapper 必須永遠返回；ok 可 True 或 False。
        assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# 7. Bonus: persist swallows DB errors when dsn is bad / 壞 dsn 仍 fail-soft
# ---------------------------------------------------------------------------
def test_persist_swallows_bad_dsn():
    def _ok_predictor(history, horizon):
        return {"pred_mean": [1.0] * horizon, "pred_std": None}

    _inject_predictor_for_testing("fake-ok2", _ok_predictor)
    cfg = Dl3Config(model_name="fake-ok2", horizon_minutes=2)
    # Intentionally broken DSN — must not raise. / 故意壞掉的 dsn — 不應拋。
    result = _run(
        run_forecast(
            cfg,
            "BTCUSDT",
            [1.0, 2.0],
            timestamp_ms=1_700_000_000_000,
            dsn="postgresql://nobody:nopass@127.0.0.1:1/none",
        )
    )
    assert result.ok is True
    assert len(result.pred_mean) == 2
