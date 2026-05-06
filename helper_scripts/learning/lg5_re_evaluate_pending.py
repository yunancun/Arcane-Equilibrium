#!/usr/bin/env python3
"""
MODULE_NOTE
模組目的：LG-5 §5.2 — 對既有 24 pending live promotion candidates 做
        bulk re-evaluation。對 ``schema_version != live_candidate_eval_v1``
        的 row 同步 synthesize ``demo_cost_baseline`` /
        ``demo_attribution_chain_ratio_by_strategy`` (從 healthcheck 歷史
        + MIT-S2-1 attribution 切片 fallback)，再 call
        ``review_live_candidate(candidate_id)``。每筆 outcome 寫 audit row
        至 ``learning.governance_audit_log``（含 ``defer`` / ``reject``）。

Module purpose: LG-5 §5.2 — bulk re-evaluation of existing pending live
                promotion candidates. For rows with
                ``schema_version != live_candidate_eval_v1``, synthesize
                ``demo_cost_baseline`` /
                ``demo_attribution_chain_ratio_by_strategy`` from
                healthcheck history + MIT-S2-1 attribution snapshots,
                write back to payload, then call
                ``review_live_candidate(candidate_id)``. Each outcome
                emits an audit row to ``learning.governance_audit_log``
                (including ``defer`` / ``reject``).

Usage / 用法：
    python3 helper_scripts/learning/lg5_re_evaluate_pending.py [--dry-run]
                                                              [--limit N]
                                                              [--verbose]

Spec source / 規格來源：
    docs/CCAgentWorkSpace/PA/workspace/reports/
        2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md §5.2

Expected outcome distribution (per MIT estimate, 24 pending):
    ~20% defer_data_insufficient
    ~48% reject_haircut_negative
    ~20% reject_cost_edge_ratio
    ~12% defer_attribution_chain_too_broken
    ~ 0% approve (live regime currently negative)

Idempotency / 冪等性：
    Re-running on already-reviewed candidates emits another audit row
    (review_live_candidate event) — by design (RFC §2.3 audit-every-call).
    Approved candidates whose ``decision_lease_id`` is already set are
    skipped (cannot double-grant lease).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# ── Ensure src import path / 確保 src import 路徑 ────────────────────────────
# This script is in srv/helper_scripts/learning/; the control_api_v1 package
# lives at srv/program_code/exchange_connectors/bybit_connector/control_api_v1/.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTROL_API_ROOT = _REPO_ROOT / "program_code" / "exchange_connectors" / "bybit_connector" / "control_api_v1"
if str(_CONTROL_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_ROOT))

logger = logging.getLogger("lg5_bulk_re_eval")

_TAKER_FEE_RATE: float = 0.00055
_MAKER_FEE_CUTOFF: float = 0.00040
_STRATEGY_ENTRY_FILL_PREDICATE: str = """
                  AND (f.entry_context_id IS NULL OR f.entry_context_id = '')
                  AND f.exit_reason IS NULL
                  AND f.order_id NOT LIKE 'oc_risk_%%'
