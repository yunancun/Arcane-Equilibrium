"""
MODULE_NOTE (中):
  用途：ADPE 閉環的**唯一可信 reward 源**讀取層。從 learning.mlde_edge_training_rows
  （V031/V034 view）讀近窗 realized demo PnL，per (strategy, regime) 聚成
  ArmReward 序列，餵給 allocator。複用 linucb_trainer 的 SQL pattern（engine_mode_scope /
  statement_timeout / psycopg2 connect_timeout），不 fork、不抄 legacy decision_outcomes。

  主要函數：
    - fetch_demo_arm_rewards(dsn, ...)：跑唯一一條 read-only SELECT，回
      list[ArmReward]（taker_real tier，realized post-fee）。
    - map_view_regime_to_alloc_regime：view 的 regime enum（trending/mean_reverting/
      random_walk）→ allocator VALID_REGIMES（chop/range/...）的誠實映射。

  依賴：
    - psycopg2（live 路徑；單元測試以 fake cursor 注入，不連真 PG）。
    - program_code.ml_training.linucb_trainer.engine_mode_scope / _set_local_statement_timeout
      （SQL pattern 100% 複用，不重寫）。
    - program_code.ml_training.regime_bandit_allocator.ArmReward / VALID_REGIMES /
      FILL_TIER_TAKER_REAL。

  硬邊界 / 誠實鐵則（為什麼這樣設計）：
    1. **engine_mode 硬鎖 demo**。SQL `WHERE engine_mode = ANY(engine_mode_scope('demo'))`，
       拒 live / live_demo。reward 污染 live = 違誠實鐵則 + 跨 demo 沙盒邊界。
    2. **只取 post-fee + attribution-gated**。`attribution_chain_ok AND net_bps_after_fee
       IS NOT NULL`（鏡像 linucb_trainer:289-291）。net_bps_after_fee 是扣費後真報酬，
       非 estimate；attribution gate 擋斷鏈的假歸因。
    3. **不走 decision_outcomes**。trading.decision_outcomes.outcome_net_bps 100% NULL
       （已知 bug，layer2_critic:414 自承）→ 用它 = 假 reward。本模組只走 mlde view。
    4. **view-fetched reward 一律 taker_real tier**。這條路徑讀的是引擎真實成交歸因，
       不是 demo-maker artifact（後者由 demo_maker_arm.build_demo_maker_reward 另標）。
    5. **arm_id 詞彙端到端一致（命門，修 E2 RETURN）**。view 的 linucb_arm_id 是
       `regime_norm || '__' || strategy_name_norm`（V031:326），regime_norm ∈
       {trending, mean_reverting, random_walk}（view 詞彙）；但 allocator / runner 的
       arm-space 用 VALID_REGIMES（{bull,bear,high-vol,chop,range,insufficient_context}）。
       若把 view 的 linucb_arm_id 原樣當 ArmReward.arm_id，下游 runner.parse_arm_id 會解出
       view 詞彙 regime（如 'trending'），不在 VALID_REGIMES → 被 _discover_candidate_arms
       靜默丟棄 → 真路徑永遠 flat（這正是 E2 抓的 vacuous 缺陷）。**修法 = 本模組產出的
       arm_id 一律用 allocator 的 make_arm_id(alloc_regime, strategy) 重建**（與 runner /
       demo_maker_arm 同一構造函數，非兩處手寫），故 ArmReward.arm_id 與 ArmReward.regime
       同詞彙、且與 runner allocate() 期望的 candidate_arm 詞彙逐字一致。strategy 由 view
       的 linucb_arm_id 拆出（與 strategy_name 欄一致，view 已保證兩者同源）。
"""

from __future__ import annotations

from typing import Optional

try:
    import psycopg2
except ImportError:  # pragma: no cover — psycopg2 在 ml_training env 必裝
    psycopg2 = None  # type: ignore[assignment]

