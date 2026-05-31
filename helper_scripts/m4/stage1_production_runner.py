"""
M4 Stage 1 production runner core.

This module keeps the non-dry-run path testable without opening a database
connection at import time. It reads the existing source-loader SQL through an
injected connection, computes a small leak-free candidate set, and writes DRAFT
rows only when the caller provides explicit Decision Lease UUIDs.
"""
from __future__ import annotations

import bisect
import math
import re
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Mapping, Sequence

from helper_scripts.m4.algorithms.cross_correlation import corr_to_p_value, pearson_corr
from helper_scripts.m4.algorithms.effect_size import cohens_d
from helper_scripts.m4.algorithms.event_window import (
    detect_funding_flip_events,
    detect_large_funding_spike_events,
    detect_liquidation_cascade_events,
    event_window_forward_shift,
    merge_close_events,
)
from helper_scripts.m4.attribute_enforcer import determine_hypothesis_status
from helper_scripts.m4.draft_writer import (
    DRAFT_INSERT_SQL,
    build_audit_metadata,
    build_writeback_payload,
    payload_to_params,
)
from helper_scripts.m4.sources.fills_loader import build_fills_query
from helper_scripts.m4.sources.funding_loader import build_funding_query
from helper_scripts.m4.sources.kline_loader import build_kline_query
from helper_scripts.m4.sources.liquidations_loader import build_liquidations_query


VALID_M4_PG_STATUSES: tuple[str, ...] = ("draft", "preregistered")
DEFAULT_CROSS_CORR_WINDOWS: tuple[int, ...] = (20, 60)
DEFAULT_EVENT_WINDOW_BARS: int = 12
LIQUIDATION_CASCADE_THRESHOLD_USD: float = 5_000_000.0


@dataclass(frozen=True)
class Stage1Candidate:
    """A candidate hypothesis before optional PG writeback."""

    strategy_name: str
    symbol: str
    pattern_type: str
    n_observations: int
    raw_p_value: float
    cohens_d: float
    analysis_lane: str
    pg_status: str
    subperiod_pass: bool | None
    graveyard_flag: bool
    silhouette: float | None
    leakage_scan_pass: bool
    score: float
    metadata: dict[str, Any]

    def summary(self) -> dict[str, Any]:
        """Stable JSON-safe summary for logs and tests."""
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "pattern_type": self.pattern_type,
            "n_observations": self.n_observations,
            "raw_p_value": self.raw_p_value,
            "cohens_d": self.cohens_d,
            "analysis_lane": self.analysis_lane,
            "pg_status": self.pg_status,
            "subperiod_pass": self.subperiod_pass,
            "leakage_scan_pass": self.leakage_scan_pass,
            "score": self.score,
            "metadata": self.metadata,
        }


class StaticLeaseProvider:
    """Lease provider for a batch with pre-acquired Decision Lease UUIDs."""

    def __init__(self, lease_ids: Iterable[uuid.UUID | str]) -> None:
        self._lease_ids = [_parse_uuid(lease_id) for lease_id in lease_ids]
        self._index = 0
        self.released: list[tuple[uuid.UUID, str]] = []

    @property
    def remaining(self) -> int:
        return len(self._lease_ids) - self._index

    def require_capacity(self, required: int) -> None:
        if self.remaining < required:
            raise RuntimeError(
                "M4 writeback requires one real decision lease UUID per DRAFT row; "
                f"needed {required}, got {self.remaining}"
            )

    def acquire_lease(self, candidate: Stage1Candidate) -> uuid.UUID:
        del candidate
        if self.remaining <= 0:
            raise RuntimeError(
                "M4 writeback refused: no decision lease UUID remains for this row"
            )
        lease_id = self._lease_ids[self._index]
        self._index += 1
        return lease_id

    def release_lease(self, lease_id: uuid.UUID, outcome: str) -> None:
        self.released.append((lease_id, outcome))


