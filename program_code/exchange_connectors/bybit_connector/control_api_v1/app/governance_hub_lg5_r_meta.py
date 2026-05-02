"""
MODULE_NOTE
模組目的：LG-5 R-meta gate 純函式 helper（split sibling of
        ``governance_hub_live_candidate_review``）。封裝 R-meta 兩個 evaluator
        + 兩個閾值常數，讓主檔 LOC < 1500 硬上限（LG5-W3-FUP-2 Fix 2 IMPL-2-consumer
        實裝後主檔 ~1575；split 後主檔回 ≤ 1500）。

Module purpose: pure-function helpers for the LG-5 R-meta gate (split sibling
                of governance_hub_live_candidate_review). Houses both R-meta
                evaluators + their two thresholds so the parent file stays under
                the 1500 LOC hard cap (Fix 2 IMPL-2-consumer pushed the parent
                to ~1575; this split returns it to ≤ 1500).

Spec source / 規格來源：
    docs/CCAgentWorkSpace/PA/workspace/reports/
        2026-05-02--lg5_w3_fup2_fix2_r_meta_window_3d_amendment_rfc.md §3 / §9.3 / §10 Q3
    docs/CCAgentWorkSpace/PA/workspace/reports/
        2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md §3 R-meta

Backward compat / 向後相容：
    主檔 ``governance_hub_live_candidate_review`` re-export
    ``R_META_RATIO_FLOOR`` / ``_R_META_MIN_SAMPLE_PER_STRATEGY`` /
    ``evaluate_r_meta`` / ``evaluate_r_meta_sample_threshold`` 4 個 symbol，
    以維持既有 unit test 與 caller import 不變。
    Parent module re-exports the four R-meta symbols so existing imports and
    unit tests remain valid (no caller change required).

Hard boundary check (CLAUDE.md §四) / 硬邊界檢查：
    本檔僅含 pure-function evaluator + 兩個 read-only float/int 常數；
    0 IPC / 0 DB IO / 0 strategy params / 0 risk config / 0 live auth 觸碰。
"""

from __future__ import annotations

from typing import Literal, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常數 (RFC v2 §3 R-meta + Fix 2 IMPL-2 PA Q3)
# ═══════════════════════════════════════════════════════════════════════════════

# R-meta — per-strategy attribution chain (MF-M2)
R_META_RATIO_FLOOR: float = 0.50

# R-meta low-sample defer threshold (LG5-W3-FUP-2 Fix 2 IMPL-2-consumer, PA Q3).
# 3d window 樣本不足時不可信評估 attribution health → defer 區別於 ratio fail。
# 3d window low-sample → defer; distinct from ratio-fail "too_broken" reject.
# Source: producer payload "demo_attribution_sample_count_by_strategy" dict.
_R_META_MIN_SAMPLE_PER_STRATEGY: int = 10


# ═══════════════════════════════════════════════════════════════════════════════
# Internal numeric coercion helpers (mirror parent module fail-soft policy)
# 內部數字轉型輔助（鏡 parent module fail-soft 策略，避免雙向 import）
# ═══════════════════════════════════════════════════════════════════════════════

def _safe_float(value: object, default: float = 0.0) -> float:
    """Coerce to float fail-soft / 容錯轉 float。"""
    try:
        if value is None:
            return default
        import math
        result = float(value)  # type: ignore[arg-type]
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, default: int = 0) -> int:
    """Coerce to int fail-soft / 容錯轉 int。"""
    try:
        if value is None:
            return default
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ═══════════════════════════════════════════════════════════════════════════════
# R-meta evaluators (pure functions) / R-meta 純函式評估器
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_r_meta(
    candidate_strategy: str,
    attribution_dict: dict[str, float],
) -> tuple[Literal["pass", "fail", "unknown"], str, Optional[float]]:
    """R-meta per-strategy attribution chain quality (RFC §3 R-meta, MF-M2).
    R-meta per-strategy attribution chain 品質（RFC §3 R-meta, MF-M2）。

    Backward-compat 3-tuple surface；Fix 2 IMPL-2 PA Q3 sample-threshold
    pre-check 走獨立 ``evaluate_r_meta_sample_threshold``，caller 串接兩者。
    Backward-compat 3-tuple；Fix 2 sample 門檻由獨立 helper + caller 串接。
    """
    if not candidate_strategy:
        return "unknown", "R-meta: candidate has no strategy_name", None
    if candidate_strategy not in attribution_dict:
        return "unknown", f"R-meta: strategy {candidate_strategy} not in attribution dict", None
    ratio = _safe_float(attribution_dict[candidate_strategy])
    if ratio < R_META_RATIO_FLOOR:
        return "fail", f"R-meta: {candidate_strategy} ratio={ratio:.3f} < {R_META_RATIO_FLOOR}", ratio
    return "pass", f"R-meta: {candidate_strategy} ratio={ratio:.3f}", ratio


