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
    - main()：argparse CLI（cron/手動），--apply 才真發 IPC，--kill-switch 一鍵停。

  依賴：reward_source / ipc_lever / demo_maker_arm（同 package）+
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
import os
import random
import time
import tomllib
from dataclasses import dataclass, field
from typing import Optional

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

logger = logging.getLogger(__name__)

# engine_mode 硬鎖唯一允許值（demo 沙盒）。
_DEMO_ENGINE_MODE = "demo"

# config 預設路徑：srv/settings/adaptive_demo_profit.toml。
# 從本檔（program_code/ml_training/adaptive_demo_profit_engine/runner.py）回推三層到 srv。
_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "settings", "adaptive_demo_profit.toml"
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

    def to_dict(self) -> dict:
        return {
            "engine_mode": self.engine_mode,
            "dry_run": self.dry_run,
            "n_rewards_ingested": self.n_rewards_ingested,
            "all_regimes_flat": self.all_regimes_flat,
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
        dsn: Optional[str] = None,
    ):
        self.runner_cfg = runner_cfg or AdpeRunnerConfig()
        self.alloc_cfg = alloc_cfg or AllocatorConfig()
        self.allocator = allocator or RegimeBanditAllocator(self.alloc_cfg)
        self.lever = lever or StrategyLever()
        # rewards_fn：注入點（測試 / 替代源）；預設用 reward_source.fetch_demo_arm_rewards。
        self._rewards_fn = rewards_fn or self._default_rewards_fn
        self._dsn = dsn
        self._rng = random.Random(self.runner_cfg.rng_seed)

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
        self, by_regime: dict[str, list[str]]
    ) -> tuple[dict[str, bool], list[CandidateDecision], bool]:
        """對每個 regime allocate，把贏家映成 active、負 EV 映成 dormant。

        映射規則（誠實鐵則）：
          - 對每 regime 跑 allocator.allocate → 權重 dict（含 flat）。
          - 某 (strategy, regime) arm 權重 > 0 且非 flat → 該 strategy 標 active（贏家）。
          - 全 regime 皆 flat（全負 EV）→ all_regimes_flat=True，desired 全 False（歸零）。
        active 是「任一 regime 為贏家即 active」的 union（strategy 級 lever）。
        """
        decisions: list[CandidateDecision] = []
        active_strategies: set[str] = set()
        seen_strategies: set[str] = set()
        any_non_flat_winner = False

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

        # desired：所有見過的策略，贏家→True、其餘→False（負 EV 歸零）。
        desired = {s: (s in active_strategies) for s in seen_strategies}
        all_flat = (not any_non_flat_winner) and bool(seen_strategies)
        return desired, decisions, all_flat

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

        # 3) 候選列舉 + 4) 逐 regime allocate → desired active。
        by_regime = self._discover_candidate_arms(ingested_arm_ids)
        desired, decisions, all_flat = self.build_desired_active(by_regime)

        # 5) 經 lever 落到 demo 引擎（冪等 diff；dry-run 不發 IPC）。
        apply_result: ApplyResult = self.lever.apply_desired(desired, dry_run=effective_dry)

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
        )
        logger.info(
            "ADPE cycle done: dry_run=%s rewards=%d active=%d all_flat=%s",
            effective_dry,
            len(rewards),
            sum(1 for v in desired.values() if v),
            all_flat,
        )
        return report

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
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    runner_cfg, alloc_cfg = load_runner_config(args.config)
    if args.seed is not None:
        runner_cfg.rng_seed = args.seed
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
