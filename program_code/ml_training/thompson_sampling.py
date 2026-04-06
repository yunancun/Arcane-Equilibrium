"""
Thompson Sampling with Normal-Inverse-Gamma (NIG) posterior for cross-strategy allocation.
Normal-Inverse-Gamma 後驗的 Thompson Sampling，用於跨策略資源分配。

MODULE_NOTE (EN): Layer 2 of the 2-layer optimization system. Decides which
  (strategy, symbol, regime) triplet to optimize next. Uses NIG conjugate prior
  for continuous outcomes. Empirical Bayes initialization from paper returns.
  Python-only for Phase 3b (Rust inference deferred to Phase 4 — E5-D3).
MODULE_NOTE (中): 兩層優化系統的第 2 層。決定下一個優化的 (策略, 幣種, regime) 三元組。
  使用 NIG 共軛先驗處理連續結果。Empirical Bayes 從紙盤回報初始化。
  Phase 3b 僅 Python（Rust 推理延後至 Phase 4 — E5-D3）。
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import asdict, dataclass, field
from typing import Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover — numpy missing 時回退
    np = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Numerical safety bounds / 數值安全邊界
# ---------------------------------------------------------------------------
_MIN_LAMBDA = 1e-6   # lambda must stay positive / lambda 必須保持正值
_MIN_ALPHA = 1.001    # alpha > 1 ensures mean exists / alpha > 1 確保均值存在
_MIN_BETA = 1e-9      # beta must stay positive / beta 必須保持正值


@dataclass
class NIGPosterior:
    """Normal-Inverse-Gamma posterior parameters.
    Normal-Inverse-Gamma 後驗參數。

    Attributes:
        mu:   mean estimate / 均值估計
        lam:  precision of mean (lambda, "prior strength") / 均值精度（先驗強度）
        alpha: shape parameter (>2 for variance to exist) / 形狀參數（>2 方差才存在）
        beta:  scale parameter / 尺度參數
        n_trials: number of observations incorporated / 已納入觀測數
    """

    mu: float = 0.0
    lam: float = 3.0
    alpha: float = 3.0
    beta: float = 1.0
    n_trials: int = 0


# ---------------------------------------------------------------------------
# Empirical Bayes initialization / Empirical Bayes 初始化
# ---------------------------------------------------------------------------

def empirical_bayes_init(returns: list[float]) -> NIGPosterior:
    """Initialize NIG prior from paper-trading returns via Empirical Bayes.
    從紙盤回報透過 Empirical Bayes 初始化 NIG 先驗。

    Args:
        returns: list of observed returns (PnL values)
                 觀測回報列表（PnL 值）

    Returns:
        NIGPosterior with Empirical Bayes parameters
        帶 Empirical Bayes 參數的 NIGPosterior
    """
    # Empty or all-zero returns → safe default prior
    # 空或全零回報 → 安全默認先驗
    if not returns or all(r == 0.0 for r in returns):
        logger.debug("empirical_bayes_init: empty/zero returns, using default prior")
        return NIGPosterior(mu=0.0, lam=3.0, alpha=3.0, beta=1.0, n_trials=0)

    n = len(returns)
    mu_0 = sum(returns) / n

    # Variance: use population variance (biased) for Empirical Bayes
    # 方差：使用 population variance（有偏）
    mean_sq = sum((r - mu_0) ** 2 for r in returns) / n

    lam_0 = 3.0    # 3 trades sufficient to diverge from prior / 3 筆交易足以偏離先驗
    alpha_0 = 3.0  # ensures both variance and mean exist / 確保方差和均值都存在

    # beta_0 = var(returns) * (alpha_0 - 1)
    beta_0 = mean_sq * (alpha_0 - 1.0)  # = var * 2

    # Guard: if zero variance (all identical returns), use small positive beta
    # 護衛：若零方差（所有回報相同），使用小正值 beta
    if beta_0 <= 0.0:
        beta_0 = 0.001

    return NIGPosterior(mu=mu_0, lam=lam_0, alpha=alpha_0, beta=beta_0, n_trials=0)


# ---------------------------------------------------------------------------
# Posterior update (single + batch) / 後驗更新（單筆 + 批次）
# ---------------------------------------------------------------------------

def update_posterior(prior: NIGPosterior, observation: float) -> NIGPosterior:
    """Conjugate update for a single observation.
    單筆觀測的共軛更新。

    NIG conjugate update formulas:
      lam_n   = lam + 1
      mu_n    = (lam * mu + x) / lam_n
      alpha_n = alpha + 0.5
      beta_n  = beta + 0.5 * lam * (x - mu)^2 / lam_n

    Args:
        prior: current NIG posterior / 當前 NIG 後驗
        observation: single observed value (e.g. PnL) / 單筆觀測值（如 PnL）

    Returns:
        new NIGPosterior with updated parameters / 更新後的 NIGPosterior
    """
    x = observation
    lam_n = prior.lam + 1.0
    mu_n = (prior.lam * prior.mu + x) / lam_n
    alpha_n = prior.alpha + 0.5
    beta_n = prior.beta + 0.5 * prior.lam * ((x - prior.mu) ** 2) / lam_n

    # Numerical safety clamps / 數值安全鉗制
    lam_n = max(lam_n, _MIN_LAMBDA)
    alpha_n = max(alpha_n, _MIN_ALPHA)
    beta_n = max(beta_n, _MIN_BETA)

    return NIGPosterior(
        mu=mu_n,
        lam=lam_n,
        alpha=alpha_n,
        beta=beta_n,
        n_trials=prior.n_trials + 1,
    )


def update_posterior_batch(
    prior: NIGPosterior, observations: list[float]
) -> NIGPosterior:
    """Apply conjugate updates for multiple observations sequentially.
    對多筆觀測依序套用共軛更新。

    Args:
        prior: current NIG posterior / 當前 NIG 後驗
        observations: list of observed values / 觀測值列表

    Returns:
        new NIGPosterior after all updates / 所有更新後的 NIGPosterior
    """
    posterior = prior
    for obs in observations:
        posterior = update_posterior(posterior, obs)
    return posterior


# ---------------------------------------------------------------------------
# Sampling / 抽樣
# ---------------------------------------------------------------------------

def sample_nig(
    posterior: NIGPosterior,
    rng: Optional[random.Random] = None,
) -> float:
    """Sample expected reward from NIG posterior.
    從 NIG 後驗抽樣期望報酬。

    Procedure / 步驟:
      1. Sample sigma^2 ~ InverseGamma(alpha, beta) = 1 / Gamma(alpha, 1/beta)
      2. Sample mu ~ Normal(posterior.mu, sigma^2 / lambda)
      Return sampled mu (the "expected reward" for this arm)
      返回抽樣的 mu（該臂的「期望報酬」）

    Args:
        posterior: NIG posterior parameters / NIG 後驗參數
        rng: optional seeded random.Random (used for seed derivation only)
             可選的帶種子 random.Random（僅用於種子派生）

    Returns:
        sampled expected reward (float) / 抽樣期望報酬
    """
    if np is None:  # pragma: no cover
        raise ImportError(
            "numpy is required for sample_nig / sample_nig 需要 numpy"
        )

    # Derive a numpy RNG from the optional stdlib rng
    # 從可選的 stdlib rng 派生 numpy RNG
    if rng is not None:
        seed = rng.randint(0, 2**31 - 1)
        np_rng = np.random.default_rng(seed)
    else:
        np_rng = np.random.default_rng()

    alpha = max(posterior.alpha, _MIN_ALPHA)
    beta = max(posterior.beta, _MIN_BETA)
    lam = max(posterior.lam, _MIN_LAMBDA)

    # Step 1: sigma^2 ~ InverseGamma(alpha, beta)
    # InverseGamma(a, b) = 1 / Gamma(a, scale=1/b)
    # numpy Gamma: shape=alpha, scale=1/beta → then invert
    # 步驟 1: sigma^2 ~ InverseGamma(alpha, beta)
    gamma_sample = np_rng.gamma(shape=alpha, scale=1.0 / beta)
    # Guard against zero / 防止除零
    gamma_sample = max(gamma_sample, 1e-30)
    sigma_sq = 1.0 / gamma_sample

    # Step 2: mu ~ Normal(posterior.mu, sigma^2 / lambda)
    # 步驟 2: mu ~ Normal(posterior.mu, sigma^2 / lambda)
    std = math.sqrt(sigma_sq / lam)
    sampled_mu = float(np_rng.normal(loc=posterior.mu, scale=std))

    return sampled_mu


# ---------------------------------------------------------------------------
# Arm selection / 臂選擇
# ---------------------------------------------------------------------------

def sample_arm(
    posteriors: dict[str, NIGPosterior],
    rng: Optional[random.Random] = None,
) -> str:
    """Thompson Sampling arm selection: sample each arm, pick the best.
    Thompson Sampling 臂選擇：對每臂抽樣，選最佳。

    Args:
        posteriors: mapping of arm_key → NIGPosterior / 臂鍵 → NIGPosterior 映射
        rng: optional seeded RNG / 可選帶種子 RNG

    Returns:
        arm key with highest sampled value / 抽樣值最高的臂鍵
    """
    if not posteriors:
        raise ValueError("posteriors dict is empty / posteriors 字典為空")

    best_key: Optional[str] = None
    best_val = -math.inf

    for key, post in posteriors.items():
        val = sample_nig(post, rng=rng)
        if val > best_val:
            best_val = val
            best_key = key

    assert best_key is not None  # guaranteed by non-empty dict
    return best_key


def exploitation_floor(
    posteriors: dict[str, NIGPosterior],
    floor_trials: int = 10,
    floor_pct: float = 0.5,
) -> bool:
    """Check whether exploitation should be forced due to scarce data.
    檢查是否因數據稀缺而強制利用模式。

    If total trials across all arms < floor_trials, return True.
    When True, caller should pick the arm with best empirical mean (mu)
    instead of sampling — this prevents pure exploration early on.
    若所有臂的總試驗次數 < floor_trials，回傳 True。
    為 True 時，呼叫者應選 mu 最高的臂而非抽樣 — 防止早期純探索。

    Args:
        posteriors: mapping of arm_key → NIGPosterior / 臂鍵 → NIGPosterior 映射
        floor_trials: minimum total trials before normal sampling / 正常抽樣前的最低總試驗數
        floor_pct: exploitation probability (reserved for future use) /
                   利用概率（保留供未來使用）

    Returns:
        True if exploitation should be forced / 若應強制利用則為 True
    """
    total = sum(p.n_trials for p in posteriors.values())
    return total < floor_trials


def select_next_arm(
    posteriors: dict[str, NIGPosterior],
    rng: Optional[random.Random] = None,
) -> str:
    """Main entry point: exploitation floor + Thompson Sampling arm selection.
    主入口：利用下限 + Thompson Sampling 臂選擇。

    If exploitation_floor is True: return arm with highest mu (best empirical mean).
    Else: return sample_arm result (Thompson Sampling).
    若 exploitation_floor 為 True：回傳 mu 最高的臂（最佳經驗均值）。
    否則：回傳 sample_arm 結果（Thompson Sampling）。

    Args:
        posteriors: mapping of arm_key → NIGPosterior / 臂鍵 → NIGPosterior 映射
        rng: optional seeded RNG / 可選帶種子 RNG

    Returns:
        selected arm key / 選定的臂鍵
    """
    if not posteriors:
        raise ValueError("posteriors dict is empty / posteriors 字典為空")

    if exploitation_floor(posteriors):
        # Pick arm with highest empirical mean / 選經驗均值最高的臂
        best_key = max(posteriors, key=lambda k: posteriors[k].mu)
        logger.debug(
            "select_next_arm: exploitation floor active, picked %s (mu=%.4f)",
            best_key,
            posteriors[best_key].mu,
        )
        return best_key

    return sample_arm(posteriors, rng=rng)


# ---------------------------------------------------------------------------
# Serialization / 序列化
# ---------------------------------------------------------------------------

def posteriors_to_dict(posteriors: dict[str, NIGPosterior]) -> dict:
    """Serialize posteriors for JSON/DB storage.
    將後驗序列化為 JSON/DB 存儲格式。

    Args:
        posteriors: mapping of arm_key → NIGPosterior / 臂鍵 → NIGPosterior 映射

    Returns:
        dict suitable for json.dumps or JSONB column / 適用於 json.dumps 或 JSONB 列的字典
    """
    return {key: asdict(post) for key, post in posteriors.items()}


def posteriors_from_dict(data: dict) -> dict[str, NIGPosterior]:
    """Deserialize posteriors from JSON/DB storage.
    從 JSON/DB 存儲反序列化後驗。

    Args:
        data: dict from json.loads or DB JSONB column /
              來自 json.loads 或 DB JSONB 列的字典

    Returns:
        mapping of arm_key → NIGPosterior / 臂鍵 → NIGPosterior 映射
    """
    result: dict[str, NIGPosterior] = {}
    for key, vals in data.items():
        result[key] = NIGPosterior(
            mu=float(vals["mu"]),
            lam=float(vals["lam"]),
            alpha=float(vals["alpha"]),
            beta=float(vals["beta"]),
            n_trials=int(vals.get("n_trials", 0)),
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# P1-5: PostgreSQL persistence for learning.bayesian_posteriors table
# P1-5：learning.bayesian_posteriors 表的 PostgreSQL 持久化
# ═══════════════════════════════════════════════════════════════════════════════

_ARM_KEY_SEP = "|"


def _parse_arm_key(arm_key: str) -> tuple[str, str, str]:
    """Parse arm_key 'strategy|symbol|regime' into tuple. / 解析臂鍵。"""
    parts = arm_key.split(_ARM_KEY_SEP)
    if len(parts) != 3:
        raise ValueError(
            f"arm_key must be 'strategy|symbol|regime', got: {arm_key}"
        )
    return parts[0], parts[1], parts[2]


def _make_arm_key(strategy: str, symbol: str, regime: str) -> str:
    """Build arm_key from components. / 構建臂鍵。"""
    return f"{strategy}{_ARM_KEY_SEP}{symbol}{_ARM_KEY_SEP}{regime}"


def save_posteriors_to_pg(
    posteriors: dict[str, NIGPosterior],
    dsn: str,
) -> int:
    """UPSERT posteriors to learning.bayesian_posteriors.
    將後驗 UPSERT 到 learning.bayesian_posteriors 表。

    Args:
        posteriors: mapping of 'strategy|symbol|regime' → NIGPosterior
        dsn: PostgreSQL DSN (e.g., 'postgresql://redacted@host:5432/db')

    Returns:
        Number of rows written / 寫入的行數。
    """
    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 not installed — install via: pip install psycopg2-binary")
        return 0

    if not posteriors:
        return 0

    rows = []
    for arm_key, post in posteriors.items():
        try:
            strategy, symbol, regime = _parse_arm_key(arm_key)
        except ValueError as e:
            logger.warning("skipping invalid arm_key: %s", e)
            continue
        rows.append((
            strategy, symbol, regime,
            post.mu, post.lam, post.alpha, post.beta, post.n_trials,
        ))

    if not rows:
        return 0

    sql = """
        INSERT INTO learning.bayesian_posteriors
            (strategy_name, symbol, regime, mu, lambda, alpha, beta, n_trials,
             last_updated_ts)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (strategy_name, symbol, regime) DO UPDATE
            SET mu = EXCLUDED.mu,
                lambda = EXCLUDED.lambda,
                alpha = EXCLUDED.alpha,
                beta = EXCLUDED.beta,
                n_trials = EXCLUDED.n_trials,
                last_updated_ts = now()
    """

    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.executemany(sql, rows)
        logger.info("save_posteriors_to_pg: upserted %d rows", len(rows))
        return len(rows)
    finally:
        conn.close()


def load_posteriors_from_pg(
    dsn: str,
    strategy: Optional[str] = None,
) -> dict[str, NIGPosterior]:
    """Load posteriors from learning.bayesian_posteriors.
    從 learning.bayesian_posteriors 載入後驗。

    Args:
        dsn: PostgreSQL DSN
        strategy: optional strategy filter / 可選策略過濾

    Returns:
        mapping of 'strategy|symbol|regime' → NIGPosterior
    """
    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 not installed")
        return {}

    base_sql = """
        SELECT strategy_name, symbol, regime, mu, lambda, alpha, beta, n_trials
        FROM learning.bayesian_posteriors
    """
    params: tuple = ()
    if strategy:
        base_sql += " WHERE strategy_name = %s"
        params = (strategy,)

    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(base_sql, params)
            result: dict[str, NIGPosterior] = {}
            for row in cur.fetchall():
                strat, sym, reg, mu, lam, alpha, beta, n_trials = row
                key = _make_arm_key(strat, sym, reg)
                result[key] = NIGPosterior(
                    mu=float(mu), lam=float(lam),
                    alpha=float(alpha), beta=float(beta),
                    n_trials=int(n_trials),
                )
            logger.info("load_posteriors_from_pg: loaded %d posteriors", len(result))
            return result
    finally:
        conn.close()
