from __future__ import annotations

"""
Strategist Promote Routes — operator API for manual params promotion.
策略師手動晉升路由 — Operator 手動把已穩定參數晉升至目標引擎。

MODULE_NOTE (EN):
  G3-10 (STRATEGIST-PROMOTE-TRIGGER-1) — operator-facing IPC bridge that
  promotes a `learning.strategist_applied_params` row from a *source* engine
  (typically demo) into a *target* engine (typically live), bypassing the
  AUTO-PROMOTE counter when an operator deems the value safe to ship.

  Two-step confirm flow (mirrors live_session-style operator workflows):
    1. POST with `confirm=false` → 200 + preview JSON
       (current params on target vs source params + diff). NO IPC dispatch,
       NO config mutation, NO audit row written. Operator inspects + decides.
    2. POST with `confirm=true`  → IPC `update_strategy_params` against
       target engine + audit log entry. The Rust side validates the params
       against the strategy's typed `update_params_json` (CONF-D
       conf_scale strip-and-apply) before swapping ConfigStore.

  Endpoint:
    POST /api/v1/strategist/promote
      body:
        strategy:       "ma_crossover" | "bb_reversion" | "bb_breakout" |
                        "grid_trading" | "funding_arb"   (whitelisted)
        symbol:         str (audit / log scoping; **no DB filter**, see
                        "Why no symbol scoping" below)
        source_engine:  "demo" | "paper"  (read latest applied row here)
        target_engine:  "live" | "paper"  (apply params here via IPC)
        source:         str (audit provenance; default "operator")
        confirm:        bool (false → preview, true → apply)

  Auth gates (mirrors executor_routes.shadow-toggle matrix):
    - Always: Operator role (current_actor + role check).
    - target_engine="live" + confirm=true → full 5-gate live chain
      (Operator + live_reserved + OPENCLAW_ALLOW_MAINNET + secret slot +
       authorization.json HMAC/expiry/env_allowed). Reuses
       executor_routes._verify_live_gate.
    - target_engine="paper" → Operator role only.
    - Preview (confirm=false) → Operator role only on any engine, no IPC.
      Preview cannot be used to leak Rust config; it only reads PG audit
      rows + the same `get_strategy_params` IPC the GUI history tab calls.
    - source_engine == target_engine → 400 (silly request).

  Why no symbol scoping (important):
    `learning.strategist_applied_params` schema (V019/V020) has only
    (engine_mode, strategy_name) — strategy params apply across all symbols
    that the strategy trades. We accept `symbol` in the body for
    audit/log scoping (operator's mental model is "ORDIUSDT looks great on
    grid") but do NOT filter PG by symbol. The audit row records the
    requested symbol so post-mortem can see operator intent without
    misleading them about per-symbol independence.

  IPC contract:
    On confirm=true success → `update_strategy_params` IPC with
      params = {
        "strategy": "<strategy>",
        "params_json": "<source_params_json_string>",
        "engine": "<target_engine>",
      }
    Rust side dispatches via `dispatch_request` → engine cmd channel →
    `event_consumer/handlers/strategy_params::handle_update_strategy_params`,
    which validates + swaps ConfigStore and persists via the same
    `strategist_scheduler::persist_applied_params` path (with
    source='manual_promote').

  On gate failure: 403 + structured `gate_failed` payload. Audit row
  written for both denial + success.

  Optional `learning.strategist_promotions` table is NOT created here; the
  same audit trail is achieved via change_audit_log + the existing
  strategist_applied_params row that Rust will write when it persists the
  IPC apply with `source='manual_promote'`.

MODULE_NOTE (中):
  G3-10 STRATEGIST-PROMOTE-TRIGGER-1 — Operator 手動把 demo 上穩定的策略參數
  晉升至 live (或 paper)；繞過 AUTO-PROMOTE counter 但不繞過 5-gate live 鏈。
  兩步 confirm（confirm=false 預覽 / confirm=true 套用）；身分驗證沿用
  executor_routes 的 5-gate。Schema 僅有 (engine_mode, strategy_name) 欄位，
  symbol 只用於 audit scope hint 不參與 SQL 過濾。
"""

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import main_legacy as base
from .db_pool import get_pg_conn
from .ipc_dispatch import one_shot_ipc_call

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════

strategist_promote_router = APIRouter(
    prefix="/api/v1/strategist",
    tags=["Strategist Promote / 策略師參數晉升"],
)


