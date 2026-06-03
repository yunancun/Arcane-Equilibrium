"""AEG-S2 breadth ladder 純函數核心 — per-tier 結果 → ladder rows + monotonicity + digest。

MODULE_NOTE:
  模塊用途：breadth ladder 的**純函數**核心。輸入 ``{tier_name: TierResult}`` + tier
    metadata，輸出 ladder rows（每 tier 一行，凍結欄序）+ summary（monotonicity 判定）
    + ``ladder_id`` digest。**0 DB / 0 候選耦合**，全 synthetic 可測（mirror FND-2
    builder 純函數哲學）。
  主要函數：
    - ``build_ladder``：核心（rows + summary + ladder_id），回 ``(rows, summary)``。
    - ``compute_ladder_id`` / ``ordered_tier_digest``：determinism digest。
    - ``classify_monotonicity``：net edge 隨 breadth 加寬存活 / 衰減 / 塌縮判定。
  硬邊界（算法權威 = PA §4 Step 3 + §5；E2 must-check #2/#3）：
    - **breadth ≠ n_independent**：``breadth_symbol_count`` 隨 tier 加寬，但
      ``n_independent`` 由候選評估器以 time-cluster-bound 方式給定，本層**原樣記錄不
      放大**（不對 n_independent 做任何 symbol-scaled 運算）。``n_independent_invariant_
      to_breadth`` 自證 nested tier 間 n_independent 不因 symbol 增而漲。
    - **monotonicity 主軸只用 nested tier**（core25/top_liq/full）；scanner_active_asof
      overlap-only 單獨報，不入 monotonicity 序。
    - **top_liquidity 降級**：tier_quality / tier_rank_pit_mode / excluded_from_promotion
      由 universe_artifact 層決定並傳入；本層只記錄 + 在 monotonicity 主軸排除
      promotion-excluded tier（diagnostic-only，OQ-B3 R-1）。
    - **不算 final_label**（那是 (c) 的 5-axis 合成 + QC 門檻）；本層只供 ``verdict_hint``
      （advisory）+ 機械化 monotonicity 證據。
    - determinism：row 固定排序（by monotonicity_rank 再 tier 名），float ``%.12g``
      固定格式化，同 universe + 同 candidate → 同 ladder_id（T-determinism）。
  依賴：標準庫（hashlib）+ 本 package tiers + evaluator。import-time 零 DB 依賴。
"""

from __future__ import annotations

import hashlib
from typing import Optional

from . import BREADTH_LADDER_VERSION, N_INDEPENDENT_PROMOTION_FLOOR
from . import tiers as tiers_mod
from .evaluator import TierResult

# breadth_ladder.csv/.parquet 凍結欄序（S0 §1.3 + (c) breadth_cohort 軸對齊；PA §5）。
# 任何欄序變更須升 LADDER_SCHEMA_VERSION（影響 ordered_tier_digest → ladder_id）。
LADDER_COLUMNS = (
    "run_id", "ladder_id", "candidate_id", "breadth_ladder_version",
    "asof_utc", "window_start_utc", "window_end_utc", "fnd2_universe_id", "fnd2_run_id",
    "breadth_cohort",                         # = tier 名（對齊 (c) verdict_matrix）
    "breadth_symbol_count", "seen_delisted_count",
    "tier_quality",                           # 'ok' / 'liquidity_source_not_pit' / 'overlap_only'
    "tier_rank_pit_mode",                     # 'n/a' / 'asof_constant'（top_liquidity caveat）
    "gross_bps", "cost_bps", "net_bps", "net_to_cost_ratio",
    "is_sharpe", "oos_sharpe",
    "n_independent", "sample_unit", "t_stat_hac",
    "psr_0", "dsr_k", "pbo", "k_trials",
    "long_leg_net_bps", "short_leg_net_bps",
    "pit_mask_source", "leak_free_signal",
    "monotonicity_rank",                      # nested tier 在 breadth 軸的序（scanner=None）
    "excluded_from_promotion", "exclusion_reason",
)

