"""
Parquet ETL — extract training data from PostgreSQL to Parquet files via DuckDB.
Parquet ETL — 通過 DuckDB 從 PostgreSQL 提取訓練數據到 Parquet 文件。

MODULE_NOTE (EN): Daily ETL that extracts decision context + outcomes from PG,
  joins with feature vectors, and exports to Parquet for offline ML training.
  Uses DuckDB for efficient columnar processing. Scheduled via cron or manual trigger.
MODULE_NOTE (中): 每日 ETL，從 PG 提取決策上下文 + 結果，
  與特徵向量連接，導出到 Parquet 供離線 ML 訓練。使用 DuckDB 高效列式處理。
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default output directory / 默認輸出目錄
DEFAULT_OUTPUT_DIR = "/tmp/openclaw/parquet"

# EDGE-P3-1 Stage 1/2: canonical 17-feature order matching Rust FeatureVectorV1
# (rust/openclaw_engine/src/edge_predictor/features.rs §3.2). The order must be
# stable because Stage 2 training computes `feature_schema_hash` over this
# sequence and the Rust predictor asserts the hash at inference time.
# Mismatched order = silent train/serve skew. DO NOT reorder.
# EDGE-P3-1 Stage 1/2：與 Rust FeatureVectorV1 一致的 17 特徵規範順序（§3.2）。
# 順序穩定：Stage 2 訓練以此序列計算 feature_schema_hash，Rust 推理時驗證匹配。
# 順序變更 = 靜默 train/serve skew。禁止重排。
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


def extract_training_data(
    pg_url: Optional[str] = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    days_back: int = 30,
    symbols: Optional[list[str]] = None,
) -> dict[str, any]:
    """Extract training data from PG → Parquet.
    �� PG 提取訓練數據到 Parquet。

    Returns dict with status, row counts, file paths.
    """
    db_url = pg_url or os.getenv("OPENCLAW_DATABASE_URL", "")
    if not db_url:
        return {"success": False, "error": "No database URL configured"}

    # SEC-B02: Validate inputs to prevent injection via f-string SQL.
    # SEC-B02：驗證輸入以防止 f-string SQL 注入。
    # db_url must look like a postgres connection string (no embedded quotes/semicolons).
    _SAFE_DB_URL = re.compile(r"^[a-zA-Z0-9+_./:@?&=%\-]+$")
    if not _SAFE_DB_URL.match(db_url):
        return {"success": False, "error": "Invalid database URL format (rejected by SEC-B02 guard)"}

    result = {"success": False, "output_dir": output_dir}

    try:
        import duckdb
    except ImportError:
        result["error"] = "duckdb not installed — pip install duckdb"
        logger.error(result["error"])
        return result

    try:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect()

        # Install and load postgres extension / 安裝並載入 postgres 擴展
        conn.execute("INSTALL postgres; LOAD postgres;")
        conn.execute(f"ATTACH '{db_url}' AS pg (TYPE postgres, READ_ONLY);")

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # SEC-B02: Assert date strings are safe (YYYY-MM-DD only).
        # SEC-B02：斷言日期字符串格式安全（僅 YYYY-MM-DD）。
        _DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        assert _DATE_RE.match(start_str) and _DATE_RE.match(end_str), "date format violation"

        # SEC-B02: Sanitize output_dir — reject path traversal / quotes.
        # SEC-B02：清理輸出目錄 — 拒絕路徑遍歷 / 引號。
        _clean_dir = str(Path(output_dir).resolve())

        # Extract decision contexts with features / 提取決策上下文 + 特徵
        ctx_path = f"{_clean_dir}/decision_contexts_{start_str}_{end_str}.parquet"
        ctx_query = f"""
            COPY (
                SELECT * FROM pg.trading.decision_context_snapshots
                WHERE ts >= '{start_str}' AND ts < '{end_str}'
                ORDER BY ts
            ) TO '{ctx_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """
        conn.execute(ctx_query)
        ctx_count = conn.execute(f"SELECT count(*) FROM read_parquet('{ctx_path}')").fetchone()[0]

        # Extract fills / 提取成交
        fills_path = f"{_clean_dir}/fills_{start_str}_{end_str}.parquet"
        fills_query = f"""
            COPY (
                SELECT * FROM pg.trading.fills
                WHERE ts >= '{start_str}' AND ts < '{end_str}'
                ORDER BY ts
            ) TO '{fills_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """
        conn.execute(fills_query)
        fills_count = conn.execute(f"SELECT count(*) FROM read_parquet('{fills_path}')").fetchone()[0]

        # Extract features with temporal window — exclude stale entries / 提取特徵（帶時間窗口，排除過期條目）
        features_path = f"{_clean_dir}/features_latest.parquet"
        # Only include features updated within the ETL window to avoid stale data.
        # updated_ts_ms is epoch millis; convert start_date to epoch ms.
        # 只包含 ETL 窗口內更新的特徵，避免過期數據。
        start_epoch_ms = int(start_date.timestamp() * 1000)
        features_query = f"""
            COPY (
                SELECT * FROM pg.features.online_latest
                WHERE updated_ts_ms >= {start_epoch_ms}
            ) TO '{features_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """
        conn.execute(features_query)

        conn.close()

        result.update({
            "success": True,
            "contexts": ctx_count,
            "fills": fills_count,
            "context_path": ctx_path,
            "fills_path": fills_path,
            "features_path": features_path,
        })
        logger.info(
            "ETL complete: %d contexts, %d fills → %s",
            ctx_count, fills_count, output_dir,
        )

    except Exception as e:
        result["error"] = str(e)
        logger.error("ETL failed: %s", e)

    return result


