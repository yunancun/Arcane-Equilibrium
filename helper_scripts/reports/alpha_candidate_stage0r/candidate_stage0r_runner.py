#!/usr/bin/env python3
"""Alpha Tournament Candidate Stage 0R Runner（Track B）。

MODULE_NOTE
模塊用途：alpha tournament candidate（A1 funding_short_v2 / A2
liquidation_cascade_fade）的 Stage 0R sanity runner 純 offline 計算層。對
candidate cohort（BTC/ETH 2-symbol）跑 6 sanity check（leak / bias-selection /
DSR-PSR / PBO-bootstrap / concentration / governance ATTEST）→ 組單一 JSON
packet（per-candidate six_check 三態 verdict + sample_sufficiency + 整體
stage0_ready）。PG 取數 + argparse + JSON render 的 IO 層在 sibling
candidate_stage0r_report.py（mirror 8c metrics.py / report.py 拆分）。

current scope：
  - A1（functional）：讀 alpha_candidate_a1_funding_short_features.sql 的
    as-of funding/basis rows，復現 funding_short_v2 entry gate，並把持倉窗口內
    market.funding_rates settlement carry 計入 net_bps。這修正了 2026-05-29
    basis_panel 還不存在時留下的 stale stub。
  - A2（functional）：復用 W-AUDIT-8c per-event 路徑（a2_cascade_adapter），方向
    與 A2 一致；2 adapter（k_total override DSR 重算 + fixed-horizon proxy）。

6-check 用 time-block CSCV（per spec v2 §3/§4.2）：2-symbol 不可 symbol-cross-
section（8b/8c symbol×cell CSCV 需 ≥10 candidate keys，candidate 是固定單一
cell）。改 day-block train/test split（best-in-train vs test-median），≥4
distinct days 才可判，否則 pbo=None → observe_more（sample insufficient 非 fail）。

主要類函數：run_candidates / a1_draft_only_packet / _time_block_cscv_pbo /
            _classify_sample_sufficiency / _candidate_six_check_a2 /
            _candidate_verdict_lane / _overall_verdict。
依賴：sibling a2_cascade_adapter；sibling W-AUDIT-8c metrics（透過 adapter）；
      W-AUDIT-8b 純統計原語（block_bootstrap_ci / wilson_ci_95 —
      direction-agnostic / leak-free）。純 stdlib，本檔不連 PG。
硬邊界（per CLAUDE §四 + 16 原則 #3/#7 + AMD §3.2）：
  - 純 offline 計算：不連 PG（由 caller 傳 rows）；不下單 / 不碰 live / 不寫
    trading|panel|market / 不調 Rust / 不碰 authorization|lease|paper|mainnet。
  - AMD §3.2 forbidden output：packet 絕不 emit Stage 1 PASS / auto_promote /
    canary_stage_log.to_stage / order / fill / TOML mutation；只
    eligible_for_demo_canary（true/false）。governance check（1/5/6）標
    ATTEST（待 E2 grep），不自證 PASS（ATTEST ≠ PASS）。
  - 不解鎖 candidate：stage0_ready=true 只是證據；candidate active=true 由
    operator/PM gate（runner 絕不改 TOML / 絕不 auto_promote）。
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

# ──────────────────────────────────────────────────────────────────────────
# sibling import：A2 adapter + 8b 純統計原語
# ──────────────────────────────────────────────────────────────────────────
try:
    from .a2_cascade_adapter import (  # type: ignore
        A2_ALPHA_SOURCE_ID,
        A2CandidateConfig,
        run_a2_candidate,
    )
except ImportError:
    _HERE0 = Path(__file__).resolve().parent
    if str(_HERE0) not in sys.path:
        sys.path.insert(0, str(_HERE0))
    from a2_cascade_adapter import (  # type: ignore
        A2_ALPHA_SOURCE_ID,
        A2CandidateConfig,
        run_a2_candidate,
    )

# 8b 純統計原語（direction-agnostic / leak-free / 無 cohort 依賴；spec v2 §2 復用）。
try:
    from ..w_audit_8b.funding_skew_stage0r_metrics import (  # type: ignore
        block_bootstrap_ci,
        dsr_with_k,
        psr_bailey_ldp,
        wilson_ci_95,
        _day_bucket,
        _n_eff,
        _safe_float as _safe_float_8b,  # noqa: F401  保留 import 對齊 spec §2 復用清單
    )
except ImportError:
    _HERE1 = Path(__file__).resolve().parent
    _B8 = _HERE1.parent / "w_audit_8b"
    if str(_B8) not in sys.path:
        sys.path.insert(0, str(_B8))
    from funding_skew_stage0r_metrics import (  # type: ignore
        block_bootstrap_ci,
        dsr_with_k,
        psr_bailey_ldp,
        wilson_ci_95,
        _day_bucket,
        _n_eff,
        _safe_float as _safe_float_8b,  # noqa: F401
    )


# ──────────────────────────────────────────────────────────────────────────
# 常數（per spec v2 §4 + §5）
# ──────────────────────────────────────────────────────────────────────────
RUNNER_VERSION = "candidate_stage0r.v2"
RUNNER_SUPERSEDES = "candidate_stage0r.v1 (8b harness reuse — QC direction error)"

# Stage 0R promotion floor（per spec v2 §5.1，與 8b/8c 同水準）。
PSR_THRESHOLD = 0.95
DSR_THRESHOLD = 0.95
PBO_THRESHOLD = 0.20
AVG_NET_FLOOR_BPS = 15.0
MAX_DAY_SHARE = 0.25
MAX_SYMBOL_SHARE = 0.30

# sample sufficiency（per spec v2 §4.2 / §5.3）。
N_EFF_DIAGNOSTIC_FLOOR = 300   # 與 8b/8c POOLED_N_EFF_FLOOR 對齊（降為診斷指標）。
MIN_DAYS_FOR_PBO = 4           # time-block CSCV ≥4 distinct days 才可判。

# bootstrap block size（5m bar 為單位；mirror 8b/8c）。
BOOTSTRAP_BLOCK_60M = 12        # 12 × 5m = 60m primary。
BOOTSTRAP_BLOCK_8H = 96         # 96 × 5m = 8h funding-cycle sensitivity（A1）。
BOOTSTRAP_BLOCK_4H = 48         # 48 × 5m = 4h sensitivity（A2）。

# A1 basis infra fallback reason（only when panel.basis_panel is unavailable).
A1_ALPHA_SOURCE_ID = "funding_short_v2"
A1_BASIS_INFRA_MISSING_REASON = "basis_panel_infra_missing"

# basis infra prereq ticket（A1 前置；spec v2 §3.4 + task brief §5）。
A1_BASIS_PREREQ_TICKET = "P2-BASIS-PANEL-INFRA"

# A1 strategy defaults（mirror rust/openclaw_engine/src/strategies/funding_short_v2/params.rs）。
A1_FUNDING_THRESHOLD_ANNUALIZED = 0.30
A1_FUNDING_EXIT_ANNUALIZED = 0.05
A1_MAX_BASIS_PCT = 0.5
A1_ENTRY_BASIS_RATIO = 0.6
A1_TOTAL_COST_BPS = 22.0
A1_EXPECTED_PERIODS = 1.5
A1_EDGE_BREAK_EVEN_FUNDING_RATE_BPS = A1_TOTAL_COST_BPS / A1_EXPECTED_PERIODS
A1_EDGE_BREAK_EVEN_ANNUALIZED = A1_EDGE_BREAK_EVEN_FUNDING_RATE_BPS / 10_000.0 * 1095.0
A1_COOLDOWN_MS = 8 * 3_600_000
A1_HOLD_HOURS = 24
A1_K_NEW_CANDIDATE = 2  # 2 symbols × short-only × one threshold set × one hold model


# ──────────────────────────────────────────────────────────────────────────
# Time-block CSCV PBO（spec v2 §4.2 核心新設計 — 2-symbol 不可 symbol-cross-section）
# ──────────────────────────────────────────────────────────────────────────


def _time_block_cscv_pbo(
    net_by_day: Mapping[str, Sequence[float]],
    *,
    pbo_max: float = PBO_THRESHOLD,
    min_days: int = MIN_DAYS_FOR_PBO,
    max_splits: int = 240,
) -> dict[str, object]:
    """Time-block CSCV PBO（candidate 單一 cell 的 day-block train/test 過擬合檢測）。

    為什麼不用 8b/8c symbol×cell CSCV：8b/8c `_pbo` 需 ≥10 candidate keys
    （sweep grid 的多 cell），但 candidate 是**固定單一 cell**（A2 per-symbol
    pinned threshold，非 sweep）+ 2-symbol → symbol-cross-section 無法成立
    （spec v2 §4.2）。改 time-block CSCV：把樣本按 calendar-day 切 day-block，
    對「該 candidate 唯一 cell」做 day train/test split。

    機制（per spec v2 §4.2）：
      - days = sorted distinct calendar days。
      - 每個 train/test split：train = half days，test = 其餘。
      - 「過擬合」= train 期 avg_net > 0（被選中為 in-sample best）但 test 期
        avg_net 落在 test 分布 median 之下（best-in-train below test-median）。
      - 單一 cell 下「best-in-train」退化為「該 cell train avg_net 是否正」，
        「test-median」用 test 期 per-day avg_net 的 median 作 generalization
        proxy：若 test 期 per-day return 半數以上 < 0（median < 0）視為 bad
        split（cell 在 in-sample 看似有 edge 但 out-of-sample 半數日子虧）。
      - pbo = bad_splits / usable_splits。

    < min_days(4) distinct days → pbo=None + reason，下游標 observe_more
    （sample insufficient，非 fail）。

    這是 day-block 過擬合 proxy，QC 必驗統計可行性（spec v2 §4.2 QC 必確認點）。
    """
    days = sorted(net_by_day.keys())
    if len(days) < min_days:
        return {
            "value": None,
            "method": "time_block_cscv",
            "usable_splits": 0,
            "reason": "insufficient_days",
            "day_count": len(days),
            "min_days_for_pbo": min_days,
        }

    train_size = len(days) // 2
    if train_size < 1 or train_size >= len(days):
        return {
            "value": None,
            "method": "time_block_cscv",
            "usable_splits": 0,
            "reason": "no_valid_train_test_split",
            "day_count": len(days),
            "min_days_for_pbo": min_days,
        }

    # day-block 組合（CSCV 對稱：train half / test half）。
    import math
    import random

    combo_count = math.comb(len(days), train_size)
    if combo_count <= max_splits:
        combos = list(combinations(days, train_size))
    else:
        rng = random.Random(20260529)
        seen: set[tuple[str, ...]] = set()
        combos = []
        attempts = 0
        while len(combos) < max_splits and attempts < max_splits * 20:
            train = tuple(sorted(rng.sample(days, train_size)))
            if train not in seen:
                seen.add(train)
                combos.append(train)
            attempts += 1

    bad = 0
    usable = 0
    for train_days in combos:
        train_set = set(train_days)
        test_days = [d for d in days if d not in train_set]
        train_vals: list[float] = []
        for d in train_days:
            train_vals.extend(net_by_day[d])
        # test 期 per-day avg_net（generalization proxy）。
        test_day_means: list[float] = []
        for d in test_days:
            vals = list(net_by_day[d])
            if vals:
                test_day_means.append(statistics.mean(vals))
        if not train_vals or not test_day_means:
            continue
        usable += 1
        train_avg = statistics.mean(train_vals)
        test_median = statistics.median(test_day_means)
        # 過擬合：in-sample 看似有 edge（train_avg > 0）但 out-of-sample
        # per-day median 落入虧損（test_median < 0）。
        if train_avg > 0.0 and test_median < 0.0:
            bad += 1

    if usable == 0:
        return {
            "value": None,
            "method": "time_block_cscv",
            "usable_splits": 0,
            "reason": "no_usable_splits",
            "day_count": len(days),
            "min_days_for_pbo": min_days,
        }

    pbo_value = bad / usable
    return {
        "value": pbo_value,
        "method": "time_block_cscv",
        "usable_splits": usable,
        "bad_splits": bad,
        "day_count": len(days),
        "train_day_count": train_size,
        "test_day_count": len(days) - train_size,
        "pbo_max": pbo_max,
        "reason": None,
    }


# ──────────────────────────────────────────────────────────────────────────
# sample sufficiency 分類（spec v2 §5.3 — sample_insufficient vs signal_failure）
# ──────────────────────────────────────────────────────────────────────────


def _classify_sample_sufficiency(
    *,
    n_eff: int,
    days: int,
    avg_net_bps: float | None,
    bootstrap_60m_lower: float | None,
) -> dict[str, object]:
    """區分 sample_insufficient（樣本不足）vs signal_failure（樣本足但確證負）。

    為什麼必分（spec v2 §5.3 + 架構教訓 29）：2-symbol + demo 短窗 + candidate
    active=false → n_eff 預期遠低 floor → 預期 verdict 多落 observe_more
    （sample insufficient），**不是 reject**。誤把樣本不足判成策略無效會 archive
    掉可能有效的 candidate。

      - sample_insufficient：n_eff < floor 或 days < min_days_for_pbo → PSR/DSR/
        PBO 無法可靠估計（None 或寬 CI）→ observe_more。
      - signal_failure：n_eff ≥ floor 且 days ≥ min_days 但 avg_net 確證負 /
        bootstrap lower < 0 → draft_only/reject。
    """
    sufficient = (n_eff >= N_EFF_DIAGNOSTIC_FLOOR) and (days >= MIN_DAYS_FOR_PBO)
    classification = "sufficient"
    if not sufficient:
        classification = "sample_insufficient"
    else:
        # 樣本足：判 signal failure（確證負 net 或 bootstrap lower < 0）。
        neg_net = avg_net_bps is not None and avg_net_bps < 0.0
        neg_ci = bootstrap_60m_lower is not None and bootstrap_60m_lower < 0.0
        if neg_net or neg_ci:
            classification = "signal_failure"
        else:
            classification = "sufficient"
    return {
        "n_eff": n_eff,
        "floor_diagnostic": N_EFF_DIAGNOSTIC_FLOOR,
        "days": days,
        "min_days_for_pbo": MIN_DAYS_FOR_PBO,
        "sufficient": sufficient,
        "classification": classification,
    }


# ──────────────────────────────────────────────────────────────────────────
# A1 source-unavailable fallback（functional path lives below）
# ──────────────────────────────────────────────────────────────────────────


def a1_draft_only_packet() -> dict[str, object]:
    """A1 funding_short_v2 fallback packet when source tables are unavailable.

    This path is only valid when the report-layer availability probe cannot find
    the required basis source. When panel.basis_panel is present, the functional
    A1 path must run and this stale-stub fallback must not be used.
    """
    return {
        "alpha_source_id": A1_ALPHA_SOURCE_ID,
        "path": "stub_draft_only_no_cohort",
        "candidate_thresholds": {
            "funding_annualized_min": A1_FUNDING_THRESHOLD_ANNUALIZED,
            "edge_break_even_funding_rate_bps": A1_EDGE_BREAK_EVEN_FUNDING_RATE_BPS,
            "edge_break_even_annualized": A1_EDGE_BREAK_EVEN_ANNUALIZED,
            "basis_pct_abs_max": A1_MAX_BASIS_PCT * A1_ENTRY_BASIS_RATIO,
            "branch": "short_only",
            "note": "A1 entry gate 設計值回顯；source unavailable 時不建 cohort",
        },
        # 六 check 全標 not_applicable（無 cohort 可算）。
        "six_check": {
            "1_leak_lookahead": {
                "verdict": "draft_only",
                "evidence": "A1 source unavailable；functional SQL not executed",
            },
            "2_bias_selection": {"verdict": "draft_only"},
            "3_dsr_psr": {"verdict": "draft_only"},
            "4_pbo_bootstrap": {"verdict": "draft_only"},
            "5_data_tier": {
                "verdict": "draft_only",
                "evidence": "required source unavailable at report time",
            },
            "6_governance": {"verdict": "draft_only"},
        },
        "eligible_for_demo_canary": False,
        "sample_sufficiency": {
            "classification": "not_applicable",
            "note": "無 cohort 可算 n_eff/days",
        },
        "fail_reasons": [
            A1_BASIS_INFRA_MISSING_REASON,
            "panel.basis_panel unavailable at report time；A1 basis entry gate cannot be evaluated",
        ],
        "verdict": "draft_only",
        "infra_gap": True,
        "is_signal_failure": False,
        "prereq_ticket": A1_BASIS_PREREQ_TICKET,
        "prereq_note": "A1 cohort 前置：basis = perp price vs spot/index basis data "
                       "pipeline + panel + writer；source unavailable 時才需要 "
                       + A1_BASIS_PREREQ_TICKET + "。",
    }


# ──────────────────────────────────────────────────────────────────────────
# A1 functional path（funding_short_v2）
# ──────────────────────────────────────────────────────────────────────────


def _safe_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _a1_edge_bps_per_period(funding_rate_bps: float) -> float:
    """Mirror Rust compute_edge in bps-per-period units."""
    return abs(funding_rate_bps) - (A1_TOTAL_COST_BPS / A1_EXPECTED_PERIODS)


def _a1_entry_gate(row: Mapping[str, Any]) -> tuple[bool, dict[str, object]]:
    """Evaluate funding_short_v2 entry gates from one feature row."""
    funding_rate_bps = _safe_float_8b(row.get("funding_rate_bps"))
    funding_ann = _safe_float_8b(row.get("funding_annualized"))
    basis_pct = _safe_float_8b(row.get("basis_pct"))
    net_bps = _safe_float_8b(row.get("net_bps"))
    exit_ts = _safe_int(row.get("exit_ts_ms"))
    reasons: list[str] = []
    if funding_rate_bps is None or funding_ann is None:
        reasons.append("missing_funding_asof")
    if basis_pct is None:
        reasons.append("missing_basis_asof")
    if net_bps is None or exit_ts is None:
        reasons.append("missing_exit_or_net")
    if reasons:
        return False, {"reasons": reasons}

    edge_bps = _a1_edge_bps_per_period(funding_rate_bps)
    if funding_rate_bps <= 0.0:
        reasons.append("funding_rate_non_positive")
    if funding_ann <= A1_FUNDING_THRESHOLD_ANNUALIZED:
        reasons.append("funding_annualized_below_threshold")
    if abs(basis_pct) >= A1_MAX_BASIS_PCT * A1_ENTRY_BASIS_RATIO:
        reasons.append("basis_above_entry_gate")
    if edge_bps <= 0.0:
        reasons.append("edge_bps_per_period_non_positive")
    return not reasons, {
        "reasons": reasons,
        "funding_rate_bps": funding_rate_bps,
        "funding_annualized": funding_ann,
        "basis_pct": basis_pct,
        "edge_bps_per_period": edge_bps,
        "net_bps": net_bps,
    }


def _a1_select_signals(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Apply A1 entry gate + per-symbol 8h cooldown to feature rows."""
    sorted_rows = sorted(
        (dict(r) for r in rows),
        key=lambda r: (int(r.get("signal_ts_ms") or 0), str(r.get("symbol") or "")),
    )
    last_signal_by_symbol: dict[str, int] = {}
    signals: list[dict[str, object]] = []
    reject_counts: Counter[str] = Counter()
    max_funding_ann: float | None = None
    max_abs_basis: float | None = None
    usable_rows = 0
    for row in sorted_rows:
        symbol = str(row.get("symbol") or "")
        signal_ts = _safe_int(row.get("signal_ts_ms"))
        if not symbol or signal_ts is None:
            reject_counts["missing_symbol_or_ts"] += 1
            continue
        funding_ann = _safe_float_8b(row.get("funding_annualized"))
        basis_pct = _safe_float_8b(row.get("basis_pct"))
        if funding_ann is not None:
            max_funding_ann = funding_ann if max_funding_ann is None else max(max_funding_ann, funding_ann)
        if basis_pct is not None:
            abs_basis = abs(basis_pct)
            max_abs_basis = abs_basis if max_abs_basis is None else max(max_abs_basis, abs_basis)

        ok, meta = _a1_entry_gate(row)
        if not ok:
            for reason in meta.get("reasons", []):  # type: ignore[union-attr]
                reject_counts[str(reason)] += 1
            continue
        usable_rows += 1
        prev_ts = last_signal_by_symbol.get(symbol)
        if prev_ts is not None and signal_ts - prev_ts < A1_COOLDOWN_MS:
            reject_counts["cooldown_dedup"] += 1
            continue
        last_signal_by_symbol[symbol] = signal_ts
        day = _day_bucket(signal_ts)
        signals.append(
            {
                "symbol": symbol,
                "signal_ts_ms": signal_ts,
                "day_bucket": day,
                "net_bps": meta["net_bps"],
                "price_gross_bps": _safe_float_8b(row.get("price_gross_bps")),
                "funding_carry_bps": _safe_float_8b(row.get("funding_carry_bps")),
                "funding_settlement_count": _safe_int(row.get("funding_settlement_count")) or 0,
                "funding_rate_bps": meta["funding_rate_bps"],
                "funding_annualized": meta["funding_annualized"],
                "basis_pct": meta["basis_pct"],
                "edge_bps_per_period": meta["edge_bps_per_period"],
            }
        )
    return signals, {
        "input_rows": len(sorted_rows),
        "gate_pass_rows_before_cooldown": usable_rows,
        "selected_signals": len(signals),
        "reject_counts": dict(reject_counts),
        "funding_threshold_annualized": A1_FUNDING_THRESHOLD_ANNUALIZED,
        "edge_break_even_funding_rate_bps": A1_EDGE_BREAK_EVEN_FUNDING_RATE_BPS,
        "edge_break_even_annualized": A1_EDGE_BREAK_EVEN_ANNUALIZED,
        "max_funding_annualized_seen": max_funding_ann,
        "max_abs_basis_pct_seen": max_abs_basis,
    }


