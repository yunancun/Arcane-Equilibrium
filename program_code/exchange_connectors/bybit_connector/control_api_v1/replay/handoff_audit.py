"""REF-20 P6-S15 handoff audit emit — append-only, hash-only typed phrase.

REF-20 P6-S15 handoff audit 發射器 — append-only、hash-only typed phrase。

MODULE_NOTE (EN):
    Wave 8 R20-P6-S15 (Bounded Demo Handoff backend security trio third leg).
    Emits one row to learning.governance_audit_log per handoff attempt
    (success / failed / rejected) per DOC-08 §12 governance audit policy.

    Append-only contract / 強制不可變:
      - INSERT only; never UPDATE or DELETE existing rows.
      - V035 GRANT INSERT pattern is preserved (no schema-level GRANT
        modifications in this module).
      - Hash-only typed phrase: typed_phrase_hash = sha256_hex(phrase);
        raw phrase NEVER persisted to DB or logs.

    Wiring with V044 / 與 V044 接線:
      - V044 extends V035 event_type CHECK enum with
        'replay_handoff_request' so this audit emit succeeds
        without resorting to 'audit_write_failed' + payload-discriminator
        fallback.
      - V044 also creates replay.handoff_requests; see handoff_routes.py
        _execute_handoff() for the parallel INSERT into the registry table.
      - This module does NOT INSERT into replay.handoff_requests; that
        write is owned by handoff_routes.py inside the same transaction.

    API surface / 對外 API:
      - emit_handoff_audit(actor_id, request, result, trace_id,
                           reject_reason, cached) -> bool

    Spec source / 規格來源:
      - V3 §11 P6 Deliverables: "audit row in learning.governance_audit_log"
      - DOC-08 §12 governance_audit_log policy (append-only, INSERT-only)
      - workplan §4 Wave 8 R20-P6-S15 row (FA + E3 review-ready)

MODULE_NOTE (中):
    Wave 8 R20-P6-S15（Bounded Demo Handoff 後端安全三劍客第三件）。
    每次 handoff 嘗試（success / failed / rejected）寫一列到
    learning.governance_audit_log，per DOC-08 §12 governance audit 政策。

    強制不可變契約：
      - 僅 INSERT；不 UPDATE / DELETE 既有 row。
      - 保留 V035 GRANT INSERT pattern（不在此 module 做 schema-level
        GRANT 修改）。
      - Hash-only typed phrase：typed_phrase_hash = sha256_hex(phrase)；
        raw phrase 永不寫 DB / log。

    與 V044 接線：
      - V044 擴 V035 event_type CHECK enum 加 'replay_handoff_request'，
        本 audit emit 才不必 fallback 'audit_write_failed' +
        payload-discriminator。
      - V044 同 commit 建 replay.handoff_requests；見 handoff_routes.py
        _execute_handoff() 在同 transaction 內 INSERT 該 registry 表。
      - 本 module 不對 replay.handoff_requests 做 INSERT；那寫由
        handoff_routes.py 擁有。

    對外 API：
      - emit_handoff_audit(actor_id, request, result, trace_id,
                           reject_reason, cached) -> bool

SPEC: REF-20 V3 §11 P6 Deliverables + §12 #20 + DOC-08 §12 governance audit
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
          §4 Wave 8 R20-P6-S15
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("replay.handoff_audit")


# ─── Constants / 常數 ────────────────────────────────────────────────


# Audit event_type for V044-extended V035 CHECK enum.
# 6-value list: review_live_candidate / lease_grant / lease_auto_revoke /
# bulk_re_evaluation / audit_write_failed / replay_handoff_request.
# V044 擴 V035 後的 event_type 值。
HANDOFF_AUDIT_EVENT_TYPE = "replay_handoff_request"

# decided_by source pattern mirrors LG-5 RFC §2.3 audit emitter convention.
# decided_by source pattern 鏡像 LG-5 RFC §2.3 audit emitter 慣例。
HANDOFF_AUDIT_DECIDED_BY_TEMPLATE = "replay_handoff.{actor_id}"


# ─── Data class / 資料類 ─────────────────────────────────────────────


@dataclass(slots=True)
class HandoffAuditRequest:
    """Subset of HandoffRequest fields needed for audit emit.
    Audit emit 所需的 HandoffRequest 子集。

    The handoff_routes.py builds this from the FastAPI Pydantic
    HandoffRequest. Decoupling the audit module from the routes module
    avoids a circular import while preserving the field contract.

    handoff_routes.py 從 FastAPI Pydantic HandoffRequest 構造此物件；
    audit module 與 routes module 解耦避免 circular import 同時保留欄位契約。
    """

    experiment_id: str
    manifest_id: str
    typed_phrase: str  # raw phrase; hashed BEFORE INSERT, never stored raw
    idempotency_key: str
    operator_notes: Optional[str] = None


# ─── Hash helper / Hash 工具 ─────────────────────────────────────────


def hash_typed_phrase(phrase: str) -> str:
    """Compute SHA-256 hex digest of typed phrase.
    計算 typed phrase 的 SHA-256 hex digest。

    Security contract:
      1. Raw phrase MUST be hashed BEFORE any persistence layer (DB or log).
      2. Audit row stores typed_phrase_hash NOT raw phrase.
      3. The phrase format is 'HANDOFF <experiment_id>'; phrase is low-
         entropy by design (operator types it manually) so plain-text
         storage offers no replay-attack defense — hash is the only
         persisted form.

    安全契約：
      1. raw phrase 必在持久層（DB / log）之前 hash。
      2. audit row 存 typed_phrase_hash 非 raw phrase。
      3. phrase 格式 'HANDOFF <experiment_id>'；operator 手打的低熵設計，
         明文存無重放攻擊防禦 — hash 是唯一持久化形態。
    """
    return hashlib.sha256(phrase.encode("utf-8")).hexdigest()


# ─── Audit emit / Audit 發射 ─────────────────────────────────────────


def emit_handoff_audit(
    *,
    actor_id: str,
    request: HandoffAuditRequest,
    result: str,
    trace_id: str,
    reject_reason: Optional[str] = None,
    cached: bool = False,
    cursor: Optional[Any] = None,
) -> bool:
    """Emit one audit row to learning.governance_audit_log.
    寫一列 audit row 到 learning.governance_audit_log。

    Append-only contract per DOC-08 §12: INSERT only; never UPDATE / DELETE.
    The cursor parameter is required so the caller (handoff_routes.py
    _execute_handoff()) can include this audit row in the SAME transaction
    as the replay.handoff_requests INSERT — atomic write or atomic rollback.

    DOC-08 §12 append-only：僅 INSERT；不 UPDATE / DELETE。cursor 參數必填，
    讓呼叫端（handoff_routes.py _execute_handoff()）把本 audit row 包進與
    replay.handoff_requests INSERT 的同一 transaction — 原子寫或原子 rollback。

    Args / 參數:
        actor_id: Authenticated actor; goes into payload + decided_by.
        request: HandoffAuditRequest with experiment_id, manifest_id,
                 typed_phrase, idempotency_key, operator_notes.
        result: 'success' / 'failed' / 'rejected'.
        trace_id: UUID + ts prefix; surfaces in payload for cross-table
                  correlation with replay.handoff_requests.trace_id.
        reject_reason: NULL unless result='rejected'; 5-value allowlist
                       enforced by replay.handoff_requests CHECK.
        cached: TRUE on idempotency hit; surfaces in payload.
        cursor: psycopg2 cursor (REQUIRED). Caller already opened a
                transaction; we INSERT under that cursor without committing
                so caller controls atomicity.

    Returns / 回傳:
        True on INSERT success; False on exception (caller decides whether
        to rollback the parent transaction or continue).

    Raises / 例外:
        ValueError if cursor is None (programmer error; defensive guard).
    """
    if cursor is None:
        raise ValueError(
            "emit_handoff_audit requires cursor for transactional atomicity"
        )

    # Hash typed phrase BEFORE persistence (security: raw phrase never stored).
    # 在持久化之前 hash typed phrase（安全：raw phrase 永不存）。
    phrase_hash = hash_typed_phrase(request.typed_phrase)

    # Build payload JSONB (forward-compat replay; V035 column has no
    # dedicated handoff fields, so all handoff-specific data lives in
    # payload sub-keys per V035 design pattern).
    # 構造 payload JSONB（前向相容；V035 column 無 handoff 專欄，全部
    # handoff 專屬資料走 payload sub-key per V035 設計）。
    payload = {
        "trace_id": trace_id,
        "experiment_id": request.experiment_id,
        "manifest_id": request.manifest_id,
        "idempotency_key": request.idempotency_key,
        "typed_phrase_hash": phrase_hash,
        "operator_notes": request.operator_notes,
        "result": result,
        "cached": cached,
        "reject_reason": reject_reason,
        "actor_id": actor_id,
        "ts_iso": datetime.now(timezone.utc).isoformat(),
        "audit_module_version": "P6-S15-v1",
    }

    decided_by = HANDOFF_AUDIT_DECIDED_BY_TEMPLATE.format(actor_id=actor_id)

    try:
        cursor.execute(
            """
            INSERT INTO learning.governance_audit_log (
                event_type, candidate_id, decision_lease_id,
                verdict_decision, verdict_reason, rule_failures,
                expected_net_bps_demo, expected_net_bps_live_adjusted,
                expected_net_bps_deflated,
                cost_regime_ratio, cost_regime_ratio_clamped,
                psr_value, psr_n_samples, psr_skew, psr_kurt,
                sr_0_deflation, v_pending_net_bps,
                lease_ttl_ms, lease_revoke_triggers,
                decided_by, payload
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s::jsonb
            )
            """,
            (
                HANDOFF_AUDIT_EVENT_TYPE,
                None,  # candidate_id NULL — handoff is not tied to a
                       # learning.mlde_param_applications row.
                None,  # decision_lease_id NULL — handoff is operator
                       # workflow, not Decision Lease acquisition.
                None,  # verdict_decision NULL — not a review_live_candidate.
                None,  # verdict_reason NULL.
                [],    # rule_failures empty list.
                None, None,    # expected_net_bps_demo / _live_adjusted NULL
                None,          # expected_net_bps_deflated NULL
                None, None,    # cost_regime_ratio / _clamped NULL
                None, None, None, None,  # psr_* NULL
                None, None,    # sr_0_deflation / v_pending_net_bps NULL
                None,          # lease_ttl_ms NULL
                [],            # lease_revoke_triggers empty list
                decided_by,
                json.dumps(payload, default=str, sort_keys=True),
            ),
        )
        logger.info(
            "handoff_audit emit: actor_id=%s result=%s trace_id=%s cached=%s",
            actor_id, result, trace_id, cached,
        )
        return True
    except Exception as exc:  # noqa: BLE001 — fail-closed per DOC-08 §12
        # Caller decides rollback vs continue based on return value.
        # Do NOT log raw phrase even in exception messages.
        # 由 caller 決定 rollback 或續跑；不在例外訊息 log raw phrase。
        logger.warning(
            "handoff_audit emit failed: actor_id=%s result=%s trace_id=%s err=%s",
            actor_id, result, trace_id, exc,
        )
        return False


# ─── Module export / 模組匯出 ────────────────────────────────────────


__all__ = [
    "HANDOFF_AUDIT_EVENT_TYPE",
    "HANDOFF_AUDIT_DECIDED_BY_TEMPLATE",
    "HandoffAuditRequest",
    "emit_handoff_audit",
    "hash_typed_phrase",
]
