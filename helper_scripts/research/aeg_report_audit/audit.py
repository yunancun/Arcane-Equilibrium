"""Read-only advisory audit for PM reports, AEG artifacts, and M4 drafts.

The audit is a gap detector, not a promotion engine. It borrows the useful
idea of report rigor/falsification checklists while preserving TradeBot's
authority boundary: no order, risk, live, DB, or runtime authority is granted.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

AUDIT_SCHEMA_VERSION = "tradebot.aeg_report_audit.v1"
RUNNER_VERSION = "aeg_report_audit.v1"
ADVISORY_STATUSES = ("advisory_pass", "audit_gap", "insufficient_evidence", "citation_missing")

_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_])[-+]?\d+(?:\.\d+)?(?:\s*(?:%|bps|USDT|rows|passed|failed|ms|s|m|h|d|days))?",
    re.IGNORECASE,
)
_UNIT_RE = re.compile(r"(?:%|bps|usdt|rows|passed|failed|ms|s|m|h|d|days)\b", re.IGNORECASE)
_FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bpromotion_ready\b", "promotion_ready"),
    (r"\bstage0_ready\b", "stage0_ready"),
    (r"\bapprove_trade\b", "approve_trade"),
    (r"\bapprove\s+trading\b", "approve trading"),
    (r"\bpass\s+to\s+trading\b", "pass to trading"),
    (r"\border_capable_action_allowed\s*[:=]\s*true\b", "order_capable_action_allowed=true"),
    (r"\b(?:recommend|recommendation|signal)\s+(?:buy|sell)\b", "BUY/SELL recommendation"),
    (r"\bsizing\s+(?:recommendation|suggestion)\b", "sizing recommendation"),
)


@dataclass(frozen=True)
class ChecklistItem:
    item_id: str
    label: str
    terms: tuple[str, ...]
    severity: str
    hint: str


PROFILE_CHECKLISTS: dict[str, tuple[ChecklistItem, ...]] = {
    "pm_report": (
        ChecklistItem("source_lineage", "Source lineage", ("sha", "artifact", "path", "commit"), "high", "Cite source artifact paths and hashes."),
        ChecklistItem("decision_status", "Decision/status", ("status", "decision", "verdict", "blocked", "ready"), "medium", "State the review decision or blocker explicitly."),
        ChecklistItem("authority_boundary", "Authority boundary", ("no order", "order_authority_granted", "no bybit", "no pg", "advisory"), "high", "State no-order/no-runtime authority boundaries."),
        ChecklistItem("verification", "Verification evidence", ("verification", "pytest", "py_compile", "smoke", "passed"), "medium", "List the concrete checks that ran."),
        ChecklistItem("next_action", "Next action", ("next", "follow", "operator", "handoff"), "low", "Give the next bounded action or handoff."),
    ),
    "aeg_artifact": (
        ChecklistItem("candidate_identity", "Candidate identity", ("candidate_id", "candidate", "strategy_family", "parameter_cell_id"), "high", "Identify candidate, strategy family, and parameter cell."),
        ChecklistItem("sample_independence", "Independent sample", ("n_independent", "sample_unit", "non_overlapping", "overlap_adjusted"), "high", "Show independent sample count and unit."),
        ChecklistItem("oos_validation", "OOS validation", ("oos", "out-of-sample", "out of sample", "oos_start_date"), "high", "Show out-of-sample split or validation window."),
        ChecklistItem("psr", "PSR", ("psr", "psr_0"), "high", "Provide PSR evidence."),
        ChecklistItem("dsr", "DSR", ("dsr", "dsr_k"), "high", "Provide DSR evidence."),
        ChecklistItem("pbo", "PBO", ("pbo", "cscv"), "high", "Provide PBO or explicit insufficient-sample reason."),
        ChecklistItem("regime", "Regime segmentation", ("regime", "bull", "bear", "chop", "range"), "medium", "Break evidence out by regime where applicable."),
        ChecklistItem("breadth", "Breadth", ("breadth", "symbol_count", "min_symbols", "universe"), "medium", "Show symbol/event breadth."),
        ChecklistItem("costs", "Costs", ("fee", "fees", "slippage", "cost_bps", "round_trip_cost"), "high", "Include fees and slippage/cost assumptions."),
        ChecklistItem("freshness", "Freshness", ("freshness", "recent_90d", "recent_180d", "decay", "latest"), "medium", "Show recency/decay evidence."),
        ChecklistItem("authority_boundary", "Authority boundary", ("advisory_only", "order_authority_granted", "promotion_proof", "no_order"), "high", "Keep artifact advisory/no-order."),
    ),
    "m4_hypothesis": (
        ChecklistItem("hypothesis_identity", "Hypothesis identity", ("hypothesis", "draft", "status", "pattern"), "medium", "Identify the hypothesis and draft state."),
        ChecklistItem("sample_floor", "Sample floor", ("n_observations", "sample", "n >=", "n>=", "n_independent"), "high", "Show sample count and floor."),
        ChecklistItem("leak_free_shift", "Leak-free shift", ("shift(1)", "shift1", "leak-free", "leak_free", "1 preceding"), "high", "Show current bar exclusion / shift(1)."),
        ChecklistItem("oos_forward_window", "Forward/OOS window", ("forward", "oos", "out-of-sample", "holdout"), "high", "Show forward label or OOS validation."),
        ChecklistItem("bonferroni", "Bonferroni", ("bonferroni", "alpha_corrected", "2e-5", "p_corrected"), "high", "Show multiple-testing correction."),
        ChecklistItem("effect_size", "Effect size", ("cohen", "effect_size", "cohens_d"), "medium", "Show effect size gate."),
        ChecklistItem("replicability", "Replicability", ("subperiod", "replicability", "stability", "graveyard"), "medium", "Show sub-period stability or graveyard check."),
        ChecklistItem("authority_boundary", "Authority boundary", ("preregistered", "exploratory", "not live", "no order"), "high", "Do not promote past M4 allowed draft/preregistered state."),
    ),
}


def authority_flags() -> dict[str, bool]:
    return {
        "advisory_only": True,
        "proof_authority": False,
        "promotion_authority": False,
        "order_authority_granted": False,
        "risk_config_authority": False,
        "runtime_mutation_authority": False,
        "bybit_access": False,
        "db_access": False,
    }


def _load_payload(path: Path) -> tuple[str, Any | None, str | None]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        try:
            return text, json.loads(text), None
        except json.JSONDecodeError as exc:
            return text, None, f"{exc.msg} at line {exc.lineno} column {exc.colno}"
    return text, None, None


def _flatten_json(value: Any) -> str:
    if isinstance(value, Mapping):
        parts: list[str] = []
        for key, item in value.items():
            parts.append(str(key))
            parts.append(_flatten_json(item))
        return " ".join(parts)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return " ".join(_flatten_json(item) for item in value)
    return "" if value is None else str(value)


def _document_text(raw_text: str, json_payload: Any | None) -> str:
    if json_payload is not None:
        return f"{raw_text}\n{_flatten_json(json_payload)}"
    return raw_text


def _term_present(text: str, terms: Sequence[str]) -> bool:
    low = text.lower()
    return any(term.lower() in low for term in terms)


def _checklist(profile: str, text: str) -> list[dict[str, Any]]:
    items = PROFILE_CHECKLISTS[profile]
    rows: list[dict[str, Any]] = []
    for item in items:
        passed = _term_present(text, item.terms)
        rows.append({
            "item_id": item.item_id,
            "label": item.label,
            "status": "PASS" if passed else "MISSING",
            "severity": item.severity,
            "terms": list(item.terms),
            "hint": item.hint,
        })
    return rows


def _finding(
    *,
    finding_id: str,
    finding_type: str,
    severity: str,
    source_path: Path,
    message: str,
    line: int | None = None,
    hint: str | None = None,
) -> dict[str, Any]:
    if finding_type not in ADVISORY_STATUSES:
        raise ValueError(f"unsupported_finding_type:{finding_type}")
    return {
        "finding_id": finding_id,
        "finding_type": finding_type,
        "severity": severity,
        "source_path": str(source_path),
        "line": line,
        "line_start": line,
        "line_end": line,
        "line_span": [line, line] if line is not None else None,
        "message": message,
        "hint": hint,
        "authority": authority_flags(),
    }


def _checklist_findings(profile: str, checklist: Sequence[Mapping[str, Any]], path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in checklist:
        if row.get("status") != "MISSING":
            continue
        findings.append(_finding(
            finding_id=f"missing_{profile}_{row['item_id']}",
            finding_type="insufficient_evidence",
            severity=str(row["severity"]),
            source_path=path,
            message=f"{profile} checklist missing: {row['label']}",
            hint=str(row.get("hint") or ""),
        ))
    return findings


def _has_citation_context(line: str) -> bool:
    low = line.lower()
    markers = (
        "sha",
        "artifact",
        "path",
        "http",
        "](",
        "`",
        "/tmp/",
        ".json",
        ".md",
        "commit",
        "pytest",
        "py_compile",
        "passed",
        "failed",
        "verification",
    )
    return any(marker in low for marker in markers)


def _mostly_date_or_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("|---") or stripped.startswith("---"):
        return True
    if re.fullmatch(r"[#\-\s]*\d{4}-\d{2}-\d{2}.*", stripped):
        return True
    return False


def _numeric_claim_findings(raw_text: str, path: Path, *, max_findings: int = 12) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw_text.splitlines(), start=1):
        if _mostly_date_or_heading(line):
            continue
        matches = list(_NUMBER_RE.finditer(line))
        if not matches:
            continue
        if _has_citation_context(line):
            continue
        if not _UNIT_RE.search(line):
            findings.append(_finding(
                finding_id="numeric_claim_missing_unit",
                finding_type="audit_gap",
                severity="low",
                source_path=path,
                line=line_no,
                message="Numeric claim lacks an explicit unit.",
                hint="Add a unit such as bps, %, USDT, rows, days, or tie the value to a cited artifact.",
            ))
        findings.append(_finding(
            finding_id="numeric_claim_without_source_lineage",
            finding_type="citation_missing",
            severity="medium",
            source_path=path,
            line=line_no,
            message="Numeric claim lacks obvious source path/hash/test citation on the same line.",
            hint="Add artifact path, sha/hash, test command, or explicit source lineage.",
        ))
        if len(findings) >= max_findings:
            break
    return findings


def _forbidden_vocabulary_findings(raw_text: str, path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw_text.splitlines(), start=1):
        for pattern, label in _FORBIDDEN_PATTERNS:
            if not re.search(pattern, line, flags=re.IGNORECASE):
                continue
            findings.append(_finding(
                finding_id="forbidden_authority_vocabulary",
                finding_type="audit_gap",
                severity="high",
                source_path=path,
                line=line_no,
                message=f"Forbidden advisory-audit vocabulary found: {label}",
                hint="Rewrite as a blocker/advisory gap; do not emit trade, promotion, or sizing language.",
            ))
    return findings


def _authority_contamination_findings(text: str, path: Path) -> list[dict[str, Any]]:
    low = text.lower()
    bad_markers = (
        "order_authority_granted=true",
        '"order_authority_granted": true',
        '"order_capable_action_allowed": true',
        "promotion_authority=true",
        '"promotion_authority": true',
        '"promotion_proof": true',
        '"proof_authority": true',
        '"risk_config_authority": true',
        '"bybit_access": true',
        '"db_access": true',
        "live_authority_granted=true",
        '"runtime_mutation_authority": true',
    )
    findings: list[dict[str, Any]] = []
    for marker in bad_markers:
        if marker in low:
            findings.append(_finding(
                finding_id="authority_contamination",
                finding_type="audit_gap",
                severity="high",
                source_path=path,
                message=f"Authority marker is unsafe for this advisory audit: {marker}",
                hint="Keep audit artifacts advisory-only and route authority through Governance/Rust paths.",
            ))
    return findings


def _malformed_json_finding(path: Path, parse_error: str) -> dict[str, Any]:
    return _finding(
        finding_id="malformed_json_artifact",
        finding_type="audit_gap",
        severity="high",
        source_path=path,
        message=f"JSON artifact could not be parsed: {parse_error}",
        hint="Fix JSON syntax before treating machine artifact content as evidence.",
    )


def _walk_json(value: Any, prefix: str = "$") -> Iterable[tuple[str, Any]]:
    yield prefix, value
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk_json(item, f"{prefix}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for idx, item in enumerate(value):
            yield from _walk_json(item, f"{prefix}[{idx}]")


def _numeric_json_findings(json_payload: Any, path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for json_path, value in _walk_json(json_payload):
        low_path = json_path.lower()
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            if not math.isfinite(float(value)):
                findings.append(_finding(
                    finding_id="numeric_value_not_finite",
                    finding_type="audit_gap",
                    severity="high",
                    source_path=path,
                    message=f"JSON numeric value is NaN/Inf at {json_path}.",
                    hint="Replace NaN/Inf with null plus explicit insufficient-evidence reason.",
                ))
            if low_path.endswith("_pct_fraction") and float(value) > 1.0:
                findings.append(_finding(
                    finding_id="percentage_fraction_unit_confusion",
                    finding_type="audit_gap",
                    severity="high",
                    source_path=path,
                    message=f"Fraction field exceeds 1.0 at {json_path}.",
                    hint="Use 0.1 for 10% fraction fields; reserve 10.0 for explicit percentage fields.",
                ))
            continue
        if isinstance(value, str):
            low_value = value.strip().lower()
            if low_value in {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}:
                findings.append(_finding(
                    finding_id="numeric_value_not_finite",
                    finding_type="audit_gap",
                    severity="high",
                    source_path=path,
                    message=f"JSON numeric text is NaN/Inf at {json_path}.",
                    hint="Use null plus explicit insufficient-evidence reason.",
                ))
            if low_path.endswith("_usdt") and "%" in value:
                findings.append(_finding(
                    finding_id="usdt_percent_unit_confusion",
                    finding_type="audit_gap",
                    severity="high",
                    source_path=path,
                    message=f"USDT field contains percent text at {json_path}.",
                    hint="Separate percentage and notional fields.",
                ))
            if low_path.endswith("_pct") and "usdt" in low_value:
                findings.append(_finding(
                    finding_id="percent_usdt_unit_confusion",
                    finding_type="audit_gap",
                    severity="high",
                    source_path=path,
                    message=f"Percent field contains USDT text at {json_path}.",
                    hint="Separate percentage and notional fields.",
                ))
    return findings


def _authority_json_findings(json_payload: Any, path: Path) -> list[dict[str, Any]]:
    unsafe_true_keys = {
        "order_authority_granted",
        "order_capable_action_allowed",
        "promotion_authority",
        "promotion_proof",
        "proof_authority",
        "risk_config_authority",
        "runtime_mutation_authority",
        "bybit_access",
        "db_access",
        "live_authority_granted",
    }
    findings: list[dict[str, Any]] = []
    for json_path, value in _walk_json(json_payload):
        key = json_path.rsplit(".", 1)[-1]
        if key in unsafe_true_keys and value is True:
            findings.append(_finding(
                finding_id="authority_contamination",
                finding_type="audit_gap",
                severity="high",
                source_path=path,
                message=f"Unsafe authority flag is true at {json_path}.",
                hint="Advisory audit artifacts must keep authority/promotion/order/runtime flags false.",
            ))
    return findings


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_ref(base_path: Path, raw: Any) -> Path | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = base_path.parent / candidate
    return candidate


def _hash_reference_findings(json_payload: Any, path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for json_path, value in _walk_json(json_payload):
        if not isinstance(value, Mapping):
            continue
        pairs = (
            ("source_path", "source_sha256"),
            ("artifact_path", "artifact_sha256"),
            ("path", "sha256"),
        )
        for path_key, sha_key in pairs:
            if path_key not in value or sha_key not in value:
                continue
            ref = _resolve_ref(path, value.get(path_key))
            expected = str(value.get(sha_key) or "").strip().lower()
            if not ref or not expected:
                continue
            if not ref.exists() or not ref.is_file():
                findings.append(_finding(
                    finding_id="referenced_artifact_missing",
                    finding_type="audit_gap",
                    severity="high",
                    source_path=path,
                    message=f"Referenced artifact is missing at {json_path}.{path_key}: {ref}",
                    hint="Use an existing local artifact path before relying on the referenced hash.",
                ))
                continue
            actual = _sha256(ref)
            if actual != expected:
                findings.append(_finding(
                    finding_id="artifact_sha_mismatch",
                    finding_type="audit_gap",
                    severity="high",
                    source_path=path,
                    message=f"Referenced artifact hash mismatch at {json_path}.{sha_key}.",
                    hint=f"Expected {expected}, actual {actual} for {ref}.",
                ))
    return findings


def _status_from_findings(findings: Sequence[Mapping[str, Any]]) -> str:
    if not findings:
        return "advisory_pass"
    types = {str(row.get("finding_type") or "audit_gap") for row in findings}
    if types == {"citation_missing"}:
        return "citation_missing"
    if "audit_gap" in types:
        return "audit_gap"
    if "insufficient_evidence" in types:
        return "insufficient_evidence"
    return "audit_gap"


def _severity_counts(findings: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter = Counter(str(row.get("severity") or "unknown") for row in findings)
    return dict(sorted(counter.items()))


def audit_path(path: Path, *, profile: str) -> dict[str, Any]:
    if profile not in PROFILE_CHECKLISTS:
        raise ValueError(f"unsupported_profile:{profile}")
    p = Path(path)
    raw_text, json_payload, parse_error = _load_payload(p)
    text = _document_text(raw_text, json_payload)
    checklist = _checklist(profile, text)
    findings = []
    if parse_error is not None:
        findings.append(_malformed_json_finding(p, parse_error))
    findings.extend(_checklist_findings(profile, checklist, p))
    if json_payload is None:
        findings.extend(_numeric_claim_findings(raw_text, p))
    else:
        findings.extend(_numeric_json_findings(json_payload, p))
        findings.extend(_authority_json_findings(json_payload, p))
        findings.extend(_hash_reference_findings(json_payload, p))
    findings.extend(_forbidden_vocabulary_findings(raw_text, p))
    findings.extend(_authority_contamination_findings(text, p))
    status = _status_from_findings(findings)
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "profile": profile,
        "input_path": str(p),
        "input_suffix": p.suffix.lower(),
        "json_parse_ok": json_payload is not None,
        "json_parse_error": parse_error,
        "status": status,
        "checklist": checklist,
        "finding_count": len(findings),
        "severity_counts": _severity_counts(findings),
        "authority": authority_flags(),
        "advisory_statuses": list(ADVISORY_STATUSES),
        "falsification_ready": status == "advisory_pass",
        "promotion_evidence": False,
        "findings": findings,
    }


def audit_many(paths: Sequence[Path], *, profile: str) -> dict[str, Any]:
    audits = [audit_path(path, profile=profile) for path in paths]
    findings = [finding for audit in audits for finding in audit["findings"]]
    status = _status_from_findings(findings)
    ready_count = sum(1 for audit in audits if audit["status"] == "advisory_pass")
    return {
        "schema_version": "tradebot.aeg_report_audit.batch.v1",
        "runner_version": RUNNER_VERSION,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "profile": profile,
        "input_count": len(audits),
        "ready_count": ready_count,
        "status": status,
        "finding_count": len(findings),
        "severity_counts": _severity_counts(findings),
        "authority": authority_flags(),
        "advisory_statuses": list(ADVISORY_STATUSES),
        "falsification_ready": status == "advisory_pass",
        "promotion_evidence": False,
        "audits": audits,
    }


def markdown_summary(batch: Mapping[str, Any]) -> str:
    lines = [
        "# AEG Report Audit",
        "",
        f"- schema: `{batch.get('schema_version')}`",
        f"- profile: `{batch.get('profile')}`",
        f"- status: `{batch.get('status')}`",
        f"- inputs: `{batch.get('input_count')}`",
        f"- findings: `{batch.get('finding_count')}`",
        f"- advisory_only: `{str((batch.get('authority') or {}).get('advisory_only')).lower()}`",
        f"- order_authority_granted: `{str((batch.get('authority') or {}).get('order_authority_granted')).lower()}`",
        f"- promotion_evidence: `{str(batch.get('promotion_evidence')).lower()}`",
        "",
        "## Findings",
    ]
    findings = [
        finding
        for audit in batch.get("audits") or []
        for finding in audit.get("findings") or []
    ]
    if not findings:
        lines.append("- none")
    else:
        for finding in findings[:50]:
            line = finding.get("line")
            loc = f"{finding.get('source_path')}:{line}" if line else str(finding.get("source_path"))
            lines.append(
                f"- `{finding.get('severity')}` `{finding.get('finding_id')}` {loc} - {finding.get('message')}"
            )
    return "\n".join(lines) + "\n"


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
