#!/usr/bin/env python3
"""seed_dead_mode_lessons — 把 6 條真實 NO-GO dead-mode 教訓冪等 seed 進 agent.lessons。

MODULE_NOTE
模塊用途：
  L2 P3b owed ②（PA 2026-06-10 owed-conductor-wiring 設計 §C）。hypothesize novelty stage
  （l2_ml_advisory_executor._check_novelty）檢索 agent.lessons WHERE symbol + lesson_type=
  'dead_mode'；表內 0 條 dead-mode row 時 novelty 失明（任何已死假設都判「新」）。本工具把
  6 條 ground 在真實 NO-GO 結案的失敗模式 seed 進去，同時供 M4 bad-set builder 當負樣本。

主要函數：
  - build_seed_rows()：純函數，回 6 條 INSERT 參數 dict（0 DB；單測主體）。
  - apply_seeds(conn, rows)：冪等寫入（conn 顯式注入；fake conn 可測）。
  - main(argv)：CLI（默認 --dry-run print 不寫；顯式 --apply/--write + --dsn 才落庫）。

欄位值決策（ground 在 layer2_critic._retrieve_lessons_sync 的 filter 行為，PA §C.1）：
  - symbol = 'ml_advisory'（= executor _SINK_SYMBOL_PLACEHOLDER）：檢索 WHERE symbol 必過濾，
    seed 的 symbol 與檢索 symbol 不一致 = 永遠 miss = 死資料。dead-mode 是 cross-symbol
    失敗模式（down-beta 偽裝不分 symbol），故掛 placeholder 當 global namespace。
  - source = 'dead_mode_seed'：第 4 namespace（不撞 l2_session / ml_advisory sink / ml_shadow）；
    filter 不含 source → 檢索照常命中；純 provenance，未來清理可精確圈定。
  - content = 英文主幹：hypothesize statement 是英文 JSON，pg_trgm 是字面 trigram，
    中文 content vs 英文 hint 相似度 ≈ 0 → 全中文 seed = 永 miss 死資料。
  - context_id = 'seed:<slug>'：穩定 idempotency 錨點（INSERT ... WHERE NOT EXISTS）。
  - outcome_net_bps / session_cost_usd 恆 NULL（V133 forward-stub 規則：readers must not
    assume non-null；seed 非 session 產物）。

硬邊界：
  - **默認 --dry-run（print 不寫，0 DB 連線）**；顯式 --apply（alias --write）才落庫。
    為什麼默認無害：承 2026-06-10 測試 fixture 寫進 prod 21 rows 污染事故（0ce45a09）——
    任何寫庫工具必須默認無害，誤跑零副作用。
  - **--dsn 顯式必填（寫模式）**：不隱式讀任何 env DSN（不吃 OPENCLAW_DATABASE_URL /
    POSTGRES_*），杜絕「忘了在哪個環境」就寫進 prod。
  - 冪等：INSERT ... SELECT ... WHERE NOT EXISTS（source + context_id 錨點），重跑 inserted=0。
  - 全參數綁定（psycopg2 %(name)s）：英文長文本不進 SQL 字面（quoting 注入零暴露面）。
  - 只寫 agent.lessons（V133）；不碰 order / promotion / lease / 任何交易真相層。
  - 不 seed listing fade：它是 active 主路徑非 dead mode（M4 good-set 側）。

用法：
  python3 helper_scripts/m4/seed_dead_mode_lessons.py                # dry-run（默認，零連線）
  python3 helper_scripts/m4/seed_dead_mode_lessons.py --apply --dsn 'postgresql://...'
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

# 與 executor / critic 檢索鏈一致的常數（PA §C.1 表）。
SEED_SOURCE = "dead_mode_seed"
SEED_SYMBOL = "ml_advisory"          # = l2_ml_advisory_executor._SINK_SYMBOL_PLACEHOLDER
SEED_LESSON_TYPE = "dead_mode"       # = _check_novelty 硬編檢索值
SEED_SESSION_TRIGGER = "seed:2026-06-10"  # seed 批次可追溯

# 6 條 dead-mode seed（PA §C.2 verbatim；全部 ground 在 memory 真實 NO-GO 結案）。
# content 模板：DEAD MODE [<family>]: <english failed-hypothesis statement>.
#               Why dead: <mechanism>. Evidence: <numbers>.
DEAD_MODE_SEEDS: tuple[dict[str, str], ...] = (
    {
        "slug": "funding_arb_v2",
        "content": (
            "DEAD MODE [funding_arb]: Delta-neutral funding rate arbitrage long spot "
            "short perp harvesting funding payments. Why dead: delta-neutral math does "
            "not survive fees plus basis drift; carry edge below cost wall. Evidence: "
            "closed NEGATIVE avg net -36.76 bps, 0 win rate, n=13 (G-2 2026-04-18)."
        ),
    },
    {
        "slug": "funding_short_v2",
        "content": (
            "DEAD MODE [funding_short]: Short perp on positive funding extreme expecting "
            "funding mean reversion. Why dead: positive-side cap is an IR floor "
            "fingerprint; regime-dormant; 160 percent break-even threshold vs realized "
            "carry. Evidence: 93 percent probe rejects missing_basis_asof (2026-05-31)."
        ),
    },
    {
        "slug": "cascade_fade_h2",
        "content": (
            "DEAD MODE [cascade_fade]: Fade liquidation cascade with mean-reversion "
            "entry after forced-liquidation burst. Why dead: apparent edge was down-beta "
            "masquerade inside a BTC downtrend regime, not alpha. Evidence: 280 events, "
            "all demeaned |t| < 1.3 (2026-06-03 NO-GO)."
        ),
    },
    {
        "slug": "funding_tilt",
        "content": (
            "DEAD MODE [funding_tilt]: Cross-sectional funding tilt portfolio long "
            "low-funding short high-funding symbols. Why dead: funding tilt loads on "
            "market beta not alpha; carry cannot clear costs. Evidence: carry_cost_ratio "
            "3.64, DSR 0, 82 percent down-beta share, NO-GO-C (2026-06-03)."
        ),
    },
    {
        "slug": "grid_short_downtrend",
        "content": (
            "DEAD MODE [grid_short]: Grid short bias harvesting volatility in a "
            "downtrend regime. Why dead: blocked-signal counterfactual shows demeaned "
            "alpha approx 0; any short bias in a down regime is trend beta in disguise; "
            "requires explicit beta neutralization. Evidence: blocked grid_short replay "
            "(2026-06-03)."
        ),
    },
    {
        "slug": "textbook_scalping_family",
        "content": (
            "DEAD MODE [micro_profit]: Textbook high-turnover scalping signals (micro "
            "profit lock, RSI reversal, breakout momentum) on 1m-5m bars. Why dead: "
            "gross edge 1-3 bps per trade below the 11-27 bps cost wall; textbook "
            "indicators carry no net alpha after costs. Evidence: five strategies "
            "alpha-deficient across sprints (2026-05-10 / 2026-06-01)."
        ),
    },
)

# 冪等 INSERT（PA §C.4）：source + context_id 是穩定錨點；outcome_net_bps /
# session_cost_usd 恆 NULL（V133 forward-stub）。WHERE NOT EXISTS 使重跑 rowcount=0。
_INSERT_SQL = """
INSERT INTO agent.lessons
    (symbol, lesson_type, content, session_trigger, context_id,
     outcome_net_bps, session_cost_usd, source)
