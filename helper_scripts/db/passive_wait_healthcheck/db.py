"""DB connection + simple SQL helpers shared by every check module.
DB 連線與簡單 SQL helper（所有 check module 共用）。

MODULE_NOTE (EN): Extracted from the original ``passive_wait_healthcheck.py``
``_get_conn`` + ``_scalar`` helpers (lines 87-107 in the pre-split file).
Kept byte-identical to preserve all SQL semantics — this is the trunk on
top of which every individual check_* fn relies, so behavior changes here
would propagate silently across all 19 checks.

DSN priority: ``OPENCLAW_DATABASE_URL`` env var first (explicit override
used by ``passive_wait_healthcheck.sh`` cron wrapper); otherwise built
from the standard ``POSTGRES_{USER,PASSWORD,HOST,PORT,DB}`` quintet
(matches restart_all.sh / fresh_start.sh secrets-load pattern).

MODULE_NOTE (中): 從原 passive_wait_healthcheck.py 87-107 行抽出 ``_get_conn``
與 ``_scalar``。與拆分前 byte-identical — 每個 check 都依賴本檔，行為變動
會悄悄傳染所有 19 個 check。
DSN 優先序：OPENCLAW_DATABASE_URL 環境變數優先（cron wrapper 顯式覆寫）；
否則用標準 POSTGRES_* 五件組組合（與 restart_all.sh / fresh_start.sh 一致）。
"""

from __future__ import annotations

import os


# ---- connection ----

def _get_conn():
    """Build a psycopg2 connection from env vars.

    Priority:
      1. ``OPENCLAW_DATABASE_URL`` (explicit DSN — cron wrapper sets this)
      2. Constructed from POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_HOST
         / POSTGRES_PORT / POSTGRES_DB (defaults to 127.0.0.1 / 5432).

    優先序：先 OPENCLAW_DATABASE_URL（cron wrapper 顯式設定），否則由
    POSTGRES_{USER,PASSWORD,HOST,PORT,DB} 五件組組合（host/port 預設
    127.0.0.1 / 5432）。
    """
    import psycopg2  # type: ignore
    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    return psycopg2.connect(dsn)


# ---- single-query helpers ----

def _scalar(cur, sql: str) -> int:
    """Run a 1-row 1-column SELECT and return the value as int (0 if NULL).

    執行單列單欄 SELECT，回 int（NULL 視為 0）。
    """
    cur.execute(sql)
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0
