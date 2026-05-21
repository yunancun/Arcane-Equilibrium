#!/usr/bin/env python3
"""[68] phys_lock_gate4_distribution — phys_lock gate4 trigger 分布 observability。

MODULE_NOTE:
  P2-PHYS-LOCK-72-HEALTHCHECK（FA round 1 #5 衍生 C6 OQ-C6-2 follow-up，
  2026-05-21）的 healthcheck standalone 入口。設計目的 = 區分**0-fire-natural**
  vs **0-fire-router-bug**，前者不需 action（policy 設計 sparse），後者立即升
  P1 ticket（emit 活但 close path 路斷）。

  Slot 編號決策（PA 拍板）：取 ``[68]`` —— canary `[62-67]` 連續占用後自然
  接續；passive_wait namespace 已用 `[68] portfolio_resting`，**完全不同
  domain**（前者 leverage chain semantic / 後者 phys_lock micro-profit lock
  trigger distribution），物理分離 + `__init__.py` MODULE_NOTE 明標 namespace
  邊界已是 R2 [66] 範本治理（見 `_common` package docstring）。

  Production wiring（PA 2026-05-21 grep 驗證 FA C6 §2 全 chain）：
    - emit：``exit_features/v2.rs:359`` → ``PhysicalDecision::Lock(
      "phys_lock_gate4_stale_roc_neg")``；giveback 對應 line:344/351/455/491/
      507/543/586/800/860/889。
    - risk routing：``risk_checks.rs:410-413`` route physical lock decision。
    - step：``step_6_risk_checks.rs:218-275`` build_risk_close_tag wrap。
    - maker policy：``maker_price.rs:99/104`` close_maker_price_policy lookup。
    - 最終寫入 ``trading.fills.exit_reason`` (strip ``risk_close:`` prefix 後
      變 ``"phys_lock_gate4_giveback"`` / ``"phys_lock_gate4_stale_roc_neg"``)
      + 寫入 ``details.close_maker_eligible_reason`` (maker-side 路徑簽名)。

  Schema 真相（PA 2026-05-21 grep INSERT INTO trading.fills statement 確認；
  與 V094 ADR-0028 對齊）：
    - ``trading.fills.exit_reason`` (V033, free-text TEXT) — emit 後字串為
      ``phys_lock_gate4_giveback`` / ``phys_lock_gate4_stale_roc_neg`` (lowercase)
    - ``trading.fills.close_maker_attempt`` (V094, BOOLEAN) — true 表示 close
      path 走 maker-first
    - ``trading.fills.close_maker_fallback_reason`` (V094, TEXT enum) — IS NULL
      表示 maker leg 成交（per [62] [63] convention）
    - ``trading.fills.details`` (JSONB) — ``close_maker_eligible_reason`` key 由
      ``trading_writer.rs:1399`` 反射確認；passive_wait [72] check 已使用

  Verdict ladder（per §2.2 spec；spec §4 acceptance criteria）：
    - INSUFFICIENT_SAMPLE：14d window 內 ``n < 5``（自然 sparse；不阻 deploy）
    - PASS：``gate4_giveback n > 0 AND close_maker_attempts > 0``
      （policy alive + close path 通）
    - WARN：``gate4_stale_roc_neg n = 0 AND gate4_giveback n ≥ 10``
      （router 缺口疑似；30d 內仍 0 升 FAIL）
    - FAIL：``gate4_stale_roc_neg n > 0 AND close_maker_attempts = 0``
      （policy alive 但 close path 不接通；**P1 ticket**）

CLI:
  python3 68_phys_lock_gate4_distribution.py [--window-secs 1209600] \\
        [--engine-mode demo,live_demo] \\
        [--insufficient-sample-threshold 5] \\
        [--warn-giveback-threshold 10] \\
        [--write-file PATH] [--text]

  預設 ``--window-secs 1209600`` = 14d（per FA C6 OQ-C6-2 建議 window）。

Exit codes:
  0 = PASS / INSUFFICIENT_SAMPLE（後者不阻 deploy）
  1 = WARN or FAIL
  2 = PG connect error

Reference:
  - spec: docs/execution_plan/2026-05-21--p2_phys_lock_72_healthcheck_spec.md
  - FA C6 audit: docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-20--...
  - ADR-0028: docs/adr/0028-close-maker-fallback-reason-dead-enum-reservation.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# 允許 standalone script + module 同時被呼叫
# stdlib import 之後加 sys.path 是為了讓 ``python3 68_phys_lock_gate4_distribution.py``
# 直接執行也能 import 同目錄 _common；package import 走 ``__init__.py`` 不受影響
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _common import (  # noqa: E402
    EXIT_FAIL,
    EXIT_PASS,
    VERDICT_FAIL,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_PASS,
    VERDICT_WARN,
    build_argparser,
    configure_logging,
    connect_pg,
    emit_result,
    severity_max,
    split_engine_modes,
)

# ───────────────────────────────────────────────────────────────────────────
# Default window + threshold（per spec §2.2 + §5.1）
# ───────────────────────────────────────────────────────────────────────────

# 14d window per FA C6 OQ-C6-2 建議；phys_lock 事件 sparse 需較長 window 累積
DEFAULT_WINDOW_SECS_14D: int = 14 * 24 * 3600

# n < 5 → INSUFFICIENT_SAMPLE（per spec §2.2）；保守值，避免 sparse 環境誤判
DEFAULT_INSUFFICIENT_SAMPLE_THRESHOLD: int = 5

# gate4_giveback n ≥ 10 + gate4_stale_roc_neg n = 0 → WARN（per spec §2.2）
# 10 是「足夠多 giveback 事件已觸發，stale_roc_neg 仍 0 = router 缺口疑似」門檻
DEFAULT_WARN_GIVEBACK_THRESHOLD: int = 10


# ───────────────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = build_argparser(
        name="68_phys_lock_gate4_distribution",
        description=(
            "[68] phys_lock_gate4_distribution healthcheck — "
            "P2-PHYS-LOCK-72-HEALTHCHECK natural vs router-bug 區分量度 "
            "(FA C6 OQ-C6-2 follow-up)"
        ),
        default_window_secs=DEFAULT_WINDOW_SECS_14D,
    )
    parser.add_argument(
        "--insufficient-sample-threshold",
        type=int,
        default=DEFAULT_INSUFFICIENT_SAMPLE_THRESHOLD,
        help=(
            f"n < threshold → INSUFFICIENT_SAMPLE "
            f"(default {DEFAULT_INSUFFICIENT_SAMPLE_THRESHOLD} per spec §2.2)"
        ),
    )
    parser.add_argument(
        "--warn-giveback-threshold",
        type=int,
        default=DEFAULT_WARN_GIVEBACK_THRESHOLD,
        help=(
            f"gate4_giveback n ≥ threshold + stale_roc_neg n = 0 → WARN "
            f"(default {DEFAULT_WARN_GIVEBACK_THRESHOLD} per spec §2.2)"
        ),
    )
    return parser.parse_args()


# ───────────────────────────────────────────────────────────────────────────
# Verdict aggregation（per spec §2.2 multi-cell aggregation logic）
# ───────────────────────────────────────────────────────────────────────────


def _aggregate_verdict_per_engine(
    cells_for_engine: list[dict],
    insufficient_sample_threshold: int,
    warn_giveback_threshold: int,
) -> str:
    """對單一 engine_mode 的 cells 計算 verdict。

    邏輯 ladder（PA 2026-05-21 IMPL refine — 修正 spec §2.2 PASS/WARN 順序 bug；
    OQ-C6-2 核心訴求是「prevent natural vs router-bug 混淆」，原 spec WARN 條件
    `stale_roc=0 AND giveback>=10` 會把所有 natural sparse 環境誤升 WARN）：

      1. FAIL（最優先）：has_stale_roc + stale_roc_close_attempts == 0
         policy alive 但 close path 不通 — 立即 P1 ticket
      2. PASS：has_giveback + giveback_close_attempts > 0 + n>=threshold
         policy alive + close path 通；**stale_roc 0 fire 視為 natural sparse**
         不沖淡 PASS（per spec §1 reframe — 0-fire-natural 是預期狀態，
         本 14d window healthcheck 無能力區分 vs 0-fire-router-bug）
      3. WARN（弱訊號）：has_giveback + giveback_n >= warn_giveback_threshold +
         giveback_close_attempts == 0
         giveback alive 但 close path 完全沒 attempts — 與 FAIL 為對稱訊號
         （stale_roc 看不到 → giveback path 觀察為 close path 健康代理；
         若 giveback 也 0 attempts → router 缺口疑似但 stale_roc 還 sparse 沒佐證）
      4. INSUFFICIENT_SAMPLE（兜底）：natural sparse / n < threshold

    為什麼移除 spec §2.2 原 WARN 條件 `stale_roc=0 AND giveback>=10`：
      - phys_lock_gate4_stale_roc_neg 的 trigger 條件本身嚴苛（per FA C6
        spec 缺 SLA 的根本訴求 — emit_features/v2.rs:359 需 stale ROC neg
        雙重條件），14d window 自然 0 fire 是預期
      - 若按原 WARN 條件，所有 demo 環境（giveback 30 + stale_roc 自然 0）
        都會升 WARN，與「natural sparse 不阻 deploy」的 spec §1 原則矛盾
      - **router 缺口疑似** 的真正訊號 = 「giveback close path 也不通」
        （即 stale_roc + giveback 同步看不到 close attempts），這才是 spec
        §1 OQ-C6-2 真實訴求

    為什麼 FAIL 仍保留 stale_roc 條件：
      - FAIL = 「我們 *確實* 看到 stale_roc fire 了（即 emit_features 在 emit），
        但 close path 0 attempts」→ 確定 routing bug
      - 這條件可在 14d window 內成立（即使 stale_roc 只 1 fire 也算），與 PASS
        條件對稱獨立
    """
    has_giveback = False
    has_stale_roc = False
    giveback_n = 0
    giveback_close_attempts_sum = 0
    stale_roc_close_attempts_sum = 0

    for cell in cells_for_engine:
        kind = cell.get("phys_lock_kind")
        n = int(cell.get("n", 0) or 0)
        close_attempts = int(cell.get("close_maker_attempts", 0) or 0)
        if kind == "gate4_giveback" and n > 0:
            has_giveback = True
            giveback_n = max(giveback_n, n)
            giveback_close_attempts_sum += close_attempts
        elif kind == "gate4_stale_roc_neg" and n > 0:
            has_stale_roc = True
            stale_roc_close_attempts_sum += close_attempts

    # FAIL（最優先）：stale_roc alive 但 close path 不通（policy 活但 router 斷）
    if has_stale_roc and stale_roc_close_attempts_sum == 0:
        return VERDICT_FAIL
    # PASS：giveback alive + close path 通 + 樣本量達標
    # （stale_roc 0 fire 視 natural sparse 不沖淡）
    if (
        has_giveback
        and giveback_close_attempts_sum > 0
        and giveback_n >= insufficient_sample_threshold
    ):
        return VERDICT_PASS
    # WARN（弱訊號）：giveback 多但 close path 0 attempts（與 FAIL 對稱訊號）
    if (
        has_giveback
        and giveback_n >= warn_giveback_threshold
        and giveback_close_attempts_sum == 0
    ):
        return VERDICT_WARN
    # INSUFFICIENT_SAMPLE：natural sparse / n < threshold
    return VERDICT_INSUFFICIENT_SAMPLE


# ───────────────────────────────────────────────────────────────────────────
# Run
# ───────────────────────────────────────────────────────────────────────────


def run(
    cur,
    window_secs: int,
    engine_modes: list[str],
    insufficient_sample_threshold: int = DEFAULT_INSUFFICIENT_SAMPLE_THRESHOLD,
    warn_giveback_threshold: int = DEFAULT_WARN_GIVEBACK_THRESHOLD,
) -> dict:
    """執行 SQL + verdict 計算，回傳 result dict。

    SQL 語意（per spec §2.1）：
      - 母體 = 14d window 內任一 phys_lock_* 路徑寫入的 fill（exit_reason 直
        match OR details.close_maker_eligible_reason match）
      - 分群 = engine_mode × phys_lock_kind（CASE WHEN 三 bucket：
        gate4_giveback / gate4_stale_roc_neg / other_phys_lock）
      - 每組量度：n / close_maker_attempts / close_maker_fills

    SQL OR-condition 雙條件（per spec §8 push back 點 3）：
      (1) exit_reason LIKE 'phys_lock_%'  — close path 完成後寫入的 final reason
      (2) details.close_maker_eligible_reason LIKE 'phys_lock_%'  — maker_price.rs
          寫入的 entry-side eligible reason
      兩處不一定 same row 同時 present（close path 邏輯可能只寫一處），故 OR。
    """
    cur.execute(
        """
        SELECT
            engine_mode,
            CASE
              WHEN exit_reason LIKE 'phys_lock_gate4_giveback%%' THEN 'gate4_giveback'
              WHEN exit_reason LIKE 'phys_lock_gate4_stale_roc_neg%%' THEN 'gate4_stale_roc_neg'
              ELSE 'other_phys_lock'
            END AS phys_lock_kind,
            COUNT(*)::int AS n,
            COUNT(*) FILTER (WHERE close_maker_attempt = TRUE)::int AS close_maker_attempts,
            COUNT(*) FILTER (
                WHERE close_maker_attempt = TRUE
                  AND close_maker_fallback_reason IS NULL
            )::int AS close_maker_fills
        FROM trading.fills
        WHERE ts > NOW() - (%s::int * INTERVAL '1 second')
          AND (
              exit_reason LIKE 'phys_lock_%%'
              OR details->>'close_maker_eligible_reason' LIKE 'phys_lock_%%'
          )
          AND engine_mode = ANY(%s::text[])
        GROUP BY engine_mode, phys_lock_kind
        ORDER BY engine_mode, phys_lock_kind
        """,
        (window_secs, engine_modes),
    )
    rows = list(cur.fetchall() or [])

    # 把 rows 轉成 per-engine cells dict，便於 aggregation function 處理
    cells: list[dict] = []
    cells_by_engine: dict[str, list[dict]] = {}
    total_n = 0
    total_close_attempts = 0
    total_close_fills = 0

    for row in rows:
        engine_mode = row[0]
        kind = row[1]
        n = int(row[2] or 0)
        close_attempts = int(row[3] or 0)
        close_fills = int(row[4] or 0)
        # cell-level verdict（注：aggregation 取 per-engine + cross-engine
        # severity_max；cell 自身 verdict 為 reference field 供 dashboard 顯示）
        # 與 _aggregate_verdict_per_engine logic 對齊（PA 2026-05-21 IMPL refine）：
        #   - stale_roc_neg cell + close_attempts=0 → FAIL（router 缺口確證）
        #   - giveback cell + close_attempts>0 + n>=threshold → PASS
        #   - giveback cell + n>=warn_giveback_threshold + close_attempts=0 → WARN
        #   - other_phys_lock / 任何 n<threshold → INSUFFICIENT_SAMPLE
        if kind == "gate4_stale_roc_neg" and n > 0 and close_attempts == 0:
            cell_verdict = VERDICT_FAIL
        elif (
            kind == "gate4_giveback"
            and n >= insufficient_sample_threshold
            and close_attempts > 0
        ):
            cell_verdict = VERDICT_PASS
        elif (
            kind == "gate4_giveback"
            and n >= warn_giveback_threshold
            and close_attempts == 0
        ):
            cell_verdict = VERDICT_WARN
        else:
            cell_verdict = VERDICT_INSUFFICIENT_SAMPLE

        cell = {
            "engine_mode": engine_mode,
            "phys_lock_kind": kind,
            "n": n,
            "close_maker_attempts": close_attempts,
            "close_maker_fills": close_fills,
            "verdict": cell_verdict,
        }
        cells.append(cell)
        cells_by_engine.setdefault(engine_mode, []).append(cell)
        total_n += n
        total_close_attempts += close_attempts
        total_close_fills += close_fills

    # 計算 per-engine aggregate verdict + cross-engine severity_max
    # 注：``_common.severity_max`` order = PASS(0) < INSUFFICIENT_SAMPLE(1)
    # < WARN(2) < FAIL(3)；PA 啟動值用 PASS 作 lower bound，這樣：
    #   - 任一 engine FAIL → overall FAIL（FAIL 最嚴重，會被取）
    #   - 任一 engine WARN → overall WARN
    #   - 任一 engine INSUFFICIENT_SAMPLE → overall INSUFFICIENT_SAMPLE
    #     （比 PASS 嚴重，原因：缺數據比有數據通過更值得 reviewer 注意）
    #   - 所有 engine PASS → overall PASS
    # 若無任何 row 時保險：全 engine 視為 INSUFFICIENT_SAMPLE
    per_engine_verdicts: dict[str, str] = {}

    if cells_by_engine:
        for engine_mode, engine_cells in cells_by_engine.items():
            v = _aggregate_verdict_per_engine(
                engine_cells,
                insufficient_sample_threshold=insufficient_sample_threshold,
                warn_giveback_threshold=warn_giveback_threshold,
            )
            per_engine_verdicts[engine_mode] = v

        # 補：未出現 row 的 engine_mode（如 fixture 只有 demo 但 CLI 要 demo+live_demo）
        # 視為 INSUFFICIENT_SAMPLE，**不沖淡** 其他 engine 的 PASS（per spec §1
        # natural sparse 不阻 deploy 原則）。注：本 fallback **不參與** overall_verdict
        # 計算，只在 per_engine_verdicts dict 中作為 reference 顯示，理由 = engine 該
        # CLI 要但 SQL 0 row 是「sample 不足」非「pipeline broken」訊號。
        for em in engine_modes:
            if em not in per_engine_verdicts:
                per_engine_verdicts[em] = VERDICT_INSUFFICIENT_SAMPLE

        # overall_verdict 只 fold 真實看到 row 的 engine（per spec §1 natural
        # sparse 不沖淡 PASS）；起始 lower bound = PASS。
        overall_verdict = VERDICT_PASS
        for engine_mode in cells_by_engine.keys():
            overall_verdict = severity_max(
                overall_verdict, per_engine_verdicts[engine_mode]
            )
    else:
        # 無任何 row → 全 INSUFFICIENT_SAMPLE
        for em in engine_modes:
            per_engine_verdicts[em] = VERDICT_INSUFFICIENT_SAMPLE
        overall_verdict = VERDICT_INSUFFICIENT_SAMPLE

    return {
        "metric": "phys_lock_gate4_distribution",
        "check_id": "[68]",
        "namespace": "canary",  # cross-namespace disambiguation（passive_wait
                                # 也用 [68] portfolio_resting；明標 namespace 避混淆）
        "spec": (
            "P2-PHYS-LOCK-72-HEALTHCHECK / FA C6 OQ-C6-2 follow-up; "
            "schema = V033 exit_reason + V094 close_maker_attempt + "
            "V094 close_maker_fallback_reason + JSONB details"
        ),
        "window_secs": window_secs,
        "engine_modes": engine_modes,
        "thresholds": {
            "insufficient_sample_threshold": insufficient_sample_threshold,
            "warn_giveback_threshold": warn_giveback_threshold,
        },
        "total_n": total_n,
        "total_close_attempts": total_close_attempts,
        "total_close_fills": total_close_fills,
        "cells": cells,
        "per_engine_verdicts": per_engine_verdicts,
        "verdict": overall_verdict,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    configure_logging()
    args = _parse_args()
    engine_modes = split_engine_modes(args.engine_mode)

    conn = connect_pg()
    try:
        with conn.cursor() as cur:
            result = run(
                cur,
                window_secs=args.window_secs,
                engine_modes=engine_modes,
                insufficient_sample_threshold=args.insufficient_sample_threshold,
                warn_giveback_threshold=args.warn_giveback_threshold,
            )
    finally:
        conn.close()

    emit_result(result, write_file=args.write_file, text_mode=args.text)

    # PASS / INSUFFICIENT_SAMPLE → exit 0；WARN/FAIL → exit 1
    if result["verdict"] in (VERDICT_FAIL, VERDICT_WARN):
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
