#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

echo "===== 0) BACKUP ====="
targets=(
  scripts/bybit_mainline_cleanup_helpers.py
  scripts/bybit_ai_cost_log.py
  scripts/bybit_thought_gate_input_builder.py
  scripts/bybit_thought_gate_policy_builder.py
  scripts/bybit_local_trigger_model_builder.py
)
for f in "${targets[@]}"; do
  if [ -f "$f" ]; then
    cp "$f" "$f.bak_final_dirty_points_fix_$(date +%s)"
    echo "backed_up: $f"
  fi
done

echo
echo "===== 1) HARDEN PRICING RESOLUTION ALIAS ====="
helper="scripts/bybit_mainline_cleanup_helpers.py"

if ! grep -q 'MAINLINE_PRICING_ALIAS_OVERRIDE_V1' "$helper"; then
  cat >> "$helper" <<'PYEOF'

# MAINLINE_PRICING_ALIAS_OVERRIDE_V1
def resolve_provider_pricing(*, provider_target, model_name, usage_summary=None):
    import os
    import re

    def _env_float(name: str):
        raw = os.getenv(name)
        if raw is None or str(raw).strip() == "":
            return None
        try:
            return float(raw)
        except Exception:
            return None

    pt = str(provider_target or "").strip().upper()
    mn = str(model_name or "").strip().lower()

    provider_aliases = []
    if pt == "OPENAI_NATIVE":
        provider_aliases = ["OPENAI", "OPENAI_NATIVE"]
    elif pt:
        provider_aliases = [pt]
    else:
        provider_aliases = ["OPENAI", "OPENAI_NATIVE"]

    model_aliases = []
    compact = re.sub(r'[^a-z0-9]+', '', mn)

    if compact.startswith("gpt5mini") or compact.startswith("gpt54mini"):
        model_aliases = [
            "GPT5_MINI",
            "GPT_5_MINI",
            "GPT54_MINI",
            "GPT_5_4_MINI",
        ]
    elif compact.startswith("gpt5nano") or compact.startswith("gpt54nano"):
        model_aliases = [
            "GPT5_NANO",
            "GPT_5_NANO",
            "GPT54_NANO",
            "GPT_5_4_NANO",
        ]
    elif compact.startswith("gpt5"):
        model_aliases = [
            "GPT5",
            "GPT_5",
            "GPT54",
            "GPT_5_4",
        ]
    else:
        generic = re.sub(r'[^A-Z0-9]+', '_', mn.upper()).strip('_')
        if generic:
            model_aliases = [generic]

    for provider_key in provider_aliases:
        for model_key in model_aliases:
            input_key = f"BYBIT_{provider_key}_{model_key}_INPUT_USD_PER_1M"
            cached_key = f"BYBIT_{provider_key}_{model_key}_CACHED_INPUT_USD_PER_1M"
            output_key = f"BYBIT_{provider_key}_{model_key}_OUTPUT_USD_PER_1M"

            input_price = _env_float(input_key)
            cached_price = _env_float(cached_key)
            output_price = _env_float(output_key)

            if input_price is not None and output_price is not None:
                return {
                    "pricing_table_bound": True,
                    "provider_target": provider_target,
                    "model_name": model_name,
                    "pricing_env_keys": {
                        "input": input_key,
                        "cached_input": cached_key,
                        "output": output_key,
                    },
                    "input_usd_per_1m": input_price,
                    "cached_input_usd_per_1m": cached_price if cached_price is not None else input_price,
                    "output_usd_per_1m": output_price,
                }

    return {
        "pricing_table_bound": False,
        "provider_target": provider_target,
        "model_name": model_name,
        "pricing_env_keys": None,
        "input_usd_per_1m": None,
        "cached_input_usd_per_1m": None,
        "output_usd_per_1m": None,
    }
PYEOF
  echo "appended_pricing_alias_override=True"
else
  echo "appended_pricing_alias_override=False (already present)"
fi

echo
echo "===== 2) PATCH thought_gate_input_builder ====="
f="scripts/bybit_thought_gate_input_builder.py"

perl -0pi -e '
s@
if recent_trade_last_price is None:
\s+operator_flags\.append\("recent_trade_last_price_missing"\)
\s+if recent_trade_last_ts_ms is None:
\s+operator_flags\.append\("recent_trade_last_ts_missing"\)
@
_rehydrated_trade = normalize_recent_trade_fields(
        locals(),
        explicit_price=recent_trade_last_price,
        explicit_ts_ms=recent_trade_last_ts_ms,
    )
    recent_trade_last_price = _rehydrated_trade.get("price")
    recent_trade_last_ts_ms = _rehydrated_trade.get("ts_ms")

    if recent_trade_last_price is None:
        operator_flags.append("recent_trade_last_price_missing")
    if recent_trade_last_ts_ms is None:
        operator_flags.append("recent_trade_last_ts_missing")

    operator_flags = prune_freshness_warning_flags(locals(), operator_flags)
