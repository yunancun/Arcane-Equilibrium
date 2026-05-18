"""_common.py unit tests — Wilson CI + verdict ladder + helpers。

MODULE_NOTE:
  驗證 Wilson 95% CI 對齊 spec §11.4 AC-14 期望 + 三段 verdict ladder。
  Wilson 參考值取 standard binomial proportion CI 表格（z=1.96）。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

# 添加 healthchecks 目錄到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import (  # noqa: E402
    VERDICT_FAIL,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_PASS,
    VERDICT_WARN,
    fill_rate_verdict,
    severity_max,
    split_engine_modes,
    wilson_ci_95,
)


class TestWilsonCI:
    """Wilson 95% binomial CI 對齊 reference 表格。"""

    def test_zero_total_returns_zero_pair(self):
        assert wilson_ci_95(0, 0) == (0.0, 0.0)

    def test_negative_total_returns_zero_pair(self):
        # defensive: 不應發生但接受
        assert wilson_ci_95(0, -1) == (0.0, 0.0)

    def test_50_of_100_centered_at_half(self):
        """n=100, k=50 → 中心 0.5；標準 Wilson 結果約 (0.404, 0.596)。

        Reference: standard binomial Wilson z=1.96 表（多 epidemiology 教科書）
        n=100 p=0.5 → CI [0.404, 0.596]，誤差 ±0.001
        """
        lower, upper = wilson_ci_95(50, 100)
        assert math.isclose(lower, 0.404, abs_tol=0.005)
        assert math.isclose(upper, 0.596, abs_tol=0.005)

    def test_7_of_10_small_n(self):
        """n=10, k=7 → CI 應較寬；reference 約 (0.397, 0.892)。"""
        lower, upper = wilson_ci_95(7, 10)
        assert math.isclose(lower, 0.397, abs_tol=0.01)
        assert math.isclose(upper, 0.892, abs_tol=0.01)

    def test_0_of_30_no_panic(self):
        """k=0 應回傳 (0.0, upper>0) 不 panic；upper 反映 N=30 的不確定性。"""
        lower, upper = wilson_ci_95(0, 30)
        assert math.isclose(lower, 0.0, abs_tol=0.001)
        # n=30 k=0 → Wilson upper ≈ 0.115（reference）
        assert math.isclose(upper, 0.115, abs_tol=0.01)

    def test_30_of_30_no_panic(self):
        """k=n → lower>0 upper=1.0；reference n=30 k=30 → CI (0.885, 1.0)。"""
        lower, upper = wilson_ci_95(30, 30)
        assert math.isclose(lower, 0.885, abs_tol=0.01)
        assert math.isclose(upper, 1.0, abs_tol=0.001)

    def test_monotone_increasing_in_p(self):
        """同 N 下 success 增加 → CI 中心右移。"""
        l1, u1 = wilson_ci_95(20, 100)
        l2, u2 = wilson_ci_95(70, 100)
        assert l2 > l1
        assert u2 > u1


class TestFillRateVerdict:
    """fill_rate_verdict ladder 對齊 spec §8.1 line 511-519。"""

    def test_below_min_sample_returns_insufficient(self):
        verdict, rate, lo, hi = fill_rate_verdict(5, 10, min_sample=30)
        assert verdict == VERDICT_INSUFFICIENT_SAMPLE
        assert rate == 0.5

    def test_pass_when_lower_above_threshold(self):
        # n=100 k=80 → Wilson 約 (0.711, 0.866)；lower=0.711 ≥ 0.60 → PASS
        verdict, rate, lo, hi = fill_rate_verdict(
            80, 100, min_sample=30, pass_lower=0.60, warn_lower=0.40
        )
        assert verdict == VERDICT_PASS
        assert lo >= 0.60

    def test_fail_when_upper_below_warn(self):
        # n=100 k=20 → Wilson 約 (0.133, 0.288)；upper=0.288 < 0.40 → FAIL
        verdict, rate, lo, hi = fill_rate_verdict(
            20, 100, min_sample=30, pass_lower=0.60, warn_lower=0.40
        )
        assert verdict == VERDICT_FAIL
        assert hi < 0.40

    def test_warn_middle_band(self):
        # n=100 k=50 → Wilson (0.404, 0.596)；lower<0.60 + upper>0.40 → WARN
        verdict, rate, lo, hi = fill_rate_verdict(
            50, 100, min_sample=30, pass_lower=0.60, warn_lower=0.40
        )
        assert verdict == VERDICT_WARN

    def test_alternative_thresholds_25_target(self):
        """AC-19 conservative 25 / target 50 ladder（caller 自選）。"""
        # n=100 k=30 → Wilson (0.218, 0.398)；lower=0.218 < 0.50; upper=0.398 > 0.25 → WARN
        verdict, rate, lo, hi = fill_rate_verdict(
            30, 100, min_sample=30, pass_lower=0.50, warn_lower=0.25
        )
        assert verdict == VERDICT_WARN


class TestSeverityMax:
    def test_pass_under_warn(self):
        assert severity_max(VERDICT_PASS, VERDICT_WARN) == VERDICT_WARN

    def test_warn_under_fail(self):
        assert severity_max(VERDICT_WARN, VERDICT_FAIL) == VERDICT_FAIL

    def test_fail_over_anything(self):
        assert severity_max(VERDICT_FAIL, VERDICT_PASS) == VERDICT_FAIL

    def test_insufficient_above_pass(self):
        # INSUFFICIENT_SAMPLE > PASS（一個 cell 不夠 sample 拉低整體至少到 INSUFFICIENT）
        assert severity_max(VERDICT_PASS, VERDICT_INSUFFICIENT_SAMPLE) == VERDICT_INSUFFICIENT_SAMPLE

    def test_warn_above_insufficient(self):
        assert severity_max(VERDICT_INSUFFICIENT_SAMPLE, VERDICT_WARN) == VERDICT_WARN


class TestSplitEngineModes:
    def test_basic(self):
        assert split_engine_modes("demo,live_demo") == ["demo", "live_demo"]

    def test_whitespace_stripped(self):
        assert split_engine_modes("demo , live_demo , paper") == [
            "demo",
            "live_demo",
            "paper",
        ]

    def test_empty_segments_dropped(self):
        assert split_engine_modes("demo,,live_demo,") == ["demo", "live_demo"]
