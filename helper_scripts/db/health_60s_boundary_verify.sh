#!/usr/bin/env bash
# =============================================================================
# health_60s_boundary_verify.sh
#
# 用途：Sprint 5+ Wave 1 §4.4.2 production hardening — 60s rolling window
#      boundary verify SOP wrapper。
#
# 為什麼此 wrapper（per PA report §3.2）:
#   - rust bybit_rest_client.rs line 318-441 已 code-level 對齊 60s expire；
#     本 wrapper 補 production runtime empirical verify（emitter scheduler
#     tokio tick 抖動 / samples_per_min duplicate emit / task crash 等
#     runtime 失準路徑）。
#   - 對齊 passive_wait_healthcheck.sh 範式（venv-aware + secrets load）;
#     避 repeat fix「No module named 'psycopg2'」/「POSTGRES_PASSWORD unset」
#     兩坑。
#
# Usage:
#   bash helper_scripts/db/health_60s_boundary_verify.sh           # full output
#   bash helper_scripts/db/health_60s_boundary_verify.sh --quiet   # only FAIL
#
# Exit codes:
#   0 = PASS（樣本 inter-arrival ∈ [58, 62] AND samples_per_min == 1）
#   1 = FAIL（任一域 inter-arrival out of [55, 65] OR samples_per_min ∉ [1, 2]）
#   2 = DB connection error（env/credentials issue）
#
# Environment overrides:
#   OPENCLAW_BASE_DIR     repo root (defaults: $HOME/BybitOpenClaw/srv)
#   OPENCLAW_SECRETS_ROOT secrets dir (defaults: $HOME/BybitOpenClaw/secrets)
#   OPENCLAW_PG_CONTAINER PG container (defaults: trading_postgres)
#   POSTGRES_DB / POSTGRES_USER / POSTGRES_HOST / POSTGRES_PORT fallback
# =============================================================================

set -u

BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
SECRETS_ENV="$SECRETS_ROOT/environment_files/basic_system_services.env"
SQL_FILE="$BASE_DIR/helper_scripts/db/health_60s_boundary_verify.sql"
PG_CONT="${OPENCLAW_PG_CONTAINER:-trading_postgres}"

QUIET=0
for arg in "$@"; do
  if [[ "$arg" == "--quiet" ]]; then
    QUIET=1
  fi
done

