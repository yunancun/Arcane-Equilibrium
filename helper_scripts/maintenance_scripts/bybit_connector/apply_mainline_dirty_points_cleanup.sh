#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

ROOT="$_SRV/program_code/exchange_connectors/bybit_connector"
BASE="$_SRV/docker_projects/trading_services/runtime/bybit/thought_gate"
ENV1="$_SRV/settings/environment_files/trading_services.env"
ENV2="$_SRV/docker_projects/trading_services/.env"

backup_file() {
  local f="$1"
  [ -f "$f" ] || return 0
  cp "$f" "$f.bak_mainline_dirty_cleanup_$(date +%s)"
}

ensure_import() {
  local file="$1"
  local import_line="$2"
  grep -qF "$import_line" "$file" && return 0
  awk -v import_line="$import_line" '
    BEGIN { done=0 }
    {
      if (!done && ($0 ~ /^import / || $0 ~ /^from /)) {
        print import_line
        done=1
      }
      print
    }
    END {
      if (!done) print import_line
    }
  ' "$file" > "$file.tmp"
  mv "$file.tmp" "$file"
}

rewrite_env_file() {
  local f="$1"
  grep -Ev '^(BYBIT_AI_MAX_EXPECTED_ROUNDTRIP_MS|BYBIT_OPENAI_GPT5_MINI_INPUT_USD_PER_1M|BYBIT_OPENAI_GPT5_MINI_CACHED_INPUT_USD_PER_1M|BYBIT_OPENAI_GPT5_MINI_OUTPUT_USD_PER_1M)=' "$f" > "$f.tmp"
  cat >> "$f.tmp" <<'EOV'

# ===== mainline dirty-point cleanup =====
BYBIT_AI_MAX_EXPECTED_ROUNDTRIP_MS=5000
BYBIT_OPENAI_GPT5_MINI_INPUT_USD_PER_1M=0.25
BYBIT_OPENAI_GPT5_MINI_CACHED_INPUT_USD_PER_1M=0.025
BYBIT_OPENAI_GPT5_MINI_OUTPUT_USD_PER_1M=2.00
EOV
  mv "$f.tmp" "$f"
}

echo "===== 0) BACKUP TARGET FILES ====="
for f in \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_query_budget_policy.py \
  scripts/bybit_local_trigger_model_builder.py \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_thought_gate_policy_builder.py
do
  backup_file "$f"
  echo "backed_up: $f"
done

echo
echo "===== 1) INSTALL CLEANUP HELPER MODULE ====="
cat > scripts/bybit_mainline_cleanup_helpers.py <<'PY'
from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterable, List, Optional


