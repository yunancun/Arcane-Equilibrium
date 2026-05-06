"""Bounded demo applier for ML/Dream edge recommendations.

模組目的 / Module purpose:
    消費 ``learning.mlde_shadow_recommendations`` 並只在 demo engine 套用受界
    參數變更（透過 Rust IPC）。Live / live_demo row 永不在此處被套用；正向
    demo 證據會發出一個 governed live ``experiment_plan`` candidate，由
    LG-5 GovernanceHub 後續 review。

    Consumes ``learning.mlde_shadow_recommendations`` and applies only demo-
    scoped parameter changes through Rust IPC. Live/live_demo rows are never
    applied here; positive demo evidence emits a governed live
    ``experiment_plan`` candidate which will be reviewed downstream by
    LG-5 GovernanceHub.

LG-5 RFC v2 §2.1 producer side:
    `_insert_live_candidate` payload now carries `schema_version`,
    `demo_cost_baseline`, `demo_realized_window`,
    `demo_attribution_chain_ratio_by_strategy` (per-strategy 5-key dict per
    MIT MF-M2), and `demo_sample_count_strategy_cell`. Consumer side (LG-5
    IMPL-2 `GovernanceHub.review_live_candidate`) fail-closes when
    `schema_version` is missing or unknown.

關聯文件 / Related docs:
    - `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md` §2.1 + §3 R-meta
    - CLAUDE.md §二 原則 #3 (AI output != command) + #8 (explainability)
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import hashlib
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional


# LG-5 RFC v2 §2.1 schema version constant.
# Consumer side (`GovernanceHub.review_live_candidate`) fail-closes on
# missing or wrong version. Bump only when payload schema breaks
# backward-compat with consumer.
# LG-5 RFC v2 §2.1 schema 版本常量。消費端 (`GovernanceHub.review_live_candidate`)
# 對缺失 / 錯誤版本 fail-closed。僅在 payload schema 與消費端不再相容時 bump。
_LIVE_CANDIDATE_EVAL_SCHEMA_VERSION = "live_candidate_eval_v1"

# LG-5 RFC v2 §2.1 hardcoded 5-strategy keyset for per-strategy attribution
# chain ratio dict. R-meta gate (per MF-M2) requires all 5 keys present;
# missing key → strategy treated as 0.0 (defer at consumer side).
# LG-5 RFC v2 §2.1 attribution per-strategy dict 的 5 個 hardcoded strategy key。
# R-meta gate (MF-M2) 要求 5 key 全在；缺 key → 該 strategy 視為 0.0 (consumer defer)。
_ATTRIBUTION_STRATEGY_KEYS: tuple[str, ...] = (
    "grid_trading",
    "ma_crossover",
    "bb_breakout",
    "bb_reversion",
    "funding_arb",
)

# LG-5 RFC v2 §3 R-meta source healthcheck ids (audit / replay reference).
# 用於 payload.demo_cost_baseline.source_healthchecks，供 IMPL-5 retro 校準。
_DEMO_COST_BASELINE_SOURCE_HEALTHCHECKS: tuple[str, ...] = ("[33]", "[40]")

# 7-day demo realized window for cost baseline + realized aggregation.
# Mirrors healthcheck `[33]` / `[40]` window (CLAUDE.md §三).
# 7d demo realized 窗口；對齊 healthcheck `[33]` / `[40]` 的窗口。
_DEMO_BASELINE_WINDOW_DAYS: int = 7

# LG-5 W3 FUP-2 Fix 2 (PA RFC 2026-05-02): R-meta attribution gate window
# decoupled from cost baseline. 7d includes 4/24-28 bug-era residuals (fixed
# by ece31b6 / 45bbe4d / 5895579 on 4/29) and over-penalises current
# candidates; 3d aligns to the pure post-fix slice. Cost baseline / realized
# window stay 7d for statistical significance + `[33]`/`[40]` alignment.
# LG-5 W3 FUP-2 Fix 2（PA RFC 2026-05-02）：R-meta gate 窗口與 cost baseline
# 解耦。7d 含 4/24-28 bug 期殘留 over-penalize；3d 對齊已修 bug 後純後時段。
# Cost baseline / realized 維持 7d 保統計顯著性 + 對齊 `[33]`/`[40]`。
_R_META_WINDOW_DAYS: int = 3

# LG-5 W3 FUP-2 Fix 2: R-meta per-strategy min sample threshold (3d window).
# bb_breakout / bb_reversion cardinality ~13 / ~2-3 in 3d (RFC §9.2); under
# threshold producer ratio collapses to 0.0 and would mis-trigger R-meta
# defer reject_attribution_chain_too_broken. Consumer (governance_hub_
# live_candidate_review.py, IMPL-2-consumer scope) uses this constant to
# emit defer_attribution_chain_low_sample instead.
# LG-5 W3 FUP-2 Fix 2：R-meta per-strategy 最小 sample 門檻 (3d)。
# bb_breakout/bb_reversion 3d 樣本稀薄 (~13/~2-3 per RFC §9.2)；producer
# ratio 易塌 0.0 會誤觸 R-meta defer。Consumer (IMPL-2 範疇) 用此門檻改發
# defer_attribution_chain_low_sample。
_R_META_MIN_SAMPLE_PER_STRATEGY: int = 10

# Maker-like fee cutoff and taker fee rate mirrored from healthcheck `[33]`
# (helper_scripts/db/passive_wait_healthcheck/checks_execution.py). Kept in
# sync manually — if `[33]` updates these, also update here.
# Maker-like fee cutoff 與 taker fee rate 鏡 healthcheck `[33]`；手動同步。
_TAKER_FEE_RATE: float = 0.00055   # 5.5 bps Bybit Linear taker default
_MAKER_FEE_CUTOFF: float = 0.00040  # any fee_rate <= 4.0 bps treated as maker-like
_STRATEGY_ENTRY_FILL_PREDICATE: str = """
                  AND (f.entry_context_id IS NULL OR f.entry_context_id = '')
                  AND f.exit_reason IS NULL
                  AND f.order_id NOT LIKE 'oc_risk_%%'
