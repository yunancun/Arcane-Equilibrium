"""
Tests for half_life_estimator (REF-20 Wave 5 P3a-Q1).
half_life_estimator 測試（REF-20 Wave 5 P3a-Q1）。

Coverage / 覆蓋:
1. PnL decay PASS — synthetic exp-decay fixture, fit returns correct half_life. /
   PnL decay 通過 — 合成指數衰減 fixture，擬合回傳正確 half_life。
2. Sharpe decay PASS — when PnL is flat noise, Sharpe series shows decay. /
   Sharpe decay 通過 — 當 PnL 為平坦噪音，Sharpe 序列顯示衰減。
3. Default fallback (n<30) — small sample → default_14d. /
   Default fallback（n<30）— 小樣本 → default_14d。
4. Default fallback (high p-value) — both fits fail significance gate. /
   Default fallback（高 p-value）— 兩擬合皆未通過顯著性門檻。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from program_code.learning_engine.half_life_estimator import (
    DEFAULT_HALF_LIFE_DAYS,
    HalfLifeEstimator,
    HalfLifeResult,
    estimate_half_life,
)


# ---------------------------------------------------------------------------
# Fixtures / Fixtures
# ---------------------------------------------------------------------------


def _make_decay_fills(
    n: int,
    true_half_life_days: float,
    a0: float = 50.0,
    noise_std: float = 1.0,
    seed: int = 42,
    duration_days: float = 60.0,
    add_sharpe: bool = True,
) -> pd.DataFrame:
    """
    Generate synthetic fills with known exponential decay in net_bps_after_fees.
    生成合成 fills，net_bps_after_fees 為已知指數衰減。
    """
    rng = np.random.default_rng(seed)
    t_days = np.linspace(0.0, duration_days, n)
    decay_y = a0 * np.exp(-t_days * np.log(2.0) / true_half_life_days)
    noise = rng.normal(0.0, noise_std, size=n)
    net_bps = decay_y + noise

    base_ts = pd.Timestamp("2026-04-01T00:00:00Z")
    ts = [base_ts + pd.Timedelta(days=float(d)) for d in t_days]

    df = pd.DataFrame(
        {
            "ts": ts,
            "net_bps_after_fees": net_bps,
        }
    )
    if add_sharpe:
        # Sharpe series independently noisy / Sharpe 序列獨立噪音
        df["sharpe_60d_window"] = rng.normal(0.5, 0.1, size=n)
    return df


def _make_flat_noise_fills(
    n: int,
    seed: int = 7,
    duration_days: float = 60.0,
) -> pd.DataFrame:
    """
    Pure white noise fills with no decay structure — used to test fallback.
    純白噪音 fills，無衰減結構 — 用於測試 fallback。
    """
    rng = np.random.default_rng(seed)
    t_days = np.linspace(0.0, duration_days, n)
    noise = rng.normal(0.0, 5.0, size=n)
    base_ts = pd.Timestamp("2026-04-01T00:00:00Z")
    ts = [base_ts + pd.Timedelta(days=float(d)) for d in t_days]
    return pd.DataFrame(
        {
            "ts": ts,
            "net_bps_after_fees": noise,
            "sharpe_60d_window": rng.normal(0.0, 0.05, size=n),
        }
    )


# ---------------------------------------------------------------------------
# Tests / 測試
# ---------------------------------------------------------------------------


def test_pnl_decay_pass():
    """
    PnL decay fit recovers true half-life within tolerance.
    PnL decay 擬合在容差內還原真實 half_life。
    """
    true_hl = 7.0
    df = _make_decay_fills(n=200, true_half_life_days=true_hl, noise_std=0.5)

    estimator = HalfLifeEstimator()
    result = estimator.estimate(df, method="pnl_decay")

    assert isinstance(result, HalfLifeResult)
    assert result.method_used == "pnl_decay"
    assert result.sample_size == 200
    assert result.fit_p_value is not None
    # Fit p-value MUST be highly significant (well below 0.10).
    # 擬合 p-value 必高度顯著（遠低於 0.10）。
    assert result.fit_p_value < 0.10, f"p_value={result.fit_p_value} should be < 0.10"
    # Half-life recovered within 25% tolerance (allows for finite-sample noise).
    # 半衰期在 25% 容差內還原（容許有限樣本噪音）。
    assert abs(result.half_life_days - true_hl) / true_hl < 0.25, (
        f"recovered={result.half_life_days}, true={true_hl}"
    )
    assert not result.low_confidence


def test_sharpe_decay_pass():
    """
    Sharpe decay fit succeeds when sharpe_60d_window has clear decay.
    當 sharpe_60d_window 有清晰衰減時，Sharpe decay 擬合成功。
    """
    rng = np.random.default_rng(123)
    n = 200
    true_hl = 5.0
    duration = 30.0
    t_days = np.linspace(0.0, duration, n)
    sharpe_y = 2.0 * np.exp(-t_days * np.log(2.0) / true_hl) + rng.normal(0.0, 0.05, n)
    base_ts = pd.Timestamp("2026-04-01T00:00:00Z")
    ts = [base_ts + pd.Timedelta(days=float(d)) for d in t_days]

    df = pd.DataFrame(
        {
            "ts": ts,
            "net_bps_after_fees": rng.normal(0.0, 1.0, n),  # flat
            "sharpe_60d_window": sharpe_y,
        }
    )

    estimator = HalfLifeEstimator()
    result = estimator.estimate(df, method="sharpe_decay")

    assert result.method_used == "sharpe_decay"
    assert result.fit_p_value is not None
    assert result.fit_p_value < 0.10
    assert abs(result.half_life_days - true_hl) / true_hl < 0.30
    assert not result.low_confidence


def test_default_fallback_small_sample():
    """
    n < min_sample_size triggers default_14d immediately (low_confidence=True).
    n < min_sample_size 立即觸發 default_14d（low_confidence=True）。
    """
    df = _make_decay_fills(n=20, true_half_life_days=7.0)
    estimator = HalfLifeEstimator(min_sample_size=30)
    result = estimator.estimate_with_fallback(df)

    assert result.method_used == "default_14d"
    assert result.half_life_days == DEFAULT_HALF_LIFE_DAYS
    assert result.fit_p_value is None
    assert result.sample_size == 20
    assert result.low_confidence is True


def test_default_fallback_high_p_value():
    """
    Pure noise → both PnL and Sharpe fits fail p-value gate → default_14d.
    純噪音 → PnL 與 Sharpe 擬合皆失敗 p-value 門檻 → default_14d。
    """
    df = _make_flat_noise_fills(n=100)
    estimator = HalfLifeEstimator(p_value_threshold=0.10)
    result = estimator.estimate_with_fallback(df)

    # On pure noise, the chain should fall through to default_14d.
    # 在純噪音上，鏈應落到 default_14d。
    assert result.method_used == "default_14d"
    assert result.half_life_days == DEFAULT_HALF_LIFE_DAYS
    assert result.low_confidence is True


def test_module_level_shortcut():
    """
    estimate_half_life convenience function returns equivalent result.
    estimate_half_life 便利函數回傳等效結果。
    """
    df = _make_decay_fills(n=150, true_half_life_days=10.0, noise_std=0.5)
    direct_result = HalfLifeEstimator().estimate_with_fallback(df)
    shortcut_result = estimate_half_life(df)

    assert direct_result.method_used == shortcut_result.method_used
    # half_life_days should be equal under same seed (no random state leaks).
    # 同 seed 下 half_life_days 應相等（無隨機狀態洩漏）。
    assert abs(direct_result.half_life_days - shortcut_result.half_life_days) < 1e-9


def test_invalid_method_raises():
    """Invalid method name raises ValueError. / 無效方法名稱拋 ValueError。"""
    df = _make_decay_fills(n=100, true_half_life_days=7.0)
    estimator = HalfLifeEstimator()
    with pytest.raises(ValueError):
        estimator.estimate(df, method="bogus_method")  # type: ignore[arg-type]


def test_half_life_clamped_within_bounds():
    """
    Returned half_life always within [HALF_LIFE_MIN_DAYS, HALF_LIFE_MAX_DAYS].
    回傳 half_life 恆在邊界內。
    """
    from program_code.learning_engine.half_life_estimator import (
        HALF_LIFE_MAX_DAYS,
        HALF_LIFE_MIN_DAYS,
    )

    df = _make_decay_fills(n=200, true_half_life_days=7.0, noise_std=0.5)
    result = HalfLifeEstimator().estimate_with_fallback(df)
    assert HALF_LIFE_MIN_DAYS <= result.half_life_days <= HALF_LIFE_MAX_DAYS
