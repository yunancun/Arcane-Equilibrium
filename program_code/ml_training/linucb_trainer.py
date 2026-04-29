"""
LinUCB batch trainer — rebuild sufficient statistics A/b from logged decisions.
LinUCB 批次訓練器 — 從決策日誌重建充分統計量 A/b 並寫回 PG。

MODULE_NOTE (EN): Phase 4 task 4-05. Batch reads (arm, context_features, reward)
  triples from `trading.decision_context_snapshots` (joined to
  `trading.decision_outcomes` for the realized return), rebuilds the LinUCB
  ridge sufficient statistics
      A_a = lambda * I + sum_t x_t x_t^T   (d x d)
      b_a = sum_t r_t x_t                  (d)
  per arm, and upserts them into `learning.linucb_state` keyed by
  (arm_id, arm_space_version). Math, BYTEA codec, and feature_schema_hash
  are kept byte-for-byte aligned with the Rust 4-04 inference / state_io /
  schema_hash modules so that warm-start in Rust is a no-op deserialization.
MODULE_NOTE (中): Phase 4 子任務 4-05。批次從 `trading.decision_context_snapshots`
  （JOIN `trading.decision_outcomes` 取已實現回報）讀取
  (arm, context_features, reward) 三元組，逐 arm 重建 LinUCB ridge 充分統計量
      A_a = lambda * I + sum_t x_t x_t^T   (d x d)
      b_a = sum_t r_t x_t                  (d)
  並 upsert 進 `learning.linucb_state`（複合鍵 (arm_id, arm_space_version)）。
  數學公式、BYTEA 編碼、feature_schema_hash 三項均與 Rust 4-04 inference /
  state_io / schema_hash 模組逐 byte 對齊，確保 Rust 端 warm-start 等同於
  純反序列化即可使用。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover — numpy is mandatory in ml_training env
    np = None  # type: ignore[assignment]

try:
    import psycopg2  # type: ignore
    from psycopg2.extras import execute_batch  # type: ignore  # noqa: F401
except ImportError:  # pragma: no cover — DB only required for live path
    psycopg2 = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config & result dataclasses / 配置與結果資料類
# ---------------------------------------------------------------------------


@dataclass
class LinUcbTrainConfig:
    """LinUCB trainer configuration. / LinUCB 訓練器配置。

    Attributes:
        arm_space_version: composite-PK version tag, aligned with 4-04 default.
            複合主鍵版本標籤，對齊 4-04 預設。
        context_dim: feature vector dimension d. / 特徵向量維度 d。
        lambda_ridge: ridge prior strength (A starts as lambda*I).
            ridge 先驗強度（A 初始化為 lambda*I）。
        feature_names: ordered feature names — drives feature_schema_hash and
            must match Rust side exactly. / 特徵名有序列表，驅動 schema hash，
            必須與 Rust 側完全一致。
        cpcv_embargo_hours: temporal embargo aligned with Phase 3b CPCV.
            與 Phase 3b CPCV 對齊的時間禁區（小時）。
        min_samples_per_arm: convergence floor; arms below this are still
            persisted but flagged converged=False.
            收斂下限；少於此數的 arm 仍會寫入但 converged=False。
        reward_column: which decision_outcomes column to use as r_t.
            作為 r_t 的 decision_outcomes 欄位名。
    """

    arm_space_version: str = "v1_15"
    context_dim: int = 8
    lambda_ridge: float = 1.0
    feature_names: list[str] = field(default_factory=list)
    cpcv_embargo_hours: int = 24
    min_samples_per_arm: int = 10
    reward_column: str = "outcome_1h"


@dataclass
class TrainResult:
    """Per-arm training result summary. / 單 arm 訓練結果摘要。"""

    arm_id: str
    n_pulls_before: int
    n_pulls_after: int
    cumulative_reward: float
    converged: bool


# ---------------------------------------------------------------------------
# Feature schema hash — must reproduce Rust schema_hash.rs byte-for-byte
# 特徵 schema 雜湊 — 必須與 Rust schema_hash.rs 逐 byte 重現
# ---------------------------------------------------------------------------


def compute_feature_schema_hash(feature_names: list[str]) -> str:
    """Compute "sha256:<first 16 hex>" of newline-joined feature names.
    計算換行串接後特徵名的 "sha256:<前 16 十六進制>"。

    Mirrors Rust `compute_feature_schema_hash` in
    `rust/openclaw_engine/src/linucb/schema_hash.rs`:
        for name in names: hasher.update(name); hasher.update("\n")
        return "sha256:" + hex(digest)[:16]
    對應 Rust 同名函數，逐 byte 對齊。
    """
    h = hashlib.sha256()
    for name in feature_names:
        h.update(name.encode("utf-8"))
        h.update(b"\n")
    return "sha256:" + h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# BYTEA codec — must reproduce Rust state_io.rs little-endian f64 layout
# BYTEA 編碼 — 必須與 Rust state_io.rs 的小端 f64 佈局一致
# ---------------------------------------------------------------------------


def _ndarray_to_le_bytes(arr) -> bytes:
    """Serialize numpy array to little-endian f64 row-major bytes.
    序列化 numpy 陣列為小端 f64、row-major bytes。

    Rust counterpart: `f64_vec_to_bytes` writes each f64 via `to_le_bytes`,
    flattened in row-major order for matrices.
    對應 Rust `f64_vec_to_bytes`：每個 f64 走 `to_le_bytes`，矩陣為 row-major。
    """
    contiguous = np.ascontiguousarray(arr, dtype="<f8")  # row-major little-endian
    return contiguous.tobytes(order="C")


def _le_bytes_to_ndarray(blob: bytes, shape) -> "np.ndarray":
    """Deserialize little-endian f64 BYTEA blob into numpy array of given shape.
    反序列化小端 f64 BYTEA blob 為指定 shape 的 numpy 陣列。
    """
    arr = np.frombuffer(blob, dtype="<f8")
    return arr.reshape(shape)


# ---------------------------------------------------------------------------
# Pure-numpy training kernel / 純 numpy 訓練核心
# ---------------------------------------------------------------------------


def train_arm(
    observations: list[tuple[list[float], float]],
    cfg: LinUcbTrainConfig,
):
    """Rebuild (A, b, n_pulls, cumulative_reward) from observation list.
    從觀測列表重建 (A, b, n_pulls, cumulative_reward)。

    Math (math notes Entry 01 §1.3.1) / 數學公式：
        A = lambda * I_d + sum_t x_t x_t^T
        b = sum_t r_t * x_t
    Empty observations -> cold-start prior (A=lambda*I, b=0, n_pulls=0).
    空觀測 -> cold-start 先驗。
    """
    d = cfg.context_dim
    A = cfg.lambda_ridge * np.eye(d, dtype=np.float64)
    b = np.zeros(d, dtype=np.float64)
    n_pulls = 0
    cum_reward = 0.0

    for x_list, r in observations:
        if x_list is None or len(x_list) != d:
            # Skip malformed rows defensively / 防禦性跳過格式異常 row
            continue
        x = np.asarray(x_list, dtype=np.float64)
        A += np.outer(x, x)
        b += float(r) * x
        n_pulls += 1
        cum_reward += float(r)

    return A, b, n_pulls, cum_reward


# ---------------------------------------------------------------------------
# PG IO — psycopg2 fetch + upsert
# PG IO — psycopg2 讀取與 upsert
# ---------------------------------------------------------------------------


def fetch_arm_observations(
    dsn: str,
    arm_id: str,
    since_ts_ms: Optional[int],
    reward_column: str = "outcome_1h",
) -> list[tuple[list[float], float]]:
    """Fetch (context_features, reward) tuples for a single arm.
    為單個 arm 取出 (context_features, reward) 三元組。

    Joins `trading.decision_context_snapshots` to `trading.decision_outcomes`
    on context_id to access realized return. Only rows with non-null reward
    are returned. `indicators_snapshot` is JSONB; the caller is responsible
    for storing it as a flat float list keyed under "features".
    JOIN `trading.decision_context_snapshots` 與 `trading.decision_outcomes`
    取得已實現回報；僅返回 reward 非 null 的 row。`indicators_snapshot` 為
    JSONB，呼叫端需確保以扁平 float 列表存於 "features" 鍵。
    """
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed / psycopg2 未安裝")

    # reward_column comes from trusted config, but still validate to prevent
    # SQL injection. / reward_column 來自信任 config，仍做白名單過濾防注入。
    allowed_cols = {"outcome_1m", "outcome_5m", "outcome_1h", "outcome_4h", "outcome_24h"}
    if reward_column not in allowed_cols:
        raise ValueError(f"reward_column not in allow-list: {reward_column}")

    sql = f"""
        SELECT s.indicators_snapshot, o.{reward_column}
          FROM trading.decision_context_snapshots s
          JOIN trading.decision_outcomes o ON o.context_id = s.context_id
         WHERE s.linucb_arm_id = %s
           AND o.{reward_column} IS NOT NULL
           AND (%s::BIGINT IS NULL OR s.ts >= to_timestamp(%s / 1000.0))
    """
    out: list[tuple[list[float], float]] = []
    with psycopg2.connect(dsn) as conn:  # pragma: no cover — live path
        with conn.cursor() as cur:
            cur.execute(sql, (arm_id, since_ts_ms, since_ts_ms))
            for indicators, reward in cur.fetchall():
                if indicators is None or reward is None:
                    continue
                feats = indicators.get("features") if isinstance(indicators, dict) else None
                if feats is None:
                    continue
                out.append((list(feats), float(reward)))
    return out


def upsert_arm_state(
    dsn: str,
    arm_id: str,
    version: str,
    schema_hash: str,
    A,
    b,
    n_pulls: int,
    cumulative_reward: float,  # noqa: ARG001 — kept for API symmetry / API 對稱保留
) -> None:
    """Upsert sufficient statistics into learning.linucb_state.
    將充分統計量 upsert 進 learning.linucb_state。

    BYTEA payload is little-endian f64 row-major, matching Rust state_io.rs.
    Composite key (arm_id, arm_space_version) per V010.
    BYTEA 為小端 f64 row-major，與 Rust state_io.rs 一致。
    複合鍵 (arm_id, arm_space_version) 來自 V010。
    """
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed / psycopg2 未安裝")

    a_bytes = _ndarray_to_le_bytes(A)
    b_bytes = _ndarray_to_le_bytes(b)
    dim = int(b.shape[0])

    sql = """
        INSERT INTO learning.linucb_state
            (arm_id, arm_space_version, a_matrix, b_vector,
             context_dim, n_pulls, feature_schema_hash, last_updated_ts)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (arm_id, arm_space_version) DO UPDATE SET
            a_matrix = EXCLUDED.a_matrix,
            b_vector = EXCLUDED.b_vector,
            context_dim = EXCLUDED.context_dim,
            n_pulls = EXCLUDED.n_pulls,
            feature_schema_hash = EXCLUDED.feature_schema_hash,
            last_updated_ts = NOW()
    """
    with psycopg2.connect(dsn) as conn:  # pragma: no cover — live path
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    arm_id,
                    version,
                    psycopg2.Binary(a_bytes),
                    psycopg2.Binary(b_bytes),
                    dim,
                    int(n_pulls),
                    schema_hash,
                ),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Top-level driver / 頂層驅動
# ---------------------------------------------------------------------------

# v1_15 = 5 strategies x 3 regimes — names mirror Rust arms_v1_15.rs intent.
# v1_15 = 5 策略 × 3 regime — 名稱對應 Rust arms_v1_15.rs。
_V1_15_STRATEGIES = (
    "ma_crossover",
    "bb_breakout",
    "bb_reversion",
    "grid_trading",
    "funding_arb",
)
_V1_15_REGIMES = ("trending", "mean_reverting", "random_walk")


def enumerate_v1_15_arm_ids() -> list[str]:
    """Return the 15 canonical arm ids of arm_space_version=v1_15.
    返回 arm_space_version=v1_15 的 15 個標準 arm id。
    """
    return [f"{regime}__{strat}" for regime in _V1_15_REGIMES for strat in _V1_15_STRATEGIES]


def train_all_arms(dsn: str, cfg: LinUcbTrainConfig) -> list[TrainResult]:
    """Train every arm in the configured arm space and persist to PG.
    遍歷配置的 arm space 內每個 arm，訓練後寫回 PG。
    """
    schema_hash = compute_feature_schema_hash(cfg.feature_names)
    results: list[TrainResult] = []
    arm_ids = enumerate_v1_15_arm_ids() if cfg.arm_space_version == "v1_15" else []

    for arm_id in arm_ids:
        try:
            obs = fetch_arm_observations(dsn, arm_id, since_ts_ms=None, reward_column=cfg.reward_column)
        except Exception as exc:  # pragma: no cover — DB error path
            logger.error("fetch_arm_observations failed arm=%s err=%s", arm_id, exc)
            continue

        A, b, n_pulls, cum_r = train_arm(obs, cfg)
        converged = n_pulls >= cfg.min_samples_per_arm

        try:
            upsert_arm_state(dsn, arm_id, cfg.arm_space_version, schema_hash, A, b, n_pulls, cum_r)
        except Exception as exc:  # pragma: no cover — DB error path
            logger.error("upsert_arm_state failed arm=%s err=%s", arm_id, exc)
            continue

        results.append(
            TrainResult(
                arm_id=arm_id,
                n_pulls_before=0,  # batch rebuild always replaces / 批次重建總是替換
                n_pulls_after=n_pulls,
                cumulative_reward=cum_r,
                converged=converged,
            )
        )
    return results