"""


def _strategy_entry_fill_predicate() -> str:
    """SQL predicate for strategy-owned entry fills only. 僅篩 strategy entry fill。"""
    return _STRATEGY_ENTRY_FILL_PREDICATE

try:
    import psycopg2  # type: ignore
    from psycopg2.extras import DictCursor, Json  # type: ignore
except ImportError:  # pragma: no cover - runtime DB path only
    psycopg2 = None  # type: ignore[assignment]
    DictCursor = None  # type: ignore[assignment]
    Json = None  # type: ignore[assignment]

# REF-20 P4-S11 evidence-source filter helpers extracted to sibling module
# to keep this file < CLAUDE.md §九 1500 LOC. / REF-20 P4-S11 抽出 sibling。
from ml_training.mlde_demo_applier_evidence_filter import (  # noqa: E402
    EVIDENCE_SOURCE_TIER_ALLOWLIST,
    fetch_pending_sql_and_params,
)

logger = logging.getLogger(__name__)
IpcCall = Callable[[str, dict[str, Any], float], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class DemoApplierConfig:
    enabled: bool = True
    engine_mode: str = "demo"
    lookback_hours: int = 168
    min_confidence: float = 0.35
    min_samples: int = 5
    max_recommendations: int = 16
    max_param_delta_pct: float = 0.20
    max_risk_delta_pct: float = 0.10
    dedupe_hours: int = 6
    conf_scale_min: float = 0.50
    conf_scale_max: float = 1.80
    rank_conf_scale_step_pct: float = 0.05
    veto_conf_scale_step_pct: float = 0.10
    live_candidate_min_confidence: float = 0.65
    live_candidate_min_samples: int = 30
    live_candidate_min_net_bps: float = 5.0
    dry_run: bool = False


def config_from_env() -> DemoApplierConfig:
    def _bool(name: str, default: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.strip().lower() not in {"0", "false", "no", "off"}

    def _int(name: str, default: int) -> int:
        try:
            return int(os.environ.get(name, str(default)))
        except ValueError:
            return default
    def _float(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, str(default)))
        except ValueError:
            return default
    return DemoApplierConfig(
        enabled=_bool("OPENCLAW_MLDE_DEMO_APPLIER_ENABLED", True),
        engine_mode=os.environ.get("OPENCLAW_MLDE_DEMO_APPLIER_ENGINE", "demo"),
        lookback_hours=max(1, _int("OPENCLAW_MLDE_DEMO_APPLIER_LOOKBACK_HOURS", 168)),
        min_confidence=max(0.0, min(1.0, _float("OPENCLAW_MLDE_DEMO_APPLIER_MIN_CONFIDENCE", 0.35))),
        min_samples=max(1, _int("OPENCLAW_MLDE_DEMO_APPLIER_MIN_SAMPLES", 5)),
        max_recommendations=max(1, _int("OPENCLAW_MLDE_DEMO_APPLIER_MAX_RECOMMENDATIONS", 16)),
        max_param_delta_pct=max(0.01, min(0.95, _float("OPENCLAW_MLDE_DEMO_APPLIER_MAX_PARAM_DELTA_PCT", 0.20))),
        max_risk_delta_pct=max(0.01, min(0.50, _float("OPENCLAW_MLDE_DEMO_APPLIER_MAX_RISK_DELTA_PCT", 0.10))),
        dedupe_hours=max(1, _int("OPENCLAW_MLDE_DEMO_APPLIER_DEDUPE_HOURS", 6)),
        conf_scale_min=max(0.05, _float("OPENCLAW_MLDE_CONF_SCALE_MIN", 0.50)),
        conf_scale_max=max(0.10, _float("OPENCLAW_MLDE_CONF_SCALE_MAX", 1.80)),
        rank_conf_scale_step_pct=max(0.0, min(0.50, _float("OPENCLAW_MLDE_RANK_CONF_SCALE_STEP_PCT", 0.05))),
        veto_conf_scale_step_pct=max(0.0, min(0.50, _float("OPENCLAW_MLDE_VETO_CONF_SCALE_STEP_PCT", 0.10))),
        live_candidate_min_confidence=max(0.0, min(1.0, _float("OPENCLAW_MLDE_LIVE_CANDIDATE_MIN_CONFIDENCE", 0.65))),
        live_candidate_min_samples=max(1, _int("OPENCLAW_MLDE_LIVE_CANDIDATE_MIN_SAMPLES", 30)),
        live_candidate_min_net_bps=_float("OPENCLAW_MLDE_LIVE_CANDIDATE_MIN_NET_BPS", 5.0),
        dry_run=_bool("OPENCLAW_MLDE_DEMO_APPLIER_DRY_RUN", False),
    )


def _resolve_dsn(dsn: Optional[str]) -> Optional[str]:
    return dsn or os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL")

def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}

def _unwrap_ipc_payload(response: dict[str, Any]) -> Any:
    payload: Any = response.get("result") if isinstance(response, dict) and "result" in response else response
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload
    return payload

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))

def _round_step(value: float, step: Any) -> float:
    try:
        s = float(step)
    except (TypeError, ValueError):
        return value
    if s <= 0:
        return value
    return round(value / s) * s

def _bounded_numeric(
    *,
    current: Any,
    desired: Any,
    min_value: float,
    max_value: float,
    step: Any = None,
    max_delta_pct: float,
) -> float | bool | None:
    if isinstance(desired, bool):
        return desired
    try:
        cur = float(current)
        want = float(desired)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(cur) or not math.isfinite(want):
        return None
    if abs(cur) > 1e-12:
        lo = cur * (1.0 - max_delta_pct)
        hi = cur * (1.0 + max_delta_pct)
    else:
        span = max(max_value - min_value, 1.0)
        lo = cur - span * max_delta_pct
        hi = cur + span * max_delta_pct
    delta_lo = min(lo, hi)
    delta_hi = max(lo, hi)
    out = _clamp(_clamp(want, delta_lo, delta_hi), min_value, max_value)
    out = _round_step(out, step)
    out = _clamp(_clamp(out, delta_lo, delta_hi), min_value, max_value)
    return int(out) if isinstance(current, int) and not isinstance(current, bool) else out

def _range_map(ranges: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(r.get("name")): r
        for r in ranges
        if isinstance(r, dict) and r.get("name") and r.get("agent_adjustable", True)
    }

def _desired_from_direction(current: Any, pct: float, direction: str) -> float | None:
    try:
        cur = float(current)
    except (TypeError, ValueError):
        return None
    d = direction.lower()
    if any(token in d for token in ("raise", "widen", "lengthen", "tighten", "increase")):
        return cur * (1.0 + abs(pct))
    if any(token in d for token in ("lower", "reduce", "shorten", "decrease")):
        return cur * (1.0 - abs(pct))
    return cur * (1.0 + pct)

def _derived_strategy_targets(
    strategy_name: str,
    payload: dict[str, Any],
    current: dict[str, Any],
    rec_type: str,
    cfg: DemoApplierConfig,
) -> dict[str, Any]:
    if isinstance(payload.get("proposed_params"), dict):
        return dict(payload["proposed_params"])
    if rec_type == "rank":
        cur = float(current.get("conf_scale", 1.0) or 1.0)
        return {"conf_scale": cur * (1.0 + cfg.rank_conf_scale_step_pct)}
    if rec_type == "veto":
        cur = float(current.get("conf_scale", 1.0) or 1.0)
        return {"conf_scale": cur * (1.0 - cfg.veto_conf_scale_step_pct)}

    pct = float(payload.get("suggested_change_pct") or 0.0)
    direction = str(payload.get("direction") or "")
    param_name = str(payload.get("param_name") or "")
    candidates: dict[str, Any] = {}
    def add_if_current(name: str, local_pct: float | None = None, local_direction: str | None = None) -> None:
        if name in current:
            desired = _desired_from_direction(
                current[name],
                pct if local_pct is None else local_pct,
                direction if local_direction is None else local_direction,
            )
            if desired is not None:
                candidates[name] = desired

    if strategy_name == "grid_trading" and param_name in {"grid_spacing_bps", "spacing_bps"}:
        add_if_current("cooldown_ms", pct, "lengthen")
        add_if_current("max_cooldown_boost", pct * 0.5, "raise")
    elif strategy_name == "ma_crossover" and param_name in {"min_hold_seconds", "min_hold_ms"}:
        add_if_current("min_persistence_ms", pct, "lengthen")
        add_if_current("cooldown_ms", pct * 0.5, "lengthen")
    elif strategy_name == "bb_breakout" and param_name == "volume_threshold":
        add_if_current("volume_threshold", pct, "raise")
        add_if_current("min_persistence_ms", pct * 0.5, "lengthen")
    elif strategy_name == "bb_reversion" and param_name in {"exit_conf_base", "confidence_threshold"}:
        add_if_current("confluence_threshold_no_trade", pct, "raise")
        add_if_current("confluence_threshold_full", pct * 0.5, "raise")
    elif strategy_name == "funding_arb" and param_name in {"min_funding_edge_bps", "funding_threshold"}:
        add_if_current("funding_threshold", pct, "raise")
    elif param_name:
        add_if_current(param_name, pct, direction)
    return candidates

def build_strategy_patch(
    *,
    strategy_name: str,
    recommendation_type: str,
    payload: dict[str, Any],
    current_params: dict[str, Any],
    param_ranges: list[dict[str, Any]],
    cfg: DemoApplierConfig,
) -> dict[str, Any]:
    desired = _derived_strategy_targets(strategy_name, payload, current_params, recommendation_type, cfg)
    ranges = _range_map(param_ranges)
    patch: dict[str, Any] = {}
    for name, want in desired.items():
        if name == "conf_scale":
            cur = float(current_params.get("conf_scale", 1.0) or 1.0)
            val = _bounded_numeric(
                current=cur,
                desired=want,
                min_value=cfg.conf_scale_min,
                max_value=cfg.conf_scale_max,
                max_delta_pct=cfg.max_param_delta_pct,
            )
        else:
            spec = ranges.get(name)
            if spec is None:
                continue
            val = _bounded_numeric(
                current=current_params.get(name),
                desired=want,
                min_value=float(spec.get("min")),
                max_value=float(spec.get("max")),
                step=spec.get("step"),
                max_delta_pct=cfg.max_param_delta_pct,
            )
        if val is None:
            continue
        if current_params.get(name) != val:
            patch[name] = val
    return patch

def _nested_get(root: dict[str, Any], path: tuple[str, ...], default: Any = None) -> Any:
    cur: Any = root
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur

def _put_nested(root: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cur = root
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value

def _bounded_risk_patch(
    raw_patch: dict[str, Any],
    current_risk_config: dict[str, Any],
    cfg: DemoApplierConfig,
) -> dict[str, Any]:
    def walk(raw: dict[str, Any], current: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, desired in raw.items():
            cur = current.get(key) if isinstance(current, dict) else None
            next_path = (*path, str(key))
            if isinstance(desired, dict) and isinstance(cur, dict):
                nested = walk(desired, cur, next_path)
                if nested:
                    out[key] = nested
                continue
            if isinstance(desired, bool) and isinstance(cur, bool):
                if desired != cur:
                    out[key] = desired
                continue
            try:
                cur_f = float(cur)
                want_f = float(desired)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(cur_f) or not math.isfinite(want_f):
                continue
            field = next_path[-1]
            min_value = 0.0001 if field == "per_trade_risk_pct" else 0.0
            if field in {"leverage_max", "open_positions_max"}:
                min_value = 1.0
            max_value = max(cur_f * (1.0 + cfg.max_risk_delta_pct), cur_f, min_value)
            bounded = _bounded_numeric(
                current=cur,
                desired=want_f,
                min_value=min_value,
                max_value=max_value,
                step=1.0 if isinstance(cur, int) and not isinstance(cur, bool) else None,
                max_delta_pct=cfg.max_risk_delta_pct,
            )
            if bounded is not None and bounded != cur:
                out[key] = bounded
        return out
    return walk(raw_patch, current_risk_config, ())

def build_risk_patch(
    *,
    payload: dict[str, Any],
    current_risk_config: dict[str, Any],
    recommendation_type: str,
    cfg: DemoApplierConfig,
) -> dict[str, Any]:
    if isinstance(payload.get("risk_patch"), dict):
        return _bounded_risk_patch(dict(payload["risk_patch"]), current_risk_config, cfg)
    if recommendation_type != "regret_summary":
        return {}

    direction = str(payload.get("net_regret_direction") or "balanced")
    if direction not in {"overtrading", "undertrading"}:
        return {}
    sign = -1.0 if direction == "overtrading" else 0.5
    patch: dict[str, Any] = {}
    for path in (
        ("limits", "per_trade_risk_pct"),
        ("limits", "leverage_max"),
        ("limits", "open_positions_max"),
    ):
        cur = _nested_get(current_risk_config, path)
        if cur is None:
            continue
        try:
            cur_f = float(cur)
        except (TypeError, ValueError):
            continue
        desired = cur_f * (1.0 + sign * cfg.max_risk_delta_pct)
        if path[-1] == "open_positions_max":
            desired = max(1, round(desired))
        bounded = _bounded_numeric(
            current=cur,
            desired=desired,
            min_value=1.0 if path[-1] != "per_trade_risk_pct" else 0.001,
            max_value=max(cur_f * (1.0 + cfg.max_risk_delta_pct), cur_f, 1.0),
            step=1.0 if path[-1] == "open_positions_max" else None,
            max_delta_pct=cfg.max_risk_delta_pct,
        )
        if bounded is not None and bounded != cur:
            _put_nested(patch, path, bounded)
    return patch

def should_create_live_candidate(row: dict[str, Any], cfg: DemoApplierConfig) -> bool:
    try:
        expected = float(row.get("expected_net_bps") or 0.0)
        confidence = float(row.get("confidence") or 0.0)
        samples = int(row.get("sample_count") or 0)
    except (TypeError, ValueError):
        return False
    return (
        expected >= cfg.live_candidate_min_net_bps
        and confidence >= cfg.live_candidate_min_confidence
        and samples >= cfg.live_candidate_min_samples
    )

def _fingerprint(kind: str, target: str, patch: dict[str, Any]) -> str:
    payload = json.dumps({"kind": kind, "target": target, "patch": patch}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

async def _default_ipc_call(method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
    try:
        from exchange_connectors.bybit_connector.control_api_v1.app.ipc_dispatch import (  # type: ignore
            one_shot_ipc_call,
        )
    except ImportError:
        from app.ipc_dispatch import one_shot_ipc_call  # type: ignore
    return await one_shot_ipc_call(
        method,
        params=params,
        timeout=timeout,
        wrap_errors_as_http=False,
        error_context="mlde_demo_applier",
    )

async def _get_strategy_state(ipc_call: IpcCall, engine: str, strategy: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    params_resp = await ipc_call("get_strategy_params", {"engine": engine, "strategy_name": strategy}, 5.0)
    ranges_resp = await ipc_call("get_param_ranges", {"engine": engine, "strategy_name": strategy}, 5.0)
    current = _as_dict(_unwrap_ipc_payload(params_resp))
    ranges_payload = _unwrap_ipc_payload(ranges_resp)
    if isinstance(ranges_payload, str):
        try:
            ranges_payload = json.loads(ranges_payload)
        except json.JSONDecodeError:
            ranges_payload = []
    if isinstance(ranges_payload, dict):
        ranges_payload = ranges_payload.get("ranges", [])
    ranges = ranges_payload if isinstance(ranges_payload, list) else []
    return current, [r for r in ranges if isinstance(r, dict)]

async def _get_risk_config(ipc_call: IpcCall, engine: str) -> dict[str, Any]:
    resp = await ipc_call("get_risk_config", {"engine": engine}, 5.0)
    payload = _unwrap_ipc_payload(resp)
    data = _as_dict(payload)
    return _as_dict(data.get("config", data))

def _fetch_pending(cur: Any, cfg: DemoApplierConfig) -> list[dict[str, Any]]:
    """Fetch eligible MLDE shadow recommendations / 取合資格 MLDE shadow 建議。
    REF-20 P4-S11 forward-compat filter built in sibling helper.
    """
    sql, params = fetch_pending_sql_and_params(
        cur, lookback_hours=cfg.lookback_hours, engine_mode=cfg.engine_mode,
        min_confidence=cfg.min_confidence, min_samples=cfg.min_samples,
        max_recommendations=cfg.max_recommendations,
    )
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]

def _already_applied(cur: Any, fingerprint: str, cfg: DemoApplierConfig) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
              FROM learning.mlde_param_applications
             WHERE ts >= now() - (%s::int || ' hours')::interval
               AND payload->>'fingerprint' = %s
               AND status IN ('applied', 'dry_run', 'skipped')
        )
        """,
        (cfg.dedupe_hours, fingerprint),
    )
    row = cur.fetchone()
    return bool(row and row[0])

