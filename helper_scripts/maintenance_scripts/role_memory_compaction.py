#!/usr/bin/env python3
"""Reversible hot/cold compaction for development-role memory files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = "role_memory_compaction_manifest_v3"
LEGACY_SCHEMA_VERSION = "role_memory_compaction_manifest_v1"
INTERMEDIATE_SCHEMA_VERSION = "role_memory_compaction_manifest_v2"
POINTER_SCHEMA_VERSION = "role_memory_archive_pointer_v1"
PROMOTION_SCHEMA_VERSION = "role_memory_promotion_v2"
PROMOTION_AUTHORITY_SCHEMA_VERSION = "role_memory_promotion_authority_v1"
PROMOTION_ARCHIVE_SCHEMA_VERSION = "role_memory_promotion_archive_record_v2"
PROMOTION_AUTHORITY = "PM_CLOSURE"
PROMOTION_TRUST_TIER = "PLATFORM_OR_EXTERNAL_ATTESTED"
MANIFEST_PATH = Path("docs/agents/role-memory-compaction-v1.json")
MAX_HOT_LINES = 300
MAX_HOT_BYTES = 48 * 1024
MAX_DURABLE_LESSON_BYTES = 2 * 1024
ALLOWED_H2 = (
    "## Usage contract",
    "## Durable lessons",
    "## Topical pointers",
    "## Archive pointer",
)
ROLE_NAMES = (
    "A3",
    "AI-E",
    "BB",
    "CC",
    "E1",
    "E1a",
    "E2",
    "E3",
    "E4",
    "E5",
    "FA",
    "MIT",
    "PA",
    "PM",
    "QA",
    "QC",
    "R4",
    "TW",
)

_DATE_TOKEN = re.compile(r"\b20\d{2}[-/]\d{2}[-/]\d{2}\b")
_TASK_LEDGER_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:task|session|日期|任務|近期記錄|工作記憶)\s*[:：|]",
    re.IGNORECASE,
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROMOTION_PRIOR_MANIFEST_SEPARATOR = (
    b"\n<!-- ROLE_MEMORY_PRIOR_MANIFEST_V2 -->\n"
)

PromotionAuthorityVerifier = Callable[
    [str, str, dict[str, Any]],
    bool,
]
MANIFEST_FIELDS = {
    "schema_version",
    "generation",
    "supersedes_manifest_digest",
    "promotions",
    "policy",
    "roles",
    "manifest_digest",
}
PROMOTION_FIELDS = {
    "schema_version",
    "role",
    "durable_lesson",
    "closure_digest",
    "authority",
    "authority_attestation_digest",
    "closure_authority",
    "request_digest",
    "prior_generation",
    "prior_manifest_digest",
    "archive_record_offset",
    "archive_record_bytes",
    "archive_record_sha256",
    "prior_active_offset",
    "prior_active_bytes",
    "prior_active_sha256",
    "prior_manifest_offset",
    "prior_manifest_bytes",
    "prior_manifest_sha256",
    "promotion_digest",
}


COMMON_USAGE = (
    "This hot file contains role-specific durable judgment only; it is not "
    "active state, a task log, a runtime ledger, or closure evidence.",
    "Load it only when the routed role and current task make the lessons "
    "relevant; do not preload every role memory.",
    "Normative policy, current source, typed Context, current TODO state, and "
    "fresh runtime or external evidence override historical memory.",
    "Persist task detail in the canonical closure or role report. Promote only "
    "a recurring heuristic, authority boundary, or prevention rule here.",
    "The cold archive is append-only evidence. Never edit an archived payload; "
    "use its digest-bound slice when exact history is required.",
)


ROLE_LESSONS: dict[str, tuple[str, ...]] = {
    "A3": (
        "A rendered control is not usable merely because markup exists: trace "
        "the click through client logic, endpoint, response, state change, and "
        "visible recovery path.",
        "Treat dead controls, silent failures, native confirm or prompt dialogs, "
        "and missing empty/error states as product defects, not cosmetic nits.",
        "High-impact actions need explicit consequence copy, typed confirmation, "
        "cancel feedback, partial-failure detail, and a persistent residual-risk "
        "surface.",
        "Keyboard operation, focus return, mobile target size, contrast, reduced "
        "motion, and screen-reader state are acceptance dimensions.",
        "Validate the actual browser surface when behavior matters; structural "
        "HTML checks alone cannot prove modal, event, or async behavior.",
        "User-facing readiness must be sourced from a current backend contract; "
        "local storage and optimistic labels cannot grant operational authority.",
    ),
    "AI-E": (
        "Separate code presence, wiring, scheduled execution, artifact emission, "
        "serving, and measured business effect; each requires different proof.",
        "Tables, routes, models, and flags can all exist while the learning loop "
        "is dormant. Trace the producer, consumer, scheduler, and runtime evidence.",
        "Source completeness and green tests do not prove target-host execution, "
        "fresh artifacts, model selection, or realized performance.",
        "Classify maturity explicitly as foundation, skeleton, shadow, canary, or "
        "production, and never promote a layer without the evidence for that layer.",
        "Measure AI utility against a deterministic baseline with cost, latency, "
        "quality, and downstream actionability; provider call volume is not value.",
        "Training and serving must bind lineage, feature and label semantics, "
        "leakage controls, artifact digest, registry state, and rollback behavior.",
        "Credentials, private endpoints, and runtime contact remain outside a "
        "read-only AI effectiveness audit unless a governed adapter admits them.",
    ),
    "BB": (
        "Broker compatibility verdicts require three-way reconciliation of "
        "official documentation, the local reference dictionary, and current code.",
        "Use public read-only evidence for specification review; development agents "
        "never gain private broker, order, lease, or trading authority.",
        "Timeouts, malformed fields, and non-zero broker return codes fail closed. "
        "Idempotent close handling is not a general retry license.",
        "Pagination completeness is a safety property: absence from a truncated "
        "listing cannot prove absence of a position, order, or instrument.",
        "Parse numeric and timestamp fields strictly; valid zero or negative market "
        "values must not be confused with parse failure or fabricated defaults.",
        "Derive funding bounds and intervals from instrument metadata, not from the "
        "maximum observed in a regime-limited history sample.",
        "One-way and hedge position modes change reconciliation and stop semantics; "
        "any mode change requires a fresh compatibility review.",
        "Demo and mainnet capability differences must be explicit branches, while "
        "live authorization and fail-closed gates remain unchanged.",
    ),
    "CC": (
        "Normative authority comes from Root Principles, Hard Boundaries, accepted "
        "ADR or AMD decisions, and explicit operator decisions, not runtime behavior.",
        "Audit every claimed exception against its exact authority source, scope, "
        "expiry, and supersession chain; prose similarity is not authorization.",
        "A soft Python guard does not replace the binding Rust or adapter gate, and "
        "a runtime observation cannot legalize a policy denial.",
        "Governance that can be disabled, bypassed by ambient environment, or "
        "self-attested by its actor is not a closed control.",
        "Separate compliance of source, deployed runtime, external policy, and "
        "operator action; mixed evidence classes must not be collapsed into PASS.",
        "Preserve historical decisions through explicit supersession rather than "
        "rewriting old evidence or deleting dissent.",
    ),
    "E1": (
        "Verify task premises, paths, symbols, callers, schemas, and baselines "
        "against current source before implementation; plans and prior reports drift.",
        "Trace every changed signature, enum, field, return meaning, and helper "
        "through production callers and test construction sites.",
        "Production paths fail closed on missing authority, secrets, invalid input, "
        "or parse failure; do not fabricate zero, permissive, or success defaults.",
        "A helper existing is not integration. Prove the full producer-to-consumer "
        "path, central registration, and the condition under which it actually fires.",
        "Tests must bite the repaired behavior: use a targeted mutation or negative "
        "control and avoid mocking away the seam under test.",
        "Preserve unrelated work, write only inside the leased worktree, and never "
        "stage, revert, commit, push, deploy, or contact runtime beyond authority.",
        "Database and migration semantics require the admitted Linux and PG evidence "
        "lane; local mocks can prove pure logic but not target runtime behavior.",
        "Keep comments synchronized with behavior because stale rationale can "
        "reintroduce a fixed race, gate, or fallback defect.",
    ),
    "E1a": (
        "Dynamic strings entering HTML require the approved escaping boundary; use "
        "data attributes and event listeners instead of string-built inline handlers.",
        "Run a real JavaScript parser for changed scripts and extracted inline code; "
        "balanced braces cannot detect lexical-scope syntax failures.",
        "Dangerous actions need case-sensitive typed confirmation, impact and "
        "rollback context, cancel feedback, and explicit partial-failure reporting.",
        "Model unknown or missing control fields as a conservative visible state; "
        "never silently upgrade readiness through field fallback.",
        "Modal locks, disabled triggers, cleanup, focus return, and every rejection "
        "path must close as one state machine.",
        "Hidden tab containers can hide fixed overlays; mount global modals outside "
        "sub-tab visibility trees and clean timers when views deactivate.",
        "Sensitive values stay out of DOM persistence and are cleared after every "
        "submission outcome; display only backend-provided masks.",
        "Validate interactive behavior with browser-capable fixtures when events, "
        "async work, accessibility, or viewport layout are in scope.",
    ),
    "E2": (
        "Adversarial review requires behavior, test-bite, and non-vacuity evidence; "
        "a green suite alone is necessary but insufficient.",
        "Recompute claims, test counts, symbol exports, byte identity, and coverage "
        "instead of trusting the builder's summary.",
        "For refactors, compare symbol bodies or contracts, enumerate every caller, "
        "and reconcile the complete base-versus-head failure and node set.",
        "Treat comments and specifications as falsifiable claims; trace each promised "
        "guarantee to reachable data flow and the actual verdict emitter.",
        "Search for silent-fail families across languages, including broad exception "
        "swallowing, shell error masking, and health checks that default to PASS.",
        "Instrumentation must prove it can observe both divergence and agreement; "
        "zero findings can be a placement or reachability defect.",
        "Database changes require empirical schema, boundary inserts, permission "
        "checks, and repeat application in the authorized environment.",
        "Return implementation findings to the builder without silently widening "
        "scope or rewriting the code under independent review.",
    ),
    "E3": (
        "Source repair is not runtime closure; reload, deployment, and post-effect "
        "verification are separate admitted evidence steps.",
        "Audit live authority across every layer and keep the binding order-entry "
        "gate as the final source of truth; soft display gates are not sufficient.",
        "Unknown endpoint or environment provenance takes the more restrictive path, "
        "and demo capability never weakens live credential or authorization gates.",
        "Secret redaction needs keyword, structural, normalization, and entropy "
        "defenses across every adjacent durable sink.",
        "Prove authorization gates run before mutation with a spy or negative probe; "
        "HTTP status alone cannot exclude a time-of-check/time-of-use gap.",
        "Evaluate denial posture at the final routed outcome, not only at an "
        "intermediate state label or flag.",
        "Bound attacker-controlled maps, queues, regex work, and retry state with "
        "expiry or capacity; dormant surfaces remain latent risks before activation.",
        "Calibrate severity to a reachable asset path and existing defense layers, "
        "while preserving unresolved residuals as strict executable contracts.",
    ),
    "E4": (
        "Create the baseline from the same source and environment under test; never "
        "use a hard-coded historical count as current truth.",
        "Compare exact failed and skipped node identities, not only totals, and "
        "attribute every base-to-head delta.",
        "Critical tests must fail under a representative mutation and return to a "
        "byte-clean tree before the green run is accepted.",
        "Mock only external boundaries; the business seam under verification must "
        "execute for real, with explicit accounting of what was stubbed.",
        "Classify flakes only after isolated repetition, unchanged source, and proof "
        "that the modified path is not involved.",
        "Local PASS does not prove Linux, PG, TimescaleDB, service, or deployed "
        "behavior; mark unavailable surfaces owed rather than inventing parity.",
        "Run a real parser for JavaScript, measure hot paths with distributions, and "
        "state why performance or cross-language parity is not applicable when skipped.",
        "Reviewers do not repair business logic or perform effects; they return a "
        "reproducible finding to the owning builder.",
    ),
    "E5": (
        "Optimize from measured bottlenecks and call frequency, not file size or "
        "intuition; distinguish hot-path cost from infrequent control-plane work.",
        "Capacity models must include burst tails, all producers, consumer blocking "
        "windows, queue bounds, and observed drop or retry rates.",
        "Separate algorithmic latency, statistical tail, and platform scheduling "
        "floor before changing an SLA or implementation.",
        "Low-resolution timers can round real work to zero; state measurement "
        "resolution and use distributions rather than a single maximum.",
        "Reconstruct slow-run and shutdown claims from monotonic or append-only event "
        "timelines; buffered output can falsify apparent ordering.",
        "Child processes must not inherit governance locks or unrelated descriptors, "
        "and background configuration must be reproducible from versioned setup.",
        "Hot reload must update downstream derived copies as one contract; swapping "
        "the source object alone can leave runtime state silently stale.",
        "Source-only performance changes are dormant until the target binary is "
        "rebuilt and observed under the admitted runtime lane.",
    ),
    "FA": (
        "Judge capability by the complete business chain from trigger through "
        "consumer and durable outcome; a file, route, or table alone is not a feature.",
        "Trace both happy and denial branches to the final channel or effect; layered "
        "KEEP or warn guards do not imply a component is dead.",
        "Distinguish implemented, wired, scheduled, deployed, exercised, and useful "
        "states in every readiness verdict.",
        "Verify the premise and current repository path before declaring a function "
        "missing; stale plans and path guesses create false gaps.",
        "Cross-module seams and H1-to-H5 handoffs require direct caller and consumer "
        "evidence, not aggregate test coverage.",
        "Functional acceptance must separate source correctness, runtime activity, "
        "operator-gated effects, and measured product outcome.",
        "Report the smallest decisive blocker and its owner instead of turning every "
        "dormant future phase into a current critical failure.",
    ),
    "MIT": (
        "Database and TimescaleDB semantics require authorized empirical reflection, "
        "boundary probes, and repeat application; static SQL and mocks are insufficient.",
        "Bind migrations to on-disk bytes, registration state, checksum lineage, and "
        "runtime application; manual SQL execution is not migration closure.",
        "For directional signals, remove side-adjusted market beta before claiming "
        "alpha and use symmetric controls to expose beta masquerading as edge.",
        "Use dependence-aware inference for overlapping returns and clustered symbols; "
        "apply multiplicity correction and reject isolated incoherent significance.",
        "Prevent leakage with shifted rolling inputs, duration-aware purge and embargo, "
        "point-in-time universe membership, and typed provenance producers.",
        "Normalize canonical values across database round trips before hashing, "
        "including signed-zero and JSON representation edge cases.",
        "Classify ML maturity and evidence tier explicitly; synthetic replay cannot be "
        "promoted to live learning evidence.",
        "Alpha verdicts are math-primary. Language models may assist recall or "
        "interpretation only through a subtraction-only, fail-closed advisory lane.",
    ),
    "PA": (
        "Validate every brief premise, symbol, schema, migration slot, and claimed "
        "runtime fact against current source and admitted evidence before designing.",
        "Produce a self-contained implementation contract with exact interfaces, "
        "acceptance, denial behavior, ownership, recovery, and a no-op exit.",
        "Design fail closed on missing projections, credentials, IPC, cold-start "
        "state, or ambiguous authority; never manufacture a permissive fallback.",
        "Enumerate direct and indirect callers across code, re-exports, scripts, and "
        "process boundaries before proposing a signature or module change.",
        "Choose the abstraction depth that leaves growth headroom and follows existing "
        "sibling patterns; do not hide complexity inside an already overloaded file.",
        "Separate sample insufficiency from signal failure and distinguish breadth "
        "from independent sample size in every quantitative gate.",
        "Do not collapse architecture and implementation authority on high-risk work; "
        "route independent review and preserve explicit unresolved decisions.",
        "Treat append-only audit state and accepted supersession as lineage; redesign "
        "must not erase prior state transitions or dissent.",
    ),
    "PM": (
        "Start from current ground truth, explicit uncertainty, and exact acceptance; "
        "task prompts, TODO summaries, and prior agent claims can be stale.",
        "Use the smallest risk-DAG that covers hard edges, and admit extra roles only "
        "when expected decision value exceeds token, wait, and rework cost.",
        "One task has finite budgets and terminal states by default; unchanged state "
        "must stop instead of generating another continuation or wakeup.",
        "Source, test, runtime, external policy, operator authority, and realized "
        "outcome are separate evidence classes and cannot substitute for one another.",
        "A review PASS opens only its declared next gate; it is not deployment, "
        "runtime, product, or profitability closure.",
        "Deduplicate multi-role findings by root cause, preserve dissent, and promote "
        "one canonical closure rather than accumulating raw role narratives.",
        "Protect unrelated work with one owner and exact scope; commit, push, deploy, "
        "restart, broker contact, and durable publication require explicit authority.",
        "Treat actual usage and savings as platform-attested claims; controller counts "
        "and planned context are structural estimates only.",
    ),
    "QA": (
        "Verify value realism and per-row invariants after aggregate key or row-count "
        "checks; plausible totals can conceal fabricated or empty values.",
        "Prove a producer is registered, scheduled, and reaches its downstream effect; "
        "code existence and unit coverage do not prove runtime activity.",
        "Independently establish deployed source, process, environment, artifact, and "
        "business-path freshness before accepting runtime claims.",
        "HTTP success requires downstream evidence and HTTP failure does not prove the "
        "data plane is dead; reproduce the exact process or effect path.",
        "Validate schema and time-zone assumptions before writing acceptance queries, "
        "and distinguish migration application from registration.",
        "Use dependence-aware confidence bounds and observed sample velocity for "
        "small-sample gates; never extrapolate a short window as long-term behavior.",
        "Test task premises against production evidence and separate known dormant "
        "design from an accidental wiring gap.",
        "QA verifies and pushes back; it does not self-fix business code or turn a "
        "pre-deploy green gate into a deployed end-to-end claim.",
    ),
    "QC": (
        "Require net-of-fee, slippage, funding, latency, and market-impact evidence; "
        "gross technical indicators are not a tradable edge.",
        "Use walk-forward or nested evaluation with purge, embargo, point-in-time "
        "membership, and an untouched holdout before promotion.",
        "Correct for overlapping horizons, clustering, multiple testing, and selection "
        "bias; breadth across symbols is not independent sample size.",
        "Separate insufficient sample, failed signal, and operational infeasibility so "
        "a sparse gate is not mistaken for economic rejection.",
        "Stress regimes, tail events, delistings, capacity, turnover, and parameter "
        "sensitivity; average performance cannot establish survivability.",
        "Pre-register the hypothesis, metric, threshold, exclusions, and falsification "
        "condition before examining the decisive holdout.",
        "Recompute claimed statistics from immutable inputs and preserve the exact "
        "evidence path; narrative summaries cannot replace quantitative lineage.",
    ),
    "R4": (
        "Index health is a referential-integrity problem: detect missing targets, "
        "unindexed authoritative files, duplicates, stale aliases, and coverage drift.",
        "Current state belongs in TODO, stable architecture in canonical docs, and "
        "historical evidence in reports or archives; indexes should point, not copy.",
        "Distinguish live navigation files from frozen historical records before "
        "rewriting paths or correcting language.",
        "Large active files need a lossless archive plus a compact hot view; verify "
        "line, byte, digest, and recovery invariants mechanically.",
        "Audit generated views against their registry or source generator and never "
        "repair generated files by hand.",
        "A cleanup is complete only when all inbound and outbound references resolve "
        "and the replacement path is discoverable from the canonical index.",
        "Prefer deterministic manifests and bounded scans over narrative inventory "
        "counts that drift after every change.",
    ),
    "TW": (
        "Documentation describes current behavior only when verified against source "
        "and accepted authority; retain historical claims as dated evidence in cold reports.",
        "Use pointers instead of repeating the same narrative across indexes, "
        "changelogs, operator notes, worklogs, and role memory.",
        "Apply language and module-note policy to newly touched blocks without "
        "rewriting untouched history or expanding scope into unrelated cleanup.",
        "Separate formal documentation from role reports: canonical indexes enumerate "
        "durable interfaces, while report directories are routed collectively.",
        "Check terminology, present-versus-future tense, supersession, and path "
        "existence together; a grammatically correct statement can still overclaim.",
        "Large changelog-like index sections are a structural regression even when "
        "every target exists; route detail to an archive and preserve a concise index.",
        "When a documented guard or capability is absent from code, correct the "
        "present-tense authority source and leave future design explicitly pending.",
    ),
}


ROLE_POINTERS: dict[str, tuple[str, ...]] = {
    "A3": (
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/",
        "tests/static/",
    ),
    "AI-E": ("docs/execution_plan/ai_ml_landing/", "ml_training/"),
    "BB": ("docs/references/", "docs/CCAgentWorkSpace/BB/workspace/reports/"),
    "CC": ("CLAUDE.md", "docs/adr/"),
    "E1": ("program_code/", "tests/"),
    "E1a": (
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/",
        "tests/static/",
    ),
    "E2": ("tests/", "docs/agents/sub-agent-hygiene-sop.md"),
    "E3": ("CLAUDE.md", "sql/migrations/"),
    "E4": ("tests/", "docs/agents/sub-agent-hygiene-sop.md"),
    "E5": ("rust/openclaw_engine/", "helper_scripts/"),
    "FA": ("README.md", "CONTEXT.md"),
    "MIT": ("ml_training/", "sql/migrations/"),
    "PA": ("CONTEXT.md", "docs/adr/"),
    "PM": ("AGENTS.md", "docs/agents/context-loading.md"),
    "QA": ("tests/", "docs/agents/sub-agent-hygiene-sop.md"),
    "QC": ("helper_scripts/research/", "docs/CCAgentWorkSpace/QC/workspace/reports/"),
    "R4": ("docs/_indexes/", "docs/README.md"),
    "TW": ("docs/README.md", "helper_scripts/SCRIPT_INDEX.md"),
}


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest_record(value: dict[str, Any], field: str) -> str:
    canonical = {key: item for key, item in value.items() if key != field}
    return _sha256(_canonical_json(canonical))


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def discover_role_memories(repo_root: Path) -> list[Path]:
    """Return the exact governed active-memory set in canonical role order."""

    base = repo_root / "docs/CCAgentWorkSpace"
    found = {
        path.parent.name: path
        for path in base.glob("*/memory.md")
        if path.is_file()
    }
    return [found[role] for role in ROLE_NAMES if role in found]


def validate_hot_memory_bytes(data: bytes) -> list[str]:
    """Validate the bounded, non-ledger hot-memory policy."""

    errors: list[str] = []
    if len(data) > MAX_HOT_BYTES:
        errors.append(
            f"hot memory exceeds {MAX_HOT_BYTES} bytes: {len(data)}"
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return errors + ["hot memory is not valid UTF-8"]
    lines = text.splitlines()
    if len(lines) > MAX_HOT_LINES:
        errors.append(
            f"hot memory exceeds {MAX_HOT_LINES} lines: {len(lines)}"
        )
    headings = tuple(line for line in lines if line.startswith("## "))
    if headings != ALLOWED_H2:
        errors.append(
            "H2 headings must be exactly: " + ", ".join(ALLOWED_H2)
        )
    if any(line.startswith("### ") for line in lines):
        errors.append("hot memory must not contain nested dated/task sections")
    if _DATE_TOKEN.search(text):
        errors.append("hot memory must not contain date-organized history")
    if any(_TASK_LEDGER_LINE.search(line) for line in lines):
        errors.append("hot memory must not contain task/session ledger rows")
    if "Pointer digest: `sha256:" not in text:
        errors.append("hot memory archive pointer is not digest-bound")
    if not text.endswith("\n"):
        errors.append("hot memory must end with one newline")
    return errors


def _pointer_contract(
    *,
    role: str,
    active_path: str,
    archive_path: str,
    payload_sha256: str,
    payload_offset: int,
    payload_bytes: int,
) -> dict[str, Any]:
    return {
        "schema_version": POINTER_SCHEMA_VERSION,
        "role": role,
        "active_path": active_path,
        "archive_path": archive_path,
        "payload_sha256": payload_sha256,
        "payload_offset": payload_offset,
        "payload_bytes": payload_bytes,
    }


def _render_hot_memory(entry: dict[str, Any]) -> bytes:
    role = entry["role"]
    pointer = _pointer_contract(
        role=role,
        active_path=entry["active_path"],
        archive_path=entry["archive_path"],
        payload_sha256=entry["payload_sha256"],
        payload_offset=entry["payload_offset"],
        payload_bytes=entry["payload_bytes"],
    )
    pointer_digest = _sha256(_canonical_json(pointer))
    if pointer_digest != entry["archive_pointer_digest"]:
        raise ValueError(f"{role}: pointer digest drift")
    lines = [
        f"# {role} Role memory",
        "",
        "## Usage contract",
        "",
    ]
    lines.extend(f"- {lesson}" for lesson in COMMON_USAGE)
    lines.extend(("", "## Durable lessons", ""))
    durable_lessons = entry.get("durable_lessons")
    if not isinstance(durable_lessons, list) or not all(
        isinstance(lesson, str) for lesson in durable_lessons
    ):
        raise ValueError(f"{role}: durable_lessons must be a string list")
    lines.extend(f"- {lesson}" for lesson in durable_lessons)
    lines.extend(("", "## Topical pointers", ""))
    lines.append(
        f"- Role reports: `docs/CCAgentWorkSpace/{role}/workspace/reports/`"
    )
    lines.extend(f"- Source pointer: `{path}`" for path in ROLE_POINTERS[role])
    lines.extend(
        (
            "",
            "## Archive pointer",
            "",
            f"- Complete pre-compaction bytes: `{entry['archive_path']}`",
            f"- Payload digest: `{entry['payload_sha256']}`",
            f"- Payload slice: offset `{entry['payload_offset']}`, "
            f"bytes `{entry['payload_bytes']}`",
            f"- Pointer digest: `{entry['archive_pointer_digest']}`",
            f"- Recovery manifest: `{MANIFEST_PATH.as_posix()}`",
            "",
        )
    )
    data = "\n".join(lines).encode("utf-8")
    errors = validate_hot_memory_bytes(data)
    if errors:
        raise ValueError(f"{role}: invalid compact memory: {'; '.join(errors)}")
    return data


def _archive_record(
    role: str,
    source: bytes,
    archive_prefix: bytes,
) -> tuple[bytes, dict[str, Any]]:
    payload_sha256 = _sha256(source)
    marker = (
        "<!-- ROLE_MEMORY_COMPACTION_V1\n"
        f"role: {role}\n"
        f"payload_sha256: {payload_sha256}\n"
        f"payload_bytes: {len(source)}\n"
        "-->\n"
    ).encode("utf-8")
    existing_marker = archive_prefix.find(marker)
    if existing_marker >= 0:
        payload_offset = existing_marker + len(marker)
        payload_end = payload_offset + len(source)
        if archive_prefix[payload_offset:payload_end] != source:
            raise ValueError(f"{role}: archive marker payload mismatch")
        footer = (
            "\n<!-- /ROLE_MEMORY_COMPACTION_V1 "
            f"payload_sha256={payload_sha256} -->\n"
        ).encode("utf-8")
        record_end = payload_end + len(footer)
        if archive_prefix[payload_end:record_end] != footer:
            raise ValueError(f"{role}: archive record footer mismatch")
        prefix = archive_prefix[:existing_marker]
        record = archive_prefix[existing_marker:record_end]
        return archive_prefix, {
            "archive_prefix_bytes": len(prefix),
            "archive_prefix_sha256": _sha256(prefix),
            "record_offset": existing_marker,
            "record_bytes": len(record),
            "record_sha256": _sha256(record),
            "payload_offset": payload_offset,
            "payload_bytes": len(source),
            "payload_sha256": payload_sha256,
        }

    separator = b""
    if archive_prefix:
        separator = b"\n" if archive_prefix.endswith(b"\n") else b"\n\n"
    header = separator + marker
    footer = (
        "\n<!-- /ROLE_MEMORY_COMPACTION_V1 "
        f"payload_sha256={payload_sha256} -->\n"
    ).encode("utf-8")
    payload_offset = len(archive_prefix) + len(header)
    appended = header + source + footer
    archive_after = archive_prefix + appended
    return archive_after, {
        "archive_prefix_bytes": len(archive_prefix),
        "archive_prefix_sha256": _sha256(archive_prefix),
        "record_offset": len(archive_prefix),
        "record_bytes": len(appended),
        "record_sha256": _sha256(appended),
        "payload_offset": payload_offset,
        "payload_bytes": len(source),
        "payload_sha256": payload_sha256,
    }


def _promotion_request(
    *,
    role: str,
    lesson: str,
    closure_digest: str,
    authority: str,
    authority_attestation_digest: str,
) -> dict[str, Any]:
    return {
        "schema_version": PROMOTION_SCHEMA_VERSION,
        "role": role,
        "durable_lesson": lesson,
        "closure_digest": closure_digest,
        "authority": authority,
        "authority_attestation_digest": authority_attestation_digest,
    }


def _promotion_archive_record(
    *,
    role: str,
    source: bytes,
    prior_manifest: bytes,
    archive_prefix: bytes,
    request_digest: str,
    prior_manifest_digest: str,
    prior_generation: int,
) -> tuple[bytes, dict[str, Any]]:
    """Append or recover one exact predecessor-active/manifest record."""

    source_sha256 = _sha256(source)
    prior_manifest_sha256 = _sha256(prior_manifest)
    header = {
        "schema_version": PROMOTION_ARCHIVE_SCHEMA_VERSION,
        "role": role,
        "request_digest": request_digest,
        "prior_manifest_digest": prior_manifest_digest,
        "prior_generation": prior_generation,
        "prior_active_sha256": source_sha256,
        "prior_active_bytes": len(source),
        "prior_manifest_sha256": prior_manifest_sha256,
        "prior_manifest_bytes": len(prior_manifest),
    }
    marker = (
        b"<!-- ROLE_MEMORY_PROMOTION_V2\n"
        + _canonical_json(header)
        + b"\n-->\n"
    )
    footer = (
        "\n<!-- /ROLE_MEMORY_PROMOTION_V2 "
        f"request_digest={request_digest} -->\n"
    ).encode("utf-8")
    record = (
        marker
        + source
        + _PROMOTION_PRIOR_MANIFEST_SEPARATOR
        + prior_manifest
        + footer
    )
    existing_marker = archive_prefix.find(marker)
    if existing_marker >= 0:
        payload_offset = existing_marker + len(marker)
        payload_end = payload_offset + len(source)
        manifest_offset = (
            payload_end + len(_PROMOTION_PRIOR_MANIFEST_SEPARATOR)
        )
        manifest_end = manifest_offset + len(prior_manifest)
        record_end = manifest_end + len(footer)
        if archive_prefix[payload_offset:payload_end] != source:
            raise ValueError(f"{role}: promotion archive payload mismatch")
        if archive_prefix[
            payload_end:manifest_offset
        ] != _PROMOTION_PRIOR_MANIFEST_SEPARATOR:
            raise ValueError(f"{role}: promotion archive separator mismatch")
        if archive_prefix[manifest_offset:manifest_end] != prior_manifest:
            raise ValueError(f"{role}: promotion prior manifest mismatch")
        if archive_prefix[manifest_end:record_end] != footer:
            raise ValueError(f"{role}: promotion archive footer mismatch")
        existing_record = archive_prefix[existing_marker:record_end]
        return archive_prefix, {
            "archive_record_offset": existing_marker,
            "archive_record_bytes": len(existing_record),
            "archive_record_sha256": _sha256(existing_record),
            "prior_active_offset": payload_offset,
            "prior_active_bytes": len(source),
            "prior_active_sha256": source_sha256,
            "prior_manifest_offset": manifest_offset,
            "prior_manifest_bytes": len(prior_manifest),
            "prior_manifest_sha256": prior_manifest_sha256,
        }

    separator = b""
    if archive_prefix:
        separator = b"\n" if archive_prefix.endswith(b"\n") else b"\n\n"
    record_offset = len(archive_prefix) + len(separator)
    payload_offset = record_offset + len(marker)
    manifest_offset = (
        payload_offset
        + len(source)
        + len(_PROMOTION_PRIOR_MANIFEST_SEPARATOR)
    )
    appended = separator + record
    return archive_prefix + appended, {
        "archive_record_offset": record_offset,
        "archive_record_bytes": len(record),
        "archive_record_sha256": _sha256(record),
        "prior_active_offset": payload_offset,
        "prior_active_bytes": len(source),
        "prior_active_sha256": source_sha256,
        "prior_manifest_offset": manifest_offset,
        "prior_manifest_bytes": len(prior_manifest),
        "prior_manifest_sha256": prior_manifest_sha256,
    }


def _promotion_archive_payloads(
    *,
    repo_root: Path,
    entry: dict[str, Any],
    promotion: dict[str, Any],
) -> tuple[bytes, bytes]:
    """Exact-parse one promotion record and recover both predecessor payloads."""

    header = {
        "schema_version": PROMOTION_ARCHIVE_SCHEMA_VERSION,
        "role": promotion["role"],
        "request_digest": promotion["request_digest"],
        "prior_manifest_digest": promotion["prior_manifest_digest"],
        "prior_generation": promotion["prior_generation"],
        "prior_active_sha256": promotion["prior_active_sha256"],
        "prior_active_bytes": promotion["prior_active_bytes"],
        "prior_manifest_sha256": promotion["prior_manifest_sha256"],
        "prior_manifest_bytes": promotion["prior_manifest_bytes"],
    }
    marker = (
        b"<!-- ROLE_MEMORY_PROMOTION_V2\n"
        + _canonical_json(header)
        + b"\n-->\n"
    )
    footer = (
        "\n<!-- /ROLE_MEMORY_PROMOTION_V2 "
        f"request_digest={promotion['request_digest']} -->\n"
    ).encode("utf-8")
    archive = (repo_root / entry["archive_path"]).read_bytes()
    record_start = promotion["archive_record_offset"]
    active_start = record_start + len(marker)
    if promotion["prior_active_offset"] != active_start:
        raise ValueError("promotion prior-active offset differs")
    if archive[record_start:active_start] != marker:
        raise ValueError("promotion archive marker differs")
    active_end = active_start + promotion["prior_active_bytes"]
    manifest_start = (
        active_end + len(_PROMOTION_PRIOR_MANIFEST_SEPARATOR)
    )
    if promotion["prior_manifest_offset"] != manifest_start:
        raise ValueError("promotion prior-manifest offset differs")
    if archive[
        active_end:manifest_start
    ] != _PROMOTION_PRIOR_MANIFEST_SEPARATOR:
        raise ValueError("promotion archive manifest separator differs")
    manifest_end = manifest_start + promotion["prior_manifest_bytes"]
    record_end = manifest_end + len(footer)
    if promotion["archive_record_bytes"] != record_end - record_start:
        raise ValueError("promotion archive record length differs")
    if archive[manifest_end:record_end] != footer:
        raise ValueError("promotion archive footer differs")
    record = archive[record_start:record_end]
    if _sha256(record) != promotion["archive_record_sha256"]:
        raise ValueError("promotion archive record changed")
    prior_active = archive[active_start:active_end]
    if (
        len(prior_active) != promotion["prior_active_bytes"]
        or _sha256(prior_active) != promotion["prior_active_sha256"]
    ):
        raise ValueError("promotion prior-active payload differs")
    prior_manifest = archive[manifest_start:manifest_end]
    if (
        len(prior_manifest) != promotion["prior_manifest_bytes"]
        or _sha256(prior_manifest) != promotion["prior_manifest_sha256"]
    ):
        raise ValueError("promotion prior manifest payload differs")
    return prior_active, prior_manifest


def _manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def recover_original_bytes(
    repo_root: Path,
    entry: dict[str, Any],
) -> bytes:
    """Recover one exact pre-compaction payload from its archive slice."""

    archive = (repo_root / entry["archive_path"]).read_bytes()
    start = entry["payload_offset"]
    end = start + entry["payload_bytes"]
    payload = archive[start:end]
    if len(payload) != entry["payload_bytes"]:
        raise ValueError(f"{entry['role']}: archive payload is truncated")
    if _sha256(payload) != entry["payload_sha256"]:
        raise ValueError(f"{entry['role']}: archive payload digest mismatch")
    return payload


def _validated_durable_lesson(lesson: str) -> str:
    if not isinstance(lesson, str):
        raise ValueError("durable lesson must be a string")
    if not lesson or lesson != lesson.strip():
        raise ValueError("durable lesson must be non-empty and trimmed")
    if "\n" in lesson or "\r" in lesson:
        raise ValueError("durable lesson must be one logical line")
    if len(lesson.encode("utf-8")) > MAX_DURABLE_LESSON_BYTES:
        raise ValueError(
            f"durable lesson exceeds {MAX_DURABLE_LESSON_BYTES} bytes"
        )
    if lesson.startswith(("-", "*", "#")):
        raise ValueError("durable lesson must not contain list or heading markup")
    if _DATE_TOKEN.search(lesson):
        raise ValueError("durable lesson must not contain date-organized history")
    if _TASK_LEDGER_LINE.search(lesson):
        raise ValueError("durable lesson must not be a task/session ledger row")
    return lesson


def _validate_promotion_authority(
    *,
    role: str,
    lesson: str,
    authority: Any,
) -> list[str]:
    """Validate packet-local structure without upgrading its trust tier."""

    if not isinstance(authority, dict):
        return ["promotion closure authority must be an object"]
    expected_fields = {
        "schema_version",
        "trust_tier",
        "authority",
        "role",
        "durable_lesson_digest",
        "closure_digest",
        "producer",
        "attestation_id",
        "record_digest",
    }
    errors: list[str] = []
    if set(authority) != expected_fields:
        errors.append("promotion closure authority fields differ from v1")
    if authority.get("schema_version") != PROMOTION_AUTHORITY_SCHEMA_VERSION:
        errors.append("promotion closure authority schema is invalid")
    if authority.get("trust_tier") != PROMOTION_TRUST_TIER:
        errors.append("promotion closure authority trust tier is invalid")
    if authority.get("authority") != PROMOTION_AUTHORITY:
        errors.append("promotion closure authority kind is invalid")
    if authority.get("role") != role:
        errors.append("promotion closure authority role differs")
    expected_lesson_digest = _sha256(lesson.encode("utf-8"))
    if authority.get("durable_lesson_digest") != expected_lesson_digest:
        errors.append("promotion closure authority lesson digest differs")
    if not _SHA256.fullmatch(str(authority.get("closure_digest", ""))):
        errors.append("promotion closure authority closure digest is invalid")
    producer = authority.get("producer")
    if (
        not isinstance(producer, dict)
        or set(producer) != {"kind", "id"}
        or producer.get("kind") not in {"platform", "external"}
        or not isinstance(producer.get("id"), str)
        or not producer["id"]
    ):
        errors.append("promotion closure authority producer is invalid")
    if (
        not isinstance(authority.get("attestation_id"), str)
        or not authority["attestation_id"]
    ):
        errors.append("promotion closure authority attestation_id is invalid")
    if authority.get("record_digest") != _digest_record(
        authority, "record_digest"
    ):
        errors.append("promotion closure authority record digest mismatch")
    return errors


def _host_verified_promotion_authority(
    verifier: PromotionAuthorityVerifier | None,
    authority: dict[str, Any],
) -> bool:
    if verifier is None:
        return False
    try:
        return verifier(
            PROMOTION_AUTHORITY_SCHEMA_VERSION,
            str(authority.get("record_digest", "")),
            authority,
        ) is True
    except Exception:
        return False


def verify_manifest(
    repo_root: Path,
    manifest: dict[str, Any],
) -> list[str]:
    """Verify archive prefix, payload, compact view, and manifest integrity."""

    errors: list[str] = []
    if set(manifest) != MANIFEST_FIELDS:
        errors.append("manifest fields differ from the v3 contract")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("manifest schema_version is invalid")
    if manifest.get("manifest_digest") != _digest_record(
        manifest, "manifest_digest"
    ):
        errors.append("manifest digest mismatch")
    promotions = manifest.get("promotions")
    if not isinstance(promotions, list):
        promotions = []
        errors.append("manifest promotions must be a list")
    generation = manifest.get("generation")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation != len(promotions) + 1
    ):
        errors.append("manifest generation must equal promotions + 1")
    supersedes = manifest.get("supersedes_manifest_digest")
    if not promotions:
        if supersedes is not None:
            errors.append("initial manifest must not supersede another manifest")
    elif not isinstance(promotions[-1], dict):
        errors.append("manifest promotion must be an object")
    elif supersedes != promotions[-1].get("prior_manifest_digest"):
        errors.append("manifest supersedes digest does not bind prior generation")
    entries = manifest.get("roles")
    if not isinstance(entries, list):
        return errors + ["manifest roles must be a list"]
    expected_roles = tuple(
        path.parent.name for path in discover_role_memories(repo_root)
    )
    actual_roles = tuple(
        entry.get("role") if isinstance(entry, dict) else None
        for entry in entries
    )
    if actual_roles != expected_roles:
        errors.append(
            "manifest role roster must exactly match governed active memories"
        )
    entries_by_role = {
        entry.get("role"): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("role"), str)
    }
    promoted_lessons: dict[str, list[str]] = {
        role: [] for role in entries_by_role
    }
    request_digests: set[str] = set()
    for index, promotion in enumerate(promotions, start=1):
        if not isinstance(promotion, dict):
            errors.append("manifest promotion must be an object")
            continue
        role = promotion.get("role", "<unknown>")
        try:
            if set(promotion) != PROMOTION_FIELDS:
                errors.append(
                    f"{role}: promotion fields differ from the v2 contract"
                )
            authority = promotion["closure_authority"]
            errors.extend(
                f"{role}: {error}"
                for error in _validate_promotion_authority(
                    role=promotion["role"],
                    lesson=promotion["durable_lesson"],
                    authority=authority,
                )
            )
            request = _promotion_request(
                role=promotion["role"],
                lesson=_validated_durable_lesson(
                    promotion["durable_lesson"]
                ),
                closure_digest=promotion["closure_digest"],
                authority=promotion["authority"],
                authority_attestation_digest=authority["record_digest"],
            )
            request_digest = _sha256(_canonical_json(request))
            if promotion.get("request_digest") != request_digest:
                errors.append(f"{role}: promotion request digest mismatch")
            if request_digest in request_digests:
                errors.append(f"{role}: duplicate promotion request")
            request_digests.add(request_digest)
            if not _SHA256.fullmatch(promotion["closure_digest"]):
                errors.append(f"{role}: promotion closure digest is invalid")
            if promotion["closure_digest"] != authority.get("closure_digest"):
                errors.append(
                    f"{role}: promotion closure digest differs from authority"
                )
            if promotion["authority"] != PROMOTION_AUTHORITY:
                errors.append(f"{role}: promotion authority is invalid")
            if promotion["authority"] != authority.get("authority"):
                errors.append(
                    f"{role}: promotion authority differs from attestation"
                )
            if promotion.get("prior_generation") != index:
                errors.append(f"{role}: promotion generation lineage is invalid")
            if not _SHA256.fullmatch(
                str(promotion.get("prior_manifest_digest", ""))
            ):
                errors.append(f"{role}: prior manifest digest is invalid")
            if promotion.get("promotion_digest") != _digest_record(
                promotion, "promotion_digest"
            ):
                errors.append(f"{role}: promotion digest mismatch")
            entry = entries_by_role[promotion["role"]]
            prior_active, prior_manifest_bytes = _promotion_archive_payloads(
                repo_root=repo_root,
                entry=entry,
                promotion=promotion,
            )
            prior_manifest = json.loads(
                prior_manifest_bytes.decode("utf-8")
            )
            if not isinstance(prior_manifest, dict):
                raise ValueError("prior manifest must be an object")
            if _manifest_bytes(prior_manifest) != prior_manifest_bytes:
                errors.append(
                    f"{role}: prior manifest bytes are not canonical"
                )
            if set(prior_manifest) != MANIFEST_FIELDS:
                errors.append(f"{role}: prior manifest fields differ")
            if prior_manifest.get("schema_version") != SCHEMA_VERSION:
                errors.append(f"{role}: prior manifest schema is invalid")
            prior_entries = prior_manifest.get("roles")
            prior_roles = (
                tuple(
                    candidate.get("role")
                    if isinstance(candidate, dict)
                    else None
                    for candidate in prior_entries
                )
                if isinstance(prior_entries, list)
                else ()
            )
            if prior_roles != expected_roles:
                errors.append(f"{role}: prior manifest role roster differs")
            if prior_manifest.get("manifest_digest") != _digest_record(
                prior_manifest, "manifest_digest"
            ):
                errors.append(f"{role}: prior manifest self-digest mismatch")
            if prior_manifest.get("manifest_digest") != promotion[
                "prior_manifest_digest"
            ]:
                errors.append(f"{role}: prior manifest digest differs")
            if prior_manifest.get("generation") != promotion[
                "prior_generation"
            ]:
                errors.append(f"{role}: prior manifest generation differs")
            if prior_manifest.get("promotions") != promotions[: index - 1]:
                errors.append(f"{role}: prior manifest promotion prefix differs")
            prior_promotions = prior_manifest.get("promotions")
            expected_prior_supersedes = (
                None
                if not prior_promotions
                else prior_promotions[-1].get("prior_manifest_digest")
            )
            if (
                prior_manifest.get("supersedes_manifest_digest")
                != expected_prior_supersedes
            ):
                errors.append(
                    f"{role}: prior manifest supersedes lineage differs"
                )
            prior_entry = next(
                (
                    candidate
                    for candidate in prior_manifest.get("roles", [])
                    if isinstance(candidate, dict)
                    and candidate.get("role") == promotion["role"]
                ),
                None,
            )
            if (
                prior_entry is None
                or prior_entry.get("active_sha256")
                != _sha256(prior_active)
            ):
                errors.append(f"{role}: prior active binding differs")
            promoted_lessons[promotion["role"]].append(
                promotion["durable_lesson"]
            )
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            errors.append(f"{role}: invalid promotion: {exc}")
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("manifest role entry must be an object")
            continue
        role = entry.get("role", "<unknown>")
        try:
            archive = (repo_root / entry["archive_path"]).read_bytes()
            prefix_end = entry["archive_prefix_bytes"]
            if _sha256(archive[:prefix_end]) != entry["archive_prefix_sha256"]:
                errors.append(f"{role}: existing archive prefix changed")
            record_start = entry["record_offset"]
            record_end = record_start + entry["record_bytes"]
            if _sha256(archive[record_start:record_end]) != entry["record_sha256"]:
                errors.append(f"{role}: archive record changed")
            recover_original_bytes(repo_root, entry)
            active = (repo_root / entry["active_path"]).read_bytes()
            if _sha256(active) != entry["active_sha256"]:
                errors.append(f"{role}: active compact memory digest mismatch")
            expected_lessons = list(ROLE_LESSONS[role]) + promoted_lessons.get(
                role, []
            )
            if entry.get("durable_lessons") != expected_lessons:
                errors.append(f"{role}: durable lesson lineage mismatch")
            expected_active = _render_hot_memory(entry)
            if active != expected_active:
                errors.append(f"{role}: active compact memory render drift")
            errors.extend(
                f"{role}: {error}" for error in validate_hot_memory_bytes(active)
            )
            pointer = _pointer_contract(
                role=role,
                active_path=entry["active_path"],
                archive_path=entry["archive_path"],
                payload_sha256=entry["payload_sha256"],
                payload_offset=entry["payload_offset"],
                payload_bytes=entry["payload_bytes"],
            )
            expected_pointer = _sha256(_canonical_json(pointer))
            if expected_pointer != entry["archive_pointer_digest"]:
                errors.append(f"{role}: archive pointer digest mismatch")
            if expected_pointer.encode("utf-8") not in active:
                errors.append(f"{role}: active archive pointer is not bound")
        except (KeyError, OSError, TypeError, ValueError) as exc:
            errors.append(f"{role}: {exc}")
    return errors


def _existing_manifest(repo_root: Path) -> dict[str, Any] | None:
    path = repo_root / MANIFEST_PATH
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("role memory compaction manifest must be an object")
    return value


def _upgrade_legacy_manifest(
    repo_root: Path,
    manifest: dict[str, Any],
    roles: tuple[str, ...],
) -> dict[str, Any]:
    """Upgrade an unpromoted v1/v2 snapshot without rewriting memory bytes."""

    schema_version = manifest.get("schema_version")
    if schema_version not in {
        LEGACY_SCHEMA_VERSION,
        INTERMEDIATE_SCHEMA_VERSION,
    }:
        raise ValueError("manifest is not a supported legacy generation")
    if manifest.get("manifest_digest") != _digest_record(
        manifest, "manifest_digest"
    ):
        raise ValueError("manifest digest mismatch")
    entries = manifest.get("roles")
    if not isinstance(entries, list):
        raise ValueError("manifest roles must be a list")
    if tuple(
        entry.get("role") if isinstance(entry, dict) else None
        for entry in entries
    ) != roles:
        raise ValueError("existing compaction manifest does not match requested roles")

    upgraded = json.loads(json.dumps(manifest, ensure_ascii=False))
    upgraded["schema_version"] = SCHEMA_VERSION
    if schema_version == LEGACY_SCHEMA_VERSION:
        upgraded["generation"] = 1
        upgraded["supersedes_manifest_digest"] = None
        upgraded["promotions"] = []
        for entry in upgraded["roles"]:
            role = entry["role"]
            entry["durable_lessons"] = list(ROLE_LESSONS[role])
    elif (
        upgraded.get("generation") != 1
        or upgraded.get("supersedes_manifest_digest") is not None
        or upgraded.get("promotions") != []
    ):
        raise ValueError(
            "v2 manifests with promotions require trusted explicit migration"
        )
    upgraded["manifest_digest"] = _digest_record(
        upgraded, "manifest_digest"
    )
    errors = verify_manifest(repo_root, upgraded)
    if errors:
        raise ValueError("; ".join(errors))
    _atomic_write(repo_root / MANIFEST_PATH, _manifest_bytes(upgraded))
    return upgraded


def _latest_bound_prior_active(
    repo_root: Path,
    manifest: dict[str, Any],
    entry: dict[str, Any],
) -> bytes | None:
    """Recover the only predecessor view allowed for interrupted finalization."""

    promotion = next(
        (
            candidate
            for candidate in reversed(manifest.get("promotions", []))
            if candidate.get("role") == entry.get("role")
        ),
        None,
    )
    if promotion is None:
        return None
    if promotion.get("promotion_digest") != _digest_record(
        promotion, "promotion_digest"
    ):
        raise ValueError(f"{entry['role']}: promotion digest mismatch")
    prior, _ = _promotion_archive_payloads(
        repo_root=repo_root,
        entry=entry,
        promotion=promotion,
    )
    return prior


def _resume_or_return(
    repo_root: Path,
    manifest: dict[str, Any],
    roles: tuple[str, ...],
) -> dict[str, Any] | None:
    entries = manifest.get("roles")
    if not isinstance(entries, list):
        return None
    if tuple(
        entry.get("role") if isinstance(entry, dict) else None
        for entry in entries
    ) != roles:
        return None
    if manifest.get("schema_version") != SCHEMA_VERSION:
        return None
    if manifest.get("manifest_digest") != _digest_record(
        manifest, "manifest_digest"
    ):
        raise ValueError("manifest digest mismatch")
    archive_errors: list[str] = []
    for entry in entries:
        try:
            recover_original_bytes(repo_root, entry)
            archive = (repo_root / entry["archive_path"]).read_bytes()
            prefix_end = entry["archive_prefix_bytes"]
            if _sha256(archive[:prefix_end]) != entry["archive_prefix_sha256"]:
                archive_errors.append(f"{entry['role']}: prefix drift")
        except (KeyError, OSError, TypeError, ValueError) as exc:
            archive_errors.append(f"{entry.get('role', '<unknown>')}: {exc}")
    if archive_errors:
        return None

    changed = False
    for entry in entries:
        active_path = repo_root / entry["active_path"]
        expected = _render_hot_memory(entry)
        current = active_path.read_bytes()
        if current == expected:
            continue
        original = recover_original_bytes(repo_root, entry)
        prior_active = _latest_bound_prior_active(repo_root, manifest, entry)
        if current != original and current != prior_active:
            raise ValueError(
                f"{entry['role']}: active memory drift after compaction"
            )
        _atomic_write(active_path, expected)
        changed = True
    if changed:
        errors = verify_manifest(repo_root, manifest)
        if errors:
            raise ValueError("; ".join(errors))
    else:
        errors = verify_manifest(repo_root, manifest)
        if errors:
            raise ValueError("; ".join(errors))
    return manifest


def compact_repository(
    repo_root: Path,
    *,
    roles: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Archive exact active bytes and replace them with bounded hot views."""

    repo_root = repo_root.resolve()
    selected = tuple(roles) if roles is not None else ROLE_NAMES
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("roles must be a non-empty unique sequence")
    unknown = sorted(set(selected) - set(ROLE_NAMES))
    if unknown:
        raise ValueError(f"unknown roles: {', '.join(unknown)}")
    if any(
        role not in ROLE_LESSONS or role not in ROLE_POINTERS
        for role in selected
    ):
        raise ValueError("every selected role requires lessons and pointers")

    existing = _existing_manifest(repo_root)
    if existing is not None:
        if existing.get("schema_version") in {
            LEGACY_SCHEMA_VERSION,
            INTERMEDIATE_SCHEMA_VERSION,
        }:
            return _upgrade_legacy_manifest(repo_root, existing, selected)
        resumed = _resume_or_return(repo_root, existing, selected)
        if resumed is not None:
            return resumed
        raise ValueError("existing compaction manifest does not match requested roles")

    active_paths = {
        path.parent.name: path for path in discover_role_memories(repo_root)
    }
    missing = [role for role in selected if role not in active_paths]
    if missing:
        raise ValueError(f"missing active role memories: {', '.join(missing)}")

    planned_archives: list[tuple[Path, bytes]] = []
    entries: list[dict[str, Any]] = []
    compact_views: list[tuple[Path, bytes]] = []
    for role in selected:
        active_path = active_paths[role]
        archive_path = active_path.with_name("memory-archive.md")
        source = active_path.read_bytes()
        archive_prefix = archive_path.read_bytes() if archive_path.exists() else b""
        archive_after, archive_fields = _archive_record(
            role, source, archive_prefix
        )
        active_rel = _relative(active_path, repo_root)
        archive_rel = _relative(archive_path, repo_root)
        entry: dict[str, Any] = {
            "role": role,
            "active_path": active_rel,
            "archive_path": archive_rel,
            **archive_fields,
            "original_lines": len(source.decode("utf-8").splitlines()),
            "durable_lessons": list(ROLE_LESSONS[role]),
        }
        pointer = _pointer_contract(
            role=role,
            active_path=active_rel,
            archive_path=archive_rel,
            payload_sha256=entry["payload_sha256"],
            payload_offset=entry["payload_offset"],
            payload_bytes=entry["payload_bytes"],
        )
        entry["archive_pointer_digest"] = _sha256(_canonical_json(pointer))
        compact = _render_hot_memory(entry)
        entry["active_bytes"] = len(compact)
        entry["active_lines"] = len(compact.decode("utf-8").splitlines())
        entry["active_sha256"] = _sha256(compact)
        planned_archives.append((archive_path, archive_after))
        compact_views.append((active_path, compact))
        entries.append(entry)

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generation": 1,
        "supersedes_manifest_digest": None,
        "promotions": [],
        "policy": {
            "allowed_h2": list(ALLOWED_H2),
            "max_hot_bytes": MAX_HOT_BYTES,
            "max_hot_lines": MAX_HOT_LINES,
            "archive_payload_encoding": "raw_bytes",
            "archive_prefix_policy": "immutable",
            "active_history_policy": "no_date_or_task_ledger",
        },
        "roles": entries,
    }
    manifest["manifest_digest"] = _digest_record(manifest, "manifest_digest")

    # Order is deliberate: preserve originals first, then publish the recovery
    # manifest, and only then replace hot views. A rerun resumes an interrupted
    # finalization without appending a duplicate payload.
    for path, data in planned_archives:
        _atomic_write(path, data)
    _atomic_write(repo_root / MANIFEST_PATH, _manifest_bytes(manifest))
    for path, data in compact_views:
        _atomic_write(path, data)

    errors = verify_manifest(repo_root, manifest)
    if errors:
        raise ValueError("; ".join(errors))
    return manifest


