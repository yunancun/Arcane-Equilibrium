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

  PHASE 2 ENHANCEMENT (2026-06-17 — demo→live human-gated promotion):
    This existing route is ENHANCED (not replaced) per execution_plan
    2026-06-17 §2.0-§2.12. Three structural gates are layered on the
    `confirm=true` + `target_engine=="live"` branch, plus a net-new demote:
      (A) flag gate OPENCLAW_STRATEGIST_PROMOTION_ENABLED (§2.1) — default-OFF
          → 409 promotion_disabled (fail-loud, never silent demo downgrade).
      (B) EDGE-ANCHORED criteria gate (§2.4) — read-only IPC
          `evaluate_promotion_criteria` (token-EXEMPT, NOT in
          LIVE_WRITE_METHODS); engine self-queries live edge_estimates +
          live cost wall + LIVE drawdown envelope; Reject/Pending → 409
          criteria_not_met. NOT demo-PnL (down-beta false-positive removed).
      (C) fail-closed audit (§2.6) — AFTER live IPC OK, a BLOCKING INSERT
          into `learning.strategist_promotions`; INSERT failure → 500
          audit_write_failed (loud, never swallowed). change_audit_log kept
          as supplement (fire-and-forget). demo/paper path unchanged.
      (D) POST /demote (§2.5) — EXACT reverse-promote on the same router:
          same flag + 5-gate + token; criteria-EXEMPT (rollback always
          allowed); precondition guard (canonical compare current-live vs
          stored promoted_params_json → 409 live_changed_since_promotion);
          restores the COMPLETE pre_promotion_params_json.
    The `promote_params_to_live()` Rust stub is intentionally NOT wired
    (it bypasses the dispatch chokepoint + Phase-0 token). live promote
    still flows through `update_strategy_params{engine:live}` IPC.

MODULE_NOTE (中):
  G3-10 STRATEGIST-PROMOTE-TRIGGER-1 — Operator 手動把 demo 上穩定的策略參數
  晉升至 live (或 paper)；繞過 AUTO-PROMOTE counter 但不繞過 5-gate live 鏈。
  兩步 confirm（confirm=false 預覽 / confirm=true 套用）；身分驗證沿用
  executor_routes 的 5-gate。Schema 僅有 (engine_mode, strategy_name) 欄位，
  symbol 只用於 audit scope hint 不參與 SQL 過濾。

  PHASE 2 ENHANCEMENT（2026-06-17 demo→live 人工促升閘）：在既有 live 分支疊
  (A) flag gate OPENCLAW_STRATEGIST_PROMOTION_ENABLED（default-OFF→409
  promotion_disabled）+ (B) EDGE-ANCHORED criteria gate（唯讀 IPC
  evaluate_promotion_criteria，token 豁免，不靠 demo PnL）+ (C) fail-closed
  同步審計 learning.strategist_promotions（INSERT 失敗→500 audit_write_failed）
  + (D) net-new POST /demote（EXACT 回滾，criteria 豁免，precondition guard）。
  **不**接 promote_params_to_live stub（繞 chokepoint+token）；live 促升仍走
  update_strategy_params{engine:live} IPC chokepoint。
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import main_legacy as base
from .db_pool import get_pg_conn
from .ipc_dispatch import one_shot_ipc_call
from .live_patch_token import canonical_json
from .strategist_promote_contract import (
    CRITERIA_IPC_METHOD,
    CRITERIA_RESPONSE_ACTIVE_COUNT_KEY,
    CRITERIA_RESPONSE_FRESH_KEY,
    CRITERIA_RESPONSE_PER_CELL_KEY,
    is_eligible,
)

logger = logging.getLogger(__name__)


# ── 配置檔路徑（SSOT；鏡像 paper_trading_routes._PAPER_CONFIG_PATH 解析範式）──
# 為何用 OPENCLAW_BASE_DIR + parents[5]：跨平台不硬編 user path（CLAUDE §六）。
# parents[5] = srv（control_api_v1/app/<file> 上溯 5 層；實測見報告）。
_SETTINGS_DIR = Path(
    os.environ.get("OPENCLAW_BASE_DIR", str(Path(__file__).resolve().parents[5]))
) / "settings"
_RISK_CONFIG_LIVE_PATH = _SETTINGS_DIR / "risk_control_rules" / "risk_config_live.toml"
_SCANNER_CONFIG_PATH = _SETTINGS_DIR / "risk_control_rules" / "scanner_config.toml"
_STRATEGY_PARAMS_LIVE_PATH = _SETTINGS_DIR / "strategy_params_live.toml"


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — promotion flag + criteria + audit table constants / 促升旗標與常數
# ═══════════════════════════════════════════════════════════════════════════════
#
# PHASE 2 把既有 promote route（已 5-gate + Phase-0 token）疊三個結構性閘：
#   (A) flag gate（§2.1）       — default-OFF → live 促升 409 promotion_disabled
#   (B) EDGE-ANCHORED criteria  — 唯讀 IPC evaluate_promotion_criteria（§2.4）
#   (C) fail-closed audit       — 同步寫 learning.strategist_promotions（§2.6）
# 加 (D) EXACT demote（§2.5）。**不**新增平行 route、**不**接 promote_params_to_live stub。
#
# 旗標讀法鏡像 strategy_write_routes._live_strategy_toggle_enabled（只接字面 "1"）。
# 為何 default-OFF（fail-closed）：今天 live edge_estimates 0 validated cell，criteria
# gate 本就會 Pending/Reject 所有促升；flag 是「機器是否上線」的總開關，OFF 時 live 促升
# 不可達（bit-identical，除新增 409 拒絕碼），永不靜默降級成 demo（鏡像 POLICY-2 fail-loud）。
_PROMOTION_FLAG_ENV = "OPENCLAW_STRATEGIST_PROMOTION_ENABLED"

# §2.4.C/D soak metric：21d soak / 72h since-change 的「判定」由 Rust criteria gate
# （promotion_criteria.rs）做，route 只 query raw metric 餵 IPC（async/sync 邊界 §2.4.G）。
# demo fills 聚合窗 = 21d（鏡像 canary Stage3 wall-clock），直接寫進 SQL INTERVAL。

# learning.strategist_promotions 審計表（E1-B migration 建；SHARED CONTRACT 表名）。
_PROMOTIONS_TABLE = "learning.strategist_promotions"


def _promotion_enabled() -> bool:
    """讀 OPENCLAW_STRATEGIST_PROMOTION_ENABLED（default-OFF，只接字面 "1"）。

    為何 fail-closed default-OFF：促升直接改 LIVE 策略行為（25-sym blast radius），
    旗標是「促升機器是否上線」總開關。OFF → live 促升分支 409 promotion_disabled
    （fail-loud），preview / paper / demote-preview 不受此旗標影響（§2.1）。
    """
    return (os.environ.get(_PROMOTION_FLAG_ENV) or "").strip() == "1"


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
# PHASE 2 — IPC-CONTRACT Option A：active-symbol 解析 + live cost 參數 + boundary
# （route 算齊所有 metric 傳入 engine；engine 只自查 edge cell — §2.4.G / Fix 1）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 為何 route 算這些（非 engine 自查）：active_symbols 需讀兩份 TOML
# （strategy_params_live + scanner_config）、boundary 需查 demo realized drawdown
# （DB query）、cost 參數讀 risk_config_live.toml [slippage] SSOT——三者在 sync IPC
# handler 內不可達（無 DB pool、無 tomllib reader）。route（async + DB + tomllib）是唯一
# 能算齊的層。此即 E1 釘死的 Option A（§2.4.G「route 算齊 metric」分支）。

