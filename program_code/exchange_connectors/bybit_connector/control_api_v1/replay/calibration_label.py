"""REF-20 Sprint C R6 W6 R6-T9 Sprint C1 closure — replay 校準標籤 Python port。

模組目的：
    本模組是 Rust `rust/openclaw_engine/src/replay/calibration_label.rs`
    `derive_execution_confidence()` 的 Python 字節等值 port。被
    `run_finalize_route._compute_and_persist_calibration` 在 post-replay
    階段呼叫，使整條 caller chain（finalize → trading.fills SELECT →
    derive_execution_confidence → update_execution_confidence → V049 row
    UPDATE）能在 Python side 完成而不需要跨 IPC 邊界。

    輸入下游：
      1. `replay.experiments.execution_confidence`（V049 text 列；CHECK
         enum {'none', 'limited', 'calibrated', 'pending'}）。
      2. `replay.simulated_fills.evidence_source_tier` 經 TTL 映射間接
         影響（calibrated→7d / limited→3d / none→0s）。

    數學契約（依 QC spec §1）byte-equal Rust：
      4 維度 AND 短路布林過濾：
        維度 1（樣本量）：n=0 → None。
        維度 2（freshness）：last_fill_age > 14d → None。
        維度 3（fee_bps 形狀）：MAD/IQR 門檻。
        維度 4（切點）：
          calibrated_ok = n ≥ 200 && age ≤ 7d  && MAD < 3 bps && IQR <  8 bps
          limited_ok    = n ≥  30 && age ≤ 14d && MAD < 8 bps && IQR < 20 bps
          否則 → None。

    統計選擇（依 QC spec §2）：
      - σ 用 MAD（median absolute deviation）— bimodal maker/taker 穩健。
      - IQR（Q3 − Q1）為副驗。

    CI 計算分層（依 QC spec §3）byte-equal Rust：
      - n ≥ 200 → empirical percentile p5/p50/p95（Type 7 線性插值）。
      - 30 ≤ n < 200 → 寬幅 percentile + 0.5×IQR pad + 單調強制。
      - n < 30 → median ± 1.645 × 1.4826 × MAD（normal-extension）。

    TTL 映射（依 QC spec §4）：
      - Calibrated → timedelta(days=7)
      - Limited    → timedelta(days=3)
      - None       → timedelta(0)

    邊界 case（依 QC spec §6）：
      - 空輸入 → None。
      - NaN/Inf fee_rate 或 entry_price → 過濾前 n 自動降低。
      - σ/MAD = NaN（n < 2）→ None。
      - σ/MAD = 0（fill 全同 fee）→ 若 n ≥ 200 + freshness OK 仍 calibrated。
      - net_bps_after_fee 全負 → label 不變（label 衡量 fee/slippage
        校準信心，**非** PnL 信心）。
      - 不傳播 Exception：任何異常 downgrade 至 None。

    Forbidden surface 審計（V3 §6.2 必綠）：
      - 0 引用 paper_state / canary_writer / database / ipc_server /
        governance_hub / live_authorization / decision_lease。
      - 純函數模組：僅依 datetime + math + dataclasses + enum + typing。
      - 無 runtime state、無 I/O。

    本檔包含：
      - ExecutionConfidence enum（3-variant，str-valued）。
      - FillRecord dataclass（minimum input row）。
      - CalibrationResult dataclass（output 含 label + 統計 + TTL）。
      - derive_execution_confidence(fills, now) → CalibrationResult。
      - 4 robust stat helper：_mad / _iqr / _median / _percentile。

    不在本檔（刻意邊界）：
      - DB writer 層（experiment_registry.update_execution_confidence 既 land）。
      - trading.fills row → list[FillRecord] SQL 投影（caller 即
        `run_finalize_route._compute_and_persist_calibration` 負責）。
      - Regime 偵測（DEFER 至 Sprint D R9）。

SPEC: REF-20 V3 §3 G7/G8 + V049 (replay_experiments) + V050
      (replay_simulated_fills.ci_*_bps) + Sprint C R6 W6 dispatch §1.1 +
      QC pre-DAG advisory `2026-05-05--ref20_r6_calibration_label_spec.md`.
Rust source-of-truth: rust/openclaw_engine/src/replay/calibration_label.rs
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List


# ───────────────────────────────────────────────────────────────────
# 公開型別
# ───────────────────────────────────────────────────────────────────


class ExecutionConfidence(str, Enum):
    """執行校準信心標籤（依 QC spec §1）。

    str-valued enum 使 `result.label.value` 直接餵 V049 CHECK enum
    （V049_EXECUTION_CONFIDENCE_ALLOWED = {'none', 'limited', 'calibrated'}）。
    """

    NONE = "none"
    LIMITED = "limited"
    CALIBRATED = "calibrated"


@dataclass
class FillRecord:
    """`derive_execution_confidence` 消費的最小 fill-record 投影。

    欄位語意（鏡 Rust FillRecord）：
      - fee_rate：小數（**非** bps）。函數內部 ×10000 轉 bps。
      - entry_price：開倉時 quote 計價。
      - exit_price：平倉時 quote 計價。
      - is_long：True=多 / False=空。caller 將 SQL `side` (Buy/Sell/long/short) 映射到 bool。
      - filled_at：UTC datetime；freshness 以 derive 的 `now` 為基準。
    """

    fee_rate: float
    entry_price: float
    exit_price: float
    is_long: bool
    filled_at: datetime


@dataclass
class CalibrationResult:
    """`derive_execution_confidence` 輸出的校準結果。

    欄位語意（鏡 Rust CalibrationResult）：
      - label：三層信心（V049 列）。
      - sample_count：過濾 NaN/Inf 後的 n。
      - last_fill_age_ms：now − 最後 filled_at（毫秒）；n=0 時 -1。
      - fee_bps_mad：robust scale；n < 2 時 NaN。
      - fee_bps_iqr：tail-robust width（Q3 − Q1）；n < 4 時 NaN。
      - net_bps_p5/p50/p95：餵 V050 ci_low/mid/high_bps（單調保證）。
      - ttl：V051 expires_at = now + ttl；None 時 timedelta(0)。
    """

    label: ExecutionConfidence
    sample_count: int
    last_fill_age_ms: int
    fee_bps_mad: float
    fee_bps_iqr: float
    net_bps_p5: float
    net_bps_p50: float
    net_bps_p95: float
    ttl: timedelta

    @classmethod
    def none_default(cls) -> "CalibrationResult":
        """空 / 無效輸入下的 canonical「無信號」結果。"""
        return cls(
            label=ExecutionConfidence.NONE,
            sample_count=0,
            last_fill_age_ms=-1,
            fee_bps_mad=float("nan"),
            fee_bps_iqr=float("nan"),
            net_bps_p5=float("nan"),
            net_bps_p50=float("nan"),
            net_bps_p95=float("nan"),
            ttl=timedelta(0),
        )


# ───────────────────────────────────────────────────────────────────
# 公開 API
# ───────────────────────────────────────────────────────────────────


def derive_execution_confidence(
    fills: List[FillRecord],
    now: datetime,
) -> CalibrationResult:
    """為單一 (strategy, symbol) cell 推導 ExecutionConfidence。

    依 QC spec §1 4 維度 AND 過濾（短路）：
      1. sample_count ≥ {200|30}
      2. last_fill_age_days ≤ {7|14}
      3. fee_bps_mad < {3|8} bps
      4. fee_bps_iqr < {8|20} bps

    Args:
        fills: caller 傳入的 fills（時序排列；空 list 合法 → None）。
        now: freshness 算術的參考時鐘；caller 傳 datetime.now(timezone.utc)。

    Returns:
        CalibrationResult — 不 raise；異常依 QC §6 降至 None。
    """
    # Step 1：過濾 NaN/Inf；caller 契約允許 NaN fee_rate 等存在。
    valid = [
        f
        for f in fills
        if math.isfinite(f.fee_rate)
        and math.isfinite(f.entry_price)
        and math.isfinite(f.exit_price)
    ]

    n = len(valid)
    if n == 0:
        return CalibrationResult.none_default()

    # Step 2：freshness — 防禦性取 max(filled_at)（容忍 caller 未排序）。
    last_filled_at = max(f.filled_at for f in valid)
    age = now - last_filled_at
    last_fill_age_ms = int(age.total_seconds() * 1000.0)
    last_fill_age_days = last_fill_age_ms / 86_400_000.0

    fee_bps_vec = [f.fee_rate * 10_000.0 for f in valid]
    net_bps_vec = [
        v
        for v in (_compute_net_bps_after_fee(f) for f in valid)
        if math.isfinite(v)
    ]

    fee_bps_mad = _mad(fee_bps_vec)
    fee_bps_iqr = _iqr(fee_bps_vec)

    # Step 3 + 4：4 維 AND 過濾。freshness > 14d 短路至 None（QC §1）。
    if last_fill_age_days > 14.0:
        label = ExecutionConfidence.NONE
    elif not math.isfinite(fee_bps_mad):
        # σ/MAD NaN（n < 2）→ None per QC §6。
        label = ExecutionConfidence.NONE
    else:
        # NaN IQR（n < 4）視為「嚴格切點失敗」；NaN→inf 使 iqr<threshold 為 false。
        iqr_for_compare = fee_bps_iqr if math.isfinite(fee_bps_iqr) else float("inf")

        calibrated_ok = (
            n >= 200
            and last_fill_age_days <= 7.0
            and fee_bps_mad < 3.0
            and iqr_for_compare < 8.0
        )
        limited_ok = (
            n >= 30
            and last_fill_age_days <= 14.0
            and fee_bps_mad < 8.0
            and iqr_for_compare < 20.0
        )

        if calibrated_ok:
            label = ExecutionConfidence.CALIBRATED
        elif limited_ok:
            label = ExecutionConfidence.LIMITED
        else:
            label = ExecutionConfidence.NONE

    # Step 5：依 QC spec §3 計算 CI。
    net_p5, net_p50, net_p95 = _compute_ci(net_bps_vec)

    # Step 6：依 QC spec §4 映射 TTL。
    if label == ExecutionConfidence.CALIBRATED:
        ttl = timedelta(days=7)
    elif label == ExecutionConfidence.LIMITED:
        ttl = timedelta(days=3)
    else:
        ttl = timedelta(0)

    return CalibrationResult(
        label=label,
        sample_count=n,
        last_fill_age_ms=last_fill_age_ms,
        fee_bps_mad=fee_bps_mad,
        fee_bps_iqr=fee_bps_iqr,
        net_bps_p5=net_p5,
        net_bps_p50=net_p50,
        net_bps_p95=net_p95,
        ttl=ttl,
    )


# ───────────────────────────────────────────────────────────────────
# 內部 helper
# ───────────────────────────────────────────────────────────────────


def _compute_net_bps_after_fee(fill: FillRecord) -> float:
    """為單筆 fill 依 QC spec §3.1 計算 net_bps_after_fee（byte-equal Rust）。

    公式：
      gross_bps = (exit - entry) / entry × 10000 × direction
      net_bps   = gross_bps − 2 × fee_bps（進場 + 出場 fee）
      （slippage_bps 留 R6-T2 row level）
    """
    if not math.isfinite(fill.entry_price) or fill.entry_price == 0.0:
        return float("nan")
    direction = 1.0 if fill.is_long else -1.0
    gross_bps = (
        (fill.exit_price - fill.entry_price) / fill.entry_price * 10_000.0 * direction
    )
    fee_bps = fill.fee_rate * 10_000.0
    return gross_bps - 2.0 * fee_bps


def _compute_ci(net_bps_vec: List[float]) -> tuple[float, float, float]:
    """依 QC spec §3 計算 (p5, p50, p95)（byte-equal Rust）。

    分層策略：
      - n ≥ 200 → empirical percentile（Type 7 線性插值）。
      - 30 ≤ n < 200 → 寬幅 percentile + 0.5×IQR pad（單調強制）。
      - n < 30 → median ± 1.645 × 1.4826 × MAD（normal-extension）。
      - n == 0 → 全 NaN。
    """
    n = len(net_bps_vec)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    if n < 30:
        # Normal-extension fallback：median ± 1.645 × σ；σ ≈ 1.4826 × MAD。
        med = _median(net_bps_vec)
        mad_value = _mad(net_bps_vec)
        if math.isfinite(mad_value):
            # 1.645 × 1.4826 = 2.4389（與 Rust 寫死同 magic literal）。
            half_width = 1.645 * 1.4826 * mad_value
        else:
            half_width = 0.0
        return med - half_width, med, med + half_width
    if n < 200:
        # 寬幅 empirical percentile：兩尾各加 0.5 × IQR。
        iqr_value = _iqr(net_bps_vec)
        pad = 0.5 * iqr_value if math.isfinite(iqr_value) else 0.0
        p5_raw = _percentile(net_bps_vec, 5.0)
        p50 = _percentile(net_bps_vec, 50.0)
        p95_raw = _percentile(net_bps_vec, 95.0)
        p5 = min(p5_raw - pad, p50)
        p95 = max(p95_raw + pad, p50)
        return p5, p50, p95
    # n ≥ 200：直接 empirical percentile。
    return (
        _percentile(net_bps_vec, 5.0),
        _percentile(net_bps_vec, 50.0),
        _percentile(net_bps_vec, 95.0),
    )


# ───────────────────────────────────────────────────────────────────
# Robust 統計 helpers（byte-equal Rust public）
# ───────────────────────────────────────────────────────────────────


def _mad(v: List[float]) -> float:
    """Median absolute deviation（50% breakdown 點）。

    回傳：
      - len(v) < 2 → NaN（QC §6 統計量無定義）。
      - 否則 median(|x - median(v)|)。
    """
    if len(v) < 2:
        return float("nan")
    med = _median(v)
    abs_dev = [abs(x - med) for x in v]
    return _median(abs_dev)


def _iqr(v: List[float]) -> float:
    """四分位距（Q3 − Q1）。

    回傳：
      - len(v) < 4 → NaN（樣本不足）。
      - 否則 percentile(v, 75) − percentile(v, 25)。
    """
    if len(v) < 4:
        return float("nan")
    return _percentile(v, 75.0) - _percentile(v, 25.0)


def _median(v: List[float]) -> float:
    """中位數 = percentile(v, 50.0)；空輸入回 NaN。"""
    if not v:
        return float("nan")
    return _percentile(v, 50.0)


def _percentile(v: List[float], p: float) -> float:
    """線性插值 percentile（Type 7 / Hyndman-Fan）— byte-equal Rust。

    演算法：
      - 升序排序副本；過濾 NaN。
      - 位置 h = (n − 1) × p/100，n = len(sorted)。
      - sorted[floor(h)] 與 sorted[ceil(h)] 之間線性插值。
      - p clamp 至 [0, 100]。

    邊界：
      - 過濾 NaN 後空 → NaN。
      - n=1 → 該值。
      - p=0 → 最小，p=100 → 最大。
    """
    sorted_vals = sorted(x for x in v if math.isfinite(x))
    if not sorted_vals:
        return float("nan")
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    p_clamped = max(0.0, min(100.0, p))
    h = (n - 1.0) * p_clamped / 100.0
    lo = int(math.floor(h))
    hi = int(math.ceil(h))
    if lo == hi:
        return sorted_vals[lo]
    frac = h - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


__all__ = [
    "CalibrationResult",
    "ExecutionConfidence",
    "FillRecord",
    "derive_execution_confidence",
]
