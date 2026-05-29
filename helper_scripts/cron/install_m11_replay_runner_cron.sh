#!/usr/bin/env bash
# install_m11_replay_runner_cron.sh — M11 Stage A daily replay_runner cron installer
#
# Spec 來源:
#   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--m11_replay_runner_schedule_proposal.md
#     §4.4 install script 範本 + §4.3 cron entry + §5 [48] healthcheck flip
#   docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md
#     Decision 1 + 5 (daily continuous hygiene)
#   operator confirm 2026-05-28 cadence = Daily 04:00 UTC (= M11.a)
#
# 本 script 不自動 install；operator dry-run + sign-off 後加
# OPENCLAW_M11_REPLAY_CRON_APPLY=1 才寫 crontab。
#
# 安裝內容（單一 crontab entry）:
#   - daily 04:00 UTC（per PA proposal §4.3 避撞 03:00 pg_dump / 03:17
#     ml_training_maintenance / 04:41 feature_baseline_writer / 06:00
#     counterfactual_daily / 09:00 replay_key_rotation_check）
#   - 跑 m11_replay_runner_daily_cron.sh：register-only — register
#     synthetic_btcusdt fixture 寫 replay.experiments row 一條/天（單一 fixture
#     heartbeat）。不 dispatch run（避免 run_state zombie 觸 [50]；per
#     P2-M11-SMOKE-ZOMBIE-DESIGN-FIX 2026-05-29）
#   - log + JSONL audit 進 $OPENCLAW_DATA_DIR/logs/
#   - heartbeat sentinel + lock + governance_audit_log INSERT
#
# 跨平台守門：Linux runtime only；Mac dev refuse exit 2。
#
# 硬邊界:
#   - 不寫 secrets；不改 PG schema；不改 trading_ai DB content
#   - idempotent guard：crontab 已有 m11_replay_runner 條目即 refuse install
#   - 路徑不硬編碼（per memory feedback_cross_platform）
#   - env value 防 cron-conflict char + length > 200 reject

set -euo pipefail

# ─── 平台守門：僅 Linux 跑 ───────────────────────────────────────
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_m11_replay_runner_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本 install script 必在 Linux runtime host (trade-core) 跑；Mac dev 走 ssh trade-core。" >&2
    exit 2
fi

# ─── env / 預設值 ─────────────────────────────────────────────────
OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
# Fixed 04:00 UTC（per PA proposal §4.3 避撞分析）。不開放 env 改避免 operator
# 誤撞 03:00 pg_dump / 03:17 ml_training。
M11_REPLAY_HOUR_UTC=4
M11_REPLAY_MINUTE_UTC=0

# ─── pre-flight ──────────────────────────────────────────────────
if [[ ! -f "$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env" ]]; then
    echo "ERROR: secrets env file missing: $OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env" >&2
    exit 4
fi
# API token 必存（cron wrapper 走 Bearer auth）
API_TOKEN_PATH="$OPENCLAW_BASE_DIR/program_code/exchange_connectors/bybit_connector/control_api_v1/.secrets/api_token"
if [[ ! -f "$API_TOKEN_PATH" ]]; then
    echo "ERROR: API token file missing: $API_TOKEN_PATH" >&2
    echo "       restart_all.sh 部署過後此檔應存在；確認 API server 已啟動。" >&2
    exit 4
fi
# Fixture 必存（cron wrapper 走 in-tree synthetic）
FIXTURE_PATH="$OPENCLAW_BASE_DIR/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json"
if [[ ! -f "$FIXTURE_PATH" ]]; then
    echo "ERROR: M11 synthetic fixture missing: $FIXTURE_PATH" >&2
    exit 4
fi
# replay_runner binary release path 必存（[47] replay_runner_binary healthcheck
# 對齊 + Stage B cohort nightly 需要；register-only heartbeat 本身不 spawn
# 子進程，但保留此 preflight 守 [47] 一致性 + Stage A→B 升級就緒）
RUNNER_BIN="$OPENCLAW_BASE_DIR/rust/target/release/replay_runner"
if [[ ! -x "$RUNNER_BIN" ]]; then
    echo "WARN: replay_runner release binary not executable: $RUNNER_BIN" >&2
    echo "      cargo build --release -p openclaw_engine --bin replay_runner 後再 install。" >&2
    echo "      [47] replay_runner_binary healthcheck 對應；當前 FAIL 不可繼續 install。" >&2
    exit 5
fi
mkdir -p "$OPENCLAW_DATA_DIR/logs"

# ─── idempotent guard：crontab 已有 m11_replay_runner 條目即 refuse install ──
if crontab -l 2>/dev/null | grep -qE 'm11_replay_runner'; then
    echo "SKIP: existing m11_replay_runner cron entry detected; not installing (manually remove first)." >&2
    crontab -l | grep -E 'm11_replay_runner' >&2
    exit 0
fi

# ─── 組 crontab entry ────────────────────────────────────────────
WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/m11_replay_runner_daily_cron.sh"
if [[ ! -x "$WRAPPER" ]]; then
    echo "ERROR: wrapper not executable: $WRAPPER" >&2
    echo "       chmod +x \"$WRAPPER\" 後再跑 install。" >&2
    exit 5
fi