# digest 用的 row 欄子集（穩定、語義關鍵欄；排除 run_id/ladder_id 自身避免循環）。
# 為什麼不含 run_id：ladder_id 須對「同 universe + 同 candidate + 同 storage」穩定，與
# run_id 無關。為什麼不含 ladder_id：它是 digest 的輸出。為什麼不含 asof/window：那些
# 已在 candidate/universe 層決定，且由 caller 餵 fnd2_universe_id（已含窗）進 digest。
_DIGEST_COLUMNS = (
    "breadth_cohort", "breadth_symbol_count", "seen_delisted_count",
    "tier_quality", "tier_rank_pit_mode",
    "gross_bps", "cost_bps", "net_bps", "net_to_cost_ratio",
    "is_sharpe", "oos_sharpe",
    "n_independent", "sample_unit", "t_stat_hac",
    "psr_0", "dsr_k", "pbo", "k_trials",
    "long_leg_net_bps", "short_leg_net_bps",
    "pit_mask_source", "leak_free_signal",
    "monotonicity_rank", "excluded_from_promotion", "exclusion_reason",
)


def _fmt_num(x: Optional[float]) -> Optional[str]:
    """數值固定格式化（determinism，避免平台浮點漂移）。None 保留 None。

    為什麼 %.12g：net_bps / t_stat 等浮點跨平台 repr 可能差異；%.12g 給足精度又消除
    尾差，進 digest 穩定（mirror FND-2 builder._fmt_num；R-4 determinism）。
    """
    if x is None:
        return None
    return "%.12g" % float(x)


def _canonical_cell(value) -> str:
    """digest 用的 cell canonical 字串化（穩定、跨平台；mirror FND-2）。"""
    if value is None:
        return "\x00NULL"
    if isinstance(value, bool):
        return "T" if value else "F"
    if isinstance(value, float):
        return _fmt_num(value) or "\x00NULL"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical_cell(v) for v in value) + "]"
    return str(value)


def _tier_meta(tier_name: str) -> tiers_mod.BreadthTier:
    return tiers_mod.tier_by_name(tier_name)


def _build_row(
    tr: TierResult,
    *,
    run_id: str,
    candidate_id: str,
    asof_utc: str,
    window_start_utc: str,
    window_end_utc: str,
    fnd2_universe_id: str,
    fnd2_run_id: str,
    tier_quality: str,
    tier_rank_pit_mode: str,
    excluded_from_promotion: bool,
    exclusion_reason: Optional[str],
) -> dict:
    """單一 TierResult → ladder row（LADDER_COLUMNS 全欄）。ladder_id 末段回填。"""
    meta = _tier_meta(tr.tier)
    return {
        "run_id": run_id,
        "ladder_id": "",  # build_ladder 末段回填
        "candidate_id": candidate_id,
        "breadth_ladder_version": BREADTH_LADDER_VERSION,
        "asof_utc": asof_utc,
        "window_start_utc": window_start_utc,
        "window_end_utc": window_end_utc,
        "fnd2_universe_id": fnd2_universe_id,
        "fnd2_run_id": fnd2_run_id,
        "breadth_cohort": tr.tier,
        "breadth_symbol_count": tr.breadth_symbol_count,
        "seen_delisted_count": tr.seen_delisted_count,
        "tier_quality": tier_quality,
        "tier_rank_pit_mode": tier_rank_pit_mode,
        "gross_bps": _fmt_num(tr.gross_bps),
        "cost_bps": _fmt_num(tr.cost_bps),
        "net_bps": _fmt_num(tr.net_bps),
        "net_to_cost_ratio": _fmt_num(tr.net_to_cost_ratio),
        "is_sharpe": _fmt_num(tr.is_sharpe),
        "oos_sharpe": _fmt_num(tr.oos_sharpe),
        "n_independent": tr.n_independent,
        "sample_unit": tr.sample_unit,
        "t_stat_hac": _fmt_num(tr.t_stat_hac),
        "psr_0": _fmt_num(tr.psr_0),
        "dsr_k": _fmt_num(tr.dsr_k),
        "pbo": _fmt_num(tr.pbo),
        "k_trials": tr.k_trials,
        "long_leg_net_bps": _fmt_num(tr.long_leg_net_bps),
        "short_leg_net_bps": _fmt_num(tr.short_leg_net_bps),
        "pit_mask_source": tr.pit_mask_source,
        "leak_free_signal": bool(tr.leak_free_signal),
        "monotonicity_rank": meta.monotonicity_rank,
        "excluded_from_promotion": bool(excluded_from_promotion),
        "exclusion_reason": exclusion_reason,
    }


