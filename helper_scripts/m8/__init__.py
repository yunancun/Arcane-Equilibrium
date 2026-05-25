"""
MODULE_NOTE
模塊用途：
    M8 anomaly_events helper_scripts/m8 入口。Sprint 2 Wave 1 W2-D 階段提供
    read-only query helper 給 Sprint 3 detector subscribe。Rust writer 在
    `rust/openclaw_engine/src/database/anomaly_event_writer.rs` 是寫入主路徑；
    本 Python sub-module 提供 cron / GUI / audit forensic 用的查詢 facade。

主要文件：
    - anomaly_event_query.py：read-only SELECT helper (get_recent_anomalies +
      get_amplification_cap_count)；對齊 V109 spec §5.3 SQL pattern。

依賴：
    - psycopg2 / asyncpg (workspace dep，視 caller 端決定)；
    - 不引 sqlalchemy ORM (對齊 helper_scripts/m4 範式)。

硬邊界：
    - Sprint 2 W2-D 階段：query-only，不寫；Sprint 3 detector wire 前置。
    - V109 schema 23 column 嚴格對齊；新增 column 必同步更新 Rust writer + 本 module。
    - engine_mode IN ('live','live_demo') for training filter (per CLAUDE.md §七)；
      其他 engine_mode 走 caller 端控制 (paper 學習資料源 / replay M11 例外)。
"""