def promote_durable_lesson(
    repo_root: Path,
    *,
    role: str,
    lesson: str,
    closure_authority: dict[str, Any],
    authority_verifier: PromotionAuthorityVerifier | None,
) -> dict[str, Any]:
    """Publish one host-authenticated durable lesson successor generation."""

    repo_root = repo_root.resolve()
    lesson = _validated_durable_lesson(lesson)
    if role not in ROLE_NAMES:
        raise ValueError(f"unknown role: {role}")
    try:
        frozen_authority = json.loads(
            json.dumps(closure_authority, ensure_ascii=False)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "promotion closure authority must be canonical JSON"
        ) from exc
    if frozen_authority != closure_authority:
        raise ValueError("promotion closure authority must be canonical JSON")
    authority_errors = _validate_promotion_authority(
        role=role,
        lesson=lesson,
        authority=frozen_authority,
    )
    if authority_errors:
        raise ValueError("; ".join(authority_errors))
    if not _host_verified_promotion_authority(
        authority_verifier,
        json.loads(json.dumps(frozen_authority, ensure_ascii=False)),
    ):
        raise ValueError(
            "promotion requires an out-of-band host verifier for exact "
            "PLATFORM_OR_EXTERNAL_ATTESTED closure authority bytes"
        )
    closure_digest = frozen_authority["closure_digest"]
    authority = frozen_authority["authority"]

    manifest = _load_checked_manifest(repo_root)
    errors = verify_manifest(repo_root, manifest)
    if errors:
        raise ValueError("; ".join(errors))
    request = _promotion_request(
        role=role,
        lesson=lesson,
        closure_digest=closure_digest,
        authority=authority,
        authority_attestation_digest=frozen_authority["record_digest"],
    )
    request_digest = _sha256(_canonical_json(request))
    for promotion in manifest["promotions"]:
        if promotion.get("request_digest") == request_digest:
            return manifest

    entry = next(
        (
            candidate
            for candidate in manifest["roles"]
            if candidate.get("role") == role
        ),
        None,
    )
    if entry is None:
        raise ValueError(f"role is not governed by this manifest: {role}")
    if lesson in entry["durable_lessons"]:
        raise ValueError("durable lesson already exists under different lineage")

    active_path = repo_root / entry["active_path"]
    archive_path = repo_root / entry["archive_path"]
    current_active = active_path.read_bytes()
    current_archive = archive_path.read_bytes()
    prior_manifest_bytes = (repo_root / MANIFEST_PATH).read_bytes()
    if prior_manifest_bytes != _manifest_bytes(manifest):
        raise ValueError("prior manifest bytes are not canonical")
    archive_after, archive_fields = _promotion_archive_record(
        role=role,
        source=current_active,
        prior_manifest=prior_manifest_bytes,
        archive_prefix=current_archive,
        request_digest=request_digest,
        prior_manifest_digest=manifest["manifest_digest"],
        prior_generation=manifest["generation"],
    )

    successor = json.loads(json.dumps(manifest, ensure_ascii=False))
    successor_entry = next(
        candidate
        for candidate in successor["roles"]
        if candidate["role"] == role
    )
    successor_entry["durable_lessons"].append(lesson)
    successor_active = _render_hot_memory(successor_entry)
    successor_entry["active_bytes"] = len(successor_active)
    successor_entry["active_lines"] = len(
        successor_active.decode("utf-8").splitlines()
    )
    successor_entry["active_sha256"] = _sha256(successor_active)
    promotion = {
        **request,
        "closure_authority": frozen_authority,
        "request_digest": request_digest,
        "prior_generation": manifest["generation"],
        "prior_manifest_digest": manifest["manifest_digest"],
        **archive_fields,
    }
    promotion["promotion_digest"] = _digest_record(
        promotion, "promotion_digest"
    )
    successor["generation"] = manifest["generation"] + 1
    successor["supersedes_manifest_digest"] = manifest["manifest_digest"]
    successor["promotions"].append(promotion)
    successor["manifest_digest"] = _digest_record(
        successor, "manifest_digest"
    )

    # Preserve the current hot view first, then publish its successor manifest,
    # and finally switch the active view. Replaying the same request reuses the
    # exact archive record and never appends a duplicate.
    _atomic_write(archive_path, archive_after)
    _atomic_write(repo_root / MANIFEST_PATH, _manifest_bytes(successor))
    _atomic_write(active_path, successor_active)

    errors = verify_manifest(repo_root, successor)
    if errors:
        raise ValueError("; ".join(errors))
    return successor