def _noop_audit_payload(cur: Any, cfg: DemoApplierConfig) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
            count(*) FILTER (
                WHERE ts >= now() - (%s::int || ' hours')::interval
            )::int AS lookback_recommendations,
            count(*) FILTER (
                WHERE ts >= now() - (%s::int || ' hours')::interval
                  AND engine_mode = %s
            )::int AS demo_recommendations,
            count(*) FILTER (
                WHERE ts >= now() - (%s::int || ' hours')::interval
                  AND engine_mode = %s
                  AND NOT applied
                  AND COALESCE(confidence, 0.0) >= %s
                  AND COALESCE(sample_count, 0) >= %s
            )::int AS eligible_recommendations
        FROM learning.mlde_shadow_recommendations
        """,
        (
            cfg.lookback_hours,
            cfg.lookback_hours,
            cfg.engine_mode,
            cfg.lookback_hours,
            cfg.engine_mode,
            cfg.min_confidence,
            cfg.min_samples,
        ),
    )
    row = cur.fetchone() or (0, 0, 0)
    return {
        "reason": "no_eligible_recommendations",
        "lookback_hours": cfg.lookback_hours,
        "engine_mode": cfg.engine_mode,
        "min_confidence": cfg.min_confidence,
        "min_samples": cfg.min_samples,
        "max_recommendations": cfg.max_recommendations,
        "lookback_recommendations": int(row[0] or 0),
        "demo_recommendations": int(row[1] or 0),
        "eligible_recommendations": int(row[2] or 0),
    }

def _record_noop_audit(cur: Any, cfg: DemoApplierConfig) -> dict[str, Any]:
    payload = _noop_audit_payload(cur, cfg)
    fp = _fingerprint(
        "applier_noop",
        "mlde_demo_applier",
        {
            "engine_mode": cfg.engine_mode,
            "min_confidence": cfg.min_confidence,
            "min_samples": cfg.min_samples,
            "lookback_recommendations": payload["lookback_recommendations"],
            "demo_recommendations": payload["demo_recommendations"],
            "eligible_recommendations": payload["eligible_recommendations"],
        },
    )
    if _already_applied(cur, fp, cfg):
        return {
            "status": "skipped",
            "reason": "no_eligible_recommendations_deduped",
            "target": "mlde_demo_applier",
        }
    _record_application(
        cur,
        row={"engine_mode": cfg.engine_mode, "id": None},
        application_type="strategy_params",
        target_name="mlde_demo_applier",
        patch={},
        prev_snapshot={},
        ipc_response={},
        status="skipped",
        reason="no_eligible_recommendations",
        requires_governance=False,
        payload={**payload, "fingerprint": fp},
    )
    return {
        "status": "skipped",
        "reason": "no_eligible_recommendations",
        "target": "mlde_demo_applier",
        "eligible_recommendations": payload["eligible_recommendations"],
    }

def _record_application(
    cur: Any,
    *,
    row: dict[str, Any],
    application_type: str,
    target_name: str,
    patch: dict[str, Any],
    prev_snapshot: dict[str, Any],
    ipc_response: dict[str, Any],
    status: str,
    reason: str,
    requires_governance: bool,
    payload: dict[str, Any],
) -> int:
    cur.execute(
        """
        INSERT INTO learning.mlde_param_applications
            (engine_mode, recommendation_id, application_type, target_name,
             patch, prev_snapshot, ipc_response, status, reason,
             requires_governance, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            row.get("engine_mode"),
            row.get("id"),
            application_type,
            target_name,
            Json(patch),
            Json(prev_snapshot),
            Json(ipc_response),
            status,
            reason,
            requires_governance,
            Json(payload),
        ),
    )
    return int(cur.fetchone()[0])

