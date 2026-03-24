#!/usr/bin/env bash
set -u
TARGET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/readonly_observer_pipeline/bybit_readonly_loop_writer.sh"
exec bash "$TARGET" "$@"
