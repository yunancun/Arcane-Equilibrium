#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

WS_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/ws")
LATEST_SUMMARY = WS_DIR / "bybit_private_ws_smoke_latest.json"
POSTGRES_CONTAINER = "trading_postgres"
SQL_SCHEMA = "trading_raw"

def q(v):
    if v is None:
        return "NULL"
    s = str(v).replace("'", "''")
    return f"'{s}'"

def qj(obj):
    s = json.dumps(obj, ensure_ascii=False).replace("'", "''")
    return f"'{s}'::jsonb"

def pick_latest_jsonl():
    files = sorted(WS_DIR.glob("bybit_private_ws_events_*.jsonl"))
    if not files:
        raise FileNotFoundError("no ws jsonl files found")
    return files[-1]

def build_sql(summary: dict, jsonl_path: Path) -> str:
    ts_ms = summary.get("ts_ms")
    lines = []

    lines.append(f"""
CREATE SCHEMA IF NOT EXISTS {SQL_SCHEMA};

CREATE TABLE IF NOT EXISTS {SQL_SCHEMA}.bybit_ws_private_events_raw (
    id BIGSERIAL PRIMARY KEY,
    session_ts_ms BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_file TEXT NOT NULL,
    event_kind TEXT,
    event_ts_ms BIGINT,
    topic TEXT,
    op TEXT,
    success BOOLEAN,
    conn_id TEXT,
    raw_payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bybit_ws_private_events_raw_session
    ON {SQL_SCHEMA}.bybit_ws_private_events_raw (session_ts_ms DESC);

CREATE INDEX IF NOT EXISTS idx_bybit_ws_private_events_raw_topic
    ON {SQL_SCHEMA}.bybit_ws_private_events_raw (topic);

CREATE INDEX IF NOT EXISTS idx_bybit_ws_private_events_raw_op
    ON {SQL_SCHEMA}.bybit_ws_private_events_raw (op);
""")

    with jsonl_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            row = json.loads(raw_line)
            data = row.get("data")
            if not isinstance(data, dict):
                data = {"value": data}

            lines.append(f"""
INSERT INTO {SQL_SCHEMA}.bybit_ws_private_events_raw (
    session_ts_ms, source_file, event_kind, event_ts_ms, topic, op, success, conn_id, raw_payload
) VALUES (
    {ts_ms},
    {q(str(jsonl_path))},
    {q(row.get("kind"))},
    {row.get("ts_ms") if row.get("ts_ms") is not None else "NULL"},
    {q(data.get("topic"))},
    {q(data.get("op"))},
    {"TRUE" if data.get("success") is True else "FALSE" if data.get("success") is False else "NULL"},
    {q(data.get("conn_id"))},
    {qj(row)}
);
""")

    return "\n".join(lines)

def run_sql(sql: str):
    cmd = [
        "docker", "exec", "-i", POSTGRES_CONTAINER,
        "sh", "-lc",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f -'
    ]
    return subprocess.run(cmd, input=sql, text=True, capture_output=True)

def main():
    summary = json.loads(LATEST_SUMMARY.read_text(encoding="utf-8"))
    jsonl_path = pick_latest_jsonl()
    sql = build_sql(summary, jsonl_path)
    proc = run_sql(sql)

    result = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "session_ts_ms": summary.get("ts_ms"),
        "jsonl_path": str(jsonl_path),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