def _load_checked_manifest(repo_root: Path) -> dict[str, Any]:
    manifest = _existing_manifest(repo_root)
    if manifest is None:
        raise ValueError(f"missing {MANIFEST_PATH.as_posix()}")
    return manifest


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--recover", metavar="ROLE")
    mode.add_argument("--promote", metavar="ROLE")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lesson")
    parser.add_argument("--closure-digest")
    parser.add_argument("--authority")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.repo_root.resolve()

    promotion_options = (
        args.lesson,
        args.closure_digest,
        args.authority,
    )
    if args.promote is None and any(
        option is not None for option in promotion_options
    ):
        raise ValueError(
            "--lesson, --closure-digest, and --authority require --promote"
        )

    if args.apply:
        manifest = compact_repository(root)
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "roles": len(manifest["roles"]),
                    "manifest_digest": manifest["manifest_digest"],
                },
                sort_keys=True,
            )
        )
        return 0

    if args.promote is not None:
        if any(option is None for option in promotion_options):
            raise ValueError(
                "--promote requires --lesson, --closure-digest, and --authority"
            )
        print(
            json.dumps(
                {
                    "schema_version": "role_memory_promotion_result_v1",
                    "status": "EXTERNAL_LIMIT",
                    "role": args.promote,
                    "mutation_applied": False,
                    "required_trust_tier": (
                        "PLATFORM_OR_EXTERNAL_ATTESTED"
                    ),
                    "reason_code": "trusted_host_verifier_unavailable",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2

    manifest = _load_checked_manifest(root)
    if args.check:
        errors = verify_manifest(root, manifest)
        print(
            json.dumps(
                {
                    "status": "PASS" if not errors else "FAIL",
                    "roles": len(manifest.get("roles", [])),
                    "errors": errors,
                    "manifest_digest": manifest.get("manifest_digest"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if not errors else 1

    entry = next(
        (
            candidate
            for candidate in manifest.get("roles", [])
            if candidate.get("role") == args.recover
        ),
        None,
    )
    if entry is None:
        raise ValueError(f"unknown manifest role: {args.recover}")
    payload = recover_original_bytes(root, entry)
    if args.output is None:
        raise ValueError("--recover requires --output")
    _atomic_write(args.output, payload)
    print(
        json.dumps(
            {
                "status": "PASS",
                "role": args.recover,
                "output": str(args.output),
                "payload_sha256": entry["payload_sha256"],
                "payload_bytes": entry["payload_bytes"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
