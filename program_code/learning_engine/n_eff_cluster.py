"""n_eff_cluster — L2 P4 online-FDR effective-trials 聚類純數學核心（M2）。

MODULE_NOTE
模塊用途：對候選 variant 報酬序列做 hand-rolled average-linkage 聚類
  （Pearson corr > corr_cut 合併），輸出 effective trials 數 N_eff。N_eff
  唯一消費面 = DSR deflation（`compute_dsr(n_trials=N_eff)`，經 adapter seam
  `k_for_dsr = n_eff`）；debit 額 = α_i，與 N_eff 無關（MIT 5a 措辭紀律——
  wealth 帳與 N_eff 不耦合，勿在任何注釋寫反）。
主要類/函數：NEffResult、n_eff_average_linkage。
依賴：numpy + 標準庫（hand-rolled，禁 scipy——pbo_gate 同款慣例；0 DB /
  0 I/O / 0 async / 0 psycopg2）。
硬邊界：純函數、無副作用；int-bar-index 契約 fail-loud（非 int key →
  ValueError，鏡像 beta_neutral_check 的「顯式可診斷、非靜默空-series」原則，
  adapter 層 catch 後走 raw k_trials fallback = 保守向）；一切無法證明相關的
  情形（overlap 不足 / 退化 corr）一律視為不相關 → N_eff 偏大 → DSR deflation
  偏狠 = 收縮向（MIT ratify #5）。

設計契約：PA P4 設計 §3.1 + MIT ratify #5（overlap 不足=不相關）/
  #6（cluster 超 cap = ceil(size/cap) effective trials）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# M2 ENDORSED 常數（PA §3.1）
# ─────────────────────────────────────────────────────────────────────────────

# M2：Pearson corr > 0.5 ⇒ 同 cluster（合併條件作用在 corr 上；
# 距離 = 1−corr 下等價於 average distance < 1−corr_cut）。
DEFAULT_CORR_CUT: float = 0.5

# 兩兩共同 bar 數低於此值 ⇒ corr 不可估 ⇒ 視為不相關（MIT ratify #5：
# 20 bar 以下 corr 估計 SE ≈ 0.24，cut=0.5 附近誤判率高，「不確定就當獨立」
# 是保守解——不合併 ⇒ N_eff 偏大 ⇒ DSR deflation 偏狠 ⇒ 更難 pass）。
DEFAULT_MIN_OVERLAP_BARS: int = 20

# M2 NOTE anti-abuse：單一 cluster 計入 effective trials 的除數上限。
# 超 cap 的 cluster 計 ceil(size/cap) 個 effective trials（MIT ratify #6：
# 封死「千變體藏一桶付一次債」；對 ENDORSED 基線一 cluster=1 trial 嚴格
# 單調更保守）。
DEFAULT_MAX_VARIANTS_PER_CLUSTER: int = 25


# ─────────────────────────────────────────────────────────────────────────────
# 結果型別（PA §3.1 契約：{n_eff:int>=1, clusters, reasons}）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class NEffResult:
    """N_eff 聚類結果。

    欄位：
      n_eff：effective trials 數，恆 ≥ 1（max(1,·) guard——K=0 永不可能流向
        `compute_dsr` 的 n_trials<1 raise）。
      clusters：各 cluster 的 variant 原始索引（輸入序位），cluster 內升序、
        cluster 間按首元素升序（確定性，供審計重現）。
      reasons：保守降級事件的聚合記錄（如 overlap 不足對數、退化 corr 對數、
        超 cap cluster 數），供 evidence/seam 落庫。
    """

    n_eff: int
    clusters: list[list[int]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 內部：int-bar-index 契約 + 兩兩 corr
# ─────────────────────────────────────────────────────────────────────────────


def _first_non_int_bar_index_key(
    variant_returns: Sequence[Mapping[int, float]],
) -> object | None:
    """回傳第一個違反 int-bar-index 契約的 key（含 bool——bool 是 int 子類但
    非合法 bar index）；全合法回 None。"""
    for series in variant_returns:
        for k in series.keys():
            if isinstance(k, bool) or not isinstance(k, int):
                return k
    return None


def _pairwise_corr(
    a: Mapping[int, float],
    b: Mapping[int, float],
    min_overlap_bars: int,
) -> tuple[float, str | None]:
    """兩序列在共同 int bar index 上的 Pearson corr。

    回 (corr, degrade_reason)：
      - overlap（雙邊皆有限值的共同 key 數）< min_overlap_bars →
        (0.0, "overlap")——視為不相關（MIT #5 保守向）。
      - 任一邊零變異 / corr 非有限（退化）→ (0.0, "degenerate")——退化 corr
        不可證明相關，合併會假縮 N_eff（反保守），故同樣視為不相關。
      - 正常 → (corr, None)。
    """
    shared = sorted(a.keys() & b.keys())
    xs: list[float] = []
    ys: list[float] = []
    for k in shared:
        va = a[k]
        vb = b[k]
        # 非有限值不參與對齊（資料損壞不得污染 corr；剔除後 overlap 不足
        # 即落回「不相關」保守路徑）。
        if math.isfinite(va) and math.isfinite(vb):
            xs.append(float(va))
            ys.append(float(vb))
    if len(xs) < min_overlap_bars:
        return 0.0, "overlap"
    ax = np.asarray(xs, dtype=np.float64)
    ay = np.asarray(ys, dtype=np.float64)
    # 零變異（常數序列）⇒ Pearson corr 未定義 ⇒ 不可證明相關 ⇒ 不合併。
    if float(np.std(ax)) == 0.0 or float(np.std(ay)) == 0.0:
        return 0.0, "degenerate"
    corr = float(np.corrcoef(ax, ay)[0, 1])
    if not math.isfinite(corr):
        return 0.0, "degenerate"
    return corr, None


# ─────────────────────────────────────────────────────────────────────────────
# 公開 API
# ─────────────────────────────────────────────────────────────────────────────


def n_eff_average_linkage(
    variant_returns: Sequence[Mapping[int, float]],
    *,
    corr_cut: float = DEFAULT_CORR_CUT,
    min_overlap_bars: int = DEFAULT_MIN_OVERLAP_BARS,
    max_variants_per_cluster: int = DEFAULT_MAX_VARIANTS_PER_CLUSTER,
) -> NEffResult:
    """hand-rolled average-linkage 聚類 → effective trials 數 N_eff。

    演算法（PA §3.1）：
      1. 兩兩 Pearson corr（共同 int bar index 上對齊；overlap 不足或退化
         一律 corr := 0 = 不相關，保守）。
      2. greedy agglomerative：每輪取「兩 cluster 間成員兩兩 corr 平均」最大
         的一對，嚴格 > corr_cut 才合併；無可合併即停。距離 = 1−corr 下此即
         average-linkage。O(M³) 量級，對 M ≤ ~50 充分。
      3. N_eff = Σ_cluster ceil(size / max_variants_per_cluster)
         （size ≤ cap 的 cluster 貢獻 1；超 cap 計 ceil(size/cap) 個
         effective trials——MIT #6 anti-abuse）。
      4. max(1, N_eff) guard：空輸入 → n_eff=1（K=0 永不流向 compute_dsr 的
         n_trials<1 raise）。

    消費語義（MIT 5a 措辭紀律）：N_eff 只影響 DSR deflation（經 adapter
    `gi["n_trials"] = n_eff`、ledger 審計欄 `k_for_dsr = n_eff`）；debit 額
    = α_i 與 N_eff 無關。

    int-bar-index 契約（fail-loud）：key 必須是共享 int bar index（date→int
    re-index 是上游 `bar_index_reindex` 的責任）。任一非 int（或 bool）key →
    ValueError——不靜默吞成「全不相關」，否則上游忘 reindex 的 wiring bug 會
    被偽裝成合法的最大 deflation 結果；adapter 層 catch 後走 raw k_trials
    fallback（保守向）。

    參數非法（corr_cut ∉ (0,1) / min_overlap_bars < 2 /
    max_variants_per_cluster < 1）→ ValueError fail-loud：corr_cut ≤ 0 會把
    互不相關的 variant 合併 = 假縮 N_eff（反保守），必須在源頭炸。
    """
    if not (math.isfinite(corr_cut) and 0.0 < corr_cut < 1.0):
        raise ValueError(f"corr_cut={corr_cut} 必須在 (0, 1) 內")
    if min_overlap_bars < 2:
        raise ValueError(f"min_overlap_bars={min_overlap_bars} 必須 >= 2")
    if max_variants_per_cluster < 1:
        raise ValueError(
            f"max_variants_per_cluster={max_variants_per_cluster} 必須 >= 1"
        )

    m = len(variant_returns)
    if m == 0:
        # 空輸入：max(1,·) guard 落點——n_eff=1、無 cluster，誠實記 reason。
        return NEffResult(
            n_eff=1, clusters=[], reasons=["empty_variant_returns_n_eff_floor_1"]
        )

    bad_key = _first_non_int_bar_index_key(variant_returns)
    if bad_key is not None:
        raise ValueError(
            "variant_returns key 非 int bar index（got "
            f"{type(bad_key).__name__} key={bad_key!r}）——int-bar-index 契約"
            "要求上游先 reindex（bar_index_reindex），fail-loud 不靜默降級"
        )

    reasons: list[str] = []

    if m == 1:
        return NEffResult(n_eff=1, clusters=[[0]], reasons=reasons)

    # ── 兩兩 corr 矩陣（對角=1；degraded 對 := 0.0 = 不相關）──
    corr = np.eye(m, dtype=np.float64)
    n_overlap_degraded = 0
    n_degenerate = 0
    for i in range(m):
        for j in range(i + 1, m):
            c, why = _pairwise_corr(
                variant_returns[i], variant_returns[j], min_overlap_bars
            )
            corr[i, j] = c
            corr[j, i] = c
            if why == "overlap":
                n_overlap_degraded += 1
            elif why == "degenerate":
                n_degenerate += 1
    if n_overlap_degraded:
        reasons.append(
            f"pairs_overlap_below_min_treated_uncorrelated:{n_overlap_degraded}"
        )
    if n_degenerate:
        reasons.append(f"pairs_degenerate_corr_treated_uncorrelated:{n_degenerate}")

    # ── greedy average-linkage agglomerative ──
    clusters: list[list[int]] = [[i] for i in range(m)]
    while len(clusters) > 1:
        best_pair: tuple[int, int] | None = None
        best_avg = corr_cut  # 嚴格 > corr_cut 才有資格合併
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                pair_sum = 0.0
                for i in clusters[a]:
                    for j in clusters[b]:
                        pair_sum += corr[i, j]
                avg = pair_sum / (len(clusters[a]) * len(clusters[b]))
                # 嚴格 > 保證確定性：等值後到者不取代先到者（掃描序固定）。
                if avg > best_avg:
                    best_avg = avg
                    best_pair = (a, b)
        if best_pair is None:
            break
        a, b = best_pair
        clusters[a] = sorted(clusters[a] + clusters[b])
        del clusters[b]

    clusters.sort(key=lambda c: c[0])

    # ── effective trials（MIT #6：超 cap 計 ceil(size/cap)）──
    n_eff = 0
    n_over_cap = 0
    for c in clusters:
        trials = math.ceil(len(c) / max_variants_per_cluster)
        if trials > 1:
            n_over_cap += 1
        n_eff += trials
    if n_over_cap:
        reasons.append(f"clusters_over_cap_ceil_effective_trials:{n_over_cap}")

    # max(1,·) guard（M2 NOTE）：防任何未來改動讓 n_eff 跌到 0。
    return NEffResult(n_eff=max(1, n_eff), clusters=clusters, reasons=reasons)