def a1_candidate_packet(
    feature_rows: Sequence[Mapping[str, Any]] | None,
    *,
    k_prior: int = 0,
    k_prior_source: str = "manual",
    hold_hours: int = A1_HOLD_HOURS,
    bootstrap_iters: int = 400,
    rng_seed: int = 20260529,
) -> dict[str, object]:
    """Build the A1 funding_short_v2 candidate packet from read-only feature rows."""
    if feature_rows is None:
        return a1_draft_only_packet()

    signals, gate_meta = _a1_select_signals(feature_rows)
    net_values = [float(s["net_bps"]) for s in signals if _safe_float_8b(s.get("net_bps")) is not None]
    net_by_day: dict[str, list[float]] = defaultdict(list)
    by_symbol: Counter[str] = Counter()
    for sig in signals:
        net = _safe_float_8b(sig.get("net_bps"))
        day = str(sig.get("day_bucket") or "")
        symbol = str(sig.get("symbol") or "")
        if net is not None and day:
            net_by_day[day].append(net)
        if symbol:
            by_symbol[symbol] += 1

    k_total = int(k_prior) + A1_K_NEW_CANDIDATE
    n_eff = _n_eff(len(net_values), hold_hours * 60)
    avg_net = statistics.mean(net_values) if net_values else None
    psr = psr_bailey_ldp(net_values)
    dsr = dsr_with_k(net_values, k_total)
    pbo_meta = _time_block_cscv_pbo(net_by_day)
    pbo_value = _safe_float_8b(pbo_meta.get("value"))
    ci_60m = block_bootstrap_ci(
        net_values,
        block_size=BOOTSTRAP_BLOCK_60M,
        iterations=bootstrap_iters,
        seed=rng_seed,
    ) if net_values else None
    ci_8h = block_bootstrap_ci(
        net_values,
        block_size=BOOTSTRAP_BLOCK_8H,
        iterations=bootstrap_iters,
        seed=rng_seed,
    ) if net_values else None
    ci_60m_lower = ci_60m[0] if isinstance(ci_60m, (list, tuple)) and ci_60m else None
    max_day_share = (
        max((len(v) for v in net_by_day.values()), default=0) / len(net_values)
        if net_values else None
    )
    max_symbol_share = (
        max(by_symbol.values(), default=0) / len(net_values)
        if net_values else None
    )
    sample_suff = _classify_sample_sufficiency(
        n_eff=n_eff,
        days=len(net_by_day),
        avg_net_bps=avg_net,
        bootstrap_60m_lower=ci_60m_lower,
    )

    if not net_values:
        six_check = {
            "1_leak_lookahead": {
                "verdict": "ATTEST",
                "evidence": "A1 SQL uses funding/basis LATERAL as-of joins and future exit rows; funding carry is outcome only",
                "e2_grep_required": True,
            },
            "2_bias_selection": {"verdict": "INSUFFICIENT", "reason": "no_selected_signals"},
            "3_dsr_psr": {"verdict": "INSUFFICIENT", "psr_0": None, "dsr": None},
            "4_pbo_bootstrap": {"verdict": "INSUFFICIENT", "pbo": None, "pbo_reason": "no_selected_signals"},
            "5_data_tier": {
                "verdict": "ATTEST",
                "source_tables": ["panel.funding_rates_panel", "panel.basis_panel", "market.klines", "market.funding_rates"],
                "synthetic_excluded": True,
            },
            "6_governance": {
                "verdict": "ATTEST",
                "emits_only": "eligible_for_demo_canary",
                "forbidden_output_present": False,
                "e2_grep_required": True,
            },
        }
        verdict = "draft_only"
        eligible = False
        reasons = ["no_a1_signals_after_entry_gate"]
    else:
        check2_pass = (
            max_day_share is not None and max_day_share <= MAX_DAY_SHARE
            and max_symbol_share is not None and max_symbol_share <= MAX_SYMBOL_SHARE
        )
        check3_pass = psr is not None and psr >= PSR_THRESHOLD and dsr is not None and dsr >= DSR_THRESHOLD
        if pbo_value is None:
            check4_verdict = "INSUFFICIENT"
        else:
            check4_verdict = "PASS" if (
                pbo_value <= PBO_THRESHOLD
                and ci_60m_lower is not None
                and ci_60m_lower > 0.0
            ) else "FAIL"
        six_check = {
            "1_leak_lookahead": {
                "verdict": "ATTEST",
                "evidence": "A1 SQL uses funding/basis LATERAL as-of joins and future exit rows; funding carry is outcome only",
                "e2_grep_required": True,
            },
            "2_bias_selection": {
                "verdict": "PASS" if check2_pass else "FAIL",
                "max_day_share": max_day_share,
                "max_symbol_share": max_symbol_share,
                "day_cap": MAX_DAY_SHARE,
                "symbol_cap": MAX_SYMBOL_SHARE,
            },
            "3_dsr_psr": {
                "verdict": "PASS" if check3_pass else "FAIL",
                "psr_0": psr,
                "dsr": dsr,
                "threshold": PSR_THRESHOLD,
                "k_total": k_total,
            },
            "4_pbo_bootstrap": {
                "verdict": check4_verdict,
                "pbo": pbo_value,
                "pbo_method": "time_block_cscv",
                "pbo_max": PBO_THRESHOLD,
                "pbo_reason": pbo_meta.get("reason"),
                "ci_60m_lower": ci_60m_lower,
                "ci_8h_lower": ci_8h[0] if isinstance(ci_8h, (list, tuple)) and ci_8h else None,
            },
            "5_data_tier": {
                "verdict": "ATTEST",
                "source_tables": ["panel.funding_rates_panel", "panel.basis_panel", "market.klines", "market.funding_rates"],
                "synthetic_excluded": True,
            },
            "6_governance": {
                "verdict": "ATTEST",
                "emits_only": "eligible_for_demo_canary",
                "forbidden_output_present": False,
                "e2_grep_required": True,
            },
        }
        verdict, eligible, reasons = _candidate_verdict_lane(six_check, sample_suff)
        if k_prior_source == "unavailable" and verdict == "stage0_ready":
            verdict = "observe_more"
            eligible = False
            reasons.append("a1_k_prior_unavailable_conservative_downgrade")

    return {
        "alpha_source_id": A1_ALPHA_SOURCE_ID,
        "path": "dedicated_a1_funding_short_with_funding_carry",
        "candidate_thresholds": {
            "funding_annualized_min": A1_FUNDING_THRESHOLD_ANNUALIZED,
            "edge_break_even_funding_rate_bps": A1_EDGE_BREAK_EVEN_FUNDING_RATE_BPS,
            "edge_break_even_annualized": A1_EDGE_BREAK_EVEN_ANNUALIZED,
            "basis_pct_abs_max": A1_MAX_BASIS_PCT * A1_ENTRY_BASIS_RATIO,
            "branch": "short_only",
        },
        "exit_model": f"fixed_hold_{hold_hours}h_with_realized_funding_proxy",
        "k_total": {
            "k_prior": int(k_prior),
            "k_prior_source": k_prior_source,
            "k_new": A1_K_NEW_CANDIDATE,
            "basis": "2sym x short_only x 1threshold x 1hold_model",
            "k_total": k_total,
        },
        "stats": {
            "n": len(net_values),
            "n_eff": n_eff,
            "days": len(net_by_day),
            "avg_net_bps": avg_net,
            "psr_0": psr,
            "dsr": dsr,
            "pbo": pbo_value,
            "bootstrap_ci_95_60m": ci_60m,
            "bootstrap_ci_95_8h": ci_8h,
            "max_day_share": max_day_share,
            "max_symbol_share": max_symbol_share,
        },
        "gate_diagnostics": gate_meta,
        "six_check": six_check,
        "eligible_for_demo_canary": eligible,
        "sample_sufficiency": sample_suff,
        "fail_reasons": reasons,
        "verdict": verdict,
        "stage0_ready_candidate": verdict == "stage0_ready",
        "infra_gap": False,
        "is_signal_failure": sample_suff.get("classification") == "signal_failure",
    }


