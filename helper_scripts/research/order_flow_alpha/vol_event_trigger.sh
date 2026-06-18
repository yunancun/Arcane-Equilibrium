#!/usr/bin/env bash
# vol_event_trigger.sh — cron 薄包裝（$0 唯讀）。
#
# 用途：為 cron 注入 PG 憑證（OPENCLAW_DATABASE_URL）+ 切到 srv root，再呼 Python
#   增量累積器 vol_event_trigger.py。本包裝零業務邏輯（parse→export→exec）。
#
# 硬邊界：純讀 PG（Python 側 connect set_session readonly）；不下單、不碰 engine/risk。
#   路徑全走 env / $HOME（禁硬編 user path；跨平台）。
#
# env（cron 行 env-prefix 提供，與既有 OpenClaw cron 慣例一致）：
#   OPENCLAW_BASE_DIR   srv root（預設 $HOME/BybitOpenClaw/srv）
#   OPENCLAW_DATA_DIR   artifact root（預設 /tmp/openclaw）
#   OPENCLAW_DATABASE_URL  若未設，從 $OPENCLAW_DATA_DIR/runtime_secrets/openclaw_database_url 讀
set -euo pipefail

BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
export OPENCLAW_DATA_DIR="$DATA_DIR"

# PG 憑證：優先用既設 env，否則讀 runtime_secrets 檔（與 sibling cron 慣例一致）。
if [[ -z "${OPENCLAW_DATABASE_URL:-}" ]]; then
  SECRET_FILE="$DATA_DIR/runtime_secrets/openclaw_database_url"
  if [[ -r "$SECRET_FILE" ]]; then
    OPENCLAW_DATABASE_URL="$(cat "$SECRET_FILE")"
    export OPENCLAW_DATABASE_URL
  fi
fi

cd "$BASE_DIR/helper_scripts/research/order_flow_alpha"
exec python3 vol_event_trigger.py "$@"
