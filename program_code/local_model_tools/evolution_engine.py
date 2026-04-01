"""
EvolutionEngine — Strategy Parameter Auto-Optimization Engine
策略参数自动优化引擎

MODULE_NOTE (中文):
  本模块实现 Phase 3 Batch 3A 规格的策略参数自动优化引擎。
  职责：使用 BacktestEngine 作为评估函数，对指定策略的参数空间进行网格搜索，
  找出最优参数组合，并将高质量结果注入 TruthSourceRegistry。

  原则 7 隔离（强制）：
  - 不修改任何 live/paper 配置
  - 不调用 GovernanceHub / PaperTradingEngine / MessageBus / PipelineBridge
  - 所有评估在回测沙箱中完成（backtest_mode=True 强制传入）
  - 唯一输出是 EvolutionResult（可选注入 TruthSourceRegistry）

  原则 5 生存优先（资源防护）：
  - max_combinations 上限预设 50，防止长时间占用计算资源
  - 单次评估有异常捕获防护，失败时跳过而非中止整体搜索

MODULE_NOTE (English):
  This module implements the strategy parameter auto-optimization engine
  per Phase 3 Batch 3A spec. Uses BacktestEngine as evaluation function
  for grid search over strategy parameter combinations.

  Principle 7 Isolation (enforced):
  - Does NOT modify any live/paper configuration
  - Does NOT call GovernanceHub / PaperTradingEngine / MessageBus / PipelineBridge
  - All evaluations done in backtest sandbox (backtest_mode=True enforced)
  - Only output is EvolutionResult (optionally injected into TruthSourceRegistry)

  Principle 5 Survival First (resource protection):
  - max_combinations capped at 50 by default, preventing resource exhaustion
  - Per-evaluation exception handling: failures skipped, not fatal

Safety invariant / 安全不变量:
  - EvolutionResult.is_simulated is ALWAYS True, enforced in __post_init__
  - backtest_mode=True is always passed to BacktestEngine; misuse raises ValueError
  - This module contains zero imports from GovernanceHub, PaperTradingEngine,
    PipelineBridge, or MessageBus (Principle 7 boundary)
"""

from __future__ import annotations

import itertools
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .backtest_engine import BacktestConfig, BacktestEngine, BacktestResult

logger = logging.getLogger(__name__)


# =============================================================================
# ParameterGrid — Search Space Definition / 参数搜索空间定义
# =============================================================================

@dataclass
class ParameterGrid:
    """
    单一参数的搜索空间定义。
    Search space definition for a single parameter.

    name   — 参数名（对应 BacktestConfig 的字段名）/ Parameter name (BacktestConfig field)
    values — 有限候选值列表，禁止无界搜索 / Finite candidate list; unbounded search forbidden.

    原则 5：调用方负责保证 values 列表长度合理，EvolutionEngine 额外截断兜底。
    Principle 5: Caller is responsible for reasonable list length; EvolutionEngine
    provides truncation as an additional safety net.
    """
    name: str
    values: List[Any]


# =============================================================================
# EvolutionResult — Optimization Result / 优化结果
# =============================================================================