# SQL pattern 100% 複用 linucb_trainer，不重寫。
from program_code.ml_training.linucb_trainer import (
    engine_mode_scope,
    _set_local_statement_timeout,
)
from program_code.ml_training.regime_bandit_allocator import (
    FILL_TIER_TAKER_REAL,
    VALID_REGIMES,
    ArmReward,
    make_arm_id,
    parse_arm_id,
)

# 預設 PG statement timeout（與 linucb_trainer DEFAULT_PG_STATEMENT_TIMEOUT_MS 同量級，
# 此處本地常數避免跨檔耦合 import 私名）。
DEFAULT_PG_STATEMENT_TIMEOUT_MS = 5000

# demo-scope engine_mode 硬鎖（唯一允許值）。
_DEMO_ENGINE_MODE = "demo"

# mlde_edge_training_rows view 的 regime enum（V031:274-282 regime_norm）
# → allocator VALID_REGIMES 的誠實映射。
#   trending       → high-vol（趨勢期 = 方向性波動主導；allocator 無 'trending'，
#                    最近語義是 high-vol 的方向性 regime context）
#   mean_reverting → range（均值回歸 = 區間 / 震盪，對齊 allocator 'range'）
#   random_walk    → chop（無結構 = 來回切，對齊 allocator 'chop'）
# 注：此映射是「view 詞彙 → allocator 詞彙」的 best-effort 對齊（兩套 enum 由不同
# migration / 模組獨立演進，無共用 SSOT）。映射不到者退 insufficient_context（誠實降級，
# 不 cherry-pick）。
_VIEW_REGIME_TO_ALLOC = {
    "trending": "high-vol",
    "mean_reverting": "range",
    "random_walk": "chop",
}


def map_view_regime_to_alloc_regime(view_regime: Optional[str]) -> str:
    """view regime enum → allocator VALID_REGIMES。

    為什麼 fallback=insufficient_context：映射不到的 regime 值（含 None / 未知字串）
    退到 allocator 的 insufficient_context（它在 VALID_REGIMES 內），避免亂塞一個
    具體 regime 造成 selection bias。
    """
    if not view_regime:
        return "insufficient_context"
    mapped = _VIEW_REGIME_TO_ALLOC.get(str(view_regime).strip().lower())
    if mapped is None or mapped not in VALID_REGIMES:
        return "insufficient_context"
    return mapped


def _strategy_from_view_arm_id(view_arm_id: str, strategy_name: Optional[str]) -> Optional[str]:
    """從 view 的 linucb_arm_id（`view_regime__strategy`）拆出 strategy 段。

    為什麼不直接用 strategy_name 欄：view 已保證 linucb_arm_id 的後段 == strategy_name_norm
    （V031:326 同源 sr.strategy_name_norm），優先用 arm_id 拆出的後段以對齊 arm-space；
    若 view arm_id 形狀異常（無分隔符），退用 strategy_name 欄（誠實降級）。
    兩者皆缺 → 回 None（呼叫端跳過該筆，不亂塞）。

    注意：本函數用 allocator 的 parse_arm_id 拆分（同一 _ARM_SEP），但 view arm_id 的
    regime 段是 view 詞彙（不在 VALID_REGIMES），故只取 strategy 段、丟棄其 regime 段
    （regime 改用 regime 欄經 map_view_regime_to_alloc_regime 對齊）。
    """
    if view_arm_id:
        try:
            _view_regime, strategy = parse_arm_id(str(view_arm_id))
        except ValueError:
            strategy = None
        if strategy:
            return strategy
    if strategy_name:
        s = str(strategy_name).strip()
        if s:
            return s
    return None


