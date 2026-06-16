#!/usr/bin/env bash
# recorder_health_cron.sh — campaign-8 microstructure recorder 耐久健康監測
#                           （DURABLE-MONITOR microstructure lead，daily，read-only）
#
# Suggested cron entry, installed manually by the operator:
#   23 6 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/recorder_health_cron.sh
#
# 為什麼需要這支：microstructure lead 的驗證跨「週」（regime 覆蓋累積 + CP-1/CP-2/CP-3）。
# session loop / cloud schedule 觸不到 private trade-core runtime，所以唯一耐久機制 =
# trade-core 本機 cron。最大風險 = recorder 在數週內「靜默停擺」沒人發現 → 本支每日
# 量測 market.trades / market.ob_top /（recorder-v2 上線後）market.l1_events 的
# rows / 新鮮度 / 24h 累積率 / hypertable_size + regime-day 計數，並在任一 live 流
# max(ts) 過期（trades/ob_top stale > THRESHOLD 分）時落 alerts.jsonl 告警。
#
# 硬邊界（純讀 + 記錄 + 告警）：read-only PG（SET TRANSACTION READ ONLY）；
# 不啟任何 flag、不重啟、不寫任何 trading/market 表、不部署。唯二寫入面 =
# <DATA>/logs/recorder_health.log（daily JSON status line）+ stale 時 <DATA>/alerts/alerts.jsonl。
# PG 憑證走 basic_system_services.env grep-parse（鏡像 kline_calibration_cron.sh，禁硬編 trading_admin）。
# 配對 healthcheck sentinel：<DATA>/cron_heartbeat/recorder_health.last_fire。

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/recorder_health_cron.log"
STATUS_LOG="${LOG_DIR}/recorder_health.log"
ALERT_DIR="${DATA}/alerts"
ALERT_FILE="${ALERT_DIR}/alerts.jsonl"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/recorder_health_cron.lock.d"

# live 流 max(ts) 過期門檻（分）：engine 應在跑 → trades/ob_top 不該超過此沉默。
STALE_THRESHOLD_MIN="${OPENCLAW_RECORDER_STALE_THRESHOLD_MIN:-15}"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$ALERT_DIR"

# Cron heartbeat sentinel — DURABLE-MONITOR（2026-06-16）。
# touch-at-start：「cron 被排程觸發」的證據，由配對 healthcheck 監測 mtime。
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true
touch "$HEARTBEAT_DIR/recorder_health.last_fire" 2>/dev/null || true

ts() { date '+%Y-%m-%d %H:%M:%S'; }

SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[$(ts)] FATAL: env file missing: $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi

PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_DB=$(grep '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST=$(grep '^POSTGRES_HOST=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_PORT=$(grep '^POSTGRES_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"

if [[ -z "$PG_PASS" || -z "$PG_USER" || -z "$PG_DB" ]]; then
    echo "[$(ts)] FATAL: PG creds incomplete in $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi

export PGHOST="$PG_HOST" PGPORT="$PG_PORT" PGDATABASE="$PG_DB" PGUSER="$PG_USER" PGPASSWORD="$PG_PASS"
# read-only 在連線層強制（涵蓋所有 psql 呼叫，含 l1_events 存在性探查）：任何誤寫 fail-loud。
# 刻意不在 SQL 內放 `SET TRANSACTION READ ONLY;` —— SET 的 command tag（"SET"）會混入
# -A -t stdout 污染 HEALTH_JSON，破壞 status line 與 stale 解析（曾致 json.loads JSONDecodeError）。
export PGOPTIONS="-c default_transaction_read_only=on"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: recorder health check already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

echo "[$(ts)] === recorder health check start (stale_threshold=${STALE_THRESHOLD_MIN}min) ===" >> "$LOG"

# ---------------------------------------------------------------------------
# 唯讀健康查詢：對每個流量測 rows / freshness / 24h 累積 / hypertable_size，
# 規模流 stale_min（max(ts) 距今分鐘），l1_events 條件式 is_snapshot 比例 + bad-tick
# 代理（crossed/locked 率），以及 regime-day 計數（distinct UTC 日）。
# l1_events 用「先探存在性 + 條件拼接 SQL 片段（__L1_FRAG__）」處理：不可在主 query 內用
# CASE 引用未建表 —— PG 在 parse/plan 階段即解析 query 內所有 relation（即使包在 CASE ELSE
# 臂裡），故 recorder-v2 上線前（market.l1_events 不存在）整條 query 會 parse-time FAIL。
# read-only 已由 PGOPTIONS 在連線層強制（見上方 export），SQL 內不放 SET（避免 command tag 污染）。
# 輸出 JSON 字典（json_build_object）一行，供 shell 解析 stale 並落 status log。
# ---------------------------------------------------------------------------
read -r -d '' HEALTH_SQL <<'SQL' || true
WITH trades_m AS (
  SELECT count(*) AS rows,
         max(ts) AS max_ts,
         (SELECT count(*) FROM market.trades WHERE ts >= now() - interval '24 hours') AS rows_24h,
         EXTRACT(EPOCH FROM (now() - max(ts)))/60.0 AS stale_min,
         pg_size_pretty(hypertable_size('market.trades')) AS hsize,
         (SELECT count(DISTINCT (ts AT TIME ZONE 'UTC')::date) FROM market.trades) AS regime_days
  FROM market.trades
),
obtop_m AS (
  SELECT count(*) AS rows,
         max(ts) AS max_ts,
         (SELECT count(*) FROM market.ob_top WHERE ts >= now() - interval '24 hours') AS rows_24h,
         EXTRACT(EPOCH FROM (now() - max(ts)))/60.0 AS stale_min,
         pg_size_pretty(hypertable_size('market.ob_top')) AS hsize,
         -- v1 ob_top 壞 tick 代理：crossed/locked 或單邊空簿率（recorder-v2 前的基線）
         (SELECT round(100.0 * count(*) FILTER (
              WHERE NOT (best_ask > best_bid AND bid_size > 0 AND ask_size > 0))
            / greatest(count(*),1), 2)
          FROM market.ob_top WHERE ts >= now() - interval '24 hours') AS bad_tick_pct_24h
  FROM market.ob_top
)
SELECT json_build_object(
  'trades', (SELECT json_build_object(
       'rows', rows, 'max_ts', max_ts, 'rows_24h', rows_24h,
       'stale_min', round(stale_min::numeric, 2), 'hypertable_size', hsize,
       'regime_days', regime_days) FROM trades_m),
  'ob_top', (SELECT json_build_object(
       'rows', rows, 'max_ts', max_ts, 'rows_24h', rows_24h,
       'stale_min', round(stale_min::numeric, 2), 'hypertable_size', hsize,
       'bad_tick_pct_24h', bad_tick_pct_24h) FROM obtop_m),
  'l1_events', __L1_FRAG__
);
SQL

# l1_events 段必須延遲到 runtime 才引用該表（見上方註解）：先探存在性，只在存在時才把
# 引用 market.l1_events 的 SQL 片段拼進主 query；不存在 → present:false 字面片段（零表引用）。
# 探查失敗（psql 出錯）→ L1_PRESENT 保持 "f" → 安全降級為 present:false，不阻斷整體健康檢查。
L1_PRESENT="f"
if _l1=$(psql -X -A -t -c "SELECT (to_regclass('market.l1_events') IS NOT NULL);" 2>>"$LOG"); then
    L1_PRESENT=$(printf '%s' "$_l1" | tr -d '[:space:]')
fi
if [[ "$L1_PRESENT" == "t" ]]; then
    L1_FRAG="(SELECT json_build_object('present', true, 'rows', count(*), 'max_ts', max(ts), 'rows_24h', (SELECT count(*) FROM market.l1_events WHERE ts >= now() - interval '24 hours'), 'stale_min', round((EXTRACT(EPOCH FROM (now() - max(ts)))/60.0)::numeric, 2), 'hypertable_size', pg_size_pretty(hypertable_size('market.l1_events')), 'is_snapshot_ratio_24h', (SELECT round(avg(CASE WHEN is_snapshot THEN 1.0 ELSE 0.0 END)::numeric, 4) FROM market.l1_events WHERE ts >= now() - interval '24 hours'), 'crossed_locked_pct_24h', (SELECT round(100.0 * count(*) FILTER (WHERE best_ask <= best_bid) / greatest(count(*),1), 2) FROM market.l1_events WHERE ts >= now() - interval '24 hours')) FROM market.l1_events)"
else
    L1_FRAG="json_build_object('present', false)"
fi
HEALTH_SQL="${HEALTH_SQL//__L1_FRAG__/$L1_FRAG}"

# psql 以 if 條件執行：非零退出不觸發 set -e 提前中止，rc 才能被捕捉供 FAIL 日誌
# （鏡像 kline_calibration_cron.sh / feature_baseline_writer_cron.sh 的 rc-capture 修正模式）。
rc=0
HEALTH_JSON=""
if HEALTH_JSON=$(psql -X -A -t -v ON_ERROR_STOP=1 -c "$HEALTH_SQL" 2>>"$LOG"); then rc=0; else rc=$?; fi

if [[ "$rc" -ne 0 || -z "$HEALTH_JSON" ]]; then
    # psql rc=0 但結果空 → 仍視為失敗（避免記 FAIL 卻 exit 0 的語意不一致）。
    [[ "$rc" -eq 0 ]] && rc=1
    echo "[$(ts)] === recorder health check end FAIL rc=${rc} (psql query failed/empty) ===" >> "$LOG"
    exit "$rc"
fi

# regime-day 計數（朝 >=10-12 CP-3 門檻）與 status line 一起落到專屬 artifact。
STATUS_LINE=$(printf '{"ts_utc":"%s","check":"recorder_health","health":%s,"stale_threshold_min":%s}' \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$HEALTH_JSON" "$STALE_THRESHOLD_MIN")
echo "$STATUS_LINE" >> "$STATUS_LOG"
echo "[$(ts)] status: $HEALTH_JSON" >> "$LOG"

# ---------------------------------------------------------------------------
# ALERT：任一 live 流 max(ts) stale 超過門檻 = recorder 停擺（這正是數週內不能讓它靜默發生的事）。
# 落 alerts.jsonl（與 alert_sink.py 同 schema：ts_utc/subject/severity/body/channels_attempted/channels_ok）。
# 用 python3 抽 stale_min（避免 shell 解析 JSON 的脆弱性；只讀字串不連 DB）。
# ---------------------------------------------------------------------------
STALE_SUBJECTS=$(HEALTH_JSON="$HEALTH_JSON" THRESH="$STALE_THRESHOLD_MIN" python3 - <<'PY' 2>>"$LOG" || true
import json, os
h = json.loads(os.environ["HEALTH_JSON"])
thr = float(os.environ["THRESH"])
stale = []
for stream in ("trades", "ob_top"):  # live 流：engine 在跑就該持續寫
    s = h.get(stream) or {}
    sm = s.get("stale_min")
    if sm is not None and float(sm) > thr:
        stale.append(f"{stream}=stale {float(sm):.1f}min(>{thr:.0f})")
# l1_events 僅在 present 時納入（recorder-v2 未上線前不告警其缺席）
l1 = h.get("l1_events") or {}
if l1.get("present"):
    sm = l1.get("stale_min")
    if sm is not None and float(sm) > thr:
        stale.append(f"l1_events=stale {float(sm):.1f}min(>{thr:.0f})")
print("; ".join(stale))
PY
)

if [[ -n "$STALE_SUBJECTS" ]]; then
    ALERT_TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    BODY="recorder stalled: ${STALE_SUBJECTS}. engine should be running; microstructure recorder appears stopped."
    printf '{"ts_utc":"%s","subject":"%s","severity":"%s","body":"%s","channels_attempted":[],"channels_ok":null}\n' \
        "$ALERT_TS" "[RECORDER-HEALTH] recorder stalled" "critical" "$BODY" >> "$ALERT_FILE"
    echo "[$(ts)] ALERT appended: $STALE_SUBJECTS" >> "$LOG"
fi

echo "[$(ts)] === recorder health check end OK ===" >> "$LOG"
exit 0
