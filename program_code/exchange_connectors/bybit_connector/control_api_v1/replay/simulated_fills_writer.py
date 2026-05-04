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
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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


# ─── Row mapper / 列映射器 ───────────────────────────────────────────


def map_fill_to_v050_row(
    fill: dict[str, Any],
    *,
    experiment_id: str,
    run_id: str,
    fill_index: int,
    strategy_name: str,
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

    if qty <= 0.0 or price <= 0.0:
        logger.warning(
            "map_fill_to_v050_row: skip fill_index=%d qty=%s price=%s "
            "(V050 CHECK qty>0 AND price>0)", fill_index, qty, price,
        )
        return None

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
    # payload：序列化整個 fill dict；超過則截斷。
    payload_bytes = json.dumps(fill, sort_keys=True, ensure_ascii=False).encode("utf-8")
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
    else:
        payload_obj = fill

    # Compose 17-col + 4-col-default param dict aligned to V050 CREATE TABLE
    # column order. ``sim_fill_id`` server-derived UUID (PK).
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
        "qty": qty,
        "price": price,
        "fee": FEE_DEFAULT,                # Sprint A no fee model
        "fee_rate": FEE_RATE_DEFAULT,      # Sprint A no fee model
        "liquidity_role": LIQUIDITY_ROLE_DEFAULT,
        "evidence_source_tier": tier,
        "execution_model_version": EXECUTION_MODEL_VERSION_DEFAULT,
        "ci_low_bps": None,                # Sprint A no per-fill CI
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

    # Map each fill; collect non-None param dicts.
    # 映射每筆 fill；收集非 None 參數 dict。
    mapped: list[dict[str, Any]] = []
    for idx, fill in enumerate(fills):
        if not isinstance(fill, dict):
            result.fills_skipped += 1
            result.errors.append(f"fill_index_{idx}_not_object")
            continue
        params = map_fill_to_v050_row(
            fill,
            experiment_id=experiment_id,
            run_id=run_id,
            fill_index=idx,
            strategy_name=strategy_name,
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
    "SUPPORTED_REPORT_SCHEMA_VERSIONS",
    "SimulatedFillsWriteResult",
    "V050_ALLOWED_LIQUIDITY_ROLES",
    "V050_ALLOWED_SIDE_VALUES",
    "V050_ALLOWED_TIER_VALUES",
    "insert_simulated_fills",
    "lookup_strategy_name_from_v049",
    "map_fill_to_v050_row",
    "parse_replay_report_json",
    "persist_replay_report",
]
