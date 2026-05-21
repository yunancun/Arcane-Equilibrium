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
#   1 = anomalous data (max_loss_pct > effective_SL + slippage_buffer
#       → SL gate failure；effective_SL 動態讀 TOML)
#   2 = DB connection / fatal SQL error
# ─────────────────────────────────────────────────────────
"""funding_arb 14d (2026-05-02 → 2026-05-16) sample accrual + 2A trigger evaluation.

讀取 trading.fills（demo + funding_arb），按 entry_context_id JOIN 配對
round-trip，聚合 total fires / win rate / gross+net bps / max single-trade
loss / SL 上限驗證；最後輸出對 2A 棄策略 trigger 的判斷文字 + next action。

Reuses helper_scripts/db/passive_wait_healthcheck/db.py for DSN building.
Read-only — no DB write.

────────────────────────────────────────────────────────────────────────────
SL_HARD_CAP_PCT 治理註記（P3-AUDIT-SCRIPT-STALE-CONST · 2026-05-21）
────────────────────────────────────────────────────────────────────────────
2026-05-02 首版本曾以 ``SL_HARD_CAP_PCT = 0.03`` 對齊「3C demo TOML
funding_arb override 3% SL」設定；W-AUDIT-6 (2026-05-09) 後該
per-strategy override 已從 demo TOML 移除，funding_arb effective SL gate
退化為 global ``limits.stop_loss_max_pct`` (25% / dyn_stop floor 25 ×
0.25 = 6.25% per fill)。FA F2 RCA (2026-05-21) 指出該 audit script 用
stale 0.03 觸發「6.29% loss/notional → SL gate failure」**假警報**：
此 audit script 不應再 hardcode 0.03，需動態讀當前 TOML。

修正：``SL_HARD_CAP_PCT`` 改為 module-load 時呼叫
``_load_sl_hard_cap_pct()`` 讀 ``settings/risk_control_rules/risk_config_demo.toml``：
優先 ``per_strategy.funding_arb.stop_loss_max_pct_override``（若未來
重啟 override 自動 pick up），否則回退 ``limits.stop_loss_max_pct``。

WARNING（歷史 cross-ref）：若被 audit 的 fill 落在 W-AUDIT-6 commit
(2026-05-09) 之前，TOML 仍包含 funding_arb 3% override，當期 effective
SL gate 才是 3%。本動態讀只反映**當前** TOML，**不重建歷史**。如需歷史
audit，必須以 ``git log -p settings/risk_control_rules/risk_config_demo.toml``
做 commit timeline cross-ref，本 script 不負責此交叉檢。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# tomllib (3.11+) or tomli fallback / TOML 解析模組（3.11+ 內建，否則回退 tomli）
try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - Python <3.11 fallback
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]

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

# ────────────────────────────────────────────────────────────────────────
# SL 觀測 / gate 閾值
#
# - SL_OBSERVE_BUCKET_PCT (0.03)：歷史 funding_arb 3% override 殘留的觀測
#   bucket，純供 ``n_over_3pct`` SQL FILTER 統計 (slippage zone 入門)。
#   非當前 effective SL gate，不可作為「gate failure」判定。
# - SL_SLIPPAGE_BUFFER_PCT (0.05)：歷史 5% 觀測 bucket，用於 ``n_over_5pct``
#   FILTER，亦純觀測 — 真正 gate failure 判定由
#   ``SL_HARD_CAP_PCT`` (動態) 加 slippage buffer 推導。
# - SL_HARD_CAP_PCT：動態讀 ``risk_config_demo.toml``，反映**當前 effective**
#   SL gate (W-AUDIT-6 後 funding_arb override 已移除 → 回退至
#   ``limits.stop_loss_max_pct`` = 25%)。若 funding_arb override 未來重啟，
#   ``_load_sl_hard_cap_pct()`` 會自動 pick up override 值。
# ────────────────────────────────────────────────────────────────────────
SL_OBSERVE_BUCKET_PCT = 0.03  # 純觀測 bucket，非 effective SL gate
SL_SLIPPAGE_BUFFER_PCT = 0.05  # 純觀測 bucket，非 effective SL gate


def _load_sl_hard_cap_pct() -> float:
    """從 risk_config_demo.toml 動態讀取 funding_arb SL hard cap (純小數比例)。

    優先級：
      1. ``per_strategy.funding_arb.stop_loss_max_pct_override`` (若存在)
      2. ``limits.stop_loss_max_pct`` (global fallback)

    為什麼：W-AUDIT-6 (2026-05-09) 後 funding_arb per-strategy SL override
    已從 demo TOML 移除，effective SL gate = global ``stop_loss_max_pct``
    = 25%。本函數讓 audit script 不再 hardcode 過期的 3%，避免 FA F2 RCA
    一樣的「stale const 假警報」。若 tomllib 不可用 (Python <3.11 且無
    tomli)，回退 ``STALE_REFERENCE_2026_05_02 = 0.03`` 並 stderr 警告。

    回傳：純小數比例 (e.g. 0.25 表示 25%)；TOML 內以百分比寫，本函數
    /100 轉換。
    """
    # 容錯沙箱：tomllib 不存在時退回 stale const 並 stderr 警告
    if tomllib is None:  # pragma: no cover - env-dependent
        print(
            "[WARN] tomllib unavailable (Python <3.11 且無 tomli) — "
            "回退 STALE_REFERENCE_2026_05_02 = 0.03；當前 effective SL "
            "gate 未經驗證，請升級 Python 或安裝 tomli",
            file=sys.stderr,
        )
        return 0.03  # STALE_REFERENCE_2026_05_02

    toml_path = (
        Path(__file__).resolve().parents[3]
        / "settings"
        / "risk_control_rules"
        / "risk_config_demo.toml"
    )
    with toml_path.open("rb") as f:
        cfg = tomllib.load(f)

    # 優先讀 funding_arb per-strategy override
    per_strategy = cfg.get("per_strategy", {}).get("funding_arb", {})
    override = per_strategy.get("stop_loss_max_pct_override")
    if override is not None:
        return float(override) / 100.0  # TOML 百分比 → 純小數

    # 回退 global limits
    return float(cfg["limits"]["stop_loss_max_pct"]) / 100.0


# Module-load 時讀一次；audit 為 short-lived script，不需要 reload
SL_HARD_CAP_PCT = _load_sl_hard_cap_pct()


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
                # sl_cap / slip_buf 為純觀測 bucket，與 effective SL gate
                # (SL_HARD_CAP_PCT) 解耦；不可改用 effective value，否則
                # n_over_3pct / n_over_5pct 計數 bucket 邊界改變失去歷史
                # 可比性。Effective gate failure 判定走 exit_code 1 邏輯。
                "sl_cap": SL_OBSERVE_BUCKET_PCT,
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
        effective_sl_pct = SL_HARD_CAP_PCT * 100.0
        return Decision(
            decision_label="DEPRECATE",
            next_action=(
                "提案 2A：demo TOML `[per_strategy.funding_arb].active = false`"
                "（棄策略）。請走 PA 流程；若 14d net 顯著為負代表 entry edge 已死，"
                f"當前 effective SL gate ({effective_sl_pct:.1f}%) 救不回。"
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
    effective_sl_pct = SL_HARD_CAP_PCT * 100.0
    return Decision(
        decision_label="CONTINUE",
        next_action=(
            f"保留 funding_arb；effective SL gate ({effective_sl_pct:.1f}%) "
            "看似不傷 edge。下一輪 audit 視同續觀察。"
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

    # effective SL gate（動態讀 TOML 結果）+ effective + slippage buffer
    effective_sl_pct = SL_HARD_CAP_PCT * 100.0
    effective_sl_plus_buf_pct = (SL_HARD_CAP_PCT + SL_SLIPPAGE_BUFFER_PCT) * 100.0
    observe_bucket_pct = SL_OBSERVE_BUCKET_PCT * 100.0
    slippage_buffer_pct = SL_SLIPPAGE_BUFFER_PCT * 100.0

    lines: list[str] = []
    lines.append("# 2026-05-16 · funding_arb 14d sample accrual + 2A trigger audit")
    lines.append("")
    lines.append(f"- **Window**: `[{DEPLOY_UTC}, deploy + {ACCRUAL_DAYS}d)` "
                 f"(2026-05-02 17:42 UTC → 2026-05-16 17:42 UTC)")
    lines.append("- **Engine mode**: `demo`")
    lines.append(f"- **Strategy filter**: `strategy_name = 'funding_arb'` "
                 f"(round-trip via `entry_context_id` JOIN)")
    lines.append(f"- **Effective SL gate (dynamic from `risk_config_demo.toml`)**: "
                 f"`{effective_sl_pct:.1f}%` "
                 f"(W-AUDIT-6 後 funding_arb override 已移除，回退 global "
                 f"`limits.stop_loss_max_pct`)")
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
                 f"effective SL gate {effective_sl_pct:.1f}%; "
                 f">{effective_sl_plus_buf_pct:.1f}% (effective+buf) = SL gate failure |")
    lines.append(f"| Fills exceeding {observe_bucket_pct:.0f}% notional "
                 f"(observe bucket) | {stats.n_over_3pct} | "
                 f"歷史觀測 bucket，非當前 gate threshold |")
    lines.append(f"| Fills exceeding {slippage_buffer_pct:.0f}% notional "
                 f"(observe bucket) | {stats.n_over_5pct} | "
                 f"歷史觀測 bucket，非當前 gate threshold |")
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
      1 = anomalous data (max_loss_pct > effective_SL + slippage_buffer →
          SL gate failure；effective_SL 動態讀 ``risk_config_demo.toml``)
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

    # 治理註記（P3-AUDIT-SCRIPT-STALE-CONST · 2026-05-21）：
    # 舊邏輯硬編碼 ``n_over_5pct > 0`` 觸發 SL gate failure，但 5% 是 stale
    # 觀測 bucket，與當前 effective SL gate (動態讀 TOML) 解耦。FA F2 RCA
    # 之所以誤判 6.29% fill = SL gate failure，根因正是該寫死 5% claim。
    # 改：以「max_loss_pct > effective_SL + slippage_buffer」為 gate
    # failure 判定，effective_SL 從 TOML 動態讀。
    effective_gate_failure_threshold = SL_HARD_CAP_PCT + SL_SLIPPAGE_BUFFER_PCT
    if stats.max_loss_notional_pct > effective_gate_failure_threshold:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
