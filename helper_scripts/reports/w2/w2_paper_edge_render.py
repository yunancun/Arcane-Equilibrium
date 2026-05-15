"""W2 legacy paper edge / Stage 0R diagnostic report 展現層。

MODULE_NOTE:
    本模組承接 W2 A4-C BTC→Alt Lead-Lag spec v1.2 §7.1 六項 metric 的
    純渲染邏輯。按 AMD-2026-05-15-01，報告只能表達 Stage 0R
    `eligible_for_demo_canary=true/false`，不得表達 Stage 1 PASS 或 promotion。
    輸入只接受 metrics 模組已算好的 pooled/per-symbol dict，輸出 markdown /
    csv / json，不觸碰 DB 與報告寫檔。
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import datetime
from typing import Any, Sequence

try:
    from .w2_paper_edge_metrics import (
        BOOTSTRAP_BLOCK_SIZE_MINUTES,
        BOOTSTRAP_ITERATIONS,
        DEFAULT_COHORT,
        DSR_THRESHOLD,
        NET_EDGE_SIGMA_LOWER_BPS,
        NET_EDGE_SIGMA_UPPER_BPS,
        PSR_THRESHOLD,
        RAW_MARKET_SIGMA_60S_BPS,
        RAW_MARKET_SIGMA_120S_BPS,
        RAW_MARKET_SIGMA_300S_BPS,
    )
except ImportError:
    from w2_paper_edge_metrics import (  # type: ignore
        BOOTSTRAP_BLOCK_SIZE_MINUTES,
        BOOTSTRAP_ITERATIONS,
        DEFAULT_COHORT,
        DSR_THRESHOLD,
        NET_EDGE_SIGMA_LOWER_BPS,
        NET_EDGE_SIGMA_UPPER_BPS,
        PSR_THRESHOLD,
        RAW_MARKET_SIGMA_60S_BPS,
        RAW_MARKET_SIGMA_120S_BPS,
        RAW_MARKET_SIGMA_300S_BPS,
    )


def _fmt(value: Any, fmt: str = ".4f") -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and not math.isfinite(value):
        return "-"
    try:
        return format(value, fmt)
    except (TypeError, ValueError):
        return str(value)


def per_symbol_breakdown_table(
    per_symbol: dict[str, dict],
    cohort: Sequence[str] = DEFAULT_COHORT,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sym in cohort:
        m = per_symbol.get(sym)
        if m is None:
            rows.append({
                "symbol": sym,
                "sample_n": 0,
                "avg_net_bps": None,
                "t_stat": None,
                "psr_0": None,
                "dsr_k95": None,
                "ci_95_low": None,
                "ci_95_high": None,
                "verdict": "no_signal",
                "eligible_for_demo_canary": False,
                "promote_n2": False,
            })
            continue
        rows.append({
            "symbol": sym,
            "sample_n": m["sample_n"],
            "avg_net_bps": m["avg_net_bps"],
            "t_stat": m["t_stat"],
            "psr_0": m["psr_0"],
            "dsr_k95": m["dsr_k95"],
            "ci_95_low": m["ci_95_low"],
            "ci_95_high": m["ci_95_high"],
            "verdict": m["verdict"]["label"],
            "eligible_for_demo_canary": m["verdict"]["eligible_for_demo_canary"],
            "promote_n2": m["verdict"]["promote_n2"],
        })
    return rows


per_symbol_breakdown = per_symbol_breakdown_table


def render_csv(
    pooled: dict,
    per_symbol: dict[str, dict],
    window_days: int,
    cohort: Sequence[str],
    timestamp: datetime,
) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "scope", "symbol", "window_days", "timestamp", "sample_n",
            "avg_net_bps", "t_stat", "psr_0", "dsr_k95", "ci_95_low",
            "ci_95_high", "verdict", "eligible_for_demo_canary", "promote_n2",
        ],
    )
    writer.writeheader()
    writer.writerow({
        "scope": "pooled",
        "symbol": "ALL",
        "window_days": window_days,
        "timestamp": timestamp.isoformat(),
        "sample_n": pooled["sample_n"],
        "avg_net_bps": pooled["avg_net_bps"],
        "t_stat": pooled["t_stat"],
        "psr_0": pooled["psr_0"],
        "dsr_k95": pooled["dsr_k95"],
        "ci_95_low": pooled["ci_95_low"],
        "ci_95_high": pooled["ci_95_high"],
        "verdict": pooled["verdict"]["label"],
        "eligible_for_demo_canary": pooled["verdict"]["eligible_for_demo_canary"],
        "promote_n2": pooled["verdict"]["promote_n2"],
    })
    for row in per_symbol_breakdown_table(per_symbol, cohort):
        writer.writerow({
            "scope": "symbol",
            "window_days": window_days,
            "timestamp": timestamp.isoformat(),
            **row,
        })
    return buf.getvalue()


def render_json(
    pooled: dict,
    per_symbol: dict[str, dict],
    window_days: int,
    cohort: Sequence[str],
    timestamp: datetime,
) -> str:
    return json.dumps(
        {
            "generated_at": timestamp.isoformat(),
            "window_days": window_days,
            "cohort": list(cohort),
            "pooled": pooled,
            "per_symbol": per_symbol,
            "per_symbol_breakdown": per_symbol_breakdown_table(per_symbol, cohort),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def render_markdown(
    pooled: dict,
    per_symbol: dict[str, dict],
    window_days: int,
    cohort: Sequence[str],
    timestamp: datetime,
) -> str:
    lines: list[str] = []
    lines.append("# W2 A4-C BTC→Alt Lead-Lag — Stage 0R Diagnostic Report")
    lines.append("")
    lines.append(
        f"**生成時間**: {timestamp.isoformat()}  "
        f"**Window**: {window_days} days  "
        f"**Cohort size**: {len(cohort)}"
    )
    lines.append(f"**Cohort symbols**: {', '.join(cohort)}")
    lines.append("")
    lines.append("**Spec reference**:")
    lines.append("- AMD-2026-05-15-01：legacy paper report downgraded to diagnostic/read-only; "
                 "output is only `eligible_for_demo_canary=true/false`")
    lines.append("- v1.2 §7.1 mandatory metric 6 條（pooled + per-symbol / DSR K=95 / "
                 "PSR(0) skew/kurt / R²(N) decay / block-bootstrap 95% CI / counterfactual delta）")
    lines.append("- v1.2 §7.1 dual-layer σ：raw market σ_60=4.54/σ_120=6.28/σ_300=10.08 bps "
                 f"+ net edge σ={NET_EDGE_SIGMA_LOWER_BPS:.0f}-{NET_EDGE_SIGMA_UPPER_BPS:.0f} bps")
    lines.append("- v1.4 diagnostic bands：+15 may set eligible_for_demo_canary=true / "
                 "+5~+15 defer / <+5 revise/archive; never Stage 1 PASS")
    lines.append("- v1.2 §7.1 metric (3) PSR(0)：Bailey-López de Prado 2012 skew/kurt-aware "
                 "formula 強制（禁 normal SR z-test）")
    lines.append("")
    lines.append(
        "**PSR(0) 公式**：`PSR(0) = Φ((SR_hat - 0) × √(n-1) / "
        "√(1 - skew·SR_hat + ((kurt-1)/4)·SR_hat²))`"
    )
    lines.append("")
    lines.append("## §1 Pooled metrics（cross-symbol aggregate）")
    lines.append("")
    lines.append("| Metric | Value | 解讀 |")
    lines.append("|---|---|---|")
    lines.append(
        f"| Sample n (normal regime) | {pooled['sample_n']} | "
        f"raw rows = {pooled['raw_rows_n']}, extreme = {pooled['extreme_regime_n']} |"
    )
    lines.append(f"| avg_net_bps | {_fmt(pooled['avg_net_bps'], '.4f')} | 平均反事實 net edge bps |")
    lines.append(f"| stdev (bps) | {_fmt(pooled['stdev_bps'], '.4f')} | "
                 f"net edge σ（對齊 dual-layer σ 範圍 [50, 80]）|")
    lines.append(f"| t-stat | {_fmt(pooled['t_stat'], '.4f')} | H0: μ=0；t>2.0 為信號顯著 |")
    lines.append(f"| PSR(0) | {_fmt(pooled['psr_0'], '.4f')} | "
                 f"Bailey-LdP 2012 skew/kurt-aware；threshold ≥ 0.95 → "
                 f"{'PASS' if pooled.get('psr_0') is not None and pooled['psr_0'] >= PSR_THRESHOLD else 'FAIL'} |")
    lines.append(f"| DSR (K=95) | {_fmt(pooled['dsr_k95'], '.4f')} | "
                 f"mu_0=√(2 ln 95)=3.018；threshold ≥ 0.95 → "
                 f"{'PASS' if pooled.get('dsr_k95') is not None and pooled['dsr_k95'] >= DSR_THRESHOLD else 'FAIL'} |")
    lines.append(
        f"| 95% block-bootstrap CI | "
        f"[{_fmt(pooled['ci_95_low'], '.4f')}, {_fmt(pooled['ci_95_high'], '.4f')}] | "
        f"block_size={BOOTSTRAP_BLOCK_SIZE_MINUTES}min, {BOOTSTRAP_ITERATIONS} iter |"
    )
    lines.append("")
    lines.append("### Alpha decay R²(N=60/120/300) — pooled")
    lines.append("")
    lines.append("| N (secs) | R²(N) | raw market σ baseline (bps) |")
    lines.append("|---|---|---|")
    lines.append(f"| 60 | {_fmt(pooled['r_squared_60s'], '.4f')} | {RAW_MARKET_SIGMA_60S_BPS:.2f} |")
    lines.append(f"| 120 (主信號) | {_fmt(pooled['r_squared_120s'], '.4f')} | {RAW_MARKET_SIGMA_120S_BPS:.2f} |")
    lines.append(f"| 300 | {_fmt(pooled['r_squared_300s'], '.4f')} | {RAW_MARKET_SIGMA_300S_BPS:.2f} |")
    lines.append("")
    r60 = pooled.get("r_squared_60s")
    r120 = pooled.get("r_squared_120s")
    r300 = pooled.get("r_squared_300s")
    decay_notes = []
    if r120 is not None and r120 < 0.04:
        decay_notes.append("- **WARN**：N=120 主信號 R² < 0.04 → spec §3.1.1 半衰期 < 60s 風險，需 revise")
    if r60 is not None and r300 is not None and r300 > r60:
        decay_notes.append(
            "- **WARN**：R²(300) > R²(60) → trend-continuation 未被 arbitrage 完全消化，需重評 N 選擇"
        )
    if not decay_notes:
        decay_notes.append("- alpha decay regime test：OK（N=120 主信號 R² ≥ 0.04 + decay 單調）")
    lines.extend(decay_notes)
    lines.append("")
    lines.append(f"### Stage 0R diagnostic verdict — pooled: **{pooled['verdict']['label']}**")
    lines.append("")
    lines.append(f"> {pooled['verdict']['reason']}")
    lines.append("")
    lines.append("## §2 Per-symbol breakdown（spec §7.1 metric (1)：n ≥ 100 + t > 2.0 diagnostic gate）")
    lines.append("")
    lines.append("| Symbol | n | avg_net (bps) | t-stat | PSR(0) | DSR | CI 95% | Verdict | eligible_for_demo_canary |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for sym in cohort:
        m = per_symbol.get(sym)
        if m is None:
            lines.append(f"| {sym} | 0 | - | - | - | - | - | no_signal | false |")
            continue
        ci_str = (
            f"[{_fmt(m['ci_95_low'], '.2f')}, {_fmt(m['ci_95_high'], '.2f')}]"
            if m.get("ci_95_low") is not None and m.get("ci_95_high") is not None
            else "-"
        )
        eligible = "true" if m["verdict"]["eligible_for_demo_canary"] else "false"
        lines.append(
            f"| {sym} | {m['sample_n']} | {_fmt(m['avg_net_bps'], '.2f')} | "
            f"{_fmt(m['t_stat'], '.3f')} | {_fmt(m['psr_0'], '.3f')} | "
            f"{_fmt(m['dsr_k95'], '.3f')} | {ci_str} | "
            f"{m['verdict']['label']} | {eligible} |"
        )
    lines.append("")
    lines.append("## §3 Per-cohort counterfactual delta（expected_dir 三方向）")
    lines.append("")
    lines.append("| Symbol | LONG n / avg (bps) | SHORT n / avg (bps) | No-signal n / baseline (bps) | extreme regime n |")
    lines.append("|---|---|---|---|---|")
    for sym in cohort:
        m = per_symbol.get(sym)
        if m is None:
            lines.append(f"| {sym} | 0 / - | 0 / - | 0 / - | 0 |")
            continue
        lines.append(
            f"| {sym} | {m['long_n']} / {_fmt(m['cf_long_avg_bps'], '.2f')} | "
            f"{m['short_n']} / {_fmt(m['cf_short_avg_bps'], '.2f')} | "
            f"{m['no_signal_n']} / {_fmt(m['cf_no_signal_baseline_bps'], '.2f')} | "
            f"{m['extreme_regime_n']} |"
        )
    lines.append("")
    lines.append("## §4 Alpha decay R²(N=60/120/300) per-symbol（spec §7.1 metric (4)）")
    lines.append("")
    lines.append("| Symbol | R²(60) | R²(120 主信號) | R²(300) | decay verdict |")
    lines.append("|---|---|---|---|---|")
    for sym in cohort:
        m = per_symbol.get(sym)
        if m is None:
            lines.append(f"| {sym} | - | - | - | no_data |")
            continue
        r60_s = m.get("r_squared_60s")
        r120_s = m.get("r_squared_120s")
        r300_s = m.get("r_squared_300s")
        verdict_d = "OK"
        if r120_s is not None and r120_s < 0.04:
            verdict_d = "FAIL: R²(120)<0.04"
        elif r60_s is not None and r300_s is not None and r300_s > r60_s:
            verdict_d = "WARN: R²(300)>R²(60)"
        lines.append(
            f"| {sym} | {_fmt(r60_s, '.4f')} | {_fmt(r120_s, '.4f')} | "
            f"{_fmt(r300_s, '.4f')} | {verdict_d} |"
        )
    lines.append("")
    lines.append("## §5 Stage 0R summary（AMD-2026-05-15-01）")
    lines.append("")
    p = pooled
    psr_pass = p.get("psr_0") is not None and p["psr_0"] >= PSR_THRESHOLD
    dsr_pass = p.get("dsr_k95") is not None and p["dsr_k95"] >= DSR_THRESHOLD
    pooled_eligible = p["verdict"].get("eligible_for_demo_canary", False)
    any_symbol_eligible = any(
        m["verdict"].get("eligible_for_demo_canary", False) for m in per_symbol.values()
    )
    lines.append(f"- Pooled PSR(0) ≥ 0.95（B-LdP 2012）: "
                 f"{'✅ PASS' if psr_pass else '❌ FAIL'} (`{_fmt(p.get('psr_0'), '.4f')}`)")
    lines.append(f"- Pooled DSR ≥ 0.95（K=95, mu_0=3.018）: "
                 f"{'✅ PASS' if dsr_pass else '❌ FAIL'} (`{_fmt(p.get('dsr_k95'), '.4f')}`)")
    lines.append(
        f"- Pooled verdict: `{p['verdict']['label']}` → "
        f"eligible_for_demo_canary: {'true' if pooled_eligible else 'false'}"
    )
    lines.append(
        f"- Any per-symbol eligible_for_demo_canary=true: "
        f"{'true' if any_symbol_eligible else 'false'}"
    )
    lines.append("")
    lines.append("**Stage 0R verdict**：")
    final_verdict = "eligible_for_demo_canary=false; ARCHIVE / REVISE"
    if pooled_eligible and any_symbol_eligible and psr_pass and dsr_pass:
        final_verdict = "eligible_for_demo_canary=true; MAY REQUEST STAGE 1 DEMO MICRO-CANARY"
    elif p["verdict"]["label"] == "plus5_15":
        final_verdict = "eligible_for_demo_canary=false_or_defer; EXTEND REPLAY/PREFLIGHT DIAGNOSTICS"
    elif p["verdict"]["label"] == "plus15" and (not psr_pass or not dsr_pass):
        final_verdict = "eligible_for_demo_canary=false; PSR/DSR fail"
    lines.append(f"> **{final_verdict}**")
    lines.append("")
    lines.append(
        "（本報告不是 Stage 1 PASS。PA + QC + MIT 只能用它決定是否申請 "
        "Stage 1 Demo micro-canary；Stage 2 必引用 demo empirical evidence。）"
    )
    lines.append("")
    return "\n".join(lines)
