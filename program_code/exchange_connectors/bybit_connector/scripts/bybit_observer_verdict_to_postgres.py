#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_observer_verdict_to_postgres.py
Role:
- 将 observer verdict 落库

Purpose in system:
- 为 verdict 历史追踪和审计提供持久化能力

Upstream:
- bybit_build_observer_verdict.py
'''

"""

import json
import subprocess
from pathlib import Path

VERDICT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/verdicts/bybit/bybit_observer_verdict_latest.json")
POSTGRES_CONTAINER = "trading_postgres"
SQL_SCHEMA = "trading_raw"
SQL_TABLE = "observer_verdicts"

def main():
    raw = VERDICT_PATH.read_text(encoding="utf-8")
    verdict = json.loads(raw)
    safe = raw.replace("'", "''")
    safe_path = str(VERDICT_PATH).replace("'", "''")

    sql = f"""
CREATE SCHEMA IF NOT EXISTS {SQL_SCHEMA};

CREATE TABLE IF NOT EXISTS {SQL_SCHEMA}.{SQL_TABLE} (
    id BIGSERIAL PRIMARY KEY,
    exchange_name TEXT NOT NULL,
    verdict_type TEXT NOT NULL,
    verdict_version TEXT,
    ts_ms BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_file TEXT NOT NULL,
    source_packet_ts_ms BIGINT,
    verdict_code TEXT,
    execution_allowed BOOLEAN,
    should_refresh_rest BOOLEAN,
    should_query_ai BOOLEAN,
    urgency TEXT,
    risk_flags JSONB,
    reasons JSONB,
    next_steps JSONB,
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observer_verdicts_exchange_ts
    ON {SQL_SCHEMA}.{SQL_TABLE} (exchange_name, ts_ms DESC);

INSERT INTO {SQL_SCHEMA}.{SQL_TABLE} (
    exchange_name,
    verdict_type,
    verdict_version,
    ts_ms,
    source_file,
    source_packet_ts_ms,
    verdict_code,
    execution_allowed,
    should_refresh_rest,
    should_query_ai,
    urgency,
    risk_flags,
    reasons,
    next_steps,
    payload
)
SELECT
    COALESCE(('{safe}'::jsonb ->> 'exchange'), 'unknown'),
    COALESCE(('{safe}'::jsonb ->> 'verdict_type'), 'unknown'),
    ('{safe}'::jsonb ->> 'verdict_version'),
    COALESCE((('{safe}'::jsonb ->> 'ts_ms')::bigint), 0),
    '{safe_path}',
    COALESCE((('{safe}'::jsonb ->> 'source_packet_ts_ms')::bigint), 0),
    ('{safe}'::jsonb ->> 'verdict_code'),
    (('{safe}'::jsonb ->> 'execution_allowed')::boolean),
    (('{safe}'::jsonb ->> 'should_refresh_rest')::boolean),
    (('{safe}'::jsonb ->> 'should_query_ai')::boolean),
    ('{safe}'::jsonb ->> 'urgency'),
    ('{safe}'::jsonb -> 'risk_flags'),
    ('{safe}'::jsonb -> 'reasons'),
    ('{safe}'::jsonb -> 'next_steps'),
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
        "verdict_ts_ms": verdict.get("ts_ms"),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
