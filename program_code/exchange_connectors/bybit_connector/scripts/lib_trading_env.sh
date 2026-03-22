#!/usr/bin/env bash
set -euo pipefail

# MODULE_NOTE / 模块说明:
# - role / 角色:
#   Shared env + secret loader helpers for Bybit connector scripts.
#   Bybit 连接器脚本共用的 env / secret 加载工具。
#
# - design / 设计原则:
#   1) Parent shell exported vars must win over file defaults.
#      父 shell 已 export 的变量优先级高于 env 文件默认值。
#   2) Secret files are loaded only when the target env var is still empty.
#      仅当目标环境变量为空时才从 secret file 注入。
#   3) Keep output silent and never print secret values.
#      保持静默，不输出任何密钥内容。

load_env_defaults() {
  local env_file="$1"
  [ -f "$env_file" ] || return 0

  while IFS= read -r line || [ -n "$line" ]; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue

    local key="${BASH_REMATCH[1]}"
    local raw="${BASH_REMATCH[2]}"

    # 父 shell 已经设置过的值不覆盖
    if [ -z "${!key+x}" ]; then
      eval "export ${key}=${raw}"
    fi
  done < "$env_file"
}

load_secret_if_missing() {
  local env_name="$1"
  local secret_file="$2"

  [ -n "${!env_name:-}" ] && return 0
  [ -f "$secret_file" ] || return 0

  local v
  v="$(tr -d '\r\n' < "$secret_file")"
  [ -n "$v" ] && export "${env_name}=${v}"
}

resolve_h1f_api_key_if_missing() {
  # 如果已经有了，就不动
  [ -n "${BYBIT_H1F_API_KEY:-}" ] && return 0

  local hint="${BYBIT_H1F_PROVIDER_MODE:-} ${BYBIT_H1F_API_BASE_URL:-}"

  case "$hint" in
    *anthropic*|*api.anthropic.com*)
      [ -n "${ANTHROPIC_API_KEY:-}" ] && export BYBIT_H1F_API_KEY="${ANTHROPIC_API_KEY}"
      ;;
    *openai*|*api.openai.com*)
      [ -n "${OPENAI_API_KEY:-}" ] && export BYBIT_H1F_API_KEY="${OPENAI_API_KEY}"
      ;;
  esac
}
