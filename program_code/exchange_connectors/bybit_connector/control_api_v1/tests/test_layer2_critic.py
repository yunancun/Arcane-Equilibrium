"""
Tests for Layer 2 Reflexion critic + lesson store — B 工作流（2026-06-05）。
Layer 2 critic / 教訓庫測試。

涵蓋（mock-only，不碰真 LLM / 真 PG / 真網路）：
  merge_critic_verdict — 最嚴重聚合（FIX 3 的純函式核心，mutation 可咬）。
  should_skip_critic    — 旗標關閉 / submit·record 工具 / error 結果 / <2 calls /
                          倒數第二輪，各跳過條件。
  run_critic            — fail-soft（provider None / 非 JSON / verdict 非法 / 例外
                          → CONTINUE）；使用最便宜 tier（role="triage"）。
  persist_lessons       — 恰一次 agent.lessons INSERT；尊重 symbol；無 insight 不寫。
  engine 整合           — 旗標開啟（mock）：STOP → COMPLETED + break（非 FAILED、
                          非 max-iter else）；REPLAN → 恰追加一則 CRITIC NOTE user
                          訊息且不移除任何既有訊息；[STOP, CONTINUE] → 仍煞車（FIX 3
                          end-to-end）。旗標關閉 → 無 critic 呼叫、無 PG 寫入。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import layer2_critic as critic  # noqa: E402
from app.layer2_critic import (  # noqa: E402
    LESSON_TRGM_MIN_SIM,
    CriticResult,
    merge_critic_verdict,
    persist_lessons,
    retrieve_lessons,
    run_critic,
    should_skip_critic,
)
from app.layer2_types import (  # noqa: E402
    CRITIC_VERDICT_CONTINUE,
    CRITIC_VERDICT_REPLAN,
    CRITIC_VERDICT_STOP,
    ENV_L2_CRITIC_ENABLED,
    ENV_L2_LESSON_STORE_ENABLED,
    Insight,
    Layer2Config,
    Layer2Session,
    SESSION_STATE_COMPLETED,
    TOOL_RECORD_INSIGHT,
    TOOL_SUBMIT_RECOMMENDATION,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助
# ═══════════════════════════════════════════════════════════════════════════════


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _session(n_tool_calls: int = 0, iterations: int = 1) -> Layer2Session:
    s = Layer2Session()
    s.iterations = iterations
    # tool_calls 內容對 should_skip_critic 只看長度，塞佔位物件即可。
    s.tool_calls = [MagicMock() for _ in range(n_tool_calls)]
    return s


class _FakeResp:
    """模擬 _provider_complete 回傳物件（只需 text / token 數）。"""

    def __init__(self, text: str, in_tok: int = 10, out_tok: int = 5):
        self.text = text
        self.input_tokens = in_tok
        self.output_tokens = out_tok


def _fake_engine(provider_text: str | None = "{}"):
    """
    構造一個最小 fake engine，提供 run_critic 需要的 4 個介面：
      _cost_tracker.get_config()/.record_claude_cost()、_resolve_effective_provider()、
      _provider_complete()（AsyncMock，回 _FakeResp 或 None）。
    回 (engine, resolve_mock) 供斷言 triage tier 使用。
    """
    engine = MagicMock()
    cfg = MagicMock()
    cfg.default_provider = "anthropic"
    engine._cost_tracker.get_config.return_value = cfg
    engine._cost_tracker.record_claude_cost = MagicMock()

    resolve_mock = MagicMock(return_value=("anthropic", "haiku"))
    engine._resolve_effective_provider = resolve_mock

    resp = None if provider_text is None else _FakeResp(provider_text)
    engine._provider_complete = AsyncMock(return_value=resp)
    return engine, resolve_mock


# ═══════════════════════════════════════════════════════════════════════════════
# merge_critic_verdict — 最嚴重聚合（FIX 3 核心）
# ═══════════════════════════════════════════════════════════════════════════════


class TestMergeCriticVerdict:
    def test_none_inputs(self):
        assert merge_critic_verdict(None, None) is None

    def test_none_current_returns_incoming(self):
        inc = CriticResult(CRITIC_VERDICT_REPLAN, "r")
        assert merge_critic_verdict(None, inc) is inc

    def test_none_incoming_keeps_current(self):
        cur = CriticResult(CRITIC_VERDICT_STOP, "s")
        assert merge_critic_verdict(cur, None) is cur

    def test_stop_beats_continue_regardless_of_order(self):
        stop = CriticResult(CRITIC_VERDICT_STOP, "halt")
        cont = CriticResult(CRITIC_VERDICT_CONTINUE, "go")
        # STOP 先到、CONTINUE 後到 → 仍 STOP（這正是 last-wins 的反例）。
        assert merge_critic_verdict(stop, cont).verdict == CRITIC_VERDICT_STOP
        # 反向順序同樣 STOP。
        assert merge_critic_verdict(cont, stop).verdict == CRITIC_VERDICT_STOP

    def test_stop_beats_replan(self):
        stop = CriticResult(CRITIC_VERDICT_STOP, "halt")
        replan = CriticResult(CRITIC_VERDICT_REPLAN, "rethink")
        assert merge_critic_verdict(replan, stop).verdict == CRITIC_VERDICT_STOP
        assert merge_critic_verdict(stop, replan).verdict == CRITIC_VERDICT_STOP

    def test_replan_beats_continue(self):
        replan = CriticResult(CRITIC_VERDICT_REPLAN, "rethink")
        cont = CriticResult(CRITIC_VERDICT_CONTINUE, "go")
        assert merge_critic_verdict(cont, replan).verdict == CRITIC_VERDICT_REPLAN

    def test_equal_severity_keeps_current_stable(self):
        a = CriticResult(CRITIC_VERDICT_CONTINUE, "first")
        b = CriticResult(CRITIC_VERDICT_CONTINUE, "second")
        # 嚴重度相等 → 保留 current（不抖動）。
        assert merge_critic_verdict(a, b) is a

    def test_unknown_verdict_does_not_beat_valid(self):
        bogus = CriticResult("garbage", "?")
        replan = CriticResult(CRITIC_VERDICT_REPLAN, "rethink")
        # 未知 verdict 視為最不嚴重，不可壓過 replan。
        assert merge_critic_verdict(replan, bogus).verdict == CRITIC_VERDICT_REPLAN


# ═══════════════════════════════════════════════════════════════════════════════
# should_skip_critic — 跳過條件
# ═══════════════════════════════════════════════════════════════════════════════


class TestShouldSkipCritic:
    def setup_method(self):
        os.environ.pop(ENV_L2_CRITIC_ENABLED, None)

    def teardown_method(self):
        os.environ.pop(ENV_L2_CRITIC_ENABLED, None)

    def _cfg(self) -> Layer2Config:
        return Layer2Config()

    def test_flag_off_always_skips(self):
        # 旗標未設 → 預設關閉 → 一律跳過（即使其他條件都滿足）。
        s = _session(n_tool_calls=5, iterations=1)
        assert should_skip_critic("get_cvd", "{}", s, self._cfg()) is True

    def test_submit_recommendation_skipped(self):
        with patch.dict(os.environ, {ENV_L2_CRITIC_ENABLED: "1"}, clear=False):
            s = _session(n_tool_calls=5, iterations=1)
            assert should_skip_critic(TOOL_SUBMIT_RECOMMENDATION, "{}", s, self._cfg()) is True

    def test_record_insight_skipped(self):
        with patch.dict(os.environ, {ENV_L2_CRITIC_ENABLED: "1"}, clear=False):
            s = _session(n_tool_calls=5, iterations=1)
            assert should_skip_critic(TOOL_RECORD_INSIGHT, "{}", s, self._cfg()) is True

    def test_error_result_skipped(self):
        with patch.dict(os.environ, {ENV_L2_CRITIC_ENABLED: "1"}, clear=False):
            s = _session(n_tool_calls=5, iterations=1)
            # 大小寫不敏感地偵測 error。
            assert should_skip_critic("get_cvd", '{"ERROR": "x"}', s, self._cfg()) is True

    def test_too_few_tool_calls_skipped(self):
        with patch.dict(os.environ, {ENV_L2_CRITIC_ENABLED: "1"}, clear=False):
            s = _session(n_tool_calls=1, iterations=1)
            assert should_skip_critic("get_cvd", "{}", s, self._cfg()) is True

    def test_last_iteration_skipped(self):
        cfg = self._cfg()
        with patch.dict(os.environ, {ENV_L2_CRITIC_ENABLED: "1"}, clear=False):
            # iterations 到達 max-1 → 再 replan 無意義 → 跳過。
            s = _session(n_tool_calls=5, iterations=max(cfg.max_iterations - 1, 0))
            assert should_skip_critic("get_cvd", "{}", s, cfg) is True

    def test_not_skipped_when_all_conditions_met(self):
        cfg = self._cfg()
        with patch.dict(os.environ, {ENV_L2_CRITIC_ENABLED: "1"}, clear=False):
            s = _session(n_tool_calls=2, iterations=1)
            # 旗標開 + 普通工具 + 非 error + >=2 calls + 非倒數第二輪 → 不跳過。
            assert should_skip_critic("get_cvd", "{}", s, cfg) is False


# ═══════════════════════════════════════════════════════════════════════════════
# run_critic — fail-soft + triage tier
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunCritic:
    def test_provider_none_returns_continue(self):
        engine, _ = _fake_engine(provider_text=None)
        out = _run(run_critic(engine, _session(), "get_cvd", {}, "{}"))
        assert out.verdict == CRITIC_VERDICT_CONTINUE

    def test_non_json_returns_continue(self):
        engine, _ = _fake_engine(provider_text="this is not json at all")
        out = _run(run_critic(engine, _session(), "get_cvd", {}, "{}"))
        assert out.verdict == CRITIC_VERDICT_CONTINUE

    def test_invalid_verdict_returns_continue(self):
        engine, _ = _fake_engine(provider_text='{"verdict": "explode", "reason": "x"}')
        out = _run(run_critic(engine, _session(), "get_cvd", {}, "{}"))
        assert out.verdict == CRITIC_VERDICT_CONTINUE

    def test_exception_returns_continue(self):
        engine, _ = _fake_engine(provider_text="{}")
        # 讓 _provider_complete 拋例外 → 必須 fail-soft 回 CONTINUE，不外拋。
        engine._provider_complete = AsyncMock(side_effect=RuntimeError("boom"))
        out = _run(run_critic(engine, _session(), "get_cvd", {}, "{}"))
        assert out.verdict == CRITIC_VERDICT_CONTINUE

    def test_valid_stop_parsed(self):
        engine, _ = _fake_engine(provider_text='{"verdict": "stop", "reason": "obvious"}')
        out = _run(run_critic(engine, _session(), "get_cvd", {}, "{}"))
        assert out.verdict == CRITIC_VERDICT_STOP
        assert out.reason == "obvious"

    def test_valid_replan_parsed(self):
        engine, _ = _fake_engine(provider_text='{"verdict": "replan", "reason": "looping"}')
        out = _run(run_critic(engine, _session(), "get_cvd", {}, "{}"))
        assert out.verdict == CRITIC_VERDICT_REPLAN
        assert out.reason == "looping"

    def test_uses_cheapest_triage_tier(self):
        engine, resolve_mock = _fake_engine(provider_text='{"verdict": "continue"}')
        _run(run_critic(engine, _session(), "get_cvd", {}, "{}"))
        # 必須以 role="triage" 解析 effective provider（強制最便宜 tier）。
        assert resolve_mock.called
        _, kwargs = resolve_mock.call_args
        assert kwargs.get("role") == "triage"

    def test_records_cost_through_tracker(self):
        engine, _ = _fake_engine(provider_text='{"verdict": "continue"}')
        _run(run_critic(engine, _session(), "get_cvd", {}, "{}"))
        # 成本必須走既有 budget 管線。
        assert engine._cost_tracker.record_claude_cost.called


# ═══════════════════════════════════════════════════════════════════════════════
# persist_lessons — 恰一次 INSERT / 尊重 symbol / 無 insight 不寫
# ═══════════════════════════════════════════════════════════════════════════════


def _mock_db_conn():
    """構造可 patch 的 get_pg_conn context manager + cursor，回 (cm, cur)。"""
    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cur
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=conn)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, cur, conn


class TestPersistLessons:
    def test_no_insights_no_write(self):
        cm, cur, conn = _mock_db_conn()
        with patch("app.layer2_critic.db_pool.get_pg_conn", return_value=cm):
            _run(persist_lessons([], Layer2Session(), "BTCUSDT"))
        # 無 insight → 完全不應觸碰 DB（連線都不取）。
        cm.__enter__.assert_not_called()
        cur.executemany.assert_not_called()

    def test_single_insert_for_insights(self):
        cm, cur, conn = _mock_db_conn()
        insights = [
            Insight(category="macro", title="t1", detail="d1"),
            Insight(category="technical", title="t2", detail="d2"),
        ]
        with patch("app.layer2_critic.db_pool.get_pg_conn", return_value=cm):
            _run(persist_lessons(insights, Layer2Session(), "ETHUSDT"))
        # 恰一次 executemany（單一 INSERT 模板，多 value tuple）。
        cur.executemany.assert_called_once()
        conn.commit.assert_called_once()
        sql, rows = cur.executemany.call_args[0]
        assert "INSERT INTO agent.lessons" in sql
        # symbol 必須被尊重（兩列都帶 ETHUSDT 作首欄）。
        assert len(rows) == 2
        assert all(r[0] == "ETHUSDT" for r in rows)

    def test_db_unavailable_no_raise(self):
        # conn 為 None（DB 不可用）→ 靜默放棄、不 raise、不 commit。
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=None)
        cm.__exit__ = MagicMock(return_value=False)
        insights = [Insight(category="macro", title="t", detail="d")]
        with patch("app.layer2_critic.db_pool.get_pg_conn", return_value=cm):
            # 不應拋例外
            _run(persist_lessons(insights, Layer2Session(), "BTCUSDT"))

    def test_empty_content_insight_not_written(self):
        cm, cur, conn = _mock_db_conn()
        # title + detail 皆空 → content 空 → 該列不落庫 → 無 row → 不 INSERT。
        insights = [Insight(category="macro", title="", detail="")]
        with patch("app.layer2_critic.db_pool.get_pg_conn", return_value=cm):
            _run(persist_lessons(insights, Layer2Session(), "BTCUSDT"))
        cur.executemany.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# retrieve_lessons — trgm 相似度查詢必須降門檻（MIT V133 實證：預設 0.3 回 0 列）
# ═══════════════════════════════════════════════════════════════════════════════


def _trgm_capture_conn():
    """
    構造可捕捉 execute 呼叫的 get_pg_conn cm + cursor。

    cursor.execute 把每次 (sql, params) 記入 calls；description/fetchall 讓
    _rows_to_dicts 能在 trgm 分支回一列（避免落到 recency 兜底分支）。
    回 (cm, cur, calls)。
    """
    calls: list[tuple[str, Any]] = []
    cur = MagicMock()

    def _execute(sql, params=None):
        calls.append((sql, params))

    cur.execute.side_effect = _execute
    # 讓 trgm 查詢回一列（含 id 欄即可），使 retrieve 在相似度分支就返回。
    cur.description = [
        ("id",), ("created_at",), ("symbol",), ("lesson_type",),
        ("content",), ("session_trigger",), ("context_id",), ("source",),
    ]
    cur.fetchall.return_value = [
        (1, "ts", "BTCUSDT", "macro", "lesson body", "manual", "ctx", "l2_session"),
    ]

    conn = MagicMock()
    conn.cursor.return_value = cur
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=conn)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, cur, calls


class TestRetrieveLessonsTrgmThreshold:
    """
    結構性斷言（Mac mock 無法跑真 trgm scoring，僅驗 SQL 結構）：
      相似度分支必須先 `SET LOCAL pg_trgm.similarity_threshold = <const>`，
      且 const = LESSON_TRGM_MIN_SIM（0.1），而非 pg_trgm 預設 0.3。
      MIT 實證真正相關教訓 similarity≈0.27 < 0.3，預設門檻下 `%` 回 0 列。
      行為驗證（≈0.27 場景現在回列）owed 給 E4 在 Linux PG 跑。
    """

    def test_const_value_is_lowered(self):
        # 常數必須明顯低於 pg_trgm 預設 0.3（避免有人改回預設）。
        assert LESSON_TRGM_MIN_SIM == pytest.approx(0.1)
        assert LESSON_TRGM_MIN_SIM < 0.3

    def test_similarity_query_sets_local_threshold_with_const(self):
        cm, cur, calls = _trgm_capture_conn()
        with patch("app.layer2_critic.db_pool.get_pg_conn", return_value=cm):
            rows = _run(retrieve_lessons("BTCUSDT", "funding spike squeeze"))
        # trgm 分支命中（回一列）→ 不應落到 recency。
        assert len(rows) == 1

        # 第一個 execute 必須是 SET LOCAL 門檻，且綁定 LESSON_TRGM_MIN_SIM 常數。
        set_local_calls = [
            (sql, params) for (sql, params) in calls
            if "SET LOCAL pg_trgm.similarity_threshold" in sql
        ]
        assert len(set_local_calls) == 1, calls
        _, set_params = set_local_calls[0]
        assert set_params == (LESSON_TRGM_MIN_SIM,)

        # 相似度 SELECT 仍用 `%` 運算子（保留 gin 索引使用），且排在 SET LOCAL 之後。
        sim_idx = next(
            i for i, (sql, _) in enumerate(calls)
            if "content %" in sql and "similarity(content" in sql
        )
        set_idx = next(
            i for i, (sql, _) in enumerate(calls)
            if "SET LOCAL pg_trgm.similarity_threshold" in sql
        )
        assert set_idx < sim_idx
        # 不得用 explicit `similarity(...) > %s` 取代 `%`（本實作走 SET LOCAL + `%`）。
        assert "similarity(content, %s) >" not in calls[sim_idx][0]

    def test_empty_hint_skips_trgm_goes_recency(self):
        cm, cur, calls = _trgm_capture_conn()
        with patch("app.layer2_critic.db_pool.get_pg_conn", return_value=cm):
            _run(retrieve_lessons("BTCUSDT", ""))
        # hint 為空 → 不發 trgm / 不設門檻，直接 recency 排序。
        assert not any(
            "SET LOCAL pg_trgm.similarity_threshold" in sql for sql, _ in calls
        )
        assert any("ORDER BY created_at DESC" in sql for sql, _ in calls)


# ═══════════════════════════════════════════════════════════════════════════════
# Engine 整合 — flag-ON（mock critic）：STOP / REPLAN / 最嚴重 end-to-end
#                flag-OFF：無 critic、無 PG
# ═══════════════════════════════════════════════════════════════════════════════


def _tool_use(name: str = "get_market_state", _id: str = "t1"):
    from app.provider_client import ToolUse
    return ToolUse(id=_id, name=name, input={"symbol": "BTCUSDT"})


def _make_engine(tmp_cost_file):
    from app.layer2_cost_tracker import Layer2CostTracker
    from app.layer2_engine import Layer2Engine
    tracker = Layer2CostTracker(state_file=tmp_cost_file)
    return Layer2Engine(cost_tracker=tracker), tracker


def _fake_provider():
    """fake provider：append_* 改 messages（沿用 test_layer2.py 範式）。"""
    fp = MagicMock()
    fp.append_assistant_message.side_effect = (
        lambda messages, response: messages.append(
            {"role": "assistant", "content": response.text or "tool_use"}
        )
    )
    fp.append_tool_results.side_effect = (
        lambda messages, results: messages.append(
            {"role": "user", "content": json.dumps(results)}
        )
    )
    return fp


class TestEngineCriticIntegration:
    """
    驅動 run_session，patch should_skip_critic=False + run_critic 回指定 verdict，
    隔離引擎 B-Hook 2/3 的處置邏輯。critic 旗標用 lesson-store 旗標控制 B-Hook 4。
    """

    def setup_method(self):
        os.environ.pop(ENV_L2_CRITIC_ENABLED, None)
        os.environ.pop(ENV_L2_LESSON_STORE_ENABLED, None)

    def teardown_method(self):
        os.environ.pop(ENV_L2_CRITIC_ENABLED, None)
        os.environ.pop(ENV_L2_LESSON_STORE_ENABLED, None)

    def _stop_capable_response(self):
        from app.provider_client import L2Response
        # 單輪含一個 tool_use，迴圈會跑 B-Hook，再依 critic 處置。
        return L2Response(
            stop_reason="tool_use",
            tool_uses=[_tool_use()],
            input_tokens=300,
            output_tokens=80,
        )

    def test_stop_verdict_completes_and_breaks(self, tmp_cost_file):
        engine, tracker = _make_engine(tmp_cost_file)
        tool_resp = self._stop_capable_response()
        fp = _fake_provider()
        with (
            patch.object(engine, "_provider_complete", new=AsyncMock(return_value=tool_resp)),
            patch("app.layer2_engine._pc.get_provider", return_value=fp),
            patch("app.layer2_engine._critic.should_skip_critic", return_value=False),
            patch(
                "app.layer2_engine._critic.run_critic",
                new=AsyncMock(return_value=CriticResult(CRITIC_VERDICT_STOP, "obvious")),
            ),
        ):
            session = _run(engine.run_session(trigger="manual", symbol="BTCUSDT"))
        # STOP → COMPLETED（非 FAILED）；在 iter 1 即 break（未進 max-iter else）。
        assert session.state == SESSION_STATE_COMPLETED
        assert session.iterations == 1
        assert "Critic stopped session" in (session.final_summary or "")
        # 未跑到 max-iterations（否則 summary 會是 "Reached max iterations"）。
        assert "Reached max iterations" not in (session.final_summary or "")

    def test_replan_appends_exactly_one_note_and_mutates_nothing(self, tmp_cost_file):
        engine, tracker = _make_engine(tmp_cost_file)
        from app.provider_client import L2Response
        tool_resp = self._stop_capable_response()
        end_resp = L2Response(
            text="done", stop_reason="end_turn", input_tokens=200, output_tokens=50
        )
        fp = _fake_provider()

        captured = {}

        # 包一層 run_session：在 REPLAN 之後、下一輪 _provider_complete 之前，
        # 記錄當時 messages 快照，驗證「恰追加一則、且不移除既有」。
        orig_complete = AsyncMock(side_effect=[tool_resp, end_resp])

        with (
            patch.object(engine, "_provider_complete", new=orig_complete),
            patch("app.layer2_engine._pc.get_provider", return_value=fp),
            patch("app.layer2_engine._critic.should_skip_critic", return_value=False),
            patch(
                "app.layer2_engine._critic.run_critic",
                new=AsyncMock(return_value=CriticResult(CRITIC_VERDICT_REPLAN, "looping")),
            ),
        ):
            session = _run(engine.run_session(trigger="manual", symbol="BTCUSDT"))

        # REPLAN 不終止 session（繼續到 end_turn）。
        assert session.state == SESSION_STATE_COMPLETED
        assert session.iterations == 2
        # 第二輪傳給 _provider_complete 的 messages 必含恰一則 CRITIC NOTE user 訊息。
        second_call_messages = orig_complete.call_args_list[1].kwargs["messages"]
        critic_notes = [
            m for m in second_call_messages
            if m.get("role") == "user"
            and isinstance(m.get("content"), str)
            and m["content"].startswith("CRITIC NOTE:")
        ]
        assert len(critic_notes) == 1
        assert "looping" in critic_notes[0]["content"]
        # 第一則 user 訊息（原始 user_message）仍在，未被移除/改動。
        assert second_call_messages[0]["role"] == "user"
        assert not second_call_messages[0]["content"].startswith("CRITIC NOTE:")

    def test_most_severe_stop_then_continue_acts_on_stop(self, tmp_cost_file):
        """FIX 3 end-to-end：同輪 [STOP, CONTINUE] 兩 tool → 仍煞車為 STOP。"""
        engine, tracker = _make_engine(tmp_cost_file)
        from app.provider_client import L2Response
        # 同一輪兩個 tool_use → run_critic 被叫兩次。
        tool_resp = L2Response(
            stop_reason="tool_use",
            tool_uses=[_tool_use(_id="t1"), _tool_use(_id="t2")],
            input_tokens=300,
            output_tokens=80,
        )
        fp = _fake_provider()
        with (
            patch.object(engine, "_provider_complete", new=AsyncMock(return_value=tool_resp)),
            patch("app.layer2_engine._pc.get_provider", return_value=fp),
            patch("app.layer2_engine._critic.should_skip_critic", return_value=False),
            patch(
                "app.layer2_engine._critic.run_critic",
                new=AsyncMock(side_effect=[
                    CriticResult(CRITIC_VERDICT_STOP, "halt"),
                    CriticResult(CRITIC_VERDICT_CONTINUE, "go"),
                ]),
            ),
        ):
            session = _run(engine.run_session(trigger="manual", symbol="BTCUSDT"))
        # 若 last-wins：final=CONTINUE → 不煞車 → 跑到 max-iter else。
        # 最嚴重聚合：final=STOP → COMPLETED + break at iter 1。
        assert session.state == SESSION_STATE_COMPLETED
        assert session.iterations == 1
        assert "Critic stopped session" in (session.final_summary or "")

    def test_flags_off_no_critic_call_no_pg(self, tmp_cost_file):
        engine, tracker = _make_engine(tmp_cost_file)
        from app.provider_client import L2Response
        # 旗標全關（setup 已清空），單輪 end_turn 直接完成。
        end_resp = L2Response(
            text="done", stop_reason="end_turn", input_tokens=200, output_tokens=50
        )
        fp = _fake_provider()
        skip_spy = MagicMock(wraps=critic.should_skip_critic)
        persist_spy = AsyncMock(wraps=critic.persist_lessons)
        with (
            patch.object(engine, "_provider_complete", new=AsyncMock(return_value=end_resp)),
            patch("app.layer2_engine._pc.get_provider", return_value=fp),
            patch("app.layer2_engine._critic.should_skip_critic", new=skip_spy),
            patch("app.layer2_engine._critic.persist_lessons", new=persist_spy),
            patch("app.layer2_critic.db_pool.get_pg_conn") as pg_mock,
        ):
            session = _run(engine.run_session(trigger="manual", symbol="BTCUSDT"))
        assert session.state == SESSION_STATE_COMPLETED
        # end_turn 在 tool 迴圈前 break → B-Hook 2 不會被觸發。
        skip_spy.assert_not_called()
        # 旗標關閉 → B-Hook 4 lesson persist 完全不執行 → 無 PG 連線。
        persist_spy.assert_not_called()
        pg_mock.assert_not_called()
