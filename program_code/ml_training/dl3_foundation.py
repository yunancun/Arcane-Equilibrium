"""DL-3 Foundation Model wrapper — TimesFM / Chronos zero-shot async inference.

DL-3 基礎模型包裝器 — TimesFM / Chronos zero-shot 異步推理。

MODULE_NOTE (EN):
    Async wrapper that runs zero-shot inference using time-series foundation
    models (TimesFM, Chronos). Does NOT block the trading hot path:
    - Inference runs in a thread pool / asyncio task
    - 5-minute timeout per call -> graceful degradation (log + skip)
    - Model load failure -> fail-soft (no exception propagation)
    - Results written to learning.foundation_model_features for later A/B (4-12)

MODULE_NOTE (中):
    異步包裝器，使用時序基礎模型（TimesFM、Chronos）跑 zero-shot 推理。
    不阻塞交易主路徑：
    - 推理在 thread pool / asyncio task 中跑
    - 每次呼叫 5 分鐘超時 → 優雅降級（log + 跳過）
    - 模型載入失敗 → fail-soft（不向上傳播異常）
    - 結果寫入 learning.foundation_model_features 供後續 A/B（4-12）使用

Spec source / 規格來源:
    docs/references/2026-04-06--phase4_execution_plan_v2.md §4-11
    docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md DL-3
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants / 常數
# ---------------------------------------------------------------------------
_UNAVAILABLE_SENTINEL = "__unavailable__"
_DEFAULT_HORIZON_MIN = 60
_DEFAULT_TIMEOUT_S = 300
_DEFAULT_BATCH_SIZE = 1


# ---------------------------------------------------------------------------
# Configuration / 配置
# ---------------------------------------------------------------------------
@dataclass
class Dl3Config:
    """Configuration for DL-3 foundation model inference.
    DL-3 基礎模型推理配置。

    Attributes:
        model_name: HuggingFace / package model identifier, or
                    '__unavailable__' to short-circuit. / 模型識別碼，或
                    '__unavailable__' 短路。
        horizon_minutes: Forecast horizon in minutes. / 預測時程（分鐘）。
        timeout_seconds: Per-call inference timeout. / 單次推理超時秒數。
        batch_size: Batch size for inference. / 推理 batch 大小。
    """

    model_name: str
    horizon_minutes: int = _DEFAULT_HORIZON_MIN
    timeout_seconds: int = _DEFAULT_TIMEOUT_S
    batch_size: int = _DEFAULT_BATCH_SIZE


@dataclass
class Dl3ForecastResult:
    """Result of a single forecast call. Always returned, never raised.
    單次預測結果。永遠返回，絕不拋出。

    Attributes:
        ok: Whether inference succeeded. / 推理是否成功。
        pred_mean: Forecast mean per horizon step (empty on failure). /
                   每步預測均值（失敗時為空）。
        pred_std: Optional forecast std per horizon step. / 每步預測標準差。
        latency_ms: Wall-clock inference latency in ms. / 推理墻鐘延遲（毫秒）。
        error_msg: Failure reason; None on success. / 失敗原因，成功為 None。
    """

    ok: bool
    pred_mean: list[float] = field(default_factory=list)
    pred_std: Optional[list[float]] = None
    latency_ms: int = 0
    error_msg: Optional[str] = None


# ---------------------------------------------------------------------------
# Lazy model loader cache / 惰性模型載入快取
# ---------------------------------------------------------------------------
# Cache resolved (predict_fn or None) per model_name to avoid repeated import.
# 每個 model_name 快取已解析的 predict_fn 或 None，避免重複 import。
_MODEL_CACHE: dict[str, Optional[Callable[[list[float], int], dict[str, list[float]]]]] = {}


def _resolve_predictor(
    model_name: str,
) -> Optional[Callable[[list[float], int], dict[str, list[float]]]]:
    """Lazily import & wrap a foundation model into a uniform predict callable.
    惰性匯入並把基礎模型包成統一的 predict callable。

    Returns None if the model package is not installed (fail-soft).
    若套件未安裝則返回 None（fail-soft）。

    Contract / 契約: predict_fn(history: list[float], horizon: int)
        -> {"pred_mean": list[float], "pred_std": list[float] | None}
    """
    if model_name == _UNAVAILABLE_SENTINEL:
        return None

    if model_name in _MODEL_CACHE:
        return _MODEL_CACHE[model_name]

    predictor: Optional[Callable[[list[float], int], dict[str, list[float]]]] = None

    # --- Chronos branch / Chronos 分支 -----------------------------------
    if "chronos" in model_name.lower():
        try:
            from chronos import ChronosPipeline  # type: ignore
            import torch  # type: ignore

            pipeline = ChronosPipeline.from_pretrained(model_name)

            def _chronos_predict(
                history: list[float], horizon: int
            ) -> dict[str, list[float]]:
                ctx = torch.tensor(history)
                forecast = pipeline.predict(ctx, prediction_length=horizon)
                # forecast shape [num_samples, horizon] -> mean/std along samples
                arr = forecast[0].numpy()
                pred_mean = arr.mean(axis=0).tolist()
                pred_std = arr.std(axis=0).tolist()
                return {"pred_mean": pred_mean, "pred_std": pred_std}

            predictor = _chronos_predict
        except ImportError:
            logger.warning(
                "chronos package not installed; DL-3 model %s unavailable "
                "(chronos 套件未安裝；DL-3 模型 %s 不可用)",
                model_name,
                model_name,
            )
            predictor = None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("chronos load failed: %s", exc)
            predictor = None

    # --- TimesFM branch / TimesFM 分支 -----------------------------------
    elif "timesfm" in model_name.lower():
        try:
            import timesfm  # type: ignore

            tfm = timesfm.TimesFm(
                context_len=512,
                horizon_len=_DEFAULT_HORIZON_MIN,
                input_patch_len=32,
                output_patch_len=128,
                num_layers=20,
                model_dims=1280,
                backend="cpu",
            )
            tfm.load_from_checkpoint(repo_id=model_name)

            def _timesfm_predict(
                history: list[float], horizon: int
            ) -> dict[str, list[float]]:
                point_forecast, _ = tfm.forecast([history], freq=[0])
                pred_mean = list(map(float, point_forecast[0][:horizon]))
                return {"pred_mean": pred_mean, "pred_std": None}

            predictor = _timesfm_predict
        except ImportError:
            logger.warning(
                "timesfm package not installed; DL-3 model %s unavailable "
                "(timesfm 套件未安裝；DL-3 模型 %s 不可用)",
                model_name,
                model_name,
            )
            predictor = None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("timesfm load failed: %s", exc)
            predictor = None
    else:
        logger.warning(
            "Unknown DL-3 model family: %s (must contain 'chronos' or 'timesfm') "
            "(未知 DL-3 模型族：%s)",
            model_name,
            model_name,
        )
        predictor = None

    _MODEL_CACHE[model_name] = predictor
    return predictor


# Allow tests to inject a fake predictor without touching the real loader.
# 測試可注入假 predictor，不觸及真實 loader。
def _inject_predictor_for_testing(
    model_name: str,
    predict_fn: Optional[Callable[[list[float], int], dict[str, list[float]]]],
) -> None:
    """Test hook: register a fake predictor under model_name.
    測試鉤子：以 model_name 註冊假的 predictor。
    """
    _MODEL_CACHE[model_name] = predict_fn


def _clear_predictor_cache() -> None:
    """Test hook: clear the lazy predictor cache.
    測試鉤子：清空惰性 predictor 快取。
    """
    _MODEL_CACHE.clear()


# ---------------------------------------------------------------------------
# Persistence / 持久化
# ---------------------------------------------------------------------------
def _persist_to_db(
    dsn: str,
    *,
    timestamp_ms: int,
    symbol: str,
    cfg: Dl3Config,
    result: Dl3ForecastResult,
) -> None:
    """Best-effort write to learning.foundation_model_features.
    盡力寫入 learning.foundation_model_features。

    Errors are logged and swallowed — never propagate to caller.
    錯誤僅 log 並吞掉，絕不向上拋出。
    """
    try:
        import psycopg2  # type: ignore
    except ImportError:
        logger.warning(
            "psycopg2 not installed; DL-3 result not persisted "
            "(psycopg2 未安裝，DL-3 結果未持久化)"
        )
        return

    try:
        ts = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        forecast_payload = {
            "pred_mean": result.pred_mean,
            "pred_std": result.pred_std,
        }
        conn = psycopg2.connect(dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO learning.foundation_model_features
                        (time, symbol, model, horizon_min, forecast,
                         latency_ms, ok, error_msg)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                    """,
                    (
                        ts,
                        symbol,
                        cfg.model_name,
                        cfg.horizon_minutes,
                        json.dumps(forecast_payload),
                        result.latency_ms,
                        result.ok,
                        result.error_msg,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(
            "DL-3 persist failed (swallowed): %s "
            "(DL-3 持久化失敗，已吞掉)",
            exc,
        )


# ---------------------------------------------------------------------------
# Public async API / 公開異步 API
# ---------------------------------------------------------------------------
async def run_forecast(
    cfg: Dl3Config,
    symbol: str,
    history_close: list[float],
    timestamp_ms: int,
    dsn: Optional[str] = None,
) -> Dl3ForecastResult:
    """Run zero-shot forecast. Fail-soft on any error.
    跑 zero-shot 預測。任何錯誤都 fail-soft。

    Steps / 步驟:
        1. Lazy import model (chronos / timesfm may not be installed).
           惰性匯入模型（chronos / timesfm 可能未安裝）。
        2. Run inference in thread pool with timeout.
           於 thread pool 中以超時執行推理。
        3. Persist to learning.foundation_model_features if dsn given.
           若提供 dsn 則寫入 learning.foundation_model_features。
        4. Return Dl3ForecastResult — never raise.
           返回 Dl3ForecastResult — 絕不拋異常。

    Args:
        cfg: Model configuration. / 模型配置。
        symbol: Trading symbol. / 交易品種。
        history_close: Historical close prices. / 歷史收盤序列。
        timestamp_ms: Wall-clock timestamp for the forecast row. /
                      預測行的墻鐘時間戳。
        dsn: Optional Postgres DSN; persist when provided. /
             可選 Postgres DSN；提供時持久化。

    Returns:
        Dl3ForecastResult — always populated, never raises.
    """
    start = time.monotonic()
    result: Dl3ForecastResult

    try:
        predictor = _resolve_predictor(cfg.model_name)
        if predictor is None:
            result = Dl3ForecastResult(
                ok=False,
                latency_ms=int((time.monotonic() - start) * 1000),
                error_msg="model_unavailable",
            )
        else:
            try:
                loop = asyncio.get_running_loop()
                fut = loop.run_in_executor(
                    None,
                    predictor,
                    list(history_close),
                    cfg.horizon_minutes,
                )
                payload = await asyncio.wait_for(fut, timeout=cfg.timeout_seconds)
                pred_mean = list(map(float, payload.get("pred_mean") or []))
                raw_std = payload.get("pred_std")
                pred_std = list(map(float, raw_std)) if raw_std is not None else None
                result = Dl3ForecastResult(
                    ok=True,
                    pred_mean=pred_mean,
                    pred_std=pred_std,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    error_msg=None,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "DL-3 inference timeout for %s on %s "
                    "(DL-3 推理超時)",
                    cfg.model_name,
                    symbol,
                )
                result = Dl3ForecastResult(
                    ok=False,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    error_msg="timeout",
                )
            except Exception as exc:
                logger.warning(
                    "DL-3 inference exception for %s on %s: %s "
                    "(DL-3 推理異常)",
                    cfg.model_name,
                    symbol,
                    exc,
                )
                result = Dl3ForecastResult(
                    ok=False,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    error_msg=f"inference_error: {exc}",
                )
    except Exception as exc:  # pragma: no cover - ultimate fail-soft
        logger.warning("DL-3 unexpected error (swallowed): %s", exc)
        result = Dl3ForecastResult(
            ok=False,
            latency_ms=int((time.monotonic() - start) * 1000),
            error_msg=f"unexpected: {exc}",
        )

    if dsn is not None:
        _persist_to_db(
            dsn,
            timestamp_ms=timestamp_ms,
            symbol=symbol,
            cfg=cfg,
            result=result,
        )

    return result
