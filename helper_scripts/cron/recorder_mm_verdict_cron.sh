#!/usr/bin/env bash
# recorder_mm_verdict_cron.sh — market-making (maker) live net-edge verdict 監測
#                              （MM-VERDICT fee-inverting lens，daily，read-only）
#
# Suggested cron entry, installed manually by the operator:
#   41 6 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/recorder_mm_verdict_cron.sh
#
# 為什麼需要這支：14 條 edge 軸全部 sub-fee-floor（結構性鐵律：以 taker 付費的方向性
# 預測無法翻過 taker 成本牆）。唯一能反轉 fee 符號的 lens = 做市（以 maker 賺 spread/rebate
# 而非以 taker 付費）。其量測基建已部署且正在累積：(a) recorder-v2 full-L1（market.l1_events，
# 乾淨）供離線 fill-sim，(b) maker 成交逆選擇 markout（trading.fills.maker_markout_bps，V145，
# 現已在真實 maker 成交上 populate）。本支把這份「正在累積的資料」轉成 live MM verdict——
# maker 成交是「真實成交」（非模擬）=最直接的 MM 量測。
#
# MODEL（per-symbol live MM net-edge 估計；QC/PA Hybrid-C 裁決，2026-06-17）：
#   MM_net_edge_bps = spread_captured_bps − adverse_selection_bps − FEE_BPS_RT
#   - spread_captured_bps = −mean(maker_markout_bps)
#       maker_markout_bps = fill_price − reference_price（signed-by-side，@submit），對
#       close-maker（reference_source='mid_at_submit'）≈ −half_spread（成交在 bid/ask 比 mid
#       差半個 spread → 帶負號）。翻號得「捕捉到的半價差」（正值）。**這就是捕捉到的 spread，
#       不是逆選擇**——舊模型誤把 ob_top 時間加權 half_spread 與 markout 相加是雙重計入。
#       **必過濾 reference_source='mid_at_submit'**：open-maker 的 reference 是 bbo_same_side
#       （≈ −full_spread，基準不同），混平均會破壞 half-spread 基準一致性。
#   - adverse_selection_bps = 離線 fill_sim 的 fill-only beta-residual fill-conditional
#       adverse_sel_bps@h（h=15s primary；5/30s sensitivity）。讀 fill_sim 最新報告
#       （見下方「為何讀報告而非內跑」）。fill_sim 已算（measure_adverse_selection）。
#   - FEE_BPS_RT = 2 × maker_fee_per_side = 4bp RT（無 rebate，保守）。
#
# 為何讀 fill_sim 報告而非在 cron 內跑（決策 + 理由）：fill_sim 對 market.l1_events 全掃
#   ~4min/12GB，把一支輕量 daily 監測 cron 耦合到重型研究 job 的 runtime/記憶體不穩健，且
#   違背「監測 cron 不做重活」的設計慣例。改讀其最新 JSON 報告（純讀、快、缺檔 fail-soft）：
#   <DATA>/research/fillsim/fillsim_report.json（fill_sim --out 預設）。報告超過
#   MM_FILLSIM_MAX_AGE_H 小時視為 stale，net-edge 退化為「spread_captured 已知、adverse
#   未知」→ 不發 MM-net-positive 告警（fail-soft，誠實）。fill_sim 的重跑由 (c) high-vol /
#   (b) L1-ready 觸發提示，operator/排程另跑（非本 cron 職責）。
#
# 每日量測並在以下任一條件 append alerts.jsonl（同 alert_sink.py schema）：
#   (a) 任一 symbol 的 MM net-edge 估計為正且 n_maker_fills >= 門檻（預設 30，對齊
#       fill_sim MIN_FILLS_FOR_SIGNIF）；**告警明標 single-window != go/no-go**（需跨 regime
#       含 trend-stress）；或
#   (b) recorder-v2 L1 regime-days >= 門檻（預設 10，fill-sim ready）；或
#   (c) 偵測到 high-vol 日（BTC 1m realized vol z-score 超門檻 → fill-sim 重跑候選）。
#
# 硬邊界（純讀 + 記錄 + 告警）：read-only PG（PGOPTIONS=-c default_transaction_read_only=on
# 在連線層強制，涵蓋所有 psql 呼叫；刻意不在 SQL 內放 `SET TRANSACTION READ ONLY;` —— SET 的
# command tag（"SET"）會混入 -A -t stdout 污染 status JSON，破壞 json.loads 解析，這正是
# recorder_health_cron.sh 修掉的 bug）。不啟任何 flag、不重啟、不寫任何 trading/market 表、
# 不下單、不碰 auth/lease、不部署。唯二寫入面 = <DATA>/logs/recorder_mm_verdict.log（daily
# JSON status line）+ 命中條件時 <DATA>/alerts/alerts.jsonl。PG 憑證走 basic_system_services.env
# grep-parse（鏡像 recorder_health_cron.sh / kline_calibration_cron.sh，禁硬編 trading_admin）。
# 配對 healthcheck sentinel：<DATA>/cron_heartbeat/recorder_mm_verdict.last_fire。

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/recorder_mm_verdict_cron.log"
STATUS_LOG="${LOG_DIR}/recorder_mm_verdict.log"
ALERT_DIR="${DATA}/alerts"
ALERT_FILE="${ALERT_DIR}/alerts.jsonl"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/recorder_mm_verdict_cron.lock.d"
# fill_sim 最新報告（read-only；缺檔/過期 → adverse 未知，fail-soft 不發正 net 告警）。
FILLSIM_REPORT="${OPENCLAW_MM_FILLSIM_REPORT:-${DATA}/research/fillsim/fillsim_report.json}"
FILLSIM_HISTORY_SCORECARD="${OPENCLAW_MM_FILLSIM_HISTORY_SCORECARD:-${DATA}/research/fillsim/fillsim_history_scorecard.json}"

# MM verdict 門檻（皆可由 env 覆寫）：
#   n_maker_fills 最小樣本（per-symbol MM-net-positive 告警的可信度門檻；對齊 fill_sim
#   MIN_FILLS_FOR_SIGNIF=30——單 cell 顯著性最低樣本）。
MM_MIN_MAKER_FILLS="${OPENCLAW_MM_MIN_MAKER_FILLS:-30}"
#   maker 單邊費（bps）：BTC/ETH 等主流 perp maker fee 約 2bp；RT = 2×（無 rebate，保守）。
MAKER_FEE_BPS_PER_SIDE="${OPENCLAW_MM_MAKER_FEE_BPS:-2.0}"
#   adverse-selection 主 horizon（秒，對齊 fill_sim DEFAULT_HORIZONS 的 primary=15s）。
MM_ADVERSE_HORIZON_S="${OPENCLAW_MM_ADVERSE_HORIZON_S:-15}"
#   fill_sim 報告最大可接受年齡（小時）；超過視為 stale → adverse 未知，不發正 net 告警。
MM_FILLSIM_MAX_AGE_H="${OPENCLAW_MM_FILLSIM_MAX_AGE_H:-72}"
#   recorder-v2 L1 fill-sim ready 門檻（distinct UTC regime-days）。
MM_L1_REGIME_DAYS="${OPENCLAW_MM_L1_REGIME_DAYS:-10}"
#   high-vol 偵測：BTC 當日 1m realized vol 對 trailing 分布的 z-score 門檻。
MM_HIGHVOL_Z="${OPENCLAW_MM_HIGHVOL_Z:-2.0}"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$ALERT_DIR"

