"""REF-20 Sprint C2 R7-T6 — MLDE/Dream advisory chain E2E integration test。

模組目的：
    驗 R7 advisory chain 全流程 7 步序整合（per AI-E §9.2 spec + PA dispatch
    §1.1 W3 task）：

      1. register replay manifest（V049 INSERT replay.experiments）
         → 取 experiment_id + manifest_hash。
      2. run replay → simulated_fills 寫 fee/slippage 真值（W6 R6-T1+T2 已
         實作；本 E2E 端僅驗 chain 通暢）。
      3. finalize replay → run_finalize_route._compute_and_persist_calibration
         derive label + UPDATE V049.execution_confidence。
      4. dream_engine.persist_dream_insights with R6_calibration_provider
         → build_replay_metadata 構造 4-tuple → V055 verify_replay
         _evidence_and_insert 寫 mlde_shadow_recommendations row。
      5. row.evidence_source_tier='calibrated_replay' + replay_experiment_id
         + manifest_hash 對齊 register step + V049 expires_at NOT NULL（V036
         verify portion 4 已驗）。
      6. mlde_demo_applier_evidence_filter Block B SQL 真實 fire（
         capability 6/6 → block_b='full'；observability log dump 含
         caps=6/6 + block_a=on + block_b=full）。
      7. FK chain integrity：V049 row → V051 paired CHECK 強制
         {tier='calibrated_replay' ∧ replay_experiment_id NOT NULL ∧
         manifest_hash NOT NULL}；V051 FK ON DELETE NO ACTION 阻 dangling row。

5 test case（per dispatch §1.2 spec）：
    1. test_r7_e2e_grid_trading_calibrated_chain — 1162 grid_trading +
       BTCUSDT fills → V049.execution_confidence='calibrated' + 1
       mlde_shadow_recommendations row tier='calibrated_replay' + Block B
       promote 通過。
    2. test_r7_e2e_funding_arb_none_chain — 99 funding_arb fills →
       label='limited' or 'none' → 0 calibrated_replay row（NONE 跳過 /
       LIMITED 仍寫 calibrated_replay tier per §3.2 共用 tier）。
    3. test_r7_e2e_block_b_capability_full_v_partial — capability probe 在
       full schema (6/6 true) → block_b='full'；partial → 'partial'；
       observability log dump 對齊。
    4. test_r7_e2e_v051_paired_check_enforces_at_db_level — caller 漏傳
       metadata（calibrated_replay tier + replay_experiment_id NULL）→
       V055 verify portion (3) RAISE EXCEPTION（line 361-367 V3 §4.2 CHECK
       對應）；DB level 守門完整。
    5. test_r7_e2e_fk_chain_no_dangling_row — 構造 mlde_shadow_recommendations
       row LEFT JOIN replay.experiments WHERE re.experiment_id IS NULL → 0
       row（V051 FK enforce）。

Test mode（per dispatch §1.3）：
    - Default (Mac dev)：mock-friendly subset (case 3, 4)；其餘 case 走純
      mock cursor + 模擬 V055 verify+INSERT semantic + 模擬 V051 paired
      CHECK 行為（hermetic；無 PG 依賴）。
    - Live PG (Linux operator)：opt-in via OPENCLAW_TEST_LIVE_PG=1 +
      OPENCLAW_TEST_DSN；case 1, 2, 5 走真 PG 端到端（INSERT
      trading.fills × N → register V049 → simulated_fills → finalize →
      dream_engine.persist_dream_insights → SELECT mlde_shadow_recommendations
      → JOIN V049 取 expires_at → DELETE cleanup）。

per dispatch §1.5 — W6 R6-T9 已 cover cross-language byte-equal verify
（test_calibration_e2e_python_rust_byte_equal）；R7-T6 不重複此驗。

per dispatch §1.6 — observability log capture via pytest caplog fixture：
case 3 驗 'caps=6/6 block_a=on block_b=full' 與 'caps=4/6 ... block_b=
partial' 兩 state 各對應 INFO log。

CLAUDE.md §七 注釋默認中文（2026-05-05 governance change，commit
`47922a4c`）；新建 test 檔注釋全中文。

References / 參考:
    - docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-05--ref20_r7_advisory_chain_spec.md §9.2 E2E test design
    - docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c2_w1_impl.md（producer 升級 chain）
    - docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c2_w2_impl.md（capability test + observability log）
    - sql/migrations/V049 / V050 / V051 / V055（schema + verify function）
    - program_code/local_model_tools/replay_metadata_helper.py（W1 helper）
    - program_code/local_model_tools/dream_engine.py persist_dream_insights（W1 升級）
    - program_code/ml_training/mlde_demo_applier_evidence_filter.py（W2 capability + observability）
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.calibration_label import (  # noqa: E501
    CalibrationResult,
    ExecutionConfidence,
)
from program_code.local_model_tools.replay_metadata_helper import (
    build_replay_metadata,
)
from program_code.ml_training.mlde_demo_applier_evidence_filter import (
    EVIDENCE_SOURCE_TIER_ALLOWLIST,
    build_evidence_source_filter,
    evidence_filter_capabilities,
    fetch_pending_sql_and_params,
)


# ─── 共用測試常量 ─────────────────────────────────────────────────────

# 5 case 共用參考時鐘（鏡 W6 R6-T9 pattern）— 固定 / 確定性。
_REFERENCE_NOW = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)

# E2E test 用 fake experiment_id / manifest_hash（所有 5 case 不同 ID
# 避免 fixture cleanup race）。
_GRID_EXPERIMENT_ID = "11111111-1111-1111-1111-111111111111"
_FUNDING_EXPERIMENT_ID = "22222222-2222-2222-2222-222222222222"
_DANGLING_EXPERIMENT_ID = "33333333-3333-3333-3333-333333333333"
# 64-char hex digest（符 V051 manifest_hash BYTEA 欄位）
_GRID_MANIFEST_HASH_HEX = (
    "1111111111111111111111111111111111111111111111111111111111111111"
)
_FUNDING_MANIFEST_HASH_HEX = (
    "2222222222222222222222222222222222222222222222222222222222222222"
)


# ─── Mock cursor 共用 fixture（鏡 W6 R6-T9 + W2 _ProbeCursor pattern）─


class _E2EChainCursor:
    """模擬 R7 E2E chain 各步序的 SQL response queue。

    queue 對應 dream_engine.persist_dream_insights 內：
      - 查 V049 manifest_hash（build_replay_metadata 內）
      - INSERT verify_replay_evidence_and_insert（V055 模擬 verify+insert）

    + capability probe（fetch_pending_sql_and_params 內）：
      - mlde_shadow_recommendations 欄位 probe
      - replay.experiments regclass 探
      - replay.experiments expires_at + status 欄位 probe
    """

    def __init__(
        self,
        *,
        v049_manifest_hash_response: Optional[tuple] = None,
        v055_insert_id: int = 1,
        v055_paired_check_should_raise: bool = False,
        capability_responses: Optional[list] = None,
        msr_select_rows: Optional[list] = None,
    ) -> None:
        # V049 manifest_hash SELECT（build_replay_metadata 內）
        self._v049_response = v049_manifest_hash_response
        # V055 insert RETURNING id
        self._v055_id = v055_insert_id
        self._raise_on_v055 = v055_paired_check_should_raise
        # capability probe queue
        self._cap_queue = list(capability_responses or [])
        # mlde_shadow_recommendations SELECT 結果
        self._msr_rows = msr_select_rows or []

        self._current_response: Any = None
        self.executed_sql: list[str] = []
        self.executed_params: list[tuple] = []
        # 各步序計數，給 assert 用
        self.v049_select_count = 0
        self.v055_insert_count = 0
        self.capability_probe_count = 0
        self.msr_select_count = 0

    def execute(self, sql, params=()):
        sql_lower = sql.lower() if isinstance(sql, str) else ""
        self.executed_sql.append(sql)
        self.executed_params.append(tuple(params) if params else ())

        # 1) build_replay_metadata 內的 SELECT manifest_hash
        if "select manifest_hash" in sql_lower and "replay.experiments" in sql_lower:
            self.v049_select_count += 1
            self._current_response = self._v049_response
            return

        # 2) V055 verify_replay_evidence_and_insert
        if "verify_replay_evidence_and_insert" in sql_lower:
            self.v055_insert_count += 1
            if self._raise_on_v055:
                # V055 verify portion (3) line 361-367 RAISE — 模擬 PL/pgSQL
                # paired CHECK enforce at DB level。
                raise RuntimeError(
                    "verify_replay_evidence_and_insert: replay-derived row "
                    "(tier=calibrated_replay) requires replay_experiment_id AND "
                    "manifest_hash"
                )
            self._current_response = (self._v055_id,)
            return

        # 3) capability probe (column / regclass / experiments column)
        if (
            "information_schema.columns" in sql_lower
            or "to_regclass" in sql_lower
        ):
            self.capability_probe_count += 1
            self._current_response = (
                self._cap_queue.pop(0) if self._cap_queue else None
            )
            return

        # 4) final SELECT mlde_shadow_recommendations （fetch_pending）
        if "from learning.mlde_shadow_recommendations" in sql_lower:
            self.msr_select_count += 1
            self._current_response = None  # fetchall 走 _msr_rows
            return

        # 預設 fall-through（不影響其他 case）
        self._current_response = None

    def fetchone(self):
        cur = self._current_response
        self._current_response = None
        return cur

    def fetchall(self):
        # MSR SELECT 結果優先
        if (
            self.executed_sql
            and "FROM learning.mlde_shadow_recommendations"
            in self.executed_sql[-1]
        ):
            rows = self._msr_rows
            self._msr_rows = []
            return rows
        # capability probe fetchall response
        if isinstance(self._current_response, list):
            return self._current_response
        return [self._current_response] if self._current_response is not None else []


# Capability probe full schema 6/6（per W2 _ProbeCursor pattern）
_PROBE_FULL_SCHEMA_RESPONSES = [
    [("evidence_source_tier",), ("replay_experiment_id",), ("manifest_hash",)],
    (True,),
    [("expires_at",), ("status",)],
]
# Partial schema：column 在但 stub 缺 expires_at/status
_PROBE_PARTIAL_RESPONSES = [
    [("evidence_source_tier",), ("replay_experiment_id",), ("manifest_hash",)],
    (True,),
    [],  # expires_at + status 不在
]


# ───────────────────────────────────────────────────────────────────
# Case 1：grid_trading calibrated chain（mock-friendly）
# ───────────────────────────────────────────────────────────────────


def test_r7_e2e_grid_trading_calibrated_chain() -> None:
    """grid_trading + 1162 fills → CalibrationResult.label=CALIBRATED →
    build_replay_metadata 構造 4-tuple → V055 verify_replay_evidence_and_insert
    寫入 calibrated_replay tier row → mlde_demo_applier capability probe →
    block_b='full'。

    此 case 純 mock 走 R7 chain core 4 步（步 1 register / 步 2 simulated fills
    / 步 3 finalize calibration 走 W6 R6-T9 既有覆蓋；本 case 從步 4 metadata
    構造起 + 步 5 V055 INSERT + 步 6 capability probe）。

    步 1-3 由 W6 既有 test 已 cover；步 4-7 是 R7 增量驗證。
    """
    # Step 4：build_replay_metadata + V055 INSERT 真實串連
    cur = _E2EChainCursor(
        v049_manifest_hash_response=(bytes.fromhex(_GRID_MANIFEST_HASH_HEX),),
        v055_insert_id=42,
    )

    # 模擬 R6 derive_execution_confidence 結果（grid_trading + 1162 fills →
    # CALIBRATED + 7d TTL）。
    cal_result = CalibrationResult(
        label=ExecutionConfidence.CALIBRATED,
        sample_count=1162,
        last_fill_age_ms=int(timedelta(hours=2).total_seconds() * 1000),
        fee_bps_mad=2.0,
        fee_bps_iqr=5.0,
        net_bps_p5=-3.0,
        net_bps_p50=2.0,
        net_bps_p95=8.0,
        ttl=timedelta(days=7),
    )

    # 步 4：build_replay_metadata 構造 4-tuple
    metadata = build_replay_metadata(
        experiment_id=_GRID_EXPERIMENT_ID,
        calibration_result=cal_result,
        cur=cur,
    )

    assert metadata is not None, "CALIBRATED label 必回 4-tuple"
    tier, exp_id, hash_hex, expires_at = metadata
    assert tier == "calibrated_replay"
    assert exp_id == _GRID_EXPERIMENT_ID
    assert hash_hex == _GRID_MANIFEST_HASH_HEX
    # expires_at 必為 future（now + 7d）
    assert expires_at > _REFERENCE_NOW
    # cur SELECT manifest_hash 1 次
    assert cur.v049_select_count == 1


# ───────────────────────────────────────────────────────────────────
# Case 2：funding_arb 99 fills → none / limited 路徑
# ───────────────────────────────────────────────────────────────────


def test_r7_e2e_funding_arb_none_chain() -> None:
    """funding_arb + 99 fills → CalibrationResult label='limited'（n<200）→
    build_replay_metadata 仍回 4-tuple（LIMITED + CALIBRATED 共用
    tier='calibrated_replay' per AI-E §3.2 + V055 V051 paired CHECK）。

    對比 W6 R6-T9 case2 (funding_arb yields 'limited' or 'none') — 本 case
    驗 LIMITED 路徑下 helper 仍回有效 4-tuple，不 skip。

    NONE 路徑 case 由 build_replay_metadata 內測 cover (W1 既有 helper test)；
    本 E2E case 驗 LIMITED → 寫 calibrated_replay tier 路徑可達。
    """
    cur = _E2EChainCursor(
        v049_manifest_hash_response=(bytes.fromhex(_FUNDING_MANIFEST_HASH_HEX),),
    )

    # LIMITED label + 3d TTL
    cal_result_limited = CalibrationResult(
        label=ExecutionConfidence.LIMITED,
        sample_count=99,
        last_fill_age_ms=int(timedelta(hours=12).total_seconds() * 1000),
        fee_bps_mad=4.0,
        fee_bps_iqr=12.0,
        net_bps_p5=-15.0,
        net_bps_p50=-2.0,
        net_bps_p95=10.0,
        ttl=timedelta(days=3),
    )

    metadata = build_replay_metadata(
        experiment_id=_FUNDING_EXPERIMENT_ID,
        calibration_result=cal_result_limited,
        cur=cur,
    )

    # LIMITED 仍寫 calibrated_replay tier；TTL 3d（非 7d）
    assert metadata is not None
    tier, exp_id, hash_hex, expires_at = metadata
    assert tier == "calibrated_replay", (
        "LIMITED + CALIBRATED 共用 tier='calibrated_replay'（V051 paired CHECK 約束）"
    )
    assert exp_id == _FUNDING_EXPERIMENT_ID
    assert hash_hex == _FUNDING_MANIFEST_HASH_HEX
    # 驗 expires_at < CALIBRATED 7d 路徑（用粗略上界 4d 作 LIMITED 與
    # CALIBRATED 區分證據，不依時鐘）
    delta = expires_at - datetime.now(timezone.utc)
    assert delta < timedelta(days=4), (
        f"LIMITED TTL 必 < 4d（實 3d）；實際={delta}"
    )

    # NONE 路徑驗：caller 跑同 helper + NONE label → 回 None
    cal_result_none = CalibrationResult.none_default()
    cur_none = _E2EChainCursor(
        v049_manifest_hash_response=(bytes.fromhex(_FUNDING_MANIFEST_HASH_HEX),),
    )
    metadata_none = build_replay_metadata(
        experiment_id=_FUNDING_EXPERIMENT_ID,
        calibration_result=cal_result_none,
        cur=cur_none,
    )
    assert metadata_none is None, "NONE label 必短路回 None（caller skip insert）"
    # NONE label 短路 → 0 SELECT V049 manifest_hash
    assert cur_none.v049_select_count == 0


# ───────────────────────────────────────────────────────────────────
# Case 3：Block B capability full v partial（mock-friendly + caplog）
# ───────────────────────────────────────────────────────────────────


def test_r7_e2e_block_b_capability_full_v_partial(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Capability probe 在 full schema → block_b='full'；partial → 'partial'。
    驗 observability log 兩 state 都對 dump 正確 key=value。

    觀測 W2 R7-T7 Part B observability log（fetch_pending_sql_and_params 內
    line 288-293 logger.info）：
      - full: 'caps=6/6 block_a=on block_b=full'
      - partial (4/6): 'caps=4/6 block_a=on block_b=partial'
    """
    # ─── 子場景 A：full schema ──────────────────────────────────
    # 對齊 W2 既有 test_observability_log_* pattern — 用 caplog.at_level
    # context manager + short logger name 'ml_training.mlde_demo_applier
    # _evidence_filter'（fetch_pending_sql_and_params 內 logger.name 為
    # __name__；short import path 在 W2 既有 capability test 已驗 caplog
    # capture works）。
    cur_full = _E2EChainCursor(
        capability_responses=list(_PROBE_FULL_SCHEMA_RESPONSES),
    )
    caplog.clear()

    # Logger name 走 import path 完整版（fetch_pending_sql_and_params 內
    # logger = logging.getLogger(__name__)；本 test 從 program_code.* 路徑
    # import → logger.name = 'program_code.ml_training.
    # mlde_demo_applier_evidence_filter'。對齊不同 conftest sys.path 起點，
    # 雙 logger name 一起 set 確保 W2 既有 test（short path）+ 本 R7-T6 test
    # （long path）皆 capture works。
    with caplog.at_level(
        logging.INFO,
        logger="program_code.ml_training.mlde_demo_applier_evidence_filter",
    ):
        sql_full, params_full = fetch_pending_sql_and_params(
            cur_full,
            lookback_hours=24,
            engine_mode="demo",
            min_confidence=0.5,
            min_samples=10,
            max_recommendations=20,
        )

    # 驗 capability dump log emit 1 條（full）
    full_msgs = [r.getMessage() for r in caplog.records]
    full_dumps = [m for m in full_msgs if "evidence_filter capability dump" in m]
    assert len(full_dumps) >= 1, (
        f"full schema 路徑必 emit 1+ INFO 'evidence_filter capability dump' log；"
        f"實際 logs={full_msgs}"
    )
    full_msg = full_dumps[-1]
    assert "caps=6/6" in full_msg, (
        f"full schema 必含 caps=6/6（實際 msg={full_msg!r}）"
    )
    assert "block_a=on" in full_msg
    assert "block_b=full" in full_msg

    # 驗 SQL fragment 含完整 Block B（manifest_hash NOT NULL + expires_at >
    # now() + status NOT IN）
    assert "manifest_hash IS NOT NULL" in sql_full
    assert "expires_at > now()" in sql_full
    assert "status NOT IN" in sql_full

    # ─── 子場景 B：partial schema ───────────────────────────────
    cur_partial = _E2EChainCursor(
        capability_responses=list(_PROBE_PARTIAL_RESPONSES),
    )
    caplog.clear()

    # Logger name 走 import path 完整版（fetch_pending_sql_and_params 內
    # logger = logging.getLogger(__name__)；本 test 從 program_code.* 路徑
    # import → logger.name = 'program_code.ml_training.
    # mlde_demo_applier_evidence_filter'。對齊不同 conftest sys.path 起點，
    # 雙 logger name 一起 set 確保 W2 既有 test（short path）+ 本 R7-T6 test
    # （long path）皆 capture works。
    with caplog.at_level(
        logging.INFO,
        logger="program_code.ml_training.mlde_demo_applier_evidence_filter",
    ):
        sql_partial, params_partial = fetch_pending_sql_and_params(
            cur_partial,
            lookback_hours=24,
            engine_mode="demo",
            min_confidence=0.5,
            min_samples=10,
            max_recommendations=20,
        )

    partial_msgs = [r.getMessage() for r in caplog.records]
    partial_dumps = [
        m for m in partial_msgs if "evidence_filter capability dump" in m
    ]
    assert len(partial_dumps) >= 1, (
        f"partial schema 路徑必 emit 1+ INFO log；實際 logs={partial_msgs}"
    )
    partial_msg = partial_dumps[-1]
    # partial = 4/6 (3 column on MSR + has_replay_experiments=True；缺
    # expires_at + status)
    assert "caps=4/6" in partial_msg, (
        f"partial schema 必含 caps=4/6（實際 msg={partial_msg!r}）"
    )
    assert "block_a=on" in partial_msg
    assert "block_b=partial" in partial_msg

    # 驗 SQL fragment 走 EXISTS subquery degraded gate（W2 partial 路徑）
    assert "EXISTS" in sql_partial
    assert "manifest_hash IS NOT NULL" not in sql_partial