def _mark_recommendation_applied(cur: Any, rec_id: int, applied: bool) -> None:
    cur.execute(
        """
        UPDATE learning.mlde_shadow_recommendations
           SET applied = %s,
               requires_governance = CASE WHEN engine_mode IN ('live', 'live_demo') THEN true ELSE false END
         WHERE id = %s
        """,
        (applied, rec_id),
    )

# ────────────────────────────────────────────────────────────────────────────
# LG-5 RFC v2 §2.1 producer-side helper functions for live candidate payload.
# These are pure SQL aggregation helpers operating on a psycopg2 cursor.
# All 4 helpers fail-soft: on SQL exception or missing data, they return a
# well-formed dict with sample_count / n_fills = 0 (consumer side R3 defers
# on insufficient sample). Never raise — payload always emittable.
#
# LG-5 RFC v2 §2.1 producer 側 helper：4 個純 SQL aggregation helper，
# 失敗 fail-soft（SQL 異常或無資料 → 回 well-formed dict 但 sample_count=0），
# 不 raise，確保 payload 永遠可發出。
# ────────────────────────────────────────────────────────────────────────────


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce DB value to float / 將 DB 值安全轉為 float。"""
    if value is None:
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(out):
        return default
    return out


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce DB value to int / 將 DB 值安全轉為 int。"""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _utc_iso8601(when: Optional[_dt.datetime] = None) -> str:
    """Return ISO8601 UTC timestamp / 回 ISO8601 UTC 時戳。"""
    ts = when or _dt.datetime.now(_dt.timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_dt.timezone.utc)
    return ts.isoformat(timespec="seconds")


def _compute_demo_cost_baseline(cur: Any) -> dict[str, Any]:
    """Compute 7d demo cost baseline / 計算 7d demo cost baseline。

    LG-5 RFC v2 §2.1：mirror healthcheck `[33]` (maker_fill_rate / fee_drop)
    + `[40]` (realized net_bps_after_fee) but query independently — does NOT
    rely on healthcheck having run. Aggregates last 7d demo + live_demo
    entry fills.

    LG-5 RFC v2 §2.1：鏡 healthcheck `[33]` (maker_fill_rate / fee_drop)
    + `[40]` (realized net_bps_after_fee)，但獨立查詢（不依賴 healthcheck
    跑過）。彙總 7d demo + live_demo entry fill。

    Returns:
        dict with keys: as_of_ts, engine_mode, maker_fill_rate_7d,
        fee_drop_only_7d, avg_realized_net_bps_7d, avg_realized_fee_bps_7d,
        avg_realized_slippage_bps_7d, sample_count, source_healthchecks.
        Sample_count < 30 → consumer side R3 defers (per RFC §3 R3).
    """
    baseline: dict[str, Any] = {
        "as_of_ts": _utc_iso8601(),
        "engine_mode": "demo",
        "maker_fill_rate_7d": 0.0,
        "fee_drop_only_7d": 0.0,
        "avg_realized_net_bps_7d": 0.0,
        "avg_realized_fee_bps_7d": 0.0,
        "avg_realized_slippage_bps_7d": 0.0,
        "sample_count": 0,
        "source_healthchecks": list(_DEMO_COST_BASELINE_SOURCE_HEALTHCHECKS),
    }

    # Block 1：maker fill / fee aggregation from trading.fills entry rows.
    # 鏡 [33]：7d demo + live_demo 入場 fill 的 effective fee_rate +
    # maker_like ratio。
    try:
        cur.execute(
            """
            WITH entry_fills AS (
                SELECT
                    coalesce(nullif(f.fee_rate, 0), %s)::float8 AS effective_fee_rate,
                    CASE
                        WHEN lower(coalesce(f.liquidity_role, '')) = 'maker'
                          OR coalesce(nullif(f.fee_rate, 0), %s) <= %s
                        THEN 1
                        ELSE 0
                    END AS maker_like
                FROM trading.fills f
                WHERE f.ts > now() - (%s::int || ' days')::interval
                  AND f.engine_mode IN ('demo', 'live_demo')
                  AND coalesce(f.strategy_name, '') <> ''
                  AND f.strategy_name NOT LIKE 'risk_close:%%'
                  AND f.strategy_name NOT LIKE 'strategy_close:%%'
                  AND f.strategy_name NOT LIKE 'ipc_close%%'
                  AND f.strategy_name NOT LIKE 'unattributed:%%'
                  AND coalesce(f.exit_source, '') = ''
            """ + _strategy_entry_fill_predicate() + """
            )
            SELECT
                count(*)::int AS total_fills,
                coalesce(sum(maker_like), 0)::int AS maker_like_fills,
                coalesce(avg(effective_fee_rate), %s)::float8 AS avg_fee_rate
            FROM entry_fills
            """,
            (
                _TAKER_FEE_RATE,
                _TAKER_FEE_RATE,
                _MAKER_FEE_CUTOFF,
                _DEMO_BASELINE_WINDOW_DAYS,
                _TAKER_FEE_RATE,
            ),
        )
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - producer fail-soft
        logger.warning("lg5 cost baseline maker query failed: %s", exc)
        row = None

    if row is not None:
        total = _safe_int(row[0])
        maker_like = _safe_int(row[1])
        avg_fee_rate = _safe_float(row[2], _TAKER_FEE_RATE)
        baseline["sample_count"] = total
        if total > 0:
            baseline["maker_fill_rate_7d"] = maker_like / total
        # fee drop = (taker_default - effective_fee) / taker_default; clamp [0, 1].
        # fee drop = (taker 預設 - 實際 fee) / taker 預設；clamp [0, 1]。
        fee_drop = max(
            0.0,
            min(1.0, (_TAKER_FEE_RATE - avg_fee_rate) / max(_TAKER_FEE_RATE, 1e-12)),
        )
        baseline["fee_drop_only_7d"] = fee_drop
        # avg fee in bps for LG-5 R5 cost_edge_ratio computation.
        # avg fee 換成 bps，供 LG-5 R5 cost_edge_ratio 用。
        baseline["avg_realized_fee_bps_7d"] = avg_fee_rate * 10_000.0

    # Block 2：realized net_bps + slippage from MLDE training rows view.
    # 鏡 [40]：7d MLDE training row 的 net_bps_after_fee 與 slippage_bps。
    try:
        cur.execute(
            "SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL"
        )
        view_exists = cur.fetchone()
    except Exception:  # noqa: BLE001
        view_exists = (False,)

    if view_exists and view_exists[0]:
        try:
            cur.execute(
                """
                SELECT
                    coalesce(avg(net_bps_after_fee), 0.0)::float8 AS avg_net_bps,
                    coalesce(avg(slippage_bps), 0.0)::float8 AS avg_slip_bps
                FROM learning.mlde_edge_training_rows
                WHERE ts > now() - (%s::int || ' days')::interval
                  AND engine_mode IN ('demo', 'live_demo')
                  AND attribution_chain_ok
                  AND net_bps_after_fee IS NOT NULL
                """,
                (_DEMO_BASELINE_WINDOW_DAYS,),
            )
            row2 = cur.fetchone()
        except Exception as exc:  # noqa: BLE001
            logger.warning("lg5 cost baseline net_bps query failed: %s", exc)
            row2 = None

        if row2 is not None:
            baseline["avg_realized_net_bps_7d"] = _safe_float(row2[0], 0.0)
            baseline["avg_realized_slippage_bps_7d"] = _safe_float(row2[1], 0.0)

    return baseline


