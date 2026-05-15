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
    block_size: int = 12,
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
        out.append(
            {
                "signal_ts_ms": signal_ts,
                "net_bps": gross - cost_bps,
                "gross_bps": gross,
                "next_funding_ms": _safe_int(row.get("next_funding_ms")),
            }
        )
    return out


def _pbo(candidates: Mapping[str, Mapping[str, float]]) -> float | None:
    days = sorted({day for daily in candidates.values() for day in daily})
    candidate_keys = list(candidates)
    if len(days) < 4 or len(candidate_keys) < 10:
        return None
    splits: list[tuple[set[str], set[str]]] = []
    mid = len(days) // 2
    splits.append((set(days[:mid]), set(days[mid:])))
    splits.append((set(days[mid:]), set(days[:mid])))
    if len(days) >= 6:
        splits.append((set(days[::2]), set(days[1::2])))
        splits.append((set(days[1::2]), set(days[::2])))
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
        return None
    return bad / usable


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
    branch_primary: dict[str, list[float]] = defaultdict(list)
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
                                branch_primary[branch].extend(values)
                                if avg_net is not None and (
                                    best_primary is None
                                    or float(best_primary.get("avg_net_bps") or -1e18) < avg_net
                                ):
                                    best_primary = cell

    pbo = _pbo(daily_for_pbo)
    pooled_ci = block_bootstrap_ci(pooled_primary)
    pooled = {
        "n": len(pooled_primary),
        "n_eff": _n_eff(len(pooled_primary), PRIMARY_HORIZON),
        "avg_net_bps": statistics.mean(pooled_primary) if pooled_primary else None,
        "psr_0": psr_bailey_ldp(pooled_primary),
        "dsr": dsr_with_k(pooled_primary, k_total),
        "bootstrap_ci_95": pooled_ci,
    }
    branch_summary = {
        branch: {
            "n": len(vals),
            "n_eff": _n_eff(len(vals), PRIMARY_HORIZON),
            "avg_net_bps": statistics.mean(vals) if vals else None,
        }
        for branch, vals in branch_primary.items()
    }

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
        ci = best_primary.get("bootstrap_ci_95")
        lower_ci = ci[0] if isinstance(ci, tuple) else None
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
            (pbo is not None and pbo <= PBO_THRESHOLD, "PBO missing or > 0.20"),
            (lower_ci is not None and lower_ci > 0, "bootstrap lower bound <= 0"),
            (len(net_values) > 0, "no net values"),
        ]
        failed = [reason for ok, reason in checks if not ok]
        eligible = not failed
        reasons.extend(failed)

    return {
        "strategy_variant": STRATEGY_VARIANT,
        "alpha_source_id": ALPHA_SOURCE_ID,
        "funding_attribution_mode": "excluded",
        "source_mode": "ws_current",
        "cost_bps": cost_bps,
        "k_prior": int(k_prior),
        "k_new": k_new,
        "k_total": k_total,
        "row_count": len(rows),
        "symbol_count": len(symbols),
        "exclusions": dict(missing),
        "pooled_primary": pooled,
        "branch_summary": branch_summary,
        "pbo": pbo,
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
