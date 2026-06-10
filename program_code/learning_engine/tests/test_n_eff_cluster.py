"""n_eff_cluster 測試（L2 P4 M2 純數學核心）。

覆蓋（E1-A 契約 + E4 驗收軸）：
  1. 常數表複核（M2 ENDORSED：corr_cut=0.5 / min_overlap=20 / cap=25）。
  2. max(1,·) guard（空輸入 / 單一輸入 → n_eff=1）。
  3. 聚類已知小例（手算 corr 結構驗 cluster 形狀：完美相關合併、獨立分離、
     兩群+1、average-linkage 反鏈式合併——精確正交構造）。
  4. overlap 邊界（19 不合併 / 20 合併 / NaN 削減有限 overlap、MIT #5 保守向）。
  5. 退化 corr（常數序列）不合併。
  6. 超 cap = ceil(size/cap) effective trials（MIT #6）。
  7. int-bar-index 契約 fail-loud（str/bool/date key → ValueError）。
  8. 參數驗證 fail-loud + 確定性 + 分割性質。
  9. 模組純度（AST 層：0 scipy / 0 psycopg2 / 0 asyncio）。
"""

from __future__ import annotations

import ast
import datetime
import inspect
import math

import numpy as np
import pytest

import program_code.learning_engine.n_eff_cluster as nec
from program_code.learning_engine.n_eff_cluster import (
    DEFAULT_CORR_CUT,
    DEFAULT_MAX_VARIANTS_PER_CLUSTER,
    DEFAULT_MIN_OVERLAP_BARS,
    NEffResult,
    n_eff_average_linkage,
)


def _series(values) -> dict[int, float]:
    """list → int-bar-index Mapping（契約形態）。"""
    return {i: float(v) for i, v in enumerate(values)}


# ─────────────────────────────────────────────────────────────────────────────
# 1. 常數表複核
# ─────────────────────────────────────────────────────────────────────────────


class TestConstantsContract:
    def test_m2_endorsed_constants_exact(self):
        assert DEFAULT_CORR_CUT == 0.5
        assert DEFAULT_MIN_OVERLAP_BARS == 20
        assert DEFAULT_MAX_VARIANTS_PER_CLUSTER == 25


# ─────────────────────────────────────────────────────────────────────────────
# 2. max(1,·) guard
# ─────────────────────────────────────────────────────────────────────────────


class TestGuards:
    def test_empty_input_n_eff_one(self):
        # 空輸入 → n_eff=1（K=0 永不流向 compute_dsr 的 n_trials<1 raise）。
        res = n_eff_average_linkage([])
        assert res.n_eff == 1
        assert res.clusters == []
        assert "empty_variant_returns_n_eff_floor_1" in res.reasons

    def test_single_variant_n_eff_one(self):
        rng = np.random.default_rng(1)
        res = n_eff_average_linkage([_series(rng.normal(size=40))])
        assert res.n_eff == 1
        assert res.clusters == [[0]]
        assert res.reasons == []

    def test_n_eff_always_geq_one(self):
        rng = np.random.default_rng(2)
        for m in [1, 2, 3, 5]:
            inputs = [_series(rng.normal(size=40)) for _ in range(m)]
            assert n_eff_average_linkage(inputs).n_eff >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. 聚類已知小例（手算 corr 結構）
# ─────────────────────────────────────────────────────────────────────────────