def _compute_demo_realized_window(
    cur: Any,
    strategy_name: Optional[str] = None,
) -> dict[str, Any]:
    """Compute 7d realized fill window / 計算 7d realized fill 窗口。

    LG-5 RFC v2 §2.1：emits ISO8601 start/end ts + total fill count + per-
    strategy fill count for the candidate's strategy slice. Consumer (R3
    PSR) uses ``n_strategy_fills`` directly to qualify sample sufficiency
    (RFC §3 R3：`n_strategy_fills < 100 → defer`)。

    LG-5 RFC v2 §2.1：發出 ISO8601 start/end ts + 全部 fill 計數 + per-strategy
    fill 計數。Consumer (R3 PSR) 直接讀 ``n_strategy_fills`` 判定 sample 是否
    足夠（RFC §3 R3：`n_strategy_fills < 100 → defer`）。

    Round 2 fix (LG-5 IMPL-1 round 2)：先前 ``n_strategy_fills`` 硬編 0，
    consumer R3 永久 defer。本版改為呼叫
    ``_compute_demo_sample_count_strategy_cell`` 取得 per-strategy cell
    sample count（與 attribution_chain_ok 過濾一致），讓 R3 真正能 promote。

    Round 2 fix (LG-5 IMPL-1 round 2): previously ``n_strategy_fills`` was
    hardcoded 0, causing consumer R3 to defer all candidates. This version
    populates it via ``_compute_demo_sample_count_strategy_cell`` (same
    attribution_chain_ok filter as MF-M2), so R3 can actually promote.
    """
    end_ts = _dt.datetime.now(_dt.timezone.utc)
    start_ts = end_ts - _dt.timedelta(days=_DEMO_BASELINE_WINDOW_DAYS)
    # Pull per-strategy cell sample count first so it is consistent with
    # MF-M2 attribution semantics (same view + same filter).
    # 先取 per-strategy cell sample count，與 MF-M2 attribution 語意一致。
    n_strategy_fills = _compute_demo_sample_count_strategy_cell(
        cur,
        strategy_name if isinstance(strategy_name, str) else None,
    )
    window: dict[str, Any] = {
        "start_ts": _utc_iso8601(start_ts),
        "end_ts": _utc_iso8601(end_ts),
        "n_fills": 0,
        "n_strategy_fills": n_strategy_fills,
        "window_days": _DEMO_BASELINE_WINDOW_DAYS,
    }

    try:
        cur.execute(
            """
            SELECT count(*)::int
              FROM trading.fills
             WHERE ts > now() - (%s::int || ' days')::interval
               AND engine_mode IN ('demo', 'live_demo')
            """,
            (_DEMO_BASELINE_WINDOW_DAYS,),
        )
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        logger.warning("lg5 realized_window n_fills query failed: %s", exc)
        row = None

    if row is not None:
        window["n_fills"] = _safe_int(row[0])

    return window


def _compute_attribution_chain_ratio_by_strategy(cur: Any) -> dict[str, float]:
    """Compute per-strategy 3d attribution_chain_ok ratio (R-meta gate input).
    計算 per-strategy 3d attribution_chain_ok 比率（R-meta gate 輸入源）。

    LG-5 RFC v2 §2.1 + MIT MF-M2 + Fix 2 amendment (PA RFC 2026-05-02):
    R-meta window aligned to post-bug-fix 3d (vs cost baseline 7d in
    ``_compute_demo_cost_baseline`` / ``_compute_demo_realized_window``).
    Returns dict keyed by 5 hardcoded strategy names; missing data → 0.0
    (consumer R-meta defers per strategy; pair with
    ``_compute_attribution_sample_count_by_strategy`` +
    ``_R_META_MIN_SAMPLE_PER_STRATEGY=10`` to split "broken" vs "3d
    insufficient"). NOT a global average — per-strategy is structural.

    LG-5 RFC v2 §2.1 + MIT MF-M2 + Fix 2 amendment（PA RFC 2026-05-02）：
    R-meta 對齊已修 bug 後 3d (vs cost baseline 7d)。回傳 5 key dict；缺者
    → 0.0（consumer R-meta per strategy defer；配 sample_count helper +
    _R_META_MIN_SAMPLE_PER_STRATEGY=10 區分「真壞」vs「3d 樣本不足」）。
    這 **不是** global 平均 — per-strategy 結構性必須。
    """
    ratios: dict[str, float] = {key: 0.0 for key in _ATTRIBUTION_STRATEGY_KEYS}

    try:
        cur.execute(
            "SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL"
        )
        view_exists = cur.fetchone()
    except Exception:  # noqa: BLE001
        return ratios
    if not view_exists or not view_exists[0]:
        return ratios

    try:
        cur.execute(
            """
            SELECT
                strategy_name,
                count(*)::int AS total,
                count(*) FILTER (WHERE attribution_chain_ok)::int AS ok_count
              FROM learning.mlde_edge_training_rows
             WHERE ts > now() - (%s::int || ' days')::interval
               AND engine_mode IN ('demo', 'live_demo')
               AND coalesce(strategy_name, '') = ANY(%s)
             GROUP BY strategy_name
            """,
            # Fix 2: window 從 7d 縮 3d（_R_META_WINDOW_DAYS）對齊已修 bug
            # 後時段；cost baseline 不動仍走 _DEMO_BASELINE_WINDOW_DAYS=7。
            # Fix 2: window 7d → 3d via _R_META_WINDOW_DAYS to align with
            # post-bug-fix slice; cost baseline still uses 7d.
            (_R_META_WINDOW_DAYS, list(_ATTRIBUTION_STRATEGY_KEYS)),
        )
        rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("lg5 attribution per-strategy ratio query failed: %s", exc)
        rows = []

    for row in rows:
        # row tuple: (strategy_name, total, ok_count)
        name = str(row[0]) if row[0] is not None else ""
        if name not in ratios:
            continue
        total = _safe_int(row[1])
        ok_count = _safe_int(row[2])
        if total > 0:
            ratios[name] = ok_count / total

    return ratios


