"""
Tests for Thompson Sampling NIG module.
Thompson Sampling NIG 模組的測試。

MODULE_NOTE (EN): 8 self-contained tests covering posterior update, convergence,
  Empirical Bayes init, exploitation floor, arm selection, and serialization.
MODULE_NOTE (中): 8 個自包含測試，涵蓋後驗更新、收斂、Empirical Bayes 初始化、
  利用下限、臂選擇和序列化。
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest

from program_code.ml_training.thompson_sampling import (
    NIGPosterior,
    empirical_bayes_init,
    exploitation_floor,
    posteriors_from_dict,
    posteriors_to_dict,
    sample_arm,
    sample_nig,
    select_next_arm,
    update_posterior,
    update_posterior_batch,
)


# ---------------------------------------------------------------------------
# 1. test_nig_update_single — prior + 1 observation → correct posterior
#    先驗 + 1 筆觀測 → 正確後驗（解析驗證）
# ---------------------------------------------------------------------------

def test_nig_update_single():
    """Verify conjugate update formulas analytically for a single observation.
    解析驗證單筆觀測的共軛更新公式。"""
    prior = NIGPosterior(mu=0.0, lam=2.0, alpha=3.0, beta=1.0, n_trials=0)
    x = 4.0

    post = update_posterior(prior, x)

    # lam_n = 2 + 1 = 3
    assert post.lam == pytest.approx(3.0)
    # mu_n = (2*0 + 4) / 3 = 4/3
    assert post.mu == pytest.approx(4.0 / 3.0)
    # alpha_n = 3 + 0.5 = 3.5
    assert post.alpha == pytest.approx(3.5)
    # beta_n = 1 + 0.5 * 2 * (4 - 0)^2 / 3 = 1 + 0.5*2*16/3 = 1 + 16/3 ≈ 6.3333
    expected_beta = 1.0 + 0.5 * 2.0 * (4.0 ** 2) / 3.0
    assert post.beta == pytest.approx(expected_beta)
    # n_trials incremented / 試驗數遞增
    assert post.n_trials == 1


# ---------------------------------------------------------------------------
# 2. test_nig_convergence — 1000 obs from N(5,1) → mu converges near 5
#    1000 筆來自 N(5,1) 的觀測 → mu 收斂至約 5
# ---------------------------------------------------------------------------

def test_nig_convergence():
    """After many observations from N(5, 1), posterior mu should converge near 5.
    經 N(5,1) 大量觀測後，後驗 mu 應收斂至約 5。"""
    rng_np = np.random.default_rng(42)
    observations = rng_np.normal(loc=5.0, scale=1.0, size=1000).tolist()

    prior = NIGPosterior(mu=0.0, lam=3.0, alpha=3.0, beta=1.0, n_trials=0)
    post = update_posterior_batch(prior, observations)

    # mu should be close to 5 / mu 應接近 5
    assert abs(post.mu - 5.0) < 0.2, f"mu={post.mu}, expected ~5.0"
    # n_trials should be 1000 / 試驗數應為 1000
    assert post.n_trials == 1000
    # alpha should be 3 + 1000*0.5 = 503 / alpha 應為 503
    assert post.alpha == pytest.approx(503.0)


# ---------------------------------------------------------------------------
# 3. test_empirical_bayes_init_basic — init with known returns
#    以已知回報初始化 → 正確的 mu/lambda/alpha/beta
# ---------------------------------------------------------------------------

def test_empirical_bayes_init_basic():
    """Empirical Bayes with known returns should produce correct parameters.
    以已知回報的 Empirical Bayes 應產生正確參數。"""
    returns = [1.0, 2.0, 3.0, 4.0, 5.0]

    post = empirical_bayes_init(returns)

    # mu_0 = mean = 3.0
    assert post.mu == pytest.approx(3.0)
    # lam_0 = 3.0
    assert post.lam == pytest.approx(3.0)
    # alpha_0 = 3.0
    assert post.alpha == pytest.approx(3.0)
    # var = mean((x - 3)^2) = (4+1+0+1+4)/5 = 2.0
    # beta_0 = var * (alpha - 1) = 2.0 * 2 = 4.0
    assert post.beta == pytest.approx(4.0)
    # Not yet observed / 尚未觀測
    assert post.n_trials == 0


# ---------------------------------------------------------------------------
# 4. test_empirical_bayes_init_empty — empty returns → safe default prior
#    空回報 → 安全默認先驗
# ---------------------------------------------------------------------------

def test_empirical_bayes_init_empty():
    """Empty or all-zero returns should produce a safe default prior.
    空或全零回報應產生安全默認先驗。"""
    # Empty list / 空列表
    post_empty = empirical_bayes_init([])
    assert post_empty.mu == 0.0
    assert post_empty.lam == 3.0
    assert post_empty.alpha == 3.0
    assert post_empty.beta == 1.0

    # All zeros / 全零
    post_zeros = empirical_bayes_init([0.0, 0.0, 0.0])
    assert post_zeros.mu == 0.0
    assert post_zeros.lam == 3.0
    assert post_zeros.alpha == 3.0
    assert post_zeros.beta == 1.0


# ---------------------------------------------------------------------------
# 5. test_exploitation_floor_enforced — <10 total trials → exploitation mode
#    總試驗數 <10 → 利用模式
# ---------------------------------------------------------------------------

def test_exploitation_floor_enforced():
    """With fewer than 10 total trials, exploitation floor should be active.
    總試驗數少於 10 時，利用下限應啟動。"""
    posteriors = {
        "arm_a": NIGPosterior(mu=1.0, n_trials=3),
        "arm_b": NIGPosterior(mu=2.0, n_trials=4),
    }
    # Total = 7 < 10 → exploitation forced / 總計 7 < 10 → 強制利用
    assert exploitation_floor(posteriors) is True

    # select_next_arm should pick arm_b (highest mu=2.0)
    # select_next_arm 應選 arm_b（最高 mu=2.0）
    selected = select_next_arm(posteriors, rng=random.Random(99))
    assert selected == "arm_b"


# ---------------------------------------------------------------------------
# 6. test_exploitation_floor_released — >=10 trials → normal sampling
#    試驗數 >=10 → 正常抽樣
# ---------------------------------------------------------------------------

def test_exploitation_floor_released():
    """With 10+ total trials, exploitation floor should be released.
    總試驗數 >=10 時，利用下限應釋放。"""
    posteriors = {
        "arm_a": NIGPosterior(mu=1.0, n_trials=5),
        "arm_b": NIGPosterior(mu=2.0, n_trials=5),
    }
    # Total = 10 → floor released / 總計 10 → 下限釋放
    assert exploitation_floor(posteriors) is False


# ---------------------------------------------------------------------------
# 7. test_sample_arm_explores — similar posteriors → both arms selected
#    相似後驗 → 兩臂都被選中（多次抽樣）
# ---------------------------------------------------------------------------

def test_sample_arm_explores():
    """With similar posteriors, Thompson Sampling should explore both arms.
    相似後驗下，Thompson Sampling 應探索兩臂。"""
    # Two arms with identical posteriors / 兩臂相同後驗
    posteriors = {
        "arm_a": NIGPosterior(mu=1.0, lam=3.0, alpha=3.0, beta=1.0, n_trials=20),
        "arm_b": NIGPosterior(mu=1.0, lam=3.0, alpha=3.0, beta=1.0, n_trials=20),
    }

    counts: dict[str, int] = {"arm_a": 0, "arm_b": 0}
    rng = random.Random(12345)

    for _ in range(200):
        chosen = sample_arm(posteriors, rng=rng)
        counts[chosen] += 1

    # Both arms should be selected at least 30 times out of 200
    # 兩臂各至少被選 30 次（200 次中）
    assert counts["arm_a"] >= 30, f"arm_a only selected {counts['arm_a']} times"
    assert counts["arm_b"] >= 30, f"arm_b only selected {counts['arm_b']} times"


# ---------------------------------------------------------------------------
# 8. test_posteriors_roundtrip — to_dict → from_dict → identical posteriors
#    to_dict → from_dict → 完全一致的後驗
# ---------------------------------------------------------------------------

def test_posteriors_roundtrip():
    """Serialization round-trip should produce identical posteriors.
    序列化往返應產生完全一致的後驗。"""
    original = {
        "strat_a:BTCUSDT:trending": NIGPosterior(
            mu=1.5, lam=4.0, alpha=3.5, beta=2.0, n_trials=10
        ),
        "strat_b:ETHUSDT:ranging": NIGPosterior(
            mu=-0.3, lam=3.0, alpha=3.0, beta=0.5, n_trials=5
        ),
    }

    serialized = posteriors_to_dict(original)
    restored = posteriors_from_dict(serialized)

    for key in original:
        orig = original[key]
        rest = restored[key]
        assert rest.mu == pytest.approx(orig.mu)
        assert rest.lam == pytest.approx(orig.lam)
        assert rest.alpha == pytest.approx(orig.alpha)
        assert rest.beta == pytest.approx(orig.beta)
        assert rest.n_trials == orig.n_trials
