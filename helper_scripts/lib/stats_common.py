"""共享統計公式 — W-AUDIT-8b / 8c / alpha_candidate Stage 0R 整併層。

MODULE_NOTE:
  模塊用途：整併原本在 ``w_audit_8b/funding_skew_stage0r_metrics.py`` 與
    ``w_audit_8c/liquidation_cluster_stage0r_metrics.py`` 之間 copy-paste 的
    統計公式（E5 finding #3）。alpha_candidate runner / adapter 透過 8b / 8c
    metrics 模塊間接復用同一組 helper，故此模塊是三者共同的單一真相源。
  主要函數：``_safe_float`` / ``_safe_int`` / ``_normal_cdf`` / ``_skew`` /
    ``_kurtosis`` / ``psr_bailey_ldp`` / ``dsr_with_k`` / ``block_bootstrap_ci`` /
    ``wilson_ci_95`` / ``pbo_cscv``（原 ``_pbo``）/ ``day_bucket``（原
    ``_day_bucket``）/ ``n_eff_horizon_overlap``（原 ``_n_eff`` / 8c
    ``_n_eff_horizon_overlap``）。
  依賴：純 stdlib（math / random / statistics / datetime / collections /
    itertools）。無 DB / 無 file IO / 無 live state 修改。
  硬邊界：
    - 純 math layer；只服務 offline scripts，不得被 runtime app 模塊匯入。
    - 隨機性（bootstrap / PBO sampling）一律以顯式 ``seed`` 參數注入，使結果
      可重現；caller 必須傳入其歷史 seed 以維持 byte-level 結果一致。

  ── 整併時的 source-divergence 對照（重要） ──
  8b / 8c 兩份副本在整併前已經 diverge，逐一核對結論如下（math-correct canonical
  選擇 + bug flag）：
    1. ``_safe_float`` / ``_safe_int`` / ``_normal_cdf`` / ``_skew`` /
       ``_kurtosis`` / ``psr_bailey_ldp`` / ``dsr_with_k`` / ``wilson_ci_95``：
       8b vs 8c 邏輯 byte-identical（8c 僅多 docstring）。直接採用。
    2. ``block_bootstrap_ci`` / ``_pbo``：邏輯 byte-identical，唯一差異是硬編碼
       亂數 seed（8b=20260515 / 8c=20260518；PBO 內 8b=20260516 / 8c=20260518）。
       這是「每次研究獨立 seed」的刻意設計，非 bug。canonical 把 seed 升為參數，
       由各 caller 傳入歷史 seed 保結果一致。
    3. ``n_eff_horizon_overlap``（原 8b ``_n_eff`` / 8c ``_n_eff_horizon_overlap``）
       **是真正的 latent bug divergence**：
         - 8b：``int(n / max(1, horizon_min // 5))``（整數除 floor）。
         - 8c：``int(n / max(1, math.ceil(horizon_min / 5)))``（math.ceil）。
       8c MODULE 註解已記 MIT 2026-05-18 dual review §2.1.4：``horizon_min // 5``
       在 horizon=6/10/14 時 floor 至 1/2/2，漏算 sub-5m bar 的 overlap penalty
       （n_eff 被高估 → CI / floor gate 偏鬆 → over-PASS bias，違 RP6
       uncertainty→conservative）。對 canonical grid（horizon 15/30/60）兩式
       結果相同（3/6/12），故 8b 在當前資料是 dormant；但 grid expansion
       （10/14/30 sensitivity sweep）會 regress。**canonical 採 math.ceil（數學
       正確版）**；對 8b 現行資料 0 行為改變（dormant fix），同時根除 8b 的 floor
       bug。QC follow-up：8b 既有報告若曾用非 canonical-grid horizon 重跑，n_eff
       需重新核對。
"""

from __future__ import annotations

import math
import random
import statistics
from datetime import datetime, timezone
from itertools import combinations
from statistics import NormalDist
from typing import Mapping, Sequence


# ── 數值安全轉換 ───────────────────────────────────────────────────────────