def _compute_attribution_sample_count_by_strategy(cur: Any) -> dict[str, int]:
    """Per-strategy sample count over R-meta 3d window.
    計算 R-meta 3d 窗口內 per-strategy sample 數。

    LG-5 W3 FUP-2 Fix 2 (PA RFC 2026-05-02 §9.3): producer-side companion
    to ``_compute_attribution_chain_ratio_by_strategy``. Consumer R-meta
    gate uses this dict + ``_R_META_MIN_SAMPLE_PER_STRATEGY=10`` to emit
    ``defer_attribution_chain_low_sample`` (vs ``reject_attribution_chain_
    too_broken``) so low-cardinality strategies (bb_breakout / bb_reversion
    ~13 / ~2-3 in 3d per RFC §9.2) are not permanently deferred. Filter
    mirrors ratio helper exactly (same window / engine_mode / strategy
    keyset). Returns dict keyed by all 5 ``_ATTRIBUTION_STRATEGY_KEYS``;
    missing → 0 (fail-soft).

    LG-5 W3 FUP-2 Fix 2（PA RFC 2026-05-02 §9.3）：producer 端 ratio helper
    的 sample-count 配對。Consumer R-meta gate 配 _R_META_MIN_SAMPLE_PER_
    STRATEGY=10 區分「真壞」vs「3d 樣本不足」(後者發
    defer_attribution_chain_low_sample)；避免 bb_breakout / bb_reversion 永久
    defer。Filter 與 ratio helper 完全一致 (window / engine_mode / keyset)。
    回傳 5 key dict；缺者 → 0 fail-soft。
    """
    counts: dict[str, int] = {key: 0 for key in _ATTRIBUTION_STRATEGY_KEYS}

    try:
        cur.execute(
            "SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL"
        )
        view_exists = cur.fetchone()
    except Exception:  # noqa: BLE001
        return counts
    if not view_exists or not view_exists[0]:
        return counts

    try:
        cur.execute(
            """
            SELECT
                strategy_name,
                count(*)::int AS total
              FROM learning.mlde_edge_training_rows
             WHERE ts > now() - (%s::int || ' days')::interval
               AND engine_mode IN ('demo', 'live_demo')
               AND coalesce(strategy_name, '') = ANY(%s)
             GROUP BY strategy_name
            """,
            # 與 ratio helper 共用 _R_META_WINDOW_DAYS / strategy keyset
            # 確保 consumer 拿 ratio + sample_count 來自同一 window slice。
            # Share _R_META_WINDOW_DAYS + strategy keyset with ratio helper
            # so consumer reads both from the same window slice.
            (_R_META_WINDOW_DAYS, list(_ATTRIBUTION_STRATEGY_KEYS)),
        )
        rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lg5 attribution per-strategy sample_count query failed: %s", exc
        )
        rows = []

    for row in rows:
        # row tuple: (strategy_name, total)
        name = str(row[0]) if row[0] is not None else ""
        if name not in counts:
            continue
        counts[name] = _safe_int(row[1])

    return counts


def _compute_demo_sample_count_strategy_cell(
    cur: Any,
    strategy_name: Optional[str],
) -> int:
    """Compute 7d cell-level sample count for one strategy.
    計算特定 strategy 的 7d cell-level sample count。

    LG-5 RFC v2 §2.1：per-strategy fill count over 7d demo + live_demo
    window, restricted to cells with attribution_chain_ok = true (mirrors
    [40] training-row eligibility). Consumer R3 uses this as the strategy
    cell sample for PSR n threshold (n < 100 → defer per RFC §3 R3).

    LG-5 RFC v2 §2.1：per-strategy 7d fill 計數，限 attribution_chain_ok=true
    （對齊 [40] training row 條件）。Consumer R3 用此作 PSR n 門檻
    （n < 100 → defer，per RFC §3 R3）。
    """
    if not strategy_name:
        return 0

    try:
        cur.execute(
            "SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL"
        )
        view_exists = cur.fetchone()
    except Exception:  # noqa: BLE001
        return 0
    if not view_exists or not view_exists[0]:
        return 0

    try:
        cur.execute(
            """
            SELECT count(*)::int
              FROM learning.mlde_edge_training_rows
             WHERE ts > now() - (%s::int || ' days')::interval
               AND engine_mode IN ('demo', 'live_demo')
               AND attribution_chain_ok
               AND strategy_name = %s
            """,
            (_DEMO_BASELINE_WINDOW_DAYS, strategy_name),
        )
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        logger.warning("lg5 strategy_cell sample_count query failed: %s", exc)
        return 0

    return _safe_int(row[0]) if row else 0


def _build_live_candidate_payload(
    cur: Any,
    *,
    source_row: dict[str, Any],
    application_id: int,
    application_type: str,
    patch: dict[str, Any],
    strategy_name: Optional[str],
) -> dict[str, Any]:
    """Build LG-5 RFC v2 §2.1 compliant live candidate payload.
    建構符合 LG-5 RFC v2 §2.1 規格的 live candidate payload。

    Single source of truth for the 5-key LG-5 producer payload. Used by
    BOTH writers:

      1. ``_insert_live_candidate`` → ``learning.mlde_shadow_recommendations``
         (audit / monitoring path; other readers may depend on it).
      2. ``_apply_one``'s ``_record_application(...)`` candidate row →
         ``learning.mlde_param_applications`` filter
         ``engine_mode='live' AND status='candidate' AND
         application_type='live_promotion_candidate'`` — this is the row
         consumer ``GovernanceHub.review_live_candidate`` reads (RFC v2
         §2.2 line 140 + MIT MF-M3 absorbed verdict).

    Consumer fail-closes on missing or wrong ``schema_version`` (defer /
    reject ``schema_unknown``); centralising payload construction here
    prevents the round-1 spec drift where only writer #1 carried full LG-5
    sub-keys while writer #2 (the one consumer actually reads) was a bare
    2-key payload — making the entire LG-5 governance pipeline silently
    inert for new candidates.

    Each helper called below is fail-soft (returns a well-formed dict / 0
    on SQL exception), so this function never raises due to baseline
    failure; the payload is always emittable.

    本函數是 LG-5 producer payload 5-key 規格的單一 SoT，兩處 writer 共用：
      1. ``_insert_live_candidate`` 寫 ``mlde_shadow_recommendations``
         （audit / monitoring 路徑，其他 reader 可能依賴）
      2. ``_apply_one`` 的 ``_record_application(...)`` candidate row 寫入
         ``mlde_param_applications``，consumer
         ``GovernanceHub.review_live_candidate`` 讀的就是這張表
         （RFC v2 §2.2 line 140 + MIT MF-M3 absorbed verdict）

    Consumer 對 missing / wrong ``schema_version`` fail-closed
    （defer / reject ``schema_unknown``）；集中 payload 建構在此可防
    round-1 的 spec drift —— 當時只有 writer #1 帶完整 LG-5 sub-key、
    writer #2（consumer 真正讀的那張表）只有 bare 2-key payload，導致
    整條 LG-5 governance pipeline 對所有新 candidate silently 失效。

    下方每個 helper 都 fail-soft（SQL 異常回 well-formed dict / 0），
    所以本函數絕不因 baseline 失敗而 raise，payload 永遠可發出。
    """
    demo_cost_baseline = _compute_demo_cost_baseline(cur)
    # Pass strategy_name into the realized_window helper so it can populate
    # ``n_strategy_fills`` (RFC §3 R3 reads this column directly).
    # 將 strategy_name 傳入 realized_window helper 讓它填寫 ``n_strategy_fills``
    # （RFC §3 R3 直接讀此欄位判斷 promote / defer）。
    demo_realized_window = _compute_demo_realized_window(cur, strategy_name)
    attribution_by_strategy = _compute_attribution_chain_ratio_by_strategy(cur)
    # LG-5 W3 FUP-2 Fix 2: paired sample-count dict so consumer R-meta gate
    # can apply ``_R_META_MIN_SAMPLE_PER_STRATEGY=10`` low-sample defer
    # logic (PA RFC 2026-05-02 §9.3). Filter mirrors ratio helper exactly.
    # LG-5 W3 FUP-2 Fix 2：sample-count 配對 dict，供 consumer R-meta gate
    # 套用 _R_META_MIN_SAMPLE_PER_STRATEGY=10 低樣本 defer 邏輯
    # （PA RFC 2026-05-02 §9.3）。Filter 與 ratio helper 完全一致。
    attribution_sample_count_by_strategy = (
        _compute_attribution_sample_count_by_strategy(cur)
    )
    sample_count_strategy_cell = _compute_demo_sample_count_strategy_cell(
        cur,
        strategy_name if isinstance(strategy_name, str) else None,
    )
    return {
        "policy": "live_governed_promotion_candidate",
        "schema_version": _LIVE_CANDIDATE_EVAL_SCHEMA_VERSION,
        "source_demo_recommendation_id": source_row.get("id"),
        "source_demo_application_id": application_id,
        "application_type": application_type,
        "patch": patch,
        "requires": ["GovernanceHub", "DecisionLease", "live_gates"],
        "demo_cost_baseline": demo_cost_baseline,
        "demo_realized_window": demo_realized_window,
        "demo_attribution_chain_ratio_by_strategy": attribution_by_strategy,
        # LG-5 W3 FUP-2 Fix 2 NEW sub-keys: 明示 R-meta gate window (3d) +
        # 提供 per-strategy sample count 給 consumer low-sample defer 邏輯。
        # 既有 27 pending candidates payload 缺此兩 key → consumer 視為
        # v1 (default 7d) backward-compat (per RFC §6.1)。
        # LG-5 W3 FUP-2 Fix 2 新 sub-key：明示 R-meta gate 窗口 (3d) +
        # 提供 per-strategy sample count 給 consumer low-sample defer。
        # 既有 27 pending candidates 缺此兩 key → consumer 視為 v1
        # (default 7d) backward-compat（per RFC §6.1）。
        "demo_attribution_window_days": _R_META_WINDOW_DAYS,
        "demo_attribution_sample_count_by_strategy": (
            attribution_sample_count_by_strategy
        ),
        "demo_sample_count_strategy_cell": sample_count_strategy_cell,
    }


