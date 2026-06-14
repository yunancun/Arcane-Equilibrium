"""
Regime-conditional Thompson-sampling demo allocator (核心配置核心).
Regime 條件化 Thompson-sampling demo 配置器 — 核心數學 / 編排層。

MODULE_NOTE (中):
  用途：在「每個 regime」下，對候選 arm（regime__strategy 三元組外加一個
  flat/cash stand-down arm）做 Thompson-sampling 配置，輸出權重 dict。
  這是 Adaptive Demo Profit Engine 的**核心 allocator 模組**。

  主要類/函數：
    - ArmReward / ArmState：純資料載體（單筆 round-trip 報酬 + 每 arm 後驗狀態）。
    - AllocatorConfig：所有閾值/上限的單一來源（不在 code 散落硬編碼）。
    - RegimeBanditAllocator：ingest_arm_outcome → update posterior →
      allocate(regime, candidate_arms) → 權重 dict（含 flat-arm）。
    - fractional_kelly_cap：把權重折成 fractional-Kelly 上限（鏡像 Rust
      kelly_sizer.rs:189 compute_kelly_qty 的分級 + max_fraction 語意，
      但本模組**不**下單、不算 qty，只給出 sizing 上限係數）。

  依賴：
    - program_code.ml_training.thompson_sampling（NIGPosterior + 共軛更新 +
      empirical_bayes + sample_nig + exploitation_floor）——bandit 數學 100%
      reuse，本模組只做編排，不發明新數學。
    - numpy（sample_nig 需要；Monte-Carlo P(μ>0) 估計）。

  硬邊界 / 誠實鐵則（為什麼這樣設計）：
    1. **尚未接入引擎**。本模組是 pure-Python 核心 + 可單元測試，**不**讀真 DB、
       **不**下單、**不**寫 live config、**不**碰 mainnet 5-gate。整合（PG IO /
       cron / consumer 接線）是下一輪 operator-gated 工作。
    2. **全負 EV → 歸 flat（學會歸零，不硬湊正）**。當所有真 arm 的
       P(μ>0) < positive_prob_gate 時，allocate 把 100% 權重給 flat-arm
       （stand-down）。這個管線本身不創造 alpha；它只在有正 EV arm 出現時才配，
       無則歸零防虧。當前 runtime 事實是底層 arm 全負 EV（OHLCV+TA net alpha≈0），
       故正確輸出 = 全 flat。
    3. **demo 撮合 artifact 不可轉移 mainnet**。fill_realism_tier=
       'maker_no_queue_demo_artifact' 的報酬被標記為 transferable=False，
       allocate 預設只信 transferable 報酬（demote artifact arm 到 explore，
       不讓 demo 無排隊 maker 立即成交的虛高 PnL 驅動真實配置）。
    4. **不 fake PnL/fills/lineage**。報酬只接受呼叫端餵入的 realized demo PnL，
       本模組不合成任何正權重。

  注入點（injectable）：RNG（random.Random）與 now_ts 都由呼叫端注入，
  不用 wall-clock，保證單元測試可重現。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover — numpy 在 ml_training env 必裝
    np = None  # type: ignore[assignment]

# bandit 數學 100% reuse thompson_sampling，本模組只做編排層。
from program_code.ml_training.thompson_sampling import (
    NIGPosterior,
    empirical_bayes_init,
    exploitation_floor,
    sample_nig,
    update_posterior,
)

# ---------------------------------------------------------------------------
# 常數 / 列舉值（與既有 schema/arm-space 對齊，避免命名漂移）
# ---------------------------------------------------------------------------

# arm_id 形狀沿用 linucb_trainer.enumerate_v1_15_arm_ids 的 'regime__strategy'。
_ARM_SEP = "__"

# flat / cash stand-down arm 的固定 id。它不是真策略，而是「不配任何真 arm」的選項。
# 為什麼需要：naive Thompson 在所有 arm 皆負 EV 時會持續押「最不爛」的負 arm 緩慢失血；
# 加一個 flat arm + m_post>0 硬閘 + explore 上限，才能讓配置器在負環境下歸零。
FLAT_ARM_ID = "__flat_cash__"

# fill_realism_tier：與 learning.arm_realized_attribution（下一輪新表）CHECK 對齊。
# 'maker_no_queue_demo_artifact' = demo 無 orderbook queue 的 maker 立即成交，
# 真實 mainnet 會排隊/部分不成交，故此 tier 的增益不可轉移。
FILL_TIER_TAKER_REAL = "taker_real"
FILL_TIER_MAKER_QUEUED_REAL = "maker_queued_real"
FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT = "maker_no_queue_demo_artifact"

_VALID_FILL_TIERS = (
    FILL_TIER_TAKER_REAL,
    FILL_TIER_MAKER_QUEUED_REAL,
    FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT,
)

# regime 詞彙與 research.aeg_regime_labels / arm_posterior_history CHECK 對齊（6-enum）。
VALID_REGIMES = (
    "bull",
    "bear",
    "high-vol",
    "chop",
    "range",
    "insufficient_context",
)

# 雙軌 posterior（誠實隔離 demo artifact）：
#   all_fills          = 全部成交（含 demo artifact，樂觀）
#   transferable_only  = 只算可轉移成交（promotion 只信這軌）
TRACK_ALL_FILLS = "all_fills"
TRACK_TRANSFERABLE_ONLY = "transferable_only"


# ---------------------------------------------------------------------------
# 配置（所有閾值/上限的單一來源；絕對 sizing 數字由 risk_config_demo.toml 提供，
# 本模組不寫死任何倉位金額——只持有「無量綱」係數/閾值）
# ---------------------------------------------------------------------------


@dataclass
class AllocatorConfig:
    """配置器所有閾值與上限。

    為什麼集中：避免「歸零閘」「explore 上限」「Kelly 分數」散落硬編碼，
    讓 E2 審查與後續 operator 調參有單一面板。
    """

    # 歸零硬閘：真 arm 的 P(μ>0) 必須 ≥ 此值才有資格被配置；否則該 arm 退出，
    # 全 arm 皆不達標時 100% 配 flat。0.55 = 略高於 50/50，要求「明顯偏正」。
    positive_prob_gate: float = 0.55

    # Monte-Carlo 估 P(μ>0) 的抽樣次數。越大越穩但越慢；2000 在單機毫秒級。
    prob_mc_samples: int = 2000

    # flat-arm 的保守成本下限（bps，負值代表 stand-down 的機會成本上限）。
    # 語意：flat 的「期望報酬」設為 -c_floor，逼真 arm 必須贏過「什麼都不做且付
    # 保守成本」才會被配。預設由呼叫端用 risk_config_demo.toml [slippage] 推算後注入；
    # 此處只放一個保守內建值（5 bps fallback rate ≈ default_rate=0.0005）。
    flat_arm_cost_floor_bps: float = 5.0

    # 每 arm explore 上限：n_trials < explore_budget 時，該 arm 仍在「探索期」，
    # 配置以 exploitation_floor 退化為經驗均值而非純抽樣（防早期噪音驅動）。
    explore_budget: int = 30

    # 遺忘因子（非平穩性）：每次 ingest 對舊充分統計量做指數衰減。
    # 0.99 = 慢衰減（spec 預設，需 validation；太小燒成本、太大跟不上 regime 轉折）。
    forgetting_gamma: float = 0.99

    # dormant 自動清除：arm 連續 dormant_clear_after 個 tick 沒新報酬，
    # 後驗回退到 prior（避免過期統計量永久把 arm 釘在某狀態）。
    dormant_clear_after_ticks: int = 1440

    # fractional-Kelly 上限（鏡像 kelly_sizer.rs 的 max_fraction=0.25）。
    # 本模組只回 sizing 係數上限，不算 qty。
    kelly_max_fraction: float = 0.25
    # 分級 Kelly 分數（與 risk_config_demo.toml [kelly] 對齊）。
    kelly_young_fraction: float = 0.125
    kelly_mature_fraction: float = 0.16666666666666666
    kelly_established_fraction: float = 0.25
    kelly_young_threshold: int = 50
    kelly_mature_threshold: int = 200

    # arm-space 版本標籤（與下一輪 posterior 表的 realism_track 一起構成主鍵維度）。
    arm_space_version: str = "alloc_v1"

    # 預設只信可轉移軌（promotion 鐵則）；設 False 才把 demo artifact 也納入配置。
    trust_track: str = TRACK_TRANSFERABLE_ONLY


# ---------------------------------------------------------------------------
# 純資料載體
# ---------------------------------------------------------------------------


@dataclass
class ArmReward:
    """單筆 round-trip 已實現報酬（呼叫端餵入，本模組不合成）。"""

    arm_id: str
    regime: str
    realized_pnl_bps: float
    ts: float  # 注入的時間戳（單調即可，不要求 wall-clock）
    fill_realism_tier: str = FILL_TIER_TAKER_REAL

    @property
    def transferable(self) -> bool:
        """是否可轉移 mainnet：demo 無排隊 maker artifact 不可轉移。"""
        return self.fill_realism_tier != FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT


@dataclass
class ArmState:
    """每 (arm_id, track) 的後驗狀態 + 探索/dormant 記帳。"""

    arm_id: str
    track: str
    posterior: NIGPosterior = field(default_factory=NIGPosterior)
    last_update_ts: float = 0.0
    # demote 旗標：只要曾被 artifact 報酬污染就標記（誠實審計）。
    saw_artifact: bool = False


# ---------------------------------------------------------------------------
# Monte-Carlo P(μ>0)：歸零硬閘的輸入
# ---------------------------------------------------------------------------


def prob_mu_positive(
    posterior: NIGPosterior,
    n_samples: int,
    rng: Optional[random.Random] = None,
) -> float:
    """估計 P(μ>0)：從 NIG 後驗抽 n_samples 個 μ，算正比例。

    為什麼用抽樣而非閉式 Student-t CDF：sample_nig 已是既有、已測的抽樣路徑，
    複用它避免引入第二套數學（漂移風險）。n_samples 大時誤差 ~1/sqrt(n)。
    """
    if n_samples <= 0:
        return 0.0
    pos = 0
    for _ in range(n_samples):
        if sample_nig(posterior, rng=rng) > 0.0:
            pos += 1
    return pos / n_samples


# ---------------------------------------------------------------------------
# fractional-Kelly 上限係數（鏡像 kelly_sizer.rs 分級，不算 qty）
# ---------------------------------------------------------------------------


def fractional_kelly_cap(n_trials: int, cfg: AllocatorConfig) -> float:
    """回傳該 arm 的 fractional-Kelly 上限係數（0~max_fraction）。

    鏡像 Rust kelly_sizer.rs:241-250 的分級邏輯：
      n < young_threshold     → young_fraction（最保守 1/8）
      n < mature_threshold    → mature_fraction（1/6）
      n >= mature_threshold   → established_fraction（1/4）
    再夾在 max_fraction。**本模組只回係數，真 qty 由 Rust 權威計算**——
    這樣 allocator 不重複 sizing 邏輯，也不會誤成第二個下單權威。
    """
    if n_trials < cfg.kelly_young_threshold:
        frac = cfg.kelly_young_fraction
    elif n_trials < cfg.kelly_mature_threshold:
        frac = cfg.kelly_mature_fraction
    else:
        frac = cfg.kelly_established_fraction
    return min(frac, cfg.kelly_max_fraction)


# ---------------------------------------------------------------------------
# 核心配置器
# ---------------------------------------------------------------------------


class RegimeBanditAllocator:
    """Regime 條件化 Thompson-sampling 配置器（核心，未接引擎）。

    狀態：每 (track, arm_id) 一個 ArmState。track 雙軌隔離 demo artifact。
    本類**不**做任何 IO；所有時間/隨機由呼叫端注入，便於單元測試重現。
    """

    def __init__(self, cfg: Optional[AllocatorConfig] = None):
        self.cfg = cfg or AllocatorConfig()
        # 巢狀 dict：track → arm_id → ArmState
        self._states: dict[str, dict[str, ArmState]] = {
            TRACK_ALL_FILLS: {},
            TRACK_TRANSFERABLE_ONLY: {},
        }

    # ---- 寫入路徑 ---------------------------------------------------------

    def _get_or_init_state(self, track: str, arm_id: str) -> ArmState:
        bucket = self._states.setdefault(track, {})
        st = bucket.get(arm_id)
        if st is None:
            st = ArmState(arm_id=arm_id, track=track)
            bucket[arm_id] = st
        return st

    def ingest_arm_outcome(
        self,
        arm_id: str,
        regime: str,
        realized_pnl_bps: float,
        ts: float,
        fill_realism_tier: str = FILL_TIER_TAKER_REAL,
    ) -> None:
        """吸收一筆 round-trip 已實現報酬，更新對應軌的後驗。

        雙軌規則（誠實隔離）：
          - all_fills 軌：永遠吸收（含 demo artifact）。
          - transferable_only 軌：只在 transferable=True 時吸收；artifact 不入軌，
            但會在 all_fills 軌的 ArmState 標 saw_artifact=True 作審計。

        非平穩處理：吸收前對舊後驗做 forgetting_gamma 指數衰減（見 _decay_posterior）。
        """
        if fill_realism_tier not in _VALID_FILL_TIERS:
            raise ValueError(f"invalid fill_realism_tier: {fill_realism_tier!r}")
        if regime not in VALID_REGIMES:
            raise ValueError(f"invalid regime: {regime!r}")

        reward = ArmReward(
            arm_id=arm_id,
            regime=regime,
            realized_pnl_bps=float(realized_pnl_bps),
            ts=float(ts),
            fill_realism_tier=fill_realism_tier,
        )

        # all_fills 軌：永遠吸收。
        st_all = self._get_or_init_state(TRACK_ALL_FILLS, arm_id)
        if not reward.transferable:
            st_all.saw_artifact = True
        self._apply_reward(st_all, reward)

        # transferable_only 軌：只吸收可轉移成交。
        if reward.transferable:
            st_tr = self._get_or_init_state(TRACK_TRANSFERABLE_ONLY, arm_id)
            self._apply_reward(st_tr, reward)

    def _apply_reward(self, st: ArmState, reward: ArmReward) -> None:
        """對單一 ArmState 套用遺忘衰減 + 共軛更新。"""
        # 非平穩：先衰減舊充分統計量（dormant 越久衰減越多），再吃新觀測。
        st.posterior = self._decay_posterior(st.posterior, st.last_update_ts, reward.ts)
        st.posterior = update_posterior(st.posterior, reward.realized_pnl_bps)
        st.last_update_ts = reward.ts

    def _decay_posterior(
        self,
        post: NIGPosterior,
        last_ts: float,
        now_ts: float,
    ) -> NIGPosterior:
        """指數遺忘：把 NIG 的「樣本量」維度（lam、alpha、beta 的累積部分）
        向 prior 收縮，讓舊資料權重隨時間衰減。

        為什麼：regime 非平穩，舊 regime 的充分統計量不該永久主導。
        gamma=1.0 等於不衰減（可關閉）。last_ts<=0 表首筆，不衰減。
        n_trials 也按比例縮（保持與 lam 的近似一致，供 explore 判斷）。
        """
        gamma = self.cfg.forgetting_gamma
        if gamma >= 1.0 or last_ts <= 0.0 or now_ts <= last_ts:
            return post

        prior = NIGPosterior()  # dataclass 預設 = 我們的收縮目標

        # 簡化模型：每「步」衰減一次 gamma（步=一筆 ingest 間隔，這裡用 1 步），
        # 把超出 prior 的累積量乘 gamma。這是保守、確定性的衰減，不用 wall-clock。
        def _shrink(cur: float, base: float) -> float:
            return base + (cur - base) * gamma

        decayed = NIGPosterior(
            mu=post.mu,  # μ 本身不衰減（值不變），只衰減其「確定性/樣本量」
            lam=_shrink(post.lam, prior.lam),
            alpha=_shrink(post.alpha, prior.alpha),
            beta=_shrink(post.beta, prior.beta),
            n_trials=int(round(_shrink(float(post.n_trials), 0.0))),
        )
        return decayed

    def warm_start_from_returns(
        self,
        arm_id: str,
        returns: list[float],
        track: str = TRACK_TRANSFERABLE_ONLY,
    ) -> None:
        """用一批歷史報酬 empirical-bayes 初始化某 arm 的後驗（cold-start）。

        reuse thompson_sampling.empirical_bayes_init。供呼叫端在進入線上更新前，
        以離線批次 warm-start；不接 DB，returns 由呼叫端提供。
        """
        st = self._get_or_init_state(track, arm_id)
        st.posterior = empirical_bayes_init(returns)

    # ---- 讀取路徑 ---------------------------------------------------------

    def _flat_posterior(self) -> NIGPosterior:
        """flat-arm 的後驗：μ = -cost_floor（保守 stand-down 成本）。

        為什麼 μ 設負：flat 代表「不做且付保守成本」，真 arm 要被配就必須在抽樣中
        贏過這個負基準。lam/alpha/beta 用較大值表示「對 flat 成本很有把握」，
        讓 flat 的抽樣方差小、不會被噪音抬高。
        """
        return NIGPosterior(
            mu=-abs(self.cfg.flat_arm_cost_floor_bps),
            lam=1e6,      # 極高精度 = flat 報酬幾乎確定 = 抽樣方差極小
            alpha=1e6,
            beta=1.0,
            n_trials=10**9,
        )

    def allocate(
        self,
        regime: str,
        candidate_arms: list[str],
        rng: Optional[random.Random] = None,
        track: Optional[str] = None,
    ) -> dict[str, float]:
        """核心：對 regime 下的候選 arm 做 Thompson 配置，回權重 dict（含 flat）。

        流程：
          1. 取 trust track（預設 transferable_only）的後驗；缺者用 prior（cold）。
          2. 對每個真 arm 估 P(μ>0)；< positive_prob_gate 的 arm 直接出局（歸零閘）。
          3. 合格 arm + flat-arm 一起跑 Monte-Carlo posterior-prob 權重：
             多輪抽樣，每輪 argmax 的 arm 計一票，票數正規化為權重。
          4. 若無任何真 arm 合格 → flat 權重 = 1.0（學會歸零）。

        回傳：{arm_id: weight}，∑weight=1，必含 FLAT_ARM_ID。
        所有真 arm 權重 ≥ 0；當前負 EV 環境的正確輸出 = {FLAT_ARM_ID: 1.0}。
        """
        if regime not in VALID_REGIMES:
            raise ValueError(f"invalid regime: {regime!r}")
        use_track = track or self.cfg.trust_track
        bucket = self._states.get(use_track, {})

        # 步驟 1-2：收集合格真 arm 的後驗（過歸零閘）。
        qualified: dict[str, NIGPosterior] = {}
        for arm_id in candidate_arms:
            if arm_id == FLAT_ARM_ID:
                continue  # flat 不在候選裡重複
            st = bucket.get(arm_id)
            post = st.posterior if st is not None else NIGPosterior()
            p_pos = prob_mu_positive(post, self.cfg.prob_mc_samples, rng=rng)
            if p_pos >= self.cfg.positive_prob_gate:
                qualified[arm_id] = post

        # 步驟 4：無合格真 arm → 全歸 flat（誠實歸零）。
        if not qualified:
            return {FLAT_ARM_ID: 1.0}

        # 步驟 3：合格 arm + flat 一起 Monte-Carlo posterior-prob 權重。
        arms_for_mc: dict[str, NIGPosterior] = dict(qualified)
        arms_for_mc[FLAT_ARM_ID] = self._flat_posterior()

        # exploitation floor：合格 arm 總樣本太少時，退化為「按經驗均值 argmax」
        # 的確定性配置（防早期純探索把權重亂撒）。
        if exploitation_floor(qualified, floor_trials=self.cfg.explore_budget):
            best = max(arms_for_mc, key=lambda k: arms_for_mc[k].mu)
            weights = {a: 0.0 for a in arms_for_mc}
            weights[best] = 1.0
            return weights

        return self._monte_carlo_weights(arms_for_mc, rng=rng)

    def _monte_carlo_weights(
        self,
        posteriors: dict[str, NIGPosterior],
        rng: Optional[random.Random] = None,
    ) -> dict[str, float]:
        """Monte-Carlo posterior-prob 權重：多輪抽樣，每輪贏家計票，正規化。

        這等價於「Thompson 配置權重 = P(該 arm 在抽樣中為最佳)」，是把單步
        Thompson 選擇平滑成連續權重的標準做法。
        """
        n = self.cfg.prob_mc_samples
        votes = {a: 0 for a in posteriors}
        for _ in range(n):
            best_a = None
            best_v = -math.inf
            for a, post in posteriors.items():
                v = sample_nig(post, rng=rng)
                if v > best_v:
                    best_v = v
                    best_a = a
            if best_a is not None:
                votes[best_a] += 1
        total = sum(votes.values()) or 1
        return {a: votes[a] / total for a in posteriors}

    # ---- 探索/dormant 維護 ------------------------------------------------

    def explore_budget_remaining(self, arm_id: str, track: Optional[str] = None) -> int:
        """回該 arm 還剩多少探索額度（explore_budget - n_trials，下限 0）。"""
        use_track = track or self.cfg.trust_track
        st = self._states.get(use_track, {}).get(arm_id)
        n = st.posterior.n_trials if st is not None else 0
        return max(0, self.cfg.explore_budget - n)

    def clear_dormant(self, now_ts: float, track: Optional[str] = None) -> list[str]:
        """把 dormant 過久的 arm 後驗清回 prior，回被清的 arm_id 列表。

        為什麼：過期充分統計量會把 arm 永久釘在某狀態（first-detection deadlock
        反模式）。dormant_clear_after_ticks 用「上次更新 ts 距 now 的差」判斷；
        ts 是注入的單調量，不用 wall-clock。
        """
        use_track = track or self.cfg.trust_track
        cleared: list[str] = []
        bucket = self._states.get(use_track, {})
        threshold = self.cfg.dormant_clear_after_ticks
        for arm_id, st in bucket.items():
            if st.last_update_ts <= 0.0:
                continue
            if (now_ts - st.last_update_ts) >= threshold:
                st.posterior = NIGPosterior()
                cleared.append(arm_id)
        return cleared

    # ---- 內省 / 審計 ------------------------------------------------------

    def arm_diagnostics(
        self,
        arm_id: str,
        rng: Optional[random.Random] = None,
        track: Optional[str] = None,
    ) -> dict:
        """回某 arm 的診斷快照（供審計/shadow 輸出；不影響配置）。"""
        use_track = track or self.cfg.trust_track
        st = self._states.get(use_track, {}).get(arm_id)
        post = st.posterior if st is not None else NIGPosterior()
        return {
            "arm_id": arm_id,
            "track": use_track,
            "mu": post.mu,
            "n_trials": post.n_trials,
            "prob_mu_positive": prob_mu_positive(
                post, self.cfg.prob_mc_samples, rng=rng
            ),
            "fractional_kelly_cap": fractional_kelly_cap(post.n_trials, self.cfg),
            "explore_budget_remaining": self.explore_budget_remaining(
                arm_id, track=use_track
            ),
            "saw_artifact": (
                self._states.get(TRACK_ALL_FILLS, {}).get(arm_id).saw_artifact
                if self._states.get(TRACK_ALL_FILLS, {}).get(arm_id) is not None
                else False
            ),
        }


# ---------------------------------------------------------------------------
# arm_id 工具（與 linucb arm-space 對齊）
# ---------------------------------------------------------------------------


def make_arm_id(regime: str, strategy: str) -> str:
    """構建 'regime__strategy' arm_id（鏡像 linucb enumerate_v1_15_arm_ids）。"""
    return f"{regime}{_ARM_SEP}{strategy}"


def parse_arm_id(arm_id: str) -> tuple[str, str]:
    """解析 'regime__strategy'；flat-arm 回 ('', flat) 不報錯。"""
    if arm_id == FLAT_ARM_ID:
        return ("", FLAT_ARM_ID)
    parts = arm_id.split(_ARM_SEP)
    if len(parts) != 2:
        raise ValueError(f"arm_id must be 'regime__strategy', got: {arm_id!r}")
    return parts[0], parts[1]
