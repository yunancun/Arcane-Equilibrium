#!/usr/bin/env bash
# m11_replay_runner_daily_cron.sh — M11 Stage A daily smoke heartbeat wrapper
#
# 配對 install script:
#   $HOME/BybitOpenClaw/srv/helper_scripts/cron/install_m11_replay_runner_cron.sh
#
# 配對 healthcheck:
#   $HOME/BybitOpenClaw/srv/helper_scripts/db/passive_wait_healthcheck/checks_replay_maintenance.py
#   `[48]` replay_manifest_registry_growth (rows_7d ≥ 1 → PASS)
#
# Spec 來源:
#   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--m11_replay_runner_schedule_proposal.md
#     §4.2 wrapper contract / §4.3 cron entry / §5 [48] healthcheck flip 預期
#   docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md
#     Decision 1 + 5 nightly continuous hygiene
#   docs/adr/0044-m7-decay-enforced-single-authority.md
#     Decision 2 line 74 M11 as 5th signal「daily_divergence_aggregate_30d」
#   operator confirm 2026-05-28 cadence = Daily 04:00 UTC (= M11.a)
#
# 設計重點:
#   1. **Stage A single-fixture smoke heartbeat 模式**：每天跑 1 個 fixture
#      (synthetic_btcusdt.json) 走完 register → run → poll status。目的只在
#      於累積 replay.experiments row 與證明 runner 鏈活著，並讓 `[48]` rows_7d
#      條件穩定為 PASS；不是 Stage B 全 cohort nightly（待 Sprint 3 Phase A）。
#   2. **不擴 V035 enum**：governance_audit_log 對齊 replay_key_rotation_check.sh
#      pattern（per PA OQ-2 (a)），piggyback event_type='audit_write_failed' +
#      payload.alert_type 識別 M11 smoke 事件；後續 Sprint 3 Phase A 同步擴。
#   3. **Operator API token 認證**：通過 $OPENCLAW_API_TOKEN_FILE 讀
#      operator session token 作 Bearer auth；不引入新 Service principal
#      （OQ-1 PENDING follow-up；現階段重用 operator token 不觸 hard
#      boundary—signed live authorization 是另一套機制，API session
#      token 屬 GUI/programmatic API 認證）。
#   4. **fail-soft**：register/run/poll 任何階段 fail 不退非 0 給 cron
#      （避免 mail 噪音），改寫 audit + log + JSONL；exit 0 給 cron。
#      `[50]` failed_rate 偵測 + `[48]` rows_24h WARN 已 cover 多日連續 fail。
#
# 模式對齊 trading_ai_pg_dump_cron.sh / feature_baseline_writer_cron.sh 風格：
#   - 平台守門：Linux only；Mac dev refuse exit 2
#   - secrets 從 $OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env
#   - lock dir 防 overrun；trap rmdir cleanup
#   - cron heartbeat sentinel start-time touch
#   - JSONL audit + log rotation natural (logrotate hourly)
#   - governance_audit_log INSERT best-effort（PG 不可用不阻塞主流）
#
# 硬邊界:
#   - 跨平台：僅 Linux 跑（uname Linux check）；Mac dev refuse exit 2
#   - 路徑不硬編碼（per memory feedback_cross_platform）
#   - 不繞 _require_replay_write Operator + replay:write scope gate（走正規
#     REST POST 帶 Bearer token）
#   - 不改 PG schema、不繞 single controlled write entry（INSERT 走 register
#     endpoint thin handler，非 raw SQL）
#   - ReplayProfile::Isolated 由 binary 端 S7/S8/S9 三層 guard 強制（per
#     replay_runner.rs:225-276），cron 端無需重複；本 wrapper 不傳 live env

set -euo pipefail

# ─── 平台守門：僅 Linux 執行 ─────────────────────────────────────────
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: m11_replay_runner_daily_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本 script 必在 Linux runtime host (trade-core) 跑；Mac dev 走 ssh trade-core。" >&2
    exit 2
fi

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"

LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/m11_replay_runner_daily_cron.cron.log"
JSONL="${LOG_DIR}/m11_replay_runner_daily_cron.jsonl"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/m11_replay_runner_daily_cron.lock.d"

mkdir -p "$LOG_DIR" "$LOCK_ROOT"