def _insert_live_candidate(
    cur: Any,
    *,
    source_row: dict[str, Any],
    application_id: int,
    application_type: str,
    patch: dict[str, Any],
) -> None:
    """Insert a live promotion candidate row with LG-5 §2.1 payload.
    插入一筆 live promotion candidate row，payload 符合 LG-5 §2.1。

    LG-5 RFC v2 §2.1 producer side：原本三個 demo 數值 (expected_net_bps /
    confidence / sample_count) 仍直接拷貝至 column；payload JSONB 由
    ``_build_live_candidate_payload`` 統一建構（含 ``schema_version`` + 4
    新 sub-key）。注意此處寫的是 ``mlde_shadow_recommendations``（audit /
    monitoring 路徑），consumer 真正讀的 row 由 ``_apply_one`` 的
    ``_record_application(...)`` 寫入 ``mlde_param_applications``（兩處
    payload 同源，由 helper 保證 1:1）。

    LG-5 RFC v2 §2.1 producer side: three demo numbers still copied
    verbatim to columns; payload JSONB built via
    ``_build_live_candidate_payload`` (single SoT shared with the
    ``mlde_param_applications`` writer the consumer actually reads).

    REF-20 W3-P2a-S4 切換 / migration:
        改呼叫 learning.verify_replay_evidence_and_insert() (V036)；
        engine_mode='live' / source='ml_shadow' / recommendation_type=
        'experiment_plan' / created_by='mlde_demo_applier' 全部保留 (per
        PM dispatch §2 #2 + V3 §4.2 P0-T7 classification — 27 既有
        engine_mode='live' row 全屬 evidence_source_tier='real_outcome'
        legacy audit trail 路徑，非 replay-derived)。LG-5 §2.1
        ``schema_version`` payload 經 ``_build_live_candidate_payload``
        helper 已注入；本 function 不解構或重建 payload。
        Switched to learning.verify_replay_evidence_and_insert() (V036).
        engine_mode='live' / source='ml_shadow' / recommendation_type=
        'experiment_plan' / created_by='mlde_demo_applier' all preserved
        (per PM dispatch §2 #2 + V3 §4.2 P0-T7 classification: the
        existing 27 engine_mode='live' rows are all legacy audit trail
        rows under evidence_source_tier='real_outcome', NOT replay-
        derived). LG-5 §2.1 ``schema_version`` payload is injected by
        ``_build_live_candidate_payload`` helper; this function does not
        decompose or rebuild the payload.
    """
    strategy_name = source_row.get("strategy_name")
    payload = _build_live_candidate_payload(
        cur,
        source_row=source_row,
        application_id=application_id,
        application_type=application_type,
        patch=patch,
        strategy_name=strategy_name if isinstance(strategy_name, str) else None,
    )
    # REF-20 W3-P2a-S4: 切換到 verified insert function (V036).
    # 保留 hardcoded 'live' engine_mode + LG-5 §2.1 schema_version payload；
    # evidence_source_tier='real_outcome' 對應 V3 §4.2 P0-T7 classification:
    # demo→live promotion candidate audit row 屬 legacy producer 路徑。
    # 任何 schema 漂移會 break LG-5 reviewer pipeline (sibling CC
    # commit 463890d Lg5_review_consumer)，下游讀 mlde_param_applications
    # FK 回 mlde_shadow_recommendations.id 必保留 sequence allocation。
    #
    # REF-20 W3-P2a-S4: switch to verified insert function (V036).
    # Hardcoded 'live' engine_mode + LG-5 §2.1 schema_version payload
    # preserved verbatim; evidence_source_tier='real_outcome' aligns with
    # V3 §4.2 P0-T7 classification (demo→live promotion candidate audit
    # row is legacy producer path, NOT replay-derived). Any schema drift
    # would break the LG-5 reviewer pipeline (sibling CC commit 463890d
    # Lg5_review_consumer); downstream mlde_param_applications FK to
    # mlde_shadow_recommendations.id requires sequence allocation
    # preservation.
    cur.execute(
        """
        SELECT learning.verify_replay_evidence_and_insert(
            'live',                         -- p_engine_mode (hardcoded for LG-5 §2.1 audit trail)
            %s,                             -- p_symbol
            %s,                             -- p_strategy_name
            'ml_shadow',                    -- p_source (hardcoded LG-5 contract)
            'experiment_plan',              -- p_recommendation_type (hardcoded LG-5 contract)
            %s,                             -- p_expected_net_bps
            %s,                             -- p_confidence
            %s,                             -- p_sample_count
            %s,                             -- p_payload (LG-5 §2.1 schema_version preserved)
            false,                          -- p_applied
            true,                           -- p_requires_governance
            'mlde_demo_applier',            -- p_created_by
            'real_outcome',                 -- p_evidence_source_tier (legacy LG-5 audit row)
            NULL, NULL, NULL,               -- replay metadata (NULL for real_outcome)
            NULL, NULL, NULL                -- decision_lease_id / context_id / intent_id
        )
        """,
        (
            source_row.get("symbol"),
            source_row.get("strategy_name"),
            source_row.get("expected_net_bps"),
            source_row.get("confidence"),
            source_row.get("sample_count"),
            Json(payload),
        ),
    )

