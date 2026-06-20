"""Focused tests for the FlashDip shallow-K retune screen."""

from __future__ import annotations

import datetime as dt
import json

import screen as base
import shallow_retune_screen as srs
import shallow_retune_adversarial as adv


def _bars(symbol: str, *, n: int = 16) -> list[dict]:
    rows = []
    start = dt.date(2026, 1, 1)
    for i in range(n):
        day = start + dt.timedelta(days=i)
        close = 100.0 + i * 0.2
        # Every third day dips through K2 but not through K6, then reverts.
        low = close * (0.975 if i % 3 == 1 else 0.995)
        rows.append({
            "date": day.isoformat(),
            "open": close,
            "high": close * 1.02,
            "low": low,
            "close": close,
            "turnover": 1000.0,
            "_symbol": symbol,
        })
    return rows


def test_research_gate_requires_shallow_k_and_notional_cap():
    base_cell = {
        "k": 0.04,
        "notional_frac": 0.03,
        "positive_expectancy": True,
        "day_clustered_significant": True,
        "survivable_maxdd": True,
    }
    ok = srs.research_gate_status(
        base_cell,
        candidate_k_grid=(0.02, 0.03, 0.04, 0.05, 0.06),
        max_research_notional_frac=0.03,
    )
    assert ok["full_history_research_gate_pass"] is True

    ref_k = dict(base_cell, k=0.15)
    assert srs.research_gate_status(
        ref_k,
        candidate_k_grid=(0.02, 0.03, 0.04, 0.05, 0.06),
        max_research_notional_frac=0.03,
    )["fail_reasons"] == ["reference_k_not_shallow_candidate"]

    too_large = dict(base_cell, notional_frac=0.10)
    assert "notional_frac_above_research_cap" in srs.research_gate_status(
        too_large,
        candidate_k_grid=(0.02, 0.03, 0.04, 0.05, 0.06),
        max_research_notional_frac=0.03,
    )["fail_reasons"]


def test_report_marks_counterfactual_boundary_and_runtime_touch_context(tmp_path):
    touch_path = tmp_path / "flash_dip_touchability.log"
    touch_path.write_text(json.dumps({
        "check": "flash_dip_touchability",
        "current_k_pct": 15,
        "deepest_candidate_k_with_touch_pct": 6,
    }) + "\n")

    merged = {
        "BTCUSDT": _bars("BTCUSDT"),
        "AAAUSDT": _bars("AAAUSDT"),
    }
    btc_fwd, btc_regime = base.build_btc_helpers(merged["BTCUSDT"])
    report = srs.run_report_from_merged(
        merged,
        funding={},
        btc_fwd=btc_fwd,
        btc_regime=btc_regime,
        meta={"n_symbols": 2, "n_rest_cached": 0, "global_first": "2026-01-01", "global_last": "2026-01-16"},
        candidate_k_grid=(0.02,),
        reference_k_grid=(),
        hold_grid=(1,),
        cap_grid=(1,),
        notional_grid=(0.02,),
        max_finalists=1,
        touchability_path=str(touch_path),
    )

    assert report["params"]["candidate_k_pct_grid"] == [2.0]
    assert report["runtime_touchability_context"]["source_ok"] is True
    assert report["runtime_touchability_context"]["latest"]["deepest_candidate_k_with_touch_pct"] == 6
    assert len(report["grid"]) == 1
    assert report["grid"][0]["evidence_boundary"] == "counterfactual_only_not_promotion_evidence"
    assert "promotion_boundary" in report["verdict"]


def _candidate_for_adversarial_gate(*, death2=True, death3=True, dsr_eff=True, dsr_full=True):
    return {
        "g1_regime_attribution": {
            "full_day_clustered_boot_t": 3.0,
            "full_day_clustered_ci95": [0.01, 0.02],
            "leave_one_crash_out": [
                {"removed_rank": "top-1", "survives": True},
                {"removed_rank": "luna+ftx_named", "survives": True},
            ],
        },
        "g2_death_spiral_fixed_notional": {
            "death_spiral_mc": [
                {"cond_death_rate_per_entry": 0.02, "survivable_p95": death2},
                {"cond_death_rate_per_entry": 0.03, "survivable_p95": death3},
            ],
        },
        "g3_dsr": {
            "dsr_survives_effective_n": dsr_eff,
            "dsr_survives_full_trials": dsr_full,
        },
    }


def test_adversarial_gate_distinguishes_conditional_from_strong():
    assert adv.candidate_label(0.04, 2, 3, 0.03) == "K4_N2_C3_nf0.03"

    strong = adv.adversarial_gate_status(
        _candidate_for_adversarial_gate(),
        pbo={"pbo": 0.20},
    )
    assert strong["conditional_adversarial_candidate"] is True
    assert strong["strong_adversarial_candidate"] is True

    conditional = adv.adversarial_gate_status(
        _candidate_for_adversarial_gate(death3=False, dsr_full=False),
        pbo={"pbo": 0.40},
    )
    assert conditional["conditional_adversarial_candidate"] is True
    assert conditional["strong_adversarial_candidate"] is False
    assert "g2_death3pct_p95_fail" in conditional["fail_reasons"]
    assert "g3_dsr_full_trials_fail" in conditional["fail_reasons"]


def test_adversarial_gate_blocks_overfit_or_death2_failure():
    death_fail = adv.adversarial_gate_status(
        _candidate_for_adversarial_gate(death2=False),
        pbo={"pbo": 0.20},
    )
    assert death_fail["conditional_adversarial_candidate"] is False
    assert "g2_death2pct_p95_fail" in death_fail["fail_reasons"]

    pbo_fail = adv.adversarial_gate_status(
        _candidate_for_adversarial_gate(),
        pbo={"pbo": 0.75},
    )
    assert pbo_fail["conditional_adversarial_candidate"] is False
    assert "g3_pbo_overfit" in pbo_fail["fail_reasons"]
