#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# replay_key_rotation_check.sh — REF-20 P2a-S1 (Wave 2 Batch 1)
# Daily cron: detect replay_signing_key approaching 90d rotation due
# 每日 cron：偵測 replay_signing_key 接近 90d rotation 期限
# ═══════════════════════════════════════════════════════════════════════════
#
# MODULE_NOTE (EN): REF-20 V3 §3 G9 + §5 spec a 90-day rotation target for the
#   replay manifest signing key (HMAC-SHA256). Runbook
#   `docs/runbooks/replay_signing_key_rotation.md` §4 trigger condition is
#   "rotation_due_at within 7d → PM schedule". This cron probes that
#   condition daily and emits an ALERT (exit 1 + governance audit row +
#   stderr) when any env's key is within 7 days of expiry, so that the
#   90d window never silently lapses into the `key_expired` fail-mode (V3
#   §5 / runbook §6).
#
#   Source-of-truth priority:
#   1. `replay.replay_signing_keys` archive table (V042, reserved per
#      `sql/migrations/REF-20_RESERVATION.md`) — preferred when present.
#   2. Filesystem mtime + 90d rule fallback — used when V042 has not yet
#      landed (current state of the codebase as of 2026-05-03).
#   The fallback is intentional: T8 already shipped the key generation
#   script before V042 lands, so daily rotation hygiene must work even
#   without the archive table.
#
#   Idempotency: this script is read-only (no key gen, no file move, no
#   DB write except a governance_audit_log INSERT on ALERT). Re-running
#   the same day on the same key state yields identical exit code.
#
# MODULE_NOTE (中): REF-20 V3 §3 G9 + §5 規定 replay manifest signing key
#   （HMAC-SHA256）90 天輪替目標。Runbook
#   `docs/runbooks/replay_signing_key_rotation.md` §4 觸發條件為
#   "rotation_due_at 距今 ≤7d → PM 排程"。本 cron 每日檢查該條件，
#   任何 env 的 key 距期限 ≤7d 即發 ALERT（exit 1 + governance audit
#   row + stderr），確保 90d 視窗永不靜默過期落入 `key_expired`
#   fail-mode（V3 §5 / runbook §6）。
#
#   權威來源優先級：
#   1. `replay.replay_signing_keys` archive table（V042，per
#      `sql/migrations/REF-20_RESERVATION.md` 預留）— 存在時優先。
#   2. 檔案 mtime + 90d 規則 fallback — V042 尚未 land 時使用
#      （2026-05-03 codebase 當前狀態）。
#   fallback 是設計的：T8 已 land key 生成腳本但 V042 還在路上，
#   所以日常輪替衛生必須在無 archive table 時也能 work。
#
#   Idempotent：本腳本 read-only（不生成 key、不 file move、僅在
#   ALERT 時 INSERT governance_audit_log row）。同日對同一 key 狀態
#   重跑得到相同 exit code。
#
# Spec source / 規格來源:
#   - REF-20 V3 §3 G9 (90d/180d/key separation invariants)
#   - REF-20 V3 §5 (manifest signature, 4 fail-mode audit)
#   - workplan R20-P2a-S1 (Wave 2 Batch 1)
#   - runbook §4 + §4.3 + §6
#   - generate_replay_signing_key.sh (T8 commit 6d9977e)
#   - sql/migrations/REF-20_RESERVATION.md V042
#
# Suggested cron entry (operator manually adds via `crontab -e`):
# 建議 cron 條目（operator `crontab -e` 加）：
#   0 9 * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/replay_key_rotation_check.sh"
#
# Exit codes:
#   0   all envs healthy (rotation_due_at > NOW + 7d on every key file)
#   1   at least one env has key approaching/past expiry (ALERT logged)
#   2   environment misconfigured (OPENCLAW_BASE_DIR / OPENCLAW_SECRETS_DIR)
#
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ─── Configuration / 配置 ───────────────────────────────────────────
# Base + data paths follow CLAUDE.md §六 cross-platform path policy.
# Mac dev sets OPENCLAW_BASE_DIR explicitly; Linux defaults below.
# Mac dev 須顯式設 OPENCLAW_BASE_DIR；Linux 預設下方。
BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
SECRETS_DIR="${OPENCLAW_SECRETS_DIR:-$HOME/BybitOpenClaw/secrets/secret_files/bybit}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/replay_key_rotation_check.log"

# Window thresholds / 視窗閾值
ROTATION_DAYS=90
ALERT_THRESHOLD_DAYS=7

# Envs covered by this check (mirrors generate_replay_signing_key.sh §1).
# 涵蓋的 env（鏡像 generate_replay_signing_key.sh §1）。
ENVS=(paper demo live)

