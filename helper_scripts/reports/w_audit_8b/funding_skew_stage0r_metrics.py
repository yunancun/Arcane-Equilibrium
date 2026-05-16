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
DEFAULT_SWEEP_Z_CELLS = (1.0, 1.2, 1.5, 2.0)
P_GRID = ((0.85, 0.15), (0.90, 0.10), (0.95, 0.05))
OI_GRID = (1.0, 2.0, 3.0)
HORIZONS = (15, 30, 60)
PRIMARY_HORIZON = 30
BRANCHES = ("crowded_long_fade", "crowded_short_squeeze")
STRATEGY_VARIANT = "funding_skew_directional.v0_2"
SWEEP_STRATEGY_VARIANT = "funding_skew_directional.v0_3"
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
K_NEW_MIN_V03 = (
    MIN_STAGE0R_SYMBOLS
    * len(BRANCHES)
    * len(DEFAULT_SWEEP_Z_CELLS)
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


def _k_new_min_for_z_grid(z_grid: Sequence[float]) -> int:
    return (
        MIN_STAGE0R_SYMBOLS
        * len(BRANCHES)
        * len(z_grid)
        * len(P_GRID)
        * len(OI_GRID)
        * len(HORIZONS)
    )


def wilson_ci_95(n: int, n_eff: int) -> tuple[float, float] | None:
    if n <= 0 or n_eff < 0 or n_eff > n:
        return None
    z = 1.96
    p_hat = n_eff / n
    z_sq = z * z
    denom = 1.0 + z_sq / n
    center = (p_hat + z_sq / (2 * n)) / denom
    inner = p_hat * (1.0 - p_hat) / n + z_sq / (4 * n * n)
    if inner < 0.0:
        return None
    margin = z * math.sqrt(inner) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


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
    *,
    z_grid: Sequence[float] | None = None,
) -> dict[str, object]:
    active_z_grid = tuple(float(z) for z in (z_grid if z_grid is not None else Z_GRID))
    if best_primary is None:
        return {
            "plateau_passed": False,
            "reason": "no_best_primary_cell",
            "neighbor_cells": [],
        }
    try:
        best_z_idx = active_z_grid.index(float(best_primary["z_hi"]))
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
            z_idx = active_z_grid.index(float(cell["z_hi"]))
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
    z_grid: Sequence[float] | None = None,
    k_new_min_floor: int | None = None,
    include_branch_best_primary: bool = False,
) -> dict[str, object]:
    active_z_grid = tuple(float(z) for z in (z_grid if z_grid is not None else Z_GRID))
    if not active_z_grid:
        raise ValueError("z_grid must contain at least one threshold")
    symbols = sorted({str(r.get("symbol")) for r in rows if r.get("symbol")})
    rows_by_symbol: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        symbol = str(row.get("symbol") or "")
        if symbol:
            rows_by_symbol[symbol].append(row)
    k_new_actual = (
        len(symbols)
        * len(BRANCHES)
        * len(active_z_grid)
        * len(P_GRID)
        * len(OI_GRID)
        * len(HORIZONS)
    )
    k_new_min = _k_new_min_for_z_grid(active_z_grid)
    if k_new_min_floor is not None:
        k_new_min = max(k_new_min, int(k_new_min_floor))
    k_new = max(k_new_min, k_new_actual)
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
    branch_gross_by_param: dict[tuple[str, float, float, float, float, int], list[float]] = defaultdict(list)
    branch_sigs_by_param: dict[tuple[str, float, float, float, float, int], list[dict[str, object]]] = defaultdict(list)
    per_symbol_by_param: dict[tuple[str, str, float, float, float, float, int], list[float]] = defaultdict(list)
    per_symbol_sigs_by_param: dict[tuple[str, str, float, float, float, float, int], list[dict[str, object]]] = defaultdict(list)
    settlement_counts_by_param: dict[tuple[float, float, float, float, int], Counter] = defaultdict(Counter)

    for symbol in symbols:
        for branch in BRANCHES:
            for z_hi in active_z_grid:
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
                                branch_gross_by_param[branch_param_key].extend(gross_values)
                                branch_sigs_by_param[branch_param_key].extend(sigs)
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
                "plateau_check": _plateau_check(cells, None, z_grid=active_z_grid),
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
            gross_values = list(branch_gross_by_param.get((branch, *param_key), []))
            sigs = list(branch_sigs_by_param.get((branch, *param_key), []))
            days = Counter(_day_bucket(int(s["signal_ts_ms"])) for s in sigs)
            cycles = Counter(str(s.get("next_funding_ms")) for s in sigs if s.get("next_funding_ms"))
            branch_summary[branch] = _summary_stats(
                values,
                horizon_min=PRIMARY_HORIZON,
                k_total=k_total,
                include_bootstrap=include_bootstrap,
            )
            branch_summary[branch].update(
                {
                    "avg_gross_bps": statistics.mean(gross_values) if gross_values else None,
                    "funding_cycles": len(cycles),
                    "max_day_share": max(days.values()) / len(sigs) if sigs and days else 0.0,
                    "max_funding_cycle_share": (
                        max(cycles.values()) / len(sigs) if sigs and cycles else 0.0
                    ),
                }
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
                days = Counter(_day_bucket(int(s["signal_ts_ms"])) for s in sigs)
                cycles = Counter(str(s.get("next_funding_ms")) for s in sigs if s.get("next_funding_ms"))
                branch_details[branch].update(
                    {
                        "funding_cycles": len(cycles),
                        "max_day_share": max(days.values()) / len(sigs) if sigs and days else 0.0,
                        "max_funding_cycle_share": (
                            max(cycles.values()) / len(sigs) if sigs and cycles else 0.0
                        ),
                    }
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
            "plateau_check": _plateau_check(cells, cell, z_grid=active_z_grid),
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
    branch_best_primary_cells = []
    branch_best_primary_artifacts = []
    if include_branch_best_primary:
        for branch in BRANCHES:
            branch_item = next(
                (
                    item
                    for item in ranked_candidates
                    if isinstance(item.get("cell"), Mapping)
                    and item["cell"].get("branch") == branch  # type: ignore[index]
                ),
                None,
            )
            if branch_item is None:
                branch_best_primary_cells.append(
                    {
                        "branch": branch,
                        "candidate_key": None,
                        "selection_fail_reasons_without_bootstrap": ["no primary-horizon signals"],
                    }
                )
                branch_best_primary_artifacts.append(
                    {
                        "branch": branch,
                        "best_primary_cell": None,
                        "branch_summary": _summary_stats(
                            [],
                            horizon_min=PRIMARY_HORIZON,
                            k_total=k_total,
                            include_bootstrap=True,
                        ),
                        "per_symbol_breakdown": [],
                        "plateau_check": _plateau_check(cells, None, z_grid=active_z_grid),
                        "selection_fail_reasons_without_bootstrap": ["no primary-horizon signals"],
                    }
                )
                continue
            cell = dict(branch_item["cell"])  # type: ignore[arg-type]
            cell["selection_fail_reasons_without_bootstrap"] = list(
                branch_item["cheap_fail_reasons"]  # type: ignore[index]
            )
            cell["cheap_fail_count"] = branch_item["cheap_fail_count"]
            cell["pooled_n_eff_for_param"] = branch_item["pooled_n_eff"]
            cell["pooled_avg_net_bps_for_param"] = branch_item["pooled_avg_net_bps"]
            cell["branch_n_eff_for_param"] = branch_item["branch_n_eff"]
            branch_best_primary_cells.append(cell)
            artifacts = _build_artifacts(cell, include_bootstrap=True)
            artifact_branch_summary = artifacts.get("branch_summary")
            branch_summary_for_best = (
                dict(artifact_branch_summary.get(branch, {}))  # type: ignore[union-attr]
                if isinstance(artifact_branch_summary, Mapping)
                else {}
            )
            per_symbol_branch_rows = []
            for item in artifacts.get("per_symbol_breakdown", []):  # type: ignore[union-attr]
                if not isinstance(item, Mapping):
                    continue
                branch_details = item.get("branches") if isinstance(item.get("branches"), Mapping) else {}
                detail = branch_details.get(branch, {}) if isinstance(branch_details, Mapping) else {}
                if not isinstance(detail, Mapping):
                    detail = {}
                per_symbol_branch_rows.append(
                    {
                        "symbol": item.get("symbol"),
                        "n": detail.get("n"),
                        "n_eff": detail.get("n_eff"),
                        "avg_net_bps": detail.get("avg_net_bps"),
                        "funding_cycles": detail.get("funding_cycles"),
                        "max_day_share": detail.get("max_day_share"),
                        "max_funding_cycle_share": detail.get("max_funding_cycle_share"),
                    }
                )
            branch_best_primary_artifacts.append(
                {
                    "branch": branch,
                    "best_primary_cell": cell,
                    "branch_summary": branch_summary_for_best,
                    "per_symbol_breakdown": per_symbol_branch_rows,
                    "plateau_check": artifacts.get("plateau_check"),
                    "selection_fail_reasons_without_bootstrap": list(
                        branch_item["cheap_fail_reasons"]  # type: ignore[index]
                    ),
                }
            )

    exclusions = {
        "funding_missing": missing.get("funding_missing", 0),
        "funding_stale_excluded": missing.get("funding_stale_excluded", 0),
        "funding_warn_age": missing.get("funding_warn_age", 0),
        "oi_missing": missing.get("oi_missing", 0),
        "oi_stale_excluded": missing.get("oi_stale_excluded", 0),
        "oi_warn_age": missing.get("oi_warn_age", 0),
    }

    packet = {
        "strategy_variant": STRATEGY_VARIANT,
        "alpha_source_id": ALPHA_SOURCE_ID,
        "funding_attribution_mode": "excluded",
        "source_mode": source_mode,
        "cost_bps": cost_bps,
        "k_prior": int(k_prior),
        "k_new": k_new,
        "k_new_actual": k_new_actual,
        "k_new_min": k_new_min,
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
    if include_branch_best_primary:
        packet["branch_best_primary_cells"] = branch_best_primary_cells
        packet["branch_best_primary_artifacts"] = branch_best_primary_artifacts
    return packet


def _z_cell_id(z_value: float) -> str:
    z_float = float(z_value)
    named = {
        1.0: "z_relaxed",
        1.2: "z_moderate",
        1.5: "z_baseline",
        2.0: "z_strict",
    }.get(round(z_float, 6), "z_custom")
    text = f"{z_float:.1f}" if z_float.is_integer() else f"{z_float:g}"
    suffix = text.replace("-", "neg_").replace(".", "_")
    return f"{named}_z_eq_{suffix}"


def _z_floor_profile(z_cell_id: str) -> dict[str, int]:
    if z_cell_id.startswith("z_strict"):
        return {"symbol": 30, "branch": 15, "pooled": 75}
    return {"symbol": SYMBOL_N_EFF_FLOOR, "branch": BRANCH_N_EFF_FLOOR, "pooled": POOLED_N_EFF_FLOOR}


def _ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if denominator in (None, 0):
        return None
    if numerator is None:
        return None
    return float(numerator) / float(denominator)


def _sweep_branch_fail_reasons(
    *,
    packet: Mapping[str, object],
    z_cell_id: str,
    branch_summary: Mapping[str, object],
    pooled_summary: Mapping[str, object],
    wilson_ci: tuple[float, float] | None,
    symbol_gate: Mapping[str, object],
    plateau_check: Mapping[str, object] | None,
) -> tuple[list[str], bool, bool]:
    floors = _z_floor_profile(z_cell_id)
    reasons: list[str] = []
    if int(packet.get("symbol_count") or 0) < MIN_STAGE0R_SYMBOLS:
        reasons.append("symbol_count < 25")
    source_mode = packet.get("source_mode")
    if source_mode == "mixed":
        reasons.append("mixed funding source modes")
    elif source_mode == "unknown":
        reasons.append("source_mode unknown")
    if int(branch_summary.get("n_eff") or 0) < floors["branch"]:
        reasons.append(f"branch n_eff < {floors['branch']}")
    if int(pooled_summary.get("n_eff") or 0) < floors["pooled"]:
        reasons.append(f"pooled n_eff < {floors['pooled']}")
    if int(symbol_gate.get("symbol_n_eff_floor_fail_count") or 0) > 0:
        reasons.append("per-symbol n_eff floor failed")
    if int(branch_summary.get("funding_cycles") or 0) < MIN_FUNDING_CYCLES:
        reasons.append("funding cycles < 14")
    if float(branch_summary.get("max_day_share") or 0.0) > MAX_DAY_OR_CYCLE_SHARE:
        reasons.append("single-day share > 25%")
    if float(branch_summary.get("max_funding_cycle_share") or 0.0) > MAX_DAY_OR_CYCLE_SHARE:
        reasons.append("single funding-cycle share > 25%")
    avg_net = _safe_float(branch_summary.get("avg_net_bps"))
    if avg_net is None or avg_net < AVG_NET_FLOOR_BPS:
        reasons.append("avg_net_bps < +15")
    psr = _safe_float(branch_summary.get("psr_0"))
    if psr is None or psr < PSR_THRESHOLD:
        reasons.append("PSR(0) < 0.95")
    dsr = _safe_float(branch_summary.get("dsr"))
    if dsr is None or dsr < DSR_THRESHOLD:
        reasons.append("DSR < 0.95")
    pbo = _safe_float(packet.get("pbo"))
    if pbo is None or pbo > PBO_THRESHOLD:
        reasons.append("PBO missing or > 0.20")
    if not isinstance(plateau_check, Mapping) or not bool(plateau_check.get("plateau_passed")):
        reasons.append("plateau check failed")
    if wilson_ci is None or wilson_ci[0] <= 0.0:
        reasons.append("Wilson CI lower <= 0")
    diagnostic_pass = not reasons
    promotion_ready = diagnostic_pass and int(pooled_summary.get("n_eff") or 0) >= POOLED_N_EFF_FLOOR
    return reasons, diagnostic_pass, promotion_ready


def _symbol_floor_gate(
    sweep_per_symbol: Sequence[Mapping[str, object]],
    *,
    z_cell_id: str,
    branch: str,
) -> dict[str, object]:
    rows = [
        row
        for row in sweep_per_symbol
        if row.get("z_cell") == z_cell_id and row.get("branch") == branch
    ]
    fail_rows = [
        row
        for row in rows
        if not bool(row.get("symbol_n_eff_floor_pass"))
    ]
    return {
        "symbol_row_count": len(rows),
        "symbol_n_eff_floor": _z_floor_profile(z_cell_id)["symbol"],
        "symbol_n_eff_floor_pass_count": len(rows) - len(fail_rows),
        "symbol_n_eff_floor_fail_count": len(fail_rows),
        "symbols_below_n_eff_floor": [
            row.get("symbol")
            for row in fail_rows[:10]
        ],
    }


def _build_sweep_per_z_cell(
    per_z_packets: Mapping[str, Mapping[str, object]],
    z_cells: Sequence[float],
    sweep_per_symbol: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    totals_by_cell: dict[str, int] = {}
    for z_value in z_cells:
        z_cell_id = _z_cell_id(z_value)
        packet = per_z_packets[z_cell_id]
        branch_artifacts = {
            str(item.get("branch")): item
            for item in packet.get("branch_best_primary_artifacts", [])
            if isinstance(item, Mapping) and item.get("branch")
        }
        by_branch: dict[str, dict[str, object]] = {}
        total_n = 0
        for branch in BRANCHES:
            artifact = branch_artifacts.get(branch, {})
            summary = artifact.get("branch_summary", {}) if isinstance(artifact, Mapping) else {}
            if not isinstance(summary, Mapping):
                summary = {}
            n = int(summary.get("n") or 0)
            n_eff = int(summary.get("n_eff") or 0)
            total_n += n
            ci = wilson_ci_95(n, n_eff)
            symbol_gate = _symbol_floor_gate(sweep_per_symbol, z_cell_id=z_cell_id, branch=branch)
            plateau = artifact.get("plateau_check") if isinstance(artifact, Mapping) else None
            best_cell = artifact.get("best_primary_cell") if isinstance(artifact, Mapping) else None
            if not isinstance(best_cell, Mapping):
                best_cell = {}
            reasons, diagnostic_pass, promotion_ready = _sweep_branch_fail_reasons(
                packet=packet,
                z_cell_id=z_cell_id,
                branch_summary=summary,
                pooled_summary=summary,
                wilson_ci=ci,
                symbol_gate=symbol_gate,
                plateau_check=plateau if isinstance(plateau, Mapping) else None,
            )
            by_branch[branch] = {
                "candidate_key": best_cell.get("candidate_key"),
                "p_hi": best_cell.get("p_hi"),
                "p_lo": best_cell.get("p_lo"),
                "oi_min_pct": best_cell.get("oi_min_pct"),
                "n_total": n,
                "n_eff": n_eff,
                "avg_gross_bps": summary.get("avg_gross_bps"),
                "avg_net_bps": summary.get("avg_net_bps"),
                "psr_0": summary.get("psr_0"),
                "dsr": summary.get("dsr"),
                "pbo": packet.get("pbo"),
                "bootstrap_ci_95_60m": summary.get("bootstrap_ci_95_60m"),
                "bootstrap_ci_95_8h_funding_cycle": summary.get("bootstrap_ci_95_8h"),
                "wilson_ci_n_to_n_eff": ci,
                "trigger_rate": _ratio(n, packet.get("row_count")),
                "funding_cycles_distinct": summary.get("funding_cycles"),
                "max_day_share": summary.get("max_day_share"),
                "max_funding_cycle_share": summary.get("max_funding_cycle_share"),
                "symbol_gate": symbol_gate,
                "plateau_pass": plateau.get("plateau_passed") if isinstance(plateau, Mapping) else None,
                "eligibility_pass": diagnostic_pass,
                "promotion_ready": promotion_ready,
                "promotion_pending_pooled_n_eff_300": (
                    diagnostic_pass and not promotion_ready and z_cell_id.startswith("z_strict")
                ),
                "eligibility_fail_reasons": reasons,
            }
        totals_by_cell[z_cell_id] = total_n
        out[z_cell_id] = {
            "z_hi": float(z_value),
            "trigger_rate": _ratio(total_n, packet.get("row_count")),
            "trigger_rate_vs_z_baseline_ratio": None,
            "by_branch": by_branch,
        }
    baseline_total = totals_by_cell.get(_z_cell_id(1.5))
    for z_cell_id, total_n in totals_by_cell.items():
        out[z_cell_id]["trigger_rate_vs_z_baseline_ratio"] = _ratio(total_n, baseline_total)
    return out


def _build_sweep_per_symbol(
    per_z_packets: Mapping[str, Mapping[str, object]],
    z_cells: Sequence[float],
    symbols: Sequence[str],
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for z_value in z_cells:
        z_cell_id = _z_cell_id(z_value)
        packet = per_z_packets[z_cell_id]
        branch_artifacts = {
            str(item.get("branch")): item
            for item in packet.get("branch_best_primary_artifacts", [])
            if isinstance(item, Mapping) and item.get("branch")
        }
        by_symbol = {
            str(item.get("symbol")): item
            for item in packet.get("per_symbol_breakdown", [])
            if isinstance(item, Mapping) and item.get("symbol")
        }
        floors = _z_floor_profile(z_cell_id)
        for branch in BRANCHES:
            artifact = branch_artifacts.get(branch, {})
            artifact_rows = {
                str(item.get("symbol")): item
                for item in artifact.get("per_symbol_breakdown", [])  # type: ignore[union-attr]
                if isinstance(item, Mapping) and item.get("symbol")
            } if isinstance(artifact, Mapping) else {}
            for symbol in symbols:
                item = by_symbol.get(symbol, {})
                branches = item.get("branches", {}) if isinstance(item, Mapping) else {}
                summary = branches.get(branch, {}) if isinstance(branches, Mapping) else {}
                artifact_row = artifact_rows.get(symbol)
                if isinstance(artifact_row, Mapping):
                    summary = artifact_row
                if not isinstance(summary, Mapping):
                    summary = {}
                n = int(summary.get("n") or 0)
                n_eff = int(summary.get("n_eff") or 0)
                ci = wilson_ci_95(n, n_eff)
                reasons: list[str] = []
                symbol_n_eff_floor_pass = n_eff >= floors["symbol"]
                cycle_day_floor_pass = True
                if n_eff < floors["symbol"]:
                    reasons.append(f"n_eff < {floors['symbol']}")
                if int(summary.get("funding_cycles") or 0) < MIN_FUNDING_CYCLES:
                    reasons.append("funding cycles < 14")
                    cycle_day_floor_pass = False
                if float(summary.get("max_day_share") or 0.0) > MAX_DAY_OR_CYCLE_SHARE:
                    reasons.append("single-day share > 25%")
                    cycle_day_floor_pass = False
                if float(summary.get("max_funding_cycle_share") or 0.0) > MAX_DAY_OR_CYCLE_SHARE:
                    reasons.append("single funding-cycle share > 25%")
                    cycle_day_floor_pass = False
                avg_net = _safe_float(summary.get("avg_net_bps"))
                if avg_net is None or avg_net < AVG_NET_FLOOR_BPS:
                    reasons.append("avg_net_bps < +15")
                out.append(
                    {
                        "z_cell": z_cell_id,
                        "z_hi": float(z_value),
                        "branch": branch,
                        "symbol": symbol,
                        "n": n,
                        "n_eff": n_eff,
                        "avg_net_bps": summary.get("avg_net_bps"),
                        "wilson_ci_95_n_eff_share": ci,
                        "symbol_n_eff_floor": floors["symbol"],
                        "symbol_n_eff_floor_pass": symbol_n_eff_floor_pass,
                        "cycle_day_floor_pass": cycle_day_floor_pass,
                        "funding_cycles": summary.get("funding_cycles"),
                        "max_day_share": summary.get("max_day_share"),
                        "max_funding_cycle_share": (
                            summary.get("max_funding_cycle_share")
                        ),
                        "per_symbol_pass": not reasons,
                        "per_symbol_fail_reasons": reasons,
                    }
                )
    return out


def _build_best_primary_per_z_branch(
    per_z_packets: Mapping[str, Mapping[str, object]],
    z_cells: Sequence[float],
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for z_value in z_cells:
        z_cell_id = _z_cell_id(z_value)
        packet = per_z_packets[z_cell_id]
        branch_artifacts = {
            str(item.get("branch")): item
            for item in packet.get("branch_best_primary_artifacts", [])
            if isinstance(item, Mapping) and item.get("branch")
        }
        top_cells = [c for c in packet.get("branch_best_primary_cells", []) if isinstance(c, Mapping)]
        if not top_cells:
            top_cells = [c for c in packet.get("top_primary_cells", []) if isinstance(c, Mapping)]
        for branch in BRANCHES:
            artifact = branch_artifacts.get(branch, {})
            best = artifact.get("best_primary_cell") if isinstance(artifact, Mapping) else None
            if not isinstance(best, Mapping):
                branch_cells = [c for c in top_cells if c.get("branch") == branch]
                best = branch_cells[0] if branch_cells else {}
            branch_summary = artifact.get("branch_summary", {}) if isinstance(artifact, Mapping) else {}
            if not isinstance(branch_summary, Mapping):
                branch_summary = {}
            n = int(best.get("n") or 0)
            n_eff = int(best.get("n_eff") or 0)
            ci = wilson_ci_95(n, n_eff)
            plateau = artifact.get("plateau_check") if isinstance(artifact, Mapping) else None
            if not isinstance(plateau, Mapping):
                plateau = {}
            out.append(
                {
                    "z_cell": z_cell_id,
                    "z_hi": float(z_value),
                    "branch": branch,
                    "candidate_key": best.get("candidate_key"),
                    "n": n,
                    "n_eff": n_eff,
                    "avg_net_bps": best.get("avg_net_bps"),
                    "psr_0": best.get("psr_0"),
                    "dsr": best.get("dsr"),
                    "wilson_ci_95_share": ci,
                    "branch_n_total": branch_summary.get("n"),
                    "branch_n_eff": branch_summary.get("n_eff"),
                    "branch_funding_cycles_distinct": branch_summary.get("funding_cycles"),
                    "branch_max_day_share": branch_summary.get("max_day_share"),
                    "branch_max_funding_cycle_share": branch_summary.get("max_funding_cycle_share"),
                    "plateau_neighbors_pass": plateau.get("passing_neighbor_count"),
                    "plateau_threshold_neighbors_min": 2,
                    "plateau_pass": plateau.get("plateau_passed"),
                }
            )
    return out


def _build_sweep_cross_z(
    sweep_per_symbol: Sequence[Mapping[str, object]],
    z_cells: Sequence[float],
    symbols: Sequence[str],
) -> list[dict[str, object]]:
    keyed = {
        (str(row.get("z_cell")), str(row.get("branch")), str(row.get("symbol"))): row
        for row in sweep_per_symbol
    }
    out: list[dict[str, object]] = []
    z_ids = [_z_cell_id(z) for z in z_cells]
    for branch in BRANCHES:
        for symbol in symbols:
            by_z: dict[str, dict[str, object]] = {}
            n_eff_values: list[int] = []
            for z_id in z_ids:
                row = keyed.get((z_id, branch, symbol), {})
                ci = row.get("wilson_ci_95_n_eff_share")
                lower = ci[0] if isinstance(ci, (list, tuple)) and ci else None
                upper = ci[1] if isinstance(ci, (list, tuple)) and len(ci) > 1 else None
                n_eff = int(row.get("n_eff") or 0)
                n_eff_values.append(n_eff)
                by_z[z_id] = {
                    "n": row.get("n"),
                    "n_eff": n_eff,
                    "avg_net_bps": row.get("avg_net_bps"),
                    "wilson_ci_lower": lower,
                    "wilson_ci_upper": upper,
                }
            out.append(
                {
                    "branch": branch,
                    "symbol": symbol,
                    "by_z_cell": by_z,
                    "n_eff_drop_z_relaxed_to_z_strict": (
                        n_eff_values[-1] - n_eff_values[0] if n_eff_values else None
                    ),
                    "monotonic_drop_in_n_eff": all(
                        left > right for left, right in zip(n_eff_values, n_eff_values[1:])
                    ),
                }
            )
    return out


def _decide_sweep_eligibility(sweep_per_z_cell: Mapping[str, Mapping[str, object]]) -> tuple[str, int, int]:
    promotion_ready = 0
    diagnostic_pass = 0
    for z_cell in sweep_per_z_cell.values():
        branches = z_cell.get("by_branch") if isinstance(z_cell, Mapping) else {}
        if not isinstance(branches, Mapping):
            continue
        for branch_data in branches.values():
            if not isinstance(branch_data, Mapping):
                continue
            diagnostic_pass += int(bool(branch_data.get("eligibility_pass")))
            promotion_ready += int(bool(branch_data.get("promotion_ready")))
    if promotion_ready:
        return "ACCEPT", promotion_ready, diagnostic_pass
    if diagnostic_pass:
        return "OPEN", promotion_ready, diagnostic_pass
    return "REJECT", promotion_ready, diagnostic_pass


def compute_stage0r_sweep(
    rows: Sequence[Mapping[str, object]],
    *,
    k_prior: int,
    cost_bps: float,
    z_cells: Sequence[float] | None = None,
) -> dict[str, object]:
    active_z_cells = tuple(float(z) for z in (z_cells if z_cells is not None else DEFAULT_SWEEP_Z_CELLS))
    if not active_z_cells:
        raise ValueError("z_cells must contain at least one threshold")
    symbols = default_symbols_from_rows(rows)
    k_new_actual = (
        len(symbols)
        * len(BRANCHES)
        * len(active_z_cells)
        * len(P_GRID)
        * len(OI_GRID)
        * len(HORIZONS)
    )
    k_new_min = (
        K_NEW_MIN_V03
        if active_z_cells == DEFAULT_SWEEP_Z_CELLS
        else _k_new_min_for_z_grid(active_z_cells)
    )
    k_new = max(k_new_min, k_new_actual)
    k_total = int(k_prior) + k_new

    per_z_packets: dict[str, dict[str, object]] = {}
    for z_value in active_z_cells:
        z_cell_id = _z_cell_id(z_value)
        per_z_packets[z_cell_id] = compute_stage0r(
            rows,
            k_prior=k_prior,
            cost_bps=cost_bps,
            z_grid=(z_value,),
            k_new_min_floor=k_new_min,
            include_branch_best_primary=True,
        )

    baseline_packet = per_z_packets.get(_z_cell_id(1.5)) or next(iter(per_z_packets.values()))
    sweep_per_symbol = _build_sweep_per_symbol(per_z_packets, active_z_cells, symbols)
    sweep_per_z_cell = _build_sweep_per_z_cell(per_z_packets, active_z_cells, sweep_per_symbol)
    best_primary_cell_per_z_branch = _build_best_primary_per_z_branch(per_z_packets, active_z_cells)
    sweep_cross_z_comparison = _build_sweep_cross_z(sweep_per_symbol, active_z_cells, symbols)
    sweep_eligibility, promotion_ready_count, diagnostic_pass_count = _decide_sweep_eligibility(
        sweep_per_z_cell
    )
    eligible_for_demo = promotion_ready_count > 0

    out = dict(baseline_packet)
    out.pop("branch_best_primary_cells", None)
    out.pop("branch_best_primary_artifacts", None)
    out.update(
        {
            "strategy_variant": SWEEP_STRATEGY_VARIANT,
            "k_new": k_new,
            "k_new_actual": k_new_actual,
            "k_new_min": k_new_min,
            "k_new_floor_applied": k_new > k_new_actual,
            "k_total": k_total,
            "eligible_for_demo_canary": eligible_for_demo,
            "sweep_per_z_cell": sweep_per_z_cell,
            "sweep_per_symbol": sweep_per_symbol,
            "best_primary_cell_per_z_branch": best_primary_cell_per_z_branch,
            "sweep_cross_z_comparison": sweep_cross_z_comparison,
            "sweep_meta": {
                "sweep_enabled": True,
                "z_cells": list(active_z_cells),
                "z_cell_ids": [_z_cell_id(z) for z in active_z_cells],
                "k_new_min_v0_3": k_new_min,
                "k_new_actual_v0_3": k_new_actual,
                "k_total_v0_3": k_total,
                "sweep_eligibility": sweep_eligibility,
                "promotion_ready_branch_count": promotion_ready_count,
                "diagnostic_pass_branch_count": diagnostic_pass_count,
            },
        }
    )
    return out


def grid_cell_count(symbol_count: int, z_grid: Sequence[float] | None = None) -> int:
    active_z_grid = tuple(float(z) for z in (z_grid if z_grid is not None else Z_GRID))
    return symbol_count * len(BRANCHES) * len(active_z_grid) * len(P_GRID) * len(OI_GRID) * len(HORIZONS)


def default_symbols_from_rows(rows: Iterable[Mapping[str, object]]) -> tuple[str, ...]:
    return tuple(sorted({str(r.get("symbol")) for r in rows if r.get("symbol")}))
