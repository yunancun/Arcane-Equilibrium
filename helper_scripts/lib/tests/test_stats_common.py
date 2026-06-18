"""Golden-value 測試 — helper_scripts.lib.stats_common。

MODULE_NOTE:
  模塊用途：對整併後的共享統計公式逐一鎖死「已知輸入 → 已知輸出」，證明從 8b /
    8c 抽取整併沒有改變數值行為，並覆蓋 div-by-zero / n<門檻 / all-equal 等邊界。
  reference 來源：偏度 / 峰度 / Wilson / n_eff 為手算（見各測試註解）；PSR / DSR /
    bootstrap 為以 canonical 實作對固定 seed 算出的穩定參考值（seed 固定後
    deterministic，故可當回歸 baseline）。
  依賴：pytest + 純 stdlib。無 DB / 無 IO。

  執行：``python3 -m pytest helper_scripts/lib/tests/test_stats_common.py -q``
"""

from __future__ import annotations

import math
import os

import pytest

from helper_scripts.lib import pg_connect as PG
from helper_scripts.lib import stats_common as S


# ── _safe_float / _safe_int ────────────────────────────────────────────────


def test_safe_float_valid():
    assert S._safe_float("3.5") == 3.5
    assert S._safe_float(2) == 2.0


def test_safe_float_rejects_non_numeric_and_non_finite():
    # NaN / Inf / 不可轉字串一律 None（fail-closed，不讓壞值污染下游）
    assert S._safe_float("x") is None
    assert S._safe_float(None) is None
    assert S._safe_float(float("nan")) is None
    assert S._safe_float(float("inf")) is None
    assert S._safe_float(float("-inf")) is None


def test_safe_int():
    assert S._safe_int("7") == 7
    assert S._safe_int(3.9) == 3      # truncates toward zero
    assert S._safe_int("x") is None
    assert S._safe_int(None) is None


# ── _normal_cdf ────────────────────────────────────────────────────────────


def test_normal_cdf_known_points():
    assert S._normal_cdf(0.0) == 0.5
    # Φ(1.96) ≈ 0.975（95% 單尾臨界），鎖到 1e-9
    assert S._normal_cdf(1.96) == pytest.approx(0.9750021048517796, abs=1e-12)
    # 對稱性：Φ(-x) = 1 - Φ(x)
    assert S._normal_cdf(-1.0) == pytest.approx(1.0 - S._normal_cdf(1.0), abs=1e-12)


# ── _skew / _kurtosis（母體公式，手算 reference） ──────────────────────────


def test_skew_known_value():
    # values=[1,2,3,4,10]，mean=4，population skew 手算 = 1.1384199576606164
    assert S._skew([1.0, 2.0, 3.0, 4.0, 10.0]) == pytest.approx(
        1.1384199576606164, abs=1e-12
    )


def test_skew_symmetric_is_zero():
    # 完全對稱序列 skew = 0
    assert S._skew([1.0, 2.0, 3.0, 4.0, 5.0]) == pytest.approx(0.0, abs=1e-12)


def test_skew_edge_cases():
    assert S._skew([1.0, 2.0]) is None          # n<3
    assert S._skew([5.0, 5.0, 5.0, 5.0]) is None  # 零變異 → div-by-zero guard


def test_kurtosis_known_value():
    # values=[1,2,3,4,10]，population kurtosis（非超額）手算 = 2.788
    assert S._kurtosis([1.0, 2.0, 3.0, 4.0, 10.0]) == pytest.approx(2.788, abs=1e-12)


def test_kurtosis_edge_cases():
    assert S._kurtosis([1.0, 2.0, 3.0]) is None       # n<4
    assert S._kurtosis([5.0, 5.0, 5.0, 5.0]) is None  # 零變異 guard


# ── psr_bailey_ldp / dsr_with_k ────────────────────────────────────────────

# 固定低波動正均值序列：mean=5.125, 8 點；canonical 對此 deterministic。
_PSR_SERIES = [5.0, 6.0, 4.0, 5.0, 7.0, 3.0, 5.0, 6.0]


def test_psr_known_value():
    # PSR(0) baseline（回歸 lock）：正 Sharpe + 小樣本 → 接近 1
    assert S.psr_bailey_ldp(_PSR_SERIES) == pytest.approx(
        0.9999438274272862, abs=1e-9
    )


def test_psr_edge_cases():
    assert S.psr_bailey_ldp([1.0, 2.0, 3.0]) is None     # n<4
    assert S.psr_bailey_ldp([5.0] * 8) is None           # sd=0 → div-by-zero guard


def test_dsr_known_value():
    # DSR with K=100：sr_benchmark=√(2 ln100)≈3.035；PSR penalized 後 < PSR(0)
    dsr = S.dsr_with_k(_PSR_SERIES, 100)
    assert dsr == pytest.approx(0.8441261252454011, abs=1e-9)
    # DSR 必 ≤ PSR(0)（多重比較 penalty 不可使 PSR 增加）
    assert dsr <= S.psr_bailey_ldp(_PSR_SERIES)