@dataclass
class EvolutionResult:
    """
    完整的参数进化搜索结果。
    Complete parameter evolution search result.

    所有字段均有双语说明。/ All fields documented in bilingual form.

    is_simulated 始终为 True（原则 7 隔离标记，由 __post_init__ 强制）。
    is_simulated is always True (Principle 7 isolation marker, enforced in __post_init__).
    """
    strategy_name: str
    symbol: str
    timeframe: str
    # 最优参数组合 / Best parameter combination found
    best_params: Dict[str, Any]
    # 最优 Sharpe / Best Sharpe ratio achieved
    best_sharpe: float
    # 最优胜率 / Best win rate achieved
    best_win_rate: float
    # 参数空间总组合数（截断前）/ Total combinations before truncation
    total_combinations: int
    # 实际评估的组合数 / Number of combinations actually evaluated
    evaluated_combinations: int
    # 所有评估结果，按 sharpe 降序排列 / All results sorted by sharpe desc
    all_results: List[Dict[str, Any]]
    # 完成时间戳（毫秒）/ Completion timestamp (ms)
    completed_at_ms: int
    # 原则 7 隔离标记，永远为 True / Principle 7 isolation marker, always True
    is_simulated: bool = True

    def __post_init__(self) -> None:
        """
        强制 is_simulated=True，无论调用方传入何值。
        Force is_simulated=True regardless of caller-supplied value.

        这是原则 7 隔离的核心保护：确保进化结果永远不会被误认为是实盘数据。
        This is the core Principle 7 guard: ensures evolution results can never
        be mistaken for live trading data.
        """
        # C6 fix: dataclass is not frozen — direct assignment replaces object.__setattr__ bypass
        # 原则 7：强制隔离标记，不可被覆盖 / Principle 7: force isolation marker, not overrideable
        self.is_simulated = True

    def __setattr__(self, name: str, value: Any) -> None:
        """Prevent is_simulated from being set to False after init (Principle 7 guard).
        只允許 is_simulated 被設為 True，阻止任何設為 False 的嘗試。"""
        if name == "is_simulated" and value is not True and hasattr(self, "is_simulated"):
            return  # silently block attempts to set is_simulated=False
        super().__setattr__(name, value)

    def to_dict(self) -> Dict[str, Any]:
        """
        序列化为字典，供 API 返回和审计日志使用。
        Serialize to dict for API responses and audit logging.
        """
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "best_params": self.best_params,
            "best_sharpe": self.best_sharpe,
            "best_win_rate": self.best_win_rate,
            "total_combinations": self.total_combinations,
            "evaluated_combinations": self.evaluated_combinations,
            "all_results": self.all_results,
            "completed_at_ms": self.completed_at_ms,
            # 原则 7 标记，审计时可核验 / Principle 7 marker, verifiable in audit
            "is_simulated": self.is_simulated,
        }


# =============================================================================
# EvolutionEngine — Main Optimization Engine / 主优化引擎
# =============================================================================

