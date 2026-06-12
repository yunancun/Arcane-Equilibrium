#!/usr/bin/env bash
# apply_manual_V140_agent_memory_vector.sh — manual V140 手動 apply 工具
#   （PA 2026-06-11 spec §3.2 路徑 B：V140 不入 sqlx 鏈，operator 以足夠權限手動跑）。
#
# 用法：
#   ./apply_manual_V140_agent_memory_vector.sh ['postgresql://redacted@host:port/db']
#   （無參數時改用 POSTGRES_USER/PASSWORD/DB[/HOST/PORT] env 組裝連線）
#
# 退出碼（供腳本化與清晰報錯）：
#   0 = apply 成功且驗證 embedding 欄為 vector（冪等：重跑同樣 0）
#   1 = SQL 失敗（非權限/前提類）或驗證不符
#   2 = 配置錯誤（無連線資訊 / psql 缺 / SQL 檔缺）
#   3 = 權限不足（CREATE EXTENSION vector 需 superuser/db-owner）—— 先以管理權限
#       單獨跑 `CREATE EXTENSION vector;` 再重跑本工具
#   4 = 前提缺失（V139 agent.agent_memory 未 apply）
#
# 為什麼不 set -e：psql 失敗 rc 要自行分類（權限/前提/其他）後給對應退出碼。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_FILE="$SCRIPT_DIR/manual_V140_agent_memory_vector.sql"

if [[ ! -f "$SQL_FILE" ]]; then
    echo "ERROR(2): SQL 檔不存在：$SQL_FILE" >&2
    exit 2
fi
if ! command -v psql >/dev/null 2>&1; then
    echo "ERROR(2): psql 不在 PATH（請在 PG 可達的主機跑，e.g. trade-core）。" >&2
    exit 2
fi

# ── 連線解析：$1 DSN 優先；否則 POSTGRES_* env ──
DSN="${1:-}"
PSQL_ARGS=()
if [[ -n "$DSN" ]]; then
    PSQL_ARGS=("$DSN")
else
    if [[ -n "${POSTGRES_USER:-}" && -n "${POSTGRES_DB:-}" ]]; then
        export PGPASSWORD="${POSTGRES_PASSWORD:-}"
        PSQL_ARGS=(
            -h "${POSTGRES_HOST:-127.0.0.1}"
            -p "${POSTGRES_PORT:-5432}"
            -U "$POSTGRES_USER"
            -d "$POSTGRES_DB"
        )
    else
        echo "ERROR(2): 無連線資訊——給 DSN 參數或設 POSTGRES_USER/POSTGRES_DB（必要時 POSTGRES_PASSWORD/HOST/PORT）。" >&2
        exit 2
    fi
fi

ERR_FILE="$(mktemp)"
trap 'rm -f "$ERR_FILE"' EXIT

echo "== manual V140 apply: $SQL_FILE =="
psql "${PSQL_ARGS[@]}" -v ON_ERROR_STOP=1 -f "$SQL_FILE" 2>"$ERR_FILE"
rc=$?

# stderr（含 NOTICE）一律回放給 operator——成功與否都要看得到 PG 端訊息。
if [[ -s "$ERR_FILE" ]]; then
    cat "$ERR_FILE" >&2
fi

if [[ $rc -ne 0 ]]; then
    if grep -qiE "permission denied to create extension|must be superuser" "$ERR_FILE"; then
        echo "" >&2
        echo "FAIL(3): 權限不足 —— CREATE EXTENSION vector 需要 superuser/db-owner。" >&2
        echo "         先以管理權限對目標 DB 跑：CREATE EXTENSION vector;" >&2
        echo "         之後重跑本工具（其餘步驟不需 superuser）。" >&2
        exit 3
    fi
    if grep -qiE "prerequisite FAIL|relation .agent\.agent_memory. does not exist" "$ERR_FILE"; then
        echo "" >&2
        echo "FAIL(4): 前提缺失 —— V139（agent.agent_memory）尚未 apply；先跑 V139 再回來。" >&2
        exit 4
    fi
    echo "" >&2
    echo "FAIL(1): psql rc=${rc}（非權限/前提類；詳見上方 stderr）。" >&2
    exit 1
fi

# ── 驗證：embedding 欄存在且 udt=vector（冪等 apply 的可觀測終態）──
VERIFY="$(psql "${PSQL_ARGS[@]}" -v ON_ERROR_STOP=1 -tA -c \
    "SELECT udt_name FROM information_schema.columns WHERE table_schema='agent' AND table_name='agent_memory' AND column_name='embedding';" \
    2>>"$ERR_FILE")"
vrc=$?
if [[ $vrc -ne 0 ]]; then
    echo "FAIL(1): 驗證查詢失敗（apply 可能已成功，請人工反射確認）。" >&2
    exit 1
fi
VERIFY="$(echo "$VERIFY" | tr -d '[:space:]')"
if [[ "$VERIFY" != "vector" ]]; then
    echo "FAIL(1): 驗證不符 —— embedding 欄 udt='$VERIFY'（期望 'vector'）。" >&2
    exit 1
fi

echo "OK: manual V140 applied — agent.agent_memory.embedding=vector(1024) + HNSW 就緒。"
echo "    冪等：本工具可安全重跑（IF NOT EXISTS 全覆蓋）。"
exit 0
