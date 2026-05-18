"""Pure metrics for W-AUDIT-8c Liquidation Cluster Reaction Stage 0R.

MODULE_NOTE
模塊用途：純粹數學層，計算 liquidation cluster reaction strategy 候選的
Stage 0R promotion-floor metrics。Stage 0R 是 Stage 1 Demo canary 上線前的
最後一個 statistical sanity gate（per spec v0.3 + PA design report
2026-05-18--w_audit_8c_stage_0r_packet_design.md §2.5）。

主要類函數：
  - CandidateCell / SweepGrid：sweep cell 與 grid 的 dataclass。
  - compute_stage0r(rows, ...)：對單一參數組合計算 PASS/RED + 全套 metrics。
  - compute_stage0r_sweep(rows, ...)：4-D sweep mirror 8b z-grid pattern，
    輸出 per-cell × per-tier × per-direction 結果列表。
  - _n_eff_cluster_aware(...)：cluster-aware n_eff（per MIT 8b SHOULD-3
    forward-applicable mandate）；公式 = min(horizon_overlap_n_eff,
    distinct_calendar_days, distinct_60min_clusters)。
  - _single_day_concentration_check / _single_symbol_concentration_check：
    per 8b INJUSDT 87% 集中度教訓的兩個 cap。
  - _both_direction_floor_check：long 與 short trigger rate 至少 0.1%（per
    8b crowded_long_fade dead-trigger trap 教訓）。
  - 4-value verdict：PASS-BOTH / PASS-LONG-ONLY / PASS-SHORT-ONLY / RED
    （per BB 2026-05-18 STRUCTURAL 長空非對稱真實微觀結構結論 — 短方向
    legitimately RED 不應 auto-RED 整 cell）。

依賴：
  - 純 stdlib（math / random / statistics / dataclasses / collections /
    datetime / itertools / typing）。
  - 8b precedent 函數直接複用（DSR / PSR / Wilson CI / block-bootstrap /
    CSCV PBO）；標示 "8b 鏡像" attribution comment。

硬邊界（per srv/CLAUDE.md §四 + spec v0.3）：
  - 純 math layer：無 DB / 無 file IO / 無 live state 修改。
  - 無 Rust 接觸；無 authorization / lease / paper / mainnet enablement 觸碰。
  - rows 為 read-only 輸入；不寫回不變更 row 結構。
  - LOC > 800 警告線：本檔目標 ~1200 LOC，原因為純 math 模塊鏡像 8b 1805
    LOC 結構 + 8c 三大新加法（cluster-aware n_eff、tier × direction 4-value
    verdict、density-floor sweep 6-D）。已先記下 justification。

文件來源：
  - PA design：srv/docs/CCAgentWorkSpace/PA/workspace/reports/
    2026-05-18--w_audit_8c_stage_0r_packet_design.md §2.4 / §2.5 / §3。
  - Spec v0.3：srv/docs/execution_plan/
    2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md。
  - 8b precedent：helper_scripts/reports/w_audit_8b/
    funding_skew_stage0r_metrics.py（mirror exactly per task brief）。
  - MIT 8b RED_FINAL review：srv/docs/CCAgentWorkSpace/MIT/workspace/reports/
    2026-05-18--w_audit_8b_round2_red_final_mit_review.md SHOULD-3
    cluster-aware n_eff formula spec。

無 DB 或 file IO 應寫入此檔；CLI / wrapper 由 8C-S0R-3 在 sibling 模塊
liquidation_cluster_stage0r_report.py 實作（本 worktree 不負責）。
"""

from __future__ import annotations

import math
import random
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from statistics import NormalDist
from typing import Iterable, Mapping, Sequence


# ============================================================================
# 常量與 grid 定義（per PA design §2.2 + spec v0.3 §"Initial Stage 0R grid"）
# ============================================================================

# 8C 的 alpha 識別字串，per PA design §2.4。
ALPHA_SOURCE_ID = "liquidation_cluster_reaction"
STRATEGY_VARIANT = "liquidation_cluster_reaction.v0_3"
SWEEP_STRATEGY_VARIANT = "liquidation_cluster_reaction.v0_3_sweep"

# 雙方向 branch，per BB cor-side mapping。
# long_liquidated  → mean-revert UP   → dir = +1
# short_liquidated → mean-revert DOWN → dir = -1
DIRECTION_BRANCHES = ("long_liquidated", "short_liquidated")

# 密度三層 tier，per spec v0.3 §"Per-symbol density tier stratification"。
# High：≥10 multi-event clusters/7d；Medium：4-9；Low：≤3。
DENSITY_TIERS = ("high", "medium", "low")

# Density-floor sweep 3D 軸，per spec v0.3 §3 density floors。
DEFAULT_K_GRID = (2, 3, 5, 8)                 # min_event_count_5m
DEFAULT_N_USD_GRID = (5_000, 10_000, 25_000, 50_000)  # min_cluster_notional_5m_usd
DEFAULT_M_GRID = (1, 2, 3)                    # min_dominant_event_count

# Magnitude / dominance sweep 4D 軸，per spec v0.3 §"Magnitude / dominance sweep"。
DEFAULT_FLOOR_GRID = (10_000, 25_000, 100_000)      # cluster_notional_floor_usd
DEFAULT_PCT_GRID = (0.90, 0.95, 0.98)               # notional_pct_floor
DEFAULT_SIDE_DOM_GRID = (0.70, 0.80, 0.90)          # side_dominance_floor
DEFAULT_QUIET_GRID = (0, 30, 60)                    # quiet_window_sec

# Horizon sweep，per spec v0.3。
DEFAULT_HORIZON_GRID = (1, 5, 15)
PRIMARY_HORIZON_MIN = 5  # 5m 為 cluster cascade 主 horizon。

# Min stage0r 樣本 cohort，per spec v0.3 §"min symbols"。
MIN_STAGE0R_SYMBOLS = 25

# Per spec v0.3 §"K_total formula"：N_symbols × 11_664；參考 PA design §1.5。
# 11664 = len(K_GRID) × len(N_USD_GRID) × len(M_GRID) × len(FLOOR_GRID) ×
#         len(PCT_GRID) × len(SIDE_DOM_GRID) × len(QUIET_GRID) ×
#         len(HORIZON_GRID) × len(DIRECTION_BRANCHES)
# = 4 × 4 × 3 × 3 × 3 × 3 × 3 × 3 × 2 = 23328（理論上限）
# Spec v0.3 採 11_664（單向 branch 算一次；direction 雙向另計）。
K_GRID_CELLS_PER_SYMBOL = 11_664

# PSR / DSR / PBO 與 8b 同水準的 promotion floor（per PA design §2.5）。
PSR_THRESHOLD = 0.95
DSR_THRESHOLD = 0.95
PBO_THRESHOLD = 0.20

# Per-cell / per-symbol / per-branch / pooled n_eff 各層 floor。
PER_CELL_N_FLOOR = 50          # NEW for 8c：避免 sweep-cell 低樣本污染。
POOLED_N_EFF_FLOOR = 300       # mirror 8b。
SYMBOL_N_EFF_FLOOR = 100       # mirror 8b spec v0.3。
BRANCH_N_EFF_FLOOR = 50        # mirror 8b spec v0.3。

# Both-direction trigger rate 最低門檻（NEW per 8b 教訓）。
BOTH_DIRECTION_FLOOR_RATE = 0.001  # 0.1%；per PA design §2.5。

# 集中度 cap：per 8b INJUSDT 87% 集中教訓。
MAX_DAY_SHARE = 0.25         # spec v0.3 + PA design §2.1。
MAX_SYMBOL_SHARE = 0.40      # NEW for 8c per 8b INJUSDT lesson；PA design §2.5。

