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

def compute_usage_cost_usd(usage_summary: Any, pricing: Any) -> Any:
    """Authoritative cost calculator. Reads `input_usd_per_1m` key names
    (matching the output of the MAINLINE_PRICING_ALIAS_OVERRIDE_V1
    resolve_provider_pricing above)."""
    if not usage_summary or not pricing or not pricing.get("pricing_table_bound"):
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
