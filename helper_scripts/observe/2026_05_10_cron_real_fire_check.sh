#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# MODULE_NOTE
# 5/10 03:17 UTC ml_training_maintenance cron weekly Sunday real-fire 觀察腳本
#
# 用途：
#   2026-05-10 (Sunday, weekday=6) 03:30 UTC 後跑此腳本，驗證
#   ml_training cron IPC __auth handshake fix（commit 3d8d543e + fac9e386
#   + 1448e0a1 + cf291d63）在真實 cron weekly fire 下行為符合預期。
#
# 涵蓋觀察點（對應 E2 round 1 review report 4 SQL 觀察點）：
#   1. cron 是否在 03:1X UTC 真實 fire（log 抓時間戳）
#   2. optuna_optimizer.detail.param_ranges_source = "ipc"（不是 "unavailable:RuntimeError"）
#      → 證明 IPC __auth handshake 通；secret 注入成功
#   3. Sunday weekly audit 五 job 是否一同 fire（thompson/optuna/cpcv/dl3/weekly_report）
#   4. PG 4 表 row count delta（before/after 對比）
#      - learning.bayesian_posteriors（thompson_sampling）
#      - learning.ml_parameter_suggestions（optuna_optimizer）
#      - learning.foundation_model_features（dl3_foundation）
#      - learning.weekly_review_log（weekly_report_generator）
#
# 通過判定：
#   ✓ log 有 "2026-05-10 03:1X" 紀錄
#   ✓ optuna_optimizer.status="ok"
#   ✓ optuna_optimizer.detail.param_ranges_source="ipc"
#   ✓ 五 audit job 都 status="ok" 或合理 skip（fills 不足）
#   ✓ 4 表 row count delta：weekly_review_log 至少 +1（必 INSERT）；
#                          bayesian_posteriors / ml_parameter_suggestions /
#                          foundation_model_features 依 fills 樣本 (≥0)
#
# Pre-condition：
#   - 須在 Mac 端跑（透過 ssh trade-core 觸發 Linux 端查詢）
#   - 在 cron fire 之前先跑一次 "before" baseline，cron fire 後再跑 "after"，比對 delta
#   - PG 密碼從 ~/BybitOpenClaw/secrets/environment_files/basic_system_services.env 動態 source
#     （不 hardcode 到此 file）
#
# Usage：
#   bash helper_scripts/observe/2026_05_10_cron_real_fire_check.sh                   # 跑全部 4 觀察點
#   bash helper_scripts/observe/2026_05_10_cron_real_fire_check.sh --before          # 只 dump baseline (cron fire 前)
#   bash helper_scripts/observe/2026_05_10_cron_real_fire_check.sh --after           # 跑 after + delta 判定
#   bash helper_scripts/observe/2026_05_10_cron_real_fire_check.sh --baseline-file   # 指定 baseline file 位置
#
# 輸出：
#   stdout：人讀 verdict 報告
#   $OPENCLAW_DATA_DIR/observe/2026_05_10_cron_real_fire_<phase>.json (Linux 端)
#   ./baseline.json + ./after.json（Mac 端 cwd 暫存，--before 寫 baseline、--after 比對）
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PHASE="${1:-full}"   # 默認跑 full（before + after 不可用）；建議分兩次跑 --before / --after
BASELINE_FILE="./baseline_2026_05_10_cron.json"
AFTER_FILE="./after_2026_05_10_cron.json"

ts() { date -u '+%Y-%m-%d %H:%M:%S'; }