def _record_skip(
    cur: Any,
    *,
    row: dict[str, Any],
    reason: str,
    application_type: str = "strategy_params",
    target_name: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _record_application(
        cur,
        row=row,
        application_type=application_type,
        target_name=target_name or str(row.get("strategy_name") or "unknown"),
        patch={},
        prev_snapshot={},
        ipc_response={},
        status="skipped",
        reason=reason,
        requires_governance=False,
        payload=payload or {},
    )
    _mark_recommendation_applied(cur, int(row["id"]), True)
    return {"status": "skipped", "reason": reason}

async def _apply_one(
    cur: Any,
    row: dict[str, Any],
    cfg: DemoApplierConfig,
    ipc_call: IpcCall,
) -> dict[str, Any]:
    payload = _as_dict(row.get("payload"))
    rec_type = str(row.get("recommendation_type") or "")
    strategy = str(row.get("strategy_name") or "")
    if row.get("engine_mode") != cfg.engine_mode or cfg.engine_mode != "demo":
        return _record_skip(cur, row=row, reason="non_demo_engine")
    if rec_type == "regret_summary" or isinstance(payload.get("risk_patch"), dict):
        current_risk = await _get_risk_config(ipc_call, cfg.engine_mode)
        patch = build_risk_patch(
            payload=payload,
            current_risk_config=current_risk,
            recommendation_type=rec_type,
            cfg=cfg,
        )
        kind = "risk_config"
        target = "risk_config"
        prev = current_risk
    else:
        if not strategy or strategy == "unknown":
            return _record_skip(cur, row=row, reason="missing_strategy")
        current_params, ranges = await _get_strategy_state(ipc_call, cfg.engine_mode, strategy)
        patch = build_strategy_patch(
            strategy_name=strategy,
            recommendation_type=rec_type,
            payload=payload,
            current_params=current_params,
            param_ranges=ranges,
            cfg=cfg,
        )
        kind = "strategy_params"
        target = strategy
        prev = current_params
    if not patch:
        return _record_skip(
            cur,
            row=row,
            reason="empty_patch",
            application_type=kind,
            target_name=target,
            payload={"source_payload": payload},
        )
    fp = _fingerprint(kind, target, patch)
    if _already_applied(cur, fp, cfg):
        _record_application(
            cur,
            row=row,
            application_type=kind,
            target_name=target,
            patch=patch,
            prev_snapshot=prev,
            ipc_response={},
            status="skipped",
            reason="dedupe",
            requires_governance=False,
            payload={"fingerprint": fp},
        )
        _mark_recommendation_applied(cur, int(row["id"]), True)
        return {"status": "skipped", "reason": "dedupe"}
    if cfg.dry_run:
        status = "dry_run"
        ipc_response: dict[str, Any] = {"dry_run": True}
    elif kind == "strategy_params":
        ipc_response = await ipc_call(
            "update_strategy_params",
            {
                "engine": cfg.engine_mode,
                "strategy_name": target,
                "params_json": json.dumps(patch, separators=(",", ":")),
            },
            5.0,
        )
        status = "applied"
    else:
        ipc_response = await ipc_call(
            "patch_risk_config",
            {"engine": cfg.engine_mode, "source": "agent", "patch": patch},
            5.0,
        )
        status = "applied"
    app_id = _record_application(
        cur,
        row=row,
        application_type=kind,
        target_name=target,
        patch=patch,
        prev_snapshot=prev,
        ipc_response=ipc_response,
        status=status,
        reason=f"mlde:{row.get('source')}:{rec_type}",
        requires_governance=False,
        payload={"fingerprint": fp, "source_payload": payload},
    )
    _mark_recommendation_applied(cur, int(row["id"]), status in {"applied", "dry_run"})
    live_candidate = False
    if status == "applied" and should_create_live_candidate(row, cfg):
        _insert_live_candidate(
            cur,
            source_row=row,
            application_id=app_id,
            application_type=kind,
            patch=patch,
        )
        # CRITICAL (LG-5 IMPL-1 round 2)：consumer
        # ``GovernanceHub.review_live_candidate`` reads from
        # ``mlde_param_applications`` (RFC v2 §2.2 line 140), NOT from
        # ``mlde_shadow_recommendations``. The payload here MUST carry the
        # full LG-5 §2.1 contract (schema_version + 4 sub-keys) or consumer
        # defers / rejects ``schema_unknown`` and the entire pipeline goes
        # silently inert. Build via shared helper so two writers stay 1:1.
        # CRITICAL (LG-5 IMPL-1 round 2)：consumer
        # ``GovernanceHub.review_live_candidate`` 讀的是
        # ``mlde_param_applications``（RFC v2 §2.2 line 140），不是
        # ``mlde_shadow_recommendations``；payload 必須帶完整 LG-5 §2.1
        # contract（schema_version + 4 sub-key），否則 consumer 對所有
        # candidate defer / reject ``schema_unknown``，整條 pipeline 失效。
        # 透過共用 helper 建構，與另一寫入點保持 1:1。
        live_candidate_payload = _build_live_candidate_payload(
            cur,
            source_row=row,
            application_id=app_id,
            application_type=kind,
            patch=patch,
            strategy_name=str(row.get("strategy_name") or "") or None,
        )
        _record_application(
            cur,
            row={**row, "engine_mode": "live"},
            application_type="live_promotion_candidate",
            target_name=target,
            patch=patch,
            prev_snapshot={},
            ipc_response={},
            status="candidate",
            reason="positive_demo_evidence_governed_live_candidate",
            requires_governance=True,
            payload=live_candidate_payload,
        )
        live_candidate = True
    return {"status": status, "application_type": kind, "target": target,
            "patch_keys": sorted(patch.keys()), "live_candidate": live_candidate}

async def _run_async(
    dsn: str,
    cfg: DemoApplierConfig,
    ipc_call: IpcCall,
) -> dict[str, Any]:
    if psycopg2 is None or DictCursor is None or Json is None:
        raise RuntimeError("psycopg2 not installed")
    summary: dict[str, Any] = {
        "enabled": cfg.enabled,
        "engine_mode": cfg.engine_mode,
        "seen": 0,
        "applied": 0,
        "dry_run": 0,
        "skipped": 0,
        "failed": 0,
        "live_candidates": 0,
        "details": [],
    }
    if not cfg.enabled:
        return summary
    if cfg.engine_mode != "demo":
        summary["skipped"] = 1
        summary["details"].append({"status": "skipped", "reason": "non_demo_config"})
        return summary
    with psycopg2.connect(dsn, connect_timeout=2, cursor_factory=DictCursor) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            rows = _fetch_pending(cur, cfg)
            summary["seen"] = len(rows)
            if not rows:
                result = _record_noop_audit(cur, cfg)
                summary["skipped"] += 1
                summary["details"].append(result)
                conn.commit()
                return summary
            for row in rows:
                try:
                    result = await _apply_one(cur, row, cfg, ipc_call)
                    status = str(result.get("status") or "skipped")
                    if status == "applied":
                        summary["applied"] += 1
                    elif status == "dry_run":
                        summary["dry_run"] += 1
                    elif status == "skipped":
                        summary["skipped"] += 1
                    else:
                        summary["failed"] += 1
                    if result.get("live_candidate"):
                        summary["live_candidates"] += 1
                    summary["details"].append(result)
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    conn.rollback()
                    summary["failed"] += 1
                    summary["details"].append({"status": "failed", "recommendation_id": row.get("id"), "error": str(exc)})
                    try:
                        _record_application(
                            cur,
                            row=row,
                            application_type="strategy_params",
                            target_name=str(row.get("strategy_name") or "unknown"),
                            patch={},
                            prev_snapshot={},
                            ipc_response={},
                            status="failed",
                            reason=str(exc),
                            requires_governance=False,
                            payload={},
                        )
                        conn.commit()
                    except Exception:
                        conn.rollback()
    return summary

def run_mlde_demo_applier(
    dsn: Optional[str] = None,
    cfg: Optional[DemoApplierConfig] = None,
    *,
    ipc_call: Optional[IpcCall] = None,
) -> dict[str, Any]:
    cfg = cfg or config_from_env()
    resolved = _resolve_dsn(dsn)
    if not resolved:
        return {"enabled": cfg.enabled, "skipped": "no_database_url", "applied": 0}
    return asyncio.run(_run_async(resolved, cfg, ipc_call or _default_ipc_call))
