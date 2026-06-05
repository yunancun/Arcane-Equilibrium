"""residual_alpha_gate 聚焦測試。"""

from __future__ import annotations

import math

import pytest

from program_code.learning_engine.residual_alpha_gate import (
    ResidualAlphaFitWindow,
    ResidualAlphaGate,
    ResidualAlphaProtocol,
)


def _protocol(**overrides) -> ResidualAlphaProtocol:
    params = {
        "fit_window": ResidualAlphaFitWindow(
            train_start=0,
            train_end=79,
            eval_start=80,
            eval_end=119,
            label="unit_test_prior_fit",
        ),
        "required_factors": ("btc", "market"),
        "return_unit": "bps",
        "min_coverage": 0.9,
        "min_train_observations": 40,
        "min_eval_observations": 20,
        "n_trials": 4,
    }
    params.update(overrides)
    return ResidualAlphaProtocol(**params)


def _pbo_peers(*means: float) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(mean for _ in range(40)) for mean in means)


def _timestamped_pbo_peer(mean: float) -> dict[int, float]:
    return {ts: mean for ts in range(80, 120)}


# 預設 eval 窗 80..119（40 obs）；eval_end 可加寬以滿足 CSCV PBO 檢定力
# （total_trades = T*候選數 >= 320）。total 預設 140 保留既有 caller 行為。
_DEFAULT_EVAL_START = 80
_DEFAULT_EVAL_END = 119


