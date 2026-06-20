#!/usr/bin/env python3
"""Adversarial review for FlashDip shallow-K retune candidates.

This is the gate after `shallow_retune_screen.py`.

It does not search for a prettier backtest. It tries to break the K4/K5/K6
N2/C3/nf3% candidates with:

  G1. macro-crash regime concentration + leave-one-crash-out
  G2. fixed-notional death-spiral Monte Carlo
  G3. DSR / PBO selection deflation across the shallow retune grid

Hard boundary:
  - read-only PG through sibling `screen.py`;
  - REST cache reuse through `prepilot_gates.py`;
  - no Bybit private/trading/auth APIs;
  - no strategy, risk, order, or runtime mutation.

Output remains counterfactual research. A green result can only ask for formal
QC/MIT/AI-E sign-off and then a separate flag-gated demo implementation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from typing import Any, Optional

import screen as base
import survival_safe as surv
import extend_history as ext
import prepilot_gates as gates
import shallow_retune_screen as shallow

ADVERSARIAL_VERSION = "tail_dislocation_meanrev.shallow_retune_adversarial.v0.1"

DEFAULT_CANDIDATE_K_GRID = (0.04, 0.05, 0.06)
DEFAULT_CANDIDATE_HOLD = 2
DEFAULT_CANDIDATE_CAP: Optional[int] = 3
DEFAULT_CANDIDATE_NOTIONAL = 0.03

DEFAULT_SELECTION_K_GRID = (0.02, 0.03, 0.04, 0.05, 0.06)
DEFAULT_SELECTION_HOLD_GRID = (1, 2, 3, 5)
DEFAULT_SELECTION_CAP_GRID: tuple[Optional[int], ...] = (1, 3, 5, None)
DEFAULT_SELECTION_NOTIONAL_GRID = (0.02, 0.03, 0.05, 0.10)
DEFAULT_EFFECTIVE_N = 15
DEFAULT_DEATH_RATES = (0.02, 0.03, 0.05)
DEFAULT_SIZING_SENSITIVITY = (0.005, 0.01, 0.02, 0.03, 0.05)


def _data_root() -> str:
    return os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")


def _stable_seed(*parts: Any) -> int:
    blob = "|".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.sha256(blob).hexdigest()[:8], 16)


def _parse_float_csv(raw: str, *, scale: float = 1.0) -> tuple[float, ...]:
    vals = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            vals.append(float(part) * scale)
    if not vals:
        raise ValueError(f"empty numeric CSV: {raw!r}")
    return tuple(vals)


def _parse_int_csv(raw: str) -> tuple[int, ...]:
    vals = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            vals.append(int(part))
    if not vals:
        raise ValueError(f"empty integer CSV: {raw!r}")
    return tuple(vals)


def _parse_cap_csv(raw: str) -> tuple[Optional[int], ...]:
    vals: list[Optional[int]] = []
    for part in raw.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if part in {"none", "unlimited", "inf", "all"}:
            vals.append(None)
        else:
            vals.append(int(part))
    if not vals:
        raise ValueError(f"empty cap CSV: {raw!r}")
    return tuple(vals)


def _cap_label(cap: Optional[int]) -> str:
    return str(cap) if cap is not None else "unlimited"


def candidate_label(k: float, hold: int, cap: Optional[int], nf: float) -> str:
    return f"K{int(round(k * 100))}_N{hold}_C{_cap_label(cap)}_nf{nf:g}"


def _selection_grid_cells(
    *,
    k_grid: tuple[float, ...],
    hold_grid: tuple[int, ...],
    cap_grid: tuple[Optional[int], ...],
    notional_grid: tuple[float, ...],
) -> list[dict[str, Any]]:
    out = []
    for k in k_grid:
        for hold in hold_grid:
            for cap in cap_grid:
                for nf in notional_grid:
                    out.append({
                        "k": k,
                        "hold": hold,
                        "cap": cap,
                        "nf": nf,
                        "label": candidate_label(k, hold, cap, nf),
                    })
    return out


def _kept_events(
    merged,
    funding,
    btc_fwd,
    btc_regime,
    *,
    k: float,
    hold: int,
    cap: Optional[int],
) -> list[dict[str, Any]]:
    events = surv.build_events_stopped(
        merged,
        funding,
        btc_fwd,
        btc_regime,
        k=k,
        hold=hold,
        stop=None,
    )
    return surv.apply_concurrency_cap(events, cap=cap)["kept"]


def _g2_for_candidate(
    kept: list[dict[str, Any]],
    *,
    k: float,
    hold: int,
    cap: Optional[int],
    notional_frac: float,
    death_rates: tuple[float, ...],
    n_seeds: int,
    sizing_sensitivity: tuple[float, ...],
) -> dict[str, Any]:
    baseline = ext.fixed_notional_equity_curve(
        kept,
        ret_key="net_taker",
        notional_frac=notional_frac,
    )
    death = []
    for rate in death_rates:
        death.append(gates.fixed_notional_death_spiral_stress(
            kept,
            ret_key="net_taker",
            notional_frac=notional_frac,
            cond_death_rate=rate,
            n_seeds=n_seeds,
            base_seed=_stable_seed("shallow_adv_g2", k, hold, cap, notional_frac, rate),
        ))
    sensitivity = []
    for nf in sizing_sensitivity:
        row = {
            "notional_frac": nf,
            "baseline": ext.fixed_notional_equity_curve(kept, ret_key="net_taker", notional_frac=nf),
            "death_stress": [],
        }
        for rate in death_rates:
            row["death_stress"].append(gates.fixed_notional_death_spiral_stress(
                kept,
                ret_key="net_taker",
                notional_frac=nf,
                cond_death_rate=rate,
                n_seeds=n_seeds,
                base_seed=_stable_seed("shallow_adv_sensitivity", k, hold, cap, nf, rate),
            ))
        sensitivity.append(row)
    return {
        "baseline": baseline,
        "death_rates": list(death_rates),
        "death_spiral_mc": death,
        "sizing_sensitivity": sensitivity,
    }


def _dsr_eval_from_series(
    rets: list[float],
    *,
    n_trials: int,
    effective_n: int,
    trial_sr_variance: float,
) -> dict[str, Any]:
    res = gates.deflated_sharpe_ratio(rets, n_trials=n_trials, effective_n=effective_n)
    if isinstance(res, dict):
        return res
    out, sr0_fn, psr_fn = res
    sr0_full = sr0_fn(n_trials, trial_sr_variance)
    sr0_eff = sr0_fn(effective_n, trial_sr_variance)
    out["trial_sr_variance"] = trial_sr_variance
    out["sr0_benchmark_full_trials"] = sr0_full
    out["sr0_benchmark_effective_n"] = sr0_eff
    out["dsr_pvalue_full_trials"] = psr_fn(sr0_full)
    out["dsr_pvalue_effective_n"] = psr_fn(sr0_eff)
    out["psr_vs_zero"] = psr_fn(0.0)
    out["dsr_survives_full_trials"] = bool(out["dsr_pvalue_full_trials"] >= 0.95)
    out["dsr_survives_effective_n"] = bool(out["dsr_pvalue_effective_n"] >= 0.95)
    return out


def _g3_for_candidates(
    merged,
    funding,
    btc_fwd,
    btc_regime,
    *,
    selection_grid: list[dict[str, Any]],
    candidate_labels: list[str],
    effective_n: int,
    cscv_partitions: int,
) -> dict[str, Any]:
    if not gates._SCIPY:
        return {"error": "scipy_unavailable"}
    trial_sharpes: list[float] = []
    candidate_series: dict[str, list[float]] = {}
    for cell in selection_grid:
        _, rets = gates._daily_return_series_for_config(
            merged,
            funding,
            btc_fwd,
            btc_regime,
            k=cell["k"],
            hold=cell["hold"],
            cap=cell["cap"],
            nf=cell["nf"],
        )
        sr = gates._sharpe(rets)
        if sr is not None and math.isfinite(sr):
            trial_sharpes.append(sr)
        if cell["label"] in candidate_labels:
            candidate_series[cell["label"]] = rets

    if len(trial_sharpes) < 2:
        sr_var = 0.0
    else:
        mean = sum(trial_sharpes) / len(trial_sharpes)
        sr_var = sum((x - mean) ** 2 for x in trial_sharpes) / (len(trial_sharpes) - 1)

    aligned = gates.build_aligned_cell_matrix(
        merged,
        funding,
        btc_fwd,
        btc_regime,
        grid_cells=selection_grid,
    )
    pbo = gates.run_g3_pbo_cscv(aligned, n_partitions=cscv_partitions)
    dsr = {
        label: _dsr_eval_from_series(
            candidate_series.get(label, []),
            n_trials=len(selection_grid),
            effective_n=effective_n,
            trial_sr_variance=sr_var,
        )
        for label in candidate_labels
    }
    return {
        "selection_grid_n_trials": len(selection_grid),
        "effective_n": effective_n,
        "trial_sharpe_distribution": {
            "n": len(trial_sharpes),
            "min": min(trial_sharpes) if trial_sharpes else None,
            "max": max(trial_sharpes) if trial_sharpes else None,
            "mean": base._mean(trial_sharpes),
            "variance": sr_var,
        },
        "candidate_dsr": dsr,
        "pbo_cscv": pbo,
    }


def _leave_one_pass(g1: dict[str, Any]) -> bool:
    rows = g1.get("leave_one_crash_out") or []
    important = [
        r for r in rows
        if r.get("removed_rank") in {"top-1", "luna+ftx_named"}
    ]
    return bool(important) and all(bool(r.get("survives")) for r in important)


def _death_survives(g2: dict[str, Any], rate: float) -> Optional[bool]:
    for row in g2.get("death_spiral_mc", []):
        if abs(float(row.get("cond_death_rate_per_entry", -1.0)) - rate) < 1e-12:
            return bool(row.get("survivable_p95"))
    return None


def adversarial_gate_status(
    candidate: dict[str, Any],
    *,
    pbo: dict[str, Any],
) -> dict[str, Any]:
    """Pure status reducer for the adversarial review.

    The threshold set is intentionally explicit so tests can lock the meaning:
    G1 must survive top-crash removal, G2 must survive 2% death stress for a
    conditional candidate and 3% for a strong candidate, and DSR must survive
    at least the honest effective-N benchmark. Full-trials DSR is reported
    separately because the grid cells are highly correlated.
    """
    g1 = candidate.get("g1_regime_attribution", {})
    g2 = candidate.get("g2_death_spiral_fixed_notional", {})
    g3 = candidate.get("g3_dsr", {})
    pbo_val = pbo.get("pbo")
    pbo_not_overfit = pbo_val is not None and pbo_val <= 0.50
    pbo_robust = pbo_val is not None and pbo_val <= 0.30
    g1_ok = (
        g1.get("full_day_clustered_boot_t") is not None
        and g1["full_day_clustered_boot_t"] >= shallow.MIN_BOOT_T
        and shallow._ci_excludes_zero(g1.get("full_day_clustered_ci95"))
        and _leave_one_pass(g1)
    )
    death2 = _death_survives(g2, 0.02)
    death3 = _death_survives(g2, 0.03)
    dsr_eff = bool(g3.get("dsr_survives_effective_n"))
    dsr_full = bool(g3.get("dsr_survives_full_trials"))
    conditional = bool(g1_ok and death2 and dsr_eff and pbo_not_overfit)
    strong = bool(conditional and death3 and dsr_full and pbo_robust)
    reasons = []
    if not g1_ok:
        reasons.append("g1_regime_concentration_or_leave_one_fail")
    if not death2:
        reasons.append("g2_death2pct_p95_fail")
    if not death3:
        reasons.append("g2_death3pct_p95_fail")
    if not dsr_eff:
        reasons.append("g3_dsr_effective_n_fail")
    if not dsr_full:
        reasons.append("g3_dsr_full_trials_fail")
    if not pbo_not_overfit:
        reasons.append("g3_pbo_overfit")
    return {
        "conditional_adversarial_candidate": conditional,
        "strong_adversarial_candidate": strong,
        "g1_pass": g1_ok,
        "g2_death2pct_p95_pass": bool(death2),
        "g2_death3pct_p95_pass": bool(death3),
        "g3_dsr_effective_n_pass": dsr_eff,
        "g3_dsr_full_trials_pass": dsr_full,
        "g3_pbo_not_overfit": pbo_not_overfit,
        "g3_pbo_robust": pbo_robust,
        "fail_reasons": reasons,
    }


def run_adversarial_review(
    conn,
    *,
    candidate_k_grid: tuple[float, ...] = DEFAULT_CANDIDATE_K_GRID,
    candidate_hold: int = DEFAULT_CANDIDATE_HOLD,
    candidate_cap: Optional[int] = DEFAULT_CANDIDATE_CAP,
    candidate_notional_frac: float = DEFAULT_CANDIDATE_NOTIONAL,
    selection_k_grid: tuple[float, ...] = DEFAULT_SELECTION_K_GRID,
    selection_hold_grid: tuple[int, ...] = DEFAULT_SELECTION_HOLD_GRID,
    selection_cap_grid: tuple[Optional[int], ...] = DEFAULT_SELECTION_CAP_GRID,
    selection_notional_grid: tuple[float, ...] = DEFAULT_SELECTION_NOTIONAL_GRID,
    death_rates: tuple[float, ...] = DEFAULT_DEATH_RATES,
    death_seeds: int = surv.DEATH_STRESS_SEEDS,
    sizing_sensitivity: tuple[float, ...] = DEFAULT_SIZING_SENSITIVITY,
    effective_n: int = DEFAULT_EFFECTIVE_N,
    cscv_partitions: int = 10,
) -> dict[str, Any]:
    merged, funding, btc_fwd, btc_regime, meta = gates.build_merged_klines(conn)
    candidate_labels = [
        candidate_label(k, candidate_hold, candidate_cap, candidate_notional_frac)
        for k in candidate_k_grid
    ]
    selection_grid = _selection_grid_cells(
        k_grid=selection_k_grid,
        hold_grid=selection_hold_grid,
        cap_grid=selection_cap_grid,
        notional_grid=selection_notional_grid,
    )
    g3 = _g3_for_candidates(
        merged,
        funding,
        btc_fwd,
        btc_regime,
        selection_grid=selection_grid,
        candidate_labels=candidate_labels,
        effective_n=effective_n,
        cscv_partitions=cscv_partitions,
    )
    pbo = g3.get("pbo_cscv", {}) if isinstance(g3, dict) else {}

    candidates = []
    for k, label in zip(candidate_k_grid, candidate_labels):
        kept = _kept_events(
            merged,
            funding,
            btc_fwd,
            btc_regime,
            k=k,
            hold=candidate_hold,
            cap=candidate_cap,
        )
        g1 = gates.regime_attribution_and_loo(
            merged,
            funding,
            btc_fwd,
            btc_regime,
            k=k,
            hold=candidate_hold,
            cap=candidate_cap,
            label=label,
            seed=_stable_seed("shallow_adv_g1", label),
        )
        g2 = _g2_for_candidate(
            kept,
            k=k,
            hold=candidate_hold,
            cap=candidate_cap,
            notional_frac=candidate_notional_frac,
            death_rates=death_rates,
            n_seeds=death_seeds,
            sizing_sensitivity=sizing_sensitivity,
        )
        row = {
            "label": label,
            "config": {
                "k": k,
                "k_pct": k * 100.0,
                "hold": candidate_hold,
                "cap": shallow._label_cap(candidate_cap),
                "notional_frac": candidate_notional_frac,
            },
            "n_kept": len(kept),
            "g1_regime_attribution": g1,
            "g2_death_spiral_fixed_notional": g2,
            "g3_dsr": (g3.get("candidate_dsr", {}) if isinstance(g3, dict) else {}).get(label, {}),
        }
        row["adversarial_gate"] = adversarial_gate_status(row, pbo=pbo)
        candidates.append(row)

    conditional = [c for c in candidates if c["adversarial_gate"]["conditional_adversarial_candidate"]]
    strong = [c for c in candidates if c["adversarial_gate"]["strong_adversarial_candidate"]]
    if strong:
        status = "STRONG_ADVERSARIAL_RESEARCH_CANDIDATE"
    elif conditional:
        status = "CONDITIONAL_ADVERSARIAL_RESEARCH_CANDIDATE"
    else:
        status = "ADVERSARIAL_REVIEW_BLOCKED_OR_REDUCE_RISK"
    return {
        "version": ADVERSARIAL_VERSION,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "params": {
            "candidate_k_grid": list(candidate_k_grid),
            "candidate_k_pct_grid": [k * 100.0 for k in candidate_k_grid],
            "candidate_hold": candidate_hold,
            "candidate_cap": shallow._label_cap(candidate_cap),
            "candidate_notional_frac": candidate_notional_frac,
            "selection_k_grid": list(selection_k_grid),
            "selection_hold_grid": list(selection_hold_grid),
            "selection_cap_grid": [shallow._label_cap(c) for c in selection_cap_grid],
            "selection_notional_grid": list(selection_notional_grid),
            "death_rates": list(death_rates),
            "death_seeds": death_seeds,
            "sizing_sensitivity": list(sizing_sensitivity),
            "effective_n": effective_n,
            "cscv_partitions": cscv_partitions,
            "survivable_maxdd": surv.SURVIVABLE_MAXDD,
        },
        "data_meta": meta,
        "g3_selection_deflation": g3,
        "candidates": candidates,
        "verdict": {
            "status": status,
            "conditional_candidate_labels": [c["label"] for c in conditional],
            "strong_candidate_labels": [c["label"] for c in strong],
            "promotion_boundary": (
                "Adversarial research only. This does not authorize live/demo "
                "parameter changes, order placement, restarts, or risk changes."
            ),
        },
    }


def write_artifact(report: dict[str, Any], *, out_path: Optional[str]) -> str:
    if out_path is None:
        root = os.path.join(_data_root(), "research", "tail_dislocation_meanrev")
        os.makedirs(root, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = os.path.join(root, f"shallow_retune_adversarial_{stamp}.json")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    blob = json.dumps(report, indent=2, sort_keys=True, default=str)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(blob)
    sha = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    with open(out_path + ".sha256", "w", encoding="utf-8") as fh:
        fh.write(sha + "  " + os.path.basename(out_path) + "\n")
    return out_path


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Read-only adversarial review for FlashDip shallow retune candidates."
    )
    ap.add_argument("--out", default=None)
    ap.add_argument("--candidate-k-pcts", default="4,5,6")
    ap.add_argument("--candidate-hold", type=int, default=DEFAULT_CANDIDATE_HOLD)
    ap.add_argument("--candidate-cap", default="3")
    ap.add_argument("--candidate-notional-frac", type=float, default=DEFAULT_CANDIDATE_NOTIONAL)
    ap.add_argument("--selection-k-pcts", default="2,3,4,5,6")
    ap.add_argument("--selection-holds", default="1,2,3,5")
    ap.add_argument("--selection-caps", default="1,3,5,unlimited")
    ap.add_argument("--selection-notional-fracs", default="0.02,0.03,0.05,0.10")
    ap.add_argument("--death-rates", default="0.02,0.03,0.05")
    ap.add_argument("--death-seeds", type=int, default=surv.DEATH_STRESS_SEEDS)
    ap.add_argument("--sizing-sensitivity", default="0.005,0.01,0.02,0.03,0.05")
    ap.add_argument("--effective-n", type=int, default=DEFAULT_EFFECTIVE_N)
    ap.add_argument("--cscv-partitions", type=int, default=10)
    args = ap.parse_args(argv)

    cap = _parse_cap_csv(args.candidate_cap)
    if len(cap) != 1:
        raise SystemExit("--candidate-cap must contain exactly one cap value")

    conn = base.connect_pg()
    try:
        report = run_adversarial_review(
            conn,
            candidate_k_grid=_parse_float_csv(args.candidate_k_pcts, scale=0.01),
            candidate_hold=args.candidate_hold,
            candidate_cap=cap[0],
            candidate_notional_frac=args.candidate_notional_frac,
            selection_k_grid=_parse_float_csv(args.selection_k_pcts, scale=0.01),
            selection_hold_grid=_parse_int_csv(args.selection_holds),
            selection_cap_grid=_parse_cap_csv(args.selection_caps),
            selection_notional_grid=_parse_float_csv(args.selection_notional_fracs),
            death_rates=_parse_float_csv(args.death_rates),
            death_seeds=args.death_seeds,
            sizing_sensitivity=_parse_float_csv(args.sizing_sensitivity),
            effective_n=args.effective_n,
            cscv_partitions=args.cscv_partitions,
        )
    finally:
        conn.close()

    out = write_artifact(report, out_path=args.out)
    verdict = report["verdict"]
    print(f"[{ADVERSARIAL_VERSION}] artifact -> {out}")
    print(f"verdict={verdict['status']}")
    pbo = report["g3_selection_deflation"].get("pbo_cscv", {})
    print(f"pbo={pbo.get('pbo')} overfit_verdict={pbo.get('overfit_verdict')}")
    for c in report["candidates"]:
        gate = c["adversarial_gate"]
        g2 = c["g2_death_spiral_fixed_notional"]
        death3 = _death_survives(g2, 0.03)
        print(
            f"{c['label']}: conditional={gate['conditional_adversarial_candidate']} "
            f"strong={gate['strong_adversarial_candidate']} "
            f"g1={gate['g1_pass']} death2={gate['g2_death2pct_p95_pass']} "
            f"death3={death3} dsr_eff={gate['g3_dsr_effective_n_pass']} "
            f"dsr_full={gate['g3_dsr_full_trials_pass']} fail={gate['fail_reasons']}"
        )
    print("boundary=counterfactual_only_not_promotion_evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
