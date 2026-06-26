#!/usr/bin/env python3
"""Bybit demo exchange-truth inventory snapshot.

This helper is intentionally read-only. It performs cursor-aware signed GET
full scans against Bybit demo open orders and positions, then writes a
timestamped JSON/Markdown packet for reconciliation review. It must not place,
cancel, modify, or close orders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BYBIT_CONTROL_ROOT = (
    REPO_ROOT / "program_code" / "exchange_connectors" / "bybit_connector"
    / "control_api_v1"
)
sys.path.insert(0, str(BYBIT_CONTROL_ROOT))

from app.bybit_rest_client import BybitClient, BybitError  # noqa: E402


SCHEMA = "bybit_demo_exchange_inventory_readonly_v1"
DEMO_BASE_URL = "https://api-demo.bybit.com"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compact_ts(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def decimal_value(value: Any) -> Decimal:
    try:
        text = str(value if value is not None else "").strip()
        if not text:
            return Decimal("0")
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def decimal_str(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001")), "f")


def stable_rows_sha256(rows: list[dict[str, Any]]) -> str:
    data = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def is_conditional_order(row: dict[str, Any]) -> bool:
    status = str(row.get("orderStatus") or "").strip()
    if status == "Untriggered":
        return True
    stop_type = str(row.get("stopOrderType") or "").strip()
    if stop_type and stop_type not in {"UNKNOWN", "None"}:
        return True
    return decimal_value(row.get("triggerPrice")) != Decimal("0")


def summarize_orders(rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(row.get("orderStatus") or "UNKNOWN") for row in rows)
    type_counts = Counter(str(row.get("orderType") or "UNKNOWN") for row in rows)
    symbol_counts = Counter(str(row.get("symbol") or "UNKNOWN") for row in rows)
    side_counts = Counter(str(row.get("side") or "UNKNOWN") for row in rows)
    notional = Decimal("0")
    for row in rows:
        price = decimal_value(row.get("price"))
        qty = decimal_value(row.get("leavesQty") or row.get("qty"))
        notional += price * qty
    return {
        "count": len(rows),
        "order_status_counts": dict(sorted(status_counts.items())),
        "order_type_counts": dict(sorted(type_counts.items())),
        "side_counts": dict(sorted(side_counts.items())),
        "symbol_counts": dict(sorted(symbol_counts.items())),
        "symbols": sorted(symbol_counts),
        "reduce_only_count": sum(1 for row in rows if row.get("reduceOnly") is True),
        "conditional_count": sum(1 for row in rows if is_conditional_order(row)),
        "estimated_open_notional_usdt": decimal_str(notional),
        "rows_sha256": stable_rows_sha256(rows),
    }


def summarize_positions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    side_counts = Counter(str(row.get("side") or "UNKNOWN") for row in rows)
    symbol_counts = Counter(str(row.get("symbol") or "UNKNOWN") for row in rows)
    nonzero = [
        row for row in rows
        if decimal_value(row.get("size")) != Decimal("0")
    ]
    nonzero_notional = Decimal("0")
    unrealised_pnl = Decimal("0")
    for row in nonzero:
        nonzero_notional += decimal_value(row.get("positionValue"))
        unrealised_pnl += decimal_value(row.get("unrealisedPnl"))
    return {
        "count": len(rows),
        "nonzero_count": len(nonzero),
        "side_counts": dict(sorted(side_counts.items())),
        "symbol_counts": dict(sorted(symbol_counts.items())),
        "nonzero_symbols": sorted({str(row.get("symbol")) for row in nonzero}),
        "nonzero_position_value_usdt": decimal_str(nonzero_notional),
        "nonzero_unrealised_pnl_usdt": decimal_str(unrealised_pnl),
        "rows_sha256": stable_rows_sha256(rows),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    default_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")) / (
        "audit/bybit_demo_exchange_inventory"
    )
    parser = argparse.ArgumentParser(
        description="Run a read-only cursor-aware Bybit demo open-order inventory.",
    )
    parser.add_argument("--environment", default="demo")
    parser.add_argument("--category", default="linear")
    parser.add_argument("--settle-coin", default="USDT")
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--output-dir", type=Path, default=default_dir)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--md-output", type=Path)
    return parser.parse_args(argv)


def build_packet(args: argparse.Namespace) -> dict[str, Any]:
    if args.environment != "demo":
        raise SystemExit("Refusing non-demo environment for this checkpoint")
    client = BybitClient(environment=args.environment)
    try:
        if client.base_url() != DEMO_BASE_URL:
            raise SystemExit(
                f"Refusing non-demo Bybit base URL: {client.base_url()}"
            )
        orders = client.get_active_orders_full_scan(
            category=args.category,
            settle_coin=args.settle_coin,
            open_only=0,
            limit=50,
            max_pages=args.max_pages,
        )
        positions = client.get_positions_full_scan(
            category=args.category,
            settle_coin=args.settle_coin,
            limit=200,
            max_pages=args.max_pages,
        )
    finally:
        client.close()

    generated = utc_now()
    return {
        "schema": SCHEMA,
        "generated_at_utc": utc_iso(generated),
        "request_scope": {
            "environment": args.environment,
            "base_url": DEMO_BASE_URL,
            "category": args.category,
            "settle_coin": args.settle_coin,
            "order_endpoint": "/v5/order/realtime",
            "order_params": {
                "category": args.category,
                "settleCoin": args.settle_coin,
                "openOnly": 0,
                "limit": 50,
            },
            "position_endpoint": "/v5/position/list",
            "position_params": {
                "category": args.category,
                "settleCoin": args.settle_coin,
                "limit": 200,
            },
            "max_pages": args.max_pages,
        },
        "boundary": {
            "read_only": True,
            "private_get_only": True,
            "post_used": False,
            "order_create_used": False,
            "cancel_or_modify_used": False,
            "position_close_used": False,
            "pg_write_used": False,
            "runtime_mutation_used": False,
            "service_restart_used": False,
            "crontab_or_env_mutation_used": False,
            "adapter_or_rust_writer_enabled": False,
            "cost_gate_lowered": False,
            "probe_or_order_authority_granted": False,
            "live_authority_granted": False,
        },
        "proof_exclusions": {
            "promotion_proof": False,
            "bounded_probe_profit_proof": False,
            "cost_gate_proof": False,
            "flash_dip_buy_fill_eligible": False,
            "unattributed_fill_eligible": False,
            "inventory_only": True,
        },
        "orders": {
            "summary": summarize_orders(orders),
            "rows": orders,
        },
        "positions": {
            "summary": summarize_positions(positions),
            "rows": positions,
        },
    }


def render_markdown(packet: dict[str, Any]) -> str:
    orders = packet["orders"]["summary"]
    positions = packet["positions"]["summary"]
    lines = [
        f"# Bybit Demo Exchange Inventory Read-Only Snapshot — {packet['generated_at_utc']}",
        "",
        f"- schema: `{packet['schema']}`",
        f"- base_url: `{packet['request_scope']['base_url']}`",
        f"- category / settleCoin: `{packet['request_scope']['category']}` / `{packet['request_scope']['settle_coin']}`",
        f"- order endpoint: `{packet['request_scope']['order_endpoint']}` openOnly=0 limit=50 cursor loop",
        f"- position endpoint: `{packet['request_scope']['position_endpoint']}` limit=200 cursor loop",
        "",
        "## Boundary",
        "",
        "- GET-only private read; no POST/order/cancel/modify/close.",
        "- No PG write, runtime mutation, service restart, crontab/env mutation, adapter/writer enablement, Cost Gate lowering, probe/order/live authority, or promotion proof.",
        "- This snapshot is exchange-truth inventory evidence only.",
        "",
        "## Open Orders",
        "",
        f"- count: `{orders['count']}`",
        f"- estimated_open_notional_usdt: `{orders['estimated_open_notional_usdt']}`",
        f"- order_status_counts: `{json.dumps(orders['order_status_counts'], sort_keys=True)}`",
        f"- order_type_counts: `{json.dumps(orders['order_type_counts'], sort_keys=True)}`",
        f"- side_counts: `{json.dumps(orders['side_counts'], sort_keys=True)}`",
        f"- symbols: `{', '.join(orders['symbols'])}`",
        f"- rows_sha256: `{orders['rows_sha256']}`",
        "",
        "## Positions",
        "",
        f"- count: `{positions['count']}`",
        f"- nonzero_count: `{positions['nonzero_count']}`",
        f"- nonzero_symbols: `{', '.join(positions['nonzero_symbols'])}`",
        f"- nonzero_position_value_usdt: `{positions['nonzero_position_value_usdt']}`",
        f"- nonzero_unrealised_pnl_usdt: `{positions['nonzero_unrealised_pnl_usdt']}`",
        f"- rows_sha256: `{positions['rows_sha256']}`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(packet: dict[str, Any], args: argparse.Namespace) -> tuple[Path, Path]:
    ts = compact_ts(utc_now())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.json_output or args.output_dir / f"{ts}_inventory.json"
    md_path = args.md_output or args.output_dir / f"{ts}_inventory.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(packet), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        packet = build_packet(args)
    except BybitError as exc:
        print(f"Bybit inventory failed closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2

    json_path, md_path = write_outputs(packet, args)
    print(json.dumps({
        "status": "DONE_READ_ONLY",
        "schema": SCHEMA,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "open_order_count": packet["orders"]["summary"]["count"],
        "nonzero_position_count": packet["positions"]["summary"]["nonzero_count"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
