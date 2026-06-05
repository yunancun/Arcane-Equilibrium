"""
MODULE_NOTE
模塊用途：Residual alpha cycle orchestrator（R-2b）。把一輪多 cell（strategy
[,symbol]）候選，按 QC/MIT 2026-06-05 定稿評估：
  ① n_trials = 真實搜尋基數（變體 × symbol × 策略，floor K>=10，記錄推導，
     **永不**用 obs/天數冒充 n_independent）；供 DsrGate 多重檢驗 deflation。
  ② PBO peers = **同策略參數變體**（非跨策略——跨策略 eval 窗對不齊且 N=2 時
     CSCV 無意義）；單一配置（無變體）→ CSCV-PBO 不適用 → **診斷性 fail-closed
     defer**（非「缺/作弊」）。DSR-only 晉升 lane 需未來明確 operator policy。
  ③ 非重疊 bucket 報酬（重用 R-2）→ R-1 → 已修的 gate（真 DsrGate/PboGate）。
主要函數：derive_n_trials、evaluate_cell、build_cycle_residual_reports（DB，Linux）。
依賴：residual_alpha_producer（R-1）+ residual_alpha_producer_db（bucket/DB）。
硬邊界：只讀；單一配置一律 defer（fail-closed）；n_trials 必為搜尋基數；
不碰 runtime / order / risk / auth。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

RESIDUAL_PRODUCER_ENV = "OPENCLAW_RESIDUAL_ALPHA_PRODUCER"
RESIDUAL_ALPHA_REPORT_FIELD = "demo_residual_alpha_report"

try:  # 套件式 import（app runtime）
    from program_code.learning_engine.residual_alpha_producer import (
        ResidualAlphaProducerResult,
        build_residual_alpha_report,
    )
    from program_code.ml_training.residual_alpha_producer_db import (
        DEFAULT_BUCKET_SEC,
        bucket_round_trips_by_exit,
        bucketed_btc_factor,
        load_btc_klines,
        load_round_trips,
    )
except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
    from learning_engine.residual_alpha_producer import (  # type: ignore
        ResidualAlphaProducerResult,
        build_residual_alpha_report,
    )
    from ml_training.residual_alpha_producer_db import (  # type: ignore
        DEFAULT_BUCKET_SEC,
        bucket_round_trips_by_exit,
        bucketed_btc_factor,
        load_btc_klines,
        load_round_trips,
    )


PBO_NOT_APPLICABLE_SINGLE = "not_applicable_single_candidate"
DEFAULT_N_TRIALS_FLOOR = 10


def derive_n_trials(
    n_param_variants: int,
    n_symbols_screened: int,
    n_strategies_screened: int,
    *,
    floor: int = DEFAULT_N_TRIALS_FLOOR,
) -> tuple[int, str]:
    """n_trials = 變體 × symbol × 策略（搜尋基數），floor 到 K>=floor。

    回 ``(n_trials, 推導字串)``。QC/MIT 紀律：這是**搜尋基數**（multiple-testing
    cardinality），**永不**是 obs/天數/row 數。floor 反映程式級多月搜尋的家族多重性
    （selection_bias_validator 要求 K>=10）。
    """
    v = max(1, int(n_param_variants))
    s = max(1, int(n_symbols_screened))
    g = max(1, int(n_strategies_screened))
    raw = v * s * g
    n = max(raw, int(floor))
    deriv = f"{v}var × {s}sym × {g}strat = {raw}"
    if n != raw:
        deriv += f" → floored to {n} (K>={floor})"
    return n, deriv


@dataclass(frozen=True)
class CellResidualResult:
    """單一 cell 的 residual 評估結果 + 診斷。"""

    cell_key: str
    status: str  # evaluated | single_config_defer | no_data
    promotion_ready: bool
    reason: str
    n_trials: int
    n_trials_derivation: str
    report: dict[str, Any] | None = None
    diag: dict[str, Any] = field(default_factory=dict)


def evaluate_cell(
    cell_key: str,
    candidate_round_trips: Sequence[Mapping[str, Any]],
    btc_klines: Sequence[Mapping[str, Any]],
    *,
    n_param_variants: int,
    n_symbols_screened: int,
    n_strategies_screened: int,
    peer_variant_round_trips: Sequence[Sequence[Mapping[str, Any]]] | None = None,
    bucket_sec: float = DEFAULT_BUCKET_SEC,
    embargo_buckets: int = 1,
    min_train_observations: int = 20,
    min_eval_observations: int = 8,
    n_trials_floor: int = DEFAULT_N_TRIALS_FLOOR,
    **gate_kwargs: Any,
) -> CellResidualResult:
    """評估單一 cell。peers = 同策略其他參數變體的非重疊 bucket 序列；無 peer
    （單一配置）→ CSCV 不適用 → 診斷性 defer。所有報酬走 R-2 非重疊 bucket。
    """
    n_trials, deriv = derive_n_trials(
        n_param_variants, n_symbols_screened, n_strategies_screened, floor=n_trials_floor
    )
    candidate_buckets, counts = bucket_round_trips_by_exit(candidate_round_trips, bucket_sec)
    factor_buckets = bucketed_btc_factor(btc_klines, bucket_sec)
    if not candidate_buckets or not factor_buckets:
        return CellResidualResult(
            cell_key=cell_key,
            status="no_data",
            promotion_ready=False,
            reason="no_aligned_buckets",
            n_trials=n_trials,
            n_trials_derivation=deriv,
            report=None,
            diag={
                "candidate_buckets": len(candidate_buckets),
                "factor_buckets": len(factor_buckets),
            },
        )

    peer_buckets = [
        bucket_round_trips_by_exit(rts, bucket_sec)[0]
        for rts in (peer_variant_round_trips or [])
    ]
    peer_buckets = [p for p in peer_buckets if p]  # 丟空 peer
    single_config = len(peer_buckets) < 1
    embargo_gap = (embargo_buckets + 0.5) * bucket_sec if embargo_buckets > 0 else 0.0

    result = build_residual_alpha_report(
        candidate_buckets,
        factor_buckets,
        n_trials=n_trials,
        peer_oos_returns=(None if single_config else peer_buckets),
        required_factors=("btc",),
        embargo_gap=embargo_gap,
        min_train_observations=min_train_observations,
        min_eval_observations=min_eval_observations,
        **gate_kwargs,
    )

    report = dict(result.report) if isinstance(result.report, dict) else None
    if single_config:
        # 標記 PBO 不適用（診斷性，非作弊/缺失）。gate 因無 peer 已 fail-closed
        # defer；此處給 orchestrator/operator 可區分的診斷理由。
        if report is not None:
            report["pbo_status"] = PBO_NOT_APPLICABLE_SINGLE
        status = "single_config_defer"
        promotion_ready = False
        reason = "pbo_not_applicable_single_candidate"
    else:
        status = "evaluated"
        promotion_ready = bool(result.promotion_ready)
        reason = result.reason

    diag = {
        "candidate_buckets": len(candidate_buckets),
        "n_peers": len(peer_buckets),
        "aligned_observations": result.aligned_observations,
        "train_observations": result.train_observations,
        "eval_observations": result.eval_observations,
        "mean_trips_per_bucket": (sum(counts.values()) / len(counts)) if counts else 0.0,
    }
    return CellResidualResult(
        cell_key=cell_key,
        status=status,
        promotion_ready=promotion_ready,
        reason=reason,
        n_trials=n_trials,
        n_trials_derivation=deriv,
        report=report,
        diag=diag,
    )


# ---------------------------------------------------------------------------
# DB cycle 層（Linux runtime 驗證）—— 只讀
# ---------------------------------------------------------------------------


def build_cycle_residual_reports(
    conn: Any,
    cells: Sequence[Mapping[str, Any]],
    *,
    engine_mode: str = "demo",
    since: datetime,
    bucket_sec: float = DEFAULT_BUCKET_SEC,
    n_symbols_screened: int = 1,
    klines_timeframe: str = "4h",
    klines_pad_sec: float = DEFAULT_BUCKET_SEC,
    **cell_kwargs: Any,
) -> dict[str, CellResidualResult]:
    """一輪多 cell 評估（v1，BTC-only，非重疊 bucket）。

    cells: ``[{"cell_key": str, "strategy_name": str,
               "n_param_variants": int(預設1),
               "peer_strategy_names": list[str]|None}, ...]``。
    n_strategies_screened = 本輪 cell 數（搜尋家族多重性）。BTC klines 載一次覆蓋
    全 cell round-trip 時間範圍。只讀；不碰 runtime / order / risk。
    """
    n_strategies_screened = len(cells)
    rt_by_strategy: dict[str, list[dict[str, float]]] = {}

    def _rts(strategy: str) -> list[dict[str, float]]:
        if strategy not in rt_by_strategy:
            rt_by_strategy[strategy] = load_round_trips(
                conn, strategy, engine_mode=engine_mode, since=since
            )
        return rt_by_strategy[strategy]

    out: dict[str, CellResidualResult] = {}
    # 先收集全部 round-trip 決定 BTC klines 範圍
    all_strategies = {c["strategy_name"] for c in cells}
    for s in all_strategies:
        _rts(s)
    all_rts = [rt for rts in rt_by_strategy.values() for rt in rts]
    if not all_rts:
        return out
    min_entry = min(rt["entry_ts"] for rt in all_rts)
    max_exit = max(rt["exit_ts"] for rt in all_rts)
    start_dt = datetime.fromtimestamp(min_entry - klines_pad_sec, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(max_exit + klines_pad_sec, tz=timezone.utc)
    btc_klines = load_btc_klines(
        conn, start_ts=start_dt, end_ts=end_dt, timeframe=klines_timeframe
    )

    for cell in cells:
        cell_key = str(cell["cell_key"])
        strategy = str(cell["strategy_name"])
        n_variants = int(cell.get("n_param_variants", 1))
        peer_names = cell.get("peer_strategy_names") or []
        peer_rts = [_rts(str(p)) for p in peer_names] if n_variants > 1 else None
        out[cell_key] = evaluate_cell(
            cell_key,
            _rts(strategy),
            btc_klines,
            n_param_variants=n_variants,
            n_symbols_screened=n_symbols_screened,
            n_strategies_screened=n_strategies_screened,
            peer_variant_round_trips=peer_rts,
            bucket_sec=bucket_sec,
            **cell_kwargs,
        )
    return out


# ---------------------------------------------------------------------------
# R-3 接線 primitive（env-flag 預設 OFF）—— 把 report 附到 recommendation payload
# ---------------------------------------------------------------------------


def residual_producer_enabled() -> bool:
    """env-flag（預設 OFF）：未明確設 ``OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1`` 一律
    不附 report。部署即關（fail-closed），不改現有晉升行為，待 operator 啟用。
    """
    return os.environ.get(RESIDUAL_PRODUCER_ENV, "0").strip() == "1"


def attach_residual_reports(
    recommendations: Sequence[Any],
    conn: Any,
    *,
    since: datetime,
    n_symbols_screened: int = 1,
    report_field: str = RESIDUAL_ALPHA_REPORT_FIELD,
    **cycle_kwargs: Any,
) -> int:
    """為每個 recommendation（須有 ``.strategy_name`` / ``.symbol`` / ``.payload``）算
    residual report 並附到其 ``payload[report_field]``（in-memory mutate）。回 attached 數。

    caller 須先檢查 ``residual_producer_enabled()``。只讀 DB；單一配置 demo 下
    report 為診斷性 defer（晉升閘仍 fail-closed），故附了也不會放行——這是 by design。
    不碰 runtime / order / risk / auth。
    """
    if not recommendations:
        return 0
    cells: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rec in recommendations:
        strategy = getattr(rec, "strategy_name", None)
        symbol = getattr(rec, "symbol", None)
        if not strategy:
            continue
        key = f"{strategy}::{symbol}"
        if key not in seen:
            seen.add(key)
            cells.append(
                {"cell_key": key, "strategy_name": str(strategy), "n_param_variants": 1}
            )
    if not cells:
        return 0
    results = build_cycle_residual_reports(
        conn, cells, since=since, n_symbols_screened=n_symbols_screened, **cycle_kwargs
    )
    attached = 0
    for rec in recommendations:
        strategy = getattr(rec, "strategy_name", None)
        symbol = getattr(rec, "symbol", None)
        payload = getattr(rec, "payload", None)
        cell_result = results.get(f"{strategy}::{symbol}")
        if (
            cell_result is not None
            and cell_result.report is not None
            and isinstance(payload, dict)
        ):
            payload[report_field] = cell_result.report
            attached += 1
    return attached


__all__ = [
    "PBO_NOT_APPLICABLE_SINGLE",
    "DEFAULT_N_TRIALS_FLOOR",
    "RESIDUAL_PRODUCER_ENV",
    "RESIDUAL_ALPHA_REPORT_FIELD",
    "derive_n_trials",
    "CellResidualResult",
    "evaluate_cell",
    "build_cycle_residual_reports",
    "residual_producer_enabled",
    "attach_residual_reports",
]
