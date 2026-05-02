#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────
# MODULE_NOTE
# 模組目的：funding_arb 1B 樣本累積彙總 — 2026-05-02 → 2026-05-16
#          (deploy + 14d) 期間 demo funding_arb fill round-trip 統計，
#          判斷 2A 棄策略 trigger 是否到（n≥30 + net bps 顯著負）。
#          僅產生 Markdown 報告，**不執行任何 DB write、不觸發任何 action**。
# Module purpose: funding_arb 1B sample accrual summary — 14 days post-3C
#                 deploy (2026-05-02 → 2026-05-16) demo funding_arb
#                 round-trip statistics. Verdict on whether the "2A
#                 deprecate funding_arb" trigger is met (n≥30 +
#                 materially negative net bps). Read-only Markdown
#                 report; no DB write, no auto-action.
#
# 關聯記憶 / Refs:
#   - memory/project_2026_05_02_p0_sqlx_hash_drift.md
#   - memory/project_funding_arb_v2_deprecation_path.md
#   - TODO.md「📅 排程提醒」section
#
# 執行 / Usage:
#   bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh
#   bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh --quiet
#
# Exit codes:
#   0 = decision rendered (continue / deprecate / adjust threshold)
#   1 = anomalous data (e.g. SL > 5% notional → SL gate bug)
#   2 = DB connection / fatal SQL error
# ─────────────────────────────────────────────────────────
"""funding_arb 14d (2026-05-02 → 2026-05-16) sample accrual + 2A trigger evaluation.

讀取 trading.fills（demo + funding_arb），按 entry_context_id JOIN 配對
round-trip，聚合 total fires / win rate / gross+net bps / max single-trade
loss / 3% SL 上限驗證；最後輸出對 2A 棄策略 trigger 的判斷文字 + next action。

Reuses helper_scripts/db/passive_wait_healthcheck/db.py for DSN building.
Read-only — no DB write.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# 重用 passive_wait_healthcheck.db 的 _get_conn（DSN 解析 + env fallback）
# Reuse passive_wait_healthcheck.db._get_conn for DSN resolution + env fallback.
_HERE = Path(__file__).resolve().parent
_PARENT = _HERE.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

# fmt: off
from passive_wait_healthcheck.db import _get_conn  # noqa: E402
# fmt: on


# ============================================================================
# Constants
# ============================================================================

# 3C TOML 真實生效時刻（與 2026-05-09 audit 相同）
DEPLOY_UTC = "2026-05-02 17:42:00+00"
ACCRUAL_DAYS = 14  # 2026-05-02 → 2026-05-16

# 2A 棄策略 trigger thresholds
DEPRECATE_MIN_N = 30
DEPRECATE_NET_BPS_NEGATIVE_THRESHOLD = -5.0  # net_bps < -5bps 視為「顯著為負」

# 3% SL hard cap + 5% slippage buffer
SL_HARD_CAP_PCT = 0.03
SL_SLIPPAGE_BUFFER_PCT = 0.05


# ============================================================================
# Result dataclass
# ============================================================================


@dataclass
class FundingArbStats:
    """Aggregated funding_arb round-trip statistics for the 14d window."""

    n_round_trips: int = 0      # 完整 round-trip 數（entry + matched close）
    n_wins: int = 0              # realized_pnl > 0 的 round-trip 數
    gross_bps_sum: float = 0.0   # gross PnL 總和（USD，未扣 fee）
    fee_sum: float = 0.0         # 進+出 fee 總和（USD）
    notional_sum: float = 0.0    # entry notional 總和（USD，分母）
    min_realized_pnl: float = 0.0  # 最差單筆 realized_pnl
    max_loss_notional_pct: float = 0.0  # 最差單筆 abs(pnl)/notional
    n_over_3pct: int = 0
    n_over_5pct: int = 0


# ============================================================================
# SQL — 一次拉所有 round-trip 配對
# ============================================================================

_AGG_SQL = """
WITH entries AS (
  SELECT context_id, ts AS entry_ts, price AS entry_price,
         qty AS entry_qty, fee AS entry_fee, symbol, side
  FROM trading.fills
  WHERE engine_mode = 'demo'
    AND strategy_name = 'funding_arb'
    AND ts >= %(deploy)s::timestamptz
    AND ts <  %(deploy)s::timestamptz + interval '14 days'
),
closes AS (
  SELECT entry_context_id AS entry_cid, ts AS close_ts,
         price AS close_price, qty AS close_qty, fee AS close_fee,
         realized_pnl,
         row_number() OVER (
           PARTITION BY entry_context_id ORDER BY ts
         ) AS rn
  FROM trading.fills
  WHERE engine_mode = 'demo'
    AND entry_context_id IS NOT NULL
    AND entry_context_id <> ''
    AND ts >= %(deploy)s::timestamptz
    AND ts <  %(deploy)s::timestamptz + interval '14 days'
    AND (strategy_name LIKE 'risk_close:%%'
         OR strategy_name LIKE 'strategy_close:%%'
         OR exit_reason IS NOT NULL)
),
first_close AS (SELECT * FROM closes WHERE rn = 1),
round_trips AS (
  SELECT e.context_id, e.entry_price, e.entry_qty, e.entry_fee,
         c.close_price, c.close_fee, c.realized_pnl,
         (e.entry_price * e.entry_qty) AS notional
  FROM entries e
  JOIN first_close c ON c.entry_cid = e.context_id
)
SELECT
  COUNT(*)::int AS n_round_trips,
  COUNT(*) FILTER (WHERE realized_pnl > 0)::int AS n_wins,
  COALESCE(SUM(realized_pnl), 0)::float8 AS gross_pnl_sum,
  COALESCE(SUM(entry_fee + close_fee), 0)::float8 AS fee_sum,
  COALESCE(SUM(notional), 0)::float8 AS notional_sum,
  COALESCE(MIN(realized_pnl), 0)::float8 AS min_realized_pnl,
  COALESCE(
    MAX(CASE WHEN notional > 0
             THEN abs(realized_pnl) / notional
             ELSE NULL END), 0
  )::float8 AS max_loss_pct,
  COUNT(*) FILTER (
    WHERE notional > 0
      AND abs(realized_pnl) / notional > %(sl_cap)s
  )::int AS n_over_3pct,
  COUNT(*) FILTER (
    WHERE notional > 0
      AND abs(realized_pnl) / notional > %(slip_buf)s
  )::int AS n_over_5pct
