#!/usr/bin/env bash
# flash_dip_death_rate_cron.sh — flash_dip_buy demo pilot death-rate 監測
#                               （FLASH-DIP-DEATH-RATE survival lens，daily，read-only）
#
# Suggested cron entry, installed manually by the operator:
#   53 6 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/flash_dip_death_rate_cron.sh
#
# 為什麼需要這支：flash_dip_buy 是 K=0.15 深價 dip-buy demo pilot（fixed-notional nf<=3%，
# N=3 日 hold）。深價均值回歸的尾部風險 = 進場後標的續跌、hold 期內標的「腰斬」（realized
# return <= -50%）。phase-2 設計原本要一個 CUSUM auto-breaker 在 death-rate 漂移時自動熔斷該
# 策略；該 auto-breaker 已 DEFERRED。本支是其 interim：純讀 trading.fills，量已了結（closed）
# flash_dip 深-K slot 的 death-rate = realized return <= -50% 的比例，n>=20 才視為可行動
# （min-sample，對齊 single-cell 顯著性下限的保守選擇），death-rate>3% 落 alerts.jsonl 告警。
# 它不熔斷任何東西（read-only），只把「該人工 disable pilot」的訊號變成可被看到的告警。
#
# death-rate 模型（純 trading.fills，read-only）：
#   - closed 深-K slot = 一筆 flash_dip CLOSE fill（exit_reason IS NOT NULL，engine_mode='demo'，
#     strategy_name='flash_dip_buy'）。close fill 攜 realized_pnl + entry_context_id（V083：close
#     fill 必攜 entry_context_id → 指向 ENTRY fill 的 context_id）。
#   - entry notional = 對應 ENTRY fill（exit_reason IS NULL，context_id = close.entry_context_id）
#     的 price * qty。flash_dip 是 long-only（dip-buy），entry notional 為正基準。
#   - realized_return = realized_pnl / entry_notional。death = realized_return <= -0.50。
#   - death_rate = deaths / n_closed_slots；n_closed_slots >= MIN_N（預設 20）才 actionable。
#   為什麼用 entry_context_id join 而非 close fill 自身 price*qty：close notional 是「出場時」
#   名目（已含跌幅），用它當分母會低估虧損比例；entry notional 才是 -50% 的正確基準。缺
#   entry fill（歷史 NULL entry_context_id）→ 該 slot 排除（fail-soft，不污染 death-rate）。
#
# 硬邊界（純讀 + 記錄 + 告警）：read-only PG（PGOPTIONS=-c default_transaction_read_only=on
# 在連線層強制，涵蓋所有 psql 呼叫；刻意不在 SQL 內放 `SET TRANSACTION READ ONLY;` —— SET 的
# command tag（"SET"）會混入 -A -t stdout 污染 status JSON，破壞 json.loads 解析，這正是
# recorder_health_cron.sh 修掉的 bug）。不啟任何 flag、不重啟、不熔斷、不寫任何 trading/market
# 表、不下單、不碰 auth/lease/risk_config、不部署（phase-2 CUSUM auto-breaker 已 DEFERRED，本支
# 只告警不動作）。唯二寫入面 = <DATA>/logs/flash_dip_death_rate.log（daily JSON status line）+
# death-rate 超門檻時 <DATA>/alerts/alerts.jsonl。PG 憑證走 basic_system_services.env grep-parse
# （鏡像 recorder_health_cron.sh / recorder_mm_verdict_cron.sh，禁硬編 trading_admin）。
# 配對 healthcheck sentinel：<DATA>/cron_heartbeat/flash_dip_death_rate.last_fire。

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/flash_dip_death_rate_cron.log"
STATUS_LOG="${LOG_DIR}/flash_dip_death_rate.log"
ALERT_DIR="${DATA}/alerts"
ALERT_FILE="${ALERT_DIR}/alerts.jsonl"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/flash_dip_death_rate_cron.lock.d"