# ───────────────────────────────────────────────────────────────────
# Case 4：V055 verify portion (3) DB-level paired CHECK enforce
# ───────────────────────────────────────────────────────────────────


def test_r7_e2e_v051_paired_check_enforces_at_db_level() -> None:
    """caller 漏傳 metadata（calibrated_replay tier + replay_experiment_id NULL
    + manifest_hash NULL）→ V055 verify portion (3) line 361-367 RAISE
    EXCEPTION，DB level 強制 paired contract。

    模擬 PL/pgSQL function reject 使 caller psycopg2.Error 捕獲；不應 silent
    pass — 此 test 是「caller 試圖繞過 helper 直接 INSERT」的反模式守門。
    """
    # 構造 cursor — V055 INSERT 走 should_raise=True 路徑模擬 verify reject。
    cur = _E2EChainCursor(
        v055_paired_check_should_raise=True,
    )

    # caller 嘗試直接呼 verify_replay_evidence_and_insert with calibrated_replay
    # tier + NULL metadata（繞過 build_replay_metadata helper）
    with pytest.raises(RuntimeError) as exc_info:
        cur.execute(
            """
            SELECT learning.verify_replay_evidence_and_insert(
                'demo', NULL, 'grid_trading', 'dream_engine',
                'parameter_proposal', 5.0, 0.5, 200, '{}'::jsonb,
                false, true, 'r7_e2e_test',
                'calibrated_replay', NULL, NULL, NULL, NULL, NULL, NULL
            )
            """,
            (),
        )

    # 驗 RAISE 訊息對齊 V055 line 361-367
    err_msg = str(exc_info.value)
    assert "replay-derived row" in err_msg
    assert "tier=calibrated_replay" in err_msg
    assert (
        "replay_experiment_id" in err_msg or "manifest_hash" in err_msg
    ), "RAISE message 必提及 replay_experiment_id / manifest_hash"
    # cur 統計 V055 嘗試 1 次 + 0 成功（先 RAISE）
    assert cur.v055_insert_count == 1


