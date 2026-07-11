#!/usr/bin/env python3
"""Review blocked-signal outcomes for the cost-gate demo learning lane.

This module turns accumulated ``blocked_signal_outcome`` ledger rows into a
machine-checkable review scorecard. It does not grant order authority, lower
the main Cost Gate, write PG, call Bybit, or mutate runtime config.

F1 修復(2026-07-10,R3 charter WP-A.1/2;判準正本 = QC 預註冊
docs/research/2026-07-10--counterfactual_rerun_preregistration.md):
  1. 樣本單位對齊預註冊 §2 — 觀測單位 = (side_cell, entry_minute, horizon),
     entry_minute = floor(entry_ts_ms / 60_000)。毫秒精確去重不足以擋近似複製:
     秒級重發信號產生 distinct 毫秒 entry_ts_ms,但同一分鐘內共享同一根 1m bar
     的價格路徑,屬同一觀測。組內不取平均(§2.3 禁止靜默平均):代表行 =
     attempt_id 字典序最小;複本 realized_net_bps / gross_bps 不一致(容差
     1e-9)→ 該 cell 標 DATA_INTEGRITY_SUSPECT 並排除出檢定 family。
  2. n_eff = 非重疊窗 greedy 子樣本(§2.6):entry_minute 升序 earliest-first,
     上一入選 entry 的 horizon 窗未關閉前不再入選 —— 窗重疊 markout 共享價格
     路徑,自相關會膨脹 t 統計。raw outcome_count 一律不得進 eligibility / t /
     BH-FDR。候選 eligibility = E1 n_eff≥30 + E2 distinct UTC days≥5 +
     E3 top-day share≤50%(§3 凍結值)。
  3. 成本雙軌 — 主判接 slippage_quantile_artifact 的實測 E[cost]
     (E[|slip|]=mean_abs,無安全乘數;預註冊 §6.1);尾部敏感性欄 = CVaR90 尾部
     成本(預註冊 §6.2)+ conservative_v1(q75×1.3)第三對照欄,皆並列輸出不作
     主判。artifact 缺失/過期/無 mean_abs 欄時主判 fail-closed 回退
     conservative_v1(不因缺 artifact 放寬)。
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
for _path in (str(RESEARCH_ROOT), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cost_gate_learning_lane.contract import BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE
from cost_gate_learning_lane.candidate_board import (
    ARBITER_INPUT_SCHEMA_VERSION,
    LEARNING_CANDIDATE_BOARD_SCHEMA_VERSION,
    build_learning_candidate_board,
    candidate_learning_context as _candidate_learning_context,
)
from cost_gate_learning_lane.cost_model import (
    FEE_FLOOR_BPS,
    FEE_TAKER_BPS,
    MIN_SYMBOL_FILLS_FOR_QUANTILE,
    QUANTILE_ARTIFACT_MAX_AGE_HOURS,
)
from cost_gate_learning_lane.evidence_stats import (
    bh_fdr_pass,
    expected_max_under_null_bps,
    one_sided_t_p_value,
    sign_flip_selection_p_value,
)
from cost_gate_learning_lane.runtime_adapter import read_jsonl_ledger


# v6:learning_candidate_board 先做 prospective raw/evaluation lineage 三分區，
# 再以 qualified subset 計算統計；另加 event_hash 衝突 quarantine 及 selection/audit
# 雜湊分面。升版使 v5 的 legacy candidate_learning_context board 在 consumer ingress
# fail-closed，不能被誤認為可供 autonomous learning 的 lineage-complete 證據。
BLOCKED_OUTCOME_REVIEW_SCHEMA_VERSION = (
    "cost_gate_demo_learning_lane_blocked_outcome_review_v6"
)
BLOCKED_OUTCOME_REVIEW_RECORD_TYPE = "blocked_signal_outcome_review"

# 樂觀成本 fallback 常數(舊 legacy row 的 gross−4.0 對照軌),與 outcome_writer
# 的 cfg.cost_bps 歷史默認一致。
_LEGACY_OPTIMISTIC_COST_BPS = 4.0
_SLIPPAGE_ARTIFACT_SCHEMA_VERSION = "cost_gate_slippage_quantile_artifact_v2"
_SLIPPAGE_ARTIFACT_FIELDS = {
    "schema_version",
    "asof",
    "window_days",
    "n_total_global",
    "symbols",
    "global",
    "boundary",
}
_SLIPPAGE_STAT_FIELDS = {
    "n",
    "mean_abs",
    "mean_signed",
    "q50",
    "q75",
    "q90",
    "cvar90",
    "thin_sample",
}
_SLIPPAGE_SYMBOL_FIELDS = {*_SLIPPAGE_STAT_FIELDS, "symbol"}
_SLIPPAGE_WINDOW_DAYS = 90
_SLIPPAGE_MEAN_ABS_TOL_BPS = 1e-9
_SLIPPAGE_MEAN_REL_TOL = 1e-12
_SLIPPAGE_BOUNDARY = (
    "slippage quantile artifact only; PG source is read-only SELECT-only; "
    "no PG write, Bybit call, order, config, risk, auth, or runtime mutation"
)


@dataclass(frozen=True)
class BlockedOutcomeReviewConfig:
    """Fail-closed thresholds for blocked-signal review candidates."""

    # F1:min_outcomes_per_side_cell 自 v4 起量測 distinct-entry 有效觀測數
    # (n_eff),不再量測 raw row 數 — 無重複時兩者相等,行為不變。
    min_outcomes_per_side_cell: int = 3
    min_avg_net_bps: float = 0.0
    min_net_positive_pct: float = 60.0
    # P2-8:候選面 BH-FDR 目標 false discovery rate;headline sign-flip 抽樣次數。
    fdr_q: float = 0.10
    sign_flip_b: int = 1000
    # F1:distinct-entry n_eff 候選門檻(eligibility 硬 floor)。30 = QC 預註冊
    # 判準 §3 E1 凍結值(docs/research/2026-07-10--counterfactual_rerun_
    # preregistration.md:厚尾下 t 近似的最低可信樣本;n<30 的 t p-value 無意義)。
    # 低於此值的 cell 統計可算(exploration 排序)但不得成 review candidate。
    min_effective_entries_per_side_cell: int = 30
    # 預註冊 §3 E2:入選 entry 覆蓋的 distinct UTC 日數下限。5 = 凍結值(F1 的
    # 根本形態是單日 episode regime-bet;day-cluster 推斷 df=G−1,G<5 不可用)。
    min_distinct_entry_utc_days: int = 5
    # 預註冊 §3 E3:單一 UTC 日佔入選 entry 比例上限。50% = 凍結值(防「名義
    # 多天、實質單日主導」繞過 E2)。
    max_top_entry_day_share_pct: float = 50.0


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _str(value: Any) -> str:
    return str(value or "").strip()


def validate_blocked_outcome_review_config(cfg: BlockedOutcomeReviewConfig) -> None:
    if cfg.min_outcomes_per_side_cell < 1 or cfg.min_outcomes_per_side_cell > 1_000:
        raise ValueError("--min-outcomes-per-side-cell must be in [1, 1000]")
    if (
        cfg.min_effective_entries_per_side_cell < 1
        or cfg.min_effective_entries_per_side_cell > 1_000
    ):
        raise ValueError("--min-effective-entries-per-side-cell must be in [1, 1000]")
    if cfg.min_distinct_entry_utc_days < 1 or cfg.min_distinct_entry_utc_days > 365:
        raise ValueError("--min-distinct-entry-utc-days must be in [1, 365]")
    if not (0.0 < cfg.max_top_entry_day_share_pct <= 100.0):
        raise ValueError("--max-top-entry-day-share-pct must be in (0, 100]")
    if cfg.min_avg_net_bps < -10_000.0 or cfg.min_avg_net_bps > 10_000.0:
        raise ValueError("--min-avg-net-bps must be in [-10000, 10000]")
    if cfg.min_net_positive_pct < 0.0 or cfg.min_net_positive_pct > 100.0:
        raise ValueError("--min-net-positive-pct must be in [0, 100]")
    if not (0.0 < cfg.fdr_q < 1.0):
        raise ValueError("--fdr-q must be in (0, 1)")
    if cfg.sign_flip_b < 1 or cfg.sign_flip_b > 100_000:
        raise ValueError("--sign-flip-b must be in [1, 100000]")


def _row_sort_ts(row: dict[str, Any]) -> str:
    return _str(row.get("generated_at_utc")) or _str(row.get("exit_ts_ms"))


def _int(value: Any, default: int = 0) -> int:
    try:
        out = int(float(value))
    except (TypeError, ValueError):
        return default
    return out


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_iso_utc(value: Any) -> dt.datetime | None:
    """解析 ISO8601 為 UTC datetime。artifact 新鮮度檢查用(不可解析 → None)。"""
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _project_tail_slippage(block: dict[str, Any]) -> tuple[float | None, str | None]:
    """尾部滑點投影:cvar90 優先,缺失 fallback q90(預註冊 §6.2 凍結順序)。"""
    cvar90 = _float(block.get("cvar90"))
    if cvar90 is not None:
        return cvar90, "cvar90"
    q90 = _float(block.get("q90"))
    if q90 is not None:
        return q90, "q90_fallback"
    return None, None


def _producer_float_or_none(value: Any, *, nonnegative: bool) -> float | None:
    """Validate the exact JSON-number type emitted by the v2 producer."""
    if value is None:
        return None
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("slippage statistic must be an exact finite float")
    if nonnegative and value < 0.0:
        raise ValueError("absolute slippage statistic must be nonnegative")
    return value


def _validate_slippage_stat_block(
    block: Any,
    *,
    symbol_row: bool,
) -> dict[str, Any]:
    expected_fields = _SLIPPAGE_SYMBOL_FIELDS if symbol_row else _SLIPPAGE_STAT_FIELDS
    if not isinstance(block, dict) or set(block) != expected_fields:
        raise ValueError("slippage statistic fields invalid")
    n = block["n"]
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
        raise ValueError("slippage sample count invalid")
    mean_abs = _producer_float_or_none(block["mean_abs"], nonnegative=True)
    mean_signed = _producer_float_or_none(block["mean_signed"], nonnegative=False)
    q50 = _producer_float_or_none(block["q50"], nonnegative=True)
    q75 = _producer_float_or_none(block["q75"], nonnegative=True)
    q90 = _producer_float_or_none(block["q90"], nonnegative=True)
    cvar90 = _producer_float_or_none(block["cvar90"], nonnegative=True)
    if (
        mean_abs is None
        or mean_signed is None
        or q50 is None
        or q75 is None
        or (q90 is None) is not (cvar90 is None)
    ):
        # CVaR may be absent while q90 is present (the canonical q90 fallback).
        if not (
            mean_abs is not None
            and mean_signed is not None
            and q50 is not None
            and q75 is not None
            and q90 is not None
            and cvar90 is None
        ):
            raise ValueError("slippage producer statistic completeness invalid")
    if abs(mean_signed) > mean_abs and not math.isclose(
        abs(mean_signed),
        mean_abs,
        rel_tol=_SLIPPAGE_MEAN_REL_TOL,
        abs_tol=_SLIPPAGE_MEAN_ABS_TOL_BPS,
    ):
        raise ValueError("slippage signed mean exceeds absolute mean")
    thin_sample = block["thin_sample"]
    if not isinstance(thin_sample, bool) or thin_sample is not (n < 100):
        raise ValueError("slippage thin-sample flag invalid")
    ordered_quantiles = [value for value in (q50, q75, q90) if value is not None]
    if ordered_quantiles != sorted(ordered_quantiles):
        raise ValueError("slippage quantile order invalid")
    if cvar90 is not None and q90 is not None and cvar90 < q90:
        raise ValueError("slippage cvar order invalid")
    result = {
        "n": n,
        "mean_abs": mean_abs,
        "mean_signed": mean_signed,
        "q50": q50,
        "q75": q75,
        "q90": q90,
        "cvar90": cvar90,
        "thin_sample": thin_sample,
    }
    if symbol_row:
        symbol = block["symbol"]
        if (
            not isinstance(symbol, str)
            or not symbol
            or symbol != symbol.strip()
            or symbol != symbol.upper()
        ):
            raise ValueError("slippage symbol invalid")
        result["symbol"] = symbol
    return result


def _load_expected_slippage(
    payload: dict[str, Any] | None,
    *,
    now: dt.datetime,
    max_age_hours: int = QUANTILE_ARTIFACT_MAX_AGE_HOURS,
) -> dict[str, Any] | None:
    """把 slippage_quantile_artifact payload 投影成主判/尾部滑點查表。

    主判 E[slip_leg] = mean_abs(E[|slip|],預註冊 §6.1 凍結公式;E[|x|]≥|E[x]|
    把有利滑點也計為成本 → 溫和保守偏置);尾部敏感性 slip = cvar90(§6.2),
    cvar90 缺失 fallback q90。回傳 None = 實測軌不可用(payload 缺失/畸形/asof
    過期/無 global mean_abs),主判 fail-closed 回退 conservative_v1。舊版
    artifact(無 mean_abs 欄)同樣整軌拒用 —— 不得以 q50 頂替 mean_abs:右偏
    |slip| 下 q50 < mean,會系統性低估成本(anti-conservative,違預註冊 §6.1)。
    """
    if not isinstance(payload, dict):
        return None
    if (
        set(payload) != _SLIPPAGE_ARTIFACT_FIELDS
        or payload.get("schema_version") != _SLIPPAGE_ARTIFACT_SCHEMA_VERSION
        or type(payload.get("window_days")) is not int
        or payload.get("window_days") != _SLIPPAGE_WINDOW_DAYS
        or payload.get("boundary") != _SLIPPAGE_BOUNDARY
    ):
        return None
    raw_asof = payload.get("asof")
    asof = _parse_iso_utc(raw_asof)
    if asof is None or not isinstance(raw_asof, str) or raw_asof != asof.isoformat():
        return None
    review_time = now.astimezone(dt.timezone.utc)
    if asof > review_time:
        return None
    if review_time - asof > dt.timedelta(hours=max_age_hours):
        return None
    try:
        global_block = _validate_slippage_stat_block(
            payload.get("global"),
            symbol_row=False,
        )
    except ValueError:
        return None
    global_n = global_block.get("n")
    n_total_global = payload.get("n_total_global")
    if (
        not isinstance(global_n, int)
        or isinstance(global_n, bool)
        or global_n <= 0
        or not isinstance(n_total_global, int)
        or isinstance(n_total_global, bool)
        or n_total_global != global_n
    ):
        return None
    global_mean_abs = global_block["mean_abs"]
    if global_mean_abs is None:
        return None
    global_tail, global_tail_metric = _project_tail_slippage(global_block)
    per_symbol: dict[str, dict[str, Any]] = {}
    rows = payload.get("symbols")
    if not isinstance(rows, list):
        return None
    try:
        normalized_rows = [
            _validate_slippage_stat_block(row, symbol_row=True) for row in rows
        ]
    except ValueError:
        return None
    symbols = [row["symbol"] for row in normalized_rows]
    if (
        not symbols
        or symbols != sorted(symbols)
        or len(symbols) != len(set(symbols))
        or sum(row["n"] for row in normalized_rows) != global_n
    ):
        return None
    try:
        weighted_mean_abs = math.fsum(
            row["mean_abs"] * row["n"] for row in normalized_rows
        ) / global_n
        weighted_mean_signed = math.fsum(
            row["mean_signed"] * row["n"] for row in normalized_rows
        ) / global_n
    except (OverflowError, ValueError):
        return None
    if (
        not math.isfinite(weighted_mean_abs)
        or not math.isfinite(weighted_mean_signed)
        or not math.isclose(
            global_mean_abs,
            weighted_mean_abs,
            rel_tol=_SLIPPAGE_MEAN_REL_TOL,
            abs_tol=_SLIPPAGE_MEAN_ABS_TOL_BPS,
        )
        or not math.isclose(
            global_block["mean_signed"],
            weighted_mean_signed,
            rel_tol=_SLIPPAGE_MEAN_REL_TOL,
            abs_tol=_SLIPPAGE_MEAN_ABS_TOL_BPS,
        )
    ):
        return None
    for row in normalized_rows:
        symbol = row["symbol"]
        mean_abs = row["mean_abs"]
        if mean_abs is None:
            return None
        tail, tail_metric = _project_tail_slippage(row)
        per_symbol[symbol] = {
            "n": row["n"],
            "mean_abs": mean_abs,
            "tail_bps": tail,
            "tail_metric": tail_metric,
        }
    canonical_asof = asof.isoformat()
    normalized_projection = {
        "schema_version": "cost_gate_expected_cost_projection_v2",
        "source_asof_utc": canonical_asof,
        "source_window_days": payload["window_days"],
        "global": {
            "n": global_n,
            "mean_abs_bps": global_mean_abs,
            "tail_bps": global_tail,
            "tail_metric": global_tail_metric,
        },
        "symbols": [
            {
                "symbol": symbol,
                "n": item["n"],
                "mean_abs_bps": item["mean_abs"],
                "tail_bps": item["tail_bps"],
                "tail_metric": item["tail_metric"],
            }
            for symbol, item in sorted(per_symbol.items())
        ],
    }
    return {
        "per_symbol": per_symbol,
        "global_mean_abs": global_mean_abs,
        "global_tail_bps": global_tail,
        "global_tail_metric": global_tail_metric,
        "asof": canonical_asof,
        "n_total_global": global_n,
        "source_payload_sha256": _canonical_sha256(payload),
        "source_payload": copy.deepcopy(payload),
        "normalized_projection": normalized_projection,
        "normalized_projection_sha256": _canonical_sha256(normalized_projection),
    }


def _expected_cost_bps_for_row(
    row: dict[str, Any],
    expected_slippage: dict[str, Any],
) -> dict[str, Any]:
    """單 row 的實測 E[cost] 主判與 CVaR90 尾部成本(bps),回傳兩軌並列。

    主判(預註冊 §6.1):E[cost] = 2×(taker fee + mean_abs) + row 自帶 funding
    drag,不乘 1.3 安全乘數 —— SM 是 gate 設計參數,不是誤殺量測的成分;尾部
    保守性由 §6.2 CVaR90 尾部欄並列承載,不再進主判。
    尾部(預註冊 §6.2):cost_tail = 2×(taker fee + CVaR90) + funding drag。
    不變量:兩軌皆 ≥ FEE_FLOOR_BPS(手續費不打折,QC 硬約束 #4)。
    """
    symbol = _str(row.get("symbol")).upper()
    entry = expected_slippage["per_symbol"].get(symbol)
    if entry is not None and entry["n"] >= MIN_SYMBOL_FILLS_FOR_QUANTILE:
        slip = entry["mean_abs"]
        tail_slip = entry["tail_bps"]
        tail_metric = entry["tail_metric"]
    else:
        slip = expected_slippage["global_mean_abs"]
        tail_slip = expected_slippage["global_tail_bps"]
        tail_metric = expected_slippage["global_tail_metric"]
    if tail_slip is None:
        # symbol 級尾部缺欄 → global 尾部(fallback 只向更廣樣本退,不放寬)。
        tail_slip = expected_slippage["global_tail_bps"]
        tail_metric = expected_slippage["global_tail_metric"]
    funding_drag = max(0.0, _float(row.get("funding_drag_bps")) or 0.0)
    expected_cost = max(2.0 * (FEE_TAKER_BPS + slip) + funding_drag, FEE_FLOOR_BPS)
    tail_cost = (
        max(2.0 * (FEE_TAKER_BPS + tail_slip) + funding_drag, FEE_FLOOR_BPS)
        if tail_slip is not None
        else None
    )
    return {
        "expected_cost_bps": expected_cost,
        "tail_cost_bps": tail_cost,
        "tail_metric": tail_metric,
    }


def _entry_group_key(row: dict[str, Any]) -> tuple[int, int] | None:
    """取 (entry_minute, horizon_minutes) 觀測單位鍵(預註冊 §2.1)。

    entry_minute = floor(entry_ts_ms / 60_000):秒級重發信號的 distinct 毫秒
    entry_ts_ms 共享同一根 1m bar 的價格路徑,屬同一觀測 —— 毫秒精確鍵會把
    近似複製誤認 distinct(v4 漏洞)。entry_ts_ms 缺失/非正 → None(unknown 桶,
    fail-closed 不入樣本)。
    """
    try:
        ts = int(float(row.get("entry_ts_ms")))
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return (ts // 60_000, max(_int(row.get("horizon_minutes"), default=0), 0))


def _entry_utc_day(entry_minute: int) -> str:
    """entry_minute → UTC 日曆日(ISO date;預註冊 §3 E2/E3 的 cluster 單位)。"""
    return (
        dt.datetime.fromtimestamp(entry_minute * 60, tz=dt.timezone.utc)
        .date()
        .isoformat()
    )


# 預註冊 §2.3 複本一致性容差(bps)。
_REPLICA_VALUE_TOLERANCE_BPS = 1e-9


def _replica_values_consistent(values: list[float | None]) -> bool:
    """組內複本值一致性:全 None 一致;None/數值混雜或極差超容差 → 不一致。

    為什麼 fail-closed:同一觀測單位的複本值不同 = 資料完整性疑點(或去重鍵
    仍不足),靜默取平均會把疑點洗進統計(預註冊 §2.3 明文禁止)。
    """
    present = [v for v in values if v is not None]
    if not present:
        return True
    if len(present) != len(values):
        return False
    return (max(present) - min(present)) <= _REPLICA_VALUE_TOLERANCE_BPS


def _effective_entries(
    rows: list[dict[str, Any]],
    *,
    expected_slippage: dict[str, Any] | None,
) -> dict[str, Any]:
    """F1 去重 + 非重疊窗子樣本:raw outcome rows → 統計唯一合法樣本(預註冊 §2)。

    為什麼:ma_crossover 類策略對同一次進場秒級重發信號,每次被擋都落一行
    outcome,raw 行數可把單一 entry 複製數千份(自相關 100%),t/BH-FDR 因此
    全部失效(F1 偽複製,NEAR 候選 5058 行實為 2 個 distinct entry)。

    管線(全部確定性、無自由參數):
      1. 按 (entry_minute, horizon) 分組;entry_ts_ms 缺失 row 無法證明身分,
         全部落 unknown 桶,不入樣本(fail-closed:寧可低估 n_eff,不可虛增)。
      2. 每組代表行 = attempt_id 字典序最小(§2.2;不取平均);複本
         realized_net_bps / gross_bps 不一致 → 記 replica_inconsistent_group_count
         (cell 級升 DATA_INTEGRITY_SUSPECT,§2.3)。
      3. greedy earliest-first 非重疊窗選樣(§2.6):entry_minute 升序,上一
         入選 entry 的 horizon 窗未關閉前跳過 —— 窗重疊 markout 共享價格路徑,
         自相關 ≈ (1 − Δt/h) 會膨脹 t 統計。
      4. 入選 entry 的 UTC 日分布(distinct days / top-day share)供 §3 E2/E3
         eligibility 與 checklist 攔截。
    """
    groups: dict[tuple[int, int] | None, list[dict[str, Any]]] = {}
    entry_ts_missing_row_count = 0
    for row in rows:
        key = _entry_group_key(row)
        if key is None:
            entry_ts_missing_row_count += 1
            continue
        groups.setdefault(key, []).append(row)

    dedup_entries: list[dict[str, Any]] = []
    replica_inconsistent_group_count = 0
    for key in sorted(groups):
        members = [
            row for row in groups[key] if _float(row.get("realized_net_bps")) is not None
        ]
        if not members:
            continue
        # §2.2 代表行 = attempt_id 字典序最小(確定性,不取平均)。
        representative = min(members, key=lambda row: _str(row.get("attempt_id")))
        # §2.3 複本一致性(realized_net_bps / gross_bps,容差 1e-9 bps)。
        if not (
            _replica_values_consistent(
                [_float(row.get("realized_net_bps")) for row in members]
            )
            and _replica_values_consistent(
                [_float(row.get("gross_bps")) for row in members]
            )
        ):
            replica_inconsistent_group_count += 1
        net = _float(representative.get("realized_net_bps"))
        gross = _float(representative.get("gross_bps"))
        # candidacy_flipped_by_cost_model 對照軌:optimistic net(gross−4.0);
        # net_bps_optimistic 缺失(舊 legacy row 未經 overlay)則 fallback。
        opt = _float(representative.get("net_bps_optimistic"))
        if opt is None:
            opt = gross - _LEGACY_OPTIMISTIC_COST_BPS if gross is not None else net
        expected_net = None
        expected_cost = None
        tail_net = None
        tail_cost = None
        tail_metric = None
        if expected_slippage is not None:
            if gross is not None:
                tracks = _expected_cost_bps_for_row(representative, expected_slippage)
                expected_cost = tracks["expected_cost_bps"]
                expected_net = gross - expected_cost
                if tracks["tail_cost_bps"] is not None:
                    tail_cost = tracks["tail_cost_bps"]
                    tail_net = gross - tail_cost
                    tail_metric = tracks["tail_metric"]
            else:
                # gross 缺失無法重算實測成本淨值 → 沿用保守淨值(fail-closed
                # 向下:conservative net ≤ expected net,不會放寬)。尾部軌不做
                # 此替代:conservative cost 可低於 CVaR90 尾部成本,替代會虛增
                # tail net(loss-budget 敘事 anti-conservative)→ 該 entry 直接
                # 不入尾部樣本。
                expected_net = net
        learning_context = _candidate_learning_context(representative) or {}
        dedup_entries.append(
            {
                "entry_minute": key[0],
                "horizon_minutes": key[1],
                "entry_utc_day": _entry_utc_day(key[0]),
                "net_conservative": net,
                "net_optimistic": opt,
                "net_expected": expected_net,
                "expected_cost_bps": expected_cost,
                "net_tail": tail_net,
                "tail_cost_bps": tail_cost,
                "tail_metric": tail_metric,
                "gross_bps": gross,
                "cost_bps": _float(representative.get("cost_bps")),
                "evidence_regime_label": learning_context.get(
                    "evidence_regime_label"
                ),
                "duplicate_row_count": len(members) - 1,
            }
        )

    # §2.6 greedy earliest-first 非重疊窗(排序鍵確定性;混 horizon cell 用「上一
    # 入選 entry 的窗關閉」判準 —— 比 per-horizon 各自 greedy 更保守,跨 horizon
    # 的路徑重疊也一併消除)。
    selected: list[dict[str, Any]] = []
    blocked_until_minute: int | None = None
    for entry in sorted(
        dedup_entries,
        key=lambda item: (item["entry_minute"], item["horizon_minutes"]),
    ):
        if (
            blocked_until_minute is not None
            and entry["entry_minute"] < blocked_until_minute
        ):
            continue
        selected.append(entry)
        blocked_until_minute = entry["entry_minute"] + max(
            entry["horizon_minutes"], 1
        )

    day_counts: dict[str, int] = {}
    for entry in selected:
        day = entry["entry_utc_day"]
        day_counts[day] = day_counts.get(day, 0) + 1
    top_entry_utc_day = None
    top_entry_day_share_pct = None
    if day_counts:
        top_entry_utc_day, top_count = sorted(
            day_counts.items(), key=lambda item: (-item[1], item[0])
        )[0]
        top_entry_day_share_pct = top_count / len(selected) * 100.0

    tail_metrics = {
        entry["tail_metric"] for entry in selected if entry["tail_metric"]
    }
    return {
        "entries": selected,
        "distinct_entry_observation_count": len(dedup_entries),
        "window_overlap_excluded_entry_count": len(dedup_entries) - len(selected),
        "replica_inconsistent_group_count": replica_inconsistent_group_count,
        "entry_ts_missing_row_count": entry_ts_missing_row_count,
        "distinct_entry_utc_days": len(day_counts),
        "entry_day_counts": {day: day_counts[day] for day in sorted(day_counts)},
        "top_entry_utc_day": top_entry_utc_day,
        "top_entry_day_share_pct": top_entry_day_share_pct,
        # 尾部滑點度量申報:cvar90 或 q90_fallback(cell 級並列輸出時記名)。
        "tail_metric": (
            sorted(tail_metrics)[0]
            if len(tail_metrics) == 1
            else ("mixed" if tail_metrics else None)
        ),
    }


def _sample_eligibility_failure_reason(
    *,
    effective_entry_count: int,
    distinct_entry_utc_days: int,
    top_entry_day_share_pct: float | None,
    entry_ts_missing_row_count: int,
    cfg: BlockedOutcomeReviewConfig,
) -> str | None:
    """候選 eligibility 檢定(預註冊 §3 E1-E3 + entry 身分完整性),回首個失敗原因。

    任一失敗 → cell 不得成 review candidate、不得進 BH family(§3.4:禁止方向性
    結論,唯一合法行動 = 繼續累積去重樣本)。
    """
    if effective_entry_count < cfg.min_effective_entries_per_side_cell:
        return "distinct_entry_effective_n_below_preregistered_threshold"
    if distinct_entry_utc_days < cfg.min_distinct_entry_utc_days:
        return "distinct_entry_utc_days_below_preregistered_min"
    if (
        top_entry_day_share_pct is not None
        and top_entry_day_share_pct > cfg.max_top_entry_day_share_pct
    ):
        return "top_day_entry_share_above_preregistered_max"
    if entry_ts_missing_row_count > 0:
        # 身分不可證的 row 已被排除出樣本;帶著被排除數據立案 = 選擇性抽樣,
        # fail-closed 直接擋候選。
        return "entry_ts_missing_rows_block_candidacy"
    return None


def _wrongful_block_score(
    *,
    effective_entry_count: int,
    avg_net_bps: float | None,
    net_positive_pct: float | None,
    sample_eligibility_ok: bool,
    cfg: BlockedOutcomeReviewConfig,
) -> float:
    """Rank review candidates without changing the conservative review gate.

    F1:sample_factor 改用非重疊 n_eff(除以預註冊門檻);raw row 數不再進排序
    分數。eligibility(§3 E1-E3)不過的 cell score=0 —— 單日 episode / 天數
    集中的偽複製形態不得靠高 avg 佔據排序榜首。
    """
    if avg_net_bps is None or net_positive_pct is None:
        return 0.0
    avg_margin = avg_net_bps - cfg.min_avg_net_bps
    pct_margin = net_positive_pct - cfg.min_net_positive_pct
    if not sample_eligibility_ok or avg_margin < 0.0 or pct_margin < 0.0:
        return 0.0
    sample_factor = min(
        2.0, effective_entry_count / cfg.min_effective_entries_per_side_cell
    )
    return avg_margin * (net_positive_pct / 100.0) * sample_factor


def _diagnose_cost_gate_escape(
    *,
    effective_entry_count: int,
    avg_net_bps: float | None,
    avg_gross_bps: float | None,
    net_positive_pct: float | None,
    review_candidate: bool,
    cfg: BlockedOutcomeReviewConfig,
) -> dict[str, Any]:
    """Classify blocked outcomes into the next profit-learning action.

    F1:樣本判準改用 distinct-entry n_eff,raw row 數不再參與。
    """
    if effective_entry_count < cfg.min_outcomes_per_side_cell:
        return {
            "learning_diagnosis": "SAMPLE_INSUFFICIENT",
            "cost_gate_escape_recommendation": (
                "continue_recording_same_side_cell_blocked_signal_outcomes"
            ),
            "edge_amplification_required": False,
            "false_negative_candidate": False,
        }

    if review_candidate:
        return {
            "learning_diagnosis": "FALSE_NEGATIVE_CANDIDATE_AFTER_COST",
            "cost_gate_escape_recommendation": (
                "operator_review_bounded_probe_authority_without_global_gate_lowering"
            ),
            "edge_amplification_required": False,
            "false_negative_candidate": True,
        }

    avg_net = avg_net_bps if avg_net_bps is not None else 0.0
    avg_gross = avg_gross_bps if avg_gross_bps is not None else 0.0
    net_positive = net_positive_pct if net_positive_pct is not None else 0.0
    if avg_gross > 0.0 and avg_net < cfg.min_avg_net_bps:
        return {
            "learning_diagnosis": "GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT",
            "cost_gate_escape_recommendation": (
                "amplify_edge_or_reduce_friction_for_same_side_cell"
            ),
            "edge_amplification_required": True,
            "false_negative_candidate": False,
        }
    if avg_net >= cfg.min_avg_net_bps and net_positive < cfg.min_net_positive_pct:
        return {
            "learning_diagnosis": "POSITIVE_EDGE_UNSTABLE_AFTER_COST",
            "cost_gate_escape_recommendation": (
                "add_regime_filter_or_matched_controls_before_probe_review"
            ),
            "edge_amplification_required": True,
            "false_negative_candidate": False,
        }
    return {
        "learning_diagnosis": "BLOCK_CONFIRMED_AFTER_COST",
        "cost_gate_escape_recommendation": (
            "keep_cost_gate_blocked_or_archive_until_new_evidence"
        ),
        "edge_amplification_required": False,
        "false_negative_candidate": False,
    }


def _optimistic_side_cell_key(side_cell_key: str) -> str:
    """side_cell_key = strategy|SYMBOL|Side → edge_estimates 的 strategy::symbol 頂層鍵。"""
    parts = side_cell_key.split("|")
    if len(parts) >= 2:
        return f"{parts[0]}::{parts[1].upper()}"
    return side_cell_key


def _review_side_cell_rows(
    side_cell_key: str,
    rows: list[dict[str, Any]],
    *,
    cfg: BlockedOutcomeReviewConfig,
    censored_count: int = 0,
    edge_estimates: dict[str, dict[str, Any]] | None = None,
    expected_slippage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    edge_estimates = edge_estimates or {}
    # --- raw row 面:僅供觀測量/資料品質/legacy 檢查/K 登記。F1 硬規則:raw
    # outcome_count 一律不得進 eligibility / t 檢定 / BH-FDR。 ---
    valid_rows: list[dict[str, Any]] = []
    horizon_counts: dict[int, int] = {}
    cost_model_version_counts: dict[str, int] = {}
    symbols = set()
    strategies = set()
    sides = set()
    latest = None
    for row in rows:
        net = _float(row.get("realized_net_bps"))
        if net is None:
            continue
        valid_rows.append(row)
        horizon = _int(row.get("horizon_minutes"), default=0)
        if horizon > 0:
            horizon_counts[horizon] = horizon_counts.get(horizon, 0) + 1
        # P1-2a:舊 row 缺 cost_model_version → legacy_optimistic_v0(樂觀成本,不可立案)。
        version = _str(row.get("cost_model_version")) or "legacy_optimistic_v0"
        cost_model_version_counts[version] = cost_model_version_counts.get(version, 0) + 1
        symbol = _str(row.get("symbol")).upper()
        strategy = _str(row.get("strategy_name"))
        side = _str(row.get("side"))
        if symbol:
            symbols.add(symbol)
        if strategy:
            strategies.add(strategy)
        if side:
            sides.add(side)
        if latest is None or _row_sort_ts(row) >= _row_sort_ts(latest):
            latest = row

    outcome_count = len(valid_rows)

    # --- F1 去重面:非重疊 distinct-entry 有效觀測 = eligibility/t/BH 唯一合法樣本。 ---
    dedup = _effective_entries(valid_rows, expected_slippage=expected_slippage)
    entries = dedup["entries"]
    entry_ts_missing_row_count = dedup["entry_ts_missing_row_count"]
    distinct_entry_observation_count = dedup["distinct_entry_observation_count"]
    window_overlap_excluded_entry_count = dedup["window_overlap_excluded_entry_count"]
    replica_inconsistent_group_count = dedup["replica_inconsistent_group_count"]
    distinct_entry_utc_days = dedup["distinct_entry_utc_days"]
    top_entry_utc_day = dedup["top_entry_utc_day"]
    top_entry_day_share_pct = dedup["top_entry_day_share_pct"]
    effective_entry_count = len(entries)
    # 去重壓縮掉的 raw 副本數(unknown 桶 row 另計 entry_ts_missing_row_count)。
    duplicate_outcome_row_count = (
        outcome_count - entry_ts_missing_row_count - distinct_entry_observation_count
    )

    conservative_nets = [e["net_conservative"] for e in entries]
    optimistic_nets = [e["net_optimistic"] for e in entries]
    expected_track_on = expected_slippage is not None
    # 成本雙軌主判:實測 E[cost] 軌可用 → 主判用它;否則 fail-closed 回退保守軌。
    if expected_track_on:
        nets = [e["net_expected"] for e in entries]
        cost_basis_main = "expected_slippage_mean_abs_v1"
    else:
        nets = list(conservative_nets)
        cost_basis_main = "conservative_v1"
    gross_values = [e["gross_bps"] for e in entries if e["gross_bps"] is not None]
    cost_values = [e["cost_bps"] for e in entries if e["cost_bps"] is not None]
    expected_cost_values = [
        e["expected_cost_bps"] for e in entries if e["expected_cost_bps"] is not None
    ]
    # 預註冊 §6.2 尾部敏感性欄(CVaR90,並列輸出不作主判):loss-budget/敘事上限用。
    tail_nets = [e["net_tail"] for e in entries if e["net_tail"] is not None]
    tail_cost_values = [
        e["tail_cost_bps"] for e in entries if e["tail_cost_bps"] is not None
    ]
    mean_net_tail = _mean(tail_nets)
    net_tail_positive_pct = (
        sum(1 for value in tail_nets if value > 0.0) / len(tail_nets) * 100.0
        if tail_nets
        else None
    )

    positive_count = sum(1 for value in nets if value > 0.0)
    gross_positive_count = sum(1 for value in gross_values if value > 0.0)
    avg_net = _mean(nets)
    # 樣本標準差(ddof=1)供 BH-FDR 單側 t 檢定用;n_eff<2 無法估變異數。
    std_net = None
    if effective_entry_count >= 2 and avg_net is not None:
        variance = sum((value - avg_net) ** 2 for value in nets) / (
            effective_entry_count - 1
        )
        std_net = math.sqrt(variance)
    # 資料完整性疑點(預註冊 §2.3 複本不一致 / §4 V=0):去重+非重疊後樣本仍
    # 全同值 = 去重逃逸嫌疑(連續價格下 distinct entry 的 markout 幾乎不可能
    # 全同;F1 攻擊面正是全同值複製)。疑點 cell 排除出檢定 family:不給 p、
    # 不進 BH、不得成候選 —— 靜默收下會把資料缺陷洗成 p=0 的偽顯著。
    zero_variance_suspect = bool(
        effective_entry_count >= 2 and std_net is not None and std_net == 0.0
    )
    data_integrity_suspect = bool(
        replica_inconsistent_group_count > 0 or zero_variance_suspect
    )
    # 候選 eligibility(預註冊 §3 E1-E3 + entry 身分完整性)。
    sample_eligibility_failure = _sample_eligibility_failure_reason(
        effective_entry_count=effective_entry_count,
        distinct_entry_utc_days=distinct_entry_utc_days,
        top_entry_day_share_pct=top_entry_day_share_pct,
        entry_ts_missing_row_count=entry_ts_missing_row_count,
        cfg=cfg,
    )
    sample_eligibility_ok = bool(
        sample_eligibility_failure is None and not data_integrity_suspect
    )
    # F7:censored_pct = censored / (有效 raw + censored)。>30% → 資料品質先於統計顯著。
    total_with_censored = outcome_count + censored_count
    censored_pct = (
        censored_count / total_with_censored * 100.0 if total_with_censored else 0.0
    )
    observation_gap_suspect = censored_pct > 30.0
    net_positive_pct = (
        positive_count / effective_entry_count * 100.0 if effective_entry_count else None
    )
    min_net = min(nets) if nets else None
    max_net = max(nets) if nets else None
    avg_gross = _mean(gross_values)
    avg_cost = _mean(cost_values)
    gross_positive_pct = (
        gross_positive_count / len(gross_values) * 100.0
        if gross_values
        else None
    )
    # 保守軌敏感性欄(並列輸出,不作主判):CVaR 類尾部成本(q75×1.3)下的平行結論。
    avg_net_conservative = _mean(conservative_nets)
    conservative_positive_pct = (
        sum(1 for value in conservative_nets if value > 0.0)
        / effective_entry_count
        * 100.0
        if effective_entry_count
        else None
    )
    conservative_tail_would_clear_thresholds = bool(
        effective_entry_count >= cfg.min_outcomes_per_side_cell
        and sample_eligibility_ok
        and avg_net_conservative is not None
        and avg_net_conservative >= cfg.min_avg_net_bps
        and conservative_positive_pct is not None
        and conservative_positive_pct >= cfg.min_net_positive_pct
    )
    net_cost_cushion_bps = (
        avg_net - cfg.min_avg_net_bps
        if avg_net is not None
        else None
    )
    net_positive_margin_pct = (
        net_positive_pct - cfg.min_net_positive_pct
        if net_positive_pct is not None
        else None
    )
    # F1:sample margin 改以 n_eff 對預註冊門檻計。
    sample_margin_count = (
        effective_entry_count - cfg.min_effective_entries_per_side_cell
    )
    wrongful_block_score = _wrongful_block_score(
        effective_entry_count=effective_entry_count,
        avg_net_bps=avg_net,
        net_positive_pct=net_positive_pct,
        sample_eligibility_ok=sample_eligibility_ok,
        cfg=cfg,
    )
    dominant_horizon = None
    if horizon_counts:
        dominant_horizon = sorted(
            horizon_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[0][0]

    # P1-2a:含 legacy_optimistic_v0 row 的 cell 數字被樂觀成本污染,不可用於立案。
    legacy_optimistic_present = cost_model_version_counts.get("legacy_optimistic_v0", 0) > 0
    if observation_gap_suspect:
        # F7:資料品質缺陷先於統計顯著;高 censored 比例不得為 review candidate。
        status = "OBSERVATION_GAP_SUSPECT"
        reason = "censored_pct_above_30_data_quality_before_significance"
        review_candidate = False
    elif data_integrity_suspect:
        # 預註冊 §2.3/§4:複本值不一致或零變異數樣本 → 資料完整性先於統計;
        # 排除出檢定 family,不得靜默平均或收下 p=0 偽顯著。
        status = "DATA_INTEGRITY_SUSPECT"
        reason = (
            "replica_values_inconsistent_within_entry_group"
            if replica_inconsistent_group_count > 0
            else "zero_variance_effective_sample_dedup_escape_suspect"
        )
        review_candidate = False
    elif effective_entry_count < cfg.min_outcomes_per_side_cell:
        status = "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
        reason = "side_cell_below_min_blocked_outcome_sample"
        review_candidate = False
    elif legacy_optimistic_present:
        status = "LEGACY_OPTIMISTIC_COST_UNBACKFILLED"
        reason = "cell_contains_legacy_optimistic_cost_rows_not_candidacy_eligible"
        review_candidate = False
    elif (
        avg_net is not None
        and avg_net >= cfg.min_avg_net_bps
        and net_positive_pct is not None
        and net_positive_pct >= cfg.min_net_positive_pct
    ):
        if sample_eligibility_failure is not None:
            # F1:過線但預註冊 eligibility(E1 n_eff floor / E2 distinct days /
            # E3 top-day share / entry 身分完整性)未達 → 不得成候選。這正是
            # 偽複製免疫的硬門(NEAR 候選 5058 行 n_eff≈1-2 + 單日 episode 在
            # 此被攔;近似複製同分鐘 distinct-ms 亦同)。
            status = "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT"
            reason = sample_eligibility_failure
            review_candidate = False
        else:
            status = "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
            reason = "blocked_signal_markouts_clear_review_thresholds"
            review_candidate = True
    else:
        status = "KEEP_COST_GATE_BLOCKED"
        reason = "blocked_signal_markouts_do_not_clear_review_thresholds"
        review_candidate = False

    # P1-2c:candidacy_flipped_by_cost_model = 樂觀成本過線但主判成本不過的 cell。
    avg_opt = _mean(optimistic_nets)
    opt_positive_pct = (
        sum(1 for v in optimistic_nets if v > 0.0) / effective_entry_count * 100.0
        if effective_entry_count
        else None
    )
    would_pass_optimistic = (
        effective_entry_count >= cfg.min_outcomes_per_side_cell
        and sample_eligibility_ok
        and avg_opt is not None
        and avg_opt >= cfg.min_avg_net_bps
        and opt_positive_pct is not None
        and opt_positive_pct >= cfg.min_net_positive_pct
    )
    candidacy_flipped_by_cost_model = bool(would_pass_optimistic and not review_candidate)

    # F1 fix(c):realized 矛盾標記。反事實 avg 遠高於 realized cell EV(且 realized 為負、
    # n≥10)代表 fill-at-signal-price 高估執行,不得進 candidate,改標 EXECUTION_REALISM_SUSPECT。
    edge = edge_estimates.get(_optimistic_side_cell_key(side_cell_key))
    realized_cell_ev_bps = _float(edge.get("realized_ev_bps")) if edge else None
    if realized_cell_ev_bps is None and edge:
        realized_cell_ev_bps = _float(edge.get("ev_bps"))
    realized_cell_n = _int(edge.get("n"), default=0) if edge else 0
    gap = (
        avg_net - realized_cell_ev_bps
        if (avg_net is not None and realized_cell_ev_bps is not None)
        else None
    )
    realized_contradiction = bool(
        realized_cell_n >= 10
        and realized_cell_ev_bps is not None
        and realized_cell_ev_bps < 0.0
        and gap is not None
        and gap > 50.0
    )
    if realized_contradiction:
        status = "EXECUTION_REALISM_SUSPECT"
        reason = "counterfactual_avg_contradicts_negative_realized_cell_ev"
        review_candidate = False

    if status == "DATA_INTEGRITY_SUSPECT":
        # 資料完整性疑點:統計結論(含 BLOCK_CONFIRMED)一律不給,先修資料。
        diagnosis = {
            "learning_diagnosis": "DATA_INTEGRITY_SUSPECT",
            "cost_gate_escape_recommendation": (
                "audit_ledger_entry_replica_consistency_before_statistics"
            ),
            "edge_amplification_required": False,
            "false_negative_candidate": False,
        }
    elif status == "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT":
        # F1:過線但預註冊 eligibility 未達的 cell,誠實診斷 = 有效樣本不足,
        # 不得落 BLOCK_CONFIRMED(會誤導成「已證實無 edge」)。
        diagnosis = {
            "learning_diagnosis": "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT",
            "cost_gate_escape_recommendation": (
                "continue_recording_distinct_entry_blocked_signal_outcomes"
            ),
            "edge_amplification_required": False,
            "false_negative_candidate": False,
        }
    else:
        diagnosis = _diagnose_cost_gate_escape(
            effective_entry_count=effective_entry_count,
            avg_net_bps=avg_net,
            avg_gross_bps=avg_gross,
            net_positive_pct=net_positive_pct,
            review_candidate=review_candidate,
            cfg=cfg,
        )

    return {
        "side_cell_key": side_cell_key,
        "status": status,
        "reason": reason,
        **diagnosis,
        "review_candidate": review_candidate,
        "outcome_count": outcome_count,
        # F1:非重疊 distinct-entry 有效觀測數 n_eff(eligibility/t/BH 的唯一合法 n)。
        "effective_entry_count": effective_entry_count,
        # 去重後(分鐘量化)觀測數與非重疊窗排除數 —— 審計對照欄,不進檢定。
        "distinct_entry_observation_count": distinct_entry_observation_count,
        "window_overlap_excluded_entry_count": window_overlap_excluded_entry_count,
        "duplicate_outcome_row_count": duplicate_outcome_row_count,
        "entry_ts_missing_row_count": entry_ts_missing_row_count,
        # 預註冊 §2.3/§4 資料完整性欄。
        "replica_inconsistent_group_count": replica_inconsistent_group_count,
        "zero_variance_suspect": zero_variance_suspect,
        "data_integrity_suspect": data_integrity_suspect,
        # 預註冊 §3 E2/E3 天數分布欄(checklist 攔截用,per 入選 entry)。
        "distinct_entry_utc_days": distinct_entry_utc_days,
        "entry_day_counts": dedup["entry_day_counts"],
        "top_entry_utc_day": top_entry_utc_day,
        "top_entry_day_share_pct": top_entry_day_share_pct,
        "sample_eligibility_ok": sample_eligibility_ok,
        "sample_eligibility_failure_reason": sample_eligibility_failure,
        "positive_outcome_count": positive_count,
        "gross_positive_outcome_count": gross_positive_count,
        "avg_net_bps": avg_net,
        "avg_gross_bps": avg_gross,
        "avg_cost_bps": avg_cost,
        "min_net_bps": min_net,
        "max_net_bps": max_net,
        "net_positive_pct": net_positive_pct,
        "gross_positive_pct": gross_positive_pct,
        "net_cost_cushion_bps": net_cost_cushion_bps,
        "net_positive_margin_pct": net_positive_margin_pct,
        "sample_margin_count": sample_margin_count,
        "wrongful_block_score": wrongful_block_score,
        "std_net_bps": std_net,
        # 疑點 cell 不給 p(預註冊 §4:V=0 / 複本不一致不得產生 p=0 偽顯著)。
        "one_sided_t_p_value": one_sided_t_p_value(
            avg_net or 0.0, std_net, effective_entry_count
        )
        if effective_entry_count >= cfg.min_outcomes_per_side_cell
        and std_net is not None
        and not data_integrity_suspect
        else None,
        # 預註冊 §5.1:BH family = 通過 eligibility 的 cells;family 外 cell 的
        # p 僅供透明對照,不得參與 step-up(family 灌水會雙向失真)。
        "bh_family_eligible": bool(
            sample_eligibility_ok
            and not observation_gap_suspect
            and not legacy_optimistic_present
        ),
        "bh_fdr_pass": None,
        # WP-A.2 成本雙軌:主判軌標記 + 實測/尾部/保守三面並列欄。
        "cost_basis_main": cost_basis_main,
        "avg_expected_cost_bps": (
            _mean(expected_cost_values) if expected_track_on else None
        ),
        "avg_net_bps_expected": avg_net if expected_track_on else None,
        "net_positive_pct_expected": net_positive_pct if expected_track_on else None,
        # 預註冊 §6.2 尾部欄(CVaR90;cvar90 缺失 fallback q90,tail_metric 記名)。
        "mean_net_tail": mean_net_tail,
        "net_tail_positive_pct": net_tail_positive_pct,
        "avg_tail_cost_bps": _mean(tail_cost_values),
        "tail_metric": dedup["tail_metric"],
        "avg_net_bps_conservative": avg_net_conservative,
        "net_positive_pct_conservative": conservative_positive_pct,
        "conservative_tail_would_clear_thresholds": (
            conservative_tail_would_clear_thresholds
        ),
        "censored_count": censored_count,
        "censored_pct": censored_pct,
        "observation_gap_suspect": observation_gap_suspect,
        "cost_model_version_counts": {
            key: cost_model_version_counts[key]
            for key in sorted(cost_model_version_counts)
        },
        "legacy_optimistic_cost_present": legacy_optimistic_present,
        "candidacy_flipped_by_cost_model": candidacy_flipped_by_cost_model,
        "avg_net_bps_optimistic": avg_opt,
        "realized_cell_ev_bps": realized_cell_ev_bps,
        "realized_cell_n": realized_cell_n,
        "counterfactual_vs_realized_gap_bps": gap,
        "realized_contradiction": realized_contradiction,
        "horizon_minutes": sorted(horizon_counts),
        "horizon_counts": {
            str(key): horizon_counts[key]
            for key in sorted(horizon_counts)
        },
        "dominant_horizon_minutes": dominant_horizon,
        "min_outcomes_per_side_cell": cfg.min_outcomes_per_side_cell,
        "min_effective_entries_per_side_cell": (
            cfg.min_effective_entries_per_side_cell
        ),
        "min_distinct_entry_utc_days": cfg.min_distinct_entry_utc_days,
        "max_top_entry_day_share_pct": cfg.max_top_entry_day_share_pct,
        "min_avg_net_bps": cfg.min_avg_net_bps,
        "min_net_positive_pct": cfg.min_net_positive_pct,
        "strategy_names": sorted(strategies),
        "symbols": sorted(symbols),
        "sides": sorted(sides),
        "latest_generated_at_utc": latest.get("generated_at_utc") if latest else None,
        "latest_attempt_id": latest.get("attempt_id") if latest else None,
        "promotion_evidence": False,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
    }


def _apply_bh_fdr(side_cells: list[dict[str, Any]], *, cfg: BlockedOutcomeReviewConfig) -> None:
    """P2-8(b):對 n_eff≥min 的 cell family 跑 BH-FDR(q),把 bh_fdr_pass 寫回 cell。

    review_candidate 再加一條 BH pass(fail-closed:BH 只會撤下不會扶正)。誠實預期:
    當前樣本(median n 小、σ≈200)幾乎必然零通過 —— 這是正確結果,未過 BH 的 cell
    只可作 exploration 排序,不得以「false-negative 證據」語言呈現。
    F1:p 值一律來自非重疊 distinct-entry 樣本(raw row 數已不可能進到這裡);
    family 限通過預註冊 eligibility 的 cells(§5.1)—— 不合格 cell 的 p 混入
    step-up 會雙向失真(低 p 垃圾 cell 可扶正邊緣候選,高 p 灌水可誤撤)。
    """
    eligible = [
        cell
        for cell in side_cells
        if cell.get("bh_family_eligible")
        and cell.get("one_sided_t_p_value") is not None
    ]
    if not eligible:
        return
    p_values = [float(cell["one_sided_t_p_value"]) for cell in eligible]
    passed = bh_fdr_pass(p_values, cfg.fdr_q)
    for cell, ok in zip(eligible, passed):
        cell["bh_fdr_pass"] = bool(ok)
        if cell.get("review_candidate") and not ok:
            # BH 未過 → 撤下候選資格,改標 exploration;診斷/推薦欄同步重算以保持 packet
            # 內部一致(否則 learning_diagnosis 仍殘留 FALSE_NEGATIVE_CANDIDATE)。
            cell["review_candidate"] = False
            cell["status"] = "EXPLORATION_CANDIDATE_BH_FDR_NOT_PASSED"
            cell["reason"] = "cleared_conservative_thresholds_but_failed_bh_fdr"
            rediagnosis = _diagnose_cost_gate_escape(
                effective_entry_count=int(cell.get("effective_entry_count") or 0),
                avg_net_bps=cell.get("avg_net_bps"),
                avg_gross_bps=cell.get("avg_gross_bps"),
                net_positive_pct=cell.get("net_positive_pct"),
                review_candidate=False,
                cfg=cfg,
            )
            cell.update(rediagnosis)


def _apply_overlay(row: dict[str, Any], overlay: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """P1-2c:legacy_optimistic row 有 overlay 時,用保守成本覆蓋計算(不改原 ledger)。

    僅覆蓋 realized_net_bps/cost_bps 並打上 conservative version 標記;無 overlay 的
    legacy row 保持 legacy_optimistic_v0,由 cell 級 legacy 判準攔候選。
    """
    if not overlay or _str(row.get("cost_model_version")):
        return row
    hit = overlay.get(_str(row.get("attempt_id")))
    if not hit:
        return row
    patched = dict(row)
    patched["realized_net_bps"] = hit.get("realized_net_bps_conservative")
    patched["cost_bps"] = hit.get("cost_bps_conservative")
    patched["cost_model_version"] = hit.get("cost_model_version") or "conservative_v1"
    patched["cost_model_source"] = hit.get("cost_model_source")
    patched["cost_backfilled_by_overlay"] = True
    return patched

def _evaluate_candidate_cohort(
    side_cell_key: str,
    rows: list[dict[str, Any]],
    *,
    cfg: BlockedOutcomeReviewConfig,
    overlay: dict[str, dict[str, Any]],
    edge_estimates: dict[str, dict[str, Any]],
    expected_slippage: dict[str, Any] | None,
) -> dict[str, Any]:
    """Adapt the existing outcome methodology to the candidate-board Interface."""
    censored_count = sum(row.get("censored") is True for row in rows)
    uncensored_row_count = len(rows) - censored_count
    review_rows = [
        _apply_overlay(row, overlay)
        for row in rows
        if row.get("censored") is not True
    ]
    metrics = _review_side_cell_rows(
        side_cell_key,
        review_rows,
        cfg=cfg,
        censored_count=censored_count,
        edge_estimates=edge_estimates,
        expected_slippage=expected_slippage,
    )
    valid_review_rows = [
        row
        for row in review_rows
        if _float(row.get("realized_net_bps")) is not None
    ]
    entries = _effective_entries(
        valid_review_rows,
        expected_slippage=expected_slippage,
    )["entries"]
    return {
        "censored_count": censored_count,
        "uncensored_row_count": uncensored_row_count,
        "metrics": metrics,
        "entries": entries,
    }


def _build_learning_candidate_board(
    ledger_rows: list[dict[str, Any]],
    *,
    cfg: BlockedOutcomeReviewConfig,
    overlay: dict[str, dict[str, Any]],
    edge_estimates: dict[str, dict[str, Any]],
    expected_slippage: dict[str, Any] | None,
    as_of_date: dt.date,
) -> dict[str, Any]:
    """Compatibility façade for the extracted candidate-board Module."""
    return build_learning_candidate_board(
        ledger_rows,
        cfg=cfg,
        overlay=overlay,
        edge_estimates=edge_estimates,
        expected_slippage=expected_slippage,
        as_of_date=as_of_date,
        cohort_evaluator=_evaluate_candidate_cohort,
    )


def build_blocked_signal_outcome_review(
    ledger_rows: list[dict[str, Any]],
    *,
    now_utc: dt.datetime | None = None,
    cfg: BlockedOutcomeReviewConfig | None = None,
    overlay: dict[str, dict[str, Any]] | None = None,
    edge_estimates: dict[str, dict[str, Any]] | None = None,
    slippage_quantiles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a conservative scorecard from blocked-signal outcome rows.

    overlay: P1-2c 回填 overlay(attempt_id → 保守成本重算),覆蓋 legacy 樂觀成本 row。
    edge_estimates: F1 fix(c) realized 矛盾標記所需的 side-cell realized EV/n(strategy::symbol)。
    slippage_quantiles: WP-A.2 成本雙軌 — slippage_quantile_artifact payload;可用時
      主判改用實測 E[cost](mean_abs),conservative_v1 降為敏感性欄;缺失/過期則主判
      fail-closed 回退 conservative_v1(與 v3 行為一致)。
    """
    cfg = cfg or BlockedOutcomeReviewConfig()
    validate_blocked_outcome_review_config(cfg)
    overlay = overlay or {}
    edge_estimates = edge_estimates or {}
    generated_at = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    expected_slippage = _load_expected_slippage(slippage_quantiles, now=generated_at)

    grouped: dict[str, list[dict[str, Any]]] = {}
    censored_grouped: dict[str, int] = {}
    invalid_outcome_row_count = 0
    for raw_row in ledger_rows:
        if _str(raw_row.get("record_type")) != BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE:
            continue
        side_cell_key = _str(raw_row.get("side_cell_key"))
        if not side_cell_key:
            invalid_outcome_row_count += 1
            continue
        # F7:censored row 保留分母資訊但不進 nets/檢定。realized_net_bps 缺失但
        # censored=true 屬合法(觀測斷供),計入 censored_count;非 censored 且無 net 才算畸形。
        if raw_row.get("censored") is True:
            censored_grouped[side_cell_key] = censored_grouped.get(side_cell_key, 0) + 1
            grouped.setdefault(side_cell_key, [])
            continue
        row = _apply_overlay(raw_row, overlay)
        net_bps = _float(row.get("realized_net_bps"))
        if net_bps is None:
            invalid_outcome_row_count += 1
            continue
        grouped.setdefault(side_cell_key, []).append(row)

    side_cells = [
        _review_side_cell_rows(
            key,
            rows,
            cfg=cfg,
            censored_count=censored_grouped.get(key, 0),
            edge_estimates=edge_estimates,
            expected_slippage=expected_slippage,
        )
        for key, rows in sorted(grouped.items())
    ]
    # P2-8(b):候選面 BH-FDR(q=cfg.fdr_q)。對每個 n_eff≥min 的 cell 單側 t-test p,
    # step-up 通過集決定 bh_pass;review_candidate 資格再加 BH pass 一條(fail-closed)。
    _apply_bh_fdr(side_cells, cfg=cfg)
    side_cells = sorted(
        side_cells,
        key=lambda row: (
            0 if row["review_candidate"] else 1,
            -float(row.get("wrongful_block_score") or 0.0),
            -int(row.get("effective_entry_count") or 0),
            -float(row.get("avg_net_bps") or -10_000.0),
            row["side_cell_key"],
        ),
    )
    candidate_rank = 0
    for rank, row in enumerate(side_cells, start=1):
        row["review_rank"] = rank
        if row["review_candidate"]:
            candidate_rank += 1
            row["bounded_demo_probe_review_rank"] = candidate_rank
        else:
            row["bounded_demo_probe_review_rank"] = None

    # P2-8(a):K 登記(無條件)。horizon 維度納入同一 family(m=cells×horizons)。
    horizon_set = {
        horizon
        for rows in grouped.values()
        for row in rows
        for horizon in (_int(row.get("horizon_minutes"), default=0),)
        if horizon > 0
    }
    n_horizons = len(horizon_set) or 1
    selection_universe = {
        "n_side_cells": len(side_cells),
        "n_horizons": n_horizons,
        "k_effective": len(side_cells) * n_horizons,
        "selection_metric": "wrongful_block_score",
        "fdr_q": cfg.fdr_q,
    }
    # P2-8(c):headline sign-flip selection test。F1:cell nets 一律取 distinct-entry
    # 去重後的主判軌淨值(raw row 複製不再灌水 null 分布與 observed best)。
    eligible_nets: list[list[float]] = []
    for rows in grouped.values():
        cell_entries = _effective_entries(rows, expected_slippage=expected_slippage)[
            "entries"
        ]
        if expected_slippage is not None:
            cell_nets = [e["net_expected"] for e in cell_entries]
        else:
            cell_nets = [e["net_conservative"] for e in cell_entries]
        cell_nets = [v for v in cell_nets if v is not None]
        if len(cell_nets) >= cfg.min_outcomes_per_side_cell:
            eligible_nets.append(cell_nets)
    signflip = sign_flip_selection_p_value(eligible_nets, b=cfg.sign_flip_b)
    pooled_std = None
    all_nets = [v for c in eligible_nets for v in c]
    if len(all_nets) >= 2:
        pooled_mean = sum(all_nets) / len(all_nets)
        pooled_std = math.sqrt(
            sum((v - pooled_mean) ** 2 for v in all_nets) / (len(all_nets) - 1)
        )
    mean_n = (
        sum(len(c) for c in eligible_nets) / len(eligible_nets) if eligible_nets else 0.0
    )
    headline_selection = {
        "method": "sign_flip",
        "p_selection": signflip["p_selection"],
        "observed_best_avg_net_bps": signflip["observed_best"],
        "b": signflip["b"],
        "k": signflip["k"],
        "expected_max_under_null_bps": (
            expected_max_under_null_bps(pooled_std or 0.0, signflip["k"], mean_n)
            if pooled_std is not None
            else None
        ),
        "headline_edge_language_allowed": bool(signflip["p_selection"] < 0.05),
    }

    candidate_count = sum(1 for row in side_cells if row["review_candidate"])
    # F1:EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT 語義上同屬「樣本不足,繼續累積」,
    # 併入 insufficient 計數讓 packet 下一步落在 continue_recording 而非誤判定案。
    insufficient_count = sum(
        1 for row in side_cells
        if row["status"] in (
            "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES",
            "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT",
        )
    )
    blocked_count = sum(
        1 for row in side_cells
        if row["status"] == "KEEP_COST_GATE_BLOCKED"
    )
    outcome_count = sum(int(row.get("outcome_count") or 0) for row in side_cells)
    effective_entry_total = sum(
        int(row.get("effective_entry_count") or 0) for row in side_cells
    )
    distinct_entry_observation_total = sum(
        int(row.get("distinct_entry_observation_count") or 0) for row in side_cells
    )
    duplicate_outcome_row_total = sum(
        int(row.get("duplicate_outcome_row_count") or 0) for row in side_cells
    )
    window_overlap_excluded_total = sum(
        int(row.get("window_overlap_excluded_entry_count") or 0) for row in side_cells
    )
    entry_ts_missing_row_total = sum(
        int(row.get("entry_ts_missing_row_count") or 0) for row in side_cells
    )
    positive_count = sum(int(row.get("positive_outcome_count") or 0) for row in side_cells)
    # F1:packet 級 avg / positive pct 以 n_eff 加權(raw 行數不再灌水總平均)。
    avg_net = (
        sum(
            float(row["avg_net_bps"]) * int(row["effective_entry_count"])
            for row in side_cells
            if row.get("avg_net_bps") is not None
        )
        / effective_entry_total
        if effective_entry_total
        else None
    )
    net_positive_pct = (
        positive_count / effective_entry_total * 100.0 if effective_entry_total else None
    )
    top_side_cell = side_cells[0] if side_cells else None
    top_candidate = next(
        (row for row in side_cells if row["review_candidate"]),
        None,
    )
    max_wrongful_block_score = (
        max(float(row.get("wrongful_block_score") or 0.0) for row in side_cells)
        if side_cells
        else 0.0
    )
    diagnosis_counts: dict[str, int] = {}
    recommendation_counts: dict[str, int] = {}
    false_negative_candidate_count = 0
    edge_amplification_required_side_cell_count = 0
    candidacy_flipped_by_cost_model_count = 0
    realized_contradiction_count = 0
    observation_gap_suspect_count = 0
    data_integrity_suspect_count = 0
    packet_cost_model_version_counts: dict[str, int] = {}
    for row in side_cells:
        if row.get("candidacy_flipped_by_cost_model") is True:
            candidacy_flipped_by_cost_model_count += 1
        if row.get("realized_contradiction") is True:
            realized_contradiction_count += 1
        if row.get("observation_gap_suspect") is True:
            observation_gap_suspect_count += 1
        if row.get("data_integrity_suspect") is True:
            data_integrity_suspect_count += 1
        for version, count in (row.get("cost_model_version_counts") or {}).items():
            packet_cost_model_version_counts[version] = (
                packet_cost_model_version_counts.get(version, 0) + count
            )
        diagnosis = _str(row.get("learning_diagnosis"))
        recommendation = _str(row.get("cost_gate_escape_recommendation"))
        if diagnosis:
            diagnosis_counts[diagnosis] = diagnosis_counts.get(diagnosis, 0) + 1
        if recommendation:
            recommendation_counts[recommendation] = (
                recommendation_counts.get(recommendation, 0) + 1
            )
        if row.get("false_negative_candidate") is True:
            false_negative_candidate_count += 1
        if row.get("edge_amplification_required") is True:
            edge_amplification_required_side_cell_count += 1

    if outcome_count == 0:
        status = "NO_BLOCKED_SIGNAL_OUTCOMES"
        reason = "blocked_signal_outcome_rows_missing"
        next_trigger = "run_cost_gate_outcome_refresh_for_blocked_signal_outcomes"
    elif candidate_count > 0:
        status = "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
        reason = "one_or_more_blocked_side_cells_clear_review_thresholds"
        next_trigger = "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
    elif insufficient_count > 0:
        status = "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
        reason = "blocked_signal_outcome_sample_below_review_threshold"
        next_trigger = "continue_recording_and_refreshing_blocked_signal_outcomes"
    else:
        status = "NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
        reason = "reviewed_blocked_side_cells_do_not_clear_thresholds"
        next_trigger = "keep_cost_gate_blocked_for_reviewed_side_cells"

    learning_candidate_board = _build_learning_candidate_board(
        ledger_rows,
        cfg=cfg,
        overlay=overlay,
        edge_estimates=edge_estimates,
        expected_slippage=expected_slippage,
        as_of_date=generated_at.date(),
    )
    return {
        "schema_version": BLOCKED_OUTCOME_REVIEW_SCHEMA_VERSION,
        "record_type": BLOCKED_OUTCOME_REVIEW_RECORD_TYPE,
        "generated_at_utc": generated_at.isoformat(),
        "status": status,
        "reason": reason,
        "next_trigger": next_trigger,
        "side_cell_count": len(side_cells),
        "review_candidate_side_cell_count": candidate_count,
        "insufficient_sample_side_cell_count": insufficient_count,
        "keep_blocked_side_cell_count": blocked_count,
        "blocked_signal_outcome_count": outcome_count,
        "blocked_signal_effective_entry_count": effective_entry_total,
        "blocked_signal_distinct_entry_observation_count": (
            distinct_entry_observation_total
        ),
        "blocked_signal_duplicate_outcome_row_count": duplicate_outcome_row_total,
        "blocked_signal_window_overlap_excluded_entry_count": (
            window_overlap_excluded_total
        ),
        "blocked_signal_entry_ts_missing_row_count": entry_ts_missing_row_total,
        "blocked_signal_positive_outcome_count": positive_count,
        "invalid_outcome_row_count": invalid_outcome_row_count,
        "avg_blocked_signal_outcome_net_bps": avg_net,
        "blocked_signal_net_positive_pct": net_positive_pct,
        "max_wrongful_block_score": max_wrongful_block_score,
        # WP-A.2 成本雙軌:主判軌標記 + artifact 可用性(消費端可核對主判基礎)。
        "cost_basis_main": (
            "expected_slippage_mean_abs_v1"
            if expected_slippage is not None
            else "conservative_v1"
        ),
        "expected_cost_artifact": {
            "available": expected_slippage is not None,
            "asof": expected_slippage.get("asof") if expected_slippage else None,
            "source_asof_utc": (
                expected_slippage.get("asof") if expected_slippage else None
            ),
            "source_payload_sha256": (
                expected_slippage.get("source_payload_sha256")
                if expected_slippage
                else None
            ),
            "source_payload": (
                expected_slippage.get("source_payload")
                if expected_slippage
                else None
            ),
            "normalized_projection": (
                expected_slippage.get("normalized_projection")
                if expected_slippage
                else None
            ),
            "normalized_projection_sha256": (
                expected_slippage.get("normalized_projection_sha256")
                if expected_slippage
                else None
            ),
            "global_mean_abs_bps": (
                expected_slippage.get("global_mean_abs") if expected_slippage else None
            ),
            "global_tail_bps": (
                expected_slippage.get("global_tail_bps") if expected_slippage else None
            ),
            "global_tail_metric": (
                expected_slippage.get("global_tail_metric")
                if expected_slippage
                else None
            ),
            "n_total_global": (
                expected_slippage.get("n_total_global") if expected_slippage else 0
            ),
            "max_age_hours": QUANTILE_ARTIFACT_MAX_AGE_HOURS,
        },
        "top_side_cell_key": top_side_cell.get("side_cell_key") if top_side_cell else None,
        "top_side_cell_status": top_side_cell.get("status") if top_side_cell else None,
        "top_side_cell_learning_diagnosis": (
            top_side_cell.get("learning_diagnosis") if top_side_cell else None
        ),
        "top_side_cell_cost_gate_escape_recommendation": (
            top_side_cell.get("cost_gate_escape_recommendation")
            if top_side_cell
            else None
        ),
        "top_side_cell_wrongful_block_score": (
            top_side_cell.get("wrongful_block_score") if top_side_cell else None
        ),
        "top_side_cell_net_cost_cushion_bps": (
            top_side_cell.get("net_cost_cushion_bps") if top_side_cell else None
        ),
        "top_review_candidate_side_cell_key": (
            top_candidate.get("side_cell_key") if top_candidate else None
        ),
        "top_review_candidate_learning_diagnosis": (
            top_candidate.get("learning_diagnosis") if top_candidate else None
        ),
        "top_review_candidate_cost_gate_escape_recommendation": (
            top_candidate.get("cost_gate_escape_recommendation")
            if top_candidate
            else None
        ),
        "top_review_candidate_wrongful_block_score": (
            top_candidate.get("wrongful_block_score") if top_candidate else None
        ),
        "top_review_candidate_net_cost_cushion_bps": (
            top_candidate.get("net_cost_cushion_bps") if top_candidate else None
        ),
        "thresholds": {
            "min_outcomes_per_side_cell": cfg.min_outcomes_per_side_cell,
            "min_effective_entries_per_side_cell": (
                cfg.min_effective_entries_per_side_cell
            ),
            "min_distinct_entry_utc_days": cfg.min_distinct_entry_utc_days,
            "max_top_entry_day_share_pct": cfg.max_top_entry_day_share_pct,
            "min_avg_net_bps": cfg.min_avg_net_bps,
            "min_net_positive_pct": cfg.min_net_positive_pct,
        },
        "diagnosis_counts": {
            key: diagnosis_counts[key] for key in sorted(diagnosis_counts)
        },
        "cost_gate_escape_recommendation_counts": {
            key: recommendation_counts[key]
            for key in sorted(recommendation_counts)
        },
        "false_negative_candidate_count": false_negative_candidate_count,
        "edge_amplification_required_side_cell_count": (
            edge_amplification_required_side_cell_count
        ),
        "selection_universe": selection_universe,
        "headline_selection": headline_selection,
        "candidacy_flipped_by_cost_model_count": candidacy_flipped_by_cost_model_count,
        "realized_contradiction_side_cell_count": realized_contradiction_count,
        "observation_gap_suspect_side_cell_count": observation_gap_suspect_count,
        "data_integrity_suspect_side_cell_count": data_integrity_suspect_count,
        "cost_model_version_counts": {
            key: packet_cost_model_version_counts[key]
            for key in sorted(packet_cost_model_version_counts)
        },
        "top_side_cells": side_cells[:16],
        "learning_candidate_board": learning_candidate_board,
        "promotion_evidence": False,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "boundary": (
            "blocked outcome review artifact only; proposes operator review at "
            "most; no PG, Bybit, order, config, risk, auth, runtime mutation, "
            "or main Cost Gate lowering"
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-outcomes-per-side-cell", type=int, default=3)
    # F1:distinct-entry n_eff 候選門檻(默認 30 = QC 預註冊 §3 E1 凍結值)。
    parser.add_argument("--min-effective-entries-per-side-cell", type=int, default=30)
    # 預註冊 §3 E2/E3 凍結值(distinct UTC days ≥5;top-day share ≤50%)。
    parser.add_argument("--min-distinct-entry-utc-days", type=int, default=5)
    parser.add_argument("--max-top-entry-day-share-pct", type=float, default=50.0)
    parser.add_argument("--min-avg-net-bps", type=float, default=0.0)
    parser.add_argument("--min-net-positive-pct", type=float, default=60.0)
    parser.add_argument("--fdr-q", type=float, default=0.10)
    parser.add_argument("--sign-flip-b", type=int, default=1000)
    # WP-A.2:slippage_quantile_artifact 路徑(實測 E[cost] 主判);缺省/檔案不存在
    # 則主判 fail-closed 回退 conservative_v1。
    parser.add_argument("--slippage-artifact", type=Path, default=None)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg = BlockedOutcomeReviewConfig(
        min_outcomes_per_side_cell=args.min_outcomes_per_side_cell,
        min_effective_entries_per_side_cell=args.min_effective_entries_per_side_cell,
        min_distinct_entry_utc_days=args.min_distinct_entry_utc_days,
        max_top_entry_day_share_pct=args.max_top_entry_day_share_pct,
        min_avg_net_bps=args.min_avg_net_bps,
        min_net_positive_pct=args.min_net_positive_pct,
        fdr_q=args.fdr_q,
        sign_flip_b=args.sign_flip_b,
    )
    validate_blocked_outcome_review_config(cfg)
    slippage_payload = None
    if args.slippage_artifact and args.slippage_artifact.exists():
        slippage_payload = json.loads(
            args.slippage_artifact.read_text(encoding="utf-8")
        )
    scorecard = build_blocked_signal_outcome_review(
        read_jsonl_ledger(args.ledger),
        cfg=cfg,
        slippage_quantiles=slippage_payload,
    )
    if args.output:
        _write_json(args.output, scorecard)
    if args.print_json or not args.output:
        print(json.dumps(scorecard, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
