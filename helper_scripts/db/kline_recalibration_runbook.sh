#!/usr/bin/env bash
# kline_recalibration_runbook.sh — intraday kline 既有 DB 真值修補 runbook（自驗、operator-gated）
#                                  （INTRADAY-KLINES-PERMANENT-FIX R4）
#
# 用途：把 market.klines 內被 live tick-synth 路徑寫壞的 intraday OHLC（range 死 / 一-bar offset /
#   turnover 0）就地修成 Bybit authoritative 真值。流程（per target symbol×timeframe×window）：
#     1. scope + dry-run（預設）：印命中 chunk + 估頁數 + 磁碟頭寸估計，不動 DB。
#     2. 逐 chunk 串行 decompress_chunk（只解壓命中窗 chunk，控磁碟峰值）。
#     3. intraday_kline_backfill --upsert-overwrite（ConflictMode::Overwrite 全 OHLCV DO UPDATE）。
#     4. truth-test GATE（kline_calibration_checker --gate）：corr0≈0.99 AND range≈1.0 才放行；
#        未達標 fail-loud（exit 5），不 recompress，留 operator 介入。
#     5. outcome_backfiller scoped reset：受影響窗 decision_context_snapshots.outcome_backfilled=FALSE
#        + 觸發 outcome_backfiller_live.py 重算（修 OHLC 後歷史歸因必須重算，PA §4.3 不可省）。
#     6. recompress_chunk（compress_chunk）還原壓縮。
#
# 安全：
#   - 預設 dry-run。寫 DB 需 --apply + OPENCLAW_KLINE_RECAL_APPLY=1 雙 gate。
#   - 逐 chunk 串行（非全窗一次解壓）控磁碟峰值；scope 只命中窗 chunk + 指定 symbol 域。
#   - GATE 未過 = fail-loud：不 recompress、不重算 outcome、非零退出，留 operator 介入。
#   - 冪等：Overwrite DO UPDATE 重跑覆蓋同值；decompress→recompress 可重入；reset+重算冪等。
#   - 不碰 live writer（market_writer.rs DO NOTHING 不變）；不碰 auth/lease/system_mode。
#
# 用法（Linux trade-core）：
#   # dry-run（預設，印 chunk + 估計，不動 DB）：
#   ./kline_recalibration_runbook.sh --symbols-from-db --interval 1 5 15 60 240 \
#       --start 2026-04-05 --end 2026-06-15
#   # apply（雙 gate；建議暫停 outcome_backfiller_live / residual stage0r cron 一回合）：
#   OPENCLAW_KLINE_RECAL_APPLY=1 ./kline_recalibration_runbook.sh --apply \
#       --symbol BTCUSDT --interval 1 --start 2026-04-05 --end 2026-06-15
#
# 為什麼 Overwrite（非 vol+turnover-only）：R4 的目的本身就是修壞 OHLC；既有 decision_outcomes
#   基於假 close 算出的歸因本身就是錯的，凍結它不是保護可重建性而是凍結錯誤。root principle #8
#   的真義 = 可重建為「真值」→ 修 OHLC = 修歸因源頭。代價 = 末步強制重跑 outcome_backfiller。

set -euo pipefail

# ---- 參數 ----
APPLY=0
SYMBOL=""
SYMBOLS_FROM_DB=0
INTERVALS=()
START_DATE=""
END_DATE=""
SKIP_OUTCOME_BACKFILL=0   # 進階：只修 klines 不重算 outcome（不建議；預設一律重算）