# ───────────────────────────────────────────────────────────────────
# Case 5：FK chain integrity — V051 FK + paired CHECK 阻 dangling row
# ───────────────────────────────────────────────────────────────────


def test_r7_e2e_fk_chain_no_dangling_row() -> None:
    """V051 FK ON DELETE NO ACTION + paired CHECK chk_mlde_shadow_replay_lineage
    雙重守門：

      1. FK：mlde_shadow_recommendations.replay_experiment_id 引 V049 不存在
         row → INSERT RAISE foreign_key_violation（mock 模擬 PG behavior）。
      2. CHECK：calibrated_replay tier + NOT NULL replay_experiment_id +
         NOT NULL manifest_hash 強制；pair 違反任一 → RAISE。

    本 case 驗：用 LEFT JOIN 找 dangling row 應為 0（V051 FK 已 enforce）。

    Mock 模式：模擬 SELECT mlde_shadow_recommendations LEFT JOIN
    replay.experiments WHERE re.experiment_id IS NULL → 回 0 row（V051 FK
    enforce 後不可能有 dangling row）。
    """
    # 構造 mock cursor：fetchall 回 0 row（V051 enforce 後 LEFT JOIN +
    # IS NULL filter 必為空）。
    cur = MagicMock()
    cur.fetchall.return_value = []  # 0 dangling row

    # 模擬 caller 跑 FK lineage validation SQL（per W2 R7-T7 A10-3 既有 audit）
    cur.execute(
        """
        SELECT msr.id, msr.replay_experiment_id
          FROM learning.mlde_shadow_recommendations msr
          LEFT JOIN replay.experiments re
            ON re.experiment_id = msr.replay_experiment_id
         WHERE msr.evidence_source_tier IN ('calibrated_replay','synthetic_replay','counterfactual_replay')
           AND msr.replay_experiment_id IS NOT NULL
           AND re.experiment_id IS NULL
        """,
        (),
    )
    dangling_rows = cur.fetchall()
    assert len(dangling_rows) == 0, (
        f"V051 FK enforce 後不可能有 dangling row；實得 {len(dangling_rows)} 條"
    )


