"""pipeline 測試：mutation 錨 ①④⑥ + flag 入口閘 + 游標 + 單裁決事務隔離。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import program_code.learning_engine.memory_distiller.embedding as embedding_mod
import program_code.learning_engine.memory_distiller.pipeline as pipeline_mod
from program_code.learning_engine.memory_distiller.pipeline import (
    DRAR_LIMIT,
    EMBED_BACKFILL_FLAG_ENV,
    L2_CALLS_LIMIT,
    PIPELINE_FLAG_ENV,
    PipelineDisabledError,
    run_daily,
)

from ._fakes import FakeConn, FakeLLM

_NOW = datetime(2026, 6, 11, 6, 0, tzinfo=timezone.utc)  # 昨日 = 2026-06-10
_TS = datetime(2026, 6, 10, 3, 0, tzinfo=timezone.utc)

_L2_COLS = ["l2_reply_id", "capability_id", "trigger", "parsed_output", "raw_response", "created_at"]
_DRAR_COLS = ["report_id", "strategy_name", "report_jsonb", "first_seen_ts"]
_FTS_COLS = ["record_id", "content", "mem_type", "priority", "scene", "created_at", "score"]
_LOAD_COLS = ["record_id", "content", "mem_type", "priority", "scene",
              "source_refs", "status", "superseded_by", "created_at", "updated_at"]

_L2_ROW = ("l2r:x1", "ml_advisory.diagnose_leak", "schedule", {"verdict": "pass"}, "raw 回應", _TS)


def _conn(l2_rows=(), drar_rows=(), recall_rows=(), old_rows=()):
    conn = FakeConn()
    conn.add_route("FROM agent.l2_calls", rows=l2_rows, columns=_L2_COLS)
    conn.add_route("FROM learning.demo_residual_alpha_reports", rows=drar_rows, columns=_DRAR_COLS)
    conn.add_route("GREATEST(ts_rank", rows=recall_rows, columns=_FTS_COLS)
    conn.add_route("INSERT INTO agent.agent_memory", rowcount=1)
    conn.add_route("SET status = 'superseded'", rowcount=1)
    conn.add_route(
        "SELECT record_id, content, mem_type, priority, scene, source_refs",
        rows=old_rows, columns=_LOAD_COLS,
    )
    return conn


def _extraction(memories: list[dict], scene: str = "覆盤測試") -> str:
    return json.dumps({"scene": scene, "memories": memories}, ensure_ascii=False)


def _mem(source_ids, **overrides) -> dict:
    base = {
        "content": "grid_trading 低流動性滑點放大",
        "mem_type": "rule",
        "priority": 90,
        "source_ids": source_ids,
    }
    base.update(overrides)
    return base


@pytest.fixture()
def enabled(monkeypatch, tmp_path):
    """flag=1 + 確定性 record_id + 游標檔在 tmp。回 (cursor_path, ids)。"""
    monkeypatch.setenv(PIPELINE_FLAG_ENV, "1")
    counter = iter(range(1, 100))
    monkeypatch.setattr(
        pipeline_mod, "new_record_id", lambda: f"mem:fixed{next(counter):07d}"
    )
    return tmp_path / "cursor.json"


def _cursor_date(path) -> str | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())["last_success_utc_date"]


# ── flag 入口閘（錨 ③ 的 run_daily 對偶：off ⇒ 零 SQL 零 LLM）─────────────────


def test_flag_off_returns_disabled_with_zero_side_effects(monkeypatch, tmp_path):
    monkeypatch.delenv(PIPELINE_FLAG_ENV, raising=False)
    conn = FakeConn()
    llm = FakeLLM([])
    out = run_daily(conn, llm, now=_NOW, state_path=tmp_path / "c.json")
    assert out["status"] == "disabled"
    assert conn.executed == [] and conn.commits == 0
    assert llm.calls == []
    assert not (tmp_path / "c.json").exists()


def test_flag_off_never_touches_conn_even_if_none(monkeypatch):
    monkeypatch.delenv(PIPELINE_FLAG_ENV, raising=False)
    # conn/llm 傳 None：若入口閘之前有任何觸碰，這裡會 AttributeError。
    assert run_daily(None, None)["status"] == "disabled"


def test_cursor_path_unresolved_is_honest_error(monkeypatch):
    monkeypatch.setenv(PIPELINE_FLAG_ENV, "1")
    monkeypatch.delenv("OPENCLAW_DATA_DIR", raising=False)
    conn = FakeConn()
    out = run_daily(conn, FakeLLM([]), now=_NOW, state_path=None)
    assert out["status"] == "error" and "cursor_path" in out["error"]
    assert conn.executed == []


# ── 兩源皆空 ⇒ no-op + 游標推進 ─────────────────────────────────────────────


def test_both_sources_empty_noop_advances_cursor(enabled):
    conn = _conn()
    llm = FakeLLM([])
    out = run_daily(conn, llm, now=_NOW, state_path=enabled)
    assert out["days_succeeded"] == 1
    assert out["day_results"][0]["noop"] is True
    assert llm.calls == []  # 無材料不呼 LLM
    assert _cursor_date(enabled) == "2026-06-10"


# ── extraction 失敗 ⇒ 0 入庫 + 游標不推進（錨 ⑥）────────────────────────────


def test_extraction_bad_json_zero_rows_and_cursor_not_advanced(enabled):
    conn = _conn(l2_rows=[_L2_ROW])
    out = run_daily(conn, FakeLLM(["這不是 JSON {"]), now=_NOW, state_path=enabled)
    assert out["days_succeeded"] == 0
    assert conn.count_sql("INSERT INTO agent.agent_memory") == 0
    assert _cursor_date(enabled) is None  # 游標不推進，下輪補跑


def test_extraction_llm_unavailable_day_fails_no_advance(enabled):
    conn = _conn(l2_rows=[_L2_ROW])
    out = run_daily(conn, FakeLLM([("", False)]), now=_NOW, state_path=enabled)
    assert out["days_succeeded"] == 0
    assert out["day_results"][0]["error"] == "extraction_llm_unavailable"
    assert _cursor_date(enabled) is None


def test_extraction_empty_memories_is_success(enabled):
    conn = _conn(l2_rows=[_L2_ROW])
    out = run_daily(conn, FakeLLM([_extraction([])]), now=_NOW, state_path=enabled)
    assert out["days_succeeded"] == 1
    assert conn.count_sql("INSERT INTO agent.agent_memory") == 0
    assert _cursor_date(enabled) == "2026-06-10"


# ── store 路徑 + source_refs 映射 + 池空短路 ─────────────────────────────────


def test_store_path_pool_empty_skips_dedup_call(enabled):
    conn = _conn(l2_rows=[_L2_ROW])  # recall 無命中 ⇒ 池空
    llm = FakeLLM([_extraction([_mem(["l2:l2r:x1"])])])
    out = run_daily(conn, llm, now=_NOW, state_path=enabled)
    assert out["day_results"][0]["stored"] == 1
    assert out["day_results"][0]["dedup_called"] is False
    assert len(llm.calls) == 1  # 池空短路：省掉 dedup call（TencentDB 同款）
    insert_sql, params = next(
        (s, p) for s, p in conn.executed if "INSERT INTO agent.agent_memory" in s
    )
    assert params[0] == "mem:fixed0000001"
    refs = json.loads(params[5])
    assert refs == [{"kind": "l2_call", "id": "l2r:x1"}]
    assert params[4] == "覆盤測試"  # scene
    assert conn.commits >= 1
    assert _cursor_date(enabled) == "2026-06-10"


def test_drar_source_runs_real_postmortem_inline(enabled):
    """G11：drar row 經 classify_signal_failure（真函數）文本化為材料塊。"""
    drar_row = (7, "grid_trading", {"residual_mean_bps": 0.5}, _TS)
    conn = _conn(drar_rows=[drar_row])
    llm = FakeLLM([_extraction([_mem(["drar:7"])])])
    out = run_daily(conn, llm, now=_NOW, state_path=enabled)
    prompt = llm.calls[0]["prompt"]
    assert "[drar:7] [drar_postmortem]" in prompt
    assert "strategy=grid_trading" in prompt and "taxonomy=" in prompt
    # source_refs 逆映射：drar 數字 id 還原為 int。
    _sql, params = next(
        (s, p) for s, p in conn.executed if "INSERT INTO agent.agent_memory" in s
    )
    assert json.loads(params[5]) == [{"kind": "drar", "id": 7}]
    assert out["days_succeeded"] == 1


# ── dedup：壞 JSON 全 store（錨 ①）+ merge supersede（錨 ④）────────────────


def _recall_hit(rid="mem:old0000001"):
    return (rid, "舊記憶內容", "rule", 80, "舊scene", _TS, 0.5)


def test_dedup_bad_json_all_store_fail_open(enabled):
    conn = _conn(l2_rows=[_L2_ROW], recall_rows=[_recall_hit()])
    llm = FakeLLM([_extraction([_mem(["l2:l2r:x1"])]), "garbage not json"])
    out = run_daily(conn, llm, now=_NOW, state_path=enabled)
    day = out["day_results"][0]
    assert day["dedup_called"] is True and len(llm.calls) == 2
    assert day["stored"] == 1 and day["fail_open"] == 1
    assert conn.count_sql("SET status = 'superseded'") == 0  # 不動舊記憶


def test_dedup_llm_unavailable_all_store_fail_open(enabled):
    conn = _conn(l2_rows=[_L2_ROW], recall_rows=[_recall_hit()])
    llm = FakeLLM([_extraction([_mem(["l2:l2r:x1"])]), ("", False)])
    out = run_daily(conn, llm, now=_NOW, state_path=enabled)
    assert out["day_results"][0]["stored"] == 1
    assert out["day_results"][0]["fail_open"] == 1


def test_merge_inserts_new_row_and_supersedes_old_without_delete(enabled):
    """mutation 錨 ④：merge ⇒ 舊 row superseded（UPDATE 軟刪）非 DELETE；
    content 不在任何 UPDATE SET 子句；新 row 帶並集 source_refs。"""
    old_row = ("mem:old0000001", "舊記憶內容", "rule", 80, "舊scene",
               [{"kind": "lesson", "id": 4}], "active", None, _TS, _TS)
    conn = _conn(l2_rows=[_L2_ROW], recall_rows=[_recall_hit()], old_rows=[old_row])
    dedup_reply = json.dumps([
        {"record_id": "mem:fixed0000001", "action": "merge",
         "target_ids": ["mem:old0000001"], "merged_content": "合併後完整記憶",
         "merged_type": "rule", "merged_priority": 95}
    ])
    llm = FakeLLM([_extraction([_mem(["l2:l2r:x1"])]), dedup_reply])
    out = run_daily(conn, llm, now=_NOW, state_path=enabled)
    day = out["day_results"][0]
    assert day["stored"] == 1 and day["superseded"] == 1

    # INSERT 新 row：merged 內容 + 並集 source_refs + merged_from 血緣。
    insert_sql, ip = next(
        (s, p) for s, p in conn.executed if "INSERT INTO agent.agent_memory" in s
    )
    assert ip[1] == "合併後完整記憶" and ip[3] == 95
    refs = json.loads(ip[5])
    assert {"kind": "l2_call", "id": "l2r:x1"} in refs
    assert {"kind": "lesson", "id": 4} in refs
    assert json.loads(ip[9])["merged_from"] == ["mem:old0000001"]

    # supersede UPDATE：指向新 record_id；零 DELETE；content 不在 SET 子句。
    up_sql, up = next((s, p) for s, p in conn.executed if "SET status = 'superseded'" in s)
    assert up == ("mem:fixed0000001", ["mem:old0000001"])
    assert all("DELETE" not in s.upper() for s in conn.sqls())
    assert "content" not in up_sql.split("SET", 1)[1].split("WHERE", 1)[0]


def test_skip_action_writes_nothing(enabled):
    conn = _conn(l2_rows=[_L2_ROW], recall_rows=[_recall_hit()])
    dedup_reply = json.dumps([{"record_id": "mem:fixed0000001", "action": "skip"}])
    llm = FakeLLM([_extraction([_mem(["l2:l2r:x1"])]), dedup_reply])
    out = run_daily(conn, llm, now=_NOW, state_path=enabled)
    day = out["day_results"][0]
    assert day["skipped"] == 1 and day["stored"] == 0
    assert conn.count_sql("INSERT INTO agent.agent_memory") == 0


# ── 單裁決事務隔離 ───────────────────────────────────────────────────────────


def test_per_decision_transaction_isolation(enabled):
    conn = FakeConn()
    conn.add_route("FROM agent.l2_calls", rows=[_L2_ROW], columns=_L2_COLS)
    conn.add_route("FROM learning.demo_residual_alpha_reports", rows=[], columns=_DRAR_COLS)
    conn.add_route("GREATEST(ts_rank", rows=[], columns=_FTS_COLS)
    conn.add_route(
        "INSERT INTO agent.agent_memory",
        rowcount=1,
        raises=RuntimeError("模擬約束違反"),
        raise_when=lambda _sql, params: bool(params) and "炸" in str(params[1]),
    )
    mems = [
        _mem(["l2:l2r:x1"], content="正常記憶一"),
        _mem(["l2:l2r:x1"], content="會炸的記憶"),
        _mem(["l2:l2r:x1"], content="正常記憶二"),
    ]
    llm = FakeLLM([_extraction(mems)])
    out = run_daily(conn, llm, now=_NOW, state_path=enabled)
    day = out["day_results"][0]
    # 壞裁決 rollback 隔離；其餘照常 commit（部分失敗不污染整批，§6.3-4）。
    assert day["stored"] == 2 and day["failed"] == 1
    assert conn.rollbacks >= 1 and conn.commits >= 2
    assert day["ok"] is True and _cursor_date(enabled) == "2026-06-10"


# ── 輸入 cap 與游標窗口 ──────────────────────────────────────────────────────


def test_source_queries_carry_limit_caps(enabled):
    conn = _conn()
    run_daily(conn, FakeLLM([]), now=_NOW, state_path=enabled)
    l2_sql, l2_params = next((s, p) for s, p in conn.executed if "agent.l2_calls" in s)
    assert l2_params[2] == L2_CALLS_LIMIT == 200
    dr_sql, dr_params = next(
        (s, p) for s, p in conn.executed if "demo_residual_alpha_reports" in s
    )
    assert dr_params[2] == DRAR_LIMIT == 20
    assert "LIMIT" in l2_sql and "LIMIT" in dr_sql


def test_window_capped_at_seven_days_lookback(enabled):
    enabled.write_text(json.dumps({"last_success_utc_date": "2026-05-01"}))
    conn = _conn()  # 兩源皆空 ⇒ 各日 noop
    out = run_daily(conn, FakeLLM([]), now=_NOW, state_path=enabled)
    assert out["days_attempted"] == 7  # 停擺一個月也只補 7 日（R5 防爆量）
    assert out["day_results"][0]["utc_date"] == "2026-06-04"
    assert _cursor_date(enabled) == "2026-06-10"


def test_failed_day_stops_window_and_keeps_cursor(enabled):
    enabled.write_text(json.dumps({"last_success_utc_date": "2026-06-07"}))
    conn = _conn(l2_rows=[_L2_ROW])
    # day1（06-08）成功空批；day2（06-09）extraction 壞 JSON ⇒ 中止。
    llm = FakeLLM([_extraction([]), "bad json {", _extraction([])])
    out = run_daily(conn, llm, now=_NOW, state_path=enabled)
    assert out["days_attempted"] == 2 and out["days_succeeded"] == 1
    assert _cursor_date(enabled) == "2026-06-08"  # 停在最後成功日
    assert len(llm.calls) == 2  # 06-10 未被嘗試（順序補跑紀律）


def test_cursor_up_to_date_no_days_processed(enabled):
    enabled.write_text(json.dumps({"last_success_utc_date": "2026-06-10"}))
    conn = _conn()
    out = run_daily(conn, FakeLLM([]), now=_NOW, state_path=enabled)
    assert out["days_attempted"] == 0
    assert conn.executed == []


# ── cron CLI 單日模式（E1-B 合流接縫：run_daily(conn, llm, target_date=day)）──


def test_target_date_mode_matches_e1b_call_shape_and_skips_cursor_file(
    enabled, monkeypatch, tmp_path
):
    """E1-B CLI 精確呼叫形不得 TypeError；單日模式完全不碰游標檔（CLI 自管）。"""
    from datetime import date

    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))  # 若誤走自管模式會留下游標檔
    conn = _conn(l2_rows=[_L2_ROW])
    llm = FakeLLM([_extraction([_mem(["l2:l2r:x1"])])])
    out = run_daily(conn, llm, target_date=date(2026, 6, 10))  # E1-B 呼叫形原樣
    assert out["status"] == "ok" and out["days_succeeded"] == 1
    assert out["day_results"][0]["utc_date"] == "2026-06-10"
    assert conn.count_sql("INSERT INTO agent.agent_memory") == 1
    assert not (tmp_path / "cron_state").exists()  # 游標檔零觸碰
    assert not enabled.exists()


def test_target_date_mode_failure_raises_for_cli_cursor_discipline(enabled):
    """單日模式失敗必 raise：CLI 以「無例外=成功」決定 write_cursor；
    靜默回 dict 會讓失敗日被 CLI 推進游標（違 §6.3 游標鐵則）。"""
    from datetime import date

    conn = _conn(l2_rows=[_L2_ROW])
    with pytest.raises(RuntimeError, match="2026-06-10"):
        run_daily(conn, FakeLLM(["bad json {"]), target_date=date(2026, 6, 10))
    assert conn.count_sql("INSERT INTO agent.agent_memory") == 0


def test_target_date_mode_disabled_raises_dedicated_exception(monkeypatch):
    """E2-A LOW-1 修復輪：target_date 模式 flag-OFF 必 raise 專用例外——
    CLI 以「無例外=成功」推進游標，回 disabled dict 會讓未處理日被誤推。"""
    from datetime import date

    monkeypatch.delenv(PIPELINE_FLAG_ENV, raising=False)
    with pytest.raises(PipelineDisabledError):
        run_daily(None, None, target_date=date(2026, 6, 10))


def test_pipeline_flag_gate_strips_whitespace(monkeypatch, tmp_path):
    """E2-A LOW-1：env 值 "1 "（尾隨空白）必須放行——CLI gate 已 strip，
    pipeline 不 strip 會造成 CLI 放行、pipeline 靜默 disabled 的判定縫。"""
    monkeypatch.setenv(PIPELINE_FLAG_ENV, "1 ")
    conn = _conn()
    out = run_daily(conn, FakeLLM([]), now=_NOW, state_path=tmp_path / "c.json")
    assert out["status"] == "ok"  # 不是 disabled


# ── LLM 適配（OllamaClient timeout= vs ABC timeout_s=）──────────────────────


class _TimeoutSOnlyLLM:
    def __init__(self):
        self.seen = None

    def generate(self, prompt, *, system="", temperature=0.3, max_tokens=500, timeout_s=None):
        self.seen = {"timeout_s": timeout_s}
        return SimpleNamespace(text="ok", success=True)


class _TimeoutOnlyLLM:
    def __init__(self):
        self.seen = None

    def generate(self, prompt, *, system=None, model=None, temperature=None,
                 max_tokens=1024, timeout=None, think=False):
        self.seen = {"timeout": timeout}
        return SimpleNamespace(text="ok", success=True)


def test_call_llm_adapts_timeout_param_name():
    a = _TimeoutSOnlyLLM()
    text, ok = pipeline_mod._call_llm(a, system="s", prompt="p")
    assert ok and a.seen == {"timeout_s": pipeline_mod.LLM_TIMEOUT_S}
    b = _TimeoutOnlyLLM()
    text, ok = pipeline_mod._call_llm(b, system="s", prompt="p")
    assert ok and b.seen == {"timeout": int(pipeline_mod.LLM_TIMEOUT_S)}


def test_call_llm_exception_returns_failure():
    class _Boom:
        def generate(self, prompt, **kwargs):
            raise ConnectionError("ollama down")

    text, ok = pipeline_mod._call_llm(_Boom(), system="s", prompt="p")
    assert text == "" and ok is False


def test_call_llm_blank_text_is_failure():
    class _Blank:
        def generate(self, prompt, **kwargs):
            return SimpleNamespace(text="   ", success=True)

    _text, ok = pipeline_mod._call_llm(_Blank(), system="s", prompt="p")
    assert ok is False


# ── MED-1 / MIT F-1：backfill flag=1 ⇒ 默認 embed client 真被構造（mutation 錨）──


def _add_backfill_routes(conn, *, pending_rows=()):
    """補嵌路徑所需 FakeConn 路由（欄存在 + meta 空 + pending rows）。"""
    conn.add_route("information_schema.columns", rows=[(1,)], columns=["?column?"])
    conn.add_route(
        "FROM agent.agent_memory_embedding_meta",
        rows=[], columns=["provider", "model", "dims"],
    )
    conn.add_route(
        "WHERE embedding_pending AND status = 'active'",
        rows=list(pending_rows), columns=["record_id", "content"],
    )
    conn.add_route("INSERT INTO agent.agent_memory_embedding_meta", rowcount=1)
    conn.add_route("SET embedding = %s::vector", rowcount=1)
    return conn


class _ScriptedUrlopen:
    """按 URL 路由的 fake urlopen：/api/tags 回模型清單、/v1/embeddings 回向量。"""

    def __init__(self, *, dims=4, raise_exc=None):
        self.dims = dims
        self.raise_exc = raise_exc
        self.urls: list[str] = []

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.urls.append(url)
        if self.raise_exc is not None:
            raise self.raise_exc
        if "/api/tags" in url:
            payload = {"models": [{"name": "bge-m3:latest"}]}
        else:
            body = json.loads(req.data.decode("utf-8"))
            payload = {"data": [{"embedding": [0.1] * self.dims} for _ in body["input"]]}
        data = json.dumps(payload).encode("utf-8")

        class _Resp:
            def read(self_inner):
                return data

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

        return _Resp()


def test_backfill_flag_on_constructs_default_client_and_reaches_embed_http(
    enabled, monkeypatch
):
    """MED-1 mutation 錨：flag=1 + 無注入 client ⇒ 默認 OllamaEmbeddingClient
    被 lazy 構造並真走到 /v1/embeddings HTTP（E2 指定 mock-urlopen 釘法）。
    把 _resolve_embed_client 中性化（恆回 None）⇒ 本測試紅。"""
    from datetime import date

    monkeypatch.setenv(EMBED_BACKFILL_FLAG_ENV, "1")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)  # 默認 loopback
    fake = _ScriptedUrlopen()
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    conn = _add_backfill_routes(
        _conn(), pending_rows=[("mem:a", "內容甲"), ("mem:b", "內容乙")]
    )
    # E1-B cron 呼叫形（生產路徑）；兩源皆空 ⇒ 蒸餾段 no-op，只走 backfill。
    out = run_daily(conn, FakeLLM([]), target_date=date(2026, 6, 10))
    assert out["backfill"]["status"] == "ok"
    assert out["backfill"]["embedded"] == 2
    assert any("/api/tags" in u for u in fake.urls)        # 可達性真探測
    assert any("/v1/embeddings" in u for u in fake.urls)   # 嵌入請求真外發


def test_backfill_flag_on_unreachable_ollama_fail_soft_embed_unavailable(
    enabled, monkeypatch
):
    """可達性探測 fail-soft：Ollama 不可達 ⇒ embed_unavailable，當日仍成功不 raise。"""
    from datetime import date

    monkeypatch.setenv(EMBED_BACKFILL_FLAG_ENV, "1")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    fake = _ScriptedUrlopen(raise_exc=ConnectionError("refused"))
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    conn = _add_backfill_routes(_conn())
    out = run_daily(conn, FakeLLM([]), target_date=date(2026, 6, 10))
    assert out["status"] == "ok"  # 探測失敗不殺管線
    assert out["backfill"]["status"] == "embed_unavailable"


def test_backfill_flag_off_never_constructs_client(enabled, monkeypatch):
    """flag gate 對偶：backfill flag-OFF ⇒ 零構造（不退化成無條件構造）。"""
    monkeypatch.delenv(EMBED_BACKFILL_FLAG_ENV, raising=False)
    constructed = []

    class _Recorder:
        def __init__(self, *a, **k):
            constructed.append(1)

    monkeypatch.setattr(embedding_mod, "OllamaEmbeddingClient", _Recorder)
    out = run_daily(_conn(), FakeLLM([]), now=_NOW, state_path=enabled)
    assert out["status"] == "ok" and constructed == []


def test_resolved_client_threads_into_recall_path(enabled, monkeypatch):
    """E2 MED-1 修法第二半：構造出的 client 必須 thread 進 recall L1
    （只接 backfill 不接 recall = 半修）。"""
    monkeypatch.setenv(EMBED_BACKFILL_FLAG_ENV, "1")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    seen_clients = []

    def _spy_recall(conn, text, k=5, *, embed_client=None, hint_mode=False):
        seen_clients.append(embed_client)
        return [], "skip"

    monkeypatch.setattr(pipeline_mod, "recall_top_k", _spy_recall)
    conn = _add_backfill_routes(_conn(l2_rows=[_L2_ROW]))
    fake = _ScriptedUrlopen()
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    llm = FakeLLM([_extraction([_mem(["l2:l2r:x1"])])])
    run_daily(conn, llm, now=_NOW, state_path=enabled)
    assert len(seen_clients) == 1
    assert isinstance(seen_clients[0], embedding_mod.OllamaEmbeddingClient)


def test_injected_embed_client_wins_over_lazy_construction(enabled, monkeypatch):
    """顯式注入優先：caller 注入的 client 原樣使用，不被默認構造覆蓋。"""
    monkeypatch.setenv(EMBED_BACKFILL_FLAG_ENV, "1")
    sentinel = object()
    assert pipeline_mod._resolve_embed_client(sentinel) is sentinel
    monkeypatch.delenv(EMBED_BACKFILL_FLAG_ENV, raising=False)
    assert pipeline_mod._resolve_embed_client(None) is None


# ── E3 MED-2：origin 譜系標記（untrusted 圍欄鍵）─────────────────────────────


def _insert_meta(conn, idx=0):
    inserts = [
        (s, p) for s, p in conn.executed if "INSERT INTO agent.agent_memory" in s
    ]
    return json.loads(inserts[idx][1][9])


def test_l2_sourced_memory_origin_untrusted(enabled):
    """l2_calls 材料含 raw_response（模型自由輸出）⇒ origin=l2_untrusted。"""
    conn = _conn(l2_rows=[_L2_ROW])
    llm = FakeLLM([_extraction([_mem(["l2:l2r:x1"])])])
    run_daily(conn, llm, now=_NOW, state_path=enabled)
    assert _insert_meta(conn)["origin"] == "l2_untrusted"


def test_drar_only_memory_origin_curated(enabled):
    """drar→postmortem 是本系統確定性 gate 輸出 ⇒ origin=l2_curated。"""
    drar_row = (7, "grid_trading", {"residual_mean_bps": 0.5}, _TS)
    conn = _conn(drar_rows=[drar_row])
    llm = FakeLLM([_extraction([_mem(["drar:7"])])])
    run_daily(conn, llm, now=_NOW, state_path=enabled)
    assert _insert_meta(conn)["origin"] == "l2_curated"


def test_origin_not_spoofable_by_llm_metadata(enabled):
    """origin 是系統擁有鍵：LLM 在 metadata 自填 origin 必被確定性推導覆蓋。"""
    conn = _conn(l2_rows=[_L2_ROW])
    spoofed = _mem(["l2:l2r:x1"], metadata={"origin": "l2_curated"})
    llm = FakeLLM([_extraction([spoofed])])
    run_daily(conn, llm, now=_NOW, state_path=enabled)
    assert _insert_meta(conn)["origin"] == "l2_untrusted"


def test_merge_origin_derived_from_union_refs(enabled):
    """merge 產物 origin 由並集 refs 推導：新候選帶 l2 源 ⇒ untrusted 傳染。"""
    old_row = ("mem:old0000001", "舊記憶內容", "rule", 80, "舊scene",
               [{"kind": "lesson", "id": 4}], "active", None, _TS, _TS)
    conn = _conn(l2_rows=[_L2_ROW], recall_rows=[_recall_hit()], old_rows=[old_row])
    dedup_reply = json.dumps([
        {"record_id": "mem:fixed0000001", "action": "merge",
         "target_ids": ["mem:old0000001"], "merged_content": "合併後記憶",
         "merged_type": "rule"}
    ])
    llm = FakeLLM([_extraction([_mem(["l2:l2r:x1"])]), dedup_reply])
    run_daily(conn, llm, now=_NOW, state_path=enabled)
    assert _insert_meta(conn)["origin"] == "l2_untrusted"


def test_every_pipeline_insert_carries_origin_key(enabled):
    """origin 必填鎖：管線寫入的每條 INSERT metadata 都帶 origin 鍵。"""
    drar_row = (7, "grid_trading", {"residual_mean_bps": 0.5}, _TS)
    conn = _conn(l2_rows=[_L2_ROW], drar_rows=[drar_row])
    mems = [_mem(["l2:l2r:x1"], content="記憶一"), _mem(["drar:7"], content="記憶二")]
    llm = FakeLLM([_extraction(mems)])
    run_daily(conn, llm, now=_NOW, state_path=enabled)
    inserts = [
        (s, p) for s, p in conn.executed if "INSERT INTO agent.agent_memory" in s
    ]
    assert len(inserts) == 2
    origins = {json.loads(p[9])["origin"] for _s, p in inserts}
    assert origins == {"l2_untrusted", "l2_curated"}


# ── E2-A LOW-2：event_start/event_end 可選時間透傳 ──────────────────────────


def _insert_event_window(conn):
    _sql, p = next(
        (s, p) for s, p in conn.executed if "INSERT INTO agent.agent_memory" in s
    )
    return p[7], p[8]  # _INSERT_SQL 欄序：event_start, event_end


def test_event_window_parsed_from_metadata_iso(enabled):
    conn = _conn(l2_rows=[_L2_ROW])
    cand = _mem(
        ["l2:l2r:x1"],
        metadata={
            "activity_start_time": "2026-06-10T03:00:00Z",
            "activity_end_time": "2026-06-10T04:30:00+00:00",
        },
    )
    run_daily(conn, FakeLLM([_extraction([cand])]), now=_NOW, state_path=enabled)
    start, end = _insert_event_window(conn)
    assert start == datetime(2026, 6, 10, 3, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 6, 10, 4, 30, tzinfo=timezone.utc)


def test_event_window_absent_stays_null(enabled):
    conn = _conn(l2_rows=[_L2_ROW])
    run_daily(
        conn, FakeLLM([_extraction([_mem(["l2:l2r:x1"])])]),
        now=_NOW, state_path=enabled,
    )
    assert _insert_event_window(conn) == (None, None)


def test_event_window_garbage_fail_soft_null(enabled):
    """LLM 時間幻覺/壞格式 ⇒ typed 欄留 NULL，記憶照存不 raise。"""
    conn = _conn(l2_rows=[_L2_ROW])
    cand = _mem(
        ["l2:l2r:x1"],
        metadata={"activity_start_time": "大約六月", "activity_end_time": 42},
    )
    out = run_daily(conn, FakeLLM([_extraction([cand])]), now=_NOW, state_path=enabled)
    assert out["day_results"][0]["stored"] == 1
    assert _insert_event_window(conn) == (None, None)


def test_event_window_inverted_range_dropped_to_null(enabled):
    """反向區間（end < start）= 幻覺 ⇒ 雙雙 NULL（原話仍在 metadata 字串）。"""
    conn = _conn(l2_rows=[_L2_ROW])
    cand = _mem(
        ["l2:l2r:x1"],
        metadata={
            "activity_start_time": "2026-06-10T05:00:00Z",
            "activity_end_time": "2026-06-10T03:00:00Z",
        },
    )
    run_daily(conn, FakeLLM([_extraction([cand])]), now=_NOW, state_path=enabled)
    assert _insert_event_window(conn) == (None, None)


def test_event_window_naive_iso_assumed_utc(enabled):
    conn = _conn(l2_rows=[_L2_ROW])
    cand = _mem(["l2:l2r:x1"], metadata={"activity_start_time": "2026-06-10T03:00:00"})
    run_daily(conn, FakeLLM([_extraction([cand])]), now=_NOW, state_path=enabled)
    start, end = _insert_event_window(conn)
    assert start == datetime(2026, 6, 10, 3, 0, tzinfo=timezone.utc) and end is None


# ── [88] 語義死亡軸資料源：day result 帶 materials_l2 ────────────────────────


def test_day_result_carries_materials_l2_count(enabled):
    drar_row = (7, "grid_trading", {"residual_mean_bps": 0.5}, _TS)
    conn = _conn(l2_rows=[_L2_ROW], drar_rows=[drar_row])
    mems = [_mem(["l2:l2r:x1"])]
    out = run_daily(conn, FakeLLM([_extraction(mems)]), now=_NOW, state_path=enabled)
    day = out["day_results"][0]
    assert day["materials"] == 2 and day["materials_l2"] == 1  # drar 不計入 l2 計數


def test_noop_day_result_materials_l2_zero(enabled):
    out = run_daily(_conn(), FakeLLM([]), now=_NOW, state_path=enabled)
    assert out["day_results"][0]["materials_l2"] == 0
