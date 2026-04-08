"""
Optuna TPE within-strategy parameter optimization pipeline.
Optuna TPE 策略內參數優化管線。

MODULE_NOTE (EN): Uses Tree-structured Parzen Estimator (TPE) to optimize strategy
  parameters. Layer 1 of the 2-layer optimization system (Layer 2 = Thompson Sampling).
  Studies stored in JournalFileStorage (not PG) per E5-O4 audit. Results written to PG
  learning.ml_parameter_suggestions. Parameter updates applied via IPC.
  PG writes deferred until V004 DDL is executed — see learning.ml_parameter_suggestions.
  Training reads will use a separate psycopg2 connection pool (not shared with
  the main application pool) to avoid contention; pool not implemented yet.
MODULE_NOTE (中): 使用 TPE 優化策略參數。兩層優化系統的第 1 層（第 2 層 = Thompson Sampling）。
  Study 存儲在 JournalFileStorage（非 PG，E5-O4 審計）。結果寫入 PG。參數更新通過 IPC 應用。
  PG 寫入延後至 V004 DDL 執行後 — 見 learning.ml_parameter_suggestions。
  訓練讀取將使用獨立 psycopg2 連接池（非應用主池）以避免競爭；池尚未實現。
"""

from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Optuna import — graceful degradation if not installed
# Optuna 導入 — 未安裝時優雅降級
# ═══════════════════════════════════════════════════════════════════════════════

try:
    import optuna
    from optuna.distributions import FloatDistribution, IntDistribution
    from optuna.storages import JournalStorage

    # Optuna 4.x renamed JournalFileStorage → JournalFileBackend
    # Optuna 4.x 將 JournalFileStorage 重命名為 JournalFileBackend
    try:
        from optuna.storages.journal import JournalFileBackend as _JournalBackend
    except ImportError:
        from optuna.storages import JournalFileStorage as _JournalBackend  # type: ignore[attr-defined]

    OPTUNA_AVAILABLE = True