FROM round_trips
"""


def fetch_stats(cur) -> tuple[FundingArbStats | None, str | None]:
    """Run the aggregate SQL and return (stats, error).

    執行聚合 SQL，回 ``(stats, None)`` 或 ``(None, error_string)``。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    try:
        cur.execute(
            _AGG_SQL,
            {
                "deploy": DEPLOY_UTC,
                "sl_cap": SL_HARD_CAP_PCT,
                "slip_buf": SL_SLIPPAGE_BUFFER_PCT,
            },
        )
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"

    if not row:
        return FundingArbStats(), None

    (
        n_round_trips, n_wins, gross_pnl_sum, fee_sum, notional_sum,
        min_pnl, max_loss_pct, n_over_3pct, n_over_5pct,
    ) = row

    return FundingArbStats(
        n_round_trips=int(n_round_trips or 0),
        n_wins=int(n_wins or 0),
        gross_bps_sum=float(gross_pnl_sum or 0.0),
        fee_sum=float(fee_sum or 0.0),
        notional_sum=float(notional_sum or 0.0),
        min_realized_pnl=float(min_pnl or 0.0),
        max_loss_notional_pct=float(max_loss_pct or 0.0),
        n_over_3pct=int(n_over_3pct or 0),
        n_over_5pct=int(n_over_5pct or 0),
    ), None


# ============================================================================
# Decision logic — 2A trigger evaluation
# ============================================================================


@dataclass
class Decision:
    """Final 2A decision — verdict + recommended next action."""

    decision_label: str   # "DEPRECATE" / "CONTINUE" / "JUDGEMENT" / "INSUFFICIENT"
    next_action: str      # 推薦下一步 / recommended next step
    rationale: str        # 判斷理由（中英）/ rationale (zh + en)