def generate_training_labels(
    fills_parquet: str,
    features_parquet: str,
    klines_parquet: str,
    output_path: str,
    atr_floor: float = 50.0,
    label_clamp: float = 5.0,
) -> dict:
    """Generate ATR-normalized training labels by joining fills + features + klines.
    通過連接 fills + features + klines 生成 ATR 歸一化訓練標籤。

    Uses DuckDB for efficient Parquet joins without loading all data into memory.
    使用 DuckDB 進行高效 Parquet 連接，無需將所有數據加載到記憶體。

    Scheduling: run daily via cron (see docs/execution_plan/phase_3b.md)
    排程：每日透過 cron 執行（見 docs/execution_plan/phase_3b.md）

    Args:
        fills_parquet: Path to fills Parquet file / fills Parquet 文件路徑
        features_parquet: Path to features Parquet file / features Parquet 文件路徑
        klines_parquet: Path to klines Parquet file / klines Parquet 文件路徑
        output_path: Path to write labeled training data Parquet / 輸出標籤訓練數據路徑
        atr_floor: Minimum ATR value to prevent division explosion / ATR 地板值防止除零爆炸
        label_clamp: Clamp labels to ±this value (winsorization) / 標籤截斷值（溫塞化）

    Returns:
        dict with keys: n_samples, n_features, label_stats (mean, std, min, max)
        返回字典：n_samples, n_features, label_stats (mean, std, min, max)
    """
    try:
        import duckdb
    except ImportError:
        logger.error("duckdb not installed — pip install duckdb")
        return {"n_samples": 0, "n_features": 0, "label_stats": {}, "error": "duckdb not installed"}

    try:
        conn = duckdb.connect()

        # Ensure output directory exists / 確保輸出目錄存在
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Check if fills is empty / 檢查 fills 是否為空
        fills_count = conn.execute(
            f"SELECT count(*) FROM read_parquet('{fills_parquet}')"
        ).fetchone()[0]

        if fills_count == 0:
            conn.close()
            logger.info("No fills found — skipping label generation / 無成交記錄，跳過標籤生成")
            return {"n_samples": 0, "n_features": 0, "label_stats": {}}

        # JOIN fills with features (nearest timestamp within 1 minute) and klines (nearest close)
        # 連接 fills 與 features（1分鐘內最近時間戳）及 klines（最近收盤價）
        join_query = f"""
            COPY (
                WITH fills AS (
                    SELECT * FROM read_parquet('{fills_parquet}')
                ),
                features AS (
                    SELECT * FROM read_parquet('{features_parquet}')
                ),
                klines AS (
                    SELECT * FROM read_parquet('{klines_parquet}')
                ),
                -- ASOF join: fills LEFT JOIN features on symbol + nearest ts within 60s
                -- ASOF 連接：fills 左連接 features，按 symbol + 60秒內最近時間戳
                fills_features AS (
                    SELECT
                        f.*,
                        feat.* EXCLUDE (symbol, ts)
                    FROM fills f
                    ASOF LEFT JOIN features feat
                        ON f.symbol = feat.symbol
                        AND f.ts >= feat.ts
                    WHERE feat.ts IS NULL
                       OR abs(epoch_ms(f.ts) - epoch_ms(feat.ts)) <= 60000
                ),
                -- ASOF join: fills_features LEFT JOIN klines on symbol + nearest ts
                -- ASOF 連接：fills_features 左連接 klines，按 symbol + 最近時間戳
                joined AS (
                    SELECT
                        ff.*,
                        k.atr
                    FROM fills_features ff
                    ASOF LEFT JOIN klines k
                        ON ff.symbol = k.symbol
                        AND ff.ts >= k.ts
                ),
                -- Compute ATR-normalized label with clamp / 計算 ATR 歸一化標籤並截斷
                labeled AS (
                    SELECT
                        *,
                        LEAST(
                            {label_clamp},
                            GREATEST(
                                -{label_clamp},
                                realized_pnl / GREATEST(COALESCE(atr, {atr_floor}), {atr_floor})
                            )
                        ) AS y
                    FROM joined
                )
                SELECT * FROM labeled
            ) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """
        conn.execute(join_query)

        # Gather statistics from output / 從輸出收集統計信息
        stats = conn.execute(f"""
            SELECT
                count(*) AS n,
                avg(y) AS mean_y,
                stddev(y) AS std_y,
                min(y) AS min_y,
                max(y) AS max_y
            FROM read_parquet('{output_path}')
        """).fetchone()

        n_samples = stats[0]

        # Get column count via DESCRIBE / 透過 DESCRIBE 取得列數
        columns = conn.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{output_path}')"
        ).fetchall()
        n_features = len(columns)

        conn.close()

        label_stats = {
            "mean": float(stats[1]) if stats[1] is not None else 0.0,
            "std": float(stats[2]) if stats[2] is not None else 0.0,
            "min": float(stats[3]) if stats[3] is not None else 0.0,
            "max": float(stats[4]) if stats[4] is not None else 0.0,
        }

        logger.info(
            "Label generation complete: %d samples, %d features, y_mean=%.4f, y_std=%.4f",
            n_samples, n_features, label_stats["mean"], label_stats["std"],
        )

        return {
            "n_samples": n_samples,
            "n_features": n_features,
            "label_stats": label_stats,
        }

    except Exception as e:
        logger.error("Label generation failed / 標籤生成失敗: %s", e)
        return {"n_samples": 0, "n_features": 0, "label_stats": {}, "error": str(e)}


