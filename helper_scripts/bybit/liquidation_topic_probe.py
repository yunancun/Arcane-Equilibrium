#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────
# MODULE_NOTE
# 模組目的：W-AUDIT-8a C1 的 Bybit 公共 WS 強平 topic 隔離探針。
#          只連接 public market-data WebSocket，不讀 secrets，不寫 DB，
#          不改 production 訂閱列表。正式 C1 proof 需要 24h 連續觀察；
#          短跑只能證明探針可執行，不能解除 C1 gate。
#
# 使用方式：
#   python3 helper_scripts/bybit/liquidation_topic_probe.py --dry-run
#   python3 helper_scripts/bybit/liquidation_topic_probe.py --duration-sec 60
#   python3 helper_scripts/bybit/liquidation_topic_probe.py --duration-sec 86400
#
# Exit codes:
#   0 = 探針完成且未偵測 poison；若 duration < 86400，仍不是 C1 proof
#   1 = topic rejection / handler not found / rate-limit / canary silent
#   2 = dependency / network / runtime fatal error
# ─────────────────────────────────────────────────────────
"""Bybit liquidation topic standalone probe for W-AUDIT-8a C1.

The script intentionally uses an isolated public WS connection. It must never
be imported by production runtime topic builders.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_URL = "wss://stream.bybit.com/v5/public/linear"
DEFAULT_TOPIC = "allLiquidation.BTCUSDT"
DEFAULT_CANARY_SYMBOL = "BTCUSDT"
OFFICIAL_DOC_URL = "https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation"
CONTROL_TEMPLATES = (
    "tickers.{symbol}",
    "orderbook.50.{symbol}",
    "publicTrade.{symbol}",
    "kline.1.{symbol}",
)
POISON_PATTERNS = (
    "handler not found",
    "too many visits",
    "rate limit",
    "rate-limit",
    "access too frequent",
    "rejected",
)


@dataclass
class ProbeStats:
    started_at_utc: str
    finished_at_utc: str | None = None
    url: str = DEFAULT_URL
    candidate_topic: str = DEFAULT_TOPIC
    control_topics: list[str] = field(default_factory=list)
    duration_sec_requested: int = 0
    duration_sec_observed: float = 0.0
    subscribe_success_count: int = 0
    subscribe_failure_count: int = 0
    pings_sent: int = 0
    pongs_seen: int = 0
    raw_message_count: int = 0
    topic_message_counts: dict[str, int] = field(default_factory=dict)
    last_seen_by_topic_utc: dict[str, str] = field(default_factory=dict)
    candidate_samples: list[dict[str, Any]] = field(default_factory=list)
    poison_events: list[str] = field(default_factory=list)
    connection_errors: list[str] = field(default_factory=list)
    verdict: str = "UNKNOWN"
    c1_proof_eligible: bool = False
    c1_blocker: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_output_dir() -> Path:
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / "audit" / "liquidation_topic_probe"


def build_topics(candidate_topic: str, canary_symbol: str) -> list[str]:
    topics = [candidate_topic]
    topics.extend(t.format(symbol=canary_symbol) for t in CONTROL_TEMPLATES)
    seen: set[str] = set()
    deduped: list[str] = []
    for topic in topics:
        if topic not in seen:
            seen.add(topic)
            deduped.append(topic)
    return deduped


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an isolated Bybit public WS liquidation-topic probe.",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--canary-symbol", default=DEFAULT_CANARY_SYMBOL)
    parser.add_argument("--duration-sec", type=int, default=86_400)
    parser.add_argument("--recv-timeout-sec", type=float, default=5.0)
    parser.add_argument("--ping-interval-sec", type=float, default=20.0)
    parser.add_argument("--proof-min-duration-sec", type=int, default=86_400)
    parser.add_argument("--output-dir", type=Path, default=_default_output_dir())
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def classify_payload(payload: dict[str, Any], stats: ProbeStats) -> None:
    stats.raw_message_count += 1

    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    lower_text = text.lower()
    if any(pattern in lower_text for pattern in POISON_PATTERNS):
        stats.poison_events.append(text[:1000])

    success = payload.get("success")
    if success is True:
        stats.subscribe_success_count += 1
    elif success is False:
        stats.subscribe_failure_count += 1

    if payload.get("op") == "pong" or payload.get("ret_msg") == "pong":
        stats.pongs_seen += 1

    topic = payload.get("topic")
    if isinstance(topic, str):
        stats.topic_message_counts[topic] = stats.topic_message_counts.get(topic, 0) + 1
        stats.last_seen_by_topic_utc[topic] = _utc_now()
        if topic == stats.candidate_topic and len(stats.candidate_samples) < 5:
            stats.candidate_samples.append(payload)


def run_probe(args: argparse.Namespace) -> ProbeStats:
    try:
        import websocket  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        stats = ProbeStats(
            started_at_utc=_utc_now(),
            url=args.url,
            candidate_topic=args.topic,
            control_topics=build_topics(args.topic, args.canary_symbol)[1:],
            duration_sec_requested=args.duration_sec,
        )
        stats.connection_errors.append(f"websocket-client unavailable: {exc}")
        stats.verdict = "FATAL_DEPENDENCY_MISSING"
        stats.c1_blocker = "Install websocket-client in the runtime environment."
        return stats

    topics = build_topics(args.topic, args.canary_symbol)
    stats = ProbeStats(
        started_at_utc=_utc_now(),
        url=args.url,
        candidate_topic=args.topic,
        control_topics=topics[1:],
        duration_sec_requested=args.duration_sec,
        topic_message_counts={topic: 0 for topic in topics},
    )

    start = time.monotonic()
    try:
        ws = websocket.create_connection(args.url, timeout=args.recv_timeout_sec)
    except Exception as exc:  # noqa: BLE001
        stats.connection_errors.append(f"connect failed: {type(exc).__name__}: {exc}")
        stats.verdict = "FATAL_CONNECT_FAILED"
        stats.c1_blocker = "Probe could not establish the isolated public WS connection."
        return stats

    try:
        ws.send(json.dumps({"op": "subscribe", "args": topics}))
        next_ping = time.monotonic() + args.ping_interval_sec
        while time.monotonic() - start < args.duration_sec:
            now = time.monotonic()
            if now >= next_ping:
                ws.send(json.dumps({"op": "ping"}))
                stats.pings_sent += 1
                next_ping = now + args.ping_interval_sec

            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as exc:  # noqa: BLE001
                stats.connection_errors.append(f"recv failed: {type(exc).__name__}: {exc}")
                break

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                stats.connection_errors.append(f"non-json message: {raw[:200]}")
                continue
            if isinstance(payload, dict):
                classify_payload(payload, stats)
    finally:
        try:
            ws.close()
        except Exception:
            pass

    stats.duration_sec_observed = time.monotonic() - start
    stats.finished_at_utc = _utc_now()
    assess(stats, args)
    return stats


def assess(stats: ProbeStats, args: argparse.Namespace) -> None:
    stats.c1_proof_eligible = stats.duration_sec_observed >= args.proof_min_duration_sec

    if stats.poison_events:
        stats.verdict = "FAIL_TOPIC_POISON"
        stats.c1_blocker = "Bybit returned a poison/rejection/rate-limit message."
        return
    if stats.connection_errors:
        stats.verdict = "FAIL_CONNECTION"
        stats.c1_blocker = "The isolated WS connection did not complete the requested window."
        return

    control_seen = {
        topic: stats.topic_message_counts.get(topic, 0) > 0 for topic in stats.control_topics
    }
    all_control_seen = all(control_seen.values()) if control_seen else False
    any_control_seen = any(control_seen.values()) if control_seen else False

    if stats.c1_proof_eligible:
        if not all_control_seen:
            stats.verdict = "FAIL_CANARY_SILENT"
            missing = [topic for topic, seen in control_seen.items() if not seen]
            stats.c1_blocker = f"Control topics silent during proof window: {missing}"
            return
        stats.verdict = "PASS_C1_PROOF_CANDIDATE"
        stats.c1_blocker = None
        return

    if not any_control_seen:
        stats.verdict = "FAIL_SMOKE_CANARY_SILENT"
        stats.c1_blocker = "Short smoke saw no control-market data."
        return

    stats.verdict = "SMOKE_PASS_NOT_C1_PROOF"
    stats.c1_blocker = "Duration shorter than 24h; keep C1 blocked until full proof."


def render_markdown(stats: ProbeStats) -> str:
    result = asdict(stats)
    lines = [
        "# Bybit Liquidation Topic Probe",
        "",
        f"- Generated: `{_utc_now()}`",
        f"- Verdict: `{stats.verdict}`",
        f"- C1 proof eligible: `{stats.c1_proof_eligible}`",
        f"- C1 blocker: `{stats.c1_blocker or 'none'}`",
        f"- URL: `{stats.url}`",
        f"- Candidate topic: `{stats.candidate_topic}`",
        f"- Official docs: {OFFICIAL_DOC_URL}",
        f"- Requested duration sec: `{stats.duration_sec_requested}`",
        f"- Observed duration sec: `{stats.duration_sec_observed:.1f}`",
        f"- Subscribe success/failure: `{stats.subscribe_success_count}` / `{stats.subscribe_failure_count}`",
        f"- Ping/pong: `{stats.pings_sent}` / `{stats.pongs_seen}`",
        "",
        "## Topic Counts",
        "",
        "| Topic | Count | Last seen UTC |",
        "|---|---:|---|",
    ]
    for topic, count in sorted(stats.topic_message_counts.items()):
        last_seen = stats.last_seen_by_topic_utc.get(topic, "")
        lines.append(f"| `{topic}` | {count} | `{last_seen}` |")

    if stats.poison_events:
        lines.extend(["", "## Poison Events", ""])
        for event in stats.poison_events[:10]:
            lines.append(f"- `{event}`")

    if stats.connection_errors:
        lines.extend(["", "## Connection Errors", ""])
        for error in stats.connection_errors[:10]:
            lines.append(f"- `{error}`")

    if stats.candidate_samples:
        lines.extend(["", "## Candidate Samples", "", "```json"])
        lines.append(json.dumps(stats.candidate_samples, ensure_ascii=False, indent=2, sort_keys=True))
        lines.append("```")

    lines.extend(["", "## Raw JSON", "", "```json"])
    lines.append(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    lines.append("```")
    return "\n".join(lines) + "\n"


def write_reports(stats: ProbeStats, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    latest_json = output_dir / "liquidation_topic_probe_latest.json"
    dated_json = output_dir / f"liquidation_topic_probe_{stamp}.json"
    latest_md = output_dir / "liquidation_topic_probe_latest.md"
    dated_md = output_dir / f"liquidation_topic_probe_{stamp}.md"

    payload = json.dumps(asdict(stats), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(stats)
    for path in (latest_json, dated_json):
        path.write_text(payload, encoding="utf-8")
    for path in (latest_md, dated_md):
        path.write_text(markdown, encoding="utf-8")
    return latest_md, dated_md


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    topics = build_topics(args.topic, args.canary_symbol)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "url": args.url,
                    "candidate_topic": args.topic,
                    "control_topics": topics[1:],
                    "duration_sec": args.duration_sec,
                    "official_doc_url": OFFICIAL_DOC_URL,
                    "note": "dry-run only; no WS connection opened",
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    stats = run_probe(args)
    latest_md, dated_md = write_reports(stats, args.output_dir)
    print(f"verdict={stats.verdict}")
    print(f"latest_report={latest_md}")
    print(f"dated_report={dated_md}")
    if stats.verdict.startswith("PASS") or stats.verdict.startswith("SMOKE_PASS"):
        return 0
    if stats.verdict.startswith("FATAL"):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
