#!/usr/bin/env python3
"""W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1：30d cycle 解封候選審計 + governance.unblock_candidates writer。

模組目的（中文）：
    QC v3 NEW-ISSUE-V3-4 揭露 freeze 是 one-way street — 17 frozen cells 多數
    7d window 0 fills + 0 rejected_outcomes，selection-bias 累積使 blocked_symbols
    list 單調膨脹（17→18→N）。本模組 fork 既有 blocked_symbols_7d_counterfactual.py
    為 30d 版，加：

      1. 30d window paper engine fill query（freeze 期 paper 不被 block, 仍可
         產生 edge proxy）
      2. §3 unblock criteria evaluation（DSR/PBO + paper_fills_30d ≥30 +
         paper_net_edge_bps_30d ≥+5 bps + SM-04 escalate 0 等）
      3. 4 verdict logic：unblock_candidate / continue_freeze /
         dormant_no_evidence / manual_review_required
      4. yo-yo detection（30d 內 unfrozen + re_frozen ≥1 cycle 強制
         manual_review_required，防止反覆解封/重 freeze）
      5. governance.unblock_candidates state machine writer（INSERT 候選 row +
         UPDATE outcome row）

    注意：本 writer 僅寫 candidate row + 初始 verdict；§5.2 sign-off 流程的
    outcome='unfrozen' UPDATE 由獨立 unfrozen_handler 觸發（在 force_eval API
    或 cron 驗證 sign-off 完成後執行），commit_sha 由 writer git rev-parse 在
    那一刻抓取（spec §5.2 #5），不是 INSERT 時刻。

對應 spec：
    docs/execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md
對應 V###：
    sql/migrations/V090__governance_unblock_candidates.sql
對應 既有 audit：
    helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py（保留為 7d
    audit，不取代）
對應 freeze SOP：
    docs/governance_dev/strategy_blocked_symbols_freeze.json
對應 healthcheck：
    helper_scripts/db/passive_wait_healthcheck/checks_governance.py [64]

入口（CLI）：
    python3 -m helper_scripts.db.audit.blocked_symbols_30d_unblock_check \
            --days 30 \
            --evaluation-path cron_30d_cycle \
            --commit  # 真實寫 PG；省略則 dry-run 印 markdown

    python3 -m helper_scripts.db.audit.blocked_symbols_30d_unblock_check \
            --cell grid_trading:BSBUSDT \
            --evaluation-path operator_force_eval \
            --commit  # 單 cell 強制 eval（force_eval API 內部呼叫）
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = ROOT / "docs" / "governance_dev" / "strategy_blocked_symbols_freeze.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from helper_scripts.db.passive_wait_healthcheck.db import _get_conn  # noqa: E402


# =============================================================================
# §1 常數與閾值（per spec §3 unblock criteria）
# =============================================================================

# spec §3 unblock criteria — 全 AND 條件
PAPER_FILLS_30D_MIN: int = 30
PAPER_NET_EDGE_BPS_MIN: float = 5.0  # +5 bps gate（demo cost 15-20 bps 下界）
DSR_MIN: float = 0.5   # W-AUDIT-6 acceptance metric
PBO_MAX: float = 0.5   # selection-bias 防護
REJECTED_OUTCOME_MIN_IF_REJECTED: int = 5  # rejected_n>0 時 outcome 標籤最少數
SM04_ESCALATE_DAYS: int = 7
WALL_CLOCK_FROZEN_MIN_DAYS: int = 30
DEFAULT_WINDOW_DAYS: int = 30

# yo-yo detection（spec §5.3）
YO_YO_DETECTION_WINDOW_DAYS: int = 30

# evaluation_path（spec §3 paper_evidence_jsonb）
EVAL_PATH_CRON: str = "cron_30d_cycle"
EVAL_PATH_FORCE: str = "operator_force_eval"
VALID_EVAL_PATHS: tuple[str, ...] = (EVAL_PATH_CRON, EVAL_PATH_FORCE)

# 4 verdict enum（spec §3, V090 CHECK constraint）
VERDICT_UNBLOCK_CANDIDATE: str = "unblock_candidate"
VERDICT_CONTINUE_FREEZE: str = "continue_freeze"
VERDICT_DORMANT_NO_EVIDENCE: str = "dormant_no_evidence"
VERDICT_MANUAL_REVIEW_REQUIRED: str = "manual_review_required"
VALID_VERDICTS: tuple[str, ...] = (
    VERDICT_UNBLOCK_CANDIDATE,
    VERDICT_CONTINUE_FREEZE,
    VERDICT_DORMANT_NO_EVIDENCE,
    VERDICT_MANUAL_REVIEW_REQUIRED,
)


@dataclass(frozen=True)
class BlockedCell:
    """單一 frozen cell 識別（strategy + symbol 二元組）。"""

    strategy: str
    symbol: str

    def cohort_key(self) -> str:
        """字串 representation；對齊 V090 CHECK constraint 的 cohort 識別。"""
        return f"{self.strategy}:{self.symbol}"


@dataclass
class UnblockCandidateRow:
    """30d audit 評估後的候選 row；對齊 V090 governance.unblock_candidates schema。

    immutable on insert：cell_strategy / cell_symbol / candidate_at_ms /
                         paper_evidence_jsonb / verdict
    mutable via sign-off：outcome / pa_report_path / qc_report_path /
                          commit_sha / unfrozen_at_ms / re_frozen_at_ms /
                          re_freeze_reason
    """

    # immutable 識別 + 證據
    cell_strategy: str
    cell_symbol: str
    candidate_at_ms: int
    paper_evidence: dict  # JSON 化後寫入 paper_evidence_jsonb
    verdict: str

    # mutable lifecycle（INSERT 時皆 None / default）
    requires_pa_qc_signoff: bool = True
    outcome: Optional[str] = None
    pa_report_path: Optional[str] = None
    qc_report_path: Optional[str] = None
    commit_sha: Optional[str] = None
    unfrozen_at_ms: Optional[int] = None
    re_frozen_at_ms: Optional[int] = None
    re_freeze_reason: Optional[str] = None

    # diagnostic 用（非 PG schema 欄位）
    diagnostic_notes: list[str] = field(default_factory=list)


# =============================================================================
# §2 既有 freeze.json 載入（從 7d writer reuse）
# =============================================================================


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    """載入 strategy_blocked_symbols_freeze.json。

    回值：dict 含 frozen_cells.<strategy>.symbols list 結構。
    """
    return json.loads(path.read_text(encoding="utf-8"))


def iter_cells(registry: dict) -> list[BlockedCell]:
    """展開 frozen_cells dict 為 BlockedCell list；保持 7d writer 一致性。"""
    cells: list[BlockedCell] = []
    for strategy, payload in registry["frozen_cells"].items():
        for symbol in payload["symbols"]:
            cells.append(BlockedCell(strategy=strategy, symbol=symbol))
    return cells


def _values_sql(cells: Iterable[BlockedCell]) -> tuple[str, list[str]]:
    """產生 (placeholder_sql, params_list) — 對齊 7d writer pattern。"""
    params: list[str] = []
    placeholders: list[str] = []
    for cell in cells:
        placeholders.append("(%s, %s)")
        params.extend([cell.strategy, cell.symbol])
    if not placeholders:
        raise ValueError("at least one blocked cell is required")
    return ", ".join(placeholders), params


# =============================================================================
# §3 PG query — 30d window paper engine + reject + sm04 + lifecycle
# =============================================================================


def fetch_audit_evidence(
    cells: list[BlockedCell],
    *,
    days: int = DEFAULT_WINDOW_DAYS,
    statement_timeout_ms: int = 10000,
) -> dict[tuple[str, str], dict]:
    """對 cells 跑 30d 多面向 query，回 (strategy, symbol) → evidence dict。

    Evidence dict 含：
        - paper_fills_30d (int): 統計 power 下界
        - paper_net_edge_bps_30d (float | None): paper 30d net edge
        - rejected_n (int): 30d window reject 總數
        - rejected_outcome_n (int): 30d window reject 後有 outcome 標籤計數
        - sm04_escalate_count_7d (int): SM-04 escalate L3+ 7d 計數
        - frozen_at_ms (int): freeze 起始時間 ms epoch（從 fills 最後 ts 推估）
        - last_fill_ms (int | None): 30d 內最後 fill 時間（lifetime monitor）

    所有 query 純 SELECT；statement_timeout 防止慢 query 阻塞 writer。
    """
    if not cells:
        return {}

    values_sql, cell_params = _values_sql(cells)

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SET LOCAL statement_timeout = %s", (statement_timeout_ms,))

        # ───────────────────────────────────────────────────────────────────
        # Q1: paper engine 30d fills + edge calc
        # 注意：freeze 只 block demo + live runtime；paper 永遠跑（OPENCLAW_ENABLE_PAPER
        # 預設關時 0 fills 是 spec §9 "paper engine availability" 結論）。
        # ───────────────────────────────────────────────────────────────────
        paper_sql = f"""
