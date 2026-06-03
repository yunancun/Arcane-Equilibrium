"""FND-2 PIT universe builder — package marker + 版本常數。

MODULE_NOTE:
  模塊用途：AEG-S1-FND-2 point-in-time（PIT）universe builder。從
    ``market.symbol_universe_snapshots``（V058）以**唯讀**方式產生 deterministic
    PIT universe artifact（含已 delisted symbol），供 AEG-S2 component (b) breadth
    ladder / (c) robustness matrix 消費。survivorship 控制核心：universe 必含窗內
    已 delist 的 symbol，絕不退化成 current-survivor-only。
  主要子模塊：
    - ``cohorts``：凍結的 core25 成員常數 + cohort/tier 定義。
    - ``builder``：純函數核心（lifecycle → lifetime mask → cohort/tier → include
      /exclude → universe rows），**0 DB 依賴**，全 synthetic 可測。
    - ``data_loader``：唯讀 PG SELECT（lifecycle 聚合 + latest 投影 + ticker tier
      排序源 + scanner overlap），``set_session(readonly=True)`` fail-closed。
    - ``artifact``：跨平台 artifact root + universe.csv/.parquet + summary.json +
      manifest.json + artifact_index.json + sha256 + universe_id digest。
    - ``harness``：CLI 編排（parse args → load → build → write → seed regression）。
  硬邊界：
    - read-only PG，0 DB write / 0 backfill / 0 schema / 0 IPC / 0 auth / 0 order。
    - 算法權威 = PA 設計報告 §4（修正版）：``listed_at``/``delisted_at`` 是唯一
      lifetime 權威；``first_seen_ts``/``last_seen_ts`` 僅診斷（snapshot ts 只跨
      27 天，coalesce 到 ts 會把舊上市幣的 alive_from 錯夾到 2026-05）。
    - 絕不 import 任何 ``control_api_v1/app/`` runtime 模組；絕不呼叫
      ``_fetch_historical_universe_snapshot_sync``；universe SQL 無 ``LIMIT`` /
      ``max_symbols`` / turnover 截斷（liquidity 只能 tier 排序，非 inclusion 條件）。
  依賴：psycopg2（延遲 import）+ 標準庫；parquet 經 duckdb/pyarrow（延遲 import，
    缺套件時 parquet 鏡像 skip，csv 為 SoT）。
"""

from __future__ import annotations

# builder 演算法 / artifact 欄序版本。任一影響 universe_id digest 的契約變更（欄序、
# lifetime 邏輯、cohort 定義）都必須升版，否則 determinism 對帳會誤判「DB 變了」。
BUILDER_VERSION = "fnd2.builder.v0.1"

# SQL query schema 版本（進 universe_id digest 與 manifest）。query 形狀（filter /
# 聚合 / latest 投影）變更時升版。
QUERY_SCHEMA_VERSION = "fnd2.query.v0.1"

# artifact manifest schema（AEG-S0 §1.4 對齊）。
MANIFEST_SCHEMA_VERSION = "aeg.alpha_history_run_manifest.v0.1"

# universe 行 artifact schema 版本（進 artifact_index）。
UNIVERSE_SCHEMA_VERSION = "fnd2.universe.v0.1"

__all__ = [
    "BUILDER_VERSION",
    "QUERY_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "UNIVERSE_SCHEMA_VERSION",
]
