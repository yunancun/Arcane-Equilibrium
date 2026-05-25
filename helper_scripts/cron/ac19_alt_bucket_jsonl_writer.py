#!/usr/bin/env python3
"""AC-19 ALT bucket 14d 監測：CSV → JSONL append + Wilson sanity verify。

MODULE_NOTE:
  模塊用途：cron wrapper 跑完 psql --csv 後將 daily bucket-split 結果 append 到
    14d 累積 JSONL summary file，附加 day_index / window meta + 重算 Wilson CI
    防 SQL 計算與 Python 雙端漂移。
  主要函數：
    - wilson_lower_95 / wilson_upper_95：canonical Wilson score interval 公式。
    - classify_verdict：bucket-aware 3 級 verdict (PASS / MARGINAL / FAIL /
      INSUFFICIENT_DATA)。
    - load_psql_csv：解析 psql --csv 輸出（含 8 欄 header）為 row dict list。
    - build_jsonl_records：根據解析行 + 配置 metadata 生成 JSONL row。
    - append_jsonl：原子 append（write-then-fsync）。
    - main：CLI entry。
  依賴：math / json / csv / argparse / pathlib（stdlib only）；無 psycopg2 依賴
    （PG query 由 wrapper script psql 完成）。
  硬邊界：
    - read-only on CSV input；write-only append on JSONL output（不改既存行）。
    - WINDOW_START / WINDOW_END 對映 W1-G SOP §1 (2026-05-19 → 2026-06-02)；
      day_index > 14 之後 wrapper 應 skip，但本 module 自身仍接受（idempotent，
      允許補跑歷史）。
    - Wilson 雙端重算與 SQL CASE 必須在 1.0% 容差內一致；超過時 sanity_drift
      warning（不 fail，留證據）。

Usage:
    python3 ac19_alt_bucket_jsonl_writer.py \\
        --input  /tmp/openclaw/logs/ac19_alt_bucket_daily_2026-05-26.log.csv \\
        --ts     2026-05-26T08:00:00Z \\
        --output /tmp/openclaw/ac19_alt_bucket_14d_summary.jsonl

Exit code（聚合 verdict，與 cron exit semantic 對齊）:
    0 — 所有 bucket PASS（或 INSUFFICIENT_DATA + ALT bucket 未 FAIL）
    1 — 任一 bucket MARGINAL（ALT bucket 20% ≤ Wilson lower < 30%）
    2 — 任一 bucket FAIL
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────
# 常量：per W1-G SOP §1 / §5
# ─────────────────────────────────────────────────────────────────────────

WINDOW_START: date = date(2026, 5, 19)
"""W1-G SOP §1：14d window start。"""

WINDOW_END: date = date(2026, 6, 2)
"""W1-G SOP §1：14d window end (exclusive)。"""

WILSON_Z_95: float = 1.96
"""95% Wilson CI z-score。"""

LARGE_CAP_PASS_THRESHOLD: float = 60.0
"""W1-G SOP §5：large_cap bucket Wilson lower ≥ 60% 才 PASS。"""

ALT_PASS_THRESHOLD: float = 30.0
"""W1-G SOP §5：ALT bucket Wilson lower ≥ 30% PASS。"""

ALT_MARGINAL_THRESHOLD: float = 20.0
"""W1-G SOP §5：ALT bucket 20% ≤ Wilson lower < 30% → MARGINAL。"""

SANITY_DRIFT_TOLERANCE_PCT: float = 1.0
"""Python 重算 Wilson 與 SQL CASE 允許漂移上限（百分點）；超過寫 warning。"""

# CSV header 欄位順序 (與 ac19_alt_bucket_daily_query.sql 一致)。
CSV_FIELDNAMES: tuple[str, ...] = (
    "bucket",
    "attempts",
    "fills",
    "timeouts",
    "fill_rate_pct",
    "wilson_lower_pct",
    "wilson_upper_pct",
    "verdict",
)


# ─────────────────────────────────────────────────────────────────────────
# Wilson CI 95% computation (canonical formula per W1-G SOP §4)
# ─────────────────────────────────────────────────────────────────────────


def wilson_lower_95(fills: int, attempts: int) -> float:
    """Wilson score interval 下界（百分比）。

    為什麼用 Wilson 而非 normal approximation：n 小 + p_hat 邊界（接近 0 或 1）時
    normal CI 失準；Wilson 對 binomial proportion 更穩健。

    不變量：attempts >= 0；attempts=0 回傳 0.0（INSUFFICIENT_DATA 由 caller 判定）。

    Args:
        fills: 成功計數（close_maker fill）。
        attempts: 嘗試總數（close_maker_attempt=true 行數）。

    Returns:
        Wilson 95% CI lower bound 百分比 [0.0, 100.0]。
    """
    if attempts <= 0:
        return 0.0
    if fills < 0 or fills > attempts:
        raise ValueError(f"fills={fills} out of range [0, {attempts}]")
    p_hat = fills / attempts
    z = WILSON_Z_95
    z2 = z * z
    # 浮點誤差防 sqrt(negative)。
    inner = max(0.0, p_hat * (1.0 - p_hat) / attempts + z2 / (4.0 * attempts * attempts))
    margin = z * math.sqrt(inner)
    center = p_hat + z2 / (2.0 * attempts)
    denom = 1.0 + z2 / attempts
    lower = (center - margin) / denom
    return max(0.0, lower * 100.0)


def wilson_upper_95(fills: int, attempts: int) -> float:
    """Wilson score interval 上界（百分比）。

    Args:
        fills: 成功計數。
        attempts: 嘗試總數。

    Returns:
        Wilson 95% CI upper bound 百分比 [0.0, 100.0]。
    """
    if attempts <= 0:
        return 0.0
    if fills < 0 or fills > attempts:
        raise ValueError(f"fills={fills} out of range [0, {attempts}]")
    p_hat = fills / attempts
    z = WILSON_Z_95
    z2 = z * z
    inner = max(0.0, p_hat * (1.0 - p_hat) / attempts + z2 / (4.0 * attempts * attempts))
    margin = z * math.sqrt(inner)
    center = p_hat + z2 / (2.0 * attempts)
    denom = 1.0 + z2 / attempts
    upper = (center + margin) / denom
    return min(100.0, upper * 100.0)


def classify_verdict(bucket: str, wilson_lower_pct: float, attempts: int) -> str:
    """3 級 verdict per W1-G SOP §5。

    為什麼 INSUFFICIENT_DATA 獨立等級：attempts=0 時 Wilson lower 數學上 = 0.0
    但語義不是 FAIL（沒收到資料 ≠ 機制失靈）；保留以利 14d 末段 retrospective。

    Args:
        bucket: 'large_cap' or 'alt'。
        wilson_lower_pct: Wilson lower bound 百分比 [0, 100]。
        attempts: 樣本數（用於 INSUFFICIENT_DATA gate）。

    Returns:
        'PASS' / 'MARGINAL' / 'FAIL' / 'INSUFFICIENT_DATA'。
    """
    if attempts == 0:
        return "INSUFFICIENT_DATA"
    if bucket == "large_cap":
        return "PASS" if wilson_lower_pct >= LARGE_CAP_PASS_THRESHOLD else "FAIL"
    if bucket == "alt":
        if wilson_lower_pct >= ALT_PASS_THRESHOLD:
            return "PASS"
        if wilson_lower_pct >= ALT_MARGINAL_THRESHOLD:
            return "MARGINAL"
        return "FAIL"
    # 未知 bucket 不靜默 PASS；fail-loud。
    raise ValueError(f"unknown bucket: {bucket}")


# ─────────────────────────────────────────────────────────────────────────
# CSV → row dict
# ─────────────────────────────────────────────────────────────────────────


def load_psql_csv(csv_text: str) -> list[dict[str, Any]]:
    """解析 psql --csv 輸出。

    為什麼接受 text 而非檔案：方便 pytest 注入 mock data；caller 從 Path 讀字串再
    呼叫本函數。

    psql --csv 輸出第一行為 column header（與 CSV_FIELDNAMES 對齊）；資料行 8 欄。

    Args:
        csv_text: psql --csv 完整輸出字串。

    Returns:
        row dict list；每 row 含 bucket / attempts / fills / timeouts /
        fill_rate_pct / wilson_lower_pct / wilson_upper_pct / verdict 8 keys。
        數值欄位自動轉 int / float（attempts/fills/timeouts 為 int；fill_rate_pct
        / wilson_*_pct 為 float）。
    """
    reader = csv.DictReader(StringIO(csv_text))
    if reader.fieldnames is None:
        return []
    # 容錯：psql 偶爾在 header 後加 ----- 分隔符；DictReader 不會自動 strip。
    rows: list[dict[str, Any]] = []
    for raw in reader:
        bucket = (raw.get("bucket") or "").strip()
        # 跳過空行或 psql trailing summary line（如 "(2 rows)"）。
        if not bucket or bucket.startswith("(") or bucket.startswith("-"):
            continue
        try:
            rows.append(
                {
                    "bucket": bucket,
                    "attempts": int(raw.get("attempts") or 0),
                    "fills": int(raw.get("fills") or 0),
                    "timeouts": int(raw.get("timeouts") or 0),
                    "fill_rate_pct": float(raw.get("fill_rate_pct") or 0.0),
                    "wilson_lower_pct": float(raw.get("wilson_lower_pct") or 0.0),
                    "wilson_upper_pct": float(raw.get("wilson_upper_pct") or 0.0),
                    "verdict": (raw.get("verdict") or "").strip(),
                }
            )
        except (ValueError, TypeError) as exc:
            # 解析失敗 fail-loud；cron wrapper 會把 stderr 寫進 daily log。
            raise ValueError(f"CSV row parse error: {raw!r}: {exc}") from exc
    return rows


# ─────────────────────────────────────────────────────────────────────────
# Build JSONL records
# ─────────────────────────────────────────────────────────────────────────


def compute_day_index(ts: datetime, window_start: date = WINDOW_START) -> int:
    """計算自 14d window 起始的 day_index（1-based, day 1 = 5/19）。

    Args:
        ts: cron fire UTC 時間。
        window_start: window 起始日（默認 W1-G SOP §1 = 5/19）。

    Returns:
        day_index >= 1；可能 > 14（window 已過期但允許補跑）。
    """
    if ts.tzinfo is None:
        # naive datetime 視為 UTC 防靜默漂移。
        ts = ts.replace(tzinfo=timezone.utc)
    days = (ts.date() - window_start).days + 1
    return max(1, days)


def build_jsonl_records(
    rows: list[dict[str, Any]],
    ts_iso: str,
    window_start: date = WINDOW_START,
    window_end: date = WINDOW_END,
) -> list[dict[str, Any]]:
    """根據解析行 + meta 構造 JSONL row（per W1-G SOP §6.2）。

    對每個 row：
      1. 重算 Wilson lower / upper（防 SQL 與 Python 漂移）。
      2. 重判 verdict（防 SQL CASE 邊界差異）。
      3. 若 |Python − SQL| > SANITY_DRIFT_TOLERANCE_PCT 寫 sanity_drift_pct 欄位
         （非 fail；保留證據）。

    Args:
        rows: load_psql_csv 解析結果。
        ts_iso: cron fire UTC ISO timestamp（如 '2026-05-26T08:00:00Z'）。
        window_start: 14d window 起始日。
        window_end: 14d window 結束日。

    Returns:
        JSONL row list；每 row 對應一個 bucket。
    """
    ts_parsed = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    day_index = compute_day_index(ts_parsed, window_start)
    records: list[dict[str, Any]] = []
    for row in rows:
        attempts = row["attempts"]
        fills = row["fills"]
        recomputed_lower = wilson_lower_95(fills, attempts)
        recomputed_upper = wilson_upper_95(fills, attempts)
        recomputed_verdict = classify_verdict(row["bucket"], recomputed_lower, attempts)
        record: dict[str, Any] = {
            "ts": ts_iso,
            "day_index": day_index,
            "window_start": f"{window_start.isoformat()}T00:00:00Z",
            "window_end": f"{window_end.isoformat()}T00:00:00Z",
            "bucket": row["bucket"],
            "attempts": attempts,
            "fills": fills,
            "timeouts": row["timeouts"],
            "fill_rate_pct": row["fill_rate_pct"],
            "wilson_lower_pct": round(recomputed_lower, 1),
            "wilson_upper_pct": round(recomputed_upper, 1),
            "verdict": recomputed_verdict,
        }
        # Sanity drift 對比：SQL 報的 lower vs Python 重算。
        sql_lower = row["wilson_lower_pct"]
        drift = abs(recomputed_lower - sql_lower)
        if drift > SANITY_DRIFT_TOLERANCE_PCT:
            record["sanity_drift_pct"] = round(drift, 2)
            record["sql_wilson_lower_pct"] = sql_lower
        records.append(record)
    return records


# ─────────────────────────────────────────────────────────────────────────
# Append JSONL
# ─────────────────────────────────────────────────────────────────────────


def append_jsonl(output_path: Path, records: list[dict[str, Any]]) -> None:
    """Append JSONL rows（write-then-fsync）。

    為什麼 fsync：cron wrapper 跑完即 exit；OS buffer flush 不保證；append-only
    summary 損失任意行都會破壞 14d trajectory。

    Args:
        output_path: 目標 JSONL（不存在會建立）。
        records: 要 append 的 row list。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
            fh.write("\n")
        fh.flush()
        try:
            import os

            os.fsync(fh.fileno())
        except OSError:
            # fsync 失敗（如 NFS 部分實作）不 fatal；buffer flush 已完成。
            pass


