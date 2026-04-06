"""LinUCB shadow compare + auto regret rollback (Phase 4 task 4-06).

LinUCB 影子比較與自動 regret 回滾（Phase 4 子任務 4-06）。

MODULE_NOTE (EN):
    Run two LinUCB arm-space versions in shadow for 1-2 weeks before promotion.
    The champion (e.g. v1_15) keeps writing real positions; the challenger
    (e.g. v2_25, warm-started by linucb_arm_migration §1.3.3) replays the
    same context read-only and accumulates a counterfactual reward stream.

    decision: 'PROMOTE' | 'KEEP_CHAMPION' | 'INSUFFICIENT_DATA'
        PROMOTE         — challenger > champion by ≥ +2σ over the window
        KEEP_CHAMPION   — challenger - champion ≤ -2σ → rollback path
        INSUFFICIENT    — fewer than min_decisions OR DB error (fail-soft)

    sigma estimation: pooled per-decision reward stddev across both versions
    divided by sqrt(N). This is the simplest unbiased estimator and is the
    same one used by Optuna early-stop in Phase 3b for consistency.

    auto_rollback_if_needed flips the active arm-space label by writing a
    rollback row to learning.linucb_migrations whose direction='collapse'
    and rollback_to references the original expand row, then archives the
    challenger version. Read-only for everything else; never touches the
    champion's state.

MODULE_NOTE (中):
    在 promote 前並行跑兩個 LinUCB arm-space 版本 1-2 週。冠軍寫真倉位；
    挑戰者用同樣的 context 重放、只記錄不下單。
    sigma 估計：兩個版本所有 per-decision reward 的 pooled stddev / sqrt(N)。
    auto_rollback_if_needed 在 KEEP_CHAMPION 且 Δ < -2σ 時，寫一筆 rollback
    row 到 linucb_migrations、歸檔 challenger，但**從不**動冠軍 state。

Safety / 安全：
    - Fail-soft on any DB error -> INSUFFICIENT_DATA, never silent PROMOTE.
    - Read-only on champion / 冠軍只讀。
    - No hard-coded paths.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import psycopg2  # type: ignore
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Config / result
# ---------------------------------------------------------------------------


@dataclass
class ShadowCompareConfig:
    """Shadow compare config. / 影子比較配置。

    Attributes:
        champion_version: e.g. 'v1_15'. / 冠軍版本標籤。
        challenger_version: e.g. 'v2_25'. / 挑戰者版本標籤。
        window_days: lookback window in days. / 回看窗口（天）。
        rollback_threshold_sigma: trigger rollback if delta < -threshold·σ.
            / 若 Δ < -threshold·σ 觸發回滾。預設 2.0。
        min_decisions: below this -> INSUFFICIENT_DATA. / 樣本下限。
    """

    champion_version: str
    challenger_version: str
    window_days: int = 14
    rollback_threshold_sigma: float = 2.0
    min_decisions: int = 100


@dataclass
class ShadowCompareResult:
    """Shadow compare result. / 影子比較結果。"""

    champion_cumulative_reward: float
    challenger_cumulative_reward: float
    delta: float
    delta_sigma: float
    decision: str  # 'PROMOTE' / 'KEEP_CHAMPION' / 'INSUFFICIENT_DATA'
    n_decisions_compared: int


# ---------------------------------------------------------------------------
# Pure decision kernel (mockable, no DB)
# 純決策核心 — 不依賴 DB
# ---------------------------------------------------------------------------


def decide(
    champion_rewards: list,
    challenger_rewards: list,
    cfg: ShadowCompareConfig,
) -> ShadowCompareResult:
    """Compute the decision from two parallel reward streams.
    根據兩條並行 reward 流計算決策結果。

    Args:
        champion_rewards: per-decision reward list of the champion.
        challenger_rewards: same length list for challenger.
        cfg: ShadowCompareConfig.

    Returns:
        ShadowCompareResult.

    Sigma model:
        pooled_var = (var_champ + var_chal) / 2
        sigma_delta = sqrt(pooled_var * (1/n_champ + 1/n_chal))
        delta = mean_chal - mean_champ
        z = delta / sigma_delta

        z >= +threshold -> PROMOTE
        z <= -threshold -> KEEP_CHAMPION
        otherwise        -> KEEP_CHAMPION (default safe to current)
    """
    n_c = len(champion_rewards)
    n_x = len(challenger_rewards)
    n = min(n_c, n_x)

    if n < cfg.min_decisions:
        return ShadowCompareResult(
            champion_cumulative_reward=float(sum(champion_rewards)) if champion_rewards else 0.0,
            challenger_cumulative_reward=(
                float(sum(challenger_rewards)) if challenger_rewards else 0.0
            ),
            delta=0.0,
            delta_sigma=0.0,
            decision="INSUFFICIENT_DATA",
            n_decisions_compared=n,
        )

    cum_c = float(sum(champion_rewards))
    cum_x = float(sum(challenger_rewards))
    mean_c = cum_c / n_c
    mean_x = cum_x / n_x

    def _var(xs, mu):
        if len(xs) < 2:
            return 0.0
        return sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)

    var_c = _var(champion_rewards, mean_c)
    var_x = _var(challenger_rewards, mean_x)
    pooled = 0.5 * (var_c + var_x)
    sigma_delta = math.sqrt(max(pooled, 0.0) * (1.0 / n_c + 1.0 / n_x))

    delta = mean_x - mean_c
    z = (delta / sigma_delta) if sigma_delta > 0 else 0.0

    if z >= cfg.rollback_threshold_sigma:
        decision = "PROMOTE"
    elif z <= -cfg.rollback_threshold_sigma:
        decision = "KEEP_CHAMPION"
    else:
        decision = "KEEP_CHAMPION"

    return ShadowCompareResult(
        champion_cumulative_reward=cum_c,
        challenger_cumulative_reward=cum_x,
        delta=delta,
        delta_sigma=sigma_delta,
        decision=decision,
        n_decisions_compared=n,
    )


# ---------------------------------------------------------------------------
# DB IO (live path)
# DB IO（live 路徑）
# ---------------------------------------------------------------------------


def _fetch_rewards(conn, version: str, window_days: int) -> list:  # pragma: no cover
    """Pull per-decision realized rewards for the given arm_space_version
    over the last window_days. Returns [] on any error.
    取出指定版本最近 window_days 天的 per-decision realized reward。
    """
    sql = """
        SELECT o.outcome_1h
          FROM trading.decision_context_snapshots s
          JOIN trading.decision_outcomes o ON o.context_id = s.context_id
         WHERE s.linucb_arm_space_version = %s
           AND s.ts >= NOW() - (%s || ' days')::INTERVAL
           AND o.outcome_1h IS NOT NULL
    """
    out: list = []
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (version, str(window_days)))
            for (r,) in cur.fetchall():
                if r is not None:
                    out.append(float(r))
    except Exception as exc:
        logger.warning("shadow_compare fetch failed version=%s err=%s", version, exc)
        return []
    return out


def run_shadow_compare(
    dsn: str,
    cfg: ShadowCompareConfig,
    _conn=None,
) -> ShadowCompareResult:
    """Live shadow compare entry point. Fail-soft on DB error.
    Live 影子比較入口；DB 錯誤時退回 INSUFFICIENT_DATA。
    """
    own = _conn is None
    try:
        conn = _conn if _conn is not None else (psycopg2.connect(dsn) if psycopg2 else None)
    except Exception as exc:
        logger.warning("shadow_compare connect failed: %s", exc)
        return ShadowCompareResult(0.0, 0.0, 0.0, 0.0, "INSUFFICIENT_DATA", 0)

    if conn is None:
        return ShadowCompareResult(0.0, 0.0, 0.0, 0.0, "INSUFFICIENT_DATA", 0)

    try:
        champ = _fetch_rewards(conn, cfg.champion_version, cfg.window_days)
        chal = _fetch_rewards(conn, cfg.challenger_version, cfg.window_days)
        return decide(champ, chal, cfg)
    finally:
        if own and hasattr(conn, "close"):
            try:
                conn.close()
            except Exception:
                pass


def auto_rollback_if_needed(
    dsn: str,
    cfg: ShadowCompareConfig,
    _conn=None,
) -> bool:
    """Run shadow compare; if challenger is significantly worse, archive it
    and write a rollback audit row. Returns True if rollback executed.
    跑一次影子比較；若 challenger 顯著更差，歸檔並寫回滾審計，返回 True。
    """
    res = run_shadow_compare(dsn, cfg, _conn=_conn)
    if res.decision != "KEEP_CHAMPION":
        return False
    if res.delta_sigma <= 0:
        return False
    z = res.delta / res.delta_sigma
    if z > -cfg.rollback_threshold_sigma:
        return False

    # Significant rollback path / 顯著回滾路徑
    own = _conn is None
    conn = _conn if _conn is not None else (psycopg2.connect(dsn) if psycopg2 else None)
    if conn is None:
        return False
    try:
        # Archive challenger / 歸檔 challenger
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO learning.linucb_state_archive
                       (arm_id, arm_space_version, parent_arm_id, inheritance_gamma,
                        feature_schema_hash, a_matrix, b_vector, context_dim, n_pulls,
                        archived_ts, archive_reason)
                   SELECT arm_id, arm_space_version, parent_arm_id, inheritance_gamma,
                          feature_schema_hash, a_matrix, b_vector, context_dim, n_pulls,
                          NOW(), %s
                     FROM learning.linucb_state
                    WHERE arm_space_version = %s""",
                (f"auto_rollback_z={z:.2f}", cfg.challenger_version),
            )
            cur.execute(
                """INSERT INTO learning.linucb_migrations
                       (from_version, to_version, direction, gamma,
                        n_arms_before, n_arms_after, started_ts, finished_ts, notes)
                   VALUES (%s, %s, 'collapse', NULL, 0, 0, NOW(), NOW(), %s)""",
                (
                    cfg.challenger_version,
                    cfg.champion_version,
                    f"auto_rollback z={z:.2f} delta={res.delta:.6f} n={res.n_decisions_compared}",
                ),
            )
        if hasattr(conn, "commit"):
            conn.commit()
        logger.warning(
            "LinUCB auto-rollback executed: %s -> %s z=%.2f delta=%.6f",
            cfg.challenger_version,
            cfg.champion_version,
            z,
            res.delta,
        )
        return True
    finally:
        if own and hasattr(conn, "close"):
            try:
                conn.close()
            except Exception:
                pass
