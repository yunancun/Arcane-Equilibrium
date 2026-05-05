"""REF-20 Sprint C2 R7 W1 — replay metadata 統一 helper。

模組目的：
    為 R7 升級 4 個 producer（dream_engine / opportunity_tracker /
    mlde_shadow_advisor / 未來 LinUCB warm-start）寫入
    ``learning.verify_replay_evidence_and_insert`` (V036) 時，提供
    從 R6 ``CalibrationResult`` + ``replay.experiments`` SELECT
    manifest_hash 到構造 4-tuple replay metadata 的統一接口。

    本 helper **不**做 INSERT，僅構造 4-tuple；caller 自行傳入 V036。
    避免 4 個 producer 各自重複 V049 SELECT 邏輯 + TTL 計算邏輯。

    關鍵設計：
      1. 接受 caller 傳入既開的 cursor（同 transaction 內 SELECT，
         避免跨 connection 資料一致性問題）。
      2. 接受 caller 傳入 R6 ``CalibrationResult`` 而非自己 derive
         （derive 是 caller 上游 R6 W6 chain 的 responsibility）。
      3. label=NONE 時回 None；caller 必 skip insert（V036 拒絕 NONE
         tier）。
      4. V049 row 缺失（experiment_id 不存在 / manifest_hash NULL）→
         log warn + 回 None；caller 視為 advisory failure。
      5. 0 raise（除明顯 type error 由 caller psycopg2 拋出）。

    與 ``experiment_registry.lookup_replay_config_blob`` 區別：
      - lookup_replay_config_blob 取 manifest_jsonb 內 strategy_params /
        risk_overrides 兩 blob（Sprint B2 R5-T6 用）。
      - 本 helper 取 manifest_hash + 確認 experiment_id 存在（R7 用）。

Forbidden surface 審計（V3 §6.2 必綠）：
    - 0 引用 paper_state / canary_writer / database / ipc_server /
      governance_hub / live_authorization / decision_lease。
    - 純 computation + 1 SQL SELECT；無 mutation；caller 不需 commit。

SPEC: REF-20 V3 §3 G7/G8 + V049 (replay_experiments) + V051
      (mlde_recommendations_replay_columns paired CHECK) + V055
      (verify_replay_evidence_and_insert function body) + Sprint C2 R7
      dispatch §1.1 + AI-E advisory §3.1/§3.2.
Cross reference:
  - rust/openclaw_engine/src/replay/calibration_label.rs
  - replay/calibration_label.py（Python port，Sprint C R6 W6 commit `29d41991`）

R7-T4 (Sprint C2 W1, 2026-05-05): LinUCB NO-OP confirmation
    AI-E §7 grep verified: linucb_trainer.py / linucb_arm_migration.py /
    linucb_shadow_compare.py / learning_routes_linucb.py — 0 hit on
    verify_replay_evidence_and_insert. LinUCB 0 producer wired into V036
    verified function path. R7 dispatch NO-OP.
    Future-proofing (per memory/linucb_shadow_compare_retention.md): if
    Sprint D/E LinUCB warm-start adds verify_replay caller, must align
    with calibrated_replay pattern (not hardcoded 'real_outcome'); 直接
    reuse 本 helper。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

try:  # pragma: no cover - import guard
    import psycopg2  # type: ignore
except ImportError:  # pragma: no cover - runtime DB path only
    psycopg2 = None  # type: ignore[assignment]

# 從 R6 W6 Python port 取 enum + dataclass（不再依 Rust 路徑）
from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.calibration_label import (
    CalibrationResult,
    ExecutionConfidence,
)


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# 公開 API
# ─────────────────────────────────────────────────────────────────────


def build_replay_metadata(
    *,
    experiment_id: str,
    calibration_result: CalibrationResult,
    cur: Any,
) -> Optional[Tuple[str, str, str, datetime]]:
    """從 R6 ``CalibrationResult`` + V049 row 構造 4-tuple replay metadata。

    本 helper 是 R7 4 個 producer (dream / opportunity / mlde_shadow /
    LinUCB future) 升級 calibrated_replay tier 時的共用 metadata 構造器。
    Caller 取本 helper 結果作為 V036 verify_replay_evidence_and_insert 的
    4 個 metadata arg：``p_evidence_source_tier`` / ``p_replay_experiment_id``
    / ``p_manifest_hash`` / ``p_expires_at``。

    決策樹：
      1. ``calibration_result.label == NONE`` → 回 None；caller 必 skip
         INSERT（V036 拒絕 NONE tier 寫入；強制 caller fail-fast）。
      2. ``calibration_result.label ∈ {LIMITED, CALIBRATED}`` →
         a. SELECT V049 row（experiment_id + manifest_hash）；
         b. row 不存在 / manifest_hash NULL → log warn + 回 None
            （advisory failure，caller 應降級為 'real_outcome' fallback
             或直接 skip）；
         c. 否則構造 4-tuple，回傳。
      3. ``ttl`` 直接從 ``CalibrationResult.ttl`` 取（R6 已決定 7d/3d）；
         caller 不需要再 map label → ttl。

    LIMITED 與 CALIBRATED 兩種 label 都寫 ``evidence_source_tier=
    'calibrated_replay'`` (per V051 paired CHECK + AI-E advisory §3.2)；
    區別在 TTL（7d vs 3d）由 ``CalibrationResult.ttl`` 直接帶。

    Args:
        experiment_id: V049 row 的 experiment_id (UUID text)。
        calibration_result: R6 ``derive_execution_confidence`` 結果，
            含 label（3-variant enum）+ ttl (timedelta)。Caller 上游
            從 finalize chain 拿，在 W6 commit `29d41991` 後可從
            run_finalize 結果或 V049 row 推導。
        cur: psycopg2-style cursor。Caller 提供同 transaction 的 cursor
            使本 SELECT 與後續 V036 INSERT 在同一 xact，避免 row 出現
            race（V049 row 已 land 必然存在，但同 xact 仍是好習慣）。

    Returns:
        - ``None`` if ``calibration_result.label == NONE`` (caller skip).
        - ``None`` if V049 row 不存在或 manifest_hash NULL (advisory
          failure；log warn 已 emit)。
        - ``(tier, replay_experiment_id, manifest_hash_hex, expires_at)``
          tuple if Calibrated/Limited:
          - tier: 'calibrated_replay'（兩種 label 共用）。
          - replay_experiment_id: 與 ``experiment_id`` 相同（str pass-through）。
          - manifest_hash_hex: BYTEA hex digest（V055 V036 接收 hex
             string，內部 decode(...,'hex')）。
          - expires_at: ``datetime.now(UTC) + calibration_result.ttl``。

    Fail-soft semantic: 任何 SQL exception 由 caller catch（本 helper 預
    期 cur.execute SELECT 不致 raise；若真 raise，caller psycopg2 path 會
    在 outer try/except 內 fail-soft）。

    Forbidden surface: 0 INSERT / 0 UPDATE；只 SELECT 1 row。
    """
    # Step 1：label NONE 短路
    if calibration_result.label == ExecutionConfidence.NONE:
        return None

    # Step 2：SELECT V049 manifest_hash（BYTEA → hex string for V036）
    cur.execute(
        """
        SELECT manifest_hash
          FROM replay.experiments
         WHERE experiment_id = %s::uuid
         LIMIT 1;
        """,
        (str(experiment_id),),
    )
    row = cur.fetchone()
    if row is None:
        logger.warning(
            "build_replay_metadata: experiment_id=%s 不在 V049（advisory "
            "skip；caller 應 skip INSERT 或 fallback real_outcome）",
            experiment_id,
        )
        return None

    manifest_hash_bytes = row[0]
    if manifest_hash_bytes is None:
        logger.warning(
            "build_replay_metadata: experiment_id=%s manifest_hash NULL "
            "(V049 NOT NULL invariant violation? 視為 advisory failure)",
            experiment_id,
        )
        return None

    # psycopg2 BYTEA 在 Python 層為 memoryview / bytes；都接受 .hex() 但
    # memoryview 在較舊 Python 版本沒有 .hex()，先 bytes() 再 .hex() 防禦。
    try:
        manifest_hash_hex = bytes(manifest_hash_bytes).hex()
    except (TypeError, ValueError) as exc:
        logger.warning(
            "build_replay_metadata: experiment_id=%s manifest_hash 無法 "
            "hex 編碼 (%s) — advisory failure",
            experiment_id, exc,
        )
        return None

    # Step 3：構造 metadata 4-tuple
    # tier 兩種 label 共用 'calibrated_replay'（V051 paired CHECK enum）；
    # ttl 區分由 CalibrationResult.ttl 帶（calibrated→7d / limited→3d）。
    tier = "calibrated_replay"
    expires_at = datetime.now(timezone.utc) + calibration_result.ttl

    return (tier, str(experiment_id), manifest_hash_hex, expires_at)


__all__ = ["build_replay_metadata"]
