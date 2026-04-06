"""Unit tests for LinUCB hierarchical warm-start migration (Phase 4 task 4-06).

LinUCB 階層式 warm-start 遷移測試 — 嚴格對齊 math_notes Entry 01 §1.3。
所有 live PG 路徑均透過 MockConn 驅動，不連線真實 DB。
"""

from __future__ import annotations

import numpy as np
import pytest

from ml_training.linucb_arm_migration import (
    MigrationReport,
    WarmStartConfig,
    collapse_children_to_parent,
    expand_parent_to_children,
    migrate_expand_arm_space,
    pad_arm_feature_dim,
)
from ml_training.linucb_trainer import _ndarray_to_le_bytes


# ---------------------------------------------------------------------------
# MockConn — minimal psycopg2-compatible surface for migration tests
# MockConn — migration 測試用的最小 psycopg2 相容介面
# ---------------------------------------------------------------------------


class MockCursor:
    def __init__(self, store):
        self.store = store
        self._last = None

    def execute(self, sql, params=()):
        self._last = (sql.strip(), params)
        sql_l = sql.strip().lower()
        # Dispatcher — very narrow matching, pattern-based
        if sql_l.startswith("select a_matrix, b_vector, context_dim, n_pulls, feature_schema_hash"):
            arm_id, version = params
            self._result = self.store["state"].get((arm_id, version))
        elif sql_l.startswith("insert into learning.linucb_state\n"):
            (
                arm_id,
                version,
                parent_arm_id,
                gamma,
                schema_hash,
                a_bytes_wrap,
                b_bytes_wrap,
                dim,
                n_pulls,
            ) = params
            a_b = bytes(a_bytes_wrap) if hasattr(a_bytes_wrap, "__bytes__") else a_bytes_wrap
            b_b = bytes(b_bytes_wrap) if hasattr(b_bytes_wrap, "__bytes__") else b_bytes_wrap
            self.store["state"][(arm_id, version)] = (
                a_b,
                b_b,
                int(dim),
                int(n_pulls),
                schema_hash,
            )
            self.store["upserts"].append(
                {
                    "arm_id": arm_id,
                    "version": version,
                    "parent_arm_id": parent_arm_id,
                    "gamma": gamma,
                    "schema_hash": schema_hash,
                    "n_pulls": int(n_pulls),
                    "dim": int(dim),
                }
            )
        elif sql_l.startswith("insert into learning.linucb_state_archive"):
            self.store["archived"].append(params)
        elif sql_l.startswith("insert into learning.linucb_migrations"):
            self.store["migrations"].append(params)
            self.store["_last_mid"] = len(self.store["migrations"])
            self._result = (self.store["_last_mid"],)
        elif sql_l.startswith("select arm_id from learning.linucb_state"):
            version = params[0]
            self._all = [
                (k[0],) for k in self.store["state"].keys() if k[1] == version
            ]
        else:
            raise AssertionError(f"MockCursor: unexpected SQL: {sql_l[:80]}")

    def fetchone(self):
        return getattr(self, "_result", None)

    def fetchall(self):
        return getattr(self, "_all", [])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class MockConn:
    def __init__(self):
        self.store = {
            "state": {},  # (arm_id, version) -> (a_bytes, b_bytes, dim, n_pulls, schema_hash)
            "archived": [],
            "migrations": [],
            "upserts": [],
            "_last_mid": 0,
        }
        self.committed = False
        self.closed = False

    def cursor(self):
        return MockCursor(self.store)

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def _seed_parent(mock: MockConn, arm_id: str, A, b, n_pulls: int, schema_hash: str, version: str):
    mock.store["state"][(arm_id, version)] = (
        _ndarray_to_le_bytes(A),
        _ndarray_to_le_bytes(b),
        int(b.shape[0]),
        int(n_pulls),
        schema_hash,
    )


# ---------------------------------------------------------------------------
# §1.3.3 expansion formula — direct kernel tests
# §1.3.3 升維公式 — 直接核心測試
# ---------------------------------------------------------------------------

LAM = 1.0
D = 3
HASH = "sha256:aaaaaaaaaaaaaaaa"


def _make_parent(n_pulls=100):
    # Handcrafted (A_p, b_p) with non-trivial off-diagonal mass
    A_p = LAM * np.eye(D) + np.array(
        [[4.0, 1.0, 0.5], [1.0, 3.0, 0.2], [0.5, 0.2, 2.0]]
    )
    b_p = np.array([1.0, 2.0, -0.5])
    return A_p, b_p, n_pulls


def test_expand_15_to_25_preserves_theta_when_gamma_1():
    """§1.3.3: γ=1 ⇒ sum of K children's (A-λI) equals parent's (A-λI).
    γ=1 時 K 個子 arm 的 sum 還原父，驗證可加性。
    """
    A_p, b_p, n_p = _make_parent(n_pulls=100)
    K = 5
    sum_A_minus_lam = np.zeros((D, D))
    sum_b = np.zeros(D)
    for _ in range(K):
        A_c, b_c, n_c, _R, cold = expand_parent_to_children(
            A_p, b_p, n_p, 10.0, K, gamma=1.0, lambda_ridge=LAM, min_parent_pulls=30
        )
        assert cold is False
        sum_A_minus_lam += A_c - LAM * np.eye(D)
        sum_b += b_c
    np.testing.assert_allclose(sum_A_minus_lam, A_p - LAM * np.eye(D), atol=1e-12)
    np.testing.assert_allclose(sum_b, b_p, atol=1e-12)


