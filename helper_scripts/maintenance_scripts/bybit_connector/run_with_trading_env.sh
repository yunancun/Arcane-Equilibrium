#!/usr/bin/env bash
set -euo pipefail

# XP-1: Use env var with auto-detection fallback / 环境变量优先，回退自动推导
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
BASE="$_SRV/program_code/exchange_connectors/bybit_connector"
PROJECT_ENV="$_SRV/settings/environment_files/trading_services.env"
RUNTIME_ENV="$_SRV/docker_projects/trading_services/.env"

AI_SECRET_DIR="$_SRV/settings/secret_files/ai"
OPENAI_SECRET_FILE="${AI_SECRET_DIR}/openai_api_key"
ANTHROPIC_SECRET_FILE="${AI_SECRET_DIR}/anthropic_api_key"

VENV_DIR="$_SRV/venvs/openclaw_bybit_ai"

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
