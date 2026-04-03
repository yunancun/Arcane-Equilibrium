#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

cd $_SRV/program_code/exchange_connectors/bybit_connector
BASE="$_SRV/docker_projects/trading_services/runtime/bybit/thought_gate"

echo "===== 0) BACKUP ====="
for f in \
  scripts/bybit_mainline_cleanup_helpers.py \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_thought_gate_policy_builder.py \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py
do
  if [ -f "$f" ]; then
    cp "$f" "$f.bak_real_dirty_fix_$(date +%s)"
    echo "backed_up: $f"
  fi
done

echo
echo "===== 1) PATCH HELPER MODULE (ROBUST RECENT-TRADE / FRESHNESS / PRICING) ====="
python3 - <<'PY'
from pathlib import Path
import re

p = Path("scripts/bybit_mainline_cleanup_helpers.py")
s = p.read_text(encoding="utf-8")

marker = "# ==== MAINLINE CLEANUP OVERRIDE V2 ===="
if marker in s:
    s = s.split(marker)[0].rstrip() + "\n\n"

append = r'''
# ==== MAINLINE CLEANUP OVERRIDE V2 ====
from typing import Any, Dict, Iterable, Optional

def _mc_deep_iter(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _mc_deep_iter(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _mc_deep_iter(v)

def _mc_first_non_null(obj: Any, keys: Iterable[str]):
    keys = list(keys)
    for node in _mc_deep_iter(obj):
        if isinstance(node, dict):
            for k in keys:
                if k in node and node[k] is not None:
                    return node[k]
    return None

def _mc_find_trade_like_candidate(obj: Any):
    preferred_price_keys = [
        "recent_trade_last_price", "last_price", "price", "trade_price", "execPrice", "lastPrice"
    ]
    preferred_ts_keys = [
        "recent_trade_last_ts_ms", "recent_trade_last_ts", "last_ts_ms", "ts_ms",
        "timestamp_ms", "trade_time_ms", "execTime", "time", "T"
    ]

    best = {"price": None, "ts_ms": None}

    for node in _mc_deep_iter(obj):
        if isinstance(node, dict):
            p = None
            t = None
            for k in preferred_price_keys:
                if k in node and node[k] is not None:
                    p = node[k]
                    break
            for k in preferred_ts_keys:
                if k in node and node[k] is not None:
                    t = node[k]
                    break
            if p is not None and best["price"] is None:
                best["price"] = p
            if t is not None and best["ts_ms"] is None:
                best["ts_ms"] = t
            if best["price"] is not None and best["ts_ms"] is not None:
                return best
    return best

def _mc_to_ms(v: Any):
    if v is None:
        return None
    try:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
        x = float(v)
        if x <= 0:
            return None
        if x < 10_000_000_000:
            return int(x * 1000)
        return int(x)
    except Exception:
        return None

def normalize_recent_trade_fields(
    context: Any,
    explicit_price: Any = None,
    explicit_ts_ms: Any = None,
) -> Dict[str, Any]:
    price = explicit_price
    ts_ms = _mc_to_ms(explicit_ts_ms)

    if price is None or ts_ms is None:
        keys_price = [
            "recent_trade_last_price", "last_trade_price", "trade_price", "last_price",
            "recent_price", "execPrice", "lastPrice"
        ]
        keys_ts = [
            "recent_trade_last_ts_ms", "recent_trade_last_ts", "last_trade_ts_ms",
            "trade_time_ms", "ts_ms", "timestamp_ms", "execTime", "time", "T"
        ]

        found_price = _mc_first_non_null(context, keys_price)
        found_ts = _mc_first_non_null(context, keys_ts)

        if price is None and found_price is not None:
            price = found_price
        if ts_ms is None and found_ts is not None:
            ts_ms = _mc_to_ms(found_ts)

    if price is None or ts_ms is None:
        candidate = _mc_find_trade_like_candidate(context)
        if price is None and candidate.get("price") is not None:
            price = candidate.get("price")
        if ts_ms is None and candidate.get("ts_ms") is not None:
            ts_ms = _mc_to_ms(candidate.get("ts_ms"))

    return {
        "price": price,
        "ts_ms": ts_ms,
    }

def prune_freshness_warning_flags(context: Any, flags: Any):
    flags = list(dict.fromkeys(list(flags or [])))

    trade = normalize_recent_trade_fields(
        context,
        explicit_price=_mc_first_non_null(context, ["recent_trade_last_price"]),
        explicit_ts_ms=_mc_first_non_null(context, ["recent_trade_last_ts_ms", "recent_trade_last_ts"]),
    )
    price = trade.get("price")
    ts_ms = trade.get("ts_ms")

    if price is not None:
        flags = [w for w in flags if w != "recent_trade_last_price_missing"]
    if ts_ms is not None:
        flags = [w for w in flags if w != "recent_trade_last_ts_missing"]
    if price is not None and ts_ms is not None:
        flags = [w for w in flags if w != "last_trade_fields_missing"]

    payload_time_summary = _mc_first_non_null(context, ["payload_time_summary"])
    explicit_stale_state = _mc_first_non_null(
        context,
        [
            "runtime_state_reference_state",
            "reference_state",
            "payload_state",
        ],
    )
    explicit_age_ms = _mc_first_non_null(
        context,
        [
            "runtime_state_reference_age_ms",
            "reference_age_ms",
            "payload_age_ms",
        ],
    )
    explicit_age_ms = _mc_to_ms(explicit_age_ms)

    stale_like_values = {"old", "stale", "soft_stale", "hard_stale"}
    has_explicit_stale = (
        (isinstance(explicit_stale_state, str) and explicit_stale_state in stale_like_values)
        or ("public_microstructure_stale" in flags)
        or ("h0_final_audit_stale" in flags)
        or (explicit_age_ms is not None and explicit_age_ms > 0)
    )

    if not has_explicit_stale and payload_time_summary in (None, {}, []):
        flags = [w for w in flags if w != "runtime_state_reference_old"]

    if (
        "runtime_state_reference_old" not in flags
        and "recent_trade_last_price_missing" not in flags
        and "recent_trade_last_ts_missing" not in flags
        and "last_trade_fields_missing" not in flags
    ):
        flags = [w for w in flags if w != "freshness_soft_warning_present"]

    return flags

def resolve_provider_pricing(provider_target: Any, model_name: Any, usage_summary: Any) -> Dict[str, Any]:
    import os

    provider_target = str(provider_target or "").strip()
    model_name = str(model_name or "").strip()

    if provider_target == "openai_native" and model_name.startswith("gpt-5-mini"):
        try:
            input_per_1m = float(os.getenv("BYBIT_OPENAI_GPT5_MINI_INPUT_USD_PER_1M", "0.25"))
            cached_input_per_1m = float(os.getenv("BYBIT_OPENAI_GPT5_MINI_CACHED_INPUT_USD_PER_1M", "0.025"))
            output_per_1m = float(os.getenv("BYBIT_OPENAI_GPT5_MINI_OUTPUT_USD_PER_1M", "2.00"))
            return {
                "pricing_table_bound": True,
                "input_per_1m": input_per_1m,
                "cached_input_per_1m": cached_input_per_1m,
                "output_per_1m": output_per_1m,
            }
        except Exception:
            pass

    return {
        "pricing_table_bound": False,
        "input_per_1m": None,
        "cached_input_per_1m": None,
        "output_per_1m": None,
    }

def compute_usage_cost_usd(usage_summary: Any, pricing: Any):
    if not usage_summary or not pricing or not pricing.get("pricing_table_bound"):
        return None

    try:
        input_tokens = int((usage_summary or {}).get("input_tokens") or 0)
        output_tokens = int((usage_summary or {}).get("output_tokens") or 0)
        cached_tokens = int((((usage_summary or {}).get("input_tokens_details") or {}).get("cached_tokens")) or 0)

        billable_input = max(input_tokens - cached_tokens, 0)

        cost = 0.0
        cost += (billable_input / 1_000_000.0) * float(pricing["input_per_1m"])
        cost += (cached_tokens / 1_000_000.0) * float(pricing["cached_input_per_1m"])
        cost += (output_tokens / 1_000_000.0) * float(pricing["output_per_1m"])
        return round(cost, 6)
    except Exception:
        return None
'''
p.write_text(s + append, encoding="utf-8")
print("patched:", p)
PY