def map_analysis_lane_to_pg_status(analysis_lane: str) -> str:
    """Map M4 analysis lanes to the V100-compatible PG status enum."""
    if analysis_lane == "preregistered":
        return "preregistered"
    if analysis_lane == "exploratory":
        return "draft"
    raise ValueError(f"unknown M4 analysis_lane={analysis_lane!r}")


def run_production_stage1(
    conn: Any,
    symbols: tuple[str, ...],
    lookback_days: int,
    max_drafts: int = 3,
    enable_writeback: bool = False,
    decision_lease_draft_ids: Iterable[uuid.UUID | str] = (),
    engine_mode: str = "live_demo",
) -> dict[str, Any]:
    """Execute the non-dry-run Stage 1 path against an injected PG connection."""
    if max_drafts < 0:
        raise ValueError("max_drafts must be >= 0")

    started_at = datetime.now(tz=timezone.utc)
    source_rows = load_source_rows(conn, symbols=symbols, lookback_days=lookback_days)
    candidates = generate_stage1_candidates(
        kline_rows=source_rows["klines"],
        funding_rows=source_rows["funding"],
        liquidation_rows=source_rows["liquidations"],
    )
    selected = rank_candidates(candidates)[:max_drafts]
    inserted: list[dict[str, Any]] = []

    if enable_writeback and selected:
        provider = StaticLeaseProvider(decision_lease_draft_ids)
        provider.require_capacity(len(selected))
        inserted = write_candidates_to_pg(
            conn=conn,
            candidates=selected,
            lease_provider=provider,
            engine_mode=engine_mode,
        )
    elif enable_writeback and not selected:
        _commit_if_available(conn)

    completed_at = datetime.now(tz=timezone.utc)
    return {
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "dry_run": False,
        "symbols": list(symbols),
        "lookback_days": lookback_days,
        "n_source_queries_built": 4,
        "n_source_stubs": 1,
        "source_row_counts": {
            "klines": len(source_rows["klines"]),
            "fills": len(source_rows["fills"]),
            "liquidations": len(source_rows["liquidations"]),
            "funding": len(source_rows["funding"]),
        },
        "n_candidates": len(candidates),
        "n_selected_candidates": len(selected),
        "n_drafts": len(inserted),
        "n_preregistered": sum(1 for item in selected if item.pg_status == "preregistered"),
        "n_exploratory": sum(1 for item in selected if item.analysis_lane == "exploratory"),
        "writeback_enabled": enable_writeback,
        "selected_candidates": [candidate.summary() for candidate in selected],
        "inserted_hypotheses": inserted,
    }


def load_source_rows(
    conn: Any,
    symbols: tuple[str, ...],
    lookback_days: int,
) -> dict[str, list[dict[str, Any]]]:
    """Read the four PG sources through existing source-loader SQL builders."""
    kline_sql, kline_params = build_kline_query(symbols, lookback_days=lookback_days)
    fills_sql, fills_params = build_fills_query(lookback_days=lookback_days)
    liq_sql, liq_params = build_liquidations_query(lookback_days=lookback_days)
    funding_sql, funding_params = build_funding_query(lookback_days=lookback_days)

    symbol_set = set(symbols)
    funding_rows = [
        row
        for row in fetch_rows(conn, funding_sql, funding_params)
        if row.get("symbol") in symbol_set
    ]
    return {
        "klines": fetch_rows(conn, kline_sql, kline_params),
        "fills": fetch_rows(conn, fills_sql, fills_params),
        "liquidations": fetch_rows(conn, liq_sql, liq_params),
        "funding": funding_rows,
    }