# 經濟層 floor。
AVG_NET_FLOOR_BPS = 15.0
COST_EDGE_RATIO_MAX = 0.80
BASELINE_LIFT_FLOOR_BPS = 0.0

# Density-floor efficacy + false-positive rate（per spec v0.3）。
DENSITY_FILTER_EFFICACY_FLOOR = 0.60  # 60% 單/雙事件 bucket 拒絕。
FALSE_POSITIVE_RATE_MAX = 0.40         # ±5 bps band 內 trigger ≤ 40%。
FP_BAND_BPS = 5.0

# Cluster-aware n_eff 之 60min window（per MIT SHOULD-3 + PA design §2.4）。
# 為什麼 60min：liquidation cascade 在 funding window 與 market regime 內
# 高度自相關；60min block 吸收典型 cascade tail，避免 horizon-overlap-only
# 公式高估獨立性（這是 8b RED root cause #3）。
CLUSTER_WINDOW_MIN_DEFAULT = 60

# 樣本最小日數（per spec v0.3 §"sample must span at least 7 calendar days"）。
MIN_SAMPLE_DAYS = 7

# Block-bootstrap 主檢定 block 大小。
# 60min primary（per spec v0.3 §"60m primary block"）/ 4h sensitivity。
PRIMARY_BOOTSTRAP_BLOCK_SIZE = 12   # 12 根 5m bar = 60m。
SENSITIVITY_BOOTSTRAP_BLOCK_SIZE = 48  # 48 根 5m bar = 4h。

# 結算 / cluster 影響窗口（毫秒）。
CLUSTER_WINDOW_MS_DEFAULT = CLUSTER_WINDOW_MIN_DEFAULT * 60_000


# ============================================================================
# Dataclass：sweep cell 識別與 metrics 包裝
# ============================================================================


@dataclass(frozen=True)
class CandidateCell:
    """單一 sweep cell 的識別 key。

    為什麼 frozen：cell key 用於 dict / set indexing；frozen 保證 hashable。
    為什麼分 direction / tier：per PA design §2.5 verdict 必須 per-tier ×
    per-direction 獨立判定。
    """

    symbol: str
    tier: str             # high / medium / low（per density classification）
    direction: str        # long_liquidated / short_liquidated
    k_event_count: int    # min_event_count_5m
    n_usd: int            # min_cluster_notional_5m_usd
    m_dominant: int       # min_dominant_event_count
    floor_usd: int        # cluster_notional_floor_usd
    side_dom: float       # side_dominance_floor
    quiet_sec: int        # quiet_window_sec
    horizon_min: int      # forward_return_horizon_min

    def label(self) -> str:
        return (
            f"{self.symbol}|tier={self.tier}|dir={self.direction}|"
            f"K={self.k_event_count}|N={self.n_usd}|M={self.m_dominant}|"
            f"floor={self.floor_usd}|dom={self.side_dom:g}|"
            f"quiet={self.quiet_sec}|h={self.horizon_min}"
        )


# ============================================================================
# 安全 cast helpers（8b 鏡像 — 為什麼複製：8b 用同一公式，純 stdlib，
# 避免跨模塊 import 增加 IPC / 部署複雜度）
# ============================================================================


def _safe_float(value: object) -> float | None:
    """Cast to finite float or None；NaN / Inf → None。

    為什麼 fail-closed：metrics 計算中 NaN propagation 會污染 PSR/DSR/CI；
    上游一律返回 None 強迫 caller 顯式處理。
    """
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _safe_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _normal_cdf(x: float) -> float:
    return NormalDist().cdf(x)


# ============================================================================
# 統計分布輔助（8b 鏡像 — skew / kurtosis；用於 PSR Bailey & López de Prado）
# ============================================================================


