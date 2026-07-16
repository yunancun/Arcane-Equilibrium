"""Transaction-boundary tests for ``connect_report_pg``.

The report callers intentionally roll back immediately after connecting before
switching to read-only autocommit.  The helper must therefore commit its own
session-configuration transaction before returning the connection.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from helper_scripts.lib import pg_connect


class _FakeConnection:
    def __init__(
        self,
        events: list[Any],
        *,
        execute_error: Exception | None = None,
        commit_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.execute_error = execute_error
        self.commit_error = commit_error
        self.pending_timeout: int | None = None
        self.committed_timeout: int | None = None
        self.commit_attempts = 0

    def cursor(self) -> "_FakeCursor":
        self.events.append("cursor")
        return _FakeCursor(self)

    def commit(self) -> None:
        self.commit_attempts += 1
        self.events.append("commit")
        if self.commit_error is not None:
            raise self.commit_error
        self.committed_timeout = self.pending_timeout
        self.pending_timeout = None

    def rollback(self) -> None:
        self.events.append("rollback")
        self.pending_timeout = None


class _FakeCursor:
    def __init__(self, conn: _FakeConnection) -> None:
        self.conn = conn

    def __enter__(self) -> "_FakeCursor":
        self.conn.events.append("cursor_enter")
        return self

    def __exit__(self, *_args: object) -> bool:
        self.conn.events.append("cursor_exit")
        return False

    def execute(self, sql: str, params: tuple[int]) -> None:
        self.conn.events.append(("execute", sql, params))
        if self.conn.execute_error is not None:
            raise self.conn.execute_error
        self.conn.pending_timeout = params[0]


def _install_fake_psycopg2(
    monkeypatch: pytest.MonkeyPatch,
    conn: _FakeConnection,
    events: list[Any],
) -> None:
    def connect(dsn: str, *, application_name: str) -> _FakeConnection:
        events.append(("connect", dsn, application_name))
        return conn

    monkeypatch.setitem(
        sys.modules,
        "psycopg2",
        types.SimpleNamespace(connect=connect),
    )


@pytest.mark.parametrize("default_ms", [180000, 120000])
def test_connect_commits_default_timeout_before_return_and_caller_rollback(
    monkeypatch: pytest.MonkeyPatch,
    default_ms: int,
) -> None:
    events: list[Any] = []
    conn = _FakeConnection(events)
    _install_fake_psycopg2(monkeypatch, conn, events)
    monkeypatch.setenv("OPENCLAW_DATABASE_URL", "postgresql://report/test")
    monkeypatch.delenv(
        pg_connect.DEFAULT_STATEMENT_TIMEOUT_ENV,
        raising=False,
    )

    returned = pg_connect.connect_report_pg(
        "timeout-persistence-test",
        statement_timeout_ms_default=default_ms,
    )

    assert returned is conn
    assert events == [
        ("connect", "postgresql://report/test", "timeout-persistence-test"),
        "cursor",
        "cursor_enter",
        ("execute", "SET statement_timeout = %s", (default_ms,)),
        "cursor_exit",
        "commit",
    ]
    assert conn.commit_attempts == 1
    assert conn.committed_timeout == default_ms

    returned.rollback()
    assert conn.committed_timeout == default_ms
    assert events[-1] == "rollback"


def test_connect_commits_exact_timeout_override(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[Any] = []
    conn = _FakeConnection(events)
    _install_fake_psycopg2(monkeypatch, conn, events)
    monkeypatch.setenv("OPENCLAW_DATABASE_URL", "postgresql://report/test")
    monkeypatch.setenv(pg_connect.DEFAULT_STATEMENT_TIMEOUT_ENV, "4321")

    returned = pg_connect.connect_report_pg(
        "timeout-override-test",
        statement_timeout_ms_default=180000,
    )

    assert returned is conn
    assert ("execute", "SET statement_timeout = %s", (4321,)) in events
    assert events[-2:] == ["cursor_exit", "commit"]
    assert conn.committed_timeout == 4321


def test_connect_failure_propagates_without_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[Any] = []

    def connect(_dsn: str, *, application_name: str) -> _FakeConnection:
        events.append(("connect", application_name))
        raise RuntimeError("connect failed")

    monkeypatch.setitem(
        sys.modules,
        "psycopg2",
        types.SimpleNamespace(connect=connect),
    )
    monkeypatch.setenv("OPENCLAW_DATABASE_URL", "postgresql://report/test")

    with pytest.raises(RuntimeError, match="connect failed"):
        pg_connect.connect_report_pg(
            "connect-failure-test",
            statement_timeout_ms_default=180000,
        )

    assert events == [("connect", "connect-failure-test")]


def test_execute_failure_propagates_without_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[Any] = []
    conn = _FakeConnection(events, execute_error=RuntimeError("execute failed"))
    _install_fake_psycopg2(monkeypatch, conn, events)
    monkeypatch.setenv("OPENCLAW_DATABASE_URL", "postgresql://report/test")

    with pytest.raises(RuntimeError, match="execute failed"):
        pg_connect.connect_report_pg(
            "execute-failure-test",
            statement_timeout_ms_default=180000,
        )

    assert conn.commit_attempts == 0
    assert events[-1] == "cursor_exit"


def test_commit_failure_propagates_without_returning_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[Any] = []
    conn = _FakeConnection(events, commit_error=RuntimeError("commit failed"))
    _install_fake_psycopg2(monkeypatch, conn, events)
    monkeypatch.setenv("OPENCLAW_DATABASE_URL", "postgresql://report/test")

    with pytest.raises(RuntimeError, match="commit failed"):
        pg_connect.connect_report_pg(
            "commit-failure-test",
            statement_timeout_ms_default=180000,
        )

    assert conn.commit_attempts == 1
    assert conn.committed_timeout is None
    assert events[-2:] == ["cursor_exit", "commit"]