# Need LOG_DIR before any append; mirror edge_label_backfill_cron.sh pattern.
# 在任何寫 LOG 前先確保 LOG_DIR 存在；對齊 edge_label_backfill_cron.sh 模式。
mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# ─── Sanity / 基本健全 ───────────────────────────────────────────────
if [[ ! -d "$SECRETS_DIR" ]]; then
    echo "[$(ts)] FATAL: OPENCLAW_SECRETS_DIR does not exist: $SECRETS_DIR" \
        | tee -a "$LOG" >&2
    exit 2
fi

# ─── Overlap lock (mirror edge_label_backfill_cron.sh SW-006 pattern) ────
# Daily cron is short, but lock guards against accidental manual + cron overlap.
# 防止手動執行與 cron 同時跑（SW-006 鎖 pattern）。
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/replay_key_rotation_check.lock.d"
mkdir -p "$LOCK_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: replay_key_rotation_check already running (lock held)" \
        >> "$LOG"
    exit 0
fi
release_lock() { rmdir "$LOCK_DIR" 2>/dev/null || true; }
trap release_lock EXIT INT TERM

# ─── Optional: PG creds for V042 query / V042 查詢用的 PG creds（可選） ──
# Mirror edge_label_backfill_cron.sh PG sourcing pattern. Best-effort:
# if creds missing OR V042 not yet in DB, fall back to filesystem mtime.
# 對齊 edge_label_backfill_cron.sh PG creds sourcing。Best-effort：creds
# 缺失或 V042 還沒 land 時 fallback 到 filesystem mtime。
PG_AVAILABLE=0
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ -f "$ENV_FILE" ]]; then
    PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_DB=$(grep '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_HOST=$(grep '^POSTGRES_HOST=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_PORT=$(grep '^POSTGRES_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_HOST="${PG_HOST:-127.0.0.1}"
    PG_PORT="${PG_PORT:-5432}"
    if [[ -n "$PG_PASS" && -n "$PG_USER" && -n "$PG_DB" ]]; then
        export OPENCLAW_DATABASE_URL="postgresql://redacted@${PG_HOST}:${PG_PORT}/${PG_DB}"
        if command -v psql >/dev/null 2>&1; then
            PG_AVAILABLE=1
        fi
    fi
fi

# ─── V042 archive table existence probe / V042 表存在偵測 ─────────────
# Returns 0 if `replay.replay_signing_keys` table exists; non-zero otherwise.
# Cheap query — no row scan; just information_schema lookup.
# 偵測 `replay.replay_signing_keys` 表是否存在。輕量 — 僅 information_schema 查表存在。
v042_table_present() {
    if [[ "$PG_AVAILABLE" -ne 1 ]]; then
        return 1
    fi
    psql "$OPENCLAW_DATABASE_URL" -tAc \
        "SELECT 1 FROM information_schema.tables WHERE table_schema='replay' AND table_name='replay_signing_keys' LIMIT 1;" \
        2>/dev/null | grep -q '^1$'
}

# ─── Per-env rotation_due_at probe / 每 env rotation_due_at 探查 ──────
# Args: $1 = env name (paper|demo|live)
# Stdout: ISO-8601 UTC timestamp of rotation_due_at (or empty on miss/fallback fail).
# Stderr: brief reason if probe failed.
# 標準輸出：rotation_due_at ISO-8601 UTC（探查失敗為空）。
probe_rotation_due_at() {
    local env_name="$1"
    local key_path="${SECRETS_DIR}/${env_name}/replay_signing_key"
    local due_at=""

    # Source 1: V042 archive table (preferred) / V042 表（首選）
    if v042_table_present; then
        # Active key per env: status='active'.
        # 取 active 狀態的 key（每 env 至多 1 row per runbook §8 audit）。
        due_at=$(psql "$OPENCLAW_DATABASE_URL" -tAc \
            "SELECT to_char(rotation_due_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') FROM replay.replay_signing_keys WHERE env='${env_name}' AND status='active' ORDER BY generated_at DESC LIMIT 1;" \
            2>/dev/null | tr -d '[:space:]' || true)
        if [[ -n "$due_at" ]]; then
            echo "$due_at"
            return 0
        fi
        # Table exists but no active row for env — that itself is anomalous,
        # surface via empty + log. Caller treats as ALERT (key_missing-adjacent).
        # 表存在但該 env 無 active row — 異常，回空字串 + log，由 caller 視為 ALERT。
        echo "[$(ts)] WARN: V042 present but no active row for env=${env_name}" >> "$LOG"
    fi

    # Source 2: Filesystem mtime fallback / 檔案 mtime fallback
    # rotation_due_at = mtime + 90d; key_path missing → empty (ALERT).
    # rotation_due_at = mtime + 90d；檔案不存在 → 回空字串（ALERT）。
    if [[ ! -f "$key_path" ]]; then
        echo "[$(ts)] WARN: key file missing for env=${env_name}: $key_path" >> "$LOG"
        return 0
    fi

    # Cross-platform mtime extraction (BSD stat on macOS, GNU stat on Linux).
    # 跨平台 mtime 提取（macOS BSD stat / Linux GNU stat）。
    local mtime_epoch
    if mtime_epoch=$(stat -f '%m' "$key_path" 2>/dev/null); then
        : # macOS / BSD branch
    elif mtime_epoch=$(stat -c '%Y' "$key_path" 2>/dev/null); then
        : # Linux / GNU branch
    else
        echo "[$(ts)] WARN: cannot stat mtime for $key_path" >> "$LOG"
        return 0
    fi

    # Compute mtime + 90d as UTC ISO-8601 (cross-platform date).
    # 計算 mtime + 90d UTC ISO-8601（跨平台 date）。
    local due_epoch=$((mtime_epoch + ROTATION_DAYS * 86400))
    if due_at=$(date -u -r "$due_epoch" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null); then
        : # macOS / BSD
    elif due_at=$(date -u -d "@${due_epoch}" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null); then
        : # Linux / GNU
    else
        due_at=""
    fi
    echo "$due_at"
}

# ─── Audit log writer (best-effort) / Audit log 寫入器（best-effort） ──
# Writes one row to learning.governance_audit_log per ALERT env.
# When PG unavailable, just logs to stderr/file — never blocks ALERT exit.
# 每個 ALERT env 寫一 row 到 learning.governance_audit_log。
# PG 不可用時僅 log 到 stderr/檔案 — 永不阻塞 ALERT exit。
write_audit_alert() {
    local env_name="$1"
    local due_at="$2"
    local days_remaining="$3"

    if [[ "$PG_AVAILABLE" -ne 1 ]]; then
        echo "[$(ts)] AUDIT_SKIP env=${env_name} reason=pg_unavailable" >> "$LOG"
        return 0
    fi

    # Check if learning.governance_audit_log exists (V035 must be applied).
    # 檢查 learning.governance_audit_log 是否存在（V035 須已 applied）。
    if ! psql "$OPENCLAW_DATABASE_URL" -tAc \
        "SELECT 1 FROM information_schema.tables WHERE table_schema='learning' AND table_name='governance_audit_log' LIMIT 1;" \
        2>/dev/null | grep -q '^1$'; then
        echo "[$(ts)] AUDIT_SKIP env=${env_name} reason=v035_table_missing" >> "$LOG"
        return 0
    fi

    # Use payload JSONB for forward-compat; event_type='audit_write_failed' is
    # not a perfect match but is the closest existing enum (V035 CHECK).
    # We piggyback this advisory alert without expanding the enum (out of scope).
    # Future: add 'replay_key_rotation_alert' to V035 enum in P2a-S6 sibling.
    # 用 payload JSONB 確保前向相容；event_type='audit_write_failed' 並非完美
    # 對應但是 V035 CHECK enum 中最接近的（P2a-S6 sibling 將擴 enum）。
    local payload
    payload=$(printf '{"alert_type":"replay_key_rotation_due","env":"%s","rotation_due_at":"%s","days_remaining":%d,"source":"replay_key_rotation_check_cron"}' \
        "$env_name" "$due_at" "$days_remaining")

    # Idempotency: the cron may run multiple days while the alert window is
    # open (≤7d). To avoid 7+ rows per env, only write when no alert row was
    # written today for this env (cheap check via WHERE ts > today_start).
    # Idempotent：alert 視窗 ≤7d 期間 cron 可能多次跑。為避免每 env 7+ row，
    # 僅當今天此 env 還沒寫 alert 時才寫（用 ts > today_start cheap 查）。
    # MED-1 retrofit (E2 review 2026-05-03): replace shell-string interpolation
    # of SQL params with psql `-v` parametrized binding. Even though `env_name`
    # is sourced from the hardcoded ENVS=(paper demo live) array (zero injection
    # surface today), defense-in-depth: if ENVS later moves to dynamic source
    # (operator config, env var override) the param binding stays safe.
    # MED-1 retrofit (E2 review 2026-05-03): 把 SQL 參數的 shell 字串插值改為
    # psql `-v` parametrized binding。即使 `env_name` 目前來自 hardcoded
    # ENVS=(paper demo live) 陣列（零注入面），仍做 defense-in-depth：未來 ENVS
    # 若改動態 source（operator 設定或 env override），參數 binding 自然安全。
    local already_today
    already_today=$(psql "$OPENCLAW_DATABASE_URL" -tAc \
        -v env="$env_name" \
        "SELECT 1 FROM learning.governance_audit_log WHERE event_type='audit_write_failed' AND ts >= date_trunc('day', NOW()) AND payload->>'alert_type'='replay_key_rotation_due' AND payload->>'env'=:'env' LIMIT 1;" \
        2>/dev/null | tr -d '[:space:]' || true)
    if [[ "$already_today" == "1" ]]; then
        echo "[$(ts)] AUDIT_DEDUP env=${env_name} (already alerted today)" >> "$LOG"
        return 0
    fi

    if psql "$OPENCLAW_DATABASE_URL" -tAc \
        -v payload="$payload" \
        "INSERT INTO learning.governance_audit_log (event_type, decided_by, payload) VALUES ('audit_write_failed', 'replay_key_rotation_check_cron', :'payload'::jsonb);" \
        >> "$LOG" 2>&1; then
        echo "[$(ts)] AUDIT_WRITTEN env=${env_name} days_remaining=${days_remaining}" >> "$LOG"
    else
        echo "[$(ts)] AUDIT_FAILED env=${env_name} (insert error; see log)" >> "$LOG"
    fi
}

# ─── Main loop / 主迴圈 ──────────────────────────────────────────────
echo "[$(ts)] === replay_key_rotation_check start (BASE=$BASE SECRETS=$SECRETS_DIR PG=$PG_AVAILABLE) ===" >> "$LOG"

ALERT_COUNT=0
NOW_EPOCH=$(date -u +%s)

for ENV_NAME in "${ENVS[@]}"; do
    DUE_AT=$(probe_rotation_due_at "$ENV_NAME")

    if [[ -z "$DUE_AT" ]]; then
        # Probe could not determine due_at (key missing OR V042 inconsistent).
        # Treat as ALERT — operator must investigate (key_missing fail-mode adjacent).
        # 探查無法判定 due_at（key 缺失或 V042 不一致）— 視為 ALERT，
        # operator 須調查（key_missing fail-mode 相關）。
        echo "[$(ts)] ALERT env=${ENV_NAME} reason=due_at_unknown (key file missing or V042 inconsistent)" \
            | tee -a "$LOG" >&2
        write_audit_alert "$ENV_NAME" "unknown" -999
        ALERT_COUNT=$((ALERT_COUNT + 1))
        continue
    fi

    # Convert DUE_AT (ISO-8601) to epoch (cross-platform).
    # ISO-8601 → epoch（跨平台）。
    if DUE_EPOCH=$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$DUE_AT" '+%s' 2>/dev/null); then
        : # macOS / BSD
    elif DUE_EPOCH=$(date -u -d "$DUE_AT" '+%s' 2>/dev/null); then
        : # Linux / GNU
    else
        echo "[$(ts)] WARN env=${ENV_NAME} cannot parse DUE_AT='$DUE_AT'" >> "$LOG"
        ALERT_COUNT=$((ALERT_COUNT + 1))
        continue
    fi

    DELTA_SECS=$((DUE_EPOCH - NOW_EPOCH))
    DAYS_REMAINING=$((DELTA_SECS / 86400))

    if [[ $DAYS_REMAINING -le $ALERT_THRESHOLD_DAYS ]]; then
        # ALERT: within 7d window OR already past due.
        # ALERT：≤7d 視窗內或已過期。
        ALERT_MSG="ALERT env=${ENV_NAME} due_at=${DUE_AT} days_remaining=${DAYS_REMAINING}"
        echo "[$(ts)] $ALERT_MSG" | tee -a "$LOG" >&2
        write_audit_alert "$ENV_NAME" "$DUE_AT" "$DAYS_REMAINING"
        ALERT_COUNT=$((ALERT_COUNT + 1))
    else
        # OK: silent (per task spec).
        # OK：silent（依任務規格）。
        echo "[$(ts)] OK env=${ENV_NAME} due_at=${DUE_AT} days_remaining=${DAYS_REMAINING}" >> "$LOG"
    fi
done

if [[ $ALERT_COUNT -eq 0 ]]; then
    echo "[$(ts)] === cron end OK (all ${#ENVS[@]} envs healthy) ===" >> "$LOG"
    exit 0
else
    echo "[$(ts)] === cron end ALERT (${ALERT_COUNT} env(s) require rotation) ===" >> "$LOG"
    exit 1
fi