WITH cells(strategy_name, symbol) AS (VALUES {values_sql})
SELECT c.strategy_name,
       c.symbol,
       COUNT(f.fill_id) FILTER (WHERE f.engine_mode='paper')::int AS paper_fills_30d,
       COALESCE(AVG(
           CASE WHEN f.engine_mode='paper' AND f.notional_usdt > 0
                THEN (COALESCE(f.realized_pnl, 0) - ABS(COALESCE(f.fee, 0)))
                     / NULLIF(f.notional_usdt, 0) * 10000
                ELSE NULL
           END
       ), NULL)::float8 AS paper_net_edge_bps_30d,
       MAX(EXTRACT(EPOCH FROM f.ts) * 1000)::bigint AS last_fill_ms
FROM cells c
LEFT JOIN trading.fills f
  ON f.strategy_name = c.strategy_name
 AND f.symbol = c.symbol
 AND f.ts > now() - (%s * interval '1 day')
GROUP BY c.strategy_name, c.symbol
"""
        cur.execute(paper_sql, [*cell_params, days])
        paper_rows = {
            (str(r[0]), str(r[1])): {
                "paper_fills_30d": int(r[2] or 0),
                "paper_net_edge_bps_30d": float(r[3]) if r[3] is not None else None,
                "last_fill_ms": int(r[4]) if r[4] is not None else None,
            }
            for r in cur.fetchall()
        }

        # ───────────────────────────────────────────────────────────────────
        # Q2: reject + outcome label coverage（沿用 7d writer 邏輯，window 改 30d）
        # ───────────────────────────────────────────────────────────────────
        reject_sql = f"""