# ──────────────────────────────────────────────────────────────────────────
# A2 6-check 組裝（from a2_cascade_adapter 結果）
# ──────────────────────────────────────────────────────────────────────────


def _candidate_six_check_a2(a2_result: Mapping[str, object]) -> dict[str, object]:
    """從 a2 adapter 結果組 6-check（per spec v2 §4.1 三態 verdict）。

    check 三態：
      - PASS/FAIL（stat 2/3）。
      - PASS/FAIL/INSUFFICIENT（4 因 sample 不足 → observe_more 非 fail）。
      - ATTEST（governance 1/5/6，待 E2 grep；ATTEST ≠ PASS）。

    check 1/5/6 = governance/grep ATTEST，權威 PASS 由 E2 grep proof 給。
    """
    packet = a2_result.get("packet_8c") or {}
    if not isinstance(packet, Mapping):
        packet = {}

    psr = _safe_float_8b(packet.get("psr_0"))
    dsr = _safe_float_8b(packet.get("dsr"))  # 已 override 後值
    pbo_meta = a2_result.get("pbo_meta") or {}
    if not isinstance(pbo_meta, Mapping):
        pbo_meta = {}
    pbo_value = _safe_float_8b(pbo_meta.get("value"))
    pbo_reason = pbo_meta.get("reason")

    day_check = packet.get("single_day_concentration") or {}
    symbol_check = packet.get("single_symbol_concentration") or {}
    max_day_share = _safe_float_8b(day_check.get("max_day_share")) if isinstance(day_check, Mapping) else None
    max_symbol_share = _safe_float_8b(symbol_check.get("max_symbol_share")) if isinstance(symbol_check, Mapping) else None

    ci_60m = a2_result.get("bootstrap_ci_95_60m")
    ci_4h = a2_result.get("bootstrap_ci_95_4h")
    ci_60m_lower = ci_60m[0] if isinstance(ci_60m, (list, tuple)) and ci_60m else None
    ci_4h_lower = ci_4h[0] if isinstance(ci_4h, (list, tuple)) and ci_4h else None

    # check 2 bias/selection：concentration cap（cohort 固定非事後挑）。
    day_pass = max_day_share is not None and max_day_share <= MAX_DAY_SHARE
    sym_pass = max_symbol_share is not None and max_symbol_share <= MAX_SYMBOL_SHARE
    check2_verdict = "PASS" if (day_pass and sym_pass) else "FAIL"

    # check 3 DSR/PSR。
    psr_pass = psr is not None and psr >= PSR_THRESHOLD
    dsr_pass = dsr is not None and dsr >= DSR_THRESHOLD
    check3_verdict = "PASS" if (psr_pass and dsr_pass) else "FAIL"

    # check 4 PBO/bootstrap：PBO None → INSUFFICIENT（sample 不足，observe_more）。
    if pbo_value is None:
        check4_verdict = "INSUFFICIENT"
    else:
        pbo_ok = pbo_value <= PBO_THRESHOLD
        ci_ok = (ci_60m_lower is not None and ci_60m_lower > 0.0)
        check4_verdict = "PASS" if (pbo_ok and ci_ok) else "FAIL"

    return {
        "1_leak_lookahead": {
            "verdict": "ATTEST",
            "evidence": "8c SQL 不變（forward-return 嚴格未來 bar / LATERAL as-of / "
                        "cutoff leak-free）；adapter 純 Python row 過濾 + k_total "
                        "override，不改 8c SQL 結構",
            "e2_grep_required": True,
        },
        "2_bias_selection": {
            "verdict": check2_verdict,
            "max_day_share": max_day_share,
            "max_symbol_share": max_symbol_share,
            "day_cap": MAX_DAY_SHARE,
            "symbol_cap": MAX_SYMBOL_SHARE,
        },
        "3_dsr_psr": {
            "verdict": check3_verdict,
            "psr_0": psr,
            "dsr": dsr,
            "threshold": PSR_THRESHOLD,
            "dsr_k_total_overridden": True,
        },
        "4_pbo_bootstrap": {
            "verdict": check4_verdict,
            "pbo": pbo_value,
            "pbo_method": "time_block_cscv",
            "pbo_max": PBO_THRESHOLD,
            "pbo_reason": pbo_reason,
            "ci_60m_lower": ci_60m_lower,
            "ci_4h_lower": ci_4h_lower,
        },
        "5_data_tier": {
            "verdict": "ATTEST",
            "source_tables": ["market.liquidations", "market.klines"],
            "synthetic_excluded": True,
            "e2_grep_required": False,
        },
        "6_governance": {
            "verdict": "ATTEST",
            "emits_only": "eligible_for_demo_canary",
            "forbidden_output_present": False,
            "e2_grep_required": True,
        },
    }


