"""
MODULE_NOTE (中):
  用途：ADPE 閉環的**唯一可信 reward 源**讀取層。讀近窗 realized demo PnL，per
  (strategy, regime) 聚成 ArmReward 序列，餵給 allocator。複用 linucb_trainer 的 SQL
  pattern（engine_mode_scope / statement_timeout / psycopg2 connect_timeout），不 fork、
  不抄 legacy decision_outcomes。

  資料源（2026-06-14 效能修法，MIT RCA adpe-reward-query-perf-rca）：**直查 base 表
  trading.intents JOIN learning.decision_features（+ decision_context_snapshots PK
  lateral 取 regime）**，不再走 learning.mlde_edge_training_rows view。原因：view 的
  intent_base CTE 含一個對 trading.signals（壓縮 hypertable、segmentby 不含 signal_id）
  的 signal_id-only LATERAL，會 per-outer-row bulk-decompress 壓縮 chunk，30d demo 視窗
  實測 3827s（64 分）；砍掉該 lateral 後 962ms（~3975x）、per-(strategy, regime) 分組 count
  與 view 逐 arm diff=0（行為等價）。輸出欄序 / regime / strategy 詞彙與 view 完全一致，
  下游映射路徑零改。詳見 _REWARD_SQL 上方註釋的等價性與 attribution 放寬 caveat。

  主要函數：
    - fetch_demo_arm_rewards(dsn, ...)：跑唯一一條 read-only SELECT，回
      list[ArmReward]（taker_real tier，realized post-fee）。
    - fetch_demo_side_edge_cells(dsn, ...)：同源讀近窗 realized demo PnL，聚合成
      (strategy, symbol, entry side) side-aware edge evidence，供 ADPE 在 JSON side overlay
      遺失時仍能 fail-closed 地評估 cost wall。
    - map_view_regime_to_alloc_regime：view 詞彙 regime enum（trending/mean_reverting/
      random_walk）→ allocator VALID_REGIMES（chop/range/...）的誠實映射。

  依賴：
    - psycopg2（live 路徑；單元測試以 fake cursor 注入，不連真 PG）。
    - program_code.ml_training.linucb_trainer.engine_mode_scope / _set_local_statement_timeout
      （SQL pattern 100% 複用，不重寫）。
    - program_code.ml_training.regime_bandit_allocator.ArmReward / VALID_REGIMES /
      FILL_TIER_TAKER_REAL。
    - PG 物件：trading.intents / learning.decision_features /
      trading.decision_context_snapshots（皆 read-only 直查；regime_norm 邏輯逐字鏡像
      V031:274-282；linucb_arm_id 形狀鏡像 V031:326）。

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


# 唯一 read-only SELECT（demo-scope、post-fee、structural-attribution-gated）。
#
# 為什麼直查 base 表而非走 learning.mlde_edge_training_rows view（MIT RCA
# 2026-06-14--adpe-reward-query-perf-rca.md）：
#   view 的 `intent_base` CTE 含一個 `LEFT JOIN LATERAL trading.signals
#   WHERE s.signal_id = i.signal_id ORDER BY ts DESC LIMIT 1`。trading.signals 是
#   TimescaleDB hypertable，壓縮 segmentby=symbol（不含 signal_id），PK=(signal_id,
#   ts)。以「裸 signal_id 無 ts 約束」查 → ChunkAppend 無法 prune chunk，歷史壓縮
#   chunk 退化成 per-outer-row 的 Bulk Decompression 全掃（每 outer row 解壓一遍整個
#   columnar chunk）。30d demo 視窗（144,526 rows）此 lateral 把查詢從應有的 ~1s 拖到
#   實測 3827s（64 分），且 5000ms statement_timeout 對 view 整體 plan 顯然未能即時砍掉
#   （超線性壞 plan）。MIT Linux PG 親驗：砍掉 signals lateral 後 962ms / 144,526 rows
#   = ~3975x，且 per-(strategy, regime) 分組 count 與 view 逐 arm diff=0（行為等價）。
#
# 等價性與 vocab 不變式（MIT §3 實證 + 本模組鐵則 5）：
#   1. 輸出仍是 5 欄、同順序 (linucb_arm_id, strategy_name, regime, net_bps_after_fee,
#      ts_secs)，regime / strategy 仍是 **view 詞彙**（trending / mean_reverting /
#      random_walk），下游 map_view_regime_to_alloc_regime / make_arm_id 重建路徑零改。
#   2. strategy_name 用 intent/feature 欄 COALESCE（與 view 的 raw_strategy_name 同源；
#      MIT 實測 144,526 row 全部由 intent/feature 欄提供，signals 對 strategy 非 load-bearing）。
#   3. regime_norm 邏輯逐字鏡像 V031:274-282（dcs.regime_5m LIKE 比對 + strategy fallback），
#      dcs lateral 走 decision_context_snapshots PK (context_id, ts) 前導欄，0.001ms/loop，不慢。
#   4. linucb_arm_id 維持 `<view_regime>__<strategy>` 形狀（V031:326），reward_source 的
#      _strategy_from_view_arm_id 只取後段 strategy、丟棄前段 view regime，故形狀必須保持。
#
# 誠實 caveat（attribution 由「signals 再讀比對」放寬為「結構性」）：
#   view 的 attribution_chain_ok 含 `signal_context_id = context_id`（再讀 signals 比對其
#   context_id 與 intent 一致）。本查詢以結構性條件取代：signal_id / context_id 非空 +
#   df.label_net_edge_bps 存在。MIT 30d demo 實證此放寬對 label-present demo row 濾掉 0 行
#   （144,526 == 144,526），但語義上略放寬（不再驗 signal 自身 context_id）。嚴格保留語義
#   且仍快只能走 schema 級（signals 壓縮 segmentby 含 signal_id / 建投影表），需 V### +
#   Guard A/B/C + Linux double-apply，且實證對 demo reward 無行為收益 → 不採（needs_migration=false）。
_REWARD_SQL = """
    WITH base AS (
        SELECT i.ts,
               i.context_id,
               lower(COALESCE(NULLIF(i.strategy_name, ''), NULLIF(df.strategy_name, ''), '')) AS raw_strat,
               df.label_net_edge_bps AS net_bps
          FROM trading.intents i
          JOIN learning.decision_features df ON df.context_id = i.context_id
         WHERE i.engine_mode = ANY(%s)
           AND df.label_net_edge_bps IS NOT NULL
           AND i.signal_id IS NOT NULL AND i.signal_id <> ''
           AND i.context_id IS NOT NULL AND i.context_id <> ''
           AND COALESCE(i.details->>'source', '') <> 'command'
           AND (%s::INT IS NULL OR i.ts >= now() - (%s::INT || ' days')::interval)
    )
    SELECT
        (q.regime_norm || '__' || q.strat_norm) AS linucb_arm_id,
        q.strat_norm AS strategy_name,
        q.regime_norm AS regime,
        q.net_bps AS net_bps_after_fee,
        floor(extract(epoch FROM q.ts))::double precision AS ts_secs
    FROM (
        SELECT b.ts,
               b.net_bps,
               CASE b.raw_strat WHEN 'bollinger_reversion' THEN 'bb_reversion' ELSE b.raw_strat END AS strat_norm,
               CASE
                   WHEN lower(COALESCE(d.regime_5m, '')) LIKE '%%trend%%' THEN 'trending'
                   WHEN lower(COALESCE(d.regime_5m, '')) LIKE ANY(ARRAY['%%mean%%', '%%range%%', '%%anti%%']) THEN 'mean_reverting'
                   WHEN b.raw_strat IN ('grid_trading', 'bb_reversion', 'bollinger_reversion') THEN 'mean_reverting'
                   WHEN b.raw_strat IN ('ma_crossover', 'bb_breakout') THEN 'trending'
                   ELSE 'random_walk'
               END AS regime_norm
          FROM base b
          LEFT JOIN LATERAL (
              SELECT d.regime_5m
                FROM trading.decision_context_snapshots d
               WHERE d.context_id = b.context_id
               ORDER BY d.ts DESC
               LIMIT 1
          ) d ON TRUE
         WHERE b.raw_strat IN ('bollinger_reversion', 'bb_reversion', 'bb_breakout', 'ma_crossover', 'grid_trading', 'funding_arb')
    ) q
    ORDER BY ts_secs ASC