# 唯一 read-only SELECT（demo-scope、post-fee、attribution-gated）。
# 鏡像 linucb_trainer.fetch_arm_observations 的 mlde 分支（:285-297）的 WHERE 結構，
# 但聚 (linucb_arm_id, regime, ts, net_bps_after_fee) 給 allocator 逐筆 ingest。
_REWARD_SQL = """
    SELECT linucb_arm_id,
           strategy_name,
           regime,
           net_bps_after_fee,
           floor(extract(epoch FROM ts))::double precision AS ts_secs
      FROM learning.mlde_edge_training_rows
     WHERE engine_mode = ANY(%s)
       AND attribution_chain_ok
       AND net_bps_after_fee IS NOT NULL
       AND linucb_arm_id IS NOT NULL
       AND (%s::INT IS NULL OR ts >= now() - (%s::INT || ' days')::interval)
     ORDER BY ts ASC
"""


def fetch_demo_arm_rewards(
    dsn: str,
    *,
    max_age_days: Optional[int] = 30,
    statement_timeout_ms: Optional[int] = DEFAULT_PG_STATEMENT_TIMEOUT_MS,
    _connect=None,
) -> list[ArmReward]:
    """讀近窗 demo realized reward，回 list[ArmReward]（taker_real tier）。

    參數：
      dsn：PG 連線字串（呼叫端提供，不在此硬編）。
      max_age_days：只取近 N 天（None=不限）。預設 30（近窗，對齊 cycle 學習視野）。
      _connect：測試注入點（注入 fake connect 取代 psycopg2.connect），
        production 不傳則用 psycopg2.connect。

    誠實：reward = realized post-fee net_bps，本函數不合成任何報酬。
    regime 經 map_view_regime_to_alloc_regime 由 view 詞彙對齊 allocator 詞彙；映射不到 /
    view regime 為 NULL → insufficient_context（誠實降級）。**arm_id 不原樣沿用 view 的
    linucb_arm_id**（它嵌 view 詞彙 regime，下游會被靜默丟棄；見 MODULE_NOTE 鐵則 5），
    而是用 allocator 的 make_arm_id(alloc_regime, strategy) 重建，保證與 runner allocate()
    期望的 candidate_arm 詞彙端到端一致。
    """
    connect = _connect
    if connect is None:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 not installed / psycopg2 未安裝")
        connect = psycopg2.connect  # pragma: no cover — live path

    engine_modes = list(engine_mode_scope(_DEMO_ENGINE_MODE))
    out: list[ArmReward] = []

    # connect_timeout=2 對齊 linucb_trainer:280（短超時、fail-fast）。
    with connect(dsn, connect_timeout=2) as conn:
        with conn.cursor() as cur:
            _set_local_statement_timeout(cur, statement_timeout_ms)
            cur.execute(_REWARD_SQL, (engine_modes, max_age_days, max_age_days))
            for view_arm_id, strategy_name, view_regime, net_bps, ts_secs in cur.fetchall():
                if view_arm_id is None or net_bps is None:
                    continue
                # regime：view 詞彙 → allocator 詞彙（單一映射 SSOT）。
                alloc_regime = map_view_regime_to_alloc_regime(view_regime)
                # strategy：從 view arm_id 後段拆出（與 strategy_name 欄同源，V031:326）。
                strategy = _strategy_from_view_arm_id(str(view_arm_id), strategy_name)
                if not strategy:
                    # view arm_id 形狀異常且無 strategy_name → 跳過（不亂塞）。
                    continue
                # arm_id：用 allocator 的構造函數重建（與 runner / demo_maker_arm 同一 SSOT）。
                # 這是 vocab 端到端一致的命門：reconstructed arm_id 的 regime 段 == alloc_regime
                # == ArmReward.regime，且與 runner make_arm_id(regime, strategy) 逐字相同。
                alloc_arm_id = make_arm_id(alloc_regime, strategy)
                out.append(
                    ArmReward(
                        arm_id=alloc_arm_id,
                        regime=alloc_regime,
                        realized_pnl_bps=float(net_bps),
                        ts=float(ts_secs) if ts_secs is not None else 0.0,
                        # view 路徑 = 引擎真實成交歸因 → taker_real（非 demo-maker artifact）。
                        fill_realism_tier=FILL_TIER_TAKER_REAL,
                    )
                )
    return out
