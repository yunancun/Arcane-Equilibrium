"""
regime_bandit_allocator 單元測試。

涵蓋核心誠實鐵則斷言：
  - 全負 EV → allocate 100% 配 flat（學會歸零，不硬湊正）。
  - 真有正 EV arm → 權重收斂到該 arm（但 flat 仍在 dict）。
  - demo artifact（無排隊 maker）→ transferable_only 軌不吸收、標 saw_artifact。
  - exploitation floor / dormant 清除 / fractional-Kelly 分級。

防 prod 污染：autouse _no_real_db 攔死 psycopg2.connect（與 memory_distiller
conftest 同精神）；本核心模組本就無 DB IO，此閘是縱深防禦，確保未來加 IO
時測試不會誤連真 PG。所有隨機由 seeded random.Random 注入，可重現。
"""

from __future__ import annotations

import random

import pytest

from program_code.ml_training.regime_bandit_allocator import (
    FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT,
    FILL_TIER_TAKER_REAL,
    FLAT_ARM_ID,
    TRACK_ALL_FILLS,
    TRACK_TRANSFERABLE_ONLY,
    AllocatorConfig,
    ArmReward,
    RegimeBanditAllocator,
    fractional_kelly_cap,
    make_arm_id,
    parse_arm_id,
    prob_mu_positive,
)
from program_code.ml_training.thompson_sampling import NIGPosterior


# ---------------------------------------------------------------------------
# 防 prod 污染鐵閘（autouse）
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch):
    """攔真 psycopg2.connect：核心模組無 DB IO，此閘為縱深防禦。"""
    try:
        import psycopg2  # noqa: PLC0415

        def _blocked(*_a, **_k):
            raise AssertionError("測試禁止真 psycopg2.connect（_no_real_db 鐵閘）")

        monkeypatch.setattr(psycopg2, "connect", _blocked)
    except ImportError:
        pass


def _rng() -> random.Random:
    return random.Random(42)


def _feed(alloc, arm_id, regime, pnls, tier=FILL_TIER_TAKER_REAL, t0=1.0):
    """餵一批報酬，ts 單調遞增（注入時間，不用 wall-clock）。"""
    t = t0
    for p in pnls:
        alloc.ingest_arm_outcome(arm_id, regime, p, t, fill_realism_tier=tier)
        t += 1.0


# ---------------------------------------------------------------------------
# 核心鐵則 1：全負 EV → 歸 flat
# ---------------------------------------------------------------------------


def test_all_negative_arms_allocate_to_flat():
    """所有真 arm 皆明顯負 → allocate 100% 配 flat（誠實歸零）。"""
    cfg = AllocatorConfig(prob_mc_samples=1500)
    alloc = RegimeBanditAllocator(cfg)
    arm_a = make_arm_id("bear", "grid_trading")
    arm_b = make_arm_id("bear", "ma_crossover")
    # 兩 arm 都餵一致的強負報酬（-30bps 級），P(μ>0) 應遠低於 gate。
    _feed(alloc, arm_a, "bear", [-30.0] * 40)
    _feed(alloc, arm_b, "bear", [-25.0] * 40)

    w = alloc.allocate("bear", [arm_a, arm_b], rng=_rng())
    assert w == {FLAT_ARM_ID: 1.0}, f"全負應歸 flat，實得 {w}"


def test_empty_cold_arms_allocate_to_flat():
    """完全沒資料（cold prior, μ=0）→ P(μ>0)≈0.5 < gate(0.55) → 全 flat。"""
    cfg = AllocatorConfig(prob_mc_samples=2000, positive_prob_gate=0.55)
    alloc = RegimeBanditAllocator(cfg)
    arm = make_arm_id("chop", "bb_reversion")
    w = alloc.allocate("chop", [arm], rng=_rng())
    assert w == {FLAT_ARM_ID: 1.0}


# ---------------------------------------------------------------------------
# 核心鐵則 2：真有正 arm → 權重收斂到正 arm
# ---------------------------------------------------------------------------


