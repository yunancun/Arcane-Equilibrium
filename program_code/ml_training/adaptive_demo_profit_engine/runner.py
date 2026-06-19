"""
MODULE_NOTE (中):
  用途：Adaptive Demo Profit Engine（ADPE）閉環 runner + kill switch + CLI/cron entry。
  一個 cycle = 讀 demo realized reward → ingest 進 allocator → 對每個 candidate regime
  allocate → 把贏家映成 active / 負 EV 映成 dormant → 經 ipc_lever 落到 demo 引擎。
  默認 dry-run（只產 plan + log，不發 IPC）。

  主要類 / 函數：
    - AdpeRunnerConfig：runner 級配置（demo 硬鎖 / dry-run / 候選策略 / window）。
    - CycleReport / CandidateDecision：一個 cycle 的審計輸出。
    - AdpeRunner：build_desired_active / run_cycle / kill_switch_snapshot /
      kill_switch（一鍵停 + 還原 active 態）。
    - ingest_demo_maker_outcome：把一筆 demo-maker round-trip 已實現價差餵進 allocator
      （走 all_fills 軌標 saw_artifact、transferable_only 軌不吸收）。
    - main()：argparse CLI（cron/手動），--apply 才真發 IPC，--kill-switch 一鍵停，
      --explore-sink 開 Track1 demo explore-gate overlay 注入。

  Track1 demo explore-gate（opt-in，enable_explore_sink）：
    每 cycle ingest+allocate 後，呼 explore_quota_sink.build_explore_overlay 由 allocator
    真實 explore_budget_remaining 推導每 cell 的 explore_eligible/explore_remaining，
    再 additive 注入 edge_estimates.json（不覆蓋 JS writer 欄位）。dry-run 不寫檔。
    explore 欄位只被 Rust demo cost_gate 讀，live gate 不讀（demo↔live 隔離）。

  依賴：reward_source / ipc_lever / demo_maker_arm / explore_quota_sink（同 package）+
    regime_bandit_allocator（核心 allocator，已測綠）+ adaptive_demo_profit config loader。

  硬邊界 / 誠實鐵則（為什麼這樣設計）：
    1. **engine_mode 硬鎖 demo**。run_cycle 啟動先驗 cfg.engine_mode=='demo'；
       非 demo 直接 raise（fail-closed，不部分 apply）。真錢 / mainnet / live 路徑不碰。
    2. **reward 全 realized，不合成**。view reward 經 reward_source（post-fee、
       attribution-gated）；demo-maker reward 經 build_demo_maker_reward（artifact tier）。
       runner 不發明任何正報酬。
    3. **kill switch 必備**。kill_switch_snapshot 在啟用 apply 前拍下 active 態；
       kill_switch() 一鍵把 active 態還原成 snapshot（+ 呼叫端停 cron/runner 進程）。
    4. **dry-run 默認**。run_cycle(dry_run=True) 不發 IPC；--apply 才真落地。
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import tomllib  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

from program_code.ml_training.regime_bandit_allocator import (
    FLAT_ARM_ID,
    TRACK_ALL_FILLS,
    VALID_REGIMES,
    AllocatorConfig,
    ArmReward,
    RegimeBanditAllocator,
    make_arm_id,
    parse_arm_id,
)
from program_code.ml_training.adaptive_demo_profit_engine.demo_maker_arm import (
    DEMO_MAKER_ARM,
    build_demo_maker_reward,
)
from program_code.ml_training.adaptive_demo_profit_engine.ipc_lever import (
    ApplyResult,
    StrategyLever,
)
from program_code.ml_training.adaptive_demo_profit_engine.reward_source import (
    fetch_demo_arm_rewards,
)
from program_code.ml_training.adaptive_demo_profit_engine.explore_quota_sink import (
    build_explore_overlay,
    merge_into_edge_estimates,
)

logger = logging.getLogger(__name__)

# engine_mode 硬鎖唯一允許值（demo 沙盒）。
_DEMO_ENGINE_MODE = "demo"

# config 預設路徑：srv/settings/adaptive_demo_profit.toml。
# 從本檔（program_code/ml_training/adaptive_demo_profit_engine/runner.py）回推三層到 srv。
_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "settings", "adaptive_demo_profit.toml"
)

# Track1 demo explore-gate：edge_estimates.json（demo 路徑）預設路徑。
# explore 欄位只被 demo gate 讀，live gate 不讀（demo↔live 隔離）。
_DEFAULT_EDGE_ESTIMATES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "settings", "edge_estimates.json"
)


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


@dataclass
class AdpeRunnerConfig:
    """runner 級配置（與 settings/adaptive_demo_profit.toml 對齊）。"""

    # engine_mode 硬鎖：只允許 'demo'。非 demo → run_cycle 拒絕（fail-closed）。
    engine_mode: str = _DEMO_ENGINE_MODE
    # 默認 dry-run：True 不發 IPC，只產 plan + log。真發需 CLI --apply。
    dry_run_default: bool = True
    # 讀 reward 的近窗天數。
    reward_max_age_days: int = 30
    # 候選策略集（要被配置的 strategy-arm 來源）。空 = 從 reward 觀測自動發現。
    candidate_strategies: list[str] = field(default_factory=list)
    # 候選 regime 集（要逐一 allocate 的 regime context）。空 = VALID_REGIMES 全集。
    candidate_regimes: list[str] = field(default_factory=list)
    # 是否把 demo-maker candidate arm 納入候選（all_fills 軌）。
    include_demo_maker_arm: bool = True
    # 隨機種子（None=非確定；CLI / 測試可注入固定值保可重現）。
    rng_seed: Optional[int] = None
    # Track1 demo explore-gate：是否在每 cycle 算 explore overlay 並 additive 注入
    # edge_estimates.json。預設 False（不影響既有 cycle 行為，opt-in）。
    enable_explore_sink: bool = False
    # explore overlay 用的「當前 regime」（design §3.3 regime 維在 Python 端 collapse）。
    # 預設 insufficient_context（fail-closed：是 VALID_REGIMES 之一，allocator 對該 arm
    # 自有 n_trials 狀態，不亂塞具體 regime 造 selection bias）。CLI / config 可覆寫。
    explore_current_regime: str = "insufficient_context"
    # Controlled experiment mode：只約束「explore 保活」；validated winner 仍可直接 active。
    # 目的不是止血，而是把 demo 從全策略常開改成可審計實驗政策。
    controlled_experiment_enabled: bool = False
    # 退役 / 禁止探索策略。命中者不能因 winner 或 explore 保活被打開。
    retired_strategy_blocklist: list[str] = field(default_factory=list)
    # 非空時，explore 保活僅限 allowlist；winner 不受此 allowlist 限制。
    explore_strategy_allowlist: list[str] = field(default_factory=list)
    # 0 = 不限；>0 時，explore-only active 只取 advisory/remaining 排名前 N。
    max_active_explore_strategies: int = 0
    # 若 true，explore 保活必須有 L2 / multi-agent advisory 正向 evidence。
    require_advisory_for_explore: bool = False
    advisory_sources: list[str] = field(default_factory=lambda: ["ml_shadow", "dream_engine"])
    advisory_max_age_hours: int = 48
    advisory_min_confidence: float = 0.5
    advisory_min_expected_net_bps: float = 0.0
    advisory_min_sample_count: int = 10
    advisory_allow_requires_governance: bool = False
    # Cost-gate aligned side-aware edge evidence. Default off keeps unit tests
    # hermetic; repo config enables it for the runtime cron.
    use_edge_snapshot_for_explore_evidence: bool = False
    require_cost_viable_edge_for_explore_when_available: bool = True
    edge_evidence_fee_rate: float = 0.00055
    edge_evidence_slippage: float = 0.0
    edge_evidence_win_rate_floor: float = 0.3
    edge_evidence_safety_multiplier: float = 1.3
    edge_evidence_grid_min_n: int = 30
    edge_evidence_require_runtime_symbol_ready: bool = False
    edge_evidence_runtime_snapshot_path: str = "/tmp/openclaw/pipeline_snapshot.json"


def load_runner_config(
    path: Optional[str] = None,
) -> tuple[AdpeRunnerConfig, AllocatorConfig]:
    """從 TOML 載入 runner + allocator 配置。

    TOML 缺檔 / 缺欄位 → 用 dataclass 預設（fail-soft，不 raise）。
    回 (AdpeRunnerConfig, AllocatorConfig)。
    """
    cfg_path = path or _DEFAULT_CONFIG_PATH
    data: dict = {}
    try:
        with open(cfg_path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        logger.info("adaptive_demo_profit.toml 不存在，用內建預設: %s", cfg_path)
    except (tomllib.TOMLDecodeError, OSError) as e:
        logger.warning("adaptive_demo_profit.toml 解析失敗，用內建預設: %s", e)

    runner_d = data.get("runner", {}) if isinstance(data, dict) else {}
    alloc_d = data.get("allocator", {}) if isinstance(data, dict) else {}

    runner_cfg = AdpeRunnerConfig(
        engine_mode=str(runner_d.get("engine_mode", _DEMO_ENGINE_MODE)),
        dry_run_default=bool(runner_d.get("dry_run_default", True)),
        reward_max_age_days=int(runner_d.get("reward_max_age_days", 30)),
        candidate_strategies=list(runner_d.get("candidate_strategies", []) or []),
        candidate_regimes=list(runner_d.get("candidate_regimes", []) or []),
        include_demo_maker_arm=bool(runner_d.get("include_demo_maker_arm", True)),
        rng_seed=runner_d.get("rng_seed"),
        enable_explore_sink=bool(runner_d.get("enable_explore_sink", False)),
        explore_current_regime=str(
            runner_d.get("explore_current_regime", "insufficient_context")
        ),
        controlled_experiment_enabled=bool(
            runner_d.get("controlled_experiment_enabled", False)
        ),
        retired_strategy_blocklist=list(
            runner_d.get("retired_strategy_blocklist", []) or []
        ),
        explore_strategy_allowlist=list(
            runner_d.get("explore_strategy_allowlist", []) or []
        ),
        max_active_explore_strategies=int(
            runner_d.get("max_active_explore_strategies", 0)
        ),
        require_advisory_for_explore=bool(
            runner_d.get("require_advisory_for_explore", False)
        ),
        advisory_sources=list(
            runner_d.get("advisory_sources", ["ml_shadow", "dream_engine"]) or []
        ),
        advisory_max_age_hours=int(runner_d.get("advisory_max_age_hours", 48)),
        advisory_min_confidence=float(runner_d.get("advisory_min_confidence", 0.5)),
        advisory_min_expected_net_bps=float(
            runner_d.get("advisory_min_expected_net_bps", 0.0)
        ),
        advisory_min_sample_count=int(runner_d.get("advisory_min_sample_count", 10)),
        advisory_allow_requires_governance=bool(
            runner_d.get("advisory_allow_requires_governance", False)
        ),
        use_edge_snapshot_for_explore_evidence=bool(
            runner_d.get("use_edge_snapshot_for_explore_evidence", False)
        ),
        require_cost_viable_edge_for_explore_when_available=bool(
            runner_d.get(
                "require_cost_viable_edge_for_explore_when_available",
                True,
            )
        ),
        edge_evidence_fee_rate=float(runner_d.get("edge_evidence_fee_rate", 0.00055)),
        edge_evidence_slippage=float(runner_d.get("edge_evidence_slippage", 0.0)),
        edge_evidence_win_rate_floor=float(
            runner_d.get("edge_evidence_win_rate_floor", 0.3)
        ),
        edge_evidence_safety_multiplier=float(
            runner_d.get("edge_evidence_safety_multiplier", 1.3)
        ),
        edge_evidence_grid_min_n=int(runner_d.get("edge_evidence_grid_min_n", 30)),
        edge_evidence_require_runtime_symbol_ready=bool(
            runner_d.get("edge_evidence_require_runtime_symbol_ready", False)
        ),
        edge_evidence_runtime_snapshot_path=str(
            runner_d.get(
                "edge_evidence_runtime_snapshot_path",
                "/tmp/openclaw/pipeline_snapshot.json",
            )
        ),
    )

    # AllocatorConfig：只覆寫 TOML 有提供的欄位，其餘用 dataclass 預設。
    alloc_cfg = AllocatorConfig()
    for fld in (
        "positive_prob_gate",
        "prob_mc_samples",
        "flat_arm_cost_floor_bps",
        "explore_budget",
        "forgetting_gamma",
        "dormant_clear_after_ticks",
        "trust_track",
    ):
        if fld in alloc_d:
            setattr(alloc_cfg, fld, alloc_d[fld])

    return runner_cfg, alloc_cfg


# ---------------------------------------------------------------------------
# cycle 審計輸出
# ---------------------------------------------------------------------------


@dataclass
class CandidateDecision:
    """單一 (strategy, regime) 候選在本 cycle 的配置決策（審計用）。"""

    strategy: str
    regime: str
    arm_id: str
    weight: float
    is_active_winner: bool  # 該 (strategy, regime) 是否為 regime 內非 flat 贏家
    saw_artifact: bool      # all_fills 軌是否曾被 demo artifact 污染


@dataclass
class CycleReport:
    """一個閉環 cycle 的完整審計快照。"""

    engine_mode: str
    dry_run: bool
    n_rewards_ingested: int
    candidate_decisions: list[CandidateDecision] = field(default_factory=list)
    desired_active: dict[str, bool] = field(default_factory=dict)
    apply_changes: list[dict] = field(default_factory=list)
    all_regimes_flat: bool = False  # 是否所有候選 regime 都歸 flat（全負 EV）
    # Track1 demo explore-gate：本 cycle explore sink 的審計快照（None=未啟用 sink）。
    explore_sink: Optional[dict] = None
    # Controlled experiment policy audit（None=未啟用 controlled mode）。
    experiment_policy: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "engine_mode": self.engine_mode,
            "dry_run": self.dry_run,
            "n_rewards_ingested": self.n_rewards_ingested,
            "all_regimes_flat": self.all_regimes_flat,
            "explore_sink": self.explore_sink,
            "experiment_policy": self.experiment_policy,
            "desired_active": self.desired_active,
            "candidate_decisions": [
                {
                    "strategy": d.strategy,
                    "regime": d.regime,
                    "arm_id": d.arm_id,
                    "weight": round(d.weight, 6),
                    "is_active_winner": d.is_active_winner,
                    "saw_artifact": d.saw_artifact,
                }
                for d in self.candidate_decisions
            ],
            "apply_changes": self.apply_changes,
        }


def _norm_set(values: list[str]) -> set[str]:
    return {str(v).strip() for v in values if str(v).strip()}


def _finite_float(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _canonical_entry_side(side: str) -> Optional[str]:
    side_s = str(side).strip().lower()
    if side_s == "buy":
        return "Buy"
    if side_s == "sell":
        return "Sell"
    return None


def _cell_bps(cell: dict) -> Optional[float]:
    # Match Rust EdgeEstimates semantics: runtime_bps, when present and numeric,
    # overrides legacy shrunk_bps.
    if "runtime_bps" in cell:
        runtime_bps = _finite_float(cell.get("runtime_bps"))
        if runtime_bps is not None:
            return runtime_bps
    return _finite_float(cell.get("shrunk_bps"))


def _cell_win_rate(cell: dict) -> float:
    win_rate = _finite_float(cell.get("win_rate_shrunk"))
    if win_rate is None:
        win_rate = _finite_float(cell.get("win_rate"))
    if win_rate is None:
        return 0.5
    return max(0.0, min(1.0, win_rate))


def _cell_n(cell: dict) -> int:
    for key in ("n", "n_trades", "sample_count", "n_observations"):
        value = _finite_float(cell.get(key))
        if value is not None:
            return max(0, int(value))
    return 0


def fetch_recent_advisory_strategy_scores(
    dsn: str,
    cfg: AdpeRunnerConfig,
    *,
    _connect=None,
) -> dict[str, float]:
    """Read L2 / multi-agent positive advisory rows as explore-eligibility evidence.

    This is deliberately read-only and strategy-level. It does not apply model
    output, mutate params, or grant order authority; it only lets controlled
    experiment mode decide which under-sampled strategies may stay active.

    Sources:
      - learning.mlde_shadow_recommendations: quantitative ml_shadow/dream rows.
      - agent.lessons: inert L2 ml_advisory backlog, only when hypothesize math
        gate passed. Neutral diagnose/interpret and DEFER rows do not count.
    """
    sources = sorted(_norm_set(cfg.advisory_sources))
    connect = _connect
    if connect is None:
        try:
            import psycopg2  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - production dependency
            raise RuntimeError("psycopg2 not installed / psycopg2 未安裝") from exc
        connect = psycopg2.connect

    shadow_sql = """
        SELECT
            strategy_name,
            max(COALESCE(expected_net_bps, 0.0) * COALESCE(confidence, 0.0))::float8
                AS advisory_score
          FROM learning.mlde_shadow_recommendations
         WHERE engine_mode = %s
           AND ts >= now() - (%s::int || ' hours')::interval
           AND source = ANY(%s)
           AND recommendation_type IN ('rank', 'parameter_proposal')
           AND COALESCE(expected_net_bps, 0.0) >= %s
           AND COALESCE(confidence, 0.0) >= %s
           AND COALESCE(sample_count, 0) >= %s
           AND (%s OR NOT COALESCE(requires_governance, false))
         GROUP BY strategy_name
    """
    lessons_sql = """
        SELECT content
          FROM agent.lessons
         WHERE source = 'ml_advisory'
           AND lesson_type = 'hypothesize'
           AND created_at >= now() - (%s::int || ' hours')::interval
           AND content LIKE %s
    """
    out: dict[str, float] = {}
    with connect(dsn, connect_timeout=2) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = %s", (5000,))
            if sources:
                cur.execute(
                    shadow_sql,
                    (
                        cfg.engine_mode,
                        cfg.advisory_max_age_hours,
                        sources,
                        cfg.advisory_min_expected_net_bps,
                        cfg.advisory_min_confidence,
                        cfg.advisory_min_sample_count,
                        cfg.advisory_allow_requires_governance,
                    ),
                )
                for strategy, score in cur.fetchall():
                    if strategy:
                        out[str(strategy)] = max(
                            out.get(str(strategy), 0.0),
                            float(score or 0.0),
                        )
            try:
                cur.execute(
                    lessons_sql,
                    (cfg.advisory_max_age_hours, "ml_advisory:hypothesize:%"),
                )
                lesson_rows = cur.fetchall()
            except Exception as exc:  # noqa: BLE001
                logger.info("ADPE ml_advisory agent.lessons evidence skipped: %s", exc)
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001
                    pass
                lesson_rows = []
            for row in lesson_rows:
                if not row:
                    continue
                parsed = _parse_ml_advisory_hypothesis_score(
                    str(row[0]), engine_mode=cfg.engine_mode
                )
                if parsed is None:
                    continue
                strategy, score = parsed
                out[strategy] = max(out.get(strategy, 0.0), score)
    return out


def _parse_ml_advisory_hypothesis_score(
    content: str, *, engine_mode: str
) -> Optional[tuple[str, float]]:
    """Extract a strategy score from an inert ml_advisory hypothesis lesson.

    agent.lessons stores the executor payload as text by design. We only treat
    deterministic math-gate pass hypotheses as positive evidence. Everything
    else is memory/backlog, not authority to keep a strategy running.
    """
    prefix = "ml_advisory:hypothesize:"
    if not content.startswith(prefix):
        return None
    raw = content[len(prefix):].strip()
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if body.get("ml_advisory_mode") != "hypothesize":
        return None
    if str(body.get("engine_mode", "")).strip() != engine_mode:
        return None
    advisory = body.get("advisory")
    if not isinstance(advisory, dict):
        return None
    gate_verdict = advisory.get("gate_verdict")
    math_gate = advisory.get("math_gate")
    if gate_verdict is None and isinstance(math_gate, dict):
        gate_verdict = math_gate.get("verdict")
    if str(gate_verdict).lower() != "pass":
        return None

    strategy = str(body.get("strategy_name") or "").strip()
    if not strategy:
        strategy = str(
            advisory.get("strategy_name") or advisory.get("strategy") or ""
        ).strip()
    if not strategy:
        return None
    # A deterministic math-gate pass is binary positive evidence. Keep the score
    # modest so quantitative post-fee advisory rows still rank first.
    return strategy, 1.0


# ---------------------------------------------------------------------------
# 閉環 runner
# ---------------------------------------------------------------------------


class AdpeRunner:
    """ADPE 閉環 runner（demo 沙盒）。

    依賴注入：allocator / lever / rewards_fn 都可注入，便於單元測試（不連真 PG/IPC）。
    """

    def __init__(
        self,
        runner_cfg: Optional[AdpeRunnerConfig] = None,
        alloc_cfg: Optional[AllocatorConfig] = None,
        *,
        allocator: Optional[RegimeBanditAllocator] = None,
        lever: Optional[StrategyLever] = None,
        rewards_fn=None,
        advisory_fn=None,
        dsn: Optional[str] = None,
        edge_estimates_path: Optional[str] = None,
    ):
        self.runner_cfg = runner_cfg or AdpeRunnerConfig()
        self.alloc_cfg = alloc_cfg or AllocatorConfig()
        self.allocator = allocator or RegimeBanditAllocator(self.alloc_cfg)
        self.lever = lever or StrategyLever()
        # rewards_fn：注入點（測試 / 替代源）；預設用 reward_source.fetch_demo_arm_rewards。
        self._rewards_fn = rewards_fn or self._default_rewards_fn
        # advisory_fn：注入點（測試 / 替代源）；預設讀 L2/multi-agent advisory 表。
        self._advisory_fn = advisory_fn or self._default_advisory_fn
        self._dsn = dsn
        self._rng = random.Random(self.runner_cfg.rng_seed)
        # Track1 demo explore-gate：edge_estimates.json 路徑（測試可注入 scratch 檔）。
        self._edge_estimates_path = edge_estimates_path or _DEFAULT_EDGE_ESTIMATES_PATH
        self._last_experiment_policy: Optional[dict] = None

    # ---- engine_mode 硬鎖 -------------------------------------------------

    def _assert_demo(self) -> None:
        """fail-closed：非 demo engine_mode 直接拒絕整個 cycle。"""
        if self.runner_cfg.engine_mode != _DEMO_ENGINE_MODE:
            raise RuntimeError(
                f"ADPE 只允許 demo 沙盒，engine_mode={self.runner_cfg.engine_mode!r} 被拒絕 "
                "（真錢 / mainnet / live 路徑不碰）"
            )

    # ---- reward 讀取 ------------------------------------------------------

    def _default_rewards_fn(self) -> list[ArmReward]:
        if self._dsn is None:
            logger.info("ADPE 無 dsn，reward 源為空（cold-start，全 explore）")
            return []
        return fetch_demo_arm_rewards(
            self._dsn,
            max_age_days=self.runner_cfg.reward_max_age_days,
        )

    def _default_advisory_fn(self) -> dict[str, float]:
        if (
            not self.runner_cfg.controlled_experiment_enabled
            or not self.runner_cfg.require_advisory_for_explore
        ):
            return {}
        if self._dsn is None:
            logger.info("ADPE 無 dsn，L2/multi-agent advisory evidence 為空")
            return {}
        try:
            return fetch_recent_advisory_strategy_scores(self._dsn, self.runner_cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ADPE advisory evidence 讀取失敗，controlled explore fail-closed: %s", exc)
            return {}

    def ingest_demo_maker_outcome(self, realized_spread_bps: float, ts: float) -> None:
        """把一筆 demo-maker round-trip 已實現價差餵進 allocator。

        誠實隔離：build_demo_maker_reward 硬編 artifact tier → all_fills 軌吸收且標
        saw_artifact、transferable_only 軌（promotion 軌）不吸收。runner 不合成價差。
        """
        reward = build_demo_maker_reward(realized_spread_bps, ts)
        self.allocator.ingest_arm_outcome(
            arm_id=reward.arm_id,
            regime=reward.regime,
            realized_pnl_bps=reward.realized_pnl_bps,
            ts=reward.ts,
            fill_realism_tier=reward.fill_realism_tier,
        )

    # ---- 候選列舉 ---------------------------------------------------------

    def _candidate_regimes(self) -> list[str]:
        regimes = self.runner_cfg.candidate_regimes or list(VALID_REGIMES)
        return [r for r in regimes if r in VALID_REGIMES]

    def _discover_candidate_arms(
        self, ingested_arm_ids: set[str]
    ) -> dict[str, list[str]]:
        """回 {regime: [arm_id, ...]}：候選 arm 按 regime 分組。

        來源 = ingest 過的 arm_id（含 demo-maker，若納入）∪ config candidate_strategies
        × candidate_regimes 的笛卡爾。flat-arm 不在候選（allocate 內部自動加）。
        """
        by_regime: dict[str, list[str]] = {r: [] for r in self._candidate_regimes()}

        # 1) 從 ingest 過的真實 arm_id 分組（arm_id='regime__strategy'）。
        for arm_id in ingested_arm_ids:
            if arm_id == FLAT_ARM_ID:
                continue
            try:
                regime, _strategy = parse_arm_id(arm_id)
            except ValueError:
                continue
            if regime in by_regime and arm_id not in by_regime[regime]:
                by_regime[regime].append(arm_id)

        # 2) config 顯式 candidate_strategies × candidate_regimes 補進（cold-start 也有候選）。
        for strategy in self.runner_cfg.candidate_strategies:
            for regime in by_regime:
                arm_id = make_arm_id(regime, strategy)
                if arm_id not in by_regime[regime]:
                    by_regime[regime].append(arm_id)

        return by_regime

    # ---- 配置決策 ---------------------------------------------------------

    def build_desired_active(
        self,
        by_regime: dict[str, list[str]],
        advisory_scores: Optional[dict[str, float]] = None,
        edge_evidence_scores: Optional[dict[str, float]] = None,
        edge_evidence_cells: Optional[list[dict]] = None,
    ) -> tuple[dict[str, bool], list[CandidateDecision], bool]:
        """對每個 regime allocate，把贏家映成 active、負 EV 映成 dormant。

        映射規則（誠實鐵則）：
          - 對每 regime 跑 allocator.allocate → 權重 dict（含 flat）。
          - 某 (strategy, regime) arm 權重 > 0 且非 flat → 該 strategy 標 active（贏家）。
          - 全 regime 皆 flat（全負 EV）→ all_regimes_flat=True。
        active 是「任一 regime 為贏家即 active」的 union（strategy 級 lever）。

        explore-eligible 保活（為什麼）：enable_explore_sink=True 時，desired 還要
        union 進「explore-eligible 策略」。否則 rich-signal 下若 winner 全空（all-flat）
        會把全策略停用 → 無單產生 → demo explore-gate（gates.rs 在 order 上放行）永不
        觸發 → 無探索數據 → 學習器持續饑餓。為打破此死結，凡某 (strategy, regime) arm
        的 allocator.explore_budget_remaining(arm_id) > 0（=該 arm 仍在探索期、under-
        sampled）即把該 strategy 保 active，讓它產單供 explore-gate 放行。
        **有界**：explore_budget_remaining==0（探索額度耗盡，已達 explore_budget=30）的
        arm 不保活——耗盡即停，不是全放行。explore-eligibility 讀 allocator 真實
        explore_budget_remaining（真實信號，非寫死）。explore 關時行為不變（純 winner）。
        """
        decisions: list[CandidateDecision] = []
        active_strategies: set[str] = set()
        explore_eligible_strategies: dict[str, int] = {}
        seen_strategies: set[str] = set()
        any_non_flat_winner = False
        advisory_scores = advisory_scores or {}
        edge_evidence_scores = edge_evidence_scores or {}
        edge_evidence_cells = edge_evidence_cells or []
        self._last_experiment_policy = None

        for regime, arms in by_regime.items():
            if not arms:
                continue
            weights = self.allocator.allocate(regime, arms, rng=self._rng)
            for arm_id in arms:
                w = weights.get(arm_id, 0.0)
                regime_v, strategy = parse_arm_id(arm_id)
                seen_strategies.add(strategy)
                is_winner = w > 0.0
                if is_winner:
                    active_strategies.add(strategy)
                    any_non_flat_winner = True
                # explore-eligible：只在 enable_explore_sink 時計算（行為門控）。
                # 讀 allocator 真實 explore_budget_remaining（>0=仍 under-sampled，
                # 探索期未耗盡）；==0 不保活（有界探索，對齊 explore_budget=30）。
                if self.runner_cfg.enable_explore_sink:
                    remaining = int(self.allocator.explore_budget_remaining(arm_id))
                    if remaining > 0:
                        explore_eligible_strategies[strategy] = max(
                            remaining,
                            explore_eligible_strategies.get(strategy, 0),
                        )
                diag = self.allocator.arm_diagnostics(arm_id, rng=self._rng)
                decisions.append(
                    CandidateDecision(
                        strategy=strategy,
                        regime=regime_v,
                        arm_id=arm_id,
                        weight=w,
                        is_active_winner=is_winner,
                        saw_artifact=bool(diag.get("saw_artifact", False)),
                    )
                )

        selected_explore, policy_audit = self._select_explore_keepalive(
            explore_eligible_strategies,
            active_strategies,
            advisory_scores,
            edge_evidence_scores,
            edge_evidence_cells,
        )
        self._last_experiment_policy = policy_audit

        # desired：贏家→True；explore 開時 explore-eligible（額度未耗盡）的策略亦保
        # active（供 explore-gate 放行產生探索數據）；其餘→False（負 EV 且非探索 → 歸零）。
        keep_active = active_strategies | selected_explore
        desired = {s: (s in keep_active) for s in seen_strategies}
        # 退役 / 禁止策略最後一層 hard override：即使 winner 或 explore 命中，也不得 active。
        for strategy in _norm_set(self.runner_cfg.retired_strategy_blocklist):
            if strategy in desired:
                desired[strategy] = False
                if self._last_experiment_policy is not None:
                    self._last_experiment_policy.setdefault("forced_dormant", []).append(strategy)
        # all_regimes_flat 仍只反映「allocate 出的權重」（winner 視角），與 explore 保活
        # 正交：即使無 winner，explore 保活仍會讓 desired 含 active 策略（這正是修復目的）。
        all_flat = (not any_non_flat_winner) and bool(seen_strategies)
        return desired, decisions, all_flat

    def _select_explore_keepalive(
        self,
        explore_candidates: dict[str, int],
        active_winners: set[str],
        advisory_scores: dict[str, float],
        edge_evidence_scores: dict[str, float],
        edge_evidence_cells: list[dict],
    ) -> tuple[set[str], Optional[dict]]:
        """Filter under-sampled explore candidates through controlled-experiment policy."""
        if not self.runner_cfg.enable_explore_sink:
            return set(), None
        if not self.runner_cfg.controlled_experiment_enabled:
            return set(explore_candidates), None

        retired = _norm_set(self.runner_cfg.retired_strategy_blocklist)
        allowlist = _norm_set(self.runner_cfg.explore_strategy_allowlist)
        require_advisory = bool(self.runner_cfg.require_advisory_for_explore)
        edge_evidence_candidate_strategies = set(explore_candidates) & set(
            edge_evidence_scores
        )
        require_cost_edge = (
            bool(self.runner_cfg.require_cost_viable_edge_for_explore_when_available)
            and bool(edge_evidence_candidate_strategies)
        )
        rejected: dict[str, str] = {}
        eligible: list[tuple[float, int, str]] = []

        for strategy, remaining in explore_candidates.items():
            if strategy in active_winners:
                continue
            if strategy in retired:
                rejected[strategy] = "retired_strategy_blocklist"
                continue
            if allowlist and strategy not in allowlist:
                rejected[strategy] = "not_in_explore_strategy_allowlist"
                continue
            advisory_score = float(advisory_scores.get(strategy, 0.0))
            edge_score = float(edge_evidence_scores.get(strategy, 0.0))
            score = max(advisory_score, edge_score)
            if require_cost_edge and strategy not in edge_evidence_scores:
                rejected[strategy] = "missing_cost_viable_edge_evidence"
                continue
            if require_advisory and strategy not in advisory_scores:
                if strategy not in edge_evidence_scores:
                    rejected[strategy] = "missing_positive_advisory_evidence"
                    continue
            eligible.append((score, int(remaining), strategy))

        eligible.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        cap = max(0, int(self.runner_cfg.max_active_explore_strategies))
        selected_items = eligible[:cap] if cap > 0 else eligible
        selected = {strategy for _score, _remaining, strategy in selected_items}
        for _score, _remaining, strategy in eligible[len(selected_items):]:
            rejected[strategy] = "max_active_explore_strategies_cap"

        audit = {
            "enabled": True,
            "require_advisory_for_explore": require_advisory,
            "max_active_explore_strategies": cap,
            "retired_strategy_blocklist": sorted(retired),
            "explore_strategy_allowlist": sorted(allowlist),
            "raw_explore_candidates": dict(sorted(explore_candidates.items())),
            "advisory_scores": {
                k: round(float(v), 6) for k, v in sorted(advisory_scores.items())
            },
            "edge_evidence_scores": {
                k: round(float(v), 6) for k, v in sorted(edge_evidence_scores.items())
            },
            "edge_evidence_cells": edge_evidence_cells[:20],
            "require_cost_viable_edge_when_available": require_cost_edge,
            "selected_explore": sorted(selected),
            "rejected_explore": dict(sorted(rejected.items())),
            "forced_dormant": [],
        }
        return selected, audit

    def _load_side_edge_evidence(self) -> tuple[dict[str, float], list[dict]]:
        """Load cost-viable entry-side cells as explore keepalive evidence.

        ADPE only uses this to choose which strategy may remain active enough to
        emit intents. The Rust cost gate remains the authority for every order.
        """
        if (
            not self.runner_cfg.use_edge_snapshot_for_explore_evidence
            or not self.runner_cfg.enable_explore_sink
            or not self.runner_cfg.controlled_experiment_enabled
        ):
            return {}, []
        try:
            with open(self._edge_estimates_path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        except FileNotFoundError:
            logger.info("ADPE edge evidence: edge_estimates.json missing")
            return {}, []
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("ADPE edge evidence: edge_estimates.json unreadable: %s", exc)
            return {}, []
        if not isinstance(snapshot, dict):
            return {}, []

        fee_rate = max(0.0, float(self.runner_cfg.edge_evidence_fee_rate))
        slippage = max(0.0, float(self.runner_cfg.edge_evidence_slippage))
        fee_bps = 2.0 * (fee_rate + slippage) * 10_000.0
        win_rate_floor = max(1e-9, min(1.0, self.runner_cfg.edge_evidence_win_rate_floor))
        safety_multiplier = max(1.0, self.runner_cfg.edge_evidence_safety_multiplier)
        grid_min_n = max(0, int(self.runner_cfg.edge_evidence_grid_min_n))
        runtime_snapshot = self._load_edge_evidence_runtime_snapshot()
        ready_symbols = (
            self._runtime_ready_symbols(runtime_snapshot)
            if self.runner_cfg.edge_evidence_require_runtime_symbol_ready
            else None
        )
        skipped_unready = 0

        scores: dict[str, float] = {}
        cells: list[dict] = []
        for key, raw_cell in snapshot.items():
            if key == "_meta" or not isinstance(raw_cell, dict):
                continue
            parts = str(key).split("::")
            if len(parts) != 3:
                continue
            strategy, symbol, side_raw = (p.strip() for p in parts)
            side = _canonical_entry_side(side_raw)
            if not strategy or not symbol or side is None:
                continue
            if ready_symbols is not None and symbol not in ready_symbols:
                skipped_unready += 1
                continue
            bps = _cell_bps(raw_cell)
            if bps is None or bps <= 0.0:
                continue
            n_trades = _cell_n(raw_cell)
            if strategy == "grid_trading" and n_trades < grid_min_n:
                continue
            win_rate = _cell_win_rate(raw_cell)
            threshold_bps = fee_bps / max(win_rate, win_rate_floor) * safety_multiplier
            margin_bps = bps - threshold_bps
            if margin_bps <= 0.0:
                continue
            scores[strategy] = max(scores.get(strategy, 0.0), margin_bps)
            cells.append(
                {
                    "strategy": strategy,
                    "symbol": symbol,
                    "side": side,
                    "key": key,
                    "bps": round(bps, 6),
                    "threshold_bps": round(threshold_bps, 6),
                    "margin_bps": round(margin_bps, 6),
                    "win_rate": round(win_rate, 6),
                    "n": n_trades,
                    "readiness": self._classify_edge_cell_readiness(
                        strategy,
                        symbol,
                        side,
                        runtime_snapshot,
                    ),
                }
            )

        cells.sort(key=lambda item: (item["margin_bps"], item["key"]), reverse=True)
        if skipped_unready:
            logger.info(
                "ADPE edge evidence: skipped %d side cells without runtime-ready symbol",
                skipped_unready,
            )
        return scores, cells

    def _load_edge_evidence_runtime_snapshot(self) -> Optional[dict]:
        path = str(self.runner_cfg.edge_evidence_runtime_snapshot_path or "").strip()
        if not path:
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            logger.info("ADPE edge evidence: runtime symbol readiness skipped: %s", exc)
            return None
        if not isinstance(snapshot, dict):
            return None
        return snapshot

    def _runtime_ready_symbols(self, snapshot: Optional[dict]) -> Optional[set[str]]:
        if not isinstance(snapshot, dict):
            return None
        latest_prices = snapshot.get("latest_prices")
        indicators = snapshot.get("indicators")
        if not isinstance(latest_prices, dict) or not isinstance(indicators, dict):
            return None
        ready: set[str] = set()
        for symbol, price in latest_prices.items():
            symbol_s = str(symbol).strip()
            if not symbol_s or _finite_float(price) is None:
                continue
            if isinstance(indicators.get(symbol_s), dict):
                ready.add(symbol_s)
        return ready

    def _classify_edge_cell_readiness(
        self,
        strategy: str,
        symbol: str,
        side: str,
        runtime_snapshot: Optional[dict],
    ) -> dict:
        """Explain why a cost-viable side cell can or cannot produce an entry now.

        This is an audit-only mirror for operator visibility. It intentionally
        does not grant or deny orders; Rust strategy code and cost gates remain
        authoritative.
        """
        desired_direction = "Long" if side == "Buy" else "Short"
        out = {
            "status": "strategy_readiness_unknown",
            "desired_direction": desired_direction,
            "reasons": [],
        }
        if not isinstance(runtime_snapshot, dict):
            out["status"] = "runtime_unavailable"
            out["reasons"] = ["runtime_snapshot_unavailable"]
            return out

        latest_prices = runtime_snapshot.get("latest_prices")
        indicators = runtime_snapshot.get("indicators")
        price = latest_prices.get(symbol) if isinstance(latest_prices, dict) else None
        indicator = indicators.get(symbol) if isinstance(indicators, dict) else None
        if _finite_float(price) is None or not isinstance(indicator, dict):
            out["status"] = "runtime_unavailable"
            out["reasons"] = ["runtime_symbol_not_ready"]
            return out

        if strategy != "ma_crossover":
            out["status"] = "strategy_readiness_unknown"
            out["reasons"] = ["strategy_readiness_not_implemented"]
            return out

        reasons: list[str] = []
        signal = self._latest_runtime_signal(runtime_snapshot, strategy, symbol)
        if signal is None:
            reasons.append("no_current_ma_signal")
        else:
            signal_direction = str(signal.get("direction") or "").strip()
            out["signal_direction"] = signal_direction
            out["signal_confidence"] = _finite_float(signal.get("confidence"))
            out["signal_edge_bps"] = _finite_float(signal.get("edge_bps"))
            if signal_direction != desired_direction:
                reasons.append(f"ma_signal_opposite:{signal_direction or 'unknown'}")

        indicator_direction = self._ma_indicator_direction(indicator)
        out["indicator_direction"] = indicator_direction or "unknown"
        if indicator_direction is None:
            reasons.append("ma_indicator_direction_unavailable")
        elif indicator_direction != desired_direction:
            reasons.append(f"ma_kama_sma_direction_opposite:{indicator_direction}")

        hurst = indicator.get("hurst")
        hurst_regime = None
        if isinstance(hurst, dict):
            hurst_regime = str(hurst.get("regime") or "").strip()
        out["hurst_regime"] = hurst_regime or "unknown"
        if hurst_regime and hurst_regime != "trending":
            reasons.append(f"ma_hurst_not_persistent:{hurst_regime}")

        if reasons:
            out["reasons"] = reasons
            out["status"] = (
                "waiting_for_signal"
                if reasons == ["no_current_ma_signal"]
                else "blocked_by_strategy_state"
            )
            return out

        out["status"] = "entry_ready"
        out["reasons"] = []
        return out

    def _latest_runtime_signal(
        self,
        runtime_snapshot: dict,
        strategy: str,
        symbol: str,
    ) -> Optional[dict]:
        signals = runtime_snapshot.get("signals")
        if not isinstance(signals, list):
            return None
        candidates = [
            s
            for s in signals
            if isinstance(s, dict)
            and str(s.get("source") or "") == strategy
            and str(s.get("symbol") or "") == symbol
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda s: int(_finite_float(s.get("ts_ms")) or 0))

    def _ma_indicator_direction(self, indicator: dict) -> Optional[str]:
        kama = indicator.get("kama")
        fast = None
        if isinstance(kama, dict):
            fast = _finite_float(kama.get("kama"))
        slow = _finite_float(indicator.get("sma_20"))
        if fast is None or slow is None or fast == slow:
            return None
        return "Long" if fast > slow else "Short"

    # ---- 一個 cycle -------------------------------------------------------

    def run_cycle(self, *, dry_run: Optional[bool] = None) -> CycleReport:
        """跑一個閉環 cycle：reward → ingest → allocate → apply（demo 硬鎖）。"""
        self._assert_demo()
        effective_dry = (
            self.runner_cfg.dry_run_default if dry_run is None else bool(dry_run)
        )

        # 1) 讀 demo realized reward。
        rewards = self._rewards_fn() or []

        # 2) ingest（view reward 走 ingest_arm_outcome；fill tier 由 reward 攜帶）。
        ingested_arm_ids: set[str] = set()
        for r in rewards:
            try:
                self.allocator.ingest_arm_outcome(
                    arm_id=r.arm_id,
                    regime=r.regime,
                    realized_pnl_bps=r.realized_pnl_bps,
                    ts=r.ts,
                    fill_realism_tier=r.fill_realism_tier,
                )
                ingested_arm_ids.add(r.arm_id)
            except ValueError as e:
                # 非法 regime / tier 的單筆 reward 跳過，不污染整 cycle。
                logger.warning("跳過非法 reward arm_id=%s: %s", r.arm_id, e)

        # demo-maker candidate arm 若納入，確保它在候選裡（即使本 cycle 無新 maker reward）。
        if self.runner_cfg.include_demo_maker_arm:
            ingested_arm_ids.add(DEMO_MAKER_ARM.arm_id)

        # 3) Controlled experiment advisory evidence（read-only L2 / multi-agent evidence）。
        advisory_scores = self._advisory_fn() or {}
        edge_evidence_scores, edge_evidence_cells = self._load_side_edge_evidence()

        # 4) 候選列舉 + 5) 逐 regime allocate → desired active。
        by_regime = self._discover_candidate_arms(ingested_arm_ids)
        desired, decisions, all_flat = self.build_desired_active(
            by_regime,
            advisory_scores=advisory_scores,
            edge_evidence_scores=edge_evidence_scores,
            edge_evidence_cells=edge_evidence_cells,
        )

        # 6) 經 lever 落到 demo 引擎（冪等 diff；dry-run 不發 IPC）。
        apply_result: ApplyResult = self.lever.apply_desired(desired, dry_run=effective_dry)

        # 7) Track1 demo explore-gate：算 explore overlay 並 additive 注入 edge_estimates.json
        #    （opt-in；dry-run 不寫檔，與 lever 同一 dry_run 紀律）。
        explore_audit: Optional[dict] = None
        if self.runner_cfg.enable_explore_sink:
            explore_audit = self._run_explore_sink(dry_run=effective_dry)

        report = CycleReport(
            engine_mode=self.runner_cfg.engine_mode,
            dry_run=effective_dry,
            n_rewards_ingested=len(rewards),
            candidate_decisions=decisions,
            desired_active=desired,
            apply_changes=[
                {
                    "strategy": c.strategy,
                    "target_active": c.target_active,
                    "status": c.status,
                    "detail": c.detail,
                }
                for c in apply_result.changes
            ],
            all_regimes_flat=all_flat,
            explore_sink=explore_audit,
            experiment_policy=self._last_experiment_policy,
        )
        logger.info(
            "ADPE cycle done: dry_run=%s rewards=%d active=%d all_flat=%s",
            effective_dry,
            len(rewards),
            sum(1 for v in desired.values() if v),
            all_flat,
        )
        return report

    # ---- Track1 demo explore-gate sink -----------------------------------

    def _load_candidate_cells(self) -> list[str]:
        """讀現有 edge_estimates.json 的 cell key 列表（'strategy::symbol'）。

        為什麼以現有 cell 為候選：explore overlay 只標註「gate 已關心的格子」，
        不憑空建 cell（additive 守恆）。缺檔 / 解析失敗 → 回空（fail-soft：本 cycle
        無 overlay，不污染閉環）。symbol 維由現有 cell 提供（design §3.3 symbol fan-out）。
        """
        try:
            with open(self._edge_estimates_path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        except FileNotFoundError:
            logger.info("explore sink: edge_estimates.json 不存在，本 cycle 無候選 cell")
            return []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("explore sink: edge_estimates.json 解析失敗，本 cycle 無候選: %s", e)
            return []
        if not isinstance(snapshot, dict):
            return []
        # 跳過 _meta 與非 'strategy::symbol' 形狀的 key（build_explore_overlay 再過濾一次）。
        return [k for k in snapshot.keys() if k != "_meta" and "::" in k]

    def _run_explore_sink(self, *, dry_run: bool) -> dict:
        """算 explore overlay（真實 allocator n_trials 衍生）並 additive 注入 edge_estimates.json。

        誠實鐵則：overlay 完全由 allocator.explore_budget_remaining 推導（build_explore_overlay
        內部），runner 不寫死任何 eligible。dry_run 透傳 sink（dry-run 不寫檔），與 lever 同紀律。
        """
        candidate_cells = self._load_candidate_cells()
        overlay = build_explore_overlay(
            self.allocator,
            self.runner_cfg.explore_current_regime,
            candidate_cells,
        )
        # apply = not dry_run：dry-run 只產 plan；真 cycle（--apply）才落檔。
        return merge_into_edge_estimates(
            overlay,
            self._edge_estimates_path,
            dry_run=dry_run,
            apply=not dry_run,
        )

    # ---- kill switch ------------------------------------------------------

    def kill_switch_snapshot(self) -> dict[str, bool]:
        """拍下當前策略 active 態快照（啟用 apply 前先存，供 kill_switch 還原）。"""
        return self.lever.read_active_snapshot()

    def kill_switch(
        self,
        snapshot: dict[str, bool],
        *,
        dry_run: bool = False,
    ) -> ApplyResult:
        """一鍵停：把策略 active 態還原成傳入 snapshot。

        注意：本函數只「還原 active 態」；停 runner 進程（cron / 迴圈）由呼叫端負責
        （移除 cron entry / 設停旗標）。dry_run 預設 False（kill 是真要還原）。
        """
        logger.warning("ADPE kill switch 觸發：還原 %d 個策略 active 態", len(snapshot))
        return self.lever.restore_snapshot(snapshot, dry_run=dry_run)


# ---------------------------------------------------------------------------
# CLI / cron entry
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    """argparse CLI：cron 跑一個 cycle（默認 dry-run），或一鍵 kill-switch。

    --apply         真發 IPC（否則 dry-run 只產 plan）。
    --kill-switch   讀當前快照後立即還原（一鍵停 active 態變動；通常配合移除 cron）。
    --snapshot-out  把 kill_switch_snapshot 寫到指定 JSON 檔（啟用 apply 前先存）。
    --config        config TOML 路徑。
    --dsn           PG 連線字串（不傳則無 reward 源，全 cold-start）。
    """
    parser = argparse.ArgumentParser(description="Adaptive Demo Profit Engine runner (demo-only)")
    parser.add_argument("--config", default=None, help="adaptive_demo_profit.toml 路徑")
    parser.add_argument("--dsn", default=os.environ.get("OPENCLAW_DATABASE_URL"), help="PG DSN")
    parser.add_argument("--apply", action="store_true", help="真發 IPC（否則 dry-run）")
    parser.add_argument("--kill-switch", action="store_true", help="一鍵還原 active 態快照")
    parser.add_argument("--snapshot-out", default=None, help="把當前 active 快照寫到此 JSON 檔")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed（可重現）")
    parser.add_argument(
        "--explore-sink",
        action="store_true",
        help="Track1 demo explore-gate：本 cycle 算 explore overlay 並 additive 注入 "
        "edge_estimates.json（仍受 --apply 控制；無 --apply 為 dry-run 不寫檔）",
    )
    parser.add_argument(
        "--explore-regime",
        default=None,
        help="explore overlay 用的當前 regime（默認 config / insufficient_context）",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    runner_cfg, alloc_cfg = load_runner_config(args.config)
    if args.seed is not None:
        runner_cfg.rng_seed = args.seed
    if args.explore_sink:
        runner_cfg.enable_explore_sink = True
    if args.explore_regime is not None:
        runner_cfg.explore_current_regime = args.explore_regime
    runner = AdpeRunner(runner_cfg, alloc_cfg, dsn=args.dsn)

    # kill-switch：讀現態 → 立即還原（demo 硬鎖也適用，restore 只動 active 態）。
    if args.kill_switch:
        snap = runner.kill_switch_snapshot()
        result = runner.kill_switch(snap, dry_run=not args.apply)
        print(json.dumps({
            "action": "kill_switch",
            "dry_run": not args.apply,
            "restored": len(snap),
            "applied": result.applied_count,
            "failed": result.failed_count,
        }, ensure_ascii=False))
        return 0

    # snapshot-out：存當前快照（啟用 apply 前的 kill-switch 備份）。
    if args.snapshot_out:
        snap = runner.kill_switch_snapshot()
        with open(args.snapshot_out, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
        print(json.dumps({"action": "snapshot_out", "path": args.snapshot_out, "n": len(snap)}, ensure_ascii=False))
        return 0

    # 正常一個 cycle。
    report = runner.run_cycle(dry_run=not args.apply)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    raise SystemExit(main())
