#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：Gate-B 自主窗口監控（alert-only）。它把 Bybit 官方 new_crypto 公告
  和 live PreLaunch instruments-info 轉成可審計 Gate-B 候選，輸出 latest artifact，
  並只在 fresh/future 可行窗口出現時發告警。

數據源：
  - GET /v5/announcements/index?locale=en-US&type=new_crypto&page=N&limit=50
  - GET /v5/market/instruments-info?category=linear&status=PreLaunch&limit=1000

硬邊界：
  - public GET only，無 credential / signing / order / DB / runtime mutation。
  - probe 自動啟動僅限 AMD-2026-07-10-01 授權範圍：sibling 模塊 gate_b_auto_capture
    （預設 OFF，OPENCLAW_GATE_B_AUTO_CAPTURE=1 啟用）對未來 5 個新上市自啟隔離探針，
    cap=5 持久化計數、cap 滿自動停；其餘情形維持 alert-only 行動提示。
  - 任何外部文本只進 artifact 或短告警摘要，不展開公告 description。
  - 拉取失敗 fail-soft exit 0；連續失敗達閾值才發 health meta-alert。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import alert_sink  # noqa: E402
import gate_b_auto_capture  # noqa: E402

logger = logging.getLogger("gate_b_watch")

API_HOST = "https://api.bybit.com"
ANNOUNCEMENTS_PATH = "/v5/announcements/index"
INSTRUMENTS_PATH = "/v5/market/instruments-info"
API_LOCALE = "en-US"
ANNOUNCEMENT_LIMIT = 50
PRELAUNCH_LIMIT = 1000

STATE_FILE = "gate_b_watch_state.json"
ARTIFACT_DIR = "gate_b_watch"
LATEST_FILE = "gate_b_watch_latest.json"
HISTORY_FILE = "gate_b_watch_history.jsonl"

DEFAULT_ANNOUNCEMENT_PAGES = 3
META_ALERT_AFTER_FAILURES = 8
MAX_ALERTS_PER_RUN = 8

ACTION_START_NOW = "START_GATE_B_NOW"
ACTION_SCHEDULE = "SCHEDULE_GATE_B_WINDOW"
ACTION_REVIEW = "OPERATOR_REVIEW"
ACTION_WATCH_CONVERSION = "WATCH_CONVERSION"
ACTION_STALE = "STALE_NO_ACTION"

STATUS_ACTIONABLE_START = "ACTIONABLE_START_NOW"
STATUS_ACTIONABLE_SCHEDULE = "ACTIONABLE_SCHEDULE"
STATUS_OPERATOR_REVIEW = "OPERATOR_REVIEW"
STATUS_WATCH_ONLY = "WATCH_ONLY"
STATUS_NO_CANDIDATE = "NO_ACTIONABLE_CANDIDATE"
STATUS_SOURCE_FAILURE = "SOURCE_FAILURE"

TRIGGER_PREMARKET_LISTING = "announcement_pre_market_listing"
TRIGGER_STANDARD_CONVERSION = "announcement_standard_conversion"
TRIGGER_PRELAUNCH_ACTIVE = "prelaunch_active"

PROBE_DURATION_SECONDS = 24 * 60 * 60

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
_SYMBOL_RE = re.compile(r"\b([A-Z0-9]{2,20}USDT)\b")
_PREMARKET_RE = re.compile(r"\bpre[- ]?(?:market|launch|listing)\b", re.IGNORECASE)
_PERPETUAL_RE = re.compile(r"\b(?:perpetual|derivatives?|futures?)\b", re.IGNORECASE)
_CONVERT_STANDARD_RE = re.compile(
    r"\bconvert(?:ing|ed|s)?\b.{0,120}\bstandard\s+perpetual\b|"
    r"\bstandard\s+perpetual\b.{0,120}\bconvert(?:ing|ed|s)?\b",
    re.IGNORECASE | re.DOTALL,
)
_PREIPO_RE = re.compile(r"\bpre[- ]?ipo\b", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_MONTH_RE = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
_BYBIT_TEXT_TIME_RE = re.compile(
    rf"\b(?:around\s+|on\s+)?(?P<month>{_MONTH_RE})\.?\s+"
    r"(?P<day>\d{1,2}),\s*(?P<year>20\d{2}),\s*"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>AM|PM)?\s*UTC\b",
    re.IGNORECASE,
)
_ISO_UTC_RE = re.compile(
    r"\b(?P<year>20\d{2})-(?P<month>\d{1,2})-(?P<day>\d{1,2})[ T]"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::\d{2})?\s*(?:UTC|Z)\b",
    re.IGNORECASE,
)