def fetch_rows(conn: Any, sql: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Execute a SELECT and normalize tuple/dict rows into dicts."""
    with _managed_cursor(conn) as cur:
        cur.execute(sql, dict(params))
        rows = cur.fetchall()
        if not rows:
            return []
        if isinstance(rows[0], Mapping):
            return [dict(row) for row in rows]
        description = getattr(cur, "description", None)
        if not description:
            raise RuntimeError("cursor returned tuple rows without description")
        columns = [desc[0] for desc in description]
        return [dict(zip(columns, row)) for row in rows]


def generate_stage1_candidates(
    kline_rows: Sequence[Mapping[str, Any]],
    funding_rows: Sequence[Mapping[str, Any]],
    liquidation_rows: Sequence[Mapping[str, Any]],
) -> list[Stage1Candidate]:
    """Generate leak-free cross-correlation and event-window candidates."""
    kline_groups = _group_klines(kline_rows)
    candidates: list[Stage1Candidate] = []

    for (symbol, timeframe), rows in kline_groups.items():
        candidates.extend(_generate_cross_corr_candidates(symbol, timeframe, rows))

    for symbol in sorted({row["symbol"] for row in funding_rows if row.get("symbol")}):
        price_rows = _preferred_price_rows(kline_groups, symbol)
        if price_rows:
            funding_symbol_rows = [
                row for row in funding_rows if row.get("symbol") == symbol
            ]
            candidates.extend(_generate_funding_event_candidates(symbol, price_rows, funding_symbol_rows))

    for symbol in sorted({row["symbol"] for row in liquidation_rows if row.get("symbol")}):
        price_rows = _preferred_price_rows(kline_groups, symbol)
        if price_rows:
            liq_symbol_rows = [
                row for row in liquidation_rows if row.get("symbol") == symbol
            ]
            candidates.extend(_generate_liquidation_event_candidates(symbol, price_rows, liq_symbol_rows))

    return candidates


def rank_candidates(candidates: Sequence[Stage1Candidate]) -> list[Stage1Candidate]:
    """Stable order: promotable evidence first, then sample size and score."""
    return sorted(
        candidates,
        key=lambda item: (
            0 if item.pg_status == "preregistered" else 1,
            -item.n_observations,
            -item.score,
            item.strategy_name,
        ),
    )


def write_candidates_to_pg(
    conn: Any,
    candidates: Sequence[Stage1Candidate],
    lease_provider: StaticLeaseProvider,
    engine_mode: str,
) -> list[dict[str, Any]]:
    """Write selected candidates into learning.hypotheses inside one transaction."""
    lease_provider.require_capacity(len(candidates))
    inserted: list[dict[str, Any]] = []
    acquired_leases: list[uuid.UUID] = []
    try:
        with _managed_cursor(conn) as cur:
            for candidate in candidates:
                if candidate.pg_status not in VALID_M4_PG_STATUSES:
                    raise RuntimeError(
                        f"invalid PG status for M4 writeback: {candidate.pg_status!r}"
                    )
                lease_id = lease_provider.acquire_lease(candidate)
                acquired_leases.append(lease_id)
                payload = build_writeback_payload(
                    strategy_name=candidate.strategy_name,
                    n_observations=candidate.n_observations,
                    raw_p_value=candidate.raw_p_value,
                    cohens_d=candidate.cohens_d,
                    status_candidate=candidate.pg_status,
                    subperiod_pass=candidate.subperiod_pass,
                    graveyard_flag=candidate.graveyard_flag,
                    silhouette=candidate.silhouette,
                    leakage_scan_pass=candidate.leakage_scan_pass,
                    decision_lease_draft_id=lease_id,
                    engine_mode=engine_mode,
                )
                cur.execute(DRAFT_INSERT_SQL, payload_to_params(payload))
                row = cur.fetchone()
                hypothesis_id = _extract_hypothesis_id(row)
                audit_metadata = build_audit_metadata(payload)
                audit_metadata.update(
                    {
                        "analysis_lane": candidate.analysis_lane,
                        "pattern_type": candidate.pattern_type,
                        "candidate_metadata": candidate.metadata,
                    }
                )
                inserted.append(
                    {
                        "hypothesis_id": hypothesis_id,
                        "strategy_name": candidate.strategy_name,
                        "decision_lease_draft_id": str(lease_id),
                        "pg_status": candidate.pg_status,
                        "analysis_lane": candidate.analysis_lane,
                        "audit_metadata": audit_metadata,
                    }
                )
        _commit_if_available(conn)
        for lease_id in acquired_leases:
            lease_provider.release_lease(lease_id, "SUCCESS")
        return inserted
    except Exception:
        _rollback_if_available(conn)
        for lease_id in acquired_leases:
            lease_provider.release_lease(lease_id, "FAILED")
        raise


def _generate_cross_corr_candidates(
    symbol: str,
    timeframe: str,
    rows: Sequence[Mapping[str, Any]],
) -> list[Stage1Candidate]:
    closes = [_float(row.get("close")) for row in rows]
    candidates: list[Stage1Candidate] = []
    for window in DEFAULT_CROSS_CORR_WINDOWS:
        pairs = _shift1_sma_feature_pairs(closes, window)
        if len(pairs) < 30:
            continue
        features = [pair[0] for pair in pairs]
        forward_bps = [pair[1] for pair in pairs]
        r = pearson_corr(features, forward_bps)
        if r is None:
            continue
        raw_p = corr_to_p_value(r, len(pairs))
        effect = _median_split_effect_size(features, forward_bps)
        if effect is None:
            continue
        subperiod_pass = _subperiod_sign_stability(features, forward_bps)
        lane = determine_hypothesis_status(
            n=len(pairs),
            raw_p=raw_p,
            cohens_d=effect,
            subperiod_pass=subperiod_pass,
            graveyard_flag=False,
            silhouette=None,
        )
        candidates.append(
            Stage1Candidate(
                strategy_name=_strategy_name("m4_xcorr_sma", symbol, timeframe, str(window)),
                symbol=symbol,
                pattern_type="cross_correlation",
                n_observations=len(pairs),
                raw_p_value=raw_p,
                cohens_d=effect,
                analysis_lane=lane,
                pg_status=map_analysis_lane_to_pg_status(lane),
                subperiod_pass=subperiod_pass,
                graveyard_flag=False,
                silhouette=None,
                leakage_scan_pass=True,
                score=abs(r) + abs(effect),
                metadata={
                    "timeframe": timeframe,
                    "feature": "shift1_sma_ratio",
                    "window": window,
                    "pearson_r": round(r, 8),
                    "forward_horizon_bars": 1,
                },
            )
        )
    return candidates


def _generate_funding_event_candidates(
    symbol: str,
    price_rows: Sequence[Mapping[str, Any]],
    funding_rows: Sequence[Mapping[str, Any]],
) -> list[Stage1Candidate]:
    rows = [
        row
        for row in sorted(funding_rows, key=lambda row: _ts_sort_key(row.get("ts")))
        if _float(row.get("funding_rate")) is not None
    ]
    if len(rows) < 2:
        return []
    rates = [_float(row.get("funding_rate")) for row in rows]
    if any(rate is None for rate in rates):
        return []
    numeric_rates = [rate for rate in rates if rate is not None]
    event_specs = [
        ("funding_flip", detect_funding_flip_events(numeric_rates)),
        ("funding_spike", detect_large_funding_spike_events(numeric_rates)),
    ]
    candidates: list[Stage1Candidate] = []
    for event_name, event_indices in event_specs:
        event_ts = [rows[index]["ts"] for index in event_indices]
        effects = _event_effects_from_timestamps(price_rows, event_ts)
        candidate = _event_candidate(symbol, event_name, effects)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _generate_liquidation_event_candidates(
    symbol: str,
    price_rows: Sequence[Mapping[str, Any]],
    liquidation_rows: Sequence[Mapping[str, Any]],
) -> list[Stage1Candidate]:
    price_ts = [_to_epoch_seconds(row.get("ts")) for row in price_rows]
    if not price_ts:
        return []

    bucket_notional: dict[int, float] = defaultdict(float)
    for row in liquidation_rows:
        ts_epoch = _to_epoch_seconds(row.get("ts"))
        if ts_epoch is None:
            continue
        qty = _float(row.get("qty"))
        price = _float(row.get("price"))
        if qty is None or price is None:
            continue
        bucket_notional[int(ts_epoch // 300) * 300] += abs(qty * price)

    series = []
    for ts_epoch in price_ts:
        if ts_epoch is None:
            series.append(0.0)
        else:
            series.append(bucket_notional.get(int(ts_epoch // 300) * 300, 0.0))
    event_indices = detect_liquidation_cascade_events(
        series,
        cascade_threshold_usd=LIQUIDATION_CASCADE_THRESHOLD_USD,
    )
    event_indices = merge_close_events(
        event_indices,
        pre_window=DEFAULT_EVENT_WINDOW_BARS,
        post_window=DEFAULT_EVENT_WINDOW_BARS,
    )
    forward_bps = _forward_returns_bps([_float(row.get("close")) for row in price_rows])
    effects = []
    for event_index in event_indices:
        result = event_window_forward_shift(
            forward_bps,
            event_index=event_index,
            pre_window=DEFAULT_EVENT_WINDOW_BARS,
            post_window=DEFAULT_EVENT_WINDOW_BARS,
        )
        if result is not None:
            effects.append(result[2])
    candidate = _event_candidate(symbol, "liq_cascade", effects)
    return [] if candidate is None else [candidate]


def _event_candidate(
    symbol: str,
    event_name: str,
    effects_bps: Sequence[float],
) -> Stage1Candidate | None:
    if len(effects_bps) < 1:
        return None
    n = len(effects_bps)
    effect_d, raw_p = _one_sample_effect_stats(effects_bps)
    lane = determine_hypothesis_status(
        n=n,
        raw_p=raw_p,
        cohens_d=effect_d,
        subperiod_pass=None,
        graveyard_flag=False,
        silhouette=None,
    )
    mean_effect_bps = sum(effects_bps) / n
    return Stage1Candidate(
        strategy_name=_strategy_name("m4_event", event_name, symbol),
        symbol=symbol,
        pattern_type="event_window",
        n_observations=n,
        raw_p_value=raw_p,
        cohens_d=effect_d,
        analysis_lane=lane,
        pg_status=map_analysis_lane_to_pg_status(lane),
        subperiod_pass=None,
        graveyard_flag=False,
        silhouette=None,
        leakage_scan_pass=True,
        score=abs(effect_d) + min(1.0, abs(mean_effect_bps) / 100.0),
        metadata={
            "event_name": event_name,
            "mean_effect_bps": round(mean_effect_bps, 8),
            "pre_window_bars": DEFAULT_EVENT_WINDOW_BARS,
            "post_window_bars": DEFAULT_EVENT_WINDOW_BARS,
        },
    )


def _event_effects_from_timestamps(
    price_rows: Sequence[Mapping[str, Any]],
    event_timestamps: Sequence[Any],
) -> list[float]:
    price_ts = [_to_epoch_seconds(row.get("ts")) for row in price_rows]
    closes = [_float(row.get("close")) for row in price_rows]
    forward_bps = _forward_returns_bps(closes)
    usable_ts = [ts for ts in price_ts if ts is not None]
    if len(usable_ts) != len(price_ts):
        return []
    effects: list[float] = []
    for event_ts in event_timestamps:
        event_epoch = _to_epoch_seconds(event_ts)
        if event_epoch is None:
            continue
        event_index = bisect.bisect_left(usable_ts, event_epoch)
        result = event_window_forward_shift(
            forward_bps,
            event_index=event_index,
            pre_window=DEFAULT_EVENT_WINDOW_BARS,
            post_window=DEFAULT_EVENT_WINDOW_BARS,
        )
        if result is not None:
            effects.append(result[2])
    return effects


def _group_klines(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        symbol = row.get("symbol")
        timeframe = row.get("timeframe")
        if symbol and timeframe:
            grouped[(str(symbol), str(timeframe))].append(row)
    return {
        key: sorted(value, key=lambda row: _ts_sort_key(row.get("ts")))
        for key, value in grouped.items()
    }


def _preferred_price_rows(
    kline_groups: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
    symbol: str,
) -> Sequence[Mapping[str, Any]]:
    for timeframe in ("1m", "5m", "15m", "1h", "4h"):
        rows = kline_groups.get((symbol, timeframe))
        if rows:
            return rows
    return []


def _shift1_sma_feature_pairs(
    closes: Sequence[float | None],
    window: int,
) -> list[tuple[float, float]]:
    forward_bps = _forward_returns_bps(closes)
    pairs: list[tuple[float, float]] = []
    for index in range(window, len(closes) - 1):
        close = closes[index]
        window_values = closes[index - window : index]
        forward = forward_bps[index]
        if close is None or forward is None or any(value is None for value in window_values):
            continue
        mean = sum(value for value in window_values if value is not None) / window
        if abs(mean) < 1e-15:
            continue
        pairs.append((close / mean - 1.0, forward))
    return pairs


def _forward_returns_bps(closes: Sequence[float | None]) -> list[float | None]:
    returns: list[float | None] = []
    for index, close in enumerate(closes):
        if index + 1 >= len(closes):
            returns.append(None)
            continue
        nxt = closes[index + 1]
        if close is None or nxt is None or abs(close) < 1e-15:
            returns.append(None)
            continue
        returns.append((nxt - close) / close * 10_000.0)
    return returns


def _median_split_effect_size(
    features: Sequence[float],
    forward_bps: Sequence[float],
) -> float | None:
    if len(features) != len(forward_bps) or len(features) < 4:
        return None
    median = sorted(features)[len(features) // 2]
    high = [ret for feature, ret in zip(features, forward_bps) if feature >= median]
    low = [ret for feature, ret in zip(features, forward_bps) if feature < median]
    return cohens_d(high, low)


def _subperiod_sign_stability(
    features: Sequence[float],
    forward_bps: Sequence[float],
) -> bool | None:
    if len(features) < 60 or len(features) != len(forward_bps):
        return None
    midpoint = len(features) // 2
    left = pearson_corr(features[:midpoint], forward_bps[:midpoint])
    right = pearson_corr(features[midpoint:], forward_bps[midpoint:])
    if left is None or right is None:
        return None
    if abs(left) < 1e-12 or abs(right) < 1e-12:
        return False
    return (left > 0) == (right > 0)


def _one_sample_effect_stats(values: Sequence[float]) -> tuple[float, float]:
    if len(values) < 2:
        return 0.0, 1.0
    n = len(values)
    mean = sum(values) / n
    variance = sum((value - mean) ** 2 for value in values) / n
    std = math.sqrt(variance)
    if std < 1e-15:
        return 0.0, 1.0
    effect = mean / std
    z = abs(effect) * math.sqrt(n)
    p_value = 2.0 * (1.0 - _normal_cdf(z))
    return effect, max(0.0, min(1.0, p_value))


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _strategy_name(*parts: str) -> str:
    joined = "_".join(str(part) for part in parts if part)
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", joined).strip("_").lower()
    return cleaned[:120]


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _to_epoch_seconds(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    timestamp = getattr(value, "timestamp", None)
    if callable(timestamp):
        return float(timestamp())
    return None


def _ts_sort_key(value: Any) -> float:
    epoch = _to_epoch_seconds(value)
    return epoch if epoch is not None else 0.0


def _parse_uuid(value: uuid.UUID | str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _extract_hypothesis_id(row: Any) -> Any:
    if isinstance(row, Mapping):
        return row.get("hypothesis_id")
    if isinstance(row, (tuple, list)) and row:
        return row[0]
    return row


@contextmanager
def _managed_cursor(conn: Any) -> Iterator[Any]:
    cursor = conn.cursor()
    if hasattr(cursor, "__enter__"):
        with cursor as managed:
            yield managed
    else:
        try:
            yield cursor
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()


def _commit_if_available(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()


def _rollback_if_available(conn: Any) -> None:
    rollback = getattr(conn, "rollback", None)
    if callable(rollback):
        rollback()
