"""Shared helpers for Phase 1b close-maker-first standalone healthchecks.

MODULE_NOTE:
  共享層 — 提供 PG 連線、Wilson 95% CI 計算、JSON 輸出、CLI argparse 範本。
  四個 [62][63][64][65] healthcheck 腳本以此為基座，保證 SQL semantic / 閾值
  / 輸出格式互相對齊。

  為什麼不複用 ``passive_wait_healthcheck.checks_close_maker_audit``：
  那個 module 是 cron orchestrator-driven（吃 ``cur`` 參數、回傳 tuple），
  耦合到 passive_wait runner state；本 package 是 PM/QA 手動 standalone
  入口，需要 self-contained connect + emit JSON。SQL 語意對齊以避治理 drift，
  但物理層獨立。

主要函數:
  - ``connect_pg()``：根據 env 建 psycopg2/psycopg connection（fail-closed
    on missing creds；不嘗試 fallback）
  - ``wilson_ci_95(successes, total)``：Wilson 95% CI 下/上界（z=1.96）
  - ``emit_result(result, write_file)``：JSON 輸出（stdout + optional file）
  - ``build_argparser(name, default_window_secs)``：CLI 範本

硬邊界:
  - PG 連線失敗必 fail-closed exit code 2（不嘗試 mock fallback）
  - Wilson CI ``total <= 0`` 直接回 (0.0, 0.0)，由 caller 處理 NEUTRAL 分支
  - 不引入新可變 singleton（每次 CLI 呼叫獨立連線）
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("phase1b_healthcheck")

# ───────────────────────────────────────────────────────────────────────────
# 預設值（與 spec §8.1 + AMD §4.1 對齊）
# ───────────────────────────────────────────────────────────────────────────

# AMD §5.4 BB-MF-2 conditional global pause 5min；per-symbol exp backoff 1s→60s。
# §4.1 表 [62][63][64][65] 7d demo+live_demo 觀察窗口。
DEFAULT_WINDOW_SECS: int = 7 * 24 * 3600

# Wilson CI z=1.96 對應 95% confidence；spec §8.1 [62] 採此標準。
WILSON_Z_95: float = 1.96

# Verdict enum；對齊 spec §11.1..§11.4 AC-1/14/15/16 三段語意。
VERDICT_PASS = "PASS"
VERDICT_WARN = "WARN"
VERDICT_FAIL = "FAIL"
VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

# Exit codes（與 engine_watchdog.py 慣例對齊）。
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_CONNECT_ERROR = 2


# ───────────────────────────────────────────────────────────────────────────
# PG 連線
# ───────────────────────────────────────────────────────────────────────────


def connect_pg() -> Any:
    """連線到 PG；fail-closed on missing env / connection failure。

    為什麼 fail-closed：healthcheck 結果會被 QA T+24h post-deploy verify 引用，
    若 silent fallback 到 mock connection，會把 0 sample 誤判為 PASS（false
    negative）。寧可 exit code 2 讓 caller 看到「資料層不通」也不要靜默 PASS。

    Env 變數來源：
      - ``DB_URL`` 完整 connection string（最高優先；對齊 sqlx 慣例）
      - 或拼接 ``POSTGRES_HOST`` / ``POSTGRES_PORT`` / ``POSTGRES_USER`` /
        ``POSTGRES_PASSWORD`` / ``POSTGRES_DB``（與
        ``basic_system_services.env`` 對齊）
    """
    try:
        import psycopg2  # type: ignore
    except ImportError as exc:
        logger.critical("psycopg2 not available: %s", exc)
        sys.exit(EXIT_CONNECT_ERROR)

    db_url = os.environ.get("DB_URL", "").strip()
    if db_url:
        try:
            return psycopg2.connect(db_url)
        except psycopg2.Error as exc:
            logger.critical("PG connect via DB_URL failed: %s", exc)
            sys.exit(EXIT_CONNECT_ERROR)

    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "")

    if not (user and db):
        logger.critical(
            "PG creds missing: need DB_URL or POSTGRES_USER+POSTGRES_DB env"
        )
        sys.exit(EXIT_CONNECT_ERROR)

    try:
        return psycopg2.connect(
            host=host, port=port, user=user, password=password, dbname=db
        )
    except psycopg2.Error as exc:
        logger.critical("PG connect via discrete env failed: %s", exc)
        sys.exit(EXIT_CONNECT_ERROR)


# ───────────────────────────────────────────────────────────────────────────
# Wilson 95% CI（核心統計 — 與 spec §8.1 AC-14 對齊）
# ───────────────────────────────────────────────────────────────────────────


def wilson_ci_95(successes: int, total: int, z: float = WILSON_Z_95) -> tuple[float, float]:
    """Wilson 95% binomial confidence interval。

    為什麼用 Wilson 而非 Normal-approx：spec §11.4 AC-14 強制 Wilson；small-n
    場景下 Normal-approx 邊界會出 (-x, y) 或 (x, 1+y) 違反 binomial domain。
    Wilson 由 ``p_hat + z²/2n`` 平移中心 + ``denom = 1 + z²/n`` rescale 確保
    永遠 ∈ [0, 1]。

    輸入：
      - ``successes``：maker fill / fallback to taker / postonly reject 等
        正向事件數
      - ``total``：attempts / fallback_required / per-engine sample 等分母
      - ``z``：信賴水準（預設 1.96 = 95%）

    輸出 (lower, upper)：
      - ``total <= 0`` → (0.0, 0.0) （由 caller 判 INSUFFICIENT_SAMPLE）
      - 其餘 → 標準 Wilson 雙邊 95% CI
    """
    if total <= 0:
        return (0.0, 0.0)
    p_hat = successes / total
    z2 = z * z
    denom = 1.0 + z2 / total
    center = p_hat + z2 / (2.0 * total)
    spread = z * math.sqrt((p_hat * (1.0 - p_hat) + z2 / (4.0 * total)) / total)
    return ((center - spread) / denom, (center + spread) / denom)


def severity_max(left: str, right: str) -> str:
    """合併兩個 verdict，取較嚴重者；INSUFFICIENT_SAMPLE 視為 WARN-equivalent。

    為什麼：multi-cell / multi-engine_mode 場景下，整體 verdict 要被任一 cell
    的 FAIL 拉下；spec §11.4 AC-14 預期 WARN/FAIL 不會被 PASS cell「沖淡」。
    """
    order = {
        VERDICT_PASS: 0,
        VERDICT_INSUFFICIENT_SAMPLE: 1,
        VERDICT_WARN: 2,
        VERDICT_FAIL: 3,
    }
    return right if order.get(right, 0) > order.get(left, 0) else left


# ───────────────────────────────────────────────────────────────────────────
# Verdict 計算（spec §8.1 [62] threshold ladder）
# ───────────────────────────────────────────────────────────────────────────


def fill_rate_verdict(
    successes: int,
    total: int,
    min_sample: int = 30,
    pass_lower: float = 0.60,
    warn_lower: float = 0.40,
) -> tuple[str, float, float, float]:
    """[62] close_maker_fill_rate Wilson-CI ladder。

    Spec §8.1 line 511-519 + §11.4 AC-14 規格：
      - n < min_sample → INSUFFICIENT_SAMPLE（不放入 PASS/FAIL 分母）
      - Wilson lower ≥ pass_lower → PASS
      - Wilson upper < warn_lower → FAIL
      - 其他 → WARN

    回傳 (verdict, fill_rate, wilson_lower, wilson_upper)。

    注意 PA prompt §1 提到「conservative 25% / median 35% / target 50%」是
    AC-19 14d extended observation 用的不同 gate；spec §8.1 [62] 預設 60/40
    threshold（基準），caller 可透過 CLI 覆寫 pass_lower / warn_lower 改用
    AC-19 ladder。本 helper 不寫死，留 CLI 注入。
    """
    if total < min_sample:
        rate = successes / total if total else 0.0
        return (VERDICT_INSUFFICIENT_SAMPLE, rate, 0.0, 0.0)
    rate = successes / total
    lower, upper = wilson_ci_95(successes, total)
    if lower >= pass_lower:
        verdict = VERDICT_PASS
    elif upper < warn_lower:
        verdict = VERDICT_FAIL
    else:
        verdict = VERDICT_WARN
    return (verdict, rate, lower, upper)


# ───────────────────────────────────────────────────────────────────────────
# 輸出格式
# ───────────────────────────────────────────────────────────────────────────


def emit_result(result: dict, write_file: str | None = None, text_mode: bool = False) -> None:
    """JSON or text 輸出（stdout + optional file）。

    為什麼支援 text_mode：QA T+24h verify 跑 ssh ad-hoc 時 JSON 不方便人讀；
    operator dashboard 整合走 JSON。預設 JSON。
    """
    if text_mode:
        for key, value in result.items():
            print(f"{key}: {value}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    if write_file:
        path = Path(write_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)


# ───────────────────────────────────────────────────────────────────────────
# CLI argparse 範本
# ───────────────────────────────────────────────────────────────────────────


def build_argparser(name: str, description: str, default_window_secs: int = DEFAULT_WINDOW_SECS) -> argparse.ArgumentParser:
    """共享 CLI 範本；保證四個腳本 flag 風格一致。"""
    parser = argparse.ArgumentParser(prog=name, description=description)
    parser.add_argument(
        "--window-secs",
        type=int,
        default=default_window_secs,
        help=f"Observation window in seconds (default {default_window_secs}s = 7d)",
    )
    parser.add_argument(
        "--write-file",
        type=str,
        default=None,
        help="Optional path to write JSON artifact",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Human-readable text output instead of JSON",
    )
    parser.add_argument(
        "--engine-mode",
        type=str,
        default="demo,live_demo",
        help="Comma-separated engine_mode filter (default: demo,live_demo)",
    )
    return parser


def split_engine_modes(modes_csv: str) -> list[str]:
    """CSV → list；去除空白。"""
    return [m.strip() for m in modes_csv.split(",") if m.strip()]


def configure_logging() -> None:
    """統一日誌格式；對齊 engine_watchdog.py。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [PHASE1B-HC] %(levelname)s %(message)s",
    )


# ───────────────────────────────────────────────────────────────────────────
# Enum allowlist（與 V094 spec §2.1.2 + checks_close_maker_audit.py 對齊）
# ───────────────────────────────────────────────────────────────────────────

FALLBACK_REASONS: tuple[str, ...] = (
    "timeout_taker",
    "postonly_reject",
    "cancel_grace_expired",
    "ack_lost",
    "rate_limit_pause_global",
    "rate_limit_backoff_per_symbol",
    "fast_escalate_safety_upgrade",
    "not_attempted_safety_path",
    "engine_shutdown_safety",
    "fallback_to_taker_mandatory",
)

# Safety path 三 enum — healthcheck [63] NULL ladder 必須 exclude 這三個
# （per Consensus-MF-3 + AC-6 + AC-16；V094 spec §2.1.2 line 156）。
SAFETY_FALLBACK_REASONS: tuple[str, ...] = (
    "fast_escalate_safety_upgrade",
    "not_attempted_safety_path",
    "engine_shutdown_safety",
)
