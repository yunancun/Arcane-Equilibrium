#!/usr/bin/env python3
"""REF-21 V058/V059 one-shot backfill helper.

Default mode is dry-run. Use --apply only after reviewing the printed counts.
The script writes only REF-21 governance/replay data:

- V058 market.symbol_universe_snapshots from Bybit public instruments-info.
- V058 governance.strategy_freeze_log from current repo/config hashes.
- V059 learning.edge_estimate_snapshots from settings/edge_estimates*.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATEGORIES = ("linear",)
DEFAULT_INSTRUMENT_STATUSES = ("Trading", "PreLaunch", "Delivering", "Closed")
BYBIT_PUBLIC_BASE = "https://api.bybit.com"
INSTRUMENTS_ENDPOINT = "/v5/market/instruments-info"
V058_SYMBOL_RE = re.compile(r"^[A-Z0-9_.]{1,32}$")


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    db: str
    user: str
    password: str


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> bytes:
    return hashlib.sha256(value).digest()


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_ms_datetime(value: Any) -> datetime | None:
    if value in (None, "", "0", 0):
        return None
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def parse_iso_datetime(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("timestamp cannot be empty")
    if raw.isdigit():
        dt = datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
    else:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_numeric(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def read_db_config(base: Path = REPO_ROOT) -> DbConfig:
    env_file = base / "settings/environment_files/basic_system_services.env"
    values: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return DbConfig(
        host=os.environ.get("PG_HOST") or values.get("POSTGRES_HOST") or "127.0.0.1",
        port=int(os.environ.get("PG_PORT") or values.get("POSTGRES_PORT") or "5432"),
        db=os.environ.get("PG_DB") or values.get("POSTGRES_DB") or "trading_ai",
        user=os.environ.get("PG_USER") or values.get("POSTGRES_USER") or "trading_admin",
        password=os.environ.get("PG_PASSWORD") or values.get("POSTGRES_PASSWORD") or "",
    )


def connect_db(config: DbConfig):
    import psycopg2  # type: ignore[import]

    return psycopg2.connect(
        host=config.host,
        port=config.port,
        dbname=config.db,
        user=config.user,
        password=config.password,
        connect_timeout=5,
    )


def fetch_instruments(
    category: str,
    *,
    base_url: str,
    rps: float,
    status: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor = ""
    sleep_s = 1.0 / max(rps, 0.1)
    while True:
        params = {"category": category, "limit": "1000"}
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        url = base_url.rstrip("/") + INSTRUMENTS_ENDPOINT + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "OpenClaw-REF21-backfill/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15.0) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("retCode") != 0:
            raise RuntimeError(
                "bybit_instruments_info_error:"
                + str(payload.get("retMsg") or payload.get("retCode"))
            )
        result = payload.get("result") or {}
        rows.extend(result.get("list") or [])
        cursor = str(result.get("nextPageCursor") or "")
        if not cursor:
            break
        time.sleep(sleep_s)
    return rows


def instrument_snapshot_rows(
    *,
    category: str,
    instruments: Iterable[dict[str, Any]],
    asof: datetime,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    source_params = {"category": category}
    if status_filter:
        source_params["status"] = status_filter
    source_uri = (
        "bybit-public://v5/market/instruments-info?"
        + urllib.parse.urlencode(source_params)
    )
    rows: list[dict[str, Any]] = []
    for item in instruments:
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol or not V058_SYMBOL_RE.match(symbol):
            continue
        status = str(item.get("status") or "unknown")
        lot = item.get("lotSizeFilter") or {}
        price = item.get("priceFilter") or {}
        delivery = parse_ms_datetime(item.get("deliveryTime"))
        payload_hash = sha256_bytes(canonical_json_bytes(item))
        rows.append({
            "ts": asof,
            "exchange": "bybit",
            "category": category,
            "symbol": symbol,
            "status": status,
            "base_coin": item.get("baseCoin"),
            "quote_coin": item.get("quoteCoin"),
            "contract_type": item.get("contractType"),
            "tick_size": parse_numeric(price.get("tickSize")),
            "qty_step": parse_numeric(lot.get("qtyStep")),
            "min_notional": parse_numeric(
                lot.get("minNotionalValue") or lot.get("minOrderAmt")
            ),
            "listed_at": parse_ms_datetime(item.get("launchTime")),
            "delisted_at": delivery,
            "is_delisted_at_asof": status.lower() in {"settled", "delisted", "closed"},
            "source_uri": source_uri,
            "payload_hash": payload_hash,
            "payload_jsonb": item,
        })
    return rows


def existing_file_hash(paths: Iterable[Path]) -> bytes:
    h = hashlib.sha256()
    found = False
    for path in sorted(paths):
        if not path.exists():
            continue
        found = True
        h.update(str(path.relative_to(REPO_ROOT)).encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    if not found:
        h.update(b"missing")
    return h.digest()


def git_sha(base: Path = REPO_ROOT) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=base,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        out = "0" * 40
    return out


def freeze_row(asof: datetime, *, actor: str) -> dict[str, Any]:
    settings = REPO_ROOT / "settings"
    day = asof.date().isoformat()
    return {
        "freeze_tag": f"freeze/{day}",
        "freeze_date": asof.date(),
        "strategy_git_sha": git_sha(),
        "strategy_config_hash": existing_file_hash(settings.glob("strategy_params_*.toml")),
        "scanner_config_hash": existing_file_hash([
            settings / "risk_control_rules/scanner_config.toml",
        ]),
        "risk_config_hash": existing_file_hash(
            (settings / "risk_control_rules").glob("risk_config*.toml")
        ),
        "created_by": actor,
        "payload_jsonb": {"source": "ref21_backfill_v058_v059.py"},
    }


def source_tier_for_edge_file(path: Path) -> str:
    name = path.name
    if "live_demo" in name:
        return "live_demo_latest_json"
    if "live" in name:
        return "live_latest_json"
    if "paper" in name:
        return "paper_isolated_json"
    return "demo_latest_json"


def parse_edge_snapshot_file(path: Path) -> tuple[datetime, dict[str, Any], list[dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} is not a JSON object")
    meta = raw.get("_meta") if isinstance(raw.get("_meta"), dict) else {}
    updated_at = meta.get("updated_at") if isinstance(meta, dict) else None
    try:
        asof = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        if asof.tzinfo is None:
            asof = asof.replace(tzinfo=timezone.utc)
    except Exception:
        asof = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    rows: list[dict[str, Any]] = []
    for key, cell in raw.items():
        if key.startswith("_") or "::" not in key or not isinstance(cell, dict):
            continue
        strategy, symbol = key.split("::", 1)
        if not strategy or not symbol:
            continue
        payload = dict(cell)
        payload_hash = sha256_bytes(canonical_json_bytes(payload))
        rows.append({
            "asof_ts": asof,
            "source_tier": source_tier_for_edge_file(path),
            "config_hash": existing_file_hash(REPO_ROOT.glob("settings/strategy_params_*.toml")),
            "strategy_hash": sha256_bytes(strategy.encode("utf-8")),
            "scanner_config_hash": existing_file_hash([
                REPO_ROOT / "settings/risk_control_rules/scanner_config.toml",
            ]),
            "symbol": symbol.upper(),
            "strategy": strategy,
            "regime_key": str(payload.get("regime_key") or "global"),
            "cell_key": str(payload.get("cell_key") or "default"),
            "estimate_payload_hash": payload_hash,
            "estimate_payload_jsonb": payload,
            "is_deprecated_at_asof": False,
            "deprecated_reason": None,
            "retention_until": asof + timedelta(days=90),
        })
    return asof, meta if isinstance(meta, dict) else {}, rows


def insert_symbol_universe(conn: Any, rows: list[dict[str, Any]]) -> int:
    from psycopg2.extras import Json, execute_batch  # type: ignore[import]

    if not rows:
        return 0
    sql = """
    INSERT INTO market.symbol_universe_snapshots (
        ts, exchange, category, symbol, status, base_coin, quote_coin,
        contract_type, tick_size, qty_step, min_notional, listed_at,
        delisted_at, is_delisted_at_asof, source_uri, payload_hash, payload_jsonb
    ) VALUES (
        %(ts)s, %(exchange)s, %(category)s, %(symbol)s, %(status)s,
        %(base_coin)s, %(quote_coin)s, %(contract_type)s, %(tick_size)s,
        %(qty_step)s, %(min_notional)s, %(listed_at)s, %(delisted_at)s,
        %(is_delisted_at_asof)s, %(source_uri)s, %(payload_hash)s,
        %(payload_jsonb)s
    )
    ON CONFLICT DO NOTHING;
    """
    payload = [{**row, "payload_jsonb": Json(row["payload_jsonb"])} for row in rows]
    with conn.cursor() as cur:
        execute_batch(cur, sql, payload, page_size=500)
    return len(rows)


def insert_freeze_log(conn: Any, row: dict[str, Any]) -> int:
    from psycopg2.extras import Json  # type: ignore[import]

    sql = """
    INSERT INTO governance.strategy_freeze_log (
        freeze_tag, freeze_date, strategy_git_sha, strategy_config_hash,
        scanner_config_hash, risk_config_hash, created_by, payload_jsonb
    ) VALUES (
        %(freeze_tag)s, %(freeze_date)s, %(strategy_git_sha)s,
        %(strategy_config_hash)s, %(scanner_config_hash)s, %(risk_config_hash)s,
        %(created_by)s, %(payload_jsonb)s
    )
    ON CONFLICT (freeze_tag) DO NOTHING;
    """
    with conn.cursor() as cur:
        cur.execute(sql, {**row, "payload_jsonb": Json(row["payload_jsonb"])})
        return cur.rowcount


def insert_edge_snapshots(conn: Any, rows: list[dict[str, Any]]) -> int:
    from psycopg2.extras import Json, execute_batch  # type: ignore[import]

    if not rows:
        return 0
    sql = """
    INSERT INTO learning.edge_estimate_snapshots (
        asof_ts, source_tier, config_hash, strategy_hash, scanner_config_hash,
        symbol, strategy, regime_key, cell_key, estimate_payload_hash,
        estimate_payload_jsonb, is_deprecated_at_asof, deprecated_reason,
        retention_until
    ) VALUES (
        %(asof_ts)s, %(source_tier)s, %(config_hash)s, %(strategy_hash)s,
        %(scanner_config_hash)s, %(symbol)s, %(strategy)s, %(regime_key)s,
        %(cell_key)s, %(estimate_payload_hash)s, %(estimate_payload_jsonb)s,
        %(is_deprecated_at_asof)s, %(deprecated_reason)s, %(retention_until)s
    )
    ON CONFLICT DO NOTHING;
    """
    payload = [
        {**row, "estimate_payload_jsonb": Json(row["estimate_payload_jsonb"])}
        for row in rows
    ]
    with conn.cursor() as cur:
        execute_batch(cur, sql, payload, page_size=500)
    return len(rows)


def existing_edge_files(base: Path = REPO_ROOT) -> list[Path]:
    settings = base / "settings"
    candidates = [
        settings / "edge_estimates.json",
        settings / "edge_estimates_live_demo.json",
        settings / "edge_estimates_live.json",
        settings / "edge_estimates_paper.json",
    ]
    return [path for path in candidates if path.exists()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write rows to PG")
    parser.add_argument(
        "--categories",
        default=",".join(DEFAULT_CATEGORIES),
        help="comma-separated Bybit categories to snapshot, default linear",
    )
    parser.add_argument(
        "--instrument-statuses",
        default=",".join(DEFAULT_INSTRUMENT_STATUSES),
        help=(
            "comma-separated instruments-info status values to fetch. "
            "Default Trading,PreLaunch,Delivering,Closed for linear public snapshots."
        ),
    )
    parser.add_argument(
        "--asof",
        default=None,
        help=(
            "snapshot timestamp as ISO-8601 or epoch ms. Use replay window end "
            "for a one-shot historical bootstrap; default is current UTC time."
        ),
    )
    parser.add_argument(
        "--freeze-asof",
        default=None,
        help=(
            "strategy freeze-log timestamp as ISO-8601 or epoch ms. Defaults "
            "to current UTC time; keep this separate from --asof when writing "
            "a bootstrap universe snapshot for an older replay window."
        ),
    )
    parser.add_argument(
        "--edge-json",
        action="append",
        default=None,
        help="edge_estimates JSON file; repeatable. Defaults to settings files that exist.",
    )
    parser.add_argument("--skip-instruments", action="store_true")
    parser.add_argument("--skip-freeze-log", action="store_true")
    parser.add_argument("--skip-edge", action="store_true")
    parser.add_argument("--actor", default="ref21_backfill")
    parser.add_argument("--base-url", default=BYBIT_PUBLIC_BASE)
    parser.add_argument("--rps", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(tz=timezone.utc)
    snapshot_asof = parse_iso_datetime(args.asof) if args.asof else now
    freeze_asof = parse_iso_datetime(args.freeze_asof) if args.freeze_asof else now
    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    statuses = [s.strip() for s in args.instrument_statuses.split(",") if s.strip()]
    edge_paths = [Path(p) for p in args.edge_json] if args.edge_json else existing_edge_files()

    universe_rows: list[dict[str, Any]] = []
    if not args.skip_instruments:
        seen_symbols: set[tuple[str, str]] = set()
        for category in categories:
            for status in statuses:
                instruments = fetch_instruments(
                    category,
                    base_url=args.base_url,
                    rps=args.rps,
                    status=status,
                )
                rows = instrument_snapshot_rows(
                    category=category,
                    instruments=instruments,
                    asof=snapshot_asof,
                    status_filter=status,
                )
                new_rows: list[dict[str, Any]] = []
                for row in rows:
                    key = (str(row["category"]), str(row["symbol"]))
                    if key in seen_symbols:
                        continue
                    seen_symbols.add(key)
                    new_rows.append(row)
                universe_rows.extend(new_rows)
                print(
                    f"[v058] {category}/{status}: fetched={len(instruments)} "
                    f"parsed={len(rows)} deduped_new={len(new_rows)}"
                )
        print(
            "[v058] note: one-shot instruments-info backfill cannot recover "
            "symbols already absent from Bybit public instruments-info; durable "
            "historical coverage still requires recurring V058 snapshots."
        )

    freeze = None if args.skip_freeze_log else freeze_row(freeze_asof, actor=args.actor)
    if freeze:
        print(f"[v058] freeze_tag={freeze['freeze_tag']} git={freeze['strategy_git_sha'][:12]}")

    edge_rows: list[dict[str, Any]] = []
    if not args.skip_edge:
        for path in edge_paths:
            edge_asof, _meta, rows = parse_edge_snapshot_file(path)
            edge_rows.extend(rows)
            print(f"[v059] {path}: asof={edge_asof.isoformat()} cells={len(rows)}")

    print(
        "[summary] mode={} universe_rows={} freeze_rows={} edge_rows={}".format(
            "APPLY" if args.apply else "DRY_RUN",
            len(universe_rows),
            1 if freeze else 0,
            len(edge_rows),
        )
    )
    if not args.apply:
        return 0

    config = read_db_config()
    conn = connect_db(config)
    try:
        inserted_universe = insert_symbol_universe(conn, universe_rows)
        inserted_freeze = insert_freeze_log(conn, freeze) if freeze else 0
        inserted_edge = insert_edge_snapshots(conn, edge_rows)
        conn.commit()
        print(
            f"[applied] universe_attempted={inserted_universe} "
            f"freeze_inserted={inserted_freeze} edge_attempted={inserted_edge}"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
