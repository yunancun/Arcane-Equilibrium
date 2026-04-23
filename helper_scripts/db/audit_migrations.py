#!/usr/bin/env python3
"""
Audit migration files vs live Postgres schema.
讀取 sql/migrations/V*.sql，提取期望 schema/table/column/index，對照 DB 實況。

READ-ONLY / 只讀：no DDL, no write.
Uses stdlib + psycopg2 only.
"""
from __future__ import annotations

import glob
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Set, Tuple

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # late-error only when fetch_live_schema is actually called


# ---------------------------------------------------------------------------
# Regex parsing
# ---------------------------------------------------------------------------

# Strip SQL comments before regex parsing.
# 策略：先去 line comments (`-- ...`) 再去 block comments (`/* ... */`)
LINE_COMMENT_RE = re.compile(r"--[^\n]*")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# CREATE SCHEMA IF NOT EXISTS name
CREATE_SCHEMA_RE = re.compile(
    r"\bCREATE\s+SCHEMA\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

# CREATE TABLE IF NOT EXISTS schema.name (
CREATE_TABLE_RE = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.IGNORECASE,
)

# ALTER TABLE schema.name ADD COLUMN [IF NOT EXISTS] col_name type
# NOTE: handles `ALTER TABLE ... ADD COLUMN x TYPE` (single) or
#       `ALTER TABLE ... ADD COLUMN a TYPE, ADD COLUMN b TYPE`.
ALTER_ADD_COLUMN_RE = re.compile(
    r"\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?"
    r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)"
    r"(.*?);",
    re.IGNORECASE | re.DOTALL,
)
ADD_COLUMN_SUB_RE = re.compile(
    r"\bADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

# CREATE [UNIQUE] INDEX [IF NOT EXISTS] idx_name ON schema.table ...
CREATE_INDEX_RE = re.compile(
    r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"([A-Za-z_][A-Za-z0-9_]*)\s+ON\s+"
    r"(?:([A-Za-z_][A-Za-z0-9_]*)\.)?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MigrationExpectations:
    filename: str
    schemas: Set[str] = field(default_factory=set)
    tables: Set[Tuple[str, str]] = field(default_factory=set)  # (schema, table)
    columns: Set[Tuple[str, str, str]] = field(default_factory=set)  # (s, t, c)
    indexes: Set[Tuple[str, str, str]] = field(default_factory=set)  # (schema, table, idx)


@dataclass
class MigrationGaps:
    filename: str
    missing_schemas: List[str] = field(default_factory=list)
    missing_tables: List[str] = field(default_factory=list)
    missing_columns: List[str] = field(default_factory=list)
    missing_indexes: List[str] = field(default_factory=list)

    def is_clean(self) -> bool:
        return not (self.missing_schemas or self.missing_tables or self.missing_columns or self.missing_indexes)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def strip_comments(sql: str) -> str:
    sql = LINE_COMMENT_RE.sub("", sql)
    sql = BLOCK_COMMENT_RE.sub("", sql)
    return sql


def parse_migration(path: str) -> MigrationExpectations:
    """Parse a single V*.sql migration file into expectations."""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    sql = strip_comments(raw)
    fname = os.path.basename(path)

    exp = MigrationExpectations(filename=fname)

    # CREATE SCHEMA
    for m in CREATE_SCHEMA_RE.finditer(sql):
        name = m.group(1).lower()
        exp.schemas.add(name)

    # CREATE TABLE
    for m in CREATE_TABLE_RE.finditer(sql):
        schema = m.group(1).lower()
        table = m.group(2).lower()
        exp.tables.add((schema, table))

    # ALTER TABLE ... ADD COLUMN (can have multiple ADD COLUMN per statement)
    for m in ALTER_ADD_COLUMN_RE.finditer(sql):
        schema = m.group(1).lower()
        table = m.group(2).lower()
        body = m.group(3)
        for cm in ADD_COLUMN_SUB_RE.finditer(body):
            col = cm.group(1).lower()
            exp.columns.add((schema, table, col))

    # CREATE INDEX
    for m in CREATE_INDEX_RE.finditer(sql):
        idx = m.group(1).lower()
        schema = (m.group(2) or "public").lower()
        table = m.group(3).lower()
        exp.indexes.add((schema, table, idx))

    return exp


# ---------------------------------------------------------------------------
# DB inspection
# ---------------------------------------------------------------------------

def fetch_live_schema(conn):
    """Snapshot all present schemas/tables/columns/indexes into in-memory sets."""
    schemas: Set[str] = set()
    tables: Set[Tuple[str, str]] = set()
    columns: Set[Tuple[str, str, str]] = set()
    indexes: Set[Tuple[str, str, str]] = set()

    with conn.cursor() as cur:
        cur.execute("SELECT lower(schema_name) FROM information_schema.schemata;")
        for (s,) in cur.fetchall():
            schemas.add(s)

        cur.execute(
            "SELECT lower(table_schema), lower(table_name) "
            "FROM information_schema.tables "
            "WHERE table_type IN ('BASE TABLE','VIEW','FOREIGN');"
        )
        for s, t in cur.fetchall():
            tables.add((s, t))

        cur.execute(
            "SELECT lower(table_schema), lower(table_name), lower(column_name) "
            "FROM information_schema.columns;"
        )
        for s, t, c in cur.fetchall():
            columns.add((s, t, c))

        cur.execute(
            "SELECT lower(schemaname), lower(tablename), lower(indexname) "
            "FROM pg_indexes;"
        )
        for s, t, i in cur.fetchall():
            indexes.add((s, t, i))

    return schemas, tables, columns, indexes


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

def diff(exp: MigrationExpectations, live) -> MigrationGaps:
    schemas, tables, columns, indexes = live
    g = MigrationGaps(filename=exp.filename)
    for s in sorted(exp.schemas):
        if s not in schemas:
            g.missing_schemas.append(s)
    for s, t in sorted(exp.tables):
        if (s, t) not in tables:
            g.missing_tables.append(f"{s}.{t}")
    for s, t, c in sorted(exp.columns):
        if (s, t, c) not in columns:
            # If the table itself is missing we already report that; skip column duplicate.
            if (s, t) in tables:
                g.missing_columns.append(f"{s}.{t}.{c}")
            else:
                g.missing_columns.append(f"{s}.{t}.{c} (table missing)")
    for s, t, i in sorted(exp.indexes):
        if (s, t, i) not in indexes:
            g.missing_indexes.append(f"{s}.{t}:{i}")
    return g


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

MIGRATIONS_DIR_CANDIDATES = [
    os.path.expanduser("~/BybitOpenClaw/srv/sql/migrations"),
    os.path.expanduser("~/srv/sql/migrations"),
    "/Users/ncyu/Projects/TradeBot/srv/sql/migrations",
]


def find_migrations_dir() -> str:
    for d in MIGRATIONS_DIR_CANDIDATES:
        if os.path.isdir(d):
            return d
    raise SystemExit("ERROR: could not locate sql/migrations directory")


def list_migration_files(mdir: str) -> List[str]:
    files = sorted(glob.glob(os.path.join(mdir, "V*.sql")))
    out = []
    for f in files:
        bn = os.path.basename(f)
        if "rollback" in bn.lower():
            continue
        if bn.startswith("V999"):
            continue
        out.append(f)
    return out


def canary_sanity(expectations) -> None:
    """Print canary assertions for V001 / V004 / V023 to stderr for quick eyeball."""
    by_name = {e.filename: e for e in expectations}
    print("--- canary parse sanity ---", file=sys.stderr)
    v1 = by_name.get("V001__create_schemas.sql")
    if v1:
        print(f"V001 schemas={sorted(v1.schemas)}", file=sys.stderr)
    v4 = by_name.get("V004__learning_features_obs_risk_tables.sql")
    if v4:
        print(f"V004 tables ({len(v4.tables)}): {sorted(v4.tables)[:3]}...", file=sys.stderr)
    v23 = by_name.get("V023__model_registry.sql")
    if v23:
        print(f"V023 tables={sorted(v23.tables)} indexes={sorted(v23.indexes)}",
              file=sys.stderr)
    print("--- end canary ---\n", file=sys.stderr)


def main() -> int:
    mdir = find_migrations_dir()
    print(f"[audit] migrations dir: {mdir}")
    files = list_migration_files(mdir)
    print(f"[audit] parsing {len(files)} migrations")

    expectations = [parse_migration(p) for p in files]
    canary_sanity(expectations)

    # DB connection
    user = os.environ.get("POSTGRES_USER")
    pw = os.environ.get("POSTGRES_PASSWORD")
    db = os.environ.get("POSTGRES_DB")
    if not (user and pw and db):
        print("ERROR: POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB required",
              file=sys.stderr)
        return 2

    if psycopg2 is None:
        print("ERROR: psycopg2 not installed", file=sys.stderr)
        return 2
    conn = psycopg2.connect(
        host="127.0.0.1", port=5432, user=user, password=pw, dbname=db
    )
    conn.set_session(readonly=True, autocommit=True)
    try:
        live = fetch_live_schema(conn)
    finally:
        conn.close()

    schemas, tables, columns, indexes = live
    print(f"[audit] live db inventory: {len(schemas)} schemas / {len(tables)} tables / "
          f"{len(columns)} columns / {len(indexes)} indexes\n")

    all_clean = []
    all_gap = []
    total_missing_tables = 0
    total_missing_cols = 0
    total_missing_idx = 0
    total_missing_schemas = 0

    for exp in expectations:
        gaps = diff(exp, live)
        print(f"=== {exp.filename} ===")
        print(f"  expected: {len(exp.schemas)} schemas, {len(exp.tables)} tables, "
              f"{len(exp.columns)} columns, {len(exp.indexes)} indexes")

        if gaps.missing_schemas:
            print(f"  MISSING schemas: {gaps.missing_schemas}")
        if gaps.missing_tables:
            print(f"  MISSING tables ({len(gaps.missing_tables)}): {gaps.missing_tables}")
        if gaps.missing_columns:
            print(f"  MISSING columns ({len(gaps.missing_columns)}): {gaps.missing_columns}")
        if gaps.missing_indexes:
            print(f"  MISSING indexes ({len(gaps.missing_indexes)}): {gaps.missing_indexes}")

        if gaps.is_clean():
            print("  ALL PRESENT OK")
            all_clean.append(exp.filename)
        else:
            all_gap.append((exp.filename, gaps))
            total_missing_schemas += len(gaps.missing_schemas)
            total_missing_tables += len(gaps.missing_tables)
            total_missing_cols += len(gaps.missing_columns)
            total_missing_idx += len(gaps.missing_indexes)
        print()

    print("--- SUMMARY ---")
    print(f"Migrations likely-applied (all targets present): {len(all_clean)}/{len(expectations)}")
    for n in all_clean:
        print(f"  OK  {n}")
    print(f"\nMigrations with gaps: {len(all_gap)}")
    for fn, g in all_gap:
        parts = []
        if g.missing_schemas:
            parts.append(f"{len(g.missing_schemas)} schema")
        if g.missing_tables:
            parts.append(f"{len(g.missing_tables)} tables")
        if g.missing_columns:
            parts.append(f"{len(g.missing_columns)} cols")
        if g.missing_indexes:
            parts.append(f"{len(g.missing_indexes)} idx")
        print(f"  GAP {fn}: {', '.join(parts)}")
    print(f"\nTotal gap count: {total_missing_schemas} schemas + "
          f"{total_missing_tables} tables + {total_missing_cols} cols + "
          f"{total_missing_idx} idx")

    return 0


if __name__ == "__main__":
    sys.exit(main())
