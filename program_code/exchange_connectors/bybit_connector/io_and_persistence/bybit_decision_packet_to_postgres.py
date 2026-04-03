#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_decision_packet_to_postgres.py
Role:
- 将 decision packet 落库
- 服务于历史审计和后续分析

Purpose in system:
- 提供 packet 级别的持久化追踪

Upstream:
- bybit_build_decision_packet.py

Maintenance notes:
- 不负责业务判断
- 若调整 packet 表结构，需注意历史兼容性
'''

"""

import json
import subprocess
from pathlib import Path
import os

PACKET_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/decision_packets/bybit/bybit_decision_packet_latest.json")
POSTGRES_CONTAINER = "trading_postgres"
SQL_SCHEMA = "trading_raw"
SQL_TABLE = "decision_packets"

def main():
    raw = PACKET_PATH.read_text(encoding="utf-8")
    packet = json.loads(raw)
    safe = raw.replace("'", "''")
    safe_path = str(PACKET_PATH).replace("'", "''")

    sql = f"""
CREATE SCHEMA IF NOT EXISTS {SQL_SCHEMA};

CREATE TABLE IF NOT EXISTS {SQL_SCHEMA}.{SQL_TABLE} (
    id BIGSERIAL PRIMARY KEY,
    exchange_name TEXT NOT NULL,
    packet_type TEXT NOT NULL,
    packet_version TEXT,
    ts_ms BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_file TEXT NOT NULL,
    risk_flags JSONB,
    local_decision_hints JSONB,
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decision_packets_exchange_ts
    ON {SQL_SCHEMA}.{SQL_TABLE} (exchange_name, ts_ms DESC);

INSERT INTO {SQL_SCHEMA}.{SQL_TABLE} (
    exchange_name,
    packet_type,
    packet_version,
    ts_ms,
    source_file,
    risk_flags,
    local_decision_hints,
    payload
)
SELECT
    COALESCE(('{safe}'::jsonb ->> 'exchange'), 'unknown'),
    COALESCE(('{safe}'::jsonb ->> 'packet_type'), 'unknown'),
    ('{safe}'::jsonb ->> 'packet_version'),
    COALESCE((('{safe}'::jsonb ->> 'ts_ms')::bigint), 0),
    '{safe_path}',
    ('{safe}'::jsonb -> 'risk_flags'),
    ('{safe}'::jsonb -> 'local_decision_hints'),
    '{safe}'::jsonb;
"""

    cmd = [
        "docker", "exec", "-i", POSTGRES_CONTAINER,
        "sh", "-lc",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f -'
    ]
    proc = subprocess.run(cmd, input=sql, text=True, capture_output=True)

    result = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "packet_ts_ms": packet.get("ts_ms"),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
