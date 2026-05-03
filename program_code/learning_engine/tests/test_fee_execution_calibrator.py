"""
Tests for fee_execution_calibrator (REF-20 Wave 5 P3a-Q5).
fee_execution_calibrator 測試（REF-20 Wave 5 P3a-Q5）。

Coverage / 覆蓋:
1. Fee aggregation — observed fee_bps path returns observed mean. /
   手續費聚合 — 觀測 fee_bps 路徑回傳觀測平均。
2. Maker/taker split — counts liquidity_role correctly. /
   Maker/taker 分布 — 正確計數 liquidity_role。
3. BUSDT 110017 exclusion — verified row drop + audit count surfaced. /
   BUSDT 110017 排除 — 驗證列丟棄 + 審計計數揭露。
4. VIP tier override — different tier returns different rates. /
   VIP tier override — 不同 tier 回傳不同費率。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from program_code.learning_engine.fee_execution_calibrator import (
    BUSDT_110017_REJECT_CODE,
    BUSDT_110017_SYMBOL,
    DEFAULT_VIP_FEE_TABLE,
    ExecutionSplit,
    FeeEstimate,
    FeeExecutionCalibrator,
    LIQUIDITY_ROLE_MAKER,
    LIQUIDITY_ROLE_TAKER,
    LIQUIDITY_ROLE_UNKNOWN,
    estimate_fee_and_split,
)


# ---------------------------------------------------------------------------
# Fixtures / Fixtures
# ---------------------------------------------------------------------------


def _make_clean_fills(
    n_maker: int = 10,
    n_taker: int = 5,
    n_unknown: int = 2,
    fee_bps_observed: bool = True,
) -> pd.DataFrame:
    """
    Build clean fills with no BUSDT 110017 pollution.
    建構無 BUSDT 110017 污染的乾淨 fills。
    """
    roles = (
        [LIQUIDITY_ROLE_MAKER] * n_maker
        + [LIQUIDITY_ROLE_TAKER] * n_taker
        + [LIQUIDITY_ROLE_UNKNOWN] * n_unknown
    )
    symbols = ["BTCUSDT"] * len(roles)
    reject_codes = [None] * len(roles)

    df = pd.DataFrame(
        {
            "symbol": symbols,
            "liquidity_role": roles,
            "reject_code": reject_codes,
        }
    )
    if fee_bps_observed:
        # Synthesize fee_bps from default tier 0 rates. /
        # 從 default tier 0 費率合成 fee_bps。
        fee_map = {
            LIQUIDITY_ROLE_MAKER: 2.0,
            LIQUIDITY_ROLE_TAKER: 5.5,
            LIQUIDITY_ROLE_UNKNOWN: 3.75,
        }
        df["fee_bps"] = [fee_map[r] for r in roles]
    return df


def _make_fills_with_busdt_110017(
    n_clean: int = 10,
    n_polluted: int = 5,
) -> pd.DataFrame:
    """
    Build fills mixing clean rows + BUSDT 110017 reject-loop pollution.
    建構混合乾淨列 + BUSDT 110017 reject-loop 污染的 fills。
    """
    clean_rows = pd.DataFrame(
        {
            "symbol": ["BTCUSDT"] * n_clean,
            "liquidity_role": [LIQUIDITY_ROLE_MAKER] * n_clean,
            "reject_code": [None] * n_clean,
            "fee_bps": [2.0] * n_clean,
        }
    )
    polluted_rows = pd.DataFrame(
        {
            "symbol": [BUSDT_110017_SYMBOL] * n_polluted,
            # All taker on polluted rows would skew split downward.
            # 污染列若全 taker 會向下偏誤分布。
            "liquidity_role": [LIQUIDITY_ROLE_TAKER] * n_polluted,
            "reject_code": [BUSDT_110017_REJECT_CODE] * n_polluted,
            "fee_bps": [5.5] * n_polluted,
        }
    )
    return pd.concat([clean_rows, polluted_rows], ignore_index=True)


# ---------------------------------------------------------------------------
# Tests — fee aggregation / 手續費聚合測試
# ---------------------------------------------------------------------------


def test_fee_aggregation_observed_path():
    """
    fee_bps column present → returns observed weighted mean.
    fee_bps column 存在 → 回傳觀測加權平均。
    """
    df = _make_clean_fills(n_maker=10, n_taker=5, n_unknown=0)
    calib = FeeExecutionCalibrator()
    result = calib.estimate_fee_per_trade(df, vip_tier=0)

    assert isinstance(result, FeeEstimate)
    assert result.vip_tier == 0
    assert result.maker_fee_bps == 2.0
    assert result.taker_fee_bps == 5.5
    # Observed fee mean = (10*2.0 + 5*5.5) / 15 = (20 + 27.5) / 15 = 3.166...
    expected = (10 * 2.0 + 5 * 5.5) / 15
    assert abs(result.avg_fee_bps - expected) < 1e-9
    assert result.sample_size == 15


def test_fee_aggregation_synthetic_path_no_observed():
    """
    fee_bps column absent → use vip_tier default + liquidity_role split.
    fee_bps column 缺失 → 用 vip_tier default + liquidity_role 分布。
    """
    df = _make_clean_fills(n_maker=10, n_taker=5, n_unknown=0, fee_bps_observed=False)
    calib = FeeExecutionCalibrator()
    result = calib.estimate_fee_per_trade(df, vip_tier=0)

    # Synthetic = (10 * 2.0 + 5 * 5.5) / 15 = same as observed in this case.
    # 合成 = (10 * 2.0 + 5 * 5.5) / 15 = 此情況下與觀測相同。
    expected = (10 * 2.0 + 5 * 5.5) / 15
    assert abs(result.avg_fee_bps - expected) < 1e-9


# ---------------------------------------------------------------------------
# Tests — maker/taker split / Maker/taker 分布測試
# ---------------------------------------------------------------------------


def test_maker_taker_split_basic():
    """
    Liquidity role count matches expected pcts.
    Liquidity role 計數符合預期比例。
    """
    df = _make_clean_fills(n_maker=10, n_taker=5, n_unknown=2)
    calib = FeeExecutionCalibrator()
    split = calib.estimate_maker_taker_split(df)

    assert isinstance(split, ExecutionSplit)
    n = 10 + 5 + 2
    assert split.sample_size == n
    assert abs(split.maker_pct - 10 / n) < 1e-9
    assert abs(split.taker_pct - 5 / n) < 1e-9
    assert abs(split.unknown_pct - 2 / n) < 1e-9
    # Pcts should sum to 1.0 / 比例和應為 1.0
    assert abs(split.maker_pct + split.taker_pct + split.unknown_pct - 1.0) < 1e-9
    assert split.sample_size_excluded_busdt_110017 == 0


def test_split_sums_to_one_with_nan_role():
    """
    NaN liquidity_role values count as unknown (graceful).
    NaN liquidity_role 值計入 unknown（優雅）。
    """
    df = pd.DataFrame(
        {
            "symbol": ["BTCUSDT"] * 6,
            "liquidity_role": [
                LIQUIDITY_ROLE_MAKER,
                LIQUIDITY_ROLE_MAKER,
                LIQUIDITY_ROLE_TAKER,
                LIQUIDITY_ROLE_TAKER,
                np.nan,  # NaN role
                "",  # empty string
            ],
        }
    )
    calib = FeeExecutionCalibrator()
    split = calib.estimate_maker_taker_split(df)

    assert split.sample_size == 6
    assert abs(split.maker_pct - 2 / 6) < 1e-9
    assert abs(split.taker_pct - 2 / 6) < 1e-9
    assert abs(split.unknown_pct - 2 / 6) < 1e-9


# ---------------------------------------------------------------------------
# Tests — BUSDT 110017 exclusion / BUSDT 110017 排除測試
# ---------------------------------------------------------------------------


def test_busdt_110017_excluded_from_split():
    """
    Polluted BUSDT 110017 rows excluded; audit count surfaced separately.
    BUSDT 110017 污染列被排除；審計計數另外揭露。
    """
    df = _make_fills_with_busdt_110017(n_clean=10, n_polluted=5)
    calib = FeeExecutionCalibrator()
    split = calib.estimate_maker_taker_split(df)

    # Only 10 clean rows remain → all maker.
    # 僅 10 列乾淨保留 → 全 maker。
    assert split.sample_size == 10
    assert split.maker_pct == 1.0
    assert split.taker_pct == 0.0
    assert split.sample_size_excluded_busdt_110017 == 5  # audit transparency


def test_busdt_110017_excluded_from_fee():
    """
    BUSDT 110017 rows excluded from fee aggregation; only clean rows counted.
    BUSDT 110017 列從 fee 聚合排除；僅乾淨列計入。
    """
    df = _make_fills_with_busdt_110017(n_clean=10, n_polluted=5)
    calib = FeeExecutionCalibrator()
    fee_est = calib.estimate_fee_per_trade(df, vip_tier=0)

    # Only 10 clean maker rows → avg = 2.0 bps.
    # 僅 10 列乾淨 maker → 平均 = 2.0 bps。
    assert fee_est.sample_size == 10
    assert abs(fee_est.avg_fee_bps - 2.0) < 1e-9


def test_busdt_110017_filter_no_reject_code_column():
    """
    Missing reject_code column → no exclusion (graceful).
    缺失 reject_code column → 不排除（優雅）。
    """
    df = pd.DataFrame(
        {
            "symbol": ["BUSDT", "BTCUSDT"],
            "liquidity_role": [LIQUIDITY_ROLE_TAKER, LIQUIDITY_ROLE_MAKER],
        }
    )
    calib = FeeExecutionCalibrator()
    split = calib.estimate_maker_taker_split(df)
    # Both rows kept since reject_code column absent.
    # 兩列皆保留，因 reject_code column 缺失。
    assert split.sample_size == 2
    assert split.sample_size_excluded_busdt_110017 == 0


# ---------------------------------------------------------------------------
# Tests — VIP tier override / VIP tier override 測試
# ---------------------------------------------------------------------------


def test_vip_tier_override_returns_different_rates():
    """
    Tier 4 (Pro 1) returns lower maker/taker rates than tier 0.
    Tier 4 (Pro 1) 回傳低於 tier 0 的 maker/taker 費率。
    """
    df = _make_clean_fills(n_maker=10, n_taker=5)
    calib = FeeExecutionCalibrator()
    fee_t0 = calib.estimate_fee_per_trade(df, vip_tier=0)
    fee_t4 = calib.estimate_fee_per_trade(df, vip_tier=4)

    # Tier 4 fees lower than tier 0. / Tier 4 費率低於 tier 0。
    assert fee_t4.maker_fee_bps < fee_t0.maker_fee_bps
    assert fee_t4.taker_fee_bps < fee_t0.taker_fee_bps
    assert fee_t4.vip_tier == 4
    # Tier-default-table values per Bybit V5: tier 0 maker 2.0, taker 5.5;
    # tier 4 maker 1.0, taker 3.5.
    # Default 表（Bybit V5）：tier 0 maker 2.0 / taker 5.5；tier 4 maker 1.0 / taker 3.5。
    assert fee_t4.maker_fee_bps == 1.0
    assert fee_t4.taker_fee_bps == 3.5


def test_vip_tier_override_custom_table():
    """
    Custom override table overrides DEFAULT_VIP_FEE_TABLE.
    自定 override 表覆蓋 DEFAULT_VIP_FEE_TABLE。
    """
    custom = {
        99: {"maker_bps": 0.0, "taker_bps": 0.5},  # zero-fee VIP
    }
    calib = FeeExecutionCalibrator(vip_tier_override=custom)
    df = _make_clean_fills(n_maker=10, n_taker=5)
    fee_est = calib.estimate_fee_per_trade(df, vip_tier=99)

    assert fee_est.maker_fee_bps == 0.0
    assert fee_est.taker_fee_bps == 0.5
    assert fee_est.vip_tier == 99


def test_invalid_vip_tier_raises():
    """
    Unknown VIP tier raises ValueError.
    未知 VIP tier 拋 ValueError。
    """
    calib = FeeExecutionCalibrator()
    df = _make_clean_fills(n_maker=5, n_taker=5)
    with pytest.raises(ValueError):
        calib.estimate_fee_per_trade(df, vip_tier=999)


# ---------------------------------------------------------------------------
# Tests — module-level shortcut / 模組級捷徑測試
# ---------------------------------------------------------------------------


def test_module_level_shortcut_returns_pair():
    """
    estimate_fee_and_split returns (FeeEstimate, ExecutionSplit) tuple.
    estimate_fee_and_split 回傳 (FeeEstimate, ExecutionSplit) 元組。
    """
    df = _make_clean_fills(n_maker=10, n_taker=5, n_unknown=0)
    fee_est, split = estimate_fee_and_split(df, vip_tier=0)

    assert isinstance(fee_est, FeeEstimate)
    assert isinstance(split, ExecutionSplit)
    expected_fee = (10 * 2.0 + 5 * 5.5) / 15
    assert abs(fee_est.avg_fee_bps - expected_fee) < 1e-9
    assert split.sample_size == 15