# ──────────────────────────────────────────────────────────────────────────
# verdict lane 映射（SSOT §6 四 lane；spec v2 §5.2）
# ──────────────────────────────────────────────────────────────────────────


def _candidate_verdict_lane(
    six_check: Mapping[str, object],
    sample_suff: Mapping[str, object],
) -> tuple[str, bool, list[str]]:
    """per-candidate verdict lane（stage0_ready / observe_more / draft_only / reject）。

    映射（spec v2 §5.2）：
      - stage0_ready_candidate：6/6 stat PASS（governance ATTEST 待 E2 grep）
        且 sample sufficient → eligible_for_demo_canary。
      - observe_more：方向正但 sample 不足（INSUFFICIENT / sample_insufficient）。
      - draft_only：結構合理但 1+ stat check FAIL（非 sample 問題）。
      - reject：governance hit / 確證 negative（本 runner 純 offline，reject
        只在 signal_failure + stat FAIL 同時）。
    """
    reasons: list[str] = []
    classification = str(sample_suff.get("classification") or "")

    # 收 stat check verdict。
    stat_checks = {
        "2": six_check.get("2_bias_selection", {}),
        "3": six_check.get("3_dsr_psr", {}),
        "4": six_check.get("4_pbo_bootstrap", {}),
    }
    has_insufficient = any(
        isinstance(c, Mapping) and c.get("verdict") == "INSUFFICIENT"
        for c in stat_checks.values()
    )
    fail_checks = [
        k for k, c in stat_checks.items()
        if isinstance(c, Mapping) and c.get("verdict") == "FAIL"
    ]
    all_stat_pass = all(
        isinstance(c, Mapping) and c.get("verdict") == "PASS"
        for c in stat_checks.values()
    )

    # sample 不足 → observe_more（最優先；spec v2 §5.3 早期預期 lane）。
    if classification == "sample_insufficient" or has_insufficient:
        reasons.append("sample_insufficient: n_eff < floor 或 days < min_days_for_pbo "
                       "或 PBO INSUFFICIENT → observe_more（非 signal failure）")
        for k in fail_checks:
            reasons.append(f"check_{k}_FAIL（但 sample 不足，不判 reject）")
        return "observe_more", False, reasons

    # 樣本足。
    if all_stat_pass:
        # 6/6 stat PASS + sample sufficient → stage0_ready candidate。
        # governance（1/5/6）為 ATTEST 待 E2 grep，整體 stage0_ready 由 caller
        # 在 E2 grep confirm 後給；candidate 層 eligible 先標 true。
        return "stage0_ready", True, ["6/6 stat PASS + sample sufficient（governance ATTEST 待 E2 grep）"]

    # 樣本足但 stat FAIL。
    if classification == "signal_failure":
        reasons.append("signal_failure: 樣本足但 avg_net 確證負 / bootstrap lower < 0")
        reasons.extend([f"check_{k}_FAIL" for k in fail_checks])
        return "reject", False, reasons

    reasons.extend([f"check_{k}_FAIL" for k in fail_checks])
    return "draft_only", False, reasons