SELECT %(symbol)s, %(lesson_type)s, %(content)s, %(session_trigger)s, %(context_id)s,
       NULL, NULL, %(source)s
WHERE NOT EXISTS (
    SELECT 1 FROM agent.lessons
    WHERE source = %(source)s AND context_id = %(context_id)s
)
"""

_COUNT_SQL = "SELECT count(*) FROM agent.lessons WHERE source = %(source)s"


def build_seed_rows() -> list[dict[str, Any]]:
    """把 DEAD_MODE_SEEDS 展開為 INSERT 參數 dict（純函數，0 DB）。

    為什麼純函數分離：欄位完整性 / slug 唯一 / content 英文主幹 等不變量可零連線單測。
    """
    rows: list[dict[str, Any]] = []
    for seed in DEAD_MODE_SEEDS:
        rows.append(
            {
                "symbol": SEED_SYMBOL,
                "lesson_type": SEED_LESSON_TYPE,
                "content": seed["content"],
                "session_trigger": SEED_SESSION_TRIGGER,
                "context_id": f"seed:{seed['slug']}",
                "source": SEED_SOURCE,
            }
        )
    return rows


def apply_seeds(conn: Any, rows: list[dict[str, Any]]) -> tuple[int, int]:
    """冪等寫入：每條跑 INSERT ... WHERE NOT EXISTS；回 (inserted, skipped)。

    conn 顯式注入（不在函數內建連線）：測試用 fake conn 驗 SQL 構造 / 冪等分支，
    真連線只在 main() 的 --apply 路徑建立。失敗直接 raise（fail-loud，不吞）。
    """
    inserted = 0
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(_INSERT_SQL, row)
            # WHERE NOT EXISTS 擋掉時 rowcount=0（冪等 skip）；插入成功 rowcount=1。
            inserted += int(cur.rowcount or 0)
    conn.commit()
    return inserted, len(rows) - inserted


def count_seed_rows(conn: Any) -> int:
    """SELECT count(*) WHERE source='dead_mode_seed'（PA §C.4 驗收查詢）。"""
    with conn.cursor() as cur:
        cur.execute(_COUNT_SQL, {"source": SEED_SOURCE})
        row = cur.fetchone()
    return int(row[0]) if row else 0


def _print_dry_run(rows: list[dict[str, Any]]) -> None:
    """dry-run 輸出：每條 context_id + content 預覽（不連線、不執行任何 SQL）。"""
    print(f"[DRY-RUN] 共 {len(rows)} 條 dead-mode seed（未寫庫；--apply --dsn 才落庫）：")
    for row in rows:
        preview = row["content"][:96]
        print(f"  - {row['context_id']}  symbol={row['symbol']} "
              f"lesson_type={row['lesson_type']} source={row['source']}")
        print(f"    content[:96]: {preview}")
    print("[DRY-RUN] 冪等錨點 = (source, context_id)；INSERT ... WHERE NOT EXISTS，可重跑。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="冪等 seed 6 條 dead-mode 教訓進 agent.lessons（默認 dry-run 不寫）。"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="只 print 不寫（默認行為；顯式給以自描述）。",
    )
    group.add_argument(
        "--apply",
        "--write",
        dest="apply",
        action="store_true",
        help="真寫庫（必須同時給 --dsn）。",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="顯式 PG DSN（寫模式必填；不隱式讀任何 env，杜絕誤寫 prod）。",
    )
    args = parser.parse_args(argv)

    rows = build_seed_rows()

    if not args.apply:
        _print_dry_run(rows)
        return 0

    if not args.dsn:
        # 為什麼 fail-closed：寫庫目標必須顯式指定，缺 DSN 絕不 fallback 任何隱式連線。
        parser.error("--apply 需要顯式 --dsn（本工具不隱式讀 env DSN）")

    # lazy import：dry-run 路徑零依賴（Mac 無 psycopg2 也能跑）；測試 monkeypatch sys.modules。
    import psycopg2

    conn = psycopg2.connect(args.dsn)
    try:
        inserted, skipped = apply_seeds(conn, rows)
        total = count_seed_rows(conn)
        print(f"[APPLY] inserted={inserted} skipped={skipped}（冪等：重跑 inserted=0）")
        print(f"[APPLY] agent.lessons WHERE source='{SEED_SOURCE}' count={total}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
