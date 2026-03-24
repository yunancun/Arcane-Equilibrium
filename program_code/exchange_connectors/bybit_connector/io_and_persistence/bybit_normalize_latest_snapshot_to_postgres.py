#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_normalize_latest_snapshot_to_postgres.py
Role:
- 将 snapshot 数据进一步规范化写入 Postgres 表
- 方便后续检索、审计、历史分析

Purpose in system:
- 提供持久化数据底座
- 不负责最终状态判断

Upstream:
- bybit_snapshot_to_postgres.py

Maintenance notes:
- 修改表结构前，需确认历史兼容性
- 当前这层主要做“落库”和“结构化”，不承担 observer verdict 逻辑
'''

"""

import json
import subprocess
from pathlib import Path

SNAPSHOT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json")
POSTGRES_CONTAINER = "trading_postgres"
SQL_SCHEMA = "trading_raw"

def q(v):
    if v is None:
        return "NULL"
    s = str(v).replace("'", "''")
    return f"'{s}'"

def qb(v):
    if v is None:
        return "NULL"
    return "TRUE" if bool(v) else "FALSE"

def qj(obj):
    s = json.dumps(obj, ensure_ascii=False).replace("'", "''")
    return f"'{s}'::jsonb"

def load_snapshot():
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

def build_sql(snapshot: dict) -> str:
    ts_ms = snapshot.get("ts_ms", 0)
    payload = snapshot.get("payload", {})

    account = payload.get("account") or {}
    positions = payload.get("positions") or {}
    order_history = payload.get("order_history") or {}
    execution_history = payload.get("execution_history") or {}

    account_resp = (((account.get("response") or {}).get("result") or {}).get("list") or [])
    account_row = account_resp[0] if account_resp else {}
    account_type = account_row.get("accountType")
    total_equity = account_row.get("totalEquity")
    total_wallet_balance = account_row.get("totalWalletBalance")
    total_available_balance = account_row.get("totalAvailableBalance")
    coins = account_row.get("coin") or []

    position_list = (((positions.get("response") or {}).get("result") or {}).get("list") or [])
    order_list = (((order_history.get("response") or {}).get("result") or {}).get("list") or [])

    exec_spot = ((execution_history.get("spot") or {}).get("items") or [])
    exec_linear = ((execution_history.get("linear") or {}).get("items") or [])
    exec_list = exec_spot + exec_linear

    lines = []

    lines.append(f"""
CREATE SCHEMA IF NOT EXISTS {SQL_SCHEMA};

CREATE TABLE IF NOT EXISTS {SQL_SCHEMA}.bybit_account_coin_snapshots (
    id BIGSERIAL PRIMARY KEY,
    snapshot_ts_ms BIGINT NOT NULL,
    source_snapshot_type TEXT DEFAULT 'bybit_system_snapshot',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    account_type TEXT,
    total_equity TEXT,
    total_wallet_balance TEXT,
    total_available_balance TEXT,
    coin TEXT,
    equity TEXT,
    wallet_balance TEXT,
    usd_value TEXT,
    free_balance TEXT,
    locked TEXT,
    unrealised_pnl TEXT,
    raw_payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS {SQL_SCHEMA}.bybit_position_snapshots (
    id BIGSERIAL PRIMARY KEY,
    snapshot_ts_ms BIGINT NOT NULL,
    source_snapshot_type TEXT DEFAULT 'bybit_system_snapshot',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category TEXT,
    symbol TEXT,
    side TEXT,
    size TEXT,
    avg_price TEXT,
    position_value TEXT,
    unrealised_pnl TEXT,
    mark_price TEXT,
    leverage TEXT,
    liq_price TEXT,
    raw_payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS {SQL_SCHEMA}.bybit_order_history_raw (
    id BIGSERIAL PRIMARY KEY,
    snapshot_ts_ms BIGINT NOT NULL,
    source_snapshot_type TEXT DEFAULT 'bybit_system_snapshot',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category TEXT,
    symbol TEXT,
    order_id TEXT,
    order_link_id TEXT,
    side TEXT,
    order_type TEXT,
    order_status TEXT,
    price TEXT,
    qty TEXT,
    cum_exec_qty TEXT,
    cum_exec_value TEXT,
    created_time TEXT,
    updated_time TEXT,
    raw_payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS {SQL_SCHEMA}.bybit_execution_history_raw (
    id BIGSERIAL PRIMARY KEY,
    snapshot_ts_ms BIGINT NOT NULL,
    source_snapshot_type TEXT DEFAULT 'bybit_system_snapshot',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category TEXT,
    symbol TEXT,
    order_id TEXT,
    order_link_id TEXT,
    exec_id TEXT,
    side TEXT,
    order_price TEXT,
    order_qty TEXT,
    exec_price TEXT,
    exec_qty TEXT,
    exec_value TEXT,
    exec_fee TEXT,
    fee_currency TEXT,
    is_maker BOOLEAN,
    exec_type TEXT,
    exec_time TEXT,
    raw_payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bybit_account_coin_snapshots_ts
    ON {SQL_SCHEMA}.bybit_account_coin_snapshots (snapshot_ts_ms DESC);

CREATE INDEX IF NOT EXISTS idx_bybit_position_snapshots_ts
    ON {SQL_SCHEMA}.bybit_position_snapshots (snapshot_ts_ms DESC);

CREATE INDEX IF NOT EXISTS idx_bybit_order_history_raw_ts
    ON {SQL_SCHEMA}.bybit_order_history_raw (snapshot_ts_ms DESC);

CREATE INDEX IF NOT EXISTS idx_bybit_execution_history_raw_ts
    ON {SQL_SCHEMA}.bybit_execution_history_raw (snapshot_ts_ms DESC);
""")

    for c in coins:
        free_balance = c.get("availableToWithdraw")
        lines.append(f"""
INSERT INTO {SQL_SCHEMA}.bybit_account_coin_snapshots (
    snapshot_ts_ms, source_snapshot_type, account_type, total_equity, total_wallet_balance, total_available_balance,
    coin, equity, wallet_balance, usd_value, free_balance, locked, unrealised_pnl, raw_payload
) VALUES (
    {ts_ms}, 'bybit_system_snapshot', {q(account_type)}, {q(total_equity)}, {q(total_wallet_balance)}, {q(total_available_balance)},
    {q(c.get("coin"))}, {q(c.get("equity"))}, {q(c.get("walletBalance"))}, {q(c.get("usdValue"))},
    {q(free_balance)}, {q(c.get("locked"))}, {q(c.get("unrealisedPnl"))}, {qj(c)}
)
ON CONFLICT (snapshot_ts_ms, source_snapshot_type, coin) DO NOTHING;
""")

    for p in position_list:
        lines.append(f"""
INSERT INTO {SQL_SCHEMA}.bybit_position_snapshots (
    snapshot_ts_ms, source_snapshot_type, category, symbol, side, size, avg_price, position_value,
    unrealised_pnl, mark_price, leverage, liq_price, raw_payload
) VALUES (
    {ts_ms}, 'bybit_system_snapshot', {q(((positions.get("response") or {}).get("result") or {}).get("category"))},
    {q(p.get("symbol"))}, {q(p.get("side"))}, {q(p.get("size"))}, {q(p.get("avgPrice"))},
    {q(p.get("positionValue"))}, {q(p.get("unrealisedPnl"))}, {q(p.get("markPrice"))},
    {q(p.get("leverage"))}, {q(p.get("liqPrice"))}, {qj(p)}
)
ON CONFLICT (snapshot_ts_ms, source_snapshot_type, category, symbol, side) DO NOTHING;
""")

    for o in order_list:
        lines.append(f"""
INSERT INTO {SQL_SCHEMA}.bybit_order_history_raw (
    snapshot_ts_ms, source_snapshot_type, category, symbol, order_id, order_link_id, side, order_type,
    order_status, price, qty, cum_exec_qty, cum_exec_value, created_time, updated_time, raw_payload
) VALUES (
    {ts_ms}, 'bybit_system_snapshot', {q(((order_history.get("response") or {}).get("result") or {}).get("category"))},
    {q(o.get("symbol"))}, {q(o.get("orderId"))}, {q(o.get("orderLinkId"))}, {q(o.get("side"))},
    {q(o.get("orderType"))}, {q(o.get("orderStatus"))}, {q(o.get("price"))}, {q(o.get("qty"))},
    {q(o.get("cumExecQty"))}, {q(o.get("cumExecValue"))}, {q(o.get("createdTime"))},
    {q(o.get("updatedTime"))}, {qj(o)}
)
ON CONFLICT (snapshot_ts_ms, source_snapshot_type, order_id) DO NOTHING;
""")

    for e in exec_list:
        lines.append(f"""
INSERT INTO {SQL_SCHEMA}.bybit_execution_history_raw (
    snapshot_ts_ms, source_snapshot_type, category, symbol, order_id, order_link_id, exec_id, side,
    order_price, order_qty, exec_price, exec_qty, exec_value, exec_fee, fee_currency,
    is_maker, exec_type, exec_time, raw_payload
) VALUES (
    {ts_ms}, 'bybit_system_snapshot', {q(e.get("category"))}, {q(e.get("symbol"))}, {q(e.get("orderId"))},
    {q(e.get("orderLinkId"))}, {q(e.get("execId"))}, {q(e.get("side"))},
    {q(e.get("orderPrice"))}, {q(e.get("orderQty"))}, {q(e.get("execPrice"))},
    {q(e.get("execQty"))}, {q(e.get("execValue"))}, {q(e.get("execFee"))},
    {q(e.get("feeCurrency"))}, {qb(e.get("isMaker"))}, {q(e.get("execType"))},
    {q(e.get("execTime"))}, {qj(e)}
)
ON CONFLICT (snapshot_ts_ms, source_snapshot_type, exec_id) DO NOTHING;
""")

    return "\n".join(lines)

def run_sql(sql: str):
    cmd = [
        "docker", "exec", "-i", POSTGRES_CONTAINER,
        "sh", "-lc",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f -'
    ]
    proc = subprocess.run(cmd, input=sql, text=True, capture_output=True)
    return proc

def main():
    snapshot = load_snapshot()
    sql = build_sql(snapshot)
    proc = run_sql(sql)

    result = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "snapshot_ts_ms": snapshot.get("ts_ms"),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