def build_r_meta_gate_verdict_kwargs(
    candidate_strategy: str,
    attribution_dict: dict[str, float],
    sample_count_dict: Optional[dict[str, int]],
    expected_net_bps_demo: float,
    decided_by_full: str,
) -> tuple[Optional[dict], Optional[int], str]:
    """Resolve R-meta gate verdict in one call (Fix 2 IMPL-2-consumer split).
    一次解 R-meta gate verdict（Fix 2 IMPL-2-consumer split，主檔 LOC 控）。

    Returns ``(verdict_kwargs, sample_n, r_meta_msg_for_pass)``:
      - verdict_kwargs is None → R-meta passed; caller proceeds (may use
        ``r_meta_msg_for_pass`` in the approve verdict's payload_snapshot).
      - verdict_kwargs is dict → caller does ``_make_verdict(**kwargs)`` +
        emit audit + return; gate triggered。
    Order: unknown → low_sample (Fix 2 PA Q3) → ratio fail (RFC §3 R-meta).
    順序：unknown → low_sample (Fix 2) → ratio fail (RFC §3 R-meta)。
    """
    r_meta_status, r_meta_msg, _ratio = evaluate_r_meta(candidate_strategy, attribution_dict)
    sample_below, sample_msg, sample_n = evaluate_r_meta_sample_threshold(
        candidate_strategy, sample_count_dict
    )
    common = dict(
        rule_failures=["R-meta"],
        expected_net_bps_demo=expected_net_bps_demo,
        decided_by=decided_by_full,
        attribution_sample_count=sample_n,
    )
    if r_meta_status == "unknown":
        return (dict(decision="defer", reason="defer_attribution_chain_strategy_unknown",
                     payload_snapshot={"r_meta_msg": r_meta_msg,
                                        "candidate_strategy": candidate_strategy},
                     **common), sample_n, r_meta_msg)
    if sample_below:
        # Fix 2 IMPL-2 PA Q3：sample 不足 defer，與 ratio fail 區分，等累積。
        return (dict(decision="defer", reason="defer_attribution_chain_low_sample",
                     payload_snapshot={"r_meta_sample_msg": sample_msg,
                                        "candidate_strategy": candidate_strategy,
                                        "min_sample_threshold": _R_META_MIN_SAMPLE_PER_STRATEGY},
                     **common), sample_n, r_meta_msg)
    if r_meta_status == "fail":
        # Per RFC §3 R-meta：用 defer decision 但 reason 用 reject_*（spec 文字）。
        return (dict(decision="defer", reason="reject_attribution_chain_too_broken",
                     payload_snapshot={"r_meta_msg": r_meta_msg},
                     **common), sample_n, r_meta_msg)
    return None, sample_n, r_meta_msg


def evaluate_r_meta_sample_threshold(
    candidate_strategy: str,
    sample_count_dict: Optional[dict[str, int]],
) -> tuple[bool, str, Optional[int]]:
    """R-meta low-sample pre-check (LG5-W3-FUP-2 Fix 2 IMPL-2-consumer, PA Q3).
    R-meta 樣本門檻 pre-check（LG5-W3-FUP-2 Fix 2 PA Q3）。

    Returns (below_threshold, msg, sample_n)。
    sample_count_dict 為 None（pre-Fix 2 payload 缺此 dict）→ 回 (False, ..., None)
    讓 caller 走原本 ratio path（preserves 既有 27 pending candidates 評估行為）。
    Strategy 在 ratio dict 但不在 sample dict → 同樣 skip（混合 backward-compat）。
    Below threshold（n < ``_R_META_MIN_SAMPLE_PER_STRATEGY``）→ 回 True 讓 caller
    emit ``defer_attribution_chain_low_sample``，與 ``reject_attribution_chain_too_broken``
    區分（前者 = 樣本不足；後者 = 樣本足但 ratio < floor）。
    """
    if not candidate_strategy or sample_count_dict is None:
        return False, "R-meta sample: skip (no sample dict)", None
    raw = sample_count_dict.get(candidate_strategy)
    if raw is None:
        return False, "R-meta sample: skip (strategy missing in sample dict)", None
    n = _safe_int(raw)
    if n < _R_META_MIN_SAMPLE_PER_STRATEGY:
        return True, (
            f"R-meta sample: {candidate_strategy} n={n} < "
            f"{_R_META_MIN_SAMPLE_PER_STRATEGY} (3d insufficient)"
        ), n
    return False, f"R-meta sample: {candidate_strategy} n={n} sufficient", n