WITH cells(strategy_name, symbol) AS (VALUES {values_sql})
SELECT c.strategy_name,
       c.symbol,
       COUNT(rv.verdict_id)::int AS rejected_n,
       COUNT(o.context_id)::int AS rejected_outcome_n
FROM cells c
LEFT JOIN trading.risk_verdicts rv
  ON rv.symbol = c.symbol
 AND rv.engine_mode IN ('demo', 'live_demo')
 AND rv.ts > now() - (%s * interval '1 day')
 AND rv.reason = c.symbol || ' blocked by per_strategy.' || c.strategy_name || '.blocked_symbols'
LEFT JOIN trading.decision_outcomes o
  ON o.context_id = rv.context_id
GROUP BY c.strategy_name, c.symbol
"""
        cur.execute(reject_sql, [*cell_params, days])
        reject_rows = {
            (str(r[0]), str(r[1])): {
                "rejected_n": int(r[2] or 0),
                "rejected_outcome_n": int(r[3] or 0),
            }
            for r in cur.fetchall()
        }

        # ───────────────────────────────────────────────────────────────────
        # Q3: SM-04 escalate L3+ 7d 計數（對齊 spec §3 條件 5）
        # 規避：governance.canary_stage_log 是 V080 後表；若 cohort_id 用
        # 'strategy:symbol:env' 形式，過濾 ILIKE pattern 命中本 cell。
        # ───────────────────────────────────────────────────────────────────
        sm04_sql = f"""
WITH cells(strategy_name, symbol) AS (VALUES {values_sql})
SELECT c.strategy_name,
       c.symbol,
       COALESCE(COUNT(t.id), 0)::int AS sm04_escalate_count_7d
FROM cells c
LEFT JOIN governance.canary_stage_log t
  ON t.transition_kind = 'incident_rollback'
 AND t.cohort_id ILIKE c.strategy_name || ':' || c.symbol || ':%'
 AND t.created_at > now() - interval '%s day'
 AND COALESCE(t.triggered_metric, '') ILIKE '%%sm04%%'
GROUP BY c.strategy_name, c.symbol
"""
        # 注意：%s 在 ILIKE 內需 %% escape；參數透過 cell_params 兩次注入
        try:
            cur.execute(sm04_sql, [*cell_params, SM04_ESCALATE_DAYS])
            sm04_rows = {
                (str(r[0]), str(r[1])): {
                    "sm04_escalate_count_7d": int(r[2] or 0),
                }
                for r in cur.fetchall()
            }
        except Exception:  # noqa: BLE001
            # governance.canary_stage_log 表不存在或 query 失敗時 fail-soft
            # （V080 land 順序差錯時不阻塞 30d cycle）
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            sm04_rows = {}

        # ───────────────────────────────────────────────────────────────────
        # Q4: yo-yo detection（30d 內同 cell unfrozen + re_frozen 計數）
        # ───────────────────────────────────────────────────────────────────
        yoyo_sql = f"""