# Cron heartbeat sentinel — MM-VERDICT（2026-06-17）。
# touch-at-start：「cron 被排程觸發」的證據，由配對 healthcheck 監測 mtime。
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true
touch "$HEARTBEAT_DIR/recorder_mm_verdict.last_fire" 2>/dev/null || true

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
# -A -t stdout 污染 STATUS JSON，破壞 status line 與 alert 解析（recorder_health_cron 修掉的 bug）。
export PGOPTIONS="-c default_transaction_read_only=on"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: mm verdict check already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

echo "[$(ts)] === mm verdict check start (min_fills=${MM_MIN_MAKER_FILLS} maker_fee=${MAKER_FEE_BPS_PER_SIDE}bp h=${MM_ADVERSE_HORIZON_S}s fillsim_max_age=${MM_FILLSIM_MAX_AGE_H}h l1_days_thr=${MM_L1_REGIME_DAYS} highvol_z=${MM_HIGHVOL_Z}) ===" >> "$LOG"

# ---------------------------------------------------------------------------
# 唯讀 MM verdict 查詢：單行 JSON（json_build_object），供 shell 用 python3 解析告警。
# 結構：
#   markout：maker 成交 markout 累計 / 24h 計數 + per-symbol mean/median/n。
#            **僅納入 liquidity_role='maker' AND maker_markout_bps NOT NULL AND
#            reference_source='mid_at_submit'**（half-spread 基準一致；open-maker 的
#            bbo_same_side 基準不同，混平均會破壞 half-spread 一致性 → QC/PA 裁決排除）。
#            spread_captured = −mean(markout)，在 python3 端翻號（markout ≈ −half_spread）。
#   l1_readiness：market.l1_events distinct UTC regime-days（朝 fill-sim 門檻）。用 to_regclass 守
#                 存在性（recorder-v2 若未上線 → present:false，安靜跳過，不阻斷整體檢查）。
#   highvol：BTC 1m realized vol（當日 close-to-close log-return 標準差，annualize 無關只比相對）
#            對 trailing N 日同量分布的 z-score。
# 注意：adverse_selection 不在 SQL 算——它是 fill_sim 的 beta-residual fill-conditional 量測，
#   由 python3 端讀 fill_sim 報告取得（見檔頭「為何讀報告而非內跑」）。
# ---------------------------------------------------------------------------
read -r -d '' MM_SQL <<'SQL' || true
WITH maker_fills AS (
  -- 真實 maker 成交（liquidity_role='maker'）且 markout 已 populate；**僅 mid_at_submit
  -- 基準**（half-spread 一致；open-maker bbo_same_side 基準不同，混平均破壞一致性）。
  SELECT symbol, maker_markout_bps AS mk, ts
  FROM trading.fills
  WHERE liquidity_role = 'maker'
    AND maker_markout_bps IS NOT NULL
    AND reference_source = 'mid_at_submit'
),
markout_per_symbol AS (
  SELECT symbol,
         count(*) AS n,
         round(avg(mk)::numeric, 4) AS mean_markout_bps,
         round((percentile_cont(0.5) WITHIN GROUP (ORDER BY mk))::numeric, 4) AS median_markout_bps
  FROM maker_fills
  GROUP BY symbol
),
fills_30d AS (
  -- Local execution throughput proxy only. Demo/live_demo rows do not prove
  -- Bybit mainnet VIP eligibility; they quantify current bot capacity.
  SELECT
      coalesce(engine_mode, 'unknown') AS engine_mode,
      lower(coalesce(liquidity_role, 'unknown')) AS role,
      abs(qty::numeric * price::numeric) AS notional_usd,
      abs(coalesce(fee, 0)::numeric) AS fee_usd
  FROM trading.fills
  WHERE ts >= now() - interval '30 days'
    AND coalesce(engine_mode, '') IN ('demo', 'live_demo', 'live')
    AND coalesce(strategy_name, '') NOT LIKE 'unattributed:%'
    AND qty IS NOT NULL AND price IS NOT NULL
),
fills_30d_by_mode AS (
  SELECT engine_mode,
         count(*) AS fills,
         round(coalesce(sum(notional_usd), 0), 2) AS notional_usd,
         round(coalesce(sum(fee_usd), 0), 4) AS fee_usd
  FROM fills_30d
  GROUP BY engine_mode
),
fee_capacity_summary AS (
  SELECT json_build_object(
    'window_days', 30,
    'fills', (SELECT count(*) FROM fills_30d),
    'notional_usd', (SELECT round(coalesce(sum(notional_usd), 0), 2) FROM fills_30d),
    'fee_usd', (SELECT round(coalesce(sum(fee_usd), 0), 4) FROM fills_30d),
    'effective_fee_bps', (
      SELECT CASE WHEN coalesce(sum(notional_usd), 0) > 0
        THEN round((sum(fee_usd) / sum(notional_usd) * 10000.0), 4)
        ELSE NULL END
      FROM fills_30d
    ),
    'maker_fills', (SELECT count(*) FROM fills_30d WHERE role = 'maker'),
    'maker_notional_usd', (
      SELECT round(coalesce(sum(notional_usd) FILTER (WHERE role = 'maker'), 0), 2)
      FROM fills_30d
    ),
    'taker_fills', (SELECT count(*) FROM fills_30d WHERE role = 'taker'),
    'taker_notional_usd', (
      SELECT round(coalesce(sum(notional_usd) FILTER (WHERE role = 'taker'), 0), 2)
      FROM fills_30d
    ),
    'by_engine_mode', COALESCE((
      SELECT json_object_agg(engine_mode, json_build_object(
          'fills', fills,
          'notional_usd', notional_usd,
          'fee_usd', fee_usd
      ))
      FROM fills_30d_by_mode
    ), '{}'::json),
    'proxy_warning', 'local demo/live_demo/live fills are capacity proxy only; not VIP eligibility proof'
  ) AS j
),
markout_summary AS (
  SELECT json_build_object(
    'n_total', (SELECT count(*) FROM maker_fills),
    'n_24h', (SELECT count(*) FROM maker_fills WHERE ts >= now() - interval '24 hours'),
    'per_symbol', COALESCE((SELECT json_object_agg(symbol, json_build_object(
        'n', n, 'mean_markout_bps', mean_markout_bps, 'median_markout_bps', median_markout_bps))
        FROM markout_per_symbol), '{}'::json)
  ) AS j
),
btc_daily_vol AS (
  -- BTC 1m close-to-close log-return 的每日標準差（過去 trailing 窗）。
  SELECT (ts AT TIME ZONE 'UTC')::date AS d,
         stddev_samp(ln(close / NULLIF(prev_close, 0))) AS rv,
         count(*) AS n_bars
  FROM (
    SELECT ts, close,
           LAG(close) OVER (ORDER BY ts) AS prev_close
    FROM market.klines
    WHERE symbol = 'BTCUSDT' AND timeframe = '1m'
      AND ts >= now() - interval '35 days'
  ) k
  WHERE prev_close IS NOT NULL AND close > 0 AND prev_close > 0
  GROUP BY (ts AT TIME ZONE 'UTC')::date
),
highvol_summary AS (
  SELECT json_build_object(
    'today', (SELECT d FROM btc_daily_vol ORDER BY d DESC LIMIT 1),
    'today_rv', (SELECT round(rv::numeric, 8) FROM btc_daily_vol ORDER BY d DESC LIMIT 1),
    'today_n_bars', (SELECT n_bars FROM btc_daily_vol ORDER BY d DESC LIMIT 1),
    -- trailing 分布（排除當日本身）統計，供 python3 算 z-score。
    'trailing_mean_rv', (SELECT round(avg(rv)::numeric, 8) FROM (
        SELECT rv FROM btc_daily_vol ORDER BY d DESC OFFSET 1) t),
    'trailing_std_rv', (SELECT round(stddev_samp(rv)::numeric, 8) FROM (
        SELECT rv FROM btc_daily_vol ORDER BY d DESC OFFSET 1) t),
    'trailing_days', (SELECT count(*) FROM btc_daily_vol) - 1
  ) AS j
)
SELECT json_build_object(
  'markout', (SELECT j FROM markout_summary),
  'fee_capacity_30d', (SELECT j FROM fee_capacity_summary),
  'l1_readiness', __L1_FRAG__,
  'highvol', (SELECT j FROM highvol_summary)
);
SQL

