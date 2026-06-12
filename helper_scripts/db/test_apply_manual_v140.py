"""manual V140 apply 工具測試（mock psql；語法 + 退出碼分類 + 冪等形狀）。

MODULE_NOTE
模塊用途：釘死 manual V140 手動 apply 工具（PA 2026-06-11 spec §3.2 路徑 B）
  的 load-bearing 行為，Mac 可跑（0 真 PG——PATH 注入 mock psql）：
    1. apply script bash -n 語法守門。
    2. 退出碼分類：0=成功+驗證、1=SQL 失敗/驗證不符、2=配置缺、
       3=CREATE EXTENSION 權限不足、4=V139 前提缺。
    3. 冪等形狀：SQL 檔全 IF NOT EXISTS / 0 DROP-TABLE / 含 Guard B'；
       mock 下重跑兩次皆 0。
    4. psql 調用面：ON_ERROR_STOP=1 + -f <sql>；成功後驗證查詢（-c）。
依賴：pytest + 標準庫 subprocess。
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_DB_DIR = Path(__file__).resolve().parent
APPLY_SH = _DB_DIR / "apply_manual_V140_agent_memory_vector.sh"
SQL_FILE = _DB_DIR / "manual_V140_agent_memory_vector.sql"

_MOCK_PSQL = """#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
with open(os.environ["MOCK_PSQL_LOG"], "a", encoding="utf-8") as fh:
    fh.write(" ".join(args) + "\\n")
mode = os.environ.get("MOCK_PSQL_MODE", "ok")
is_verify = "-c" in args
if not is_verify:
    if mode == "perm":
        sys.stderr.write(
            'psql:manual_V140_agent_memory_vector.sql:46: ERROR:  permission denied'
            ' to create extension "vector"\\n'
            "HINT:  Must be superuser to create this extension.\\n"
        )
        sys.exit(1)
    if mode == "noprereq":
        sys.stderr.write(
            "psql:manual_V140_agent_memory_vector.sql:36: ERROR:  manual V140"
            " prerequisite FAIL: agent.agent_memory missing - apply V139 first.\\n"
        )
        sys.exit(1)
    if mode == "sqlerr":
        sys.stderr.write("ERROR:  syntax error at or near something\\n")
        sys.exit(1)
    sys.stdout.write("BEGIN\\nCREATE EXTENSION\\nALTER TABLE\\nCREATE INDEX\\nCOMMIT\\n")
    sys.exit(0)
if mode == "verifybad":
    sys.stdout.write("text\\n")
else:
    sys.stdout.write("vector\\n")
sys.exit(0)
"""


@pytest.fixture()
def mock_env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    psql = bin_dir / "psql"
    psql.write_text(_MOCK_PSQL, encoding="utf-8")
    psql.chmod(psql.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "psql_calls.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "MOCK_PSQL_LOG": str(log),
        "MOCK_PSQL_MODE": "ok",
        "POSTGRES_USER": "trading_admin",
        "POSTGRES_PASSWORD": "x",
        "POSTGRES_DB": "trading_ai",
    }
    return env, log


def _run(env):
    return subprocess.run(
        ["bash", str(APPLY_SH)], env=env, capture_output=True, text=True, timeout=30
    )


def test_apply_script_bash_syntax_ok():
    assert subprocess.run(["bash", "-n", str(APPLY_SH)]).returncode == 0


class TestSqlFileShape:
    """冪等邏輯靜態釘子：IF NOT EXISTS 全覆蓋 + Guard + 0 破壞性語句。"""

    def test_idempotent_forms_present(self):
        text = SQL_FILE.read_text(encoding="utf-8")
        assert "CREATE EXTENSION IF NOT EXISTS vector" in text
        assert "ADD COLUMN IF NOT EXISTS embedding vector(1024)" in text
        assert "CREATE INDEX IF NOT EXISTS idx_agent_memory_embedding_hnsw" in text
        assert "BEGIN;" in text and "COMMIT;" in text

    def test_guards_present(self):
        text = SQL_FILE.read_text(encoding="utf-8")
        assert "prerequisite FAIL" in text  # V139 前提守門
        assert "udt_name" in text  # Guard B'（vector 型反射用 udt_name）
        assert "Guard B" in text

    def test_no_destructive_statements(self):
        # rollback 指引只活在註釋；可執行區 0 DROP/DELETE/TRUNCATE。
        executable = "\n".join(
            ln
            for ln in SQL_FILE.read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith("--")
        ).upper()
        assert "DROP TABLE" not in executable
        assert "DELETE FROM" not in executable
        assert "TRUNCATE" not in executable
        assert "DROP COLUMN" not in executable


class TestApplyExitCodes:
    def test_success_applies_and_verifies(self, mock_env):
        env, log = mock_env
        proc = _run(env)
        assert proc.returncode == 0, proc.stderr
        assert "OK: manual V140 applied" in proc.stdout
        calls = log.read_text().splitlines()
        assert len(calls) == 2, "apply (-f) + verify (-c) 各一次"
        assert "ON_ERROR_STOP=1" in calls[0]
        assert calls[0].endswith(str(SQL_FILE))
        assert "-c" in calls[1]

    def test_rerun_idempotent_still_zero(self, mock_env):
        env, _log = mock_env
        assert _run(env).returncode == 0
        assert _run(env).returncode == 0, "冪等：重跑同樣成功"

    def test_permission_denied_exit3_with_guidance(self, mock_env):
        env, _log = mock_env
        env["MOCK_PSQL_MODE"] = "perm"
        proc = _run(env)
        assert proc.returncode == 3
        assert "權限不足" in proc.stderr
        assert "CREATE EXTENSION vector;" in proc.stderr

    def test_prerequisite_missing_exit4(self, mock_env):
        env, _log = mock_env
        env["MOCK_PSQL_MODE"] = "noprereq"
        proc = _run(env)
        assert proc.returncode == 4
        assert "V139" in proc.stderr

    def test_generic_sql_failure_exit1(self, mock_env):
        env, _log = mock_env
        env["MOCK_PSQL_MODE"] = "sqlerr"
        proc = _run(env)
        assert proc.returncode == 1

    def test_verify_mismatch_exit1(self, mock_env):
        env, _log = mock_env
        env["MOCK_PSQL_MODE"] = "verifybad"
        proc = _run(env)
        assert proc.returncode == 1
        assert "驗證不符" in proc.stderr

    def test_no_conn_info_exit2(self, mock_env):
        env, _log = mock_env
        for var in ("POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD"):
            env.pop(var, None)
        proc = _run(env)
        assert proc.returncode == 2
        assert "無連線資訊" in proc.stderr

    def test_dsn_arg_passes_through(self, mock_env):
        env, log = mock_env
        proc = subprocess.run(
            ["bash", str(APPLY_SH), "postgresql://redacted@h:5/db"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0
        first_call = log.read_text().splitlines()[0]
        assert first_call.startswith("postgresql://"), "DSN 應作為 psql 首位參數"
