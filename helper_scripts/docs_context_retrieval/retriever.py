"""Offline BM25-style retrieval over repo-local governance docs.

This module is intentionally read-only with respect to source/runtime state.
It reads selected repository files, writes only the caller-selected index JSON,
and never treats retrieval output as trading, risk, promotion, or proof
authority.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

INDEX_SCHEMA_VERSION = "tradebot.docs_context_retrieval.index.v1"
QUERY_SCHEMA_VERSION = "tradebot.docs_context_retrieval.query.v1"
RUNNER_VERSION = "docs_context_retrieval.v1"

DEFAULT_SOURCE_PATHS = (
    "AGENTS.md",
    "CLAUDE.md",
    ".codex/MEMORY.md",
    ".codex/AGENT_DISPATCH_PROTOCOL.md",
    ".codex/SUBAGENT_EXECUTION_RULES.md",
    "docs/README.md",
    "docs/adr",
    "docs/execution_plan",
    "docs/CCAgentWorkSpace/PM/memory.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports",
)

SUPPORTED_SUFFIXES = {".md", ".txt", ".json", ".toml", ".yaml", ".yml"}
DEFAULT_OUTPUT_ROOT = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")) / "docs_context_retrieval"
MAX_FILE_BYTES = 2_000_000

_TOKEN_RE = re.compile(r"[a-z0-9_][a-z0-9_'\-]*|[\u4e00-\u9fff]+", re.IGNORECASE)
_CJK_RE = re.compile(r"^[\u4e00-\u9fff]+$")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_text(repo_root: Path, args: Sequence[str]) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout.strip()
    except Exception:
        return ""


def git_provenance(repo_root: Path) -> dict[str, Any]:
    status = _git_text(repo_root, ["status", "--porcelain"])
    diff = _git_text(repo_root, ["diff", "HEAD"])
    return {
        "git_sha": _git_text(repo_root, ["rev-parse", "HEAD"]) or "unknown",
        "git_dirty": bool(status),
        "git_diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest() if diff else None,
    }


def canonical_json_sha(payload: Mapping[str, Any]) -> str:
    clone = dict(payload)
    clone.pop("index_sha256", None)
    clone.pop("created_at_utc", None)
    raw = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if raw in _STOPWORDS:
            continue
        if _CJK_RE.match(raw) and len(raw) > 1:
            tokens.extend(raw[i : i + 2] for i in range(len(raw) - 1))
            tokens.append(raw)
            continue
        tokens.append(raw)
    return tokens


def _iter_source_files(repo_root: Path, source_paths: Sequence[str]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    root = repo_root.resolve()
    for raw in source_paths:
        if not raw:
            continue
        path = Path(raw)
        full = (path if path.is_absolute() else root / path).resolve()
        if not (full == root or full.is_relative_to(root)):
            raise ValueError(f"source_path_outside_repo:{raw}")
        if full.is_file():
            candidates = [full]
        elif full.is_dir():
            candidates = [p for p in full.rglob("*") if p.is_file()]
        else:
            continue
        for candidate in sorted(candidates):
            if candidate.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if candidate.stat().st_size > MAX_FILE_BYTES:
                continue
            resolved = candidate.resolve()
            if not (resolved == root or resolved.is_relative_to(root)):
                raise ValueError(f"candidate_path_outside_repo:{candidate}")
            if resolved not in seen:
                seen.add(resolved)
                files.append(candidate)
    return sorted(files)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _chunk_lines(
    rel_path: str,
    text: str,
    *,
    chunk_line_count: int,
    overlap_lines: int,
) -> Iterable[dict[str, Any]]:
    lines = text.splitlines()
    if not lines:
        return
    step = max(1, chunk_line_count - overlap_lines)
    for start in range(0, len(lines), step):
        end = min(len(lines), start + chunk_line_count)
        body = "\n".join(lines[start:end]).strip()
        if not body:
            continue
        yield {
            "chunk_id": f"{rel_path}:{start + 1}-{end}",
            "source_path": rel_path,
            "line_start": start + 1,
            "line_end": end,
            "text": body,
        }
        if end >= len(lines):
            break


def _source_fingerprint(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
    }


def build_index(
    *,
    repo_root: Path | None = None,
    source_paths: Sequence[str] | None = None,
    chunk_line_count: int = 80,
    overlap_lines: int = 10,
) -> dict[str, Any]:
    """Build a deterministic local retrieval index from repo files."""
    if chunk_line_count <= 0:
        raise ValueError("chunk_line_count_must_be_positive")
    if overlap_lines < 0:
        raise ValueError("overlap_lines_must_be_non_negative")
    if overlap_lines >= chunk_line_count:
        raise ValueError("overlap_lines_must_be_less_than_chunk_line_count")
    root = (repo_root or repo_root_from_here()).resolve()
    sources = tuple(source_paths or DEFAULT_SOURCE_PATHS)
    files = _iter_source_files(root, sources)

    chunks: list[dict[str, Any]] = []
    doc_freq: Counter[str] = Counter()
    total_terms = 0
    source_fingerprints: list[dict[str, Any]] = []

    for path in files:
        rel_path = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        text = _read_text(path)
        source_fingerprints.append(_source_fingerprint(path))
        for chunk in _chunk_lines(
            rel_path,
            text,
            chunk_line_count=chunk_line_count,
            overlap_lines=overlap_lines,
        ):
            terms = tokenize(chunk["text"])
            if not terms:
                continue
            tf = Counter(terms)
            doc_freq.update(tf.keys())
            total_terms += len(terms)
            chunks.append({
                **chunk,
                "term_count": len(terms),
                "term_freq": dict(sorted(tf.items())),
            })

    chunk_count = len(chunks)
    payload: dict[str, Any] = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo_root": str(root),
        "source_paths": list(sources),
        "chunk_line_count": chunk_line_count,
        "overlap_lines": overlap_lines,
        "supported_suffixes": sorted(SUPPORTED_SUFFIXES),
        "max_file_bytes": MAX_FILE_BYTES,
        "chunk_count": chunk_count,
        "avg_document_length": (total_terms / chunk_count) if chunk_count else 0.0,
        "document_frequency": dict(sorted(doc_freq.items())),
        "source_fingerprints": source_fingerprints,
        "authority": authority_flags(),
        "provenance": git_provenance(root),
        "chunks": chunks,
    }
    payload["index_sha256"] = canonical_json_sha(payload)
    return payload


def write_index(index: Mapping[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def load_index(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != INDEX_SCHEMA_VERSION:
        raise ValueError(f"unsupported_index_schema:{payload.get('schema_version')}")
    return payload


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


def _bm25_score(
    query_terms: Sequence[str],
    term_freq: Mapping[str, int],
    *,
    document_frequency: Mapping[str, int],
    document_count: int,
    document_length: int,
    avg_document_length: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    if document_count <= 0 or avg_document_length <= 0:
        return 0.0
    q_counts = Counter(query_terms)
    score = 0.0
    for term, q_count in q_counts.items():
        tf = int(term_freq.get(term, 0))
        if tf <= 0:
            continue
        df = int(document_frequency.get(term, 0))
        idf = math.log(1.0 + (document_count - df + 0.5) / (df + 0.5))
        denom = tf + k1 * (1.0 - b + b * document_length / avg_document_length)
        score += idf * (tf * (k1 + 1.0) / denom) * q_count
    return score


def _trim_snippet(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        raise ValueError("snippet_token_budget_must_be_positive")
    compact = "\n".join(line.rstrip() for line in text.strip().splitlines())
    tokens = tokenize(compact)
    if len(tokens) <= max_tokens:
        return compact
    snippet_tokens = tokens[:max_tokens]
    snippet = " ".join(snippet_tokens).strip()
    while snippet_tokens and len(tokenize(snippet)) > max_tokens:
        snippet_tokens = snippet_tokens[:-1]
        snippet = " ".join(snippet_tokens).strip()
    return (snippet or tokens[0]) + " ..."


def query_index(
    index: Mapping[str, Any],
    query: str,
    *,
    top_k: int = 8,
    snippet_token_budget: int = 200,
) -> dict[str, Any]:
    """Return advisory retrieval candidates from a local index."""
    if top_k <= 0:
        raise ValueError("top_k_must_be_positive")
    if snippet_token_budget <= 0:
        raise ValueError("snippet_token_budget_must_be_positive")
    query_terms = tokenize(query)
    document_count = int(index.get("chunk_count") or 0)
    avg_document_length = float(index.get("avg_document_length") or 0.0)
    document_frequency = index.get("document_frequency") or {}
    scored: list[dict[str, Any]] = []

    for chunk in index.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        score = _bm25_score(
            query_terms,
            chunk.get("term_freq") or {},
            document_frequency=document_frequency,
            document_count=document_count,
            document_length=int(chunk.get("term_count") or 0),
            avg_document_length=avg_document_length,
        )
        if score <= 0:
            continue
        snippet = _trim_snippet(str(chunk.get("text") or ""), snippet_token_budget)
        scored.append({
            "score": round(score, 6),
            "score_semantics": "relevance_only",
            "source_path": chunk.get("source_path"),
            "line_start": chunk.get("line_start"),
            "line_end": chunk.get("line_end"),
            "line_span": [chunk.get("line_start"), chunk.get("line_end")],
            "chunk_id": chunk.get("chunk_id"),
            "snippet": snippet,
            "snippet_token_estimate": len(tokenize(snippet)),
            "degraded_level": "offline_bm25_local",
        })

    scored.sort(key=lambda row: (-float(row["score"]), str(row["source_path"]), int(row["line_start"] or 0)))
    return {
        "schema_version": QUERY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "query": query,
        "query_terms": query_terms,
        "top_k": top_k,
        "index_sha256": index.get("index_sha256"),
        "index_git_sha": (index.get("provenance") or {}).get("git_sha"),
        "authority": authority_flags(),
        "result_count": min(top_k, len(scored)),
        "results": scored[:top_k],
    }