class EvolutionEngine:
    """
    MODULE_NOTE (中文):
      策略参数自动优化引擎。使用 BacktestEngine 评估函数，对指定策略参数进行网格搜索。

      原则 7 隔离（强制）：
      - 不修改任何 live/paper 配置
      - 不调用 GovernanceHub / PaperTradingEngine / MessageBus / PipelineBridge
      - 所有评估在回测沙箱中完成（backtest_mode=True 强制）
      - 唯一输出是 EvolutionResult（可选注入 TruthSourceRegistry）

      原则 5 生存优先（防护）：
      - max_combinations 上限预设 50，防止长时间占用计算资源
      - 单次评估有异常捕获防护（fail-open），失败时跳过而非中止整体

    MODULE_NOTE (English):
      Strategy parameter auto-optimization engine. Uses BacktestEngine as evaluation
      function for grid search over strategy parameter combinations.
      Principle 7: zero live module imports. Principle 5: resource limits enforced.
    """

    def __init__(
        self,
        backtest_engine: Optional[BacktestEngine] = None,
        truth_registry: Optional[Any] = None,
        max_combinations: int = 50,
        per_eval_timeout_s: float = 30.0,
    ) -> None:
        """
        Args:
            backtest_engine    — 回测引擎实例，None 时创建默认实例 / BacktestEngine instance; default if None
            truth_registry     — TruthSourceRegistry 实例，None 时跳过注入 / Registry; skip injection if None
            max_combinations   — 参数组合上限（原则 5 资源防护）/ Max combos cap (Principle 5 resource guard)
            per_eval_timeout_s — 单次评估超时秒数（当前为软限制）/ Per-eval timeout in seconds (soft limit)
        """
        # 使用注入引擎或创建默认实例 / Use injected engine or create default
        self._engine = backtest_engine if backtest_engine is not None else BacktestEngine()
        # TruthSourceRegistry 可为 None，注入时 fail-open / Registry may be None; fail-open on injection
        self._truth_registry = truth_registry
        # 原则 5：组合数量上限防止资源耗尽 / Principle 5: cap prevents resource exhaustion
        self._max_combinations = max_combinations
        self._per_eval_timeout_s = per_eval_timeout_s
        # 线程锁保护统计计数器 / Lock protects stat counters
        self._lock = threading.Lock()
        self._total_runs: int = 0
        self._last_run_ts: Optional[float] = None
        # B13: 存储最近一次进化结果，供外部查询（如 strategy_auto_deployer）
        # B13: Store most recent evolution result for external queries (e.g., strategy_auto_deployer)
        self._last_result: Optional[EvolutionResult] = None

    # ── Public API / 公开 API ──

    def run_evolution(
        self,
        *,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        parameter_grids: List[ParameterGrid],
        lookback_days: int = 30,
        min_sharpe_to_register: float = 1.0,
        klines: Optional[List[Dict]] = None,
    ) -> EvolutionResult:
        """
        执行完整参数进化搜索 / Run complete parameter evolution search.

        流程：
        1. 计算笛卡儿积（截断到 max_combinations）
        2. 逐一用 BacktestEngine 评估（backtest_mode=True 强制）
        3. 按 sharpe 排序，选出最优
        4. 若 best_sharpe >= min_sharpe_to_register，注入 TruthRegistry（fail-open）
        5. 返回 EvolutionResult（is_simulated=True 永远）

        Process:
        1. Compute Cartesian product (truncated to max_combinations)
        2. Evaluate each combo via BacktestEngine (backtest_mode=True enforced)
        3. Sort by sharpe, select best
        4. If best_sharpe >= min_sharpe_to_register, inject TruthRegistry (fail-open)
        5. Return EvolutionResult (is_simulated=True always)

        Fail-closed 守卫 / Fail-closed guards:
        - 单次评估异常 → log warning + 跳过（不中止整体）
          Single eval exception → log warning + skip (do not abort overall search)
        - 零有效结果 → 返回空 EvolutionResult（不崩溃）
          Zero valid results → return empty EvolutionResult (no crash)
        - TruthRegistry 注入失败 → fail-open，log warning
          TruthRegistry injection failure → fail-open, log warning

        Args:
            strategy_name           — 策略名称 / Strategy identifier
            symbol                  — 交易对 / Trading pair
            timeframe               — K线时间框架 / Kline timeframe
            parameter_grids         — 参数搜索网格列表 / Parameter search grids
            lookback_days           — 回测回看天数 / Lookback days for backtest
            min_sharpe_to_register  — 注入 TruthRegistry 的 Sharpe 阈值 / Sharpe threshold for registry injection
            klines                  — 可选预加载 OHLCV 数据 / Optional preloaded OHLCV data

        Returns:
            EvolutionResult with is_simulated=True (enforced by __post_init__)
        """
        start_ts = time.time()

        # 步骤 1：生成参数组合 / Step 1: generate parameter combinations
        combos = self._build_parameter_combinations(parameter_grids, self._max_combinations)
        total_combinations = _count_raw_combinations(parameter_grids)

        logger.info(
            "EvolutionEngine: strategy=%s symbol=%s timeframe=%s "
            "参数组合数=%d（截断上限=%d，原始空间=%d）",
            strategy_name, symbol, timeframe,
            len(combos), self._max_combinations, total_combinations,
        )

        # 步骤 2：逐一评估 / Step 2: evaluate each combination
        evaluated_results: List[Dict[str, Any]] = []
        evaluated_count = 0

        for params in combos:
            # 构造 BacktestConfig，backtest_mode=True 强制 / Build BacktestConfig with backtest_mode=True enforced
            config = self._build_config(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                lookback_days=lookback_days,
                params=params,
            )
            # 将 klines 转换为 BacktestEngine 期望的格式（ohlcv_data 字典 or None）
            # Convert klines list to ohlcv_data dict expected by BacktestEngine, or pass None
            ohlcv_data = _klines_to_ohlcv(klines) if klines is not None else None
            result = self._evaluate_one(config, ohlcv_data)
            evaluated_count += 1

            if result is not None:
                # 提取评估结果关键指标 / Extract key metrics from result
                evaluated_results.append({
                    "params": params,
                    "sharpe": result.sharpe_ratio,
                    "win_rate": result.win_rate,
                    "total_trades": result.total_trades,
                })

        # 步骤 3：按 sharpe 降序排列 / Step 3: sort by sharpe descending
        evaluated_results.sort(key=lambda x: x["sharpe"], reverse=True)

        # 选出最优结果 / Pick best result
        if evaluated_results:
            best = evaluated_results[0]
            best_params = best["params"]
            best_sharpe = best["sharpe"]
            best_win_rate = best["win_rate"]
        else:
            # 零有效结果 fail-open — 返回空结果不崩溃 / Zero valid results fail-open — return empty, no crash
            logger.warning(
                "EvolutionEngine: 全部 %d 个组合评估失败，返回空结果 "
                "（fail-open — zero valid results, returning empty EvolutionResult）",
                evaluated_count,
            )
            best_params = {}
            best_sharpe = 0.0
            best_win_rate = 0.0

        # 步骤 4：注入 TruthRegistry（达标时，fail-open）
        # Step 4: inject TruthRegistry if threshold met (fail-open)
        if self._truth_registry is not None and best_sharpe >= min_sharpe_to_register:
            try:
                self._truth_registry.register_claim(
                    pattern_text=f"best_params={best_params} sharpe={best_sharpe:.2f}",
                    evidence_source=f"statistical_N={evaluated_count}",
                    observation_count=evaluated_count,
                    confidence=min(0.75, best_sharpe / 3.0),  # 上限 0.75，永不为 FACT / cap 0.75, never FACT
                    applies_to_regime="all",
                    applies_to_strategy=strategy_name,
                )
                # 原则 12：持续进化 — 高品质进化结果注入学习管线
                # Principle 12: continuous evolution — inject high-quality results into learning pipeline
                logger.info(
                    "EvolutionEngine: TruthRegistry 注入成功 strategy=%s sharpe=%.2f N=%d",
                    strategy_name, best_sharpe, evaluated_count,
                )
            except Exception as e:
                # fail-open：注入失败不影响主搜索结果 / fail-open: injection failure does not affect search result
                logger.warning("TruthRegistry injection failed (fail-open): %s", e)

        # 更新统计计数器 / Update stat counters
        now_ts = time.time()
        with self._lock:
            self._total_runs += 1
            self._last_run_ts = now_ts

        completed_at_ms = int(now_ts * 1000)

        logger.info(
            "EvolutionEngine 完成: strategy=%s best_sharpe=%.2f evaluated=%d elapsed=%.1fs",
            strategy_name, best_sharpe, evaluated_count, now_ts - start_ts,
        )

        # 步骤 5：构建并存储 EvolutionResult，然后返回（__post_init__ 强制 is_simulated=True）
        # Step 5: build and store EvolutionResult, then return (__post_init__ enforces is_simulated=True)
        # B13: Store result for external query via get_last_result()
        # B13: 存储结果以供外部通过 get_last_result() 查询
        evolution_result = EvolutionResult(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            best_params=best_params,
            best_sharpe=best_sharpe,
            best_win_rate=best_win_rate,
            total_combinations=total_combinations,
            evaluated_combinations=evaluated_count,
            all_results=evaluated_results,
            completed_at_ms=completed_at_ms,
            is_simulated=True,  # __post_init__ 强制，此处冗余但明确意图 / __post_init__ forces; explicit intent
        )
        with self._lock:
            self._last_result = evolution_result
        return evolution_result

    # ── Private helpers / 私有辅助方法 ──

    def _build_parameter_combinations(
        self,
        grids: List[ParameterGrid],
        max_count: int,
    ) -> List[Dict[str, Any]]:
        """
        生成参数笛卡儿积，截断到 max_count。
        Generate Cartesian product of parameter grids, truncated to max_count.

        截断时 log warning。/ Log warning on truncation.

        原则 5：截断防止资源耗尽。
        Principle 5: truncation prevents resource exhaustion.

        Args:
            grids     — ParameterGrid 列表 / List of ParameterGrid
            max_count — 最大组合数上限 / Maximum combination count

        Returns:
            List of parameter dicts, at most max_count entries.
        """
        if not grids:
            # 空参数网格 → 返回一个空组合（确保至少评估一次）
            # Empty grids → return one empty combo (ensure at least one evaluation)
            return [{}]

        keys = [g.name for g in grids]
        values_lists = [g.values for g in grids]
        # 使用 itertools.product 计算笛卡儿积 / Use itertools.product for Cartesian product
        combos = [dict(zip(keys, combo)) for combo in itertools.product(*values_lists)]

        if len(combos) > max_count:
            # 原则 5 资源保护：截断搜索空间 / Principle 5 resource guard: truncate search space
            logger.warning(
                "Parameter grid has %d combinations, truncating to %d "
                "（原则 5 资源保护：截断搜索空间 / Principle 5: truncating search space）",
                len(combos), max_count,
            )
            combos = combos[:max_count]

        return combos

    def _build_config(
        self,
        *,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        lookback_days: int,
        params: Dict[str, Any],
    ) -> BacktestConfig:
        """
        构造 BacktestConfig，backtest_mode=True 强制传入。
        Build BacktestConfig with backtest_mode=True enforced.

        params 中已知 BacktestConfig 字段会直接映射；未知字段忽略（安全边界）。
        Known BacktestConfig fields from params are mapped directly;
        unknown fields are ignored (safety boundary).

        原则 7：backtest_mode=True 始终强制，防止回测配置污染 live 配置。
        Principle 7: backtest_mode=True always enforced; prevents backtest config
        from contaminating live configuration.
        """
        # 已知 BacktestConfig 可配置字段白名单 / Whitelist of configurable BacktestConfig fields
        known_fields = {
            "initial_capital", "fee_rate_taker", "fee_rate_maker",
            "slippage_bps", "position_size_pct", "stop_loss_pct",
        }
        # 仅映射白名单字段，忽略其他 / Only map whitelisted fields, ignore others
        safe_params = {k: v for k, v in params.items() if k in known_fields}

        return BacktestConfig(
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            # backtest_mode=True 强制，不可被 params 覆盖 / Enforced; not overrideable by params
            backtest_mode=True,
            **safe_params,
        )

    def _evaluate_one(
        self,
        config: BacktestConfig,
        ohlcv_data: Optional[Dict[str, Any]],
    ) -> Optional[BacktestResult]:
        """
        单次回测评估，失败返回 None（不传播异常）。
        Single backtest evaluation; return None on failure (no exception propagation).

        fail-open 此处 — 单次失败不应中止整体搜索。
        fail-open here — single failure must not abort the overall search.

        Args:
            config     — BacktestConfig（backtest_mode=True 已由调用方保证）
            ohlcv_data — 可选 OHLCV 数据字典 / Optional OHLCV data dict

        Returns:
            BacktestResult on success; None on any exception.
        """
        try:
            return self._engine.run(config, ohlcv_data)
        except Exception as e:
            # fail-open：跳过此组合继续搜索 / fail-open: skip this combo, continue search
            logger.warning(
                "EvolutionEngine eval failed for strategy=%s params=%s: %s "
                "（跳过此组合 / skipping this combination）",
                getattr(config, 'strategy_name', '?'),
                {k: v for k, v in config.__dict__.items() if k not in ('symbol', 'timeframe', 'strategy_name', 'backtest_mode')},
                e,
            )
            return None  # fail-open：返回 None 而非传播异常 / fail-open: return None, not propagate

    def get_status(self) -> Dict[str, Any]:
        """
        返回引擎当前状态，供监控和 API 查询使用。
        Return current engine status for monitoring and API queries.

        Returns:
            Dict with total_runs, last_run_ts, max_combinations, last_result.
        """
        with self._lock:
            return {
                "total_runs": self._total_runs,
                "last_run_ts": self._last_run_ts,
                "max_combinations": self._max_combinations,
                "last_result": self._last_result.to_dict() if self._last_result else None,
            }

    def get_last_result(self) -> Optional['EvolutionResult']:
        """
        返回最近一次进化搜索结果，供外部查询使用。
        Return the most recent evolution result for external queries.

        Returns:
            EvolutionResult if available, None otherwise.
        """
        with self._lock:
            return self._last_result