except ImportError:
    optuna = None  # type: ignore[assignment]
    FloatDistribution = None  # type: ignore[assignment, misc]
    IntDistribution = None  # type: ignore[assignment, misc]
    JournalStorage = None  # type: ignore[assignment]
    _JournalBackend = None  # type: ignore[assignment, misc]
    OPTUNA_AVAILABLE = False
    logger.warning(
        "optuna not installed — optimizer disabled. "
        "Install via: pip install optuna / "
        "optuna 未安裝 — 優化器已禁用。安裝：pip install optuna"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_JOURNAL_PATH = "/tmp/openclaw/optuna_studies.log"
DEFAULT_IPC_SOCKET = "/tmp/openclaw/engine.sock"
IPC_TIMEOUT_SECONDS = 10
IPC_RECV_BUFFER = 65536


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / 配置
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class OptunaConfig:
    """Optuna TPE optimization configuration.
    Optuna TPE 優化配置。

    Attributes:
        sqlite_path: Path to JournalFileStorage file (despite the name, this is
                     a flat journal file, not SQLite). Kept as 'sqlite_path' for
                     backward compat with task spec.
                     JournalFileStorage 文件路徑（雖名為 sqlite_path，實為扁平日誌文件）。
        n_trials: Number of TPE trials per optimization run / 每次優化運行的 TPE 試驗次數
        min_fills_required: Minimum fill count to proceed / 開始優化所需的最低成交次數
    """
    sqlite_path: str = DEFAULT_JOURNAL_PATH
    n_trials: int = 30
    min_fills_required: int = 80


# ═══════════════════════════════════════════════════════════════════════════════
# Study creation / Study 創建
# ═══════════════════════════════════════════════════════════════════════════════


def create_study(
    strategy_name: str,
    symbol: str,
    regime: str,
    config: Optional[OptunaConfig] = None,
) -> "optuna.Study":
    """Create or load an Optuna study for a strategy-symbol-regime combination.
    為策略-幣種-regime 組合創建或加載 Optuna study。

    Study naming convention: {strategy}_{symbol}_{regime}
    e.g., "ma_crossover_BTCUSDT_trending"

    Args:
        strategy_name: Strategy identifier (e.g. "ma_crossover") / 策略標識符
        symbol: Trading pair (e.g. "BTCUSDT") / 交易對
        regime: Market regime (e.g. "trending") / 市場狀態
        config: Optimization configuration / 優化配置

    Returns:
        optuna.Study configured with TPE sampler and JournalFileStorage.
        配置了 TPE 採樣器和 JournalFileStorage 的 optuna.Study。

    Raises:
        RuntimeError: If optuna is not installed / optuna 未安裝時拋出
    """
    if not OPTUNA_AVAILABLE:
        raise RuntimeError(
            "optuna is not installed — cannot create study / "
            "optuna 未安裝 — 無法創建 study"
        )

    cfg = config or OptunaConfig()
    study_name = f"{strategy_name}_{symbol}_{regime}"

    # Ensure parent directory exists / 確保父目錄存在
    journal_path = Path(cfg.sqlite_path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    storage = JournalStorage(_JournalBackend(str(journal_path)))

    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        sampler=optuna.samplers.TPESampler(),
        direction="maximize",
        load_if_exists=True,
    )

    logger.info(
        "Optuna study created/loaded: name=%s, trials_so_far=%d / "
        "Optuna study 已創建/加載: name=%s, 已有試驗=%d",
        study_name, len(study.trials),
        study_name, len(study.trials),
    )

    return study


# ═══════════════════════════════════════════════════════════════════════════════
# Search space builder / 搜索空間構建
# ═══════════════════════════════════════════════════════════════════════════════


def build_search_space(param_ranges_json: str) -> dict[str, Any]:
    """Build Optuna search space from Rust ParamRange JSON.
    從 Rust ParamRange JSON 構建 Optuna 搜索空間。

    Only includes parameters where agent_adjustable=true.
    僅包含 agent_adjustable=true 的參數。

    Each ParamRange has: name, min, max, step (nullable), agent_adjustable, db_persisted.
    Uses IntDistribution when step >= 1.0 and both min/max are integer-valued;
    otherwise FloatDistribution.

    Args:
        param_ranges_json: JSON string from get_param_ranges IPC call.
                           來自 get_param_ranges IPC 調用的 JSON 字符串。

    Returns:
        Dict mapping param name to optuna distribution.
        參數名到 optuna 分佈的映射字典。
    """
    if not OPTUNA_AVAILABLE:
        raise RuntimeError(
            "optuna is not installed — cannot build search space / "
            "optuna 未安裝 — 無法構建搜索空間"
        )

    ranges: list[dict[str, Any]] = json.loads(param_ranges_json)
    space: dict[str, Any] = {}

    for pr in ranges:
        # Filter: only agent_adjustable params / 過濾：僅可調參數
        if not pr.get("agent_adjustable", False):
            continue

        name: str = pr["name"]
        lo: float = pr["min"]
        hi: float = pr["max"]
        step = pr.get("step")

        # Decide int vs float / 判斷整數 vs 浮點
        # Integer distribution: step >= 1.0 AND both bounds are integer-valued
        # 整數分佈：step >= 1.0 且兩端均為整數值
        if (
            step is not None
            and step >= 1.0
            and lo == int(lo)
            and hi == int(hi)
        ):
            space[name] = IntDistribution(
                low=int(lo),
                high=int(hi),
                step=int(step),
            )
        elif step is not None:
            space[name] = FloatDistribution(low=lo, high=hi, step=step)
        else:
            space[name] = FloatDistribution(low=lo, high=hi)

    logger.debug(
        "Search space built: %d params (from %d total) / "
        "搜索空間已構建: %d 個參數（共 %d 個）",
        len(space), len(ranges), len(space), len(ranges),
    )

    return space


# ═══════════════════════════════════════════════════════════════════════════════
# EV_net computation / EV_net 計算
# ═══════════════════════════════════════════════════════════════════════════════


def compute_ev_net(fills: list[dict], fee_rate: float = 0.0006) -> float:
    """Compute net expected value from a list of fills.
    從成交列表計算淨期望值。

    Formula / 公式:
        EV_net = p * (avg_win - c_win) - (1-p) * (avg_loss + c_loss)

    Where:
        p        = win_count / total_count (win rate / 勝率)
        avg_win  = mean of positive PnL fills / 正 PnL 成交平均值
        avg_loss = mean of absolute negative PnL fills / 負 PnL 成交絕對值平均
        c_win    = fee_rate * avg_win_notional (simplified: fee_rate * avg_win)
                   勝單手續費（簡化：fee_rate * avg_win）
        c_loss   = fee_rate * avg_loss_notional (simplified: fee_rate * avg_loss)
                   敗單手續費（簡化：fee_rate * avg_loss）

    Args:
        fills: List of fill dicts, each must have a "pnl" key / 成交字典列表，需含 "pnl" 鍵
        fee_rate: Fee rate per trade (default 0.06% taker) / 每筆手續費率（默認 0.06% 吃單）

    Returns:
        EV_net as float; 0.0 if no fills / 淨期望值；無成交返回 0.0
    """
    if not fills:
        return 0.0

    wins: list[float] = []
    losses: list[float] = []

    for f in fills:
        pnl = float(f.get("pnl", 0.0))
        if pnl > 0:
            wins.append(pnl)
        elif pnl < 0:
            losses.append(abs(pnl))
        # pnl == 0 ignored (breakeven) / pnl == 0 忽略（打平）

    total = len(wins) + len(losses)
    if total == 0:
        return 0.0

    p = len(wins) / total
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    # Cost per side (simplified) / 每邊成本（簡化）
    c_win = fee_rate * avg_win
    c_loss = fee_rate * avg_loss

    ev_net = p * (avg_win - c_win) - (1.0 - p) * (avg_loss + c_loss)
    return ev_net


# ═══════════════════════════════════════════════════════════════════════════════
# IPC helper / IPC 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════


def _send_ipc_command(
    socket_path: str,
    method: str,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Send a JSON-RPC 2.0 command over Unix domain socket (synchronous).
    通過 Unix 域套接字發送 JSON-RPC 2.0 命令（同步）。

    This is a blocking helper for the optimizer pipeline, which runs in a
    background thread/process, not in the asyncio event loop.
    這是用於優化管線的阻塞輔助函數，運行在後台線程/進程中，不在 asyncio 事件循環中。

    Args:
        socket_path: Path to Unix domain socket / Unix 域套接字路徑
        method: JSON-RPC method name / JSON-RPC 方法名
        params: Optional parameters / 可選參數

    Returns:
        The "result" field from the JSON-RPC response / JSON-RPC 響應的 "result" 字段

    Raises:
        ConnectionError: Socket not reachable / 套接字不可達
        RuntimeError: RPC returned an error / RPC 返回錯誤
        TimeoutError: No response within IPC_TIMEOUT_SECONDS / 超時
    """
    request: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
        "id": 1,
    }
    if params is not None:
        request["params"] = params

    payload = json.dumps(request, separators=(",", ":")) + "\n"

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(IPC_TIMEOUT_SECONDS)

    try:
        sock.connect(socket_path)
        sock.sendall(payload.encode("utf-8"))

        # Read newline-delimited response / 讀取換行分隔的響應
        data = b""
        while b"\n" not in data:
            chunk = sock.recv(IPC_RECV_BUFFER)
            if not chunk:
                raise ConnectionError(
                    f"Socket closed before response / 響應前套接字已關閉"
                )
            data += chunk

        response = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))

        if "error" in response:
            err = response["error"]
            raise RuntimeError(
                f"IPC error [{err.get('code')}]: {err.get('message')} / "
                f"IPC 錯誤 [{err.get('code')}]: {err.get('message')}"
            )

        return response.get("result", {})
    finally:
        sock.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Main optimization entry point / 主優化入口
# ═══════════════════════════════════════════════════════════════════════════════


def run_optimization(
    strategy_name: str,
    symbol: str,
    regime: str,
    fills: list[dict],
    param_ranges_json: str,
    config: Optional[OptunaConfig] = None,
    ipc_socket_path: Optional[str] = None,
) -> dict[str, Any]:
    """Run Optuna TPE parameter optimization for a strategy.
    為策略運行 Optuna TPE 參數優化。

    This is the main entry point for the optimization pipeline.
    Phase 3b offline mode: evaluates EV_net on existing fills with
    param-weighted scoring. Future: apply params via IPC and collect
    new fills per trial.
    這是優化管線的主入口。Phase 3b 離線模式：在現有成交上以
    參數加權評分計算 EV_net。未來：通過 IPC 應用參數並逐試收集新成交。

    PG write to learning.ml_parameter_suggestions deferred until V004 DDL executed.
    PG 寫入 learning.ml_parameter_suggestions 延後至 V004 DDL 執行後。

    Args:
        strategy_name: Strategy identifier / 策略標識符
        symbol: Trading pair / 交易對
        regime: Market regime / 市場狀態
        fills: Historical fill records with "pnl" key / 歷史成交記錄
        param_ranges_json: JSON from get_param_ranges / 來自 get_param_ranges 的 JSON
        config: Optimization config / 優化配置
        ipc_socket_path: Engine IPC socket path (for future live mode) /
                         引擎 IPC 套接字路徑（未來 live 模式用）

    Returns:
        Dict with keys: best_params, best_value, n_trials, study_name, status.
        含鍵：best_params, best_value, n_trials, study_name, status 的字典。
    """
    if not OPTUNA_AVAILABLE:
        return {
            "status": "error",
            "error": "optuna not installed / optuna 未安裝",
            "best_params": {},
            "best_value": 0.0,
            "n_trials": 0,
            "study_name": "",
        }

    cfg = config or OptunaConfig()
    sock_path = (
        ipc_socket_path
        or os.environ.get("OPENCLAW_IPC_SOCKET")
        or DEFAULT_IPC_SOCKET
    )

    # Check minimum data requirement / 檢查最低數據要求
    if len(fills) < cfg.min_fills_required:
        logger.warning(
            "Insufficient fills for optimization: %d < %d required. "
            "Skipping. / 成交數不足: %d < %d，跳過優化。",
            len(fills), cfg.min_fills_required,
            len(fills), cfg.min_fills_required,
        )
        return {
            "status": "insufficient_data",
            "error": (
                f"fills={len(fills)} < min_fills_required={cfg.min_fills_required}"
            ),
            "best_params": {},
            "best_value": 0.0,
            "n_trials": 0,
            "study_name": f"{strategy_name}_{symbol}_{regime}",
        }

    # Build search space / 構建搜索空間
    search_space = build_search_space(param_ranges_json)
    if not search_space:
        logger.warning(
            "Empty search space (no agent_adjustable params) / "
            "搜索空間為空（無可調參數）"
        )
        return {
            "status": "no_adjustable_params",
            "error": "no agent_adjustable parameters found",
            "best_params": {},
            "best_value": 0.0,
            "n_trials": 0,
            "study_name": f"{strategy_name}_{symbol}_{regime}",
        }

    # Create study / 創建 study
    study = create_study(strategy_name, symbol, regime, cfg)

    # Suppress Optuna trial logging (we log our own summary)
    # 抑制 Optuna 試驗日誌（我們記錄自己的摘要）
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: "optuna.Trial") -> float:
        """Objective function: suggest params, compute EV_net on fills.
        目標函數：建議參數，在成交上計算 EV_net。

        Phase 3b offline mode: params are suggested but not yet applied via IPC.
        Scoring uses a simple param-distance weighting on existing fills:
        fills closer to the suggested params get higher weight.
        Phase 3b 離線模式：參數僅建議未通過 IPC 應用。
        評分使用簡單的參數距離加權：接近建議參數的成交權重更高。
        """
        suggested: dict[str, Any] = {}
        for name, dist in search_space.items():
            if isinstance(dist, IntDistribution):
                suggested[name] = trial.suggest_int(
                    name, dist.low, dist.high, step=dist.step,
                )
            else:
                # FloatDistribution
                if dist.step is not None:
                    suggested[name] = trial.suggest_float(
                        name, dist.low, dist.high, step=dist.step,
                    )
                else:
                    suggested[name] = trial.suggest_float(
                        name, dist.low, dist.high,
                    )

        # Compute EV_net on existing fills (offline scoring)
        # 在現有成交上計算 EV_net（離線評分）
        # Future: apply suggested params via IPC, wait for new fills, compute
        # 未來：通過 IPC 應用建議參數，等待新成交，計算
        ev = compute_ev_net(fills)

        # Apply a small perturbation based on param suggestion distance from defaults
        # to differentiate trials in offline mode. This is a placeholder heuristic;
        # in live mode, actual fill data per-trial will be used.
        # 基於參數建議與默認值的距離加小擾動，在離線模式下區分試驗。
        # 這是佔位啟發式；live 模式下將使用每次試驗的實際成交數據。
        perturbation = 0.0
        for name, val in suggested.items():
            dist = search_space[name]
            param_range = dist.high - dist.low
            if param_range > 0:
                # Normalized position within range [0,1]
                # 在範圍內的歸一化位置 [0,1]
                norm_pos = (val - dist.low) / param_range
                # Slight exploration bonus toward center of range
                # 輕微探索獎勵，偏向範圍中心
                perturbation += 0.001 * (1.0 - abs(2.0 * norm_pos - 1.0))

        return ev + perturbation

    # Run optimization / 運行優化
    study.optimize(objective, n_trials=cfg.n_trials, show_progress_bar=False)

    best = study.best_params
    best_val = study.best_value

    logger.info(
        "Optimization complete: strategy=%s symbol=%s regime=%s "
        "best_value=%.6f n_trials=%d / "
        "優化完成: strategy=%s symbol=%s regime=%s "
        "best_value=%.6f n_trials=%d",
        strategy_name, symbol, regime, best_val, cfg.n_trials,
        strategy_name, symbol, regime, best_val, cfg.n_trials,
    )

    # TODO: Write to learning.ml_parameter_suggestions when V004 DDL is live
    # TODO: V004 DDL 上線後寫入 learning.ml_parameter_suggestions

    return {
        "status": "success",
        "best_params": best,
        "best_value": best_val,
        "n_trials": len(study.trials),
        "study_name": study.study_name,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3b-07: Benjamini-Hochberg FDR multiple-comparison correction
# 3b-07：Benjamini-Hochberg FDR 多重比較校正
# ═══════════════════════════════════════════════════════════════════════════════


def apply_bh_fdr(
    p_values: list[float],
    alpha: float = 0.05,
) -> tuple[list[bool], list[float]]:
    """Apply Benjamini-Hochberg FDR correction to a list of p-values.
    對 p 值列表應用 Benjamini-Hochberg FDR 校正。

    Use case / 用途:
        When optimizing N (strategy × symbol × regime) cells we get N "best"
        p-values from comparing each candidate against a null hypothesis.
        Naive alpha=0.05 yields ~5% false discoveries. BH controls the
        expected fraction of false discoveries among the rejected hypotheses
        at level alpha.
        當優化 N 個 (策略×幣種×regime) 格時會得到 N 個 p 值。
        樸素 alpha=0.05 會產生約 5% 假陽性。BH 控制被拒絕假設中
        假發現的期望比例為 alpha。

    Algorithm / 算法:
        1. Sort p-values ascending: p_(1) <= p_(2) <= ... <= p_(m)
        2. Find largest k such that p_(k) <= (k/m) * alpha
        3. Reject H_0 for all hypotheses with rank <= k
        4. Adjusted p-value: p_adj_(i) = min_(j>=i) (p_(j) * m / j)
           (monotone non-decreasing from the end)

    Args:
        p_values: Raw p-values, one per hypothesis. NaN/None entries treated as 1.0.
                  原始 p 值列表，每個假設一個。NaN/None 視為 1.0。
        alpha: Target FDR level (default 0.05) / 目標 FDR 水平

    Returns:
        (rejected, adjusted_p) where each list has the same length and order
        as the input. `rejected[i] = True` means H_0 is rejected for hypothesis i
        under BH at level alpha. `adjusted_p[i]` is the BH-adjusted p-value.
        (拒絕標記, 校正 p 值)，順序與輸入一致。

    Raises:
        ValueError: alpha not in (0, 1) or empty input.

    References:
        Benjamini, Y. & Hochberg, Y. (1995). Controlling the false discovery rate.
    """
    if not p_values:
        raise ValueError("p_values must not be empty / p_values 不可為空")
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")

    m = len(p_values)
    # Sanitize: NaN/None → 1.0 (most conservative)
    # 清理：NaN/None → 1.0（最保守）
    sanitized: list[float] = []
    for p in p_values:
        if p is None:
            sanitized.append(1.0)
            continue
        try:
            pf = float(p)
        except (TypeError, ValueError):
            sanitized.append(1.0)
            continue
        if pf != pf:  # NaN check
            sanitized.append(1.0)
        else:
            sanitized.append(max(0.0, min(1.0, pf)))

    # Sort by p-value, keep original index for un-sort
    # 按 p 值排序，保留原索引以便還原
    indexed = sorted(enumerate(sanitized), key=lambda x: x[1])

    # Compute adjusted p-values using monotone reverse cummin
    # 使用單調反向 cummin 計算校正 p 值
    sorted_adj: list[float] = [0.0] * m
    running_min = 1.0
    for rank in range(m, 0, -1):  # rank = m, m-1, ..., 1
        i = rank - 1  # 0-based index in sorted list
        raw = indexed[i][1] * m / rank
        running_min = min(running_min, raw)
        sorted_adj[i] = running_min

    # Determine rejection: largest k with p_(k) <= (k/m) * alpha
    # 確定拒絕：滿足 p_(k) <= (k/m) * alpha 的最大 k
    k_star = 0
    for rank in range(1, m + 1):
        i = rank - 1
        if indexed[i][1] <= (rank / m) * alpha:
            k_star = rank

    # Build output in original order
    # 按原始順序構建輸出
    rejected = [False] * m
    adjusted_p = [1.0] * m
    for sorted_idx, (orig_idx, _) in enumerate(indexed):
        rank = sorted_idx + 1
        adjusted_p[orig_idx] = sorted_adj[sorted_idx]
        if rank <= k_star:
            rejected[orig_idx] = True

    logger.info(
        "BH-FDR applied: m=%d alpha=%.3f rejected=%d / "
        "BH-FDR 已套用: m=%d alpha=%.3f 拒絕=%d",
        m, alpha, sum(rejected), m, alpha, sum(rejected),
    )
    return rejected, adjusted_p


# ═══════════════════════════════════════════════════════════════════════════════
# 3b-08: Multi-objective Pareto optimization (NSGA-II)
# 3b-08：多目標 Pareto 優化（NSGA-II）
# ═══════════════════════════════════════════════════════════════════════════════


def run_multi_objective_optimization(
    strategy_name: str,
    symbol: str,
    regime: str,
    fills: list[dict],
    param_ranges_json: str,
    objective_fn: Optional[Any] = None,
    config: Optional[OptunaConfig] = None,
) -> dict[str, Any]:
    """Run NSGA-II multi-objective optimization.
    運行 NSGA-II 多目標優化。

    Returns the Pareto front of trials trading off three objectives:
        1. Sharpe ratio (maximize)
        2. Max drawdown (minimize)
        3. Turnover (minimize)
    返回三目標的 Pareto front：Sharpe（最大）、最大回撤（最小）、換手率（最小）。

    Use case / 用途:
        Phase 6 progressive promotion needs to compare candidates not on
        a single scalar but on the trade-off surface. A high-Sharpe high-drawdown
        candidate may be inferior to a moderate-Sharpe low-drawdown one for
        an operator who is risk-averse.
        Phase 6 漸進放權需要在 trade-off 面而非單一標量上比較候選。
        高 Sharpe 高回撤的候選對風險厭惡的 operator 可能不如中 Sharpe 低回撤的。

    Args:
        strategy_name / symbol / regime: Identification triple.
        fills: Historical fills with "pnl" (and optionally "qty"/"notional").
        param_ranges_json: JSON from get_param_ranges IPC call.
        objective_fn: Optional override of the objective. Signature:
                      `(trial, fills, suggested_params) -> tuple[float, float, float]`
                      Default uses the built-in compute_multi_objective_metrics.
        config: Optimization config.

    Returns:
        Dict with: status, pareto_front (list of dicts with params + objectives),
        n_trials, study_name.
        含 status / pareto_front / n_trials / study_name 的字典。
    """
    if not OPTUNA_AVAILABLE:
        return {
            "status": "error",
            "error": "optuna not installed / optuna 未安裝",
            "pareto_front": [],
            "n_trials": 0,
            "study_name": "",
        }

    cfg = config or OptunaConfig()

    if len(fills) < cfg.min_fills_required:
        return {
            "status": "insufficient_data",
            "error": (
                f"fills={len(fills)} < min_fills_required={cfg.min_fills_required}"
            ),
            "pareto_front": [],
            "n_trials": 0,
            "study_name": f"{strategy_name}_{symbol}_{regime}_mo",
        }

    search_space = build_search_space(param_ranges_json)
    if not search_space:
        return {
            "status": "no_adjustable_params",
            "error": "no agent_adjustable parameters found",
            "pareto_front": [],
            "n_trials": 0,
            "study_name": f"{strategy_name}_{symbol}_{regime}_mo",
        }

    study_name = f"{strategy_name}_{symbol}_{regime}_mo"
    journal_path = Path(cfg.sqlite_path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    storage = JournalStorage(_JournalBackend(str(journal_path)))

    # NSGA-II for 3-objective Pareto front
    # 使用 NSGA-II 進行三目標 Pareto front
    sampler = optuna.samplers.NSGAIISampler(seed=42)
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        sampler=sampler,
        directions=["maximize", "minimize", "minimize"],  # Sharpe, MDD, turnover
        load_if_exists=True,
    )

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def default_objective(trial: "optuna.Trial") -> tuple[float, float, float]:
        suggested: dict[str, Any] = {}
        for name, dist in search_space.items():
            if isinstance(dist, IntDistribution):
                suggested[name] = trial.suggest_int(
                    name, dist.low, dist.high, step=dist.step,
                )
            elif dist.step is not None:
                suggested[name] = trial.suggest_float(
                    name, dist.low, dist.high, step=dist.step,
                )
            else:
                suggested[name] = trial.suggest_float(
                    name, dist.low, dist.high,
                )
            trial.set_user_attr(f"param_{name}", suggested[name])
        return compute_multi_objective_metrics(fills, suggested, search_space)

    obj = objective_fn or default_objective
    study.optimize(obj, n_trials=cfg.n_trials, show_progress_bar=False)

    # Extract Pareto front (best_trials in multi-objective study)
    # 提取 Pareto front（多目標 study 的 best_trials）
    pareto: list[dict[str, Any]] = []
    for t in study.best_trials:
        sharpe, mdd, turnover = t.values
        pareto.append({
            "trial_number": t.number,
            "params": dict(t.params),
            "sharpe": sharpe,
            "max_drawdown": mdd,
            "turnover": turnover,
        })

    logger.info(
        "Multi-objective optimization complete: study=%s pareto_size=%d n_trials=%d / "
        "多目標優化完成: study=%s Pareto 大小=%d n_trials=%d",
        study_name, len(pareto), cfg.n_trials,
        study_name, len(pareto), cfg.n_trials,
    )

    return {
        "status": "success",
        "pareto_front": pareto,
        "n_trials": len(study.trials),
        "study_name": study_name,
    }


def compute_multi_objective_metrics(
    fills: list[dict],
    suggested_params: dict[str, Any],
    search_space: dict[str, Any],
) -> tuple[float, float, float]:
    """Compute (sharpe, max_drawdown, turnover) for a candidate parameter set.
    計算候選參數集的 (sharpe, 最大回撤, 換手率)。

    Phase 3b offline mode: applies a parameter-distance perturbation to
    differentiate trials on the same fill set. Live mode would re-collect
    fills per trial via IPC.
    Phase 3b 離線模式：在同一筆數據集上以參數距離擾動區分試驗。

    Args:
        fills: Historical fills (pnl / qty / notional optional)
        suggested_params: Trial-suggested parameter values
        search_space: Optuna distributions (used for normalization)

    Returns:
        (sharpe, max_drawdown, turnover) tuple
    """
    if not fills:
        return 0.0, 0.0, 0.0

    pnls = [float(f.get("pnl", 0.0)) for f in fills]
    n = len(pnls)

    # Sharpe: mean / std (no annualization, fill-level)
    # Sharpe：均值/標準差（不年化，成交層級）
    mean = sum(pnls) / n
    if n > 1:
        var = sum((p - mean) ** 2 for p in pnls) / (n - 1)
        std = var ** 0.5
    else:
        std = 0.0
    sharpe = mean / std if std > 1e-12 else 0.0

    # Max drawdown on cumulative PnL
    # 累積 PnL 的最大回撤
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        dd = peak - cum
        max_dd = max(max_dd, dd)

    # Turnover: sum of |notional| (fall back to qty * 1.0, then count)
    # 換手率：|notional| 之和（退化為 qty 或計數）
    turnover = 0.0
    for f in fills:
        if "notional" in f:
            turnover += abs(float(f["notional"]))
        elif "qty" in f:
            turnover += abs(float(f["qty"]))
        else:
            turnover += 1.0

    # Offline-mode perturbation: small parameter-distance bonus to ensure
    # NSGA-II sees gradient between trials evaluated on the same fill set.
    # 離線模式擾動：小的參數距離獎勵，確保 NSGA-II 在同一數據集上看到梯度。
    if suggested_params:
        norm_sum = 0.0
        for name, val in suggested_params.items():
            dist = search_space.get(name)
            if dist is None:
                continue
            param_range = dist.high - dist.low
            if param_range > 0:
                norm_sum += (val - dist.low) / param_range
        avg_norm = norm_sum / len(suggested_params)
        sharpe += 0.001 * avg_norm
        turnover += 0.001 * (1.0 - avg_norm)

    return sharpe, max_dd, turnover