# ── Whitelists / 白名單 ───────────────────────────────────────────────────────
# Sources / targets are a tighter subset than executor_routes' engine list:
# we explicitly forbid lifting **out of live** because a live row should
# never be re-applied on demo / paper (no edge benefit; risks polluting demo
# baseline). live can only be a target.
# 來源/目標白名單比 executor_routes 收緊：禁止 live → demo/paper（無 edge
# 益處且會污染 demo baseline）。live 只能當目標。
_ALLOWED_SOURCE_ENGINES: frozenset[str] = frozenset({"demo", "paper"})
_ALLOWED_TARGET_ENGINES: frozenset[str] = frozenset({"live", "paper"})

# Strategy whitelist mirrors strategist_history_routes._ALLOWED_STRATEGIES so
# both endpoints reject the same set of unknown strategies.
# 策略白名單對齊 strategist_history_routes，避免兩端不一致。
_ALLOWED_STRATEGIES: frozenset[str] = frozenset(
    {
        "ma_crossover",
        "bb_reversion",
        "bb_breakout",
        "grid_trading",
        "funding_arb",
    }
)

# Symbol regex / format guard — Bybit perp symbols are upper-case alnum,
# usually ≤16 chars (BTCUSDT / 1000PEPEUSDT). We bound length + charset to
# stop log/audit injection via this field.
# Symbol 上限 32 char / [A-Z0-9]，防 audit/log 注入。
_MAX_SYMBOL_LEN = 32


# ═══════════════════════════════════════════════════════════════════════════════
# Request / response models / 請求 / 回應 模型
# ═══════════════════════════════════════════════════════════════════════════════


class PromoteRequest(BaseModel):
    """POST /api/v1/strategist/promote body.

    Two-step confirm:
      - confirm=false → preview JSON (no side effects).
      - confirm=true  → dispatch IPC + audit log + (optional) lineage row.

    兩步 confirm：preview 純讀無副作用；apply 才送 IPC / 寫 audit。
    """

    strategy: str = Field(..., description="Strategy name (whitelisted)")
    symbol: str = Field(
        ...,
        min_length=1,
        max_length=_MAX_SYMBOL_LEN,
        description=(
            "Symbol scope hint (audit/log only — strategy params apply across "
            "all symbols the strategy trades). 用於 audit scope；不影響 SQL 過濾。"
        ),
    )
    source_engine: str = Field(
        ..., description="Engine to read params from: demo | paper"
    )
    target_engine: str = Field(
        ..., description="Engine to apply params on: live | paper"
    )
    source: str = Field(
        default="operator",
        min_length=1,
        max_length=64,
        description="Audit provenance tag (default 'operator')",
    )
    confirm: bool = Field(
        default=False,
        description=(
            "False → return preview JSON only (no IPC / no audit / no mutation). "
            "True  → dispatch IPC `update_strategy_params` + write audit row."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════


def _validate_engine_pair(source_engine: str, target_engine: str) -> None:
    """Reject silly / unsafe engine pairs early.

    - source ∈ {demo, paper}  / target ∈ {live, paper}
    - source == target          → 400 (no-op promotion)
    - Anything outside whitelist → 400 with explicit allowed list

    早期拒絕無意義/不安全 engine 對。
    """
    if source_engine not in _ALLOWED_SOURCE_ENGINES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"source_engine must be one of {sorted(_ALLOWED_SOURCE_ENGINES)}, "
                f"got {source_engine!r}. Live is target-only."
            ),
        )
    if target_engine not in _ALLOWED_TARGET_ENGINES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"target_engine must be one of {sorted(_ALLOWED_TARGET_ENGINES)}, "
                f"got {target_engine!r}."
            ),
        )
    if source_engine == target_engine:
        raise HTTPException(
            status_code=400,
            detail=(
                f"source_engine == target_engine == {source_engine!r}; "
                f"promote is a no-op. 來源 == 目標，無意義。"
            ),
        )


