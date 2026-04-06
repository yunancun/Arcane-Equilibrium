"""LinUCB hierarchical warm-start migration (Q3 / math_implementation_notes Entry 01).

LinUCB 階層式 warm-start 遷移（Q3 / 數學筆記 Entry 01）。

MODULE_NOTE (EN):
    Three operations on linucb_state aligned with math_notes Entry 01 §1.3:
        - migrate_expand_arm_space:   V1 (N1 arms) -> V2 (N2 > N1) using §1.3.3
        - migrate_collapse_arm_space: V2 -> V1 using §1.3.4 (exact, sum-pooling)
        - pad_feature_dim:            d_v1 -> d_v2 using §1.3.5 (block-identity)
    All operations:
        - Archive current state to learning.linucb_state_archive (config.archive)
        - Write a row to learning.linucb_migrations (audit log)
        - Compute feature_schema_hash and persist on the new rows
        - Hard-fail boundaries (§1.3.6):
            * reward redefinition (caller-managed marker, not enforced here)
            * schema_hash drift -> ValueError, abort
            * parent n_pulls < min_parent_pulls -> child cold-start (NOT abort)
            * regime structure break -> operator-triggered γ ≈ 0.1 (config.gamma)
    BYTEA codec and feature_schema_hash are imported directly from
    linucb_trainer (4-05) so all 3 layers (Rust 4-04 / Python trainer 4-05 /
    Python migration 4-06) share one byte layout.

MODULE_NOTE (中):
    對 linucb_state 的三類遷移操作，數學嚴格對齊 math_notes Entry 01 §1.3：
        - migrate_expand_arm_space:   升維（V1 N1 arms -> V2 N2 arms），§1.3.3
        - migrate_collapse_arm_space: 降維（V2 -> V1），§1.3.4 精確 sum-pooling
        - pad_feature_dim:            特徵維度填充，§1.3.5 block-identity
    所有操作均：
        - 將當前 state 歸檔到 learning.linucb_state_archive（cfg.archive 控制）
        - 寫一筆審計到 learning.linucb_migrations
        - 計算 feature_schema_hash 並持久化到新 row
        - 硬邊界（§1.3.6）：
            * reward 重定義（呼叫端 marker，本檔不強制）
            * schema_hash 漂移 -> ValueError 中止
            * 父 arm n_pulls < min_parent_pulls -> 子 arm 退回 cold start（非中止）
            * 黑天鵝結構斷裂 -> 由 operator 設 γ ≈ 0.1
    BYTEA codec 與 feature_schema_hash 從 4-05 trainer 直接 import，
    確保 Rust 4-04 / Python trainer 4-05 / Python migration 4-06 三層共用同一 byte 佈局。

Safety / 安全：
    - Read-only fall-through: if numpy or psycopg2 missing, raises at call time
      (not import time), so unit tests can still import without DB.
    - All SQL is parameterized.
    - No hard-coded paths (CLAUDE.md §七 cross-platform rule).
    - Live PG paths are exercised only via mocks in tests.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:
    import psycopg2  # type: ignore
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]

# Import codec + schema hash from 4-05 trainer to guarantee byte alignment
# 從 4-05 trainer 引入 BYTEA codec 與 schema hash，確保 byte 對齊
from ml_training.linucb_trainer import (
    _le_bytes_to_ndarray,
    _ndarray_to_le_bytes,
    compute_feature_schema_hash,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config / result dataclasses
# 配置與結果資料類
# ---------------------------------------------------------------------------


@dataclass
class WarmStartConfig:
    """Hierarchical warm-start config. / 階層式 warm-start 配置。

    Attributes:
        gamma: §1.3.3 inheritance discount γ ∈ [0, 1]. 0.5 default; 0.1 for
            regime structure break (§1.3.6 case 4). / 繼承折扣 γ。
        lambda_ridge: ridge prior strength (A_init = λ I). / ridge 先驗強度。
        min_parent_pulls: §1.3.6 case 3 — children of parents below this fall
            back to cold-start. / 父 arm 樣本低於此值則子 arm 降為冷啟動。
        archive: archive previous state before migration. / 遷移前是否歸檔。
    """

    gamma: float = 0.5
    lambda_ridge: float = 1.0
    min_parent_pulls: int = 30
    archive: bool = True


@dataclass
class MigrationReport:
    """Per-migration summary. / 單次遷移摘要。"""

    migration_id: int
    direction: str  # 'expand' / 'collapse' / 'feature_pad'
    n_arms_before: int
    n_arms_after: int
    skipped_cold_start: int  # children that fell back to cold-start / 退回冷啟動的子 arm 數
    elapsed_ms: int


# ---------------------------------------------------------------------------
# Pure math kernels (§1.3.3 / §1.3.4 / §1.3.5)
# 純數學核心 — 不依賴 DB，便於單元測試
# ---------------------------------------------------------------------------


def expand_parent_to_children(
    A_p,
    b_p,
    n_pulls_p: int,
    cumulative_reward_p: float,
    k: int,
    gamma: float,
    lambda_ridge: float,
    min_parent_pulls: int,
):
    """§1.3.3 升維公式 / expansion formula.

    Returns one (A_c, b_c, n_c, R_c) tuple per child (K identical copies — the
    formula is symmetric across siblings).

    A_c = λI + (γ/K) · (A_p - λI)
    b_c = (γ/K) · b_p
    n_c = floor(γ · n_pulls_p / K)
    R_c = γ · cumulative_reward_p / K

    If n_pulls_p < min_parent_pulls, return cold-start (§1.3.6 case 3):
        A_c = λI, b_c = 0, n_c = 0, R_c = 0
        and the second item of the returned tuple = True (cold_start flag).

    若父 n_pulls 不足 min_parent_pulls，子 arm 退回冷啟動。
    """
    d = A_p.shape[0]
    if n_pulls_p < min_parent_pulls:
        A_c = lambda_ridge * np.eye(d, dtype=np.float64)
        b_c = np.zeros(d, dtype=np.float64)
        return A_c, b_c, 0, 0.0, True

    scale = gamma / float(k)
    A_c = lambda_ridge * np.eye(d, dtype=np.float64) + scale * (
        A_p - lambda_ridge * np.eye(d, dtype=np.float64)
    )
    b_c = scale * b_p
    n_c = int(math.floor(gamma * n_pulls_p / float(k)))
    R_c = gamma * cumulative_reward_p / float(k)
    return A_c, b_c, n_c, R_c, False


def collapse_children_to_parent(children_states, lambda_ridge: float):
    """§1.3.4 降維公式 / exact sum-pooling.

    Args:
        children_states: list of (A_c, b_c, n_c, R_c) tuples.
        lambda_ridge: λ.

    Returns:
        (A_p, b_p, n_p, R_p)

    A_p = λI + Σ_c (A_c - λI)
    b_p = Σ_c b_c
    n_p = Σ_c n_c
    R_p = Σ_c R_c

    Exact (zero information loss across the chosen partition).
    """
    if not children_states:
        raise ValueError("children_states empty / 子 arm 列表為空")
    d = children_states[0][0].shape[0]
    A_p = lambda_ridge * np.eye(d, dtype=np.float64)
    b_p = np.zeros(d, dtype=np.float64)
    n_p = 0
    R_p = 0.0
    for A_c, b_c, n_c, R_c in children_states:
        A_p = A_p + (A_c - lambda_ridge * np.eye(d, dtype=np.float64))
        b_p = b_p + b_c
        n_p += int(n_c)
        R_p += float(R_c)
    return A_p, b_p, n_p, R_p


def pad_arm_feature_dim(A_v1, b_v1, k_new: int, lambda_ridge: float):
    """§1.3.5 block-identity padding / orthogonal feature pad.

    A_v2 = block_diag(A_v1, λ·I_k)   shape (d+k, d+k)
    b_v2 = [b_v1; 0_k]               shape (d+k,)

    Old features keep all learned mass; new features start at ridge prior.
    對舊 feature 完全保留學習；新 feature 從 ridge prior 起步。
    """
    d = A_v1.shape[0]
    new_d = d + k_new
    A_v2 = np.zeros((new_d, new_d), dtype=np.float64)
    A_v2[:d, :d] = A_v1
    for i in range(k_new):
        A_v2[d + i, d + i] = lambda_ridge
    b_v2 = np.zeros(new_d, dtype=np.float64)
    b_v2[:d] = b_v1
    return A_v2, b_v2


# ---------------------------------------------------------------------------
# DB IO helpers (mockable surface)
# DB IO 輔助 — 全部可被測試 mock
# ---------------------------------------------------------------------------


def _connect(dsn: str):  # pragma: no cover — live path
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed / psycopg2 未安裝")
    return psycopg2.connect(dsn)


def _archive_version(conn, from_version: str, reason: str) -> None:
    """Copy all rows of from_version to linucb_state_archive.
    將 from_version 全部 row 拷貝至 linucb_state_archive。
    """
    sql = """
        INSERT INTO learning.linucb_state_archive
            (arm_id, arm_space_version, parent_arm_id, inheritance_gamma,
             feature_schema_hash, a_matrix, b_vector, context_dim, n_pulls,
             archived_ts, archive_reason)
        SELECT arm_id, arm_space_version, parent_arm_id, inheritance_gamma,
               feature_schema_hash, a_matrix, b_vector, context_dim, n_pulls,
               NOW(), %s
          FROM learning.linucb_state
         WHERE arm_space_version = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (reason, from_version))