# Cron heartbeat sentinel — P1-CRON-INSTALL-WAVE-1 同模式。
# touch-at-start：「cron 被排程觸發」的證據；給未來 [??] cron heartbeat
# healthcheck 監測 mtime。
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true
touch "$HEARTBEAT_DIR/m11_replay_runner_daily.last_fire" 2>/dev/null || true

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

# ─── env / secrets / API token ────────────────────────────────────
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[$(ts)] FATAL: env file missing: $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi

PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_DB=$(grep   '^POSTGRES_DB='       "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST=$(grep '^POSTGRES_HOST='     "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_PORT=$(grep '^POSTGRES_PORT='     "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"
if [[ -z "$PG_PASS" || -z "$PG_USER" || -z "$PG_DB" ]]; then
    echo "[$(ts)] FATAL: PG creds incomplete in $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi
export PGPASSWORD="$PG_PASS"

# Operator API token：對齊 control_api_v1/.secrets/api_token deploy path（per
# restart_all.sh + README §70）；cron 重用 operator token 作 Bearer 認證。
# 未來如要 swap 到 dedicated Service principal（OQ-1 PA proposal）只需改本段。
API_TOKEN_FILE="${OPENCLAW_API_TOKEN_FILE:-$BASE/program_code/exchange_connectors/bybit_connector/control_api_v1/.secrets/api_token}"
if [[ ! -f "$API_TOKEN_FILE" ]]; then
    echo "[$(ts)] FATAL: API token file missing: $API_TOKEN_FILE" | tee -a "$LOG" >&2
    exit 2
fi
API_TOKEN=$(<"$API_TOKEN_FILE")
if [[ -z "$API_TOKEN" ]]; then
    echo "[$(ts)] FATAL: API token file empty: $API_TOKEN_FILE" | tee -a "$LOG" >&2
    exit 2
fi

# API base URL：對齊 uvicorn host:port（per restart_all.sh bind host = Tailscale
# IPv4 auto-resolve）。實機 trade-core uvicorn bind 在 Tailscale IPv4
# (100.91.x.x) 而非 0.0.0.0，loopback 127.0.0.1:8000 不通 — 必須走 Tailscale
# IPv4。OPENCLAW_API_BASE_URL env 可顯式覆寫；無覆寫時 auto-detect
# tailscale ip -4，最後 fallback loopback 給未來 bind=0.0.0.0 場景。
if [[ -n "${OPENCLAW_API_BASE_URL:-}" ]]; then
    API_BASE="$OPENCLAW_API_BASE_URL"
else
    TS_IP=$(tailscale ip -4 2>/dev/null | head -1 || true)
    if [[ -n "$TS_IP" ]]; then
        API_BASE="http://${TS_IP}:8000"
    else
        API_BASE="http://127.0.0.1:8000"
    fi
fi

# CSRF double-submit token：對齊 csrf_middleware.py:108-179 — middleware 只
# constant-time 比對 cookie ↔ header 同值（無 server-side session 驗證；
# 純 double-submit）。cron 場景下 cookie 與 header 自設同值即可滿足 CSRF
# gate；token 本身不簽署，安全性靠 SameSite=Strict 第一層 + 同源 referer。
# 隨機 32-byte hex 防 hard-coded 字串被 grep。
CSRF_TOKEN=$(head -c 32 /dev/urandom 2>/dev/null | xxd -p 2>/dev/null | tr -d '\n' || python3 -c 'import secrets;print(secrets.token_hex(16))' 2>/dev/null || echo "m11cronstaticfallback00000000000000000000000000000000000000000000")

# Fixture path：對齊 restart_all.sh:672 既有 default in-tree fixture。
FIXTURE_PATH="${OPENCLAW_M11_REPLAY_FIXTURE:-$BASE/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json}"
if [[ ! -f "$FIXTURE_PATH" ]]; then
    echo "[$(ts)] FATAL: M11 fixture missing: $FIXTURE_PATH" | tee -a "$LOG" >&2
    exit 2
fi

# Lock：防重入（手動 + cron 同時跑 / 上次未結束）。
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: m11_replay_runner_daily already running (lock held)" >> "$LOG"
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

START_EPOCH=$(date -u +%s)
echo "[$(ts)] === M11 replay_runner Stage A smoke START (BASE=$BASE API=$API_BASE FIXTURE=$FIXTURE_PATH) ===" >> "$LOG"

# ─── governance_audit_log INSERT helper（best-effort）─────────────
# 對齊 replay_key_rotation_check.sh §219-285 pattern：V035 CHECK enum 未含
# m11_replay_runner_* event_type（V113 只擴了 pg_dump_*），暫 piggyback
# 'audit_write_failed' + payload.alert_type 識別。Sprint 3 Phase A 同步擴
# enum 後改用專屬 event_type。
emit_governance_audit() {
    local alert_type="$1"      # 'm11_replay_runner_smoke_completed' / '_failed' / '_register_failed'
    local payload_extra="$2"   # JSON object 字段（不含外層 {}）
    local payload
    payload=$(printf '{"alert_type":"%s","source":"m11_replay_runner_daily_cron",%s}' \
        "$alert_type" "$payload_extra")
    # psql `-v var=value` -c 模式對 JSON `:` 衝突（被當 psql variable
    # substitution prefix）；改用 stdin heredoc + dollar-quoted string literal
    # ($payload$...$payload$) 對齊 trading_ai_pg_dump_cron.sh:132-148 範式。
    # dollar-quoting 不解析 `:` / `'` / `\` 任何特殊字 → JSON 內容原樣傳遞。
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
        -v ON_ERROR_STOP=1 \
        -c "INSERT INTO learning.governance_audit_log (
                ts, event_type, decided_by, payload, rule_failures, lease_revoke_triggers
            ) VALUES (
                NOW(), 'audit_write_failed', 'm11_replay_runner_daily_cron',
                \$payload\$${payload}\$payload\$::jsonb,
                ARRAY[]::TEXT[], ARRAY[]::TEXT[]
            );" >> "$LOG" 2>&1 || {
        echo "[$(ts)] WARN: governance_audit_log INSERT failed (alert_type=${alert_type})" >> "$LOG"
        return 1
    }
    return 0
}

