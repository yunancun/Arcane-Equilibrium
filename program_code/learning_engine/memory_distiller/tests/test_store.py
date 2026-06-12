"""store 測試：supersede 紀律（E2 審查重點 1）+ 冪等 INSERT + 零物理刪除。"""

from __future__ import annotations

import re
from pathlib import Path

from program_code.learning_engine.memory_distiller.store import (
    MemoryRecord,
    MemoryStore,
    new_record_id,
)

from ._fakes import FakeConn

_STORE_SRC = Path(
    __file__
).resolve().parents[1] / "store.py"


def _record(rid: str = "mem:abc123def456") -> MemoryRecord:
    return MemoryRecord(
        record_id=rid,
        content="測試記憶內容",
        mem_type="rule",
        priority=90,
        scene="seed:test",
        source_refs=({"kind": "l2_call", "id": "l2r:x"},),
        event_time_str="2026-06-10 前後",
        metadata={"k": "v"},
    )


def test_new_record_id_format():
    rid = new_record_id()
    assert re.fullmatch(r"mem:[0-9a-f]{12}", rid)


def test_insert_sql_is_idempotent_on_conflict():
    conn = FakeConn()
    conn.add_route("INSERT INTO agent.agent_memory", rowcount=1)
    assert MemoryStore(conn).insert_record(_record()) is True
    sql, params = conn.executed[-1]
    assert "ON CONFLICT (record_id) DO NOTHING" in sql
    assert params[0] == "mem:abc123def456"
    assert params[1] == "測試記憶內容"
    # source_refs / metadata 走 json 文本 + ::jsonb cast（參數化，無字串拼接）。
    assert '"l2_call"' in params[5]
    assert "%s" not in params[1]


def test_insert_conflict_returns_false():
    conn = FakeConn()
    conn.add_route("INSERT INTO agent.agent_memory", rowcount=0)
    assert MemoryStore(conn).insert_record(_record()) is False


def test_supersede_updates_only_whitelisted_columns():
    """UPDATE 白名單（E2 審查重點 1）：SET 子句僅 status/superseded_by/updated_at；
    content 永不出現在任何 UPDATE。"""
    conn = FakeConn()
    conn.add_route("SET status = 'superseded'", rowcount=2)
    n = MemoryStore(conn).supersede_records(["mem:a", "mem:b"], "mem:new")
    assert n == 2
    sql, params = conn.executed[-1]
    assert sql.startswith("UPDATE agent.agent_memory")
    set_clause = sql.split("SET", 1)[1].split("WHERE", 1)[0]
    assert "status" in set_clause and "superseded_by" in set_clause and "updated_at" in set_clause
    assert "content" not in set_clause
    # WHERE 守 active：已 superseded 的 row 不被重複改寫（鏈首次指向不可覆蓋）。
    assert "status = 'active'" in sql
    assert params == ("mem:new", ["mem:a", "mem:b"])


def test_supersede_empty_targets_no_sql():
    conn = FakeConn()
    assert MemoryStore(conn).supersede_records([], "mem:new") == 0
    assert conn.executed == []


def test_module_source_has_zero_physical_delete():
    """mutation 錨 ④ 半邊：全模組（含 SQL 常數）零物理刪除語句。"""
    src = _STORE_SRC.read_text(encoding="utf-8")
    assert "DELETE FROM" not in src.upper()


def test_all_update_statements_touch_only_whitelisted_columns():
    """UPDATE 白名單（V139 application discipline）：掃模組層全部 UPDATE SQL
    常數，SET 子句只允許 status/superseded_by/updated_at/embedding/
    embedding_pending 五欄；content 永不可變。動態掃描＝新加 UPDATE 也被咬。"""
    import program_code.learning_engine.memory_distiller.store as store_mod

    updates = [
        v for v in vars(store_mod).values()
        if isinstance(v, str) and v.strip().upper().startswith("UPDATE agent.agent_memory".upper())
    ]
    assert len(updates) >= 3  # supersede / set_embedding / mark_all_pending
    allowed = {"status", "superseded_by", "updated_at", "embedding", "embedding_pending"}
    for stmt in updates:
        set_clause = stmt.split("SET", 1)[1].split("WHERE", 1)[0]
        cols = set(re.findall(r"([a-z_]+)\s*=", set_clause))
        assert cols <= allowed, f"UPDATE 越界欄位: {cols - allowed} in {stmt!r}"
        assert "content" not in set_clause


def test_executed_sql_stream_never_contains_delete():
    conn = FakeConn()
    conn.add_route("INSERT INTO agent.agent_memory", rowcount=1)
    conn.add_route("SET status = 'superseded'", rowcount=1)
    st = MemoryStore(conn)
    st.insert_record(_record())
    st.supersede_records(["mem:a"], "mem:new")
    st.load_candidates_by_ids(["mem:a"])
    assert all("DELETE" not in s.upper() for s in conn.sqls())


def test_load_candidates_by_ids_empty_short_circuits():
    conn = FakeConn()
    assert MemoryStore(conn).load_candidates_by_ids([]) == []
    assert conn.executed == []


def test_load_candidates_by_ids_returns_dicts():
    conn = FakeConn()
    conn.add_route(
        "SELECT record_id, content, mem_type, priority, scene, source_refs",
        rows=[("mem:a", "c", "rule", 90, "s", [], "active", None, None, None)],
        columns=["record_id", "content", "mem_type", "priority", "scene",
                 "source_refs", "status", "superseded_by", "created_at", "updated_at"],
    )
    rows = MemoryStore(conn).load_candidates_by_ids(["mem:a"])
    assert rows[0]["record_id"] == "mem:a" and rows[0]["status"] == "active"


def test_set_embedding_builds_vector_literal_and_clears_pending():
    conn = FakeConn()
    conn.add_route("SET embedding = %s::vector", rowcount=1)
    MemoryStore(conn).set_embedding("mem:a", [0.5, -1.25])
    sql, params = conn.executed[-1]
    assert "embedding_pending = false" in sql
    assert params == ("[0.5,-1.25]", "mem:a")


def test_mark_all_pending_and_meta_upsert_shapes():
    conn = FakeConn()
    conn.add_route("SET embedding = NULL", rowcount=7)
    st = MemoryStore(conn)
    assert st.mark_all_embedding_pending() == 7
    st.upsert_embedding_meta("ollama", "bge-m3", 1024)
    sql, params = conn.executed[-1]
    assert "ON CONFLICT (meta_id) DO UPDATE" in sql
    assert params == ("ollama", "bge-m3", 1024)


def test_read_embedding_meta_none_and_row():
    conn = FakeConn()
    assert MemoryStore(conn).read_embedding_meta() is None
    conn2 = FakeConn()
    conn2.add_route(
        "FROM agent.agent_memory_embedding_meta",
        rows=[("ollama", "bge-m3", 1024)],
        columns=["provider", "model", "dims"],
    )
    meta = MemoryStore(conn2).read_embedding_meta()
    assert meta == {"provider": "ollama", "model": "bge-m3", "dims": 1024}
