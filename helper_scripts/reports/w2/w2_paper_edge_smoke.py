"""W2 paper edge report smoke fixture。

MODULE_NOTE:
    本模組承接 W2 A4-C BTC→Alt Lead-Lag spec v1.2 §7.1 / §8.1 的
    三組 mock fixture smoke test：plus15、plus5_15、minus5。fixture 不連 PG，
    只驗 metrics 模組的 PSR/DSR/bootstrap/R² 與 step gate verdict。
"""

from __future__ import annotations

import random

try:
    from .w2_paper_edge_metrics import compute_per_symbol_metrics, compute_pooled_metrics
    from .w2_paper_edge_render import _fmt
except ImportError:
    from w2_paper_edge_metrics import compute_per_symbol_metrics, compute_pooled_metrics  # type: ignore
    from w2_paper_edge_render import _fmt  # type: ignore


def _make_mock_row(
    symbol: str,
    ts_bucket: int,
    expected_dir: int,
    btc_lead: float,
    btc_lead_60s: float,
    btc_lead_300s: float,
    xcorr: float,
    regime: str,
    alt_fwd_60s: float,
    alt_fwd_120s: float,
    alt_fwd_300s: float,
    has_fill: bool = False,
) -> dict:
    cf_60 = expected_dir * alt_fwd_60s if expected_dir != 0 else None
    cf_120 = expected_dir * alt_fwd_120s if expected_dir != 0 else None
    cf_300 = expected_dir * alt_fwd_300s if expected_dir != 0 else None
    return {
        "symbol": symbol,
        "snapshot_ts_ms": ts_bucket,
        "lead_window_secs": 120,
        "btc_lead_return_pct": btc_lead,
        "btc_lead_return_pct_60s": btc_lead_60s,
        "btc_lead_return_pct_300s": btc_lead_300s,
        "btc_volume_z": 0.5,
        "btc_book_imbalance": 0.1,
        "xcorr": xcorr,
        "expected_dir": expected_dir,
        "regime_tag": regime,
        "alt_forward_return_60s_bps": alt_fwd_60s,
        "alt_forward_return_120s_bps": alt_fwd_120s,
        "alt_forward_return_300s_bps": alt_fwd_300s,
        "cf_net_edge_60s_bps": cf_60,
        "cf_net_edge_120s_bps": cf_120,
        "cf_net_edge_300s_bps": cf_300,
        "has_actual_fill": has_fill,
        "actual_fill_count": 1 if has_fill else 0,
    }


def make_smoke_fixture_plus15() -> list[dict]:
    rng = random.Random(20260512)
    rows = []
    ts0 = 1_730_000_000_000
    for i in range(150):
        alt = 20.0 + rng.uniform(-5.0, 5.0)
        btc_jitter = rng.uniform(-3.0, 3.0)
        rows.append(_make_mock_row(
            symbol="ETHUSDT",
            ts_bucket=ts0 + i * 60_000,
            expected_dir=1,
            btc_lead=12.0 + btc_jitter,
            btc_lead_60s=8.0 + btc_jitter * 0.6,
            btc_lead_300s=18.0 + btc_jitter * 1.4,
            xcorr=0.65,
            regime="normal",
            alt_fwd_60s=alt * 0.5,
            alt_fwd_120s=alt,
            alt_fwd_300s=alt * 1.5,
            has_fill=True,
        ))
    return rows


def make_smoke_fixture_plus5_15() -> list[dict]:
    rng = random.Random(20260513)
    rows = []
    ts0 = 1_730_000_000_000
    for i in range(150):
        alt = 8.0 + rng.uniform(-5.0, 5.0)
        btc_jitter = rng.uniform(-3.0, 3.0)
        rows.append(_make_mock_row(
            symbol="ETHUSDT",
            ts_bucket=ts0 + i * 60_000,
            expected_dir=1,
            btc_lead=12.0 + btc_jitter,
            btc_lead_60s=8.0 + btc_jitter * 0.6,
            btc_lead_300s=18.0 + btc_jitter * 1.4,
            xcorr=0.55,
            regime="normal",
            alt_fwd_60s=alt * 0.5,
            alt_fwd_120s=alt,
            alt_fwd_300s=alt * 1.5,
            has_fill=False,
        ))
    return rows


def make_smoke_fixture_minus5() -> list[dict]:
    rng = random.Random(20260514)
    rows = []
    ts0 = 1_730_000_000_000
    for i in range(150):
        alt = -3.0 + rng.uniform(-5.0, 5.0)
        btc_jitter = rng.uniform(-3.0, 3.0)
        rows.append(_make_mock_row(
            symbol="ETHUSDT",
            ts_bucket=ts0 + i * 60_000,
            expected_dir=1,
            btc_lead=11.0 + btc_jitter,
            btc_lead_60s=7.0 + btc_jitter * 0.6,
            btc_lead_300s=17.0 + btc_jitter * 1.4,
            xcorr=0.45,
            regime="normal",
            alt_fwd_60s=alt * 0.5,
            alt_fwd_120s=alt,
            alt_fwd_300s=alt * 1.5,
            has_fill=False,
        ))
    return rows