def _load_arm(conn, arm_id: str, version: str):
    """Load (A, b, n_pulls, cumulative_reward, feature_schema_hash, dim) for one arm.
    讀取單個 arm 完整 state。
    """
    sql = """
        SELECT a_matrix, b_vector, context_dim, n_pulls, feature_schema_hash
          FROM learning.linucb_state
         WHERE arm_id = %s AND arm_space_version = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (arm_id, version))
        row = cur.fetchone()
    if row is None:
        return None
    a_blob, b_blob, dim, n_pulls, schema_hash = row
    A = _le_bytes_to_ndarray(bytes(a_blob), (dim, dim))
    b = _le_bytes_to_ndarray(bytes(b_blob), (dim,))
    return A, b, int(n_pulls), 0.0, schema_hash, int(dim)


def _upsert_child(
    conn,
    arm_id: str,
    version: str,
    parent_arm_id: Optional[str],
    gamma: Optional[float],
    schema_hash: str,
    A,
    b,
    n_pulls: int,
) -> None:
    """Upsert one child arm into linucb_state.
    UPSERT 一個子 arm 到 linucb_state。
    """
    a_bytes = _ndarray_to_le_bytes(A)
    b_bytes = _ndarray_to_le_bytes(b)
    dim = int(b.shape[0])
    sql = """
        INSERT INTO learning.linucb_state
            (arm_id, arm_space_version, parent_arm_id, inheritance_gamma,
             feature_schema_hash, a_matrix, b_vector, context_dim, n_pulls,
             last_updated_ts)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (arm_id, arm_space_version) DO UPDATE SET
            parent_arm_id = EXCLUDED.parent_arm_id,
            inheritance_gamma = EXCLUDED.inheritance_gamma,
            feature_schema_hash = EXCLUDED.feature_schema_hash,
            a_matrix = EXCLUDED.a_matrix,
            b_vector = EXCLUDED.b_vector,
            context_dim = EXCLUDED.context_dim,
            n_pulls = EXCLUDED.n_pulls,
            last_updated_ts = NOW()
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                arm_id,
                version,
                parent_arm_id,
                gamma,
                schema_hash,
                psycopg2.Binary(a_bytes) if psycopg2 is not None else a_bytes,
                psycopg2.Binary(b_bytes) if psycopg2 is not None else b_bytes,
                dim,
                int(n_pulls),
            ),
        )