def classify_monotonicity(nested_rows: list) -> dict:
    """net edge 隨 breadth 加寬的 monotonicity 判定（純函數，PA §5）。

    nested_rows：只含 nested tier（core25/top_liq/full）的 ladder row，**已按
    monotonicity_rank 升序**，且**已排除 promotion-excluded tier**（如 top_liquidity
    diagnostic-only，OQ-B3）→ 主軸通常是 core25 → full。

    判定（PA §5）：
      - survives：net_bps 在 core25→full 不顯著衰減，且最寬 tier n_independent>=30 +
        net_bps>0 → verdict_hint='breadth_real'。
      - collapses_to_narrow：net_bps 在最寬 tier 顯著 < 最窄 → narrow_only_edge=true
        → 'breadth-limited'（S0 §2.8 low_breadth overlay）。
      - insufficient_n_independent：任一 nested tier n_independent<30 → 整 ladder
        verdict_hint='insufficient_n_independent'（cost-wall 8-rebalance 牆機械化）。
    """
    # 取 net_bps 與 n_independent（row 值是格式化字串/數值，統一轉 float/int）。
    pts = []
    for r in nested_rows:
        net = _to_float(r.get("net_bps"))
        n_ind = _to_int(r.get("n_independent"))
        pts.append((r.get("breadth_cohort"), r.get("monotonicity_rank"), net, n_ind))

    per_tier_net = {c: net for c, _rank, net, _n in pts}
    per_tier_n = {c: n for c, _rank, _net, n in pts}

    if len(pts) < 2:
        return {
            "net_bps_monotonic_in_breadth": False,
            "net_bps_trend": "inconclusive",
            "narrow_only_edge": False,
            "n_independent_invariant_to_breadth": _n_independent_invariant(per_tier_n),
            "binding_ceiling": "time_period_count",
            "per_tier_net_bps": per_tier_net,
            "per_tier_n_independent": per_tier_n,
            "verdict_hint": "inconclusive",
            "reason": "fewer_than_2_nested_promotion_eligible_tiers",
        }

    nets = [net for _c, _rank, net, _n in pts]
    n_inds = [n for _c, _rank, _net, n in pts]
    narrowest_net = nets[0]
    widest_net = nets[-1]

    # gate 3：任一 nested tier n_independent < 30 → sample-bound（cost-wall 牆）。
    if any(n < N_INDEPENDENT_PROMOTION_FLOOR for n in n_inds):
        return {
            "net_bps_monotonic_in_breadth": False,
            "net_bps_trend": "insufficient_n_independent",
            "narrow_only_edge": False,
            "n_independent_invariant_to_breadth": _n_independent_invariant(per_tier_n),
            "binding_ceiling": "time_period_count",
            "per_tier_net_bps": per_tier_net,
            "per_tier_n_independent": per_tier_n,
            "verdict_hint": "insufficient_n_independent",
            "reason": (
                f"at least one nested tier n_independent < {N_INDEPENDENT_PROMOTION_FLOOR}"
            ),
        }

    # 任一 net 不可用 → inconclusive（不偽造判定）。
    if any(n is None for n in nets):
        return {
            "net_bps_monotonic_in_breadth": False,
            "net_bps_trend": "inconclusive",
            "narrow_only_edge": False,
            "n_independent_invariant_to_breadth": _n_independent_invariant(per_tier_n),
            "binding_ceiling": "time_period_count",
            "per_tier_net_bps": per_tier_net,
            "per_tier_n_independent": per_tier_n,
            "verdict_hint": "inconclusive",
            "reason": "missing_net_bps_in_at_least_one_tier",
        }

    # collapse 判定：最寬 tier net 明顯塌縮（< 最窄的一半 或 翻負）→ narrow fluke。
    # 為什麼 0.5×：edge 集中窄基的指紋是「加寬後 edge 大幅蒸發」；保守用一半 + 翻負雙條件。
    collapses = (widest_net <= 0.0 and narrowest_net > 0.0) or (
        narrowest_net > 0.0 and widest_net < 0.5 * narrowest_net
    )
    # survives 判定：最寬 tier net 仍 > 0 且未塌縮（衰減在容忍內）。
    survives = (widest_net > 0.0) and (not collapses)
    # monotonic（弱遞減而非塌縮，或遞增）：相鄰差非劇烈塌縮。
    monotonic = survives

    if collapses:
        trend = "collapses_to_narrow"
        verdict_hint = "breadth-limited"
        narrow_only = True
    elif survives:
        trend = "survives"
        verdict_hint = "breadth_real"
        narrow_only = False
    else:
        # 最窄就 <=0（無 edge 可談存活）。
        trend = "decays"
        verdict_hint = "breadth-limited" if narrowest_net > 0 else "inconclusive"
        narrow_only = narrowest_net > 0

    return {
        "net_bps_monotonic_in_breadth": bool(monotonic),
        "net_bps_trend": trend,
        "narrow_only_edge": bool(narrow_only),
        "n_independent_invariant_to_breadth": _n_independent_invariant(per_tier_n),
        "binding_ceiling": "time_period_count",
        "per_tier_net_bps": per_tier_net,
        "per_tier_n_independent": per_tier_n,
        "verdict_hint": verdict_hint,
        "reason": None,
    }