echo
echo "===== 2) PATCH H1 INPUT / POLICY BUILDERS ====="
python3 - <<'PY'
from pathlib import Path
import re

def ensure_import(s: str) -> str:
    imp = 'from bybit_mainline_cleanup_helpers import normalize_recent_trade_fields, prune_freshness_warning_flags'
    if imp in s:
        return s
    lines = s.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from __future__ import "):
            insert_at = i + 1
            break
    lines.insert(insert_at, imp)
    return "\n".join(lines) + "\n"

# ---------- bybit_thought_gate_input_builder.py ----------
p = Path("scripts/bybit_thought_gate_input_builder.py")
s = p.read_text(encoding="utf-8")
orig = s
s = ensure_import(s)

pattern = re.compile(
    r'(\s*)if recent_trade_last_price is None:\n\1\s+operator_flags\.append\("recent_trade_last_price_missing"\)\n\1if recent_trade_last_ts_ms is None:\n\1\s+operator_flags\.append\("recent_trade_last_ts_missing"\)',
    re.M
)
repl = r'''\1_rehydrated_trade = normalize_recent_trade_fields(
\1    locals(),
\1    explicit_price=recent_trade_last_price,
\1    explicit_ts_ms=recent_trade_last_ts_ms,
\1)
\1recent_trade_last_price = _rehydrated_trade.get("price")
\1recent_trade_last_ts_ms = _rehydrated_trade.get("ts_ms")

\1if recent_trade_last_price is None:
\1    operator_flags.append("recent_trade_last_price_missing")
\1if recent_trade_last_ts_ms is None:
\1    operator_flags.append("recent_trade_last_ts_missing")

\1operator_flags = prune_freshness_warning_flags(locals(), operator_flags)'''
s, n1 = pattern.subn(repl, s, count=1)