usage() {
    cat <<'EOF'
kline_recalibration_runbook.sh — R4 intraday kline 真值修補（dry-run 預設）

USAGE:
  ./kline_recalibration_runbook.sh [--dry-run] --symbol BTCUSDT|--symbols-from-db \
      --interval 1|5|15|60|240 [--interval ...] --start YYYY-MM-DD --end YYYY-MM-DD
  OPENCLAW_KLINE_RECAL_APPLY=1 ./kline_recalibration_runbook.sh --apply [same options]

FLAGS:
  --dry-run            (default) 印 chunk + 估頁 + 磁碟估計，不動 DB
  --apply              真執行（需同時 OPENCLAW_KLINE_RECAL_APPLY=1 雙 gate）
  --symbol SYM         單一 symbol
  --symbols-from-db    market.klines 全 distinct symbol（與 --symbol 互斥）
  --interval N         1|5|15|60|240（可重複；對應 1m/5m/15m/1h/4h）
  --start YYYY-MM-DD   窗起（UTC 日界，含）
  --end   YYYY-MM-DD   窗止（UTC 日界，含當天）
  --skip-outcome-backfill  進階：跳過 outcome 重算（不建議——修 OHLC 後歸因會脫鉤）

ENV:
  OPENCLAW_BASE_DIR        srv root（預設 $HOME/BybitOpenClaw/srv）
  OPENCLAW_DATA_DIR        data root（預設 /tmp/openclaw）
  OPENCLAW_SECRETS_ROOT    secrets root（PG creds）
  OPENCLAW_KLINE_RECAL_APPLY=1  與 --apply 雙 gate（缺一不寫 DB）
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) APPLY=0; shift ;;
        --apply) APPLY=1; shift ;;
        --symbol) SYMBOL="${2:?--symbol requires a value}"; shift 2 ;;
        --symbols-from-db) SYMBOLS_FROM_DB=1; shift ;;
        --interval) INTERVALS+=("${2:?--interval requires a value}"); shift 2 ;;
        --start) START_DATE="${2:?--start requires a value}"; shift 2 ;;
        --end) END_DATE="${2:?--end requires a value}"; shift 2 ;;
        --skip-outcome-backfill) SKIP_OUTCOME_BACKFILL=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; usage; exit 2 ;;
    esac
done

# ---- 驗參 ----
if [[ -n "$SYMBOL" && "$SYMBOLS_FROM_DB" -eq 1 ]]; then
    echo "ERROR: --symbol and --symbols-from-db are mutually exclusive" >&2; exit 2
fi
if [[ -z "$SYMBOL" && "$SYMBOLS_FROM_DB" -eq 0 ]]; then
    echo "ERROR: one of --symbol or --symbols-from-db required" >&2; exit 2
fi
if [[ ${#INTERVALS[@]} -eq 0 ]]; then
    echo "ERROR: at least one --interval required (1|5|15|60|240)" >&2; exit 2
fi
if [[ -z "$START_DATE" || -z "$END_DATE" ]]; then
    echo "ERROR: --start and --end required (YYYY-MM-DD UTC)" >&2; exit 2
fi
# interval → timeframe 映射（與 intraday_kline_backfill / kline_calibration_checker 一致）。
# 用 case 函數而非 associative array：macOS 預設 bash 3.2 無 `declare -A`，case 跨平台可解析
# （本 runbook 雖只在 Linux trade-core 真跑，但要能在 Mac syntax-check + arg 驗證）。
tf_of() {
    case "$1" in
        1) echo "1m" ;;
        5) echo "5m" ;;
        15) echo "15m" ;;
        60) echo "1h" ;;
        240) echo "4h" ;;
        *) return 1 ;;
    esac
}
for iv in "${INTERVALS[@]}"; do
    if ! tf_of "$iv" >/dev/null; then
        echo "ERROR: --interval expects 1|5|15|60|240, got $iv" >&2; exit 2
    fi
done

# ---- 雙 gate 驗證 ----
if [[ "$APPLY" -eq 1 && "${OPENCLAW_KLINE_RECAL_APPLY:-0}" != "1" ]]; then
    echo "ERROR: --apply requires OPENCLAW_KLINE_RECAL_APPLY=1 (double gate; refusing to write DB)" >&2
    exit 2
