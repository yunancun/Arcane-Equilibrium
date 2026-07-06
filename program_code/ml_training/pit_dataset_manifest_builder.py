"""
MODULE_NOTE
模塊用途：從 caller 提供的 source mapping 建立 pit_dataset_manifest_v1。
主要類/函數：PitDatasetManifestBuild、
build_pit_dataset_manifest_from_source、compute_synthetic_dataset_hash。
依賴：僅 Python 標準庫與 pit_dataset_manifest validator；不讀 DB、不讀檔、
不讀環境、不連 runtime、不呼叫交易所。
硬邊界：本 builder 只整理 caller 已提供的 source mapping 與 synthetic rows；
validation 未達 dataset_ready 時不能授予訓練、proof、order、probe、DB、
runtime、Cost Gate、deploy、live/mainnet authority。
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

try:
    from .pit_dataset_manifest import (
        DATASET_READY,
        PIT_DATASET_MANIFEST_SCHEMA_VERSION,
        PitDatasetManifestValidation,
        compute_pit_dataset_manifest_hash,
        validate_pit_dataset_manifest,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    from pit_dataset_manifest import (  # type: ignore
        DATASET_READY,
        PIT_DATASET_MANIFEST_SCHEMA_VERSION,
        PitDatasetManifestValidation,
        compute_pit_dataset_manifest_hash,
        validate_pit_dataset_manifest,
    )


_ROW_ID_FIELDS = (
    "row_id",
    "source_row_id",
    "id",
    "fill_id",
    "order_id",
    "order_link_id",
    "context_id",
)
_HASH_KEYS = {
    "dataset_hash",
    "feature_definition_hash",
    "feature_names_hash",
    "feature_schema_hash",
    "fill_row_ids_hash",
    "fill_source_artifact_hash",
    "fold_preprocessing_stats_hash",
    "label_config_hash",
    "label_schema_hash",
    "leakage_report_hash",
    "matched_control_artifact_hash",
    "matched_control_row_ids_hash",
    "query_hash",
    "query_params_hash",
    "query_text_hash",
    "row_ids_hash",
    "schema_hash",
    "split_hash",
    "train_row_ids_hash",
    "validation_row_ids_hash",
    "test_row_ids_hash",
}


@dataclass(frozen=True)
class PitDatasetManifestBuild:
    """Builder 結果；只有 validation.dataset_ready 才能被下游放行。"""

    manifest: dict[str, Any] | None
    validation: PitDatasetManifestValidation
    source: str
    downgrade_reason: str | None = None


def build_pit_dataset_manifest_from_source(
    source_mapping: Mapping[str, Any],
) -> PitDatasetManifestBuild:
    """從 caller-provided mapping 建立 PIT dataset manifest。

    必要 source sections 由 caller 顯式提供：as_of_ts/window/query/rows/
    features/labels/splits/leakage/controls/fills/provenance。此函數不補查
    外部狀態；缺欄位只會讓 validator fail-closed。
    """
    if not isinstance(source_mapping, Mapping):
        validation = PitDatasetManifestValidation(
            dataset_ready=False,
            verdict="pending_schema",
            reason="source_mapping_not_mapping",
            reasons=("source_mapping_not_mapping",),
        )
        return PitDatasetManifestBuild(
            manifest=None,
            validation=validation,
            source="source_mapping_invalid",
            downgrade_reason=validation.reason,
        )

    manifest = _draft_manifest_from_source(source_mapping)
    manifest["manifest_hash"] = compute_pit_dataset_manifest_hash(manifest)
    validation = validate_pit_dataset_manifest(manifest)
    return PitDatasetManifestBuild(
        manifest=manifest,
        validation=validation,
        source="source_mapping",
        downgrade_reason=None if validation.dataset_ready else validation.reason,
    )


def compute_synthetic_row_hash(row: Any) -> str:
    """對單列 synthetic row 做 canonical JSON sha256。"""
    return _canonical_sha256(_jsonable(row))


def compute_synthetic_row_id(row: Any) -> str:
    """取得 deterministic row id；無顯式 id 時退回 row hash。"""
    if isinstance(row, Mapping):
        for field in _ROW_ID_FIELDS:
            text = _text(row.get(field))
            if text:
                return text
    if isinstance(row, (str, int, float)) and not isinstance(row, bool):
        text = _text(row)
        if text:
            return text
    return compute_synthetic_row_hash(row)


def compute_synthetic_row_ids_hash(rows: Any) -> str:
    """對 row id set 做 deterministic hash；不受 row dict key order 影響。"""
    row_ids = sorted(compute_synthetic_row_id(row) for row in _items(rows))
    return _canonical_sha256(row_ids)


def compute_synthetic_dataset_hash(rows: Any) -> str:
    """對 row payload set 做 deterministic hash；不受 row/key order 影響。"""
    row_hashes = sorted(compute_synthetic_row_hash(row) for row in _items(rows))
    return _canonical_sha256(row_hashes)


def hash_synthetic_row_ids(rows: Any) -> str:
    """Alias for callers that prefer verb-first helper naming."""
    return compute_synthetic_row_ids_hash(rows)


def hash_synthetic_dataset(rows: Any) -> str:
    """Alias for callers that prefer verb-first helper naming."""
    return compute_synthetic_dataset_hash(rows)


def _draft_manifest_from_source(source: Mapping[str, Any]) -> dict[str, Any]:
    window = _mapping(source.get("window"))
    query = _mapping(source.get("query"))
    rows_source = source.get("rows")
    rows_meta = _mapping(rows_source)
    rows = _items(rows_source)
    rebuilt_rows = _items(rows_meta.get("rebuilt_rows")) or rows

    manifest: dict[str, Any] = {
        "schema_version": PIT_DATASET_MANIFEST_SCHEMA_VERSION,
        "verdict": DATASET_READY,
        "point_in_time": source.get("point_in_time", True),
        "future_data_allowed": source.get("future_data_allowed", False),
    }
    _put_if_text(manifest, "dataset_id", source.get("dataset_id"))
    _put_if_text(manifest, "dataset_role", source.get("dataset_role"))
    _put_if_text(manifest, "as_of_ts", source.get("as_of_ts"))
    manifest["candidate_scope"] = _jsonable(_mapping(source.get("candidate_scope")))
    manifest["source_query"] = _build_source_query(query, window)
    manifest["row_set"] = _build_row_set(rows_meta, rows, window)
    manifest["feature_lineage"] = _build_feature_lineage(_mapping(source.get("features")))
    manifest["label_lineage"] = _build_label_lineage(
        _mapping(source.get("labels")),
        source.get("as_of_ts"),
    )
    manifest["split_lineage"] = _build_split_lineage(_mapping(source.get("splits")))
    manifest["leakage_evidence"] = _build_leakage_evidence(
        _mapping(source.get("leakage"))
    )
    manifest["matched_controls"] = _build_matched_controls(
        _mapping(source.get("controls"))
    )
    manifest["row_backed_fill_source"] = _build_row_backed_fill_source(
        _mapping(source.get("fills"))
    )
    manifest["rebuild_evidence"] = _build_rebuild_evidence(rows, rebuilt_rows)
    manifest["provenance"] = _jsonable(_mapping(source.get("provenance")))
    return manifest


def _build_source_query(
    query: Mapping[str, Any],
    window: Mapping[str, Any],
) -> dict[str, Any]:
    query_payload = _jsonable(query)
    out: dict[str, Any] = {}
    _put_if_text(out, "query_id", _first(query.get("query_id"), query.get("id")))
    out["query_hash"] = _first(
        query.get("query_hash"),
        _hash_without_hash_fields(query_payload),
    )
    out["query_params_hash"] = _first(
        query.get("query_params_hash"),
        query.get("params_hash"),
        _canonical_sha256(_jsonable(query.get("params", {}))),
    )
    _put_if_text(
        out,
        "start_ts",
        _first(query.get("start_ts"), window.get("start_ts"), window.get("start")),
    )
    _put_if_text(
        out,
        "end_ts",
        _first(query.get("end_ts"), window.get("end_ts"), window.get("end")),
    )
    query_text = _first(query.get("query_text"), query.get("text"), query.get("sql"))
    if _text(query_text):
        out["query_text"] = _text(query_text)
        out["query_text_hash"] = _first(
            query.get("query_text_hash"),
            _canonical_sha256(_text(query_text)),
        )
    if "params" in query:
        out["params"] = _jsonable(query.get("params"))
    if "max_age_days" in query:
        out["max_age_days"] = _jsonable(query.get("max_age_days"))
    return out


def _build_row_set(
    rows_meta: Mapping[str, Any],
    rows: list[Any],
    window: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "row_count": _first_int(rows_meta.get("row_count"), len(rows)),
        "row_ids_hash": _first(
            rows_meta.get("row_ids_hash"),
            compute_synthetic_row_ids_hash(rows),
        ),
        "dataset_hash": _first(
            rows_meta.get("dataset_hash"),
            compute_synthetic_dataset_hash(rows),
        ),
        "min_ts": _text(
            _first(
                rows_meta.get("min_ts"),
                window.get("min_ts"),
                window.get("start_ts"),
                window.get("start"),
            )
        ),
        "max_ts": _text(
            _first(
                rows_meta.get("max_ts"),
                window.get("max_ts"),
                window.get("end_ts"),
                window.get("end"),
            )
        ),
        "schema_hash": _first(rows_meta.get("schema_hash"), _schema_hash(rows)),
    }


def _build_feature_lineage(features: Mapping[str, Any]) -> dict[str, Any]:
    names = _first(features.get("feature_names"), features.get("names"), [])
    return {
        "feature_schema_version": _text(
            _first(features.get("feature_schema_version"), features.get("schema_version"))
        ),
        "feature_schema_hash": _first(
            features.get("feature_schema_hash"),
            _section_hash(features.get("schema", features)),
        ),
        "feature_definition_hash": _first(
            features.get("feature_definition_hash"),
            _section_hash(features.get("definition", features)),
        ),
        "feature_names_hash": _first(
            features.get("feature_names_hash"),
            _canonical_sha256(_jsonable(names)),
        ),
    }


def _build_label_lineage(labels: Mapping[str, Any], as_of_ts: Any) -> dict[str, Any]:
    return {
        "label_schema_hash": _first(
            labels.get("label_schema_hash"),
            _section_hash(labels.get("schema", labels)),
        ),
        "label_config_hash": _first(
            labels.get("label_config_hash"),
            _section_hash(labels.get("config", labels)),
        ),
        "outcome_cutoff_ts": _text(_first(labels.get("outcome_cutoff_ts"), as_of_ts)),
    }


def _build_split_lineage(splits: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "split_id": _text(splits.get("split_id")),
        "split_hash": _first(splits.get("split_hash"), _hash_without_hash_fields(splits)),
        "train_row_ids_hash": _first(
            splits.get("train_row_ids_hash"),
            _ids_hash(_first(splits.get("train_row_ids"), splits.get("train_rows"), [])),
        ),
        "validation_row_ids_hash": _first(
            splits.get("validation_row_ids_hash"),
            _ids_hash(
                _first(
                    splits.get("validation_row_ids"),
                    splits.get("validation_rows"),
                    splits.get("val_row_ids"),
                    splits.get("val_rows"),
                    [],
                )
            ),
        ),
        "test_row_ids_hash": _first(
            splits.get("test_row_ids_hash"),
            _ids_hash(_first(splits.get("test_row_ids"), splits.get("test_rows"), [])),
        ),
    }
    for field in ("embargo_bars", "purge_bars", "embargo_days", "purge_days"):
        if field in splits:
            out[field] = _jsonable(splits.get(field))
    return out


def _build_leakage_evidence(leakage: Mapping[str, Any]) -> dict[str, Any]:
    out = {
        "leakage_report_hash": _first(
            leakage.get("leakage_report_hash"),
            _section_hash(leakage.get("report", leakage)),
        ),
        "fold_preprocessing_stats_hash": _first(
            leakage.get("fold_preprocessing_stats_hash"),
            _section_hash(leakage.get("fold_preprocessing_stats", leakage)),
        ),
    }
    if "overlap_count" in leakage:
        out["overlap_count"] = _jsonable(leakage.get("overlap_count"))
    return out


def _build_matched_controls(controls: Mapping[str, Any]) -> dict[str, Any]:
    control_rows = _first(
        controls.get("matched_control_rows"),
        controls.get("control_rows"),
        controls.get("rows"),
        controls.get("matched_control_ids"),
        [],
    )
    control_count = _first_int(
        controls.get("matched_control_count"),
        len(_items(control_rows)),
    )
    return {
        "matched_control_artifact_hash": _first(
            controls.get("matched_control_artifact_hash"),
            _hash_without_hash_fields(controls),
        ),
        "matched_control_row_ids_hash": _first(
            controls.get("matched_control_row_ids_hash"),
            _ids_hash(control_rows),
        ),
        "matched_control_count": control_count,
    }


def _build_row_backed_fill_source(fills: Mapping[str, Any]) -> dict[str, Any]:
    fill_rows = _first(fills.get("fill_rows"), fills.get("rows"), fills.get("fill_ids"), [])
    return {
        "fill_source_artifact_hash": _first(
            fills.get("fill_source_artifact_hash"),
            _hash_without_hash_fields(fills),
        ),
        "fill_row_ids_hash": _first(fills.get("fill_row_ids_hash"), _ids_hash(fill_rows)),
        "fill_id_field": _text(fills.get("fill_id_field")),
        "order_link_id_field": _text(fills.get("order_link_id_field")),
        "context_id_field": _text(fills.get("context_id_field")),
    }


def _build_rebuild_evidence(rows: list[Any], rebuilt_rows: list[Any]) -> dict[str, Any]:
    original_row_ids_hash = compute_synthetic_row_ids_hash(rows)
    rebuilt_row_ids_hash = compute_synthetic_row_ids_hash(rebuilt_rows)
    original_dataset_hash = compute_synthetic_dataset_hash(rows)
    rebuilt_dataset_hash = compute_synthetic_dataset_hash(rebuilt_rows)
    return {
        "status": (
            "rebuild_hash_match"
            if original_row_ids_hash == rebuilt_row_ids_hash
            and original_dataset_hash == rebuilt_dataset_hash
            and len(rows) == len(rebuilt_rows)
            else "rebuild_hash_mismatch"
        ),
        "original_row_count": len(rows),
        "rebuilt_row_count": len(rebuilt_rows),
        "original_row_ids_hash": original_row_ids_hash,
        "rebuilt_row_ids_hash": rebuilt_row_ids_hash,
        "original_dataset_hash": original_dataset_hash,
        "rebuilt_dataset_hash": rebuilt_dataset_hash,
    }


def _items(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        for key in ("rows", "items", "records", "row_ids", "ids"):
            child = value.get(key)
            if isinstance(child, (list, tuple)):
                return list(child)
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _ids_hash(value: Any) -> str:
    items = _items(value)
    if not items and isinstance(value, (list, tuple)):
        items = list(value)
    ids = sorted(compute_synthetic_row_id(item) for item in items)
    return _canonical_sha256(ids)


def _schema_hash(rows: list[Any]) -> str:
    schema: list[Any] = []
    for row in rows:
        if isinstance(row, Mapping):
            schema.append(
                sorted((str(key), type(value).__name__) for key, value in row.items())
            )
        else:
            schema.append(type(row).__name__)
    return _canonical_sha256(sorted(_canonical_json(item) for item in schema))


def _section_hash(value: Any) -> str:
    return _hash_without_hash_fields(value)


def _hash_without_hash_fields(value: Any) -> str:
    return _canonical_sha256(_drop_hash_fields(_jsonable(value)))


def _drop_hash_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _drop_hash_fields(child)
            for key, child in value.items()
            if str(key) not in _HASH_KEYS and str(key) != "manifest_hash"
        }
    if isinstance(value, list):
        return [_drop_hash_fields(child) for child in value]
    return value


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(child) for child in value]
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    return str(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(*values: Any) -> Any:
    for value in values:
        if _present(value):
            return value
    return ""


def _first_int(*values: Any) -> int:
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _put_if_text(target: dict[str, Any], key: str, value: Any) -> None:
    text = _text(value)
    if text:
        target[key] = text


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.hex()
    return str(value).strip()


def _present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


__all__ = [
    "PitDatasetManifestBuild",
    "build_pit_dataset_manifest_from_source",
    "compute_synthetic_dataset_hash",
    "compute_synthetic_row_hash",
    "compute_synthetic_row_id",
    "compute_synthetic_row_ids_hash",
    "hash_synthetic_dataset",
    "hash_synthetic_row_ids",
]
