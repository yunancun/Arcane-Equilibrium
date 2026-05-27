#!/usr/bin/env python3
"""check_pg_dump_freshness — P0-OPS-4 GAP-D Python 主入口（FA acceptance §E #7）。

MODULE_NOTE:
  PA spec §10.B.2 9-invariant dashboard 接點。本 healthcheck 是 P0-OPS-4 GAP-D
  PG dump cron 健康狀態的 SSOT 入口，呼叫者：
    1. operator ad-hoc：`python3 .../check_pg_dump_freshness.py --status`
    2. passive_wait_healthcheck.checks_cron_heartbeat.check_pg_dump_freshness()
       wrapper 引用本檔 JSON 結果（per A2 wire）
    3. FA acceptance §E #7 7-check 驗收：`passive_wait_healthcheck.sh --quiet`
       含本 check 第 7 個 slot

  與 sidecar `helper_scripts/cron/verify_pg_dump.sh` 對齊 5 個 file-system check：
    1. backup dir 存在 + 可寫
    2. 最新 trading_ai_*.dump mtime < 26h（cron daily 03:00 UTC + 2h grace）
    3. dump 大小 > 1 MB（防 zero-byte partial-fail）
    4. md5sum 對齊當日 JSONL log entry
    5. retention policy 真正生效（最舊 dump ≤ retention+1d）

  追加第 6 個 L0 schema coverage smoke test（per FA §C.5 + PA §10.B.6）：
    6. `pg_restore --list <latest> | grep earn_movement_log` ≥1 entry
       （Earn V100 audit trail；MIT C-4 / BB OPS-3 C-4 acceptance）

  追加第 7 個 governance_audit_log trail check（per PA §10.B.1 + FA §C / §E #6）：
    7. last `pg_dump_completed` event ts < 26h（V113 enum 已 land 後才可驗；
       未 apply 時 INSUFFICIENT_SAMPLE-skip 不阻擋）

  為什麼共 7 check 而非 verify_pg_dump.sh 的 5：
    operator SSH ad-hoc 場景下 verify_pg_dump.sh 比 Python 快（不需 venv），
    覆 5 check 已夠。Python 主入口 cover 完整 7 check 提供 FA / governance
    audit dashboard 接點。第 6/7 check 須 subprocess pg_restore + psycopg2
    PG query，不適合 Bash side-car。

硬邊界：
  - Linux only（`sys.platform != 'linux'` refuse with exit 2）
  - stdlib + psycopg2（passive_wait_healthcheck venv 既有）only，不引入新依賴
  - 不寫 PG / 不 mutate 任何 governance state；純 read-only
  - V113 未 apply / dump cron 尚未 fire → INSUFFICIENT_SAMPLE-skip（fail-soft
    避免阻擋 first-day deploy）；real FAIL 留給 dump 真實寫入過後 staleness 偵測

CLI:
  python3 check_pg_dump_freshness.py [--status] [--text] [--write-file PATH]

Exit codes（對齊 [80] / _common.py 慣例）:
  0 = PASS / INSUFFICIENT_SAMPLE（dump 尚未 fire / V113 未 land）
  1 = WARN / FAIL（任一 check 違反閾值）
  2 = environment / connect / platform error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# 允許 standalone script + module 同時被呼叫（對齊 80_liquidation_pulse_freshness.py pattern）
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _common import (  # noqa: E402
    EXIT_CONNECT_ERROR,
    EXIT_FAIL,
    EXIT_PASS,
    VERDICT_FAIL,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_PASS,
    VERDICT_WARN,
    configure_logging,
    connect_pg,
    emit_result,
    severity_max,
)

# ───────────────────────────────────────────────────────────────────────────
# 預設值（與 verify_pg_dump.sh + trading_ai_pg_dump_cron.sh 對齊）
# ───────────────────────────────────────────────────────────────────────────

# Daily cron 03:00 UTC + 2h grace = 26h；對齊 PA spec §10.B.2 expected ts < 26h。
DEFAULT_MAX_AGE_HOURS: int = 26

# 預設 retention 30d（per operator 2026-05-27 拍板；對齊 trading_ai_pg_dump_cron.sh）
DEFAULT_RETENTION_DAYS: int = 30

# Min dump size = 1 MB；trading_ai compressed estimate 6-9 GB，> 1MB 為 min sanity。
MIN_DUMP_SIZE_BYTES: int = 1024 * 1024


def _platform_guard() -> None:
    """Linux only。Mac 跑會誤判 stat 格式（BSD vs GNU）。"""
    if sys.platform != "linux":
        sys.stderr.write(
            f"ERROR: check_pg_dump_freshness.py requires Linux runtime "
            f"(current sys.platform={sys.platform!r}).\n"
            f"       Mac dev 走 ssh trade-core；本 check 依賴 GNU stat 與 "
            f"Linux pg_dump 路徑語義。\n"
        )
        sys.exit(EXIT_CONNECT_ERROR)


def _resolve_paths() -> dict[str, Path]:
    """解析 backup / log / sentinel / heartbeat 路徑（與 cron wrapper env 完全對齊）。

    對齊 trading_ai_pg_dump_cron.sh:46-55；任何 env override 必鏡，否則 healthcheck
    讀的不是 cron 真實寫入路徑（false-PASS 風險）。
    """
    home = Path.home()
    backup_root = Path(
        os.environ.get("OPENCLAW_BACKUP_ROOT", str(home / "pg_backups"))
    )
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return {
        "backup_root": backup_root,
        "data_dir": data_dir,
        "log_dir": data_dir / "logs",
        "jsonl": data_dir / "logs" / "trading_ai_pg_dump_cron.jsonl",
        "sentinel": backup_root / ".last_pg_dump",
        "heartbeat": data_dir / "cron_heartbeat" / "trading_ai_pg_dump.last_fire",
    }


def _list_dumps(backup_root: Path) -> list[Path]:
    """列出 backup_root 下所有 trading_ai_*.dump，by mtime DESC。

    不存目錄 / 空目錄 → 回空 list（caller 判 INSUFFICIENT_SAMPLE）。
    """
    if not backup_root.is_dir():
        return []
    try:
        dumps = [
            p for p in backup_root.iterdir()
            if p.is_file() and p.name.startswith("trading_ai_") and p.name.endswith(".dump")
        ]
    except OSError:
        return []
    dumps.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dumps


def _stat_mtime(path: Path) -> float | None:
    """回傳 mtime epoch；不存在或 stat 失敗回 None。"""
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _md5sum(path: Path) -> str | None:
    """純 stdlib md5sum；對齊 verify_pg_dump.sh check 4。"""
    import hashlib

    h = hashlib.md5()  # noqa: S324 — checksum 對齊 cron wrapper md5sum 慣例（非 security）
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _read_jsonl_md5(jsonl_path: Path, dump_file: Path) -> str | None:
    """從 trading_ai_pg_dump_cron.jsonl 末 50 行找 dump_file=指定 + status=ok 的 md5。

    對齊 verify_pg_dump.sh:88-89 的 jq 邏輯，純 stdlib 不依 jq。
    """
    if not jsonl_path.is_file():
        return None
    try:
        # 末 50 行；檔小直接 read all（cron daily fire；30d retention ≈ 30 行）
        lines = jsonl_path.read_text(encoding="utf-8").splitlines()[-50:]
    except OSError:
        return None
    target = str(dump_file)
    md5 = None
    # 取最末符合的一條（newest takes precedence）
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("dump_file") == target and obj.get("status") == "ok":
            md5_val = obj.get("md5")
            if isinstance(md5_val, str) and md5_val:
                md5 = md5_val
    return md5


# ───────────────────────────────────────────────────────────────────────────
# 個別 check 函數（5 個對齊 verify_pg_dump.sh + 1 個 L0 + 1 個 audit log）
# ───────────────────────────────────────────────────────────────────────────


def check_1_backup_dir(paths: dict[str, Path]) -> tuple[str, str]:
    """[1] backup dir 存在 + 可寫。

    為什麼 missing → INSUFFICIENT_SAMPLE 而非 FAIL：cron 首次 fire 前
    `trading_ai_pg_dump_cron.sh:57` 才 mkdir，pre-deploy / install_pg_dump_cron.sh
    未跑時這條目錄不存在是 expected state，不該阻擋 first-day deploy 的
    healthcheck pass。dir 存在但非 dir / 不可寫才視為配置錯誤 FAIL。
    """
    backup_root = paths["backup_root"]
    if not backup_root.exists():
        return (
            VERDICT_INSUFFICIENT_SAMPLE,
            f"backup dir missing: {backup_root} "
            "(cron not yet fired / install_pg_dump_cron.sh not run)",
        )
    if not backup_root.is_dir():
        return (VERDICT_FAIL, f"backup path is not a directory: {backup_root}")
    if not os.access(backup_root, os.W_OK):
        return (VERDICT_FAIL, f"backup dir not writable: {backup_root}")
    return (VERDICT_PASS, f"backup dir OK ({backup_root})")


def check_2_freshness(
    paths: dict[str, Path], max_age_hours: int, now_epoch: float
) -> tuple[str, str]:
    """[2] 最新 dump mtime < max_age_hours（致命 check：> threshold → FAIL）。

    INSUFFICIENT_SAMPLE：尚未有任何 dump 寫入（cron 未 fire / 剛部署）。
    """
    dumps = _list_dumps(paths["backup_root"])
    if not dumps:
        return (
            VERDICT_INSUFFICIENT_SAMPLE,
            f"no trading_ai_*.dump found in {paths['backup_root']} "
            "(cron not yet fired / fresh deploy)",
        )
    latest = dumps[0]
    mtime = _stat_mtime(latest)
    if mtime is None:
        return (VERDICT_FAIL, f"stat failed on latest dump: {latest}")
    age_hours = (now_epoch - mtime) / 3600.0
    if age_hours > max_age_hours:
        return (
            VERDICT_FAIL,
            f"latest dump stale {age_hours:.1f}h > {max_age_hours}h: {latest.name}",
        )
    return (
        VERDICT_PASS,
        f"latest dump fresh {age_hours:.1f}h: {latest.name}",
    )


def check_3_size(paths: dict[str, Path]) -> tuple[str, str]:
    """[3] dump 大小 > 1 MB（致命 check：partial-fail → FAIL）。"""
    dumps = _list_dumps(paths["backup_root"])
    if not dumps:
        return (
            VERDICT_INSUFFICIENT_SAMPLE,
            "no dump file to size-check (covered by check[2])",
        )
    latest = dumps[0]
    try:
        size_bytes = latest.stat().st_size
    except OSError as e:
        return (VERDICT_FAIL, f"stat failed: {latest}: {e}")
    if size_bytes < MIN_DUMP_SIZE_BYTES:
        return (
            VERDICT_FAIL,
            f"dump too small {size_bytes}B < {MIN_DUMP_SIZE_BYTES}B (partial?)",
        )
    return (
        VERDICT_PASS,
        f"dump size {size_bytes / (1024 * 1024 * 1024):.2f}GB ({size_bytes}B)",
    )


def check_4_md5_match(paths: dict[str, Path]) -> tuple[str, str]:
    """[4] md5sum 對齊 JSONL log entry（drift detect tampering / partial write）。

    JSONL 缺 / 對應 entry 缺 → WARN（不 FAIL；cron 首日 / log rotate 等正當失誤）。
    """
    dumps = _list_dumps(paths["backup_root"])
    if not dumps:
        return (
            VERDICT_INSUFFICIENT_SAMPLE,
            "no dump file to md5-check (covered by check[2])",
        )
    latest = dumps[0]
    jsonl_md5 = _read_jsonl_md5(paths["jsonl"], latest)
    if jsonl_md5 is None:
        return (
            VERDICT_WARN,
            f"no recent ok JSONL entry for {latest.name} "
            f"(jsonl={paths['jsonl']})",
        )
    actual_md5 = _md5sum(latest)
    if actual_md5 is None:
        return (VERDICT_FAIL, f"md5sum read failed: {latest}")
    if jsonl_md5 != actual_md5:
        return (
            VERDICT_FAIL,
            f"md5 drift recorded={jsonl_md5} actual={actual_md5}",
        )
    return (VERDICT_PASS, f"md5 match {jsonl_md5}")


def check_5_retention(
    paths: dict[str, Path], retention_days: int, now_epoch: float
) -> tuple[str, str]:
    """[5] retention prune 真正生效（oldest dump ≤ retention+1d 容差）。"""
    dumps = _list_dumps(paths["backup_root"])
    if not dumps:
        return (
            VERDICT_INSUFFICIENT_SAMPLE,
            "no dump file to retention-check (covered by check[2])",
        )
    oldest = dumps[-1]
    mtime = _stat_mtime(oldest)
    if mtime is None:
        return (VERDICT_WARN, f"stat failed on oldest dump: {oldest}")
    age_days = (now_epoch - mtime) / 86400.0
    max_days = retention_days + 1
    if age_days > max_days:
        return (
            VERDICT_WARN,
            f"oldest dump {age_days:.1f}d > retention {retention_days}d "
            f"(prune not running? oldest={oldest.name})",
        )
    return (
        VERDICT_PASS,
        f"oldest dump {age_days:.1f}d (retention {retention_days}d)",
    )


def check_6_l0_schema_coverage(paths: dict[str, Path]) -> tuple[str, str]:
    """[6] L0 schema coverage smoke test（FA §C.5 + PA §10.B.6）。

    subprocess pg_restore --list <latest> | grep earn_movement_log；
    應 ≥ 1 entry（table + index + comment 通常 3+ entry，最低 1 entry = 表本身）。

    pg_restore 缺（PG client 未裝）→ WARN；timeout / 非 0 exit → FAIL。
    """
    dumps = _list_dumps(paths["backup_root"])
    if not dumps:
        return (
            VERDICT_INSUFFICIENT_SAMPLE,
            "no dump file to schema-check (covered by check[2])",
        )
    latest = dumps[0]

    # 為什麼用 shutil.which：pg_restore 在 PG client 套件內，部分 Linux 部署只裝
    # libpq 不裝 pg_restore；WARN 而非 FAIL 是因「dump 本身已在」是更可信指標。
    import shutil

    if shutil.which("pg_restore") is None:
        return (
            VERDICT_WARN,
            "pg_restore CLI not available (PG client not fully installed); skip",
        )

    try:
        # --list 純文字 TOC dump；不解壓 / 不還原資料；< 1s
        # 60s timeout 足夠 — empirical 6-9GB dump 的 TOC < 5s
        result = subprocess.run(  # noqa: S603 — shell=False + 固定 cmd 安全
            ["pg_restore", "--list", str(latest)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return (VERDICT_FAIL, f"pg_restore --list timeout (>60s): {latest.name}")
    except OSError as e:
        return (VERDICT_FAIL, f"pg_restore subprocess failed: {e}")

    if result.returncode != 0:
        stderr_tail = (result.stderr or "")[-200:].replace("\n", " ")
        return (
            VERDICT_FAIL,
            f"pg_restore --list rc={result.returncode}: {stderr_tail}",
        )

    # grep earn_movement_log；計 entry 數（≥1 = PASS，≥3 = ideal per FA §E #2）
    matched = [
        line for line in result.stdout.splitlines()
        if "earn_movement_log" in line
    ]
    if not matched:
        return (
            VERDICT_FAIL,
            f"L0 schema coverage drift: earn_movement_log absent from "
            f"{latest.name} TOC (V100 schema regression?)",
        )
    return (
        VERDICT_PASS,
        f"L0 schema coverage OK: {len(matched)} earn_movement_log entries in TOC",
    )


def check_7_audit_trail(max_age_hours: int) -> tuple[str, str]:
    """[7] last pg_dump_completed event ts < max_age_hours（governance_audit_log）。

    V113 未 apply（CHECK constraint 缺 pg_dump_completed 值）→ INSUFFICIENT_SAMPLE-
    skip with note；cron 從未 fire（0 row）→ INSUFFICIENT_SAMPLE。

    V113 已 apply 且有 row 但 stale → FAIL。
    """
    try:
        conn = connect_pg()
    except SystemExit:
        # connect_pg() 內部 sys.exit(EXIT_CONNECT_ERROR) 不該打斷別的 check；
        # 但我們呼叫前已平台 / 環境 guard，這條僅做 defensive 包裝。
        raise
    try:
        with conn.cursor() as cur:
            # 先驗 CHECK 是否含 'pg_dump_completed'（V113 已 apply？）
            cur.execute(
                """
                SELECT pg_get_constraintdef(c.oid)
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'learning'
                  AND t.relname = 'governance_audit_log'
                  AND c.contype = 'c'
                  AND c.conname = 'governance_audit_log_event_type_check'
                """
            )
            row = cur.fetchone()
            check_def = row[0] if row else None
            if not check_def or "pg_dump_completed" not in check_def:
                return (
                    VERDICT_INSUFFICIENT_SAMPLE,
                    "V113 not applied yet (governance_audit_log CHECK lacks "
                    "pg_dump_completed); skip until migration lands",
                )

            cur.execute(
                """
                SELECT
                    MAX(ts) AS last_ts,
                    COUNT(*) AS n
                FROM learning.governance_audit_log
                WHERE event_type = 'pg_dump_completed'
                  AND ts > NOW() - INTERVAL '7 day'
                """
            )
            row = cur.fetchone() or (None, 0)
            last_ts = row[0]
            n_rows = int(row[1] or 0)

            if n_rows == 0:
                return (
                    VERDICT_INSUFFICIENT_SAMPLE,
                    "no pg_dump_completed event in last 7d (cron not yet fired)",
                )

            # last_ts 是 timezone-aware datetime；用 UTC now diff
            now_utc = datetime.now(timezone.utc)
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            age_hours = (now_utc - last_ts).total_seconds() / 3600.0
            if age_hours > max_age_hours:
                return (
                    VERDICT_FAIL,
                    f"last pg_dump_completed {age_hours:.1f}h > {max_age_hours}h "
                    f"(audit trail stale; 7d window n={n_rows})",
                )
            return (
                VERDICT_PASS,
                f"last pg_dump_completed {age_hours:.1f}h "
                f"(7d window n={n_rows})",
            )
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────────────────
# Orchestrator
# ───────────────────────────────────────────────────────────────────────────


def run(
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict:
    """跑 7 個 check 並合併 verdict。"""
    import time

    paths = _resolve_paths()
    now_epoch = time.time()

    checks: list[tuple[str, str, str]] = []  # (check_id, verdict, note)

    v, m = check_1_backup_dir(paths)
    checks.append(("[1]", v, m))

    v, m = check_2_freshness(paths, max_age_hours, now_epoch)
    checks.append(("[2]", v, m))

    v, m = check_3_size(paths)
    checks.append(("[3]", v, m))

    v, m = check_4_md5_match(paths)
    checks.append(("[4]", v, m))

    v, m = check_5_retention(paths, retention_days, now_epoch)
    checks.append(("[5]", v, m))

    v, m = check_6_l0_schema_coverage(paths)
    checks.append(("[6]", v, m))

    # check[7] 依 PG；若 connect_pg fail 整體 exit 2（_common.connect_pg sys.exit）
    v, m = check_7_audit_trail(max_age_hours)
    checks.append(("[7]", v, m))

    overall = VERDICT_PASS
    for _, v, _ in checks:
        overall = severity_max(overall, v)

    return {
        "metric": "pg_dump_freshness",
        "check_id": "[pg_dump]",
        "namespace": "canary",
        "spec": (
            "PA spec 2026-05-26 §10.B.2 + FA acceptance 2026-05-27 §E #7 "
            "+ §C.5 (Earn V100 audit trail) + §C.1 (governance_audit_log)"
        ),
        "thresholds": {
            "max_age_hours": max_age_hours,
            "retention_days": retention_days,
            "min_dump_size_bytes": MIN_DUMP_SIZE_BYTES,
        },
        "paths": {k: str(v) for k, v in paths.items()},
        "checks": [
            {"id": cid, "verdict": v, "note": m}
            for cid, v, m in checks
        ],
        "verdict": overall,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_pg_dump_freshness",
        description=(
            "PG dump freshness 7-check （FA acceptance §E #7：5 verify_pg_dump.sh "
            "check + L0 schema coverage smoke + governance_audit_log trail）"
        ),
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help=(
            "Print verdict + 7 check JSON; exit 0 if PASS/INSUFFICIENT_SAMPLE, "
            "1 if WARN/FAIL, 2 if env error. Default mode; flag preserved for "
            "passive_wait_healthcheck wrapper API contract."
        ),
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=DEFAULT_MAX_AGE_HOURS,
        help=(
            f"Latest dump freshness ceiling in hours "
            f"(default {DEFAULT_MAX_AGE_HOURS}h = 24h cron + 2h grace)"
        ),
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help=(
            f"Expected retention window in days "
            f"(default {DEFAULT_RETENTION_DAYS}d per operator 2026-05-27 拍板)"
        ),
    )
    parser.add_argument(
        "--write-file",
        type=str,
        default=None,
        help="Optional JSON artifact write path.",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Human-readable text output instead of JSON.",
    )
    return parser.parse_args()


def main() -> int:
    _platform_guard()
    configure_logging()
    args = _parse_args()

    try:
        result = run(
            max_age_hours=args.max_age_hours,
            retention_days=args.retention_days,
        )
    except SystemExit:
        # _common.connect_pg() 用 sys.exit(EXIT_CONNECT_ERROR) 報缺 env / 連不上 PG；
        # 直接 propagate（caller wrapper passive_wait_healthcheck.sh 一致 exit code）
        raise

    emit_result(result, write_file=args.write_file, text_mode=args.text)

    if result["verdict"] in (VERDICT_FAIL, VERDICT_WARN):
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
