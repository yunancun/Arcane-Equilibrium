"""EDGE-P3 特徵 schema 契約的 PG-surface-free 葉模組(S2.4 §8.1/W2 P1-C)。

存在理由(E3 P1-2):``learning_runtime_manifest`` 只需要 parquet_etl 的三個純常量/
純函數(``EDGE_P3_FEATURE_NAMES`` / ``EDGE_P3_FEATURE_SCHEMA_VERSION`` /
``compute_feature_schema_hash``),但 parquet_etl 自身是**真連 PostgreSQL** 的 duckdb
ETL 面(``ATTACH ... TYPE postgres``、``_get_pg_conn`` 會回退 ``OPENCLAW_DATABASE_URL``/
``DSN``/``POSTGRES_*`` 等 ambient env)。為了讓 engine-scanner 的 runtime import 閉包
內「零 ambient-DSN 來源」,契約下沉至本葉:

- 本模組硬邊界:純常量 + 純雜湊,零 I/O、零 DB、零網路、零 env 讀取、零第三方相依;
- ``parquet_etl.py`` 本身**刻意不改**——它仍是 ``LEARNING_CODE_INPUTS_V2`` 的內容輸入,
  改動即改 ``learning_runtime_digest_v2``(WP1 已凍結的 v2 學習碼身分);
- 兩側常量必須逐位元組一致,由
  ``tests/structure/test_learning_runtime_manifest_source_static.py`` 的漂移測試釘死。

順序穩定性(與 Rust ``FeatureVectorV1`` 對齊)是 train/serve 契約:重排 = 靜默 skew。
"""

from __future__ import annotations

import hashlib

# EDGE-P3-1 Stage 1/2:與 Rust FeatureVectorV1 一致的 17 特徵規範順序
# (rust/openclaw_engine/src/edge_predictor/features.rs §3.2)。順序穩定:Stage 2 訓練
# 以此序列計算 feature_schema_hash,Rust 推理時驗證匹配。順序變更 = 靜默 train/serve
# skew。禁止重排(此處為 parquet_etl 的 SSOT 鏡像,漂移由 source-static 測試攔下)。
EDGE_P3_FEATURE_NAMES = (
    "adx_1h",
    "bb_width_pct",
    "atr_pct",
    "funding_rate",
    "realized_vol_1h",
    "basis_bps",
    "orderbook_imbalance_top5",
    "spread_bps",
    "confluence_score",
    "persistence_elapsed_ms",
    "side",
    "notional_pct_of_bal",
    "concurrent_positions",
    "same_direction_cnt",
    "tod_sin",
    "tod_cos",
    "is_funding_settlement_window",
)

EDGE_P3_FEATURE_SCHEMA_VERSION = "v1"


def _compute_sha256_short(items: tuple[str, ...] | list[str]) -> str:
    """Rust-parity 短雜湊(逐項 utf-8 + 換行;取前 16 hex)。"""
    digest = hashlib.sha256()
    for item in items:
        digest.update(str(item).encode("utf-8"))
        digest.update(b"\n")
    return "sha256:" + digest.hexdigest()[:16]


def compute_feature_schema_hash(
    feature_names: tuple[str, ...] | list[str] = EDGE_P3_FEATURE_NAMES,
) -> str:
    """Rust-parity name-order hash used for train/serve schema checks."""
    return _compute_sha256_short(list(feature_names))


__all__ = [
    "EDGE_P3_FEATURE_NAMES",
    "EDGE_P3_FEATURE_SCHEMA_VERSION",
    "compute_feature_schema_hash",
]
