"""Wave 6 R20-P4-Q5 — MLDE rank/veto on replay candidates unit tests.

Wave 6 R20-P4-Q5 — MLDE 對 replay 候選的 rank/veto 單元測試。

MODULE_NOTE (EN):
    4 acceptance test cases for the new
    ``rank_and_veto_replay_candidates()`` API surface added to
    ``ml_training/mlde_shadow_advisor.py``. The tests cover:

      1. High score + no veto: candidate with positive edge, low cost,
         high confidence → ranked top, veto_reason=None.
      2. Low cost_edge_ratio → veto: candidate with cost_edge_ratio < 0.8
         → veto_reason='cost_edge_below_threshold'.
      3. DSR fail → veto: candidate with caller-supplied dsr_k < 0.95 →
         veto_reason='dsr_below_threshold' (when other gates pass).
      4. advisory_summary bilingual: every emitted summary contains both
         ASCII / English phrase + Chinese characters; satisfies V043
         ``chk_replay_mlde_veto_advisory_summary_nonempty`` CHECK.

    Tests use a lightweight ``StubCandidate`` shaped like P4-Q4
    ``ReplayCandidate`` so they don't import from the producing module
    (avoids hard-coupling Wave 6 Q4 with Wave 6 Q5 test fixtures).

MODULE_NOTE (中):
    新增 ``rank_and_veto_replay_candidates()`` API 表面的 4 個驗收 test。
    Test 涵蓋：

      1. 高分無 veto：正 edge / 低 cost / high confidence → top rank +
         veto_reason=None。
      2. 低 cost_edge_ratio → veto: cost_edge_ratio < 0.8 →
         veto_reason='cost_edge_below_threshold'。
      3. DSR 失敗 → veto: caller 提供 dsr_k < 0.95 →
         veto_reason='dsr_below_threshold'。
      4. advisory_summary 雙語：每個 summary 同時含 ASCII/English 短語 +
         中文字元；滿足 V043
         ``chk_replay_mlde_veto_advisory_summary_nonempty`` CHECK。

    Test 用輕量 ``StubCandidate``（形狀似 P4-Q4 ``ReplayCandidate``）以避
    免把 Wave 6 Q4 與 Q5 test fixture 硬耦合。

SPEC:
  - REF-20 V3 §11 P4 KPI (advisory only)
  - REF-20 V3 §12 #6 / #17 / #24
  - V043 chk_replay_mlde_veto_reason allowlist
  - V043 chk_replay_mlde_veto_advisory_summary_nonempty
Workplan:
  docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 Wave 6 R20-P4-Q5
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pytest

# conftest.py at program_code/ml_training/tests/ adds sys.path entries.
# conftest.py 在 program_code/ml_training/tests/ 設置 sys.path。
from ml_training.mlde_shadow_advisor import (
    COST_EDGE_RATIO_GATE,
    DSR_GATE,
    PBO_GATE,
    RankAndVetoGateInputs,
    RankedCandidate,
    rank_and_veto_replay_candidates,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test fixture: lightweight stub mimicking P4-Q4 ReplayCandidate shape.
# Test fixture：輕量 stub 模擬 P4-Q4 ReplayCandidate 形狀。
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StubCandidate:
    """Stub candidate shaped like P4-Q4 ReplayCandidate (5 attributes).

    Stub candidate 形狀似 P4-Q4 ReplayCandidate (5 個必要屬性)。
    """

    candidate_id: str
    strategy_params: dict[str, Any]
    expected_edge_bps: float
    expected_cost_bps: float
    confidence: str  # 'high' | 'medium' | 'low' | 'none'


# Match Chinese codepoints (CJK Unified Ideographs Basic block).
# 配對中文 codepoint (CJK Unified Ideographs Basic block)。
_CJK_PATTERN = re.compile(r"[一-鿿]")
# Match basic ASCII Latin letters.
# 配對基本 ASCII Latin 字母。
_ASCII_PATTERN = re.compile(r"[A-Za-z]")


def _has_chinese(text: str) -> bool:
    return bool(_CJK_PATTERN.search(text))


def _has_english(text: str) -> bool:
    return bool(_ASCII_PATTERN.search(text))


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: high score + no veto.
# Test 1：高分無 veto。
# ─────────────────────────────────────────────────────────────────────────────


def test_high_score_no_veto():
    """Positive edge + low cost + high confidence → top rank, no veto.

    正 edge + 低 cost + high confidence → 排名第一 + 無 veto。
    """
    candidates = [
        StubCandidate(
            candidate_id="c-high",
            strategy_params={"grid_spacing_bps": 12.5},
            expected_edge_bps=10.0,  # large positive edge
            expected_cost_bps=1.5,  # tiny cost; cost_edge_ratio = 10/1.5 ≈ 6.67 > 0.8
            confidence="high",
        ),
        StubCandidate(
            candidate_id="c-mediocre",
            strategy_params={"grid_spacing_bps": 11.0},
            expected_edge_bps=2.0,
            expected_cost_bps=1.0,  # cost_edge_ratio = 2.0 > 0.8
            confidence="medium",
        ),
    ]
    out = rank_and_veto_replay_candidates(candidates)
    assert len(out) == 2
    # First entry is the best by score.
    # 第一名為最高分。
    assert out[0].rank == 1
    assert out[0].candidate_id == "c-high"
    assert out[0].veto_reason is None
    # Score positive (edge - cost) * confidence_multiplier.
    # 分數為正 (edge - cost) * 信心 multiplier。
    assert out[0].ml_score > 0.0
    # Second entry second.
    assert out[1].rank == 2
    assert out[1].candidate_id == "c-mediocre"
    # All RankedCandidate are dataclass instances.
    # 所有 RankedCandidate 皆為 dataclass。
    assert all(isinstance(r, RankedCandidate) for r in out)


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: low cost_edge_ratio → veto.
# Test 2：低 cost_edge_ratio → veto。
# ─────────────────────────────────────────────────────────────────────────────


def test_low_cost_edge_ratio_triggers_veto():
    """cost_edge_ratio < 0.8 → veto_reason='cost_edge_below_threshold'.

    cost_edge_ratio < 0.8 → veto_reason='cost_edge_below_threshold'。
    """
    # Candidate where cost dominates edge:
    # |edge|=2.0, cost=10.0 → cost_edge_ratio = 2.0/10.0 = 0.2 < 0.8.
    # 設計：edge 小、cost 大 → cost_edge_ratio 0.2 < 0.8。
    candidate = StubCandidate(
        candidate_id="c-expensive",
        strategy_params={"grid_spacing_bps": 13.0},
        expected_edge_bps=2.0,
        expected_cost_bps=10.0,
        confidence="high",
    )
    out = rank_and_veto_replay_candidates([candidate])
    assert len(out) == 1
    assert out[0].veto_reason == "cost_edge_below_threshold"
    # Bilingual summary mentions threshold.
    # 雙語 summary 提及閾值。
    assert str(COST_EDGE_RATIO_GATE) in out[0].advisory_summary
    assert "cost-edge" in out[0].advisory_summary or "成本邊際" in (
        out[0].advisory_summary
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: DSR fail → veto.
# Test 3：DSR 失敗 → veto。
# ─────────────────────────────────────────────────────────────────────────────


def test_dsr_below_threshold_triggers_veto():
    """dsr_k < 0.95 → veto_reason='dsr_below_threshold' (assumes other gates pass).

    dsr_k < 0.95 → veto_reason='dsr_below_threshold' (其他 gate 假設通過)。
    """
    # Candidate that would pass cost_edge gate but fails DSR.
    # |edge|=10, cost=1 → cost_edge_ratio = 10 > 0.8. DSR set 0.50 < 0.95.
    # 候選通過 cost_edge gate 但 DSR fail。
    candidate = StubCandidate(
        candidate_id="c-low-dsr",
        strategy_params={"min_hold_seconds": 95.0},
        expected_edge_bps=10.0,
        expected_cost_bps=1.0,
        confidence="high",
    )
    gate_inputs = RankAndVetoGateInputs(dsr_k=0.50)  # below DSR_GATE 0.95
    out = rank_and_veto_replay_candidates(
        [candidate], gate_inputs=gate_inputs
    )
    assert len(out) == 1
    assert out[0].veto_reason == "dsr_below_threshold"
    # Summary mentions threshold value (0.95) somewhere.
    # Summary 提及閾值 0.95。
    assert str(DSR_GATE) in out[0].advisory_summary
    # Sanity: PBO gate also covered when input set.
    # 一致性：PBO gate input 設時也覆蓋。
    pbo_inputs = RankAndVetoGateInputs(pbo=0.75)  # above PBO_GATE 0.5
    pbo_out = rank_and_veto_replay_candidates(
        [candidate], gate_inputs=pbo_inputs
    )
    # cost_edge OK; pbo > 0.5 → veto.
    # cost_edge OK；pbo > 0.5 → veto。
    assert pbo_out[0].veto_reason == "pbo_above_threshold"
    assert str(PBO_GATE) in pbo_out[0].advisory_summary


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: advisory_summary bilingual.
# Test 4：advisory_summary 雙語。
# ─────────────────────────────────────────────────────────────────────────────


def test_advisory_summary_bilingual():
    """Every advisory_summary contains BOTH Chinese codepoints AND English ASCII.

    每個 advisory_summary 同時含中文 codepoint 與 ASCII 英文。

    V043 chk_replay_mlde_veto_advisory_summary_nonempty CHECK demands
    non-empty body; the bilingual contract is enforced at Python level so
    the operator GUI can render both halves regardless of locale.

    V043 chk_replay_mlde_veto_advisory_summary_nonempty CHECK 要求非空；
    雙語契約在 Python 層強制，讓 operator GUI 不論 locale 都可呈現兩段。
    """
    # Mix of vetoed + non-vetoed candidates exercising 5 reason codes +
    # the no-veto path.
    # 混合 veto 與無 veto 候選，覆蓋 5 reason 與通過路徑。
    candidates = [
        # No veto / 無 veto.
        StubCandidate(
            candidate_id="c-pass",
            strategy_params={"k": 1.0},
            expected_edge_bps=5.0,
            expected_cost_bps=1.0,
            confidence="high",
        ),
        # cost_edge_below_threshold.
        StubCandidate(
            candidate_id="c-cost",
            strategy_params={"k": 1.0},
            expected_edge_bps=1.0,
            expected_cost_bps=10.0,
            confidence="high",
        ),
        # low_confidence_replay (confidence='none').
        StubCandidate(
            candidate_id="c-none",
            strategy_params={"k": 1.0},
            expected_edge_bps=5.0,
            expected_cost_bps=1.0,
            confidence="none",
        ),
        # unknown_strategy_axis (empty params).
        StubCandidate(
            candidate_id="c-empty",
            strategy_params={},
            expected_edge_bps=5.0,
            expected_cost_bps=1.0,
            confidence="high",
        ),
    ]
    # Add gate_inputs to exercise DSR + PBO summaries too.
    # 加 gate_inputs 同時覆蓋 DSR + PBO summary。
    gate_inputs = RankAndVetoGateInputs(pbo=0.6, dsr_k=0.80)
    out = rank_and_veto_replay_candidates(
        candidates, gate_inputs=gate_inputs
    )
    assert len(out) == 4
    for ranked in out:
        # Non-empty satisfies V043 CHECK.
        # 非空滿足 V043 CHECK。
        assert ranked.advisory_summary
        assert len(ranked.advisory_summary) > 0
        # Bilingual: both Chinese + English present.
        # 雙語：中文 + 英文皆在。
        assert _has_chinese(ranked.advisory_summary), (
            f"summary missing Chinese: {ranked.advisory_summary!r}"
        )
        assert _has_english(ranked.advisory_summary), (
            f"summary missing English: {ranked.advisory_summary!r}"
        )
        # Rank prefix present.
        # rank 前綴可見。
        assert "排名" in ranked.advisory_summary
        assert "rank" in ranked.advisory_summary


# ─────────────────────────────────────────────────────────────────────────────
# Bonus: empty input → empty output (defensive contract).
# Bonus：空輸入 → 空輸出 (防禦性契約)。
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_input_returns_empty_list():
    """Empty candidate list → empty RankedCandidate list (no crash).

    空候選 list → 空 RankedCandidate list (不 crash)。
    """
    assert rank_and_veto_replay_candidates([]) == []
    assert rank_and_veto_replay_candidates(None or []) == []


def test_missing_candidate_id_raises():
    """Defensive: candidate without ``candidate_id`` raises ValueError.

    防禦性：候選缺 ``candidate_id`` raises ValueError。
    """

    class BadCandidate:
        strategy_params: dict[str, Any] = {}
        expected_edge_bps = 1.0
        expected_cost_bps = 1.0
        confidence = "high"

    with pytest.raises(ValueError, match="candidate_id"):
        rank_and_veto_replay_candidates([BadCandidate()])
