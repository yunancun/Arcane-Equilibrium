"""
Unit tests for LinUCB batch trainer (Phase 4 task 4-05).
LinUCB 批次訓練器單元測試（Phase 4 子任務 4-05）。

Math, BYTEA codec, and feature_schema_hash are pinned against the Rust 4-04
contract — these tests are the cross-language tripwire. Live PG paths are
exercised only via mocks.
數學公式、BYTEA 編碼、feature_schema_hash 均對 Rust 4-04 契約做釘樁，
是跨語言對拍 tripwire。Live PG 路徑只透過 mock 驅動。
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from ml_training.linucb_trainer import (
    LinUcbTrainConfig,
    TrainResult,
    _le_bytes_to_ndarray,
    _ndarray_to_le_bytes,
    compute_feature_schema_hash,
    enumerate_v1_15_arm_ids,
    train_arm,
)


# ---------------------------------------------------------------------------
# feature_schema_hash — pinned to Rust schema_hash.rs
# feature_schema_hash — 對 Rust schema_hash.rs 釘樁
# ---------------------------------------------------------------------------


def test_compute_feature_schema_hash_deterministic():
    h1 = compute_feature_schema_hash(["atr", "rsi", "regime"])
    h2 = compute_feature_schema_hash(["atr", "rsi", "regime"])
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert len(h1) == len("sha256:") + 16


def test_compute_feature_schema_hash_order_sensitive():
    h1 = compute_feature_schema_hash(["atr", "rsi"])
    h2 = compute_feature_schema_hash(["rsi", "atr"])
    assert h1 != h2


def test_compute_feature_schema_hash_matches_rust_format():
    """Hardcoded expected hash for ["price","volume","atr"].
    對 ["price","volume","atr"] 的硬編碼期望雜湊。

    Rust formula (schema_hash.rs):
        for name in names: hasher.update(name); hasher.update(b"\n")
        return "sha256:" + hex(digest)[:16]

    Independently computed in Python here so any drift in either side breaks
    this test. Treat this hash as the cross-language pin.
    Python 端獨立計算同樣公式並對比硬編碼值，任一側漂移都會打破此測試。
    此 hash 即為跨語言對拍釘樁。
    """
    hardcoded_expected = "sha256:07fe5f19cb66a0af"
    actual = compute_feature_schema_hash(["price", "volume", "atr"])
    assert actual == hardcoded_expected, (
        f"Cross-language schema hash drift: got {actual} expected {hardcoded_expected}"
    )

    # Sanity: re-derive from raw sha256 to confirm formula intent.
    raw = hashlib.sha256(b"price\nvolume\natr\n").hexdigest()[:16]
    assert actual == "sha256:" + raw


def test_compute_feature_schema_hash_empty_list():
    # sha256("") prefix / 空輸入也應穩定
    h = compute_feature_schema_hash([])
    assert h == "sha256:" + hashlib.sha256(b"").hexdigest()[:16]


# ---------------------------------------------------------------------------
# train_arm — math/§1.3.1
# train_arm — 數學公式 §1.3.1
# ---------------------------------------------------------------------------


def _cfg(d=3, lam=1.0):
    return LinUcbTrainConfig(context_dim=d, lambda_ridge=lam, feature_names=[f"f{i}" for i in range(d)])


def test_train_arm_identity_prior_when_empty():
    cfg = _cfg(d=4, lam=1.0)
    A, b, n, cr = train_arm([], cfg)
    np.testing.assert_array_almost_equal(A, np.eye(4))
    np.testing.assert_array_almost_equal(b, np.zeros(4))
    assert n == 0
    assert cr == 0.0


def test_train_arm_single_observation():
    cfg = _cfg(d=3, lam=1.0)
    x = [1.0, 2.0, 3.0]
    r = 0.5
    A, b, n, cr = train_arm([(x, r)], cfg)
    expected_A = np.eye(3) + np.outer(x, x)
    expected_b = r * np.array(x)
    np.testing.assert_array_almost_equal(A, expected_A)
    np.testing.assert_array_almost_equal(b, expected_b)
    assert n == 1
    assert cr == pytest.approx(0.5)


def test_train_arm_accumulates_correctly():
    cfg = _cfg(d=2, lam=1.0)
    obs = [
        ([1.0, 0.0], 1.0),
        ([0.0, 1.0], 2.0),
        ([1.0, 1.0], -0.5),
    ]
    A, b, n, cr = train_arm(obs, cfg)
    expected_A = np.eye(2)
    expected_b = np.zeros(2)
    for x_l, r in obs:
        x = np.array(x_l)
        expected_A = expected_A + np.outer(x, x)
        expected_b = expected_b + r * x
    np.testing.assert_array_almost_equal(A, expected_A)
    np.testing.assert_array_almost_equal(b, expected_b)
    assert n == 3
    assert cr == pytest.approx(2.5)


def test_train_arm_below_min_samples_returns_n_pulls():
    cfg = LinUcbTrainConfig(
        context_dim=2,
        lambda_ridge=1.0,
        feature_names=["a", "b"],
        min_samples_per_arm=10,
    )
    A, b, n, cr = train_arm([([1.0, 1.0], 0.1)], cfg)
    assert n == 1  # records pull count even though below min / 仍記錄即使不足
    converged = n >= cfg.min_samples_per_arm
    assert converged is False


def test_train_arm_negative_reward_handled():
    cfg = _cfg(d=2)
    A, b, n, cr = train_arm([([1.0, 0.0], -2.0)], cfg)
    assert b[0] == pytest.approx(-2.0)
    assert b[1] == pytest.approx(0.0)
    assert cr == pytest.approx(-2.0)


def test_train_arm_skips_malformed_rows():
    cfg = _cfg(d=3)
    obs = [
        ([1.0, 2.0], 1.0),       # wrong dim, dropped / 維度錯，丟棄
        ([1.0, 2.0, 3.0], 0.5),  # ok
        (None, 0.7),             # None, dropped / None 丟棄
    ]
    A, b, n, cr = train_arm(obs, cfg)  # type: ignore[arg-type]
    assert n == 1
    assert cr == pytest.approx(0.5)


def test_lambda_ridge_in_a_diagonal():
    cfg = LinUcbTrainConfig(context_dim=4, lambda_ridge=2.5, feature_names=["a", "b", "c", "d"])
    A, _, _, _ = train_arm([], cfg)
    for i in range(4):
        assert A[i, i] == pytest.approx(2.5)
        for j in range(4):
            if i != j:
                assert A[i, j] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# BYTEA codec — pinned to Rust state_io.rs little-endian f64
# BYTEA 編碼 — 對 Rust state_io.rs 小端 f64 釘樁
# ---------------------------------------------------------------------------


def test_bytea_serialization_round_trip():
    rng = np.random.default_rng(42)
    A = rng.standard_normal((5, 5)).astype(np.float64)
    b = rng.standard_normal(5).astype(np.float64)

    a_bytes = _ndarray_to_le_bytes(A)
    b_bytes = _ndarray_to_le_bytes(b)
    assert len(a_bytes) == 5 * 5 * 8
    assert len(b_bytes) == 5 * 8

    A_back = _le_bytes_to_ndarray(a_bytes, (5, 5))
    b_back = _le_bytes_to_ndarray(b_bytes, (5,))
    np.testing.assert_array_equal(A, A_back)
    np.testing.assert_array_equal(b, b_back)


def test_bytea_layout_matches_rust_le_f64():
    """A 2x2 matrix [[1.0, 2.0],[3.0, 4.0]] must serialize as 32 bytes,
    little-endian f64, row-major (1,2,3,4) — same as Rust f64_vec_to_bytes
    on a row-major Vec<f64>.
    2x2 矩陣必須以小端 f64、row-major 順序輸出 32 bytes，與 Rust
    f64_vec_to_bytes 對 row-major Vec<f64> 的輸出一致。
    """
    A = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    blob = _ndarray_to_le_bytes(A)
    assert len(blob) == 32
    expected = b"".join(np.float64(v).tobytes() for v in (1.0, 2.0, 3.0, 4.0))
    assert blob == expected
    # Manual little-endian check on first f64 / 對第一個 f64 手動小端驗證
    import struct
    assert struct.unpack("<d", blob[:8])[0] == 1.0
    assert struct.unpack("<d", blob[8:16])[0] == 2.0


# ---------------------------------------------------------------------------
# Dataclass / driver helpers
# 資料類與驅動 helper
# ---------------------------------------------------------------------------


def test_train_result_dataclass_fields_present():
    r = TrainResult(
        arm_id="trending__ma_crossover",
        n_pulls_before=0,
        n_pulls_after=42,
        cumulative_reward=1.23,
        converged=True,
    )
    assert r.arm_id == "trending__ma_crossover"
    assert r.n_pulls_before == 0
    assert r.n_pulls_after == 42
    assert r.cumulative_reward == pytest.approx(1.23)
    assert r.converged is True


def test_enumerate_v1_15_returns_15_unique_ids():
    ids = enumerate_v1_15_arm_ids()
    assert len(ids) == 15
    assert len(set(ids)) == 15
    # Format check: regime__strategy
    for arm_id in ids:
        assert "__" in arm_id
        regime, strat = arm_id.split("__", 1)
        assert regime in {"trending", "ranging", "volatile"}
        assert strat  # non-empty