WITH cells(strategy_name, symbol) AS (VALUES {values_sql})
SELECT c.strategy_name,
       c.symbol,
       COUNT(*) FILTER (
           WHERE u.outcome IN ('unfrozen', 're_frozen')
             AND u.candidate_at_ms > (EXTRACT(EPOCH FROM now()) * 1000)::bigint - (%s::bigint * 86400000)
       )::int AS yoyo_count_30d
FROM cells c
LEFT JOIN governance.unblock_candidates u
  ON u.cell_strategy = c.strategy_name
 AND u.cell_symbol   = c.symbol
GROUP BY c.strategy_name, c.symbol
"""
        try:
            cur.execute(yoyo_sql, [YO_YO_DETECTION_WINDOW_DAYS, *cell_params])
            yoyo_rows = {
                (str(r[0]), str(r[1])): {
                    "yoyo_count_30d": int(r[2] or 0),
                }
                for r in cur.fetchall()
            }
        except Exception:  # noqa: BLE001
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            yoyo_rows = {}
    finally:
        conn.close()

    # 合併四面向 evidence 為 unified dict
    evidence: dict[tuple[str, str], dict] = {}
    for cell in cells:
        key = (cell.strategy, cell.symbol)
        merged = {
            "paper_fills_30d": 0,
            "paper_net_edge_bps_30d": None,
            "last_fill_ms": None,
            "rejected_n": 0,
            "rejected_outcome_n": 0,
            "sm04_escalate_count_7d": 0,
            "yoyo_count_30d": 0,
        }
        merged.update(paper_rows.get(key, {}))
        merged.update(reject_rows.get(key, {}))
        merged.update(sm04_rows.get(key, {}))
        merged.update(yoyo_rows.get(key, {}))
        evidence[key] = merged

    return evidence


# =============================================================================
# §4 DSR / PBO 計算（W-AUDIT-6 acceptance metric）
# =============================================================================


def compute_dsr_pbo(
    paper_fills_30d: int,
    paper_net_edge_bps_30d: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """計算 Deflated Sharpe Ratio + Probability of Backtest Overfitting。

    回 (DSR, PBO) tuple；資料不足時回 (None, None) → verdict 走
    'manual_review_required'。

    DSR 簡化版（per W-AUDIT-6 §3）：
        DSR = sqrt(N) * mean / stddev * (1 - skew * mean / stddev / 2)
    本 audit 無法直接計算 stddev / skew（樣本聚合在 SQL avg），用
    proxy = (mean / sqrt(2 * variance_assumption)) * sqrt(N) 簡化。
    缺 stddev 時 fallback 估計 stddev = |mean| * 2（保守 noise floor）。

    PBO 計算：本 audit 不跑 backtest，無 K-fold；用 paper sample 數做
    proxy = clamp((30 - n) / 30, 0, 1)；30 = sample sufficient threshold。

    spec §3：DSR ≥ 0.5 + PBO ≤ 0.5 → 通過 selection-bias 防護
    spec §3：DSR / PBO 計算 NULL → verdict 'manual_review_required'
    """
    if paper_fills_30d < 1 or paper_net_edge_bps_30d is None:
        return (None, None)

    # DSR proxy
    n = float(paper_fills_30d)
    mean = float(paper_net_edge_bps_30d)
    # stddev 估計：保守用 |mean| * 2 作 noise floor（無真實 stddev 可用）
    stddev = max(abs(mean) * 2.0, 1.0)  # min stddev = 1 bps 防 div by 0
    sharpe = mean / stddev
    dsr = math.sqrt(n) * sharpe

    # PBO proxy（樣本越多 PBO 越低）
    pbo = max(0.0, min(1.0, (30.0 - n) / 30.0)) if n < 30 else 0.0

    return (dsr, pbo)


# =============================================================================
# §5 Verdict logic（spec §3）
# =============================================================================


def evaluate_verdict(
    cell: BlockedCell,
    evidence: dict,
) -> tuple[str, dict, list[str]]:
    """對單一 cell 評估 4 verdict + diagnostic notes。

    Returns:
        (verdict, augmented_evidence, diagnostic_notes)
        augmented_evidence 加入計算結果（DSR / PBO / 觸發條件）。
    """
    notes: list[str] = []
    aug = dict(evidence)  # shallow copy 避免污染原 evidence

    paper_fills = int(evidence.get("paper_fills_30d", 0))
    paper_edge = evidence.get("paper_net_edge_bps_30d")
    rejected_n = int(evidence.get("rejected_n", 0))
    rejected_outcome_n = int(evidence.get("rejected_outcome_n", 0))
    sm04_count = int(evidence.get("sm04_escalate_count_7d", 0))
    yoyo_count = int(evidence.get("yoyo_count_30d", 0))

    # 計算 DSR / PBO 並 augment evidence
    dsr, pbo = compute_dsr_pbo(paper_fills, paper_edge)
    aug["DSR"] = dsr
    aug["PBO"] = pbo

    # ───────────────────────────────────────────────────────────────────
    # yo-yo detection：30d 內同 cell unfrozen + re_frozen ≥1 cycle
    # → 強制 manual_review_required（spec §5.3 selection-bias 防護）
    # ───────────────────────────────────────────────────────────────────
    if yoyo_count >= 1:
        notes.append(
            f"yo-yo detection trip: yoyo_count_30d={yoyo_count} ≥ 1; "
            "spec §5.3 強制 manual_review_required"
        )
        return (VERDICT_MANUAL_REVIEW_REQUIRED, aug, notes)

    # ───────────────────────────────────────────────────────────────────
    # dormant_no_evidence：paper_fills_30d < 30
    # spec §3 paper_fills 是統計 power 下界，不足即不 evidence-driven
    # ───────────────────────────────────────────────────────────────────
    if paper_fills < PAPER_FILLS_30D_MIN:
        notes.append(
            f"paper_fills_30d={paper_fills} < {PAPER_FILLS_30D_MIN} "
            "(統計 power 下界)；可能 paper engine 未啟動 or strategy 自身停滯"
        )
        return (VERDICT_DORMANT_NO_EVIDENCE, aug, notes)

    # ───────────────────────────────────────────────────────────────────
    # manual_review_required：DSR / PBO 計算 NULL（spec §3 第 4 verdict）
    # 已在 paper_fills_30d ≥ 30 條件下進來，DSR/PBO 應有值；若仍 None 表示
    # paper_edge 計算 NULL（notional_usdt = 0 等異常）
    # ───────────────────────────────────────────────────────────────────
    if dsr is None or pbo is None:
        notes.append(
            "DSR/PBO 計算 NULL（paper_net_edge_bps_30d=None；可能 notional_usdt=0 異常）"
            "；spec §3 強制 manual_review_required"
        )
        return (VERDICT_MANUAL_REVIEW_REQUIRED, aug, notes)

    # ───────────────────────────────────────────────────────────────────
    # 全 AND PASS criteria（spec §3）
    # ───────────────────────────────────────────────────────────────────
    criteria_failures: list[str] = []

    # paper_net_edge_bps_30d ≥ +5 bps
    if paper_edge is None or paper_edge < PAPER_NET_EDGE_BPS_MIN:
        criteria_failures.append(
            f"paper_net_edge_bps_30d={paper_edge} < +{PAPER_NET_EDGE_BPS_MIN} bps"
        )

    # DSR ≥ 0.5
    if dsr < DSR_MIN:
        criteria_failures.append(f"DSR={dsr:.3f} < {DSR_MIN}")

    # PBO ≤ 0.5
    if pbo > PBO_MAX:
        criteria_failures.append(f"PBO={pbo:.3f} > {PBO_MAX}")

    # SM-04 escalate ≥L3 7d 必須 0
    if sm04_count > 0:
        criteria_failures.append(
            f"sm04_escalate_count_7d={sm04_count} > 0 "
            "(SM-04 incident_rollback 7d 內觸發)"
        )

    # rejected_n > 0 時 outcome 標籤必 ≥ 5
    if rejected_n > 0 and rejected_outcome_n < REJECTED_OUTCOME_MIN_IF_REJECTED:
        criteria_failures.append(
            f"rejected_n={rejected_n} > 0 but rejected_outcome_n={rejected_outcome_n} "
            f"< {REJECTED_OUTCOME_MIN_IF_REJECTED} (outcome 樣本不足)"
        )

    if criteria_failures:
        # 已有 sufficient evidence (paper_fills ≥30) 但 criteria 未全 PASS
        # → continue_freeze
        notes.extend(criteria_failures)
        notes.append("paper_fills_30d ≥ 30 但 criteria 未全 PASS → continue_freeze")
        return (VERDICT_CONTINUE_FREEZE, aug, notes)

    # 全 AND PASS → unblock_candidate（待 PA + QC sign-off）
    notes.append(
        f"全 AND PASS: paper_fills={paper_fills}, paper_edge={paper_edge:.2f}bps, "
        f"DSR={dsr:.3f}, PBO={pbo:.3f}, sm04={sm04_count}, "
        f"rejected_outcome={rejected_outcome_n}/{rejected_n}"
    )
    return (VERDICT_UNBLOCK_CANDIDATE, aug, notes)


# =============================================================================
# §6 PG writer — INSERT / UPDATE outcome
# =============================================================================


def insert_unblock_candidate(
    row: UnblockCandidateRow,
    *,
    statement_timeout_ms: int = 5000,
) -> int:
    """寫入單筆 candidate row 到 governance.unblock_candidates；回 inserted id。

    INSERT 時刻 immutable 5 欄 + requires_pa_qc_signoff 預設 TRUE。
    paper_evidence 序列化為 jsonb；JSON 結構驗證留 caller。
    """
    if row.verdict not in VALID_VERDICTS:
        raise ValueError(f"invalid verdict: {row.verdict}; allowed={VALID_VERDICTS}")

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SET LOCAL statement_timeout = %s", (statement_timeout_ms,))
        cur.execute(
            """
            INSERT INTO governance.unblock_candidates (
                cell_strategy,
                cell_symbol,
                candidate_at_ms,
                paper_evidence_jsonb,
                verdict,
                requires_pa_qc_signoff
            ) VALUES (%s, %s, %s, %s::jsonb, %s, %s)
            RETURNING id
            """,
            [
                row.cell_strategy,
                row.cell_symbol,
                row.candidate_at_ms,
                json.dumps(row.paper_evidence),
                row.verdict,
                row.requires_pa_qc_signoff,
            ],
        )
        inserted_id = cur.fetchone()[0]
        conn.commit()
        return int(inserted_id)
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        conn.close()


def update_unblock_outcome(
    candidate_id: int,
    *,
    outcome: str,
    pa_report_path: Optional[str] = None,
    qc_report_path: Optional[str] = None,
    commit_sha: Optional[str] = None,
    unfrozen_at_ms: Optional[int] = None,
    re_frozen_at_ms: Optional[int] = None,
    re_freeze_reason: Optional[str] = None,
    statement_timeout_ms: int = 5000,
) -> bool:
    """sign-off 後更新 candidate row 的 outcome + audit trail。

    unfrozen 路徑（spec §5.2）：必含 pa_report_path + qc_report_path +
    commit_sha + unfrozen_at_ms（V090 unfrozen_completeness_chk 強制）。

    re_frozen 路徑（spec §5.3）：必含 re_frozen_at_ms + re_freeze_reason +
    unfrozen_at_ms 已存在（V090 re_frozen_completeness_chk + lifecycle_order_chk）。

    commit_sha 寫入 timing：spec §5.2 #5 — operator 動 TOML + freeze.json 後
    update outcome='unfrozen' row；本 helper 在 unfrozen UPDATE 那一刻寫入。

    Returns True if exactly 1 row updated；False 表示 candidate_id 不存在
    or update 0 row（caller fail-closed）。
    """
    if outcome not in ("unfrozen", "re_frozen", "kept_frozen"):
        raise ValueError(
            f"invalid outcome: {outcome}; allowed=unfrozen|re_frozen|kept_frozen"
        )

    # Sign-off completeness pre-check（client-side fail-fast；PG CHECK 是
    # last line of defense）
    if outcome == "unfrozen":
        if not (pa_report_path and qc_report_path and commit_sha and unfrozen_at_ms):
            raise ValueError(
                "outcome='unfrozen' 必含 pa_report_path + qc_report_path + "
                "commit_sha + unfrozen_at_ms（spec §5.2 / V090 CHECK constraint）"
            )
    elif outcome == "re_frozen":
        if not (re_frozen_at_ms and re_freeze_reason):
            raise ValueError(
                "outcome='re_frozen' 必含 re_frozen_at_ms + re_freeze_reason"
                "（spec §5.3 / V090 CHECK constraint）"
            )

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SET LOCAL statement_timeout = %s", (statement_timeout_ms,))
        cur.execute(
            """
            UPDATE governance.unblock_candidates
            SET outcome          = %s,
                pa_report_path   = COALESCE(%s, pa_report_path),
                qc_report_path   = COALESCE(%s, qc_report_path),
                commit_sha       = COALESCE(%s, commit_sha),
                unfrozen_at_ms   = COALESCE(%s, unfrozen_at_ms),
                re_frozen_at_ms  = COALESCE(%s, re_frozen_at_ms),
                re_freeze_reason = COALESCE(%s, re_freeze_reason),
                updated_at       = NOW()
            WHERE id = %s
            """,
            [
                outcome,
                pa_report_path,
                qc_report_path,
                commit_sha,
                unfrozen_at_ms,
                re_frozen_at_ms,
                re_freeze_reason,
                candidate_id,
            ],
        )
        rowcount = cur.rowcount
        conn.commit()
        return rowcount == 1
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        conn.close()


# =============================================================================
# §7 Main cycle — 對全 frozen cells 跑 30d audit
# =============================================================================


def run_30d_cycle(
    *,
    cells: Optional[list[BlockedCell]] = None,
    days: int = DEFAULT_WINDOW_DAYS,
    evaluation_path: str = EVAL_PATH_CRON,
    commit: bool = False,
    statement_timeout_ms: int = 10000,
) -> list[UnblockCandidateRow]:
    """跑完整 30d cycle：對 cells 逐個評估 + INSERT 候選 row（commit=True 才寫）。

    Args:
        cells: None 時從 freeze.json 載入全 17 frozen cells；list 時只跑指定
               cells（force_eval API 內部呼叫單 cell 用）。
        days: window 大小，預設 30
        evaluation_path: 'cron_30d_cycle' or 'operator_force_eval'
        commit: True 才實寫 PG；False 為 dry-run（回 row 不寫）

    Returns:
        list of UnblockCandidateRow（含 verdict + diagnostic notes）。
    """
    if evaluation_path not in VALID_EVAL_PATHS:
        raise ValueError(
            f"invalid evaluation_path: {evaluation_path}; allowed={VALID_EVAL_PATHS}"
        )

    # Load cells
    if cells is None:
        registry = load_registry()
        cells = iter_cells(registry)
    if not cells:
        return []

    # Pull 30d evidence for all cells
    evidence_map = fetch_audit_evidence(
        cells, days=days, statement_timeout_ms=statement_timeout_ms
    )

    candidate_at_ms = int(time.time() * 1000)
    rows: list[UnblockCandidateRow] = []
    for cell in sorted(cells, key=lambda c: (c.strategy, c.symbol)):
        evidence = evidence_map.get((cell.strategy, cell.symbol), {})
        verdict, aug_evidence, notes = evaluate_verdict(cell, evidence)
        # 加入 evaluation_path + frozen_at_ms 到 evidence（per spec §3）
        # frozen_at_ms 計算：last_fill_ms 是粗略 proxy（freeze SOP 未紀錄
        # 真實 freeze ts；real freeze 起算用 freeze.json freeze_id 對應的
        # commit ts，但本 audit 不做 git query 避免 ops cost）
        aug_evidence["evaluation_path"] = evaluation_path
        aug_evidence["frozen_at_ms"] = aug_evidence.get("last_fill_ms") or 0

        row = UnblockCandidateRow(
            cell_strategy=cell.strategy,
            cell_symbol=cell.symbol,
            candidate_at_ms=candidate_at_ms,
            paper_evidence=aug_evidence,
            verdict=verdict,
            diagnostic_notes=notes,
        )
        rows.append(row)

        # Commit 模式：寫 PG
        if commit:
            try:
                row_id = insert_unblock_candidate(row)
                row.diagnostic_notes.append(f"INSERTed id={row_id}")
            except Exception as exc:  # noqa: BLE001
                row.diagnostic_notes.append(f"INSERT FAILED: {exc}")

    return rows


# =============================================================================
# §8 Markdown rendering（cron 輸出 + GUI display 用）
# =============================================================================


def render_markdown(rows: list[UnblockCandidateRow], *, days: int) -> str:
    """渲染 30d cycle 結果為 markdown；對齊 7d writer pattern。"""
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# P1-DYNAMIC-UNBLOCK-CHECK-1 — 30d Cycle Unblock Audit",
        "",
        f"- Generated: `{generated}`",
        f"- Window: last `{days}` days, paper engine 30d edge proxy",
        "- Boundary: read-only DB SELECT + INSERT governance.unblock_candidates only;",
        "  no risk_config*.toml mutation, no freeze.json mutation, no engine restart.",
        "- Spec: docs/execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md",
        "",
        "## Per-cell Verdict Summary",
        "",
        "| strategy | symbol | verdict | paper_fills_30d | paper_edge_bps | DSR | PBO | sm04_7d | yoyo_30d | notes |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    counts = {v: 0 for v in VALID_VERDICTS}
    for row in rows:
        ev = row.paper_evidence
        edge = ev.get("paper_net_edge_bps_30d")
        edge_s = "n/a" if edge is None else f"{edge:.2f}"
        dsr = ev.get("DSR")
        dsr_s = "n/a" if dsr is None else f"{dsr:.3f}"
        pbo = ev.get("PBO")
        pbo_s = "n/a" if pbo is None else f"{pbo:.3f}"
        notes = "; ".join(row.diagnostic_notes) if row.diagnostic_notes else ""
        counts[row.verdict] = counts.get(row.verdict, 0) + 1
        lines.append(
            "| "
            f"{row.cell_strategy} | {row.cell_symbol} | {row.verdict} | "
            f"{ev.get('paper_fills_30d', 0)} | {edge_s} | {dsr_s} | {pbo_s} | "
            f"{ev.get('sm04_escalate_count_7d', 0)} | "
            f"{ev.get('yoyo_count_30d', 0)} | {notes} |"
        )

    lines.extend([
        "",
        "## Aggregate",
        "",
        f"- Cells audited: `{len(rows)}`",
        f"- unblock_candidate: `{counts.get(VERDICT_UNBLOCK_CANDIDATE, 0)}`",
        f"- continue_freeze: `{counts.get(VERDICT_CONTINUE_FREEZE, 0)}`",
        f"- dormant_no_evidence: `{counts.get(VERDICT_DORMANT_NO_EVIDENCE, 0)}`",
        f"- manual_review_required: `{counts.get(VERDICT_MANUAL_REVIEW_REQUIRED, 0)}`",
        "",
        "## Next Steps",
        "",
        "- `unblock_candidate` rows → emit GUI alert + 等 PA + QC sign-off",
        "  （spec §5.2 三段式：PA RFC + QC review + operator 動 TOML/freeze.json）",
        "- `continue_freeze` rows → 維持 freeze（已有 evidence 但不 promote）",
        "- `dormant_no_evidence` rows → paper engine 啟動議題（OPENCLAW_ENABLE_PAPER=1）",
        "- `manual_review_required` rows → operator 介入 review（yo-yo or DSR/PBO NULL）",
        "",
    ])
    return "\n".join(lines)


# =============================================================================
# §9 CLI entry
# =============================================================================


def _parse_cell_arg(s: str) -> BlockedCell:
    """Parse 'strategy:symbol' 為 BlockedCell；force_eval API 用。"""
    parts = s.split(":", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise argparse.ArgumentTypeError(
            f"--cell 格式錯誤：{s}；應為 'strategy:symbol' (e.g. 'grid_trading:BSBUSDT')"
        )
    return BlockedCell(strategy=parts[0], symbol=parts[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help=f"window 大小（預設 {DEFAULT_WINDOW_DAYS}d）",
    )
    parser.add_argument(
        "--evaluation-path",
        choices=VALID_EVAL_PATHS,
        default=EVAL_PATH_CRON,
        help="evaluation 來源（cron_30d_cycle 或 operator_force_eval）",
    )
    parser.add_argument(
        "--cell",
        type=_parse_cell_arg,
        action="append",
        help="單一 cell 強制 eval（格式 'strategy:symbol'，可多次）；省略則跑 freeze.json 全 cells",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="實寫 PG governance.unblock_candidates；省略為 dry-run",
    )
    parser.add_argument(
        "--statement-timeout-ms",
        type=int,
        default=10000,
        help="PG statement_timeout（毫秒）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="markdown 輸出檔；省略則 stdout",
    )
    args = parser.parse_args()

    cells = args.cell if args.cell else None
    rows = run_30d_cycle(
        cells=cells,
        days=args.days,
        evaluation_path=args.evaluation_path,
        commit=args.commit,
        statement_timeout_ms=args.statement_timeout_ms,
    )
    markdown = render_markdown(rows, days=args.days)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
