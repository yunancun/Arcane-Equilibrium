"""recall 測試：三級降級不冒泡（mutation 錨 ⑤）+ B3 bundle 預算。"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone

from program_code.learning_engine.memory_distiller import recall as recall_mod
from program_code.learning_engine.memory_distiller.recall import (
    RecallBundle,
    build_recall_bundle,
    recall_for_prompt,
    recall_top_k,
)

from ._fakes import FakeConn

_FTS_COLS = ["record_id", "content", "mem_type", "priority", "scene", "created_at", "score"]
_VEC_COLS = ["record_id", "content", "mem_type", "priority", "scene", "created_at"]


class _FakeEmbed:
    def __init__(self, *, available: bool = True, vectors=None):
        self._available = available
        self._vectors = vectors if vectors is not None else [[0.1, 0.2]]

    def is_available(self, *, force_check: bool = False) -> bool:
        return self._available

    def embed_batch(self, texts):
        return self._vectors


class _UndefinedColumn(Exception):
    """模擬 psycopg2.errors.UndefinedColumn（V140 未 apply 時 vector SQL 的真實錯）。"""


def test_vector_level_used_when_embed_available():
    conn = FakeConn()
    conn.add_route(
        "ORDER BY embedding",
        rows=[("mem:v1", "向量命中", "rule", 90, "s", None)],
        columns=_VEC_COLS,
    )
    rows, level = recall_top_k(conn, "查詢", k=5, embed_client=_FakeEmbed())
    assert level == "vector" and rows[0]["record_id"] == "mem:v1"


def test_vector_undefined_column_degrades_to_fts_no_raise():
    # mutation 錨 ⑤：無 V140（embedding 欄缺）⇒ vector 級降級不 raise。
    conn = FakeConn()
    conn.add_route("ORDER BY embedding", raises=_UndefinedColumn("column embedding does not exist"))
    conn.add_route(
        "GREATEST(ts_rank",
        rows=[("mem:f1", "FTS 命中", "rule", 80, "s", None, 0.4)],
        columns=_FTS_COLS,
    )
    rows, level = recall_top_k(conn, "查詢", k=5, embed_client=_FakeEmbed())
    assert level == "fts" and rows[0]["record_id"] == "mem:f1"
    assert conn.rollbacks >= 1  # 降級前 rollback 清壞事務


def test_no_embed_client_goes_straight_to_fts():
    conn = FakeConn()
    conn.add_route("GREATEST(ts_rank", rows=[], columns=_FTS_COLS)
    _rows, level = recall_top_k(conn, "查詢", k=5)
    assert level == "fts"
    assert conn.count_sql("ORDER BY embedding") == 0


def test_fts_sets_local_trgm_threshold():
    conn = FakeConn()
    conn.add_route("GREATEST(ts_rank", rows=[], columns=_FTS_COLS)
    recall_top_k(conn, "查詢")
    set_locals = [s for s in conn.sqls() if "SET LOCAL pg_trgm.similarity_threshold" in s]
    assert len(set_locals) == 1  # G14 教訓：預設 0.3 擋真命中，必降門檻


# ── MIT ratify 條件 ①：hint 幾何 word_similarity（mutation 錨）──────────────


def test_default_content_mode_keeps_symmetric_similarity():
    """回歸釘：dedup（content-vs-content 幾何）維持對稱 similarity + 0.1 門檻，
    不被 hint 修復誤改。"""
    conn = FakeConn()
    conn.add_route("GREATEST(ts_rank", rows=[], columns=_FTS_COLS)
    recall_top_k(conn, "候選記憶內容")
    fts_sql = next(s for s in conn.sqls() if "GREATEST(ts_rank" in s)
    assert "similarity(content, %s)" in fts_sql
    assert "word_similarity(" not in fts_sql
    assert any("SET LOCAL pg_trgm.similarity_threshold" in s for s in conn.sqls())


def test_hint_mode_uses_word_similarity_and_threshold():
    """mutation 錨：hint_mode 退回對稱 similarity ⇒ 本測試紅。
    短 hint vs 長混排 content 的對稱 similarity 在 prod 實測 0.092<0.1 漏召回
    （MIT [PROD]），hint 幾何必須 word_similarity（`<%`，hint 在前）。"""
    conn = FakeConn()
    conn.add_route("GREATEST(ts_rank", rows=[], columns=_FTS_COLS)
    recall_top_k(conn, "中性化檢驗", hint_mode=True)
    fts_sql = next(s for s in conn.sqls() if "GREATEST(ts_rank" in s)
    assert "word_similarity(%s, content)" in fts_sql
    assert "%s <%% content" in fts_sql
    assert "similarity(content, %s)" not in fts_sql
    assert any(
        "SET LOCAL pg_trgm.word_similarity_threshold" in s for s in conn.sqls()
    )


def test_recall_for_prompt_routes_hint_mode_with_cjk_mixed_hint(monkeypatch):
    """中文混排 case：B3 接縫走 hint 幾何，CJK 混排 hint 逐字進 SQL 參數
    （真 PG 命中語意屬 E4 Linux 驗證範圍）。"""
    conn = FakeConn()
    conn.add_route(
        "GREATEST(ts_rank",
        rows=[("mem:r1", "任何短 bias 信號必須先做 beta 中性化檢驗", "rule", 90, "s", None, 0.7)],
        columns=_FTS_COLS,
    )

    @contextmanager
    def _fake_open():
        yield conn

    monkeypatch.setattr(recall_mod, "_open_db_conn", _fake_open)
    b = asyncio.run(recall_for_prompt("BTCUSDT", "beta 中性化檢驗"))
    assert "中性化檢驗" in b.stable_block
    fts_sql, params = next(
        (s, p) for s, p in conn.executed if "GREATEST(ts_rank" in s
    )
    assert "word_similarity(" in fts_sql
    assert params[0] == "BTCUSDT beta 中性化檢驗"  # CJK 混排 hint 原樣綁定


def test_vector_zero_rows_falls_through_to_fts():
    """MIT F-2：vector 查詢成功但 0 rows（全表 embedding NULL=補嵌未收斂窗口）
    ⇒ 落 FTS 而非回空 "vector"——dedup 池不得在最需要的窗口恆空。"""
    conn = FakeConn()
    conn.add_route("ORDER BY embedding", rows=[], columns=_VEC_COLS)  # 0 rows
    conn.add_route(
        "GREATEST(ts_rank",
        rows=[("mem:f1", "FTS 命中", "rule", 80, "s", None, 0.4)],
        columns=_FTS_COLS,
    )
    rows, level = recall_top_k(conn, "查詢", k=5, embed_client=_FakeEmbed())
    assert level == "fts" and rows[0]["record_id"] == "mem:f1"
    assert conn.count_sql("ORDER BY embedding") == 1  # vector 真的試過才落下來


def test_fts_failure_degrades_to_skip_empty_no_raise():
    conn = FakeConn()
    conn.add_route("SET LOCAL", raises=RuntimeError("pg_trgm 不可用"))
    rows, level = recall_top_k(conn, "查詢")
    assert rows == [] and level == "skip"
    assert conn.rollbacks >= 1


def test_empty_query_skips_without_sql():
    conn = FakeConn()
    rows, level = recall_top_k(conn, "   ")
    assert rows == [] and level == "skip" and conn.executed == []


# ── RecallBundle 組裝（B3 接縫，PA spec §8）─────────────────────────────────


def _row(rid, mem_type, priority, content, created=None):
    return {
        "record_id": rid, "mem_type": mem_type, "priority": priority,
        "content": content, "created_at": created,
    }


def test_bundle_splits_stable_and_recent_blocks():
    t1 = datetime(2026, 6, 9, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 10, tzinfo=timezone.utc)
    rows = [
        _row("mem:r1", "rule", 90, "規則一"),
        _row("mem:t1", "system_trait", 95, "特質一"),
        _row("mem:i1", "incident", 70, "事件舊", t1),
        _row("mem:i2", "incident", 70, "事件新", t2),
    ]
    b = build_recall_bundle(rows, "fts", char_budget=2000)
    # stable：rule+system_trait，priority DESC（95 特質先於 90 規則）。
    assert b.stable_block.index("特質一") < b.stable_block.index("規則一")
    # recent：incident，recency DESC（新事件在前）。
    assert b.recent_block.index("事件新") < b.recent_block.index("事件舊")
    assert b.degraded_level == "fts"
    assert b.total_chars == len(b.stable_block) + len(b.recent_block)
    assert set(b.record_ids) == {"mem:r1", "mem:t1", "mem:i1", "mem:i2"}


def test_bundle_budget_drops_whole_entries():
    rows = [
        _row("mem:r1", "rule", 90, "短"),
        _row("mem:r2", "rule", 80, "超長" * 500),
        _row("mem:r3", "rule", 70, "次短"),
    ]
    b = build_recall_bundle(rows, "fts", char_budget=100)
    # 超長條整條丟棄（不截半句）；後續較短條仍可入。
    assert "mem:r2" not in b.record_ids
    assert "mem:r1" in b.record_ids and "mem:r3" in b.record_ids
    assert b.total_chars <= 100


def test_bundle_stable_order_deterministic_by_priority_then_id():
    rows = [
        _row("mem:b", "rule", 90, "乙"),
        _row("mem:a", "rule", 90, "甲"),
    ]
    b = build_recall_bundle(rows, "fts")
    assert b.record_ids[:2] == ["mem:a", "mem:b"]  # 同 priority 按 record_id 穩定序


# ── recall_for_prompt（fail-open 鐵律）──────────────────────────────────────


def test_recall_for_prompt_db_failure_returns_empty_bundle():
    # conftest 鐵閘讓 _open_db_conn 直接炸 ⇒ fail-open 空 bundle，不冒泡。
    b = asyncio.run(recall_for_prompt("BTCUSDT", "回撤覆盤"))
    assert isinstance(b, RecallBundle)
    assert b.stable_block == "" and b.recent_block == "" and b.degraded_level == "skip"


def test_recall_for_prompt_timeout_returns_empty_bundle(monkeypatch):
    def _slow(*_a, **_k):
        import time

        time.sleep(0.5)
        return RecallBundle(stable_block="不該到這")

    monkeypatch.setattr(recall_mod, "_recall_for_prompt_sync", _slow)
    b = asyncio.run(recall_for_prompt("BTCUSDT", "hint", timeout_s=0.05))
    assert b.stable_block == ""


def test_recall_for_prompt_happy_path_with_injected_conn(monkeypatch):
    conn = FakeConn()
    conn.add_route(
        "GREATEST(ts_rank",
        rows=[("mem:r1", "規則命中", "rule", 90, "s", None, 0.5)],
        columns=_FTS_COLS,
    )

    @contextmanager
    def _fake_open():
        yield conn

    monkeypatch.setattr(recall_mod, "_open_db_conn", _fake_open)
    b = asyncio.run(recall_for_prompt("BTCUSDT", "規則"))
    assert "規則命中" in b.stable_block
    assert b.record_ids == ["mem:r1"]
    assert b.degraded_level == "fts"


def test_recall_for_prompt_blank_inputs_empty_bundle():
    b = asyncio.run(recall_for_prompt("", ""))
    assert b.record_ids == [] and b.total_chars == 0
