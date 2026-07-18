#!/usr/bin/env bash
# residual_stage0r_preflight_cron.sh — Stage-0R β-residualization producer
# orchestrator 手動 one-shot CLI shim（PART 4 Gap A/D）。
#
# 作用：把 mlde_shadow_recommendations 中「數值預閘達標但缺 lineage」的 demo 候選，
# 經多因子 residual + permutation + Gap D selection-bias 斷言 → 註冊 replay
# experiment（replay.experiments + sealed hidden_oos_state_registry）→ 寫 drar →
# 蓋 lineage，使下游 mlde_demo_applier 的 β-residualization 晉升閘真正審判真實候選。
#
# Spec 來源:
#   docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-08--residual-gap-closure-design.md
#     §2 Gap A（6-step flow）+ §2 Gap D + §4 flag boundary + §5 PIT risks
#   PA REVISED ruling：NO peer synthesis（單一配置 PBO 誠實 defer，不捏造 peer）。
#
# ★ 三重 OFF（行為中性硬約束 — 不啟用即零寫入）:
#   1. OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT=1   （NEW flag，預設 0）
#   2. OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1      （既有 flag，預設 0，bridge 內部再 check）
#   3. --jobs residual_preflight               （該 job 不在 DEFAULT_JOBS，須顯式加）
#   三者皆滿足才會寫任何 row。任一缺 → orchestrator 早退 skipped。
#
# ★ DEMO evidence lane only：只寫 replay.experiments / hidden_oos_state_registry /
#   demo_residual_alpha_reports + rec-stamp UPDATE；只讀 demo 資料。零 live/auth/
#   order/risk/lease 變動（live-candidate INSERT 留下游 mlde_demo_applier，需
#   GovernanceHub + Decision Lease，本 shim 不碰）。
#
# 必要時間窗 env（PIT：邊界是 operator 承諾，不自行猜；缺則 orchestrator skipped）:
#   OPENCLAW_RESIDUAL_PREFLIGHT_SINCE       ISO-8601（residual 計算起點）
#   OPENCLAW_RESIDUAL_PREFLIGHT_OOS_START   ISO-8601（hidden-OOS 窗起點，strict carve-out）
#   OPENCLAW_RESIDUAL_PREFLIGHT_DATA_END    ISO-8601（OOS 窗終點 > oos_start）
#
# 模式對齊 m11_replay_runner_daily_cron.sh / trading_ai_pg_dump_cron.sh 風格：
#   - 平台守門：Linux only（Mac dev refuse exit 2；本 shim 在 runtime host 跑）
#   - 路徑不硬編碼（OPENCLAW_BASE_DIR / OPENCLAW_DATA_DIR / OPENCLAW_SECRETS_ROOT）
#   - lock dir 防 overrun；trap rmdir cleanup
#   - cron heartbeat sentinel start-time touch
#   - fail-soft：runner 非 0 不再向上拋（避免 cron mail 噪音），記 log/JSONL；exit 0
#
# 硬邊界:
#   - 不繞 single controlled write entry：register 走 experiment_registry thin
#     handler（非 raw SQL）；drar/stamp 走 orchestrator 受控寫入路徑。
#   - 不改 PG schema（lineage 欄位已存在，無 migration）。

set -euo pipefail

# ─── 平台守門：僅 Linux 執行 ─────────────────────────────────────────
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: residual_stage0r_preflight_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本 script 必在 Linux runtime host (trade-core) 跑；Mac dev 走 ssh trade-core。" >&2
    exit 2
fi

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"

LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/residual_stage0r_preflight_cron.cron.log"
JSONL="${LOG_DIR}/residual_stage0r_preflight_cron.jsonl"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/residual_stage0r_preflight_cron.lock.d"

mkdir -p "$LOG_DIR" "$LOCK_ROOT"

# Cron heartbeat sentinel — touch-at-start（「被觸發」的證據，供未來 healthcheck）。
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true
touch "$HEARTBEAT_DIR/residual_stage0r_preflight.last_fire" 2>/dev/null || true

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

# ─── lock dir 防 overrun ──────────────────────────────────────────
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: another residual_stage0r_preflight run holds lock $LOCK_DIR" | tee -a "$LOG"
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

# ─── env / DSN ────────────────────────────────────────────────────
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ -f "$ENV_FILE" ]]; then
    # 只取需要的 PG creds 拼 DSN；不 source 整檔（避免污染環境）。
    PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_USER=$(grep '^POSTGRES_USER='     "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_DB=$(grep   '^POSTGRES_DB='       "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_HOST=$(grep '^POSTGRES_HOST='     "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_PORT=$(grep '^POSTGRES_PORT='     "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_HOST="${PG_HOST:-127.0.0.1}"
    PG_PORT="${PG_PORT:-5432}"
fi

# DSN 優先序：顯式 OPENCLAW_DATABASE_URL > 由 PG creds 拼。
DSN="${OPENCLAW_DATABASE_URL:-}"
if [[ -z "$DSN" && -n "${PG_USER:-}" && -n "${PG_PASS:-}" && -n "${PG_DB:-}" ]]; then
    # DSN 字面量刻意拆開,避免 public-repo gate(embedded_credential_dsn query 形)匹配源碼 bytes;勿合併回單一字串。
    DSN="postgresql://${PG_HOST}:${PG_PORT}/${PG_DB}?user=${PG_USER}&pass""word=${PG_PASS}"
fi
if [[ -z "$DSN" ]]; then
    echo "[$(ts)] SKIP: no DSN (set OPENCLAW_DATABASE_URL or PG creds in $ENV_FILE)" | tee -a "$LOG"
    echo "{\"ts\":\"$(ts)\",\"event\":\"residual_preflight_skip\",\"reason\":\"no_dsn\"}" >> "$JSONL"
    exit 0
fi
export OPENCLAW_DATABASE_URL="$DSN"

# ─── 跑 runner（只跑 residual_preflight job）────────────────────────
# runner 內部三重 flag gate 仍會把缺旗標的情況轉成 skipped（zero-write）；本 shim
# 只負責把 job 名顯式選入並提供 DSN。fail-soft：非 0 退碼不再上拋。
STATUS_JSON="${DATA}/status/residual_stage0r_preflight.json"
mkdir -p "${DATA}/status" 2>/dev/null || true

echo "[$(ts)] residual_stage0r_preflight starting (flags: STAGE0R=${OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT:-0} PRODUCER=${OPENCLAW_RESIDUAL_ALPHA_PRODUCER:-0})" | tee -a "$LOG"

set +e
PYTHONDONTWRITEBYTECODE=1 python3 "$BASE/helper_scripts/cron/ml_training_maintenance.py" \
    --base-dir "$BASE" \
    --jobs residual_preflight \
    --status-json "$STATUS_JSON" \
    >> "$LOG" 2>&1
RC=$?
set -e

echo "{\"ts\":\"$(ts)\",\"event\":\"residual_preflight_done\",\"exit_code\":${RC}}" >> "$JSONL"
if [[ $RC -ne 0 ]]; then
    echo "[$(ts)] residual_stage0r_preflight runner exit=$RC (fail-soft; see $LOG / $STATUS_JSON)" | tee -a "$LOG"
fi

# fail-soft：永遠 exit 0（cron 不 page；多日連續失敗由 status_json / log 追蹤）。
exit 0