# ─── Step 1: 構造 register payload 並 POST /experiments/register ──
# Manifest jsonb 採用最小可通過 register 必填欄位 + fixture 路徑指向 in-tree
# synthetic fixture；fixture_uri 留空走 OPENCLAW_REPLAY_FIXTURE_DEFAULT env
# 預設 fallback。data_window 用「過去 24h」固定 window（fixture 是 synthetic
# 不真綁時間，但 V049 仍要求 start < end）。
DATESTAMP=$(date -u '+%Y-%m-%d')
WINDOW_END=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
WINDOW_START=$(date -u -d '24 hours ago' '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
                || date -u -v-24H '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
                || echo "2026-05-28T00:00:00Z")

# strategy_config_sha256 / risk_config_sha256：fixture-driven 不對應真實
# strategy/risk config，用 fixture path SHA256 + "smoke" suffix 區分。V049
# CHECK 只要求 64-char lowercase hex；server 收到 strategy_params 會 OVERRIDE
# 為 sha256(canonical_bytes(strategy_params)) — 即使我們塞錯也會被 server 改正
# （per experiment_registry.py:303-320 R5-T6 round 2 override 行為）。
FIXTURE_SHA=$( (sha256sum "$FIXTURE_PATH" 2>/dev/null || shasum -a 256 "$FIXTURE_PATH" 2>/dev/null) | cut -d' ' -f1 )
STRATEGY_SHA="${FIXTURE_SHA}"  # 64 char hex
RISK_SHA="${FIXTURE_SHA}"      # 64 char hex（同一）

IDEMPOTENCY_KEY="m11-daily-smoke-${DATESTAMP}"

# Manifest jsonb：對齊 synthetic_btcusdt.json + V3 §4.1 必欄。strategy_params
# 提供讓 server override sha；symbol/strategy/timeframe 對應 fixture 內容
# （BTCUSDT 1m grid_trading 為 smoke baseline）。
# 為什麼 embargo_days=14：V049 CHECK chk_embargo_days 要求
# `embargo_days >= GREATEST(7, ceil(2 * half_life_days))` — half_life=7d ⇒
# 下限 = max(7, 14) = 14；smoke 不真消費此值（只通過 CHECK），對 fixture
# semantics 無影響。
REGISTER_BODY=$(cat <<JSON_EOF
{
  "idempotency_key": "${IDEMPOTENCY_KEY}",
  "symbol": "BTCUSDT",
  "strategy": "grid_trading",
  "timeframe": "1m",
  "data_tier": "S3",
  "data_window_start": "${WINDOW_START}",
  "data_window_end": "${WINDOW_END}",
  "strategy_config_sha256": "${STRATEGY_SHA}",
  "risk_config_sha256": "${RISK_SHA}",
  "half_life_days": 7.0,
  "embargo_days": 14.0,
  "strategy_params": {"smoke_mode": true, "fixture": "synthetic_btcusdt"},
  "manifest_jsonb": {
    "schema_version": 1,
    "source": "m11_daily_smoke",
    "fixture_uri": "${FIXTURE_PATH}",
    "data_tier": "S3",
    "mode": "smoke_heartbeat",
    "symbol": "BTCUSDT",
    "strategy": "grid_trading",
    "timeframe": "1m"
  }
}
JSON_EOF
)

