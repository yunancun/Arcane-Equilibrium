"""
Tests for Layer 2 AI Reasoning Engine / L2 AI 推理引擎测试

覆盖范围 / Coverage:
  - layer2_types: data structures, PricingTable, Layer2Config, AdaptiveBudgetState, Layer2Session
  - layer2_cost_tracker: cost recording, daily budget, adaptive multiplier, pricing, session history
  - layer2_tools: ToolExecutor, SearchProvider degradation, tool schemas
  - layer2_engine: L1 triage, L2 agent loop (mocked), model upgrade triage, paper integration
  - layer2_routes: all 9 routes via TestClient
  - Safety invariants: is_simulated, daily hard cap, budget enforcement
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.layer2_types import (
    ADAPTIVE_MIN_DAYS,
    ADAPTIVE_TIERS,
    DEFAULT_DAILY_HARD_CAP_USD,
    DEFAULT_SESSION_BUDGET_SONNET_USD,
    DEFAULT_SESSION_BUDGET_OPUS_USD,
    MODEL_HAIKU,
    MODEL_IDS,
    MODEL_OPUS,
    MODEL_SONNET,
    MAX_AGENT_ITERATIONS,
    PRICING_VERIFY_INTERVAL_DAYS,
    SESSION_STATE_BUDGET_EXCEEDED,
    SESSION_STATE_COMPLETED,
    SESSION_STATE_FAILED,
    SESSION_STATE_PENDING,
    SESSION_STATE_RUNNING,
    SEARCH_PROVIDER_PERPLEXITY,
    SEARCH_PROVIDER_WEBPILOT,
    TOOL_GET_MARKET_STATE,
    TOOL_SUBMIT_RECOMMENDATION,
    TOOL_WEB_SEARCH,
    AdaptiveBudgetState,
    Insight,
    Layer2Config,
    Layer2Session,
    ModelPricing,
    PricingTable,
    Recommendation,
    SearchResponse,
    SearchResult,
    ToolCallRecord,
)
from app.layer2_cost_tracker import Layer2CostTracker
from app.provider_client import L2Response, ToolUse
from app.layer2_tools import (
    TOOL_SCHEMAS,
    ToolExecutor,
    PerplexitySearchProvider,
    WebPilotSearchProvider,
    search_with_degradation,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures / 测试夹具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_cost_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def cost_tracker(tmp_cost_file):
    return Layer2CostTracker(state_file=tmp_cost_file)


@pytest.fixture
def session():
    return Layer2Session()


def _run(coro):
    # Py 3.12：asyncio.get_event_loop() 在無 current loop 時 raise RuntimeError。
    # 前序 test 可能關閉 loop，故每 call 自管 new loop + close，不污染 global state。
    # Py 3.12: asyncio.get_event_loop() raises when no current loop exists.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Types Tests / 类型测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayer2Types:
    """Tests for layer2_types.py"""

    def test_search_result_defaults(self):
        r = SearchResult(title="test", snippet="test snippet")
        assert r.title == "test"
        assert r.provider == ""
        assert r.confidence == 0.0

    def test_search_response_defaults(self):
        r = SearchResponse(query="btc news")
        assert r.results == []
        assert r.error is None
        assert not r.is_degraded

    def test_tool_call_record_timestamp(self):
        tc = ToolCallRecord(tool_name="test_tool")
        assert tc.timestamp_ms > 0
        assert tc.error is None

    def test_recommendation_fields(self):
        rec = Recommendation(
            action="buy", symbol="BTCUSDT", confidence=0.8,
            edge_bps=15.0, reasoning="test",
        )
        assert rec.action == "buy"
        assert rec.suggested_size_fraction == 0.02

    def test_insight_fields(self):
        ins = Insight(category="macro", title="Fed rate", detail="Rate unchanged")
        assert ins.confidence == 0.0

    def test_layer2_session_to_dict(self):
        s = Layer2Session()
        d = s.to_dict()
        assert d["state"] == SESSION_STATE_PENDING
        assert d["is_simulated"] is True
        assert d["data_category"] == "paper_simulated"
        assert d["recommendation"] is None
        assert d["total_cost_usd"] == 0.0

    def test_layer2_session_with_recommendation(self):
        s = Layer2Session()
        s.recommendation = Recommendation(
            action="sell", symbol="ETHUSDT", confidence=0.7,
            edge_bps=10.0, reasoning="bearish signal",
        )
        d = s.to_dict()
        assert d["recommendation"]["action"] == "sell"
        assert d["recommendation"]["symbol"] == "ETHUSDT"

    def test_session_total_cost(self):
        s = Layer2Session()
        s.cost_usd = 0.5
        s.search_cost_usd = 0.01
        assert s.total_cost() == 0.51

    def test_session_duration(self):
        s = Layer2Session()
        s.started_at_ms = 1000
        s.completed_at_ms = 5000
        assert s.duration_ms() == 4000

    def test_session_duration_none(self):
        s = Layer2Session()
        assert s.duration_ms() is None

    def test_model_pricing_cost(self):
        mp = ModelPricing(model_id="test", input_per_mtok=3.0, output_per_mtok=15.0)
        cost = mp.cost_for_tokens(1000, 500)
        # 1000/1M * 3.0 + 500/1M * 15.0 = 0.003 + 0.0075 = 0.0105
        assert abs(cost - 0.0105) < 0.0001

    def test_pricing_table_defaults(self):
        pt = PricingTable()
        assert MODEL_HAIKU in pt.models
        assert MODEL_SONNET in pt.models
        assert MODEL_OPUS in pt.models
        assert pt.perplexity_per_search == 0.005

    def test_pricing_table_stale_detection(self):
        pt = PricingTable()
        # With current date as verified, should not be stale
        assert not pt.is_stale("2026-03-27")
        # 60 days later should be stale
        assert pt.is_stale("2026-05-27")

    def test_pricing_table_to_dict(self):
        pt = PricingTable()
        d = pt.to_dict()
        assert "models" in d
        assert "is_stale" in d

    def test_layer2_config_defaults(self):
        c = Layer2Config()
        assert c.daily_hard_cap_usd == DEFAULT_DAILY_HARD_CAP_USD
        assert c.default_model == MODEL_SONNET
        assert c.max_iterations == MAX_AGENT_ITERATIONS

    def test_layer2_config_to_dict(self):
        c = Layer2Config()
        d = c.to_dict()
        assert d["daily_hard_cap_usd"] == 2.0
        assert d["adaptive_enabled"] is True

    def test_adaptive_budget_state_to_dict(self):
        a = AdaptiveBudgetState(multiplier=1.5, roi_7d=2.5)
        d = a.to_dict()
        assert d["multiplier"] == 1.5
        assert d["roi_7d"] == 2.5

    def test_adaptive_budget_state_none_roi(self):
        a = AdaptiveBudgetState()
        d = a.to_dict()
        assert d["roi_7d"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# Cost Tracker Tests / 成本追踪器测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayer2CostTracker:
    """Tests for layer2_cost_tracker.py"""

    def test_init_creates_default_state(self, cost_tracker, tmp_cost_file):
        assert os.path.exists(tmp_cost_file)
        with open(tmp_cost_file) as f:
            data = json.load(f)
        assert "daily_spend" in data
        assert "sessions" in data
        assert "config" in data
        assert "pricing" in data

    def test_get_daily_spend_default(self, cost_tracker):
        spend = cost_tracker.get_daily_spend()
        assert spend["total_usd"] == 0.0
        assert spend["session_count"] == 0

    def test_check_daily_budget_ok(self, cost_tracker):
        allowed, remaining = cost_tracker.check_daily_budget()
        assert allowed is True
        # Remaining is min(hard_cap, adaptive_effective) when adaptive enabled
        assert remaining > 0
        assert remaining <= DEFAULT_DAILY_HARD_CAP_USD

    def test_record_claude_cost(self, cost_tracker, session):
        cost = cost_tracker.record_claude_cost(session, input_tokens=1000, output_tokens=500, model_tier=MODEL_SONNET)
        assert cost > 0
        assert session.cost_usd > 0
        assert session.input_tokens == 1000
        assert session.output_tokens == 500

    def test_record_claude_cost_unknown_tier(self, cost_tracker, session):
        # Unknown tier should fall back to sonnet
        cost = cost_tracker.record_claude_cost(session, input_tokens=100, output_tokens=50, model_tier="unknown_model")
        assert cost > 0

    def test_record_search_cost(self, cost_tracker, session):
        cost_tracker.record_search_cost(session, "perplexity", 0.005)
        assert session.search_cost_usd == 0.005
        spend = cost_tracker.get_daily_spend()
        assert spend["search_usd"] == 0.005

    def test_daily_hard_cap_enforcement(self, cost_tracker, session):
        # Exhaust daily budget
        for _ in range(100):
            cost_tracker.record_claude_cost(session, input_tokens=100000, output_tokens=50000, model_tier=MODEL_OPUS)
        allowed, remaining = cost_tracker.check_daily_budget()
        # After many expensive calls, should be over budget
        assert remaining <= 0 or not allowed

    def test_effective_session_budget_sonnet(self, cost_tracker):
        budget = cost_tracker.get_effective_session_budget(MODEL_SONNET)
        assert budget > 0
        assert budget <= DEFAULT_DAILY_HARD_CAP_USD

    def test_effective_session_budget_opus(self, cost_tracker):
        budget = cost_tracker.get_effective_session_budget(MODEL_OPUS)
        assert budget >= DEFAULT_SESSION_BUDGET_OPUS_USD or budget <= DEFAULT_DAILY_HARD_CAP_USD

    # ── G3-08 Phase 3 Sub-task 3-1: H2 budget integration tests ──
    # PA RFC `2026-04-26--g3_08_phase3_subtask_split.md` §4

    def test_get_h2_snapshot_schema(self, cost_tracker):
        """H2 snapshot returns 3 PA-spec fields (Rust H2BudgetState parity)."""
        snap = cost_tracker.get_h2_snapshot()
        assert isinstance(snap, dict)
        # Schema parity with Rust H2BudgetState (rust/openclaw_engine/src/
        # h_state_cache/types.rs:58-72): exactly 3 fields, no extra/missing.
        assert set(snap.keys()) == {
            "daily_remaining_usd",
            "hard_cap_usd",
            "adaptive_multiplier",
        }

    def test_get_h2_snapshot_types_and_initial_values(self, cost_tracker):
        """All 3 H2 fields are float; initial values reflect default config."""
        snap = cost_tracker.get_h2_snapshot()
        # All values must be float (Rust H2BudgetState uses f64).
        assert isinstance(snap["daily_remaining_usd"], float)
        assert isinstance(snap["hard_cap_usd"], float)
        assert isinstance(snap["adaptive_multiplier"], float)
        # Default config: hard_cap = DEFAULT_DAILY_HARD_CAP_USD = 2.0;
        # multiplier = 1.0 (neutral) until adaptive recalculation runs.
        assert snap["hard_cap_usd"] == DEFAULT_DAILY_HARD_CAP_USD
        assert snap["adaptive_multiplier"] == 1.0
        # Fresh tracker → no spend → remaining ≈ hard_cap.
        assert snap["daily_remaining_usd"] > 0
        assert snap["daily_remaining_usd"] <= DEFAULT_DAILY_HARD_CAP_USD

    def test_get_h2_snapshot_after_claude_cost_decreases_remaining(self, cost_tracker, session):
        """Recording Claude cost reduces daily_remaining_usd."""
        before = cost_tracker.get_h2_snapshot()
        cost_tracker.record_claude_cost(
            session, input_tokens=1000, output_tokens=500, model_tier=MODEL_SONNET,
        )
        after = cost_tracker.get_h2_snapshot()
        # remaining_after = remaining_before - claude_cost
        assert after["daily_remaining_usd"] < before["daily_remaining_usd"]
        # hard_cap and multiplier are config — unchanged by recording.
        assert after["hard_cap_usd"] == before["hard_cap_usd"]
        assert after["adaptive_multiplier"] == before["adaptive_multiplier"]

    def test_get_h2_snapshot_pure_read_no_state_mutation(self, cost_tracker):
        """get_h2_snapshot must not mutate state (idempotent)."""
        snap_a = cost_tracker.get_h2_snapshot()
        snap_b = cost_tracker.get_h2_snapshot()
        assert snap_a == snap_b
        # Distinct dict objects (no aliasing).
        assert snap_a is not snap_b

    def test_get_h2_snapshot_remaining_clamped_at_zero(self, cost_tracker, session):
        """daily_remaining_usd clamped at >= 0 even when over budget.

        check_daily_budget() returns max(0.0, remaining); H2 snapshot wraps it.
        """
        # Exhaust budget with many expensive Opus calls.
        for _ in range(50):
            cost_tracker.record_claude_cost(
                session, input_tokens=200000, output_tokens=100000, model_tier=MODEL_OPUS,
            )
        snap = cost_tracker.get_h2_snapshot()
        assert snap["daily_remaining_usd"] >= 0.0

    def test_record_claude_cost_fires_h2_invalidate(self, cost_tracker, session):
        """record_claude_cost must fire ``invalidate_async("h2.budget_consumed")``.

        Patch the module-level ``_invalidate_h_state_async`` import in
        ``app.layer2_cost_recording`` to count calls (avoiding daemon thread
        spawn / IPC). Pattern mirrors test_h1_thought_gate.py:206-226.

        G3-08 Phase 4 Method A: import was relocated from
        ``app.layer2_cost_tracker`` to ``app.layer2_cost_recording`` when
        ``record_claude_cost`` / ``record_search_cost`` moved to the
        recording sibling (per RFC §7.3 patch path升級).

        Phase 3 Sub-task 3-3 update: ``record_claude_cost`` now also fires
        ``h5.claude_cost_recorded`` after the H2 hint (same call site, two
        hints — H2 + H5 are two lenses on the same Layer2CostTracker). This
        Sub-task 3-1 test asserts H2 hint is among the emitted reasons,
        without asserting exclusivity (the dedicated dual-hint test
        ``test_record_claude_cost_fires_h2_and_h5_invalidate`` covers the
        full Sub-task 3-3 contract).
        Phase 3 Sub-task 3-3 更新：``record_claude_cost`` 在 H2 提示後加發
        ``h5.claude_cost_recorded``（同呼叫點兩條提示 —— H2 + H5 是同一
        Layer2CostTracker 的兩個視角）。本 Sub-task 3-1 測試斷言 H2 提示
        在發出的 reasons 中，但不斷言獨佔（完整 Sub-task 3-3 dual-hint
        contract 由 ``test_record_claude_cost_fires_h2_and_h5_invalidate``
        測試涵蓋）。
        """
        # G3-08 Phase 4: patch path升級 from ``layer2_cost_tracker`` to
        # ``layer2_cost_recording`` after Method A split moved
        # ``record_claude_cost`` / ``record_search_cost`` (and their
        # ``_invalidate_h_state_async`` import) into the recording sibling
        # (per RFC §7.3).
        # G3-08 Phase 4：Method A 拆分後，``record_claude_cost`` /
        # ``record_search_cost``（連同 ``_invalidate_h_state_async`` import）
        # 移至 recording sibling，patch path 升級為
        # ``app.layer2_cost_recording`` (per RFC §7.3)。
        with patch("app.layer2_cost_recording._invalidate_h_state_async") as mock_inv:
            cost_tracker.record_claude_cost(
                session, input_tokens=1000, output_tokens=500, model_tier=MODEL_SONNET,
            )
            # Sub-task 3-3 added the h5 hint → call_count is now 2 (H2 + H5).
            # Sub-task 3-3 加 h5 提示 → call_count 現為 2（H2 + H5）。
            assert mock_inv.call_count == 2
            # H2 hint must be present (Sub-task 3-1 contract).
            # H2 提示必到（Sub-task 3-1 contract）。
            emitted_reasons = [c.args[0] for c in mock_inv.call_args_list]
            assert "h2.budget_consumed" in emitted_reasons

    def test_record_search_cost_does_not_fire_h2_invalidate(self, cost_tracker, session):
        """Sub-task 3-1 scope: only Claude cost fires h2 hint; search is 3-3 (H5).

        Phase 3 Sub-task 3-3 (this commit) updated record_search_cost to fire
        ``h5.search_cost_recorded`` — so the call_count is now 1, but the SOLE
        call is the H5 hint, NOT an H2 hint. Test asserts H2 is NOT in the
        emitted reasons (Sub-task 3-1 contract preserved).
        Phase 3 Sub-task 3-3（本 commit）更新 record_search_cost 發
        ``h5.search_cost_recorded`` 提示 —— call_count 現為 1，但唯一這
        條呼叫是 H5 提示而非 H2。測試斷言發出的 reasons 中**不含** H2
        （Sub-task 3-1 contract 保留）。
        """
        # G3-08 Phase 4: patch path升級 from ``layer2_cost_tracker`` to
        # ``layer2_cost_recording`` after Method A split moved
        # ``record_claude_cost`` / ``record_search_cost`` (and their
        # ``_invalidate_h_state_async`` import) into the recording sibling
        # (per RFC §7.3).
        # G3-08 Phase 4：Method A 拆分後，``record_claude_cost`` /
        # ``record_search_cost``（連同 ``_invalidate_h_state_async`` import）
        # 移至 recording sibling，patch path 升級為
        # ``app.layer2_cost_recording`` (per RFC §7.3)。
        with patch("app.layer2_cost_recording._invalidate_h_state_async") as mock_inv:
            cost_tracker.record_search_cost(session, "perplexity", 0.005)
            # Sub-task 3-3 added h5.search_cost_recorded → exactly 1 call now.
            assert mock_inv.call_count == 1
            # The single call must be the H5 hint, NOT an H2 hint
            # (Sub-task 3-1 scope contract).
            emitted_reasons = [c.args[0] for c in mock_inv.call_args_list]
            assert "h5.search_cost_recorded" in emitted_reasons
            assert all(not r.startswith("h2.") for r in emitted_reasons)

    # ── G3-08 Phase 3 Sub-task 3-3: H5 cost_logging integration tests ──
    # PA RFC `2026-04-26--g3_08_phase3_subtask_split.md` §6

    def test_get_h5_snapshot_schema(self, cost_tracker):
        """H5 snapshot returns 4 PA-spec fields (Rust H5CostStats parity)."""
        snap = cost_tracker.get_h5_snapshot()
        assert isinstance(snap, dict)
        # Schema parity with Rust H5CostStats (rust/openclaw_engine/src/
        # h_state_cache/types.rs:167-178): exactly 4 fields, no extra/missing.
        # Notably DROPS the ``roi_basis`` / ``roi_disclaimer`` metadata
        # markers that get_cost_edge_ratio() adds for the broader Cost
        # Summary API (principle 10 disclosure markers; not part of the
        # Rust hot-path schema).
        # Schema 對齊 Rust H5CostStats：恰 4 個欄位，丟棄 get_cost_edge_ratio()
        # 為更廣 Cost Summary API 加的 roi_basis/roi_disclaimer metadata 標記
        # （原則 10 揭露用，非 Rust hot-path schema 一部分）。
        assert set(snap.keys()) == {
            "ai_spend_7d_usd",
            "paper_pnl_7d_usd",
            "cost_edge_ratio",
            "data_days",
        }

    def test_get_h5_snapshot_types_and_initial_values(self, cost_tracker):
        """H5 fields have correct types; initial values reflect fresh tracker."""
        snap = cost_tracker.get_h5_snapshot()
        # ai_spend_7d_usd / paper_pnl_7d_usd are float (Rust f64).
        assert isinstance(snap["ai_spend_7d_usd"], float)
        assert isinstance(snap["paper_pnl_7d_usd"], float)
        # data_days is int (Rust u32).
        assert isinstance(snap["data_days"], int)
        # cost_edge_ratio is Optional[float] — None on fresh tracker
        # because data_days < ADAPTIVE_MIN_DAYS (= 3).
        # Rust mirror: Option<f64> via #[serde(default)].
        assert snap["cost_edge_ratio"] is None
        # Fresh tracker → no spend or PnL → both 0.0; data_days = 0.
        assert snap["ai_spend_7d_usd"] == 0.0
        assert snap["paper_pnl_7d_usd"] == 0.0
        assert snap["data_days"] == 0

    def test_get_h5_snapshot_pure_read_no_state_mutation(self, cost_tracker):
        """get_h5_snapshot must not mutate state (idempotent + distinct dicts)."""
        snap_a = cost_tracker.get_h5_snapshot()
        snap_b = cost_tracker.get_h5_snapshot()
        assert snap_a == snap_b
        # Distinct dict objects (no aliasing) — caller mutation can't leak.
        assert snap_a is not snap_b

    def test_get_h5_snapshot_drops_metadata_keys_from_get_cost_edge_ratio(self, cost_tracker):
        """H5 snapshot must NOT contain roi_basis or roi_disclaimer metadata.

        get_cost_edge_ratio() returns 6 keys (4 numeric + 2 metadata strings
        for principle 10 disclosure on the broader Cost Summary API).
        get_h5_snapshot() must filter to just the 4 numeric Rust H5CostStats
        fields — passing the metadata strings on the wire would force Rust
        to use ``serde(default)`` to silently drop them, which works but
        wastes wire bandwidth and obscures the schema contract.
        get_h5_snapshot() 必須過濾為 Rust H5CostStats 期望的 4 個數值欄位 ——
        wire 上帶 metadata 雖能由 Rust ``serde(default)`` 靜默丟，但浪費頻寬
        且模糊 schema contract。
        """
        snap = cost_tracker.get_h5_snapshot()
        assert "roi_basis" not in snap
        assert "roi_disclaimer" not in snap
        # Sanity: get_cost_edge_ratio() (the source) DOES include them.
        full = cost_tracker.get_cost_edge_ratio()
        assert "roi_basis" in full
        assert "roi_disclaimer" in full

    def test_get_h5_snapshot_after_recalculate_with_data(self, cost_tracker):
        """When recalculate_adaptive populates _adaptive, H5 snapshot reflects it."""
        # Manually inject 3+ days of synthetic data via _adaptive direct
        # mutation (mirrors what recalculate_adaptive() would compute from
        # a multi-day daily_spend record).
        # 直接注入 ≥3 天合成資料（鏡射 recalculate_adaptive() 從多天
        # daily_spend 紀錄會算出的結果）。
        cost_tracker._adaptive.ai_spend_7d_usd = 1.5
        cost_tracker._adaptive.paper_pnl_7d_usd = 3.0
        cost_tracker._adaptive.data_days = 5
        # NOTE: get_cost_edge_ratio uses live _adaptive (no recalc needed
        # to surface these values via the snapshot).
        snap = cost_tracker.get_h5_snapshot()
        assert snap["ai_spend_7d_usd"] == 1.5
        assert snap["paper_pnl_7d_usd"] == 3.0
        assert snap["data_days"] == 5
        # cost_edge_ratio = paper_pnl / ai_spend = 3.0 / 1.5 = 2.0
        # (data_days >= ADAPTIVE_MIN_DAYS=3 → ratio computable).
        assert snap["cost_edge_ratio"] == 2.0

    def test_get_h5_snapshot_cost_edge_ratio_none_when_data_insufficient(self, cost_tracker):
        """cost_edge_ratio is None when data_days < ADAPTIVE_MIN_DAYS (= 3)."""
        # Inject spend but only 2 days — below threshold.
        cost_tracker._adaptive.ai_spend_7d_usd = 0.5
        cost_tracker._adaptive.paper_pnl_7d_usd = 1.0
        cost_tracker._adaptive.data_days = 2
        snap = cost_tracker.get_h5_snapshot()
        # data_days < 3 → cost_edge_ratio collapses to None even if numbers
        # would otherwise compute. Rust Option<f64> accepts null over JSON.
        assert snap["cost_edge_ratio"] is None
        # But the raw spend / pnl / data_days fields remain visible.
        assert snap["ai_spend_7d_usd"] == 0.5
        assert snap["paper_pnl_7d_usd"] == 1.0
        assert snap["data_days"] == 2

    def test_record_claude_cost_fires_h2_and_h5_invalidate(self, cost_tracker, session):
        """record_claude_cost must fire BOTH h2 AND h5 invalidate hints (Sub-task 3-3).

        Sub-task 3-1 added the h2 hint; Sub-task 3-3 (this commit) adds the
        h5 hint to the same call site. The two hints share the same
        daemon-thread fire-and-forget infra — ordering is not guaranteed
        (call_args_list may be h2 first or h5 first depending on patch
        invocation order), but both must be present.
        Sub-task 3-1 加 h2 提示；Sub-task 3-3（本 commit）在同一呼叫點加
        h5 提示。兩條提示共用同套 daemon-thread fire-and-forget 基礎設施
        —— 順序不保證（h2 先或 h5 先取決於 patch 呼叫順序），但兩條都必到。
        """
        # G3-08 Phase 4: patch path升級 from ``layer2_cost_tracker`` to
        # ``layer2_cost_recording`` after Method A split moved
        # ``record_claude_cost`` / ``record_search_cost`` (and their
        # ``_invalidate_h_state_async`` import) into the recording sibling
        # (per RFC §7.3).
        # G3-08 Phase 4：Method A 拆分後，``record_claude_cost`` /
        # ``record_search_cost``（連同 ``_invalidate_h_state_async`` import）
        # 移至 recording sibling，patch path 升級為
        # ``app.layer2_cost_recording`` (per RFC §7.3)。
        with patch("app.layer2_cost_recording._invalidate_h_state_async") as mock_inv:
            cost_tracker.record_claude_cost(
                session, input_tokens=1000, output_tokens=500, model_tier=MODEL_SONNET,
            )
            # Exactly two invalidate calls per record_claude_cost.
            assert mock_inv.call_count == 2
            # Both reasons present (order-independent set check).
            emitted_reasons = {c.args[0] for c in mock_inv.call_args_list}
            assert emitted_reasons == {
                "h2.budget_consumed",
                "h5.claude_cost_recorded",
            }

    def test_record_search_cost_fires_h5_invalidate(self, cost_tracker, session):
        """record_search_cost must fire h5.search_cost_recorded (Sub-task 3-3 NEW).

        Search cost (Perplexity / WebPilot) feeds the same 7-day AI spend
        rollup that H5 exposes via cost_edge_ratio — so we hint H5 to
        refresh, separate from the h5.claude_cost_recorded hint emitted
        by record_claude_cost. Sub-task 3-1 deliberately did NOT add an
        h2 hint here (search cost was scoped to Sub-task 3-3 H5 contract).
        搜尋成本（Perplexity / WebPilot）灌入 H5 透過 cost_edge_ratio
        暴露的同一個 7d AI 花費彙總 —— 故發 H5 提示，與 record_claude_cost
        發的 h5.claude_cost_recorded 區別。Sub-task 3-1 刻意未在此加 H2
        提示（搜尋成本範圍限縮在 Sub-task 3-3 H5 contract）。
        """
        # G3-08 Phase 4: patch path升級 from ``layer2_cost_tracker`` to
        # ``layer2_cost_recording`` after Method A split moved
        # ``record_claude_cost`` / ``record_search_cost`` (and their
        # ``_invalidate_h_state_async`` import) into the recording sibling
        # (per RFC §7.3).
        # G3-08 Phase 4：Method A 拆分後，``record_claude_cost`` /
        # ``record_search_cost``（連同 ``_invalidate_h_state_async`` import）
        # 移至 recording sibling，patch path 升級為
        # ``app.layer2_cost_recording`` (per RFC §7.3)。
        with patch("app.layer2_cost_recording._invalidate_h_state_async") as mock_inv:
            cost_tracker.record_search_cost(session, "perplexity", 0.005)
            # Exactly one invalidate call (the H5 hint added in Sub-task 3-3).
            assert mock_inv.call_count == 1
            assert mock_inv.call_args.args[0] == "h5.search_cost_recorded"

    def test_record_session(self, cost_tracker, session):
        session.state = SESSION_STATE_COMPLETED
        cost_tracker.record_session(session)
        sessions = cost_tracker.get_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == session.session_id

    def test_get_session_by_id(self, cost_tracker, session):
        session.state = SESSION_STATE_COMPLETED
        cost_tracker.record_session(session)
        found = cost_tracker.get_session_by_id(session.session_id)
        assert found is not None
        assert found["session_id"] == session.session_id

    def test_get_session_by_id_not_found(self, cost_tracker):
        assert cost_tracker.get_session_by_id("nonexistent") is None

    def test_backfill_pnl_attribution(self, cost_tracker, session):
        session.state = SESSION_STATE_COMPLETED
        cost_tracker.record_session(session)
        result = cost_tracker.backfill_pnl_attribution(
            session.session_id, {"realized_pnl_usd": 5.0, "roi": 2.5},
        )
        assert result is True
        found = cost_tracker.get_session_by_id(session.session_id)
        assert found["pnl_attribution"]["roi"] == 2.5

    def test_backfill_pnl_not_found(self, cost_tracker):
        assert cost_tracker.backfill_pnl_attribution("fake", {}) is False

    def test_recalculate_adaptive_no_data(self, cost_tracker):
        state = cost_tracker.recalculate_adaptive()
        assert state.multiplier == 1.0
        assert state.roi_7d is None

    def test_get_cost_summary(self, cost_tracker):
        summary = cost_tracker.get_cost_summary()
        assert "today" in summary
        assert "budget" in summary
        assert "adaptive" in summary
        assert "cumulative" in summary
        assert summary["budget"]["daily_hard_cap_usd"] == DEFAULT_DAILY_HARD_CAP_USD

    def test_update_pricing(self, cost_tracker):
        pricing = cost_tracker.update_pricing({
            "models": {"haiku": {"input_per_mtok": 1.0, "last_verified_date": "2026-03-27"}},
        })
        assert pricing.models[MODEL_HAIKU].input_per_mtok == 1.0

    def test_update_config(self, cost_tracker):
        config = cost_tracker.update_config({"daily_hard_cap_usd": 20.0})
        assert config.daily_hard_cap_usd == 20.0

    def test_session_budget_check(self, cost_tracker, session):
        session.session_budget_usd = 1.0
        assert cost_tracker.check_session_budget(session) is True
        session.cost_usd = 1.5
        assert cost_tracker.check_session_budget(session) is False

    def test_max_session_history_trimmed(self, cost_tracker):
        for i in range(510):
            s = Layer2Session(state=SESSION_STATE_COMPLETED)
            cost_tracker.record_session(s)
        sessions = cost_tracker.get_sessions(limit=600)
        assert len(sessions) <= Layer2CostTracker.MAX_SESSION_HISTORY

    def test_file_permissions(self, tmp_cost_file):
        tracker = Layer2CostTracker(state_file=tmp_cost_file)
        st = os.stat(tmp_cost_file)
        # Check owner-only permissions (0o600)
        assert (st.st_mode & 0o777) == 0o600


# ═══════════════════════════════════════════════════════════════════════════════
# Tools Tests / 工具测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolSchemas:
    """Test tool schema definitions"""

    def test_all_schemas_present(self):
        names = {s["name"] for s in TOOL_SCHEMAS}
        assert TOOL_GET_MARKET_STATE in names
        assert TOOL_SUBMIT_RECOMMENDATION in names
        assert TOOL_WEB_SEARCH in names
        # G3-07 (2026-04-26): added query_onchain + check_derivatives → 10 tools.
        # G3-07（2026-04-26）：新增 query_onchain + check_derivatives → 10 個工具。
        assert len(TOOL_SCHEMAS) == 10

    def test_schemas_have_required_fields(self):
        for schema in TOOL_SCHEMAS:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema
            assert schema["input_schema"]["type"] == "object"


class TestToolExecutor:
    """Tests for ToolExecutor"""

    @pytest.fixture
    def executor(self):
        return ToolExecutor()

    def test_unknown_tool(self, executor):
        result = _run(
            executor.execute("nonexistent_tool", {})
        )
        parsed = json.loads(result)
        assert "error" in parsed

    def test_submit_recommendation(self, executor):
        result = _run(
            executor.execute(TOOL_SUBMIT_RECOMMENDATION, {
                "action": "buy",
                "symbol": "BTCUSDT",
                "confidence": 0.8,
                "edge_bps": 15.0,
                "reasoning": "test reasoning",
            })
        )
        parsed = json.loads(result)
        assert parsed["status"] == "recommendation_accepted"
        assert executor.recommendation is not None
        assert executor.recommendation.action == "buy"

    def test_record_insight(self, executor):
        result = _run(
            executor.execute("record_insight", {
                "category": "macro",
                "title": "Test Insight",
                "detail": "Test detail",
            })
        )
        parsed = json.loads(result)
        assert parsed["status"] == "insight_recorded"
        assert len(executor.insights) == 1

    def test_get_account_state_no_engine(self, executor):
        result = _run(
            executor.execute("get_account_state", {})
        )
        parsed = json.loads(result)
        assert "error" in parsed

    def test_get_market_state_no_files(self, executor):
        result = _run(
            executor.execute("get_market_state", {"symbol": "BTCUSDT"})
        )
        parsed = json.loads(result)
        assert parsed["symbol"] == "BTCUSDT"

    def test_web_search_empty_query(self, executor):
        result = _run(
            executor.execute("web_search", {"query": ""})
        )
        parsed = json.loads(result)
        assert "error" in parsed

    def test_fetch_url_empty(self, executor):
        result = _run(
            executor.execute("fetch_url", {"url": ""})
        )
        parsed = json.loads(result)
        assert "error" in parsed

    def test_get_recent_decisions_no_dir(self, executor):
        result = _run(
            executor.execute("get_recent_decisions", {"limit": 5})
        )
        parsed = json.loads(result)
        assert "decisions" in parsed or "error" in parsed

    def test_get_experience_no_state(self, executor):
        result = _run(
            executor.execute("get_experience", {"category": "all"})
        )
        parsed = json.loads(result)
        # Either returns records or an error/note about missing file
        assert isinstance(parsed, dict)


class TestSearchProviders:
    """Tests for search provider implementations"""

    def test_perplexity_not_available_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = PerplexitySearchProvider()
            # Without API key, should not be available
            os.environ.pop("PERPLEXITY_API_KEY", None)
            assert provider.is_available() is False

    def test_webpilot_availability(self):
        provider = WebPilotSearchProvider()
        # May or may not be available depending on environment
        result = provider.is_available()
        assert isinstance(result, bool)

    def test_search_with_degradation_all_unavailable(self):
        """When all providers are unavailable, should return error"""
        with patch("app.layer2_tools.SEARCH_PROVIDERS", {}):
            response = _run(
                search_with_degradation("test query", enabled_providers=["nonexistent"])
            )
            assert response.error is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Engine Tests / 引擎测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayer2Engine:
    """Tests for layer2_engine.py"""

    @pytest.fixture
    def engine_setup(self, tmp_cost_file):
        from app.layer2_engine import Layer2Engine
        tracker = Layer2CostTracker(state_file=tmp_cost_file)
        engine = Layer2Engine(cost_tracker=tracker)
        return engine, tracker

    def test_not_running_initially(self, engine_setup):
        engine, _ = engine_setup
        assert engine.is_running is False
        assert engine.get_current_session() is None

    def test_run_session_no_api_key(self, engine_setup):
        """Without ANTHROPIC_API_KEY, session should fail gracefully"""
        engine, _ = engine_setup
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            from app.layer2_engine import reset_anthropic_client
            reset_anthropic_client()

            session = _run(
                engine.run_session(trigger="manual", symbol="BTCUSDT")
            )
            assert session.state == SESSION_STATE_FAILED
            final_summary = session.final_summary.lower()
            assert (
                "not available" in final_summary
                or "not set" in final_summary
                or "不可用" in final_summary
            )

    def test_run_session_budget_exceeded(self, engine_setup):
        """When daily budget is 0, session should be blocked"""
        engine, tracker = engine_setup
        tracker.update_config({"daily_hard_cap_usd": 0.001})
        # Record enough cost to exceed
        s = Layer2Session()
        tracker.record_claude_cost(s, 1000000, 500000, MODEL_OPUS)

        session = _run(
            engine.run_session(trigger="manual")
        )
        assert session.state == SESSION_STATE_BUDGET_EXCEEDED

    def test_concurrent_session_blocked(self, engine_setup):
        """Second concurrent session should fail"""
        engine, _ = engine_setup
        # Py 3.12：改 new_event_loop + close 外層 try/finally，內層 try/finally 保留 lock release。
        # Py 3.12: wrap with new_event_loop+close (outer); keep lock release in inner try/finally.
        loop = asyncio.new_event_loop()
        try:
            # Acquire the asyncio lock to simulate a running session (P1-NEW-7: asyncio.Lock)
            loop.run_until_complete(engine._session_lock.acquire())
            try:
                session = loop.run_until_complete(
                    engine.run_session(trigger="manual")
                )
                assert session.state == SESSION_STATE_FAILED
                assert "already running" in session.final_summary.lower()
            finally:
                engine._session_lock.release()
        finally:
            loop.close()

    def test_l1_triage_no_client(self, engine_setup):
        """L1 triage without API key should return not worth investigating"""
        engine, _ = engine_setup
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            from app.layer2_engine import reset_anthropic_client
            reset_anthropic_client()

            result = _run(
                engine.l1_triage()
            )
            assert result.get("worth_investigating") is False

    def test_l1_triage_success(self, engine_setup):
        """L1 triage with mocked provider abstraction"""
        engine, _ = engine_setup
        provider_response = L2Response(
            text='{"worth_investigating": true, "reason": "test"}',
            input_tokens=100,
            output_tokens=50,
        )

        with patch.object(engine, "_provider_complete", new=AsyncMock(return_value=provider_response)):
            result = _run(
                engine.l1_triage({"test": "context"})
            )
        assert result.get("worth_investigating") is True

    def test_full_session_mocked(self, engine_setup):
        """Full session with mocked provider abstraction (end_turn immediately)"""
        engine, tracker = engine_setup
        provider_response = L2Response(
            text="Market analysis complete. No clear opportunity at this time.",
            stop_reason="end_turn",
            input_tokens=500,
            output_tokens=200,
        )
        fake_provider = MagicMock()
        fake_provider.append_assistant_message.side_effect = (
            lambda messages, response: messages.append({"role": "assistant", "content": response.text})
        )

        with (
            patch.object(engine, "_provider_complete", new=AsyncMock(return_value=provider_response)),
            patch("app.layer2_engine._pc.get_provider", return_value=fake_provider),
        ):
            session = _run(
                engine.run_session(trigger="manual", symbol="BTCUSDT")
            )
        assert session.state == SESSION_STATE_COMPLETED
        assert session.iterations == 1
        assert session.cost_usd > 0
        assert session.is_simulated is True

        # Session should be recorded
        sessions = tracker.get_sessions()
        assert len(sessions) == 1

    def test_session_with_tool_calls(self, engine_setup):
        """Session with tool calls then end_turn"""
        engine, tracker = engine_setup
        tool_response = L2Response(
            stop_reason="tool_use",
            tool_uses=[ToolUse(id="tool_1", name="get_market_state", input={"symbol": "BTCUSDT"})],
            input_tokens=500,
            output_tokens=100,
        )
        end_response = L2Response(
            text="Based on market analysis, holding is recommended.",
            stop_reason="end_turn",
            input_tokens=800,
            output_tokens=300,
        )
        fake_provider = MagicMock()
        fake_provider.append_assistant_message.side_effect = (
            lambda messages, response: messages.append({"role": "assistant", "content": response.text})
        )
        fake_provider.append_tool_results.side_effect = (
            lambda messages, results: messages.append({"role": "user", "content": json.dumps(results)})
        )

        with (
            patch.object(
                engine,
                "_provider_complete",
                new=AsyncMock(side_effect=[tool_response, end_response]),
            ),
            patch("app.layer2_engine._pc.get_provider", return_value=fake_provider),
        ):
            session = _run(
                engine.run_session(trigger="manual", symbol="BTCUSDT")
            )
        assert session.state == SESSION_STATE_COMPLETED
        assert session.iterations == 2
        assert len(session.tool_calls) == 1
        assert session.tool_calls[0].tool_name == "get_market_state"

    def test_model_upgrade_triage(self, engine_setup):
        """Test model upgrade triage logic"""
        engine, _ = engine_setup
        triage_response = L2Response(
            text='{"upgrade_to_opus": true, "reason": "major event"}',
            input_tokens=100,
            output_tokens=50,
        )

        session = Layer2Session()
        with patch.object(engine, "_provider_complete", new=AsyncMock(return_value=triage_response)):
            result = _run(
                engine._model_upgrade_triage(session, '{"results": [{"title": "Fed rate hike"}]}')
            )
        assert result is True
        assert session.upgrade_reason == "major event"


# ═══════════════════════════════════════════════════════════════════════════════
# Safety Invariant Tests / 安全不变量测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyInvariants:
    """Verify safety invariants are always maintained"""

    def test_session_always_simulated(self):
        s = Layer2Session()
        assert s.is_simulated is True
        assert s.data_category == "paper_simulated"
        d = s.to_dict()
        assert d["is_simulated"] is True

    def test_daily_hard_cap_cannot_be_bypassed(self, cost_tracker, session):
        """Even with high adaptive multiplier, daily cap holds"""
        cost_tracker.update_config({"daily_hard_cap_usd": 1.0})
        # Record costs up to cap
        for _ in range(20):
            cost_tracker.record_claude_cost(session, 100000, 50000, MODEL_OPUS)

        allowed, remaining = cost_tracker.check_daily_budget()
        assert not allowed or remaining <= 0

    def test_session_budget_enforced(self, cost_tracker):
        s = Layer2Session(session_budget_usd=0.01)
        s.cost_usd = 0.02
        assert not cost_tracker.check_session_budget(s)

    def test_recommendation_requires_all_fields(self):
        with pytest.raises(TypeError):
            Recommendation(action="buy")  # Missing required fields

    def test_tool_schemas_count(self):
        # G3-07 (2026-04-26): added query_onchain + check_derivatives → 10 tools.
        # G3-07（2026-04-26）：新增 query_onchain + check_derivatives → 10 個工具。
        assert len(TOOL_SCHEMAS) == 10


# ═══════════════════════════════════════════════════════════════════════════════
# Route Tests / 路由测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayer2Routes:
    """Tests for layer2_routes.py via direct function calls"""

    @pytest.fixture
    def setup_routes(self, tmp_cost_file):
        """Patch the cost tracker and engine for route testing"""
        tracker = Layer2CostTracker(state_file=tmp_cost_file)

        with patch("app.layer2_routes._get_cost_tracker", return_value=tracker):
            from app.layer2_engine import Layer2Engine
            engine = Layer2Engine(cost_tracker=tracker)
            with patch("app.layer2_routes._get_engine", return_value=engine):
                yield tracker, engine

    def test_get_cost_summary(self, setup_routes):
        from app.layer2_routes import get_cost_summary
        tracker, _ = setup_routes

        mock_actor = MagicMock()
        result = _run(
            get_cost_summary(actor=mock_actor)
        )
        assert result["action_result"] == "success"
        assert result["is_simulated"] is True
        assert "today" in result["data"]

    def test_get_pricing(self, setup_routes):
        from app.layer2_routes import get_pricing
        mock_actor = MagicMock()
        result = _run(
            get_pricing(actor=mock_actor)
        )
        assert result["action_result"] == "success"
        assert "models" in result["data"]

    def test_get_config(self, setup_routes):
        from app.layer2_routes import get_config
        mock_actor = MagicMock()
        result = _run(
            get_config(actor=mock_actor)
        )
        assert result["action_result"] == "success"
        assert "daily_hard_cap_usd" in result["data"]

    def test_get_sessions_empty(self, setup_routes):
        from app.layer2_routes import get_sessions
        mock_actor = MagicMock()
        result = _run(
            get_sessions(limit=20, offset=0, actor=mock_actor)
        )
        assert result["data"]["sessions"] == []

    def test_get_adaptive_budget(self, setup_routes):
        from app.layer2_routes import get_adaptive_budget
        mock_actor = MagicMock()
        result = _run(
            get_adaptive_budget(recalculate=False, actor=mock_actor)
        )
        assert result["action_result"] == "success"
        assert "multiplier" in result["data"]

    def test_get_adaptive_budget_recalculate(self, setup_routes):
        from app.layer2_routes import get_adaptive_budget
        mock_actor = MagicMock()
        result = _run(
            get_adaptive_budget(recalculate=True, actor=mock_actor)
        )
        assert result["action_result"] == "success"

    def test_update_config_empty(self, setup_routes):
        from app.layer2_routes import update_config, ConfigUpdateRequest
        mock_actor = MagicMock()
        req = ConfigUpdateRequest()
        result = _run(
            update_config(req=req, actor=mock_actor)
        )
        assert result["action_result"] == "blocked"

    def test_update_config_valid(self, setup_routes):
        from app.layer2_routes import update_config, ConfigUpdateRequest
        tracker, _ = setup_routes
        mock_actor = MagicMock()
        req = ConfigUpdateRequest(daily_hard_cap_usd=20.0)
        result = _run(
            update_config(req=req, actor=mock_actor)
        )
        assert result["action_result"] == "success"
        assert result["data"]["config"]["daily_hard_cap_usd"] == 20.0

    def test_update_pricing_empty(self, setup_routes):
        from app.layer2_routes import update_pricing, PricingUpdateRequest
        mock_actor = MagicMock()
        req = PricingUpdateRequest()
        result = _run(
            update_pricing(req=req, actor=mock_actor)
        )
        assert result["action_result"] == "blocked"

    def test_update_pricing_valid(self, setup_routes):
        from app.layer2_routes import update_pricing, PricingUpdateRequest
        mock_actor = MagicMock()
        req = PricingUpdateRequest(
            models={"haiku": {"input_per_mtok": 1.0, "last_verified_date": "2026-03-28"}},
        )
        result = _run(
            update_pricing(req=req, actor=mock_actor)
        )
        assert result["action_result"] == "success"

    def test_get_session_detail_not_found(self, setup_routes):
        from app.layer2_routes import get_session_detail
        mock_actor = MagicMock()
        with pytest.raises(Exception):  # HTTPException
            _run(
                get_session_detail(session_id="nonexistent", actor=mock_actor)
            )

    @patch("app.layer2_engine._get_anthropic_client")
    def test_trigger_session_budget_exceeded(self, mock_client_fn, setup_routes):
        from app.layer2_routes import trigger_l2_session, TriggerRequest
        tracker, engine = setup_routes
        tracker.update_config({"daily_hard_cap_usd": 0.001})
        # Exhaust budget
        s = Layer2Session()
        tracker.record_claude_cost(s, 1000000, 500000, MODEL_OPUS)

        mock_actor = MagicMock()
        mock_actor.roles = {"operator"}
        mock_actor.scopes = {"ai_budget:write"}
        mock_actor.actor_id = "test_op"
        background = MagicMock()
        req = TriggerRequest(symbol="BTCUSDT")
        result = _run(
            trigger_l2_session(req=req, background_tasks=background, actor=mock_actor)
        )
        assert result["action_result"] == "blocked"
        assert "daily_budget_exceeded" in result["reason_codes"]