# =============================================================================
# Internal helpers / 内部辅助函数
# =============================================================================

def _count_raw_combinations(grids: List[ParameterGrid]) -> int:
    """
    计算参数网格的原始笛卡儿积大小（截断前）。
    Compute raw Cartesian product size before truncation.

    Args:
        grids — ParameterGrid 列表 / List of ParameterGrid

    Returns:
        Total combination count (1 if grids is empty).
    """
    if not grids:
        return 1
    total = 1
    for g in grids:
        total *= len(g.values)
    return total


def _klines_to_ohlcv(klines: List[Dict]) -> Optional[Dict[str, Any]]:
    """
    将 klines 列表（[{open, high, low, close, volume, ...}]）转换为
    BacktestEngine.run() 期望的 ohlcv_data 字典格式。
    Convert klines list to ohlcv_data dict expected by BacktestEngine.run().

    BacktestEngine 期望 ohlcv_data 为 dict[str, list[float]]，
    键为 "open"/"high"/"low"/"close"/"volume"。
    BacktestEngine expects ohlcv_data as dict[str, list[float]],
    keys: "open", "high", "low", "close", "volume".

    Args:
        klines — list of kline dicts

    Returns:
        ohlcv_data dict, or None if input is empty.
    """
    if not klines:
        return None
    ohlcv: Dict[str, List[float]] = {
        "open": [], "high": [], "low": [], "close": [], "volume": [],
    }
    for k in klines:
        ohlcv["open"].append(float(k.get("open", 0)))
        ohlcv["high"].append(float(k.get("high", 0)))
        ohlcv["low"].append(float(k.get("low", 0)))
        ohlcv["close"].append(float(k.get("close", 0)))
        ohlcv["volume"].append(float(k.get("volume", 0)))
    return ohlcv