def evaluate_2a_trigger(stats: FundingArbStats) -> Decision:
    """Evaluate the 2A "deprecate funding_arb" trigger.

    Trigger criteria:
      - n ≥ DEPRECATE_MIN_N (30) AND net_bps ≤ NEGATIVE_THRESHOLD (-5bps)
        → DEPRECATE （棄策略）
      - n < DEPRECATE_MIN_N → INSUFFICIENT （續收樣本）
      - n ≥ DEPRECATE_MIN_N AND net_bps ∈ (-5, +5) → JUDGEMENT （操作 judgement）
      - n ≥ DEPRECATE_MIN_N AND net_bps > +5 → CONTINUE （正 edge，留用）
    """
    if stats.n_round_trips == 0:
        return Decision(
            decision_label="INSUFFICIENT",
            next_action="續收樣本 / continue accrual",
            rationale=(
                f"0 round-trips in 14d post-deploy window — "
                f"funding_arb may be already disabled or no entry signal. "
                f"檢查 demo TOML active=true 與 strategist 是否仍嘗試發單。"
            ),
        )

    if stats.notional_sum <= 0:
        return Decision(
            decision_label="JUDGEMENT",
            next_action="人工檢查 notional 計算 / manual investigation",
            rationale=(
                f"notional_sum={stats.notional_sum:.2f} ≤ 0 但 n={stats.n_round_trips}; "
                f"資料異常（entry price/qty 寫入問題？）"
            ),
        )

    net_pnl = stats.gross_bps_sum - 0.0   # gross_pnl already net of fee in fills.realized_pnl
    # 注意：trading.fills.realized_pnl 在 close fill 上已是 gross PnL；
    # 進+出 fee 額外從 entry.fee + close.fee 抓。net = realized_pnl_sum - fee_sum
    # （round_trip 視角：realized_pnl 是該 close 對 entry 的 P&L，未扣自身 fee）
    # NOTE: trading.fills.realized_pnl on close fill represents gross P&L of
    # the round-trip; entry+close fee come from .fee column. Net = sum(pnl) - sum(fee)
    net_after_fee = stats.gross_bps_sum - stats.fee_sum
    net_bps = (net_after_fee / stats.notional_sum) * 10000.0

    if stats.n_round_trips < DEPRECATE_MIN_N:
        return Decision(
            decision_label="INSUFFICIENT",
            next_action="續收樣本 / continue accrual; revisit at next window",
            rationale=(
                f"n={stats.n_round_trips} < {DEPRECATE_MIN_N}; "
                f"net_bps={net_bps:+.2f}bps preview only, sample too small for 2A trigger."
            ),
        )

    # n ≥ 30 — 判斷 net_bps 方向
    if net_bps <= DEPRECATE_NET_BPS_NEGATIVE_THRESHOLD:
        return Decision(
            decision_label="DEPRECATE",
            next_action=(
                "提案 2A：demo TOML `[per_strategy.funding_arb].active = false`"
                "（棄策略）。請走 PA 流程；若 14d net 顯著為負代表 entry edge 已死，"
                "3% SL 救不回 / 3% SL cannot save it."
            ),
            rationale=(
                f"n={stats.n_round_trips} ≥ {DEPRECATE_MIN_N} AND "
                f"net_bps={net_bps:+.2f}bps ≤ {DEPRECATE_NET_BPS_NEGATIVE_THRESHOLD}bps "
                f"(materially negative). 14d 樣本足 + net edge 顯著為負 = 2A trigger 命中。"
            ),
        )

    if net_bps < 5.0:
        return Decision(
            decision_label="JUDGEMENT",
            next_action=(
                "操作員 judgement：(a) 改 entry threshold 收緊樣本品質，"
                "(b) 收 21d 再評，(c) 棄策略。建議 (a) 並 21d 再 audit。"
            ),
            rationale=(
                f"n={stats.n_round_trips} ≥ {DEPRECATE_MIN_N} BUT net_bps={net_bps:+.2f}bps "
                f"is neutral (in [-5, +5] band). 樣本足夠但 edge 不顯著，"
                f"非自動 trigger，留 operator 決策空間。"
            ),
        )

    # net_bps ≥ +5
    return Decision(
        decision_label="CONTINUE",
        next_action=(
            "保留 funding_arb；3C SL hard cap (3%) 看似不傷 edge。"
            "下一輪 audit 視同續觀察 / next audit window for ongoing monitoring."
        ),
        rationale=(
            f"n={stats.n_round_trips} ≥ {DEPRECATE_MIN_N} AND net_bps={net_bps:+.2f}bps "
            f">= +5bps (positive edge). 棄策略 trigger 不命中。"
        ),
    )


# ============================================================================
# Render
# ============================================================================