@smx
' "$f"

grep -nE 'normalize_recent_trade_fields|prune_freshness_warning_flags|recent_trade_last_price_missing|recent_trade_last_ts_missing' "$f" || true

echo
echo "===== 3) PATCH thought_gate_policy_builder ====="
f="scripts/bybit_thought_gate_policy_builder.py"

perl -0pi -e '
s@
if "recent_trade_last_price_missing" in operator_flags_from_input:
\s+warning_flags\.append\("recent_trade_last_price_missing"\)
\s+if "recent_trade_last_ts_missing" in operator_flags_from_input:
\s+warning_flags\.append\("recent_trade_last_ts_missing"\)
@
if "recent_trade_last_price_missing" in operator_flags_from_input:
        warning_flags.append("recent_trade_last_price_missing")
    if "recent_trade_last_ts_missing" in operator_flags_from_input:
        warning_flags.append("recent_trade_last_ts_missing")

    warning_flags = prune_freshness_warning_flags(locals(), warning_flags)
@smx
' "$f"

grep -nE 'prune_freshness_warning_flags|recent_trade_last_price_missing|recent_trade_last_ts_missing|runtime_state_reference_old|freshness_soft_warning_present' "$f" || true

echo
echo "===== 4) PATCH local_trigger_model_builder REHYDRATE BLOCK ====="
f="scripts/bybit_local_trigger_model_builder.py"

perl -0pi -e '
s@
last_trade_fields_present = \(
\s+recent_trade_last_price is not None
\s+and recent_trade_last_ts_ms is not None
\s+\)
\s+if not last_trade_fields_present:
\s+warning_flags\.append\("last_trade_fields_missing"\)
@
_rehydrated_trade = normalize_recent_trade_fields(
        locals(),
        explicit_price=recent_trade_last_price,
        explicit_ts_ms=recent_trade_last_ts_ms,
    )
    recent_trade_last_price = _rehydrated_trade.get("price")
    recent_trade_last_ts_ms = _rehydrated_trade.get("ts_ms")

    last_trade_fields_present = (
        recent_trade_last_price is not None
        and recent_trade_last_ts_ms is not None
    )
    if not last_trade_fields_present:
        warning_flags.append("last_trade_fields_missing")
@smx
' "$f"

grep -nE 'normalize_recent_trade_fields|prune_freshness_warning_flags|last_trade_fields_present|last_trade_fields_missing|freshness_soft_warning_present' "$f" || true

echo
echo "===== 5) PY_COMPILE ====="
python3 -m py_compile \
  scripts/bybit_mainline_cleanup_helpers.py \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_thought_gate_policy_builder.py \
  scripts/bybit_local_trigger_model_builder.py \
  scripts/bybit_query_budget_policy.py

echo
echo "===== 6) REBUILD MAINLINE H1 -> H5 ====="
./scripts/run_with_trading_env.sh bash -lc '
set -euo pipefail
cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

./scripts/run_h1_thought_gate_full_closure.sh
./scripts/run_h2_query_budget_full_closure.sh
./scripts/run_h3_model_router_full_closure.sh
./scripts/run_h4_compute_governor_full_closure.sh
./scripts/run_h5_ai_cost_governance_full_closure.sh
'

echo
echo "===== 7) POST-REBUILD MAINLINE CHECK ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

def load(name):
    return json.loads((base / name).read_text(encoding="utf-8"))

h1 = load("bybit_ai_request_envelope_latest.json")
h2p = load("bybit_query_budget_policy_latest.json")
h2r = load("bybit_query_budget_runtime_latest.json")
h5 = load("bybit_ai_cost_log_latest.json")
h5a = load("bybit_ai_cost_governance_final_audit_latest.json")

acct = (h5.get("cost_log") or {}).get("cost_accounting_summary") or {}
perf = (h5.get("cost_log") or {}).get("performance_summary") or {}

print("===== FINAL MAINLINE DIRTY POINTS STATUS =====")
print("H1 warning_flags =", h1.get("warning_flags"))
print("H2 policy warning_flags =", h2p.get("warning_flags"))
print("H2 runtime warning_flags =", h2r.get("warning_flags"))
print("H5 warning_flags =", h5.get("warning_flags"))
print("")
print("pricing_table_bound =", acct.get("pricing_table_bound"))
print("actual_cost_usd =", acct.get("actual_cost_usd"))
print("within_timeout_hint =", perf.get("within_timeout_hint"))
print("")
print("H5 audit_state =", h5a.get("audit_state"))
print("runtime_still_protected =", (h5a.get("audit_summary") or {}).get("runtime_still_protected"))
PY