# death-rate 門檻（皆可由 env 覆寫）：
#   MIN_N：metric 可行動的最小 closed-slot 樣本（n<MIN_N → not actionable，不發告警，誠實）。
MIN_N="${OPENCLAW_FLASH_DIP_DEATHRATE_MIN_N:-20}"
#   DEATH_THRESHOLD_PCT：death-rate（百分比）告警門檻（預設 3%）。
DEATH_THRESHOLD_PCT="${OPENCLAW_FLASH_DIP_DEATHRATE_THRESHOLD_PCT:-3.0}"
#   DEATH_RETURN：單 slot「死亡」的 realized-return 門檻（預設 -0.50 = -50%）。
DEATH_RETURN="${OPENCLAW_FLASH_DIP_DEATH_RETURN:--0.50}"
#   engine_mode 範圍：pilot 是 demo-only（registry kind-gate）；保守鎖 demo，避免誤納其他模式。
ENGINE_MODE="${OPENCLAW_FLASH_DIP_DEATHRATE_ENGINE_MODE:-demo}"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$ALERT_DIR"

# Cron heartbeat sentinel — FLASH-DIP-DEATH-RATE（2026-06-18）。
# touch-at-start：「cron 被排程觸發」的證據，由配對 healthcheck 監測 mtime。
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true
touch "$HEARTBEAT_DIR/flash_dip_death_rate.last_fire" 2>/dev/null || true

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
# read-only 在連線層強制（涵蓋所有 psql 呼叫）：任何誤寫 fail-loud。
# 刻意不在 SQL 內放 `SET TRANSACTION READ ONLY;` —— SET 的 command tag（"SET"）會混入
# -A -t stdout 污染 STATUS JSON，破壞 json.loads 解析（recorder_health_cron 修掉的 bug）。
export PGOPTIONS="-c default_transaction_read_only=on"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: flash_dip death-rate check already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

echo "[$(ts)] === flash_dip death-rate check start (min_n=${MIN_N} threshold_pct=${DEATH_THRESHOLD_PCT} death_return=${DEATH_RETURN} engine_mode=${ENGINE_MODE}) ===" >> "$LOG"

# ---------------------------------------------------------------------------
# 唯讀 death-rate 查詢：單行 JSON（json_build_object），供 shell 用 python3 解析告警。
# closed 深-K slot = flash_dip CLOSE fill join 回其 ENTRY fill 取 entry notional，算 realized_return。
#   - close fill：strategy_name='flash_dip_buy' AND exit_reason IS NOT NULL AND engine_mode=:mode。
#   - entry fill：exit_reason IS NULL（V083：entry row entry_context_id 恆 NULL）
#                 AND context_id = close.entry_context_id。取 price*qty 為 entry notional。
#   - realized_return = realized_pnl / entry_notional；death = realized_return <= DEATH_RETURN。
# 缺 entry（entry_context_id NULL 或 join 不到）→ INNER JOIN 自動排除（fail-soft，不污染分母）。
# entry notional <= 0 → 同樣排除（NULLIF 防除零）。輸出 n / deaths / death_rate_pct + 樣本診斷。
# ---------------------------------------------------------------------------
read -r -d '' DEATH_SQL <<SQL || true
WITH closes AS (
  -- 已了結的 flash_dip 深-K slot 的 CLOSE fill（攜 realized_pnl + entry_context_id）。
  SELECT fill_id, ts, symbol, realized_pnl, entry_context_id
  FROM trading.fills
  WHERE strategy_name = 'flash_dip_buy'
    AND exit_reason IS NOT NULL
    AND engine_mode = '${ENGINE_MODE}'
    AND entry_context_id IS NOT NULL
),
slots AS (
  -- join 回 ENTRY fill 取 entry notional（price*qty），算 per-slot realized_return。
  SELECT c.fill_id,
         c.symbol,
         c.realized_pnl::double precision AS realized_pnl,
         (e.price::double precision * e.qty::double precision) AS entry_notional,
         (c.realized_pnl::double precision
            / NULLIF(e.price::double precision * e.qty::double precision, 0)) AS realized_return
  FROM closes c
  JOIN trading.fills e
    ON e.context_id = c.entry_context_id
   AND e.exit_reason IS NULL
   AND e.strategy_name = 'flash_dip_buy'
),
slots_valid AS (
  -- entry_notional<=0 或 realized_return NULL（除零）→ 排除（fail-soft）。
  SELECT * FROM slots WHERE entry_notional > 0 AND realized_return IS NOT NULL
)
SELECT json_build_object(
  'n_closed_slots', (SELECT count(*) FROM slots_valid),
  'n_deaths', (SELECT count(*) FROM slots_valid WHERE realized_return <= ${DEATH_RETURN}),
  'death_rate_pct', (SELECT CASE WHEN count(*) > 0
        THEN round(100.0 * count(*) FILTER (WHERE realized_return <= ${DEATH_RETURN})
                   / count(*), 4)
        ELSE NULL END
      FROM slots_valid),
  'worst_return', (SELECT round(min(realized_return)::numeric, 4) FROM slots_valid),
  'median_return', (SELECT round((percentile_cont(0.5)
        WITHIN GROUP (ORDER BY realized_return))::numeric, 4) FROM slots_valid),
  'n_closes_seen', (SELECT count(*) FROM closes),
  'n_dropped_no_entry', (SELECT count(*) FROM closes) - (SELECT count(*) FROM slots)
);
SQL

