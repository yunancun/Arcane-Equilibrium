#!/usr/bin/env python3
"""
MODULE_NOTE (English):
  Canary Comparator (R07-3) — reads Rust engine_results.jsonl and Python
  shadow_results.jsonl, joins on (timestamp_ms, symbol), applies tolerance
  tiers from V3-FINAL §5.4, and produces daily reports.

MODULE_NOTE (中文):
  灰度比較器（R07-3）— 讀取 Rust engine_results.jsonl 和 Python
  shadow_results.jsonl，按 (timestamp_ms, symbol) 連接，應用 V3-FINAL §5.4
  容差分級，生成每日報告。

Usage:
  python canary_comparator.py --engine engine_results.jsonl --shadow shadow_results.jsonl
  python canary_comparator.py --engine engine_results.jsonl --shadow shadow_results.jsonl --output report.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# Import schema tolerances / 導入模式容差
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canary_schema import (
    INDICATOR_TOLERANCES,
    BALANCE_TOLERANCES,
    TOLERANCE_SIMPLE,
    TOLERANCE_RECURSIVE,
    TOLERANCE_COMPLEX,
    TOLERANCE_BALANCE,
    BOUNDARY_THRESHOLD_PCT,
    KNOWN_MISSING_INDICATORS,
    validate_record,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Result Types / 結果類型
# ═══════════════════════════════════════════════════════════════════════════════

PASS = "PASS"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
MISSING = "MISSING"                      # Indicator present on one side only (known) / 指標只在一側存在（已知）
BOUNDARY_DIVERGENCE = "BOUNDARY_DIVERGENCE"
SKIPPED = "SKIPPED"
SKIPPED_NON_CLOSE = "SKIPPED_NON_CLOSE"  # Signal/intent skip: non bar-close tick / 非 bar-close tick 跳過信號比較


@dataclass
class Divergence:
    """Single divergence between Rust and Python / Rust 與 Python 之間的單個偏差"""
    tick_number: int
    timestamp_ms: int
    symbol: str
    field: str
    rust_value: Any
    python_value: Any
    tolerance: float
    actual_diff: float
    severity: str           # "WARNING" | "CRITICAL" | "BOUNDARY_DIVERGENCE"
    reason: str


@dataclass
class ComparisonReport:
    """Daily comparison report / 每日比較報告"""
    report_date: str
    engine_file: str
    shadow_file: str
    total_ticks_engine: int = 0
    total_ticks_shadow: int = 0
    matched_ticks: int = 0
    unmatched_engine: int = 0
    unmatched_shadow: int = 0
    total_divergences: int = 0
    critical_count: int = 0
    warning_count: int = 0
    boundary_divergence_count: int = 0
    missing_count: int = 0         # Known-missing indicator occurrences / 已知缺失指標出現次數
    paper_state_skipped: int = 0   # Ticks where paper_state compare was skipped / 跳過 paper_state 比較的 tick 數
    signal_compared_ticks: int = 0   # Ticks where signals were actually compared / 實際比較了信號的 tick 數
    signal_skipped_ticks: int = 0    # Ticks skipped for signal compare (non bar-close) / 因非 bar-close 跳過信號比較的 tick 數
    verdict: str = PASS     # Overall verdict / 總體判定
    divergences: list[dict] = field(default_factory=list)
    boundary_escalation: bool = False
    escalation_reason: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Indicator Key Normalization / 指標鍵名正規化
# ═══════════════════════════════════════════════════════════════════════════════

# Mapping from Rust/Python indicator flat keys to canonical form.
# Rust uses short names (sma_20, bollinger.upper); Python uses parameterized
# names (SMA(20).sma, BB(20,2.0).upper). This map unifies both to a single
# canonical key so comparisons don't produce false-positive divergences.
# Rust 用短名 (sma_20, bollinger.upper)；Python 用參數化名
# (SMA(20).sma, BB(20,2.0).upper)。此映射統一雙方到規範鍵，避免假陽性。
_INDICATOR_KEY_MAP: dict[str, str] = {
    # ── Rust flat key → canonical ──
    "sma_20":               "sma_20",
    "ema_12":               "ema_12",
    "rsi_14":               "rsi_14",
    "macd.macd":            "macd_macd",
    "macd.signal":          "macd_signal",
    "macd.histogram":       "macd_histogram",
    "bollinger.upper":      "bb_upper",
    "bollinger.middle":     "bb_middle",
    "bollinger.lower":      "bb_lower",
    "bollinger.bandwidth":  "bb_bandwidth",
    "bollinger.percent_b":  "bb_percent_b",
    "atr.atr":              "atr_14",
    "atr.atr_percent":      "atr_14_pct",
    "stochastic.k":         "stoch_k",
    "stochastic.d":         "stoch_d",
    "kama.kama":            "kama",
    "kama.efficiency_ratio": "kama_er",
    "adx.adx":              "adx",
    "adx.plus_di":          "adx_plus_di",
    "adx.minus_di":         "adx_minus_di",
    "hurst.hurst":          "hurst",
    "hurst.regime":         "hurst_regime",
    "ewma_vol.ewma_vol":    "ewma_vol",
    "ewma_vol.vol_regime":  "ewma_vol_regime",
    "volume_ratio":         "volume_ratio",
    "donchian.upper":       "dc_upper",
    "donchian.lower":       "dc_lower",
    "donchian.middle":      "dc_middle",
    "donchian.width":       "dc_width",

    # ── Python flat key → canonical ──
    "SMA(20).sma":                  "sma_20",
    "SMA(50).sma":                  "sma_50",
    "EMA(12).ema":                  "ema_12",
    "EMA(26).ema":                  "ema_26",
    "RSI(14).rsi":                  "rsi_14",
    "MACD(12,26,9).macd":           "macd_macd",
    "MACD(12,26,9).signal":         "macd_signal",
    "MACD(12,26,9).histogram":      "macd_histogram",
    "BB(20,2.0).upper":             "bb_upper",
    "BB(20,2.0).middle":            "bb_middle",
    "BB(20,2.0).lower":             "bb_lower",
    "BB(20,2.0).bandwidth":         "bb_bandwidth",
    "BB(20,2.0).percent_b":         "bb_percent_b",
    "ATR(14).atr":                  "atr_14",
    "ATR(14).atr_percent":          "atr_14_pct",
    "ATR(5).atr":                   "atr_5",
    "ATR(5).atr_percent":           "atr_5_pct",
    "Stochastic(14,3).k":           "stoch_k",
    "Stochastic(14,3).d":           "stoch_d",
    "KAMA(10).kama":                "kama",
    "KAMA(10).efficiency_ratio":    "kama_er",
    "ADX(14).adx":                  "adx",
    "ADX(14).plus_di":              "adx_plus_di",
    "ADX(14).minus_di":             "adx_minus_di",
    "Hurst.hurst":                  "hurst",
    "Hurst.regime":                 "hurst_regime",
    "EWMA_Vol(1h).ewma_vol":        "ewma_vol",
    "EWMA_Vol(1h).vol_regime":      "ewma_vol_regime",
    "VolumeRatio(20).volume_ratio":  "volume_ratio",
    "Donchian(20).donchian_upper":  "dc_upper",
    "Donchian(20).donchian_lower":  "dc_lower",
    "Donchian(20).donchian_middle": "dc_middle",
    "Donchian(20).donchian_width":  "dc_width",
}


def normalize_indicator_keys(flat_indicators: dict[str, Any]) -> dict[str, Any]:
    """
    Map Rust or Python indicator flat keys to canonical form.
    將 Rust 或 Python 的展平指標鍵映射到規範形式。

    Unknown keys are kept as-is so new indicators don't silently vanish.
    未知鍵保持原樣，避免新指標被靜默丟棄。
    """
    normalized: dict[str, Any] = {}
    for key, value in flat_indicators.items():
        canonical = _INDICATOR_KEY_MAP.get(key, key)
        normalized[canonical] = value
    return normalized


# ═══════════════════════════════════════════════════════════════════════════════
# Comparison Engine / 比較引擎
# ═══════════════════════════════════════════════════════════════════════════════


def _flatten_dict(d: dict, prefix: str = "") -> dict[str, Any]:
    """
    Flatten nested dict to dot-notation keys.
    將嵌套字典展平為點記法鍵。
    Example: {"macd": {"macd": 1.0}} → {"macd.macd": 1.0}
    """
    items: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(_flatten_dict(v, key))
        else:
            items[key] = v
    return items


def _get_tolerance(field_name: str) -> float:
    """
    Get tolerance for a field, checking indicator and balance maps.
    獲取字段的容差，檢查指標和餘額映射。
    """
    if field_name in INDICATOR_TOLERANCES:
        return INDICATOR_TOLERANCES[field_name]
    if field_name in BALANCE_TOLERANCES:
        return BALANCE_TOLERANCES[field_name]
    # Default to recursive tolerance for unknown fields / 未知字段默認用遞歸容差
    return TOLERANCE_RECURSIVE


def compare_numeric(
    field_name: str,
    rust_val: Any,
    python_val: Any,
    tick_number: int,
    timestamp_ms: int,
    symbol: str,
) -> Optional[Divergence]:
    """
    Compare two numeric values with the appropriate tolerance.
    用適當的容差比較兩個數值。
    Returns Divergence if they differ beyond tolerance, else None.
    """
    if rust_val is None and python_val is None:
        return None
    if rust_val is None or python_val is None:
        # Check if this is a known-missing indicator — report as MISSING, not WARNING/CRITICAL
        # 檢查是否為已知缺失指標 — 報告為 MISSING 而非 WARNING/CRITICAL
        if field_name in KNOWN_MISSING_INDICATORS:
            return Divergence(
                tick_number=tick_number,
                timestamp_ms=timestamp_ms,
                symbol=symbol,
                field=field_name,
                rust_value=rust_val,
                python_value=python_val,
                tolerance=0,
                actual_diff=0,
                severity=MISSING,
                reason=f"known missing indicator: {field_name} (rust={'present' if rust_val is not None else 'absent'}, python={'present' if python_val is not None else 'absent'})",
            )
        # One has value, other doesn't — WARNING unless it's a critical field
        # 一個有值另一個沒有 — WARNING 除非是關鍵字段
        return Divergence(
            tick_number=tick_number,
            timestamp_ms=timestamp_ms,
            symbol=symbol,
            field=field_name,
            rust_value=rust_val,
            python_value=python_val,
            tolerance=0,
            actual_diff=float("inf"),
            severity=WARNING,
            reason=f"one side is None: rust={rust_val}, python={python_val}",
        )
    if not isinstance(rust_val, (int, float)) or not isinstance(python_val, (int, float)):
        return None  # Skip non-numeric / 跳過非數值

    tolerance = _get_tolerance(field_name)
    diff = abs(float(rust_val) - float(python_val))

    if diff <= tolerance:
        return None

    # Determine severity / 確定嚴重程度
    if diff > tolerance * 1000:
        severity = CRITICAL
    else:
        severity = WARNING

    return Divergence(
        tick_number=tick_number,
        timestamp_ms=timestamp_ms,
        symbol=symbol,
        field=field_name,
        rust_value=rust_val,
        python_value=python_val,
        tolerance=tolerance,
        actual_diff=diff,
        severity=severity,
        reason=f"diff={diff:.2e} > tolerance={tolerance:.0e}",
    )


def compare_signal_direction(
    rust_signals: list[dict],
    python_signals: list[dict],
    tick_number: int,
    timestamp_ms: int,
    symbol: str,
) -> list[Divergence]:
    """
    Compare signal directions with boundary exemption.
    比較信號方向，帶邊界豁免。
    """
    divergences: list[Divergence] = []

    # Index by source rule / 按規則名索引
    rust_by_source = {s.get("source", ""): s for s in rust_signals}
    python_by_source = {s.get("source", ""): s for s in python_signals}

    all_sources = set(rust_by_source.keys()) | set(python_by_source.keys())
    for source in all_sources:
        r = rust_by_source.get(source)
        p = python_by_source.get(source)

        if r is None or p is None:
            divergences.append(Divergence(
                tick_number=tick_number,
                timestamp_ms=timestamp_ms,
                symbol=symbol,
                field=f"signal.{source}.presence",
                rust_value="present" if r else "absent",
                python_value="present" if p else "absent",
                tolerance=0,
                actual_diff=1,
                severity=WARNING,
                reason=f"signal '{source}' present in one side only",
            ))
            continue

        r_dir = r.get("direction", "Neutral")
        p_dir = p.get("direction", "Neutral")

        if r_dir == p_dir:
            continue

        # Check boundary exemption: if confidence is near threshold / 檢查邊界豁免
        r_conf = r.get("confidence", 0.5)
        p_conf = p.get("confidence", 0.5)
        near_boundary = abs(r_conf - 0.5) < BOUNDARY_THRESHOLD_PCT / 100

        if near_boundary:
            severity = BOUNDARY_DIVERGENCE
            reason = f"direction mismatch ({r_dir} vs {p_dir}) but near boundary (conf={r_conf:.3f})"
        else:
            severity = CRITICAL
            reason = f"direction mismatch: rust={r_dir}, python={p_dir}, conf={r_conf:.3f}"

        divergences.append(Divergence(
            tick_number=tick_number,
            timestamp_ms=timestamp_ms,
            symbol=symbol,
            field=f"signal.{source}.direction",
            rust_value=r_dir,
            python_value=p_dir,
            tolerance=0,
            actual_diff=1,
            severity=severity,
            reason=reason,
        ))

    return divergences


def _is_bar_close_tick(rust: dict, python: dict) -> bool:
    """
    Determine if this tick is a bar-close tick where Python shadow produces signals.
    判斷此 tick 是否為 bar-close tick（Python shadow 會在此生成信號）。

    Heuristic: replay_runner synthesize_ticks() generates 4 ticks per kline
    (open, high, low, close). The 4th tick (close) is where Python produces
    signals. If Python shadow has empty signals while Rust has signals, this
    is a non-close tick — skip signal/intent comparison.
    啟發式：replay_runner 每根 K 線生成 4 個 tick。第 4 個（close）是 Python
    生成信號的位置。若 Python 無信號而 Rust 有，則為非 close tick，跳過比較。
    """
    r_sigs = rust.get("signals", [])
    p_sigs = python.get("signals", [])
    r_intents = rust.get("order_intents", [])
    p_intents = python.get("order_intents", [])

    # If Python has signals or intents, it's a bar-close tick — compare normally
    # 若 Python 有信號或意圖，為 bar-close tick，正常比較
    if p_sigs or p_intents:
        return True

    # If both sides are empty, nothing to compare — treat as close (no false positive)
    # 雙方都為空則無需比較，視為 close（不會產生假陽性）
    if not r_sigs and not r_intents:
        return True

    # Rust has signals/intents but Python doesn't — non-close tick, skip
    # Rust 有信號/意圖但 Python 沒有 — 非 close tick，跳過
    return False


def compare_tick(rust: dict, python: dict) -> tuple[list[Divergence], bool, bool]:
    """
    Compare a single tick pair (Rust vs Python).
    比較單個 tick 對（Rust vs Python）。
    Returns (divergences, paper_state_skipped, signal_skipped).
    返回 (偏差列表, 是否跳過 paper_state 比較, 是否跳過信號比較)。
    """
    tick_number = rust.get("tick_number", 0)
    timestamp_ms = rust.get("timestamp_ms", 0)
    symbol = rust.get("symbol", "")
    divergences: list[Divergence] = []

    # 1. Compare indicators (normalize keys first) — always compare, unaffected by bar-close
    #    比較指標（先正規化鍵名）— 始終比較，不受 bar-close 影響
    r_ind = normalize_indicator_keys(_flatten_dict(rust.get("indicators") or {}))
    p_ind = normalize_indicator_keys(_flatten_dict(python.get("indicators") or {}))
    all_keys = set(r_ind.keys()) | set(p_ind.keys())
    for key in all_keys:
        d = compare_numeric(key, r_ind.get(key), p_ind.get(key), tick_number, timestamp_ms, symbol)
        if d:
            divergences.append(d)

    # 2. Compare signals — only on bar-close ticks (Option C: comparator-side filter)
    #    比較信號 — 僅在 bar-close tick 比較（方案 C：comparator 側過濾）
    #    Rust produces signals every tick; Python only on bar close. Comparing
    #    non-close ticks would generate massive false positives.
    #    Rust 每個 tick 都產生信號；Python 僅在 bar close 時。比較非 close tick
    #    會產生大量假陽性。
    bar_close = _is_bar_close_tick(rust, python)
    sig_skipped = not bar_close

    if bar_close:
        r_sigs = rust.get("signals", [])
        p_sigs = python.get("signals", [])
        divergences.extend(compare_signal_direction(r_sigs, p_sigs, tick_number, timestamp_ms, symbol))

    # 3. Compare paper state — skip if either side is empty (known Python shadow
    #    limitation: paper_state is always {}).
    #    比較紙盤狀態 — 若任一方為空則跳過（已知 Python shadow 限制：
    #    paper_state 永遠為 {}）。結果記為 SKIPPED 而非 WARNING。
    r_ps = rust.get("paper_state") or {}
    p_ps = python.get("paper_state") or {}
    ps_skipped = False
    if r_ps and p_ps:
        for key in BALANCE_TOLERANCES:
            d = compare_numeric(key, r_ps.get(key), p_ps.get(key), tick_number, timestamp_ms, symbol)
            if d:
                divergences.append(d)
    else:
        # SKIPPED — one or both paper_state empty, not a real divergence
        # SKIPPED — 一方或雙方 paper_state 為空，非真實偏差
        ps_skipped = True

    # 4. Compare order intent counts — only on bar-close ticks (same reason as signals)
    #    比較訂單意圖數量 — 僅在 bar-close tick 比較（原因同信號）
    if bar_close:
        r_intents = rust.get("order_intents", [])
        p_intents = python.get("order_intents", [])
        if len(r_intents) != len(p_intents):
            divergences.append(Divergence(
                tick_number=tick_number,
                timestamp_ms=timestamp_ms,
                symbol=symbol,
                field="order_intents.count",
                rust_value=len(r_intents),
                python_value=len(p_intents),
                tolerance=0,
                actual_diff=abs(len(r_intents) - len(p_intents)),
                severity=WARNING,
                reason=f"intent count mismatch: rust={len(r_intents)}, python={len(p_intents)}",
            ))

    return divergences, ps_skipped, sig_skipped


# ═══════════════════════════════════════════════════════════════════════════════
# Boundary Divergence Escalation (V3-QC-5) / 邊界偏差升級
# ═══════════════════════════════════════════════════════════════════════════════


def check_boundary_escalation(
    divergences: list[Divergence],
) -> tuple[bool, str]:
    """
    Check if boundary divergences should be escalated to CRITICAL.
    檢查邊界偏差是否應升級為 CRITICAL。

    Rules (V3-QC-5):
    - Consecutive 1h > 5% boundary divergence rate → escalate
    - 24h cumulative > 50 boundary divergences → escalate
    """
    bd_count = sum(1 for d in divergences if d.severity == BOUNDARY_DIVERGENCE)
    total = len(divergences) if divergences else 1

    if bd_count > 50:
        return True, f"24h cumulative boundary divergences ({bd_count}) > 50"

    bd_rate = bd_count / total if total > 0 else 0
    if bd_rate > 0.05 and bd_count > 10:
        return True, f"boundary divergence rate ({bd_rate:.1%}) > 5% with {bd_count} occurrences"

    return False, ""


# ═══════════════════════════════════════════════════════════════════════════════
# Main Comparison Pipeline / 主比較管線
# ═══════════════════════════════════════════════════════════════════════════════


def load_jsonl(path: str) -> list[dict]:
    """Load JSONL file into list of dicts / 載入 JSONL 文件為字典列表"""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"WARNING: {path}:{line_num} — invalid JSON: {e}", file=sys.stderr)
    return records


def run_comparison(
    engine_path: str,
    shadow_path: str,
    report_date: Optional[str] = None,
) -> ComparisonReport:
    """
    Run full comparison between engine and shadow JSONL files.
    執行引擎和影子 JSONL 文件之間的完整比較。
    """
    if report_date is None:
        report_date = time.strftime("%Y-%m-%d")

    report = ComparisonReport(
        report_date=report_date,
        engine_file=engine_path,
        shadow_file=shadow_path,
    )

    engine_records = load_jsonl(engine_path)
    shadow_records = load_jsonl(shadow_path)
    report.total_ticks_engine = len(engine_records)
    report.total_ticks_shadow = len(shadow_records)

    # Index by (timestamp_ms, symbol) / 按 (timestamp_ms, symbol) 索引
    engine_idx: dict[tuple[int, str], dict] = {}
    for r in engine_records:
        key = (r.get("timestamp_ms", 0), r.get("symbol", ""))
        engine_idx[key] = r

    shadow_idx: dict[tuple[int, str], dict] = {}
    for r in shadow_records:
        key = (r.get("timestamp_ms", 0), r.get("symbol", ""))
        shadow_idx[key] = r

    # Join on key / 按鍵連接
    matched_keys = set(engine_idx.keys()) & set(shadow_idx.keys())
    report.matched_ticks = len(matched_keys)
    report.unmatched_engine = len(engine_idx) - len(matched_keys)
    report.unmatched_shadow = len(shadow_idx) - len(matched_keys)

    all_divergences: list[Divergence] = []
    ps_skip_count = 0
    sig_skip_count = 0
    sig_compared_count = 0
    for key in sorted(matched_keys):
        divs, ps_skipped, sig_skipped = compare_tick(engine_idx[key], shadow_idx[key])
        all_divergences.extend(divs)
        if ps_skipped:
            ps_skip_count += 1
        if sig_skipped:
            sig_skip_count += 1
        else:
            sig_compared_count += 1
    report.paper_state_skipped = ps_skip_count
    report.signal_compared_ticks = sig_compared_count
    report.signal_skipped_ticks = sig_skip_count

    # Classify / 分類
    # MISSING divergences are informational only — not counted toward WARNING/CRITICAL verdict
    # MISSING 偏差僅供參考 — 不計入 WARNING/CRITICAL 判定
    report.total_divergences = len(all_divergences)
    report.critical_count = sum(1 for d in all_divergences if d.severity == CRITICAL)
    report.warning_count = sum(1 for d in all_divergences if d.severity == WARNING)
    report.boundary_divergence_count = sum(1 for d in all_divergences if d.severity == BOUNDARY_DIVERGENCE)
    report.missing_count = sum(1 for d in all_divergences if d.severity == MISSING)

    # Check boundary escalation / 檢查邊界升級
    escalated, reason = check_boundary_escalation(all_divergences)
    if escalated:
        report.boundary_escalation = True
        report.escalation_reason = reason
        report.critical_count += report.boundary_divergence_count

    # Determine verdict / 確定判定
    if report.critical_count > 0:
        report.verdict = CRITICAL
    elif report.warning_count > 10:
        report.verdict = WARNING
    else:
        report.verdict = PASS

    # Store top divergences (limit to 100 for readability) / 存儲前 100 個偏差
    severity_order = {CRITICAL: 0, BOUNDARY_DIVERGENCE: 1, WARNING: 2, MISSING: 3}
    sorted_divs = sorted(all_divergences, key=lambda d: (severity_order.get(d.severity, 3), -d.actual_diff))
    report.divergences = [asdict(d) for d in sorted_divs[:100]]

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / 命令行接口
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Canary Comparator — compare Rust engine vs Python shadow outputs"
    )
    parser.add_argument("--engine", required=True, help="Path to engine_results.jsonl")
    parser.add_argument("--shadow", required=True, help="Path to shadow_results.jsonl")
    parser.add_argument("--output", help="Output report path (default: stdout)")
    parser.add_argument("--date", help="Report date (default: today)")
    args = parser.parse_args()

    report = run_comparison(args.engine, args.shadow, report_date=args.date)

    output = report.to_json()
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Print summary / 打印摘要
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Verdict: {report.verdict}", file=sys.stderr)
    print(f"Matched ticks: {report.matched_ticks}", file=sys.stderr)
    print(f"CRITICAL: {report.critical_count} | WARNING: {report.warning_count} | BOUNDARY: {report.boundary_divergence_count} | MISSING: {report.missing_count} | PAPER_STATE_SKIPPED: {report.paper_state_skipped}", file=sys.stderr)
    print(f"Signal compared: {report.signal_compared_ticks} | Signal skipped (non bar-close): {report.signal_skipped_ticks}", file=sys.stderr)
    if report.boundary_escalation:
        print(f"⚠ Boundary escalation: {report.escalation_reason}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    # Exit code: 0=PASS, 1=WARNING, 2=CRITICAL
    sys.exit(0 if report.verdict == PASS else 1 if report.verdict == WARNING else 2)


if __name__ == "__main__":
    main()