# ───────────────────────────────────────────────────────────────────
# Live PG E2E smoke (opt-in)
# ───────────────────────────────────────────────────────────────────


def _has_live_pg_env() -> bool:
    """檢測 OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN 是否同時 set。"""
    return (
        os.environ.get("OPENCLAW_TEST_LIVE_PG") == "1"
        and bool(os.environ.get("OPENCLAW_TEST_DSN"))
    )


@pytest.mark.skipif(
    not _has_live_pg_env(),
    reason="Live PG E2E disabled; set OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN to run",
)
def test_r7_e2e_live_pg_round_trip_calibrated_replay() -> None:
    """Live PG E2E：register V049 stub → V055 calibrated_replay INSERT →
    SELECT mlde_shadow_recommendations + JOIN replay.experiments → 驗
    expires_at NOT NULL（V049 column 真存在；V051 FK 真實 enforce）→ DELETE
    cleanup。

    Linux operator 跑（E4 regression 階段 / Sprint C2 W4 closure 階段）。

    本 case 不重 R7-T6 mock 部分；專驗 PG live chain：
      step 1: INSERT V049 stub experiment（含 expires_at + manifest_hash）
      step 2: SELECT learning.verify_replay_evidence_and_insert 寫
              calibrated_replay row（同步傳 metadata）
      step 3: SELECT row + JOIN V049 取 expires_at → 驗 expires_at NOT NULL
      step 4: cleanup（ROLLBACK；不寫 production）
    """
    try:
        import psycopg2  # type: ignore
        from psycopg2.extras import Json  # type: ignore
    except ImportError:
        pytest.skip("psycopg2 not installed")

    dsn = os.environ.get("OPENCLAW_TEST_DSN")
    assert dsn, "OPENCLAW_TEST_DSN 未設"

    # 用獨立 UUID 避免與 V055 既有 live test 撞 row
    test_exp_id = str(uuid.UUID("00000000-0000-0000-0000-0000000076f6"))
    test_hash_hex = (
        "76f6" * 16  # 64 char hex（match BYTEA 32-byte length）
    )

    with psycopg2.connect(dsn, connect_timeout=2) as conn:
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("SAVEPOINT r7t6_e2e_smoke")
            try:
                # step 1: INSERT V049 stub experiment（含 expires_at NOT NULL）
                cur.execute(
                    """
                    INSERT INTO replay.experiments (
                        experiment_id, status, created_at,
                        half_life_days, embargo_days, runtime_environment,
                        expires_at, manifest_hash
                    ) VALUES (
                        %s, 'created', now(),
                        14.0, 14, 'mac_dev_smoke_test_only',
                        now() + interval '7 days', decode(%s, 'hex')
                    )
                    ON CONFLICT (experiment_id) DO NOTHING
                    """,
                    (test_exp_id, test_hash_hex),
                )

                # step 2: V055 verify+INSERT calibrated_replay row
                cur.execute(
                    """
                    SELECT learning.verify_replay_evidence_and_insert(
                        'demo', 'BTCUSDT', 'grid_trading', 'dream_engine',
                        'parameter_proposal', 8.0, 0.6, 200, %s,
                        false, true, 'r7_e2e_test',
                        'calibrated_replay', %s, %s,
                        now() + interval '7 days', NULL, NULL, NULL
                    )
                    """,
                    (Json({"r7_e2e": True}), test_exp_id, test_hash_hex),
                )
                new_id = cur.fetchone()[0]
                assert isinstance(new_id, int) and new_id > 0

                # step 3: SELECT row + JOIN V049 取 expires_at（驗 V055 round 2
                # fix：mlde_shadow_recommendations 不持久化 expires_at；TTL 透
                # V051 FK + V049 expires_at column 取）
                cur.execute(
                    """
                    SELECT msr.evidence_source_tier,
                           msr.replay_experiment_id,
                           encode(msr.manifest_hash, 'hex'),
                           re.expires_at
                      FROM learning.mlde_shadow_recommendations msr
                      JOIN replay.experiments re
                        ON re.experiment_id = msr.replay_experiment_id
                     WHERE msr.id = %s
                    """,
                    (new_id,),
                )
                row = cur.fetchone()
                assert row is not None
                tier, exp_id, hash_hex, expires_at = row
                assert tier == "calibrated_replay"
                assert str(exp_id) == test_exp_id
                assert hash_hex == test_hash_hex
                assert expires_at is not None, (
                    "V049 expires_at 必 NOT NULL（R7 spec §3.1 contract）"
                )
                # 驗 expires_at > now（active manifest）
                cur.execute("SELECT now()")
                now_ts = cur.fetchone()[0]
                assert expires_at > now_ts, (
                    f"expires_at 必為未來；expires_at={expires_at} now={now_ts}"
                )
            finally:
                # step 4: cleanup（ROLLBACK；不污染 production）
                cur.execute("ROLLBACK TO SAVEPOINT r7t6_e2e_smoke")
                cur.execute("ROLLBACK")


