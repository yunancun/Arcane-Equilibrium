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
