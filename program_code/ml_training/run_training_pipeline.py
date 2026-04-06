"""End-to-end training pipeline orchestrator.
端到端訓練管線編排器。

MODULE_NOTE (EN): P1-3 stub that wires ETL → label generation → CPCV-validated
  scorer training → calibration → ONNX export → registry write. Each step is
  callable individually for debugging; `run_pipeline()` runs them in sequence.
  Currently skips ONNX export (ort integration deferred) and relies on
  model.pkl/metrics.json artifacts.
MODULE_NOTE (中): P1-3 存根，串接 ETL → 標籤生成 → CPCV 驗證評分器訓練
  → 校準 → ONNX 導出 → 註冊表寫入。每一步可單獨呼叫用於除錯。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """End-to-end training pipeline configuration.
    端到端訓練管線配置。"""

    strategy_type: str = "trending"
    symbol: str = "BTCUSDT"
    regime: str = "trending"
    output_dir: str = "/tmp/openclaw/models"
    dsn: Optional[str] = None  # PostgreSQL DSN for ETL + posteriors persistence
    min_samples: int = 200
    dry_run: bool = False
    skip_onnx: bool = True  # ort integration deferred (Phase 4)


@dataclass
class PipelineResult:
    """Result of a pipeline run.
    管線執行結果。"""

    success: bool = False
    stages_completed: list[str] = field(default_factory=list)
    model_path: str = ""
    metrics: dict = field(default_factory=dict)
    error: str = ""


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Run the full training pipeline end-to-end.
    端到端執行訓練管線。

    Stages:
        1. ETL: load features + labels from PG or Parquet
        2. Label gen: compute ATR-normalized PnL labels
        3. CPCV training: scorer_trainer.train_scorer with timestamps
        4. Calibration: (placeholder — Platt/isotonic not yet implemented)
        5. Persistence: write model.pkl + metrics.json
        6. Posteriors: flush Thompson Sampling posteriors to PG
    """
    result = PipelineResult()
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Stage 1: ETL
        logger.info("[pipeline] stage 1: ETL")
        try:
            import numpy as np
        except ImportError:
            result.error = "numpy required"
            return result

        if config.dry_run:
            # Generate synthetic data for smoke-test / 為煙霧測試生成合成資料
            n = 200  # fixed synthetic size — min_samples enforced below
            rng = np.random.default_rng(42)
            features = rng.standard_normal((n, 8))
            labels = features[:, 0] * 0.1 + rng.standard_normal(n) * 0.05
            timestamps = np.arange(n, dtype=np.int64) * 60_000  # 1-minute bars
            feature_names = [f"f{i}" for i in range(8)]
        else:
            from ml_training.parquet_etl import load_training_data
            features, labels, timestamps, feature_names = load_training_data(
                symbol=config.symbol,
                strategy_type=config.strategy_type,
                dsn=config.dsn,
            )

        if len(labels) < config.min_samples:
            result.error = (
                f"insufficient samples: {len(labels)} < {config.min_samples}"
            )
            logger.warning(result.error)
            return result
        result.stages_completed.append("etl")

        # Stage 2: Label generation (already included in ETL output)
        result.stages_completed.append("labels")

        # Stage 3: CPCV training
        logger.info("[pipeline] stage 3: CPCV training")
        from ml_training.scorer_trainer import ScorerConfig, train_scorer

        scorer_cfg = ScorerConfig(output_dir=str(output_dir))
        train_result = train_scorer(
            features=features,
            labels=labels,
            feature_names=feature_names,
            config=scorer_cfg,
            timestamps=timestamps,
            strategy_type=config.strategy_type,
        )
        if not train_result.success:
            result.error = f"training failed: {train_result.error}"
            return result
        result.stages_completed.append("cpcv_training")
        result.model_path = train_result.model_path
        result.metrics.update(train_result.metrics)

        # Stage 4: Calibration (placeholder)
        logger.info("[pipeline] stage 4: calibration (placeholder)")
        result.stages_completed.append("calibration_skipped")

        # Stage 5: Persistence
        metrics_path = output_dir / "metrics.json"
        metrics_path.write_text(json.dumps(result.metrics, indent=2))
        result.stages_completed.append("persistence")

        # Stage 6: ONNX export (deferred)
        if not config.skip_onnx:
            logger.warning("ONNX export requested but not implemented — skipping")
        result.stages_completed.append("onnx_skipped")

        result.success = True
        logger.info(
            "[pipeline] complete: stages=%s metrics=%s",
            result.stages_completed, result.metrics,
        )
    except Exception as e:  # noqa: BLE001
        result.error = str(e)
        logger.exception("pipeline failed")

    return result


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--strategy", default="trending")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--output", default="/tmp/openclaw/models")
    args = ap.parse_args()

    cfg = PipelineConfig(
        strategy_type=args.strategy,
        symbol=args.symbol,
        output_dir=args.output,
        dry_run=args.dry_run,
    )
    res = run_pipeline(cfg)
    print(json.dumps({
        "success": res.success,
        "stages": res.stages_completed,
        "error": res.error,
        "metrics": res.metrics,
    }, indent=2))