def render_markdown(stats: FundingArbStats, decision: Decision) -> str:
    """Render summary table + 2A trigger judgement text.

    輸出 1 個 Markdown summary table + 1 段判斷文字（含推薦 next action）。
    """
    if stats.notional_sum > 0:
        gross_bps = (stats.gross_bps_sum / stats.notional_sum) * 10000.0
        net_bps = ((stats.gross_bps_sum - stats.fee_sum) / stats.notional_sum) * 10000.0
        win_rate = (
            (stats.n_wins / stats.n_round_trips * 100.0)
            if stats.n_round_trips else 0.0
        )
    else:
        gross_bps = 0.0
        net_bps = 0.0
        win_rate = 0.0

    max_loss_pct = stats.max_loss_notional_pct * 100.0

    lines: list[str] = []
    lines.append("# 2026-05-16 · funding_arb 14d sample accrual + 2A trigger audit")
    lines.append("")
    lines.append(f"- **Window**: `[{DEPLOY_UTC}, deploy + {ACCRUAL_DAYS}d)` "
                 f"(2026-05-02 17:42 UTC → 2026-05-16 17:42 UTC)")
    lines.append("- **Engine mode**: `demo`")
    lines.append(f"- **Strategy filter**: `strategy_name = 'funding_arb'` "
                 f"(round-trip via `entry_context_id` JOIN)")
    lines.append("")
    lines.append("## Aggregate stats")
    lines.append("")
    lines.append("| Metric | Value | Note |")
    lines.append("|---|---|---|")
    lines.append(f"| Total round-trips | {stats.n_round_trips} | "
                 f"trigger threshold n ≥ {DEPRECATE_MIN_N} |")
    lines.append(f"| Win rate | {win_rate:.1f}% | wins={stats.n_wins} |")
    lines.append(f"| Gross bps | {gross_bps:+.2f} | "
                 f"sum(realized_pnl)/sum(notional) × 10000 |")
    lines.append(f"| Net bps after fee | {net_bps:+.2f} | "
                 f"(realized_pnl_sum − fee_sum) / notional_sum × 10000 |")
    lines.append(f"| Min realized_pnl (worst single fill) | "
                 f"{stats.min_realized_pnl:+.2f} USD | absolute USD |")
    lines.append(f"| Max single-trade abs(loss)/notional | {max_loss_pct:.2f}% | "
                 f"3% hard cap; >5% = SL gate bug |")
    lines.append(f"| Fills exceeding 3% notional | {stats.n_over_3pct} | "
                 f"slippage zone (≤5% acceptable) |")
    lines.append(f"| Fills exceeding 5% notional | {stats.n_over_5pct} | "
                 f"**must be 0** — SL gate failure if > 0 |")
    lines.append(f"| Total notional traded | {stats.notional_sum:+.2f} USD | "
                 f"denominator for bps |")
    lines.append(f"| Total fee paid | {stats.fee_sum:+.2f} USD | entry + close |")
    lines.append("")
    lines.append("## 2A deprecation trigger evaluation")
    lines.append("")
    lines.append(f"**Decision**: `{decision.decision_label}`")
    lines.append("")
    lines.append(f"**Rationale**: {decision.rationale}")
    lines.append("")
    lines.append(f"**Next action**: {decision.next_action}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("**Trigger criteria (reference)**:")
    lines.append(f"- `DEPRECATE` ⇐ n ≥ {DEPRECATE_MIN_N} AND "
                 f"net_bps ≤ {DEPRECATE_NET_BPS_NEGATIVE_THRESHOLD:.1f}bps")
    lines.append(f"- `INSUFFICIENT` ⇐ n < {DEPRECATE_MIN_N}")
    lines.append(f"- `JUDGEMENT` ⇐ n ≥ {DEPRECATE_MIN_N} AND "
                 f"net_bps ∈ ({DEPRECATE_NET_BPS_NEGATIVE_THRESHOLD:.1f}, +5.0)")
    lines.append(f"- `CONTINUE` ⇐ n ≥ {DEPRECATE_MIN_N} AND net_bps ≥ +5.0bps")
    return "\n".join(lines)


def render_quiet(stats: FundingArbStats, decision: Decision) -> str:
    """Quiet mode: 1-line decision summary + key numbers."""
    if stats.notional_sum > 0:
        net_bps = ((stats.gross_bps_sum - stats.fee_sum) / stats.notional_sum) * 10000.0
    else:
        net_bps = 0.0
    win_rate = (
        (stats.n_wins / stats.n_round_trips * 100.0)
        if stats.n_round_trips else 0.0
    )
    return (
        f"[{decision.decision_label}] n={stats.n_round_trips}, "
        f"win={win_rate:.1f}%, net={net_bps:+.2f}bps, "
        f"max_loss_pct={stats.max_loss_notional_pct * 100:.2f}%, "
        f">5%_fills={stats.n_over_5pct}\n"
        f"  → {decision.next_action}"
    )


# ============================================================================
# main
# ============================================================================


def main() -> int:
    """Entry point — fetch stats, evaluate trigger, render report.

    Exit codes:
      0 = decision rendered (any of DEPRECATE / INSUFFICIENT / JUDGEMENT / CONTINUE)
      1 = anomalous data (e.g. SL gate bug — fills > 5% notional)
      2 = DB connection / fatal SQL error
    """
    parser = argparse.ArgumentParser(
        description="2026-05-16 funding_arb 14d sample accrual + 2A trigger evaluation "
        "(read-only; no DB write)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="只印 decision 1 行 / Only print decision summary line",
    )
    args = parser.parse_args()

    try:
        conn = _get_conn()
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] DB connect failed: {exc}", file=sys.stderr)
        return 2

    try:
        with conn.cursor() as cur:
            stats, err = fetch_stats(cur)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if err is not None or stats is None:
        print(f"[FATAL] aggregate query failed: {err}", file=sys.stderr)
        return 2

    decision = evaluate_2a_trigger(stats)

    if args.quiet:
        print(render_quiet(stats, decision))
    else:
        print(render_markdown(stats, decision))

    # Exit 1 only on data anomaly (SL gate bug indicator).
    # 唯有 SL gate bug indicator (>5% notional fills) 觸發 exit 1。
    if stats.n_over_5pct > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
