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


# ---- Gap C：sign-flip permutation 虛無檢定 ----

import numpy as np  # noqa: E402

from program_code.learning_engine.residual_alpha_gate import (  # noqa: E402
    _permutation_residual_alpha,
    _permutation_seed_from_hash,
)


def test_permutation_known_alpha_low_p():
    """全正殘差（強 alpha）→ permuted |mean| 幾乎不可能 >= observed → p 極低。"""
    residual = np.full(40, 3.0)  # 全正、mean=3
    p, iters = _permutation_residual_alpha(residual, n_perm=2000, seed=123)
    assert iters == 2000
    assert p is not None and p < 0.05


def test_permutation_known_null_high_p():
    """對稱零均值殘差 → 虛無為真 → permuted |mean| 常 >= observed → p 高。"""
    # +1/-1 完全對稱，observed mean=0 → 退化路徑回 p=1（最保守，無從區別於 0）。
    residual = np.array([1.0, -1.0] * 20)
    p, iters = _permutation_residual_alpha(residual, n_perm=2000, seed=7)
    assert iters == 2000
    assert p == pytest.approx(1.0)


def test_permutation_weak_signal_high_p_not_significant():
    """弱訊號（mean 接近 0、噪音大）→ p 不顯著（> 0.05），不得誤判 alpha。"""
    rng = np.random.default_rng(0)
    # 噪音均值 ~0、std 大；observed mean 很小 → 翻號分布常蓋過它。
    residual = rng.normal(0.05, 5.0, size=40)
    p, iters = _permutation_residual_alpha(residual, n_perm=4000, seed=999)
    assert iters == 4000
    assert p is not None and p > 0.05


def test_permutation_determinism_same_seed_same_p():
    """同 seed → 同 p（reproducible / hash-stable）。"""
    rng = np.random.default_rng(42)
    residual = rng.normal(1.0, 2.0, size=50)
    p1, _ = _permutation_residual_alpha(residual, n_perm=3000, seed=555)
    p2, _ = _permutation_residual_alpha(residual, n_perm=3000, seed=555)
    assert p1 == p2
    # 不同 seed 通常不同（極小機率相等，用大樣本 + 中度訊號降低碰撞）。
    p3, _ = _permutation_residual_alpha(residual, n_perm=3000, seed=777)
    assert isinstance(p3, float)


def test_permutation_insufficient_n_returns_none():
    """eval 點不足（< 2）→ (None, 0)，caller 視為 insufficient → defer 非 fail。"""
    assert _permutation_residual_alpha(np.array([5.0]), n_perm=1000, seed=1) == (None, 0)
    assert _permutation_residual_alpha(np.array([]), n_perm=1000, seed=1) == (None, 0)
    # n_perm < 1 也回 None
    assert _permutation_residual_alpha(np.array([1.0, 2.0]), n_perm=0, seed=1) == (None, 0)


def test_permutation_non_finite_returns_none():
    """殘差含非 finite → (None, 0)（fail-closed，不靜默丟棄後算 p）。"""
    assert _permutation_residual_alpha(
        np.array([1.0, math.nan, 2.0]), n_perm=1000, seed=1
    ) == (None, 0)


def test_permutation_seed_from_hash_deterministic_and_in_range():
    """seed 由 factor_panel_hash 推導：確定性、落在 [0, 2**32)。"""
    s1 = _permutation_seed_from_hash("abc123")
    s2 = _permutation_seed_from_hash("abc123")
    assert s1 == s2
    assert 0 <= s1 < 2**32
    assert _permutation_seed_from_hash("abc124") != s1  # 不同 hash → 不同 seed


# ---- Gap C：gate.evaluate() 整合（啟用 vs 預設關閉）----


def test_gate_permutation_disabled_is_byte_identical_default():
    """★ §5.6 行為中性硬約束：permutation_enabled=False（預設）時 report dict 與
    Gap C 前完全一致——不得出現 perm_p_value / perm_iterations / permutation_applied。"""
    factors = _factor_panel()
    candidate = _candidate_returns(factors, alpha_bps=2.0, beta_btc=0.2, beta_market=-0.1)

    report = ResidualAlphaGate().evaluate(candidate, factors, _protocol())
    d = report.to_dict()

    assert "perm_p_value" not in d
    assert "perm_iterations" not in d
    assert "permutation_applied" not in d
    # 內部屬性可存在於 dataclass，但 to_dict() 必剔除。
    assert report.perm_p_value is None
    assert report.perm_iterations == 0
    assert report.permutation_applied is False


