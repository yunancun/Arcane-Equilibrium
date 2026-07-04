"""Artifact-only outcome writer for cost-gate demo-learning lane rows."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.contract import (
    ADAPTER_SCHEMA_VERSION,
    ADMIT_DECISION,
    BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    PROBE_ADMISSION_DECISION_RECORD_TYPE,
    PROBE_OUTCOME_RECORD_TYPE,
)
from cost_gate_learning_lane.cost_model import (
    LEGACY_OPTIMISTIC_COST_BPS,
    SlippageQuantileTable,
    conservative_cost_bps,
    funding_crossing_count,
)


# F7:出場觀測延遲上界。延遲 ≤ 25% horizon 時量測窗畸變有界且 exit_ts 已落盤可事後
# 加權；超過即語義不可救，寫 censored row。cap 30min、floor 5min。
def _max_exit_delay_ms(horizon_ms: int) -> int:
    return int(max(5 * 60_000, min(0.25 * horizon_ms, 30 * 60_000)))


@dataclass(frozen=True)
class ProbeOutcomeConfig:
    """Markout/outcome contract for already-admitted demo-learning probes.

    cost_bps 為樂觀常數對照(保留 4.0)；權威淨值走保守成本模型(cost_model.py)。
    slippage_quantiles = 分位 artifact payload(load_slippage_quantiles 的輸入)，
    None → 走 fallback 鏈的 toml_tier。
    """

    horizon_minutes: int = 60
    cost_bps: float = LEGACY_OPTIMISTIC_COST_BPS
    max_entry_delay_ms: int = 5 * 60_000
    funding_interval_hours: float = 8.0
    slippage_table: SlippageQuantileTable | None = None


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_dt(value: Any) -> dt.datetime | None:
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


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str:
    return str(value or "").strip()


def _side_cell_key(strategy_name: Any, symbol: Any, side: Any) -> str:
    return "|".join([_str(strategy_name), _str(symbol).upper(), _str(side)])


def _event_to_side_cell(event: dict[str, Any]) -> str:
    return _side_cell_key(
        event.get("strategy_name") or event.get("strategy"),
        event.get("symbol"),
        event.get("side"),
    )


def _ledger_side_cell(row: dict[str, Any]) -> str:
    if row.get("side_cell_key"):
        return _str(row.get("side_cell_key"))
    event = _dict(row.get("event"))
    if event:
        return _event_to_side_cell(event)
    return _side_cell_key(row.get("strategy_name"), row.get("symbol"), row.get("side"))


def _row_decision(row: dict[str, Any]) -> str:
    if row.get("decision"):
        return _str(row.get("decision"))
    decision = _dict(row.get("admission_decision"))
    return _str(decision.get("decision"))


def _row_ts_ms(row: dict[str, Any]) -> int:
    for key in ("ts_ms", "attempt_ts_ms", "generated_at_ms"):
        value = _int(row.get(key), default=0)
        if value > 0:
            return value
    event = _dict(row.get("event"))
    return _int(event.get("ts_ms"), default=0)


def _attempt_id(row: dict[str, Any]) -> str:
    event = _dict(row.get("event"))
    context_id = _str(event.get("context_id"))
    if context_id:
        return context_id
    signal_id = _str(event.get("signal_id"))
    if signal_id:
        return signal_id
    return "|".join([_ledger_side_cell(row), str(_row_ts_ms(row))])


def validate_outcome_config(cfg: ProbeOutcomeConfig) -> None:
    if cfg.horizon_minutes < 1 or cfg.horizon_minutes > 24 * 60:
        raise ValueError("--outcome-horizon-minutes must be in [1, 1440]")
    if cfg.cost_bps < 0.0 or cfg.cost_bps > 10_000.0:
        raise ValueError("--outcome-cost-bps must be in [0, 10000]")
    if cfg.max_entry_delay_ms < 0 or cfg.max_entry_delay_ms > 24 * 3_600_000:
        raise ValueError("--max-entry-delay-ms must be in [0, 86400000]")
    if not (0.0 < cfg.funding_interval_hours <= 24.0):
        raise ValueError("funding_interval_hours must be in (0, 24]")


def read_price_observations(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        rows = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed JSONL observation at {path}:{line_no}") from exc
            if isinstance(payload, dict):
                rows.append(payload)
        return rows
    payload = json.loads(text)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "klines", "observations", "prices"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    raise ValueError(f"{path} did not contain a JSON array or row container")


def _observation_ts_ms(row: dict[str, Any]) -> int:
    for key in ("ts_ms", "close_ts_ms", "timestamp_ms", "start_ts_ms"):
        value = _int(row.get(key), default=0)
        if value > 0:
            return value
    parsed = _parse_dt(row.get("ts_utc") or row.get("timestamp") or row.get("time"))
    return int(parsed.timestamp() * 1000) if parsed else 0


def _observation_price(row: dict[str, Any]) -> float | None:
    for key in ("price", "close", "close_price", "last_price", "mark_price"):
        value = _float(row.get(key))
        if value is not None and value > 0.0:
            return value
    return None


def _matching_observations(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
) -> list[tuple[int, float]]:
    out = []
    target_symbol = _str(symbol).upper()
    for row in rows:
        if _str(row.get("symbol")).upper() != target_symbol:
            continue
        ts_ms = _observation_ts_ms(row)
        price = _observation_price(row)
        if ts_ms > 0 and price is not None:
            out.append((ts_ms, price))
    return sorted(out, key=lambda item: item[0])


def _first_price_at_or_after(
    observations: list[tuple[int, float]],
    ts_ms: int,
    *,
    max_delay_ms: int | None = None,
) -> tuple[int, float] | None:
    for obs_ts, price in observations:
        if obs_ts < ts_ms:
            continue
        if max_delay_ms is not None and obs_ts - ts_ms > max_delay_ms:
            return None
        return obs_ts, price
    return None


def _existing_outcome_attempt_ids(
    ledger_rows: list[dict[str, Any]],
    *,
    record_type: str,
) -> set[str]:
    return {
        _str(row.get("attempt_id")) or _attempt_id(row)
        for row in ledger_rows
        if _str(row.get("record_type")) == record_type
    }


def _row_outcome_horizon_minutes(row: dict[str, Any], default_horizon_minutes: int) -> int:
    candidate = _dict(row.get("candidate_summary"))
    for value in (
        row.get("outcome_horizon_minutes"),
        row.get("learning_outcome_horizon_minutes"),
        candidate.get("outcome_horizon_minutes"),
        candidate.get("learning_outcome_horizon_minutes"),
    ):
        parsed = _int(value)
        if 1 <= parsed <= 24 * 60:
            return parsed
    return default_horizon_minutes


def _build_markout_outcome_records(
    ledger_rows: list[dict[str, Any]],
    price_observations: list[dict[str, Any]],
    *,
    now_utc: dt.datetime | None = None,
    cfg: ProbeOutcomeConfig | None = None,
    source_row_predicate,
    record_type: str,
    outcome_source: str,
    boundary: str,
) -> list[dict[str, Any]]:
    cfg = cfg or ProbeOutcomeConfig()
    validate_outcome_config(cfg)
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    existing_attempt_ids = _existing_outcome_attempt_ids(
        ledger_rows,
        record_type=record_type,
    )
    outcomes: list[dict[str, Any]] = []

    for row in ledger_rows:
        if _str(row.get("record_type")) != PROBE_ADMISSION_DECISION_RECORD_TYPE:
            continue
        decision = _row_decision(row)
        if not source_row_predicate(row, decision):
            continue
        attempt_id = _str(row.get("attempt_id")) or _attempt_id(row)
        if not attempt_id or attempt_id in existing_attempt_ids:
            continue
        event = _dict(row.get("event"))
        event_ts_ms = _row_ts_ms(row)
        horizon_minutes = _row_outcome_horizon_minutes(row, cfg.horizon_minutes)
        horizon_ms = horizon_minutes * 60_000
        exit_target_ts_ms = event_ts_ms + horizon_ms
        max_exit_delay_ms = _max_exit_delay_ms(horizon_ms)
        if event_ts_ms <= 0 or now_ms < exit_target_ts_ms:
            continue

        symbol = _str(event.get("symbol")).upper()
        side = _str(event.get("side"))
        observations = _matching_observations(price_observations, symbol=symbol)
        last_observation_ts_ms = observations[-1][0] if observations else None
        base_row = {
            "schema_version": ADAPTER_SCHEMA_VERSION,
            "record_type": record_type,
            "generated_at_utc": now.isoformat(),
            "attempt_id": attempt_id,
            "side_cell_key": row.get("side_cell_key") or _ledger_side_cell(row),
            "source_admission_decision": decision,
            "allowed_to_submit_order": row.get("allowed_to_submit_order"),
            "strategy_name": event.get("strategy_name") or event.get("strategy"),
            "symbol": symbol,
            "side": side,
            "event_ts_ms": event_ts_ms,
            "horizon_minutes": horizon_minutes,
            "default_horizon_minutes": cfg.horizon_minutes,
            "outcome_source": outcome_source,
            "candidate_summary": row.get("candidate_summary") or {},
            "promotion_evidence": False,
            "boundary": boundary,
        }

        entry = _float(event.get("entry_price") or event.get("price") or event.get("last_price"))
        entry_ts_ms = event_ts_ms
        if entry is None or entry <= 0.0:
            entry_obs = _first_price_at_or_after(
                observations,
                event_ts_ms,
                max_delay_ms=cfg.max_entry_delay_ms,
            )
            if entry_obs is None:
                # F7:入場觀測缺失。時限未到 → 下輪再試(不落 row);時限已過 → 寫
                # censored row，終結「無限重掃」漏洞(attempt_id 進 existing set)。
                entry_deadline_ms = (
                    event_ts_ms + cfg.max_entry_delay_ms + horizon_ms + max_exit_delay_ms
                )
                if now_ms > entry_deadline_ms:
                    outcomes.append(
                        _censored_row(
                            base_row,
                            censor_reason="entry_observation_gap",
                            last_observation_ts_ms=last_observation_ts_ms,
                        )
                    )
                continue
            entry_ts_ms, entry = entry_obs

        exit_obs = _first_price_at_or_after(
            observations,
            exit_target_ts_ms,
            max_delay_ms=max_exit_delay_ms,
        )
        if exit_obs is None:
            # F7:出場觀測缺失。超過 exit_target+max_exit_delay 仍無價 → 語義不可救，
            # 寫 censored row;尚在延遲窗內 → continue(唯一合法重試窗)。
            if now_ms > exit_target_ts_ms + max_exit_delay_ms:
                outcomes.append(
                    _censored_row(
                        base_row,
                        censor_reason="exit_observation_gap",
                        last_observation_ts_ms=last_observation_ts_ms,
                        entry_ts_ms=entry_ts_ms,
                        entry_price=entry,
                    )
                )
            continue
        exit_ts_ms, exit_price = exit_obs

        side_sign = -1.0 if side.lower() == "sell" else 1.0
        gross_bps = side_sign * (exit_price - entry) / entry * 10_000.0

        # P1-2a:保守成本模型(taker fee + per-symbol 滑點分位 p75 × SM + funding)。
        crossings = funding_crossing_count(
            event_ts_ms=event_ts_ms,
            horizon_minutes=horizon_minutes,
            funding_interval_hours=cfg.funding_interval_hours,
        )
        cost = conservative_cost_bps(
            symbol=symbol,
            horizon_minutes=horizon_minutes,
            table=cfg.slippage_table,
            now=now,
            funding_crossings=crossings,
        )
        cost_bps_conservative = cost["cost_bps"]
        realized_net_bps = gross_bps - cost_bps_conservative
        net_bps_optimistic = gross_bps - cfg.cost_bps
        outcomes.append(
            {
                **base_row,
                "censored": False,
                "entry_ts_ms": entry_ts_ms,
                "exit_ts_ms": exit_ts_ms,
                "exit_delay_ms": exit_ts_ms - exit_target_ts_ms,
                "entry_price": entry,
                "exit_price": exit_price,
                "gross_bps": gross_bps,
                # 語義升級:cost_bps = 保守權威成本(review 直接沿用，下游零改動)。
                "cost_bps": cost_bps_conservative,
                "cost_model_version": cost["cost_model_version"],
                "cost_model_source": cost["cost_model_source"],
                "slippage_bps": cost["slippage_bps"],
                "cost_bps_optimistic": cfg.cost_bps,
                "net_bps_optimistic": net_bps_optimistic,
                "realized_net_bps": realized_net_bps,
                "funding_crossings": cost["funding_crossings"],
                "funding_drag_bps": cost["funding_drag_bps"],
            }
        )

    return outcomes


def _censored_row(
    base_row: dict[str, Any],
    *,
    censor_reason: str,
    last_observation_ts_ms: int | None,
    entry_ts_ms: int | None = None,
    entry_price: float | None = None,
) -> dict[str, Any]:
    """F7:觀測斷供的 censored outcome row。

    為什麼 censored 而非 silent drop：觀測斷供與波動事件相關(MNAR，缺失非隨機)，
    silent drop 造成的偏差方向不可知；顯式 censoring 保留分母資訊、讓資料品質缺陷
    可被看見，並終結每輪 refresh 對同 attempt_id 的無限重掃(attempt_id 進 existing set)。
    censored row 不進 nets/檢定分母(消費側 outcome_review 據 censored 欄剔除)。
    """
    return {
        **base_row,
        "censored": True,
        "censor_reason": censor_reason,
        "entry_ts_ms": entry_ts_ms,
        "exit_ts_ms": None,
        "entry_price": entry_price,
        "exit_price": None,
        "gross_bps": None,
        "cost_bps": None,
        "realized_net_bps": None,
        "last_observation_ts_ms": last_observation_ts_ms,
    }


def build_probe_outcome_records(
    ledger_rows: list[dict[str, Any]],
    price_observations: list[dict[str, Any]],
    *,
    now_utc: dt.datetime | None = None,
    cfg: ProbeOutcomeConfig | None = None,
) -> list[dict[str, Any]]:
    """Build append-only outcome rows for admitted probes whose horizon matured."""
    return _build_markout_outcome_records(
        ledger_rows,
        price_observations,
        now_utc=now_utc,
        cfg=cfg,
        source_row_predicate=lambda _row, decision: decision == ADMIT_DECISION,
        record_type=PROBE_OUTCOME_RECORD_TYPE,
        outcome_source="market_markout_proxy",
        boundary=(
            "probe outcome ledger artifact only; markout proxy unless "
            "future fill-backed writer replaces source; no PG, Bybit, "
            "order, config, risk, auth, or runtime mutation"
        ),
    )


def build_blocked_signal_outcome_records(
    ledger_rows: list[dict[str, Any]],
    price_observations: list[dict[str, Any]],
    *,
    now_utc: dt.datetime | None = None,
    cfg: ProbeOutcomeConfig | None = None,
) -> list[dict[str, Any]]:
    """Build markout rows for rejected signals that were recorded but not allowed."""
    return _build_markout_outcome_records(
        ledger_rows,
        price_observations,
        now_utc=now_utc,
        cfg=cfg,
        source_row_predicate=lambda row, decision: (
            decision != ADMIT_DECISION and row.get("allowed_to_submit_order") is False
        ),
        record_type=BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
        outcome_source="market_markout_proxy_for_blocked_signal",
        boundary=(
            "blocked-signal counterfactual outcome artifact only; not a probe "
            "fill, not promotion evidence, and no PG, Bybit, order, config, "
            "risk, auth, or runtime mutation"
        ),
    )