# l1_events 段延遲到 runtime 才引用該表：先探存在性，只在存在時才把引用 market.l1_events 的
# SQL 片段拼進主 query（PG 在 parse/plan 階段即解析 query 內所有 relation，即使包在 subquery 裡，
# 故 recorder-v2 未上線時整條 query 會 parse-time FAIL）。探查失敗 → L1_PRESENT 保持 "f" → 安全
# 降級 present:false，不阻斷整體 MM verdict 檢查。
L1_PRESENT="f"
if _l1=$(psql -X -A -t -c "SELECT (to_regclass('market.l1_events') IS NOT NULL);" 2>>"$LOG"); then
    L1_PRESENT=$(printf '%s' "$_l1" | tr -d '[:space:]')
fi
if [[ "$L1_PRESENT" == "t" ]]; then
    L1_FRAG="(SELECT json_build_object('present', true, 'regime_days', (SELECT count(DISTINCT (ts AT TIME ZONE 'UTC')::date) FROM market.l1_events), 'rows', count(*), 'max_ts', max(ts)) FROM market.l1_events)"
else
    L1_FRAG="json_build_object('present', false)"
fi
MM_SQL="${MM_SQL//__L1_FRAG__/$L1_FRAG}"

# psql 以 if 條件執行：非零退出不觸發 set -e 提前中止，rc 才能被捕捉供 FAIL 日誌
# （鏡像 recorder_health_cron.sh / kline_calibration_cron.sh 的 rc-capture 修正模式）。
rc=0
MM_JSON=""
if MM_JSON=$(psql -X -A -t -v ON_ERROR_STOP=1 -c "$MM_SQL" 2>>"$LOG"); then rc=0; else rc=$?; fi

if [[ "$rc" -ne 0 || -z "$MM_JSON" ]]; then
    # psql rc=0 但結果空 → 仍視為失敗（避免記 FAIL 卻 exit 0 的語意不一致）。
    [[ "$rc" -eq 0 ]] && rc=1
    echo "[$(ts)] === mm verdict check end FAIL rc=${rc} (psql query failed/empty) ===" >> "$LOG"
    exit "$rc"
fi