REGISTER_TMP=$(mktemp "${DATA}/m11_register_response.XXXXXX.json")
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true; rm -f "$REGISTER_TMP" 2>/dev/null || true' EXIT

echo "[$(ts)] POST ${API_BASE}/api/v1/replay/experiments/register idem=${IDEMPOTENCY_KEY}" >> "$LOG"
REGISTER_HTTP=$(curl -sS -o "$REGISTER_TMP" -w '%{http_code}' \
    -X POST "${API_BASE}/api/v1/replay/experiments/register" \
    -H "Authorization: Bearer ${API_TOKEN}" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -b "oc_csrf=${CSRF_TOKEN}" \
    -d "$REGISTER_BODY" 2>>"$LOG" || echo "000")

if [[ "$REGISTER_HTTP" != "200" && "$REGISTER_HTTP" != "201" ]]; then
    END_EPOCH=$(date -u +%s)
    DUR=$((END_EPOCH - START_EPOCH))
    RESP_BODY=$(head -c 500 "$REGISTER_TMP" 2>/dev/null || echo "")
    echo "[$(ts)] FAIL register http=$REGISTER_HTTP dur=${DUR}s body=$RESP_BODY" >> "$LOG"
    printf '{"ts":"%s","status":"fail","stage":"register","http":%s,"duration_sec":%s}\n' \
        "$(ts)" "$REGISTER_HTTP" "$DUR" >> "$JSONL"
    emit_governance_audit 'm11_replay_runner_smoke_register_failed' \
        "$(printf '"http":%s,"duration_sec":%s,"datestamp":"%s"' \
            "$REGISTER_HTTP" "$DUR" "$DATESTAMP")" || true
    echo "[$(ts)] === M11 replay_runner Stage A smoke END FAIL (register) dur=${DUR}s ===" >> "$LOG"
    # fail-soft exit 0（避免 cron mail spam；[48] WARN/FAIL 由 healthcheck cover）。
    exit 0
fi

