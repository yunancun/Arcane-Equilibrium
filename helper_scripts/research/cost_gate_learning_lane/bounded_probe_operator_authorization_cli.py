#!/usr/bin/env python3
"""CLI for bounded Demo probe operator-authorization packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.bounded_probe_operator_authorization import (
    DEFAULT_MAX_ARTIFACT_AGE_HOURS,
    DEFAULT_MAX_AUTHORIZATION_TTL_HOURS,
    build_bounded_demo_probe_operator_authorization,
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def render_markdown(packet: dict[str, Any]) -> str:
    candidate = _dict(packet.get("candidate"))
    fields = [
        ("Generated", packet.get("generated_at_utc")),
        ("Status", packet.get("status")),
        ("Decision", packet.get("decision")),
        ("Operator", packet.get("operator_id")),
        ("Authorization id", packet.get("authorization_id")),
        ("Side-cell", candidate.get("side_cell_key")),
        ("Max authorized probe orders", packet.get("requested_max_authorized_probe_orders")),
        ("Expires at", packet.get("expires_at_utc")),
    ]
    lines = [
        "# Bounded Demo Probe Operator Authorization",
        "",
        *[f"- {label}: `{value}`" for label, value in fields],
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Authorization Phrase",
        "",
        f"`{packet.get('typed_confirm_expected')}`",
        "",
        "## Gates",
        "",
        "| gate | passed | status | reason |",
        "|---|---:|---|---|",
    ]
    for gate in packet.get("gates") or []:
        lines.append(
            f"| {gate.get('name')} | `{gate.get('passed')}` | "
            f"`{gate.get('status')}` | {gate.get('reason')} |"
        )
    lines.extend(["", "## Next Actions", ""])
    for action in packet.get("next_actions") or []:
        lines.append(f"- `{action}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-json", type=Path)
    parser.add_argument("--placement-repair-plan-json", type=Path)
    parser.add_argument("--authority-patch-readiness-json", type=Path)
    parser.add_argument("--decision", choices=["defer", "reject", "authorize"], default="defer")
    parser.add_argument("--operator-id")
    parser.add_argument("--authorization-id")
    parser.add_argument("--max-authorized-probe-orders", type=int)
    parser.add_argument("--expires-at-utc")
    parser.add_argument("--typed-confirm")
    parser.add_argument("--review-note")
    parser.add_argument("--max-artifact-age-hours", type=int, default=DEFAULT_MAX_ARTIFACT_AGE_HOURS)
    parser.add_argument(
        "--max-authorization-ttl-hours",
        type=int,
        default=DEFAULT_MAX_AUTHORIZATION_TTL_HOURS,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_read_json(args.preflight_json),
        placement_repair_plan=_read_json(args.placement_repair_plan_json),
        authority_patch_readiness=_read_json(args.authority_patch_readiness_json),
        decision=args.decision,
        operator_id=args.operator_id,
        authorization_id=args.authorization_id,
        max_authorized_probe_orders=args.max_authorized_probe_orders,
        expires_at_utc=args.expires_at_utc,
        typed_confirm=args.typed_confirm,
        review_note=args.review_note,
        paths={
            "preflight": args.preflight_json,
            "placement_repair_plan": args.placement_repair_plan_json,
            "authority_patch_readiness": args.authority_patch_readiness_json,
        },
        max_artifact_age_hours=args.max_artifact_age_hours,
        max_authorization_ttl_hours=args.max_authorization_ttl_hours,
    )
    markdown = render_markdown(packet)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    if args.print_json:
        print(json.dumps(packet, sort_keys=True))
    if not args.output and not args.json_output and not args.print_json:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