# ─────────────────────────────────────────────────────────────────────────
# Aggregate exit code（per cron semantic）
# ─────────────────────────────────────────────────────────────────────────


def aggregate_exit_code(records: list[dict[str, Any]]) -> int:
    """聚合 verdict → cron exit code。

    Rule（per W1-G SOP §3.1 cron exit pattern）：
        0 — 全 PASS（或 INSUFFICIENT_DATA）
        1 — 任一 MARGINAL
        2 — 任一 FAIL

    Args:
        records: build_jsonl_records 輸出。

    Returns:
        0 / 1 / 2。
    """
    code = 0
    for record in records:
        verdict = record.get("verdict", "")
        if verdict == "FAIL":
            return 2
        if verdict == "MARGINAL" and code < 1:
            code = 1
    return code


# ─────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AC-19 ALT bucket cron CSV → JSONL append + sanity verify",
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="psql --csv 輸出檔（cron wrapper 產生）",
    )
    parser.add_argument(
        "--ts",
        type=str,
        required=True,
        help="cron fire UTC ISO timestamp，例 2026-05-26T08:00:00Z",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="累積 JSONL summary 路徑（append-only）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="解析 + 重算 + 印 stdout，不寫 JSONL（驗 syntax + 數值）",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="verbose logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger = logging.getLogger(__name__)

    if not args.input.exists():
        logger.error("input CSV missing: %s", args.input)
        return 2
    try:
        csv_text = args.input.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("read input CSV %s failed: %s", args.input, exc)
        return 2

    try:
        rows = load_psql_csv(csv_text)
    except ValueError as exc:
        logger.error("parse CSV failed: %s", exc)
        return 2

    if not rows:
        logger.warning(
            "CSV parsed 0 row — possibly day-0 (no attempts) or psql error;"
            " writing INSUFFICIENT_DATA stub for both buckets"
        )
        # day-0 fallback：兩 bucket 都寫 stub 行，保 14d trajectory 不出洞。
        rows = [
            {
                "bucket": "large_cap",
                "attempts": 0,
                "fills": 0,
                "timeouts": 0,
                "fill_rate_pct": 0.0,
                "wilson_lower_pct": 0.0,
                "wilson_upper_pct": 0.0,
                "verdict": "INSUFFICIENT_DATA",
            },
            {
                "bucket": "alt",
                "attempts": 0,
                "fills": 0,
                "timeouts": 0,
                "fill_rate_pct": 0.0,
                "wilson_lower_pct": 0.0,
                "wilson_upper_pct": 0.0,
                "verdict": "INSUFFICIENT_DATA",
            },
        ]

    records = build_jsonl_records(rows, args.ts)

    if args.dry_run:
        for record in records:
            print(json.dumps(record, ensure_ascii=False))
        logger.info("dry-run: not writing to %s", args.output)
        return aggregate_exit_code(records)

    try:
        append_jsonl(args.output, records)
    except OSError as exc:
        logger.error("append JSONL %s failed: %s", args.output, exc)
        return 2

    logger.info(
        "appended %d row to %s; verdicts=%s",
        len(records),
        args.output,
        [r["verdict"] for r in records],
    )
    return aggregate_exit_code(records)


if __name__ == "__main__":
    sys.exit(main())
