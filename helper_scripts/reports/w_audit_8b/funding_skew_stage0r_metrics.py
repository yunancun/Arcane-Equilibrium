"""Pure metrics for W-AUDIT-8b Funding Skew Stage 0R.

No DB or file IO belongs here. The report CLI feeds point-in-time feature rows
from ``sql/queries/w_audit_8b_funding_skew_stage0r_features.sql``.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from statistics import NormalDist
from typing import Iterable, Mapping, Sequence


Z_GRID = (1.5, 2.0, 2.5)
P_GRID = ((0.85, 0.15), (0.90, 0.10), (0.95, 0.05))
OI_GRID = (1.0, 2.0, 3.0)
HORIZONS = (15, 30, 60)
PRIMARY_HORIZON = 30
BRANCHES = ("crowded_long_fade", "crowded_short_squeeze")
STRATEGY_VARIANT = "funding_skew_directional.v0_2"
ALPHA_SOURCE_ID = "funding_skew_directional"
MIN_STAGE0R_SYMBOLS = 25
K_NEW_MIN = (
    MIN_STAGE0R_SYMBOLS
    * len(BRANCHES)
    * len(Z_GRID)
    * len(P_GRID)
    * len(OI_GRID)
    * len(HORIZONS)
)

WARN_AGE_MS = 60_000
EXCLUDE_AGE_MS = 300_000
SETTLEMENT_WINDOW_MS = 30 * 60_000
PRIMARY_BOOTSTRAP_BLOCK_SIZE = 12   # 12 根 5m bar = 60m 主檢定 block。
FUNDING_BOOTSTRAP_BLOCK_SIZE = 96   # 96 根 5m bar = 8h funding-cycle 敏感度。
PSR_THRESHOLD = 0.95
DSR_THRESHOLD = 0.95
PBO_THRESHOLD = 0.20
AVG_NET_FLOOR_BPS = 15.0
BASELINE_LIFT_FLOOR_BPS = 0.0
COST_EDGE_RATIO_MAX = 0.80
POOLED_N_EFF_FLOOR = 300
SYMBOL_N_EFF_FLOOR = 100
BRANCH_N_EFF_FLOOR = 50
MIN_FUNDING_CYCLES = 14
MAX_DAY_OR_CYCLE_SHARE = 0.25


@dataclass(frozen=True)
class CandidateKey:
    symbol: str
    branch: str
    z_hi: float
    p_hi: float
    p_lo: float
    oi_min_pct: float
    horizon_min: int

    def label(self) -> str:
        return (
            f"{self.symbol}|{self.branch}|z={self.z_hi:g}|p={self.p_hi:g}/{self.p_lo:g}|"
            f"oi={self.oi_min_pct:g}|h={self.horizon_min}"
        )


def _safe_float(value: object) -> float | None:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _safe_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _normal_cdf(x: float) -> float:
    return NormalDist().cdf(x)


def _skew(values: Sequence[float]) -> float | None:
    if len(values) < 3:
        return None
    mean = statistics.mean(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    if var <= 0:
        return None
    sd = math.sqrt(var)
    return sum(((v - mean) / sd) ** 3 for v in values) / len(values)


def _kurtosis(values: Sequence[float]) -> float | None:
    if len(values) < 4:
        return None
    mean = statistics.mean(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    if var <= 0:
        return None
    sd = math.sqrt(var)
    return sum(((v - mean) / sd) ** 4 for v in values) / len(values)


def psr_bailey_ldp(values: Sequence[float], sr_benchmark: float = 0.0) -> float | None:
    clean = [v for v in values if math.isfinite(v)]
    if len(clean) < 4:
        return None
    sd = statistics.stdev(clean)
    if sd <= 0:
        return None
    sr_hat = statistics.mean(clean) / sd
    skew = _skew(clean)
    kurt = _kurtosis(clean)
    if skew is None or kurt is None:
        return None
    denom_sq = 1.0 - skew * sr_hat + ((kurt - 1.0) / 4.0) * (sr_hat**2)
    if denom_sq <= 0:
        return None
    z = (sr_hat - sr_benchmark) * math.sqrt(len(clean) - 1) / math.sqrt(denom_sq)
    return _normal_cdf(z)


def dsr_with_k(values: Sequence[float], k_total: int) -> float | None:
    if k_total <= 1:
        return None
    sr_benchmark = math.sqrt(2.0 * math.log(k_total))
    return psr_bailey_ldp(values, sr_benchmark=sr_benchmark)


def block_bootstrap_ci(
    values: Sequence[float],
    *,
    block_size: int = PRIMARY_BOOTSTRAP_BLOCK_SIZE,
    iterations: int = 400,
    seed: int = 20260515,
) -> tuple[float, float] | None:
    clean = [v for v in values if math.isfinite(v)]
    if len(clean) < block_size:
        return None
    rng = random.Random(seed)
    means: list[float] = []
    blocks_per_iter = max(1, math.ceil(len(clean) / block_size))
    for _ in range(iterations):
        sample: list[float] = []
        for _b in range(blocks_per_iter):
            start = rng.randint(0, len(clean) - block_size)
            sample.extend(clean[start:start + block_size])
        means.append(statistics.mean(sample[:len(clean)]))
    means.sort()
    lo = max(0, int(0.025 * iterations))
    hi = min(iterations - 1, int(0.975 * iterations))
    return means[lo], means[hi]


def _summary_stats(
    values: Sequence[float],
    *,
    horizon_min: int = PRIMARY_HORIZON,
    k_total: int | None = None,
    include_bootstrap: bool = True,
) -> dict[str, object]:
    clean = [v for v in values if math.isfinite(v)]
    summary: dict[str, object] = {
        "n": len(clean),
        "n_eff": _n_eff(len(clean), horizon_min),
        "avg_net_bps": statistics.mean(clean) if clean else None,
        "psr_0": psr_bailey_ldp(clean),
    }
    if k_total is not None:
        summary["dsr"] = dsr_with_k(clean, k_total)
    if include_bootstrap:
        summary["bootstrap_ci_95_60m"] = block_bootstrap_ci(
            clean,
            block_size=PRIMARY_BOOTSTRAP_BLOCK_SIZE,
        )
        summary["bootstrap_ci_95_8h"] = block_bootstrap_ci(
            clean,
            block_size=FUNDING_BOOTSTRAP_BLOCK_SIZE,
        )
        summary["bootstrap_block_minutes"] = {
            "primary": PRIMARY_BOOTSTRAP_BLOCK_SIZE * 5,
            "funding_cycle_sensitivity": FUNDING_BOOTSTRAP_BLOCK_SIZE * 5,
        }
        # 保留舊讀者仍會看的欄位名。
        summary["bootstrap_ci_95"] = summary["bootstrap_ci_95_60m"]
    return summary


def _day_bucket(signal_ts_ms: int) -> str:
    return datetime.fromtimestamp(signal_ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _n_eff(n: int, horizon_min: int) -> int:
    return int(n / max(1, horizon_min // 5))


def _funding_interval_by_symbol(rows: Sequence[Mapping[str, object]]) -> dict[str, int | None]:
    by_symbol: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        symbol = str(row.get("symbol") or "")
        nxt = _safe_int(row.get("next_funding_ms"))
        if symbol and nxt:
            by_symbol[symbol].add(nxt)
    intervals: dict[str, int | None] = {}
    for symbol, values in by_symbol.items():
        ordered = sorted(values)
        deltas = [
            (b - a) // 60_000
            for a, b in zip(ordered, ordered[1:])
            if b > a
        ]
        intervals[symbol] = int(statistics.median(deltas)) if deltas else None
    return intervals


def _source_mode_from_tier(tier: str | None) -> str | None:
    if not tier:
        return None
    lowered = tier.lower()
    if "ws" in lowered or "ticker" in lowered or "current" in lowered:
        return "ws_current"
    if "rest" in lowered or "settled" in lowered or "history" in lowered:
        return "rest_settled"
    return "unknown"


def _source_mode(rows: Sequence[Mapping[str, object]]) -> str:
    modes = Counter(
        mode
        for row in rows
        for mode in (_source_mode_from_tier(str(row.get("funding_source_tier") or "")),)
        if mode
    )
    if not modes:
        return "unknown"
    if len(modes) == 1:
        return next(iter(modes))
    return "mixed"


def _panel_metadata(rows: Sequence[Mapping[str, object]], symbols: Sequence[str]) -> dict[str, object]:
    funding_snapshots = [
        value
        for row in rows
        for value in (_safe_int(row.get("funding_snapshot_ts_ms")),)
        if value is not None
    ]
    oi_snapshots = [
        value
        for row in rows
        for value in (_safe_int(row.get("oi_snapshot_ts_ms")),)
        if value is not None
    ]
    funding_ages = [
        value
        for row in rows
        for value in (_safe_int(row.get("funding_age_ms")),)
        if value is not None
    ]
    oi_ages = [
        value
        for row in rows
        for value in (_safe_int(row.get("oi_age_ms")),)
        if value is not None
    ]
    funding_tiers = Counter(str(row.get("funding_source_tier") or "missing") for row in rows)
    oi_tiers = Counter(str(row.get("oi_source_tier") or "missing") for row in rows)
    mode_counts = Counter()
    for tier, count in funding_tiers.items():
        mode = _source_mode_from_tier(tier)
        if mode:
            mode_counts[mode] += count
    cohort_ns = [
        value
        for row in rows
        for value in (_safe_int(row.get("funding_cohort_n")),)
        if value is not None
    ]
    funding_symbols = {
        str(row.get("symbol"))
        for row in rows
        if row.get("symbol") and _safe_int(row.get("funding_age_ms")) is not None
    }
    oi_symbols = {
        str(row.get("symbol"))
        for row in rows
        if row.get("symbol") and _safe_int(row.get("oi_age_ms")) is not None
    }
    symbol_count = len(symbols)
    return {
        "funding_latest_snapshot_ts_ms": max(funding_snapshots) if funding_snapshots else None,
        "funding_oldest_snapshot_ts_ms": min(funding_snapshots) if funding_snapshots else None,
        "oi_latest_snapshot_ts_ms": max(oi_snapshots) if oi_snapshots else None,
        "oi_oldest_snapshot_ts_ms": min(oi_snapshots) if oi_snapshots else None,
        "funding_max_age_ms": max(funding_ages) if funding_ages else None,
        "oi_max_age_ms": max(oi_ages) if oi_ages else None,
        "funding_source_tier_counts": dict(funding_tiers),
        "oi_source_tier_counts": dict(oi_tiers),
        "source_mode_counts": dict(mode_counts),
        "funding_symbol_coverage_pct": (len(funding_symbols) / symbol_count) if symbol_count else 0.0,
        "oi_symbol_coverage_pct": (len(oi_symbols) / symbol_count) if symbol_count else 0.0,
        "cohort_coverage": {
            "funding_cohort_n_min": min(cohort_ns) if cohort_ns else None,
            "funding_cohort_n_max": max(cohort_ns) if cohort_ns else None,
            "funding_cohort_n_avg": statistics.mean(cohort_ns) if cohort_ns else None,
        },
    }


def _signal_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    key: CandidateKey,
    cost_bps: float,
    funding_interval_min: int | None = None,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    fwd_col = f"fwd_return_{key.horizon_min}m_bps"
    for row in rows:
        funding_age = _safe_int(row.get("funding_age_ms"))
        oi_age = _safe_int(row.get("oi_age_ms"))
        if funding_age is None or oi_age is None:
            continue
        if funding_age > EXCLUDE_AGE_MS or oi_age > EXCLUDE_AGE_MS:
            continue
        z = _safe_float(row.get("funding_zscore_25sym"))
        pct = _safe_float(row.get("funding_percentile_25sym"))
        oi = _safe_float(row.get("oi_delta_15m_pct"))
        prior = _safe_float(row.get("prior_5m_return_bps"))
        fwd = _safe_float(row.get(fwd_col))
        if z is None or pct is None or oi is None or prior is None or fwd is None:
            continue
        direction = 0
        if (
            key.branch == "crowded_long_fade"
            and z >= key.z_hi
            and pct >= key.p_hi
            and oi >= key.oi_min_pct
            and prior <= 0
        ):
            direction = -1
        elif (
            key.branch == "crowded_short_squeeze"
            and z <= -key.z_hi
            and pct <= key.p_lo
            and oi >= key.oi_min_pct
            and prior >= 0
        ):
            direction = 1
        if direction == 0:
            continue
        signal_ts = _safe_int(row.get("signal_ts_ms"))
        if signal_ts is None:
            continue
        gross = direction * fwd
        next_funding = _safe_int(row.get("next_funding_ms"))
        interval_ms = funding_interval_min * 60_000 if funding_interval_min else None
        previous_funding = next_funding - interval_ms if next_funding and interval_ms else None
        is_settlement_window = (
            next_funding is not None
            and abs(next_funding - signal_ts) <= SETTLEMENT_WINDOW_MS
        ) or (
            previous_funding is not None
            and abs(signal_ts - previous_funding) <= SETTLEMENT_WINDOW_MS
        )
        out.append(
            {
                "signal_ts_ms": signal_ts,
                "net_bps": gross - cost_bps,
                "gross_bps": gross,
                "next_funding_ms": next_funding,
                "previous_funding_ms": previous_funding,
                "settlement_window": is_settlement_window,
            }
        )
    return out


def _baseline_signal_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    branch: str,
    cost_bps: float,
    horizon_min: int = PRIMARY_HORIZON,
    funding_interval_min: int | None = None,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    fwd_col = f"fwd_return_{horizon_min}m_bps"
    for row in rows:
        funding_age = _safe_int(row.get("funding_age_ms"))
        oi_age = _safe_int(row.get("oi_age_ms"))
        if funding_age is None or oi_age is None:
            continue
        if funding_age > EXCLUDE_AGE_MS or oi_age > EXCLUDE_AGE_MS:
            continue
        prior = _safe_float(row.get("prior_5m_return_bps"))
        fwd = _safe_float(row.get(fwd_col))
        signal_ts = _safe_int(row.get("signal_ts_ms"))
        if prior is None or fwd is None or signal_ts is None:
            continue
        direction = 0
        if branch == "crowded_long_fade" and prior <= 0:
            direction = -1
        elif branch == "crowded_short_squeeze" and prior >= 0:
            direction = 1
        if direction == 0:
            continue
        gross = direction * fwd
        next_funding = _safe_int(row.get("next_funding_ms"))
        interval_ms = funding_interval_min * 60_000 if funding_interval_min else None
        previous_funding = next_funding - interval_ms if next_funding and interval_ms else None
        is_settlement_window = (
            next_funding is not None
            and abs(next_funding - signal_ts) <= SETTLEMENT_WINDOW_MS
        ) or (
            previous_funding is not None
            and abs(signal_ts - previous_funding) <= SETTLEMENT_WINDOW_MS
        )
        out.append(
            {
                "signal_ts_ms": signal_ts,
                "net_bps": gross - cost_bps,
                "gross_bps": gross,
                "next_funding_ms": next_funding,
                "previous_funding_ms": previous_funding,
                "settlement_window": is_settlement_window,
            }
        )
    return out


def _plateau_check(
    cells: Sequence[Mapping[str, object]],
    best_primary: Mapping[str, object] | None,
) -> dict[str, object]:
    if best_primary is None:
        return {
            "plateau_passed": False,
            "reason": "no_best_primary_cell",
            "neighbor_cells": [],
        }
    try:
        best_z_idx = Z_GRID.index(float(best_primary["z_hi"]))
        best_p_idx = P_GRID.index((float(best_primary["p_hi"]), float(best_primary["p_lo"])))
        best_oi_idx = OI_GRID.index(float(best_primary["oi_min_pct"]))
    except (KeyError, ValueError, TypeError):
        return {
            "plateau_passed": False,
            "reason": "best_cell_grid_coordinates_unavailable",
            "neighbor_cells": [],
        }
    neighbors: list[Mapping[str, object]] = []
    for cell in cells:
        if cell.get("horizon_min") != PRIMARY_HORIZON:
            continue
        if cell.get("symbol") != best_primary.get("symbol"):
            continue
        if cell.get("branch") != best_primary.get("branch"):
            continue
        try:
            z_idx = Z_GRID.index(float(cell["z_hi"]))
            p_idx = P_GRID.index((float(cell["p_hi"]), float(cell["p_lo"])))
            oi_idx = OI_GRID.index(float(cell["oi_min_pct"]))
        except (KeyError, ValueError, TypeError):
            continue
        distance = abs(z_idx - best_z_idx) + abs(p_idx - best_p_idx) + abs(oi_idx - best_oi_idx)
        if distance == 1:
            neighbors.append(cell)
    best_avg = _safe_float(best_primary.get("avg_net_bps"))
    tolerance = max(10.0, abs(best_avg or 0.0) * 0.50)
    passing_neighbors = []
    for cell in neighbors:
        avg = _safe_float(cell.get("avg_net_bps"))
        if avg is None or best_avg is None:
            continue
        if (
            int(cell.get("n_eff") or 0) >= BRANCH_N_EFF_FLOOR
            and avg >= AVG_NET_FLOOR_BPS
            and avg >= best_avg - tolerance
        ):
            passing_neighbors.append(cell)
    return {
        "plateau_passed": len(passing_neighbors) >= 2
        and int(best_primary.get("n_eff") or 0) >= SYMBOL_N_EFF_FLOOR,
        "reason": None if len(passing_neighbors) >= 2 else "insufficient_adjacent_support",
        "neighbor_count": len(neighbors),
        "passing_neighbor_count": len(passing_neighbors),
        "neighbor_cells": [
            {
                "candidate_key": cell.get("candidate_key"),
                "n_eff": cell.get("n_eff"),
                "avg_net_bps": cell.get("avg_net_bps"),
                "psr_0": cell.get("psr_0"),
                "dsr": cell.get("dsr"),
            }
            for cell in sorted(
                neighbors,
                key=lambda c: float(c.get("avg_net_bps") or -1e18),
                reverse=True,
            )[:8]
        ],
    }


def _pbo(candidates: Mapping[str, Mapping[str, float]], *, max_splits: int = 240) -> dict[str, object]:
    days = sorted({day for daily in candidates.values() for day in daily})
    candidate_keys = list(candidates)
    if len(days) < 4 or len(candidate_keys) < 10:
        return {
            "value": None,
            "method": "day_block_cscv",
            "usable_splits": 0,
            "reason": "insufficient_days_or_candidates",
            "day_count": len(days),
            "candidate_count": len(candidate_keys),
        }
    train_size = len(days) // 2
    combo_count = math.comb(len(days), train_size)
    if combo_count <= max_splits:
        combos = list(combinations(days, train_size))
    else:
        rng = random.Random(20260516)
        seen: set[tuple[str, ...]] = set()
        combos = []
        attempts = 0
        while len(combos) < max_splits and attempts < max_splits * 20:
            train = tuple(sorted(rng.sample(days, train_size)))
            if train not in seen:
                seen.add(train)
                combos.append(train)
            attempts += 1
    splits = [(set(train), set(days) - set(train)) for train in combos]
    bad = 0
    usable = 0
    for train_days, test_days in splits:
        train_scores: dict[str, float] = {}
        test_scores: dict[str, float] = {}
        for key, daily in candidates.items():
            train_vals = [daily[d] for d in train_days if d in daily]
            test_vals = [daily[d] for d in test_days if d in daily]
            if train_vals and test_vals:
                train_scores[key] = statistics.mean(train_vals)
                test_scores[key] = statistics.mean(test_vals)
        if len(train_scores) < 10 or len(test_scores) < 10:
            continue
        best = max(train_scores, key=train_scores.get)
        ranked = sorted(test_scores.values())
        best_test = test_scores.get(best)
        if best_test is None:
            continue
        median_rank = ranked[len(ranked) // 2]
        bad += int(best_test < median_rank)
        usable += 1
    if usable == 0:
        return {
            "value": None,
            "method": "day_block_cscv",
            "usable_splits": 0,
            "reason": "no_usable_cscv_splits",
            "day_count": len(days),
            "candidate_count": len(candidate_keys),
            "requested_splits": len(splits),
        }
    return {
        "value": bad / usable,
        "method": "day_block_cscv",
        "usable_splits": usable,
        "day_count": len(days),
        "candidate_count": len(candidate_keys),
        "requested_splits": len(splits),
        "train_day_count": train_size,
        "test_day_count": len(days) - train_size,
        "reason": None,
    }


def compute_stage0r(
    rows: Sequence[Mapping[str, object]],
    *,
    k_prior: int,
    cost_bps: float,
) -> dict[str, object]:
    symbols = sorted({str(r.get("symbol")) for r in rows if r.get("symbol")})
    rows_by_symbol: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        symbol = str(row.get("symbol") or "")
        if symbol:
            rows_by_symbol[symbol].append(row)
    k_new_actual = len(symbols) * len(BRANCHES) * len(Z_GRID) * len(P_GRID) * len(OI_GRID) * len(HORIZONS)
    k_new = max(K_NEW_MIN, k_new_actual)
    k_total = int(k_prior) + k_new
    intervals = _funding_interval_by_symbol(rows)

    missing = Counter()
    for row in rows:
        if _safe_int(row.get("funding_age_ms")) is None:
            missing["funding_missing"] += 1
        elif int(row["funding_age_ms"]) > EXCLUDE_AGE_MS:
            missing["funding_stale_excluded"] += 1
        elif int(row["funding_age_ms"]) > WARN_AGE_MS:
            missing["funding_warn_age"] += 1
        if _safe_int(row.get("oi_age_ms")) is None:
            missing["oi_missing"] += 1
        elif int(row["oi_age_ms"]) > EXCLUDE_AGE_MS:
            missing["oi_stale_excluded"] += 1
        elif int(row["oi_age_ms"]) > WARN_AGE_MS:
            missing["oi_warn_age"] += 1

    cells: list[dict[str, object]] = []
    daily_for_pbo: dict[str, dict[str, float]] = {}
    pooled_by_param: dict[tuple[float, float, float, float, int], list[float]] = defaultdict(list)
    pooled_all_by_param: dict[tuple[float, float, float, float, int], list[float]] = defaultdict(list)
    pooled_gross_by_param: dict[tuple[float, float, float, float, int], list[float]] = defaultdict(list)
    branch_by_param: dict[tuple[str, float, float, float, float, int], list[float]] = defaultdict(list)
    per_symbol_by_param: dict[tuple[str, str, float, float, float, float, int], list[float]] = defaultdict(list)
    per_symbol_sigs_by_param: dict[tuple[str, str, float, float, float, float, int], list[dict[str, object]]] = defaultdict(list)
    settlement_counts_by_param: dict[tuple[float, float, float, float, int], Counter] = defaultdict(Counter)

    for symbol in symbols:
        for branch in BRANCHES:
            for z_hi in Z_GRID:
                for p_hi, p_lo in P_GRID:
                    for oi_min in OI_GRID:
                        for horizon in HORIZONS:
                            key = CandidateKey(symbol, branch, z_hi, p_hi, p_lo, oi_min, horizon)
                            sigs_all = _signal_rows(
                                rows_by_symbol[symbol],
                                key=key,
                                cost_bps=cost_bps,
                                funding_interval_min=intervals.get(symbol),
                            )
                            sigs = [s for s in sigs_all if not bool(s.get("settlement_window"))]
                            values = [float(s["net_bps"]) for s in sigs]
                            gross_values = [float(s["gross_bps"]) for s in sigs]
                            n = len(values)
                            n_eff = _n_eff(n, horizon)
                            avg_net = statistics.mean(values) if values else None
                            avg_gross = statistics.mean(gross_values) if gross_values else None
                            psr = psr_bailey_ldp(values)
                            dsr = dsr_with_k(values, k_total)
                            ci = block_bootstrap_ci(values)
                            days = Counter(_day_bucket(int(s["signal_ts_ms"])) for s in sigs)
                            cycles = Counter(str(s.get("next_funding_ms")) for s in sigs if s.get("next_funding_ms"))
                            max_day_share = max(days.values()) / n if n and days else 0.0
                            max_cycle_share = max(cycles.values()) / n if n and cycles else 0.0
                            cell = {
                                "candidate_key": key.label(),
                                "symbol": symbol,
                                "branch": branch,
                                "z_hi": z_hi,
                                "p_hi": p_hi,
                                "p_lo": p_lo,
                                "oi_min_pct": oi_min,
                                "horizon_min": horizon,
                                "n": n,
                                "n_eff": n_eff,
                                "avg_gross_bps": avg_gross,
                                "avg_net_bps": avg_net,
                                "psr_0": psr,
                                "dsr": dsr,
                                "bootstrap_ci_95": ci,
                                "funding_cycles": len(cycles),
                                "max_day_share": max_day_share,
                                "max_funding_cycle_share": max_cycle_share,
                                "funding_interval_min": intervals.get(symbol),
                            }
                            cells.append(cell)
                            if values:
                                by_day: dict[str, list[float]] = defaultdict(list)
                                for sig, value in zip(sigs, values):
                                    by_day[_day_bucket(int(sig["signal_ts_ms"]))].append(value)
                                daily_for_pbo[key.label()] = {
                                    day: statistics.mean(vals) for day, vals in by_day.items()
                                }
                            if horizon == PRIMARY_HORIZON:
                                param_key = (z_hi, p_hi, p_lo, oi_min, horizon)
                                branch_param_key = (branch, z_hi, p_hi, p_lo, oi_min, horizon)
                                symbol_param_key = (symbol, branch, z_hi, p_hi, p_lo, oi_min, horizon)
                                pooled_all_by_param[param_key].extend(
                                    float(s["net_bps"]) for s in sigs_all
                                )
                                pooled_by_param[param_key].extend(values)
                                pooled_gross_by_param[param_key].extend(gross_values)
                                branch_by_param[branch_param_key].extend(values)
                                per_symbol_by_param[symbol_param_key].extend(values)
                                per_symbol_sigs_by_param[symbol_param_key].extend(sigs)
                                settlement_counts_by_param[param_key]["primary_signals"] += len(sigs_all)
                                settlement_counts_by_param[param_key][
                                    "primary_settlement_window_signals"
                                ] += sum(
                                    1 for s in sigs_all if bool(s.get("settlement_window"))
                                )

    pbo_meta = _pbo(daily_for_pbo)
    pbo = pbo_meta.get("value")
    source_mode = _source_mode(rows)
    panel_metadata = _panel_metadata(rows, symbols)

    baseline_values_by_branch: dict[str, list[float]] = {}
    baseline_all_values: list[float] = []
    for branch in BRANCHES:
        branch_values: list[float] = []
        for symbol in symbols:
            baseline_sigs = _baseline_signal_rows(
                rows_by_symbol[symbol],
                branch=branch,
                cost_bps=cost_bps,
                funding_interval_min=intervals.get(symbol),
            )
            branch_values.extend(
                float(sig["net_bps"])
                for sig in baseline_sigs
                if not bool(sig.get("settlement_window"))
            )
        baseline_values_by_branch[branch] = branch_values
        baseline_all_values.extend(branch_values)
    baseline_summary_by_branch = {
        branch: _summary_stats(
            values,
            horizon_min=PRIMARY_HORIZON,
            k_total=k_total,
            include_bootstrap=False,
        )
        for branch, values in baseline_values_by_branch.items()
    }
    baseline_all = _summary_stats(
        baseline_all_values,
        horizon_min=PRIMARY_HORIZON,
        k_total=k_total,
        include_bootstrap=False,
    )

    def _param_key_from_cell(cell: Mapping[str, object]) -> tuple[float, float, float, float, int]:
        return (
            float(cell["z_hi"]),
            float(cell["p_hi"]),
            float(cell["p_lo"]),
            float(cell["oi_min_pct"]),
            PRIMARY_HORIZON,
        )

    def _ci_lower(value: object) -> float | None:
        if isinstance(value, (list, tuple)) and value:
            return _safe_float(value[0])
        return None

    def _build_artifacts(
        cell: Mapping[str, object] | None,
        *,
        include_bootstrap: bool,
    ) -> dict[str, object]:
        if cell is None:
            pooled_empty = _summary_stats(
                [],
                horizon_min=PRIMARY_HORIZON,
                k_total=k_total,
                include_bootstrap=include_bootstrap,
            )
            return {
                "param_key": None,
                "pooled_primary": pooled_empty,
                "branch_summary": {
                    branch: _summary_stats(
                        [],
                        horizon_min=PRIMARY_HORIZON,
                        k_total=k_total,
                        include_bootstrap=False,
                    )
                    for branch in BRANCHES
                },
                "per_symbol_breakdown": [],
                "settlement_window": {
                    "window_minutes": SETTLEMENT_WINDOW_MS // 60_000,
                    "primary_signals": 0,
                    "primary_settlement_window_signals": 0,
                    "primary_settlement_window_share": 0.0,
                    "eligibility_uses": "primary_excluding_settlement_window",
                },
                "baseline_lift": {
                    "baseline": "prior_5m_direction_without_funding_or_oi_confirmation",
                    "pooled_baseline": baseline_all,
                    "stage0r_minus_baseline_avg_net_bps": None,
                    "branches": baseline_summary_by_branch,
                },
                "execution_cost_model": {
                    "mode": "flat_conservative_cost_bps",
                    "cost_bps": cost_bps,
                    "maker_share": None,
                    "taker_share": None,
                    "maker_taker_source": "not_available_in_stage0r_replay_rows",
                    "cost_edge_ratio": None,
                },
                "plateau_check": _plateau_check(cells, None),
            }

        param_key = _param_key_from_cell(cell)
        pooled_values = list(pooled_by_param.get(param_key, []))
        pooled_all_values = list(pooled_all_by_param.get(param_key, []))
        pooled_gross_values = list(pooled_gross_by_param.get(param_key, []))
        pooled_summary = _summary_stats(
            pooled_values,
            horizon_min=PRIMARY_HORIZON,
            k_total=k_total,
            include_bootstrap=include_bootstrap,
        )

        branch_summary: dict[str, dict[str, object]] = {}
        for branch in BRANCHES:
            values = list(branch_by_param.get((branch, *param_key), []))
            branch_summary[branch] = _summary_stats(
                values,
                horizon_min=PRIMARY_HORIZON,
                k_total=k_total,
                include_bootstrap=False,
            )

        per_symbol_breakdown = []
        for symbol in symbols:
            total_values: list[float] = []
            total_sigs: list[dict[str, object]] = []
            branch_details: dict[str, dict[str, object]] = {}
            for branch in BRANCHES:
                symbol_param_key = (symbol, branch, *param_key)
                values = list(per_symbol_by_param.get(symbol_param_key, []))
                sigs = list(per_symbol_sigs_by_param.get(symbol_param_key, []))
                total_values.extend(values)
                total_sigs.extend(sigs)
                branch_details[branch] = _summary_stats(
                    values,
                    horizon_min=PRIMARY_HORIZON,
                    include_bootstrap=False,
                )
            days = Counter(_day_bucket(int(s["signal_ts_ms"])) for s in total_sigs)
            cycles = Counter(str(s.get("next_funding_ms")) for s in total_sigs if s.get("next_funding_ms"))
            per_symbol_breakdown.append(
                {
                    "symbol": symbol,
                    "n": len(total_values),
                    "n_eff": _n_eff(len(total_values), PRIMARY_HORIZON),
                    "avg_net_bps": statistics.mean(total_values) if total_values else None,
                    "funding_cycles": len(cycles),
                    "max_day_share": (
                        max(days.values()) / len(total_sigs) if total_sigs and days else 0.0
                    ),
                    "max_funding_cycle_share": (
                        max(cycles.values()) / len(total_sigs) if total_sigs and cycles else 0.0
                    ),
                    "funding_interval_min": intervals.get(symbol),
                    "branches": branch_details,
                }
            )

        settlement_counts = settlement_counts_by_param.get(param_key, Counter())
        primary_signals = int(settlement_counts.get("primary_signals", 0))
        primary_settlement = int(settlement_counts.get("primary_settlement_window_signals", 0))
        including_settlement = _summary_stats(
            pooled_all_values,
            horizon_min=PRIMARY_HORIZON,
            k_total=k_total,
            include_bootstrap=False,
        )
        excluding_settlement = _summary_stats(
            pooled_values,
            horizon_min=PRIMARY_HORIZON,
            k_total=k_total,
            include_bootstrap=False,
        )
        settlement_summary = {
            "window_minutes": SETTLEMENT_WINDOW_MS // 60_000,
            "primary_signals": primary_signals,
            "primary_settlement_window_signals": primary_settlement,
            "primary_settlement_window_share": (
                primary_settlement / primary_signals if primary_signals else 0.0
            ),
            "eligibility_uses": "primary_excluding_settlement_window",
            "primary_including_settlement_window": including_settlement,
            "primary_excluding_settlement_window": excluding_settlement,
            "adverse_drag_sensitivity_bps": (
                float(excluding_settlement["avg_net_bps"])
                - float(including_settlement["avg_net_bps"])
                if excluding_settlement.get("avg_net_bps") is not None
                and including_settlement.get("avg_net_bps") is not None
                else None
            ),
            "funding_interval_min_by_symbol": dict(intervals),
            "funding_interval_source": "inferred_from_next_funding_ms",
        }

        baseline_by_branch: dict[str, dict[str, object]] = {}
        for branch in BRANCHES:
            baseline_summary = dict(baseline_summary_by_branch.get(branch, {}))
            branch_avg = branch_summary.get(branch, {}).get("avg_net_bps")
            baseline_avg = baseline_summary.get("avg_net_bps")
            baseline_summary["lift_vs_stage0r_branch_bps"] = (
                float(branch_avg) - float(baseline_avg)
                if branch_avg is not None and baseline_avg is not None
                else None
            )
            baseline_by_branch[branch] = baseline_summary
        baseline_lift = {
            "baseline": "prior_5m_direction_without_funding_or_oi_confirmation",
            "pooled_baseline": baseline_all,
            "stage0r_minus_baseline_avg_net_bps": (
                float(pooled_summary["avg_net_bps"]) - float(baseline_all["avg_net_bps"])
                if pooled_summary.get("avg_net_bps") is not None
                and baseline_all.get("avg_net_bps") is not None
                else None
            ),
            "branches": baseline_by_branch,
        }

        gross_mean = statistics.mean(pooled_gross_values) if pooled_gross_values else None
        cost_edge_ratio = (
            abs(cost_bps) / abs(gross_mean)
            if gross_mean is not None and gross_mean != 0
            else None
        )
        execution_cost_model = {
            "mode": "flat_conservative_cost_bps",
            "cost_bps": cost_bps,
            "maker_share": None,
            "taker_share": None,
            "maker_taker_source": "not_available_in_stage0r_replay_rows",
            "cost_edge_ratio": cost_edge_ratio,
            "gross_edge_mean_bps": gross_mean,
        }

        return {
            "param_key": param_key,
            "pooled_primary": pooled_summary,
            "branch_summary": branch_summary,
            "per_symbol_breakdown": per_symbol_breakdown,
            "settlement_window": settlement_summary,
            "baseline_lift": baseline_lift,
            "execution_cost_model": execution_cost_model,
            "plateau_check": _plateau_check(cells, cell),
        }

    def _candidate_fail_reasons(
        cell: Mapping[str, object] | None,
        artifacts: Mapping[str, object],
        *,
        include_bootstrap: bool,
    ) -> list[str]:
        if cell is None:
            return ["no primary-horizon signals"]

        reasons: list[str] = []
        pooled_summary = artifacts["pooled_primary"]  # type: ignore[index]
        branch_summary = artifacts["branch_summary"]  # type: ignore[index]
        baseline_lift = artifacts["baseline_lift"]  # type: ignore[index]
        cost_model = artifacts["execution_cost_model"]  # type: ignore[index]
        plateau = artifacts["plateau_check"]  # type: ignore[index]
        selected_branch = str(cell["branch"])

        if len(symbols) < MIN_STAGE0R_SYMBOLS:
            reasons.append("symbol_count < 25")
        if source_mode == "mixed":
            reasons.append("mixed funding source modes")
        elif source_mode == "unknown":
            reasons.append("source_mode unknown")
        if int(cell.get("n_eff") or 0) < SYMBOL_N_EFF_FLOOR:
            reasons.append("symbol n_eff < 100")
        if int(branch_summary.get(selected_branch, {}).get("n_eff", 0)) < BRANCH_N_EFF_FLOOR:
            reasons.append("branch n_eff < 50")
        if int(pooled_summary.get("n_eff", 0)) < POOLED_N_EFF_FLOOR:
            reasons.append("pooled n_eff < 300")
        if int(cell.get("funding_cycles") or 0) < MIN_FUNDING_CYCLES:
            reasons.append("funding cycles < 14")
        if cell.get("funding_interval_min") is None:
            reasons.append("funding interval unavailable")
        if float(cell.get("max_day_share") or 0.0) > MAX_DAY_OR_CYCLE_SHARE:
            reasons.append("single-day share > 25%")
        if float(cell.get("max_funding_cycle_share") or 0.0) > MAX_DAY_OR_CYCLE_SHARE:
            reasons.append("single funding-cycle share > 25%")
        avg_net = _safe_float(cell.get("avg_net_bps"))
        if avg_net is None or avg_net < AVG_NET_FLOOR_BPS:
            reasons.append("avg_net_bps < +15")
        psr = _safe_float(cell.get("psr_0"))
        if psr is None or psr < PSR_THRESHOLD:
            reasons.append("PSR(0) < 0.95")
        dsr = _safe_float(cell.get("dsr"))
        if dsr is None or dsr < DSR_THRESHOLD:
            reasons.append("DSR < 0.95")
        pbo_value = _safe_float(pbo)
        if pbo_value is None or pbo_value > PBO_THRESHOLD:
            reasons.append("PBO missing or > 0.20")
        if include_bootstrap:
            lower_60m = _ci_lower(pooled_summary.get("bootstrap_ci_95_60m"))
            lower_8h = _ci_lower(pooled_summary.get("bootstrap_ci_95_8h"))
            if lower_60m is None or lower_60m <= 0:
                reasons.append("pooled 60m bootstrap lower bound <= 0")
            if lower_8h is None or lower_8h <= 0:
                reasons.append("pooled 8h bootstrap lower bound <= 0")
        if not bool(plateau.get("plateau_passed")):
            reasons.append("plateau check failed")
        baseline_delta = _safe_float(baseline_lift.get("stage0r_minus_baseline_avg_net_bps"))
        if baseline_delta is None or baseline_delta <= BASELINE_LIFT_FLOOR_BPS:
            reasons.append("baseline lift <= 0")
        cost_edge_ratio = _safe_float(cost_model.get("cost_edge_ratio"))
        if cost_edge_ratio is None or cost_edge_ratio >= COST_EDGE_RATIO_MAX:
            reasons.append("cost_edge_ratio >= 0.80")
        if int(pooled_summary.get("n") or 0) <= 0 or int(cell.get("n") or 0) <= 0:
            reasons.append("no net values")
        return reasons

    primary_cells = [
        c for c in cells if c["horizon_min"] == PRIMARY_HORIZON and c["avg_net_bps"] is not None
    ]
    ranked_candidates: list[dict[str, object]] = []
    for cell in primary_cells:
        cheap_artifacts = _build_artifacts(cell, include_bootstrap=False)
        cheap_reasons = _candidate_fail_reasons(
            cell,
            cheap_artifacts,
            include_bootstrap=False,
        )
        pooled_summary = cheap_artifacts["pooled_primary"]  # type: ignore[index]
        branch_summary = cheap_artifacts["branch_summary"]  # type: ignore[index]
        ranked_candidates.append(
            {
                "cell": cell,
                "cheap_fail_reasons": cheap_reasons,
                "cheap_fail_count": len(cheap_reasons),
                "pooled_n_eff": int(pooled_summary.get("n_eff") or 0),
                "pooled_avg_net_bps": pooled_summary.get("avg_net_bps"),
                "branch_n_eff": int(
                    branch_summary.get(str(cell["branch"]), {}).get("n_eff", 0)
                ),
            }
        )
    ranked_candidates.sort(
        key=lambda item: (
            int(item["cheap_fail_count"]),
            -int(item["pooled_n_eff"]),
            -int(item["branch_n_eff"]),
            -float(item["cell"].get("avg_net_bps") or -1e18),  # type: ignore[union-attr]
        )
    )

    selected_cell: dict[str, object] | None = None
    selected_artifacts = _build_artifacts(None, include_bootstrap=True)
    reasons: list[str] = ["no primary-horizon signals"]
    selection_basis = "no_primary_horizon_signals"

    for item in ranked_candidates:
        if item["cheap_fail_reasons"]:
            break
        cell = item["cell"]  # type: ignore[assignment]
        final_artifacts = _build_artifacts(cell, include_bootstrap=True)  # type: ignore[arg-type]
        final_reasons = _candidate_fail_reasons(
            cell,  # type: ignore[arg-type]
            final_artifacts,
            include_bootstrap=True,
        )
        if not final_reasons:
            selected_cell = dict(cell)  # type: ignore[arg-type]
            selected_artifacts = final_artifacts
            reasons = final_reasons
            selection_basis = "eligible_candidate"
            break

    if selected_cell is None and ranked_candidates:
        item = ranked_candidates[0]
        cell = item["cell"]  # type: ignore[assignment]
        selected_cell = dict(cell)  # type: ignore[arg-type]
        selected_artifacts = _build_artifacts(cell, include_bootstrap=True)  # type: ignore[arg-type]
        reasons = _candidate_fail_reasons(
            cell,  # type: ignore[arg-type]
            selected_artifacts,
            include_bootstrap=True,
        )
        selection_basis = "least_failed_candidate"

    eligible = not reasons
    best_primary = selected_cell
    if best_primary is not None:
        best_primary["selection_basis"] = selection_basis
        best_primary["selection_fail_reasons"] = list(reasons)
        pooled_for_best = selected_artifacts["pooled_primary"]  # type: ignore[index]
        best_primary["pooled_n_eff_for_param"] = pooled_for_best.get("n_eff")
        best_primary["pooled_avg_net_bps_for_param"] = pooled_for_best.get("avg_net_bps")

    pooled = selected_artifacts["pooled_primary"]  # type: ignore[index]
    branch_summary = selected_artifacts["branch_summary"]  # type: ignore[index]
    per_symbol_breakdown = selected_artifacts["per_symbol_breakdown"]  # type: ignore[index]
    settlement_summary = selected_artifacts["settlement_window"]  # type: ignore[index]
    baseline_lift = selected_artifacts["baseline_lift"]  # type: ignore[index]
    execution_cost_model = selected_artifacts["execution_cost_model"]  # type: ignore[index]
    plateau = selected_artifacts["plateau_check"]  # type: ignore[index]
    top_primary_cells = []
    for item in ranked_candidates[:20]:
        cell = dict(item["cell"])  # type: ignore[arg-type]
        cell["selection_fail_reasons_without_bootstrap"] = list(item["cheap_fail_reasons"])  # type: ignore[arg-type]
        cell["cheap_fail_count"] = item["cheap_fail_count"]
        cell["pooled_n_eff_for_param"] = item["pooled_n_eff"]
        cell["pooled_avg_net_bps_for_param"] = item["pooled_avg_net_bps"]
        cell["branch_n_eff_for_param"] = item["branch_n_eff"]
        top_primary_cells.append(cell)

    exclusions = {
        "funding_missing": missing.get("funding_missing", 0),
        "funding_stale_excluded": missing.get("funding_stale_excluded", 0),
        "funding_warn_age": missing.get("funding_warn_age", 0),
        "oi_missing": missing.get("oi_missing", 0),
        "oi_stale_excluded": missing.get("oi_stale_excluded", 0),
        "oi_warn_age": missing.get("oi_warn_age", 0),
    }

    return {
        "strategy_variant": STRATEGY_VARIANT,
        "alpha_source_id": ALPHA_SOURCE_ID,
        "funding_attribution_mode": "excluded",
        "source_mode": source_mode,
        "cost_bps": cost_bps,
        "k_prior": int(k_prior),
        "k_new": k_new,
        "k_new_actual": k_new_actual,
        "k_new_min": K_NEW_MIN,
        "k_new_floor_applied": k_new > k_new_actual,
        "k_total": k_total,
        "row_count": len(rows),
        "symbol_count": len(symbols),
        "min_stage0r_symbols": MIN_STAGE0R_SYMBOLS,
        "panel_metadata": panel_metadata,
        "exclusions": exclusions,
        "pooled_primary": pooled,
        "branch_summary": branch_summary,
        "per_symbol_breakdown": per_symbol_breakdown,
        "settlement_window": settlement_summary,
        "baseline_lift": baseline_lift,
        "execution_cost_model": execution_cost_model,
        "pbo": pbo,
        "pbo_metadata": pbo_meta,
        "plateau_check": plateau,
        "best_primary_cell": best_primary,
        "top_primary_cells": top_primary_cells,
        "selection_policy": (
            "prefer zero-fail primary candidate after fixed-parameter pooled/branch/symbol "
            "checks; otherwise report the least-failed diagnostic candidate"
        ),
        "eligible_for_demo_canary": eligible,
        "eligibility_fail_reasons": reasons,
    }


def grid_cell_count(symbol_count: int) -> int:
    return symbol_count * len(BRANCHES) * len(Z_GRID) * len(P_GRID) * len(OI_GRID) * len(HORIZONS)


def default_symbols_from_rows(rows: Iterable[Mapping[str, object]]) -> tuple[str, ...]:
    return tuple(sorted({str(r.get("symbol")) for r in rows if r.get("symbol")}))