# ──────────────────────────────────────────────────────────────────────────
# core runner
# ──────────────────────────────────────────────────────────────────────────


def run_candidates(
    a2_panel_rows: Sequence[Mapping[str, Any]],
    *,
    a2_total_bucket_count: int | None,
    window_days: int,
    a1_feature_rows: Sequence[Mapping[str, Any]] | None = (),
    a1_k_prior: int = 0,
    a1_k_prior_source: str = "manual",
    a1_hold_hours: int = A1_HOLD_HOURS,
    a2_cfg: A2CandidateConfig | None = None,
    bootstrap_iters: int = 400,
    rng_seed: int = 20260529,
) -> dict[str, object]:
    """跑 A1 + A2 candidates → 組單一 JSON packet。

    為什麼 a2_panel_rows 由 caller 傳：runner 殼負責 PG 取數（read-only），把
    8c SQL 結果列傳入；本函數純 offline 計算，便於 smoke test mock。
    """
    cfg = a2_cfg or A2CandidateConfig()

    # === A2 functional path ===
    a2_result = run_a2_candidate(
        a2_panel_rows,
        cfg,
        total_bucket_count=a2_total_bucket_count,
        bootstrap_iters=bootstrap_iters,
        rng_seed=rng_seed,
    )

    # 從 8c packet 取 per-event net 序列（adapter 已暴露 net_values 數量；
    # 此處用 packet 暴露的 per-event 不可直接得 → 用 adapter 內 parsed net）。
    # adapter 已回 n_net_values；net_by_day 需 signal_ts → 從 filtered rows 重建。
    net_by_day: dict[str, list[float]] = defaultdict(list)
    all_net: list[float] = []
    for row in a2_panel_rows:
        symbol = str(row.get("symbol") or "")
        if symbol not in cfg.cohort:
            continue
        threshold = cfg.per_symbol_threshold.get(symbol)
        cn = _safe_float_8b(row.get("cluster_notional_5m"))
        if threshold is None or cn is None or cn < threshold:
            continue
        net = _safe_float_8b(row.get("net_bps"))
        bet = row.get("bucket_end_ts_ms")
        ts_ms = None
        if isinstance(bet, (int, float)):
            ts_ms = int(bet)
        if net is None or ts_ms is None:
            continue
        net_by_day[_day_bucket(ts_ms)].append(net)
        all_net.append(net)

    # time-block CSCV PBO（spec v2 §4.2）。
    pbo_meta = _time_block_cscv_pbo(net_by_day)
    a2_result["pbo_meta"] = pbo_meta

    # bootstrap CI（60m primary + 4h sensitivity；block bootstrap 抗自相關）。
    ci_60m = block_bootstrap_ci(all_net, block_size=BOOTSTRAP_BLOCK_60M,
                                iterations=bootstrap_iters, seed=rng_seed) if all_net else None
    ci_4h = block_bootstrap_ci(all_net, block_size=BOOTSTRAP_BLOCK_4H,
                               iterations=bootstrap_iters, seed=rng_seed) if all_net else None
    a2_result["bootstrap_ci_95_60m"] = ci_60m
    a2_result["bootstrap_ci_95_4h"] = ci_4h

    # sample sufficiency（n_eff 用 8c packet pooled_n_eff；days = distinct days）。
    packet = a2_result.get("packet_8c") or {}
    n_eff = int(packet.get("pooled_n_eff") or 0) if isinstance(packet, Mapping) else 0
    days = len(net_by_day)
    avg_net = a2_result.get("avg_net_bps")
    ci_60m_lower = ci_60m[0] if isinstance(ci_60m, (list, tuple)) and ci_60m else None
    sample_suff = _classify_sample_sufficiency(
        n_eff=n_eff, days=days, avg_net_bps=avg_net, bootstrap_60m_lower=ci_60m_lower,
    )
    a2_result["sample_sufficiency"] = sample_suff

    # 6-check + verdict lane。
    six_check = _candidate_six_check_a2(a2_result)
    a2_result["six_check"] = six_check
    a2_verdict, a2_eligible, a2_reasons = _candidate_verdict_lane(six_check, sample_suff)
    a2_result["verdict"] = a2_verdict
    a2_result["eligible_for_demo_canary"] = a2_eligible
    a2_result["fail_reasons"] = a2_reasons
    a2_result["stage0_ready_candidate"] = (a2_verdict == "stage0_ready")

    # === A1 functional path ===
    a1_packet = a1_candidate_packet(
        a1_feature_rows,
        k_prior=a1_k_prior,
        k_prior_source=a1_k_prior_source,
        hold_hours=a1_hold_hours,
        bootstrap_iters=bootstrap_iters,
        rng_seed=rng_seed,
    )

    # === 整體 verdict lane（SSOT §6）===
    overall_verdict, overall_basis = _overall_verdict(a1_packet, a2_result)
    prereq_tickets = []
    if a1_packet.get("infra_gap"):
        prereq_tickets.append(
            {
                "ticket": A1_BASIS_PREREQ_TICKET,
                "blocks": "A1_funding_short_v2 cohort 邏輯",
                "what": "basis = perp price vs spot/index basis data pipeline + "
                        "panel.basis_panel + writer；A1 basis<0.3% entry gate 待此 land",
                "evidence": "A1 source unavailable at report time",
            }
        )

    return {
        "runner_version": RUNNER_VERSION,
        "supersedes": RUNNER_SUPERSEDES,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_days": window_days,
        "cohort": list(cfg.cohort),
        # AMD §3.2 forbidden output 自我宣告（E2 grep 權威）。
        "governance_attest": {
            "emits_only": "eligible_for_demo_canary",
            "forbidden_output_present": False,
            "no_stage1_pass": True,
            "no_auto_promote": True,
            "no_order_or_fill": True,
            "no_toml_mutation": True,
            "no_candidate_unlock": True,
            "attest_not_pass": "governance check 1/5/6 為 ATTEST 待 E2 grep proof",
        },
        "candidates": {
            "A1_funding_short_v2": a1_packet,
            "A2_liquidation_cascade_fade": a2_result,
        },
        "verdict": overall_verdict,
        "stage0_ready": overall_verdict == "stage0_ready",
        "verdict_basis": overall_basis,
        "prereq_tickets": prereq_tickets,
    }