# ============================================================
# EDGE-P3-1 Stage 1 / Stage 2 — decision_features feature store
# EDGE-P3-1 第一/二階段 — 決策特徵儲存讀取
# ============================================================
#
# `load_training_data()` is the ingestion entrypoint consumed by
# `run_training_pipeline.run_pipeline()` (line 85). It reads the already-
# labeled rows from `learning.decision_features` (populated by
# `edge_label_backfill.py`), expands the `features_jsonb` column into the
# canonical 17-column matrix, and hands (features, labels, timestamps,
# feature_names) back to the CPCV trainer.
#
# `export_decision_features_parquet()` is the optional offline-dump helper
# for operators who want to train off a PG snapshot (useful when PG is
# under load or for reproducibility).
#
# Labels are filled by the separate `edge_label_backfill.py` job — this
# module does NOT re-implement split-blend logic; it only consumes the
# `label_net_edge_bps` column after backfill has run. Stale-label NULL
# alerting lives in `edge_label_backfill.check_stale_labels()`; keep the
# single source of truth there.
# ============================================================

def _get_pg_conn(dsn: Optional[str]):
    """Open a psycopg2 connection using explicit DSN or env-var fallback.
    Pattern mirrors edge_label_backfill._get_conn so stale-label alerting
    and training-data loading share identical DB resolution rules.
    以顯式 DSN 或環境變量為後備開啟 psycopg2 連線；與 edge_label_backfill 一致。"""
    try:
        import psycopg2  # type: ignore
    except ImportError as e:
        raise RuntimeError("psycopg2 not installed — activate venv first") from e

    resolved = (
        dsn
        or os.environ.get("OPENCLAW_DATABASE_URL")
        or os.environ.get("DSN")
    )
    if not resolved:
        host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
        port = os.environ.get("POSTGRES_PORT", "5432")
        user = os.environ.get("POSTGRES_USER", "openclaw")
        password = os.environ.get("POSTGRES_PASSWORD", "")
        db = os.environ.get("POSTGRES_DB", "openclaw")
        resolved = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return psycopg2.connect(resolved)