# DEFAULT_TAKER_FEE_RATE 鏡像 intent_processor/mod.rs:489（live cost gate fee_rate）。
# fee_bps_round_trip = 2×(fee_rate + slippage)×10000，與 cost_gate_live_with_slippage:299 同式。
# slippage 取 [slippage].default_rate（volume≤0 fallback = 最保守 tier），fail-closed：
# 用最保守滑點作 cost wall，不挑樂觀的高流動性 tier（promote 是 25-sym blast radius）。
_DEFAULT_TAKER_FEE_RATE = 0.00055


def _load_toml(path: Path) -> dict[str, Any] | None:
    """讀一份 TOML 配置；缺檔 / parse 失敗 → None（caller fail-closed）。"""
    try:
        if not path.exists():
            logger.warning("strategist_promote: config TOML missing path=%s", path.name)
            return None
        import tomllib  # noqa: PLC0415 — py3.11+ stdlib
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — config 讀失敗 = 無證據 = fail-closed
        logger.warning("strategist_promote: config TOML read failed path=%s err=%s", path.name, exc)
        return None


def _resolve_active_symbols(strategy_name: str) -> list[str]:
    """§2.4.B active-symbol 集合 = `strategy_params_live.allowed_symbols` ∩ pinned universe。

    為何 ∩ pinned：promote 的 live blast radius = 該策略在 live 真會開倉的 symbol 集
    （`is_pinned` 是硬交易 gate，only pinned tier 真開新倉）。allowed_symbols 為空/未設
    → 該策略 live 不交易任何 symbol → 回 []（criteria gate 接著 Reject("no_active_symbols")，
    無 blast radius 即無促升意義，fail-closed）。

    讀檔失敗（任一 TOML 缺）→ 回 []（fail-closed：無法解析 active set 即視同無 active）。
    """
    sp = _load_toml(_STRATEGY_PARAMS_LIVE_PATH)
    sc = _load_toml(_SCANNER_CONFIG_PATH)
    if sp is None or sc is None:
        return []
    strat_section = sp.get(strategy_name)
    allowed: list[str] = []
    if isinstance(strat_section, dict):
        raw_allowed = strat_section.get("allowed_symbols")
        if isinstance(raw_allowed, list):
            allowed = [str(s) for s in raw_allowed]
    # pinned_symbols 在 scanner_config 的 [universe] 段（非 top-level，親查實況）；
    # 留 top-level fallback 防 schema 演進。讀錯位置會令所有策略誤回 [] → 誤
    # Reject("no_active_symbols")（safe 但理由錯，masking-bug 類）。
    universe = sc.get("universe") if isinstance(sc.get("universe"), dict) else {}
    pinned_raw = universe.get("pinned_symbols")
    if not isinstance(pinned_raw, list):
        pinned_raw = sc.get("pinned_symbols")
    pinned: set[str] = set()
    if isinstance(pinned_raw, list):
        pinned = {str(s) for s in pinned_raw}
    # ∩ + 穩定排序（audit / 判定 determinism）。
    return sorted(s for s in allowed if s in pinned)


def _load_live_cost_model() -> dict[str, Any] | None:
    """讀 risk_config_live.toml [slippage] SSOT → criteria cost-model 參數（Fix 1 Option A）。

    回 {fee_bps_round_trip, cost_gate_safety_multiplier, cost_gate_win_rate_floor, edge_ttl_secs}。
    讀檔失敗 → None（caller fail-closed：無 cost model 不放行）。

    為何不硬編 1.3/0.3/ttl：SSOT 在 TOML，硬編會與 live cost_gate drift（承 QC MEDIUM）。
    fee_bps 用 default_rate（最保守 tier）+ 固定 taker fee_rate，鏡像 cost_gate_live 算式。
    """
    rc = _load_toml(_RISK_CONFIG_LIVE_PATH)
    if rc is None:
        return None
    slip = rc.get("slippage")
    if not isinstance(slip, dict):
        logger.warning("strategist_promote: risk_config_live.toml missing [slippage]")
        return None
    default_rate = float(slip.get("default_rate", 0.0005))
    safety_multiplier = float(slip.get("cost_gate_safety_multiplier", 1.3))
    win_rate_floor = float(slip.get("cost_gate_win_rate_floor", 0.3))
    edge_ttl_secs = int(slip.get("edge_estimate_ttl_secs", 172_800))
    # fee_bps_round_trip = 2×(taker_fee + slippage)×10000（cost_gate_live_with_slippage:299）。
    fee_bps_round_trip = 2.0 * (_DEFAULT_TAKER_FEE_RATE + default_rate) * 10_000.0
    return {
        "fee_bps_round_trip": fee_bps_round_trip,
        "cost_gate_safety_multiplier": safety_multiplier,
        "cost_gate_win_rate_floor": win_rate_floor,
        "edge_ttl_secs": edge_ttl_secs,
    }


