#!/usr/bin/env bash
set -euo pipefail

BASE="/home/ncyu/srv/program_code/exchange_connectors/bybit_connector"
PROJECT_ENV="/home/ncyu/srv/settings/environment_files/trading_services.env"
RUNTIME_ENV="/home/ncyu/srv/docker_projects/trading_services/.env"

AI_SECRET_DIR="/home/ncyu/srv/settings/secret_files/ai"
OPENAI_SECRET_FILE="${AI_SECRET_DIR}/openai_api_key"
ANTHROPIC_SECRET_FILE="${AI_SECRET_DIR}/anthropic_api_key"

VENV_DIR="/home/ncyu/srv/venvs/openclaw_bybit_ai"

# 优先使用稳定的专用 venv
if [ -x "${VENV_DIR}/bin/python" ]; then
  export PATH="${VENV_DIR}/bin:${PATH}"
fi

source "${BASE}/scripts/lib_trading_env.sh"

# 加载 env 默认值（父 shell 已 export 的优先）
load_env_defaults "$PROJECT_ENV"
load_env_defaults "$RUNTIME_ENV"

# 注入 provider secrets（仅在目标变量未设置时）
load_secret_if_missing OPENAI_API_KEY "$OPENAI_SECRET_FILE"
load_secret_if_missing ANTHROPIC_API_KEY "$ANTHROPIC_SECRET_FILE"

exec "$@"