"""

_SIDE_EDGE_SQL = """
    WITH base AS (
        SELECT
            CASE lower(COALESCE(NULLIF(df.strategy_name, ''), NULLIF(i.strategy_name, ''), ''))
                WHEN 'bollinger_reversion' THEN 'bb_reversion'
                ELSE lower(COALESCE(NULLIF(df.strategy_name, ''), NULLIF(i.strategy_name, ''), ''))
            END AS strategy_name,
            df.symbol AS symbol,
            CASE
                WHEN df.side > 0 THEN 'Buy'
                WHEN df.side < 0 THEN 'Sell'
                ELSE NULL
            END AS entry_side,
            df.label_net_edge_bps AS net_bps
          FROM trading.intents i
          JOIN learning.decision_features df ON df.context_id = i.context_id
         WHERE i.engine_mode = ANY(%s)
           AND df.engine_mode = ANY(%s)
           AND df.label_net_edge_bps IS NOT NULL
           AND i.signal_id IS NOT NULL AND i.signal_id <> ''
           AND i.context_id IS NOT NULL AND i.context_id <> ''
           AND COALESCE(i.details->>'source', '') <> 'command'
           AND (%s::INT IS NULL OR i.ts >= now() - (%s::INT || ' days')::interval)
    )
    SELECT
        strategy_name,
        symbol,
        entry_side,
        count(*)::int AS n,
        avg(net_bps)::double precision AS mean_bps,
        COALESCE(stddev_samp(net_bps), 0.0)::double precision AS std_bps,
        avg((net_bps > 0.0)::int)::double precision AS win_rate,
        COALESCE(avg(net_bps) FILTER (WHERE net_bps > 0.0), 0.0)::double precision AS avg_win_bps,
        COALESCE(avg(net_bps) FILTER (WHERE net_bps <= 0.0), 0.0)::double precision AS avg_loss_bps
      FROM base
     WHERE strategy_name IN ('bb_reversion', 'bb_breakout', 'ma_crossover', 'grid_trading', 'funding_arb')
       AND COALESCE(symbol, '') <> ''
       AND entry_side IS NOT NULL
     GROUP BY strategy_name, symbol, entry_side
     ORDER BY strategy_name, symbol, entry_side
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

    誠實：reward = realized post-fee net_bps（df.label_net_edge_bps，直查 base 表），本函數
    不合成任何報酬。regime 由 _REWARD_SQL 在 SQL 側算出 view 詞彙（trending/mean_reverting/
    random_walk，邏輯鏡像 V031:274-282），再經 map_view_regime_to_alloc_regime 對齊 allocator
    詞彙；映射不到 / regime 為 NULL → insufficient_context（誠實降級）。**arm_id 不原樣沿用
    SQL 回的 view 詞彙 linucb_arm_id**（它嵌 view 詞彙 regime，下游會被靜默丟棄；見 MODULE_NOTE
    鐵則 5），而是用 allocator 的 make_arm_id(alloc_regime, strategy) 重建，保證與 runner
    allocate() 期望的 candidate_arm 詞彙端到端一致。

    fail-soft：statement_timeout_ms 經 _set_local_statement_timeout 以 `SET LOCAL
    statement_timeout` 套在本交易（psycopg2 connect 預設 autocommit=False，with-block 開
    交易，SET LOCAL 綁定之）。慢查詢 raise（QueryCanceled）而非 hang；呼叫端（runner driver）
    以 fail-soft 接（reward 源異常 → 本 cycle 視為空 reward / 全 explore，不污染閉環）。
    效能修法後 30d demo 962ms 遠在 5000ms 限內，timeout 為防呆兜底而非熱路徑常觸。
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


