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

WARN_AGE_MS = 60_000
EXCLUDE_AGE_MS = 300_000
SETTLEMENT_WINDOW_MS = 30 * 60_000
PRIMARY_BOOTSTRAP_BLOCK_SIZE = 12   # 12 根 5m bar = 60m 主檢定 block。
FUNDING_BOOTSTRAP_BLOCK_SIZE = 96   # 96 根 5m bar = 8h funding-cycle 敏感度。
PSR_THRESHOLD = 0.95
DSR_THRESHOLD = 0.95
PBO_THRESHOLD = 0.20
AVG_NET_FLOOR_BPS = 15.0
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
    if modes.get("rest_settled", 0) > modes.get("ws_current", 0):
        return "rest_settled"
    return "ws_current"


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
        is_settlement_window = (
            next_funding is not None
            and abs(next_funding - signal_ts) <= SETTLEMENT_WINDOW_MS
        )
        out.append(
            {
                "signal_ts_ms": signal_ts,
                "net_bps": gross - cost_bps,
                "gross_bps": gross,
                "next_funding_ms": next_funding,
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
        out.append(
            {
                "signal_ts_ms": signal_ts,
                "net_bps": gross - cost_bps,
                "gross_bps": gross,
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


def _pbo(candidates: Mapping[str, Mapping[str, float]], *, embargo_days: int = 7) -> dict[str, object]:
    days = sorted({day for daily in candidates.values() for day in daily})
    candidate_keys = list(candidates)
    if len(days) < 4 or len(candidate_keys) < 10:
        return {
            "value": None,
            "method": "purged_day_walk_forward",
            "embargo_days": embargo_days,
            "usable_splits": 0,
            "reason": "insufficient_days_or_candidates",
        }
    splits: list[tuple[set[str], set[str]]] = []
    for split_idx in range(1, len(days) - 1):
        left_end = max(0, split_idx - embargo_days)
        right_start = min(len(days), split_idx + embargo_days)
        left = set(days[:left_end])
        right = set(days[right_start:])
        if left and right:
            splits.append((left, right))
            splits.append((right, left))
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
            "method": "purged_day_walk_forward",
            "embargo_days": embargo_days,
            "usable_splits": 0,
            "reason": "embargo_removed_all_usable_splits",
        }
    return {
        "value": bad / usable,
        "method": "purged_day_walk_forward",
        "embargo_days": embargo_days,
        "usable_splits": usable,
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
    k_new = len(symbols) * len(BRANCHES) * len(Z_GRID) * len(P_GRID) * len(OI_GRID) * len(HORIZONS)
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
    pooled_primary: list[float] = []
    pooled_primary_gross: list[float] = []
    pooled_primary_non_settlement: list[float] = []
    branch_primary: dict[str, list[float]] = defaultdict(list)
    per_symbol_primary: dict[str, dict[str, list[float]]] = {
        symbol: {branch: [] for branch in BRANCHES} for symbol in symbols
    }
    per_symbol_primary_sigs: dict[str, list[dict[str, object]]] = defaultdict(list)
    settlement_window_counts = Counter()
    best_primary: dict[str, object] | None = None

    for symbol in symbols:
        for branch in BRANCHES:
            for z_hi in Z_GRID:
                for p_hi, p_lo in P_GRID:
                    for oi_min in OI_GRID:
                        for horizon in HORIZONS:
                            key = CandidateKey(symbol, branch, z_hi, p_hi, p_lo, oi_min, horizon)
                            sigs = _signal_rows(rows_by_symbol[symbol], key=key, cost_bps=cost_bps)
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
                                pooled_primary.extend(values)
                                pooled_primary_gross.extend(gross_values)
                                non_settlement = [
                                    float(s["net_bps"])
                                    for s in sigs
                                    if not bool(s.get("settlement_window"))
                                ]
                                pooled_primary_non_settlement.extend(non_settlement)
                                settlement_window_counts["primary_signals"] += len(sigs)
                                settlement_window_counts["primary_settlement_window_signals"] += sum(
                                    1 for s in sigs if bool(s.get("settlement_window"))
                                )
                                branch_primary[branch].extend(values)
                                per_symbol_primary[symbol][branch].extend(values)
                                per_symbol_primary_sigs[symbol].extend(sigs)
                                if avg_net is not None and (
                                    best_primary is None
                                    or float(best_primary.get("avg_net_bps") or -1e18) < avg_net
                                ):
                                    best_primary = cell

    pbo_meta = _pbo(daily_for_pbo)
    pbo = pbo_meta.get("value")
    pooled = _summary_stats(
        pooled_primary,
        horizon_min=PRIMARY_HORIZON,
        k_total=k_total,
        include_bootstrap=True,
    )
    branch_summary = {
        branch: {
            "n": len(vals),
            "n_eff": _n_eff(len(vals), PRIMARY_HORIZON),
            "avg_net_bps": statistics.mean(vals) if vals else None,
        }
        for branch, vals in ((branch, branch_primary.get(branch, [])) for branch in BRANCHES)
    }
    per_symbol_breakdown = []
    for symbol in symbols:
        sigs = per_symbol_primary_sigs.get(symbol, [])
        days = Counter(_day_bucket(int(s["signal_ts_ms"])) for s in sigs)
        cycles = Counter(str(s.get("next_funding_ms")) for s in sigs if s.get("next_funding_ms"))
        total_values = [
            value
            for branch in BRANCHES
            for value in per_symbol_primary[symbol].get(branch, [])
        ]
        per_symbol_breakdown.append(
            {
                "symbol": symbol,
                "n": len(total_values),
                "n_eff": _n_eff(len(total_values), PRIMARY_HORIZON),
                "avg_net_bps": statistics.mean(total_values) if total_values else None,
                "funding_cycles": len(cycles),
                "max_day_share": max(days.values()) / len(sigs) if sigs and days else 0.0,
                "max_funding_cycle_share": max(cycles.values()) / len(sigs) if sigs and cycles else 0.0,
                "branches": {
                    branch: {
                        "n": len(per_symbol_primary[symbol].get(branch, [])),
                        "n_eff": _n_eff(
                            len(per_symbol_primary[symbol].get(branch, [])),
                            PRIMARY_HORIZON,
                        ),
                        "avg_net_bps": (
                            statistics.mean(per_symbol_primary[symbol][branch])
                            if per_symbol_primary[symbol].get(branch)
                            else None
                        ),
                    }
                    for branch in BRANCHES
                },
            }
        )
    non_settlement_summary = _summary_stats(
        pooled_primary_non_settlement,
        horizon_min=PRIMARY_HORIZON,
        k_total=k_total,
        include_bootstrap=False,
    )
    settlement_summary = {
        "window_minutes": SETTLEMENT_WINDOW_MS // 60_000,
        "primary_signals": settlement_window_counts.get("primary_signals", 0),
        "primary_settlement_window_signals": settlement_window_counts.get(
            "primary_settlement_window_signals",
            0,
        ),
        "primary_settlement_window_share": (
            settlement_window_counts.get("primary_settlement_window_signals", 0)
            / settlement_window_counts.get("primary_signals", 1)
            if settlement_window_counts.get("primary_signals", 0)
            else 0.0
        ),
        "primary_excluding_settlement_window": non_settlement_summary,
        "adverse_drag_sensitivity_bps": (
            (
                float(non_settlement_summary["avg_net_bps"])
                - float(pooled["avg_net_bps"])
            )
            if non_settlement_summary.get("avg_net_bps") is not None
            and pooled.get("avg_net_bps") is not None
            else None
        ),
    }

    baseline_by_branch: dict[str, dict[str, object]] = {}
    baseline_values_all: list[float] = []
    for branch in BRANCHES:
        baseline_sigs = [
            sig
            for symbol in symbols
            for sig in _baseline_signal_rows(
                rows_by_symbol[symbol],
                branch=branch,
                cost_bps=cost_bps,
            )
        ]
        baseline_values = [float(sig["net_bps"]) for sig in baseline_sigs]
        baseline_values_all.extend(baseline_values)
        baseline_summary = _summary_stats(
            baseline_values,
            horizon_min=PRIMARY_HORIZON,
            k_total=k_total,
            include_bootstrap=False,
        )
        branch_avg = branch_summary.get(branch, {}).get("avg_net_bps")
        baseline_avg = baseline_summary.get("avg_net_bps")
        baseline_summary["lift_vs_stage0r_branch_bps"] = (
            float(branch_avg) - float(baseline_avg)
            if branch_avg is not None and baseline_avg is not None
            else None
        )
        baseline_by_branch[branch] = baseline_summary
    baseline_all = _summary_stats(
        baseline_values_all,
        horizon_min=PRIMARY_HORIZON,
        k_total=k_total,
        include_bootstrap=False,
    )
    baseline_lift = {
        "baseline": "prior_5m_direction_without_funding_or_oi_confirmation",
        "pooled_baseline": baseline_all,
        "stage0r_minus_baseline_avg_net_bps": (
            float(pooled["avg_net_bps"]) - float(baseline_all["avg_net_bps"])
            if pooled.get("avg_net_bps") is not None
            and baseline_all.get("avg_net_bps") is not None
            else None
        ),
        "branches": baseline_by_branch,
    }

    cost_edge_ratio = (
        abs(cost_bps) / abs(statistics.mean(pooled_primary_gross))
        if pooled_primary_gross and statistics.mean(pooled_primary_gross) != 0
        else None
    )
    execution_cost_model = {
        "mode": "flat_conservative_cost_bps",
        "cost_bps": cost_bps,
        "maker_share": None,
        "taker_share": None,
        "maker_taker_source": "not_available_in_stage0r_replay_rows",
        "cost_edge_ratio": cost_edge_ratio,
    }
    plateau = _plateau_check(cells, best_primary)

    eligible = False
    reasons: list[str] = []
    if best_primary is None:
        reasons.append("no primary-horizon signals")
    else:
        best_values = _signal_rows(
            rows_by_symbol[str(best_primary["symbol"])],
            key=CandidateKey(
                str(best_primary["symbol"]),
                str(best_primary["branch"]),
                float(best_primary["z_hi"]),
                float(best_primary["p_hi"]),
                float(best_primary["p_lo"]),
                float(best_primary["oi_min_pct"]),
                PRIMARY_HORIZON,
            ),
            cost_bps=cost_bps,
        )
        net_values = [float(v["net_bps"]) for v in best_values]
        pooled_ci = pooled.get("bootstrap_ci_95_60m")
        lower_ci = (
            pooled_ci[0]
            if isinstance(pooled_ci, tuple)
            else pooled_ci[0]
            if isinstance(pooled_ci, list) and pooled_ci
            else None
        )
        checks = [
            (int(best_primary["n_eff"]) >= SYMBOL_N_EFF_FLOOR, "symbol n_eff < 100"),
            (
                branch_summary.get(str(best_primary["branch"]), {}).get("n_eff", 0) >= BRANCH_N_EFF_FLOOR,
                "branch n_eff < 50",
            ),
            (int(pooled["n_eff"]) >= POOLED_N_EFF_FLOOR, "pooled n_eff < 300"),
            (int(best_primary["funding_cycles"]) >= MIN_FUNDING_CYCLES, "funding cycles < 14"),
            (float(best_primary["max_day_share"]) <= MAX_DAY_OR_CYCLE_SHARE, "single-day share > 25%"),
            (
                float(best_primary["max_funding_cycle_share"]) <= MAX_DAY_OR_CYCLE_SHARE,
                "single funding-cycle share > 25%",
            ),
            (
                best_primary["avg_net_bps"] is not None
                and float(best_primary["avg_net_bps"]) >= AVG_NET_FLOOR_BPS,
                "avg_net_bps < +15",
            ),
            (
                best_primary["psr_0"] is not None
                and float(best_primary["psr_0"]) >= PSR_THRESHOLD,
                "PSR(0) < 0.95",
            ),
            (
                best_primary["dsr"] is not None
                and float(best_primary["dsr"]) >= DSR_THRESHOLD,
                "DSR < 0.95",
            ),
            (
                pbo is not None
                and float(pbo) <= PBO_THRESHOLD,
                "PBO missing or > 0.20",
            ),
            (lower_ci is not None and float(lower_ci) > 0, "pooled bootstrap lower bound <= 0"),
            (bool(plateau.get("plateau_passed")), "plateau check failed"),
            (len(net_values) > 0, "no net values"),
        ]
        failed = [reason for ok, reason in checks if not ok]
        eligible = not failed
        reasons.extend(failed)

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
        "source_mode": _source_mode(rows),
        "cost_bps": cost_bps,
        "k_prior": int(k_prior),
        "k_new": k_new,
        "k_total": k_total,
        "row_count": len(rows),
        "symbol_count": len(symbols),
        "panel_metadata": _panel_metadata(rows, symbols),
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
        "top_primary_cells": sorted(
            [c for c in cells if c["horizon_min"] == PRIMARY_HORIZON and c["avg_net_bps"] is not None],
            key=lambda c: (float(c["avg_net_bps"]), int(c["n_eff"])),
            reverse=True,
        )[:20],
        "eligible_for_demo_canary": eligible,
        "eligibility_fail_reasons": reasons,
    }


def grid_cell_count(symbol_count: int) -> int:
    return symbol_count * len(BRANCHES) * len(Z_GRID) * len(P_GRID) * len(OI_GRID) * len(HORIZONS)


def default_symbols_from_rows(rows: Iterable[Mapping[str, object]]) -> tuple[str, ...]:
    return tuple(sorted({str(r.get("symbol")) for r in rows if r.get("symbol")}))