def _overall_verdict(
    a1_packet: Mapping[str, object],
    a2_result: Mapping[str, object],
) -> tuple[str, str]:
    """整體 verdict lane（SSOT §6 四 lane；spec v2 §5.2）。
    """
    a1_verdict = str(a1_packet.get("verdict") or "draft_only")
    a2_verdict = str(a2_result.get("verdict") or "draft_only")
    if a1_verdict == "stage0_ready" or a2_verdict == "stage0_ready":
        winners = [
            name for name, verdict in (
                ("A1", a1_verdict),
                ("A2", a2_verdict),
            )
            if verdict == "stage0_ready"
        ]
        return "stage0_ready", (
            ", ".join(winners)
            + " 6/6 stat PASS + sample sufficient（governance ATTEST 待 E2 grep）"
        )
    if a1_verdict == "observe_more" or a2_verdict == "observe_more":
        return "observe_more", (
            f"A1={a1_verdict}, A2={a2_verdict}; 至少一條 candidate 方向未被確證失敗但樣本/統計不足"
        )
    if a1_verdict == "reject" and a2_verdict == "reject":
        return "reject", "A1/A2 樣本足且均 signal_failure"
    return "draft_only", f"A1={a1_verdict}, A2={a2_verdict}; 無 candidate 達 stage0_ready/observe_more"


# MODULE_NOTE 邊界：PG 取數 + argparse + JSON render IO 層已拆至 sibling
# candidate_stage0r_report.py（mirror 8c metrics.py / report.py 拆分）。本檔
# 只保留純 offline 計算（run_candidates 及其 helper），不連 PG、不做 IO。