def _compute_demo_boundary_violation_count(strategy_name: str) -> int:
    """§2.4.D：demo soak 窗內 realized drawdown 是否曾突破 LIVE 12%/7% envelope。

    為何用 LIVE envelope（非 demo 寬鬆 25%/15%）：促升的是 live 行為；demo 在寬鬆
    envelope 下「沒爆」不代表 live 緊 envelope 下安全。SSOT 讀 risk_config_live.toml
    （session_drawdown_max_pct / daily_loss_max_pct），不硬編 12/7。

    drawdown 量測鏡像 trading_true_metrics._fetch_db_risk_metrics：以 baseline 10000 USDT
    累計 demo realized close PnL（realized_pnl - fee），peak-to-trough max drawdown %
    與單日 max loss %。任一突破 LIVE envelope → 回 1（criteria Reject）。

    fail-closed：config 讀失敗 / DB 不可用 → 回 1（保守：視為曾越界 → Reject），與 Rust
    handler 缺 boundary 欄時 unwrap_or(1) 同向。
    """
    rc = _load_toml(_RISK_CONFIG_LIVE_PATH)
    if rc is None:
        return 1  # fail-closed
    limits = rc.get("limits") if isinstance(rc.get("limits"), dict) else rc
    session_dd_max_pct = float(limits.get("session_drawdown_max_pct", 12.0))
    daily_loss_max_pct = float(limits.get("daily_loss_max_pct", 7.0))

    sql = """
        SELECT ts,
               (COALESCE(realized_pnl, 0) - COALESCE(fee, 0))::float8 AS pnl
          FROM trading.fills
         WHERE engine_mode = 'demo'
           AND strategy_name = %s
           AND ts >= now() - INTERVAL '21 days'
           AND (
                COALESCE(realized_pnl, 0) <> 0
             OR COALESCE(exit_reason, '') <> ''
           )
         ORDER BY ts ASC
    """
    with get_pg_conn() as conn:
        if conn is None:
            return 1  # fail-closed
        try:
            cur = conn.cursor()
            cur.execute(sql, (strategy_name,))
            rows = cur.fetchall() or []
        except Exception as exc:  # noqa: BLE001 — DB 失敗 = 無證據 = fail-closed
            logger.warning(
                "strategist_promote boundary query failed strategy=%s err=%s",
                strategy_name,
                exc,
            )
            return 1

    if not rows:
        # 無 demo realized close → 無越界可量（也無 soak 證據，但 boundary 此處不擋；
        # soak/fills 閘另在 criteria 內擋）。回 0（無越界），由 coverage/soak 閘決定。
        return 0

    baseline = 10_000.0
    cumulative = 0.0
    peak = 0.0
    max_drawdown_abs = 0.0
    # daily loss 聚合（按 UTC date bucket 累計當日 PnL，取最負者）。
    daily_pnl: dict[Any, float] = {}
    for ts, pnl in rows:
        cumulative += float(pnl)
        if cumulative > peak:
            peak = cumulative
        max_drawdown_abs = max(max_drawdown_abs, peak - cumulative)
        day_key = ts.date() if hasattr(ts, "date") else ts
        daily_pnl[day_key] = daily_pnl.get(day_key, 0.0) + float(pnl)

    max_drawdown_pct = (max_drawdown_abs / baseline) * 100.0
    worst_daily_loss_pct = 0.0
    if daily_pnl:
        worst_daily = min(daily_pnl.values())  # 最負（虧最多）
        if worst_daily < 0:
            worst_daily_loss_pct = (abs(worst_daily) / baseline) * 100.0

    breached = (
        max_drawdown_pct > session_dd_max_pct or worst_daily_loss_pct > daily_loss_max_pct
    )
    if breached:
        logger.info(
            "strategist_promote boundary BREACH strategy=%s max_dd=%.2f%%(>%.1f) "
            "worst_daily=%.2f%%(>%.1f)",
            strategy_name,
            max_drawdown_pct,
            session_dd_max_pct,
            worst_daily_loss_pct,
            daily_loss_max_pct,
        )
    return 1 if breached else 0


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — criteria metric query / tuned-param diff / snapshot / fail-closed audit
# 促升 criteria 度量查詢 / 改動 param diff / 完整 snapshot / fail-closed 審計
# ═══════════════════════════════════════════════════════════════════════════════


def _diff_tuned_param_names(
    pre_promotion_params: dict[str, Any] | None,
    promoted_params: dict[str, Any],
) -> list[str]:
    """算「本次促升相對 pre-promotion live set 真正改動的 param key」（§2.4.F）。

    為何要 diff 而非送全 key：direction bound（promotion_criteria.rs step 1）對
    「本次實際改的 param」逐個查 v1 allowlist；若把未改動的 key 也算進去，會誤把
    denylist 但本次沒動的 param 當成「被促升」→ 誤 Reject。改動定義 = key 新增
    或值不同（鏡像 _diff_params 的 changed 語意）。pre 為 None（live 無此策略）時
    promoted 的全 key 都算新增改動。
    """
    pre = pre_promotion_params or {}
    changed: list[str] = []
    for k in sorted(promoted_params.keys()):
        if k not in pre or pre.get(k) != promoted_params.get(k):
            changed.append(k)
    return changed


def _fetch_demo_soak_metrics(strategy_name: str) -> dict[str, Any]:
    """查 §2.4.C/D 的 demo soak 度量（與 _fetch_latest_applied_row 同 DB lane）。

    回傳供 evaluate_promotion_criteria IPC 餵入的 raw metric（純 query，判定在 Rust）：
      - demo_soak_wall_clock_ms：該策略「當前 param-version」自 applied 起的 wall-clock。
      - ms_since_last_param_change：自上次 params_json 變動以來 wall-clock（取最近兩筆
        applied row 的 applied_at_ms 差；只一筆則 = soak wall-clock）。
      - attributable_demo_fills：soak 窗內該策略 demo fills 計數（鏡像 evaluate.rs:417 同源）。

    boundary（demo 是否突破 LIVE 12/7 envelope，§2.4.D）由 Rust criteria gate 自查
    live risk_config + demo realized drawdown；route 不在此硬編 12/7（SSOT 在 Rust）。
    故本函數**不**回 demo_boundary_violation_count（交 engine 自查）。

    DB 不可用 / SQL 失敗 → 回 {"degraded": reason}，caller 據此 503（不可在缺度量
    下放行 — fail-closed，無證據不促升）。
    """
    now_ms = int(time.time() * 1000)
    sql_versions = """
        SELECT applied_at_ms
          FROM learning.strategist_applied_params
         WHERE engine_mode = 'demo'
           AND strategy_name = %s
         ORDER BY applied_at_ms DESC, id DESC
         LIMIT 2
    """
    # demo fills 計數：trading.fills engine_mode='demo'，soak 窗內該策略。
    # 欄名以 V021/V033 schema 為準：strategy_name（非 strategy）、ts（timestamptz，
    # 非 ts_ms）。soak 窗用 ts >= now() - INTERVAL（鏡像 sibling fills query 慣例）。
    sql_fills = """
        SELECT count(*)
          FROM trading.fills
         WHERE engine_mode = 'demo'
           AND strategy_name = %s
           AND ts >= now() - INTERVAL '21 days'
    """
    with get_pg_conn() as conn:
        if conn is None:
            return {"degraded": "pg_unavailable"}
        try:
            cur = conn.cursor()
            cur.execute(sql_versions, (strategy_name,))
            version_rows = cur.fetchall()
            if not version_rows:
                # 無 applied row（理論上 caller 已先 _fetch_latest_applied_row 過 404）；
                # 防禦：當作 soak=0 → criteria 必 Pending。
                return {
                    "demo_soak_wall_clock_ms": 0,
                    "ms_since_last_param_change": 0,
                    "attributable_demo_fills": 0,
                }
            latest_ms = int(version_rows[0][0])
            demo_soak_wall_clock_ms = max(0, now_ms - latest_ms)
            if len(version_rows) >= 2:
                prev_ms = int(version_rows[1][0])
                ms_since_last_param_change = max(0, latest_ms - prev_ms)
            else:
                # 只有一筆 applied → 該 param-version 從 applied 起就沒再變 → 用 soak 全長。
                ms_since_last_param_change = demo_soak_wall_clock_ms
            cur.execute(sql_fills, (strategy_name,))
            fills_tup = cur.fetchone()
            attributable_demo_fills = int(fills_tup[0]) if fills_tup else 0
            return {
                "demo_soak_wall_clock_ms": demo_soak_wall_clock_ms,
                "ms_since_last_param_change": ms_since_last_param_change,
                "attributable_demo_fills": attributable_demo_fills,
            }
        except Exception as exc:  # noqa: BLE001 — 度量查詢失敗 = 無證據 = fail-closed
            logger.warning(
                "strategist_promote soak metric query failed strategy=%s err=%s",
                strategy_name,
                exc,
            )
            return {"degraded": f"pg_error:{type(exc).__name__}"}