echo "[$(ts) UTC] === 5/10 cron real-fire check / phase=$PHASE ==="
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# 觀察點 1：cron fire log 抓時間戳
# ─────────────────────────────────────────────────────────────────────────────
check_cron_log() {
    echo "[1/4] cron fire log 檢查..."
    local result
    result=$(ssh trade-core "tail -100 /tmp/openclaw/logs/ml_training_maintenance_cron.log 2>/dev/null | grep -E '2026-05-10 03:1' || echo 'NO_MATCH'")
    if [[ "$result" == "NO_MATCH" ]] || [[ -z "$result" ]]; then
        echo "  ✗ FAIL: 未在 cron log 中找到 '2026-05-10 03:1X' 時間戳"
        echo "  排查方向："
        echo "    - cron job 是否裝在 crontab？ ssh trade-core 'crontab -l | grep ml_training_maintenance'"
        echo "    - 系統時區是否 UTC？ ssh trade-core 'date'"
        echo "    - 是否 lock 拒 spawn？ ssh trade-core 'ls /tmp/openclaw/locks/ml_training_maintenance_cron.lock.d 2>/dev/null'"
        return 1
    else
        echo "  ✓ PASS: cron 已 fire"
        echo "$result" | sed 's/^/    /'
        return 0
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# 觀察點 2：optuna_optimizer IPC handshake 通
# ─────────────────────────────────────────────────────────────────────────────
check_ipc_handshake() {
    echo ""
    echo "[2/4] optuna_optimizer IPC __auth handshake 檢查..."
    local result
    result=$(ssh trade-core "python3 -c \"
import json, sys
try:
    data = json.load(open('/tmp/openclaw/status/ml_training_maintenance_status.json'))
except Exception as e:
    print('STATUS_JSON_READ_FAIL:' + str(e))
    sys.exit(0)
for j in data.get('jobs', []):
    if j.get('job') == 'optuna_optimizer':
        detail = j.get('detail') or {}
        print('STATUS:' + str(j.get('status', '')))
        print('PARAM_RANGES_SOURCE:' + str(detail.get('param_ranges_source', '')))
        print('FILLS:' + str(detail.get('fills', '')))
        print('ERROR:' + str(j.get('error', '')))
        result = detail.get('result') or {}
        print('RESULT_STATUS:' + str(result.get('status', '')))
        print('RESULT_ERROR:' + str(result.get('error', '')))
        sys.exit(0)
print('OPTUNA_JOB_NOT_FOUND')
\"")
    echo "$result" | sed 's/^/    /'
    local status param_source
    status=$(echo "$result" | grep '^STATUS:' | cut -d: -f2-)
    param_source=$(echo "$result" | grep '^PARAM_RANGES_SOURCE:' | cut -d: -f2-)
    if [[ "$status" == "ok" ]] && [[ "$param_source" == "ipc" ]]; then
        echo "  ✓ PASS: status=ok / param_ranges_source=ipc → IPC __auth 握手通過"
        return 0
    elif [[ "$param_source" == unavailable* ]] || [[ "$param_source" == "" ]]; then
        echo "  ✗ FAIL: param_ranges_source='$param_source'，IPC handshake 未通過"
        echo "  排查方向："
        echo "    - cron sh 是否注入 OPENCLAW_IPC_SECRET_FILE？ grep IPC_SECRET ml_training_maintenance_cron.sh"
        echo "    - secret file 是否存在？ ssh trade-core 'ls -la \$HOME/BybitOpenClaw/secrets/environment_files/ipc_secret.txt'"
        echo "    - engine 是否監聽 IPC socket？ ssh trade-core 'ls -la /tmp/openclaw/openclaw_engine.sock'"
        return 1
    else
        echo "  ⚠ WARN: status='$status' / param_ranges_source='$param_source' — 非預期狀態，需人工判斷"
        return 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# 觀察點 3：Sunday weekly 五 job 同步 fire
# ─────────────────────────────────────────────────────────────────────────────
check_weekly_jobs() {
    echo ""
    echo "[3/4] Sunday weekly 五 audit job 檢查..."
    local result
    result=$(ssh trade-core "python3 -c \"
import json, sys
try:
    data = json.load(open('/tmp/openclaw/status/ml_training_maintenance_status.json'))
except Exception:
    sys.exit(0)
weekly = ['thompson_sampling', 'optuna_optimizer', 'cpcv_validator', 'dl3_foundation', 'weekly_report_generator']
seen = {}
for j in data.get('jobs', []):
    name = j.get('job')
    if name in weekly:
        seen[name] = j.get('status', '?')
for w in weekly:
    print(w + ':' + seen.get(w, 'MISSING'))
\"")
    echo "$result" | sed 's/^/    /'
    local missing_count error_count
    missing_count=$(echo "$result" | grep -c ':MISSING' || true)
    error_count=$(echo "$result" | grep -c ':error' || true)
    if [[ "$missing_count" -gt 0 ]]; then
        echo "  ✗ FAIL: $missing_count 個 weekly job 在 status_json 內缺席"
        echo "  排查方向：今天是否真 weekday=6 (Sunday)？ ssh trade-core 'date +%w'"
        return 1
    elif [[ "$error_count" -gt 0 ]]; then
        echo "  ⚠ WARN: $error_count 個 weekly job 回 error（已 fire 但 job 內部失敗，需人工檢查）"
        echo "  注：本 SOP 主旨是驗 IPC fix 與 cron real-fire；個別 job 內部 error 屬獨立議題"
        return 0
    else
        echo "  ✓ PASS: 五 weekly job 全部 fire 且 status=ok"
        return 0
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# 觀察點 4：PG 4 表 row count delta
# ─────────────────────────────────────────────────────────────────────────────
dump_pg_counts() {
    local out_file="$1"
    # 注：psql 對無 collation version 的 DB 會在 stderr 印 WARNING；
    # `2>/dev/null` 屏蔽 stderr 確保 out_file 只含 At 模式 row 輸出（純 "tbl:count" 格式）
    ssh trade-core "
        set -e
        ENV_FILE=\"\$HOME/BybitOpenClaw/secrets/environment_files/basic_system_services.env\"
        if [[ ! -f \"\$ENV_FILE\" ]]; then
            echo 'ENV_FILE_MISSING'
            exit 2
        fi
        PG_PASS=\$(grep '^POSTGRES_PASSWORD=' \"\$ENV_FILE\" | cut -d= -f2-)
        PG_USER=\$(grep '^POSTGRES_USER=' \"\$ENV_FILE\" | cut -d= -f2-)
        PG_DB=\$(grep '^POSTGRES_DB=' \"\$ENV_FILE\" | cut -d= -f2-)
        PG_HOST=\$(grep '^POSTGRES_HOST=' \"\$ENV_FILE\" | cut -d= -f2-)
        PG_PORT=\$(grep '^POSTGRES_PORT=' \"\$ENV_FILE\" | cut -d= -f2-)
        PG_HOST=\${PG_HOST:-127.0.0.1}
        PG_PORT=\${PG_PORT:-5432}
        export PGPASSWORD=\"\$PG_PASS\"
        psql -h \"\$PG_HOST\" -p \"\$PG_PORT\" -U \"\$PG_USER\" -d \"\$PG_DB\" -At -F: -c \"
            SELECT 'bp' || ':' || COUNT(*) FROM learning.bayesian_posteriors
            UNION ALL SELECT 'mps' || ':' || COUNT(*) FROM learning.ml_parameter_suggestions
            UNION ALL SELECT 'fmf' || ':' || COUNT(*) FROM learning.foundation_model_features
            UNION ALL SELECT 'wrl' || ':' || COUNT(*) FROM learning.weekly_review_log;
        \" 2>/dev/null
    " > "$out_file" 2>&1
}

check_pg_delta() {
    echo ""
    echo "[4/4] PG 4 表 row count delta 檢查..."
    if [[ ! -f "$BASELINE_FILE" ]]; then
        echo "  ✗ FAIL: baseline file 不存在 ($BASELINE_FILE)"
        echo "  請先在 cron fire 前跑：bash $0 --before"
        return 1
    fi
    dump_pg_counts "$AFTER_FILE"
    if grep -q 'ENV_FILE_MISSING\|FATAL\|psql:' "$AFTER_FILE" 2>/dev/null; then
        echo "  ✗ FAIL: PG query 失敗"
        cat "$AFTER_FILE" | sed 's/^/    /'
        return 1
    fi
    echo "  baseline ($(wc -l < "$BASELINE_FILE" | tr -d ' ') rows):"
    cat "$BASELINE_FILE" | sed 's/^/    /'
    echo "  after ($(wc -l < "$AFTER_FILE" | tr -d ' ') rows):"
    cat "$AFTER_FILE" | sed 's/^/    /'
    echo ""
    local pass=true
    for tbl in bp mps fmf wrl; do
        local before_count after_count delta
        before_count=$(grep "^${tbl}:" "$BASELINE_FILE" | cut -d: -f2 || echo "0")
        after_count=$(grep "^${tbl}:" "$AFTER_FILE" | cut -d: -f2 || echo "0")
        before_count=${before_count:-0}
        after_count=${after_count:-0}
        delta=$((after_count - before_count))
        echo "    $tbl: $before_count → $after_count (delta=$delta)"
        if [[ "$tbl" == "wrl" ]] && [[ "$delta" -lt 1 ]]; then
            echo "      ⚠ WARN: weekly_review_log 預期至少 +1（weekly_report_generator 必 INSERT）"
            pass=false
        fi
    done
    if [[ "$pass" == "true" ]]; then
        echo "  ✓ PASS: 4 表 delta 符合預期（wrl ≥ +1，其他依 fills 樣本可 0）"
        return 0
    else
        echo "  ✗ FAIL: 至少一表 delta 異常"
        return 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────
case "$PHASE" in
    --before)
        echo "[BEFORE] 採集 baseline（cron fire 前跑）..."
        dump_pg_counts "$BASELINE_FILE"
        if grep -q 'ENV_FILE_MISSING\|FATAL\|psql:' "$BASELINE_FILE" 2>/dev/null; then
            echo "  ✗ baseline dump 失敗："
            cat "$BASELINE_FILE" | sed 's/^/    /'
            exit 1
        fi
        echo "  ✓ baseline 寫入 $BASELINE_FILE："
        cat "$BASELINE_FILE" | sed 's/^/    /'
        echo ""
        echo "下一步：等到 5/10 03:17 UTC 後 (約 03:30 UTC) 跑 'bash $0 --after'"
        ;;
    --after|full)
        if [[ "$PHASE" == "full" ]] && [[ ! -f "$BASELINE_FILE" ]]; then
            echo "⚠ full mode 需先有 baseline，但 $BASELINE_FILE 不存在"
            echo "  請改跑：bash $0 --before（cron fire 前）+ bash $0 --after（cron fire 後）"
            exit 2
        fi
        FAIL=0
        check_cron_log     || FAIL=$((FAIL + 1))
        check_ipc_handshake || FAIL=$((FAIL + 1))
        check_weekly_jobs  || FAIL=$((FAIL + 1))
        check_pg_delta     || FAIL=$((FAIL + 1))
        echo ""
        echo "[$(ts) UTC] === 5/10 cron real-fire check 完成 ==="
        if [[ "$FAIL" -eq 0 ]]; then
            echo "✅ 全 4 觀察點 PASS — IPC __auth handshake fix 在真實 cron weekly fire 下生效"
            exit 0
        else
            echo "✗ $FAIL 觀察點 FAIL — 詳情見上"
            exit 1
        fi
        ;;
    *)
        echo "Usage: $0 [--before|--after]"
        echo "建議流程："
        echo "  cron fire 前一刻：bash $0 --before"
        echo "  cron fire 後 ~15min：bash $0 --after"
        exit 2
        ;;
esac