def test_clearly_positive_arm_gets_majority_weight():
    """一個明顯正 arm vs 一個明顯負 arm → 正 arm 拿絕大多數權重。"""
    cfg = AllocatorConfig(prob_mc_samples=3000)
    alloc = RegimeBanditAllocator(cfg)
    pos_arm = make_arm_id("bull", "bb_breakout")
    neg_arm = make_arm_id("bull", "grid_trading")
    _feed(alloc, pos_arm, "bull", [40.0] * 60)   # 強正
    _feed(alloc, neg_arm, "bull", [-40.0] * 60)  # 強負

    w = alloc.allocate("bull", [pos_arm, neg_arm], rng=_rng())
    assert FLAT_ARM_ID in w
    assert pos_arm in w
    # 負 arm 應被歸零閘擋掉（不在權重 dict 的真 arm 集），或權重極小。
    assert w[pos_arm] > 0.8, f"正 arm 應拿絕大多數，實得 {w}"
    # 權重和為 1。
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_positive_arm_beats_flat():
    """強正 arm 應贏過 flat 的負基準（拿到 > 0 權重）。"""
    cfg = AllocatorConfig(prob_mc_samples=3000, flat_arm_cost_floor_bps=5.0)
    alloc = RegimeBanditAllocator(cfg)
    pos_arm = make_arm_id("range", "bb_reversion")
    _feed(alloc, pos_arm, "range", [25.0] * 80)
    w = alloc.allocate("range", [pos_arm], rng=_rng())
    assert w[pos_arm] > 0.5, f"強正 arm 應贏過 flat，實得 {w}"


# ---------------------------------------------------------------------------
# 核心鐵則 3：demo artifact 不可轉移
# ---------------------------------------------------------------------------


def test_artifact_not_ingested_into_transferable_track():
    """無排隊 maker artifact 報酬不進 transferable_only 軌，但進 all_fills 軌。"""
    alloc = RegimeBanditAllocator()
    arm = make_arm_id("chop", "grid_trading")
    _feed(
        alloc, arm, "chop", [50.0] * 30,
        tier=FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT,
    )
    # all_fills 軌吃到了（n_trials>0）
    st_all = alloc._states[TRACK_ALL_FILLS][arm]
    assert st_all.posterior.n_trials == 30
    assert st_all.saw_artifact is True
    # transferable_only 軌完全沒這 arm（artifact 不入軌）
    assert arm not in alloc._states[TRACK_TRANSFERABLE_ONLY]


def test_artifact_inflated_arm_does_not_drive_transferable_allocation():
    """只靠 demo artifact 的虛高正 PnL，在 transferable 軌上仍歸 flat。"""
    cfg = AllocatorConfig(prob_mc_samples=2000)
    alloc = RegimeBanditAllocator(cfg)
    arm = make_arm_id("bull", "bb_breakout")
    # 全部是 artifact 的虛高 +60bps，transferable 軌不該被驅動。
    _feed(
        alloc, arm, "bull", [60.0] * 50,
        tier=FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT,
    )
    w = alloc.allocate("bull", [arm], rng=_rng(), track=TRACK_TRANSFERABLE_ONLY)
    assert w == {FLAT_ARM_ID: 1.0}, f"artifact-only 在 transferable 軌應歸 flat，實得 {w}"


def test_reward_transferable_flag():
    """ArmReward.transferable：只有 artifact tier 為 False。"""
    assert ArmReward("a", "bull", 1.0, 1.0, FILL_TIER_TAKER_REAL).transferable is True
    assert (
        ArmReward("a", "bull", 1.0, 1.0, FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT).transferable
        is False
    )


# ---------------------------------------------------------------------------
# exploitation floor / Monte-Carlo 權重 / 正規化
# ---------------------------------------------------------------------------