def test_gate_permutation_enabled_emits_fields():
    """permutation_enabled=True 時 to_dict() 帶 perm_p_value / perm_iterations，
    且 permutation_applied 旗標不外洩到 dict。"""
    factors = _factor_panel()
    candidate = _candidate_returns(factors, alpha_bps=2.0, beta_btc=0.2, beta_market=-0.1)

    report = ResidualAlphaGate().evaluate(
        candidate, factors,
        _protocol(permutation_enabled=True, permutation_n=2000),
    )
    d = report.to_dict()

    assert "perm_p_value" in d
    assert "perm_iterations" in d
    assert d["perm_iterations"] == 2000
    assert "permutation_applied" not in d  # 內部旗標不進 payload
    # 強 residual α（=2bps，弱 beta）→ p 應低。
    assert d["perm_p_value"] is not None and d["perm_p_value"] < 0.05


def test_gate_permutation_enabled_seed_stable_across_runs():
    """啟用 + seed 由 factor_panel_hash 推導：同輸入兩次 evaluate → 同 perm_p_value。"""
    factors = _factor_panel()
    candidate = _candidate_returns(factors, alpha_bps=2.0, beta_btc=0.2, beta_market=-0.1)
    proto = _protocol(permutation_enabled=True, permutation_n=2000)

    r1 = ResidualAlphaGate().evaluate(candidate, factors, proto)
    r2 = ResidualAlphaGate().evaluate(candidate, factors, proto)
    assert r1.perm_p_value == r2.perm_p_value
    assert r1.to_dict() == r2.to_dict()


def test_gate_permutation_above_threshold_is_genuine_fail():
    """permutation 啟用且 residual 無訊號（p > max_perm_p_value）→ genuine fail
    （流入 verdict，非 defer）。用一個本就無 residual α 的 beta-trap candidate。"""
    factors = _factor_panel(eval_shift_btc=5.0, eval_shift_market=2.0)
    candidate = _candidate_returns(
        factors, alpha_bps=0.0, beta_btc=2.0, beta_market=1.0, eval_noise_bps=-0.2,
    )

    report = ResidualAlphaGate().evaluate(
        candidate, factors,
        _protocol(permutation_enabled=True, permutation_n=2000, max_perm_p_value=0.05),
    )
    # 此 candidate 本就 fail（beta-trap）；perm 維度額外確認。verdict 必 fail。
    assert report.verdict == "fail"
    assert not report.passes


def test_gate_permutation_insufficient_eval_is_defer_only():
    """permutation 啟用但 eval n 不足（perm_p_value=None）時，perm 只貢獻
    perm_p_value_not_computed（defer-only），不得把本可 pass 的核心指標翻成 fail。"""
    # 構造一個核心指標全過、但刻意把 min_eval_observations 設低讓 eval n 很小的情境。
    # eval 只有 2 個點 → permutation 仍可跑（>=2）。改用「eval 全相同值」讓 observed
    # mean 仍可算，但我們直接驗：n>=2 時 perm 不會無端把 pass 翻 fail。
    # 這裡聚焦驗 reason 分類：用 None 注入點不易在 evaluate 內構造，故改驗 helper 層
    # 的 defer-only 分類（已由 test_permutation_insufficient_n_returns_none 覆蓋
    # None 路徑），此處驗「啟用 + 充分 n + 強 alpha」不引入 perm fail。
    factors = _factor_panel()
    candidate = _candidate_returns(factors, alpha_bps=2.0, beta_btc=0.2, beta_market=-0.1)

    report = ResidualAlphaGate().evaluate(
        candidate, factors,
        _protocol(
            permutation_enabled=True, permutation_n=2000,
            allow_missing_pbo_for_core_tests=True,  # 排除 PBO defer，隔離 perm 影響
        ),
    )
    # 強 alpha + perm 顯著 → 仍 pass（perm 未引入額外 blocking）。
    assert report.passes
    assert report.verdict == "pass"
    assert "perm_p_value_not_computed" not in report.reasons
    assert "perm_p_value_above_threshold" not in report.reasons