def _safe_float(value: object) -> float | None:
    """轉成 finite float，否則 None；NaN / Inf → None。

    為什麼 fail-closed 回 None：metrics 計算中 NaN propagation 會污染下游
    PSR / DSR / CI；統一回 None 強迫 caller 顯式處理，不讓壞值靜默傳遞。
    """
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _safe_int(value: object) -> int | None:
    """轉成 int，否則 None（不可轉者不拋例外，回 None 由 caller 處理）。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ── 統計分布輔助（skew / kurtosis；供 PSR Bailey & López de Prado） ─────────


def _normal_cdf(x: float) -> float:
    """標準常態 CDF。"""
    return NormalDist().cdf(x)


def _skew(values: Sequence[float]) -> float | None:
    """母體（population）偏度；n<3 或零變異回 None。"""
    if len(values) < 3:
        return None
    mean = statistics.mean(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    if var <= 0:
        return None
    sd = math.sqrt(var)
    return sum(((v - mean) / sd) ** 3 for v in values) / len(values)


def _kurtosis(values: Sequence[float]) -> float | None:
    """母體（population）峰度（非超額；常態 ≈ 3）；n<4 或零變異回 None。"""
    if len(values) < 4:
        return None
    mean = statistics.mean(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    if var <= 0:
        return None
    sd = math.sqrt(var)
    return sum(((v - mean) / sd) ** 4 for v in values) / len(values)


# ── PSR / DSR（Bailey & López de Prado 2014） ──────────────────────────────


def psr_bailey_ldp(values: Sequence[float], sr_benchmark: float = 0.0) -> float | None:
    """Probabilistic Sharpe Ratio (PSR) per Bailey & López de Prado 2014。

    為什麼用 PSR 而非 textbook Sharpe：textbook Sharpe 假設常態 return，而
    funding-skew / liquidation-cluster return 顯然 heavy-tailed + skewed；PSR
    顯式以 skew（γ3）/ kurtosis（γ4）修正。

    公式：denom² = 1 − γ3·SR̂ + ((γ4−1)/4)·SR̂²；
          z = (SR̂ − SR*)·√(n−1) / denom；PSR = Φ(z)。
    sr_benchmark = 0.0 → PSR(0)；> 0 → PSR(SR*)（DSR 用 SR* = √(2 ln K)）。
    n<4 / 零標準差 / denom² ≤ 0 一律回 None（fail-closed，不回偽 PSR）。
    """
    clean = [v for v in values if math.isfinite(v)]
    if len(clean) < 4:
        return None
    sd = statistics.stdev(clean)
    if sd <= 0:
        return None
    sr_hat = statistics.mean(clean) / sd
    skew = _skew(clean)
    kurt = _kurtosis(clean)
    if skew is None or kurt is None:
        return None
    denom_sq = 1.0 - skew * sr_hat + ((kurt - 1.0) / 4.0) * (sr_hat**2)
    if denom_sq <= 0:
        return None
    z = (sr_hat - sr_benchmark) * math.sqrt(len(clean) - 1) / math.sqrt(denom_sq)
    return _normal_cdf(z)


def dsr_with_k(values: Sequence[float], k_total: int) -> float | None:
    """Deflated Sharpe Ratio per Bailey & López de Prado 2014。

    為什麼用 DSR：多重比較 penalty；K_total = 嘗試過的 candidate cell 數。
    sr_benchmark = √(2 × ln K_total) 是 Gaussian 假設下 random trials 的
    expected max Sharpe（保守 leading term）。k_total ≤ 1 無多重比較，回 None。
    """
    if k_total <= 1:
        return None
    sr_benchmark = math.sqrt(2.0 * math.log(k_total))
    return psr_bailey_ldp(values, sr_benchmark=sr_benchmark)


# ── Block bootstrap CI（抗 autocorrelation 的 95% bootstrap 區間） ─────────


def block_bootstrap_ci(
    values: Sequence[float],
    *,
    block_size: int,
    iterations: int = 400,
    seed: int,
) -> tuple[float, float] | None:
    """Stationary block bootstrap 95% CI（回傳排序後 2.5% / 97.5% 分位）。

    為什麼 block：i.i.d. bootstrap 在 autocorr 樣本（cascade / funding cycle）
    會 over-confident；block 保持 within-block 序列相關性。

    為什麼 seed 為必填無預設：8b / 8c 歷史各用不同 seed（20260515 / 20260518），
    bootstrap 結果隨 seed 確定性變動；強制 caller 顯式傳入歷史 seed 才能維持
    byte-level 結果一致，避免整併時靜默改變任一報告的數值。
    n < block_size 回 None（樣本不足以構成單一 block）。
    """
    clean = [v for v in values if math.isfinite(v)]
    if len(clean) < block_size:
        return None
    rng = random.Random(seed)
    means: list[float] = []
    blocks_per_iter = max(1, math.ceil(len(clean) / block_size))
    for _ in range(iterations):
        sample: list[float] = []
        for _b in range(blocks_per_iter):
            start = rng.randint(0, len(clean) - block_size)
            sample.extend(clean[start:start + block_size])
        means.append(statistics.mean(sample[:len(clean)]))
    means.sort()
    lo = max(0, int(0.025 * iterations))
    hi = min(iterations - 1, int(0.975 * iterations))
    return means[lo], means[hi]


# ── Wilson score interval 95% ──────────────────────────────────────────────


def wilson_ci_95(n: int, n_eff: int) -> tuple[float, float] | None:
    """Wilson score interval 95%（z=1.96），輸入 (n, n_eff)。

    為什麼用 Wilson 而非 normal approx：n_eff / n 比例在小樣本下 normal approx
    over-confident 且邊界可能落在 [0,1] 之外；Wilson 由 p_hat + z²/2n 平移中心、
    denom = 1 + z²/n rescale，確保結果 clamp 在 [0,1]。
    無效輸入（n≤0 / n_eff<0 / n_eff>n / inner<0）回 None 由 caller 判斷分支。

    註：``canary/healthchecks/_common.py`` 另有一個 ``wilson_ci_95(successes,
    total, z)`` 變體（contract 不同：回 (0.0,0.0) 而非 None），服務 [62-65]
    healthcheck package，與本函數契約不相容，刻意不整併（不同 caller 期望）。
    """
    if n <= 0 or n_eff < 0 or n_eff > n:
        return None
    z = 1.96
    p_hat = n_eff / n
    z_sq = z * z
    denom = 1.0 + z_sq / n
    center = (p_hat + z_sq / (2 * n)) / denom
    inner = p_hat * (1.0 - p_hat) / n + z_sq / (4 * n * n)
    if inner < 0.0:
        return None
    margin = z * math.sqrt(inner) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


# ── 時間 bucket / 有效樣本數 ───────────────────────────────────────────────


def day_bucket(signal_ts_ms: int) -> str:
    """ms epoch → UTC YYYY-MM-DD 字串（per-day 集中度與 PBO day-block 用）。"""
    return datetime.fromtimestamp(signal_ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def n_eff_horizon_overlap(n: int, horizon_min: int) -> int:
    """horizon-overlap-only 有效樣本數 n_eff = n / ceil(horizon_min / 5)。

    為什麼 math.ceil 而非整數除：5m bar 取樣下，horizon > 5m 的 forward return
    彼此重疊，n_eff 必須扣 overlap penalty。``horizon_min // 5``（8b 舊版）在
    horizon=6/10/14 時 floor 至 1/2/2 → 漏算 sub-5m overlap，高估 n_eff（MIT
    2026-05-18 dual review §2.1.4 確認的 latent bug）。canonical grid（15/30/60）
    兩式同值（dormant），但 grid expansion 會 regress；故統一採 math.ceil。
    """
    return int(n / max(1, math.ceil(horizon_min / 5)))


# ── Probability of Backtest Overfitting（CSCV，原 _pbo） ───────────────────


def pbo_cscv(
    candidates: Mapping[str, Mapping[str, float]],
    *,
    seed: int,
    max_splits: int = 240,
) -> dict[str, object]:
    """Combinatorially Symmetric Cross-Validation 的 Probability of Backtest
    Overfitting（day-block CSCV）。

    為什麼用 CSCV：標準 K-fold 對 backtest 不適；PBO 看 train-set best cell 在
    test-set 是否落到 below-median，high PBO → strategy 是 overfit。

    為什麼 seed 為必填無預設：當 day combination 數超過 max_splits 會走亂數抽樣
    train-day 組合，結果隨 seed 確定性變動；8b / 8c 歷史各用不同 seed
    （20260516 / 20260518）。強制 caller 傳入歷史 seed 維持結果一致。
    day < 4 或 candidate < 10 / 無 usable split 一律回 value=None + reason。
    """
    days = sorted({day for daily in candidates.values() for day in daily})
    candidate_keys = list(candidates)
    if len(days) < 4 or len(candidate_keys) < 10:
        return {
            "value": None,
            "method": "day_block_cscv",
            "usable_splits": 0,
            "reason": "insufficient_days_or_candidates",
            "day_count": len(days),
            "candidate_count": len(candidate_keys),
        }
    train_size = len(days) // 2
    combo_count = math.comb(len(days), train_size)
    if combo_count <= max_splits:
        combos = list(combinations(days, train_size))
    else:
        rng = random.Random(seed)
        seen: set[tuple[str, ...]] = set()
        combos = []
        attempts = 0
        while len(combos) < max_splits and attempts < max_splits * 20:
            train = tuple(sorted(rng.sample(days, train_size)))
            if train not in seen:
                seen.add(train)
                combos.append(train)
            attempts += 1
    splits = [(set(train), set(days) - set(train)) for train in combos]
    bad = 0
    usable = 0
    for train_days, test_days in splits:
        train_scores: dict[str, float] = {}
        test_scores: dict[str, float] = {}
        for key, daily in candidates.items():
            train_vals = [daily[d] for d in train_days if d in daily]
            test_vals = [daily[d] for d in test_days if d in daily]
            if train_vals and test_vals:
                train_scores[key] = statistics.mean(train_vals)
                test_scores[key] = statistics.mean(test_vals)
        if len(train_scores) < 10 or len(test_scores) < 10:
            continue
        best = max(train_scores, key=train_scores.get)
        ranked = sorted(test_scores.values())
        best_test = test_scores.get(best)
        if best_test is None:
            continue
        median_rank = ranked[len(ranked) // 2]
        bad += int(best_test < median_rank)
        usable += 1
    if usable == 0:
        return {
            "value": None,
            "method": "day_block_cscv",
            "usable_splits": 0,
            "reason": "no_usable_cscv_splits",
            "day_count": len(days),
            "candidate_count": len(candidate_keys),
            "requested_splits": len(splits),
        }
    return {
        "value": bad / usable,
        "method": "day_block_cscv",
        "usable_splits": usable,
        "day_count": len(days),
        "candidate_count": len(candidate_keys),
        "requested_splits": len(splits),
        "train_day_count": train_size,
        "test_day_count": len(days) - train_size,
        "reason": None,
    }