class FetchError(Exception):
    """單一 source 拉取失敗；caller fail-soft 處理。"""


def _env_float(name: str, default: float, *, lower: float, upper: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        value = default
    return max(lower, min(value, upper))


def _env_int(name: str, default: int, *, lower: int, upper: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(lower, min(value, upper))


def _iso_utc(seconds: float | int | None) -> str | None:
    if seconds is None:
        return None
    return dt.datetime.fromtimestamp(float(seconds), tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return _iso_utc(ms / 1000.0)


def _strip_control(text: Any) -> str:
    return _CONTROL_CHARS_RE.sub(" ", str(text or "")).strip()


def _plain_text(text: Any) -> str:
    return _strip_control(_HTML_TAG_RE.sub(" ", str(text or "")))


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, "", "0"):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _hash_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_url(url: Any) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parts = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return None
    if not parts.netloc:
        return None
    path = parts.path.rstrip("/") or "/"
    scheme = (parts.scheme or "https").lower()
    return f"{scheme}://{parts.netloc.lower()}{path}"


def _announcement_key(item: dict[str, Any]) -> str:
    norm = normalize_url(item.get("url"))
    if norm:
        return norm
    basis = {
        "locale": API_LOCALE,
        "title": _plain_text(item.get("title")),
        "publishTime": item.get("publishTime"),
    }
    return "sha256:" + _hash_json(basis)


def _symbols_from_text(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for symbol in _SYMBOL_RE.findall(text.upper()):
        if symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def parse_event_time_ms(text: str) -> int | None:
    """Parse common Bybit UTC text timestamps into epoch milliseconds."""
    m = _BYBIT_TEXT_TIME_RE.search(text)
    if m:
        month_key = m.group("month").lower().rstrip(".")
        month = _MONTHS.get(month_key[:3], _MONTHS.get(month_key))
        if month is None:
            return None
        hour = int(m.group("hour"))
        minute = int(m.group("minute") or "0")
        ampm = (m.group("ampm") or "").upper()
        if ampm == "PM" and hour != 12:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0
        try:
            parsed = dt.datetime(
                int(m.group("year")),
                month,
                int(m.group("day")),
                hour,
                minute,
                tzinfo=dt.timezone.utc,
            )
        except ValueError:
            return None
        return int(parsed.timestamp() * 1000)

    m = _ISO_UTC_RE.search(text)
    if m:
        try:
            parsed = dt.datetime(
                int(m.group("year")),
                int(m.group("month")),
                int(m.group("day")),
                int(m.group("hour")),
                int(m.group("minute")),
                tzinfo=dt.timezone.utc,
            )
        except ValueError:
            return None
        return int(parsed.timestamp() * 1000)
    return None


def _request_json(path: str, params: dict[str, Any], *, opener=None, timeout: float = 10.0) -> dict[str, Any]:
    opener = opener or alert_sink.urlopen_no_redirect
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{API_HOST}{path}?{query}",
        headers={"User-Agent": "openclaw-gate-b-watch/1.0"},
    )
    try:
        with opener(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"http_error {type(exc).__name__}: {exc}") from exc
    if status != 200:
        raise FetchError(f"http_status_{status}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise FetchError(f"parse_error: {exc}") from exc
    if not isinstance(payload, dict):
        raise FetchError("payload_not_dict")
    if payload.get("retCode") != 0:
        ret_msg = str(payload.get("retMsg", ""))[:120]
        raise FetchError(f"retCode={payload.get('retCode')!r} retMsg={ret_msg!r}")
    return payload


def fetch_new_crypto_announcements(*, pages: int, opener=None, timeout: float = 10.0) -> list[dict[str, Any]]:
    pages = max(1, min(int(pages), 10))
    out: list[dict[str, Any]] = []
    for page in range(1, pages + 1):
        payload = _request_json(
            ANNOUNCEMENTS_PATH,
            {
                "locale": API_LOCALE,
                "type": "new_crypto",
                "page": page,
                "limit": ANNOUNCEMENT_LIMIT,
            },
            opener=opener,
            timeout=timeout,
        )
        rows = (payload.get("result") or {}).get("list")
        if not isinstance(rows, list):
            raise FetchError("announcements.result.list_missing")
        page_items = [row for row in rows if isinstance(row, dict)]
        out.extend(page_items)
        if len(page_items) < ANNOUNCEMENT_LIMIT:
            break
    return out


def fetch_prelaunch_instruments(*, opener=None, timeout: float = 10.0) -> list[dict[str, Any]]:
    payload = _request_json(
        INSTRUMENTS_PATH,
        {
            "category": "linear",
            "status": "PreLaunch",
            "limit": PRELAUNCH_LIMIT,
        },
        opener=opener,
        timeout=timeout,
    )
    rows = (payload.get("result") or {}).get("list")
    if not isinstance(rows, list):
        raise FetchError("instruments.result.list_missing")
    return [row for row in rows if isinstance(row, dict)]


def _window_hints(event_time_ms: int | None, now: float) -> dict[str, Any]:
    pre_hours = _env_float("OPENCLAW_GATE_B_WATCH_PRE_WINDOW_HOURS", 6.0, lower=0.0, upper=48.0)
    if event_time_ms is None:
        return {
            "suggested_probe_start_utc": _iso_utc(now),
            "suggested_probe_duration_seconds": PROBE_DURATION_SECONDS,
            "event_window_basis": "missing_event_time_start_now_if_fresh",
        }
    start_seconds = max(now, event_time_ms / 1000.0 - pre_hours * 3600.0)
    return {
        "suggested_probe_start_utc": _iso_utc(start_seconds),
        "suggested_probe_duration_seconds": PROBE_DURATION_SECONDS,
        "event_window_basis": f"event_time_minus_{pre_hours:g}h",
    }


def _announcement_action(
    *,
    event_time_ms: int | None,
    publish_time_ms: int | None,
    now: float,
) -> tuple[str, str]:
    pre_hours = _env_float("OPENCLAW_GATE_B_WATCH_PRE_WINDOW_HOURS", 6.0, lower=0.0, upper=48.0)
    post_hours = _env_float("OPENCLAW_GATE_B_WATCH_POST_WINDOW_HOURS", 12.0, lower=1.0, upper=96.0)
    fresh_hours = _env_float("OPENCLAW_GATE_B_WATCH_FRESH_ANNOUNCEMENT_HOURS", 72.0, lower=1.0, upper=720.0)

    if event_time_ms is not None:
        delta_hours = event_time_ms / 1000.0 / 3600.0 - now / 3600.0
        if delta_hours < -post_hours:
            return ACTION_STALE, f"event_time_passed_by_{abs(delta_hours):.1f}h"
        if delta_hours <= pre_hours:
            return ACTION_START_NOW, f"inside_gate_b_start_window_delta_h={delta_hours:.1f}"
        return ACTION_SCHEDULE, f"future_event_delta_h={delta_hours:.1f}"

    if publish_time_ms is not None:
        age_hours = now / 3600.0 - publish_time_ms / 1000.0 / 3600.0
        if age_hours <= fresh_hours:
            return ACTION_START_NOW, f"fresh_announcement_without_event_time_age_h={age_hours:.1f}"
        return ACTION_STALE, f"announcement_without_event_time_age_h={age_hours:.1f}"
    return ACTION_REVIEW, "missing_publish_and_event_time"


def _prelaunch_action(row: dict[str, Any], now: float) -> tuple[str, str]:
    pre_hours = _env_float("OPENCLAW_GATE_B_WATCH_PRE_WINDOW_HOURS", 6.0, lower=0.0, upper=48.0)
    fresh_hours = _env_float("OPENCLAW_GATE_B_WATCH_FRESH_PRELAUNCH_HOURS", 72.0, lower=1.0, upper=720.0)
    phase_info = row.get("preListingInfo") if isinstance(row.get("preListingInfo"), dict) else {}
    cur_phase = _strip_control(phase_info.get("curAuctionPhase") or row.get("curAuctionPhase"))
    launch_time_ms = _safe_int(row.get("launchTime"))

    if cur_phase in {"CallAuction", "CallAuctionNoCancel", "CrossMatching"}:
        return ACTION_START_NOW, f"active_auction_phase={cur_phase}"

    if launch_time_ms is None:
        return ACTION_REVIEW, "prelaunch_missing_launch_time"

    delta_hours = launch_time_ms / 1000.0 / 3600.0 - now / 3600.0
    if delta_hours > pre_hours:
        return ACTION_SCHEDULE, f"future_launch_delta_h={delta_hours:.1f}"
    if delta_hours >= -fresh_hours:
        return ACTION_START_NOW, f"fresh_prelaunch_delta_h={delta_hours:.1f}"
    if cur_phase == "ContinuousTrading":
        return ACTION_WATCH_CONVERSION, f"old_continuous_prelaunch_age_h={abs(delta_hours):.1f}"
    return ACTION_REVIEW, f"old_prelaunch_unexpected_phase={cur_phase or 'unknown'}"


def _candidate_priority(action: str) -> str:
    if action in {ACTION_START_NOW, ACTION_SCHEDULE, ACTION_REVIEW}:
        return "P1"
    return "P2"


def _is_alertable(action: str) -> bool:
    return action in {ACTION_START_NOW, ACTION_SCHEDULE, ACTION_REVIEW}


def candidates_from_announcement(item: dict[str, Any], *, now: float) -> list[dict[str, Any]]:
    title = _plain_text(item.get("title"))
    description = _plain_text(item.get("description"))
    text = f"{title}\n{description}"
    tags = [str(t) for t in item.get("tags", []) if isinstance(t, str)]
    type_key = _strip_control(((item.get("type") or {}).get("key")) if isinstance(item.get("type"), dict) else "")

    is_premarket = bool(_PREMARKET_RE.search(text))
    is_perpetual = bool(_PERPETUAL_RE.search(text) or {"Derivatives", "Futures"} & set(tags))
    is_conversion = bool(_CONVERT_STANDARD_RE.search(text))
    is_preipo_review = bool(_PREIPO_RE.search(text))
    if not ((is_premarket and is_perpetual) or is_conversion or is_preipo_review):
        return []

    if is_conversion:
        trigger_type = TRIGGER_STANDARD_CONVERSION
    elif is_premarket:
        trigger_type = TRIGGER_PREMARKET_LISTING
    else:
        trigger_type = "announcement_preipo_review"

    publish_time_ms = _safe_int(item.get("publishTime") or item.get("dateTimestamp"))
    event_time_ms = parse_event_time_ms(text)
    action, reason = _announcement_action(
        event_time_ms=event_time_ms,
        publish_time_ms=publish_time_ms,
        now=now,
    )
    symbols = _symbols_from_text(text) or ["UNKNOWN"]
    article_key = _announcement_key(item)
    url = normalize_url(item.get("url")) or _strip_control(item.get("url"))
    candidates: list[dict[str, Any]] = []
    for symbol in symbols:
        candidate_key = f"announcement:{article_key}:{symbol}:{trigger_type}"
        fields = {
            "candidate_key": candidate_key,
            "symbol": symbol,
            "source": "announcements_new_crypto",
            "trigger_type": trigger_type,
            "priority": _candidate_priority(action),
            "recommended_action": action,
            "action_reason": reason,
            "should_alert": _is_alertable(action),
            "title": title[:300],
            "url": url,
            "type_key": type_key,
            "tags": tags[:20],
            "publish_time_utc": _ms_to_iso(publish_time_ms),
            "event_time_utc": _ms_to_iso(event_time_ms),
            "suggested_probe": _window_hints(event_time_ms, now) if _is_alertable(action) else None,
        }
        fields["fingerprint"] = _hash_json({
            "trigger_type": fields["trigger_type"],
            "symbol": fields["symbol"],
            "recommended_action": fields["recommended_action"],
            "event_time_utc": fields["event_time_utc"],
            "publish_time_utc": fields["publish_time_utc"],
        })
        candidates.append(fields)
    return candidates


def candidate_from_prelaunch(row: dict[str, Any], *, now: float) -> dict[str, Any] | None:
    symbol = _strip_control(row.get("symbol")).upper()
    if not symbol.endswith("USDT"):
        return None
    status = _strip_control(row.get("status"))
    launch_time_ms = _safe_int(row.get("launchTime"))
    phase_info = row.get("preListingInfo") if isinstance(row.get("preListingInfo"), dict) else {}
    cur_phase = _strip_control(phase_info.get("curAuctionPhase") or row.get("curAuctionPhase"))
    action, reason = _prelaunch_action(row, now)
    candidate = {
        "candidate_key": f"prelaunch:{symbol}",
        "symbol": symbol,
        "source": "market_instruments_info",
        "trigger_type": TRIGGER_PRELAUNCH_ACTIVE,
        "priority": _candidate_priority(action),
        "recommended_action": action,
        "action_reason": reason,
        "should_alert": _is_alertable(action),
        "status": status,
        "launch_time_utc": _ms_to_iso(launch_time_ms),
        "cur_auction_phase": cur_phase or None,
        "suggested_probe": _window_hints(launch_time_ms, now) if _is_alertable(action) else None,
    }
    candidate["fingerprint"] = _hash_json({
        "symbol": symbol,
        "status": status,
        "launch_time_utc": candidate["launch_time_utc"],
        "cur_auction_phase": candidate["cur_auction_phase"],
        "recommended_action": action,
    })
    return candidate


def build_candidates(
    announcements: list[dict[str, Any]],
    prelaunch_rows: list[dict[str, Any]],
    *,
    now: float,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in announcements:
        for candidate in candidates_from_announcement(item, now=now):
            key = candidate["candidate_key"]
            if key not in seen:
                seen.add(key)
                candidates.append(candidate)
    for row in prelaunch_rows:
        candidate = candidate_from_prelaunch(row, now=now)
        if candidate is None:
            continue
        key = candidate["candidate_key"]
        if key not in seen:
            seen.add(key)
            candidates.append(candidate)
    candidates.sort(
        key=lambda c: (
            0 if c.get("recommended_action") == ACTION_START_NOW else
            1 if c.get("recommended_action") == ACTION_SCHEDULE else
            2 if c.get("recommended_action") == ACTION_REVIEW else
            3,
            str(c.get("symbol") or ""),
            str(c.get("source") or ""),
        )
    )
    return candidates


def load_state(data_dir: str) -> dict[str, Any]:
    try:
        with open(Path(data_dir) / STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True, default=str)
        f.write("\n")
    os.replace(tmp, path)


def save_state(data_dir: str, state: dict[str, Any]) -> None:
    try:
        _atomic_write_json(Path(data_dir) / STATE_FILE, state)
    except OSError as exc:
        logger.warning("state save failed: %s", exc)


def _resolve_alert_fn():
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        import engine_watchdog  # noqa: PLC0415

        return engine_watchdog._send_alert_best_effort
    except Exception as exc:  # noqa: BLE001
        logger.warning("engine_watchdog emitter unavailable, alert no-op: %s", exc)
        return lambda subject, body, severity, data_dir: None


def _probe_command_hint(candidate: dict[str, Any]) -> str:
    symbol = _strip_control(candidate.get("symbol")) or "UNKNOWN"
    day = _strip_control((candidate.get("event_time_utc") or candidate.get("launch_time_utc") or "")[:10])
    suffix = day.replace("-", "") if day else "manual"
    run_id = f"gate_b_{symbol.lower()}_{suffix}"
    return (
        "python3 helper_scripts/research/aeg_gate_b_probe.py "
        f"--duration-seconds {PROBE_DURATION_SECONDS} --run-id {run_id}"
    )


def format_alert(candidate: dict[str, Any]) -> tuple[str, str]:
    symbol = _strip_control(candidate.get("symbol") or "UNKNOWN")
    action = _strip_control(candidate.get("recommended_action"))
    trigger = _strip_control(candidate.get("trigger_type"))
    subject = f"[GATE-B-WATCH][{candidate.get('priority', 'P1')}] {symbol} {trigger} -> {action}"
    body_lines = [
        f"symbol: {symbol}",
        f"trigger: {trigger}",
        f"recommended_action: {action}",
        f"reason: {_strip_control(candidate.get('action_reason'))[:240]}",
    ]
    title = _strip_control(candidate.get("title"))
    if title:
        body_lines.append(f"title: {title[:240]}")
    url = _strip_control(candidate.get("url"))
    if url:
        body_lines.append(f"url: {url[:300]}")
    if candidate.get("event_time_utc"):
        body_lines.append(f"event_time_utc: {candidate['event_time_utc']}")
    if candidate.get("launch_time_utc"):
        body_lines.append(f"launch_time_utc: {candidate['launch_time_utc']}")
    suggested = candidate.get("suggested_probe") if isinstance(candidate.get("suggested_probe"), dict) else {}
    if suggested.get("suggested_probe_start_utc"):
        body_lines.append(f"suggested_probe_start_utc: {suggested['suggested_probe_start_utc']}")
    body_lines.append(f"probe_command_hint: {_probe_command_hint(candidate)}")
    body_lines.append(
        "boundary: no trading/DB/runtime paths; probe autostart only under "
        "operator-authorized cap (AMD-2026-07-10-01, default OFF)."
    )
    return subject[:260], "\n".join(body_lines)


def _alert_candidates(
    data_dir: str,
    state: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    alert_fn=None,
    dry_run: bool,
    now: float,
    sleep_fn=time.sleep,
) -> int:
    seen = state.setdefault("seen_candidates", {})
    if not isinstance(seen, dict):
        seen = {}
        state["seen_candidates"] = seen

    alertable: list[dict[str, Any]] = []
    for candidate in candidates:
        key = candidate["candidate_key"]
        fingerprint = candidate["fingerprint"]
        entry = seen.setdefault(key, {"first_seen_at": now})
        entry["last_seen_at"] = now
        entry["last_recommended_action"] = candidate.get("recommended_action")
        entry["last_fingerprint"] = fingerprint
        entry["last_symbol"] = candidate.get("symbol")
        if not candidate.get("should_alert"):
            continue
        if entry.get("last_alerted_fingerprint") == fingerprint:
            continue
        alertable.append(candidate)

    alertable = alertable[:MAX_ALERTS_PER_RUN]
    if not alertable:
        return 0

    fn = alert_fn or _resolve_alert_fn()
    sent = 0
    for candidate in alertable:
        subject, body = format_alert(candidate)
        key = candidate["candidate_key"]
        if dry_run:
            print(f"DRY-RUN would alert: {subject}")
        else:
            try:
                fn(subject, body, "WARN", data_dir)
            except Exception as exc:  # noqa: BLE001
                logger.warning("alert send failed: %s", exc)
        seen[key]["last_alerted_fingerprint"] = candidate["fingerprint"]
        seen[key]["alerted_at"] = now
        sent += 1

    if sent and not dry_run:
        drain_seconds = _env_float("OPENCLAW_GATE_B_WATCH_ALERT_DRAIN_SECONDS", 6.0, lower=0.0, upper=30.0)
        sleep_fn(drain_seconds)
    return sent


def _artifact_status(candidates: list[dict[str, Any]], source_health: dict[str, Any]) -> str:
    if not source_health.get("announcements", {}).get("ok") and not source_health.get("prelaunch", {}).get("ok"):
        return STATUS_SOURCE_FAILURE
    actions = {
        c.get("recommended_action")
        for c in candidates
        if c.get("recommended_action") != ACTION_STALE
    }
    if ACTION_START_NOW in actions:
        return STATUS_ACTIONABLE_START
    if ACTION_SCHEDULE in actions:
        return STATUS_ACTIONABLE_SCHEDULE
    if ACTION_REVIEW in actions:
        return STATUS_OPERATOR_REVIEW
    if ACTION_WATCH_CONVERSION in actions:
        return STATUS_WATCH_ONLY
    return STATUS_NO_CANDIDATE


def _write_artifacts(
    data_dir: str,
    payload: dict[str, Any],
    *,
    append_history: bool = True,
) -> None:
    root = Path(data_dir) / ARTIFACT_DIR
    try:
        _atomic_write_json(root / LATEST_FILE, payload)
        if append_history:
            summary = {
                "generated_at_utc": payload.get("generated_at_utc"),
                "status": payload.get("status"),
                "candidate_count": payload.get("candidate_counts", {}).get("total"),
                "alertable_count": payload.get("candidate_counts", {}).get("alertable"),
                "alerts_sent": payload.get("alerts_sent"),
                "source_health": payload.get("source_health"),
            }
            with open(root / HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(summary, sort_keys=True, default=str) + "\n")
    except OSError as exc:
        logger.warning("artifact write failed: %s", exc)


def _failure_meta_alert(
    data_dir: str,
    state: dict[str, Any],
    *,
    error_text: str,
    alert_fn=None,
    dry_run: bool,
    now: float,
    sleep_fn=time.sleep,
) -> int:
    fails = int(state.get("consecutive_failures", 0) or 0) + 1
    state["consecutive_failures"] = fails
    state["last_failure_at"] = now
    if fails != META_ALERT_AFTER_FAILURES:
        return 0
    subject = "[GATE-B-WATCH][META] consecutive source failures"
    body = (
        f"gate_b_watch consecutive source failures={fails}; last_error={_strip_control(error_text)[:500]}\n"
        "action: check gate_b_watch_cron.log and Bybit public API reachability."
    )
    if dry_run:
        print(f"DRY-RUN would alert: {subject}")
    else:
        fn = alert_fn or _resolve_alert_fn()
        try:
            fn(subject, body, "WARN", data_dir)
            drain_seconds = _env_float("OPENCLAW_GATE_B_WATCH_ALERT_DRAIN_SECONDS", 6.0, lower=0.0, upper=30.0)
            sleep_fn(drain_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("meta-alert send failed: %s", exc)
    return 1


def run_once(
    data_dir: str,
    *,
    opener=None,
    alert_fn=None,
    now: float | None = None,
    dry_run: bool = False,
    announcement_pages: int | None = None,
    sleep_fn=time.sleep,
) -> int:
    now = time.time() if now is None else now
    timeout = _env_float("OPENCLAW_GATE_B_WATCH_HTTP_TIMEOUT_SECONDS", 10.0, lower=2.0, upper=30.0)
    pages = announcement_pages if announcement_pages is not None else _env_int(
        "OPENCLAW_GATE_B_WATCH_ANNOUNCEMENT_PAGES",
        DEFAULT_ANNOUNCEMENT_PAGES,
        lower=1,
        upper=10,
    )
    state = load_state(data_dir)

    announcements: list[dict[str, Any]] = []
    prelaunch_rows: list[dict[str, Any]] = []
    source_health: dict[str, Any] = {
        "announcements": {"ok": False, "count": 0, "pages": pages, "error": None},
        "prelaunch": {"ok": False, "count": 0, "error": None},
    }
    errors: list[str] = []

    try:
        announcements = fetch_new_crypto_announcements(pages=pages, opener=opener, timeout=timeout)
        source_health["announcements"].update({"ok": True, "count": len(announcements)})
    except FetchError as exc:
        source_health["announcements"]["error"] = str(exc)
        errors.append(f"announcements:{exc}")
        logger.warning("announcements fetch failed: %s", exc)

    try:
        prelaunch_rows = fetch_prelaunch_instruments(opener=opener, timeout=timeout)
        source_health["prelaunch"].update({"ok": True, "count": len(prelaunch_rows)})
    except FetchError as exc:
        source_health["prelaunch"]["error"] = str(exc)
        errors.append(f"prelaunch:{exc}")
        logger.warning("prelaunch fetch failed: %s", exc)

    candidates = build_candidates(announcements, prelaunch_rows, now=now)
    alerts_sent = 0
    if errors:
        alerts_sent += _failure_meta_alert(
            data_dir,
            state,
            error_text="; ".join(errors),
            alert_fn=alert_fn,
            dry_run=dry_run,
            now=now,
            sleep_fn=sleep_fn,
        )
    else:
        state["consecutive_failures"] = 0
        state["last_success_at"] = now

    alerts_sent += _alert_candidates(
        data_dir,
        state,
        candidates,
        alert_fn=alert_fn,
        dry_run=dry_run,
        now=now,
        sleep_fn=sleep_fn,
    )

    # 自動觸發（AMD-2026-07-10-01）：operator 已授權未來 5 個新上市自啟隔離 Gate-B capture。
    # 為什麼放在告警後、artifact 前：告警去重 state 不受影響；auto_capture 的計數 / audit
    # 結果要進本輪 latest artifact 與 state 落地。模塊自身 fail-soft，flag OFF 零副作用。
    auto_capture_summary = gate_b_auto_capture.maybe_auto_capture(
        data_dir,
        state,
        candidates,
        now=now,
        dry_run=dry_run,
        alert_fn=alert_fn,
        alert_resolver=_resolve_alert_fn,
        sleep_fn=sleep_fn,
    )

    payload = {
        "schema_version": 1,
        "generated_at_utc": _iso_utc(now),
        "status": _artifact_status(candidates, source_health),
        "source_health": source_health,
        "candidate_counts": {
            "total": len(candidates),
            "alertable": sum(1 for c in candidates if c.get("should_alert")),
            "start_now": sum(1 for c in candidates if c.get("recommended_action") == ACTION_START_NOW),
            "schedule": sum(1 for c in candidates if c.get("recommended_action") == ACTION_SCHEDULE),
            "watch_only": sum(1 for c in candidates if c.get("recommended_action") == ACTION_WATCH_CONVERSION),
        },
        "alerts_sent": alerts_sent,
        "probe_preconditions": [
            "fresh Bybit Pre-Market / PreLaunch / standard-conversion window exists",
            "run isolated helper_scripts/research/aeg_gate_b_probe.py for 24h",
            "do not connect production scanner/strategy/order/DB/runtime paths",
            "treat no transition as INCONCLUSIVE_NO_TRANSITION, not alpha evidence",
        ],
        "candidates": candidates,
        "auto_capture": auto_capture_summary,
        # 為什麼 boundary 隨 flag 分流：artifact 是審計面，措辭必須反映真實行為，
        # 不得在 auto-capture 啟用時仍宣稱 no probe autostart。
        "boundary": (
            "alert + operator-authorized bounded auto-capture "
            "(AMD-2026-07-10-01, cap=5); no trading/runtime/DB mutation"
            if auto_capture_summary.get("enabled")
            else "alert-only; auto-capture disabled; no trading/runtime/DB mutation"
        ),
    }
    _write_artifacts(data_dir, payload)
    save_state(data_dir, state)
    logger.info(
        "round done: status=%s candidates=%d alertable=%d alerts=%d source_errors=%d",
        payload["status"],
        len(candidates),
        payload["candidate_counts"]["alertable"],
        alerts_sent,
        len(errors),
    )
    return 0


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [GATE-B-WATCH] %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        prog="gate_b_watch",
        description="Gate-B public announcement + PreLaunch watcher (alert-only).",
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"),
        help="runtime data dir (default $OPENCLAW_DATA_DIR else /tmp/openclaw)",
    )
    parser.add_argument("--once", action="store_true", help="single cycle (default behavior)")
    parser.add_argument("--dry-run", action="store_true", help="run without sending alerts; state/artifacts still write")
    parser.add_argument(
        "--announcement-pages",
        type=int,
        default=None,
        help="new_crypto announcement pages to scan (default env or 3, max 10)",
    )
    args = parser.parse_args(argv)
    return run_once(
        args.data_dir,
        dry_run=args.dry_run,
        announcement_pages=args.announcement_pages,
    )


if __name__ == "__main__":
    sys.exit(main())
