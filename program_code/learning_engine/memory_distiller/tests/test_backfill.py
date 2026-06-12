"""backfill 測試：meta 漂移重索引（mutation 錨 ②）+ V140 缺欄 no-op + 批次。"""

from __future__ import annotations

from program_code.learning_engine.memory_distiller.backfill_embeddings import run_backfill

from ._fakes import FakeConn

_PROBE_KEY = "information_schema.columns"
_META_KEY = "FROM agent.agent_memory_embedding_meta"
_PENDING_KEY = "WHERE embedding_pending AND status = 'active'"


class _FakeEmbed:
    def __init__(self, *, available=True, dims=4, fail_batch=False):
        self._available = available
        self._dims = dims
        self._fail_batch = fail_batch
        self.provider_name = "ollama"
        self.model = "bge-m3"

    def is_available(self, *, force_check: bool = False) -> bool:
        return self._available

    def embed_batch(self, texts):
        if self._fail_batch and len(texts) > 1:
            return None
        return [[0.1] * self._dims for _ in texts]


def _conn_with_column(*, meta_row=None, pending_rows=()):
    conn = FakeConn()
    conn.add_route(_PROBE_KEY, rows=[(1,)], columns=["?column?"])
    conn.add_route(
        _META_KEY,
        rows=[meta_row] if meta_row else [],
        columns=["provider", "model", "dims"],
    )
    conn.add_route(_PENDING_KEY, rows=list(pending_rows), columns=["record_id", "content"])
    conn.add_route("SET embedding = NULL", rowcount=9)
    conn.add_route("SET embedding = %s::vector", rowcount=1)
    conn.add_route("INSERT INTO agent.agent_memory_embedding_meta", rowcount=1)
    return conn


def test_no_embedding_column_is_noop():
    conn = FakeConn()
    conn.add_route(_PROBE_KEY, rows=[], columns=["?column?"])  # 欄不存在
    out = run_backfill(conn, _FakeEmbed())
    assert out["status"] == "no_embedding_column" and out["embedded"] == 0
    # 探測之後零寫入。
    assert conn.count_sql("UPDATE") == 0 and conn.count_sql("INSERT") == 0


def test_embed_unavailable_is_noop():
    conn = _conn_with_column()
    out = run_backfill(conn, _FakeEmbed(available=False))
    assert out["status"] == "embed_unavailable"
    assert conn.count_sql("UPDATE") == 0


def test_none_embed_client_is_noop():
    conn = _conn_with_column()
    assert run_backfill(conn, None)["status"] == "embed_unavailable"


def test_meta_drift_triggers_full_reindex_mark():
    """mutation 錨 ②：meta 漂移 ⇒ 全表 embedding=NULL + pending=true + meta 更新。"""
    conn = _conn_with_column(meta_row=("ollama", "old-model", 4))
    out = run_backfill(conn, _FakeEmbed(dims=4))
    assert out["reindexed"] is True
    assert conn.count_sql("SET embedding = NULL") == 1
    assert conn.count_sql("INSERT INTO agent.agent_memory_embedding_meta") == 1


def test_meta_missing_inserts_meta_without_reindex():
    conn = _conn_with_column(meta_row=None)
    out = run_backfill(conn, _FakeEmbed(dims=4))
    assert out["reindexed"] is False
    assert conn.count_sql("SET embedding = NULL") == 0
    assert conn.count_sql("INSERT INTO agent.agent_memory_embedding_meta") == 1


def test_meta_match_no_reindex_no_meta_write():
    conn = _conn_with_column(meta_row=("ollama", "bge-m3", 4))
    out = run_backfill(conn, _FakeEmbed(dims=4))
    assert out["reindexed"] is False
    assert conn.count_sql("SET embedding = NULL") == 0
    assert conn.count_sql("INSERT INTO agent.agent_memory_embedding_meta") == 0


def test_pending_rows_embedded_and_committed():
    conn = _conn_with_column(
        meta_row=("ollama", "bge-m3", 4),
        pending_rows=[("mem:a", "內容甲"), ("mem:b", "內容乙")],
    )
    out = run_backfill(conn, _FakeEmbed(dims=4))
    assert out["status"] == "ok" and out["embedded"] == 2
    assert conn.count_sql("SET embedding = %s::vector") == 2
    assert conn.commits >= 1


def test_no_pending_rows_ok_zero():
    conn = _conn_with_column(meta_row=("ollama", "bge-m3", 4), pending_rows=[])
    out = run_backfill(conn, _FakeEmbed(dims=4))
    assert out["status"] == "ok" and out["embedded"] == 0


def test_batch_embed_failure_aborts_without_partial_write():
    conn = _conn_with_column(
        meta_row=("ollama", "bge-m3", 4),
        pending_rows=[("mem:a", "甲"), ("mem:b", "乙")],
    )
    out = run_backfill(conn, _FakeEmbed(dims=4, fail_batch=True))
    assert out["status"] == "embed_failed" and out["embedded"] == 0
    assert conn.count_sql("SET embedding = %s::vector") == 0  # 不部分寫避免錯位


def test_column_probe_exception_fail_soft():
    conn = FakeConn()
    conn.add_route(_PROBE_KEY, raises=RuntimeError("db down"))
    out = run_backfill(conn, _FakeEmbed())
    assert out["status"] == "error" and conn.rollbacks >= 1
