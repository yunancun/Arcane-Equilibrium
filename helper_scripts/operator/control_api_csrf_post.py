#!/usr/bin/env python3
"""Secret-safe curl wrapper for CSRF-protected Control API POSTs.

The helper exists to prevent ad hoc POST invocations from leaking bearer tokens
or accidentally omitting the CSRF cookie. It does not grant authority. Exchange
or session mutation paths are denied by default and require an explicit reviewed
mutation flag plus exact path binding.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse


DEFAULT_API_BASE = "http://100.91.109.86:8000"
APPROVED_API_BASES = {
    "http://100.91.109.86:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
}
DEFAULT_TOKEN_FILE = (
    "program_code/exchange_connectors/bybit_connector/control_api_v1/.secrets/"
    "api_token"
)
REVIEWED_WRITE_TOKEN = "reviewed_pm_control_api_write"
REVIEWED_MUTATION_TOKEN = "reviewed_e3_bb_pm_exchange_mutation"
SAFE_PROBE_PREFIX = "/api/v1/__csrf_probe_"
SENSITIVE_EXACT_PATHS = {
    "/api/v1/strategy/demo/close-all-positions",
    "/api/v1/strategy/demo/session/start",
    "/api/v1/strategy/demo/session/stop",
    "/api/v1/strategy/demo/session/resume",
    "/api/v1/strategy/demo/session/pause",
    "/api/v1/paper/session/stop",
    "/api/v1/paper/session/stop-all",
    "/api/v1/live/session/stop",
    "/api/v1/live/close-all-positions",
}
SENSITIVE_PREFIXES = (
    "/api/v1/live/",
    "/api/v1/strategy/demo/positions/",
)


class ConfigError(ValueError):
    """User-facing configuration error."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def normalize_api_base(value: str) -> str:
    base = (value or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ConfigError("api base must start with http:// or https://")
    parsed = urlparse(base)
    if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ConfigError("api base must not include auth, path, query, or fragment")
    if base not in APPROVED_API_BASES:
        approved = ", ".join(sorted(APPROVED_API_BASES))
        raise ConfigError(f"api base is not approved for token-bearing POSTs: {approved}")
    return base


def normalize_path(value: str) -> str:
    path = (value or "").strip()
    if not path.startswith("/api/v1/"):
        raise ConfigError("path must be an absolute /api/v1/... path")
    if "://" in path or "\\" in path or any(ch.isspace() for ch in path):
        raise ConfigError("path must not contain a URL scheme, backslash, or whitespace")
    if "?" in path or "#" in path:
        raise ConfigError("path must not contain query strings or fragments")
    if "%" in path:
        raise ConfigError("path must not contain percent-encoded segments")
    segments = path.split("/")
    if any(segment in {".", ".."} for segment in segments):
        raise ConfigError("path must not contain dot segments")
    if any(segment == "" for segment in segments[1:]):
        raise ConfigError("path must not contain empty path segments")
    return path


def is_sensitive_path(path: str) -> bool:
    return path in SENSITIVE_EXACT_PATHS or any(
        path.startswith(prefix) for prefix in SENSITIVE_PREFIXES
    )


def mutation_allowed(args: argparse.Namespace, path: str) -> bool:
    if path.startswith(SAFE_PROBE_PREFIX):
        return True
    if not (
        args.allow_reviewed_write == REVIEWED_WRITE_TOKEN
        and args.reviewed_path == path
        and bool((args.reviewed_change_id or "").strip())
    ):
        return False
    if not is_sensitive_path(path):
        return True
    return (
        args.allow_reviewed_mutation == REVIEWED_MUTATION_TOKEN
        and args.reviewed_path == path
        and bool((args.reviewed_change_id or "").strip())
    )


def resolve_token(args: argparse.Namespace) -> str:
    token = (os.environ.get("OPENCLAW_API_TOKEN") or "").strip()
    if not token:
        token_file = Path(args.token_file)
        if not token_file.is_absolute():
            token_file = repo_root() / token_file
        try:
            token = token_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigError(f"cannot read API token file: {token_file}") from exc
    validate_header_value("API token", token)
    return token


def validate_header_value(name: str, value: str) -> None:
    if not value:
        raise ConfigError(f"{name} is empty")
    if any(ch in value for ch in {'"', "\\", "\n", "\r"}):
        raise ConfigError(f"{name} contains unsupported characters")


def build_curl_config(
    *,
    api_base: str,
    path: str,
    token: str,
    csrf_token: str,
    connect_timeout: int,
    max_time: int,
    data: str | None,
) -> str:
    validate_header_value("API token", token)
    validate_header_value("CSRF token", csrf_token)
    lines = [
        f'url = "{api_base}{path}"',
        'request = "POST"',
        f'header = "Authorization: Bearer {token}"',
        f'header = "X-CSRF-Token: {csrf_token}"',
        f'cookie = "oc_csrf={csrf_token}"',
        f"connect-timeout = {int(connect_timeout)}",
        f"max-time = {int(max_time)}",
        "silent",
        "show-error",
    ]
    if data is not None:
        validate_header_value("Content-Type", "application/json")
        lines.append('header = "Content-Type: application/json"')
        lines.append(f"data-raw = {json.dumps(data)}")
    return "\n".join(lines) + "\n"


def read_body(args: argparse.Namespace) -> str | None:
    if args.data and args.data_file:
        raise ConfigError("use --data or --data-file, not both")
    if args.data_file:
        return Path(args.data_file).read_text(encoding="utf-8")
    if args.data is not None:
        return args.data
    return None


def response_summary(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"json": False}
    if not isinstance(payload, dict):
        return {"json": True, "object": False}
    detail = payload.get("detail")
    reason_codes = None
    if isinstance(detail, dict):
        reason_codes = detail.get("reason_codes")
    data = payload.get("data")
    return {
        "json": True,
        "object": True,
        "status": payload.get("status"),
        "detail_reason_codes": reason_codes,
        "data_status": data.get("status") if isinstance(data, dict) else None,
        "closed_all": data.get("closed_all") if isinstance(data, dict) else None,
        "partial_failure": data.get("partial_failure") if isinstance(data, dict) else None,
    }


def parse_expected_http(values: Sequence[str]) -> set[int]:
    expected: set[int] = set()
    for value in values:
        for part in str(value).split(","):
            text = part.strip()
            if not text:
                continue
            try:
                code = int(text)
            except ValueError as exc:
                raise ConfigError(f"invalid --expect-http value: {text!r}") from exc
            if code < 100 or code > 599:
                raise ConfigError(f"invalid --expect-http status: {code}")
            expected.add(code)
    return expected


def http_status_ok(status: str, expected: set[int]) -> bool:
    try:
        code = int(str(status).strip())
    except ValueError:
        return False
    if expected:
        return code in expected
    return 200 <= code <= 299


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--path", required=True)
    parser.add_argument("--token-file", default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--data")
    parser.add_argument("--data-file")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument("--max-time", type=int, default=120)
    parser.add_argument("--expect-http", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-reviewed-write", default="")
    parser.add_argument("--allow-reviewed-mutation", default="")
    parser.add_argument("--reviewed-path", default="")
    parser.add_argument("--reviewed-change-id", default="")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        api_base = normalize_api_base(args.api_base)
        path = normalize_path(args.path)
        if not mutation_allowed(args, path):
            raise ConfigError(
                "control API POST requires either a /api/v1/__csrf_probe_* path "
                f"or --allow-reviewed-write {REVIEWED_WRITE_TOKEN!r}, "
                "--reviewed-path, and --reviewed-change-id; exchange-sensitive "
                "paths also require --allow-reviewed-mutation "
                f"{REVIEWED_MUTATION_TOKEN!r}"
            )
        expected_http = parse_expected_http(args.expect_http)
        body = read_body(args)
        token = resolve_token(args)
        csrf_token = secrets.token_urlsafe(32)
        curl_config = build_curl_config(
            api_base=api_base,
            path=path,
            token=token,
            csrf_token=csrf_token,
            connect_timeout=args.connect_timeout,
            max_time=args.max_time,
            data=body,
        )
    except ConfigError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2

    summary = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "path": path,
        "sensitive_path": is_sensitive_path(path),
        "uses_curl_cookie_engine": 'cookie = "oc_csrf=' in curl_config,
        "uses_raw_cookie_header": 'header = "Cookie:' in curl_config,
        "output": str(args.output),
        "expected_http": sorted(expected_http),
    }
    if args.dry_run:
        print(json.dumps(summary, sort_keys=True))
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False) as cfg:
        cfg_path = Path(cfg.name)
        cfg.write(curl_config)
    os.chmod(cfg_path, stat.S_IRUSR | stat.S_IWUSR)
    try:
        proc = subprocess.run(
            [
                "curl",
                "--config",
                str(cfg_path),
                "--output",
                str(args.output),
                "--write-out",
                "%{http_code}",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.max_time + 10,
            check=False,
        )
    finally:
        try:
            cfg_path.unlink()
        except FileNotFoundError:
            pass
    http_status = proc.stdout.strip()
    http_ok = http_status_ok(http_status, expected_http)
    summary.update(
        {
            "curl_returncode": proc.returncode,
            "http_status": http_status,
            "http_status_ok": http_ok,
            "stderr_present": bool(proc.stderr.strip()),
            "response": response_summary(args.output),
        }
    )
    summary["ok"] = proc.returncode == 0 and http_ok
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["ok"] is True else 1


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