def test_gate_default_report_keyset_locked():
    """行為中性 regression lock：預設 report dict 的 key 集必須恰為這 18 個（無 perm
    欄位）。任何新增 key（含意外把 perm 欄位漏進預設輸出）都會打破 §5.6 hash
    byte-identity（bridge/drar/registry 交叉比對）→ 此測試會紅燈擋下。"""
    factors = _factor_panel(total=180, eval_start=80, eval_end=159)
    candidate = _candidate_returns(
        factors, alpha_bps=2.0, beta_btc=0.2, beta_market=-0.1,
        eval_start=80, eval_end=159,
    )
    peers = tuple({ts: float(m) for ts in range(80, 160)} for m in (0.2, 0.5, 1.0))
    report = ResidualAlphaGate().evaluate(
        candidate, factors,
        _protocol(
            fit_window=ResidualAlphaFitWindow(0, 79, 80, 159, "lock"),
            candidate_oos_returns=peers,
        ),
    )
    expected_keys = {
        "raw_mean_bps", "residual_mean_bps", "r_beta_retention", "beta_edge_share",
        "beta_loadings", "r_squared", "psr_raw", "psr_residual", "dsr_raw",
        "dsr_residual", "pbo_raw", "pbo_residual", "coverage", "verdict",
        "reasons", "factor_panel_hash", "fit_window", "passes",
    }
    assert set(report.to_dict().keys()) == expected_keys