def _is_tier_design_excluded(row: dict) -> bool:
    """row 是否因 **tier 設計**（非 n_independent）而 diagnostic-only。

    為什麼需要區分：tier-design diagnostic-only（top_liquidity asof_constant cross-section
    leak / scanner overlap-only）不該進 monotonicity 主軸（OQ-B3）；但 n_independent<30
    的排除須留在主軸讓 n-gate 觸發 insufficient verdict（PA §5）。
    top_liquidity → tier_rank_pit_mode=='asof_constant'；scanner → tier_quality=='overlap_only'。
    """
    return (
        row.get("tier_rank_pit_mode") == "asof_constant"
        or row.get("tier_quality") == "overlap_only"
    )


def _n_independent_invariant(per_tier_n: dict) -> bool:
    """nested tier 間 n_independent 是否不因 breadth 加寬而膨脹（★ 招牌自證）。

    為什麼這是 breadth≠n_independent 的機械防線：time-cluster-bound n_independent 對
    固定窗應在 nested tier 間近乎不變（core25≈full）；若某 tier 隨 symbol 數明顯漲，代表
    n_independent 被 symbol-scaled 污染（false-rich-sample），返回 False 暴露之。容忍
    小幅差異（不同 tier 的 PIT 可用日數可能略不同），但不容許隨 symbol 數成比例放大。
    """
    vals = [v for v in per_tier_n.values() if v is not None]
    if len(vals) < 2:
        return True
    lo, hi = min(vals), max(vals)
    if lo <= 0:
        # 有 tier n_independent=0（樣本不足）→ 不主張 invariant 成立（保守 False）。
        return hi == 0
    # 容忍上限：最大不得超過最小的 2 倍（time-period count 的窗對齊應使差異很小；
    # symbol-scaled 污染會讓 full（800 sym）遠超 core25（25 sym），>>2×）。
    return hi <= 2 * lo