def _build_criteria_ipc_params(
    *,
    strategy_name: str,
    active_symbols: list[str],
    soak_metrics: dict[str, Any],
    demo_boundary_violation_count: int,
    cost_model: dict[str, Any],
    tuned_param_names: list[str],
) -> dict[str, Any]:
    """組 evaluate_promotion_criteria IPC 的 OUTGOING params（IPC-CONTRACT Option A）。

    SHARED CONTRACT：key 集合 == strategist_promote_contract.CRITERIA_OUTGOING_KEYS
    == Rust dispatch.rs::handle_evaluate_promotion_criteria 讀的 key（contract test 斷言）。
    抽成獨立 builder 是為了讓 contract test 能直接斷言 emit 的 key 集合，不必跑整條 route。

    - strategy（非 strategy_name！handler 讀 params.get("strategy")）。
    - active_symbols：route 解析 allowed∩pinned（空 → handler Reject no_active_symbols）。
    - cost 參數 / edge_ttl：route 讀 risk_config_live.toml [slippage] SSOT。
    - demo_boundary_violation_count：route 量測 demo drawdown vs LIVE envelope。
    """
    return {
        "strategy": strategy_name,
        "active_symbols": active_symbols,
        "demo_soak_wall_clock_ms": soak_metrics.get("demo_soak_wall_clock_ms", 0),
        "ms_since_last_param_change": soak_metrics.get("ms_since_last_param_change", 0),
        "attributable_demo_fills": soak_metrics.get("attributable_demo_fills", 0),
        "demo_boundary_violation_count": demo_boundary_violation_count,
        # attribution_chain_ok healthcheck v1 對 strategist-param 不可查 → None（handler
        # 視為 Pending("attribution_not_computed")，§2.4.C additional where-available）。
        "attribution_chain_ok_ratio": None,
        "fee_bps_round_trip": cost_model["fee_bps_round_trip"],
        "cost_gate_safety_multiplier": cost_model["cost_gate_safety_multiplier"],
        "cost_gate_win_rate_floor": cost_model["cost_gate_win_rate_floor"],
        "edge_ttl_secs": cost_model["edge_ttl_secs"],
        "tuned_param_names": tuned_param_names,
    }


def _criteria_input_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """從 handler 回應組裝 audit `criteria_input_json` 的 EDGE-ANCHORED 證據（Fix 2/P8）。

    handler **不**回 "criteria_input" 整包，而是分欄回 per_cell / active_count /
    edge_estimates_fresh（dispatch.rs response payload）。route 必須讀這些真鍵組裝快照，
    否則 criteria_input_json 永遠 null（承 QC/CC HIGH：route 讀不存在的 "criteria_input"）。
    """
    return {
        "per_cell": payload.get(CRITERIA_RESPONSE_PER_CELL_KEY, []),
        "active_count": payload.get(CRITERIA_RESPONSE_ACTIVE_COUNT_KEY),
        "edge_estimates_fresh": payload.get(CRITERIA_RESPONSE_FRESH_KEY),
        "verdict": payload.get("verdict"),
        "reason": payload.get("reason"),
    }