def test_dsr_k_le_1_returns_none():
    # K≤1 無多重比較 → None（不可回偽 DSR）
    assert S.dsr_with_k(_PSR_SERIES, 1) is None
    assert S.dsr_with_k(_PSR_SERIES, 0) is None


# ── block_bootstrap_ci（seed-deterministic 回歸 + seed 保真） ──────────────


def test_block_bootstrap_deterministic_per_seed():
    # 同 seed → byte-identical；證明 seed 是唯一隨機源
    b1 = S.block_bootstrap_ci(_PSR_SERIES, block_size=2, seed=20260515, iterations=400)
    b2 = S.block_bootstrap_ci(_PSR_SERIES, block_size=2, seed=20260515, iterations=400)
    assert b1 == b2
    assert b1 == (4.375, 5.625)


def test_block_bootstrap_seed_changes_result():
    # 不同 seed → 不同結果；故整併時 caller 必須傳歷史 seed 才能維持原報告數值
    b_15 = S.block_bootstrap_ci(_PSR_SERIES, block_size=2, seed=20260515, iterations=400)
    b_18 = S.block_bootstrap_ci(_PSR_SERIES, block_size=2, seed=20260518, iterations=400)
    assert b_15 != b_18


def test_block_bootstrap_insufficient_sample():
    # n < block_size → None
    assert S.block_bootstrap_ci([1.0, 2.0], block_size=12, seed=1) is None


def test_block_bootstrap_ci_ordering():
    lo, hi = S.block_bootstrap_ci(_PSR_SERIES, block_size=2, seed=20260515)
    assert lo <= hi


# ── wilson_ci_95（手算 reference + 邊界） ──────────────────────────────────


def test_wilson_known_value():
    # n=100, n_eff=60；Wilson 95%（z=1.96）手算 = (0.5020007846184025, 0.6906002538863971)
    lo, hi = S.wilson_ci_95(100, 60)
    assert lo == pytest.approx(0.5020007846184025, abs=1e-12)
    assert hi == pytest.approx(0.6906002538863971, abs=1e-12)


def test_wilson_bounds_within_unit_interval():
    # 邊界 p_hat→1 時 normal-approx 會越界，Wilson 必 clamp 在 [0,1]
    lo, hi = S.wilson_ci_95(5, 5)
    assert 0.0 <= lo <= hi <= 1.0


def test_wilson_edge_cases():
    assert S.wilson_ci_95(0, 0) is None     # n<=0
    assert S.wilson_ci_95(10, 11) is None   # n_eff>n
    assert S.wilson_ci_95(10, -1) is None   # n_eff<0


# ── day_bucket ─────────────────────────────────────────────────────────────


def test_day_bucket_utc():
    # 2026-05-15 12:00:00 UTC = 1778846400000 ms
    assert S.day_bucket(1778846400000) == "2026-05-15"


# ── n_eff_horizon_overlap（latent-bug fix 鎖死：ceil vs floor） ────────────