"""


def _strategy_entry_fill_predicate() -> str:
    """SQL predicate for strategy-owned entry fills only. 僅篩 strategy entry fill。"""
    return _STRATEGY_ENTRY_FILL_PREDICATE


# ═══════════════════════════════════════════════════════════════════════════════
# Imports deferred to runtime (post sys.path injection)
# ═══════════════════════════════════════════════════════════════════════════════

def _lazy_imports():
    """Defer heavy imports until after sys.path injection.
    延遲 heavy import 到 sys.path 注入後。"""
    from app.db_pool import get_conn, put_conn  # noqa: WPS433
    from app.governance_hub_live_candidate_review import (  # noqa: WPS433
        EXPECTED_SCHEMA_VERSION,
        ReviewVerdict,
        review_live_candidate,
        _emit_audit_row,
    )
    return get_conn, put_conn, EXPECTED_SCHEMA_VERSION, ReviewVerdict, review_live_candidate, _emit_audit_row


# ═══════════════════════════════════════════════════════════════════════════════
# Backfill payload synthesis / 回填 payload 合成
# ═══════════════════════════════════════════════════════════════════════════════

def _synthesize_demo_cost_baseline(cur: Any, candidate_ts: Any) -> dict[str, Any]:
    """Synthesize demo_cost_baseline retroactively from trading.fills history.
    從 trading.fills 歷史回填 demo_cost_baseline。

    Best-effort — when historical [33]/[40] data is too thin for the
    candidate's creation time window, returns zeros (which the consumer
    will defer on data_insufficient).

    Returns dict mirror of mlde_demo_applier._compute_demo_cost_baseline
    output schema.
    """
    baseline: dict[str, Any] = {
        "as_of_ts": str(candidate_ts) if candidate_ts is not None else "",
        "engine_mode": "demo",
        "maker_fill_rate_7d": 0.0,
        "fee_drop_only_7d": 0.0,
        "avg_realized_net_bps_7d": 0.0,
        "avg_realized_fee_bps_7d": 0.0,
        "avg_realized_slippage_bps_7d": 0.0,
        "sample_count": 0,
        "source_healthchecks": ["[33]", "[40]"],
        "synthesized_by": "lg5_re_evaluate_pending.py",
    }
    if candidate_ts is None:
        return baseline
    try:
        cur.execute(
            """
            WITH entry_fills AS (
                SELECT
                    coalesce(nullif(f.fee_rate, 0), %s)::float8 AS effective_fee_rate,
                    CASE
                        WHEN lower(coalesce(f.liquidity_role, '')) = 'maker'
                          OR coalesce(nullif(f.fee_rate, 0), %s) <= %s
                        THEN 1 ELSE 0
                    END AS maker_like
                FROM trading.fills f
                WHERE f.ts > %s::timestamptz - INTERVAL '7 days'
                  AND f.ts <= %s::timestamptz
                  AND f.engine_mode IN ('demo', 'live_demo')
                  AND coalesce(f.strategy_name, '') <> ''
                  AND f.strategy_name NOT LIKE 'risk_close:%%'
                  AND f.strategy_name NOT LIKE 'strategy_close:%%'
                  AND f.strategy_name NOT LIKE 'ipc_close%%'
                  AND f.strategy_name NOT LIKE 'unattributed:%%'
                  AND coalesce(f.exit_source, '') = ''
            """ + _strategy_entry_fill_predicate() + """
            )
            SELECT count(*)::int, coalesce(sum(maker_like), 0)::int,
                   (coalesce(avg(effective_fee_rate), %s)::float8 * 10000.0)::float8
            FROM entry_fills
            """,
            (
                _TAKER_FEE_RATE,
                _TAKER_FEE_RATE,
                _MAKER_FEE_CUTOFF,
                candidate_ts,
                candidate_ts,
                _TAKER_FEE_RATE,
            ),
        )
        row = cur.fetchone()
        if row is not None:
            total = int(row[0]) if row[0] else 0
            maker_like = int(row[1]) if row[1] else 0
            avg_fee_bps = float(row[2]) if row[2] else 0.0
            baseline["sample_count"] = total
            if total > 0:
                baseline["maker_fill_rate_7d"] = maker_like / total
            baseline["avg_realized_fee_bps_7d"] = avg_fee_bps
            fee_drop = max(
                0.0,
                min(
                    1.0,
                    (_TAKER_FEE_RATE * 10_000.0 - avg_fee_bps)
                    / max(_TAKER_FEE_RATE * 10_000.0, 1e-12),
                ),
            )
            baseline["fee_drop_only_7d"] = fee_drop
    except Exception as exc:  # noqa: BLE001
        logger.warning("synthesize maker query failed cand_ts=%s err=%s",
                       candidate_ts, exc)

    try:
        cur.execute("SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL")
        view_exists = cur.fetchone()
    except Exception:  # noqa: BLE001
        view_exists = (False,)

    if view_exists and view_exists[0]:
        try:
            cur.execute(
                """
                SELECT coalesce(avg(net_bps_after_fee), 0.0)::float8,
                       coalesce(avg(slippage_bps), 0.0)::float8
                FROM learning.mlde_edge_training_rows
                WHERE ts > %s::timestamptz - INTERVAL '7 days'
                  AND ts <= %s::timestamptz
                  AND engine_mode IN ('demo', 'live_demo')
                  AND attribution_chain_ok
                  AND net_bps_after_fee IS NOT NULL
                """,
                (candidate_ts, candidate_ts),
            )
            row2 = cur.fetchone()
            if row2 is not None:
                baseline["avg_realized_net_bps_7d"] = float(row2[0]) if row2[0] else 0.0
                baseline["avg_realized_slippage_bps_7d"] = float(row2[1]) if row2[1] else 0.0
        except Exception as exc:  # noqa: BLE001
            logger.warning("synthesize net_bps query failed err=%s", exc)

    return baseline


def _synthesize_attribution_dict(cur: Any) -> dict[str, float]:
    """Synthesize per-strategy attribution chain ratio at write-back time.
    回填當下的 per-strategy attribution chain ratio。

    Pulls from current MLDE attribution log (no historical re-creation —
    candidate's creation-time attribution is unrecoverable, but current
    snapshot is acceptable for re-eval purposes per RFC §5.2 fallback).
    """
    five_strategies = ("grid_trading", "ma_crossover", "bb_breakout",
                       "bb_reversion", "funding_arb")
    result: dict[str, float] = {s: 0.0 for s in five_strategies}
    try:
        cur.execute("SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL")
        exists = cur.fetchone()
        if not (exists and exists[0]):
            return result
        cur.execute(
            """
            SELECT strategy_name,
                   sum(case when attribution_chain_ok then 1 else 0 end)::float8
                     / nullif(count(*), 0)::float8 AS ratio
            FROM learning.mlde_edge_training_rows
            WHERE ts > now() - INTERVAL '7 days'
              AND engine_mode IN ('demo', 'live_demo')
              AND strategy_name IS NOT NULL
            GROUP BY strategy_name
            """
        )
        rows = cur.fetchall()
        for row in rows:
            sname = str(row[0]) if row[0] else ""
            ratio = float(row[1]) if row[1] is not None else 0.0
            if sname in result:
                result[sname] = ratio
    except Exception as exc:  # noqa: BLE001
        logger.warning("synthesize attribution dict failed err=%s", exc)
    return result


def _backfill_payload(
    cur: Any,
    candidate_id: int,
    candidate_ts: Any,
    existing_payload: dict[str, Any],
    expected_schema_version: str,
) -> dict[str, Any]:
    """Backfill payload sub-keys to satisfy ``live_candidate_eval_v1``.
    回填 payload sub-key 至 ``live_candidate_eval_v1``。
    """
    new_payload = dict(existing_payload) if isinstance(existing_payload, dict) else {}
    new_payload["schema_version"] = expected_schema_version
    new_payload.setdefault("policy", "live_governed_promotion_candidate")
    new_payload.setdefault("application_type", "live_promotion_candidate")
    new_payload.setdefault("requires", ["GovernanceHub", "DecisionLease", "live_gates"])

    if not isinstance(new_payload.get("demo_cost_baseline"), dict):
        new_payload["demo_cost_baseline"] = _synthesize_demo_cost_baseline(cur, candidate_ts)

    if not isinstance(new_payload.get("demo_realized_window"), dict):
        # Best-effort; n_strategy_fills=0 → consumer R3 defer (acceptable).
        # 盡力回填；n_strategy_fills=0 → consumer R3 defer（可接受）。
        new_payload["demo_realized_window"] = {
            "start_ts": "",
            "end_ts": str(candidate_ts) if candidate_ts is not None else "",
            "n_fills": 0,
            "n_strategy_fills": 0,
            "window_days": 7,
            "synthesized_by": "lg5_re_evaluate_pending.py",
        }

    if not isinstance(new_payload.get("demo_attribution_chain_ratio_by_strategy"), dict):
        new_payload["demo_attribution_chain_ratio_by_strategy"] = _synthesize_attribution_dict(cur)

    new_payload.setdefault("demo_sample_count_strategy_cell", 0)
    new_payload.setdefault("backfilled_by_lg5_re_evaluate_pending", True)
    return new_payload


def _write_back_payload(cur: Any, candidate_id: int, payload: dict[str, Any]) -> None:
    """UPDATE candidate row's payload column.
    更新 candidate row 的 payload 欄位。"""
    cur.execute(
        """
        UPDATE learning.mlde_param_applications
        SET payload = %s::jsonb
        WHERE id = %s
        """,
        (json.dumps(payload, default=str), candidate_id),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Hub bootstrap / Hub 啟動
# ═══════════════════════════════════════════════════════════════════════════════

class _StubHub:
    """Minimal hub stub for bulk script when full GovernanceHub init not desired.
    精簡 hub stub — 批量執行不需完整 GovernanceHub 啟動。

    Round-2 MEDIUM-1 fix (RFC §5.2 line 430): the spec asks bulk re-eval to
    NOT auto-issue fresh leases for historical pending candidates — it does
    NOT ask us to force every verdict into ``reject_hard_veto``. Round-1
    incorrectly returned ``is_authorized()=False`` which masked all R1-R5 +
    R-meta verdicts behind R6 (auth_effective=False → reject_hard_veto).
    Correct behaviour:
      * ``acquire_lease`` returns None  → triggers
        ``defer_lease_acquisition_failed`` even when R1-R5 pass; preserves
        the real per-rule verdict in audit while declining lease.
      * ``is_authorized`` returns True  → lets R1-R6 + R-meta evaluate
        normally and surface true verdict distribution.

    Round-2 MEDIUM-1 修正（RFC §5.2 line 430）：spec 要的是「不自動發 lease」，
    不是「強制 reject_hard_veto」。Round-1 將 is_authorized 設 False 導致所有
    candidate 撞 R6 hard veto，遮蔽 R1-R5 + R-meta 真實 verdict。修法：
      * acquire_lease 回 None → 即使 R1-R5 全 pass 也走
        defer_lease_acquisition_failed；audit 仍保留真實的 R1-R5/R-meta 結果。
      * is_authorized 回 True → R1-R6 + R-meta 正常評估，verdict 分布真實。
    """

    def acquire_lease(self, *args, **kwargs):
        # lease=None forces defer_lease_acquisition_failed even on R1-R5 pass —
        # preserves real R1-R5/R-meta verdict in audit while declining lease
        # per RFC §5.2 line 430.
        # lease=None 即使 R1-R5 全 pass 也觸發 defer_lease_acquisition_failed —
        # audit 仍保留真實 R1-R5/R-meta verdict，符合 RFC §5.2 line 430。
        return None

    def is_authorized(self):
        # Returns True so review_live_candidate evaluates R1-R6 + R-meta
        # against real data; R6 only vetoes on real conditions
        # (7 negative days / catastrophic maker / [22] FAIL / auth invalid).
        # 回 True 讓 review_live_candidate 用真實資料評 R1-R6 + R-meta；
        # R6 只在真實條件成立才 veto。
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# Main bulk runner / 主批量執行
# ═══════════════════════════════════════════════════════════════════════════════

def run_bulk_re_evaluation(
    *,
    dry_run: bool = False,
    limit: int = 100,
    verbose: bool = False,
) -> dict[str, Any]:
    """Iterate pending live candidates and emit verdict + audit per RFC §5.2.
    遍歷 pending live candidates，per RFC §5.2 emit verdict + audit row。

    Returns summary dict {processed, by_decision, by_reason, errors}.
    """
    (
        get_conn,
        put_conn,
        EXPECTED_SCHEMA_VERSION,
        ReviewVerdict,
        review_live_candidate,
        _emit_audit_row,
    ) = _lazy_imports()

    summary: dict[str, Any] = {
        "processed": 0,
        "skipped_already_leased": 0,
        "by_decision": Counter(),
        "by_reason": Counter(),
        "errors": [],
    }

    conn = get_conn()
    if conn is None:
        logger.error("DB connection unavailable; aborting")
        summary["errors"].append("no_db_conn")
        return summary

    candidates: list[tuple[int, Any, dict[str, Any], Any]] = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ts, payload, decision_lease_id
                FROM learning.mlde_param_applications
                WHERE engine_mode = 'live'
                  AND status = 'candidate'
                  AND application_type = 'live_promotion_candidate'
                  AND decision_lease_id IS NULL
                ORDER BY ts ASC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        for row in rows:
            cand_id = int(row[0])
            cand_ts = row[1]
            raw_payload = row[2]
            if isinstance(raw_payload, str):
                try:
                    raw_payload = json.loads(raw_payload)
                except Exception:  # noqa: BLE001
                    raw_payload = {}
            if not isinstance(raw_payload, dict):
                raw_payload = {}
            lease = row[3]
            candidates.append((cand_id, cand_ts, raw_payload, lease))
    except Exception as exc:  # noqa: BLE001
        logger.error("Initial fetch failed: %s", exc)
        summary["errors"].append(f"fetch_failed:{exc}")
        put_conn(conn)
        return summary

    logger.info("Bulk re-eval: %d candidates fetched (dry_run=%s)",
                len(candidates), dry_run)

    # Backfill phase / 回填階段
    for cand_id, cand_ts, payload, lease in candidates:
        if lease:
            summary["skipped_already_leased"] += 1
            continue
        sv = str(payload.get("schema_version") or "")
        if sv != EXPECTED_SCHEMA_VERSION:
            try:
                with conn.cursor() as cur:
                    new_payload = _backfill_payload(
                        cur, cand_id, cand_ts, payload, EXPECTED_SCHEMA_VERSION
                    )
                    if not dry_run:
                        _write_back_payload(cur, cand_id, new_payload)
                if not dry_run:
                    conn.commit()
                logger.info("Backfilled payload cand=%d schema_was=%r", cand_id, sv)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Backfill failed cand=%d err=%s", cand_id, exc)
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001
                    pass
                summary["errors"].append(f"backfill_failed:{cand_id}:{exc}")

    put_conn(conn)

    if dry_run:
        logger.info("--dry-run: skipping review_live_candidate calls")
        return summary

    # Review phase / 評估階段
    hub = _StubHub()
    for cand_id, cand_ts, _payload, lease in candidates:
        if lease:
            continue
        try:
            verdict = review_live_candidate(
                hub,
                cand_id,
                decided_by="GovernanceHub.review_live_candidate.bulk_re_evaluation",
            )
            summary["processed"] += 1
            summary["by_decision"][verdict.decision] += 1
            summary["by_reason"][verdict.reason] += 1
            if verbose:
                logger.info(
                    "cand=%d → %s/%s (rule_failures=%s)",
                    cand_id, verdict.decision, verdict.reason, verdict.rule_failures,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("review_live_candidate raised cand=%d err=%s", cand_id, exc)
            summary["errors"].append(f"review_failed:{cand_id}:{exc}")
            # Per PM #4: every outcome (including review failure) MUST emit
            # audit. Use a defer/audit_write_failed-like marker.
            # 每筆 outcome (含 review 失敗) 必發 audit。
            try:
                fallback_verdict = ReviewVerdict(
                    decision="defer",
                    reason="defer_audit_write_failed",
                    rule_failures=["review_raised_exception"],
                    expected_net_bps_demo=0.0,
                    expected_net_bps_live_adjusted=None,
                    expected_net_bps_deflated=None,
                    cost_regime_ratio=None,
                    cost_regime_ratio_clamped=None,
                    psr_value=None,
                    psr_n_samples=None,
                    psr_skew=None,
                    psr_kurt=None,
                    sr_0_deflation=None,
                    v_pending_net_bps=None,
                    lease_ttl_ms=None,
                    lease_revoke_triggers=[],
                    decided_at_ts=0,
                    decided_by="GovernanceHub.review_live_candidate.bulk_re_evaluation",
                    payload_snapshot={"raised_exception": str(exc)},
                )
                _emit_audit_row("review_live_candidate", cand_id, fallback_verdict)
            except Exception:  # noqa: BLE001
                pass

    return summary


def _print_summary(summary: dict[str, Any]) -> None:
    """Pretty-print summary for operator inspection.
    為 operator 友善列印摘要。"""
    print("\n=== LG-5 bulk re-evaluation summary ===")
    print(f"Processed:               {summary['processed']}")
    print(f"Skipped (already leased): {summary['skipped_already_leased']}")
    print("\nBy decision:")
    for k, v in summary["by_decision"].most_common():
        print(f"  {k:<10}  {v}")
    print("\nBy reason:")
    for k, v in summary["by_reason"].most_common():
        print(f"  {k:<55}  {v}")
    if summary["errors"]:
        print(f"\nErrors ({len(summary['errors'])}):")
        for e in summary["errors"][:10]:
            print(f"  {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / 命令列介面
# ═══════════════════════════════════════════════════════════════════════════════

def _build_parser() -> argparse.ArgumentParser:
    """Build CLI argparse parser / 建構 CLI argparse parser。"""
    p = argparse.ArgumentParser(
        description="LG-5 bulk re-evaluation of pending live promotion candidates"
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Synthesize payload but skip writes + review calls")
    p.add_argument("--limit", type=int, default=100,
                   help="Max candidates to process (default 100)")
    p.add_argument("--verbose", action="store_true",
                   help="Per-candidate verdict log")
    return p


def main(argv: list[str] | None = None) -> int:
    """Main entry / 主入口。"""
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    summary = run_bulk_re_evaluation(
        dry_run=args.dry_run,
        limit=args.limit,
        verbose=args.verbose,
    )
    _print_summary(summary)
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