# ─── 1. Load Postgres env (mirrors passive_wait_healthcheck.sh:79-88) ────────
if [[ -f "$SECRETS_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$SECRETS_ENV"
  set +a
else
  echo "[FATAL] secrets env not found: $SECRETS_ENV" >&2
  echo "        POSTGRES_PASSWORD unset → DB connect will fail." >&2
  exit 2
fi

# Sane defaults for non-secret fields (mirror passive_wait_healthcheck.sh:91-94)
export POSTGRES_DB="${POSTGRES_DB:-trading_ai}"
export POSTGRES_USER="${POSTGRES_USER:-trading_admin}"
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
export PGPASSWORD="${POSTGRES_PASSWORD:-}"

if [[ -z "$PGPASSWORD" ]]; then
  echo "[FATAL] POSTGRES_PASSWORD not loaded from $SECRETS_ENV" >&2
  exit 2
fi

# ─── 2. Sanity check SQL file ─────────────────────────────────────────────
if [[ ! -r "$SQL_FILE" ]]; then
  echo "[FATAL] SQL file not readable: $SQL_FILE" >&2
  exit 2
fi

# ─── 3. Run SQL through containerized PG (per AC-1b 範式) ──────────────────
# 為什麼 docker exec：trade-core PG 跑 container；host psql client 版本可能
# 與 server 版本錯位（observed 13 vs 16 SCRAM auth 不相容）。
SQL_OUTPUT=$(docker exec -i \
  -e PGPASSWORD="$PGPASSWORD" \
  "$PG_CONT" \
  psql \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    -v ON_ERROR_STOP=1 \
    -F'|' -A -t \
    < "$SQL_FILE" 2>&1)
RC=$?

if (( RC != 0 )); then
  echo "[FATAL] PG query failed (rc=$RC):"
  echo "$SQL_OUTPUT"
  exit 2
fi

# ─── 4. Parse SQL output for verdict ──────────────────────────────────────
FAIL_COUNT=0
WARN_COUNT=0

# §1 sample_inter_arrival：delta_seconds 欄位（第 5 欄；NULL 跳過首筆）
# §2 samples_per_min：count 欄位（第 5 欄）
# §3 30min_summary：row_count_30min 欄位 + avg_delta_seconds 欄位

while IFS='|' read -r check_name domain metric_name col4 col5; do
  [[ -z "${check_name// }" ]] && continue

  case "$check_name" in
    "§1 sample_inter_arrival")
      # col5 = delta_seconds；NULL（首筆）跳過
      if [[ -n "$col5" && "$col5" != " " ]]; then
        # delta 範圍檢查：58-62 PASS / 55-65 WARN / 其他 FAIL
        delta_int=$(printf "%.0f" "$col5" 2>/dev/null || echo 0)
        if (( delta_int < 55 || delta_int > 65 )); then
          echo "[FAIL] §1 $domain $metric_name delta=$col5 sec (expected 58-62)"
          FAIL_COUNT=$((FAIL_COUNT + 1))
        elif (( delta_int < 58 || delta_int > 62 )); then
          (( QUIET == 0 )) && echo "[WARN] §1 $domain $metric_name delta=$col5 sec (scheduler jitter)"
          WARN_COUNT=$((WARN_COUNT + 1))
        fi
      fi
      ;;
    "§2 samples_per_min")
      # col5 = samples_per_min；應 == 1
      samples="$col5"
      # 為什麼顯式 regex check：原本 `2>/dev/null` 抑制非數字 stderr 是
      # except:pass 反模式（per feedback_working_principles 「誠實報告測試」）；
      # 非數字 sample value（如 SQL parse 漏接 NULL / column drift）必須 fail
      # loud 而非靜默歸 OK band。
      if [[ ! "$samples" =~ ^[0-9]+$ ]]; then
        echo "[FAIL] §2 $domain $metric_name bucket=$col4 samples_per_min='$samples' (非數字；SQL parse 漏接 or column drift)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
      elif [[ "$samples" == "0" ]]; then
        echo "[FAIL] §2 $domain $metric_name bucket=$col4 samples_per_min=0 (emitter task crashed?)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
      elif (( samples > 2 )); then
        echo "[FAIL] §2 $domain $metric_name bucket=$col4 samples_per_min=$samples (duplicate emit bug?)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
      fi
      ;;
    "§3 30min_summary")
      # col4 = row_count_30min；col5 = avg_delta_seconds
      row_count="$col4"
      avg_delta="$col5"
      # 同上：row_count 非數字必須 fail loud。
      if [[ ! "$row_count" =~ ^[0-9]+$ ]]; then
        echo "[FAIL] §3 $domain $metric_name 30min row_count='$row_count' (非數字；SQL parse 漏接 or column drift)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
      elif (( row_count < 25 )); then
        echo "[FAIL] §3 $domain $metric_name 30min row_count=$row_count (expected ~30)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
      else
        (( QUIET == 0 )) && echo "[OK] §3 $domain $metric_name row=$row_count avg_delta=${avg_delta}s"
      fi
      ;;
  esac
done <<<"$SQL_OUTPUT"

# ─── 5. Verdict ────────────────────────────────────────────────────────────
if (( FAIL_COUNT > 0 )); then
  echo "[FAIL] 60s boundary verify: $FAIL_COUNT failure(s), $WARN_COUNT warning(s)"
  exit 1
fi

(( QUIET == 0 )) && echo "[PASS] 60s boundary verify: 0 failure, $WARN_COUNT warning(s) (scheduler jitter only)"
exit 0