def build_ladder(
    tier_results: dict,
    *,
    run_id: str,
    candidate_id: str,
    asof_utc: str,
    window_start_utc: str,
    window_end_utc: str,
    fnd2_universe_id: str,
    fnd2_run_id: str,
    tier_quality_by_name: Optional[dict] = None,
    tier_rank_pit_mode_by_name: Optional[dict] = None,
    promotion_exclusion_by_name: Optional[dict] = None,
) -> tuple:
    """核心 builder（PA §5）。回 ``(rows, summary)``。

    tier_results：``{tier_name: TierResult}``（由 evaluator 產，per tier 一個）。
    tier_quality_by_name / tier_rank_pit_mode_by_name / promotion_exclusion_by_name：
      由 universe_artifact / harness 層決定的 per-tier metadata（top_liquidity 降級在此
      傳入）；promotion_exclusion_by_name[tier] = (excluded:bool, reason:str|None)。

    rows：每 tier 一行（LADDER_COLUMNS 全欄），按 (monotonicity_rank, tier 名) 排序。
    summary：per_tier_* + monotonicity + delisted_proof_total + verdict_hint（PA §5）。
    """
    tier_quality_by_name = tier_quality_by_name or {}
    tier_rank_pit_mode_by_name = tier_rank_pit_mode_by_name or {}
    promotion_exclusion_by_name = promotion_exclusion_by_name or {}

    rows = []
    for tier_name, tr in tier_results.items():
        excluded, reason = promotion_exclusion_by_name.get(tier_name, (False, None))
        # n_independent < 30 也標 excluded（gate 3 機械化，PA §5 / T-insufficient-n）。
        if (not excluded) and tr.n_independent < N_INDEPENDENT_PROMOTION_FLOOR:
            excluded = True
            reason = _join_reason(reason, "n_independent_below_30")
        rows.append(_build_row(
            tr,
            run_id=run_id,
            candidate_id=candidate_id,
            asof_utc=asof_utc,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            fnd2_universe_id=fnd2_universe_id,
            fnd2_run_id=fnd2_run_id,
            tier_quality=tier_quality_by_name.get(tier_name, "ok"),
            tier_rank_pit_mode=tier_rank_pit_mode_by_name.get(tier_name, "n/a"),
            excluded_from_promotion=excluded,
            exclusion_reason=reason,
        ))

    # row 固定排序（determinism）：nested 在前按 rank 升序，overlap（rank=None）在後按名。
    rows.sort(key=lambda r: (
        0 if r["monotonicity_rank"] is not None else 1,
        r["monotonicity_rank"] if r["monotonicity_rank"] is not None else 0,
        r["breadth_cohort"],
    ))

    ladder_id = compute_ladder_id(
        rows, fnd2_universe_id=fnd2_universe_id, candidate_id=candidate_id,
    )
    for r in rows:
        r["ladder_id"] = ladder_id

    summary = _build_summary(
        rows, run_id=run_id, candidate_id=candidate_id, ladder_id=ladder_id,
        asof_utc=asof_utc, window_start_utc=window_start_utc, window_end_utc=window_end_utc,
        fnd2_universe_id=fnd2_universe_id, fnd2_run_id=fnd2_run_id,
    )
    return rows, summary