def test_expand_below_min_parent_pulls_uses_cold_start():
    """§1.3.6 case 3: n_pulls<min -> child falls back to cold start."""
    A_p, b_p, _ = _make_parent(n_pulls=100)
    A_c, b_c, n_c, R_c, cold = expand_parent_to_children(
        A_p, b_p, n_pulls_p=5, cumulative_reward_p=0.5,
        k=3, gamma=0.5, lambda_ridge=LAM, min_parent_pulls=30,
    )
    assert cold is True
    np.testing.assert_allclose(A_c, LAM * np.eye(D))
    np.testing.assert_allclose(b_c, np.zeros(D))
    assert n_c == 0
    assert R_c == 0.0


def test_expand_gamma_discount_correct():
    """γ=0.5: sum of K children's (A-λI) == 0.5 * (A_p-λI). Exact by linearity.
    γ=0.5 時 K 個子 arm 的 sum 等於 0.5 倍父。
    """
    A_p, b_p, n_p = _make_parent(n_pulls=100)
    K = 4
    gamma = 0.5
    sum_A = np.zeros((D, D))
    sum_b = np.zeros(D)
    for _ in range(K):
        A_c, b_c, _n, _R, _cold = expand_parent_to_children(
            A_p, b_p, n_p, 8.0, K, gamma=gamma, lambda_ridge=LAM, min_parent_pulls=30
        )
        sum_A += A_c - LAM * np.eye(D)
        sum_b += b_c
    np.testing.assert_allclose(sum_A, gamma * (A_p - LAM * np.eye(D)), atol=1e-12)
    np.testing.assert_allclose(sum_b, gamma * b_p, atol=1e-12)


# ---------------------------------------------------------------------------
# §1.3.4 collapse — exact sum-pooling
# ---------------------------------------------------------------------------


def test_collapse_25_to_15_exact_recovers_sum():
    """§1.3.4: collapse is exact — A_p = λI + Σ(A_c-λI), b_p = Σ b_c.
    Construct K children via expansion with γ=1; collapse must recover parent.
    用 γ=1 升維再降維必須精確還原。
    """
    A_p, b_p, n_p = _make_parent(n_pulls=200)
    K = 5
    children = []
    for _ in range(K):
        A_c, b_c, n_c, _R, _cold = expand_parent_to_children(
            A_p, b_p, n_p, 20.0, K, gamma=1.0, lambda_ridge=LAM, min_parent_pulls=30
        )
        children.append((A_c, b_c, n_c, 0.0))
    A_back, b_back, n_back, _R_back = collapse_children_to_parent(children, LAM)
    np.testing.assert_allclose(A_back, A_p, atol=1e-12)
    np.testing.assert_allclose(b_back, b_p, atol=1e-12)
    # n_pulls recovery is floor-based so allow small loss
    assert abs(n_back - n_p) <= K


# ---------------------------------------------------------------------------
# §1.3.5 block-identity feature pad
# ---------------------------------------------------------------------------


def test_pad_feature_dim_preserves_v1_block_and_adds_ridge():
    A_v1 = np.array([[5.0, 1.0], [1.0, 4.0]])
    b_v1 = np.array([0.7, -0.3])
    A_v2, b_v2 = pad_arm_feature_dim(A_v1, b_v1, k_new=3, lambda_ridge=2.0)
    # Shape / 形狀
    assert A_v2.shape == (5, 5)
    assert b_v2.shape == (5,)
    # Top-left block preserved / 左上塊保留
    np.testing.assert_allclose(A_v2[:2, :2], A_v1)
    np.testing.assert_allclose(b_v2[:2], b_v1)
    # New feature block = ridge prior / 新特徵 = ridge prior
    for i in range(3):
        for j in range(3):
            expected = 2.0 if i == j else 0.0
            assert A_v2[2 + i, 2 + j] == pytest.approx(expected)
    # Off-diagonal cross-block = 0 / 塊外為零
    assert np.allclose(A_v2[:2, 2:], 0.0)
    assert np.allclose(A_v2[2:, :2], 0.0)
    # New b dims = 0
    assert np.allclose(b_v2[2:], 0.0)


# ---------------------------------------------------------------------------
# Integration: migrate_expand_arm_space through MockConn — verify archive step
# 整合測試：migrate_expand_arm_space 走 MockConn，驗證歸檔步驟
# ---------------------------------------------------------------------------


def test_migration_archives_state_before_change_and_logs_audit():
    mock = MockConn()
    A_p, b_p, n_p = _make_parent(n_pulls=200)
    parent_id = "trending__ma_crossover"
    _seed_parent(mock, parent_id, A_p, b_p, n_p, HASH, "v1_15")

    children = [f"{parent_id}__SYM{i}" for i in range(5)]
    cfg = WarmStartConfig(gamma=1.0, lambda_ridge=LAM, min_parent_pulls=30, archive=True)
    rep = migrate_expand_arm_space(
        dsn="",
        from_version="v1_15",
        to_version="v2_25",
        parent_to_children={parent_id: children},
        cfg=cfg,
        _conn=mock,
    )
    assert isinstance(rep, MigrationReport)
    assert rep.direction == "expand"
    assert rep.n_arms_after == 5
    assert rep.skipped_cold_start == 0
    # Archive happened before upserts / 歸檔 row 存在
    assert len(mock.store["archived"]) == 1
    # 5 upserts created / 5 個子 arm upsert
    assert len(mock.store["upserts"]) == 5
    for up in mock.store["upserts"]:
        assert up["version"] == "v2_25"
        assert up["parent_arm_id"] == parent_id
        assert up["gamma"] == 1.0
        assert up["schema_hash"] == HASH
    # Audit log row / 審計 row
    assert len(mock.store["migrations"]) == 1
    assert mock.committed is True
