"""
demo_maker_arm 單元測試。

涵蓋誠實鐵則：
  - demo-maker arm 永遠是 post-only + artifact tier（不可偽裝成可轉移）。
  - build_demo_maker_reward 構造的 reward 走 all_fills 軌標 saw_artifact、
    transferable_only 軌（promotion 軌）不吸收。
  - artifact 增益在 transferable_only 軌上 0 配置權重（無 promotion power）。

防 prod 污染：autouse _no_real_db；本模組無 DB IO，閘為縱深防禦。
"""

from __future__ import annotations

import inspect
import random

import pytest

from program_code.ml_training.adaptive_demo_profit_engine.demo_maker_arm import (
    DEMO_MAKER_ARM,
    DemoMakerArmSpec,
    build_demo_maker_reward,
)
from program_code.ml_training.regime_bandit_allocator import (
    FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT,
    FLAT_ARM_ID,
    AllocatorConfig,
    RegimeBanditAllocator,
)


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch):
    """攔真 psycopg2.connect：本模組無 DB IO，此閘為縱深防禦。"""
    try:
        import psycopg2  # noqa: PLC0415

        def _blocked(*_a, **_k):
            raise AssertionError("測試禁止真 psycopg2.connect（_no_real_db 鐵閘）")

        monkeypatch.setattr(psycopg2, "connect", _blocked)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# spec 不可變性 / artifact tier 硬鎖
# ---------------------------------------------------------------------------


def test_demo_maker_arm_is_post_only_and_artifact_tier():
    assert DEMO_MAKER_ARM.post_only is True
    assert DEMO_MAKER_ARM.fill_realism_tier == FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT


def test_demo_maker_arm_id_shape():
    # 'regime__strategy' 形狀。
    assert DEMO_MAKER_ARM.arm_id == "range__grid_trading"


def test_spec_is_frozen():
    # frozen dataclass：arm 定義不可在 runtime 被改寫。
    with pytest.raises(Exception):
        DEMO_MAKER_ARM.post_only = False  # type: ignore[misc]


def test_build_reward_does_not_expose_tier_override():
    # 簽名刻意不暴露 tier 參數 → 呼叫端無法把 artifact 偽裝成 taker_real。
    params = list(inspect.signature(build_demo_maker_reward).parameters.keys())
    assert "fill_realism_tier" not in params
    assert "tier" not in params


def test_build_reward_always_artifact_tier():
    r = build_demo_maker_reward(123.4, 5.0)
    assert r.fill_realism_tier == FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT
    assert r.transferable is False
    assert r.realized_pnl_bps == 123.4
    assert r.regime == "range"


def test_build_reward_does_not_synthesize_or_clip():
    # 負價差照實傳遞，不夾正（不合成 PnL）。
    r = build_demo_maker_reward(-77.0, 1.0)
    assert r.realized_pnl_bps == -77.0


# ---------------------------------------------------------------------------
# 誠實隔離：透過 allocator 雙軌驗證
# ---------------------------------------------------------------------------


def test_artifact_not_absorbed_by_transferable_track():
    alloc = RegimeBanditAllocator(AllocatorConfig())
    for i in range(40):
        r = build_demo_maker_reward(70.0, float(i))
        alloc.ingest_arm_outcome(
            r.arm_id, r.regime, r.realized_pnl_bps, r.ts, r.fill_realism_tier
        )
    diag_tr = alloc.arm_diagnostics(DEMO_MAKER_ARM.arm_id, track="transferable_only")
    diag_all = alloc.arm_diagnostics(DEMO_MAKER_ARM.arm_id, track="all_fills")
    # transferable_only 軌完全不吸收 artifact。
    assert diag_tr["n_trials"] == 0
    # all_fills 軌吸收且標 saw_artifact。
    assert diag_all["n_trials"] == 40
    assert diag_all["saw_artifact"] is True


def test_artifact_has_zero_promotion_power_on_transferable_track():
    # 即使 demo-maker 在 demo 上呈現巨大正 PnL，promotion 軌（transferable_only）
    # 上它仍歸 flat（無 promotion power）= 誠實鐵則。
    alloc = RegimeBanditAllocator(AllocatorConfig())
    for i in range(50):
        r = build_demo_maker_reward(90.0, float(i))
        alloc.ingest_arm_outcome(
            r.arm_id, r.regime, r.realized_pnl_bps, r.ts, r.fill_realism_tier
        )
    weights = alloc.allocate(
        "range",
        [DEMO_MAKER_ARM.arm_id],
        rng=random.Random(1),
        track="transferable_only",
    )
    assert weights == {FLAT_ARM_ID: 1.0}


def test_custom_spec_regime_must_be_valid():
    bad = DemoMakerArmSpec(strategy="grid_trading", regime="not_a_regime")
    with pytest.raises(ValueError):
        build_demo_maker_reward(10.0, 1.0, spec=bad)