async def _evaluate_criteria(
    *,
    strategy_name: str,
    active_symbols: list[str],
    soak_metrics: dict[str, Any],
    demo_boundary_violation_count: int,
    cost_model: dict[str, Any],
    tuned_param_names: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """唯讀 IPC evaluate_promotion_criteria（§2.4.G / IPC-CONTRACT Option A）。

    SHARED CONTRACT：method=evaluate_promotion_criteria（**不在** LIVE_WRITE_METHODS，
    token 豁免）。route 算齊所有 metric（active_symbols + soak/fills + boundary + cost
    參數 + edge_ttl + tuned_param_names）傳入；engine 只自查 live-grade EdgeEstimates
    snapshot 的 per-cell edge（freshness/runtime_field 須與 live cost_gate 看同一記憶體
    snapshot）+ 跑 promotion_criteria.rs 判定，回 {verdict, reason, per_cell, active_count,
    edge_estimates_fresh}。

    回 (verdict_dict | None, err_reason | None)。IPC 失敗 → (None, reason)，caller fail-closed
    （無 verdict 不可放行）。
    """
    ipc_params = _build_criteria_ipc_params(
        strategy_name=strategy_name,
        active_symbols=active_symbols,
        soak_metrics=soak_metrics,
        demo_boundary_violation_count=demo_boundary_violation_count,
        cost_model=cost_model,
        tuned_param_names=tuned_param_names,
    )
    try:
        ipc_response = await one_shot_ipc_call(
            CRITERIA_IPC_METHOD,
            params=ipc_params,
            timeout=5.0,
            wrap_errors_as_http=False,
            error_context="strategist_promote_criteria",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "strategist_promote evaluate_promotion_criteria IPC failed strategy=%s err=%s",
            strategy_name,
            exc,
        )
        return None, f"ipc_unavailable:{type(exc).__name__}"

    # Rust 回 JSON-RPC 信封；verdict 在 result 或頂層（雙形容忍，鏡像 _fetch_target_current_params）。
    payload: Any = ipc_response
    if isinstance(ipc_response, dict) and "result" in ipc_response:
        payload = ipc_response["result"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            return None, f"ipc_parse_error:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return None, "ipc_unexpected_shape"
    if "verdict" not in payload:
        return None, "ipc_missing_verdict"
    return payload, None


async def _capture_pre_promotion_snapshot(
    target_engine: str,
    strategy_name: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """§2.5 步驟 1：促升寫入**前**捕捉 target engine 上**完整** typed param set。

    唯讀 IPC get_strategy_params{engine, strategy_name}（無 token），handle_get_strategy_params
    回完整 typed 序列化（§2.0 已證）。此完整 set 進 strategist_promotions.pre_promotion_params_json
    作 demote 的 EXACT 還原目標（§2.5）。

    回 (complete_params | None, err_reason | None)。IPC 失敗 → (None, reason)，caller fail-closed
    （促升前抓不到 live 現狀 = 不能促升，否則 demote 無還原基準）。
    """
    return await _fetch_target_current_params(target_engine, strategy_name)


def _insert_promotion_audit(
    *,
    action: str,  # "promote" | "demote"
    strategy_name: str,
    symbol: str,
    source_engine: str,
    target_engine: str,
    pre_promotion_params: dict[str, Any],
    promoted_params: dict[str, Any],
    criteria_verdict: str,
    criteria_input: dict[str, Any] | None,
    actor_id: str,
    gate_passed: bool,
    reverts_promotion_id: int | None,
    reason: str | None,
) -> int:
    """§2.6 同步 fail-closed 寫 learning.strategist_promotions，回新 row id。

    為何 fail-closed（非 fire-and-forget）：live 策略參數已改 + 無耐久 audit row = P8
    違反（root #8；audit_events 歷史稀疏甚至為空，不可只信 code path）。本函數**不**吞錯
    ——INSERT 失敗 raise，caller（promote 成功路徑）據此回 500 audit_write_failed + 告警，
    讓 operator 立即知曉「live 已改但 audit 沒落」並考慮 demote。這與 demo/paper 路徑的
    change_audit_log fire-and-forget（_record_promote_audit）刻意區分。

    JSONB 欄走 %s::jsonb + json.dumps（鏡像 governance_audit_log payload 慣例）。
    """
    applied_at_ms = int(time.time() * 1000)
    sql = f"""
        INSERT INTO {_PROMOTIONS_TABLE} (
            action, strategy_name, symbol, source_engine, target_engine,
            pre_promotion_params_json, promoted_params_json,
            criteria_verdict, criteria_input_json,
            actor_id, gate_passed, applied_at_ms,
            reverts_promotion_id, reason
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s::jsonb, %s::jsonb,
            %s, %s::jsonb,
            %s, %s, %s,
            %s, %s
        )
        RETURNING id
    """
    params = (
        action,
        strategy_name,
        symbol,
        source_engine,
        target_engine,
        json.dumps(pre_promotion_params),
        json.dumps(promoted_params),
        criteria_verdict,
        json.dumps(criteria_input) if criteria_input is not None else None,
        actor_id,
        gate_passed,
        applied_at_ms,
        reverts_promotion_id,
        reason,
    )
    with get_pg_conn() as conn:
        if conn is None:
            # fail-closed：promote 成功路徑呼此函數時 DB 不可用 = 無法落 audit row。
            raise RuntimeError("strategist_promotions_insert_failed: pg_unavailable")
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                new_row = cur.fetchone()
                new_id = int(new_row[0]) if new_row else -1
            conn.commit()
            return new_id
        except Exception:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001 — rollback best-effort
                pass
            raise


def _fetch_promotion_row(promotion_id: int) -> tuple[dict[str, Any] | None, str | None]:
    """讀 strategist_promotions 一筆 promote row（demote 的回滾目標）。

    回 (row_dict | None, err_reason | None)。DB 不可用 → (None, reason)。找不到 / 非
    promote action → (None, None)（caller 404）。
    """
    sql = f"""
        SELECT id, action, strategy_name, symbol, source_engine, target_engine,
               pre_promotion_params_json, promoted_params_json, applied_at_ms
          FROM {_PROMOTIONS_TABLE}
         WHERE id = %s
         LIMIT 1
    """
    with get_pg_conn() as conn:
        if conn is None:
            return None, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute(sql, (promotion_id,))
            tup = cur.fetchone()
            if tup is None:
                return None, None
            cols = [d.name for d in cur.description] if cur.description else []
            return dict(zip(cols, tup)), None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "strategist_promote fetch_promotion_row failed id=%s err=%s",
                promotion_id,
                exc,
            )
            return None, f"pg_error:{type(exc).__name__}"


def _as_param_dict(value: Any) -> dict[str, Any]:
    """把 JSONB 欄讀出的值正規化成 dict（driver 可能回 dict 或 JSON str）。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


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
        # P2-WP05-FUP-1：client 看 stable code；具體 fetch_reason（含 PG
        # exception class name）只進 log，避免把 PG 內部錯誤類型外洩給呼叫者。
        logger.warning(
            "strategist_promote: PG unavailable / query failed (fetch_reason=%s)",
            fetch_reason,
        )
        raise HTTPException(
            status_code=503,
            detail="pg_unavailable",
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

    # ── Step 4a: PHASE 2 flag gate（§2.1，僅 live promote）──
    # 順序 §2.2 ①：flag-OFF + live target → 409 promotion_disabled（fail-loud，
    # 不靜默降級成 demo，鏡像 POLICY-2 的 409 姿態）。flag 不擋 paper target、不擋
    # preview（已在 Step 4 返回）。flag-OFF 時 live promote 完全不可達 = bit-identical
    # 行為（除此 409）。為何在 5-gate 之前：flag 是業務總開關，比 signed-auth 廉價先拒。
    if body.target_engine == "live" and not _promotion_enabled():
        _record_promote_audit(
            actor_id=actor_id,
            request_body=body,
            source_row_id=source_row.get("id"),
            success=False,
            gate_failed="promotion_disabled",
            confirm_phase="apply",
            ipc_response=None,
            reason=f"flag {_PROMOTION_FLAG_ENV} is OFF",
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "promotion_disabled",
                "hint": (
                    f"Live strategist promotion is disabled. Set {_PROMOTION_FLAG_ENV}=1 "
                    f"on the engine environment to enable. "
                    f"Live 策略促升已停用（flag default-OFF）。"
                ),
            },
        )

    # ── Step 4b: PHASE 2 criteria gate（§2.4，僅 live promote，EDGE-ANCHORED）──
    # 順序 §2.2 ④：在 5-gate 前先跑廉價的 EDGE-ANCHORED criteria gate（不靠 demo PnL）。
    # route 算 soak/since-change/fills metric（§2.4.C）+ tuned-param diff（§2.4.F），經唯讀
    # IPC evaluate_promotion_criteria（token 豁免）由 engine 自查 live edge cell + cost wall +
    # boundary-vs-LIVE-envelope（§2.4.B/D）+ 跑判定。Reject/Pending → 409 criteria_not_met
    # （0 IPC promote）。criteria_input 留給 §2.6 audit 作 edge 證據快照。
    # 為何只對 live：promote 的 blast radius 在 live；paper target 不需 criteria（沿用既有行為）。
    criteria_input_snapshot: dict[str, Any] | None = None
    if body.target_engine == "live":
        # 先抓 pre-promotion live 完整 set（§2.5 步驟 1）——同時供 criteria 的 tuned-param diff
        # 與 demote 的 EXACT 還原目標。promote 前抓不到 live 現狀 → fail-closed 503。
        pre_promotion_params, pre_reason = await _capture_pre_promotion_snapshot(
            body.target_engine, body.strategy
        )
        if pre_reason is not None:
            logger.warning(
                "strategist_promote: pre-promotion snapshot unavailable strategy=%s reason=%s",
                body.strategy,
                pre_reason,
            )
            _record_promote_audit(
                actor_id=actor_id,
                request_body=body,
                source_row_id=source_row.get("id"),
                success=False,
                gate_failed="pre_promotion_snapshot_unavailable",
                confirm_phase="apply",
                ipc_response=None,
                reason=pre_reason,
            )
            raise HTTPException(
                status_code=503,
                detail="pre_promotion_snapshot_unavailable",
            )

        tuned_param_names = _diff_tuned_param_names(pre_promotion_params, source_params)
        soak_metrics = _fetch_demo_soak_metrics(body.strategy)
        if soak_metrics.get("degraded"):
            logger.warning(
                "strategist_promote: soak metric unavailable strategy=%s reason=%s",
                body.strategy,
                soak_metrics.get("degraded"),
            )
            raise HTTPException(status_code=503, detail="pg_unavailable")

        # IPC-CONTRACT Option A（Fix 1）：route 算齊 active_symbols + cost model +
        # boundary，連同 soak/tuned 一起傳 engine（engine 只自查 edge cell）。
        active_symbols = _resolve_active_symbols(body.strategy)
        cost_model = _load_live_cost_model()
        if cost_model is None:
            # cost model SSOT 讀失敗 = 無法量 cost wall = fail-closed（無證據不放行）。
            logger.warning(
                "strategist_promote: live cost model unavailable strategy=%s "
                "(risk_config_live.toml [slippage] unreadable)",
                body.strategy,
            )
            raise HTTPException(
                status_code=503, detail="criteria_evaluation_unavailable"
            )
        demo_boundary_violation_count = _compute_demo_boundary_violation_count(body.strategy)

        verdict_payload, criteria_reason = await _evaluate_criteria(
            strategy_name=body.strategy,
            active_symbols=active_symbols,
            soak_metrics=soak_metrics,
            demo_boundary_violation_count=demo_boundary_violation_count,
            cost_model=cost_model,
            tuned_param_names=tuned_param_names,
        )
        if criteria_reason is not None or verdict_payload is None:
            # criteria IPC 不可用 = 無 verdict = fail-closed（無證據不放行）。
            _record_promote_audit(
                actor_id=actor_id,
                request_body=body,
                source_row_id=source_row.get("id"),
                success=False,
                gate_failed="criteria_unavailable",
                confirm_phase="apply",
                ipc_response=None,
                reason=criteria_reason,
            )
            raise HTTPException(
                status_code=503,
                detail="criteria_evaluation_unavailable",
            )

        verdict = str(verdict_payload.get("verdict", ""))
        verdict_reason = verdict_payload.get("reason")
        # Fix 2 (P8/root-#8)：handler 分欄回 per_cell/active_count/edge_estimates_fresh，
        # **不**回 "criteria_input"。route 必須讀真鍵組裝 EDGE-ANCHORED 證據快照，否則
        # criteria_input_json 永遠 null（承 QC/CC HIGH finding）。
        criteria_input_snapshot = _criteria_input_from_payload(verdict_payload)
        # Fix 2：verdict casing 對齊——handler emit 小寫 tag（"eligible"），route 經
        # is_eligible 做 canonical .lower() 比對，杜絕「比大寫 Eligible 永久拒」bug。
        if not is_eligible(verdict):
            # Reject（direction/boundary/down-beta）或 Pending（證據不足）→ 409，0 IPC promote。
            # 今天 0 validated edge cell → criteria gate 對所有促升回 Pending/Reject = DESIRED（§2.9）。
            criteria_verdict_str = f"{verdict}:{verdict_reason}" if verdict_reason else verdict
            # denied 路徑同步寫 audit row（§2.6，best-effort 可接受因無 live 改動）。
            try:
                _insert_promotion_audit(
                    action="promote",
                    strategy_name=body.strategy,
                    symbol=body.symbol,
                    source_engine=body.source_engine,
                    target_engine=body.target_engine,
                    pre_promotion_params=pre_promotion_params or {},
                    promoted_params=source_params,
                    criteria_verdict=criteria_verdict_str,
                    criteria_input=criteria_input_snapshot,
                    actor_id=actor_id,
                    gate_passed=False,
                    reverts_promotion_id=None,
                    reason=f"criteria_not_met:{verdict_reason or verdict}",
                )
            except Exception as exc:  # noqa: BLE001 — denied 路徑無 live 改動，audit 失敗只 warn
                logger.warning(
                    "strategist_promote denied-audit write failed (best-effort) strategy=%s err=%s",
                    body.strategy,
                    exc,
                )
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "criteria_not_met",
                    "verdict": verdict,
                    "reason": verdict_reason,
                },
            )
    else:
        # paper target：無 criteria gate、無 pre-promotion snapshot（沿用既有行為）。
        pre_promotion_params = None

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
    # PHASE 0 AUTH-1：target_engine=="live" 時 update_strategy_params ∈ LIVE_WRITE_METHODS
    # → Rust chokepoint 要求 token。此路由的 live 分支已於 Step 5 過完整 5-gate
    # （_apply_target_gate → _verify_live_gate），故在此鑄 method-bound token 併入 params。
    # non-patch 類 hash 對象 = params 去 token 三欄 + engine（call_params_with_token 自動處理）。
    # demo/paper target 不鑄。
    if body.target_engine == "live":
        from .live_patch_token import call_params_with_token  # noqa: PLC0415
        ipc_params = call_params_with_token("update_strategy_params", ipc_params)
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
        # WP-05 Real Fix
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=500,
            detail=sanitize_exc_for_detail(exc, "rust_engine_unavailable"),
        ) from exc

    # ── Step 6b: Fix 3 — 重讀 live 完整 post-promotion typed set 作 promoted_params_json ──
    # 為何重讀（§2.5 步驟 1 + must-fix REVERSE-PROMOTE EXACTNESS）：IPC update_strategy_params
    # 是 deep MERGE（merge_strategy_params_json 只覆寫/新增、不刪 key），且 get_strategy_params
    # 回完整 typed 序列化。若 promoted_params_json 只存 source_params（PARTIAL tune delta），
    # demote 的 precondition 拿「完整 live set」canonical 比對「PARTIAL stored set」→ 必不等
    # → 每次合法 demote 都 409 live_changed_since_promotion（承 E2/QC HIGH）。修法：promote IPC
    # 成功後重讀 get_strategy_params{live} 取 **完整** post-promotion set，存 THAT；demote 才
    # full-vs-full 正確比對。重讀失敗 → 仍以 source_params fallback（loud warn），不阻 audit
    # （live 已改，audit 必落；fallback 下 demote precondition 可能誤 409，但不靜默丟 audit）。
    post_promotion_params: dict[str, Any] = source_params
    if body.target_engine == "live":
        reread_params, reread_reason = await _fetch_target_current_params(
            body.target_engine, body.strategy
        )
        if reread_reason is None and reread_params is not None:
            post_promotion_params = reread_params
        else:
            logger.warning(
                "strategist_promote: post-promotion live re-read failed strategy=%s "
                "reason=%s — promoted_params_json falls back to PARTIAL source set "
                "(demote precondition may 409; live already changed)",
                body.strategy,
                reread_reason,
            )

    # ── Step 7: PHASE 2 同步 fail-closed audit（§2.6，僅 live promote）──
    # 順序 §2.2 ⑨：IPC update_strategy_params{engine:live} 已回 OK（live 已改）→ **同步**
    # INSERT learning.strategist_promotions（action='promote'）。INSERT 失敗 → route 回 500
    # audit_write_failed + 結構化告警（live 已改但 audit 沒落 = 必須 loud；operator 須立即
    # 知曉並考慮 demote）。**不可吞錯靜默成功**——這是 must-fix C「commit gate 在 audit
    # 寫成功」的核心，與 demo/paper 的 change_audit_log fire-and-forget 刻意區分。
    promotion_id: int | None = None
    if body.target_engine == "live":
        try:
            promotion_id = _insert_promotion_audit(
                action="promote",
                strategy_name=body.strategy,
                symbol=body.symbol,
                source_engine=body.source_engine,
                target_engine=body.target_engine,
                pre_promotion_params=pre_promotion_params or {},
                # Fix 3：存 **完整** post-promotion live set（重讀 get_strategy_params），
                # 非 PARTIAL source_params → demote 的 full-vs-full precondition 才正確。
                promoted_params=post_promotion_params,
                criteria_verdict="Eligible",
                criteria_input=criteria_input_snapshot,
                actor_id=actor_id,
                gate_passed=True,
                reverts_promotion_id=None,
                reason=None,
            )
        except Exception as exc:  # noqa: BLE001 — fail-closed：audit 沒落 = loud 500
            logger.error(
                "strategist_promote AUDIT WRITE FAILED (live param already changed, "
                "audit row NOT persisted — operator must reconstruct/consider demote) "
                "strategy=%s symbol=%s row_id=%s err=%s pre_params=%s applied_params=%s",
                body.strategy,
                body.symbol,
                source_row.get("id"),
                exc,
                json.dumps(pre_promotion_params or {}),
                json.dumps(post_promotion_params),
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "audit_write_failed",
                    "hint": (
                        "Live promotion applied to engine but the strategist_promotions "
                        "audit row failed to persist. Operator action required: verify live "
                        "params and consider demote. "
                        "live 促升已套用但 audit row 寫入失敗，須人工核對 + 考慮 demote。"
                    ),
                },
            ) from exc

    # ── Step 8: success — change_audit_log（補充）+ return envelope ──
    response_data = {
        "ok": True,
        "phase": "apply",
        "strategy": body.strategy,
        "symbol": body.symbol,
        "source_engine": body.source_engine,
        "target_engine": body.target_engine,
        "applied_params": source_params,
        "source_row_id": source_row.get("id"),
        "promotion_id": promotion_id,
        "ipc_response": ipc_response,
        "ts_ms": int(time.time() * 1000),
        "source": body.source,
        "actor": actor_id,
    }
    logger.warning(
        "strategist_promote SUCCESS actor=%s strategy=%s symbol=%s %s→%s row_id=%s "
        "promotion_id=%s source=%s",
        actor_id,
        body.strategy,
        body.symbol,
        body.source_engine,
        body.target_engine,
        source_row.get("id"),
        promotion_id,
        body.source,
    )
    # change_audit_log 保留為補充（governance hub 統一審計流，fire-and-forget）；
    # learning.strategist_promotions 的同步 INSERT 才是 live 的 commit-gate 權威 row。
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


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — reverse-promote (demote) route / 反向促升（回滾）路由
# ═══════════════════════════════════════════════════════════════════════════════


class DemoteRequest(BaseModel):
    """POST /api/v1/strategist/demote body（§2.5）。

    demote = 把 live 策略參數 EXACT 還原到指向的 promote row 的 pre_promotion_params_json。
    criteria-EXEMPT（回滾到已知 live-safe 的 pre-promotion 狀態永遠允許，root #5/#6）；
    仍須 flag-ON + 5-gate + token（live write）+ precondition guard（live 自促升後未被改）。

    demote 是回滾安全方向；不需 confirm 兩步（operator 已明確指 promotion_id；但保留
    confirm 旗標與 promote 對稱，default-False 時回 precondition 預覽不寫 live）。
    """

    strategy: str = Field(..., description="Strategy name (whitelisted)")
    symbol: str = Field(
        ...,
        min_length=1,
        max_length=_MAX_SYMBOL_LEN,
        description="Symbol scope hint (audit/log only). 用於 audit scope。",
    )
    promotion_id: int = Field(
        ...,
        description="learning.strategist_promotions row id (action='promote') to roll back.",
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
            "False → precondition preview only (no IPC / no live write). "
            "True  → restore pre-promotion live set + write demote audit row."
        ),
    )


def _params_canonically_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """canonical byte-equal 比較兩 param set（鏡像 Phase-0 canonical_json）。

    為何 canonical 而非 == dict：避免 key 序 / float 字串化的假性不等（§2.5 步驟 3）。
    """
    return canonical_json(a) == canonical_json(b)


@strategist_promote_router.post("/demote")
async def post_strategist_demote(
    body: DemoteRequest,
    actor: Any = Depends(base.current_actor),
) -> dict[str, Any]:
    """POST /api/v1/strategist/demote — EXACT 回滾一次 live 促升（§2.5）。

    流程：
      ① flag gate（§2.1，與 promote 共用 OPENCLAW_STRATEGIST_PROMOTION_ENABLED）
      ② operator-role（always）
      ③ 取 promote row（strategist_promotions.promotion_id，必 action='promote'）
      ④ precondition guard：IPC get_strategy_params{live} 取當前 live set，canonical 比對
         vs row.promoted_params_json；不等 → 409 live_changed_since_promotion
      ⑤ 5-gate `_apply_target_gate(actor,"live")`（demote 是 live write）
      ⑥ token mint + IPC update_strategy_params{live} 送回 row.pre_promotion_params_json
         （完整 typed set → EXACT 行為還原，§2.5 裁決 B）
      ⑦ 同步 fail-closed 寫 strategist_promotions（action='demote', reverts_promotion_id）

    **criteria-EXEMPT**：回滾到 pre-promotion 已知 live-safe 狀態永遠允許（root #5/#6）。

    Returns:
      200 + envelope（preview 或 demoted）
      400 unknown strategy / 422 missing field
      403 gate denial
      404 promotion_id 不存在 / 非 promote action
      409 promotion_disabled（flag-OFF）/ live_changed_since_promotion
      500 audit_write_failed / IPC failure
    """
    actor_id = str(getattr(actor, "actor_id", "?"))

    # ── Step 1: validate inputs ──
    if body.strategy not in _ALLOWED_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"strategy must be one of {sorted(_ALLOWED_STRATEGIES)}, got {body.strategy!r}",
        )
    if not body.symbol.replace("_", "").isalnum() or not body.symbol.isupper():
        raise HTTPException(
            status_code=400,
            detail=f"symbol must be uppercase alphanumeric (e.g. 'BTCUSDT'); got {body.symbol!r}",
        )

    # ── Step 2: flag gate（demote 是 live write，共用 promotion flag）──
    # 為何 demote 也要 flag：demote 是 live update_strategy_params 寫入，flag-OFF 時整個
    # 促升機器（含回滾）未上線。但 demote 是安全方向 → flag-OFF 仍回 409 fail-loud（不
    # 靜默），讓 operator 知道機器沒開（與 promote 同 409 promotion_disabled 姿態）。
    if not _promotion_enabled():
        raise HTTPException(
            status_code=409,
            detail={
                "error": "promotion_disabled",
                "hint": (
                    f"Live strategist demote is disabled. Set {_PROMOTION_FLAG_ENV}=1 "
                    f"to enable. Live 策略回滾已停用（flag default-OFF）。"
                ),
            },
        )

    # ── Step 3: operator-role（always）──
    from .governance_routes import _require_operator_role  # noqa: PLC0415
    _require_operator_role(actor)

    # ── Step 4: 取 promote row ──
    row, fetch_reason = _fetch_promotion_row(body.promotion_id)
    if fetch_reason == "pg_unavailable" or (fetch_reason and fetch_reason.startswith("pg_error")):
        logger.warning(
            "strategist_demote: PG unavailable / query failed (fetch_reason=%s)", fetch_reason
        )
        raise HTTPException(status_code=503, detail="pg_unavailable")
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No strategist_promotions row found for promotion_id={body.promotion_id}.",
        )
    if row.get("action") != "promote":
        raise HTTPException(
            status_code=400,
            detail=(
                f"promotion_id={body.promotion_id} has action={row.get('action')!r}; "
                f"can only demote a 'promote' row."
            ),
        )
    target_engine = str(row.get("target_engine") or "live")
    pre_promotion_params = _as_param_dict(row.get("pre_promotion_params_json"))
    promoted_params = _as_param_dict(row.get("promoted_params_json"))

    # ── Step 5: precondition guard（§2.5 步驟 3）──
    # 取當前 live set，canonical 比對 vs 促升當下寫入的 promoted_params_json。
    # 不等 → live 自促升後被其他路徑改過 → 409（避免盲目覆寫中間的合法改動）。
    current_live, current_reason = await _fetch_target_current_params(
        target_engine, body.strategy
    )
    if current_reason is not None or current_live is None:
        logger.warning(
            "strategist_demote: current live params unavailable strategy=%s reason=%s",
            body.strategy,
            current_reason,
        )
        raise HTTPException(status_code=503, detail="live_params_unavailable")
    changed_since_promotion = not _params_canonically_equal(current_live, promoted_params)

    # ── Step 6: preview path（confirm=false）──
    if not body.confirm:
        return {
            "ok": True,
            "phase": "preview",
            "confirm_required": True,
            "action": "demote",
            "promotion_id": body.promotion_id,
            "strategy": body.strategy,
            "symbol": body.symbol,
            "target_engine": target_engine,
            "current_live_params": current_live,
            "restore_target_params": pre_promotion_params,
            "changed_since_promotion": changed_since_promotion,
            "diff": _diff_params(current_live, pre_promotion_params),
            "next_step": (
                "Re-call with confirm=true to restore pre-promotion live params "
                "(blocked with 409 if live changed since promotion). "
                "重呼 confirm=true 以還原（live 中途被改則 409）。"
            ),
            "ts_ms": int(time.time() * 1000),
            "actor": actor_id,
        }

    # ── Step 7: precondition fail → 409（confirm=true 才硬擋寫入）──
    if changed_since_promotion:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "live_changed_since_promotion",
                "hint": (
                    "Live params changed since promotion_id was applied; refusing to "
                    "blindly overwrite. Inspect the intervening change first. "
                    "live 自促升後被改過，拒絕盲目覆寫；請先查清中間改動。"
                ),
            },
        )

    # ── Step 8: 5-gate（demote 是 live write，full 5-gate）──
    try:
        _apply_target_gate(actor, target_engine)
    except HTTPException:
        # demote 的 5-gate 拒絕沿用 promote 的審計慣例（change_audit_log fire-and-forget）。
        raise

    # ── Step 9: token mint + IPC update_strategy_params{live} 還原完整 pre-promotion set ──
    # §2.5 裁決 B：送回完整 typed param set → merge 後 typed deserialize 整 struct →
    # promote 期間任何 typed 欄位值變動都被還原（EXACT 行為還原）。
    ipc_params = {
        "engine": target_engine,
        "strategy_name": body.strategy,
        "params_json": json.dumps(pre_promotion_params),
        "source": body.source,
        "reason": (
            f"demote:reverts_promotion_id={body.promotion_id}:symbol={body.symbol}"
        ),
    }
    if target_engine == "live":
        from .live_patch_token import call_params_with_token  # noqa: PLC0415
        ipc_params = call_params_with_token("update_strategy_params", ipc_params)
    try:
        ipc_response = await one_shot_ipc_call(
            "update_strategy_params",
            params=ipc_params,
            timeout=5.0,
            wrap_errors_as_http=False,
            error_context="strategist_demote_apply",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "strategist_demote IPC failed strategy=%s promotion_id=%s err=%s",
            body.strategy,
            body.promotion_id,
            exc,
        )
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=500,
            detail=sanitize_exc_for_detail(exc, "rust_engine_unavailable"),
        ) from exc

    # ── Step 10: 同步 fail-closed audit（§2.6，action='demote'）──
    try:
        demote_id = _insert_promotion_audit(
            action="demote",
            strategy_name=body.strategy,
            symbol=body.symbol,
            source_engine=str(row.get("source_engine") or target_engine),
            target_engine=target_engine,
            # demote row 的 pre/post：pre = 促升後 live set（即被回滾掉的狀態）；
            # promoted = 還原後的 pre-promotion set（demote 寫入 live 的）。
            pre_promotion_params=promoted_params,
            promoted_params=pre_promotion_params,
            criteria_verdict="demote_exempt",
            criteria_input=None,
            actor_id=actor_id,
            gate_passed=True,
            reverts_promotion_id=body.promotion_id,
            reason="manual_demote",
        )
    except Exception as exc:  # noqa: BLE001 — fail-closed：live 已還原但 audit 沒落 = loud 500
        logger.error(
            "strategist_demote AUDIT WRITE FAILED (live restored, audit row NOT persisted) "
            "strategy=%s promotion_id=%s err=%s restored_params=%s",
            body.strategy,
            body.promotion_id,
            exc,
            json.dumps(pre_promotion_params),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "audit_write_failed",
                "hint": (
                    "Demote restored live params but the audit row failed to persist. "
                    "demote 已還原 live 但 audit row 寫入失敗，須人工核對。"
                ),
            },
        ) from exc

    logger.warning(
        "strategist_demote SUCCESS actor=%s strategy=%s symbol=%s reverts_promotion_id=%s "
        "demote_id=%s",
        actor_id,
        body.strategy,
        body.symbol,
        body.promotion_id,
        demote_id,
    )
    return {
        "ok": True,
        "phase": "apply",
        "action": "demote",
        "strategy": body.strategy,
        "symbol": body.symbol,
        "target_engine": target_engine,
        "reverts_promotion_id": body.promotion_id,
        "demote_id": demote_id,
        "restored_params": pre_promotion_params,
        "ipc_response": ipc_response,
        "ts_ms": int(time.time() * 1000),
        "actor": actor_id,
    }


__all__ = [
    "strategist_promote_router",
    "PromoteRequest",
    "DemoteRequest",
]
