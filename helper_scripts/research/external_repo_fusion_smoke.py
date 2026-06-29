#!/usr/bin/env python3
"""End-to-end smoke for external-repo fusion helpers.

The smoke wires the two adopted ideas into TradeBot-native adapters:
offline docs retrieval and advisory PM/AEG/M4 report audit. It writes only to a
caller-selected artifact directory and grants no runtime/trading authority.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

SRV_ROOT = Path(__file__).resolve().parents[2]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from helper_scripts.docs_context_retrieval import retriever  # noqa: E402
from helper_scripts.research.aeg_report_audit import audit as audit_mod  # noqa: E402

SMOKE_SCHEMA_VERSION = "tradebot.external_repo_fusion_smoke.v1"


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def default_output_dir() -> Path:
    return Path("/tmp/openclaw") / "external_repo_fusion_smoke"


def scratch_root() -> Path:
    return Path("/tmp/openclaw").resolve()


def _resolve_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    root = scratch_root()
    if not (resolved == root or resolved.is_relative_to(root)):
        raise ValueError(f"output_dir_must_be_under_tmp_openclaw:{output_dir}")
    return resolved


def _existing(paths: Sequence[Path]) -> list[Path]:
    return [path for path in paths if path.exists()]


def _default_pm_inputs(repo_root: Path) -> list[Path]:
    return _existing([
        repo_root / "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--external_repo_integration_synthesis.md",
        repo_root / "CLAUDE.md",
    ])


def _default_aeg_inputs(repo_root: Path) -> list[Path]:
    return _existing([
        repo_root / "docs/adr/0047-alpha-edge-regime-evidence-governance.md",
        repo_root / "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-12--aeg_s3_oi_delta_pbo_grid.md",
    ])


def _default_m4_inputs(repo_root: Path) -> list[Path]:
    return _existing([
        repo_root / "docs/adr/0045-m4-hypothesis-discovery-governance.md",
        repo_root / "helper_scripts/m4/attribute_enforcer.py",
    ])


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _run_audit_profile(profile: str, inputs: Sequence[Path], output_dir: Path) -> dict:
    if not inputs:
        batch = {
            "schema_version": "tradebot.aeg_report_audit.batch.v1",
            "profile": profile,
            "input_count": 0,
            "ready_count": 0,
            "status": "insufficient_evidence",
            "finding_count": 0,
            "severity_counts": {},
            "authority": audit_mod.authority_flags(),
            "advisory_statuses": ["advisory_pass", "audit_gap", "insufficient_evidence", "citation_missing"],
            "falsification_ready": False,
            "promotion_evidence": False,
            "audits": [],
        }
    else:
        batch = audit_mod.audit_many(list(inputs), profile=profile)
    json_path = _write_json(output_dir / f"{profile}_audit.json", batch)
    md_path = _write_text(output_dir / f"{profile}_audit.md", audit_mod.markdown_summary(batch))
    return {
        "profile": profile,
        "status": batch["status"],
        "input_count": batch["input_count"],
        "finding_count": batch["finding_count"],
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "authority": batch["authority"],
    }


def run_smoke(
    *,
    repo_root: Path,
    output_dir: Path,
    queries: Sequence[str] | None = None,
    top_k: int = 5,
) -> dict:
    out = _resolve_output_dir(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    index = retriever.build_index(repo_root=repo_root)
    index_path = retriever.write_index(index, out / "docs_context_index.json")
    query_texts = list(queries or (
        "alpha evidence governance PSR DSR PBO",
        "Decision Lease Rust authority no order",
        "ContextDistiller token cap docs retrieval",
    ))
    retrieval_results = []
    for idx, query in enumerate(query_texts, start=1):
        result = retriever.query_index(index, query, top_k=top_k, snippet_token_budget=160)
        result_path = _write_json(out / f"docs_query_{idx}.json", result)
        retrieval_results.append({
            "query": query,
            "result_count": result["result_count"],
            "score_semantics": "relevance_only",
            "json_path": str(result_path),
            "authority": result["authority"],
        })

    audit_results = [
        _run_audit_profile("pm_report", _default_pm_inputs(repo_root), out),
        _run_audit_profile("aeg_artifact", _default_aeg_inputs(repo_root), out),
        _run_audit_profile("m4_hypothesis", _default_m4_inputs(repo_root), out),
    ]

    authority_payloads = [index["authority"]]
    authority_payloads.extend(row["authority"] for row in retrieval_results)
    authority_payloads.extend(row["authority"] for row in audit_results)
    authority_preserved = all(
        payload.get("advisory_only") is True
        and payload.get("order_authority_granted") is False
        and payload.get("promotion_authority") is False
        and payload.get("runtime_mutation_authority") is False
        for payload in authority_payloads
    )
    retrieval_ready = all(row["result_count"] > 0 for row in retrieval_results)
    audit_emitted = all(row["input_count"] >= 0 and row["json_path"] for row in audit_results)
    status = (
        "EXTERNAL_REPO_FUSION_SMOKE_COMPLETE"
        if retrieval_ready and audit_emitted and authority_preserved
        else "EXTERNAL_REPO_FUSION_SMOKE_GAPS_FOUND"
    )
    summary = {
        "schema_version": SMOKE_SCHEMA_VERSION,
        "status": status,
        "repo_root": str(repo_root),
        "output_dir": str(out),
        "docs_index_json": str(index_path),
        "docs_index_sha256": index["index_sha256"],
        "docs_index_chunk_count": index["chunk_count"],
        "retrieval_ready": retrieval_ready,
        "audit_emitted": audit_emitted,
        "authority_preserved": authority_preserved,
        "authority": retriever.authority_flags(),
        "retrieval_results": retrieval_results,
        "audit_results": audit_results,
    }
    _write_json(out / "external_repo_fusion_smoke_summary.json", summary)
    return summary


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="external_repo_fusion_smoke",
        description="Read-only smoke for docs retrieval + PM/AEG/M4 advisory audit fusion",
    )
    parser.add_argument("--repo-root", default=str(repo_root_from_here()), dest="repo_root")
    parser.add_argument("--output-dir", default=str(default_output_dir()), dest="output_dir")
    parser.add_argument("--query", action="append", default=[], dest="queries")
    parser.add_argument("--top-k", type=int, default=5, dest="top_k")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    summary = run_smoke(
        repo_root=Path(args.repo_root).resolve(),
        output_dir=Path(args.output_dir),
        queries=args.queries or None,
        top_k=args.top_k,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["status"] == "EXTERNAL_REPO_FUSION_SMOKE_COMPLETE" else 2


if __name__ == "__main__":
    sys.exit(main())
