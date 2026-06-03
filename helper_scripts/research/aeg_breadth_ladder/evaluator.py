"""AEG-S2 breadth ladder — CandidateEvaluator protocol + TierResult schema + adapter。

MODULE_NOTE:
  模塊用途：定義 breadth ladder 的 candidate-agnostic 輸入契約（``TierResult`` +
    ``CandidateEvaluator`` protocol），並提供一個 **multiday reference adapter**
    （包既有 multiday_trend_diagnostic 候選 harness 為 per-tier evaluate），證明
    protocol 可被既有候選滿足。
  主要類/函數：
    - ``TierResult``：候選評估器 → breadth runner 的凍結契約（per-tier 結果）。
    - ``CandidateEvaluator``：窄 protocol（``evaluate(tier, universe, alive_mask)``）。
    - ``MultidayTrendReferenceEvaluator``：reference adapter（OQ-B2；真資料端到端驗證
      用，trend 候選已 universe-parametrized + 已知 NO-GO，正好驗 breadth 能正確顯示
      narrowness / 非單調）。
    - ``StubEvaluator``：測試用固定 TierResult 注入器（candidate-agnostic 驗證）。
  硬邊界（PA §3 + §4 leak-free）：
    - candidate-agnostic：(b) 不內嵌任一候選信號/PnL；具體候選由 caller 注入。
    - **n_independent 是 time-cluster-bound NOT symbol-scaled**：adapter 計算
      n_independent 時用 time-period count 取 min（PA §4 Step 3-4），**不沿用** multiday
      ``eff_n = pooled_flips × cluster_factor``（symbol-contaminated）。
    - survivorship 繼承（★ HIGH-1）：adapter 把候選 panel.survivorship（listed_at 下界）
      與 FND-2 ``alive_mask``（含 alive_to delist 上界）**取交集**後才餵 PnL，候選只在
      [alive_from, alive_to] 內持倉（delist 後 0 持倉 / 0 PnL）；(b) 0 自寫 listed_at 查詢。
      adapter 經 ``survivorship_mask_applied`` 自證確有套 mask（summary 由此推導
      ``survivorship_inherited_from_fnd2``，非寫死 True）。
    - read-only：adapter 委派候選 harness 既有 ``set_session(readonly=True)`` loader。
  依賴：標準庫 + numpy（adapter 計算）；multiday 候選 harness（adapter 內延遲 import，
    research/ sys.path 由 conftest 或 harness 自補）。import-time 零 DB 依賴。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass
class TierResult:
    """候選評估器 → breadth runner 的契約（per-tier 結果，凍結 schema，PA §3.2）。

    為什麼把 breadth 與 n_independent 分開兩欄：S0 §2.9 + cost-wall 實證——同 rebalance
    的 symbols 是 **breadth** 非 independent time draws；加寬 breadth 增
    ``breadth_symbol_count`` 但 ``n_independent`` 須 time-cluster-bound（不隨 symbol 漲）。
    """

    tier: str                          # 凍結 tier 名（= breadth_cohort 軸）
    breadth_symbol_count: int          # 該 tier 入選 symbol 數（加寬軸；含 delisted）
    seen_delisted_count: int           # 該 tier 含 delisted symbol 數（healthcheck 用）

    # 候選評估器產出（per-tier，已 PIT-mask + leak-free）：
    net_bps: Optional[float] = None        # per-trade/per-period net edge（bps）
    gross_bps: Optional[float] = None
    cost_bps: Optional[float] = None
    net_to_cost_ratio: Optional[float] = None
    is_sharpe: Optional[float] = None      # annualized
    oos_sharpe: Optional[float] = None     # 若候選提供 walk-forward；否則 None

    # 顯著性原料（★ time-cluster-aware，breadth≠n_independent）：
    n_independent: int = 0                  # time-cluster-bound（NOT symbol-scaled）
    sample_unit: str = "unspecified"        # 'non_overlapping_holding_window' / ...
    t_stat_hac: Optional[float] = None      # overlap-corrected HAC t
    psr_0: Optional[float] = None
    dsr_k: Optional[float] = None
    pbo: Optional[float] = None
    k_trials: Optional[int] = None

    # per-leg（候選若 market-neutral，沿用 funding_tilt per-leg 哲學防單邊偽裝）：
    long_leg_net_bps: Optional[float] = None
    short_leg_net_bps: Optional[float] = None

    # PIT / leak 自證：
    pit_mask_source: str = "fnd2_alive_from_alive_to"  # 繼承證據
    leak_free_signal: bool = False          # 候選自證 leak-free（leak-free vs naive 已驗）
    # survivorship 繼承自證（★ 破 tautology，re-E2 HIGH-1）：候選評估器是否**真的**
    # 把 FND-2 ``alive_mask`` 的 ``[alive_from, alive_to]`` 套上 PnL（含 delist 上界），
    # 而非只跑在 listed_at-only 的 panel.survivorship（會多算 delist 後死 symbol 的 PnL）。
    # summary 由此欄聚合推導 ``survivorship_inherited_from_fnd2``，**不寫死 True**：漏用
    # alive_mask / 漏 alive_to 上界的 adapter 必回 False（或保留 None）→ healthcheck FAIL。
    survivorship_mask_applied: Optional[bool] = None
    notes: dict = field(default_factory=dict)


@runtime_checkable
class CandidateEvaluator(Protocol):
    """breadth ladder 的候選注入邊界（窄 protocol，PA §3.2）。

    candidate_id：候選識別字（進 ladder_id digest + artifact）。
    evaluate：給定 tier + universe symbol-set + alive_mask（FND-2 繼承）→ TierResult。
      alive_mask = {symbol: (alive_from_utc, alive_to_utc)}（候選只在窗內持倉，MIT b.2）。
    """

    candidate_id: str

    def evaluate(self, *, tier: str, universe: tuple, alive_mask: dict) -> TierResult:
        ...


# ───────────────────────── multiday reference adapter（OQ-B2）─────────────────────────

# multiday TSMOM 顯著性檢定的 k 集合（沿用 multiday TSMOM_SCALE_KS；reference adapter
# 用單一代表 k 算 per-tier net edge / time-cluster n_independent）。
_REFERENCE_TSMOM_K = 30


class MultidayTrendReferenceEvaluator:
    """multiday trend 候選的 reference adapter（端到端真資料驗證用，OQ-B2）。

    為什麼選 multiday 作 reference：PM 裁決——trend 候選 panel 真資料 + 已知 NO-GO，
    正好驗 breadth 能正確顯示 narrowness / 非單調；且 multiday 已 universe-parametrized
    （``run_diagnostic(panel, universe)`` / ``tsmom_significance(close, surv, k)`` 已吃
    universe），adapter 只需用 tier symbol-set 各呼一次。

    n_independent 計算（PA §4 Step 3-4，candidate-agnostic 主軸的 time-cluster 化）：
      multi-day time-series 候選 → ``n_independent = non-overlapping holding-period
      windows 數``，與 symbol 數無關（受窗長/holding k 決定）。對固定窗，core25 與 full
      的 n_independent **相同**（時間軸一致，只 symbol 數不同）→ 這正是 breadth≠
      n_independent 的機械保證。**不沿用** multiday ``eff_n = pooled_flips ×
      cluster_factor``（pooled_flips 隨 symbol 漲，是 breadth-contaminated）。

    本 adapter read-only：用 multiday data_loader（``set_session(readonly=True)``）載
    panel 一次，per-tier 只切 universe 子集重算（不重連 PG）。
    """

    candidate_id = "multiday_trend_reference"

    def __init__(self, panel, *, k: int = _REFERENCE_TSMOM_K):
        """panel = multiday data_loader.Panel（caller 一次載入，per-tier 共用）。"""
        self._panel = panel
        self._k = k

    def evaluate(self, *, tier: str, universe: tuple, alive_mask: dict) -> TierResult:
        """對單一 tier 的 universe 算 per-tier TierResult（leak-free TSMOM signed-fwd）。"""
        import numpy as np  # 延遲 import
        from multiday_trend_diagnostic import stats  # research/ sys.path 由 caller 補

        panel = self._panel
        k = self._k
        # 只取 tier ∩ panel 有 close 的 symbol（panel 可能未覆蓋全 FND-2 universe）。
        tier_syms = tuple(s for s in universe if s in panel.close)
        close_by_symbol = {s: panel.close[s] for s in tier_syms}
        # ★ HIGH-1：survivorship 必須是 panel.survivorship（listed_at 下界）∩ FND-2
        # alive_mask（含 alive_to delist 上界）。只用 panel.survivorship 會多算 delist 後
        # 死 symbol（如 DEADUSDT）的 PnL（panel 只有 listed_at 下界、無上界）。交集後
        # delist 後的 bar surv=False → tsmom_significance 跳過 → 該 symbol delist 後持倉=0。
        surv_by_symbol = self._clamped_survivorship(tier_syms, alive_mask, panel)
        # adapter **真的**套了 alive_mask 的 [alive_from, alive_to] → 自證繼承（非寫死）。
        mask_applied = self._mask_was_applied(tier_syms, alive_mask)

        breadth_count = len(tier_syms)
        # delist-after-clip：tier 內 alive_to 早於 panel 末日（窗內真 delist）的 symbol 數
        # （★ 真用 alive_mask 數，非佔位 0）。供 notes 佐證 + 自證 mask 確有 delist 上界。
        delisted_clipped = self._count_seen_delisted(tier_syms, alive_mask, panel)

        # leak-free TSMOM signed-forward 顯著性（time-cluster-aware：n_eff_non_overlapping
        # = n_obs / k 是 holding-period overlap 校正後的非重疊有效樣本；time-bound）。
        tsmom = stats.tsmom_significance(close_by_symbol, surv_by_symbol, k)
        if tsmom is None or tsmom.get("insufficient"):
            return TierResult(
                tier=tier,
                breadth_symbol_count=breadth_count,
                seen_delisted_count=0,  # artifact 權威值由 ladder 層覆寫（見 MODULE_NOTE）
                n_independent=0,
                sample_unit="non_overlapping_holding_window",
                pit_mask_source="fnd2_alive_from_alive_to",
                leak_free_signal=True,
                survivorship_mask_applied=mask_applied,
                notes={"reason": "insufficient_observations_at_scale", "k": k,
                       "n_obs": (tsmom or {}).get("n_obs", 0),
                       "delisted_clipped_count": delisted_clipped},
            )

        # n_independent = time-cluster-bound：non-overlapping holding-period windows。
        # 為什麼用 distinct-date 範圍 / k 而非 n_obs/k：n_obs pools 跨 symbol（symbol 多
        # 則 n_obs 大），會 breadth-contaminate；time-period count 只看時間軸跨度（per
        # symbol 可用日數 / k 的 cross-symbol 上確界），對固定窗 core25≈full（PA §4）。
        n_independent = self._time_cluster_n_independent(close_by_symbol, surv_by_symbol, k)

        mean_signed_bps = tsmom.get("mean_signed_fwd_bps")
        long_bps = tsmom.get("mean_long_fwd_bps")
        short_bps = tsmom.get("mean_short_fwd_bps")
        # net edge 用代表性 round-turn 成本扣（沿用 multiday cost_model 哲學的保守 taker）。
        from multiday_trend_diagnostic import cost_model
        rt_cost_bps = cost_model.TAKER_FEE_BPS_PER_SIDE * 2.0
        gross_bps = mean_signed_bps
        net_bps = (gross_bps - rt_cost_bps) if gross_bps is not None else None
        ncr = None
        if net_bps is not None and rt_cost_bps > 0:
            ncr = net_bps / rt_cost_bps

        return TierResult(
            tier=tier,
            breadth_symbol_count=breadth_count,
            seen_delisted_count=0,   # artifact 權威值由 ladder 層覆寫（見 MODULE_NOTE）
            net_bps=round(net_bps, 4) if net_bps is not None else None,
            gross_bps=round(gross_bps, 4) if gross_bps is not None else None,
            cost_bps=round(rt_cost_bps, 4),
            net_to_cost_ratio=round(ncr, 4) if ncr is not None else None,
            is_sharpe=None,          # multiday TSMOM 檢定不直接產 per-tier annualized Sharpe
            oos_sharpe=None,         # 無 walk-forward（OQ-B4：(b) 不強制候選做 OOS）
            n_independent=n_independent,
            sample_unit="non_overlapping_holding_window",
            t_stat_hac=tsmom.get("t_stat_hac"),
            long_leg_net_bps=(round(long_bps - rt_cost_bps, 4)
                              if long_bps is not None else None),
            short_leg_net_bps=(round(short_bps - rt_cost_bps, 4)
                               if short_bps is not None else None),
            pit_mask_source="fnd2_alive_from_alive_to",
            leak_free_signal=True,   # tsmom_significance 用 C_{t-1} lookback（leak-free）
            survivorship_mask_applied=mask_applied,
            notes={
                "k": k,
                "n_obs_pooled": tsmom.get("n_obs"),
                "n_eff_non_overlapping_pooled": tsmom.get("n_eff_non_overlapping"),
                "hit_rate": tsmom.get("hit_rate"),
                "significant_positive_momentum": tsmom.get("significant_positive_momentum"),
                "delisted_clipped_count": delisted_clipped,
            },
        )

    @staticmethod
    def _time_cluster_n_independent(close_by_symbol: dict, surv_by_symbol: dict, k: int) -> int:
        """time-cluster-bound n_independent（PA §4 Step 4：time-period count，NOT symbol-scaled）。

        定義：non-overlapping holding-period windows 數 = (最大可用 PIT 交易日跨度) / k。
        為什麼取 cross-symbol 最大可用跨度（而非 pooled n_obs）：對固定分析窗，breadth
        加寬只增 symbol 數，**不增時間軸**；time-period count 只受窗長/holding k 決定，
        故 core25 與 full 應得相同 n_independent（這是 breadth≠n_independent 的機械保證，
        T-breadth-not-nindep bite test）。不重疊：除以 holding k（前瞻 k 日視窗不重疊）。

        impl-spec 偏離記錄（re-E2 MED；對齊 PA §4 字面 ``window/k``）：
          spec 字面是「分析窗長 / k」；本實作用「**單 symbol 最長可用 tradable days** // k」
          （cross-symbol 上確界），而非整段分析窗長。為什麼 production-safe：core25 成員是
          最老 / 最 liquid 的 perp，其單 symbol 可用史已是 universe 內最長者；更寬 tier
          只會引入**更短或等長**史的 symbol（晚上市 / 中途 delist），不會引入更長史 →
          max_tradable_days 不因 breadth 加寬而漲 → n_independent 仍 breadth-invariant。
          取最長（而非分析窗名目長）反而更保守地反映「最佳 symbol 實際有多少不重疊窗」，
          不會因某 symbol 史短而虛報整窗樣本。
          注意：promotion 端更嚴的 effective-N（跨 symbol 共用時間軸的真有效獨立窗數、
          cross-sectional 收縮）屬 (c) / QC scope，非本 (b) 診斷層職責。
        """
        import numpy as np  # 延遲 import
        max_tradable_days = 0
        for s, close in close_by_symbol.items():
            c = np.asarray(close, dtype=float)
            finite = np.isfinite(c) & (c > 0)
            surv = surv_by_symbol.get(s)
            if surv is not None:
                surv = np.asarray(surv, dtype=bool)
                finite = finite & surv
            days = int(np.count_nonzero(finite))
            if days > max_tradable_days:
                max_tradable_days = days
        if max_tradable_days < 2 * k:
            return 0
        # entry 需 C_{t-1-k} 與 C_{t+k}，每個 holding window 跨 ~k 日不重疊。
        return max(0, max_tradable_days // k)

    @staticmethod
    def _alive_window_dates(alive_mask: dict, symbol: str) -> tuple:
        """取 symbol 的 alive_mask 窗（轉成 date 上下界）。回 ``(alive_from_date, alive_to_date)``。

        alive_from/alive_to 為 tz-aware UTC datetime（或 None=無界）。轉成 date 以對齊
        panel.dates（datetime.date）。None → None（該側不設界）。
        """
        af, at = alive_mask.get(symbol, (None, None))
        af_d = af.date() if af is not None else None
        at_d = at.date() if at is not None else None
        return af_d, at_d

    @classmethod
    def _clamped_survivorship(cls, tier_syms: tuple, alive_mask: dict, panel) -> dict:
        """survivorship = panel.survivorship（listed_at 下界）∩ alive_mask [alive_from, alive_to]。

        為什麼交集（★ HIGH-1）：panel.survivorship 只有 listed_at 下界、**無 delist 上界**
        （data_loader 只查 listed_at）；FND-2 alive_mask 帶 alive_to delist 上界。交集後
        delist 後的 bar surv=False，候選只在 [alive_from, alive_to] 內持倉（delist 後 0
        持倉 / 0 PnL 貢獻，MIT b.2）。symbol 不在 alive_mask（無界）→ 退回 panel 原值
        （保守，不擴大持倉窗）。
        """
        import numpy as np  # 延遲 import
        out: dict = {}
        dates = panel.dates
        for s in tier_syms:
            base = panel.survivorship.get(s)
            if base is None:
                continue
            surv = np.asarray(base, dtype=bool).copy()
            af_d, at_d = cls._alive_window_dates(alive_mask, s)
            if af_d is None and at_d is None:
                out[s] = surv  # 無 alive_mask 界 → 退回 panel 原值（不擴大窗）
                continue
            # 套上下界：alive_from 前 / alive_to 後的 bar 視為未存活（surv=False）。
            for i, d in enumerate(dates):
                if af_d is not None and d < af_d:
                    surv[i] = False
                if at_d is not None and d > at_d:
                    surv[i] = False
            out[s] = surv
        return out

    @classmethod
    def _mask_was_applied(cls, tier_syms: tuple, alive_mask: dict):
        """adapter 是否**真的**對此 tier 套了 FND-2 alive_mask（自證繼承，破 tautology）。

        回 ``Optional[bool]``（summary 端聚合時只看非 None 的已評估 tier）：
          - 空 tier（如 scanner overlap 常為空）→ **None**：無 symbol 可套 mask，非繼承
            訊號（不該拖累整體繼承判定）。
          - 非空 tier 但 alive_mask 無此 tier 任一 symbol → **False**：mask 缺、adapter
            無從繼承（誠實標記，不偽造 True）→ 拉低整體判定。
          - 非空 tier 且 alive_mask 至少有一 symbol 條目 → **True**：``_clamped_survivorship``
            會據此 clip（含 alive_to delist 上界）→ 真的繼承。
        為什麼不要求每個 symbol 都有界：core25 等 tier 可能含 alive_to=None（仍上市）的
        symbol，但只要 mask 有提供條目、adapter 有據此 clip，即屬「真的繼承」。
        """
        if not tier_syms:
            return None
        return any(s in alive_mask for s in tier_syms)

    @classmethod
    def _count_seen_delisted(cls, tier_syms: tuple, alive_mask: dict, panel) -> int:
        """tier 內**真 delist-after-clip** 的 symbol 數（★ 真用 alive_mask 數，非佔位 0）。

        定義：symbol 在 alive_mask 有 alive_to 上界、且該上界**早於 panel 末交易日**
        → 代表此 symbol 在分析窗內真的下市（其 survivorship 被 alive_to clip 掉一段）。
        為什麼這樣數：driver 是「mask 的 delist 上界確實對某 symbol 生效」的機械證據，與
        artifact 的 seen_delisted flag 互補（seen_delisted_count 仍由 ladder 層用 artifact
        權威值覆寫；本數值入 notes 佐證 mask 真有 delist 上界、非佔位）。
        """
        dates = panel.dates
        if not dates:
            return 0
        last_date = dates[-1]
        count = 0
        for s in tier_syms:
            _af_d, at_d = cls._alive_window_dates(alive_mask, s)
            if at_d is not None and at_d < last_date:
                count += 1
        return count


class StubEvaluator:
    """測試用固定 TierResult 注入器（candidate-agnostic 驗證 + ladder 純函數測）。

    為什麼需要：ladder/monotonicity 純函數測不應依賴真 PG / 真候選；StubEvaluator 讓
    測試直接餵已知 per-tier 數值（T-monotonic-* / T-breadth-not-nindep / T-determinism）。
    """

    def __init__(self, candidate_id: str, results_by_tier: dict):
        self.candidate_id = candidate_id
        self._results = results_by_tier

    def evaluate(self, *, tier: str, universe: tuple, alive_mask: dict) -> TierResult:
        base = self._results.get(tier)
        if base is None:
            # 無預設 result → 誠實標記未套 mask（survivorship_mask_applied=None），
            # 讓 summary 推導 survivorship_inherited_from_fnd2=False（非偽造 True）。
            return TierResult(
                tier=tier, breadth_symbol_count=len(universe), seen_delisted_count=0,
                n_independent=0, sample_unit="stub_no_result",
            )
        # 回 copy 並把 breadth_symbol_count 對齊實際 universe 大小（除非 stub 已指定）。
        from dataclasses import replace
        if base.breadth_symbol_count == 0:
            base = replace(base, breadth_symbol_count=len(universe))
        return base


__all__ = [
    "TierResult",
    "CandidateEvaluator",
    "MultidayTrendReferenceEvaluator",
    "StubEvaluator",
]