# ─── env value validation（對齊 install_pg_dump_cron.sh:75-94 MED-3）──
# cron 對 `%` 解為 stdin 換行（除非 escape `\%`）；space 拆 token 破解析；
# control char / newline 直接 corrupt crontab；長度 > 200 通常是 ENV 污染。
# 任一不合即 abort 強制 operator 顯式覆寫（避免 silent corruption）。
_validate_cron_env_value() {
    local name="$1"
    local value="$2"
    if [[ -z "$value" ]]; then
        echo "ERROR: cron env value empty: ${name}" >&2
        exit 6
    fi
    if [[ ${#value} -gt 200 ]]; then
        echo "ERROR: cron env value too long (>200 chars): ${name}=${value}" >&2
        echo "       crontab line size limit risk；請縮短 path 或 abort。" >&2
        exit 6
    fi
    # cron 特殊字 / shell 特殊字 / 空格 / 控制字
    if [[ "$value" =~ [[:space:]%[:cntrl:]\"\'\\\$\`] ]]; then
        echo "ERROR: cron-conflict character in ${name}=${value}" >&2
        echo "       Disallowed: space / % (cron stdin newline) / control / quote / backslash / \$ / backtick" >&2
        echo "       請用 ASCII path 無 special char；或 abort 並用 systemd timer 替代 cron。" >&2
        exit 6
    fi
}

_validate_cron_env_value "OPENCLAW_BASE_DIR" "$OPENCLAW_BASE_DIR"
_validate_cron_env_value "OPENCLAW_DATA_DIR" "$OPENCLAW_DATA_DIR"
_validate_cron_env_value "OPENCLAW_SECRETS_ROOT" "$OPENCLAW_SECRETS_ROOT"
_validate_cron_env_value "WRAPPER" "$WRAPPER"

# 不用 printf %q quoting：cron 不跑 full shell parser；上面 validation reject
# special char 已保證 plain interpolation 安全（對齊 install_pg_dump_cron.sh:104-106
# 註解）。
ENTRY="${M11_REPLAY_MINUTE_UTC} ${M11_REPLAY_HOUR_UTC} * * * OPENCLAW_BASE_DIR=${OPENCLAW_BASE_DIR} OPENCLAW_DATA_DIR=${OPENCLAW_DATA_DIR} OPENCLAW_SECRETS_ROOT=${OPENCLAW_SECRETS_ROOT} ${WRAPPER} >> ${OPENCLAW_DATA_DIR}/logs/m11_replay_runner_daily_cron.cron.log 2>&1"

echo "------- proposed crontab entry -------"
echo "$ENTRY"
echo "--------------------------------------"
echo "Schedule: ${M11_REPLAY_MINUTE_UTC} ${M11_REPLAY_HOUR_UTC} * * * UTC (Daily 04:00 UTC = M11.a)"
echo "Wrapper:  $WRAPPER"
echo "Fixture:  $FIXTURE_PATH"
echo "API:      由 wrapper auto-resolve Tailscale IPv4 (uvicorn 在 trade-core 不 bind loopback;"
echo "          實機例如 \$(tailscale ip -4 | head -1):8000)。OPENCLAW_API_BASE_URL env 可覆寫;"
echo "          非 127.0.0.1 — operator 手動 pre-flight 勿用 loopback。"
echo "Log:      $OPENCLAW_DATA_DIR/logs/m11_replay_runner_daily_cron.cron.log"
echo "Heartbeat: $OPENCLAW_DATA_DIR/cron_heartbeat/m11_replay_runner_daily.last_fire"
echo "Audit row: learning.governance_audit_log (event_type='audit_write_failed'"
echo "           + payload.alert_type='m11_replay_runner_smoke_completed/_failed';"
echo "           V035 enum 未含 m11_*，piggyback per replay_key_rotation_check pattern;"
echo "           Sprint 3 Phase A 同步擴 enum)"
echo "Healthcheck impact: [48] FAIL → PASS within 24h after first fire"
echo ""
echo "避撞時段:"
echo "  03:00 UTC pg_dump (30 min budget)"
echo "  03:17 UTC ml_training_maintenance"
echo "  04:00 UTC ★ M11 daily smoke ★"
echo "  04:41 UTC feature_baseline_writer"
echo "  06:00 UTC counterfactual_daily"
echo "  09:00 UTC replay_key_rotation_check"

if [[ "${OPENCLAW_M11_REPLAY_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_M11_REPLAY_CRON_APPLY=1 to actually install."
    echo
    echo "預檢必跑：在 OPENCLAW_M11_REPLAY_CRON_APPLY=1 前確認"
    echo "  1. API server 跑中。注意 uvicorn 在 trade-core auto-resolve Tailscale IPv4 bind,"
    echo "     不 bind loopback;手動 pre-flight 用實機綁定 IP 非 127.0.0.1，例如："
    echo "       curl -s \"http://\$(tailscale ip -4 | head -1):8000/api/v1/replay/status\" → 200"
    echo "     （wrapper 內部同樣 auto-resolve；OPENCLAW_API_BASE_URL env 可覆寫）"
    echo "  2. replay_runner binary 跑得通（[47] healthcheck PASS）"
    echo "  3. 手動跑 wrapper dry-run 一次驗 register-only（不 dispatch run）："
    echo "     bash $WRAPPER"
    echo "  4. 驗 replay.experiments 多一 row + governance_audit_log alert_type='m11_replay_runner_register_only_completed' row"
    echo "     + replay.run_state 無新增 status='running' row（register-only 不製造 zombie）"
    exit 0
fi

# ─── 實際 install（僅 OPENCLAW_M11_REPLAY_CRON_APPLY=1 才走到）──
( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -
echo "INSTALLED: m11_replay_runner cron entry added. Verify with: crontab -l | grep m11_replay_runner"