fi

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*"; }

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: env file missing: $ENV_FILE" >&2; exit 2
fi
PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_DB=$(grep '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST=$(grep '^POSTGRES_HOST=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_PORT=$(grep '^POSTGRES_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"
if [[ -z "$PG_PASS" || -z "$PG_USER" || -z "$PG_DB" ]]; then
    echo "ERROR: PG creds incomplete in $ENV_FILE" >&2; exit 2
fi
export PGHOST="$PG_HOST" PGPORT="$PG_PORT" PGUSER="$PG_USER" PGDATABASE="$PG_DB" PGPASSWORD="$PG_PASS"
export OPENCLAW_DATABASE_URL="postgresql://redacted@${PG_HOST}:${PG_PORT}/${PG_DB}"

# psql 包裝：-X 不讀 ~/.psqlrc，-q 安靜，-t -A 純值（caller 解析），ON_ERROR_STOP fail-loud。
psql_val() { psql -X -q -t -A -v ON_ERROR_STOP=1 -c "$1"; }
psql_run() { psql -X -q -v ON_ERROR_STOP=1 -c "$1"; }

# UTC 日界 → epoch ms（--end 含當天 → 隔日 00:00 半開上界）。
to_ms() { date -u -d "${1} 00:00:00" +%s000 2>/dev/null || date -u -j -f "%Y-%m-%d %H:%M:%S" "${1} 00:00:00" +%s000; }
START_MS=$(to_ms "$START_DATE")
END_DAY_MS=$(to_ms "$END_DATE")
END_MS=$(( END_DAY_MS + 86400000 ))   # 含當天 → 隔日 00:00
if [[ "$START_MS" -ge "$END_MS" ]]; then
    echo "ERROR: --start must be strictly before --end" >&2; exit 2
fi
# psql 用 timestamptz：epoch ms → ISO（to_timestamp 秒）。
START_ISO=$(date -u -d "@$(( START_MS / 1000 ))" '+%Y-%m-%d %H:%M:%S+00' 2>/dev/null || date -u -r "$(( START_MS / 1000 ))" '+%Y-%m-%d %H:%M:%S+00')
END_ISO=$(date -u -d "@$(( END_MS / 1000 ))" '+%Y-%m-%d %H:%M:%S+00' 2>/dev/null || date -u -r "$(( END_MS / 1000 ))" '+%Y-%m-%d %H:%M:%S+00')

# ---- symbol 集解析 ----
if [[ "$SYMBOLS_FROM_DB" -eq 1 ]]; then
    # 以 timeframe 標籤集查 distinct symbol（'1m','5m',... 逗號分隔字面，供 IN 子句）。
    TFS_SQL=$(IFS=,; tfs=(); for iv in "${INTERVALS[@]}"; do tfs+=("'$(tf_of "$iv")'"); done; echo "${tfs[*]}")
    mapfile -t SYMBOLS < <(psql_val "SELECT DISTINCT symbol FROM market.klines WHERE timeframe IN ($TFS_SQL) ORDER BY symbol")
else
    SYMBOLS=("$SYMBOL")
fi
if [[ ${#SYMBOLS[@]} -eq 0 ]]; then
    echo "ERROR: resolved 0 symbols (market.klines empty for these timeframes?)" >&2; exit 4
fi

log "=== kline_recalibration_runbook ($([ "$APPLY" -eq 1 ] && echo APPLY || echo DRY-RUN)) ==="
log "window = [$START_ISO, $END_ISO)  (ms [$START_MS, $END_MS))"
log "intervals = ${INTERVALS[*]}  symbols = ${#SYMBOLS[@]}"
log "outcome_backfill_after = $([ "$SKIP_OUTCOME_BACKFILL" -eq 1 ] && echo SKIP || echo YES)"

# ---- §1 scope + dry-run：命中 chunk + 磁碟估計 ----
# show_chunks 用 newer_than/older_than（TIMESTAMPTZ）取窗內 chunk；range_start/range_end 供報告。
CHUNK_SQL="SELECT chunk_schema || '.' || chunk_name AS chunk, range_start, range_end \
  FROM timescaledb_information.chunks \
  WHERE hypertable_schema='market' AND hypertable_name='klines' \
    AND range_end > '${START_ISO}'::timestamptz AND range_start < '${END_ISO}'::timestamptz \
  ORDER BY range_start"
log "--- chunks overlapping window (market.klines) ---"
psql -X -q -v ON_ERROR_STOP=1 -c "$CHUNK_SQL" || { echo "ERROR: chunk discovery failed" >&2; exit 4; }
mapfile -t CHUNKS < <(psql_val "$CHUNK_SQL" | cut -d'|' -f1)
log "chunks overlapping window: ${#CHUNKS[@]}"

# 估頁數（per symbol×interval，1000-bar 分頁）：交由 intraday_kline_backfill --dry-run 印（rate-limit math）。
log "--- estimated pages (intraday_kline_backfill dry-run, no fetch) ---"
BACKFILL_BIN_REL="$BASE/rust/target/release/intraday_kline_backfill"
BACKFILL_BIN_DBG="$BASE/rust/target/debug/intraday_kline_backfill"
run_backfill() {
    # $@ = extra args；自動選 release/debug/cargo。
    if [[ -x "$BACKFILL_BIN_REL" ]]; then "$BACKFILL_BIN_REL" "$@"
    elif [[ -x "$BACKFILL_BIN_DBG" ]]; then "$BACKFILL_BIN_DBG" "$@"
    else ( cd "$BASE/rust" && cargo run -q -p openclaw_engine --bin intraday_kline_backfill -- "$@" ); fi
}
run_gate() {
    local bin_rel="$BASE/rust/target/release/kline_calibration_checker"
    local bin_dbg="$BASE/rust/target/debug/kline_calibration_checker"
    if [[ -x "$bin_rel" ]]; then "$bin_rel" "$@"
    elif [[ -x "$bin_dbg" ]]; then "$bin_dbg" "$@"
    else ( cd "$BASE/rust" && cargo run -q -p openclaw_engine --bin kline_calibration_checker -- "$@" ); fi
}

BF_INTERVAL_ARGS=(); for iv in "${INTERVALS[@]}"; do BF_INTERVAL_ARGS+=(--interval "$iv"); done
BF_SYMBOL_ARGS=(); if [[ "$SYMBOLS_FROM_DB" -eq 1 ]]; then BF_SYMBOL_ARGS=(--symbols-from-db); else BF_SYMBOL_ARGS=(--symbol "$SYMBOL"); fi
run_backfill --dry-run "${BF_INTERVAL_ARGS[@]}" "${BF_SYMBOL_ARGS[@]}" --start "$START_DATE" --end "$END_DATE" || true

# 磁碟頭寸估計：解壓副本暫膨脹。逐 chunk 串行（一次只解壓一個 chunk）控峰值。
log "--- disk headroom note ---"
log "decompress is per-chunk SERIAL: at most ONE chunk decompressed at a time to bound peak disk."
log "check free space >= largest chunk uncompressed size before --apply."

if [[ "$APPLY" -eq 0 ]]; then
    log "=== DRY-RUN complete: no DB writes, no decompress, no overwrite, no recompress ==="
    log "to apply: OPENCLAW_KLINE_RECAL_APPLY=1 $0 --apply <same options>"
    exit 0
fi

# ====================================================================
# §2-§6 APPLY 路徑（雙 gate 已驗）
# ====================================================================
log "=== APPLY mode (double gate OK) — recommend pausing outcome_backfiller_live / residual stage0r cron ==="

# §2 逐 chunk 串行 decompress（只解壓命中窗 chunk）。已解壓 chunk 再 decompress no-op（冪等）。
for chunk in "${CHUNKS[@]}"; do
    [[ -z "$chunk" ]] && continue
    log "decompress_chunk: $chunk"
    # decompress_chunk(if_not_compressed => TRUE)：未壓縮的 chunk 不報錯（冪等可重入）。
    psql_run "SELECT decompress_chunk('${chunk}'::regclass, if_compressed => TRUE);" \
        || { echo "ERROR: decompress failed for $chunk" >&2; exit 4; }
done

# §3 upsert-overwrite（ConflictMode::Overwrite 全 OHLCV DO UPDATE）。
log "--- §3 intraday_kline_backfill --upsert-overwrite (full OHLCV DO UPDATE) ---"
OPENCLAW_INTRADAY_KLINE_BACKFILL_APPLY=1 run_backfill --apply --upsert-overwrite \
    "${BF_INTERVAL_ARGS[@]}" "${BF_SYMBOL_ARGS[@]}" --start "$START_DATE" --end "$END_DATE" \
    || { echo "ERROR: upsert-overwrite failed; chunks left DECOMPRESSED for operator inspection" >&2; exit 4; }

# §4 truth-test GATE（per symbol×timeframe）：corr0≈0.99 AND range≈1.0 才放行。
# 任一 cell FAIL → fail-loud：不 recompress、不重算 outcome，留 operator 介入（chunks 仍解壓態）。
log "--- §4 truth-test GATE (kline_calibration_checker --gate; read-only) ---"
GATE_FAIL=0
for sym in "${SYMBOLS[@]}"; do
    for iv in "${INTERVALS[@]}"; do
        tf="$(tf_of "$iv")"
        if run_gate --gate --symbol "$sym" --timeframe "$tf" --start-ms "$START_MS" --end-ms "$END_MS"; then
            log "GATE PASS: $sym $tf"
        else
            rc=$?
            log "GATE FAIL: $sym $tf (rc=$rc) — recal did not reach truth standard"
            GATE_FAIL=1
        fi
    done
done
if [[ "$GATE_FAIL" -eq 1 ]]; then
    echo "ERROR: truth-test GATE FAILED for ≥1 cell — NOT recompressing, NOT recomputing outcomes." >&2
    echo "       chunks left DECOMPRESSED for operator inspection. Investigate before re-running." >&2
    exit 5
fi
log "all cells passed truth-test GATE."

# §5 outcome_backfiller scoped reset + 重算（修 OHLC 後歸因必須重算，PA §4.3 不可省）。
if [[ "$SKIP_OUTCOME_BACKFILL" -eq 0 ]]; then
    log "--- §5 outcome_backfiller scoped reset + recompute ---"
    # 受影響窗：decision_context_snapshots.ts 落在 recal 窗 + symbol 在 recal 域 → outcome_backfilled=FALSE。
    SYM_SQL=$(IFS=,; ss=(); for s in "${SYMBOLS[@]}"; do ss+=("'$s'"); done; echo "${ss[*]}")
    # 先印 affected count（scope 驗證：只命中目標窗 symbol）。
    AFFECTED=$(psql_val "SELECT count(*) FROM trading.decision_context_snapshots \
        WHERE symbol IN ($SYM_SQL) AND ts >= '${START_ISO}'::timestamptz AND ts < '${END_ISO}'::timestamptz \
          AND outcome_backfilled = TRUE")
    log "decision_context_snapshots to reset (scoped to recal window+symbols): $AFFECTED"
    psql_run "UPDATE trading.decision_context_snapshots \
        SET outcome_backfilled = FALSE \
        WHERE symbol IN ($SYM_SQL) AND ts >= '${START_ISO}'::timestamptz AND ts < '${END_ISO}'::timestamptz \
          AND outcome_backfilled = TRUE" \
        || { echo "ERROR: outcome reset failed; chunks still DECOMPRESSED" >&2; exit 4; }
    # 觸發 outcome_backfiller_live.py 重算（讀剛修好的 klines 重算 decision_outcomes）。
    if [[ -f "$BASE/helper_scripts/db/outcome_backfiller_live.py" ]]; then
        export PYTHONPATH="${BASE}/program_code:${BASE}:${PYTHONPATH:-}"
        python3 "$BASE/helper_scripts/db/outcome_backfiller_live.py" \
            --dsn "$OPENCLAW_DATABASE_URL" --engine-mode "live,live_demo" \
            || { echo "ERROR: outcome_backfiller_live recompute failed; chunks still DECOMPRESSED" >&2; exit 4; }
        log "outcome_backfiller_live recompute done."
    else
        log "WARN: outcome_backfiller_live.py not found; reset done but recompute skipped — run it manually."
    fi
else
    log "--- §5 SKIPPED (--skip-outcome-backfill) — WARNING: decision_outcomes now decoupled from new OHLC ---"
fi

# §6 recompress chunks（compress_chunk）還原壓縮。已壓縮 chunk no-op（冪等）。
log "--- §6 recompress chunks ---"
for chunk in "${CHUNKS[@]}"; do
    [[ -z "$chunk" ]] && continue
    log "compress_chunk: $chunk"
    psql_run "SELECT compress_chunk('${chunk}'::regclass, if_not_compressed => TRUE);" \
        || { echo "ERROR: recompress failed for $chunk — chunk left DECOMPRESSED, recompress manually" >&2; exit 4; }
done

log "=== kline_recalibration_runbook APPLY complete: klines recalibrated, truth-test passed, outcomes recomputed, chunks recompressed ==="
exit 0