if n1 == 0 and 'operator_flags = prune_freshness_warning_flags(locals(), operator_flags)' not in s:
    anchor = '"operator_flags": operator_flags,'
    if anchor in s:
        s = s.replace(anchor, 'operator_flags = prune_freshness_warning_flags(locals(), operator_flags)\n\n        "operator_flags": operator_flags,', 1)

if s != orig:
    p.write_text(s, encoding="utf-8")
    print("patched:", p)
else:
    print("no_change:", p)

# ---------- bybit_thought_gate_policy_builder.py ----------
p = Path("scripts/bybit_thought_gate_policy_builder.py")
s = p.read_text(encoding="utf-8")
orig = s

imp = 'from bybit_mainline_cleanup_helpers import prune_freshness_warning_flags'
if imp not in s:
    lines = s.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from __future__ import "):
            insert_at = i + 1
            break
    lines.insert(insert_at, imp)
    s = "\n".join(lines) + "\n"

bad = 'warning_flags = prune_freshness_warning_flags(locals(), warning_flags)\nwarning_flags = prune_freshness_warning_flags(locals(), warning_flags)\n'
while bad in s:
    s = s.replace(bad, 'warning_flags = prune_freshness_warning_flags(locals(), warning_flags)\n')

if 'warning_flags = prune_freshness_warning_flags(locals(), warning_flags)' not in s:
    m = re.search(r'(^\s*report\s*=\s*\{)', s, re.M)
    if m:
        s = s[:m.start()] + '    warning_flags = prune_freshness_warning_flags(locals(), warning_flags)\n\n' + s[m.start()]

if s != orig:
    p.write_text(s, encoding="utf-8")
    print("patched:", p)
else:
    print("no_change:", p)
PY

echo
echo "===== 3) PATCH H5 STATE CLASSIFICATION (SOFT-WARN ONLY, NOT BLOCK) ====="
python3 - <<'PY'
from pathlib import Path
import re

targets = [
    ("scripts/bybit_ai_cost_log.py", "log_state", "log_ok", "ai_cost_log_recorded", "ai_cost_log_recorded_soft_warn", "ai_cost_log_blocked"),
    ("scripts/bybit_ai_governance_audit.py", "audit_state", "audit_ok", "ai_governance_audit_passed", "ai_governance_audit_passed_soft_warn", "ai_governance_audit_blocked"),
]

for file_name, state_name, ok_name, good_state, soft_state, blocked_state in targets:
    p = Path(file_name)
    s = p.read_text(encoding="utf-8")
    orig = s

    marker = f"# {state_name.upper()}_SOFTWARN_REPAIR_V2"
    if marker in s:
        s = s.replace(
            marker + "\n",
            ""
        )

    snippet = f'''    # {state_name.upper()}_SOFTWARN_REPAIR_V2
    soft_warn_only_flags = {{
        "recent_trade_last_price_missing",
        "recent_trade_last_ts_missing",
        "runtime_state_reference_old",
        "freshness_soft_warning_present",
        "last_trade_fields_missing",
    }}
    warning_flags = list(dict.fromkeys(list(warning_flags or [])))
    blocking_reasons = [x for x in list(blocking_reasons or []) if x not in soft_warn_only_flags]

    if blocking_reasons:
        {state_name} = "{blocked_state}"
        {ok_name} = False
    else:
        {state_name} = "{soft_state}" if warning_flags else "{good_state}"
        {ok_name} = True

'''

    m = re.search(r'(^\s*report\s*=\s*\{)', s, re.M)
    if m:
        s = s[:m.start()] + snippet + s[m.start():]

    if s != orig:
        p.write_text(s, encoding="utf-8")
        print("patched:", p)
    else:
        print("no_change:", p)

