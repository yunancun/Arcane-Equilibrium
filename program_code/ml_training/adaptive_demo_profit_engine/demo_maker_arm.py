"""
MODULE_NOTE (中):
  用途：demo-maker 候選 arm 的**定義 / 註冊 cell**（純資料 + 純函數，無 DB / IPC /
  下單）。demo-maker = post-only maker 單捕價差：在 demo 沙盒裡，撮合無 orderbook
  queue → maker 單立即成交且不吃逆選擇 → 在 demo 上呈現正 PnL。

  主要類 / 函數：
    - DemoMakerArmSpec：candidate arm 的不可變定義（arm_id、post-only、fill tier）。
    - DEMO_MAKER_ARM：本 package 唯一內建 demo-maker candidate（grid_trading 系，
      regime-agnostic 用 'range'）。
    - build_demo_maker_reward：把一筆 demo-maker round-trip 已實現價差（bps）包成
      allocator 認得的 ArmReward，**硬編 fill_realism_tier=
      maker_no_queue_demo_artifact** → 走 all_fills 軌標 saw_artifact、
      transferable_only 軌誠實不吸收。

  依賴：program_code.ml_training.regime_bandit_allocator（ArmReward / fill tier 常數 /
  make_arm_id）。本模組**只**構造 reward 物件，不 ingest、不下單。

  硬邊界 / 誠實鐵則（為什麼這樣設計）：
    1. **不改既有 strategy 框架**。demo-maker 不是新 Rust 策略、不註冊進
       orchestrator strategy registry；它只是 allocator arm-space 裡的一個
       candidate id + 一個 reward 構造器。真實「下 post-only 單」由既有 demo
       引擎 / 既有策略產生（本 cell 不發單），ADPE 只在 allocator 層把它當一個
       可被配置 / 評分的 arm。這樣 0 改既有檔（符任務硬約束）。
    2. **增益必標 artifact 不可轉移**。demo 無排隊 maker 立即成交是 demo 撮合
       artifact，mainnet 會排隊 / 部分不成交，故此 arm 的 reward **強制**
       fill_realism_tier=maker_no_queue_demo_artifact → allocator transferable_only
       軌不吸收（promotion 鐵則），all_fills 軌吸收但標 saw_artifact 供審計。
       絕不可把這個 tier 改成 taker_real / maker_queued_real 偽裝成可轉移 edge。
    3. **不合成 PnL**。realized_spread_bps 必須由呼叫端餵入真 demo round-trip
       已實現價差；本模組不發明任何正報酬。
"""

from __future__ import annotations

from dataclasses import dataclass

from program_code.ml_training.regime_bandit_allocator import (
    FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT,
    VALID_REGIMES,
    ArmReward,
    make_arm_id,
)

# demo-maker 綁定的底層策略名（與 mlde_edge_training_rows strategy_name_norm 對齊：
# grid_trading 是 maker 掛單捕價差語意最近的既有 5-enum 策略）。
DEMO_MAKER_STRATEGY = "grid_trading"

# demo-maker 的 regime context：post-only 捕價差在區間 / 震盪市最自然，故綁 'range'。
# 'range' 在 allocator VALID_REGIMES 內（誠實對齊，不發明新 regime 值）。
DEMO_MAKER_REGIME = "range"


@dataclass(frozen=True)
class DemoMakerArmSpec:
    """demo-maker 候選 arm 的不可變定義。

    為什麼 frozen：arm 定義是 arm-space 的穩定錨點（持久化 / 日誌 key），
    不該在 runtime 被改寫。
    """

    strategy: str
    regime: str
    # post_only 永遠 True：demo-maker 的全部論點就是「post-only maker 在 demo 無
    # 排隊 → 立即成交且不吃逆選擇」。non-post-only 就不是這個 arm。
    post_only: bool = True
    # fill tier 永遠是 demo artifact tier：見 MODULE_NOTE 鐵則 2，硬編不可變。
    fill_realism_tier: str = FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT

    @property
    def arm_id(self) -> str:
        """allocator arm_id（'regime__strategy'，鏡像 make_arm_id）。"""
        return make_arm_id(self.regime, self.strategy)


# 本 package 唯一內建 demo-maker candidate arm。
# regime='range' / strategy='grid_trading' / post-only / artifact tier。
DEMO_MAKER_ARM = DemoMakerArmSpec(
    strategy=DEMO_MAKER_STRATEGY,
    regime=DEMO_MAKER_REGIME,
)


def build_demo_maker_reward(
    realized_spread_bps: float,
    ts: float,
    *,
    spec: DemoMakerArmSpec = DEMO_MAKER_ARM,
) -> ArmReward:
    """把一筆 demo-maker round-trip 已實現價差包成 allocator 的 ArmReward。

    為什麼 fill_realism_tier 來自 spec（恆 artifact tier）：見 MODULE_NOTE 鐵則 2。
    呼叫端**不可**覆寫 tier — 簽名刻意不暴露 tier 參數，避免把 demo artifact
    增益偽裝成可轉移 edge。

    realized_spread_bps：呼叫端餵入的真 demo 已實現價差（bps，可正可負）；
    本函數不合成、不夾正。
    """
    if spec.regime not in VALID_REGIMES:
        # 防呆：spec 的 regime 必須在 allocator 詞彙內，否則 ingest 會 raise。
        raise ValueError(f"demo-maker spec regime 不在 VALID_REGIMES: {spec.regime!r}")
    return ArmReward(
        arm_id=spec.arm_id,
        regime=spec.regime,
        realized_pnl_bps=float(realized_spread_bps),
        ts=float(ts),
        fill_realism_tier=spec.fill_realism_tier,
    )