def _build_summary(
    rows: list,
    *,
    run_id: str,
    candidate_id: str,
    ladder_id: str,
    asof_utc: str,
    window_start_utc: str,
    window_end_utc: str,
    fnd2_universe_id: str,
    fnd2_run_id: str,
) -> dict:
    """summary dict（PA §5 breadth_ladder_summary.json）。"""
    # nested tier（monotonicity 主軸）。
    # 為什麼用 tier-design 排除而非全 excluded_from_promotion 排除：promotion 排除有兩源
    # — (1) tier-design diagnostic-only（top_liquidity asof_constant / scanner overlap，
    # OQ-B3，這些**不該**進 monotonicity 主軸）；(2) n_independent<30（gate 3，這些**該**
    # 留在主軸讓 classify_monotonicity 的 n-gate 觸發 insufficient_n_independent，PA §5）。
    # 若把 n-independent-excluded tier 也移除，會讓主軸只剩 core25 → 退化成 inconclusive，
    # 漏掉 sample 牆 verdict（T-insufficient-n）。故此處只排除 tier-design diagnostic-only。
    nested_rows = [r for r in rows if r["monotonicity_rank"] is not None]
    nested_for_monotonicity = [r for r in nested_rows if not _is_tier_design_excluded(r)]
    nested_for_monotonicity.sort(key=lambda r: r["monotonicity_rank"])

    monotonicity = classify_monotonicity(nested_for_monotonicity)

    per_tier_net = {r["breadth_cohort"]: _to_float(r["net_bps"]) for r in rows}
    per_tier_n = {r["breadth_cohort"]: _to_int(r["n_independent"]) for r in rows}
    per_tier_breadth = {r["breadth_cohort"]: r["breadth_symbol_count"] for r in rows}
    delisted_proof_total = sum(int(r["seen_delisted_count"] or 0) for r in rows)

    return {
        "run_id": run_id,
        "ladder_id": ladder_id,
        "candidate_id": candidate_id,
        "breadth_ladder_version": BREADTH_LADDER_VERSION,
        "fnd2_universe_id": fnd2_universe_id,
        "fnd2_run_id": fnd2_run_id,
        "asof_utc": asof_utc,
        "window_start_utc": window_start_utc,
        "window_end_utc": window_end_utc,
        "tiers_evaluated": [r["breadth_cohort"] for r in rows],
        "per_tier_net_bps": per_tier_net,
        "per_tier_n_independent": per_tier_n,
        "per_tier_breadth": per_tier_breadth,
        "monotonicity": monotonicity,
        "delisted_proof_total": delisted_proof_total,
        "survivorship_inherited_from_fnd2": True,
        "verdict_hint": monotonicity["verdict_hint"],
    }


def ordered_tier_digest(rows: list) -> str:
    """canonical-sorted ladder row 的穩定 digest（sha256 hex，determinism R-4）。

    為什麼用固定 _DIGEST_COLUMNS 子集：排除 run_id/ladder_id（避免循環）與 asof/window
    （由 fnd2_universe_id 已涵蓋窗）。row 已在 build_ladder 排序，但這裡再依
    (monotonicity_rank, breadth_cohort) canonical 排序確保 digest 與 row 順序無關。
    """
    h = hashlib.sha256()
    sorted_rows = sorted(
        rows,
        key=lambda r: (
            0 if r["monotonicity_rank"] is not None else 1,
            r["monotonicity_rank"] if r["monotonicity_rank"] is not None else 0,
            r["breadth_cohort"],
        ),
    )
    for r in sorted_rows:
        for col in _DIGEST_COLUMNS:
            h.update(_canonical_cell(r.get(col)).encode("utf-8"))
            h.update(b"\x1f")  # 欄分隔
        h.update(b"\x1e")  # 行分隔
    return h.hexdigest()


def compute_ladder_id(rows: list, *, fnd2_universe_id: str, candidate_id: str) -> str:
    """deterministic ladder_id（PA §5）。

    digest 輸入 = fnd2_universe_id || candidate_id || BREADTH_LADDER_VERSION ||
    ordered_tier_digest。同 universe + 同 candidate + 同 storage → 同 ladder_id
    （T-determinism；跨進程穩定靠 %.12g + 固定排序）。
    """
    parts = [
        fnd2_universe_id or "",
        candidate_id or "",
        BREADTH_LADDER_VERSION,
        ordered_tier_digest(rows),
    ]
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def _to_float(value) -> Optional[float]:
    """row cell（格式化字串/數值/None）→ float（不可轉回 None，不拋）。"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int:
    """row cell → int（不可轉回 0）。"""
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _join_reason(existing: Optional[str], new: str) -> str:
    """串接 exclusion reason（分號分隔，不重複）。"""
    if not existing:
        return new
    parts = [p.strip() for p in existing.split(";") if p.strip()]
    if new not in parts:
        parts.append(new)
    return "; ".join(parts)


__all__ = [
    "LADDER_COLUMNS",
    "build_ladder",
    "classify_monotonicity",
    "compute_ladder_id",
    "ordered_tier_digest",
]