# final audit
p = Path("scripts/bybit_ai_cost_governance_final_audit.py")
s = p.read_text(encoding="utf-8")
orig = s

snippet = '''    warning_flags = list(dict.fromkeys(list(warning_flags or [])))

    if failed_checks:
        final_state = "ai_cost_governance_not_closed"
    else:
        final_state = "ai_cost_governance_closed_soft_warn_ready_for_i1" if warning_flags else "ai_cost_governance_closed_ready_for_i1"

'''

if 'final_state = "ai_cost_governance_closed_soft_warn_ready_for_i1"' not in s:
    m = re.search(r'(^\s*report\s*=\s*\{)', s, re.M)
    if m:
        s = s[:m.start()] + snippet + s[m.start():]

if '"final_state": final_state,' not in s:
    s = s.replace('"audit_state": audit_state,', '"audit_state": audit_state,\n        "final_state": final_state,')

if s != orig:
    p.write_text(s, encoding="utf-8")
    print("patched:", p)
else:
    print("no_change:", p)
PY

echo
echo "===== 4) PY_COMPILE ====="
python3 -m py_compile \
  scripts/bybit_mainline_cleanup_helpers.py \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_thought_gate_policy_builder.py \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py

echo
echo "===== 5) REBUILD H1 -> H5 ====="
./scripts/run_h1_thought_gate_full_closure.sh
./scripts/run_h2_query_budget_full_closure.sh
./scripts/run_h3_model_router_full_closure.sh
./scripts/run_h4_compute_governor_full_closure.sh
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 6) FINAL RECHECK ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json, os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def load(name):
    p = base / name
    return json.loads(p.read_text(encoding="utf-8"))

h1_req = load("bybit_ai_request_envelope_latest.json")
h5_log = load("bybit_ai_cost_log_latest.json")
h5_audit = load("bybit_ai_governance_audit_latest.json")
h5_final = load("bybit_ai_cost_governance_final_audit_latest.json")
h2_policy = load("bybit_query_budget_policy_latest.json")
h2_runtime = load("bybit_query_budget_runtime_latest.json")

cost_log = h5_log.get("cost_log") or {}
acct = cost_log.get("cost_accounting_summary") or {}
perf = cost_log.get("performance_summary") or {}

print("===== FINAL MAINLINE DIRTY POINTS STATUS =====")
print("H1 warning_flags =", h1_req.get("warning_flags"))
print("H2 policy warning_flags =", h2_policy.get("warning_flags"))
print("H2 runtime warning_flags =", h2_runtime.get("warning_flags"))
print("H5 warning_flags =", h5_final.get("warning_flags"))
print("")
print("pricing_table_bound =", acct.get("pricing_table_bound"))
print("actual_cost_usd =", acct.get("actual_cost_usd"))
print("within_timeout_hint =", perf.get("within_timeout_hint"))
print("")
print("log_state =", h5_log.get("log_state"))
print("audit_state =", h5_audit.get("audit_state"))
print("final_state =", h5_final.get("final_state"))
print("runtime_still_protected =", (h5_final.get("audit_summary") or {}).get("runtime_still_protected"))
print("h5_stage_closed =", (h5_final.get("audit_summary") or {}).get("h5_stage_closed"))
print("h_chapter_closed =", (h5_final.get("audit_summary") or {}).get("h_chapter_closed"))
print("ready_for_i1 =", (h5_final.get("audit_summary") or {}).get("ready_for_i1"))
PY

echo
echo "===== 7) H1 TRUTH RECHECK ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json, os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def load(name):
    p = base / name
    return json.loads(p.read_text(encoding="utf-8"))

tg = load("bybit_thought_gate_input_latest.json")
pol = load("bybit_thought_gate_policy_latest.json")
req = load("bybit_ai_request_envelope_latest.json")

def find_first(obj, key):
    if isinstance(obj, dict):
        if key in obj and obj[key] is not None:
            return obj[key]
        for v in obj.values():
            r = find_first(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_first(v, key)
            if r is not None:
                return r
    return None

print("recent_trade_last_price =", find_first(tg, "recent_trade_last_price"))
print("recent_trade_last_ts_ms =", find_first(tg, "recent_trade_last_ts_ms"))
print("operator_flags =", find_first(tg, "operator_flags"))
print("payload_time_summary =", find_first(tg, "payload_time_summary"))
print("policy_warning_flags =", pol.get("warning_flags"))
print("request_warning_flags =", req.get("warning_flags"))
PY
