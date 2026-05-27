#!/usr/bin/env bash
# install_pg_dump_cron.sh — P0-OPS-4 GAP-D installer：安裝 PG dump + 30d retention cron。
#
# Spec 來源：
#   docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md
#     §2.3 + §7.2 + §10 GAP-D
#   MIT empirical report:
#     docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--ops_4_gap_bd_pg_backup_restore_research.md
#     §1.5 disk budget / §1.6 schedule
#
# 本 script 不自動 install；operator dry-run + sign-off 後加 OPENCLAW_BACKUP_CRON_APPLY=1 才寫 crontab。
#
# 安裝內容（單一 crontab entry）：
#   - daily 03:00 UTC（per MIT §1.6 crypto Asian off-hours + 避撞 02:00 UTC ml_training_maintenance）
#   - 跑 trading_ai_pg_dump_cron.sh 寫 `$OPENCLAW_BACKUP_ROOT`（預設 $HOME/pg_backups）
#   - 30d retention（per operator 2026-05-27 拍板；MIT §1.5 180-270 GB budget 安全於 842 GB free）
#   - JSONL log + governance_audit_log INSERT（per FA §C audit trail requirement）
#
# 跨平台守門：Linux runtime only；Mac dev refuse exit 2。
#
# 硬邊界：
#   - 不寫 secrets；不改 PG schema；不改 trading_ai DB content
#   - idempotent guard：若 crontab 已有 pg_dump 條目，refuse install 強制 operator 顯式 remove
#   - 路徑不硬編碼（per memory feedback_cross_platform）

set -euo pipefail

# ----- 平台守門：僅 Linux 跑（per MIT draft pattern）-----
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_pg_dump_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本 install script 必在 Linux runtime host (trade-core) 跑；Mac dev 走 ssh trade-core。" >&2
    exit 2
fi

# ----- env / 預設值 -----
OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
OPENCLAW_BACKUP_ROOT="${OPENCLAW_BACKUP_ROOT:-$HOME/pg_backups}"
# 預設 30d（per operator 2026-05-27 拍板取代原 15d）。
OPENCLAW_BACKUP_RETENTION_DAYS="${OPENCLAW_BACKUP_RETENTION_DAYS:-30}"
OPENCLAW_BACKUP_HOUR_UTC="${OPENCLAW_BACKUP_HOUR_UTC:-3}"   # default 03:00 UTC

# ----- pre-flight -----
if ! command -v pg_dump >/dev/null 2>&1; then
    echo "ERROR: pg_dump not found on PATH. Install postgresql-client matching PG 16.x." >&2
    exit 3
fi
if [[ ! -f "$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env" ]]; then
    echo "ERROR: secrets env file missing: $OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env" >&2
    exit 4
fi
mkdir -p "$OPENCLAW_BACKUP_ROOT"
mkdir -p "$OPENCLAW_DATA_DIR/logs"

# ----- idempotent guard：若 crontab 已有 pg_dump entry，refuse 強制 operator 顯式 remove -----
if crontab -l 2>/dev/null | grep -qE '(pg_dump|trading_ai_pg_dump_cron\.sh)'; then
    echo "SKIP: existing pg_dump cron entry detected; not installing (manually remove first)." >&2
    crontab -l | grep -E '(pg_dump|trading_ai_pg_dump_cron\.sh)' >&2
    exit 0
fi

# ----- 組 crontab entry -----
WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/trading_ai_pg_dump_cron.sh"
if [[ ! -x "$WRAPPER" ]]; then
    echo "ERROR: wrapper not executable: $WRAPPER" >&2
    echo "       chmod +x \"$WRAPPER\" 後再跑 install。" >&2
    exit 5
fi

