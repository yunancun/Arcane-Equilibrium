#!/usr/bin/env bash
set -euo pipefail

# MODULE_NOTE / 模块说明:
# - role / 角色:
#   Bind active AI route into normalized runtime env exports.
#   将当前 AI 路由决策绑定为统一的运行时环境变量。
#
# - purpose / 目的:
#   Read H1-R route selector output, then map route A/B/C/skip
#   to provider target, model, and output-token budget.
#   读取 H1-R 路由选择结果，并把 A/B/C/skip 映射成
#   provider target、model 和输出 token 预算。
#
# - design / 设计原则:
#   1) Only emit NEW normalized variables.
#      只输出新的标准化变量。
#   2) Do NOT emit any legacy H1E/H1F compatibility vars.
#      不再输出任何旧 H1E/H1F 兼容变量。
#   3) Parent shell exported values still override env defaults upstream;
#      this script only resolves the active route snapshot.
#      父 shell 的覆盖优先级仍由上游负责；本脚本只负责把当前路由决议标准化。

# XP-1: Use env var with auto-detection fallback / 环境变量优先，回退自动推导
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../../../.." && pwd)}"
BASE="$_SRV/program_code/exchange_connectors/bybit_connector"
ROUTE_JSON="$_SRV/docker_projects/trading_services/runtime/bybit/thought_gate/bybit_ai_route_selector_latest.json"
PROJECT_ENV="$_SRV/settings/environment_files/trading_services.env"
RUNTIME_ENV="$_SRV/docker_projects/trading_services/.env"

emit_export() {
  local name="$1"
  local value="${2:-}"
  printf 'export %s=%q\n' "$name" "$value"
}

if [ ! -f "$ROUTE_JSON" ]; then
  echo "route json not found: $ROUTE_JSON" >&2
  exit 1
fi

export _SRV  # Make available to embedded Python / 传递给内嵌 Python
python3 - <<'PY'
import json, os
from pathlib import Path

_srv = Path(os.environ.get("_SRV", "."))
route_json = _srv / "docker_projects/trading_services/runtime/bybit/thought_gate/bybit_ai_route_selector_latest.json"
env_files = [
    _srv / "settings/environment_files/trading_services.env",
    _srv / "docker_projects/trading_services/.env",
]

def load_env_files(paths):
    env = {}
    for path in paths:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env

def emit(name, value):
    if value is None:
        value = ""
    value = str(value).replace("'", "'\"'\"'")
    print(f"export {name}='{value}'")

env = load_env_files(env_files)
payload = json.loads(route_json.read_text(encoding="utf-8"))

route_decision = payload.get("route_decision", {}) or {}
route_plan = route_decision.get("route_plan", "route_skip")
route_reason = route_decision.get("route_reason", "missing_route_reason")
selected_ai_tier = route_decision.get("selected_ai_tier", "skip")
route_group = route_decision.get("env_binding_group", "ROUTE_SKIP")

provider_target = ""
model_name = ""
max_output_tokens = ""
route_tier = "skip"

if route_plan == "route_a_light":
    provider_target = env.get("BYBIT_ROUTE_A_PROVIDER_TARGET", "anthropic_native")
    model_name = env.get("BYBIT_ROUTE_A_MODEL", "")
    max_output_tokens = env.get("BYBIT_AI_MAX_OUTPUT_TOKENS_LIGHT", "220")
    route_tier = "light"
elif route_plan in {"route_b_standard", "route_b"}:
    provider_target = env.get("BYBIT_ROUTE_B_PROVIDER_TARGET", "openai_native")
    model_name = env.get("BYBIT_ROUTE_B_MODEL", "")
    max_output_tokens = env.get("BYBIT_AI_MAX_OUTPUT_TOKENS_STANDARD", "400")
    route_tier = "standard"
elif route_plan in {"route_c_strong", "route_c_escalated", "route_c"}:
    provider_target = env.get("BYBIT_ROUTE_C_PROVIDER_TARGET", "openai_native")
    model_name = env.get("BYBIT_ROUTE_C_MODEL", "")
    max_output_tokens = env.get("BYBIT_AI_MAX_OUTPUT_TOKENS_STRONG", "700")
    route_tier = "strong"
else:
    provider_target = ""
    model_name = ""
    max_output_tokens = "0"
    route_tier = "skip"

emit("BYBIT_AI_ACTIVE_ROUTE_PLAN", route_plan)
emit("BYBIT_AI_ACTIVE_ROUTE_TIER", route_tier)
emit("BYBIT_AI_ACTIVE_ROUTE_REASON", route_reason)
emit("BYBIT_AI_ACTIVE_ROUTE_GROUP", route_group)
emit("BYBIT_AI_ACTIVE_PROVIDER_TARGET", provider_target)
emit("BYBIT_AI_ACTIVE_MODEL", model_name)
emit("BYBIT_AI_ACTIVE_MAX_OUTPUT_TOKENS", max_output_tokens)
emit("BYBIT_AI_ACTIVE_SELECTED_AI_TIER", selected_ai_tier)
PY