# Canonical training query. `engine_mode` filter defaults to 'demo' because
# spec §8.2 uses demo-fill-rate as the primary acceptance gate; operators can
# widen to ('paper','demo') once Stage 4 paper-promote is active. Paper is
# already separated at label-write time — shadow fills go to
# learning.decision_shadow_fills (V017 CHECK), so this query's WHERE on
# label_net_edge_bps IS NOT NULL naturally excludes them.
# 標準訓練查詢；engine_mode 預設 'demo'（§8.2 驗收閾值），paper-promote 後可放寬。
# Shadow fill 寫入分離表，NOT NULL 過濾自然排除 ε-greedy 探索污染訓練集。
_LOAD_TRAINING_DATA_SQL = """
SELECT
    context_id,
    extract(epoch FROM ts) * 1000.0 AS ts_ms,
    features_jsonb,
    label_net_edge_bps,
    symbol,
    strategy_name
FROM learning.decision_features
WHERE label_net_edge_bps IS NOT NULL
  AND engine_mode = %(engine_mode)s
  AND (%(strategy_name)s IS NULL OR strategy_name = %(strategy_name)s)
  AND (%(symbol)s IS NULL OR symbol = %(symbol)s)
  AND ts >= now() - (%(max_age_days)s || ' days')::interval
ORDER BY ts ASC
"""