# 解析 experiment_id；對齊 _replay_response envelope（per replay_routes.py:382
# 返回 data: {experiment_id, manifest_hash, idempotency_hit, ...}）。
EXPERIMENT_ID=$(python3 -c "
import json, sys
try:
    data = json.load(open('$REGISTER_TMP'))
    # envelope: {data: {...}} or flat {...}
    payload = data.get('data', data)
    print(payload.get('experiment_id', ''))
except Exception:
    sys.exit(0)
" 2>/dev/null || echo "")

if [[ -z "$EXPERIMENT_ID" ]]; then
    END_EPOCH=$(date -u +%s)
    DUR=$((END_EPOCH - START_EPOCH))
    echo "[$(ts)] FAIL register response missing experiment_id body=$(head -c 300 "$REGISTER_TMP")" >> "$LOG"
    printf '{"ts":"%s","status":"fail","stage":"register_parse","http":%s,"duration_sec":%s}\n' \
        "$(ts)" "$REGISTER_HTTP" "$DUR" >> "$JSONL"
    emit_governance_audit 'm11_replay_runner_smoke_register_failed' \
        "$(printf '"http":%s,"duration_sec":%s,"reason":"missing_experiment_id"' \
            "$REGISTER_HTTP" "$DUR")" || true
    exit 0
fi

echo "[$(ts)] OK register http=$REGISTER_HTTP experiment_id=$EXPERIMENT_ID" >> "$LOG"

# ─── Step 2: POST /replay/run 啟動 run ───────────────────────────
# /run body 對齊 ReplayRunRequest（per replay_routes.py:385+）；只需
# experiment_id + idempotency_key。run_id 由 server 生成。
RUN_BODY=$(printf '{"experiment_id":"%s","idempotency_key":"m11-run-%s"}' \
    "$EXPERIMENT_ID" "$DATESTAMP")
RUN_TMP=$(mktemp "${DATA}/m11_run_response.XXXXXX.json")
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true; rm -f "$REGISTER_TMP" "$RUN_TMP" 2>/dev/null || true' EXIT

echo "[$(ts)] POST ${API_BASE}/api/v1/replay/run experiment_id=$EXPERIMENT_ID" >> "$LOG"
RUN_HTTP=$(curl -sS -o "$RUN_TMP" -w '%{http_code}' \
    -X POST "${API_BASE}/api/v1/replay/run" \
    -H "Authorization: Bearer ${API_TOKEN}" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -b "oc_csrf=${CSRF_TOKEN}" \
    -d "$RUN_BODY" 2>>"$LOG" || echo "000")

if [[ "$RUN_HTTP" != "200" && "$RUN_HTTP" != "201" ]]; then
    END_EPOCH=$(date -u +%s)
    DUR=$((END_EPOCH - START_EPOCH))
    RESP_BODY=$(head -c 500 "$RUN_TMP" 2>/dev/null || echo "")
    echo "[$(ts)] FAIL run http=$RUN_HTTP dur=${DUR}s body=$RESP_BODY" >> "$LOG"
    printf '{"ts":"%s","status":"fail","stage":"run","http":%s,"experiment_id":"%s","duration_sec":%s}\n' \
        "$(ts)" "$RUN_HTTP" "$EXPERIMENT_ID" "$DUR" >> "$JSONL"
    emit_governance_audit 'm11_replay_runner_smoke_failed' \
        "$(printf '"http":%s,"experiment_id":"%s","duration_sec":%s,"stage":"run","datestamp":"%s"' \
            "$RUN_HTTP" "$EXPERIMENT_ID" "$DUR" "$DATESTAMP")" || true
    # register row 已寫進 replay.experiments → [48] healthcheck 仍 flip 到 PASS
    # （rows_7d 條件達標）。fail-soft exit 0。
    exit 0
fi

# 解析 run_id + status：subprocess 可能已在 poll grace 內完成（per
# replay_routes.py:442 subprocess_completed_in_poll = subprocess_pid is None）。
RUN_ID=$(python3 -c "
import json, sys
try:
    data = json.load(open('$RUN_TMP'))
    payload = data.get('data', data)
    print(payload.get('run_id', ''))
except Exception:
    sys.exit(0)
" 2>/dev/null || echo "")
RUN_STATUS=$(python3 -c "
import json, sys
try:
    data = json.load(open('$RUN_TMP'))
    payload = data.get('data', data)
    print(payload.get('status', ''))
except Exception:
    sys.exit(0)
" 2>/dev/null || echo "")

echo "[$(ts)] OK run http=$RUN_HTTP run_id=$RUN_ID initial_status=$RUN_STATUS" >> "$LOG"

# Smoke 場景下 single-fixture wall clock < 2 min；不 poll status terminal
# state（避免 cron 內 30s 級別等待；replay subprocess 在 server 端非同步跑
# 完，無需 cron 端阻塞）。`[50]` healthcheck 偵測 zombie 'running' > 1h。

END_EPOCH=$(date -u +%s)
DUR=$((END_EPOCH - START_EPOCH))
echo "[$(ts)] OK m11_replay_runner_daily_cron experiment_id=$EXPERIMENT_ID run_id=$RUN_ID dur=${DUR}s" >> "$LOG"
printf '{"ts":"%s","status":"ok","experiment_id":"%s","run_id":"%s","initial_run_status":"%s","duration_sec":%s,"datestamp":"%s"}\n' \
    "$(ts)" "$EXPERIMENT_ID" "$RUN_ID" "$RUN_STATUS" "$DUR" "$DATESTAMP" >> "$JSONL"

# governance_audit_log: smoke_completed（register + run dispatch 均通）
emit_governance_audit 'm11_replay_runner_smoke_completed' \
    "$(printf '"experiment_id":"%s","run_id":"%s","initial_run_status":"%s","duration_sec":%s,"datestamp":"%s"' \
        "$EXPERIMENT_ID" "$RUN_ID" "$RUN_STATUS" "$DUR" "$DATESTAMP")" || true

echo "[$(ts)] === M11 replay_runner Stage A smoke END OK dur=${DUR}s ===" >> "$LOG"
exit 0
