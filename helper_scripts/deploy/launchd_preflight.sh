#!/usr/bin/env bash
# launchd_preflight.sh — validate macOS launchd deployment prerequisites
# launchd_preflight.sh — 驗證 macOS launchd 部署前置條件
#
# Batch E / OS-005:
#   - Fail closed when plist placeholders are not replaced
#   - Fail closed when required secret files are missing/placeholder
#   - Enforce "preflight before load" operator workflow
#
# Usage:
#   export OPENCLAW_BASE_DIR=/abs/path/to/srv
#   export OPENCLAW_SECRETS_ROOT=/abs/path/to/secrets
#   bash helper_scripts/deploy/launchd_preflight.sh

set -euo pipefail

OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:?OPENCLAW_BASE_DIR not set}"
OPENCLAW_SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:?OPENCLAW_SECRETS_ROOT not set}"
LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"

PLISTS=(
  "com.openclaw.engine.plist"
  "com.openclaw.engine-watchdog.plist"
  "com.openclaw.trading-api.plist"
  "com.openclaw.gateway.plist"
)

DB_URL_FILE="$OPENCLAW_SECRETS_ROOT/environment_files/openclaw_database_url"
IPC_SECRET_FILE="$OPENCLAW_SECRETS_ROOT/environment_files/ipc_secret.txt"

fail() {
  echo "[preflight][FAIL] $*" >&2
  exit 2
}

warn() {
  echo "[preflight][WARN] $*" >&2
}

info() {
  echo "[preflight][OK] $*"
}

contains_placeholder() {
  local file="$1"
  rg -n "__BASE__|__HOME__|change-me|YOUR_PASSWORD|PLACEHOLDER" "$file" >/dev/null 2>&1
}

[[ -d "$LAUNCH_AGENTS_DIR" ]] || fail "launch agents dir missing: $LAUNCH_AGENTS_DIR"

for p in "${PLISTS[@]}"; do
  full="$LAUNCH_AGENTS_DIR/$p"
  [[ -f "$full" ]] || fail "missing plist: $full"
  plutil -lint "$full" >/dev/null || fail "invalid plist syntax: $full"
  if rg -n "__BASE__|__HOME__" "$full" >/dev/null 2>&1; then
    fail "unreplaced placeholder found in $full"
  fi
done
info "plist files exist, parse, and have no __BASE__/__HOME__ placeholders"

[[ -f "$DB_URL_FILE" ]] || fail "missing DB URL file: $DB_URL_FILE"
[[ -s "$DB_URL_FILE" ]] || fail "empty DB URL file: $DB_URL_FILE"
if ! grep -Eq '^postgres(ql)?://[^[:space:]]+$' "$DB_URL_FILE"; then
  fail "DB URL file is not a valid postgresql:// URL: $DB_URL_FILE"
fi
if contains_placeholder "$DB_URL_FILE"; then
  fail "DB URL file contains placeholder-like value: $DB_URL_FILE"
fi
info "database URL file exists and looks valid"

[[ -f "$IPC_SECRET_FILE" ]] || fail "missing IPC secret file: $IPC_SECRET_FILE"
[[ -s "$IPC_SECRET_FILE" ]] || fail "empty IPC secret file: $IPC_SECRET_FILE"
if contains_placeholder "$IPC_SECRET_FILE"; then
  fail "IPC secret file contains placeholder-like value: $IPC_SECRET_FILE"
fi
info "IPC secret file exists and is non-placeholder"

if [[ ! -d "$OPENCLAW_BASE_DIR/program_code/exchange_connectors/bybit_connector/control_api_v1" ]]; then
  fail "OPENCLAW_BASE_DIR does not look like srv root: $OPENCLAW_BASE_DIR"
fi
if [[ ! -x "$OPENCLAW_BASE_DIR/rust/target/release/openclaw-engine" ]]; then
  warn "engine binary not executable yet: $OPENCLAW_BASE_DIR/rust/target/release/openclaw-engine"
  warn "run helper_scripts/restart_all.sh --rebuild before loading engine plist"
else
  info "engine binary exists and is executable"
fi

info "launchd preflight passed"