# psql 以 if 條件執行：非零退出不觸發 set -e 提前中止，rc 才能被捕捉供 FAIL 日誌
# （鏡像 recorder_health_cron.sh / recorder_mm_verdict_cron.sh 的 rc-capture 修正模式）。
rc=0
DEATH_JSON=""
if DEATH_JSON=$(psql -X -A -t -v ON_ERROR_STOP=1 -c "$DEATH_SQL" 2>>"$LOG"); then rc=0; else rc=$?; fi

if [[ "$rc" -ne 0 || -z "$DEATH_JSON" ]]; then
    # psql rc=0 但結果空 → 仍視為失敗（避免記 FAIL 卻 exit 0 的語意不一致）。
    [[ "$rc" -eq 0 ]] && rc=1
    echo "[$(ts)] === flash_dip death-rate check end FAIL rc=${rc} (psql query failed/empty) ===" >> "$LOG"
    exit "$rc"
fi

# ---------------------------------------------------------------------------
# python3 端：判定告警條件、組裝 status line。只讀字串 + 純算術，不連 DB（DB 已在上方關閉）。
# 告警 gate：death_rate_pct > THRESHOLD AND n_closed_slots >= MIN_N（min-sample 才 actionable）。
# n<MIN_N → not actionable，不發告警（誠實，避免小樣本噪音觸發）。
# 輸出兩行至 stdout：第一行 STATUS=<json>（落 status log）；第二行 ALERT=<json or empty>。
# ---------------------------------------------------------------------------
PY_OUT=$(DEATH_JSON="$DEATH_JSON" \
    MIN_N="$MIN_N" \
    DEATH_THRESHOLD_PCT="$DEATH_THRESHOLD_PCT" \
    DEATH_RETURN="$DEATH_RETURN" \
    ENGINE_MODE="$ENGINE_MODE" \
    python3 - <<'PY' 2>>"$LOG" || true
import json, os, datetime

d = json.loads(os.environ["DEATH_JSON"])
min_n = int(float(os.environ["MIN_N"]))
threshold_pct = float(os.environ["DEATH_THRESHOLD_PCT"])
death_return = float(os.environ["DEATH_RETURN"])
engine_mode = os.environ["ENGINE_MODE"]

n = int(d.get("n_closed_slots") or 0)
deaths = int(d.get("n_deaths") or 0)
death_rate_pct = d.get("death_rate_pct")  # NULL（n=0）→ None
death_rate_pct = None if death_rate_pct is None else float(death_rate_pct)

# actionable：n>=MIN_N（min-sample 門檻）。n 不足 → metric 不可行動，不發告警（誠實）。
actionable = n >= min_n
alert = None
if actionable and death_rate_pct is not None and death_rate_pct > threshold_pct:
    alert = (f"[FLASH-DIP-DEATH-RATE] death-rate {death_rate_pct:.2f}% > {threshold_pct:.1f}% "
             f"(n={n} deaths={deaths} worst={d.get('worst_return')} "
             f"median={d.get('median_return')}); flash_dip_buy demo pilot tail-risk breached "
             f"-> consider manual disable (phase-2 CUSUM auto-breaker DEFERRED; this monitor "
             f"is alert-only, no auto-circuit-breaker action taken)")

status = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "check": "flash_dip_death_rate",
    "engine_mode": engine_mode,
    "model": ("death_rate = fraction of closed flash_dip deep-K slots with "
              "realized_return = realized_pnl/entry_notional <= death_return, within N=3 hold"),
    "thresholds": {"min_n": min_n, "death_threshold_pct": threshold_pct,
                   "death_return": death_return},
    "n_closed_slots": n,
    "n_deaths": deaths,
    "death_rate_pct": death_rate_pct,
    "worst_return": d.get("worst_return"),
    "median_return": d.get("median_return"),
    "n_closes_seen": d.get("n_closes_seen"),
    "n_dropped_no_entry": d.get("n_dropped_no_entry"),
    "actionable": actionable,
    "alerted": alert is not None,
    "note": ("interim monitor for the DEFERRED phase-2 CUSUM auto-breaker; "
             "read-only, alert-only, takes no circuit-breaker / disable action"),
}
print("STATUS=" + json.dumps(status, separators=(",", ":"), default=str))
print("ALERT=" + (alert if alert is not None else ""))
PY
)