def _fetch_latest_applied_row(
    engine_mode: str,
    strategy_name: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Read the latest `strategist_applied_params` row for (engine, strategy).

    Returns ``(row_dict | None, err_reason | None)``. err_reason is set on
    DB unavailability / SQL error so the caller can surface degraded=True
    instead of a generic 500.

    讀最新一行 strategist_applied_params；DB 不可用回 (None, reason)。
    """
    sql = """
        SELECT id,
               engine_mode,
               strategy_name,
               applied_at,
               applied_at_ms,
               source,
               reason,
               prev_params_json,
               params_json
          FROM learning.strategist_applied_params
         WHERE engine_mode = %s
           AND strategy_name = %s
         ORDER BY applied_at_ms DESC, id DESC
         LIMIT 1
    """
    with get_pg_conn() as conn:
        if conn is None:
            return None, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute(sql, (engine_mode, strategy_name))
            tup = cur.fetchone()
            if tup is None:
                return None, None
            cols = [d.name for d in cur.description] if cur.description else []
            row = dict(zip(cols, tup))
            applied_at = row.get("applied_at")
            if applied_at is not None:
                row["applied_at"] = applied_at.isoformat()
            return row, None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "strategist_promote latest_row query failed strategy=%s engine=%s err=%s",
                strategy_name,
                engine_mode,
                exc,
            )
            return None, f"pg_error:{type(exc).__name__}"


def _diff_params(
    target_current: dict[str, Any] | None,
    source_proposed: dict[str, Any],
) -> dict[str, Any]:
    """Build a key-by-key diff dict for the preview payload.

    Each key in either side becomes ``{old, new, changed: bool}``. New keys
    on the source are flagged ``old=None``; keys present only on the target
    are kept with ``new=None`` so the operator can see what would be
    *removed* (typically nothing, since IPC partial-merges don't delete).

    產生欄位級 diff；preview 回傳給 operator 比對。
    """
    target_current = target_current or {}
    diff: dict[str, Any] = {}
    keys = set(target_current.keys()) | set(source_proposed.keys())
    for k in sorted(keys):
        old = target_current.get(k)
        new = source_proposed.get(k)
        diff[k] = {
            "old": old,
            "new": new,
            "changed": old != new,
        }
    return diff


async def _fetch_target_current_params(
    target_engine: str,
    strategy_name: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Best-effort fetch of the *current* strategy params on target engine via
    Rust IPC (`get_strategy_params`). On IPC failure / parse error, return
    ``(None, reason)`` — preview falls back to "current=unknown" rather than
    failing the request.

    透過 Rust IPC 抓 target engine 上策略當前參數；失敗時 preview 顯示 unknown。
    """
    try:
        ipc_response = await one_shot_ipc_call(
            "get_strategy_params",
            params={
                "engine": target_engine,
                "strategy_name": strategy_name,
            },
            timeout=5.0,
            wrap_errors_as_http=False,
            error_context="strategist_promote_preview",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "strategist_promote get_strategy_params IPC failed strategy=%s engine=%s err=%s",
            strategy_name,
            target_engine,
            exc,
        )
        return None, f"ipc_unavailable:{type(exc).__name__}"

    # Rust returns a JSON-RPC envelope; the params live under "result" or
    # directly in the response dict depending on the dispatch path. We
    # accept either shape and parse the inner string-or-dict payload.
    # Rust 端可能直接回 dict 或 {"result": "<json string>"}；雙形容忍。
    payload: Any
    if isinstance(ipc_response, dict) and "result" in ipc_response:
        payload = ipc_response["result"]
    else:
        payload = ipc_response

    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return parsed, None
        except json.JSONDecodeError as exc:
            logger.warning(
                "strategist_promote get_strategy_params parse failed strategy=%s err=%s",
                strategy_name,
                exc,
            )
            return None, f"ipc_parse_error:{type(exc).__name__}"
    elif isinstance(payload, dict):
        return payload, None

    return None, "ipc_unexpected_shape"


def _record_promote_audit(
    *,
    actor_id: str,
    request_body: PromoteRequest,
    source_row_id: int | None,
    success: bool,
    gate_failed: str | None,
    confirm_phase: str,  # "preview" | "apply"
    ipc_response: dict[str, Any] | None,
    reason: str | None,
) -> None:
    """Write a STATE_CHANGE audit row (best effort; never blocks the request).

    Mirrors executor_routes._record_shadow_toggle_audit. Both denial + apply
    are logged so post-mortem can see who tried + why it was rejected.

    沿用 executor_routes 模式；成功 / 失敗都寫，post-mortem 可見「誰嘗試 + 為何被拒」。
    """
    try:
        from .governance_routes import _get_governance_hub  # lazy import
        hub = _get_governance_hub()
    except Exception as exc:  # noqa: BLE001
        logger.warning("strategist_promote audit: hub lazy import failed: %s", exc)
        return

    if hub is None or getattr(hub, "_change_audit_log", None) is None:
        # Fail-soft: log a warning so the gap is visible. Mirrors
        # executor_routes / risk_routes behavior.
        # Fail-soft：警告記下缺口（與 executor_routes / risk_routes 一致）。
        logger.warning(
            "strategist_promote audit: change_audit_log unavailable — "
            "actor=%s strategy=%s symbol=%s phase=%s success=%s gate=%s "
            "(Root Principle #8 trace gap)",
            actor_id,
            request_body.strategy,
            request_body.symbol,
            confirm_phase,
            success,
            gate_failed,
        )
        return

    try:
        from .change_audit_log import ChangeType
        verdict = "applied" if success else ("previewed" if confirm_phase == "preview" else "denied")
        what = (
            f"Strategist promote {request_body.source_engine}→{request_body.target_engine} "
            f"strategy={request_body.strategy} symbol={request_body.symbol} ({verdict})"
        )
        hub._change_audit_log.record_change(
            change_type=ChangeType.STATE_CHANGE,
            who=actor_id,
            what=what,
            reason=(
                f"source={request_body.source}; phase={confirm_phase}; "
                f"row_id={source_row_id}; reason={reason or 'none'}; "
                f"gate_failed={gate_failed or 'none'}"
            ),
            old_value={
                "engine": request_body.target_engine,
                "verdict": "request",
                "phase": confirm_phase,
            },
            new_value={
                "strategy": request_body.strategy,
                "symbol": request_body.symbol,
                "source_engine": request_body.source_engine,
                "target_engine": request_body.target_engine,
                "source_row_id": source_row_id,
                "verdict": verdict,
                "gate_failed": gate_failed,
                "ipc_result": ipc_response,
            },
            affected_components=[
                f"strategist:{request_body.target_engine}:{request_body.strategy}",
                "rust:StrategyParams",
                "learning.strategist_applied_params",
            ],
            auto_approve=True,  # actor already passed Operator-role gate
        )
    except Exception as exc:  # noqa: BLE001 — audit must never break the request
        logger.warning("strategist_promote audit write failed: %s", exc)


def _apply_target_gate(actor: Any, target_engine: str) -> None:
    """Run the auth gate for the target engine + confirmed apply path.

    Mirrors executor_routes' `_verify_*_gate` matrix:
      - target=live  → full 5-gate live chain
      - target=paper → Operator role only

    沿用 executor_routes 5-gate 鏈；live=full 5-gate / paper=Operator 角色。
    """
    if target_engine == "live":
        # Reuse the canonical 5-gate verifier from executor_routes — DO NOT
        # reimplement. If it ever evolves (gate added / refactored), this
        # endpoint inherits the change automatically.
        # 重用 executor_routes 的 5-gate 驗證；後續演進自動繼承。
        from .executor_routes import _verify_live_gate
        _verify_live_gate(actor)
    elif target_engine == "paper":
        from .governance_routes import _require_operator_role
        _require_operator_role(actor)
    else:  # pragma: no cover — _validate_engine_pair already rejected
        raise HTTPException(status_code=400, detail=f"unreachable target_engine {target_engine!r}")


# ═══════════════════════════════════════════════════════════════════════════════
# Routes / 路由
# ═══════════════════════════════════════════════════════════════════════════════


@strategist_promote_router.post("/promote")
async def post_strategist_promote(
    body: PromoteRequest,
    actor: Any = Depends(base.current_actor),
) -> dict[str, Any]:
    """POST /api/v1/strategist/promote — Operator manual params promotion.

    Two-step flow:
      1. ``confirm=false`` (default) → preview JSON: source row + current
         target params + key-by-key diff. NO side effects.
      2. ``confirm=true`` → dispatch IPC `update_strategy_params` against
         target engine, write change_audit_log entry. Rust persist path
         writes a `strategist_applied_params` row with `source='manual_promote'`.

    Auth (mirrors executor_routes shadow-toggle matrix):
      - All requests: Operator role required (always).
      - target=live + confirm=true → full 5-gate live chain (Operator +
        live_reserved + OPENCLAW_ALLOW_MAINNET + secret slot +
        authorization.json HMAC/expiry/env_allowed).
      - target=paper → Operator role only.
      - Preview (confirm=false) → Operator role only on any target.
      - source==target → 400 (silly).

    Returns:
      200 + envelope (preview or applied) on success
      400 invalid engine pair / unknown strategy
      403 + {gate_failed, hint} on gate denial
      404 no source row found
      500 IPC failure on apply path

    Operator 兩步 confirm 晉升 strategist 參數；preview 無副作用，apply 觸發 IPC + audit。
    """
    actor_id = str(getattr(actor, "actor_id", "?"))

    # ── Step 1: validate inputs ──
    # Whitelist strategy first so we can keep audit log honest.
    # 先驗策略白名單，audit 才不會亂寫。
    if body.strategy not in _ALLOWED_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"strategy must be one of {sorted(_ALLOWED_STRATEGIES)}, "
                f"got {body.strategy!r}"
            ),
        )
    # Symbol charset/length already bounded by Pydantic; cheap final guard.
    # symbol 字元集 — 防 log/audit 注入。
    if not body.symbol.replace("_", "").isalnum() or not body.symbol.isupper():
        raise HTTPException(
            status_code=400,
            detail=(
                f"symbol must be uppercase alphanumeric (e.g. 'BTCUSDT'); got {body.symbol!r}"
            ),
        )

    _validate_engine_pair(body.source_engine, body.target_engine)

    # ── Step 2: Operator role gate (always required) ──
    # Operator 角色（無論 preview / apply）。
    try:
        from .governance_routes import _require_operator_role
        _require_operator_role(actor)
    except HTTPException as exc:
        # Audit denial of the role gate.
        # 審計角色拒絕。
        gate = "operator_role" if exc.status_code == 403 else "unauthenticated"
        _record_promote_audit(
            actor_id=actor_id,
            request_body=body,
            source_row_id=None,
            success=False,
            gate_failed=gate,
            confirm_phase="preview" if not body.confirm else "apply",
            ipc_response=None,
            reason=str(exc.detail) if isinstance(exc.detail, str) else None,
        )
        raise

    # ── Step 3: look up source row ──
    # 找來源 row（latest applied on source_engine for strategy）。
    source_row, fetch_reason = _fetch_latest_applied_row(
        body.source_engine, body.strategy
    )
    if fetch_reason == "pg_unavailable" or fetch_reason and fetch_reason.startswith("pg_error"):
        # PG down → cannot establish source params → cannot proceed.
        # PG 不可用 → 沒參數可晉升。
        raise HTTPException(
            status_code=503,
            detail=f"PG unavailable / query failed: {fetch_reason}",
        )
    if source_row is None:
        _record_promote_audit(
            actor_id=actor_id,
            request_body=body,
            source_row_id=None,
            success=False,
            gate_failed="source_row_not_found",
            confirm_phase="preview" if not body.confirm else "apply",
            ipc_response=None,
            reason="no row matching (source_engine, strategy)",
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"No strategist_applied_params row found for "
                f"engine={body.source_engine!r} strategy={body.strategy!r}. "
                f"Strategist scheduler may not have applied this strategy yet."
            ),
        )

    # ── Step 4: Preview path (confirm=false) ──
    # confirm=false → 只回 preview，不發 IPC，不寫 audit（節省風暴 audit row）。
    source_params = source_row.get("params_json") or {}
    if not isinstance(source_params, dict):
        # params_json column is JSONB; sqlx returns parsed dict. Defensive
        # check in case driver returns a JSON-string fallback.
        # 防禦：若 driver 回 str fallback 嘗試解析。
        try:
            source_params = json.loads(source_params) if isinstance(source_params, str) else {}
        except (json.JSONDecodeError, TypeError):
            source_params = {}

    if not body.confirm:
        target_current, current_reason = await _fetch_target_current_params(
            body.target_engine, body.strategy
        )
        diff = _diff_params(target_current, source_params)
        preview = {
            "ok": True,
            "phase": "preview",
            "confirm_required": True,
            "source_engine": body.source_engine,
            "target_engine": body.target_engine,
            "strategy": body.strategy,
            "symbol": body.symbol,
            "source_row": {
                "id": source_row.get("id"),
                "applied_at": source_row.get("applied_at"),
                "applied_at_ms": source_row.get("applied_at_ms"),
                "source": source_row.get("source"),
                "reason": source_row.get("reason"),
            },
            "source_params": source_params,
            "target_current_params": target_current,
            "target_current_degraded": current_reason is not None,
            "target_current_reason": current_reason,
            "diff": diff,
            "next_step": (
                "Re-call POST /api/v1/strategist/promote with confirm=true "
                "(and the same body) to dispatch IPC + write audit row. "
                "重新呼叫 confirm=true 以套用。"
            ),
            "ts_ms": int(time.time() * 1000),
            "actor": actor_id,
        }
        # Preview is intentionally NOT audited — operators routinely call it
        # to inspect; storming change_audit_log adds noise without forensic
        # value. The apply path covers all real mutations.
        # preview 刻意不寫 audit；只記真正會改 state 的 apply。
        logger.info(
            "strategist_promote PREVIEW actor=%s strategy=%s symbol=%s %s→%s row_id=%s diff_keys=%d",
            actor_id,
            body.strategy,
            body.symbol,
            body.source_engine,
            body.target_engine,
            source_row.get("id"),
            sum(1 for d in diff.values() if d["changed"]),
        )
        return preview

    # ── Step 5: Apply path (confirm=true) ──
    # confirm=true：先過 target gate（live=5-gate / paper=Operator role），再 IPC。
    try:
        _apply_target_gate(actor, body.target_engine)
    except HTTPException as exc:
        gate_failed: str | None = None
        if exc.status_code == 403 and isinstance(exc.detail, dict):
            gate_failed = exc.detail.get("gate_failed")
        elif exc.status_code == 403:
            gate_failed = "operator_role"
        elif exc.status_code == 401:
            gate_failed = "unauthenticated"
        _record_promote_audit(
            actor_id=actor_id,
            request_body=body,
            source_row_id=source_row.get("id"),
            success=False,
            gate_failed=gate_failed,
            confirm_phase="apply",
            ipc_response=None,
            reason=None,
        )
        raise

    # ── Step 6: dispatch IPC update_strategy_params ──
    # IPC method `update_strategy_params` is the same path the Strategist
    # scheduler uses for auto-tune cycles; Rust validates with the typed
    # `update_params_json` (CONF-D conf_scale strip-and-apply) before
    # ConfigStore swap + persist row with source='manual_promote'.
    # IPC 沿用 Strategist scheduler 的 update_strategy_params 路徑；Rust 驗證
    # 後 ConfigStore 交換並寫入 source='manual_promote' row。
    ipc_params = {
        "engine": body.target_engine,
        "strategy_name": body.strategy,
        "params_json": json.dumps(source_params),
        "source": body.source,
        "reason": (
            f"manual_promote:{body.source_engine}->{body.target_engine}:"
            f"row_id={source_row.get('id')}:symbol={body.symbol}"
        ),
    }
    try:
        ipc_response = await one_shot_ipc_call(
            "update_strategy_params",
            params=ipc_params,
            timeout=5.0,
            wrap_errors_as_http=False,
            error_context="strategist_promote_apply",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "strategist_promote IPC failed strategy=%s symbol=%s %s→%s err=%s",
            body.strategy,
            body.symbol,
            body.source_engine,
            body.target_engine,
            exc,
        )
        _record_promote_audit(
            actor_id=actor_id,
            request_body=body,
            source_row_id=source_row.get("id"),
            success=False,
            gate_failed="ipc_unavailable",
            confirm_phase="apply",
            ipc_response=None,
            reason=f"{type(exc).__name__}:{exc}",
        )
        raise HTTPException(
            status_code=500,
            detail=f"rust_engine_unavailable: update_strategy_params: {exc}",
        ) from exc

    # ── Step 7: success — record audit + return envelope ──
    response_data = {
        "ok": True,
        "phase": "apply",
        "strategy": body.strategy,
        "symbol": body.symbol,
        "source_engine": body.source_engine,
        "target_engine": body.target_engine,
        "applied_params": source_params,
        "source_row_id": source_row.get("id"),
        "ipc_response": ipc_response,
        "ts_ms": int(time.time() * 1000),
        "source": body.source,
        "actor": actor_id,
    }
    logger.warning(
        "strategist_promote SUCCESS actor=%s strategy=%s symbol=%s %s→%s row_id=%s source=%s",
        actor_id,
        body.strategy,
        body.symbol,
        body.source_engine,
        body.target_engine,
        source_row.get("id"),
        body.source,
    )
    _record_promote_audit(
        actor_id=actor_id,
        request_body=body,
        source_row_id=source_row.get("id"),
        success=True,
        gate_failed=None,
        confirm_phase="apply",
        ipc_response=ipc_response if isinstance(ipc_response, dict) else None,
        reason=None,
    )
    return response_data


__all__ = [
    "strategist_promote_router",
    "PromoteRequest",
]