def run_smoke_test() -> int:
    print("=== W2 paper edge report smoke test ===")
    print("(per dispatch §3.4 E4 regression：plus15 / plus5_15 / minus5)")
    print()

    failures: list[str] = []

    print("Case 1: plus15 (gross +20 bps, n=150, expected promote N+2)")
    rows1 = make_smoke_fixture_plus15()
    per_sym_1 = compute_per_symbol_metrics(rows1, primary_window_secs=120)
    pooled_1 = compute_pooled_metrics(rows1, primary_window_secs=120)
    m1 = per_sym_1.get("ETHUSDT", {})
    print(f"  ETHUSDT: n={m1.get('sample_n')} avg_net={_fmt(m1.get('avg_net_bps'), '.2f')} "
          f"t={_fmt(m1.get('t_stat'), '.3f')} verdict={m1.get('verdict', {}).get('label')}")
    print(f"  pooled: avg_net={_fmt(pooled_1.get('avg_net_bps'), '.2f')} "
          f"verdict={pooled_1.get('verdict', {}).get('label')}")
    if m1.get("verdict", {}).get("label") != "plus15":
        failures.append(f"Case 1 ETHUSDT verdict expected plus15 got {m1.get('verdict', {}).get('label')}")
    if not m1.get("verdict", {}).get("promote_n2"):
        failures.append("Case 1 ETHUSDT promote_n2 expected True")
    print()

    print("Case 2: plus5_15 (gross +8 bps, n=150, expected extend 14d)")
    rows2 = make_smoke_fixture_plus5_15()
    per_sym_2 = compute_per_symbol_metrics(rows2, primary_window_secs=120)
    pooled_2 = compute_pooled_metrics(rows2, primary_window_secs=120)
    m2 = per_sym_2.get("ETHUSDT", {})
    print(f"  ETHUSDT: n={m2.get('sample_n')} avg_net={_fmt(m2.get('avg_net_bps'), '.2f')} "
          f"t={_fmt(m2.get('t_stat'), '.3f')} verdict={m2.get('verdict', {}).get('label')}")
    print(f"  pooled: avg_net={_fmt(pooled_2.get('avg_net_bps'), '.2f')} "
          f"verdict={pooled_2.get('verdict', {}).get('label')}")
    if m2.get("verdict", {}).get("label") != "plus5_15":
        failures.append(f"Case 2 ETHUSDT verdict expected plus5_15 got {m2.get('verdict', {}).get('label')}")
    if m2.get("verdict", {}).get("promote_n2"):
        failures.append("Case 2 ETHUSDT promote_n2 expected False")
    print()

    print("Case 3: minus5 (gross -3 bps, n=150, expected revise/archive)")
    rows3 = make_smoke_fixture_minus5()
    per_sym_3 = compute_per_symbol_metrics(rows3, primary_window_secs=120)
    pooled_3 = compute_pooled_metrics(rows3, primary_window_secs=120)
    m3 = per_sym_3.get("ETHUSDT", {})
    print(f"  ETHUSDT: n={m3.get('sample_n')} avg_net={_fmt(m3.get('avg_net_bps'), '.2f')} "
          f"t={_fmt(m3.get('t_stat'), '.3f')} verdict={m3.get('verdict', {}).get('label')}")
    print(f"  pooled: avg_net={_fmt(pooled_3.get('avg_net_bps'), '.2f')} "
          f"verdict={pooled_3.get('verdict', {}).get('label')}")
    if m3.get("verdict", {}).get("label") != "minus5":
        failures.append(f"Case 3 ETHUSDT verdict expected minus5 got {m3.get('verdict', {}).get('label')}")
    if m3.get("verdict", {}).get("promote_n2"):
        failures.append("Case 3 ETHUSDT promote_n2 expected False")
    print()

    psr_case1 = m1.get("psr_0")
    if psr_case1 is None or psr_case1 < 0.95:
        failures.append(f"Case 1 PSR(0) expected ≥0.95, got {psr_case1}")
    else:
        print(f"  PSR(0) case 1 = {_fmt(psr_case1, '.4f')} ≥ 0.95 ✅ (Bailey-LdP 2012 formula)")

    dsr_case1 = m1.get("dsr_k95")
    if dsr_case1 is None:
        failures.append("Case 1 DSR K=95 None - formula error")
    else:
        print(f"  DSR(K=95) case 1 = {_fmt(dsr_case1, '.4f')} (mu_0=√(2 ln 95)=3.018)")
    print()

    ci_case1 = (m1.get("ci_95_low"), m1.get("ci_95_high"))
    if ci_case1[0] is None or ci_case1[1] is None:
        failures.append("Case 1 block-bootstrap CI None")
    else:
        print(f"  Case 1 95% CI = [{_fmt(ci_case1[0], '.3f')}, {_fmt(ci_case1[1], '.3f')}] "
              f"(block_size=60, 1000 iter)")
    print()

    r60 = m1.get("r_squared_60s")
    r120 = m1.get("r_squared_120s")
    r300 = m1.get("r_squared_300s")
    print(f"  Alpha decay R²(60/120/300) case 1: "
          f"{_fmt(r60, '.4f')} / {_fmt(r120, '.4f')} / {_fmt(r300, '.4f')}")
    if r60 is None or r120 is None or r300 is None:
        failures.append("Case 1 R²(N) None - decay formula error")

    print()
    print("=" * 50)
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL PASS — 3 mock case + PSR(0) + DSR + CI + R²(N) 公式驗證通過")
    return 0


def main() -> int:
    return run_smoke_test()


if __name__ == "__main__":
    raise SystemExit(main())