def test_n_eff_canonical_grid_matches_legacy_floor():
    # canonical grid (15/30/60)：ceil(h/5) 與舊 h//5 同值（dormant fix，0 行為改變）
    assert S.n_eff_horizon_overlap(100, 15) == 33   # ceil(15/5)=3 → 33; floor 同
    assert S.n_eff_horizon_overlap(100, 30) == 16   # ceil(30/5)=6 → 16; floor 同
    assert S.n_eff_horizon_overlap(120, 60) == 10   # ceil(60/5)=12 → 10; floor 同
    # 與舊 floor 公式在 canonical grid 上逐一比對相同
    for h in (15, 30, 60):
        assert S.n_eff_horizon_overlap(100, h) == int(100 / max(1, h // 5))


def test_n_eff_non_canonical_horizon_fixes_floor_bug():
    # 非 canonical grid (6/10/14)：ceil 正確扣 overlap，舊 floor 高估 n_eff（bug）。
    # h=14：ceil(14/5)=3 → 33（正確）；舊 floor 14//5=2 → 50（高估，over-PASS bias）
    assert S.n_eff_horizon_overlap(100, 14) == 33
    assert int(100 / max(1, 14 // 5)) == 50          # 舊 8b floor 的高估值（對照）
    assert S.n_eff_horizon_overlap(100, 14) < int(100 / max(1, 14 // 5))
    # h=6：ceil(6/5)=2 → 50；舊 floor 6//5=1 → 100（高估一倍）
    assert S.n_eff_horizon_overlap(100, 6) == 50
    assert int(100 / max(1, 6 // 5)) == 100


def test_n_eff_zero_and_tiny_horizon():
    assert S.n_eff_horizon_overlap(0, 30) == 0
    # horizon < 5 → ceil → 1，max(1,..) guard 防 div-by-zero
    assert S.n_eff_horizon_overlap(100, 1) == 100
    assert S.n_eff_horizon_overlap(100, 0) == 100   # max(1, ceil(0))=1


# ── pbo_cscv（CSCV PBO；不足樣本 + 結構） ──────────────────────────────────


def test_pbo_insufficient_days_or_candidates():
    # < 4 days 或 < 10 candidates → value=None + reason
    out = S.pbo_cscv({"c0": {"2026-05-15": 1.0}}, seed=20260516)
    assert out["value"] is None
    assert out["reason"] == "insufficient_days_or_candidates"


def test_pbo_full_enumeration_structure():
    # 10 candidates × 4 days：combo C(4,2)=6 ≤ max_splits → 全枚舉（seed 不影響）
    days = ["2026-05-1{}".format(i) for i in range(1, 5)]
    candidates = {
        "c{}".format(k): {d: float((k + i) % 3) for i, d in enumerate(days)}
        for k in range(10)
    }
    out = S.pbo_cscv(candidates, seed=20260516)
    assert out["method"] == "day_block_cscv"
    assert out["day_count"] == 4
    assert out["candidate_count"] == 10
    # value（若有 usable split）必為合法機率
    if out["value"] is not None:
        assert 0.0 <= out["value"] <= 1.0


def test_pbo_deterministic_per_seed_when_sampling():
    # 構造 day 數夠大使 combo > max_splits → 走亂數抽樣；同 seed 必 byte-identical
    days = ["2026-05-{:02d}".format(i) for i in range(1, 25)]  # 24 days，C(24,12) 極大
    candidates = {
        "c{}".format(k): {d: float((k * 7 + i) % 5) for i, d in enumerate(days)}
        for k in range(12)
    }
    out1 = S.pbo_cscv(candidates, seed=20260516, max_splits=50)
    out2 = S.pbo_cscv(candidates, seed=20260516, max_splits=50)
    assert out1 == out2
    assert out1["requested_splits"] == 50


def test_pbo_empty_input():
    out = S.pbo_cscv({}, seed=1)
    assert out["value"] is None
    assert out["day_count"] == 0
    assert out["candidate_count"] == 0


# ── pg_connect.resolve_report_dsn（DSN 解析口徑回歸；無 DB 連線） ───────────


def test_dsn_prefers_database_url(monkeypatch):
    # OPENCLAW_DATABASE_URL 存在時最高優先，直接用之
    monkeypatch.setenv("OPENCLAW_DATABASE_URL", "postgresql://x/y")
    monkeypatch.setenv("POSTGRES_USER", "ignored")
    monkeypatch.setenv("POSTGRES_PASSWORD", "ignored")
    assert PG.resolve_report_dsn() == "postgresql://x/y"


def test_dsn_builds_from_discrete_env(monkeypatch):
    # 無 OPENCLAW_DATABASE_URL → 由離散 POSTGRES_* 拼接（host 預設 127.0.0.1）
    monkeypatch.delenv("OPENCLAW_DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "svc")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw")
    monkeypatch.setenv("POSTGRES_HOST", "10.0.0.5")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_DB", "trade")
    assert PG.resolve_report_dsn() == "postgresql://redacted@10.0.0.5:6543/trade"


def test_dsn_host_port_defaults(monkeypatch):
    # host / port 缺省 → 127.0.0.1 / 5432（禁硬編碼但有保守預設）
    for k in ("OPENCLAW_DATABASE_URL", "POSTGRES_HOST", "POSTGRES_PORT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    assert PG.resolve_report_dsn() == "postgresql://redacted@127.0.0.1:5432/d"


def test_dsn_loads_missing_password_from_secrets_env(monkeypatch, tmp_path):
    # ssh 直 invoke 沒 source secrets 時，從 canonical env file 只補 POSTGRES_PASSWORD。
    secrets_root = tmp_path / "secrets"
    env_dir = secrets_root / "environment_files"
    env_dir.mkdir(parents=True)
    (env_dir / "basic_system_services.env").write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD='secret=pw'",
                "POSTGRES_HOST=should_not_be_loaded",
            ]
        ),
        encoding="utf-8",
    )
    for k in (
        "OPENCLAW_DATABASE_URL",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OPENCLAW_SECRETS_ROOT", str(secrets_root))
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_DB", "d")

    assert PG.resolve_report_dsn() == "postgresql://redacted@127.0.0.1:5432/d"
    assert "POSTGRES_HOST" not in os.environ


def test_dsn_does_not_override_existing_password(monkeypatch, tmp_path):
    secrets_root = tmp_path / "secrets"
    env_dir = secrets_root / "environment_files"
    env_dir.mkdir(parents=True)
    (env_dir / "basic_system_services.env").write_text(
        "POSTGRES_PASSWORD=file_pw\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENCLAW_DATABASE_URL", raising=False)
    monkeypatch.setenv("OPENCLAW_SECRETS_ROOT", str(secrets_root))
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "env_pw")
    monkeypatch.setenv("POSTGRES_DB", "d")

    assert PG.resolve_report_dsn() == "postgresql://redacted@127.0.0.1:5432/d"