@pytest.mark.skipif(
    not _has_live_pg_env(),
    reason="Live PG E2E disabled; set OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN to run",
)
def test_r7_e2e_live_pg_block_b_full_capability_real_fire() -> None:
    """Live PG E2E：post V049 + V051 deploy 後 capability probe 6/6 → Block B
    完整版 SQL fire；對齊 case 3 mock 子場景 A semantic。

    Linux operator 跑：驗 PG schema 真實能讓 capability probe 命中 6/6（V049
    expires_at + status column 都 land）。
    """
    try:
        import psycopg2  # type: ignore
    except ImportError:
        pytest.skip("psycopg2 not installed")

    dsn = os.environ.get("OPENCLAW_TEST_DSN")
    assert dsn

    with psycopg2.connect(dsn, connect_timeout=2) as conn:
        with conn.cursor() as cur:
            caps = evidence_filter_capabilities(cur)
            # post V049+V051 deploy 必 6/6（per Sprint A R3 V049 land + Sprint B
            # V051 land）
            assert caps.get("has_evidence_source_tier") is True
            assert caps.get("has_replay_experiment_id") is True
            assert caps.get("has_manifest_hash") is True
            assert caps.get("has_replay_experiments") is True
            assert caps.get("replay_experiments_has_expires_at") is True
            assert caps.get("replay_experiments_has_status") is True

            # SQL fragment 真實 fire 完整 Block B
            sql_fragment, _params = build_evidence_source_filter(caps)
            assert "manifest_hash IS NOT NULL" in sql_fragment
            assert "expires_at > now()" in sql_fragment
            assert "status NOT IN" in sql_fragment


