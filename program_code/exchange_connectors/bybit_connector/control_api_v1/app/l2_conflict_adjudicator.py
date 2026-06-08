"""
MODULE_NOTE
模塊用途：
  L2 Advisory Mesh 衝突裁決（PA P2 設計 §G / §F.2）。兩類衝突都「朝確定性/更保守側」
  解決（root principle 4、6），**永不由 model 裁決**。這是一個 fixed precedence table，
  設計成 CC 可 grep 確認「無 model 輸出裁決兩個 proposal」（stress-test 6）。

  兩類衝突：
    (a) L2 advisory vs deterministic governor/gate：strict `deterministic > advisory`
        （gate reject 永勝 L2 recommend；L2 只能 pull tighter，永不 relax）。
    (b) cross-capability：fixed precedence（contract > expand；同向取更嚴；正交各走各 gate；
        無法解 → escalate 人工 inbox，NO auto-apply，fail-closed）。

主要類/函數：
  - PRECEDENCE：literal dict（direction → rank）；contract 勝 expand 是字面比較。
  - adjudicate_vs_gate(gate_verdict, l2_recommendation):gate reject 永勝。
  - adjudicate_cross_capability(prop_a, prop_b):fixed precedence；unresolved → escalate。

依賴：
  - l2_capability_registry.LANE_DIRECTION（direction 來源 single source；不複製方向定義）。

硬邊界：
  - 裁決函數內**零 model 呼叫**（無 run_session / 無 LLM client）——CC stress-test 6 grep target。
  - gate reject > L2 recommend 與 contract > expand 都是「字面比較」，非 model 判斷。
  - unresolved → NO auto-apply（escalate 人工 + provenance），fail-closed。
  - 純函數模塊（stateless）：無 mutable singleton（singleton-registry §4.1 note 即可）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from .l2_capability_registry import LANE_DIRECTION

logger = logging.getLogger("l2_conflict_adjudicator")

AdjudicationOutcome = Literal["a_wins", "b_wins", "both_proceed", "escalate"]


# ═══════════════════════════════════════════════════════════════════════════════
# Fixed precedence table（literal — CC grep 確認非 model call）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 為什麼是 literal dict：CC stress-test 6 要驗「無 model 裁決」。把方向優先級寫成
# 字面 rank dict，裁決就是「查表 + 比 int」，結構上不可能是 model 判斷。
# rank 越大越優先。contract（收緊/防禦）> expand（放鬆/晉升）：regime-risk 說「現在收緊」
# 勝過 ML 說「晉升 X」→ 收緊勝，晉升 deferred+logged（非 killed）。neutral 不參與方向衝突。
PRECEDENCE: dict[str, int] = {
    "contract": 2,  # 收緊/防禦：survival-first，永遠優先
    "neutral": 1,  # 研究/告警：不與方向衝突
    "expand": 0,  # 放鬆/晉升：最低優先（被 contract 壓過）
}


@dataclass
class Proposal:
    """一個 capability 提案（裁決輸入）。

    target：衝突判定的目標鍵（同 target 才比較；正交 target 不衝突）。
    lane：→ LANE_DIRECTION → direction（contract/expand/neutral）。
    magnitude：同向衝突時取「更嚴」用（語義由 lane 決定：contract 越大越嚴）。
    """

    capability_id: str
    lane: str
    target: str
    magnitude: float = 0.0


def _direction_of(lane: str) -> str:
    """lane → direction（single source = LANE_DIRECTION；未知 lane 視 neutral 保守）。"""
    return LANE_DIRECTION.get(lane, "neutral")


def adjudicate_vs_gate(
    *, gate_verdict: str, l2_recommendation: str
) -> AdjudicationOutcome:
    """(a) L2 advisory vs deterministic gate：gate reject 永勝 L2 recommend。

    為什麼 fail-closed：Alpha Evidence Governance（CLAUDE.md）—— model 永不 override 失敗的
    量化 gate。這是「字面比較」（gate_verdict=="reject" → gate 勝），**非** model 判斷。

    回傳 a_wins = gate 勝（proposal 不放行）；b_wins = gate 未 reject，L2 recommend 可續走
    其自身 gate（非「直接 apply」）。
    """
    # gate reject 永勝（deterministic > advisory）。
    if str(gate_verdict).lower() in ("reject", "fail", "block"):
        return "a_wins"  # gate（a）勝
    return "b_wins"  # gate 未否決，L2 recommend 續走自身管線


def adjudicate_cross_capability(
    prop_a: Proposal, prop_b: Proposal
) -> tuple[AdjudicationOutcome, str]:
    """(b) cross-capability 衝突：fixed precedence，無 model 裁決。回 (outcome, reason)。

    規則（design §G.1）：
      1. 正交 target（不同 target）→ both_proceed（各走各 gate，無衝突）。
      2. 方向優先：contract 勝 expand（同 target；查 PRECEDENCE 字面比較）。
      3. 同向同 direction、不同 magnitude → 取更嚴者（contract: magnitude 大者勝）。
      4. 無法解（同 rank 同 magnitude，table 不覆蓋）→ escalate（NO auto-apply，fail-closed）。
    """
    # 1) 正交 target → 各自 proceed（無衝突）。
    if prop_a.target != prop_b.target:
        return "both_proceed", "orthogonal_targets"

    dir_a = _direction_of(prop_a.lane)
    dir_b = _direction_of(prop_b.lane)
    rank_a = PRECEDENCE.get(dir_a, 1)
    rank_b = PRECEDENCE.get(dir_b, 1)

    # 2) 方向優先：rank 高者勝（contract > expand 是字面比較）。
    if rank_a != rank_b:
        if rank_a > rank_b:
            return "a_wins", f"direction_precedence:{dir_a}>{dir_b}"
        return "b_wins", f"direction_precedence:{dir_b}>{dir_a}"

    # 3) 同 direction、不同 magnitude → 取更嚴（contract: magnitude 大者；其餘亦取大者保守）。
    if prop_a.magnitude != prop_b.magnitude:
        if prop_a.magnitude > prop_b.magnitude:
            return "a_wins", "stricter_magnitude"
        return "b_wins", "stricter_magnitude"

    # 4) table 不覆蓋（同 rank 同 magnitude）→ escalate（fail-closed，NO auto-apply）。
    return "escalate", "unresolvable_escalate_to_human"


__all__ = [
    "AdjudicationOutcome",
    "PRECEDENCE",
    "Proposal",
    "adjudicate_vs_gate",
    "adjudicate_cross_capability",
]
