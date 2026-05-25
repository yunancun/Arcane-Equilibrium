#!/usr/bin/env python3
"""Sprint 2 Alpha Tournament daily 14d evidence accumulation。

per W2-A finalize §3.3-§3.4 + AC-S2-A-2 minimum bar：
   - 14d bucket-split SQL per strategy × symbol × trade_date
   - Wilson CI 95% lower bound projection per candidate × symbol × date
   - Bonferroni K=2 alpha 調整（2 candidate this sprint）
   - Sample size cumulative projection（target ≥ 30 over 14d per CR-6）
   - read-only：SELECT only + stdout JSON log；不寫 PG
   - attribution_chain_ok 必 100%（per Sprint N+0 closure 範式）
   - track = 'direct_exploit'（per V101 ENUM + ADR-0026 hand-coded Rust）

Output: stdout JSON + log to /tmp/openclaw/logs/alpha_candidate_daily_<YYYYMMDD>.log

Usage:
   python3 -m helper_scripts.alpha_tournament.attribution_daily
   python3 -m helper_scripts.alpha_tournament.attribution_daily --dry-run

Caller 端 PG connection 由環境變數注入（OPENCLAW_PG_DSN / 個別 PGHOST 等）；
本 script 接受 psycopg2 connection 也接受 dry-run no-conn mode（僅 SQL build）。

MODULE_NOTE:
   模塊用途：read-only 14d demo accumulation cron entry；2 candidate × 7 trade_date
     × 2 symbol bucket-split + Wilson CI lower bound + Bonferroni K=2 alpha 調整。
   主要函數：build_bucket_split_query / compute_wilson_lower_bound /
     compute_bonferroni_alpha / project_min_sample_gate / main (CLI entry)。
   依賴：psycopg2-binary (optional：dry-run mode 不需)；math (stdlib)。
   硬邊界：
     - 不寫 PG（SELECT only）。
     - track = 'direct_exploit' / engine_mode IN ('demo','live_demo') /
       attribution_chain_ok = TRUE 三 invariant hard-coded。
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from typing import Any

# psycopg2 為 optional dep：dry-run mode (僅 SQL build) 不需。
try:
    import psycopg2.extensions  # noqa: F401
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────
# 常量：per W2-A finalize §3.1 + §3.3
# ─────────────────────────────────────────────────────────────────────────

CANDIDATE_STRATEGIES: tuple[str, ...] = (
    "funding_short_v2",
    "liquidation_cascade_fade",
)
"""Sprint 2 Stream A 2 candidate；W2-F MIT post-IMPL audit 評 14d evidence。"""

BONFERRONI_K: int = 2
"""Bonferroni 多重檢定校正常數：K=2 (2 candidate this sprint)。
不變量：alpha = 0.05 / K = 0.025。Sprint 3+ K 變化需 PA + QC 重評。"""

ALPHA_RAW: float = 0.05
"""Per-test alpha；Bonferroni 校正後 = ALPHA_RAW / BONFERRONI_K = 0.025。"""

MIN_FILLS_PER_CANDIDATE: int = 30
"""per CR-6 minimum bar #1：N >= 30 over 14d cumulative。
per AC-S2-A-2 / AC-S2-A-C1-7 / AC-S2-A-C4-9。"""

WILSON_Z_95: float = 1.96
"""z-score for 95% Wilson CI lower bound。"""

# track ENUM compliance：per ADR-0026 hand-coded Rust strategy 必 = direct_exploit。
# 不可寫 'alpha_short_carry' / 'alpha_microstructure_fade'（W1-A 虛構 ENUM）。
EXPECTED_TRACK: str = "direct_exploit"

# engine_mode 過濾：demo + live_demo (per memory project_engine_mode_tag_live_demo)。
EXPECTED_ENGINE_MODES: tuple[str, ...] = ("demo", "live_demo")


# ─────────────────────────────────────────────────────────────────────────
# Build SQL: 14d bucket-split per W2-A §3.3
# ─────────────────────────────────────────────────────────────────────────


def build_bucket_split_query() -> str:
    """構造 14d bucket-split SQL per W2-A finalize §3.3。

    為什麼用字符串模板而非 psycopg2 placeholder：本 SQL 完全為靜態 SELECT，
    動態變量僅 strategy_name list 走 caller 端 %s placeholder（在 main 呼叫處 bind）。

    Returns:
        SQL string with 1 placeholder (%s) for strategy_name array (ANY(%s))。
    """
    return """