def test_exploitation_floor_deterministic_when_scarce():
    """合格 arm 但總樣本 < explore_budget → 退化為按 μ argmax 的確定性配置。"""
    cfg = AllocatorConfig(prob_mc_samples=1500, explore_budget=100, positive_prob_gate=0.5)
    alloc = RegimeBanditAllocator(cfg)
    arm = make_arm_id("range", "bb_reversion")
    # 只 5 筆強正 → 過 gate 但樣本 < explore_budget(100)。
    _feed(alloc, arm, "range", [30.0] * 5)
    w = alloc.allocate("range", [arm], rng=_rng())
    # 退化模式：權重必為 0/1（確定性），且和為 1。
    assert set(w.values()) <= {0.0, 1.0}
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_weights_sum_to_one_and_nonneg():
    """任何配置結果：權重非負且和為 1，必含 flat-arm。"""
    cfg = AllocatorConfig(prob_mc_samples=2000)
    alloc = RegimeBanditAllocator(cfg)
    a1 = make_arm_id("bull", "bb_breakout")
    a2 = make_arm_id("bull", "ma_crossover")
    _feed(alloc, a1, "bull", [20.0] * 60)
    _feed(alloc, a2, "bull", [15.0] * 60)
    w = alloc.allocate("bull", [a1, a2], rng=_rng())
    assert FLAT_ARM_ID in w
    assert all(v >= 0.0 for v in w.values())
    assert abs(sum(w.values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 非平穩：遺忘 + dormant 清除
# ---------------------------------------------------------------------------


def test_forgetting_decays_old_stats():
    """gamma<1：舊統計量會被衰減（n_trials 不會無限累積到精確 N）。"""
    cfg = AllocatorConfig(forgetting_gamma=0.5)
    alloc = RegimeBanditAllocator(cfg)
    arm = make_arm_id("bear", "grid_trading")
    _feed(alloc, arm, "bear", [-10.0] * 20)
    st = alloc._states[TRACK_TRANSFERABLE_ONLY][arm]
    # 有衰減時，n_trials 應 < 20（每步衰減舊量）。
    assert st.posterior.n_trials < 20


def test_no_forgetting_when_gamma_one():
    """gamma=1.0：不衰減，n_trials == 觀測數。"""
    cfg = AllocatorConfig(forgetting_gamma=1.0)
    alloc = RegimeBanditAllocator(cfg)
    arm = make_arm_id("bear", "grid_trading")
    _feed(alloc, arm, "bear", [-10.0] * 15)
    st = alloc._states[TRACK_TRANSFERABLE_ONLY][arm]
    assert st.posterior.n_trials == 15


def test_clear_dormant_resets_posterior():
    """dormant 過久的 arm 後驗清回 prior。"""
    cfg = AllocatorConfig(dormant_clear_after_ticks=10, forgetting_gamma=1.0)
    alloc = RegimeBanditAllocator(cfg)
    arm = make_arm_id("bull", "bb_breakout")
    _feed(alloc, arm, "bull", [20.0] * 5, t0=1.0)  # last_update_ts = 5.0
    cleared = alloc.clear_dormant(now_ts=100.0)  # 距上次 95 >= 10
    assert arm in cleared
    st = alloc._states[TRACK_TRANSFERABLE_ONLY][arm]
    assert st.posterior.n_trials == 0
    assert st.posterior.mu == 0.0


def test_clear_dormant_skips_recent():
    """近期更新的 arm 不被清。"""
    cfg = AllocatorConfig(dormant_clear_after_ticks=1000, forgetting_gamma=1.0)
    alloc = RegimeBanditAllocator(cfg)
    arm = make_arm_id("bull", "bb_breakout")
    _feed(alloc, arm, "bull", [20.0] * 5, t0=1.0)
    cleared = alloc.clear_dormant(now_ts=10.0)
    assert cleared == []


# ---------------------------------------------------------------------------
# fractional-Kelly 分級（鏡像 kelly_sizer.rs）
# ---------------------------------------------------------------------------


def test_fractional_kelly_tiers():
    cfg = AllocatorConfig()
    assert fractional_kelly_cap(10, cfg) == cfg.kelly_young_fraction       # young
    assert fractional_kelly_cap(100, cfg) == cfg.kelly_mature_fraction     # mature
    assert fractional_kelly_cap(500, cfg) == cfg.kelly_established_fraction  # established


def test_fractional_kelly_capped_at_max():
    cfg = AllocatorConfig(kelly_established_fraction=0.9, kelly_max_fraction=0.25)
    assert fractional_kelly_cap(1000, cfg) == 0.25


# ---------------------------------------------------------------------------
# prob_mu_positive / arm_id 工具 / 診斷
# ---------------------------------------------------------------------------


def test_prob_mu_positive_monotone():
    """強正後驗的 P(μ>0) 應接近 1；強負應接近 0。"""
    pos = NIGPosterior(mu=50.0, lam=100.0, alpha=50.0, beta=1.0, n_trials=100)
    neg = NIGPosterior(mu=-50.0, lam=100.0, alpha=50.0, beta=1.0, n_trials=100)
    assert prob_mu_positive(pos, 2000, rng=_rng()) > 0.95
    assert prob_mu_positive(neg, 2000, rng=_rng()) < 0.05


def test_make_parse_arm_id_roundtrip():
    aid = make_arm_id("high-vol", "funding_arb")
    assert aid == "high-vol__funding_arb"
    assert parse_arm_id(aid) == ("high-vol", "funding_arb")


def test_parse_flat_arm_id():
    assert parse_arm_id(FLAT_ARM_ID) == ("", FLAT_ARM_ID)


def test_invalid_regime_rejected():
    alloc = RegimeBanditAllocator()
    with pytest.raises(ValueError):
        alloc.ingest_arm_outcome("bull__x", "not_a_regime", 1.0, 1.0)


def test_invalid_fill_tier_rejected():
    alloc = RegimeBanditAllocator()
    with pytest.raises(ValueError):
        alloc.ingest_arm_outcome("bull__x", "bull", 1.0, 1.0, fill_realism_tier="bogus")


def test_arm_diagnostics_shape():
    alloc = RegimeBanditAllocator()
    arm = make_arm_id("bull", "bb_breakout")
    _feed(alloc, arm, "bull", [20.0] * 10)
    d = alloc.arm_diagnostics(arm, rng=_rng())
    assert d["arm_id"] == arm
    assert "prob_mu_positive" in d
    assert "fractional_kelly_cap" in d
    assert "explore_budget_remaining" in d
    assert d["saw_artifact"] is False


def test_explore_budget_remaining_decreases():
    cfg = AllocatorConfig(explore_budget=30, forgetting_gamma=1.0)
    alloc = RegimeBanditAllocator(cfg)
    arm = make_arm_id("bull", "bb_breakout")
    assert alloc.explore_budget_remaining(arm) == 30
    _feed(alloc, arm, "bull", [10.0] * 10)
    assert alloc.explore_budget_remaining(arm) == 20


# ---------------------------------------------------------------------------
# E4 補測：任務明示 5 場景中既有檔未直接覆蓋者
#   (3) regime 切換 → 配置隨 regime 變
#   (4) Kelly cap 不超限（全分級 sweep 斷言 ≤ max_fraction）
#   (5) exploration 預算邊界（n==budget 與超 budget 不為負）
# 不改業務邏輯；純加測。隨機全 seeded、ts 全注入，可重現。
# ---------------------------------------------------------------------------


def test_regime_switch_allocation_follows_regime():
    """同一 allocator 餵入兩 regime 各自的正/負 arm；切 regime 時配置切到
    該 regime 下訓練為正的 arm（regime-conditional，不是全域單一贏家）。

    這是任務鐵則「配到真有 realized edge 的 arm」在 regime 維度的展開：
    bull regime 只有 bull__bb_breakout 正、bear regime 只有 bear__ma_crossover 正，
    切換 candidate_arms（regime 前綴）時權重必須跟著切。
    """
    cfg = AllocatorConfig(prob_mc_samples=3000)
    alloc = RegimeBanditAllocator(cfg)

    bull_pos = make_arm_id("bull", "bb_breakout")
    bull_neg = make_arm_id("bull", "grid_trading")
    bear_pos = make_arm_id("bear", "ma_crossover")
    bear_neg = make_arm_id("bear", "bb_breakout")

    _feed(alloc, bull_pos, "bull", [35.0] * 60)
    _feed(alloc, bull_neg, "bull", [-35.0] * 60)
    _feed(alloc, bear_pos, "bear", [35.0] * 60)
    _feed(alloc, bear_neg, "bear", [-35.0] * 60)

    w_bull = alloc.allocate("bull", [bull_pos, bull_neg], rng=_rng())
    w_bear = alloc.allocate("bear", [bear_pos, bear_neg], rng=_rng())

    # bull regime：權重落在 bull 正 arm，且 bear 正 arm 完全不在 bull 候選集。
    assert w_bull.get(bull_pos, 0.0) > 0.8, f"bull 應配 bull_pos，實得 {w_bull}"
    assert bear_pos not in w_bull
    # bear regime：權重落在 bear 正 arm，且 bull 正 arm 不在 bear 候選集。
    assert w_bear.get(bear_pos, 0.0) > 0.8, f"bear 應配 bear_pos，實得 {w_bear}"
    assert bull_pos not in w_bear
    # 兩配置的主權重 arm 不同 → 證明配置確實隨 regime 變（非固定贏家）。
    bull_winner = max(w_bull, key=lambda k: w_bull[k])
    bear_winner = max(w_bear, key=lambda k: w_bear[k])
    assert bull_winner != bear_winner, "regime 切換後贏家應不同"
    assert bull_winner == bull_pos and bear_winner == bear_pos


def test_regime_switch_stale_regime_arm_not_carried_over():
    """跨 regime 隔離：只在 bull 訓練為正的 arm，不會污染 bear regime 的配置。
    bear 候選全冷（無資料）→ 即使 bull arm 強正，bear allocate 仍誠實歸 flat。
    """
    cfg = AllocatorConfig(prob_mc_samples=2000)
    alloc = RegimeBanditAllocator(cfg)
    bull_pos = make_arm_id("bull", "bb_breakout")
    _feed(alloc, bull_pos, "bull", [40.0] * 60)

    # bear regime 候選是完全沒訓練過的 arm → cold prior → P(μ>0)≈0.5 < gate。
    bear_cold = make_arm_id("bear", "ma_crossover")
    w_bear = alloc.allocate("bear", [bear_cold], rng=_rng())
    assert w_bear == {FLAT_ARM_ID: 1.0}, (
        f"bull 正 arm 不該外溢到 bear 冷候選，bear 應歸 flat，實得 {w_bear}"
    )
    # 同時 bull regime 本身仍配 bull_pos（證 bull 知識未被破壞）。
    w_bull = alloc.allocate("bull", [bull_pos], rng=_rng())
    assert w_bull.get(bull_pos, 0.0) > 0.5


def test_kelly_cap_never_exceeds_max_fraction_all_tiers():
    """Kelly cap 不超限（鐵則 4）：即使把所有分級 fraction 設到遠高於 max，
    所有 n_trials 區間回傳值都必須被夾在 kelly_max_fraction。"""
    cfg = AllocatorConfig(
        kelly_young_fraction=0.9,
        kelly_mature_fraction=0.8,
        kelly_established_fraction=0.95,
        kelly_max_fraction=0.25,
    )
    for n in (0, 1, 49, 50, 199, 200, 1000, 10_000):
        cap = fractional_kelly_cap(n, cfg)
        assert cap <= cfg.kelly_max_fraction + 1e-12, f"n={n} cap={cap} 超過 max"
        assert cap >= 0.0


def test_kelly_cap_default_tiers_monotone_nondecreasing():
    """預設分級下 cap 隨 n 單調非遞減且永不超 max（鏡像 kelly_sizer.rs 分級）。"""
    cfg = AllocatorConfig()
    ns = [0, 10, 49, 50, 100, 199, 200, 1000]
    caps = [fractional_kelly_cap(n, cfg) for n in ns]
    for prev, cur in zip(caps, caps[1:]):
        assert cur >= prev - 1e-12, f"cap 不應遞減：{caps}"
    assert all(c <= cfg.kelly_max_fraction + 1e-12 for c in caps)
    # 邊界：young<mature<established（嚴格分級存在）。
    assert fractional_kelly_cap(0, cfg) == cfg.kelly_young_fraction
    assert fractional_kelly_cap(cfg.kelly_young_threshold, cfg) == cfg.kelly_mature_fraction
    assert fractional_kelly_cap(cfg.kelly_mature_threshold, cfg) == cfg.kelly_established_fraction


def test_explore_budget_boundary_exact_and_overflow():
    """exploration 預算邊界（鐵則 5）：
      - n == explore_budget → remaining == 0（邊界相等不為負）。
      - n > explore_budget → remaining 仍夾在 0（不回負數）。
    """
    cfg = AllocatorConfig(explore_budget=30, forgetting_gamma=1.0)
    alloc = RegimeBanditAllocator(cfg)
    arm = make_arm_id("bull", "bb_breakout")
    _feed(alloc, arm, "bull", [10.0] * 30)
    assert alloc.explore_budget_remaining(arm) == 0  # 恰好用盡
    _feed(alloc, arm, "bull", [10.0] * 5, t0=31.0)
    assert alloc.explore_budget_remaining(arm) == 0  # 超用仍夾 0，不為負


def test_exploration_floor_boundary_below_and_above_budget():
    """exploitation_floor 在 explore_budget 邊界的行為：
      - 合格 arm 總樣本 < budget → 退化確定性（0/1 權重）。
      - 合格 arm 總樣本 >= budget → 走 Monte-Carlo（權重可為分數）。
    這驗證 exploration→exploitation 轉換邊界真實存在。
    """
    # 案例 A：樣本 < budget → 確定性退化。
    cfg_a = AllocatorConfig(prob_mc_samples=1500, explore_budget=50, positive_prob_gate=0.5)
    alloc_a = RegimeBanditAllocator(cfg_a)
    a1 = make_arm_id("range", "bb_reversion")
    a2 = make_arm_id("range", "ma_crossover")
    _feed(alloc_a, a1, "range", [30.0] * 10)   # 過 gate 但 10+10=20 < 50
    _feed(alloc_a, a2, "range", [20.0] * 10)
    w_a = alloc_a.allocate("range", [a1, a2], rng=_rng())
    assert set(w_a.values()) <= {0.0, 1.0}, f"低於 budget 應確定性，實得 {w_a}"

    # 案例 B：樣本 >= budget → Monte-Carlo（兩個相近正 arm 應分權，非純 0/1）。
    cfg_b = AllocatorConfig(prob_mc_samples=3000, explore_budget=20, positive_prob_gate=0.5)
    alloc_b = RegimeBanditAllocator(cfg_b)
    b1 = make_arm_id("range", "bb_reversion")
    b2 = make_arm_id("range", "ma_crossover")
    _feed(alloc_b, b1, "range", [22.0] * 40)   # 40+40 >> 20，且兩 arm 報酬相近
    _feed(alloc_b, b2, "range", [20.0] * 40)
    w_b = alloc_b.allocate("range", [b1, b2], rng=_rng())
    # 至少一個真 arm 拿到嚴格介於 0 與 1 之間的分數權重（證走了 MC 而非退化）。
    frac_weights = [v for k, v in w_b.items() if 0.0 < v < 1.0]
    assert frac_weights, f"高於 budget 應走 MC 出分數權重，實得 {w_b}"
    assert abs(sum(w_b.values()) - 1.0) < 1e-9