# ---------------------------------------------------------------------------
# python3 端：讀 fill_sim 報告取 adverse_selection、合成 per-symbol net-edge、判定三類
# 告警條件、組裝 status line。只讀字串/檔案 + 純算術，不連 DB（DB 已在上方關閉）。
# 輸出兩行至 stdout：
#   第一行 STATUS=<json>（含 verdict 詳情，落 status log）
#   第二行 ALERTS=<json list of subject strings>（命中條件，落 alerts.jsonl）
# ---------------------------------------------------------------------------
PY_OUT=$(MM_JSON="$MM_JSON" \
    OPENCLAW_BASE_DIR="$BASE" \
    MM_MIN_MAKER_FILLS="$MM_MIN_MAKER_FILLS" \
    MAKER_FEE_BPS_PER_SIDE="$MAKER_FEE_BPS_PER_SIDE" \
    MM_ADVERSE_HORIZON_S="$MM_ADVERSE_HORIZON_S" \
    MM_FILLSIM_MAX_AGE_H="$MM_FILLSIM_MAX_AGE_H" \
    MM_L1_REGIME_DAYS="$MM_L1_REGIME_DAYS" \
    MM_HIGHVOL_Z="$MM_HIGHVOL_Z" \
    FILLSIM_REPORT="$FILLSIM_REPORT" \
    FILLSIM_HISTORY_SCORECARD="$FILLSIM_HISTORY_SCORECARD" \
    python3 - <<'PY' 2>>"$LOG" || true
import json, os, datetime, sys

base_dir = os.environ.get("OPENCLAW_BASE_DIR")
if base_dir:
    sys.path.insert(0, base_dir)
from program_code.research.microstructure.fee_path import (
    build_maker_fee_path_feasibility_scorecard,
)

mm = json.loads(os.environ["MM_JSON"])
min_fills = float(os.environ["MM_MIN_MAKER_FILLS"])
maker_fee = float(os.environ["MAKER_FEE_BPS_PER_SIDE"])
fee_rt = 2.0 * maker_fee  # RT fee（無 rebate，保守）= 4bp。
h_primary = int(float(os.environ["MM_ADVERSE_HORIZON_S"]))
fillsim_max_age_h = float(os.environ["MM_FILLSIM_MAX_AGE_H"])
l1_thr = float(os.environ["MM_L1_REGIME_DAYS"])
highvol_z_thr = float(os.environ["MM_HIGHVOL_Z"])
fillsim_path = os.environ["FILLSIM_REPORT"]
fillsim_history_path = os.environ["FILLSIM_HISTORY_SCORECARD"]

markout = mm.get("markout") or {}
l1 = mm.get("l1_readiness") or {}
highvol = mm.get("highvol") or {}
fee_capacity_30d = mm.get("fee_capacity_30d") or {}

per_sym_mk = markout.get("per_symbol") or {}
alerts = []  # alert subject 字串


def _flt(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:
        return None
    return out


def _round(value, ndigits=4):
    out = _flt(value)
    if out is None:
        return None
    return round(out, ndigits)


def _flt_key(value, default=-1e9):
    out = _flt(value)
    return default if out is None else out


def _int_or_zero(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _sample_gated_fill_sim_cost_wall(fillsim, *, h_primary, min_fills):
    """Rank fill_sim cells with the same sample gate used by fill_sim scorecards."""
    edge = fillsim.get("edge_scorecard") or {}
    all_cells = edge.get("all_fill_only_cells") or []
    sample_gated = []
    for cell in all_cells:
        if not isinstance(cell, dict):
            continue
        n = int(cell.get("n") or cell.get("n_fill_only") or 0)
        if n < int(min_fills) or cell.get("signif_suppressed"):
            continue
        net = _flt(cell.get("net_bps"))
        if net is None:
            continue
        row = dict(cell)
        row["n_fill_only"] = n
        sample_gated.append(row)
    sample_gated.sort(key=lambda row: _flt_key(row.get("net_bps")), reverse=True)

    best = sample_gated[0] if sample_gated else None
    break_even = (fillsim.get("maker_fee_sensitivity_scorecard") or {}).get(
        "best_sample_gated_break_even_cell"
    )
    if not isinstance(break_even, dict):
        break_even = None

    if best is None and break_even is None:
        return {
            "available": False,
            "status": "NO_SAMPLE_GATED_FILL_SIM_CELL",
            "horizon_s": h_primary,
            "sample_gate_min_fills": int(min_fills),
            "sample_gated_cell_count": 0,
            "reason": "fill_sim_has_no_sample_gated_fill_only_cells",
        }

    best_net = _flt(best.get("net_bps")) if best else None
    status = (
        "SAMPLE_GATED_CURRENT_FEE_POSITIVE"
        if best_net is not None and best_net > 0.0
        else "SAMPLE_GATED_CURRENT_FEE_COST_WALL"
    )
    be_fee = _flt((break_even or {}).get("break_even_maker_fee_bps_per_side"))
    return {
        "available": True,
        "status": status,
        "horizon_s": h_primary,
        "sample_gate_min_fills": int(min_fills),
        "sample_gated_cell_count": len(sample_gated),
        "current_fee_round_trip_bps": fee_rt,
        "best_sample_gated_current_fee_cell": best,
        "best_sample_gated_break_even_cell": break_even,
        "best_sample_gated_net_bps": _round(best_net, 4),
        "best_sample_gated_fee_round_trip_shortfall_bps": _round(
            (best or {}).get("fee_round_trip_shortfall_bps")
        ),
        "best_sample_gated_required_half_spread_bps": (
            (best or {}).get("required_half_spread_bps")
        ),
        "break_even_maker_fee_bps_per_side": _round(be_fee, 4),
        "fee_reduction_needed_bps_per_side": _round(
            max(0.0, maker_fee - be_fee) if be_fee is not None else None,
            4,
        ),
        "note": (
            "Uses fill_sim sample-gated cells only; live markout n can remain "
            "diagnostic but does not define the sample-gated cost wall."
        ),
    }


def _cell_sample_gated(cell, *, min_fills):
    if not isinstance(cell, dict):
        return False
    return (
        _int_or_zero(cell.get("n") or cell.get("n_fill_only")) >= int(min_fills)
        and not bool(cell.get("signif_suppressed"))
    )


def _compact_gross_cell(cell, *, source, min_fills):
    if not isinstance(cell, dict):
        return None
    edge = _flt(cell.get("edge_before_fees_bps"))
    net = _flt(cell.get("net_bps"))
    if edge is None and net is not None:
        edge = net + fee_rt
    if net is None and edge is not None:
        net = edge - fee_rt
    if edge is None and net is None:
        return None
    n_fill_only = _int_or_zero(cell.get("n") or cell.get("n_fill_only"))
    break_even_fee = edge / 2.0 if edge is not None else None
    return {
        "source": source,
        "name": cell.get("name"),
        "condition": cell.get("condition"),
        "symbol": cell.get("symbol"),
        "queue_position": cell.get("queue_position"),
        "policy": cell.get("policy"),
        "track": cell.get("track"),
        "feature": cell.get("feature"),
        "n_fill_only": n_fill_only,
        "sample_gated": n_fill_only >= int(min_fills) and not bool(cell.get("signif_suppressed")),
        "signif_suppressed": bool(cell.get("signif_suppressed")),
        "edge_before_fees_bps": _round(edge, 4),
        "net_bps": _round(net, 4),
        "fee_round_trip_shortfall_bps": _round(
            cell.get("fee_round_trip_shortfall_bps")
            if cell.get("fee_round_trip_shortfall_bps") is not None
            else (fee_rt - edge if edge is not None else None),
            4,
        ),
        "break_even_maker_fee_bps_per_side": _round(break_even_fee, 4),
        "fee_reduction_needed_bps_per_side": _round(
            max(0.0, maker_fee - break_even_fee) if break_even_fee is not None else None,
            4,
        ),
    }


def _walk_forward_candidates(walk_forward):
    rows = []
    seen = set()

    def add(row):
        if not isinstance(row, dict):
            return
        key = (
            row.get("name"),
            row.get("condition"),
            json.dumps(row.get("train") or {}, sort_keys=True, default=str),
            json.dumps(row.get("holdout") or {}, sort_keys=True, default=str),
        )
        if key in seen:
            return
        seen.add(key)
        rows.append(row)

    for key in (
        "top_train_candidates",
        "top_holdout_gross_candidates",
        "holdout_confirmed_candidates",
        "train_positive_sample_gated_candidates",
        "train_current_fee_clearing_candidates",
    ):
        for row in walk_forward.get(key) or []:
            add(row)
    add(walk_forward.get("best_train_candidate"))
    add(walk_forward.get("best_holdout_confirmed_candidate"))
    add(walk_forward.get("best_holdout_current_fee_candidate"))
    add(walk_forward.get("best_holdout_gross_candidate"))
    return rows


def _compact_walk_forward_candidate(row, *, min_fills, source_prefix="walk_forward"):
    if not isinstance(row, dict):
        return None
    train = _compact_gross_cell(
        row.get("train"),
        source=f"{source_prefix}_train",
        min_fills=min_fills,
    )
    holdout = _compact_gross_cell(
        row.get("holdout"),
        source=f"{source_prefix}_holdout",
        min_fills=min_fills,
    )
    if train is None and holdout is None:
        return None
    decay = None
    if train and holdout and train.get("net_bps") is not None and holdout.get("net_bps") is not None:
        decay = _round(float(train["net_bps"]) - float(holdout["net_bps"]), 4)
    return {
        "name": row.get("name"),
        "condition": row.get("condition"),
        "feature": row.get("feature"),
        "threshold_source": row.get("threshold_source"),
        "train": train,
        "holdout": holdout,
        "train_sample_gated_positive": row.get("train_sample_gated_positive"),
        "holdout_sample_gated_positive": row.get("holdout_sample_gated_positive"),
        "holdout_confirmed": row.get("holdout_confirmed"),
        "train_to_holdout_net_decay_bps": decay,
    }


def _mm_gross_edge_cost_decomposition(fillsim, *, h_primary, min_fills):
    """Separate true no-edge from gross edge that is smaller than current fees."""
    edge = fillsim.get("edge_scorecard") or {}
    fill_cells = [
        _compact_gross_cell(cell, source="edge_scorecard", min_fills=min_fills)
        for cell in edge.get("all_fill_only_cells") or []
        if _cell_sample_gated(cell, min_fills=min_fills)
    ]
    fill_cells = [cell for cell in fill_cells if cell is not None]

    conditional = fillsim.get("conditional_feature_scorecard") or {}
    conditional_cells = [
        _compact_gross_cell(
            cell,
            source="conditional_feature_scorecard",
            min_fills=min_fills,
        )
        for cell in conditional.get("all_cells") or []
        if _cell_sample_gated(cell, min_fills=min_fills)
    ]
    conditional_cells = [cell for cell in conditional_cells if cell is not None]

    walk_forward = fillsim.get("walk_forward_feature_scorecard") or {}
    walk_rows = [
        compact
        for compact in (
            _compact_walk_forward_candidate(row, min_fills=min_fills)
            for row in _walk_forward_candidates(walk_forward)
        )
        if compact is not None
    ]
    walk_train_cells = [
        row["train"] for row in walk_rows
        if row.get("train") and row["train"].get("sample_gated")
    ]
    walk_holdout_cells = [
        row["holdout"] for row in walk_rows
        if row.get("holdout") and row["holdout"].get("sample_gated")
    ]

    low_friction = fillsim.get("low_friction_signal_scorecard") or {}
    low_friction_rows = [
        compact
        for compact in (
            _compact_walk_forward_candidate(
                row,
                min_fills=min_fills,
                source_prefix="low_friction_signal",
            )
            for row in _walk_forward_candidates(low_friction)
        )
        if compact is not None
    ]
    low_friction_train_cells = [
        row["train"] for row in low_friction_rows
        if row.get("train") and row["train"].get("sample_gated")
    ]
    low_friction_holdout_cells = [
        row["holdout"] for row in low_friction_rows
        if row.get("holdout") and row["holdout"].get("sample_gated")
    ]

    all_cells = (
        fill_cells
        + conditional_cells
        + walk_train_cells
        + walk_holdout_cells
        + low_friction_train_cells
        + low_friction_holdout_cells
    )
    current_fee_positive = [
        cell for cell in all_cells
        if _flt(cell.get("net_bps")) is not None and _flt(cell.get("net_bps")) > 0.0
    ]
    gross_positive = [
        cell for cell in all_cells
        if _flt(cell.get("edge_before_fees_bps")) is not None
        and _flt(cell.get("edge_before_fees_bps")) > 0.0
    ]

    best_current_fee = (
        max(all_cells, key=lambda cell: _flt_key(cell.get("net_bps")))
        if all_cells else None
    )
    best_gross = (
        max(gross_positive, key=lambda cell: _flt_key(cell.get("edge_before_fees_bps")))
        if gross_positive else None
    )
    top_gross_cells = sorted(
        gross_positive,
        key=lambda cell: _flt_key(cell.get("edge_before_fees_bps")),
        reverse=True,
    )[:10]
    walk_train_gross = [
        row for row in walk_rows
        if row.get("train")
        and row["train"].get("sample_gated")
        and (_flt(row["train"].get("edge_before_fees_bps")) or -1e9) > 0.0
    ]
    walk_holdout_gross = [
        row for row in walk_rows
        if row.get("holdout")
        and row["holdout"].get("sample_gated")
        and (_flt(row["holdout"].get("edge_before_fees_bps")) or -1e9) > 0.0
    ]
    best_walk_train = (
        max(
            walk_train_gross,
            key=lambda row: _flt_key(row["train"].get("edge_before_fees_bps")),
        )
        if walk_train_gross else None
    )
    best_walk_holdout = (
        max(
            walk_holdout_gross,
            key=lambda row: _flt_key(row["holdout"].get("edge_before_fees_bps")),
        )
        if walk_holdout_gross else None
    )
    both_gross = [
        row for row in walk_rows
        if row.get("train")
        and row.get("holdout")
        and row["train"].get("sample_gated")
        and row["holdout"].get("sample_gated")
        and (_flt(row["train"].get("edge_before_fees_bps")) or -1e9) > 0.0
        and (_flt(row["holdout"].get("edge_before_fees_bps")) or -1e9) > 0.0
    ]
    best_walk_both = (
        max(
            both_gross,
            key=lambda row: min(
                _flt_key(row["train"].get("edge_before_fees_bps")),
                _flt_key(row["holdout"].get("edge_before_fees_bps")),
            ),
        )
        if both_gross else None
    )
    low_friction_holdout_gross = [
        row for row in low_friction_rows
        if row.get("holdout")
        and row["holdout"].get("sample_gated")
        and (_flt(row["holdout"].get("edge_before_fees_bps")) or -1e9) > 0.0
    ]
    best_low_friction_holdout = (
        max(
            low_friction_holdout_gross,
            key=lambda row: _flt_key(row["holdout"].get("edge_before_fees_bps")),
        )
        if low_friction_holdout_gross else None
    )

    if current_fee_positive:
        status = "CURRENT_FEE_GROSS_AND_NET_POSITIVE"
    elif gross_positive:
        status = "GROSS_EDGE_BELOW_CURRENT_FEE_COST_WALL"
    else:
        status = "NO_SAMPLE_GATED_GROSS_EDGE"

    return {
        "available": bool(all_cells),
        "status": status,
        "horizon_s": h_primary,
        "sample_gate_min_fills": int(min_fills),
        "current_maker_fee_bps_per_side": maker_fee,
        "current_fee_round_trip_bps": fee_rt,
        "sample_gated_cell_count": len(all_cells),
        "sample_gated_fill_only_cell_count": len(fill_cells),
        "sample_gated_fill_only_gross_positive_count": len([
            cell for cell in fill_cells
            if (_flt(cell.get("edge_before_fees_bps")) or -1e9) > 0.0
        ]),
        "sample_gated_conditional_cell_count": len(conditional_cells),
        "sample_gated_walk_forward_candidate_count": len(walk_rows),
        "sample_gated_low_friction_signal_candidate_count": len(low_friction_rows),
        "gross_positive_sample_gated_cell_count": len(gross_positive),
        "current_fee_positive_sample_gated_cell_count": len(current_fee_positive),
        "best_sample_gated_current_fee_cell": best_current_fee,
        "best_sample_gated_gross_cell": best_gross,
        "top_sample_gated_gross_cells": top_gross_cells,
        "best_sample_gated_gross_edge_bps": (
            best_gross.get("edge_before_fees_bps") if best_gross else None
        ),
        "best_gross_cell_net_bps": best_gross.get("net_bps") if best_gross else None,
        "best_current_fee_net_bps": (
            best_current_fee.get("net_bps") if best_current_fee else None
        ),
        "break_even_maker_fee_bps_per_side": (
            best_gross.get("break_even_maker_fee_bps_per_side") if best_gross else None
        ),
        "fee_reduction_needed_bps_per_side": (
            best_gross.get("fee_reduction_needed_bps_per_side") if best_gross else None
        ),
        "best_walk_forward_train_gross_candidate": best_walk_train,
        "best_walk_forward_holdout_gross_candidate": best_walk_holdout,
        "best_walk_forward_both_gross_candidate": best_walk_both,
        "best_low_friction_signal_holdout_gross_candidate": best_low_friction_holdout,
        "low_friction_signal_status": low_friction.get("status"),
        "note": (
            "Gross edge is edge_before_fees_bps. If gross edge is positive but "
            "net_bps remains non-positive at the current maker fee, the blocker is "
            "a fee/cost wall rather than absence of any measured signal."
        ),
    }

# --- fill_sim 報告：adverse_selection（beta-residual fill-conditional）---
# 決策：讀最新報告而非內跑（檔頭已記理由）。取 pooled fill_only adverse_sel@h（primary=15s，
# 另記 5/30s sensitivity）。報告缺檔/解析失敗/過期 → adverse 未知（None），net-edge 退化、
# 不發正 net 告警（fail-soft，誠實）。
def _load_fillsim_adverse(path, h_primary, max_age_h):
    info = {"source": path, "present": False, "stale": None, "age_hours": None,
            "stale_reason": None, "data_stale": None, "data_l1_rows_post_filter": None,
            "data_l1_max_ts": None, "data_l1_max_age_hours": None,
            "data_l1_wall_age_hours": None,
            "adverse_sel_bps": None, "adverse_sel_n": None,
            "adverse_sel_signif_suppressed": None, "sensitivity": {}}
    try:
        with open(path) as f:
            rep = json.load(f)
    except (OSError, ValueError):
        return info
    info["present"] = True
    now = datetime.datetime.now(datetime.timezone.utc)
    def _parse_ts(raw):
        ts = datetime.datetime.fromisoformat(str(raw))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        return ts.astimezone(datetime.timezone.utc)

    # 年齡：用報告 generated_at（ISO8601）對比 now，無法解析則標 stale=True 保守。
    gen = rep.get("generated_at")
    try:
        gt = _parse_ts(gen)
        age_h = (now - gt).total_seconds() / 3600.0
        info["age_hours"] = round(age_h, 2)
        info["stale"] = age_h > max_age_h
    except (TypeError, ValueError):
        info["stale"] = True
        info["stale_reason"] = "bad_generated_at"
    data = rep.get("data") or {}
    info["data_l1_rows_post_filter"] = data.get("l1_rows_post_filter")
    info["data_l1_max_ts"] = data.get("l1_max_ts")
    info["data_l1_max_age_hours"] = data.get("l1_max_age_hours")
    info["data_stale"] = False
    try:
        if int(data.get("l1_rows_post_filter") or 0) <= 0:
            info["data_stale"] = True
            info["stale"] = True
            info["stale_reason"] = "empty_l1"
    except (TypeError, ValueError):
        info["data_stale"] = True
        info["stale"] = True
        info["stale_reason"] = "bad_l1_rows"
    try:
        l1_max_ts = data.get("l1_max_ts")
        if not l1_max_ts:
            info["data_stale"] = True
            info["stale"] = True
            info["stale_reason"] = "missing_l1_max_ts"
        else:
            l1_ts = _parse_ts(l1_max_ts)
            data_age = (now - l1_ts).total_seconds() / 3600.0
            info["data_l1_wall_age_hours"] = round(data_age, 3)
            if data_age > max_age_h:
                info["data_stale"] = True
                info["stale"] = True
                info["stale_reason"] = "stale_l1_data"
    except (TypeError, ValueError):
        info["data_stale"] = True
        info["stale"] = True
        info["stale_reason"] = "bad_l1_max_ts"
    try:
        if info["data_l1_wall_age_hours"] is None and data.get("l1_max_age_hours") is not None:
            data_age = float(data.get("l1_max_age_hours"))
            if data_age > max_age_h:
                info["data_stale"] = True
                info["stale"] = True
                info["stale_reason"] = "stale_l1_data"
    except (TypeError, ValueError):
        if info["stale_reason"] is None:
            info["data_stale"] = True
            info["stale"] = True
            info["stale_reason"] = "bad_l1_age"
    if info["stale"] and info["stale_reason"] is None:
        info["stale_reason"] = "stale_generated_at"
    # fill-only 軌（QC/PA：fill_only，非 pooled，非 adverse_through）的 adverse_sel@h。
    fo = (((rep.get("pooled") or {}).get("naive") or {}).get("fill_only") or {})
    info["adverse_sel_bps"] = fo.get(f"adverse_sel_bps@{h_primary}")
    info["adverse_sel_n"] = fo.get("n")
    info["adverse_sel_signif_suppressed"] = fo.get(f"signif_suppressed@{h_primary}")
    info["fill_only_cost_wall"] = {
        "edge_before_fees_bps": fo.get(f"edge_before_fees_bps@{h_primary}"),
        "break_even_fee_round_trip_bps": fo.get(
            f"break_even_fee_round_trip_bps@{h_primary}_maker_exit"
        ),
        "break_even_maker_fee_bps_per_side": fo.get(
            f"break_even_maker_fee_bps_per_side@{h_primary}_maker_exit"
        ),
        "fee_round_trip_shortfall_bps": fo.get(
            f"fee_round_trip_shortfall_bps@{h_primary}_maker_exit"
        ),
        "required_half_spread_bps": fo.get(f"required_half_spread_bps@{h_primary}_maker_exit"),
        "required_maker_rebate_bps_per_side": fo.get(
            f"required_maker_rebate_bps_per_side@{h_primary}_maker_exit"
        ),
    }
    info["edge_scorecard"] = rep.get("edge_scorecard")
    info["horizon_scorecard"] = rep.get("horizon_scorecard")
    info["conditional_feature_scorecard"] = rep.get("conditional_feature_scorecard")
    info["walk_forward_feature_scorecard"] = rep.get("walk_forward_feature_scorecard")
    info["low_friction_signal_scorecard"] = rep.get("low_friction_signal_scorecard")
    info["maker_fee_sensitivity_scorecard"] = rep.get("maker_fee_sensitivity_scorecard")
    # 5/30s sensitivity（誠實透明，不入 net 計算）。
    for hs in (5, 30):
        v = fo.get(f"adverse_sel_bps@{hs}")
        if v is not None:
            info["sensitivity"][f"adverse_sel_bps@{hs}"] = v
    return info

def _load_fillsim_history_scorecard(path):
    info = {"source": path, "present": False, "parse_ok": False, "status": None,
            "generated_at": None, "windows_loaded": None, "valid_windows": None,
            "distinct_window_dates": None, "best_sample_gated_break_even_window": None,
            "reason": None}
    try:
        with open(path) as f:
            rep = json.load(f)
    except FileNotFoundError:
        info["reason"] = "missing"
        return info
    except ValueError:
        info["reason"] = "parse_error"
        return info
    info.update({
        "present": True,
        "parse_ok": True,
        "status": rep.get("status"),
        "generated_at": rep.get("generated_at"),
        "windows_loaded": rep.get("windows_loaded"),
        "valid_windows": rep.get("valid_windows"),
        "distinct_window_dates": rep.get("distinct_window_dates"),
        "current_fee_sample_gated_positive_windows": rep.get(
            "current_fee_sample_gated_positive_windows"
        ),
        "walk_forward_holdout_confirmed_windows": rep.get(
            "walk_forward_holdout_confirmed_windows"
        ),
        "repeated_positive_keys": rep.get("repeated_positive_keys"),
        "best_sample_gated_break_even_window": rep.get(
            "best_sample_gated_break_even_window"
        ),
        "lower_fee_break_even_windows": rep.get("lower_fee_break_even_windows"),
        "lower_fee_break_even_distinct_window_dates": rep.get(
            "lower_fee_break_even_distinct_window_dates"
        ),
        "repeated_lower_fee_break_even_keys": rep.get(
            "repeated_lower_fee_break_even_keys"
        ),
        "best_lower_fee_break_even_window": rep.get(
            "best_lower_fee_break_even_window"
        ),
        "lower_fee_break_even_stability": rep.get(
            "lower_fee_break_even_stability"
        ),
        "reason": rep.get("reason"),
    })
    return info

fillsim = _load_fillsim_adverse(fillsim_path, h_primary, fillsim_max_age_h)
fillsim["history_scorecard"] = _load_fillsim_history_scorecard(fillsim_history_path)
adverse_sel = fillsim["adverse_sel_bps"]
fee_path_feasibility = build_maker_fee_path_feasibility_scorecard(
    fillsim.get("maker_fee_sensitivity_scorecard"),
    fee_capacity_30d,
    current_maker_fee_bps_per_side=maker_fee,
)
sample_gated_cost_wall_summary = _sample_gated_fill_sim_cost_wall(
    fillsim,
    h_primary=h_primary,
    min_fills=min_fills,
)
gross_edge_cost_decomposition = _mm_gross_edge_cost_decomposition(
    fillsim,
    h_primary=h_primary,
    min_fills=min_fills,
)
# adverse 可用性：報告存在、非過期、有數值。否則 adverse 未知 → net 不可發正告警。
adverse_usable = (fillsim["present"] and not fillsim["stale"] and adverse_sel is not None)

# --- (3) per-symbol live MM net-edge 估計 + (a) MM-net-positive 告警 ---
# QC/PA Hybrid-C：MM_net_edge = spread_captured − adverse_selection − FEE_RT。
#   spread_captured = −mean(maker_markout_bps)（翻號；markout ≈ −half_spread → 翻號得正）。
#   adverse_selection = fill_sim fill-only adverse_sel@h（live 與 offline 是不同 fill 樣本，
#     只在同 regime 可比；single-window != verdict——告警明標 caveat）。
net_edge = {}
positive_flagged = []
for sym, mkrow in per_sym_mk.items():
    mean_mk = mkrow.get("mean_markout_bps")
    n = mkrow.get("n") or 0
    spread_captured = None if mean_mk is None else round(-float(mean_mk), 4)
    if spread_captured is None or not adverse_usable:
        net = None
        edge_before_fees = None
        break_even_fee_rt = None
        break_even_maker_fee = None
        fee_rt_shortfall = None
        required_spread_captured = None
        required_maker_rebate = None
    else:
        edge_before_fees = round(spread_captured - float(adverse_sel), 4)
        break_even_fee_rt = edge_before_fees
        break_even_maker_fee = round(break_even_fee_rt / 2.0, 4)
        fee_rt_shortfall = round(fee_rt - break_even_fee_rt, 4)
        required_spread_captured = round(float(adverse_sel) + fee_rt, 4)
        required_maker_rebate = round(max(0.0, -break_even_maker_fee), 4)
        net = round(edge_before_fees - fee_rt, 4)
    net_edge[sym] = {
        "net_edge_bps": net,
        "spread_captured_bps": spread_captured,
        "mean_markout_bps": mean_mk,
        "adverse_selection_bps": (round(float(adverse_sel), 4) if adverse_usable else None),
        "fee_bps_rt": fee_rt,
        "edge_before_fees_bps": edge_before_fees,
        "break_even_fee_round_trip_bps": break_even_fee_rt,
        "break_even_maker_fee_bps_per_side": break_even_maker_fee,
        "fee_round_trip_shortfall_bps": fee_rt_shortfall,
        "required_spread_captured_bps": required_spread_captured,
        "required_maker_rebate_bps_per_side": required_maker_rebate,
        "n_maker_fills": n,
    }
    # 告警 gate：net>0 AND n>=門檻（對齊 fill_sim MIN_FILLS_FOR_SIGNIF=30）AND adverse 可用。
    if net is not None and net > 0 and float(n) >= min_fills:
        positive_flagged.append(f"{sym}=net+{net:.2f}bp(cap={spread_captured:.2f},"
                                f"adv={float(adverse_sel):.2f},n={int(n)})")

if positive_flagged:
    # NON-NEGOTIABLE caveat（QC/PA）：single-window != go/no-go；live spread-capture 與
    # offline adverse-selection 是不同 fill 樣本（只同 regime 可比）；需跨 regime（含
    # trend-stress）才是裁決。
    caveat = ("SINGLE-WINDOW != GO/NO-GO: cross-regime (incl trend-stress) required; "
                  "live spread-capture & offline adverse-selection are DIFFERENT fill samples "
                  "(comparable only same-regime)")
    alerts.append("[MM-VERDICT] maker net-edge POSITIVE: " + "; ".join(positive_flagged)
                  + " || " + caveat)

cost_wall_rows = [
    (row["net_edge_bps"], sym, row)
    for sym, row in net_edge.items()
    if row.get("net_edge_bps") is not None
]
if cost_wall_rows:
    best_net, best_sym, best_row = max(cost_wall_rows, key=lambda item: item[0])
    cost_wall_summary = {
        "available": True,
        "horizon_s": h_primary,
        "best_symbol_by_net_edge": best_sym,
        "best_net_edge_bps": best_net,
        "best_n_maker_fills": best_row.get("n_maker_fills"),
        "best_fee_round_trip_shortfall_bps": best_row.get("fee_round_trip_shortfall_bps"),
        "best_required_maker_rebate_bps_per_side": best_row.get(
            "required_maker_rebate_bps_per_side"
        ),
        "best_required_spread_captured_bps": best_row.get("required_spread_captured_bps"),
        "note": (
            "fee_round_trip_shortfall_bps = current maker RT fee - break-even RT fee; "
            "positive means still below break-even"
        ),
    }
else:
    cost_wall_summary = {
        "available": False,
        "horizon_s": h_primary,
        "reason": "adverse_selection_unusable_or_no_markout",
    }

# --- (4)+(b) recorder-v2 L1 readiness ---
l1_days = None
l1_ready = False
if l1.get("present"):
    l1_days = l1.get("regime_days")
    if l1_days is not None and float(l1_days) >= l1_thr:
        l1_ready = True
        alerts.append(f"[MM-VERDICT] L1 fill-sim READY: regime_days={int(l1_days)}(>={int(l1_thr)})")

# --- (5)+(c) high-vol detection ---
hv_z = None
hv_flagged = False
today_rv = highvol.get("today_rv")
tmean = highvol.get("trailing_mean_rv")
tstd = highvol.get("trailing_std_rv")
tdays = highvol.get("trailing_days") or 0
# 需足夠 trailing 樣本（>=5 日）且 std 有效，否則 z-score 不可信，跳過告警。
if (today_rv is not None and tmean is not None and tstd is not None
        and float(tstd) > 0 and float(tdays) >= 5):
    hv_z = round((float(today_rv) - float(tmean)) / float(tstd), 3)
    if hv_z >= highvol_z_thr:
        hv_flagged = True
        alerts.append(f"[MM-VERDICT] HIGH-VOL day: BTC 1m rv z={hv_z:.2f}(>={highvol_z_thr:.1f}) "
                      f"-> fill-sim re-run candidate")

status = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "check": "recorder_mm_verdict",
    "model": "MM_net_edge = spread_captured(-mean_markout) - adverse_selection(fill_sim) - fee_rt",
    "thresholds": {"min_maker_fills": min_fills, "maker_fee_bps_per_side": maker_fee,
                   "fee_bps_rt": fee_rt, "adverse_horizon_s": h_primary,
                   "fillsim_max_age_h": fillsim_max_age_h,
                   "l1_regime_days": l1_thr, "highvol_z": highvol_z_thr},
    "markout_n_total": markout.get("n_total"),
    "markout_n_24h": markout.get("n_24h"),
    "markout_basis": "reference_source=mid_at_submit (half-spread basis only)",
    "fillsim": fillsim,
    "fee_capacity_30d": fee_capacity_30d,
    "fee_path_feasibility": fee_path_feasibility,
    "adverse_selection_usable": adverse_usable,
    "net_edge_per_symbol": net_edge,
    "cost_wall_summary": cost_wall_summary,
    "sample_gated_cost_wall_summary": sample_gated_cost_wall_summary,
    "gross_edge_cost_decomposition": gross_edge_cost_decomposition,
    "l1_regime_days": l1_days,
    "l1_fill_sim_ready": l1_ready,
    "highvol_z": hv_z,
    "highvol_day": hv_flagged,
    "caveat": ("single-window estimate, NOT go/no-go; live spread-capture & offline "
               "adverse-selection are different fill samples (comparable only same-regime); "
               "cross-regime incl trend-stress required for any verdict"),
}
print("STATUS=" + json.dumps(status, separators=(",", ":"), default=str))
print("ALERTS=" + json.dumps(alerts, separators=(",", ":")))
PY
)

# 解析 python3 兩行輸出（fail-soft：缺行 → 視為無 status / 無告警）。
STATUS_JSON=$(printf '%s\n' "$PY_OUT" | grep '^STATUS=' | head -n1 | cut -d= -f2-)
ALERTS_JSON=$(printf '%s\n' "$PY_OUT" | grep '^ALERTS=' | head -n1 | cut -d= -f2-)

if [[ -z "$STATUS_JSON" ]]; then
    echo "[$(ts)] === mm verdict check end FAIL (python3 verdict synthesis empty) ===" >> "$LOG"
    exit 1
fi

echo "$STATUS_JSON" >> "$STATUS_LOG"
echo "[$(ts)] status: $STATUS_JSON" >> "$LOG"

# ---------------------------------------------------------------------------
# ALERT：命中 (a) MM-net-positive / (b) L1 fill-sim ready / (c) high-vol day 時，逐條
# append alerts.jsonl（與 alert_sink.py 同 schema：ts_utc/subject/severity/body/
# channels_attempted/channels_ok）。MM 正 edge 是「應該被人看到」的好消息（info），
# L1-ready / high-vol 是 fill-sim 行動觸發（info）。用 python3 逐條 emit（避免 shell
# JSON 拼接脆弱性；只讀字串不連 DB）。
# ---------------------------------------------------------------------------
N_ALERTS=$(printf '%s' "$ALERTS_JSON" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>>"$LOG" || echo 0)
if [[ "${N_ALERTS:-0}" -gt 0 ]]; then
    ALERTS_JSON="$ALERTS_JSON" python3 - >> "$ALERT_FILE" 2>>"$LOG" <<'PY' || true
import json, os, time
subjects = json.loads(os.environ["ALERTS_JSON"])
ts_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
for subj in subjects:
    rec = {
        "ts_utc": ts_utc,
        "subject": subj,
        "severity": "info",
        "body": subj + " (read-only MM verdict monitor; no trading action taken).",
        "channels_attempted": [],
        "channels_ok": None,
    }
    print(json.dumps(rec, separators=(",", ":")))
PY
    echo "[$(ts)] ALERT appended: ${N_ALERTS} condition(s) -> $ALERTS_JSON" >> "$LOG"
fi

echo "[$(ts)] === mm verdict check end OK ===" >> "$LOG"
exit 0
