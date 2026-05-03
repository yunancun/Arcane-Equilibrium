"""
fee_execution_calibrator — REF-20 Wave 5 P3a-Q5 Bybit fee model + execution split.
Bybit 手續費模型 + 執行類型分布估計 — REF-20 Wave 5 P3a-Q5。

MODULE_NOTE (EN): Estimates per-fill / per-trade fee in bps using Bybit V5
  USDT linear perpetual fee schedule with VIP-tier override. Estimates
  maker/taker execution split from `liquidity_role` column on simulated /
  realized fills. Excludes BUSDT 110017 reject-loop pollution per V3 §11
  P3a KPI footnote (known bug pollutes execution rate estimate).
MODULE_NOTE (中): 用 Bybit V5 USDT linear perpetual fee schedule + VIP-tier
  override 估計 per-fill / per-trade 手續費（bps）。從模擬 / 已實現 fills
  的 `liquidity_role` 欄位估計 maker/taker 執行類型分布。依 V3 §11 P3a KPI
  腳註，排除 BUSDT 110017 reject-loop 污染（已知 bug 污染執行率估計）。

V3 §11 P3a binding / V3 §11 P3a 綁定:
- "fee model"
- "maker/taker execution estimates"
- BUSDT 110017 reject loop exclusion (per FA cold panorama 2026-05-02)

Default Bybit V5 USDT linear perpetual fee schedule (VIP=0):
- maker_fee_bps = 2.0 bps (0.02%)
- taker_fee_bps = 5.5 bps (0.055%)
Source: docs/references/2026-04-04--bybit_api_reference.md L656
       (`refresh_fee_rates` default 註: "taker 0.055%, maker 0.02%")
NOTE / 註: PA dispatch wording "maker -0.025% / taker 0.06%" appears to be
  a different cohort (possibly older docs / spot category). We use the
  Bybit reference values for USDT linear perpetual; VIP tier table allows
  override. Operator may adjust via `vip_tier` parameter.
PA dispatch 用詞「maker -0.025% / taker 0.06%」似為不同群組（可能舊版 docs /
  spot category）。我們對 USDT linear perpetual 用 Bybit reference 值；VIP 表
  允許 override。Operator 可由 `vip_tier` 參數調整。

Fills DataFrame schema (REQUIRED):
- 'symbol': str (e.g., 'BTCUSDT', 'BUSDT')
- 'fee_bps': float — pre-computed fee in bps (signed: negative = rebate paid
                     to taker on maker-side fill; positive = fee charged)
                     若 None → 用 vip_tier maker/taker default
- 'liquidity_role': str enum {'maker', 'taker', 'unknown'}
- 'reject_code': Optional[str] — fill-side reject code; if 'BUSDT'+'110017'
                                  → exclude from execution split estimate

Usage / 使用:
    from program_code.learning_engine.fee_execution_calibrator import (
        FeeExecutionCalibrator, FeeEstimate, ExecutionSplit,
    )
    calibrator = FeeExecutionCalibrator()
    fee_est = calibrator.estimate_fee_per_trade(fills_df, vip_tier=0)
    split = calibrator.estimate_maker_taker_split(fills_df)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — Bybit V5 USDT linear fee schedule by VIP tier
# 常量 — Bybit V5 USDT linear 各 VIP tier 手續費表
# ---------------------------------------------------------------------------

# Source / 來源: docs/references/2026-04-04--bybit_api_reference.md L656.
# Bybit official VIP tier docs: https://www.bybit.com/en/help-center/article/...
# Values in bps (1 bp = 0.01%). Maker rebate exists for VIP 4+ Pro accounts
# but is omitted from default table; operator can pass custom dict via
# `vip_tier_override` if needed.
# 數值單位 bps（1 bp = 0.01%）。Maker rebate 存在於 VIP 4+ Pro 帳戶但 default
# 表省略；operator 如需可傳入 `vip_tier_override` 自定 dict。
DEFAULT_VIP_FEE_TABLE: Dict[int, Dict[str, float]] = {
    0: {"maker_bps": 2.0, "taker_bps": 5.5},   # default retail / 散戶預設
    1: {"maker_bps": 1.6, "taker_bps": 5.0},
    2: {"maker_bps": 1.4, "taker_bps": 4.5},
    3: {"maker_bps": 1.2, "taker_bps": 4.0},
    4: {"maker_bps": 1.0, "taker_bps": 3.5},   # Pro 1
    5: {"maker_bps": 0.8, "taker_bps": 3.0},   # Pro 2
}

# BUSDT 110017 reject-loop exclusion filter constants (per V3 §11 P3a KPI footnote).
# BUSDT funding_arb V2 deprecation path (commit a19797d) left residual orders
# triggering Bybit reject code 110017 (insufficient balance for short, looped).
# Inclusion in maker/taker estimate biases the rate downward.
# BUSDT 110017 reject-loop 排除過濾常量（V3 §11 P3a KPI 腳註）。BUSDT funding_arb
# V2 棄策略路徑（commit a19797d）遺留訂單觸發 Bybit reject code 110017（空單餘額
# 不足，循環）。納入 maker/taker 估計會向下偏誤。
BUSDT_110017_SYMBOL: str = "BUSDT"
BUSDT_110017_REJECT_CODE: str = "110017"

# Liquidity role enum values per V3 §4.1 simulated_fills schema.
# 流動性角色枚舉值（V3 §4.1 simulated_fills schema）。
LIQUIDITY_ROLE_MAKER: str = "maker"
LIQUIDITY_ROLE_TAKER: str = "taker"
LIQUIDITY_ROLE_UNKNOWN: str = "unknown"


# ---------------------------------------------------------------------------
# Result dataclasses / 結果 dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FeeEstimate:
    """
    Fee aggregation outcome.
    手續費聚合結果。

    Attributes / 屬性:
        avg_fee_bps: weighted-average fee across all fills in bps. /
                     所有 fills 加權平均手續費（bps）。
        maker_fee_bps: VIP-tier maker fee rate. /
                       VIP-tier maker 費率。
        taker_fee_bps: VIP-tier taker fee rate. /
                       VIP-tier taker 費率。
        sample_size: number of fills aggregated. /
                     聚合的 fills 數量。
        vip_tier: VIP tier used for default rates. /
                  default 費率使用的 VIP tier。
    """

    avg_fee_bps: float
    maker_fee_bps: float
    taker_fee_bps: float
    sample_size: int
    vip_tier: int


@dataclass
class ExecutionSplit:
    """
    Maker/taker execution split outcome.
    Maker/taker 執行類型分布結果。

    Attributes / 屬性:
        maker_pct: fraction of fills with liquidity_role='maker'. /
                   liquidity_role='maker' 的 fills 比例。
        taker_pct: fraction of fills with liquidity_role='taker'. /
                   liquidity_role='taker' 的 fills 比例。
        unknown_pct: fraction with unknown / null liquidity_role. /
                     未知 / null liquidity_role 的比例。
        sample_size: number of fills counted (post-exclusion). /
                     計入的 fills 數量（排除後）。
        sample_size_excluded_busdt_110017: fills excluded by BUSDT 110017
                                            filter (audit transparency). /
                                            BUSDT 110017 filter 排除的 fills
                                            數量（審計透明度）。
    """

    maker_pct: float
    taker_pct: float
    unknown_pct: float
    sample_size: int
    sample_size_excluded_busdt_110017: int


# ---------------------------------------------------------------------------
# Calibrator class / 校準器類別
# ---------------------------------------------------------------------------


class FeeExecutionCalibrator:
    """
    Fee model + maker/taker split estimator with BUSDT 110017 exclusion.
    手續費模型 + maker/taker 分布估計器，含 BUSDT 110017 排除。

    Production note / 生產備註: When FUP-2 attribution writer + decision_outcomes
    timeframe fix deploy, fills_df shall be loaded from
    `replay.simulated_fills` (during P3a calibration) JOIN
    `learning.exit_features` per cell key. For now, fixture-driven IMPL
    accepts arbitrary DataFrame matching schema above.
    """

    def __init__(
        self,
        vip_tier_override: Optional[Dict[int, Dict[str, float]]] = None,
    ) -> None:
        """
        Initialize with optional VIP fee table override.
        以選填 VIP 費率表 override 初始化。

        Args / 引數:
            vip_tier_override: custom VIP tier → fee dict mapping (overrides
                               DEFAULT_VIP_FEE_TABLE). /
                               自定 VIP tier → fee dict 對映（覆蓋 default）。
        """
        self.fee_table: Dict[int, Dict[str, float]] = (
            dict(DEFAULT_VIP_FEE_TABLE)
            if vip_tier_override is None
            else dict(vip_tier_override)
        )

    # ------------------------------------------------------------------
    # Public API / 公開 API
    # ------------------------------------------------------------------

    def get_vip_fees(self, vip_tier: int) -> Dict[str, float]:
        """
        Look up maker/taker bps for a VIP tier; raises if absent.
        查找 VIP tier 的 maker/taker bps；缺失則拋錯。

        Args / 引數:
            vip_tier: VIP tier integer key. / VIP tier 整數 key。

        Returns / 回傳:
            dict with 'maker_bps' + 'taker_bps' keys. /
            含 'maker_bps' + 'taker_bps' keys 的 dict。

        Raises / 拋出:
            ValueError: vip_tier not in fee table. / vip_tier 不在費率表中。
        """
        if vip_tier not in self.fee_table:
            raise ValueError(
                f"VIP tier {vip_tier} not in fee table; available: "
                f"{sorted(self.fee_table.keys())}"
            )
        return self.fee_table[vip_tier]

    def estimate_fee_per_trade(
        self,
        fills_df: pd.DataFrame,
        vip_tier: int = 0,
    ) -> FeeEstimate:
        """
        Estimate average fee per trade in bps from fills DataFrame.
        從 fills DataFrame 估計每筆交易平均手續費（bps）。

        Logic / 邏輯:
        1. Filter out BUSDT 110017 reject-loop pollution.
           過濾 BUSDT 110017 reject-loop 污染。
        2. If `fee_bps` column present + not all NULL → use observed values.
           若 `fee_bps` column 存在且非全 NULL → 用觀測值。
        3. Otherwise compute synthetic fee from VIP-tier default + liquidity_role.
           否則由 VIP-tier default + liquidity_role 計算合成 fee。

        Args / 引數:
            fills_df: see module docstring schema. / 見模組 docstring schema。
            vip_tier: Bybit VIP tier key (0=retail). / Bybit VIP tier key。

        Returns / 回傳:
            FeeEstimate with avg_fee_bps + tier rates + sample_size. /
            含 avg_fee_bps + tier 費率 + sample_size 的 FeeEstimate。
        """
        tier_fees = self.get_vip_fees(vip_tier)
        maker_bps = float(tier_fees["maker_bps"])
        taker_bps = float(tier_fees["taker_bps"])

        df = self._filter_busdt_110017(fills_df)

        if len(df) == 0:
            return FeeEstimate(
                avg_fee_bps=0.0,
                maker_fee_bps=maker_bps,
                taker_fee_bps=taker_bps,
                sample_size=0,
                vip_tier=vip_tier,
            )

        # Path A: observed fee_bps present and not all NULL. / 觀測 fee_bps 路徑。
        if "fee_bps" in df.columns:
            observed = df["fee_bps"].dropna()
            if len(observed) > 0:
                avg = float(observed.astype(float).mean())
                return FeeEstimate(
                    avg_fee_bps=avg,
                    maker_fee_bps=maker_bps,
                    taker_fee_bps=taker_bps,
                    sample_size=len(observed),
                    vip_tier=vip_tier,
                )

        # Path B: synthetic from liquidity_role. / 由 liquidity_role 合成路徑。
        if "liquidity_role" not in df.columns:
            # No way to attribute → use mid (50/50) as conservative estimate.
            # 無屬性可用 → 用中間（50/50）作為保守估計。
            avg = (maker_bps + taker_bps) / 2.0
            return FeeEstimate(
                avg_fee_bps=avg,
                maker_fee_bps=maker_bps,
                taker_fee_bps=taker_bps,
                sample_size=len(df),
                vip_tier=vip_tier,
            )

        roles = df["liquidity_role"].astype(str).str.lower()
        n_maker = int((roles == LIQUIDITY_ROLE_MAKER).sum())
        n_taker = int((roles == LIQUIDITY_ROLE_TAKER).sum())
        n_total = n_maker + n_taker

        if n_total == 0:
            avg = (maker_bps + taker_bps) / 2.0
        else:
            avg = (n_maker * maker_bps + n_taker * taker_bps) / float(n_total)

        return FeeEstimate(
            avg_fee_bps=avg,
            maker_fee_bps=maker_bps,
            taker_fee_bps=taker_bps,
            sample_size=len(df),
            vip_tier=vip_tier,
        )

    def estimate_maker_taker_split(
        self,
        fills_df: pd.DataFrame,
    ) -> ExecutionSplit:
        """
        Estimate maker/taker/unknown execution split from liquidity_role column.
        從 liquidity_role column 估計 maker/taker/unknown 執行類型分布。

        BUSDT 110017 reject-loop fills excluded for audit transparency.
        排除 BUSDT 110017 reject-loop fills 以審計透明度。

        Args / 引數:
            fills_df: see module docstring schema. / 見模組 docstring schema。

        Returns / 回傳:
            ExecutionSplit with maker_pct + taker_pct + unknown_pct. /
            含 maker_pct + taker_pct + unknown_pct 的 ExecutionSplit。
        """
        # Count BUSDT 110017 exclusions BEFORE filter for audit transparency.
        # 在 filter 前計算 BUSDT 110017 排除數量（審計透明度）。
        n_excluded = self._count_busdt_110017(fills_df)
        df = self._filter_busdt_110017(fills_df)

        if "liquidity_role" not in df.columns or len(df) == 0:
            return ExecutionSplit(
                maker_pct=0.0,
                taker_pct=0.0,
                unknown_pct=0.0,
                sample_size=len(df),
                sample_size_excluded_busdt_110017=n_excluded,
            )

        roles = df["liquidity_role"].astype(str).str.lower()
        n = len(roles)
        n_maker = int((roles == LIQUIDITY_ROLE_MAKER).sum())
        n_taker = int((roles == LIQUIDITY_ROLE_TAKER).sum())
        # Unknown = anything not in {maker, taker} (includes 'unknown', NaN, '').
        # Unknown = 不在 {maker, taker} 的任何值（含 'unknown'、NaN、空字串）。
        n_unknown = n - n_maker - n_taker

        return ExecutionSplit(
            maker_pct=n_maker / n,
            taker_pct=n_taker / n,
            unknown_pct=n_unknown / n,
            sample_size=n,
            sample_size_excluded_busdt_110017=n_excluded,
        )

    # ------------------------------------------------------------------
    # Internal filters / 內部過濾
    # ------------------------------------------------------------------

    def _filter_busdt_110017(self, fills_df: pd.DataFrame) -> pd.DataFrame:
        """
        Drop rows where (symbol='BUSDT' AND reject_code='110017').
        丟棄 (symbol='BUSDT' AND reject_code='110017') 的列。

        Per V3 §11 P3a KPI footnote: BUSDT funding_arb V2 deprecation path
        (commit a19797d) left residual orders triggering Bybit 110017 reject
        loop, polluting execution rate estimate. Filter at SQL probe and
        Python aggregation layers.
        依 V3 §11 P3a KPI 腳註：BUSDT funding_arb V2 棄策略路徑遺留訂單觸發
        Bybit 110017 reject loop，污染執行率估計。在 SQL probe + Python 聚合層過濾。
        """
        # If column 'reject_code' absent, no filter applied (graceful).
        # 若 column 'reject_code' 缺失，不過濾（優雅 fallback）。
        if "reject_code" not in fills_df.columns:
            return fills_df

        if "symbol" not in fills_df.columns:
            return fills_df

        # Build boolean mask: True = keep, False = drop. /
        # 建布林 mask：True = 保留，False = 丟棄。
        symbol_match = fills_df["symbol"].astype(str) == BUSDT_110017_SYMBOL
        reject_match = (
            fills_df["reject_code"].astype(str) == BUSDT_110017_REJECT_CODE
        )
        drop_mask = symbol_match & reject_match
        return fills_df[~drop_mask].copy()

    def _count_busdt_110017(self, fills_df: pd.DataFrame) -> int:
        """
        Count rows that WOULD be dropped by BUSDT 110017 filter.
        計算被 BUSDT 110017 filter 丟棄的列數（用於審計透明度）。
        """
        if "reject_code" not in fills_df.columns:
            return 0
        if "symbol" not in fills_df.columns:
            return 0
        symbol_match = fills_df["symbol"].astype(str) == BUSDT_110017_SYMBOL
        reject_match = (
            fills_df["reject_code"].astype(str) == BUSDT_110017_REJECT_CODE
        )
        return int((symbol_match & reject_match).sum())


# ---------------------------------------------------------------------------
# Module-level convenience / 模組級便利函數
# ---------------------------------------------------------------------------


def estimate_fee_and_split(
    fills_df: pd.DataFrame,
    vip_tier: int = 0,
) -> tuple[FeeEstimate, ExecutionSplit]:
    """
    Convenience: run both fee + split estimation in one call.
    便利函數：一次呼叫同時跑 fee + split 估計。
    """
    calib = FeeExecutionCalibrator()
    return (
        calib.estimate_fee_per_trade(fills_df, vip_tier=vip_tier),
        calib.estimate_maker_taker_split(fills_df),
    )