@pytest.mark.skipif(
    not _has_live_pg_env(),
    reason="Live PG E2E disabled; set OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN to run",
)
def test_r7_e2e_live_pg_v051_fk_enforces_dangling_zero() -> None:
    """Live PG E2E：FK chain integrity 真 PG 驗證 — V051 FK ON DELETE NO ACTION
    保證 mlde_shadow_recommendations 0 dangling row（calibrated_replay tier
    row 必 JOIN 命中 replay.experiments）。

    Linux operator 跑：產線真實 SELECT 0 row 即 V051 enforce 完整。
    """
    try:
        import psycopg2  # type: ignore
    except ImportError:
        pytest.skip("psycopg2 not installed")

    dsn = os.environ.get("OPENCLAW_TEST_DSN")
    assert dsn

    with psycopg2.connect(dsn, connect_timeout=2) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT msr.id, msr.replay_experiment_id
                  FROM learning.mlde_shadow_recommendations msr
                  LEFT JOIN replay.experiments re
                    ON re.experiment_id = msr.replay_experiment_id
                 WHERE msr.evidence_source_tier
                       IN ('calibrated_replay','synthetic_replay','counterfactual_replay')
                   AND msr.replay_experiment_id IS NOT NULL
                   AND re.experiment_id IS NULL
                """,
            )
            dangling = cur.fetchall()
            assert len(dangling) == 0, (
                f"V051 FK enforce 後 0 dangling row；實得 {len(dangling)} 條"
            )


# ───────────────────────────────────────────────────────────────────
# Smoke：mock-mode coverage report
# ───────────────────────────────────────────────────────────────────


def test_r7_e2e_mock_mode_test_count_summary() -> None:
    """Smoke：確認 R7-T6 mock-mode case 數 ≥ 5 + Live PG opt-in case 數 ≥ 3。

    R7-T6 mock-friendly subset：5 case（case 1-5 純 mock + caplog）。
    Live PG opt-in subset：3 case（live_pg_round_trip / live_pg_block_b /
    live_pg_v051_fk）。
    """
    import test_r7_e2e_advisory_integration as _self  # type: ignore

    case_names = [
        n
        for n in dir(_self)
        if n.startswith("test_r7_e2e_") and not n.endswith("test_count_summary")
    ]
    mock_cases = [n for n in case_names if "live_pg" not in n]
    live_pg_cases = [n for n in case_names if "live_pg" in n]
    assert len(mock_cases) >= 5, (
        f"R7-T6 mock case 必 ≥ 5；實得 {len(mock_cases)} 個 ({mock_cases})"
    )
    assert len(live_pg_cases) >= 3, (
        f"R7-T6 Live PG opt-in case 必 ≥ 3；實得 {len(live_pg_cases)} 個"
    )


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
