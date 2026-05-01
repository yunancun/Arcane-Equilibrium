#!/usr/bin/env bash
# G4-03 Phase B canary promote cron wrapper.
# G4-03 Phase B canary 晉升 cron wrapper。
#
# Default mode is dry-run and read-only. Apply mode requires BOTH:
#   OPENCLAW_CANARY_CRON_APPLY=1
#   OPENCLAW_AUTO_PROMOTE_ENABLED=1
#
# Optional SIGHUP after applied promoting→production:
#   OPENCLAW_CANARY_EMIT_SIGHUP=1
#   OPENCLAW_ENGINE_PID_FILE=/path/to/engine.pid

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRV_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$SRV_ROOT"

args=()
if [[ "${OPENCLAW_CANARY_CRON_APPLY:-0}" == "1" ]]; then
  args+=(--apply)
else
  args+=(--dry-run)
fi

if [[ "${OPENCLAW_CANARY_EMIT_SIGHUP:-0}" == "1" ]]; then
  args+=(--emit-sighup)
  if [[ -n "${OPENCLAW_ENGINE_PID_FILE:-}" ]]; then
    args+=(--sighup-pid-file "$OPENCLAW_ENGINE_PID_FILE")
  fi
fi

exec python3 helper_scripts/db/canary_promote_runner.py "${args[@]}"
