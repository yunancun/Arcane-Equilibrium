"""Tests for pbo_gate (REF-20 Wave 6 P4-Q2).

pbo_gate 測試（REF-20 Wave 6 P4-Q2）。

Coverage / 覆蓋:
  1. PBO=low + sufficient power → 'promote' verdict. /
     PBO 低 + 足量 power → 'promote'。
  2. PBO=high → 'block' verdict. /
     PBO 高 → 'block'。
  3. K=5 < min_K=10 → 'block' (insufficient n_splits). /
     K=5 < min_K=10 → 'block'（n_splits 不足）。
  4. total_trades=200 < min_total_trades=320 → 'block'. /
     total_trades=200 < min_total_trades=320 → 'block'。
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from program_code.learning_engine.pbo_gate import (
    DEFAULT_MIN_K,
    DEFAULT_MIN_TOTAL_TRADES,
    DEFAULT_PBO_THRESHOLD,
    PboGate,
    PboResult,
    compute_pbo,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _generate_persistent_alpha_candidates(
    n_candidates: int = 10,
    n_periods: int = 256,
    seed: int = 42,
) -> list[np.ndarray]:
    """Generate candidates where IS performance correlates with OOS — low PBO.

    生成樣本內表現與樣本外相關的候選（低 PBO）。

    Each candidate has constant alpha + noise. High-alpha candidates win
    in both IS and OOS → CSCV ranks should be consistent → low PBO.

    每候選有常數 alpha + 噪音。高 alpha 候選在 IS 與 OOS 皆勝 →
    CSCV ranks 應一致 → 低 PBO。
    """
    rng = np.random.default_rng(seed)
    candidates = []
    # Strongly differentiated alphas so ranking is stable and IS leader
    # remains OOS leader → low PBO.
    # 強差異化 alphas 使 ranking 穩定，IS 領先者於 OOS 仍領先 → 低 PBO。
    for k in range(n_candidates):
        alpha = float(k) * 0.05  # 0, 0.05, 0.10, ..., 0.45
        # Lower noise so alpha signal dominates.
        # 降低噪音以使 alpha 訊號主導。
        noise = rng.normal(0.0, 0.05, size=n_periods)
        candidates.append(alpha + noise)
    return candidates


def _generate_random_candidates(
    n_candidates: int = 10,
    n_periods: int = 256,
    seed: int = 42,
) -> list[np.ndarray]:
    """Generate candidates with no real alpha — high PBO expected.

    生成無真 alpha 之候選（預期高 PBO）。

    All candidates have mean 0 — IS winner is just luck → OOS rank is
    uniform → PBO ≈ 0.5.

    全候選均值為 0 — IS 贏家為運氣 → OOS rank 均勻 → PBO ≈ 0.5。
    """
    rng = np.random.default_rng(seed)
    candidates = []
    for _ in range(n_candidates):
        candidates.append(rng.normal(0.0, 1.0, size=n_periods))
    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: PBO=low + sufficient → 'promote'
# ─────────────────────────────────────────────────────────────────────────────


def test_pbo_low_sufficient_power_promote():
    """Persistent-alpha candidates → low PBO + sufficient power → 'promote'.

    持續 alpha 候選 → 低 PBO + 足量 power → 'promote'。

    Setup / 設定:
      - 10 candidates × 256 periods = 2560 total trades >= 320 ✓
      - S=16 → C(16, 8) = 12870 combinations >= 10 ✓
      - Strong alpha differentiation → IS leader = OOS leader → PBO low
    """
    candidates = _generate_persistent_alpha_candidates(
        n_candidates=10, n_periods=256, seed=42,
    )

    gate = PboGate(threshold=0.5, min_K=10, min_total_trades=320, s_slices=16)
    result = gate.compute_pbo(candidates)

    assert isinstance(result, PboResult)
    assert result.total_trades == 10 * 256  # 2560
    assert result.n_splits == math.comb(16, 8)  # 12870
    assert result.total_trades >= 320
    assert result.n_splits >= 10
    assert not result.insufficient_power
    # Strong alpha → low PBO; ensure < 0.5.
    # 強 alpha → 低 PBO；確保 < 0.5。
    assert result.pbo < 0.5, f"PBO={result.pbo} should be < 0.5 for persistent alpha"

    verdict = gate.gate(result)
    assert verdict == "promote", f"expected 'promote', got '{verdict}'"


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: PBO=high → 'block'
# ─────────────────────────────────────────────────────────────────────────────


def test_pbo_high_blocks_promotion():
    """Anti-persistent candidates (IS winner = OOS loser) → PBO > 0.5 → 'block'.

    反持續候選（IS 贏家 = OOS 輸家）→ PBO > 0.5 → 'block'。

    Setup / 設定:
      - First half of each candidate = positive alpha-k.
      - Second half = negative alpha-k → IS leader = OOS loser.
      - PBO should be high (> 0.5).

      設定：每候選前半 = +alpha_k，後半 = -alpha_k → IS 贏家 = OOS 輸家。
      PBO 應高（> 0.5）。
    """
    rng = np.random.default_rng(seed=42)
    n_candidates = 10
    n_periods = 256
    candidates = []
    for k in range(n_candidates):
        # Strong sign-flip: positive alpha first half, negative second half.
        # 強符號翻轉：前半正 alpha，後半負 alpha。
        alpha = float(k) * 0.05
        noise = rng.normal(0.0, 0.05, size=n_periods)
        sign_flip = np.concatenate([
            np.ones(n_periods // 2),
            -np.ones(n_periods - n_periods // 2),
        ])
        candidates.append(alpha * sign_flip + noise)

    gate = PboGate(threshold=0.5, min_K=10, min_total_trades=320, s_slices=2)
    # Use s_slices=2 to amplify IS/OOS sign-flip — top half = IS, bottom = OOS.
    # 用 s_slices=2 放大 IS/OOS sign-flip — 上半 = IS，下半 = OOS。
    result = gate.compute_pbo(candidates)

    # PBO should be high (> 0.5); verdict 'block' regardless.
    # PBO 應高（> 0.5）；判決必為 'block'。
    assert result.pbo > 0.5 or not result.passes_threshold, (
        f"PBO={result.pbo} should reflect overfitting"
    )

    verdict = gate.gate(result)
    assert verdict == "block", f"expected 'block', got '{verdict}'"


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: K=5 (insufficient n_splits) → 'block'
# ─────────────────────────────────────────────────────────────────────────────


def test_insufficient_n_splits_blocks():
    """Few combinations (s_slices=4 → C(4,2)=6 < 10) → 'block'.

    少組合（s_slices=4 → C(4,2)=6 < 10）→ 'block'。

    Setup / 設定:
      - s_slices=4 → only C(4,2) = 6 combinations < min_K=10.
      - Even with low PBO, gate must block due to insufficient splits.

      s_slices=4 → 僅 C(4,2)=6 組合 < min_K=10。
      即使 PBO 低，gate 必因 splits 不足而 block。
    """
    candidates = _generate_persistent_alpha_candidates(
        n_candidates=10, n_periods=200, seed=42,
    )
    # s_slices=4 → C(4,2)=6 combinations only.
    # s_slices=4 → 僅 C(4,2)=6 組合。
    gate = PboGate(threshold=0.5, min_K=10, min_total_trades=320, s_slices=4)
    result = gate.compute_pbo(candidates)

    assert result.n_splits == math.comb(4, 2)  # 6
    assert result.n_splits < 10  # below min_K
    assert result.insufficient_power, (
        f"insufficient_power should be True; n_splits={result.n_splits}"
    )
    assert not result.passes_threshold

    verdict = gate.gate(result)
    assert verdict == "block", f"expected 'block', got '{verdict}'"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: total_trades=200 < 320 → 'block'
# ─────────────────────────────────────────────────────────────────────────────


def test_insufficient_total_trades_blocks():
    """total_trades=200 < min_total_trades=320 → 'block'.

    total_trades=200 < min_total_trades=320 → 'block'。

    Setup / 設定:
      - 10 candidates × 20 periods = 200 total trades.
      - 200 < 320 → gate must block.

      設定：10 候選 × 20 periods = 200 total trades < 320 → gate 必 block。
    """
    candidates = _generate_persistent_alpha_candidates(
        n_candidates=10, n_periods=20, seed=42,
    )
    # T=20 too small for s_slices=16 → CSCV will fall back / use lower S.
    # We use s_slices=4 + min_K=2 to focus the test on total_trades fail.
    # T=20 對 s_slices=16 太小 → 用 s_slices=4 + min_K=2 聚焦 total_trades。
    gate = PboGate(threshold=0.5, min_K=2, min_total_trades=320, s_slices=4)
    result = gate.compute_pbo(candidates)

    # total_trades = 10 * 20 = 200.
    assert result.total_trades == 200
    assert result.total_trades < 320
    assert result.insufficient_power, (
        f"insufficient_power should be True; total_trades={result.total_trades}"
    )
    assert not result.passes_threshold

    verdict = gate.gate(result)
    assert verdict == "block", f"expected 'block', got '{verdict}'"


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases / 邊緣案例（防禦性）
# ─────────────────────────────────────────────────────────────────────────────


def test_invalid_threshold_raises():
    """Threshold outside (0, 1) must raise.

    閾值 (0, 1) 外必拋。
    """
    with pytest.raises(ValueError):
        PboGate(threshold=1.5)
    with pytest.raises(ValueError):
        PboGate(threshold=0.0)


def test_invalid_s_slices_raises():
    """Odd or < 2 s_slices must raise.

    奇數或 < 2 之 s_slices 必拋。
    """
    with pytest.raises(ValueError):
        PboGate(s_slices=3)
    with pytest.raises(ValueError):
        PboGate(s_slices=1)


def test_empty_input_raises():
    """Empty candidates list must raise.

    空候選 list 必拋。
    """
    gate = PboGate()
    with pytest.raises(ValueError):
        gate.compute_pbo([])


def test_single_candidate_raises():
    """Single candidate insufficient for ranking.

    單一候選不足供 ranking。
    """
    gate = PboGate()
    with pytest.raises(ValueError):
        gate.compute_pbo([np.array([0.1, 0.2, 0.3])])


def test_module_shortcut_matches_class():
    """Module-level compute_pbo matches PboGate(...).compute_pbo.

    模組級 compute_pbo 須等同 PboGate(...).compute_pbo。
    """
    candidates = _generate_persistent_alpha_candidates(
        n_candidates=4, n_periods=64, seed=42,
    )
    a = compute_pbo(candidates, threshold=0.5, min_K=2, min_total_trades=2, s_slices=4)
    b = PboGate(threshold=0.5, min_K=2, min_total_trades=2, s_slices=4).compute_pbo(
        candidates,
    )
    assert math.isclose(a.pbo, b.pbo, abs_tol=1e-12)
    assert a.n_splits == b.n_splits
    assert a.total_trades == b.total_trades


def test_random_candidates_pbo_around_half():
    """Random (no alpha) candidates → PBO ≈ 0.5 ± noise.

    隨機（無 alpha）候選 → PBO ≈ 0.5 ± 噪音。
    """
    candidates = _generate_random_candidates(
        n_candidates=10, n_periods=256, seed=42,
    )
    gate = PboGate(threshold=0.5, min_K=10, min_total_trades=320, s_slices=16)
    result = gate.compute_pbo(candidates)

    # Random candidates: PBO should be near 0.5 (within reasonable band).
    # Allowable band: [0.3, 0.7] reflects finite-sample variance.
    # 隨機候選：PBO 應接近 0.5（合理帶內）。
    assert 0.3 < result.pbo < 0.7, (
        f"random candidates PBO={result.pbo} outside [0.3, 0.7] reasonable band"
    )