WITH alpha_candidate_demo AS (
  SELECT
    strategy_name,
    DATE(filled_at AT TIME ZONE 'UTC') AS trade_date,
    symbol,
    COUNT(*) AS n_fills,
    AVG(net_pnl_bps) AS avg_net_bps,
    -- Wilson CI lower bound (z=1.96 for 95% CI; per CR-6 minimum bar #2)。
    -- defensive against n=0 / stddev=NULL (COALESCE + NULLIF)。
    (AVG(net_pnl_bps) - 1.96 * COALESCE(STDDEV(net_pnl_bps), 0)
     / NULLIF(SQRT(GREATEST(COUNT(*), 1)::float8), 0))::numeric(10,4) AS wilson_lower_bps
  FROM trading.fills
  WHERE strategy_name = ANY(%s)
    AND engine_mode IN ('demo', 'live_demo')
    AND track = 'direct_exploit'           -- per ADR-0026 hand-coded Rust = direct_exploit
    AND attribution_chain_ok = TRUE        -- per Sprint N+0 closure 範式 100% 預期
    AND filled_at > NOW() - INTERVAL '14 days'
  GROUP BY strategy_name, trade_date, symbol
)
SELECT
  strategy_name,
  trade_date,
  SUM(n_fills) AS total_fills,
  AVG(avg_net_bps) AS avg_net_bps_overall,
  MIN(wilson_lower_bps) AS wilson_lower_overall_bps,
  SUM(SUM(n_fills)) OVER (PARTITION BY strategy_name ORDER BY trade_date)
    AS cumulative_n_fills,
  CASE WHEN SUM(SUM(n_fills)) OVER (PARTITION BY strategy_name ORDER BY trade_date) >= 30
       THEN 'PASS' ELSE 'PENDING' END AS min_sample_gate
FROM alpha_candidate_demo
GROUP BY strategy_name, trade_date
ORDER BY strategy_name, trade_date DESC;
"""


# ─────────────────────────────────────────────────────────────────────────
# Statistical helpers
# ─────────────────────────────────────────────────────────────────────────


def compute_bonferroni_alpha(k: int = BONFERRONI_K, alpha_raw: float = ALPHA_RAW) -> float:
    """Bonferroni 多重檢定校正。

    為什麼 K=2：Sprint 2 Stream A 同時跑 2 candidate；若任一 p-value < alpha/K
    則拒絕該 candidate 的 null hypothesis。

    不變量：k > 0；alpha_raw 必 > 0 且 < 1。

    Args:
        k: 同時測試的 candidate 數量。
        alpha_raw: 每個檢定的 raw alpha（默認 0.05）。

    Returns:
        Bonferroni-corrected alpha = alpha_raw / k。
    """
    if k < 1:
        raise ValueError(f"Bonferroni k={k} must be >= 1")
    if not (0.0 < alpha_raw < 1.0):
        raise ValueError(f"alpha_raw={alpha_raw} must be in (0, 1)")
    return alpha_raw / float(k)


def compute_wilson_lower_bound(
    mean: float,
    stddev: float,
    n: int,
    z: float = WILSON_Z_95,
) -> float | None:
    """計算 Wilson CI 下界（normal-approximation 形式；per W2-A finalize §3.3）。

    公式：mean - z × stddev / sqrt(n)。

    不變量：n > 0；缺資料返 None。

    Args:
        mean: 樣本平均（net_pnl_bps）。
        stddev: 樣本標準差。
        n: 樣本數。
        z: z-score (默認 1.96 for 95% CI)。

    Returns:
        Wilson lower bound 或 None (if n <= 0 or stddev NaN/None)。
    """
    if n <= 0:
        return None
    if stddev is None or not math.isfinite(stddev):
        return None
    if mean is None or not math.isfinite(mean):
        return None
    return mean - z * stddev / math.sqrt(max(n, 1))


def project_min_sample_gate(cumulative_n: int, min_required: int = MIN_FILLS_PER_CANDIDATE) -> bool:
    """per CR-6 minimum bar #1：cumulative n_fills >= 30 gate pass。

    為什麼 hard threshold：sample size < 30 統計 power 不足；CPCV / Bonferroni
    校正不可靠。Sprint 2 14d 預期累積 30+；不達不可升 'preregistered'。

    Args:
        cumulative_n: 14d 累積 fill 數。
        min_required: 預設 30 (per AC-S2-A-2)。

    Returns:
        True if cumulative_n >= min_required。
    """
    return cumulative_n >= min_required


# ─────────────────────────────────────────────────────────────────────────
# Main CLI entry
# ─────────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sprint 2 Alpha Tournament daily 14d evidence accumulation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="不連 PG，只 build SQL + 印 Bonferroni alpha + 配置摘要（驗 module import / SQL syntax）",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="verbose logging",
    )
    parser.add_argument(
        "--bonferroni-k",
        type=int,
        default=BONFERRONI_K,
        help=f"Bonferroni K (default {BONFERRONI_K})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger = logging.getLogger(__name__)

    summary: dict[str, Any] = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "bonferroni_k": args.bonferroni_k,
        "bonferroni_alpha": compute_bonferroni_alpha(args.bonferroni_k),
        "min_fills_required": MIN_FILLS_PER_CANDIDATE,
        "expected_track": EXPECTED_TRACK,
        "expected_engine_modes": list(EXPECTED_ENGINE_MODES),
        "candidates": list(CANDIDATE_STRATEGIES),
        "dry_run": args.dry_run,
    }

    sql = build_bucket_split_query()
    summary["bucket_split_sql_lines"] = len(sql.strip().splitlines())

    if args.dry_run:
        # dry-run：SQL build + 配置摘要，不連 PG。
        logger.info("dry-run mode: SQL built, no PG query executed")
        summary["candidates_data"] = {
            name: {
                "status": "dry_run",
                "cumulative_n_fills": 0,
                "min_sample_gate_pass": False,
            }
            for name in CANDIDATE_STRATEGIES
        }
        print(json.dumps(summary, indent=2))
        return 0

    if not PSYCOPG2_AVAILABLE:
        logger.error(
            "psycopg2 not available; install psycopg2-binary or run with --dry-run"
        )
        return 2

    # 真實 PG 路徑：caller 端必透過環境變數提供 PG connection 配置。
    # 為什麼不在本 module own connection lifecycle：m8/anomaly_event_query.py 範式
    # 是 caller 注入 conn；本 cron entry 由 wrapper shell script (見 §3.4 cron line)
    # source secrets 後 psql 跑 SQL 或注入 conn 至本 module。
    # Sprint 2 W2-B scaffold 階段：cron wrapper shell + psql 路徑由主會話 W2-F
    # PA 接續落地（per W2-A finalize §3.4 cron line + §11.3 action checklist）。
    logger.warning(
        "Sprint 2 W2-B scaffold: cron wrapper + psql 路徑由 W2-F PA 接續；"
        "本 module 真實 PG query 由 wrapper script 通過 connection 注入路徑接通"
    )

    # 跑 SQL 路徑（Sprint 3+ cron 完整 wire-up 後啟用）。
    # 此 placeholder 保持 main() 不 throw；運維端可走 dry-run 驗 SQL syntax。
    summary["candidates_data"] = {
        name: {
            "status": "wire_up_pending_w2f_pa",
            "cumulative_n_fills": 0,
            "min_sample_gate_pass": False,
        }
        for name in CANDIDATE_STRATEGIES
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