# 解析 python3 兩行輸出（fail-soft：缺行 → 視為無 status / 無告警）。
STATUS_JSON=$(printf '%s\n' "$PY_OUT" | grep '^STATUS=' | head -n1 | cut -d= -f2-)
ALERT_SUBJECT=$(printf '%s\n' "$PY_OUT" | grep '^ALERT=' | head -n1 | cut -d= -f2-)

if [[ -z "$STATUS_JSON" ]]; then
    echo "[$(ts)] === flash_dip death-rate check end FAIL (python3 synthesis empty) ===" >> "$LOG"
    exit 1
fi

echo "$STATUS_JSON" >> "$STATUS_LOG"
echo "[$(ts)] status: $STATUS_JSON" >> "$LOG"

# ---------------------------------------------------------------------------
# ALERT：death-rate>門檻 AND n>=MIN_N 時 append alerts.jsonl（同 alert_sink.py schema：
# ts_utc/subject/severity/body/channels_attempted/channels_ok）。survival tail-risk =
# critical（深價 dip-buy 腰斬比例過高應立即被看到並考慮人工 disable）。用 python3 emit
# （避免 shell JSON 拼接脆弱性；只讀字串不連 DB）。
# ---------------------------------------------------------------------------
if [[ -n "$ALERT_SUBJECT" ]]; then
    ALERT_SUBJECT="$ALERT_SUBJECT" python3 - >> "$ALERT_FILE" 2>>"$LOG" <<'PY' || true
import json, os, time
subj = os.environ["ALERT_SUBJECT"]
rec = {
    "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "subject": subj,
    "severity": "critical",
    "body": subj + " (read-only flash_dip death-rate monitor; no trading/disable action taken).",
    "channels_attempted": [],
    "channels_ok": None,
}
print(json.dumps(rec, separators=(",", ":")))
PY
    echo "[$(ts)] ALERT appended: $ALERT_SUBJECT" >> "$LOG"
fi

echo "[$(ts)] === flash_dip death-rate check end OK ===" >> "$LOG"
exit 0
