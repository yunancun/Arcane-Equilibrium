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

import copy
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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

    # WP2.1 source-only PIT manifest gate for contract-bound quantile training.
    # WP2.1：合約綁定分位訓練必須先綁定 PIT dataset manifest；傳統路徑保持
    # 非 contract-bound，若 caller 誤設 contract_bound_run 會 fail-closed。
    contract_bound_run: bool = False
    candidate_id: Optional[str] = None
    side: Optional[str] = None
    pit_dataset_manifest: Optional[Dict[str, Any]] = None
    pit_dataset_manifest_path: Optional[str] = None
    pit_dataset_manifest_source: Optional[Dict[str, Any]] = None


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
    contract_bound_run: bool = False
    pit_dataset_manifest_hash: str = ""
    pit_dataset_manifest_path: str = ""
    pit_dataset_manifest_status: str = ""
    pit_dataset_manifest_reason: str = ""


@dataclass(frozen=True)
class PitBinding:
    """Training-time PIT manifest binding emitted into acceptance reports."""

    contract_bound_run: bool = False
    manifest: Optional[Dict[str, Any]] = None
    manifest_hash: str = ""
    manifest_path: str = ""
    status: str = "not_contract_bound"
    validation_verdict: str = "not_required"
    validation_reason: str = "not_contract_bound"
    candidate_scope: Dict[str, Any] = field(default_factory=dict)

    def to_report_binding(self) -> Dict[str, Any]:
        binding: Dict[str, Any] = {
            "schema_version": "training_pit_manifest_binding_v1",
            "contract_bound_run": self.contract_bound_run,
            "status": self.status,
            "manifest_hash": self.manifest_hash,
            "manifest_path": self.manifest_path,
            "validation_verdict": self.validation_verdict,
            "validation_reason": self.validation_reason,
            "not_authority": True,
            "runtime_mutation_performed": False,
            "db_write_performed": False,
            "exchange_private_read_performed": False,
            "order_or_probe_performed": False,
            "live_or_mainnet_performed": False,
            "cost_gate_change_performed": False,
            "deploy_performed": False,
            "secret_access_performed": False,
        }
        if self.candidate_scope:
            binding["candidate_scope"] = dict(self.candidate_scope)
        return binding


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


