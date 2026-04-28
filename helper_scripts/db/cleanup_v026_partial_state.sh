#!/usr/bin/env bash
# MODULE_NOTE
#   purpose : Clean up partial state left by V026 1st-apply ERROR (TimescaleDB
#             retention_policy syntax bug, fixed in commit on 2026-04-28).
#             Use ONLY when Linux PG has aborted V026 hypertable artifact
#             and re-applying V026 still RAISEs because the table exists
#             but the retention policy was never registered.
#   用途   : 清理 V026 1st-apply 失敗留下的 partial state（TimescaleDB
#             retention_policy 語法 bug，已於 2026-04-28 commit 修復）。
#             僅當 Linux PG 殘留 abort 的 V026 hypertable artifact、且 V026
#             重 apply 仍 RAISE 時使用。
#   safe   : DROP CASCADE 將清空 learning.cost_edge_advisor_log 已寫入的
#             observation rows — Phase A advisory-only 期間 0 production
#             impact。Phase B Wave 1 deploy 前必跑一次。
#
#   usage  : bash helper_scripts/db/cleanup_v026_partial_state.sh
#   prereq : PG_DSN env var or default linux trade-core local socket.

set -euo pipefail

DSN="${PG_DSN:-postgresql:///openclaw}"

echo "=== V026 partial state cleanup ==="
psql "$DSN" -v ON_ERROR_STOP=1 <<'SQL'
DROP TABLE IF EXISTS learning.cost_edge_advisor_log CASCADE;
DROP FUNCTION IF EXISTS learning.cost_edge_advisor_log_now_ms() CASCADE;
SQL

echo "=== cleanup OK — re-run V026 via linux_bootstrap_db.sh --apply ==="
