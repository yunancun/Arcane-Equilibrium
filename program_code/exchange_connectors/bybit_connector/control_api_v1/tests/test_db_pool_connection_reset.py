from __future__ import annotations

from program_code.exchange_connectors.bybit_connector.control_api_v1.app import db_pool


class _Conn:
    def __init__(self, *, rollback_error: Exception | None = None):
        self.rollback_error = rollback_error
        self.rollback_calls = 0
        self.closed = False

    def rollback(self):
        self.rollback_calls += 1
        if self.rollback_error is not None:
            raise self.rollback_error

    def close(self):
        self.closed = True


class _Pool:
    def __init__(self):
        self.put_calls: list[tuple[_Conn, bool]] = []

    def putconn(self, conn, close=False):
        self.put_calls.append((conn, close))


def test_put_conn_rolls_back_before_reuse(monkeypatch):
    pool = _Pool()
    conn = _Conn()
    monkeypatch.setattr(db_pool, "_pool", pool)

    db_pool.put_conn(conn)

    assert conn.rollback_calls == 1
    assert pool.put_calls == [(conn, False)]


def test_put_conn_discards_connection_when_rollback_fails(monkeypatch):
    pool = _Pool()
    conn = _Conn(rollback_error=RuntimeError("bad transaction"))
    monkeypatch.setattr(db_pool, "_pool", pool)

    db_pool.put_conn(conn)

    assert conn.rollback_calls == 1
    assert pool.put_calls == [(conn, True)]