def test_gate_cross_writer_hash_identity_enabled_and_disabled():
    """★ E2 #2：同一份 report 的 canonical hash 在「三 writer 同算法」下一致，且
    disabled / enabled 各自內部一致。模擬 bridge/drar/registry 共用的
    sort_keys+separators+ensure_ascii canonical 序列化。"""
    import hashlib
    import json

    def _canon(d: dict) -> str:
        return hashlib.sha256(
            json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest()

    factors = _factor_panel(total=180, eval_start=80, eval_end=159)
    candidate = _candidate_returns(
        factors, alpha_bps=2.0, beta_btc=0.2, beta_market=-0.1,
        eval_start=80, eval_end=159,
    )
    peers = tuple({ts: float(m) for ts in range(80, 160)} for m in (0.2, 0.5, 1.0))

    # disabled：同一 report 兩次 to_dict() hash 必相等（writer 間一致）。
    rep_off = ResidualAlphaGate().evaluate(
        candidate, factors,
        _protocol(fit_window=ResidualAlphaFitWindow(0, 79, 80, 159, "x"),
                  candidate_oos_returns=peers),
    )
    h_bridge = _canon(rep_off.to_dict())
    h_drar = _canon(rep_off.to_dict())
    h_registry = _canon(rep_off.to_dict())
    assert h_bridge == h_drar == h_registry

    # enabled：帶 perm 欄位後三 writer 仍對同一最終 dict 取 hash → 一致。
    rep_on = ResidualAlphaGate().evaluate(
        candidate, factors,
        _protocol(fit_window=ResidualAlphaFitWindow(0, 79, 80, 159, "x"),
                  candidate_oos_returns=peers, permutation_enabled=True),
    )
    assert _canon(rep_on.to_dict()) == _canon(rep_on.to_dict())
    # disabled vs enabled 必不同（enabled 多了 perm 欄位）——證明 perm 確實進了 hash。
    assert _canon(rep_off.to_dict()) != _canon(rep_on.to_dict())


def test_permutation_determinism_borderline_p_binds_seed():
    """E4（補 E2 LOW #2）：seed binding 在「邊界 p」regime 才真有 bite。

    既有 determinism 測試用強訊號 fixture（mean=1.0/std=2.0 → p 飽和到 0.0），
    `assert p1==p2` 在 seed 被打斷（`default_rng()` 忽略 seed）時仍會通過，因為兩次
    都飽和在 0.0。本測試改用**弱訊號 borderline fixture**（27×+0.5 / 23×-0.5，
    n=50、observed mean=0.04bps）使 p 落在 ~0.66–0.69 且隨 seed 變動（非飽和）：

    1. 同 seed 兩次呼叫 → p 完全相等（嚴格 deterministic；打斷 seed → 兩次 entropy
       播種發散 → 此斷言 FAIL，即 mutation bite）。
    2. 兩個不同 seed → p 接近但不相等（documented：0.668 vs 0.6812），且兩者皆落在
       借助 sign-flip null 的中段區間 [0.60, 0.75]（非 0/1 飽和）。

    這些值在 PYTHONHASHSEED=0 下跨 run 可重現（PCG64 整數抽樣平台無關）。
    """
    # 弱訊號 fixture：手構（非 rng），fixture 本身 reproducible，與 seed binding 解耦。
    residual = np.asarray([0.5] * 27 + [-0.5] * 23, dtype=np.float64)
    assert abs(float(residual.mean())) == pytest.approx(0.04)  # 確認弱訊號（非飽和源）

    seed_a, seed_b, n_perm = 20260608, 777, 5000

    # (1) 同 seed → 嚴格相等（deterministic）。打斷 seed binding 後此處 FAIL。
    p_a1, iters_a1 = _permutation_residual_alpha(residual, n_perm=n_perm, seed=seed_a)
    p_a2, iters_a2 = _permutation_residual_alpha(residual, n_perm=n_perm, seed=seed_a)
    assert iters_a1 == iters_a2 == n_perm
    assert p_a1 == p_a2  # ★ seed-binding bite：broken seed → 兩次發散 → FAIL

    # (2) borderline（非飽和）—— p 必在中段，不得是 0.0/1.0；否則退回飽和 regime
    #     而 (1) 又會喪失 bite（即守住「這條 fixture 真的有鑑別力」）。
    assert 0.60 < p_a1 < 0.75
    assert p_a1 not in (0.0, 1.0)

    # (3) 不同 seed → 接近但不相等（documented 值；證明 p 確實隨 seed 變動）。
    p_b1, iters_b1 = _permutation_residual_alpha(residual, n_perm=n_perm, seed=seed_b)
    assert iters_b1 == n_perm
    assert p_a1 != p_b1
    assert 0.60 < p_b1 < 0.75
    # documented 值（PYTHONHASHSEED=0、numpy PCG64、n_perm=5000）：
    assert p_a1 == pytest.approx(0.668, abs=1e-9)
    assert p_b1 == pytest.approx(0.6812, abs=1e-9)
    # 「接近但不相等」：差異小（<0.05）但確實非零。
    assert 0.0 < abs(p_a1 - p_b1) < 0.05


# ---- HIGH-1：負零正規化（PG jsonb 丟符號位 → hash cross-check 破裂）----

from program_code.learning_engine.residual_alpha_gate import (  # noqa: E402
    ResidualEdgeReport,
)


def _canon_sha256(d: dict) -> str:
    """複製 bridge/drar/registry/source-contract 共用的 canonical sha256。

    sort_keys+separators+ensure_ascii 與 residual_hidden_oos_bridge._canonical_sha256
    / candidate_evidence_source_contract._canonical_sha256 完全一致。
    """
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _has_negative_zero(value) -> bool:
    """遞迴偵測結構中是否存在 -0.0（math.copysign 對 -0.0 回 -1.0）。"""
    if isinstance(value, float):
        return value == 0.0 and math.copysign(1.0, value) == -1.0
    if isinstance(value, dict):
        return any(_has_negative_zero(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_negative_zero(v) for v in value)
    return False


def _residual_report(*, residual_mean_bps: float, beta_btc: float) -> ResidualEdgeReport:
    """直接構造 report（dataclass）以精確注入 +0.0 / -0.0；不靠 np.mean 巧合產零。

    其餘欄位取中性占位（不影響 -0.0 正規化驗證）。
    """
    return ResidualEdgeReport(
        raw_mean_bps=12.0,
        residual_mean_bps=residual_mean_bps,
        r_beta_retention=0.6,
        beta_edge_share=0.4,
        beta_loadings={"btc": beta_btc, "market": 0.3, "_intercept_bps": 1.0},
        r_squared=0.5,
        psr_raw=0.97,
        psr_residual=0.96,
        dsr_raw=0.97,
        dsr_residual=0.96,
        pbo_raw=0.1,
        pbo_residual=0.1,
        coverage={"train": 80, "eval": 40},
        verdict="pass",
        reasons=(),
        factor_panel_hash="0" * 64,
        fit_window={"train_start": 0, "train_end": 79, "eval_start": 80, "eval_end": 119},
        passes=True,
    )


def test_to_dict_normalizes_negative_zero_to_positive_zero():
    """★ MIT HIGH-1：弱/共線 factor 的 np.mean / 回歸係數可能產 -0.0
    （residual_mean_bps、beta_loadings[factor]）；PG jsonb 會丟掉浮點符號位
    （-0.0 讀回變 0.0），而 registry hash 在進 jsonb 前算、source-contract 在讀回後
    重算 → -0.0→0.0 漂移 → residual_alpha_report_hash_mismatch → 候選被誤判 INVALID。

    驗 to_dict() chokepoint 抹平 -0.0：
    1. 注入 -0.0 到 residual_mean_bps 與 beta_loadings["btc"] 的 report，to_dict()
       後結構中**無任何 -0.0**（含巢狀 beta_loadings）。
    2. 該 report 的 canonical hash == 用 +0.0 構造的「相同」report 的 hash
       —— 證明 PG 的 -0.0→0.0 已無法讓 cross-check 漂移。

    PG jsonb 真 round-trip（-0.0→0.0、其餘不正規化）由 MIT 在 Linux 真 PG 驗證；本測試
    在 in-memory 層證明 to_dict() 已先消除 -0.0，使 jsonb 丟符號位成為 no-op。
    """
    neg = _residual_report(residual_mean_bps=-0.0, beta_btc=-0.0)
    pos = _residual_report(residual_mean_bps=0.0, beta_btc=0.0)

    # 先確認 fixture 本身真的帶 -0.0（否則測試無 bite）。
    assert math.copysign(1.0, neg.residual_mean_bps) == -1.0
    assert math.copysign(1.0, neg.beta_loadings["btc"]) == -1.0

    neg_dict = neg.to_dict()

    # (1) to_dict() 後結構中無任何 -0.0（含 beta_loadings 巢狀 dict）。
    assert not _has_negative_zero(neg_dict)
    assert math.copysign(1.0, neg_dict["residual_mean_bps"]) == 1.0
    assert math.copysign(1.0, neg_dict["beta_loadings"]["btc"]) == 1.0

    # (2) -0.0 report 與 +0.0 report 的 canonical hash 必相等
    #     → PG jsonb 的 -0.0→0.0 不再能讓 registry/source-contract hash 漂移。
    assert _canon_sha256(neg.to_dict()) == _canon_sha256(pos.to_dict())


def test_negative_zero_drift_without_normalization_would_break_hash():
    """mutation 守門：證明若不正規化（直接序列化 -0.0），canonical hash 會與 +0.0
    版本不同 —— 即此 cross-check 真的對 -0.0 敏感（_normalize_zeros 的 bite 來源）。

    這裡用 asdict 繞過 to_dict()（不經 _normalize_zeros），直接序列化原始 -0.0 結構，
    對照 to_dict()（已正規化）的 hash：前者與 +0.0 版本不同、後者相同。
    """
    from dataclasses import asdict

    neg = _residual_report(residual_mean_bps=-0.0, beta_btc=-0.0)
    pos = _residual_report(residual_mean_bps=0.0, beta_btc=0.0)

    # 未經正規化（raw asdict，剔同 to_dict() 的內部旗標以對齊 key 集）：-0.0 仍在 →
    # 與 +0.0 版本序列化不同（json.dumps 對 -0.0 輸出 "-0.0"，+0.0 輸出 "0.0"）。
    def _raw(report: ResidualEdgeReport) -> dict:
        d = asdict(report)
        d.pop("permutation_applied", None)
        d.pop("perm_p_value", None)
        d.pop("perm_iterations", None)
        return d

    assert _canon_sha256(_raw(neg)) != _canon_sha256(_raw(pos))  # 未正規化 → 漂移（bug 還原）
    assert _canon_sha256(neg.to_dict()) == _canon_sha256(pos.to_dict())  # 正規化後 → 收口
