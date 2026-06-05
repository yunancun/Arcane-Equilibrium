"""residual_alpha_producer 聚焦測試（R-1 純核心）。

用不規則 epoch-like timestamp（非連續整數）驗證 producer 能正確對齊、切窗、
並把 beta-trap 擋下、true-alpha 放行；缺 PBO peer / 樣本不足一律不得 promotion-ready。
"""

from __future__ import annotations

import pytest

from program_code.learning_engine.residual_alpha_producer import (
    ResidualAlphaProducerResult,
    build_residual_alpha_report,
)


# 每小時一根、epoch 秒（不規則於「連續整數」假設，驗證真實 ts 也能對齊）
_BASE_TS = 1_700_000_000
_STEP = 3600


def _ts(i: int) -> int:
    return _BASE_TS + i * _STEP


def _factor_returns(
    *, eval_shift_btc: float = 0.0, eval_shift_market: float = 0.0
) -> dict[int, dict[str, float]]:
    out: dict[int, dict[str, float]] = {}
    for i in range(140):
        btc = 4.0 if i % 2 == 0 else -4.0
        market = 3.0 if (i // 2) % 2 == 0 else -3.0
        if 80 <= i <= 119:
            btc += eval_shift_btc
            market += eval_shift_market
        out[_ts(i)] = {"btc": btc, "market": market}
    return out


def _candidate_returns(
    factor_returns: dict[int, dict[str, float]],
    *,
    alpha_bps: float,
    beta_btc: float,
    beta_market: float,
    eval_noise_bps: float = 0.0,
) -> dict[int, float]:
    out: dict[int, float] = {}
    for i in range(120):  # 候選只覆蓋 i=0..119
        row = factor_returns[_ts(i)]
        value = alpha_bps + beta_btc * row["btc"] + beta_market * row["market"]
        if 80 <= i <= 119:
            value += eval_noise_bps
        out[_ts(i)] = value
    return out


def _ts_peers(candidate: dict[int, float], *means: float) -> tuple[dict[int, float], ...]:
    # timestamped peers：gate 會自動 scope 到 eval 窗，免去固定長度匹配問題
    ts_list = sorted(candidate)
    return tuple({ts: float(mean) for ts in ts_list} for mean in means)


def test_true_alpha_promotion_ready():
    factors = _factor_returns()
    candidate = _candidate_returns(factors, alpha_bps=2.0, beta_btc=0.4, beta_market=-0.2)
    res = build_residual_alpha_report(
        candidate,
        factors,
        n_trials=4,
        peer_oos_returns=_ts_peers(candidate, 0.2, 0.5, 1.0),
        min_train_observations=40,
        min_eval_observations=20,
        min_coverage=0.9,
    )
    assert isinstance(res, ResidualAlphaProducerResult)
    assert res.promotion_ready is True
    assert res.report["passes"] is True
    assert res.report["verdict"] == "pass"
    assert res.report["residual_mean_bps"] > 0.0
    assert res.aligned_observations == 120


def test_beta_trap_not_promotion_ready():
    factors = _factor_returns(eval_shift_btc=5.0, eval_shift_market=2.0)
    candidate = _candidate_returns(
        factors, alpha_bps=0.0, beta_btc=2.0, beta_market=1.0, eval_noise_bps=-0.2
    )
    res = build_residual_alpha_report(
        candidate,
        factors,
        n_trials=4,
        peer_oos_returns=_ts_peers(candidate, 0.2, 0.5, 1.0),
        min_train_observations=40,
        min_eval_observations=20,
        min_coverage=0.9,
    )
    # OOS raw 為正（吃到 down-market beta），但扣 prior-fit beta 後殘差非正 → 必須擋
    assert res.report["raw_mean_bps"] > 0.0
    assert res.report["residual_mean_bps"] <= 0.0
    assert res.report["verdict"] == "fail"
    assert res.promotion_ready is False


def test_alignment_drops_unmatched_timestamps():
    factors = _factor_returns()
    candidate = _candidate_returns(factors, alpha_bps=2.0, beta_btc=0.4, beta_market=-0.2)
    # (1) candidate 有一個 factor 沒有的 ts → 應丟棄
    candidate[999_999_999] = 1.0
    # (2) factor 有一個 ts 缺 required factor "market" → 該 ts 也應丟棄
    drop_ts = _ts(0)
    factors[drop_ts] = {"btc": 1.0}
    res = build_residual_alpha_report(
        candidate,
        factors,
        n_trials=4,
        peer_oos_returns=_ts_peers(candidate, 0.5, 1.0),
        min_train_observations=10,
        min_eval_observations=5,
        min_coverage=0.5,
    )
    # 原 120 個對齊 ts，減去缺 market 的 1 個；999... 不在 factor 不計入 → 119
    assert res.aligned_observations == 119


def test_insufficient_data_defers():
    factors = {1: {"btc": 1.0, "market": 1.0}}
    candidate = {1: 1.0}
    res = build_residual_alpha_report(candidate, factors, n_trials=1, peer_oos_returns=None)
    assert res.promotion_ready is False
    assert res.report["verdict"] in ("defer_data", "fail")
    assert res.aligned_observations == 1


def test_missing_pbo_peers_not_promotion_ready():
    factors = _factor_returns()
    candidate = _candidate_returns(factors, alpha_bps=2.0, beta_btc=0.4, beta_market=-0.2)
    res = build_residual_alpha_report(
        candidate,
        factors,
        n_trials=4,
        peer_oos_returns=None,  # 無 PBO peer → core diagnostic forbidden → 不得 pass
        min_train_observations=40,
        min_eval_observations=20,
        min_coverage=0.9,
    )
    assert res.promotion_ready is False


def test_embargo_purges_train_tail_near_seam():
    factors = _factor_returns()
    candidate = _candidate_returns(factors, alpha_bps=2.0, beta_btc=0.4, beta_market=-0.2)
    common = dict(
        n_trials=4,
        peer_oos_returns=_ts_peers(candidate, 0.5, 1.0),
        min_train_observations=10,
        min_eval_observations=5,
        min_coverage=0.5,
    )
    base = build_residual_alpha_report(candidate, factors, **common)
    # embargo_gap = 5 小時（5*_STEP 秒）→ 接縫前 ~5 個 train obs 應被 purge
    emb = build_residual_alpha_report(candidate, factors, embargo_gap=5 * _STEP, **common)
    assert emb.train_observations < base.train_observations
    assert emb.eval_observations == base.eval_observations
    # 被 purge 的 ts 不在 fit-scope，故 train_end < eval_start 仍成立
    assert emb.report["fit_window"]["train_end"] < emb.report["fit_window"]["eval_start"]


def test_invalid_args_raise():
    factors = {1: {"btc": 1.0, "market": 1.0}, 2: {"btc": 1.0, "market": 1.0}}
    candidate = {1: 1.0, 2: 1.0}
    with pytest.raises(ValueError):
        build_residual_alpha_report(candidate, factors, n_trials=0)
    with pytest.raises(ValueError):
        build_residual_alpha_report(candidate, factors, n_trials=1, train_fraction=1.0)
    with pytest.raises(ValueError):
        build_residual_alpha_report(candidate, factors, n_trials=1, return_unit="pct")
    with pytest.raises(ValueError):
        build_residual_alpha_report(candidate, factors, n_trials=1, embargo_gap=-1.0)
