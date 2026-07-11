"""Deterministic human projection for a validated governance closure."""

from __future__ import annotations

import json
from typing import Any

from agent_governance_closure import validate_closure


def _markdown_cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    elif value is None:
        rendered = ""
    else:
        rendered = str(value)
    return rendered.replace("|", "\\|").replace("\n", " ")


def project_closure(packet: dict[str, Any]) -> str:
    """Project one validated closure into a deterministic, lossless Markdown view."""

    errors = validate_closure(packet)
    if errors:
        raise ValueError("invalid closure_packet_v1: " + "; ".join(errors))
    summary = packet["human_summary"]
    lines = [
        f"# Closure: {_markdown_cell(packet['task_id'])}", "",
        f"Objective: {_markdown_cell(summary['objective'])}", "",
        f"Scope: {_markdown_cell(summary['scope'])}", "",
        f"Outcome: {_markdown_cell(summary['outcome'])}", "",
        "| Decision | Value |", "|---|---|",
        f"| Work status | `{_markdown_cell(packet['work_status'])}` |",
        f"| Gate verdict | `{_markdown_cell(packet['gate_verdict'])}` |",
        f"| Disposition | `{_markdown_cell(packet['disposition'])}` |",
        f"| Confidence | `{_markdown_cell(packet['confidence'])}` |", "",
        "## Acceptance", "", "| Criterion | Status | Evidence |", "|---|---|---|",
    ]
    for item in packet["acceptance"]:
        lines.append(
            f"| {_markdown_cell(item.get('criterion'))} | `{_markdown_cell(item.get('status'))}` | "
            f"{_markdown_cell(item.get('evidence_refs', []))} |"
        )
    lines.extend([
        "", "## Immutable role fragments", "",
        "| Fragment | Node | Role | Work | Gate | Class | Confidence | Summary | Concerns | Payload kind | Payload | Evidence |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ])
    for fragment in packet["role_fragments"]:
        lines.append(
            "| " + " | ".join(
                _markdown_cell(value) for value in (
                    fragment.get("id"), fragment.get("node_id"), fragment.get("role"),
                    fragment.get("work_status"), fragment.get("gate_verdict"),
                    fragment.get("classification"), fragment.get("confidence"),
                    fragment.get("summary"), fragment.get("concerns", []),
                    fragment.get("payload_kind"), fragment.get("payload"),
                    fragment.get("evidence_refs", []),
                )
            ) + " |"
        )
    lines.extend([
        "", "## Evidence index", "", "| ID | Scope | Kind | Digest | Observed |",
        "|---|---|---|---|---|",
    ])
    for evidence in packet["evidence"]:
        lines.append(
            "| " + " | ".join(
                _markdown_cell(value) for value in (
                    evidence.get("id"), evidence.get("scope"), evidence.get("kind"),
                    evidence.get("digest"), evidence.get("observed_at"),
                )
            ) + " |"
        )
    lines.extend([
        "", "## Residual state", "",
        f"- Unverified: `{_markdown_cell(packet['unverified'])}`",
        f"- Skipped roles: `{_markdown_cell(packet['skipped_roles'])}`",
        f"- Side effects: `{_markdown_cell(packet['side_effects'])}`",
        f"- Consumption: `{_markdown_cell(packet['consumption'])}`",
        f"- Next action: `{_markdown_cell(packet['next_action'])}`", "", "<details>",
        "<summary>Canonical closure_packet_v1</summary>", "", "```json",
        json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2), "```", "",
        "</details>", "",
    ])
    return "\n".join(lines)