# ----- env value validation：防 cron 特殊字 / 空格 / 過長 entry 解析錯亂（E2 round 2 MED-3）-----
# cron 對 `%` 解為 stdin 換行（除非 escape `\%`）；space 拆 token 破解析；
# control char / newline 直接 corrupt crontab；長度 > 200 通常是 ENV 污染。
# 任一不合即 abort 強制 operator 顯式覆寫（避免 silent corruption）。
_validate_cron_env_value() {
    local name="$1"
    local value="$2"
    if [[ -z "$value" ]]; then
        echo "ERROR: cron env value empty: ${name}" >&2
        exit 6
    fi
    if [[ ${#value} -gt 200 ]]; then
        echo "ERROR: cron env value too long (>200 chars): ${name}=${value}" >&2
        echo "       crontab line size limit risk；請縮短 path 或 abort。" >&2
        exit 6
    fi
    # cron 特殊字 / shell 特殊字 / 空格 / 控制字
    if [[ "$value" =~ [[:space:]%[:cntrl:]\"\'\\\$\`] ]]; then
        echo "ERROR: cron-conflict character in ${name}=${value}" >&2
        echo "       Disallowed: space / % (cron stdin newline) / control / quote / backslash / \$ / backtick" >&2
        echo "       請用 ASCII path 無 special char；或 abort 並用 systemd timer 替代 cron。" >&2
        exit 6
    fi
}

_validate_cron_env_value "OPENCLAW_BASE_DIR" "$OPENCLAW_BASE_DIR"
_validate_cron_env_value "OPENCLAW_DATA_DIR" "$OPENCLAW_DATA_DIR"
_validate_cron_env_value "OPENCLAW_SECRETS_ROOT" "$OPENCLAW_SECRETS_ROOT"
_validate_cron_env_value "OPENCLAW_BACKUP_ROOT" "$OPENCLAW_BACKUP_ROOT"
_validate_cron_env_value "OPENCLAW_BACKUP_RETENTION_DAYS" "$OPENCLAW_BACKUP_RETENTION_DAYS"
_validate_cron_env_value "OPENCLAW_BACKUP_HOUR_UTC" "$OPENCLAW_BACKUP_HOUR_UTC"
_validate_cron_env_value "WRAPPER" "$WRAPPER"

# 為什麼不用 printf %q quoting：cron 不跑 full shell parser；`%` 即使被
# single-quote / backslash escape 在某些 cron impl 仍當 stdin newline；
# 唯一可靠路徑是上面 validation reject special char，這裡組裝就 plain。
ENTRY="0 ${OPENCLAW_BACKUP_HOUR_UTC} * * * OPENCLAW_BASE_DIR=${OPENCLAW_BASE_DIR} OPENCLAW_DATA_DIR=${OPENCLAW_DATA_DIR} OPENCLAW_SECRETS_ROOT=${OPENCLAW_SECRETS_ROOT} OPENCLAW_BACKUP_ROOT=${OPENCLAW_BACKUP_ROOT} OPENCLAW_BACKUP_RETENTION_DAYS=${OPENCLAW_BACKUP_RETENTION_DAYS} ${WRAPPER} >> ${OPENCLAW_DATA_DIR}/logs/trading_ai_pg_dump_cron.cron.log 2>&1"

echo "------- proposed crontab entry -------"
echo "$ENTRY"
echo "--------------------------------------"
echo "Retention: ${OPENCLAW_BACKUP_RETENTION_DAYS}d"
echo "Backup root: ${OPENCLAW_BACKUP_ROOT}"
echo "Schedule: 0 ${OPENCLAW_BACKUP_HOUR_UTC} * * * UTC"
echo "EXCLUDE: learning.decision_features_evaluations + *_damaged_*"
echo "audit row: learning.governance_audit_log (event_type=pg_dump_completed|pg_dump_failed)"

if [[ "${OPENCLAW_BACKUP_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_BACKUP_CRON_APPLY=1 to actually install."
    echo
    echo "預檢必跑：在 OPENCLAW_BACKUP_CRON_APPLY=1 前確認"
    echo "  1. V113 (governance_audit_log_pg_dump_event_types) 已 land Linux PG（否則 audit INSERT 撞 CHECK）"
    echo "  2. $OPENCLAW_BACKUP_ROOT 寫權限正常 / 至少 270 GB free（30d × 9 GB upper bound）"
    echo "  3. 手動跑 wrapper dry-run（OPENCLAW_BACKUP_CRON_APPLY=0 ${WRAPPER}）驗 pg_dump 邏輯"
    exit 0
fi

# ----- 實際 install（僅 OPENCLAW_BACKUP_CRON_APPLY=1 才走到）-----
( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -
echo "INSTALLED: pg_dump cron entry added. Verify with: crontab -l | grep pg_dump"
