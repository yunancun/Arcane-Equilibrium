"""REF-20 Sprint A R3-T0 — replay.simulated_fills writer.
REF-20 Sprint A R3-T0 — replay.simulated_fills 寫入器。

MODULE_NOTE (EN):
    Parses the replay_runner output JSON (`replay_report.json`) produced by
    the Rust binary (`rust/openclaw_engine::replay::report_writer`) and
    INSERTs each fill into ``replay.simulated_fills`` (V050 schema).
    Called from the POST /api/v1/replay/run/{run_id}/finalize endpoint
    after the subprocess has exited.

    Sprint A scope decisions (R3 plan §6.R3 + V050 17-col contract):

      - Synthetic walker fills emit ``side ∈ {long, short}`` (V050 CHECK
        accepts ``buy/sell/long/short`` so no remapping needed).
      - ``evidence_source_tier`` comes from the JSON fill; we validate
        against V050 CHECK allowlist
        ``{calibrated_replay, synthetic_replay, counterfactual_replay}``
        and SKIP rows with non-allowlist tiers (the Rust binary does not
        currently emit ``real_outcome`` but defense-in-depth).
      - ``fee = 0.0``, ``fee_rate = 0.0`` — Sprint A has no fee model.
        V050 CHECK only requires ``qty > 0 AND price > 0``; ``fee_rate``
        is unconstrained at SQL level so 0.0 is accepted. R6 calibration
        sprint will overwrite when fee model lands.
      - ``liquidity_role = 'taker'`` — synthetic walker assumption (taker
        is the conservative cost class). V050 CHECK requires
        ``maker | taker | unknown``.
      - ``execution_model_version = 'synthetic_v1'`` — sentinel for the
        Sprint A walker. R6+ replaces with calibrated model identifiers.
      - ``ci_low_bps`` / ``ci_mid_bps`` / ``ci_high_bps`` = NULL — no
        per-fill confidence model in Sprint A. V050 CHECK ordering
        constraint allows all three NULL.
      - ``intent_id`` = NULL — synthetic walker has no IntentProcessor
        lineage (V3 §6.2 forbids replay coupling to live intent path).
      - ``decision_lease_id`` = NULL — V3 §6.2 forbids replay acquiring
        leases. V3 §4.1 allows METADATA-only reference here when the
        replay represents a real live decision; Sprint A walker has none.
      - ``idempotency_key`` = ``f"{run_id}:{fill_index}"`` — V050 has
        UNIQUE ``(experiment_id, idempotency_key)`` so two runs against
        the same experiment are de-duplicated by fill index. INSERT uses
        ``ON CONFLICT (experiment_id, idempotency_key) DO NOTHING``
        for idempotent re-finalize.
      - ``payload`` JSONB caps at 4 KB per fill (DoS bound) — overflow
        gets a truncated ``{"_truncated": true, "_original_size": N}``
        marker and is still INSERTed (data integrity > best-effort
        debug payload).

    What this module does NOT do:
      - PG xact lifecycle (caller-owned via ``run_finalize_route``).
      - Schema validation / DDL (V050 owns).
      - Spawn / poll subprocess (route_helpers owns).
      - Write report_artifacts row (canary_writer owns; called separately
        by ``run_finalize_route`` in the same xact).

MODULE_NOTE (中):
    解析 Rust binary 寫的 replay_runner 輸出 JSON（``replay_report.json``）
    然後 INSERT 每筆 fill 到 ``replay.simulated_fills``（V050 schema）。
    由 POST /api/v1/replay/run/{run_id}/finalize endpoint 在 subprocess
    結束後呼叫。

    Sprint A scope 決策（R3 plan §6.R3 + V050 17-col 契約）：

      - synthetic walker fill 發 ``side ∈ {long, short}``（V050 CHECK 接受
        ``buy/sell/long/short`` 故不需重映射）。
      - ``evidence_source_tier`` 來自 JSON fill；對照 V050 CHECK 白名單
        ``{calibrated_replay, synthetic_replay, counterfactual_replay}``
        驗，非白名單 tier 的列 SKIP（Rust binary 當前不發 ``real_outcome``，
        但縱深防禦保留 skip 邏輯）。
      - ``fee = 0.0`` / ``fee_rate = 0.0`` — Sprint A 無 fee 模型；V050
        CHECK 僅要求 ``qty > 0 AND price > 0``，``fee_rate`` SQL 層無約束
        故 0.0 可接受。R6 calibration sprint 將以 fee 模型覆寫。
      - ``liquidity_role = 'taker'`` — synthetic walker 假設（taker 為
        保守 cost class）。V050 CHECK 要求 ``maker | taker | unknown``。
      - ``execution_model_version = 'synthetic_v1'`` — Sprint A walker
        sentinel。R6+ 換為 calibrated 模型識別字。
      - ``ci_low_bps / ci_mid_bps / ci_high_bps`` = NULL — Sprint A 無 per-fill
        confidence 模型。V050 CHECK ordering 允許三者皆 NULL。
      - ``intent_id`` = NULL — synthetic walker 無 IntentProcessor lineage
        （V3 §6.2 禁 replay 耦合 live intent path）。
      - ``decision_lease_id`` = NULL — V3 §6.2 禁 replay 取 lease。V3 §4.1
        允許 METADATA-only 參考當 replay 代表真 live decision；Sprint A 無此。
      - ``idempotency_key`` = ``f"{run_id}:{fill_index}"`` — V050 有
        UNIQUE ``(experiment_id, idempotency_key)``，同 experiment 兩次
        run 以 fill index 去重。INSERT 用
        ``ON CONFLICT (experiment_id, idempotency_key) DO NOTHING``
        以容忍 idempotent re-finalize。
      - ``payload`` JSONB 每 fill 上限 4 KB（DoS bound）— 超過則用截斷
        ``{"_truncated": true, "_original_size": N}`` 標記寫入（資料完整
        性 > best-effort debug payload）。

    本模組不做：
      - PG xact 生命周期（``run_finalize_route`` 持）。
      - schema 驗證 / DDL（V050 擁有）。
      - spawn / poll subprocess（route_helpers 擁有）。
      - 寫 report_artifacts row（canary_writer 擁有；同 xact 內由
        ``run_finalize_route`` 另外呼叫）。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R3
V050 schema: sql/migrations/V050__replay_simulated_fills.sql (17-col contract)
Rust source: rust/openclaw_engine/src/replay/runner.rs::SimulatedFill
            rust/openclaw_engine/src/replay/report_writer.rs::ReportEnvelope

REF-20 Sprint B2 R5-T5 extension (this commit):
    The Rust runner now emits an additional ``result.decision_traces`` field
    (one entry per tick that produced ≥1 strategy action). When the runner
    walked the adapter pipeline (R5-T3 strategy + risk gate path), each
    `Open` action carries a deterministic SHA-256 ``intent_signature`` — see
    ``rust/openclaw_engine/src/replay/strategy_adapter.rs::compute_intent_signature``.
    R5-T5 (this module's responsibility): match each accepted fill to the
    strategy decision that produced it and inject a ``_replay_decision_evidence``
    sub-object into the V050 ``payload`` jsonb so the audit chain can be
    reconstructed without re-parsing the report from the raw JSON.

    Schema (PA design §6.1, jsonb-only — NO V### migration in R5-T5 scope):
        payload jsonb already exists in V050 (col 17). R5-T5 widens the
        per-fill object with one optional reserved key:

            payload._replay_decision_evidence = {
                "signal_id":         "<ts_ms>:<symbol>:<side>",  # composite
                "strategy_decision": "open" | "close",
                "risk_decision":     "accepted" | "rejected",
                "rejected_reason":   None | "<reason str>",
                "intent_signature":  "<sha256 hex>" | None,
                "intended_qty":      <float>,
                "intended_price":    <float>,
            }

    Match algorithm: for each fill row, find the first decision_trace entry
    whose `(ts_ms, symbol)` matches and the action's `side` aligns. Fill
    matching is greedy (one decision_trace entry can be matched at most once);
    unmatched fills get ``_replay_decision_evidence = None`` so callers can
    distinguish legacy synthetic-walker fills (no trace) from adapter-path
    fills with truncated trace.

REF-20 Sprint B2 R5-T5 擴展（本 commit）：
    Rust runner 現額外發 ``result.decision_traces``（每 tick 至少一個策略
    action 即記一筆）。adapter 路徑（R5-T3 strategy + risk gate）下每個
    `Open` action 攜帶確定性 SHA-256 ``intent_signature``。R5-T5（本模組）
    將每筆 accepted fill 與其對應策略決策比對並把 ``_replay_decision_evidence``
    子物件注入 V050 ``payload`` jsonb，使審計鏈無需重 parse raw JSON 即可
    重建。Schema 限於 jsonb（R5-T5 範圍**不**新增 V### migration）。
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Constants / 常量 ────────────────────────────────────────────────

# V050 CHECK chk_replay_simulated_fills_evidence_tier allowlist.
# V050 CHECK chk_replay_simulated_fills_evidence_tier 白名單。
V050_ALLOWED_TIER_VALUES = frozenset({
    "calibrated_replay",
    "synthetic_replay",
    "counterfactual_replay",
})

# V050 CHECK chk_replay_simulated_fills_side allowlist.
# V050 CHECK chk_replay_simulated_fills_side 白名單。
V050_ALLOWED_SIDE_VALUES = frozenset({"buy", "sell", "long", "short"})

# V050 CHECK chk_replay_simulated_fills_liquidity_role allowlist.
# V050 CHECK chk_replay_simulated_fills_liquidity_role 白名單。
V050_ALLOWED_LIQUIDITY_ROLES = frozenset({"maker", "taker", "unknown"})

# Sprint A defaults (see MODULE_NOTE for rationale).
# Sprint A 預設值（理由見 MODULE_NOTE）。
LIQUIDITY_ROLE_DEFAULT = "taker"
EXECUTION_MODEL_VERSION_DEFAULT = "synthetic_v1"
FEE_DEFAULT = 0.0
FEE_RATE_DEFAULT = 0.0
REJECTED_FILL_QTY_SENTINEL = 1e-12

# Per-fill JSONB payload size cap (DoS bound); fills with bigger raw payload
# get truncated to a {"_truncated": true, "_original_size": N} marker.
# 每 fill JSONB payload 大小上限（DoS bound）；超過用截斷標記。
MAX_PAYLOAD_BYTES = 4 * 1024  # 4 KB

# Replay report JSON schema_version we accept. Bump when downstream contract
# changes; mismatch = raise (fail-closed).
# 接受的 replay report JSON schema_version。下游契約變更時 bump；不符 raise。
SUPPORTED_REPORT_SCHEMA_VERSIONS = frozenset({1})

# Maximum bytes we read from replay_report.json (DoS bound on disk file).
# 從 replay_report.json 讀取的 byte 上限（disk file DoS bound）。
MAX_REPORT_BYTES = 16 * 1024 * 1024  # 16 MB; fill list dominates


# ─── Result type / 結果型別 ──────────────────────────────────────────


@dataclass(frozen=False)
class SimulatedFillsWriteResult:
    """Outcome of a ``persist_replay_report`` call.
    ``persist_replay_report`` 呼叫結果。

    Fields / 欄位:
      - fills_inserted        UUID-affected rows from ON CONFLICT-aware INSERT.
      - fills_skipped         malformed / out-of-allowlist tier rows skipped.
      - fills_truncated       rows whose payload exceeded MAX_PAYLOAD_BYTES.
      - errors                short reason strings; non-fatal observability.
    """

    fills_inserted: int = 0
    fills_skipped: int = 0
    fills_truncated: int = 0
    errors: list[str] = field(default_factory=list)


# ─── Parser / 解析器 ─────────────────────────────────────────────────


def parse_replay_report_json(report_path: Path) -> dict[str, Any]:
    """Read + parse ``replay_report.json`` with schema_version sanity.
    讀 + 解析 ``replay_report.json``，含 schema_version 檢查。

    Args:
        report_path: filesystem Path resolved by caller (path-traversal
            guard is the caller's responsibility — see ``run_finalize_route``).

    Returns / 回傳:
        Parsed envelope dict (the JSON top-level object).

    Raises / 異常:
        ValueError: missing / malformed schema_version, missing ``result``,
                    missing ``result.fills``.
        OSError: file read failure (caller maps to 410 in finalize route).
        json.JSONDecodeError: invalid JSON.
    """
    # Guard against pathological large files (DoS bound).
    # 防禦病態大檔（DoS bound）。
    try:
        size = report_path.stat().st_size
    except OSError:
        # Re-raise so caller maps to 410 replay_report_artifact_missing.
        # 上拋讓 caller map 到 410 replay_report_artifact_missing。
        raise
    if size > MAX_REPORT_BYTES:
        raise ValueError(
            f"replay_report.json size {size} exceeds cap {MAX_REPORT_BYTES} bytes"
        )

    with open(report_path, "rb") as f:
        raw = f.read(MAX_REPORT_BYTES)
    envelope = json.loads(raw.decode("utf-8"))

    if not isinstance(envelope, dict):
        raise ValueError(
            f"replay_report.json top-level is not an object: type={type(envelope).__name__}"
        )

    schema_version = envelope.get("schema_version")
    if schema_version not in SUPPORTED_REPORT_SCHEMA_VERSIONS:
        raise ValueError(
            f"unsupported replay_report schema_version={schema_version!r}; "
            f"supported={sorted(SUPPORTED_REPORT_SCHEMA_VERSIONS)}"
        )

    result = envelope.get("result")
    if not isinstance(result, dict):
        raise ValueError(
            f"replay_report.json missing 'result' object: got type="
            f"{type(result).__name__}"
        )

    fills = result.get("fills")
    if not isinstance(fills, list):
        raise ValueError(
            f"replay_report.json missing 'result.fills' list: got type="
            f"{type(fills).__name__}"
        )

    return envelope


# ─── Decision-trace helpers (R5-T5) / 決策追蹤輔助 ────────────────────


def extract_decision_traces(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """Return ``result.decision_traces`` list (empty if absent / wrong type).
    回傳 ``result.decision_traces`` list（缺或型別錯則回空 list）。

    REF-20 Sprint B2 R5-T5 (per dispatch §11.1).

    The Rust runner adds ``decision_traces`` as a top-level key inside
    ``result`` only when the adapter pipeline ran (R5-T3 path). For
    synthetic-walker runs (proof_1/4/5 baseline) the field is absent or
    serialized as ``[]`` via ``#[serde(default)]``. We tolerate both.

    Rust runner 僅 adapter 路徑（R5-T3）執行時才在 ``result`` 加
    ``decision_traces``。synthetic-walker 路徑（proof_1/4/5 baseline）
    下欄位缺或序列化為 ``[]``（``#[serde(default)]``）。兩者皆容忍。

    Args:
        envelope: parsed replay_report.json dict (top-level).

    Returns / 回傳:
        ``list[dict]`` — possibly empty; never raises.
    """
    result = envelope.get("result") or {}
    if not isinstance(result, dict):
        return []
    traces = result.get("decision_traces")
    if not isinstance(traces, list):
        return []
    # Defense-in-depth: only keep entries whose required keys are present
    # and well-typed; unknown shapes are dropped silently to avoid raising.
    # 縱深防禦：僅保留必要 key 齊全且型別正確的 entry；未知 shape 靜默丟棄
    # 避免 raise。
    return [
        t for t in traces
        if isinstance(t, dict)
        and isinstance(t.get("ts_ms"), int)
        and isinstance(t.get("symbol"), str)
        and isinstance(t.get("actions_emitted"), list)
    ]


def _normalize_action_side(action: dict[str, Any]) -> Optional[str]:
    """Translate a `StrategyActionTrace` enum to a ``long|short`` side string.
    將 `StrategyActionTrace` enum 翻譯為 ``long|short`` side 字串。

    Rust serde tag: `Open { is_long: bool, ... }` / `Close { ... }`.
    serde untagged: serializes as ``{"Open": {...}}`` or ``{"Close": {...}}``.

    For ``Open`` we return ``"long"`` if ``is_long`` else ``"short"``; for
    ``Close`` we return ``None`` because close-side fills emit ``side``
    opposite to the position which is not on the trace entry directly.

    Returns / 回傳:
        ``"long"`` / ``"short"`` for Open; ``None`` for Close (caller
        treats absence as "match-any-close-direction").
    """
    if "Open" in action and isinstance(action.get("Open"), dict):
        is_long = bool(action["Open"].get("is_long"))
        return "long" if is_long else "short"
    if "Close" in action:
        return None
    return None


def build_decision_evidence_index(
    decision_traces: list[dict[str, Any]],
) -> dict[Tuple[int, str, Optional[str]], list[dict[str, Any]]]:
    """Index decision-trace actions by ``(ts_ms, symbol, side)`` for fill match.
    依 ``(ts_ms, symbol, side)`` 索引決策 trace action 供 fill 比對。

    Returns / 回傳:
        Dict mapping ``(ts_ms, symbol, side)`` to a FIFO list of matched
        action dicts (each dict pre-flattened with strategy_name +
        indicators_present + intent_signature etc. for downstream injection).
        First-match-wins consumption: caller pops from the front of the list.

    REF-20 Sprint B2 R5-T5: greedy matching (one trace action consumed at
    most once) avoids duplicate evidence injection on multi-fill same-tick
    scenarios. Side=None bucket holds Close-side traces (match-any-side).
    """
    idx: dict[Tuple[int, str, Optional[str]], list[dict[str, Any]]] = {}
    for entry in decision_traces:
        ts_ms = int(entry["ts_ms"])
        symbol = str(entry["symbol"])
        strategy_name = str(entry.get("strategy_name", ""))
        indicators_present = bool(entry.get("indicators_present", False))
        for action in entry.get("actions_emitted", []):
            if not isinstance(action, dict):
                continue
            side = _normalize_action_side(action)
            kind: str
            payload_obj: dict[str, Any] = {}
            if "Open" in action and isinstance(action.get("Open"), dict):
                kind = "open"
                inner = action["Open"]
                payload_obj.update(
                    {
                        "intent_signature": inner.get("intent_signature"),
                        "intended_qty": float(inner.get("qty", 0.0)),
                        "intended_price": float(inner.get("price", 0.0))
                        if inner.get("price") is not None else None,
                        "confidence": float(inner.get("confidence", 0.0)),
                        "order_type": inner.get("order_type"),
                    }
                )
            elif "Close" in action and isinstance(action.get("Close"), dict):
                kind = "close"
                inner = action["Close"]
                payload_obj.update(
                    {
                        "intent_signature": None,
                        "intended_qty": None,
                        "intended_price": None,
                        "confidence": float(inner.get("confidence", 0.0)),
                        "reason": inner.get("reason"),
                    }
                )
            else:
                continue
            payload_obj["strategy_name"] = strategy_name
            payload_obj["indicators_present"] = indicators_present
            payload_obj["strategy_decision"] = kind
            key = (ts_ms, symbol, side)
            idx.setdefault(key, []).append(payload_obj)
    return idx


def consume_decision_evidence_for_fill(
    fill: dict[str, Any],
    index: dict[Tuple[int, str, Optional[str]], list[dict[str, Any]]],
) -> Optional[dict[str, Any]]:
    """Pop the first matching decision evidence dict for a given fill.
    為指定 fill 取出（pop）第一筆比對到的 decision evidence。

    Match key tries (in order):
        1. Exact ``(ts_ms, symbol, side)`` for Open traces.
        2. Fallback ``(ts_ms, symbol, None)`` for Close traces (side=None
           bucket).

    Returns / 回傳:
        Decision evidence dict (with synthesized ``signal_id`` + ``risk_decision``
        + ``rejected_reason`` keys) on match; ``None`` on no match.

    REF-20 Sprint B2 R5-T5：match algorithm + greedy consumption (one trace
    action consumed at most once per fill).
    """
    try:
        ts_ms = int(fill.get("ts_ms", 0))
        symbol = str(fill.get("symbol", ""))
        side = fill.get("side")
        side_str = str(side) if isinstance(side, str) else None
    except (TypeError, ValueError):
        return None

    # Try the exact-side bucket first (Open traces), then fall back to the
    # side=None bucket (Close traces).
    # 先試精確 side bucket（Open trace），再 fallback side=None bucket（Close trace）。
    for key in [(ts_ms, symbol, side_str), (ts_ms, symbol, None)]:
        bucket = index.get(key)
        if bucket:
            evidence = bucket.pop(0)
            # Risk decision: qty>0 → accepted; qty==0 ghost row → rejected.
            # 風控決策：qty>0 → 接受；qty==0 ghost row → 拒絕。
            try:
                qty = float(fill.get("qty", 0.0))
            except (TypeError, ValueError):
                qty = 0.0
            risk_decision = "accepted" if qty > 0.0 else "rejected"
            rejected_reason = None
            if risk_decision == "rejected":
                # The fill itself does not carry the rejection reason (R5-T3
                # records it in `last_action_label` at runner level); we
                # surface the strategy_name + a generic marker so downstream
                # auditors can correlate via diagnostics.last_action_label.
                # fill 本身不含拒絕原因（R5-T3 由 runner 寫 last_action_label）；
                # 此處給 strategy_name + 通用標記，下游審計透過
                # diagnostics.last_action_label 關聯。
                rejected_reason = (
                    f"qty=0_ghost_fill;strategy={evidence.get('strategy_name', '')}"
                )
            evidence_out: dict[str, Any] = {
                "signal_id": f"{ts_ms}:{symbol}:{side_str or 'close'}",
                "strategy_decision": evidence.get("strategy_decision"),
                "risk_decision": risk_decision,
                "rejected_reason": rejected_reason,
                "intent_signature": evidence.get("intent_signature"),
                "intended_qty": evidence.get("intended_qty"),
                "intended_price": evidence.get("intended_price"),
                "strategy_name": evidence.get("strategy_name"),
                "indicators_present": evidence.get("indicators_present"),
                "confidence": evidence.get("confidence"),
            }
            return evidence_out
    return None


# ─── Row mapper / 列映射器 ───────────────────────────────────────────


def map_fill_to_v050_row(
    fill: dict[str, Any],
    *,
    experiment_id: str,
    run_id: str,
    fill_index: int,
    strategy_name: str,
    decision_evidence: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Map JSON fill dict → V050 17-col INSERT params dict (or None to skip).
    將 JSON fill dict 映射到 V050 17-col INSERT 參數 dict（None 表 skip）。

    Args:
        fill: a single dict from ``result.fills`` list.
        experiment_id: V049 experiment uuid (FK target).
        run_id: V045 run uuid (used for idempotency_key composition).
        fill_index: positional index in the fills list (used for
                    idempotency_key composition; identical fills_emitted
                    sequence yields identical idempotency_key).
        strategy_name: V049 row's manifest_jsonb.strategy (looked up by caller).
        decision_evidence: REF-20 Sprint B2 R5-T5 — optional decision evidence
            dict (from ``consume_decision_evidence_for_fill``). When present,
            inject as ``payload._replay_decision_evidence`` jsonb sub-object.
            ``None`` means either (a) synthetic-walker run (no decision_traces)
            or (b) adapter-path run with no matching trace for this fill.
            REF-20 Sprint B2 R5-T5：選用決策證據 dict（來自
            ``consume_decision_evidence_for_fill``）。提供時注入為
            ``payload._replay_decision_evidence`` jsonb 子物件。``None`` 表示
            (a) synthetic-walker run（無 decision_traces）或 (b) adapter-path
            run 但本 fill 無對應 trace。

    Returns / 回傳:
        Mapped param dict on accept; ``None`` on skip (caller increments
        ``fills_skipped``).

    Skip conditions / Skip 條件:
        - ``evidence_source_tier`` not in V050 CHECK allowlist.
        - ``side`` not in V050 CHECK allowlist.
        - ``qty <= 0`` or ``price <= 0`` (V050 CHECK enforces).
        - missing required JSON keys (ts_ms / symbol / side / qty / price /
          evidence_source_tier).
    """
    # Required keys probe (skip on any missing).
    # 必要 key 檢查（缺則 skip）。
    required = ("ts_ms", "symbol", "side", "qty", "price", "evidence_source_tier")
    for k in required:
        if k not in fill:
            logger.warning(
                "map_fill_to_v050_row: skip fill_index=%d missing key=%s",
                fill_index, k,
            )
            return None

    # Type / value validation (V050 CHECK enforce-time match).
    # 型別 / 值驗證（V050 CHECK 強制等價）。
    side = fill.get("side")
    if side not in V050_ALLOWED_SIDE_VALUES:
        logger.warning(
            "map_fill_to_v050_row: skip fill_index=%d side=%r not in allowlist",
            fill_index, side,
        )
        return None

    tier = fill.get("evidence_source_tier")
    if tier not in V050_ALLOWED_TIER_VALUES:
        logger.warning(
            "map_fill_to_v050_row: skip fill_index=%d evidence_source_tier=%r "
            "not in allowlist", fill_index, tier,
        )
        return None

    try:
        qty = float(fill["qty"])
        price = float(fill["price"])
    except (TypeError, ValueError):
        logger.warning(
            "map_fill_to_v050_row: skip fill_index=%d qty/price not numeric",
            fill_index,
        )
        return None

    if qty < 0.0 or price <= 0.0:
        logger.warning(
            "map_fill_to_v050_row: skip fill_index=%d qty=%s price=%s "
            "(V050 CHECK qty>0 AND price>0)", fill_index, qty, price,
        )
        return None
    is_ghost_fill = qty == 0.0
    db_qty = REJECTED_FILL_QTY_SENTINEL if is_ghost_fill else qty

    try:
        ts_ms = int(fill["ts_ms"])
    except (TypeError, ValueError):
        logger.warning(
            "map_fill_to_v050_row: skip fill_index=%d ts_ms not int",
            fill_index,
        )
        return None

    # Compose idempotency_key from run_id + fill_index for de-dup on retry.
    # idempotency_key 由 run_id + fill_index 組合，retry 時去重。
    idempotency_key = f"{run_id}:{fill_index}"

    # ts (TIMESTAMPTZ) derived from ts_ms; UTC.
    # ts (TIMESTAMPTZ) 由 ts_ms 衍生，UTC。
    ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)

    # Payload: serialize the entire fill dict; truncate if oversize.
    # REF-20 Sprint B2 R5-T5: when decision_evidence is provided, inject as
    # ``_replay_decision_evidence`` sub-object so the audit chain can be
    # reconstructed without re-parsing replay_report.json. The injection
    # happens BEFORE the size check so a giant evidence object would still
    # fall back to truncation (DoS bound preserved).
    #
    # payload：序列化整個 fill dict；超過則截斷。
    # REF-20 Sprint B2 R5-T5：decision_evidence 存在時注入為
    # ``_replay_decision_evidence`` 子物件，使審計鏈不需重 parse
    # replay_report.json。注入發生於 size check 前，超大 evidence 仍會 fallback
    # 截斷（保留 DoS bound）。
    fill_with_evidence = dict(fill)
    if is_ghost_fill:
        fill_with_evidence["_replay_is_ghost_fill"] = True
        fill_with_evidence["_replay_original_qty"] = qty
        fill_with_evidence["_replay_db_qty_sentinel"] = db_qty
    if decision_evidence is not None:
        fill_with_evidence["_replay_decision_evidence"] = decision_evidence
    payload_bytes = json.dumps(
        fill_with_evidence, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")
    payload_truncated = False
    if len(payload_bytes) > MAX_PAYLOAD_BYTES:
        payload_truncated = True
        payload_obj = {
            "_truncated": True,
            "_original_size": len(payload_bytes),
            "_truncated_at": MAX_PAYLOAD_BYTES,
            "ts_ms": ts_ms,
            "symbol": fill.get("symbol"),
            "side": side,
        }
        # When truncating, still preserve the decision evidence as a top-level
        # marker (cheap; the evidence dict is bounded ~300 bytes by design).
        # 截斷時仍保留 decision evidence 為頂層標記（便宜；evidence 設計上 bound ~300 bytes）。
        if decision_evidence is not None:
            payload_obj["_replay_decision_evidence"] = decision_evidence
        if is_ghost_fill:
            payload_obj["_replay_is_ghost_fill"] = True
            payload_obj["_replay_original_qty"] = qty
            payload_obj["_replay_db_qty_sentinel"] = db_qty
    else:
        payload_obj = fill_with_evidence

    # R6-T5 (Sprint C, 2026-05-05): 從 Rust fill JSON 解析 W1 R6-T1+T2 真實
    # fee model + slippage model 寫入；fallback 到 Sprint A sentinel default
    # 當 fill 缺對應 key（synthetic walker fallback path）。
    # liquidity_role 必驗 V050 CHECK enum allowlist (maker/taker/unknown)。
    # ci_low/mid/high_bps 仍 None（cell-level CalibrationResult 由
    # run_finalize_route.py post-replay 統一 UPDATE 寫入，per QC §3.1）。

    fee_value = fill.get("fee")
    fee = float(fee_value) if isinstance(fee_value, (int, float)) else FEE_DEFAULT

    fee_rate_value = fill.get("fee_rate")
    fee_rate = (
        float(fee_rate_value)
        if isinstance(fee_rate_value, (int, float))
        else FEE_RATE_DEFAULT
    )

    liquidity_role_value = fill.get("liquidity_role")
    if liquidity_role_value in V050_ALLOWED_LIQUIDITY_ROLES:
        liquidity_role = liquidity_role_value
    else:
        if liquidity_role_value is not None:
            logger.warning(
                "map_fill_to_v050_row: fill_index=%d liquidity_role=%r 不在 V050 "
                "CHECK allowlist {maker,taker,unknown}；fallback 'unknown'",
                fill_index, liquidity_role_value,
            )
        liquidity_role = LIQUIDITY_ROLE_DEFAULT

    execution_model_version_value = fill.get("execution_model_version")
    execution_model_version = (
        str(execution_model_version_value)
        if isinstance(execution_model_version_value, str)
        and execution_model_version_value
        else EXECUTION_MODEL_VERSION_DEFAULT
    )

    # 組合 17-col + 4 default 參數 dict，對齊 V050 CREATE TABLE 順序。
    # ``sim_fill_id`` server-derived UUID (PK)。
    return {
        "sim_fill_id": uuid.uuid4().hex,
        "experiment_id": experiment_id,
        "intent_id": None,                 # V3 §6.2: replay has no live intent
        "decision_lease_id": None,         # V3 §6.2: replay does not acquire
        "idempotency_key": idempotency_key,
        "ts": ts,
        "ts_ms": ts_ms,
        "symbol": str(fill["symbol"]),
        "strategy_name": strategy_name,
        "side": side,
        "qty": db_qty,
        "price": price,
        "fee": fee,                        # R6-T5: 從 Rust JSON 解析 W1 R6-T1 fee model
        "fee_rate": fee_rate,              # R6-T5: 從 Rust JSON 解析 W1 R6-T1 fee_rate
        "liquidity_role": liquidity_role,  # R6-T5: 從 Rust JSON 解析 + V050 CHECK 驗
        "evidence_source_tier": tier,
        "execution_model_version": execution_model_version,  # R6-T5: 從 Rust JSON 解析
        "ci_low_bps": None,                # cell-level CI 由 run_finalize_route 統一 UPDATE
        "ci_mid_bps": None,
        "ci_high_bps": None,
        "payload": json.dumps(payload_obj, sort_keys=True, ensure_ascii=False),
        "_payload_truncated": payload_truncated,  # observability hint, not INSERTed
    }


# ─── Strategy lookup / strategy 查詢 ─────────────────────────────────


def lookup_strategy_name_from_v049(
    cur: Any, experiment_id: str
) -> Optional[str]:
    """SELECT manifest_jsonb->>'strategy' FROM replay.experiments WHERE id=?.
    SELECT manifest_jsonb->>'strategy' FROM replay.experiments WHERE id=?。

    Sprint A walker writes ``strategy_name`` into V050 from the V049
    manifest_jsonb. V049 has no top-level ``strategy_name`` column; the
    canonical place is ``manifest_jsonb.strategy`` (the
    ``ReplayExperimentRegisterRequest.strategy`` field after
    ``register_experiment``).

    Sprint A walker 從 V049 manifest_jsonb 取 ``strategy_name`` 寫入 V050。
    V049 無 top-level ``strategy_name`` column；正規位置在
    ``manifest_jsonb.strategy``（``ReplayExperimentRegisterRequest.strategy``
    欄位於 ``register_experiment`` 後的位置）。

    Args:
        cur: psycopg2-style cursor inside caller's transaction.
        experiment_id: V049 row's experiment_id (uuid text).

    Returns / 回傳:
        ``str`` (strategy name) on found; ``None`` else.
    """
    cur.execute(
        "SELECT manifest_jsonb->>'strategy' FROM replay.experiments "
        "WHERE experiment_id = %s::uuid LIMIT 1;",
        (experiment_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    val = row[0]
    return str(val) if val is not None else None


# ─── Bulk insert / 批量插入 ──────────────────────────────────────────


def insert_simulated_fills(
    cur: Any,
    fill_params_list: list[dict[str, Any]],
) -> int:
    """Bulk INSERT mapped fills into V050 with ON CONFLICT DO NOTHING.
    將 mapped fill 批次 INSERT 到 V050，含 ON CONFLICT DO NOTHING。

    Idempotency: V050 has UNIQUE ``(experiment_id, idempotency_key)``
    so a finalize-then-finalize-again sequence yields zero inserts on
    the second call (per the natural unique).

    幂等性：V050 ``(experiment_id, idempotency_key)`` UNIQUE，
    finalize 兩次第二次 INSERT 0 row（以 natural unique 去重）。

    Args:
        cur: psycopg2-style cursor; caller owns xact lifecycle.
        fill_params_list: list of dicts from ``map_fill_to_v050_row``.

    Returns / 回傳:
        Number of rows actually inserted (per RETURNING).
    """
    if not fill_params_list:
        return 0

    # Use parameterized INSERT (no string concat). executemany would also
    # work but we want RETURNING count — use a single INSERT with VALUES
    # tuple expansion via psycopg2 mogrify. To keep psycopg2-compat without
    # importing extras, we issue executemany then count rowcount.
    # 用參數化 INSERT（無字串拼接）。我們想要 RETURNING count — 用單條
    # INSERT + VALUES 展開（psycopg2 mogrify）。為相容無需 extras 的 psycopg2，
    # 走 executemany + rowcount。
    sql = """
        INSERT INTO replay.simulated_fills (
            sim_fill_id, experiment_id, intent_id, decision_lease_id,
            idempotency_key, ts, ts_ms, symbol, strategy_name,
            side, qty, price, fee, fee_rate, liquidity_role,
            evidence_source_tier, execution_model_version,
            ci_low_bps, ci_mid_bps, ci_high_bps, payload
        ) VALUES (
            %(sim_fill_id)s::uuid, %(experiment_id)s::uuid, %(intent_id)s,
            %(decision_lease_id)s, %(idempotency_key)s, %(ts)s, %(ts_ms)s,
            %(symbol)s, %(strategy_name)s, %(side)s, %(qty)s, %(price)s,
            %(fee)s, %(fee_rate)s, %(liquidity_role)s,
            %(evidence_source_tier)s, %(execution_model_version)s,
            %(ci_low_bps)s, %(ci_mid_bps)s, %(ci_high_bps)s,
            %(payload)s::jsonb
        )
        ON CONFLICT (experiment_id, idempotency_key) DO NOTHING;
    """

    inserted = 0
    for params in fill_params_list:
        # Strip observability-only keys before passing to psycopg2.
        # 剝除僅供觀察的 key（不傳 psycopg2）。
        clean = {k: v for k, v in params.items() if not k.startswith("_")}
        cur.execute(sql, clean)
        # rowcount on a single-row INSERT with ON CONFLICT DO NOTHING is 1
        # if INSERTed, 0 if conflict. Sum to get a true insert count.
        # ON CONFLICT DO NOTHING 單行 INSERT，rowcount=1 表示 INSERT 成功，
        # 0 表示 conflict。求和得真實 INSERT 計數。
        if cur.rowcount and cur.rowcount > 0:
            inserted += cur.rowcount

    return inserted


# ─── High-level API / 高層 API ───────────────────────────────────────


def persist_replay_report(
    cur: Any,
    report_path: Path,
    *,
    experiment_id: str,
    run_id: str,
) -> SimulatedFillsWriteResult:
    """Parse ``replay_report.json`` + INSERT all fills into V050.
    解析 ``replay_report.json`` + 將所有 fill INSERT 到 V050。

    High-level wrapper combining parse / strategy lookup / map / insert.
    Caller (``run_finalize_route``) owns the PG xact lifecycle.

    高層包裝結合 parse / strategy lookup / map / insert。
    caller（``run_finalize_route``）持 PG xact 生命周期。

    Args:
        cur: psycopg2-style cursor inside caller's transaction.
        report_path: filesystem Path to replay_report.json (caller verified
                     existence + within allowlist).
        experiment_id: V049 experiment uuid.
        run_id: V045 run uuid (used for idempotency_key composition).

    Returns / 回傳:
        ``SimulatedFillsWriteResult`` with counts. NEVER raises on
        per-fill issues (those increment ``fills_skipped`` and append to
        ``errors``). Parser-level errors propagate (caller maps to 410/500).

    Raises / 異常:
        ValueError: schema_version / result / fills missing or malformed.
        OSError: file read failure.
        json.JSONDecodeError: invalid JSON.
    """
    result = SimulatedFillsWriteResult()

    envelope = parse_replay_report_json(report_path)
    fills = envelope["result"]["fills"]  # parser guarantees list

    # Lookup strategy_name from V049 manifest_jsonb (single SELECT).
    # 從 V049 manifest_jsonb 取 strategy_name（單條 SELECT）。
    strategy_name = lookup_strategy_name_from_v049(cur, experiment_id)
    if strategy_name is None:
        # Defense-in-depth: caller should have already verified V049 row
        # exists (via run_state.manifest_id FK). Fall back to a sentinel
        # so V050 NOT NULL constraint passes.
        # 縱深防禦：caller 應已驗 V049 row 存在（透過 run_state.manifest_id
        # FK）。fallback sentinel 以滿足 V050 NOT NULL。
        strategy_name = "unknown_strategy"
        result.errors.append("strategy_name_missing_from_v049_manifest_jsonb")

    # REF-20 Sprint B2 R5-T5: build decision-trace index for per-fill match.
    # Empty index when:
    #   * synthetic walker run (no decision_traces field; #[serde(default)] in
    #     Rust side emits []).
    #   * adapter-path run with empty trace (zero ticks emitted any action).
    # Either case is non-fatal — mapping proceeds with decision_evidence=None.
    #
    # REF-20 Sprint B2 R5-T5：建立決策 trace index 供逐 fill 比對。空 index 於：
    #   * synthetic walker run（缺 decision_traces；Rust 端 #[serde(default)] 發 []）
    #   * adapter 路徑但 trace 空（無 tick 發 action）
    # 兩種情況皆 non-fatal — 比對 fail 時 decision_evidence=None。
    decision_traces = extract_decision_traces(envelope)
    decision_index = build_decision_evidence_index(decision_traces)

    # Map each fill; collect non-None param dicts.
    # 映射每筆 fill；收集非 None 參數 dict。
    mapped: list[dict[str, Any]] = []
    for idx, fill in enumerate(fills):
        if not isinstance(fill, dict):
            result.fills_skipped += 1
            result.errors.append(f"fill_index_{idx}_not_object")
            continue
        # R5-T5: greedy-match decision evidence (consumes from index).
        # R5-T5：貪婪比對 decision evidence（從 index pop）。
        decision_evidence = consume_decision_evidence_for_fill(fill, decision_index)
        params = map_fill_to_v050_row(
            fill,
            experiment_id=experiment_id,
            run_id=run_id,
            fill_index=idx,
            strategy_name=strategy_name,
            decision_evidence=decision_evidence,
        )
        if params is None:
            result.fills_skipped += 1
            continue
        if params.get("_payload_truncated"):
            result.fills_truncated += 1
        mapped.append(params)

    # Bulk INSERT.
    # 批量 INSERT。
    if mapped:
        result.fills_inserted = insert_simulated_fills(cur, mapped)

    logger.info(
        "persist_replay_report: experiment_id=%s run_id=%s "
        "fills_seen=%d inserted=%d skipped=%d truncated=%d errors=%d",
        experiment_id, run_id, len(fills), result.fills_inserted,
        result.fills_skipped, result.fills_truncated, len(result.errors),
    )

    return result


__all__ = [
    "EXECUTION_MODEL_VERSION_DEFAULT",
    "FEE_DEFAULT",
    "FEE_RATE_DEFAULT",
    "LIQUIDITY_ROLE_DEFAULT",
    "MAX_PAYLOAD_BYTES",
    "MAX_REPORT_BYTES",
    "REJECTED_FILL_QTY_SENTINEL",
    "SUPPORTED_REPORT_SCHEMA_VERSIONS",
    "SimulatedFillsWriteResult",
    "V050_ALLOWED_LIQUIDITY_ROLES",
    "V050_ALLOWED_SIDE_VALUES",
    "V050_ALLOWED_TIER_VALUES",
    # R5-T5 decision-evidence helpers
    "build_decision_evidence_index",
    "consume_decision_evidence_for_fill",
    "extract_decision_traces",
    "insert_simulated_fills",
    "lookup_strategy_name_from_v049",
    "map_fill_to_v050_row",
    "parse_replay_report_json",
    "persist_replay_report",
]