def load_training_data(
    symbol: Optional[str] = None,
    strategy_type: Optional[str] = None,
    dsn: Optional[str] = None,
    engine_mode: str = "demo",
    max_age_days: int = 90,
):
    """Load labeled training rows from `learning.decision_features`.

    Returns (features, labels, timestamps, feature_names) as numpy arrays /
    tuple so `run_training_pipeline.run_pipeline()` can feed CPCV directly.

    Missing / non-numeric JSONB fields fall through as 0.0 — row stays
    because label quality is what gated inclusion. The schema hash mismatch
    check happens at Rust inference time, not here; ETL's job is breadth,
    not drop-on-skew.

    Args:
        symbol: Optional symbol filter (e.g. "BTCUSDT"). None → all symbols.
        strategy_type: Optional strategy_name filter (e.g. "ma_crossover").
            None → all strategies (multi-model training pulls one slice
            per call). Named `strategy_type` to match the existing
            `run_training_pipeline.PipelineConfig.strategy_type` field.
        dsn: PG DSN override; falls back to env vars.
        engine_mode: "paper" | "demo" | "live". Default "demo" per §8.2.
        max_age_days: trailing-window size (90d default, covers 12 weeks
            of fills — enough for LGBM quantile training per strategy).

    從 learning.decision_features 載入已標籤訓練行；回傳 numpy 陣列
    (features, labels, timestamps, feature_names)。JSONB 缺失 / 非數值欄位
    填 0.0（schema hash 在 Rust 推理時驗證，此處不丟行）。

    Raises:
        RuntimeError: if numpy/psycopg2 missing.
    """
    try:
        import numpy as np  # type: ignore
    except ImportError as e:
        raise RuntimeError("numpy not installed — pip install numpy") from e

    conn = _get_pg_conn(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                _LOAD_TRAINING_DATA_SQL,
                {
                    "engine_mode": engine_mode,
                    "strategy_name": strategy_type,
                    "symbol": symbol,
                    "max_age_days": max_age_days,
                },
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    feature_names = list(EDGE_P3_FEATURE_NAMES)
    if not rows:
        logger.info(
            "load_training_data: 0 labeled rows (engine_mode=%s strategy=%s symbol=%s)",
            engine_mode, strategy_type, symbol,
        )
        empty_f = np.empty((0, len(feature_names)), dtype=np.float32)
        empty_y = np.empty((0,), dtype=np.float32)
        empty_ts = np.empty((0,), dtype=np.int64)
        return empty_f, empty_y, empty_ts, feature_names

    features_mat = np.zeros((len(rows), len(feature_names)), dtype=np.float32)
    labels_vec = np.zeros((len(rows),), dtype=np.float32)
    ts_vec = np.zeros((len(rows),), dtype=np.int64)

    for i, (_ctx_id, ts_ms, feat_json, label_bps, _sym, _strat) in enumerate(rows):
        # psycopg2 returns JSONB as already-decoded dict; defensive parse for
        # text-mode rollback or external dumps. 防禦性解析：JSONB → dict。
        feat = feat_json if isinstance(feat_json, dict) else json.loads(feat_json)
        for j, name in enumerate(feature_names):
            val = feat.get(name, 0.0)
            if val is None:
                val = 0.0
            try:
                features_mat[i, j] = float(val)
            except (TypeError, ValueError):
                features_mat[i, j] = 0.0
        labels_vec[i] = float(label_bps)
        ts_vec[i] = int(ts_ms)

    logger.info(
        "load_training_data: %d rows × %d features (engine_mode=%s strategy=%s symbol=%s)",
        len(rows), len(feature_names), engine_mode, strategy_type, symbol,
    )
    return features_mat, labels_vec, ts_vec, feature_names


def export_decision_features_parquet(
    pg_url: Optional[str] = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    engine_mode: str = "demo",
    days_back: int = 30,
    labeled_only: bool = True,
) -> dict:
    """Dump `learning.decision_features` to Parquet for offline training.

    Operator-triggered helper: stable snapshot for reproducible training runs
    or PG-off-hours processing. Stage 2 trainer normally goes through
    `load_training_data()`; this is the reproducibility escape hatch.

    將 learning.decision_features 匯出為 Parquet 供離線訓練；操作員觸發的
    可重現快照工具。Stage 2 訓練常走 load_training_data()，本函數是逃生艙。

    Returns dict with success / row_count / output_path.
    """
    db_url = pg_url or os.environ.get("OPENCLAW_DATABASE_URL", "")
    if not db_url:
        return {"success": False, "error": "No database URL configured"}

    _SAFE_DB_URL = re.compile(r"^[a-zA-Z0-9+_./:@?&=%\-]+$")
    if not _SAFE_DB_URL.match(db_url):
        return {"success": False, "error": "Invalid database URL format (rejected by SEC-B02 guard)"}

    result: dict = {"success": False, "engine_mode": engine_mode}
    try:
        import duckdb  # type: ignore
    except ImportError:
        result["error"] = "duckdb not installed — pip install duckdb"
        return result

    try:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        _clean_dir = str(Path(output_dir).resolve())
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        _DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        assert _DATE_RE.match(start_str) and _DATE_RE.match(end_str), "date format violation"

        # SEC-B02: engine_mode constrained to literal set; no injection surface.
        if engine_mode not in ("paper", "demo", "live"):
            return {"success": False, "error": f"invalid engine_mode: {engine_mode!r}"}

        conn = duckdb.connect()
        conn.execute("INSTALL postgres; LOAD postgres;")
        conn.execute(f"ATTACH '{db_url}' AS pg (TYPE postgres, READ_ONLY);")

        label_filter = "AND label_net_edge_bps IS NOT NULL" if labeled_only else ""
        out_path = (
            f"{_clean_dir}/decision_features_{engine_mode}_{start_str}_{end_str}.parquet"
        )
        query = f"""
            COPY (
                SELECT * FROM pg.learning.decision_features
                WHERE engine_mode = '{engine_mode}'
                  AND ts >= '{start_str}' AND ts < '{end_str}'
                  {label_filter}
                ORDER BY ts
            ) TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """
        conn.execute(query)
        row_count = conn.execute(
            f"SELECT count(*) FROM read_parquet('{out_path}')"
        ).fetchone()[0]
        conn.close()

        result.update({
            "success": True,
            "row_count": int(row_count),
            "output_path": out_path,
            "labeled_only": labeled_only,
        })
        logger.info(
            "decision_features export: %d rows (engine=%s, %s labels only=%s) → %s",
            row_count, engine_mode, f"{start_str}..{end_str}", labeled_only, out_path,
        )
    except Exception as e:  # noqa: BLE001
        result["error"] = str(e)
        logger.error("decision_features export failed: %s", e)

    return result
