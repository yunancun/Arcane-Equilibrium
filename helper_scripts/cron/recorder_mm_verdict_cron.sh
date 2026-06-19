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
    MM_MIN_MAKER_FILLS="$MM_MIN_MAKER_FILLS" \
    MAKER_FEE_BPS_PER_SIDE="$MAKER_FEE_BPS_PER_SIDE" \
    MM_ADVERSE_HORIZON_S="$MM_ADVERSE_HORIZON_S" \
    MM_FILLSIM_MAX_AGE_H="$MM_FILLSIM_MAX_AGE_H" \
    MM_L1_REGIME_DAYS="$MM_L1_REGIME_DAYS" \
    MM_HIGHVOL_Z="$MM_HIGHVOL_Z" \
    FILLSIM_REPORT="$FILLSIM_REPORT" \
    python3 - <<'PY' 2>>"$LOG" || true
import json, os, datetime

mm = json.loads(os.environ["MM_JSON"])
min_fills = float(os.environ["MM_MIN_MAKER_FILLS"])
maker_fee = float(os.environ["MAKER_FEE_BPS_PER_SIDE"])
fee_rt = 2.0 * maker_fee  # RT fee（無 rebate，保守）= 4bp。
h_primary = int(float(os.environ["MM_ADVERSE_HORIZON_S"]))
fillsim_max_age_h = float(os.environ["MM_FILLSIM_MAX_AGE_H"])
l1_thr = float(os.environ["MM_L1_REGIME_DAYS"])
highvol_z_thr = float(os.environ["MM_HIGHVOL_Z"])
fillsim_path = os.environ["FILLSIM_REPORT"]

markout = mm.get("markout") or {}
l1 = mm.get("l1_readiness") or {}
highvol = mm.get("highvol") or {}

per_sym_mk = markout.get("per_symbol") or {}
alerts = []  # alert subject 字串

# --- fill_sim 報告：adverse_selection（beta-residual fill-conditional）---
# 決策：讀最新報告而非內跑（檔頭已記理由）。取 pooled fill_only adverse_sel@h（primary=15s，
# 另記 5/30s sensitivity）。報告缺檔/解析失敗/過期 → adverse 未知（None），net-edge 退化、
# 不發正 net 告警（fail-soft，誠實）。
def _load_fillsim_adverse(path, h_primary, max_age_h):
    info = {"source": path, "present": False, "stale": None, "age_hours": None,
            "stale_reason": None, "data_stale": None, "data_l1_rows_post_filter": None,
            "data_l1_max_ts": None, "data_l1_max_age_hours": None,
            "adverse_sel_bps": None, "adverse_sel_n": None,
            "adverse_sel_signif_suppressed": None, "sensitivity": {}}
    try:
        with open(path) as f:
            rep = json.load(f)
    except (OSError, ValueError):
        return info
    info["present"] = True
    # 年齡：用報告 generated_at（ISO8601）對比 now，無法解析則標 stale=True 保守。
    gen = rep.get("generated_at")
    try:
        gt = datetime.datetime.fromisoformat(gen)
        if gt.tzinfo is None:
            gt = gt.replace(tzinfo=datetime.timezone.utc)
        age_h = (datetime.datetime.now(datetime.timezone.utc) - gt).total_seconds() / 3600.0
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
        data_age = data.get("l1_max_age_hours")
        if data_age is not None and float(data_age) > max_age_h:
            info["data_stale"] = True
            info["stale"] = True
            info["stale_reason"] = "stale_l1_data"
    except (TypeError, ValueError):
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
    # 5/30s sensitivity（誠實透明，不入 net 計算）。
    for hs in (5, 30):
        v = fo.get(f"adverse_sel_bps@{hs}")
        if v is not None:
            info["sensitivity"][f"adverse_sel_bps@{hs}"] = v
    return info

fillsim = _load_fillsim_adverse(fillsim_path, h_primary, fillsim_max_age_h)
adverse_sel = fillsim["adverse_sel_bps"]
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
    else:
        net = round(spread_captured - float(adverse_sel) - fee_rt, 4)
    net_edge[sym] = {
        "net_edge_bps": net,
        "spread_captured_bps": spread_captured,
        "mean_markout_bps": mean_mk,
        "adverse_selection_bps": (round(float(adverse_sel), 4) if adverse_usable else None),
        "fee_bps_rt": fee_rt,
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
    "adverse_selection_usable": adverse_usable,
    "net_edge_per_symbol": net_edge,
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
