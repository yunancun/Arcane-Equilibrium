"""Sprint 1A-ζ Phase 3b AC-7 — cross-language 1e-4 fixture (proof-of-concept).

MODULE_NOTE
模塊用途：
  AC-7 cross-language 1e-4 容差 fixture minimal harness。spec §AC-7 字面要求
  `engine_cpu_pct` 5 sample window mean / sigma Rust ↔ Python replay 1e-4 容差。
  Sprint 1A-ζ spike scope health/mod.rs 沒實作 window 算法（只 4-state band
  classifier），spec §5.3 已預期 AC-7 可能 partial PASS — H-18 cross-language
  fixture harness 全套延 Sprint 1B。本 fixture 提供 PoC：
  - 2 條同算法獨立 Python 實作 (naive sum + Welford)；diff < 1e-4
  - 證明 algorithm itself well-defined + 數字 deterministic
  - Sprint 1B 補 Rust window IMPL 時可以此 fixture 對齊（換 Welford for Rust）

設計：
  - input: [10.0, 20.0, 30.0, 25.0, 15.0]（5 sample，spec § AC-7 line 277）
  - mean = 20.0
  - sample stddev (ddof=1) = sqrt(((10-20)²+(20-20)²+(30-20)²+(25-20)²+(15-20)²)/4)
                          = sqrt(250/4) = sqrt(62.5) ≈ 7.905694150420949
  - population stddev (ddof=0) = sqrt(50.0) ≈ 7.0710678118654755

  2 條獨立實作互驗 + numpy 第三方對齊 → cross-impl consistency 數位 fingerprint。

依賴: numpy（std lib + venv 內 pre-existing dep）

硬邊界：
  - fixture 純算術；不接 PG / Rust / IPC
  - test 必 import-only；不污染 production code path
  - 容差 1e-4 對齊 spec § AC-7
"""

from __future__ import annotations

import math

import numpy as np
import pytest


# 對齊 spec §AC-7 line 277 「`engine_cpu_pct` 算 5 sample window」
SPIKE_SAMPLE: list[float] = [10.0, 20.0, 30.0, 25.0, 15.0]

# 預期 mean = 20.0
EXPECTED_MEAN: float = 20.0
# Sample stddev (ddof=1): sqrt(sum((x-mean)^2) / (N-1)) = sqrt(250/4) = sqrt(62.5)
EXPECTED_SAMPLE_STD: float = math.sqrt(62.5)
# Population stddev (ddof=0): sqrt(sum((x-mean)^2) / N) = sqrt(50.0)
EXPECTED_POP_STD: float = math.sqrt(50.0)

# AC-7 容差
TOLERANCE: float = 1e-4


def python_naive_mean_sigma(samples: list[float], ddof: int = 1) -> tuple[float, float]:
    """Naive 兩遍法 (two-pass)：先算 mean,再算 variance。

    為什麼: 算法 well-known、簡單、易 cross-language 對齊 (Rust 端也可直接寫
    同樣 two-pass)。但浮點累加 catastrophic cancellation 風險,需配合 Welford
    互驗。
    """
    n = len(samples)
    if n == 0:
        return 0.0, 0.0
    if n - ddof <= 0:
        raise ValueError(f"n={n} ddof={ddof}: ddof must be < n")

    mean = sum(samples) / n
    sq_diff_sum = sum((x - mean) ** 2 for x in samples)
    var = sq_diff_sum / (n - ddof)
    return mean, math.sqrt(var)


def python_welford_mean_sigma(samples: list[float], ddof: int = 1) -> tuple[float, float]:
    """Welford online algorithm: numerical-stable single-pass mean + variance。

    為什麼: Rust hot-path window 算法首選 (incremental update,numerically
    stable);本 PoC 對齊「Rust IMPL 未來必走 Welford」假設。
    """
    n = 0
    mean = 0.0
    m2 = 0.0
    for x in samples:
        n += 1
        delta = x - mean
        mean += delta / n
        delta2 = x - mean
        m2 += delta * delta2
    if n - ddof <= 0:
        raise ValueError(f"n={n} ddof={ddof}: ddof must be < n")
    var = m2 / (n - ddof)
    return mean, math.sqrt(var)


def numpy_mean_sigma(samples: list[float], ddof: int = 1) -> tuple[float, float]:
    """numpy 第三方對齊 (確保 Python 兩條實作不是 trivially 共錯)。"""
    arr = np.asarray(samples, dtype=np.float64)
    return float(arr.mean()), float(arr.std(ddof=ddof))


def test_cpu_pct_window_mean_matches_expected() -> None:
    """spec §AC-7 line 277:5 sample window mean = 20.0。"""
    mean_naive, _ = python_naive_mean_sigma(SPIKE_SAMPLE)
    mean_welford, _ = python_welford_mean_sigma(SPIKE_SAMPLE)
    mean_numpy, _ = numpy_mean_sigma(SPIKE_SAMPLE)

    assert abs(mean_naive - EXPECTED_MEAN) < TOLERANCE, (
        f"naive mean diverges: got {mean_naive}, expected {EXPECTED_MEAN}"
    )
    assert abs(mean_welford - EXPECTED_MEAN) < TOLERANCE, (
        f"welford mean diverges: got {mean_welford}, expected {EXPECTED_MEAN}"
    )
    assert abs(mean_numpy - EXPECTED_MEAN) < TOLERANCE, (
        f"numpy mean diverges: got {mean_numpy}, expected {EXPECTED_MEAN}"
    )