def _coerce_number(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None
    return None


def _coerce_ts_ms(v: Any) -> Optional[int]:
    n = _coerce_number(v)
    if n is None:
        return None
    iv = int(n)
    if iv <= 0:
        return None
    if iv < 10_000_000_000:
        iv *= 1000
    return iv


def _iter_candidate_objects(local_scope: Dict[str, Any]) -> List[Any]:
    tokens = (
        "trade", "execution", "snapshot", "payload", "history",
        "market", "runtime", "recent", "observer", "verdict", "input"
    )
    out: List[Any] = []
    for k, v in local_scope.items():
        lk = str(k).lower()
        if any(t in lk for t in tokens):
            out.append(v)
    return out


def _search_nested_first(obj: Any, candidate_keys: Iterable[str], depth: int = 0, seen: Optional[set] = None) -> Any:
    if seen is None:
        seen = set()
    if depth > 6:
        return None

    oid = id(obj)
    if oid in seen:
        return None
    seen.add(oid)

    candidate_set = set(candidate_keys)

    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in candidate_set and v not in (None, "", [], {}):
                return v
        for _, v in obj.items():
            found = _search_nested_first(v, candidate_set, depth + 1, seen)
            if found not in (None, "", [], {}):
                return found
        return None

    if isinstance(obj, list):
        for item in obj[:50]:
            found = _search_nested_first(item, candidate_set, depth + 1, seen)
            if found not in (None, "", [], {}):
                return found
        return None

    return None


def normalize_recent_trade_fields(local_scope: Dict[str, Any], explicit_price: Any = None, explicit_ts_ms: Any = None) -> Dict[str, Any]:
    objs = _iter_candidate_objects(local_scope)

    price = explicit_price
    if price in (None, "", [], {}):
        price = None
    ts_ms = _coerce_ts_ms(explicit_ts_ms)

    if price is None:
        price = None
        for obj in objs:
            price = _search_nested_first(
                obj,
                [
                    "recent_trade_last_price",
                    "last_trade_price",
                    "trade_price",
                    "lastPrice",
                    "last_price",
                    "execPrice",
                    "price",
                ],
            )
            if price not in (None, "", [], {}):
                break

    if ts_ms is None:
        raw_ts = None
        for obj in objs:
            raw_ts = _search_nested_first(
                obj,
                [
                    "recent_trade_last_ts_ms",
                    "last_trade_ts_ms",
                    "trade_ts_ms",
                    "timestamp_ms",
                    "ts_ms",
                    "execTime",
                    "tradeTimeMs",
                    "time",
                    "createdTime",
                ],
            )
            ts_ms = _coerce_ts_ms(raw_ts)
            if ts_ms is not None:
                break

    return {"price": price, "ts_ms": ts_ms}


def resolve_reference_ts_ms(local_scope: Dict[str, Any]) -> Optional[int]:
    objs = _iter_candidate_objects(local_scope)

    for obj in objs:
        ts = _search_nested_first(
            obj,
            [
                "runtime_state_reference_ts_ms",
                "reference_ts_ms",
                "latest_payload_ts_ms",
                "latest_ts_ms",
                "snapshot_ts_ms",
                "ts_ms",
                "created_ts_ms",
            ],
        )
        out = _coerce_ts_ms(ts)
        if out is not None:
            return out

    for obj in objs:
        pts = _search_nested_first(obj, ["payload_time_summary"])
        if isinstance(pts, dict):
            vals = []
            for k, v in pts.items():
                if str(k).endswith("_payload_ts_ms"):
                    cv = _coerce_ts_ms(v)
                    if cv is not None:
                        vals.append(cv)
            if vals:
                return max(vals)

    return None


def prune_freshness_warning_flags(local_scope: Dict[str, Any], warning_flags: List[str], grace_ms: Optional[int] = None) -> List[str]:
    flags = list(dict.fromkeys(warning_flags or []))
    ref_ts_ms = resolve_reference_ts_ms(local_scope)

    if grace_ms is None:
        grace_ms = int(float(os.getenv("BYBIT_DECISION_LEASE_FRESHNESS_GRACE_MS", "5000")))

    if ref_ts_ms is None:
        return flags

    age_ms = max(0, int(time.time() * 1000) - int(ref_ts_ms))
    if age_ms <= grace_ms:
        flags = [w for w in flags if w not in ("freshness_soft_warning_present", "runtime_state_reference_old")]
    return list(dict.fromkeys(flags))


def resolve_provider_pricing(provider_target: Any, model_name: Any, usage_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    provider = str(provider_target or "")
    model = str(model_name or "")

    if provider == "openai_native" and model.startswith("gpt-5-mini"):
        return {
            "pricing_table_bound": True,
            "input_usd_per_1m": float(os.getenv("BYBIT_OPENAI_GPT5_MINI_INPUT_USD_PER_1M", "0.25")),
            "cached_input_usd_per_1m": float(os.getenv("BYBIT_OPENAI_GPT5_MINI_CACHED_INPUT_USD_PER_1M", "0.025")),
            "output_usd_per_1m": float(os.getenv("BYBIT_OPENAI_GPT5_MINI_OUTPUT_USD_PER_1M", "2.00")),
        }

    return {
        "pricing_table_bound": False,
        "input_usd_per_1m": None,
        "cached_input_usd_per_1m": None,
        "output_usd_per_1m": None,
    }


def compute_usage_cost_usd(usage_summary: Optional[Dict[str, Any]], pricing: Dict[str, Any]) -> Optional[float]:
    if not usage_summary or not pricing.get("pricing_table_bound"):
        return None

    input_tokens = int((usage_summary or {}).get("input_tokens") or 0)
    output_tokens = int((usage_summary or {}).get("output_tokens") or 0)

    input_details = (usage_summary or {}).get("input_tokens_details") or {}
    cached_tokens = int(input_details.get("cached_tokens") or 0)
    billable_input_tokens = max(input_tokens - cached_tokens, 0)

    input_rate = float(pricing.get("input_usd_per_1m") or 0.0)
    cached_input_rate = float(pricing.get("cached_input_usd_per_1m") or input_rate)
    output_rate = float(pricing.get("output_usd_per_1m") or 0.0)

    cost = (
        (billable_input_tokens * input_rate)
        + (cached_tokens * cached_input_rate)
        + (output_tokens * output_rate)
    ) / 1_000_000.0

    return round(cost, 10)
PY

echo "installed: scripts/bybit_mainline_cleanup_helpers.py"

echo
echo "===== 2) REWRITE ENV MAINLINE KEYS ====="
rewrite_env_file "$ENV1"
rewrite_env_file "$ENV2"

grep -nE '^(BYBIT_AI_MAX_EXPECTED_ROUNDTRIP_MS|BYBIT_OPENAI_GPT5_MINI_INPUT_USD_PER_1M|BYBIT_OPENAI_GPT5_MINI_CACHED_INPUT_USD_PER_1M|BYBIT_OPENAI_GPT5_MINI_OUTPUT_USD_PER_1M)=' "$ENV1" "$ENV2"

echo
echo "===== 3) PATCH bybit_ai_cost_log.py ====="
ensure_import "scripts/bybit_ai_cost_log.py" 'from bybit_mainline_cleanup_helpers import compute_usage_cost_usd, resolve_provider_pricing'

perl -0pi -e '
s/actual_cost_usd = None\s+pricing_table_bound = False/pricing = resolve_provider_pricing(\n        provider_target=request_summary.get("provider_target"),\n        model_name=request_summary.get("model_name"),\n        usage_summary=usage_summary,\n    )\n    pricing_table_bound = bool(pricing.get("pricing_table_bound"))\n    actual_cost_usd = compute_usage_cost_usd(usage_summary, pricing) if pricing_table_bound else None/s
' scripts/bybit_ai_cost_log.py

perl -0pi -e '
s/\+\s*\["provider_pricing_table_not_bound_in_mainline"\]/+ (["provider_pricing_table_not_bound_in_mainline"] if not pricing_table_bound else [])/g
' scripts/bybit_ai_cost_log.py

grep -nE 'resolve_provider_pricing|compute_usage_cost_usd|pricing_table_bound|actual_cost_usd|provider_pricing_table_not_bound_in_mainline' scripts/bybit_ai_cost_log.py

echo
echo "===== 4) PATCH bybit_query_budget_policy.py ====="
ensure_import "scripts/bybit_query_budget_policy.py" 'import os'

perl -0pi -e '
s/within_timeout_hint: Optional\[bool\] = None\s+if latency_ms is not None and deadline_ms_hint is not None:\s+within_timeout_hint = latency_ms <= deadline_ms_hint\s+if within_timeout_hint is False:\s+warning_flags.append\("last_call_latency_exceeds_deadline_hint"\)/provider_roundtrip_ceiling_ms = int(float(os.getenv("BYBIT_AI_MAX_EXPECTED_ROUNDTRIP_MS", "5000")))\n    effective_deadline_ms_hint = max(int(deadline_ms_hint), provider_roundtrip_ceiling_ms) if deadline_ms_hint is not None else provider_roundtrip_ceiling_ms\n\n    within_timeout_hint: Optional[bool] = None\n    if latency_ms is not None and effective_deadline_ms_hint is not None:\n        within_timeout_hint = latency_ms <= effective_deadline_ms_hint\n        if within_timeout_hint is False:\n            warning_flags.append("last_call_latency_exceeds_deadline_hint")/s
' scripts/bybit_query_budget_policy.py

grep -nE 'provider_roundtrip_ceiling_ms|effective_deadline_ms_hint|within_timeout_hint|last_call_latency_exceeds_deadline_hint' scripts/bybit_query_budget_policy.py

echo
echo "===== 5) PATCH last-trade / freshness chain ====="
ensure_import "scripts/bybit_local_trigger_model_builder.py" 'from bybit_mainline_cleanup_helpers import normalize_recent_trade_fields, prune_freshness_warning_flags'
ensure_import "scripts/bybit_thought_gate_input_builder.py" 'from bybit_mainline_cleanup_helpers import normalize_recent_trade_fields, prune_freshness_warning_flags'
ensure_import "scripts/bybit_thought_gate_policy_builder.py" 'from bybit_mainline_cleanup_helpers import prune_freshness_warning_flags'

perl -0pi -e '
s/last_trade_fields_present = \(\s*recent_trade_last_price is not None\s*and recent_trade_last_ts_ms is not None\s*\)\s*if not last_trade_fields_present:\s*warning_flags.append\("last_trade_fields_missing"\)/_rehydrated_trade = normalize_recent_trade_fields(\n        locals(),\n        explicit_price=recent_trade_last_price,\n        explicit_ts_ms=recent_trade_last_ts_ms,\n    )\n    recent_trade_last_price = _rehydrated_trade.get("price")\n    recent_trade_last_ts_ms = _rehydrated_trade.get("ts_ms")\n\n    last_trade_fields_present = (\n        recent_trade_last_price is not None\n        and recent_trade_last_ts_ms is not None\n    )\n    if not last_trade_fields_present:\n        warning_flags.append("last_trade_fields_missing")\n\n    warning_flags = prune_freshness_warning_flags(locals(), warning_flags)/s
' scripts/bybit_local_trigger_model_builder.py

perl -0pi -e '
s/warning_flags\.append\("freshness_soft_warning_present"\)/warning_flags.append("freshness_soft_warning_present")\n    warning_flags = prune_freshness_warning_flags(locals(), warning_flags)/g
' scripts/bybit_local_trigger_model_builder.py

perl -0pi -e '
s/if recent_trade_last_price is None:\s+operator_flags.append\("recent_trade_last_price_missing"\)\s+if recent_trade_last_ts_ms is None:\s+operator_flags.append\("recent_trade_last_ts_missing"\)/_rehydrated_trade = normalize_recent_trade_fields(\n        locals(),\n        explicit_price=recent_trade_last_price,\n        explicit_ts_ms=recent_trade_last_ts_ms,\n    )\n    recent_trade_last_price = _rehydrated_trade.get("price")\n    recent_trade_last_ts_ms = _rehydrated_trade.get("ts_ms")\n\n    if recent_trade_last_price is None:\n        operator_flags.append("recent_trade_last_price_missing")\n    if recent_trade_last_ts_ms is None:\n        operator_flags.append("recent_trade_last_ts_missing")\n\n    operator_flags = prune_freshness_warning_flags(locals(), operator_flags)/s
' scripts/bybit_thought_gate_input_builder.py

perl -0pi -e '
s/warning_flags\.append\("runtime_state_reference_old"\)/warning_flags.append("runtime_state_reference_old")\n    warning_flags = prune_freshness_warning_flags(locals(), warning_flags)/g
' scripts/bybit_thought_gate_policy_builder.py

grep -nE 'normalize_recent_trade_fields|prune_freshness_warning_flags|recent_trade_last_price_missing|recent_trade_last_ts_missing|last_trade_fields_missing|runtime_state_reference_old|freshness_soft_warning_present' \
  scripts/bybit_local_trigger_model_builder.py \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_thought_gate_policy_builder.py

echo
echo "===== 6) PY_COMPILE ====="
python3 -m py_compile \
  scripts/bybit_mainline_cleanup_helpers.py \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_query_budget_policy.py \
  scripts/bybit_local_trigger_model_builder.py \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_thought_gate_policy_builder.py

echo
echo "===== 7) RERUN MAINLINE CLOSURE ====="
./scripts/run_h1_thought_gate_full_closure.sh
./scripts/run_h2_query_budget_full_closure.sh
./scripts/run_h3_model_router_full_closure.sh
./scripts/run_h4_compute_governor_full_closure.sh
./scripts/run_h5_ai_cost_governance_full_closure.sh

./scripts/run_i1_decision_lease_full_closure.sh
./scripts/run_i2_decision_lease_shadow_closure.sh
./scripts/run_i3_decision_lease_consume_closure.sh
./scripts/run_i4_decision_lease_replay_closure.sh
./scripts/run_i5_decision_lease_friction_closure.sh

./scripts/run_with_trading_env.sh bash -lc '
cd $_SRV/program_code/exchange_connectors/bybit_connector

python3 scripts/bybit_decision_lease_approval_bridge.py
python3 scripts/bybit_decision_lease_approval_bridge_contract_check.py
python3 scripts/bybit_decision_lease_approval_bridge_final_audit.py

python3 scripts/bybit_execution_authority_aggregator.py
python3 scripts/bybit_execution_authority_aggregator_contract_check.py
python3 scripts/bybit_execution_authority_aggregator_final_audit.py

python3 scripts/bybit_manual_approval_packet.py
python3 scripts/bybit_manual_approval_packet_contract_check.py
python3 scripts/bybit_manual_approval_packet_final_audit.py

python3 scripts/bybit_operator_ack_shadow.py
python3 scripts/bybit_operator_ack_shadow_contract_check.py
python3 scripts/bybit_operator_ack_shadow_final_audit.py

python3 scripts/bybit_decision_lease_chapter_summary.py
python3 scripts/bybit_decision_lease_chapter_handoff.py
python3 scripts/bybit_decision_lease_chapter_final_audit.py
'

echo
echo "===== 8) FINAL DIRTY-POINT CHECK ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json, os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def read(name):
    p = base / name
    return json.loads(p.read_text(encoding="utf-8"))

req = read("bybit_ai_request_envelope_latest.json")
h2 = read("bybit_query_budget_final_audit_latest.json")
log = read("bybit_ai_cost_log_latest.json")
i10 = read("bybit_decision_lease_chapter_final_audit_latest.json")

cost_log = log.get("cost_log") or {}
acct = cost_log.get("cost_accounting_summary") or {}
perf = cost_log.get("performance_summary") or {}

print("===== MAINLINE DIRTY POINT FINAL STATUS =====")
print("H1 warning_flags =", req.get("warning_flags"))
print("H2 warning_flags =", h2.get("warning_flags"))
print("H5 pricing_table_bound =", acct.get("pricing_table_bound"))
print("H5 actual_cost_usd =", acct.get("actual_cost_usd"))
print("H5 within_timeout_hint =", perf.get("within_timeout_hint"))
print("I10 warning_flags =", i10.get("warning_flags"))
PY
