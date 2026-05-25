"""
MODULE_NOTE
模塊用途：M4 Stage 1 DRAFT writeback 至 learning.hypotheses（V100 base + V103 EXTEND 6 column）。

per W1-B spec §4：
   - Decision Lease acquire（lease_type='M4_DRAFT_WRITEBACK'）
   - INSERT learning.hypotheses（base 13 column + V103 EXTEND 6 column）
   - Lease release

不變量（per W1-B spec §0 I-5 + 16 原則 #7）：
   - DRAFT writeback 不 trigger live order（live_order_intent=FALSE）
   - 不 auto-promote past 'preregistered'（state ∈ {'draft', 'exploratory', 'preregistered'}）
   - hypothesis_source_module 必顯式設 'M4_AUTO'（不依 DEFAULT 'OPERATOR'）
   - leakage_scan_pass 必顯式設（per §3.3 結果），不可 NULL（DEFAULT FALSE fail-closed）
   - decision_lease_draft_id 必 backref Lease ID（per §9.5 audit chain）

Mac scaffold 階段：本 module 提供 SQL pattern + Lease 介面 stub；真實 PG INSERT
由 Linux runtime 跑（per `feedback_v_migration_pg_dry_run` Mac mock 不能 catch
PG semantic）。Sprint 2 末週 cron wire-up 由 W2-D MIT 接 production。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# INSERT pattern — parametrized 形式，caller 用 psycopg2.cursor.execute 注 params。
# 為什麼 V103 EXTEND 6 column 必顯式設：DEFAULT 'OPERATOR' / FALSE / 'NONE' 是給
# backfill existing row 用；新 row 必走顯式 'M4_AUTO'（per W1-B spec §4.2）。
DRAFT_INSERT_SQL: str = """
INSERT INTO learning.hypotheses (
    hypothesis_id,
    strategy_name,
    status,
    m4_attribute_n,
    m4_attribute_p_bonferroni,
    m4_attribute_effect_size,
    m4_attribute_subperiod_pass,
    m4_attribute_graveyard_flag,
    m4_attribute_silhouette,
    hypothesis_source_module,
    leakage_scan_pass,
    bonferroni_corrected_p,
    replicability_score,
    decision_lease_draft_id,
    cowork_review_status,
    created_at
) VALUES (
    %(hypothesis_id)s,
    %(strategy_name)s,
    %(status)s,
    %(n_observations)s,
    %(raw_p_value)s,
    %(cohens_d)s,
    %(subperiod_pass)s,
    %(graveyard_flag)s,
    %(silhouette)s,
    'M4_AUTO',
    %(leakage_scan_pass)s,
    %(raw_p_value)s,
    %(replicability_score)s,
    %(decision_lease_draft_id)s,
    'NONE',
    %(created_at)s
)
"""


@dataclass
class DraftWritebackPayload:
    """DRAFT writeback INSERT payload — 對應 Rust m4_miner::types::PatternDraft + 6 attribute。

    不變量：
       - status ∈ {'draft', 'exploratory', 'preregistered'} — Rust PatternDraft 已驗
       - decision_lease_draft_id 不可 NULL（per W1-B spec §9.5 audit chain）
       - leakage_scan_pass 不可 NULL（DEFAULT FALSE fail-closed per V103 EXTEND）
    """
    hypothesis_id: uuid.UUID
    strategy_name: str
    status: str  # 'draft' / 'exploratory' / 'preregistered'
    n_observations: int
    raw_p_value: float  # bonferroni_corrected_p 同此值，application 端用 K=2500 比較
    cohens_d: float
    subperiod_pass: Optional[bool]
    graveyard_flag: bool
    silhouette: Optional[float]
    leakage_scan_pass: bool
    replicability_score: Optional[float]
    decision_lease_draft_id: uuid.UUID
    created_at: datetime


def build_writeback_payload(
    strategy_name: str,
    n_observations: int,
    raw_p_value: float,
    cohens_d: float,
    status_candidate: str,
    subperiod_pass: Optional[bool] = None,
    graveyard_flag: bool = False,
    silhouette: Optional[float] = None,
    leakage_scan_pass: bool = False,
    replicability_score: Optional[float] = None,
    decision_lease_draft_id: Optional[uuid.UUID] = None,
) -> DraftWritebackPayload:
    """組裝 INSERT payload。

    Raises:
       ValueError: status_candidate 不在白名單；或 decision_lease_draft_id 為 None
           （per W1-B spec §9.5 audit chain — Lease backref 100% non-NULL）
    """
    # 不變量：M4 不可寫 'live' / 'promoted' / 'rejected'
    # (per 16 原則 #7 + AMD-2026-05-21-01 protected scope (a)).
    if status_candidate not in ("draft", "exploratory", "preregistered"):
        raise ValueError(
            f"M4 DRAFT writeback 不能 promote past 'preregistered'，"
            f"got status_candidate='{status_candidate}'"
        )
    if decision_lease_draft_id is None:
        # 不變量：Lease backref 100% non-NULL（per W1-B spec §9.5）。
        # 為什麼 fail-loud：缺 Lease backref 等同失去 audit chain，
        # 違反 16 原則 #8 "every trade reconstructable"。
        raise ValueError(
            "decision_lease_draft_id 必 non-NULL — Lease backref 是 audit chain 必要條件"
        )
    return DraftWritebackPayload(
        hypothesis_id=uuid.uuid4(),
        strategy_name=strategy_name,
        status=status_candidate,
        n_observations=n_observations,
        raw_p_value=max(0.0, min(1.0, raw_p_value)),
        cohens_d=cohens_d,
        subperiod_pass=subperiod_pass,
        graveyard_flag=graveyard_flag,
        silhouette=silhouette,
        leakage_scan_pass=leakage_scan_pass,
        replicability_score=replicability_score,
        decision_lease_draft_id=decision_lease_draft_id,
        created_at=datetime.now(tz=timezone.utc),
    )


def payload_to_params(payload: DraftWritebackPayload) -> dict:
    """把 payload 轉成 psycopg2.execute(SQL, params) 用的 dict。

    為什麼分開：parametrized query 防 SQL injection（CLAUDE.md §七）+ 易於 dry-run 注 mock。
    """
    return {
        "hypothesis_id": str(payload.hypothesis_id),
        "strategy_name": payload.strategy_name,
        "status": payload.status,
        "n_observations": payload.n_observations,
        "raw_p_value": payload.raw_p_value,
        "cohens_d": payload.cohens_d,
        "subperiod_pass": payload.subperiod_pass,
        "graveyard_flag": payload.graveyard_flag,
        "silhouette": payload.silhouette,
        "leakage_scan_pass": payload.leakage_scan_pass,
        "replicability_score": payload.replicability_score,
        "decision_lease_draft_id": str(payload.decision_lease_draft_id),
        "created_at": payload.created_at,
    }


# Decision Lease 介面 stub — Sprint 2 末週由 W2-D MIT 接 GovernanceHub IPC。
# 為什麼用 stub：Mac scaffold 階段不能呼 Linux runtime GovernanceHub；
# 真實 lease acquire/release 走 ai_service.py IPC（per W1-B spec §5.2）。
class GovernanceHubInterface:
    """GovernanceHub Decision Lease 介面 — Sprint 2 scaffold 階段 stub。

    Sprint 3 接 production：用 helper_scripts.lib.ipc_client 連 ai_service.py
    JSON-RPC 2.0 over Unix domain socket（per srv/CLAUDE.md §六 + ipc 規範）。

    不變量：
       - lease_type 必為 'M4_DRAFT_WRITEBACK'（per W1-B spec §4.1）
       - live_order_intent 必 FALSE（M4 是學習路徑非 live order trigger）
       - expires_at <= now + 5 min（短 lease 避過長持有）
    """

    LEASE_TYPE: str = "M4_DRAFT_WRITEBACK"
    DEFAULT_LEASE_TTL_SECONDS: int = 300  # 5 min

    def acquire_lease(self, actor: str = "m4_pattern_miner") -> uuid.UUID:
        """Acquire DRAFT writeback lease（per W1-B spec §4.1）。

        scaffold 階段 stub 回 random UUID；production wire-up 走 IPC。
        """
        # Scaffold 階段：local UUID — production 接 ai_service.py 後改 IPC call。
        return uuid.uuid4()

    def release_lease(self, lease_id: uuid.UUID, outcome: str = "SUCCESS") -> None:
        """Release lease（per W1-B spec §4.1）。

        scaffold 階段 no-op；production wire-up 寫 audit log + close lease。
        """
        # Scaffold no-op — production audit log emit 在 W2-D MIT IMPL。
        pass