def _log_migration(
    conn,
    from_version: str,
    to_version: str,
    direction: str,
    gamma: Optional[float],
    n_arms_before: int,
    n_arms_after: int,
    notes: str,
) -> int:
    """Insert audit row, return migration_id.
    寫入審計 row 並返回 migration_id。
    """
    sql = """
        INSERT INTO learning.linucb_migrations
            (from_version, to_version, direction, gamma,
             n_arms_before, n_arms_after, started_ts, finished_ts, notes)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), %s)
        RETURNING migration_id
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                from_version,
                to_version,
                direction,
                gamma,
                n_arms_before,
                n_arms_after,
                notes,
            ),
        )
        return int(cur.fetchone()[0])


# ---------------------------------------------------------------------------
# Public migration entrypoints
# 公開遷移入口
# ---------------------------------------------------------------------------


def migrate_expand_arm_space(
    dsn: str,
    from_version: str,
    to_version: str,
    parent_to_children: dict,
    cfg: WarmStartConfig,
    feature_names: Optional[list] = None,
    _conn=None,  # injected by tests / 測試注入
) -> MigrationReport:
    """Expand V1 -> V2 via §1.3.3 hierarchical warm-start.
    通過 §1.3.3 階層式 warm-start 將 V1 升維到 V2。

    Args:
        dsn: PG dsn (ignored if _conn injected).
        from_version: e.g. "v1_15".
        to_version: e.g. "v2_25".
        parent_to_children: {parent_arm_id: [child arm_id list]}.
        cfg: WarmStartConfig.
        feature_names: feature name list for new rows' schema_hash. If None,
            inherits parent's hash (assumed schema unchanged).
        _conn: optional pre-built connection (testing only).

    Returns:
        MigrationReport.
    """
    if np is None:
        raise RuntimeError("numpy not installed / numpy 未安裝")

    started = time.time()
    own_conn = _conn is None
    conn = _conn if _conn is not None else _connect(dsn)
    skipped = 0
    n_after = 0
    n_before_total = len(parent_to_children)
    inherited_hash: Optional[str] = None
    try:
        if cfg.archive:
            _archive_version(conn, from_version, reason=f"expand_{from_version}_to_{to_version}")

        for parent_id, children in parent_to_children.items():
            loaded = _load_arm(conn, parent_id, from_version)
            if loaded is None:
                logger.warning("expand: parent %s not found in %s", parent_id, from_version)
                continue
            A_p, b_p, n_p, R_p, parent_hash, _dim = loaded
            inherited_hash = inherited_hash or parent_hash

            k = len(children)
            if k == 0:
                continue
            for child_id in children:
                A_c, b_c, n_c, _R_c, cold = expand_parent_to_children(
                    A_p, b_p, n_p, R_p, k, cfg.gamma, cfg.lambda_ridge, cfg.min_parent_pulls
                )
                if cold:
                    skipped += 1
                target_hash = (
                    compute_feature_schema_hash(feature_names) if feature_names else parent_hash
                )
                # §1.3.6 case 2 — schema drift fail-closed
                if feature_names and target_hash != parent_hash:
                    raise ValueError(
                        f"feature_schema_hash drift parent={parent_hash} target={target_hash} — "
                        f"fail-closed (§1.3.6 case 2)"
                    )
                _upsert_child(
                    conn,
                    child_id,
                    to_version,
                    parent_id,
                    cfg.gamma,
                    target_hash,
                    A_c,
                    b_c,
                    n_c,
                )
                n_after += 1

        mid = _log_migration(
            conn,
            from_version,
            to_version,
            "expand",
            cfg.gamma,
            n_before_total,
            n_after,
            notes=f"skipped_cold_start={skipped}",
        )
        if hasattr(conn, "commit"):
            conn.commit()
    finally:
        if own_conn and hasattr(conn, "close"):
            conn.close()

    return MigrationReport(
        migration_id=mid,
        direction="expand",
        n_arms_before=n_before_total,
        n_arms_after=n_after,
        skipped_cold_start=skipped,
        elapsed_ms=int((time.time() - started) * 1000),
    )


def migrate_collapse_arm_space(
    dsn: str,
    from_version: str,
    to_version: str,
    children_to_parent: dict,
    cfg: WarmStartConfig,
    feature_names: Optional[list] = None,
    _conn=None,
) -> MigrationReport:
    """Collapse V2 -> V1 via §1.3.4 exact sum-pooling.
    通過 §1.3.4 精確 sum-pooling 將 V2 降維到 V1。

    Args:
        children_to_parent: {child_arm_id: parent_arm_id}.
    """
    if np is None:
        raise RuntimeError("numpy not installed / numpy 未安裝")

    started = time.time()
    own_conn = _conn is None
    conn = _conn if _conn is not None else _connect(dsn)
    n_before = len(children_to_parent)
    n_after = 0
    inherited_hash: Optional[str] = None
    try:
        if cfg.archive:
            _archive_version(conn, from_version, reason=f"collapse_{from_version}_to_{to_version}")

        # group children per parent / 按 parent 分組
        parent_to_children: dict = {}
        for child_id, parent_id in children_to_parent.items():
            parent_to_children.setdefault(parent_id, []).append(child_id)

        for parent_id, children in parent_to_children.items():
            states = []
            parent_hash: Optional[str] = None
            for child_id in children:
                loaded = _load_arm(conn, child_id, from_version)
                if loaded is None:
                    continue
                A_c, b_c, n_c, _R_c, schema_hash, _dim = loaded
                parent_hash = parent_hash or schema_hash
                inherited_hash = inherited_hash or schema_hash
                # §1.3.6 case 2 fail-closed
                if schema_hash != parent_hash:
                    raise ValueError(
                        f"feature_schema_hash drift across siblings: {schema_hash} vs {parent_hash}"
                    )
                states.append((A_c, b_c, n_c, 0.0))
            if not states:
                continue
            A_p, b_p, n_p, _R_p = collapse_children_to_parent(states, cfg.lambda_ridge)
            target_hash = (
                compute_feature_schema_hash(feature_names) if feature_names else parent_hash
            )
            _upsert_child(
                conn,
                parent_id,
                to_version,
                None,
                None,
                target_hash,
                A_p,
                b_p,
                n_p,
            )
            n_after += 1

        mid = _log_migration(
            conn,
            from_version,
            to_version,
            "collapse",
            None,
            n_before,
            n_after,
            notes="exact_sum_pooling",
        )
        if hasattr(conn, "commit"):
            conn.commit()
    finally:
        if own_conn and hasattr(conn, "close"):
            conn.close()

    return MigrationReport(
        migration_id=mid,
        direction="collapse",
        n_arms_before=n_before,
        n_arms_after=n_after,
        skipped_cold_start=0,
        elapsed_ms=int((time.time() - started) * 1000),
    )


def pad_feature_dim(
    dsn: str,
    arm_space_version: str,
    new_feature_count: int,
    new_feature_names: list,
    cfg: WarmStartConfig,
    arm_ids: Optional[list] = None,
    _conn=None,
) -> MigrationReport:
    """Pad feature dim via §1.3.5 block-identity expansion.
    通過 §1.3.5 block-identity 對所有 arm 做特徵維度填充。

    Args:
        new_feature_count: number of new feature columns to append.
        new_feature_names: full new feature name list (used for hash recompute).
        arm_ids: restrict to a subset of arms; None = all in version.
    """
    if np is None:
        raise RuntimeError("numpy not installed / numpy 未安裝")

    started = time.time()
    own_conn = _conn is None
    conn = _conn if _conn is not None else _connect(dsn)
    n_after = 0
    try:
        if cfg.archive:
            _archive_version(conn, arm_space_version, reason=f"feature_pad_{arm_space_version}")

        # Determine arm list / 決定 arm 列表
        if arm_ids is None:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT arm_id FROM learning.linucb_state WHERE arm_space_version = %s",
                    (arm_space_version,),
                )
                arm_ids = [r[0] for r in cur.fetchall()]

        new_hash = compute_feature_schema_hash(new_feature_names)

        for arm_id in arm_ids:
            loaded = _load_arm(conn, arm_id, arm_space_version)
            if loaded is None:
                continue
            A_v1, b_v1, n_pulls, _R, _old_hash, _dim = loaded
            A_v2, b_v2 = pad_arm_feature_dim(A_v1, b_v1, new_feature_count, cfg.lambda_ridge)
            _upsert_child(
                conn,
                arm_id,
                arm_space_version,
                None,
                None,
                new_hash,
                A_v2,
                b_v2,
                n_pulls,
            )
            n_after += 1

        mid = _log_migration(
            conn,
            arm_space_version,
            arm_space_version,
            "feature_pad",
            None,
            len(arm_ids),
            n_after,
            notes=f"new_feature_count={new_feature_count}",
        )
        if hasattr(conn, "commit"):
            conn.commit()
    finally:
        if own_conn and hasattr(conn, "close"):
            conn.close()

    return MigrationReport(
        migration_id=mid,
        direction="feature_pad",
        n_arms_before=len(arm_ids),
        n_arms_after=n_after,
        skipped_cold_start=0,
        elapsed_ms=int((time.time() - started) * 1000),
    )
