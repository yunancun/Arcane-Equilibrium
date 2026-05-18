#!/usr/bin/env python3
"""[63] close_maker_fallback_audit — audit 完整性 (NULL ladder + enum allowlist)。

MODULE_NOTE:
  AMD-2026-05-15-02 v0.6 §4.1 + spec §8.1 規範的 [63] healthcheck standalone
  入口。檢查兩件事：
    (a) ``close_maker_fallback_reason`` enum allowlist 完整性 — 任何不在 V094
        spec §2.1.2 line 124-134 10-value allowlist 內的值 = FAIL
        （V094 CHECK constraint 應在 PG 層阻擋，本 check 是 second-line
        defense + audit）
    (b) NULL ladder ratio — ``close_maker_attempt=TRUE`` 但 ``fallback_reason``
        IS NULL 且 fill 是 closed_by_market 的 rate 階梯
        （per Consensus-MF-3 + AC-6 + AC-16）：
          PASS ≤ 0.1% / WARN 0.1-1.0% / FAIL > 1.0%

  Safety path 3 enum (``fast_escalate_safety_upgrade`` /
  ``not_attempted_safety_path`` / ``engine_shutdown_safety``) **不算 NULL**
  per spec §8.1 line 552-555 + V094 spec §2.1.2 line 156 — 它們是 fail-closed
  走 market 的審計簽名。

  與 ``passive_wait_healthcheck.checks_close_maker_audit.check_close_maker_fallback_null_ladder``
  ([72] slot) SQL 語意對齊；JSONB completeness 子檢查（``close_initial_limit_price``
  / ``close_final_fill_price`` / ``close_maker_eligible_reason``）也帶入，但 [62-65]
  prompt 主視窗仍以 fallback enum + NULL ladder 為 primary verdict driver。

CLI:
  python3 63_close_maker_fallback_audit.py [--window-secs 604800] \\
        [--engine-mode demo,live_demo] [--pass-null-rate 0.001] \\
        [--warn-null-rate 0.01] [--write-file PATH] [--text]

Exit codes:
  0 = PASS / INSUFFICIENT_SAMPLE
  1 = WARN / FAIL（enum 非法 = FAIL；NULL ladder 超 1% = FAIL）
  2 = PG connect error
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _common import (  # noqa: E402
    EXIT_FAIL,
    EXIT_PASS,
    FALLBACK_REASONS,
    SAFETY_FALLBACK_REASONS,
    VERDICT_FAIL,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_PASS,
    VERDICT_WARN,
    build_argparser,
    configure_logging,
    connect_pg,
    emit_result,
)


def _parse_args() -> argparse.Namespace:
    parser = build_argparser(
        name="63_close_maker_fallback_audit",
        description=(
            "[63] close_maker_fallback_audit — enum allowlist + NULL ladder verdict"
        ),
    )
    parser.add_argument(
        "--pass-null-rate",
        type=float,
        default=0.001,
        help="PASS upper bound for NULL rate (default 0.001 = 0.1%% per Consensus-MF-3)",
    )
    parser.add_argument(
        "--warn-null-rate",
        type=float,
        default=0.01,
        help="WARN upper bound (FAIL beyond); default 0.01 = 1.0%% per Consensus-MF-3",
    )
    parser.add_argument(
        "--min-sample",
        type=int,
        default=5,
        help="Minimum attempts to compute NULL ladder (default 5)",
    )
    return parser.parse_args()


def _verdict_from_null_rate(
    ratio: float,
    pass_rate: float,
    warn_rate: float,
) -> str:
    if ratio <= pass_rate:
        return VERDICT_PASS
    if ratio <= warn_rate:
        return VERDICT_WARN
    return VERDICT_FAIL


def run(
    cur,
    window_secs: int,
    engine_modes: list[str],
    pass_rate: float,
    warn_rate: float,
    min_sample: int,
) -> dict:
    # (1) Enum 分布 — 含 NULL bucket
    cur.execute(
        """
        SELECT
            COALESCE(close_maker_fallback_reason, '<NULL>') AS reason,
            COUNT(*)::int AS n
        FROM trading.fills
        WHERE close_maker_attempt = TRUE
          AND ts > NOW() - (%s::int * INTERVAL '1 second')
          AND engine_mode = ANY(%s::text[])
        GROUP BY 1
        ORDER BY n DESC, reason
        """,
        (window_secs, engine_modes),
    )
    enum_rows = list(cur.fetchall() or [])

    enum_distribution: list[dict] = []
    illegal_reasons: list[str] = []
    n_attempts = 0
    n_null = 0
    n_safety = 0
    for row in enum_rows:
        reason = row[0]
        count = int(row[1] or 0)
        n_attempts += count
        is_safety = reason in SAFETY_FALLBACK_REASONS
        if reason == "<NULL>":
            n_null += count
        if is_safety:
            n_safety += count
        is_legal = (reason == "<NULL>") or (reason in FALLBACK_REASONS)
        if not is_legal:
            illegal_reasons.append(f"{reason}(n={count})")
        enum_distribution.append({
            "reason": reason,
            "count": count,
            "is_safety_path": is_safety,
            "is_legal_enum": is_legal,
        })

    # (2) NULL ladder — 排除 safety path
    # spec §8.1 line 547-555：分母 = close_maker_attempt=TRUE AND NOT safety；
    # 分子 = 該分母 AND fallback_reason IS NULL（maker 沒成功成交但又無 fallback
    # 標記 = audit 漏寫）。spec line 549 ``fill_status='closed_by_market'`` 限定
    # 是 fail-closed safety hint；trading.fills 沒 fill_status 欄，但用
    # ``close_maker_fallback_reason IS NULL`` 已足夠抓「audit 漏寫」。
    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE close_maker_attempt = TRUE
                  AND (
                    close_maker_fallback_reason IS NULL
                    OR NOT (close_maker_fallback_reason = ANY(%s::text[]))
                  )
            )::int AS not_safety_total,
            COUNT(*) FILTER (
                WHERE close_maker_attempt = TRUE
                  AND close_maker_fallback_reason IS NULL
                  AND (
                    NOT (details ? 'close_initial_limit_price')
                    OR NOT (details ? 'close_final_fill_price')
                    OR NOT (details ? 'close_maker_eligible_reason')
                  )
            )::int AS null_audit_missing,
            COUNT(*) FILTER (
                WHERE close_maker_attempt = TRUE
                  AND close_maker_fallback_reason IS NULL
            )::int AS null_count,
            COUNT(*) FILTER (
                WHERE close_maker_attempt = TRUE
                  AND close_maker_fallback_reason IS NULL
                  AND details ? 'close_initial_limit_price'
                  AND details ? 'close_final_fill_price'
                  AND details ? 'close_maker_eligible_reason'
            )::int AS null_audit_complete
        FROM trading.fills
        WHERE close_maker_attempt = TRUE
          AND ts > NOW() - (%s::int * INTERVAL '1 second')
          AND engine_mode = ANY(%s::text[])
        """,
        (list(SAFETY_FALLBACK_REASONS), window_secs, engine_modes),
    )
    row = cur.fetchone() or (0, 0, 0, 0)
    not_safety_total = int(row[0] or 0)
    null_audit_missing = int(row[1] or 0)
    null_count = int(row[2] or 0)
    null_audit_complete = int(row[3] or 0)

    # NULL rate = NULL count 占 not_safety_total 比；audit 漏寫率輔助診斷
    if not_safety_total > 0:
        null_rate = null_count / not_safety_total
        audit_missing_rate = null_audit_missing / not_safety_total
    else:
        null_rate = 0.0
        audit_missing_rate = 0.0

    # (3) Verdict 計算
    if illegal_reasons:
        # V094 CHECK constraint 應已擋住；若 healthcheck 看到 illegal value =
        # constraint drift 或被 ALTER 過 = FAIL 強信號（per AC-6 完整性）
        ladder_verdict = VERDICT_FAIL
        verdict_note = f"illegal enum values: {illegal_reasons}"
    elif n_attempts < min_sample:
        ladder_verdict = VERDICT_INSUFFICIENT_SAMPLE
        verdict_note = f"n_attempts={n_attempts} < min_sample={min_sample}"
    else:
        ladder_verdict = _verdict_from_null_rate(null_rate, pass_rate, warn_rate)
        verdict_note = (
            f"null_rate={null_rate:.5f} vs pass≤{pass_rate} / warn≤{warn_rate}"
        )

    return {
        "metric": "close_maker_fallback_audit",
        "check_id": "[63]",
        "spec": "AMD-2026-05-15-02 §4.1 / spec §8.1 Consensus-MF-3",
        "window_secs": window_secs,
        "engine_modes": engine_modes,
        "thresholds": {
            "pass_null_rate": pass_rate,
            "warn_null_rate": warn_rate,
            "min_sample": min_sample,
        },
        "n_attempts": n_attempts,
        "n_null_fallback_reason": null_count,
        "n_safety_path": n_safety,
        "not_safety_total": not_safety_total,
        "null_rate": round(null_rate, 6),
        "null_audit_missing": null_audit_missing,
        "null_audit_complete": null_audit_complete,
        "audit_missing_rate": round(audit_missing_rate, 6),
        "enum_distribution": enum_distribution,
        "illegal_reasons": illegal_reasons,
        "verdict": ladder_verdict,
        "verdict_note": verdict_note,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    configure_logging()
    args = _parse_args()

    conn = connect_pg()
    try:
        with conn.cursor() as cur:
            result = run(
                cur,
                window_secs=args.window_secs,
                engine_modes=[m.strip() for m in args.engine_mode.split(",") if m.strip()],
                pass_rate=args.pass_null_rate,
                warn_rate=args.warn_null_rate,
                min_sample=args.min_sample,
            )
    finally:
        conn.close()

    emit_result(result, write_file=args.write_file, text_mode=args.text)

    if result["verdict"] in (VERDICT_FAIL, VERDICT_WARN):
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
