"""End-to-end training pipeline orchestrator.
端到端訓練管線編排器。

MODULE_NOTE (EN): Two paths:
  (A) Legacy regression scorer path (original P1-3 behaviour; CPCV-validated
      LightGBM regression → metrics.json).
  (B) EDGE-P3-1 Stage 2 quantile path (use_quantile_predictor=True):
      ETL → train_quantile_trio → CQR calibration → acceptance report
      → per-quantile ONNX export (gated on verdict ≠ no_ship).
  Each stage is independently callable for debugging.
MODULE_NOTE (中): 兩條路徑：
  (A) 傳統 regression scorer（原 P1-3，CPCV LightGBM → metrics.json）。
  (B) EDGE-P3-1 Stage 2 分位路徑（use_quantile_predictor=True）：
      ETL → train_quantile_trio → CQR → 驗收報告 → per-quantile ONNX 匯出
      （verdict ≠ no_ship 才匯出）。各階段獨立可呼叫便於除錯。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Honour OPENCLAW_DATA_DIR for cross-platform dev (Mac: $HOME/.openclaw_runtime).
# 支援 OPENCLAW_DATA_DIR 跨平台開發（Mac：$HOME/.openclaw_runtime）。
DEFAULT_MODEL_DIR = os.path.join(
    os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"), "models"
)


@dataclass
class PipelineConfig:
    """End-to-end training pipeline configuration.
    端到端訓練管線配置。

    symbol semantics (P1-7 C pooled-training, 2026-04-23):
      - str (e.g. "BTCUSDT"): per-symbol training (future ma/bb path).
      - None or "ALL": pooled across all symbols for this strategy. Use when a
        single symbol cannot reach `min_samples` within a reasonable window
        (e.g. grid_trading rotating across short-lived symbols).

    symbol 語義（P1-7 C pooled-training，2026-04-23）：
      - 具體字串（如 "BTCUSDT"）：逐 symbol 訓練（未來 ma/bb 路徑）。
      - None 或 "ALL"：跨 symbol pooled（grid_trading 類策略輪動 symbol 時使用，
        單一 symbol 無法在合理時間內累積到 min_samples）。

    min_samples 語義（pooled vs per-slice）：
      - pooled 模式：跨所有 symbol 合計 labels 數 ≥ min_samples 即可訓練。
      - per-symbol 模式：該 symbol 單獨的 labels 數 ≥ min_samples 才訓練。
    """

    strategy_type: str = "trending"
    symbol: Optional[str] = None  # None → pooled across all symbols for strategy
    regime: str = "trending"
    output_dir: str = DEFAULT_MODEL_DIR
    dsn: Optional[str] = None  # PostgreSQL DSN for ETL + posteriors persistence
    min_samples: int = 200
    dry_run: bool = False
    skip_onnx: bool = True  # ort integration deferred (Phase 4) — legacy path

    # EDGE-P3-1 Stage 2 branch.
    # When True: route to quantile trio training + CQR + per-quantile ONNX export.
    # When False: legacy regression scorer path (unchanged).
    # EDGE-P3-1 Stage 2 分支；True = 分位路徑，False = 傳統 regression（預設）。
    use_quantile_predictor: bool = False
    engine_mode: str = "demo"
    schema_version: str = "v1"
    onnx_validate_samples: int = 1000  # random vectors for precision gate


@dataclass
class PipelineResult:
    """Result of a pipeline run.
    管線執行結果。"""

    success: bool = False
    stages_completed: List[str] = field(default_factory=list)
    model_path: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    # EDGE-P3-1 Stage 2 extras (populated only in quantile path).
    verdict: str = ""
    acceptance_report_path: str = ""
    onnx_artifacts: Dict[str, Any] = field(default_factory=dict)


def _resolve_symbol_slot(config: PipelineConfig) -> tuple[bool, str]:
    """Resolve (pooled_flag, artifact_symbol_slot) from config.symbol.

    Returns:
      (pooled, slot) where:
        - pooled=True  slot="ALL"        → symbol=None or "ALL" in config
        - pooled=False slot=<symbol>     → per-symbol training

    解析 (pooled_flag, artifact_symbol_slot)：symbol=None/"ALL" → pooled+"ALL"；
    具體字串 → per-symbol + symbol 自身。artifact slot 統一以字串形式向下游
    流（onnx_exporter / model_registry）傳遞，避免 Optional refactor 擴散。
    """
    sym = config.symbol
    if sym is None or (isinstance(sym, str) and sym.upper() == "ALL"):
        return True, "ALL"
    return False, sym


def _load_dataset(
    config: PipelineConfig,
) -> tuple:
    """Load (features, labels, timestamps, feature_names). Shared between paths.
    共用資料載入：回傳 (features, labels, timestamps, feature_names)。"""
    import numpy as np

    if config.dry_run:
        # Synthetic dataset sized to clear min_samples + quantile signal.
        # If quantile path: produce 17 features to match EDGE-P3-1 FeatureVectorV1
        # so the pipeline exercises the real feature-count contract end-to-end.
        # 合成資料：分位路徑產 17 特徵以走完整 FeatureVectorV1 契約。
        n = 600
        rng = np.random.default_rng(42)
        if config.use_quantile_predictor:
            from ml_training.parquet_etl import EDGE_P3_FEATURE_NAMES
            feature_names = list(EDGE_P3_FEATURE_NAMES)
            n_features = len(feature_names)
        else:
            n_features = 8
            feature_names = [f"f{i}" for i in range(n_features)]
        features = rng.standard_normal((n, n_features)).astype(np.float32)
        # Signal: positive drift + first feature drives edge so decile lift > 1.5.
        # 訊號：正漂移 + 首特徵驅動 edge，讓 decile lift > 1.5。
        labels = (
            features[:, 0] * 1.5
            + rng.standard_normal(n) * 0.5
            + 1.0
        ).astype(np.float32)
        # Compressed timestamps (1-minute bars) — holdout split falls back to
        # fractional 20% because total span is < 7d.
        # 壓縮時間戳（1 分鐘）— holdout 因總跨度 <7d 退回 20% 比例切分。
        timestamps = (np.arange(n, dtype=np.int64) * 60_000)
        return features, labels, timestamps, feature_names

    # Resolve pooling: symbol=None or "ALL" → SQL-level symbol filter skipped.
    # Everything else → filter to that exact symbol.
    # 解析 pooling：symbol=None 或 "ALL" → SQL 不加 symbol filter；其他 → 精確過濾。
    pooled, _slot = _resolve_symbol_slot(config)
    sql_symbol: Optional[str] = None if pooled else config.symbol

    if config.use_quantile_predictor:
        from ml_training.parquet_etl import load_training_data
        features, labels, timestamps, feature_names = load_training_data(
            symbol=sql_symbol,
            strategy_type=config.strategy_type,
            dsn=config.dsn,
            engine_mode=config.engine_mode,
        )
    else:
        from ml_training.parquet_etl import load_training_data
        features, labels, timestamps, feature_names = load_training_data(
            symbol=sql_symbol,
            strategy_type=config.strategy_type,
            dsn=config.dsn,
        )

    # Explicit pooled vs per-symbol log line + row count — caller / audit trail
    # reads `[pipeline] dataset_mode=...` to verify the run's slicing decision.
    # Pooled mode additionally emits distinct-symbol count + top-N per-symbol
    # rows so operator can see which symbols dominate the training set.
    # 明確標記 pooled 或 per-symbol 模式 + 樣本數；pooled 額外輸出 distinct
    # symbol 數與 top-N per-symbol 細分，供 operator 檢視主導 symbol 分布。
    if pooled:
        try:
            breakdown = _pooled_symbol_breakdown(
                config=config, engine_mode=config.engine_mode,
            )
        except Exception as e:  # noqa: BLE001 — breakdown is diagnostic-only
            logger.warning("pooled breakdown query failed (non-fatal): %s", e)
            breakdown = []
        distinct = len(breakdown)
        top = ", ".join(f"{s}={n}" for s, n in breakdown[:10])
        logger.info(
            "[pipeline] dataset_mode=pooled strategy=%s engine_mode=%s n_rows=%d "
            "distinct_symbols=%d top=[%s] (symbol filter skipped; cross-symbol aggregate)",
            config.strategy_type, config.engine_mode, len(labels), distinct, top,
        )
    else:
        logger.info(
            "[pipeline] dataset_mode=per_symbol strategy=%s engine_mode=%s "
            "symbol=%s n_rows=%d",
            config.strategy_type, config.engine_mode, sql_symbol, len(labels),
        )
    return features, labels, timestamps, feature_names


def _pooled_symbol_breakdown(
    config: "PipelineConfig",
    engine_mode: str,
    max_age_days: int = 90,
) -> list[tuple[str, int]]:
    """Return [(symbol, labeled_count), ...] desc for the strategy's pooled set.

    Diagnostic-only — failures return [] in the caller. Dry-run or missing DSN
    skips to avoid synthetic-dataset log noise.

    僅供診斷日誌使用；失敗在 caller 端返回 []。dry_run 或無 DSN 時跳過。
    """
    if config.dry_run:
        return []
    from ml_training.parquet_etl import _get_pg_conn
    sql = """
    SELECT symbol, COUNT(*) AS labeled
    FROM learning.decision_features
    WHERE label_net_edge_bps IS NOT NULL
      AND engine_mode = %(engine_mode)s
      AND (%(strategy_name)s IS NULL OR strategy_name = %(strategy_name)s)
      AND ts >= now() - (%(max_age_days)s || ' days')::interval
    GROUP BY symbol
    ORDER BY labeled DESC
    """
    conn = _get_pg_conn(config.dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "engine_mode": engine_mode,
                "strategy_name": config.strategy_type,
                "max_age_days": max_age_days,
            })
            return [(sym, int(n)) for sym, n in cur.fetchall()]
    finally:
        conn.close()


def _run_quantile_pipeline(
    config: PipelineConfig,
    features, labels, timestamps, feature_names,
) -> PipelineResult:
    """EDGE-P3-1 Stage 2 quantile path end-to-end.
    EDGE-P3-1 Stage 2 分位路徑端到端。"""
    import numpy as np
    from ml_training.quantile_trainer import (
        QuantileTrainingConfig,
        train_quantile_trio,
    )
    from ml_training.calibration import fit_cqr_trio, evaluate_cqr_coverage
    from ml_training.quantile_reports import (
        VERDICT_NO_SHIP,
        generate_acceptance_report,
    )
    from ml_training.onnx_exporter import export_quantile_trio_to_onnx

    result = PipelineResult()
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # P1-7 C pooled vs per-symbol — drive filename slots + metrics annotations.
    # P1-7 C：解析 pooled / per-symbol；供 acceptance report 檔名 + 指標標記。
    pooled, symbol_slot = _resolve_symbol_slot(config)

    qcfg = QuantileTrainingConfig(schema_version=config.schema_version)

    # Stage 2: train q10/q50/q90.
    train_result = train_quantile_trio(
        features=features,
        labels=labels,
        timestamps_ms=timestamps,
        feature_names=feature_names,
        strategy_name=config.strategy_type,
        engine_mode=config.engine_mode,
        config=qcfg,
    )
    if not train_result.success:
        result.error = f"quantile training failed: {train_result.error}"
        return result
    result.stages_completed.append("quantile_train")

    # Stage 3: CQR calibration on holdout.
    cqr_offsets = fit_cqr_trio(
        train_result.holdout_labels,
        train_result.holdout_q10_pred,
        train_result.holdout_q50_pred,
        train_result.holdout_q90_pred,
    )
    post_coverage = evaluate_cqr_coverage(
        train_result.holdout_labels,
        train_result.holdout_q10_pred,
        train_result.holdout_q50_pred,
        train_result.holdout_q90_pred,
        cqr_offsets,
    )
    result.stages_completed.append("cqr_calibration")

    # Stage 4: acceptance report.
    # Filename includes symbol_slot so pooled ("ALL") vs per-symbol runs don't
    # overwrite each other's acceptance report on the same output_dir.
    # 檔名含 symbol_slot：pooled ("ALL") 與 per-symbol 報告可在同一 output_dir 共存。
    report_path = (
        output_dir
        / f"{config.strategy_type}_{config.engine_mode}_{symbol_slot}_acceptance_report.json"
    )
    report = generate_acceptance_report(
        train_result, qcfg,
        cqr_offsets=cqr_offsets,
        post_cqr_coverage=post_coverage,
        output_path=str(report_path),
        harness_n_samples=config.onnx_validate_samples,
    )
    result.stages_completed.append("acceptance_report")
    result.verdict = report.get("verdict", "")
    result.acceptance_report_path = str(report_path)

    # Stage 5: ONNX export — gate on verdict ≠ no_ship.
    # shadow_only still emits ONNX so Rust can wire shadow inference.
    # shadow_only 仍匯出以讓 Rust 側接 shadow 推理。
    if result.verdict == VERDICT_NO_SHIP:
        result.stages_completed.append("onnx_export_skipped_no_ship")
        result.success = True
        return result

    # Build 1000 random vector sample for precision gate (reuse harness seed).
    # 產 1000 random vector 供精度 gate（重用 harness seed）。
    rng = np.random.default_rng(1337)
    validate_samples = rng.uniform(
        -3.0, 3.0, size=(config.onnx_validate_samples, len(feature_names)),
    ).astype(np.float32)
    onnx_out = export_quantile_trio_to_onnx(
        models=train_result.models,
        output_dir=str(output_dir),
        engine_mode=config.engine_mode,
        strategy_name=config.strategy_type,
        n_features=len(feature_names),
        schema_version=config.schema_version,
        validate_samples=validate_samples,
        feature_schema_hash=train_result.feature_schema_hash,
        # Stage 0: definition hash aliases schema hash (spec §3.3). If/when
        # definitions drift, trainer starts emitting a distinct value and this
        # call site needs no change.
        # Stage 0：definition hash 與 schema hash 同值；將來公式漂移時 trainer 自動分叉。
        feature_definition_hash=train_result.feature_schema_hash,
    )
    result.onnx_artifacts = onnx_out
    result.stages_completed.append("onnx_export")

    # Stage 5.5: Register ONNX artifacts in learning.model_registry (V023).
    # INFRA-PREBUILD-1 Part B (2026-04-23): persist artifact path + verdict +
    # acceptance report JSONB + provenance hashes so Rust OnnxModelManager can
    # query "latest production model for this slot" from DB instead of relying
    # solely on the filesystem `_current` symlink. Skipped when DB unavailable
    # or verdict=no_ship (registry stays clean of unshippable models).
    # INFRA-PREBUILD-1 B 部：寫 learning.model_registry，讓 Rust OnnxModelManager
    # 可以查 DB 取「這個 slot 的 latest production model」，不必只依賴 _current
    # symlink。DB 不可用或 verdict=no_ship 時跳過。
    try:
        from ml_training.model_registry import register_quantile_trio_from_onnx_out
        registry_ids = register_quantile_trio_from_onnx_out(
            onnx_out=onnx_out,
            strategy=config.strategy_type,
            engine_mode=config.engine_mode,
            schema_version=config.schema_version,
            verdict=result.verdict,
            acceptance_report_path=result.acceptance_report_path,
            feature_schema_hash=train_result.feature_schema_hash,
            training_sample_size=train_result.n_samples_labeled,
            dsn=config.dsn,
        )
        if registry_ids:
            result.stages_completed.append(f"model_registry_wrote_{len(registry_ids)}")
        else:
            result.stages_completed.append("model_registry_skipped")
    except Exception as e:  # noqa: BLE001 — registry write is audit-only
        logger.warning("model_registry write failed (non-fatal): %s", e)
        result.stages_completed.append("model_registry_error")

    # Stage 6: summary metrics for pipeline consumer.
    # pooled / symbol_slot 直接進 metrics JSON，acceptance report 檔名也帶 slot。
    result.metrics = {
        "verdict": result.verdict,
        "n_samples_labeled": train_result.n_samples_labeled,
        "n_holdout": train_result.n_holdout,
        "pinball_skill_q10": train_result.per_quantile_metrics["q10"].pinball_skill,
        "pinball_skill_q50": train_result.per_quantile_metrics["q50"].pinball_skill,
        "pinball_skill_q90": train_result.per_quantile_metrics["q90"].pinball_skill,
        "crossing_rate": train_result.crossing_rate,
        "decile_lift_point": train_result.decile_lift_point,
        "decile_lift_ci_lower": train_result.decile_lift_ci_lower,
        "feature_schema_hash": train_result.feature_schema_hash,
        "pooled": pooled,
        "symbol_slot": symbol_slot,
    }
    result.success = True
    return result


def _run_legacy_scorer_pipeline(
    config: PipelineConfig,
    features, labels, timestamps, feature_names,
) -> PipelineResult:
    """Original regression scorer path (unchanged from P1-3).
    傳統 regression scorer 路徑（P1-3 行為不變）。"""
    result = PipelineResult()
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

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

    # P1-7 C: tag legacy-path metrics with pooled / symbol_slot too, for audit
    # parity with quantile path (same operator CLI + same metrics.json shape).
    # 傳統路徑同樣標記 pooled / symbol_slot，維持與分位路徑的審計一致性。
    _pooled, _slot = _resolve_symbol_slot(config)
    result.metrics["pooled"] = _pooled
    result.metrics["symbol_slot"] = _slot

    result.stages_completed.append("calibration_skipped")

    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(result.metrics, indent=2))
    result.stages_completed.append("persistence")

    if not config.skip_onnx:
        logger.warning("ONNX export requested but not implemented — skipping")
    result.stages_completed.append("onnx_skipped")

    result.success = True
    return result


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Run training pipeline end-to-end; routes to quantile or legacy path.
    端到端執行；依 config.use_quantile_predictor 路由。"""
    result = PipelineResult()

    try:
        logger.info(
            "[pipeline] start: strategy=%s engine=%s quantile=%s dry_run=%s",
            config.strategy_type, config.engine_mode,
            config.use_quantile_predictor, config.dry_run,
        )
        features, labels, timestamps, feature_names = _load_dataset(config)
        result.stages_completed.append("etl")
        # Legacy audit-trail convention: labels stage is reported separately
        # even when label computation happens inside the ETL query. Keep for
        # downstream monitoring that greps stages_completed.
        # 傳統審計軌跡：labels 階段單獨報告（即便 label 在 ETL SQL 內完成）。
        result.stages_completed.append("labels")

        if len(labels) < config.min_samples:
            result.error = f"insufficient samples: {len(labels)} < {config.min_samples}"
            logger.warning(result.error)
            return result

        if config.use_quantile_predictor:
            inner = _run_quantile_pipeline(config, features, labels, timestamps, feature_names)
        else:
            inner = _run_legacy_scorer_pipeline(config, features, labels, timestamps, feature_names)

        # Merge inner into outer keeping etl + labels stages first.
        inner.stages_completed = ["etl", "labels"] + inner.stages_completed
        logger.info(
            "[pipeline] complete: success=%s stages=%s verdict=%s",
            inner.success, inner.stages_completed, inner.verdict,
        )
        return inner
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
    ap.add_argument(
        "--symbol",
        default=None,
        help=(
            "Symbol filter for training data. Omit or pass 'ALL' to pool all "
            "symbols for the strategy (recommended for grid_trading which "
            "rotates across short-lived symbols). Specify e.g. 'BTCUSDT' for "
            "per-symbol training. Default = pooled. "
            "省略或 'ALL' = 跨 symbol pooled（grid_trading 建議）；具體 symbol = 逐 symbol 訓練。"
        ),
    )
    ap.add_argument("--output", default=DEFAULT_MODEL_DIR)
    ap.add_argument("--engine-mode", default="demo", choices=("paper", "demo", "live"))
    ap.add_argument("--use-quantile-predictor", action="store_true",
                    help="Route to EDGE-P3-1 Stage 2 quantile trio path")
    args = ap.parse_args()

    cfg = PipelineConfig(
        strategy_type=args.strategy,
        symbol=args.symbol,  # None → pooled (P1-7 C)
        output_dir=args.output,
        dry_run=args.dry_run,
        use_quantile_predictor=args.use_quantile_predictor,
        engine_mode=args.engine_mode,
    )
    res = run_pipeline(cfg)
    print(json.dumps({
        "success": res.success,
        "stages": res.stages_completed,
        "error": res.error,
        "metrics": res.metrics,
        "verdict": res.verdict,
        "acceptance_report_path": res.acceptance_report_path,
    }, indent=2, default=str))
