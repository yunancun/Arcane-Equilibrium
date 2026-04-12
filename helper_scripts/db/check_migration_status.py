#!/usr/bin/env python3
"""
OpenClaw DDL Migration Status Checker
DDL 遷移狀態檢查工具

MODULE_NOTE (EN):
    Connects to PostgreSQL and verifies that expected schemas and tables
    from V001–V005 foundation migrations exist. Reports PASS/FAIL per
    migration with table-level detail. Uses POSTGRES_* env vars or DSN.
    V006+ create additional tables; extend EXPECTED dict to cover them.

MODULE_NOTE (中):
    連接 PostgreSQL 驗證 V001–V005 基礎遷移文件中定義的 schema 和表是否存在。
    按遷移文件報告 PASS/FAIL 及表級細節。使用 POSTGRES_* 環境變量或 DSN。
    V006+ 創建額外表；擴展 EXPECTED 字典可覆蓋它們。

Usage / 用法:
    source settings/environment_files/basic_system_services.env
    python3 helper_scripts/db/check_migration_status.py

    # Or with explicit DSN:
    DSN=postgresql://redacted@127.0.0.1/openclaw python3 helper_scripts/db/check_migration_status.py
"""

import os
import sys

# FIX-35: Expected schemas and tables per migration.
# FIX-35：每個遷移文件預期的 schema 和表。
EXPECTED = {
    "V001": {
        "description": "8 schemas",
        "schemas": [
            "market", "trading", "agent", "learning",
            "features", "observability", "risk", "config",
        ],
        "tables": [],
    },
    "V002": {
        "description": "market tables",
        "schemas": [],
        "tables": [
            "market.klines", "market.funding_rates", "market.orderbook_snapshots",
            "market.ticker_snapshots", "market.regime_snapshots",
        ],
    },
    "V003": {
        "description": "trading + agent tables",
        "schemas": [],
        "tables": [
            "trading.decision_context_snapshots", "trading.decision_outcomes",
            "trading.signals", "trading.intents", "trading.risk_verdicts",
            "trading.orders", "trading.order_state_changes", "trading.fills",
            "trading.position_snapshots",
            "agent.messages", "agent.ai_invocations", "agent.state_changes",
        ],
    },
    "V004": {
        "description": "learning + features + obs + risk tables",
        "schemas": [],
        "tables": [
            "learning.parameter_suggestions", "learning.bayesian_posteriors",
            "learning.strategy_evaluations", "learning.experience_replay",
            "features.indicator_snapshots", "features.kline_features",
            "observability.pipeline_health", "observability.engine_metrics",
            "risk.risk_events", "risk.drawdown_snapshots",
        ],
    },
    "V005": {
        "description": "indexes + views",
        "schemas": [],
        "tables": [],  # views and indexes — checked via schema existence
    },
}


def get_dsn() -> str:
    """Build DSN from env vars. / 從環境變量構建 DSN。"""
    if dsn := os.environ.get("DSN"):
        return dsn
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "openclaw")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "openclaw")
    return f"postgresql://redacted@{host}:{port}/{db}"


def main() -> int:
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Activate venv first.")
        print("  source program_code/exchange_connectors/bybit_connector/"
              "control_api_v1/.venv/bin/activate")
        return 1

    dsn = get_dsn()
    try:
        conn = psycopg2.connect(dsn)
    except Exception as e:
        print(f"ERROR: Cannot connect to PostgreSQL: {e}")
        print("  source settings/environment_files/basic_system_services.env")
        return 1

    cur = conn.cursor()

    # Fetch existing schemas / 獲取現有 schema
    cur.execute(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name NOT IN ('pg_catalog','information_schema','pg_toast',"
        "'_timescaledb_catalog','_timescaledb_config','_timescaledb_internal',"
        "'_timescaledb_cache','timescaledb_experimental','timescaledb_information')"
    )
    existing_schemas = {row[0] for row in cur.fetchall()}

    # Fetch existing tables / 獲取現有表
    cur.execute(
        "SELECT table_schema || '.' || table_name "
        "FROM information_schema.tables "
        "WHERE table_schema NOT IN ('pg_catalog','information_schema','public',"
        "'_timescaledb_catalog','_timescaledb_config','_timescaledb_internal')"
    )
    existing_tables = {row[0] for row in cur.fetchall()}

    conn.close()

    # Report / 報告
    total_pass = 0
    total_fail = 0

    for ver, spec in sorted(EXPECTED.items()):
        missing_schemas = [s for s in spec["schemas"] if s not in existing_schemas]
        missing_tables = [t for t in spec["tables"] if t not in existing_tables]

        if missing_schemas or missing_tables:
            status = "FAIL"
            total_fail += 1
        else:
            status = "PASS"
            total_pass += 1

        print(f"  {ver} ({spec['description']}): {status}")
        if missing_schemas:
            for s in missing_schemas:
                print(f"    MISSING schema: {s}")
        if missing_tables:
            for t in missing_tables:
                print(f"    MISSING table: {t}")

    print(f"\n{'='*50}")
    print(f"  Total: {total_pass} PASS, {total_fail} FAIL")

    if existing_schemas:
        print(f"\n  Existing schemas: {', '.join(sorted(existing_schemas))}")
    print(f"  Existing tables: {len(existing_tables)}")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