def _skew(values: Sequence[float]) -> float | None:
    if len(values) < 3:
        return None
    mean = statistics.mean(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    if var <= 0:
        return None
    sd = math.sqrt(var)
    return sum(((v - mean) / sd) ** 3 for v in values) / len(values)


def _kurtosis(values: Sequence[float]) -> float | None:
    if len(values) < 4:
        return None
    mean = statistics.mean(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    if var <= 0:
        return None
    sd = math.sqrt(var)
    return sum(((v - mean) / sd) ** 4 for v in values) / len(values)


# ============================================================================
# PSR / DSR（8b 鏡像 attribution — Bailey & López de Prado 2014 公式）
# ============================================================================


def psr_bailey_ldp(values: Sequence[float], sr_benchmark: float = 0.0) -> float | None:
    """Probabilistic Sharpe Ratio (PSR) per Bailey & López de Prado 2014。

    為什麼用 PSR 而非 Sharpe：textbook Sharpe 假設 normal returns，liquidation
    cluster return 顯然 heavy-tailed + skewed；PSR 顯式調 skew / kurtosis。

    sr_benchmark = 0.0 → PSR(0)；> 0 → PSR(sr_benchmark)；
    後者用於 DSR：sr_benchmark = √(2 ln K_total)。
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
    sr_benchmark = √(2 × ln K_total) 是 expected max Sharpe from random
    trials assuming Gaussian。
    """
    if k_total <= 1:
        return None
    sr_benchmark = math.sqrt(2.0 * math.log(k_total))
    return psr_bailey_ldp(values, sr_benchmark=sr_benchmark)


# ============================================================================
# Block bootstrap CI（8b 鏡像 — 抗 autocorrelation 的 95% bootstrap lower）
# ============================================================================


def block_bootstrap_ci(
    values: Sequence[float],
    *,
    block_size: int = PRIMARY_BOOTSTRAP_BLOCK_SIZE,
    iterations: int = 400,
    seed: int = 20260518,
) -> tuple[float, float] | None:
    """Stationary block bootstrap 95% CI。

    為什麼 block：i.i.d. bootstrap 在 autocorr 樣本 (liquidation cascade)
    over-confident；block 保持 within-block 序列相關性。
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


# ============================================================================
# Wilson CI（8b 鏡像 — 用於 trigger-rate 比例的小樣本 95% lower bound）
# ============================================================================


def wilson_ci_95(n: int, n_eff: int) -> tuple[float, float] | None:
    """Wilson score interval 95%。

    為什麼用 Wilson 而非 normal approx：n_eff / n 比例在小樣本下 normal
    approx over-confident；Wilson 對 boundary (p_hat→0 或 →1) 更穩定。
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


# ============================================================================
# Cluster-aware n_eff（**8c NEW per MIT 8b SHOULD-3 forward-applicable**）
# ============================================================================


def _n_eff_horizon_overlap(n: int, horizon_min: int) -> int:
    """8b 鏡像：horizon-overlap-only n_eff。

    為什麼保留：作為 cluster-aware 公式的 input 之一（min 之三）；
    亦保留 8b 同公式的 backward compatibility。
    """
    # max(1, horizon_min // 5)：horizon=5 → 1（no overlap），horizon=30 → 6（6:1）
    return int(n / max(1, horizon_min // 5))


def _n_eff_cluster_aware(
    triggers: Sequence[Mapping[str, object]],
    *,
    horizon_min: int = PRIMARY_HORIZON_MIN,
    cluster_window_min: int = CLUSTER_WINDOW_MIN_DEFAULT,
) -> dict[str, int]:
    """Cluster-aware effective sample size for liquidation cluster regime。

    **這是 8b RED root cause #3 的修法（per MIT review SHOULD-3）。**

    為什麼 cluster-aware：
      - 8b 用 _n_eff = n / (horizon_min // 5) 只調 horizon 重疊。
      - 但 liquidation cascade 在 60min funding window + market regime 內
        高度自相關（INJUSDT 87% 集中於 single calendar day 是極端例）。
      - 真實 effective n 受三個 ceiling 同時限制：
          (1) horizon overlap：horizon // 5 個 5m bar 為一獨立單位。
          (2) distinct calendar days：每個 calendar day 為一獨立 regime 樣本。
          (3) distinct 60min clusters：同一 cluster window 內視為 1 個事件。

    公式（per MIT SHOULD-3 提案）：
      n_eff_cluster = min(
          n_eff_horizon_overlap(n, horizon_min),
          distinct_calendar_days,
          distinct_60min_clusters,
      )

    對 INJUSDT z=1.2 cluster 案例（8b RED）：
      n = 42, horizon = 30m → n_eff_horizon = 7
      distinct days = 7
      distinct 60min clusters ≈ 10
      ⇒ n_eff_cluster = min(7, 7, 10) = 7（此 cell 三方一致；其他 cell 可能差別大）。

    返回 dict 含 raw 三方數值，便於 MIT review 看 penalty rate。
    """
    n = len(triggers)
    if n == 0:
        return {
            "n_raw": 0,
            "n_eff_horizon": 0,
            "distinct_days": 0,
            "distinct_60min_clusters": 0,
            "n_eff_cluster": 0,
            "penalty_rate": 0.0,
        }

    # 三方計算。
    n_eff_horizon = _n_eff_horizon_overlap(n, horizon_min)

    days = set()
    for t in triggers:
        ts_ms = _safe_int(t.get("signal_ts_ms"))
        if ts_ms is None:
            continue
        days.add(datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d"))
    distinct_days = len(days)

    # Distinct 60min clusters：按 (symbol, direction) 排序 triggers，
    # 連續 60min 內視為同一 cluster。
    sorted_triggers = sorted(
        (t for t in triggers if _safe_int(t.get("signal_ts_ms")) is not None),
        key=lambda x: (
            str(x.get("symbol") or ""),
            str(x.get("direction") or ""),
            int(x.get("signal_ts_ms") or 0),
        ),
    )
    window_ms = cluster_window_min * 60_000
    distinct_clusters = 0
    last_key: tuple[str, str] | None = None
    last_ts_ms: int | None = None
    for t in sorted_triggers:
        key = (str(t.get("symbol") or ""), str(t.get("direction") or ""))
        ts_ms = int(t.get("signal_ts_ms") or 0)
        if last_key != key or last_ts_ms is None or (ts_ms - last_ts_ms) > window_ms:
            distinct_clusters += 1
            last_key = key
            last_ts_ms = ts_ms
        # 同 cluster 內保持 last_ts_ms 不變；新事件並不啟 new cluster
        # 直到超過 60min 才算 cluster 結束。

    n_eff_cluster = min(n_eff_horizon, distinct_days, distinct_clusters)
    penalty_rate = 1.0 - (n_eff_cluster / n) if n > 0 else 0.0

    return {
        "n_raw": n,
        "n_eff_horizon": n_eff_horizon,
        "distinct_days": distinct_days,
        "distinct_60min_clusters": distinct_clusters,
        "n_eff_cluster": n_eff_cluster,
        "penalty_rate": penalty_rate,
    }


# ============================================================================
# Concentration checks（NEW for 8c per 8b INJUSDT 87% lesson）
# ============================================================================


def _day_bucket(signal_ts_ms: int) -> str:
    """Convert ms epoch to UTC YYYY-MM-DD string；8b 鏡像。"""
    return datetime.fromtimestamp(signal_ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _single_day_concentration_check(
    triggers: Sequence[Mapping[str, object]],
    *,
    cap: float = MAX_DAY_SHARE,
) -> dict[str, object]:
    """Check 單一日 contribution share ≤ cap。

    為什麼 cap = 0.25 預設：spec v0.3 §"no single day may contribute more
    than 25% of eligible clusters"。為什麼需要這個 check：8b INJUSDT 87%
    集中於 2026-05-13 single day → effective independent observations
    跌至 ~2-3 calendar days；同樣 risk 在 8c liquidation cascade regime
    更嚴重（cascades 本質 cluster on big-move days）。

    返回 (max_day_share, fail_reason_if_breach)；fail_reason = None 表示通過。
    """
    n = len(triggers)
    if n == 0:
        return {
            "max_day_share": 0.0,
            "max_day": None,
            "distinct_days": 0,
            "passed": True,
            "fail_reason": None,
        }
    days = Counter()
    for t in triggers:
        ts_ms = _safe_int(t.get("signal_ts_ms"))
        if ts_ms is None:
            continue
        days[_day_bucket(ts_ms)] += 1
    if not days:
        return {
            "max_day_share": 0.0,
            "max_day": None,
            "distinct_days": 0,
            "passed": True,
            "fail_reason": "no_valid_ts",
        }
    max_day, max_count = max(days.items(), key=lambda kv: kv[1])
    share = max_count / n
    passed = share <= cap
    return {
        "max_day_share": share,
        "max_day": max_day,
        "distinct_days": len(days),
        "passed": passed,
        "fail_reason": None if passed else f"single-day share {share:.1%} > {cap:.0%}",
    }


def _single_symbol_concentration_check(
    triggers: Sequence[Mapping[str, object]],
    *,
    cap: float = MAX_SYMBOL_SHARE,
) -> dict[str, object]:
    """Check 單一 symbol contribution share ≤ cap（NEW for 8c）。

    為什麼 cap = 0.40 預設：per PA design §2.5 + 8b INJUSDT 87% lesson 之
    pooled n_eff collapse 教訓的反 pattern。spec v0.3 未明示 single-symbol
    cap，但 PA design §2.5 為 8c 新加；MIT 對 8b RED 的 INJUSDT verdict
    印證此為 effective n collapse 的關鍵 root cause。

    返回 (max_symbol_share, fail_reason_if_breach)。
    """
    n = len(triggers)
    if n == 0:
        return {
            "max_symbol_share": 0.0,
            "max_symbol": None,
            "distinct_symbols": 0,
            "passed": True,
            "fail_reason": None,
        }
    symbols = Counter()
    for t in triggers:
        sym = str(t.get("symbol") or "")
        if sym:
            symbols[sym] += 1
    if not symbols:
        return {
            "max_symbol_share": 0.0,
            "max_symbol": None,
            "distinct_symbols": 0,
            "passed": True,
            "fail_reason": "no_valid_symbol",
        }
    max_sym, max_count = max(symbols.items(), key=lambda kv: kv[1])
    share = max_count / n
    passed = share <= cap
    return {
        "max_symbol_share": share,
        "max_symbol": max_sym,
        "distinct_symbols": len(symbols),
        "passed": passed,
        "fail_reason": None if passed else f"single-symbol share {share:.1%} > {cap:.0%}",
    }


# ============================================================================
# Both-direction trigger rate floor（NEW per 8b crowded_long_fade lesson）
# ============================================================================


def _both_direction_floor_check(
    triggers: Sequence[Mapping[str, object]],
    total_bucket_count: int,
    *,
    floor_rate: float = BOTH_DIRECTION_FLOOR_RATE,
) -> dict[str, object]:
    """Check long 與 short trigger rate 至少 floor_rate。

    為什麼 floor = 0.1% 預設：per PA design §2.5 + 8b 教訓：crowded_long_fade
    branch 在 8b 是 dead trigger（z>=+1.5 區間僅 0.27% of total）→ 整 branch
    n=0 直接 RED 無意義。8c 雙方向先驗 floor check，dead 方向先 retire；
    剩餘方向 verdict 仍可 PASS-LONG-ONLY / PASS-SHORT-ONLY（per task brief）。

    為什麼分母用 total_bucket_count（不是 trigger 總 n）：trigger rate 是
    "fraction of all 5m buckets that triggered"，不是 "fraction of triggers
    that were long"；後者天生 = 1 因 trigger 必有方向。
    """
    if total_bucket_count <= 0:
        return {
            "long_trigger_rate": 0.0,
            "short_trigger_rate": 0.0,
            "long_passed": False,
            "short_passed": False,
            "both_passed": False,
            "fail_reason": "no_buckets",
        }
    long_count = sum(1 for t in triggers if str(t.get("direction")) == "long_liquidated")
    short_count = sum(1 for t in triggers if str(t.get("direction")) == "short_liquidated")
    long_rate = long_count / total_bucket_count
    short_rate = short_count / total_bucket_count
    long_passed = long_rate >= floor_rate
    short_passed = short_rate >= floor_rate
    both_passed = long_passed and short_passed

    if both_passed:
        fail_reason = None
    elif not long_passed and not short_passed:
        fail_reason = (
            f"both direction dead: long {long_rate:.4%} < {floor_rate:.1%} "
            f"AND short {short_rate:.4%} < {floor_rate:.1%}"
        )
    elif not long_passed:
        fail_reason = f"long-direction dead: {long_rate:.4%} < {floor_rate:.1%}"
    else:
        fail_reason = f"short-direction dead: {short_rate:.4%} < {floor_rate:.1%}"

    return {
        "long_trigger_rate": long_rate,
        "short_trigger_rate": short_rate,
        "long_passed": long_passed,
        "short_passed": short_passed,
        "both_passed": both_passed,
        "long_count": long_count,
        "short_count": short_count,
        "total_bucket_count": total_bucket_count,
        "fail_reason": fail_reason,
    }


# ============================================================================
# Density floor efficacy / False positive rate（per spec v0.3）
# ============================================================================


def _density_floor_efficacy(
    raw_count: int,
    after_k: int,
    after_n: int,
    after_m: int,
) -> dict[str, object]:
    """Density-floor filter efficacy ratio。

    為什麼門檻 ≥ 60%：spec v0.3 §"density-floor filter must remove ≥ 60%
    of single/double-event 5m buckets" — 證 floor 在做事而非 rubber-stamp。

    raw_count 為 raw 5m buckets with any event 數；after_k/n/m 為各 floor
    過濾後剩餘數。最終 efficacy = 1 - after_m / raw_count（總拒絕比例）。
    """
    if raw_count <= 0:
        return {
            "raw_count": 0,
            "after_k": 0,
            "after_n": 0,
            "after_m": 0,
            "efficacy": 0.0,
            "passed": False,
            "fail_reason": "no_raw_buckets",
        }
    efficacy = 1.0 - (after_m / raw_count)
    passed = efficacy >= DENSITY_FILTER_EFFICACY_FLOOR
    return {
        "raw_count": raw_count,
        "after_k": after_k,
        "after_n": after_n,
        "after_m": after_m,
        "efficacy": efficacy,
        "passed": passed,
        "fail_reason": None if passed else (
            f"density-floor efficacy {efficacy:.1%} < {DENSITY_FILTER_EFFICACY_FLOOR:.0%}"
        ),
    }


def _false_positive_rate(
    triggers: Sequence[Mapping[str, object]],
    *,
    bps_band: float = FP_BAND_BPS,
    cost_bps: float = 12.0,
) -> dict[str, object]:
    """False positive rate：|net_bps| ≤ bps_band 視為 noise trigger。

    為什麼門檻 ≤ 40%：spec v0.3 §"false-positive rate (forward return within
    ±5 bps after fee/slippage) ≤ 40% in winning grid cell" — 證 trigger
    非 dominated by noise events。
    """
    n = len(triggers)
    if n == 0:
        return {
            "n_total": 0,
            "n_fp": 0,
            "fp_rate": 0.0,
            "passed": True,
            "fail_reason": None,
        }
    n_fp = sum(
        1 for t in triggers
        if (val := _safe_float(t.get("net_bps"))) is not None
        and abs(val) <= bps_band
    )
    fp_rate = n_fp / n
    passed = fp_rate <= FALSE_POSITIVE_RATE_MAX
    return {
        "n_total": n,
        "n_fp": n_fp,
        "fp_rate": fp_rate,
        "passed": passed,
        "fail_reason": None if passed else (
            f"false-positive rate {fp_rate:.1%} > {FALSE_POSITIVE_RATE_MAX:.0%}"
        ),
    }


# ============================================================================
# CSCV PBO（8b 鏡像）
# ============================================================================


def _pbo(candidates: Mapping[str, Mapping[str, float]], *, max_splits: int = 240) -> dict[str, object]:
    """Combinatorially Symmetric Cross-Validation Probability of Backtest Overfitting。

    為什麼用 CSCV：標準 K-fold 對 backtest 不適；PBO 看 train-set best 在
    test-set 是否 below median；high PBO → strategy 是 overfit。
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
        rng = random.Random(20260518)
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


# ============================================================================
# Tier classification helpers
# ============================================================================


def _classify_tier(distinct_multi_event_clusters_7d: int) -> str:
    """Per spec v0.3 §"Per-symbol density tier stratification"。

    High：≥10 multi-event clusters/7d。
    Medium：4-9。
    Low：≤3。

    為什麼這個分層：density 結構決定 promotion 的 statistical power baseline；
    low-density tier 在 7d sample 不可能達 n_eff ≥ 50 per active branch 而被
    spec 預期 fail（這不是 bug 而是 spec design）。
    """
    if distinct_multi_event_clusters_7d >= 10:
        return "high"
    if distinct_multi_event_clusters_7d >= 4:
        return "medium"
    return "low"


def _classify_symbols_by_tier(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, str]:
    """Build symbol → tier map based on distinct multi-event cluster count。

    輸入 rows 為 SQL CTE 已過 density floor 後的 trigger candidate rows
    （含 symbol + signal_ts_ms 即可）；輸出 dict[symbol → tier]。

    "multi-event cluster" 指該 row 已通過 density floor，即代表一個 cluster
    candidate。distinct_clusters_7d = len(rows with that symbol)。
    """
    counts: Counter = Counter()
    for r in rows:
        sym = str(r.get("symbol") or "")
        if sym:
            counts[sym] += 1
    return {sym: _classify_tier(cnt) for sym, cnt in counts.items()}


# ============================================================================
# Signal row extraction（8c 改寫 — 從 SQL panel row 提 trigger 候選）
# ============================================================================


def _extract_trigger_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    k_event_count: int,
    n_usd: int,
    m_dominant: int,
    floor_usd: int,
    side_dom: float,
    quiet_sec: int,
    horizon_min: int,
    cost_bps: float,
) -> list[dict[str, object]]:
    """從 panel rows 提通過 density + magnitude + dominance + quiet 門檻的
    trigger 候選，並計算 gross/net bps。

    輸入 rows 假設 SQL CTE 5 之 final_signals 結果（per PA design §2.3），
    每 row 至少含：
      symbol / bucket_5m_epoch / bucket_end_ts_ms / dominant_side /
      expected_dir / cluster_notional_5m / event_count_5m /
      dominant_event_count / side_dominance_ratio / notional_pct_24h /
      entry_mid / exit_mid / gross_bps / net_bps / day_bucket。

    為什麼 net_bps 由 caller 預計算：保持 SQL CTE 與 Python 的 cost model
    一致；本函數重新驗 cost_bps 是否被 caller 套用，並可重 override。
    """
    out: list[dict[str, object]] = []
    for row in rows:
        # 過 density floor。
        ec = _safe_int(row.get("event_count_5m"))
        cn = _safe_float(row.get("cluster_notional_5m"))
        dec = _safe_int(row.get("dominant_event_count"))
        if ec is None or cn is None or dec is None:
            continue
        if ec < k_event_count or cn < n_usd or dec < m_dominant:
            continue
        # 過 magnitude floor。
        if cn < floor_usd:
            continue
        # 過 side dominance floor。
        sdr = _safe_float(row.get("side_dominance_ratio"))
        if sdr is None or sdr < side_dom:
            continue
        # quiet window（SQL CTE 已 join quiet_sec 後的 entry_mid；Python 層
        # 信任 caller）。
        dominant_side = str(row.get("dominant_side") or "")
        if dominant_side not in ("long_liquidated", "short_liquidated"):
            continue
        expected_dir = _safe_int(row.get("expected_dir"))
        if expected_dir not in (-1, +1):
            continue
        # 計算 gross / net bps（caller 可能已 pre-compute；本函數重算保
        # cost model 一致）。
        entry_mid = _safe_float(row.get("entry_mid"))
        exit_mid = _safe_float(row.get("exit_mid"))
        if entry_mid is None or exit_mid is None or entry_mid <= 0 or exit_mid <= 0:
            continue
        gross_bps = 10000.0 * expected_dir * (exit_mid - entry_mid) / entry_mid
        net_bps = gross_bps - cost_bps
        # signal_ts_ms（用 bucket_end_ts_ms；ms 為 caller convert 過）。
        signal_ts_ms = _safe_int(row.get("bucket_end_ts_ms"))
        if signal_ts_ms is None:
            continue
        out.append({
            "symbol": str(row.get("symbol") or ""),
            "signal_ts_ms": signal_ts_ms,
            "direction": dominant_side,
            "expected_dir": expected_dir,
            "cluster_notional_5m": cn,
            "event_count_5m": ec,
            "dominant_event_count": dec,
            "side_dominance_ratio": sdr,
            "notional_pct_24h": _safe_float(row.get("notional_pct_24h")),
            "entry_mid": entry_mid,
            "exit_mid": exit_mid,
            "gross_bps": gross_bps,
            "net_bps": net_bps,
            "horizon_min": horizon_min,
            "quiet_sec": quiet_sec,
        })
    return out


# ============================================================================
# Verdict derivation — 4-value (PASS-BOTH/LONG-ONLY/SHORT-ONLY/RED)
# ============================================================================


def _derive_pass_verdict(
    *,
    long_branch_passed: bool,
    short_branch_passed: bool,
    both_direction_check: Mapping[str, object],
    other_red_reasons: Sequence[str],
) -> tuple[str, list[str]]:
    """4-value verdict 推導（per BB STRUCTURAL 2026-05-18 + task brief）。

    為什麼 4-value：BB 2026-05-18 對 demo testnet long-liq 8-12× skew 的
    verdict = STRUCTURAL (real microstructure)，非 demo bias。即 short-side
    direction legitimately RED 不等於 cell RED；spec v0.3 §"per-tier
    independent promotion" 已暗示，task brief 形式化為 4 verdict 值。

    決策樹：
      - 若有任何 non-direction RED reason（e.g. DSR fail / PBO fail）→ RED。
      - 若 both 方向都過 → PASS-BOTH。
      - 若僅 long 過 → PASS-LONG-ONLY。
      - 若僅 short 過 → PASS-SHORT-ONLY。
      - 若 both 都不過 → RED。
    """
    reasons: list[str] = list(other_red_reasons)

    # 任一 hard fail（如 DSR / PBO / sample window）→ 直接 RED。
    if reasons:
        return "RED", reasons

    if long_branch_passed and short_branch_passed:
        return "PASS-BOTH", []

    if long_branch_passed and not short_branch_passed:
        reason = both_direction_check.get("fail_reason") or "short-direction failed promotion floor"
        return "PASS-LONG-ONLY", [str(reason)]

    if not long_branch_passed and short_branch_passed:
        reason = both_direction_check.get("fail_reason") or "long-direction failed promotion floor"
        return "PASS-SHORT-ONLY", [str(reason)]

    reason = both_direction_check.get("fail_reason") or "both directions failed promotion floor"
    return "RED", [str(reason)]


# ============================================================================
# Core API：compute_stage0r — 單一參數組合計算
# ============================================================================


def compute_stage0r(
    rows: Sequence[Mapping[str, object]],
    *,
    cost_bps: float = 12.0,
    horizon_min: int = PRIMARY_HORIZON_MIN,
    k_event_count: int = 3,
    n_usd: int = 10_000,
    m_dominant: int = 2,
    floor_usd: int = 10_000,
    side_dom: float = 0.80,
    quiet_sec: int = 30,
    k_prior: int = 0,
    n_min_per_cell: int = PER_CELL_N_FLOOR,
    n_eff_min_pooled: int = POOLED_N_EFF_FLOOR,
    single_day_concentration_cap: float = MAX_DAY_SHARE,
    single_symbol_concentration_cap: float = MAX_SYMBOL_SHARE,
    both_direction_floor_rate: float = BOTH_DIRECTION_FLOOR_RATE,
    bootstrap_iters: int = 400,
    cluster_window_min: int = CLUSTER_WINDOW_MIN_DEFAULT,
    rng_seed: int = 20260518,
    bb_demo_bias_confirmed: bool = True,
    total_bucket_count: int | None = None,
    raw_5m_bucket_count: int | None = None,
    after_k_count: int | None = None,
    after_n_count: int | None = None,
    after_m_count: int | None = None,
) -> dict[str, object]:
    """Compute Stage 0R full-cell metrics + 4-value verdict。

    Input rows: SQL CTE 5 final_signals 結果（per PA design §2.3）。

    bb_demo_bias_confirmed：True 表 BB 已 STRUCTURAL clear（2026-05-18 完成）。
    False 表 BB 尚未 clear long-liq skew 是否真 microstructure；本 module
    refuse 計算並回 explicit RED reason（per task brief §"RED Risk #1"）。

    total_bucket_count：所有 5m bucket 數（不論是否 trigger）；用於計算
    long/short trigger rate 分母。Caller 從 SQL CTE 1 raw_buckets 取 count(*)
    傳入。若 None，fallback 用 len(rows)（偏保守但仍有意義）。

    raw_5m_bucket_count / after_k/n/m_count：density-floor efficacy 用；
    若 None，fallback skip 該 check。

    返回 dict 含：
      pass: 4-value verdict（PASS-BOTH/LONG-ONLY/SHORT-ONLY/RED）。
      pass_reasons: list[str]，verdict 為 RED 時的失敗原因。
      n_per_cell, pooled_n, pooled_n_eff, ...，全套 metrics。
      tombstone_risk: dict mark BB clear / cluster penalty / cost 三檢查狀態。
    """
    # === BB demo-bias gate (RED Risk #1) ===
    if not bb_demo_bias_confirmed:
        return {
            "strategy_variant": STRATEGY_VARIANT,
            "alpha_source_id": ALPHA_SOURCE_ID,
            "pass": "RED",
            "pass_reasons": [
                "bb_demo_bias_not_confirmed: refuse Stage 0R until BB clears "
                "demo testnet long-liquidation skew is real microstructure"
            ],
            "tombstone_risk": {
                "demo_bias_gate": "BB_NOT_CLEARED",
                "cluster_n_eff_penalty": "skipped",
                "cost_realism_gate": "skipped",
            },
            "n_per_cell": 0,
            "pooled_n": 0,
            "pooled_n_eff": 0,
        }

    # === 抽 trigger candidates ===
    triggers = _extract_trigger_rows(
        rows,
        k_event_count=k_event_count,
        n_usd=n_usd,
        m_dominant=m_dominant,
        floor_usd=floor_usd,
        side_dom=side_dom,
        quiet_sec=quiet_sec,
        horizon_min=horizon_min,
        cost_bps=cost_bps,
    )

    n_per_cell = len(triggers)
    if total_bucket_count is None:
        total_bucket_count = len(rows)

    # === Cluster-aware n_eff ===
    cluster_neff = _n_eff_cluster_aware(
        triggers,
        horizon_min=horizon_min,
        cluster_window_min=cluster_window_min,
    )
    pooled_n_eff = cluster_neff["n_eff_cluster"]

    # === Net bps + bootstrap CI + PSR + DSR + PBO ===
    net_values = [float(t["net_bps"]) for t in triggers if _safe_float(t.get("net_bps")) is not None]
    gross_values = [float(t["gross_bps"]) for t in triggers if _safe_float(t.get("gross_bps")) is not None]
    avg_net = statistics.mean(net_values) if net_values else None
    avg_gross = statistics.mean(gross_values) if gross_values else None

    bootstrap_ci_60m = block_bootstrap_ci(
        net_values, block_size=PRIMARY_BOOTSTRAP_BLOCK_SIZE,
        iterations=bootstrap_iters, seed=rng_seed,
    )
    bootstrap_ci_4h = block_bootstrap_ci(
        net_values, block_size=SENSITIVITY_BOOTSTRAP_BLOCK_SIZE,
        iterations=bootstrap_iters, seed=rng_seed,
    )

    psr_value = psr_bailey_ldp(net_values)

    # K_total = K_prior + K_new；K_new = N_symbols × 11_664。
    symbols_in_panel = sorted({str(t.get("symbol") or "") for t in triggers if t.get("symbol")})
    n_symbols = len(symbols_in_panel)
    k_new = max(MIN_STAGE0R_SYMBOLS, n_symbols) * K_GRID_CELLS_PER_SYMBOL
    k_total = int(k_prior) + k_new
    dsr_value = dsr_with_k(net_values, k_total)

    # PBO：build per-day score map for current cell only（CSCV 需 ≥ 10 candidates；
    # 本 cell 只計算 self-coverage）。
    daily_for_pbo: dict[str, dict[str, float]] = {}
    daily_returns: defaultdict = defaultdict(list)
    for t in triggers:
        ts_ms = _safe_int(t.get("signal_ts_ms"))
        nb = _safe_float(t.get("net_bps"))
        if ts_ms is None or nb is None:
            continue
        daily_returns[_day_bucket(ts_ms)].append(nb)
    if daily_returns:
        cell_label = f"K{k_event_count}_N{n_usd}_M{m_dominant}_h{horizon_min}"
        daily_for_pbo[cell_label] = {
            day: statistics.mean(vals) for day, vals in daily_returns.items()
        }
    pbo_meta = _pbo(daily_for_pbo)

    # === Concentration checks ===
    day_check = _single_day_concentration_check(triggers, cap=single_day_concentration_cap)
    symbol_check = _single_symbol_concentration_check(triggers, cap=single_symbol_concentration_cap)

    # === Both-direction floor ===
    direction_check = _both_direction_floor_check(
        triggers, total_bucket_count, floor_rate=both_direction_floor_rate,
    )

    # === Density-floor efficacy（optional：caller 傳 raw/after_k/n/m count）===
    if all(v is not None for v in (raw_5m_bucket_count, after_k_count, after_n_count, after_m_count)):
        density_efficacy = _density_floor_efficacy(
            int(raw_5m_bucket_count or 0),
            int(after_k_count or 0),
            int(after_n_count or 0),
            int(after_m_count or 0),
        )
    else:
        density_efficacy = {
            "passed": True,  # 不可判定 → 不阻塞；標 SKIPPED
            "fail_reason": None,
            "reason_for_skip": "raw/after_k/n/m count not provided by caller",
        }

    # === False positive rate ===
    fp_check = _false_positive_rate(triggers, bps_band=FP_BAND_BPS, cost_bps=cost_bps)

    # === Cost edge ratio ===
    cost_edge_ratio = (
        abs(cost_bps) / abs(avg_gross)
        if avg_gross is not None and avg_gross != 0 else None
    )
    cost_check_passed = cost_edge_ratio is not None and cost_edge_ratio < COST_EDGE_RATIO_MAX

    # === Sample window check（≥ 7 calendar days）===
    distinct_days = cluster_neff["distinct_days"]
    sample_window_passed = distinct_days >= MIN_SAMPLE_DAYS

    # === 收集 RED reasons（hard failures，非 direction-side）===
    other_red_reasons: list[str] = []

    if n_per_cell < n_min_per_cell:
        other_red_reasons.append(f"n_per_cell {n_per_cell} < {n_min_per_cell}")

    if pooled_n_eff < n_eff_min_pooled:
        other_red_reasons.append(f"pooled_n_eff_cluster {pooled_n_eff} < {n_eff_min_pooled}")

    if not sample_window_passed:
        other_red_reasons.append(f"distinct_days {distinct_days} < {MIN_SAMPLE_DAYS}")

    if not day_check["passed"]:
        other_red_reasons.append(str(day_check["fail_reason"]))

    if not symbol_check["passed"]:
        other_red_reasons.append(str(symbol_check["fail_reason"]))

    if avg_net is None or avg_net < AVG_NET_FLOOR_BPS:
        other_red_reasons.append(f"avg_net_bps {avg_net} < {AVG_NET_FLOOR_BPS}")

    if psr_value is None or psr_value < PSR_THRESHOLD:
        other_red_reasons.append(f"PSR(0) {psr_value} < {PSR_THRESHOLD}")

    if dsr_value is None or dsr_value < DSR_THRESHOLD:
        other_red_reasons.append(f"DSR {dsr_value} < {DSR_THRESHOLD}")

    # Auto-RED：DSR=0 AND PBO>0.5（per 8b RED_FINAL lesson hard rule，PA §2.5）。
    pbo_value = _safe_float(pbo_meta.get("value"))
    if dsr_value == 0.0 and pbo_value is not None and pbo_value > 0.5:
        other_red_reasons.append("AUTO-RED: DSR=0 AND PBO>0.5 (8b RED_FINAL lesson)")
    elif pbo_value is not None and pbo_value > PBO_THRESHOLD:
        other_red_reasons.append(f"PBO {pbo_value} > {PBO_THRESHOLD}")

    if bootstrap_ci_60m is not None and bootstrap_ci_60m[0] <= 0:
        other_red_reasons.append("60m bootstrap CI lower <= 0")

    if not cost_check_passed:
        other_red_reasons.append(
            f"cost_edge_ratio {cost_edge_ratio} >= {COST_EDGE_RATIO_MAX}"
        )

    if not density_efficacy.get("passed"):
        fr = density_efficacy.get("fail_reason")
        if fr:
            other_red_reasons.append(str(fr))

    if not fp_check["passed"]:
        other_red_reasons.append(str(fp_check["fail_reason"]))

    # === Per-direction branch evaluation ===
    long_triggers = [t for t in triggers if t.get("direction") == "long_liquidated"]
    short_triggers = [t for t in triggers if t.get("direction") == "short_liquidated"]

    def _branch_eval(branch_triggers: Sequence[Mapping[str, object]]) -> dict[str, object]:
        if not branch_triggers:
            return {
                "n": 0,
                "n_eff_cluster": 0,
                "avg_net_bps": None,
                "passed": False,
                "fail_reason": "no_triggers",
            }
        nv = [float(t["net_bps"]) for t in branch_triggers
              if _safe_float(t.get("net_bps")) is not None]
        n_b = len(branch_triggers)
        cluster_b = _n_eff_cluster_aware(
            branch_triggers, horizon_min=horizon_min, cluster_window_min=cluster_window_min,
        )
        n_eff_b = cluster_b["n_eff_cluster"]
        avg_b = statistics.mean(nv) if nv else None
        # branch-level PASS：n_eff ≥ branch floor + avg_net ≥ floor。
        branch_passed = (
            n_eff_b >= BRANCH_N_EFF_FLOOR
            and avg_b is not None
            and avg_b >= AVG_NET_FLOOR_BPS
        )
        reasons = []
        if n_eff_b < BRANCH_N_EFF_FLOOR:
            reasons.append(f"branch n_eff_cluster {n_eff_b} < {BRANCH_N_EFF_FLOOR}")
        if avg_b is None or avg_b < AVG_NET_FLOOR_BPS:
            reasons.append(f"branch avg_net_bps {avg_b} < {AVG_NET_FLOOR_BPS}")
        return {
            "n": n_b,
            "n_eff_cluster": n_eff_b,
            "n_eff_cluster_breakdown": cluster_b,
            "avg_net_bps": avg_b,
            "passed": branch_passed,
            "fail_reason": "; ".join(reasons) if reasons else None,
        }

    long_branch = _branch_eval(long_triggers)
    short_branch = _branch_eval(short_triggers)

    # Both-direction floor failure（trigger rate）合併入 branch verdict。
    long_passed = bool(long_branch["passed"]) and bool(direction_check["long_passed"])
    short_passed = bool(short_branch["passed"]) and bool(direction_check["short_passed"])

    # === Verdict ===
    verdict, verdict_reasons = _derive_pass_verdict(
        long_branch_passed=long_passed,
        short_branch_passed=short_passed,
        both_direction_check=direction_check,
        other_red_reasons=other_red_reasons,
    )

    # === Tombstone risk diagnostic（per PA §3）===
    tombstone_risk = {
        "demo_bias_gate": "BB_CLEARED" if bb_demo_bias_confirmed else "BB_NOT_CLEARED",
        "cluster_n_eff_penalty": {
            "raw_n": cluster_neff["n_raw"],
            "n_eff_cluster": cluster_neff["n_eff_cluster"],
            "penalty_rate": cluster_neff["penalty_rate"],
            "binding_dimension": _binding_dimension(cluster_neff),
        },
        "cost_realism_gate": {
            "cost_bps": cost_bps,
            "gross_bps": avg_gross,
            "net_bps": avg_net,
            "cost_edge_ratio": cost_edge_ratio,
        },
    }

    return {
        "strategy_variant": STRATEGY_VARIANT,
        "alpha_source_id": ALPHA_SOURCE_ID,
        "pass": verdict,
        "pass_reasons": verdict_reasons,
        "n_per_cell": n_per_cell,
        "pooled_n": n_per_cell,         # alias for top-level n
        "pooled_n_eff": pooled_n_eff,
        "pooled_n_eff_breakdown": cluster_neff,
        "avg_gross_bps": avg_gross,
        "avg_net_bps": avg_net,
        "gross_bps": avg_gross,         # backward-compat alias
        "net_bps": avg_net,             # backward-compat alias
        "cost_edge_ratio": cost_edge_ratio,
        "cost_bps": cost_bps,
        "psr_0": psr_value,
        "dsr": dsr_value,
        "k_prior": int(k_prior),
        "k_new": k_new,
        "k_total": k_total,
        "n_symbols": n_symbols,
        "symbols_in_panel": symbols_in_panel,
        "bootstrap_ci_95_60m": bootstrap_ci_60m,
        "bootstrap_ci_95_4h": bootstrap_ci_4h,
        "pbo": pbo_value,
        "pbo_metadata": pbo_meta,
        "single_day_concentration": day_check,
        "single_symbol_concentration": symbol_check,
        "both_direction_floor": direction_check,
        "density_floor_efficacy": density_efficacy,
        "false_positive_rate": fp_check,
        "long_branch": long_branch,
        "short_branch": short_branch,
        "long_branch_promotion_passed": long_passed,
        "short_branch_promotion_passed": short_passed,
        "distinct_days": distinct_days,
        "sample_window_passed": sample_window_passed,
        "tombstone_risk": tombstone_risk,
        "cell_params": {
            "k_event_count": k_event_count,
            "n_usd": n_usd,
            "m_dominant": m_dominant,
            "floor_usd": floor_usd,
            "side_dom": side_dom,
            "quiet_sec": quiet_sec,
            "horizon_min": horizon_min,
            "cluster_window_min": cluster_window_min,
        },
    }


def _binding_dimension(cluster_neff: Mapping[str, object]) -> str:
    """Identify which of the 3 n_eff dimensions binds (smallest → binding)。

    為什麼有用：MIT review 看哪個維度 dominate；若 binding = days 表
    sample 不夠跨 regime；若 binding = clusters 表 within-day clustering
    太強；若 binding = horizon_overlap 表 horizon 太長相對 sample。
    """
    h = int(cluster_neff.get("n_eff_horizon") or 0)
    d = int(cluster_neff.get("distinct_days") or 0)
    c = int(cluster_neff.get("distinct_60min_clusters") or 0)
    items = (("horizon_overlap", h), ("distinct_days", d), ("distinct_60min_clusters", c))
    valid = [(name, v) for name, v in items if v > 0]
    if not valid:
        return "all_zero"
    name, _ = min(valid, key=lambda kv: kv[1])
    return name


# ============================================================================
# Sweep API：compute_stage0r_sweep — 4-D grid evaluation
# ============================================================================


def compute_stage0r_sweep(
    rows: Sequence[Mapping[str, object]],
    *,
    cost_bps: float = 12.0,
    horizon_grid: Sequence[int] | None = None,
    k_grid: Sequence[int] | None = None,
    n_usd_grid: Sequence[int] | None = None,
    m_grid: Sequence[int] | None = None,
    side_dom_grid: Sequence[float] | None = None,
    floor_grid: Sequence[int] | None = None,
    quiet_grid: Sequence[int] | None = None,
    k_prior: int = 0,
    bb_demo_bias_confirmed: bool = True,
    bootstrap_iters: int = 400,
    cluster_window_min: int = CLUSTER_WINDOW_MIN_DEFAULT,
    rng_seed: int = 20260518,
    total_bucket_count: int | None = None,
) -> dict[str, object]:
    """Sensitivity sweep mirror of W-AUDIT-8b z-grid sweep。

    為什麼 sweep 而非單 cell：spec v0.3 §"adjacent grid cells must form a
    plateau" — 必須驗多 cell 環繞 best cell；single lucky cell 不可信。

    返回 dict 含：
      sweep_cells: list[dict]，每 cell 完整 compute_stage0r 結果。
      best_per_tier_per_direction: 4 cells（high × {long, short}, medium × {long, short}）
      eligible_for_demo_canary_per_tier: dict[tier → {long: bool, short: bool}]。
      sweep_meta: 維度與總 cell 數。
    """
    k_grid = tuple(k_grid) if k_grid is not None else DEFAULT_K_GRID
    n_usd_grid = tuple(n_usd_grid) if n_usd_grid is not None else DEFAULT_N_USD_GRID
    m_grid = tuple(m_grid) if m_grid is not None else DEFAULT_M_GRID
    side_dom_grid = tuple(side_dom_grid) if side_dom_grid is not None else DEFAULT_SIDE_DOM_GRID
    floor_grid = tuple(floor_grid) if floor_grid is not None else DEFAULT_FLOOR_GRID
    quiet_grid = tuple(quiet_grid) if quiet_grid is not None else DEFAULT_QUIET_GRID
    horizon_grid = tuple(horizon_grid) if horizon_grid is not None else DEFAULT_HORIZON_GRID

    # Pre-check：BB demo bias gate (RED Risk #1 short-circuit).
    if not bb_demo_bias_confirmed:
        return {
            "strategy_variant": SWEEP_STRATEGY_VARIANT,
            "alpha_source_id": ALPHA_SOURCE_ID,
            "eligible_for_demo_canary": False,
            "eligible_for_demo_canary_per_tier": {
                tier: {"long": False, "short": False} for tier in DENSITY_TIERS
            },
            "sweep_cells": [],
            "sweep_meta": {
                "bb_demo_bias_confirmed": False,
                "reason": "Stage 0R sweep refused until BB clears demo testnet "
                          "long-liquidation skew is real microstructure",
            },
        }

    sweep_cells: list[dict[str, object]] = []
    for k in k_grid:
        for n in n_usd_grid:
            for m in m_grid:
                for fl in floor_grid:
                    for sd in side_dom_grid:
                        for q in quiet_grid:
                            for h in horizon_grid:
                                cell_result = compute_stage0r(
                                    rows,
                                    cost_bps=cost_bps,
                                    horizon_min=h,
                                    k_event_count=k,
                                    n_usd=n,
                                    m_dominant=m,
                                    floor_usd=fl,
                                    side_dom=sd,
                                    quiet_sec=q,
                                    k_prior=k_prior,
                                    bootstrap_iters=bootstrap_iters,
                                    cluster_window_min=cluster_window_min,
                                    rng_seed=rng_seed,
                                    bb_demo_bias_confirmed=True,
                                    total_bucket_count=total_bucket_count,
                                )
                                # 為 sweep_cells 加 explicit grid coords。
                                cell_result["grid_coords"] = {
                                    "k": k, "n_usd": n, "m": m,
                                    "floor_usd": fl, "side_dom": sd,
                                    "quiet_sec": q, "horizon_min": h,
                                }
                                sweep_cells.append(cell_result)

    # === Per-tier × per-direction best cell + verdict ===
    # 從 rows 推 symbol → tier 分類；用 default density floors (K=3, N=10k, M=2)
    # 之 triggers 來定 tier baseline（per spec v0.3）。
    default_triggers = _extract_trigger_rows(
        rows,
        k_event_count=3, n_usd=10_000, m_dominant=2,
        floor_usd=10_000, side_dom=0.80, quiet_sec=30,
        horizon_min=PRIMARY_HORIZON_MIN, cost_bps=cost_bps,
    )
    symbol_tiers = _classify_symbols_by_tier(default_triggers)

    # Per-tier 的 best cell（best = lowest pass_reasons count then highest avg_net）。
    per_tier_per_direction_best: dict[str, dict[str, dict[str, object] | None]] = {
        tier: {"long_liquidated": None, "short_liquidated": None}
        for tier in DENSITY_TIERS
    }
    per_tier_per_direction_passed: dict[str, dict[str, bool]] = {
        tier: {"long": False, "short": False} for tier in DENSITY_TIERS
    }

    def _tier_score(cell: Mapping[str, object], direction_key: str) -> tuple[int, float]:
        """Lower fail count + higher avg_net = better。"""
        branch_key = "long_branch" if direction_key == "long_liquidated" else "short_branch"
        branch = cell.get(branch_key)
        if not isinstance(branch, Mapping):
            return (1_000_000, -1e18)
        avg_n = _safe_float(branch.get("avg_net_bps")) or -1e18
        # 用 verdict 推 fail count（PASS-BOTH = 0；PASS-LONG/SHORT-ONLY = 1；RED = 2）。
        verdict = str(cell.get("pass") or "RED")
        fail_count = {"PASS-BOTH": 0, "PASS-LONG-ONLY": 1, "PASS-SHORT-ONLY": 1, "RED": 2}.get(verdict, 3)
        return (fail_count, -avg_n)

    # 對每 tier × direction 找 best cell（用 default tier baseline triggers
    # 投票每 cell 的「主導 tier」；本實作簡化為 across-all-cells 排序）。
    for tier in DENSITY_TIERS:
        # 該 tier 包含的 symbols。
        tier_symbols = {s for s, t in symbol_tiers.items() if t == tier}
        if not tier_symbols:
            # Tier 無 symbol → 直接 fail。
            continue
        for direction in DIRECTION_BRANCHES:
            # 選此 tier × direction 之 best cell（限 cell 之 symbols_in_panel
            # 與 tier_symbols 有交集；放寬 fallback 取 best 全 panel cell 註明）。
            best_in_tier = None
            best_score = (1_000_000, -1e18)
            for cell in sweep_cells:
                cell_syms = set(cell.get("symbols_in_panel") or [])
                if not (cell_syms & tier_symbols):
                    continue
                score = _tier_score(cell, direction)
                if score < best_score:
                    best_score = score
                    best_in_tier = cell
            per_tier_per_direction_best[tier][direction] = best_in_tier
            if best_in_tier:
                # tier × direction PASS 條件：該 cell 對應 branch 通過 promotion。
                direction_short = "long" if direction == "long_liquidated" else "short"
                branch_key = f"{direction_short}_branch_promotion_passed"
                per_tier_per_direction_passed[tier][direction_short] = bool(best_in_tier.get(branch_key))

    # === Overall eligibility：至少一個 tier × direction PASS ===
    any_tier_direction_passed = any(
        v for tier_d in per_tier_per_direction_passed.values() for v in tier_d.values()
    )

    return {
        "strategy_variant": SWEEP_STRATEGY_VARIANT,
        "alpha_source_id": ALPHA_SOURCE_ID,
        "eligible_for_demo_canary": any_tier_direction_passed,
        "eligible_for_demo_canary_per_tier": per_tier_per_direction_passed,
        "best_per_tier_per_direction": per_tier_per_direction_best,
        "symbol_tiers": symbol_tiers,
        "sweep_cells": sweep_cells,
        "sweep_meta": {
            "bb_demo_bias_confirmed": True,
            "k_grid": list(k_grid),
            "n_usd_grid": list(n_usd_grid),
            "m_grid": list(m_grid),
            "side_dom_grid": list(side_dom_grid),
            "floor_grid": list(floor_grid),
            "quiet_grid": list(quiet_grid),
            "horizon_grid": list(horizon_grid),
            "total_cells": len(sweep_cells),
            "cost_bps": cost_bps,
            "cluster_window_min": cluster_window_min,
            "rng_seed": rng_seed,
        },
    }


# ============================================================================
# Utility：default symbols from rows (mirror 8b API for caller stability)
# ============================================================================


def default_symbols_from_rows(rows: Iterable[Mapping[str, object]]) -> tuple[str, ...]:
    """Convenience helper — sorted unique symbols from input rows。"""
    return tuple(sorted({str(r.get("symbol")) for r in rows if r.get("symbol")}))


def grid_cell_count(
    *,
    k_grid: Sequence[int] = DEFAULT_K_GRID,
    n_usd_grid: Sequence[int] = DEFAULT_N_USD_GRID,
    m_grid: Sequence[int] = DEFAULT_M_GRID,
    floor_grid: Sequence[int] = DEFAULT_FLOOR_GRID,
    side_dom_grid: Sequence[float] = DEFAULT_SIDE_DOM_GRID,
    quiet_grid: Sequence[int] = DEFAULT_QUIET_GRID,
    horizon_grid: Sequence[int] = DEFAULT_HORIZON_GRID,
) -> int:
    """Return total cell count of the 7-D sweep grid。"""
    return (
        len(k_grid) * len(n_usd_grid) * len(m_grid)
        * len(floor_grid) * len(side_dom_grid) * len(quiet_grid)
        * len(horizon_grid)
    )
