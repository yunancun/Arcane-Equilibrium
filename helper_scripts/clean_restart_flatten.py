#!/usr/bin/env python3
"""
clean_restart_flatten.py — Exchange flatten helper for clean_restart.sh.

MODULE_NOTE (EN): Uses httpx-based BybitClient (PYO3-ELIMINATE-1 Phase 2) to
  close every open position with reduce_only market orders and cancel every
  open order, for a given environment ("demo" or "mainnet"). Safe to run with
  the Rust engine stopped — talks to Bybit REST directly.
MODULE_NOTE (中): 使用 httpx 版 BybitClient（PYO3-ELIMINATE-1 Phase 2 後）
  對指定環境（demo 或 mainnet）的每個未平倉持倉下 reduce_only 市價單，
  並取消所有未成交訂單。Rust 引擎停止時可安全運行 — 直接透過 Bybit REST 通訊。

Usage:
    python3 clean_restart_flatten.py --env demo [--yes] [--dry-run]
    python3 clean_restart_flatten.py --env mainnet --yes   # live flatten
"""

from __future__ import annotations

import argparse
import sys
import time


def main() -> int:
    ap = argparse.ArgumentParser(description="Flatten Bybit positions/orders")
    ap.add_argument("--env", default="demo", choices=["demo", "mainnet"],
                    help="Bybit environment slot (default: demo)")
    ap.add_argument("--yes", action="store_true", help="Skip confirmation")
    ap.add_argument("--dry-run", action="store_true", help="Report only")
    args = ap.parse_args()

    # ── Import Python BybitClient (PYO3-ELIMINATE-1 Phase 2) ────────────
    # ── 使用純 Python httpx 版 BybitClient（已從 PyO3 遷移）
    try:
        from program_code.exchange_connectors.bybit_connector.control_api_v1.app.bybit_rest_client import BybitClient
    except ImportError as exc:
        print(f"[ERR] BybitClient not importable: {exc}", file=sys.stderr)
        print("      Activate API venv and cd to repo root:", file=sys.stderr)
        print("      cd /home/ncyu/BybitOpenClaw/srv  # or $OPENCLAW_BASE_DIR", file=sys.stderr)
        print("      source program_code/exchange_connectors/bybit_connector/"
              "control_api_v1/.venv/bin/activate", file=sys.stderr)
        return 2

    # ── Connect ──────────────────────────────────────────────────────────
    try:
        client = BybitClient(environment=args.env)
    except Exception as exc:
        print(f"[ERR] BybitClient({args.env}) failed: {exc}", file=sys.stderr)
        return 3
    if not client.has_credentials():
        print(f"[ERR] No credentials configured for {args.env}", file=sys.stderr)
        return 3

    print(f"[{args.env}] base_url={client.base_url()}")

    # ── Load instrument specs (required for place_order rounding/validation)
    # ── 載入品種規格（place_order 取整/驗證必需）
    try:
        n = client.refresh_instruments("linear")
        print(f"[{args.env}] loaded {n} linear instrument specs")
    except Exception as exc:
        print(f"[ERR] refresh_instruments failed: {exc}", file=sys.stderr)
        return 6

    # ── List positions ───────────────────────────────────────────────────
    try:
        positions = client.get_positions("linear")
    except Exception as exc:
        print(f"[ERR] get_positions failed: {exc}", file=sys.stderr)
        return 4

    open_pos = [p for p in positions if float(p.get("size", 0) or 0) > 0]
    print(f"[{args.env}] open positions: {len(open_pos)}")
    for p in open_pos:
        print(f"  • {p.get('symbol')} {p.get('side')} size={p.get('size')} "
              f"unrealPnL={p.get('unrealisedPnl')}")

    # ── List open orders ─────────────────────────────────────────────────
    try:
        orders = client.get_active_orders("linear", None, "USDT")
    except Exception as exc:
        print(f"[WARN] get_active_orders failed: {exc}", file=sys.stderr)
        orders = []
    print(f"[{args.env}] open orders: {len(orders)}")

    if args.dry_run:
        print("[dry-run] no action taken")
        return 0

    if not open_pos and not orders:
        print(f"[{args.env}] ✅ already flat — nothing to do")
        return 0

    if not args.yes:
        resp = input(f"Proceed to flatten {len(open_pos)} positions + "
                     f"cancel {len(orders)} orders on {args.env}? [yes/NO]: ")
        if resp.strip().lower() != "yes":
            print("Aborted.")
            return 1

    # ── Cancel open orders ───────────────────────────────────────────────
    cancelled = 0
    for o in orders:
        sym = o.get("symbol")
        oid = o.get("orderId") or o.get("order_id")
        if not sym or not oid:
            continue
        try:
            client.cancel_order(sym, oid, "linear")
            cancelled += 1
            print(f"  cancelled order {sym} {oid}")
        except Exception as exc:
            print(f"  cancel {sym} {oid} failed: {exc}", file=sys.stderr)

    # ── Flatten positions (reduce_only market) ───────────────────────────
    closed = 0
    for p in open_pos:
        sym = p.get("symbol")
        size = float(p.get("size") or 0)
        side = p.get("side")
        if size <= 0 or side not in ("Buy", "Sell"):
            continue
        close_side = "Sell" if side == "Buy" else "Buy"
        try:
            r = client.place_order(
                symbol=sym,
                side=close_side,
                order_type="Market",
                qty=size,
                category="linear",
                reduce_only=True,
            )
            closed += 1
            print(f"  closed {sym} {side}->{close_side} qty={size}: "
                  f"order_id={r.get('order_id') or r.get('orderId')}")
        except Exception as exc:
            print(f"  close {sym} failed: {exc}", file=sys.stderr)

    print(f"[{args.env}] cancelled {cancelled}/{len(orders)} orders, "
          f"closed {closed}/{len(open_pos)} positions")

    # ── Verify (loop-retry + residual sweep) ─────────────────────────────
    remaining: list = []
    for attempt in range(5):
        time.sleep(3)
        try:
            remaining = [p for p in client.get_positions("linear")
                         if float(p.get("size", 0) or 0) > 0]
        except Exception as exc:
            print(f"[WARN] verify attempt {attempt+1} failed: {exc}",
                  file=sys.stderr)
            continue
        if not remaining:
            break
        # Residual qty (rounding dust) — sweep with reduce_only again
        # 殘尾數量（取整殘餘）— 再次 reduce_only 掃尾
        print(f"  attempt {attempt+1}: {len(remaining)} residual, sweeping...")
        for p in remaining:
            sym = p.get("symbol")
            size = float(p.get("size") or 0)
            side = p.get("side")
            if size <= 0 or side not in ("Buy", "Sell"):
                continue
            close_side = "Sell" if side == "Buy" else "Buy"
            try:
                client.place_order(
                    symbol=sym, side=close_side, order_type="Market",
                    qty=size, category="linear", reduce_only=True,
                )
                print(f"    swept {sym} {size}")
            except Exception as exc:
                print(f"    sweep {sym} failed: {exc}", file=sys.stderr)
    if remaining:
        print(f"[ERR] {len(remaining)} positions still open after 5 sweeps: "
              f"{[p.get('symbol') for p in remaining]}", file=sys.stderr)
        return 5
    print(f"[{args.env}] ✅ 0 open positions confirmed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
