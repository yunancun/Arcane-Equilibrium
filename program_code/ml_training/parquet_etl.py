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

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default output directory / 默認輸出目錄
DEFAULT_OUTPUT_DIR = "/tmp/openclaw/parquet"


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

        # Extract decision contexts with features / 提取決策上下文 + 特徵
        ctx_path = f"{output_dir}/decision_contexts_{start_str}_{end_str}.parquet"
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
        fills_path = f"{output_dir}/fills_{start_str}_{end_str}.parquet"
        fills_query = f"""
            COPY (
                SELECT * FROM pg.trading.fills
                WHERE ts >= '{start_str}' AND ts < '{end_str}'
                ORDER BY ts
            ) TO '{fills_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """
        conn.execute(fills_query)
        fills_count = conn.execute(f"SELECT count(*) FROM read_parquet('{fills_path}')").fetchone()[0]

        # Extract features / 提取特徵
        features_path = f"{output_dir}/features_latest.parquet"
        features_query = f"""
            COPY (
                SELECT * FROM pg.features.online_latest
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