def _training_window_bounds(
    timestamps: Any,
) -> tuple[Optional[datetime], Optional[datetime]]:
    """從訓練 timestamps 導出 (window_start, window_end) 的 UTC datetime（Item 7）。

    為什麼在此計算而非交給 DB：register 路徑本就持有本次訓練的 timestamps，min/max
      即訓練資料的實際時窗，是 PIT lineage 最小可重建錨點。單位偵測與
      cpcv_validator.generate_folds / scorer_trainer 保持一致（>1e12 視為毫秒轉秒），
      避免跨模組單位漂移。空/無效輸入 → (None, None)，讓欄位落 NULL 而非炸掉 register
      （registry 是審計目錄，lineage 缺席不得擋訓練）。
    """
    try:
        import numpy as np

        arr = np.asarray(timestamps, dtype=np.float64)
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            return (None, None)
        lo = float(arr.min())
        hi = float(arr.max())
    except Exception:  # noqa: BLE001 — lineage 是 best-effort，絕不擋 register
        return (None, None)
    # epoch-ms 自動偵測（與 generate_folds 一致）：>1e12 視為毫秒。
    if hi > 1e12:
        lo /= 1000.0
        hi /= 1000.0
    try:
        return (
            datetime.fromtimestamp(lo, tz=timezone.utc),
            datetime.fromtimestamp(hi, tz=timezone.utc),
        )
    except (OverflowError, OSError, ValueError):
        return (None, None)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _canonical_json_bytes(value: Dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _not_contract_bound_pit_binding() -> PitBinding:
    return PitBinding()


def _apply_pit_binding(result: PipelineResult, binding: PitBinding) -> None:
    result.contract_bound_run = binding.contract_bound_run
    result.pit_dataset_manifest_hash = binding.manifest_hash
    result.pit_dataset_manifest_path = binding.manifest_path
    result.pit_dataset_manifest_status = binding.status
    result.pit_dataset_manifest_reason = binding.validation_reason


def _pit_gate_failure_result(config: PipelineConfig, reason: str, status: str = "invalid") -> PipelineResult:
    result = PipelineResult(
        contract_bound_run=bool(config.contract_bound_run),
        pit_dataset_manifest_status=status,
        pit_dataset_manifest_reason=reason,
        error=reason,
    )
    result.stages_completed.append("pit_manifest_gate_failed")
    return result


def _load_pit_manifest_from_config(config: PipelineConfig) -> tuple[Any, str, str, int]:
    """Load explicit PIT manifest input without inferring external state.

    Returns (manifest, manifest_input_path, failure_reason, input_count).
    回傳 (manifest, 輸入路徑, 失敗原因, input_count)；只消費 caller 顯式提供的
    inline/path/source mapping，不讀 DB/runtime/exchange。
    """
    inputs = []
    if config.pit_dataset_manifest is not None:
        inputs.append("inline")
    if _text(config.pit_dataset_manifest_path):
        inputs.append("path")
    if config.pit_dataset_manifest_source is not None:
        inputs.append("source")
    if len(inputs) > 1:
        return None, "", "pit_dataset_manifest_multiple_inputs", len(inputs)
    if not inputs:
        return None, "", "", 0

    kind = inputs[0]
    if kind == "inline":
        return copy.deepcopy(config.pit_dataset_manifest), "", "", 1

    if kind == "path":
        path_text = _text(config.pit_dataset_manifest_path)
        try:
            manifest = json.loads(Path(path_text).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return None, path_text, f"pit_dataset_manifest_path_unreadable:{type(exc).__name__}", 1
        return manifest, path_text, "", 1

    from program_code.ml_training.pit_dataset_manifest_builder import (
        build_pit_dataset_manifest_from_source,
    )

    build = build_pit_dataset_manifest_from_source(config.pit_dataset_manifest_source or {})
    if build.manifest is None:
        return None, "", build.validation.reason, 1
    return build.manifest, "", "", 1


def _candidate_scope_mismatch_reason(
    config: PipelineConfig,
    manifest: Dict[str, Any],
    symbol_slot: str,
) -> str:
    scope = manifest.get("candidate_scope") if isinstance(manifest, dict) else None
    if not isinstance(scope, dict):
        return "pit_manifest_candidate_scope_missing"
    expected = {
        "candidate_id": _text(config.candidate_id),
        "strategy_name": _text(config.strategy_type),
        "symbol": _text(symbol_slot),
        "side": _text(config.side),
        "engine_mode": _text(config.engine_mode),
    }
    for field, expected_value in expected.items():
        if not expected_value:
            return f"pit_manifest_config_{field}_missing"
        actual_value = _text(scope.get(field))
        if actual_value != expected_value:
            return f"pit_manifest_candidate_scope_{field}_mismatch"
    return ""


def _write_pit_manifest_sidecar(
    output_dir: Path,
    strategy: str,
    engine_mode: str,
    symbol_slot: str,
    manifest: Dict[str, Any],
) -> str:
    path = output_dir / f"{strategy}_{engine_mode}_{symbol_slot}_pit_dataset_manifest.json"
    _atomic_write_bytes(path, _canonical_json_bytes(manifest) + b"\n")
    return str(path)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """先寫同目錄暫存檔，完整成功後才替換 final artifact。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{id(payload)}.tmp")
    try:
        tmp_path.write_bytes(payload)
        tmp_path.replace(path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _persist_acceptance_report_with_registry_contract(
    *,
    report_path: Path,
    report: Dict[str, Any],
    registry_serving_contract: Dict[str, Any],
) -> Dict[str, Any]:
    """同目錄 temp+replace 寫回已附 registry contract 的 acceptance report。"""
    from program_code.ml_training.registry_serving_contract import (
        attach_registry_serving_contract,
    )

    attached = attach_registry_serving_contract(report, registry_serving_contract)
    payload = json.dumps(attached, indent=2, default=str).encode("utf-8")
    _atomic_write_bytes(report_path, payload)
    return attached


def _iso_from_base_ms(base: datetime, offset_ms: int) -> str:
    ts = base + timedelta(milliseconds=int(offset_ms))
    return ts.isoformat().replace("+00:00", "Z")


def _build_dry_run_pit_manifest_source(
    config: PipelineConfig,
    features,
    labels,
    timestamps,
    feature_names,
    label_composition,
) -> Dict[str, Any]:
    """Build deterministic synthetic source mapping for dry-run PIT gate tests.

    這只證明 source-only gate 與 report binding 接線；不是 runtime evidence、
    ProofPacket、bounded Demo outcome 或 promotion proof。
    """
    base = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
    as_of_ts = "2026-07-06T00:00:00Z"
    row_ids = [f"dry-run-row-{idx:06d}" for idx in range(len(labels))]
    rows = []
    for idx, row_id in enumerate(row_ids):
        feature_values = features[idx].tolist() if hasattr(features[idx], "tolist") else list(features[idx])
        rows.append({
            "row_id": row_id,
            "ts": _iso_from_base_ms(base, int(timestamps[idx])),
            "feature_values": [float(value) for value in feature_values],
            "label": float(labels[idx]),
        })
    split_a = max(1, int(len(row_ids) * 0.6))
    split_b = max(split_a + 1, int(len(row_ids) * 0.8))
    split_b = min(split_b, len(row_ids))
    train_ids = row_ids[:split_a]
    validation_ids = row_ids[split_a:split_b] or row_ids[-1:]
    test_ids = row_ids[split_b:] or row_ids[-1:]
    start_ts = rows[0]["ts"] if rows else as_of_ts
    end_ts = rows[-1]["ts"] if rows else as_of_ts
    matched_control_count = max(1, min(16, len(row_ids)))
    feature_names_list = [str(name) for name in feature_names]
    label_summary = label_composition or {"source": "dry_run_synthetic"}

    return {
        "dataset_id": (
            f"dry-run-{config.strategy_type}-{config.engine_mode}-"
            f"{config.symbol}-{config.candidate_id}"
        ),
        "dataset_role": "synthetic_training_dry_run",
        "as_of_ts": as_of_ts,
        "candidate_scope": {
            "candidate_id": _text(config.candidate_id),
            "strategy_name": _text(config.strategy_type),
            "symbol": _text(config.symbol),
            "side": _text(config.side),
            "engine_mode": _text(config.engine_mode),
        },
        "window": {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "min_ts": start_ts,
            "max_ts": end_ts,
        },
        "query": {
            "query_id": (
                f"dry_run_source_only_{config.strategy_type}_"
                f"{config.engine_mode}_{config.symbol}"
            ),
            "query_text": (
                "SELECT deterministic synthetic dry_run training rows "
                "WHERE ts >= :start_ts AND ts <= :end_ts"
            ),
            "params": {
                "start_ts": start_ts,
                "end_ts": end_ts,
                "candidate_id": _text(config.candidate_id),
                "symbol": _text(config.symbol),
                "side": _text(config.side),
                "source_only": True,
            },
        },
        "rows": {"rows": rows},
        "features": {
            "feature_schema_version": _text(config.schema_version),
            "feature_names": feature_names_list,
            "feature_schema_hash": "f" * 64,
            "feature_definition_hash": "e" * 64,
            "definition": {
                "source": "deterministic_dry_run_synthetic_features",
                "n_features": len(feature_names_list),
            },
            "schema": {name: "float32" for name in feature_names_list},
        },
        "labels": {
            "schema": {"label": "float32"},
            "config": {
                "source": "deterministic_dry_run_synthetic_labels",
                "label_composition": label_summary,
            },
            "outcome_cutoff_ts": as_of_ts,
        },
        "splits": {
            "split_id": "dry-run-source-only-cpcv-v1",
            "train_row_ids": train_ids,
            "validation_row_ids": validation_ids,
            "test_row_ids": test_ids,
            "embargo_bars": 12,
            "purge_bars": 4,
        },
        "leakage": {
            "report": {"checked": True, "source": "dry_run_synthetic"},
            "fold_preprocessing_stats": {"fit_scope": "train_fold_only"},
            "overlap_count": 0,
        },
        "controls": {
            "matched_control_rows": [
                {"row_id": f"dry-run-control-{idx:06d}"}
                for idx in range(matched_control_count)
            ],
            "matched_control_count": matched_control_count,
        },
        "fills": {
            "fill_rows": [{
                "fill_id": "dry-run-fill-entry-000000",
                "order_link_id": "dry-run-order-000000",
                "context_id": "dry-run-context-000000",
            }],
            "fill_id_field": "fill_id",
            "order_link_id_field": "order_link_id",
            "context_id_field": "context_id",
        },
        "provenance": {
            "code_commit": "0" * 40,
            "rust_build_sha": "1" * 40,
            "source_hashes": {
                "pit_dataset_manifest_builder": "2" * 64,
                "run_training_pipeline": "3" * 64,
            },
            "input_artifact_hashes": {
                "dry_run_synthetic_dataset": "4" * 64,
                "dry_run_synthetic_labels": "5" * 64,
            },
        },
    }


def _resolve_training_pit_binding(
    config: PipelineConfig,
    *,
    output_dir: Path,
    symbol_slot: str,
    pooled: bool,
    features,
    labels,
    timestamps,
    feature_names,
    label_composition,
) -> tuple[Optional[PitBinding], str]:
    if not config.contract_bound_run:
        return _not_contract_bound_pit_binding(), ""

    if pooled:
        return None, "pit_manifest_pooled_symbol_not_allowed"

    manifest, _input_path, load_error, input_count = _load_pit_manifest_from_config(config)
    if load_error:
        return None, load_error

    if input_count == 0:
        if not config.dry_run:
            return None, "pit_dataset_manifest_missing"
        if not (_text(config.candidate_id) and _text(config.symbol) and _text(config.side)):
            return None, "pit_manifest_dry_run_scope_missing"
        from program_code.ml_training.pit_dataset_manifest_builder import (
            build_pit_dataset_manifest_from_source,
        )
        source = _build_dry_run_pit_manifest_source(
            config, features, labels, timestamps, feature_names, label_composition,
        )
        build = build_pit_dataset_manifest_from_source(source)
        manifest = build.manifest
        if manifest is None:
            return None, build.validation.reason

    from program_code.ml_training.pit_dataset_manifest import (
        DATASET_READY,
        compute_pit_dataset_manifest_hash,
        validate_pit_dataset_manifest,
    )

    validation = validate_pit_dataset_manifest(manifest)
    if not validation.dataset_ready or validation.verdict != DATASET_READY:
        return None, validation.reason
    if not isinstance(manifest, dict):
        return None, "pit_dataset_manifest_not_mapping"
    mismatch = _candidate_scope_mismatch_reason(config, manifest, symbol_slot)
    if mismatch:
        return None, mismatch

    manifest_hash = compute_pit_dataset_manifest_hash(manifest)
    manifest_path = _write_pit_manifest_sidecar(
        output_dir, config.strategy_type, config.engine_mode, symbol_slot, manifest,
    )
    scope = manifest.get("candidate_scope")
    return PitBinding(
        contract_bound_run=True,
        manifest=copy.deepcopy(manifest),
        manifest_hash=manifest_hash,
        manifest_path=manifest_path,
        status=DATASET_READY,
        validation_verdict=validation.verdict,
        validation_reason=validation.reason,
        candidate_scope=dict(scope) if isinstance(scope, dict) else {},
    ), ""


def _load_dataset(
    config: PipelineConfig,
) -> tuple:
    """Load (features, labels, timestamps, feature_names, label_composition).
    共用資料載入：回傳 5-tuple；label_composition 供 acceptance report 硬 gate
    （P1-3），dry-run 合成資料無 close_tag 語義 → None（gate 記 unavailable）。"""
    import numpy as np

    if config.dry_run:
        # Synthetic dataset sized to clear min_samples + quantile signal.
        # If quantile path: produce 17 features to match EDGE-P3-1 FeatureVectorV1
        # so the pipeline exercises the real feature-count contract end-to-end.
        # 合成資料：分位路徑產 17 特徵以走完整 FeatureVectorV1 契約。
        n = 600
        rng = np.random.default_rng(42)
        if config.use_quantile_predictor:
            from program_code.ml_training.parquet_etl import EDGE_P3_FEATURE_NAMES
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
        return features, labels, timestamps, feature_names, None

    # Resolve pooling: symbol=None or "ALL" → SQL-level symbol filter skipped.
    # Everything else → filter to that exact symbol.
    # 解析 pooling：symbol=None 或 "ALL" → SQL 不加 symbol filter；其他 → 精確過濾。
    pooled, _slot = _resolve_symbol_slot(config)
    sql_symbol: Optional[str] = None if pooled else config.symbol

    if config.use_quantile_predictor:
        from program_code.ml_training.parquet_etl import load_training_data
        features, labels, timestamps, feature_names, label_composition = load_training_data(
            symbol=sql_symbol,
            strategy_type=config.strategy_type,
            dsn=config.dsn,
            engine_mode=config.engine_mode,
        )
    else:
        from program_code.ml_training.parquet_etl import load_training_data
        features, labels, timestamps, feature_names, label_composition = load_training_data(
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
    return features, labels, timestamps, feature_names, label_composition


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
    from program_code.ml_training.parquet_etl import _get_pg_conn, engine_mode_scope
    engine_modes = list(engine_mode_scope(engine_mode))
    sql = """
    SELECT symbol, COUNT(*) AS labeled
    FROM learning.decision_features
    WHERE label_net_edge_bps IS NOT NULL
      AND engine_mode = ANY(%(engine_modes)s)
      AND (%(strategy_name)s IS NULL OR strategy_name = %(strategy_name)s)
      AND ts >= now() - (%(max_age_days)s || ' days')::interval
    GROUP BY symbol
    ORDER BY labeled DESC
    """
    conn = _get_pg_conn(config.dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "engine_modes": engine_modes,
                "strategy_name": config.strategy_type,
                "max_age_days": max_age_days,
            })
            return [(sym, int(n)) for sym, n in cur.fetchall()]
    finally:
        conn.close()


def _run_quantile_pipeline(
    config: PipelineConfig,
    features, labels, timestamps, feature_names,
    label_composition=None,
) -> PipelineResult:
    """EDGE-P3-1 Stage 2 quantile path end-to-end.
    EDGE-P3-1 Stage 2 分位路徑端到端。"""
    import numpy as np
    from program_code.ml_training.quantile_trainer import (
        QuantileTrainingConfig,
    )
    from program_code.ml_training.calibration import fit_cqr_trio, evaluate_cqr_coverage
    from program_code.ml_training.quantile_reports import (
        VERDICT_NO_SHIP,
        generate_acceptance_report,
    )
    from program_code.ml_training.onnx_exporter import export_quantile_trio_to_onnx

    result = PipelineResult()
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # P1-7 C pooled vs per-symbol — drive filename slots + metrics annotations.
    # P1-7 C：解析 pooled / per-symbol；供 acceptance report 檔名 + 指標標記。
    pooled, symbol_slot = _resolve_symbol_slot(config)

    pit_binding, pit_error = _resolve_training_pit_binding(
        config,
        output_dir=output_dir,
        symbol_slot=symbol_slot,
        pooled=pooled,
        features=features,
        labels=labels,
        timestamps=timestamps,
        feature_names=feature_names,
        label_composition=label_composition,
    )
    if pit_error:
        failed = _pit_gate_failure_result(config, pit_error)
        return failed
    pit_binding = pit_binding or _not_contract_bound_pit_binding()
    _apply_pit_binding(result, pit_binding)

    qcfg = QuantileTrainingConfig(schema_version=config.schema_version)

    # Stage 2: train q10/q50/q90.
    from program_code.ml_training.quantile_trainer import train_quantile_trio

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

    # Stage 3: CQR calibration on the CALIBRATION partition; post-coverage on TEST.
    # 反洩漏後：CQR 位移在 calibration 分區擬合，「CQR 後 coverage」（ship-gate 指標）
    # 在未污染的 test 分區回報 —— 校準集與回報集互斥，不再共用資料列（claim-0002 HIGH）。
    cqr_offsets = fit_cqr_trio(
        train_result.calibration_labels,
        train_result.calibration_q10_pred,
        train_result.calibration_q50_pred,
        train_result.calibration_q90_pred,
    )
    post_coverage = evaluate_cqr_coverage(
        train_result.test_labels,
        train_result.test_q10_pred,
        train_result.test_q50_pred,
        train_result.test_q90_pred,
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
        # P1-3：label 組成硬 gate（synthetic_share==0 且 zeros_share≤0.5，
        # fail → verdict 封頂 shadow_only）。
        label_composition=label_composition,
        pit_dataset_manifest=pit_binding.manifest,
        pit_dataset_manifest_binding=pit_binding.to_report_binding(),
        persist_required=pit_binding.contract_bound_run,
    )
    result.stages_completed.append("acceptance_report")
    result.verdict = report.get("verdict", "")
    result.acceptance_report_path = str(report_path)
    if pit_binding.contract_bound_run:
        try:
            persisted = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            result.error = f"pit acceptance report persist verification failed: {exc}"
            result.stages_completed.append("pit_manifest_report_verify_failed")
            return result
        persisted_binding = persisted.get("pit_dataset_manifest_binding", {})
        if persisted_binding.get("manifest_hash") != pit_binding.manifest_hash:
            result.error = "pit_manifest_report_hash_mismatch"
            result.stages_completed.append("pit_manifest_report_verify_failed")
            return result

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
        feature_definition_hash=train_result.feature_definition_hash,
    )
    result.onnx_artifacts = onnx_out
    result.stages_completed.append("onnx_export")

    registry_serving_contract = None
    if pit_binding.contract_bound_run:
        from program_code.ml_training.registry_serving_contract import (
            build_registry_serving_contract_from_training_acceptance,
        )

        registry_serving_contract = (
            build_registry_serving_contract_from_training_acceptance(
                acceptance_report=report,
                onnx_out=onnx_out,
            )
        )
        report = _persist_acceptance_report_with_registry_contract(
            report_path=report_path,
            report=report,
            registry_serving_contract=registry_serving_contract,
        )
        result.stages_completed.append("registry_serving_contract")

    # Stage 5.5: Register ONNX artifacts in learning.model_registry (V023).
    # INFRA-PREBUILD-1 Part B (2026-04-23): persist artifact path + verdict +
    # acceptance report JSONB + provenance hashes so Rust OnnxModelManager can
    # query "latest production model for this slot" from DB instead of relying
    # solely on the filesystem `_current` symlink. Skipped when DB unavailable
    # or verdict=no_ship (registry stays clean of unshippable models).
    # INFRA-PREBUILD-1 B 部：寫 learning.model_registry，讓 Rust OnnxModelManager
    # 可以查 DB 取「這個 slot 的 latest production model」，不必只依賴 _current
    # symlink。DB 不可用或 verdict=no_ship 時跳過。
    # P1-14：对 live-readiness-bearing 工件（should_ship / shadow_only + 已写盘
    # 三件套）注册持久化是强制要求，DB 不可用必须 fail-loud；no_ship / unknown
    # 仍是非致命的合法跳过。caller 侧先做连通性预检以区分「DB 不可用」与「verdict
    # 跳过 / slot 锁定」，避免改 register_model 签名（更小爆炸半径）。
    from program_code.ml_training.model_registry import (
        register_quantile_trio_from_onnx_out,
        has_required_persistence_artifact,
        check_db_connectivity,
        RegistryPersistenceError,
    )
    registry_required = has_required_persistence_artifact(
        onnx_out=onnx_out, verdict=result.verdict
    )
    if registry_required and not check_db_connectivity(dsn=config.dsn):
        # 为什么 fail-loud：required 工件无法落库即 registry 静默陈旧，
        # canary_promoter 取不到候选；训练绝不能在此情况下报成功。
        result.stages_completed.append("registry_persistence_failed")
        raise RegistryPersistenceError(
            f"required registry persistence unavailable for "
            f"{config.strategy_type}/{config.engine_mode} verdict={result.verdict}: "
            "DB connectivity precheck failed"
        )
    # Item 7 (PIT lineage, V157)：每次 register 一併寫入可重建 lineage 的三欄。
    #   training_window_start/end 取自本次訓練 timestamps 的最小/最大（epoch-ms 自動
    #   偵測轉秒），pit_manifest_hash 取自 PIT binding（非 contract-bound run 為空 →
    #   存 NULL）。此為 SOURCE 路線：不翻動 production contract_bound_run 亦能讓
    #   registry row 自身承載訓練資料時窗，供稽核直接重建，而非只能靠 acceptance
    #   report sidecar。_latest / proof 晉升路徑完全不動。
    training_window_start, training_window_end = _training_window_bounds(timestamps)
    pit_manifest_hash = pit_binding.manifest_hash or None
    try:
        registry_kwargs = {
            "onnx_out": onnx_out,
            "strategy": config.strategy_type,
            "engine_mode": config.engine_mode,
            "schema_version": config.schema_version,
            "verdict": result.verdict,
            "acceptance_report_path": result.acceptance_report_path,
            "feature_schema_hash": train_result.feature_schema_hash,
            # P1-3：registry 記帳改 informative count（排除合成 reject），
            # 終結「524k 樣本」假象；composition 缺席（dry-run）回退 labeled 數。
            "training_sample_size": (
                int(label_composition["n_informative"])
                if label_composition else train_result.n_samples_labeled
            ),
            "dsn": config.dsn,
            "training_window_start": training_window_start,
            "training_window_end": training_window_end,
            "pit_manifest_hash": pit_manifest_hash,
        }
        if registry_serving_contract is not None:
            registry_kwargs["registry_serving_contract"] = registry_serving_contract
        registry_ids = register_quantile_trio_from_onnx_out(**registry_kwargs)
        if registry_ids:
            result.stages_completed.append(f"model_registry_wrote_{len(registry_ids)}")
        elif registry_required:
            # required 工件 + DB 已连通却 0 行：非 DB 原因（slot 锁定 promoting/
            # production 是合法 no-op，记 INFO；no_ship/unknown 不会进到这里）。
            logger.info(
                "model_registry: required artifact returned 0 rows (likely slot "
                "locked in promoting/production) for %s/%s",
                config.strategy_type, config.engine_mode,
            )
            result.stages_completed.append("model_registry_skipped_slot_locked")
        else:
            result.stages_completed.append("model_registry_skipped")
    except RegistryPersistenceError:
        raise
    except Exception as e:  # noqa: BLE001 — non-required registry write is audit-only
        logger.warning("model_registry write failed (non-fatal): %s", e)
        result.stages_completed.append("model_registry_error")

    # Stage 6: summary metrics for pipeline consumer.
    # pooled / symbol_slot 直接進 metrics JSON，acceptance report 檔名也帶 slot。
    result.metrics = {
        "verdict": result.verdict,
        "n_samples_labeled": train_result.n_samples_labeled,
        "n_holdout": train_result.n_holdout,
        # 三分區列數 + 指標來源標記，供消費端溯源 ship-gate 指標取自未污染的 test 分區。
        # MIT Item 1 修訂：可能走 two_way_shadow_capped 退路（holdout 太小），故來源標記與
        #   partition_mode 由 train_result 溯源，不寫死；two_way 時 verdict 已被封頂 shadow_only。
        "n_validation": train_result.n_validation,
        "n_calibration": train_result.n_calibration,
        "n_test": train_result.n_test,
        "ship_gate_metric_source": getattr(
            train_result, "ship_gate_metric_source", "test_partition",
        ),
        "partition_mode": getattr(train_result, "partition_mode", "three_way"),
        "pinball_skill_q10": train_result.per_quantile_metrics["q10"].pinball_skill,
        "pinball_skill_q50": train_result.per_quantile_metrics["q50"].pinball_skill,
        "pinball_skill_q90": train_result.per_quantile_metrics["q90"].pinball_skill,
        "crossing_rate": train_result.crossing_rate,
        "decile_lift_point": train_result.decile_lift_point,
        "decile_lift_ci_lower": train_result.decile_lift_ci_lower,
        "feature_schema_hash": train_result.feature_schema_hash,
        "feature_definition_hash": train_result.feature_definition_hash,
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

    from program_code.ml_training.scorer_trainer import ScorerConfig, train_scorer

    scorer_cfg = ScorerConfig(output_dir=str(output_dir))
    train_result = train_scorer(
        features=features,
        labels=labels,
        feature_names=feature_names,
        config=scorer_cfg,
        timestamps=timestamps,
        strategy_type=config.strategy_type,
        # Item 6：把 pipeline 的 config.dsn 一路 thread 到 validate_cpcv →
        #   _persist_cpcv_result，統一 CPCV 持久化 DSN 來源，不再只靠 env。
        dsn=config.dsn,
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
    result = PipelineResult(contract_bound_run=bool(config.contract_bound_run))

    try:
        if config.contract_bound_run and not config.use_quantile_predictor:
            return _pit_gate_failure_result(
                config,
                "contract_bound_quantile_path_required",
                status="invalid",
            )
        logger.info(
            "[pipeline] start: strategy=%s engine=%s quantile=%s dry_run=%s",
            config.strategy_type, config.engine_mode,
            config.use_quantile_predictor, config.dry_run,
        )
        features, labels, timestamps, feature_names, label_composition = _load_dataset(config)
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

        # 反洩漏 name-pattern 預篩（audit remediation item 4）：任何 fit 之前先用
        # leakage_check 掃描特徵名的 forbidden pattern。此模塊是 L2 ml_advisory
        # PromptContract 唯一引用的 name_pattern_check producer
        # （l2_prompt_contract_registry.py:152-190），故不可刪除；但它只是 weak
        # necessary-not-sufficient screen，不能宣稱 leak-free PIT——真正的值級 gate
        # （shift1_compliance / is_oos_gap）是 P3b MIT-owned producer，尚未接線。
        # 為什麼 strict=False：ALLOWED_PREFIXES 白名單相對 EDGE_P3_FEATURE_NAMES 已過時
        # （17 個真特徵有 12 個不匹配前綴），strict 會誤殺合法特徵並中斷訓練；只有
        # forbidden pattern（outcome_/future_/target_/label/realized_pnl…）才是無歧義
        # 的洩漏訊號。為什麼 fail-closed：特徵名內出現 forbidden pattern 代表 label 或
        # 未來資訊直接進入特徵集，任何下游 ship-gate metric 都失去意義，必須在 fit 前中止。
        from program_code.ml_training.leakage_check import check_feature_leakage

        leakage_passed, leakage_violations = check_feature_leakage(
            feature_names, strict=False,
        )
        leakage_prescreen = {
            "source_class": "name_pattern_check",
            "strict": False,
            "passed": leakage_passed,
            "violations": leakage_violations,
            # name-pattern 不足以支撐 leak-free 斷言，明確標 False 供 L2 advisory typing。
            "leak_free_pit_claim": False,
        }
        if not leakage_passed:
            result.metrics["leakage_prescreen"] = leakage_prescreen
            result.error = "feature_leakage_forbidden_pattern: " + "; ".join(
                leakage_violations[:5]
            )
            result.stages_completed.append("feature_leakage_prescreen_failed")
            logger.warning(result.error)
            return result

        if config.use_quantile_predictor:
            inner = _run_quantile_pipeline(
                config, features, labels, timestamps, feature_names,
                label_composition=label_composition,
            )
        else:
            inner = _run_legacy_scorer_pipeline(config, features, labels, timestamps, feature_names)

        # Merge inner into outer keeping etl + labels + leakage pre-screen first.
        # 反洩漏預篩已在 fit 前通過，補進 stages 與 metrics，讓消費端（含 L2 advisory）
        # 能溯源 name_pattern_check 這個 evidence 確實被產出，而非僅 prompt 宣稱。
        inner.stages_completed = [
            "etl", "labels", "feature_leakage_prescreen",
        ] + inner.stages_completed
        inner.metrics["leakage_prescreen"] = leakage_prescreen
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
    ap.add_argument("--engine-mode", default="demo", choices=("paper", "demo", "live", "live_demo"))
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