class TestClusterShapes:
    def test_perfectly_correlated_merge_to_one(self):
        # 正數倍縮放 ⇒ 兩兩 Pearson corr 恰為 1 ⇒ 全合併 → n_eff=1。
        rng = np.random.default_rng(3)
        base = rng.normal(size=60)
        inputs = [_series(base), _series(2.0 * base), _series(5.0 * base)]
        res = n_eff_average_linkage(inputs)
        assert res.n_eff == 1
        assert res.clusters == [[0, 1, 2]]

    def test_independent_stay_separate(self):
        # 獨立序列（seed 固定，cross-corr 遠低於 0.5）⇒ 各自一 cluster。
        rng = np.random.default_rng(7)
        x, y, z = (rng.normal(size=60) for _ in range(3))
        # 前置自檢：構造確實互不相關（避免 seed 巧合讓測試空轉）。
        for a, b in [(x, y), (x, z), (y, z)]:
            assert abs(float(np.corrcoef(a, b)[0, 1])) < 0.4
        res = n_eff_average_linkage([_series(x), _series(y), _series(z)])
        assert res.n_eff == 3
        assert res.clusters == [[0], [1], [2]]

    def test_two_groups_plus_one_independent(self):
        # 手算結構：{0,1} 同組（corr=1）、{2,3} 同組（corr=1）、4 獨立
        # ⇒ clusters [[0,1],[2,3],[4]]、n_eff=3。
        rng = np.random.default_rng(11)
        x, y, z = (rng.normal(size=60) for _ in range(3))
        for a, b in [(x, y), (x, z), (y, z)]:
            assert abs(float(np.corrcoef(a, b)[0, 1])) < 0.4
        inputs = [
            _series(x),
            _series(2.0 * x),
            _series(y),
            _series(3.0 * y),
            _series(z),
        ]
        res = n_eff_average_linkage(inputs)
        assert res.n_eff == 3
        assert res.clusters == [[0, 1], [2, 3], [4]]
        # 分割性質：clusters 是 variant 索引的不交完備分割。
        flat = sorted(i for c in res.clusters for i in c)
        assert flat == list(range(5))

    def test_average_linkage_blocks_chain_merge(self):
        # 精確正交構造（n=40，4 的倍數 ⇒ 零均值且 dot(u,v)=0）：
        #   u_k=(-1)^k、v_k=(-1)^(k//2)、b=u+0.8v（非對稱權重避免數學上恰相等的 tie）
        #   corr(u,b)=1/√1.64≈0.781、corr(v,b)=0.8/√1.64≈0.625、corr(u,v)=0
        # 先合併最大對 {u,b}（0.781>0.625 嚴格，無 tie）；{u,b} vs {v} 的平均
        # corr=(0+0.625)/2≈0.312<0.5 ⇒ average linkage 不鏈式合併
        #（single linkage 會因 corr(v,b)=0.625>0.5 誤合到一桶）。
        n = 40
        u = np.array([(-1.0) ** k for k in range(n)])
        v = np.array([(-1.0) ** (k // 2) for k in range(n)])
        assert float(u @ v) == 0.0  # 構造自檢：精確正交
        b = u + 0.8 * v
        res = n_eff_average_linkage([_series(u), _series(b), _series(v)])
        assert res.clusters == [[0, 1], [2]]
        assert res.n_eff == 2

    def test_corr_cut_parameter_honored(self):
        # 同上構造 corr(v,b)=0.8/√1.64≈0.6247：cut=0.62 時 {v} 在第二輪與
        # {u,b} 的平均 corr=(0+0.6247)/2≈0.312 仍不合併（average-linkage），
        # 但首輪後 cut=0.79 連 {u,b}（corr≈0.781）都不合併 ⇒ n_eff=3。
        n = 40
        u = np.array([(-1.0) ** k for k in range(n)])
        v = np.array([(-1.0) ** (k // 2) for k in range(n)])
        b = u + 0.8 * v
        inputs = [_series(u), _series(b), _series(v)]
        assert n_eff_average_linkage(inputs, corr_cut=0.70).n_eff == 2
        assert n_eff_average_linkage(inputs, corr_cut=0.79).n_eff == 3

    def test_deterministic_repeat(self):
        rng = np.random.default_rng(13)
        x, y = rng.normal(size=60), rng.normal(size=60)
        inputs = [_series(x), _series(2 * x), _series(y)]
        r1 = n_eff_average_linkage(inputs)
        r2 = n_eff_average_linkage(inputs)
        assert (r1.n_eff, r1.clusters, r1.reasons) == (r2.n_eff, r2.clusters, r2.reasons)


# ─────────────────────────────────────────────────────────────────────────────
# 4. overlap 邊界（MIT #5：不足 ⇒ 不相關 ⇒ 保守）
# ─────────────────────────────────────────────────────────────────────────────


class TestOverlapBoundary:
    def test_overlap_19_not_merged(self):
        # 完美相關但共同 bar 僅 19 < 20 ⇒ 視為不相關 ⇒ 不合併。
        rng = np.random.default_rng(17)
        base = rng.normal(size=19)
        res = n_eff_average_linkage([_series(base), _series(2.0 * base)])
        assert res.n_eff == 2
        assert res.clusters == [[0], [1]]
        assert "pairs_overlap_below_min_treated_uncorrelated:1" in res.reasons

    def test_overlap_exactly_20_merged(self):
        # 邊界含端點：恰 20 bar ⇒ corr 可估 ⇒ 完美相關合併。
        rng = np.random.default_rng(19)
        base = rng.normal(size=20)
        res = n_eff_average_linkage([_series(base), _series(2.0 * base)])
        assert res.n_eff == 1
        assert res.clusters == [[0, 1]]

    def test_disjoint_keys_treated_uncorrelated(self):
        # key 完全不相交（overlap=0）⇒ 不相關 ⇒ 各自獨立 trial（最大 deflation）。
        rng = np.random.default_rng(23)
        a = {i: float(v) for i, v in enumerate(rng.normal(size=30))}
        b = {i + 100: float(v) for i, v in enumerate(rng.normal(size=30))}
        res = n_eff_average_linkage([a, b])
        assert res.n_eff == 2

    def test_nan_values_shrink_finite_overlap(self):
        # 25 共同 key 但 6 個 NaN ⇒ 有限 overlap=19<20 ⇒ 不合併（資料損壞
        # 不得偽裝成可估 corr——收縮向）。
        rng = np.random.default_rng(29)
        base = rng.normal(size=25)
        noisy = base.copy()
        noisy[:6] = np.nan
        res = n_eff_average_linkage([_series(base), _series(noisy)])
        assert res.n_eff == 2
        assert "pairs_overlap_below_min_treated_uncorrelated:1" in res.reasons

    def test_min_overlap_bars_parameter_honored(self):
        # 19 共同 bar 在 min_overlap_bars=10 下可估 ⇒ 合併。
        rng = np.random.default_rng(31)
        base = rng.normal(size=19)
        res = n_eff_average_linkage(
            [_series(base), _series(2.0 * base)], min_overlap_bars=10
        )
        assert res.n_eff == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. 退化 corr（常數序列）
# ─────────────────────────────────────────────────────────────────────────────


class TestDegenerateCorr:
    def test_constant_series_never_merges(self):
        # 常數序列 ⇒ Pearson corr 未定義 ⇒ 不可證明相關 ⇒ 不合併
        #（合併會假縮 N_eff = 反保守）。
        rng = np.random.default_rng(37)
        res = n_eff_average_linkage(
            [_series([1.0] * 40), _series(rng.normal(size=40))]
        )
        assert res.n_eff == 2
        assert "pairs_degenerate_corr_treated_uncorrelated:1" in res.reasons

    def test_two_constant_series_stay_separate(self):
        # 兩條常數序列也不互併（corr 未定義，非「同為常數=相關」）。
        res = n_eff_average_linkage([_series([1.0] * 40), _series([1.0] * 40)])
        assert res.n_eff == 2


# ─────────────────────────────────────────────────────────────────────────────
# 6. 超 cap = ceil(size/cap)（MIT #6）
# ─────────────────────────────────────────────────────────────────────────────


class TestOverCapTrials:
    def test_thirty_clones_default_cap(self):
        # 30 個完美相關 variant ⇒ 單 cluster size=30 > 25
        # ⇒ ceil(30/25)=2 effective trials（封死「千變體藏一桶付一次債」）。
        rng = np.random.default_rng(41)
        base = rng.normal(size=40)
        inputs = [_series(float(i + 1) * base) for i in range(30)]
        res = n_eff_average_linkage(inputs)
        assert len(res.clusters) == 1
        assert len(res.clusters[0]) == 30
        assert res.n_eff == 2
        assert "clusters_over_cap_ceil_effective_trials:1" in res.reasons

    def test_ceil_arithmetic_with_small_cap(self):
        # 7 clones、cap=3 ⇒ ceil(7/3)=3。
        rng = np.random.default_rng(43)
        base = rng.normal(size=40)
        inputs = [_series(float(i + 1) * base) for i in range(7)]
        res = n_eff_average_linkage(inputs, max_variants_per_cluster=3)
        assert res.n_eff == 3

    def test_at_cap_counts_one(self):
        # size == cap（不超）⇒ 1 effective trial，無 over-cap reason。
        rng = np.random.default_rng(47)
        base = rng.normal(size=40)
        inputs = [_series(float(i + 1) * base) for i in range(5)]
        res = n_eff_average_linkage(inputs, max_variants_per_cluster=5)
        assert res.n_eff == 1
        assert not any(r.startswith("clusters_over_cap") for r in res.reasons)

    def test_monotone_vs_endorsed_baseline(self):
        # MIT #6：對 ENDORSED 基線（一 cluster=1 trial）嚴格單調更保守——
        # n_eff ≥ cluster 數恆成立。
        rng = np.random.default_rng(53)
        base = rng.normal(size=40)
        inputs = [_series(float(i + 1) * base) for i in range(30)]
        res = n_eff_average_linkage(inputs)
        assert res.n_eff >= len(res.clusters)


# ─────────────────────────────────────────────────────────────────────────────
# 7. int-bar-index 契約 fail-loud
# ─────────────────────────────────────────────────────────────────────────────


class TestIntBarIndexContract:
    def test_str_key_raises(self):
        with pytest.raises(ValueError, match="int bar index"):
            n_eff_average_linkage([{"2024-01-01": 0.1}])  # type: ignore[list-item]

    def test_bool_key_raises(self):
        # bool 是 int 子類但非合法 bar index（B1 同款契約）。
        with pytest.raises(ValueError, match="int bar index"):
            n_eff_average_linkage([{0: 0.1, True: 0.2}])

    def test_date_key_raises(self):
        with pytest.raises(ValueError, match="int bar index"):
            n_eff_average_linkage(
                [{datetime.date(2024, 1, 1): 0.1}]  # type: ignore[list-item]
            )

    def test_mixed_keys_raise(self):
        rng = np.random.default_rng(59)
        good = _series(rng.normal(size=40))
        bad = {0: 0.1, 1: 0.2, "x": 0.3}
        with pytest.raises(ValueError, match="int bar index"):
            n_eff_average_linkage([good, bad])  # type: ignore[list-item]


# ─────────────────────────────────────────────────────────────────────────────
# 8. 參數驗證 fail-loud
# ─────────────────────────────────────────────────────────────────────────────


class TestParamValidation:
    @pytest.mark.parametrize("cut", [0.0, 1.0, -0.5, float("nan")])
    def test_invalid_corr_cut_raises(self, cut):
        # cut ≤ 0 會把互不相關的 variant 合併 = 假縮 N_eff（反保守）。
        with pytest.raises(ValueError):
            n_eff_average_linkage([_series([1.0, 2.0])], corr_cut=cut)

    @pytest.mark.parametrize("mob", [0, 1, -5])
    def test_invalid_min_overlap_raises(self, mob):
        with pytest.raises(ValueError):
            n_eff_average_linkage([_series([1.0, 2.0])], min_overlap_bars=mob)

    @pytest.mark.parametrize("cap", [0, -1])
    def test_invalid_cap_raises(self, cap):
        with pytest.raises(ValueError):
            n_eff_average_linkage(
                [_series([1.0, 2.0])], max_variants_per_cluster=cap
            )


# ─────────────────────────────────────────────────────────────────────────────
# 9. NEffResult 形態 + 模組純度
# ─────────────────────────────────────────────────────────────────────────────


class TestResultShapeAndPurity:
    def test_result_fields_types(self):
        rng = np.random.default_rng(61)
        res = n_eff_average_linkage([_series(rng.normal(size=40))])
        assert isinstance(res, NEffResult)
        assert isinstance(res.n_eff, int)
        assert isinstance(res.clusters, list)
        assert isinstance(res.reasons, list)

    def test_no_forbidden_imports_ast(self):
        # 為什麼用 AST：MODULE_NOTE 合法提及「禁 scipy / 0 psycopg2」，
        # 裸字串 grep 會誤紅（驗「code 無引用」必剝 docstring/註釋）。
        tree = ast.parse(inspect.getsource(nec))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {"scipy", "psycopg2", "asyncio", "pandas", "aiohttp", "requests"}
        assert imported.isdisjoint(forbidden), imported
        # hand-rolled 慣例：numpy + 標準庫而已。
        assert imported <= {"__future__", "math", "dataclasses", "typing", "numpy"}

    def test_no_async_defs(self):
        tree = ast.parse(inspect.getsource(nec))
        assert not any(isinstance(n, ast.AsyncFunctionDef) for n in ast.walk(tree))
