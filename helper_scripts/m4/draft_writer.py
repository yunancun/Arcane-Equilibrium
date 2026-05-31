"""
MODULE_NOTE
模塊用途：M4 Stage 1 DRAFT writeback 至 learning.hypotheses（V100 base + V103 EXTEND 6 column）。

per W1-B spec §4 + W1-A spec §7.3 6 attribute → V103 EXTEND mapping：
   - Decision Lease acquire（lease_type='M4_DRAFT_WRITEBACK'）
   - INSERT learning.hypotheses（V100 base required + V103 EXTEND real column；
     6 attribute composite mapping per W1-A §7.3）
   - Lease release

Schema 對齊（W1-C Round 3 empirical PG reflect 2026-05-25 — `\\d learning.hypotheses`）：
   真實 19 column = V100 base 13 + V103 EXTEND 6；**0 個 `m4_attribute_*` column** + **0 個 `evidence_json` column**。
   W1-C Round 1/2 IMPL 假設 6 個 `m4_attribute_*` 是 W2-F QA + FA HIGH BLOCKER 退回。

   per W1-A spec §7.3 mapping（與 W2-F QA report §5.3 一致）：
      attribute_n            → min_sample_size              (V100 base INTEGER)
      attribute_p_bonferroni → bonferroni_corrected_p       (V103 EXTEND NUMERIC(10,8))
      attribute_effect_size  → composite into replicability_score (V103 EXTEND NUMERIC(5,4))
      attribute_subperiod    → composite into replicability_score
      attribute_silhouette   → composite into replicability_score
      attribute_graveyard    → warning only（per attribute_enforcer.py 既有設計）；不寫 PG

   不引入 `evidence_json` JSONB column（PA task 提及但 empirical PG 不存在；
   W1-A spec §7.3 也未要求；強寫會 PG ERROR）。caller-side cron 完整 6 attribute
   metadata 用 logger 輸出供 cowork operator review，audit chain 走
   decision_lease_draft_id backref + lease metadata。

不變量（per W1-B spec §0 I-5 + 16 原則 #7）：
   - DRAFT writeback 不 trigger live order
   - 不 auto-promote past 'preregistered'（PG status ∈ {'draft', 'preregistered'}；
     analysis lane 'exploratory' 由 caller 映射成 PG 'draft'）
   - hypothesis_source_module 必顯式 'M4_AUTO'（不依 DEFAULT 'OPERATOR'）
   - leakage_scan_pass 必顯式設（per §3.3 結果），DEFAULT FALSE fail-closed
   - decision_lease_draft_id 必 backref Lease ID（per §9.5 audit chain）
   - engine_mode 必 IN ('live','live_demo')（per CLAUDE.md §七）

Mac scaffold 階段：本 module 提供 SQL pattern + Lease 介面 stub；真實 PG INSERT
由 Linux runtime 跑（per `feedback_v_migration_pg_dry_run` Mac mock 不能 catch
PG semantic）。Sprint 2 末週 cron wire-up 由 W2-D MIT 接 production。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# INSERT SQL — parametrized 形式對齊真實 V100 base + V103 EXTEND schema。
# 為什麼 13 column（5 V100 required + 1 V100 optional + 6 V103 EXTEND + 1 created_at）：
#    - V100 NOT NULL required（5）：strategy_name / pre_reg_ts / pre_reg_hash / status / engine_mode
#    - V100 optional（min_sample_size）：W1-A §7.3 mapping attribute_n
#    - V103 EXTEND 6：hypothesis_source_module（必顯式 'M4_AUTO'）/ leakage_scan_pass /
#      bonferroni_corrected_p / replicability_score / decision_lease_draft_id /
#      cowork_review_status（顯式 'NONE'，Y1 不啟 Cowork review）
#    - created_at：DEFAULT now() 但顯式設便於 dry-run / replay 時間戳一致性
# 為什麼不含 hypothesis_id：BIGSERIAL DEFAULT nextval；INSERT 不指定讓 PG 自動配 ID。
# 為什麼不含 evidence_json：empirical PG 不存在此 column（per W1-C Round 3 reflection）。
DRAFT_INSERT_SQL: str = """
INSERT INTO learning.hypotheses (
    strategy_name,
    pre_reg_ts,
    pre_reg_hash,
    status,
    engine_mode,
    min_sample_size,
    hypothesis_source_module,
    leakage_scan_pass,
    bonferroni_corrected_p,
    replicability_score,
    decision_lease_draft_id,
    cowork_review_status,
    created_at
) VALUES (
    %(strategy_name)s,
    %(pre_reg_ts)s,
    %(pre_reg_hash)s,
    %(status)s,
    %(engine_mode)s,
    %(n_observations)s,
    'M4_AUTO',
    %(leakage_scan_pass)s,
    %(bonferroni_corrected_p)s,
    %(replicability_score)s,
    %(decision_lease_draft_id)s,
    'NONE',
    %(created_at)s
)
RETURNING hypothesis_id
"""


@dataclass
class DraftWritebackPayload:
    """DRAFT writeback INSERT payload — 對齊 V100 base + V103 EXTEND 真實 schema。

    Field mapping（per W1-A spec §7.3 + W1-C Round 3 empirical PG reflect）：
       hypothesis_id = None     -- BIGSERIAL 由 PG nextval 分配；INSERT 不傳
       strategy_name             -- V100 base TEXT NOT NULL
       pre_reg_ts                -- V100 base TIMESTAMPTZ NOT NULL（M4 用 created_at 同值；
                                    pre-registration time == DRAFT writeback time）
       pre_reg_hash              -- V100 base TEXT NOT NULL（SHA-256 of spec params canonical JSON）
       status                    -- V100 base TEXT NOT NULL CHECK 11 enum；M4 限 {draft,preregistered}
       engine_mode               -- V100 base TEXT NOT NULL CHECK 4 enum；M4 限 {live,live_demo}
       n_observations            -- → min_sample_size INTEGER（V100 base optional；
                                    per W1-A §7.3 attribute_n mapping）
       leakage_scan_pass         -- V103 EXTEND BOOLEAN（DEFAULT FALSE fail-closed）
       bonferroni_corrected_p    -- V103 EXTEND NUMERIC(10,8) CHECK [0,1]；W1-A §7.3
                                    attribute_p_bonferroni（K=2500 corrected）
       replicability_score       -- V103 EXTEND NUMERIC(5,4) CHECK [0,1]；composite
                                    of attribute_effect_size + subperiod + silhouette
                                    per W1-A §7.3
       decision_lease_draft_id   -- V103 EXTEND UUID；audit chain backref
       cowork_review_status      -- V103 EXTEND TEXT；M4 限 'NONE'（Y1 不啟 Cowork review）

    不變量：
       - status ∈ {'draft', 'preregistered'}；不可直接寫 analysis lane 'exploratory'
       - engine_mode ∈ {'live', 'live_demo'}（per CLAUDE.md §七）
       - decision_lease_draft_id 不可 NULL（per audit chain）
       - leakage_scan_pass 不可 NULL（DEFAULT FALSE per V103 EXTEND fail-closed）

    Caller-side 6 attribute completeness：
       attribute_n / bonferroni_corrected_p / replicability_score 寫 PG；
       attribute_effect_size / subperiod_pass / silhouette / graveyard_flag 由 caller
       cron 端用 logger 輸出完整 metadata（attribute_enforcer.py 已將 graveyard 設
       'warning only 不阻 promote'）；audit chain via decision_lease_draft_id backref。
    """
    strategy_name: str
    pre_reg_ts: datetime
    pre_reg_hash: str
    status: str  # 'draft' / 'preregistered'
    engine_mode: str  # 'live' / 'live_demo'
    n_observations: int
    leakage_scan_pass: bool
    bonferroni_corrected_p: Optional[float]
    replicability_score: Optional[float]
    decision_lease_draft_id: uuid.UUID
    cowork_review_status: str  # 永遠 'NONE'（Y1 不啟 Cowork review）
    created_at: datetime

    # Caller-side metadata — 不寫 PG，audit log 用
    raw_p_value: float = 0.0
    cohens_d: Optional[float] = None
    subperiod_pass: Optional[bool] = None
    graveyard_flag: bool = False
    silhouette: Optional[float] = None


def _compose_replicability_score(
    cohens_d: Optional[float],
    subperiod_pass: Optional[bool],
    silhouette: Optional[float],
) -> Optional[float]:
    """3-element composite per W1-A §7.3 mapping。

    為什麼 composite：V103 EXTEND replicability_score 為 NUMERIC(5,4) [0,1] single
    value；W1-A §7.3 將 effect size / subperiod stability / silhouette 三軸
    encode 進此 score（per spec line 695-697 "composite (#3 effect + #4 subperiod
    + #6 cluster)"）。

    baseline 加權（per W1-B spec §4.3 Open Q3 待 QC review）：
       - cohens_d 標準化（|d|/3 capped at 1.0），weight 0.4
       - subperiod_pass 0/1，weight 0.3
       - silhouette 標準化（max(0, min(1, sil))），weight 0.3

    若任一 component 為 None：跳過該 weight，剩餘 weight 重新歸一。
    所有 None → return None（不可計算 composite）。

    QC review pending（W1-B spec §4.3 Open Q3）：weights 0.4/0.3/0.3 是 baseline；
    Sprint 3 接 cron 收集 empirical 後 PM + PA + QC 仲裁終值。
    """
    components: list[tuple[float, float]] = []  # (normalized_value, weight)
    if cohens_d is not None:
        d_norm = min(1.0, abs(cohens_d) / 3.0)
        components.append((d_norm, 0.4))
    if subperiod_pass is not None:
        components.append((1.0 if subperiod_pass else 0.0, 0.3))
    if silhouette is not None:
        sil_norm = max(0.0, min(1.0, silhouette))
        components.append((sil_norm, 0.3))

    if not components:
        return None

    total_weight = sum(w for _, w in components)
    weighted_sum = sum(v * w for v, w in components)
    return round(weighted_sum / total_weight, 4)  # NUMERIC(5,4) 精度對齊


def _compute_pre_reg_hash(
    strategy_name: str,
    n_observations: int,
    raw_p_value: float,
    cohens_d: Optional[float],
    subperiod_pass: Optional[bool],
    graveyard_flag: bool,
    silhouette: Optional[float],
) -> str:
    """組裝 pre_reg_hash — canonical JSON serialization 的 SHA-256。

    為什麼 hash：pre-registration 不變式（per V100 base spec ADR-0026 v3 + DOC-08 §12）；
    hash 鎖定 spec spec + thresholds 防後置調整。M4 場景 spec = 6 attribute snapshot。
    """
    payload = {
        "strategy_name": strategy_name,
        "attribute_n": n_observations,
        "attribute_p_raw": raw_p_value,
        "attribute_effect_size_cohens_d": cohens_d,
        "attribute_subperiod_pass": subperiod_pass,
        "attribute_graveyard_flag": graveyard_flag,
        "attribute_silhouette": silhouette,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    decision_lease_draft_id: Optional[uuid.UUID] = None,
    engine_mode: str = "live_demo",
) -> DraftWritebackPayload:
    """組裝 INSERT payload — 對齊 V100 base + V103 EXTEND empirical schema。

    Args:
        strategy_name: 策略名稱（必填，V100 base NOT NULL）
        n_observations: 觀察樣本量（→ min_sample_size，W1-A §7.3 attribute_n mapping）
        raw_p_value: 原始 p-value（用於 bonferroni_corrected_p ≤ 1 clamp + audit log）
        cohens_d: Cohen's d effect size（→ replicability_score composite）
        status_candidate: 'draft' / 'preregistered'（V100 PG enum 白名單檢查）
        subperiod_pass: sub-period stability boolean（→ replicability_score composite）
        graveyard_flag: 圖庫匹配警告（warning only，不寫 PG）
        silhouette: cluster silhouette（→ replicability_score composite）
        leakage_scan_pass: leakage scan 結果（V103 EXTEND BOOLEAN fail-closed）
        decision_lease_draft_id: Lease UUID（V103 EXTEND，audit chain 必 non-NULL）
        engine_mode: 'live' / 'live_demo'（V100 base，CLAUDE.md §七 必含 live_demo）

    Raises:
       ValueError: status_candidate 不在白名單；或 decision_lease_draft_id 為 None；
           或 engine_mode 不在 IN ('live','live_demo')
    """
    # 不變量：M4 不可寫 'live' / 'promoted' / 'rejected'，也不可直接寫
    # analysis lane 'exploratory'（V100 CHECK enum 不含該值）。
    # (per 16 原則 #7 + AMD-2026-05-21-01 protected scope (a)).
    if status_candidate not in ("draft", "preregistered"):
        raise ValueError(
            f"M4 DRAFT writeback status 必須是 V100 PG enum 中的 'draft' 或 "
            f"'preregistered'，"
            f"got status_candidate='{status_candidate}'"
        )
    if decision_lease_draft_id is None:
        # 不變量：Lease backref 100% non-NULL（per W1-B spec §9.5）。
        # 為什麼 fail-loud：缺 Lease backref 等同失去 audit chain，
        # 違反 16 原則 #8 "every trade reconstructable"。
        raise ValueError(
            "decision_lease_draft_id 必 non-NULL — Lease backref 是 audit chain 必要條件"
        )
    # 不變量：engine_mode 必 IN ('live','live_demo')（per CLAUDE.md §七 + memory
    # project_engine_mode_tag_live_demo；M4 source 已是 fills_loader engine_mode filter，
    # writeback 端再次驗）。
    if engine_mode not in ("live", "live_demo"):
        raise ValueError(
            f"M4 DRAFT writeback engine_mode 必 IN ('live','live_demo')，"
            f"got engine_mode='{engine_mode}'"
        )

    # bonferroni_corrected_p — clamp [0,1] 對齊 V103 EXTEND CHECK constraint
    bonferroni_p_clamped = max(0.0, min(1.0, raw_p_value))

    # replicability_score composite — 3 軸 weighted average
    replicability = _compose_replicability_score(cohens_d, subperiod_pass, silhouette)

    # pre_reg_hash — 6 attribute canonical snapshot SHA-256
    pre_reg_hash = _compute_pre_reg_hash(
        strategy_name=strategy_name,
        n_observations=n_observations,
        raw_p_value=raw_p_value,
        cohens_d=cohens_d,
        subperiod_pass=subperiod_pass,
        graveyard_flag=graveyard_flag,
        silhouette=silhouette,
    )

    now = datetime.now(tz=timezone.utc)
    return DraftWritebackPayload(
        strategy_name=strategy_name,
        pre_reg_ts=now,
        pre_reg_hash=pre_reg_hash,
        status=status_candidate,
        engine_mode=engine_mode,
        n_observations=n_observations,
        leakage_scan_pass=leakage_scan_pass,
        bonferroni_corrected_p=bonferroni_p_clamped,
        replicability_score=replicability,
        decision_lease_draft_id=decision_lease_draft_id,
        cowork_review_status="NONE",
        created_at=now,
        # caller-side metadata（不寫 PG，audit log 用）
        raw_p_value=raw_p_value,
        cohens_d=cohens_d,
        subperiod_pass=subperiod_pass,
        graveyard_flag=graveyard_flag,
        silhouette=silhouette,
    )


def payload_to_params(payload: DraftWritebackPayload) -> dict:
    """把 payload 轉成 psycopg2.execute(SQL, params) 用的 dict。

    為什麼分開：parametrized query 防 SQL injection（CLAUDE.md §七）+ 易於 dry-run 注 mock。

    為什麼只回 INSERT 用 13 field：subset of dataclass 字段；raw_p_value / cohens_d /
    subperiod_pass / graveyard_flag / silhouette 是 caller-side metadata 不進 PG。
    """
    return {
        "strategy_name": payload.strategy_name,
        "pre_reg_ts": payload.pre_reg_ts,
        "pre_reg_hash": payload.pre_reg_hash,
        "status": payload.status,
        "engine_mode": payload.engine_mode,
        "n_observations": payload.n_observations,
        "leakage_scan_pass": payload.leakage_scan_pass,
        "bonferroni_corrected_p": payload.bonferroni_corrected_p,
        "replicability_score": payload.replicability_score,
        "decision_lease_draft_id": str(payload.decision_lease_draft_id),
        "created_at": payload.created_at,
    }


def build_audit_metadata(payload: DraftWritebackPayload) -> dict:
    """組裝 6 attribute 完整 metadata supplément — 不入 PG，給 cron logger emit。

    為什麼存在：W1-A §7.3 6→4 composite mapping 失去 graveyard_flag / 原始 cohens_d /
    原始 silhouette / raw_p 等審計痕跡。audit chain 走 decision_lease_draft_id backref
    （PG）+ cron logger emit（log file）雙軌。
    """
    return {
        "decision_lease_draft_id": str(payload.decision_lease_draft_id),
        "strategy_name": payload.strategy_name,
        "pre_reg_hash": payload.pre_reg_hash,
        "status": payload.status,
        "engine_mode": payload.engine_mode,
        # 6 attribute full snapshot（rest 由 PG column 承載）
        "attribute_n": payload.n_observations,
        "attribute_p_raw": payload.raw_p_value,
        "attribute_p_bonferroni_clamped": payload.bonferroni_corrected_p,
        "attribute_effect_size_cohens_d": payload.cohens_d,
        "attribute_subperiod_pass": payload.subperiod_pass,
        "attribute_graveyard_flag": payload.graveyard_flag,
        "attribute_silhouette": payload.silhouette,
        "replicability_score_composite": payload.replicability_score,
        "leakage_scan_pass": payload.leakage_scan_pass,
    }


# Decision Lease 介面 placeholder — Sprint 2 末週由 W2-D MIT 接 GovernanceHub IPC。
# 為什麼 fail-closed：Mac scaffold 階段不能呼 Linux runtime GovernanceHub；
# 隨機 UUID 不能當 production Decision Lease audit proof。
class GovernanceHubInterface:
    """GovernanceHub Decision Lease 介面 — 未 wire 前 fail-closed。

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
        """Acquire DRAFT writeback lease（per W1-B spec §4.1）.

        Production IPC is not implemented in this interface yet. Callers must pass
        pre-acquired real lease UUIDs into the Stage 1 runner instead of using a
        synthetic UUID.
        """
        del actor
        raise NotImplementedError(
            "GovernanceHubInterface.acquire_lease is not wired to production IPC; "
            "pass a real decision_lease_draft_id UUID to the Stage 1 runner"
        )

    def release_lease(self, lease_id: uuid.UUID, outcome: str = "SUCCESS") -> None:
        """Release lease（per W1-B spec §4.1）。

        scaffold 階段 no-op；production wire-up 寫 audit log + close lease。
        """
        # Scaffold no-op — production audit log emit 在 W2-D MIT IMPL。
        pass