def test_cpu_pct_window_sample_sigma_matches_expected() -> None:
    """spec §AC-7:5 sample sample stddev (ddof=1)。"""
    _, sigma_naive = python_naive_mean_sigma(SPIKE_SAMPLE, ddof=1)
    _, sigma_welford = python_welford_mean_sigma(SPIKE_SAMPLE, ddof=1)
    _, sigma_numpy = numpy_mean_sigma(SPIKE_SAMPLE, ddof=1)

    assert abs(sigma_naive - EXPECTED_SAMPLE_STD) < TOLERANCE, (
        f"naive sample sigma diverges: got {sigma_naive}, expected {EXPECTED_SAMPLE_STD}"
    )
    assert abs(sigma_welford - EXPECTED_SAMPLE_STD) < TOLERANCE, (
        f"welford sample sigma diverges: got {sigma_welford}, expected {EXPECTED_SAMPLE_STD}"
    )
    assert abs(sigma_numpy - EXPECTED_SAMPLE_STD) < TOLERANCE, (
        f"numpy sample sigma diverges: got {sigma_numpy}, expected {EXPECTED_SAMPLE_STD}"
    )


def test_cpu_pct_window_naive_vs_welford_cross_impl_1e_4() -> None:
    """Cross-impl 1e-4 容差:naive two-pass vs Welford online,互驗 algorithm
    本身 deterministic + numerically equivalent。

    為什麼:Sprint 1B Rust 端 window IMPL 假設走 Welford;本 fixture 已證明
    naive (Python ref) 與 Welford (Rust 假設) 在容差內等價,Sprint 1B Rust
    IMPL 接此 fixture 時直接通過。
    """
    mean_naive, sigma_naive = python_naive_mean_sigma(SPIKE_SAMPLE, ddof=1)
    mean_welford, sigma_welford = python_welford_mean_sigma(SPIKE_SAMPLE, ddof=1)

    assert abs(mean_naive - mean_welford) < TOLERANCE, (
        f"cross-impl mean diverges: naive={mean_naive}, welford={mean_welford}, "
        f"diff={abs(mean_naive - mean_welford)} >= 1e-4"
    )
    assert abs(sigma_naive - sigma_welford) < TOLERANCE, (
        f"cross-impl sigma diverges: naive={sigma_naive}, welford={sigma_welford}, "
        f"diff={abs(sigma_naive - sigma_welford)} >= 1e-4"
    )


def test_cpu_pct_window_python_vs_numpy_cross_impl_1e_4() -> None:
    """Python (Welford) vs numpy reference 1e-4:確保 Python 實作非 trivially
    與自己錯。第三方 well-tested 庫 numpy 作 ground truth fallback。"""
    mean_welford, sigma_welford = python_welford_mean_sigma(SPIKE_SAMPLE, ddof=1)
    mean_numpy, sigma_numpy = numpy_mean_sigma(SPIKE_SAMPLE, ddof=1)

    assert abs(mean_welford - mean_numpy) < TOLERANCE, (
        f"python vs numpy mean diverges: py={mean_welford}, np={mean_numpy}"
    )
    assert abs(sigma_welford - sigma_numpy) < TOLERANCE, (
        f"python vs numpy sigma diverges: py={sigma_welford}, np={sigma_numpy}"
    )


@pytest.mark.parametrize(
    "samples,expected_mean,expected_sigma_ddof1",
    [
        ([10.0, 20.0, 30.0, 25.0, 15.0], 20.0, math.sqrt(62.5)),  # spec §AC-7 sample
        ([50.0, 50.0, 50.0, 50.0, 50.0], 50.0, 0.0),  # constant edge case
        # alternating: mean=40, sum_sq=(40²×3)+(60²×2)=4800+7200=12000, sample var=12000/(5-1)=3000
        ([0.0, 100.0, 0.0, 100.0, 0.0], 40.0, math.sqrt(3000.0)),
    ],
)
def test_cpu_pct_window_parametric_1e_4(
    samples: list[float], expected_mean: float, expected_sigma_ddof1: float
) -> None:
    """3 種 sample 圖譜驗 algorithm robust。"""
    mean_welford, sigma_welford = python_welford_mean_sigma(samples, ddof=1)
    assert abs(mean_welford - expected_mean) < TOLERANCE
    assert abs(sigma_welford - expected_sigma_ddof1) < TOLERANCE


if __name__ == "__main__":
    # 直接 python3 spike_cross_lang_fixture.py 跑 visual check
    mean_naive, sigma_naive = python_naive_mean_sigma(SPIKE_SAMPLE)
    mean_welford, sigma_welford = python_welford_mean_sigma(SPIKE_SAMPLE)
    mean_numpy, sigma_numpy = numpy_mean_sigma(SPIKE_SAMPLE)
    print(f"SPIKE_SAMPLE = {SPIKE_SAMPLE}")
    print(f"naive   : mean={mean_naive:.15f} sigma={sigma_naive:.15f}")
    print(f"welford : mean={mean_welford:.15f} sigma={sigma_welford:.15f}")
    print(f"numpy   : mean={mean_numpy:.15f} sigma={sigma_numpy:.15f}")
    print(f"expected: mean={EXPECTED_MEAN:.15f} sigma={EXPECTED_SAMPLE_STD:.15f}")