def _factor_panel(
    *,
    eval_shift_btc: float = 0.0,
    eval_shift_market: float = 0.0,
    future_shock: float = 0.0,
    total: int = 140,
    eval_start: int = _DEFAULT_EVAL_START,
    eval_end: int = _DEFAULT_EVAL_END,
) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    for ts in range(total):
        btc = 4.0 if ts % 2 == 0 else -4.0
        market = 3.0 if (ts // 2) % 2 == 0 else -3.0
        if eval_start <= ts <= eval_end:
            btc += eval_shift_btc
            market += eval_shift_market
        if ts > eval_end:
            btc += future_shock
            market -= future_shock
        rows.append({"timestamp": ts, "btc": btc, "market": market})
    return rows


def _candidate_returns(
    factor_panel: list[dict[str, float | int]],
    *,
    alpha_bps: float,
    beta_btc: float,
    beta_market: float,
    eval_noise_bps: float = 0.0,
    eval_start: int = _DEFAULT_EVAL_START,
    eval_end: int = _DEFAULT_EVAL_END,
) -> list[dict[str, float | int]]:
    returns: list[dict[str, float | int]] = []
    for row in factor_panel:
        ts = int(row["timestamp"])
        if ts > eval_end:
            continue
        value = alpha_bps + beta_btc * float(row["btc"]) + beta_market * float(row["market"])
        if eval_start <= ts <= eval_end:
            value += eval_noise_bps
        returns.append({"timestamp": ts, "return_bps": value})
    return returns


def test_beta_trap_raw_positive_but_residual_fails():
    """beta trap：OOS raw 為正，但扣掉 prior-fit beta 後殘差必須 fail。"""
    factors = _factor_panel(eval_shift_btc=5.0, eval_shift_market=2.0)
    candidate = _candidate_returns(
        factors,
        alpha_bps=0.0,
        beta_btc=2.0,
        beta_market=1.0,
        eval_noise_bps=-0.2,
    )

    report = ResidualAlphaGate().evaluate(candidate, factors, _protocol())

    assert report.raw_mean_bps > 0.0
    assert report.residual_mean_bps <= 0.0
    assert not report.passes
    assert report.verdict == "fail"
    assert "raw_positive_residual_non_positive" in report.reasons
    assert "r_beta_retention_below_threshold" in report.reasons
    assert "beta_edge_share_above_threshold" in report.reasons


def test_true_alpha_residual_passes():
    """true alpha：factor beta 可存在，但 residual edge 應保留並 pass。

    用真 DsrGate / PboGate 後此 case 需滿足兩件事才算「真 alpha 過關」：
    (1) raw DSR(K=4) >= 0.95 — 原 beta_btc=0.4/beta_market=-0.2 的 raw Sharpe
        被真 DSR deflate 到 0.727（< 0.95），故把 beta 調弱（0.2 / -0.1）讓 raw
        edge 在正確 DSR 下仍顯著；residual edge（=alpha=2bps）不變。
    (2) CSCV PBO 檢定力足夠 — eval 窗加寬到 80 obs（80..159），4 條序列
        （候選 + 3 peer）→ total_trades = 80*4 = 320 >= min_total_trades，
        否則 PboGate 回 insufficient_power → defer（這正是真 CSCV 的正確行為）。
    這不是放寬 gate，而是讓合成 alpha 強到能通過正確統計。
    """
    eval_start, eval_end = 80, 159
    factors = _factor_panel(total=180, eval_start=eval_start, eval_end=eval_end)
    candidate = _candidate_returns(
        factors,
        alpha_bps=2.0,
        beta_btc=0.2,
        beta_market=-0.1,
        eval_start=eval_start,
        eval_end=eval_end,
    )
    # 與 eval 窗對齊的 timestamped peer；gate 自動 scope 到 eval 窗。
    peers = tuple(
        {ts: float(mean) for ts in range(eval_start, eval_end + 1)}
        for mean in (0.2, 0.5, 1.0)
    )

    report = ResidualAlphaGate().evaluate(
        candidate,
        factors,
        _protocol(
            fit_window=ResidualAlphaFitWindow(
                train_start=0,
                train_end=79,
                eval_start=eval_start,
                eval_end=eval_end,
                label="unit_test_prior_fit_wide",
            ),
            candidate_oos_returns=peers,
        ),
    )

    assert report.passes
    assert report.verdict == "pass"
    assert report.reasons == ()
    # 真 PSR(含 skew/kurt)：raw/residual 在此強 alpha 下皆 ~1.0。
    assert report.psr_raw is not None and report.psr_raw >= 0.95
    assert report.psr_residual == pytest.approx(1.0, abs=1e-9)
    # 真 DSR(E[max SR_k], K=4)：弱 beta 後 raw DSR 也 >= 0.95（實測 ~1.0）。
    assert report.dsr_raw is not None and report.dsr_raw >= 0.95
    assert report.dsr_residual == pytest.approx(1.0, abs=1e-9)
    # 真 CSCV PBO（檢定力足夠，total_trades=320）：raw/residual 皆 0.0。
    assert report.pbo_raw == pytest.approx(0.0, abs=1e-12)
    assert report.pbo_residual == pytest.approx(0.0, abs=1e-12)
    assert report.raw_mean_bps == pytest.approx(2.0, abs=1e-9)
    assert report.residual_mean_bps == pytest.approx(2.0, abs=1e-9)
    assert report.r_beta_retention == pytest.approx(1.0, abs=1e-9)
    assert report.beta_edge_share == pytest.approx(0.0, abs=1e-9)
    assert report.beta_loadings["btc"] == pytest.approx(0.2, abs=1e-9)
    assert report.beta_loadings["market"] == pytest.approx(-0.1, abs=1e-9)
    assert report.r_squared > 0.99


def test_future_factor_shock_does_not_change_prior_fit_or_early_oos_result():
    """leakage bite：未來 factor shock 不得改變早期 prior-fit residual 結果。"""
    factors = _factor_panel()
    shocked_factors = _factor_panel(future_shock=1_000_000.0)
    candidate = _candidate_returns(
        factors,
        alpha_bps=1.5,
        beta_btc=0.8,
        beta_market=0.3,
    )

    gate = ResidualAlphaGate()
    baseline = gate.evaluate(candidate, factors, _protocol())
    shocked = gate.evaluate(candidate, shocked_factors, _protocol())

    assert shocked.raw_mean_bps == pytest.approx(baseline.raw_mean_bps, abs=1e-12)
    assert shocked.residual_mean_bps == pytest.approx(
        baseline.residual_mean_bps,
        abs=1e-12,
    )
    assert shocked.r_beta_retention == pytest.approx(
        baseline.r_beta_retention,
        abs=1e-12,
    )
    assert shocked.beta_edge_share == pytest.approx(baseline.beta_edge_share, abs=1e-12)
    assert shocked.beta_loadings == pytest.approx(baseline.beta_loadings)
    assert shocked.r_squared == pytest.approx(baseline.r_squared, abs=1e-12)
    assert shocked.factor_panel_hash == baseline.factor_panel_hash


def test_future_invalid_rows_after_eval_end_do_not_change_report():
    """future row：eval_end 後的 NaN candidate/factor 不得污染 verdict/hash/report。"""
    factors = _factor_panel()
    candidate = _candidate_returns(
        factors,
        alpha_bps=1.5,
        beta_btc=0.8,
        beta_market=0.3,
    )
    dirty_candidate = [
        *candidate,
        {"timestamp": 130, "return_bps": math.nan},
        {"timestamp": 131, "not_a_return": "invalid_future_row"},
    ]
    dirty_factors = [
        *factors,
        {"timestamp": 130, "btc": math.nan, "market": math.nan},
    ]

    gate = ResidualAlphaGate()
    baseline = gate.evaluate(candidate, factors, _protocol())
    dirty = gate.evaluate(dirty_candidate, dirty_factors, _protocol())

    assert dirty.to_dict() == baseline.to_dict()


def test_future_pbo_peer_rows_after_eval_end_do_not_change_report():
    """PBO peer future row：eval_end 後資料不得改變 verdict/reasons/PBO。"""
    factors = _factor_panel()
    candidate = _candidate_returns(
        factors,
        alpha_bps=2.0,
        beta_btc=0.4,
        beta_market=-0.2,
    )
    baseline_peer = _timestamped_pbo_peer(0.2)
    baseline = ResidualAlphaGate().evaluate(
        candidate,
        factors,
        _protocol(candidate_oos_returns=(baseline_peer,)),
    )
    dirty_cases = (
        {**baseline_peer, 130: 9_999.0},
        {**baseline_peer, 130: math.nan},
        [
            *({"timestamp": ts, "return_bps": 0.2} for ts in range(80, 120)),
            {"timestamp": 130, "not_a_return": "invalid_future_row"},
        ],
    )

    for dirty_peer in dirty_cases:
        dirty = ResidualAlphaGate().evaluate(
            candidate,
            factors,
            _protocol(candidate_oos_returns=(dirty_peer,)),
        )

        assert dirty.to_dict() == baseline.to_dict()
        assert dirty.verdict == baseline.verdict
        assert dirty.reasons == baseline.reasons
        assert dirty.pbo_raw == pytest.approx(baseline.pbo_raw, abs=1e-12)
        assert dirty.pbo_residual == pytest.approx(baseline.pbo_residual, abs=1e-12)


def test_untimestamped_pbo_peer_sequence_still_requires_eval_length():
    """無 timestamp 的純 numeric peer：維持舊契約，長度必須等於 eval_len。

    弱 beta（0.2 / -0.1）讓 raw DSR 在真 DsrGate 下 >= 0.95（核心指標過關），
    使本 case 的 defer 純粹由「peer 長度不符 → pbo_not_computed」驅動，而非
    DSR 不足；否則無法檢驗長度契約。
    """
    factors = _factor_panel()
    candidate = _candidate_returns(
        factors,
        alpha_bps=2.0,
        beta_btc=0.2,
        beta_market=-0.1,
    )

    report = ResidualAlphaGate().evaluate(
        candidate,
        factors,
        _protocol(candidate_oos_returns=(tuple(0.2 for _ in range(41)),)),
    )

    assert not report.passes
    assert report.verdict == "defer_data"
    assert report.pbo_raw is None
    assert report.pbo_residual is None
    assert "pbo_candidate_returns_length_mismatch" in report.reasons
    assert "pbo_not_computed" in report.reasons


def test_insufficient_factor_coverage_downgrades_without_promotion():
    """coverage 不足：資料不足時 downgrade/defer，不得 pass。"""
    factors = _factor_panel()
    candidate = _candidate_returns(
        factors,
        alpha_bps=2.0,
        beta_btc=0.4,
        beta_market=-0.2,
    )
    incomplete_factors: list[dict[str, float | int]] = []
    for row in factors:
        if 90 <= int(row["timestamp"]) <= 119:
            incomplete_factors.append({"timestamp": row["timestamp"], "btc": row["btc"]})
        else:
            incomplete_factors.append(row)

    report = ResidualAlphaGate().evaluate(candidate, incomplete_factors, _protocol())

    assert not report.passes
    assert report.verdict == "defer_data"
    assert report.coverage["eval"] < 0.9
    assert "eval_coverage_below_min" in report.reasons
    assert "eval_observations_below_min" in report.reasons


def test_non_finite_input_fails_closed():
    """非 finite 輸入：不得被靜默丟棄後 pass。"""
    factors = _factor_panel()
    candidate = _candidate_returns(
        factors,
        alpha_bps=2.0,
        beta_btc=0.4,
        beta_market=-0.2,
    )
    candidate[10] = {"timestamp": 10, "return_bps": math.nan}

    report = ResidualAlphaGate().evaluate(candidate, factors, _protocol())

    assert not report.passes
    assert report.verdict == "fail"
    assert "non_finite_candidate_return" in report.reasons


def test_missing_pbo_evidence_defer_not_pass_even_when_core_metrics_pass():
    """PBO 缺失：核心 residual 指標過關也不得 promotion-ready。

    弱 beta（0.2 / -0.1）讓 raw DSR 在真 DsrGate 下 >= 0.95，確保核心 PSR/DSR
    指標確實全過（語意前提成立），再驗「缺 PBO peer → defer，不得 pass」。
    """
    factors = _factor_panel()
    candidate = _candidate_returns(
        factors,
        alpha_bps=2.0,
        beta_btc=0.2,
        beta_market=-0.1,
    )

    report = ResidualAlphaGate().evaluate(candidate, factors, _protocol())

    assert not report.passes
    assert report.verdict == "defer_data"
    # 核心 PSR/DSR 確實全過（不是 None、且 >= 門檻），defer 純由缺 PBO 驅動。
    assert report.psr_raw is not None and report.psr_raw >= 0.95
    assert report.psr_residual is not None and report.psr_residual >= 0.95
    assert report.dsr_raw is not None and report.dsr_raw >= 0.95
    assert report.dsr_residual is not None and report.dsr_residual >= 0.95
    assert report.pbo_raw is None
    assert report.pbo_residual is None
    assert "pbo_missing_candidate_returns" in report.reasons


def test_allow_missing_pbo_is_core_diagnostic_only():
    """core diagnostic 例外：必須顯式標註，不得默默當成完整 promotion evidence。

    弱 beta（0.2 / -0.1）讓 raw DSR 在真 DsrGate 下 >= 0.95，使核心指標確實全過，
    再驗 allow_missing_pbo_for_core_tests 旗標下「core-only 過關但顯式標註」。
    """
    factors = _factor_panel()
    candidate = _candidate_returns(
        factors,
        alpha_bps=2.0,
        beta_btc=0.2,
        beta_market=-0.1,
    )

    report = ResidualAlphaGate().evaluate(
        candidate,
        factors,
        _protocol(allow_missing_pbo_for_core_tests=True),
    )

    assert report.passes
    assert report.verdict == "pass"
    assert report.pbo_raw is None
    assert report.pbo_residual is None
    assert "pbo_missing_candidate_returns_core_diagnostic_only" in report.reasons


def test_duplicate_factor_timestamp_in_row_sequence_fails_closed():
    """factor row sequence 重複 timestamp：不得靜默覆寫。"""
    factors = _factor_panel()
    duplicated = [
        *factors[:21],
        {"timestamp": 20, "btc": 999.0, "market": -999.0},
        *factors[21:],
    ]
    candidate = _candidate_returns(
        factors,
        alpha_bps=2.0,
        beta_btc=0.4,
        beta_market=-0.2,
    )

    report = ResidualAlphaGate().evaluate(candidate, duplicated, _protocol())

    assert not report.passes
    assert report.verdict == "fail"
    assert "duplicate_factor_timestamp" in report.reasons


@pytest.mark.parametrize(
    ("fit_window", "reason"),
    [
        (
            ResidualAlphaFitWindow(
                train_start=10,
                train_end=9,
                eval_start=80,
                eval_end=119,
            ),
            "train_window_invalid",
        ),
        (
            ResidualAlphaFitWindow(
                train_start=0,
                train_end=79,
                eval_start=120,
                eval_end=119,
            ),
            "eval_window_invalid",
        ),
        (
            ResidualAlphaFitWindow(
                train_start=0,
                train_end=80,
                eval_start=80,
                eval_end=119,
            ),
            "fit_window_not_prior",
        ),
    ],
)
def test_invalid_fit_window_hard_fails(
    fit_window: ResidualAlphaFitWindow,
    reason: str,
):
    """fit_window 順序錯誤：train/eval/邊界任一錯誤都 hard fail。"""
    factors = _factor_panel()
    candidate = _candidate_returns(
        factors,
        alpha_bps=2.0,
        beta_btc=0.4,
        beta_market=-0.2,
    )

    report = ResidualAlphaGate().evaluate(
        candidate,
        factors,
        _protocol(fit_window=fit_window),
    )

    assert not report.passes
    assert report.verdict == "fail"
    assert reason in report.reasons