def fetch_demo_side_edge_cells(
    dsn: str,
    *,
    max_age_days: Optional[int] = 30,
    statement_timeout_ms: Optional[int] = DEFAULT_PG_STATEMENT_TIMEOUT_MS,
    _connect=None,
) -> list[dict]:
    """Read demo realized edge grouped by strategy/symbol/entry-side.

    This is an evidence fallback for ADPE only. It does not write snapshots and
    does not grant order authority; runner still applies the same cost-wall and
    runtime-readiness filters used for JSON side cells.
    """
    connect = _connect
    if connect is None:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 not installed / psycopg2 未安裝")
        connect = psycopg2.connect  # pragma: no cover — live path

    engine_modes = list(engine_mode_scope(_DEMO_ENGINE_MODE))
    out: list[dict] = []
    with connect(dsn, connect_timeout=2) as conn:
        with conn.cursor() as cur:
            _set_local_statement_timeout(cur, statement_timeout_ms)
            cur.execute(
                _SIDE_EDGE_SQL,
                (engine_modes, engine_modes, max_age_days, max_age_days),
            )
            for (
                strategy,
                symbol,
                side,
                n,
                mean_bps,
                std_bps,
                win_rate,
                avg_win_bps,
                avg_loss_bps,
            ) in cur.fetchall():
                if not strategy or not symbol or side not in ("Buy", "Sell"):
                    continue
                mean = float(mean_bps)
                wins = float(win_rate)
                out.append(
                    {
                        "strategy": str(strategy),
                        "symbol": str(symbol),
                        "side": str(side),
                        "key": f"{strategy}::{symbol}::{side}",
                        "source": "db_decision_features_side_edge",
                        "cell": {
                            "shrunk_bps": mean,
                            "runtime_bps": mean,
                            "raw_bps": mean,
                            "n": int(n),
                            "std_bps": float(std_bps or 0.0),
                            "win_rate": wins,
                            "win_rate_shrunk": wins,
                            "avg_win_bps_shrunk": float(avg_win_bps or 0.0),
                            "avg_loss_bps_shrunk": float(avg_loss_bps or 0.0),
                            "combined_ev_bps": mean,
                            "validation_passed": False,
                            "validation_reason": "db_side_edge_demo_only_not_promotion_evidence",
                            "_side": str(side),
                            "_side_from": "learning.decision_features.side",
                        },
                    }
                )
    return out
